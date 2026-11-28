# Kiểm soát quyền truy cập, IllegalArgumentException và exception từ method đích

`InvocationHandler` là điểm tập trung để kiểm tra quyền và xử lý lời gọi đi qua Java dynamic proxy. Handler có thể kiểm tra người gọi, phương thức và đối số trước khi chạy default method hoặc ủy quyền đến implementation thật. Khi dùng Reflection, cần phân biệt lỗi do đối số không hợp lệ, lỗi truy cập phương thức và ngoại lệ phát sinh bên trong method đích.

Các API `Proxy`, `InvocationHandler`, `Method.invoke` và `InvocationHandler.invokeDefault` vẫn được hỗ trợ trên các JDK hiện đại. `InvocationHandler.invokeDefault` có từ Java 16. Nội dung dưới đây tập trung vào kiểm soát ở tầng ứng dụng và các quy tắc ngoại lệ hiện hành.

## 1. Kiểm soát quyền truy cập tại InvocationHandler

Dynamic proxy chuyển lời gọi phương thức instance trên các interface đã đăng ký đến cùng một `InvocationHandler`. Vì vậy, handler có thể áp dụng chính sách chung trước khi thực hiện phương thức:

- Xác định người dùng hoặc ngữ cảnh đang thực hiện lời gọi.
- Kiểm tra vai trò, quyền hoặc phạm vi dữ liệu được phép truy cập.
- Kiểm tra tính hợp lệ của đối số.
- Gọi default method bằng `InvocationHandler.invokeDefault` hoặc ủy quyền đến target thật.
- Ghi nhận kết quả và xử lý ngoại lệ theo chính sách của ứng dụng.

Ví dụ, một `DocumentService` có thể cho phép người dùng đọc tài liệu nhưng chỉ quản trị viên được xóa tài liệu. Handler kiểm tra quyền trước khi gọi phương thức tương ứng.

```java
public interface DocumentService {
    String read(String id) throws IOException;

    void delete(String id) throws IOException;

    default String preview(String id) throws IOException {
        String content = read(id);
        return content.substring(0, Math.min(20, content.length()));
    }
}
```

`preview` là default method và gọi `read` thông qua `this`. Khi `preview` chạy trên proxy bằng `invokeDefault`, lời gọi `read` tiếp tục đi qua proxy và handler có cơ hội kiểm tra quyền cho `read` lần nữa.

## 2. Ví dụ proxy có kiểm tra quyền

Ví dụ sau sử dụng một principal chứa tên người dùng và tập vai trò. Người dùng có vai trò `USER` được đọc và xem trước tài liệu; thao tác xóa yêu cầu vai trò `ADMIN`.

```java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Set;

public class SecuredDocumentProxyDemo {
    public record Principal(String name, Set<String> roles) {
    }

    public interface DocumentService {
        String read(String id) throws IOException;

        void delete(String id) throws IOException;

        default String preview(String id) throws IOException {
            String content = read(id);
            return content.substring(0, Math.min(20, content.length()));
        }
    }

    public static final class DocumentServiceImpl implements DocumentService {
        @Override
        public String read(String id) throws IOException {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Document id is required");
            }
            if (id.equals("IO-FAIL")) {
                throw new IOException("Storage is unavailable");
            }
            return "Document content for " + id;
        }

        @Override
        public void delete(String id) throws IOException {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Document id is required");
            }
            System.out.println("Deleted " + id);
        }
    }

    private static void authorize(Principal principal, Method method) {
        String name = method.getName();

        if (name.equals("read") || name.equals("preview")) {
            if (!principal.roles().contains("USER")
                    && !principal.roles().contains("ADMIN")) {
                throw new SecurityException("Read permission is required");
            }
        } else if (name.equals("delete")) {
            if (!principal.roles().contains("ADMIN")) {
                throw new SecurityException("Admin role is required to delete");
            }
        }
    }

    private static DocumentService secure(
            DocumentService target, Principal principal) {
        InvocationHandler handler = (proxy, method, args) -> {
            // Đặt chính sách rõ ràng cho các phương thức của Object.
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "SecuredDocumentServiceProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            authorize(principal, method);

            if (method.isDefault()) {
                Object[] actualArgs = args == null ? new Object[0] : args;
                return InvocationHandler.invokeDefault(
                        proxy, method, actualArgs);
            }

            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException exception) {
                // Chuyển tiếp ngoại lệ gốc do implementation ném ra.
                throw exception.getCause();
            } catch (IllegalAccessException exception) {
                // Đây là lỗi truy cập method, không phải lỗi từ thân method.
                throw new IllegalStateException(
                        "Cannot access target method: " + method, exception);
            }
        };

        return (DocumentService) Proxy.newProxyInstance(
                DocumentService.class.getClassLoader(),
                new Class<?>[]{DocumentService.class},
                handler);
    }

    public static void main(String[] args) {
        Principal user = new Principal("Lan", Set.of("USER"));
        DocumentService service = secure(new DocumentServiceImpl(), user);

        try {
            System.out.println(service.preview("DOC-1"));
        } catch (IOException exception) {
            System.out.println("Read failed: " + exception.getMessage());
        }

        try {
            service.delete("DOC-1");
        } catch (SecurityException exception) {
            System.out.println("Access denied: " + exception.getMessage());
        } catch (IOException exception) {
            System.out.println("Delete failed: " + exception.getMessage());
        }

        try {
            service.read("IO-FAIL");
        } catch (IOException exception) {
            System.out.println("Target error: " + exception.getMessage());
        }
    }
}
```

Kết quả:

```text
Document content for
Access denied: Admin role is required to delete
Target error: Storage is unavailable
```

Khi gọi `preview`, handler kiểm tra quyền cho `preview`, rồi gọi phần thân default method trên proxy. Lời gọi `read` bên trong `preview` quay lại handler và được kiểm tra quyền thêm lần nữa trước khi ủy quyền đến target. Khi gọi `delete`, quyền bị từ chối ngay trong handler nên implementation không được chạy. Với `read("IO-FAIL")`, implementation ném `IOException`; handler mở `InvocationTargetException` và chuyển tiếp nguyên nhân `IOException` về client.

## 3. IllegalArgumentException có thể đến từ đâu?

`IllegalArgumentException` là unchecked exception. Trong luồng proxy và Reflection, nó có thể xuất hiện từ nhiều nguồn khác nhau:

| Nguồn | Ví dụ | Ý nghĩa |
|---|---|---|
| Kiểm tra đầu vào của ứng dụng | ID tài liệu rỗng hoặc định dạng sai | Dữ liệu đầu vào vi phạm hợp đồng nghiệp vụ. |
| `Method.invoke` | Target không tương thích với method hoặc số lượng/kiểu đối số không đúng | Reflection không thể thực hiện lời gọi theo chữ ký đã cung cấp. |
| `InvocationHandler.invokeDefault` | Proxy không hợp lệ hoặc `Method` không phải default method phù hợp thuộc interface của proxy | Cặp proxy và method không thỏa điều kiện của API. |
| Logic của implementation | Target chủ động ném `IllegalArgumentException` | Phương thức đích đã được gọi và từ chối đối số theo quy tắc nghiệp vụ. |

Phân biệt nguồn rất quan trọng khi ghi log và trả lỗi cho client. Ví dụ, lỗi đối số do `Method.invoke` phát hiện xảy ra trước khi thân phương thức target chạy; nó được ném trực tiếp dưới dạng `IllegalArgumentException`. Nếu chính thân target ném `IllegalArgumentException`, `Method.invoke` bọc nó trong `InvocationTargetException`, và handler cần lấy `getCause()` để nhận lỗi gốc.

## 4. Điều kiện gọi invokeDefault và IllegalArgumentException

`InvocationHandler.invokeDefault(proxy, method, args)` yêu cầu:

- `proxy` là đối tượng dynamic proxy đang được xử lý.
- `method` đại diện cho default method được khai báo trong một interface mà proxy triển khai trực tiếp hoặc thông qua kế thừa.
- Các đối số khớp với chữ ký của default method được chọn.

Nếu truyền đối tượng không phải proxy, chọn một phương thức không phải default method hoặc chọn method không thuộc hệ interface phù hợp của proxy, API có thể ném `IllegalArgumentException`. Vì vậy, handler nên kiểm tra `method.isDefault()` khi dùng chính `Method` nhận từ `invoke`:

```java
if (method.isDefault()) {
    Object[] actualArgs = args == null ? new Object[0] : args;
    return InvocationHandler.invokeDefault(proxy, method, actualArgs);
}
```

`isDefault()` chỉ kiểm tra `Method` hiện tại. Nếu proxy triển khai nhiều interface có phương thức trùng chữ ký, handler có thể cần lấy `Method` từ interface cụ thể muốn chọn và xác nhận interface đó thuộc proxy.

## 5. IllegalArgumentException từ Method.invoke

`Method.invoke(target, args)` yêu cầu target tương thích với class/interface khai báo phương thức và các đối số phù hợp với danh sách tham số. Một số trường hợp dẫn đến `IllegalArgumentException`:

- Truyền sai số lượng đối số.
- Truyền giá trị không thể chuyển đổi hoặc unbox sang kiểu tham số cần thiết.
- Truyền target không phải instance tương thích với kiểu khai báo phương thức.

Nếu truyền target `null` khi gọi phương thức instance, `Method.invoke` ném `NullPointerException` vì không có đối tượng nhận lời gọi. Đây là trường hợp riêng, không phải `IllegalArgumentException`.

Ví dụ:

```java
Method method = Calculator.class.getMethod("add", int.class, int.class);

// Giả sử target là một instance Calculator hợp lệ.
Object result = method.invoke(target, 10); // Sai: thiếu một đối số.
```

Lỗi đối số này được Reflection phát hiện trước khi gọi thân `add`. Nó không được bọc trong `InvocationTargetException`.

Khi dùng `InvocationHandler`, có thể kiểm tra trước dữ liệu đầu vào bằng `method.getParameterTypes()` và số phần tử của `args`. Tuy nhiên, nếu chỉ chuyển tiếp nguyên trạng các đối số nhận được từ proxy, JDK đã tạo mảng theo lời gọi ban đầu; việc kiểm tra bổ sung chủ yếu cần thiết khi handler biến đổi hoặc tự tạo đối số.

## 6. Phân biệt InvocationTargetException với IllegalAccessException

`Method.invoke` có thể ném các ngoại lệ khác nhau tùy giai đoạn thất bại:

| Ngoại lệ | Khi nào xảy ra | Cách xử lý |
|---|---|---|
| `InvocationTargetException` | Thân phương thức target đã chạy và ném ngoại lệ | Lấy `getCause()` để xử lý hoặc chuyển tiếp lỗi gốc. |
| `IllegalArgumentException` | Target hoặc đối số không hợp lệ; thân phương thức chưa được gọi | Sửa target/chữ ký/đối số hoặc trả lỗi đầu vào phù hợp. |
| `NullPointerException` | Target là `null` khi gọi phương thức instance | Cung cấp một đối tượng target hợp lệ. |
| `IllegalAccessException` | Reflection không có quyền truy cập phương thức trong ngữ cảnh hiện tại | Kiểm tra khả năng truy cập, visibility và cấu hình module. |

Với ứng dụng dùng Java Platform Module System, public API cần được đặt trong package được module export phù hợp. Truy cập sâu vào thành viên không public có thể cần package được mở (`opens`) cho module gọi. Không nên mặc định bật truy cập sâu cho toàn bộ ứng dụng; chỉ cấu hình quyền truy cập ở phạm vi thực sự cần thiết.

Ví dụ mở ngoại lệ gốc:

```java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException exception) {
    Throwable cause = exception.getCause();
    throw cause == null ? exception : cause;
} catch (IllegalAccessException exception) {
    throw new IllegalStateException(
            "Method is not accessible: " + method, exception);
}
```

Đoạn code giữ lại `InvocationTargetException` nếu không có cause, dù tình huống này hiếm. Lỗi truy cập được chuyển thành `IllegalStateException` vì đây thường là vấn đề cấu hình hoặc triển khai của proxy, không phải lỗi nghiệp vụ mà client có thể khắc phục bằng cách đổi đối số.

## 7. Ngoại lệ checked từ method đích và quy tắc của proxy

`InvocationHandler.invoke` khai báo `throws Throwable`, nên handler có thể chuyển tiếp ngoại lệ gốc từ target. Tuy nhiên, khi lời gọi đi qua dynamic proxy, client chỉ nhận trực tiếp checked exception được khai báo phù hợp trong `throws` của phương thức interface.

Ví dụ interface khai báo:

```java
public interface FileService {
    String load(String path) throws IOException;
}
```

Nếu `FileServiceImpl.load` ném `IOException` và handler chuyển tiếp `exception.getCause()`, client nhận `IOException` như hợp đồng đã khai báo. Nếu target ném một checked exception không được khai báo trong phương thức interface, proxy bọc nó trong `UndeclaredThrowableException`.

Các unchecked exception như `IllegalArgumentException` và `SecurityException` có thể truyền về client trực tiếp. Vì thế, handler nên phân biệt lỗi đầu vào, lỗi quyền và lỗi hạ tầng để lớp gọi có thể xử lý đúng cách.

## 8. Đặt chính sách bảo mật đúng ranh giới

Kiểm tra quyền trong `InvocationHandler` chỉ bảo vệ những lời gọi đi qua proxy. Nếu ứng dụng giữ hoặc chia sẻ trực tiếp tham chiếu đến `target`, mã khác có thể gọi target mà không đi qua handler và bỏ qua chính sách kiểm tra quyền.

Một số nguyên tắc khi áp dụng:

- Giữ target bên trong factory hoặc handler; chỉ cung cấp proxy cho phần mã cần chịu kiểm soát.
- Xác định principal từ ngữ cảnh xác thực đáng tin cậy của ứng dụng, không nhận vai trò tùy ý từ tham số do client gửi.
- Kiểm tra quyền trước khi gọi default method hoặc target.
- Xử lý riêng các phương thức `equals`, `hashCode`, `toString`; không để chúng vô tình bị chặn hoặc làm lộ thông tin nhạy cảm.
- Nhớ rằng lời gọi nội bộ trong default method có thể quay lại handler, do đó từng phương thức con có thể được kiểm tra quyền độc lập.
- Không dựa vào dynamic proxy như ranh giới bảo mật duy nhất nếu target còn có thể được truy cập bằng đường khác.

## 9. Ghi nhớ

- `InvocationHandler` có thể kiểm tra quyền và đầu vào trước khi xử lý lời gọi.
- `SecurityException` phù hợp khi người gọi không có quyền; `IllegalArgumentException` phù hợp khi đối số vi phạm hợp đồng.
- `IllegalArgumentException` do Reflection phát hiện thường xảy ra trước khi thân target chạy; lỗi cùng loại do target ném ra nằm trong `InvocationTargetException`.
- `InvocationTargetException` chứa ngoại lệ gốc của method đích; dùng `getCause()` khi muốn chuyển tiếp lỗi gốc.
- `IllegalAccessException` là lỗi truy cập Reflection, khác với ngoại lệ do method đích ném.
- Checked exception không khai báo trong interface có thể bị dynamic proxy bọc thành `UndeclaredThrowableException`.
- Proxy chỉ kiểm soát các lời gọi đi qua nó; cần giữ kín target để chính sách có hiệu lực.

Khi tách rõ kiểm tra quyền, xác thực đối số, lỗi truy cập Reflection và ngoại lệ từ method đích, `InvocationHandler` trở thành nơi điều phối lời gọi dễ kiểm soát. Những nguyên tắc này tiếp tục áp dụng với dynamic proxy trên các JDK hiện đại.
