# Unchecked exception khi ghi đè phương thức trong Java

> **Java Core – Exception** · Nhóm **Kế thừa và hợp đồng** · Chủ đề: phương thức override được khai báo hoặc ném unchecked exception như thế nào, so sánh với giới hạn của checked exception và ảnh hưởng tới caller. Các ví dụ hoàn chỉnh dùng **Java 17+**.

## 1. Kết luận quan trọng nhất

Khi một phương thức **ghi đè (override)** phương thức của lớp cha hoặc triển khai phương thức của interface, Java giới hạn **checked exception** được khai báo trong mệnh đề `throws`, nhưng **không áp đặt cùng giới hạn đối với unchecked exception**.

Ví dụ:

~~~java
interface Job {
    void execute();
}

class RemoteJob implements Job {
    @Override
    public void execute() throws IllegalStateException {
        throw new IllegalStateException("service unavailable");
    }
}
~~~

Đây là hai khai báo kiểu Java hợp lệ, có thể đặt trong một file riêng nếu không có quy định khác về tên public class. Phương thức của interface `Job.execute()` **không khai báo ngoại lệ nào**, trong khi phiên bản override:

- Được phép khai báo `throws IllegalStateException`.
- Được phép thực sự ném `IllegalStateException`.
- Không buộc caller viết `try/catch` hoặc `throws` chỉ vì loại ngoại lệ này.
- Vẫn có thể làm lời gọi **kết thúc bất thường tại runtime** nếu exception không được xử lý.

Lý do: `IllegalStateException extends RuntimeException`, thuộc nhóm **unchecked**.

**Đối chiếu:** Nếu đổi `throws IllegalStateException` ở trên thành `throws IOException`, trình biên dịch sẽ **từ chối**, vì `IOException` là checked exception mới mà hợp đồng phương thức `Job.execute()` không cho phép.

Điều quan trọng cho thiết kế là **Java cho phép ở compile time không đồng nghĩa với thay đổi hành vi luôn hợp lý**. Một subclass có thể ném unchecked exception mới nhưng vẫn phải tôn trọng những điều kiện và bảo đảm đã cam kết cho caller trong hợp đồng lớp cha/interface.

## 2. Hiểu đúng quan hệ giữa checked, unchecked và throws

### 2.1. Phân cấp các lớp ngoại lệ

~~~text
java.lang.Throwable
├── java.lang.Error
│   └── Các lớp con Error                       ← unchecked
└── java.lang.Exception
    ├── java.io.IOException                     ← checked
    │   └── java.io.FileNotFoundException       ← checked
    └── java.lang.RuntimeException              ← unchecked
        ├── java.lang.IllegalArgumentException
        ├── java.lang.IllegalStateException
        ├── java.lang.NullPointerException
        └── java.io.UncheckedIOException
~~~

*Ghi chú:* Sơ đồ chỉ thể hiện một phần phân cấp Java chuẩn, không phải liệt kê mọi lớp con.

**Checked exceptions** thường là các lớp con của `Exception` nhưng không thuộc nhánh `RuntimeException`. Compiler yêu cầu các checked exception có khả năng thoát ra từ một phương thức phải được **bắt hoặc khai báo** đúng điều kiện của ngôn ngữ.

**Unchecked exceptions** gồm `RuntimeException` và các lớp con, cùng `Error` và các lớp con. Java **không yêu cầu** khai báo `throws` hoặc bắt những ngoại lệ này để mã biên dịch.

Vì vậy:

~~~java
void run() {
    throw new IllegalStateException("bad state");
}
~~~

là phương thức hợp lệ dù không có mệnh đề `throws`. Ngược lại:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
void read() {
    throw new java.io.IOException("read failed");
}
~~~

sẽ bị compiler từ chối vì `IOException` chưa được bắt hoặc khai báo. Dòng minh họa sai không thuộc chương trình runnable trong bài.

### 2.2. throws không phải danh sách mọi lỗi có thể xảy ra

Mệnh đề `throws` có hai vai trò:

1. Đáp ứng quy tắc compile-time đối với **checked exception**.
2. Truyền đạt thông tin API cho người đọc và công cụ khi kiểu ngoại lệ được khai báo.

Tuy nhiên, `throws` **không liệt kê hết mọi unchecked exception có thể xảy ra**. Phương thức có thể ném `NullPointerException`, `IllegalArgumentException` hoặc `IllegalStateException` ngay cả khi chữ ký không đề cập chúng.

Có thể khai báo unchecked exception tường minh:

~~~java
void execute() throws IllegalStateException {
    // ...
}
~~~

nhưng việc khai báo đó **không biến nó thành checked** và cũng không làm caller bắt buộc phải catch. Trong JavaDoc, chú thích `@throws IllegalStateException` thường giúp ghi rõ **trong điều kiện nào** method có thể ném lỗi.

## 3. Quy tắc override về throws: nhìn từ phương thức cha

Theo [Java Language Specification Java 17 mục 8.4.8.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3), khi ghi đè một phương thức, tập **checked exception** được phép khai báo không thể tự do mở rộng so với phương thức cha.

### 3.1. Phương thức cha không khai báo checked exception

~~~java
class Parent {
    void save() {
        System.out.println("saved");
    }
}

class Child extends Parent {
    @Override
    void save() throws IllegalStateException {
        throw new IllegalStateException("storage unavailable");
    }
}
~~~

**Hợp lệ:** `IllegalStateException` là unchecked.

Ví dụ sau **cố ý sai**:

~~~java
class Parent {
    void save() { }
}

class Child extends Parent {
    @Override
    void save() throws java.io.IOException { } // Lỗi biên dịch.
}
~~~

Trong trường hợp thứ hai, `Child.save()` thêm một checked exception mới mà chữ ký ở `Parent.save()` không cho phép. Compiler thường báo đại ý *overridden method does not throw IOException*.

Ngay cả khi thân phương thức con đang rỗng và thực tế chưa ném IOException, riêng **khai báo `throws IOException` không hợp lệ** đã đủ gây lỗi compile-time.

### 3.2. Phương thức cha khai báo một checked exception

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

class Parent {
    void read() throws IOException { }
}

class Child extends Parent {
    @Override
    void read() throws FileNotFoundException {
        throw new FileNotFoundException("missing.txt");
    }
}
~~~

**Hợp lệ:** `FileNotFoundException extends IOException`, nên đây là **thu hẹp** loại checked exception được công khai bởi override.

Các lựa chọn hợp lệ khác là giữ `throws IOException` hoặc **không khai báo checked exception nào**, nếu phần thân xử lý được mọi checked exception liên quan.

Ngược lại:

~~~java
class Parent {
    void read() throws java.io.IOException { }
}

class Child extends Parent {
    @Override
    void read() throws Exception { } // CỐ Ý SAI.
}
~~~

**Không hợp lệ:** `Exception` rộng hơn `IOException` nên không thể dùng nó để mở rộng nghĩa vụ của caller trong override.

### 3.3. Unchecked exception không bị giới hạn theo cùng quy tắc

Giả sử phương thức cha khai báo `IOException`:

~~~java
class Parent {
    void fetch() throws java.io.IOException { }
}

class Child extends Parent {
    @Override
    void fetch() throws java.io.FileNotFoundException,
            IllegalStateException {
        throw new IllegalStateException("temporarily unavailable");
    }
}
~~~

Mã **hợp lệ**:

- `FileNotFoundException` là checked subtype của `IOException`, nên được phép.
- `IllegalStateException` là unchecked, nên không phải chịu giới hạn về kiểu checked của phương thức cha.

Mệnh đề `throws` có thể liệt kê cả checked và unchecked exception, nhưng chúng được kiểm tra khác nhau.

**Tóm tắt nhanh:**

| Chữ ký phương thức cha | Chữ ký override | Hợp lệ? | Lý do |
| --- | --- | --- | --- |
| Không `throws` | Không `throws` | Có | Không thêm nghĩa vụ checked |
| Không `throws` | `throws IllegalStateException` | Có | Unchecked được phép |
| Không `throws` | `throws IOException` | Không | Thêm checked exception |
| `throws IOException` | `throws FileNotFoundException` | Có | Checked exception được thu hẹp |
| `throws IOException` | `throws IOException` | Có | Giữ loại checked đã cho phép |
| `throws IOException` | Không `throws` | Có | Loại bỏ khai báo checked |
| `throws IOException` | `throws Exception` | Không | Mở rộng checked exception |
| `throws IOException` | `throws IllegalStateException` | Có | Không còn checked, thêm unchecked |

Bảng xét các ví dụ đơn giản không dùng generic exception type parameter; trong Java có thêm các quy tắc kỹ thuật về erasure khi override phương thức generic. Đừng suy rộng thành quy tắc cho mọi chữ ký phức tạp mà bỏ qua JLS.

## 4. Có nhất thiết viết throws cho unchecked trong override?

**Không.** Hai cách sau đều hợp lệ:

~~~java
class ServiceA {
    void process() {
        throw new IllegalStateException("not ready");
    }
}

class ServiceB extends ServiceA {
    @Override
    void process() {
        throw new IllegalArgumentException("invalid operation");
    }
}
~~~

Và:

~~~java
class ServiceB extends ServiceA {
    @Override
    void process() throws IllegalArgumentException {
        throw new IllegalArgumentException("invalid operation");
    }
}
~~~

Hai khối code **chỉ minh họa các phương án riêng**, không đặt đồng thời hai khai báo trùng tên `ServiceB` trong cùng một file. Dù có viết `throws IllegalArgumentException`, caller vẫn không bắt buộc catch vì kiểu đó unchecked.

**Vì sao đôi khi vẫn khai báo?** Nó có thể giúp người đọc nhận ra điều kiện lỗi được dự kiến trong hợp đồng. Nhưng cách trình bày tốt hơn thường là JavaDoc mô tả **điều kiện phát sinh**, vì tên loại ngoại lệ một mình không nói rõ cách sử dụng API:

~~~java
/**
 * @throws IllegalArgumentException if the input is blank
 * @throws IllegalStateException if the service is unavailable
 */
@Override
public String execute(String input) {
    // ...
    return input;
}
~~~

Đây là đoạn minh họa thuộc một class có phương thức cha phù hợp, không phải một file độc lập.

Điều này đặc biệt quan trọng với interface mà phương thức chưa có khai báo unchecked exception: triển khai có thể ném những lỗi phù hợp với hợp đồng mà không phải làm mọi caller đổi chữ ký.

## 5. Chương trình Java 17 hoàn chỉnh: override, đa hình và checked/unchecked

Lưu tệp **`OverrideUncheckedDemo.java`**. Ví dụ gồm ba phần:

1. Interface `Job` không khai báo checked exception; subclass `RemoteJob` override và khai báo `throws IllegalStateException`.
2. Interface `FileTask` khai báo `IOException`; implementation có thể thu hẹp thành `FileNotFoundException` hoặc bỏ khai báo checked hoàn toàn.
3. Abstract class `Gateway` không khai báo checked exception; implementation bắt `IOException` từ thao tác kỹ thuật rồi **bọc có cause** thành `UncheckedIOException`.

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.UncheckedIOException;

public class OverrideUncheckedDemo {
    interface Job {
        /** Input must be non-null and non-blank. */
        String execute(String input);
    }

    static class BaseJob implements Job {
        @Override
        public String execute(String input) {
            validate(input);
            return "base:" + input;
        }
    }

    static final class RemoteJob extends BaseJob {
        @Override
        public String execute(String input) throws IllegalStateException {
            validate(input);
            if ("busy".equals(input)) {
                throw new IllegalStateException("service unavailable");
            }
            return "remote:" + input;
        }
    }

    private static void validate(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("input required");
        }
    }

    interface FileTask {
        void open() throws IOException;
    }

    static class MissingFileTask implements FileTask {
        @Override
        public void open() throws FileNotFoundException {
            throw new FileNotFoundException("missing.txt");
        }
    }

    static class WorkingFileTask implements FileTask {
        @Override
        public void open() {
            System.out.println("open=ok");
        }
    }

    static abstract class Gateway {
        abstract String load();
    }

    static final class CheckedToUncheckedGateway extends Gateway {
        @Override
        String load() {
            try {
                return fetch();
            } catch (IOException ex) {
                throw new UncheckedIOException("cannot load data", ex);
            }
        }

        private String fetch() throws IOException {
            throw new IOException("upstream offline");
        }
    }

    public static void main(String[] args) {
        System.out.println("== unchecked through interface ==");
        Job job = new RemoteJob();
        System.out.println("result=" + job.execute("ok"));

        try {
            job.execute("busy");
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }

        try {
            job.execute("");
        } catch (IllegalArgumentException ex) {
            System.out.println("input=" + ex.getMessage());
        }

        System.out.println("== checked narrowing ==");
        FileTask missing = new MissingFileTask();
        try {
            missing.open();
        } catch (IOException ex) {
            System.out.println("checked=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }

        FileTask working = new WorkingFileTask();
        try {
            working.open();
        } catch (IOException ex) {
            System.out.println("unexpected=" + ex.getMessage());
        }

        System.out.println("== checked wrapped as unchecked ==");
        Gateway gateway = new CheckedToUncheckedGateway();
        try {
            gateway.load();
        } catch (UncheckedIOException ex) {
            System.out.println("wrapper=" + ex.getClass().getSimpleName());
            System.out.println("cause=" + ex.getCause().getClass().getSimpleName()
                    + ": " + ex.getCause().getMessage());
        }
    }
}
~~~

### Biên dịch và chạy

Sử dụng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 OverrideUncheckedDemo.java
java OverrideUncheckedDemo
~~~

**Stdout chính xác đã được biên dịch và chạy kiểm chứng:**

~~~text
== unchecked through interface ==
result=remote:ok
caught=IllegalStateException: service unavailable
input=input required
== checked narrowing ==
checked=FileNotFoundException: missing.txt
open=ok
== checked wrapped as unchecked ==
wrapper=UncheckedIOException
cause=IOException: upstream offline
~~~

Chương trình dùng `IOException` được tạo có chủ đích, không phụ thuộc file ngoài hoặc mạng, nên thông điệp lỗi và stdout ổn định. Mỗi ngoại lệ dự kiến được bắt ở đúng boundary của phần minh họa.

## 6. Đọc kỹ chương trình: phần unchecked của Job

### 6.1. Interface không có throws

~~~java
interface Job {
    String execute(String input);
}
~~~

Ở compile time, code dùng biến kiểu `Job` thấy chữ ký **không khai báo checked exception**. Vì vậy caller không buộc viết try/catch nếu chỉ gọi `job.execute("ok")`.

Tuy vậy một implementation vẫn có thể ném unchecked exception. Điều đó không thay đổi kiểu trả về và chữ ký lời gọi ở phía compiler.

### 6.2. Subclass override và khai báo unchecked

~~~java
static final class RemoteJob extends BaseJob {
    @Override
    public String execute(String input) throws IllegalStateException {
        validate(input);
        if ("busy".equals(input)) {
            throw new IllegalStateException("service unavailable");
        }
        return "remote:" + input;
    }
}
~~~

Lớp `RemoteJob` vừa ghi đè implementation của `BaseJob`, vừa thỏa interface `Job`. Từ khóa `@Override` yêu cầu compiler kiểm tra đây thật sự là override, tránh một số lỗi gõ nhầm tên/tham số.

Đoạn `throws IllegalStateException` **không vi phạm** hợp đồng checked exception của cả lớp cha và interface. Nó cũng không đòi hỏi caller khai báo `throws IllegalStateException`.

Nhưng khi `input="busy"`, lời gọi ném `IllegalStateException` và sẽ lan đến caller nếu không được bắt.

### 6.3. Đa hình: kiểu biến khác kiểu object runtime

~~~java
Job job = new RemoteJob();
job.execute("busy");
~~~

Biểu thức gọi dựa trên **kiểu tĩnh `Job`** để compiler kiểm tra chữ ký và checked exceptions. Lúc chạy, Java dùng **dynamic dispatch** để chọn implementation `RemoteJob.execute` trên đối tượng thực tế.

Do đó method được thực thi có thể ném `IllegalStateException`, mặc dù kiểu interface không khai báo `throws`. Runtime không cấm việc này chỉ vì caller nhìn thấy method qua kiểu cha.

Nói cách khác:

- **Kiểu tĩnh/chữ ký**: quyết định các nghĩa vụ compile-time về checked exception.
- **Implementation runtime**: quyết định mã nào chạy và exception thực tế được ném.
- **Catch**: nếu có, chọn handler phù hợp theo kiểu runtime của exception.

Đây là lý do các giao diện callback và framework có thể để unchecked exception lan xuyên qua nhiều tầng không khai báo `throws`.

### 6.4. Unchecked exception khác nhau vẫn có thể biểu diễn hai lỗi khác nhau

Trong `RemoteJob`, `validate()` có thể ném `IllegalArgumentException` khi input null hoặc blank. Khi input là `busy`, implementation ném `IllegalStateException`.

Cả hai đều unchecked, nhưng ý nghĩa khác:

- `IllegalArgumentException`: tham số không đáp ứng tiền điều kiện của API.
- `IllegalStateException`: đối tượng/dịch vụ không ở trạng thái cho phép hoàn tất thao tác.

Caller có thể bắt riêng từng kiểu khi thực sự có cách khắc phục phù hợp. Không nên coi mọi `RuntimeException` là lỗi nhập liệu để “bắt cho hết”.

## 7. Đọc kỹ phần checked narrowing

Trong chương trình, interface định nghĩa:

~~~java
interface FileTask {
    void open() throws IOException;
}
~~~

Implementation thứ nhất:

~~~java
class MissingFileTask implements FileTask {
    @Override
    public void open() throws FileNotFoundException {
        throw new FileNotFoundException("missing.txt");
    }
}
~~~

Đây là **thu hẹp checked exception hợp lệ**. Caller giữ reference kiểu interface:

~~~java
FileTask missing = new MissingFileTask();
try {
    missing.open();
} catch (IOException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
~~~

Nó phải xử lý hoặc khai báo `IOException` theo **kiểu tĩnh `FileTask`**, dù implementation runtime ném subtype `FileNotFoundException`.

Implementation thứ hai:

~~~java
class WorkingFileTask implements FileTask {
    @Override
    public void open() {
        System.out.println("open=ok");
    }
}
~~~

được phép **bỏ hẳn khai báo checked exception** trong override. Nhưng trong chương trình chính:

~~~java
FileTask working = new WorkingFileTask();
try {
    working.open();
} catch (IOException ex) {
    System.out.println("unexpected=" + ex.getMessage());
}
~~~

catch `IOException` vẫn hợp lệ và hợp lý xét từ **chữ ký kiểu interface**.

Nếu thay kiểu biến thành đúng `WorkingFileTask` thì compiler biết chính implementation đó không khai báo checked IOException. Viết một catch `IOException` trực tiếp quanh lời gọi vốn không thể ném checked IOException có thể bị báo lỗi *exception is never thrown in body of corresponding try statement*:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
WorkingFileTask working = new WorkingFileTask();
try {
    working.open();
} catch (IOException ex) {
    System.out.println("unreachable for this static call");
}
~~~

Sự khác biệt ở đây là **kiểu tĩnh của biểu thức gọi**, không phải Java “phán đoán trước” kết quả thực thi của implementation.

## 8. Khi override cần gọi mã ném checked exception nhưng cha không cho phép

Một implementation có thể phải gọi API I/O có khai báo `throws IOException`, trong khi phương thức cha/interface **không cho phép thêm checked exception**. Có hai hướng chính:

1. **Xử lý và phục hồi tại chỗ** nếu có cách hợp lệ.
2. **Chuyển sang unchecked exception có ý nghĩa, giữ nguyên cause**, nếu lỗi cần được truyền tới tầng khác và hợp đồng phương thức không cho checked exception thoát ra.

Ví dụ trong chương trình chính:

~~~java
static final class CheckedToUncheckedGateway extends Gateway {
    @Override
    String load() {
        try {
            return fetch();
        } catch (IOException ex) {
            throw new UncheckedIOException("cannot load data", ex);
        }
    }

    private String fetch() throws IOException {
        throw new IOException("upstream offline");
    }
}
~~~

`Gateway.load()` không khai báo checked exception. `CheckedToUncheckedGateway.load()` vẫn override hợp lệ vì nó **bắt** IOException trong thân method, rồi ném `UncheckedIOException`.

`UncheckedIOException` là lớp chuẩn được cung cấp từ Java 8, kế thừa `RuntimeException` và thiết kế để mang nguyên nhân là `IOException`. Đoạn:

~~~java
throw new UncheckedIOException("cannot load data", ex);
~~~

giữ thông tin nguồn qua `getCause()`; nó **không xóa lỗi gốc** để thay bằng một message thiếu ngữ cảnh.

**Không phải mọi checked exception đều nên gói thành `UncheckedIOException`**. Lớp này chuyên cho `IOException`. Với loại checked khác, chọn một unchecked exception có ý nghĩa với hợp đồng API, ví dụ `IllegalStateException("context", cause)` hoặc custom runtime exception phù hợp.

**Không dùng việc wrap để né thiết kế:** nếu caller bắt buộc phải giải quyết một lỗi nghiệp vụ dự kiến, chỉ bọc thành unchecked để compiler im lặng có thể khiến caller quên xử lý. Phải xác định rõ loại lỗi có phục hồi được hay không trước khi quyết định.

## 9. Có thể ném unchecked exception mới, nhưng phải giữ hợp đồng hành vi

Ở mức ngôn ngữ, subclass được phép khai báo/ném unchecked exception mới. Ở mức thiết kế, **subclass vẫn phải có khả năng thay thế superclass/interface trong những bối cảnh hợp lệ** (*substitutability*).

Ví dụ API:

~~~java
class Formatter {
    /** Chấp nhận mọi String khác null, kể cả String dài 1 ký tự. */
    String format(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value required");
        }
        return "ok:" + value;
    }
}
~~~

Một override không nên tự ý nâng điều kiện tối thiểu thành “phải có ít nhất 3 ký tự”:

~~~java
class StrictFormatter extends Formatter {
    @Override
    String format(String value) {
        if (value.length() < 3) {
            throw new IllegalArgumentException("too short");
        }
        return super.format(value);
    }
}
~~~

Hai class trên là **đoạn minh họa**, chưa có `main`; chúng có thể biên dịch nhưng override có **vấn đề về hợp đồng**:

- Theo hợp đồng của `Formatter`, giá trị `"A"` là input hợp lệ.
- Với `StrictFormatter`, giá trị `"A"` lại gây unchecked `IllegalArgumentException`.
- Caller dùng reference kiểu `Formatter` có thể bất ngờ thất bại với một input trước đó được bảo đảm hợp lệ.
- Override còn thiếu kiểm tra null nhất quán: với null, biểu thức `value.length()` gây NPE thay vì cùng IllegalArgumentException như parent.

**Compiler vẫn chấp nhận**, vì đây không phải lỗi về quy tắc checked exception hoặc chữ ký override. Nhưng thiết kế có thể vi phạm hành vi mà API đã cam kết.

Giải pháp:

- Không **tăng tiền điều kiện** đối với những input mà hợp đồng lớp cha đã hứa chấp nhận.
- Không **giảm hậu điều kiện** hoặc phá invariant mà caller được quyền dựa vào.
- Ghi rõ các unchecked exception **hợp lệ** theo API (ví dụ input null, trạng thái service không sẵn sàng).
- Với biến thể thực sự có hợp đồng khác, xem xét **API/method/type riêng**, thay vì ép override làm hành vi khó đoán.

Đây là tinh thần áp dụng **Liskov Substitution Principle**, dù JLS chỉ cưỡng chế một phần các ràng buộc đó.

## 10. Hợp đồng ngoại lệ của interface cần mô tả hành vi kỳ vọng

Một interface có thể không khai báo checked exception nhưng vẫn cần JavaDoc mô tả lỗi unchecked:

~~~java
interface Job {
    /**
     * Thực hiện tác vụ với chuỗi đầu vào hợp lệ.
     *
     * @param input chuỗi khác null và không được blank
     * @return kết quả xử lý
     * @throws IllegalArgumentException nếu input không hợp lệ
     * @throws IllegalStateException nếu dịch vụ chưa sẵn sàng
     */
    String execute(String input);
}
~~~

Đây là một interface hợp lệ để minh họa hợp đồng. Một implementation nên tuân những điều kiện đã cam kết, dù nó có khai báo `throws IllegalStateException` trong mã hay không.

Khi viết override, các trường hợp sau cần xem xét kỹ:

| Hành vi override | Compiler có cho phép? | Tương thích hợp đồng? |
| --- | --- | --- |
| Ném `IllegalArgumentException` khi input null và contract cấm null | Có | Thường có |
| Ném `IllegalStateException` khi service chưa sẵn sàng như contract mô tả | Có | Thường có |
| Ném `IllegalArgumentException` với input mà contract đã bảo đảm hợp lệ | Có | Có thể vi phạm |
| Ném unchecked từ bug nội bộ chưa được xử lý | Có thể biên dịch | Không nên coi là kết quả nghiệp vụ được bảo đảm |
| Thêm `throws IOException` vào override của method không có checked throws | Không | Không có kết quả runtime vì không biên dịch |
| Bắt `IOException` rồi bọc thành `UncheckedIOException` có cause | Có | Phụ thuộc hợp đồng và chính sách phục hồi |

Không cần liệt kê mọi NullPointerException có thể do bug vào JavaDoc; nên ưu tiên điều kiện lỗi được **dự kiến và có ý nghĩa đối với caller**.

## 11. Thứ tự catch khi xử lý unchecked exception

Một lệnh gọi qua biến cha vẫn có thể ném các runtime subtype khác nhau. Nếu chọn bắt chúng, Java yêu cầu đặt catch **cụ thể trước tổng quát**:

~~~java
try {
    job.execute(input);
} catch (IllegalArgumentException ex) {
    handleInvalidInput(ex);
} catch (IllegalStateException ex) {
    handleUnavailable(ex);
} catch (RuntimeException ex) {
    reportUnexpected(ex);
}
~~~

Đây là cấu trúc minh họa với các hàm handler cần định nghĩa. `IllegalArgumentException` và `IllegalStateException` là hai subtype ngang hàng, không cần thứ tự kế thừa giữa chúng; nhưng cả hai phải đứng trước `RuntimeException` nếu xuất hiện ở cùng chuỗi catch.

Viết ngược:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
try {
    job.execute(input);
} catch (RuntimeException ex) {
    reportUnexpected(ex);
} catch (IllegalStateException ex) {
    handleUnavailable(ex);
}
~~~

làm catch thứ hai bị che vì `RuntimeException` đã bắt mọi `IllegalStateException`.

**Không nên bắt `RuntimeException` ở mọi tầng rồi cho chạy tiếp**. Bắt rộng đôi khi phù hợp ở ranh giới tác vụ/web request để log và chuyển thành lỗi hệ thống, nhưng cần chính sách rõ để tránh che bug.

## 12. Checked exception có thể vẫn đến từ reference kiểu cha

Điều này là khác biệt dễ nhầm giữa Java compiler và runtime:

~~~java
interface ReaderTask {
    String read() throws IOException;
}

class ConstantReader implements ReaderTask {
    @Override
    public String read() {
        return "fixed data";
    }
}
~~~

Đây là khai báo minh họa, cần import `IOException`.

- Biến kiểu `ReaderTask` khi gọi `read()` vẫn có hợp đồng compile-time `throws IOException`.
- Biến kiểu `ConstantReader` gọi chính override không có `throws IOException`, nên không phải khai báo checked IOException chỉ vì interface có khai báo.
- Nếu caller gặp một implementation khác ném `IOException` hợp lệ, việc bắt/xử lý exception sẽ dựa trên đối tượng thực tế tại runtime.

Như vậy **override được phép thu hẹp checked throws** và **unchecked có thể phát sinh ngoài danh sách checked**. Hai quy tắc không mâu thuẫn nhau.

## 13. Khi một class triển khai nhiều interface có throws khác nhau

Giả sử hai interface có method trùng chữ ký:

~~~java
interface LocalAction {
    void execute() throws java.io.IOException;
}

interface DatabaseAction {
    void execute() throws java.sql.SQLException;
}
~~~

Một class triển khai cả hai phải có implementation override hợp lệ đối với **cả hai hợp đồng**. Chẳng hạn:

~~~java
class UnifiedAction implements LocalAction, DatabaseAction {
    @Override
    public void execute() throws IllegalStateException {
        throw new IllegalStateException("not ready");
    }
}
~~~

Đoạn này **hợp lệ**: implementation không khai báo checked exception nào và chỉ khai báo unchecked `IllegalStateException`. Vì một loại checked exception chung phải tương thích với cả hai phương thức được kế thừa, không thể tùy ý thêm `throws IOException` hoặc `throws SQLException` vào override chung khi chỉ một phía khai báo loại tương ứng.

Đây là trường hợp mở rộng để thấy vì sao **không có checked throws** thường dễ triển khai nhiều interface có hợp đồng khác nhau; nhưng unchecked exception vẫn cần tôn trọng các bảo đảm hành vi của **từng** interface.

Nếu một class bị buộc thực hiện thao tác I/O ném checked exception, nó vẫn có thể xử lý tại chỗ hoặc bọc exception sau khi cân nhắc thiết kế.

## 14. Ngoại lệ Error có phải cũng được phép trong override?

Về định nghĩa ngôn ngữ, `Error` và các lớp con cũng là **unchecked exception**. Compiler không yêu cầu khai báo `throws Error` và không giới hạn chúng theo quy tắc checked throws của override.

Tuy nhiên, **không nên sử dụng `Error` để đại diện lỗi nghiệp vụ** hoặc dùng nó như cách né compiler. Các lớp `Error` thường dành cho tình huống nghiêm trọng như lỗi liên kết class hoặc lỗi về tài nguyên ở mức JVM; ứng dụng bình thường không nên thiết kế luồng phục hồi chung quanh chúng.

Nếu cần biểu diễn một điều kiện lỗi ứng dụng unchecked, thường dùng subtype của `RuntimeException` với thông điệp và cause thích hợp.

## 15. Phân biệt các khái niệm dễ lẫn khi ghi đè

### 15.1. Override khác overload

~~~java
class Parent {
    void work(String value) { }
}

class Child extends Parent {
    @Override
    void work(String value) throws IllegalStateException { }

    void work(int value) throws java.io.IOException { }
}
~~~

Đây là các class minh họa **có thể biên dịch**, trong đó:

- `work(String)` ở Child **override** phương thức của Parent, nên áp dụng giới hạn checked throws của phương thức cha.
- `work(int)` ở Child là một **overload khác chữ ký**, không override Parent.work(String). Nó có thể khai báo `IOException` vì không bị ràng buộc bởi throws của Parent.work(String), nhưng caller phải xử lý checked IOException nếu gọi overload này.

`@Override` giúp kiểm tra nhầm lẫn. Nếu gắn `@Override` vào `work(int)` trong ví dụ này, compiler sẽ báo lỗi vì method đó không override method nào tương ứng.

### 15.2. Không phải mọi phương thức trùng tên đều là override

- Phương thức `static` cùng chữ ký ở lớp con là **method hiding**, không phải override động.
- Phương thức `private` ở lớp cha không được kế thừa như một method override.
- Phương thức `final` không được phép override.
- Constructor không được override.

Các trường hợp này tuân những quy tắc ngôn ngữ khác nhau; đừng áp dụng máy móc lập luận về overriding exceptions cho mọi method cùng tên.

### 15.3. Chữ ký throws không quyết định catch runtime

Một phương thức có thể khai báo `throws IllegalStateException` nhưng thực tế ném `IllegalArgumentException` hoặc không ném gì cả. Catch phù hợp tại runtime dựa trên **kiểu đối tượng Throwable thực sự được ném**, không đơn giản là tên kiểu trong mệnh đề `throws`.

Vì thế `throws RuntimeException` không phải một "cửa chắn" đảm bảo chỉ RuntimeException mới có thể phát sinh trong mọi hoàn cảnh; các lỗi `Error` cũng có thể xảy ra, và checked exception chỉ có thể lan theo quy tắc hợp lệ của ngôn ngữ hoặc cơ chế ngoài thông thường.

## 16. Cách review một override có exception

Khi thấy một class con ghi đè method, kiểm tra theo thứ tự:

1. **Xác định đúng method cha/interface** mà chữ ký đang override; có `@Override` không?
2. **Ghi lại checked throws của method cha**, phân biệt với unchecked throws.
3. **Phân loại từng loại trong throws của override:** checked hay unchecked?
4. **Nếu checked**, kiểm tra nó có hợp lệ theo hợp đồng cha không; không thêm checked type rộng hơn hoặc mới.
5. **Nếu unchecked**, nhớ compile-time cho phép nhưng phải đọc JavaDoc/tiền điều kiện/hậu điều kiện để xác định tính tương thích hành vi.
6. **Đọc phần thân:** có gọi API checked exception không? Nếu có, đã catch/declare hợp lệ chưa? Có bọc thành unchecked và giữ cause không?
7. **Xem kiểu tĩnh của caller:** gọi qua interface hoặc qua implementation dẫn đến phân tích checked exception khác nhau.
8. **Kiểm thử bằng runtime polymorphism:** biến cha trỏ đến instance con, có bắt đúng ngoại lệ và giữ được hành vi cam kết không?
9. **Kiểm tra ranh giới catch:** không catch quá rộng và bỏ qua lỗi lập trình; ghi log exception object thay vì chỉ message.
10. **Kiểm tra chính sách chuyển đổi lỗi:** không gói một checked exception nghiệp vụ cần phục hồi thành RuntimeException chỉ để né `throws`.

Khi mọi bước đã hợp lệ, một override có thể khai báo thêm unchecked exception về mặt ngôn ngữ và vẫn duy trì một hợp đồng API dễ sử dụng.

## 17. Những hiểu nhầm thường gặp

- **“Method cha không có throws nên method con không thể ném bất cứ exception nào.”** Sai: unchecked exception vẫn có thể được ném.
- **“Method con có throws RuntimeException thì caller buộc phải catch.”** Sai: unchecked không tạo nghĩa vụ compile-time.
- **“Chỉ RuntimeException mới unchecked.”** Chưa đủ: `Error` và các lớp con cũng unchecked.
- **“Method con được mở rộng checked throws như overload bình thường.”** Sai: override có ràng buộc checked throws theo method cha.
- **“Base throws IOException thì child có thể throws Exception.”** Sai: mở rộng checked throws không hợp lệ.
- **“Child throws FileNotFoundException thay IOException là sai.”** Sai: FileNotFoundException là subtype của IOException.
- **“Interface không khai báo exception thì implementation không thể ném IllegalStateException.”** Sai: đó là unchecked exception.
- **“Đặt biến kiểu interface rồi gọi implementation không thay đổi xử lý lỗi.”** Cần phân biệt kiểm tra compile-time qua kiểu tĩnh với dynamic dispatch runtime.
- **“Nếu implementation bỏ throws IOException, caller qua interface không cần xử lý IOException.”** Sai: lời gọi qua kiểu interface vẫn theo checked signature của interface.
- **“Bọc IOException thành UncheckedIOException là mất nguyên nhân gốc.”** Sai nếu dùng constructor nhận cause; hãy kiểm tra `getCause()`.
- **“Bọc checked thành unchecked luôn là quyết định tốt.”** Sai: phụ thuộc hợp đồng và khả năng phục hồi của caller.
- **“Compiler cho phép một unchecked exception mới nên luôn tương thích LSP.”** Sai: override có thể tăng tiền điều kiện hoặc phá bảo đảm hành vi.
- **“Catch RuntimeException trước IllegalStateException vẫn ổn.”** Sai: handler cụ thể bị che, không biên dịch.
- **“throws IllegalStateException có nghĩa method chỉ ném loại đó.”** Sai: mệnh đề throws không mô tả hết mọi lỗi runtime.
- **“Đổi input contract trong subclass cũng chỉ là chi tiết implementation.”** Sai nếu khiến caller hợp lệ của superclass không còn hoạt động đúng.
- **“@Override ảnh hưởng exception runtime.”** Không: annotation này giúp compiler xác thực ghi đè; cơ chế throw/catch runtime không đổi.

## 18. Câu hỏi tự luyện

**Câu 1.** Interface `Action { void run(); }`; implementation override khai báo `throws IllegalArgumentException`. Có biên dịch được không?

*Đáp án:* Có. IllegalArgumentException là unchecked. Caller không buộc catch do khai báo đó.

**Câu 2.** Đổi khai báo của implementation sang `throws IOException` thì sao?

*Đáp án:* Không biên dịch nếu interface/base không cho phép checked IOException ở method bị override.

**Câu 3.** Base method khai báo `throws IOException`. Child override khai báo `throws FileNotFoundException` có hợp lệ?

*Đáp án:* Có. FileNotFoundException là checked subtype của IOException, tức thu hẹp throws.

**Câu 4.** Base `throws IOException`, child `throws Exception` có hợp lệ?

*Đáp án:* Không. Exception là checked supertype rộng hơn IOException.

**Câu 5.** Vì sao biến `FileTask task = new WorkingFileTask();` vẫn cần handle IOException khi gọi `task.open()`?

*Đáp án:* Compiler kiểm tra lời gọi qua kiểu tĩnh FileTask, có khai báo throws IOException, dù implementation WorkingFileTask không khai báo.

**Câu 6.** Nếu override muốn gọi `Files.readString(path)` trong method cha không khai báo checked throws, phải làm gì?

*Đáp án:* Catch/handle IOException bên trong override, hoặc chuyển đổi thành unchecked phù hợp với hợp đồng và giữ cause. Không được chỉ thêm `throws IOException` trái quy tắc override.

**Câu 7.** Vì sao thêm unchecked IllegalArgumentException khi input `"A"` vốn được base cho phép lại có vấn đề?

*Đáp án:* Compiler cho phép nhưng hành vi override có thể làm mạnh thêm tiền điều kiện, vi phạm khả năng thay thế và hợp đồng caller.

**Câu 8.** Có cần ghi `throws IllegalStateException` để ném IllegalStateException không?

*Đáp án:* Không. Đó là khai báo tùy chọn, không làm exception trở thành checked.

**Câu 9.** Một class triển khai hai interface cùng method `execute()`, interface thứ nhất `throws IOException`, interface thứ hai `throws SQLException`, implementation không throws checked nhưng có `throws IllegalStateException`. Có hợp lệ?

*Đáp án:* Có. Unchecked exception không bị ràng buộc bởi checked throws của hai interface.

**Câu 10.** Nếu catch RuntimeException rồi bỏ qua exception để tiếp tục nghiệp vụ, có luôn an toàn?

*Đáp án:* Không. Nó có thể che bug hoặc một lỗi trạng thái nghiêm trọng. Catch rộng chỉ nên có ở ranh giới với chính sách xử lý rõ ràng.

## 19. Tài liệu chuẩn

- [JLS Java SE 17 mục 8.4.8.3 – Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): giới hạn checked exception khi method override.
- [JLS Java SE 17 mục 9.4.1.3 – Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3): điều kiện override/implement interface methods.
- [JLS Java SE 17 mục 8.4.6 – Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): ý nghĩa mệnh đề throws của method.
- [JLS Java SE 17 chương 11 – Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): phân loại checked/unchecked và cơ chế kiểm tra exception.
- [Java SE 17 API – RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): nhánh unchecked cho lỗi thời gian chạy.
- [Java SE 17 API – UncheckedIOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html): wrapper unchecked giữ nguyên nhân IOException.
- [Java SE 17 API – Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): message, cause và stack trace.

**Ghi nhớ:** **Override được phép thêm khai báo hoặc ném unchecked exception**, ngay cả khi method cha/interface không có mệnh đề `throws`. **Checked exception phải tuân hợp đồng phương thức cha**, không được tự ý thêm hoặc mở rộng. Nhưng một override được compiler chấp nhận chưa chắc đúng thiết kế: hãy giữ tiền điều kiện/hậu điều kiện, tài liệu hóa lỗi dự kiến, bảo toàn cause khi wrap và xét cách caller dùng method qua kiểu cha.