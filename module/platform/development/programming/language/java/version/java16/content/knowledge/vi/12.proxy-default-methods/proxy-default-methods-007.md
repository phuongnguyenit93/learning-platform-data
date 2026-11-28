# Default method kế thừa, bị override và tác động khi interface thay đổi

Default method cho phép interface cung cấp phần triển khai dùng chung. Khi một lớp triển khai interface hoặc một interface con kế thừa interface cha, Java áp dụng các quy tắc xác định phần thân nào được dùng. Nắm được thứ tự ưu tiên giữa phương thức của class, default method cụ thể hơn và các interface độc lập giúp tránh xung đột khi thiết kế API.

Các quy tắc kế thừa và ghi đè default method vẫn áp dụng trên các JDK hiện đại. Từ Java 16, dynamic proxy còn có `InvocationHandler.invokeDefault` để handler chọn và gọi một default method cụ thể thuộc hệ interface mà proxy triển khai.

## 1. Default method được kế thừa từ interface cha

Một interface con kế thừa default method từ interface cha nếu không khai báo phương thức ghi đè cùng chữ ký.

```java
public interface BaseMessage {
    default String message() {
        return "Message from Base";
    }
}

public interface UserMessage extends BaseMessage {
    // Kế thừa message() từ BaseMessage.
}

public class UserMessageImpl implements UserMessage {
    // Không cần triển khai message().
}
```

Khi gọi:

```java
UserMessage user = new UserMessageImpl();
System.out.println(user.message());
```

Kết quả:

```text
Message from Base
```

Phương thức được kế thừa vẫn là default method do `BaseMessage` khai báo. Có thể dùng reflection để xác định interface khai báo phương thức:

```java
import java.lang.reflect.Method;

Method method = UserMessage.class.getMethod("message");
System.out.println(method.isDefault());
System.out.println(method.getDeclaringClass().getSimpleName());
```

Kết quả là `true` và `BaseMessage`. `getDeclaringClass()` cho biết nơi khai báo phương thức, không nhất thiết là interface mà client đang dùng làm kiểu tham chiếu.

## 2. Default method ở interface con ghi đè phương thức của interface cha

Interface con có thể định nghĩa default method cùng chữ ký để thay thế hành vi kế thừa. Phương thức ở interface con cụ thể hơn nên được chọn khi một lớp triển khai interface con.

```java
public interface BaseFormatter {
    default String format(String value) {
        return "[" + value + "]";
    }
}

public interface HtmlFormatter extends BaseFormatter {
    @Override
    default String format(String value) {
        return "<strong>" + value + "</strong>";
    }
}

public class HtmlFormatterImpl implements HtmlFormatter {
}
```

Lời gọi:

```java
HtmlFormatter formatter = new HtmlFormatterImpl();
System.out.println(formatter.format("Java"));
```

Kết quả:

```text
<strong>Java</strong>
```

`HtmlFormatter.format` ghi đè `BaseFormatter.format`. Lớp `HtmlFormatterImpl` kế thừa hành vi mới từ interface con mà không cần tự triển khai phương thức.

Nên dùng `@Override` khi ghi đè default method. Annotation này giúp compiler xác nhận chữ ký thực sự ghi đè một phương thức được kế thừa; nếu viết sai tên hoặc sai tham số, lỗi sẽ được phát hiện khi biên dịch.

## 3. Interface con có thể loại bỏ default implementation

Interface con có thể khai báo lại một default method dưới dạng phương thức abstract. Cách này giữ lại hợp đồng phương thức nhưng yêu cầu lớp triển khai cụ thể tự cung cấp phần thân.

```java
public interface BaseConnection {
    default String state() {
        return "UNKNOWN";
    }
}

public interface ManagedConnection extends BaseConnection {
    @Override
    String state();
}
```

`ManagedConnection` không còn cung cấp phần thân mặc định cho `state()`. Lớp cụ thể triển khai interface này phải định nghĩa phương thức:

```java
public class DatabaseConnection implements ManagedConnection {
    @Override
    public String state() {
        return "CONNECTED";
    }
}
```

Nếu một class cụ thể không triển khai `state()`, compiler báo lỗi vì class chưa thực hiện đầy đủ hợp đồng abstract. Quy tắc này hữu ích khi interface con muốn buộc các implementation cung cấp hành vi phù hợp với ngữ cảnh chuyên biệt hơn.

## 4. Phương thức của class được ưu tiên hơn default method

Khi một lớp kế thừa phương thức instance phù hợp từ superclass và đồng thời triển khai interface có default method cùng chữ ký, phương thức của class hoặc superclass được ưu tiên.

```java
public interface Greeting {
    default String greet() {
        return "Hello from interface";
    }
}

public class BaseService {
    public String greet() {
        return "Hello from superclass";
    }
}

public class GreetingService extends BaseService implements Greeting {
}
```

Khi gọi:

```java
GreetingService service = new GreetingService();
System.out.println(service.greet());
```

Kết quả:

```text
Hello from superclass
```

Quy tắc này thường được mô tả là class wins: phương thức kế thừa từ class có ưu tiên so với default method của interface. Điều này cũng áp dụng khi superclass khai báo phương thức abstract cùng chữ ký: default method của interface không tự lấp phần triển khai abstract mà class hierarchy yêu cầu. Một lớp con cụ thể vẫn phải thực hiện phương thức abstract đó.

## 5. Hai interface độc lập cùng khai báo default method

Nếu một class triển khai hai interface độc lập và cả hai cùng cung cấp default method trùng chữ ký, compiler không thể tự chọn phần thân nào. Class phải override phương thức để giải quyết xung đột.

```java
public interface JsonLabel {
    default String label() {
        return "JSON";
    }
}

public interface XmlLabel {
    default String label() {
        return "XML";
    }
}
```

Lớp triển khai phải đưa ra lựa chọn:

```java
public class DocumentLabel implements JsonLabel, XmlLabel {
    @Override
    public String label() {
        return JsonLabel.super.label();
    }
}
```

`JsonLabel.super.label()` gọi trực tiếp phần thân default method của interface được chỉ định. Lớp cũng có thể gọi `XmlLabel.super.label()` hoặc kết hợp kết quả của cả hai theo nghiệp vụ.

Cú pháp `InterfaceName.super.method()` dùng để gọi default method của một direct superinterface hợp lệ của class hoặc interface hiện tại. Nó giúp thể hiện rõ lựa chọn khi có nhiều phần thân mặc định có thể áp dụng.

## 6. Thứ tự ưu tiên khi xác định phần triển khai

Có thể dùng bảng sau để nhớ các trường hợp phổ biến:

| Tình huống | Kết quả |
|---|---|
| Interface con không ghi đè default method của cha | Kế thừa default method từ interface cha. |
| Interface con ghi đè bằng default method mới | Dùng default method ở interface con cụ thể hơn. |
| Interface con khai báo lại phương thức dưới dạng abstract | Implementation cụ thể phải tự triển khai phương thức. |
| Superclass có phương thức instance cùng chữ ký | Phương thức của class hierarchy được ưu tiên. |
| Hai interface độc lập có default method trùng chữ ký | Class triển khai phải override để giải quyết xung đột. |

Với nhiều interface trong một hệ kế thừa, phương thức được khai báo ở interface con cụ thể hơn sẽ ưu tiên phương thức tương ứng ở interface cha. Trường hợp các interface không có quan hệ kế thừa và đều cung cấp default method cạnh tranh, cần có một implementation rõ ràng ở class.

## 7. Tác động khi interface thay đổi theo thời gian

Default method được đưa vào Java để interface có thể bổ sung hành vi mà không buộc mọi lớp triển khai cũ phải viết lại ngay. Tuy vậy, thay đổi interface vẫn cần được đánh giá về tương thích nguồn, tương thích nhị phân và hành vi runtime.

### Thêm default method mới

Giả sử phiên bản đầu của API có:

```java
public interface Report {
    String title();
}
```

Một ứng dụng đã có lớp triển khai:

```java
public class MonthlyReport implements Report {
    @Override
    public String title() {
        return "Monthly";
    }
}
```

Phiên bản sau bổ sung default method:

```java
public interface Report {
    String title();

    default String format() {
        return "Plain text";
    }
}
```

`MonthlyReport` có thể kế thừa `format()` mà không cần sửa mã nguồn. Đây là lợi ích tương thích quan trọng của default method khi mở rộng interface đã được nhiều class triển khai.

### Thêm default method có thể tạo xung đột

Giả sử class đã triển khai hai interface độc lập. Ban đầu chỉ một interface có default method `label()`. Sau đó phiên bản mới của interface còn lại cũng thêm default method cùng chữ ký. Khi biên dịch lại, class có thể gặp xung đột và phải override để chọn hành vi. Với binary cũ chạy cùng phiên bản interface mới, việc phân giải lời gọi trong trường hợp có nhiều default method cụ thể cạnh tranh có thể thất bại tại runtime bằng `IncompatibleClassChangeError`.

Vì vậy, thêm default method thường giúp mở rộng interface tương thích hơn việc thêm phương thức abstract, nhưng không có nghĩa là mọi thay đổi đều an toàn trong mọi hệ thống kế thừa.

### Thêm phương thức abstract

Nếu phiên bản mới thêm một phương thức abstract vào interface, các class triển khai cần cung cấp phương thức đó để mã nguồn biên dịch lại thành công. Binary cũ chưa có implementation vẫn có thể được nạp, nhưng khi lời gọi đi đến phương thức chưa được triển khai, runtime có thể ném `AbstractMethodError`.

### Thay đổi phần thân default method hiện có

Sửa phần thân default method thường không làm thay đổi chữ ký nhị phân của interface, nhưng có thể thay đổi hành vi của các class đang kế thừa nó. Các implementation không override phương thức sẽ nhận hành vi mới sau khi chạy với phiên bản interface mới. Đây là thay đổi hành vi cần kiểm thử như một thay đổi API.

### Chuyển default method thành abstract

Xóa phần thân `default` và biến phương thức thành abstract làm thay đổi yêu cầu đối với các implementation. Mã nguồn cần được cập nhật; binary cũ không có implementation tương ứng có thể gặp `AbstractMethodError` khi phương thức được gọi. Không nên xem đây là thay đổi tương thích thông thường.

## 8. Tương tác với dynamic proxy

Dynamic proxy xử lý lời gọi theo `InvocationHandler`, nên việc chọn default method cần được xem xét riêng với quy tắc kế thừa của class thông thường.

Khi proxy triển khai nhiều interface có phương thức trùng chữ ký, thứ tự interface truyền vào `Proxy.newProxyInstance` ảnh hưởng đến đối tượng `Method` được chuyển cho handler. Vì vậy `method.isDefault()` chỉ phản ánh `Method` mà handler đang nhận; nó không tự tìm kiếm default method trùng chữ ký trong các interface còn lại.

Nếu cần chọn một default method cụ thể, handler có thể lấy `Method` từ interface mong muốn rồi gọi `InvocationHandler.invokeDefault`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

Method selected = Report.class.getMethod("format");

InvocationHandler handler = (proxy, method, args) -> {
    if (method.getName().equals("format")
            && method.getParameterCount() == 0) {
        return InvocationHandler.invokeDefault(
                proxy,
                selected,
                args == null ? new Object[0] : args);
    }
    throw new UnsupportedOperationException(method.toString());
};
```

`Report` phải thuộc hệ interface mà proxy triển khai, và `selected` phải là default method hợp lệ. API `invokeDefault` có từ Java 16. Nếu proxy dùng nhiều interface, handler nên xác định chính sách lựa chọn rõ ràng thay vì phụ thuộc ngầm vào thứ tự interface.

## 9. Nguyên tắc khi thiết kế interface có default method

- Chỉ thêm default method khi có một hành vi mặc định hợp lý cho phần lớn implementation hiện tại.
- Chọn tên phương thức tránh trùng với các phương thức phổ biến mà implementation có thể đã khai báo.
- Kiểm tra các interface cha và các interface thường được triển khai cùng nhau để phát hiện default method trùng chữ ký.
- Dùng `@Override` khi thay thế default method; dùng `InterfaceName.super.method()` khi cần chọn rõ một phần thân từ direct superinterface.
- Khi phát hành phiên bản API mới, kiểm thử cả class triển khai trực tiếp, class kế thừa superclass và class triển khai nhiều interface.
- Đánh giá riêng tương thích nguồn, tương thích nhị phân và thay đổi hành vi; việc thêm `default` giảm công sức cập nhật implementation nhưng không loại bỏ mọi xung đột.

Hiểu đúng quy tắc kế thừa, override và xung đột giúp default method trở thành công cụ mở rộng interface ổn định. Khi API thay đổi, cần kiểm tra toàn bộ hệ interface và class liên quan để bảo đảm implementation tiếp tục chọn đúng hành vi trên các JDK hiện đại.
