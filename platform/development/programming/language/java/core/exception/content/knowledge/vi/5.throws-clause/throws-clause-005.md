# Lan truyền checked exception qua nhiều tầng lời gọi trong Java

Trong Java, một phương thức có thể gọi phương thức khác, phương thức đó lại gọi xuống tầng thấp hơn. Nếu tầng thấp phát sinh **checked exception** mà không xử lý tại chỗ, ngoại lệ có thể **lan truyền ngược lên chuỗi lời gọi**. Để mã biên dịch, mỗi tầng có khả năng để ngoại lệ checked thoát ra phải khai báo kiểu ngoại lệ tương ứng trong mệnh đề `throws`, hoặc dùng `try-catch` để xử lý hay chuyển đổi nó.

Ví dụ, một ứng dụng đọc cấu hình theo đường `Controller → Service → Repository → File API`. `Files.readString(...)` có thể phát sinh `IOException`. Nếu `Repository`, `Service` và `Controller` đều không xử lý, kiểu `IOException` phải xuất hiện trong hợp đồng `throws` của các phương thức liên quan. Tại một ranh giới có đủ ngữ cảnh, chương trình bắt lỗi, quyết định trả thông báo, dùng dữ liệu dự phòng hoặc dừng thao tác.

**Điểm cốt lõi:** `throws` là **khai báo khả năng phát sinh ngoại lệ checked ở thời điểm biên dịch**. Nó không tự ném, tự bắt, in log hay sửa lỗi. Ngoại lệ chỉ thực sự di chuyển khi chương trình đang chạy và một ngoại lệ được ném.

## 1. Nhắc lại: checked exception là gì?

Mọi đối tượng có thể ném bằng `throw` phải thuộc `Throwable`. Java chia ngoại lệ theo quy tắc kiểm tra lúc biên dịch:

| Nhánh lớp | Checked? | Ví dụ | Nghĩa vụ của phương thức gọi |
| --- | --- | --- | --- |
| `Exception` nhưng không thuộc `RuntimeException` | Có | `IOException`, `SQLException`, `ParseException` | Bắt hoặc khai báo `throws` nếu thao tác có thể ném chúng |
| `RuntimeException` và lớp con | Không | `IllegalArgumentException`, `NullPointerException` | Không bắt buộc `catch` hay `throws` |
| `Error` và lớp con | Không | `OutOfMemoryError`, `LinkageError` | Không bắt buộc `catch` hay `throws` |
| Chính `Throwable` | Có | `new Throwable("...")` | Phải xử lý/khai báo nếu có thể thoát ra |

Vì `IOException` là checked, compiler kiểm tra xem phương thức gọi `Files.readString(path)` có bắt hoặc cho phép `IOException` đi ra ngoài không. Cùng quy tắc áp dụng cho từng lời gọi ở tầng trên. Trình biên dịch kiểm tra *kiểu* ngoại lệ có thể phát sinh theo cấu trúc mã; nó không cần chờ ngoại lệ xảy ra khi chương trình chạy.

Một số API khai báo nhiều kiểu checked, chẳng hạn `IOException` và một ngoại lệ nghiệp vụ do thư viện tự định nghĩa. Khi những kiểu đó có thể thoát ra khỏi một phương thức, `throws` phải bao quát tất cả chúng bằng các kiểu phù hợp hoặc một kiểu cha hợp lệ. `throws Exception` về mặt cú pháp bao quát rất rộng, nhưng thường làm hợp đồng API khó sử dụng hơn `throws IOException` hay một loại cụ thể.

## 2. Chuỗi gọi nhiều tầng và hướng lan truyền

Sơ đồ dưới đây mô tả **chiều gọi phương thức** và **chiều ngoại lệ lan truyền**:

```text
Đi xuống khi gọi:
main() ──► controller() ──► service() ──► repository() ──► readFile()
                                                        │
                                                        │ throw IOException
                                                        ▼
Đi lên khi lỗi:
main() ◄── controller() ◄── service() ◄── repository() ◄─┘
  │
  └── catch IOException hoặc khai báo throws tiếp
```

Khi `readFile()` ném `IOException`:

1. Phần mã sau điểm ném trên đường chạy bình thường của `readFile()` không chạy.
2. Nếu `readFile()` không bắt lỗi, lời gọi trong `repository()` hoàn tất đột ngột.
3. Nếu `repository()` không bắt, lỗi tiếp tục lên `service()`; tương tự với `controller()`.
4. Khi gặp `catch` tương thích đầu tiên trên đường tháo chuỗi lời gọi, chương trình thực thi khối xử lý đó. Các `finally` phù hợp được thực hiện theo quy tắc Java trong quá trình truyền ngoại lệ.
5. Nếu không ai bắt, ngoại lệ có thể thoát khỏi điểm vào của thread và được xử lý như ngoại lệ chưa bắt.

**Cần tách hai câu hỏi.** Compiler hỏi: “Có loại checked exception nào *có thể* đi ra khỏi phương thức này?” Runtime hỏi: “Một đối tượng ngoại lệ *đã thực sự* được ném và hiện được xử lý ở đâu?”. Việc khai báo `throws` giải quyết nghĩa vụ compile-time; việc đi lên stack xảy ra ở runtime.

## 3. Ví dụ Java 17+: lan truyền qua bốn tầng rồi bắt ở biên

Lưu thành `CheckedPropagationDemo.java`:

```java
import java.io.IOException;

public class CheckedPropagationDemo {
    static String readFile() throws IOException {
        throw new IOException("config missing");
    }

    static String repository() throws IOException {
        return readFile();
    }

    static String service() throws IOException {
        return repository();
    }

    static String controller() throws IOException {
        return service();
    }

    public static void main(String[] args) {
        try {
            System.out.println(controller());
        } catch (IOException ex) {
            System.out.println("type=" + ex.getClass().getSimpleName());
            System.out.println("message=" + ex.getMessage());
            System.out.println("handled at main");
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 CheckedPropagationDemo.java
java CheckedPropagationDemo
```

Kết quả chính xác:

```text
type=IOException
message=config missing
handled at main
```

Trong ví dụ này:

- `readFile()` là nơi tạo và ném `IOException`.
- `repository()`, `service()` và `controller()` không có `catch`; mỗi phương thức khai báo `throws IOException` để cho phép lỗi đi tiếp.
- `main()` bắt và xử lý bằng `catch (IOException ex)`, nên nó không cần `throws IOException`.
- Lệnh `System.out.println(controller())` không thể in ra kết quả thành công trong lần chạy này: lời gọi `controller()` ném ngoại lệ trước khi có giá trị làm tham số cho `println`.
- **Cùng một đối tượng ngoại lệ** có thể truyền lên nhiều tầng nếu không được thay thế. Mỗi `throws` không tạo ngoại lệ mới.

Để tránh phụ thuộc vào hệ thống tệp hoặc dữ liệu bên ngoài, ví dụ cố ý ném `IOException` trực tiếp tại tầng thấp. Với ứng dụng thật, `readFile()` thường gọi `Files.readString(path)` và để ngoại lệ API đó truyền ra.

## 4. Vì sao mỗi tầng vẫn phải khai báo `throws`?

Xét một phiên bản sai:

```java
import java.io.IOException;

class MissingThrowsExample {
    static String storage() throws IOException {
        throw new IOException("failed");
    }

    static String service() {
        return storage(); // compile error: unreported exception IOException
    }
}
```

Đây là ví dụ **cố ý không biên dịch**. Vì `storage()` được khai báo có thể ném `IOException`, phương thức `service()` phải bắt nó hoặc khai báo `throws IOException`.

Cách sửa cho phép lan truyền:

```java
static String service() throws IOException {
    return storage();
}
```

Câu trên là đoạn sửa **bên trong lớp `MissingThrowsExample`**, thay cho phương thức `service()` cũ. Một cách sửa khác là bao lời gọi trong `try-catch` nếu `service()` có quy tắc xử lý phù hợp.

Nếu sửa `service()` theo hướng `throws IOException`, mã gọi `service()` tại tầng cao hơn cũng phải đáp ứng yêu cầu tương tự. Đây là **chuỗi nghĩa vụ checked exception**, kéo dài cho tới khi một tầng xử lý hoặc một entry point tiếp tục khai báo lỗi.

Một phương thức có thể khai báo `throws IOException` dù trong đường chạy hiện tại nó không thực sự ném ngoại lệ. Khai báo mô tả một khả năng theo hợp đồng, không buộc phương thức ném lỗi mỗi lần được gọi. Trình biên dịch cũng không tự suy ra rằng một phương thức mang tên `loadSafely` chắc chắn an toàn; nó xem chữ ký và quy tắc phân tích ngoại lệ của mã.

## 5. Ba lựa chọn thực tế ở mỗi tầng

| Lựa chọn | Khi nào dùng | Hệ quả cho tầng gọi |
| --- | --- | --- |
| **Lan truyền nguyên ngoại lệ** bằng `throws IOException` | Tầng hiện tại không có đủ ngữ cảnh để giải quyết; kiểu lỗi vẫn có ý nghĩa | Tầng trên phải xử lý/khai báo ngoại lệ checked |
| **Bắt và xử lý** bằng `catch` | Có quy tắc phục hồi đáng tin: dữ liệu dự phòng, thử lại có giới hạn, thông báo kết quả rõ ràng | Nếu xử lý xong và không phát sinh checked exception mới, nghĩa vụ với ngoại lệ đó có thể kết thúc |
| **Chuyển đổi ngoại lệ** bằng `throw new DomainException("...", cause)` | Ranh giới tầng cần hợp đồng riêng; không muốn API nghiệp vụ phụ thuộc trực tiếp vào lỗi hạ tầng | Tầng trên xử lý/khai báo **kiểu mới** nếu nó là checked |

Một tầng không nên tự động “bắt cho hết lỗi” chỉ để tránh viết `throws`. Nếu không thể phục hồi, việc bắt rồi trả dữ liệu giả thành công có thể che giấu hỏng dữ liệu hoặc khiến tầng trên ra quyết định sai.

Ngược lại, **không phải tầng nào cũng phải lan truyền**. Chỉ cần một tầng có khả năng xử lý phù hợp thì chuỗi có thể kết thúc tại đó.

## 6. Ví dụ Java 17+: một tầng xử lý bằng giá trị dự phòng

Lưu thành `HandledAtServiceDemo.java`:

```java
import java.io.IOException;

public class HandledAtServiceDemo {
    static String storage(boolean available) throws IOException {
        if (!available) {
            throw new IOException("storage unavailable");
        }
        return "live-config";
    }

    static String repository(boolean available) throws IOException {
        return storage(available);
    }

    static String service(boolean available) {
        try {
            return repository(available);
        } catch (IOException ex) {
            System.out.println("fallback because: " + ex.getMessage());
            return "default-config";
        }
    }

    static void controller(boolean available) {
        System.out.println("config=" + service(available));
    }

    public static void main(String[] args) {
        controller(false);
        controller(true);
    }
}
```

```bash
javac -encoding UTF-8 HandledAtServiceDemo.java
java HandledAtServiceDemo
```

Kết quả:

```text
fallback because: storage unavailable
config=default-config
config=live-config
```

Ở `service()`, lỗi `IOException` được xử lý bằng fallback **có chủ đích**. Vì `catch` trả về cấu hình mặc định và không ném checked exception mới, `service()` không cần `throws IOException`. Do đó `controller()` cũng không cần khai báo lỗi này. Mã chỉ minh họa cơ chế; trong hệ thống thật, cần xác định fallback có an toàn, có được phép theo nghiệp vụ và có làm mất thông tin chẩn đoán hay không.

Điểm quan trọng: **xử lý thành công ở tầng dưới làm dừng lan truyền ngoại lệ tại tầng đó**. Không có đối tượng ngoại lệ nào bị chuyển tiếp lên `controller()` từ lần gọi thất bại này.

## 7. Chuyển đổi checked exception giữa các tầng và giữ nguyên nhân

Trong hệ thống nhiều tầng, không phải lúc nào lớp API cũng nên biết `IOException`, `SQLException` hoặc loại lỗi cụ thể của thư viện hạ tầng. Một tầng dịch vụ có thể biến chúng thành ngoại lệ phù hợp với ngữ nghĩa nghiệp vụ.

Lưu thành `ExceptionTranslationDemo.java`:

```java
import java.io.IOException;

public class ExceptionTranslationDemo {
    static class ConfigLoadException extends Exception {
        ConfigLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String storage() throws IOException {
        throw new IOException("disk read failed");
    }

    static String repository() throws IOException {
        return storage();
    }

    static String service() throws ConfigLoadException {
        try {
            return repository();
        } catch (IOException ex) {
            throw new ConfigLoadException("cannot load configuration", ex);
        }
    }

    static void controller() {
        try {
            System.out.println(service());
        } catch (ConfigLoadException ex) {
            System.out.println("type=" + ex.getClass().getSimpleName());
            System.out.println("message=" + ex.getMessage());
            System.out.println("causeType="
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("causeMessage=" + ex.getCause().getMessage());
        }
    }

    public static void main(String[] args) {
        controller();
    }
}
```

```bash
javac -encoding UTF-8 ExceptionTranslationDemo.java
java ExceptionTranslationDemo
```

Kết quả:

```text
type=ConfigLoadException
message=cannot load configuration
causeType=IOException
causeMessage=disk read failed
```

Đây là một ví dụ về **dịch hợp đồng ngoại lệ**:

1. `storage()` và `repository()` dùng kiểu checked `IOException` của tầng I/O.
2. `service()` bắt `IOException` và **tạo một đối tượng mới** `ConfigLoadException`, cũng là checked vì kế thừa `Exception` nhưng không kế thừa `RuntimeException`.
3. `service()` khai báo `throws ConfigLoadException`; tầng trên chỉ cần biết hợp đồng mới.
4. `controller()` bắt `ConfigLoadException` và vẫn có thể truy vết nguyên nhân ban đầu qua `getCause()`.

**Không viết** `throw new ConfigLoadException(ex.getMessage(), null);` hoặc chỉ tạo `new Exception(ex.getMessage())` nếu mục đích là bổ sung ngữ cảnh mà vẫn bảo toàn nguyên nhân. Hãy truyền đối tượng `ex` làm `cause`. Khi log, tránh ghi cùng một stack trace lặp lại ở mọi tầng.

Với lớp ngoại lệ nghiệp vụ, chọn loại checked hay unchecked tùy hợp đồng: một lỗi có thể xử lý có ý nghĩa riêng thường thích hợp với checked; vi phạm bất biến, tham số bất hợp lệ hoặc lỗi lập trình thường dùng unchecked. Không có quy tắc rằng mọi `IOException` nhất thiết phải bọc thành `RuntimeException`.

## 8. Khai báo nhiều kiểu checked exception và quan hệ lớp cha

Một phương thức có thể phát sinh nhiều loại checked độc lập:

```java
import java.io.IOException;
import java.text.ParseException;

class MultipleCheckedExample {
    static String readAndParse(int mode) throws IOException, ParseException {
        if (mode == 1) {
            throw new IOException("I/O failed");
        }
        if (mode == 2) {
            throw new ParseException("Invalid format", 0);
        }
        return "OK";
    }

    static String service(int mode) throws IOException, ParseException {
        return readAndParse(mode);
    }
}
```

Đoạn này biên dịch được (dù không có `main` để chạy độc lập). `IOException` và `ParseException` là hai kiểu checked khác nhau. Vì `service()` không bắt, nó phải khai báo cả hai loại hoặc một kiểu cha phù hợp như `Exception`; khai báo cụ thể giúp người gọi biết các trường hợp cần xử lý.

Trong một `catch`, có thể dùng multi-catch nếu những kiểu không có quan hệ lớp cha/con với nhau:

```java
try {
    MultipleCheckedExample.service(1);
} catch (IOException | ParseException ex) {
    System.out.println("failed: " + ex.getMessage());
}
```

Đây là đoạn minh họa nằm trong một phương thức và có thể truy cập lớp `MultipleCheckedExample`. Nếu bắt kiểu cha `Exception` thay thế, nhiều loại lỗi sẽ bị gom chung, đôi khi làm mất quyết định xử lý riêng.

**Quan hệ kế thừa quyết định phạm vi bao phủ của `throws`:** nếu phương thức con có thể ném `FileNotFoundException` thì `throws IOException` là đủ, vì `FileNotFoundException extends IOException`. Không cần viết đồng thời `throws FileNotFoundException, IOException` trừ khi muốn ghi chú rõ để người đọc; về quy tắc biên dịch, vế sau đã bao quát vế trước.

Tương tự, `throws Exception` bao quát mọi checked exception thuộc nhánh `Exception`, nhưng không có nghĩa bao quát một checked `Throwable` trực tiếp không thuộc `Exception`. `throws Throwable` là loại quá rộng cho API thông thường vì còn bao phủ cả các lỗi ở nhánh `Error` trong hợp đồng.

## 9. `throws` ở phương thức và constructor: giới hạn thiết kế

`throws` được phép trong khai báo phương thức và constructor:

```java
import java.io.IOException;

class ResourceHolder {
    ResourceHolder(String location) throws IOException {
        if (location == null || location.isBlank()) {
            throw new IOException("location missing");
        }
    }
}
```

Nếu gọi `new ResourceHolder("")`, trình biên dịch yêu cầu bên gọi `catch` hoặc khai báo `throws IOException`. Nghĩa vụ tương tự lời gọi phương thức. Đoạn này minh họa lớp hợp lệ nhưng không có `main`.

### Ghi nhớ quy tắc ghi đè phương thức

Khi ghi đè (*override*) một phương thức, phiên bản ghi đè **không được khai báo thêm hoặc mở rộng các checked exceptions** ngoài những gì hợp đồng phương thức cha cho phép. Nó có thể khai báo ít hơn hoặc kiểu con phù hợp.

Ví dụ hợp lệ:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

interface ConfigSource {
    String load() throws IOException;
}

class FileSource implements ConfigSource {
    @Override
    public String load() throws FileNotFoundException {
        throw new FileNotFoundException("missing");
    }
}

class InMemorySource implements ConfigSource {
    @Override
    public String load() {
        return "local";
    }
}
```

`FileNotFoundException` là con của `IOException` nên hợp lệ. `InMemorySource` không khai báo checked exception nào cũng hợp lệ. Nhưng nếu một implementation cố khai báo `throws Exception`, nó mở rộng hợp đồng checked exception so với `IOException` và bị từ chối lúc biên dịch.

Khi biến được khai báo kiểu `ConfigSource`, lời gọi `source.load()` vẫn phải xét hợp đồng `throws IOException` của interface tại compile time, dù đối tượng thực tế là `InMemorySource` không ném checked exception.

**Lưu ý:** Overriding không được thêm checked exception mới; nó vẫn có thể phát sinh unchecked exception. Khả năng compiler kiểm tra là một phần hợp đồng kiểu, không phải cam kết rằng mã runtime hoàn toàn không lỗi.

## 10. `throws` tại `main` có thể đưa ngoại lệ đến đâu?

Java cho phép khai báo:

```java
import java.io.IOException;

class MainThrowsExample {
    public static void main(String[] args) throws IOException {
        perform();
    }

    static void perform() throws IOException {
        throw new IOException("operation failed");
    }
}
```

Đây là chương trình **biên dịch được**, nhưng nếu chạy, ngoại lệ thoát ra khỏi `main` và được xử lý như ngoại lệ chưa bắt của thread khởi chạy. JVM/JDK thông thường in thông tin lỗi và stack trace; nội dung dòng/đường dẫn phụ thuộc môi trường nên không cần cố định stdout.

Khai báo `throws IOException` tại `main` giải quyết vấn đề biên dịch, **không đồng nghĩa đã xử lý sự cố**. Trong chương trình dòng lệnh, có thể cố ý để lỗi chấm dứt chương trình; trong một dịch vụ, API hoặc tác vụ nền, ranh giới thường cần quy tắc ghi nhận, phản hồi và dọn dẹp phù hợp.

Vì ngoại lệ không tự động chạy lại phương thức thất bại, không nên hình dung `throws` như một phép “chuyển việc xử lý cho JVM và sau đó tiếp tục bình thường”. Nếu không có `catch` phù hợp, đường thực thi của lời gọi đó kết thúc đột ngột.

## 11. `try-with-resources` và lỗi phát sinh ở nhiều bước

Trong các ứng dụng I/O, một phương thức có thể lỗi khi thực hiện nghiệp vụ **và** khi đóng tài nguyên. `try-with-resources` quản lý việc đóng `AutoCloseable` theo thứ tự ngược với lúc khởi tạo. Nếu thân `try` ném ngoại lệ và `close()` cũng ném ngoại lệ, lỗi đóng thường được lưu trong `getSuppressed()` của ngoại lệ chính.

Lưu thành `SuppressedPropagationDemo.java`:

```java
import java.io.IOException;

public class SuppressedPropagationDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void storage() throws IOException {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        }
    }

    static void service() throws IOException {
        storage();
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressedCount=" + ex.getSuppressed().length);
            System.out.println("suppressed="
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedPropagationDemo.java
java SuppressedPropagationDemo
```

Kết quả:

```text
primary=read failed
suppressedCount=1
suppressed=close failed
```

Ngoại lệ `IOException("read failed")` lan từ `storage()` lên `service()` rồi `main()`, giống một checked exception thông thường. `IOException("close failed")` **không thay thế lỗi chính**, mà được đính kèm vào `getSuppressed()`. Từ đó có thể truy vết đầy đủ thay vì mất lỗi từ thao tác đọc.

Nếu chỉ có lỗi khi đóng tài nguyên mà không có lỗi trong thân `try`, lỗi đóng có thể trở thành ngoại lệ chính. `try-with-resources` không miễn yêu cầu khai báo checked exception phát sinh từ việc đóng; compiler vẫn kiểm tra các kiểu checked mà việc tự động đóng tài nguyên có thể ném.

## 12. Không đánh đồng `throws` với bất đồng bộ và lambda

Khi dùng callback, lambda hoặc executor, checked exception vẫn phải tuân theo chữ ký của functional interface. Ví dụ, `Supplier<T>.get()` **không khai báo checked exception**. Vì vậy đoạn sau **cố ý không biên dịch**:

```java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;

class InvalidSupplierExample {
    static String read() throws IOException {
        throw new IOException("read failed");
    }

    static void submit() {
        CompletableFuture.supplyAsync(() -> read());
        // Lỗi: lambda của Supplier không thể để IOException checked thoát ra.
    }
}
```

Việc gọi API có chữ `Async` không bỏ qua quy tắc checked exception. Nếu thực sự muốn chuyển lỗi qua `CompletableFuture`, cần thiết kế một kết quả lỗi phù hợp hoặc bọc nguyên nhân trong unchecked wrapper theo hợp đồng của API. Khi `join()` quan sát một tác vụ hoàn thành bất thường, một `CompletionException` có thể xuất hiện với nguyên nhân gốc. Đây là cơ chế truyền thất bại của thư viện đồng thời; không phải cứ có `throws IOException` là lỗi tự động truyền sang thread gọi.

Các ví dụ đồng bộ ở phần đầu bài minh họa rõ cơ chế `throws` qua chuỗi gọi trực tiếp; vấn đề async chỉ là điểm cần lưu ý nếu thiết kế được mở rộng.

## 13. `InterruptedException` là checked exception cần chính sách riêng

Một ví dụ checked exception quan trọng trong chương trình có thread là `InterruptedException`, thường phát sinh từ thao tác chờ như `Thread.sleep(...)`. Tầng trên có thể để lan truyền:

```java
static void waitForWork() throws InterruptedException {
    Thread.sleep(100);
}

static void service() throws InterruptedException {
    waitForWork();
}
```

Nếu tầng này không được phép khai báo thêm `InterruptedException` do hợp đồng API, khi bắt nó thường phải **khôi phục cờ interrupt** rồi kết thúc/hủy thao tác theo chính sách:

```java
static void serviceWithoutCheckedThrows() {
    try {
        Thread.sleep(100);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

Cả hai đoạn là phương thức minh họa trong một lớp. Việc gọi `interrupt()` là để báo cho tầng gọi biết thread đang có yêu cầu hủy; trong ứng dụng thật, cần tránh tiếp tục công việc như chưa có gì xảy ra. Không nên áp dụng “nuốt ngoại lệ và tiếp tục” như quy tắc chung cho `InterruptedException`.

## 14. Lỗi thường gặp khi truyền checked exception qua các tầng

| Sai lầm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Chỉ khai báo `throws IOException` ở tầng thấp rồi quên khai báo tại tầng gọi kế tiếp. | Compiler báo `unreported exception ... must be caught or declared`. | Bổ sung `throws` ở tầng cần lan truyền hoặc xử lý tại tầng đó. |
| Nghĩ `throws` tự bắt và xử lý. | Ngoại lệ vẫn lan khi runtime có `throw` thực tế. | Đặt `catch` tại ranh giới có đủ thông tin xử lý. |
| Bao mọi phương thức bằng `catch (Exception ex) { }`. | Nuốt lỗi, mất nguyên nhân; tầng cao có thể nhầm là thành công. | Chỉ bắt loại có thể xử lý; truyền hoặc chuyển đổi lỗi nếu cần. |
| Mọi tầng đều `catch`, ghi log rồi `throw ex;`. | Trùng log, phân tán trách nhiệm ghi nhận; mã trở nên dài mà không bổ sung ý nghĩa. | Chọn một tầng ghi log/đưa lỗi ra ngoài phù hợp; chỉ bắt khi cần ngữ cảnh hoặc phục hồi. |
| Chuyển ngoại lệ thành `new RuntimeException(ex.getMessage())`. | Mất `cause` và chuỗi stack trace gốc. | Dùng `new RuntimeException("ngữ cảnh", ex)` khi hợp đồng quyết định dùng unchecked. |
| Khai báo `throws Exception` hoặc `throws Throwable` ở mọi tầng. | Hợp đồng kém chính xác, khó phân biệt nhóm lỗi. | Dùng loại checked cụ thể hoặc một ngoại lệ miền nghiệp vụ. |
| Đưa ngoại lệ checked mới vào phương thức override dù interface không cho phép. | Vi phạm quy tắc ghi đè. | Thiết kế interface từ đầu hoặc dùng quy tắc dịch ngoại lệ thích hợp. |
| Trả giá trị mặc định dù dữ liệu bị lỗi nghiêm trọng. | B che khuất sự cố và có thể dẫn tới trạng thái không nhất quán. | Chỉ dùng fallback có căn cứ nghiệp vụ; nếu không thì lan truyền lỗi. |
| Bỏ qua `getSuppressed()` khi đóng tài nguyên thất bại. | Thiếu thông tin thứ cấp có thể giúp điều tra. | Dùng `try-with-resources`, ghi nhận cả ngoại lệ chính và suppressed khi cần. |

## 15. Cách đọc và thiết kế hợp đồng ngoại lệ của một module

Với từng tầng, hãy trả lời:

1. **Nguồn ngoại lệ:** phương thức nào phát sinh? Đây là checked hay unchecked? API đã khai báo `throws` gì?
2. **Ý nghĩa của tầng:** tầng này có đủ thông tin phục hồi không? Ví dụ thao tác đọc cấu hình lỗi thì có dữ liệu mặc định được phép sử dụng không?
3. **Quyết định:** bắt và xử lý, truyền nguyên loại qua `throws`, hay chuyển đổi sang một checked exception phù hợp ranh giới?
4. **Hợp đồng với tầng gọi:** chữ ký có công bố đúng loại checked exception có thể đi ra không? Nếu override/interface, có vi phạm giới hạn không?
5. **Thông tin chẩn đoán:** khi bọc ngoại lệ đã giữ `cause` chưa? Nếu đóng tài nguyên, `suppressed` có được giữ lại không?
6. **Điểm kết thúc:** tầng nào biến lỗi thành thông báo, kết quả có kiểu, phản hồi API hoặc quyết định kết thúc tác vụ? Đừng để mỗi tầng tự quyết định theo cách mâu thuẫn.

Một sơ đồ thiết kế hợp lý, nếu mỗi tầng có vai trò tách bạch:

```text
Repository: throws IOException
        |
        v
Service: catches IOException
         throws ConfigLoadException (cause = IOException)
        |
        v
Controller: catches ConfigLoadException
            -> tạo phản hồi phù hợp
```

Sơ đồ này không phải khuôn áp dụng cho mọi dự án. Nếu một API của service vốn là API I/O thuần và `IOException` có ý nghĩa cho bên gọi, có thể truyền nguyên loại. Nếu tầng service có thể phục hồi an toàn, nó có thể kết thúc chuỗi ngoại lệ ở chính mình. Quyết định dựa trên hợp đồng và khả năng xử lý, không dựa trên việc muốn ít `throws` hơn bằng mọi giá.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `repository() throws IOException` được gọi trong `service()`. Nếu `service()` không bắt lỗi thì có phải khai báo `throws IOException` không?  
**Có.** Nếu ngoại lệ checked có thể đi ra khỏi `service()`, compiler đòi hỏi khai báo loại đó hoặc kiểu cha phù hợp.

**Câu 2.** `throws IOException` có tạo một đối tượng `IOException` tại mỗi tầng không?  
**Không.** Nó chỉ khai báo hợp đồng. Không bắt/bọc thì đối tượng ngoại lệ ban đầu có thể lan qua nhiều lời gọi.

**Câu 3.** Nếu `service()` bắt `IOException` và trả về fallback hợp lệ, `controller()` có bắt buộc khai báo `throws IOException` chỉ vì từng có `IOException` ở tầng dưới không?  
**Không.** Nếu lỗi đã được xử lý hoàn toàn và không có đường nào để checked exception đó thoát khỏi `service()`, tầng trên không có nghĩa vụ đó.

**Câu 4.** Nếu `service()` bắt `IOException` và ném `ConfigLoadException extends Exception`, tầng gọi phải tuân thủ hợp đồng nào?  
**ConfigLoadException.** Đây là checked exception mới; lưu `IOException` cũ qua `getCause()` để không mất ngữ cảnh.

**Câu 5.** Khai báo `throws IOException` có bao quát `FileNotFoundException` không?  
**Có.** Vì `FileNotFoundException` là lớp con của `IOException`.

**Câu 6.** Một implementation có thể thêm `throws Exception` khi phương thức interface chỉ khai báo `throws IOException` không?  
**Không.** Phương thức ghi đè không được mở rộng checked exceptions được cho phép bởi phương thức cha.

**Câu 7.** Nếu `main() throws IOException` thì chương trình đã bắt lỗi chưa?  
**Chưa.** Đây vẫn là khai báo lan truyền. Nếu lỗi thực sự thoát `main` mà không có handler phù hợp, nó là ngoại lệ chưa bắt.

**Câu 8.** Một lambda của `Supplier<String>` có thể ném `IOException` checked chỉ vì nó được đưa vào `CompletableFuture.supplyAsync` không?  
**Không.** `Supplier.get()` không khai báo checked exception; phải thiết kế cơ chế bọc/chuyển kết quả phù hợp.

## Tham khảo chuẩn

- [JLS Java SE 21 — §11.1.1 Các lớp checked và unchecked](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1).
- [JLS Java SE 21 — §11.2 Kiểm tra checked exception lúc biên dịch](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).
- [JLS Java SE 21 — §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2.3).
- [JLS Java SE 21 — §8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.6).
- [JLS Java SE 21 — §8.4.8.3 Giới hạn throws khi ghi đè](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3).
- [JLS Java SE 21 — §14.20 Cách try, catch và finally hoạt động](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20).

**Ghi nhớ:** `throws` cho phép một tầng **công bố** loại checked exception mà nó chưa xử lý, và các tầng trên tiếp tục có trách nhiệm bắt hoặc khai báo. Chuỗi truyền lỗi chỉ dừng khi có xử lý phù hợp hoặc khi ngoại lệ thoát ra ngoài điểm vào. Khi cần chuyển đổi lỗi ở ranh giới tầng, hãy giữ `cause` và khai báo đúng checked exception mới.
