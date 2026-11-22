# Xử lý bản ghi JFR lớn mà không đọc toàn bộ vào bộ nhớ trong Java 11

**Chủ đề cha:** Đọc bản ghi JFR  
**Đề bài:** Xử lý bản ghi lớn mà không đọc toàn bộ vào bộ nhớ  
**Phạm vi:** API `jdk.jfr.consumer.RecordingFile`, lọc `RecordedEvent`, tổng hợp liên tục, xuất CSV theo dòng, Top-K có giới hạn, lỗi file và yêu cầu bộ nhớ. Nội dung chỉ dựa trên những kiến thức **vẫn còn áp dụng đến hiện giờ**; ví dụ dùng đúng API Java 11, không đưa các API chỉ có từ Java 14 vào chương trình Java 11.

Một bản ghi Java Flight Recorder (`.jfr`) có thể chứa hàng triệu sự kiện từ JVM và ứng dụng: GC, CPU, threads, allocation, I/O, lock, stack trace và custom events. Mỗi event có kiểu, timestamps, trường riêng và metadata. Nếu dùng `RecordingFile.readAllEvents(path)`, API trả về một `List<RecordedEvent>` gồm **tất cả events** trước khi bạn có cơ hội lọc hay thống kê. Javadoc Java SE 11 nói rõ phương thức này dùng cho trường hợp đơn giản và **không dành cho file lớn**.

Giải pháp là đọc **từng event** bằng `RecordingFile`, xử lý và loại bỏ event ngay trong vòng lặp. Với count/min/max/total chỉ cần vài biến; với Top-K giữ K summaries; với CSV ghi từng record ra writer có buffer. Không thu thập tất cả events vào `List`, `Map` có số key tăng vô hạn hoặc `StringBuilder` cho cả file.

**Giới hạn phải hiểu đúng:** Giảm bộ nhớ **ứng dụng giữ lại theo số sự kiện** không có nghĩa JVM/JFR decoder luôn dùng một lượng RAM tuyệt đối cố định: parser có buffers, chunk metadata và các objects trung gian. Cần kiểm soát nguồn input, kích thước file, số concurrent readers và đo heap/RSS trên dữ liệu thật.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `RecordingFile.readAllEvents` tạo áp lực heap với file lớn.
2. Sử dụng `try (RecordingFile file = new RecordingFile(path))`, `hasMoreEvents()` và `readEvent()` để đọc tuần tự.
3. Lọc theo `event.getEventType().getName()` trước khi gọi `getInt/getLong/getString`.
4. Khám phá metadata bằng `RecordingFile.readEventTypes()` và `EventType.getFields()`.
5. Thiết kế tổng hợp `O(1)`, group-by `O(G)`, histogram có giới hạn, Top-K `O(K)`.
6. Xuất CSV tăng dần bằng `BufferedWriter`, xử lý quote/comma/newline và spreadsheet formula injection.
7. Phân biệt synthetic latency field với duration JFR lấy từ `RecordedEvent.getDuration()`.
8. Xử lý `EOFException`, `IOException` và file thiếu/hỏng, không báo success cho kết quả partial.
9. Giới hạn việc giữ events trong queues, futures, logs, caches và temporary data.
10. Chạy các ví dụ Java 11 tạo recording rồi đọc lại và xác minh kết quả chính xác.

## 2. So sánh các chiến lược đọc

| Nhu cầu | Cách làm | Bộ nhớ ứng dụng tích lũy |
|---|---|---|
| Lấy toàn bộ events | `RecordingFile.readAllEvents(path)` | `O(N)` sự kiện |
| Đếm/tổng/min/max | Cập nhật các biến số | `O(1)` |
| Đếm theo vài status cố định | Mỗi status một counter | `O(1)` |
| Group-by type đã biết | Map type → count | `O(G)`, phải giới hạn G |
| Top-K events | Min-heap chỉ có K entries | `O(K)` |
| Histogram hữu hạn | Mảng bins cố định | `O(B)` |
| Ghi CSV/JSON Lines từng record | Buffered writer | Không giữ toàn output |
| Dùng `Collectors.toList()` hoặc `StringBuilder` toàn file | Materialize toàn bộ | `O(N)` hoặc `O(output bytes)` |
| Group theo unique requestId không hạn mức | Map tăng theo cardinality | Có thể trở thành `O(N)` |

N là số events, K số phần tử muốn giữ, G số nhóm, B số bins. Các giới hạn này nói về **state ứng dụng**, không bao gồm parser buffers, JFR chunk internals, GC, những string/stack rất lớn, file output và native memory.

### 2.1 readAllEvents không sai, chỉ không đúng cho file lớn

`readAllEvents` hoàn toàn hữu ích cho test nhỏ hoặc công cụ tương tác xử lý vài event. Nhưng gọi nó rồi chạy `stream().filter(...).count()` vẫn giữ toàn bộ danh sách vì filter diễn ra **sau khi đã đọc hết**. Tăng `-Xmx` có thể trì hoãn lỗi OOM chứ không sửa độ phức tạp.

Ví dụ phương án không nên dùng trên file nhiều triệu sự kiện:

```java
List<RecordedEvent> all = RecordingFile.readAllEvents(path);
long errors = all.stream()
        .filter(e -> "training.jfr.PayloadEvent".equals(
                e.getEventType().getName()))
        .count();
```

Đây là **trích đoạn minh họa anti-pattern**, không phải chương trình đầy đủ. Nó giữ danh sách N events rồi mới lọc.

## 3. API RecordingFile của Java 11

| Phương thức | Ý nghĩa | Lưu ý |
|---|---|---|
| `new RecordingFile(Path)` | Mở file recording JFR | Có thể ném IOException nếu file hỏng/thiếu/không đọc được |
| `hasMoreEvents()` | Trả true khi còn event chưa đọc | Điều kiện chuẩn cho vòng lặp |
| `readEvent()` | Đọc event tiếp theo | Trả `RecordedEvent` hoặc ném IOException/EOFException |
| `readEventTypes()` | List metadata `EventType` | Không phải List tất cả events |
| `close()` | Đóng reader, giải phóng tài nguyên | Dùng try-with-resources |
| `readAllEvents(Path)` | Đọc hết và trả `List<RecordedEvent>` | Tránh với file lớn |

Ví dụ method đọc đúng cách:

```java
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.io.IOException;
import java.nio.file.Path;

public class JfrCounter {
    public static long count(Path input, String wantedType)
            throws IOException {
        long count = 0;
        try (RecordingFile file = new RecordingFile(input)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (wantedType.equals(event.getEventType().getName())) {
                    count = Math.addExact(count, 1L);
                }
            }
        }
        return count;
    }
}
```

Đây là **class Java 11 có thể biên dịch**, nhưng không có `main`: gọi `JfrCounter.count(path,name)` từ chương trình điều phối. `Math.addExact` giúp phát hiện trường hợp bộ đếm vượt `long` thay vì âm thầm overflow. Ở vòng lặp không giữ reference tới mỗi event sau khi đã xử lý.

### 3.1 Event type và field

`RecordedEvent` extends `RecordedObject`, có:

- `event.getEventType().getName()`: tên type như `jdk.CPULoad` hoặc `training.jfr.PayloadEvent`.
- `event.getInt("id")`, `getLong("latencyMicros")`, `getString("status")`: getters typed.
- `event.hasField("field")`: kiểm tra field tồn tại.
- `event.getStartTime()`, `getEndTime()`, `getDuration()`: thời gian thực của event.
- `event.getStackTrace()`: có thể null khi không ghi stack, và không cần truy cập nếu chỉ đếm.
- `event.getEventType().getFields()`: metadata field descriptors.

Luôn **lọc type trước khi đọc field**. Event `jdk.CPULoad` không có trường `requestId` của custom event; `getInt` cho field không tồn tại/không đúng kiểu có thể ném `IllegalArgumentException`. Với input từ JDK khác, nên kiểm tra `hasField` và type schema theo version.

### 3.2 Type name khác label

`getName()` là identifier, ví dụ `"training.jfr.PayloadEvent"`. `@Label` là nhãn hiển thị, có thể thay theo công cụ/ngôn ngữ, không dùng làm key tương thích. `EventType.getId()` cũng không nên hardcode giữa các JVM/files vì ID được cấp theo runtime.

### 3.3 Metadata không phải tất cả events

`readEventTypes()` trả list event types của recording, có thể dùng một lần để khám phá schema. Nó không materialize toàn bộ events như `readAllEvents`, tuy metadata vẫn tốn bộ nhớ. Không gọi `readEventTypes()` bên trong vòng lặp nhiều triệu lần.

## 4. Mẫu pipeline xử lý file lớn

```text
Input .jfr (validate trusted source, size and policy)
      |
      v
try (RecordingFile file = new RecordingFile(path))
      |
      v
while (file.hasMoreEvents()):
      |
    event = file.readEvent()
      |
    if wrong type: continue
      |
    validate schema and extract required fields
      |
      +--> update counters/histogram
      +--> maintain bounded Top-K heap
      +--> BufferedWriter.write(one record)
      |
      v
 next event
      |
      v
close reader, close writer, verify and publish output
```

Reader vẫn phải parse dữ liệu để tìm events cần thiết, nên lọc type/time trong vòng lặp **giảm state/output**, không phải tạo một index ngẫu nhiên cho phép skip byte của file. Nếu source có hàng nghìn loại event, tránh gọi `event.toString()` hoặc dựng stack trace đầy đủ khi bạn chỉ cần một counter.

## 5. Demo 1 — đọc 12.000 events và tổng hợp O(1)

Chương trình tạo recording tạm, bật custom `training.jfr.PayloadEvent`, ghi **12.000** events với ID từ 0 tới 11999, payloadBytes `i % 100`, status ERROR nếu `i % 4 == 0` còn lại OK. Consumer đọc tuần tự và chỉ giữ vài counters, tổng bytes, min/max ID; không tạo `List<RecordedEvent>`.

Lưu thành **`JfrLargeSummaryDemo.java`**:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class JfrLargeSummaryDemo {
    @Name("training.jfr.PayloadEvent")
    @StackTrace(false)
    @Threshold("0 ms")
    static class PayloadEvent extends Event {
        int id;
        int payloadBytes;
        String status;
    }

    public static void main(String[] args) throws Exception {
        final int expectedEvents = 12000;
        Path path = Files.createTempFile("jfr-large-summary-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(PayloadEvent.class)
                         .withoutThreshold()
                         .withoutStackTrace();
                recording.start();
                for (int i = 0; i < expectedEvents; i++) {
                    PayloadEvent event = new PayloadEvent();
                    event.id = i;
                    event.payloadBytes = i % 100;
                    event.status = i % 4 == 0 ? "ERROR" : "OK";
                    event.commit();
                }
                recording.stop();
                recording.dump(path);
            }

            long count = 0L, ok = 0L, error = 0L, totalBytes = 0L;
            int minId = Integer.MAX_VALUE, maxId = Integer.MIN_VALUE;
            boolean metadataFound = false;
            try (RecordingFile file = new RecordingFile(path)) {
                metadataFound = file.readEventTypes().stream()
                        .anyMatch(type -> "training.jfr.PayloadEvent"
                                .equals(type.getName()));
                while (file.hasMoreEvents()) {
                    RecordedEvent event = file.readEvent();
                    if (!"training.jfr.PayloadEvent".equals(
                            event.getEventType().getName())) {
                        continue;
                    }
                    int id = event.getInt("id");
                    count++;
                    totalBytes += event.getInt("payloadBytes");
                    minId = Math.min(minId, id);
                    maxId = Math.max(maxId, id);
                    if ("ERROR".equals(event.getString("status"))) {
                        error++;
                    } else if ("OK".equals(event.getString("status"))) {
                        ok++;
                    } else {
                        throw new AssertionError("Unexpected status");
                    }
                }
            }
            System.out.println("metadata-found=" + metadataFound);
            System.out.println("events=" + count);
            System.out.println("ok=" + ok);
            System.out.println("error=" + error);
            System.out.println("bytes-total=" + totalBytes);
            System.out.println("id-range=" + minId + ".." + maxId);
            System.out.println("retained-event-list=false");
            if (!metadataFound || count != expectedEvents || ok != 9000
                    || error != 3000 || totalBytes != 594000
                    || minId != 0 || maxId != 11999) {
                throw new AssertionError("Streaming aggregation mismatch");
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrLargeSummaryDemo.java
java --add-modules jdk.jfr JfrLargeSummaryDemo
```

**Stdout đã kiểm chứng:**

```text
metadata-found=true
events=12000
ok=9000
error=3000
bytes-total=594000
id-range=0..11999
retained-event-list=false
```

**Giải thích kết quả:**

- `metadata-found=true` xác nhận `readEventTypes()` có type custom.
- `events=12000` là số event **đúng type custom**, không phải tổng mọi loại event hệ thống trong file.
- `ok=9000`, `error=3000` do công thức tạo dữ liệu.
- `bytes-total=594000` là tổng toán học xác định từ 120 chu kỳ `0..99`, không phụ thuộc timestamp.
- `id-range=0..11999` xác minh không bỏ các endpoints trong fixture.
- `retained-event-list=false` là thông tin về **thuật toán demo**, không phải phép đo heap tuyệt đối hay bằng chứng parser không buffer.

Nếu muốn kiểm tra chương trình thực tế với file của người dùng, tách hẳn phần tạo recording khỏi phần đọc; phần đọc theo vòng lặp vẫn giống hệt. Dùng `long` cho counters/totals khi số event có thể vượt khả năng biểu diễn của `int`.

## 6. Demo 2 — xuất CSV từng dòng không giữ toàn output

Bên cạnh counters, một yêu cầu thực tế là chuyển vài fields của JFR sang CSV để phân tích bằng công cụ khác. Không dùng `StringBuilder` để ghép toàn output rồi một lần `Files.writeString`, vì output có thể dài hàng GB.

Chương trình sau:

1. Ghi 4 `ExportEvent` và 1 `IgnoredEvent` vào recording test.
2. Dùng một `RecordingFile` và một `BufferedWriter` trong cùng try-with-resources.
3. Chỉ ghi rows từ đúng type `training.jfr.ExportEvent`.
4. Escape dấu phẩy, dấu nháy kép, CR/LF theo CSV.
5. Minh họa việc **trung hòa công thức** cho giá trị dạng `=2+2` khi CSV sẽ được mở trong spreadsheet. Đây là defense-in-depth đặc thù consumer; phải test theo phần mềm và security policy đích.
6. Đóng reader/writer trước khi xác nhận file, và xóa các file tạm.

Lưu thành **`JfrCsvStreamingDemo.java`**:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class JfrCsvStreamingDemo {
    @Name("training.jfr.ExportEvent")
    static class ExportEvent extends Event {
        int id;
        String status;
        String message;
    }

    @Name("training.jfr.IgnoredEvent")
    static class IgnoredEvent extends Event {
        String note;
    }

    static String csvCell(String input) {
        String value = input == null ? "" : input;
        int start = 0;
        while (start < value.length()
                && Character.isWhitespace(value.charAt(start))) {
            start++;
        }
        if (start < value.length()
                && "=+-@".indexOf(value.charAt(start)) >= 0) {
            value = "'" + value;
        }
        if (value.indexOf(',') >= 0 || value.indexOf('"') >= 0
                || value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0) {
            return "\"" + value.replace("\"", "\"\"") + "\"";
        }
        return value;
    }

    static void commit(int id, String status, String message) {
        ExportEvent event = new ExportEvent();
        event.id = id;
        event.status = status;
        event.message = message;
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        Path recordingFile = Files.createTempFile("jfr-csv-source-", ".jfr");
        Path csv = Files.createTempFile("jfr-csv-export-", ".csv");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(ExportEvent.class)
                        .withoutThreshold().withoutStackTrace();
                recording.enable(IgnoredEvent.class)
                        .withoutThreshold().withoutStackTrace();
                recording.start();
                commit(1, "OK", "plain");
                commit(2, "WARN", "hello,\"friend\"");
                commit(3, "OK", "multi\nline");
                commit(4, "WARN", "=2+2");
                IgnoredEvent extra = new IgnoredEvent();
                extra.note = "skip";
                extra.commit();
                recording.stop();
                recording.dump(recordingFile);
            }

            long scanned = 0L, written = 0L;
            try (RecordingFile input = new RecordingFile(recordingFile);
                 BufferedWriter out = Files.newBufferedWriter(
                         csv, StandardCharsets.UTF_8)) {
                out.write("id,status,message");
                out.newLine();
                while (input.hasMoreEvents()) {
                    RecordedEvent event = input.readEvent();
                    scanned++;
                    if (!"training.jfr.ExportEvent".equals(
                            event.getEventType().getName())) {
                        continue;
                    }
                    out.write(Integer.toString(event.getInt("id")));
                    out.write(',');
                    out.write(csvCell(event.getString("status")));
                    out.write(',');
                    out.write(csvCell(event.getString("message")));
                    out.newLine();
                    written++;
                }
            }

            System.out.println("scanned-events=" + scanned);
            System.out.println("exported-rows=" + written);
            System.out.println("csv-file-nonempty=" + (Files.size(csv) > 0L));
            System.out.println("csv-comma-and-quote="
                    + "\"hello,\"\"friend\"\"\"".equals(
                            csvCell("hello,\"friend\"")));
            System.out.println("csv-newline-quoted="
                    + "\"multi\nline\"".equals(csvCell("multi\nline")));
            System.out.println("csv-formula-neutralized="
                    + "'=2+2".equals(csvCell("=2+2")));
            if (scanned != 5 || written != 4
                    || Files.size(csv) == 0L) {
                throw new AssertionError("Streaming CSV export mismatch");
            }
        } finally {
            Files.deleteIfExists(csv);
            Files.deleteIfExists(recordingFile);
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrCsvStreamingDemo.java
java --add-modules jdk.jfr JfrCsvStreamingDemo
```

**Stdout đã kiểm chứng:**

```text
scanned-events=5
exported-rows=4
csv-file-nonempty=true
csv-comma-and-quote=true
csv-newline-quoted=true
csv-formula-neutralized=true
```

CSV là định dạng records có quoting: một field chứa newline có thể chiếm nhiều **dòng vật lý** trong file. Vì vậy đừng đếm `BufferedReader.readLine()` như một CSV parser chính xác. Một field bắt đầu `=`/`+`/`-`/`@` có thể bị bảng tính diễn giải như công thức; demo thêm apostrophe khi phát hiện, nhưng cách bảo vệ tối ưu tùy consumer. Trường chứa dữ liệu do người dùng nhập còn phải được **redact/allowlist** nếu có PII hoặc secret.

**Đảm bảo file xuất không bị công bố khi partial:** trong production, ghi vào tệp tạm, close thành công rồi mới rename/publish; với filesystem hỗ trợ có thể dùng `Files.move` và `ATOMIC_MOVE`, nhưng cần xử lý trường hợp không hỗ trợ atomic move. Khi writer lỗi ở event thứ 100.000, không báo đó là file CSV đầy đủ.

## 7. Demo 3 — Top-K request có score cao nhất chỉ giữ K phần tử

Nếu muốn tìm 3 request có `latencyMicros` lớn nhất trong 10.000 events, đừng gọi `readAllEvents` rồi sort 10.000 object. **Min-heap giới hạn K** dùng `PriorityQueue`:

- Nếu chưa đủ K: thêm ứng viên.
- Nếu đã đủ K: so với `peek()` (nhỏ nhất trong Top-K), chỉ thay khi mới hơn/tốt hơn.
- Khi kết thúc, copy đúng K ứng viên sang list nhỏ để sort giảm dần rồi hiển thị.

Chi phí thuật toán: `O(N log K)` thời gian và `O(K)` memory cho ứng viên, chưa kể reader internals. Demo không giữ `RecordedEvent` trong heap mà chỉ giữ DTO nhỏ gồm `requestId` và `latencyMicros`. Field `latencyMicros` được sinh bằng `(i*37L)%1000` để output xác định, **không phải duration thực đo** của JFR; khi xử lý sự kiện duration thật, dùng `event.getDuration()` sau khi kiểm tra loại event.

Lưu thành **`JfrTopKDemo.java`**:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class JfrTopKDemo {
    @Name("training.jfr.LatencyEvent")
    static class LatencyEvent extends Event {
        int requestId;
        long latencyMicros;
    }

    static final class Candidate {
        final int requestId;
        final long latencyMicros;

        Candidate(int requestId, long latencyMicros) {
            this.requestId = requestId;
            this.latencyMicros = latencyMicros;
        }

        @Override
        public String toString() {
            return requestId + ":" + latencyMicros;
        }
    }

    public static void main(String[] args) throws Exception {
        final int totalEvents = 10000;
        final int k = 3;
        Path path = Files.createTempFile("jfr-topk-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(LatencyEvent.class)
                        .withoutThreshold().withoutStackTrace();
                recording.start();
                for (int i = 0; i < totalEvents; i++) {
                    LatencyEvent event = new LatencyEvent();
                    event.requestId = i;
                    event.latencyMicros = (i * 37L) % 1000L;
                    event.commit();
                }
                recording.stop();
                recording.dump(path);
            }

            Comparator<Candidate> smallestFirst =
                    Comparator.comparingLong(
                            (Candidate c) -> c.latencyMicros)
                            .thenComparingInt(c -> c.requestId);
            PriorityQueue<Candidate> best =
                    new PriorityQueue<>(k, smallestFirst);
            long count = 0L;
            try (RecordingFile file = new RecordingFile(path)) {
                while (file.hasMoreEvents()) {
                    RecordedEvent event = file.readEvent();
                    if (!"training.jfr.LatencyEvent".equals(
                            event.getEventType().getName())) {
                        continue;
                    }
                    count++;
                    Candidate current = new Candidate(
                            event.getInt("requestId"),
                            event.getLong("latencyMicros"));
                    if (best.size() < k) {
                        best.add(current);
                    } else if (smallestFirst.compare(
                            current, best.peek()) > 0) {
                        best.poll();
                        best.add(current);
                    }
                }
            }

            List<Candidate> sorted = new ArrayList<>(best);
            sorted.sort(smallestFirst.reversed());
            StringBuilder output = new StringBuilder();
            for (Candidate c : sorted) {
                if (output.length() != 0) output.append(',');
                output.append(c);
            }
            System.out.println("scanned-events=" + count);
            System.out.println("retained-candidates=" + best.size());
            System.out.println("top3=" + output);

            if (count != totalEvents || best.size() != k
                    || !"9027:999,8027:999,7027:999"
                            .equals(output.toString())) {
                throw new AssertionError("Top-K mismatch");
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrTopKDemo.java
java --add-modules jdk.jfr JfrTopKDemo
```

**Stdout đã kiểm chứng:**

```text
scanned-events=10000
retained-candidates=3
top3=9027:999,8027:999,7027:999
```

Cùng điểm 999 xuất hiện ở nhiều IDs. Comparator so score rồi theo ID để chọn **ba ID cao nhất** (9027, 8027, 7027) với điểm 999, không phụ thuộc thứ tự đọc khi tie. Nếu yêu cầu “lấy tất cả events đồng hạng tại vị trí K”, số kết quả có thể vượt K và phải có một chính sách khác; ví dụ chọn chính xác K bằng tie-break là rõ nhất.

**Nếu K không giới hạn**, Top-K có thể thành O(N). Validate `K>0` và quota hợp lý trước khi tạo heap trong ứng dụng thật. Để tính percentile chính xác trên toàn bộ dữ liệu bất kỳ, counters/Top-K không đủ: sử dụng histogram có độ phân giải hữu hạn, quantile sketch với sai số được xác định, external sort hoặc một engine analytics phù hợp.

## 8. Demo 4 — lỗi EOF, file thiếu và file hỏng

`RecordingFile.readEvent()` sẽ ném `EOFException` nếu gọi khi hết sự kiện. `hasMoreEvents()` là guard đúng cho thao tác đọc tuần tự, còn constructor và read có thể ném `IOException` khi file không phải JFR hợp lệ hoặc không đọc được.

Demo tạo một recording với đúng một custom event, kiểm chứng reader đọc đủ, sau đó cố tình gọi quá EOF. Nó cũng thử mở file văn bản không phải JFR và path thiếu để chứng minh không được coi lỗi như recording rỗng hợp lệ.

Lưu thành **`JfrReadFailuresDemo.java`**:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class JfrReadFailuresDemo {
    @Name("training.jfr.SingleEvent")
    static class SingleEvent extends Event {
        int value;
    }

    public static void main(String[] args) throws Exception {
        Path valid = Files.createTempFile("jfr-readable-", ".jfr");
        Path invalid = Files.createTempFile("jfr-invalid-", ".jfr");
        Path missing = invalid.resolveSibling("jfr-no-such-file-302.jfr");
        try {
            Files.deleteIfExists(missing);
            Files.write(invalid, "not a JFR file".getBytes(
                    StandardCharsets.UTF_8));
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(SingleEvent.class)
                        .withoutThreshold().withoutStackTrace();
                recording.start();
                SingleEvent event = new SingleEvent();
                event.value = 42;
                event.commit();
                recording.stop();
                recording.dump(valid);
            }

            long count = 0;
            boolean eofRejected = false;
            try (RecordingFile input = new RecordingFile(valid)) {
                while (input.hasMoreEvents()) {
                    if ("training.jfr.SingleEvent".equals(
                            input.readEvent().getEventType().getName())) {
                        count++;
                    }
                }
                try {
                    input.readEvent();
                } catch (EOFException expected) {
                    eofRejected = true;
                }
            }
            System.out.println("single-event-count=" + count);
            System.out.println("eof-is-checked=" + eofRejected);

            boolean invalidRejected = false;
            try (RecordingFile ignored = new RecordingFile(invalid)) {
                throw new AssertionError("Unexpected success");
            } catch (IOException expected) {
                invalidRejected = true;
            }
            System.out.println("invalid-jfr-rejected=" + invalidRejected);

            boolean missingRejected = false;
            try (RecordingFile ignored = new RecordingFile(missing)) {
                throw new AssertionError("Missing file unexpectedly opened");
            } catch (IOException expected) {
                missingRejected = true;
            }
            System.out.println("missing-file-rejected=" + missingRejected);

            if (count != 1 || !eofRejected || !invalidRejected
                    || !missingRejected) {
                throw new AssertionError("Read failure tests mismatch");
            }
        } finally {
            Files.deleteIfExists(valid);
            Files.deleteIfExists(invalid);
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.jfr -encoding UTF-8 JfrReadFailuresDemo.java
java --add-modules jdk.jfr JfrReadFailuresDemo
```

**Stdout đã kiểm chứng:**

```text
single-event-count=1
eof-is-checked=true
invalid-jfr-rejected=true
missing-file-rejected=true
```

**Lưu ý portability:** Java 11 Javadoc có thể ghi cụ thể `NoSuchFileException` cho một trường hợp thiếu file. Trên một runtime thử nghiệm, cùng trường hợp trả `FileNotFoundException` (cũng là `IOException`). Vì thế ở biên xử lý file hãy catch `IOException` khi cần một nhánh failure chung, đừng viết code chỉ phụ thuộc đúng một subclass nếu phải hỗ trợ nhiều JDK/provider/filesystem. Nếu cần trả thông báo chính xác, map từng lỗi theo runtime mục tiêu và không tiết lộ path nhạy cảm.

Không catch `IOException` rồi trả count 0. “File không hợp lệ” khác với “file hợp lệ có 0 events”; lỗi giữa chừng phải đánh dấu `FAILED`/`PARTIAL`, cleanup output tạm và có policy retry/idempotency.

## 9. Cần nhớ về schema, filter và time range

### 9.1 Lọc trước, đọc field sau

Một file có thể chứa `jdk.CPULoad`, `jdk.ExecutionSample`, `jdk.GarbageCollection`, `jdk.JavaMonitorEnter` và nhiều custom types. Không gọi `event.getInt("id")` trên mọi type.

```java
if (!"training.jfr.PayloadEvent".equals(
        event.getEventType().getName())) {
    continue;
}
if (!event.hasField("payloadBytes")) {
    throw new IllegalArgumentException("Expected field is absent");
}
long bytes = event.getInt("payloadBytes");
```

Đây là **trích đoạn** bên trong vòng lặp với `event` đã được khai báo, không phải chương trình độc lập. Với input qua nhiều phiên bản JDK hoặc custom event schemas khác nhau, kiểm tra field name và type rồi chọn policy skip, translate hay fail rõ ràng. Không đoán rằng `@Label` là event identifier.

### 9.2 Lọc theo thời gian không tạo random access

`RecordedEvent.getStartTime()` và `getEndTime()` trả `Instant`. Bạn có thể kiểm tra khoảng thời gian:

```java
Instant t = event.getStartTime();
if (t.isBefore(fromInclusive) || !t.isBefore(toExclusive)) {
    continue;
}
```

Đây là **trích đoạn**, biến `event`, `fromInclusive`, `toExclusive` phải có trong method và import `Instant`. Bộ lọc giảm số events xuất/giữ, nhưng `RecordingFile` vẫn phải đọc tuần tự cho đến khi tìm thấy sự kiện cần thiết. Không có API index/seek theo timestamp trên `RecordingFile` Java 11; đừng giả định timeline tuyệt đối được sắp xếp theo yêu cầu truy vấn của mọi consumer.

### 9.3 Stack traces và nested metadata

`RecordedEvent.getStackTrace()` có thể `null` và có thể chứa nhiều frames. Đừng tạo string của tất cả stack traces nếu mục tiêu chỉ count events. `RecordedObject.getValue("thread.group.name")` có khả năng truy cập nested fields nhưng từng field có thể absent/null hoặc thay đổi theo JDK. Với dữ liệu không ổn định, validate metadata, hạn chế dereference và không log object toàn bộ.

## 10. Bộ nhớ thực tế: ở đâu có thể phình?

Ngay cả khi reader dùng `readEvent()` từng lần, memory có thể gồm:

1. JFR internal buffers/chunk metadata và các objects decoder.
2. Event hiện tại, strings, RecordedClass/RecordedThread/RecordedStackTrace.
3. State ứng dụng: counters, histograms, maps, heap Top-K.
4. Queue, futures, task captures và network writes chưa hoàn thành.
5. Output buffer hoặc `StringBuilder` của serializer.
6. Heap/GC/JIT overhead và native memory trong JVM.

| Anti-pattern | Vấn đề |
|---|---|
| `list.add(event)` cho tất cả events | O(N) retained objects |
| `Map<Id,RecordedEvent>` theo request ID | Có thể O(N) |
| `collect(Collectors.toList())` | Materialize stream |
| `StringBuilder allCsv` | O(total output size) |
| `PriorityQueue` với K lấy từ user không giới hạn | K có thể tương đương N |
| `Map<String,Long>` theo userId/cardinality cao | Map không còn bounded |
| `System.out.println(event)` mọi dòng | Tốn CPU/I/O và có thể lộ dữ liệu |
| `CompletableFuture` mỗi event, giữ tới `allOf` | Retain futures/outputs |
| `BlockingQueue` không có capacity | Buildup khi sink chậm |
| Đọc tất cả CSV xuất ra chỉ để verify | Tạo lại O(output size) ở bước sau |

Một event hoặc string field có thể rất lớn, nên nói `O(1)` của counters **không** nghĩa peak heap của cả tiến trình không phụ thuộc kích thước event/chunk. Cần test file nhiều chunks, file có metadata/stack traces lớn, nhiều event types và input không hoàn chỉnh, đo actual heap/GC/RSS thay vì chỉ dựa vào lý thuyết.

### 10.1 Bounded queue và backpressure

Nếu reader nhanh hơn writer/database, một queue vô hạn sẽ giữ ngày càng nhiều event objects. Dùng `BlockingQueue` hữu hạn hoặc bounded executor, throttle reader khi queue đầy. Chuyển từ `RecordedEvent` sang DTO nhỏ chỉ có các fields cần thiết trước khi đưa qua thread boundary, không giữ toàn object graph không cần.

### 10.2 Gộp nhiều file

Đọc từng file rồi close trước khi sang file mới giúp giữ số active readers nhỏ. Nếu chạy parallel, mỗi reader có bộ đệm riêng: memory tăng theo concurrency và số chunks; đặt giới hạn worker/số file/file size. Với resume, `RecordingFile` không có method seek tùy ý theo event index; thiết kế checkpoint theo file và sink idempotent, hoặc external index nếu thực sự cần.

### 10.3 Time, counters và aggregation

Số event/tổng bytes nên dùng `long`, xét overflow bằng `Math.addExact` nếu có nguy cơ. Histogram hữu hạn có memory giới hạn nếu số bins cố định; Map group-by chỉ memory bounded khi số groups cũng được chặn. Tính percentiles chính xác cho dữ liệu arbitrary không thể tùy ý giả bằng average; cần thuật toán phù hợp, có sai số hoặc external analytics.

### 10.4 Streaming output và commit

`BufferedWriter` giảm số lần ghi nhỏ nhưng không đảm bảo atomic output. Production nên xuất sang temp cùng filesystem, close hoàn tất, validate count/checksum/schema rồi publish bằng `Files.move` nếu cơ chế filesystem/policy cho phép. Khi lỗi, cleanup temp và báo incomplete. Với DB, dùng batch fixed size rồi clear; tránh giữ N rows cho một transaction duy nhất và phải có retry/backpressure/idempotency.

## 11. Security và vận hành

Oracle Java SE 11 RecordingFile Javadoc nêu rõ **chỉ đọc recording files từ nguồn đáng tin**. JFR là binary format có metadata phong phú; source không tin cậy có thể làm parser tốn tài nguyên hoặc lộ dữ liệu qua logging/output. Hãy thiết lập:

- Chỉ nhận JFR từ nguồn cho phép, validate path, ownership, file size và quyền đọc.
- Chạy ingestion trong môi trường cô lập khi xử lý dữ liệu upload, hạn chế CPU/RAM/disk và concurrency.
- Không log toàn bộ `RecordedEvent.toString()`, stack traces hoặc request payload khi không cần.
- Redact/allowlist fields, đặc biệt PII, access tokens, hostnames, paths và business data.
- Giới hạn độ dài fields, số records xuất, output size, số nhóm và thời gian xử lý.
- Bảo vệ file `.jfr` và CSV kết quả bằng ACL/encryption/retention theo policy.
- Nếu CSV mở bằng spreadsheet, phải có kế hoạch ngăn formula injection được test trên consumer đích.
- Báo rõ file malformed, partial export và lỗi disk đầy; không trộn số liệu partial vào báo cáo complete.
- Dùng JDK được cập nhật bản vá và module JFR được hỗ trợ.

**Không coi extension `.jfr` là kiểm tra an toàn định dạng.** Constructor sẽ kiểm tra cấu trúc nhưng không thay thế việc tin cậy nguồn, sandbox hay quota. Các event do ứng dụng tùy biến có thể chứa data nhạy cảm ngay cả khi stack trace bị tắt.

## 12. Các test nên có trong CI và môi trường tích hợp

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Tạo/đọc 12.000 custom events | Đúng 12.000, không giữ list |
| Tổng hợp status | OK 9000, ERROR 3000 |
| Tổng payloadBytes | 594000 |
| Metadata | readEventTypes thấy type |
| Mixed types | Filter trước khi gọi getters |
| CSV với 5 events | Scan 5, export 4 |
| CSV comma/quotes | Quote đúng |
| CSV newline | Quote đúng field có newline |
| CSV formula | Neutralization theo policy |
| Top-K 10.000 events | Heap size=3, Top-3 chính xác |
| Top-K tie | Có quy tắc tie-break |
| EOF | readEvent sau EOF ném EOFException |
| Missing path | IOException, không báo count 0 |
| Invalid JFR | IOException, không publish output |
| Field absent | hasField và policy skip/fail |
| Large stack metadata | Đo heap, quota, parser limits |
| CSV sink lỗi/disk full | Cleanup partial và report failure |
| Groups cardinality cao | Không tăng memory vô hạn |
| Concurrency | Bounded queue, bounded readers |
| File nhiều chunks | Throughput/GC vẫn trong budget |
| JDK baseline | `javac --release 11 --add-modules jdk.jfr` |

**Kiểm thử “không OOM” với file nhỏ là chưa đủ.** Nên thử các input scale thực sự, đo heap peak, GC pauses, throughput, output bytes và so kết quả tổng hợp với nguồn/fixtures biết trước. Dự đoán thời gian đọc không chỉ dựa vào số byte file: event fields/stack decoding và sink I/O cũng ảnh hưởng.

## 13. Sai lầm phổ biến

| Sai lầm | Hệ quả | Hướng đúng |
|---|---|---|
| `readAllEvents` file rất lớn | Heap O(N), có thể OOM | Vòng lặp readEvent |
| Lọc sau khi load list | Peak heap không giảm | Filter ngay khi read |
| Group-by mọi requestId không giới hạn | Map O(N) | Quota/cardinality policy |
| Sort toàn bộ events để tìm 10 event lớn nhất | O(N) RAM | Min-heap K=10 |
| Ghi mọi event vào StringBuilder | Giữ toàn output | BufferedWriter từng dòng |
| Không escape CSV | Record hỏng/injection risk | CSV quoting + consumer policy |
| Xử lý `readEvent` sau EOF như null | Sai contract | hasMoreEvents + EOFException |
| Catch IOException rồi báo rỗng | Số liệu không chính xác | FAILED/PARTIAL |
| Giữ `RecordedEvent` trong async queue vô hạn | OOM khi worker chậm | DTO + bounded queue |
| Gọi getters cho field không tồn tại | IllegalArgumentException | Lọc type, hasField |
| Giữ stack traces toàn bộ | Retained object graph lớn | Chỉ phân tích fields cần thiết |
| Coi streaming là JVM O(1) tuyệt đối | Quên parser buffers/metadata | Đo heap thực tế |
| Trộn labels với type names | Filter sai | getEventType().getName() |
| Đọc file từ nguồn không tin cậy | Parser và dữ liệu nhạy cảm | Trusted source/sandbox/quota |
| Bỏ qua output atomicity | File partial bị hiểu complete | Temp + publish after close |
| Dùng API `EventStream` trong Java11 | Compile lỗi | RecordingFile |
| Giả định filter time giúp seek trực tiếp | Vẫn cần scan | External index hoặc process file |
| Bật nhiều file readers không quota | RAM/IO tăng theo concurrency | Bounded parallelism |

## 14. Bài tập có đáp án

**1.** Đọc file JFR 3GB bằng `RecordingFile.readAllEvents` rồi chỉ giữ 1% events. Đó đã là streaming đúng nghĩa chưa?  
**Đáp án:** chưa. Hàm materialize 100% trước filter; đổi sang `hasMoreEvents/readEvent` và lọc trong vòng lặp.

**2.** Muốn đếm 50 triệu events của một type mà không giữ danh sách, giữ gì trong memory?  
**Đáp án:** một `long` counter và một `RecordingFile` đang đọc, cộng buffers/metadata cần thiết của JFR decoder.

**3.** Top-5 chậm nhất trong 10 triệu events cần thuật toán gì?  
**Đáp án:** PriorityQueue min-heap kích thước 5, `O(N log 5)` thời gian cho events thích hợp và `O(5)` state thuật toán.

**4.** Vì sao đọc `event.getString("status")` trước khi lọc event type dễ ném lỗi?  
**Đáp án:** mỗi EventType có schema riêng, event hệ thống không nhất thiết có field đó.

**5.** CSV field `hello,"friend"` và newline thì xử lý thế nào?  
**Đáp án:** đặt field trong dấu nháy kép, thay mỗi dấu nháy kép bằng hai dấu nháy kép, giữ newline trong quoted field; parser CSV hiểu đúng record.

**6.** CSV chứa `=SUM(A1:A10)` do người dùng nhập có thể gây vấn đề gì?  
**Đáp án:** spreadsheet có thể thực thi như công thức khi mở. Phải neutralize theo consumer đích; demo dùng apostrophe prefix như một lớp phòng vệ.

**7.** Một producer đẩy RecordedEvent vào queue vô hạn; consumer ghi DB chậm. Có bounded memory không?  
**Đáp án:** không. Dùng bounded queue, block/throttle và DTO nhỏ.

**8.** Parser ném IOException sau khi xuất 90% rows. Có được đưa file CSV này thành báo cáo hoàn tất không?  
**Đáp án:** không. Phải report partial/failed, cleanup hoặc resume/retry theo cơ chế rõ.

**9.** `readEventTypes()` có phải API đọc mọi RecordedEvent không?  
**Đáp án:** không; đây là danh sách metadata EventType, không phải danh sách events.

**10.** Có thể tin rằng streaming reader luôn chỉ tiêu thụ dưới 1MB RAM không?  
**Đáp án:** không. Parser buffers, chunk metadata, kích thước một event, string fields và JVM GC vẫn cần bộ nhớ; phải benchmark.

**11.** `EventStream.openFile` có sẵn trên Java 11 không?  
**Đáp án:** không. `EventStream` được bổ sung từ Java14; Java11 dùng `RecordingFile`.

**12.** Vì sao status “file thiếu” không giống “file hợp lệ nhưng zero events”?  
**Đáp án:** file thiếu/hỏng là lỗi input, trả zero như success sẽ tạo số liệu giả và có thể che giấu thiếu telemetry.

**13.** Khi muốn p99 chính xác, chỉ giữ tổng và count đã đủ chưa?  
**Đáp án:** chưa. Cần histogram/sketch hoặc external sorting/analytics theo yêu cầu chính xác/sai số và memory budget.

**14.** Nếu event fields chứa access token, việc chỉ chọn streaming có tự bảo vệ không?  
**Đáp án:** không. Phải redact/allowlist, bảo vệ storage, audit quyền truy cập và hạn chế log/output.

## 15. Tài liệu chính thức

- [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): `readEvent`, `hasMoreEvents`, `readEventTypes`, `close`, cảnh báo `readAllEvents` không cho file lớn và nguồn file đáng tin.
- [Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): type, start/end, duration, stack/thread.
- [Java SE 11 — RecordedObject](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `hasField` và typed getters.
- [Java SE 11 — EventType](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html): name, fields, metadata.
- [Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): enable events, start/stop/dump.
- [Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): custom JFR events.
- [Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): withoutThreshold/withoutStackTrace.
- [Java SE 11 — jdk.jfr.consumer package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html): API đọc file recording.
- [Java SE 14 — EventStream](https://docs.oracle.com/en/java/javase/14/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): API đời sau, không nằm trong baseline Java11.
- [OpenJDK — Flight Recorder](https://openjdk.org/jeps/328): bối cảnh tính năng JFR trong OpenJDK.

**Kết luận:** Với file `.jfr` lớn, trên Java 11 hãy dùng `RecordingFile` + `while(hasMoreEvents())` + `readEvent()` và xử lý từng event ngay. Giữ counters, histogram hữu hạn, heap Top-K hay buffered writer thay vì `List<RecordedEvent>` toàn file. Đây là cách hạn chế bộ nhớ **do ứng dụng tích lũy**; vận hành thực còn phải kiểm soát parser/chunk memory, nguồn file đáng tin, quyền dữ liệu, backpressure, quota và output partial.