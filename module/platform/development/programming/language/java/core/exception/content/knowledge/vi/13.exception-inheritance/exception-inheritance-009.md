# Static initializer, checked exception và lỗi khởi tạo lớp trong Java

Khi JVM sử dụng một lớp Java lần đầu theo cách yêu cầu **khởi tạo lớp** (*class initialization*), nó thực thi những phần khởi tạo tĩnh: biểu thức khởi tạo của các trường `static` và các khối `static { ... }` theo thứ tự được khai báo trong mã nguồn. Những câu lệnh này chạy ở giai đoạn thiết lập trạng thái dùng chung cho lớp, **không phải mỗi lần tạo đối tượng**.

Vấn đề phát sinh khi công việc khởi tạo có thể thất bại. Đặc biệt:

- Khối `static` **không có khai báo `throws`**, và một checked exception không được phép thoát khỏi initializer nếu chưa được bắt/xử lý.
- Nếu quá trình khởi tạo lớp thất bại bởi một ngoại lệ không phải `Error`, JVM thường báo `ExceptionInInitializerError` cho lần thất bại đầu tiên.
- Nếu quá trình khởi tạo thất bại bởi một đối tượng thuộc `Error`, đối tượng `Error` đó có thể được truyền trực tiếp, không bắt buộc bị bọc lại thành `ExceptionInInitializerError`.
- Sau khi một lớp đã bị đánh dấu khởi tạo thất bại, những lần sử dụng sau cần khởi tạo lớp ấy thường nhận `NoClassDefFoundError` trong cùng runtime/class loader, **không phải thử chạy lại initializer**.

Đây là lý do việc đọc tệp, gọi dịch vụ mạng hoặc truy vấn cơ sở dữ liệu ngay trong `static` có thể biến một sự cố tạm thời thành một **lớp không thể sử dụng trong phần còn lại của vòng đời class loader**.

Bài học này nằm trong Java Core – Exception, nhóm **Kế thừa và hợp đồng**, và giải thích mối liên hệ giữa checked/unchecked exceptions, ngữ nghĩa khởi tạo lớp theo JVM và cách thiết kế API an toàn khi trạng thái tĩnh có thể gặp lỗi.

## 1. Static initializer là gì?

Có hai hình thức thông thường để khởi tạo trạng thái tĩnh:

**Biểu thức khởi tạo trường static:**

~~~java
static int cacheSize = calculateCacheSize();
~~~

**Khối static initializer:**

~~~java
static {
    System.out.println("Đang chuẩn bị lớp");
    // Gán trạng thái tĩnh, kiểm tra một số bất biến.
}
~~~

Đây là những mảnh mã để đặt **bên trong định nghĩa class**, không phải những chương trình độc lập. Một lớp có thể có nhiều trường tĩnh và nhiều khối `static`; chúng tham gia vào quá trình khởi tạo theo **thứ tự văn bản** khi JVM khởi tạo lớp.

Ví dụ hoàn chỉnh về thứ tự:

~~~java
class Preparation {
    static int value = createValue();

    static {
        System.out.println("static block: value=" + value);
    }

    static int createValue() {
        System.out.println("static field initializer");
        return 42;
    }
}
~~~

Khi `Preparation` thực sự được khởi tạo, đầu ra là:

~~~text
static field initializer
static block: value=42
~~~

Lệnh gọi `createValue()` ở trường `value` xảy ra trước khối `static` vì nó đứng trước trong mã nguồn.

**Không nhầm với constructor:** constructor thường chạy mỗi khi tạo một instance; code `static` được JVM chạy trong quá trình khởi tạo lớp (thông thường một lần **thành công** cho mỗi định nghĩa lớp gắn với một class loader), không phải mỗi lần `new`.

## 2. Những thao tác nào kích hoạt khởi tạo lớp?

Một số tình huống *active use* thường dẫn tới khởi tạo:

- Tạo đối tượng bằng `new SomeClass()` nếu lớp chưa được khởi tạo.
- Đọc trường `static` **không phải constant variable** của lớp.
- Ghi một trường `static` của lớp.
- Gọi phương thức `static` được khai báo bởi lớp.
- Một số đường reflective use, chẳng hạn `Class.forName("fully.qualified.Name")` theo overload mặc định có yêu cầu khởi tạo.

Ví dụ:

~~~java
class Startup {
    static final int CONSTANT = 7;
    static int computed = initialize();

    static int initialize() {
        System.out.println("Startup initialized");
        return 42;
    }

    static void ping() {
        System.out.println("ping");
    }
}
~~~

Nếu mã khác đọc `Startup.CONSTANT`, giá trị `7` là một **compile-time constant** (`static final int` với constant expression). Khi được biên dịch và dùng theo cách thông thường, việc đọc hằng số này **không cần kích hoạt khởi tạo `Startup`**.

Ngược lại, đọc `Startup.computed` hoặc gọi `Startup.ping()` là active use khiến lớp được khởi tạo nếu chưa khởi tạo.

### Các thao tác không nhất thiết kích hoạt initializer

Một vài cách dùng có thể làm bạn tưởng lớp đã “được sử dụng” nhưng chưa yêu cầu khởi tạo:

~~~java
Class<?> type = Startup.class;
int value = Startup.CONSTANT;
~~~

Lấy class literal `Startup.class` không tự yêu cầu thực thi các `static` initializer của `Startup`. Đọc compile-time constant cũng không bắt buộc khởi tạo lớp đó.

Phân biệt **loading**, **linking** và **initialization**: JVM có thể tải hoặc liên kết một lớp mà chưa chạy phần khởi tạo tĩnh. Cú pháp dùng class name không đồng nghĩa các `static` đã thực thi.

Ngoài ra, lớp cha thông thường được khởi tạo trước lớp con khi khởi tạo lớp con. Một số quy tắc riêng còn áp dụng cho interface và các superinterface khai báo default methods; không nên dùng ví dụ lớp thường để suy ra tuyệt đối cho mọi loại interface.

## 3. Checked exception trong static initializer: vì sao không được thoát trực tiếp?

Java sử dụng *checked exceptions* để buộc nơi gọi xử lý hoặc khai báo khi những ngoại lệ kiểm tra được có thể truyền qua ranh giới phương thức. Ví dụ `IOException` là checked:

~~~java
static String readConfig() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}
~~~

Đây là một phương thức minh họa, có thể đặt trong một lớp Java.

Nhưng **khối `static` không phải phương thức hoặc constructor**, nên bạn không thể khai báo:

~~~java
static throws java.io.IOException {
    // Sai cú pháp Java.
}
~~~

Đồng thời, đoạn sau **không biên dịch**:

~~~java
class WrongStaticBlock {
    static {
        java.nio.file.Files.readString(
                java.nio.file.Path.of("config.txt"));
    }
}
~~~

Lý do: `Files.readString(...)` khai báo có thể ném checked `IOException`, nhưng khối `static` không bắt nó và không có `throws` hợp lệ để chuyển cho caller.

Thông báo biên dịch thường có ý nghĩa tương tự *unreported exception IOException; must be caught or declared to be thrown*. Nội dung chính xác và số dòng có thể khác theo compiler.

### Không có cách “thêm throws cho class” để sửa

Các cách sau **không hợp lệ**:

~~~java
class WrongClass throws java.io.IOException {
    // Class không khai báo throws như phương thức.
}
~~~

Và constructor:

~~~java
class AlsoWrong {
    AlsoWrong() throws java.io.IOException {
        // Constructor có throws, nhưng không cấp quyền
        // cho static initializer ném checked exception ra ngoài.
    }
}
~~~

Constructor được phép khai báo `throws`, nhưng khai báo ấy không biến static initializer thành một phần của đường checked-exception của constructor. Lớp còn có thể bị khởi tạo bởi một lệnh gọi phương thức static mà không tạo instance nào.

**Quy tắc đúng:** mọi checked exception có thể phát sinh trong `static` initializer phải được xử lý trong phạm vi có thể bắt, hoặc được **chuyển thành ngoại lệ unchecked** theo một chính sách rõ ràng.

## 4. Cách bắt checked exception trong khối static

Một mẫu thường gặp:

~~~java
class ConfigHolder {
    static final String CONTENT;

    static {
        try {
            CONTENT = java.nio.file.Files.readString(
                    java.nio.file.Path.of("config.txt"));
        } catch (java.io.IOException cause) {
            throw new IllegalStateException(
                    "Không thể nạp cấu hình tĩnh", cause);
        }
    }
}
~~~

Đoạn class này có thể biên dịch trên Java 17+ vì `IOException` được bắt và khối `catch` ném `IllegalStateException`, một unchecked exception. Tuy vậy, việc truy cập lớp có thể thất bại **ngay lúc JVM khởi tạo** nếu không đọc được tệp.

Lưu ý:

1. `CONTENT` là `static final` và phải được gán trên mọi đường khối `static` **hoàn tất bình thường**.
2. Nếu đọc thành công, `CONTENT` nhận nội dung và lớp khởi tạo thành công.
3. Nếu đọc thất bại, `catch` giữ cause gốc trong `IllegalStateException`, rồi ném ra.
4. Trong giai đoạn khởi tạo lớp, JVM xử lý lỗi đó theo quy tắc class initialization; vì `IllegalStateException` không phải `Error`, bên gọi thường nhận `ExceptionInInitializerError` với cause là `IllegalStateException`.
5. `IOException` gốc nằm sâu hơn một tầng: `ExceptionInInitializerError → IllegalStateException → IOException`.

**Quan trọng:** không nên dùng mẫu này một cách vô thức cho cấu hình hoặc tài nguyên có thể tạm thời không sẵn sàng. Sau một lần khởi tạo thất bại, lớp thường bị đánh dấu **erroneous** và không được JVM tự khởi tạo lại trong cùng class loader.

### Nếu lỗi không đòi hỏi lớp phải thất bại?

Có thể chọn fallback khi hợp đồng cho phép:

~~~java
class DefaultConfig {
    static final int TIMEOUT;

    static {
        int selected;
        try {
            selected = readTimeout();
        } catch (java.io.IOException e) {
            selected = 5;
        }
        TIMEOUT = selected;
    }

    static int readTimeout() throws java.io.IOException {
        throw new java.io.IOException("file unavailable");
    }
}
~~~

Đây là ví dụ Java hợp lệ, nhưng chỉ đúng về nghiệp vụ khi timeout mặc định `5` được cho phép và việc không có tệp cấu hình không phải một lỗi fatal.

**Đừng bắt checked exception rồi âm thầm chọn một giá trị vô nghĩa chỉ để static initialization “đi qua”.** Nếu ứng dụng cần cấu hình đúng mới vận hành an toàn, phục hồi giả sẽ dẫn tới lỗi khó điều tra hơn về sau.

## 5. Static field initializer cũng chịu quy tắc checked exception

Không chỉ `static { ... }`, biểu thức gán cho trường `static` cũng không được để checked exception thoát ra:

~~~java
class InvalidField {
    static final String TEXT = read();

    static String read() throws java.io.IOException {
        throw new java.io.IOException("missing");
    }
}
~~~

Đây là **phản ví dụ không biên dịch**: biểu thức khởi tạo `TEXT` có thể ném checked `IOException` mà không có handler.

Một cách sửa là chuyển logic sang helper tự xử lý checked exception:

~~~java
class FieldViaHelper {
    static final String TEXT = readUnchecked();

    static String readUnchecked() {
        try {
            return read();
        } catch (java.io.IOException cause) {
            throw new IllegalStateException("Cannot read text", cause);
        }
    }

    static String read() throws java.io.IOException {
        return "ready";
    }
}
~~~

Đây là class Java hợp lệ. Phương thức `readUnchecked()` không khai báo checked exception vì đã xử lý nó. Nhưng nếu helper ném unchecked exception trong lúc khởi tạo `TEXT`, quá trình khởi tạo lớp vẫn có thể thất bại và phát sinh `ExceptionInInitializerError`.

Đưa mã vào helper **không biến lỗi khởi tạo thành lỗi thông thường có thể retry tự động**. Nó chỉ giải quyết hợp đồng checked exception và tổ chức code.

## 6. Khi static initializer gặp unchecked exception

Một lỗi thường gặp là nghĩ rằng: “Vì `IllegalStateException` là unchecked nên caller chỉ cần `catch(IllegalStateException)` khi khởi tạo lớp thất bại.”

Khi ngoại lệ không phải `Error` phát sinh và thoát khỏi quá trình khởi tạo, JVM thường tạo một `ExceptionInInitializerError` để biểu thị **thất bại trong class initialization**. Nó là subclass của `LinkageError`, cũng là `Error`.

Ví dụ:

~~~java
class Broken {
    static final int VALUE = initialize();

    static int initialize() {
        throw new IllegalStateException("bad config");
    }
}
~~~

Đây là class hợp lệ; phần khởi tạo trường gọi phương thức có thể ném unchecked exception tại runtime.

Nếu truy cập `Broken.VALUE` lần đầu:

~~~java
try {
    System.out.println(Broken.VALUE);
} catch (ExceptionInInitializerError e) {
    System.out.println(e.getClass().getSimpleName());
    System.out.println(
            e.getCause().getClass().getSimpleName());
}
~~~

Kết quả trong tình huống khởi tạo thất bại nêu trên:

~~~text
ExceptionInInitializerError
IllegalStateException
~~~

Đối tượng gốc `IllegalStateException` không bị mất; nó được đặt làm cause của `ExceptionInInitializerError`.

**Phân biệt hai tầng:**

- `IllegalStateException("bad config")`: vấn đề cụ thể phát sinh trong code khởi tạo.
- `ExceptionInInitializerError`: thông báo ở mức VM rằng việc khởi tạo một lớp đã kết thúc bất thường.

### `ExceptionInInitializerError` là checked hay unchecked?

Lớp `ExceptionInInitializerError` kế thừa `LinkageError` → `Error` → `Throwable`, vì vậy nó **unchecked**. Phương thức truy cập một lớp không phải khai báo `throws ExceptionInInitializerError`.

Một handler `catch (Exception e)` **không bắt** `ExceptionInInitializerError` vì nó không nằm trong nhánh `Exception`.

Đây là điểm đáng chú ý của chủ đề **Kế thừa và hợp đồng**: code khởi tạo có thể tạo `RuntimeException`, nhưng đối tượng quan sát được bên ngoài lần đầu lại thuộc nhóm `Error` do quy tắc khởi tạo lớp.

## 7. Nếu static initializer tự ném `Error`

JVM không phải lúc nào cũng bọc mọi lỗi thành `ExceptionInInitializerError`.

Quy tắc cốt lõi: nếu quá trình khởi tạo kết thúc bất thường bởi một đối tượng **thuộc `Error` hoặc subclass của `Error`**, JVM có thể truyền chính đối tượng `Error` đó như lý do thất bại của lần khởi tạo đầu.

Ví dụ:

~~~java
class FailsWithError {
    static {
        if (shouldFail()) {
            throw new AssertionError("broken invariant");
        }
    }

    static boolean shouldFail() {
        return true;
    }

    static void touch() {
        System.out.println("unreachable during failure");
    }
}
~~~

Đây là class Java hợp lệ. Điều kiện gọi phương thức không phải biểu thức hằng ở compile-time, nên khối `static` có một đường **có thể hoàn tất bình thường** theo phân tích compile-time. Lúc thực thi `shouldFail()` trả `true`, và `AssertionError` được ném.

Ở lần gọi `FailsWithError.touch()` đầu tiên, một `catch (AssertionError e)` phù hợp có thể nhận đối tượng `AssertionError` đó, thay vì bắt buộc nhận `ExceptionInInitializerError`.

**Không diễn giải thành “cứ có lỗi trong static thì luôn là ExceptionInInitializerError”.** Loại đối tượng bất thường thoát khỏi initializer quyết định có bước bọc vào `ExceptionInInitializerError` hay không.

## 8. Lớp thất bại một lần thường không được tự khởi tạo lại

Đây là hậu quả thực tế quan trọng nhất.

Khi JVM đã đánh dấu một lớp **khởi tạo thất bại**, trạng thái của định nghĩa lớp đó không trở lại “chưa khởi tạo” chỉ vì caller bắt được lỗi. Những lần active use tiếp theo thường thất bại nhanh với `NoClassDefFoundError`.

~~~text
Active use lần đầu
       |
       v
Thực thi static initialization
       |
       +-- Thành công ---> Lớp ở trạng thái initialized
       |
       +-- Thất bại ----> Lớp bị đánh dấu erroneous
                                  |
                                  v
                         Active use lần sau
                                  |
                                  v
                         NoClassDefFoundError
~~~

Vì thế, mã sau **không phải chiến lược retry hữu hiệu**:

~~~java
for (int attempt = 0; attempt < 3; attempt++) {
    try {
        UnstableHolder.connect();
        break;
    } catch (ExceptionInInitializerError e) {
        System.out.println("retry after static failure");
    }
}
~~~

Đây là mảnh minh họa, giả định có class `UnstableHolder`. Nếu lần đầu khởi tạo lớp đã thất bại, lần sau thường không vào cùng nhánh `catch (ExceptionInInitializerError)`; thay vào đó có thể có `NoClassDefFoundError`. Không nên xây cơ chế phục hồi bằng việc chỉ gọi lại một lớp đã bị đánh dấu erroneous.

**Trong cùng class loader**, JVM không tự “thử khởi tạo lại từ đầu” lớp đã thất bại. Khả năng tải một định nghĩa lớp mới bằng class loader khác là một cơ chế class loading riêng, không phải retry bình thường cho một ứng dụng.

## 9. `NoClassDefFoundError` không chỉ có nghĩa “thiếu file .class”

Tên `NoClassDefFoundError` dễ gây hiểu nhầm. Có ít nhất hai nhóm tình huống cần phân biệt:

1. **Không thể tìm hoặc định nghĩa lớp cần thiết tại runtime**, ví dụ classpath/module path không chứa một lớp đã được biên dịch để dùng.
2. **Một lớp đã được tìm thấy nhưng khởi tạo thất bại trước đó**; lần active use sau không thể dùng lại định nghĩa lỗi đó.

Vì vậy khi gặp `NoClassDefFoundError`:

- Đọc message và toàn bộ cause/stack trace để xác định có dấu hiệu `Could not initialize class ...` hay không.
- Tìm lỗi **đầu tiên** của quá trình khởi tạo, thường là `ExceptionInInitializerError` hoặc một `Error` khác.
- Nếu nguyên nhân gốc là lỗi I/O, cấu hình hay kết nối trong `static`, hãy xử lý thiết kế khởi tạo thay vì chỉ thêm JAR vào classpath.
- Nếu lớp thật sự không có ở runtime, hãy kiểm tra packaging, module path, classpath, phiên bản dependency và class loader.

Không được kết luận “thêm dependency” hay “đổi tên file .class” chỉ từ tên `NoClassDefFoundError`.

### Tại sao đôi khi lần đầu và lần hai có loại khác?

Ở lần đầu JVM đang **thực thi mã khởi tạo**, nên thấy lỗi trực tiếp của quá trình ấy hoặc wrapper `ExceptionInInitializerError`.

Ở lần hai JVM biết định nghĩa lớp đã ở trạng thái erroneous, nên việc active use không thực thi lại logic khởi tạo và thường dẫn tới `NoClassDefFoundError`. Dù message khác nhau theo JVM, khác biệt về pha là điểm cần hiểu.

## 10. Một chương trình Java 17+ chạy độc lập: thành công, checked failure, Error và lần dùng sau

Chương trình dưới đây chỉ dùng **lớp lồng tĩnh** để minh họa dễ chạy. Nó **không đọc tệp thật**, mà cố ý ném `IOException` từ một hàm mô phỏng nhằm có đầu ra xác định. Không cần thư viện ngoài.

Lưu thành tệp **`StaticInitializationDemo.java`**:

~~~java
import java.io.IOException;

public class StaticInitializationDemo {

    static class Good {
        static final String COMPILE_TIME = "constant";
        static int value = initializeValue();

        static {
            System.out.println("Good static block");
        }

        static int initializeValue() {
            System.out.println("Good field initializer");
            return 42;
        }

        static void touch() {
            System.out.println("Good.touch value=" + value);
        }
    }

    static class Failing {
        static {
            System.out.println("Failing static block");
            try {
                loadRequiredConfig();
            } catch (IOException cause) {
                throw new IllegalStateException(
                        "config initialization failed", cause);
            }
        }

        static void touch() {
            System.out.println("Failing.touch");
        }
    }

    static class FailingWithError {
        static {
            System.out.println("FailingWithError static block");
            if (shouldFail()) {
                throw new AssertionError("invariant broken");
            }
        }

        static boolean shouldFail() {
            return true;
        }

        static void touch() {
            System.out.println("FailingWithError.touch");
        }
    }

    public static void main(String[] args) {
        System.out.println("== compile-time constant ==");
        System.out.println("constant=" + Good.COMPILE_TIME);

        System.out.println("== successful init ==");
        Good.touch();
        Good.touch();

        System.out.println("== checked source first use ==");
        try {
            Failing.touch();
        } catch (ExceptionInInitializerError e) {
            System.out.println(
                    "first=" + e.getClass().getSimpleName());
            System.out.println(
                    "wrapped=" + e.getCause().getClass().getSimpleName());
            System.out.println(
                    "root=" + e.getCause().getCause()
                            .getClass().getSimpleName());
            System.out.println(
                    "rootMessage=" + e.getCause().getCause().getMessage());
        }

        System.out.println("== checked source second use ==");
        try {
            Failing.touch();
        } catch (NoClassDefFoundError e) {
            System.out.println(
                    "second=" + e.getClass().getSimpleName());
        }

        System.out.println("== direct Error first use ==");
        try {
            FailingWithError.touch();
        } catch (AssertionError e) {
            System.out.println(
                    "firstError=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }

        System.out.println("== direct Error second use ==");
        try {
            FailingWithError.touch();
        } catch (NoClassDefFoundError e) {
            System.out.println(
                    "secondError=" + e.getClass().getSimpleName());
        }
    }

    static void loadRequiredConfig() throws IOException {
        throw new IOException("config missing");
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac StaticInitializationDemo.java
java StaticInitializationDemo
~~~

**Stdout chính xác cho chương trình này:**

~~~text
== compile-time constant ==
constant=constant
== successful init ==
Good field initializer
Good static block
Good.touch value=42
Good.touch value=42
== checked source first use ==
Failing static block
first=ExceptionInInitializerError
wrapped=IllegalStateException
root=IOException
rootMessage=config missing
== checked source second use ==
second=NoClassDefFoundError
== direct Error first use ==
FailingWithError static block
firstError=AssertionError: invariant broken
== direct Error second use ==
secondError=NoClassDefFoundError
~~~

### Phân tích kết quả theo từng đoạn

**Compile-time constant:** `Good.COMPILE_TIME` được biên dịch như một giá trị hằng. Dòng `constant=constant` xuất hiện mà `Good` chưa phải chạy phần khởi tạo `value` hay static block. Không kết luận rằng bất kỳ lần đọc trường `static final` nào cũng bỏ khởi tạo: trường đó phải là **constant variable** theo quy tắc Java.

**Successful init:** lần gọi `Good.touch()` đầu tiên kích hoạt khởi tạo lớp. Biểu thức `value = initializeValue()` chạy trước và in `Good field initializer`; khối `static` chạy sau và in `Good static block`. Phương thức `touch()` in giá trị `42`. Lần gọi `Good.touch()` thứ hai không chạy initializer lại, nên chỉ in dòng của `touch()`.

**Checked source first use:** `Failing` gọi một phương thức khai báo `throws IOException` trong `static`, nhưng đã bắt checked exception đó. Code chuyển nó thành `IllegalStateException` có cause là `IOException`. Vì unchecked exception không thuộc `Error` thoát khỏi khởi tạo, JVM báo `ExceptionInInitializerError` với một cause `IllegalStateException`, bên trong nữa là `IOException`.

**Checked source second use:** JVM đã đánh dấu định nghĩa `Failing` là erroneous. Lần active use sau dẫn tới `NoClassDefFoundError` thay vì chạy lại static block. Không có dòng `Failing static block` thứ hai.

**Direct Error first use:** `FailingWithError` cố ý ném `AssertionError` qua điều kiện runtime. Vì đó đã là một `Error`, lần đầu caller bắt `AssertionError` trực tiếp. Đây là ví dụ phân tích JVM, **không khuyến nghị dùng `AssertionError` để biểu diễn lỗi cấu hình**.

**Direct Error second use:** định nghĩa lớp vẫn đã khởi tạo thất bại, nên lần sau nhận `NoClassDefFoundError`, không chạy lại logic static block.

**Không phải mã phục hồi production:** các khối `catch (ExceptionInInitializerError)`, `catch (AssertionError)` và `catch (NoClassDefFoundError)` trong chương trình chỉ để quan sát hậu quả. Khi một lớp quan trọng không khởi tạo được, chương trình thực thường cần báo lỗi rõ ràng rồi dừng/tái khởi động có kiểm soát thay vì cố tiếp tục sử dụng cùng lớp.

## 11. Vì sao khối `static` không được chỉ có một lệnh `throw` vô điều kiện?

Java có một quy tắc compile-time riêng: **static initializer phải có khả năng hoàn tất bình thường** (*must be able to complete normally*).

Phản ví dụ:

~~~java
class AlwaysFail {
    static {
        throw new IllegalStateException("always");
    }
}
~~~

Đây là **mã không biên dịch**. Dù `IllegalStateException` là unchecked, khối `static` chỉ có `throw` vô điều kiện nên không thể hoàn tất bình thường theo quy tắc phân tích luồng của compiler.

Một ví dụ được phép biên dịch nhưng thất bại khi chạy:

~~~java
class FailsAtRuntime {
    static {
        if (shouldFail()) {
            throw new IllegalStateException("runtime failure");
        }
    }

    static boolean shouldFail() {
        return true;
    }
}
~~~

Mã này có một nhánh điều kiện không phải constant expression, vì vậy compiler có thể thấy đường hoàn tất bình thường. Khi chạy, `shouldFail()` luôn trả `true`, khiến static initialization thất bại.

**Không dùng mẹo này để chủ động làm hỏng một class trong ứng dụng.** Nó chỉ minh họa khác biệt giữa:
- Kiểm tra *có thể hoàn tất bình thường* ở compile-time.
- Việc thực tế initializer có ném lỗi trong lần chạy hay không.

Một khối có `try/catch` xung quanh thao tác có thể ném lỗi thường cũng có đường hoàn tất bình thường theo phân tích compile-time, nhưng runtime vẫn có thể luôn thất bại nếu tác vụ phụ thuộc môi trường.

## 12. Phân biệt static initializer với constructor và instance initializer

Một số người tưởng có thể sửa lỗi checked trong `static` bằng cách thêm `throws` vào constructor:

~~~java
class IncorrectFix {
    IncorrectFix() throws java.io.IOException {
        // Throws chỉ gắn với constructor này.
    }

    static {
        // Nếu gọi phương thức throws IOException ở đây
        // mà không bắt thì vẫn là lỗi biên dịch.
    }
}
~~~

Điều đó **không sửa** khả năng ném checked exception trong `static`. Khởi tạo lớp và khởi tạo instance thuộc các pha khác nhau.

Phân biệt:

| Đặc điểm | Static initializer | Constructor |
| --- | --- | --- |
| Thuộc về | Lớp | Một lần tạo instance |
| Khi chạy | Khi JVM khởi tạo lớp theo quy tắc active use | Khi tạo đối tượng, sau bước khởi tạo lớp cần thiết |
| Có cú pháp khai báo `throws`? | Không | Có |
| Checked exception chưa xử lý có được thoát? | Không | Có nếu constructor khai báo/bắt phù hợp |
| Lỗi khởi tạo có thể làm class erroneous? | Có | Constructor ném lỗi bình thường không tự làm class erroneous |
| Tự động retry khi gọi lại? | Không nếu định nghĩa class đã erroneous | Có thể thử tạo instance mới nếu class đã khởi tạo thành công |

Một **instance initializer block** khác với static initializer. Nó được thực thi trong đường khởi tạo instance; quy tắc checked exception của instance initializer phụ thuộc các constructor hợp lệ và phức tạp hơn. Không được mang quy tắc của instance initializer để suy ra static block có thể khai báo `throws`.

Ví dụ constructor có checked exception hợp lệ:

~~~java
class InstanceConfig {
    InstanceConfig() throws java.io.IOException {
        throw new java.io.IOException("instance failed");
    }
}
~~~

Đây là class Java hợp lệ. Nếu `new InstanceConfig()` ném `IOException`, lớp `InstanceConfig` **không tự bị đánh dấu khởi tạo thất bại** chỉ vì constructor của một instance ném lỗi. Caller có thể xử lý và thử tạo instance khác theo hợp đồng. Đây là lý do nên cân nhắc chuyển thao tác I/O dễ thất bại ra khỏi `static`.

## 13. Thiết kế tốt hơn cho cấu hình có thể thất bại: factory có checked exception

Thay vì để việc đọc cấu hình trong static initializer, có thể dùng một phương thức factory:

~~~java
final class Settings {
    private final String content;

    private Settings(String content) {
        this.content = content;
    }

    static Settings load(java.nio.file.Path path)
            throws java.io.IOException {
        String text = java.nio.file.Files.readString(path);
        return new Settings(text);
    }

    String content() {
        return content;
    }
}
~~~

Đây là class Java 17 hợp lệ. Việc tạo một đối tượng `Settings` bây giờ diễn ra qua `Settings.load(path)` và phương thức có thể khai báo checked `IOException`.

**Lợi ích:**

1. Caller biết rõ thao tác có khả năng thất bại thông qua `throws IOException`.
2. Caller có thể chọn retry, báo lỗi, fallback hoặc chuyển tiếp.
3. Một lần nạp cấu hình thất bại **không đánh dấu cả `Settings` là class erroneously initialized** nếu class không có static initializer ném lỗi.
4. Dữ liệu cấu hình được gắn với **instance** thay vì một trạng thái static khó thay thế.
5. Dễ kiểm thử với tệp mẫu hoặc dữ liệu giả lập; vòng đời có thể do dependency injection/container quản lý.

Nếu không muốn phơi lỗi I/O ra khỏi abstraction, factory có thể bọc checked `IOException` trong một custom checked exception miền:

~~~java
static Settings loadRequired(java.nio.file.Path path)
        throws ConfigurationLoadException {
    try {
        return load(path);
    } catch (java.io.IOException cause) {
        throw new ConfigurationLoadException(
                "Cannot load required configuration", cause);
    }
}
~~~

Đây là **phương thức minh họa**, giả định `ConfigurationLoadException` là checked exception có constructor nhận message và cause. Điểm quan trọng là lỗi phát sinh **trong lời gọi phương thức bình thường**, không phải qua một static initializer khiến class erroneous.

## 14. Lazy initialization có giải quyết hoàn toàn vấn đề không?

Không phải cứ hoãn khởi tạo tới lần truy cập đầu là sẽ có khả năng retry.

**Initialization-on-demand holder idiom:**

~~~java
class Service {
    private static class Holder {
        static final Service INSTANCE = createService();
    }

    static Service instance() {
        return Holder.INSTANCE;
    }

    static Service createService() {
        return new Service();
    }
}
~~~

Đây là class minh họa. `Holder` thường chỉ được khởi tạo khi `Service.instance()` cần `Holder.INSTANCE`. Nó là cách triển khai **lazy initialization** hữu ích khi thao tác khởi tạo đơn giản, an toàn và thực sự đáng chạy một lần.

Tuy nhiên, nếu `createService()` ném unchecked exception trong quá trình khởi tạo `Holder`, **Holder cũng có thể bị đánh dấu erroneous**. Đưa công việc thất bại vào lớp `Holder` **không biến nó thành cơ chế retry**.

Nếu bạn cần thử kết nối lại, làm mới credential, đổi endpoint hoặc phục hồi sau lỗi tạm thời, hãy thiết kế một **state machine hoặc provider quản lý vòng đời** có kiểm soát, thay vì mong rằng `static final INSTANCE` tự được tạo lại.

### Cẩn thận với double-checked locking và trạng thái dùng chung

Một dịch vụ lazy phức tạp có thể dùng `volatile`, synchronization hoặc thư viện concurrent. Đây là câu chuyện riêng về Java Memory Model, nhưng liên quan trực tiếp đến việc khởi tạo thất bại: cần quyết định rõ khi nào trạng thái được công bố, caller nào chờ, liệu có retry, và cách tránh công bố đối tượng nửa khởi tạo.

**Đừng tự chế một singleton retry phức tạp nếu một factory hoặc dependency injection lifecycle đã đủ rõ.**

## 15. Tác động tới class loading và đa luồng

Class initialization không chỉ là vài dòng được gọi tùy ý; JVM có một giao thức khởi tạo để bảo đảm các trạng thái cơ bản khi nhiều thread cùng active use lớp.

Thông thường:

- JVM đồng bộ hóa quá trình khởi tạo một định nghĩa lớp để không có hai thread độc lập cùng chạy initializer như hai lần khởi tạo riêng.
- Một thread có thể phải đợi khi thread khác đang khởi tạo cùng định nghĩa lớp.
- Nếu initializer thành công, các thread dùng lớp đã khởi tạo thấy kết quả theo bảo đảm khởi tạo lớp.
- Nếu initializer thất bại, định nghĩa lớp chuyển sang trạng thái erroneous; các thread khác không được kỳ vọng “tự chạy lại” static initializer.
- Một khối `static` làm I/O lâu, chờ lock hoặc đợi tác vụ khác có thể ảnh hưởng nặng đến thời gian startup hoặc tạo nguy cơ deadlock.

### Vì sao không nên bắt đầu thread rồi đợi trong static block?

Một mẫu đáng nghi ngại:

~~~java
class Dangerous {
    static {
        Thread worker = new Thread(() -> initialize();
        );
        worker.start();
        // Nếu chờ worker hoàn thành ở đây mà worker cần
        // chính class đang được khởi tạo, có thể deadlock.
    }

    static void initialize() {
        // Công việc phụ thuộc trạng thái lớp.
    }
}
~~~

Đoạn trên **chỉ là sơ đồ phản ví dụ về ý tưởng**, không phải mã Java biên dịch (nó cố ý trình bày một ý tưởng luồng nguy hiểm). Khi triển khai thực, bất kỳ công việc nào yêu cầu thread khác truy cập class đang chờ khởi tạo đều cần được xem xét nguy cơ khóa khởi tạo vòng tròn.

Về bản chất, class initialization thích hợp cho việc thiết lập những hằng số hoặc trạng thái đơn giản, có thể dự đoán; không phải chỗ lý tưởng để khởi động một workflow phụ thuộc đa luồng.

## 16. Cách chẩn đoán `ExceptionInInitializerError` trong thực tế

Khi nhìn log:

~~~text
java.lang.ExceptionInInitializerError
    ...
Caused by: java.lang.IllegalStateException: config initialization failed
    ...
Caused by: java.io.IOException: config missing
    ...
~~~

Đây là **minh họa cấu trúc**, không phải stack trace đầy đủ hoặc đầu ra byte-for-byte của một JVM.

Hãy đi theo những bước:

1. **Tìm lần lỗi đầu tiên**, không chỉ các `NoClassDefFoundError` sau đó.
2. Đọc `getCause()` của `ExceptionInInitializerError` để thấy lỗi gốc mà initializer đã ném; nếu đó là wrapper, tiếp tục duyệt chuỗi cause.
3. Kiểm tra các trường static/khối static **theo thứ tự khai báo**, đặc biệt những hàm đọc cấu hình, truy cập môi trường hoặc khởi tạo client.
4. Xác định lỗi là thiếu dependency, I/O, sai cấu hình, vi phạm bất biến, hay class initialization cycle.
5. Kiểm tra có phải một thread khác chờ initialization lock hoặc phát sinh deadlock không.
6. Quyết định chính sách **fail fast**, fallback hợp lệ, hay chuyển thao tác sang factory để có thể retry đúng cách.
7. Kiểm thử với môi trường mô phỏng lỗi, không phải cố tình phá JVM production.

Nếu log chỉ còn:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class ...
~~~

hãy kiểm tra log **trước thời điểm đó** để tìm lỗi khởi tạo đầu tiên. Đây là chẩn đoán thường có giá trị hơn việc tìm file `.class` trong trường hợp lớp đã được tìm thấy nhưng initialization thất bại.

### `ExceptionInInitializerError.getException()` và `getCause()`

`ExceptionInInitializerError` có phương thức cũ `getException()` để lấy đối tượng được lưu khi tạo một số dạng lỗi khởi tạo. Trong mã hiện đại, `getCause()` thường là API dễ dùng hơn để lần theo nguyên nhân như các `Throwable` khác.

Không nên giả định một đối tượng `ExceptionInInitializerError` bất kỳ luôn có cause khác null: code có thể tự tạo `new ExceptionInInitializerError()` hoặc constructor nhận message mà không lưu một throwable nguyên nhân. Khi duyệt cause, kiểm tra null trước khi dùng.

## 17. Bảo đảm của `finally` và try-with-resources khi class initialization thất bại

Một exception phát sinh trong static initializer vẫn đi qua các cấu trúc `try/finally` đã được thực thi theo luật Java thông thường. Ví dụ:

~~~java
class ResourceInit {
    static {
        try {
            System.out.println("initializing");
            fail();
        } finally {
            System.out.println("cleanup during initialization");
        }
    }

    static void fail() {
        throw new IllegalStateException("cannot initialize");
    }
}
~~~

Class này hợp lệ. Khi JVM chạy initializer, nó in `initializing`, rồi `cleanup during initialization` trước khi `IllegalStateException` thoát và thường bị JVM bọc trong `ExceptionInInitializerError`.

Try-with-resources cũng gọi `close()` khi rời scope nếu mã Java còn cơ hội thực thi. Điều đó **không có nghĩa nó sửa trạng thái erroneous của lớp** sau khi lỗi đã thoát.

Cần phân biệt:

- Dọn dẹp tài nguyên khi một bước khởi tạo thất bại.
- Làm cho định nghĩa lớp trở lại trạng thái có thể khởi tạo lần đầu.

Hai việc này không tương đương. Một `finally` chạy thành công có thể dọn tài nguyên đang mở mà vẫn để quá trình class initialization kết thúc bất thường.

## 18. Những lỗi hiểu sai phổ biến

### Sai lầm 1 — “Static block có thể viết `throws IOException`”

Không. `static` initializer không có cú pháp khai báo `throws` và không được để checked exception thoát trực tiếp.

### Sai lầm 2 — “Constructor khai báo `throws` giúp static initializer hợp lệ”

Không. Constructor và static initialization là hai pha khác nhau. `throws` của constructor không xử lý checked exception của khối `static`.

### Sai lầm 3 — “Chỉ khối `static {}` mới có thể làm lớp khởi tạo thất bại”

Không. Biểu thức khởi tạo của trường `static` cũng tham gia vào quá trình khởi tạo lớp và có thể thất bại.

### Sai lầm 4 — “Một `RuntimeException` thoát khỏi static block luôn được caller nhận trực tiếp”

Không. Khi khởi tạo lớp thất bại bởi một ngoại lệ không phải `Error`, JVM thường bọc nó bằng `ExceptionInInitializerError`.

### Sai lầm 5 — “Bất kỳ `Error` nào thoát khỏi initializer cũng phải bị bọc”

Không. Một `Error` có thể là lỗi được báo trực tiếp của lần khởi tạo đầu.

### Sai lầm 6 — “Lần sau JVM sẽ khởi tạo lại class đã lỗi”

Không. Trong cùng class loader, một định nghĩa lớp đã bị đánh dấu erroneous thông thường không được khởi tạo lại; lần dùng sau thường phát sinh `NoClassDefFoundError`.

### Sai lầm 7 — “`NoClassDefFoundError` luôn do thiếu file .class”

Sai. Nó cũng xuất hiện khi class đã được tìm thấy nhưng một lần khởi tạo trước thất bại.

### Sai lầm 8 — “`catch(Exception)` chắc chắn bắt `ExceptionInInitializerError`”

Không. `ExceptionInInitializerError extends LinkageError`, tức nằm dưới `Error`, không dưới `Exception`.

### Sai lầm 9 — “`static final` lúc nào cũng khởi tạo class khi đọc”

Không. Trường compile-time constant có thể được inlined và không kích hoạt khởi tạo lớp như một static field thông thường.

### Sai lầm 10 — “`SomeClass.class` luôn chạy static block”

Không. Lấy class literal không tự kích hoạt initialization, dù cơ chế tải lớp có thể đã diễn ra.

### Sai lầm 11 — “Đưa code vào static helper là có thể retry”

Không. Nếu helper chạy **trong static field initializer** và ném lỗi ra ngoài, toàn bộ quá trình khởi tạo lớp vẫn có thể thất bại.

### Sai lầm 12 — “Static initializer chỉ chạy khi gọi constructor”

Không. Gọi phương thức static hoặc truy cập trường static không phải constant cũng có thể kích hoạt khởi tạo.

### Sai lầm 13 — “`NoClassDefFoundError` sau initialization failure nên luôn được catch rồi tiếp tục”

Không. Lớp phụ thuộc quan trọng có thể không còn sử dụng được. Cần xem xét chính sách thất bại và khởi động lại, không tiếp tục mù quáng.

### Sai lầm 14 — “Bắt `IOException` trong static rồi bỏ qua luôn là tốt”

Không. Fallback chỉ hợp lý nếu hợp đồng cho phép và trạng thái thay thế an toàn.

### Sai lầm 15 — “Một constructor ném checked exception làm cả class bị erroneous”

Không. Class initialization và instance initialization khác nhau. Một constructor thất bại không mặc định đánh dấu class initialization thất bại.

### Sai lầm 16 — “`finally` không chạy khi initializer ném ngoại lệ”

Không. `finally` liên quan vẫn được thực thi khi luồng Java rời scope theo cách thông thường. Nó không tự sửa class initialization failure.

### Sai lầm 17 — “Một static block vô điều kiện chỉ có `throw` luôn biên dịch vì RuntimeException unchecked”

Không. Java còn có yêu cầu static initializer **phải có khả năng hoàn tất bình thường** khi phân tích compile-time.

### Sai lầm 18 — “Có thể làm class có cơ chế retry bằng cách dời mọi I/O vào lazy static holder”

Không. Lazy holder vẫn bị erroneous nếu initializer của chính nó thất bại. Retry cần được thiết kế trong phương thức/provider quản lý trạng thái.

### Sai lầm 19 — “Mọi lời gọi `Class.forName` đều giống hệt đọc `SomeClass.class`”

Không. Overload mặc định `Class.forName(String)` yêu cầu initialization; class literal chỉ đại diện cho class object và không tự khởi tạo theo cùng cách. Một số overload reflective cho phép điều khiển cờ initialize.

### Sai lầm 20 — “Có thể đoán nguyên nhân chỉ từ tên `ExceptionInInitializerError`”

Không. Phải xem cause chain, khối `static` liên quan và lỗi đầu tiên. Đây là wrapper mô tả giai đoạn thất bại, không nêu đầy đủ lý do kỹ thuật.

## 19. Checklist thiết kế static state an toàn

Trước khi viết I/O hoặc logic có thể lỗi trong khối `static`, tự hỏi:

1. **Tài nguyên có thể tạm thời không sẵn sàng không?** Nếu có, một static initializer thất bại là lựa chọn khó phục hồi.
2. **Caller có cần retry không?** Dùng factory hoặc service lifecycle thay vì class initialization.
3. **Có thể dùng giá trị mặc định an toàn không?** Nếu có, fallback phải được ghi trong hợp đồng.
4. **Có checked exception cần truyền cho caller không?** Static initializer không có `throws`; hãy chuyển code sang phương thức phù hợp khi cần.
5. **Có phụ thuộc mạng, đĩa hoặc cơ sở dữ liệu không?** Những công việc đó thường không lý tưởng cho `static`.
6. **Có nguy cơ deadlock hoặc thời gian khởi tạo dài không?** Tránh chờ các thread khác hoặc gọi mạng trong initialization lock.
7. **Các constant có thể biểu diễn bằng constant expression không?** Giữ những cấu hình tĩnh đơn giản, bất biến và dễ dự đoán.
8. **Nếu thất bại, ứng dụng cần fail fast hay tiếp tục?** Quyết định ở tầng kiểm soát lifecycle.
9. **Có ghi log cause gốc trước khi gặp các lỗi `NoClassDefFoundError` tiếp theo không?** Giữ dấu vết đầu tiên.
10. **Có test cả lần sử dụng đầu và lần sử dụng sau trong cùng JVM không?** Hai lần có thể quan sát kiểu lỗi khác.
11. **Có test việc gọi từ nhiều thread không?** Class initialization là tài nguyên đồng bộ hóa ẩn có thể bị chờ.
12. **Có phải code thực sự cần static mutable state không?** Instance được quản lý rõ vòng đời có thể dễ kiểm thử hơn.

Một static initializer tốt thường ngắn, xác định, không phụ thuộc I/O dễ lỗi và không tạo side effect khó hoàn tác.

## 20. Bài tập tự kiểm tra

1. Phân biệt class initialization với instance construction trong Java.
2. Biểu thức khởi tạo trường `static` có nằm trong quy trình class initialization không?
3. Vì sao `static { Files.readString(path); }` thường không biên dịch?
4. Có thể ghi `throws IOException` trực tiếp vào phần khai báo static initializer không?
5. Thêm `throws IOException` vào constructor có cho phép checked exception thoát khỏi static block không?
6. Nếu `static` bắt `IOException` và ném `IllegalStateException`, caller active use lần đầu thường thấy loại nào?
7. `ExceptionInInitializerError` thuộc nhánh `Exception` hay `Error`?
8. `catch(Exception)` có bắt `ExceptionInInitializerError` không?
9. Nếu static initializer ném trực tiếp `AssertionError`, JVM có bắt buộc bọc nó bằng `ExceptionInInitializerError` không?
10. Sau một lần class initialization thất bại, lần dùng sau thường nhận lỗi gì?
11. Có phải mọi `NoClassDefFoundError` đều do thiếu file class?
12. Vì sao `static final int X = 7` thường không kích hoạt khởi tạo lớp khi được đọc?
13. Đọc `static int X = calculate()` có thể kích hoạt class initialization không?
14. Lấy `SomeClass.class` có tự chạy `static` block không?
15. Gọi một phương thức `static` có thể kích hoạt initialization không?
16. Vì sao một khối `static` chỉ có `throw new RuntimeException()` vô điều kiện không hợp lệ?
17. Lỗi trong constructor có tự làm class erroneous không?
18. Có thể dùng try-with-resources trong quá trình class initialization không?
19. Nếu `finally` chạy khi khởi tạo thất bại, class có trở lại dùng được không?
20. Cách nào hợp lý hơn static initializer nếu công việc đọc cấu hình có thể retry?
21. Lazy holder có bảo đảm retry khi lần tạo `INSTANCE` đầu tiên lỗi không?
22. Tại sao các công việc phụ thuộc đa luồng không nên nằm trong static initialization?
23. Khi gặp `NoClassDefFoundError: Could not initialize class ...`, nên tìm log nào?
24. Một checked exception `IOException` được giữ ở đâu trong cause chain `ExceptionInInitializerError → IllegalStateException → IOException`?
25. Khi nào fallback trong static block là hợp lý?

### Đáp án gợi ý

1. Class initialization chạy các trạng thái static theo cơ chế JVM; constructor chạy khi tạo một instance.
2. Có.
3. Vì `IOException` là checked và chưa được bắt/xử lý.
4. Không.
5. Không.
6. Thường là `ExceptionInInitializerError`.
7. Nhánh `Error` (qua `LinkageError`).
8. Không.
9. Không; một `Error` có thể được truyền trực tiếp ở lần lỗi đầu.
10. Thường là `NoClassDefFoundError`.
11. Không; nó cũng có thể báo class đã khởi tạo thất bại trước đó.
12. Vì `X` là compile-time constant có thể được inline.
13. Có.
14. Không tự kích hoạt initialization.
15. Có.
16. Do quy tắc static initializer phải có khả năng hoàn tất bình thường.
17. Không, nếu bản thân quá trình class initialization đã thành công.
18. Có; nó đóng tài nguyên trên đường rời scope Java thông thường, nhưng không sửa lỗi initialization.
19. Không; dọn dẹp và trạng thái class erroneous là hai việc khác nhau.
20. Phương thức factory/loader có khai báo `throws` và chính sách retry rõ.
21. Không; holder cũng có thể erroneous.
22. Vì initialization lock và phụ thuộc vòng có thể gây chờ hoặc deadlock.
23. Lỗi **đầu tiên** khi static initializer/field initializer thực thi, cùng cause chain.
24. Là cause của `IllegalStateException`, tức cause sâu hơn của `ExceptionInInitializerError`.
25. Khi trạng thái mặc định an toàn, có ý nghĩa và được API cho phép.

## 21. Tổng kết

**Khối `static` không có `throws` và không được để checked exception thoát trực tiếp.** Nếu công việc khởi tạo có thể ném `IOException`, phải bắt/xử lý hoặc thay đổi kiến trúc để lỗi xuất hiện trong một phương thức có hợp đồng `throws` rõ ràng. Khi class initialization thất bại do ngoại lệ không phải `Error`, JVM thường chuyển nó thành `ExceptionInInitializerError`; khi lỗi gốc là `Error`, nó có thể được truyền trực tiếp. Sau thất bại, class thường trở thành **erroneous**, khiến những active use tiếp theo nhận `NoClassDefFoundError` thay vì chạy initializer lại.

Với cấu hình, kết nối hoặc tài nguyên có khả năng thất bại tạm thời, **factory/loader và vòng đời được quản lý rõ ràng** thường an toàn, dễ retry, dễ kiểm thử hơn việc phụ thuộc vào static initializer.