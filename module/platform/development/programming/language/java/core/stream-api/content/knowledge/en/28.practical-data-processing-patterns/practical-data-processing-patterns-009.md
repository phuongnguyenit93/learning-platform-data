# Phân tích tệp log theo dòng với chính sách xử lý lỗi rõ ràng

## 1. Bài toán: báo cáo log không được âm thầm mất dữ liệu

Trong **JAVA_STREAM_API**, những pipeline `filter`, `map`, `reduce` và `collect` rất phù hợp để biến các dòng log thành thống kê. Tuy nhiên, tệp log không giống một `List` sạch trong bộ nhớ: dòng có thể sai định dạng, giá trị đo có thể không hợp lệ, tệp có thể bị xóa khi đang đọc và lỗi I/O có thể xuất hiện sau khi stream đã mở thành công.

Giả sử một ứng dụng ghi log theo định dạng:

```text
2026-11-18T08:00:00Z|INFO|api|40
2026-11-18T08:00:01Z|ERROR|api|120

2026-11-18T08:00:02Z|WARN|worker|75
invalid line
2026-11-18T08:00:03Z|ERROR|api|80
2026-11-18T08:00:04Z|INFO|worker|-1
```

Mỗi dòng hợp lệ gồm: `timestamp|level|service|durationMs`. Dòng thứ ba rỗng, dòng thứ năm không đủ trường, dòng thứ bảy có thời lượng âm.

Một lời giải kiểu:

```java
// Không đủ tin cậy nếu yêu cầu phải biết nguồn có dòng lỗi:
long errors = Files.lines(path)
    .map(LogParser::parseOrNull)
    .filter(Objects::nonNull)
    .filter(event -> event.level() == Level.ERROR)
    .count();
```

có thể báo `2` sự kiện ERROR, nhưng không cho biết **đã bỏ qua bao nhiêu dòng**, **ở dòng nào** và **vì sao**. Đoạn này còn không đóng stream `Files.lines`. Nếu parser tự bắt mọi exception rồi trả `null`, hệ thống rất dễ tạo ra báo cáo “thành công” từ dữ liệu thiếu.

Trong chương **Mẫu xử lý dữ liệu thực tế**, bài học này xây dựng một pipeline đọc log theo dòng có **hợp đồng xử lý lỗi tường minh**, đảm bảo:

1. Đọc log theo luồng, không phải đưa toàn bộ tệp vào bộ nhớ.
2. Giữ số thứ tự dòng để định vị lỗi.
3. Phân biệt **dòng hợp lệ**, **dòng trắng** và **dòng sai định dạng**.
4. Cung cấp ba chính sách: **FAIL_FAST**, **SKIP_WITH_COUNT**, **COLLECT_ERRORS**.
5. Phân biệt lỗi nội dung log với **lỗi mở/đọc/đóng tệp**.
6. Tổng hợp số sự kiện, thời lượng nhỏ nhất/lớn nhất và thời gian trung bình theo `service` và `level` trong **một lượt duyệt**.
7. Kiểm thử nguồn rỗng, lỗi đầu vào, giới hạn mẫu lỗi, số học và tài nguyên.

Các ví dụ đầy đủ dùng **Java 17+** (vì sử dụng `record` và `sealed interface`). Trọng tâm là Stream API và chính sách dữ liệu; đây chưa phải bộ phân tích mọi định dạng log sản xuất.

## 2. Xác định hợp đồng dữ liệu trước khi viết pipeline

### 2.1. Định dạng một dòng hợp lệ

| Trường | Ví dụ | Quy tắc |
| --- | --- | --- |
| `timestamp` | `2026-11-18T08:00:00Z` | Chuỗi thời gian có thể đọc bằng `Instant.parse` |
| `level` | `INFO`, `WARN`, `ERROR` | Chỉ chấp nhận đúng enum đã công bố |
| `service` | `api`, `worker-1` | Chuỗi định danh theo `[a-z][a-z0-9-]{0,31}` |
| `durationMs` | `40`, `120` | Số nguyên `long` không âm |

Trong bài, dấu `|` phân cách các trường. Dùng `String.split("\\|", -1)`: ký tự `|` là metacharacter của regex nên phải escape, còn tham số `-1` giữ nguyên **các trường rỗng ở cuối** để phát hiện thiếu dữ liệu.

Ví dụ:

```text
2026-11-18T08:00:00Z|INFO|api|40  -> hợp lệ
2026-11-18T08:00:00Z|DEBUG|api|40 -> level không hợp lệ
2026-11-18T08:00:00Z|INFO|api|   -> duration không hợp lệ
2026-11-18T08:00:00Z|INFO|api|-1 -> duration âm
2026-11-18T08:00:00Z|INFO|api    -> thiếu một trường
```

Không tự đoán rằng `DEBUG` tương đương `INFO` hay `durationMs` rỗng tương đương `0`. Những giá trị như vậy phải có **quy ước nghiệp vụ riêng** nếu muốn chấp nhận.

### 2.2. Ba loại dòng khác nhau

| Loại | Ý nghĩa | Góp phần vào báo cáo? |
| --- | --- | --- |
| **Valid** | Parse thành sự kiện có trường hợp lệ | Có: tăng số sự kiện và cập nhật thống kê |
| **Blank** | Dòng trắng hoặc chỉ gồm khoảng trắng | Không tính là sự kiện; tăng `blankLines` |
| **Invalid** | Có nội dung nhưng sai schema hoặc giá trị | Không tính là sự kiện; tăng `invalidLines` và xử lý theo policy |

Hợp đồng của bài **không xem dòng trắng là lỗi**. Một hệ thống khác có thể chọn ngược lại, nhưng phải định nghĩa rõ và kiểm thử.

Với mỗi tệp được xử lý hết mà không lỗi I/O:

\[
\text{totalLines}=\text{validLines}+\text{blankLines}+\text{invalidLines}
\]

Đây là **bất biến kiểm thử** quan trọng. Không dùng `filter` để xóa dòng lỗi quá sớm khiến hệ thống không còn biết có bao nhiêu dòng đã bị loại.

## 3. Định nghĩa rõ ba chính sách xử lý dòng sai

### 3.1. `FAIL_FAST` — dừng tại dòng đầu tiên không hợp lệ

Khi parser gặp một dòng có nội dung nhưng sai, ném một ngoại lệ gắn **số dòng và mã lý do**. Không trả báo cáo từng phần như thể công việc đã thành công.

Phù hợp với:

- Pipeline phải nhận dữ liệu **đầy đủ và sạch** trước khi tính tiền, tính phí hay xuất bản.
- Bài kiểm tra chất lượng dữ liệu trước bước xử lý chính.
- Hệ thống mà một dòng sai có thể làm sai ý nghĩa thống kê.

Nhược điểm: không liệt kê được tất cả dòng lỗi trong cùng một lần chạy. Có thể chạy một chế độ kiểm tra lỗi trước nếu cần tổng hợp nhiều vấn đề.

### 3.2. `SKIP_WITH_COUNT` — bỏ dòng sai nhưng luôn đếm

Không ném lỗi đối với **dòng sai định dạng**, nhưng tăng `invalidLines` và chỉ tổng hợp các sự kiện hợp lệ. Không lưu chi tiết lỗi.

Phù hợp với nguồn mà đặc tả cho phép **best effort**, và tỷ lệ lỗi vẫn được giám sát.

Không nên gọi báo cáo là “đầy đủ” khi `invalidLines > 0`. Các bộ phận khác có thể đặt ngưỡng chất lượng dữ liệu, ví dụ nếu tỷ lệ lỗi vượt mức cấu hình thì không xuất bản.

### 3.3. `COLLECT_ERRORS` — tiếp tục và lưu một số lỗi mẫu

Giống `SKIP_WITH_COUNT` về kết quả thống kê và số dòng sai, nhưng còn lưu tối đa `sampleLimit` mục lỗi, mỗi mục gồm **số dòng và mã lỗi**, không lưu nguyên văn nội dung có thể chứa bí mật.

Phù hợp với:

- Báo cáo vận hành cần cả số liệu và chẩn đoán.
- Công cụ nhập log lần đầu cần tìm nhiều lỗi schema.
- Màn hình chất lượng dữ liệu nhưng không muốn lưu toàn bộ dòng sai trong RAM.

**Quan trọng:** giới hạn `sampleLimit` **chỉ giới hạn số lỗi lưu lại**, không giới hạn số dòng được xử lý và không làm giảm `invalidLines`. Nếu file có một triệu dòng lỗi mà giới hạn mẫu là 20, bộ đếm vẫn phải là một triệu.

### 3.4. Ma trận kết quả

| Tình huống | FAIL_FAST | SKIP_WITH_COUNT | COLLECT_ERRORS |
| --- | --- | --- | --- |
| Dòng hợp lệ | Tổng hợp | Tổng hợp | Tổng hợp |
| Dòng trắng | Đếm blank, tiếp tục | Đếm blank, tiếp tục | Đếm blank, tiếp tục |
| Dòng sai schema | Ném ngoại lệ | Tăng invalid, tiếp tục | Tăng invalid, lưu mẫu đến giới hạn |
| Không mở được tệp | Lỗi I/O | **Vẫn lỗi I/O** | **Vẫn lỗi I/O** |
| Đọc tệp thất bại giữa chừng | Lỗi I/O | **Vẫn lỗi I/O** | **Vẫn lỗi I/O** |
| Báo cáo trả ra bình thường | Không có dòng sai | Có thể có dòng sai | Có thể có dòng sai |

**Đừng trộn hai nhóm lỗi:** chính sách bỏ qua **dòng không hợp lệ** không cho phép tự động bỏ qua **tệp không đọc được**. Nếu cần cơ chế tiếp tục khi một tệp lỗi, hãy thiết kế thêm kết quả **theo tệp** có trạng thái thành công/thất bại và kiểm kê tất cả tệp đã bỏ qua.

## 4. Đọc tệp bằng `Files.lines` và quản lý vòng đời stream

`Files.lines(path, charset)` trả một `Stream<String>` đọc dòng **lười**. Điều này tránh nạp cả tệp vào bộ nhớ:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .filter(line -> !line.isBlank())
            .count();
    }
}
```

**Quyền sở hữu tài nguyên:**

- `Files.lines` mở tài nguyên I/O; **caller phải đóng stream**.
- `count()`, `collect()` và `toList()` là terminal operation, **không tự gọi `close()`**.
- `try-with-resources` đóng nguồn cả khi hoàn thành bình thường lẫn khi terminal operation ném ngoại lệ.
- `Files.lines` có thể ném checked `IOException` khi mở; lỗi đọc phát sinh **trong lúc duyệt** có thể được bọc thành `UncheckedIOException`.
- Đọc đúng charset; ví dụ này chọn UTF-8. Mã hóa sai không được “sửa” bằng cách âm thầm bỏ dòng parse lỗi.

### 4.1. Vì sao không đọc tất cả dòng bằng `readAllLines`?

`Files.readAllLines(path)` đưa mọi dòng vào một danh sách. Với tệp rất lớn, dung lượng bộ nhớ có thể tăng theo tổng nội dung tệp. `Files.lines` hoặc `BufferedReader.readLine` cho phép xử lý từng dòng và giữ trạng thái thống kê **gọn hơn nhiều**.

Nếu cần **số dòng vật lý** khi báo lỗi, một stream thuần `Files.lines` không cung cấp chỉ số dòng sẵn có. Thêm một `AtomicLong` mutable vào `map` để tăng số dòng là một giải pháp dễ sai khi pipeline đổi sang song song hoặc được tối ưu. Bài này sẽ cung cấp một **nguồn stream có đánh số dòng tuần tự** để không lệ thuộc side effect của mapper.

### 4.2. `BufferedReader.lines()` và quyền đóng reader

`BufferedReader.lines()` tạo stream đọc các dòng từ reader, nhưng reader **vẫn do người tạo reader sở hữu**:

```java
import java.io.BufferedReader;

try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    long count = reader.lines().count();
}
// Reader được đóng bởi try-with-resources.
```

Không giả định đóng stream `reader.lines()` sẽ tự đóng `BufferedReader`. Trong lời giải đầy đủ, chúng ta sở hữu reader trực tiếp và đóng nó tại ranh giới phương thức phân tích.

## 5. Parser thuần: trả một kết quả có trạng thái

Một parser đáng kiểm thử nên chỉ phụ thuộc vào **nội dung dòng** và **số dòng**, không tự đọc tệp, ghi log hệ thống, tăng bộ đếm toàn cục hay quyết định chiến lược fail-fast.

Thiết kế kiểu:

```java
record NumberedLine(long number, String text) {}
record LogEvent(Instant time, Level level, String service, long durationMs) {}

sealed interface ParseOutcome permits Accepted, Blank, Rejected {}

record Accepted(LogEvent event) implements ParseOutcome {}
record Blank(long lineNumber) implements ParseOutcome {}
record Rejected(Issue issue) implements ParseOutcome {}

record Issue(long lineNumber, String code) {}
```

**Vì sao không dùng `Optional<LogEvent>` cho mọi trường hợp?**

`Optional.empty()` không cho biết đó là dòng trắng hay dòng sai định dạng. Nếu nghiệp vụ cần phân biệt, một kiểu kết quả có trạng thái tường minh rõ ràng hơn. Chỉ khi đã cố ý coi cả hai là “không có sự kiện” thì `Optional` mới đủ.

Ví dụ parser tách:

```java
String[] fields = line.split("\\|", -1);
if (fields.length != 4) {
    return new Rejected(new Issue(lineNumber, "FIELD_COUNT"));
}
```

Sau đó lần lượt validate timestamp, level, service và duration. Hãy bắt **những ngoại lệ dữ liệu dự kiến** như `DateTimeParseException` và `NumberFormatException`. Tránh `catch (Exception e) { return Optional.empty(); }`, vì cách đó có thể giấu cả lỗi lập trình hay lỗi hạ tầng.

### 5.1. Mã lỗi có cấu trúc tốt hơn giữ toàn bộ dòng thô

Ví dụ `Issue(7, "NEGATIVE_DURATION")` đủ để người vận hành biết loại lỗi và quay lại dòng 7 trong tệp nguồn. Khi log có thể chứa token, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm, **đừng mặc định đưa toàn bộ dòng lỗi vào báo cáo, console hoặc dashboard**. Nếu cần lưu đoạn xem trước, nên giới hạn độ dài, loại bỏ ký tự điều khiển và ẩn dữ liệu nhạy cảm theo chính sách bảo mật.

### 5.2. Số dòng có nghĩa gì?

Trong bài, `lineNumber` bắt đầu từ **1** và tăng mỗi khi `BufferedReader.readLine()` trả về một dòng, kể cả dòng trắng. Nó là số dòng **trong tệp được đọc ở lần chạy đó**, không phải số byte, thời điểm log hay số sự kiện hợp lệ. Nếu một dòng log chứa nhiều dòng vật lý (ví dụ stack trace multiline), mô hình schema đơn dòng cần được thay bằng parser trạng thái có hợp đồng riêng.

## 6. Nguồn `Stream<NumberedLine>` không dùng bộ đếm trong mapper

Để ghép **số dòng** với **nội dung** khi file chưa biết trước có bao nhiêu dòng, ta có thể xây một `Iterator<NumberedLine>` tuần tự trên `BufferedReader`, rồi dùng:

```java
StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(
        iterator, Spliterator.ORDERED | Spliterator.NONNULL
    ),
    false
);
```

Ý tưởng:

```text
BufferedReader.readLine()
      │
      ├─ lần 1 -> NumberedLine(1, "2026-...|INFO|api|40")
      ├─ lần 2 -> NumberedLine(2, "2026-...|ERROR|api|120")
      ├─ lần 3 -> NumberedLine(3, "")
      └─ EOF   -> không còn phần tử
                      │
                      ▼
           Stream<NumberedLine> tuần tự
                      │
                  map(parse)
                      │
           collect(reportCollector)
```

Đặc tính `ORDERED` phù hợp với thứ tự vật lý của các dòng. `NONNULL` hợp lệ vì mỗi phần tử phát ra là một đối tượng `NumberedLine` khác null. **Không** tự khai `SIZED` hoặc `SUBSIZED`, vì số dòng chưa được xác định trước.

### 6.1. Vì sao cần quản lý lookahead cho `Iterator`?

`Iterator.hasNext()` có thể được gọi nhiều lần trước `next()`. Implementation phải **đọc sẵn nhiều nhất một dòng** rồi giữ lại, tránh việc mỗi lần `hasNext` vô tình bỏ qua một dòng. Khi `next()` được gọi, nó trả dòng đã đọc sẵn và chuyển sang trạng thái cho phép đọc tiếp.

Nếu `readLine()` ném `IOException`, iterator có thể bọc bằng `UncheckedIOException` vì `Iterator.hasNext/next` không khai checked exception. Ngoại lệ này **được truyền ra ngoài**, không biến thành dòng sai schema.

### 6.2. Không biến `Iterator` này thành nguồn song song tùy tiện

`BufferedReader` có trạng thái đọc tuần tự; mỗi `Iterator` sở hữu một con trỏ dòng. Bài chọn `StreamSupport.stream(..., false)` để đảm bảo số dòng và thứ tự rõ ràng. `parallel()` ở phần sau không làm cho nguồn I/O có thể bị nhiều worker gọi `readLine` độc lập theo số dòng; muốn chia file phải thiết kế nguồn và ranh giới dòng an toàn hơn.

## 7. Bộ tích lũy báo cáo: đếm lỗi và tổng hợp sự kiện trong một lượt

Một giải pháp thiếu hiệu quả là gọi:

```java
// Không thể dùng lại một Stream<String> đã tiêu thụ:
long total = lines.count();
long errors = lines.filter(LogParser::isError).count();
```

Với stream I/O, không thể chạy hai terminal operations trên **cùng một stream đã tiêu thụ**. Đọc lại tệp để đếm riêng từng loại vừa tốn I/O vừa có nguy cơ dữ liệu thay đổi giữa hai lần đọc.

Thay vào đó, một `Collector` tùy chỉnh nhận từng `ParseOutcome` và cập nhật trạng thái nhỏ:

```text
                    ParseOutcome
                          │
           ┌──────────────┼────────────────┐
           ▼              ▼                ▼
       Accepted          Blank           Rejected
           │              │                │
       validLines++    blankLines++    invalidLines++
           │                               │
   service + level map            policy FAIL/SKIP/COLLECT
           │
      GroupStats
   count/sum/min/max
           │
           ▼
       Report cuối
```

Bộ tích lũy giữ:

- `totalLines`, `validLines`, `blankLines`, `invalidLines`;
- map `service → level → GroupStats`;
- tối đa `sampleLimit` ví dụ `Issue`;
- tham số policy và giới hạn mẫu.

Với báo cáo số liệu, dùng `Math.addExact` cho bộ đếm và tổng thời lượng giúp **ném `ArithmeticException` nếu tràn `long`**, thay vì âm thầm nhận một tổng sai. Trung bình kiểu `double` vẫn là số xấp xỉ, phù hợp báo cáo thời lượng thông thường; tiền tệ và số liệu yêu cầu độ chính xác tuyệt đối cần quy tắc số học khác.

### 7.1. Vì sao collector có `combiner` dù nguồn đang tuần tự?

Giao diện `Collector<T,A,R>` gồm supplier, accumulator, combiner và finisher. Kể cả khi nguồn hiện tại chạy tuần tự, việc xây combiner **có tính kết hợp** là một phần thiết kế collector đúng hợp đồng. Ở bài này:

- Các bộ đếm được cộng bằng `Math.addExact`.
- Các thống kê cùng khóa được gộp bằng count/sum/min/max.
- Các mẫu lỗi được nối từ trái sang phải và **cắt tới sampleLimit**.
- Không gắn `CONCURRENT` cho map/bộ tích lũy mutable.

Điều này **không** làm cho nguồn `BufferedReader` tự nhiên trở thành parallel-safe. Nguồn I/O và collector là hai tầng trách nhiệm riêng.

## 8. Chương trình Java 17 hoàn chỉnh: `LogLineAnalyzer`

Tệp sau là chương trình độc lập có thể lưu thành `LogLineAnalyzer.java`. Nó dùng nguồn tuần tự có đánh số dòng, parser thuần và một collector tổng hợp có kiểm soát lỗi.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public final class LogLineAnalyzer {

    private LogLineAnalyzer() {}

    public enum Level { INFO, WARN, ERROR }

    public enum InvalidLinePolicy {
        FAIL_FAST,
        SKIP_WITH_COUNT,
        COLLECT_ERRORS
    }

    public record Issue(long lineNumber, String code) {}

    public record Metric(
        long count,
        long totalMs,
        long minMs,
        long maxMs,
        double averageMs
    ) {}

    public record Report(
        long totalLines,
        long validLines,
        long blankLines,
        long invalidLines,
        Map<String, Map<Level, Metric>> groups,
        List<Issue> issueSamples
    ) {}

    public static final class InvalidLogLineException
            extends RuntimeException {
        public InvalidLogLineException(Issue issue) {
            super("Dòng " + issue.lineNumber() +
                  " không hợp lệ: " + issue.code());
        }
    }

    private record NumberedLine(long number, String text) {}

    private record LogEvent(
        Instant time, Level level, String service, long durationMs
    ) {}

    private sealed interface ParseOutcome
            permits Accepted, Blank, Rejected {}

    private record Accepted(LogEvent event) implements ParseOutcome {}
    private record Blank(long lineNumber) implements ParseOutcome {}
    private record Rejected(Issue issue) implements ParseOutcome {}

    // Parser thuần: không truy cập I/O, không sửa trạng thái bên ngoài.
    private static ParseOutcome parse(NumberedLine line) {
        String raw = line.text();
        if (raw.isBlank()) {
            return new Blank(line.number());
        }

        String[] fields = raw.split("\\|", -1);
        if (fields.length != 4) {
            return new Rejected(
                new Issue(line.number(), "FIELD_COUNT")
            );
        }

        Instant time;
        try {
            time = Instant.parse(fields[0]);
        } catch (DateTimeParseException ex) {
            return new Rejected(
                new Issue(line.number(), "INVALID_TIMESTAMP")
            );
        }

        Level level;
        try {
            level = Level.valueOf(fields[1]);
        } catch (IllegalArgumentException ex) {
            return new Rejected(
                new Issue(line.number(), "INVALID_LEVEL")
            );
        }

        String service = fields[2];
        if (!service.matches("[a-z][a-z0-9-]{0,31}")) {
            return new Rejected(
                new Issue(line.number(), "INVALID_SERVICE")
            );
        }

        long duration;
        try {
            duration = Long.parseLong(fields[3]);
        } catch (NumberFormatException ex) {
            return new Rejected(
                new Issue(line.number(), "INVALID_DURATION")
            );
        }
        if (duration < 0L) {
            return new Rejected(
                new Issue(line.number(), "NEGATIVE_DURATION")
            );
        }

        return new Accepted(
            new LogEvent(time, level, service, duration)
        );
    }

    // Reader vẫn thuộc sở hữu của analyze(), không thuộc Iterator.
    private static Stream<NumberedLine> numberedLines(
        BufferedReader reader
    ) {
        Iterator<NumberedLine> iterator = new Iterator<>() {
            private long number;
            private NumberedLine nextLine;
            private boolean ready;
            private boolean ended;

            private void load() {
                if (ready || ended) {
                    return;
                }
                try {
                    String text = reader.readLine();
                    if (text == null) {
                        ended = true;
                    } else {
                        number = Math.addExact(number, 1L);
                        nextLine = new NumberedLine(number, text);
                        ready = true;
                    }
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            }

            @Override
            public boolean hasNext() {
                load();
                return ready;
            }

            @Override
            public NumberedLine next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                NumberedLine result = nextLine;
                nextLine = null;
                ready = false;
                return result;
            }
        };

        Spliterator<NumberedLine> source =
            Spliterators.spliteratorUnknownSize(
                iterator,
                Spliterator.ORDERED | Spliterator.NONNULL
            );
        return StreamSupport.stream(source, false);
    }

    // Mutable state nội bộ, không được chia sẻ cho caller.
    private static final class GroupStats {
        long count;
        long sum;
        long min = Long.MAX_VALUE;
        long max = Long.MIN_VALUE;

        void add(long durationMs) {
            count = Math.addExact(count, 1L);
            sum = Math.addExact(sum, durationMs);
            min = Math.min(min, durationMs);
            max = Math.max(max, durationMs);
        }

        void merge(GroupStats other) {
            count = Math.addExact(count, other.count);
            sum = Math.addExact(sum, other.sum);
            if (other.count > 0L) {
                min = Math.min(min, other.min);
                max = Math.max(max, other.max);
            }
        }

        Metric finish() {
            // GroupStats chỉ tồn tại nếu đã có ít nhất một event.
            return new Metric(
                count, sum, min, max, (double) sum / count
            );
        }
    }

    private static final class Accumulator {
        final InvalidLinePolicy policy;
        final int sampleLimit;
        long totalLines;
        long validLines;
        long blankLines;
        long invalidLines;

        final Map<String, EnumMap<Level, GroupStats>> groups =
            new HashMap<>();
        final List<Issue> issueSamples = new ArrayList<>();

        Accumulator(InvalidLinePolicy policy, int sampleLimit) {
            this.policy = policy;
            this.sampleLimit = sampleLimit;
        }

        void accept(ParseOutcome outcome) {
            totalLines = Math.addExact(totalLines, 1L);

            if (outcome instanceof Accepted accepted) {
                validLines = Math.addExact(validLines, 1L);
                LogEvent event = accepted.event();
                groups.computeIfAbsent(
                    event.service(), unused -> new EnumMap<>(Level.class)
                ).computeIfAbsent(
                    event.level(), unused -> new GroupStats()
                ).add(event.durationMs());
            } else if (outcome instanceof Blank) {
                blankLines = Math.addExact(blankLines, 1L);
            } else if (outcome instanceof Rejected rejected) {
                invalidLines = Math.addExact(invalidLines, 1L);
                Issue issue = rejected.issue();

                if (policy == InvalidLinePolicy.FAIL_FAST) {
                    throw new InvalidLogLineException(issue);
                }
                if (policy == InvalidLinePolicy.COLLECT_ERRORS
                        && issueSamples.size() < sampleLimit) {
                    issueSamples.add(issue);
                }
            }
        }

        Accumulator merge(Accumulator other) {
            totalLines = Math.addExact(totalLines, other.totalLines);
            validLines = Math.addExact(validLines, other.validLines);
            blankLines = Math.addExact(blankLines, other.blankLines);
            invalidLines = Math.addExact(invalidLines, other.invalidLines);

            other.groups.forEach((service, levels) -> {
                EnumMap<Level, GroupStats> target =
                    groups.computeIfAbsent(
                        service, unused -> new EnumMap<>(Level.class)
                    );
                levels.forEach((level, stats) -> {
                    target.computeIfAbsent(
                        level, unused -> new GroupStats()
                    ).merge(stats);
                });
            });

            if (policy == InvalidLinePolicy.COLLECT_ERRORS) {
                for (Issue issue : other.issueSamples) {
                    if (issueSamples.size() == sampleLimit) {
                        break;
                    }
                    issueSamples.add(issue);
                }
            }
            return this;
        }

        Report finish() {
            Map<String, Map<Level, Metric>> output = new TreeMap<>();

            groups.forEach((service, levels) -> {
                EnumMap<Level, Metric> finished =
                    new EnumMap<>(Level.class);
                levels.forEach(
                    (level, stats) -> finished.put(level, stats.finish())
                );
                output.put(
                    service, Collections.unmodifiableMap(finished)
                );
            });

            return new Report(
                totalLines,
                validLines,
                blankLines,
                invalidLines,
                Collections.unmodifiableMap(output),
                List.copyOf(issueSamples)
            );
        }
    }

    public static Report analyze(
        Path file, InvalidLinePolicy policy, int sampleLimit
    ) throws IOException {
        Objects.requireNonNull(file, "file");
        Objects.requireNonNull(policy, "policy");
        if (sampleLimit < 0) {
            throw new IllegalArgumentException(
                "sampleLimit phải không âm"
            );
        }

        try (BufferedReader reader =
                 Files.newBufferedReader(
                     file, StandardCharsets.UTF_8
                 )) {
            return numberedLines(reader)
                .map(LogLineAnalyzer::parse)
                .collect(Collector.of(
                    () -> new Accumulator(policy, sampleLimit),
                    Accumulator::accept,
                    Accumulator::merge,
                    Accumulator::finish
                ));
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println(
                "Cách dùng: java LogLineAnalyzer <file.log>"
            );
            return;
        }

        Path file = Path.of(args[0]);
        Report report = analyze(
            file, InvalidLinePolicy.COLLECT_ERRORS, 10
        );

        System.out.println("Tổng dòng: " + report.totalLines());
        System.out.println("Hợp lệ: " + report.validLines());
        System.out.println("Trắng: " + report.blankLines());
        System.out.println("Không hợp lệ: " + report.invalidLines());
        System.out.println("Lỗi mẫu: " + report.issueSamples());
        System.out.println("Nhóm: " + report.groups());
    }
}
```

### 8.1. Chạy thử với dữ liệu mẫu

Lưu đúng bảy dòng đầu bài vào `app.log` rồi chạy:

```bash
javac LogLineAnalyzer.java
java LogLineAnalyzer app.log
```

Các giá trị chính phải là:

```text
Tổng dòng: 7
Hợp lệ: 4
Trắng: 1
Không hợp lệ: 2
Lỗi mẫu: [Issue[lineNumber=5, code=FIELD_COUNT],
          Issue[lineNumber=7, code=NEGATIVE_DURATION]]
```

Bộ thống kê theo nhóm:

| Service | Level | Số event | Tổng thời lượng (ms) | Min (ms) | Max (ms) | TB (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| api | INFO | 1 | 40 | 40 | 40 | 40.0 |
| api | ERROR | 2 | 200 | 80 | 120 | 100.0 |
| worker | WARN | 1 | 75 | 75 | 75 | 75.0 |

Với `HashMap` nội bộ, chương trình **không cam kết thứ tự duyệt ngay trong quá trình tích lũy**. `finish` chuyển khóa service sang `TreeMap` và level sang `EnumMap` nên kết quả khi đọc sau khi hoàn tất có thứ tự rõ ràng; số liệu không phụ thuộc thứ tự duyệt map.

### 8.2. Tại sao code chính không dùng `parallel()`?

Nguồn đọc tệp là iterator tuần tự trên **một `BufferedReader`**. Số dòng là một con trỏ tăng liên tục, và việc gọi `readLine()` phải tuân thứ tự. `StreamSupport.stream(..., false)` cố ý không song song. Dù collector có combiner đúng, việc đổi sang `parallel()` không tự tạo các phần tệp độc lập có số dòng chính xác và không nhất thiết tăng tốc I/O.

Nếu cần xử lý **nhiều tệp độc lập**, có thể phân công **mỗi tệp một tác vụ** và gộp các báo cáo theo hợp đồng tường minh, kiểm soát số file mở đồng thời. Với **một tệp** cực lớn, phân chia byte phải xử lý đúng charset, ranh giới dòng, thứ tự và offset; đó là bài toán nguồn tùy chỉnh cần thiết kế riêng.

### 8.3. Tại sao báo cáo có thể giữ ít bộ nhớ?

`Accumulator` chỉ giữ một bộ thống kê cho mỗi cặp (`service`, `level`) và tối đa `sampleLimit` ví dụ lỗi. Nó **không giữ toàn bộ dòng log**.

Với `g` nhóm khác nhau và `k` mẫu lỗi, trạng thái tăng theo số nhóm và mẫu lỗi, gần `O(g+k)`, chứ không tăng tuyến tính theo **tổng độ dài tất cả các dòng** nếu số nhóm và giới hạn mẫu được khống chế. `BufferedReader` còn có bộ đệm đọc riêng; một dòng cực dài vẫn có thể yêu cầu bộ nhớ lớn, nên cần chiến lược giới hạn kích thước dòng ở hệ thống thực.

## 9. Thử từng chính sách trên cùng một tệp

Giả sử `app.log` có các dòng giống đầu bài.

### 9.1. Chế độ `FAIL_FAST`

```java
try {
    LogLineAnalyzer.Report strict = LogLineAnalyzer.analyze(
        Path.of("app.log"),
        LogLineAnalyzer.InvalidLinePolicy.FAIL_FAST,
        0
    );
    System.out.println(strict);
} catch (LogLineAnalyzer.InvalidLogLineException ex) {
    System.err.println(ex.getMessage());
}
// Dòng 5 không hợp lệ: FIELD_COUNT
```

`analyze` dừng tại dòng sai đầu tiên, **không có `Report` thành công**. `BufferedReader` vẫn được đóng bởi `try-with-resources` trong `analyze`. Một dòng sai sau đó có thể chưa được đọc; đây là ý nghĩa của fail-fast.

### 9.2. Chế độ `SKIP_WITH_COUNT`

```java
LogLineAnalyzer.Report report = LogLineAnalyzer.analyze(
    Path.of("app.log"),
    LogLineAnalyzer.InvalidLinePolicy.SKIP_WITH_COUNT,
    0
);

System.out.println(report.validLines());       // 4
System.out.println(report.invalidLines());     // 2
System.out.println(report.issueSamples());     // []
```

Báo cáo phản ánh **4 sự kiện hợp lệ**, không phản ánh “tất cả 7 dòng đều hợp lệ”. Nếu downstream yêu cầu tối thiểu 99,9% dòng có nội dung parse được, hãy đặt bước quyết định chất lượng dữ liệu **sau khi thu thập** dựa trên count, thay vì bỏ qua tỉ lệ lỗi.

### 9.3. Chế độ `COLLECT_ERRORS` với giới hạn mẫu

```java
LogLineAnalyzer.Report report = LogLineAnalyzer.analyze(
    Path.of("app.log"),
    LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
    1
);

System.out.println(report.invalidLines());     // 2
System.out.println(report.issueSamples().size()); // 1
System.out.println(report.issueSamples().get(0).lineNumber()); // 5
```

Chỉ giữ một lỗi mẫu nhưng vẫn đếm đủ hai lỗi. Không dùng `issueSamples().size()` làm **tổng số dòng lỗi**: trường này là **số mẫu được lưu**, không phải bộ đếm.

### 9.4. Trường hợp tệp rỗng

Tệp có 0 dòng hợp lệ thì:

```text
totalLines   = 0
validLines   = 0
blankLines   = 0
invalidLines = 0
groups       = {}
issueSamples = []
```

Không nên tạo một nhóm `"UNKNOWN"` hoặc kết luận độ trễ trung bình bằng 0 nếu không có sự kiện. `groups` rỗng nghĩa là không có dữ liệu hợp lệ để tạo nhóm.

## 10. Kiểm chứng thống kê và những phép tính thường bị hiểu nhầm

### 10.1. `count` không đo được dữ liệu bị bỏ

Nếu `parseOrNull` trả null và sau đó gọi `filter(Objects::nonNull).count()`, người dùng chỉ biết **số sự kiện sống sót**, không biết bao nhiêu dòng lỗi. Một pipeline thuần có thể tạo `ParseOutcome` cho **mọi dòng** rồi thu thập đủ số đếm.

### 10.2. Trung bình chỉ tính từ sự kiện hợp lệ

`api/ERROR` trong dữ liệu mẫu có hai duration: 120 và 80 ms.

\[
\text{averageMs}=\frac{120+80}{2}=100.0
\]

Không lấy mẫu sai schema hoặc dòng trắng làm thời lượng 0; nếu thêm số 0 giả vào mẫu, trung bình bị kéo xuống và mất ý nghĩa đo.

### 10.3. Không lấy trung bình đơn giản của các trung bình nhóm

Để tính trung bình của tất cả sự kiện, phải dùng:

\[
\overline{d}
=\frac{\sum_{g}\mathrm{totalMs}_{g}}
       {\sum_{g}\mathrm{count}_{g}}
\]

Không dùng trung bình không trọng số của `Metric.averageMs()` từng nhóm nếu số sự kiện mỗi nhóm khác nhau. Có thể lấy tổng `count` và `totalMs` của tất cả nhóm từ `Report.groups()` và thực hiện phép chia có kiểm soát.

### 10.4. Tràn số và số thực

Trong chương trình, `Math.addExact` kiểm tra tràn của `count` và `sum`. Nhưng giá trị trung bình `(double) sum / count` vẫn là xấp xỉ dấu phẩy động; với giá trị `long` cực lớn có thể mất chữ số chính xác. Nếu cần tính tổng thời gian ở quy mô vượt miền `long` hoặc số học tái lập chính xác, cân nhắc `BigInteger`/`BigDecimal` và chính sách làm tròn.

Các giá trị `durationMs` là **không âm** theo schema, nên với tổng cuối nằm trong miền `long`, việc gộp các tổng không âm theo thứ tự khác nhau sẽ không gặp tràn do cộng các phần; phép toán vẫn phải kiểm tra giới hạn tổng cuối.

## 11. Kiểm thử JUnit 5: dữ liệu, chính sách và lỗi I/O

Các kiểm thử dưới đây dùng class `LogLineAnalyzer` ở mục 8. JUnit Jupiter cần được cấu hình trong dự án; file test có thể đặt cùng package.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LogLineAnalyzerTest {

    @TempDir
    Path temporary;

    private Path sampleFile() throws IOException {
        Path file = temporary.resolve("app.log");
        Files.write(file, List.of(
            "2026-11-18T08:00:00Z|INFO|api|40",
            "2026-11-18T08:00:01Z|ERROR|api|120",
            "",
            "2026-11-18T08:00:02Z|WARN|worker|75",
            "invalid line",
            "2026-11-18T08:00:03Z|ERROR|api|80",
            "2026-11-18T08:00:04Z|INFO|worker|-1"
        ), StandardCharsets.UTF_8);
        return file;
    }

    @Test
    void collectsMetricsAndBoundedErrorExamples() throws IOException {
        var report = LogLineAnalyzer.analyze(
            sampleFile(),
            LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
            1
        );

        assertEquals(7L, report.totalLines());
        assertEquals(4L, report.validLines());
        assertEquals(1L, report.blankLines());
        assertEquals(2L, report.invalidLines());
        assertEquals(report.totalLines(),
            report.validLines() + report.blankLines()
                + report.invalidLines());

        assertEquals(1, report.issueSamples().size());
        assertEquals(5L, report.issueSamples().get(0).lineNumber());
        assertEquals("FIELD_COUNT", report.issueSamples().get(0).code());

        var metric = report.groups()
            .get("api").get(LogLineAnalyzer.Level.ERROR);
        assertEquals(2L, metric.count());
        assertEquals(200L, metric.totalMs());
        assertEquals(80L, metric.minMs());
        assertEquals(120L, metric.maxMs());
        assertEquals(100.0, metric.averageMs(), 1e-9);
    }

    @Test
    void skipPolicyKeepsInvalidCountWithoutSamples() throws IOException {
        var report = LogLineAnalyzer.analyze(
            sampleFile(),
            LogLineAnalyzer.InvalidLinePolicy.SKIP_WITH_COUNT,
            0
        );
        assertEquals(2L, report.invalidLines());
        assertTrue(report.issueSamples().isEmpty());
        assertEquals(4L, report.validLines());
    }

    @Test
    void failFastReportsPhysicalLineNumber() throws IOException {
        var ex = assertThrows(
            LogLineAnalyzer.InvalidLogLineException.class,
            () -> LogLineAnalyzer.analyze(
                sampleFile(),
                LogLineAnalyzer.InvalidLinePolicy.FAIL_FAST,
                0
            )
        );
        assertTrue(ex.getMessage().contains("Dòng 5"));
        assertTrue(ex.getMessage().contains("FIELD_COUNT"));
    }

    @Test
    void emptyFileCreatesEmptyReport() throws IOException {
        Path file = temporary.resolve("empty.log");
        Files.writeString(file, "", StandardCharsets.UTF_8);

        var report = LogLineAnalyzer.analyze(
            file,
            LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
            20
        );
        assertEquals(0L, report.totalLines());
        assertTrue(report.groups().isEmpty());
        assertTrue(report.issueSamples().isEmpty());
    }

    @Test
    void allBlankLinesAreNotInvalid() throws IOException {
        Path file = temporary.resolve("blank.log");
        Files.write(file, List.of("", "  ", "\t"),
            StandardCharsets.UTF_8);

        var report = LogLineAnalyzer.analyze(
            file,
            LogLineAnalyzer.InvalidLinePolicy.FAIL_FAST,
            0
        );
        assertEquals(3L, report.blankLines());
        assertEquals(0L, report.invalidLines());
        assertTrue(report.groups().isEmpty());
    }

    @Test
    void missingFileDoesNotBecomeEmptyReport() {
        Path missing = temporary.resolve("missing.log");
        assertThrows(NoSuchFileException.class, () ->
            LogLineAnalyzer.analyze(
                missing,
                LogLineAnalyzer.InvalidLinePolicy.SKIP_WITH_COUNT,
                0
            )
        );
    }

    @Test
    void rejectsNegativeSampleLimit() throws IOException {
        assertThrows(IllegalArgumentException.class, () ->
            LogLineAnalyzer.analyze(
                sampleFile(),
                LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
                -1
            )
        );
    }

    @Test
    void resultCollectionsCannotBeMutated() throws IOException {
        var report = LogLineAnalyzer.analyze(
            sampleFile(),
            LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
            10
        );

        assertThrows(UnsupportedOperationException.class, () ->
            report.groups().clear()
        );
        assertThrows(UnsupportedOperationException.class, () ->
            report.issueSamples().clear()
        );
        assertFalse(report.groups().get("api").isEmpty());
    }
}
```

**Ý nghĩa các phép thử:**

- Trường hợp **valid/blank/invalid** phải giữ bất biến tổng số dòng.
- Mẫu lỗi bị giới hạn nhưng **bộ đếm không bị giới hạn**.
- `FAIL_FAST` báo đúng dòng vật lý đầu tiên có lỗi, không trả bản báo cáo giả thành công.
- Tệp rỗng và tệp không tồn tại có kết quả khác nhau.
- Các collection trong `Report` không được phép bị caller sửa trực tiếp.

Test `NoSuchFileException` áp dụng cho tệp chưa tồn tại khi mở; một lỗi đọc I/O phát sinh **sau khi mở** thường có đường đi `UncheckedIOException`. Không dễ mô phỏng lỗi đọc giữa chừng bằng tệp thường; trong dự án thật có thể dùng một `Reader` giả lập ném `IOException` ở một vị trí xác định để kiểm tra nhánh này.

## 12. Bài kiểm thử nâng cao: parser và dữ liệu biên

Ngoài các unit test trên, nên có một ma trận kiểm thử độc lập cho các tình huống sau:

| Input | Kết quả mong muốn |
| --- | --- |
| `2026-11-18T08:00:00Z|INFO|api|0` | Valid: thời lượng `0` là hợp lệ |
| `2026-11-18T08:00:00Z|INFO|api|-1` | `NEGATIVE_DURATION` |
| `2026-11-18T08:00:00Z|INFO|api|abc` | `INVALID_DURATION` |
| `2026-11-18T08:00:00Z|DEBUG|api|12` | `INVALID_LEVEL` |
| `not-a-time|INFO|api|12` | `INVALID_TIMESTAMP` |
| `2026-11-18T08:00:00Z|INFO||12` | `INVALID_SERVICE` |
| `2026-11-18T08:00:00Z|INFO|api|` | `INVALID_DURATION` |
| `2026-11-18T08:00:00Z|INFO|api` | `FIELD_COUNT` |
| Một dòng có 5 trường | `FIELD_COUNT` |
| Một dòng chỉ chứa khoảng trắng | Blank, không phải Invalid |
| Chỉ có dòng sai | `groups` rỗng; số `invalidLines` đúng |
| Tất cả sự kiện thuộc một nhóm | Một bộ `Metric` với đúng count/sum |
| Dòng không có newline cuối file | Vẫn được `BufferedReader.readLine` đọc |
| Tổng duration vượt `long` | `ArithmeticException` do `Math.addExact` |
| Đường dẫn null hoặc policy null | `NullPointerException` từ kiểm tra đầu vào |

**Khác biệt quan trọng:** `Long.parseLong` có thể nhận dấu `+` trước số; nếu schema cần **chỉ các chữ số ASCII**, hãy kiểm tra thêm một pattern như `[0-9]+` trước khi parse. Bài hiện quy định kiểu `long` không âm, không cấm rõ dấu cộng; không nên viết test cho một quy tắc chưa được xác định trong hợp đồng.

### 12.1. Dữ liệu có dấu `|` trong một trường

`split("\\|", -1)` chỉ phù hợp với định dạng phân cách đơn giản không có escape hoặc quoting. Nếu service/tin nhắn log có thể chứa `|`, dữ liệu sẽ bị chia sai trường và bị báo `FIELD_COUNT`. Không tự sửa bằng cách ghép tùy tiện các mảnh chuỗi: cần xác định grammar có escape hoặc dùng định dạng có parser đáng tin như JSON Lines.

### 12.2. Unicode và BOM

`StandardCharsets.UTF_8` là lựa chọn minh bạch, nhưng một số nguồn thêm **UTF-8 BOM** ở đầu file. Nếu gặp BOM, `Instant.parse` của trường timestamp đầu tiên có thể không nhận đúng. Nếu hệ thống phải hỗ trợ BOM, định nghĩa và kiểm thử chính sách loại bỏ BOM **chỉ ở đầu tệp**, thay vì gọi `strip()` vô điều kiện trên toàn bộ log.

### 12.3. Stack trace nhiều dòng

Một ngoại lệ Java thường được log thành nhiều dòng; dòng thứ hai trở đi có thể là thông tin stack trace, không phải bản ghi mới. Parser dòng độc lập ở bài này sẽ đánh dấu chúng là `FIELD_COUNT`. Nếu cần xử lý multiline, cần bộ **framing** gom các dòng vật lý thành một sự kiện logic trước khi parse; đồng thời vẫn nên giữ vị trí bắt đầu/kết thúc của sự kiện để truy vết.

## 13. Quyết định xuất bản báo cáo từ các bộ đếm chất lượng

`COLLECT_ERRORS` và `SKIP_WITH_COUNT` cho phép tính số liệu **trên tập dòng hợp lệ**, nhưng không cho biết tự động rằng số liệu ấy đạt chất lượng xuất bản.

Ví dụ thêm một chính sách xuất bản:

```java
static boolean acceptable(LogLineAnalyzer.Report r) {
    long nonBlank = r.validLines() + r.invalidLines();
    if (nonBlank == 0L) {
        return false; // Chưa có mẫu.
    }
    // Ngưỡng minh họa: ít nhất 99% dòng có nội dung hợp lệ.
    return (double) r.validLines() / nonBlank >= 0.99;
}
```

Đây là **một ví dụ quy tắc**, không phải ngưỡng áp dụng cho mọi hệ thống. Có nghiệp vụ yêu cầu **100%**, có nghiệp vụ cho phép một lượng nhỏ dữ liệu lỗi nhưng phải cảnh báo. Nếu số sự kiện thành công quá ít, tỷ lệ 100% cũng có thể không đủ để báo cáo đại diện; cần thêm ngưỡng số mẫu.

Với số lượng dòng rất lớn, biểu thức `validLines + invalidLines` có thể tràn `long`; chương trình chính đã kiểm soát cộng bộ đếm bằng `Math.addExact` và thực tế bị giới hạn bởi khả năng đọc tệp, nhưng các phép tính mới ở tầng quyết định cũng nên xác định miền số và quy tắc kiểm tra tràn phù hợp.

### 13.1. Không định nghĩa thành công bằng “không thấy exception”

Trong hai chế độ best effort, `analyze` có thể trả `Report` bình thường dù `invalidLines > 0`. Vì vậy:

- **Kỹ thuật:** tệp đã đọc hoàn tất, không có lỗi I/O hay overflow, báo cáo đã tạo.
- **Chất lượng dữ liệu:** tỷ lệ dòng hợp lệ, số lỗi và loại lỗi có đáp ứng chính sách?
- **Nghiệp vụ:** báo cáo có đủ chính xác để dùng cho giám sát, cảnh báo hay quyết định?

Ba kết luận này nên được biểu diễn riêng trong hệ thống vận hành.

## 14. Nhiều tệp: phân biệt lỗi của từng tệp với lỗi của từng dòng

Nếu một ngày có 100 tệp log, có hai cấp kết quả:

```text
BatchReport
  ├── app-01.log -> Report (thành công, invalidLines = 2)
  ├── app-02.log -> Report (thành công, invalidLines = 0)
  ├── app-03.log -> FileFailure(IOException)
  └── ...
```

**Chính sách lỗi dòng** điều khiển xử lý **bên trong một tệp**. **Chính sách lỗi tệp** quyết định việc tiếp tục khi một tệp không thể mở/đọc. Không trộn hai cấp bằng cách bắt mọi `IOException` rồi trả `new Report(0,0,...)`.

Ví dụ skeleton mô tả các trạng thái cấp tệp:

```java
sealed interface FileResult permits FileSuccess, FileFailure {}

record FileSuccess(
    Path path, LogLineAnalyzer.Report report
) implements FileResult {}

record FileFailure(
    Path path, String errorCode, String message
) implements FileResult {}
```

Nếu hệ thống chọn **continue-on-file-error**, hãy lưu đường dẫn, mã lỗi và nguyên nhân đã làm sạch thông tin nhạy cảm; báo cáo tổng phải hiển thị cả số tệp thành công lẫn thất bại. Với chế độ **fail-batch-fast**, ngoại lệ ở một tệp phải dẫn đến dừng batch và đóng mọi nguồn đã mở.

### 14.1. `Files.list`, `flatMap` và tài nguyên con

Khi liệt kê đường dẫn:

```java
try (Stream<Path> paths = Files.list(directory)) {
    List<Path> selected = paths
        .filter(path -> path.getFileName().toString()
            .endsWith(".log"))
        .toList();
}
```

`Files.list` giữ tài nguyên duyệt thư mục, cần đóng. Sau khi lấy danh sách `Path`, có thể phân tích từng file bằng `analyze` với policy phù hợp. Nếu sử dụng `flatMap` để mở `Files.lines` cho từng tệp, cần đọc kỹ hợp đồng đóng stream con; còn nguồn thư mục vẫn thuộc sở hữu caller.

**Không** dựa vào thứ tự `Files.list` để nói “tệp đầu tiên” nếu chưa sắp theo một tiêu chí; điều này ảnh hưởng tới chính sách dừng ngay khi gặp tệp lỗi và thứ tự ví dụ lỗi được báo.

## 15. Tính lười, short-circuit và vấn đề log thay đổi khi đọc

### 15.1. Vì sao không đặt `limit` rồi gọi đó là báo cáo toàn tệp?

`limit(1000)` chỉ phân tích **tối đa 1.000 dòng đầu**, không phải toàn bộ file. Đây có thể là chế độ **lấy mẫu** hợp lệ, nhưng phải gắn nhãn kết quả là mẫu:

```java
try (Stream<String> lines = Files.lines(path)) {
    long firstThousand = lines
        .limit(1_000)
        .filter(line -> !line.isBlank())
        .count();
}
```

Đừng dùng số đếm này làm số sự kiện cả tệp. `findFirst` cũng có thể dừng sớm, nên pipeline chưa kiểm tra những dòng phía sau và không thể kết luận “tệp không có lỗi”.

### 15.2. Không nên dựa vào số lần gọi `peek` hoặc mapper để ghi log kiểm toán

Các thao tác trung gian của Stream API là lazy và có thể bị short-circuit. Một số tối ưu hóa hợp lệ còn có thể lược bỏ lời gọi trung gian không ảnh hưởng tới kết quả terminal. Vì vậy, tránh đưa side effect bắt buộc (ví dụ tăng bộ đếm nghiệp vụ, ghi audit record, mở file không được đóng) vào `peek` hoặc mapper.

Trong chương trình chính, parser tạo `ParseOutcome` và **collector là nơi ghi nhận số lượng**, tránh bộ đếm dùng chung ngoài pipeline.

### 15.3. File đang được ghi, xoay vòng hoặc cắt ngắn

Với log được ghi liên tục, không được giả định file là snapshot bất biến:

- Writer có thể nối thêm dòng trong khi reader đang xử lý.
- Hệ thống log rotation có thể đổi tên hoặc thay thế file.
- Một dòng đang ghi dở có thể thiếu trường ở thời điểm reader thấy nó.
- Metadata về dung lượng và tổng dòng có thể thay đổi.

Bài toán **phân tích file đã chốt** khác bài toán **theo dõi log thời gian thực**. Với báo cáo tái lập, nên sử dụng file snapshot hoặc một mốc dữ liệu đã đóng; với tailing/live monitoring, cần thiết kế vòng đời reader, retry, checkpoint và xử lý dòng chưa hoàn chỉnh.

### 15.4. Không chuyển lỗi I/O thành dòng `Invalid`

Lỗi I/O có thể xảy ra giữa hai lời gọi `readLine`; không nên cố tạo `Rejected("IO_ERROR")` như thể đó là một dòng thuộc schema. Reader đã không cung cấp được nội dung dòng đó; không biết tệp còn bao nhiêu dòng chưa đọc. Nếu tiếp tục sau lỗi đọc, cần cơ chế retry/reopen và xác định tính nhất quán riêng, không nằm trong ba chính sách lỗi dữ liệu của bài.

## 16. Hiệu năng, bộ nhớ và bảo mật trong hệ thống thực

### 16.1. Cân bằng throughput và khả năng chẩn đoán

| Thiết kế | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| `Files.readAllLines` | Đơn giản khi tệp nhỏ | Bộ nhớ tăng theo toàn bộ nội dung |
| `Files.lines` | Đọc lười, tiện cho Stream | Không có số dòng tự động; phải đóng stream |
| `BufferedReader.readLine` + iterator | Giữ số dòng, kiểm soát I/O | Cần cài đặt lookahead và ownership đúng |
| `COLLECT_ERRORS` không giới hạn | Chẩn đoán đầy đủ | Có thể giữ quá nhiều lỗi trong RAM |
| `COLLECT_ERRORS` giới hạn mẫu | Bộ nhớ lỗi có giới hạn | Không lưu mọi vị trí lỗi |
| `summarizingLong` theo nhóm | Có count/sum/min/max/avg | Tổng `long` không tự phát hiện tràn |
| Accumulator với `Math.addExact` | Tránh overflow im lặng | Có thêm code và chi phí kiểm tra |

Phép `String.split` và `String.matches` đơn giản, đủ cho bài học; với log có lưu lượng lớn, có thể cân nhắc parser tối ưu hơn và `Pattern` được biên dịch một lần. Chỉ tối ưu sau khi xác nhận schema và dữ liệu có đúng không, đồng thời dùng benchmark trên JDK/thực tế hệ thống.

### 16.2. Kích thước một dòng và quá nhiều khóa nhóm

Pipeline không lưu toàn bộ tệp, nhưng **một dòng rất dài** vẫn cần bộ nhớ đủ để biểu diễn chuỗi đó. Ngoài ra, nếu `service` có hàng triệu giá trị khác nhau, số nhóm `O(g)` có thể lớn. Hệ thống sản xuất cần giới hạn độ dài dòng, độ dài trường, số nhóm, thời gian xử lý và chính sách từ chối dữ liệu ngoài ngưỡng.

Không dùng `durationMs` âm làm cờ “thiếu dữ liệu”: bài đã quy định nó là lỗi. Nếu cần biểu diễn đo không thành công, thêm trạng thái tường minh thay vì nhét sentinel vào số đo.

### 16.3. Log có thể chứa bí mật

Ngay cả khi ứng dụng chỉ lưu `Issue(lineNumber, code)`, log nguồn có thể chứa token truy cập, cookie, email hoặc ID. Không tự in toàn bộ dòng sai trong `catch`, không chuyển nguyên văn message exception của hệ thống ra API công khai và không đưa dữ liệu nhạy cảm vào dashboard nếu chưa có chính sách xử lý.

Khi cần điều tra, dùng đường dẫn và số dòng kết hợp với cơ chế truy cập tệp có kiểm soát. Các ví dụ log trong bài chỉ chứa dữ liệu giả lập.

### 16.4. Kiểm soát tài nguyên và dừng công việc

`try-with-resources` bảo vệ reader kể cả khi parser, accumulator hoặc downstream ném lỗi. Nhưng nó không tự giải quyết timeout cho nguồn mạng hoặc ngăn một dòng quá dài được cấp phát. Với nguồn ngoài file cục bộ, cần bổ sung timeout, khả năng hủy và giới hạn tài nguyên ở tầng I/O.

## 17. Các phản mẫu cần tránh

| Phản mẫu | Điều có thể sai | Giải pháp |
| --- | --- | --- |
| `Files.lines(path).collect(...)` không đóng stream | Rò rỉ tài nguyên I/O | `try-with-resources` |
| Parser trả `null` cho mọi lỗi | Mất nguyên nhân và số lỗi | `ParseOutcome` tường minh |
| `catch (Exception) { return Stream.empty(); }` | Nuốt lỗi đọc/tạo báo cáo thiếu | Tách lỗi schema khỏi lỗi I/O |
| `filter(Objects::nonNull)` ngay sau parser | Bỏ số liệu về dòng sai | Đếm loại kết quả trước khi loại |
| `AtomicLong.incrementAndGet()` trong mapper song song để đánh số dòng | Số dòng phụ thuộc lịch chạy | Nguồn `NumberedLine` tuần tự hoặc Spliterator được thiết kế riêng |
| Dùng `issueSamples.size()` làm tổng lỗi | Sai khi áp sample limit | Sử dụng `invalidLines` |
| Xem duration `0` là không có mẫu | Nhầm với sự kiện hợp lệ duration 0 | Lưu `count` |
| Tính trung bình từ các trung bình nhóm không trọng số | Sai khi số sự kiện mỗi nhóm khác nhau | Gộp tổng và count |
| Đọc toàn bộ file bằng `readAllLines` không cân nhắc kích thước | Có thể hết bộ nhớ | Đọc lười, tích lũy gọn |
| Dùng `limit` nhưng ghi nhãn báo cáo toàn file | Bỏ dòng chưa duyệt | Đặt tên báo cáo là mẫu hoặc không giới hạn |
| Luôn `parallel()` khi đọc một reader | Nguồn có con trỏ tuần tự; overhead và rủi ro | Đo hiệu năng và thiết kế nguồn chia được |
| Dùng `LongSummaryStatistics` mà tưởng luôn phát hiện overflow | Tổng có thể tràn | `Math.addExact` hoặc số học lớn |
| Lưu cả raw line lỗi trong dashboard | Có thể làm lộ dữ liệu nhạy cảm | Chỉ lưu mã lỗi, số dòng và preview đã làm sạch khi cần |
| Cho rằng file không thay đổi trong lúc đọc | Log rotation hoặc ghi dở | Snapshot/mốc dữ liệu hoặc mô hình streaming thời gian thực |

## 18. Bài tập áp dụng

### Bài 1 — Chọn policy

Cho log 7 dòng ở mục 1, chạy đủ `FAIL_FAST`, `SKIP_WITH_COUNT` và `COLLECT_ERRORS` với `sampleLimit = 1`. Viết bảng thể hiện số dòng hợp lệ, trắng, sai và số ví dụ lỗi. Giải thích vì sao `FAIL_FAST` không có báo cáo thành công, trong khi hai mode best effort phải ghi rõ đã bỏ dòng.

### Bài 2 — Thêm mã lỗi mới

Thay schema `durationMs` thành số nguyên dương **lớn hơn 0**. Điều chỉnh parser để duration bằng 0 trả `ZERO_DURATION` thay vì hợp lệ. Viết test cho số `0`, số âm, chuỗi rỗng và chuỗi không phải số. Mô tả tác động của thay đổi schema tới số liệu lịch sử.

### Bài 3 — Tính tỉ lệ ERROR theo service

Từ `Report.groups()`, tính cho từng service:

\[
\text{errorRate}=\frac{\text{ERROR count}}
{\text{INFO count}+\text{WARN count}+\text{ERROR count}}
\]

Nếu một service không có event hợp lệ, không tự tạo tỷ lệ `0` mà cần thể hiện “không có dữ liệu”. Đối chiếu kết quả `api` trên file mẫu: có 2 ERROR trên tổng 3 sự kiện.

### Bài 4 — Top service theo tổng thời lượng

Tạo danh sách service sắp theo tổng `totalMs` giảm dần, phá hòa bằng tên service tăng dần. Không phụ thuộc vào thứ tự duyệt của `HashMap`. Giải thích sự khác biệt giữa thống kê theo `service` và thống kê theo `service + level`.

### Bài 5 — Giới hạn mẫu lỗi và số lượng lớn

Sinh 10.000 dòng không hợp lệ và chạy `COLLECT_ERRORS` với `sampleLimit = 10`. Kiểm chứng `invalidLines == 10_000`, danh sách lỗi chỉ có 10 mục và `totalLines` vẫn chính xác. Đánh giá bộ nhớ khi tăng giới hạn lên 10.000.

### Bài 6 — Nguồn I/O giả lập lỗi

Xây một `Reader`/`BufferedReader` thử nghiệm ném `IOException` sau ba dòng. Chỉnh thiết kế để có thể inject reader vào hàm phân tích trong test. Chứng minh rằng lỗi này **không trở thành `Rejected`**, và reader vẫn được đóng khi thất bại.

### Bài 7 — Báo cáo nhiều file

Cho ba file `app-1.log`, `app-2.log` và một file không tồn tại. Thiết kế kiểu kết quả bao gồm `FileSuccess` và `FileFailure`. Lựa chọn một chính sách **fail-batch-fast** hoặc **continue-on-file-error** rồi giải thích việc xử lý lỗi dòng trong từng file vẫn độc lập.

### Bài 8 — Log nhiều dòng

Định nghĩa một quy tắc cho phép dòng bắt đầu bằng whitespace là phần tiếp nối stack trace của sự kiện trước. Phác thảo **framing state machine** để gom nhiều dòng vật lý thành một sự kiện logic, nêu cách báo phạm vi `startLine/endLine` và xử lý trường hợp file kết thúc giữa một sự kiện.

### Bài 9 — Số học và độ chính xác

Thêm hai dòng hợp lệ có duration `Long.MAX_VALUE` và `1` trong cùng nhóm. Chứng minh `Math.addExact` tạo lỗi khi tổng vượt miền số. Viết bản thay thế dùng `BigInteger` nếu nghiệp vụ thật sự cho phép giá trị lớn đó; không nuốt lỗi thành số âm.

## 19. Checklist trước khi dùng pipeline log trong thực tế

- [ ] Định dạng log và charset được công bố rõ.
- [ ] Biết trường hợp nào là dòng **blank**, **invalid** hay **valid**.
- [ ] Mỗi dòng vật lý có số thứ tự rõ ràng.
- [ ] Parser chỉ bắt các lỗi dữ liệu dự kiến, không nuốt mọi exception.
- [ ] Chính sách `FAIL_FAST` / `SKIP_WITH_COUNT` / `COLLECT_ERRORS` được chọn tường minh.
- [ ] Có đủ `totalLines`, `validLines`, `blankLines` và `invalidLines` để đối chiếu.
- [ ] Giới hạn lỗi mẫu **không** giới hạn bộ đếm lỗi tổng.
- [ ] Lỗi I/O không bị chuyển nhầm thành “dữ liệu rỗng”.
- [ ] `BufferedReader` hoặc `Files.lines` được đóng đúng owner.
- [ ] Không đưa số thứ tự dòng vào mapper dùng chung trạng thái khi chạy song song.
- [ ] Không giữ toàn bộ tệp trong RAM nếu chỉ cần thống kê.
- [ ] Không coi trung bình trên tập không có mẫu là giá trị đo thực.
- [ ] Kiểm soát tràn số, độ chính xác `double` và thời lượng âm.
- [ ] Đã kiểm thử file rỗng, file thiếu, dòng sai, dòng trắng, lỗi đọc và tổng hợp theo nhóm.
- [ ] Không ghi raw log nhạy cảm vào chẩn đoán nếu chưa có cơ chế làm sạch.
- [ ] Có chính sách cho log đang ghi/rotate và nhiều file nếu hệ thống cần.

## 20. Bảng quyết định và tổng kết

| Yêu cầu | Lựa chọn khuyến nghị |
| --- | --- |
| Chỉ cần đọc dòng theo luồng | `Files.lines(path, UTF_8)` trong `try-with-resources` |
| Cần số dòng vật lý chính xác và dễ kiểm chứng | `BufferedReader.readLine` + `Iterator<NumberedLine>` tuần tự |
| Cần biểu diễn lỗi parse phân biệt với dòng trắng | Kiểu `ParseOutcome` có `Accepted`, `Blank`, `Rejected` |
| Một dòng lỗi phải làm hỏng toàn bộ báo cáo | `FAIL_FAST` |
| Cho phép bỏ dòng lỗi nhưng cần giám sát chất lượng | `SKIP_WITH_COUNT` |
| Cần một số ví dụ để điều tra | `COLLECT_ERRORS` kèm `sampleLimit` |
| Cần đếm đủ dòng và thống kê theo nhiều khóa | Một collector giữ counters và map `service → level → Metric` |
| Chỉ cần thống kê số trên dữ liệu đã sạch | `groupingBy` + `counting`/`summarizingLong` |
| Nguồn không mở/đọc được | Báo lỗi I/O, không biến thành báo cáo rỗng |
| Cần tổng số chính xác vượt `long` | Dùng `BigInteger`/`BigDecimal` theo miền nghiệp vụ |
| Muốn phân tích nhiều file | Chọn chính sách lỗi **cấp tệp** riêng và đóng từng nguồn |
| Muốn tính theo luồng thời gian thực | Mô hình tailing, checkpoint, retry và xử lý dòng chưa hoàn chỉnh riêng |

**Phân tích tệp log theo dòng với chính sách xử lý lỗi rõ ràng** không chỉ là thao tác `Files.lines(...).filter(...).count()`. Điểm quan trọng là **đúng hợp đồng dữ liệu**: ghi nhận đủ dòng hợp lệ, trắng và sai; không đánh đồng lỗi parser với lỗi I/O; trả số liệu có thể kiểm chứng; đóng nguồn đúng vòng đời và khống chế lượng bộ nhớ dùng để chẩn đoán. Khi những điều kiện này được bảo đảm, Java Stream API giúp diễn đạt các phép `map`, `filter`, `collect`, thống kê theo nhóm và các bước báo cáo tiếp theo một cách rõ ràng, dễ mở rộng và an toàn hơn.
