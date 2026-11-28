# Gọi default method qua invokeDefault với đúng proxy, method và args

Java 16 bổ sung `InvocationHandler.invokeDefault` để `InvocationHandler` có thể gọi phần thân của một default method trên dynamic proxy. Khi dùng API này, ba đầu vào `proxy`, `method` và `args` phải mô tả đúng lời gọi đang được xử lý: đối tượng proxy hiện tại, default method thuộc hệ interface của proxy và các đối số đúng thứ tự, đúng kiểu.

API này vẫn được hỗ trợ trong các JDK hiện đại. Nó đặc biệt hữu ích khi handler cần ghi log, kiểm tra quyền hoặc bổ sung chính sách chung rồi vẫn muốn chạy hành vi mặc định đã được định nghĩa trong interface.

## 1. Chữ ký và ý nghĩa của ba tham số

Chữ ký API:

```java
public static Object invokeDefault(
        Object proxy,
        Method method,
        Object... args) throws Throwable
```

| Tham số | Giá trị cần truyền | Vai trò |
|---|---|---|
| `proxy` | Đối số `proxy` nhận được trong `InvocationHandler.invoke` | Đối tượng dynamic proxy mà default method sẽ chạy trên đó. |
| `method` | Đối số `method` nhận được trong `InvocationHandler.invoke` | `Method` đại diện cho default method cần gọi. |
| `args` | Đối số `args` nhận được trong `InvocationHandler.invoke` | Các tham số thực tế của lời gọi, giữ nguyên thứ tự và cấu trúc. |

Trong một handler thông thường, cách chuyển tiếp an toàn là:

```java
if (method.isDefault()) {
    Object[] actualArgs = args == null ? new Object[0] : args;
    return InvocationHandler.invokeDefault(proxy, method, actualArgs);
}
```

Điều kiện `method.isDefault()` giúp handler chỉ gọi API này cho default method. Chuẩn hóa `args == null` thành mảng rỗng thể hiện rõ trường hợp phương thức không có tham số và tránh truyền một mảng `null` vào tham số varargs.

## 2. Truyền đúng proxy

Đối số `proxy` phải là chính đối tượng proxy mà JDK chuyển vào `InvocationHandler.invoke`. Đây là đối tượng nhận lời gọi và là đối tượng mà phần thân default method nhìn thấy qua `this`.

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.isDefault()) {
        Object[] actualArgs = args == null ? new Object[0] : args;
        return InvocationHandler.invokeDefault(proxy, method, actualArgs);
    }

    // Xử lý các phương thức còn lại.
    return null;
};
```

Không thay `proxy` bằng đối tượng implementation thật mà handler đang giữ. `invokeDefault` chạy phần thân default method trên proxy; nó không dùng để gọi phương thức trên target. Nếu truyền một đối tượng thông thường thay cho dynamic proxy, lời gọi không hợp lệ.

Điều này ảnh hưởng đến các lời gọi bên trong default method. Ví dụ, nếu default method gọi `this.load()`, lời gọi `load()` tiếp tục đi qua proxy và được chuyển đến handler. Handler có thể xử lý `load()` hoặc ủy quyền đến target theo chính sách của ứng dụng.

## 3. Truyền đúng Method

`method` phải đại diện cho default method thuộc một interface mà proxy triển khai trực tiếp hoặc thông qua kế thừa. Trong `InvocationHandler.invoke`, JDK đã cung cấp `Method` tương ứng với lời gọi được chuyển đến handler, vì vậy thông thường nên dùng chính đối số này.

```java
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(
            proxy,
            method,
            args == null ? new Object[0] : args);
}
```

Nếu cần chọn một default method cụ thể theo chính sách riêng, có thể lấy `Method` từ interface tương ứng:

```java
Method defaultMethod = Greeting.class.getMethod("greeting", String.class);
Object result = InvocationHandler.invokeDefault(
        proxy, defaultMethod, "An");
```

Trong ví dụ này, `Greeting` phải thuộc hệ interface mà proxy triển khai và `greeting(String)` phải là default method hợp lệ. Khi lấy `Method` thủ công, cần kiểm tra đúng tên, kiểu tham số và interface khai báo phương thức; không chỉ chọn theo tên vì interface có thể có overload.

Các trường hợp sau không phù hợp:

- `method` mô tả phương thức trừu tượng, phương thức static hoặc phương thức của class thay vì default method.
- Interface khai báo `method` không thuộc các interface mà proxy triển khai hoặc kế thừa.
- Dùng một `Method` khác chữ ký với lời gọi mà handler đang xử lý, dẫn đến truyền đối số không tương thích.

Có thể kiểm tra metadata trước khi gọi:

```java
System.out.println(method.isDefault());
System.out.println(method.getDeclaringClass().getName());
System.out.println(java.util.Arrays.toString(method.getParameterTypes()));
```

`isDefault()` xác nhận loại phương thức, `getDeclaringClass()` cho biết interface khai báo nó và `getParameterTypes()` giúp xác nhận chữ ký cần truyền đối số.

## 4. Truyền đúng args, kể cả phương thức không có tham số và varargs

`args` của `InvocationHandler.invoke` là mảng các đối số của lời gọi. Mảng có thể là `null` khi phương thức không có tham số. Với phương thức có tham số, mỗi phần tử phải đúng thứ tự và tương thích với kiểu tham số tương ứng.

Ví dụ:

```java
public interface Greeting {
    default String greeting(String name, int count) {
        return "Hello " + name + " x" + count;
    }

    default String status() {
        return "READY";
    }
}
```

Khi handler nhận lời gọi `greeting("An", 2)`, `args` có hai phần tử: chuỗi `"An"` và giá trị số được đóng gói thành `Integer`. Khi nhận lời gọi `status()`, `args` có thể là `null`; hãy chuyển thành `new Object[0]` trước khi gọi `invokeDefault`.

Phương thức varargs cần chú ý thêm một cấp mảng:

```java
public interface LabelService {
    default String join(String... labels) {
        return String.join("-", labels);
    }
}
```

Với lời gọi `proxy.join("A", "B")`, phương thức có một tham số kiểu `String[]`. Mảng `args` nhận trong handler là mảng ngoài chứa một phần tử; phần tử đó là `String[] {"A", "B"}`. Hãy chuyển tiếp nguyên mảng `args` này. Không tự tách các phần tử của `String[]` thành nhiều phần tử ở cấp ngoài, vì như vậy chữ ký lời gọi sẽ sai.

Quy tắc thực hành:

- Không có tham số: dùng `new Object[0]`.
- Có tham số thông thường: giữ nguyên mảng `args` nhận được.
- Có tham số varargs: giữ nguyên cả mảng ngoài và mảng varargs nằm trong phần tử tương ứng.
- Chỉ thay đổi đối số khi logic nghiệp vụ chủ đích yêu cầu; bảo đảm số lượng, thứ tự và kiểu tương thích với `Method`.

## 5. Ví dụ hoàn chỉnh trong InvocationHandler

Ví dụ sau minh họa cả ba trường hợp: default method gọi phương thức trừu tượng, default method không có tham số và default method dùng varargs. Handler dùng đúng đối tượng proxy, `Method` do JDK cung cấp và mảng đối số nhận được.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class InvokeDefaultArgumentsDemo {
    public interface GreetingService {
        String normalize(String name);

        default String greeting(String name) {
            return "Hello " + normalize(name);
        }

        default String status() {
            return "READY";
        }

        default String join(String... values) {
            return String.join("-", values);
        }
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, arguments) -> {
            if (method.isDefault()) {
                Object[] actualArgs = arguments == null
                        ? new Object[0]
                        : arguments;
                return InvocationHandler.invokeDefault(
                        proxy, method, actualArgs);
            }

            if (method.getName().equals("normalize")
                    && method.getParameterCount() == 1) {
                return ((String) arguments[0]).toUpperCase();
            }

            throw new UnsupportedOperationException(method.toString());
        };

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[]{GreetingService.class},
                handler);

        System.out.println(service.greeting("An"));
        System.out.println(service.status());
        System.out.println(service.join("A", "B"));
    }
}
```

Kết quả:

```text
Hello AN
READY
A-B
```

Khi gọi `greeting("An")`, handler chuyển lời gọi đến default method. Phần thân `greeting` gọi `normalize` trên `this`, tức proxy, nên handler nhận thêm lời gọi `normalize` và xử lý theo nhánh nghiệp vụ. Khi gọi `status()`, handler chuyển mảng rỗng. Khi gọi `join("A", "B")`, handler chuyển nguyên cấu trúc đối số varargs.

## 6. Điều kiện và lỗi khi truyền sai tham số

Để `invokeDefault` hoạt động, cần thỏa mãn các điều kiện chính:

1. `proxy` là dynamic proxy được tạo bởi cơ chế `Proxy` của Java.
2. `method` là default method được khai báo trong một interface mà proxy triển khai trực tiếp hoặc kế thừa.
3. Số lượng và kiểu của `args` phù hợp với danh sách tham số của `method`.
4. Default method có thể được truy cập và gọi trong ngữ cảnh module/class loader của ứng dụng.

Nếu truyền đối tượng không phải proxy, phương thức không phải default method hoặc interface khai báo phương thức không thuộc hệ interface của proxy, lời gọi không hợp lệ và có thể ném `IllegalArgumentException`. Nếu truyền số lượng hoặc kiểu đối số không phù hợp, lời gọi cũng thất bại thay vì tự chuyển đổi theo ý muốn của ứng dụng.

`invokeDefault` khai báo `throws Throwable`. Ngoại lệ do chính default method ném ra được truyền ra từ lời gọi này; API không bọc ngoại lệ của phương thức đích trong `InvocationTargetException` như `Method.invoke`. Handler có thể chuyển tiếp ngoại lệ bằng cách để nó thoát khỏi lambda hoặc dùng `try/catch` để áp dụng chính sách riêng. Sau đó, dynamic proxy vẫn áp dụng quy tắc của Java đối với checked exception không được khai báo trong `throws` của phương thức interface; trường hợp không tương thích có thể dẫn đến `UndeclaredThrowableException` ở phía client.

## 7. Những cách gọi dễ sai

| Cách gọi | Vấn đề | Cách làm đúng |
|---|---|---|
| `invokeDefault(target, method, args)` | `target` là implementation thông thường, không phải proxy đang xử lý lời gọi. | Truyền `proxy` nhận từ handler. |
| `invokeDefault(proxy, abstractMethod, args)` | Phương thức không có phần thân default. | Kiểm tra `method.isDefault()` trước khi gọi. |
| `invokeDefault(proxy, method, null)` cho phương thức không tham số | Truyền mảng varargs `null`, làm ý nghĩa đối số không rõ ràng. | Dùng `new Object[0]`. |
| Bỏ hoặc đổi thứ tự phần tử `args` | Đối số không còn khớp chữ ký phương thức. | Chuyển tiếp nguyên mảng nếu không cần biến đổi. |
| Tách mảng varargs thành nhiều phần tử cấp ngoài | Sai cấu trúc: phương thức varargs vẫn có một tham số mảng ở cấp chữ ký. | Giữ nguyên mảng đối số nhận từ handler. |
| `method.invoke(proxy, args)` | Lời gọi lại phương thức proxy và có thể quay lại handler vô hạn. | Dùng `InvocationHandler.invokeDefault`. |

## 8. Ghi nhớ khi triển khai

- Lấy `proxy`, `method`, `args` trực tiếp từ `InvocationHandler.invoke` trong trường hợp chuyển tiếp thông thường.
- Kiểm tra `method.isDefault()` trước khi gọi `invokeDefault`.
- Chuẩn hóa `args == null` thành mảng rỗng; giữ nguyên thứ tự và cấu trúc các đối số còn lại.
- Truyền đúng proxy vì default method chạy trên proxy và lời gọi tiếp theo trên `this` có thể quay lại handler.
- Chỉ chọn `Method` thủ công khi có lý do rõ ràng; xác nhận interface khai báo nó thuộc hệ interface của proxy và chữ ký phù hợp.
- Dùng `InvocationHandler.invokeDefault` trên Java 16 trở lên; đây là API công khai, ổn định để gọi default method trong dynamic proxy.

Khi ba tham số được truyền đúng, handler có thể gọi phần thân default method một cách tường minh, giữ nguyên hành vi của interface và kết hợp nó với các chính sách xử lý của ứng dụng.
