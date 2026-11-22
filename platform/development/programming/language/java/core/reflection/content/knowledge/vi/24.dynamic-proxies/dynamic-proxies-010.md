# Gọi default method bằng `InvocationHandler.invokeDefault` trong Java

## 1. Vấn đề: default method cũng đi qua InvocationHandler

Dynamic proxy của JDK là một đối tượng được tạo bằng `java.lang.reflect.Proxy` để triển khai một hoặc nhiều interface. Khi gọi phương thức của proxy, lời gọi được chuyển tới `InvocationHandler.invoke(proxy, method, args)`, kể cả khi interface đã có phần thân `default method`. Vì thế, nếu handler muốn **thực thi phần thân mặc định** thay vì tự tính kết quả, nó cần chủ động chuyển tiếp lời gọi.

Từ **Java 16**, API `InvocationHandler.invokeDefault` cung cấp cách trực tiếp để làm việc này. Với Java 17+, đây là lựa chọn rõ ràng khi viết dynamic proxy có hỗ trợ default method.

```java
// Mẫu dùng bên trong InvocationHandler.invoke:
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(proxy, method, args);
}
```

Đây là **đoạn minh họa đặt trong handler**, chưa phải chương trình độc lập. `method.isDefault()` giúp phân biệt default method thực sự với phương thức abstract của interface, phương thức của `Object` và các phương thức khác.

## 2. Cú pháp, tham số và cơ chế

Chữ ký API:

```java
public static Object invokeDefault(
        Object proxy, Method method, Object... args) throws Throwable;
```

| Tham số | Ý nghĩa |
| --- | --- |
| `proxy` | Đối tượng **dynamic proxy** đang xử lý lời gọi. |
| `method` | `Method` đại diện cho **default method hợp lệ** được khai báo trên một proxy interface hoặc được interface đó kế thừa. |
| `args` | Các đối số truyền cho default method, đúng số lượng và kiểu tham số; có thể là `null` khi phương thức không có tham số. |
| Giá trị trả về | `Object` chứa kết quả do phần thân default method trả về (hoặc `null` nếu phương thức trả về `void`). |

`InvocationHandler.invokeDefault(proxy, method, args)` thực thi phần thân mặc định theo ngữ nghĩa gần với lệnh JVM `invokespecial`, tương đương ý tưởng gọi `InterfaceName.super.method(...)` từ lớp proxy. Đây **không phải** lời gọi thông thường thông qua `Method.invoke(proxy, ...)`.

Điều kiện quan trọng: `method` phải là default method có thể được phân giải qua các interface của **chính proxy**. Không thể lấy một default method tùy ý từ interface không liên quan rồi yêu cầu proxy thực thi. Nếu một proxy interface override default method của interface cha, việc cố gọi trực tiếp phiên bản cha bằng một `Method` cũ có thể không còn hợp lệ.

Sơ đồ luồng:

```text
client gọi proxy.defaultMethod(...)
    → JVM chuyển vào handler.invoke(proxy, method, args)
        → method.isDefault() == true
            → InvocationHandler.invokeDefault(proxy, method, args)
                → chạy thân default method trong interface
                    → trả kết quả về handler rồi về client
```

Nếu bên trong thân default method lại gọi một phương thức interface khác qua `this`, lời gọi ảo đó vẫn có thể đi qua handler của proxy. Handler phải xử lý được cả lời gọi tiếp theo.

## 3. Ví dụ Java 17+ chạy độc lập

Lưu tệp `InvokeDefaultDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class InvokeDefaultDemo {
    public interface TextService {
        String code();

        default String greeting(String name) {
            return "Hello, " + name + " from " + code();
        }

        default String plain() {
            return "DEFAULT";
        }
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, callArgs) -> {
            if (method.isDefault()) {
                System.out.println("handler default: " + method.getName());
                return InvocationHandler.invokeDefault(
                        proxy, method, callArgs);
            }

            if (method.getName().equals("code")
                    && method.getParameterCount() == 0) {
                return "proxy";
            }

            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "TextServiceProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == callArgs[0];
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            throw new UnsupportedOperationException(method.toString());
        };

        TextService service = (TextService) Proxy.newProxyInstance(
                TextService.class.getClassLoader(),
                new Class<?>[] { TextService.class },
                handler);

        System.out.println(service.greeting("An"));
        System.out.println(service.plain());
        System.out.println(service.code());
        System.out.println(service.toString());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 InvokeDefaultDemo.java
java InvokeDefaultDemo
```

Stdout chính xác:

```text
handler default: greeting
Hello, An from proxy
handler default: plain
DEFAULT
proxy
TextServiceProxy
```

Diễn giải theo thứ tự:

1. `service.greeting("An")` tới handler. Vì `greeting` là default method, `method.isDefault()` là `true` và `invokeDefault` chạy phần thân đã viết trong `TextService`.
2. Trong thân `greeting` có `code()`; đây là phương thức abstract được gọi trên proxy, nên handler nhận lời gọi `code` và trả `"proxy"`. Kết quả ghép thành `Hello, An from proxy`.
3. `plain()` không nhận tham số: `callArgs` trong handler có thể bằng `null`, và truyền nguyên giá trị đó cho `invokeDefault` là hợp lệ.
4. `code()` không phải default method: handler tự cung cấp kết quả.
5. `toString()` thuộc nhóm phương thức `Object` được proxy chuyển đến handler; nhánh xử lý riêng tránh việc mọi lời gọi không phải default đều bị ném lỗi. Ví dụ cũng xử lý `equals` và `hashCode` theo danh tính proxy.

## 4. Tại sao không dùng Method.invoke(proxy, args)?

Giả sử trong handler bạn viết:

```java
// Sai khi mục tiêu là chạy phần thân default method:
return method.invoke(proxy, args);
```

`Method.invoke` gọi phương thức trên chính đối tượng `proxy`. Đối tượng này lại chuyển lời gọi về handler, dẫn tới chu trình lặp và có nguy cơ `StackOverflowError`. `InvocationHandler.invokeDefault` đi vào **phần thân mặc định được chỉ định**, nên giải quyết đúng bài toán.

Cũng không thể viết `SomeInterface.super.method(...)` trực tiếp trong handler lambda: cú pháp đó chỉ hợp lệ ở ngữ cảnh Java cho phép gọi default method của superinterface, không phải một lời gọi động dựa vào đối tượng `Method`.

Trước Java 16, các cách xử lý thường liên quan `MethodHandles.Lookup` và quyền truy cập module; không nên sao chép những ví dụ cũ sang Java 17+ khi API `invokeDefault` đã đáp ứng nhu cầu.

## 5. Kế thừa, override và nhiều default method trùng chữ ký

**Kế thừa:** nếu `Child extends Parent` và `Child` không override default method `Parent.run()`, proxy chỉ triển khai `Child` vẫn có thể gọi phần thân default kế thừa từ `Parent` thông qua `invokeDefault`. `Method` do handler nhận có thể có `getDeclaringClass() == Parent.class`.

**Override:** nếu sau đó `Child` định nghĩa lại `default run()`, phương thức hiệu lực là phiên bản của `Child`. Một handler lưu sẵn `Parent.class.getMethod("run")` rồi ép `invokeDefault` gọi bản cha có thể nhận `IllegalArgumentException`, vì bản cha không còn là mục tiêu phân giải hợp lệ qua `Child`. Đây là điểm cần kiểm tra khi nâng cấp thư viện interface.

**Hai interface độc lập có cùng default method:** handler có thể chủ động chọn một bản bằng cách lấy đúng `Method` của interface mong muốn. Ví dụ độc lập sau cho kết quả cùng là `second`, bất kể client ép proxy về `First` hay `Second`:

Lưu tệp `ChooseDefaultDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ChooseDefaultDemo {
    public interface First {
        default String origin() { return "first"; }
    }

    public interface Second {
        default String origin() { return "second"; }
    }

    public static void main(String[] args) throws Exception {
        Method chosen = Second.class.getMethod("origin");

        InvocationHandler handler = (proxy, method, callArgs) -> {
            if (method.getName().equals("origin")) {
                return InvocationHandler.invokeDefault(
                        proxy, chosen, callArgs);
            }
            throw new UnsupportedOperationException(method.toString());
        };

        Object proxy = Proxy.newProxyInstance(
                ChooseDefaultDemo.class.getClassLoader(),
                new Class<?>[] { First.class, Second.class },
                handler);

        System.out.println(((First) proxy).origin());
        System.out.println(((Second) proxy).origin());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ChooseDefaultDemo.java
java ChooseDefaultDemo
```

```text
second
second
```

Ví dụ trên chọn rõ `Second.origin()`. Nó **không** nói rằng Java tự ưu tiên `Second`; thứ tự và `Method` ban đầu chuyển đến handler không nên được sử dụng thay cho quyết định nghiệp vụ. Nếu muốn chọn theo đối tượng gọi ban đầu, hãy thiết kế giao diện/điểm vào rõ ràng: với hai chữ ký trùng nhau, handler không tự nhận được thông tin client đã cast sang interface nào.

## 6. Kiểm tra đầu vào, lỗi và ngoại lệ

| Trường hợp | Hành vi/cách xử lý |
| --- | --- |
| `method.isDefault() == false` | Không chuyển phương thức abstract hoặc `Object` sang `invokeDefault`; tự xử lý/delegate. |
| `proxy` không phải dynamic proxy, hoặc `method` không phải default method hợp lệ của proxy | `IllegalArgumentException`. |
| `method` đã bị proxy interface override khiến mục tiêu cũ không còn hợp lệ | Có thể nhận `IllegalArgumentException`; cập nhật lựa chọn `Method` theo interface hiệu lực. |
| Số đối số sai hoặc kiểu đối số không tương thích, kể cả việc unbox primitive | `IllegalArgumentException`. |
| `proxy == null` hoặc `method == null` | `NullPointerException`. |
| Lớp khai báo default method không thể truy cập từ nơi gọi | Có thể phát sinh `IllegalAccessException`. |
| Thân default method tự ném ngoại lệ | `invokeDefault` có thể ném tiếp `Throwable` đó; phải cân nhắc hợp đồng `throws` của phương thức interface. |

Handler có chữ ký `Object invoke(...) throws Throwable`, nên có thể chuyển tiếp `Throwable` từ `invokeDefault` mà không cần ép thành `RuntimeException`. Nếu ngoại lệ checked không được khai báo bởi phương thức interface thoát khỏi handler, lời gọi trên proxy có thể bao nó trong `UndeclaredThrowableException`. Với phương thức trả về primitive, kết quả handler trả về phải tương thích với wrapper tương ứng; trả `null` sẽ gây lỗi khi proxy cần unbox.

Để dùng an toàn, hãy kiểm tra `method.isDefault()` trước, truyền đúng proxy thực, chuyển nguyên `args` (kể cả `null` khi không có tham số), và xử lý riêng các phương thức còn lại.

## 7. Lỗi thường gặp và cách tránh

- **Tự gọi lại proxy bằng reflection:** `method.invoke(proxy, args)` không phải cách gọi thân default; dùng `invokeDefault`.
- **Cho rằng default method tự chạy:** dynamic proxy chuyển lời gọi vào handler; muốn chạy phần thân mặc định phải chọn làm điều đó.
- **Nhầm `isDefault()` với `!isAbstract()`:** phương thức `Object` cũng không abstract nhưng không phải default method.
- **Tự tạo `Method` theo tên mà không xét proxy interface:** chỉ dùng phương thức default hợp lệ, còn hiệu lực và có thể truy cập.
- **Giả sử `args` luôn khác `null`:** handler nhận `null` khi phương thức không có tham số; nếu tự đọc `args[0]` phải chắc chắn phương thức cần đối số.
- **Bỏ qua đường gọi tiếp từ default method:** phần thân default có thể gọi phương thức interface khác và làm handler chạy thêm lần nữa.
- **Không kiểm tra tương thích JDK:** `InvocationHandler.invokeDefault` chỉ xuất hiện từ Java 16; biên dịch với `--release 11` không thể gọi API này.
- **Quên kế thừa và override:** việc thêm default method mới trong interface con có thể thay đổi phương thức mà `invokeDefault` được phép gọi.

## 8. Câu hỏi tự kiểm tra

1. **Vì sao `method.invoke(proxy, args)` không phù hợp để chạy default method từ handler?** Vì nó gọi lại phương thức trên proxy, có thể đưa lời gọi trở vào chính handler và lặp vô hạn.
2. **Default method gọi một abstract method cùng interface thì sao?** Lời gọi thực hiện trên proxy; handler lại nhận phương thức abstract và phải xử lý nó.
3. **Một proxy triển khai `First` và `Second` đều có `default origin()`. Có thể chọn `Second` không?** Có: lấy `Second.class.getMethod("origin")` rồi truyền phương thức đó vào `InvocationHandler.invokeDefault`, miễn hợp lệ với các interface của proxy.
4. **Có thể truyền `null` cho `args` không?** Có, khi default method có 0 tham số; với phương thức có tham số phải truyền số lượng/kiểu đối số hợp lệ.
5. **API này dùng trên Java 11 được không?** Không; API xuất hiện từ Java 16.

**Ghi nhớ:** `InvocationHandler.invokeDefault` là cầu nối từ `InvocationHandler` tới **phần thân default method hợp lệ của interface trên dynamic proxy**. Hãy dùng `Method.isDefault()` để nhận diện, xử lý riêng phương thức abstract/`Object`, và kiểm tra kỹ kế thừa, override, quyền truy cập cùng đối số.

Tham khảo: [Javadoc Java 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html).