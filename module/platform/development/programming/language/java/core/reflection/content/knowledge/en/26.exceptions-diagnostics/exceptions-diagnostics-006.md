# InvocationTargetException và cách giữ nguyên cause khi dùng Java Reflection

Khi gọi một phương thức qua Java Reflection, lỗi do **chính phương thức được gọi** ném ra thường không đi thẳng tới khối `catch` ở bên ngoài. API `Method.invoke(...)` bọc lỗi gốc trong `InvocationTargetException`. Cơ chế tương tự áp dụng khi constructor thực thi qua `Constructor.newInstance(...)` thất bại vì code bên trong constructor ném ngoại lệ.

Điều cần làm khi chẩn đoán là phân biệt **lỗi thực thi bên trong đối tượng đích** với **lỗi do thao tác Reflection**, đọc ngoại lệ gốc qua `getCause()` và **giữ liên kết cause** khi bổ sung thông tin ngữ cảnh hoặc ném lại ngoại lệ. Nếu chỉ in thông điệp lỗi rồi tạo một exception mới không có cause, thông tin về nơi phát sinh lỗi ban đầu sẽ bị mất khỏi chuỗi chẩn đoán.

Bài này thuộc nhóm **Ngoại lệ và chẩn đoán** của Java Reflection. Các ví dụ dùng Java 17+ và được trình bày đầy đủ để tự biên dịch và chạy.

## 1. InvocationTargetException thực sự đại diện cho điều gì?

Giả sử một phương thức nghiệp vụ có thể thất bại:

~~~java
public String read(String key) throws IOException {
    if ("bad".equals(key)) {
        throw new IOException("không đọc được");
    }
    return "value:" + key;
}
~~~

Nếu gọi trực tiếp `target.read("bad")`, mã gọi phải xử lý `IOException` theo hợp đồng `throws IOException`. Nhưng khi gọi bằng Reflection:

~~~java
Method method = Target.class.getMethod("read", String.class);
Object result = method.invoke(target, "bad");
~~~

`Method.invoke` công bố các ngoại lệ liên quan đến thao tác gọi động, trong đó có **checked exception** `InvocationTargetException`. Khi body của `read` ném `IOException`, lớp wrapper được tạo và chứa chính `IOException` đó làm cause:

~~~text
Call site
   |
   v
Method.invoke(target, "bad")
   |
   v
Target.read("bad")
   |
   +-- throws IOException("không đọc được")    [lỗi gốc]
   |
   v
Method.invoke throws InvocationTargetException
                           |
                           +-- getCause() -> IOException
   |
   v
catch (InvocationTargetException ex)
   |
   +-- xem / ghi log ngoại lệ gốc
   +-- ném lại lỗi gốc hoặc tạo wrapper mới có cause
~~~

Điểm quan trọng:

- `InvocationTargetException` **không tự nói rằng Reflection API bị hỏng**; nó cho biết phần mã được gọi đã ném ngoại lệ.
- `ex.getCause()` trả đối tượng `Throwable` được phương thức hoặc constructor đích ném ra. Lỗi gốc có thể là checked exception (ví dụ `IOException`), `RuntimeException` hoặc `Error`.
- `ex.getTargetException()` cũng trả ngoại lệ đích; đây là phương thức có từ trước cơ chế exception chaining chung. **Ưu tiên `getCause()`**.
- Javadoc cho phép `getCause()` trả `null` (có thể tự tạo `InvocationTargetException` không kèm target). Khi `Method.invoke` thực sự vừa bắt lỗi từ target, thông thường sẽ có cause; mã thư viện phòng thủ vẫn nên tránh dereference nếu cause là `null`.
- Wrapper có stack trace riêng của nó; cause cũng mang stack trace ở nơi lỗi nghiệp vụ phát sinh. Hai lớp thông tin phục vụ hai mục đích chẩn đoán khác nhau.

`InvocationTargetException` kế thừa `ReflectiveOperationException` và là **checked exception**. Không thể dùng một lệnh `catch (RuntimeException ex)` để bắt riêng wrapper này.

## 2. Nhận diện hai nhóm lỗi: target exception và Reflection exception

Không phải mọi lỗi xảy ra quanh một lời gọi `invoke` đều là `InvocationTargetException`.

| Tình huống | Ngoại lệ điển hình | Điểm phát sinh và cách hiểu |
|---|---|---|
| Body phương thức ném `IOException` | `InvocationTargetException` với cause là `IOException` | Target đã chạy và thất bại |
| Body phương thức ném `IllegalStateException` | `InvocationTargetException` với cause là `IllegalStateException` | Target đã chạy và thất bại |
| Body constructor ném `IllegalArgumentException` | `InvocationTargetException` với cause là `IllegalArgumentException` | Constructor đã chạy và thất bại |
| Sai số lượng/kiểu đối số truyền vào `Method.invoke` | `IllegalArgumentException` | API từ chối lời gọi trước khi thực thi target |
| Đối tượng nhận (`receiver`) không phù hợp với method instance | `IllegalArgumentException` | Sai đối tượng đích |
| Dùng `null` làm receiver của method instance | `NullPointerException` | Không có đối tượng đích để gọi |
| Thành viên không thể truy cập theo quy tắc Java | `IllegalAccessException` | Lỗi quyền truy cập Reflection |
| `getMethod`/`getDeclaredMethod` không tìm được chữ ký | `NoSuchMethodException` | Lỗi bước tra cứu trước lời gọi |
| Class initialization do lời gọi kích hoạt thất bại | `ExceptionInInitializerError` | Lỗi khởi tạo lớp, có thể xuất hiện ngoài wrapper |
| Constructor không thể tạo instance của abstract class | `InstantiationException` | Không thể khởi tạo kiểu đó |

Vì thế đừng viết `catch (Exception e) { throw new RuntimeException("Target lỗi"); }` cho toàn bộ đoạn Reflection. Cách đó làm mờ ranh giới giữa **chương trình đích lỗi** và **host gọi sai hoặc không có quyền**. Có thể xử lý trong một tầng chung khi cần, nhưng thông điệp và cause nên đủ để phân biệt từng nhóm.

Một lưu ý kỹ thuật: `Class.newInstance()` đã deprecated từ Java 9 và có cách lan truyền ngoại lệ constructor khác. Khi cần tạo đối tượng từ `Class`, ưu tiên `getDeclaredConstructor(...).newInstance(...)` để có hành vi exception wrapping rõ ràng.

## 3. Chương trình Java 17+ chạy được: thấy nguyên nhân và giữ cause

Lưu nguyên khối mã sau thành **`ReflectionFailureDemo.java`**. Nó minh họa năm bước: gọi thành công, thêm ngữ cảnh và giữ nguyên cause, lan truyền lại checked exception đúng kiểu, bắt lỗi constructor, và phân biệt lỗi sai đối số Reflection.

~~~java
import java.io.IOException;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionFailureDemo {
    static class Target {
        public Target(String token) {
            if (token.isBlank()) {
                throw new IllegalStateException("token rỗng");
            }
        }

        public String read(String key) throws IOException {
            if ("bad".equals(key)) {
                throw new IOException("không đọc được");
            }
            return "value:" + key;
        }
    }

    static String callAndWrap(Method method, Target target, String key) {
        try {
            return (String) method.invoke(target, key);
        } catch (InvocationTargetException ex) {
            throw new IllegalStateException(
                    "Không gọi được Target.read", ex.getCause());
        } catch (IllegalAccessException ex) {
            throw new IllegalStateException(
                    "Không có quyền truy cập method", ex);
        }
    }

    static String callAndPreserve(Method method, Target target, String key)
            throws IOException {
        try {
            return (String) method.invoke(target, key);
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            if (cause instanceof IOException io) {
                throw io;
            }
            if (cause instanceof RuntimeException re) {
                throw re;
            }
            if (cause instanceof Error error) {
                throw error;
            }
            throw new IllegalStateException("Lỗi ngoài hợp đồng", cause);
        } catch (IllegalAccessException ex) {
            throw new IllegalStateException(
                    "Không có quyền truy cập method", ex);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Constructor<Target> constructor =
                Target.class.getDeclaredConstructor(String.class);
        Target target = constructor.newInstance("ok");
        Method method = Target.class.getMethod("read", String.class);

        System.out.println("success = " + callAndWrap(method, target, "a"));

        try {
            callAndWrap(method, target, "bad");
        } catch (IllegalStateException ex) {
            Throwable cause = ex.getCause();
            System.out.println("wrapper = " + ex.getClass().getSimpleName());
            System.out.println("cause = " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
            System.out.println("origin = " + cause.getStackTrace()[0].getMethodName());
        }

        try {
            callAndPreserve(method, target, "bad");
        } catch (IOException ex) {
            System.out.println("preserve = " + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }

        try {
            constructor.newInstance("");
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println("constructor = " + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }

        try {
            method.invoke(target, 42);
        } catch (IllegalArgumentException ex) {
            System.out.println("argument = " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 ReflectionFailureDemo.java
java ReflectionFailureDemo
~~~

**Stdout thực tế của ví dụ (đã kiểm chứng):**

~~~text
success = value:a
wrapper = IllegalStateException
cause = IOException: không đọc được
origin = read
preserve = IOException: không đọc được
constructor = IllegalStateException: token rỗng
argument = IllegalArgumentException
~~~

Giải thích kết quả:

1. Khi `key = "a"`, `read` trả `"value:a"`; Reflection hoàn thành bình thường.
2. Khi `key = "bad"`, `IOException` được `Method.invoke` bọc thành `InvocationTargetException`. `callAndWrap` tạo `IllegalStateException` có ngữ cảnh nhưng truyền **đúng đối tượng cause** vào constructor của wrapper mới.
3. `origin = read` chứng minh stack trace của cause vẫn bắt đầu từ phương thức `read` nơi `IOException` được tạo/ném (trong ví dụ cụ thể này).
4. `callAndPreserve` dùng pattern matching `instanceof` của Java 17 để nhận diện `IOException` và ném lại chính ngoại lệ đó. Chữ ký hàm vẫn khai báo `throws IOException`, giữ hợp đồng checked exception cho caller.
5. Constructor `Target(String)` ném `IllegalStateException` khi token rỗng. `Constructor.newInstance("")` trả lỗi qua `InvocationTargetException`, và cause vẫn là `IllegalStateException` của constructor.
6. `method.invoke(target, 42)` vi phạm chữ ký `read(String)` nên ném **`IllegalArgumentException` trực tiếp**, không tạo `InvocationTargetException` cho tình huống này.

Các phương thức trong `Target` được công bố `public` cho mục đích demo, còn lớp `Target` là nested class cùng phạm vi với mã gọi. Với mã chạy khác package/module, phải tuân thủ quy tắc truy cập Java và JPMS; không suy luận rằng cứ tìm thấy `Method` là có thể gọi.

## 4. Hai chiến lược giữ nguyên nguyên nhân: wrap có cause hoặc ném lại đúng kiểu

### 4.1. Bổ sung ngữ cảnh bằng wrapper mới

Một tầng tích hợp có thể không muốn đưa `IOException` của thư viện nội bộ ra API. Thay vào đó, nó cung cấp ngoại lệ ở cấp ứng dụng:

~~~java
catch (InvocationTargetException ex) {
    Throwable cause = ex.getCause();
    throw new IllegalStateException("Không gọi được phương thức đồng bộ", cause);
}
~~~

Khối trên là **đoạn mã đặt trong một lệnh `try` gọi Reflection**, không phải chương trình độc lập. Constructor `IllegalStateException(String, Throwable)` lưu lại mối quan hệ:

~~~text
IllegalStateException: Không gọi được phương thức đồng bộ
    Caused by: IOException: không đọc được
        at Target.read(...)
        ...
~~~

Khi log đầy đủ `IllegalStateException`, Java có thể in cả chuỗi `Caused by` và các stack frame liên quan. Wrapper mới tạo vị trí/nhãn chẩn đoán ở tầng tích hợp; cause giữ nguyên dấu vết gốc.

Nếu muốn **giữ toàn bộ đường đi qua Reflection**, có thể gắn `ex` làm cause thay vì `ex.getCause()`. Khi đó chuỗi là `ApplicationException -> InvocationTargetException -> IOException`. Cách này không làm mất cause nhưng dài hơn một tầng; chọn theo mức độ cần debug cơ chế Reflection. Khi phân loại lỗi nghiệp vụ, thường cần lấy nguyên nhân đích qua `getCause()`.

**Sai lầm phổ biến:**

~~~java
catch (InvocationTargetException ex) {
    throw new IllegalStateException(ex.getCause().getMessage());
}
~~~

Đây cũng chỉ là mảnh mã minh họa trong khối `try/catch`. Nó **chỉ lấy chuỗi thông điệp**, tạo một exception mới **không có cause**. Lúc log wrapper mới, đường stack trace của `IOException` gốc không còn nối qua `getCause()`.

Tương tự, chỉ ghi `logger.error("{}", ex.getMessage())` có thể làm mất stack trace hoặc chi tiết cause nếu logger không được truyền đối tượng `Throwable`. Dùng API logging của thư viện thực tế để truyền exception làm đối số throwable; ví dụ với SLF4J:

~~~java
logger.error("Lỗi gọi phương thức {}", method.getName(), ex.getCause());
~~~

Đây là **mảnh minh họa phụ thuộc SLF4J**, không thuộc chương trình Java độc lập phía trên. Cần bảo đảm dữ liệu trong exception message/log không làm lộ bí mật, thông tin cá nhân hoặc tham số nhạy cảm.

### 4.2. Giữ nguyên checked exception đã công bố

Nếu API của tầng gọi đã khai báo `throws IOException`, bạn có thể giữ nguyên loại và đối tượng ngoại lệ:

~~~java
Throwable cause = ex.getCause();
if (cause instanceof IOException io) {
    throw io;
}
if (cause instanceof RuntimeException re) {
    throw re;
}
if (cause instanceof Error error) {
    throw error;
}
throw new IllegalStateException("Lỗi ngoài hợp đồng", cause);
~~~

Đoạn trên thuộc **nhánh `catch (InvocationTargetException ex)`**. Kiểu `Throwable` là tổng quát; bạn không thể viết `throw cause;` trong mọi method mà không quan tâm chữ ký `throws`. Nếu phương thức hiện tại chỉ cho phép `IOException`, cần phân loại các nhánh như ví dụ. Có thể dùng `throws Throwable` ở những tầng hạ thấp có chủ ý, nhưng nó làm API khó dùng vì caller phải xử lý quá rộng.

Trong nhánh `IOException`, `throw io` ném **chính đối tượng nguyên nhân gốc**; không tạo wrapper mới và không đổi loại ngoại lệ. Các nhánh `RuntimeException` và `Error` được lan truyền nguyên dạng. Một exception checked khác ngoài hợp đồng được gói trong `IllegalStateException` với cause được giữ lại.

**Không nên tự động bao `Error`** hoặc nuốt những lỗi nghiêm trọng trong một wrapper nghiệp vụ. Chính sách xử lý `Error` phụ thuộc ứng dụng, nhưng khi chọn lan truyền, việc phân biệt nó với lỗi kiểm tra dữ liệu bình thường là quan trọng.

## 5. Khai thác cause chain và stack trace khi chẩn đoán

Một số câu hỏi hữu ích khi gặp `InvocationTargetException` trong log:

1. **Lỗi nào thực sự đầu tiên?** Xem `getCause()`, rồi nếu nó còn cause thì tiếp tục đi theo chuỗi.
2. **Lỗi phát sinh ở đâu?** Xem stack trace của ngoại lệ gốc, tìm frame thuộc code đích thay vì dừng ở `Method.invoke`.
3. **Lỗi thuộc domain hay do host gọi sai?** `InvocationTargetException` nghĩa là target đã ném lỗi; `IllegalAccessException`/`NoSuchMethodException`/`IllegalArgumentException` có thể chỉ ra sai hợp đồng Reflection, cấu hình hoặc quyền.
4. **Có wrapper bổ sung ở tầng trung gian?** Một số framework có thể thêm wrapper để cung cấp context. Đừng giả định rằng `getCause()` chỉ cần gọi đúng một lần là luôn tới root cause.
5. **Có suppressed exception không?** Khi có lỗi đóng tài nguyên trong `try-with-resources`, thông tin này có thể được lưu qua `Throwable.getSuppressed()`; log đầy đủ giúp giữ cả cause và suppressed.

Có thể viết hàm tiện ích duyệt cause chain:

~~~java
static Throwable deepestCause(Throwable throwable) {
    Throwable current = throwable;
    while (current != null
            && current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
~~~

Đây là **phương thức hỗ trợ minh họa**, đặt trong một lớp Java. Nếu có ngoại lệ tự tạo ra chu trình cause phức tạp hơn vòng tự tham chiếu, thuật toán thực tế nên theo dõi tập đối tượng đã gặp để tránh lặp vô hạn. Không luôn thay thế exception bên ngoài bằng deepest cause khi hiển thị: wrapper ngoài còn mang **bối cảnh hoạt động**. Thường log full exception sẽ hữu ích hơn chỉ log root message.

Ví dụ một chuỗi đầy đủ có thể là:

~~~text
IllegalStateException: Không gọi được Target.read
  Caused by: IOException: không đọc được
      tại Target.read(...)
~~~

Nếu thay bằng `new RuntimeException("Lỗi")` không truyền cause, chuỗi quan trọng này biến mất. Nếu truyền `new RuntimeException("Lỗi", cause)`, nó vẫn có thể được lần theo.

### Vị trí catch và thông tin context

Bắt lỗi ở ranh giới giữa hai tầng có thể là hợp lý:

- **Adapter Reflection:** Có tên method, class và input context; có thể chuyển exception sang API ổn định của adapter.
- **Service/application boundary:** Có thông tin nghiệp vụ như operation hoặc request ID; có thể thêm context nhưng không log trùng lặp ở mọi tầng.
- **Top-level handler:** Quyết định phản hồi cho caller, log đầy đủ với chính sách ẩn thông tin nhạy cảm.

Không cần `catch` ở mọi tầng chỉ để thêm một dòng `logger.error` giống nhau. Một log được ghi đúng nơi với cause chain đầy đủ thường dễ hiểu hơn nhiều log lặp cùng stack trace.

## 6. Constructor, checked exception, runtime exception và Error

`Constructor.newInstance(...)` cũng dùng `InvocationTargetException` nếu **body constructor** ném exception:

~~~java
Constructor<Target> constructor = Target.class.getDeclaredConstructor(String.class);
try {
    constructor.newInstance("");
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    // original là IllegalStateException("token rỗng") trong demo.
}
~~~

Đoạn trên dùng lớp `Target` đã khai báo trong chương trình hoàn chỉnh. Không nhầm với `NoSuchMethodException` của `getDeclaredConstructor(...)` hoặc `InstantiationException` của bước khởi tạo lớp trừu tượng. Các lỗi đó thuộc cơ chế Reflection.

Với lời gọi `Method.invoke`, việc target ném `RuntimeException` hay một `Error` cũng có thể đi qua `InvocationTargetException`. Vì wrapper là checked exception, ở điểm bắt bạn nhận cùng kiểu wrapper để phân loại bên trong. Khi ném lại:

- Checked cause được phép lan truyền nếu API gọi khai báo phù hợp.
- Runtime cause có thể được ném lại theo đúng loại.
- `Error` cần chính sách xử lý riêng; nhiều hệ thống lan truyền thay vì biến thành lỗi nghiệp vụ bình thường.

Trường hợp class initializer (`static`) bị lỗi khi khởi tạo lớp **không nhất thiết** đi qua wrapper target; Java có thể trực tiếp ném `ExceptionInInitializerError`. Vì thế không đưa mọi `ExceptionInInitializerError` vào nhánh xử lý `InvocationTargetException`.

Mã nguồn cũ có thể sử dụng:

~~~java
Class<?> type = Class.forName("example.Plugin");
Object instance = type.newInstance(); // deprecated
~~~

Đây là **mảnh minh họa API cũ**, không yêu cầu chạy: nếu class không tồn tại, `Class.forName` thất bại; và `Class.newInstance()` đã deprecated. Nó có đặc điểm exception propagation khác với `Constructor.newInstance()`. Khi viết code mới, ưu tiên tìm constructor phù hợp rồi gọi `newInstance(...)` trên đối tượng `Constructor<?>`.

## 7. Các lỗi thiết kế thường gặp và cách sửa

| Lối làm dễ lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| `throw new RuntimeException(ex.getMessage())` | Chỉ giữ chuỗi, mất chuỗi cause | `throw new RuntimeException("...", ex.getCause())` hoặc `throw new RuntimeException("...", ex)` nếu muốn giữ wrapper |
| `throw new RuntimeException(ex.getCause().getMessage())` | Mất loại và stack trace ngoại lệ gốc | Truyền đối tượng `Throwable` vào constructor có cause |
| Chỉ `printStackTrace` rồi `return null` | Host tưởng gọi thành công, lỗi gốc bị che | Trả kết quả thật hoặc lan truyền lỗi có nghĩa |
| Bắt mọi `Exception` rồi báo “method nghiệp vụ lỗi” | Che `NoSuchMethodException`, `IllegalAccessException`, lỗi đối số | Tách lỗi Reflection khỏi lỗi target |
| Dùng `catch (RuntimeException)` để bắt wrapper | `InvocationTargetException` là checked | `catch (InvocationTargetException ex)` hoặc bắt theo hợp đồng checked |
| Luôn viết `throw ex.getCause()` trong API khai báo hẹp | Lỗi compile nếu cause kiểu `Throwable` chưa được khai báo | Phân loại checked/runtime/error hoặc định nghĩa hợp đồng `throws` rõ |
| Luôn dùng `ex.getTargetException()` | API cũ, không đồng nhất với idiom chung | Ưu tiên `ex.getCause()` |
| Chỉ log `ex.getCause().getMessage()` | Thiếu stack trace/cause chain | Log exception object, kiểm soát dữ liệu nhạy cảm |
| Cho rằng `getCause()` không thể `null` trong mọi trường hợp | Có constructor `InvocationTargetException` với target null | Xử lý phòng thủ trong thư viện tổng quát |
| Cố bypass access bằng `setAccessible(true)` mọi nơi | Có thể bị chặn bởi JPMS; che lỗi thiết kế quyền | Ưu tiên API public, `exports`/`opens` phù hợp khi cần |

Cũng cần lưu ý lời gọi phản chiếu có thể đi qua **Java Dynamic Proxy**, callback hoặc tầng framework. Trong Dynamic Proxy, nếu `InvocationHandler.invoke` ném một checked exception **không tương thích `throws` trên interface method**, phía caller có thể gặp `UndeclaredThrowableException`. Đây là cơ chế khác với `Method.invoke` nhưng có thể tạo thêm tầng wrapper. Khi debug, tiếp tục duyệt cause chain thay vì kết luận chỉ từ tên ngoại lệ ngoài cùng.

## 8. Checklist xử lý Reflection trong ứng dụng thực tế

Trước khi gọi Reflection, xác minh tên lớp, tên method, chữ ký tham số, receiver và khả năng truy cập. Dùng `getMethod` cho method public phù hợp, `getDeclaredMethod` khi cần xét member được khai báo trực tiếp; tìm được private member không đồng nghĩa được phép gọi nó trong mọi module.

Khi xử lý exception, nên theo thứ tự:

1. **Bắt đúng `InvocationTargetException`** ở ranh giới `invoke`/`newInstance` nếu bạn cần xử lý lỗi target.
2. **Lấy `Throwable cause = ex.getCause()`**; đừng rút nó thành thông điệp rồi bỏ object.
3. **Chọn chính sách API:** rethrow đúng loại đã khai báo, hay tạo wrapper mới truyền `cause`.
4. **Xử lý các lỗi Reflection khác một cách riêng biệt** để không đánh đồng sai hợp đồng với sai dữ liệu nghiệp vụ.
5. **Log với Throwable đầy đủ**, kèm ngữ cảnh hữu ích (class, method, operation), và giới hạn nội dung nhạy cảm.
6. **Kiểm thử cả trường hợp lỗi**, bao gồm checked exception từ method, runtime exception từ constructor, đối số sai và quyền truy cập.

Khi chỉ cần gọi trực tiếp một kiểu đã biết ở compile time, dùng lời gọi Java thường sẽ có kiểm tra kiểu và xử lý `throws` rõ ràng hơn. Reflection phù hợp khi quyết định kiểu/method nằm ở runtime, nhưng sẽ chuyển trách nhiệm phát hiện lỗi sang phía code tích hợp.

## 9. Bài tập tự kiểm tra

1. Đổi `Target.read` từ `IOException` sang `IllegalArgumentException` trong body. Khi gọi qua `Method.invoke`, ngoại lệ nào ở ngoài cùng? `getCause()` là gì?
2. Đổi `method.invoke(target, 42)` thành `method.invoke(target, "bad")`. Vì sao trường hợp sau có `InvocationTargetException` còn trường hợp đầu ném `IllegalArgumentException` trực tiếp?
3. Sửa `callAndWrap` thành `throw new IllegalStateException("Không gọi được")`. Phần nào của cause chain bị mất? Cách sửa ra sao?
4. Viết thêm một constructor nhận `int` và chủ động ném `IOException`. Gọi bằng `Constructor.newInstance` và xác nhận cause của wrapper. Điều gì khác với lỗi không tìm được constructor đúng chữ ký?
5. Viết một phương thức `callAndPreserve` cho target có thể ném `SQLException`; cập nhật `throws` theo hợp đồng và kiểm tra khả năng bắt trực tiếp `SQLException` ở caller.
6. Tìm trong stack trace hoàn chỉnh hai lớp vị trí: điểm host gọi Reflection và điểm body target ném ngoại lệ. Giải thích vì sao thông điệp của lớp wrapper và message của cause phục vụ hai mục đích khác nhau.

**Điểm cần nhớ:** `InvocationTargetException` là wrapper của lỗi phát sinh trong **method/constructor được gọi**. `getCause()` dẫn tới ngoại lệ thật. Muốn chẩn đoán tốt, giữ nguyên đối tượng cause khi rethrow hoặc thêm wrapper bằng constructor nhận `Throwable`; đồng thời xử lý riêng các lỗi Reflection như sai đối số, sai chữ ký hoặc thiếu quyền.

### Tài liệu chính thức (Java 17)

- [`InvocationTargetException` — `getCause()` và `getTargetException()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [`Method.invoke` — các ngoại lệ được công bố](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [`Constructor.newInstance` — wrapper khi constructor ném lỗi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...))
- [`Class.newInstance` đã deprecated](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#newInstance())
