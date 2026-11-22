# Tránh gọi lại chính proxy gây đệ quy vô hạn trong Java Dynamic Proxy

## 1. Mục tiêu và bối cảnh

Khi sử dụng **JDK Dynamic Proxy**, mỗi lời gọi phương thức trên proxy được chuyển đến `InvocationHandler.invoke(...)`. Lỗi thường gặp là trong handler, lập trình viên lại gọi phương thức **trên chính đối tượng proxy** để “thực thi phương thức gốc”. Lệnh này kích hoạt handler thêm lần nữa; vòng lặp có thể tiếp diễn đến khi cạn ngăn xếp và phát sinh `StackOverflowError`.

Sau bài này, bạn có thể:

- Phân biệt `proxy` (đối tượng trung gian) với `target` (đối tượng triển khai thật).
- Nhận diện đệ quy trực tiếp qua `method.invoke(proxy, args)` và đệ quy gián tiếp qua logging, `toString()`, `equals()` hay `hashCode()`.
- Chuyển tiếp lời gọi đúng sang `target`, xử lý ngoại lệ phản chiếu và các phương thức của `Object`.
- Hiểu khi nào một lời gọi lại proxy là **có chủ đích** và khi nào nó tạo chu trình không mong muốn.

Bài này tập trung vào **JDK Dynamic Proxy** (`java.lang.reflect.Proxy`), vốn tạo proxy cho **interface**. Cơ chế proxy dựa trên subclass của các thư viện khác có thể khác về cách chuyển tiếp lời gọi.

## 2. Cơ chế gây đệ quy

Một handler được khai báo theo giao diện `InvocationHandler`:

```java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
```

Trong đó:

- `proxy` là **chính đối tượng proxy** mà bên gọi vừa sử dụng, không phải đối tượng nghiệp vụ thật.
- `method` mô tả phương thức mà bên gọi đang yêu cầu; có thể là phương thức của interface hoặc `equals`, `hashCode`, `toString` từ `Object`.
- `args` chứa tham số của lời gọi; có thể là `null` nếu phương thức không có tham số.

**Ví dụ sai**, chỉ là mảnh code đặt trong ngữ cảnh đã import `InvocationHandler`:

```java
InvocationHandler badHandler = (proxy, method, args) -> {
    System.out.println("Gọi " + method.getName());
    return method.invoke(proxy, args); // SAI: gọi lại chính proxy
};
```

Nếu client gọi `service.greet("An")`, luồng thực hiện sẽ thành:

```text
client gọi proxy.greet("An")
    -> InvocationHandler.invoke(proxy, greet, ["An"])
       -> method.invoke(proxy, ["An"])
          -> InvocationHandler.invoke(proxy, greet, ["An"])
             -> method.invoke(proxy, ["An"])
                -> ... lặp lại ...
```

`Method.invoke(...)` không “bỏ qua” handler khi receiver là proxy. Đây vẫn là lời gọi vào một phương thức của proxy, nên cơ chế chuyển tiếp lại hoạt động. Kết cục thường là `StackOverflowError`; dấu vết có thể xen kẽ giữa phương thức proxy, handler và Java Reflection. **Không nên chạy đoạn sai như một bài thử tải**, vì việc tràn ngăn xếp không mang thêm giá trị học tập.

Quy tắc chính: **`proxy` là điểm tiếp nhận lời gọi; `target` mới là nơi thực hiện công việc nếu đang xây dựng proxy ủy quyền.**

## 3. Cách sửa: chuyển tiếp vào đối tượng thật

Với trường hợp proxy dùng để đo thời gian, ghi log, kiểm tra quyền hoặc bổ sung hành vi quanh một đối tượng có sẵn, cấu trúc đúng là:

```text
caller -> proxy -> InvocationHandler
                       |
                       +-> ghi log / kiểm tra
                       +-> method.invoke(target, args)
                       +-> trả kết quả cho caller
```

Cần bảo đảm:

1. `target` là một đối tượng **khác proxy**, triển khai interface có phương thức được gọi.
2. Handler dùng `method.invoke(target, args)` thay cho `method.invoke(proxy, args)`.
3. Nếu thao tác trên `target` lại gọi ngược vào proxy, phải xem xét luồng gọi thật để loại bỏ **chu trình phụ thuộc**. Chỉ thay receiver bằng `target` không tự động giải quyết mọi vòng lặp gián tiếp.

### Chương trình Java 17+ chạy độc lập

Tạo tệp `SafeProxyDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class SafeProxyDemo {
    public interface GreetingService {
        String greet(String name);
    }

    static final class RealGreetingService implements GreetingService {
        @Override
        public String greet(String name) {
            return "Xin chào, " + name + "!";
        }
    }

    public static void main(String[] args) {
        GreetingService target = new RealGreetingService();

        InvocationHandler handler = (proxy, method, arguments) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == arguments[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "GreetingProxy@" +
                            Integer.toHexString(System.identityHashCode(proxy));
                    default -> throw new UnsupportedOperationException(method.getName());
                };
            }

            System.out.println("Gọi: " + method.getName());
            try {
                return method.invoke(target, arguments);
            } catch (InvocationTargetException e) {
                throw e.getCause();
            }
        };

        GreetingService service = (GreetingService) Proxy.newProxyInstance(
                GreetingService.class.getClassLoader(),
                new Class<?>[] { GreetingService.class },
                handler);

        System.out.println(service.greet("An"));
        System.out.println(service.toString().startsWith("GreetingProxy@"));
        System.out.println(service.equals(service));
        System.out.println(service.hashCode() == System.identityHashCode(service));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac SafeProxyDemo.java
java SafeProxyDemo
```

Kết quả (chương trình này đã được chạy để xác minh):

```text
Gọi: greet
Xin chào, An!
true
true
true
```

**Giải thích:**

- `target` là `RealGreetingService` và thực sự xử lý `greet`.
- Handler ghi tên phương thức bằng `method.getName()`; thao tác trên metadata này không gọi lại proxy.
- `method.invoke(target, arguments)` thực thi phương thức trên `target`. Kết quả trả về qua handler rồi về client, không tạo vòng lặp.
- Ba phép thử cuối xác minh hành vi của `toString`, `equals` và `hashCode`. `toString()` được gọi thật trên proxy, nhưng nhánh dành cho `Object` trả chuỗi tự tạo **mà không gọi lại** `proxy.toString()`.
- `System.identityHashCode(proxy)` lấy mã băm định danh trực tiếp, không gọi `proxy.hashCode()`.
- `InvocationTargetException` gói ngoại lệ do phương thức đích ném; `throw e.getCause()` truyền nguyên nhân gốc qua `InvocationHandler`. Việc proxy chuyển tiếp checked exception vẫn tuân theo khai báo `throws` của interface.

Ví dụ dùng quy ước equality theo **identity của proxy** để bảo đảm `service.equals(service)` là `true`. Đây là một lựa chọn có chủ đích: nếu ứng dụng yêu cầu equality dựa trên nghiệp vụ, hãy thiết kế cả `equals`/`hashCode` một cách nhất quán thay vì ủy quyền tùy tiện.

## 4. Bẫy gián tiếp: logging cũng có thể gọi lại proxy

Ngay cả khi đã dùng `method.invoke(target, args)`, handler vẫn có thể tự gây đệ quy:

```java
// Mảnh code minh họa lỗi bên trong một handler.
System.out.println("Proxy: " + proxy); // SAI trong handler chung
return method.invoke(target, args);
```

Toán tử nối chuỗi biến `proxy` thành chuỗi, dẫn đến `proxy.toString()`. Với JDK dynamic proxy, `toString()` cũng đi qua `InvocationHandler`. Lời gọi mới lại chạy chính dòng logging đó, rồi tiếp tục gọi `toString()`.

Các tình huống cần phân biệt:

| Biểu thức trong handler | Có thể gọi lại handler? | Cách thay thế hoặc lưu ý |
| --- | --- | --- |
| `method.invoke(proxy, args)` | **Có**, với phương thức được proxy điều phối | Chuyển tiếp vào `target` thật, nếu đang làm delegation |
| `proxy.toString()`, `"proxy=" + proxy`, `System.out.println(proxy)` | **Có**, qua `toString` | Ghi `method.getName()` hoặc `System.identityHashCode(proxy)` |
| `proxy.hashCode()` | **Có**, qua `hashCode` | Dùng `System.identityHashCode(proxy)` khi cần identity |
| `proxy.equals(other)` | **Có**, qua `equals` | Dùng `proxy == other` nếu mục tiêu là so sánh tham chiếu |
| `proxy.getClass()` | **Không** đối với lời gọi `Object.getClass()` thông thường | `getClass` là `final`, không được override để chuyển đến handler |
| `method.getName()`, `method.getDeclaringClass()` | **Không** | Chỉ đọc metadata của `Method` |

Không nên viết `logger.info("proxy={}", proxy)` và mặc nhiên nghĩ rằng cách log có placeholder sẽ tránh gọi `toString()`. Nhiều logger định dạng đối tượng tại thời điểm phát log; việc gọi `toString()` có thể xảy ra sau đó. Khi debug handler, ưu tiên một nhãn cố định, tên phương thức và identity hash.

## 5. Vì sao phải chú ý các phương thức của Object?

Trên JDK dynamic proxy, các lời gọi `equals(Object)`, `hashCode()` và `toString()` được gửi đến `InvocationHandler`. Do đó, một handler chỉ biết gọi `method.invoke(target, args)` có thể gây ra **lỗi ngữ nghĩa** dù không tràn ngăn xếp.

Ví dụ, nếu `target` dùng `Object.equals` mặc định, chuyển tiếp `proxy.equals(proxy)` thành `target.equals(proxy)` có thể trả về `false`. Khi đó tính chất phản xạ của `equals` (`x.equals(x) == true`) bị vi phạm. Tương tự, `proxy.hashCode()` có thể trả mã băm của target trong khi `equals` được định nghĩa bằng identity proxy, khiến hợp đồng `equals/hashCode` thiếu nhất quán nếu không cân nhắc.

Một cách xử lý an toàn cho proxy dùng identity là:

```java
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "equals" -> proxy == args[0];
        case "hashCode" -> System.identityHashCode(proxy);
        case "toString" -> "ServiceProxy@" +
                Integer.toHexString(System.identityHashCode(proxy));
        default -> throw new UnsupportedOperationException(method.getName());
    };
}
```

Đây là mảnh code bên trong `invoke`; `args[0]` được sử dụng trong nhánh `equals(Object)` có một tham số. Nếu interface có yêu cầu đặc biệt về identity hoặc equality, hãy thay đổi chính sách này có chủ đích và kiểm thử.

## 6. Phân biệt recursion ngoài ý muốn với lời gọi lồng nhau hợp lệ

Không phải cứ `InvocationHandler.invoke` chạy lại là lỗi. Chẳng hạn, khi triển khai một default method của interface, phương thức này có thể gọi phương thức khác trên `this`, và lời gọi thứ hai hợp lệ nếu cuối cùng được xử lý xong.

Với Java 17, API `InvocationHandler.invokeDefault(proxy, method, args)` cho phép gọi phần triển khai mặc định của một phương thức interface **mà không gọi lại handler để thực thi chính phương thức default đó**:

```java
// Mảnh code trong InvocationHandler.invoke(...), dùng khi phù hợp:
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(proxy, method, args);
}
```

Cần lưu ý rằng **thân default method vẫn có thể gọi các phương thức khác trên proxy**. Nếu các lời gọi đó quay về chính default method mà không có điểm dừng, chu trình vẫn tồn tại. `invokeDefault` không phải cơ chế chống đệ quy tổng quát.

Tương tự, proxy có thể bọc thêm một proxy khác để xây dựng chuỗi interceptor hợp lệ. Điều cần loại bỏ là **chu trình gọi** như `proxyA -> handlerA -> proxyB -> handlerB -> proxyA`, không phải toàn bộ lời gọi lồng nhau.

## 7. Chẩn đoán và khắc phục khi gặp StackOverflowError

Khi thấy `StackOverflowError` trong quá trình gọi dynamic proxy:

1. **Đọc chuỗi frame lặp lại** trong stack trace. Tìm các frame của `InvocationHandler.invoke`, `Method.invoke`, lớp proxy và các hàm logging. Chuỗi này giúp xác định lời gọi nào quay lại điểm xuất phát.
2. **Tìm mọi vị trí dùng `proxy` bên trong handler**, đặc biệt là receiver của lời gọi phương thức, phép chuyển thành chuỗi và callback do target thực hiện. Đừng chỉ tìm đúng dòng `method.invoke(proxy, args)`.
3. **Xác định đối tượng nhận lời gọi thật**: nếu handler được thiết kế để ủy quyền, `target` phải triển khai interface cần gọi và không được trỏ về proxy vừa tạo. Nếu dùng nhiều tầng proxy, vẽ thứ tự các tầng để phát hiện chu trình.
4. **Sửa đường đi của lời gọi**: gọi target thật, cung cấp cách xử lý riêng cho `Object`, hoặc dùng API dành riêng cho default method khi thích hợp.
5. **Kiểm thử hành vi**: gọi một phương thức nghiệp vụ, `toString`, `equals`, `hashCode`, trường hợp không có tham số, đường đi ném ngoại lệ và một target được bọc bởi nhiều interceptor nếu ứng dụng có dùng.

Một lời chặn re-entry như `ThreadLocal<Boolean>` có thể hữu ích trong trường hợp ứng dụng **cố ý cấm** một luồng đi vào handler lần hai; phải xóa trạng thái trong `finally`. Tuy nhiên, đặt chặn chung cho mọi lời gọi lồng nhau có thể từ chối cả tương tác hợp lệ giữa các phương thức. Cách giải quyết chính vẫn là thiết kế lại đường chuyển tiếp để không tạo chu trình.

Đừng cố “chữa” bằng cách tăng kích thước stack (`-Xss`) hoặc bắt và bỏ qua `StackOverflowError`. Những cách đó không sửa luồng gọi sai, đồng thời có thể khiến ứng dụng hỏng theo cách khó theo dõi hơn.

## 8. Lỗi phổ biến và bài tập tự kiểm tra

**Lỗi phổ biến:**

- Dùng nhầm `proxy` thay vì `target` làm receiver của `Method.invoke`.
- Ghi log nguyên proxy bên trong handler và vô tình kích hoạt `toString`.
- Bỏ qua `equals/hashCode/toString` hoặc chuyển tiếp chúng sang target mà không kiểm tra hợp đồng đối tượng.
- Giữ tham chiếu đến proxy làm target khi cấu hình nhiều interceptor.
- Bọc thêm `InvocationTargetException` mà không kiểm tra nguyên nhân gốc; cách này làm khó chẩn đoán ngoại lệ thật của phương thức nghiệp vụ.
- Coi mọi lời gọi lồng nhau là lỗi và dùng chặn re-entry quá rộng.

**Tự kiểm tra:**

1. Vì sao `method.invoke(proxy, args)` có thể gọi `InvocationHandler.invoke` lần nữa? Vì receiver vẫn là proxy, nên lời gọi được điều phối qua handler.
2. Nếu handler in `"Đang xử lý: " + proxy`, điều gì có thể xảy ra? Phép nối chuỗi gọi `toString` của proxy, thường kích hoạt chính handler đó.
3. Làm sao lấy một mã băm định danh để log mà không đi qua `hashCode` của proxy? Dùng `System.identityHashCode(proxy)`.
4. Khi nào `method.invoke(target, args)` vẫn không an toàn? Khi `target` lại là proxy đó, có chu trình qua những proxy khác hoặc target callback quay ngược về proxy vô hạn.
5. `InvocationHandler.invokeDefault` có bảo đảm không còn vòng lặp không? Không; nó chỉ gọi trực tiếp phần thân default method, còn thân này có thể phát sinh lời gọi khác và tạo chu trình.

**Ghi nhớ:** Trong `InvocationHandler`, biến `proxy` đại diện cho đầu vào của lời gọi đã bị chặn. Muốn ủy quyền, hãy gọi **đối tượng đích thật** và kiểm soát các đường gọi gián tiếp, nhất là logging và ba phương thức `equals/hashCode/toString`.