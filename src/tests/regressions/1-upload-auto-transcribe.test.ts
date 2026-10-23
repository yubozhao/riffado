import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ enabled: true, transcribe: vi.fn() }));
vi.mock("@/db", () => ({
    db: {
        select: () => ({
            from: () => ({
                where: () => ({
                    limit: async () => [{ autoTranscribe: mocks.enabled }],
                }),
            }),
        }),
    },
}));
vi.mock("@/lib/transcription/transcribe-recording", () => ({
    transcribeRecording: mocks.transcribe,
}));

import { transcribeNewUpload } from "@/lib/transcription/auto-transcribe-upload";

describe("automatic local upload transcription", () => {
    beforeEach(() => {
        mocks.enabled = true;
        mocks.transcribe.mockReset().mockResolvedValue({ success: true });
    });
    it("transcribes the newly inserted recording when enabled", async () => {
        await transcribeNewUpload("owner", "new-upload");
        expect(mocks.transcribe).toHaveBeenCalledExactlyOnceWith(
            "owner",
            "new-upload",
            { trigger: "upload" },
        );
    });
    it("does not transcribe when automatic transcription is off", async () => {
        mocks.enabled = false;
        await transcribeNewUpload("owner", "new-upload");
        expect(mocks.transcribe).not.toHaveBeenCalled();
    });
});
