# Functional interface riêng có `throws` khi thật sự cần trong Java

## 1. Vấn đề: lambda và checked exception

Lambda Java được kiểm tra theo kiểu đích (functional interface) của nó. Các interface chuẩn như `Function<T,R>`, `Consumer<T>`, `Predicate<T>`, `Supplier<T>` thuộc `java.util.function` có phương thức trừu tượng duy nhất (SAM) **không khai báo checked exception**.

Khi logic cần đọc file, gọi API JDBC, xử lý network I/O hoặc dùng một dịch vụ có `throws IOException`/`SQLException`, nhiều lambda đơn giản không còn biên dịch nếu truyền trực tiếp vào những interface đó. Có thể catch tại chỗ, chuyển lỗi có chủ đích, hoặc — **khi hợp đồng callback cần giữ checked exception** — tạo functional interface riêng có `throws`.

Mục tiêu bài này:

- Nhận biết giới hạn `throws` của SAM chuẩn và nguyên nhân lỗi biên dịch.
- Thiết kế `ThrowingFunction<T,R,E extends Exception>` và `ThrowingConsumer<T,E extends Exception>` đúng quy tắc một SAM.
- Truyền checked exception xuyên qua API nhận callback mà không mất cause.
- Biết khi nào dùng method bình thường, `try/catch` trong lambda, adapter `UncheckedIOException`, hay kiểu kết quả biểu diễn cả thành công và lỗi.
- Hiểu điểm khác nhau khi dùng helper tuần tự và các API như `Stream.map`.
- Tránh lạm dụng functional interface riêng, che ngoại lệ, quên đóng resource hoặc tạo side effect không kiểm soát.

Các ví dụ độc lập dùng **Java 17 trở lên**.

## 2. Kiến thức nền: checked và unchecked exception

### 2.1. Checked exception là một phần chữ ký được compiler kiểm tra

`IOException` và `SQLException` là checked exceptions: chúng kế thừa `Exception` nhưng không thuộc nhánh `RuntimeException`. Đường đi code có khả năng ném checked exception phải được **catch** hoặc **khai báo tiếp bằng `throws`** theo luật Java.

Ví dụ trong class có import `java.io.BufferedReader` và `java.io.IOException`:

~~~java
static String firstLine(BufferedReader reader) throws IOException {
    return reader.readLine();
}
~~~

`BufferedReader.readLine()` khai báo `throws IOException`, nên method phía trên có thể chuyển lỗi lên caller. Không cần bắt lỗi tại tầng không biết xử lý thế nào.

Unchecked exceptions gồm các subclass của `RuntimeException` như `IllegalArgumentException`, `NullPointerException` và `UncheckedIOException`; các subclass của `Error` cũng không chịu quy tắc checked exception tương tự. “Unchecked” không có nghĩa là an toàn, có thể bỏ qua hay không cần log.

### 2.2. Vì sao `Function` không chấp nhận lambda có `IOException`?

Phương thức trừu tượng của `Function<T,R>` là:

~~~java
R apply(T input);
~~~

Nó **không khai báo `throws IOException`**. Vì thế đoạn sau là **mã lỗi có chủ đích**:

~~~java
Function<BufferedReader, String> read =
        reader -> reader.readLine(); // Unhandled IOException
~~~

Đoạn này không biên dịch, cho dù phương thức bao ngoài có `throws IOException`. Compiler kiểm tra thân lambda dựa trên **throws clause của SAM target type**, không dựa duy nhất vào method chứa khai báo lambda.

So sánh với một cách xử lý hợp lệ khi API bắt buộc nhận `Function`:

~~~java
Function<BufferedReader, String> read = reader -> {
    try {
        return reader.readLine();
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
};
~~~

`UncheckedIOException` là wrapper cho nguyên nhân kiểu `IOException`; caller có thể dùng `getCause()`. Đây là **quyết định chính sách lỗi**, không phải lối sửa bắt buộc. Nếu nghiệp vụ có thể phục hồi hoặc yêu cầu checked exception giữ nguyên, cần chọn cách khác.

## 3. Khi nào thật sự cần functional interface riêng có `throws`?

Chỉ nên tạo khi đồng thời có các nhu cầu thực chất:

1. **Cần truyền hành vi** dưới dạng lambda/method reference cho một API do bạn kiểm soát.
2. Hành vi đó hợp lệ khi ném **một loại checked exception**; loại lỗi là thành phần hợp đồng, không phải sự cố cần che giấu.
3. **Nơi nhận callback có thể truyền ngoại lệ lên** tầng gọi; caller biết chọn retry, báo lỗi, bỏ qua, rollback hoặc dừng tác vụ.

Một API dùng để đọc và chuyển đổi nhiều tài liệu theo callback là tình huống phù hợp. Caller muốn biết `IOException` xuất hiện ở đâu; helper không có đủ ngữ cảnh để luôn chuyển thành `"UNKNOWN"` hoặc nuốt ngoại lệ.

**Không cần tạo interface riêng** nếu phép tính không ném checked exception; thao tác chỉ được gọi ở một method thường `throws IOException`; đã có callback chuyên dụng phù hợp; hoặc lỗi đã được giải quyết đúng ở biên hiện tại. Đừng nhân bản toàn bộ `java.util.function` với hậu tố `Throwing` chỉ để “phòng xa”.

| Nhu cầu | Giải pháp thường phù hợp |
| --- | --- |
| Biến đổi dữ liệu thuần | `Function` tiêu chuẩn |
| Ghi log hay side effect không có checked exception | `Consumer` tiêu chuẩn |
| Một method đọc file được gọi trực tiếp | Method thường `throws IOException` |
| Helper nhận callback I/O và phải giữ checked error | `ThrowingFunction`/`ThrowingConsumer` |
| Stream cần `Function` mà thao tác ném `IOException` | Adapter catch/wrap có chủ đích hoặc tổ chức lại |
| Muốn báo lỗi từng item nhưng vẫn xử lý item khác | Kiểu `Result`/`Outcome` hoặc catch trong vòng lặp |

## 4. Tự định nghĩa `ThrowingFunction`

~~~java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}
~~~

Giải nghĩa:

- `T`: kiểu đầu vào.
- `R`: kiểu kết quả.
- `E`: kiểu ngoại lệ khai báo, có bound `extends Exception`.
- `throws E` trên SAM: callback được phép ném loại ngoại lệ đó, caller xử lý theo luật checked exception.
- `@FunctionalInterface`: compiler kiểm tra interface có đúng một hợp đồng trừu tượng theo quy tắc SAM.

Ví dụ:

~~~java
ThrowingFunction<BufferedReader, String, IOException> read =
        BufferedReader::readLine;
~~~

Đây là mảnh mã với import phù hợp. Method reference có chữ ký tương thích `String apply(BufferedReader) throws IOException`. Khi gọi `read.apply(reader)`, compiler yêu cầu nơi gọi catch hoặc khai báo `IOException`.

Một biến thể chuyên cho I/O, thường dễ hiểu nếu API chỉ làm I/O:

~~~java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T input) throws IOException;
}
~~~

Giữa generic `throws E` và `throws IOException` cụ thể, hãy chọn **hợp đồng nhỏ và rõ nhất** mà ứng dụng cần. Generic có lợi cho helper tái sử dụng; loại lỗi cố định thường dễ đọc và dễ catch.

### `throws E` cho phép chứ không bắt buộc ném ngoại lệ

~~~java
ThrowingFunction<String, Integer, IOException> length =
        String::length;
~~~

Ví dụ hợp lệ dù `String.length()` không thực sự ném `IOException`. Kiểu tĩnh vẫn thông báo rằng lời gọi `length.apply(...)` **có thể** ném checked exception; caller phải thực hiện nghĩa vụ xử lý theo chữ ký. Đây là lý do không nên biến mọi helper thành “throwing” theo mặc định.

Một interface có thể có các method `default`, `static` hoặc `private` đã có thân mà vẫn giữ một SAM; đừng thêm phương thức trừu tượng thứ hai rồi kỳ vọng lambda còn hợp lệ.

## 5. `ThrowingConsumer` và các chữ ký liên quan

Nếu hành động **không trả kết quả** nhưng có thể ném checked exception:

~~~java
@FunctionalInterface
interface ThrowingConsumer<T, E extends Exception> {
    void accept(T input) throws E;
}
~~~

Ví dụ gọi `Writer.write`:

~~~java
ThrowingConsumer<String, IOException> write =
        text -> writer.write(text);
~~~

Đây là mảnh mã cần biến `writer` kiểu `java.io.Writer` đã khởi tạo và ở trong phạm vi. Lambda có thể ném `IOException`, nên nơi thực thi callback phải bắt hoặc khai báo lỗi này. Việc tạo lambda **không tự đóng resource**; nơi sở hữu `writer` cần quản lý vòng đời bằng `try-with-resources` hoặc cơ chế tương đương.

Khi thật sự cần thêm dạng không nhận tham số, có thể thiết kế:

~~~java
@FunctionalInterface
interface ThrowingSupplier<T, E extends Exception> {
    T get() throws E;
}

@FunctionalInterface
interface ThrowingRunnable<E extends Exception> {
    void run() throws E;
}
~~~

Đừng thêm những interface này vào mọi module nếu không có use case. Định nghĩa chức năng là một hợp đồng API cần được bảo trì, nên chỉ giữ các biến thể có giá trị rõ.

## 6. Helper `mapChecked`: giữ checked exception đến caller

~~~java
static <T, R, E extends Exception> List<R> mapChecked(
        List<T> inputs,
        ThrowingFunction<? super T, ? extends R, E> mapper)
        throws E {

    Objects.requireNonNull(inputs, "inputs");
    Objects.requireNonNull(mapper, "mapper");

    List<R> output = new ArrayList<>();
    for (T item : inputs) {
        output.add(mapper.apply(item));
    }
    return output;
}
~~~

Đây là method đặt trong class có import `java.util.List`, `ArrayList` và `Objects`.

- `? super T` nghĩa callback có thể nhận một kiểu thích hợp rộng bằng hoặc hơn `T`.
- `? extends R` cho phép callback tạo ra kết quả là subtype của `R`.
- `throws E` trên helper biểu thị rằng lỗi checked từ callback được **chuyển tiếp**, không biến mất.
- Vòng lặp tuần tự xử lý từng item; nếu `mapper.apply` ném ngoại lệ, việc xử lý ngừng ở item đó và method không trả list kết quả bình thường.
- Side effect đã xảy ra với item trước đó **không được tự động rollback**.

Caller có thể viết:

~~~java
try {
    List<String> result = mapChecked(paths, path -> Files.readString(path));
    System.out.println(result);
} catch (IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

Đây là đoạn minh họa trong method với `paths` là `List<Path>` và import `java.nio.file.Files`, `IOException`; cú pháp và suy luận kiểu phù hợp khi type inference xác định `E=IOException`. Trong code sản xuất, cần log đầy đủ đường dẫn, nguyên nhân lỗi và quyết định tiếp tục hay dừng. Catch lỗi rồi chỉ in message không phải chiến lược xử lý đủ cho mọi yêu cầu.

### `forEachChecked` cho hành động `void`

~~~java
static <T, E extends Exception> void forEachChecked(
        Iterable<T> inputs,
        ThrowingConsumer<? super T, E> action)
        throws E {

    Objects.requireNonNull(inputs, "inputs");
    Objects.requireNonNull(action, "action");

    for (T item : inputs) {
        action.accept(item);
    }
}
~~~

`Iterable.forEach` của thư viện chuẩn nhận `Consumer<? super T>` **không khai báo checked exception**. Helper này biểu đạt khác biệt rõ ràng: callback được phép `throws E` và helper đẩy lỗi tới caller. Nó là cách duyệt tuần tự, không tạo concurrency hay transaction.

### Vì sao helper có `throws` vẫn chưa đủ nếu callback là `Function`?

~~~java
static <T, R> R execute(Function<T, R> fn, T value)
        throws IOException {
    return fn.apply(value);
}
~~~

Ví dụ này tự nó có thể biên dịch, nhưng việc helper `execute` khai báo `throws IOException` **không khiến lambda truyền vào `Function` được ném `IOException` chưa xử lý**. Quy tắc throws vẫn thuộc SAM `Function.apply`. Phải sửa target type, xử lý exception trong lambda hoặc viết adapter.

## 7. Adapter cho `Stream.map`: khi buộc phải dùng `Function`

`Stream.map` được định nghĩa nhận `Function<? super T, ? extends R>`; nó không tự chấp nhận `ThrowingFunction`. Nếu bạn chọn bọc `IOException` thành unchecked tại **ranh giới này**, hãy làm chính sách rõ ràng:

~~~java
static <T, R> Function<T, R> uncheckedIo(
        ThrowingFunction<T, R, IOException> operation) {

    Objects.requireNonNull(operation, "operation");

    return input -> {
        try {
            return operation.apply(input);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    };
}
~~~

Sau đó:

~~~java
List<String> cleaned = raw.stream()
        .map(uncheckedIo(MyClass::firstLine))
        .toList();
~~~

Đây là mảnh mã: `MyClass` là class có `firstLine(String) throws IOException`, `raw` là `List<String>`. Adapter tạo một `Function` thỏa chữ ký của Stream. `IOException` từ callback được bọc trong `UncheckedIOException`, và `getCause()` vẫn là lỗi I/O gốc. Bởi chỉ catch `IOException`, adapter không “nuốt” `RuntimeException`, `Error` hay những lỗi khác.

**Không dùng `UncheckedIOException` để bọc tùy tiện `SQLException` hoặc mọi `Exception`**: constructor nhận cause là `IOException`. Với lỗi khác, cần kiểu wrapper hoặc chiến lược riêng và bảo toàn cause.

### Stream là lazy, nên đặt catch đúng thời điểm

~~~java
var pipeline = raw.stream()
        .map(uncheckedIo(MyClass::firstLine));
~~~

Việc tạo pipeline trung gian `map` thường chưa gọi lambda. Checked exception đã được chuyển thành unchecked, nhưng **ngoại lệ có thể xuất hiện tại terminal operation** như `toList()`, `collect(...)` hoặc `forEach(...)`. Vì thế, vùng `try/catch` phải bao quanh điểm thực thi pipeline, không chỉ dòng khởi tạo.

Nếu một phần tử gây lỗi, các phần tử trước có thể đã thực hiện side effect; việc bọc lỗi không rollback bất kỳ thao tác nào. Với Stream song song, thứ tự và số lượng tác vụ đã bắt đầu trước khi lỗi lan ra càng cần được xem xét. Không đặt tác vụ nghiệp vụ bắt buộc trong `peek` rồi giả định nó chạy đúng một lần.

## 8. Chương trình Java 17 hoàn chỉnh

Ví dụ dùng `BufferedReader` trên dữ liệu `StringReader` trong bộ nhớ nên **không cần file thật**. `BufferedReader.readLine()` vẫn có khai báo `throws IOException`; một kiểm tra dòng trống tạo nhánh IOException có thể kiểm thử chắc chắn.

Tạo tệp **`CheckedFunctionsDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Function;

public class CheckedFunctionsDemo {

    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T input) throws E;
    }

    @FunctionalInterface
    interface ThrowingConsumer<T, E extends Exception> {
        void accept(T input) throws E;
    }

    static <T, R, E extends Exception> List<R> mapChecked(
            List<T> inputs,
            ThrowingFunction<? super T, ? extends R, E> mapper)
            throws E {

        Objects.requireNonNull(inputs, "inputs");
        Objects.requireNonNull(mapper, "mapper");

        List<R> output = new ArrayList<>();
        for (T item : inputs) {
            output.add(mapper.apply(item));
        }
        return output;
    }

    static <T, E extends Exception> void forEachChecked(
            Iterable<T> inputs,
            ThrowingConsumer<? super T, E> action)
            throws E {

        Objects.requireNonNull(inputs, "inputs");
        Objects.requireNonNull(action, "action");

        for (T item : inputs) {
            action.accept(item);
        }
    }

    static <T, R> Function<T, R> uncheckedIo(
            ThrowingFunction<T, R, IOException> operation) {

        Objects.requireNonNull(operation, "operation");

        return input -> {
            try {
                return operation.apply(input);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static String firstLine(String input) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(input))) {

            String first = reader.readLine();
            if (first == null || first.isBlank()) {
                throw new IOException("empty first line");
            }

            return first.strip().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws IOException {
        List<String> raw = List.of(
                "  java\nignore",
                "  lambda\nignore"
        );

        // Giữ checked exception qua helper.
        System.out.println(
                mapChecked(raw, CheckedFunctionsDemo::firstLine)
        );

        // ThrowingConsumer cho hành động không trả giá trị.
        List<String> labels = new ArrayList<>();
        forEachChecked(raw, value -> labels.add(firstLine(value)));
        System.out.println(labels);

        // Stream buộc nhận Function: chuyển sang unchecked ở biên.
        System.out.println(raw.stream()
                .map(uncheckedIo(CheckedFunctionsDemo::firstLine))
                .toList());

        // IOException trực tiếp từ helper.
        try {
            mapChecked(
                    List.of("okay", "  \nnext"),
                    CheckedFunctionsDemo::firstLine
            );
        } catch (IOException ex) {
            System.out.println("caught: " + ex.getMessage());
        }

        // IOException nằm trong wrapper từ Stream.
        try {
            List.of("  ").stream()
                    .map(uncheckedIo(CheckedFunctionsDemo::firstLine))
                    .toList();
        } catch (UncheckedIOException ex) {
            System.out.println(
                    "wrapped: " + ex.getCause().getMessage()
            );
        }
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 CheckedFunctionsDemo.java
java CheckedFunctionsDemo
~~~

**Stdout chính xác:**

~~~text
[JAVA, LAMBDA]
[JAVA, LAMBDA]
[JAVA, LAMBDA]
caught: empty first line
wrapped: empty first line
~~~

Diễn giải kết quả:

1. `mapChecked` nhận method reference `firstLine`, chuyển chuỗi `"  java\nignore"` và `"  lambda\nignore"` thành `[JAVA, LAMBDA]`.
2. `forEachChecked` chạy lambda có thể ném `IOException`, thêm hai kết quả vào list. `List.add` trả boolean nhưng lambda tương thích với `void`; giá trị boolean được bỏ qua.
3. Adapter `uncheckedIo` giúp Stream nhận lambda thông qua `Function` chuẩn; dữ liệu hợp lệ trả list tương tự.
4. Dòng đầu `"  "` là `isBlank()`, nên `firstLine` ném `IOException("empty first line")`. `mapChecked` truyền nó ra và caller bắt trực tiếp.
5. Trong Stream, cùng lỗi đó được adapter bọc thành `UncheckedIOException`; `getCause()` cho phép truy cập `IOException` gốc.

`main` khai báo `throws IOException` để các lời gọi helper đầu tiên tuân thủ hợp đồng checked exception, dù dữ liệu minh họa hợp lệ. Với ứng dụng thực, biên xử lý phù hợp thường sẽ catch và xử lý, thay vì chỉ để lỗi kết thúc chương trình.

### Resource và `try-with-resources`

`firstLine` mở `BufferedReader` và đóng tự động khi hoàn tất hoặc ném exception. Đối với file, socket hay database thật, việc đóng resource phải thuộc về **nơi sở hữu resource**, không được mặc định một lambda tự giải quyết. `try-with-resources` cũng hỗ trợ ghi nhận lỗi khi đóng dưới dạng **suppressed exceptions**; khi cần phân tích, dùng `Throwable.getSuppressed()` bên cạnh cause/stack trace. Ví dụ dùng `StringReader` không gây phụ thuộc dữ liệu bên ngoài nhưng vẫn minh họa chính xác hợp đồng `readLine() throws IOException`.

## 9. Các lựa chọn thay cho functional interface riêng

### 9.1. Catch và phục hồi có ý nghĩa

~~~java
Function<String, String> convert = value -> {
    try {
        return service.convert(value);
    } catch (SomeCheckedException ex) {
        return "UNKNOWN";
    }
};
~~~

Đây là **mẫu không chạy độc lập**: `service`/`SomeCheckedException` chỉ đại diện API thật. Chỉ dùng fallback `"UNKNOWN"` khi nó là quyết định nghiệp vụ đúng. Không biến mọi I/O error thành kết quả rỗng hoặc `null`, vì caller có thể hiểu nhầm lỗi là dữ liệu hợp lệ.

### 9.2. Method thường có `throws`

~~~java
static String load(Path file) throws IOException {
    return Files.readString(file);
}
~~~

Đây là method minh họa cần import `Path`/`Files`. Nếu chỉ gọi method trực tiếp và không có nhu cầu truyền callback, **không có lý do bắt buộc** phải tạo `ThrowingFunction<Path,String,IOException>`.

### 9.3. Wrapper lỗi khi buộc dùng API tiêu chuẩn

~~~java
Function<Path, String> load = file -> {
    try {
        return Files.readString(file);
    } catch (IOException ex) {
        throw new UncheckedIOException(
                "Cannot read: " + file, ex);
    }
};
~~~

Đoạn minh họa dùng `Function` chuẩn, giữ cause và bổ sung đường dẫn ngữ cảnh. Việc wrap làm lỗi được lan truyền dưới dạng unchecked; nó **không biến lỗi thành thành công**. Cần xác định caller sẽ bắt loại wrapper ở tầng nào.

### 9.4. Lỗi như dữ liệu nếu muốn xử lý mọi phần tử

Khi cần xử lý 100 file và thu được cả lỗi từng file, helper fail-fast ném ngoại lệ đầu tiên có thể không phù hợp. Có thể trả một kiểu dữ liệu chứa trạng thái:

~~~java
record ReadOutcome(String file, String text, IOException error) {
    boolean success() {
        return error == null;
    }
}
~~~

Đây là **record minh họa**, chưa áp đặt invariant. Thiết kế thật cần phân biệt rõ nhánh thành công/lỗi (ví dụ sealed type), không để vừa có text vừa có error mơ hồ. Mỗi phần tử trả `ReadOutcome` giúp tích lũy, báo cáo, thử lại các lỗi có chọn lọc và tránh mất ngữ cảnh đường dẫn.

### Bảng so sánh

| Phương án | Loại lỗi thấy ở caller | Phù hợp khi |
| --- | --- | --- |
| Catch tại lambda chuẩn | Fallback, log hoặc wrapper theo chính sách | Tầng hiện tại có đủ ngữ cảnh |
| Custom functional interface `throws E` | Checked exception `E` | API cần callback và truyền lỗi tường minh |
| `UncheckedIOException` adapter | Unchecked wrapper với `IOException` làm cause | Biên Stream/`Function` bắt buộc |
| Trả kết quả có trạng thái | Lỗi trở thành dữ liệu | Xử lý tiếp các mục còn lại, báo nhiều lỗi |
| Method bình thường `throws IOException` | Checked exception trực tiếp | Không cần truyền hành vi qua API |

## 10. Những lỗi phổ biến

| Sai lầm | Vì sao sai hoặc rủi ro | Khắc phục |
| --- | --- | --- |
| Cho rằng `throws` trên method ngoài sửa được SAM của `Function` | Kiểm tra checked exception dựa trên target type | Dùng interface đúng hoặc catch trong lambda |
| Tạo mọi callback thành `ThrowingFunction` | Caller có thể phải xử lý checked error vô ích | Chỉ dùng khi hợp đồng cần |
| Bắt `Exception` rồi trả `null` vô điều kiện | Mất nguyên nhân và che lỗi dữ liệu | Chỉ fallback khi hợp đồng cho phép |
| Bọc bằng `new RuntimeException()` không có cause | Mất chuỗi nguyên nhân để debug | Bọc với cause và ngữ cảnh |
| Dùng `UncheckedIOException` cho mọi checked exception | Constructor yêu cầu cause `IOException` | Dùng loại wrapper hoặc thiết kế phù hợp |
| Nghĩ `Stream.map` chạy ngay | Pipeline trung gian thường lazy | Đặt catch quanh terminal operation |
| Nghĩ helper tự rollback khi lỗi | Side effect trước lỗi vẫn tồn tại | Transaction/compensation theo nghiệp vụ |
| Quên đóng resource | Rò rỉ handle/connection | `try-with-resources` đúng phạm vi |
| Dùng `sneaky throws` để vượt qua compiler | Che giấu checked exception trong hợp đồng | Truyền lỗi rõ hoặc wrap có chủ đích |
| Nuốt `InterruptedException` | Mất tín hiệu yêu cầu dừng | Propagate hoặc restore interrupt khi cần |
| Dùng raw `Function`/ép kiểu không kiểm soát | Mất type safety | Dùng generic đầy đủ |
| Cho rằng `@FunctionalInterface` cho phép hai SAM | Annotation chỉ kiểm tra SAM | Giữ đúng một abstract method |

### `InterruptedException` cần xử lý riêng

Một callback làm việc với blocking operation có thể ném `InterruptedException`. Nếu tầng xử lý **không thể truyền checked exception lên** và phải chuyển kiểu lỗi, thường cần khôi phục interrupt bằng `Thread.currentThread().interrupt()` trước khi thoát, theo hợp đồng API thực tế. Không catch rộng rồi bỏ qua tín hiệu hủy của thread.

### Generic `E` không phải cách “lách” compiler

`E extends Exception` và `throws E` giúp mô tả một **hợp đồng lỗi**, không phải lý do để dùng thủ thuật `sneakyThrow` che loại ngoại lệ khỏi caller. Nếu một callback có thể ném nhiều checked exception khác loại, compiler có thể suy luận một supertype rộng như `Exception`; khi đó người gọi phải xử lý loại rộng. Nếu API chỉ cần lỗi I/O, dùng chữ ký cụ thể `throws IOException` có thể dễ sử dụng và an toàn về nghĩa hơn.

### Vấn đề thứ tự, concurrency và tính nguyên tử

`mapChecked` của bài chạy tuần tự. Nó không cam kết rollback side effect; `Stream.parallel()` càng không cam kết xử lý theo thứ tự thông thường hoặc shared mutable state được đồng bộ an toàn. Việc convert checked sang unchecked không giải quyết concurrency. Nếu callback có tác động như gửi email, ghi tiền hay cập nhật database, phải thiết kế retry, idempotency và transaction riêng.

## 11. Checklist thiết kế API nhận callback có ngoại lệ

Trước khi tạo custom throwing functional interface, hãy tự kiểm:

1. Có thực sự **truyền lambda làm callback** hay chỉ cần method thường?
2. SAM tiêu chuẩn đã phù hợp chưa? Logic có checked exception thực sự hay chỉ có RuntimeException?
3. Loại checked exception nào phải giữ nguyên? `IOException`, `SQLException` hay loại miền?
4. Tầng nào biết cách xử lý và quyết định retry, rollback, bỏ qua hay báo lỗi?
5. Có thể dùng `try/catch` ngay ở lambda mà không làm mất ý nghĩa nghiệp vụ không?
6. Nếu cần Stream, adapter sẽ bọc lỗi kiểu gì, ở đâu sẽ catch wrapper và ai kiểm tra cause?
7. Resource được mở và đóng ở đâu, kể cả khi callback lỗi?
8. Nếu callback lỗi giữa chừng, side effect đã xảy ra trước đó được xử lý thế nào?
9. Caller cần **dừng ở lỗi đầu tiên** hay cần **tổng hợp lỗi trên nhiều phần tử**?
10. Generic `throws E` có làm API rộng và khó suy luận hơn mức cần thiết không?
11. Có nguy cơ che `InterruptedException` hoặc các tín hiệu dừng không?
12. Test đã bao phủ cả đường thành công, lỗi checked, wrapper và case resource chưa?

Một API tốt không phải API “không bao giờ ném lỗi”; nó làm **đường đi của lỗi và trách nhiệm xử lý được nhìn thấy rõ**.

## 12. Bài tập tự luyện

**Bài 1 — Tạo `ThrowingSupplier`.** Định nghĩa `T get() throws E` với `E extends Exception`. Viết method dùng callback để đọc một dòng từ `BufferedReader` và chuyển tiếp `IOException`. So sánh với `Supplier<T>` không hỗ trợ checked exception.

**Bài 2 — Sửa lambda lỗi.** Cho:

~~~java
Function<Path, String> read =
        path -> Files.readString(path);
~~~

Hãy sửa (a) bằng `ThrowingFunction<Path,String,IOException>` và (b) bằng `Function` có `try/catch` chuyển `IOException` sang `UncheckedIOException`. Giải thích khác biệt ở caller.

**Bài 3 — Kiểm thử fail-fast.** Sử dụng `mapChecked` để đọc danh sách ba chuỗi, trong đó phần tử thứ hai có dòng đầu trống. Quan sát exception và lý giải tại sao phần tử thứ ba không được xử lý nếu helper không bắt lỗi.

**Bài 4 — Catch đúng điểm thực thi.** Tạo một Stream với `map(uncheckedIo(...))` nhưng chưa gọi terminal operation; sau đó thêm `toList()` trong `try/catch`. Kiểm tra rằng lỗi từ callback xuất hiện khi pipeline chạy chứ không bắt buộc ngay khi khai báo.

**Bài 5 — Callback viết file.** Viết `forEachChecked` cho `ThrowingConsumer<String,IOException>` dùng `Writer.write`. Đặt `try-with-resources` tại nơi sở hữu writer. Thử trường hợp callback ném lỗi và xác minh resource vẫn được đóng.

**Bài 6 — Giữ cause.** Tạo wrapper `new UncheckedIOException("read failed", original)`. Viết test kiểm tra `getCause() == original` và thông tin lỗi. So sánh với wrapper không truyền cause.

**Bài 7 — Tiếp tục xử lý sau lỗi.** Chọn cách biểu diễn thành công/lỗi cho từng tài liệu (record hoặc sealed interface), thay vì dừng ở lỗi đầu tiên. Giải thích cách giữ định danh tài liệu để retry những mục thất bại.

**Bài 8 — Khi không tạo interface mới.** Một ứng dụng có method `loadConfig(Path) throws IOException` được gọi đúng một nơi và không truyền làm callback. Giải thích vì sao method `throws` bình thường dễ hiểu hơn custom throwing interface; chỉ chuyển sang interface khi xuất hiện nhu cầu truyền hành vi và bảo toàn hợp đồng lỗi.

## 13. Câu hỏi tự kiểm tra

1. **Vì sao `Function<T,R>` không cho lambda ném `IOException` trực tiếp?** SAM `apply` không khai báo checked exception đó.
2. **Thêm `throws IOException` trên method chứa lambda có đủ không?** Không; compiler xét throws của SAM.
3. **`ThrowingFunction<T,R,E>` khác gì?** Có `throws E` tại SAM, cho phép truyền checked error.
4. **`ThrowingConsumer` làm gì?** Nhận một đầu vào, trả `void`, có thể ném checked exception đã khai báo.
5. **Khi nào không cần tạo interface riêng?** Khi không cần callback có checked exception hoặc method thường đủ dùng.
6. **Stream.map có nhận thẳng ThrowingFunction không?** Không; nó nhận `Function`. Cần adapter hoặc cách xử lý khác.
7. **Vì sao `uncheckedIo` chỉ catch `IOException`?** Vì `UncheckedIOException` được thiết kế cho IOException.
8. **Catch wrapper rồi muốn đọc lỗi gốc làm sao?** Dùng `getCause()`.
9. **Vì sao `try-with-resources` quan trọng?** Đóng resource ngay cả khi có lỗi, hỗ trợ suppressed exception.
10. **Có nên nuốt exception để compiler hết báo lỗi?** Không; phải có chính sách lỗi rõ ràng.
11. **Custom functional interface có `throws` làm lỗi biến mất không?** Không; nó đưa lỗi thành hợp đồng cho caller.
12. **Có nên tạo hàng chục biến thể throwing interface từ đầu?** Không, chỉ định nghĩa chữ ký thật sự được dùng.

## 14. Tổng kết và tài liệu tham khảo

**Functional interface riêng có `throws` nên được tạo khi checked exception là một phần thực sự của hợp đồng callback.** Với API tự kiểm soát, `ThrowingFunction`/`ThrowingConsumer` có thể giữ nguyên `IOException` hoặc checked exception miền và truyền lên nơi có đủ ngữ cảnh xử lý. Với API chỉ nhận `Function`/`Consumer` tiêu chuẩn, cần catch tại chỗ, adapter bọc lỗi có chủ đích, hoặc thiết kế lại ranh giới thao tác.

Mọi cách đều cần bảo toàn nguyên nhân lỗi, đóng resource phù hợp, tránh nuốt interrupt, xác định fail-fast hay gom lỗi, và xét tác dụng phụ trước khi retry. Nếu không có nhu cầu truyền hành vi bằng lambda, **method thường có `throws` thường là lựa chọn đơn giản hơn**.

Tài liệu chuẩn: Java Language Specification mục **`11 Exceptions`**, **`15.27 Lambda Expressions`**; Javadoc Java SE 17 của **`java.util.function.Function`**, **`Consumer`**, **`java.io.IOException`**, **`UncheckedIOException`**, **`java.io.BufferedReader`**, **`java.util.stream.Stream`** và **`AutoCloseable`**.
