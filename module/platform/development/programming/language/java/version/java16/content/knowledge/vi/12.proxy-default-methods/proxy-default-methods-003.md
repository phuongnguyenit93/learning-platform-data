# Nhận diện default method bằng Method.isDefault

Reflection trong Java cung cấp `Method.isDefault()` để xác định một đối tượng `Method` có đại diện cho default method được khai báo trong interface hay không. API này có từ Java 8 và vẫn được hỗ trợ trên các JDK hiện đại.

Trong dynamic proxy, `InvocationHandler` nhận một đối tượng `Method` cho mỗi lời gọi được chuyển đến handler. Kiểm tra `method.isDefault()` giúp handler nhận ra lời gọi đang tương ứng với default method. Từ Java 16, handler có thể gọi phần thân phương thức đó bằng `InvocationHandler.invokeDefault`.

Hai việc cần phân biệt: `isDefault()` chỉ nhận diện loại phương thức mà `Method` mô tả; nó không tự thực thi phần thân phương thức. Cách thực thi phụ thuộc vào ngữ cảnh, đặc biệt là khi phương thức được gọi qua dynamic proxy.

## 1. Default method trong interface

Default method là phương thức instance được khai báo trong interface bằng từ khóa `default` và có phần thân. Nó cho phép interface bổ sung hành vi dùng chung mà vẫn hỗ trợ các lớp triển khai hiện có.

```java
public interface UserView {
    String userName();

    default String displayName() {
        return "User: " + userName();
    }

    static String viewType() {
        return "USER";
    }
}
```

Trong interface trên:

- `userName()` là phương thức trừu tượng, không có phần thân.
- `displayName()` là default method vì được khai báo với `default` và có phần thân.
- `viewType()` là phương thức `static` của interface, không phải default method.

Một lớp triển khai `UserView` có thể kế thừa phần thân `displayName()` hoặc ghi đè phương thức đó. Phương thức `static` được gọi thông qua tên interface, không phải qua một đối tượng triển khai.

## 2. Dùng Method.isDefault để nhận diện

`Class.getMethod` trả về đối tượng `Method` mô tả một phương thức public theo tên và kiểu tham số. Sau đó có thể gọi `isDefault()` để kiểm tra:

```java
import java.lang.reflect.Method;

public class DefaultMethodReflectionDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Method displayName = UserView.class.getMethod("displayName");
        Method userName = UserView.class.getMethod("userName");
        Method viewType = UserView.class.getMethod("viewType");

        System.out.println(displayName.isDefault()); // true
        System.out.println(userName.isDefault());    // false
        System.out.println(viewType.isDefault());    // false
    }
}
```

Kết quả:

```text
true
false
false
```

`isDefault()` trả về `true` khi đối tượng `Method` đại diện cho một default method của interface. Phương thức trừu tượng và phương thức `static` không phải default method nên trả về `false`.

API này có từ Java 8. Nếu chỉ cần nhận diện default method, không cần suy luận bằng cách kết hợp `Modifier.isAbstract`, `Modifier.isStatic` hoặc kiểm tra tên phương thức. Những cách đó không thể thay thế chính xác ý nghĩa mà `Method.isDefault()` cung cấp.

## 3. Liệt kê default method của một interface

Có thể dùng `Class.getMethods()` để duyệt các phương thức public mà interface khai báo hoặc kế thừa, rồi lọc bằng `isDefault()`:

```java
import java.lang.reflect.Method;

public static void printDefaultMethods(Class<?> type) {
    for (Method method : type.getMethods()) {
        if (method.isDefault()) {
            System.out.println(
                    method.getDeclaringClass().getSimpleName()
                            + "#" + method.getName());
        }
    }
}
```

`getMethods()` bao gồm các phương thức public kế thừa từ interface cha. Ngược lại, `getDeclaredMethods()` chỉ trả về các phương thức được khai báo trực tiếp trong kiểu đang xét; nó không tự liệt kê các phương thức kế thừa từ interface cha.

Ví dụ:

```java
public interface BaseView {
    default String category() {
        return "base";
    }
}

public interface DetailedView extends BaseView {
    default String description() {
        return "details";
    }
}
```

Khi duyệt `DetailedView.class.getMethods()`, có thể nhận được cả `description()` và `category()`. Với `category()`, `method.getDeclaringClass()` là `BaseView`, vì đó là interface thực sự khai báo phương thức. Thuộc tính này hữu ích khi cần biết default method đến từ interface nào trong hệ kế thừa.

## 4. Dùng isDefault trong InvocationHandler

Khi một phương thức được gọi trên dynamic proxy, JDK chuyển lời gọi đến `InvocationHandler.invoke`. Tham số `method` cho biết phương thức tương ứng. Handler có thể kiểm tra `isDefault()` để phân nhánh giữa default method và phương thức nghiệp vụ thông thường.

Ví dụ sau dùng Java 16 trở lên để gọi phần thân default method trên proxy:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyDefaultDetectionDemo {
    public interface UserView {
        String userName();

        default String displayName() {
            return "User: " + userName();
        }
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, arguments) -> {
            if (method.isDefault()) {
                Object[] actualArguments = arguments == null
                        ? new Object[0]
                        : arguments;
                return InvocationHandler.invokeDefault(
                        proxy, method, actualArguments);
            }

            if (method.getName().equals("userName")
                    && method.getParameterCount() == 0) {
                return "An";
            }

            throw new UnsupportedOperationException(method.toString());
        };

        UserView user = (UserView) Proxy.newProxyInstance(
                UserView.class.getClassLoader(),
                new Class<?>[]{UserView.class},
                handler);

        System.out.println(user.displayName());
    }
}
```

Kết quả:

```text
User: An
```

Luồng xử lý:

1. Client gọi `user.displayName()` trên proxy.
2. Handler nhận `Method` mô tả `displayName`; `method.isDefault()` trả về `true`.
3. `InvocationHandler.invokeDefault` thực thi phần thân default method với proxy làm đối tượng nhận lời gọi.
4. Bên trong `displayName`, lời gọi `userName()` tiếp tục đi qua proxy và quay lại handler.
5. `userName()` là phương thức trừu tượng nên `isDefault()` trả về `false`; handler xử lý và trả về `"An"`.

`InvocationHandler.invokeDefault` được bổ sung từ Java 16. Vì vậy, `Method.isDefault()` có thể dùng từ Java 8 để nhận diện, còn ví dụ gọi default method qua API chuẩn này cần JDK 16 trở lên.

## 5. Default method kế thừa và phương thức ghi đè

Default method có thể được kế thừa từ interface cha. Khi lấy phương thức qua interface con, `Method.getDeclaringClass()` cho biết interface khai báo phương thức đó.

```java
public interface BaseStatus {
    default String status() {
        return "BASE";
    }
}

public interface CurrentStatus extends BaseStatus {
    // Kế thừa status() từ BaseStatus.
}
```

Kiểm tra:

```java
import java.lang.reflect.Method;

Method status = CurrentStatus.class.getMethod("status");

System.out.println(status.isDefault());
System.out.println(status.getDeclaringClass().getSimpleName());
```

Kết quả:

```text
true
BaseStatus
```

Nếu interface con ghi đè default method, `Method` lấy từ interface con sẽ mô tả phần khai báo ở interface con:

```java
public interface CurrentStatus extends BaseStatus {
    @Override
    default String status() {
        return "CURRENT";
    }
}
```

Khi đó `CurrentStatus.class.getMethod("status").getDeclaringClass()` trả về `CurrentStatus`, và `isDefault()` vẫn là `true`.

Trong handler, `isDefault()` cho biết phương thức được chuyển đến có phải default method hay không; `getDeclaringClass()` cho biết interface khai báo phương thức. Nếu proxy triển khai nhiều interface có phương thức trùng chữ ký, quy tắc chọn `Method` của dynamic proxy còn phụ thuộc thứ tự interface khi tạo proxy. Không nên dùng riêng tên phương thức để suy ra interface gốc.

## 6. isDefault không đồng nghĩa với thực thi default method

`Method.isDefault()` chỉ trả lời câu hỏi về đối tượng `Method`. Nó không gọi phương thức và cũng không quyết định mọi lời gọi trên một đối tượng bất kỳ sẽ chạy phần thân default method.

Ví dụ một lớp có thể ghi đè default method:

```java
public class CustomStatus implements BaseStatus {
    @Override
    public String status() {
        return "CUSTOM";
    }
}
```

Hai đối tượng `Method` sau mô tả hai khai báo khác nhau:

```java
import java.lang.reflect.Method;

Method interfaceMethod = BaseStatus.class.getMethod("status");
Method classMethod = CustomStatus.class.getMethod("status");

System.out.println(interfaceMethod.isDefault()); // true
System.out.println(classMethod.isDefault());     // false
```

`interfaceMethod` đại diện cho default method được khai báo trong interface. `classMethod` đại diện cho phương thức cụ thể do lớp ghi đè. Khi gọi `status()` trên một đối tượng `CustomStatus`, Java thực thi phần ghi đè của lớp.

Với dynamic proxy, nếu handler muốn thực thi phần thân default method, trên Java 16 trở lên hãy dùng `InvocationHandler.invokeDefault(proxy, method, args)`. Không dùng `method.invoke(proxy, args)` để thay thế: lời gọi reflection đó lại gọi phương thức trên proxy, có thể quay lại handler và gây đệ quy vô hạn.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `isDefault()` trả về `true` nghĩa là phương thức đã được chạy. | Đây chỉ là phép kiểm tra metadata; muốn gọi phải thực hiện lời gọi phù hợp với ngữ cảnh. |
| Phương thức không abstract thì chắc chắn là default method. | Phương thức `static` của interface và phương thức cụ thể của class cũng không abstract nhưng không phải default method. |
| Phương thức `static` trong interface là default method. | Phương thức `static` được gọi qua interface và `isDefault()` trả về `false`. |
| Default method kế thừa luôn được khai báo ở interface con. | `getDeclaringClass()` chỉ ra interface thực sự khai báo phương thức; có thể là interface cha. |
| `isDefault()` là API mới của Java 16. | `Method.isDefault()` có từ Java 8; API Java 16 liên quan đến việc gọi default method trên proxy là `InvocationHandler.invokeDefault`. |

## 8. Khi nào nên dùng?

`Method.isDefault()` hữu ích trong các tình huống sau:

- Xây dựng `InvocationHandler` cần phân biệt default method với phương thức trừu tượng.
- Kiểm tra hoặc liệt kê hành vi mặc định được khai báo trong một interface và các interface cha.
- Viết framework hoặc thư viện dùng reflection để phân tích hợp đồng interface.
- Xác định interface khai báo phương thức bằng cách kết hợp `isDefault()` với `getDeclaringClass()`.

Khi xử lý dynamic proxy trên JDK hiện đại, hãy dùng `method.isDefault()` để nhận diện default method và `InvocationHandler.invokeDefault` để gọi phần thân khi cần. Cách này dựa trên API reflection và proxy công khai của Java, không phụ thuộc vào thủ thuật truy cập nội bộ của JDK.
