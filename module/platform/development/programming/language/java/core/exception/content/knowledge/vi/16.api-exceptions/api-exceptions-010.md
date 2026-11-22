# UndeclaredThrowableException khi dùng dynamic proxy trong Java

> **Java Core – Exception** · Nhóm: **Ngoại lệ API** · Trọng tâm: vì sao một `InvocationHandler` có thể ném checked exception nhưng lời gọi qua JDK dynamic proxy lại nhận `UndeclaredThrowableException`; cách giữ nguyên cause, mở lớp `InvocationTargetException` khi ủy quyền bằng reflection, và thiết kế hợp đồng `throws` đúng. Ví dụ tương thích **Java 17+**.

## 1. Hiện tượng: method không khai báo IOException nhưng proxy lại gặp lỗi I/O

Giả sử một interface công khai có phương thức:

~~~java
interface Service {
    String find();
}
~~~

Đoạn trên là khai báo interface độc lập hợp lệ. Vì phương thức `find()` **không khai báo checked exception**, caller bình thường có thể gọi mà không phải catch/declare `IOException`.

Nhưng một JDK dynamic proxy được tạo cho interface ấy có thể được điều khiển bởi `InvocationHandler`, và handler lại ném:

~~~java
throw new java.io.IOException("remote service offline");
~~~

Dòng này là ví dụ bên trong một handler hoặc method được phép ném IOException. Khi caller gọi `proxy.find()`, nó thường **không nhận trực tiếp IOException**. Theo cơ chế JDK dynamic proxy, một checked exception từ `InvocationHandler.invoke(...)` **không phù hợp với throws clause của method được gọi** sẽ bị bọc trong:

~~~text
java.lang.reflect.UndeclaredThrowableException
    └── java.io.IOException: remote service offline
~~~

**Tên đầy đủ:** `java.lang.reflect.UndeclaredThrowableException`, thường viết tắt **UTE**.

UTE kế thừa `RuntimeException`, tức **unchecked exception**. Exception gốc có thể truy xuất từ:

~~~java
Throwable original = ex.getUndeclaredThrowable();
// Hoặc, theo cơ chế exception chaining phổ biến:
Throwable cause = ex.getCause();
~~~

Đây là đoạn minh họa đặt trong handler có biến `ex` kiểu UndeclaredThrowableException. API UTE Java 17 nêu rõ `getUndeclaredThrowable()` và `getCause()` thể hiện cùng exception đã được bọc theo cơ chế chaining của lớp này.

**Điểm cần nhớ:** UTE không nhất thiết chỉ ra một bug trong chính class proxy. Nó thường báo rằng **exception thoát khỏi invocation handler không khớp hợp đồng checked exception của interface mà proxy đang triển khai**.

## 2. Ba thành phần cần phân biệt

### 2.1. Interface: hợp đồng mà caller thấy

~~~java
interface Repository {
    String load() throws java.io.IOException;
}
~~~

Hợp đồng `load()` cho phép caller nhận `IOException` (hoặc subtype checked thích hợp). Nếu implementation động không thể hoàn thành thao tác, nó có thể truyền `IOException` gốc theo con đường được cho phép.

Trái lại:

~~~java
interface Service {
    String load();
}
~~~

Hợp đồng của `Service.load()` **không cho checked IOException thoát ra ở compile time**. Người dùng interface không bắt buộc (và trong một số cách viết còn không thể hợp lệ) đặt `catch (IOException)` cho lời gọi đơn lẻ này nếu không có nguồn checked IOException nào khác trong try.

### 2.2. InvocationHandler: bộ định tuyến lời gọi động

JDK cung cấp interface:

~~~java
@FunctionalInterface
public interface InvocationHandler {
    Object invoke(Object proxy, Method method, Object[] args)
            throws Throwable;
}
~~~

Đây là **chữ ký rút gọn mang tính minh họa**: `Method` là `java.lang.reflect.Method`; trong Java SE 17, `InvocationHandler` có một abstract method `invoke` với nội dung tương ứng. Cách khai báo ở trên không nhằm tạo mới class/interface trùng tên trong package chuẩn.

Ba tham số:

- `proxy`: đối tượng proxy nhận lời gọi.
- `method`: metadata `Method` tương ứng lời gọi interface.
- `args`: các đối số được truyền, hoặc `null` khi không có đối số.

Kiểu trả về `Object` cho phép proxy chuyển/ép giá trị về kiểu trả về của method tương ứng. Nếu method interface trả primitive mà handler trả null hoặc kiểu wrapper không tương thích, proxy có thể báo NPE hoặc ClassCastException; đó là **cơ chế kết quả**, khác với UTE.

Điểm dễ gây hiểu nhầm nhất là chữ ký:

~~~java
Object invoke(...) throws Throwable
~~~

Nó cho phép **mã của handler** viết `throw new IOException(...)`, `throw new SQLException(...)` hay ném một checked exception khác về mặt kiểm tra compiler tại chính handler. **Nhưng chữ ký rộng của handler không hề mở rộng mệnh đề `throws` của các method interface do proxy cung cấp cho caller.**

### 2.3. Proxy object: nơi kiểm tra hợp đồng thực tế

Một proxy được tạo bằng:

~~~java
Service service = (Service) Proxy.newProxyInstance(
        Service.class.getClassLoader(),
        new Class<?>[] { Service.class },
        handler);
~~~

Đây là đoạn minh họa: cần import `java.lang.reflect.Proxy` và định nghĩa `Service`, `handler`. Đối tượng sinh ra triển khai một hoặc nhiều **interface được chỉ định**, và phần lớn lời gọi method interface được chuyển tới handler.

Khi handler ném Throwable, proxy tuân quy tắc:

1. Nếu là **RuntimeException** hoặc subtype → truyền ra trực tiếp, không tự bọc UTE vì unchecked.
2. Nếu là **Error** hoặc subtype → truyền ra trực tiếp, không tự bọc UTE.
3. Nếu là **checked Throwable** có kiểu tương thích với mệnh đề `throws` của method proxy → được phép truyền trực tiếp.
4. Nếu là **checked Throwable không tương thích** → proxy tạo/ném một `UndeclaredThrowableException` chứa Throwable ấy.

Những điểm trên là **hợp đồng JDK Proxy/InvocationHandler**, không phải quy tắc mọi loại proxy của mọi framework bên ngoài đều cài đặt y hệt.

## 3. Sơ đồ cơ chế dẫn tới UTE

~~~text
Caller
  |
  | gọi service.find()
  v
JDK dynamic proxy (method do interface khai báo)
  |
  | chuyển tới InvocationHandler.invoke(...)
  v
Handler thực hiện logic
  |
  +-- trả giá trị bình thường --> proxy trả về caller
  |
  +-- ném RuntimeException/Error ---------> truyền ra caller
  |
  +-- ném checked tương thích throws ------> truyền ra caller
  |
  +-- ném checked không tương thích throws
          |
          v
    UndeclaredThrowableException
          |
          +-- getUndeclaredThrowable() --> Throwable gốc
          +-- getCause() --------------> Throwable gốc
          |
          v
       caller nhận UTE
~~~

Ví dụ `interface Service { String find(); }` không có throws. Nếu handler ném `IOException` thì caller nhận UTE. Nếu đổi hợp đồng thành `String find() throws IOException;`, cùng loại IOException có thể đi ra trực tiếp.

**Giới hạn:** Proxy được phép bọc checked exception **do handler ném không khai báo tương thích**. Nếu một đoạn code thông thường tự `throw new UndeclaredThrowableException(...)` thì bạn cũng sẽ gặp class UTE, nhưng đó không phải bằng chứng chắc chắn lỗi đến từ proxy. Hãy xem stack trace và chain trước khi kết luận.

## 4. Chương trình Java 17 hoàn chỉnh: các loại exception qua proxy

Lưu toàn bộ mã thành **`UndeclaredThrowableProxyDemo.java`**. Chương trình trình diễn:

- IOException **được method interface khai báo** → truyền trực tiếp.
- IOException **không được method interface khai báo** → UTE.
- IllegalStateException (**unchecked**) → truyền trực tiếp.
- AssertionError (**Error**) → truyền trực tiếp.
- Handler dùng `Method.invoke` nhưng **quên mở InvocationTargetException** → UTE bọc InvocationTargetException.
- Handler biết mở `InvocationTargetException` → IOException gốc lại đi ra trực tiếp, đúng hợp đồng interface.

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;

public class UndeclaredThrowableProxyDemo {
    public interface Service {
        String declared() throws IOException;
        String undeclared();
        String unchecked();
        String serious();
    }

    private static Service proxyFor(InvocationHandler handler) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] {Service.class},
                handler);
    }

    private static void show(String label, Runnable call) {
        System.out.println("== " + label + " ==");
        try {
            call.run();
        } catch (UndeclaredThrowableException ex) {
            Throwable root = ex.getUndeclaredThrowable();
            System.out.println("outer=" + ex.getClass().getSimpleName());
            System.out.println("wrapped=" + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
            System.out.println("same-cause=" + (ex.getCause() == root));
        } catch (RuntimeException ex) {
            System.out.println("runtime=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        } catch (AssertionError ex) {
            System.out.println("error=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }
    }

    public interface Repository {
        String load() throws IOException;
    }

    public static final class RepositoryImpl implements Repository {
        @Override
        public String load() throws IOException {
            throw new IOException("disk offline");
        }
    }

    private static Repository reflected(Repository target, boolean unwrap) {
        InvocationHandler handler = (Object proxy, Method method, Object[] args) -> {
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException ex) {
                if (unwrap) {
                    throw ex.getCause();
                }
                throw ex;
            }
        };
        return (Repository) Proxy.newProxyInstance(
                Repository.class.getClassLoader(),
                new Class<?>[] {Repository.class},
                handler);
    }

    public static void main(String[] args) {
        Service service = proxyFor((proxy, method, arguments) -> {
            switch (method.getName()) {
                case "declared":
                    throw new IOException("declared checked");
                case "undeclared":
                    throw new IOException("not in interface");
                case "unchecked":
                    throw new IllegalStateException("business state");
                case "serious":
                    throw new AssertionError("fatal condition");
                default:
                    throw new IllegalArgumentException("unknown method");
            }
        });

        System.out.println("== declared checked ==");
        try {
            service.declared();
        } catch (IOException ex) {
            System.out.println("checked=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }

        show("undeclared checked", service::undeclared);
        show("unchecked", service::unchecked);
        show("error", service::serious);

        Repository target = new RepositoryImpl();
        System.out.println("== reflection without unwrap ==");
        try {
            reflected(target, false).load();
        } catch (UndeclaredThrowableException ex) {
            Throwable wrapper = ex.getUndeclaredThrowable();
            System.out.println("outer=" + ex.getClass().getSimpleName());
            System.out.println("wrapped=" + wrapper.getClass().getSimpleName());
            System.out.println("target=" + ((InvocationTargetException) wrapper)
                    .getTargetException().getMessage());
        } catch (IOException ex) {
            System.out.println("unexpected=" + ex);
        }

        System.out.println("== reflection with unwrap ==");
        try {
            reflected(target, true).load();
        } catch (IOException ex) {
            System.out.println("checked=" + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 UndeclaredThrowableProxyDemo.java
java UndeclaredThrowableProxyDemo
~~~

**Stdout đã được kiểm chứng bằng cách biên dịch và chạy thực tế:**

~~~text
== declared checked ==
checked=IOException: declared checked
== undeclared checked ==
outer=UndeclaredThrowableException
wrapped=IOException: not in interface
same-cause=true
== unchecked ==
runtime=IllegalStateException: business state
== error ==
error=AssertionError: fatal condition
== reflection without unwrap ==
outer=UndeclaredThrowableException
wrapped=InvocationTargetException
target=disk offline
== reflection with unwrap ==
checked=IOException: disk offline
~~~

Chương trình chạy với JDK hỗ trợ Java 17 ở mức `javac --release 17`. Các exception được tạo có chủ ý, không có mạng/tệp bên ngoài, và stdout không phụ thuộc số dòng stack trace.

**Lưu ý về helper `show`:** Nó dùng `Runnable` và method reference để thể hiện các lời gọi **không khai báo checked exception**. Riêng phương thức `service.declared()` được gọi trong `try/catch (IOException)` riêng, bởi chữ ký của nó là checked. Đây cũng là một cách thấy sự khác biệt compile time giữa các phương thức trên cùng interface.

## 5. Phân tích từng nhánh của ví dụ

### 5.1. Declared checked: IOException đi ra trực tiếp

Interface định nghĩa:

~~~java
String declared() throws IOException;
~~~

Handler ném:

~~~java
throw new IOException("declared checked");
~~~

Tại proxy, kiểu thực tế `IOException` phù hợp với `throws IOException`. Vì vậy caller bắt **trực tiếp** `IOException` và in:

~~~text
checked=IOException: declared checked
~~~

Không có UTE ở đây. `InvocationHandler.invoke() throws Throwable` không làm mọi checked exception bị bọc: proxy **chỉ bọc nếu checked type không tương thích với hợp đồng method**.

Subtype cũng được chấp nhận. Ví dụ nếu method công bố `throws IOException`, handler có thể ném `FileNotFoundException`, vốn kế thừa IOException, và proxy sẽ truyền trực tiếp loại lỗi con đó.

### 5.2. Undeclared checked: IOException bị bọc thành UTE

Interface định nghĩa:

~~~java
String undeclared();
~~~

Handler vẫn ném IOException:

~~~java
throw new IOException("not in interface");
~~~

Lời gọi từ caller qua method không có checked throws, nên proxy ném:

~~~text
outer=UndeclaredThrowableException
wrapped=IOException: not in interface
same-cause=true
~~~

Kiểm tra:

~~~java
ex.getUndeclaredThrowable() == ex.getCause()
~~~

là true trong chương trình; exception được bọc chính là IOException do handler đã ném.

**Quan trọng:** IOException gốc không biến mất. UTE là **wrapper**. Khi chẩn đoán, đừng chỉ log `ex.getMessage()` mà phải giữ object Throwable và đọc cause/stack trace.

### 5.3. Unchecked exception đi qua không cần được khai báo

Handler ném:

~~~java
throw new IllegalStateException("business state");
~~~

`IllegalStateException extends RuntimeException`, là unchecked. Proxy truyền ra cùng kiểu lỗi, caller in:

~~~text
runtime=IllegalStateException: business state
~~~

Đây không phải UTE. Quy tắc tương tự áp dụng cho nhiều RuntimeException khác, kể cả `IllegalArgumentException` và `NullPointerException`.

**Không suy rằng mọi unchecked đều an toàn để tiếp tục nghiệp vụ.** Việc proxy cho ngoại lệ đi qua không miễn trừ yêu cầu thiết kế xử lý lỗi, rollback, logging và dừng tác vụ ở boundary thích hợp.

### 5.4. Error cũng không được proxy tự chuyển thành UTE

Handler ném:

~~~java
throw new AssertionError("fatal condition");
~~~

`AssertionError` nằm trong nhánh `Error`, thuộc nhóm unchecked. Output:

~~~text
error=AssertionError: fatal condition
~~~

Ở đây ví dụ **bắt AssertionError chỉ để minh họa** rằng loại Error không bị UTE bọc. Trong ứng dụng thật, đừng catch mọi Error để coi như lỗi nghiệp vụ bình thường; Error thường liên quan tới những tình huống nghiêm trọng hoặc invariant không thể tiếp tục đáng tin cậy.

### 5.5. Catch order cũng áp dụng với UTE

Vì UTE kế thừa `RuntimeException`, nếu cùng chuỗi catch có cả hai thì handler UTE phải đứng trước handler RuntimeException:

~~~java
try {
    service.undeclared();
} catch (UndeclaredThrowableException ex) {
    handleProxyMismatch(ex);
} catch (RuntimeException ex) {
    handleOtherRuntimeFailure(ex);
}
~~~

Đây là đoạn minh họa; các hàm handler cần định nghĩa. Nếu đặt `catch (RuntimeException)` lên trước, handler UTE sau đó bị che và compiler từ chối vì unreachable catch.

Ngược lại, `catch (IOException)` **không thể tự nhận IOException ẩn bên trong UTE**. Catch chọn theo kiểu Throwable **đang thực sự được ném ở tầng hiện tại**. Muốn truy nguyên IOException thì đọc cause và kiểm tra kiểu gốc, hoặc sửa hợp đồng/handler để truyền trực tiếp nếu phù hợp.

## 6. Bẫy lớn nhất: Method.invoke tạo InvocationTargetException

Một dynamic proxy thường được dùng để thêm logging, metrics, retry hoặc kiểm soát truy cập trước/sau khi gọi một object thật.

Cách ủy quyền bằng reflection:

~~~java
InvocationHandler handler = (proxy, method, args) -> method.invoke(target, args);
~~~

Đây là đoạn minh họa, cần biến `target` với method tương ứng.

**Vấn đề:** Khi phương thức **được gọi qua reflection** ném exception, `Method.invoke(...)` dùng một wrapper checked riêng:

~~~text
InvocationTargetException
    └── exception thật do target method ném
~~~

Ví dụ method `Repository.load() throws IOException` của target ném `IOException("disk offline")`. `method.invoke(target, args)` không truyền trực tiếp IOException đó lên handler, mà ném `InvocationTargetException`.

`InvocationTargetException` là checked exception thuộc package `java.lang.reflect` và **không phải subtype của IOException**.

Nếu handler chỉ viết:

~~~java
return method.invoke(target, args);
~~~

thì `InvocationTargetException` có thể thoát khỏi `InvocationHandler.invoke()` (vì handler khai báo `throws Throwable`). Nhưng method interface `Repository.load()` chỉ cho phép checked IOException. Proxy xét **loại checked thực sự thoát khỏi handler**, thấy `InvocationTargetException` không phù hợp, rồi **bọc thêm UTE**:

~~~text
UndeclaredThrowableException
    └── InvocationTargetException
          └── IOException("disk offline")
~~~

Đây chính là hiện tượng **double wrapping** thường gặp trong AOP hoặc framework proxy tự viết.

### 6.1. Phần output chứng minh double wrapping

Trong chương trình đầy đủ, `reflected(target, false)` không unwrap `InvocationTargetException`. Output:

~~~text
== reflection without unwrap ==
outer=UndeclaredThrowableException
wrapped=InvocationTargetException
target=disk offline
~~~

Điểm quan trọng: mặc dù method interface **đã khai báo `throws IOException`**, caller **vẫn nhận UTE** vì đối tượng checked mà handler ném ra là **InvocationTargetException**, chứ không phải IOException ban đầu.

Đây là lý do không thể chỉ nhìn tên exception gốc hoặc chữ ký interface mà kết luận proxy sẽ tự truyền trực tiếp. Cần kiểm tra **lớp wrapper nào thoát khỏi handler**.

### 6.2. Cách sửa: mở InvocationTargetException ngay trong handler

Phương thức trích từ ví dụ:

~~~java
InvocationHandler handler = (proxy, method, args) -> {
    try {
        return method.invoke(target, args);
    } catch (InvocationTargetException ex) {
        throw ex.getCause();
    }
};
~~~

Mã minh họa trong một method có biến `target` hợp lệ, và import `InvocationHandler`, `InvocationTargetException`.

`ex.getCause()` hoặc `ex.getTargetException()` truy xuất Throwable thực sự mà target đã ném. Handler ném lại **exception gốc**:

- Nếu gốc là IOException và interface cho phép IOException → proxy truyền trực tiếp.
- Nếu gốc là RuntimeException/Error → proxy truyền trực tiếp theo nhánh unchecked.
- Nếu gốc là checked exception **không thuộc hợp đồng interface** → proxy **vẫn** bọc UTE. Unwrap không làm cho exception trái hợp đồng trở thành hợp lệ.

Output phần đã sửa:

~~~text
== reflection with unwrap ==
checked=IOException: disk offline
~~~

**Vì sao nên unwrap ở handler thay vì catch UTE tại mọi caller?** Handler là tầng đã tạo ra wrapper reflection. Sửa tại đây bảo toàn đúng hợp đồng public API, tránh buộc mọi caller hiểu chi tiết implementation và làm cho code sử dụng interface đơn giản, rõ ràng.

### 6.3. Các ngoại lệ khác từ Method.invoke

`Method.invoke` có thể ném `IllegalAccessException` nếu truy cập không được phép, `IllegalArgumentException` khi đối số/receiver không phù hợp và các vấn đề reflection khác. Không được bắt tất cả `Exception` rồi tự cho rằng đó đều là “business IOException từ target”.

Nếu vấn đề là **reflection configuration**, có thể phù hợp hơn với một unchecked exception có thông điệp và cause để báo lỗi framework/implementation. Đừng cố biến `IllegalAccessException` thành `IOException` chỉ để vừa với một chữ ký interface khi thực chất hạ tầng proxy cấu hình sai.

## 7. Cách đọc UTE và truy vết nguyên nhân

Khi nhận UTE, bắt đầu bằng:

~~~java
catch (UndeclaredThrowableException ex) {
    Throwable original = ex.getUndeclaredThrowable();
    // Ghi log đầy đủ ex cùng original/cause theo chính sách.
}
~~~

Đây là handler minh họa nằm trong cấu trúc try/catch phù hợp.

Hai API thường dùng:

| API | Giá trị |
| --- | --- |
| `ex.getUndeclaredThrowable()` | Throwable được bọc, theo hợp đồng chuyên biệt của UTE; có thể null với một số constructor |
| `ex.getCause()` | Cause theo cơ chế chaining chung của Throwable; đối với UTE tạo với wrapped exception thì tham chiếu tới cùng Throwable |
| `ex.printStackTrace()` | In UTE, cause và stack trace, giúp thấy các lớp bọc |
| `ex.getSuppressed()` | Các lỗi phụ được gắn vào chính UTE, nếu có; không tự đồng nghĩa lỗi proxy |

Đừng chỉ log:

~~~java
System.err.println(ex.getMessage());
~~~

Message của UTE có thể ít thông tin, hoặc chứa một biểu diễn của lớp wrapped thay vì bối cảnh nghiệp vụ đủ rõ. Hãy log **object exception**, giữ stack trace và cause.

### 7.1. Có nên unwrap mọi loại exception theo vòng lặp?

Khi bạn là **tầng quan sát/diagnostics**, có thể cần đi qua chain UTE → InvocationTargetException → IOException để tìm nguyên nhân.

Nhưng **không tự động ném lại “root cause sâu nhất” ở mọi nơi**: một wrapper có thể biểu thị bối cảnh hay hợp đồng public API quan trọng; bỏ hết lớp bọc có thể khiến caller nhận một checked exception không còn phù hợp với chữ ký. Cần phân biệt:

- **Unwrap khi ủy quyền reflection trong handler** để không rò rỉ wrapper kỹ thuật `InvocationTargetException`.
- **Traverse chain để log/diagnose** khi cần.
- **Translate exception** ở ranh giới API theo hợp đồng, giữ cause thay vì phá vỡ hoặc làm mất thông tin.

### 7.2. Nếu cause null hoặc không đúng loại thì sao?

Java cho phép tạo UTE thủ công bằng constructor nhận Throwable; API nêu `getUndeclaredThrowable()` **có thể trả null**. Vì vậy với code thư viện hoặc UTE không biết nguồn, hãy kiểm tra null trước khi gọi `getClass()`.

Ví dụ an toàn:

~~~java
Throwable cause = ex.getUndeclaredThrowable();
if (cause == null) {
    System.err.println("Undeclared throwable unavailable");
} else {
    System.err.println("Original type: " + cause.getClass().getName());
}
~~~

Đây là đoạn minh họa, biến `ex` cần là UTE. Không ép kiểu thẳng sang IOException chỉ vì *một lần* gặp IOException trong log trước đó.

## 8. Ví dụ nâng cao: hai interface có cùng method nhưng throws khác nhau

Một trường hợp ít gặp hơn nhưng quan trọng khi tự viết dynamic proxy là **duplicate interface methods**: proxy triển khai nhiều interface có method **cùng tên và chữ ký**, nhưng các interface công khai **những checked exception khác nhau**.

Ví dụ:

~~~java
interface FileAction {
    void execute() throws java.io.IOException;
}

interface DbAction {
    void execute() throws java.sql.SQLException;
}
~~~

Cùng một proxy object có thể được gọi qua `FileAction.execute()` hoặc `DbAction.execute()`.

Mọi checked exception thoát khỏi handler phải **tương thích với throws clause của tất cả các method interface trùng chữ ký** có thể được gọi qua proxy. Vì `IOException` và `SQLException` là hai nhánh checked **không kế thừa nhau**, việc ném IOException **không hợp lệ với DbAction.execute()**. Trong trường hợp này, proxy không thể cho IOException thoát ra trực tiếp, dù caller đang cast proxy về `FileAction`.

Một điểm rất dễ đánh lừa người đọc: đối tượng `Method` truyền vào handler có thể đến từ **interface xuất hiện đầu tiên trong danh sách proxy interfaces**, nên `method.getExceptionTypes()` **không nhất thiết** biểu diễn đầy đủ ràng buộc checked exception của **mọi interface trùng method**.

### 8.1. Chương trình riêng kiểm chứng trường hợp method trùng

Lưu thành file **`DuplicateProxyThrowsDemo.java`**:

~~~java
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.sql.SQLException;

public class DuplicateProxyThrowsDemo {
    interface FileAction { void execute() throws IOException; }
    interface DbAction { void execute() throws SQLException; }

    public static void main(String[] args) {
        Object proxy = Proxy.newProxyInstance(
                DuplicateProxyThrowsDemo.class.getClassLoader(),
                new Class<?>[] {FileAction.class, DbAction.class},
                (obj, method, arguments) -> {
                    System.out.println("handler-declaring="
                            + method.getDeclaringClass().getSimpleName());
                    throw new IOException("read failed");
                });

        try {
            ((FileAction) proxy).execute();
        } catch (UndeclaredThrowableException ex) {
            System.out.println("file-call=" + ex.getClass().getSimpleName());
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        } catch (IOException ex) {
            System.out.println("direct-io=" + ex.getMessage());
        }

        try {
            ((DbAction) proxy).execute();
        } catch (UndeclaredThrowableException ex) {
            System.out.println("db-call=" + ex.getClass().getSimpleName());
        } catch (SQLException ex) {
            System.out.println("direct-sql=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy độc lập:

~~~bash
javac --release 17 -encoding UTF-8 DuplicateProxyThrowsDemo.java
java DuplicateProxyThrowsDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
handler-declaring=FileAction
file-call=UndeclaredThrowableException
cause=IOException
handler-declaring=FileAction
db-call=UndeclaredThrowableException
~~~

Điều cần rút ra:

1. Proxy được khai báo thứ tự interface `FileAction` trước `DbAction`, nên metadata Method trong ví dụ được nhận diện là `FileAction`.
2. Handler ném IOException, nhưng method tương ứng của `DbAction` không khai báo IOException.
3. UTE xuất hiện cả khi caller gọi qua `FileAction` và khi gọi qua `DbAction`.
4. Chỉ dựa trên `Method.getExceptionTypes()` của object đưa cho handler là **chưa đủ** để chứng minh ngoại lệ checked sẽ đi qua khi có method trùng giữa nhiều interfaces.

Theo Javadoc `Proxy` Java 17, trường hợp duplicate methods phải tuân điều kiện tương thích cho tất cả những interface methods mà proxy có thể được gọi qua. Một thiết kế đơn giản hơn có thể tránh tình trạng này bằng cách tách API hoặc thống nhất hợp đồng checked exception giữa các interface.

## 9. Khi nào proxy ném UTE và khi nào không?

| Throwable thoát khỏi `InvocationHandler.invoke` | Interface method | Kết quả thường thấy |
| --- | --- | --- |
| `IOException` | `throws IOException` | IOException trực tiếp |
| `FileNotFoundException` | `throws IOException` | FileNotFoundException trực tiếp |
| `IOException` | Không `throws` checked | UTE bọc IOException |
| `SQLException` | `throws IOException` | UTE bọc SQLException |
| `IllegalStateException` | Không `throws` | IllegalStateException trực tiếp |
| `NullPointerException` | `throws IOException` | NullPointerException trực tiếp |
| `AssertionError` | Không `throws` | AssertionError trực tiếp |
| `InvocationTargetException` | `throws IOException` | UTE bọc InvocationTargetException |
| `IOException` sau khi unwrap `InvocationTargetException` | `throws IOException` | IOException trực tiếp |
| `IOException` với hai method trùng chữ ký, một interface chỉ cho SQLException | Cả hai interface phải được xét | UTE bọc IOException |

Bảng nói về **JDK dynamic proxy** do `java.lang.reflect.Proxy` tạo, không nên áp dụng máy móc cho tất cả proxy của framework hoặc proxy theo subclass.

## 10. Checked exception ở compile time và runtime không mâu thuẫn

Một câu hỏi thường gặp: “Nếu method `String undeclared()` không khai báo IOException, tại sao handler biên dịch được khi ném IOException?”

Phải phân biệt **hai vị trí compiler kiểm tra**:

**Tại nơi cài đặt handler:**

~~~java
InvocationHandler handler = (proxy, method, args) -> {
    throw new IOException("network failed");
};
~~~

Mã hợp lệ vì `InvocationHandler.invoke` khai báo `throws Throwable`.

**Tại nơi gọi method interface:**

~~~java
Service service = ...;
service.undeclared();
~~~

Caller nhìn thấy `Service.undeclared()` không có checked IOException. Compiler không buộc xử lý IOException ở đây. Tại runtime, proxy nhận checked IOException từ handler rồi tạo UTE unchecked để truyền kết quả thất bại mà vẫn tuân giới hạn checked throws của method.

Không có mâu thuẫn giữa compile time và runtime; **proxy cung cấp một cơ chế runtime wrapping** cho tình huống handler đã được phép ném rộng hơn chữ ký interface.

### Vì sao không viết catch IOException trực tiếp?

Nếu đoạn `try` chỉ chứa lời gọi phương thức không khai báo checked IOException (và không có nguồn checked IOException khác), câu lệnh:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH TRONG NGỮ CẢNH NÀY:
try {
    service.undeclared();
} catch (IOException ex) {
    System.out.println("Could not load");
}
~~~

bị compiler báo IOException không được ném theo phân tích compile-time của try. Việc handler ở runtime có thể ném IOException trước khi bị proxy chuyển thành UTE **không thay đổi kết quả phân tích compile-time ở caller**.

Nếu service công khai một hợp đồng có thể lỗi I/O mà caller cần xử lý riêng, hãy cân nhắc khai báo `throws IOException` trên interface từ đầu, hoặc dùng một custom runtime exception hợp đồng có cause là IOException khi policy API không muốn checked exception.

## 11. Cách sửa đúng theo tầng gây vấn đề

### 11.1. Sửa interface khi checked IOException là một phần hợp đồng

Nếu API công khai cho phép lỗi I/O và caller cần biết loại này:

~~~java
interface RemoteReader {
    byte[] read() throws IOException;
}
~~~

Đây là interface minh họa, cần import IOException. Handler có thể ném IOException hoặc subtype phù hợp. Caller bắt/khai báo IOException theo cách Java thông thường. Đây là lựa chọn rõ ràng khi **checked exception được kỳ vọng và có ý nghĩa với caller**.

Không tự đổi `throws` của một public interface đang được sử dụng rộng rãi mà chưa xét tương thích nguồn/binary và chính sách phiên bản; đây là thay đổi hợp đồng.

### 11.2. Dùng runtime wrapper có cause nếu API không muốn checked throws

Nếu interface cố ý không khai báo checked exception, thay vì để raw IOException thoát khỏi handler và tự nhận UTE chung chung, bạn có thể chuyển sang một unchecked exception phù hợp:

~~~java
try {
    return readFromDisk();
} catch (IOException ex) {
    throw new java.io.UncheckedIOException("Cannot load data", ex);
}
~~~

Đây là mã minh họa bên trong handler hoặc method phù hợp, cần định nghĩa `readFromDisk()`. `UncheckedIOException` chuyên dùng để bọc IOException, giữ cause. Nếu là lỗi thuộc một domain khác, chọn một custom runtime exception phù hợp với **hợp đồng caller**, không mặc định dùng UncheckedIOException cho mọi checked Throwable.

Ưu điểm là caller nhận một lỗi **được đặt tên có chủ đích**, không phải wrapper kỹ thuật UTE phát sinh bất ngờ. Nhưng đổi checked sang unchecked cũng phải dựa vào chính sách API; nó không tự giải quyết khả năng phục hồi lỗi hoặc retry.

### 11.3. Unwrap InvocationTargetException trong handler phản chiếu

Nếu handler delegate bằng `Method.invoke`, ưu tiên:

~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
~~~

Mẫu trích từ chương trình chính. Đừng đưa nguyên `InvocationTargetException` sang proxy nếu public interface chỉ khai báo checked exception gốc.

### 11.4. Xử lý lỗi setup reflection riêng

Những tình huống `IllegalAccessException`, cấu hình quyền truy cập, sai target, sai tham số hoặc sai method là vấn đề framework/implementation. Hãy phân loại và báo lỗi kỹ thuật rõ, không bọc hết chúng thành `IOException` để “lách” hợp đồng.

### 11.5. Ở caller: log cause và áp dụng fallback an toàn

Nếu caller không sở hữu interface/handler (ví dụ dùng thư viện bên thứ ba), có thể bắt UTE **ở ranh giới tích hợp** và phân tích cause để đưa ra hành động được tài liệu hóa.

Ví dụ:

~~~java
try {
    invokeThirdPartyService();
} catch (UndeclaredThrowableException ex) {
    Throwable cause = ex.getUndeclaredThrowable();
    logUnexpectedProxyFailure(ex, cause);
    throw ex; // Hoặc chuyển sang lỗi hợp đồng rõ ràng ở boundary.
}
~~~

Đây là đoạn minh họa: cần định nghĩa các hàm và biến phù hợp. Không bắt UTE rồi bỏ qua để tiếp tục như thể thao tác đã thành công. Nếu quyết định dịch sang domain exception, giữ cause, ngữ cảnh và không dựa vào message của wrapper.

## 12. Proxy chỉ áp dụng cho interface, không đồng nhất với subclass proxy

JDK dynamic proxy được tạo qua `java.lang.reflect.Proxy` triển khai **interface**. Nó không biến một class bất kỳ thành subclass động theo cùng API.

Trong các framework, có thể tồn tại nhiều cơ chế proxy:

- **JDK interface-based dynamic proxy:** sử dụng `Proxy` và `InvocationHandler`, tuân quy tắc UTE đang học.
- **Subclass-based proxy hoặc bytecode enhancement:** có thể sử dụng cơ chế khác để tạo/intercept method; hành vi exception phụ thuộc framework và hợp đồng method thực tế.
- **Remote proxy (RPC):** có thể chuyển lỗi từ tiến trình khác thành exception domain/transport; không đồng nghĩa luôn dùng `java.lang.reflect.Proxy`.

Nếu thấy UTE trong ứng dụng dùng framework, hãy xem stack trace và cấu hình proxy để xác nhận proxy thực sự là JDK proxy. **Không kết luận mọi proxy đều bọc checked exception theo một cách giống nhau** chỉ dựa vào từ “proxy”.

## 13. Các method đặc biệt: equals, hashCode, toString

Một proxy JDK thường điều hướng cả lời gọi các method public của `Object` như `equals`, `hashCode` và `toString` đến `InvocationHandler`.

Nếu handler chỉ giả định mọi method đều là business API (ví dụ `load`, `save`), việc logger hoặc debugger gọi `proxy.toString()` có thể dẫn tới lỗi ngoài dự kiến.

Một chiến lược đơn giản:

~~~java
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "toString" -> "ServiceProxy";
        case "hashCode" -> System.identityHashCode(proxy);
        case "equals" -> proxy == args[0];
        default -> throw new UnsupportedOperationException(method.getName());
    };
}
~~~

Đây là **đoạn minh họa bên trong handler**, cần tham số `method`, `proxy`, `args`, và nếu triển khai thực tế phải xét chính sách equality/hashCode phù hợp.

Một lỗi thiết kế nguy hiểm là xử lý method của `Object` bằng cách gọi trực tiếp `method.invoke(proxy, args)` ngay trong handler: lời gọi phản chiếu trên chính proxy có thể đi vào handler trở lại, gây **đệ quy vô hạn**. Phải ủy quyền đến object thật phù hợp hoặc có chính sách riêng.

`equals/hashCode/toString` không khai báo checked exception. Vì vậy nếu handler cố ném checked IOException từ những lời gọi này, quy tắc UTE cũng có thể xuất hiện. Nhưng đây chỉ là một phần của bức tranh rộng hơn về hợp đồng proxy.

## 14. Method trùng giữa interface và Object: không nên chỉ nhìn Method metadata

Với các method `equals`, `hashCode` và `toString`, JDK proxy có quy tắc xử lý đặc biệt về `Method` đưa vào invocation handler. Với các duplicate methods giữa nhiều interfaces, metadata `Method` có thể gắn với interface xuất hiện sớm hơn.

Điều này tạo hai khuyến nghị:

1. **Không xem `method.getDeclaringClass()` là bằng chứng duy nhất** về mọi hợp đồng throws của các interface được proxy triển khai.
2. Khi handler phụ thuộc vào chữ ký method, cần phân biệt method của Object, method interface trùng và các interface chuyên biệt. Đặc biệt chú ý trường hợp có nhiều throws clause không tương thích.

Với proxy phức tạp, nên xem danh sách interface của proxy và thiết kế một **mapping explicit** cho method/exception policy, thay vì chỉ dùng `Method.getExceptionTypes()` rồi giả định đủ.

## 15. UTE có giống InvocationTargetException không?

**Không.** Hai lớp này khác vai trò và vị trí xuất hiện.

| Đặc điểm | `UndeclaredThrowableException` | `InvocationTargetException` |
| --- | --- | --- |
| Package | `java.lang.reflect` | `java.lang.reflect` |
| Nhóm | **Unchecked** (extends RuntimeException) | **Checked** (extends ReflectiveOperationException) |
| Thường do đâu? | JDK proxy gặp checked Throwable không hợp đồng | `Method.invoke`/reflection báo exception do target method ném |
| Truy xuất Throwable bọc | `getUndeclaredThrowable()`, `getCause()` | `getTargetException()`, `getCause()` |
| Cần khai báo/catch khi method có thể ném? | Compiler không bắt buộc vì unchecked | Có nếu không xử lý trong handler/method |
| Cách phòng ngừa phổ biến | Giữ hợp đồng checked throws hoặc dịch ngoại lệ có chủ đích | Unwrap exception mục tiêu ngay khi delegate reflection |

Hai lớp **có thể lồng nhau**: UTE bọc InvocationTargetException nếu handler để wrapper checked reflection thoát ra qua một interface không khai báo loại checked đó.

## 16. Cách debug khi stack trace hiển thị UndeclaredThrowableException

Hãy làm theo trình tự:

1. **Xác nhận nguồn proxy:** đó có phải object được tạo từ `Proxy.newProxyInstance` không? Dùng stack trace và thông tin class/framework; có thể kiểm tra `Proxy.isProxyClass(instance.getClass())` nếu phù hợp.
2. **Xác định method interface mà caller vừa gọi**, đặc biệt throws clause công khai.
3. **Đọc wrapped throwable của UTE:** `getUndeclaredThrowable()` hoặc `getCause()`.
4. Nếu wrapped là `InvocationTargetException`, **tiếp tục xem `getTargetException()`/`getCause()`** để tìm lỗi target.
5. Xác định **handler đã ném checked exception nào ra ngoài**, khác với thông điệp hoặc loại sâu nhất trong chain.
6. **So kiểu checked thực tế với throws clause** của method interface, bao gồm cả các duplicate methods nếu có nhiều interface.
7. **Kiểm tra nơi delegate:** nếu có `Method.invoke`, handler đã catch `InvocationTargetException` chưa?
8. **Kiểm tra logic translate exception:** có bọc mọi exception vào checked type không được công bố không?
9. **Sửa tại tầng sở hữu hợp đồng hoặc handler** nếu có quyền. Không buộc mọi caller xử lý UTE bằng cách cast kiểu tùy tiện.
10. **Ghi log đầy đủ** cả wrapper lẫn cause, có đủ ngữ cảnh nhưng không lộ thông tin nhạy cảm.

Một chuỗi điển hình để đọc:

~~~text
UndeclaredThrowableException
  Caused by: InvocationTargetException
    Caused by: IOException("disk offline")
~~~

Đây là sơ đồ nguyên nhân, không phải nguyên văn của mọi `printStackTrace()`; tên frame, số dòng và định dạng tùy JVM.

## 17. Những lỗi thiết kế thường gặp

1. **“InvocationHandler.invoke throws Throwable nên public interface cũng cho throws Throwable.”** Sai: hai hợp đồng khác nhau.
2. **“UTE là checked exception.”** Sai: UTE kế thừa RuntimeException.
3. **“UTE làm mất exception gốc.”** Sai: thường có thể truy qua `getUndeclaredThrowable()`/`getCause()`.
4. **“Mọi exception handler ném đều bị UTE bọc.”** Sai: RuntimeException/Error đi qua; checked tương thích cũng đi qua.
5. **“Method interface có throws IOException thì IOException từ target qua Method.invoke chắc chắn đi thẳng ra.”** Sai nếu handler để InvocationTargetException thoát ra.
6. **“InvocationTargetException là subtype IOException.”** Sai: đó là checked reflection exception khác.
7. **“Chỉ cần đổi catch ở caller là chữa được proxy.”** Không nhất thiết: nên sửa handler/contract khi có quyền.
8. **“Catch IOException quanh một method không khai báo checked IOException lúc nào cũng hợp lệ.”** Không: compiler kiểm tra nguồn checked exception trong try.
9. **“Có thể tự chuyển mọi checked exception sang IOException để vừa throws.”** Sai nếu ý nghĩa lỗi không phù hợp.
10. **“Unwrap mọi Throwable tới tầng sâu nhất rồi ném là luôn tốt.”** Sai: có thể phá hợp đồng ở ranh giới API và mất context.
11. **“getUndeclaredThrowable luôn khác null.”** Không tuyệt đối với UTE được tạo thủ công.
12. **“Nếu wrapped exception là IOException thì nguyên nhân chắc chắn là lỗi file.”** Không: IOException còn dùng cho nhiều thao tác I/O khác, cần đọc ngữ cảnh.
13. **“Proxy có hai interface trùng method thì checked throws là hợp các loại được khai báo.”** Sai: phải phù hợp với tất cả hợp đồng method liên quan.
14. **“Method.getExceptionTypes() của đối tượng Method handler nhận luôn đủ toàn bộ ràng buộc.”** Sai trong trường hợp duplicate methods.
15. **“Gọi method.invoke(proxy,args) trong handler là cách delegate an toàn.”** Có thể gây proxy gọi lại handler và đệ quy.
16. **“equals/hashCode/toString không liên quan handler.”** Sai với JDK dynamic proxy.
17. **“Mọi thư viện AOP đều sử dụng Proxy của JDK.”** Sai: có nhiều cơ chế proxy.
18. **“Tạo runtime wrapper tự động giải quyết retry/transaction.”** Sai: wrapper chỉ thay đổi cách biểu diễn/truyền lỗi, không tự phục hồi logic.
19. **“Chỉ log UTE.getMessage() là đủ.”** Thường không: cần cause và stack trace.
20. **“Thêm throws ở implementation proxy có thể giải quyết mọi trường hợp.”** Với JDK-generated proxy, hợp đồng public interface và các duplicate methods mới là yếu tố then chốt.

## 18. Bài tập tự kiểm tra

**Câu 1.** Interface có `void run();`, handler ném `IOException`. Caller sẽ thường nhận kiểu gì?

*Đáp án:* `UndeclaredThrowableException` bọc IOException, vì checked IOException không được interface method khai báo.

**Câu 2.** Đổi interface thành `void run() throws IOException;` và handler vẫn ném IOException. Kết quả?

*Đáp án:* IOException có thể được truyền trực tiếp, không cần UTE.

**Câu 3.** Handler ném `IllegalArgumentException` dù method interface không có throws. Proxy xử lý thế nào?

*Đáp án:* Đây là RuntimeException unchecked nên đi ra trực tiếp.

**Câu 4.** Handler ném `AssertionError`, proxy có tạo UTE không?

*Đáp án:* Không, Error thuộc nhóm unchecked nên truyền trực tiếp.

**Câu 5.** Interface có `throws IOException`, nhưng handler thực hiện `method.invoke(target, args)` và không catch InvocationTargetException. Target ném IOException. Caller có thể nhận gì?

*Đáp án:* UTE bọc InvocationTargetException, bên trong là IOException của target.

**Câu 6.** Sửa handler như thế nào để truyền lại IOException gốc đúng hợp đồng?

*Đáp án:* Catch InvocationTargetException và `throw ex.getCause()`. Nếu cause là IOException phù hợp throws, proxy truyền trực tiếp.

**Câu 7.** UTE có hai getter nào giúp xem wrapped exception?

*Đáp án:* `getUndeclaredThrowable()` và `getCause()`.

**Câu 8.** Nếu wrapped là InvocationTargetException, cần xem tiếp API nào?

*Đáp án:* `getTargetException()` hoặc `getCause()` để thấy Throwable do target thực sự ném.

**Câu 9.** Vì sao handler được viết `throw new SQLException(...)` dù interface không khai báo SQLException?

*Đáp án:* Bởi `InvocationHandler.invoke()` khai báo `throws Throwable`, nhưng proxy vẫn kiểm tra hợp đồng interface tại runtime và có thể bọc nó trong UTE.

**Câu 10.** Hai interface cùng method `execute()`, một khai báo IOException, một khai báo SQLException. Handler ném IOException. Có được truyền trực tiếp qua mọi caller không?

*Đáp án:* Không. Vì IOException không tương thích với throws clause của interface kia, proxy có thể tạo UTE; ví dụ Java 17 ở trên cho kết quả UTE ở cả hai cách gọi.

**Câu 11.** Có nên dùng UTE làm custom exception nghiệp vụ cho mọi API không?

*Đáp án:* Không. Đây chủ yếu là wrapper phản ánh mismatch tại JDK dynamic proxy. Nếu API cần phản ứng nghiệp vụ rõ, dùng hợp đồng exception riêng có ý nghĩa hơn.

**Câu 12.** Bắt UTE rồi chỉ in message và return success có an toàn không?

*Đáp án:* Không. Lỗi gốc còn tồn tại; bỏ qua có thể làm chương trình trả kết quả giả và che bug.

**Câu 13.** `Method.invoke(proxy,args)` ngay trên chính proxy trong handler có nguy cơ gì?

*Đáp án:* Nó có thể đi vào cùng handler trở lại và gây đệ quy không kiểm soát.

**Câu 14.** Vì sao `method.getDeclaringClass()` không luôn phản ánh toàn bộ hợp đồng checked exception khi proxy có nhiều interface?

*Đáp án:* Với method trùng chữ ký, handler có thể nhận Method từ một interface đã chọn, nhưng quy tắc throws vẫn chịu ràng buộc của các interface có method tương ứng.

## 19. Checklist thiết kế InvocationHandler

Trước khi đưa một JDK dynamic proxy vào production:

- **Interface contract:** đã công bố checked exceptions đúng nhu cầu của caller chưa?
- **Handler throwing policy:** những checked Throwable nào có thể thoát ra từ handler?
- **Reflection delegation:** có unwrap `InvocationTargetException` khi gọi target qua `Method.invoke` không?
- **Cause preservation:** có giữ lỗi gốc khi dịch thành runtime/domain exception không?
- **Multiple interfaces:** có duplicate methods với throws khác nhau không?
- **Object methods:** đã có chính sách hợp lý cho `equals`, `hashCode`, `toString` chưa?
- **Return values:** kiểu `Object` mà handler trả có tương thích kiểu return của method, kể cả primitive không?
- **Access/arguments:** đã phân biệt lỗi cấu hình reflection với lỗi nghiệp vụ do target ném chưa?
- **Logging:** có giữ đầy đủ chain UTE → InvocationTargetException → lỗi gốc, cùng bối cảnh và dữ liệu không nhạy cảm không?
- **Tests:** đã test checked declared, checked undeclared, unchecked, Error, reflection wrapper và duplicate interfaces nếu phù hợp chưa?
- **Caller policy:** có đang bắt/nuốt UTE rồi báo thành công giả không?
- **Ownership:** nên sửa hợp đồng interface/handler hay cần một adapter ở boundary do thư viện bên ngoài không thể chỉnh sửa?
- **Maintenance:** nếu nâng Java hoặc đổi cơ chế proxy/framework, đã test lại contract exception chưa?

## 20. Tài liệu Java 17 chính thức

- [Java SE 17 API – UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): điều kiện proxy tạo wrapper, getter và cơ chế cause.
- [Java SE 17 API – InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): `invoke(Object,Method,Object[]) throws Throwable` và quy tắc unchecked/checked.
- [Java SE 17 API – Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): tạo proxy interface, duplicate methods, checked exception constraints.
- [Java SE 17 API – InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): wrapper checked từ reflection và cách truy xuất target exception.
- [Java SE 17 API – Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `Method.invoke` và ngoại lệ phát sinh.
- [Java SE 17 API – RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): nhánh unchecked trong phân cấp Throwable.
- [Java SE 17 API – Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, message, stack trace, suppressed exceptions.
- [JLS Java SE 17 – chương 11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked exceptions và phân tích compiler.
- [JLS Java SE 17 – mục 8.4.8.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): giới hạn checked throws khi override thông thường.

**Kết luận:** `UndeclaredThrowableException` xuất hiện trong JDK dynamic proxy khi `InvocationHandler.invoke` làm thoát ra **checked exception không tương thích với `throws` của method interface**. RuntimeException và Error không bị wrapper theo cơ chế này; checked exception được khai báo hợp lệ cũng đi ra trực tiếp. Khi delegate bằng reflection, **hãy unwrap `InvocationTargetException`** để giữ exception gốc và hợp đồng caller, đặc biệt nếu target đã ném IOException được interface cho phép. Luôn xem cả cause, xét duplicate interface methods và đừng dùng việc catch UTE để thay cho thiết kế hợp đồng API đúng.