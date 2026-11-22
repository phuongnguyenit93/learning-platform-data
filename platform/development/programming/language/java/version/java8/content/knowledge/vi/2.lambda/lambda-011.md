# Ngoại lệ checked trong hợp đồng hàm đích của Lambda — Java

Khi viết lambda trong Java, **kiểu functional interface đích** quyết định không chỉ danh sách tham số và kiểu kết quả, mà còn **những checked exception được phép thoát ra khỏi thân lambda**. Đây là quy tắc đang áp dụng trong Java hiện đại: nếu thân lambda có thể phát sinh một checked exception chưa được xử lý, loại ngoại lệ đó phải phù hợp với mệnh đề `throws` của phương thức trừu tượng trong giao diện hàm đích.

Ví dụ, `java.util.function.Function<T,R>` không khai báo checked exception ở `apply`, nên lambda dùng làm `Function` không thể trực tiếp phát sinh `IOException` chưa xử lý. Ngược lại, `Callable<V>` khai báo `call() throws Exception`, nên một lambda tương thích với `Callable` có thể chuyển một `IOException` tới nơi gọi `call()`.

Bài này tập trung vào **hợp đồng ngoại lệ của functional interface đích**, cách compiler kiểm tra thân lambda, cách xử lý đúng tại ranh giới API và những lỗi dễ gặp khi ghép lambda với Stream, callback hoặc tác vụ có I/O.

## 1. Ôn lại: checked exception và unchecked exception

Java phân biệt ngoại lệ theo kiểu kế thừa:

- **Checked exception:** những lớp con của `Throwable` không thuộc `RuntimeException` hoặc `Error`, ví dụ `IOException`, `SQLException`, `ClassNotFoundException`, `InterruptedException`. Trình biên dịch buộc mã phải bắt ngoại lệ hoặc để ngoại lệ lan truyền theo hợp đồng `throws` phù hợp.
- **Unchecked exception:** `RuntimeException` và các lớp con (như `IllegalArgumentException`, `UncheckedIOException`, `NullPointerException`), cùng `Error` và các lớp con. Java không yêu cầu khai báo chúng trong `throws`.
- **Không đồng nhất “checked” với “có thể xảy ra”:** checked exception là quy tắc **kiểm tra ở lúc biên dịch** dựa trên kiểu và hợp đồng phương thức; còn mọi lời gọi vẫn có thể gặp lỗi trong thời gian chạy.

Ví dụ phương thức có thể ném checked exception:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String load(Path path) throws IOException {
    return Files.readString(path);
}
```

Đây là **đoạn minh họa trong một lớp**, không phải chương trình Java độc lập. `Files.readString` có mặt từ Java 11, vẫn là API được sử dụng trong Java hiện đại. Với mã bắt buộc tương thích mức nguồn Java 8, có thể dùng API hiện hành có từ Java 8 như `Files.readAllBytes(path)` và giải mã bằng `new String(bytes, StandardCharsets.UTF_8)`. Dù dùng cách nào, điều cần học ở đây là **`load` khai báo `throws IOException`**.

Một lời gọi `load(path)` phải được compiler kiểm tra ngoại lệ theo ngữ cảnh, kể cả khi lời gọi xuất hiện trong thân lambda.

## 2. Functional interface đích là hợp đồng cho lambda

Functional interface có một phương thức trừu tượng duy nhất (*single abstract method* — SAM). Với lambda, **kiểu đích** là giao diện này, và mệnh đề `throws` của SAM xác định những checked exception có thể được thân lambda chuyển ra ngoài.

So sánh:

```java
@FunctionalInterface
interface TextReader {
    String read(String source) throws java.io.IOException;
}

@FunctionalInterface
interface TextMapper {
    String map(String source);
}
```

Cả hai SAM đều nhận một `String` và trả về `String`. Khác biệt quyết định là:

- `TextReader.read` khai báo `throws IOException`.
- `TextMapper.map` không khai báo checked exception.

Giả sử đã có phương thức `static String readText(String input) throws IOException` trong cùng lớp:

```java
TextReader allowed = input -> readText(input);

// KHÔNG BIÊN DỊCH: checked IOException không thuộc
// throws của TextMapper.map.
// TextMapper denied = input -> readText(input);
```

Dòng chú thích lỗi là ví dụ cố ý không biên dịch, **không chép vào chương trình chạy đầy đủ**. Thân lambda có cùng hành vi, nhưng compiler quyết định khác nhau vì **target SAM khác nhau**.

### 2.1. Luật kiểm tra checked exception

Đối với mỗi checked exception mà thân lambda **có thể ném ra ngoài** theo phân tích của trình biên dịch, ngoại lệ đó phải là kiểu được phép bởi mệnh đề `throws` của SAM đích. Cụ thể, checked exception phát sinh phải tương thích với ít nhất một kiểu ngoại lệ khai báo trong `throws` của hàm đích. Nếu không, Java báo lỗi biên dịch.

Ví dụ:

| Hợp đồng của SAM | Thân lambda phát sinh | Kết quả |
| --- | --- | --- |
| `void run()` | `IOException` chưa bắt | Không hợp lệ |
| `String read() throws IOException` | `FileNotFoundException` | Hợp lệ: `FileNotFoundException` là lớp con của `IOException` |
| `String read() throws IOException` | `SQLException` chưa bắt | Không hợp lệ: không là lớp con của `IOException` |
| `String call() throws Exception` | `IOException` | Hợp lệ: `IOException` là lớp con của `Exception` |
| `String get()` | `IllegalArgumentException` | Hợp lệ theo kiểm tra checked exception: đây là unchecked exception |
| `String get()` | `IOException` được bắt trong lambda | Hợp lệ nếu mọi checked exception còn lại được xử lý hợp lệ |

Không phải cứ thêm `throws IOException` vào phương thức **bao quanh biểu thức lambda** là đủ. Sự tương thích được xác định bằng **SAM đích**, không lấy từ mệnh đề `throws` của phương thức chứa lệnh tạo lambda.

### 2.2. “Tạo lambda” khác “gọi lambda”

```java
TextReader reader = input -> readText(input);
```

Phép gán chỉ tạo ra một đối tượng thực hiện hợp đồng `TextReader`, không ngay lập tức gọi `readText`. Khi người dùng gọi `reader.read("...")`, checked exception mới có thể lan tới người gọi.

Vì `reader.read` khai báo `throws IOException`, người gọi phải xử lý:

```java
try {
    String result = reader.read("...");
    System.out.println(result);
} catch (java.io.IOException e) {
    System.err.println("Không đọc được: " + e.getMessage());
}
```

Các đoạn trong mục này minh họa cú pháp và giả định `reader`, `readText` đã được khai báo phù hợp. Chương trình độc lập hoàn chỉnh ở mục 6.

## 3. Khác biệt giữa các functional interface chuẩn

### 3.1. `Function`, `Supplier`, `Consumer`, `Predicate` và `Runnable`

Những giao diện phổ biến này **không khai báo checked exception** ở phương thức trừu tượng chính:

```java
// Chữ ký cốt lõi, rút gọn để minh họa:
R Function<T, R>.apply(T value);
T Supplier<T>.get();
void Consumer<T>.accept(T value);
boolean Predicate<T>.test(T value);
void Runnable.run();
```

Đây là **các chữ ký mô tả**, không phải cú pháp khai báo Java chạy độc lập.

Hệ quả:

```java
// Giả sử load(path) khai báo throws IOException.

// SAI: Function.apply không khai báo IOException.
// Function<Path, String> f = path -> load(path);

// SAI: Supplier.get cũng không khai báo IOException.
// Supplier<String> s = () -> load(Path.of("notes.txt"));
```

Ngay cả khi method bao ngoài có `throws IOException`, hai lambda trên vẫn không hợp lệ vì **hợp đồng phương thức đích không cho phép ngoại lệ checked đó thoát ra**.

### 3.2. `Callable<V>` cho phép checked exception

`java.util.concurrent.Callable<V>` có chữ ký:

```java
V call() throws Exception;
```

Do đó:

```java
Callable<String> task = () -> load(Path.of("notes.txt"));
```

Lambda hợp lệ nếu `load` có thể ném `IOException`. **Người gọi `task.call()` phải xử lý `Exception`** theo hợp đồng của `Callable.call`, kể cả khi implementation cụ thể chỉ ném `IOException`.

Lưu ý: `Callable` là một lựa chọn có ý nghĩa khi API **thực sự nhận Callable**. Không thể tùy ý đưa `Callable` vào chỗ Stream API đang yêu cầu `Function`. Hai giao diện có chữ ký và hợp đồng riêng, không thay thế được nhau chỉ vì chúng đều chấp nhận lambda.

### 3.3. Giao diện tự định nghĩa có `throws` cụ thể

Khi bạn **kiểm soát API nhận callback**, có thể định nghĩa hợp đồng khớp với ngoại lệ thật:

```java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T input) throws java.io.IOException;
}
```

`IOFunction` biểu diễn một hàm biến đổi có thể lỗi I/O. Điều này làm trách nhiệm xử lý lỗi rõ ràng hơn so với việc ném chung `Exception` ở mọi nơi:

```java
IOFunction<Path, String> readFile = path -> Files.readString(path);
```

Ở đây `Files.readString` cần Java 11+. Mục tiêu của ví dụ là chứng minh quy tắc `throws IOException`; với Java 8 hãy thay bằng API đọc file phù hợp. Nếu nhiều loại checked exception độc lập thật sự có thể xảy ra, cân nhắc khai báo từng loại hoặc thiết kế abstraction lỗi thích hợp; đừng mở rộng tất cả thành `Exception` nếu không có nhu cầu.

## 4. Bốn cách xử lý checked exception tại ranh giới lambda

### Cách 1 — Bắt và xử lý ngay bên trong lambda

Phù hợp khi lambda **có thể giải quyết lỗi một cách có ý nghĩa**, chẳng hạn ghi log rồi bỏ qua một tác vụ không quan trọng, hoặc chuyển lỗi thành một kết quả rõ ràng đã được thiết kế:

```java
Consumer<Path> reader = path -> {
    try {
        String text = Files.readString(path);
        System.out.println(text);
    } catch (IOException e) {
        System.err.println("Không đọc được " + path + ": " + e.getMessage());
    }
};
```

Ở đây `Consumer.accept` không khai báo checked exception, nhưng body đã bắt `IOException` nên không còn checked exception đó thoát ra. Đoạn mã minh họa cần các import tương ứng và Java 11+ cho `Files.readString`.

**Cẩn trọng:** chỉ ghi log rồi tiếp tục là quyết định nghiệp vụ. Với thao tác quan trọng như nạp cấu hình, xử lý giao dịch hay dữ liệu bắt buộc, nuốt lỗi có thể tạo ra trạng thái sai. Khi không thể phục hồi, nên chuyển lỗi đến ranh giới gọi phù hợp.

### Cách 2 — Chuyển sang unchecked exception có giữ nguyên nguyên nhân

Khi API không khai báo checked exception và **không có cách phục hồi hợp lý ngay trong lambda**, có thể bọc ngoại lệ:

```java
Function<Path, String> readFile = path -> {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        throw new UncheckedIOException("Không đọc được " + path, e);
    }
};
```

`UncheckedIOException` là kiểu có sẵn trong `java.io` dành cho trường hợp bọc `IOException`, giữ ngoại lệ gốc tại `getCause()`. Caller cần biết API này có thể phát sinh unchecked exception để xử lý ở tầng phù hợp. Ví dụ này dùng Java 11+ cho `Files.readString`.

Với checked exception không phải I/O, có thể chọn loại runtime exception có ý nghĩa trong thiết kế ứng dụng và truyền ngoại lệ gốc làm `cause`. Không bọc mọi lỗi một cách máy móc chỉ để ép code biên dịch.

### Cách 3 — Thiết kế callback có khai báo `throws` rõ ràng

Nếu API do bạn thiết kế có thể làm việc I/O, cho phép callback biểu đạt checked exception:

```java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T input) throws IOException;
}

static <T, R> R execute(IOFunction<T, R> callback, T input)
        throws IOException {
    return callback.apply(input);
}
```

Đây là đoạn khai báo minh họa cần import `java.io.IOException`. Lời gọi `execute` cũng phải tuân theo `throws IOException`. Giữ hợp đồng này xuyên suốt các tầng khi việc để caller xử lý checked exception là chủ đích thiết kế.

Với nhiều loại ngoại lệ và khi cần một interface tổng quát, có thể định nghĩa:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}
```

Tuy nhiên, đây là **interface tự định nghĩa**, không phải kiểu có sẵn trong `java.util.function`. Nó cũng **không tự động tương thích** với các API nhận `Function<T,R>`.

### Cách 4 — Chọn API có hợp đồng phù hợp nếu bài toán cho phép

Nếu mục đích là một tác vụ có kết quả được thực thi qua một API hỗ trợ `Callable`, lựa chọn `Callable<V>` thể hiện được `throws Exception`:

```java
Callable<String> task = () -> Files.readString(Path.of("notes.txt"));
```

Chỉ dùng cách này khi caller hoặc framework thực sự nhận `Callable` và có chiến lược xử lý kết quả/lỗi. Ví dụ, đưa `Callable` vào executor sẽ có cách báo lỗi qua kết quả tác vụ của executor, khác với việc gọi `call()` trực tiếp; không nên giả định mọi ngoại lệ tự động xuất hiện ở thread gọi phương thức gửi tác vụ.

## 5. Ví dụ đặc biệt: Stream API và method reference

### 5.1. `Stream.map` nhận `Function`

`map` nhận `Function<? super T, ? extends R>`. Vì `Function.apply` không khai báo checked exception, một lambda như sau không biên dịch nếu `readContent` khai báo `throws IOException`:

```java
// KHÔNG BIÊN DỊCH nếu readContent(path) throws IOException:
// List<String> values = paths.stream()
//         .map(path -> readContent(path))
//         .toList();
```

Cách xử lý khi cần đưa lỗi ra ngoài dưới dạng unchecked exception:

```java
List<String> values = paths.stream()
        .map(path -> {
            try {
                return readContent(path);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        })
        .toList();
```

Đoạn minh họa này dùng Java 16+ cho `Stream.toList()`, và giả định `paths` là `List<Path>` cùng `readContent(Path) throws IOException`; không phải chương trình độc lập. Nếu cần tương thích Java 8, có thể kết thúc bằng `.collect(Collectors.toList())`. Logic xử lý checked exception không thay đổi theo cách thu thập danh sách.

**Lưu ý nghiệp vụ:** Stream có đặc tính *lazy* đối với thao tác trung gian như `map`. Ngoại lệ phát sinh khi pipeline được thực thi bởi thao tác kết thúc, không nhất thiết khi biểu thức `map(...)` mới được xây dựng.

### 5.2. Method reference tuân thủ cùng hợp đồng

Hai cách sau đều có thể hợp lệ:

```java
IOFunction<Path, String> first = path -> Files.readString(path);
IOFunction<Path, String> second = Files::readString;
```

Tương ứng, khi kiểu đích là `Function<Path,String>`, cả hai cách đều có vấn đề với checked `IOException` chưa được xử lý:

```java
// KHÔNG BIÊN DỊCH:
// Function<Path, String> a = path -> Files.readString(path);
// Function<Path, String> b = Files::readString;
```

Method reference là cách viết ngắn gọn hơn trong trường hợp phù hợp chữ ký; nó **không** bỏ qua quy tắc checked exception của target SAM.

## 6. Chương trình Java hoàn chỉnh: ba kiểu hợp đồng và cách caller xử lý

Chương trình sau dùng API có từ Java 8, có thể biên dịch/chạy trên **JDK 17+** và cũng tương thích Java 8. `BufferedReader.readLine()` khai báo `throws IOException`; hàm `firstLine` minh họa một đường phát sinh checked exception có kiểm soát để stdout luôn xác định.

Tạo tệp **`CheckedLambdaDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.io.UncheckedIOException;
import java.util.concurrent.Callable;
import java.util.function.Function;

public class CheckedLambdaDemo {

    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T input) throws IOException;
    }

    private static String firstLine(String input) throws IOException {
        if ("FAIL".equals(input)) {
            throw new IOException("Lỗi minh họa");
        }

        try (BufferedReader reader =
                     new BufferedReader(new StringReader(input))) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) {
        // Hợp đồng tùy chỉnh cho phép IOException thoát ra ngoài.
        IOFunction<String, String> reader =
                CheckedLambdaDemo::firstLine;

        try {
            System.out.println("IOFunction: "
                    + reader.apply("Java\nLambda"));
        } catch (IOException e) {
            System.out.println("IOException: " + e.getMessage());
        }

        // Function không khai báo checked exception:
        // bắt IOException bên trong rồi bọc thành unchecked.
        Function<String, String> adapted = input -> {
            try {
                return firstLine(input);
            } catch (IOException e) {
                throw new UncheckedIOException("Không đọc được", e);
            }
        };

        System.out.println("Function: "
                + adapted.apply("Lambda\nJava"));

        try {
            adapted.apply("FAIL");
        } catch (UncheckedIOException e) {
            System.out.println("UncheckedIOException: "
                    + e.getCause().getMessage());
        }

        // Callable.call cho phép throws Exception.
        Callable<String> task = () -> firstLine("Callable\nOK");

        try {
            System.out.println("Callable: " + task.call());
        } catch (Exception e) {
            System.out.println("Callable thất bại: " + e.getMessage());
        }

        // Checked exception từ IOFunction được xử lý khi gọi.
        try {
            reader.apply("FAIL");
        } catch (IOException e) {
            System.out.println("IOException: " + e.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CheckedLambdaDemo.java
java CheckedLambdaDemo
```

**Stdout chính xác** khi chương trình hoạt động bình thường:

```text
IOFunction: Java
Function: Lambda
UncheckedIOException: Lỗi minh họa
Callable: Callable
IOException: Lỗi minh họa
```

Giải thích từng bước:

1. `reader` có kiểu `IOFunction` với `throws IOException`. Lambda/method reference có thể gọi `firstLine` mà không cần bắt ngay trong thân; `reader.apply("Java\nLambda")` trả về dòng `Java`.
2. `adapted` có kiểu `Function`, vì vậy thân phải tự xử lý `IOException`; khi đầu vào bình thường, trả về `Lambda`.
3. Với đầu vào `"FAIL"`, `firstLine` ném `IOException`. Adapter bọc nó thành `UncheckedIOException`; caller truy xuất ngoại lệ gốc bằng `getCause()`.
4. `task` có kiểu `Callable`; `call()` có hợp đồng `throws Exception`. Lời gọi thành công trả về `Callable`.
5. Khi gọi `reader.apply("FAIL")`, exception checked thoát qua đúng hợp đồng `IOFunction.apply` và được `catch (IOException e)` xử lý.

Điểm quan trọng là **cùng một phương thức `firstLine`** có thể được dùng trong các lambda khác nhau, nhưng đường xử lý ngoại lệ thay đổi theo **hợp đồng SAM mà lambda được gán**.

## 7. Trường hợp `InterruptedException` trong callback

`InterruptedException` là checked exception thường gặp khi gọi `Thread.sleep` hoặc thao tác chờ có thể bị ngắt. `Runnable.run()` không khai báo nó; vì vậy đoạn dưới đây là cách bắt và **khôi phục trạng thái ngắt** khi một tác vụ không có hợp đồng `throws InterruptedException`:

```java
Runnable task = () -> {
    try {
        Thread.sleep(100);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return;
    }
};
```

Không dùng `catch (Exception e) { }` để bỏ qua sự kiện bị ngắt. Trong bài toán có chính sách hủy tác vụ, việc khôi phục interrupt flag giúp tầng điều phối nhận ra yêu cầu ngắt. Nếu functional interface do bạn làm chủ và cần cho phép lan truyền `InterruptedException`, có thể khai báo chính xác trong SAM; nhưng các API nhận `Runnable` vẫn yêu cầu triển khai không làm rò checked exception ra ngoài.

## 8. Lỗi thường gặp và cách sửa

| Sai lầm | Cơ chế lỗi | Cách xử lý |
| --- | --- | --- |
| `Function<Path,String> f = p -> Files.readString(p)` | `Function.apply` không khai báo `IOException` | Bắt trong lambda rồi xử lý/bọc hợp lý, hoặc thay đổi API nhận callback nếu có quyền |
| Khai báo `throws IOException` cho method tạo `Function` | Không thay đổi hợp đồng của `Function.apply` | Kiểm tra `throws` của **SAM đích** |
| Đổi sang `Callable` trong khi `Stream.map` đòi `Function` | Hai interface không tương thích tự động | Dùng `Function` với chiến lược xử lý ngoại lệ rõ ràng |
| Bắt `IOException` rồi `return null` dù `null` không là kết quả hợp lệ | Biến lỗi thành dữ liệu giả, khó phát hiện | Báo lỗi, trả kiểu kết quả có ngữ nghĩa hoặc thiết kế API khác |
| `catch (Exception ignored) { }` | Nuốt lỗi, bỏ mất nguyên nhân | Chỉ bắt ngoại lệ có thể xử lý; giữ `cause` khi bọc |
| Bỏ qua `InterruptedException` | Làm mất tín hiệu ngắt | Xử lý hủy đúng chính sách và thường khôi phục interrupt flag |
| Nghĩ method reference sẽ bỏ qua checked exception | Method reference cũng bị kiểm tra theo SAM | Dùng target type phù hợp hoặc adapter |
| Bọc mọi checked exception vào `RuntimeException` không phân biệt | Mất ngữ nghĩa lỗi, khó quan sát và xử lý | Chọn wrapper có ý nghĩa, ví dụ `UncheckedIOException` cho I/O |
| Cho rằng tạo lambda sẽ chạy body ngay | Lambda chỉ thực thi khi được gọi qua SAM | Phân biệt thời điểm gán, gọi và lúc lỗi thực sự phát sinh |

### Vấn đề overload

Khi có nhiều overload nhận các functional interface có tham số/kết quả tương thích nhưng hợp đồng checked exception khác nhau, việc chọn overload có thể không trực quan hoặc mơ hồ. Đừng giả định chỉ dựa trên `throws` là compiler luôn chọn overload “đúng”. Khai báo biến lambda theo interface mong muốn trước khi truyền hoặc cung cấp ép kiểu tường minh thích hợp khi cần làm rõ API đích.

## 9. Quy tắc thiết kế nên áp dụng

- **Bắt đầu từ SAM của API nhận lambda:** kiểm tra đúng chữ ký và `throws`, không suy đoán từ nội dung lambda.
- **Ưu tiên hợp đồng ngoại lệ cụ thể:** nếu callback thực sự có thể lỗi I/O và bạn quản lý API, `throws IOException` rõ nghĩa hơn `throws Exception`.
- **Chọn nơi xử lý lỗi có đủ thông tin:** bắt trong lambda nếu có thể phục hồi; nếu không, lan truyền theo giao diện phù hợp hoặc bọc có nguyên nhân rõ ràng tại ranh giới API.
- **Giữ nguyên nguyên nhân khi bọc:** dùng `new UncheckedIOException(message, cause)` cho `IOException` để còn truy vết.
- **Không tạo kết quả giả để “chữa” lỗi checked:** điều này dễ làm hỏng dữ liệu và che nguyên nhân.
- **Tuân thủ hợp đồng của thư viện:** `Stream.map` cần `Function`; `Callable` chỉ dùng nơi API chấp nhận; các interface tự định nghĩa không tự động thay thế `java.util.function`.
- **Chú ý ngắt luồng:** với `InterruptedException`, tôn trọng cách tác vụ phản ứng với tín hiệu hủy, thường bằng cách khôi phục interrupt flag trong callback không khai báo checked exception.
- **Tương thích phiên bản:** cú pháp lambda, `Callable`, `UncheckedIOException` và các `java.util.function` dùng trong bài có thể dùng từ Java 8; `Files.readString` là API Java 11+ và `Stream.toList` là Java 16+. Chọn API theo mức Java thật sự được dự án hỗ trợ.

### Câu hỏi tự kiểm tra

1. Vì sao `() -> load(path)` hợp lệ khi gán cho `Callable<String>` nhưng có thể không hợp lệ với `Supplier<String>`?
2. Phương thức chứa câu lệnh tạo lambda có `throws IOException` có làm `Function.apply` được ném `IOException` không? Vì sao?
3. Tại sao `FileNotFoundException` tương thích với `throws IOException`, còn `SQLException` thì không?
4. Với `Stream.map` cần đọc tệp, bạn sẽ bắt, chuyển hoặc truyền lỗi như thế nào để caller không hiểu nhầm kết quả?
5. Vì sao khi bắt `InterruptedException` trong `Runnable` nên cân nhắc khôi phục trạng thái interrupt?

**Ghi nhớ:** checked exception phát sinh từ thân lambda phải được **bắt trong thân** hoặc **được cho phép bởi mệnh đề `throws` của phương thức trừu tượng của functional interface đích**. Đây là quy tắc biên dịch gắn với target type, áp dụng cho cả lambda và method reference, và vẫn là nền tảng của Java hiện đại.

## Tài liệu chuẩn để tra cứu

- Java Language Specification, **`15.27 Lambda Expressions** và **`11.2 Compile-Time Checking of Exceptions**: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html
- Java SE API, **`java.util.concurrent.Callable`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Callable.html
- Java SE API, **`java.util.function.Function`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html
- Java SE API, **`java.io.UncheckedIOException`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/UncheckedIOException.html
