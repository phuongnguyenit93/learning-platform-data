# Proxy và InvocationHandler trong Java

## 1. Từ lời gọi interface đến một bộ xử lý chung

Giả sử nhiều thao tác cần ghi log trước và sau khi chạy. Nếu viết phần log vào từng method nghiệp vụ, mã lặp lại và phần nghiệp vụ bị trộn với việc theo dõi lời gọi.

**Proxy động của JDK (dynamic proxy)** tạo một đối tượng triển khai các interface được chọn lúc chạy. Khi mã gọi sử dụng đối tượng ấy qua interface, lời gọi được chuyển đến một bộ xử lý chung: `InvocationHandler`.

Bộ xử lý có thể:

- Thêm hành vi trước hoặc sau lời gọi.
- Ủy quyền cho một đối tượng thật.
- Tự tính kết quả mà không có đối tượng thật.
- Từ chối một thao tác hoặc chuyển đổi lỗi theo hợp đồng interface.

Các vai trò cần giữ riêng:

| Vai trò | Trách nhiệm |
| --- | --- |
| Interface | Hợp đồng mà mã gọi nhìn thấy |
| Proxy instance | Đối tượng nhận lời gọi qua interface |
| InvocationHandler | Quyết định cách xử lý lời gọi đã được mô tả |
| Đối tượng đích, nếu có | Thực hiện nghiệp vụ được handler ủy quyền |

Proxy không mặc nhiên đồng nghĩa với một đối tượng đích ẩn bên trong. Đối tượng đích là một lựa chọn của cách viết handler.

## 2. Cơ chế chuyển lời gọi

Một luồng ủy quyền điển hình:

~~~text
Mã gọi
  -> phương thức trên proxy qua interface
  -> InvocationHandler.invoke(proxy, method, args)
  -> xử lý bổ sung
  -> method.invoke(target, args), nếu chọn ủy quyền
  -> kết quả hoặc ngoại lệ quay lại mã gọi
~~~

Hai API chính:

~~~java
Proxy.newProxyInstance(loader, interfaces, handler)
~~~

Đây là biểu thức minh họa, với các biến đã được chuẩn bị. Phương thức trả về `Object`; mã gọi ép về interface mà proxy được tạo để triển khai.

Handler thực hiện phương thức:

~~~java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable
~~~

Dòng trên biểu diễn chữ ký của `InvocationHandler.invoke`, không phải một phương thức hoàn chỉnh có phần thân.

Ý nghĩa các tham số:

- `proxy`: chính đối tượng proxy đang nhận lời gọi, **không phải đối tượng đích**.
- `method`: metadata của method interface được gọi; lớp khai báo có thể là interface cha mà interface được cung cấp kế thừa method.
- `args`: các đối số, với giá trị primitive được đóng hộp; bằng `null` nếu method không có đối số.

Lấy được một `Method` mô tả lời gọi chưa có nghĩa handler phải dùng Reflection để gọi một đối tượng thật. Handler có thể chọn cách xử lý khác.

## 3. Ví dụ hoàn chỉnh: thêm dấu vết và ủy quyền

Lưu thành `ProxyHandlerDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Objects;

public class ProxyHandlerDemo {
    public interface GreetingService {
        String greet(String name);
        int calls();
    }

    public static final class RealGreetingService
            implements GreetingService {
        private int count;

        @Override
        public String greet(String name) {
            String cleaned = Objects.requireNonNull(name, "name").strip();
            if (cleaned.isEmpty()) {
                throw new IllegalArgumentException("name is blank");
            }
            count++;
            return "Hello, " + cleaned;
        }

        @Override
        public int calls() {
            return count;
        }
    }

    public static final class TracingHandler implements InvocationHandler {
        private final GreetingService target;

        public TracingHandler(GreetingService target) {
            this.target = Objects.requireNonNull(target, "target");
        }

        @Override
        public Object invoke(
                Object proxy,
                Method method,
                Object[] arguments) throws Throwable {

            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreetingProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            System.out.println("enter " + method.getName());
            try {
                return method.invoke(target, arguments);
            } catch (InvocationTargetException exception) {
                throw exception.getCause();
            } finally {
                System.out.println("leave " + method.getName());
            }
        }
    }

    public static void main(String[] args) {
        GreetingService target = new RealGreetingService();
        TracingHandler handler = new TracingHandler(target);

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[] {GreetingService.class},
                handler);

        System.out.println("isProxyClass="
                + Proxy.isProxyClass(service.getClass()));
        System.out.println("handlerMatches="
                + (Proxy.getInvocationHandler(service) == handler));

        System.out.println(service.greet("Lan"));
        System.out.println("calls=" + service.calls());
        System.out.println("toString=" + service);
        System.out.println("equalsSelf=" + service.equals(service));
        System.out.println("equalsTarget=" + service.equals(target));

        try {
            service.greet(" ");
        } catch (IllegalArgumentException exception) {
            System.out.println("error="
                    + exception.getClass().getSimpleName()
                    + ":" + exception.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 ProxyHandlerDemo.java
java ProxyHandlerDemo
~~~

Kết quả:

~~~text
isProxyClass=true
handlerMatches=true
enter greet
leave greet
Hello, Lan
enter calls
leave calls
calls=1
toString=GreetingProxy
equalsSelf=true
equalsTarget=false
enter greet
leave greet
error=IllegalArgumentException:name is blank
~~~

Chương trình chạy tuần tự. `RealGreetingService` giữ số lần chào hợp lệ; ví dụ không xây một bộ đếm đồng thời.

Đọc theo từng bước:

1. `newProxyInstance` tạo một đối tượng triển khai `GreetingService`.
2. `service.greet("Lan")` chuyển thành lời gọi `handler.invoke`.
3. Handler in `enter`, gọi method trên `target`, rồi luôn in `leave` trong `finally`.
4. `calls()` không có tham số, nên mảng đối số của handler là null. `Method.invoke` chấp nhận null để biểu diễn không có đối số.
5. Kết quả `int` của `calls()` được Reflection đóng hộp khi trở về handler, rồi proxy trả lại kết quả phù hợp với kiểu `int` của interface.
6. Khi đối tượng đích từ chối tên rỗng, handler lấy nguyên nhân gốc khỏi `InvocationTargetException`, nên phía gọi nhận `IllegalArgumentException`.

Proxy được nhận diện bằng `Proxy.isProxyClass`, không bằng việc tìm một chuỗi tên lớp do JDK sinh. `Proxy.getInvocationHandler` lấy handler gắn với đúng proxy instance.

## 4. Tách vai trò proxy, handler và target

Ví dụ trên có hai đối tượng **khác nhau**: `service` là proxy nhận lời gọi từ caller, còn `target` là `RealGreetingService` thực hiện nghiệp vụ. Handler nối hai đối tượng bằng `method.invoke(target, arguments)` và chỉ log quanh lần gọi được ủy quyền đó. Lời gọi `target.greet("Lan")` trực tiếp **không đi qua handler**; chỉ những lời gọi mà caller gửi đến `service` mới được chặn.

Không có quy tắc yêu cầu handler phải sở hữu target. Một mock hoặc RPC stub có thể tự trả lời dựa trên `method` và `args`. Khi không có target, handler vẫn phải tạo kết quả đúng kiểu hoặc ném ngoại lệ phù hợp với hợp đồng của interface.

**Không ủy quyền ngược về proxy:** `method.invoke(proxy, arguments)` thực hiện lại cùng phương thức trên đối tượng proxy, nên lại kích hoạt handler và có thể gây vòng lặp đến `StackOverflowError`. Khi log, tránh nối chuỗi với chính `proxy` nếu chưa có chính sách xử lý `toString()` rõ ràng.

## 5. Bốn ranh giới mà một handler cần giữ đúng

| Ranh giới | Điều cần biết khi viết handler |
| --- | --- |
| Đối số | `args == null` nếu method không nhận tham số; primitive được boxing. |
| Giá trị trả về | Một `int` cần `Integer` tương ứng; `null` với kiểu primitive gây `NullPointerException`; kiểu object sai có thể gây `ClassCastException`. |
| Ngoại lệ | `Method.invoke(target, args)` bọc lỗi của target bằng `InvocationTargetException`; nếu chuyển tiếp lỗi thật, thường lấy `getCause()`. Checked exception ra khỏi handler phải phù hợp với `throws` của interface, nếu không proxy có thể bọc `UndeclaredThrowableException`. |
| `Object` methods | `equals`, `hashCode` và `toString` cũng tới handler; ví dụ dùng identity của proxy cho equality/hash và chuỗi `GreetingProxy`. |

Với default method của interface, lời gọi vẫn đi qua handler. Nếu thật sự muốn chạy phần thân mặc định, từ Java 16 có `InvocationHandler.invokeDefault`; không sử dụng `Method.invoke(proxy, args)` để thay thế. Các bài riêng về giá trị trả về, checked exception, default method và các phương thức của `Object` sẽ đi sâu vào các điều kiện cụ thể.

## 6. Khi nào sử dụng mô hình này?

Chọn JDK dynamic proxy nếu caller làm việc qua một **interface** và bạn muốn thay đổi cách lời gọi được xử lý tại runtime: kiểm tra, ghi log, đo đạc, mock hay gọi dịch vụ từ xa. `newProxyInstance` tạo lớp proxy implements các interface đó; nó không làm proxy trở thành subclass của lớp `RealGreetingService`.

Bộ nạp lớp phải nhìn thấy đúng từng interface được yêu cầu. Cần xét thêm ranh giới Java modules, interface `sealed`/`hidden`, các method trùng chữ ký và quyền truy cập của interface `non-public` nếu dùng trong môi trường plugin/module. Chỉ một interface public ở classpath thông thường, như ví dụ, giúp tập trung vào luồng lời gọi trước khi chuyển sang các trường hợp khó.

## 7. Tự kiểm tra từ ví dụ

1. `Proxy.newProxyInstance` có tự khởi tạo `RealGreetingService` không? **Không**; target được tạo độc lập và handler nhận target do code ứng dụng cung cấp.
2. Vì sao `service.greet("Lan")` có in `enter/leave`, nhưng `target.greet("Lan")` không? **Đối tượng nhận lời gọi khác nhau**; chỉ proxy chuyển lời gọi qua handler.
3. `calls()` không có tham số; handler có nhận mảng một phần tử không? **Không**; `arguments` là `null`.
4. Vì sao cần tháo `InvocationTargetException` khi chuyển tiếp lỗi gốc? Để giữ nguyên nhân nghiệp vụ và tránh đưa một checked wrapper ngoài `throws` của interface ra phía caller.
5. Có bắt buộc dùng `Method.invoke(target, arguments)` không? **Không**; handler có thể tự thực thi một chiến lược khác và trả giá trị đúng hợp đồng.

**Ghi nhớ:** JDK proxy cung cấp một đối tượng gọi được qua interface, còn `InvocationHandler` định nghĩa hành vi của lời gọi. Target, nếu có, là lựa chọn của handler. Luôn tách **proxy nhận lời gọi**, **handler điều phối** và **target xử lý nghiệp vụ** để tránh vô tình gọi ngược vào proxy.

### Tài liệu chính thức

- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 17 — Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
