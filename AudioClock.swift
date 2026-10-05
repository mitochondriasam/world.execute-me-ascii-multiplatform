import Foundation
import AVFoundation

final class PlaybackDelegate: NSObject, AVAudioPlayerDelegate {
    var ended = false
    var error: String? = nil
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        ended = flag
        if !flag { error = "Audio playback failed" }
    }
    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        self.error = error?.localizedDescription ?? "Audio decode failed"
    }
}

// The audio device owns the timeline. The terminal consumes currentTime.
do {
    guard CommandLine.arguments.count > 1 else { throw NSError(domain: "Missing audio path", code: 1) }
    let player = try AVAudioPlayer(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    let playback = PlaybackDelegate()
    player.delegate = playback
    player.prepareToPlay()
    player.volume = 0.75
    var quitting = false
    var pending = ""
    let input = FileHandle.standardInput
    input.readabilityHandler = { handle in
        let data = handle.availableData
        DispatchQueue.main.async {
            if data.isEmpty { quitting = true; return }
            pending += String(decoding: data, as: UTF8.self)
            while let newline = pending.firstIndex(of: "\n") {
                let line = String(pending[..<newline])
                pending.removeSubrange(...newline)
                let fields = line.split(separator: " ")
                switch fields.first {
                case "play":
                    if !player.play() {
                        FileHandle.standardOutput.write(Data("{\"error\":\"Audio output unavailable\"}\n".utf8))
                    }
                case "pause": player.pause()
                case "seek":
                    if fields.count > 1, let t = Double(fields[1]) {
                        player.currentTime = min(max(0, t), max(0, player.duration - 0.01))
                        playback.ended = false
                    }
                case "volume":
                    if fields.count > 1, let v = Float(fields[1]) { player.volume = min(1, max(0, v)) }
                case "quit": quitting = true
                default: break
                }
            }
        }
    }
    while !quitting {
        RunLoop.current.run(until: Date(timeIntervalSinceNow: 1.0 / 60.0))
        var state: [String: Any] = ["time": player.currentTime, "duration": player.duration,
                                   "playing": player.isPlaying, "ended": playback.ended, "volume": player.volume]
        if let message = playback.error { state = ["error": message] }
        let data = try JSONSerialization.data(withJSONObject: state)
        FileHandle.standardOutput.write(data + Data("\n".utf8))
    }
    input.readabilityHandler = nil
    player.stop()
} catch {
    FileHandle.standardError.write(Data("Audio error: \(error.localizedDescription)\n".utf8))
    exit(1)
}
