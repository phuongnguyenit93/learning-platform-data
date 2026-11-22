# `ExceptionInInitializerError` khi khởi tạo `static` thất bại trong Java

`ExceptionInInitializerError` là một lỗi thuộc nhánh `Error` dùng để báo rằng **quá trình khởi tạo lớp hoặc interface đã thất bại**. Trong thực tế, lỗi này thường xuất hiện khi một **static field initializer** hoặc **static initializer block** ném `RuntimeException` (hoặc một `Throwable` khác không thuộc `Error`) trong lúc JVM khởi tạo lớp.

Điều quan trọng nhất không phải chỉ là tên exception:

1. `ExceptionInInitializerError` thường là **lớp vỏ** báo lỗi ở giai đoạn JVM khởi tạo; nguyên nhân kỹ thuật thực tế nằm ở `getCause()` hoặc `getException()`.
2. **Không phải mọi lỗi phát sinh trong static initializer đều bị bọc**. Nếu ngoại lệ đang lan truyền đã là một `Error` hoặc subclass, JVM có thể truyền chính đối tượng `Error` đó tại lần thất bại đầu tiên.
3. **Sau khi một lớp khởi tạo thất bại**, cùng định nghĩa lớp đó thường được đánh dấu *erroneous* trong class loader hiện tại. Những lần *active use* sau sẽ gặp `NoClassDefFoundError`; Java **không tự chạy lại initializer**.
4. Không thể dùng `throws IOException` cho một khối `static`. Phải bắt checked exception bên trong quá trình khởi tạo hoặc chuyển công việc thất bại sang một phương thức bình thường.
5. Đối với I/O, kết nối, tải cấu hình hay tài nguyên cần retry, **static initializer thường không phải nơi thích hợp**.

Bài học thuộc Java Core – Exception, nhóm **Error và khởi tạo**, tập trung vào nguyên nhân, luật JVM, đọc stack trace/cause, hậu quả và thiết kế xử lý đúng, kèm ví dụ Java 17+ có stdout xác định.

## 1. `ExceptionInInitializerError` nằm đâu trong cây kế thừa?

Cây rút gọn:

~~~text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   └── java.lang.RuntimeException
    │       └── java.lang.IllegalStateException
    └── java.lang.Error
        └── java.lang.LinkageError
            ├── java.lang.ExceptionInInitializerError
            └── java.lang.NoClassDefFoundError
~~~

Do kế thừa `LinkageError` → `Error`:

- `ExceptionInInitializerError` là **unchecked**, nên method không phải khai báo `throws ExceptionInInitializerError`.
- `catch (Exception e)` **không bắt được** nó.
- `catch (ExceptionInInitializerError e)` có thể bắt đúng loại, nhưng làm vậy **không khiến định nghĩa lớp bị lỗi trở lại trạng thái khởi tạo được**.
- `catch (Error)` và `catch (Throwable)` có thể nhận về mặt ngôn ngữ, nhưng không nên dùng mặc định rồi tiếp tục xử lý nghiệp vụ.
- `NoClassDefFoundError` ở các lần gọi sau cũng thuộc nhánh `Error`, không nằm trong `Exception`.

**Tên giống nhau không đồng nghĩa cùng vai trò:** `IllegalStateException` có thể là **nguyên nhân trong initializer**; `ExceptionInInitializerError` là **wrapper do cơ chế khởi tạo tạo ra**; `NoClassDefFoundError` có thể là **hậu quả về sau**.

## 2. Static field initializer và static block

Một lớp Java có thể khởi tạo các trường static và thực thi một hoặc nhiều khối static:

~~~java
class Settings {
    static int base = initializeBase();

    static {
        System.out.println("static block: base=" + base);
    }

    static int initializeBase() {
        System.out.println("field initializer");
        return 10;
    }
}
~~~

Đây là một lớp hợp lệ. Khi `Settings` được **khởi tạo lần đầu**, đầu ra từ phần initialization:

~~~text
field initializer
static block: base=10
~~~

Java thực hiện những static field initializers và static initializer blocks **theo thứ tự văn bản trong mã nguồn** khi khởi tạo lớp đó. Không hiểu nhầm rằng mọi trường static đều chạy trước tất cả khối static: **thứ tự khai báo** quyết định thứ tự thực hiện giữa hai loại.

Ví dụ:

~~~java
class Sequence {
    static int first = print("first", 1);

    static {
        System.out.println("middle");
    }

    static int second = print("second", 2);

    static int print(String label, int value) {
        System.out.println(label);
        return value;
    }
}
~~~

Thứ tự khi khởi tạo `Sequence` là:

~~~text
first
middle
second
~~~

**Constructor khác static initializer:** constructor chạy khi tạo một đối tượng; việc gọi method static hoặc đọc một trường static không phải constant cũng có thể khởi tạo lớp dù bạn không tạo đối tượng nào.

## 3. Tải, liên kết và khởi tạo là những bước khác nhau

Các khái niệm:

- **Loading:** JVM tìm hoặc tạo biểu diễn của một class/interface.
- **Linking:** kiểm tra, chuẩn bị các phần cần thiết, và có thể giải quyết các tham chiếu ký hiệu theo quy tắc JVM.
- **Initialization:** thực hiện phương thức khởi tạo lớp do JVM tổng hợp từ static field initializers và static blocks; trong bytecode thường được gọi là `<clinit>`.

`ExceptionInInitializerError` gắn với **giai đoạn initialization**, không nhất thiết có nghĩa file `.class` không được tìm thấy hoặc Java không parse được bytecode.

### Các kiểu sử dụng thường kích hoạt initialization

Một số tình huống *active use*:

- `new SomeClass()` khi lớp chưa được khởi tạo.
- Gọi một phương thức static được khai báo bởi class.
- Đọc hoặc ghi trường static không thuộc trường hằng (*constant variable*) được sử dụng theo cách đặc biệt.
- Một số hoạt động reflection, chẳng hạn `Class.forName("fully.qualified.ClassName")` với overload mặc định có yêu cầu initialization.

Ví dụ:

~~~java
class ActiveUse {
    static final int COMPILE_TIME_CONSTANT = 7;
    static int calculated = loadValue();

    static int loadValue() {
        System.out.println("ActiveUse initialized");
        return 42;
    }

    static void ping() {
        System.out.println("ping");
    }
}
~~~

Đọc `ActiveUse.calculated` hoặc gọi `ActiveUse.ping()` thường kích hoạt initialization nếu lớp chưa initialized.

### Class literal và compile-time constants

~~~java
Class<?> metadata = ActiveUse.class;
int number = ActiveUse.COMPILE_TIME_CONSTANT;
~~~

Đây là mảnh minh họa. Chỉ lấy class literal `ActiveUse.class` **không bắt buộc chạy initializer**. Đọc `COMPILE_TIME_CONSTANT` là một compile-time constant, có thể được biên dịch/inlined nên cũng **không yêu cầu class initialization** theo cơ chế đọc một static field bình thường.

Ngược lại:

~~~java
int value = ActiveUse.calculated;
~~~

là active use. Điều đó sẽ làm `loadValue()` chạy nếu lớp chưa được khởi tạo.

**Đừng suy diễn rằng cứ có `static final` thì bỏ khởi tạo.** Trường `static final` được tính bằng lời gọi method **không** phải compile-time constant:

~~~java
static final String CONFIG = readConfigUnchecked();
~~~

Nếu nằm trong một class chưa initialized, đọc `CONFIG` có thể kích hoạt công việc `readConfigUnchecked()` và dẫn đến initialization failure.

## 4. Luồng cơ bản khi initialization thành công hoặc thất bại

~~~text
Active use đầu tiên
        |
        v
Class đã initialized?
     |        |
     Có      Chưa
     |        |
Sử dụng      JVM thực hiện initialization
                 |
         +-------+-------+
         |               |
       Thành công       Thất bại
         |               |
Class initialized    Class erroneous
                         |
                  +------+------+
                  |             |
             Throwable       Throwable
             không là Error  thuộc Error
                  |             |
           EIIE bọc lại    Error có thể
           lỗi gốc        truyền trực tiếp
                         |
            Active use tiếp theo
                         |
                 NoClassDefFoundError
~~~

`EIIE` trong sơ đồ là viết tắt của `ExceptionInInitializerError`.

Một **sự thất bại ở chính quá trình khởi tạo** có hậu quả khác với một method static đã chạy **sau khi lớp initialized thành công** mà ném exception. Ví dụ một lớp hoàn toàn đã khởi tạo, rồi `static void query()` ném `IOException`/`IllegalStateException` trong một lần gọi thông thường, **không** vì thế bị JVM đánh dấu erroneous chỉ do exception của method.

## 5. RuntimeException thoát khỏi initializer thường bị bọc

Ví dụ:

~~~java
class FailingConfiguration {
    static final String VALUE = load();

    static String load() {
        throw new IllegalStateException("invalid configuration");
    }
}
~~~

Đây là class hợp lệ. Nếu một lần active use cần khởi tạo `FailingConfiguration`, method `load()` ném `IllegalStateException`. Ngoại lệ này là subtype của `RuntimeException`, **không thuộc `Error`**.

Theo quy tắc khởi tạo, JVM tạo một `ExceptionInInitializerError` để mang lỗi thất bại ban đầu. Caller có thể đọc:

~~~java
try {
    System.out.println(FailingConfiguration.VALUE);
} catch (ExceptionInInitializerError failure) {
    System.out.println(
            failure.getClass().getSimpleName());
    System.out.println(
            failure.getCause().getClass().getSimpleName());
}
~~~

Đầu ra mô tả hai tầng:

~~~text
ExceptionInInitializerError
IllegalStateException
~~~

**Đừng chỉ bắt `IllegalStateException` ở caller và nghĩ rằng nó sẽ nhận nguyên đối tượng ban đầu.** Trong trường hợp khởi tạo này, đối tượng được quan sát ở đường thất bại đầu tiên thường là `ExceptionInInitializerError`, với `IllegalStateException` làm cause.

### Nguyên nhân thật có thể sâu hơn

~~~java
static String load() {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of("settings.txt"));
    } catch (java.io.IOException root) {
        throw new IllegalStateException(
                "cannot load settings", root);
    }
}
~~~

Đây là phương thức minh họa: nếu nó chạy trong static field initializer và đọc file thất bại, chain thường là:

~~~text
ExceptionInInitializerError
  └── cause -> IllegalStateException: cannot load settings
                  └── cause -> IOException: ...thất bại I/O...
~~~

Như vậy **`ExceptionInInitializerError` là ngữ cảnh về giai đoạn thất bại**, còn `IOException` sâu hơn có thể giải thích nguyên nhân vận hành cụ thể.

## 6. Nếu initializer ném `Error`, có bị bọc không?

**Không nhất thiết.** Quy tắc khởi tạo phân biệt lỗi đang truyền ra có thuộc `Error` hay không.

Ví dụ:

~~~java
class FailedAssertion {
    static {
        if (condition()) {
            throw new AssertionError("broken invariant");
        }
    }

    private static boolean condition() {
        return true;
    }

    static void touch() {
        System.out.println("unreachable");
    }
}
~~~

Class này biên dịch hợp lệ. Điều kiện `condition()` là lời gọi method, nên compiler vẫn nhìn thấy khả năng static block hoàn tất bình thường. Ở runtime, điều kiện trả `true` và một `AssertionError` được ném.

`AssertionError extends Error`, vì vậy lần đầu active use thường quan sát **chính `AssertionError`**; không bắt buộc có wrapper `ExceptionInInitializerError`.

**Không phải hướng thiết kế được khuyên cho lỗi cấu hình:** `AssertionError` mô tả một invariant nội bộ sai, không phù hợp để thay cho ngoại lệ checked/unchecked của những tình huống vận hành có thể phục hồi.

### Ví dụ trực tiếp `throw new ExceptionInInitializerError`

Code có thể tự ném:

~~~java
throw new ExceptionInInitializerError(
        new IllegalStateException("initialization failed"));
~~~

Đây là mảnh minh họa có thể đặt ở nơi `throw` hợp lệ. Đối tượng vốn đã thuộc `Error`, nên khi thoát static initializer, JVM không cần bọc thêm một EIIE nữa.

Tuy nhiên, thường **không cần tự tạo EIIE** trong code nghiệp vụ. Nếu code khởi tạo ném unchecked `IllegalStateException` với cause chính xác, JVM có cơ chế riêng báo lỗi class initialization. Đừng nhân đôi wrapper không cần thiết, trừ khi thiết kế rất đặc biệt cần điều đó.

## 7. Static initializer không có `throws` cho checked exception

Phương thức thông thường có thể khai báo:

~~~java
static String readFile() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}
~~~

Nhưng nếu dùng trực tiếp trong static initializer mà không bắt:

~~~java
class InvalidStatic {
    static final String TEXT = readFile();

    static String readFile() throws java.io.IOException {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of("config.txt"));
    }
}
~~~

**Class trên cố ý KHÔNG BIÊN DỊCH.** Biểu thức khởi tạo `TEXT` có thể ném checked `IOException` chưa được bắt.

Tương tự, không thể viết:

~~~java
static throws java.io.IOException {
    // Đây không phải cú pháp Java hợp lệ.
}
~~~

**Tại sao?** Static initializer không có chữ ký `throws` như method/constructor. Nếu việc khởi tạo lớp có khả năng ném checked exception, mã trong initializer phải **xử lý nó ngay tại đó** hoặc chuyển sang một kiến trúc không thực hiện công việc ấy trong initializer.

### Cách xử lý hợp lệ bằng try/catch

~~~java
class ConfigAtStartup {
    static final String TEXT;

    static {
        try {
            TEXT = java.nio.file.Files.readString(
                    java.nio.file.Path.of("config.txt"));
        } catch (java.io.IOException cause) {
            throw new IllegalStateException(
                    "cannot initialize configuration", cause);
        }
    }
}
~~~

Class hợp lệ về mặt cú pháp/checked exceptions. Nếu file không đọc được:

1. `Files.readString` ném checked `IOException`.
2. `catch` bắt và chuyển thành unchecked `IllegalStateException` với cause gốc.
3. `IllegalStateException` thoát initializer.
4. JVM báo `ExceptionInInitializerError`, thường với `IllegalStateException` làm cause.
5. Định nghĩa `ConfigAtStartup` bị đánh dấu initialization failed, không sẵn sàng để tự khởi tạo lại ở active use tiếp theo.

**Đây là mẫu hợp lệ về Java nhưng có thể là thiết kế không phù hợp về vận hành**, nhất là khi lỗi đọc file có thể tạm thời và ứng dụng cần retry.

### Không dùng constructor `throws` để “sửa” static initializer

~~~java
class WrongMentalModel {
    WrongMentalModel() throws java.io.IOException {
        // Constructor có thể khai báo checked exception.
    }

    static {
        // Không vì constructor có throws mà code static
        // được phép thả IOException ra ngoài.
    }
}
~~~

Constructor chỉ quy định lời gọi tạo **instance**, không làm thay luật exception của quá trình initialization lớp.

## 8. Static initializer phải có khả năng hoàn tất bình thường

Java còn có một yêu cầu compile-time: một static initializer **phải có khả năng hoàn tất bình thường** (*able to complete normally*).

Đoạn sau **không biên dịch**:

~~~java
class AlwaysFails {
    static {
        throw new IllegalStateException("always fails");
    }
}
~~~

Dù `IllegalStateException` là unchecked, một khối `static` chỉ có lệnh `throw` vô điều kiện không thể hoàn tất bình thường theo phân tích luồng của compiler.

Để mô tả một lỗi runtime có điều kiện:

~~~java
class RuntimeFailure {
    static {
        if (shouldFail()) {
            throw new IllegalStateException("runtime failure");
        }
    }

    private static boolean shouldFail() {
        return true;
    }
}
~~~

Đoạn này **có thể biên dịch**: với trình biên dịch, `shouldFail()` không phải hằng số false/true được suy ra như một constant expression cho nhánh if; khối có đường có thể hoàn tất bình thường. Tuy nhiên, khi chạy nó vẫn luôn thất bại.

Đây chỉ là ví dụ **phân biệt compile-time flow analysis và runtime behavior**, không phải lời khuyên cố ý phá một static initializer.

## 9. Sau lỗi khởi tạo: lớp ở trạng thái erroneous

Đây là hậu quả làm `ExceptionInInitializerError` nguy hiểm đối với cấu hình và tài nguyên dễ thất bại.

Khi initialization của một **định nghĩa lớp trong một class loader** kết thúc bất thường, JVM đánh dấu nó là **erroneous**. Điều đó không bị xóa khi caller bắt được EIIE.

Ví dụ khái niệm:

~~~java
try {
    Unstable.value(); // Lần đầu: EIIE.
} catch (ExceptionInInitializerError e) {
    System.out.println("first initialization failed");
}

try {
    Unstable.value(); // Lần sau: NoClassDefFoundError.
} catch (NoClassDefFoundError e) {
    System.out.println("class could not be initialized");
}
~~~

Đoạn trên là minh họa với class `Unstable` chưa được định nghĩa ở đây. Các biến thể loại lỗi tùy nguyên nhân ban đầu; nếu ban đầu initializer ném `Error`, caller có thể thấy `Error` đó thay vì EIIE.

**Không tự động khởi tạo lại:** một file cấu hình vừa được sửa hoặc một dịch vụ mạng vừa hoạt động trở lại **không** làm initializer của class erroneous chạy lại.

### Phân biệt với lỗi trong method static sau initialization

~~~java
class RetryableOperation {
    static int calls;

    static String load(boolean ready) {
        calls++;
        if (!ready) {
            throw new IllegalStateException("temporarily unavailable");
        }
        return "ready";
    }
}
~~~

Ở đây initialization của `RetryableOperation` thành công (không có static initializer dễ lỗi). Một lần gọi `load(false)` ném exception **trong method thông thường**, không đánh dấu cả class erroneous. Có thể gọi lại `load(true)` và nhận kết quả thành công nếu hợp đồng cho phép.

**Khác biệt cốt lõi:** “Exception xảy ra trong một static method” **không giống** “Exception xảy ra trong quá trình class initialization”. Tên `static` xuất hiện trong cả hai trường hợp nhưng thời điểm và hậu quả JVM hoàn toàn khác nhau.

## 10. `NoClassDefFoundError` sau lần thất bại không hẳn do thiếu JAR

`NoClassDefFoundError` có thể xuất hiện khi JVM không thể tìm/định nghĩa một class cần thiết lúc runtime, chẳng hạn thiếu dependency. Nhưng nó cũng có thể xuất hiện vì:

- Class đã được load/linked thành công.
- Một lần initialization của class đó trước đây **thất bại**.
- Lần active use sau cố dùng định nghĩa class erroneous ấy.

Do đó, khi gặp log:

~~~text
java.lang.NoClassDefFoundError:
    Could not initialize class com.example.ConfigurationHolder
~~~

đừng tự động kết luận “thiếu `ConfigurationHolder.class`”. Hãy tìm trong log **lần đầu** lớp này được dùng: thường sẽ có `ExceptionInInitializerError` hoặc một `Error` ban đầu, kèm cause chain về nguyên nhân.

### Vì sao hai lần gọi cho loại lỗi khác nhau?

| Lần sử dụng | Trạng thái class | Kết quả |
| --- | --- | --- |
| Lần đầu cần initialization | Chưa initialized | Thử chạy initializers; có thể thành công hoặc thất bại |
| Đang chạy initializer và ném non-`Error` | Initialization thất bại | Thường báo `ExceptionInInitializerError` |
| Đang chạy initializer và ném `Error` | Initialization thất bại | Có thể báo nguyên đối tượng `Error` |
| Lần active use tiếp sau, cùng definition/class loader | Erroneous | Thường báo `NoClassDefFoundError` |
| Method static thất bại sau class initialized | Initialized thành công | Exception của method, **không tự làm class erroneous** |

Không dựa vào message `NoClassDefFoundError` như một chuỗi chính xác giữa các phiên bản JVM. **Phân loại dựa trên thời điểm, class name, cause và log lần đầu.**

## 11. Một ví dụ Java 17+ độc lập, không cần database hoặc file ngoài

Chương trình `InitializationFailureDemo.java` sau có năm mục tiêu:

1. `Good` khởi tạo thành công; static initializers chỉ chạy một lần.
2. Đọc compile-time constant hoặc class literal không tự làm `Good` chạy initializer.
3. `BrokenWithRuntime` có một `IOException` giả lập được bọc thành `IllegalStateException` ở initializer, rồi JVM báo `ExceptionInInitializerError`.
4. `BrokenWithError` ném `AssertionError` trong static block; lần đầu nhận `AssertionError` trực tiếp, lần sau gặp `NoClassDefFoundError`.
5. `RecoverableLoader` cho thấy I/O mô phỏng có thể thử lại trong **method thường**, không làm class erroneous.

Tạo tệp **`InitializationFailureDemo.java`**:

~~~java
import java.io.IOException;

public class InitializationFailureDemo {

    static final class Good {
        static final int MAGIC = 11;
        static int count = initializeCount();

        static {
            System.out.println("Good.staticBlock");
        }

        static int initializeCount() {
            System.out.println("Good.fieldInitializer");
            return 7;
        }

        static int count() {
            return count;
        }
    }

    static final class BrokenWithRuntime {
        static final String CONFIG = loadDuringInitialization();

        static String loadDuringInitialization() {
            System.out.println("Runtime.initializer");
            try {
                simulateFileLoad(false);
                return "ok";
            } catch (IOException cause) {
                throw new IllegalStateException(
                        "configuration unavailable", cause);
            }
        }

        static String config() {
            return CONFIG;
        }
    }

    static final class BrokenWithError {
        static {
            System.out.println("Error.staticBlock");
            if (shouldFail()) {
                throw new AssertionError("broken invariant");
            }
        }

        static boolean shouldFail() {
            return true;
        }

        static void ping() {
            System.out.println("Error.ping");
        }
    }

    static final class RecoverableLoader {
        static int calls;

        static String load(boolean available) throws IOException {
            calls++;
            simulateFileLoad(available);
            return "configuration ready";
        }
    }

    public static void main(String[] args) {
        System.out.println("== passive reference ==");
        System.out.println("literal="
                + Good.class.getSimpleName());
        System.out.println("constant=" + Good.MAGIC);

        System.out.println("== successful initialization ==");
        System.out.println("goodCount=" + Good.count());
        System.out.println("goodAgain=" + Good.count());

        System.out.println("== runtime failure first use ==");
        try {
            BrokenWithRuntime.config();
        } catch (ExceptionInInitializerError error) {
            System.out.println("first="
                    + error.getClass().getSimpleName());
            Throwable wrapped = error.getCause();
            System.out.println("cause="
                    + wrapped.getClass().getSimpleName()
                    + ": " + wrapped.getMessage());
            Throwable root = wrapped.getCause();
            System.out.println("root="
                    + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }

        System.out.println("== runtime failure second use ==");
        try {
            BrokenWithRuntime.config();
        } catch (NoClassDefFoundError error) {
            System.out.println("second="
                    + error.getClass().getSimpleName());
        }

        System.out.println("== Error failure first use ==");
        try {
            BrokenWithError.ping();
        } catch (AssertionError error) {
            System.out.println("firstError="
                    + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        }

        System.out.println("== Error failure second use ==");
        try {
            BrokenWithError.ping();
        } catch (NoClassDefFoundError error) {
            System.out.println("secondError="
                    + error.getClass().getSimpleName());
        }

        System.out.println("== regular method can retry ==");
        try {
            RecoverableLoader.load(false);
        } catch (IOException error) {
            System.out.println("loadFailed="
                    + error.getMessage());
        }
        try {
            System.out.println("loadSuccess="
                    + RecoverableLoader.load(true));
        } catch (IOException error) {
            System.out.println("unexpected retry failure");
        }
        System.out.println("loadCalls=" + RecoverableLoader.calls);
    }

    static void simulateFileLoad(boolean available)
            throws IOException {
        if (!available) {
            throw new IOException("file unavailable");
        }
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac InitializationFailureDemo.java
java InitializationFailureDemo
~~~

**Stdout chính xác:**

~~~text
== passive reference ==
literal=Good
constant=11
== successful initialization ==
Good.fieldInitializer
Good.staticBlock
goodCount=7
goodAgain=7
== runtime failure first use ==
Runtime.initializer
first=ExceptionInInitializerError
cause=IllegalStateException: configuration unavailable
root=IOException: file unavailable
== runtime failure second use ==
second=NoClassDefFoundError
== Error failure first use ==
Error.staticBlock
firstError=AssertionError: broken invariant
== Error failure second use ==
secondError=NoClassDefFoundError
== regular method can retry ==
loadFailed=file unavailable
loadSuccess=configuration ready
loadCalls=2
~~~

### Vì sao `Good.class` không in phần khởi tạo?

`Good.class` lấy class literal. Việc gọi `getSimpleName()` trên đối tượng `Class` để lấy tên không tự yêu cầu chạy `Good` static initialization. `MAGIC` lại là compile-time constant, nên việc đọc `Good.MAGIC` không yêu cầu khởi tạo lớp theo cách đọc một static field thông thường.

Lần đầu `Good.count()` mới yêu cầu initialization; `count = initializeCount()` chạy, sau đó static block chạy theo thứ tự văn bản. Lần gọi thứ hai chỉ thực hiện method, không khởi tạo lại.

### Vì sao `BrokenWithRuntime` cho thấy ba tầng?

`simulateFileLoad(false)` ném checked `IOException`. Nó được **bắt trong helper** rồi bọc thành `IllegalStateException` có cause là chính IOException. Khi helper chạy trong static field initializer của `BrokenWithRuntime`, unchecked `IllegalStateException` thoát ra. JVM báo `ExceptionInInitializerError` với:

~~~text
ExceptionInInitializerError
    └── IllegalStateException: configuration unavailable
          └── IOException: file unavailable
~~~

`getCause()` trên EIIE trả wrapper; đọc tiếp `getCause()` của wrapper trả IOException. Nếu bỏ constructor truyền cause, thông tin sâu nhất có thể bị mất.

### Vì sao lần gọi lại không in `Runtime.initializer` nữa?

Class đã initialization failed và ở trạng thái erroneous trong class loader ấy. JVM **không** chạy lại `loadDuringInitialization()`. Lần dùng sau báo `NoClassDefFoundError`.

### Vì sao `BrokenWithError` không có `ExceptionInInitializerError` ở lần đầu?

`AssertionError` đã thuộc nhánh `Error`. JVM có thể truyền trực tiếp nó khi initialization thất bại. Lần sau class vẫn erroneous, nên báo `NoClassDefFoundError`.

### Vì sao `RecoverableLoader` có thể thử lại?

`RecoverableLoader` khởi tạo class thành công; I/O xảy ra trong method `load()` sau đó. Lỗi `IOException` của một lần gọi không làm cả class erroneous. Caller có thể quyết định thử lại có giới hạn khi môi trường thay đổi. Ví dụ giả lập `available` để kết quả không phụ thuộc file hay mạng thật; **không phải chính sách retry chung cho mọi thao tác ghi dữ liệu**.

## 12. Constructor thất bại không giống class initialization thất bại

Xét:

~~~java
class CustomerConnection {
    CustomerConnection(boolean available)
            throws IOException {
        if (!available) {
            throw new IOException("connection not available");
        }
    }
}
~~~

Đây là class hợp lệ khi import `java.io.IOException`. Khi:

~~~java
new CustomerConnection(false);
~~~

ném `IOException`, điều đó không tự đánh dấu `CustomerConnection` là erroneous nếu quá trình initialization của class đã thành công. Có thể thử tạo một instance mới với input khác, tùy hợp đồng constructor.

Bảng so sánh:

| Khía cạnh | Static initializer thất bại | Constructor thất bại |
| --- | --- | --- |
| Thời điểm | JVM initialize class | Tạo instance sau khi class được initialize |
| Có thể khai báo `throws IOException` trực tiếp? | Không | Có |
| Có thể làm class erroneous? | Có | Không chỉ vì constructor ném lỗi |
| Gọi lại trong cùng class loader | Thường `NoClassDefFoundError` | Có thể thử `new` lại |
| Phạm vi trạng thái thất bại | Định nghĩa class | Lần tạo instance |
| Dùng để tải cấu hình cần retry | Thường kém phù hợp | Constructor/factory có thể phù hợp tùy thiết kế |

Có một sắc thái: nếu `new` lần đầu kích hoạt **class initialization thất bại trước khi vào constructor**, caller vẫn nhận lỗi initialization như đã học. Vì vậy không được suy ra từ cú pháp `new` rằng mọi lỗi quan sát được đều phát sinh bên trong constructor.

## 13. Factory/loader có checked exception là lựa chọn tốt khi cần phục hồi

Thay vì:

~~~java
class StaticConfig {
    static final String TEXT = readFileUnchecked();
}
~~~

có thể dùng API bình thường:

~~~java
final class Configuration {
    private final String text;

    private Configuration(String text) {
        this.text = text;
    }

    static Configuration load(java.nio.file.Path file)
            throws java.io.IOException {
        return new Configuration(
                java.nio.file.Files.readString(file));
    }

    String text() {
        return text;
    }
}
~~~

Lớp Java này biên dịch độc lập khi đặt trong một tệp Java thích hợp. `Configuration.load(path)` thực hiện I/O **trong lời gọi method**, có `throws IOException` để caller được trình biên dịch nhắc xử lý.

Lợi ích:

- Caller có thể báo lỗi, giới hạn retry, dùng fallback được phép hoặc yêu cầu người dùng sửa đường dẫn.
- Một lần đọc file lỗi không tự phá trạng thái khởi tạo của cả lớp.
- Có thể truyền cấu hình qua constructor/dependency injection và kiểm thử bằng data giả lập.
- Phân biệt rõ lỗi của lần **nạp dữ liệu** với lỗi của chính JVM **khởi tạo class**.
- Có thể xây chiến lược quản lý vòng đời và đóng tài nguyên có kiểm soát.

Nếu không muốn public API phụ thuộc vào `IOException`, có thể bọc ở ranh giới rõ ràng bằng custom checked exception nhận cause. Nhưng không nên đánh mất nguyên nhân gốc.

### Khi nào static initializer vẫn phù hợp?

Đối với hằng số, lookup table thuần túy và những cấu trúc:

- Không phụ thuộc trạng thái mạng/tệp dễ thay đổi.
- Có kết quả xác định từ dữ liệu nội bộ hợp lệ.
- Hoàn thành nhanh và ít side effect.
- Không có yêu cầu retry động.
- Không phụ thuộc vòng chờ các thread khác.

Ví dụ:

~~~java
class Constants {
    static final int DEFAULT_PORT = 8080;
    static final java.util.List<String> LEVELS =
            java.util.List.of("LOW", "MEDIUM", "HIGH");
}
~~~

Đây là những trạng thái tĩnh đơn giản hơn nhiều so với mở kết nối database lúc load class.

## 14. Lazy static holder có giải quyết retry không?

Mẫu *initialization-on-demand holder*:

~~~java
class SingletonService {
    private static class Holder {
        static final SingletonService INSTANCE =
                createSingleton();
    }

    static SingletonService instance() {
        return Holder.INSTANCE;
    }

    private static SingletonService createSingleton() {
        return new SingletonService();
    }
}
~~~

Class hợp lệ. `Holder` thường được khởi tạo khi `instance()` lần đầu cần `Holder.INSTANCE`. Đây là kỹ thuật lazy initialization hữu ích cho trạng thái tạo một lần an toàn.

**Nhưng không phải cơ chế retry.** Nếu `createSingleton()` ném exception trong lúc `Holder` khởi tạo, `Holder` có thể bị đánh dấu erroneous. Những lần đọc `Holder.INSTANCE` sau thường gặp `NoClassDefFoundError`.

Đừng hiểu “lazy” là “mỗi lần thất bại sẽ thử tạo lại”. Nếu cần kết nối lại hoặc refresh cấu hình, thiết kế lifecycle riêng với state machine, factory, cache invalidation hoặc provider có khả năng retry có giới hạn.

## 15. `getCause()` và `getException()` của `ExceptionInInitializerError`

`ExceptionInInitializerError` có các API:

~~~java
Throwable cause = error.getCause();
Throwable original = error.getException();
~~~

Đây là mảnh minh họa với `error` kiểu `ExceptionInInitializerError`.

`getException()` là một API lịch sử để truy xuất ngoại lệ được lưu khi tạo wrapper. Trong mã hiện đại, `getCause()` thường phù hợp hơn vì nhất quán với cách duyệt cause chain trên `Throwable`.

Ví dụ:

~~~java
IllegalStateException root =
        new IllegalStateException("configuration invalid");

ExceptionInInitializerError error =
        new ExceptionInInitializerError(root);

System.out.println(error.getCause() == root); // true
System.out.println(error.getException() == root); // true
~~~

**Không giả định EIIE bất kỳ luôn có cause khác null.** Code có thể tự tạo:

~~~java
ExceptionInInitializerError empty =
        new ExceptionInInitializerError();

System.out.println(empty.getCause() == null); // true
~~~

Một phương thức logger tổng quát cần kiểm tra null trước khi gọi `getClass()`/`getMessage()` của cause.

### Không bắt EIIE rồi thay bằng thông báo vô nghĩa

Không nên chỉ viết:

~~~java
catch (ExceptionInInitializerError e) {
    System.err.println("Cannot start");
}
~~~

ở một phạm vi lớn rồi bỏ qua. Lỗi gốc có thể là `NullPointerException` từ static field initializer, thiếu cấu hình, xung đột phiên bản hoặc thao tác I/O. Nếu chỉ in một thông báo chung, bạn mất dữ liệu để chẩn đoán.

Nếu ở ranh giới startup thực sự cần báo lỗi, hãy ghi lại cause chain an toàn, xác định chính sách dừng/khởi động lại và **không tiếp tục sử dụng lớp đã erroneous**.

## 16. `finally` và try-with-resources khi initialization thất bại

Một `Throwable` ném trong static initializer vẫn tuân theo quy tắc dọn dẹp của các cấu trúc Java khi chương trình còn thực thi luồng rời scope bình thường.

~~~java
class CleanupDuringInit {
    static {
        try {
            System.out.println("initializing");
            fail();
        } finally {
            System.out.println("cleanup");
        }
    }

    private static void fail() {
        throw new IllegalStateException("cannot initialize");
    }
}
~~~

Khi JVM chạy initializer của `CleanupDuringInit`:

~~~text
initializing
cleanup
~~~

được in trước khi lỗi thoát khỏi quá trình initialization và thường bị bọc thành `ExceptionInInitializerError`.

Dọn dẹp trong `finally` **không sửa trạng thái erroneous**. Một class có thể đã giải phóng mọi tài nguyên đang mở mà vẫn không được JVM khởi tạo lại sau thất bại.

### Suppressed exceptions trong try-with-resources

Ví dụ:

~~~java
class FailingResource implements AutoCloseable {
    @Override
    public void close() throws java.io.IOException {
        throw new java.io.IOException("close failed");
    }
}
~~~

Nếu code trong static initializer có một try-with-resources với `FailingResource` và thân `try` ném lỗi chính, Java có thể gắn lỗi `close()` thành **suppressed exception** trên lỗi chính. Nếu lỗi chính là `IllegalStateException` và JVM bọc bằng EIIE, suppressed của lỗi đóng nằm trên **lỗi chính** đó, không tự trở thành cause trực tiếp của EIIE.

Khi chẩn đoán, cần phân biệt:

- `getCause()`: chuỗi nguyên nhân từ wrapper đến lỗi gốc.
- `getSuppressed()`: những lỗi phụ khi dọn dẹp.
- `ExceptionInInitializerError`: ngữ cảnh class initialization thất bại.

**Không nên chỉ in EIIE message rồi bỏ qua suppressed/cause** nếu đang phân tích một lỗi khởi tạo tài nguyên phức tạp.

## 17. Đa luồng và class initialization lock

JVM có cơ chế đồng bộ hóa khởi tạo class để các thread không tự chạy cùng initializer độc lập như nhiều lần khởi tạo riêng.

Thông thường:

- Một thread bắt đầu initialization cho một class.
- Thread khác cần active use class đó có thể phải chờ kết quả initialization.
- Sau khi khởi tạo thành công, những thread cần class ấy có thể dùng trạng thái đã initialized theo các bảo đảm của JVM.
- Nếu khởi tạo thất bại, class trở thành erroneous; thread đang chờ hoặc thread sau đó không tự chạy lại initializer.
- Một static initializer mất nhiều thời gian hoặc chờ I/O có thể gây chậm startup, latency spike hoặc deadlock khi có vòng phụ thuộc.

### Vòng chờ khi initializer đợi thread khác

Giả sử static initializer bắt đầu một worker thread rồi `join()`, trong khi worker lại cần gọi method static của **chính class còn đang được khởi tạo**. Worker có thể phải chờ initialization hoàn tất, còn thread khởi tạo chờ worker hoàn tất — tạo deadlock.

Không cần một ví dụ đa luồng nguy hiểm chạy thực để hiểu quy tắc. Thực hành nên tránh khởi động workflow phức tạp, block chờ mạng hoặc lấy nhiều lock trong static initializer.

### Circular initialization có thể phơi giá trị mặc định

Với hai class phụ thuộc nhau qua các trường static, một quá trình initialization đệ quy có thể quan sát **giá trị mặc định đã được chuẩn bị** của một trường chưa chạy initializer của nó trong một số cấu trúc. Điều này **không nhất thiết ném EIIE** nhưng có thể gây bug khó hiểu như số `0` hoặc tham chiếu `null` bất ngờ.

Vì vậy, đừng xây một đồ thị static initializers phụ thuộc chéo phức tạp rồi chỉ dựa vào việc “JVM sẽ xử lý đúng”. Giảm vòng phụ thuộc, dùng factory rõ ràng và tránh side effect là những lựa chọn dễ kiểm thử hơn.

## 18. Đọc stack trace: tìm lỗi đầu tiên, không chỉ dòng cuối

Một bản log có thể trông như sau:

~~~text
java.lang.ExceptionInInitializerError
    at com.example.App.main(App.java:...)
Caused by: java.lang.IllegalStateException: cannot load configuration
    at com.example.ConfigHolder.load(ConfigHolder.java:...)
Caused by: java.io.IOException: file unavailable
    at ...
~~~

Đây là **mẫu cấu trúc log minh họa**, không phải stack trace byte-for-byte của một lần chạy cụ thể.

Sau đó, các request khác có thể ghi:

~~~text
java.lang.NoClassDefFoundError:
    Could not initialize class com.example.ConfigHolder
~~~

Nếu chỉ đọc log mới nhất, dễ chẩn đoán nhầm rằng không có class trên classpath. Việc cần làm là **tìm sự kiện đầu tiên** đưa class vào trạng thái erroneous.

### Quy trình điều tra thực tế

1. Ghi lại **class name** xuất hiện trong EIIE hoặc `NoClassDefFoundError`.
2. Tìm lần đầu class được active use, đặc biệt khi startup.
3. Mở stack trace đầu tiên để tìm `<clinit>`, static field initializer hoặc static block.
4. Duyệt `getCause()`, chú ý `NullPointerException`, `IllegalStateException`, `IOException`, lỗi parse và lỗi dependency.
5. Kiểm tra `getSuppressed()` của các throwable liên quan nếu dùng try-with-resources.
6. Kiểm tra các static fields/blocks **theo thứ tự khai báo**.
7. Xác định có phụ thuộc I/O, hệ thống bên ngoài, môi trường hoặc chu trình class initialization không.
8. Kiểm tra các thread đang chờ class initialization khi nghi deadlock.
9. Phân biệt class thực sự **thiếu lúc runtime** với class **có mặt nhưng initialization failed**.
10. Chọn cách sửa nguồn lỗi, không chỉ thêm `catch (Error)`.
11. Nếu muốn retry, chuyển thao tác dễ thất bại sang factory/provider được quản lý; không gọi lại một class erroneous.
12. Ghi log có cấu trúc và lọc dữ liệu nhạy cảm nếu cause/message có đường dẫn, token hay chuỗi kết nối.

Một lỗi như `ExceptionInInitializerError` **không tự cho biết lỗi nghiệp vụ nằm ở đâu**; nó là tín hiệu rằng cần xem quá trình initialization và lỗi gốc.

## 19. Vì sao không nên tự động catch `Error` để “cứu hệ thống”?

Có thể viết:

~~~java
try {
    CriticalConfig.initialize();
} catch (Error e) {
    System.err.println("initialization problem");
}
~~~

Đây là mảnh minh họa với `CriticalConfig` giả định. Nhưng handler chỉ in log không biến class erroneous thành class initialized. Những lời gọi khác vẫn có thể thất bại và hệ thống tiếp tục ở trạng thái thiếu dependency quan trọng.

`catch (Throwable)` còn rộng hơn, có thể nhận `OutOfMemoryError`, `StackOverflowError` và các lỗi mà ứng dụng không đủ điều kiện phục hồi an toàn. **Không dùng catch rộng làm cơ chế mặc định cho mọi lỗi initialization**.

Có những ranh giới chuyên biệt như bootstrap hoặc test runner muốn ghi nhận lỗi startup. Trong trường hợp đó, có thể log theo chính sách rồi dừng/quản lý lại vòng đời, chứ không tùy tiện báo thành công cho những thao tác cần class chưa initialized.

## 20. Kiểm thử static initialization failure

Kiểm thử loại lỗi này khó hơn kiểm thử một method bình thường vì **một class definition khởi tạo thất bại không tự reset** giữa các lần gọi trong cùng class loader.

### Tránh test dựa vào thứ tự ngẫu nhiên

Nếu hai test cùng dùng một class có static initializer ném lỗi:

- Test gọi trước có thể nhận `ExceptionInInitializerError` (hoặc một `Error` gốc).
- Test gọi sau có thể nhận `NoClassDefFoundError`.
- Kết quả dễ phụ thuộc thứ tự chạy và việc test runner tái sử dụng JVM/class loader.

Đừng viết hai test với giả định mỗi lần gọi cùng class đều “khởi tạo từ đầu”.

### Cách kiểm thử ổn định hơn

- Chạy các ca trong **JVM subprocess riêng** nếu bắt buộc kiểm chứng initialization failure một cách cách ly.
- Hoặc dùng **class loader riêng** khi đã nắm rõ class loading/parent delegation, nhưng đây là lựa chọn phức tạp.
- Tốt hơn trong thiết kế ứng dụng: chuyển thao tác dễ thất bại sang **factory/method có thể gọi lại**, rồi viết unit test thông thường cho nhánh success/failure.
- Test nguyên nhân ban đầu và chính sách fallback ở tầng sở hữu vòng đời, không chỉ test loại wrapper.

Ví dụ chương trình `InitializationFailureDemo.java` cố tình giữ thứ tự **first use → second use** trong một lần chạy duy nhất, nên stdout không phụ thuộc trạng thái của test trước.

## 21. Những nhầm lẫn thường gặp

### 21.1. “EIIE có nghĩa Java không tìm thấy file .class”

Không. EIIE phản ánh **khởi tạo thất bại**. Không tìm thấy class ở runtime là một lớp vấn đề khác có thể dẫn đến `NoClassDefFoundError`.

### 21.2. “Hễ method static ném RuntimeException thì lớp erroneous”

Không. Nếu class đã initialized, exception của method bình thường không tự phá trạng thái class.

### 21.3. “Mọi lỗi trong static đều bị bọc thành EIIE”

Không. `Error` hoặc subclass có thể được truyền trực tiếp ở lần đầu.

### 21.4. “Static initializer có thể ghi `throws IOException`”

Không. Cần bắt checked exception hoặc chuyển công việc sang method phù hợp.

### 21.5. “Constructor khai báo throws thay cho khối static”

Không. Constructor và class initialization thuộc các pha khác nhau.

### 21.6. “Một static block có một câu `throw` vô điều kiện vẫn biên dịch nếu unchecked”

Không. Static initializer còn phải **có khả năng hoàn tất bình thường** theo compile-time analysis.

### 21.7. “Bắt EIIE thì lần sau class tự initialized lại”

Không. Cùng class definition/class loader, class erroneous không được tự chạy initializer lần nữa.

### 21.8. “Sau EIIE, thiếu JAR là nguyên nhân chắc chắn”

Không. `NoClassDefFoundError` về sau có thể do initialization failed trước đó. Phải tìm log đầu tiên.

### 21.9. “`catch (Exception)` sẽ bắt cả EIIE”

Không. EIIE kế thừa `Error`.

### 21.10. “Chỉ cần in EIIE.getMessage() để có nguyên nhân”

Không. Cause chain thường là thông tin chính. Message có thể không đủ và không phải hợp đồng ổn định.

### 21.11. “EIIE.getCause() luôn khác null”

Không. Code có thể tự tạo EIIE không có cause. Viết logger null-safe.

### 21.12. “Lazy holder tự động hỗ trợ retry”

Không. Holder cũng là class chịu luật erroneous khi initialization failed.

### 21.13. “`static final` luôn không kích hoạt class initialization”

Không. Chỉ compile-time constant có ngữ nghĩa đặc biệt; static final object hoặc giá trị từ method vẫn có thể đòi khởi tạo.

### 21.14. “Class literal luôn làm chạy static block”

Không. `SomeClass.class` tự nó không đòi class initialization.

### 21.15. “`finally` chạy xong là class hết erroneous”

Không. Cleanup và trạng thái initialization là hai khái niệm riêng.

### 21.16. “Lỗi đóng tài nguyên là cause trực tiếp của EIIE”

Không nhất thiết. Nếu thân try đã ném lỗi chính, lỗi đóng thường được suppressed trên lỗi chính theo quy tắc try-with-resources.

### 21.17. “I/O trong static initializer là cách tối ưu để có singleton an toàn”

Không. Nó có thể gây lỗi khó retry, thời gian startup dài hoặc deadlock; dùng factory/lifecycle khi tài nguyên cần phục hồi.

### 21.18. “EIIE là checked vì có từ Exception trong tên”

Không. Phân cấp xác định tính checked/unchecked; EIIE thuộc `Error`.

### 21.19. “Static initialization failure và constructor failure giống nhau”

Không. Constructor ném exception không tự làm class erroneous nếu class đã initialized.

### 21.20. “Không cần xem log trước khi class lỗi”

Sai. Các lỗi tiếp theo thường chỉ còn `NoClassDefFoundError`; lỗi đầu tiên quan trọng nhất.

## 22. Checklist thiết kế tránh EIIE trong ứng dụng

Trước khi thêm công việc vào static initializer, tự hỏi:

1. Công việc có **thể thất bại tạm thời** (file, network, database, DNS) không?
2. Nếu thất bại, caller có cần **retry có giới hạn** không?
3. Có thể **đưa vào factory/loader** với `throws` thích hợp không?
4. Static field có thực sự là compile-time constant hoặc dữ liệu thuần túy không?
5. Mọi static initializer có chạy nhanh, không block và ít side effect không?
6. Có chu trình phụ thuộc giữa các static fields/classes không?
7. Có khả năng deadlock do chờ thread khác trong lúc class initialization không?
8. Nếu một lớp phụ thuộc không initialized được, ứng dụng nên dừng hoặc degrade theo chính sách nào?
9. Có log nguyên nhân gốc mà không lộ dữ liệu nhạy cảm không?
10. Có unit test kiểm tra cơ chế retry ở **method** thay vì cố reset trạng thái class không?
11. Có dùng try-with-resources đúng quyền sở hữu tài nguyên không?
12. Có hiểu khác biệt giữa `getCause()` và `getSuppressed()` trong một lỗi khởi tạo phức tạp không?
13. Có phân biệt `NoClassDefFoundError` do thiếu class với do erroneous initialization không?
14. Có tránh bắt `Error` rộng rồi im lặng tiếp tục không?

Một static initializer tốt thường khởi tạo trạng thái **đơn giản, có thể dự đoán**, không phải mở một kết nối sống phụ thuộc nhiều yếu tố bên ngoài.

## 23. Câu hỏi tự kiểm tra

1. `ExceptionInInitializerError` thuộc nhánh `Error` hay `Exception`?
2. Nó là checked hay unchecked?
3. Hai loại đoạn mã nào thường tham gia khởi tạo static?
4. Static field initializer và static block có chạy theo thứ tự khai báo không?
5. Mọi lần gọi constructor có chạy lại static initializer không?
6. Đọc một compile-time constant có nhất thiết khởi tạo class không?
7. Lấy `SomeClass.class` có tự chạy static block không?
8. Gọi phương thức static có thể kích hoạt initialization không?
9. Khi static initializer ném `IllegalStateException` ra ngoài, caller lần đầu thường thấy gì?
10. `getCause()` của EIIE có thể chứa đối tượng nào?
11. Nếu lỗi gốc của wrapper là `IOException`, nên giữ nó bằng constructor gì?
12. Khi static initializer ném trực tiếp `AssertionError`, có bắt buộc JVM bọc EIIE không?
13. Tại sao static initializer không thể khai báo `throws IOException`?
14. Một static block chỉ có `throw new RuntimeException()` vô điều kiện có biên dịch không?
15. Sau lần initialization failed, active use tiếp theo thường thấy loại lỗi nào?
16. Khi đã bắt EIIE, class có tự thử chạy initializer lại không?
17. `NoClassDefFoundError` có luôn có nghĩa thiếu dependency không?
18. Một method static ném `IOException` sau class initialized có làm class erroneous không?
19. Constructor ném exception có tự đánh dấu class erroneous không?
20. Khi cần đọc cấu hình có thể retry, nên chọn static initializer hay factory?
21. Lazy static holder có tự động retry khi holder initialization failed không?
22. Vì sao `catch (Exception)` không bắt được EIIE?
23. `getException()` trên EIIE có liên quan gì tới `getCause()`?
24. Có thể tồn tại EIIE không có cause không?
25. Lỗi `close()` trong try-with-resources thường nằm ở đâu nếu thân try đã ném lỗi chính?
26. `finally` thành công có sửa trạng thái erroneous không?
27. Tại sao nên tránh side effect/I/O lâu trong class initialization?
28. Cần tìm log nào khi các request sau chỉ ghi `NoClassDefFoundError`?
29. Trong cùng một class loader, chạy test thứ nhất làm class erroneous có thể ảnh hưởng test thứ hai không?
30. Phân biệt câu “static method thất bại” với “class initialization thất bại” bằng một ví dụ.

### Gợi ý đáp án

1. `Error`, qua `LinkageError`.
2. Unchecked.
3. Static field initializers và static initializer blocks.
4. Có, theo thứ tự văn bản khi JVM initialize class.
5. Không.
6. Không.
7. Không tự yêu cầu initialization.
8. Có, nếu là active use và class chưa initialized.
9. Thường `ExceptionInInitializerError`.
10. Ngoại lệ không phải `Error` ban đầu, ví dụ `IllegalStateException`.
11. `super(message, cause)` trong wrapper hoặc constructor thích hợp nhận cause.
12. Không; một `Error` có thể được truyền trực tiếp.
13. Không có cú pháp/khai báo checked `throws` cho static initializer.
14. Không, vì block phải có khả năng hoàn tất bình thường.
15. Thường `NoClassDefFoundError`.
16. Không.
17. Không; cũng có thể do class initialization đã failed trước đó.
18. Không; exception của lời gọi method thường không tự phá trạng thái class.
19. Không nếu class initialization thành công.
20. Factory/loader có `throws` và chính sách retry hợp lệ.
21. Không.
22. EIIE thuộc `Error`, không thuộc `Exception`.
23. Cả hai giúp truy xuất nguyên nhân đã được lưu khi wrapper được tạo phù hợp; `getCause()` là API hiện đại.
24. Có.
25. Trong `getSuppressed()` của lỗi chính.
26. Không.
27. Vì có thể kéo dài startup, gây deadlock và khó phục hồi sau initialization failed.
28. Lần đầu class xuất hiện EIIE hoặc một `Error` ban đầu, cùng cause chain.
29. Có; class erroneous không tự reset.
30. Static method gọi sau khi class initialized có thể ném lỗi rồi lần sau vẫn dùng class; lỗi trong static initializer có thể làm class erroneous.

## 24. Ghi nhớ

**`ExceptionInInitializerError` là lỗi báo một class/interface không khởi tạo thành công, thường do một exception không thuộc `Error` thoát khỏi static initialization.** Hãy đọc `getCause()` hoặc `getException()` để tìm nguyên nhân; nếu lỗi gốc đã là `Error`, JVM có thể truyền trực tiếp đối tượng ấy. Sau initialization failure, class definition có thể ở trạng thái erroneous, khiến active use sau gặp `NoClassDefFoundError` thay vì chạy lại static block. Không nhầm hiện tượng này với lỗi thiếu class trên classpath hoặc exception từ một static method bình thường. Đối với cấu hình, I/O và tài nguyên cần retry, nên chuyển công việc sang factory/method có quản lý vòng đời thay vì để nó thất bại trong quá trình khởi tạo class.

### Tham khảo chuẩn Java 17

- Java Language Specification, Initialization of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- Java Virtual Machine Specification, Initialization: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- `ExceptionInInitializerError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html
- `NoClassDefFoundError`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html
