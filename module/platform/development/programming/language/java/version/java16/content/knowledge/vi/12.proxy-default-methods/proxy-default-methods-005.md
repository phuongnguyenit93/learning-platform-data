# Xử lý default method không tham số, primitive và giá trị trả về

Khi một dynamic proxy nhận lời gọi đến default method, JDK chuyển lời gọi đó đến `InvocationHandler.invoke`. Handler có thể dùng `InvocationHandler.invokeDefault(proxy, method, args)` để chạy phần thân mặc định của interface. Để chuyển tiếp chính xác, cần hiểu cách Java biểu diễn lời gọi không tham số, cách đóng gói kiểu primitive trong `Object[]` và cách giá trị trả về đi từ handler về client.

`InvocationHandler.invokeDefault` được bổ sung từ Java 16 và vẫn là API công khai dùng được trên các JDK hiện đại. Các quy tắc boxing, unboxing và kiểu trả về dưới đây là quy tắc Java nền tảng, không phải hành vi thử nghiệm.

## 1. Lời gọi không có tham số

Chữ ký của `InvocationHandler.invoke` nhận đối số cuối là `Object[] args`. Theo hợp đồng của API, nếu phương thức được gọi không có tham số thì `args` có thể là `null`.

Ví dụ interface có một default method không tham số:

```java
public interface ServiceStatus {
    default String status() {
        return "READY";
    }
}
```

Handler nên chuẩn hóa trường hợp `args == null` thành mảng rỗng trước khi chuyển tiếp:

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.isDefault()) {
        Object[] actualArgs = args == null
                ? new Object[0]
                : args;
        return InvocationHandler.invokeDefault(
                proxy, method, actualArgs);
    }

    throw new UnsupportedOperationException(method.toString());
};
```

Mảng rỗng biểu diễn rõ một lời gọi không có đối số. Tránh truyền trực tiếp `null` vào tham số varargs của `invokeDefault`, vì khi đó Java hiểu `null` là chính mảng varargs, không phải một mảng có phần tử.

## 2. Primitive trong tham số của default method

`InvocationHandler.invoke` nhận các đối số dưới dạng `Object[]`. Vì vậy, khi phương thức interface nhận kiểu primitive, Java tự động boxing giá trị thành wrapper trước khi đặt vào mảng.

| Kiểu primitive | Wrapper trong `args` |
|---|---|
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

Ví dụ:

```java
public interface Calculator {
    default int add(int left, int right) {
        return left + right;
    }
}
```

Khi client gọi `proxy.add(10, 20)`, handler nhận hai phần tử `Integer` trong `args`. Nếu handler chỉ chuyển tiếp default method thì nên giữ nguyên mảng đó:

```java
if (method.isDefault()) {
    Object[] actualArgs = args == null ? new Object[0] : args;
    return InvocationHandler.invokeDefault(proxy, method, actualArgs);
}
```

Không cần tự unbox rồi boxing lại các phần tử. Nếu ứng dụng có chủ đích thay đổi đối số, phải giữ đúng số lượng, thứ tự và kiểu wrapper tương ứng với chữ ký phương thức. Ví dụ tham số `int` cần giá trị `Integer`; tham số `long` cần `Long`.

## 3. Primitive trong giá trị trả về

`InvocationHandler.invokeDefault` có kiểu trả về là `Object`, nên kết quả primitive của default method được boxing thành wrapper khi trả về handler. Sau đó handler trả wrapper đó về cho phương thức proxy. Lớp proxy do JDK tạo sẽ unbox wrapper về primitive để trả cho client.

Ví dụ với `int`:

```java
public interface Sequence {
    default int firstValue() {
        return 10;
    }
}
```

Khi gọi `sequence.firstValue()`, luồng giá trị là:

1. Phần thân default method tạo giá trị primitive `int` bằng `10`.
2. `invokeDefault` trả kết quả qua kiểu `Object`, nên giá trị được boxing thành `Integer`.
3. Handler trả `Integer` về cho proxy.
4. Phương thức proxy unbox `Integer` thành `int` và trả về client.

Handler không cần tự gọi `Integer.valueOf` khi đã dùng `invokeDefault`; API đã trả kết quả phù hợp qua kiểu `Object`.

Các kiểu primitive khác cũng tuân theo quy tắc tương tự: `boolean` thành `Boolean`, `long` thành `Long`, `double` thành `Double`, v.v. Khi handler tự tạo kết quả thay vì gọi default method, cần trả đúng wrapper tương ứng.

## 4. Kiểu trả về void

Default method có kiểu trả về `void` vẫn có thể được nhận diện và gọi qua handler:

```java
public interface AuditService {
    default void record(String message) {
        System.out.println("AUDIT: " + message);
    }
}
```

Với phương thức `void`, `invokeDefault` trả về `null` qua kiểu `Object`. Phương thức proxy không có giá trị nào để trả cho client; kết quả handler trả về được bỏ qua. Vì vậy, cách chuyển tiếp thông thường vẫn là trả trực tiếp kết quả từ `invokeDefault`.

Nếu handler tự xử lý một phương thức `void` mà không gọi default method, có thể trả về `null` sau khi hoàn tất tác vụ. Không trả về một đối tượng để biểu diễn kết quả của `void`, vì bên gọi không nhận giá trị đó.

Có thể nhận diện phương thức `void` bằng:

```java
if (method.getReturnType() == void.class) {
    // Phương thức không có giá trị trả về.
}
```

`void.class` là cách reflection biểu diễn kiểu trả về `void`.

## 5. Ví dụ hoàn chỉnh: không tham số, primitive và void

Ví dụ sau tạo một dynamic proxy chỉ triển khai các default method. Handler ghi nhận metadata của lời gọi rồi chuyển tiếp đến phần thân default method bằng API Java 16.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyPrimitiveReturnDemo {
    public interface Meter {
        default int initialValue() {
            return 40;
        }

        default int increment(int value) {
            return value + 1;
        }

        default boolean isPositive(int value) {
            return value > 0;
        }

        default void printValue(int value) {
            System.out.println("value=" + value);
        }
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, arguments) -> {
            if (!method.isDefault()) {
                throw new UnsupportedOperationException(method.toString());
            }

            Object[] actualArgs = arguments == null
                    ? new Object[0]
                    : arguments;

            System.out.printf(
                    "[handler] %s, parameters=%d, return=%s%n",
                    method.getName(),
                    method.getParameterCount(),
                    method.getReturnType().getSimpleName());

            return InvocationHandler.invokeDefault(
                    proxy, method, actualArgs);
        };

        Meter meter = (Meter) Proxy.newProxyInstance(
                Meter.class.getClassLoader(),
                new Class<?>[]{Meter.class},
                handler);

        int initial = meter.initialValue();
        int next = meter.increment(initial);
        boolean positive = meter.isPositive(next);

        System.out.println("initial=" + initial);
        System.out.println("next=" + next);
        System.out.println("positive=" + positive);
        meter.printValue(next);
    }
}
```

Kết quả:

```text
[handler] initialValue, parameters=0, return=int
[handler] increment, parameters=1, return=int
[handler] isPositive, parameters=1, return=boolean
initial=40
next=41
positive=true
[handler] printValue, parameters=1, return=void
value=41
```

Ở `initialValue()`, `arguments` có thể là `null`; handler đổi thành mảng rỗng. Ở `increment` và `isPositive`, phần tử đối số là wrapper `Integer`. Kết quả của hai default method lần lượt được boxing thành `Integer` và `Boolean`, rồi proxy unbox về `int` và `boolean`. `printValue` có kiểu trả về `void`, nên handler không có giá trị cần chuyển về client; phần thân default method chỉ thực hiện tác dụng phụ là in dòng chữ.

## 6. Khi handler tự tạo giá trị trả về

Không phải mọi nhánh trong handler đều gọi `invokeDefault`. Handler có thể tự xử lý phương thức trừu tượng hoặc thay thế hành vi mặc định. Trong trường hợp đó, kiểu trả về phải phù hợp với chữ ký interface.

| Kiểu trả về của interface | Giá trị handler cần trả |
|---|---|
| `int` | `Integer` |
| `long` | `Long` |
| `boolean` | `Boolean` |
| `double` | `Double` |
| `char` | `Character` |
| Kiểu tham chiếu | Đối tượng tương thích với kiểu khai báo, hoặc `null` nếu hợp đồng cho phép |
| `void` | Thường trả `null`; giá trị bị bỏ qua |

Ví dụ handler tự xử lý phương thức primitive:

```java
if (method.getName().equals("count")
        && method.getReturnType() == int.class) {
    return Integer.valueOf(5);
}
```

Nếu handler trả về wrapper sai kiểu, proxy có thể ném `ClassCastException` khi chuyển kết quả. Nếu phương thức trả về primitive mà handler trả `null`, thao tác unboxing có thể ném `NullPointerException`. Đây là lỗi ở thời điểm thực thi, không phải chuyển đổi tự động giữa các wrapper khác nhau.

Với kiểu tham chiếu, `null` có thể được trả về về mặt kỹ thuật, nhưng ứng dụng vẫn cần tuân thủ hợp đồng của phương thức, chẳng hạn yêu cầu không null hoặc các annotation/kiểm tra runtime riêng.

## 7. Kiểm tra kiểu khi cần xử lý tổng quát

Nếu handler có chính sách chung cho nhiều interface, có thể dùng reflection để đọc kiểu tham số và kiểu trả về:

```java
Class<?> returnType = method.getReturnType();
Class<?>[] parameterTypes = method.getParameterTypes();

boolean returnsVoid = returnType == void.class;
boolean returnsPrimitive = returnType.isPrimitive()
        && returnType != void.class;
```

`getParameterTypes()` cho biết chữ ký primitive hay reference. Các giá trị thực tế trong `args` vẫn là object, nên cần xem wrapper tương ứng nếu muốn kiểm tra hoặc biến đổi dữ liệu. Không cần thực hiện các kiểm tra này khi chỉ chuyển tiếp nguyên trạng đến `invokeDefault`; việc kiểm tra bổ sung hữu ích khi handler tự xây dựng kết quả hoặc áp dụng chính sách riêng.

## 8. Ngoại lệ và lưu ý khi vận hành

`InvocationHandler.invokeDefault` khai báo `throws Throwable`. Nếu phần thân default method ném ngoại lệ, handler có thể để ngoại lệ truyền ra hoặc bắt lại để áp dụng chính sách của ứng dụng. Dynamic proxy tiếp tục áp dụng quy tắc checked exception theo khai báo `throws` của phương thức interface; checked exception không được khai báo phù hợp có thể bị bọc trong `UndeclaredThrowableException` khi client nhận lỗi.

Một số lưu ý thực tế:

- Dùng đúng đối tượng `proxy` nhận từ handler để phần thân default method chạy trên proxy.
- Kiểm tra `method.isDefault()` trước khi gọi `invokeDefault`.
- Với phương thức không tham số, chuyển `args == null` thành `new Object[0]`.
- Giữ nguyên wrapper của primitive khi chuyển tiếp đối số; nếu tự tạo kết quả thì trả đúng wrapper.
- Không trả `null` cho phương thức có kiểu trả về primitive.
- Với phương thức `void`, tập trung vào tác dụng phụ và xử lý ngoại lệ; không có giá trị trả về cho client.

Hiểu rõ boxing, unboxing và giá trị `void` giúp handler chuyển tiếp default method chính xác. Khi chỉ cần chạy phần thân mặc định, hãy giữ nguyên đối số và trả trực tiếp kết quả của `InvocationHandler.invokeDefault`; chỉ can thiệp kiểu dữ liệu khi chính sách của ứng dụng thực sự yêu cầu.
