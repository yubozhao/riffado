import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ provider: "VoiceInk", retry: vi.fn() }));
vi.mock("@/db", () => ({
    db: {
        select: vi.fn(() => ({
            from: () => ({
                where: () => ({
                    limit: async () => [{ provider: mocks.provider }],
                }),
            }),
        })),
    },
}));
vi.mock("@/lib/sync/auto-transcribe-state", () => ({
    listAutoTranscribeRetryIds: mocks.retry,
}));

import { selectAutoTranscriptionIds } from "@/lib/sync/select-auto-transcriptions";

describe("VoiceInk automatic transcription", () => {
    beforeEach(() => {
        mocks.provider = "VoiceInk";
        mocks.retry.mockReset().mockResolvedValue(["old-failure"]);
    });

    it("only queues newly added recordings and never retries the old backlog", async () => {
        expect(
            await selectAutoTranscriptionIds("user", ["new", "new"], {
                providerId: "voiceink-id",
                transcriptMode: "keep_both",
            }),
        ).toEqual(["new"]);
        expect(mocks.retry).not.toHaveBeenCalled();
    });

    it("does not launch work when a sync has no new recordings", async () => {
        expect(
            await selectAutoTranscriptionIds("user", [], {
                providerId: "voiceink-id",
                transcriptMode: "keep_both",
            }),
        ).toEqual([]);
        expect(mocks.retry).not.toHaveBeenCalled();
    });

    it("keeps backlog retry behavior for other providers", async () => {
        mocks.provider = "OpenAI";
        expect(
            await selectAutoTranscriptionIds("user", ["new"], {
                transcriptMode: "keep_both",
            }),
        ).toEqual(["new", "old-failure"]);
        expect(mocks.retry).toHaveBeenCalledWith("user", {
            transcriptMode: "keep_both",
        });
    });
});
