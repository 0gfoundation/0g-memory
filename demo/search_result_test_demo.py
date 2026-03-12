"""Search Result Test Demo

Purpose:
    Verify that the memory system correctly retrieves topic-relevant memories.
    10 Q&A pairs cover 10 completely unrelated topics with sharp boundaries.
    Then 10 queries (one per topic) confirm retrieval accuracy.

Topics:
    1.  Soccer / Champions League
    2.  Stock market / Tesla
    3.  Cat care after vaccination
    4.  Cooking / Italian pasta recipe
    5.  Travel / Japan trip planning
    6.  Python programming / async patterns
    7.  Fitness / strength training
    8.  Classical music / Beethoven concert
    9.  Ancient Roman history
    10. Space / James Webb Telescope discoveries

Expected result:
    Each query should return only memories related to its own topic,
    with no cross-topic contamination.

Prerequisites:
    Start the API server first (in another terminal):
    uv run python src/run.py

Run:
    uv run python src/bootstrap.py demo/search_result_test_demo.py                        # search only (rrf)
    uv run python src/bootstrap.py demo/search_result_test_demo.py --insert               # insert + search (rrf)
    uv run python src/bootstrap.py demo/search_result_test_demo.py --insert --mode agentic  # insert + search (agentic + rerank)
"""

import argparse
import asyncio
from demo.utils import SimpleMemoryManager


async def main():
    parser = argparse.ArgumentParser(description="Search Result Test Demo")
    parser.add_argument(
        "--insert",
        action="store_true",
        help="Insert the 10 topic conversations before searching",
    )
    parser.add_argument(
        "--mode",
        default="rrf",
        help="Retrieval mode: rrf (default), keyword, vector, hybrid, agentic",
    )
    args = parser.parse_args()
    search_mode = args.mode

    memory = SimpleMemoryManager()

    memory.print_separator("🧪  Search Result Test Demo  (10 Topics × 10 Queries)")

    if args.insert:
        # ========== Step 1: Store 10 Q&A pairs, each on a different topic ==========
        print("\n📝 Step 1: Store Conversations (10 distinct topics)")
        memory.print_separator()

        # ── Topic 1: Soccer ──────────────────────────────────────────────────────
        print("\n  [1] Soccer")
        await memory.store(
            "I watched the Champions League final last night. Real Madrid beat Bayern Munich 3-1. "
            "Mbappe scored twice and Bellingham added the third. Absolutely electric atmosphere."
        )
        await asyncio.sleep(2)
        await memory.store(
            "What a final! Mbappe's pace was unplayable all night. Real Madrid's squad depth is "
            "unreal — even their substitutes are world-class. They're the favorites to retain the "
            "Champions League title next season too.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 2: Stock Market ─────────────────────────────────────────────────
        print("\n  [2] Stock Market")
        await memory.store(
            "Tesla stock dropped 12% today after the earnings call disappointed. I sold half my "
            "position before the dip — reduced my average cost to almost zero. Now thinking about "
            "rotating into dividend ETFs and gold since rates are staying high."
        )
        await asyncio.sleep(2)
        await memory.store(
            "Smart move. The Fed signaling two more rate hikes is brutal for growth stocks. "
            "NVIDIA also fell 8% despite beating earnings — just shows sentiment is everything right now. "
            "Dividend stocks and gold ETFs are a reasonable hedge in this environment.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 3: Cat Care ─────────────────────────────────────────────────────
        print("\n  [3] Cat Care")
        await memory.store(
            "My cat Luna got her annual vaccinations today. The vet said she might be lethargic for "
            "48 hours and I should only give her soft wet food. Also mentioned Luna is slightly "
            "overweight and recommended switching to low-calorie dry food long-term."
        )
        await asyncio.sleep(2)
        await memory.store(
            "Post-vaccination lethargy is completely normal. Keep fresh water available and avoid "
            "stressful situations for a day. For the weight issue, reducing treats to twice a week "
            "and adding a short play session daily can make a big difference over time.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 4: Cooking ──────────────────────────────────────────────────────
        print("\n  [4] Cooking")
        await memory.store(
            "I tried making carbonara from scratch last night. Used guanciale, pecorino romano, "
            "eggs, and black pepper — no cream at all. The sauce broke the first time because "
            "the pan was too hot, but the second attempt came out perfectly silky."
        )
        await asyncio.sleep(2)
        await memory.store(
            "Authentic carbonara is all about temperature control — the residual heat from the pasta "
            "should cook the egg without scrambling it. Pro tip: reserve a cup of pasta water and "
            "add it gradually while tossing. The starch helps emulsify the sauce beautifully.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 5: Travel ───────────────────────────────────────────────────────
        print("\n  [5] Travel")
        await memory.store(
            "I'm planning a 10-day trip to Japan in April for cherry blossom season. Thinking of "
            "splitting time between Tokyo, Kyoto, and Osaka. Not sure whether to get a JR Pass "
            "or buy individual Shinkansen tickets — the math is confusing."
        )
        await asyncio.sleep(2)
        await memory.store(
            "April is peak season — book accommodations now or you'll pay double. For a Tokyo-Kyoto-Osaka "
            "itinerary the JR Pass usually breaks even around the 3rd Shinkansen ride, so it's worth it. "
            "Also budget time for Nara deer park and Fushimi Inari — both are must-sees from Kyoto.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 6: Python Programming ───────────────────────────────────────────
        print("\n  [6] Python Programming")
        await memory.store(
            "I've been refactoring our backend to use asyncio properly. The main pain point is that "
            "some third-party libraries are blocking and freeze the event loop. I'm using "
            "loop.run_in_executor to offload them to a thread pool, but I'm not sure that's the "
            "right pattern long-term."
        )
        await asyncio.sleep(2)
        await memory.store(
            "run_in_executor is the correct approach for CPU-bound or blocking I/O calls that have "
            "no async alternative. For CPU-heavy work consider ProcessPoolExecutor instead of the "
            "default ThreadPoolExecutor to bypass the GIL. Also look into anyio as an abstraction "
            "layer — it makes swapping between asyncio and trio much easier.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 7: Fitness ──────────────────────────────────────────────────────
        print("\n  [7] Fitness")
        await memory.store(
            "I started a 5x5 strength training program three weeks ago — squats, deadlifts, bench "
            "press, overhead press, and barbell rows. My squat went from 60kg to 80kg already. "
            "But my lower back is getting sore after deadlift sessions."
        )
        await asyncio.sleep(2)
        await memory.store(
            "Lower back soreness on deadlifts usually means your hips are shooting up too fast at "
            "the start of the pull — keep your chest up and drive through the floor with your legs "
            "first. Also film yourself from the side to check your bar path. "
            "Consider adding Romanian deadlifts on a separate day to strengthen the posterior chain.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 8: Classical Music ──────────────────────────────────────────────
        print("\n  [8] Classical Music")
        await memory.store(
            "I went to a live performance of Beethoven's Ninth Symphony at the Berlin Philharmonic "
            "last weekend. The fourth movement — the Ode to Joy — gave me chills. "
            "I've heard it dozens of times on recordings but nothing compares to live."
        )
        await asyncio.sleep(2)
        await memory.store(
            "The Berlin Philharmonic's acoustic is legendary — every section is perfectly balanced. "
            "Beethoven's Ninth is extraordinary partly because he was completely deaf when he composed it. "
            "The choral finale was groundbreaking for its time; no symphony before it had ever used a choir. "
            "Karajan's 1963 recording with the BPO is still considered the benchmark.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 9: Ancient History ──────────────────────────────────────────────
        print("\n  [9] Ancient Roman History")
        await memory.store(
            "I've been reading about the fall of the Western Roman Empire. Most people blame the "
            "barbarian invasions, but I think internal factors — debasement of currency, political "
            "instability, over-reliance on mercenary armies — were the real causes. The invasions "
            "were just the final blow to an already collapsing system."
        )
        await asyncio.sleep(2)
        await memory.store(
            "You're citing the 'internal decline' thesis, which historians like Bryan Ward-Perkins "
            "support with hard archaeological data — collapsed trade networks, shrinking cities, "
            "declining literacy. Adrienne Mayor's contrast: the Eastern Empire (Byzantium) survived "
            "another thousand years with essentially the same external threats, which strongly suggests "
            "internal governance was the key variable.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ── Topic 10: Space / James Webb ─────────────────────────────────────────
        print("\n  [10] Space")
        await memory.store(
            "The James Webb Space Telescope just released new images of a galaxy cluster from "
            "13 billion light-years away. The gravitational lensing effect made background galaxies "
            "appear stretched into arcs. It's mind-blowing that we can observe light that left its "
            "source only 800 million years after the Big Bang."
        )
        await asyncio.sleep(2)
        await memory.store(
            "Webb's infrared capability is what makes this possible — Hubble couldn't see that far "
            "back because visible light from the early universe is redshifted into infrared by the "
            "time it reaches us. The gravitational lensing arcs are actually a bonus: they act as "
            "a natural telescope, magnifying objects behind the cluster even further. "
            "Some of those arcs are the faintest objects ever imaged.",
            sender="Assistant",
        )
        await asyncio.sleep(2)

        # ========== Step 2: Wait for Indexing ==========
        print("\n⏳ Step 2: Wait for Index Building")
        memory.print_separator()
        await memory.wait_for_index(seconds=15)

    # ========== Step 3: 10 Queries, one per topic ==========
    print("\n🔍 Step 3: Search Memories (10 queries, one per topic)")
    memory.print_separator()

    print("\n━━━ [Query 1 / Soccer] ━━━")
    await memory.search(
        "What happened in the Champions League final? Who scored the goals?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 2 / Stocks] ━━━")
    await memory.search(
        "What did the user say about their stock investments and Tesla?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 3 / Cat Care] ━━━")
    await memory.search(
        "What did the vet say about Luna the cat after vaccination?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 4 / Cooking] ━━━")
    await memory.search(
        "How did the user make carbonara pasta? What ingredients were used?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 5 / Travel] ━━━")
    await memory.search(
        "What is the user's Japan trip plan? Which cities will they visit?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 6 / Python] ━━━")
    await memory.search(
        "What Python asyncio problem was the user solving? What pattern did they use?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 7 / Fitness] ━━━")
    await memory.search(
        "What strength training program is the user following? What issue did they have with deadlifts?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 8 / Music] ━━━")
    await memory.search(
        "What classical music concert did the user attend? Which symphony was performed?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 9 / History] ━━━")
    await memory.search(
        "What does the user think caused the fall of the Roman Empire?",
        user_id="",
        mode=search_mode,
    )

    print("\n━━━ [Query 10 / Space] ━━━")
    await memory.search(
        "What did the James Webb Space Telescope recently discover or photograph?",
        user_id="",
        mode=search_mode,
    )

    # ========== Done ==========
    memory.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
