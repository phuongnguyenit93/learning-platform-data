# Functional interface: Hợp đồng `throws` và ngoại lệ trong hàm

## 1. Vì sao `throws` quan trọng khi dùng lambda?

Một **functional interface** chỉ có một phương thức trừu tượng cần triển khai (SAM — single abstract method), chẳng hạn `Runnable.run()`, `Callable.call()` hay `Function.apply()`. Khi gán lambda hoặc method reference vào functional interface, kiểu của interface là **hợp đồng** mà trình biên dịch sử dụng để kiểm tra tham số, kiểu trả về **và checked exception**.

Ví dụ, hai interface dưới đây cùng có một thao tác không tham số, không trả kết quả, nhưng quy tắc ngoại lệ khác nhau:

~~~java
@FunctionalInterface
interface TaskWithoutCheckedException {
    void run();
}

@FunctionalInterface
interface TaskWithIoException {
    void run() throws java.io.IOException;
}
~~~

- Với `TaskWithoutCheckedException`, thân lambda không được để một `IOException` có thể thoát ra ngoài mà không bắt/xử lý.
- Với `TaskWithIoException`, thân lambda có thể ném `IOException` hoặc kiểu con của nó; người **gọi `run()`** phải catch hoặc khai báo `throws IOException`.
- `IllegalArgumentException`, `IllegalStateException` và các lớp kế thừa `RuntimeException` là **unchecked**; chúng có thể được ném ở cả hai trường hợp, dù không xuất hiện trong `throws`.
- `@FunctionalInterface` yêu cầu compiler xác minh interface vẫn là functional interface; annotation không tự thay đổi luật checked exception.
- `default`/`static` method không trở thành phương thức trừu tượng thứ hai, nên một functional interface có thể chứa các method loại đó.

Bài tập trung vào quy tắc **vẫn áp dụng trên Java hiện đại**, với ví dụ tương thích Java 8 và chạy được bằng JDK đang được bảo trì. Không sử dụng cách xử lý ngoại lệ kiểu "sneaky throw", không nuốt lỗi im lặng và không phụ thuộc vào API đã lỗi thời.

## 2. Checked, unchecked và phân tích lỗi tại thời điểm biên dịch

Java chia ngoại lệ theo trách nhiệm compiler:

| Kiểu | Ví dụ | Có bắt buộc catch hoặc `throws`? | Ý nghĩa |
| --- | --- | --- | --- |
| Checked exception | `IOException`, `SQLException`, `InterruptedException` | Có, tại những vị trí compiler thấy có thể phát sinh | Thường đại diện lỗi có thể được xử lý theo quy tắc nghiệp vụ/hệ thống |
| Unchecked exception | `IllegalArgumentException`, `NumberFormatException`, `UncheckedIOException` | Không bắt buộc ở compile-time | Thường là điều kiện sai, dữ liệu sai, hoặc wrapper để đưa checked exception qua API không khai báo nó |
| `Error` và lớp con | `OutOfMemoryError` | Không bắt buộc | Thường là sự cố nghiêm trọng; không dùng catch tổng quát để giả vờ phục hồi |

**Phân biệt quan trọng:** `throws` là một **cam kết kiểu tại compile-time** về checked exception có thể thoát khỏi phương thức; nó không tạo exception và cũng không thay cho `throw`.

~~~java
// Khai báo hợp đồng:
void load() throws java.io.IOException;

// Phát sinh một exception cụ thể trong thân method/lambda:
throw new java.io.IOException("Không đọc được dữ liệu");
~~~

Hai dòng trên là ví dụ cú pháp trong những ngữ cảnh khác nhau, **không phải một chương trình Java độc lập**. Bạn cũng không thể thêm `throws IOException` trực tiếp vào cú pháp lambda theo cách viết method declaration. Thay vào đó, khai báo `throws` ở **abstract method của functional interface**.

### Phương thức gọi vẫn phải tuân thủ hợp đồng

~~~java
@FunctionalInterface
interface CheckedAction {
    void run() throws java.io.IOException;
}

// Phương thức này chỉ chuyển tiếp hợp đồng:
static void invoke(CheckedAction action) throws java.io.IOException {
    action.run();
}
~~~

Ngay cả khi implementation thực tế không ném exception, compiler vẫn thấy rằng `CheckedAction.run()` **có thể** ném `IOException`. Vì vậy, caller của `invoke` phải xử lý checked exception theo chữ ký, trừ khi caller cũng khai báo nó.

## 3. Checked exception trong lambda và method reference

### 3.1. Target type quyết định điều gì được ném

~~~java
import java.io.IOException;
import java.util.concurrent.Callable;

// Các câu lệnh này đặt trong một method:
Callable<String> fromCallable = () -> {
    throw new IOException("Đọc thất bại");
}; // Hợp lệ: Callable.call() khai báo throws Exception.

// LỖI khi bỏ comment: Runnable.run() không khai báo checked exception.
// Runnable fromRunnable = () -> {
//     throw new IOException("Đọc thất bại");
// };
~~~

`Callable<V>.call() throws Exception` rộng hơn `IOException`; còn `Runnable.run()` không khai báo checked exception. Do đó **không thể sửa lỗi chỉ bằng cách thêm `throws` ở method chứa biểu thức lambda** — giới hạn của **target functional interface** vẫn còn.

Ví dụ khác: `Function<T,R>.apply(T)`, `Consumer<T>.accept(T)`, `Predicate<T>.test(T)`, `Supplier<T>.get()` **không khai báo checked exception**. Khi lambda gọi một phương thức có thể ném `IOException`, bạn phải xử lý bên trong lambda hoặc chọn một interface có hợp đồng phù hợp.

### 3.2. Method reference cũng phải tương thích ngoại lệ

Giả sử bạn có method đã tồn tại:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

@FunctionalInterface
interface ByteLoader {
    byte[] load(Path file) throws IOException;
}

// Trong một phương thức:
ByteLoader allowed = Files::readAllBytes;

// LỖI nếu bỏ comment: Function.apply không khai báo IOException.
// Function<Path, byte[]> notAllowed = Files::readAllBytes;
~~~

Đây là **các đoạn khai báo/biểu thức cần được đặt trong class hoặc method thích hợp**, không phải một file hoàn chỉnh. Method reference không tự xử lý checked exception của method được trỏ tới; compiler so khớp kiểu trả về, tham số và ràng buộc checked exceptions với target interface.

### 3.3. Thay anonymous class bằng lambda không làm thay đổi hợp đồng

~~~java
// Dưới ngữ cảnh có ByteLoader ở trên:
ByteLoader anonymous = new ByteLoader() {
    @Override
    public byte[] load(Path file) throws IOException {
        return Files.readAllBytes(file);
    }
};
ByteLoader lambda = file -> Files.readAllBytes(file);
~~~

Cả hai vẫn tuân thủ `ByteLoader.load(Path) throws IOException`. Lambda là cách viết implementation ngắn gọn hơn; **interface** vẫn quyết định những checked exception nào được phép thoát ra ngoài. Ngoài ra, việc chuyển sang lambda cần kiểm tra các khác biệt `this`/scope nếu anonymous class có state riêng.

## 4. Tạo functional interface có `throws` phù hợp nghiệp vụ

Khi hoạt động có thể thất bại do I/O, cấu hình, tích hợp bên ngoài hoặc điều kiện có thể phục hồi, hãy cân nhắc thiết kế một interface nói rõ điều đó:

~~~java
import java.io.IOException;

@FunctionalInterface
interface CheckedParser {
    int parse(String input) throws IOException;
}
~~~

Interface này cho phép:
- Một lambda trả `int` và ném `IOException` khi input không thể đọc/diễn giải theo hợp đồng.
- Một phương thức gọi có thể chọn `catch(IOException)` để xử lý hoặc khai báo tiếp `throws IOException`.
- Unit test gọi cùng logic mà không cần wrapper unchecked nếu API nghiệp vụ đã cho phép checked exceptions.

Không thêm `throws Exception` quá rộng chỉ để tránh suy nghĩ về loại lỗi. Nếu biết loại lỗi cụ thể, khai báo loại cụ thể, ví dụ `IOException`. Nếu một lỗi là điều kiện dữ liệu đầu vào bất hợp lệ, `IllegalArgumentException` (unchecked) có thể hợp lý hơn; cần thống nhất semantics trong API. Không phải mọi lỗi parsing đều là checked: `Integer.parseInt` ném `NumberFormatException`, thuộc `RuntimeException`.

### Generic interface khi cần tái sử dụng

~~~java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}

// Trong method có đủ import:
ThrowingFunction<String, Integer, java.io.IOException> parse =
    text -> {
        if (text.isEmpty()) {
            throw new java.io.IOException("Input rỗng");
        }
        return Integer.parseInt(text);
    };
~~~

Đây là một interface **do ứng dụng định nghĩa**, không phải loại có sẵn trong `java.util.function`. Nó rất hữu ích bên trong các tầng nghiệp vụ cần giữ kiểu checked exception. Tuy nhiên, nó không thể truyền trực tiếp vào mọi API nhận `Function<T,R>`: hai target type không đồng nhất và hợp đồng `throws` khác nhau.

## 5. Ví dụ hoàn chỉnh: gọi trực tiếp và chuyển checked sang unchecked có chủ đích

Tạo file **`ThrowsContractDemo.java`** với encoding UTF-8. Ví dụ không phụ thuộc file thực tế hay mạng, nên stdout luôn xác định; `IOException` được ném có chủ đích nhằm minh họa hợp đồng. Trên hệ thống thật, lỗi này có thể phát sinh từ thao tác đọc file hoặc dịch vụ.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;

public class ThrowsContractDemo {
    @FunctionalInterface
    interface CheckedParser {
        int parse(String text) throws IOException;
    }

    static int invoke(CheckedParser parser, String text)
            throws IOException {
        return parser.parse(text);
    }

    // Adapter được gọi khi thư viện bên ngoài yêu cầu Function.
    static Function<String, Integer> unchecked(CheckedParser parser) {
        return text -> {
            try {
                return parser.parse(text);
            } catch (IOException error) {
                throw new UncheckedIOException("Parse failed", error);
            }
        };
    }

    public static void main(String[] args) {
        CheckedParser parser = value -> {
            String normalized = value.trim();
            if (normalized.isEmpty()) {
                throw new IOException("Input is blank");
            }
            return Integer.parseInt(normalized);
        };

        try {
            System.out.println("Checked: " + invoke(parser, " 42 "));
        } catch (IOException error) {
            System.out.println("Checked error: " + error.getMessage());
        }

        Function<String, Integer> standardFunction = unchecked(parser);
        System.out.println("Function: " + standardFunction.apply("7"));

        try {
            standardFunction.apply(" ");
        } catch (UncheckedIOException error) {
            System.out.println("Wrapped: " + error.getCause().getMessage());
        }

        try {
            invoke(parser, " ");
        } catch (IOException error) {
            System.out.println("Direct: " + error.getMessage());
        }
    }
}
~~~

Dùng một JDK đang được nhà cung cấp cập nhật. Nếu compiler còn hỗ trợ target Java 8:

~~~text
javac --release 8 -encoding UTF-8 ThrowsContractDemo.java
java ThrowsContractDemo
~~~

Trong dự án chỉ chạy trên JDK hiện đại, có thể dùng `javac -encoding UTF-8 ThrowsContractDemo.java` với toolchain dự án; `--release 8` chỉ cần khi bạn thực sự yêu cầu mức tương thích Java 8.

**Stdout đúng bốn dòng:**

~~~text
Checked: 42
Function: 7
Wrapped: Input is blank
Direct: Input is blank
~~~

**Vì sao bốn dòng này xuất hiện?**

1. `invoke(parser, " 42 ")` gọi SAM `parse`. `trim()` cho `"42"`, `Integer.parseInt` cho 42; do method `invoke` khai báo `throws IOException`, `main` dùng `try/catch` dù nhánh này không phát sinh lỗi.
2. `unchecked(parser)` trả về `Function<String,Integer>` đúng target type được framework/Stream API mong đợi. Với `"7"`, lambda không gặp exception, trả 7.
3. Input chỉ chứa khoảng trắng khiến `CheckedParser` ném `IOException("Input is blank")`. Adapter bắt đúng `IOException` và tạo `UncheckedIOException`. `getCause()` giữ ngoại lệ gốc nên thông điệp được in ra.
4. Gọi trực tiếp `invoke(parser, " ")` làm cùng `IOException` thoát ra, caller xử lý ngay dưới dạng checked exception.

**Giới hạn có chủ ý:** Khi truyền `"abc"`, `Integer.parseInt` ném `NumberFormatException`, **không** bị `catch(IOException)` trong adapter bắt. Đây là hành vi đúng theo kiểu exception, không phải bug của `try/catch`. Hãy định nghĩa riêng chính sách đối với lỗi dữ liệu đầu vào khi đưa ví dụ vào sản phẩm thật.

## 6. Ba cách xử lý checked exception trong hàm

| Cách | Khi phù hợp | Trách nhiệm của caller | Cần chú ý |
| --- | --- | --- | --- |
| Khai báo `throws` trên SAM tự định nghĩa | API domain muốn biểu đạt lỗi recoverable rõ ràng | `catch` hoặc `throws` theo chữ ký | Không cắm trực tiếp vào API đòi `Function` chuẩn |
| Catch ngay trong lambda | Có kết quả thay thế hợp lệ hoặc xử lý tại chỗ là đúng tầng | Không nhận lại checked exception đó nếu đã xử lý hoàn toàn | Tránh mặc định trả `null` hoặc chuỗi rỗng làm ẩn lỗi |
| Catch và wrap thành unchecked | Phải thích ứng với API chuẩn không khai báo checked exception | Có thể để exception propagate hoặc catch wrapper ở boundary | Giữ cause; không dùng wrap để che hậu quả |

Ví dụ xử lý tại chỗ khi **fallback đã được nghiệp vụ định nghĩa**:

~~~java
// Đặt trong một method, với CheckedParser parser và import Function:
Function<String, Integer> withFallback = text -> {
    try {
        return parser.parse(text);
    } catch (IOException error) {
        return -1;
    }
};
~~~

Đây chỉ là mẫu minh họa. Nếu `-1` là một điểm số hợp lệ hoặc che lỗi quan trọng, fallback này **không phù hợp**; thay bằng một kiểu kết quả rõ ràng, ghi log đúng tầng hoặc cho phép lỗi lan tới người có khả năng xử lý.

### Dùng `UncheckedIOException` khi đúng loại nguyên nhân

`UncheckedIOException` được thêm trong Java 8, giúp biểu đạt một `IOException` đã bị chuyển thành unchecked nhưng **giữ nguyên cause**. Nó không dành cho `SQLException` hay bất kỳ checked exception nào. Với loại khác, cân nhắc một exception runtime theo domain của bạn, có constructor nhận cause, ví dụ `new DataAccessRuntimeException("...", cause)` nếu domain đã định nghĩa kiểu đó. Không tạo wrapper chỉ vì muốn loại bỏ `throws` khỏi API.

### Tránh những kiểu xử lý làm mất thông tin

~~~java
// CÁCH LÀM KHÔNG NÊN DÙNG:
// catch (IOException ignored) { return null; }
// catch (Exception error) { return ""; }
// throw new RuntimeException(error.getMessage()); // mất cause
~~~

Nên ghi lại hoặc gắn cause, đặt thông điệp đủ ngữ cảnh nhưng **không đưa dữ liệu nhạy cảm** vào log/message. Nếu đã xử lý/ghi log tại boundary, tránh lặp vô ích ở tất cả tầng trung gian.

## 7. Hợp đồng `throws` khi override phương thức

Quy tắc của overriding giúp hiểu vì sao implementation lambda không được ném checked exception vượt hợp đồng:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

interface Operation {
    void execute() throws IOException;
}

class NoCheckedOperation implements Operation {
    @Override
    public void execute() {  // HỢP LỆ: không ném checked exception.
    }
}

class NarrowOperation implements Operation {
    @Override
    public void execute() throws FileNotFoundException { // HỢP LỆ: kiểu con.
    }
}

// ĐÂY LÀ MINH HỌA LỖI, KHÔNG PHẢI CODE BIÊN DỊCH:
// class WrongOperation implements Operation {
//     @Override
//     public void execute() throws java.sql.SQLException { }
// }
~~~

Implementation có thể khai báo ít checked exception hơn hoặc kiểu con phù hợp của loại được phép. Nó **không thể mở rộng** checked exception tùy ý thành kiểu không tương thích (ví dụ `SQLException` thay vì `IOException`). Các unchecked exception không chịu ràng buộc compiler tương tự.

Danh sách `throws` cũng **không phải là một phần phân biệt overload**: bạn không thể có hai method cùng tên và cùng tham số, chỉ khác `throws IOException`/`throws SQLException` rồi coi là hai overload hợp lệ.

### Kế thừa nhiều abstract method tương ứng

Ở interface phức tạp, nếu một functional interface kế thừa các abstract method có chữ ký tương ứng nhưng danh sách checked exceptions khác nhau, kiểu chức năng tổng hợp có thể bị **hạn chế hơn** từng method riêng lẻ. Không suy đoán từ một interface cha tùy ý; tra JLS `9.8`/`9.9` và để compiler kiểm tra target type. Nếu API cần hợp đồng exception rõ ràng, giữ SAM đơn giản là lựa chọn dễ bảo trì.

## 8. Luồng, tác vụ bất đồng bộ và ngoại lệ

Một số API được dùng rộng rãi với functional interface chuẩn:

- `Stream.map(Function)` và `Stream.filter(Predicate)` không khai báo checked exception trong callback. Nếu mapper đọc file hay gọi API có `IOException`, cần xử lý hoặc adapter; đừng chỉ thêm `throws IOException` lên method bên ngoài rồi hy vọng lambda compile.
- `Runnable.run()` không cho checked exception thoát ra, nhưng `Callable<V>.call() throws Exception` có. Khi gửi `Callable` vào `ExecutorService.submit`, lỗi từ tác vụ thường tới bên gọi thông qua `Future.get()` dưới dạng `ExecutionException`; đừng nhầm với chữ ký trực tiếp của `call()`.
- `CompletableFuture.supplyAsync(Supplier)` yêu cầu `Supplier.get()` không khai báo checked exception. Nếu wrapper runtime lan ra khỏi supplier, completion sẽ thất bại; `join()` thường báo `CompletionException` và bạn nên quan sát chain nguyên nhân ở đúng boundary.
- Chuyển lỗi checked sang unchecked **không** làm lỗi tự biến mất, và cũng không biến thao tác I/O thành an toàn để retry hoặc song song.

Với `InterruptedException`, đừng coi nó như một exception bình thường có thể nuốt. Nếu buộc catch tại ranh giới không cho khai báo checked exception, cân nhắc phục hồi cờ interrupt qua `Thread.currentThread().interrupt()` và truyền tín hiệu hủy/thất bại phù hợp với hợp đồng. Không thực hiện retry vô hạn hay đánh rơi yêu cầu hủy.

## 9. Lỗi thường gặp và cách sửa

### Lỗi: `unreported exception IOException; must be caught or declared to be thrown`

~~~java
import java.io.IOException;
import java.util.function.Function;

// Với method read(String) throws IOException:
// Function<String, String> wrong = input -> read(input);
~~~

**Nguyên nhân:** `Function.apply` không có `throws IOException`. **Cách sửa:** nếu được kiểm soát type, dùng functional interface tự định nghĩa có `throws`; nếu thư viện bắt buộc `Function`, xử lý bên trong lambda hoặc wrap đúng cách và giữ cause.

### Lỗi: `throws` ở method bao quanh không đủ

~~~java
// Giả sử có một static method load() throws IOException:
// static void setup() throws IOException {
//     Runnable r = () -> load(); // VẪN LỖI: Runnable.run() không throws.
// }
~~~

**Nguyên nhân:** checked exception có thể thoát khỏi *thân lambda*, còn target `Runnable` cấm điều đó. Chữ ký `throws` của `setup` chỉ liên quan đến các lời gọi trực tiếp trong `setup`, không tự sửa target type của lambda.

### Lỗi: bắt quá rộng

~~~java
// KHÔNG NÊN: catch (Exception e) { return null; }
~~~

**Vấn đề:** che luôn lỗi lập trình có thể biểu hiện qua `RuntimeException`. Bắt loại lỗi mà tầng hiện tại thực sự xử lý được; nếu cần bắt rộng tại boundary hệ thống, nêu chính sách rõ ràng và giữ nguyên nguyên nhân.

### Lỗi: truyền wrapper mà quên kiểm tra lỗi ở consumer

Nếu bạn biến `IOException` thành `UncheckedIOException` trong `Stream.map`, ngoại lệ có thể xuất hiện khi chạy **terminal operation** như `collect` hoặc `forEach`, vì intermediate Stream operations thường là lazy. Đặt quan sát/xử lý lỗi ở khu vực thực thi thực tế; không giả định exception sẽ phát sinh lúc tạo pipeline.

### Lỗi: coi mọi exception là lỗi có thể retry

`NumberFormatException` có thể đến từ input sai, còn `IOException` có thể là lỗi transient hoặc lâu dài. Chỉ retry khi hoạt động idempotent hoặc có cơ chế chống trùng, biết chính sách backoff và giới hạn; checked/unchecked không tự quyết định có nên retry.

## 10. Hướng dẫn thiết kế API có thể bảo trì

1. **Dùng `throws` để nói rõ hợp đồng tại ranh giới thích hợp.** Nếu caller có thể xử lý lỗi theo nhánh nghiệp vụ, interface tùy biến có checked exception cụ thể giúp truyền ý nghĩa tốt hơn.
2. **Giữ đúng target type khi dùng thư viện.** `java.util.function` chủ yếu không khai báo checked exception; adapter nên tập trung ở ranh giới tích hợp thay vì để từng lambda tự xử lý không nhất quán.
3. **Đừng khai báo `throws Exception` vô tội vạ.** Ưu tiên kiểu cụ thể hoặc kiểu domain có ngữ nghĩa; đừng làm mọi caller phải catch quá rộng.
4. **Giữ stack trace và cause.** `new UncheckedIOException(context, cause)` cho I/O; với loại khác dùng wrapper có cause hợp lệ.
5. **Không lạm dụng ngoại lệ để điều khiển luồng thông thường.** Một kết quả "không tìm thấy" hợp lệ có thể phù hợp với `Optional` hoặc kiểu kết quả domain, tùy hợp đồng.
6. **Không tự động gán fallback** khi không có giá trị dự phòng đã định nghĩa; dữ liệu "thành công giả" khó phát hiện hơn exception rõ ràng.
7. **Phân biệt compile-time với runtime.** Qua `throws` compiler biết cách ràng buộc checked exception; ở runtime vẫn có unchecked failures, lỗi I/O thật, context bất đồng bộ và cancellation.
8. **Test cả hai đường.** Test output thành công và loại exception, message/cause khi thất bại; nếu dùng adapter, test rằng checked lỗi được wrap chứ không bị đánh mất.

## 11. Bài tập tự kiểm tra

1. Tạo một `@FunctionalInterface interface DataReader { String read() throws IOException; }`. Viết lambda trả `"ok"` và lambda ném `new IOException("failed")`. Chứng minh caller cần catch/throws khi gọi `read()`, ngay cả với lambda `"ok"`.
2. Thử gán `() -> { throw new IOException("failed"); }` cho `Runnable`. Phân biệt lỗi compiler với trường hợp tương ứng gán cho `Callable<String>`.
3. Dùng `Files::readAllBytes` với `ByteLoader` và `Function<Path,byte[]>`. Giải thích vì sao trường hợp thứ nhất hợp lệ, thứ hai compile error.
4. Sửa hàm `unchecked` trong ví dụ hoàn chỉnh thành phiên bản fallback. Chỉ dùng `-1` nếu đầu vào của bài tập quy định `-1` là giá trị báo lỗi, rồi so sánh mất/thừa thông tin với phương án `UncheckedIOException`.
5. Nhập `"abc"` cho parser. Nêu đúng loại exception: `NumberFormatException`. Giải thích vì sao catch `IOException` không bắt được nó, và xác định một hợp đồng lỗi input rõ ràng hơn.
6. Viết implementation của `Operation.execute() throws IOException`: một class không khai báo checked exception, một class ném `FileNotFoundException` và một class thử ném `SQLException`. Dự đoán đâu là class compile được và vì sao.
7. Đặt lambda đọc file trong `Stream.map`, mô tả nơi lỗi xuất hiện khi terminal operation chạy, cách chuyển nguyên nhân và cách test cả đường thành công/lỗi.

**Hoàn thành khi:** bạn giải thích được quan hệ giữa `throws` của SAM, lambda body và caller; sửa được lỗi checked exception trong `Function`/`Runnable` mà không nuốt nguyên nhân; chọn được custom functional interface hoặc adapter phù hợp và chạy chương trình `ThrowsContractDemo.java` đúng stdout.

## Tài liệu chuẩn để đối chiếu

- Java Language Specification (JLS) mới, `9.8 Functional Interfaces và `9.9 Function Types: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html
- JLS, `11.2.3 Exception Checking: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-11.html#jls-11.2.3
- JLS, `15.27.3 Type of a Lambda Expression: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.27.3
- Java 8 `UncheckedIOException`: https://docs.oracle.com/javase/8/docs/api/java/io/UncheckedIOException.html

Các đặc tả trên mô tả quy tắc hiện vẫn được hỗ trợ. Khi triển khai thực tế, hãy chọn JDK phân phối đang có cập nhật và các thư viện đang được bảo trì.