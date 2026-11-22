# Ngoại lệ phát sinh từ mã Java, API hoặc JVM

## 1. Mục tiêu

Khi đọc stack trace, bạn thường thấy một tên ngoại lệ như `NullPointerException`, `NumberFormatException` hoặc `IOException`. Tên kiểu lỗi cho biết **điều gì đã được báo**, nhưng chưa đủ cho biết **ai hoặc cơ chế nào đã tạo ra lỗi đó**.

Sau bài này, bạn có thể:

- Phân biệt ba đường phát sinh thường gặp: mã ứng dụng chủ động `throw`, phương thức API báo thất bại, và JVM phát sinh ngoại lệ/lỗi khi thực thi.
- Xác định điểm ngoại lệ xuất hiện, cách nó lan truyền qua các phương thức, cách `catch` chọn handler và tác động tới `finally`.
- Giải thích vì sao một kiểu ngoại lệ có thể xuất hiện từ nhiều nguồn, đặc biệt là `NullPointerException` và `IllegalArgumentException`.
- Phân biệt checked exception, unchecked exception và `Error` dù nguồn phát sinh là gì.
- Viết và chạy ví dụ Java 17+, quan sát luồng thực thi và áp dụng cách chẩn đoán phù hợp.

> “Mã Java”, “API” và “JVM” là cách phân loại theo **nơi hoặc cơ chế báo lỗi**. Chúng không phải ba nhánh lớp độc lập trong hệ phân cấp `Throwable`. Một API cũng được viết bằng Java hoặc mã native, và JVM chạy cả mã ứng dụng lẫn mã API.

## 2. Nền tảng: ngoại lệ đi vào luồng thực thi như thế nào?

Trong Java, đối tượng được ném phải là `Throwable` hoặc lớp con của nó. Cấu trúc chính:

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── các checked exception (ví dụ IOException)
│   └── java.lang.RuntimeException
│       ├── IllegalArgumentException
│       │   └── NumberFormatException
│       ├── NullPointerException
│       └── IndexOutOfBoundsException
└── java.lang.Error
    ├── AssertionError
    ├── LinkageError
    └── VirtualMachineError
        ├── OutOfMemoryError
        └── StackOverflowError
```

Đây là **sơ đồ các lớp tiêu biểu**, không liệt kê toàn bộ hệ phân cấp. Những lớp trong nhánh `Error` không phải `Exception` dù đều có thể được ném. Trong Java, `RuntimeException` và `Error` cùng các lớp con thuộc nhóm *unchecked*; các lớp `Exception` khác không kế thừa `RuntimeException` thường là *checked* (trừ cách diễn đạt kỹ thuật chính xác hơn: mọi lớp con của `Throwable` không thuộc `RuntimeException` hoặc `Error` là checked).

Khi một biểu thức hoặc lời gọi phương thức hoàn thành đột ngột (*abrupt completion*) do ném ngoại lệ:

1. Phần còn lại của biểu thức/câu lệnh đang thực hiện không tiếp tục như bình thường.
2. JVM tìm handler `catch` có kiểu phù hợp trong các khối `try` bao quanh.
3. Nếu không có handler tại phương thức hiện tại, quá trình lan truyền ra phương thức gọi; các khối `finally` thích hợp được thực hiện trong quá trình thoát bình thường của stack.
4. Nếu không được bắt đến tận ranh giới thực thi của luồng, ngoại lệ có thể đến `UncaughtExceptionHandler`; luồng đó kết thúc. Điều này không nhất thiết làm mọi luồng hoặc cả JVM dừng ngay.

Nguồn phát sinh **không đổi cơ chế lan truyền**. Một `IllegalArgumentException` do bạn `throw` và một `IllegalArgumentException` được ném từ API đều đi qua cùng quy tắc chọn `catch`.

## 3. Ba nguồn phát sinh chính

| Nguồn | Điều gì tạo tín hiệu lỗi? | Ví dụ điển hình | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **Mã ứng dụng Java** | Lệnh `throw` do người lập trình viết khi điều kiện/bất biến không đạt | `throw new IllegalArgumentException("age < 0")` | Điều kiện kiểm tra, hợp đồng phương thức, dữ liệu đầu vào |
| **API/thư viện** | Phương thức được gọi báo thất bại theo hợp đồng của nó; nội bộ có thể dùng `throw` Java hoặc xử lý native | `Integer.parseInt("12x")` → `NumberFormatException`; `Files.readString(path)` có thể ném `IOException` | JavaDoc, tham số, trạng thái tài nguyên, `throws`, nguyên nhân gốc |
| **JVM khi thực thi** | Một thao tác ở mức ngôn ngữ/bytecode vi phạm điều kiện chạy hoặc VM không đáp ứng tài nguyên | Gọi phương thức trên `null` → `NullPointerException`; chia nguyên cho 0 → `ArithmeticException`; thiếu stack → `StackOverflowError` | Dòng mã/bytecode, giá trị tại thời điểm chạy, thông báo và trạng thái JVM |

**Lưu ý về ranh giới:** Không thể kết luận chắc “do JVM”, “do API” hay “do mã mình” **chỉ bằng tên lớp**. Ví dụ `NullPointerException` có thể do dereference `null` trong bytecode, do `Objects.requireNonNull(null)` trong API hoặc do lập trình viên tự `throw new NullPointerException()`. Stack trace, call site và hợp đồng API mới giúp xác định nguồn.

### 3.1. Ngoại lệ do mã Java chủ động ném

Cú pháp:

```java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
```

Đây là **mảnh mã minh họa bên trong phương thức**. Lệnh `throw` tạo một lối thoát đột ngột; câu lệnh sau đó trên cùng nhánh không chạy. Nếu một phương thức khai báo trả về giá trị, đường đi `throw` không cần trả về giá trị.

Chọn kiểu ngoại lệ để truyền đạt đúng hợp đồng:

- `IllegalArgumentException`: tham số không hợp lệ; một biến thể phổ biến là `NumberFormatException`.
- `IllegalStateException`: trạng thái hiện tại không cho phép thao tác.
- Checked exception tự định nghĩa hoặc có sẵn: bên gọi cần biết và được trình biên dịch buộc xử lý/khai báo nếu kiểu được ném là checked.
- Đừng dùng `Error` hoặc `OutOfMemoryError` để diễn đạt lỗi nghiệp vụ thông thường.

Lệnh `throw` có thể ném lại **cùng đối tượng đã bắt**:

```java
try {
    performWork();
} catch (IllegalStateException failure) {
    // Ghi nhận ngữ cảnh phù hợp, sau đó giữ nguyên ngoại lệ gốc.
    throw failure;
}
```

Đây là **mảnh mã minh họa**, `performWork()` không được định nghĩa trong đoạn này. Khi tạo ngoại lệ bọc bằng `new SomeException(message, cause)`, nên giữ nguyên `cause` để không mất chuỗi nguyên nhân.

### 3.2. Ngoại lệ do API hoặc thư viện Java báo

API có hợp đồng về dữ liệu hợp lệ và điều kiện thất bại. Các ví dụ:

```java
Integer.parseInt("12x");        // NumberFormatException
java.util.Objects.requireNonNull(null); // NullPointerException
java.util.List.of("a").get(3); // IndexOutOfBoundsException
```

Các dòng trên là **ví dụ riêng lẻ về lời gọi ném lỗi**, không phải một chương trình `main` hoàn chỉnh. `Integer.parseInt` phát hiện chuỗi không thể chuyển thành `int`; `Objects.requireNonNull` chủ động kiểm tra tham chiếu; `List.get` kiểm tra chỉ số. Đây là lỗi được báo theo **hợp đồng API**, kể cả khi loại ngoại lệ trùng với loại JVM có thể ném.

API cũng khai báo checked exception:

```java
String content = java.nio.file.Files.readString(path); // có thể ném IOException
```

Đây là **mảnh mã minh họa**; `path` phải là `java.nio.file.Path` được khởi tạo và câu lệnh phải được đặt trong khối xử lý `IOException` hoặc phương thức có `throws IOException`. Tùy filesystem và quyền truy cập, lời gọi có thể thành công hoặc báo một lớp con của `IOException`.

Đọc JavaDoc để xác định: phương thức nhận gì, ném loại nào, có kiểm tra tham số hay không, có phụ thuộc tệp/mạng/cấu hình/luồng hay không. `throws` trong chữ ký mô tả checked exception bắt buộc phải xét; một số unchecked exception được nêu trong JavaDoc mà không bắt buộc xuất hiện ở chữ ký.

### 3.3. Ngoại lệ/lỗi JVM có thể phát sinh khi thực thi

Một số thao tác Java có kiểm tra tại runtime và có thể thất bại ngay cả khi **không có lệnh `throw` hiện rõ trong mã nguồn**.

| Hoạt động | Ví dụ | Loại có thể phát sinh |
| --- | --- | --- |
| Truy cập trường/gọi phương thức qua `null` | `String s = null; s.length();` | `NullPointerException` |
| Truy cập phần tử mảng sai giới hạn | `int[] a = new int[1]; int x = a[2];` | `ArrayIndexOutOfBoundsException` |
| Ép kiểu tham chiếu không tương thích | `Object x = "hi"; Integer n = (Integer) x;` | `ClassCastException` |
| Chia số nguyên cho 0 | `int zero = 0; int q = 10 / zero;` | `ArithmeticException` |
| Tạo mảng với kích thước âm | `int[] a = new int[-1];` | `NegativeArraySizeException` |
| Gán phần tử không phù hợp kiểu runtime của mảng tham chiếu | `Object[] a = new String[1]; a[0] = 42;` | `ArrayStoreException` |
| Stack của luồng vượt giới hạn | Đệ quy quá sâu | `StackOverflowError` (`Error`) |
| JVM không đáp ứng được yêu cầu cấp phát/tài nguyên | Thiếu heap, native resource tùy tình huống | `OutOfMemoryError` (`Error`) |

Lưu ý kỹ thuật:

- Với toán hạng `double` hoặc `float`, phép chia cho `0.0` theo IEEE 754 thường tạo `Infinity` hoặc `NaN`, **không** tạo `ArithmeticException` như phép chia số nguyên cho 0.
- Các `Error` như `OutOfMemoryError`, `StackOverflowError` thuộc `Throwable` nhưng **không thuộc `Exception`**; `catch (Exception e)` sẽ không bắt chúng.
- Không nên cố tạo lỗi cạn bộ nhớ/stack để kiểm tra logic xử lý trong môi trường thực; hệ quả phụ thuộc JVM, tài nguyên và cách triển khai.

## 4. Ví dụ chạy được: quan sát cả ba nguồn

Tạo file **`ExceptionOriginsDemo.java`**:

```java
import java.util.Objects;

public class ExceptionOriginsDemo {
    private static void validateAge(int age) {
        if (age < 0) {
            throw new IllegalArgumentException("age cannot be negative");
        }
    }

    private static void observe(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": OK");
        } catch (RuntimeException failure) {
            System.out.println(label + ": "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        observe("Java code", () -> validateAge(-1));

        observe("JDK API parse", () -> Integer.parseInt("12x"));

        observe("JDK API null check", () -> Objects.requireNonNull(null));

        observe("JVM null access", () -> {
            String text = null;
            text.length();
        });

        System.out.println("Program continues");
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac ExceptionOriginsDemo.java
java ExceptionOriginsDemo
```

Kết quả `stdout`:

```text
Java code: IllegalArgumentException
JDK API parse: NumberFormatException
JDK API null check: NullPointerException
JVM null access: NullPointerException
Program continues
```

Giải thích theo từng dòng:

1. **Java code**: `validateAge(-1)` kiểm tra tham số và chủ động `throw new IllegalArgumentException(...)`.
2. **JDK API parse**: `Integer.parseInt("12x")` nhận chuỗi không hợp lệ và ném `NumberFormatException` theo hợp đồng API.
3. **JDK API null check**: `Objects.requireNonNull(null)` chủ động kiểm tra rồi ném `NullPointerException` ở tầng API.
4. **JVM null access**: phép gọi `text.length()` cố dereference `null`, khiến JVM ném `NullPointerException` trong quá trình thực thi.
5. **Program continues**: `observe` xử lý từng `RuntimeException` ngay tại ranh giới ví dụ, nên luồng chính tiếp tục. Trong ứng dụng thật, không nhất thiết nên bắt mọi `RuntimeException`; ranh giới phục hồi phải có mục đích rõ ràng.

Chương trình chỉ in **tên lớp ngoại lệ**, tránh phụ thuộc thông điệp `NullPointerException` chi tiết có thể khác nhau tùy JDK, bytecode và cấu hình JVM.

Điểm đáng nhớ: hai dòng cuối cùng trong nhóm lỗi đều in `NullPointerException`, nhưng một lỗi do phương thức API kiểm tra chủ động, còn lỗi kia do JVM kiểm tra thao tác truy cập tham chiếu.

## 5. Ngoại lệ lan truyền: nguồn nào cũng đi qua cùng cơ chế

Tạo file **`ExceptionFlowDemo.java`**:

```java
public class ExceptionFlowDemo {
    private static void lowLevel() {
        System.out.println("low: before throw");
        throw new IllegalStateException("invalid state");
    }

    private static void middleLevel() {
        try {
            lowLevel();
            System.out.println("middle: after call");
        } finally {
            System.out.println("middle: finally");
        }
    }

    public static void main(String[] args) {
        try {
            middleLevel();
            System.out.println("main: after call");
        } catch (IllegalStateException failure) {
            System.out.println("main caught: " + failure.getMessage());
        }
        System.out.println("main continues");
    }
}
```

```bash
javac ExceptionFlowDemo.java
java ExceptionFlowDemo
```

Kết quả `stdout`:

```text
low: before throw
middle: finally
main caught: invalid state
main continues
```

Diễn biến chính xác:

- `lowLevel()` in dòng đầu rồi `throw` nên không trả về bình thường.
- `middleLevel()` không có `catch`, nhưng khối `finally` của nó vẫn được thực hiện trong quá trình lan truyền ngoại lệ.
- Câu lệnh `middle: after call` và `main: after call` không chạy.
- `catch (IllegalStateException)` tại `main` nhận lỗi, in thông điệp rồi cho chương trình tiếp tục.

Nếu thay `throw new IllegalStateException(...)` bằng một lời gọi API ném `IllegalStateException` hoặc một thao tác JVM ném `RuntimeException` khác mà `catch` tương thích, cơ chế tìm handler và unwind vẫn tương tự. **Nguồn tạo lỗi** không tự động quyết định lỗi sẽ được bắt ở đâu.

### `finally` có phải luôn chạy?

Không thể hứa “luôn chạy” trong mọi hoàn cảnh. Với ví dụ bình thường trên, `finally` chạy khi phương thức bị thoát do ngoại lệ. Nhưng nếu tiến trình/VM bị kết thúc bất thường, `Runtime.halt`, mất nguồn điện hoặc môi trường không cho phép tiếp tục, nó không được bảo đảm hoàn tất. Nếu chính `finally` ném một ngoại lệ mới, kết quả lan truyền có thể thay đổi; đừng viết `finally` che giấu lỗi gốc.

## 6. Checked exception: nghĩa vụ khi gọi API

Việc ngoại lệ đến từ thư viện hay từ ứng dụng **không quyết định** nó có checked hay không. Phân loại được xác định bởi **kiểu lớp kế thừa** và ngữ cảnh bắt/khai báo.

- **Checked**: ví dụ `IOException`. Nếu mã có thể ném một checked exception, trình biên dịch yêu cầu bắt bằng `catch` phù hợp hoặc khai báo bằng `throws` ở phương thức gọi (trong khuôn khổ quy tắc Java).
- **Unchecked**: các lớp con của `RuntimeException` và `Error`. Không bắt buộc khai báo trong chữ ký hoặc bắt tại call site.
- Từ khóa `throws` **không tạo ra ngoại lệ**; nó khai báo khả năng phương thức hoàn thành đột ngột bằng những kiểu ngoại lệ được liệt kê. `throw` là thao tác thực sự ném một đối tượng.

Ví dụ chạy được với một API khai báo `throws IOException` dù dữ liệu đọc ở ví dụ không gây lỗi.

Tạo file **`CheckedApiDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;

public class CheckedApiDemo {
    private static String firstLine(Reader source) throws IOException {
        try (BufferedReader reader = new BufferedReader(source)) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        String value = firstLine(new StringReader("hello\nworld"));
        System.out.println(value);
    }
}
```

```bash
javac CheckedApiDemo.java
java CheckedApiDemo
```

Kết quả:

```text
hello
```

`BufferedReader.readLine()` có chữ ký khai báo `IOException`. Vì vậy `firstLine` và `main` khai báo `throws IOException` để thỏa quy tắc checked exception. Lần chạy này dùng `StringReader` nên thành công, nhưng **không vì thế mà bỏ được nghĩa vụ khai báo/bắt checked exception**. Với nguồn I/O thật, lỗi đọc có thể xảy ra do điều kiện ngoài chương trình.

Có thể thay `throws IOException` tại biên ứng dụng bằng `try/catch (IOException e)` khi có cách phản hồi phù hợp. Với tài nguyên như file/socket/stream, ưu tiên `try-with-resources` để đóng tài nguyên. Nếu cả phần thân và thao tác `close()` đều ném ngoại lệ, cơ chế try-with-resources thường giữ lỗi chính và lưu lỗi đóng dưới dạng **suppressed exception**; cần xem cả `getSuppressed()` khi chẩn đoán.

## 7. Chẩn đoán từ stack trace và hợp đồng API

Khi gặp lỗi, thứ tự phân tích hữu ích là:

1. **Đọc kiểu và thông điệp đầy đủ**: loại nào, nội dung thông báo nêu tham số, đường dẫn, chỉ số hay trạng thái nào? Tránh bỏ qua `Caused by` và `Suppressed`.
2. **Đọc stack trace từ vị trí phát sinh**: xem các frame đầu để tìm điểm tạo lỗi/điểm kiểm tra, rồi theo đường gọi về code của mình. Với lỗi được bọc, xem từng `cause` để tìm lỗi gốc.
3. **Phân loại thao tác**: có `throw` chủ động của ứng dụng không, có một API báo sai hợp đồng hoặc lỗi tài nguyên không, hay có toán tử/truy cập mà JVM kiểm tra?
4. **Kiểm tra giá trị tại thời điểm lỗi**: `null`, chỉ số, số chia, đầu vào chuỗi, điều kiện bất biến, trạng thái file/network hoặc dung lượng tài nguyên.
5. **Sửa nguyên nhân** và quyết định nơi xử lý đúng: chặn input sớm, chỉnh logic, bảo đảm tài nguyên, trả thông báo nghiệp vụ, hay nâng mức cảnh báo vận hành.

Ví dụ, cùng `NullPointerException` nhưng hướng sửa khác nhau:

| Tình huống | Hướng điều tra |
| --- | --- |
| `customer.getName()` với `customer == null` | Tìm đường dữ liệu tạo/cho phép `null`, sửa hợp đồng và nhánh logic |
| `Objects.requireNonNull(config, "config")` | Xem vì sao đối số truyền vào API thiếu và lời gọi nào vi phạm hợp đồng |
| API bên thứ ba ném `NullPointerException` nội bộ | Đối chiếu hợp đồng, phiên bản thư viện, input và stack trace; có thể là lỗi thư viện |
| `OutOfMemoryError` khi gọi API | Kiểm tra cả workload của API, dữ liệu, giới hạn bộ nhớ và môi trường JVM; nguồn nằm tại thao tác cấp phát thực tế |

Một stack trace **không nhất thiết chứng minh tất cả nguyên nhân sâu xa**: JVM có thể tối ưu cách hiển thị, một thư viện có thể bọc lỗi, còn dữ liệu runtime có thể đã thay đổi trước khi điều tra. Hãy giữ log/đầu vào/phiên bản JDK phù hợp để tái hiện.

### Khi chủ động ném lại hoặc bọc lỗi

Nên giữ ngữ cảnh bằng `cause` khi chuyển một lỗi từ tầng thấp lên tầng cao. Ví dụ **mảnh mã trong phương thức có phép đọc dữ liệu**:

```java
try {
    loadFromStorage();
} catch (java.io.IOException failure) {
    throw new IllegalStateException("Cannot initialize data", failure);
}
```

Đây là **mảnh minh họa**, cần có phương thức `loadFromStorage()` khai báo `throws IOException` trong chương trình thật. `IllegalStateException` là unchecked nhưng `failure` vẫn truy cập được qua `getCause()`. Không nên bọc vô tội vạ nhiều tầng bằng thông điệp vô nghĩa, hoặc chỉ ghi `failure.getMessage()` rồi làm mất stack trace.

## 8. Những nhầm lẫn cần tránh

**“API tạo ngoại lệ là JVM tự tạo.”** Không nhất thiết. Một phương thức JDK có thể dùng `throw` sau khi kiểm tra hợp đồng, như `Objects.requireNonNull`. JVM chỉ thực thi lời gọi ấy; phân loại nguồn phụ thuộc nơi điều kiện lỗi được nhận biết.

**“`NullPointerException` luôn chứng minh có lệnh gọi trên `null`.”** Sai. Mã hoặc API có thể chủ động ném chính lớp này.

**“Ngoại lệ do JVM phát sinh đều là `Error`.”** Sai. Truy cập `null`, chỉ số mảng sai hoặc chia số nguyên cho 0 thường tạo các lớp `RuntimeException`.

**“`catch (Exception)` bắt mọi lỗi trong Java.”** Sai. Nó không bắt `Error` như `StackOverflowError` hoặc `OutOfMemoryError`. Hạn chế bắt `Throwable` ở mức chung trừ những hạ tầng chuyên dụng có lý do rõ ràng.

**“Không thấy `throws` thì phương thức không thể lỗi.”** Sai. Unchecked exception/Error có thể phát sinh mà không được khai báo, và các unchecked exception được JavaDoc mô tả vẫn cần được hiểu.

**“Có `throws IOException` chắc chắn lần chạy sẽ ném lỗi.”** Sai. Nó là một khả năng cần xử lý tại lúc biên dịch, không phải một sự kiện chắc chắn khi chạy.

**“Bắt xong là chương trình đã phục hồi.”** Chưa chắc. Chỉ xử lý và tiếp tục khi trạng thái và tài nguyên vẫn thỏa bất biến. Đặc biệt, không giả định có thể tiếp tục an toàn sau lỗi cạn tài nguyên JVM.

**“Ném ngoại lệ cùng tên nghĩa là cùng nguyên nhân.”** Sai. Tên lớp cần được đặt cùng thao tác gây lỗi, thông điệp và chuỗi `cause`.

## 9. Câu hỏi tự kiểm tra

1. **Bạn tự viết `throw new IllegalArgumentException("bad")`. Nguồn phát sinh là gì?** Mã ứng dụng Java.
2. **`Integer.parseInt("x")` phát sinh gì và ở đâu?** `NumberFormatException` do API báo dữ liệu không thể phân tích theo hợp đồng.
3. **`String s = null; s.length();` phát sinh gì?** JVM có thể ném `NullPointerException` khi đánh giá thao tác dereference.
4. **Hai trường hợp ở câu 2 và 3 đều unchecked vì đều từ API/JVM?** Không. Chúng unchecked vì kế thừa `RuntimeException`, độc lập với nguồn.
5. **`catch (IOException e)` có nhận `OutOfMemoryError`?** Không, chúng thuộc hai nhánh `Exception` và `Error` khác nhau.
6. **Một phương thức khai báo `throws IOException` có buộc phải thực sự ném IOException mỗi lần gọi?** Không. Chữ ký thể hiện khả năng phát sinh checked exception.
7. **Khi không biết một `NullPointerException` đến từ API hay bytecode, nên đọc gì?** Call site, stack trace, API contract và dữ liệu thực tại thời điểm lỗi.

## 10. Tham khảo Java 17

- [Java Language Specification 17 — §11.1.3 Causes of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.1.3): nguyên nhân phát sinh ngoại lệ.
- [Java Language Specification 17 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): quy tắc checked exception.
- [Java Language Specification 17 — §11.3 Run-Time Handling of an Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.3): lan truyền và xử lý tại runtime.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): cause, stack trace, suppressed exception.
- [Java SE 17 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): kiểm tra `null` theo hợp đồng API.
- [Java SE 17 API — BufferedReader.readLine](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine()): API có `throws IOException`.

Khi hiểu **thao tác nào đã báo lỗi**, **kiểu `Throwable` nào được ném** và **handler nào nhận được nó**, bạn sẽ phân tích luồng thực thi chính xác và chọn vị trí sửa lỗi phù hợp.
