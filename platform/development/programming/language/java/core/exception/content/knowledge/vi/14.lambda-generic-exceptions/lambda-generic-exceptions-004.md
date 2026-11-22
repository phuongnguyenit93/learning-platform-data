# Vì sao `Function`, `Consumer` và `Supplier` thông thường gây vướng với checked exception trong Java?

> **Chủ đề:** Java Core → Exception → Lambda và generic. Ba functional interface quen thuộc trong `java.util.function` — `Function<T,R>`, `Consumer<T>` và `Supplier<T>` — được thiết kế cho callback thông dụng nhưng **phương thức trừu tượng của chúng không khai báo `throws` cho checked exception**. Vì vậy một lambda hay method reference gán cho các kiểu này không được để `IOException`, `SQLException` hay checked exception khác thoát trực tiếp. Vướng mắc đến từ **hợp đồng phương thức đích của lambda**, chứ không phải vì lambda “không thể dùng checked exception”.

## 1. Nắm đúng ba chữ ký

Đọc ba phương thức trừu tượng (các interface thật còn có những method hỗ trợ khác):

```java
@FunctionalInterface
interface Function<T, R> {
    R apply(T value);
}

@FunctionalInterface
interface Consumer<T> {
    void accept(T value);
}

@FunctionalInterface
interface Supplier<T> {
    T get();
}
```

Đây là bản **rút gọn để giải thích chữ ký**, không phải bản sao toàn bộ mã nguồn JDK; khi viết code thật dùng `java.util.function.Function`, `Consumer`, `Supplier`. Tên tham số không quan trọng, nhưng sự vắng mặt của `throws IOException` hoặc `throws Exception` rất quan trọng.

| Interface chuẩn | Phương thức đích | Công việc thường dùng | Cho checked exception thoát trực tiếp? |
| --- | --- | --- | --- |
| `Function<T,R>` | `R apply(T t)` | Chuyển đổi từ T sang R, `stream.map(...)` | Không |
| `Consumer<T>` | `void accept(T t)` | Thực hiện side effect, `forEach(...)` | Không |
| `Supplier<T>` | `T get()` | Tạo/cung cấp giá trị khi cần, `orElseGet(...)` | Không |

**Lưu ý:** “không khai báo checked exception” không có nghĩa callback không thể ném **unchecked `RuntimeException` hoặc `Error`**. Chúng vẫn có thể xuất hiện trong quá trình chạy dù không kê `throws`.

Ví dụ hợp lệ:

```java
java.util.function.Function<String, Integer> length =
        String::length;

java.util.function.Consumer<String> print =
        System.out::println;

java.util.function.Supplier<String> supply =
        () -> "Hello";
```

Các đoạn trên dùng lambda/method reference không gây checked exception theo chữ ký. Trái lại, `Files.readString(path)` hoặc `BufferedReader.readLine()` có thể ném `IOException` (checked), nên không thể nhét trực tiếp vào callback chuẩn mà không có cách xử lý.

## 2. Checked và unchecked exception: vấn đề nằm ở compile-time

Trong Java:

- **Checked exception:** các subtype của `Throwable` không thuộc nhánh `RuntimeException` hoặc `Error`; ví dụ `IOException`, `SQLException`, `ParseException`, `InterruptedException`. Khi có thể thoát khỏi phương thức, code phải bắt hoặc khai báo theo luật Java.
- **Unchecked exception:** `RuntimeException`/`Error` cùng các subtype. Compiler không áp đặt nghĩa vụ bắt/khai báo như với checked exceptions.
- **Lambda:** có thể chạy code gây lỗi như bất kỳ phương thức nào; **điều bị giới hạn** là tập checked exception nó được phép để thoát, dựa trên **functional interface làm target type**.

Mục đích của checked exception là để người gọi nhìn thấy và giải quyết đường thất bại theo API. `Function.apply` không quảng cáo `IOException`; một nơi gọi `Function.apply`, như implementation của `Stream.map`, không có nghĩa vụ checked I/O được công bố. Java không thể cho lambda bí mật mở rộng hợp đồng ấy.

### 2.1. Code cố ý không biên dịch: `Function`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

class InvalidFunction {
    static void demo() {
        Function<Path, String> read = path -> Files.readString(path);
    }
}
```

Đây là **ví dụ cố ý không biên dịch**: `Files.readString(Path)` công bố checked `IOException`, còn `Function.apply(Path)` không công bố nó. Thông báo `javac` thường có ý “unreported exception IOException; must be caught or declared”.

Ngay cả khi `demo()` được đổi thành:

```java
static void demo() throws IOException {
    Function<Path, String> read = path -> Files.readString(path);
}
```

thì **vẫn sai**. `throws IOException` thuộc phương thức **`demo()`**, không thay đổi chữ ký `Function.apply()` mà lambda triển khai. Exception có thể phát sinh **sau khi `demo()` đã kết thúc**, tại lúc một caller khác chạy `read.apply(...)`. Compiler cần bảo vệ hợp đồng của callback, không chỉ phương thức nơi tạo lambda.

### 2.2. Code cố ý không biên dịch: `Consumer`

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Consumer;

class InvalidConsumer {
    static void demo() {
        Consumer<Path> delete = path -> Files.delete(path);
    }
}
```

`Files.delete(Path)` có thể ném checked `IOException`; `Consumer.accept` không khai báo checked exception. Vì vậy đoạn trên bị từ chối.

Đừng suy luận “Consumer trả void thì được ném tùy ý”. Giá trị trả về và quy tắc checked `throws` là hai khía cạnh độc lập.

### 2.3. Code cố ý không biên dịch: `Supplier`

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Supplier;

class InvalidSupplier {
    static void demo(Path path) {
        Supplier<String> source = () -> Files.readString(path);
    }
}
```

`Supplier.get()` không khai báo checked exception. Ngay cả khi `get()` chỉ được gọi sau này, hợp đồng vẫn không cho `IOException` thoát trực tiếp.

## 3. Lambda không tự quyết định chữ ký `throws`: target typing

Một lambda như:

```java
path -> java.nio.file.Files.readString(path)
```

không mang một “kiểu lambda độc lập” với hợp đồng exception tự động suy từ body. Nó cần một **target type** — thường là một functional interface.

Cùng logic đọc file có thể:

- **Bị từ chối** khi target là `Function<Path,String>`.
- **Hợp lệ** khi target là một functional interface tự định nghĩa có `String apply(Path) throws IOException`.
- **Hợp lệ** khi lambda bắt `IOException` ngay bên trong và trả kết quả/đổi thành unchecked exception phù hợp.

Ví dụ:

```java
@FunctionalInterface
interface ThrowingPathReader {
    String read(java.nio.file.Path path)
            throws java.io.IOException;
}
```

Khi đó:

```java
ThrowingPathReader reader =
        path -> java.nio.file.Files.readString(path);
```

là hợp lệ trong một class/method có import hoặc tên đầy đủ tương ứng. Nhưng `ThrowingPathReader` **không tự là** `Function<Path,String>`; không thể truyền biến reader thẳng vào `Stream.map(...)`, vì `map` yêu cầu `Function` chuẩn.

Đó là lý do đôi khi cần **adapter** giữa hai kiểu callback.

## 4. Method reference gặp cùng ràng buộc

Không chỉ lambda:

```java
// CỐ Ý SAI:
java.util.function.Function<java.nio.file.Path, String> read =
        java.nio.file.Files::readString;
```

`Files.readString(Path)` khai báo `throws IOException`, nên method reference đó không tương thích với phương thức trừu tượng `Function.apply`.

Ngược lại:

```java
ThrowingPathReader read =
        java.nio.file.Files::readString;
```

có thể hợp lệ nếu `ThrowingPathReader` đã định nghĩa như Mục 3.

**Method reference không làm biến mất luật checked exception.** Nó là cách viết ngắn cho việc chuyển method hiện có thành callback của một functional interface phù hợp; việc kiểm tra loại ngoại lệ vẫn dựa trên target method.

## 5. Vì sao `Stream.map(...)` và `forEach(...)` hay làm lộ vấn đề?

API Stream dùng các functional interface chuẩn, ví dụ:

```java
<R> java.util.stream.Stream<R> map(
        java.util.function.Function<? super T, ? extends R> mapper);
```

Đây là chữ ký khái quát của `Stream<T>.map`, không phải một chương trình độc lập. Phương thức mapper nhận kiểu `Function`; vì vậy lambda trong `map` vẫn bị giới hạn checked `throws` của `Function.apply`.

Ví dụ người học muốn đọc nhiều file:

```java
// CỐ Ý SAI — readString có checked IOException:
java.util.List<String> content = paths.stream()
        .map(path -> java.nio.file.Files.readString(path))
        .toList();
```

Giả định `paths` là `List<Path>`. Mặc dù đoạn code ở trong một method có thể khai báo `throws IOException`, callback mà `map` nhận vẫn là `Function<Path,String>` **không khai báo checked exception**.

Tương tự, `forEach` dùng `Consumer`:

```java
// CỐ Ý SAI — Files.delete(path) có checked IOException:
paths.forEach(path -> java.nio.file.Files.delete(path));
```

Không phải vì Stream hay `List.forEach` cấm I/O, mà vì **kiểu callback tại điểm gọi** không cho checked exception thoát trực tiếp.

### 5.1. Stream thường lười thực thi

Trong pipeline Stream, `map` là một **intermediate operation**. Lambda được đăng ký có thể chưa chạy ngay khi tạo pipeline. Thông thường nó được gọi trong quá trình thực hiện **terminal operation** như `toList()`, `collect(...)`, `forEach(...)` hoặc `reduce(...)`.

Điều này ảnh hưởng nơi bắt lỗi:

```java
var pipeline = inputs.stream().map(converter);
try {
    var results = pipeline.toList();
    // Sử dụng results.
} catch (RuntimeException e) {
    // Lỗi unchecked từ converter có thể xuất hiện lúc terminal operation.
}
```

Đoạn minh họa giả định biến `inputs`/`converter` đã được định nghĩa. Nếu `converter` bọc checked `IOException` thành `UncheckedIOException`, lỗi có thể xuất hiện ở `toList()`, không phải tại lúc bạn gọi `map(converter)`.

Đừng kết luận một pipeline “thành công” chỉ vì biểu thức `stream.map(...)` đã trả về một Stream.

### 5.2. Parallel stream và chính sách side effect

Nếu lambda thực hiện I/O qua `parallelStream()`, thứ tự thực thi/hoàn thành có thể không xác định; một exception từ một worker có thể khiến terminal operation thất bại trong khi side effect khác đã xảy ra. Không được giả định rollback, thứ tự log hoặc “đã gặp lỗi thì mọi tác vụ khác chắc chắn dừng ngay”.

Đặc biệt cẩn thận với `Consumer` ghi file/xóa file hoặc thao tác giao dịch: parallel execution và exception không tự bảo đảm tính nguyên tử.

## 6. Cách 1: bắt checked exception bên trong lambda

Khi API chuẩn cần một `Function` và ta có cách **xử lý thật sự** lỗi ở ngay đó, có thể `try/catch` trực tiếp trong body của lambda.

### 6.1. Trả fallback có nghĩa, không che lỗi tùy tiện

Tạo **`FunctionCatchInsideDemo.java`**:

```java
import java.io.IOException;
import java.util.List;
import java.util.function.Function;

public class FunctionCatchInsideDemo {
    static int parseSize(String input) throws IOException {
        if ("bad".equals(input)) {
            throw new IOException("Nguồn không khả dụng");
        }
        return input.length();
    }

    public static void main(String[] args) {
        Function<String, Integer> safeLength = input -> {
            try {
                return parseSize(input);
            } catch (IOException e) {
                System.out.println("Ghi nhận lỗi: " + input);
                return -1;
            }
        };

        List<Integer> results = List.of("cat", "bad", "xy")
                .stream()
                .map(safeLength)
                .toList();

        System.out.println("Kết quả: " + results);
    }
}
```

Biên dịch/chạy Java 17:

```bash
javac -encoding UTF-8 FunctionCatchInsideDemo.java
java FunctionCatchInsideDemo
```

Stdout:

```text
Ghi nhận lỗi: bad
Kết quả: [3, -1, 2]
```

**Giải thích:**

1. `parseSize` công bố `throws IOException`; bên trong có đường lỗi được mô phỏng có kiểm soát.
2. Lambda `safeLength` tự bắt `IOException`, nên không để checked exception thoát khỏi `Function.apply`.
3. Giá trị `-1` ở ví dụ là một **sentinel** được quy ước cho thất bại để dễ quan sát; không phải fallback an toàn mặc định cho mọi bài toán.
4. Stream được chạy qua `toList()`, từ đó callback thực thi.
5. Nếu `-1` cũng là một giá trị hợp lệ trong domain, hoặc caller cần biết nguyên nhân I/O, cách thiết kế này dễ gây nhập nhằng. Khi đó nên dùng một kiểu kết quả rõ ràng hoặc cho lỗi truyền theo một hợp đồng khác.

### 6.2. Tránh “bắt rồi coi là thành công”

Anti-pattern:

```java
Function<Path, String> unsafe = path -> {
    try {
        return Files.readString(path);
    } catch (IOException ignored) {
        return "";
    }
};
```

Đây là đoạn minh họa cần import `Path`/`Files`/`IOException`. Nếu chuỗi rỗng là dữ liệu file hợp lệ, caller không thể phân biệt “file rỗng thật” với “đọc file thất bại”. Không dùng cách này chỉ để qua compiler.

Nếu fallback là một phần **hợp đồng sản phẩm** — ví dụ cache dự phòng đã được kiểm chứng — có thể trả fallback; cần ghi rõ trường hợp nào được fallback và tác động tới trạng thái.

## 7. Cách 2: chuyển checked exception thành unchecked và giữ `cause`

Khi không thể xử lý hợp lệ tại callback, nhưng API bắt buộc dùng `Function`/`Consumer`/`Supplier`, có thể bọc checked exception vào một unchecked exception phù hợp rồi để lỗi **lan lên** nơi quyết định failure.

Với `IOException`, Java cung cấp `java.io.UncheckedIOException`:

```java
try {
    return java.nio.file.Files.readString(path);
} catch (java.io.IOException original) {
    throw new java.io.UncheckedIOException(
            "Không đọc được file", original);
}
```

Đây là mảnh method/lambda minh họa cần đặt trong ngữ cảnh có `return` thích hợp. Ưu điểm:

- `UncheckedIOException extends RuntimeException`, nên callback `Function.apply` được phép ném.
- `getCause()` giữ đối tượng `IOException` gốc để truy nguyên.
- Caller nhận **UncheckedIOException**, không nhận `IOException` trực tiếp khi gọi callback.
- Lỗi không bị nuốt hoặc trá hình thành giá trị thành công.

**Không** thay bằng `throw new RuntimeException(original.getMessage())`: cách đó sao chép message nhưng làm mất mối liên kết cause. Khi dùng wrapper, ưu tiên constructor nhận cause.

### 7.1. Java 17: adapter I/O từ `ThrowingFunction` sang `Function`

Tạo **`UncheckedFunctionAdapterDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class UncheckedFunctionAdapterDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(
            IoFunction<T, R> source) {
        Objects.requireNonNull(source);
        return value -> {
            try {
                return source.apply(value);
            } catch (IOException e) {
                throw new UncheckedIOException(
                        "Không thể chuyển đổi dữ liệu", e);
            }
        };
    }

    static int readSize(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("Không đọc được bad");
        }
        return key.length();
    }

    public static void main(String[] args) {
        Function<String, Integer> mapper =
                unchecked(UncheckedFunctionAdapterDemo::readSize);

        try {
            System.out.println(
                    List.of("good", "bad", "later")
                            .stream()
                            .map(mapper)
                            .toList());
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: "
                    + e.getClass().getSimpleName());
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
javac -encoding UTF-8 UncheckedFunctionAdapterDemo.java
java UncheckedFunctionAdapterDemo
```

Stdout:

```text
Wrapper: UncheckedIOException
Cause: IOException
Cause message: Không đọc được bad
```

**Luồng hoạt động:**

1. `IoFunction.apply` **có** `throws IOException`, nên method reference `readSize` là target hợp lệ của `IoFunction`.
2. `unchecked(...)` trả một `Function<T,R>` chuẩn, bắt `IOException` và ném `UncheckedIOException`.
3. `Stream.map(...)` nhận `Function` và biên dịch được.
4. Khi terminal `toList()` chạy, phần tử `"bad"` làm `readSize` ném `IOException`.
5. Wrapper unchecked thoát lên vị trí terminal operation và được `catch (UncheckedIOException)` bắt.
6. `"later"` không được biến đổi trong pipeline tuần tự này sau khi exception đã làm terminal operation thất bại; ví dụ không dựa vào giả định này để khôi phục công việc.

**Không phải adapter phép màu:** adapter đổi **cách báo lỗi**, không biến thất bại thành thành công, không rollback side effect và không bảo đảm retry an toàn. Nó phù hợp khi boundary của API đã chấp nhận unchecked failure và caller có chính sách chẩn đoán/khôi phục.

### 7.2. Khi không phải `IOException` thì sao?

`UncheckedIOException` chỉ nhận **`IOException`** làm nguyên nhân. Với checked exception khác, có thể tạo một subclass `RuntimeException` phù hợp hoặc dùng `RuntimeException("...", cause)` để giữ cause khi đúng hợp đồng.

Đừng bọc tất cả `RuntimeException` sẵn có thành một wrapper khác nếu không có lý do: làm mất thông tin phân loại và khiến stack phức tạp. Adapter chuyên biệt nên bắt **chỉ checked exception dự kiến**, để những unchecked lỗi lập trình tiếp tục truyền nguyên dạng.

## 8. Cách 3: dùng `ThrowingFunction<T,R,E>` riêng có `throws E`

Khi **bạn kiểm soát API nhận lambda**, cách thể hiện hợp đồng checked exception rõ ràng nhất đôi khi là tạo functional interface riêng:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}
```

Nếu `E` là `IOException`, lambda có thể để `IOException` thoát và caller của method nhận callback phải giải quyết nó. Interface này dùng **generic type parameter `E`** để khai báo checked exception có thể phát sinh.

Tương tự:

```java
@FunctionalInterface
interface ThrowingConsumer<T, E extends Exception> {
    void accept(T input) throws E;
}

@FunctionalInterface
interface ThrowingSupplier<T, E extends Exception> {
    T get() throws E;
}
```

Ba kiểu trên là **định nghĩa tự tạo**, không phải các interface chuẩn của `java.util.function`. Tên `ThrowingFunction` và generic `E extends Exception` là một convention thiết kế; Java không có sẵn chúng trong `java.util.function`.

### 8.1. Generic `E` giúp gì?

Xét:

```java
static <T, R, E extends Exception> R call(
        T input, ThrowingFunction<T, R, E> operation) throws E {
    return operation.apply(input);
}
```

Đây là method minh họa cần đặt trong class. Vì operation có thể ném `E`, method `call` công bố `throws E`. Nếu lambda gắn với `IOException`, caller có thể bắt `IOException` thay vì buộc bắt `Exception` rộng.

Generic exception type có thể tăng độ chính xác hợp đồng. Tuy nhiên type inference có quy tắc riêng; nếu chương trình phức tạp hoặc có nhiều exception độc lập, có thể cần khai báo type parameter/chữ ký rõ ràng. Đừng giả định một generic `E` mô tả hoàn hảo mọi union của các checked exception.

### 8.2. Java 17: giữ nguyên checked exception qua custom functional interface

Tạo **`ThrowingFunctionDemo.java`**:

```java
import java.io.IOException;

public class ThrowingFunctionDemo {
    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T value) throws E;
    }

    static <T, R, E extends Exception> R execute(
            T input, ThrowingFunction<T, R, E> action) throws E {
        return action.apply(input);
    }

    static int loadLength(String input) throws IOException {
        if ("bad".equals(input)) {
            throw new IOException("Dữ liệu không đọc được");
        }
        return input.length();
    }

    public static void main(String[] args) {
        try {
            int result = ThrowingFunctionDemo
                    .<String, Integer, IOException>execute(
                            "cat", ThrowingFunctionDemo::loadLength);
            System.out.println("Length: " + result);

            ThrowingFunctionDemo
                    .<String, Integer, IOException>execute(
                            "bad", ThrowingFunctionDemo::loadLength);
        } catch (IOException e) {
            System.out.println("Checked: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ThrowingFunctionDemo.java
java ThrowingFunctionDemo
```

Stdout:

```text
Length: 3
Checked: IOException
Message: Dữ liệu không đọc được
```

**Điểm quan trọng:**

- `ThrowingFunction.apply` cho phép checked `E`.
- `execute(...)` công bố `throws E`, nên exception gốc có thể thoát **mà không cần wrapper unchecked**.
- Ở call site, ví dụ chỉ rõ generic arguments, gồm `IOException`, để việc học dễ theo dõi; trong trường hợp đơn giản compiler có thể suy luận kiểu.
- Không cần `catch(Exception)` hoặc `throws Exception` rộng nếu hợp đồng thực tế chỉ yêu cầu `IOException`.
- Nếu muốn truyền `ThrowingFunction` trực tiếp cho `Stream.map` chuẩn, vẫn không được: `map` nhận `Function`, không phải kiểu custom này.

### 8.3. Vì sao tự định nghĩa interface không giải quyết trực tiếp `Stream.map`?

Trong Java, lambda là target-typed, nhưng `Stream.map` đã công bố:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

Method signature của `map` thuộc thư viện chuẩn; việc bạn tạo `ThrowingFunction` **không thay thế parameter type của `map`**. Muốn áp dụng, phải:

1. Viết **adapter** từ `ThrowingFunction` sang `Function`, quyết định chuyển lỗi sang unchecked hoặc xử lý khác; hoặc
2. Viết hàm/luồng xử lý riêng nhận `ThrowingFunction` và công bố `throws E`; hoặc
3. Dùng vòng lặp thông thường có `try/catch`/`throws` khi logic checked exception là trung tâm.

Đây là hạn chế của **API đích**, không phải vấn đề generic làm thiếu từ khóa `throws`.

## 9. `Consumer<T>`: xử lý side effect và checked exception

`Consumer.accept` nhận một đối tượng, trả `void`; các thao tác side effect thường là ghi file, xóa file, lưu dữ liệu, gửi sự kiện hoặc cập nhật trạng thái. Những thao tác này đặc biệt dễ có checked exceptions.

Một `Consumer` với `forEach` có thể:

- Bắt lỗi và tiếp tục xử lý phần tử kế tiếp **nếu đó là chính sách đã chọn**.
- Bắt rồi ném unchecked wrapper khiến vòng lặp thường dừng ngay vì exception.
- Đưa lỗi vào một kết quả có cấu trúc được quản lý bên ngoài (cần cân nhắc concurrency và thread safety).
- Không thể để checked exception thoát trực tiếp theo `Consumer.accept`.

### 9.1. Java 17: bắt từng lỗi khi chính sách cho phép tiếp tục

Tạo **`ConsumerFailurePolicyDemo.java`**:

```java
import java.io.IOException;
import java.util.List;
import java.util.function.Consumer;

public class ConsumerFailurePolicyDemo {
    static void process(String name) throws IOException {
        if ("bad".equals(name)) {
            throw new IOException("Không xử lý được bad");
        }
        System.out.println("OK: " + name);
    }

    public static void main(String[] args) {
        Consumer<String> consumer = name -> {
            try {
                process(name);
            } catch (IOException e) {
                System.out.println("FAILED: " + name);
            }
        };

        List.of("one", "bad", "two").forEach(consumer);
        System.out.println("Hoàn tất lượt forEach");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ConsumerFailurePolicyDemo.java
java ConsumerFailurePolicyDemo
```

Stdout:

```text
OK: one
FAILED: bad
OK: two
Hoàn tất lượt forEach
```

Ví dụ chủ động chọn **tiếp tục sau một phần tử thất bại**, vì các phần tử được coi độc lập trong tình huống mô phỏng. Đây **không phải mặc định đúng** cho các thao tác ghi dữ liệu thực tế.

Nếu thất bại của một phần tử khiến cả batch phải thất bại, chỉ in “FAILED” rồi tiếp tục như thành công là sai. Khi đó hãy dùng cấu trúc kết quả batch thể hiện phần tử lỗi, hoặc ném wrapper và để caller xử lý trạng thái batch; cũng phải xét những side effect đã xảy ra trước đó.

### 9.2. Viết vòng lặp thường khi cần semantics checked rõ ràng

Thay vì `forEach`:

```java
static void deleteAll(java.util.List<java.nio.file.Path> files)
        throws java.io.IOException {
    for (java.nio.file.Path path : files) {
        java.nio.file.Files.delete(path);
    }
}
```

Đây là một **method hoàn chỉnh**, nhưng cần đặt trong class. Nó giữ checked `throws IOException` rõ ràng, dùng `for` thông thường và không cần adapter `Consumer`.

Khi chức năng chính là I/O có thể thất bại, vòng lặp thường thường **dễ hiểu hơn** việc ép `Consumer` chuẩn rồi bọc exception qua nhiều tầng. Không phải mọi tác vụ phải dùng Stream/lambda mới là Java hiện đại.

## 10. `Supplier<T>`: cung cấp giá trị nhưng `get()` không cho checked exception

`Supplier<T>` rất phổ biến với tạo lazy value, `Optional.orElseGet(...)`, các API cache và các hook tạo đối tượng. Nếu khởi tạo giá trị có I/O/SQL checked, lambda sẽ gặp giới hạn tương tự.

Ví dụ sai:

```java
java.util.function.Supplier<String> config =
        () -> java.nio.file.Files.readString(path);
```

Giả định `path` có kiểu `Path`. `Files.readString` có `throws IOException`, nên không biên dịch khi dùng trực tiếp với `Supplier.get`.

### 10.1. Java 17: `Supplier` đổi IOException thành unchecked

Tạo **`SupplierCheckedDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Supplier;

public class SupplierCheckedDemo {
    static String readConfig(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("Không tải được config");
        }
        return "ready";
    }

    static Supplier<String> createSupplier(boolean fail) {
        return () -> {
            try {
                return readConfig(fail);
            } catch (IOException e) {
                throw new UncheckedIOException("Lỗi cấu hình", e);
            }
        };
    }

    public static void main(String[] args) {
        Supplier<String> good = createSupplier(false);
        Supplier<String> bad = createSupplier(true);

        System.out.println("Good: " + good.get());
        try {
            System.out.println("Bad: " + bad.get());
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: " + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SupplierCheckedDemo.java
java SupplierCheckedDemo
```

Stdout:

```text
Good: ready
Wrapper: UncheckedIOException
Cause: Không tải được config
```

`createSupplier(...)` chỉ tạo đối tượng callback; `readConfig(...)` được thực thi **khi gọi `get()`**, không phải lúc dựng supplier. Do đó lỗi xảy ra trong `get()`. Chữ ký `Supplier.get` không khai báo checked exception, nên wrapper unchecked làm đường thất bại tiếp tục hợp lệ với API đích.

### 10.2. `Optional.orElseGet` cũng chịu quy tắc này

`Optional.orElseGet(Supplier<? extends T>)` nhận một `Supplier` chuẩn. Nếu fallback phải gọi API checked I/O, code cần xử lý/bọc exception theo cùng cách. Không thể vì đó là “fallback” mà Java tự miễn checked exception.

Thêm một lưu ý: `Optional.orElseGet` chỉ gọi supplier khi Optional rỗng, nên lỗi từ supplier **chỉ có thể phát sinh trên đường cần fallback**. Đừng chủ quan không kiểm thử nhánh này.

## 11. `Callable<V>` khác `Supplier<V>` ở checked `throws`

Trong thư viện chuẩn có `java.util.concurrent.Callable<V>`:

```java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
```

Vì `Callable.call()` khai báo `throws Exception`, một lambda gọi API ném checked `IOException` có thể được gán cho `Callable<String>`. Đây là đối chiếu rất rõ với `Supplier.get()`.

| Tiêu chí | `Supplier<T>` | `Callable<V>` |
| --- | --- | --- |
| Phương thức đích | `T get()` | `V call() throws Exception` |
| Checked exception có thể thoát? | Không | Có; trong phạm vi `Exception` |
| Package | `java.util.function` | `java.util.concurrent` |
| Được `Stream.map` nhận trực tiếp? | Không; map nhận `Function` | Không; map nhận `Function` |
| Dùng nhiều trong | Lazy value, Optional, factory callback | Executor/service task, công việc có thể thất bại |

`Callable` không phải một `Supplier` có tên khác. Hai interface có mục đích và chữ ký khác nhau; không thể đưa `Callable` trực tiếp cho API yêu cầu `Supplier` mà không adapter.

### 11.1. Java 17: `Callable` giữ checked exception

Tạo **`CallableVsSupplierDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.function.Supplier;

public class CallableVsSupplierDemo {
    static String load(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("Không có dữ liệu");
        }
        return "loaded";
    }

    public static void main(String[] args) {
        Callable<String> task = () -> load(true);
        Supplier<String> good = () -> {
            try {
                return load(false);
            } catch (IOException e) {
                throw new IllegalStateException(e);
            }
        };

        System.out.println("Supplier: " + good.get());
        try {
            System.out.println("Callable: " + task.call());
        } catch (IOException e) {
            System.out.println("Checked: " + e.getMessage());
        } catch (Exception e) {
            System.out.println("Other: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CallableVsSupplierDemo.java
java CallableVsSupplierDemo
```

Stdout:

```text
Supplier: loaded
Checked: Không có dữ liệu
```

**Vì sao `catch(IOException)` hợp lệ?** `Callable.call()` công bố `throws Exception`, nên có thể phát sinh checked subtype `IOException`. Handler `catch(Exception)` còn lại bao phủ các checked exceptions khác mà hợp đồng `Callable` cho phép.

Nếu đổi lời gọi `task.call()` thành `good.get()` trong `try` chỉ có `Supplier.get()`, một handler checked `IOException` không có nguồn checked tương ứng sẽ bị compiler từ chối. Trường hợp có wrapper unchecked, phải bắt kiểu wrapper thích hợp.

### 11.2. `Runnable` cũng không khai báo checked exception

`Runnable.run()` là `void run()`, không `throws` checked exception. Vì vậy lambda truyền cho `new Thread(() -> ...)` hoặc `Executor.execute(Runnable)` gặp hạn chế tương tự `Consumer`. Ngược lại, `Callable.call` cho phép `throws Exception`.

**Tuy nhiên:** khi submit `Callable` tới `ExecutorService.submit` và lấy kết quả bằng `Future.get()`, thất bại tác vụ thường được bọc trong `ExecutionException` (cause là lỗi từ task). Không suy ra rằng checked `IOException` tự động ném trực tiếp từ `Future.get()`. Mỗi tầng có hợp đồng exception riêng.

## 12. Kiểu generic `E extends Exception` và giới hạn của suy luận kiểu

Một interface tự tạo có thể viết:

```java
@FunctionalInterface
interface CheckedMapper<T, R, E extends Exception> {
    R map(T input) throws E;
}
```

Ở đây `E` là biến kiểu đại diện cho **một họ ngoại lệ được khai báo theo type parameter**. Khi API sở hữu callback, nó có thể truyền nghĩa vụ checked từ callback ra caller:

```java
static <T, R, E extends Exception> R convert(
        T value, CheckedMapper<T, R, E> mapper) throws E {
    return mapper.map(value);
}
```

Nhưng một số giới hạn cần nhớ:

- `E` không làm `java.util.function.Function` bỗng chốc khai báo checked exception.
- Generic parameter là kiểu Java, không phải cú pháp “union exception”. Với nhiều checked exception không có quan hệ subtype chung hẹp, đôi khi API cần `throws Exception` hoặc phải khai báo nhiều tham số kiểu/thêm thiết kế thích hợp.
- Type inference chịu ràng buộc của ngữ cảnh gọi và lambda; trong ví dụ phức tạp, nên kiểm tra chữ ký suy luận thay vì khẳng định mọi lời gọi đều suy luận đúng subtype nhỏ nhất.
- Không nên tạo cả một framework utility generic chỉ để thay một vòng lặp `for` dễ hiểu.
- Java không có checked-exception polymorphism như một “effect system” tùy ý; luật `throws` vẫn nằm ở những phương thức và interface được khai báo.

### 12.1. Vì sao không để `E extends Throwable` tùy tiện?

Về cú pháp, functional interface có thể khai báo `throws E` với `E extends Throwable`. Tuy nhiên việc mở rộng lên `Throwable` có thể khiến API caller phải xử lý cả các tình huống dưới `Error` hoặc khai báo quá rộng, không hợp nghĩa vụ thông thường. `E extends Exception` thường phù hợp hơn nếu mục tiêu là hỗ trợ checked exceptions trong ứng dụng.

## 13. Cách viết adapter tổng quát: ưu điểm và bẫy

Một thư viện nội bộ đôi khi muốn adapter generic:

```java
@FunctionalInterface
interface CheckedFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}

static <T, R, E extends Exception>
java.util.function.Function<T, R> unchecked(
        CheckedFunction<T, R, E> source) {
    return input -> {
        try {
            return source.apply(input);
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException(
                    "Callback thất bại", e);
        }
    };
}
```

Đây là **hai khai báo minh họa** cần đặt đúng trong class/interface. Cơ chế:

1. `CheckedFunction` cho phép checked `E` thoát.
2. Adapter bắt unchecked `RuntimeException` và **ném lại nguyên trạng**.
3. Adapter bắt các `Exception` checked còn lại và bọc trong một `RuntimeException` có `cause`.
4. Kết quả adapter có kiểu `Function<T,R>` để truyền cho API chuẩn.

Nhưng cách này có hạn chế:

- Sau khi bọc, caller phải xử lý runtime wrapper, **không được mong `IOException` trực tiếp**.
- Wrapper chung mất khả năng phân loại nhanh các checked exceptions nếu không đọc `getCause()`; một adapter chuyên biệt cho `IOException` dùng `UncheckedIOException` có thể tốt hơn.
- `Exception` là phạm vi catch rộng; cần quyết định có nên giữ nguyên các `RuntimeException` vốn là lỗi khác không. Đoạn mẫu đã làm điều đó.
- Không được dùng adapter để âm thầm nuốt exception, hoặc thay mọi lỗi bằng `null`/giá trị mặc định ngoài hợp đồng.
- Nếu API xử lý song song, adapter phải tuân thủ thread safety của callback và quản lý side effect riêng.

### 13.1. Không “sneaky throw” chỉ để qua compiler

Có những thủ thuật generic/erasure cho phép ném checked exception qua một API không công bố nó (*sneaky throw*). Điều đó có thể khiến người sử dụng `Function.apply` bất ngờ nhận một checked exception ở runtime mà chữ ký không cho họ dự đoán.

Trong phần lớn ứng dụng, hãy ưu tiên ba cách rõ hợp đồng:

1. Bắt và xử lý thực sự trong callback.
2. Bọc unchecked có `cause` và chấp nhận thay đổi hợp đồng báo lỗi.
3. Dùng API/functional interface cho phép checked exception, hoặc vòng lặp thông thường.

Thủ thuật né compiler làm giảm khả năng đọc hiểu, có thể gây khó xử lý ở caller và khiến unit test/exception policy thiếu minh bạch.

## 14. Tài nguyên và `try-with-resources` trong lambda

Lambda có thể mở resource và tự đóng bằng `try-with-resources`:

```java
Function<Path, String> load = path -> {
    try (var reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    } catch (IOException e) {
        throw new UncheckedIOException(
                "Không thể đọc dòng đầu", e);
    }
};
```

Đây là **đoạn minh họa** (cần import `Path`, `Files`, `Function`, `IOException`, `UncheckedIOException`). Nhờ TWR, reader được đóng khi rời callback. Vì cả `Files.newBufferedReader(...)`, `readLine()` và `close()` có thể ném `IOException`, callback bắt và chuyển sang `UncheckedIOException`.

Những điểm cần chú ý:

- Lambda gọi nhiều lần có thể mở/đóng nhiều resource riêng; cân nhắc hiệu năng và vòng đời.
- Nếu thân đọc và `close()` đều thất bại, TWR giữ primary/suppressed theo quy tắc của `Throwable`; wrapper có `cause` là primary, nhờ đó vẫn có thể xem `getCause().getSuppressed()`.
- Không đưa một resource đã đóng ra ngoài callback rồi dùng lại tùy tiện.
- Nếu callback trả `Stream<String>` từ `Files.lines(path)`, phải thiết kế rõ **ai sở hữu và đóng stream**; không thể luôn đóng ngay trước khi caller kịp xử lý các phần tử.
- `Files.lines` có checked `IOException` khi mở, và một số lỗi đọc sau đó có thể được báo dưới dạng unchecked I/O trong lúc stream được tiêu thụ; cần hiểu hợp đồng API cụ thể.

### 14.1. Lazy stream và vị trí xảy ra lỗi I/O

Một lời gọi cung cấp dữ liệu cho Stream có thể không tiêu thụ file ngay. Nếu đóng source quá sớm hoặc giữ resource mở vô thời hạn, chương trình có thể gặp lỗi trong giai đoạn sau.

Đây là vấn đề **ownership/resource lifetime** bên cạnh vấn đề checked exception của callback. Không nên kết luận rằng chỉ cần adapter `Function` là đã giải quyết cả việc đóng tài nguyên.

## 15. `CompletableFuture`: callback khác, hợp đồng khác

Các method như `CompletableFuture.supplyAsync(Supplier<U>)` cũng nhận `Supplier` **không khai báo checked exception**. Vì thế:

```java
// CỐ Ý SAI nếu readChecked() throws IOException:
java.util.concurrent.CompletableFuture.supplyAsync(
        () -> readChecked());
```

sẽ gặp hạn chế checked tương tự.

Nếu chuyển thành unchecked wrapper trong supplier, một CompletableFuture thất bại sẽ hoàn tất **exceptionally**. Khi gọi `join()`, người sử dụng thường nhận `CompletionException`, và phải đọc cause chain theo hợp đồng `CompletableFuture`. Không giả định rằng `join()` tự ném checked `IOException` trực tiếp.

Khi dùng `get()` của `Future`/`CompletableFuture`, API công bố `ExecutionException` cùng các ngoại lệ của hoạt động chờ; tiếp tục phân biệt **lỗi gốc**, **wrapper unchecked trong callback**, và **wrapper đồng bộ hóa ở tương lai**.

### 15.1. Hệ quả với policy retry

Một thao tác callback đã ghi một phần dữ liệu trước khi thất bại không tự trở nên an toàn để retry chỉ vì nó chạy trong future/stream. Muốn retry, phải biết thao tác idempotent hay có transaction/compensation phù hợp. Exception wrapping giữ chẩn đoán, không hoàn tác side effect.

## 16. Khi nào nên bỏ Stream/lambda để viết vòng lặp?

Có những lúc câu trả lời tốt nhất là không ép I/O checked vào `Function` hoặc `Consumer`.

Ví dụ đọc nhiều file và **báo checked IOException trực tiếp**:

```java
static java.util.List<String> readAll(
        java.util.List<java.nio.file.Path> paths)
        throws java.io.IOException {
    java.util.List<String> results =
            new java.util.ArrayList<>();
    for (java.nio.file.Path path : paths) {
        results.add(java.nio.file.Files.readString(path));
    }
    return results;
}
```

Đây là method Java hợp lệ đặt trong class. Ưu điểm:

- Chữ ký `throws IOException` phản ánh lỗi I/O.
- Không cần adapter hoặc wrapper chỉ để làm vừa `Stream.map`.
- Thứ tự duyệt và vị trí lỗi khá dễ đọc.
- Có thể kiểm soát dừng khi lỗi, cleanup và xử lý phần đã hoàn tất.

**Nhược điểm không phải điều đáng sợ:** số dòng nhiều hơn Stream, nhưng hợp đồng lỗi rõ ràng. Ưu tiên khả năng đọc hiểu và bảo toàn ngữ nghĩa hơn cú pháp “functional” bằng mọi giá.

## 17. So sánh các phương án theo hợp đồng

| Nhu cầu | Hướng thường phù hợp | Điều cần tránh |
| --- | --- | --- |
| Lỗi có fallback đúng nghiệp vụ trong từng phần tử | `try/catch` ngay trong lambda chuẩn | Trả sentinel nhập nhằng rồi giả thành công |
| API thư viện yêu cầu `Function`/`Consumer`/`Supplier`, không thể đổi | Bọc unchecked có cause, hoặc kết quả có cấu trúc khi API hỗ trợ | Tự ý truyền checked exception bằng thủ thuật |
| Bạn kiểm soát API nhận lambda | `ThrowingFunction`/`ThrowingConsumer`/`ThrowingSupplier` có `throws E` | Tạo abstraction quá phức tạp không có nhu cầu |
| Task được gọi như `Callable` | Dùng `Callable.call() throws Exception` | Nghĩ Callable là subtype của Supplier |
| Đọc/ghi file hàng loạt cần truyền checked exception lên caller | `for` thường với `throws IOException` | Ép stream rồi nuốt lỗi |
| Stream pipeline đọc file lazy | Thiết kế resource lifetime và vị trí terminal operation | Đóng resource quá sớm/không đóng |
| Async supplier | Chuyển lỗi có cause, dùng exception policy của future | Mong checked IOException thoát trực tiếp từ `join()` |
| Xử lý nhiều phần tử độc lập | Kết quả per-item hoặc error collection có nghĩa | Gọi mọi phần tử thành công khi một số đã thất bại |

## 18. Những lỗi phổ biến

### 18.1. “Lambda không được ném exception”

Sai. Lambda có thể ném unchecked exceptions, và có thể ném checked exceptions **nếu functional method của target type cho phép**, chẳng hạn `Callable.call() throws Exception` hoặc custom `ThrowingFunction.apply() throws IOException`.

### 18.2. “Chỉ cần thêm `throws IOException` vào method bao ngoài”

Sai nếu checked exception nằm **bên trong callback `Function.apply`** không khai báo checked. Tập exception cho phép được xét theo phương thức của target functional interface.

### 18.3. “Khi `Stream.map` chứa I/O thì Java tự chuyển checked thành unchecked”

Sai. Compiler từ chối callback chưa xử lý checked exception. Chỉ khi bạn hoặc chính API cụ thể chủ động wrapper thì kiểu unchecked xuất hiện.

### 18.4. “Dùng `Function<T,R>` với `throws E` ở generic type argument”

Sai. `Function` chuẩn chỉ có hai type parameters T/R; không có parameter kiểu ngoại lệ. Không thể viết `Function<T,R,IOException>`.

### 18.5. “Method reference được miễn quy tắc `throws`”

Sai. `Files::readString` chịu kiểm tra checked exception theo target tương tự lambda gọi `Files.readString(path)`.

### 18.6. “Bọc mọi exception thành unchecked là luôn tốt”

Không. Nó thay đổi hợp đồng của caller và có thể che phân loại lỗi. Chỉ dùng khi đúng kiến trúc và giữ cause, không biến mọi failure thành một kiểu vô nghĩa.

### 18.7. “`UncheckedIOException` dùng cho mọi checked exception”

Sai. Constructor của `UncheckedIOException` dành cho `IOException`. Với `SQLException` hoặc exception checked khác, chọn wrapper/thiết kế khác phù hợp.

### 18.8. “`Callable` có thể truyền trực tiếp cho `Supplier`”

Sai. Hai interface độc lập, dù đều trả giá trị. Chữ ký abstract method khác nhau: `get()` vs `call() throws Exception`. Cần adapter với chính sách exception rõ ràng nếu muốn chuyển.

### 18.9. “Chuyển sang `parallelStream` sẽ tự giải quyết IOException”

Sai. Parallel không thay target method `Function.apply`/`Consumer.accept`. Nó còn làm side effect và thứ tự xử lý khó suy luận hơn.

### 18.10. “Ngoại lệ trong `map` xuất hiện ngay khi viết `map(...)`”

Không nhất thiết. Stream thường lazy: callback được gọi khi terminal operation chạy. Hãy đặt handler ở phạm vi chứa **thao tác thực sự tiêu thụ pipeline**.

### 18.11. “Có `catch` nên mọi trạng thái trước đó đã rollback”

Sai. Nếu Consumer thực hiện ghi/xóa file trước khi lỗi xảy ra, những side effect trước đó không tự bị hoàn tác. Checked/unchecked chỉ là hợp đồng báo lỗi, không phải transaction.

### 18.12. “Bắt rồi trả `null` là trung lập”

Sai. `null` có thể bị hiểu là dữ liệu hợp lệ, gây `NullPointerException` ở vị trí xa lỗi gốc hoặc mất thông tin chẩn đoán. Dùng result có cấu trúc, fallback hợp lệ hoặc lan failure.

## 19. Câu hỏi thường gặp

### 19.1. Tại sao các interface chuẩn không thêm `throws Exception` cho thuận tiện?

Đó là lựa chọn API của thư viện chuẩn: phần lớn callback thông dụng được thiết kế để không ép mọi caller phải xử lý checked `Exception` rộng. Nếu `Function.apply` khai báo `throws Exception`, vô số API và code dùng nó sẽ phải thay chữ ký/bắt lỗi, kể cả khi callback không bao giờ làm I/O.

Điều đó có lợi cho nhiều thao tác thuần nhưng bất tiện khi tác vụ callback có checked failures; Java cho phép tạo functional interface chuyên biệt khi cần.

### 19.2. Có thể viết `try/catch` ở ngoài `stream.map(...)` không?

Chỉ `try/catch` bên ngoài **không khắc phục lỗi compile-time của lambda** nếu lambda còn để checked exception thoát. Trước tiên lambda phải hợp lệ với `Function.apply` bằng cách tự xử lý, chuyển sang unchecked hoặc dùng API khác. Sau đó bên ngoài có thể bắt wrapper unchecked khi terminal operation chạy.

### 19.3. Có thể gắn `throws IOException` lên chính lambda không?

Lambda expression của Java không có cú pháp khai báo `throws` như một method declaration độc lập. Nó nhận khả năng checked `throws` từ phương thức trừu tượng của functional interface target.

### 19.4. Làm sao giữ stack trace và nguyên nhân?

Bọc lỗi bằng constructor nhận cause, ví dụ `new UncheckedIOException("...", e)` hoặc `new RuntimeException("...", e)`, rồi log Throwable tại boundary. Đừng chỉ giữ message hoặc thay lỗi gốc bằng một message mới.

### 19.5. `ThrowingFunction` có phải chuẩn JDK không?

Không. Đây là tên custom thường gặp; dự án có thể định nghĩa riêng hoặc sử dụng thư viện hỗ trợ. Cần đọc hợp đồng cụ thể nếu dùng thư viện bên thứ ba, vì một số adapter có cách bọc lỗi khác nhau.

### 19.6. Dùng `Supplier` cho lazy I/O có nguy hiểm gì?

Đôi khi caller gọi `get()` nhiều lần, có thể mở resource nhiều lần hoặc kích hoạt nhiều lần side effect. `Supplier` **không** hứa memoization. Nếu cần cache kết quả, phải xây chính sách caching và vòng đời resource riêng.

### 19.7. Khi nào nên dùng `Callable`?

Khi API thực sự nhận `Callable` hoặc tác vụ có contract `call() throws Exception` phù hợp. Đừng dùng `Callable` chỉ vì muốn nhét callback vào `Stream.map`, vì kiểu đầu vào của `map` là `Function`.

## 20. Bài tập tự luyện

### Bài 1 — Xác định compile error

Đọc ba ví dụ `InvalidFunction`, `InvalidConsumer` và `InvalidSupplier`. Với từng ví dụ, viết rõ **phương thức đích** và API nào khai báo checked `IOException`. Giải thích vì sao phương thức bao ngoài `throws IOException` không giải quyết được.

### Bài 2 — Thay target type

Từ method `loadLength(String) throws IOException`, thử gán method reference cho `Function<String,Integer>` và `ThrowingFunction<String,Integer,IOException>`. Chỉ ra bản nào biên dịch và vì sao.

### Bài 3 — Fallback hay error signal?

Trong `FunctionCatchInsideDemo`, giả sử giá trị `-1` cũng là một length hợp lệ trong mô hình mới. Hãy thay bằng một result type có trạng thái thành công/thất bại rõ ràng, hoặc để lỗi lan theo một callback có checked `throws`.

### Bài 4 — Wrapper và cause

Trong `UncheckedFunctionAdapterDemo`, thay `new UncheckedIOException("...", e)` bằng `new RuntimeException(e.getMessage())`. Caller còn lấy được IOException gốc qua `getCause()` không? Vì sao đây là regression về chẩn đoán?

### Bài 5 — Tiếp tục hay dừng batch?

Chạy `ConsumerFailurePolicyDemo`. Chuyển handler từ in `FAILED` sang ném `UncheckedIOException` để cả vòng lặp dừng tại phần tử `"bad"`. Dự đoán dòng `OK: two` có còn xuất hiện không. Mô tả cách báo batch failure cho caller.

### Bài 6 — Dùng Callable

Chạy `CallableVsSupplierDemo`. Thay `Callable` bằng `Supplier` rồi để lambda trực tiếp gọi `load(true)`. Compiler báo vấn đề gì? Hãy so sánh `Callable.call` và `Supplier.get`.

### Bài 7 — Stream lazy

Tạo `Stream<String>` với `map` dùng một `Function` in “mapping X” rồi trả kết quả. Không chạy terminal operation, quan sát callback chưa được thực hiện. Thêm `toList()` và giải thích thời điểm callback chạy.

### Bài 8 — Loop thay stream

Viết method `readAll(List<Path>) throws IOException` bằng vòng lặp, sau đó thử cùng logic bằng `stream().map(Files::readString).toList()`. So sánh khả năng compile, hợp đồng của caller và cách bảo toàn IOException khi muốn truyền trực tiếp.

### Bài 9 — Exception trong CompletableFuture

Dùng `CompletableFuture.supplyAsync` với supplier bọc IOException thành UncheckedIOException. Dùng `join()` và quan sát `CompletionException`/cause chain theo hợp đồng API. Phân biệt wrapper của callback với wrapper của future.

### Bài 10 — Quản lý tài nguyên

Dùng `try-with-resources` trong callback để mở reader, đọc xong rồi đóng. Nếu callback trả một Stream lazy đọc từ cùng reader, hãy giải thích vì sao đóng resource trước khi stream được tiêu thụ là lỗi thiết kế ownership.

## 21. Checklist trước khi dùng lambda có I/O/SQL

- [ ] Tôi đã xác định callback target là `Function`, `Consumer`, `Supplier` hay interface khác chưa?
- [ ] Tôi đã đọc chữ ký **phương thức trừu tượng** của target, có `throws` checked không?
- [ ] Tôi không kỳ vọng `throws IOException` ở method bao ngoài tự sửa lambda sai contract chứ?
- [ ] Tôi phân biệt lambda với method reference: cả hai tuân theo target checked throws?
- [ ] Khi dùng `Stream.map`, tôi biết lambda thường chạy lúc terminal operation chứ?
- [ ] Nếu bắt ngay trong lambda, tôi có chính sách phục hồi/fallback thực sự thay vì che lỗi không?
- [ ] Nếu bọc unchecked, tôi có giữ cause và không bọc thừa RuntimeException không?
- [ ] Tôi đã chọn đúng `UncheckedIOException` chỉ cho IOException chưa?
- [ ] Nếu tự định nghĩa `ThrowingFunction<T,R,E>`, API nhận callback có công bố `throws E` đầy đủ không?
- [ ] Tôi nhớ custom `ThrowingFunction` không truyền trực tiếp vào `Stream.map` nếu thiếu adapter chứ?
- [ ] Tôi có cân nhắc một vòng lặp thường để giữ checked IOException minh bạch không?
- [ ] Với `Consumer` có side effect, tôi biết trạng thái của các phần tử đã xử lý khi lỗi không?
- [ ] Với `Supplier`, tôi biết `get()` có thể được gọi nhiều lần và chưa chắc memoize không?
- [ ] Tôi có phân biệt `Supplier.get` với `Callable.call throws Exception` không?
- [ ] Khi dùng future, tôi xem đúng hợp đồng exception của `join()`/`get()` không?
- [ ] Resource mở trong lambda có được đóng đúng lúc, đặc biệt với stream lazy không?
- [ ] Tôi đã test đường thành công, checked failure, wrapper cause và side effect sau lỗi chưa?

**Kết luận:** `Function.apply`, `Consumer.accept` và `Supplier.get` **không có checked `throws`**, nên lambda/method reference gán cho chúng không được để checked exception thoát trực tiếp. Có ba hướng giải quyết rõ nghĩa: **bắt và xử lý trong callback**, **chuyển sang unchecked wrapper có cause**, hoặc **chọn/tạo callback API khai báo `throws`**; khi cần, vòng lặp `for` thường giúp hợp đồng checked I/O sáng sủa hơn. Sự khác biệt nằm ở **chữ ký của functional interface**, không phải một hạn chế chung của cú pháp lambda Java.