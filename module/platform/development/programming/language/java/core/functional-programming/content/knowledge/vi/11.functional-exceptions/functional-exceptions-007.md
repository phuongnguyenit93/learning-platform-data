# Không nuốt ngoại lệ để làm cho quy trình Stream tiếp tục

## 1. Vấn đề: tiếp tục xử lý không có nghĩa là che giấu lỗi

`Stream` trong Java giúp biểu diễn quy trình lọc, biến đổi và tổng hợp dữ liệu. Một cách xử lý lỗi nguy hiểm là bắt ngoại lệ ngay trong lambda, không ghi nhận nó, rồi trả về một giá trị mặc định hoặc bỏ phần tử để pipeline có vẻ như vẫn chạy:

```java
// Ví dụ phản diện: đoạn trích minh họa, không phải chương trình độc lập.
List<Integer> values = rawValues.stream()
        .map(raw -> {
            try {
                return Integer.parseInt(raw);
            } catch (Exception ignored) {
                return null;
            }
        })
        .filter(Objects::nonNull)
        .toList();
```

Nếu `rawValues` có phần tử `"abc"`, kết quả chỉ chứa những phần tử chuyển được thành số. Nhưng hệ thống **không biết** bản ghi `"abc"` đã thất bại, thất bại vì sao, hoặc có bao nhiêu dữ liệu mất. Cách viết này còn bắt cả những `RuntimeException` khác ngoài lỗi chuyển số, khiến lỗi lập trình dễ bị ngụy trang thành dữ liệu không hợp lệ.

Một pipeline chạy đến cuối **chưa chứng minh** rằng tất cả dữ liệu được xử lý thành công. “Không nuốt ngoại lệ” có nghĩa là phải giữ đúng ngữ nghĩa của lỗi và chính sách xử lý đã thống nhất:

- **Lỗi cần dừng xử lý:** để ngoại lệ lan lên nơi có trách nhiệm xử lý, hoặc đóng gói lại với ngữ cảnh rồi ném tiếp.
- **Lỗi dự kiến và có thể xử lý trên từng phần tử:** tạo kết quả thất bại tường minh, giữ nguyên nhân và vị trí bản ghi để báo cáo; phần tử còn lại có thể tiếp tục.
- **Dữ liệu được phép loại bỏ theo nghiệp vụ:** dùng `filter` hoặc `Optional` theo quy tắc đã công bố, nhưng vẫn cần xác định liệu việc loại bỏ có cần thống kê hoặc truy vết hay không.

Điều quan trọng là **chọn chính sách có chủ đích**, không thêm `catch` rộng hoặc `return null` chỉ để Stream hoàn thành terminal operation.

## 2. Cơ chế ngoại lệ trong Stream

Stream có hai đặc điểm liên quan trực tiếp đến xử lý lỗi.

### Thực thi lười và terminal operation

Các bước trung gian như `map`, `filter` và `flatMap` thường lười: chúng thiết lập pipeline, còn công việc diễn ra khi terminal operation như `toList()`, `collect(...)`, `count()`, `reduce(...)` hoặc `forEach(...)` yêu cầu phần tử.

```java
Stream<String> pipeline = Stream.of("10", "bad", "20");
Stream<Integer> mapped = pipeline.map(Integer::parseInt);
// Chưa cần chuyển chuỗi sang số tại hai dòng trên.

List<Integer> result = mapped.toList();
// NumberFormatException xuất hiện trong quá trình toList().
```

Ở đây `Integer.parseInt("bad")` ném `NumberFormatException`. Khi ngoại lệ không được xử lý trong pipeline, terminal operation kết thúc bất thường; `toList()` không trả về một danh sách kết quả hoàn chỉnh. Không có cơ chế mặc định “bỏ phần tử lỗi rồi tiếp tục” và không thể tiếp tục dùng lại Stream đã tiêu thụ sau đó.

### Lambda không tự động thay đổi hợp đồng ngoại lệ

Các functional interface chuẩn như `Function<T,R>`, `Predicate<T>` và `Consumer<T>` có phương thức trừu tượng không khai báo `throws` checked exception. Vì thế đoạn mã sau không hợp lệ nếu `read` khai báo `throws IOException`:

```java
// Ví dụ minh họa, không biên dịch khi read(Path) throws IOException:
List<String> lines = paths.stream()
        .map(path -> read(path))
        .toList();
```

Checked exception cần xử lý bằng cách phù hợp: chuyển đổi sang lỗi unchecked có ngữ cảnh và ném tiếp, xử lý tại ranh giới nghiệp vụ, hoặc biểu diễn một `Result` chứa thành công/thất bại. Không nên thêm `catch (Exception ignored)` chỉ để lambda hợp kiểu.

### Đừng đánh đồng lỗi dữ liệu và lỗi hệ thống

`NumberFormatException` từ chuỗi đầu vào không phải số có thể là **lỗi dữ liệu dự kiến** trong luồng import. Ngược lại, `NullPointerException` do bug, lỗi cấu hình, trạng thái đối tượng sai hoặc `IOException` từ hạ tầng không nên mặc nhiên được phân loại như một dòng CSV thiếu dữ liệu. Việc phân loại dựa trên hợp đồng nghiệp vụ và điều kiện bắt ngoại lệ cụ thể.

## 3. Hai chính sách xử lý thường gặp

| Chính sách | Khi áp dụng | Stream làm gì? | Cách quan sát lỗi |
| --- | --- | --- | --- |
| **Fail-fast** | Một lỗi khiến kết quả không còn đáng tin, phải rollback hoặc cần người gọi quyết định | Ném lỗi; terminal operation có thể kết thúc bất thường | Ngoại lệ với nguyên nhân, ngữ cảnh ở ranh giới xử lý |
| **Continue with recorded failures** | Các bản ghi độc lập, lỗi một bản ghi không làm sai kết quả của bản ghi khác | Mỗi phần tử cho kết quả `Success` hoặc `Failure`; pipeline tiếp tục qua lỗi dự kiến | Danh sách thất bại, mã lỗi, vị trí dòng, số lượng và báo cáo |
| **Skip by defined rule** | Việc loại bỏ là một bước nghiệp vụ hợp lệ, ví dụ bỏ dòng trống | `filter` hoặc kết quả không có giá trị được dùng theo hợp đồng | Quy tắc loại bỏ và thống kê nếu cần |

Trong một luồng nhập dữ liệu, có thể cho phép tiếp tục sau lỗi định dạng của một dòng. Trong một lệnh chuyển tiền gồm các bước phụ thuộc nhau, việc âm thầm bỏ qua một bước thất bại có thể tạo trạng thái sai nghiêm trọng. Chính sách cần được chọn theo khả năng khôi phục và mức độ phụ thuộc giữa các bước, không dựa trên mục tiêu “không bị exception”.

## 4. Fail-fast: để ngoại lệ đến đúng nơi xử lý

Khi một lỗi phải khiến toàn bộ thao tác thất bại, hãy để ngoại lệ lan ra. Nếu cần thông tin dòng, bọc lỗi bằng ngoại lệ có ngữ cảnh và giữ `cause` gốc:

```java
// Phương thức minh họa: đặt trong một class có import java.util.*.
static List<Integer> parseAllStrict(List<String> lines) {
    return java.util.stream.IntStream.range(0, lines.size())
            .mapToObj(index -> {
                String raw = lines.get(index);
                try {
                    return Integer.parseInt(raw);
                } catch (NumberFormatException cause) {
                    throw new IllegalArgumentException(
                            "Invalid integer at line " + (index + 1),
                            cause);
                }
            })
            .toList();
}
```

Với `List.of("10", "bad", "20")`, lời gọi `parseAllStrict(...)` kết thúc bằng `IllegalArgumentException` có thông điệp chỉ dòng 2 và `NumberFormatException` là nguyên nhân. Dòng lỗi không bị thay thành `0`, `null`, hay bị xóa khỏi báo cáo.

Lưu ý: với một Stream tuần tự có thứ tự như ví dụ, việc xử lý phần tử xảy ra theo nhu cầu của terminal operation. Không nên xây logic dựa trên giả định tất cả phần tử trước vị trí lỗi đã được ghi thành công bên ngoài. Nếu lambda có tác dụng phụ, một số tác dụng phụ có thể đã xảy ra trước khi exception thoát ra; Stream **không cung cấp transaction/rollback**. Việc hoàn tác phải do cơ chế giao dịch hoặc điều phối nghiệp vụ đảm trách.

## 5. Tiếp tục có trách nhiệm: trả về kết quả có cả thất bại

Một luồng kiểm tra độc lập từng bản ghi có thể sử dụng kiểu kết quả đại diện hai nhánh:

```text
Input row
   │
   ▼
Validate/parse
   ├── Thành công → Accepted(line, raw, value)
   └── Thất bại  → Rejected(line, raw, reason)
                    │
                    ▼
         Tổng hợp kết quả và lỗi
```

Trong Java 17, `record` lưu dữ liệu bất biến ở mức các thành phần tham chiếu được khai báo, còn `sealed interface` giới hạn rõ hai loại kết quả. Ta bắt **đúng lỗi dự kiến** (`NumberFormatException`) trong phạm vi chuyển đổi số; không có `catch (Exception)` chung, không dùng `null` làm tín hiệu mất dữ liệu.

Ví dụ nghiệp vụ:

- Chuỗi `null` hoặc rỗng: thất bại `missing input`.
- Chuỗi không biểu diễn một `int` hợp lệ (kể cả số vượt giới hạn `int`): thất bại `not a valid int`.
- Số âm: thất bại `negative not allowed`.
- Số nguyên không âm: thành công; cho phép số `0`.

Mỗi đầu vào có đúng **một kết quả**, nhờ vậy luôn có thể kiểm tra tổng số thành công cộng thất bại bằng tổng số dòng.

## 6. Ví dụ Java 17+ độc lập, chạy được

Tạo file `StreamErrorHandlingDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

public class StreamErrorHandlingDemo {
    sealed interface Outcome permits Accepted, Rejected {}

    record Accepted(int line, String raw, int value) implements Outcome {}

    record Rejected(int line, String raw, String reason) implements Outcome {}

    static Outcome parseOne(int line, String raw) {
        if (raw == null || raw.isBlank()) {
            return new Rejected(line, raw, "missing input");
        }

        final int value;
        try {
            value = Integer.parseInt(raw.strip());
        } catch (NumberFormatException cause) {
            return new Rejected(line, raw, "not a valid int");
        }

        if (value < 0) {
            return new Rejected(line, raw, "negative not allowed");
        }
        return new Accepted(line, raw, value);
    }

    static List<Outcome> process(List<String> inputs) {
        return IntStream.range(0, inputs.size())
                .mapToObj(i -> parseOne(i + 1, inputs.get(i)))
                .toList();
    }

    static List<Integer> acceptedValues(List<Outcome> outcomes) {
        return outcomes.stream()
                .filter(Accepted.class::isInstance)
                .map(Accepted.class::cast)
                .map(Accepted::value)
                .toList();
    }

    static List<Rejected> failures(List<Outcome> outcomes) {
        return outcomes.stream()
                .filter(Rejected.class::isInstance)
                .map(Rejected.class::cast)
                .toList();
    }

    static void checkEquals(Object expected, Object actual, String label) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<String> inputs = Arrays.asList(
                "10", "abc", " 20 ", null, "-3", "30");

        List<Outcome> expected = List.of(
                new Accepted(1, "10", 10),
                new Rejected(2, "abc", "not a valid int"),
                new Accepted(3, " 20 ", 20),
                new Rejected(4, null, "missing input"),
                new Rejected(5, "-3", "negative not allowed"),
                new Accepted(6, "30", 30));

        List<Outcome> actual = process(inputs);
        checkEquals(expected, actual, "one outcome per input");
        checkEquals(List.of(10, 20, 30),
                acceptedValues(actual), "accepted values");
        checkEquals(3, failures(actual).size(), "failure count");
        checkEquals(new Accepted(1, "0", 0),
                parseOne(1, "0"), "zero is accepted");
        checkEquals(new Rejected(1, "", "missing input"),
                parseOne(1, ""), "empty string");
        checkEquals(new Rejected(1, "2147483648", "not a valid int"),
                parseOne(1, "2147483648"), "integer overflow");

        List<String> anotherInput = new ArrayList<>();
        anotherInput.add(null);
        anotherInput.add("bad");
        checkEquals(2, failures(process(anotherInput)).size(),
                "all invalid inputs have visible failures");
    }

    public static void main(String[] args) {
        runTests();
        System.out.println("tests=PASS");

        List<String> inputs = Arrays.asList(
                "10", "abc", " 20 ", null, "-3", "30");
        List<Outcome> outcomes = process(inputs);

        List<Integer> values = acceptedValues(outcomes);
        List<Rejected> errors = failures(outcomes);

        System.out.println("accepted=" + values);
        for (Rejected error : errors) {
            System.out.println("line=" + error.line()
                    + " input=" + error.raw()
                    + " reason=" + error.reason());
        }
        System.out.println("successes=" + values.size()
                + ", failures=" + errors.size());
    }
}
```

Biên dịch và chạy:

```bash
javac StreamErrorHandlingDemo.java
java StreamErrorHandlingDemo
```

Kết quả stdout:

```text
tests=PASS
accepted=[10, 20, 30]
line=2 input=abc reason=not a valid int
line=4 input=null reason=missing input
line=5 input=-3 reason=negative not allowed
successes=3, failures=3
```

**Đối chiếu hành vi:**

1. `process` dùng `IntStream.range` để giữ chỉ số nguồn, chuyển thành số dòng bắt đầu từ 1.
2. `parseOne` luôn tạo `Accepted` hoặc `Rejected` khi gặp các đầu vào theo hợp đồng; nó không `return null`, cũng không ghi lỗi rồi giả vờ thành công.
3. `NumberFormatException` chỉ được bắt quanh `Integer.parseInt(...)`. Khi chuỗi không phải số `int`, thay vì coi một exception không xác định là lỗi dữ liệu, chương trình trả về nguyên nhân cụ thể `not a valid int`.
4. Các trường hợp số âm được phân loại bằng kiểm tra nghiệp vụ sau khi parse thành công; không dùng exception để diễn tả một điều kiện kiểm tra bình thường.
5. `failures` và `acceptedValues` được đọc từ cùng danh sách `Outcome`, nên báo cáo không bỏ quên bản ghi.
6. `runTests` so sánh kết quả đầy đủ, thứ tự dòng, giá trị, lỗi và ca biên, ném `AssertionError` nếu sai. Test không phụ thuộc tùy chọn JVM `-ea`.

Trong ví dụ này `raw` được hiển thị vì dữ liệu thử nghiệm không nhạy cảm. Khi sử dụng thật, tránh lưu hoặc in số tài khoản, token, dữ liệu cá nhân hoặc toàn bộ thông điệp ngoại lệ có thể chứa bí mật. Nên chọn mã lỗi ổn định, lưu chỉ số dòng và dữ liệu đã ẩn thông tin nhạy cảm.

## 7. Vì sao `Optional.empty()` hoặc `Stream.empty()` đôi khi vẫn là “nuốt lỗi”?

`Optional` và `Stream.empty()` hoàn toàn hợp lệ khi bản chất nghiệp vụ là “không có giá trị” hoặc “phần tử này được phép bỏ qua”. Nhưng ví dụ dưới đây sẽ che giấu lỗi nhập liệu nếu không có cơ chế quan sát khác:

```java
// Phản ví dụ: lỗi parse bị biến thành sự vắng mặt, không có lý do.
static java.util.stream.Stream<Integer> parseOrDrop(String text) {
    try {
        return java.util.stream.Stream.of(Integer.parseInt(text));
    } catch (NumberFormatException ignored) {
        return java.util.stream.Stream.empty();
    }
}
```

Gọi `raw.stream().flatMap(MyClass::parseOrDrop).toList()` có thể trả về danh sách số hợp lệ nhưng không thể phân biệt “dòng được phép bỏ” với “dòng bị lỗi”. Nếu tiêu chí là **bỏ các dòng trống theo đặc tả**, dùng `filter(s -> !s.isBlank())` thường rõ hơn. Nếu phần tử sai dữ liệu phải được thống kê, hãy tạo `Rejected` như ví dụ đầy đủ.

Không nên tự suy luận rằng dùng `Optional` là sai: sai hay đúng phụ thuộc vào **hợp đồng báo lỗi**. Khi hợp đồng đã định nghĩa “không có dữ liệu” là kết quả bình thường, `Optional.empty()` có thể chính là biểu diễn phù hợp. Cần tránh dùng nó như nơi giấu ngoại lệ ngoài dự kiến.

## 8. Xử lý checked exception trong lambda

Ví dụ thao tác I/O:

```java
// Minh họa trong class có import java.nio.file.* và java.io.*.
static String readText(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new java.io.UncheckedIOException(
                "Cannot read: " + path, cause);
    }
}
```

Khi dùng:

```java
// Minh họa, cần có List<Path> paths.
List<String> texts = paths.stream()
        .map(MyClass::readText)
        .toList();
```

`UncheckedIOException` giữ `IOException` gốc làm nguyên nhân và buộc lỗi được xử lý tại ranh giới có đủ ngữ cảnh. Nếu ứng dụng muốn tiếp tục đọc file khác, có thể trả về `ReadSuccess`/`ReadFailure` và tập hợp báo cáo thay vì ném ngay. Điều đó phải được quyết định rõ: có trường hợp đọc thiếu một file khiến toàn bộ kết quả không còn hợp lệ.

**Không bắt `Throwable` hoặc `Error` để giữ pipeline chạy.** Những tình huống như cạn bộ nhớ hoặc lỗi nghiêm trọng của VM không phải lỗi nhập liệu bình thường. Với `InterruptedException`, nếu phải bắt và không ném lại checked exception, thường cần khôi phục trạng thái ngắt bằng `Thread.currentThread().interrupt()` và chuyển điều khiển theo chính sách hủy thao tác. Không cố tiếp tục xử lý bình thường sau tín hiệu hủy như thể không có gì xảy ra.

## 9. Cảnh báo về `parallelStream`, `peek` và tác dụng phụ

Một cách xử lý lỗi tưởng tiện là thêm vào `catch` một lệnh `errors.add(...)`, rồi cho pipeline tiếp tục:

```java
// Phản ví dụ: chia sẻ ArrayList không an toàn khi chạy song song.
List<String> errors = new ArrayList<>();
List<Integer> values = raw.parallelStream()
        .map(s -> {
            try {
                return Integer.parseInt(s);
            } catch (NumberFormatException e) {
                errors.add(s);
                return null;
            }
        })
        .filter(Objects::nonNull)
        .toList();
```

`ArrayList` không an toàn cho các cập nhật đồng thời, nên việc thêm lỗi từ nhiều thread có thể làm mất bản ghi hoặc dẫn đến hỏng trạng thái. Ngay cả với Stream tuần tự, cách này khiến đánh giá kết quả phụ thuộc vào tác dụng phụ và không gắn rõ lỗi với từng bản ghi.

Một cách tốt hơn là **trả về kết quả dưới dạng dữ liệu**, sau đó dùng một terminal operation thu thập `Outcome`. Có thể tách thành accepted/rejected bằng các phép duyệt không làm thay đổi nguồn. Với workload lớn, cân nhắc một collector phù hợp nếu cần tổng hợp một lượt; ưu tiên tính rõ ràng và đo hiệu năng thực tế.

`peek` chủ yếu phục vụ quan sát hoặc gỡ lỗi; không nên dựa vào `peek` để tạo nhật ký lỗi nghiệp vụ bắt buộc. Một số phép tối ưu hóa/terminal operation không đảm bảo lambda `peek` được gọi cho tất cả phần tử theo cách bạn dự đoán. Khi chạy song song, thời điểm tác dụng phụ xảy ra và thứ tự báo lỗi có thể khác thứ tự dữ liệu nguồn.

Nếu pipeline xử lý song song rồi có lỗi chưa bắt, không nên suy diễn rằng mọi phần tử trước lỗi đều đã được xử lý hoặc rằng các phần tử khác lập tức dừng đúng thời điểm ấy. Trong ví dụ chính, dùng `IntStream.range` tuần tự để vị trí lỗi và thứ tự báo cáo xác định.

## 10. Kiểm thử hành vi thất bại: cần chứng minh điều gì?

Một test tốt cho chính sách lỗi phải kiểm tra được:

| Tình huống | Hành vi kỳ vọng |
| --- | --- |
| Dữ liệu hợp lệ | Xuất hiện đúng một kết quả thành công |
| Sai định dạng có thể khôi phục | Có `Rejected` kèm chỉ số và lý do |
| Dữ liệu rỗng/`null` | Có kết quả bị từ chối đúng quy tắc, không phát sinh `NullPointerException` tình cờ |
| Hết giới hạn số nguyên | Được phân loại là lỗi parse, không thay bằng `0` |
| Có nhiều lỗi xen kẽ dữ liệu hợp lệ | Mọi bản ghi có kết quả, không thất lạc vị trí |
| Tất cả phần tử đều không hợp lệ | Danh sách thành công rỗng, lỗi vẫn đầy đủ |
| Lỗi ngoài phạm vi được cho phép tiếp tục | Exception phải lan lên, có thể giữ `cause`, không bị đổi thành thành công |
| Dùng Stream song song hoặc có tác dụng phụ | Đảm bảo thread safety và chính sách thứ tự khi thực sự cần |

Trong ví dụ, `runTests()` kiểm tra nhiều dòng thành công/thất bại, `null`, rỗng, vượt giới hạn và cả trường hợp tất cả sai. Ngoài kiểm tra đầu ra, với bài toán thực tế nên có test xác minh **mã lỗi** ổn định, tổng số dòng vào bằng tổng thành công và thất bại, không ghi dữ liệu nhạy cảm, và không tiếp tục sau lỗi hạ tầng không được phép khôi phục.

Đối với fail-fast, kiểm thử exception rõ ràng. Với JUnit 5 có thể dùng `assertThrows(IllegalArgumentException.class, () -> parseAllStrict(List.of("1", "bad")))` và kiểm tra `getCause() instanceof NumberFormatException`. Câu lệnh JUnit ở đây là ví dụ minh họa, cần dependency JUnit và import tương ứng; chương trình Java 17 ở phần 6 không yêu cầu JUnit.

## 11. Các lỗi thiết kế cần tránh

**1. `catch (Exception e) { return null; }`.** Trộn lỗi dữ liệu và lỗi lập trình, xóa thông tin nguyên nhân, tạo nguy cơ `NullPointerException` ở bước sau.

**2. `catch (RuntimeException ignored) { return defaultValue; }`.** Một giá trị mặc định “hợp lệ” như `0`, `false` hoặc chuỗi rỗng có thể đi tiếp vào tổng hợp, làm sai thống kê, doanh thu hoặc quyết định nghiệp vụ. Chỉ dùng fallback khi đã định nghĩa rõ và có khả năng quan sát việc fallback.

**3. Chỉ `printStackTrace()` hoặc `log.error()` rồi bỏ lỗi.** Ghi log giúp chẩn đoán nhưng không thay thế chính sách trả về, ném lỗi hay báo cáo. Hệ thống gọi hàm có thể vẫn hiểu rằng mọi thứ thành công nếu không nhận tín hiệu thất bại.

**4. Bắt ngoại lệ bao trùm toàn bộ phép biến đổi.** `catch` quá rộng khiến lỗi phân tích cú pháp, lỗi DB và bug trong bước định dạng bị phân loại thành cùng một loại. Hãy đặt `try/catch` quanh thao tác mà bạn hiểu rõ ngoại lệ dự kiến.

**5. Dùng `filter` để che dữ liệu hỏng.** Quy tắc lọc phải giải thích được vì sao loại phần tử. Một lỗi bất ngờ không tự biến thành “phần tử không cần thiết” chỉ vì nó nằm trong Stream.

**6. Tin rằng terminal operation thành công đồng nghĩa dữ liệu đầy đủ.** `count()` hoặc `toList()` có thể thành công dù nhiều dòng trước đó đã bị âm thầm xóa. Cần đối soát số lượng và thông tin lỗi theo hợp đồng.

**7. Dùng lại Stream đã lỗi hoặc tiêu thụ.** Stream là luồng xử lý dùng một lần. Khi terminal operation kết thúc (kể cả thất bại), không được coi đó là luồng có thể “chạy tiếp từ dòng lỗi”; hãy thiết kế từ nguồn dữ liệu có thể lặp lại và chính sách xử lý rõ ràng nếu cần thử lại.

**8. Bỏ qua giao dịch và tính nhất quán.** Pipeline có tác dụng phụ như gửi email, ghi DB, gọi API có thể đã thực hiện một phần trước khi exception xuất hiện. Không giả định Stream tự hủy những tác dụng phụ đó; cần transaction, idempotency, retry policy, hoặc cơ chế bù trừ theo từng hệ thống.

## 12. Bài tập củng cố

1. Thay quy tắc số âm thành chấp nhận các giá trị từ 0 đến 100. Bổ sung lý do `too large` cho giá trị lớn hơn 100 và test với 100, 101, `-1`.
2. Nâng kết quả thất bại thành `Rejected(line, raw, errorCode, message)`; viết hàm tổng hợp số lỗi theo `errorCode` mà không dựa vào nội dung log.
3. Viết hàm fail-fast biến đổi một danh sách chuỗi sang `List<Integer>` và test rằng phần tử `"abc"` ở dòng 2 khiến ngoại lệ chỉ rõ dòng 2, giữ `NumberFormatException` trong `getCause()`.
4. Giả sử dữ liệu gồm các dòng bí mật: thiết kế hàm hiển thị lỗi chỉ chứa số dòng và mã lỗi, không trả hoặc log chuỗi đầu vào gốc.
5. Giải thích sự khác nhau giữa bỏ dòng trống bằng `filter` theo đặc tả và bỏ một dòng do `NumberFormatException` nhưng không ghi nhận lỗi.
6. Chỉ ra điều gì có thể sai khi `parallelStream()` cùng thêm lỗi vào một `ArrayList`, rồi sửa bằng cách thu thập các `Outcome` bất biến.

Một quy trình Stream bền vững cần phân biệt **điều kiện nghiệp vụ được phép bỏ qua**, **lỗi có thể khôi phục cần ghi nhận**, và **lỗi phải dừng xử lý**. Khi cho phép tiếp tục, hãy đưa thất bại thành một phần của dữ liệu kết quả để hệ thống vẫn nhìn thấy điều đã xảy ra.
