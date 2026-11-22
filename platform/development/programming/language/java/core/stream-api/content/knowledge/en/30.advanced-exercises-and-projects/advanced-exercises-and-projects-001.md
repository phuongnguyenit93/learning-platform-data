# Xây dựng bộ phân tích tệp lớn với đóng tài nguyên đúng vòng đời

Trong chương **Bài tập nâng cao và dự án** của **Java Stream API**, chúng ta kết hợp các kiến thức về nguồn Stream, pipeline lazy, `filter`, `map`, `reduce`, `collect` và quản lý tài nguyên để giải quyết một bài toán gần với công việc thực tế: **phân tích một tệp log lớn mà không tải toàn bộ các dòng vào bộ nhớ**.

Trọng tâm không phải viết một pipeline ngắn nhất. Một bộ phân tích đáng tin cậy cần đồng thời đáp ứng:

- **Đúng kết quả:** phân biệt bản ghi hợp lệ với dòng lỗi; không bỏ sót hoặc đếm trùng.
- **Không phụ thuộc kích thước toàn bộ tệp:** xử lý từng dòng và chỉ lưu những thống kê thực sự cần.
- **Đóng tài nguyên đúng vòng đời:** tệp được đóng cả khi xử lý thành công, ném ngoại lệ hoặc dừng sớm.
- **Hợp đồng rõ ràng:** định dạng đầu vào, kiểu dữ liệu, giới hạn bộ nhớ, tràn số, thời điểm hoàn tất và chính sách báo lỗi phải được xác định.
- **Có thể kiểm chứng:** có dữ liệu mẫu, kết quả mong đợi, các tình huống biên và hướng mở rộng.

Chúng ta sẽ xây dựng bộ phân tích log theo dịch vụ. Sau phần triển khai, bài học còn trình bày cách thêm bộ lọc, tránh các bẫy với Stream song song, benchmark và các nhiệm vụ mở rộng.

> **Môi trường ví dụ:** Java 17 trở lên, mã hóa UTF-8 và một tệp văn bản ghi từng sự kiện trên một dòng. Phần cốt lõi của Stream API và `Files.lines` có từ Java 8; `record`, `String.isBlank()` và các API tiện ích sử dụng trong ví dụ đòi hỏi phiên bản mới hơn.

## 1. Đặc tả bài toán trước khi viết code

Giả sử hệ thống có một tệp log lớn, mỗi dòng biểu diễn một yêu cầu đã xử lý. Định dạng được **đơn giản hóa có chủ đích** cho dự án:

~~~text
timestamp|service|level|latencyMs
~~~

Trong đó:

| Trường | Kiểu và quy tắc | Ví dụ |
| --- | --- | --- |
| `timestamp` | Thời điểm UTC theo ISO-8601, phân tích được bằng `Instant.parse` | `2026-11-18T08:00:00Z` |
| `service` | Mã dịch vụ không rỗng, chỉ gồm chữ ASCII, số, dấu chấm, gạch ngang, gạch dưới | `checkout` |
| `level` | Một trong `INFO`, `WARN`, `ERROR` (phân biệt hoa/thường) | `ERROR` |
| `latencyMs` | Số nguyên `long` không âm, đơn vị mili-giây | `145` |

Ký tự `|` là dấu phân cách. Dự án **không** hỗ trợ ký tự phân cách nằm trong giá trị, dòng log nhiều dòng, cú pháp CSV có quote, hoặc các biến thể timestamp khác. Nếu dữ liệu thực có các trường hợp đó, cần dùng parser đúng với định dạng thực thay vì mở rộng `String.split` một cách tùy tiện.

### Kết quả cần xuất

Với toàn bộ tệp, báo cáo phải có:

1. **Tổng số dòng** đã đọc.
2. **Số dòng hợp lệ** và **số dòng không hợp lệ**.
3. **Số sự kiện `WARN`** và **`ERROR`** hợp lệ.
4. Với **mỗi dịch vụ**: số yêu cầu, số lỗi, tổng thời gian xử lý, độ trễ lớn nhất và độ trễ trung bình.

Không lưu toàn bộ log. Một dòng hỏng được tính vào `totalLines` và `invalidLines`, nhưng **không** làm tăng thống kê của dịch vụ.

### Dữ liệu mẫu

Tệp `events.log`:

~~~text
2026-11-18T08:00:00Z|checkout|INFO|120
2026-11-18T08:00:01Z|search|WARN|45
2026-11-18T08:00:02Z|checkout|ERROR|310
not-a-log-line
2026-11-18T08:00:03Z|search|INFO|20
2026-11-18T08:00:04Z|checkout|WARN|-1
~~~

Kết quả kỳ vọng:

| Chỉ số chung | Giá trị |
| --- | ---: |
| Tổng dòng | 6 |
| Dòng hợp lệ | 4 |
| Dòng không hợp lệ | 2 |
| Sự kiện `WARN` hợp lệ | 1 |
| Sự kiện `ERROR` hợp lệ | 1 |

| Dịch vụ | Số yêu cầu | Lỗi | Tổng độ trễ (ms) | Lớn nhất (ms) | Trung bình (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `checkout` | 2 | 1 | 430 | 310 | 215.00 |
| `search` | 2 | 0 | 65 | 45 | 32.50 |

Dòng `not-a-log-line` sai cấu trúc; dòng có `latencyMs = -1` sai quy tắc dữ liệu. Cả hai đều bị loại khỏi thống kê dịch vụ.

## 2. Kiến trúc một lượt đọc

Thay vì đọc hết tệp vào `List<String>`, chúng ta tạo một nguồn lazy và duyệt tệp **một lần**:

~~~text
Tệp events.log
      |
      v
Files.lines(path, UTF_8)       [nguồn I/O, cần đóng]
      |
      v
Stream<String>
      |
      v
collect(Report::new,
        Report::acceptLine,
        Report::merge)
      |
      v
Report
  +-- tổng dòng / dòng lỗi / WARN / ERROR
  +-- Map<service, ServiceStats>
      +-- số yêu cầu
      +-- số ERROR
      +-- tổng độ trễ
      +-- độ trễ lớn nhất
      |
      v
Đóng Stream khi ra khỏi try-with-resources
      |
      v
In hoặc xuất Report
~~~

`collect` ở đây là một **mutable reduction có kiểm soát**: nó tạo vùng tích lũy `Report`, nhận từng dòng và gộp các kết quả thành một báo cáo. Ta chỉ thay đổi đối tượng tích lũy do collector quản lý, không cập nhật một Map dùng chung từ `parallelStream().forEach(...)`.

Bộ nhớ cần giữ chủ yếu là **thống kê cho từng dịch vụ**, không phải một đối tượng cho từng dòng đã đọc. Đó là sự khác nhau giữa “phân tích tệp lớn” và “đọc tệp lớn vào danh sách rồi mới phân tích”.

## 3. Vì sao chọn Files.lines và try-with-resources?

`Files.lines(path, StandardCharsets.UTF_8)` trả về `Stream<String>`, có thể đọc các dòng khi pipeline yêu cầu. Nguồn này gắn với tài nguyên I/O cần đóng.

Cách đúng:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
~~~

`try-with-resources` đóng Stream khi rời khối, kể cả khi `count()` ném ngoại lệ. Trái lại, cách viết sau không thiết lập vòng đời đóng:

~~~java
// Không nên dùng với nguồn Files.lines.
long count = Files.lines(path, StandardCharsets.UTF_8).count();
~~~

**Terminal operation không tự động đóng Stream.** Những phương thức như `count`, `collect`, `reduce`, `findFirst`, `anyMatch` hay `toList` kết thúc pipeline logic, nhưng không thay thế `close()` của nguồn I/O.

`Files.lines` có thể mở tệp thành công nhưng gặp lỗi I/O **trong lúc terminal operation đang đọc dữ liệu**. Tùy giai đoạn, lỗi có thể xuất hiện dưới dạng `IOException` (mở nguồn) hoặc `UncheckedIOException` (đọc lazy). Cả hai trường hợp vẫn cần được thông báo đúng, không được tự biến thành “tệp có 0 bản ghi”.

## 4. Thiết kế kiểu dữ liệu và ranh giới parser

Chúng ta tách ba trách nhiệm:

- `LogEvent`: biểu diễn **một dòng hợp lệ** sau parse.
- `ServiceStats`: giữ thống kê cho **một dịch vụ**.
- `Report`: giữ thống kê toàn tệp và Map những dịch vụ đã xuất hiện.

Có thể dùng `record` cho dữ liệu kết quả parse:

~~~java
enum Level { INFO, WARN, ERROR }

record LogEvent(
        java.time.Instant timestamp,
        String service,
        Level level,
        long latencyMs
) {}
~~~

Parser có hợp đồng rõ:

~~~text
parseLine(dòng hợp lệ)       -> LogEvent
parseLine(dòng lỗi dữ liệu)  -> null (được tính invalid)
~~~

Trong **dự án minh họa**, sử dụng `null` như tín hiệu nội bộ của parser giúp mã ngắn. Với API công khai hoặc khi cần thông tin lỗi chi tiết, nên dùng kiểu kết quả parse có cấu trúc, chẳng hạn `ParseResult` gồm `Success`/`Failure`, thay vì trả `null`.

Phân biệt **lỗi bản ghi** với **lỗi hệ thống**:

- Sai timestamp, sai `level`, độ trễ âm: **dữ liệu không hợp lệ**, báo cáo tăng bộ đếm `invalidLines`.
- Tệp không tồn tại, mất quyền truy cập, lỗi giải mã, I/O bị ngắt: **lỗi đọc nguồn**, nên được ném lên; không lặng lẽ tính là một dòng hỏng.
- Tràn `long` khi cộng tổng: **lỗi giới hạn số học**, cần được xử lý riêng, không coi đó là một bản ghi lỗi thông thường.

Thiết kế này giúp vận hành hiểu khi nào báo cáo thật sự hoàn tất và khi nào không đáng tin cậy.

## 5. Triển khai hoàn chỉnh: LargeLogAnalyzer

Đây là phiên bản có thể đặt trong tệp `LargeLogAnalyzer.java` khi thực hành. Toàn bộ phân tích nằm trong một lượt `collect` và nguồn tệp được đóng tại đúng phạm vi sở hữu.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Stream;

public class LargeLogAnalyzer {

    enum Level { INFO, WARN, ERROR }

    record LogEvent(
            Instant timestamp,
            String service,
            Level level,
            long latencyMs
    ) {}

    // Thống kê cho đúng một dịch vụ.
    static final class ServiceStats {
        long requests;
        long errors;
        long totalLatencyMs;
        long maxLatencyMs;

        void accept(LogEvent event) {
            requests = Math.addExact(requests, 1L);
            if (event.level() == Level.ERROR) {
                errors = Math.addExact(errors, 1L);
            }
            totalLatencyMs = Math.addExact(
                    totalLatencyMs, event.latencyMs());
            maxLatencyMs = Math.max(
                    maxLatencyMs, event.latencyMs());
        }

        void merge(ServiceStats other) {
            requests = Math.addExact(requests, other.requests);
            errors = Math.addExact(errors, other.errors);
            totalLatencyMs = Math.addExact(
                    totalLatencyMs, other.totalLatencyMs);
            maxLatencyMs = Math.max(
                    maxLatencyMs, other.maxLatencyMs);
        }

        double averageLatencyMs() {
            return requests == 0
                    ? 0.0
                    : (double) totalLatencyMs / requests;
        }
    }

    // Vùng tích lũy của collector: mỗi dòng đi qua đúng một lần.
    static final class Report {
        long totalLines;
        long validLines;
        long invalidLines;
        long warningEvents;
        long errorEvents;
        final Map<String, ServiceStats> byService = new HashMap<>();

        void acceptLine(String line) {
            totalLines = Math.addExact(totalLines, 1L);

            LogEvent event = parseLine(line);
            if (event == null) {
                invalidLines = Math.addExact(invalidLines, 1L);
                return;
            }

            validLines = Math.addExact(validLines, 1L);

            if (event.level() == Level.WARN) {
                warningEvents = Math.addExact(warningEvents, 1L);
            } else if (event.level() == Level.ERROR) {
                errorEvents = Math.addExact(errorEvents, 1L);
            }

            byService.computeIfAbsent(
                    event.service(), key -> new ServiceStats()
            ).accept(event);
        }

        // Combiner dùng khi collector cần gộp các kết quả riêng.
        void merge(Report other) {
            totalLines = Math.addExact(totalLines, other.totalLines);
            validLines = Math.addExact(validLines, other.validLines);
            invalidLines = Math.addExact(invalidLines, other.invalidLines);
            warningEvents = Math.addExact(
                    warningEvents, other.warningEvents);
            errorEvents = Math.addExact(
                    errorEvents, other.errorEvents);

            other.byService.forEach((service, stats) ->
                    byService.computeIfAbsent(
                            service, key -> new ServiceStats()
                    ).merge(stats)
            );
        }
    }

    // null = một dòng không đúng định dạng của dự án.
    static LogEvent parseLine(String line) {
        String[] fields = line.split("\\|", -1);
        if (fields.length != 4) {
            return null;
        }

        String service = fields[1].trim();
        if (!service.matches("[A-Za-z0-9._-]+")) {
            return null;
        }

        try {
            Instant timestamp = Instant.parse(fields[0].trim());
            Level level = Level.valueOf(fields[2].trim());
            long latencyMs = Long.parseLong(fields[3].trim());

            if (latencyMs < 0) {
                return null;
            }

            return new LogEvent(
                    timestamp, service, level, latencyMs);
        } catch (DateTimeParseException
                 | IllegalArgumentException ex) {
            return null;
        }
    }

    static Report analyze(Path path) throws IOException {
        // Stream được mở, duyệt và đóng trong cùng một phương thức.
        try (Stream<String> lines =
                     Files.lines(path, StandardCharsets.UTF_8)) {

            return lines.collect(
                    Report::new,
                    Report::acceptLine,
                    Report::merge
            );
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java LargeLogAnalyzer <path-to-log>");
            return;
        }

        Report report = analyze(Path.of(args[0]));

        System.out.printf(
                "total=%d valid=%d invalid=%d warnings=%d errors=%d%n",
                report.totalLines,
                report.validLines,
                report.invalidLines,
                report.warningEvents,
                report.errorEvents
        );

        report.byService.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> {
                    ServiceStats stats = entry.getValue();
                    System.out.printf(
                            Locale.ROOT,
                            "%s: requests=%d errors=%d " +
                            "sumMs=%d maxMs=%d avgMs=%.2f%n",
                            entry.getKey(),
                            stats.requests,
                            stats.errors,
                            stats.totalLatencyMs,
                            stats.maxLatencyMs,
                            stats.averageLatencyMs()
                    );
                });
    }
}
~~~

Để thực hành với file mẫu, lưu sáu dòng log của phần 1 vào `events.log`, đặt tệp Java và log ở thư mục làm việc rồi chạy:

~~~bash
javac LargeLogAnalyzer.java
java LargeLogAnalyzer events.log
~~~

Kết quả kỳ vọng:

~~~text
total=6 valid=4 invalid=2 warnings=1 errors=1
checkout: requests=2 errors=1 sumMs=430 maxMs=310 avgMs=215.00
search: requests=2 errors=0 sumMs=65 maxMs=45 avgMs=32.50
~~~

Tên dịch vụ được sắp theo khóa **sau khi đã đóng nguồn tệp**. Đây là một Stream mới trên `Map` kết quả, không phải tiếp tục sử dụng Stream đọc tệp đã đóng.

> Ví dụ áp dụng giả định rằng số dịch vụ phân biệt đủ nhỏ để giữ Map thống kê trong bộ nhớ. Trong hệ thống thực, mã dịch vụ có thể cần validation chặt hơn và các bản ghi có kích thước bất thường cần chính sách giới hạn riêng.

## 6. Vì sao triển khai này không phải đọc hết tệp vào RAM?

Một cách viết đơn giản nhưng kém phù hợp với tệp lớn:

~~~java
// Tránh làm thế này nếu mục tiêu là xử lý tệp lớn một lượt.
java.util.List<String> allLines = Files.readAllLines(
        path, StandardCharsets.UTF_8);

long errors = allLines.stream()
        .filter(line -> line.contains("|ERROR|"))
        .count();
~~~

`Files.readAllLines` tạo một `List<String>` chứa toàn bộ dòng. Khi tệp lớn, nhu cầu bộ nhớ tăng theo **tổng kích thước văn bản**. Hơn nữa, phép tìm chuỗi `"|ERROR|"` không xác thực định dạng hay đảm bảo sự kiện có level hợp lệ.

Với `Files.lines` kết hợp một accumulator:

~~~java
try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {

    Report report = lines.collect(
            Report::new,
            Report::acceptLine,
            Report::merge);
}
~~~

Mỗi dòng được xử lý rồi có thể trở thành đối tượng đủ điều kiện để thu gom rác; phần tồn tại lâu dài là các bộ đếm và `Map<String, ServiceStats>`. Vì vậy, mức sử dụng bộ nhớ **không tăng tuyến tính theo số dòng** nếu số dịch vụ phân biệt và độ dài từng dòng được giới hạn hợp lý.

Ký hiệu sơ bộ:

- `N`: tổng số dòng của tệp.
- `D`: số dịch vụ phân biệt.
- `L`: kích thước dòng lớn nhất cần xử lý trong một thời điểm.

Thời gian xử lý thường tỷ lệ theo số dòng và độ dài cần parse, cộng chi phí cập nhật Map; bộ nhớ tích lũy của báo cáo khoảng **O(D)**, còn bộ đệm đọc/parsing phụ thuộc nguồn và kích thước dòng (có thể xem như **O(D + L)** nếu chỉ xét trạng thái cần giữ).

**Lưu ý:** Không được quảng cáo “bộ nhớ hằng số trong mọi trường hợp”. Một tệp có hàng triệu mã dịch vụ khác nhau sẽ tạo rất nhiều mục Map. Một dòng đơn lẻ dài bất thường vẫn cần được đọc và parse. Nếu phải giới hạn bộ nhớ tuyệt đối, cần thay đổi mô hình lưu trữ, áp giới hạn kích thước/giá trị hoặc sử dụng cơ chế tổng hợp ngoài bộ nhớ như database hay external aggregation.

## 7. Vai trò của collect ba tham số

Đoạn mã cốt lõi:

~~~java
return lines.collect(
        Report::new,
        Report::acceptLine,
        Report::merge
);
~~~

Chữ ký chung của overload:

~~~java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner
)
~~~

Ánh xạ vào dự án:

| Tham số | Kiểu | Vai trò |
| --- | --- | --- |
| `supplier` | `() -> Report` | Tạo vùng tích lũy độc lập. |
| `accumulator` | `(Report, String) -> void` | Đếm một dòng, parse và cập nhật các thống kê. |
| `combiner` | `(Report, Report) -> void` | Ghép hai báo cáo trung gian khi Stream chia phần. |
| Kết quả | `Report` | Báo cáo được thu sau khi pipeline kết thúc. |

Ở chế độ tuần tự, phần lớn công việc đi qua `acceptLine`. Nhưng `merge` vẫn là một thành phần bắt buộc của hợp đồng thu thập, và phải gộp tất cả trường của báo cáo đúng ý nghĩa.

**Không nên làm điều tương tự bằng một biến báo cáo dùng chung và `parallel().forEach(report::acceptLine)`.** Vì `Report`/`HashMap` là mutable và không được đồng bộ, nhiều luồng cùng cập nhật sẽ gây race condition. `collect` để thư viện Stream quản lý việc tạo và ghép vùng tích lũy theo hợp đồng.

Chúng ta không dùng `reduce` với một `Report` mutable làm identity, vì kiểu reduction đó có những ràng buộc khác và dễ sai khi identity bị chia sẻ. `collect` là công cụ phù hợp với việc xây dựng container có thể thay đổi.

## 8. Kiểm chứng các bất biến của báo cáo

Ngoài việc nhìn kết quả in ra, hãy xác định các bất biến có thể kiểm tra tự động.

### 8.1. Tổng dòng phải bằng số dòng hợp lệ cộng số dòng lỗi

~~~text
totalLines = validLines + invalidLines
~~~

Nếu bất biến này không đúng, logic phân loại đã bỏ sót hoặc đếm lại dòng.

### 8.2. Tổng yêu cầu của các dịch vụ bằng tổng dòng hợp lệ

~~~text
sum(service.requests) = validLines
~~~

Mỗi sự kiện hợp lệ thuộc đúng một dịch vụ.

### 8.3. Tổng số lỗi trong từng dịch vụ bằng số sự kiện ERROR

~~~text
sum(service.errors) = errorEvents
~~~

Điều này đúng vì báo cáo đếm lỗi chỉ với bản ghi hợp lệ và chỉ khi `level == ERROR`.

### 8.4. Độ trễ phải không âm và bình quân có cơ sở

Với mỗi dịch vụ có `requests > 0`:

~~~text
0 <= maxLatencyMs <= totalLatencyMs
averageLatencyMs = totalLatencyMs / requests
~~~

Trong dự án, độ trễ đầu vào luôn không âm nên giá trị lớn nhất và tổng có quan hệ như trên. Nếu mở rộng sang số đo âm như độ lệch nhiệt độ, bất biến này không còn áp dụng.

Không dùng `double` để **cộng** độ trễ khi đầu vào là số nguyên mili-giây; tổng ở đây dùng `long` với `Math.addExact` để phát hiện tràn. Việc chuyển sang `double` chỉ phục vụ **hiển thị trung bình** và có thể chấp nhận sai số biểu diễn khi định dạng hai chữ số; nếu nghiệp vụ cần số thập phân chính xác, dùng `BigDecimal` và quy tắc làm tròn rõ ràng.

## 9. Khi nào một dòng được coi là không hợp lệ?

Parser chủ động phân biệt các dạng lỗi:

| Đầu vào | Kết quả | Nguyên nhân |
| --- | --- | --- |
| `2026-11-18T08:00:00Z\|api\|INFO\|10` | Hợp lệ | Đủ bốn trường và giá trị hợp lệ |
| `broken` | Không hợp lệ | Không đủ trường |
| `2026-11-18T08:00:00Z\|\|INFO\|10` | Không hợp lệ | Mã dịch vụ rỗng |
| `2026-11-18T08:00:00Z\|api\|DEBUG\|10` | Không hợp lệ | Level không được hỗ trợ |
| `2026-11-18T08:00:00Z\|api\|INFO\|-2` | Không hợp lệ | Độ trễ âm |
| `2026-11-18T08:00:00Z\|api\|INFO\|abc` | Không hợp lệ | Độ trễ không phải số nguyên |
| `2026-99-18T08:00:00Z\|api\|INFO\|10` | Không hợp lệ | Timestamp không thể parse |
| Dòng rỗng | Không hợp lệ | Không đúng bốn trường |

Các ví dụ trên dùng ký tự phân cách `|`; dấu gạch chéo đứng trước dấu đó trong bảng chỉ là ký hiệu để Markdown hiển thị đúng cột.

### Không nên nuốt lỗi I/O trong parseLine

Parser chỉ xử lý **nội dung một dòng đã được đọc thành công**. Nếu Stream đọc tệp gặp lỗi giải mã hoặc I/O, lỗi thuộc **tầng nguồn**, không phải một LogEvent sai. Bọc toàn bộ `analyze` trong một `catch(Exception)` rồi trả `new Report()` có thể biến một báo cáo thất bại thành báo cáo “0 sự kiện”, rất nguy hiểm.

Nếu ứng dụng cần cho phép bỏ qua lỗi đầu vào ở cấp tệp, phải có trạng thái báo cáo riêng như `PARTIAL` hoặc `FAILED`, không dùng im lặng một báo cáo thành công giả.

## 10. Đóng nguồn đúng vòng đời kể cả khi dừng sớm

Một phiên bản khác chỉ cần kiểm tra **có sự kiện ERROR trong tệp hay không**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static boolean hasErrorMarker(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines.anyMatch(
                line -> line.contains("|ERROR|"));
    }
}
~~~

`anyMatch` có thể dừng sớm; việc ra khỏi `try` vẫn đóng Stream. Tuy nhiên, ví dụ này chỉ tìm marker văn bản, **không xác nhận** level ở đúng vị trí và các trường còn lại hợp lệ. Nếu yêu cầu nghiệp vụ là “có sự kiện `ERROR` hợp lệ”, thay predicate bằng parser:

~~~java
static boolean hasValidError(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines.map(LargeLogAnalyzer::parseLine)
                .anyMatch(event ->
                        event != null &&
                        event.level() == Level.ERROR);
    }
}
~~~

Ở đây `Level` là enum lồng trong `LargeLogAnalyzer` của ví dụ đầy đủ, còn phương thức này có thể đặt trong cùng lớp. Short-circuit không phải lý do bỏ `try-with-resources`.

Đặc biệt, **`count()`/`toList()`/`collect()`/`findFirst()` không tự gọi `close()`**, kể cả khi đã tiêu thụ hết hoặc dừng trước khi hết tệp.

## 11. Lỗi tài nguyên phổ biến: trả Stream đã đóng

Đừng viết:

~~~java
// Sai: caller nhận một pipeline lazy phụ thuộc Stream đã đóng.
static Stream<String> badOpen(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines.filter(line -> !line.isBlank());
    }
}
~~~

`filter` là intermediate operation lazy. Trước khi caller gọi terminal operation, khối `try` đã kết thúc và Stream bị đóng.

Hai lựa chọn đúng:

**Lựa chọn A — Phương thức sở hữu Stream và trả kết quả đã tính:**

~~~java
static long countNonBlank(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

**Lựa chọn B — Phương thức trả Stream mở và giao trách nhiệm đóng cho caller:**

~~~java
/**
 * Caller sở hữu và phải đóng Stream được trả về.
 */
static Stream<String> openNonBlank(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8)
            .filter(line -> !line.isBlank());
}

// Phía caller:
try (Stream<String> lines = openNonBlank(path)) {
    long count = lines.count();
}
~~~

Trong dự án chính, chọn lựa A: phương thức `analyze(Path)` sở hữu nguồn và trả `Report` đã hoàn tất; caller không phải quản lý Stream.

Nếu cần trả dữ liệu lazy để caller quyết định pipeline, phải tài liệu hóa rõ quyền sở hữu. Không tạo Stream I/O rồi quên ai sẽ đóng nó.

## 12. Lỗi đọc tệp, lỗi đóng và phạm vi ngoại lệ

Với `Files.lines`, phải phân biệt:

- **`IOException` khi mở:** tệp không có, không đủ quyền, hoặc nguồn không thể mở.
- **`UncheckedIOException` khi đọc lazy:** lỗi I/O có thể phát sinh trong lúc `collect` đang yêu cầu dòng tiếp theo.
- **`ArithmeticException`:** phép `Math.addExact` phát hiện bộ đếm/tổng độ trễ vượt giới hạn `long`.
- **`RuntimeException` khác:** lỗi lập trình trong accumulator hoặc parser nếu có.

Ví dụ tầng gọi:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;

try {
    LargeLogAnalyzer.Report report =
            LargeLogAnalyzer.analyze(path);
    // Chỉ công bố report sau khi phân tích hoàn tất.
} catch (IOException | UncheckedIOException ex) {
    System.err.println("Không đọc được tệp: " + path);
    // Ghi log hoặc báo thất bại cho hệ thống gọi.
} catch (ArithmeticException ex) {
    System.err.println("Giá trị tổng hợp vượt giới hạn long");
}
~~~

`try-with-resources` thực hiện `close()` cả khi terminal operation ném lỗi. Nếu vừa có lỗi xử lý vừa có lỗi khi đóng, Java giữ lỗi xử lý làm ngoại lệ chính và có thể đính kèm lỗi đóng qua `getSuppressed()`.

Một hệ thống thực tế nên ghi nhận đường dẫn, nguyên nhân và trạng thái xử lý; không nên tiếp tục hiển thị kết quả thiếu dữ liệu như kết quả hoàn chỉnh.

## 13. Kiểm thử trước khi dùng tệp thật

Có thể xây bộ dữ liệu nhỏ bằng `List<String>` và dùng **cùng logic accumulator** để kiểm thử. Không cần tệp lớn để kiểm tra phép cộng hoặc quy tắc parse.

~~~java
import java.util.List;

List<String> sample = List.of(
        "2026-11-18T08:00:00Z|checkout|INFO|120",
        "2026-11-18T08:00:01Z|search|WARN|45",
        "2026-11-18T08:00:02Z|checkout|ERROR|310",
        "not-a-log-line",
        "2026-11-18T08:00:03Z|search|INFO|20",
        "2026-11-18T08:00:04Z|checkout|WARN|-1"
);

LargeLogAnalyzer.Report report = sample.stream()
        .collect(
                LargeLogAnalyzer.Report::new,
                LargeLogAnalyzer.Report::acceptLine,
                LargeLogAnalyzer.Report::merge
        );

if (report.totalLines != 6L ||
        report.validLines != 4L ||
        report.invalidLines != 2L ||
        report.errorEvents != 1L ||
        report.warningEvents != 1L) {
    throw new AssertionError("Sai thống kê chung");
}

if (report.byService.get("checkout").totalLatencyMs != 430L) {
    throw new AssertionError("Sai tổng độ trễ checkout");
}
~~~

Ví dụ này giả định mã kiểm thử được đặt cùng package hoặc trong bối cảnh truy cập được các thành phần package-private của `LargeLogAnalyzer`.

### Bộ ca kiểm thử cần có

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Tệp rỗng | Tất cả bộ đếm bằng 0, Map dịch vụ rỗng |
| Một dòng hợp lệ | Tổng dòng và hợp lệ bằng 1, đúng service |
| Một dòng sai định dạng | Tổng dòng bằng 1, invalid bằng 1 |
| Dòng rỗng, trường thiếu hoặc dư | Parser phân loại đúng, không ném lỗi bất thường |
| Timestamp hỏng, level không hỗ trợ | Được tính invalid |
| Độ trễ âm, không phải số, hoặc vượt `long` | Được tính invalid |
| Nhiều dòng cùng dịch vụ | Gộp count, errors, sum, max đúng |
| Nhiều dịch vụ | Không trộn khóa thống kê |
| Tệp không tồn tại | Có lỗi đọc, không tạo báo cáo thành công giả |
| Tệp lớn hơn bộ nhớ sẵn có | Không giữ tất cả dòng, vẫn cần đo bộ nhớ thực |
| Nguồn bị lỗi khi duyệt | Lỗi đi ra ngoài đúng, resource vẫn được đóng |
| Các dịch vụ lặp nhiều lần | Bộ nhớ không tăng theo số lần xuất hiện của cùng khóa |

Không nên chỉ kiểm tra tổng số dòng. Một chương trình có thể đếm đúng `totalLines` nhưng ghi nhầm số liệu giữa các dịch vụ hoặc nuốt lỗi I/O.

## 14. Bổ sung test cho vòng đời tài nguyên

Với nguồn I/O, tính đúng không chỉ nằm ở dữ liệu báo cáo. Cần kiểm tra **đóng tài nguyên khi hoàn thành và khi lỗi**.

Một mô phỏng không cần truy cập tệp thật:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

AtomicBoolean closed = new AtomicBoolean(false);

try (Stream<String> lines = List.of("a", "b").stream()
        .onClose(() -> closed.set(true))) {

    long count = lines.count();
    System.out.println(count); // 2
}

System.out.println(closed.get()); // true
~~~

`onClose` minh họa thời điểm đóng Stream. Không nên suy rằng `count()` tự đóng; chính `try-with-resources` gọi `close()` khi ra khỏi khối.

Để kiểm tra đường đi có lỗi:

~~~java
AtomicBoolean closed = new AtomicBoolean(false);

try (Stream<String> lines = Stream.of("x")
        .onClose(() -> closed.set(true))) {

    throw new IllegalStateException("processing failed");
} catch (IllegalStateException ex) {
    // Lỗi xử lý được báo ra, nhưng close handler vẫn đã chạy.
}

System.out.println(closed.get()); // true
~~~

Đây là kiểm thử mô phỏng **cơ chế đóng**, không chứng minh bản thân `Files.lines` đã đóng file handle ở mọi hệ điều hành. Với tài nguyên thực, kiểm thử tích hợp có thể mở/đọc tệp theo những đường đi khác nhau và giám sát file descriptor/handle khi điều kiện môi trường cho phép.

## 15. Có nên dùng parallelStream cho tệp lớn?

**Không mặc định.** Một tệp lớn không tự động trở thành công việc dễ chia song song.

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {

    Report report = lines.parallel().collect(
            Report::new,
            Report::acceptLine,
            Report::merge
    );
}
~~~

Về nguyên tắc, `Stream.collect` có thể tích lũy vào những `Report` trung gian độc lập rồi gộp bằng `merge`. Các phép cộng số nguyên dùng `Math.addExact` và phép lấy `max` có ý nghĩa kết hợp khi giá trị không vượt giới hạn. Tuy nhiên, chạy song song còn phụ thuộc vào khả năng chia của nguồn, cách xử lý lỗi và chi phí gộp Map.

**Phiên bản chuẩn của dự án dùng Stream tuần tự.** Chỉ cân nhắc song song sau khi:

1. Đã chứng minh `Report.merge` đúng với nhiều cách phân chia dữ liệu.
2. Tất cả mapper/accumulator tránh trạng thái dùng chung ngoài vùng tích lũy.
3. Không cần thứ tự xử lý bản ghi để tính thống kê hiện tại.
4. Đã benchmark với tệp đủ lớn, nhiều dịch vụ và dữ liệu thực tế.
5. Đã xác định giới hạn CPU, I/O, bộ nhớ và xử lý lỗi.

Đặc biệt, `Files.lines` có thể có khả năng tách nguồn khác nhau tùy cách đọc tệp và charset. Song song hóa việc phân tích không bảo đảm tăng tốc nếu nút thắt là tốc độ đọc ổ đĩa hoặc chi phí tạo lô dữ liệu.

**Sai lầm cần tránh:**

~~~java
Report shared = new Report();

// Không an toàn: nhiều task sửa HashMap và bộ đếm chung.
try (Stream<String> lines = Files.lines(path)) {
    lines.parallel().forEach(shared::acceptLine);
}
~~~

`Report` không phải cấu trúc concurrent. Dùng collector thích hợp hoặc giữ pipeline tuần tự, không thêm `synchronized` một cách cơ học để che vấn đề thiết kế.

## 16. Mở rộng: báo cáo nhiều tệp trong một thư mục

Nếu cần phân tích nhiều tệp, phải quản lý **hai cấp tài nguyên**: Stream liệt kê thư mục và Stream đọc từng tệp.

Một thiết kế dễ kiểm soát là thu danh sách đường dẫn hữu hạn từ thư mục, **đóng Stream liệt kê**, rồi xử lý từng tệp độc lập:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<Path> logFiles(Path dir) throws IOException {
    try (Stream<Path> paths = Files.list(dir)) {
        return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName()
                        .toString().endsWith(".log"))
                .sorted()
                .toList();
    }
}
~~~

Caller có thể duyệt `List<Path>` và gọi `LargeLogAnalyzer.analyze(path)` cho từng tệp. Mỗi lần gọi tự đóng Stream đọc file.

Nếu cần một báo cáo gộp:

~~~java
LargeLogAnalyzer.Report combined = new LargeLogAnalyzer.Report();

for (Path file : logFiles(directory)) {
    LargeLogAnalyzer.Report oneFile =
            LargeLogAnalyzer.analyze(file);

    combined.merge(oneFile);
}
~~~

Ở đây `directory` là đường dẫn thư mục của caller. `combined` là accumulator ngoài Stream, được sử dụng **tuần tự**; không có nhiều thread cùng sửa nó. Chỉ nên công bố báo cáo cuối sau khi tất cả tệp đã được phân tích thành công.

Việc thu danh sách đường dẫn làm bộ nhớ tăng theo **số tệp**. Nếu thư mục có lượng tệp khổng lồ, cân nhắc xử lý từng `Path` ngay trong phạm vi `Files.list` với quản lý lỗi và quyền sở hữu rõ ràng.

## 17. Hạn chế và quyết định thiết kế trong ứng dụng thật

Dự án chủ động đơn giản hóa một số vấn đề. Trước khi triển khai production, cần quyết định:

### 17.1. Định dạng log

Nếu log là CSV có dấu phẩy/quote, JSON Lines hoặc định dạng nhị phân, đừng dựa vào `String.split("\\|")`. Dùng parser đúng đặc tả và quyết định dòng quá dài hoặc payload chứa dòng mới được xử lý thế nào.

### 17.2. Dữ liệu nhạy cảm

Không tự đưa nguyên văn dòng log vào báo cáo lỗi nếu dòng có thể chứa mã truy cập, email, token hoặc dữ liệu cá nhân. Chỉ lưu những trường được phép, giới hạn độ dài mẫu lỗi và áp dụng chính sách làm mờ dữ liệu.

### 17.3. Chất lượng số liệu

`Math.addExact` cho biết khi tổng `long` tràn, nhưng không tự sửa dữ liệu. Với dữ liệu có thể vượt giới hạn, cân nhắc `BigInteger` hoặc chiến lược thống kê khác. Với latency trung bình cần chính xác theo thập phân, dùng `BigDecimal` và `RoundingMode` rõ ràng.

### 17.4. Giới hạn số khóa và bộ nhớ

Một Map có một mục cho mỗi service. Nếu service là giá trị sinh động theo request hoặc user, số lượng khóa có thể rất lớn. Khi đó cần giới hạn cardinality, nhóm bớt theo tiêu chí hợp lệ hoặc tổng hợp ngoài bộ nhớ.

### 17.5. Tệp đang được ghi đồng thời

Bài học giả định tệp đầu vào là một snapshot ổn định trong lúc phân tích. `Files.lines` không tự cung cấp hợp đồng snapshot nhất quán khi một tiến trình khác liên tục ghi/sửa tệp. Cần quy trình tách tệp log, snapshot hoặc hợp đồng khóa dữ liệu nếu báo cáo yêu cầu nhất quán.

### 17.6. Phát hành báo cáo

Không ghi đè báo cáo chính thức khi việc phân tích còn dở. Nếu yêu cầu xuất JSON/CSV, nên tạo đầu ra tạm, chỉ công bố kết quả sau khi đọc và đóng nguồn thành công, rồi xử lý việc ghi đích theo cơ chế an toàn với lỗi/ghi dở.

## 18. Nhiệm vụ nâng cao theo từng mức

| Mức | Nhiệm vụ | Tiêu chí đạt |
| --- | --- | --- |
| Cơ bản | Đọc một tệp, đếm hợp lệ/lỗi, đóng nguồn | Đúng dữ liệu mẫu; tệp luôn được đóng |
| Trung bình | Tính thống kê `WARN`/`ERROR` và latency theo dịch vụ | Bất biến ở phần 8 đúng |
| Trung bình | Ghi nhận tối đa N ví dụ dòng lỗi | Không giữ mọi dòng lỗi; có giới hạn bộ nhớ |
| Khá | Thống kê theo `(service, level)` hoặc theo ngày UTC | Khóa tổng hợp không gây trộn dữ liệu |
| Khá | Phân tích nhiều tệp và tổng hợp báo cáo | Từng Stream và Stream liệt kê được đóng |
| Khó | Tách parser bằng `ParseResult` thay `null` | Phân biệt mã lỗi, không nuốt lỗi I/O |
| Khó | So sánh pipeline tuần tự và song song | Kết quả đúng hợp đồng, có benchmark phù hợp |
| Khó | Xử lý đầu vào với hàng triệu khóa phân biệt | Có chiến lược memory/cardinality hợp lý |

### Mở rộng A — Giữ N mẫu dòng lỗi

Thêm một danh sách nhỏ vào `Report`:

~~~java
private static final int MAX_SAMPLES = 10;
private final java.util.List<String> invalidSamples =
        new java.util.ArrayList<>();
~~~

Khi gặp dòng lỗi, chỉ thêm nếu danh sách còn chỗ:

~~~java
if (invalidSamples.size() < MAX_SAMPLES) {
    invalidSamples.add(line);
}
~~~

Nhưng phải lưu ý **dòng có thể rất dài** hoặc chứa dữ liệu nhạy cảm. Hãy giới hạn số ký tự và làm mờ thông tin cần thiết, đồng thời xác định rõ thứ tự và quy tắc chọn mẫu khi gộp hai báo cáo trung gian. Không chỉ giới hạn số lượng mẫu mà bỏ qua kích thước của từng mẫu.

### Mở rộng B — Thời gian xử lý theo ngày

Từ `Instant` của `LogEvent`, có thể lấy ngày UTC:

~~~java
java.time.LocalDate day = event.timestamp()
        .atZone(java.time.ZoneOffset.UTC)
        .toLocalDate();
~~~

Nếu nhóm theo ngày, cần xác định rõ múi giờ nghiệp vụ. UTC và giờ địa phương có thể cho **ngày khác nhau** đối với sự kiện gần ranh giới nửa đêm. Đừng trộn timestamp UTC với ngày địa phương một cách ngầm định.

### Mở rộng C — Kịch bản lỗi tài nguyên

Thiết kế phép thử cho trường hợp file thiếu, file bị từ chối quyền truy cập và thao tác xử lý ném exception. Mục tiêu là chứng minh rằng chương trình không để nguồn mở và **không công bố kết quả giả khi thất bại**.

## 19. Tiêu chí nghiệm thu dự án

Trước khi coi bộ phân tích hoàn thiện, hãy kiểm tra:

- [ ] Đầu vào có định dạng được mô tả, parser không chấp nhận ngầm giá trị ngoài hợp đồng.
- [ ] Dữ liệu mẫu cho đúng `total=6, valid=4, invalid=2, warnings=1, errors=1`.
- [ ] `checkout` có 2 yêu cầu, tổng 430 ms, lớn nhất 310 ms; `search` có 2 yêu cầu, tổng 65 ms.
- [ ] Tệp rỗng, dòng lỗi, số âm và dữ liệu trùng khóa được xử lý đúng.
- [ ] Không gọi `Files.readAllLines` hoặc `Stream.toList` để giữ toàn bộ log lớn.
- [ ] `Files.lines` được mở, duyệt và đóng trong `try-with-resources`.
- [ ] Có đường đi xử lý khi `Files.lines` hoặc terminal operation ném lỗi I/O.
- [ ] Bộ đếm/tổng không bị tràn âm thầm; có quyết định rõ khi gặp `ArithmeticException`.
- [ ] Không dùng `parallel().forEach(...)` để sửa `HashMap` hoặc bộ đếm chung.
- [ ] Bộ nhớ được đánh giá theo số khóa phân biệt và kích thước dòng lớn nhất, không chỉ số dòng.
- [ ] Báo cáo chỉ được sử dụng sau khi phân tích hoàn tất và nguồn đã đóng.
- [ ] Có kiểm thử tích hợp phù hợp với môi trường chạy; benchmark hiệu năng được thực hiện tách biệt kiểm thử đúng.

## 20. Bài tập tự kiểm tra

**Bài 1.** Vì sao `Files.readAllLines(path)` không phải lựa chọn mặc định cho tệp log rất lớn?

**Đáp án:** Nó vật hóa toàn bộ các dòng thành `List<String>`, nên bộ nhớ tăng theo kích thước dữ liệu. Dùng `Files.lines` với một collector tổng hợp giúp không giữ tất cả dòng khi chỉ cần thống kê.

**Bài 2.** Nếu bộ phân tích thấy 10 dòng, trong đó 7 hợp lệ và 3 sai định dạng, các bất biến cơ bản là gì?

**Đáp án:** `totalLines = 10`, `validLines = 7`, `invalidLines = 3` và tổng `requests` của mọi dịch vụ là 7.

**Bài 3.** `lines.filter(...).findFirst()` đã trả về, có thể bỏ `close()` không?

**Đáp án:** Không. Short-circuit dừng pipeline nhưng không tự đóng tài nguyên I/O. Dùng `try-with-resources` bao quanh việc tạo Stream và terminal operation.

**Bài 4.** Vì sao không dùng `Report shared = new Report(); lines.parallel().forEach(shared::acceptLine)`?

**Đáp án:** Nhiều tác vụ sẽ sửa các bộ đếm và `HashMap` mutable dùng chung. Nó không an toàn và có thể làm sai kết quả. Dùng `collect` với vùng tích lũy riêng hoặc giữ pipeline tuần tự.

**Bài 5.** Nếu có một triệu dòng nhưng chỉ ba dịch vụ, bộ nhớ của thiết kế sẽ tăng tỷ lệ với số dòng không?

**Đáp án:** Không theo số dòng **đã hoàn tất xử lý**, miễn nguồn không giữ toàn bộ dòng và không có dòng quá dài; phần báo cáo giữ khoảng ba mục dịch vụ. Tuy nhiên, không thể tuyên bố giới hạn bộ nhớ tuyệt đối vì còn bộ đệm I/O, cấp phát trong parser và kích thước từng dòng.

**Bài 6.** Một file bắt đầu có dữ liệu hợp lệ rồi mất quyền truy cập trong lúc đọc. Có nên trả `Report` với những dòng đã xử lý được và ghi thành “thành công” không?

**Đáp án:** Không, trừ khi hệ thống có hợp đồng báo cáo một phần được đánh dấu rõ ràng. Với dự án này, lỗi I/O phải đi ra ngoài và caller không được công bố báo cáo hoàn chỉnh giả.

**Bài 7.** Nếu muốn thống kê theo ngày tại Việt Nam, nên dùng gì?

**Đáp án:** Chọn rõ múi giờ nghiệp vụ, ví dụ `ZoneId.of("Asia/Ho_Chi_Minh")`, chuyển `Instant` sang ngày của múi giờ đó rồi mới nhóm. Không lấy phần ngày UTC một cách vô thức nếu báo cáo yêu cầu ngày địa phương.

## 21. Ghi nhớ

- **Đặt nguồn I/O trong `try-with-resources`:** terminal operation như `collect`, `count` hay `findFirst` không tự đóng `Files.lines`.
- **Đọc một lượt, giữ thống kê:** dùng collector với vùng tích lũy có phạm vi rõ ràng thay vì vật hóa mọi dòng.
- **Tách lỗi dữ liệu khỏi lỗi hệ thống:** parse sai một dòng khác với I/O thất bại hoặc tràn số khi tổng hợp.
- **Thiết kế theo hợp đồng:** xác định định dạng, nhóm, đơn vị thời gian, cách tính số liệu, giới hạn số khóa và tính nhất quán nguồn.
- **Không chia sẻ accumulator mutable bừa bãi:** `collect` phù hợp với mutable reduction; chỉ cân nhắc song song khi combiner đúng và có kiểm thử/đo hiệu năng.
- **Phải giữ tài nguyên mở trong suốt pipeline lazy:** không trả về Stream đã bị đóng; ai mở nguồn thì phải đóng hoặc chuyển quyền sở hữu rõ ràng.
- **Tối ưu sau khi đúng:** kiểm tra kết quả mẫu, bất biến và vòng đời tài nguyên trước khi benchmark tệp lớn.

**Ý chính:** Một bộ phân tích tệp lớn đáng tin cậy không được đánh giá chỉ bằng khả năng đọc nhanh. Nó phải **đọc từng phần tử mà không giữ toàn bộ tệp, tổng hợp đúng, phân biệt lỗi bản ghi với lỗi I/O và bảo đảm đóng nguồn khi mọi đường đi kết thúc**. `Files.lines` kết hợp `try-with-resources` và collector được thiết kế đúng là nền tảng thực hành quan trọng để xây các pipeline Stream API an toàn trong ứng dụng thực tế.
