# Chọn default method khi proxy triển khai nhiều interface

Một dynamic proxy có thể triển khai nhiều interface cùng lúc. Nếu các interface khai báo phương thức trùng chữ ký, `InvocationHandler` cần xác định phần triển khai nào sẽ được thực thi. Trường hợp có nhiều default method cùng tên và cùng danh sách kiểu tham số đặc biệt cần được xử lý tường minh: thứ tự interface khi tạo proxy ảnh hưởng đến đối tượng `Method` mà handler nhận được, còn `InvocationHandler.invokeDefault` cho phép chọn default method cụ thể thuộc hệ interface của proxy.

Đây là cơ chế được hỗ trợ trên các JDK hiện đại. `InvocationHandler.invokeDefault` có từ Java 16 và là API công khai để gọi phần thân default method trên dynamic proxy.

## 1. Một proxy có thể triển khai nhiều interface

`Proxy.newProxyInstance` nhận một mảng interface. Lớp proxy do JDK tạo sẽ triển khai tất cả interface trong mảng đó và chuyển các lời gọi phương thức instance đến cùng một `InvocationHandler`.

```java
Object proxy = Proxy.newProxyInstance(
        classLoader,
        new Class<?>[]{FirstService.class, SecondService.class},
        handler);
```

Client có thể ép kiểu proxy sang bất kỳ interface nào trong danh sách. Tuy nhiên, nếu hai interface khai báo phương thức có cùng tên và cùng kiểu tham số, handler không nhận được thông tin trực tiếp cho biết client đã gọi qua biến có kiểu interface nào.

## 2. Quy tắc chọn Method khi chữ ký bị trùng

Khi nhiều interface của proxy khai báo một phương thức có cùng tên và cùng danh sách kiểu tham số, thứ tự interface trong mảng truyền vào `Proxy.newProxyInstance` quyết định `Method` nào được chuyển đến `InvocationHandler.invoke`. JDK dùng phương thức từ interface xuất hiện đầu tiên trong danh sách có chứa chữ ký đó.

Ví dụ hai interface cùng khai báo `status()`:

```java
public interface LegacyStatus {
    String status();
}

public interface DefaultStatus {
    default String status() {
        return "READY";
    }
}
```

Tạo proxy theo thứ tự:

```java
new Class<?>[]{LegacyStatus.class, DefaultStatus.class}
```

Khi client gọi `status()` trên proxy, handler nhận `Method` được khai báo bởi `LegacyStatus`, vì interface này đứng trước. Do đó:

```java
method.getDeclaringClass() == LegacyStatus.class
method.isDefault() == false
```

Điều này vẫn đúng nếu client gọi qua biến kiểu `DefaultStatus`. Tham chiếu phía client không làm thay đổi `Method` mà proxy chuyển đến handler.

Đây là điểm dễ gây lỗi nếu handler chỉ dựa vào `method.isDefault()`: default method của interface đứng sau có thể không được nhận diện qua `Method` mà handler nhận ban đầu.

## 3. Chọn rõ default method bằng Method của interface mong muốn

Nếu proxy triển khai `DefaultStatus`, handler có thể lấy trực tiếp phương thức từ interface đó rồi truyền vào `InvocationHandler.invokeDefault`:

```java
Method selectedDefault = DefaultStatus.class.getMethod("status");

InvocationHandler handler = (proxy, method, args) -> {
    if (method.getName().equals("status")
            && method.getParameterCount() == 0) {
        Object[] actualArgs = args == null ? new Object[0] : args;
        return InvocationHandler.invokeDefault(
                proxy, selectedDefault, actualArgs);
    }

    throw new UnsupportedOperationException(method.toString());
};
```

`selectedDefault` là default method được khai báo trong `DefaultStatus`, và `DefaultStatus` nằm trong danh sách interface mà proxy triển khai. Vì thế handler có thể yêu cầu chạy phần thân mặc định đó ngay cả khi `Method` ban đầu trong `invoke` đến từ `LegacyStatus`.

Khi chọn thủ công, cần bảo đảm:

- Interface khai báo phương thức được proxy triển khai trực tiếp hoặc thông qua kế thừa.
- `Method` được chọn thực sự là default method.
- Chữ ký được chọn đúng overload, bao gồm kiểu và thứ tự tham số.
- Đối số truyền vào phù hợp với phương thức được chọn.

Không chọn phương thức chỉ bằng tên khi interface có overload. Dùng `getMethod(name, parameterTypes...)` để lấy đúng chữ ký.

## 4. Ví dụ hoàn chỉnh: interface đầu tiên khai báo abstract, interface sau có default

Ví dụ sau cho thấy `method.isDefault()` có thể là `false` dù một interface khác mà proxy triển khai có default method cùng chữ ký. Handler chọn default method từ `DefaultStatus` một cách tường minh.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class MultipleInterfaceDefaultDemo {
    public interface LegacyStatus {
        String status();
    }

    public interface DefaultStatus {
        default String status() {
            return "READY";
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        // Lấy đúng default method từ interface mong muốn.
        Method selectedDefault = DefaultStatus.class.getMethod("status");

        InvocationHandler handler = (proxy, method, arguments) -> {
            System.out.println("Method from: "
                    + method.getDeclaringClass().getSimpleName());
            System.out.println("Received method is default: "
                    + method.isDefault());

            if (method.getName().equals("status")
                    && method.getParameterCount() == 0) {
                Object[] actualArgs = arguments == null
                        ? new Object[0]
                        : arguments;
                return InvocationHandler.invokeDefault(
                        proxy, selectedDefault, actualArgs);
            }

            throw new UnsupportedOperationException(method.toString());
        };

        Object proxy = Proxy.newProxyInstance(
                LegacyStatus.class.getClassLoader(),
                new Class<?>[]{LegacyStatus.class, DefaultStatus.class},
                handler);

        LegacyStatus service = (LegacyStatus) proxy;
        System.out.println("Result: " + service.status());
    }
}
```

Kết quả:

```text
Method from: LegacyStatus
Received method is default: false
Result: READY
```

Mặc dù `Method` mà handler nhận được mô tả phương thức abstract của `LegacyStatus`, handler vẫn gọi được phần thân `DefaultStatus.status()` vì proxy triển khai interface đó. Điều kiện là `selectedDefault` phải là default method hợp lệ thuộc hệ interface của proxy.

## 5. Khi nhiều interface đều có default method trùng chữ ký

Hai interface độc lập cũng có thể cung cấp hai cách triển khai mặc định:

```java
public interface ShortLabel {
    default String label() {
        return "Short";
    }
}

public interface DetailedLabel {
    default String label() {
        return "Detailed";
    }
}
```

Dynamic proxy có thể triển khai cả hai interface vì lớp proxy tự định nghĩa phương thức chuyển tiếp đến handler. Handler cần đặt ra chính sách lựa chọn, ví dụ luôn ưu tiên `DetailedLabel`:

```java
Method preferred = DetailedLabel.class.getMethod("label");

InvocationHandler handler = (proxy, method, args) -> {
    if (method.getName().equals("label")
            && method.getParameterCount() == 0) {
        return InvocationHandler.invokeDefault(
                proxy, preferred,
                args == null ? new Object[0] : args);
    }
    throw new UnsupportedOperationException(method.toString());
};
```

Nếu chính sách nghiệp vụ cần chọn `ShortLabel`, chỉ cần lấy `ShortLabel.class.getMethod("label")` làm `preferred`. Việc chọn rõ interface giúp kết quả không phụ thuộc thứ tự interface trong mảng proxy.

## 6. Khi interface con ghi đè default method của interface cha

Quan hệ kế thừa cũng tạo ra nhiều phần thân có thể lựa chọn:

```java
public interface BaseMessage {
    default String message() {
        return "Base";
    }
}

public interface CustomMessage extends BaseMessage {
    @Override
    default String message() {
        return "Custom";
    }
}
```

Nếu một lớp triển khai `CustomMessage` trực tiếp, Java chọn phần triển khai cụ thể hơn là `CustomMessage.message()`. Với dynamic proxy, lời gọi vẫn được chuyển đến handler; `Method` nhận được mô tả khai báo phù hợp trong hệ interface, và handler quyết định phần thân nào sẽ chạy. Khi cần gọi rõ phần thân ở interface cha, handler có thể lấy `Method` từ `BaseMessage`:

```java
Method baseMethod = BaseMessage.class.getMethod("message");
Object result = InvocationHandler.invokeDefault(
        proxy, baseMethod);
```

`BaseMessage` là superinterface của interface mà proxy triển khai, nên phương thức mặc định của nó có thể được chọn tường minh. Đây là một cách dùng hữu ích khi muốn giữ lại hành vi gốc của interface cha trong khi interface con đã cung cấp một default method khác.

## 7. Thiết kế chính sách chọn phương thức

Khi proxy triển khai nhiều interface, nên xác định quy tắc chọn default method ngay trong handler. Một số chính sách phổ biến:

| Tình huống | Chính sách xử lý |
|---|---|
| Chỉ có một default method phù hợp | Có thể dùng `method` nhận từ handler nếu `method.isDefault()` là `true`. |
| Interface đầu tiên khai báo abstract, interface sau có default cùng chữ ký | Lấy `Method` từ interface có default method và gọi tường minh. |
| Nhiều interface độc lập có default method cùng chữ ký | Chọn interface ưu tiên theo nghiệp vụ hoặc từ chối lời gọi nếu không có quy tắc rõ ràng. |
| Interface con ghi đè default method của interface cha | Dùng `Method` của interface con cho hành vi mới, hoặc `Method` của interface cha nếu cần gọi phần thân gốc. |
| Có overload | Chọn bằng tên cùng kiểu tham số chính xác, không chỉ bằng tên. |

Với proxy dùng chung cho nhiều luồng, chính sách chọn method nên bất biến hoặc được bảo vệ khi có trạng thái cấu hình mutable. Có thể chuẩn bị sẵn các đối tượng `Method` trước khi tạo handler thay vì tra cứu reflection lặp lại trong từng lời gọi.

## 8. Điều kiện và giới hạn cần nhớ

- `InvocationHandler.invokeDefault` có từ Java 16; cần chạy trên JDK 16 trở lên để sử dụng.
- `proxy` phải là đối tượng dynamic proxy hiện tại.
- `method` phải đại diện cho default method được khai báo trong interface mà proxy triển khai trực tiếp hoặc kế thừa.
- Đối số phải tương thích với chữ ký của default method được chọn.
- Với các phương thức trùng tên và tham số, thứ tự interface trong mảng tạo proxy ảnh hưởng đến `Method` ban đầu được chuyển cho handler.
- `method.isDefault()` chỉ kiểm tra `Method` đang cầm; nó không tìm kiếm các default method trùng chữ ký trong những interface khác.

Khi cần kết quả xác định trong proxy đa interface, hãy chọn rõ `Method` từ interface mong muốn và gọi bằng `InvocationHandler.invokeDefault`. Cách này giúp handler kiểm soát chính xác phần thân default method được thực thi, kể cả khi nhiều interface cung cấp cùng một chữ ký.
