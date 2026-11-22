# Bọc ngoại lệ và giữ nguyên nguyên nhân trong lập trình hàm Java

Khi một chương trình Java gọi nhiều tầng phương thức, nhất là trong **lambda**, **method reference** và **Stream API**, lỗi thường xuất hiện ở tầng thấp nhưng cần được xử lý tại tầng có đủ ngữ cảnh nghiệp vụ. **Bọc ngoại lệ (exception wrapping)** là tạo ngoại lệ mới phù hợp với ranh giới API và gắn ngoại lệ ban đầu làm **nguyên nhân (cause)**, thay vì xóa mất thông tin chẩn đoán.

Công thức điển hình:

~~~java
try {
    return parse(rawValue);
} catch (NumberFormatException cause) {
    throw new IllegalArgumentException("Invalid amount: " + rawValue, cause);
}
~~~

Ý nghĩa: “Tại tầng này, yêu cầu không hợp lệ” **vì** “ở tầng thấp hơn, chuỗi không thể chuyển thành số”. Constructor có đối số cause giúp người điều tra truy ngược cả **ngữ cảnh lỗi** lẫn **ngoại lệ gốc và stack trace của nó**.

Đây là bài học tập trung vào cơ chế bọc ngoại lệ, bảo toàn nguyên nhân, lựa chọn checked/unchecked exception khi thao tác với functional interface và cách tránh những lỗi khiến việc debug khó khăn.

## 1. Tại sao phải bọc ngoại lệ?

Giả sử một hệ thống nhận số tiền qua chuỗi và chuyển sang int. Integer.parseInt("oops") ném **NumberFormatException**. Thông tin này chính xác về mặt kỹ thuật nhưng chưa cho biết chuỗi đó là “số tiền của đơn hàng nào”.

Nếu quy tắc nghiệp vụ muốn báo lỗi với ngữ cảnh rõ hơn:

~~~java
static int parseAmount(String rawAmount) {
    try {
        return Integer.parseInt(rawAmount);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
            "Invalid amount: " + rawAmount,
            cause
        );
    }
}
~~~

Tầng gọi nhận **IllegalArgumentException**: đầu vào không phù hợp hợp đồng; người debug vẫn truy cập **NumberFormatException** qua error.getCause(). Khi ghi stack trace đầy đủ, Java thể hiện chuỗi nguyên nhân bằng các khối **Caused by:**.

Bọc ngoại lệ có ích khi:

- **Thêm ngữ cảnh:** lỗi xảy ra khi đọc tài liệu, xử lý đơn hàng, giải mã dữ liệu, nạp cấu hình hoặc truy xuất bản ghi.
- **Chuyển mức trừu tượng:** tầng nghiệp vụ không muốn mọi caller phải biết chi tiết API tệp, parser hoặc cơ sở dữ liệu.
- **Thích nghi kiểu ngoại lệ:** API callback như Function.apply không khai báo checked exception.
- **Giữ bằng chứng:** thông điệp và stack trace của lỗi gốc vẫn được liên kết để truy tìm nguồn phát sinh.

Bọc ngoại lệ **không có nghĩa** mọi catch đều phải tạo ngoại lệ mới. Nếu ngoại lệ đã đúng nghĩa tại ranh giới đang xét, cho nó truyền lên có thể đơn giản và chính xác hơn.

## 2. Phân biệt message, stack trace và cause

Một Throwable trong Java có các thông tin liên quan:

| Thành phần | Phương thức | Chức năng |
| --- | --- | --- |
| Kiểu ngoại lệ | getClass() | Loại lỗi mà tầng hiện tại muốn báo |
| Thông điệp | getMessage() | Mô tả lỗi, thường có ngữ cảnh |
| Nguyên nhân | getCause() | Throwable thấp hơn dẫn đến lỗi này |
| Stack trace | getStackTrace(), printStackTrace() | Vị trí/call stack khi ngoại lệ được tạo hoặc ném |
| Suppressed exceptions | getSuppressed() | Các ngoại lệ phụ bị giữ lại, ví dụ khi đóng tài nguyên thất bại |

Khi gọi:

~~~java
throw new IllegalArgumentException("Bad price", cause);
~~~

Java tạo ngoại lệ mới với stack trace ở nơi bọc, đồng thời **giữ tham chiếu tới cause**. Vì vậy thông tin gọi tầng thấp không biến mất. Chuỗi cause cho phép đọc lỗi từ ranh giới nghiệp vụ trở về nguồn.

Hai đối tượng ngoại lệ **không phải cùng một instance**: ngoại lệ bọc có kiểu, message và stack trace riêng, còn ngoại lệ gốc giữ dữ liệu ban đầu.

Ví dụ:

~~~java
try {
    Integer.parseInt("not-a-number");
} catch (NumberFormatException original) {
    IllegalArgumentException outer =
        new IllegalArgumentException("Invalid quantity", original);
    System.out.println(outer.getCause() == original); // true
}
~~~

getCause() có thể trả null nếu ngoại lệ được tạo không có nguyên nhân. Không giả định mọi ngoại lệ đều có cause; khi trình bày lỗi phải kiểm tra null.

### 2.1. Message không phải cause

Cách viết gây mất dữ liệu:

~~~java
catch (IOException error) {
    throw new IllegalStateException(error.getMessage());
}
~~~

IllegalStateException mới chỉ mang **chuỗi thông điệp**. getCause() sẽ là null và ngoại lệ gốc không còn được nối vào chuỗi stack trace theo cơ chế cause.

Cách đúng nếu cần chuyển nghĩa:

~~~java
catch (IOException error) {
    throw new IllegalStateException("Unable to load configuration", error);
}
~~~

Nếu không cần thay đổi ý nghĩa hoặc hợp đồng, có thể để IOException đi lên:

~~~java
static String readConfig(java.nio.file.Path path) throws IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Không nên bọc một lỗi nhiều lần ở mọi tầng chỉ để thêm câu “Error occurred”. Hãy thêm ngữ cảnh có giá trị **tại ranh giới mà lớp đó hiểu ý nghĩa của thao tác**.

### 2.2. Message của wrapper và message của cause

Thông điệp của ngoại lệ bọc nên trả lời “**thao tác nào thất bại**?”, còn cause mô tả “**hỏng ở bước kỹ thuật nào**?”. Ví dụ:

~~~java
throw new IllegalStateException(
    "Failed to initialize product catalog",
    original
);
~~~

Không cần copy toàn bộ stack trace sang message. Stack trace cần được trình bày qua cơ chế logging hoặc in lỗi phù hợp. Hạn chế đưa thông tin nhạy cảm như mật khẩu, access token, dữ liệu cá nhân hoặc nguyên văn payload bí mật vào message: cause có thể được ghi log hoặc hiển thị ngoài ý muốn nếu xử lý không cẩn thận.

## 3. Constructors và cách gắn cause

Nhiều exception chuẩn có constructor nhận một chuỗi và một Throwable:

~~~java
new IllegalArgumentException("Invalid field", cause);
new IllegalStateException("Invalid state", cause);
new RuntimeException("Operation failed", cause);
new java.io.UncheckedIOException("Read failed", ioCause);
~~~

Tùy lớp ngoại lệ, có thể có constructor chỉ nhận Throwable hoặc có thêm các phiên bản khác. **Không phải mọi exception class có cùng bộ constructor**, vì vậy kiểm tra chữ ký của loại cụ thể trước khi sử dụng.

Với ngoại lệ tùy chỉnh:

~~~java
final class OrderProcessingException extends RuntimeException {
    OrderProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Khi gọi new OrderProcessingException("Cannot process order", cause), caller có thể đọc getCause() để xem lỗi gốc. Nên đặt tên exception theo cấp trừu tượng, không tạo một lớp custom mới cho mọi catch nhỏ.

### 3.1. initCause cho API cũ

Một số kiểu ngoại lệ hoặc API cũ không có constructor nhận cause. Throwable.initCause(cause) là cơ chế đặt nguyên nhân trong trường hợp phù hợp:

~~~java
Exception wrapped = new Exception("Legacy operation failed");
wrapped.initCause(original);
throw wrapped;
~~~

Đây là **đoạn minh họa cần được đặt trong ngữ cảnh catch/method có khai báo throws**. initCause chỉ được dùng trong những trạng thái hợp lệ; không thể gán lại nguyên nhân tùy tiện sau khi đã được khởi tạo, và có thể ném IllegalStateException hoặc IllegalArgumentException nếu vi phạm hợp đồng.

**Ưu tiên constructor nhận cause** khi có sẵn. Nó rõ ràng, khó quên và tạo một đối tượng đã có đầy đủ mối liên hệ nguyên nhân ngay khi khởi tạo.

## 4. Checked và unchecked exception trong functional interface

Đây là điểm đặc biệt quan trọng của Java functional programming.

Một số functional interface chuẩn:

~~~java
java.util.function.Function<T, R>       // R apply(T value)
java.util.function.Consumer<T>          // void accept(T value)
java.util.function.Predicate<T>         // boolean test(T value)
java.util.function.Supplier<T>          // T get()
~~~

Các SAM này **không khai báo checked exception**. Vì vậy một lambda gọi trực tiếp phương thức throws IOException không thể được dùng làm Function nếu không bắt hoặc chuyển ngoại lệ.

Ví dụ không hợp lệ:

~~~java
// KHÔNG BIÊN DỊCH nếu readString ném IOException chưa xử lý.
java.util.function.Function<java.nio.file.Path, String> reader =
    path -> java.nio.file.Files.readString(path);
~~~

Files.readString(Path) khai báo IOException, trong khi Function.apply không có throws IOException.

### 4.1. Bọc checked exception ở ranh giới lambda

Có thể làm ngay trong lambda:

~~~java
java.util.function.Function<java.nio.file.Path, String> reader =
    path -> {
        try {
            return java.nio.file.Files.readString(path);
        } catch (IOException cause) {
            throw new java.io.UncheckedIOException(
                "Cannot read file: " + path,
                cause
            );
        }
    };
~~~

Lambda giờ phù hợp với Function<Path,String> vì UncheckedIOException là một **RuntimeException**, không phải checked exception. Điểm quan trọng là **truyền cause**: người xử lý phía ngoài còn biết đây là IOException nào.

UncheckedIOException là loại chuẩn dành cho trường hợp chuyển **IOException** sang ngoại lệ unchecked; không dùng nó để bọc SQLException hoặc mọi Exception không liên quan. Với checked exception khác, có thể dùng một runtime exception có ý nghĩa phù hợp, hoặc định nghĩa API trả kết quả lỗi một cách tường minh.

**Cân nhắc kiến trúc:** chuyển checked thành unchecked không có nghĩa lỗi biến mất hoặc được xử lý. Nó chỉ thay đổi cơ chế bắt buộc khai báo tại compile time; caller vẫn phải xác định nơi xử lý, log và phục hồi.

### 4.2. Tại sao không bắt Exception một cách tùy tiện?

Ví dụ không nên dùng:

~~~java
java.util.function.Function<String, String> action =
    value -> {
        try {
            return execute(value);
        } catch (Exception error) {
            return "";
        }
    };
~~~

Đây là mã minh họa; execute là phương thức giả định. catch Exception quá rộng và trả chuỗi rỗng khiến lỗi đọc dữ liệu, lỗi lập trình hoặc lỗi nghiệp vụ bị biến thành một kết quả có vẻ hợp lệ. Không còn bằng chứng để chẩn đoán lỗi.

Cũng không nên bọc mọi Exception vào RuntimeException chung nếu một số loại cần được xử lý đặc biệt. Hãy **bắt loại ngoại lệ bạn thực sự có thể xử lý hoặc chuyển nghĩa**. Để lỗi lập trình (như NullPointerException không mong đợi) lộ ra thay vì bị che giấu, trừ khi ranh giới yêu cầu chính sách có chủ đích.

## 5. Adapter để tái sử dụng lambda có checked exception

Khi nhiều callback đều cần gọi phương thức throws IOException, lặp try/catch ở từng lambda làm code dài. Có thể định nghĩa functional interface riêng có throws:

~~~java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}
~~~

Sau đó tạo adapter chuyển IOFunction thành Function:

~~~java
static <T, R> java.util.function.Function<T, R> unchecked(
        IOFunction<T, R> function) {
    java.util.Objects.requireNonNull(function);
    return value -> {
        try {
            return function.apply(value);
        } catch (IOException cause) {
            throw new java.io.UncheckedIOException("I/O in pipeline", cause);
        }
    };
}
~~~

Lợi ích:

1. **Nguồn lỗi vẫn được lưu:** UncheckedIOException.getCause() là IOException gốc.
2. **Mã xử lý Stream dễ đọc:** map(unchecked(MyClass::readData)).
3. **Bắt đúng loại checked exception:** adapter xử lý IOException, không tự nuốt các ngoại lệ khác.
4. **Kiểm thử tách biệt:** có thể kiểm tra đường thành công và lỗi của adapter.

Tuy nhiên, adapter vẫn làm callback có thể gây **I/O và tác dụng phụ**, nên không mặc nhiên là hàm thuần hay thread-safe. Nếu thích hợp, tách đọc dữ liệu ra trước rồi dùng Stream xử lý dữ liệu đã có trong bộ nhớ. Nếu cần giữ checked exception trong hợp đồng của một tầng API, có thể không nên chuyển sang Function chuẩn ngay từ đầu.

### 5.1. Một adapter tổng quát không phải giấy phép bắt Throwable

Java cho phép khai báo interface như:

~~~java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
~~~

Nhưng nếu viết adapter chung, cần quyết định chính sách chuyển từng E sang runtime exception, ghi thêm context và bảo toàn cause. Bắt Throwable quá rộng còn có thể can thiệp Error nghiêm trọng và các cơ chế điều khiển khác. Không nên tự phát triển “sneaky throw” chỉ để lách checked exception, vì caller có thể mất khả năng hiểu hợp đồng lỗi ở compile time.

### 5.2. Việc quấn lỗi không thay đổi tính lazy của Stream

~~~java
List<String> results = paths.stream()
    .map(unchecked(path -> Files.readString(path)))
    .toList();
~~~

Ví dụ là đoạn minh họa cần import Files, List và kiểu paths phù hợp. Việc tạo pipeline bằng map **chưa nhất thiết thực hiện đọc tệp**. IOException được bọc khi hàm thực sự được gọi trong quá trình thực hiện terminal operation như toList().

Nếu pipeline có short-circuit như findFirst, callback có thể không chạy trên mọi phần tử; vì thế đừng coi lambda bên trong Stream là nơi chắc chắn thực hiện mọi yêu cầu ghi log hay I/O. Nếu Stream song song, các ngoại lệ có thể xuất hiện từ worker thread và thứ tự phần tử bị lỗi nào được quan sát không luôn như stream tuần tự.

## 6. Bọc ngoại lệ để thêm ngữ cảnh nghiệp vụ

Một ngoại lệ parser thường biết “text không hợp lệ”, nhưng không biết nó thuộc bản ghi nào. Khi bọc, hãy bổ sung thông tin có ích ở tầng hiện tại:

~~~java
static int parseQuantity(String orderId, String rawQuantity) {
    try {
        return Integer.parseInt(rawQuantity);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
            "Invalid quantity in order " + orderId,
            cause
        );
    }
}
~~~

Cấp nghiệp vụ đọc được đơn hàng cụ thể, còn getCause() giữ NumberFormatException gốc.

Trong một chuỗi nhiều tầng:

~~~text
OrderService: cannot create order
    caused by CatalogException: cannot resolve product
        caused by IOException: catalog source unavailable
~~~

Đây là mô tả cấu trúc, không phải output cố định của JVM. Mỗi tầng **chỉ nên bọc khi thêm ý nghĩa hoặc đổi hợp đồng lỗi một cách có chủ đích**. Bọc nhiều tầng nhưng chỉ lặp "failed" gây nhiễu stack trace, không giúp debug.

Một quy tắc thực dụng:

- Nếu tầng hiện tại **có thể phục hồi**, hãy xử lý cụ thể và tiếp tục khi an toàn.
- Nếu tầng hiện tại **không thể phục hồi** nhưng có thêm ngữ cảnh hữu ích, hãy bọc đúng loại ngoại lệ và giữ cause.
- Nếu tầng hiện tại **không thể thêm gì**, cứ để ngoại lệ phù hợp truyền lên.
- Ở ranh giới cuối (HTTP, CLI, job runner), chuyển lỗi thành phản hồi hoặc trạng thái thích hợp; ghi log với chuỗi nguyên nhân, nhưng không trả toàn bộ stack trace nội bộ cho người dùng cuối.

## 7. Bọc đúng loại và xử lý các ngoại lệ đặc biệt

### 7.1. IOException và UncheckedIOException

Dùng UncheckedIOException khi thực sự bọc IOException:

~~~java
catch (IOException cause) {
    throw new UncheckedIOException("Cannot load document", cause);
}
~~~

Người bắt UncheckedIOException có thể lấy nguyên nhân có kiểu IOException bằng getCause(), thuận tiện cho xử lý riêng nhóm lỗi I/O.

### 7.2. NumberFormatException và IllegalArgumentException

NumberFormatException **đã là** subclass của IllegalArgumentException. Nếu tầng gọi cần biết lỗi parse cụ thể mà không có ngữ cảnh bổ sung, có thể truyền nguyên ngoại lệ. Nếu cần giải thích dữ liệu nghiệp vụ nào sai, bọc thêm IllegalArgumentException với cause có thể có giá trị.

~~~java
catch (NumberFormatException cause) {
    throw new IllegalArgumentException("Invalid tax percentage", cause);
}
~~~

Đừng bọc chỉ vì một nguyên tắc máy móc; đánh giá thông tin tăng thêm và loại exception mà API muốn công bố.

### 7.3. InterruptedException cần bảo toàn tín hiệu ngắt

InterruptedException có ý nghĩa đặc biệt trong concurrency. Một số thao tác chờ có thể xóa trạng thái interrupted khi ném InterruptedException. Nếu buộc phải chuyển nó sang unchecked exception và không thể tiếp tục ném checked exception, thông thường cần **khôi phục interrupt flag** trước khi ném:

~~~java
catch (InterruptedException cause) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", cause);
}
~~~

Đây là đoạn minh họa đặt trong khối try/catch phù hợp. Tùy hợp đồng hệ thống, có thể chọn hủy tác vụ hoặc dùng ngoại lệ mang nghĩa cancellation; không coi một lần interrupt đơn thuần là lỗi I/O thường. **Giữ cause không thay thế việc phục hồi interrupt status** khi cần.

### 7.4. Không tùy tiện bắt Error

Không dùng catch (Throwable) để bọc tất cả mọi thứ trong một RuntimeException. Throwable bao gồm Error như OutOfMemoryError và LinkageError, thường không nên được ứng dụng bắt/chuyển đổi phổ quát. Hãy giới hạn nhóm ngoại lệ có thể xử lý và giữ chính sách rõ ràng.

### 7.5. CompletionException và ExecutionException

Trong code bất đồng bộ, **CompletableFuture.join()** có thể ném CompletionException, còn Future.get() thường làm lộ ExecutionException cho lỗi của tác vụ. Các wrapper này có thể chứa nguyên nhân gốc qua getCause(). Khi debug, kiểm tra chuỗi cause, đừng dừng ở thông báo "CompletionException" hoặc "ExecutionException".

Không nên tự ý unwrap rồi ném một Throwable checked ở nơi hợp đồng không cho phép. Giữ đúng loại lỗi và chính sách API ở ranh giới.

## 8. Cause khác suppressed exception như thế nào?

Hai cơ chế dễ bị nhầm:

- **Cause:** trả lời "ngoại lệ nào gây ra hoặc là cơ sở cho ngoại lệ hiện tại?".
- **Suppressed exception:** lưu ngoại lệ bổ sung mà chương trình không muốn thay thế ngoại lệ chính, thường gặp khi **try-with-resources** đang có lỗi ở phần thân rồi thao tác close() cũng gặp lỗi.

Ví dụ minh họa cấu trúc:

~~~java
try (SomeResource resource = openResource()) {
    performWork(resource); // Có thể ném ngoại lệ chính.
}
// Nếu close() cũng thất bại, lỗi đóng có thể trở thành
// suppressed exception của ngoại lệ chính.
~~~

Đây là pseudocode Java có những kiểu/phương thức giả định, không phải chương trình độc lập.

Đọc các ngoại lệ suppressed bằng error.getSuppressed(). Đừng dùng initCause để cố “đổi” ngoại lệ phụ thành nguyên nhân, vì hai quan hệ mang ý nghĩa khác nhau.

**Quan trọng:** bọc một ngoại lệ bằng constructor nhận cause sẽ giữ đối tượng ngoại lệ gốc, bao gồm thông tin suppressed gắn trên chính nó. Khi ghi log, nên dùng logger có hỗ trợ đối số Throwable để in toàn bộ cause và suppressed thay vì chỉ in getMessage().

## 9. Chương trình Java 17+ hoàn chỉnh

Ví dụ này tập hợp ba ý quan trọng:

1. Phương thức parseAmount bắt NumberFormatException, bọc thành IllegalArgumentException và **giữ cause**.
2. Functional interface IOFunction<T,R> cho phép khai báo **throws IOException**; adapter unchecked đổi sang Function<T,R> cho Stream.
3. Chương trình bắt ngoại lệ ở ranh giới main, in **thông điệp wrapper**, **loại cause** và **thông điệp cause** để chứng minh mối liên hệ vẫn tồn tại.

Tạo tệp **CausePreservingDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Stream;

public class CausePreservingDemo {
    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(IOFunction<T, R> function) {
        Objects.requireNonNull(function);
        return value -> {
            try {
                return function.apply(value);
            } catch (IOException cause) {
                throw new UncheckedIOException("I/O in pipeline", cause);
            }
        };
    }

    static String load(String key) throws IOException {
        if ("missing".equals(key)) {
            throw new IOException("resource not found");
        }
        return key.toUpperCase(Locale.ROOT);
    }

    static int parseAmount(String raw) {
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new IllegalArgumentException("Invalid amount: " + raw, cause);
        }
    }

    public static void main(String[] args) {
        List<Integer> valid = Stream.of("10", "20")
            .map(CausePreservingDemo::parseAmount).toList();
        System.out.println("valid=" + valid);

        try {
            Stream.of("10", "oops", "30")
                .map(CausePreservingDemo::parseAmount).toList();
        } catch (IllegalArgumentException error) {
            System.out.println("parse message=" + error.getMessage());
            System.out.println("parse cause=" +
                error.getCause().getClass().getSimpleName());
        }

        List<String> loaded = Stream.of("alpha", "beta")
            .map(unchecked(CausePreservingDemo::load)).toList();
        System.out.println("loaded=" + loaded);

        try {
            Stream.of("alpha", "missing")
                .map(unchecked(CausePreservingDemo::load)).toList();
        } catch (UncheckedIOException error) {
            System.out.println("io message=" + error.getMessage());
            System.out.println("io cause=" +
                error.getCause().getClass().getSimpleName());
            System.out.println("io detail=" + error.getCause().getMessage());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp bằng **JDK 17 trở lên**:

~~~bash
javac CausePreservingDemo.java
java CausePreservingDemo
~~~

**Stdout chính xác:**

~~~text
valid=[10, 20]
parse message=Invalid amount: oops
parse cause=NumberFormatException
loaded=[ALPHA, BETA]
io message=I/O in pipeline
io cause=IOException
io detail=resource not found
~~~

### Giải thích kết quả

- Hai số 10, 20 hợp lệ và đi qua Stream.map bình thường.
- "oops" gây NumberFormatException, được parseAmount bọc trong IllegalArgumentException với thông điệp mô tả dữ liệu sai. getCause().getClass().getSimpleName() trả NumberFormatException.
- Hai khóa alpha và beta đi qua load, được đổi thành chữ hoa. Đây là nhánh thành công của adapter.
- Khi gặp "missing", load ném IOException("resource not found"). Adapter bắt đúng IOException và ném UncheckedIOException("I/O in pipeline", cause).
- Ở ranh giới main, ngoại lệ được bắt; message thuộc **wrapper**, còn loại IOException và thông điệp "resource not found" được lấy từ **cause**.
- Vì chương trình in các thành phần được chọn thay vì printStackTrace(), stdout ngắn và ổn định. Trong hệ thống thực, logger có thể ghi toàn bộ stack trace của wrapper để hiển thị các khối Caused by.

Phương thức load trong chương trình là mô phỏng nguồn dữ liệu để ví dụ tự chạy được, **không đọc tệp thật**. Trong ứng dụng thực, có thể thay load bằng Files.readString(Path) hoặc một API khai báo throws IOException, vẫn giữ nguyên nguyên tắc adapter và bảo toàn cause.

## 10. Kiểm thử việc giữ nguyên nguyên nhân

Khi test exception wrapping, đừng chỉ assert rằng một exception nào đó được ném. Hãy xác minh cả **loại wrapper, message có ý nghĩa và cause gốc**.

Ví dụ kiểm thử theo phong cách JUnit 5, với các class có thể truy cập được:

~~~java
// Minh họa assertion JUnit 5, không phải chương trình độc lập.
IllegalArgumentException error = assertThrows(
    IllegalArgumentException.class,
    () -> CausePreservingDemo.parseAmount("bad")
);

assertTrue(error.getMessage().contains("Invalid amount"));
assertInstanceOf(NumberFormatException.class, error.getCause());
~~~

Đoạn này cần import các assertion tương ứng của JUnit 5. Nếu phương thức có ràng buộc về ngữ cảnh như orderId hoặc file path, test cũng nên kiểm tra thông điệp wrapper chứa ngữ cảnh cần thiết, **không kiểm tra toàn bộ thông điệp hệ thống có thể thay đổi theo JDK** khi không cần.

Với adapter I/O, có thể dùng IOFunction giả ném IOException cố định và kiểm tra:

~~~java
// Ý tưởng unit test, đặt trong ngữ cảnh có unchecked và IOFunction.
IOException original = new IOException("broken stream");
IOFunction<String, String> failing = value -> {
    throw original;
};

UncheckedIOException wrapped = assertThrows(
    UncheckedIOException.class,
    () -> unchecked(failing).apply("input")
);

assertSame(original, wrapped.getCause());
~~~

Điểm quan trọng ở đây là **assertSame**: cùng instance IOException gốc được giữ làm cause, thay vì tạo một IOException mới chỉ sao chép message. Trong test tích hợp thực tế, cần kiểm tra thêm chính sách log, mapping lỗi và không rò rỉ thông tin nhạy cảm.

### 10.1. Kiểm thử đường thành công và lỗi

Một adapter tốt phải xử lý cả hai nhánh:

- **Thành công:** trả đúng giá trị mà IOFunction cung cấp, không tự thêm hoặc mất dữ liệu.
- **Thất bại:** ném đúng loại unchecked exception đã cam kết, cause chính là checked exception gốc.
- **Không che ngoại lệ khác:** RuntimeException không liên quan có thể truyền lên nếu adapter chỉ catch IOException.
- **Biên null:** nếu API cấm callback null, kiểm tra rõ sớm bằng Objects.requireNonNull; đừng tạo lambda rồi chỉ phát hiện null vào lúc xử lý phần tử.

Kiểm thử này quan trọng hơn việc chỉ chạy một ví dụ với đầu vào hợp lệ: nếu adapter vô tình viết new RuntimeException(e.getMessage()), đường thành công vẫn chạy, nhưng thông tin gốc bị mất.

## 11. Logging và quan sát lỗi trong ứng dụng thực

Không cần vừa ghi log lỗi đầy đủ ở tầng parser, vừa bọc và log thêm ở tầng repository, vừa log ở tầng service và cuối cùng log ở HTTP handler: một lỗi có thể biến thành nhiều bản ghi trùng lặp.

Quy tắc thường hữu ích:

1. **Bọc** khi có thêm ý nghĩa/ngữ cảnh hoặc cần thay hợp đồng exception.
2. **Để truyền lên** khi chưa có chính sách phục hồi.
3. **Ghi log một lần tại ranh giới phù hợp**, truyền trực tiếp Throwable cho logger để giữ stack trace/cause/suppressed.
4. **Trả thông tin an toàn** cho client. Mã lỗi công khai nên dễ hiểu nhưng không làm lộ tài khoản, token hoặc chi tiết hệ thống nội bộ.

Minh họa theo kiểu một logging API thông dụng:

~~~java
// Minh họa API logging; "logger" do ứng dụng cung cấp.
logger.error("Failed to process order {}", orderId, exception);
~~~

Cần dùng đúng overload của thư viện logging đang sử dụng. Không chỉ ghi exception.getMessage() rồi bỏ Throwable nếu muốn bảo toàn stack trace.

Về mặt vận hành, nên cân nhắc **context hợp lệ và có kiểm soát** (mã tác vụ, ID không nhạy cảm, loại thao tác, mã lỗi). Bọc ngoại lệ không được dùng để đưa dữ liệu riêng tư vào log hoặc response mà không được phép.

## 12. Những lỗi phổ biến khi bọc ngoại lệ

**Lỗi 1 — làm mất cause:** throw new RuntimeException(error.getMessage()). Cách sửa là truyền nguyên Throwable vào constructor hỗ trợ cause.

**Lỗi 2 — tạo lỗi mới nhưng không thêm ngữ cảnh:** bọc IOException thành RuntimeException("error", cause) qua nhiều tầng. Chỉ bọc tại ranh giới có ý nghĩa và chọn thông điệp mô tả thao tác.

**Lỗi 3 — nuốt lỗi:** catch (Exception e) { return null; } có thể khiến pipeline trả dữ liệu sai mà caller không nhận ra. Nếu null là kết quả hợp lệ, cần phân biệt lỗi với kết quả hợp lệ bằng hợp đồng rõ ràng.

**Lỗi 4 — log trùng lặp:** catch, log đầy đủ, ném tiếp ở mọi tầng. Hãy thiết kế vị trí chịu trách nhiệm log và vị trí chỉ chuyển nghĩa.

**Lỗi 5 — bọc nhầm loại:** dùng UncheckedIOException cho một exception không liên quan tới I/O, hoặc đổi lỗi validation thành lỗi hệ thống không đúng nghĩa. Loại wrapper ảnh hưởng chiến lược bắt và xử lý của caller.

**Lỗi 6 — quên checked exception ở SAM:** Function.apply và Consumer.accept không khai báo throws IOException. Cần catch/chuyển nghĩa, adapter hoặc một interface riêng có throws phù hợp.

**Lỗi 7 — tưởng bọc lỗi là đã phục hồi:** ném RuntimeException mới vẫn làm pipeline thất bại khi được đánh giá; nó không biến lỗi thành kết quả hợp lệ hay tự retry tác vụ.

**Lỗi 8 — bắt InterruptedException rồi bỏ qua:** có thể khiến xử lý cancellation không hoạt động. Khi không thể ném tiếp và quyết định chuyển loại, nhớ xem xét Thread.currentThread().interrupt() theo hợp đồng.

**Lỗi 9 — không phân biệt cause và suppressed:** một lỗi khi close() xảy ra bên cạnh lỗi chính là suppressed; đừng thay nguyên nhân chính chỉ để giữ lỗi phụ.

**Lỗi 10 — catch Throwable tổng quát:** có thể bắt Error nghiêm trọng mà ứng dụng không thể phục hồi. Chỉ bắt nhóm phù hợp với ranh giới.

**Lỗi 11 — phụ thuộc vào số lần chạy của lambda:** Stream lazy và có thể short-circuit; exception trong map/filter chỉ xuất hiện khi callback được gọi. Không kỳ vọng mọi phần tử đều phải chạy đến cùng trước khi một lỗi được báo.

**Lỗi 12 — lộ dữ liệu trong thông điệp:** đưa nguyên password, token, nội dung file bí mật hoặc dữ liệu cá nhân vào exception message. Chọn ngữ cảnh tối thiểu cần thiết, và lọc/log an toàn theo quy định của ứng dụng.

## 13. Checklist khi review code có exception wrapping

| Câu hỏi | Điều nên kiểm tra |
| --- | --- |
| Tại sao phải bọc? | Có bổ sung ngữ cảnh hoặc đổi hợp đồng lỗi cần thiết không? |
| Cause có còn? | new Wrapper(message, original) hoặc cơ chế tương đương |
| Wrapper có đúng nghĩa? | IllegalArgumentException, UncheckedIOException, lỗi domain... |
| Có nuốt lỗi? | Không return giá trị giả có vẻ hợp lệ khi gặp lỗi bất ngờ |
| Có bắt quá rộng? | Tránh catch Throwable và catch Exception vô điều kiện |
| Có tuân thủ SAM? | Đặc biệt checked exception trong Function/Stream |
| Có giữ interrupt? | Xem xét InterruptedException và chính sách hủy |
| Có xử lý ở ranh giới? | Không log nhiều lần; có mapping lỗi phù hợp |
| Có giữ stack/cause/suppressed? | Logger nhận Throwable thay vì chỉ message |
| Có kiểm thử cả lỗi? | Assert wrapper, nguyên nhân và bối cảnh thông điệp |
| Có bảo vệ dữ liệu? | Không lộ thông tin nhạy cảm trong exception/log |

## 14. Câu hỏi tự kiểm tra

1. Khác biệt giữa throw new RuntimeException(error.getMessage()) và throw new RuntimeException("Read failed", error) là gì?
2. Vì sao một lambda truyền vào Function<Path,String> không được gọi trực tiếp Files.readString(path) khi IOException chưa xử lý?
3. Khi nào nên dùng UncheckedIOException thay vì RuntimeException?
4. Nếu một service đã ném ngoại lệ nghiệp vụ với cause đầy đủ, tầng controller có nhất thiết phải bọc thêm không?
5. Sự khác nhau giữa Throwable.getCause() và getSuppressed() là gì?
6. Vì sao nên kiểm tra getCause() trong unit test thay vì chỉ so message?
7. Điều gì xảy ra nếu catch IOException trong map nhưng return "" rồi tiếp tục collect?
8. Khi nào InterruptedException cần được xử lý khác với lỗi parse dữ liệu?
9. Một Stream có thể ném lỗi ở bước tạo pipeline hay chỉ khi terminal operation thực thi callback?
10. Làm sao thêm ngữ cảnh về bản ghi thất bại mà không làm lộ dữ liệu nhạy cảm?
11. Vì sao catch(Throwable) để bọc mọi lỗi có thể nguy hiểm?
12. Bọc exception có làm callback trở thành hàm thuần hoặc thread-safe không?

**Ghi nhớ:** Bọc ngoại lệ tốt là **thêm ý nghĩa ở đúng ranh giới nhưng không làm mất bằng chứng**. Trong Java functional programming, việc chuyển checked exception sang unchecked exception để tương thích với lambda/Stream phải luôn được quyết định có chủ đích và **truyền cause gốc**. Hãy kiểm tra loại lỗi, message, cause, stack trace, suppressed exceptions và chính sách xử lý cuối cùng thay vì chỉ cố làm cho code biên dịch.