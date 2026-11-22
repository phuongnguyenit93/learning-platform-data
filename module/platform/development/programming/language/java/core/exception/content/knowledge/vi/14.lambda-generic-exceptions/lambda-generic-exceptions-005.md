# Bắt tại lambda, chuyển đổi ngoại lệ hoặc chọn interface riêng trong Java

Lambda giúp truyền hành vi dưới dạng một giá trị, nhưng không xóa bỏ cơ chế **checked exception** của Java. Một lời gọi trong thân lambda có thể ném `IOException`, `SQLException`, `InterruptedException` hoặc ngoại lệ checked khác. Nó có hợp lệ hay không phụ thuộc vào **functional interface được dùng làm kiểu đích** (*target type*) và mệnh đề `throws` trên phương thức trừu tượng của interface ấy.

Ví dụ, `java.util.function.Function<T, R>` khai báo `R apply(T t)` mà **không có `throws IOException`**. Vì thế, bạn không thể gán trực tiếp lambda gọi một phương thức `throws IOException` cho `Function<String, String>` rồi mong compiler bỏ qua ngoại lệ. Cũng không thể chỉ thêm `throws IOException` vào phương thức bao quanh để sửa mọi trường hợp: **thân lambda phải tương thích với hợp đồng ngoại lệ của chính functional interface**.

Có ba hướng xử lý chính:

1. **Bắt tại lambda:** dùng `try-catch` trong thân lambda khi bạn có thể phục hồi hoặc quyết định kết quả phù hợp tại chỗ.
2. **Chuyển đổi ngoại lệ:** giữ `cause` và bọc checked exception thành một unchecked exception có ý nghĩa, ví dụ `UncheckedIOException` cho lỗi I/O, khi API buộc dùng `Function`/`Consumer` không khai báo `throws`.
3. **Chọn interface riêng có `throws`:** tạo `@FunctionalInterface` như `ThrowingFunction<T,R,E extends Exception>` để giữ checked exception trong chữ ký; phương thức gọi nó phải `catch` hoặc `throws` đúng hợp đồng.

Không có lựa chọn đúng cho mọi trường hợp. Bài học này trình bày cơ chế theo Java 17+, ví dụ độc lập có lệnh biên dịch/chạy và kết quả stdout, cách tích hợp với Stream API, lambda/method reference, Generic `throws E`, `InterruptedException`, lỗi phổ biến và checklist quyết định thiết kế.

## 1. Lambda có một kiểu đích, và kiểu đó xác định ngoại lệ được phép

Một lambda như `name -> read(name)` **không có kiểu độc lập tách khỏi ngữ cảnh**. Nó cần được gán, truyền hoặc ép sang một functional interface phù hợp. *Function type* của interface cho biết tham số, kết quả và các checked exception được phép thoát ra từ hành vi ấy.

Ví dụ về hai interface:

```java
@FunctionalInterface
interface SimpleLoader {
    String load(String key);
}

@FunctionalInterface
interface CheckedLoader {
    String load(String key) throws java.io.IOException;
}
```

Đây là **hai interface minh họa hợp lệ** khi đặt ở phạm vi thích hợp. Cả hai cùng nhận một `String` và trả một `String`, nhưng chúng khác nhau ở **hợp đồng ném ngoại lệ**.

Giả sử có phương thức:

```java
static String read(String key) throws java.io.IOException {
    if ("bad".equals(key)) {
        throw new java.io.IOException("cannot read");
    }
    return "DATA:" + key;
}
```

Khi gán:

```java
CheckedLoader allowed = key -> read(key); // Hợp lệ.
SimpleLoader invalid = key -> read(key);   // Không biên dịch.
```

Đây là **mã đặt trong một lớp có phương thức `read` như trên**, dòng thứ hai được ghi rõ là ví dụ cố ý không hợp lệ. `CheckedLoader.load` công bố `throws IOException` nên lambda được quyền truyền lỗi checked này cho bên gọi. `SimpleLoader.load` không công bố loại checked nào nên lambda buộc phải tự xử lý hoặc chuyển đổi `IOException` trước khi thoát khỏi thân.

### Những interface chuẩn thường gặp

| Functional interface / API | Phương thức trừu tượng | Cho phép checked exception do người dùng khai báo? |
| --- | --- | --- |
| `Runnable` | `void run()` | Không |
| `Supplier<T>` | `T get()` | Không |
| `Consumer<T>` | `void accept(T t)` | Không |
| `Function<T,R>` | `R apply(T t)` | Không |
| `Predicate<T>` | `boolean test(T t)` | Không |
| `BiFunction<T,U,R>` | `R apply(T t,U u)` | Không |
| `Callable<V>` | `V call() throws Exception` | Có; giao diện cho phép `Exception` |
| `ThrowingFunction<T,R,E>` tự tạo | `R apply(T t) throws E` | Có; kiểu `E` được ràng buộc phù hợp |

Cột cuối nói về **ngoại lệ checked được phép truyền qua hợp đồng**, không có nghĩa các interface không khai báo `throws` sẽ không bao giờ ném bất kỳ lỗi nào. `RuntimeException` và `Error` là unchecked nên vẫn có thể xuất hiện lúc chạy.

## 2. Lỗi biên dịch khi gọi phương thức có `throws` trong lambda

Mã sau **cố ý không biên dịch**:

```java
import java.io.IOException;
import java.util.function.Function;

class InvalidLambda {
    static String load(String key) throws IOException {
        throw new IOException("file unavailable");
    }

    static void example() {
        Function<String, String> reader = key -> load(key);
        // Lỗi: IOException checked không được xử lý trong lambda.
    }
}
```

Lý do **không phải** `Function` không thể biểu diễn một thao tác có lỗi, mà vì `Function.apply` **không có `throws IOException`**. Compiler kiểm tra exception analysis cho **thân lambda theo function type đích** và từ chối checked exception có thể đi ra ngoài mà không được cho phép.

Thay chữ ký bên ngoài thành `static void example() throws IOException` **không sửa** tính không tương thích giữa thân lambda và `Function.apply`. Phần thân lambda không được chạy ngay khi khai báo biến; nó sẽ thực hiện khi `reader.apply(...)` được gọi về sau, có thể ở nơi hoàn toàn khác. Bởi vậy, Java không thể dùng `throws` của phương thức **tạo lambda** để thay cho `throws` của phương thức **functional interface**.

Cùng quy tắc áp dụng cho method reference:

```java
Function<String, String> reader = InvalidLambda::load;
// Cũng không biên dịch, vì load(String) throws IOException.
```

Method reference không phải “cách né checked exception”; nó phải tương thích với function type đích như lambda.

## 3. Hướng 1: bắt ngoại lệ ngay trong lambda

Nếu lỗi có thể được xử lý **đúng và đủ** ngay tại nơi chạy lambda, một `try-catch` trong thân là cách trực tiếp nhất. Ví dụ một tác vụ chấp nhận sự kiện được phép ghi nhận lỗi của từng sự kiện rồi tiếp tục nhận các sự kiện độc lập.

Lưu thành `LocalCatchDemo.java`:

```java
import java.io.IOException;
import java.util.function.Consumer;

public class LocalCatchDemo {
    static String load(String id) throws IOException {
        if ("bad".equals(id)) {
            throw new IOException("source unavailable");
        }
        return "data:" + id;
    }

    public static void main(String[] args) {
        Consumer<String> consumer = id -> {
            try {
                System.out.println("accepted=" + load(id));
            } catch (IOException ex) {
                System.out.println("error=" + id + ":" + ex.getMessage());
            }
        };

        consumer.accept("ok");
        consumer.accept("bad");
        consumer.accept("next");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 LocalCatchDemo.java
java LocalCatchDemo
```

Kết quả:

```text
accepted=data:ok
error=bad:source unavailable
accepted=data:next
```

Giải thích:

- `Consumer.accept` không khai báo checked exceptions. Nhưng **bản thân lambda đã bắt `IOException`**, không để lỗi checked ấy đi ra ngoài.
- Lần gọi với `bad` đi vào `catch`, in lỗi rồi kết thúc **lần gọi `accept("bad")` bình thường**. Vì `main` tiếp tục gọi `accept("next")`, ví dụ in được dòng cuối.
- Cách này chỉ đúng khi chính sách nghiệp vụ thực sự cho phép xử lý lỗi mỗi mục **tại chỗ**. Với thao tác tài chính hoặc cập nhật trạng thái phải thành công toàn bộ, việc chỉ in lỗi rồi coi đã xử lý có thể rất nguy hiểm.
- `catch` trong lambda không ảnh hưởng ngoại lệ được ném từ một lần gọi `accept` **khác** hoặc các tác vụ chạy ở thread khác.

**Đừng dùng `catch(Exception ex) { }` rỗng** để compiler chấp nhận lambda. Cách đó che khuất lỗi, khiến dữ liệu sai hoặc mất mà bên gọi không biết.

## 4. Với `Function<T,R>`, một `catch` phải quyết định giá trị trả về

Khác `Consumer.accept` trả `void`, `Function.apply` phải trả một giá trị `R` hoặc kết thúc đột ngột. Nếu bắt lỗi nhưng vẫn muốn trả giá trị, hãy chọn một **fallback hợp lệ theo hợp đồng**, không tự động trả `null` hoặc chuỗi rỗng.

Mẫu đặt trong một phương thức:

```java
Function<String, String> safeReader = key -> {
    try {
        return readChecked(key);
    } catch (IOException ex) {
        return "verified-cache:" + key;
    }
};
```

Đây là **mẫu minh họa**, giả định `readChecked(String) throws IOException` đã được định nghĩa và kết quả `verified-cache` thật sự là một giá trị dự phòng hợp lệ. Không phải mọi lỗi đọc đều phù hợp với fallback: cache có thể cũ, không được phép sử dụng hoặc làm vi phạm tính nhất quán.

Nếu chính sách đòi **không được tiếp tục**, đừng trả giá trị giả. Khi đó chuyển đổi thành unchecked exception với cause hoặc dùng một interface có `throws` sẽ làm trách nhiệm của caller rõ ràng hơn.

Một cách khác là trả `Optional<R>` hay một `Result<R,E>` để biểu thị thất bại như dữ liệu. Chỉ dùng lựa chọn đó khi nó phù hợp API và thông tin lỗi cần được giữ; `Optional.empty()` có thể không đủ nếu bên gọi cần biết **vì sao** đã thất bại.

## 5. Hướng 2: bọc `IOException` thành `UncheckedIOException`

Khi một API chỉ nhận `Function` hoặc `Consumer`, nhưng bạn muốn **dừng xử lý và báo lỗi cho tầng gọi**, có thể bọc ngoại lệ I/O trong `java.io.UncheckedIOException`.

`UncheckedIOException extends RuntimeException` và nhận `IOException` làm **cause**. Đây là kiểu phù hợp với lỗi I/O, không phải wrapper tổng quát cho mọi checked exception khác.

Lưu thành `UncheckedStreamDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Locale;
import java.util.function.Function;
import java.util.stream.Stream;

public class UncheckedStreamDemo {
    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("read failed");
        }
        return key.toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        Function<String, String> adapter = key -> {
            try {
                return read(key);
            } catch (IOException ex) {
                throw new UncheckedIOException(
                        "cannot load " + key, ex);
            }
        };

        Stream<String> pipeline =
                Stream.of("one", "bad", "two").map(adapter);

        System.out.println("pipeline created");

        try {
            pipeline.forEach(value ->
                    System.out.println("value=" + value));
        } catch (UncheckedIOException ex) {
            System.out.println("wrapper=" + ex.getMessage());
            System.out.println("cause=" + ex.getCause().getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 UncheckedStreamDemo.java
java UncheckedStreamDemo
```

Kết quả với stream tuần tự trong ví dụ:

```text
pipeline created
value=ONE
wrapper=cannot load bad
cause=read failed
```

Vì `Stream.map` là thao tác **lazy**, việc tạo pipeline chưa thực thi `adapter.apply`. Lỗi chỉ phát sinh khi gọi terminal operation `forEach`.

Dòng `value=TWO` không được in, vì khi tới `bad`, lambda ném `UncheckedIOException` và lần đánh giá stream tuần tự này kết thúc bằng ngoại lệ. Đừng dùng đầu ra này để khẳng định rằng **mọi parallel stream** hoặc pipeline có thao tác khác sẽ xử lý/chấm dứt theo thứ tự y hệt; thứ tự xử lý và tác dụng phụ cần xét riêng.

Bộ xử lý ngoài terminal operation nhận `UncheckedIOException`. Nó có thể xem `ex.getCause()` để tìm đúng `IOException("read failed")`. **Cause không mất**, khác với `throw new RuntimeException(ex.getMessage())` chỉ sao chép một chuỗi.

## 6. Khi chuyển đổi checked sang unchecked, cần thiết kế ranh giới xử lý

Đổi loại ngoại lệ chỉ để “né compiler” thường là lựa chọn kém. Quyết định hợp lệ khi **hợp đồng API** buộc callback không khai báo checked exception nhưng ứng dụng vẫn muốn phân loại thất bại tại một ranh giới cao hơn.

| Nguồn lỗi | Wrapper có thể phù hợp | Lưu ý |
| --- | --- | --- |
| `IOException` khi đọc tệp, mạng hoặc stream | `UncheckedIOException(message, cause)` | Chỉ nhận `IOException` không `null` |
| `SQLException` từ repository | Custom `DataAccessFailure extends RuntimeException` | Truyền `SQLException` làm cause; không đổi thành `UncheckedIOException` |
| Checked exception nghiệp vụ | Custom unchecked exception **nếu hợp đồng cho phép** | Không làm mất ý nghĩa phục hồi của lỗi |
| `InterruptedException` | Thường **truyền lên hoặc khôi phục cờ interrupt và kết thúc tác vụ** | Không xử lý như lỗi thông thường rồi tiếp tục |
| Bất kỳ `RuntimeException` có sẵn | Có thể cho lan truyền | Không cần bọc lại chỉ vì ở lambda |

Ví dụ custom wrapper:

```java
class DataAccessFailure extends RuntimeException {
    DataAccessFailure(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là lớp minh họa hợp lệ không có `main` độc lập. Khi catch lỗi SQL:

```java
catch (java.sql.SQLException ex) {
    throw new DataAccessFailure("Cannot load orders", ex);
}
```

Nhánh catch này là **đoạn minh họa trong thân lambda hoặc phương thức** có thể phát sinh `SQLException`. Bằng cách truyền `ex` làm cause, bên gọi giữ được loại lỗi gốc, stack trace và các suppressed exceptions nằm trên đối tượng cause.

**Không nên** dùng `new UncheckedIOException(new IOException(sqlException))` chỉ để ép một lỗi SQL thành lỗi I/O: tạo sai ngữ nghĩa chẩn đoán và gây hiểu nhầm cho logic xử lý phía trên.

## 7. Hướng 3: tự tạo functional interface có `throws E`

Khi bạn **kiểm soát API gọi callback**, một interface riêng thường tốt hơn việc buộc mọi lambda phải bọc lỗi. Có thể khai báo:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
```

Đây là một functional interface hợp lệ:

- `T`: kiểu đầu vào;
- `R`: kiểu kết quả;
- `E extends Exception`: loại checked (hoặc unchecked thuộc nhánh Exception) mà callback có thể ném;
- `apply(T) throws E`: chữ ký cho phép checked exception `E` đi ra ngoài.

### Chương trình Java 17+: giữ `IOException` qua interface riêng

Lưu thành `CheckedFunctionDemo.java`:

```java
import java.io.IOException;

public class CheckedFunctionDemo {
    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T input) throws E;
    }

    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("file unavailable");
        }
        return "data:" + key;
    }

    static <T, R, E extends Exception> R invoke(
            T input, ThrowingFunction<T, R, E> function) throws E {
        return function.apply(input);
    }

    public static void main(String[] args) {
        ThrowingFunction<String, String, IOException> loader =
                CheckedFunctionDemo::read;

        try {
            System.out.println("value=" + invoke("ok", loader));
            invoke("bad", loader);
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 CheckedFunctionDemo.java
java CheckedFunctionDemo
```

Kết quả:

```text
value=data:ok
caught=file unavailable
```

Phân tích:

1. Method reference `CheckedFunctionDemo::read` tương thích với `ThrowingFunction<String,String,IOException>` vì `apply` được phép ném IOException.
2. Phương thức generic `invoke` công bố `throws E` nên cho phép truyền nguyên đối tượng ngoại lệ ra ngoài.
3. `main` bắt `IOException` cụ thể. Không cần tạo một wrapper unchecked mới.
4. Trong ví dụ, `loader` được truyền dưới dạng interface riêng, **không phải `Function<String,String>`**; dù giống tham số/kết quả, hai hợp đồng exception không tự đồng nhất.

Đây là lựa chọn phù hợp cho callback trong thư viện nội bộ, batch processing hoặc workflow mà bên gọi thực sự có trách nhiệm xử lý checked exception.

## 8. Dùng interface riêng với Stream API: không tự động tương thích

Một hiểu lầm thường gặp:

```java
ThrowingFunction<String, String, IOException> loader =
        CheckedFunctionDemo::read;

// KHÔNG HỢP LỆ:
// Stream.of("a", "b").map(loader);
```

Đây là đoạn minh họa, giả sử `ThrowingFunction` đã được khai báo. Lý do không phải lỗi type erasure mà là **`Stream.map` yêu cầu `Function<? super T, ? extends R>`**, không yêu cầu một `ThrowingFunction` tự tạo. Hai interface không cùng kiểu, và bản thân `Function.apply` cũng không công bố `throws IOException`.

Khi bạn **không kiểm soát chữ ký của API chuẩn**, hãy chọn:

- **Adapter** từ interface ném checked sang `Function` bằng một chính sách bọc/biểu diễn lỗi minh bạch.
- **Đổi quy trình xử lý** sang phương thức nhận `ThrowingFunction` nếu có quyền thiết kế API.
- **Trả kết quả biểu diễn lỗi** cho từng phần tử, nếu chính sách không muốn dừng cả pipeline.

Không cố ép kiểu `(Function<String,String>) loader`: hai interface độc lập không tự tương thích và phép cast không sửa mệnh đề `throws` của phương thức chức năng.

## 9. Adapter tái sử dụng: từ `IOFunction` đến `Function`

Nếu nhiều chỗ trong dự án cần dùng Stream với thao tác I/O, có thể gom logic bọc vào một adapter thay vì viết `try-catch` trùng trong từng lambda.

Lưu thành `IoAdapterDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;
import java.util.stream.Stream;

public class IoAdapterDemo {
    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(
            IOFunction<T, R> checked) {
        return value -> {
            try {
                return checked.apply(value);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("cannot read " + key);
        }
        return "loaded:" + key;
    }

    public static void main(String[] args) {
        Function<String, String> loader =
                unchecked(IoAdapterDemo::read);

        try {
            Stream.of("a", "bad", "c")
                    .map(loader)
                    .forEach(x -> System.out.println("value=" + x));
        } catch (UncheckedIOException ex) {
            System.out.println("io=" + ex.getCause().getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 IoAdapterDemo.java
java IoAdapterDemo
```

Kết quả cho pipeline tuần tự:

```text
value=loaded:a
io=cannot read bad
```

Ở đây, callback mà adapter **nhận** có hợp đồng `throws IOException`; callback mà adapter **trả về** là `Function<T,R>` không khai báo checked exception. Vì vậy bước bọc được thực hiện **tại đúng ranh giới chuyển kiểu**.

Chính sách của adapter là **fail fast**: lỗi từ một phần tử ngăn pipeline tuần tự hoàn thành bình thường. Nếu bạn cần gom tất cả lỗi để báo cáo sau, không sử dụng adapter fail-fast này mà hãy thiết kế `Result` hoặc một bộ thu thập lỗi riêng.

**Giới hạn:** `IOFunction` và adapter trên chỉ xử lý `IOException`. Với `SQLException` hoặc checked exception khác, tạo adapter phù hợp với hợp đồng lỗi của module; không bắt `Exception` rộng rồi tự động bọc mọi thứ theo cùng một cách.

## 10. Dùng `Result` để giữ cả dữ liệu thành công lẫn lỗi của từng phần tử

Khi xử lý nhiều bản ghi độc lập, đôi lúc yêu cầu là **không dừng toàn bộ batch** khi một bản ghi lỗi. Bắt lỗi rồi chuyển mỗi kết quả thành một giá trị có trạng thái sẽ phù hợp hơn so với bọc lỗi và dừng stream.

Lưu thành `ResultPipelineDemo.java`:

```java
import java.io.IOException;
import java.util.stream.Stream;

public class ResultPipelineDemo {
    record Outcome(String key, String value, IOException error) {
        boolean success() {
            return error == null;
        }
    }

    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("disk unavailable");
        }
        return "DATA-" + key;
    }

    public static void main(String[] args) {
        Stream.of("a", "bad", "c")
                .map(key -> {
                    try {
                        return new Outcome(key, read(key), null);
                    } catch (IOException ex) {
                        return new Outcome(key, null, ex);
                    }
                })
                .forEach(result -> {
                    if (result.success()) {
                        System.out.println("ok=" + result.key()
                                + ":" + result.value());
                    } else {
                        System.out.println("fail=" + result.key()
                                + ":" + result.error().getMessage());
                    }
                });
    }
}
```

```bash
javac -encoding UTF-8 ResultPipelineDemo.java
java ResultPipelineDemo
```

Kết quả:

```text
ok=a:DATA-a
fail=bad:disk unavailable
ok=c:DATA-c
```

Lúc này, lambda của `Stream.map` **không ném checked exception ra ngoài**; nó luôn trả một `Outcome` cho những trường hợp được xử lý. Kiểu `Outcome` chứa tham chiếu `IOException` gốc, nên có thể tiếp tục truy vấn stack trace, cause và suppressed nếu cần.

`record` là tính năng chuẩn ở Java 17, vì vậy ví dụ không cần thư viện Result bên ngoài. Trong hệ thống sản xuất, nên thiết kế bất biến rõ ràng: mỗi outcome phải là **thành công hoặc thất bại**, không đồng thời cả hai; có thể dùng sealed hierarchy hoặc factory methods thay cho constructor record công khai khi cần.

Ưu điểm của cách này là biểu diễn lỗi **như một phần kết quả**. Đổi lại, các tầng sau phải chủ động kiểm tra trạng thái; nếu bỏ qua `error`, sự cố vẫn có thể bị “nuốt” ở tầng nghiệp vụ.

## 11. `InterruptedException` trong lambda cần chính sách riêng

`InterruptedException` biểu thị tín hiệu phối hợp gián đoạn/hủy trong nhiều API như `Thread.sleep(...)`. Không nên coi nó như `IOException` rồi chỉ log hoặc bọc thành unchecked để cho tác vụ tiếp tục bình thường.

Khi interface không khai báo `throws InterruptedException`, hai hướng thường hợp lý:

- Nếu có thể **thay hợp đồng interface**, chọn functional interface có `throws InterruptedException` và truyền tín hiệu cho tầng điều phối tác vụ.
- Nếu buộc dùng `Runnable`, bắt `InterruptedException`, **khôi phục cờ interrupt** bằng `Thread.currentThread().interrupt()` khi API đã xóa cờ, rồi kết thúc thao tác hoặc thực hiện quy trình hủy phù hợp.

Chương trình Java 17+ minh họa, lưu thành `InterruptLambdaDemo.java`:

```java
public class InterruptLambdaDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Runnable task = () -> {
            try {
                Thread.sleep(10_000);
                System.out.println("completed sleep");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("interruptFlag="
                        + Thread.currentThread().isInterrupted());
            }
        };

        Thread worker = new Thread(task);
        worker.start();
        worker.interrupt();
        worker.join();

        System.out.println("finished=" + !worker.isAlive());
    }
}
```

```bash
javac -encoding UTF-8 InterruptLambdaDemo.java
java InterruptLambdaDemo
```

Kết quả trong điều kiện chạy bình thường:

```text
interruptFlag=true
finished=true
```

Nếu tín hiệu interrupt tới **trước khi thread bắt đầu `sleep`**, trạng thái interrupt đã được đặt và `Thread.sleep` ném `InterruptedException`; nếu tới **trong lúc sleep**, nó đánh thức thao tác bằng ngoại lệ đó. Hai đường đều vào nhánh catch, cờ được đặt lại và `Runnable.run()` kết thúc. `join()` làm main chờ worker kết thúc trước khi in dòng cuối.

Ví dụ cố ý điều phối worker theo một lần interrupt rõ ràng, **không minh họa một hệ thống hủy tác vụ hoàn chỉnh**. Trong mã thật, nên xem chính sách dừng thread, dọn dẹp tài nguyên, xử lý gián đoạn khi chờ và việc shutdown của executor.

**Không ném `UncheckedIOException` cho `InterruptedException`.** Ngoài việc không đúng loại tham số, nó còn sai ngữ nghĩa về nguyên nhân/hợp đồng I/O.

## 12. `Callable` và `Runnable` khác nhau về hợp đồng checked exception

Không nhất thiết phải tự tạo functional interface trong mọi trường hợp. Thư viện chuẩn đã có `java.util.concurrent.Callable<V>`:

```java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
```

Đây là bản lược giản chữ ký API để học. `Callable.call()` cho phép checked exception, còn `Runnable.run()` thì không. Do đó một lời gọi ném `IOException` có thể phù hợp với target type `Callable<String>`:

```java
Callable<String> task = () -> readChecked("profile");
```

Đoạn này minh họa trong phương thức đã import `Callable`, với `readChecked(String) throws IOException`. Nếu tự gọi `task.call()`, chữ ký là `throws Exception` nên bên gọi phải bắt hoặc khai báo `Exception` phù hợp.

Nếu nộp `Callable` vào `ExecutorService.submit(...)`, checked exception do task ném thường được quan sát tại `Future.get()` thông qua `ExecutionException` với cause là lỗi từ task. **Không nên giả định `Future.get()` sẽ ném trực tiếp chính `IOException` theo chữ ký**. `Future.get()` còn có thể ném `InterruptedException` khi thread chờ bị ngắt.

Ngược lại, `CompletableFuture.supplyAsync(...)` nhận `Supplier<T>` không có checked `throws`. Vì vậy, đổi từ `Runnable` sang `supplyAsync` không tự giải quyết checked exception của lambda. Tùy API, bạn cần adapter/bọc lỗi hoặc thiết kế cơ chế báo lỗi khác. Những wrapper bất đồng bộ có thể làm xuất hiện `CompletionException` tại điểm truy cập kết quả; nên kiểm tra cause chain chứ không đoán tất cả lỗi sẽ lộ ra cùng một kiểu.

## 13. Method reference phải theo cùng quy tắc với lambda

Giả sử:

```java
static String read(String key) throws IOException { /* ... */ }
```

Khi đó:

```java
ThrowingFunction<String, String, IOException> ok = MyClass::read;

// Function<String, String> invalid = MyClass::read;
```

Đây là **mẫu minh họa** với tên lớp `MyClass`, `ThrowingFunction` đã khai báo và import phù hợp. Lần gán thứ nhất được phép vì interface nhận checked `IOException`. Nếu bỏ comment ở dòng thứ hai, nó sẽ không biên dịch vì `Function.apply` không công bố IOException.

Method reference hữu ích để viết ngắn nhưng **không làm mất checked exception**. Nếu có method overload, compiler còn xét overload resolution theo target type của method reference; việc đổi kiểu target có thể ảnh hưởng phương thức cụ thể được tham chiếu. Cần kiểm tra chữ ký thực tế thay vì giả định mọi `MyClass::read` luôn tương ứng một phương thức.

Trong chương trình `CheckedFunctionDemo`, method reference `CheckedFunctionDemo::read` đã được dùng trong một ví dụ hoàn chỉnh có `throws IOException`.

## 14. Generics giúp giữ loại checked exception, nhưng không tạo generic exception class

Khai báo:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
```

là **hoàn toàn hợp lệ**. Interface generic có tham số `E` để biểu diễn kiểu ngoại lệ được phép ném, nhưng **chính interface này không kế thừa `Throwable`**.

Điểm cần phân biệt:

- `<E extends Exception> ... throws E` trong phương thức generic là hợp lệ theo JLS §8.4.6.
- `catch (E ex)` với E là type variable không hợp lệ; type variable không được dùng làm loại exception parameter.
- `class GenericFailure<E> extends Exception` không hợp lệ; Java cấm generic class kế thừa trực tiếp hoặc gián tiếp `Throwable`.
- `ThrowingFunction<T,R,E>` có thể ném một đối tượng của lớp ngoại lệ **không generic** như `IOException`, `SQLException` hoặc custom `DataLoadException`.

Nếu cần một callback có thể ném **nhiều loại checked exception độc lập** trong cùng một lần thực thi, một tham số `E` đôi khi làm việc suy luận kiểu kém chính xác hoặc buộc chọn lớp cha như `Exception`. Có thể định nghĩa một hợp đồng `throws IOException, SQLException` rõ ràng khi hai loại là phần ổn định của API, hoặc dùng thiết kế dựa trên result type. Không tự động ép mọi callback thành `throws Exception` nếu bên gọi cần biết chính xác điều gì có thể xảy ra.

## 15. Ba chính sách khác nhau khi một phần tử bị lỗi

Với một batch gồm các khóa `a, bad, c`, cùng một lỗi đọc có thể dẫn tới ba kết quả khác nhau:

| Chính sách | Cách biểu diễn | Tác dụng |
| --- | --- | --- |
| **Continue after handling** | Bắt trong lambda, ghi nhận hợp lệ rồi tiếp tục | Xử lý mục tiếp theo; lỗi phải được ghi nhận theo hợp đồng |
| **Fail fast** | Chuyển thành unchecked exception có cause | Dừng đường xử lý hiện tại khi exception lan ra; tầng cao nhận lỗi |
| **Accumulate per-item failures** | Trả `Result`/`Outcome` | Vẫn tạo kết quả cho các mục độc lập; bên gọi phân loại lỗi từng mục |
| **Propagate checked** | Functional interface có `throws E` | Tầng gọi bắt/khai báo E; thường dùng khi kiểm soát API |
| **Cancellation** | Truyền `InterruptedException` hoặc khôi phục interrupt và kết thúc | Thông báo yêu cầu dừng công việc, không giả vờ thành công |

Đừng dựa vào cấu trúc `try-catch` để quyết định hoàn toàn chính sách nghiệp vụ. Bắt lỗi là **cơ chế ngôn ngữ**; tiếp tục xử lý, thử lại, bỏ qua, bọc lỗi, trả result hay hủy tác vụ là **quyết định của ứng dụng**.

Ví dụ, nếu mỗi phần tử ghi dữ liệu lên cơ sở dữ liệu và các phần tử cùng nằm trong một giao dịch, việc bắt `SQLException` rồi tiếp tục xử lý có thể làm trạng thái giao dịch không nhất quán. Nếu chúng là các phép đọc độc lập có thể báo lỗi từng mục, `Result` lại có thể phù hợp.

## 16. Không nên bắt rộng và vô tình nuốt lỗi runtime

Khi viết adapter tổng quát, cách sau có vấn đề:

```java
Function<String, String> reader = key -> {
    try {
        return readChecked(key);
    } catch (Exception ex) {
        return "";
    }
};
```

Đây là mẫu **cần tránh**. `catch (Exception)` bắt cả nhiều `RuntimeException` không liên quan như `NullPointerException` hoặc `IllegalStateException`, sau đó thay mọi lỗi bằng chuỗi rỗng. Bên gọi không thể phân biệt một chuỗi rỗng hợp lệ với một lỗi nghiêm trọng.

Nếu chính sách cần xử lý `IOException`, **bắt đúng `IOException`**:

```java
Function<String, String> reader = key -> {
    try {
        return readChecked(key);
    } catch (IOException ex) {
        throw new UncheckedIOException(
                "Reading key failed: " + key, ex);
    }
};
```

Đây là đoạn minh họa khi `readChecked(String) throws IOException` tồn tại, và import được khai báo. Việc giữ cause giúp chẩn đoán nơi lỗi phát sinh. Nếu `key` chứa dữ liệu nhạy cảm, đừng đưa nó thẳng vào message/log.

Một adapter `catch(Exception) { throw new RuntimeException(ex); }` tổng quát có thể che giấu cả `InterruptedException` lẫn lỗi runtime vốn không cần bọc. Chỉ dùng nếu API thực sự muốn mọi lỗi checked được chuyển theo chính sách đã công bố, và thiết kế riêng đường hủy/gián đoạn.

## 17. Mỗi lambda có phạm vi `try-catch` riêng

Đặt `try-catch` quanh câu lệnh **tạo lambda** không có nghĩa nó bao quanh lần thực thi về sau:

```java
Function<String, String> reader;

try {
    reader = key -> readChecked(key); // Vẫn lỗi biên dịch.
} catch (RuntimeException ex) {
    // Không phải nơi xử lý IOException checked từ thân lambda.
}
```

Đây là ví dụ **cố ý không biên dịch**, giả định `readChecked` ném `IOException`. Checked exception trong thân lambda không tự lan ra khi tạo lambda, nên `try-catch` quanh chỗ gán không thay được hợp đồng của `Function.apply`.

Nếu lambda bọc checked exception thành unchecked, caller có thể bắt tại lúc **kích hoạt** callback:

```java
Function<String, String> reader = key -> {
    try {
        return readChecked(key);
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};

try {
    System.out.println(reader.apply("bad"));
} catch (UncheckedIOException ex) {
    System.out.println("failure=" + ex.getCause().getMessage());
}
```

Đây là hai đoạn minh họa trong thân phương thức; import và `readChecked` cần được định nghĩa. Ở Stream API, điểm kích hoạt thường là terminal operation; với `ExecutorService`, callback có thể chạy trong worker thread và ngoại lệ được biểu diễn qua `Future`.

**Phải phân biệt thời điểm khai báo lambda và thời điểm callback được gọi.** Nếu không, bạn có thể bắt lỗi ở một phạm vi không bao giờ chứng kiến ngoại lệ đó.

## 18. Ưu tiên thiết kế API rõ hợp đồng hơn “sneaky throw”

Một số đoạn mã dùng generic cast hoặc mẹo kiểu để ném checked exception **như thể** unchecked, thường được gọi là *sneaky throw*. Dù có thể tồn tại các kỹ thuật như vậy, chúng làm hợp đồng khó hiểu: tầng gọi không nhìn thấy loại lỗi thật trong `throws`, trong khi ngoại lệ checked vẫn có thể xuất hiện tại runtime.

Với mục tiêu học và xây thư viện dễ bảo trì, nên chọn một trong ba cơ chế **hiển thị rõ**:

- Một `try-catch` chủ động phục hồi ngay trong lambda.
- Một wrapper unchecked đúng ý nghĩa có cause, ví dụ `UncheckedIOException` hoặc custom domain runtime exception.
- Một functional interface riêng với `throws E` và caller quản lý checked exception.

Khi cần tiếp tục batch, một `Outcome`/`Result` biểu diễn thất bại cũng minh bạch hơn việc giấu ngoại lệ sau các cast khó đọc. Sử dụng `throws Exception` một cách quá rộng hoặc “giấu” checked exception không giúp mô hình lỗi của ứng dụng chính xác hơn.

## 19. Những lỗi thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Gán lambda gọi `throws IOException` cho `Function<T,R>` mà không catch | Không biên dịch | Bắt trong lambda, adapter/bọc, hoặc interface có `throws` |
| Thêm `throws IOException` vào phương thức *tạo* lambda | Không sửa hợp đồng `Function.apply` | Xử lý theo function type, không theo vị trí gán |
| Đổi sang method reference `Class::read` để “né checked” | Vẫn phải tương thích với target type | Dùng target interface cho phép `throws` |
| Bắt `Exception` rồi trả `null`/chuỗi rỗng cho mọi lỗi | Che sự cố và vi phạm hợp đồng dữ liệu | Bắt loại đúng, xác định fallback hợp lệ |
| Bọc `IOException` bằng runtime wrapper mà bỏ cause | Mất đường chẩn đoán | Truyền `ex` làm cause |
| Dùng `UncheckedIOException` cho `SQLException` | Sai hợp đồng loại lỗi | Tạo domain exception hoặc wrapper phù hợp |
| Trả `Optional.empty()` dù caller cần lý do thất bại | Mất loại lỗi, message, stack trace | Trả Result/Outcome có error |
| Dùng `ThrowingFunction` trực tiếp với `Stream.map` | Không tương thích với `Function` chuẩn | Dùng adapter hoặc API riêng nhận ThrowingFunction |
| Mong `catch(IOException)` quanh việc tạo Stream sẽ bắt lỗi từ `map` | Pipeline lazy; lỗi khi thực thi terminal operation | Đặt xử lý ở đúng điểm thực thi |
| Catch `InterruptedException` rồi tiếp tục im lặng | Có thể làm mất tín hiệu hủy | Truyền interrupt hoặc restore flag và kết thúc |
| Bọc lại mọi `RuntimeException` mà không thêm ý nghĩa | Chain dài, mất ý nghĩa loại lỗi | Cho lỗi phù hợp lan truyền |
| Dùng callback trong parallel stream rồi dựa vào side effect tuần tự | Thứ tự/hoàn tất có thể khác giả định | Thiết kế xử lý concurrency/ordering rõ |
| Tạo custom generic exception `MyException<E>` | Java cấm generic subtype của Throwable | Dùng exception không generic; generic ở interface/result |
| Chỉ chạy test happy path | Không kiểm tra chính sách lỗi và cause | Test đường lỗi, dòng output, cause chain, interrupt |

## 20. Checklist chọn hướng xử lý

Trước khi viết lambda gọi một phương thức có `throws`, tự hỏi:

1. **Target type là gì?** `Runnable`/`Function`/`Consumer` không khai báo checked exception, hay `Callable`/interface riêng có cho phép?
2. **Loại ngoại lệ cụ thể nào có thể phát sinh?** `IOException`, `SQLException`, `InterruptedException` hay custom checked exception?
3. **Bạn kiểm soát API nhận lambda không?** Nếu có, cân nhắc interface có `throws` để giữ checked exception nguyên dạng.
4. **Lỗi có thể phục hồi hợp lệ ngay tại phần tử không?** Nếu có, catch cục bộ với fallback/ghi nhận rõ ràng.
5. **Nếu không phục hồi, có cần dừng pipeline/tác vụ không?** Có thể bọc unchecked có cause rồi xử lý ở tầng ranh giới.
6. **Caller cần kết quả cho mọi phần tử?** Nếu có, cân nhắc Result/Outcome thay cho ném lỗi dừng cả batch.
7. **Lỗi có phải interrupt?** Truyền tín hiệu hoặc khôi phục trạng thái interrupt và kết thúc đúng chính sách.
8. **Đường thực thi lambda ở đâu?** Trực tiếp, Stream terminal operation, executor hay callback bất đồng bộ? Đặt catch ở nơi có thể chứng kiến lỗi.
9. **Thông tin gốc còn không?** Dùng `getCause()`, log toàn bộ `Throwable`, giữ suppressed nếu lỗi gốc có.
10. **Kiểm tra compiler và test:** một mã chạy thành công không chứng minh đường checked exception đã đúng; biên dịch với JDK đích và thử cả tình huống thất bại.

### Bảng quyết định nhanh

| Hoàn cảnh | Lựa chọn có xu hướng phù hợp |
| --- | --- |
| Callback được phép bỏ qua một bản ghi lỗi sau khi ghi nhận, các bản ghi độc lập | `try-catch` bên trong lambda |
| `Stream.map` phải dừng khi I/O hỏng và caller chịu trách nhiệm | Bọc `IOException` bằng `UncheckedIOException`, giữ cause |
| Viết API nội bộ nhận callback mà caller cần xử lý checked exception rõ ràng | `ThrowingFunction<T,R,E>` / `ThrowingConsumer<T,E>` |
| Cần báo thành công/thất bại riêng cho từng mục | `Result`/`Outcome` |
| Gọi tác vụ trả kết quả cho executor với checked exception | `Callable<V>` và xử lý `Future.get()`/`ExecutionException` |
| Callback có thể bị interrupt | Hợp đồng `throws InterruptedException` hoặc catch + restore flag và kết thúc |
| Thư viện buộc dùng `Supplier<T>`/`Function<T,R>` | Adapter minh bạch theo policy; không dùng sneaky throw |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Function<String,String> f = x -> read(x);` không biên dịch nếu `read` khai báo `throws IOException`?  
Vì phương thức `Function.apply` không công bố `IOException`, nên lambda không được phép để checked exception này thoát.

**Câu 2.** Thêm `throws IOException` vào phương thức đang khai báo biến `f` có đủ không?  
**Không.** Exception checking của thân lambda dựa vào function type đích, không phải chữ ký của phương thức tạo lambda.

**Câu 3.** `UncheckedIOException` dùng để bọc loại lỗi nào?  
**`IOException`.** Nó là unchecked wrapper có constructor nhận IOException và cause được giữ.

**Câu 4.** `Stream.map` có chạy callback ngay khi được gọi không?  
**Không.** `map` là thao tác trung gian lazy; callback được đánh giá khi có terminal operation thích hợp.

**Câu 5.** `ThrowingFunction<String,String,IOException>` có thể mang method reference trỏ tới phương thức `throws IOException` không?  
**Có**, vì `apply` công bố `throws IOException`.

**Câu 6.** Có thể truyền trực tiếp `ThrowingFunction` vào `Stream.map` không?  
**Không**, vì `map` yêu cầu `Function` chuẩn; cần adapter hoặc đổi API.

**Câu 7.** Nếu muốn xử lý tiếp các bản ghi sau một lỗi riêng lẻ và giữ nguyên lỗi, có thể dùng cách nào?  
Một `Result`/`Outcome` chứa giá trị thành công hoặc đối tượng ngoại lệ, rồi xử lý từng kết quả.

**Câu 8.** `Callable.call()` và `Runnable.run()` khác nhau về checked exception thế nào?  
`Callable.call() throws Exception`; `Runnable.run()` không khai báo checked exception.

**Câu 9.** Có nên catch `InterruptedException` trong `Runnable` rồi chỉ in log, bỏ qua yêu cầu dừng?  
**Không nên.** Cần truyền lên nếu hợp đồng cho phép, hoặc restore interrupt flag và kết thúc tác vụ đúng chính sách.

**Câu 10.** Bọc checked exception thành unchecked có nghĩa ngoại lệ được “xử lý thành công” chưa?  
**Chưa.** Đó chỉ là **đổi hợp đồng lan truyền**. Tầng tiếp nhận wrapper vẫn phải áp dụng chính sách xử lý thực tế.

## Tài liệu tham khảo

- [JLS Java SE 21 — §15.27.3, Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.27.3).
- [JLS Java SE 21 — §11.2.3, Exception Checking](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.3).
- [JLS Java SE 21 — §8.4.6, Method Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.6).
- [Java SE 21 API — `Function<T,R>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Function.html).
- [Java SE 21 API — `UncheckedIOException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/UncheckedIOException.html).
- [Java SE 21 API — `Callable<V>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html).
- [Java SE 21 API — `Stream<T>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html).

**Ghi nhớ:** Khi lambda có thể ném checked exception, hãy nhìn vào **functional interface đích**. Bắt tại chỗ khi có chính sách phục hồi đúng; bọc thành unchecked **có cause** khi API chuẩn không cho truyền checked mà caller cần biết lỗi; hoặc dùng **interface riêng có `throws`** khi bạn kiểm soát API và muốn giữ chính xác hợp đồng checked exception. Với nhiều bản ghi độc lập, có thể dùng Result/Outcome để biểu diễn lỗi như dữ liệu thay vì nuốt lỗi hay buộc toàn bộ pipeline dừng.
