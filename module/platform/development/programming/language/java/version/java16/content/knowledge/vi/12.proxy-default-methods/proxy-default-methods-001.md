# InvocationHandler.invokeDefault và hỗ trợ default method từ Java 16

Java 16 bổ sung `InvocationHandler.invokeDefault`, một API chính thức để gọi phần thân của một `default method` trên đối tượng Java dynamic proxy. API này vẫn có trong các JDK hiện đại, vì vậy có thể dùng trực tiếp khi ứng dụng chạy trên JDK 16 trở lên.

Điểm cần nhớ là lời gọi phương thức trên một dynamic proxy luôn được chuyển đến `InvocationHandler`. Kể cả khi phương thức đó có phần triển khai mặc định trong interface, proxy cũng không tự chạy phần thân ấy. Handler cần quyết định có gọi default method hay xử lý theo logic riêng.

## 1. Vì sao cần gọi default method từ InvocationHandler?

Interface có thể khai báo phương thức trừu tượng và phương thức mặc định. Phương thức mặc định có phần thân dùng chung, còn lớp triển khai có thể kế thừa hoặc ghi đè phần thân đó.

```java
public interface GreetingService {
    default String greet(String name) {
        return "Xin chào " + name;
    }

    String findMessage(String key);
}
```

Khi gọi `greet` trên một đối tượng triển khai trực tiếp `GreetingService`, phần thân mặc định được thực thi như một phương thức thông thường. Nhưng nếu đối tượng là dynamic proxy được tạo bằng `Proxy.newProxyInstance`, lời gọi được chuyển đến `InvocationHandler.invoke`.

Trong handler, tham số `method` mô tả phương thức vừa được gọi. Có thể dùng `method.isDefault()` để nhận biết đây là một default method. Nếu handler chỉ trả về kết quả cho các phương thức trừu tượng mà không xử lý trường hợp này, default method sẽ không tự chạy; handler có thể trả về sai kiểu, trả về `null` hoặc ném ngoại lệ tùy cách triển khai.

Java 16 giải quyết trường hợp đó bằng lời gọi:

```java
InvocationHandler.invokeDefault(proxy, method, args);
```

Phương thức tĩnh này yêu cầu proxy thực thi phần thân default method được chỉ ra bởi đối tượng `Method`.

## 2. Gọi default method trong proxy

Ví dụ sau tạo một proxy cho `GreetingService`. Handler chuyển các default method về phần triển khai trong interface và tự xử lý phương thức trừu tượng `findMessage`.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ProxyDefaultMethodDemo {
    public interface GreetingService {
        default String greet(String name) {
            return "Xin chào " + findMessage(name);
        }

        String findMessage(String key);
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, arguments) -> {
            // Xử lý các phương thức khai báo bởi Object.
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreetingService proxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            // Chạy phần thân default method trên chính proxy.
            if (method.isDefault()) {
                Object[] actualArguments = arguments == null
                        ? new Object[0]
                        : arguments;
                return InvocationHandler.invokeDefault(
                        proxy, method, actualArguments);
            }

            // Xử lý phương thức trừu tượng theo quy tắc của ứng dụng.
            if (method.getName().equals("findMessage")) {
                return "người dùng " + arguments[0];
            }

            throw new UnsupportedOperationException(method.toString());
        };

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[]{GreetingService.class},
                handler);

        System.out.println(service.greet("An"));
        System.out.println(service.findMessage("Bình"));
    }
}
```

Kết quả:

```text
Xin chào người dùng An
người dùng Bình
```

Khi `service.greet("An")` được gọi, luồng xử lý diễn ra như sau:

1. Proxy chuyển lời gọi đến `handler.invoke` với `method` tương ứng `greet`.
2. `method.isDefault()` trả về `true`, nên handler gọi `InvocationHandler.invokeDefault`.
3. Phần thân `GreetingService.greet` chạy với đối tượng nhận lời gọi là proxy.
4. Bên trong `greet`, lời gọi `findMessage(name)` tiếp tục đi qua proxy và quay lại `handler.invoke`.
5. Handler xử lý `findMessage` rồi trả kết quả cho `greet`.

Ví dụ này cho thấy default method có thể phối hợp với các phương thức trừu tượng do handler cung cấp. `this` bên trong default method chính là proxy; những lời gọi phương thức tiếp theo trên `this` vẫn được proxy chuyển đến handler.

## 3. Chọn default method khi interface có quan hệ kế thừa

Tham số `method` quyết định chính xác phần thân default method nào sẽ được gọi. Điều này hữu ích khi một interface con ghi đè default method của interface cha.

```java
public interface BaseLabel {
    default String label() {
        return "Base";
    }
}

public interface PremiumLabel extends BaseLabel {
    @Override
    default String label() {
        return "Premium";
    }
}
```

Nếu proxy triển khai `PremiumLabel`, lời gọi `label()` thông thường đi vào default method của `PremiumLabel`. Trong handler, ứng dụng vẫn có thể chủ động chọn phần thân của `BaseLabel` bằng cách lấy đúng đối tượng `Method`:

```java
Method baseLabel = BaseLabel.class.getMethod("label");
Object result = InvocationHandler.invokeDefault(proxy, baseLabel);
```

`BaseLabel` là interface cha của interface mà proxy triển khai, nên default method này có thể được gọi trên proxy. Cách chọn tường minh này cũng hữu ích khi proxy triển khai nhiều interface có default method cùng chữ ký và ứng dụng cần quyết định phần triển khai nào sẽ chạy.

Không nên chỉ dựa vào tên phương thức để chọn default method trong trường hợp có overload. Hãy lấy `Method` từ đúng interface và truyền đúng đối số tương ứng với chữ ký đó.

## 4. Điều kiện và cách xử lý lỗi

`InvocationHandler.invokeDefault` có từ Java 16. Ứng dụng cần chạy bằng JDK 16 trở lên để sử dụng API này; mã nguồn dùng API này không thể chạy nguyên trạng trên JDK 8 hoặc JDK 11.

Các điều kiện chính khi gọi:

- `proxy` phải là một đối tượng dynamic proxy.
- `method` phải là default method của một interface mà proxy triển khai, trực tiếp hoặc thông qua kế thừa.
- Các đối số phải phù hợp với tham số của phương thức được chọn.
- Giá trị trả về của handler phải phù hợp với kiểu trả về mà phương thức proxy khai báo.

Nếu `method` không phải default method hoặc interface khai báo nó không thuộc hệ interface của proxy, lời gọi không hợp lệ và có thể ném `IllegalArgumentException`. Vì `InvocationHandler.invoke` cho phép ném `Throwable`, handler có thể chuyển tiếp ngoại lệ phát sinh từ default method. Tuy nhiên, nếu ngoại lệ checked không nằm trong `throws` của phương thức interface, cơ chế dynamic proxy có thể bọc nó trong `UndeclaredThrowableException`.

Đối với phương thức không có tham số, `InvocationHandler.invoke` có thể nhận `arguments == null`. Ví dụ trên chuyển trường hợp này thành mảng rỗng trước khi gọi `invokeDefault`, giúp thể hiện rõ rằng phương thức không có đối số và tránh truyền nhầm một tham chiếu mảng `null` vào tham số varargs.

## 5. Khi nào nên dùng?

`InvocationHandler.invokeDefault` phù hợp khi handler cần giữ lại hành vi mặc định của interface trong khi bổ sung xử lý cho proxy, chẳng hạn:

- Ghi log hoặc đo thời gian thực thi rồi tiếp tục chạy default method.
- Dùng default method làm hành vi dự phòng cho một số lời gọi.
- Cho phép các default method dùng chung logic được cung cấp bởi những phương thức trừu tượng mà handler xử lý.
- Chọn rõ default method của interface cha khi interface con ghi đè hoặc nhiều interface có phương thức trùng chữ ký.

Một handler có thể áp dụng chính sách chung cho default method:

```java
if (method.isDefault()) {
    long startedAt = System.nanoTime();
    try {
        return InvocationHandler.invokeDefault(
                proxy,
                method,
                arguments == null ? new Object[0] : arguments);
    } finally {
        long elapsed = System.nanoTime() - startedAt;
        System.out.println(method.getName() + " took " + elapsed + " ns");
    }
}
```

Hãy chú ý đến việc default method có thể gọi ngược các phương thức khác trên proxy. Những lời gọi đó lại đi qua handler, vì vậy chính sách ghi log, kiểm tra quyền hoặc đo thời gian có thể được áp dụng nhiều lần trong một chuỗi gọi. Handler cần thiết kế điều kiện xử lý phù hợp để tránh lặp vô hạn hoặc thực hiện cùng một tác vụ ngoài ý muốn.

Nếu proxy đại diện cho một đối tượng đích, handler cũng cần quyết định rõ phương thức nào được chuyển đến đối tượng đích và phương thức default nào được chạy trên proxy. `invokeDefault` chạy phần thân interface với proxy làm đối tượng nhận lời gọi; nó không tự tìm hay gọi một đối tượng đích khác.

## 6. Ghi nhớ

- Dynamic proxy chuyển lời gọi phương thức đến `InvocationHandler`, kể cả khi phương thức có phần thân mặc định.
- `Method.isDefault()` giúp nhận biết default method.
- Từ Java 16, `InvocationHandler.invokeDefault(proxy, method, args)` là API chuẩn để chạy default method trên proxy.
- Đối tượng `Method` xác định interface và phần thân cụ thể sẽ được gọi; có thể chọn default method của interface cha nếu interface đó thuộc hệ kế thừa của proxy.
- Lời gọi phương thức bên trong default method vẫn có thể quay lại handler vì `this` là proxy.

Khi xây dựng dynamic proxy trên JDK hiện đại, hãy xử lý default method một cách tường minh trong `InvocationHandler`. Cách này giúp giữ hành vi mặc định của interface và vẫn cho phép handler kiểm soát các lời gọi qua proxy.
