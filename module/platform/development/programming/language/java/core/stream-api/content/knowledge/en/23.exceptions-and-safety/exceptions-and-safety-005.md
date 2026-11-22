# Tránh nuốt ngoại lệ và giữ nguyên nguyên nhân gốc

Trong Java Stream API, một pipeline `filter`, `map`, `reduce` hoặc `collect` có thể đọc hàng nghìn phần tử trước khi gặp dữ liệu sai, sự cố I/O hoặc lỗi nghiệp vụ. Nếu đoạn xử lý chỉ `catch` rồi bỏ qua, ghi một dòng log không đủ thông tin hoặc trả giá trị mặc định để tiếp tục, hệ thống có thể **báo thành công dù kết quả đã thiếu hoặc sai**. Nguy hiểm hơn, nếu tạo ngoại lệ mới mà không truyền nguyên nhân gốc, người bảo trì mất stack trace của nơi thực sự phát sinh sự cố.

Bài học thuộc chương **Ngoại lệ và tính an toàn** của module `JAVA_STREAM_API`. Ta tập trung vào cách **không nuốt lỗi**, **giữ chuỗi nguyên nhân bằng `cause`**, giữ cả lỗi dọn dẹp bằng **suppressed exceptions**, đặt `try/catch` đúng ranh giới thực thi lazy, và lựa chọn rõ ràng giữa **fail-fast** với **lỗi được biểu diễn thành dữ liệu**. Các ví dụ kết nối với nguồn I/O, Collector tùy chỉnh, pipeline song song, quản lý tài nguyên và giới hạn về trạng thái/hiệu năng.

> Các ví dụ chính dùng Java 8 trở lên. Các câu lệnh minh họa ở cấp cao nhất cần đặt trong `main`, phương thức hoặc JShell; các lớp tiện ích có thể đặt ở tệp riêng. Những đoạn đánh dấu **SAI** chỉ dùng để nhận diện anti-pattern, không phải mã nên đưa vào ứng dụng.

## 1. “Nuốt ngoại lệ” thực sự là gì?

*Nuốt ngoại lệ* (*exception swallowing*) là việc bắt một lỗi rồi **làm mất tín hiệu thất bại**, khiến tầng gọi không biết hoạt động đã không hoàn tất như mong muốn.

Ví dụ rất nguy hiểm:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> raw = Arrays.asList("10", "bad", "30");

List<Integer> values = raw.stream()
        .map(text -> {
            try {
                return Integer.parseInt(text);
            } catch (NumberFormatException ex) {
                return 0; // SAI: dữ liệu lỗi bị biến thành số 0 hợp lệ.
            }
        })
        .collect(Collectors.toList());

System.out.println(values); // [10, 0, 30]
```

Nếu nghiệp vụ tính tổng, kết quả sẽ là 40 và trông hoàn toàn hợp lệ. Không có thông tin cho biết `"bad"` đã bị ép thành số 0; thậm chí không thể phân biệt số 0 thực sự với 0 do lỗi.

Các biểu hiện khác của cùng vấn đề:

- `catch (Exception ignored) {}`: im lặng bỏ lỗi.
- `catch (...) { return null; }`: giấu thất bại trong một giá trị mơ hồ.
- `catch (...) { return Collections.emptyList(); }`: làm kết quả rỗng trông như dữ liệu không có bản ghi.
- `catch (...) { log(...); }` rồi **tiếp tục trả thành công** khi hợp đồng không cho phép.
- `catch (...) { throw new RuntimeException("failed"); }`: vẫn ném lỗi, nhưng **làm mất cause** và stack trace gốc.
- Bắt mọi loại lỗi, kể cả lỗi lập trình, rồi coi chúng là một bản ghi không hợp lệ.

**Không phải mọi trường hợp bỏ qua một bản ghi đều sai.** Nếu nghiệp vụ quy định các dòng trống được phép bỏ qua, `filter` chúng đi là hợp lệ. Vấn đề là **bỏ qua mà không có hợp đồng, không giữ số lượng hoặc không phân loại lỗi**.

## 2. Ba quyết định phải tách biệt

Khi một thao tác có thể thất bại, hãy hỏi ba câu:

1. **Đây là lỗi nào?** Dữ liệu đầu vào sai, khóa Map trùng, lỗi đọc tệp, bị ngắt tác vụ, hay bug?
2. **Tầng này có quyền xử lý không?** Có thể sửa, đổi sang kết quả nghiệp vụ, thử lại hợp lệ, hay phải truyền lên?
3. **Cần giữ bằng chứng gì?** Loại lỗi, `cause`, vị trí bản ghi, thông tin nguồn an toàn, `suppressed exceptions` và trạng thái hoàn tất.

| Tình huống | Chính sách thường phù hợp | Điều không nên làm |
| --- | --- | --- |
| Một dòng CSV có giá trị không phải số nhưng được phép báo lỗi từng dòng | `ParseOutcome` chứa lỗi, bộ đếm rejected | Trả 0 mà không đánh dấu |
| Không mở được tệp nguồn bắt buộc | Ném/lan truyền `IOException` với ngữ cảnh | Trả danh sách rỗng rồi báo thành công |
| Lỗi I/O khi đọc trong lambda | `UncheckedIOException` giữ `IOException` gốc | Chỉ ném `new RuntimeException("read failed")` |
| Khóa `toMap` trùng ngoài mong đợi | Fail-fast hoặc áp dụng merge rule được xác định | Dùng `(a,b) -> a` để che lỗi mà không kiểm tra ý nghĩa |
| Không có phần tử thỏa bộ lọc | `Optional.empty()` hoặc kết quả rỗng hợp lệ | Biến tình huống bình thường thành lỗi hạ tầng |
| Lỗi tạm thời có khả năng thử lại | Retry có giới hạn với nguồn mới và tác dụng phụ idempotent | Gọi lại terminal trên cùng Stream |
| Thread bị gián đoạn khi chờ I/O | Khôi phục interrupt hoặc xử lý tại tầng có thẩm quyền | Bắt `InterruptedException` rồi bỏ qua |

**Nguyên tắc:** xử lý lỗi chỉ là thành công khi tầng đó có thể **đảm bảo kết quả sau xử lý đúng hợp đồng**. Không xử lý được thì truyền lỗi lên, kèm nguyên nhân.

## 3. Phân biệt message, stack trace, cause và suppressed

Một `Throwable` trong Java mang nhiều thông tin:

| Thành phần | Cách truy cập | Ý nghĩa |
| --- | --- | --- |
| Loại exception | `ex.getClass()` | Phân loại lỗi |
| Message | `ex.getMessage()` | Mô tả ngắn, có thể thiếu ngữ cảnh |
| Stack trace | `ex.getStackTrace()` / log Throwable | Vị trí lời gọi và đường thực thi |
| Cause | `ex.getCause()` | Lỗi khác đã dẫn đến lỗi hiện tại |
| Suppressed | `ex.getSuppressed()` | Các lỗi bổ sung, thường là lúc đóng tài nguyên |

Ví dụ bọc lỗi đúng:

```java
import java.io.IOException;
import java.io.UncheckedIOException;

IOException original =
        new IOException("disk read failure");

UncheckedIOException wrapped =
        new UncheckedIOException("Cannot import orders", original);

System.out.println(wrapped.getCause() == original); // true
System.out.println(wrapped.getMessage());
// Cannot import orders
```

Tầng nghiệp vụ biết **nhập đơn hàng thất bại**, còn tầng chẩn đoán vẫn truy được **IOException gốc**.

Không nên làm:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot import orders"); // SAI
}
```

Hãy truyền `ex` vào constructor:

```java
catch (IOException ex) {
    throw new IllegalStateException(
            "Cannot import orders", ex);
}
```

`new IllegalStateException(message, ex)` giữ nguyên Throwable gốc ở `getCause()`. Điều đó quan trọng hơn việc sao chép `ex.getMessage()` vào một chuỗi mới.

## 4. Khi nào phải ném lại nguyên lỗi, khi nào được wrap?

**Truyền nguyên lỗi** khi kiểu exception và ngữ cảnh đã đủ nghĩa:

```java
try {
    processRecords();
} catch (IllegalArgumentException ex) {
    // Ví dụ muốn thêm metric ở một tầng ranh giới.
    metrics.recordInvalidRequest();
    throw ex; // Giữ nguyên object/stack trace gốc.
}
```

Đây là đoạn minh họa, giả định `processRecords` và `metrics` thuộc ứng dụng. Nếu metric có tác dụng phụ/không thread-safe, phải quản lý riêng; bản thân việc ghi metric không biến lỗi thành thành công.

**Wrap** khi thật sự cần **đổi abstraction**: lỗi I/O cụ thể của tầng nguồn được diễn đạt như lỗi nạp báo cáo của tầng nghiệp vụ.

```java
public final class ReportLoadException
        extends RuntimeException {

    public ReportLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Sử dụng:

```java
try {
    return loadReportFromSource(path);
} catch (java.io.UncheckedIOException ex) {
    throw new ReportLoadException(
            "Report load failed for source " + sourceId,
            ex);
}
```

Đoạn mã sử dụng `loadReportFromSource` và `sourceId` như các thành phần ứng dụng, không phải API chuẩn. Chuỗi cause trở thành:

```text
ReportLoadException: Report load failed for source ...
  caused by UncheckedIOException: cannot read ...
    caused by IOException: disk read failure
```

**Không wrap nhiều lần chỉ để thêm cùng một câu “failed”**. Một chuỗi bọc quá sâu với các message trùng nhau làm log khó đọc. Chỉ thêm context ở ranh giới có ý nghĩa nghiệp vụ; giữ nguyên cause nếu phải bọc.

## 5. Lazy evaluation: bắt lỗi quanh nơi terminal thực thi

Stream là lazy: lời gọi tạo pipeline không bảo đảm đã chạy lambda.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> raw = Arrays.asList("1", "bad", "3");

Stream<Integer> pipeline = raw.stream()
        .map(Integer::parseInt); // Chưa parse các phần tử.

try {
    List<Integer> parsed =
            pipeline.collect(Collectors.toList());
    System.out.println(parsed);
} catch (NumberFormatException ex) {
    System.err.println("Invalid integer: " + ex.getMessage());
}
```

Sai ranh giới:

```java
Stream<Integer> pipeline;

try {
    pipeline = raw.stream().map(Integer::parseInt);
} catch (NumberFormatException ex) {
    // Không bắt được lỗi parse sẽ xảy ra khi terminal chạy.
    throw new IllegalStateException("Parse failed", ex);
}

// Lỗi có thể xuất hiện ở đây:
pipeline.collect(Collectors.toList());
```

Một lưu ý tinh tế: ngay cả khi có terminal, **không phải mọi intermediate callback đều chắc chắn được thực thi**. `count()` có thể sử dụng `SIZED` để tính số lượng mà bỏ qua `map` nếu phép biến đổi không ảnh hưởng kích thước.

```java
long count = raw.stream()
        .map(Integer::parseInt) // Có thể không chạy!
        .count();

System.out.println(count); // Có thể là 3.
```

Đừng dùng `peek`, `map` cộng `count` hay một phép dừng sớm để ép kiểm tra tính hợp lệ của **tất cả** các dòng. Nếu đó là yêu cầu bắt buộc, cần xây terminal thu thập kết quả xác thực hoặc thiết kế một phép duyệt bảo đảm đánh giá tất cả giá trị cần kiểm tra.

## 6. Checked exception trong map: bọc đúng loại và giữ cause

Các giao diện chức năng như `Function<T,R>` không khai báo `throws IOException`. Vì vậy đoạn sau không biên dịch:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

// SAI: Files.size ném checked IOException.
List<Long> sizes = paths.stream()
        .map(Files::size)
        .collect(java.util.stream.Collectors.toList());
```

`paths` ở đây được giả định là `List<Path>`. Nếu chính sách là **fail-fast**, hãy bắt `IOException` trong lambda rồi bọc bằng `UncheckedIOException`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

static List<Long> fileSizes(List<Path> paths) {
    return paths.stream()
            .map(path -> {
                try {
                    return Files.size(path);
                } catch (IOException ex) {
                    throw new UncheckedIOException(
                            "Cannot read size of " + path, ex);
                }
            })
            .collect(Collectors.toList());
}
```

Ở ranh giới gọi:

```java
try {
    List<Long> sizes = fileSizes(paths);
    System.out.println(sizes);
} catch (UncheckedIOException ex) {
    IOException root = ex.getCause();

    // Trong ứng dụng: log exception/cause tại tầng xử lý lỗi.
    System.err.println("File operation failed: "
            + root.getClass().getSimpleName());
    throw ex; // Không báo thành công giả.
}
```

`UncheckedIOException` chỉ chấp nhận `IOException` làm cause. Nó không phải công cụ bọc tùy tiện mọi `RuntimeException` hoặc lỗi validation. Chọn kiểu ngoại lệ làm rõ vấn đề thay vì đẩy mọi thứ về `RuntimeException("failed")`.

Một lựa chọn khác, nếu API của bạn **được phép khai báo checked exception**, là đặt I/O ở một phương thức có `throws IOException` hoặc dùng vòng lặp thay vì ép mọi thao tác vào Stream. Cú pháp pipeline không quan trọng hơn hợp đồng lỗi rõ ràng.

## 7. Không trả null, 0 hoặc danh sách rỗng cho lỗi hạ tầng

Xem một hàm đọc tệp:

```java
// SAI: trả List rỗng nếu không đọc được tệp.
static List<String> unsafeRead(Path path) {
    try {
        return java.nio.file.Files.readAllLines(path);
    } catch (java.io.IOException ex) {
        return java.util.Collections.emptyList();
    }
}
```

Caller không thể phân biệt:

- Tệp tồn tại và thật sự không có dòng;
- Tệp không tồn tại;
- Hệ thống không có quyền đọc;
- Thiết bị lưu trữ gặp lỗi.

Một phiên bản hợp đồng rõ ràng hơn:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

static List<String> readRequiredFile(Path path)
        throws IOException {
    return Files.readAllLines(path, StandardCharsets.UTF_8);
}
```

Lựa chọn khác, khi API ở tầng cao bắt buộc không khai báo checked exception, là wrap nguyên nhân bằng `UncheckedIOException` hoặc một exception nghiệp vụ. **Không được biến lỗi không đọc được tệp thành “không có dữ liệu”** trừ khi hợp đồng nói rõ như vậy, chẳng hạn tệp tùy chọn không tồn tại được coi là cấu hình mặc định.

Cũng cần phân biệt **fallback được phép** với **fallback che lỗi**. Ví dụ một cấu hình tùy chọn có thể sử dụng giá trị mặc định **chỉ khi không có file**, nhưng không nhất thiết khi file hiện hữu bị hỏng hoặc không đọc được.

## 8. File.lines: lỗi mở nguồn và lỗi đọc lazy khác nhau

`Files.lines` có thể ném `IOException` khi mở nguồn, còn lỗi đọc trong khi duyệt có thể đi ra dưới dạng `UncheckedIOException`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countWarnings(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(s -> s.startsWith("WARN:"))
                .count();
    }
}
```

Ở tầng gọi:

```java
import java.io.UncheckedIOException;

try {
    long count = countWarnings(path);
    System.out.println("Warnings: " + count);
} catch (UncheckedIOException ex) {
    // Lỗi có thể phát sinh trong lúc duyệt lazy.
    throw new IllegalStateException(
            "Failed while reading log content", ex);
} catch (java.io.IOException ex) {
    // Lỗi checked có thể phát sinh lúc mở nguồn.
    throw new IllegalStateException(
            "Failed to open log source", ex);
}
```

Thực tế cũng có thể có lỗi do `filter` hoặc downstream ném RuntimeException. **Không bắt chung mọi RuntimeException rồi gọi nó là lỗi I/O**.

### Phải đóng nguồn ngay cả khi lỗi

`try-with-resources` vẫn gọi `close` khi thân xử lý ném ngoại lệ. Terminal như `collect`, `count`, `findFirst` hoặc `forEach` **không tự đóng** Stream từ `Files.lines`.

Nguồn `BufferedReader.lines()` lại có quyền sở hữu khác: nếu tự tạo `BufferedReader`, hãy đóng chính Reader đó. Đừng mặc định việc đóng Stream tạo từ Reader đồng nghĩa Reader đã được đóng.

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

    long count = reader.lines()
            .filter(s -> !s.isEmpty())
            .count();
    System.out.println(count);
}
```

Nếu trả Stream lazy cho caller, phải chuyển rõ trách nhiệm đóng nguồn. **Không** mở Reader trong `try`, trả `reader.lines()` ra ngoài và để caller tiêu thụ sau khi Reader đã đóng.

## 9. Không dùng catch(Exception) để che lỗi lập trình

Đoạn sau gần như chắc chắn gây khó khăn khi vận hành:

```java
// SAI: mọi lỗi đều bị thay bằng giá trị mặc định.
static int parseOrZero(String text) {
    try {
        return Integer.parseInt(text);
    } catch (Exception ex) {
        return 0;
    }
}
```

Nó gom chung `NumberFormatException`, các trường hợp null và nhiều lỗi khác rồi tuyên bố thành công.

Nếu một **giá trị đầu vào không hợp lệ** là lỗi phải dừng, bắt cụ thể và thêm context:

```java
static int parseRequiredScore(String text, int lineNumber) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid score at line " + lineNumber, ex);
    }
}
```

Hàm trên không nuốt exception: caller nhận `IllegalArgumentException` có thông báo nghiệp vụ và `NumberFormatException` ban đầu trong `getCause()`.

Nếu điểm được phép vắng mặt, hãy có chính sách khác tường minh, ví dụ `OptionalInt.empty()` **chỉ** cho tình huống được phép vắng. Không dùng `Optional.empty` thay thế cho lỗi hệ thống không thể phục hồi.

### Không catch(Throwable) để “đảm bảo luôn chạy”

`Throwable` bao gồm cả `Error` như `OutOfMemoryError` và `StackOverflowError`. Những lỗi này thường **không phải dữ liệu sai có thể bỏ qua**.

```java
// SAI:
// try {
//     ...
// } catch (Throwable ignored) {
//     return Collections.emptyList();
// }
```

Chỉ bắt những loại lỗi mà tầng hiện tại có chính sách xử lý hợp lệ. Nếu lỗi vượt ngoài phạm vi đó, để nó lan truyền tới tầng quản lý vòng đời/tác vụ.

## 10. Khi bị ngắt tác vụ, đừng nuốt InterruptedException

Một số tác vụ blocking trong pipeline có thể ném `InterruptedException`. Functional interface của Stream không khai báo checked exception này, nên không thể đơn giản bỏ qua.

```java
import java.util.concurrent.TimeUnit;
import java.util.List;
import java.util.stream.Collectors;

List<String> results = tasks.stream()
        .map(task -> {
            try {
                TimeUnit.MILLISECONDS.sleep(10L);
                return task;
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while processing task " + task,
                        ex);
            }
        })
        .collect(Collectors.toList());
```

`tasks` là `List<String>` giả định trong ứng dụng. Đoạn trên chỉ minh họa cách giữ `cause` và **khôi phục interrupt flag** khi một functional interface không cho ném checked exception trực tiếp. Trong tác vụ nền thực tế, tầng điều phối có thể cần một cơ chế hủy tác vụ riêng.

Không nên làm:

```java
catch (InterruptedException ignored) {
    return task; // SAI: giả vờ xử lý đã hoàn tất.
}
```

Đặc biệt với parallel stream, cơ chế dừng một pipeline không đồng nghĩa mọi tác vụ blocking của bạn được tự động interrupt. Không dùng `parallel()` như công cụ quản lý cancellation hoặc timeout cho nguồn I/O mà chưa có thiết kế riêng.

## 11. Chọn fail-fast hay ghi lỗi thành dữ liệu?

Đôi khi một tập dữ liệu có vài bản ghi hỏng và ứng dụng được phép xử lý phần còn lại. **Không ném exception cho từng bản ghi** có thể là chính sách đúng — miễn việc chuyển lỗi thành dữ liệu là **có chủ ý và kiểm toán được**.

Ta định nghĩa một kiểu `ParseOutcome` Java 8 để giữ số dòng, giá trị hợp lệ hoặc `cause` của thất bại.

```java
public final class ParseOutcome {
    private final int line;
    private final Integer value;
    private final RuntimeException error;

    private ParseOutcome(
            int line, Integer value, RuntimeException error) {
        this.line = line;
        this.value = value;
        this.error = error;
    }

    public static ParseOutcome parse(int line, String raw) {
        if (raw == null) {
            return new ParseOutcome(
                    line, null,
                    new IllegalArgumentException("Missing value"));
        }

        String normalized = raw.trim();
        if (normalized.isEmpty()) {
            return new ParseOutcome(
                    line, null,
                    new IllegalArgumentException("Blank value"));
        }

        try {
            return new ParseOutcome(
                    line, Integer.parseInt(normalized), null);
        } catch (NumberFormatException ex) {
            return new ParseOutcome(line, null, ex);
        }
    }

    public boolean isSuccess() {
        return error == null;
    }

    public int line() {
        return line;
    }

    public int value() {
        if (!isSuccess()) {
            throw new IllegalStateException(
                    "No parsed value at line " + line, error);
        }
        return value;
    }

    public RuntimeException error() {
        return error;
    }
}
```

Ở đây lỗi parse được **lưu nguyên object `NumberFormatException`** trong `ParseOutcome.error()`. Nó không bị đổi thành 0 và không mất thông tin nguyên nhân.

Với dòng trống và null, ứng dụng chủ động tạo `IllegalArgumentException` mô tả tình huống sai. Tùy yêu cầu, cũng có thể lưu mã lỗi/loại lỗi thay vì giữ Throwable trong hàng triệu đối tượng nếu chi phí bộ nhớ là vấn đề.

### Dùng ParseOutcome trong pipeline

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<String> raw = Arrays.asList(
        "10", "bad", "-3", "", null
);

List<ParseOutcome> outcomes =
        IntStream.range(0, raw.size())
                .mapToObj(i ->
                        ParseOutcome.parse(i + 1, raw.get(i)))
                .collect(Collectors.toList());

long success = outcomes.stream()
        .filter(ParseOutcome::isSuccess)
        .count();

long failure = outcomes.stream()
        .filter(o -> !o.isSuccess())
        .count();

System.out.println(success); // 2
System.out.println(failure); // 3
```

Báo cáo lỗi vẫn truy được số dòng và cause:

```java
for (ParseOutcome outcome : outcomes) {
    if (!outcome.isSuccess()) {
        System.err.println(
                "Line " + outcome.line()
                + " failed: "
                + outcome.error().getClass().getSimpleName());
    }
}
```

Trong vận hành thực tế, không nên log nội dung raw nếu có dữ liệu nhạy cảm. Để tránh ghi hàng triệu dòng lỗi, cần giới hạn số lỗi chi tiết được lưu/log và luôn giữ số lỗi tổng.

**Đây không phải “nuốt lỗi”.** Lỗi là một phần của mô hình dữ liệu đầu ra, đã được phân loại, đếm và có thể quyết định kết quả nhập liệu thành công một phần hay thất bại. Tầng gọi phải biết cách kiểm tra `failure`, thay vì chỉ nhìn số phần tử thành công.

## 12. Thu thập thống kê mà không giữ mọi exception trong bộ nhớ

Nếu chỉ cần tổng thành công, lỗi và tổng điểm, có thể dùng `collect` ba tham số với accumulator nhỏ:

```java
public final class ImportStats {
    private long accepted;
    private long rejected;
    private long sum;

    public void add(ParseOutcome outcome) {
        if (outcome.isSuccess()) {
            accepted++;
            sum += outcome.value();
        } else {
            rejected++;
        }
    }

    public void merge(ImportStats other) {
        accepted += other.accepted;
        rejected += other.rejected;
        sum += other.sum;
    }

    public long accepted() { return accepted; }
    public long rejected() { return rejected; }
    public long sum() { return sum; }
}
```

Áp dụng:

```java
ImportStats stats = IntStream.range(0, raw.size())
        .mapToObj(i -> ParseOutcome.parse(i + 1, raw.get(i)))
        .collect(
                ImportStats::new,
                ImportStats::add,
                ImportStats::merge);

System.out.println(stats.accepted()); // 2
System.out.println(stats.rejected()); // 3
System.out.println(stats.sum());      // 7
```

Điểm cần chú ý:

- Supplier `ImportStats::new` tạo bộ tích lũy mới cho mỗi nhánh nếu framework cần.
- Accumulator tăng đúng một trong hai bộ đếm `accepted`/`rejected`.
- Combiner `merge` cộng đủ mọi trường; không bỏ dữ liệu nhánh phải.
- Với nguồn cố định, `accepted + rejected == raw.size()`.
- Mẫu chỉ giữ thống kê `O(1)` theo số bản ghi, không giữ mọi `Throwable` để truy cứu.

Nếu cần cả thống kê lẫn ví dụ lỗi, thiết kế một bộ tích lũy **giới hạn danh sách lỗi mẫu** và giữ tổng số lỗi riêng. Không tích lũy exception vô hạn trong hệ thống ingest lâu dài. Số học `long` vẫn có giới hạn; chọn kiểu số/chính sách phát hiện tràn tùy quy mô.

## 13. Terminal operation cũng có thể ném lỗi

Không phải mọi ngoại lệ đều đến từ `map`. Một terminal `collect`, `reduce` hoặc `forEach` có thể thất bại do hợp đồng của chính phép toán.

### toMap khi khóa trùng

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, String> byLength =
        Arrays.asList("cat", "dog")
                .stream()
                .collect(Collectors.toMap(
                        String::length,
                        s -> s));
// IllegalStateException: khóa 3 bị trùng.
```

**Không nên** chữa lỗi bằng merge function tùy tiện `(oldValue, newValue) -> oldValue` nếu nghiệp vụ cần giữ cả hai bản ghi. Khi đó dùng `groupingBy`:

```java
import java.util.List;

Map<Integer, List<String>> grouped =
        Arrays.asList("cat", "dog")
                .stream()
                .collect(Collectors.groupingBy(String::length));

System.out.println(grouped.get(3)); // [cat, dog]
```

Nếu yêu cầu chỉ giữ một bản ghi theo quy tắc (ví dụ mới nhất theo timestamp), định nghĩa merge function dựa trên **thuộc tính dữ liệu và tie-breaker** thay vì dựa vào thứ tự nhánh parallel.

### reduce có thể ném ArithmeticException

```java
import java.util.Arrays;

int sum = Arrays.asList(Integer.MAX_VALUE, 1)
        .stream()
        .reduce(0, Math::addExact);
// ArithmeticException: integer overflow
```

`Math.addExact` giúp phát hiện tràn thay vì để tổng `int` vòng lại. Đừng bắt `ArithmeticException` rồi trả 0 nếu 0 cũng là một tổng có nghĩa. Hãy báo số liệu vượt miền hoặc nâng sang `long`/`BigInteger` theo hợp đồng nghiệp vụ.

Trên parallel reduction, các tổng trung gian có thể được nhóm khác nhau; phép cộng kiểm tra tràn có thể ném lỗi ở một cách nhóm nhưng không ở cách khác nếu một tổng trung gian vượt miền trong khi tổng toán học cuối cùng vẫn nằm trong miền. Nếu cần hành vi bất biến theo cách chia nhánh, chọn mô hình số học phù hợp.

### Collector tùy chỉnh

`supplier`, `accumulator`, `combiner` và `finisher` của Collector đều có thể ném runtime exception. Khi rà lỗi, hãy kiểm tra **cả bốn**, không chỉ mapper đầu vào. Việc một Collector có `CONCURRENT` hoặc chạy trên Stream parallel **không xóa** lỗi nghiệp vụ từ các hàm đó.

## 14. Giữ exception gốc khi thêm vị trí bản ghi

Một thông điệp `"For input string: abc"` chưa đủ để biết lỗi ở dòng nào. Có thể thêm bối cảnh trong wrapper nhưng vẫn giữ `cause`.

```java
public final class InputLineException
        extends RuntimeException {

    private final long lineNumber;

    public InputLineException(
            long lineNumber, String message, Throwable cause) {
        super(message, cause);
        this.lineNumber = lineNumber;
    }

    public long lineNumber() {
        return lineNumber;
    }
}
```

Ví dụ phân tích một List có thứ tự:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<String> raw = Arrays.asList("10", "abc", "30");

List<Integer> parsed = IntStream.range(0, raw.size())
        .mapToObj(i -> {
            String text = raw.get(i);
            try {
                return Integer.parseInt(text);
            } catch (NumberFormatException ex) {
                throw new InputLineException(
                        i + 1,
                        "Invalid integer at line " + (i + 1),
                        ex);
            }
        })
        .collect(Collectors.toList());
```

Caller vẫn có thể:

```java
try {
    runImport();
} catch (InputLineException ex) {
    System.err.println("Bad line: " + ex.lineNumber());
    System.err.println("Root type: "
            + ex.getCause().getClass().getSimpleName());
}
```

`runImport` ở đây là phương thức ứng dụng chứa pipeline ở trên. Với nguồn `List` được đánh chỉ số tường minh, số dòng ổn định. Với `parallelStream` từ tệp, **không** dùng một `int[]` hoặc `AtomicInteger` tăng trong `map` để giả làm số dòng theo encounter order; hãy gắn chỉ số bằng một bước đọc tuần tự có hợp đồng rõ ràng hoặc giữ record `(lineNumber, text)` ở đầu nguồn.

### Giảm lộ dữ liệu nhạy cảm

Ngay cả `NumberFormatException` gốc có thể chứa văn bản đầu vào trong message. Việc **giữ cause để chẩn đoán** không có nghĩa được phép ghi toàn bộ stack trace ra hệ thống log có phạm vi truy cập rộng. Phân quyền log, redaction và chỉ giữ metadata cần thiết là trách nhiệm của tầng vận hành.

## 15. onClose và suppressed exceptions: không để mất lỗi dọn dẹp

`try-with-resources` giúp đóng nguồn kể cả khi terminal operation ném lỗi. Nếu **cả xử lý lẫn đóng tài nguyên đều thất bại**, Java thường giữ ngoại lệ xử lý làm **primary** và gắn lỗi đóng tài nguyên vào `getSuppressed()`.

Ví dụ có thể chạy với Stream trong bộ nhớ:

```java
import java.util.stream.Stream;

try (Stream<String> lines = Stream.of("A")
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {

    lines.forEach(s -> {
        throw new IllegalArgumentException("parse failed");
    });

} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage()); // parse failed

    for (Throwable suppressed : ex.getSuppressed()) {
        System.out.println(suppressed.getMessage());
        // close failed
    }
}
```

Nhìn vào `getMessage()` của primary mà không kiểm tra `getSuppressed()` có thể bỏ sót thông tin rằng tài nguyên cũng không được dọn dẹp thành công.

**Điểm phân biệt quan trọng:**

- `getCause()` mô tả quan hệ **vì lỗi A nên có lỗi B**.
- `getSuppressed()` chứa **lỗi bổ sung** xảy ra trong lúc xử lý cùng sự cố, thường khi đóng.
- `onClose(...)` chỉ chạy khi `close()` được gọi, **không tự chạy sau mọi terminal operation**.
- Nếu không có lỗi ở thân `try` mà `close` thất bại, lỗi đóng có thể là ngoại lệ chính được ném ra.
- Không viết `finally { return defaultValue; }` vì `return` trong `finally` có thể che ngoại lệ từ khối `try`.

Một nguyên tắc thiết kế quan trọng là **log toàn bộ Throwable (khi bảo mật cho phép)** ở ranh giới xử lý lỗi, bởi formatter chuẩn thường thể hiện cause và suppressed. Đừng chỉ log `ex.getMessage()` rồi bỏ stack trace.

## 16. Không log rồi nuốt, cũng không log trùng ở mọi tầng

Có hai anti-pattern đối lập:

```java
// SAI: chỉ log rồi trả thành công giả.
try {
    importRequiredData();
} catch (RuntimeException ex) {
    logger.warning("Import failed: " + ex.getMessage());
}
return ImportStatus.SUCCESS;
```

và:

```java
// DỄ GÂY NHIỄU: mọi tầng log cùng một exception rồi rethrow.
catch (RuntimeException ex) {
    logger.log(java.util.logging.Level.SEVERE,
            "Import failed", ex);
    throw ex;
}
```

Đoạn thứ hai **không đánh mất lỗi**, nhưng nếu mọi tầng đều làm vậy, một sự cố có thể tạo nhiều bản log gần giống nhau. Thay vì thế:

- Ở tầng thấp: bắt đúng loại nếu cần thêm context, rồi `throw` với cause hoặc truyền nguyên lỗi.
- Ở ranh giới giao tiếp/tác vụ: **log một lần** với stack trace và thông tin an toàn, rồi chuyển thành response lỗi hoặc trạng thái thất bại phù hợp.
- Ở giao diện người dùng: trả thông báo dễ hiểu, không phơi bày stack trace/cause nhạy cảm.

Ví dụ logging tập trung:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

static final Logger LOG =
        Logger.getLogger("import-service");

static void runImportJob() {
    try {
        executeImport();
    } catch (ReportLoadException ex) {
        LOG.log(Level.SEVERE, "Import job failed", ex);
        // Thông báo lỗi lên scheduler/caller theo hợp đồng tác vụ.
        throw ex;
    }
}
```

`executeImport` là phương thức ứng dụng giả định. `LOG.log(Level.SEVERE, message, ex)` giữ Throwable thay vì chỉ một message. Việc ném lại ở đây phù hợp nếu scheduler cần nhận biết công việc thất bại; nếu giao thức có trạng thái lỗi chính thức, có thể chuyển đổi tại ranh giới đó.

## 17. Parallel stream: không dựa vào ngoại lệ “đầu tiên”

Một parallel pipeline có thể xử lý nhiều phần dữ liệu đồng thời:

```java
import java.util.stream.IntStream;

int result = IntStream.range(0, 1000)
        .parallel()
        .map(n -> {
            if (n == 200 || n == 700) {
                throw new IllegalArgumentException(
                        "Bad value: " + n);
            }
            return n;
        })
        .sum();
```

Trong trường hợp này:

1. Không bảo đảm lỗi của 200 sẽ được báo trước lỗi của 700.
2. Các tác vụ khác có thể đã hoàn thành một phần việc; không có rollback tự động.
3. Stack trace/cause có thể phản ánh lớp thực thi song song; đừng chỉ kiểm tra message.
4. Không bảo đảm tất cả lỗi từ mọi tác vụ đều được tập hợp để caller xem.
5. Catch bên ngoài terminal có thể xử lý lỗi được lan ra, nhưng không làm những side effect trước đó biến mất.

Không viết test:

```java
// SAI cho parallel pipeline trên:
// assertEquals("Bad value: 200", exception.getMessage());
```

Nếu ứng dụng phải báo **mọi** bản ghi sai, hãy biến lỗi dự kiến thành `ParseOutcome` hoặc kết quả có cấu trúc, rồi thu thập số lỗi. **Fail-fast** là cơ chế ngừng xử lý khi có lỗi, không phải một hệ thống tổng hợp đầy đủ mọi lỗi.

### Collectors an toàn không bảo đảm lambda vô hại

`Collectors.groupingByConcurrent` và `toConcurrentMap` có các bảo đảm đồng thời riêng. Nhưng classifier, value mapper hoặc merge function vẫn có thể ném exception. Nếu chúng tự ghi vào state mutable bên ngoài, việc collector là concurrent **không** tự khắc phục race condition.

Đừng dùng `parallel()` để “tự động retry” một mapper thất bại. Mỗi Stream vẫn chỉ có một lần tiêu thụ terminal theo hợp đồng.

## 18. Dừng sớm không phải cách xác thực tất cả phần tử

Các thao tác `findFirst`, `findAny`, `anyMatch`, `allMatch`, `limit` có thể **không cần duyệt hết nguồn**.

```java
import java.util.Arrays;

boolean found = Arrays.asList("100", "bad", "50")
        .stream()
        .anyMatch(s -> Integer.parseInt(s) >= 100);

System.out.println(found); // true, không cần parse "bad".
```

Một pipeline có `"bad"` nhưng không ném lỗi **không chứng minh** dữ liệu đã được xác thực toàn bộ.

```java
int first = Arrays.asList("7", "invalid")
        .stream()
        .map(Integer::parseInt)
        .findFirst()
        .orElseThrow(IllegalStateException::new);

System.out.println(first); // 7
```

Nếu nhu cầu là “kiểm tra mọi bản ghi trước khi nhập”, đừng dùng một terminal dừng sớm để chứng minh tính hợp lệ. Hãy chọn phép thu thập đủ dữ liệu cần kiểm tra hoặc một bước validation chuyên biệt. Với parallel stream, không giả định số lần gọi mapper đúng bằng số phần tử đầu ra khi có dừng sớm.

## 19. Retry đúng: tạo nguồn mới, giới hạn lần thử, không lặp tác dụng phụ

Một Stream sau khi đã tiêu thụ hoặc tiêu thụ thất bại **không dùng lại được**:

```java
import java.util.stream.Stream;

Stream<String> source = Stream.of("10", "20");
long first = source.count();

// SAI: source đã tiêu thụ rồi.
long second = source.count();
```

Đối với lỗi đọc tệp **tạm thời**, ví dụ sau minh họa retry tối đa hai lượt, mỗi lượt mở nguồn mới:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countWarningsWithOneRetry(Path path)
        throws IOException {

    IOException lastFailure = null;

    for (int attempt = 1; attempt <= 2; attempt++) {
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                    .filter(s -> s.startsWith("WARN:"))
                    .count();

        } catch (UncheckedIOException ex) {
            lastFailure = ex.getCause();
        } catch (IOException ex) {
            lastFailure = ex;
        }
    }

    throw new IOException(
            "Cannot count warnings after two attempts",
            lastFailure);
}
```

Đây là **mẫu minh họa**, không có delay/backoff, deadline hay cơ chế xác định lỗi có thể thử lại. Trong sản phẩm thật:

- Retry **chỉ những lỗi được xác định là tạm thời**; parse sai là lỗi dữ liệu, thử lại nguyên chuỗi đó không giúp ích.
- Có **giới hạn số lần và thời gian**, cân nhắc backoff.
- Đảm bảo đầu vào giữa các lượt là một snapshot hợp lệ nếu cần kết quả nhất quán.
- Nếu pipeline có ghi database/gửi request, xác định **idempotency** hoặc transaction trước khi retry.
- Giữ cause của lần cuối trong ngoại lệ tổng kết; có thể cần ghi lại các lần trước dưới dạng diagnostic/suppressed nếu phù hợp.

Không retry bằng cách gọi lại terminal trên một instance `Stream` cũ hoặc dùng Reader đã bị đóng.

## 20. Unit test: không chỉ kiểm tra “có ném lỗi”

Một phép kiểm thử tốt phải xác minh **loại lỗi**, **chuỗi cause**, **trạng thái đầu ra** và **đóng tài nguyên**, thay vì chỉ kiểm tra bất kỳ exception nào đó.

Ví dụ với **JUnit Jupiter** (dependency kiểm thử bên ngoài JDK):

```java
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExceptionSafetyTest {

    @Test
    void parseFailureKeepsOriginalCause() {
        IllegalArgumentException ex =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> parseRequiredScore("abc", 7)
                );

        assertTrue(ex.getMessage().contains("line 7"));
        assertInstanceOf(NumberFormatException.class,
                ex.getCause());
    }

    @Test
    void dataErrorsAreCountedInsteadOfIgnored() {
        java.util.List<String> raw =
                Arrays.asList("10", "bad", "-3", "", null);

        ImportStats stats = java.util.stream.IntStream
                .range(0, raw.size())
                .mapToObj(i ->
                        ParseOutcome.parse(i + 1, raw.get(i)))
                .collect(
                        ImportStats::new,
                        ImportStats::add,
                        ImportStats::merge);

        assertEquals(2L, stats.accepted());
        assertEquals(3L, stats.rejected());
        assertEquals(7L, stats.sum());
    }
}
```

`parseRequiredScore`, `ParseOutcome` và `ImportStats` được định nghĩa ở các phần trước. `assertInstanceOf` là tiện ích của một số phiên bản JUnit Jupiter hiện đại; nếu phiên bản bạn sử dụng không có, có thể thay bằng:

```java
assertTrue(ex.getCause() instanceof NumberFormatException);
```

Một bài test riêng cho `try-with-resources` và suppressed:

```java
import java.util.stream.Stream;

IllegalArgumentException ex;
try {
    try (Stream<String> source = Stream.of("x")
            .onClose(() -> {
                throw new IllegalStateException("close");
            })) {
        source.forEach(s -> {
            throw new IllegalArgumentException("body");
        });
    }
    throw new AssertionError("Expected processing failure");
} catch (IllegalArgumentException caught) {
    ex = caught;
}

if (ex.getSuppressed().length != 1
        || !"close".equals(
                ex.getSuppressed()[0].getMessage())) {
    throw new AssertionError("Suppressed close error missing");
}
```

**Lưu ý khi kiểm thử:** không phụ thuộc thông điệp cụ thể của JVM cho `NumberFormatException` hoặc kiểu wrapper chính xác mà framework parallel có thể thêm. Chỉ assert những điều **thuộc hợp đồng ứng dụng**. Với lỗi I/O, nên dùng fixture hoặc thành phần nguồn có thể điều khiển, thay vì cố gây race không ổn định.

## 21. Các lỗi phổ biến khi review code

| Anti-pattern | Hậu quả | Thay thế |
| --- | --- | --- |
| `catch (Exception ignored) {}` | Lỗi biến mất | Xử lý đúng hoặc ném lại |
| Bắt lỗi rồi trả `0`, `null`, empty List | Trộn lỗi với dữ liệu hợp lệ | Dùng `Result`/`Optional` đúng nghĩa hoặc fail-fast |
| `new RuntimeException("failed")` | Mất cause gốc | `new RuntimeException("context", ex)` |
| Chỉ log `ex.getMessage()` | Mất stack trace, cause và suppressed | Log Throwable tại ranh giới tin cậy |
| Log rồi trả `SUCCESS` | Giả mạo trạng thái hoàn thành | Báo thất bại theo hợp đồng |
| Log và rethrow ở mọi tầng | Nhiều log trùng lặp | Log tập trung, wrap khi cần |
| Catch mọi `Throwable` | Nuốt cả lỗi nghiêm trọng | Bắt ngoại lệ có thể xử lý |
| Nuốt `InterruptedException` | Mất tín hiệu hủy/ngắt | Khôi phục interrupt và lan truyền |
| Bọc `IOException` bằng một chuỗi không cause | Không truy được I/O gốc | `UncheckedIOException(message, ex)` |
| Bắt lỗi quanh lúc dựng `map` | Không bắt được lỗi lazy ở terminal | Bắt quanh terminal hoặc trong mapper |
| Dùng `map(...).count()` để validate | Mapper có thể bị bỏ qua | Thu thập kết quả validation thật |
| Bắt khóa trùng của `toMap` rồi giữ tùy ý một giá trị | Che quy tắc merge chưa có | `groupingBy` hoặc merge policy đúng |
| Nuốt `Math.addExact` overflow | Giá trị tổng mất tin cậy | Nâng miền số hoặc báo lỗi |
| Không đóng `Files.lines` khi có exception | Rò rỉ tài nguyên | `try-with-resources` |
| Quên kiểm tra `getSuppressed()` | Không thấy lỗi lúc close | Giữ và quan sát suppressed |
| `return` từ `finally` | Có thể che ngoại lệ từ `try` | Để `try-with-resources` quản lý close |
| Retry trên Stream đã tiêu thụ | `IllegalStateException` hoặc dữ liệu dở | Tạo nguồn mới |
| Retry side effect không idempotent | Ghi/gửi trùng | Giao dịch/idempotency |
| Assert “lỗi phần tử đầu tiên” trong parallel | Không có bảo đảm lịch xử lý | Kiểm tra hợp đồng lỗi, không ép thứ tự |
| Log toàn bộ bản ghi có dữ liệu nhạy cảm | Rủi ro bảo mật | Redaction và quyền truy cập log |
| Gom mọi lỗi thành `Optional.empty()` | Trộn không có kết quả với thất bại | Phân biệt absence, validation và system failure |

## 22. Quy trình xử lý ngoại lệ theo tầng

```text
Một thao tác thất bại
         |
         v
 Lỗi thuộc loại nào?
   /       |          \
 dữ liệu   I/O       bug / hạ tầng khác
   |       |               |
   v       v               v
 Có hợp    Có thể          Không che lỗi
 đồng cho  retry           bằng fallback
 phép bỏ   thật sự?
 qua?       |
  / \      / \
 Có Không Có Không
 |    |   |    |
 v    v   v    v
Result  Ném  Nguồn Ném/wrap
được    với  mới,  giữ cause
đếm     cause giới hạn
         |     |
         +--+--+
            v
   Ranh giới tác vụ/API
            |
   log một lần + context an toàn
            |
   trạng thái thất bại rõ ràng
```

Chọn các điểm **biến lỗi thành dữ liệu** và **biến lỗi thành exception của tầng cao hơn** có chủ đích. Chỉ khi cả hai là một hợp đồng rõ ràng, pipeline mới có thể vừa dễ đọc vừa đáng tin cậy.

## 23. Checklist trước khi đưa pipeline vào production

1. Có `catch` rỗng, catch rồi trả 0/`null`/List rỗng hoặc log rồi coi là thành công không?
2. Nếu wrap exception, constructor có truyền `cause` gốc không?
3. Lỗi ở `map`/`filter` có thể xuất hiện **khi terminal chạy**, chứ không phải khi tạo pipeline không?
4. Terminal nào short-circuit hoặc có thể bỏ qua callback do tối ưu? Việc xác thực dữ liệu có phụ thuộc vào số lần callback không?
5. Phân biệt lỗi dữ liệu dự kiến, lỗi I/O, lỗi lập trình và tín hiệu ngắt tác vụ chưa?
6. Nếu dùng `Result`, tổng accepted/rejected có đối chiếu với số phần tử đầu vào không?
7. Nếu dùng Collector tùy chỉnh, Supplier/accumulator/combiner/finisher có truyền lỗi đúng và không chia sẻ trạng thái sai không?
8. Có một `try-with-resources` bao quanh đúng nguồn I/O cần đóng không?
9. Nếu xử lý lẫn đóng tài nguyên đều thất bại, có giữ primary và suppressed exceptions không?
10. Có log exception đầy đủ ở ranh giới phù hợp, nhưng tránh log trùng và tránh lộ dữ liệu nhạy cảm không?
11. Nếu retry, có nguồn mới, giới hạn số lần, xác định tính tạm thời, snapshot và idempotency không?
12. Nếu parallel, có tránh giả định lỗi xuất hiện theo encounter order hoặc mọi tác vụ đều rollback không?
13. Test đã kiểm tra dữ liệu hợp lệ, lỗi parse, null, nguồn rỗng, khóa trùng, overflow và đóng tài nguyên chưa?
14. Có dùng giá trị mặc định **chỉ** khi nghiệp vụ cho phép, thay vì che mất thất bại không?

## 24. Bài tập thực hành

### Bài tập A: sửa code đang nuốt lỗi

Cho pipeline:

```java
List<Integer> values = raw.stream()
        .map(s -> {
            try {
                return Integer.parseInt(s);
            } catch (Exception ignored) {
                return 0;
            }
        })
        .collect(Collectors.toList());
```

**Yêu cầu:** viết lại theo hai cách: (1) fail-fast bằng `IllegalArgumentException(message, cause)` với bối cảnh dòng; (2) dùng `ParseOutcome` để đếm đúng số bản ghi lỗi. So sánh sự khác nhau về kết quả trả cho caller và khả năng kiểm toán.

### Bài tập B: truyền nguyên nhân của Files.size

Tạo `List<Path>` gồm hai tệp có thật và một đường dẫn không tồn tại. Trong `map`, wrap `IOException` bằng `UncheckedIOException`. Ở caller, xác minh `getCause()` là `IOException` và không trả tổng kích thước “thành công” nếu một tệp bắt buộc không đọc được.

### Bài tập C: primary và suppressed

Đăng ký `onClose` có handler ném `IllegalStateException("close")`. Trong `forEach` ném `IllegalArgumentException("body")`. Kiểm tra primary là lỗi xử lý, danh sách suppressed có lỗi close. Thử thêm trường hợp chỉ close thất bại.

### Bài tập D: báo cáo dữ liệu lỗi

Với nguồn:

```text
"10", "bad", "-3", "", null
```

Kết quả mong đợi:

```text
accepted = 2
rejected = 3
sum = 7
```

Dùng `ParseOutcome` và `ImportStats`. Không bắt mọi `RuntimeException` như thể đó chỉ là lỗi parse.

### Bài tập E: khóa trùng và overflow

Thử `toMap(String::length, s -> s)` trên `"cat"`/`"dog"`. Định nghĩa cách xử lý khóa trùng phù hợp thay vì bắt lỗi rồi giữ tùy ý một phần tử. Sau đó thử `reduce(0, Math::addExact)` với `Integer.MAX_VALUE` và `1`; thiết kế chính sách báo lỗi hoặc chuyển miền số.

### Bài tập F: retry và nguồn một lần

Dùng `Files.lines` với một fixture bất biến. Thiết kế factory mở Stream mới cho mỗi lượt thử, đóng mỗi Stream và giới hạn retry. Giải thích vì sao không được gọi terminal lần thứ hai trên cùng một Stream đã lỗi.

### Bài tập G: lỗi trong parallel

Dùng hai phần tử được cấu hình ném `IllegalArgumentException` ở vị trí khác nhau của `IntStream.range(...).parallel()`. Viết test **không** ràng buộc phần tử nào báo trước; sau đó thay fail-fast bằng `ParseOutcome` để báo cáo tất cả lỗi dữ liệu dự kiến.

## 25. Câu hỏi tự kiểm tra

1. Nuốt ngoại lệ là gì? **Bắt lỗi rồi làm mất tín hiệu thất bại khi không có hợp đồng xử lý hợp lệ**.
2. Vì sao `catch (Exception ex) { return 0; }` nguy hiểm? **Làm lỗi trông như dữ liệu số 0 hợp lệ**.
3. Nếu tạo exception mới, làm sao giữ lỗi ban đầu? **Dùng constructor nhận `cause`, ví dụ `new IllegalStateException(message, ex)`**.
4. `getCause()` và `getSuppressed()` khác nhau thế nào? **Cause biểu diễn quan hệ nguyên nhân; suppressed chứa các lỗi bổ sung, thường khi đóng**.
5. Lỗi trong `map` thường xuất hiện lúc nào? **Khi một terminal yêu cầu đánh giá phần tử ấy**.
6. `map(parse).count()` có bắt buộc gọi mọi mapper không? **Không**, Stream có thể tối ưu bỏ mapper.
7. `Function.apply` có cho ném `IOException` trực tiếp mà không bắt/wrap không? **Không**, đây là checked exception không có trong chữ ký `Function`.
8. Nên wrap `IOException` bằng kiểu nào để giữ ngữ nghĩa I/O trong lambda? **`UncheckedIOException(message, cause)`**.
9. Có thể coi mọi `RuntimeException` là lỗi một bản ghi không? **Không**, một số là bug hoặc lỗi hạ tầng phải fail-fast.
10. Vì sao không nên bắt `Throwable` để trả thành công? **Có thể nuốt cả `Error` nghiêm trọng**.
11. Khi bắt `InterruptedException` nhưng không thể ném checked exception, cần lưu ý gì? **Khôi phục interrupt flag và truyền lỗi với cause theo hợp đồng tầng gọi**.
12. `ParseOutcome` giúp điều gì? **Giữ lỗi dữ liệu như một kết quả có cấu trúc, có thể đếm và kiểm toán**.
13. Tại sao không nên giữ hàng triệu Throwable trong bộ nhớ? **Chi phí bộ nhớ/stack trace lớn; cần thống kê hoặc giới hạn mẫu lỗi**.
14. `toMap` không có merge function gặp khóa trùng có thể ném gì? **`IllegalStateException`**.
15. `reduce(0, Math::addExact)` vượt miền `int` ném gì? **`ArithmeticException`**.
16. `Files.lines` có thể ném lỗi khi mở và khi duyệt dưới dạng nào? **`IOException` và `UncheckedIOException`**.
17. `collect` có tự đóng Stream từ `Files.lines` không? **Không**.
18. `onClose` chạy khi nào? **Khi Stream được đóng, không chỉ vì terminal đã hoàn tất**.
19. Nếu body và close đều lỗi trong `try-with-resources`, lỗi nào thường là primary? **Lỗi body; lỗi close được suppressed**.
20. Một lỗi được log có tự đồng nghĩa đã được xử lý không? **Không**, trạng thái kết quả phải đúng hợp đồng.
21. Retry một Stream đã tiêu thụ có đúng không? **Không**, phải tạo nguồn mới.
22. Trước khi retry thao tác có side effect, cần gì? **Xác định lỗi tạm thời, giới hạn lần thử và idempotency/transaction**.
23. Với parallel stream có hai lỗi, lỗi nào bắt buộc được báo trước? **Không có bảo đảm theo thứ tự nguồn**.
24. Vì sao phải hạn chế thông tin raw trong exception message? **Cause/message có thể chứa dữ liệu nhạy cảm**.
25. Điều quan trọng nhất khi viết `catch` là gì? **Biết mình có thể xử lý hợp lệ hay phải truyền lỗi kèm nguyên nhân, không tạo thành công giả**.

**Nguyên tắc áp dụng:** Một pipeline Java Stream an toàn **không che giấu thất bại bằng dữ liệu mặc định** và **không đánh mất ngoại lệ gốc khi thay đổi tầng trừu tượng**. Bắt đúng loại lỗi ở đúng ranh giới lazy/terminal, truyền `cause` khi wrap, giữ `suppressed exceptions` khi đóng tài nguyên, dùng `Result` có cấu trúc khi nghiệp vụ cho phép xử lý từng bản ghi, và không phụ thuộc vào thứ tự lỗi khi chạy song song. Nếu một tầng không thể bảo đảm kết quả sau xử lý vẫn đúng hợp đồng, hãy để lỗi được lan truyền rõ ràng tới tầng chịu trách nhiệm.
