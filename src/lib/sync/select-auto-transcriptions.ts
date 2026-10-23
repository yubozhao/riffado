import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { apiCredentials } from "@/db/schema";
import { findPreset } from "@/lib/ai/provider-presets";
import { listAutoTranscribeRetryIds } from "@/lib/sync/auto-transcribe-state";

/** Select new recordings and any backlog eligible for automatic transcription. */
export async function selectAutoTranscriptionIds(
    userId: string,
    newIds: string[],
    options: { providerId?: string | null; transcriptMode: string },
): Promise<string[]> {
    const [provider] = await db
        .select({ provider: apiCredentials.provider })
        .from(apiCredentials)
        .where(
            and(
                eq(apiCredentials.userId, userId),
                options.providerId
                    ? eq(apiCredentials.id, options.providerId)
                    : eq(apiCredentials.isDefaultTranscription, true),
            ),
        )
        .limit(1);
    if (
        findPreset(provider?.provider ?? "")?.retryTranscriptionBacklog ===
        false
    ) {
        return [...new Set(newIds)];
    }
    try {
        const retryIds = await listAutoTranscribeRetryIds(userId, {
            transcriptMode: options.transcriptMode,
        });
        return [...new Set([...newIds, ...retryIds])];
    } catch (error) {
        console.error("Auto-transcribe retry lookup failed:", error);
        return [...new Set(newIds)];
    }
}
