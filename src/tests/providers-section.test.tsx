/** @vitest-environment jsdom */

import {
    act,
    cleanup,
    fireEvent,
    render,
    screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProvidersSection } from "@/components/settings-sections/providers-section";

vi.mock("@/components/confirm-dialog", () => ({
    useConfirm: () => vi.fn(),
}));
vi.mock("@/components/settings/add-provider-dialog", () => ({
    AddProviderDialog: ({ onSuccess }: { onSuccess: () => void }) => (
        <button type="button" onClick={onSuccess}>
            Simulate provider added
        </button>
    ),
}));
vi.mock("@/components/settings/edit-provider-dialog", () => ({
    EditProviderDialog: () => null,
}));
vi.mock("@/components/settings-sections/prompt-manager", () => ({
    PromptManager: () => null,
}));

const voiceInk = {
    id: "voiceink",
    provider: "VoiceInk",
    defaultModel: "voiceink-app",
    baseUrl: "http://host.docker.internal:8084/v1",
    isDefaultTranscription: true,
    isDefaultEnhancement: false,
    createdAt: new Date(),
};

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

describe("provider list loading", () => {
    it("loads configured providers when the settings dialog opens with an empty seed", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(Response.json({ providers: [voiceInk] })),
        );
        render(<ProvidersSection initialProviders={[]} />);
        expect(
            await screen.findByRole("heading", { name: "VoiceInk" }),
        ).toBeTruthy();
        expect(screen.queryByText("No providers configured")).toBeNull();
    });

    it("does not let an older load overwrite a provider mutation refresh", async () => {
        let finishInitial: (response: Response) => void = () => {};
        const initialResponse = new Promise<Response>((resolve) => {
            finishInitial = resolve;
        });
        vi.stubGlobal(
            "fetch",
            vi
                .fn()
                .mockReturnValueOnce(initialResponse)
                .mockResolvedValueOnce(
                    Response.json({ providers: [voiceInk] }),
                ),
        );
        render(<ProvidersSection initialProviders={[]} />);
        fireEvent.click(
            screen.getByRole("button", { name: "Simulate provider added" }),
        );
        expect(
            await screen.findByRole("heading", { name: "VoiceInk" }),
        ).toBeTruthy();
        await act(async () => {
            finishInitial(Response.json({ providers: [] }));
        });
        expect(screen.getByRole("heading", { name: "VoiceInk" })).toBeTruthy();
    });
});
