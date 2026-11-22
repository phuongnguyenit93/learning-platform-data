# Biểu diễn chuỗi và thông tin chẩn đoán của đối tượng trong Java

> **Chủ đề:** OOP → Cơ chế ngôn ngữ.  
> **Mục tiêu:** Hiểu vai trò của `Object.toString()`, phân biệt thông tin biểu diễn cho lập trình viên với dữ liệu dùng cho người dùng hoặc API, biết thiết kế một chuỗi chẩn đoán ngắn gọn và an toàn, sử dụng logging/exception đúng mục đích và kiểm thử nguy cơ rò rỉ dữ liệu.

## 1. Vì sao một đối tượng cần được biểu diễn thành chuỗi?

Khi một ứng dụng đang chạy, ta thường muốn biết **đối tượng nào đang được xử lý và trạng thái đáng chú ý của nó**. Ví dụ, khi một đơn hàng không chuyển được từ `CREATED` sang `PAID`, một dòng log như:

~~~text
Order{id='ORD-42', status=CREATED, itemCount=2, traceId='REQ-72'}
~~~

hữu ích hơn một chuỗi tương tự:

~~~text
com.example.Order@6d06d69c
~~~

Chuỗi đầu giúp người phát triển xác định mã đơn, trạng thái, số mặt hàng và mã truy vết. Chuỗi thứ hai chủ yếu cho biết lớp của đối tượng và một giá trị hash, thường chưa đủ để chẩn đoán.

Trong Java, **`toString()`** là phương thức căn bản để cung cấp biểu diễn văn bản của một đối tượng. Nó được khai báo trong `java.lang.Object`, nên mọi đối tượng Java đều kế thừa được phương thức này:

~~~java
public String toString()
~~~

Một class có thể **override** `toString()` để trình bày thông tin có ý nghĩa hơn. Mục đích điển hình là **quan sát đối tượng khi debug, ghi log hoặc xem trong trình gỡ lỗi (debugger)**.

**Điểm cần phân biệt ngay từ đầu:** Chuỗi từ `toString()` không nhất thiết là dữ liệu dành cho người dùng cuối, không có cam kết là định dạng JSON/XML, và thường **không nên** là định dạng trao đổi giữa các hệ thống. Nếu cần dữ liệu có schema ổn định, hãy dùng DTO và serializer phù hợp.

## 2. Mặc định `Object.toString()` tạo ra gì?

Triển khai mặc định của `Object.toString()` về cơ bản tương đương:

~~~java
public String toString() {
    return getClass().getName() + "@"
            + Integer.toHexString(hashCode());
}
~~~

Điều này tạo ra chuỗi gồm **tên lớp đầy đủ**, dấu `@` và kết quả `hashCode()` được biểu diễn theo hệ thập lục phân.

Ví dụ:

~~~java
class Ticket {
    private final String code = "T-17";
}

Ticket ticket = new Ticket();
System.out.println(ticket);
~~~

Có thể in ra chuỗi có dạng:

~~~text
Ticket@1b6d3586
~~~

Giá trị phía sau `@` **không cố định**, có thể khác giữa các lần chạy. Đừng dùng nó để khẳng định vị trí bộ nhớ, định danh database hoặc mã nghiệp vụ của đối tượng.

### Ba điều dễ hiểu nhầm về chuỗi mặc định

1. `hashCode()` **không phải địa chỉ bộ nhớ**. Không có bảo đảm API Java rằng chuỗi `@...` chứa địa chỉ vật lý hoặc vị trí heap.
2. `Object.toString()` gọi **`hashCode()`**, nên nếu class ghi đè `hashCode()`, chuỗi mặc định của nó có thể chịu ảnh hưởng bởi cách hash được định nghĩa.
3. Hai đối tượng khác nhau **có thể trùng hash code**. `hashCode()` không phải một ID duy nhất hoặc khóa truy vết nghiệp vụ.

Nếu thật sự cần một giá trị hash theo identity mà không phụ thuộc override `hashCode()`, Java có `System.identityHashCode(object)`; song giá trị ấy vẫn **không bảo đảm duy nhất tuyệt đối** và không thay thế ID nghiệp vụ.

### `toString()` liên quan thế nào đến `println` và nối chuỗi?

Java tự gọi cơ chế chuyển đối tượng sang chuỗi trong nhiều ngữ cảnh:

~~~java
Ticket ticket = new Ticket();

System.out.println(ticket);                // println(Object)
System.out.println("Ticket: " + ticket);   // phép nối chuỗi
String text = String.valueOf(ticket);       // String.valueOf(Object)
String formatted = String.format("%s", ticket);
~~~

Các thao tác này thông thường sử dụng kết quả `toString()` khi đối tượng khác `null`. Bởi vậy, chỉ cần override đúng một phương thức, nhiều vị trí debug/logging sẽ dễ đọc hơn.

Trường hợp null cần nhớ:

~~~java
Object missing = null;

System.out.println(String.valueOf(missing)); // "null"
System.out.println(java.util.Objects.toString(
        missing, "<chưa có>"));               // "<chưa có>"
~~~

Đừng tự gọi `missing.toString()`: lời gọi đó ném `NullPointerException`. `String.valueOf(Object)` và `Objects.toString(Object, String)` có chính sách xử lý null riêng.

## 3. Ví dụ thực tế Java 17: chẩn đoán một đơn hàng

Giả sử lớp `Order` giữ cả thông tin nghiệp vụ lẫn dữ liệu nhạy cảm:

- **Hữu ích khi chẩn đoán:** mã đơn, trạng thái, số mặt hàng, mã truy vết.
- **Không nên in ra:** email khách hàng, access token dùng gọi dịch vụ ngoài.
- **Không nên đưa trực tiếp vào `toString()`:** toàn bộ lịch sử xử lý dài, danh sách đối tượng lớn, thông tin có thể phải truy vấn từ database.

Ta viết `toString()` **có chủ đích chọn trường** (*allowlist*), không lấy tất cả field.

Tạo file **`ObjectDiagnosticsDemo.java`** và chạy bằng JDK 17 trở lên:

~~~java
import java.util.List;
import java.util.Objects;

// Enum mô tả các trạng thái hợp lệ.
enum OrderStatus {
    CREATED, PAID, CANCELLED
}

// Record chỉ chứa dữ liệu có thể hiển thị trong ví dụ này.
record OrderLine(String sku, int quantity) {
    OrderLine {
        Objects.requireNonNull(sku, "sku");

        if (!sku.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}

final class Order {
    private final String id;
    private final OrderStatus status;
    private final List<OrderLine> lines;
    private final String traceId;

    // Hai trường này được giữ cho nghiệp vụ, KHÔNG ghi ra toString.
    private final String customerEmail;
    private final String accessToken;

    Order(
            String id,
            OrderStatus status,
            List<OrderLine> lines,
            String traceId,
            String customerEmail,
            String accessToken) {

        this.id = requireSafeId(id, "id");
        this.status = Objects.requireNonNull(status, "status");
        this.lines = List.copyOf(
                Objects.requireNonNull(lines, "lines"));
        this.traceId = requireSafeId(traceId, "traceId");

        this.customerEmail = Objects.requireNonNull(
                customerEmail, "customerEmail");
        this.accessToken = Objects.requireNonNull(
                accessToken, "accessToken");
    }

    private static String requireSafeId(String value, String name) {
        Objects.requireNonNull(value, name);
        if (!value.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid " + name);
        }
        return value;
    }

    String id() {
        return id;
    }

    int itemCount() {
        return lines.size();
    }

    @Override
    public String toString() {
        return "Order{"
                + "id='" + id + '\''
                + ", status=" + status
                + ", itemCount=" + itemCount()
                + ", traceId='" + traceId + '\''
                + '}';
    }

    // API riêng dành cho hiển thị nghiệp vụ; không dựa vào toString().
    String customerMessage() {
        return "Đơn " + id + " hiện ở trạng thái " + status;
    }
}

public class ObjectDiagnosticsDemo {
    public static void main(String[] args) {
        Order order = new Order(
                "ORD-42",
                OrderStatus.CREATED,
                List.of(
                        new OrderLine("SKU-1", 2),
                        new OrderLine("SKU-2", 1)),
                "REQ-72",
                "khach@example.com",
                "secret-token-do-not-log");

        System.out.println(order); // Tự gọi toString().
        System.out.println("Kiểm tra: " + order);
        System.out.println(order.customerMessage());

        OrderLine line = new OrderLine("SKU-1", 2);
        System.out.println(line); // Record sinh toString() mặc định.
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ObjectDiagnosticsDemo.java
java ObjectDiagnosticsDemo
~~~

Kết quả:

~~~text
Order{id='ORD-42', status=CREATED, itemCount=2, traceId='REQ-72'}
Kiểm tra: Order{id='ORD-42', status=CREATED, itemCount=2, traceId='REQ-72'}
Đơn ORD-42 hiện ở trạng thái CREATED
OrderLine[sku=SKU-1, quantity=2]
~~~

### Vì sao thiết kế này hữu ích?

- `Order.toString()` cung cấp **bối cảnh tối thiểu cần cho việc điều tra**: đơn nào, trạng thái nào, có bao nhiêu dòng, trace nào.
- Không đưa `customerEmail` và `accessToken` vào chuỗi. Thậm chí dữ liệu bị che một phần vẫn cần đánh giá lại theo chính sách riêng tư; giải pháp mặc định an toàn hơn là **không thêm trường đó**.
- `lines` được chụp bằng `List.copyOf` khi dựng đối tượng, giảm nguy cơ một bên khác thay đổi cấu trúc danh sách từ bên ngoài. Vì `OrderLine` là record chỉ chứa `String` và `int`, phần tử ví dụ này cũng không có state mutable bên trong.
- `customerMessage()` diễn đạt **nội dung dành cho khách hàng**. Nó có hợp đồng riêng, không phụ thuộc chuỗi dành cho developer.
- `traceId` là một mã được truyền từ luồng xử lý; có thể dùng để liên kết sự kiện qua nhiều lớp. Nó **không tự sinh ra correlation/tracing** nếu hệ thống chưa thiết kế cơ chế truyền và ghi nhận trace.

Đoạn trên minh họa một **snapshot đơn giản**. Trong hệ thống thực, thay vì trực tiếp lấy trạng thái từ entity phức tạp hoặc lazy-loaded ORM object ở `toString()`, có thể dùng một diagnostic DTO hoặc tập các trường đã chuẩn hóa.

## 4. Quy tắc thiết kế một `toString()` tốt

Không có một định dạng bắt buộc cho mọi class. Thay vào đó, nên đánh giá qua các tiêu chí thực tế:

| Tiêu chí | Cách áp dụng | Rủi ro khi làm sai |
|---|---|---|
| **Ngắn gọn** | Chọn ID, trạng thái và vài thuộc tính liên quan lỗi | Log quá dài, khó đọc, tăng chi phí lưu trữ |
| **Có ngữ nghĩa** | `orderId`, `status`, `itemCount` | Chỉ thấy hash hoặc các field không rõ ý nghĩa |
| **An toàn thông tin** | Dùng allowlist, bỏ token, mật khẩu, thông tin cá nhân không cần thiết | Rò rỉ dữ liệu qua log và công cụ giám sát |
| **Không tác dụng phụ** | Không đổi trạng thái, không gọi mạng, không ghi DB | Việc “xem object” gây hành vi ngoài ý muốn |
| **Chịu được null** | Xử lý trường tùy chọn có thể null | `NullPointerException` khi ghi log |
| **Hiệu năng dự đoán được** | Không tải quan hệ lazy, không duyệt graph khổng lồ | N+1 query, treo luồng, tạo chuỗi lớn |
| **Không phụ thuộc format như API** | Cho phép sửa chữ mô tả để tăng khả năng chẩn đoán | Consumer parse `toString()` bị hỏng khi refactor |
| **Dễ hiểu khi đa luồng** | Snapshot bất biến hoặc đọc trạng thái có cơ chế đồng bộ rõ | Chuỗi tổng hợp từ nhiều thời điểm khác nhau |

Một `toString()` được gọi rất thường xuyên: trên console, trong IDE, khi format chuỗi, khi ghi log có đối số object hoặc trong một thông báo exception. Vì vậy việc thực thi nên **nhanh, an toàn và không bất ngờ**.

### Những gì không nên đưa mặc định vào `toString()`

- Mật khẩu, access token, refresh token, API key, session cookie, mã OTP, secret nội bộ.
- Thông tin cá nhân chi tiết (email, số điện thoại, địa chỉ, định danh) nếu không có căn cứ rõ ràng để ghi log.
- Nội dung request/response thô có thể chứa dữ liệu người dùng.
- Toàn bộ collection lớn, file, ảnh, blob hoặc kết quả truy vấn.
- Đối tượng service, connection, ORM proxy, graph hai chiều hoặc những quan hệ có thể kích hoạt truy vấn.

Kể cả **ID** cũng có thể được xem là dữ liệu nhạy cảm trong một số hệ thống. Hãy tuân theo chính sách phân loại dữ liệu; không mặc định rằng “không phải password” nghĩa là an toàn để ghi log.

## 5. `toString()` của `record`, collection và array

### 5.1. Record tự tạo chuỗi dựa trên thành phần khai báo

Java `record` tự sinh `toString()`, `equals()` và `hashCode()` theo các thành phần của record nếu ta không override. Ví dụ:

~~~java
record Coordinate(int x, int y) {}

System.out.println(new Coordinate(2, 5));
// Coordinate[x=2, y=5]
~~~

Điều này hữu ích với **value object chứa dữ liệu đã được phép hiển thị**. Nhưng hãy cẩn thận với record giữ dữ liệu nhạy cảm:

~~~java
// RỦI RO nếu để record tự sinh toString().
record Credentials(String username, String password) {}

// System.out.println(new Credentials("alice", "secret"));
// Có thể làm lộ cả password trong biểu diễn mặc định.
~~~

Ta có thể override:

~~~java
record SafeCredentials(String username, String password) {
    @Override
    public String toString() {
        return "SafeCredentials{username='" + username
                + "', password=<redacted>}";
    }
}
~~~

Trong production, cũng nên cân nhắc ẩn `username` nếu đó là dữ liệu cần bảo vệ. **Không chỉ log** mới có thể gọi `toString()`; đôi khi trình debug hoặc code xử lý exception cũng làm điều tương tự.

### 5.2. Collection có thể lồng `toString()` của từng phần tử

~~~java
List<OrderLine> lines = List.of(
        new OrderLine("SKU-1", 2),
        new OrderLine("SKU-2", 1));

System.out.println(lines);
// [OrderLine[sku=SKU-1, quantity=2],
//  OrderLine[sku=SKU-2, quantity=1]]
~~~

Đây là ví dụ logic; output thực tế thường nằm trên **một dòng**. Phương thức `toString()` của collection có thể gọi `String.valueOf`/`toString()` cho phần tử, vì vậy **một phần tử chứa dữ liệu nhạy cảm có thể làm cả collection bị lộ**.

Đừng nối `list.toString()` vào log ở đường chạy nóng nếu collection có hàng nghìn phần tử. Thay bằng `size`, số phần tử lỗi hoặc vài ID đã được chọn lọc. Với collection thay đổi đồng thời, việc duyệt để tạo chuỗi còn có thể chịu ảnh hưởng của concurrency.

### 5.3. Array khác collection

Array Java mặc định không có cách biểu diễn nội dung theo phần tử như `List`:

~~~java
int[] values = {1, 2, 3};

System.out.println(values);
// Chuỗi dạng [I@... (tên kiểu mảng + hash), không phải [1, 2, 3].

System.out.println(java.util.Arrays.toString(values));
// [1, 2, 3]
~~~

Với array lồng nhau:

~~~java
int[][] matrix = {{1, 2}, {3, 4}};

System.out.println(java.util.Arrays.toString(matrix));
// Các phần tử int[] được in dưới dạng tham chiếu [I@...

System.out.println(java.util.Arrays.deepToString(matrix));
// [[1, 2], [3, 4]]
~~~

Lưu ý `Arrays.deepToString` cũng có thể in một lượng dữ liệu lớn; với cấu trúc phức tạp, chỉ sử dụng cho dữ liệu đã được phép xuất ra log.

### 5.4. Chu kỳ tham chiếu dễ gây lỗi đệ quy

Hai object có thể tham chiếu lẫn nhau: `Parent → Child → Parent`. Nếu `Parent.toString()` nối `child` và `Child.toString()` lại nối `parent`, hai phương thức có thể gọi qua lại vô hạn dẫn tới `StackOverflowError`.

Ví dụ cần tránh:

~~~java
class Parent {
    Child child;

    @Override
    public String toString() {
        return "Parent{child=" + child + "}";
    }
}

class Child {
    Parent parent;

    @Override
    public String toString() {
        return "Child{parent=" + parent + "}";
    }
}
~~~

Thay vì in cả graph, nên in **ID của đối tượng liên quan** hoặc một mô tả cạn (*shallow representation*):

~~~java
// Hướng thiết kế tốt hơn (minh họa ý tưởng):
// "Parent{id=10, childId=20}"
// "Child{id=20, parentId=10}"
~~~

Tránh lạm dụng reflection để in tất cả field: khó kiểm soát dữ liệu nhạy cảm, quan hệ vòng, lazy loading và hiệu năng.

## 6. `toString()` không phải `equals()` hay `hashCode()`

Ba phương thức từ `Object` có mục đích khác nhau:

| Phương thức | Trả về | Mục đích điển hình |
|---|---|---|
| `toString()` | `String` | Quan sát/biểu diễn đối tượng |
| `equals(Object)` | `boolean` | Kiểm tra ngữ nghĩa “bằng nhau” theo hợp đồng class |
| `hashCode()` | `int` | Hỗ trợ bảng băm, như `HashMap`/`HashSet`, theo hợp đồng với `equals` |

Một class override `toString()` **không cần** override `equals()` hay `hashCode()` chỉ vì mục đích chẩn đoán. Ngược lại, nếu định nghĩa lại `equals()`, phải bảo đảm các đối tượng bằng nhau có cùng `hashCode()`.

Đừng đưa chuỗi `toString()` vào thuật toán `equals()` hoặc làm key lưu trữ mặc định. Nếu thay format để debug dễ hơn, điều đó không nên làm thay đổi định danh nghiệp vụ hoặc cấu trúc của tập hợp.

### `toString()` có phải định dạng ổn định?

Không có cam kết chung nào bắt buộc biểu diễn `toString()` của lớp tùy biến phải là schema ổn định theo phiên bản. Dù một vài lớp Java có format được document cụ thể, vẫn phải **xem hợp đồng từng API** trước khi dựa vào nó.

Ví dụ:

~~~java
// KHÔNG NÊN:
database.save("order_dump", order.toString());

// KHÔNG NÊN:
String responseBody = order.toString(); // coi như JSON cho client

// NÊN:
// DTO -> JSON serializer có schema/validation/phân quyền rõ ràng.
~~~

Nếu cần dấu vết có cấu trúc, ghi các trường được phép như `orderId`, `status`, `traceId` riêng biệt thông qua hệ thống log hỗ trợ structured logging; nếu cần giao tiếp API, dùng DTO với schema xác định.

## 7. Ghi log và chẩn đoán lỗi đúng cách

`System.out.println` hữu ích để học nhanh, nhưng trong ứng dụng Java/Spring nên dùng một **logging API** có level, nơi ghi, cấu hình định dạng và khả năng xử lý exception.

Các loại thông tin có giá trị trong chẩn đoán thường gồm:

- **Sự kiện:** đang tạo đơn, từ chối thanh toán, đã đổi trạng thái.
- **Định danh và tương quan:** `orderId`, `traceId`, request/correlation ID đã được cấp.
- **Trạng thái cần thiết:** giá trị hiện tại và hành động được thử.
- **Nguyên nhân thất bại:** loại exception, message phù hợp, stack trace và cause chain.
- **Thời gian và ngữ cảnh:** timestamp và môi trường, nhưng thường để logger/tracing framework tự bổ sung.

### 7.1. Java Util Logging (JDK có sẵn)

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

final class OrderDiagnostics {
    private static final Logger LOG =
            Logger.getLogger(OrderDiagnostics.class.getName());

    static void inspect(Order order) {
        // Supplier: xây chuỗi chẩn đoán khi thông điệp được log.
        LOG.log(Level.FINE, () -> "Order snapshot: " + order);
    }

    static void reportFailure(String orderId, Exception error) {
        // Logger nhận Throwable riêng để giữ stack trace.
        LOG.log(Level.WARNING,
                "Cannot process order " + orderId, error);
    }
}
~~~

Đây là snippet riêng, giả sử `Order` là class ở ví dụ chính. Gọi `OrderDiagnostics.inspect(order)` chỉ hữu ích nếu logger được cấu hình để ghi `FINE`. Dùng overload nhận `Supplier<String>` có thể tránh tạo chuỗi khi mức log bị tắt.

**Chú ý:** `Supplier` không tự xử lý dữ liệu nhạy cảm; nếu `Order.toString()` làm lộ token, log vẫn rò rỉ khi được bật. Và nếu `orderId` đến trực tiếp từ dữ liệu người dùng, cần hạn chế ký tự xuống dòng/ký tự điều khiển để tránh log injection; ID trong ví dụ chính đã được kiểm soát định dạng.

### 7.2. SLF4J / Spring: parameterized logging

Trong ứng dụng dùng SLF4J, cú pháp thường gặp:

~~~java
// Snippet dành cho dự án đã có SLF4J, không chạy bằng JDK trần.
private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(CheckoutService.class);

log.debug("Processing order: {}", order);
log.warn("Failed processing order {}", order.id(), exception);
~~~

`CheckoutService` ở đây là tên class minh họa; hãy thay bằng class thật của dự án. Đối số `order` có thể được chuyển thành chuỗi khi logger xử lý sự kiện, vì vậy phải **thiết kế `toString()` an toàn ngay từ gốc**. SLF4J parameterized logging thường tránh nối chuỗi trước khi xác định có cần ghi log, nhưng chi phí phụ thuộc implementation và cách sử dụng.

Với việc báo lỗi, truyền `Throwable` qua overload phù hợp giúp hệ thống log giữ **stack trace**, thay vì chỉ ghép `exception.toString()` vào chuỗi. Lưu ý backend/cấu hình có thể xử lý stack trace khác nhau.

### 7.3. `Exception.toString()`, `getMessage()` và stack trace

~~~java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    System.out.println(ex.getMessage()); // Mô tả riêng.
    System.out.println(ex.toString());    // Tên exception + mô tả.
    ex.printStackTrace();                 // Stack trace ra stderr.
}
~~~

Về mặt khái niệm:

| Cách lấy | Thông tin chính |
|---|---|
| `ex.getMessage()` | Lời nhắn gắn với exception (có thể null) |
| `ex.toString()` | Tên lớp exception và message nếu có |
| `ex.printStackTrace()` | Stack trace cùng thông tin exception/cause; ghi tới stream |
| `logger.log(Level.WARNING, "...", ex)` | Gửi exception cho logger để xử lý theo cấu hình |

Đừng gọi `ex.printStackTrace()` một cách tràn lan trong service production nếu đã có logger, vì nó ghi trực tiếp đến stream mặc định và khó tổ chức theo pipeline log. Stack trace cũng có thể mang thông tin nhạy cảm từ message; exception message cần được thiết kế cẩn thận.

## 8. Những lỗi hay gặp khi override `toString()`

### Lỗi A: tự động in mọi field mà không kiểm tra bảo mật

~~~java
// Minh họa SAI:
@Override
public String toString() {
    return "Account{email=" + email
            + ", apiToken=" + apiToken + "}";
}
~~~

Một lần `log.info("{}", account)` có thể khiến secret đi vào log và lưu lại lâu dài. Hãy xây **allowlist các field chẩn đoán** và kiểm tra các lớp lồng nhau.

### Lỗi B: lấy dữ liệu từ hệ thống bên ngoài trong `toString()`

~~~java
// Minh họa SAI:
@Override
public String toString() {
    return "Order{items=" + repository.findAllByOrder(id) + "}";
}
~~~

Một lời gọi `println(order)` có thể vô tình tạo I/O, N+1 queries, deadlock hoặc thất bại vì connection bị đóng. Lấy thông tin cần thiết **trước** khi tạo diagnostic snapshot; `toString()` chỉ format dữ liệu có sẵn.

### Lỗi C: phụ thuộc `toString()` để kiểm tra nghiệp vụ

~~~java
// Không nên dùng:
if (order.toString().contains("status=PAID")) {
    // ...
}
~~~

Hành vi nghiệp vụ phải dựa vào `order.status()`, enum hoặc phương thức có hợp đồng rõ, không parse văn bản phục vụ con người.

### Lỗi D: trả về null hoặc ném exception ngoài dự tính

Hợp đồng `Object.toString()` kỳ vọng một chuỗi biểu diễn đối tượng. Override nên trả về **chuỗi khác null**, đồng thời tránh phụ thuộc vào field tùy chọn mà có thể chưa khởi tạo.

~~~java
// Nếu nickname có thể null:
@Override
public String toString() {
    return "Profile{nickname="
            + java.util.Objects.toString(nickname, "<missing>")
            + "}";
}
~~~

Snippet trên giả định có một field `nickname`. Dùng dữ liệu đã có, không gọi callback hoặc method virtual phức tạp khiến việc in đối tượng gặp lỗi khó lường.

### Lỗi E: kết quả không giới hạn hoặc không an toàn khi đa luồng

In hàng chục nghìn phần tử có thể tạo áp lực GC và tăng độ trễ. Đọc nhiều field mutable mà không có cơ chế đồng bộ có thể tạo **ảnh chụp trạng thái không nhất quán**. Với dữ liệu lớn hoặc concurrent, nên tạo diagnostic DTO bất biến, có giới hạn kích thước, thu thập trong ranh giới đồng bộ khi cần và log theo dạng có cấu trúc.

Không nhất thiết mọi `toString()` phải dùng `StringBuilder`: phép nối chuỗi ngắn bằng dấu `+` rõ ràng và compiler/JVM thường tối ưu phù hợp. Chỉ tối ưu khi đo được chi phí thực tế và mục tiêu hiệu năng.

## 9. Kiểm thử biểu diễn chuỗi và chính sách bảo mật

Unit test cho `toString()` có thể kiểm tra **các thuộc tính quan trọng**: có ID để tra cứu, có trạng thái, không chứa dữ liệu nhạy cảm, không ném exception khi đối tượng hợp lệ.

Đặt tệp `ObjectDiagnosticsDemoTest.java` trong source set kiểm thử cùng package với `ObjectDiagnosticsDemo.java`, với dependency JUnit Jupiter 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class ObjectDiagnosticsDemoTest {

    private Order order() {
        return new Order(
                "ORD-42",
                OrderStatus.CREATED,
                List.of(new OrderLine("SKU-1", 2)),
                "REQ-72",
                "private@example.com",
                "token-top-secret");
    }

    @Test
    void diagnosticContainsUsefulFields() {
        String diagnostic = order().toString();

        assertTrue(diagnostic.contains("ORD-42"));
        assertTrue(diagnostic.contains("CREATED"));
        assertTrue(diagnostic.contains("itemCount=1"));
        assertTrue(diagnostic.contains("REQ-72"));
    }

    @Test
    void diagnosticDoesNotLeakSecrets() {
        String diagnostic = order().toString();

        assertFalse(diagnostic.contains("private@example.com"));
        assertFalse(diagnostic.contains("token-top-secret"));
        assertFalse(diagnostic.contains("customerEmail"));
        assertFalse(diagnostic.contains("accessToken"));
    }

    @Test
    void recordRepresentsSafeComponents() {
        String diagnostic = new OrderLine("SKU-1", 2).toString();

        assertEquals("OrderLine[sku=SKU-1, quantity=2]", diagnostic);
    }

    @Test
    void nullConversionIsPredictable() {
        assertEquals("null", String.valueOf((Object) null));
        assertEquals("<missing>", java.util.Objects.toString(
                null, "<missing>"));
    }
}
~~~

**Vì sao không luôn `assertEquals` toàn bộ `toString()`?** Nếu mục đích chỉ là chẩn đoán, test khớp toàn bộ dấu câu có thể quá giòn khi đổi format hợp lý. Hãy kiểm tra trường nào **bắt buộc có hoặc bắt buộc không được lộ**. Chỉ kiểm tra nguyên văn khi định dạng là một phần hợp đồng rõ ràng.

**Giới hạn của kiểm thử bảo mật:** Việc assert hai chuỗi bí mật không xuất hiện **không chứng minh tuyệt đối** không có dữ liệu nhạy cảm khác. Cần review field mới, xem nội dung của nested objects, kiểm tra log thực tế và áp dụng quy định phân loại dữ liệu.

## 10. Khi nào nên tạo mô hình chẩn đoán riêng?

`toString()` rất phù hợp cho chuỗi quan sát ngắn. Nhưng hệ thống lớn thường cần nhiều mức độ chi tiết:

- **Thông tin công khai:** mã theo dõi được phép chia sẻ, trạng thái mà người dùng cần biết.
- **Thông tin cho lập trình viên:** ID nội bộ hợp lệ, mã correlation, trạng thái kỹ thuật, tên component.
- **Thông tin phục vụ điều tra chuyên sâu:** timing, số lần retry, error codes, span IDs, chi tiết đã được làm sạch và được kiểm soát quyền truy cập.

Khi một object có thể hiển thị khác nhau tùy mục đích, đừng ép mọi nhu cầu vào `toString()`. Tạo các API khác nhau:

~~~java
record OrderDiagnostic(
        String orderId,
        String status,
        int itemCount,
        String traceId
) {}

record OrderPublicView(
        String reference,
        String customerFacingStatus
) {}
~~~

Hai record này là ví dụ về **hình dạng dữ liệu**. Trong API thực, đừng serialize `OrderDiagnostic` ra public endpoint chỉ vì nó là record: cần quyết định rõ nơi gửi, quyền truy cập và trường được phép. Bản thân record tự sinh `toString()` từ component, nên việc chọn component an toàn vẫn cực kỳ quan trọng.

Với logging có cấu trúc, thay vì chỉ có:

~~~text
Order{id='ORD-42', status=CREATED, traceId='REQ-72'}
~~~

hệ thống có thể ghi các trường riêng:

~~~json
{
  "event": "order.processing",
  "orderId": "ORD-42",
  "status": "CREATED",
  "traceId": "REQ-72"
}
~~~

JSON trên là **ví dụ minh họa schema log**, không phải kết quả của `Object.toString()`. Một logging framework có khả năng structured logging cần xử lý phần serialize, lọc field, làm sạch dữ liệu và giới hạn kích thước.

## 11. Bài tập thực hành: chẩn đoán PaymentAttempt

Tạo một class `PaymentAttempt` với những field:

| Field | Ví dụ | Được phép xuất trong chuỗi demo? |
|---|---|---|
| `attemptId` | `ATT-17` | Có |
| `orderId` | `ORD-42` | Có |
| `status` | `PENDING` | Có |
| `retryCount` | `2` | Có |
| `providerToken` | `sk_example_secret` | **Không** |
| `payerEmail` | `customer@example.com` | **Không** |
| `failureCode` | `PROVIDER_TIMEOUT` | Có khi là mã lỗi đã kiểm duyệt |

Các yêu cầu:

1. Override `toString()` để trả chuỗi ngắn có ID, status, retry count và mã lỗi nếu có.
2. Không đưa email, token hoặc nội dung raw provider response vào chuỗi.
3. Nếu `failureCode` là null, hiển thị một giá trị cố định như `none` mà không ném lỗi.
4. Viết test chứng minh secret không xuất hiện và chuỗi vẫn có các trường cần để điều tra.
5. Tạo danh sách 100.000 attempts và giải thích vì sao không nên log toàn bộ danh sách chỉ để biết số retry lỗi.
6. Viết method riêng `toCustomerMessage()` hoặc mapper DTO, chỉ trả trạng thái thân thiện với khách hàng.
7. Với trường hợp exception khi gọi provider, log `Throwable` qua API phù hợp để giữ stack trace; không chỉ ghép `ex.toString()`.

### Câu hỏi tự kiểm tra

1. Vì sao chuỗi dạng `ClassName@1a2b3c` không được xem như địa chỉ bộ nhớ hoặc ID nghiệp vụ?
2. `System.out.println(order)` thường dùng phương thức nào của đối tượng?
3. `String.valueOf(null)` khác gì gọi `nullReference.toString()`?
4. Record tự sinh `toString()` dựa vào đâu, và vì sao điều đó có thể nguy hiểm?
5. Khi nào nên dùng `Arrays.toString` và `Arrays.deepToString`?
6. Vì sao hai đối tượng trỏ vòng nhau có thể gây `StackOverflowError` trong `toString()` tự viết?
7. Vì sao parse `toString()` để xác định trạng thái đơn hàng là thiết kế kém bền vững?
8. Gửi `Exception` trực tiếp cho logger khác gì chỉ ghi `ex.getMessage()`?
9. Khi nào một diagnostic DTO hoặc structured logging phù hợp hơn `toString()`?

**Ghi nhớ:** **`toString()` là một biểu diễn hữu ích cho việc quan sát đối tượng**, do chính class quyết định. Hãy ưu tiên **ngữ nghĩa rõ, dữ liệu được phép hiển thị, xử lý nhanh và không có tác dụng phụ**. Những thông tin phục vụ khách hàng, serialization API, hợp đồng nghiệp vụ và điều tra bằng structured logs nên có giao diện thích hợp riêng, thay vì phụ thuộc vào một chuỗi debug.