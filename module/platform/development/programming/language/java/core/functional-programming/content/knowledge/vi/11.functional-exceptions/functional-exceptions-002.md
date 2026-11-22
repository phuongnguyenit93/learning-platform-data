# Vì sao `Function` và `Consumer` không khai báo checked exception?

## 1. Câu trả lời từ chữ ký API

Hai functional interface rất phổ biến trong `java.util.function` có phương thức trừu tượng (*single abstract method*, SAM) như sau:

```java
@FunctionalInterface
public interface Function<T, R> {
    R apply(T value);
}

@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
}
```

Các chữ ký trên được **rút gọn để minh họa**; API JDK thật còn có các phương thức mặc định/tĩnh như `Function.andThen`, `Function.compose`, `Function.identity` và `Consumer.andThen`. Điểm quan trọng là **`apply` và `accept` không có mệnh đề `throws` khai báo checked exception**.

Do đó, khi truyền lambda hoặc method reference vào một chỗ yêu cầu `Function<T,R>`/`Consumer<T>`, compiler kiểm tra thân lambda theo hợp đồng `apply`/`accept`. Một thao tác có thể ném **checked exception** chưa được bắt, như `IOException`, không thể được chuyển tiếp trực tiếp qua các phương thức này. Java yêu cầu xử lý checked exception tại chỗ hoặc dùng một functional interface có chữ ký `throws` thích hợp.

Ví dụ minh họa lỗi biên dịch:

```java
import java.io.IOException;
import java.util.function.Function;

static String load(String id) throws IOException {
    return id;
}

// SAI: Function.apply(String) không khai báo throws IOException.
// Function<String, String> loader = id -> load(id);
// Function<String, String> alsoBad = MyClass::load;
```

Đây là ví dụ chứa phương thức `static` để đặt trong một lớp giả định, không phải chương trình độc lập. Với `load` khai báo `throws IOException`, compiler không thể dùng lambda/method reference ấy làm `Function<String,String>` nếu exception chưa được xử lý. Lỗi xuất hiện **ngay khi biên dịch**, bất kể đường chạy cụ thể có thực sự phát sinh `IOException` hay không.

**Nội dung cốt lõi:** đây là một **quyết định thiết kế chữ ký API** và là hệ quả của **kiểm tra ngoại lệ theo kiểu đích của lambda** trong Java. Không có quy tắc nào nói mọi lambda đều cấm checked exception; giới hạn xuất hiện khi functional interface đích không cho phép ném loại checked exception đó.

## 2. Phân biệt checked và unchecked exception

Java có những nhóm throwable khác nhau:

| Nhóm | Ví dụ | Kiểm tra khi biên dịch |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException`, `ParseException`, `InterruptedException` | Phải bắt hoặc khai báo truyền tiếp qua một chữ ký cho phép |
| Unchecked exception (`RuntimeException` và lớp con) | `IllegalArgumentException`, `NullPointerException`, `UncheckedIOException` | Không bắt buộc khai báo `throws` |
| `Error` và lớp con | `OutOfMemoryError`, `StackOverflowError` | Không phải checked exception; thường không phù hợp để phục hồi như lỗi nghiệp vụ |

Một ngoại lệ checked là lớp con của `Throwable` **không** thuộc `RuntimeException` hoặc `Error` và các lớp con của hai loại đó. Những ngoại lệ unchecked có thể được truyền qua `Function.apply`/`Consumer.accept` dù hai phương thức không có mệnh đề `throws`.

Ví dụ:

```java
Function<String, Integer> parse = Integer::parseInt;
System.out.println(parse.apply("42")); // 42
// parse.apply("abc"); // Ném NumberFormatException (unchecked).
```

`Integer.parseInt` có thể ném `NumberFormatException`, vốn là `RuntimeException`. Do vậy method reference trên vẫn hợp lệ. “Không khai báo checked exception” **không đồng nghĩa** “không bao giờ ném ngoại lệ”.

### Quy tắc compile-time dựa trên kiểu đã khai báo

Java xét **khả năng ném checked exception của biểu thức theo khai báo phương thức**, thay vì chờ chạy thử. Một phương thức khai báo `throws IOException` sẽ khiến compiler yêu cầu cách xử lý tương thích, kể cả khi dữ liệu mẫu hiện tại không làm nó ném lỗi. Điều này cho phép compiler phát hiện ràng buộc trước runtime.

Ví dụ:

```java
static String read(String code) throws java.io.IOException {
    if (code.equals("BAD")) {
        throw new java.io.IOException("cannot read");
    }
    return code;
}
```

Không thể dùng trực tiếp `Function<String,String> f = Example::read` nếu `read` là phương thức ở lớp `Example` như trên. Phải chọn cách xử lý ngoại lệ phù hợp. Ngoại lệ xảy ra hay không với `"GOOD"` không thay đổi sự không tương thích kiểu.

## 3. Vì sao `java.util.function` chọn những chữ ký đơn giản?

`Function` và `Consumer` là **các giao diện chức năng đa dụng**, được sử dụng trong rất nhiều API: `Stream.map`, `Stream.forEach`, `Optional.map`, `Map.computeIfAbsent`, callback, bộ chuyển đổi dữ liệu, v.v. Thiết kế JDK chọn chữ ký SAM ngắn gọn, không có tham số kiểu hay mệnh đề `throws` cho checked exception.

Các hệ quả thực tế:

1. **Dùng đơn giản với các thao tác thuần trong bộ nhớ.** Nhiều mapper/consumer chỉ biến đổi dữ liệu, so sánh hoặc ghi kết quả cục bộ và không có nhu cầu truyền checked exception.
2. **Hợp đồng thống nhất cho các API tổng quát.** `Stream.map` nhận `Function<? super T,? extends R>`, còn `forEach` nhận `Consumer<? super T>`; các API không phải làm việc với một kiểu ngoại lệ checked tùy biến trên mỗi lambda.
3. **Chính sách lỗi được quyết định ở ranh giới ứng dụng.** Khi tác vụ đụng I/O, database hoặc network, người viết phải chọn bắt, chuyển đổi, lưu lỗi dưới dạng dữ liệu, hoặc định nghĩa một giao diện có `throws`.
4. **Đổi lại có chi phí cho I/O trong pipeline.** Một method reference tới API có `throws IOException` thường không dùng trực tiếp được như `Function`. Phải thêm code thích ứng (*adapter*) hoặc tổ chức lại luồng xử lý.

Không nên diễn giải rằng “functional programming không có checked exception”. Java vẫn hỗ trợ SAM khai báo checked exception, chẳng hạn `Callable<V>.call() throws Exception`. Việc `Function`/`Consumer` không khai báo `throws` là **hợp đồng cụ thể của hai interface này**, không phải hạn chế chung của tất cả functional interface hay của lambda.

## 4. Ngữ cảnh kiểu đích quyết định lambda có được `throws` hay không

Lambda được kiểm tra dựa trên *target type*. Hai interface có cùng kiểu đầu vào/đầu ra có thể khác nhau về ngoại lệ:

```java
import java.io.IOException;
import java.util.function.Function;

@FunctionalInterface
interface CheckedLoader {
    String load(String id) throws IOException;
}
```

Với phương thức `static String fetch(String id) throws IOException`:

```java
// Hợp lệ: SAM khai báo throws IOException.
CheckedLoader good = id -> fetch(id);

// Không hợp lệ: Function.apply không cho checked IOException.
// Function<String, String> bad = id -> fetch(id);
```

Đây là các đoạn **minh họa**, cần đặt `fetch` và các khai báo vào ngữ cảnh lớp/phương thức phù hợp. Điểm khác biệt không nằm ở cú pháp `->`: cùng một lambda có thể hợp lệ cho `CheckedLoader` nhưng không hợp lệ cho `Function<String,String>`.

Method reference cũng chịu quy tắc này:

```java
CheckedLoader good = Example::fetch;
// Function<String, String> bad = Example::fetch; // Không compile.
```

`Example::fetch` chỉ là một tham chiếu tới phương thức; compiler vẫn phải xác nhận checked exception của phương thức được tham chiếu phù hợp với `throws` của SAM đích.

### `try/catch` trong lambda được phép

`Function` không cấm **gọi** phương thức có checked exception nếu lambda tự xử lý nó:

```java
Function<String, String> safe = id -> {
    try {
        return fetch(id);
    } catch (IOException ex) {
        return "UNAVAILABLE";
    }
};
```

Ở đây `IOException` đã được bắt, nên phần thân lambda không còn truyền checked exception chưa xử lý ra khỏi `apply`. Lựa chọn chuỗi `"UNAVAILABLE"` chỉ là chính sách ví dụ: trong hệ thống thật, trả giá trị mặc định có thể che giấu lỗi, vì thế phải quy định rõ cách phân biệt lỗi với dữ liệu hợp lệ.

## 5. Ba hướng xử lý phổ biến

Một thao tác có `throws IOException` khi được đưa vào `Function`/`Consumer` thường có ba hướng thiết kế chính:

| Hướng | Kết quả quan sát được | Phù hợp khi |
| --- | --- | --- |
| Bắt và xử lý ngay trong lambda | Lambda tiếp tục hoặc trả fallback | Có chính sách phục hồi rõ ràng |
| Bọc thành unchecked exception | Pipeline thất bại nếu caller không bắt | Lỗi phải làm dừng thao tác, caller chịu trách nhiệm |
| Trả lỗi như một giá trị (*Result*) | Mỗi phần tử có trạng thái thành công/thất bại | Cần xử lý nhiều phần tử và báo lỗi riêng từng phần tử |

Không có một giải pháp luôn đúng. Phải cân nhắc bài toán có cần **fail-fast** (dừng ở lỗi đầu) hay **collect-all** (tiếp tục xử lý các phần tử khác), có side effect hay không, có cần retry hay giữ nguyên nguyên nhân gốc không.

Nếu xử lý checked exception bằng cách bọc thành unchecked, **không hề biến lỗi thành thành công**. Bạn chỉ thay đổi cách ngoại lệ đi qua hợp đồng Java của `Function`/`Consumer`. Lỗi vẫn xuất hiện ở runtime, chỉ khác rằng compiler không bắt buộc mọi caller của `apply` phải khai báo `throws`.

## 6. Ví dụ Java 17 hoàn chỉnh: fail-fast, Result và Consumer có I/O

Chương trình dưới đây mô phỏng một nguồn dữ liệu có thể ném `IOException`. Nó minh họa:

- `Function<String,String>` được tạo bằng adapter bọc checked `IOException` thành `UncheckedIOException`.
- `Function<String,Outcome>` ghi nhận lỗi **theo từng phần tử**, nên vẫn xử lý được các phần tử hợp lệ phía sau.
- `Consumer<String>` thực hiện hành động có thể phát sinh `IOException` và cách lỗi đi qua `accept`.
- Giữ `IOException` làm `cause` khi bọc ngoại lệ, giúp caller xác định nguyên nhân gốc.

Tạo tệp **`CheckedExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Consumer;
import java.util.function.Function;

public class CheckedExceptionDemo {
    @FunctionalInterface
    interface CheckedFunction<T, R> {
        R apply(T value) throws IOException;
    }

    @FunctionalInterface
    interface CheckedConsumer<T> {
        void accept(T value) throws IOException;
    }

    record Outcome(String value, String error) {
        boolean success() {
            return error == null;
        }
    }

    // Đóng vai một phép đọc dữ liệu có thể thất bại.
    static String readCode(String input) throws IOException {
        if (input.equals("IO")) {
            throw new IOException("source unavailable");
        }
        return input.trim().toUpperCase(Locale.ROOT);
    }

    // Đóng vai hành động ghi có thể thất bại.
    static void writeAudit(String code) throws IOException {
        if (code.equals("IO")) {
            throw new IOException("audit unavailable");
        }
        System.out.println("Audit: " + code);
    }

    // Adapter từ interface có checked IOException sang Function JDK.
    static <T, R> Function<T, R> uncheckedFunction(
            CheckedFunction<T, R> action) {
        Objects.requireNonNull(action, "action");
        return value -> {
            try {
                return action.apply(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    // Adapter cho hành động void.
    static <T> Consumer<T> uncheckedConsumer(
            CheckedConsumer<T> action) {
        Objects.requireNonNull(action, "action");
        return value -> {
            try {
                action.accept(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    // Biểu diễn thất bại dưới dạng dữ liệu để tiếp tục từng phần tử.
    static Outcome readSafely(String input) {
        try {
            return new Outcome(readCode(input), null);
        } catch (IOException ex) {
            return new Outcome(null, ex.getMessage());
        }
    }

    public static void main(String[] args) {
        List<String> inputs = List.of(" book ", "IO", " pen ");

        Function<String, String> loader =
                uncheckedFunction(CheckedExceptionDemo::readCode);

        System.out.println("Fail-fast:");
        try {
            inputs.stream()
                    .map(loader)
                    .forEach(code -> System.out.println("Code: " + code));
        } catch (UncheckedIOException ex) {
            System.out.println("Caught: " + ex.getCause().getMessage());
        }

        System.out.println("Per-item:");
        List<Outcome> outcomes = inputs.stream()
                .map(CheckedExceptionDemo::readSafely)
                .toList();

        outcomes.forEach(outcome -> {
            if (outcome.success()) {
                System.out.println("OK: " + outcome.value());
            } else {
                System.out.println("ERROR: " + outcome.error());
            }
        });

        long count = outcomes.stream()
                .filter(Outcome::success)
                .count();
        System.out.println("Success count: " + count);

        Consumer<String> audit =
                uncheckedConsumer(CheckedExceptionDemo::writeAudit);

        audit.accept("BOOK");
        try {
            audit.accept("IO");
        } catch (UncheckedIOException ex) {
            System.out.println("Audit failed: "
                    + ex.getCause().getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 CheckedExceptionDemo.java
java CheckedExceptionDemo
```

**Stdout kỳ vọng chính xác:**

```text
Fail-fast:
Code: BOOK
Caught: source unavailable
Per-item:
OK: BOOK
ERROR: source unavailable
OK: PEN
Success count: 2
Audit: BOOK
Audit failed: audit unavailable
```

### Giải thích từng phần

**Phần fail-fast:** `" book "` được chuyển thành `"BOOK"`. Phần tử tiếp theo `"IO"` khiến `readCode` ném `IOException("source unavailable")`. Adapter bắt ngoại lệ ấy và ném `UncheckedIOException`. `forEach` không tiếp tục in các mã còn lại trong chương trình tuần tự này; `catch` bao ngoài in `Caught: source unavailable`. Do đã dừng tại lỗi, không có `Code: PEN` trong phần này.

**Phần Result:** `readSafely` tự bắt `IOException` và trả một `Outcome` có `error`. Vì stream không bị ném lỗi ra ngoài, cả ba phần tử được xử lý. Kết quả là hai thành công (`BOOK` và `PEN`), một thất bại (`source unavailable`). Đây là cách **biến ngoại lệ thành dữ liệu** để tầng gọi có thể quyết định xử lý từng bản ghi.

**Phần Consumer:** `writeAudit` là `void` và có thể ném checked `IOException`. `uncheckedConsumer` tạo `Consumer<String>` hợp lệ bằng cách bắt/bọc lỗi. Với `BOOK`, nó in `Audit: BOOK`. Với `IO`, lỗi `audit unavailable` được bọc rồi phía caller bắt và báo `Audit failed: audit unavailable`.

**Điểm cần phân biệt:** ví dụ dùng `List.of` và stream tuần tự với thứ tự đầu vào xác định. Nếu chuyển sang `parallelStream`, các nhánh có thể xử lý đồng thời; việc một nhánh ném ngoại lệ **không bảo đảm** rằng các nhánh khác chưa tạo side effect. Vì vậy ý nghĩa “dừng ở lỗi đầu” cần được xem theo ngữ cảnh pipeline tuần tự/đồng thời và ranh giới tác dụng phụ.

## 7. Tạo interface có `throws`: vì sao làm được nhưng không truyền thẳng vào Stream?

Bạn hoàn toàn có thể định nghĩa:

```java
@FunctionalInterface
interface ThrowingFunction<T, R> {
    R apply(T input) throws IOException;
}

@FunctionalInterface
interface ThrowingConsumer<T> {
    void accept(T input) throws IOException;
}
```

Chữ ký có `throws IOException` nên những lambda sau hợp lệ, giả sử `readCode` và `writeAudit` đã khai báo như trong chương trình:

```java
ThrowingFunction<String, String> loader = CheckedExceptionDemo::readCode;
ThrowingConsumer<String> writer = CheckedExceptionDemo::writeAudit;
```

Tuy nhiên, `Stream.map` có chữ ký nhận **`Function<? super T,? extends R>`**, chứ không nhận `ThrowingFunction`. Hai interface không tự chuyển đổi thành nhau dù có cùng số lượng tham số và kiểu trả về. Java có cơ chế target typing cho lambda/method reference, **không có cấu trúc “structural subtyping” tự động giữa hai interface khác tên**.

Vì vậy đoạn sau không hợp lệ:

```java
// SAI: ThrowingFunction không phải java.util.function.Function.
// inputs.stream().map(loader);
```

Adapter là cầu nối:

```java
Function<String, String> adapted = uncheckedFunction(loader);
List<String> values = inputs.stream()
        .map(adapted)
        .toList();
```

Đây là **ví dụ thành phần**, giả định `loader`, `inputs` và `uncheckedFunction` đã được khai báo. Nếu `inputs` chứa `"IO"`, `toList()` ném `UncheckedIOException` trừ khi caller bắt. Adapter **không khiến Stream thay đổi chữ ký map hoặc bổ sung checked exception vào chữ ký của nó**.

### Tại sao ví dụ chỉ khai báo `throws IOException`?

Vì ví dụ xử lý dữ liệu I/O cụ thể, dùng `CheckedFunction<T,R> throws IOException` giúp adapter nhỏ và bắt đúng loại ngoại lệ. Trong dự án lớn, có thể thấy interface generic như `ThrowingFunction<T,R,E extends Exception>`, nhưng sử dụng nó với API JDK vẫn cần adapter và chính sách chuyển đổi lỗi. Không nên xây một hệ phân cấp ngoại lệ mới chỉ để tránh vài dòng `try/catch` nếu bài toán đơn giản.

## 8. `UncheckedIOException`: giữ nguyên nhân gốc khi chuyển đổi

`UncheckedIOException` là lớp con của `RuntimeException` dành riêng cho việc bọc `IOException`. Nó nhận `IOException` ở constructor và giữ ngoại lệ gốc ở `getCause()`.

```java
try {
    readCode("IO");
} catch (IOException ex) {
    throw new java.io.UncheckedIOException(ex);
}
```

Đây là đoạn đặt trong một phương thức. Việc bọc giúp một phương thức không khai báo checked `IOException` vẫn truyền lỗi ra ngoài. So với `throw new RuntimeException(ex)`, `UncheckedIOException` mô tả **nguồn I/O** rõ ràng hơn và cho phép caller bắt đúng kiểu.

Không nên viết:

```java
// Mã không khuyến nghị: làm mất thông tin lỗi gốc.
// catch (IOException ex) {
//     throw new RuntimeException("failed");
// }
```

Cách trên bỏ `ex`, khiến stack trace và chuỗi nguyên nhân khó truy vết. Nếu cần thông báo bổ sung, dùng `new UncheckedIOException("cannot load code", ex)` hoặc exception thích hợp giữ `cause`.

**Chú ý:** `UncheckedIOException` chỉ dành cho `IOException` và lớp con của nó; đừng sử dụng nó để bọc mọi checked exception như `SQLException`. Với các lỗi khác, cần cơ chế xử lý hoặc kiểu exception phù hợp với domain.

## 9. Bắt ngoại lệ trong lambda và chính sách lỗi

Ví dụ trả mặc định:

```java
Function<String, String> fallback = id -> {
    try {
        return readCode(id);
    } catch (IOException ex) {
        return "UNKNOWN";
    }
};
```

Đây là đoạn minh họa được đặt trong phạm vi có thể gọi `readCode`. Cách này dễ viết, nhưng có một rủi ro: `"UNKNOWN"` có thể trùng với giá trị dữ liệu hợp lệ. Khi báo cáo, caller không thể phân biệt “đọc thật được UNKNOWN” với “đọc thất bại nên trả UNKNOWN”.

Để giữ ý nghĩa lỗi:

- Dùng **Result/Outcome** để biểu diễn thành công hoặc thất bại ở mỗi phần tử.
- Dùng **`Optional<R>`** nếu chỉ cần mô tả có/không có giá trị và thực sự chấp nhận mất chi tiết nguyên nhân.
- Bọc exception thành **unchecked** nếu quy trình nên dừng và để caller xử lý.
- Đưa I/O ra khỏi pipeline nếu nhiệm vụ cần kiểm soát retry, timeout, transaction hoặc tài nguyên theo từng bước.

Không bắt và lặng lẽ bỏ qua exception mà không có quyết định nghiệp vụ, đặc biệt khi đang xử lý thanh toán, đơn hàng hoặc nhập dữ liệu quan trọng.

### Có nên bắt `Exception` hoặc `Throwable` cho tất cả lỗi?

Thông thường **không**. Bắt quá rộng có thể che bug lập trình, lỗi tài nguyên hoặc khiến hệ thống tiếp tục trong trạng thái không an toàn. Adapter ví dụ chỉ bắt đúng `IOException` để những lỗi runtime ngoài dự kiến vẫn được truyền ra, giúp việc chẩn đoán rõ hơn.

Với `InterruptedException`, khi buộc phải xử lý trong một callback không khai báo `throws`, không được coi nó như `IOException` và bọc tùy tiện. Nếu không truyền checked exception tiếp được, thường cần **khôi phục interrupt flag** bằng `Thread.currentThread().interrupt()` rồi kết thúc/đổi thành lỗi phù hợp với hợp đồng, để tầng gọi không mất tín hiệu hủy. Đặt chính sách theo loại tác vụ và cơ chế hủy của ứng dụng.

## 10. Phạm vi try/catch quyết định xử lý từng phần tử hay toàn pipeline

Hai tổ chức sau có hành vi khác nhau.

### Bắt ngoài terminal operation: dừng ở ngoại lệ đầu tiên

```java
try {
    inputs.stream()
            .map(uncheckedFunction(CheckedExceptionDemo::readCode))
            .forEach(System.out::println);
} catch (UncheckedIOException ex) {
    System.out.println("Failed: " + ex.getCause().getMessage());
}
```

Trong stream tuần tự của ví dụ, mapper ném lỗi trên `"IO"` nên pipeline kết thúc bằng lỗi. Những phần tử phía sau chưa được xử lý sẽ không xuất hiện trong stdout. Nếu các bước trước có side effect, chúng **không tự rollback**.

### Bắt bên trong mapper: có thể tiếp tục với phần tử tiếp theo

```java
List<Outcome> results = inputs.stream()
        .map(CheckedExceptionDemo::readSafely)
        .toList();
```

`readSafely` không để `IOException` thoát ra, nên stream được xử lý qua cả ba phần tử và thu về ba Outcome. Tầng ứng dụng có thể phân loại, đếm lỗi, thông báo và xử lý retry có chọn lọc.

Trong pipeline xử lý dữ liệu lớn, đôi khi một số bản ghi lỗi phải được ghi ra danh sách lỗi để sửa, còn các bản ghi hợp lệ vẫn nhập được. Đây là lúc *Result as data* phù hợp. Khi hợp đồng yêu cầu **tất cả hoặc không gì cả**, cần cơ chế transaction/atomicity riêng; chỉ bọc exception hay bắt trong lambda không đảm bảo tính nguyên tử.

## 11. `Consumer.andThen` và `Function.andThen` vẫn theo hợp đồng exception của SAM

`Function.andThen` nối hai phép biến đổi, `Consumer.andThen` nối hai hành động. Chúng không bổ sung khả năng truyền checked exception vào `apply`/`accept`:

```java
Function<String, Integer> parse = Integer::parseInt;
Function<Integer, String> label = n -> "Number " + n;
Function<String, String> pipeline = parse.andThen(label);

System.out.println(pipeline.apply("7")); // Number 7
```

Nếu `parse` ném unchecked `NumberFormatException` với `"abc"`, `label` không chạy. Nếu một mapper đã bọc checked `IOException` thành `UncheckedIOException`, ngoại lệ unchecked đó cũng sẽ truyền ra và bước sau bị bỏ qua.

Tương tự:

```java
Consumer<String> first = value -> System.out.println("first " + value);
Consumer<String> second = value -> {
    throw new IllegalStateException("stop");
};

first.andThen(second).accept("A");
```

Dòng `first A` sẽ được in rồi `second` ném `IllegalStateException`. Việc `Consumer.andThen` chấp nhận lỗi unchecked **không đồng nghĩa** với việc nó bắt checked exception hoặc rollback side effect của `first`.

## 12. Những tình huống liên quan trong thư viện Java

**`Stream.map`/`forEach`:** yêu cầu `Function` và `Consumer` của `java.util.function`, không có `throws` checked exception trong SAM, nên lambda gọi API I/O cần adapter hoặc xử lý tại chỗ.

**`Optional.map`:** cũng nhận `Function`. Chữ ký `Optional.map` không tự giải quyết checked exception; một method reference tới phương thức có `throws IOException` vẫn phải thích ứng.

**`Map.computeIfAbsent`:** nhận `Function<? super K,? extends V>`; mapping function ném unchecked exception sẽ làm phép tính thất bại theo hợp đồng của map cụ thể. Không dùng I/O tùy tiện trong mapping function mà chưa xét lỗi, side effect và quy tắc đồng thời.

**`Callable<V>`:** `V call() throws Exception` là functional interface có thể truyền checked exception. Ví dụ `Callable<String> task = () -> readCode("BOOK");` hợp lệ nếu `readCode` khai báo `throws IOException`. Tuy nhiên `Callable` không thay thế `Function<T,R>` trong `Stream.map` vì `Callable.call()` không có đầu vào, còn `Function.apply(T)` có một đầu vào.

**`Files.lines(Path)`:** thao tác mở nguồn có thể ném `IOException`; sau khi mở, các lỗi I/O khi đọc nội dung có thể thể hiện qua `UncheckedIOException` trong quá trình tiêu thụ stream. Vì thế cần quản lý tài nguyên bằng `try-with-resources` và xử lý lỗi đúng ranh giới, không cho rằng việc chuyển sang stream làm mất rủi ro I/O.

## 13. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| “Lambda không được ném checked exception” | Lambda vẫn có thể dùng SAM khai báo `throws` | Kiểm tra target functional interface |
| `Function<String,String> f = this::readFile` khi `readFile` ném `IOException` | `Function.apply` không khai báo checked exception | Bắt trong lambda, adapter hoặc đổi API |
| Cho rằng `Function` không thể ném bất cứ exception nào | Unchecked exception vẫn được phép | Phân biệt checked và unchecked |
| Dùng `RuntimeException` không giữ cause | Khó truy vết nguồn lỗi | Bọc đúng kiểu và truyền `cause` |
| Trả `null` hoặc chuỗi mặc định cho mọi lỗi | Mất phân biệt lỗi với dữ liệu hợp lệ | Dùng Result/Outcome hoặc hợp đồng fallback rõ |
| Bắt `Exception` và bỏ qua | Có thể nuốt bug hoặc lỗi nghiêm trọng | Bắt loại lỗi cụ thể, xử lý theo chính sách |
| Retry toàn pipeline sau lỗi I/O | Có thể lặp side effect đã thành công | Idempotency, transaction, checkpoint hoặc retry có chọn lọc |
| Nghĩ `andThen` chạy bước sau dù bước trước lỗi | Khi có exception, bước sau không chạy | Bắt lỗi trong bước trước nếu phục hồi hợp lệ |
| Dùng parallel stream với mapper có side effect | Không bảo đảm thứ tự và có nguy cơ race | Tách side effect, dùng đồng bộ hoặc pipeline thuần |
| Quên đóng nguồn I/O khi tạo Stream từ file | Có thể rò rỉ handle | `try-with-resources` |
| Bắt `InterruptedException` rồi quên cờ interrupt | Có thể mất tín hiệu hủy tác vụ | Khôi phục interrupt flag hoặc truyền lỗi đúng hợp đồng |

## 14. Bài tập vận dụng

1. Viết một phương thức `static String read(String id) throws IOException`. Thử gán `Function<String,String> bad = YourClass::read`, ghi lại lỗi compiler và giải thích vì sao nó xuất hiện dù phương thức có thể không ném lỗi với một input hợp lệ.
2. Tạo `@FunctionalInterface interface ThrowingFunction<T,R> { R apply(T value) throws IOException; }`, rồi gán method reference `YourClass::read`. Tại sao việc gán hợp lệ, nhưng chưa thể dùng trực tiếp biến đó vào `Stream.map`?
3. Viết một adapter từ `ThrowingFunction<T,R>` sang `Function<T,R>` với `UncheckedIOException`. Kiểm tra khi input lỗi, `getCause()` vẫn là `IOException` gốc.
4. Viết `Function<String,Outcome>` để xử lý danh sách `"A", "IO", "B"`. Khi `"IO"` lỗi, kết quả phải vẫn có ba Outcome, trong đó hai thành công và một thất bại.
5. Thay `List.of(" book ", "IO", " pen ")` bằng một danh sách không có `"IO"`. Dự đoán phần fail-fast in bao nhiêu dòng `Code: ...` và có còn dòng `Caught: ...` không.
6. Viết `Consumer<String>` gọi phương thức `writeAudit(String) throws IOException` và xử lý lỗi bằng `UncheckedIOException`. So sánh với một `CheckedConsumer<String>` có `throws IOException`.
7. Viết `Function<String,Integer>` dùng `Integer::parseInt`. Tại sao `"abc"` ném `NumberFormatException` mà compiler vẫn chấp nhận method reference?
8. Chuyển ví dụ `readSafely` sang `Optional<String>`. Thông tin nào về lỗi bị mất so với `Outcome`? Trường hợp nghiệp vụ nào chấp nhận sự mất mát đó?
9. Thiết kế một hàm xử lý file có dùng `try-with-resources` và trả danh sách dữ liệu trước khi đưa vào stream. So sánh ưu/nhược điểm với việc stream đọc file trực tiếp.
10. Trình bày chính sách riêng cho `IOException`, `SQLException` và `InterruptedException` trong callback không khai báo checked `throws`. Vì sao không nên bọc tất cả thành `UncheckedIOException`?

## 15. Checklist khi thiết kế pipeline có thao tác dễ phát sinh lỗi

- Xác minh **SAM đích** của lambda/method reference có `throws` checked exception không.
- Biết phương thức gọi bên trong khai báo **loại checked exception nào**.
- Chọn rõ **fail-fast** hay **xử lý lỗi từng phần tử**.
- Nếu chuyển sang unchecked, giữ **cause** và đặt tên exception phù hợp.
- Không nuốt lỗi hay trả fallback mơ hồ khi nghiệp vụ cần tính đúng/khả năng kiểm toán.
- Với `InterruptedException`, xử lý tín hiệu hủy và interrupt flag đúng cách.
- Xem xét **side effect**, retry, idempotency, transaction và tài nguyên I/O riêng với logic stream.
- Test ít nhất trường hợp hợp lệ, lỗi đầu vào, lỗi giữa pipeline và trạng thái sau lỗi.

**Ghi nhớ:** `Function.apply` và `Consumer.accept` không khai báo checked exception, nên thân lambda/method reference dùng với chúng không thể để một checked exception chưa xử lý thoát ra. Java vẫn cho phép lambda ném checked exception khi **functional interface phù hợp** có chữ ký `throws`. Khi cần I/O trong pipeline, hãy chọn một chính sách lỗi rõ ràng: xử lý tại chỗ, chuyển thành unchecked một cách có nguyên nhân, hoặc biểu diễn lỗi thành dữ liệu.
