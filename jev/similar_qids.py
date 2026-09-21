

from dotenv import load_dotenv
load_dotenv()          # ← 这一行必须在读取 os.environ 之前执行

import os
from typesafe_sdk import TypeSafeClient, Choice


def test_similar_qids(client: TypeSafeClient, messages: list[str]):
    """测试 Jev 对语义相近 qid 的区分能力"""

    # 语义高度相近的三个 qid
    qid_criteria = {
        "cancel_by_passenger":
            "乘客主动取消订单，询问如何取消、取消操作或取消规则",

        "cancel_fee_by_passenger":
            "乘客主动取消订单后，被收取了取消费，询问为什么收费或要求退还取消费",

        "driver_cancel":
            "司机主动取消订单，乘客询问司机为什么取消、司机取消订单或司机取消导致订单结束",

        "driver_no_show":
            "司机已经接单，但长时间没有到达上车点，乘客想取消订单或询问司机为什么不来",

        "driver_asked_passenger_cancel":
            "司机要求或诱导乘客主动取消订单，例如让乘客自己取消、让乘客取消后重新叫车",

        "order_auto_cancel":
            "订单没有被乘客或司机主动取消，而是因为超时、系统原因等自动取消",
    }

    for idx, msg in enumerate(messages, 1):
        print(f"\n{'='*60}")
        print(f"测试 {idx}: {msg}")
        print(f"{'='*60}")

        response = client.system_one(
            model="jev-latest",
            state=msg,
            questions={
                "qid": Choice(
                    instructions="这条用户消息最匹配哪个标准问？",
                    criteria=qid_criteria
                )
            }
        )

        answer = response.answers["qid"]
        print(f"匹配 qid: {answer.choice}")
        print(f"置信度:   {answer.confidence:.3f}")
        print(f"概率分布:")
        for qid, prob in sorted(answer.probabilities.items(),
                                key=lambda x: -x[1]):
            bar = "█" * int(prob * 40)
            print(f"  {qid:20s} {prob:.4f}  {bar}")


def main():
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        raise RuntimeError("请设置 TYPESAFE_API_KEY")

    client = TypeSafeClient(api_key=api_key)

    test_messages = [
        "我不想打车了，怎么取消订单？",

        "我取消订单为什么还要收我钱？",

        "司机怎么把我的订单取消了？",

        "司机接单半天了还没过来，我能取消吗？",

        "司机让我自己把订单取消掉，说他不想接了。",

        "订单怎么突然自己没了，我也没取消啊？",

        "司机让我取消订单重新叫一个，这是什么情况？",

        "我把订单取消了，被扣了20块取消费，能退吗？",

        "司机已经接单了，但是一直不来，我取消后还扣费了。",
    ]

    test_similar_qids(client, test_messages)


if __name__ == "__main__":
    main()