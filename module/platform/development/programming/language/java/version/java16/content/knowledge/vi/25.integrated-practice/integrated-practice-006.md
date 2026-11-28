# Viết proxy bổ sung logging nhưng giữ nguyên default method

Trong Java, dynamic proxy cho phép tạo một object thực thi một hoặc nhiều interface và chuyển các lời gọi phương thức tới `InvocationHandler`. Đây là cách hữu ích để bổ sung logging, đo thời gian, kiểm tra quyền hoặc tracing mà không sửa class triển khai interface.

Một điểm cần xử lý rõ ràng là default method. Khi một phương thức mặc định được gọi trên proxy, lời gọi vẫn đi qua `InvocationHandler.invoke()`. Nếu handler không gọi phần triển khai default method, hành vi mặc định sẽ không tự chạy. Từ Java 16, API `InvocationHandler.invokeDefault()` cho phép handler gọi trực tiếp phần triển khai default method trên proxy một cách chính thức.

Bài thực hành xây dựng một proxy cho dịch vụ tài khoản. Proxy ghi log thời gian gọi, chuyển phương thức abstract tới object thật và thực thi default method bằng `InvocationHandler.invokeDefault()`. Default method gọi lại phương thức abstract để minh họa rằng lời gọi nội bộ đó tiếp tục đi qua proxy và được logging.

## 1. Mục tiêu thực hành

Hoàn thành bài này, bạn sẽ:

- Tạo dynamic proxy bằng `Proxy.newProxyInstance()`.
- Viết `InvocationHandler` để xử lý lời gọi interface.
- Bổ sung log thời gian mà không thay đổi kết quả của phương thức.
- Giữ nguyên hành vi của default method bằng `InvocationHandler.invokeDefault()`.
- Hiểu vì sao default method gọi một phương thức khác trên `this` có thể đi qua proxy lần nữa.
- Xử lý riêng các phương thức `equals()`, `hashCode()` và `toString()`.
- Giữ nguyên exception do object đích ném ra.
- Viết kiểm thử để xác nhận cả hành vi và kết quả trả về.

## 2. Bài toán

Giả sử một ứng dụng có interface `AccountService`. Interface cung cấp một phương thức abstract để tra tên chủ tài khoản và hai default method để tạo nhãn hiển thị.

Yêu cầu là tạo một proxy để ghi nhận phương thức được gọi và thời gian thực thi, đồng thời giữ nguyên kết quả của các default method.

Các điều kiện chấp nhận:

1. Gọi `proxy.ownerName(42)` phải chuyển lời gọi tới object triển khai thật.
2. Gọi `proxy.label(42)` phải chạy phần thân default method.
3. Khi default method `label()` gọi `ownerName()`, lời gọi lồng nhau phải được proxy nhận và ghi log.
4. Giá trị trả về phải giống logic của interface và object đích.
5. Exception từ object đích phải được ném ra dưới dạng exception gốc, không để lộ `InvocationTargetException`.
6. `equals()`, `hashCode()` và `toString()` phải có hành vi được xác định rõ.
7. Không ghi giá trị tham số nhạy cảm vào log.

## 3. Thiết kế interface có default method

Tạo file `AccountService.java`:

~~~java
package example.proxy;

public interface AccountService {
    String ownerName(long accountId);

    default String label(long accountId) {
        return "Account#" + accountId
                + " owner=" + ownerName(accountId);
    }

    default String serviceName() {
        return "AccountService";
    }
}
~~~

`ownerName()` là phương thức abstract. `label()` và `serviceName()` là default method.

Điểm đáng chú ý nằm trong `label()`:

~~~java
return "Account#" + accountId
        + " owner=" + ownerName(accountId);
~~~

Khi `label()` được thực thi với `this` là proxy, lời gọi `ownerName()` cũng đi qua proxy. Handler sẽ nhận hai invocation: một lần cho `label()` và một lần cho `ownerName()`.

Tạo implementation thật trong file `AccountServiceImpl.java`:

~~~java
package example.proxy;

public final class AccountServiceImpl implements AccountService {
    @Override
    public String ownerName(long accountId) {
        return "Customer-" + accountId;
    }
}
~~~

Class triển khai không override hai default method. Bài lab chọn chính sách ưu tiên phần thân default method của interface; các phương thức abstract được chuyển tiếp tới implementation thật.

## 4. Viết LoggingInvocationHandler

Tạo file `LoggingInvocationHandler.java`:

~~~java
package example.proxy;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Objects;

public final class LoggingInvocationHandler
        implements InvocationHandler {

    private static final System.Logger LOGGER =
            System.getLogger(LoggingInvocationHandler.class.getName());

    private final Object target;

    public LoggingInvocationHandler(Object target) {
        this.target = Objects.requireNonNull(target, "target");
    }

    @Override
    public Object invoke(
            Object proxy,
            Method method,
            Object[] args) throws Throwable {

        if (method.getDeclaringClass() == Object.class) {
            return invokeObjectMethod(proxy, method, args);
        }

        Object[] actualArgs = args == null ? new Object[0] : args;
        long startedAt = System.nanoTime();

        LOGGER.log(
                System.Logger.Level.DEBUG,
                "Invoking {0}",
                method.toGenericString());

        try {
            Object result;

            if (method.isDefault()) {
                result = InvocationHandler.invokeDefault(
                        proxy, method, actualArgs);
            } else {
                result = invokeTarget(method, actualArgs);
            }

            return result;
        } catch (Throwable failure) {
            LOGGER.log(
                    System.Logger.Level.WARNING,
                    "Invocation failed: " + method.toGenericString(),
                    failure);
            throw failure;
        } finally {
            long elapsedNanos = System.nanoTime() - startedAt;
            LOGGER.log(
                    System.Logger.Level.DEBUG,
                    "Finished {0} in {1} ns",
                    method.getName(),
                    elapsedNanos);
        }
    }

    private Object invokeTarget(
            Method method,
            Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException exception) {
            Throwable cause = exception.getCause();
            throw cause == null ? exception : cause;
        }
    }

    private Object invokeObjectMethod(
            Object proxy,
            Method method,
            Object[] args) {

        return switch (method.getName()) {
            case "equals" -> proxy == args[0];
            case "hashCode" -> System.identityHashCode(proxy);
            case "toString" ->
                    "LoggingProxy[" + target.getClass().getName() + "]";
            default -> throw new UnsupportedOperationException(
                    method.toGenericString());
        };
    }
}
~~~

### Vì sao handler kiểm tra default method?

Đoạn quan trọng:

~~~java
if (method.isDefault()) {
    result = InvocationHandler.invokeDefault(
            proxy, method, actualArgs);
} else {
    result = invokeTarget(method, actualArgs);
}
~~~

`method.isDefault()` cho biết method có phải default method của interface hay không. `InvocationHandler.invokeDefault()` gọi phần triển khai mặc định tương ứng trên chính proxy.

Đây là API chính thức có từ Java 16. Không cần dùng các kỹ thuật truy cập private lookup hoặc method handle tự xây dựng để gọi default method trong trường hợp thông thường.

### Vì sao không dùng method.invoke(proxy, args)?

Không viết:

~~~java
return method.invoke(proxy, args);
~~~

Nếu `method` đại diện cho phương thức interface trên proxy, `Method.invoke(proxy, ...)` lại gọi phương thức trên proxy. Lời gọi quay trở lại `InvocationHandler.invoke()`, có thể tạo đệ quy vô hạn.

Với default method, dùng `InvocationHandler.invokeDefault(proxy, method, args)`. Với phương thức abstract cần chuyển tới implementation thật, dùng `method.invoke(target, args)`.

### Vì sao phải mở InvocationTargetException?

`Method.invoke()` bọc exception được ném từ phương thức đích trong `InvocationTargetException`. Handler cần ném lại `getCause()` để giữ nguyên exception gốc.

Nếu không mở wrapper này, caller có thể nhìn thấy exception reflection thay vì exception mà API công bố. Proxy runtime cũng có quy tắc riêng: checked exception không được khai báo trong chữ ký interface có thể bị bọc thành `UndeclaredThrowableException`.

### Vì sao xử lý Object methods riêng?

Các lời gọi `equals()`, `hashCode()` và `toString()` trên proxy cũng được chuyển tới handler. Lab chọn identity semantics:

- Proxy chỉ bằng chính nó.
- Hash code dựa trên identity của proxy.
- `toString()` mô tả proxy và loại target, không gọi `target.toString()` để tránh log hoặc gọi đệ quy không mong muốn.

Đây là một chính sách rõ ràng cho proxy. Nếu ứng dụng cần equality theo domain object hoặc muốn ủy quyền các Object method cho target, hãy thiết kế và kiểm thử hợp đồng đó riêng.

## 5. Tạo proxy và chạy thử

Tạo file `ProxyDemo.java`:

~~~java
package example.proxy;

import java.lang.reflect.Proxy;

public final class ProxyDemo {
    public static void main(String[] args) {
        AccountService target = new AccountServiceImpl();

        AccountService proxy = (AccountService) Proxy.newProxyInstance(
                AccountService.class.getClassLoader(),
                new Class<?>[] { AccountService.class },
                new LoggingInvocationHandler(target));

        System.out.println(proxy.ownerName(42));
        System.out.println(proxy.label(42));
        System.out.println(proxy.serviceName());
        System.out.println(proxy);
        System.out.println(proxy.equals(proxy));
        System.out.println(proxy.equals(target));
    }
}
~~~

Kết quả nghiệp vụ:

~~~text
Customer-42
Account#42 owner=Customer-42
AccountService
LoggingProxy[example.proxy.AccountServiceImpl]
true
false
~~~

Log chi tiết phụ thuộc logger configuration. Khi bật mức DEBUG, lần gọi `label(42)` tạo một log cho `label()` và một log lồng nhau cho `ownerName()`.

## 6. Hiểu luồng gọi của default method

Khi gọi:

~~~java
proxy.label(42);
~~~

luồng xử lý là:

~~~text
Caller
  |
  v
Proxy.label(42)
  |
  v
LoggingInvocationHandler.invoke(label)
  |
  v
InvocationHandler.invokeDefault(proxy, label, args)
  |
  v
AccountService.default label()
  |
  | this.ownerName(42)
  v
Proxy.ownerName(42)
  |
  v
LoggingInvocationHandler.invoke(ownerName)
  |
  v
method.invoke(target, args)
  |
  v
AccountServiceImpl.ownerName(42)
~~~

Default method chạy với receiver là proxy. Vì thế lời gọi interface khác từ bên trong default method vẫn đi qua proxy và được handler xử lý.

Đây là điểm khác biệt quan trọng so với việc gọi `method.invoke(target, args)` cho cả default method. Trong trường hợp đó, default method chạy với receiver là target; lời gọi `this.ownerName()` bên trong sẽ đi thẳng tới target và không đi qua proxy.

## 7. Kiểm thử hành vi bằng JUnit Jupiter

Tạo file `LoggingInvocationHandlerTest.java` trong test source set:

~~~java
package example.proxy;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Proxy;
import org.junit.jupiter.api.Test;

class LoggingInvocationHandlerTest {

    private AccountService createProxy(AccountService target) {
        return (AccountService) Proxy.newProxyInstance(
                AccountService.class.getClassLoader(),
                new Class<?>[] { AccountService.class },
                new LoggingInvocationHandler(target));
    }

    @Test
    void delegatesAbstractMethodToTarget() {
        AccountService proxy = createProxy(new AccountServiceImpl());

        assertEquals("Customer-42", proxy.ownerName(42));
    }

    @Test
    void invokesDefaultMethodOnProxy() {
        AccountService proxy = createProxy(new AccountServiceImpl());

        assertEquals(
                "Account#42 owner=Customer-42",
                proxy.label(42));
        assertEquals("AccountService", proxy.serviceName());
    }

    @Test
    void objectMethodsUseIdentitySemantics() {
        AccountService proxy = createProxy(new AccountServiceImpl());
        AccountService anotherProxy =
                createProxy(new AccountServiceImpl());

        assertTrue(proxy.equals(proxy));
        assertFalse(proxy.equals(anotherProxy));
        assertEquals(System.identityHashCode(proxy), proxy.hashCode());
        assertTrue(proxy.toString().startsWith("LoggingProxy["));
    }
}
~~~

Test trên xác nhận kết quả của abstract method, default method và Object methods. Để xác minh chắc chắn lời gọi lồng nhau được handler nhận, có thể bổ sung một test handler ghi lại tên method:

~~~java
@Test
void defaultMethodCallsBackThroughTheProxy() {
    AccountService target = new AccountServiceImpl();
    java.util.List<String> calls = new java.util.ArrayList<>();

    AccountService proxy = (AccountService) Proxy.newProxyInstance(
            AccountService.class.getClassLoader(),
            new Class<?>[] { AccountService.class },
            (currentProxy, method, args) -> {
                calls.add(method.getName());

                if (method.getDeclaringClass() == Object.class) {
                    return switch (method.getName()) {
                        case "equals" -> currentProxy == args[0];
                        case "hashCode" ->
                                System.identityHashCode(currentProxy);
                        case "toString" -> "TestProxy";
                        default -> throw new UnsupportedOperationException();
                    };
                }

                Object[] actualArgs =
                        args == null ? new Object[0] : args;
                if (method.isDefault()) {
                    return java.lang.reflect.InvocationHandler.invokeDefault(
                            currentProxy, method, actualArgs);
                }
                try {
                    return method.invoke(target, actualArgs);
                } catch (java.lang.reflect.InvocationTargetException e) {
                    throw e.getCause();
                }
            });

    assertEquals(
            "Account#7 owner=Customer-7",
            proxy.label(7));
    assertEquals(
            java.util.List.of("label", "ownerName"),
            calls);
}
~~~

Test phụ dùng handler nhỏ để ghi lại thứ tự invocation. Nó chứng minh rằng khi default method gọi `ownerName()` trên `this`, proxy tiếp tục nhận lời gọi thứ hai.

## 8. Bài tập mở rộng

Sau khi hoàn thành phần cơ bản, hãy thử các yêu cầu sau:

### Bài tập A: đo thời gian theo từng method

Thay vì chỉ ghi thời gian từng invocation, hãy lưu thống kê tổng số lần gọi và tổng thời gian theo tên method. Dùng cấu trúc thread-safe nếu nhiều thread cùng gọi proxy.

Yêu cầu:

- Không làm thay đổi kết quả trả về.
- Không giữ reference tới argument hoặc kết quả sau khi invocation kết thúc.
- Có thể xuất thống kê theo method khi ứng dụng yêu cầu.

### Bài tập B: xử lý default method kế thừa

Tạo interface cha:

~~~java
public interface NamedService {
    default String category() {
        return "general";
    }
}
~~~

Cho `AccountService` kế thừa `NamedService`. Kiểm tra rằng `category()` vẫn được handler nhận là default method và có thể gọi bằng `InvocationHandler.invokeDefault()`.

Method object có thể khai báo ở interface cha. Interface khai báo method phải là superinterface hợp lệ của proxy class.

### Bài tập C: nhiều interface có default method trùng chữ ký

Tạo hai interface cùng khai báo default method có cùng tên và tham số. Khi proxy triển khai cả hai, hãy xác định method object nào được truyền tới handler và viết chính sách chọn default method rõ ràng.

Không dựa vào thứ tự gọi qua biến tham chiếu để giả định handler luôn nhận Method từ interface mà caller đang dùng. Với các method trùng signature trong nhiều proxy interface, quy tắc của Proxy có thể cung cấp Method từ interface xuất hiện trước trong danh sách interface.

### Bài tập D: kiểm tra exception

Cho target ném một checked exception được khai báo trong interface. Xác nhận caller nhận exception gốc. Sau đó thử một checked exception không được khai báo và quan sát quy tắc `UndeclaredThrowableException` của proxy.

### Bài tập E: chính sách cho default method bị override

Trong lab cơ bản, handler ưu tiên phần thân default method của interface khi `method.isDefault()` là true. Nếu target class override default method và ứng dụng cần giữ hành vi override đó, hãy điều chỉnh dispatch để gọi target trong trường hợp ấy.

Viết test cho cả hai trường hợp:

- Target không override: default method của interface được thực thi.
- Target có override: proxy thực thi implementation của target theo chính sách đã chọn.

Không thay đổi chính sách một cách ngầm định; ghi rõ hợp đồng của proxy.

## 9. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không xử lý method có `isDefault()` | Default method không chạy theo mong đợi | Gọi `InvocationHandler.invokeDefault()` |
| Gọi `method.invoke(proxy, args)` | Handler có thể tự gọi lại vô hạn | Gọi default method bằng `invokeDefault()` |
| Gọi default method trên target | Lời gọi nội bộ có thể bỏ qua proxy | Gọi default method trên proxy khi cần intercept lời gọi lồng nhau |
| Không mở `InvocationTargetException` | Caller nhận wrapper reflection thay vì exception gốc | Ném lại `getCause()` |
| Log toàn bộ arguments | Có thể làm lộ token, mật khẩu hoặc dữ liệu cá nhân | Chỉ log method, correlation ID và dữ liệu đã sanitize |
| Bỏ qua Object methods | `equals`, `hashCode`, `toString` có thể có semantics bất ngờ | Định nghĩa và kiểm thử chính sách riêng |
| Nghĩ proxy intercept mọi lời gọi trong target | Self-invocation trên target không đi qua proxy | Chỉ các lời gọi đi qua proxy mới được intercept |
| Cho rằng proxy giữ nguyên override của target dù luôn gọi default method | Implementation override có thể bị bỏ qua | Chọn rõ policy: default body hay delegate target |
| Không kiểm tra interface/class loader | Tạo proxy thất bại do interface không nhìn thấy hoặc không hợp lệ | Dùng class loader nhìn thấy toàn bộ interface |

## 10. Giới hạn của JDK dynamic proxy

JDK dynamic proxy chỉ tạo proxy cho interface. Nó không tự tạo subclass để intercept mọi method của một concrete class.

Các điểm cần nhớ:

- Proxy class được tạo động và triển khai các interface được truyền vào.
- Các interface phải nhìn thấy được từ class loader được chọn và đáp ứng các ràng buộc của Proxy API.
- Method gọi qua proxy được chuyển tới handler; lời gọi trực tiếp trên target không được intercept.
- Sealed interface không thể được triển khai tùy ý bởi proxy class được sinh động; hãy kiểm tra giới hạn của Proxy API nếu thiết kế dùng sealed types.
- Các method trùng signature ở nhiều interface có quy tắc chọn Method riêng; không nên dựa vào interface reference của caller.
- Reflection và invocation handler tạo thêm chi phí. Với đường gọi rất nóng, hãy benchmark trước khi áp dụng rộng.

Nếu cần intercept method của class không triển khai interface, cần cân nhắc giải pháp khác như decorator, instrumentation hoặc framework proxy phù hợp. Không biến JDK dynamic proxy thành công cụ thay thế mọi hình thức AOP.

## 11. Logging an toàn và ít gây nhiễu

Logging proxy thường chạy trên đường gọi nghiệp vụ. Vì vậy:

- Không log toàn bộ arguments theo mặc định.
- Không ghi password, access token, session ID, dữ liệu thanh toán hoặc dữ liệu cá nhân.
- Dùng method signature, thời gian và correlation ID đã được kiểm soát.
- Chọn log level phù hợp; DEBUG thường phù hợp cho invocation detail, WARNING/ERROR cho lỗi.
- Dùng `System.nanoTime()` để đo duration, không dùng `System.currentTimeMillis()` làm đồng hồ đo elapsed time.
- Không thực hiện I/O nặng đồng bộ trong handler nếu latency là yêu cầu quan trọng.
- Nếu dùng asynchronous logging, bảo đảm queue có giới hạn và chính sách backpressure/drop rõ ràng.

Ví dụ trong bài chỉ log method signature và duration, không log giá trị tham số.

## 12. Quy trình hoàn thành bài thực hành

1. Tạo interface có một abstract method và ít nhất một default method.
2. Tạo implementation thật cho abstract method.
3. Tạo `LoggingInvocationHandler` với target.
4. Xử lý Object methods riêng.
5. Dùng `InvocationHandler.invokeDefault()` cho default method.
6. Delegate abstract method bằng reflection và mở `InvocationTargetException`.
7. Tạo proxy bằng `Proxy.newProxyInstance()`.
8. Chạy demo để quan sát kết quả và log lồng nhau.
9. Chạy JUnit tests cho abstract method, default method và Object methods.
10. Thử default method kế thừa, exception và interface có method trùng signature.
11. Benchmark nếu proxy được dùng trên hot path.

## 13. Checklist review

- [ ] Proxy chỉ triển khai các interface cần thiết.
- [ ] Handler phân biệt default method và abstract method.
- [ ] Default method được gọi bằng `InvocationHandler.invokeDefault()`.
- [ ] Không gọi `method.invoke(proxy, args)` cho default method.
- [ ] Lời gọi từ default method sang method khác được hiểu và kiểm thử.
- [ ] Abstract method được delegate tới target.
- [ ] `InvocationTargetException` được mở để giữ exception gốc.
- [ ] `equals()`, `hashCode()` và `toString()` có semantics rõ ràng.
- [ ] Logging không làm lộ dữ liệu nhạy cảm.
- [ ] Duration dùng `System.nanoTime()`.
- [ ] Có test cho default method kế thừa và exception.
- [ ] Chính sách khi target override default method được ghi rõ.
- [ ] Đã xác minh class loader và các interface hợp lệ với Proxy API.

## 14. Ghi nhớ

- Mọi lời gọi interface qua JDK dynamic proxy đều đi qua `InvocationHandler`.
- Default method cũng đi qua handler; nó không tự động chạy nếu handler không dispatch tới phần thân mặc định.
- `InvocationHandler.invokeDefault()` có từ Java 16 và là API chính thức để gọi default method trên proxy.
- Default method được gọi trên proxy có thể gọi tiếp method khác và tạo invocation mới qua handler.
- Dùng `Method.invoke(target, args)` cho abstract method cần delegate.
- Mở `InvocationTargetException` để giữ exception gốc của target.
- Xử lý `equals()`, `hashCode()` và `toString()` như một phần của hợp đồng proxy.
- Proxy chỉ intercept lời gọi đi qua proxy; self-invocation trên target không được intercept.
- Không log dữ liệu nhạy cảm và phải đo overhead trước khi dùng proxy trên hot path.
- Chọn rõ default-method policy khi target class cũng override method đó.

Bài thực hành kết hợp dynamic proxy, logging và default method để minh họa một điểm quan trọng từ Java 16: handler có thể gọi phần thân default method bằng API chính thức trong khi vẫn giữ proxy làm receiver. Nhờ vậy, lời gọi lồng nhau trong default method tiếp tục đi qua handler và có thể được quan sát mà không sửa interface hay class nghiệp vụ.

## Tài liệu tham khảo

- [InvocationHandler — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/InvocationHandler.html) — hợp đồng `invoke()` và `invokeDefault()`.
- [Proxy — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Proxy.html) — tạo dynamic proxy và quy tắc chuyển lời gọi tới handler.
- [InvocationHandler — Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/reflect/InvocationHandler.html) — API invokeDefault() được bổ sung từ Java 16.
