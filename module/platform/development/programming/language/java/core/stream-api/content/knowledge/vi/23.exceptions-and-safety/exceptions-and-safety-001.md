# Lan truyền ngoại lệ từ nguồn, hàm ánh xạ và phép toán kết thúc

Java Stream API giúp mô tả xử lý dữ liệu bằng pipeline `filter`, `map`, `reduce` và `collect`. Nhưng khi dữ liệu không hợp lệ, nguồn I/O gặp sự cố hoặc một Collector không thể hoàn tất, **ngoại lệ xuất hiện ở đâu và được lan truyền như thế nào?** Đây là câu hỏi quan trọng trong cả code nghiệp vụ lẫn kiểm thử.

Một đặc điểm cốt lõi của Stream là **lazy evaluation**: phần lớn intermediate operation không duyệt dữ liệu ngay khi được khai báo. Ngoại lệ của hàm `map` hoặc `filter` vì vậy thường chỉ xuất hiện khi terminal operation thực sự yêu cầu tính phần tử. Với nguồn có tài nguyên như `Files.lines`, còn phải phân biệt lỗi **mở nguồn** với lỗi **đọc trong khi duyệt**, và nhớ rằng việc xử lý kết thúc không tự đóng nguồn.

Bài thuộc chương **Ngoại lệ và tính an toàn** của module `JAVA_STREAM_API`. Ta sẽ lần lượt phân tích ba lớp lỗi — **nguồn**, **phép biến đổi** và **terminal operation** — rồi xây cách xử lý fail-fast hoặc gom lỗi theo từng bản ghi, giữ nguyên nguyên nhân, quản lý `try-with-resources`, kiểm thử pipeline song song và tránh những giả định nguy hiểm về việc tất cả phần tử đều được xử lý.

> **Môi trường:** Các ví dụ Stream chính sử dụng API **Java 8 trở lên**. Mỗi khối mã có thể là đoạn trong `main`, JShell hoặc một phương thức độc lập theo mô tả; các class/helper có thể đặt riêng. Những ví dụ cố ý ném ngoại lệ được đánh dấu rõ. Việc lựa chọn bỏ qua dữ liệu, ghi nhận lỗi hay dừng toàn bộ là **chính sách nghiệp vụ**, không phải hành vi được Java Stream API tự quyết định.

## 1. Ngoại lệ có thể xuất hiện ở ba tầng khác nhau

Một pipeline điển hình:

```text
Nguồn Stream<T>
   |
   |  [1] tạo và đọc nguồn
   |      - IOException khi mở tệp
   |      - UncheckedIOException khi duyệt dòng
   |      - IllegalStateException từ nguồn tự viết
   v
filter / map / flatMap / peek
   |
   |  [2] hàm trong pipeline
   |      - NumberFormatException khi parse
   |      - NullPointerException khi truy cập null
   |      - IllegalArgumentException khi validate
   v
collect / reduce / count / forEach / findFirst
   |
   |  [3] thao tác kết thúc và Collector
   |      - IllegalStateException do khóa toMap trùng
   |      - ArithmeticException từ phép cộng kiểm tra tràn
   |      - ngoại lệ từ accumulator/combiner/finisher
   v
Kết quả hoặc ngoại lệ
```

| Tầng | Thời điểm thường gặp | Ví dụ | Hướng xử lý |
| --- | --- | --- | --- |
| Tạo nguồn | Khi gọi factory nguồn | `Files.lines(path)` không mở được tệp | Bắt hoặc khai báo `IOException` ở ranh giới I/O |
| Duyệt nguồn lazy | Khi terminal kéo phần tử | Lỗi đọc từ `Files.lines` sau vài dòng | Xử lý `UncheckedIOException`, bảo đảm đóng nguồn |
| Intermediate operation | Khi phần tử thực sự đi qua hàm | `Integer.parseInt("abc")` trong `map` | Fail-fast hoặc chuyển lỗi thành giá trị |
| Terminal operation | Trong quá trình thu thập/rút gọn | `toMap` gặp khóa trùng; `reduce` ném lỗi | Chọn merge policy/collector đúng, không che mất lỗi |
| Dọn dẹp tài nguyên | Khi gọi `Stream.close()` hoặc thoát `try` | Close handler ném lỗi | Theo dõi ngoại lệ chính và suppressed exceptions |

**Quy tắc:** xác định **nơi gây ra lỗi** và **nơi lỗi được quan sát**. Hai nơi này không nhất thiết trùng nhau. Với Stream, lời gọi tạo pipeline thường chỉ lắp ráp các bước; lỗi trong lambda có thể xuất hiện muộn hơn tại lời gọi terminal.

## 2. Lazy evaluation: viết map không đồng nghĩa đã chạy map

Đoạn mã sau **chưa parse chuỗi nào** tại thời điểm gọi `map`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> raw = Arrays.asList("10", "20", "not-a-number");

Stream<Integer> numbers = raw.stream()
        .map(Integer::parseInt); // chưa duyệt phần tử

// Lỗi thường xuất hiện tại terminal operation:
List<Integer> parsed = numbers.collect(Collectors.toList());
// NumberFormatException: For input string "not-a-number"
```

`Integer::parseInt` có thể ném `NumberFormatException`, một `RuntimeException`. Trong pipeline này, phép thu thập vào danh sách cần toàn bộ kết quả nên cuối cùng gặp phần tử không hợp lệ.

Sai lầm phổ biến là đặt `try/catch` quanh **chỉ đoạn dựng Stream**:

```java
Stream<Integer> pending;

try {
    pending = raw.stream().map(Integer::parseInt);
} catch (NumberFormatException ex) {
    // Không bắt được lỗi parse phát sinh lúc collect phía sau.
    throw new IllegalStateException("Cannot parse input", ex);
}

pending.collect(Collectors.toList()); // lỗi xuất hiện ở đây
```

Muốn bắt lỗi tại ranh giới xử lý, đặt `try/catch` quanh **terminal operation**:

```java
try {
    List<Integer> parsed = raw.stream()
            .map(Integer::parseInt)
            .collect(Collectors.toList());
    System.out.println(parsed);
} catch (NumberFormatException ex) {
    System.err.println("Invalid integer: " + ex.getMessage());
}
```

Không nhất thiết mọi intermediate lambda đều được gọi. Ví dụ một số pipeline có nguồn biết trước kích thước và terminal `count()` có thể được tối ưu để **không thực hiện `map`**:

```java
long count = raw.stream()
        .map(Integer::parseInt) // có thể không chạy
        .count();

System.out.println(count); // Có thể là 3, không nhất thiết ném lỗi parse
```

**Đừng dùng `count()` kèm một `map` chỉ để “ép kiểm tra hợp lệ”** nếu mục đích không phải là kết quả được Stream yêu cầu. Nếu bắt buộc kiểm tra toàn bộ dữ liệu, hãy thiết kế một terminal tiêu thụ giá trị đã biến đổi hoặc một phép tổng hợp lỗi riêng.

## 3. Ngoại lệ từ nguồn: mở nguồn khác đọc nguồn

Với nguồn tệp:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
```

Có **hai thời điểm gây lỗi khác nhau**:

1. **Tạo nguồn:** `Files.lines(...)` có thể ném `IOException` ngay khi mở tệp, ví dụ không tồn tại hoặc không có quyền truy cập.
2. **Tiêu thụ nguồn:** việc đọc tệp xảy ra lazy. Nếu I/O thất bại khi duyệt, Stream từ `Files.lines` có thể ném `UncheckedIOException` từ terminal operation.

`UncheckedIOException` là một `RuntimeException` bọc một `IOException`. Khi cần truy cập nguyên nhân I/O đã được bọc, dùng `getCause()`:

```java
import java.io.UncheckedIOException;

try {
    countLines(path);
} catch (UncheckedIOException ex) {
    System.err.println("Read failed: "
            + ex.getCause().getMessage());
} catch (IOException ex) {
    System.err.println("Open/close failed: "
            + ex.getMessage());
}
```

`countLines` được khai báo `throws IOException` để biểu diễn lỗi được kiểm tra ở tầng nguồn. Ngoại lệ runtime như `UncheckedIOException` vẫn có thể lan ra mà không cần khai báo trong chữ ký.

**Lưu ý:** `Stream.count()` có các tối ưu dựa vào kích thước nguồn nếu phù hợp; không thiết kế mã kiểm thử phụ thuộc vào việc mỗi dòng chắc chắn được materialize trong mọi trường hợp. Muốn kiểm tra nội dung, nên dùng pipeline cần đọc/parse dữ liệu đó.

### Nguồn tự viết cũng có thể ném lỗi khi duyệt

Nếu một `Iterator`, `Spliterator` hoặc supplier phát phần tử ném `RuntimeException`, lỗi có thể đi ra khi terminal kéo tới phần tử tương ứng:

```java
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

Iterator<String> source = new Iterator<String>() {
    private int index;

    @Override
    public boolean hasNext() {
        if (index == 2) {
            throw new IllegalStateException("Source read failed");
        }
        return index < 4;
    }

    @Override
    public String next() {
        return "event-" + index++;
    }
};

Spliterator<String> spliterator =
        Spliterators.spliteratorUnknownSize(
                source, Spliterator.ORDERED);

try {
    StreamSupport.stream(spliterator, false)
            .collect(Collectors.toList());
} catch (IllegalStateException ex) {
    System.err.println(ex.getMessage()); // Source read failed
}
```

`try/catch` bên ngoài terminal có thể bắt lỗi nhưng **không thể khôi phục Iterator đã tiêu thụ dở**. Muốn thử lại, phải tạo **nguồn mới** với chính sách retry và tính nhất quán dữ liệu rõ ràng.

## 4. Ngoại lệ từ map, filter, flatMap và các callback

Các hàm trong Stream thường được biểu diễn bằng `Function`, `Predicate`, `Consumer` hoặc primitive functional interface. Nếu callback ném một `RuntimeException` hoặc `Error`, chúng thường lan ra khỏi quá trình thực thi pipeline; Stream không tự chuyển một phần tử lỗi thành `Optional.empty()` hay tự ghi log cho bạn.

### map: lỗi parse hoặc chuyển kiểu

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList("7", "x", "12")
        .stream()
        .map(Integer::parseInt)
        .collect(Collectors.toList());
// NumberFormatException tại "x"
```

Đoạn trên là **ví dụ fail-fast**. Danh sách đầu ra không được trả về bình thường nếu phép parse ném ngoại lệ. Đừng giả định Java sẽ trả danh sách `[7]` như một kết quả hoàn chỉnh và bỏ qua phần tử lỗi.

### filter: Predicate cũng có thể ném ngoại lệ

```java
import java.util.Arrays;

boolean hasHighValue = Arrays.asList("10", "bad", "50")
        .stream()
        .anyMatch(text -> Integer.parseInt(text) > 40);
```

Với phiên bản tuần tự và thứ tự trên, predicate gặp `"bad"` trước khi tới `"50"` nên ném `NumberFormatException`. Nếu đầu tiên là `"50"`, `anyMatch` có thể trả `true` mà không đánh giá các phần tử sau.

### flatMap: lỗi của nguồn lồng nhau

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> records = Arrays.asList("a,b", "c,d", "e,f");

List<String> tokens = records.stream()
        .flatMap(line -> Stream.of(line.split(",")))
        .collect(Collectors.toList());
```

Đoạn này hợp lệ với ba chuỗi không null. Nhưng nếu `line` là `null` thì `line.split(...)` ném `NullPointerException` khi mapper được chạy. Với nguồn tệp lồng nhau, một `flatMap` có thể kéo phần tử từ stream con và gặp lỗi khi duyệt stream con. Theo hợp đồng `flatMap`, **mỗi stream con được trả về được đóng sau khi nội dung của nó được đặt vào pipeline**; tuy nhiên, điều đó không thay thế việc đóng stream nguồn bên ngoài nếu nó giữ tài nguyên.

### Hàm có side effect: ngoại lệ không tự hoàn tác tác dụng phụ

```java
import java.util.Arrays;
import java.util.List;

List<String> values = Arrays.asList("A", "B", "C");

values.stream().forEach(value -> {
    if ("B".equals(value)) {
        throw new IllegalArgumentException("B is not allowed");
    }
    System.out.println("Processed: " + value);
});
```

Có thể đã in `"Processed: A"` trước khi lỗi xảy ra. Nếu thay in log bằng ghi database, gửi email hoặc gọi API, những tác động đã thực hiện **không tự bị rollback** vì Stream ném ngoại lệ. Cần thiết kế transaction/idempotency ở tầng nghiệp vụ nếu mong muốn tất cả hoặc không gì cả.

## 5. Checked exception không tự đi qua Function

`Function<T,R>.apply` không khai báo `throws IOException`. Vì vậy lambda sau **không hợp lệ khi biên dịch**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

// SAI: Files.size(...) ném checked IOException.
List<Long> sizes = paths.stream()
        .map(path -> Files.size(path))
        .collect(java.util.stream.Collectors.toList());
```

Đây là ví dụ minh họa lỗi biên dịch; `paths` được giả định là `List<Path>`. Compiler không cho phép bỏ qua checked exception của `Files.size` trong `Function`.

Có ba cách chọn chính sách:

1. **Chuyển sang unchecked exception có nguyên nhân**, ví dụ `UncheckedIOException`, khi cần fail-fast.
2. **Chuyển kết quả thành giá trị chứa lỗi** (Result/Outcome) để giữ dữ liệu hợp lệ và lỗi.
3. **Đưa thao tác I/O ra ngoài pipeline** hoặc dùng vòng lặp rõ ràng nếu cần xử lý checked exception phức tạp.

Không nên dùng một generic “sneaky throw” để né kiểm tra exception chỉ vì muốn giữ cú pháp Stream ngắn gọn; nó có thể khiến hợp đồng API khó đọc và khó vận hành.

## 6. Cách fail-fast đúng: UncheckedIOException giữ nguyên cause

Ví dụ chuyển từng đường dẫn thành kích thước tệp:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

static List<Long> readSizes(List<Path> paths) {
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

Tại ranh giới gọi:

```java
try {
    List<Long> sizes = readSizes(paths);
    System.out.println(sizes);
} catch (UncheckedIOException ex) {
    IOException cause = ex.getCause();
    System.err.println("I/O error: " + cause.getMessage());
}
```

Tại sao chọn `UncheckedIOException` thay vì `new RuntimeException(ex)`?

- Kiểu ngoại lệ **nói rõ đây là lỗi I/O**.
- `getCause()` có kiểu `IOException`.
- Stack trace giữ chuỗi nguyên nhân từ thao tác gốc.

`UncheckedIOException` không biến lỗi thành “đã xử lý thành công”. Nó chỉ cho phép lỗi đi qua callback không khai báo checked exception, để tầng ngoài quyết định báo lỗi, retry hoặc trả trạng thái thất bại.

**Không nên bắt `Exception` một cách quá rộng trong mapper** rồi biến tất cả lỗi thành 0. Lỗi I/O, lỗi parse, lỗi lập trình và vi phạm hợp đồng nghiệp vụ có thể cần chính sách khác nhau.

## 7. Xử lý một phần tử lỗi: fail-fast, bỏ qua, hay giữ cả lỗi?

Không có một lựa chọn đúng cho mọi hệ thống.

| Chính sách | Cách biểu diễn | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| **Fail-fast** | Ném exception tại phần tử lỗi | Không che dữ liệu hỏng | Dừng toàn bộ kết quả, có thể đã có side effect |
| **Skip có chủ đích** | Bỏ phần tử không hợp lệ sau khi xác thực | Tiếp tục xử lý dữ liệu tốt | Mất dữ liệu nếu không đếm/ghi nhận số lỗi |
| **Giữ lỗi dưới dạng dữ liệu** | `ParseResult` hoặc kiểu `Either` | Báo cáo được cả thành công và thất bại | Cần định nghĩa kiểu kết quả và xử lý rõ ràng |
| **Fallback** | Giá trị mặc định có ý nghĩa nghiệp vụ | Đầu ra liên tục nếu lỗi được phép | Có thể che sai lệch nghiêm trọng |
| **Retry** | Khởi tạo thao tác/nguồn mới theo chính sách | Có ích với một số lỗi tạm thời | Có thể lặp tác dụng phụ hoặc gặp cùng lỗi vĩnh viễn |

Với số liệu kinh doanh, bỏ âm thầm một dòng lỗi có thể làm báo cáo sai. Với telemetry, hệ thống có thể chọn tiếp tục nhưng phải ghi số dòng hỏng để theo dõi chất lượng dữ liệu.

### Chỉ bỏ qua dữ liệu hợp lệ theo quy tắc đã được xác định

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> raw = Arrays.asList(" 10 ", "", " -3 ", null, "25");

List<Integer> parsed = raw.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .map(Integer::parseInt)
        .collect(Collectors.toList());

System.out.println(parsed); // [10, -3, 25]
```

Pipeline này chỉ giải quyết **null/chuỗi rỗng**, vì chúng bị lọc trước khi parse. Nếu chuỗi là `"abc"`, `Integer.parseInt` vẫn ném `NumberFormatException`. Đừng gọi pipeline này là “tự bỏ qua mọi bản ghi sai”.

Một cách an toàn hơn là dùng `Result` để phân biệt lỗi parse thực tế và vẫn giữ thông tin bản ghi gốc.

## 8. Mẫu Result: chuyển lỗi parse thành một giá trị có thể thu thập

Ví dụ Java 8, không cần `record` hoặc thư viện bên ngoài:

```java
public final class ParseResult {
    private final String raw;
    private final Integer value;
    private final String error;

    private ParseResult(String raw, Integer value, String error) {
        this.raw = raw;
        this.value = value;
        this.error = error;
    }

    public static ParseResult from(String raw) {
        if (raw == null) {
            return new ParseResult(null, null, "Missing value");
        }

        String normalized = raw.trim();
        if (normalized.isEmpty()) {
            return new ParseResult(raw, null, "Blank value");
        }

        try {
            return new ParseResult(
                    raw, Integer.parseInt(normalized), null);
        } catch (NumberFormatException ex) {
            return new ParseResult(
                    raw, null, "Not an integer: " + normalized);
        }
    }

    public boolean isValid() {
        return error == null;
    }

    public int value() {
        if (!isValid()) {
            throw new IllegalStateException(
                    "Cannot read value from failed ParseResult");
        }
        return value;
    }

    public String error() {
        return error;
    }

    public String raw() {
        return raw;
    }
}
```

Mỗi phần tử được biểu diễn thành **một kết quả thành công hoặc thất bại**, không làm hỏng cả Stream vì một lỗi dữ liệu có thể dự đoán được:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<ParseResult> results = Arrays.asList(
        "10", "bad", "-3", "", null
).stream()
 .map(ParseResult::from)
 .collect(Collectors.toList());

Map<Boolean, Long> byValidity = results.stream()
        .collect(Collectors.partitioningBy(
                ParseResult::isValid,
                Collectors.counting()));

System.out.println(byValidity.get(true));  // 2
System.out.println(byValidity.get(false)); // 3
```

Lấy các giá trị thành công:

```java
List<Integer> accepted = results.stream()
        .filter(ParseResult::isValid)
        .map(ParseResult::value)
        .collect(Collectors.toList());

System.out.println(accepted); // [10, -3]
```

Lấy thông tin lỗi:

```java
List<String> errors = results.stream()
        .filter(r -> !r.isValid())
        .map(r -> "raw=" + r.raw() + ", error=" + r.error())
        .collect(Collectors.toList());

System.out.println(errors.size()); // 3
```

**Lợi ích:** có thể đối chiếu `total = accepted + rejected`. Các lỗi được dự kiến như chuỗi rỗng hoặc giá trị không phải số trở thành dữ liệu có thể báo cáo.

**Giới hạn:** mẫu này không đồng nghĩa nên bắt `OutOfMemoryError`, `StackOverflowError` hoặc mọi `RuntimeException` rồi coi chúng như lỗi của một bản ghi. Đối với lỗi hạ tầng và lỗi lập trình không thể phục hồi, fail-fast có thể an toàn hơn.

## 9. Một lượt xử lý dữ liệu tốt và lỗi mà không cần lưu tất cả kết quả

`results.stream().collect(toList())` ở phần trước giữ mọi `ParseResult` trong bộ nhớ. Với nguồn lớn, có thể tạo một thống kê nhỏ trong một lượt thu thập:

```java
import java.util.List;

final class ImportSummary {
    private long accepted;
    private long rejected;
    private long sum;

    void add(ParseResult result) {
        if (result.isValid()) {
            accepted++;
            sum += result.value();
        } else {
            rejected++;
        }
    }

    void merge(ImportSummary other) {
        accepted += other.accepted;
        rejected += other.rejected;
        sum += other.sum;
    }

    long accepted() { return accepted; }
    long rejected() { return rejected; }
    long sum() { return sum; }
}
```

Sử dụng:

```java
import java.util.Arrays;

ImportSummary summary = Arrays.asList(
        "10", "bad", "-3", "", null
).stream()
 .map(ParseResult::from)
 .collect(
         ImportSummary::new,
         ImportSummary::add,
         ImportSummary::merge
 );

System.out.println(summary.accepted()); // 2
System.out.println(summary.rejected()); // 3
System.out.println(summary.sum());      // 7
```

Supplier `ImportSummary::new` tạo accumulator riêng khi framework cần nhiều nhánh. `merge` kết hợp đầy đủ ba trường, không bỏ sót dữ liệu. Thiết kế này không lưu `String` lỗi cụ thể; nếu cần kiểm toán từng bản ghi hỏng, hãy lưu riêng theo giới hạn, ghi ra đích có chính sách tài nguyên hoặc trả một danh sách lỗi có giới hạn.

Không ghi từ `ImportSummary.add` vào một `ArrayList` dùng chung ở bên ngoài mà không đồng bộ. Với parallel stream, việc có một accumulator mới cho mỗi nhánh mới là điều kiện để mutable reduction theo mẫu này hoạt động đúng. `long` vẫn có thể tràn trên các tập dữ liệu cực lớn; nếu nghiệp vụ đòi chính xác tuyệt đối, cần cơ chế kiểm tra số học.

## 10. Ngoại lệ từ terminal operation

Nhiều người chỉ nhìn vào `map` hoặc `filter` khi tìm lỗi, nhưng terminal operation cũng có thể chủ động ném ngoại lệ:

| Terminal | Tình huống lỗi | Ghi chú |
| --- | --- | --- |
| `collect(toMap(...))` | Khóa trùng mà không có merge function | `IllegalStateException` |
| `collect(groupingBy(...))` | Classifier tạo khóa null | `NullPointerException` với collector chuẩn |
| `reduce(...)` | Operator ném lỗi, ví dụ `Math.addExact` tràn | Exception từ accumulator/combiner |
| `forEach(...)` | Consumer ném lỗi | Tác dụng phụ trước lỗi không tự rollback |
| `findFirst()` | Phần tử được chọn là null | Có thể ném `NullPointerException` |
| `Optional.get()` sau terminal | `Optional` rỗng | `NoSuchElementException` từ `get` |
| `collect(customCollector)` | Supplier/accumulator/combiner/finisher có lỗi | Lỗi tùy vào code của Collector |
| `count()` | Không yêu cầu mọi bước intermediate chạy | Không dùng `count` để đảm bảo validation side effect |

### Ví dụ toMap gặp khóa trùng

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, String> byLength = Arrays.asList("cat", "dog")
        .stream()
        .collect(Collectors.toMap(
                String::length,
                s -> s
        ));
// IllegalStateException: cả hai chuỗi đều tạo key 3.
```

Lỗi ở đây không phải parse dữ liệu mà là **không định nghĩa cách giải quyết khóa trùng**. Nếu mục tiêu giữ tất cả chuỗi theo độ dài, dùng `groupingBy`:

```java
import java.util.List;

Map<Integer, List<String>> grouped = Arrays.asList("cat", "dog")
        .stream()
        .collect(Collectors.groupingBy(String::length));

System.out.println(grouped.get(3)); // [cat, dog]
```

Nếu nghiệp vụ muốn chọn một phần tử theo quy tắc, dùng `toMap(keyMapper,valueMapper,mergeFunction)`, nhưng hàm merge phải hợp lệ và độc lập với thứ tự nếu kết quả cần bền vững khi chạy song song.

### Ví dụ reduce có toán tử ném lỗi

```java
import java.util.Arrays;

int sum = Arrays.asList(Integer.MAX_VALUE, 1)
        .stream()
        .reduce(0, Math::addExact);
// ArithmeticException: integer overflow
```

`Math.addExact` hữu ích khi phải phát hiện tràn thay vì cho phép vòng lại giá trị. Tuy nhiên, với parallel reduction, phép gộp các phần có thể tạo những tổng trung gian khác nhau. Nếu kết quả toán học tổng cuối nằm trong miền nhưng một cách gộp trung gian vượt miền, ngoại lệ có thể phụ thuộc cách phân nhóm. Cần xác định hợp đồng số học và chọn kiểu/thuật toán đáp ứng yêu cầu trước khi so sánh tuần tự với song song.

### Optional rỗng không phải lỗi nếu đã mô hình hóa đúng

```java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> firstEven = Arrays.asList(1, 3, 5)
        .stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(firstEven.isPresent()); // false
```

Đừng gọi `firstEven.get()` khi nó rỗng. Chọn `orElse`, `orElseGet` hoặc `orElseThrow` với thông báo nghiệp vụ rõ ràng, tùy bài toán.

## 11. Kiểm soát thứ tự và short-circuit khi xảy ra lỗi

Một terminal operation dừng sớm có thể **không duyệt tới phần tử không hợp lệ**:

```java
import java.util.Arrays;

boolean found = Arrays.asList("100", "bad", "10")
        .stream()
        .anyMatch(s -> Integer.parseInt(s) >= 100);

System.out.println(found); // true
```

Ở đây số `100` đầu tiên đã đủ để trả `true`; `"bad"` đứng sau không cần được parse trong thực thi tuần tự.

Tương tự:

```java
int first = Arrays.asList("7", "invalid")
        .stream()
        .map(Integer::parseInt)
        .findFirst()
        .orElseThrow(IllegalStateException::new);

System.out.println(first); // 7
```

Việc không gặp lỗi trong một terminal **không chứng minh** mọi bản ghi hợp lệ.

### Parallel stream có thể xử lý phần tử khác thứ tự thời gian

Trên `parallelStream()`, framework có thể tính các phần tử ở nhiều nhánh trước khi biết terminal đã có đủ kết quả. Không được khẳng định “có `limit(1)` nên các phần tử khác chắc chắn chưa bị gọi mapper”. Tính đúng của một pipeline song song không được dựa vào side effect hoặc khả năng ném lỗi ở một vị trí thời gian cụ thể.

Nếu yêu cầu là **kiểm tra tất cả bản ghi và báo lỗi nếu bất kỳ bản ghi nào sai**, hãy thiết kế phép thu thập kết quả kiểm tra toàn bộ, không dùng `findAny`, `anyMatch` hoặc `limit` làm công cụ đảm bảo mọi phần tử đã được kiểm tra.

### peek không nên dùng để kiểm chứng việc ném ngoại lệ

```java
long length = Arrays.asList("A", "B", "C")
        .stream()
        .peek(s -> {
            if ("B".equals(s)) {
                throw new IllegalStateException("B detected");
            }
        })
        .count();
```

Pipeline có kích thước nguồn biết trước và `count()` có thể được tối ưu mà không chạy `peek`. `peek` phù hợp để **quan sát tạm thời**, không nên gắn việc xác thực bắt buộc hoặc ghi nghiệp vụ vào đó.

## 12. Lan truyền lỗi khi chạy parallel: không dựa vào “lỗi đầu tiên”

Khi dùng `parallel()`, nhiều tác vụ có thể đang xử lý các phần dữ liệu khác nhau. Một phép `map` hoặc `reduce` có thể ném lỗi trong một tác vụ khi tác vụ khác vẫn đang làm việc.

```java
import java.util.stream.IntStream;

int total = IntStream.range(0, 1000)
        .parallel()
        .map(n -> {
            if (n == 200 || n == 700) {
                throw new IllegalArgumentException(
                        "Invalid element: " + n);
            }
            return n;
        })
        .sum();
```

Nếu pipeline ném ngoại lệ:

- **Không bảo đảm** phần tử lỗi có chỉ số nhỏ hơn sẽ được báo trước.
- Không dùng thứ tự stack trace hoặc thứ tự log các worker để suy encounter order.
- Có thể có các tác vụ khác đã xử lý một phần dữ liệu; không nên dựa vào side effect “tất cả hoặc không”.
- Ngoại lệ có thể đi qua lớp thực thi song song và có chuỗi `cause`; hãy giữ nguyên stack trace/causes để chẩn đoán thay vì chỉ ghi `ex.getMessage()`.
- Không yêu cầu mọi lỗi đồng thời đều xuất hiện đầy đủ dưới dạng một tập kết quả. Fail-fast không phải cơ chế thu thập tất cả lỗi.

Ví dụ cách xử lý ở ranh giới:

```java
try {
    int total = IntStream.range(0, 1000)
            .parallel()
            .map(n -> {
                if (n == 200 || n == 700) {
                    throw new IllegalArgumentException(
                            "Invalid element: " + n);
                }
                return n;
            })
            .sum();

    System.out.println(total);
} catch (RuntimeException ex) {
    // Ghi cả exception/stack trace và cause nếu có.
    ex.printStackTrace();
    throw ex; // giữ nguyên lỗi để tầng gọi xử lý
}
```

Không nên viết test cố định `ex.getMessage().equals("Invalid element: 200")` cho pipeline song song này. Hãy kiểm tra **loại tình huống lỗi** và tính đúng của chính sách xử lý, hoặc chuyển tất cả lỗi dự kiến thành giá trị trước khi thu thập nếu cần báo cáo đầy đủ.

### Concurrent collector không xóa lỗi nghiệp vụ

`groupingByConcurrent` hay `toConcurrentMap` có thể tích lũy an toàn theo hợp đồng nhưng classifier, mapper hoặc merge function vẫn có thể ném exception. Bật `CONCURRENT` không khiến các hàm đó tự trở thành không ném lỗi. Tương tự, một Collector thường không concurrent vẫn có thể chạy đúng trên parallel stream bằng các container riêng và combiner hợp lệ.

## 13. Vòng đời tài nguyên: terminal operation không tự close

`Stream` có `close()` nhưng nhiều nguồn trong bộ nhớ không giữ tài nguyên. Những nguồn I/O như `Files.lines` cần đóng rõ ràng.

Mẫu đúng:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<Integer> readNumbers(Path path)
        throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .map(Integer::parseInt)
                .collect(Collectors.toList());
    }
}
```

Nếu có dòng chứa `"abc"`:

1. `Files.lines` được mở trong biểu thức tạo resource.
2. `map(Integer::parseInt)` ném `NumberFormatException` khi duyệt dòng đó.
3. `try-with-resources` vẫn gọi `close()` đối với Stream đã mở.
4. `NumberFormatException` có thể tiếp tục lan ra caller.

Không phải vì đã gọi `collect(...)` mà nguồn tự được đóng. Nếu muốn trả Stream lazy cho caller, phải **chuyển quyền sở hữu và trách nhiệm đóng** cho caller một cách rõ ràng. Không trả Stream từ một `try-with-resources` đã đóng Reader bên trong.

### Reader.lines và quyền sở hữu Reader

`BufferedReader.lines()` trả một Stream các dòng nhưng đóng Stream đó **không nhất thiết đóng Reader** theo cách bạn mong muốn. Cách rõ ràng là đóng chính `BufferedReader` sở hữu dữ liệu:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static long countWarnings(Path path) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(s -> s.startsWith("WARN:"))
                .count();
    }
}
```

Với nguồn tự định nghĩa từ `Spliterator`, Java không tự biết bạn giữ socket, connection hay Reader nào. Đừng cho rằng việc tiêu thụ Spliterator thành công đồng nghĩa tài nguyên đã được giải phóng.

## 14. Lỗi trong close và suppressed exceptions

Khi xử lý dữ liệu ném lỗi, thao tác dọn dẹp cũng có thể thất bại. `try-with-resources` giữ ngoại lệ của phần thân làm **ngoại lệ chính**, và gắn ngoại lệ đóng tài nguyên vào `getSuppressed()`.

Ví dụ dùng `Stream.onClose` để minh họa:

```java
import java.util.stream.Stream;

try (Stream<String> source = Stream.of("A")
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {

    source.forEach(s -> {
        throw new IllegalArgumentException("processing failed");
    });

} catch (IllegalArgumentException primary) {
    System.out.println(primary.getMessage());
    // processing failed

    for (Throwable secondary : primary.getSuppressed()) {
        System.out.println(secondary.getMessage());
        // close failed
    }
}
```

Hai exception có vai trò khác nhau:

- `IllegalArgumentException("processing failed")` ném từ terminal callback.
- `IllegalStateException("close failed")` ném khi `try-with-resources` đóng Stream.
- Ngoại lệ thứ hai được ghi vào danh sách **suppressed** của ngoại lệ thứ nhất, nên không làm mất ngữ cảnh nguyên nhân ban đầu.

Nếu phần thân **không ném lỗi**, ngoại lệ từ `close()` có thể trở thành lỗi được caller nhận. `onClose` có thể đăng ký nhiều handler; khi đóng, các handler được gọi theo thứ tự đăng ký và vẫn cố gắng chạy các handler còn lại nếu một handler ném lỗi. Các lỗi bổ sung có thể được gắn dưới dạng suppressed exceptions theo hợp đồng.

**Không nên viết catch trống quanh `close`** rồi giả vờ pipeline thành công. Lỗi dọn dẹp có thể quan trọng, nhất là khi tài nguyên cần flush/commit dữ liệu. Đồng thời, khi log sự cố, nên giữ cả primary, causes và suppressed exceptions.

## 15. onClose không thay thế try-with-resources

`onClose` đăng ký hành vi sẽ chạy **khi Stream được đóng**, không phải “khi terminal operation kết thúc”:

```java
import java.util.stream.Stream;

Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("closed"));

stream.forEach(System.out::println);
// Chưa có bảo đảm in "closed".

stream.close(); // lúc này handler close chạy
```

Để bảo đảm handler được gọi cả khi terminal thất bại:

```java
try (Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("closed"))) {
    stream.forEach(System.out::println);
}
```

Trên tệp/Reader/network, nên để `try-with-resources` bao quanh đúng nguồn sở hữu tài nguyên, hoặc bao quanh Stream có close handler đúng. Không dựa vào `forEach`, `findFirst`, `count`, `collect` hay `reduce` để tự đóng nguồn.

### Tài nguyên có vòng đời ngoài Stream

Nếu một database transaction hoặc một kết nối cần rollback/commit, việc đóng Stream chỉ là một phần của giao thức tài nguyên. Một `RuntimeException` từ mapper không đảm bảo transaction tự rollback nếu bạn không quản lý transaction trong tầng gọi. Luôn xác định rõ quyền sở hữu, thứ tự commit/rollback và trách nhiệm phát lại thao tác.

## 16. Retry phải tạo nguồn mới và kiểm soát idempotency

Sau khi pipeline lỗi, Stream **đã hoặc có thể đã bị tiêu thụ một phần**. Không được retry bằng cách gọi terminal lần nữa trên cùng Stream:

```java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<Integer> source = Arrays.asList(1, 2, 3).stream();

int first = source.mapToInt(Integer::intValue).sum();

// SAI: không thể chạy lại terminal trên cùng source.
int second = source.mapToInt(Integer::intValue).sum();
```

Nếu muốn retry xử lý từ dữ liệu có thể tái tạo, hãy dùng **factory tạo Stream mới**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

List<String> values = Arrays.asList("10", "20", "30");
Supplier<Stream<String>> fresh = values::stream;

int attempt1 = fresh.get()
        .mapToInt(Integer::parseInt)
        .sum();

int attempt2 = fresh.get()
        .mapToInt(Integer::parseInt)
        .sum();

System.out.println(attempt1 == attempt2); // true
```

Ví dụ chỉ minh họa việc tạo nguồn mới; **không phải khuyến nghị retry mọi lỗi**. Lỗi parse `"abc"` là lỗi dữ liệu vĩnh viễn, thử lại với cùng input sẽ không giúp ích. Với lỗi tạm thời như I/O, cần xác định số lần thử, khoảng nghỉ, timeout, tính nguyên vẹn của snapshot và xem các tác động ngoài (ghi database, gọi API) có **idempotent** không.

Với `Files.lines`, mỗi lần thử phải mở và đóng một Stream mới. Không giữ lại một Reader đã duyệt dở hoặc đã đóng.

## 17. Null, Optional và exception không nên bị trộn lẫn

Có ba tình huống khác nhau:

- **Không có giá trị hợp lệ**: có thể biểu diễn bằng `Optional.empty()`.
- **Giá trị đầu vào không hợp lệ**: tùy nghiệp vụ có thể trả `ParseResult` thất bại hoặc ném `IllegalArgumentException`.
- **Lỗi hạ tầng khi đọc dữ liệu**: cần giữ thông tin `IOException`/`UncheckedIOException` và chính sách phục hồi riêng.

Ví dụ:

```java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> firstLarge = Arrays.asList(1, 2, 3)
        .stream()
        .filter(n -> n > 100)
        .findFirst();

int fallback = firstLarge.orElse(-1);
System.out.println(fallback); // -1
```

`Optional.empty()` ở đây đơn giản vì **không có số nào lớn hơn 100**, chứ không phải có lỗi I/O. Nếu mapper trước `findFirst` ném `NumberFormatException`, lỗi không tự biến thành Optional rỗng.

### Không trả null làm dấu hiệu lỗi nếu có thể tránh

`map` có thể phát `null`, nhưng nhiều terminal/collector không chấp nhận null hoặc xử lý theo các hợp đồng khác nhau. Ví dụ `Collectors.toMap` không dùng giá trị null như một bản ghi hợp lệ; `findFirst` có thể ném `NullPointerException` nếu phần tử được chọn là null.

Thay vì trả null mỗi khi parse thất bại rồi `filter(Objects::nonNull)`, mẫu `ParseResult` giữ được **nguyên nhân** và **số lượng lỗi**. Nếu thật sự chọn bỏ qua lỗi, hãy ghi rõ đó là chính sách được phép.

## 18. Thông báo lỗi, log và dữ liệu nhạy cảm

Thông báo ngoại lệ có thể giúp chẩn đoán, nhưng cũng có thể vô tình lộ dữ liệu người dùng hoặc nội dung tệp.

Một thông báo lỗi tốt thường chứa:

- Loại thao tác thất bại: mở tệp, đọc dòng, parse, phân nhóm hay kết thúc.
- Định danh nguồn hoặc vị trí phù hợp (nếu được phép): tên luồng dữ liệu, số dòng, mã tác vụ.
- Lỗi gốc được giữ dưới dạng `cause`, thay vì chỉ chuyển thành chuỗi.
- Thông tin hành động: dừng nhập, bỏ qua một bản ghi, hay retry ở tầng có trách nhiệm.

Không nên ghi toàn bộ số thẻ, mật khẩu, token truy cập hoặc dữ liệu nhạy cảm vào exception message. Nếu cần log một dòng bị lỗi, hãy áp dụng quy tắc rút gọn/ẩn dữ liệu của hệ thống và phân biệt log vận hành với báo cáo lỗi dữ liệu.

### Gắn số dòng vào dữ liệu trước khi parse

Nếu muốn báo lỗi kèm vị trí mà không lưu mọi phần tử vào Map ngoài Stream, có thể ghép chỉ số với dòng đã đọc:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<String> raw = Arrays.asList("10", "bad", "30");

List<String> report = IntStream.range(0, raw.size())
        .mapToObj(i -> {
            String text = raw.get(i);
            try {
                int value = Integer.parseInt(text);
                return "line=" + (i + 1) + ", value=" + value;
            } catch (NumberFormatException ex) {
                return "line=" + (i + 1) + ", invalid integer";
            }
        })
        .collect(Collectors.toList());

System.out.println(report);
// [line=1, value=10, line=2, invalid integer, line=3, value=30]
```

Ví dụ dùng List có thứ tự và truy cập theo chỉ số. Với tệp rất lớn, không nên nạp toàn bộ `Files.lines` thành List chỉ để lấy số dòng; có thể thiết kế cấu trúc `LineRecord` được đánh số theo một lượt đọc tuần tự, hoặc dùng API đọc dòng phù hợp. Không dùng một biến `int[]` ngoài pipeline để tăng số dòng từ nhiều luồng song song.

## 19. Kiểm thử lan truyền ngoại lệ

Một bộ kiểm thử nên có cả hành vi bình thường lẫn đầu vào lỗi, không chỉ chạy với dữ liệu đẹp.

| Ca thử | Kỳ vọng |
| --- | --- |
| Dữ liệu hợp lệ | Terminal trả kết quả đúng |
| `map(Integer::parseInt)` gặp chuỗi không hợp lệ | `NumberFormatException` lan ra nếu fail-fast |
| `filter`/`anyMatch` dừng trước phần tử lỗi | Không đòi kiểm tra mọi phần tử |
| `toMap` gặp khóa trùng | Lỗi nếu không có merge policy |
| Nguồn tệp không mở được | Lỗi `IOException` khi tạo nguồn |
| Lỗi I/O khi đọc lazy | `UncheckedIOException` hoặc thông tin nguồn thích hợp |
| Mapper ném lỗi trong `try-with-resources` | Nguồn vẫn được đóng |
| Mapper và close cùng ném | Ngoại lệ chính giữ lỗi xử lý; close được suppressed |
| Song song có nhiều phần tử lỗi | Không giả định phần tử nào được báo trước |
| Dùng `ParseResult` | Có thể tính số hợp lệ/lỗi, tổng bản ghi bảo toàn |
| Nguồn rỗng | Kết quả phù hợp, không “tạo ra” lỗi giả |
| Retry | Nguồn mới; không chạy lại Stream cũ |

### Ví dụ kiểm thử thủ công việc lỗi parse lan ra

```java
import java.util.Arrays;
import java.util.stream.Collectors;

boolean thrown = false;

try {
    Arrays.asList("1", "bad", "3")
            .stream()
            .map(Integer::parseInt)
            .collect(Collectors.toList());
} catch (NumberFormatException ex) {
    thrown = true;
}

if (!thrown) {
    throw new AssertionError("Expected NumberFormatException");
}
```

Lưu ý test này dùng terminal `collect(toList())` để yêu cầu thực sự materialize các phần tử sau `map`. Nếu thay bằng `count()`, không thể dựa vào việc tất cả mapper đều được gọi.

### Ví dụ kiểm thử dữ liệu lỗi được giữ lại

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, Long> counts = Arrays.asList(
        "1", "bad", "3", null
).stream()
 .map(ParseResult::from)
 .collect(Collectors.partitioningBy(
         ParseResult::isValid,
         Collectors.counting()
 ));

if (!Long.valueOf(2L).equals(counts.get(true))
        || !Long.valueOf(2L).equals(counts.get(false))) {
    throw new AssertionError("Incorrect accepted/rejected counts");
}
```

Cách này xác minh **chính sách phân loại** chứ không chỉ tính toán xong một kết quả số. Đối với lỗi không thể phục hồi như nguồn tệp bị hỏng, đừng ép nó trở thành một bản ghi lỗi thông thường nếu xử lý tiếp sẽ tạo kết quả thiếu tin cậy.

## 20. Các bẫy khi “xử lý hết mọi exception” trong pipeline

| Cách viết hoặc giả định | Vấn đề | Thay thế phù hợp |
| --- | --- | --- |
| Bao `try/catch` quanh chỉ `stream.map(...)` | Lambda chưa thực thi | Bao quanh terminal hoặc xử lý trong lambda |
| Nghĩ `count()` buộc mọi `map` chạy | Tối ưu có thể bỏ mapper | Dùng phép tiêu thụ kết quả cần validation |
| Catch `Exception` và trả 0 ở mọi lỗi | Che lỗi nguồn, lỗi lập trình, dữ liệu sai | Phân loại lỗi và chính sách rõ ràng |
| Bắt `IOException` trực tiếp trong `Function` mà không khai báo | Không biên dịch nếu không bắt/wrap đúng | `UncheckedIOException` hoặc kiểu Result |
| Ném `new RuntimeException(ex.getMessage())` | Mất cause/stack trace gốc | Giữ cause trong exception mới |
| Dùng null như “lỗi parse” rồi xóa tất cả | Không thể kiểm toán lỗi bị loại | `ParseResult` hoặc bộ đếm lỗi |
| Nghĩ `collect` tự đóng `Files.lines` | Rò rỉ tài nguyên | `try-with-resources` |
| Nghĩ `BufferedReader.lines().close()` luôn đóng Reader | Không xác định đúng owner | Đóng chính Reader |
| Nghĩ `onClose` chạy khi `forEach` hoàn tất | Handler chỉ chạy khi close | Gọi close hoặc `try-with-resources` |
| Nuốt ngoại lệ close | Che mất lỗi dọn dẹp | Giữ suppressed exceptions/log đầy đủ |
| Retry trên cùng Stream đã dùng | Stream dùng một lần | Factory nguồn mới |
| Retry thao tác gửi/ghi không idempotent | Có thể tạo tác dụng phụ trùng | Thiết kế transaction/idempotency |
| Mong `limit(1)` luôn chạy đúng một mapper trong parallel | Có thể có xử lý thêm ở nhánh khác | Không ràng buộc vào số callback |
| Mong exception đầu tiên theo thứ tự nguồn trong parallel | Lịch thực thi không cố định | Không assert message của phần tử lỗi cụ thể |
| Ghi toàn bộ bản ghi lỗi vào exception/log | Có thể lộ dữ liệu nhạy cảm | Rút gọn, ẩn thông tin không cần thiết |
| Biến mọi `RuntimeException` thành lỗi dữ liệu | Lỗi lập trình có thể bị che | Chỉ bắt lỗi dự kiến, loại khác fail-fast |
| Dùng side effect rồi nghĩ exception rollback | Các tác động trước lỗi vẫn tồn tại | Transaction hoặc xử lý dữ liệu thuần |

## 21. Checklist thiết kế an toàn trước khi đưa vào ứng dụng

1. **Nguồn ở đâu?** Mảng/List trong bộ nhớ, Iterator một lần, `Files.lines`, Reader hay nguồn network?
2. **Điểm mở nguồn có ném checked exception không?** Tách lỗi mở và lỗi duyệt lazy.
3. **Lambda nào có thể ném lỗi?** `map`, `filter`, `flatMap`, classifier, comparator, accumulator?
4. **Terminal có thể ném gì?** `toMap` khóa trùng, `reduce` tràn số, `Optional.get` rỗng?
5. **Lỗi nào thuộc dữ liệu, lỗi nào thuộc hạ tầng?** Không dùng một fallback cho mọi loại.
6. **Cần fail-fast hay kết quả từng bản ghi?** Nếu muốn báo cáo lỗi, thiết kế `Result` và thống kê.
7. **Có bỏ qua phần tử không?** Nếu có, lưu số lượng và chính sách để không làm báo cáo sai.
8. **Có phụ thuộc vào số lần callback chạy không?** `count` và short-circuit có thể bỏ qua thao tác.
9. **Có chạy song song không?** Không dựa vào thứ tự lỗi hoặc side effect; kiểm tra Collector/combiner.
10. **Có nguồn I/O không?** Ai là chủ sở hữu và ai chịu trách nhiệm close?
11. **Nếu xử lý và close cùng lỗi?** Có giữ primary, cause, suppressed exceptions?
12. **Nếu retry?** Có tạo nguồn mới và bảo đảm snapshot/idempotency?
13. **Thông báo lỗi có lộ dữ liệu nhạy cảm không?** Chỉ giữ thông tin cần thiết cho chẩn đoán.
14. **Test có kiểm tra nguồn rỗng, bản ghi lỗi, ngoại lệ tại terminal và đóng tài nguyên không?**

## 22. Bài tập thực hành

### Bài tập A: bắt lỗi ở đúng thời điểm

Tạo `Stream<Integer>` từ `["10","invalid","30"]` bằng `map(Integer::parseInt)`. Đặt `try/catch` quanh phần **khai báo pipeline** rồi quan sát vì sao không thấy lỗi. Chuyển `try/catch` bao quanh `collect(toList())` và giải thích sự khác biệt.

### Bài tập B: chuyển checked exception thành unchecked có nguyên nhân

Dùng `List<Path>` và `Files.size`. Viết mapper bắt `IOException` rồi ném `UncheckedIOException`; ở tầng gọi, kiểm tra `ex.getCause()` là lỗi I/O gốc. Thử một đường dẫn không tồn tại.

### Bài tập C: từ fail-fast sang báo cáo lỗi

Đọc `["10", "abc", "", "-3", null]` thành `ParseResult`. Báo cáo:

```text
accepted = 2
rejected = 3
sum = 7
```

Dùng `partitioningBy` hoặc `ImportSummary`. Không được làm mất số lượng bản ghi đầu vào khi chỉ bỏ các lỗi parse.

### Bài tập D: lỗi từ terminal

Gọi `Collectors.toMap(String::length, s -> s)` trên `["cat","dog"]`. Giải thích `IllegalStateException` do khóa trùng. Đổi sang `groupingBy(String::length)` để giữ cả hai phần tử.

### Bài tập E: exception khi close

Tạo `Stream.of("A").onClose(...)` với close handler ném lỗi; trong `forEach` cũng ném lỗi. Dùng `try-with-resources` và xác nhận ngoại lệ xử lý là primary, lỗi close nằm trong `getSuppressed()`.

### Bài tập F: parallel và short-circuit

Dùng nguồn có nhiều chuỗi sai định dạng. So `findFirst`, `anyMatch`, `collect` trong hai chế độ. Ghi rõ terminal nào **có thể** không kiểm tra mọi phần tử, và vì sao không được viết test ràng buộc phần tử lỗi được báo trước ở parallel.

### Bài tập G: nguồn tệp và vòng đời tài nguyên

Viết hàm đọc tệp điểm, parse từng dòng và thống kê hợp lệ/lỗi. Dùng `Files.lines` trong `try-with-resources`. Thử nguồn rỗng, dòng sai định dạng, thiếu tệp và dữ liệu lớn; phân biệt lỗi mở `IOException` với lỗi duyệt `UncheckedIOException`.

## 23. Câu hỏi tự kiểm tra

1. Vì sao lỗi trong `map` thường không xuất hiện tại dòng tạo pipeline? **Vì intermediate operation thường lazy, chạy khi terminal yêu cầu phần tử**.
2. `NumberFormatException` có phải checked exception không? **Không, nó là `RuntimeException`**.
3. Gọi `map(Integer::parseInt).count()` có bắt buộc parse mọi phần tử không? **Không**, tối ưu có thể bỏ mapper nếu không ảnh hưởng count.
4. `Files.lines(path)` có thể ném gì khi mở nguồn? **`IOException`**.
5. Khi đọc từ `Files.lines` gặp lỗi giữa quá trình duyệt, có thể nhận ngoại lệ nào? **`UncheckedIOException`**.
6. `UncheckedIOException.getCause()` trả loại nào? **`IOException`**.
7. `Function.apply` có cho lambda ném `IOException` trực tiếp mà không xử lý không? **Không**, checked exception không được khai báo trong chữ ký đó.
8. Khi nào nên dùng `UncheckedIOException`? **Khi cần fail-fast qua functional interface và giữ cause I/O**.
9. Khi nào nên dùng kiểu `ParseResult`? **Khi lỗi dữ liệu dự kiến cần được báo cáo thay vì dừng toàn bộ**.
10. Tại sao không nên catch `Exception` rồi trả 0? **Có thể che lỗi nghiêm trọng và làm dữ liệu sai**.
11. `Collectors.toMap` hai tham số gặp khóa trùng sẽ ra sao? **Ném `IllegalStateException`**.
12. `Optional.empty()` có đồng nghĩa pipeline gặp lỗi không? **Không, nó có thể chỉ báo không có kết quả**.
13. `anyMatch` trả `true` có chứng minh mọi bản ghi hợp lệ không? **Không, nó có thể dừng sớm**.
14. Với parallel stream, exception từ phần tử nào phải xuất hiện đầu tiên? **Không có bảo đảm theo thứ tự nguồn**.
15. Nếu `forEach` đã gọi API ngoài rồi ném exception, API ngoài có tự rollback không? **Không**.
16. `collect` có tự đóng `Files.lines` không? **Không**, cần `try-with-resources`.
17. Đối với `BufferedReader.lines()`, nên đóng tài nguyên nào? **Đóng chính BufferedReader sở hữu nguồn**.
18. `onClose` chạy khi terminal hoàn tất hay khi Stream được close? **Khi close**.
19. Nếu xử lý và close cùng lỗi trong `try-with-resources`, lỗi nào là primary? **Lỗi xử lý; lỗi close được ghi ở suppressed exceptions**.
20. Sau một terminal operation lỗi, có nên gọi terminal lại trên cùng Stream không? **Không**, phải tạo Stream mới nếu cần thử lại.
21. Nếu muốn retry I/O, cần cân nhắc gì? **Số lần thử, snapshot và idempotency của tác dụng phụ**.
22. Vì sao cần giữ `cause` và suppressed exceptions? **Để không đánh mất nguyên nhân và lỗi dọn dẹp**.
23. Nếu xử lý nhiều bản ghi và muốn đếm lỗi, nên giữ gì? **Tổng đầu vào, số hợp lệ, số lỗi và chính sách phân loại**.
24. Tại sao cần kiểm thử cả xử lý tuần tự và song song? **Parallel có lịch xử lý và cách gộp khác, có thể lộ lỗi state/combiner**.

**Nguyên tắc áp dụng:** Ngoại lệ trong Java Stream API phải được hiểu theo **thời điểm thực thi** chứ không chỉ theo dòng code nơi khai báo. Phân biệt lỗi khi mở nguồn với lỗi khi duyệt lazy, nhớ rằng callback có thể ném lỗi từ `map`/`filter` tới terminal, và tránh kỳ vọng short-circuit hay parallel sẽ kiểm tra đúng một tập phần tử cố định. Chọn fail-fast hoặc kết quả mang lỗi theo yêu cầu nghiệp vụ, **giữ nguyên cause**, không nuốt lỗi hạ tầng, và luôn quản lý vòng đời tài nguyên bằng `try-with-resources`. Một pipeline an toàn không chỉ trả kết quả đúng khi mọi thứ thuận lợi, mà còn báo lỗi chính xác, có thể chẩn đoán và không làm thất thoát dữ liệu khi gặp sự cố.
