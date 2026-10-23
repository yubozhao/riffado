import { eq } from "drizzle-orm";
import { db } from "@/db";
import { userSettings } from "@/db/schema";
import { transcribeRecording } from "@/lib/transcription/transcribe-recording";

/** Honor automatic transcription for a newly committed local upload. */
export async function transcribeNewUpload(
    userId: string,
    recordingId: string,
): Promise<void> {
    const [settings] = await db
        .select({ autoTranscribe: userSettings.autoTranscribe })
        .from(userSettings)
        .where(eq(userSettings.userId, userId))
        .limit(1);
    if (settings?.autoTranscribe) {
        await transcribeRecording(userId, recordingId, { trigger: "upload" });
    }
}
