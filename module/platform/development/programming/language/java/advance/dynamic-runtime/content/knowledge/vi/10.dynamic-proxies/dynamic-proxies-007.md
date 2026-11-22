# 10.7 Giải bọc InvocationTargetException và xử lý UndeclaredThrowableException

Trong Java Dynamic Proxy, một lỗi từ phương thức nghiệp vụ có thể bị **bọc hai tầng** nếu `InvocationHandler` dùng Reflection để gọi đối tượng thật (*target*). Hai lớp ngoại lệ quan trọng là:

- **`java.lang.reflect.InvocationTargetException`**: lớp bọc do `Method.invoke(...)` sinh ra khi **phần thân phương thức đích** ném ngoại lệ.
- **`java.lang.reflect.UndeclaredThrowableException`**: lớp bọc do **proxy động** có thể sinh ra khi `InvocationHandler.invoke(...)` ném một **checked exception** mà phương thức interface được proxy **không cho phép khai báo** trong `throws`.

Hai lớp này giải quyết hai ranh giới khác nhau: **Reflection → target** và **InvocationHandler → caller của proxy**. Gỡ `InvocationTargetException` là bước cần thiết khi muốn truyền nguyên nhân gốc ra ngoài, nhưng **chỉ gỡ bọc chưa bảo đảm tránh được `UndeclaredThrowableException`**: ngoại lệ gốc vẫn phải phù hợp với hợp đồng `throws` của phương thức trong interface.

Mục tiêu bài học: hiểu chính xác hai cơ chế bọc, viết `InvocationHandler` giữ được ngữ nghĩa ngoại lệ, nhận diện chuỗi nguyên nhân trong stack trace và đưa ra chính sách rõ ràng khi checked exception không nằm trong chữ ký API. Ví dụ sử dụng **Java 17+**.

## 1. Bối cảnh: lời gọi đi qua hai tầng

Dynamic Proxy của JDK dựa trên interface và `InvocationHandler`:

~~~text
Caller
  |
  | proxy.load("42")
  v
JDK Proxy: phương thức load(...)
  |
  | InvocationHandler.invoke(proxy, method, args)
  v
Handler
  |
  | Method.invoke(target, args)
  v
Target.load(...) ------------------> ném FileNotFoundException
  |
  | Reflection bọc exception của target
  v
InvocationTargetException
  |
  | handler gỡ bọc bằng getCause()
  v
FileNotFoundException
  |
  | Proxy kiểm tra ngoại lệ handler ném có hợp lệ
  v
Caller nhận FileNotFoundException nếu interface khai báo IOException
~~~

Nếu handler **không gỡ** `InvocationTargetException`, proxy có thể nhìn thấy chính lớp checked exception `InvocationTargetException` — không phải `FileNotFoundException` bên trong. Với interface chỉ khai báo `throws IOException`, `InvocationTargetException` không phải subtype của `IOException`, nên proxy sẽ bọc tiếp:

~~~text
UndeclaredThrowableException
  -> InvocationTargetException
       -> FileNotFoundException
~~~

Ngay cả khi handler đã gỡ đúng `InvocationTargetException`, nếu interface **không có** `throws IOException`, một `IOException` vẫn là checked exception không được khai báo và proxy sẽ có thể tạo:

~~~text
UndeclaredThrowableException
  -> IOException
~~~

Sự khác biệt của hai cây nguyên nhân này là trọng tâm khi gỡ lỗi proxy động.

## 2. InvocationTargetException: cơ chế của Method.invoke

`java.lang.reflect.Method.invoke(Object receiver, Object... args)` gọi một phương thức qua Reflection. Nếu **code bên trong phương thức đích** ném `Throwable`, lời gọi phản xạ sẽ ném `InvocationTargetException` chứa ngoại lệ đó.

Ví dụ code khái niệm:

~~~java
public static class Reader {
    public String read(String id) throws java.io.IOException {
        throw new java.io.IOException("not found: " + id);
    }
}
~~~

Lời gọi phản xạ:

~~~java
Method method = Reader.class.getMethod("read", String.class);
try {
    method.invoke(new Reader(), "A1");
} catch (InvocationTargetException wrapper) {
    Throwable original = wrapper.getCause();
    // original là IOException với message "not found: A1".
}
~~~

Hai đoạn trên **minh họa**, chưa phải chương trình chạy độc lập: cần khai báo class/method bao chứa và các import từ `java.lang.reflect`. Phần `Method.invoke` không thay đổi bản chất của lỗi nghiệp vụ, chỉ bọc nó để phân biệt “phương thức được gọi đã ném lỗi” với “chính thao tác Reflection không thực hiện được”.

Các API đọc nguyên nhân:

- `wrapper.getCause()`: trả ngoại lệ đích, theo `Throwable.getCause()`.
- `wrapper.getTargetException()`: API chuyên biệt của `InvocationTargetException`, về mục đích này cũng cho ngoại lệ đích.
- `wrapper.getClass().getSimpleName()`: trả tên của **lớp bọc**, không phải lỗi nghiệp vụ thật.

**Phân biệt quan trọng:** không phải mọi ngoại lệ khi gọi `Method.invoke` đều được bọc thành `InvocationTargetException`. Ví dụ `IllegalAccessException` khi caller không đủ quyền là lỗi của **lớp Reflection**, còn `IllegalArgumentException` có thể xuất hiện khi truyền receiver/arguments sai. Lỗi tra cứu `NoSuchMethodException` phát sinh từ `getMethod`/`getDeclaredMethod`, không phải từ thân method đích.

Ngay cả khi target ném một `RuntimeException` hoặc `Error`, `Method.invoke` vẫn sử dụng `InvocationTargetException` để bao ngoại lệ **của target**. Vì vậy một handler phản xạ không nên chỉ gỡ bọc với checked exception rồi xử lý unchecked exception theo cách khác; hãy gỡ đúng ngoại lệ đích trước khi áp dụng chính sách API.

## 3. Vì sao phải gỡ bọc ngay trong InvocationHandler?

Phương thức của `InvocationHandler` có chữ ký:

~~~java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
~~~

Nó được JDK Proxy gọi mỗi khi caller gọi một phương thức được proxy. Tham số `method` đại diện cho method của interface (hoặc một số method của `Object`); `args` là mảng các đối số, có thể `null` với phương thức không có tham số.

Một handler chuyển tiếp bằng Reflection thường có dạng:

~~~java
InvocationHandler handler = (proxy, method, args) -> {
    Method targetMethod = target.getClass().getMethod(
            method.getName(), method.getParameterTypes());
    try {
        return targetMethod.invoke(target, args);
    } catch (InvocationTargetException wrapper) {
        throw wrapper.getCause();
    }
};
~~~

Đây là **đoạn minh họa**, cần biến `target` hợp lệ, import `java.lang.reflect.*` và ngữ cảnh tạo proxy. `target.getClass().getMethod(...)` tìm một public method phù hợp với tên và erased parameter types từ interface. Phương thức đích của target **không bắt buộc** là cùng `Method` được truyền từ interface; việc chọn method và tương thích chữ ký là trách nhiệm của handler.

`catch (InvocationTargetException wrapper) { throw wrapper.getCause(); }` có ba ý nghĩa:

1. Không làm lộ lớp bọc Reflection như một checked exception từ handler, nếu nguyên nhân gốc không phải loại đó.
2. Giữ nguyên **kiểu cụ thể**, **message**, **cause chain** và **stack trace** của ngoại lệ nghiệp vụ.
3. Đưa ngoại lệ gốc trở lại ranh giới JDK Proxy để proxy áp dụng đúng hợp đồng checked exception của interface.

**Không dùng `throw wrapper` để “giữ nguyên lỗi gốc”.** Đó là lỗi Reflection wrapper, không phải đối tượng `Throwable` của nghiệp vụ. Cũng tránh `throw new RuntimeException(wrapper)` nếu hợp đồng yêu cầu caller bắt trực tiếp `IOException` hoặc checked exception khác: cách này làm thay đổi API và để lại một tầng bọc không cần thiết.

Tuy nhiên, việc gỡ bọc **không tự cấp quyền** cho một checked exception được thoát ra khỏi mọi phương thức interface; điều đó do quy tắc `throws` ở bước kế tiếp quyết định.

## 4. UndeclaredThrowableException: quy tắc checked exceptions của JDK Proxy

Khi `InvocationHandler.invoke` hoàn thành bằng ngoại lệ, phương thức của proxy động xử lý theo loại ngoại lệ:

| Ngoại lệ handler ném | Interface có khai báo cho phép? | Caller của proxy nhận |
| --- | --- | --- |
| `RuntimeException` (unchecked) | Không cần khai báo `throws` | Chính `RuntimeException` |
| `Error` (unchecked) | Không cần khai báo `throws` | Chính `Error` |
| `FileNotFoundException` | `throws IOException` hoặc supertype phù hợp | Chính `FileNotFoundException` |
| `IOException` | Phương thức không khai báo checked exception | `UndeclaredThrowableException` có `IOException` làm nguyên nhân |
| `InvocationTargetException` | Chỉ `throws IOException` | Thông thường `UndeclaredThrowableException`, vì wrapper không phải `IOException` |
| Checked exception khác | Chỉ khi tương thích với `throws` của phương thức được proxy | Truyền thẳng nếu hợp lệ, nếu không thì bọc `UndeclaredThrowableException` |

**`UndeclaredThrowableException` là một `RuntimeException`**, nên caller không bị yêu cầu khai báo hoặc bắt nó tại compile time. Nó không có nghĩa JVM “bí mật chuyển tất cả ngoại lệ thành RuntimeException”; đây là hành vi bảo vệ hợp đồng checked exceptions của **phương thức proxy**.

`UndeclaredThrowableException` có hai cách lấy ngoại lệ chưa được khai báo:

- `e.getUndeclaredThrowable()`: truy cập trực tiếp checked exception bị bọc.
- `e.getCause()`: cùng chuỗi nguyên nhân thông thường của `Throwable`.

Ví dụ:

~~~java
catch (UndeclaredThrowableException e) {
    Throwable rootAtProxyBoundary = e.getUndeclaredThrowable();
    System.out.println(rootAtProxyBoundary.getClass().getName());
}
~~~

Đây là một **nhánh catch minh họa**, không phải chương trình độc lập. Nếu handler chưa gỡ `InvocationTargetException`, biến `rootAtProxyBoundary` ở đây có thể vẫn là **`InvocationTargetException`**, cần đi thêm một tầng để tìm lỗi đích. Nếu handler đã gỡ đúng nhưng checked exception không nằm trong `throws`, nó có thể chính là `IOException`.

### Quy tắc “hợp lệ” phụ thuộc interface, không phụ thuộc target

Giả sử interface quy định:

~~~java
interface Api {
    String load(String id) throws java.io.IOException;
    void audit();
}
~~~

Handler gọi target phản xạ:

- `load` ném `FileNotFoundException`: `FileNotFoundException extends IOException`, nên sau khi handler gỡ `InvocationTargetException`, proxy cho phép truyền thẳng.
- `audit` ném `IOException`: `audit()` không khai báo checked exception, nên proxy bọc `IOException` thành `UndeclaredThrowableException` nếu handler đẩy thẳng ra ngoài.

Dù implementation của target có khai báo `throws IOException` cho `audit()`, điều đó **không thay đổi** chữ ký `Api.audit()` mà caller đang nhìn thấy.

## 5. Ví dụ Java 17+ hoàn chỉnh: ba kết quả trong cùng một proxy

Tạo file **ProxyExceptionsDemo.java**:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;

public class ProxyExceptionsDemo {
    public interface Service {
        String load(String id) throws IOException;
        void audit();
        String status();
    }

    public static class Target {
        public String load(String id) throws IOException {
            throw new FileNotFoundException("not found: " + id);
        }

        public void audit() throws IOException {
            throw new IOException("audit offline");
        }

        public String status() {
            return "up";
        }
    }

    static Service create(InvocationHandler handler) {
        return (Service) Proxy.newProxyInstance(
                ProxyExceptionsDemo.class.getClassLoader(),
                new Class<?>[] { Service.class },
                handler);
    }

    public static void main(String[] args) {
        Target target = new Target();

        // Cách đúng: giải bọc lỗi đích từ Method.invoke.
        InvocationHandler correct = (proxy, method, actualArgs) -> {
            Method implementation = Target.class.getMethod(
                    method.getName(), method.getParameterTypes());
            try {
                return implementation.invoke(target, actualArgs);
            } catch (InvocationTargetException wrapper) {
                throw wrapper.getCause();
            }
        };

        Service safe = create(correct);
        System.out.println("status: " + safe.status());

        try {
            safe.load("a");
        } catch (IOException ex) {
            System.out.println("declared: " +
                    ex.getClass().getSimpleName() + " | " + ex.getMessage());
        }

        try {
            safe.audit();
        } catch (UndeclaredThrowableException ex) {
            Throwable cause = ex.getUndeclaredThrowable();
            System.out.println("undeclared wrapper: " +
                    ex.getClass().getSimpleName());
            System.out.println("undeclared cause: " +
                    cause.getClass().getSimpleName());
        }

        // Cách sai có chủ đích: làm lộ InvocationTargetException.
        InvocationHandler raw = (proxy, method, actualArgs) -> {
            Method implementation = Target.class.getMethod(
                    method.getName(), method.getParameterTypes());
            return implementation.invoke(target, actualArgs);
        };

        Service wrong = create(raw);
        try {
            wrong.load("b");
        } catch (UndeclaredThrowableException ex) {
            Throwable inner = ex.getUndeclaredThrowable();
            System.out.println("bad inner: " +
                    inner.getClass().getSimpleName());
            System.out.println("bad root: " +
                    ((InvocationTargetException) inner)
                            .getCause().getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac ProxyExceptionsDemo.java
java ProxyExceptionsDemo
~~~

Stdout dự kiến:

~~~text
status: up
declared: FileNotFoundException | not found: a
undeclared wrapper: UndeclaredThrowableException
undeclared cause: IOException
bad inner: InvocationTargetException
bad root: FileNotFoundException
~~~

### Vì sao từng dòng xuất hiện?

**`status`:** target trả chuỗi thông thường; `Method.invoke` trả kết quả, handler trả lại, proxy chuyển về `String` theo chữ ký interface.

**`load("a")` với handler đúng:** target ném `FileNotFoundException`, Reflection bọc thành `InvocationTargetException`, handler ném lại `getCause()`. Interface `Service.load` khai báo `throws IOException` nên proxy truyền nguyên `FileNotFoundException`; catch `IOException` ở caller bắt được nó. Lỗi không biến thành `UndeclaredThrowableException`.

**`audit()` với handler đúng:** target ném `IOException`, handler đã giải bọc đúng thành `IOException`, nhưng `Service.audit()` **không** có `throws IOException`. Proxy phải giữ hợp đồng interface nên bọc thành `UndeclaredThrowableException`; `getUndeclaredThrowable()` trả `IOException`.

**`load("b")` với handler sai:** handler chỉ trả kết quả `Method.invoke`, không bắt `InvocationTargetException`. Proxy nhận `InvocationTargetException` như một checked exception thoát ra từ handler. `Service.load` chỉ khai báo `IOException` và không cho phép `InvocationTargetException`, nên proxy bọc thành `UndeclaredThrowableException`. Vì vậy nguyên nhân trực tiếp của `UTE` là `InvocationTargetException`, còn `FileNotFoundException` nằm sâu thêm một tầng.

Chương trình cố tình không gọi `equals`, `hashCode` hoặc `toString` trên proxy. Các lời gọi `Object` này cũng có thể được `InvocationHandler` chuyển tiếp và đòi chính sách riêng nếu xây handler tái sử dụng trong framework.

## 6. Giải bọc đúng một lớp và đi qua chuỗi nguyên nhân

Khi đã bắt được `InvocationTargetException`, code xử lý bình thường là:

~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException e) {
    throw e.getCause();
}
~~~

Đoạn này là **mã minh họa** đặt trong `InvocationHandler.invoke` hoặc lambda handler có thể ném `Throwable`. Đừng ép `getCause()` thành `Exception`: target có thể ném cả `Error`, và `InvocationHandler.invoke` khai báo `throws Throwable`.

Nếu đứng ở bên **caller** và bắt được `UndeclaredThrowableException`, không nên mặc định chỉ có một lớp bọc. Với chain:

~~~text
UTE
 ├── trực tiếp: IOException
 └── hoặc: InvocationTargetException
               └── IOException / RuntimeException / Error khác
~~~

Việc mở nguyên nhân để **chẩn đoán** có thể sử dụng một hàm nhỏ:

~~~java
static Throwable unwrapOne(Throwable error) {
    if (error instanceof InvocationTargetException e
            && e.getCause() != null) {
        return e.getCause();
    }
    if (error instanceof UndeclaredThrowableException e
            && e.getUndeclaredThrowable() != null) {
        return e.getUndeclaredThrowable();
    }
    return error;
}
~~~

Hàm trên là **một phương thức minh họa**, cần import hai loại exception và đặt trong class. Nếu muốn lần theo nhiều tầng, có thể gọi lặp khi kết quả mới khác đối tượng cũ; tuy nhiên code production phải kiểm soát vòng lặp và giữ dấu vết tầng lỗi phục vụ log.

**Không xóa mọi wrapper một cách mù quáng.** Đôi khi `UndeclaredThrowableException` là thông tin quan trọng rằng interface và implementation có **hợp đồng ngoại lệ không khớp**. `InvocationTargetException` có thể đến từ một API Reflection mà caller thực sự cần biết. Hàm “unwrap one” phù hợp để quan sát hoặc để giải bọc tại ranh giới đã được thiết kế, không phải lý do để xóa sạch toàn bộ ngữ nghĩa exception ở mọi tầng hệ thống.

### Khi nào nên dùng getCause?

- **Trong handler gọi `Method.invoke`:** bắt **đúng `InvocationTargetException`**, ném lại nguyên nhân `getCause()` để proxy tự xét hợp đồng checked exception.
- **Trong caller bắt `UndeclaredThrowableException`:** dùng `getUndeclaredThrowable()` hoặc `getCause()` để biết ngoại lệ nào thực sự thoát khỏi handler; kiểm tra thêm nó có phải `InvocationTargetException` hay không.
- **Khi báo lỗi hệ thống:** giữ chuỗi nguyên nhân để quan sát toàn bộ các ranh giới Reflection/Proxy, tránh log mỗi `e.toString()` rồi mất bối cảnh.

## 7. Ba chiến lược khi checked exception không được interface khai báo

Khi handler đã có ngoại lệ gốc, quyết định tiếp theo là **hợp đồng API muốn làm gì**.

### A. Khai báo checked exception trên interface (khi có quyền thiết kế)

~~~java
public interface FileApi {
    String read(String path) throws java.io.IOException;
}
~~~

Nếu đây là API nghiệp vụ thực sự phát sinh lỗi I/O, khai báo `throws IOException` thường tự nhiên. Handler gỡ Reflection wrapper và ném lại `IOException`; caller được yêu cầu xử lý hoặc khai báo tiếp. Ưu điểm là mất mát thông tin ít, hợp đồng rõ.

Nhưng **thay đổi `throws` trên public interface không phải lúc nào cũng khả thi** khi API đã được phát hành hoặc implement ở nhiều nơi. Việc bổ sung checked exception có thể làm ảnh hưởng mã gọi. Cân nhắc khả năng tương thích, không thêm `throws Throwable` đại trà chỉ để “dập” `UndeclaredThrowableException`.

### B. Chuyển thành unchecked exception có chủ đích

Nếu interface là API không cho phép checked exception, có thể dịch ngoại lệ gốc sang unchecked exception có ý nghĩa:

~~~java
catch (InvocationTargetException wrapper) {
    Throwable cause = wrapper.getCause();
    if (cause instanceof java.io.IOException io) {
        throw new java.io.UncheckedIOException("read failed", io);
    }
    if (cause instanceof RuntimeException runtime) {
        throw runtime;
    }
    if (cause instanceof Error error) {
        throw error;
    }
    throw new IllegalStateException("unexpected checked failure", cause);
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. `UncheckedIOException` là một `RuntimeException` chuyên biệt để bao `IOException` và vẫn giữ `IOException` trong `getCause()`. Với ngoại lệ nghiệp vụ khác, có thể dùng custom unchecked exception có tên phù hợp domain, thay vì biến tất cả thành `IllegalStateException`.

Những điểm nên tuân thủ:

- Chuyển đổi **một cách có chủ đích và nhất quán** giữa interface và target.
- Giữ nguyên ngoại lệ unchecked hoặc `Error` khi không có lý do đặc biệt để biến đổi.
- Giữ `cause` gốc để phục vụ chẩn đoán.
- Không hứa một API “không bao giờ lỗi” chỉ vì đã chuyển checked sang unchecked.

### C. Để proxy bọc bằng UndeclaredThrowableException và xử lý ở biên

Một framework không kiểm soát toàn bộ interface có thể chọn ném lại checked exception gốc và để proxy tạo `UndeclaredThrowableException`. Caller có thể bắt UTE rồi đọc `getUndeclaredThrowable()`. Cách này diễn tả đúng hành vi của JDK nhưng thường **khó dùng** khi caller không mong đợi UTE; vì vậy cần tài liệu, logging và test rõ. Không nên coi UTE là một cơ chế chuyển đổi nghiệp vụ tùy tiện nếu có thể thiết kế API minh bạch hơn.

## 8. Ví dụ Java 17+ hoàn chỉnh: dịch IOException thành UncheckedIOException

Tạo file **ProxyPolicyDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ProxyPolicyDemo {
    public interface Port {
        String read(String key);
    }

    public static class LegacyStore {
        public String read(String key) throws IOException {
            if ("ok".equals(key)) {
                return "data:ok";
            }
            throw new IOException("storage unavailable");
        }
    }

    public static void main(String[] args) {
        LegacyStore legacy = new LegacyStore();

        InvocationHandler handler = (proxy, method, actualArgs) -> {
            Method targetMethod = LegacyStore.class.getMethod(
                    method.getName(), method.getParameterTypes());
            try {
                return targetMethod.invoke(legacy, actualArgs);
            } catch (InvocationTargetException wrapper) {
                Throwable cause = wrapper.getCause();

                if (cause instanceof IOException io) {
                    throw new UncheckedIOException("read failed", io);
                }
                if (cause instanceof RuntimeException re) {
                    throw re;
                }
                if (cause instanceof Error err) {
                    throw err;
                }
                throw new IllegalStateException(
                        "unexpected checked failure", cause);
            }
        };

        Port port = (Port) Proxy.newProxyInstance(
                ProxyPolicyDemo.class.getClassLoader(),
                new Class<?>[] { Port.class },
                handler);

        System.out.println("success: " + port.read("ok"));

        try {
            port.read("bad");
        } catch (UncheckedIOException ex) {
            System.out.println("mapped: " +
                    ex.getClass().getSimpleName());
            System.out.println("cause: " +
                    ex.getCause().getClass().getSimpleName());
            System.out.println("detail: " +
                    ex.getCause().getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ProxyPolicyDemo.java
java ProxyPolicyDemo
~~~

Stdout dự kiến:

~~~text
success: data:ok
mapped: UncheckedIOException
cause: IOException
detail: storage unavailable
~~~

**Điều đã thay đổi:** `Port.read` không khai báo checked exception, nhưng target `LegacyStore.read` có thể ném `IOException`. Handler bắt `InvocationTargetException`, lấy đúng `IOException` gốc và chuyển sang `UncheckedIOException` (subtype của `RuntimeException`). Proxy truyền unchecked exception trực tiếp cho caller, **không cần tạo `UndeclaredThrowableException`**. Caller vẫn có thể đọc nguyên nhân I/O và thông điệp lỗi.

Cách này không làm `IOException` biến mất khỏi hệ thống; nó làm **hợp đồng lỗi** của proxy rõ ràng theo dạng unchecked. Khi có nhu cầu nghiệp vụ khác, dùng ngoại lệ được đặt tên theo domain thay vì `UncheckedIOException`, nhưng luôn giữ cause gốc.

## 9. Khi gỡ bọc không thành công: phân biệt lỗi của target và lỗi Reflection

Các API liên quan nằm ở hai giai đoạn khác nhau:

| Vị trí xảy ra | Loại lỗi có thể gặp | Diễn giải đúng |
| --- | --- | --- |
| `Target.class.getMethod(...)` | `NoSuchMethodException` | Không tìm thấy public method phù hợp tên và erased parameter types |
| `targetMethod.invoke(...)` trước khi chạy đích | `IllegalAccessException`, `IllegalArgumentException` | Không đủ quyền, sai receiver hoặc argument, vấn đề Reflection |
| Bên trong code đích | Bất kỳ lỗi nghiệp vụ nào | `Method.invoke` bọc thành `InvocationTargetException` |
| Handler ném checked ngoại lệ ngoài `throws` interface | `UndeclaredThrowableException` | Proxy bảo vệ hợp đồng checked exceptions |
| Handler ném RuntimeException/Error | Ngoại lệ đi thẳng | Proxy không bắt buộc bọc unchecked |
| Caller gọi proxy nhưng handler trả dữ liệu không đúng kiểu return | `ClassCastException` hoặc lỗi unboxing | Handler thực hiện xong nhưng kết quả không phù hợp chữ ký proxy |

Không nên viết:

~~~java
try {
    return targetMethod.invoke(target, args);
} catch (Exception e) {
    throw new RuntimeException(e);
}
~~~

Đoạn này là **ví dụ lỗi thiết kế**: nếu target ném một `IOException` được interface cho phép, code lại bọc nó trong `RuntimeException` chứa `InvocationTargetException`, khiến caller không còn bắt được `IOException` theo hợp đồng. Nó còn dễ trộn lỗi nghiệp vụ với `IllegalAccessException` hay `NoSuchMethodException` của chính hạ tầng Reflection.

Cách hợp lý là bắt `InvocationTargetException` riêng để xử lý nguyên nhân đích, còn lỗi tra cứu/quyền truy cập được xử lý theo chính sách của hệ thống, có thể chuyển thành lỗi cấu hình rõ ràng khi chúng thực sự là bất thường không thể phục hồi.

### Interface, method overload và việc ánh xạ sang target

`InvocationHandler.invoke` cung cấp `Method` thuộc khai báo proxy (thường thuộc interface), không bảo đảm `method.invoke(target, args)` hợp lệ nếu `target` **không implement chính interface đó**. Trong hai demo, target có phương thức cùng tên và tham số nhưng không implement interface, nên handler chủ động tìm `Method` tương ứng trên class target.

Nếu target thực sự implement interface, gọi `method.invoke(target, args)` là một lựa chọn phổ biến. Nhưng nếu đang gọi proxy như target hoặc vô tình truyền chính `proxy` vào `Method.invoke`, có thể gây **đệ quy vô hạn** qua handler. Luôn xác định đối tượng đích thật, tránh gọi lặp lại proxy trên chính đường chuyển tiếp.

Khi mapping bằng tên và parameter types, còn cần kiểm tra return type, overload, generic erasure và khả năng có nhiều interface khai báo method trùng chữ ký. Một handler trong framework nên có quy tắc mapping rõ hơn “tên trùng là đủ”.

## 10. Trường hợp interface có nhiều phương thức / nhiều interface

Java cho phép một proxy implement nhiều interface cùng lúc. Hai interface có thể có method trùng tên và danh sách tham số nhưng khác danh sách `throws`. Khi xử lý cùng một signature được hợp nhất trong proxy, checked exception thoát ra phải hợp lệ theo quy tắc của **tất cả các khai báo liên quan** — về trực giác là tập checked exceptions được cho phép **chung** chứ không phải hợp của mọi `throws`.

Ví dụ ý tưởng:

~~~java
interface A {
    void process() throws java.io.IOException;
}
interface B {
    void process();
}
~~~

Một proxy implement cả `A` và `B` không thể tự cho phép `IOException` chỉ vì `A` khai báo nó, trong khi `B.process()` không khai báo checked exception. Nếu handler ném `IOException` cho chữ ký chung đó, lớp proxy sẽ có thể dùng `UndeclaredThrowableException`. Việc tham số `Method` được truyền tới handler thuộc interface nào còn chịu quy tắc chọn method của JDK Proxy khi các khai báo trùng nhau; không dùng `method.getDeclaringClass()` để suy ra rằng người gọi chỉ “đi qua một interface” và có quyền nhận checked exception theo riêng interface đó.

Các tình huống có `throws Exception`, `throws IOException` hay nhiều checked exceptions giao nhau cần được review kỹ khi thiết kế proxy kết hợp nhiều interface. Tốt nhất thống nhất hợp đồng ngoại lệ ngay ở các interface.

## 11. Một số hiểu lầm về exception và dynamic proxy

### “Handler khai báo throws Throwable nên có thể ném bất cứ thứ gì cho caller”

`InvocationHandler.invoke` **được phép ném `Throwable` tại tầng handler**, nhưng phương thức interface được JDK Proxy triển khai vẫn có **hợp đồng checked exceptions**. Proxy phải quyết định loại nào truyền thẳng và loại nào bọc thành UTE. Hai chữ ký này ở hai tầng khác nhau, không thể thay thế nhau.

### “Đã throw e.getCause() thì sẽ không còn UTE”

Không đúng. `throw e.getCause()` chỉ giải bọc **Reflection exception**. Nếu cause là checked exception ngoài `throws` của method interface, proxy vẫn có thể tạo UTE. Điều đó là **hành vi đúng** của JDK Proxy chứ không phải lỗi của `getCause()`.

### “UTE chắc chắn chứa InvocationTargetException”

Không đúng. UTE có thể trực tiếp chứa `IOException` hoặc checked exception khác nếu handler đã giải bọc hoặc tự ném chúng. Chỉ dựa vào `e.getUndeclaredThrowable()` để xem thực tế, sau đó mới quyết định có cần đọc thêm `InvocationTargetException.getCause()`.

### “Method.invoke chỉ bọc checked exception”

Không đúng. Nó bọc **ngoại lệ do phương thức đích ném**, kể cả unchecked hoặc `Error`. Còn lỗi xảy ra trước khi method đích thực thi có thể thuộc nhóm ngoại lệ Reflection khác.

### “Bắt UTE rồi ép cause thành IOException là luôn an toàn”

Không đúng. `getUndeclaredThrowable()` có thể là `InvocationTargetException` hoặc bất kỳ checked `Throwable` không tương thích. Nên kiểm tra `instanceof` trước khi cast và ghi log đầy đủ. Tránh dựa vào một cấu trúc chain giả định duy nhất.

### “Cứ thêm throws Exception vào interface là giải quyết tốt”

Khai báo `throws Exception` có thể mở rộng tập checked exceptions hợp lệ và thay đổi nghĩa API/cách caller xử lý. Nhưng đây là quyết định thiết kế giao diện, không phải sửa lỗi tùy tiện. Với API ổn định, chỉ nên khai báo những ngoại lệ thực sự thuộc hợp đồng nghiệp vụ.

## 12. Bảng xử lý theo từng tình huống thực tế

| Trường hợp | Hành động tại handler | Hành động tại caller |
| --- | --- | --- |
| Target ném subtype của checked exception đã khai báo | Bắt ITE, `throw getCause()` | Bắt checked exception theo interface |
| Target ném `RuntimeException` | Bắt ITE, ném lại cause | Xử lý unchecked theo nghiệp vụ |
| Target ném `Error` | Bắt ITE, chuyển tiếp Error; không nuốt | Không dùng catch bao trùm để che lỗi hệ thống |
| Target ném checked exception không có trong interface | Gỡ ITE rồi chọn: map sang unchecked, thay đổi interface hợp lệ hoặc cho proxy tạo UTE | Bắt lỗi theo chính sách được tài liệu hóa |
| Caller nhận UTE chứa ITE | Điều tra handler còn chuyển tiếp wrapper Reflection | Caller đọc UTE → ITE → cause, sửa handler về đúng thiết kế |
| Caller nhận UTE chứa trực tiếp IOException | Handler đã gỡ ITE nhưng interface không cho phép IOException | Xem xét hợp đồng `throws` hoặc chuyển lỗi có chủ đích |
| Lỗi NoSuchMethod/IllegalAccess ở Reflection | Không coi là business exception | Ghi stage, class, method signature và nguyên nhân |
| Handler proxy được gọi cho `equals`/`hashCode`/`toString` | Định nghĩa chính sách xử lý riêng hoặc chuyển tiếp đúng | Tránh giả định đây là method nghiệp vụ bình thường |

**Giới hạn quan trọng:** Handler viết như những demo trên cố ý đơn giản để minh họa exception. Một proxy framework hoàn chỉnh thường cần thêm chính sách cho `Object` methods, method mặc định trên interface, tính năng annotation, transaction, logging và ranh giới classloader/module. Những chức năng đó không thay đổi hai cơ chế bọc cốt lõi đã học.

## 13. Logging, chẩn đoán và kiểm thử exception chain

Khi production log chỉ hiện `UndeclaredThrowableException`, lỗi dễ bị gán nhầm là “JDK Proxy hỏng”. Một quy trình quan sát tốt là:

1. Ghi nhận **interface method** được gọi và tập checked exceptions khai báo (`Method.getExceptionTypes()`).
2. Nếu thấy UTE, đọc `getUndeclaredThrowable()` và kiểm tra kiểu.
3. Nếu nguyên nhân này là ITE, đọc tiếp `getCause()` để tìm ngoại lệ target.
4. Xác định handler có sử dụng `Method.invoke` và có catch riêng `InvocationTargetException` hay không.
5. So sánh checked exception gốc với `throws` hợp lệ của phương thức được proxy (đặc biệt nếu proxy implement nhiều interface có method trùng nhau).
6. Chỉ sau đó chọn sửa handler, sửa hợp đồng interface hay chuyển ngoại lệ theo domain; không chỉ bắt UTE ở UI rồi âm thầm bỏ qua.

Khi log, nên giữ **full throwable/cause chain** thay vì chỉ in message. Message trống không có nghĩa exception vô hại. Đồng thời không vô tình ghi mật khẩu, token hoặc dữ liệu nhạy cảm trong đối số method; log class/method cùng trace phù hợp và áp dụng quy tắc bảo vệ thông tin.

### Các ca kiểm thử nên có

| Ca | Handler nhận từ target | Hợp đồng interface | Kết quả mong đợi |
| --- | --- | --- | --- |
| Return bình thường | Không có exception | Bất kỳ | Caller nhận đúng kết quả |
| Checked hợp lệ | `FileNotFoundException` sau unwrap | `throws IOException` | Caller bắt `IOException` trực tiếp |
| Checked không hợp lệ | `IOException` sau unwrap | Không khai báo checked | Caller nhận UTE, cause là IOException |
| Quên unwrap | `InvocationTargetException` | `throws IOException` | Caller nhận UTE, cause là ITE |
| Runtime exception | `IllegalStateException` sau unwrap | Không khai báo | Caller nhận chính IllegalStateException |
| Target throws Error | `AssertionError` sau unwrap | Không khai báo | Caller nhận Error nếu handler truyền thẳng |
| Handler tự map | `IOException` thành `UncheckedIOException` | Không khai báo checked | Caller nhận UncheckedIOException |
| Reflection mapping sai | `NoSuchMethodException` | Bất kỳ | Lỗi hạ tầng được phân loại rõ, không gọi nhầm là business exception |

Một test tốt nên kiểm tra bằng **`instanceof`** và **cause chain** thay vì chỉ so sánh chuỗi error message. Với hai chương trình mẫu, số dòng stdout cố định nên có thể dùng làm smoke test ở môi trường Java 17+.

## 14. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** `Method.invoke` gọi target ném `IOException`. Lời gọi Reflection trực tiếp ném gì?  
**Đáp án:** `InvocationTargetException`; `getCause()` là `IOException`.

**Câu 2.** Interface có `read() throws IOException`. Handler gỡ ITE và ném `FileNotFoundException`. Caller nhận gì?  
**Đáp án:** Chính `FileNotFoundException` vì nó kế thừa `IOException`, là checked exception được hợp đồng interface cho phép.

**Câu 3.** Interface `void audit()` không khai báo checked exception. Handler ném `IOException`. Caller nhận gì?  
**Đáp án:** Thông thường là `UndeclaredThrowableException`; `getUndeclaredThrowable()` là `IOException`.

**Câu 4.** Vì sao handler không gỡ ITE có thể tạo UTE ngay cả khi interface khai báo `throws IOException`?  
**Đáp án:** Vì proxy thấy `InvocationTargetException` (checked) chứ không thấy cause `IOException`. `InvocationTargetException` không phải subtype của `IOException`.

**Câu 5.** `UndeclaredThrowableException` có thể chứa trực tiếp `IOException` không?  
**Đáp án:** Có. Đó là trường hợp handler đã giải bọc ITE hoặc tự ném `IOException` nhưng interface không khai báo cho phép.

**Câu 6.** Có nên catch `Exception` quanh toàn bộ Reflection rồi `throw new RuntimeException(e)` không?  
**Đáp án:** Không nên nếu muốn bảo toàn hợp đồng checked exceptions. Cần phân biệt lỗi target (ITE) và lỗi hạ tầng Reflection, rồi xử lý từng nhóm.

**Câu 7.** `RuntimeException` hoặc `Error` đi qua handler có bị proxy tự bọc thành UTE không?  
**Đáp án:** Không, theo quy tắc JDK Proxy chúng được chuyển tiếp trực tiếp. Nếu chúng xuất phát từ `Method.invoke`, handler vẫn phải gỡ ITE trước.

**Câu 8.** Khi nào `UncheckedIOException` hợp lý?  
**Đáp án:** Khi API không khai báo checked `IOException` và thiết kế có chủ đích muốn chuyển lỗi I/O thành unchecked, vẫn giữ `IOException` gốc trong `getCause()`.

**Câu 9.** Nếu target method khai báo `throws IOException` nhưng interface proxy không khai báo, target declaration có tự cho proxy quyền ném IOException không?  
**Đáp án:** Không. Proxy thực thi hợp đồng của **interface**, không lấy danh sách `throws` từ method implementation của target.

**Câu 10.** Một proxy implement hai interface có method trùng chữ ký, một nơi có `throws IOException` và nơi kia không có, có được bảo đảm truyền IOException trực tiếp không?  
**Đáp án:** Không. Quy tắc checked exceptions cho chữ ký trùng cần tương thích với các khai báo liên quan; nên thống nhất chính sách throws hoặc chuyển lỗi có chủ đích.

**Câu 11.** `getCause()` và `getUndeclaredThrowable()` khác nhau thế nào trên UTE?  
**Đáp án:** Cả hai cho truy cập nguyên nhân chưa được khai báo; `getUndeclaredThrowable()` thể hiện rõ mục đích chuyên biệt của UTE.

**Câu 12.** Nếu caller bắt UTE rồi chỉ in `e.getMessage()`, điều gì có thể bị bỏ lỡ?  
**Đáp án:** Kiểu của checked exception gốc, tầng Reflection `InvocationTargetException` có thể có, stack trace và bối cảnh hợp đồng throws bị vi phạm.

## 15. Kết luận và checklist triển khai

- **`InvocationTargetException` thuộc tầng Reflection:** `Method.invoke` bọc exception do target ném. Trong handler gọi phản xạ, bắt riêng ITE rồi dùng **`throw wrapper.getCause()`** khi muốn chuyển đúng ngoại lệ target.
- **`UndeclaredThrowableException` thuộc tầng Proxy:** xảy ra khi handler ném checked exception không được method interface cho phép. **Gỡ ITE đúng không đồng nghĩa UTE chắc chắn biến mất**.
- **Kiểm tra hợp đồng interface:** các checked exceptions truyền thẳng phải là loại được `throws` cho phép; unchecked `RuntimeException` và `Error` được truyền trực tiếp.
- **Chọn chính sách nhất quán:** khai báo checked exception phù hợp khi thiết kế được API; nếu API không cho phép thì có thể map sang unchecked exception có nghĩa và giữ cause; hoặc tài liệu hóa hành vi UTE.
- **Phân biệt lỗi nghiệp vụ với lỗi hạ tầng Reflection:** `NoSuchMethodException`, `IllegalAccessException`, sai receiver/args không phải chính là lỗi từ target.
- **Gỡ đúng số tầng:** UTE có thể chứa ITE hoặc chứa trực tiếp IOException. Đọc `getUndeclaredThrowable()`, `getCause()` và quan sát toàn bộ exception chain.
- **Kiểm thử có hệ thống:** target trả bình thường, checked hợp lệ, checked không hợp lệ, không unwrap, unchecked, Error và chính sách mapping; kiểm tra loại exception, cause, message thay vì chỉ kiểm tra một dòng log.

Hiểu rõ **ai tạo wrapper, tại ranh giới nào, và vì sao** giúp thiết kế Dynamic Proxy giữ đúng contract, bảo toàn nguyên nhân lỗi và tránh tình trạng code chỉ nhìn thấy `UndeclaredThrowableException` mà không biết ngoại lệ nghiệp vụ thật nằm ở đâu.
