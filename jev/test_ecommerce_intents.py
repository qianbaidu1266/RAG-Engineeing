
from dotenv import load_dotenv
load_dotenv()

import os
from typesafe_sdk import TypeSafeClient, Choice


def test_ecommerce_intents(client: TypeSafeClient, messages: list[str]):
    """电商售后意图识别：语义高度重叠的 qid 测试"""

    # 五个语义高度相近的售后 qid
    qid_criteria = {
        "return_refund": "用户要求退货退款，需要把商品寄回给商家",
        "refund_only": "用户要求仅退款，不寄回商品，商品自行处理",
        "exchange": "用户要求更换同款商品，不涉及退款",
        "reship": "用户要求补发缺少的配件或商品，不退款不退货",
        "price_protection": "用户要求退还降价差价，商品保留不退货",
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
                    instructions="这条用户消息最匹配哪个售后处理方式？",
                    criteria=qid_criteria
                )
            }
        )

        answer = response.answers["qid"]
        print(f"Top-1 qid: {answer.choice}")
        print(f"置信度:    {answer.confidence:.3f}")
        print(f"完整概率分布:")
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
        "这个东西我不要了，把钱退给我。",
        "我收到的商品和描述不符，怎么处理？",
        "少了一个零件，怎么办？",
        "买完就降价了，能退我钱吗？",
    ]

    test_ecommerce_intents(client, test_messages)


if __name__ == "__main__":
    main()