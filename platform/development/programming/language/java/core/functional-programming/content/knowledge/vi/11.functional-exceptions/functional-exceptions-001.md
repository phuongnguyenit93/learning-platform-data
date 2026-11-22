# Checked exception phải tương thích với `throws` của kiểu đích trong lambda Java

## 1. Vấn đề cốt lõi

Lambda và method reference trong Java không có một kiểu hàm tự do: chúng được biên dịch theo **functional interface đích** (target type). Phương thức trừu tượng chức năng của interface đó, thường gọi **SAM** (*single abstract method*), quyết định tham số, kiểu trả về **và checked exception được phép thoát ra**.

Ví dụ, phương thức **Files.readString(Path)** đọc nội dung tệp và khai báo **throws IOException**. Trong khi đó, **Function<Path,String>** dùng SAM **String apply(Path)**, không khai báo checked exception. Vì vậy, dòng sau **không biên dịch**:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH: Function.apply không khai báo IOException.
Function<Path, String> read = path -> Files.readString(path);
~~~

Đoạn minh họa giả định đã import **java.nio.file.Files**, **java.nio.file.Path** và **java.util.function.Function**. Lỗi không phải vì lambda không được phép gọi API I/O, mà vì **IOException có thể thoát khỏi thân lambda nhưng không nằm trong hợp đồng throws của SAM**.

Nếu tự định nghĩa một functional interface có phương thức chức năng khai báo **throws IOException**, cùng hành vi có thể hợp lệ:

~~~java
@FunctionalInterface
interface TextLoader {
    String load(Path path) throws IOException;
}

TextLoader loader = Files::readString;
~~~

Đây là **đoạn mã minh họa** cần import **IOException**, **Files**, **Path**, không phải chương trình độc lập. **Files::readString** cũng có thể dùng được vì chữ ký phương thức được tham chiếu khớp với **TextLoader.load(Path)** và ngoại lệ được cho phép.

**Quy tắc nhớ:** Checked exception có thể thoát khỏi lambda hoặc method reference **chỉ khi phù hợp với phần throws của SAM đích**, hoặc được **bắt và xử lý trong thân**. Việc phương thức chứa phép gán lambda tự khai báo throws **không mở rộng** throws của SAM.

## 2. Checked và unchecked exception khác nhau thế nào?

Java chia các throwable quan trọng thành:

- **Checked exception:** các lớp con của **Exception** nhưng không thuộc **RuntimeException** (ví dụ **IOException**, **SQLException**, **ParseException**). Trình biên dịch yêu cầu bắt hoặc khai báo theo hợp đồng liên quan.
- **Unchecked exception:** **RuntimeException** và các lớp con (ví dụ **IllegalArgumentException**, **NullPointerException**, **UncheckedIOException**) cùng **Error** và các lớp con. Chúng không bắt buộc phải được liệt kê trong throws để mã biên dịch.
- **Error:** như **OutOfMemoryError** hoặc **StackOverflowError**, thường phản ánh vấn đề môi trường hoặc tài nguyên; không dùng Error thay thế cơ chế báo lỗi nghiệp vụ thông thường.

**throws** ở chữ ký phương thức mô tả checked exception có thể được truyền lên người gọi. **throw** là câu lệnh thực sự ném một đối tượng Throwable:

~~~java
String load(Path path) throws IOException {
    if (path == null) {
        throw new IllegalArgumentException("path required");
    }
    return Files.readString(path);
}
~~~

Đây là **phương thức minh họa**, không phải chương trình độc lập. Trong đó, **IllegalArgumentException** là unchecked nên không bắt buộc khai báo; **IOException** đến từ Files.readString là checked, được phép thoát nhờ **throws IOException**.

**Không nên nhầm:** Một lambda có thể ném **RuntimeException** mà SAM không khai báo throws. Sự tự do về mặt biên dịch **không** có nghĩa nên tùy tiện chuyển mọi lỗi thành unchecked.

## 3. Target type quyết định phạm vi ngoại lệ được phép

Xét các kiểu chức năng thường gặp:

| Functional interface đích | SAM | Checked exception có được thoát trực tiếp? |
| --- | --- | --- |
| **Runnable** | **void run()** | Không khai báo checked exception |
| **Supplier<T>** | **T get()** | Không khai báo checked exception |
| **Function<T,R>** | **R apply(T)** | Không khai báo checked exception |
| **Consumer<T>** | **void accept(T)** | Không khai báo checked exception |
| **Predicate<T>** | **boolean test(T)** | Không khai báo checked exception |
| **Callable<V>** | **V call() throws Exception** | Cho phép checked Exception hoặc lớp con phù hợp |
| **TextLoader** tự định nghĩa | **String load(Path) throws IOException** | Cho phép IOException hoặc lớp con phù hợp |

Các interface chuẩn trong **java.util.function** không khai báo checked exception trong SAM chính; điều này quan trọng khi truyền callback vào **Stream.map/filter/forEach**, **Optional.map**, hoặc các API nhận Function, Consumer, Supplier.

Ví dụ sự khác biệt:

~~~java
// Hợp lệ: Callable.call khai báo throws Exception.
Callable<String> operation = () -> Files.readString(path);

// Không hợp lệ: Supplier.get không khai báo IOException.
// Supplier<String> operation2 = () -> Files.readString(path);
~~~

Đoạn minh họa cần import **Callable**, **Supplier**, **Files**, và có biến **path** kiểu Path. Đó không phải hai khai báo độc lập sẵn sàng biên dịch cùng ngữ cảnh. **Callable.call()** khai báo **throws Exception**, vì vậy IOException là một lớp con phù hợp. Khi **gọi operation.call()**, bên gọi vẫn phải bắt hoặc khai báo **Exception** theo kiểu tĩnh Callable, ngay cả khi lambda cụ thể chỉ có thể ném IOException.

### 3.1. Kiểu cụ thể hơn không thể thay đổi hợp đồng SAM

Giả sử một lambda được gán cho **Function<Path,String>**:

~~~java
Function<Path, String> f = path -> {
    return Files.readString(path);
};
~~~

Đây là **ví dụ cố ý không biên dịch**. Thêm dấu ngoặc nhọn và **return** không sửa được lỗi checked exception. Kiểu trả về String đã tương thích, nhưng **IOException vẫn không được phép thoát qua Function.apply**.

Cũng không thể sửa lỗi bằng cách khai báo phương thức tạo lambda như sau:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
static Function<Path, String> makeReader() throws IOException {
    return path -> Files.readString(path);
}
~~~

**throws IOException** của **makeReader** chỉ áp dụng cho quá trình thực hiện **makeReader**, không làm **Function.apply** khai báo IOException. Việc đọc tệp nằm trong lambda và được thực thi sau đó, nên trình biên dịch vẫn xét hợp đồng throws của **Function.apply**.

Tương tự, thêm **throws IOException** vào phương thức **main** không khiến một lambda gán cho Function được phép ném IOException chưa xử lý.

## 4. Đọc đúng hướng của quan hệ ngoại lệ

Với SAM:

~~~java
@FunctionalInterface
interface IoAction {
    void run() throws IOException;
}
~~~

Thân lambda **được phép** ném:

- **IOException**, hoặc một lớp con cụ thể hơn như **FileNotFoundException**.
- **Unchecked exception** như **IllegalStateException** mà không cần khai báo thêm.

Nhưng **không được phép** để một checked exception rộng hơn hoặc không liên quan thoát ra nếu SAM không khai báo nó:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH nếu method có thể ném Exception rộng hơn:
IoAction bad = () -> {
    throw new Exception("wider checked exception");
};
~~~

Hai đoạn trên minh họa quy tắc. **Exception** là kiểu cha của **IOException**, không phải lớp con, vì thế không nằm trong tập checked exception mà **throws IOException** cho phép.

Ngược lại, interface dùng SAM **throws Exception** cho phép lambda ném IOException. Quy tắc tương tự cơ chế override phương thức trong Java: một implementation không được tùy ý mở rộng các checked exception đã được hứa với caller của kiểu cha.

**Nhớ rõ chiều tương thích:** “SAM khai báo IOException” cho phép **FileNotFoundException**; “SAM khai báo FileNotFoundException” **không** cho phép một IOException bất kỳ.

Nếu một lambda có nhiều nhánh ném nhiều checked exception độc lập, SAM phải khai báo các kiểu bao phủ được tất cả ngoại lệ có thể thoát; hoặc lambda cần bắt và chuyển đổi một số ngoại lệ trước khi trả quyền điều khiển.

## 5. Bốn cách xử lý phổ biến

### 5.1. Cách A: Bắt và xử lý ngay trong lambda

Khi API bắt buộc dùng **Function<T,R>**, bạn có thể bắt IOException và chọn một chính sách phù hợp:

~~~java
Function<Path, String> reader = path -> {
    try {
        return Files.readString(path);
    } catch (IOException cause) {
        return "[unavailable]";
    }
};
~~~

Đây là đoạn minh họa cần import **Function**, **Files**, **Path**, **IOException**. Nó **biên dịch**, vì IOException không thoát ra ngoài lambda.

Tuy nhiên, **trả giá trị mặc định** chỉ đúng nếu hệ thống chủ động định nghĩa rằng “không đọc được tệp” có thể được coi là “không có nội dung”. Trong đa số nghiệp vụ, việc âm thầm nuốt lỗi có thể khiến dữ liệu sai mà khó phát hiện. Nếu lỗi quan trọng, đừng dùng mẫu trên mà không có quyết định về semantics rõ ràng.

Một biến thể là log và bỏ qua, trả Optional hoặc loại bản ghi hỏng. Các lựa chọn này làm thay đổi hợp đồng nghiệp vụ: **bắt được exception** không tự nói lên điều gì nên xảy ra tiếp theo.

### 5.2. Cách B: Bọc IOException vào UncheckedIOException

Nếu API nhận Function và lỗi đọc tệp **phải làm thất bại** phép biến đổi, có thể chuyển checked IOException thành **UncheckedIOException**:

~~~java
Function<Path, String> reader = path -> {
    try {
        return Files.readString(path);
    } catch (IOException cause) {
        throw new UncheckedIOException("Cannot read " + path, cause);
    }
};
~~~

Đoạn minh họa cần import **java.io.UncheckedIOException** cùng các kiểu đã dùng. **UncheckedIOException** kế thừa RuntimeException, nên **Function.apply** không bắt buộc khai báo nó. **Cause** được giữ lại để người xử lý lỗi biết nguyên nhân I/O ban đầu.

Đây không phải một “ngoại lệ checked tự động thành công”: lỗi vẫn xảy ra khi lambda chạy, nhưng được biểu diễn dưới dạng unchecked và có thể truyền qua API chuẩn.

**Không bắt Exception quá rộng để ép mọi thứ về RuntimeException** nếu chưa xác định chính sách. Điều đó dễ vô tình gói cả lỗi lập trình và vi phạm bất biến.

### 5.3. Cách C: Tạo functional interface riêng với throws phù hợp

Khi callback có hợp đồng I/O rõ ràng, tạo một SAM có checked exception được công bố:

~~~java
@FunctionalInterface
interface TextLoader {
    String load(Path path) throws IOException;
}
~~~

Bạn có thể truyền vào lambda:

~~~java
TextLoader loader = path -> Files.readString(path);
~~~

hoặc method reference:

~~~java
TextLoader loader = Files::readString;
~~~

Các đoạn minh họa này cần import **Path**, **Files**, **IOException** và được viết riêng hoặc trong ngữ cảnh phù hợp. Ưu điểm là caller đọc chữ ký **load(...) throws IOException** sẽ thấy khả năng lỗi cần xử lý. Nhược điểm: đối tượng TextLoader **không mặc nhiên là Function<Path,String>**; **Stream.map** vẫn yêu cầu Function, không trực tiếp chấp nhận interface mới.

Dùng cách này nếu lỗi I/O là một phần quan trọng của **hợp đồng API**, đặc biệt ở ranh giới đọc file, kết nối, truyền dữ liệu hoặc truy cập tài nguyên.

### 5.4. Cách D: Viết adapter rõ ràng giữa kiểu có throws và Function

Tạo một **IoFunction<T,R>** có SAM khai báo IOException, rồi chuyển nó thành Function bằng quy tắc bọc lỗi. Adapter giúp tránh lặp lại cùng một try/catch ở mọi pipeline, nhưng cần được đặt tên và tài liệu hóa để caller biết checked IOException sẽ xuất hiện dưới dạng UncheckedIOException.

~~~java
@FunctionalInterface
interface IoFunction<T, R> {
    R apply(T value) throws IOException;
}

static <T, R> Function<T, R> unchecked(IoFunction<T, R> action) {
    Objects.requireNonNull(action, "action");
    return value -> {
        try {
            return action.apply(value);
        } catch (IOException cause) {
            throw new UncheckedIOException(cause);
        }
    };
}
~~~

Đây là **đoạn API minh họa**, giả định đặt phương thức **unchecked** trong một lớp và import **Objects**, **Function**, **IOException**, **UncheckedIOException**. Nó không phải chương trình Java độc lập. Bên trong adapter, IOException được bắt, nên lambda trả về phù hợp Function.apply.

**Không nhầm:** Adapter giúp chuyển kiểu theo **chính sách exception**; nó không làm thay đổi signature **throws** của Function.

## 6. Ví dụ Java 17 chạy được: cùng một I/O qua hai hợp đồng

Tạo tệp **CheckedLambdaDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

@FunctionalInterface
interface TextLoader {
    String load(Path path) throws IOException;
}

public class CheckedLambdaDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("checked-lambda-", ".txt");
        try {
            Files.writeString(file, "Xin chào\n");

            TextLoader checked = Files::readString;

            Function<Path, String> wrapped = path -> {
                try {
                    return Files.readString(path);
                } catch (IOException cause) {
                    throw new UncheckedIOException(cause);
                }
            };

            System.out.println("checked: "
                    + checked.load(file).strip());
            System.out.println("wrapped: "
                    + wrapped.apply(file).strip());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 CheckedLambdaDemo.java
java CheckedLambdaDemo
~~~

Stdout trên môi trường có quyền tạo/đọc/xóa tệp tạm:

~~~text
checked: Xin chào
wrapped: Xin chào
~~~

**Phân tích từng ranh giới:**

1. **Files.createTempFile** và **Files.writeString** có thể ném IOException trong main; main khai báo **throws IOException** nên chúng được phép truyền lên caller.
2. **TextLoader.checked** dùng method reference **Files::readString**. SAM **load(Path) throws IOException** cho phép ngoại lệ tương ứng.
3. **Function<Path,String> wrapped** không khai báo checked exception. Lambda bắt IOException rồi ném **UncheckedIOException**, nên hợp đồng Function được tôn trọng.
4. **checked.load(file)** là lời gọi tới SAM khai báo checked exception; main đã có **throws IOException** phù hợp.
5. **wrapped.apply(file)** không bắt buộc xử lý checked exception ở compile time; nếu lỗi I/O, UncheckedIOException truyền ra.
6. **finally** thực hiện xóa tệp tạm ngay cả khi phép đọc thất bại; nếu việc xóa cũng gặp IOException, lỗi đó có thể truyền ra khỏi main.

Kết quả stdout không phụ thuộc vào tên tệp tạm vì chương trình chỉ in nội dung đã ghi. **Mã ví dụ không có nghĩa IOException không thể xảy ra**; quyền truy cập filesystem vẫn là điều kiện môi trường cần có.

## 7. Checked exception và Stream: pipeline không mở rộng throws

Các API Stream phổ biến nhận functional interface chuẩn:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
Stream<T> filter(Predicate<? super T> predicate);
void forEach(Consumer<? super T> action);
~~~

Đây là **chữ ký mô tả rút gọn**, không phải các phương thức hoàn chỉnh để copy vào chương trình. Vì **Function**, **Predicate**, **Consumer** không khai báo IOException, đoạn dưới **không biên dịch**:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
List<String> contents = paths.stream()
        .map(Files::readString)
        .toList();
~~~

Giả định **paths** là List<Path> và đã import các lớp liên quan. Một method reference không được đặc cách: nó cũng phải tương thích với **throws** của SAM đích. Nếu **Files::readString** có IOException checked, **Stream.map** không tự bắt nó.

**Cách giải quyết:** chuyển IOException theo chính sách (ví dụ UncheckedIOException), hoặc xử lý I/O trước/sau pipeline bằng API có throws thích hợp. Nếu lỗi của một phần tử cần được giữ cùng dữ liệu thay vì dừng toàn bộ stream, thiết kế một kiểu kết quả như **ReadResult(content, error)**, với hợp đồng rõ về thành công/thất bại.

### 7.1. Lazy evaluation làm thay đổi thời điểm lỗi xuất hiện

Khi viết:

~~~java
Stream<String> pipeline = paths.stream().map(unchecked(Files::readString));
~~~

đây là **đoạn minh họa**, với adapter **unchecked** đã định nghĩa và các import cần thiết. Việc tạo pipeline thông thường **chưa đọc các file** vì map là intermediate operation. IOException được bọc thành UncheckedIOException sẽ xuất hiện **khi terminal operation thực sự đòi dữ liệu**, chẳng hạn **toList()**, không phải lúc khai báo pipeline.

Điều này có hai hệ quả:

- Nếu stream không được tiêu thụ, tác vụ I/O trong mapper có thể chưa chạy.
- Khi đọc dữ liệu có side effect hoặc gặp lỗi giữa chừng, một số phần tử có thể đã được xử lý trước khi exception xuất hiện. Không mặc định pipeline thất bại đồng nghĩa toàn bộ công việc được rollback.

Với parallel stream, ngoại lệ có thể xuất hiện trong luồng thực thi khác, và thứ tự/số lượng side effect không nên được dựa vào như hợp đồng nghiệp vụ. Giữ pipeline dữ liệu đơn giản và phân tách trách nhiệm I/O khi điều đó giúp kiểm soát lỗi tốt hơn.

## 8. Ví dụ Java 17: adapter IoFunction và Stream.map

Tạo tệp **CheckedStreamDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Stream;

@FunctionalInterface
interface IoFunction<T, R> {
    R apply(T input) throws IOException;
}

public class CheckedStreamDemo {
    static <T, R> Function<T, R> unchecked(IoFunction<T, R> action) {
        Objects.requireNonNull(action, "action");
        return value -> {
            try {
                return action.apply(value);
            } catch (IOException cause) {
                throw new UncheckedIOException(cause);
            }
        };
    }

    public static void main(String[] args) throws IOException {
        Path first = Files.createTempFile("source-a-", ".txt");
        Path second = Files.createTempFile("source-b-", ".txt");

        try {
            Files.writeString(first, "alpha\n");
            Files.writeString(second, "beta\n");

            IoFunction<Path, String> read = Files::readString;

            List<String> contents = Stream.of(first, second)
                    .map(unchecked(read))
                    .map(String::strip)
                    .toList();

            System.out.println(contents);

            IoFunction<String, String> failing = value -> {
                throw new IOException("invalid input");
            };

            try {
                unchecked(failing).apply("x");
            } catch (UncheckedIOException failure) {
                System.out.println("cause: "
                        + failure.getCause().getMessage());
            }
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CheckedStreamDemo.java
java CheckedStreamDemo
~~~

Stdout khi các thao tác tệp tạm thành công:

~~~text
[alpha, beta]
cause: invalid input
~~~

**Tại sao mã hợp lệ?**

- **IoFunction<Path,String> read = Files::readString** hợp lệ vì SAM khai báo IOException.
- **unchecked(read)** trả **Function<Path,String>** để Stream.map chấp nhận. Bên trong Function, IOException được bọc và ném thành UncheckedIOException.
- **Stream.of(first, second)** duy trì thứ tự gặp cho stream tuần tự; **toList()** lấy hai nội dung sau khi strip xuống dòng.
- **failing** là IoFunction cố ý ném IOException; ở lần gọi thông qua adapter, chương trình bắt UncheckedIOException và lấy lại cause **IOException("invalid input")**.
- **finally** cố gắng xóa cả hai file, giúp ví dụ không để lại dữ liệu tạm trong trường hợp thông thường.

Mẫu này phù hợp khi chính sách dự kiến là **dừng pipeline lúc không đọc được dữ liệu**. Nếu cần tiếp tục và lưu danh sách tệp lỗi, một wrapper kiểu Result hoặc một vòng lặp try/catch trên từng file có thể rõ hơn. **Cách giải quyết exception là quyết định về hợp đồng nghiệp vụ**, không đơn thuần là mẹo sửa lỗi biên dịch.

## 9. Callable và Runnable: đối chiếu ngay trong thư viện chuẩn

Đây là hai functional interface dễ nhầm khi truyền công việc:

- **Runnable.run()** trả void và **không khai báo checked exception**.
- **Callable<V>.call() throws Exception** trả V và **cho phép checked exception** (bao gồm IOException).

Vì vậy:

~~~java
Callable<String> checked = () -> Files.readString(path);

// CỐ Ý KHÔNG BIÊN DỊCH:
// Runnable cannotDirectlyRead = () -> Files.readString(path);
~~~

Đoạn minh họa cần import Callable, Runnable, Files, Path và có biến path phù hợp. Dù kết quả trả về của Files.readString có thể được bỏ qua trong Runnable, **IOException checked vẫn không tương thích với Runnable.run**. Việc bỏ kết quả không bỏ nghĩa vụ xử lý checked exception.

Một chương trình ngắn **CallableExample.java**:

~~~java
import java.io.IOException;
import java.util.concurrent.Callable;

public class CallableExample {
    public static void main(String[] args) {
        Callable<String> task = () -> {
            throw new IOException("offline");
        };

        try {
            task.call();
        } catch (Exception failure) {
            System.out.println(failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac CallableExample.java
java CallableExample
~~~

Stdout:

~~~text
IOException: offline
~~~

Lưu ý **Callable.call** được khai báo **throws Exception**, nên caller bắt **Exception** cho mục đích ví dụ. Nếu đưa Callable vào **ExecutorService.submit**, checked exception trong task thường được truyền đến người chờ kết quả qua **ExecutionException** (khi gọi Future.get), chứ không được trực tiếp ném từ submit. Điều này là cơ chế báo lỗi của Executor/Future, **không phải** bằng chứng rằng Callable bỏ qua checked exception.

Tương tự, **CompletableFuture.supplyAsync** nhận Supplier không khai báo checked exception, nên I/O trong lambda phải được xử lý/bọc theo chính sách. Khi lấy kết quả, CompletableFuture có thể báo lỗi thông qua CompletionException hoặc ExecutionException tùy phương thức truy xuất kết quả.

## 10. `throws` của lambda không được viết ở mũi tên

Lambda không có cú pháp khai báo **throws** riêng gắn ngay sau tham số. Điều kiện checked exception đến từ SAM đích:

~~~java
@FunctionalInterface
interface IoTask {
    void execute() throws IOException;
}

IoTask task = () -> {
    throw new IOException("not available");
};
~~~

Đây là **đoạn minh họa** cần import IOException. **Không có cú pháp** như **() throws IOException -> {...}** để thêm quyền checked exception cho lambda.

Nếu viết method reference **service::load**, trình biên dịch cũng đối chiếu checked exception khai báo bởi phương thức load với SAM. Việc chỉ đổi từ lambda sang method reference **không** loại bỏ lỗi throws. Một method reference đến phương thức generic hoặc overload còn cần khớp kiểu tham số và kiểu kết quả tương tự những lambda thông thường.

### 10.1. Overload có thể làm kiểu đích thay đổi

Giả sử có hai overload khác nhau nhận Function và IoFunction. Lambda/method reference có thể tương thích với cả hai theo những cách khác nhau hoặc gây mơ hồ, tùy chữ ký cụ thể và ngữ cảnh. **Đừng trông chờ riêng việc lambda ném checked exception để luôn chọn đúng overload**. Nếu có khả năng mơ hồ, hãy xác định target type trước:

~~~java
IoFunction<Path, String> checkedReader = Files::readString;
// Truyền biến checkedReader vào overload nhận IoFunction.
~~~

Đoạn minh họa giả định đã khai báo IoFunction thích hợp. Việc đặt tên và khai báo kiểu rõ ràng giúp API dễ đọc hơn và giảm nguy cơ suy luận kiểu phức tạp.

### 10.2. SAM generic và ngoại lệ

Có thể tổng quát hóa:

~~~java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
~~~

Đây là **đoạn khai báo interface minh họa**. Khi gán **ThrowingFunction<Path,String,IOException>**, compiler cho phép IOException; khi gán **ThrowingFunction<Path,String,FileNotFoundException>**, compiler chỉ cho phép FileNotFoundException và các lớp con tương ứng.

Generic checked exception hữu ích trong thư viện helper nội bộ nhưng có thể khiến API phức tạp. Nếu chỉ cần một nghiệp vụ đọc tệp, **TextLoader throws IOException** dễ hiểu hơn ba tham số kiểu generic. Chọn mức độ trừu tượng dựa trên việc nó thực sự giúp caller xác định nghĩa vụ xử lý lỗi.

## 11. Không nên nuốt hoặc làm mất nguyên nhân gốc

Một số cách “sửa lỗi compile” dễ tạo bug vận hành:

| Cách làm | Vấn đề | Thay thế có chủ đích |
| --- | --- | --- |
| **catch(IOException e) { return null; }** | Có thể che dữ liệu lỗi; caller gặp NPE ở xa nguồn | Dùng kiểu Result/Optional nếu null có nghĩa rõ, hoặc ném lỗi thích hợp |
| **catch(Exception e) { return ""; }** | Gom mọi loại lỗi thành chuỗi rỗng | Bắt loại ngoại lệ cần thiết và định nghĩa fallback |
| **throw new RuntimeException(e.getMessage())** | Mất cause và stack trace gốc | **throw new UncheckedIOException(e)** với IOException; hoặc RuntimeException có cause |
| Khai báo **throws IOException** ở method chứa lambda và cho rằng đủ | Không thay đổi throws của SAM | Bắt trong lambda hoặc dùng SAM thích hợp |
| Ép kiểu **(Function<T,R>)** để hy vọng tránh lỗi | Cast không sửa checked exception không tương thích | Sửa đúng target type hoặc chọn adapter |
| **catch(Throwable)** để che mọi lỗi | Có thể bắt cả Error và làm lỗi hệ thống khó chẩn đoán | Bắt checked exception mong đợi, để lỗi khác theo chính sách |
| Bắt rồi tiếp tục im lặng trong Stream | Có thể xuất kết quả thiếu mà không ai biết | Báo lỗi có cấu trúc, log/metric được kiểm soát, hoặc dừng xử lý |

**Giữ nguyên cause** là yêu cầu quan trọng khi chuyển lỗi sang một lớp exception khác. Ví dụ **UncheckedIOException** chứa IOException gốc; code kiểm tra nguyên nhân có thể dùng **getCause()**, như chương trình ở trên.

Khi muốn xử lý lỗi theo từng bản ghi, một kết quả giàu ngữ nghĩa có thể tốt hơn ném exception cho toàn bộ pipeline:

~~~java
record ReadResult(Path path, String text, IOException error) {
    boolean successful() {
        return error == null;
    }
}
~~~

Đây là **kiểu record minh họa**. Một thiết kế thực tế cần định nghĩa rõ bất biến: khi thành công, text phải có giá trị; khi thất bại, error phải có giá trị. Không tự mặc định ba trường độc lập đã bảo đảm bất biến đó. Cấu trúc Result giúp không phải mất thông tin lỗi của từng nguồn dữ liệu, nhưng cũng đòi hỏi caller xử lý cả hai trường hợp.

## 12. Ngoại lệ của method reference có thể khó nhìn thấy hơn

Khi viết:

~~~java
TextLoader reader = Files::readString;
~~~

không có từ khóa throws nào hiện diện ở dòng gán, nhưng phương thức được tham chiếu vẫn có **throws IOException**. Trình biên dịch không chỉ so khớp kiểu tham số và giá trị trả về; nó còn kiểm tra checked exception theo SAM.

Ngược lại:

~~~java
Function<Path, String> reader = Files::readString;
~~~

đây là **ví dụ cố ý không biên dịch** (giả định import liên quan) vì Function.apply không cho IOException thoát. Đổi cách viết thành **path -> Files.readString(path)** cũng không hợp lệ.

Khi gặp lỗi ở method reference, hãy kiểm tra **khai báo của phương thức nguồn**, **target functional interface**, **SAM throws**, **các overload** và **ngoại lệ phát sinh từ thao tác chuyển đổi/lời gọi**. Không nên chỉ nhìn một dòng có dấu **::** rồi đoán rằng không có checked exception.

## 13. Thực hành kiểm thử cả thành công lẫn thất bại

Một bài test đủ tốt cần kiểm tra hai hướng:

1. **Success path:** lambda trả đúng kết quả khi không có lỗi I/O.
2. **Failure path:** checked exception được khai báo, bắt hoặc bọc đúng kiểu như hợp đồng; không vô tình biến lỗi thành kết quả thành công.

Các trường hợp nên có:

- **TextLoader**: tệp đọc được, **load** trả String dự kiến.
- **TextLoader**: tệp không đọc được hoặc không tồn tại, caller xử lý IOException theo hợp đồng.
- **Adapter unchecked**: IoFunction giả lập ném IOException, caller nhận **UncheckedIOException** với **getCause() instanceof IOException**.
- **Function fallback**: nếu có fallback, kiểm tra fallback chỉ xuất hiện trong ca được chính sách chấp nhận.
- **Stream lazy**: kiểm tra pipeline chỉ bắt đầu I/O khi terminal operation cần dữ liệu.
- **Cleanup**: tài nguyên I/O được đóng/xóa bằng **try-with-resources** hoặc **finally** phù hợp, kể cả khi có exception.

Với hàm không thuần và dữ liệu thay đổi được, unit test nên kiểm soát filesystem, thời điểm và nguồn dữ liệu. Chương trình học ở đây dùng tệp tạm để không phụ thuộc vào một đường dẫn cá nhân cố định.

### 13.1. Phân biệt compile-time với runtime

Có ba thời điểm khác nhau:

~~~text
1. Biên dịch:
   Lambda/method reference có checked exception phù hợp SAM không?
   → Không phù hợp: mã không biên dịch.

2. Tạo callback:
   Tạo lambda/method reference; thường chưa chạy thân xử lý I/O.
   → Không có nghĩa tệp đã được đọc thành công.

3. Gọi callback hoặc chạy terminal operation:
   Thực hiện I/O và có thể gặp IOException hoặc UncheckedIOException.
   → Caller xử lý theo hợp đồng đã chọn.
~~~

Đừng dùng một lần chạy thành công để kết luận rằng cấu trúc throws đã được thiết kế tốt, và đừng bắt lỗi chỉ ở nơi tạo callback rồi cho rằng lỗi đọc tệp sau này sẽ tự được bắt. Exception phát sinh khi thực thi hành vi cần được quản lý tại ranh giới thực sự thực thi hành vi đó.

## 14. Bài tập

### Bài 1: Nhận biết lỗi biên dịch

Phân loại các dòng sau. Giả định **path** là Path và đã import đầy đủ:

~~~java
Callable<String> a = () -> Files.readString(path);
Supplier<String> b = () -> Files.readString(path);
TextLoader c = Files::readString;
Function<Path, String> d = Files::readString;
~~~

Đây là **tập ví dụ có những dòng cố ý không biên dịch**; không copy nguyên khối vào file thực hành. **Đáp án:** a và c hợp lệ về checked exception; b và d không hợp lệ vì Supplier.get và Function.apply không khai báo IOException.

### Bài 2: Chuyển cách báo lỗi

Viết một **Function<Path,String>** đọc tệp, nhưng trong catch(IOException) ném **UncheckedIOException** giữ cause. Viết thêm kiểm thử gọi Function với một IoFunction giả lập luôn ném IOException và kiểm tra nguyên nhân gốc.

### Bài 3: Chọn hợp đồng phù hợp

Một thư viện cần truyền callback đọc tệp và caller phải biết nó có thể thất bại vì IOException. Hãy giải thích vì sao **TextLoader.load(Path) throws IOException** có thể phù hợp hơn **Function<Path,String>**, và nhược điểm khi dùng trực tiếp trong Stream.map.

### Bài 4: Gắn adapter vào pipeline

Viết **Stream.of(path1, path2).map(unchecked(Files::readString)).toList()** với phương thức unchecked nhận IoFunction. Giải thích vì sao exception có thể xuất hiện khi gọi **toList()**, không phải khi tạo pipeline.

### Bài 5: Đối chiếu throws của lớp cha và interface

Tạo interface có SAM **throws IOException**, rồi thử lambda ném FileNotFoundException, IOException và Exception. Cái nào hợp lệ? Giải thích bằng quan hệ kế thừa giữa các checked exception.

## 15. Ghi nhớ

- **Lambda và method reference phải tuân thủ throws của SAM đích**. Kiểu trả về tương thích **chưa đủ**.
- **Function, Consumer, Predicate, Supplier, Runnable** không cho checked IOException thoát trực tiếp; **Callable.call throws Exception** và custom SAM **throws IOException** có thể cho phép.
- **throws của phương thức bao ngoài không mở rộng throws của lambda**; cũng không thể tự thêm cú pháp throws sau mũi tên lambda.
- Khi dùng API chuẩn không cho checked exception, hãy **bắt và xử lý**, **bọc có giữ cause**, hoặc tạo **adapter rõ ràng**; khi hợp đồng cần checked I/O, hãy cân nhắc một functional interface riêng.
- **Method reference không bỏ qua ngoại lệ**, **Stream.map không mở rộng throws** và **laziness** có thể khiến lỗi chỉ xuất hiện khi tiêu thụ pipeline.
- Chọn cách xử lý lỗi dựa trên **ý nghĩa nghiệp vụ**, không phải chỉ để “hết lỗi biên dịch”.

Câu hỏi cốt lõi trước khi gán lambda là: **“SAM của kiểu đích cho phép những checked exception nào thoát ra, và người gọi sẽ xử lý chúng bằng hợp đồng gì?”**