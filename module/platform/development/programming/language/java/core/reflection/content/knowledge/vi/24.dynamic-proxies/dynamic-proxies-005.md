# Lời gọi qua dynamic proxy được chuyển tới `InvocationHandler.invoke`

## 1. Ý nghĩa của cơ chế chuyển tiếp lời gọi

Với **JDK dynamic proxy** (`java.lang.reflect.Proxy`), ứng dụng tạo một đối tượng tại runtime triển khai một hoặc nhiều **interface**. Khi code gọi một phương thức qua interface trên đối tượng proxy, mã của lớp proxy do JDK tạo sẽ chuyển lời gọi đến `InvocationHandler.invoke(proxy, method, args)`. Handler quyết định phải làm gì: trả kết quả trực tiếp, gọi một đối tượng thật (*target*), kiểm tra quyền, ghi log, tính thời gian hoặc ném ngoại lệ.

Điểm cốt lõi của bài này là **lời gọi phương thức trên proxy kích hoạt handler; không mặc định chạy phương thức cùng tên của một đối tượng đích**. Chỉ khi handler chủ động gọi target thì nghiệp vụ của target mới chạy.

Ví dụ về đường đi:

```text
Caller
  |
  | service.greet("Lan")  // service là JDK proxy
  v
Phương thức greet trong lớp proxy do JDK tạo
  |
  | handler.invoke(proxy, Method(greet), Object[]{"Lan"})
  v
InvocationHandler
  |-- xử lý ngay và trả String
  |-- hoặc kiểm tra/log rồi gọi method.invoke(target, args)
  |-- hoặc ném exception
  v
Giá trị trả về / exception được chuyển về caller
```

Bản thân interface chỉ quy định hợp đồng, chẳng hạn `GreetingService.greet(String)`; proxy cung cấp implementation tại runtime thông qua handler. Điều này hữu ích khi muốn chèn hành vi chung quanh nhiều lời gọi mà code sử dụng interface không phải đổi cách gọi.

## 2. Tạo đối tượng proxy và điều kiện áp dụng

Ví dụ tạo proxy ở mức API:

```java
GreetingService service = (GreetingService) Proxy.newProxyInstance(
    GreetingService.class.getClassLoader(),
    new Class<?>[] { GreetingService.class },
    handler
);
```

Đây là **đoạn minh họa**, giả định đã định nghĩa `GreetingService` và `handler`. Ba đối số có vai trò:

1. **Class loader:** dùng để định nghĩa lớp proxy và giải quyết các interface được yêu cầu; loader phải phù hợp với khả năng nhìn thấy các interface.
2. **Mảng interface:** tập interface mà proxy triển khai. Lời gọi qua các interface này được chuyển tới handler. Các interface cần thỏa điều kiện hợp lệ của API (chẳng hạn phải là interface, không trùng lặp).
3. **`InvocationHandler`:** đối tượng xử lý các lời gọi được chuyển tiếp.

`Proxy.newProxyInstance(...)` trả về `Object` nên thường cần ép kiểu sang interface. Class của proxy là một lớp được sinh ở runtime, kế thừa `Proxy` và triển khai các interface đã chỉ định. `Proxy` của JDK **không tự tạo subclass của một concrete class bất kỳ**; nếu cần thay thế hành vi của concrete class, phải chọn cơ chế thích hợp khác.

Từ phía code sử dụng, cú pháp trông bình thường:

```java
String message = service.greet("Lan");
```

Dù caller gọi như một method Java thông thường, với `service` là proxy thì lời gọi ấy đi vào handler.

## 3. Bốn thành phần của `InvocationHandler.invoke`

Interface `InvocationHandler` khai báo:

```java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `proxy` | Chính đối tượng proxy nhận lời gọi, không phải target nghiệp vụ. |
| `method` | Đối tượng `java.lang.reflect.Method` mô tả phương thức được gọi qua proxy: tên, tham số, kiểu trả về, annotation và declaring class. |
| `args` | Giá trị các đối số theo thứ tự khai báo, được đóng hộp khi đối số thuộc kiểu primitive; có thể là `null` nếu phương thức không có tham số. |
| Giá trị trả về / `throws Throwable` | Handler trả giá trị phù hợp với chữ ký phương thức được gọi hoặc ném lỗi; lớp proxy chuyển kết quả hay ngoại lệ về caller theo các quy tắc Java. |

Lưu ý `method` là **metadata mô tả phương thức**, còn `args` là **dữ liệu của lần gọi hiện tại**. Hai lời gọi đến cùng một method có thể đi qua handler với các giá trị `args` khác nhau.

Việc chuyển tiếp không tương đương `method.invoke(proxy, args)` trong handler. Cách gọi đó thường quay ngược vào chính proxy, khiến `invoke` bị gọi lặp lại và có thể dẫn tới `StackOverflowError`. Nếu muốn ủy quyền, hãy gọi method lên một **target riêng có kiểu tương thích** hoặc thực hiện nghiệp vụ trực tiếp.

## 4. Ví dụ Java 17+ hoàn chỉnh: gọi proxy, handler nhận lời gọi

Tạo tệp `ProxyInvokeDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyInvokeDemo {
    public interface GreetingService {
        String greet(String name);
        void ping();
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, arguments) -> {
            System.out.println("invoke: " + method.getName());

            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreetingProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            return switch (method.getName()) {
                case "greet" -> "Xin chào, " + arguments[0];
                case "ping" -> null;
                default -> throw new UnsupportedOperationException(
                        method.getName());
            };
        };

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[] { GreetingService.class },
                handler
        );

        System.out.println(service.greet("Lan"));
        service.ping();
        System.out.println(service.toString());
        System.out.println(service.equals(service));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ProxyInvokeDemo.java
java ProxyInvokeDemo
```

Stdout chính xác:

```text
invoke: greet
Xin chào, Lan
invoke: ping
invoke: toString
GreetingProxy
invoke: equals
true
```

Diễn giải từng bước:

1. `Proxy.newProxyInstance(...)` tạo đối tượng triển khai `GreetingService`. Không có class `GreetingServiceImpl` nào cần được tạo.
2. `service.greet("Lan")` đến handler với `method.getName()` là `"greet"` và `arguments[0]` là `"Lan"`. Handler in tên phương thức rồi trả chuỗi. Caller nhận chuỗi đó như kết quả của `greet`.
3. `service.ping()` cũng tới handler. Phương thức `void` không mang giá trị về caller; handler trả `null`.
4. `service.toString()` và `service.equals(service)` đều được JDK proxy chuyển tới handler. Với ba phương thức đặc biệt `equals`, `hashCode` và `toString`, đối tượng `Method` được truyền vào có `Object.class` là declaring class. Ví dụ xử lý chúng một cách có chủ đích.
5. `proxy == arguments[0]` tại nhánh `equals` kiểm tra đồng nhất tham chiếu, tránh gọi lại `proxy.equals(...)` từ handler.

Ví dụ cố ý trả lời trực tiếp trong handler để làm rõ cơ chế. Thực tế handler thường còn ủy quyền đến target.

## 5. Trường hợp handler ủy quyền tới target bằng Reflection

Với proxy dùng để thêm log, đo thời gian hoặc bảo mật, handler thường bao lời gọi gốc theo trình tự: **trước lời gọi → gọi target → sau lời gọi**. Hãy phân biệt:

- `proxy`: đối tượng trung gian mà caller đang sử dụng.
- `target`: implementation nghiệp vụ thật, tồn tại độc lập.
- `method.invoke(target, arguments)`: lời gọi phản chiếu lên target; đây là hành động **do handler lựa chọn** thực hiện.

Ví dụ độc lập `ForwardingProxyDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ForwardingProxyDemo {
    public interface Calculator {
        int divide(int left, int right);
    }

    public static final class DefaultCalculator implements Calculator {
        @Override
        public int divide(int left, int right) {
            return left / right;
        }
    }

    public static void main(String[] args) {
        Calculator target = new DefaultCalculator();

        Calculator proxy = (Calculator) Proxy.newProxyInstance(
                Calculator.class.getClassLoader(),
                new Class<?>[] { Calculator.class },
                (proxyObject, method, actualArgs) -> {
                    System.out.println("before: " + method.getName());
                    try {
                        return method.invoke(target, actualArgs);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    } finally {
                        System.out.println("after: " + method.getName());
                    }
                }
        );

        System.out.println("result: " + proxy.divide(8, 2));

        try {
            proxy.divide(1, 0);
        } catch (ArithmeticException ex) {
            System.out.println("caught: " + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac ForwardingProxyDemo.java
java ForwardingProxyDemo
```

Stdout:

```text
before: divide
after: divide
result: 4
before: divide
after: divide
caught: ArithmeticException
```

Trong lần gọi thứ nhất, `proxy.divide(8, 2)` chuyển tới handler; handler gọi `method.invoke(target, actualArgs)`, target tính `8 / 2` và trả số nguyên `4`. Reflection trả giá trị kiểu `Object` chứa `Integer`; lớp proxy gỡ hộp thành `int` cho caller.

Trong lần gọi thứ hai, target ném `ArithmeticException` vì chia cho 0. `Method.invoke` bọc ngoại lệ từ method đích trong `InvocationTargetException`. Handler lấy `ex.getCause()` và ném nguyên nhân thực sự; `finally` vẫn chạy. Vì vậy caller bắt được `ArithmeticException`. Nếu cứ ném nguyên `InvocationTargetException` ra từ handler, nó là checked exception không được khai báo trong chữ ký `divide` và có thể bị proxy bọc thêm trong `UndeclaredThrowableException`, khiến việc xử lý lỗi khó hơn.

Ở bài toán lớn, hãy kiểm soát việc truy cập target, xử lý ngoại lệ và bảo đảm logic ghi log/transaction không bỏ sót nhánh thất bại.

## 6. Kiểm chứng phạm vi chuyển lời gọi

Hai ví dụ trên cho thấy **cùng một cơ chế dispatch có hai cách xử lý khác nhau**:

- `ProxyInvokeDemo` không có target: `greet()` và `ping()` tới handler, rồi handler tự cung cấp kết quả. Vì thế `invoke: greet` xuất hiện trước chuỗi chào; `ping` trả `null` vì method là `void`.
- `ForwardingProxyDemo` có target: handler nhận `divide`, ghi `before`, rồi chủ động gọi `method.invoke(target, actualArgs)`. `finally` ghi `after` ngay cả khi target ném `ArithmeticException`.

Điểm thực nghiệm cần nhớ: nếu gọi `target.divide(8, 2)` trực tiếp, handler của proxy **không chạy**, dù target triển khai cùng interface. Nếu target tự gọi phương thức của chính nó qua `this`, lời gọi đó cũng không tự chuyển về proxy bên ngoài. Do vậy, quy tắc chặn lời gọi phụ thuộc **receiver thực tế**, không phụ thuộc việc method có tên giống nhau.

## 7. Điều gì diễn ra khi handler trả kết quả hoặc ném lỗi?

Khi handler hoàn tất, lớp proxy phải đáp ứng kiểu và ngoại lệ của method interface:

| Tình huống | Kết quả quan sát ở caller |
| --- | --- |
| Handler trả `"Xin chào, Lan"` cho method trả `String` | Caller nhận chính chuỗi đó |
| Handler trả `Integer(4)` cho method trả `int` | Proxy unbox thành `4` |
| Handler trả `null` cho method trả `void` | Hoàn thành không có giá trị trả về |
| Handler trả `null` cho method trả primitive | `NullPointerException` tại đường chuyển kiểu |
| Handler ném `RuntimeException` hoặc `Error` | Caller nhận trực tiếp theo hợp đồng unchecked |
| Handler ném checked exception ngoài `throws` của interface | Proxy bọc `UndeclaredThrowableException` |

Nếu target ném `ArithmeticException` trong lần `Method.invoke`, Reflection bọc nó vào `InvocationTargetException`; `ForwardingProxyDemo` chủ động ném `ex.getCause()` để caller nhìn thấy lỗi thật. Nếu bỏ bước này, wrapper checked có thể bị proxy bọc thêm lần nữa.

## 8. Ba đường gọi đặc biệt để không hiểu sai dispatch

**Các method của `Object`:** `equals(Object)`, `hashCode()`, `toString()` được proxy chuyển tới handler; `Method.getDeclaringClass()` ở ba lời gọi này là `Object.class`. Method `getClass()` là `final` nên không bị chặn theo cơ chế đó. Nếu in chính proxy trong handler, lời gọi `toString()` có thể quay lại handler gây đệ quy.

**Default method:** phần thân `default` của interface không tự chạy trước handler. Với Java 16+, handler có thể dùng `InvocationHandler.invokeDefault(proxy, method, args)` cho default method hợp lệ nếu quyết định thực thi phần thân. Lệnh `method.invoke(proxy, args)` lại gọi chính proxy và có nguy cơ đệ quy.

**Nhiều interface:** khi hai interface có cùng tên method và danh sách tham số, `Method` đưa vào handler có thể phụ thuộc thứ tự interface khi tạo proxy, và kiểu trả về hiệp biến còn có quy tắc riêng. Handler không nhận được thông tin caller đã ép proxy thành interface nào. Thiết kế dispatch theo contract đã rõ, không chỉ dựa vào tên method.

## 9. Bài tự kiểm tra

1. Trong `ProxyInvokeDemo`, bỏ đối tượng target đi có làm lời gọi `greet` thất bại không? **Không**, handler đang tự trả kết quả.
2. Trong `ForwardingProxyDemo`, vì sao `after: divide` vẫn được in khi chia cho 0? Vì handler dùng `finally` quanh lời gọi target.
3. Nếu thay receiver trong `method.invoke(target, actualArgs)` bằng proxy của cùng lời gọi, điều gì xảy ra? Dispatch quay về handler, dễ lặp vô hạn.
4. Nếu gọi method trả `int` mà handler trả `null`, lỗi có xuất hiện trước khi handler trả về không? Không nhất thiết; lớp proxy phải unbox kết quả và sẽ ném `NullPointerException`.
5. `service.toString()` có tới handler không? **Có**. `service.getClass()` có tới handler không? **Không**, vì `getClass` là `final` method của `Object`.

**Điều cần nhớ:** lời gọi trên **proxy instance** kích hoạt handler. Handler có thể tự xử lý, gọi target hoặc chạy default method được chọn; phía caller chỉ nhìn thấy kết quả/ngoại lệ phù hợp với chữ ký interface. Truy ra receiver của mỗi lời gọi là cách chắc chắn nhất để dự đoán hành vi.

### Tài liệu chính thức

- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
