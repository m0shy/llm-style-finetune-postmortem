# -*- coding: utf-8 -*-
"""为每本源书抽「专名表」——用于给训练样本注入专名锚点块

动机（v5 评测的硬证据）：
  v5 在「大纲式」探针上把《灵境行者》的「李东泽」（该书出现 717 次）当主角写了进来，
  完全无视 prompt 里给的专名锚点。原因是：**训练时从来没有过锚点块**，
  模型没学过"要用锚点里给的名字"，于是退回它最强的先验（灵境人物表）。
  训练充分度越高，这个先验越强，所以 v5 反而比 v3 更差。

修法：训练样本也带上锚点块，但用**该本源书自己的名字**。
模型学到的是机制（"锚点里列的名字就是要用的名字"），而不是某一份具体名单。
  - 训练时：灵境样本的锚点块 = 灵境的人物（张元清、李东泽、王泰……）
  - 推理时：你的样本的锚点块 = 你的本作专名（主角、示例角色12……）

用法：python scripts/build_glossary.py
输出：data_dual/glossary.json  {书名: [名字, ...]}
"""
import json, os, re, sys, io
from collections import Counter

try:
    sys.stdout.reconfigure(encoding='utf-8')   # 原地重配置；新建 TextIOWrapper 会接管
except Exception:                              # 底层缓冲，旧对象被回收时会把流关掉
    pass
DS = r'<项目目录>\Datasets'
OUT = os.path.join(DS, 'data_dual', 'glossary.json')

SRC_HOME = r'<old-lib>'
BOOKS = {
    '灵境行者': [os.path.join(SRC_HOME, '《灵境行者》', n) for n in
                 ('灵境行者(1-500章).txt', '灵境行者(501-1000章).txt')],
    '大奉打更人': [os.path.join(SRC_HOME, '《大奉打更人》', n) for n in
                   ('大奉打更人(1-500章).txt', '大奉打更人(501-955章).txt')],
    '玩家凶猛': [os.path.join(SRC_HOME, '《玩家凶猛》', '玩家凶猛.txt')],
    '恐怖屋': [os.path.join(SRC_HOME, '参考', '我有一座恐怖屋.txt')],
    '还剩三个月命': [os.path.join(SRC_HOME, '参考', '还剩三个月命，请让我从容赴死.txt')],
}

SURNAMES = ('赵钱孙李周吴郑王冯陈蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜谢邹柏窦章云苏潘葛'
            '范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅齐康'
            '余元卜顾孟平黄和穆萧尹姚邵汪祁毛狄贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝'
            '闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万柯管卢莫房裘解宗'
            '丁宣邓郁单杭洪包诸左石崔吉龚程邢滑裴陆荣翁荀羊惠甄曲封芮储靳段富巫乌焦巴弓牧'
            '山谷车侯全班仲伊宫宁仇栾甘厉戎祖武符刘詹束龙叶幸司韶黎薄印宿白怀蒲从鄂索咸赖'
            '卓蔺屠蒙池乔阴胥苍闻党翟谭贡劳姬申扶堵冉雍桑桂牛寿通边燕浦尚农温别庄晏柴瞿阎'
            '充慕连茹习艾鱼容向古易慎戈廖庾终居衡步都耿满弘匡国文寇广禄欧沃利蔚越隆师巩聂'
            '晁融冷辛那简饶空曾沙养鞠须丰巢关蒯相查荆红游竺权盖益桓')
STOP = set('王者 王国 历史 于是 结果 同时 随后 顿时 武侠 文字 天才 天空 白天 明明 江湖 江水 '
           '山东 东南 西边 北上 中华 人生 任务 何必 何况 允许 许多 李子 石头 包住 陈述 张开 '
           '程度 方程 柳树 疏通 雷霆 容纳 向阳 古今 实际 步调 众多 任意 无奈 冷清 戈壁 融洽 '
           '简便 子孙 叶子 关怀 查探 石破 时辰 老人 少年 中年 男人 女人 对方 众人 '
           '那么 那我 那是 那是一 那时 那边 这时 终于 闻言 相比 解释 高声 冷冷 房间 平静 '
           '居然 空气 明天 毕竟 从那 从小 从来 谢谢 孩子 周围 幸运 司机 游客 红衣 相当 '
           '游戏 欧洲 全球 通灵 白色 红色 黑色 突然 显然 果然 虽然 当然 既然 必然 猛然 '
           '回过 站在 坐在 看着 看向 抬头 低头 转身 开口 出声 沉默 点头 摇头 皱眉 冷笑'.split())
BAD_TAIL = set('的了是在把和与而且但就是大继脸道想呢来着过说笑看走站坐起落问答总好新'
               '会能要可都也就又还只很太更最真更上下里外前后中')
LEFT_OK = set('，。！？；：、“”「」"\' \n\t（()）　·…')
SPEECH = ('说道', '道：', '问道', '笑道', '冷笑', '皱眉', '点头', '摇头', '开口', '出声',
          '低声道', '沉声道', '喃喃', '看着', '看向', '站在', '坐在', '走了', '说：', '道，')


def read(p):
    for enc in ('utf-8', 'gbk'):
        try:
            return __import__('scan_noise').read_text(p)   # 2026-09-16 统一修缮：原 errors='ignore' 对 GBK 静默出错
        except Exception:
            continue
    return ''


def extract(files, topn=34):
    cnt = Counter()
    for f in files:
        if not os.path.isfile(f):
            continue
        t = read(f)
        for m in re.finditer(r'[' + SURNAMES + r']', t):
            i = m.start()
            left_ok = (i == 0) or (t[i - 1] in LEFT_OK)
            for L in (3, 2):
                w = t[i:i + L]
                if len(w) < L or not re.fullmatch(r'[\u4e00-\u9fff]+', w):
                    continue
                tail = t[i + L:i + L + 2]
                if not (left_ok or any(tail.startswith(v) for v in SPEECH)):
                    continue
                if w[-1] in BAD_TAIL or w in STOP:
                    continue
                cnt[w] += 1
                break
    # 只保留出现次数达标的，且同一前缀只留最高频的一个分支
    keep = [(w, c) for w, c in cnt.most_common(topn * 4) if c >= 25]
    names, seen = [], set()
    for w, c in keep:
        if len(names) >= topn:
            break
        if w[0] in seen and len([x for x in names if x[0] == w[0]]) >= 2:
            continue
        names.append(w)
        seen.add(w[0])
    return names


# 人工增删（自动抽词难免带噪声、也难免漏掉高频主角，这一层兜住）
DROP = {'元始天', '夏侯傲', '元清', '宫主', '关雅姐', '李昂点', '柴大小', '欧洲重', '全球超',
        '从背包', '相当于', '游戏币', '那么他', '那孩子', '那个', '红色高', '越来越', '白衣术',
        '云鹿书', '安点', '孙长老', '蔡长老', '赵长老', '陈贵妃', '安博', '通常', '时间',
        '沙哑', '慕诗', '司天监', '巫神教', '云鹿书', '武林盟', '通灵鬼', '红衣老', '居天赋'}
ADD = {
    # 以下每个都已在源书原文中核实过出现次数（零虚构原则）
    '灵境行者': ['王泰', '小圆', '元始天尊'],          # 254 / 929 / 3381 次
    '大奉打更人': ['许铃音', '李妙真', '楚元缜', '洛玉衡'],  # 395 / 1266 / 689 / 484 次
}


def main():
    g = {}
    for book, files in BOOKS.items():
        names = [n for n in extract(files) if n not in DROP]
        for extra in ADD.get(book, []):
            if extra not in names:
                names.append(extra)
        g[book] = names
        print(f'{book}({len(names)}): {"、".join(names)}')
    json.dump(g, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n已写出 {OUT}')


if __name__ == '__main__':
    main()
