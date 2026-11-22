# UncheckedIOException khi API không khai báo checked IOException

Trong Java, `java.io.IOException` là **checked exception**: nếu một lời gọi có thể ném nó, phương thức bao quanh phải bắt hoặc khai báo `throws` phù hợp. Tuy nhiên, nhiều callback quan trọng của Java như `Function.apply`, `Consumer.accept`, `Supplier.get`, `Predicate.test` và `Runnable.run` **không khai báo checked exception**. Điều gì xảy ra khi logic đặt bên trong callback vẫn phải đọc file, ghi dữ liệu hay làm I/O?

`java.io.UncheckedIOException` cung cấp một cách **bọc IOException thành unchecked exception** có ý nghĩa rõ ràng. Nó kế thừa `RuntimeException`, giữ `IOException` gốc làm **cause** và có thể lan truyền qua những API không cho checked `throws`. Bên xử lý cuối vẫn đọc được nguyên nhân thật thông qua `getCause()`.

**Quy tắc cần nhớ:** dùng `UncheckedIOException` khi **thao tác thực sự thất bại vì IOException**, nhưng **ranh giới callback/API không cho phép truyền trực tiếp checked IOException**, và **chính sách hợp đồng cho phép chuyển thất bại đó thành unchecked**. Đây không phải mẹo bỏ qua lỗi: chương trình vẫn thất bại nếu không được xử lý, việc chuyển đổi phải có chủ đích, và gọi lại thao tác chưa chắc an toàn.

Bài này giải thích phân cấp, cách dùng constructor, các ví dụ Java 17 có thể chạy được, lambda và method reference, Stream API, `Files.lines`/`BufferedReader.lines`, adapter tái sử dụng, catch và unwrap, tài nguyên, exception propagation, rủi ro retry, kiểm thử, và những trường hợp không nên dùng wrapper.

## 1. `UncheckedIOException` nằm ở đâu trong hệ phân cấp?

Sơ đồ rút gọn:

```text
java.lang.Throwable
├── java.lang.Error
└── java.lang.Exception
    ├── java.io.IOException                (checked)
    │   ├── java.io.FileNotFoundException
    │   ├── java.nio.file.FileSystemException
    │   └── ...
    └── java.lang.RuntimeException         (unchecked)
        ├── java.io.UncheckedIOException
        ├── java.lang.IllegalArgumentException
        ├── java.lang.IllegalStateException
        └── ...
```

Những điểm quyết định:

- `IOException` và các subclass thông thường của nó là **checked**.
- `UncheckedIOException extends RuntimeException` nên **unchecked**.
- `UncheckedIOException` **không kế thừa `IOException`**. Một `catch (IOException e)` không bắt trực tiếp object `UncheckedIOException`.
- `UncheckedIOException` **chứa một `IOException`** làm nguyên nhân (`cause`). Đây là quan hệ **chứa/chuỗi nguyên nhân**, không phải quan hệ subtype.
- Constructor của `UncheckedIOException` yêu cầu nguyên nhân là một `IOException`; không phải mọi `Exception` đều có thể trực tiếp làm cause trong constructor chuyên biệt ấy.
- `UncheckedIOException` xuất hiện trong Java từ Java 8, phù hợp với giai đoạn sử dụng nhiều Stream API/lambda.

Ví dụ kiểu:

```java
IOException original = new IOException("Không đọc được tệp");
UncheckedIOException wrapped = new UncheckedIOException(
        "Lỗi I/O trong callback", original);

System.out.println(wrapped instanceof RuntimeException);
System.out.println(wrapped.getCause() == original);
```

Đây là **đoạn minh họa** cần import `java.io.IOException` và `java.io.UncheckedIOException`, có thể đặt trong một phương thức. Hai phép kiểm tra in `true`. Ngược lại, không được viết `wrapped instanceof IOException`: ở đây hai lớp không có quan hệ kiểu cho phép kiểm tra đó và compiler Java có thể từ chối phép kiểm tra `instanceof` bất khả thi giữa các kiểu tĩnh không liên quan.

## 2. Checked exception không tương thích với mọi functional interface

Java sử dụng **single abstract method** (SAM) của functional interface để kiểm tra một lambda hay method reference.

Một số SAM thông dụng:

| Functional interface | SAM | Checked `throws` được công bố? |
| --- | --- | --- |
| `Runnable` | `void run()` | Không |
| `Supplier<T>` | `T get()` | Không |
| `Consumer<T>` | `void accept(T)` | Không |
| `Function<T,R>` | `R apply(T)` | Không |
| `Predicate<T>` | `boolean test(T)` | Không |
| `BiFunction<T,U,R>` | `R apply(T,U)` | Không |
| `Callable<V>` | `V call() throws Exception` | Có |
| Custom `IoFunction<T,R>` | `R apply(T) throws IOException` | Có nếu bạn định nghĩa |

Ví dụ method đọc dữ liệu:

```java
static String read(String path) throws IOException {
    return Files.readString(Path.of(path));
}
```

Đây là **method minh họa**, cần import `IOException`, `Files` và `Path`. Nếu cố gán:

```java
Function<String, String> fn = Example::read;
```

thì **không biên dịch** (giả định method thuộc lớp `Example`), vì `Function.apply()` không khai báo `throws IOException`.

Dùng method reference `::` không làm exception tự biến thành unchecked. Tương tự:

```java
Function<String, String> fn = x -> Files.readString(Path.of(x));
```

là **phản ví dụ không biên dịch**: thân lambda có thể ném checked `IOException`. Việc khai báo `throws IOException` ở phương thức bao ngoài **không sửa được** hợp đồng `Function.apply`, vì lỗi nằm ở biểu thức dùng để tạo callback.

## 3. Vì sao không thể “thêm throws” cho `Function.apply`?

Interface chuẩn có chữ ký `R apply(T t)`, không phải `R apply(T t) throws IOException`. Khi triển khai hoặc sử dụng biểu thức lambda theo `Function`, implementation không được khai báo checked exception rộng hơn hợp đồng của SAM.

Ví dụ **cố ý không hợp lệ**:

```java
class FileMapper implements Function<String, String> {
    @Override
    public String apply(String path) throws IOException {
        return Files.readString(Path.of(path));
    }
}
```

Đây là **đoạn phản ví dụ** cần import tương ứng. Compiler báo lỗi vì method override thêm checked `IOException` không có trong `Function.apply`.

Có bốn hướng xử lý chính:

1. **Không dùng `Function`** khi kiểm soát API: định nghĩa custom SAM có `throws IOException` và truyền checked exception một cách tường minh.
2. **Bắt và phục hồi thật sự** bên trong callback: chọn fallback phù hợp hoặc trả một result type.
3. **Bắt `IOException` rồi bọc trong `UncheckedIOException`** nếu muốn exception vẫn lan ra nhưng qua một hợp đồng unchecked.
4. **Thay đổi cấu trúc**: đưa thao tác I/O ra ngoài callback/pipeline, nơi có thể khai báo `throws IOException`.

`UncheckedIOException` tương ứng với hướng 3, không thay thế các hướng còn lại.

## 4. Hai constructor thông dụng

Hai constructor được sử dụng:

```java
new UncheckedIOException(ioException);

new UncheckedIOException("Mô tả ngữ cảnh", ioException);
```

Đây là **các biểu thức minh họa**; biến `ioException` có kiểu `IOException`. Constructor có message rất hữu ích để bổ sung ngữ cảnh như “không đọc được tập cấu hình” hoặc “thất bại khi biến đổi phần tử trong stream”.

Ví dụ:

```java
try {
    saveReport();
} catch (IOException e) {
    throw new UncheckedIOException(
            "Ghi báo cáo thất bại", e);
}
```

Đây là **đoạn minh họa** với `saveReport() throws IOException` được định nghĩa ở nơi khác. Kết quả:

- Exception ngoài là `UncheckedIOException`.
- `getMessage()` chứa mô tả do bạn cung cấp.
- `getCause()` trả về object `IOException` gốc.
- Cause giữ stack trace và thông tin của lỗi thấp hơn.
- Caller không bị compiler buộc catch/declare `UncheckedIOException` nhưng chương trình vẫn có thể bị ngắt khi callback thực thi.

**Constructor yêu cầu cause khác null.** Đừng tạo wrapper với cause giả hoặc `null` để biểu diễn một tình trạng “không có file” không liên quan lỗi I/O thực tế.

## 5. Ví dụ Java 17 độc lập: bọc và bắt đúng loại

Lưu **`UncheckedIOExceptionBasicsDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;

public class UncheckedIOExceptionBasicsDemo {
    static void load() {
        try {
            simulateRead();
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Không tải được cấu hình", e);
        }
    }

    static void simulateRead() throws IOException {
        throw new IOException("Thiết bị đọc thất bại");
    }

    public static void main(String[] args) {
        try {
            load();
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 UncheckedIOExceptionBasicsDemo.java
java UncheckedIOExceptionBasicsDemo
```

**Stdout chính xác:**

```text
Wrapper: UncheckedIOException
Message: Không tải được cấu hình
Cause: IOException
Cause message: Thiết bị đọc thất bại
```

Chương trình **chủ động mô phỏng lỗi bằng `IOException`**, không phụ thuộc ổ đĩa hay mạng thực. Điều này thích hợp cho unit test hành vi wrapping.

Lưu ý lỗi được chuyển loại **ở ranh giới `load()`**. Nếu API bên ngoài có thể cho `throws IOException` thì việc bọc chưa chắc đem lại giá trị; phải cân nhắc trách nhiệm caller.

## 6. `getCause()` có kiểu trả về đặc biệt

Trong `Throwable`, `getCause()` trả `Throwable`. Riêng `UncheckedIOException` override `getCause()` theo kiểu trả về hẹp hơn: **`IOException`**.

Vì vậy có thể viết:

```java
UncheckedIOException failure =
        new UncheckedIOException(new IOException("I/O"));

IOException original = failure.getCause();
System.out.println(original.getClass().getSimpleName());
```

Đây là **mã minh họa** cần import hai lớp. Nó in `IOException` và không cần ép kiểu thủ công.

Điều này khác `new RuntimeException(ioException)`:

```java
RuntimeException generic = new RuntimeException(
        new IOException("I/O"));
// IOException original = generic.getCause(); // Không biên dịch.
// getCause() ở đây có kiểu tĩnh Throwable.
```

Không nên hiểu rằng `UncheckedIOException` làm lỗi thấp hơn biến mất. Đây là wrapper **chuyên biệt cho I/O**: loại của cause và ý nghĩa nguyên nhân được giữ.

## 7. Khi nào nên sử dụng `UncheckedIOException`?

Nó thích hợp khi ba điều kiện đồng thời có ý nghĩa:

1. **Có `IOException` thật** từ một thao tác I/O hoặc API có hợp đồng I/O.
2. **Ranh giới đang dùng không cho checked `throws IOException`**; ví dụ `Function` trong `Stream.map`, `Consumer` trong `forEach`, `Runnable` trong executor.
3. **Chính sách cho phép thất bại lan ra theo unchecked exception** để tầng có trách nhiệm xử lý, báo lỗi hoặc hủy thao tác.

Một số ví dụ:

- Ánh xạ danh sách `Path` sang nội dung file bằng `Stream.map`.
- Đọc dữ liệu trong `forEach` của một API chỉ nhận `Consumer`.
- Một adapter để truyền function có I/O sang `Function<T,R>`.
- Thực thi `Runnable` cần I/O nhưng framework không có checked `throws`.
- Một stream đọc dữ liệu lười (*lazy*) mà tài liệu API quy định exception đọc phát sinh lúc terminal operation được chuyển thành `UncheckedIOException`.

**Không nên bọc đơn thuần để “làm compiler hết báo”**. Nếu một library công khai yêu cầu caller chọn cách phục hồi I/O, giữ checked `IOException` hoặc thiết kế callback có `throws` vẫn có thể đúng hơn.

## 8. `Stream.map`: vì sao lỗi compile xuất hiện?

`Stream.map` nhận `Function<? super T, ? extends R>`. SAM `Function.apply` không khai báo checked exception, vì vậy biểu thức sau **cố ý không biên dịch**:

```java
Stream<Path> paths = Stream.of(Path.of("a.txt"));
Stream<String> contents = paths.map(Files::readString);
```

Giả định import `java.util.stream.Stream` và `java.nio.file.Files, Path`. Phương thức `Files.readString(Path)` có `throws IOException`; method reference không tương thích `Function<Path,String>`.

Đoạn lambda tương đương:

```java
Stream<String> contents = paths.map(
        path -> Files.readString(path));
```

cũng không biên dịch với cùng lý do.

**Một `try/catch` bao lấy dòng tạo pipeline không tự sửa vấn đề**, vì checked exception thuộc phần triển khai của SAM. Bạn phải thay đổi **bên trong biểu thức lambda**, hoặc thay target interface/cấu trúc.

Đối với stream, cũng cần nhớ nhiều thao tác là **lazy**: tạo pipeline không nhất thiết gọi mapper ngay, nên exception wrapper có thể chỉ xuất hiện khi terminal operation tiêu thụ phần tử.

## 9. Ví dụ chạy được: chuyển `IOException` sang `UncheckedIOException` trong `map`

Lưu **`StreamUncheckedIOExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

public class StreamUncheckedIOExceptionDemo {
    static String read(String key) throws IOException {
        if ("missing".equals(key)) {
            throw new IOException("Không tìm thấy dữ liệu: " + key);
        }
        return "Nội dung " + key;
    }

    public static void main(String[] args) {
        List<String> keys = List.of("one", "missing", "three");

        try {
            List<String> results = keys.stream()
                    .map(key -> {
                        try {
                            return read(key);
                        } catch (IOException e) {
                            throw new UncheckedIOException(
                                    "Đọc phần tử thất bại", e);
                        }
                    })
                    .toList();

            System.out.println("Kết quả: " + results);
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: " + e.getMessage());
            System.out.println("Cause: " + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 StreamUncheckedIOExceptionDemo.java
java StreamUncheckedIOExceptionDemo
```

**Stdout chính xác:**

```text
Wrapper: Đọc phần tử thất bại
Cause: Không tìm thấy dữ liệu: missing
```

Các điểm cần hiểu:

1. `read(key) throws IOException` là method mô phỏng thao tác I/O.
2. `Stream.map` không cho checked exception của mapper.
3. Lambda **bắt tại chỗ** và ném `UncheckedIOException`.
4. `toList()` tiêu thụ stream; khi gặp `"missing"`, mapper phát sinh exception.
5. Vì terminal operation không hoàn tất, biến `results` không nhận một danh sách kết quả cuối cùng và dòng in `Kết quả` không chạy.
6. Handler bên ngoài bắt exception đã chuyển loại, lấy cause để chẩn đoán.

**Không đồng nghĩa mọi phần tử sau `"missing"` đã được xử lý**. Với stream tuần tự ví dụ này, phép tính dừng ở lỗi; với parallel stream, điều kiện lỗi và side effect phức tạp hơn, không nên giả định thứ tự fail-fast hoặc rollback tự động.

## 10. Điều quan trọng: stream lazy và thời điểm phát sinh lỗi

Một stream pipeline có thể được tạo mà chưa đọc file hay gọi mapper. Chỉ khi terminal operation như `toList()`, `count()`, `forEach()`, `reduce()` hoặc một thao tác tiêu thụ khác chạy, callback mới có thể được gọi.

Ví dụ Java 17 **`StreamLazyIoDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.stream.Stream;

public class StreamLazyIoDemo {
    static String read(String name) throws IOException {
        System.out.println("Đang đọc: " + name);
        if ("bad".equals(name)) {
            throw new IOException("Không đọc được bad");
        }
        return name.toUpperCase();
    }

    public static void main(String[] args) {
        Stream<String> pipeline = Stream.of("ok", "bad")
                .map(name -> {
                    try {
                        return read(name);
                    } catch (IOException e) {
                        throw new UncheckedIOException(
                                "Mapper gặp lỗi", e);
                    }
                });

        System.out.println("Đã tạo pipeline");

        try {
            pipeline.forEach(System.out::println);
        } catch (UncheckedIOException e) {
            System.out.println("Bắt: " + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 StreamLazyIoDemo.java
java StreamLazyIoDemo
```

**Stdout chính xác:**

```text
Đã tạo pipeline
Đang đọc: ok
OK
Đang đọc: bad
Bắt: Không đọc được bad
```

`pipeline` được tạo trước, nhưng phần đọc bắt đầu khi `forEach` là terminal operation chạy. Khi I/O thất bại, exception bọc được ném ra ngoài `forEach`.

**Không được suy rằng mọi terminal operation đều thực thi mọi mapper**. Ví dụ một số tối ưu hóa stream hoặc short-circuit operation có thể tránh chạy những stage nhất định. Đối với code I/O có side effect, lựa chọn Stream API cần tính tới tính lazy, tối ưu hóa và chính sách đóng tài nguyên.

## 11. `Consumer.accept` và `forEach` cũng không khai báo checked exception

`Consumer<T>` nhận một giá trị và không trả kết quả; `accept(T)` không khai báo checked exception. Vì vậy:

```java
items.forEach(item -> writeToDisk(item));
```

là **phản ví dụ cố ý không biên dịch** nếu `writeToDisk` khai báo `throws IOException` (và `items` có kiểu phù hợp).

Cách chuyển loại có chủ đích:

```java
items.forEach(item -> {
    try {
        writeToDisk(item);
    } catch (IOException e) {
        throw new UncheckedIOException(
                "Ghi phần tử thất bại", e);
    }
});
```

Đây là **mã minh họa** cần biến `items`, method `writeToDisk` và import các lớp. Bất kỳ lỗi nào tại callback có thể thoát thành unchecked exception; `forEach` không tự catch hoặc tự retry.

**Nguy cơ lớn hơn với ghi dữ liệu:** một số phần tử trước đó có thể đã được ghi thành công. Khi gặp lỗi giữa vòng lặp, không có rollback tự động. Nếu việc ghi nhiều mục phải nguyên tử, cần cơ chế transaction, staging hoặc compensating action theo hệ thống đích.

## 12. Khi dùng `Runnable` hoặc job executor

`Runnable.run()` không khai báo checked exception. Nếu công việc phải gọi API ném `IOException`, bạn có thể bắt và bọc:

```java
Runnable job = () -> {
    try {
        doIoWork();
    } catch (IOException e) {
        throw new UncheckedIOException(
                "Job thất bại vì I/O", e);
    }
};
```

Đây là **mã minh họa**, `doIoWork() throws IOException` phải được định nghĩa.

Sự khác biệt:

- `job.run()` trực tiếp có thể ném `UncheckedIOException` cho caller.
- Nếu `job` được thực thi bởi `ExecutorService.submit`, lỗi có thể được quan sát qua `Future.get()` dưới dạng `ExecutionException` theo hợp đồng executor.
- Với `CompletableFuture`, lỗi của task có thể được bọc bởi `CompletionException` khi `join()` hoặc API tương ứng truyền thất bại.
- Các wrapper do framework tạo là **tầng khác** với `UncheckedIOException` mà code của bạn ném. Muốn phân loại nguyên nhân sâu hơn, có thể phải xem cause chain.

**Không nhầm** “unchecked” với “đã được thread pool xử lý thành công”. Exception có thể nằm trong kết quả Future và không tự động được in ra console theo cách bạn tưởng.

## 13. `Callable` có thể là lựa chọn giữ checked exception

`Callable<V>.call() throws Exception` **cho phép checked exception**. Nếu bạn kiểm soát interface callback cần dùng, không nhất thiết phải bọc.

Ví dụ Java 17 **`CallableCheckedDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;

public class CallableCheckedDemo {
    static String read() throws IOException {
        throw new IOException("Nguồn chưa sẵn sàng");
    }

    public static void main(String[] args) {
        Callable<String> task = CallableCheckedDemo::read;

        try {
            task.call();
        } catch (Exception e) {
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 CallableCheckedDemo.java
java CallableCheckedDemo
```

**Stdout chính xác:**

```text
Loại: IOException
Message: Nguồn chưa sẵn sàng
```

Phương thức `read() throws IOException` tương thích với `Callable.call() throws Exception`. Ở điểm gọi qua biến `Callable`, compiler buộc caller catch/declare `Exception` theo chữ ký rộng của SAM.

**Đừng đổi sang `UncheckedIOException` chỉ vì đã quen cách viết adapter**, nếu hợp đồng hiện tại đã cho checked I/O và caller có trách nhiệm xử lý nó.

## 14. Thiết kế functional interface riêng có `throws IOException`

Nếu tạo API của mình, có thể mô tả khả năng I/O trực tiếp:

```java
@FunctionalInterface
interface IoFunction<T, R> {
    R apply(T input) throws IOException;
}
```

Đây là **interface minh họa**, cần import `java.io.IOException`. Method reference `Files::readString` có thể thích hợp với `IoFunction<Path,String>` do tham số, kiểu trả về và checked exception khớp.

Ví dụ độc lập **`IoFunctionCheckedDemo.java`**:

```java
import java.io.IOException;

public class IoFunctionCheckedDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T input) throws IOException;
    }

    static String read(String name) throws IOException {
        if (name.isBlank()) {
            throw new IOException("Tên nguồn rỗng");
        }
        return "DATA:" + name;
    }

    static <T, R> R execute(IoFunction<T, R> task, T input)
            throws IOException {
        return task.apply(input);
    }

    public static void main(String[] args) {
        IoFunction<String, String> task = IoFunctionCheckedDemo::read;

        try {
            System.out.println(execute(task, "orders"));
            System.out.println(execute(task, ""));
        } catch (IOException e) {
            System.out.println("Đã bắt IOException: "
                    + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 IoFunctionCheckedDemo.java
java IoFunctionCheckedDemo
```

**Stdout chính xác:**

```text
DATA:orders
Đã bắt IOException: Tên nguồn rỗng
```

Ở đây không cần `UncheckedIOException`, vì **toàn bộ chuỗi callback và phương thức gọi** cho phép checked `IOException`.

Thiết kế này hữu ích khi người dùng API thực sự cần phân biệt I/O failure theo compile-time contract. Ngược lại, các framework chuẩn nhận `Function` thì không thể tự sửa chữ ký `Function.apply`, lúc đó adapter là một lựa chọn.

## 15. Adapter chuyển `IoFunction` thành `Function`

Để tránh lặp `try/catch` trong mọi lambda, có thể tạo một adapter tái sử dụng. Trọng tâm của adapter là **thay đổi hợp đồng lỗi tại một điểm rõ ràng**.

Lưu **`IoFunctionAdapterDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class IoFunctionAdapterDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T input) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(
            IoFunction<T, R> function) {
        Objects.requireNonNull(function, "function");
        return input -> {
            try {
                return function.apply(input);
            } catch (IOException e) {
                throw new UncheckedIOException(
                        "I/O trong Function.apply", e);
            }
        };
    }

    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("Không đọc được bad");
        }
        return "OK-" + key;
    }

    public static void main(String[] args) {
        Function<String, String> mapper =
                unchecked(IoFunctionAdapterDemo::read);

        System.out.println(mapper.apply("good"));

        try {
            List<String> values = List.of("a", "bad", "c");
            System.out.println(values.stream()
                    .map(mapper)
                    .toList());
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: " + e.getMessage());
            System.out.println("Cause: " + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 IoFunctionAdapterDemo.java
java IoFunctionAdapterDemo
```

**Stdout chính xác:**

```text
OK-good
Wrapper: I/O trong Function.apply
Cause: Không đọc được bad
```

Những ưu điểm:

1. Method reference `IoFunctionAdapterDemo::read` được target type `IoFunction` chấp nhận vì SAM có `throws IOException`.
2. Adapter trả `Function` dùng được trong `Stream.map`.
3. I/O failure vẫn đi ra dưới dạng `UncheckedIOException`, giữ cause.
4. Mọi nơi gọi adapter có **một chính sách chuyển lỗi nhất quán**.
5. `Objects.requireNonNull` làm rõ tiền điều kiện của adapter.

Nhược điểm: chữ ký `Function` đã bỏ ràng buộc checked exception; caller cần đọc tài liệu hợp đồng adapter và biết nơi nhận lỗi nếu pipeline thất bại.

## 16. Adapter cho `Consumer` và `Runnable`

Tương tự `IoFunction`, có thể xây các interface checked:

```java
@FunctionalInterface
interface IoConsumer<T> {
    void accept(T value) throws IOException;
}

@FunctionalInterface
interface IoRunnable {
    void run() throws IOException;
}
```

Đây là **hai interface minh họa** cần import `IOException`. Những adapter đơn giản:

```java
static <T> Consumer<T> uncheckedConsumer(IoConsumer<T> io) {
    return value -> {
        try {
            io.accept(value);
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Consumer I/O thất bại", e);
        }
    };
}

static Runnable uncheckedRunnable(IoRunnable io) {
    return () -> {
        try {
            io.run();
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Runnable I/O thất bại", e);
        }
    };
}
```

Đây là **các method minh họa**, giả định hai interface trên nằm trong phạm vi, đã import `Consumer`, `IOException` và `UncheckedIOException`.

Trước khi đưa adapter vào thư viện chung, nên xác định:

- Có thật cần cả ba kiểu `IoFunction`, `IoConsumer`, `IoRunnable` không?
- Khi I/O thất bại, handler cuối nằm ở đâu?
- Có cần message gắn tên tác vụ hoặc ID phần tử không?
- Có khả năng một tác vụ đã ghi **một phần** rồi lỗi không?
- API bên nhận `Consumer`/`Runnable` có chính sách riêng cho unchecked exception không?

Không tạo adapter “nuốt IOException và tiếp tục” nếu hợp đồng yêu cầu báo thất bại.

## 17. `Files.readString` vẫn khai báo checked `IOException`

Một lỗi hiểu biết thường gặp: vì đã có `UncheckedIOException` nên mọi API đọc file của JDK sẽ tự ném unchecked. **Không đúng.**

Ví dụ `Files.readString(Path)` khai báo `throws IOException`. Khi gọi trực tiếp:

```java
String text = Files.readString(Path.of("config.txt"));
```

đây là **mã minh họa**, method chứa cần catch/declare `IOException`. Java **không tự bọc thành `UncheckedIOException`** tại đây.

Nếu đưa nó vào `Stream.map`, bạn có thể chọn bọc trong lambda:

```java
Function<Path, String> readText = path -> {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        throw new UncheckedIOException(
                "Không đọc được: " + path.getFileName(), e);
    }
};
```

Đây là **đoạn minh họa**, cần import `Path`, `Files`, `Function`, `IOException` và `UncheckedIOException`.

Nguyên tắc: **hãy đọc JavaDoc của method cụ thể**. Một số JDK API tự bọc lỗi I/O ở giai đoạn lazy processing, trong khi các API khác tiếp tục dùng checked `IOException` trực tiếp.

## 18. `Files.lines`: lỗi khi mở stream và lỗi khi tiêu thụ stream

`Files.lines(Path)` tạo một `Stream<String>` đọc các dòng của file. Hợp đồng lỗi có hai thời điểm cần phân biệt:

1. **Mở nguồn / tạo stream:** lời gọi `Files.lines(path)` có thể ném **checked `IOException`**. Caller phải catch/declare.
2. **Đọc thêm dòng trong quá trình tiêu thụ stream:** nếu xảy ra lỗi I/O trong quá trình xử lý lười, hành vi của API có thể là ném **`UncheckedIOException`**.

Ví dụ cấu trúc:

```java
try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(System.out::println);
}
```

Đây là **mã minh họa** với `path` được định nghĩa, import `Stream` và `Files`; method bao ngoài phải xử lý/khai báo `IOException` từ bước mở.

**Điểm quan trọng:** `try-with-resources` đóng stream, giải phóng file handle. Việc stream bị đóng không tự bảo đảm lỗi đọc sẽ được xử lý; cần catch ở ranh giới thích hợp. Với pipeline có tác dụng phụ, những dòng trước khi lỗi phát sinh có thể đã được xử lý.

Nếu bạn chỉ catch `UncheckedIOException` mà bỏ qua checked `IOException` khi mở file, code có thể không biên dịch. Ngược lại, chỉ catch `IOException` quanh một pipeline không đủ để bắt wrapper unchecked từ giai đoạn đọc lười.

## 19. Ví dụ Java 17: đọc file theo dòng và đóng stream

Ví dụ này chạy được bằng một file tạm do chính chương trình tạo, **không phụ thuộc đường dẫn file có sẵn**. Nó minh họa thành công, không cố ép lỗi I/O không xác định.

Lưu **`FilesLinesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("line-demo-", ".txt");

        try {
            Files.writeString(file, "alpha\nbeta\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                lines.forEach(line ->
                        System.out.println("Dòng: " + line));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 FilesLinesDemo.java
java FilesLinesDemo
```

**Stdout chính xác khi filesystem cho phép tạo/đọc/xóa file tạm:**

```text
Dòng: alpha
Dòng: beta
```

Tại đây không có `UncheckedIOException` vì luồng đọc thành công. Điều quan trọng là **chữ ký `main throws IOException`** bao phủ các thao tác checked như tạo, ghi, mở và xóa file.

Ví dụ tạo/xóa file tạm trên máy học viên. Nếu sandbox cấm ghi filesystem, chương trình có thể ném `IOException` trước khi in stdout; đây là điều kiện môi trường, không phải hành vi exception wrapper.

## 20. `BufferedReader.lines()` và `UncheckedIOException`

`BufferedReader.lines()` trả về một stream các dòng. Vì `Stream` không có checked `throws IOException` trong những operation thông thường, **lỗi I/O xảy ra trong quá trình đọc các dòng bằng stream** được báo theo hợp đồng của `BufferedReader.lines()` bằng **`UncheckedIOException`**.

Ví dụ ý tưởng:

```java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    reader.lines().forEach(System.out::println);
}
```

Đây là **mã minh họa** với `path`, các import cần thiết và method bao ngoài xử lý checked `IOException` khi mở/đóng reader.

Chú ý:

- `Files.newBufferedReader(path)` có thể ném **checked IOException**.
- Việc tiêu thụ `reader.lines()` có thể ném **UncheckedIOException** nếu reader gặp lỗi I/O.
- `reader.lines()` không tự sở hữu/đóng reader độc lập; ở mẫu này, **try-with-resources bao reader**.
- Không đọc reader theo cách đồng thời ngoài stream khi stream đang được tiêu thụ; JavaDoc quy định không nên thao tác reader trong lúc stream đang vận hành vì kết quả có thể không xác định.
- Đừng suy rằng `BufferedReader.readLine()` (gọi trực tiếp) tự chuyển thành `UncheckedIOException`; nó vẫn khai báo checked `IOException`.

Sự khác biệt này là một ví dụ rõ: **cùng đối tượng dữ liệu, API trực tiếp và API stream có thể công bố exception khác nhau**.

## 21. Mẫu phân loại lỗi ở ranh giới đọc file

Một handler có thể phân biệt:

```java
try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(this::consumeLine);
} catch (UncheckedIOException e) {
    handleReadFailure(e.getCause());
} catch (IOException e) {
    handleOpenOrCloseFailure(e);
}
```

Đây là **mã khung minh họa**: cần `this::consumeLine` tương thích với `Consumer<String>`, không ném checked exception, và các method xử lý tồn tại. Thứ tự hai handler không chịu quan hệ subtype vì `UncheckedIOException` không kế thừa `IOException`.

**Không coi việc bắt riêng hai loại là bằng chứng chắc chắn lỗi xảy ra đúng một bước.** Ví dụ `IOException` cũng có thể phát sinh từ cleanup; nếu wrapper được ném trong thân, lỗi cleanup có thể là suppressed. Phân tích cần ngữ cảnh thao tác và cause.

Nếu một handler thật sự có thể phục hồi, hãy làm rõ việc xử lý tiếp theo. Nếu không, nên ném tiếp exception hoặc chuyển lỗi tới tầng có trách nhiệm, không in một dòng log rồi âm thầm trả thành công.

## 22. `Files.list`, `Files.walk` và thao tác thư mục

Các API liên quan filesystem cũng có thể dùng Stream, ví dụ:

- `Files.list(Path)`: tạo stream các entry trực tiếp trong thư mục, có thể ném checked `IOException` lúc mở.
- `Files.walk(Path, ...)`: tạo stream duyệt cây file, có thể ném checked `IOException` lúc thiết lập.
- Các lỗi I/O phát sinh trong giai đoạn lazy traversal có thể được chuyển thành `UncheckedIOException` theo hợp đồng API tương ứng.

Cần đặc biệt lưu ý:

1. **Đóng stream** bằng try-with-resources, vì stream có thể nắm tài nguyên hệ điều hành.
2. Một phần cây thư mục đã được duyệt trước khi lỗi xảy ra; không có rollback tự động.
3. Cây file có thể thay đổi trong khi duyệt; “file vừa kiểm tra tồn tại” không bảo đảm thao tác tiếp theo thành công.
4. Quyền truy cập, symbolic links, file bị xóa, mounted filesystem và race có thể gây I/O errors.
5. Không ném `UncheckedIOException` chỉ để diễn đạt việc một entry không thỏa filter; filter loại entry là **nhánh bình thường**, không phải lỗi I/O.

Một giải pháp nhận diện vấn đề là **chia rõ giai đoạn mở nguồn, xử lý stream, đóng nguồn**, thay vì catch `Exception` chung và mất ngữ cảnh.

## 23. `UncheckedIOException` không phải lỗi “không tìm thấy dữ liệu” theo nghĩa nghiệp vụ

Tên lớp mô tả **một IOException đã được wrap**, không mang ngữ nghĩa domain như `CustomerNotFoundException`.

Ví dụ:

- Một file cấu hình bắt buộc bị thiếu → `NoSuchFileException` khi truy cập file có thể là cause.
- Một key không tồn tại trong `Map` → thường không liên quan I/O; dùng kết quả rỗng hoặc exception contract khác.
- Một record không có trong database → có thể là kết quả nghiệp vụ bình thường, không được mặc định tạo `UncheckedIOException`.
- Một filesystem từ chối đọc do quyền truy cập → IOException phù hợp, có thể bọc nếu API không khai báo checked.
- Một response HTTP hợp lệ báo 404 → không đồng nghĩa đã xảy ra `IOException`; xử lý theo contract HTTP/domain.

**Không tự tạo `new IOException("not found")` chỉ để được dùng `UncheckedIOException`** khi tình huống thực chất không phải thất bại I/O. Lựa chọn exception phải phản ánh **nguyên nhân thật** và trách nhiệm caller.

## 24. Vì sao không dùng `RuntimeException` chung cho mọi lỗi?

Bạn có thể viết:

```java
throw new RuntimeException("I/O thất bại", e);
```

khi `e` là `IOException`. Nó cũng là unchecked và giữ cause. Nhưng `UncheckedIOException` có một số lợi ích về hợp đồng:

- **Tên lớp diễn đạt rõ đây là lỗi I/O được chuyển sang unchecked**, không phải một runtime failure bất kỳ.
- Constructor chuyên biệt bắt buộc cause kiểu `IOException`.
- `getCause()` trả `IOException`, giúp caller phân loại và lấy thông tin I/O rõ ràng.
- Handler có thể `catch (UncheckedIOException e)` thay vì catch rộng `RuntimeException`.
- Code review dễ nhìn thấy ranh giới thay đổi chính sách lỗi.

Mặt khác, nếu tầng mới muốn biểu diễn **một domain abstraction khác**, chẳng hạn `ReportGenerationException` với mã lỗi riêng, custom exception có thể phù hợp hơn. Không có quy tắc cứ cause là IOException thì **luôn** phải dùng `UncheckedIOException`.

Chọn wrapper theo **hợp đồng API bạn muốn công bố**, không chỉ theo sự tiện lợi.

## 25. Không được bọc mọi checked exception bằng `UncheckedIOException`

Constructor của `UncheckedIOException` nhận `IOException`, không phải `Throwable` tùy ý. Những checked exception khác cần chính sách riêng:

- `SQLException`: không phải subclass của `IOException`.
- `ClassNotFoundException`: không phải subclass của `IOException`.
- `InterruptedException`: không phải subclass của `IOException`.
- Domain checked exception tự định nghĩa có thể không liên quan I/O.

Phản ví dụ **không biên dịch**:

```java
SQLException sqlError = new SQLException("DB lỗi");
throw new UncheckedIOException(sqlError);
```

Đây là **đoạn minh họa không hợp lệ**, nếu đã import `SQLException` và `UncheckedIOException`. Compiler không tìm thấy constructor chấp nhận `SQLException`.

Nếu muốn chuyển checked exception tổng quát sang unchecked, cần chọn **wrapper đúng ý nghĩa** hoặc API cung cấp kiểu lỗi riêng. Đừng cố `new IOException(sqlError)` chỉ để ép một lỗi SQL vào loại I/O, trừ khi thực sự đang thiết kế abstraction I/O có lý do rõ ràng.

Đặc biệt, `InterruptedException` mang ý nghĩa hủy/interrupt; không được tự coi nó là một IOException để bỏ qua ngữ nghĩa ngắt.

## 26. `UncheckedIOException` và `InterruptedIOException`

`InterruptedIOException` kế thừa `IOException`. Vì vậy có thể làm cause của `UncheckedIOException` theo kiểu Java. Nhưng **`InterruptedIOException` không đồng nghĩa chắc chắn thread đã bị interrupt** trong mọi trường hợp.

Ví dụ `SocketTimeoutException extends InterruptedIOException` được dùng để báo thời hạn chờ socket đã hết. **Bắt một `SocketTimeoutException` và gọi `Thread.currentThread().interrupt()` vô điều kiện là sai** nếu chưa có dấu hiệu thread thật sự nhận interrupt.

Nếu một thao tác I/O bị ngắt vì thread cancellation, cần tuân theo contract của API đó (có thể cần khôi phục cờ interrupt hoặc lan truyền dấu hiệu hủy). Việc bọc vào `UncheckedIOException` không tự giải quyết chính sách cancellation.

Một thiết kế tốt tách:

- **Timeout**: hết ngân sách chờ thao tác.
- **Interruption**: tín hiệu luồng muốn dừng.
- **I/O failure**: thao tác đọc/ghi không thành công.
- **Domain failure**: yêu cầu không đạt điều kiện nghiệp vụ.

Các hiện tượng có thể tương tác, nhưng không được gộp thành một loại thành công/thất bại duy nhất thiếu ngữ cảnh.

## 27. `UncheckedIOException` khác `CompletionException` và `ExecutionException`

Một callback có thể ném `UncheckedIOException`, nhưng khi framework chạy callback **bất đồng bộ**, caller đôi khi nhận thêm một wrapper của framework.

Ví dụ cấu trúc:

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> readUnchecked("some-file"));

String value = future.join();
```

Đây là **mã minh họa**, cần định nghĩa `readUnchecked` và import `CompletableFuture`. Nếu callback ném `UncheckedIOException`:

- `join()` có thể báo lỗi bằng `CompletionException`, với cause là lỗi từ callback theo contract của future.
- `Future.get()` trên một task đã thất bại báo `ExecutionException`.
- Lớp wrapper ngoài **không phải bằng chứng cause gốc đã mất**.
- Bên xử lý cần xét **nhiều tầng cause** nếu chính sách phân loại thất bại nằm ở ranh giới bất đồng bộ.
- Không nên giả định mọi framework dùng cùng một wrapper, thứ tự cause hay cách ghi log.

Không catch `CompletionException` rồi trả giá trị mặc định mà không kiểm tra cause và chính sách phục hồi.

## 28. Ví dụ Java 17: exception được bọc qua `CompletableFuture.join`

Lưu **`AsyncUncheckedIOExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncUncheckedIOExceptionDemo {
    static String read() {
        try {
            throw new IOException("Không đọc được payload");
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Callback I/O thất bại", e);
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> future =
                CompletableFuture.supplyAsync(
                        AsyncUncheckedIOExceptionDemo::read);

        try {
            future.join();
        } catch (CompletionException e) {
            Throwable wrapper = e.getCause();
            System.out.println("Async cause type: "
                    + wrapper.getClass().getSimpleName());

            if (wrapper instanceof UncheckedIOException io) {
                System.out.println("I/O cause: "
                        + io.getCause().getMessage());
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 AsyncUncheckedIOExceptionDemo.java
java AsyncUncheckedIOExceptionDemo
```

**Stdout chính xác** trên Java 17 đối với task có hành vi đã khai báo:

```text
Async cause type: UncheckedIOException
I/O cause: Không đọc được payload
```

Ví dụ không phụ thuộc truy cập file thực hay thời điểm task hoàn tất; `join()` chờ kết quả. Nó minh họa hai tầng wrapping: `CompletionException -> UncheckedIOException -> IOException`.

Trong code production, cần chính sách cancellation, timeout và đóng executor khi tự quản lý executor. Ví dụ dùng common pool mặc định chỉ để minh họa cách quan sát lỗi.

## 29. Catch đúng tầng: không phải chỉ catch `IOException`

Khi một API truyền ra `UncheckedIOException`, handler:

```java
try {
    runPipeline();
} catch (IOException e) {
    handleIoError(e);
}
```

đây là **mã phản ví dụ về kỳ vọng sai** (các hàm phụ chưa định nghĩa). Vì `UncheckedIOException` không extends `IOException`, handler trên **không** bắt wrapper ấy. Ngoài ra, nếu trong `try` không có lời gọi nào được khai báo có thể ném checked `IOException`, Java có thể báo **catch checked IOException không hợp lệ**.

Dạng thích hợp khi code có thể truyền cả hai:

```java
try {
    runOperation();
} catch (UncheckedIOException e) {
    handleIoError(e.getCause());
} catch (IOException e) {
    handleIoError(e);
}
```

Đây là **mã khung minh họa**, `runOperation` cần có chữ ký cho phép checked IOException nếu muốn nhánh thứ hai hợp lệ. Việc bắt cả hai lớp là tùy contract của đường xử lý.

Quan trọng hơn: **không ép tầng nào cũng catch cả hai**. Nếu API công bố một loại nhất quán, hãy xử lý loại đó tại ranh giới có trách nhiệm.

## 30. Không bắt `UncheckedIOException` để trả thành công giả

Một anti-pattern:

```java
try {
    return files.stream().map(uncheckedReader).toList();
} catch (UncheckedIOException ignored) {
    return List.of();
}
```

Đây là **mã khung minh họa**, chưa có biến/hàm đầy đủ. Nếu yêu cầu đọc các file bắt buộc, lỗi đọc file thứ hai không thể biến thành “danh sách đầu ra rỗng” mà caller tin là thành công.

Các lựa chọn tốt hơn:

1. **Fail whole operation** nếu tất cả mục là bắt buộc.
2. **Thu thập kết quả từng phần tử** theo kiểu success/error có cấu trúc nếu hệ thống cho phép partial success.
3. **Retry có giới hạn** ở đúng tầng khi an toàn và nguyên nhân có thể phục hồi.
4. **Fallback** chỉ khi có dữ liệu dự phòng thực sự hợp lệ và contract công bố rõ.
5. **Ghi nhận và báo thất bại** ở tầng giao tiếp thay vì im lặng nuốt.

Đặc biệt với Stream pipeline có side effect, các phần tử trước lỗi có thể đã được xử lý. Việc catch exception không hủy những thay đổi đã xảy ra.

## 31. Retry phải xem thao tác I/O và idempotency

Không phải cứ `UncheckedIOException` là retry ngay. Loại này chỉ nói **một IOException đã được chuyển thành unchecked**, không nói nguyên nhân chắc chắn tạm thời.

Cần xác định:

- Lỗi đến từ đọc file, ghi file, HTTP, socket, storage hay mount từ xa?
- Đã ghi hoặc gửi **một phần** dữ liệu chưa?
- Request phía server có thể đã commit nhưng response bị mất không?
- Thao tác có **idempotent** hay có ID yêu cầu chống thực thi lặp?
- Có tài nguyên cần đóng hoặc trạng thái pipeline không thể tái sử dụng?
- Giới hạn số lần retry, backoff và deadline tổng là gì?
- Lỗi do đường dẫn sai/quyền truy cập/cấu hình, hay do gián đoạn tạm thời?

Ví dụ:

- Đọc một file bất biến có thể retry có kiểm soát nếu hệ thống và dữ liệu cho phép.
- Ghi tiền hoặc tạo đơn hàng qua mạng cần **idempotency key/tra cứu trạng thái** trước khi retry.
- File không có thật do người dùng cung cấp sai đường dẫn cần phản hồi phù hợp, không phải retry vô hạn.
- IOException vì disk full thường cần can thiệp tài nguyên, không khắc phục bằng lặp lại nhanh.

**Wrapper không mã hóa chính sách retry.** Caller không nên suy quá nhiều từ riêng loại `UncheckedIOException`.

## 32. Try-with-resources, primary và suppressed exceptions

Một callback có I/O có thể dùng tài nguyên:

```java
try (Reader reader = openReader()) {
    consume(reader);
} catch (IOException e) {
    throw new UncheckedIOException(
            "Đọc hoặc đóng Reader thất bại", e);
}
```

Đây là **mã minh họa**, cần `openReader()`, `consume`, `Reader` và import tương ứng.

Nếu `consume` ném `IOException`, rồi `reader.close()` cũng ném, try-with-resources có thể gắn lỗi đóng vào **`e.getSuppressed()`** của lỗi chính. Khi bọc trong `UncheckedIOException`, suppressed exceptions **vẫn nằm trên cause** trừ khi bạn chủ động tạo/chuyển quan hệ khác.

Phân biệt:

- `wrapper.getCause()` là IOException đã bị bọc.
- `wrapper.getSuppressed()` là danh sách suppressed gắn **trực tiếp** trên wrapper; có thể rỗng.
- `wrapper.getCause().getSuppressed()` có thể chứa lỗi cleanup từ try-with-resources trước khi wrapping.

Không chuyển mọi suppressed exception thành một lỗi chính mới mà làm mất nguyên nhân ban đầu. Khi ghi log, ưu tiên logger nhận object exception để hiển thị toàn bộ cause/suppressed/stack trace nếu được hỗ trợ.

## 33. Ví dụ Java 17: kiểm tra suppressed exception trên cause

Lưu **`SuppressedIoWrapperDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;

public class SuppressedIoWrapperDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("Lỗi đóng tài nguyên");
        }
    }

    static void perform() {
        try (Resource resource = new Resource()) {
            throw new IOException("Lỗi xử lý chính");
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Xử lý tài nguyên thất bại", e);
        }
    }

    public static void main(String[] args) {
        try {
            perform();
        } catch (UncheckedIOException e) {
            System.out.println("Cause: "
                    + e.getCause().getMessage());
            System.out.println("Suppressed on cause: "
                    + e.getCause().getSuppressed().length);
            System.out.println("Suppressed message: "
                    + e.getCause().getSuppressed()[0].getMessage());
            System.out.println("Suppressed on wrapper: "
                    + e.getSuppressed().length);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 SuppressedIoWrapperDemo.java
java SuppressedIoWrapperDemo
```

**Stdout chính xác:**

```text
Cause: Lỗi xử lý chính
Suppressed on cause: 1
Suppressed message: Lỗi đóng tài nguyên
Suppressed on wrapper: 0
```

Điểm mấu chốt: **giữ cause** giúp giữ lại cả danh sách suppressed có trên exception gốc. Nhưng suppressed không tự “di chuyển” sang wrapper, vì hai object khác nhau.

Mẫu này dùng `AutoCloseable` tùy chỉnh chỉ để chứng minh cấu trúc exception, không phụ thuộc filesystem hay networking.

## 34. Không bọc lỗi đã là unchecked lần nữa nếu không có giá trị

Nếu `Function.apply` bên trong ném `UncheckedIOException`, một adapter chỉ bắt `IOException` sẽ **không bắt lại** wrapper ấy:

```java
try {
    return function.apply(value);
} catch (IOException e) {
    throw new UncheckedIOException(e);
}
```

Đây là **mã khung**, với `function.apply` khai báo checked IOException. Một `UncheckedIOException` thoát từ bên trong `function.apply` sẽ đi xuyên qua handler `catch (IOException)` mà không bị bọc thêm, vì nó là unchecked sibling branch.

Nếu bắt rộng `catch (Exception e)` rồi `new RuntimeException(e)`, bạn có thể tạo chuỗi wrapper lồng nhau vô ích và vô tình bắt cả lỗi lập trình (`NullPointerException`, `IllegalStateException`). Nên giới hạn catch **đúng checked IOException** mà adapter cần chuyển loại.

Đây cũng là lý do đặt các handler cụ thể ở ranh giới phù hợp: tránh mất thông tin và tránh bọc lặp làm khó phân tích stack trace.

## 35. Method reference vẫn bị ràng buộc bởi `throws`

Một method reference tới `Files.readString` **không** tương thích trực tiếp với `Function<Path,String>`. Chuyển cú pháp:

```java
Function<Path, String> direct = Files::readString;
```

là **phản ví dụ không biên dịch**. Không có conversion tự động chỉ vì dùng `::`.

Ngược lại:

```java
IoFunction<Path, String> checked = Files::readString;
Function<Path, String> adapted = unchecked(checked);
```

đây là **đoạn minh họa** giả định `IoFunction` và adapter `unchecked` như đã định nghĩa trước. Method reference hợp lệ ở bước thứ nhất vì target SAM có `throws IOException`; bước thứ hai đổi hợp đồng sang `Function` một cách có chủ đích.

Nếu một người viết thêm `throws IOException` trên method chứa dòng `Function<Path,String> direct = Files::readString;`, compiler vẫn từ chối bởi SAM `Function.apply` không thay đổi.

## 36. Có thể chuyển lỗi thành kết quả thay vì exception

Không phải mọi pipeline có I/O đều nên dừng toàn bộ khi một phần tử thất bại. Với tác vụ xử lý danh sách file, đôi khi yêu cầu là **giữ cả thành công lẫn lỗi từng file**.

Có thể mô hình hóa bằng record hoặc sealed hierarchy, chẳng hạn:

```java
sealed interface ReadResult permits ReadSuccess, ReadFailure {
}

record ReadSuccess(String file, String content)
        implements ReadResult {
}

record ReadFailure(String file, String reason)
        implements ReadResult {
}
```

Đây là **các kiểu Java 17 minh họa**, không có `main`. Method đọc có thể bắt `IOException` và trả `ReadFailure` thay vì ném wrapper, khi điều đó là **nhánh nghiệp vụ được chấp nhận**.

Ưu điểm:

- Pipeline có thể hoàn tất và thu thập lỗi **mỗi phần tử**.
- Caller không cần catch một exception chung để biết file nào thất bại.
- Có thể báo cáo partial success minh bạch.
- Kết quả có cấu trúc không phụ thuộc message exception làm mã phân loại.

Nhược điểm: code phải xử lý nhiều dạng kết quả; nếu toàn bộ thao tác phải thất bại ngay khi một file bắt buộc không đọc được, wrapper vẫn có thể đơn giản và đúng hơn.

**Chọn theo ngữ nghĩa tác vụ**, không theo mong muốn giữ pipeline “đẹp” bằng mọi giá.

## 37. So sánh bốn cách biểu diễn lỗi I/O

| Cách | Hợp đồng Java | Khi nào phù hợp | Rủi ro |
| --- | --- | --- | --- |
| `throws IOException` | Checked, caller catch/declare | API sở hữu cho phép checked I/O | Có thể khó dùng với `Function`/`Consumer` chuẩn |
| `UncheckedIOException` | Unchecked nhưng cause phải là IOException | Callback không cho checked `throws`, cần truyền lỗi I/O rõ | Caller có thể bỏ qua nếu không biết hợp đồng |
| Custom domain exception | Checked hoặc unchecked theo superclass chọn | Muốn báo lỗi theo nghiệp vụ/tầng trừu tượng | Dễ bọc lặp hoặc làm mất cause nếu thiết kế kém |
| Result type (`Success/Failure`) | Dữ liệu trả về có cấu trúc | Lỗi là nhánh dự kiến, cần partial success | Caller phải kiểm tra/định tuyến trạng thái kết quả |

Một số quyết định thực hành:

- API thư viện công bố dữ liệu từ file và muốn caller tự fallback → có thể giữ checked `IOException`.
- Mapper trong stream hiện có hợp đồng `Function` → dùng adapter `UncheckedIOException` nếu fail-fast hợp lý.
- Batch xử lý mọi file dù có file lỗi → kiểu `ReadResult` có thể phù hợp.
- API domain không muốn lộ chi tiết filesystem → custom domain exception có `cause` rõ ràng.

Không có cách duy nhất tốt nhất cho mọi dự án.

## 38. Kiểm thử `UncheckedIOException` đúng cách

Một bài test nên xác minh không chỉ “có exception” mà còn:

1. **Wrapper type đúng:** `UncheckedIOException`.
2. **Cause đúng object hoặc đúng subtype IOException:** không làm mất exception gốc.
3. **Message/context phù hợp:** không lộ thông tin nhạy cảm, đủ để chẩn đoán.
4. **Lỗi không bị nuốt:** tác vụ thất bại theo chính sách.
5. **Stream lazy:** ngoại lệ xảy ra khi callback thật sự chạy, không phải mặc định lúc tạo pipeline.
6. **Kết quả từng phần/side effect:** không giả định rollback.
7. **Nguồn tài nguyên được đóng** dù callback ném lỗi.
8. **Không retry vô hạn** hoặc thực thi trùng với thao tác có side effect.
9. **Các loại runtime khác không bị bọc sai**: ví dụ `IllegalArgumentException` từ validation không nên biến thành I/O.
10. **Ranh giới bất đồng bộ giữ được cause chain** nếu chạy trong future/executor.

Nên dùng test nhân tạo ném `IOException` để kiểm thử adapter. Test trực tiếp quyền file hay mạng có thể flaky; integration test riêng kiểm tra tương tác thực và tài nguyên.

## 39. Ví dụ Java 17: tự kiểm tra giữ object cause và runtime exception khác

Lưu **`UncheckedIOExceptionAssertionsDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;

public class UncheckedIOExceptionAssertionsDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T input) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(
            IoFunction<T, R> fn) {
        return value -> {
            try {
                return fn.apply(value);
            } catch (IOException e) {
                throw new UncheckedIOException("I/O failed", e);
            }
        };
    }

    public static void main(String[] args) {
        IOException source = new IOException("root");
        Function<String, String> failIo =
                unchecked(value -> { throw source; });

        try {
            failIo.apply("x");
            throw new AssertionError("Thiếu wrapper");
        } catch (UncheckedIOException e) {
            if (e.getCause() != source) {
                throw new AssertionError("Cause không còn cùng object");
            }
            System.out.println("PASS same cause");
        }

        Function<String, String> failValidation =
                unchecked(value -> {
                    throw new IllegalArgumentException("bad argument");
                });

        try {
            failValidation.apply("x");
            throw new AssertionError("Thiếu validation error");
        } catch (IllegalArgumentException e) {
            System.out.println("PASS runtime unchanged");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 UncheckedIOExceptionAssertionsDemo.java
java UncheckedIOExceptionAssertionsDemo
```

**Stdout chính xác:**

```text
PASS same cause
PASS runtime unchanged
```

Chương trình chứng minh:

- Adapter giữ chính object `IOException` gốc trong `getCause()`.
- Handler chỉ bắt `IOException` nên **không biến `IllegalArgumentException` thành lỗi I/O**.
- Test dùng `AssertionError` để thất bại chủ động; không phụ thuộc cờ `-ea`.

Đây là hai kiểm tra quan trọng nếu bạn định đóng gói adapter thành tiện ích dùng chung.

## 40. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`UncheckedIOException` là subclass `IOException`.” | Sai. Nó là subclass `RuntimeException` và chứa `IOException` làm cause. |
| “Đã có `UncheckedIOException` thì mọi `Files.readString` đều unchecked.” | Sai. `Files.readString` vẫn công bố checked `IOException`. |
| “`Function.apply` tự hiểu và chuyển IOException.” | Không. Callback phải bắt/chuyển hoặc dùng hợp đồng khác. |
| “Bọc code tạo Stream trong catch IOException sẽ sửa method reference không tương thích.” | Không. Checked exception nằm trong SAM; phải đổi callback. |
| “`UncheckedIOException` đã xử lý được lỗi.” | Sai. Nó chỉ đổi hình thức lan truyền exception. |
| “`catch (IOException)` bắt luôn `UncheckedIOException`.” | Không; hai loại ở hai nhánh khác nhau. |
| “`UncheckedIOException` nhận cause là SQLException.” | Không. Constructor chuyên biệt cần IOException. |
| “Mọi lỗi I/O đều có thể retry an toàn.” | Không. Có thể đã có side effect hoặc lỗi cấu hình vĩnh viễn. |
| “Viết `throws IOException` ở method chứa lambda làm Function.apply cho checked IOException.” | Sai. SAM của Function không thay đổi. |
| “`Files.lines` chỉ có unchecked lỗi.” | Sai. Lúc mở stream có thể ném checked IOException; lúc xử lý lazy có thể có UncheckedIOException. |
| “Stream pipeline chạy toàn bộ mapper ngay lúc được tạo.” | Không. Các intermediate operations thường lazy. |
| “Dữ liệu đã ghi trước lỗi sẽ được Stream rollback.” | Không. Stream không cung cấp transaction/rollback cho side effect. |
| “Sau `UncheckedIOException` có thể an toàn tiếp tục dùng mọi resource.” | Không thể suy vậy; phải xem giao thức và trạng thái tài nguyên. |
| “Bắt `Exception` rồi bọc thành RuntimeException là tương đương.” | Nó có thể bắt cả lỗi lập trình, làm mất ngữ nghĩa I/O và tạo wrapper dư thừa. |
| “`getCause()` của UncheckedIOException chỉ là Throwable chung.” | Java khai báo override trả `IOException`. |
| “Mọi wrapper đều tự mang suppressed của cause lên chính wrapper.” | Không. Suppressed thuộc từng Throwable object, cần kiểm tra đúng tầng. |
| “Vì `SocketTimeoutException extends InterruptedIOException` nên phải đặt interrupt flag.” | Không chỉ vì timeout; cần biết contract cancellation thật. |
| “`join()` trả trực tiếp UncheckedIOException trong mọi Future.” | Không. CompletableFuture có thể báo `CompletionException` với cause tương ứng. |
| “Nếu dùng `UncheckedIOException` thì không cần JavaDoc.” | Sai. Caller vẫn cần biết hợp đồng, thời điểm lỗi và chính sách phục hồi. |
| “Mọi nhánh không tìm thấy dữ liệu đều nên ném UncheckedIOException.” | Không. Thiếu dữ liệu nghiệp vụ có thể không phải lỗi I/O. |

## 41. Câu hỏi tự kiểm tra

**1. `UncheckedIOException` là checked hay unchecked?**  
Unchecked, vì kế thừa `RuntimeException`.

**2. `UncheckedIOException extends IOException` có đúng không?**  
Không. Nó chứa một `IOException` làm `cause`.

**3. Vì sao `Function<Path,String> f = Files::readString` không biên dịch?**  
`Files.readString` khai báo checked `IOException` nhưng `Function.apply` không cho checked `throws`.

**4. Bọc lambda bằng `try/catch(IOException)` rồi ném `UncheckedIOException` làm thay đổi điều gì?**  
Checked IOException không còn thoát khỏi SAM; thay vào đó là unchecked wrapper khi I/O thất bại.

**5. `UncheckedIOException.getCause()` có kiểu trả về tĩnh là gì?**  
`IOException`.

**6. Có thể truyền `SQLException` trực tiếp cho constructor `UncheckedIOException` không?**  
Không, vì `SQLException` không là `IOException`.

**7. API nào nên cân nhắc nếu muốn callback **giữ checked IOException**?**  
Custom SAM có `throws IOException`, hoặc một API có sẵn cho phép checked exception như `Callable.call`.

**8. Có phải `Stream.map` luôn thực thi ngay khi viết `stream.map(fn)`?**  
Không. Intermediate operations thường lazy.

**9. `Files.lines` có thể ném loại lỗi nào khi mở file?**  
Checked `IOException`.

**10. Trong lúc tiêu thụ lazy Stream từ `Files.lines`, lỗi đọc I/O có thể xuất hiện dưới loại nào?**  
`UncheckedIOException`.

**11. Khi xử lý `BufferedReader.readLine()` trực tiếp, Java có tự bọc thành `UncheckedIOException` không?**  
Không. `readLine` trực tiếp khai báo checked `IOException`.

**12. Vì sao phải đóng stream từ `Files.lines`?**  
Nó có thể nắm tài nguyên file; dùng try-with-resources theo contract.

**13. Nếu stream đã xử lý ba phần tử và phần tử thứ tư ném wrapper, các side effect trước có tự rollback không?**  
Không.

**14. Vì sao không retry một lệnh tạo giao dịch chỉ dựa trên loại `UncheckedIOException`?**  
Vì lệnh có thể đã thực thi phía server hoặc đã ghi một phần; cần idempotency, kiểm tra trạng thái và chính sách retry.

**15. Trong `CompletableFuture.join()`, wrapper nào có thể bao ngoài lỗi từ callback?**  
`CompletionException`.

**16. Có cần giữ object IOException gốc ở cause khi chuyển lỗi?**  
Có, để giữ loại lỗi, message, stack trace và dữ liệu suppressed của cause.

**17. Sau khi wrap lỗi chính đã có suppressed, nên tra chúng ở đâu?**  
Thường ở `wrapped.getCause().getSuppressed()`, vì suppressed không tự chuyển lên wrapper.

**18. Nếu lambda ném `IllegalArgumentException`, adapter chỉ catch `IOException` có đổi nó thành `UncheckedIOException` không?**  
Không, vì `IllegalArgumentException` không thuộc `IOException`.

**19. Dùng `UncheckedIOException` có tự tạo deadline hoặc timeout cho đọc file không?**  
Không. Nó không liên quan thiết lập deadline.

**20. Nếu một phần tử không tồn tại theo nghiệp vụ, có bắt buộc dùng `UncheckedIOException` không?**  
Không. Nó chỉ phù hợp khi có lỗi I/O thực và hợp đồng muốn truyền unchecked.

**21. Có thể chọn `ReadResult` success/failure thay vì exception trong batch không?**  
Có, khi cần giữ kết quả từng phần tử hoặc thất bại là nhánh dự kiến.

**22. `Callable.call() throws Exception` có thể tham chiếu method `throws IOException` không?**  
Có, vì `IOException extends Exception`.

**23. `UncheckedIOException` được tạo bằng constructor nào để bổ sung context?**  
`new UncheckedIOException("Mô tả", ioException)`.

**24. Vì sao không nên catch rộng RuntimeException rồi coi mọi lỗi là “I/O”?**  
Vì đó có thể là lỗi đối số, trạng thái, NPE hoặc bug khác.

## 42. Checklist khi review code sử dụng `UncheckedIOException`

Trước khi đưa vào production:

1. **Xác nhận lỗi gốc thật sự là IOException**, không phải lỗi nghiệp vụ hay checked exception khác.
2. **Xác định SAM/API đang giới hạn checked throws**: Function, Consumer, Supplier, Runnable, Stream?
3. **Có thể thay bằng custom SAM có `throws IOException` không?** Nếu sở hữu API, cân nhắc lựa chọn checked.
4. **Có cần fail-fast hay giữ partial results?** Cân nhắc result type nếu cần.
5. **Bắt đúng phạm vi IOException**, không bắt `Exception` rồi gán nhầm ngữ nghĩa.
6. **Dùng constructor giữ cause**: `new UncheckedIOException(message, e)`.
7. **Message bổ sung ngữ cảnh có ích** mà không lộ dữ liệu nhạy cảm.
8. **Biết exception xảy ra ở đâu**: lúc tạo nguồn, tạo pipeline hay terminal operation?
9. **Bắt wrapper tại đúng ranh giới**; `catch(IOException)` không bắt được wrapper.
10. **Nếu dùng Files.lines/list/walk**, có quản lý stream/resource bằng try-with-resources không?
11. **Nếu dùng BufferedReader.lines**, ai sở hữu và đóng Reader?
12. **Nếu callback có side effect**, đã xét dữ liệu ghi một phần và rollback chưa?
13. **Không retry mù quáng** chỉ vì lỗi mang từ “I/O”.
14. **Đối với request có side effect**, có idempotency key hoặc trạng thái xác nhận chưa?
15. **Nếu chạy bất đồng bộ**, có xử lý wrapper của Future/CompletableFuture đúng hợp đồng không?
16. **Có log Throwable cùng cause/suppressed**, thay vì chỉ lưu message không?
17. **Có test cause giữ nguyên object**, subtype đúng và runtime exception khác không bị bắt nhầm không?
18. **Có test đúng thời điểm xảy ra lỗi lazy stream không?**
19. **Có tài nguyên chưa đóng sau exception không?** Kiểm tra try-with-resources và cleanup.
20. **Có nguy cơ ném wrapper lồng nhiều tầng không cần thiết không?**
21. **Có chính sách cancellation/interrupt riêng** với timeout I/O không?
22. **Đã tài liệu hóa unchecked exception** trong API/adapter chưa?
23. **Đã tránh biến thất bại thành danh sách rỗng hoặc thành công giả chưa?**
24. **Nếu đổi hợp đồng public API từ checked sang unchecked**, đã xét caller/catch/tests và tương thích chưa?

## 43. Kết luận

`UncheckedIOException` là **cầu nối giữa checked `IOException` và những API Java không cho callback ném checked exception**. Nó là subclass của `RuntimeException`, giữ nguyên nhân kiểu `IOException` ở `getCause()`, và đặc biệt hữu ích với lambda, method reference adapter, `Function`, `Consumer`, Stream API hoặc các API đọc dữ liệu lazily như `Files.lines` và `BufferedReader.lines`.

Điều cần phân biệt là **truyền lỗi** và **xử lý lỗi**. Bọc `IOException` bằng `UncheckedIOException` giúp mã đi qua một chữ ký callback không có checked `throws`; nó **không phục hồi I/O, không tạo retry an toàn, không đóng tài nguyên thay bạn và không rollback side effect**. Lỗi vẫn phải được báo hoặc xử lý ở tầng có trách nhiệm.

Khi API của bạn có thể công bố checked `IOException` và caller cần quyền xử lý tường minh, giữ checked exception hoặc dùng custom SAM có `throws IOException` có thể tốt hơn. Nếu một thất bại là nhánh nghiệp vụ dự kiến hoặc cần partial success, kiểu kết quả có trạng thái có thể phù hợp hơn. Chỉ chuyển sang unchecked **có chủ đích, giữ cause, chọn ranh giới bắt hợp lý và kiểm thử chính sách thất bại**.
