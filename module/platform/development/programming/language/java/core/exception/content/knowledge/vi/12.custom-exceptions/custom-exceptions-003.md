# Đặt tên ngoại lệ tùy chỉnh theo tình huống thất bại và mức trừu tượng trong Java

Khi thiết kế **custom exception** trong Java, mục tiêu không chỉ là đặt tên một lớp kế thừa `Exception` hoặc `RuntimeException`. Tên ngoại lệ cần giúp người đọc trả lời hai câu hỏi: **“Điều gì đã thất bại?”** và **“Tầng nào chịu trách nhiệm diễn giải thất bại đó?”**. Một tên tốt làm rõ hành vi hợp đồng, cách khôi phục và ý nghĩa của `catch`; một tên chung chung hoặc rò rỉ chi tiết triển khai có thể khiến API khó sử dụng, khó bảo trì và khó thay đổi hạ tầng.

Ví dụ trong hệ thống đơn hàng:

- `OrderNotFoundException`: không tìm thấy đơn hàng mà người gọi yêu cầu.
- `OrderAlreadyPaidException`: thao tác thanh toán bị từ chối vì đơn đã được thanh toán.
- `PaymentDeclinedException`: yêu cầu thanh toán bị từ chối theo kết quả nghiệp vụ của quá trình thanh toán.
- `PaymentGatewayUnavailableException`: không thể liên hệ hoặc sử dụng cổng thanh toán để xác định kết quả.

Những lớp trên đều có thể là **tên minh họa do ứng dụng định nghĩa**, không phải lớp dựng sẵn của Java. Chúng truyền đạt các tình huống khác nhau. Đặc biệt, “bị từ chối” và “không gọi được hệ thống để biết kết quả” **không tương đương**: chính sách retry và thông báo người dùng có thể khác nhau.

Bài học hướng dẫn cách chọn tên ngoại lệ dựa trên tình huống thất bại và **mức trừu tượng** (domain, application/service, infrastructure, API boundary), khi nào dùng lại ngoại lệ chuẩn, khi nào tạo lớp riêng, cách chọn checked/unchecked, giữ nguyên nhân gốc, thiết kế constructor và kiểm thử hành vi. Ví dụ sử dụng Java 17+.

## 1. Ngoại lệ tùy chỉnh là gì và vì sao cần tên rõ nghĩa?

Ngoại lệ tùy chỉnh là một lớp do ứng dụng hoặc thư viện định nghĩa, kế thừa một lớp thuộc phân cấp `Throwable`, thường là `Exception` hoặc `RuntimeException`:

~~~java
// Một kiểu checked exception.
class OrderNotFoundException extends Exception {
    OrderNotFoundException(String message) {
        super(message);
    }
}

// Một kiểu unchecked exception.
class OrderAlreadyPaidException extends IllegalStateException {
    OrderAlreadyPaidException(String message) {
        super(message);
    }
}
~~~

Tên riêng hữu ích khi caller cần **nhận biết một trường hợp thất bại có ý nghĩa** khác với những trường hợp khác. Chẳng hạn, caller có thể hiển thị “không tìm thấy đơn” cho `OrderNotFoundException`, nhưng chặn việc thanh toán trùng cho `OrderAlreadyPaidException`.

Ngược lại, nếu phương thức chỉ nhận một đối số âm trong khi hợp đồng yêu cầu không âm, một `IllegalArgumentException` chuẩn thường đã đủ:

~~~java
static void reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity phải dương");
    }
}
~~~

Một lớp `BadQuantityException` không tự động tốt hơn nếu nó không bổ sung hợp đồng, hành vi phân loại hoặc thông tin hữu ích. Tạo ngoại lệ tùy chỉnh cần có lý do thiết kế cụ thể, tránh tạo nhiều loại chỉ để tên nhìn có vẻ “nghiệp vụ”.

**Nguyên tắc:** tên ngoại lệ là một phần của **ngôn ngữ API**, không phải chỉ là nhãn cho thông điệp log. Khi nó được công bố từ một thư viện hoặc module, các lớp client có thể sử dụng chính kiểu ngoại lệ đó trong `catch`, kiểm thử hoặc tài liệu.

## 2. Đặt tên theo tình huống thất bại: “điều gì xảy ra?”

Một tên tốt thường diễn đạt một **trạng thái hoặc kết quả không mong muốn**, gắn với đối tượng/thao tác cụ thể:

| Tình huống | Tên nên cân nhắc | Tên quá mơ hồ |
| --- | --- | --- |
| Không tìm thấy đơn được yêu cầu | `OrderNotFoundException` | `NotFoundError`, `DataException` |
| Thanh toán lại một đơn đã trả tiền | `OrderAlreadyPaidException` | `ProcessException`, `FailException` |
| Hết hàng trong lúc đặt | `InsufficientInventoryException` | `StockErrorException`, `SomethingWrongException` |
| Không nạp được cấu hình ứng dụng | `ConfigurationLoadException` | `FileErrorException`, `ServiceException` |
| Phiên sử dụng đã hết hạn | `SessionExpiredException` | `ExpiredException` |
| Không thể xác thực quyền truy cập | `AuthorizationDeniedException` | `SecurityProblemException` |
| Đơn bị khóa nên không chỉnh sửa được | `OrderLockedException` | `UpdateException` |
| Dịch vụ cổng thanh toán không khả dụng | `PaymentGatewayUnavailableException` | `HttpException` ở tầng nghiệp vụ |

Mỗi tên “nên cân nhắc” là **phương án thiết kế minh họa**, cần kiểm tra ngôn ngữ miền của dự án. Nếu API chuẩn đã có kiểu phù hợp, ưu tiên dùng lại thay vì tạo lớp mới.

Từ khóa thường hữu ích trong tên:

- **`NotFound`**: đối tượng cần tìm không tồn tại theo hợp đồng tra cứu; không dùng cho mọi lỗi kết nối khiến thao tác tra cứu không hoàn thành.
- **`Already...`**: thao tác đang vi phạm trạng thái đã hoàn tất, ví dụ `OrderAlreadyPaidException`.
- **`Invalid...`**: quy tắc dữ liệu hoặc trạng thái không hợp lệ, nhưng cần chỉ rõ *cái gì* không hợp lệ.
- **`Expired`**: tài nguyên phiên/token đã hết hiệu lực theo thời gian, không chỉ là “lỗi hệ thống”.
- **`Unavailable`**: phụ thuộc/hệ thống tạm thời không thể sử dụng, không đồng nghĩa yêu cầu bị từ chối vì nghiệp vụ.
- **`Load`/`Parse`/`Decode`**: thất bại của thao tác chuyển đổi/nạp trong một abstraction; nên phân biệt dữ liệu sai định dạng với không truy cập được dữ liệu.

Tên tốt không nhất thiết dài. `OrderNotFoundException` đã rõ trong một domain cụ thể; `OrderLookupFailedDueToInternalDatabaseConnectivityException` thường vừa rò rỉ triển khai vừa không ổn định.

## 3. Thế nào là “mức trừu tượng” của ngoại lệ?

Một hệ thống thường có nhiều tầng:

~~~text
API / UI
   ↓
Application / Service
   ↓
Domain / Business Rules
   ↓
Infrastructure / Database / Files / Network
~~~

Sơ đồ này là ví dụ tổ chức phổ biến, không phải cấu trúc bắt buộc của mọi ứng dụng. Cùng một sự cố có thể được **diễn giải khác** khi đi qua ranh giới tầng.

Ví dụ một file cấu hình bị từ chối truy cập:

1. Hạ tầng gọi `Files.readString(path)` và nhận `IOException` hoặc lớp con phù hợp.
2. Tầng nạp cấu hình biết thao tác của mình là **nạp cấu hình ứng dụng**, nên có thể bọc thành `ConfigurationLoadException`, giữ `IOException` làm cause.
3. Tầng API/UI quyết định cách báo cho người dùng, có thể ghi log toàn bộ lỗi nội bộ và trả thông điệp an toàn.

Ở tầng hạ tầng, `IOException` đã có ý nghĩa. Ở tầng cấu hình, chỉ nói `IOException` có thể là quá chi tiết hoặc quá hẹp với ý nghĩa của hợp đồng. Nhưng không phải cứ đi qua tầng mới là bắt buộc bọc; chỉ bọc khi **tạo ra ngữ nghĩa mới có giá trị**.

### 3.1. Ngoại lệ domain

Tên nhấn mạnh quy tắc hoặc khái niệm nghiệp vụ:

~~~java
// Các tên minh họa trong domain đơn hàng.
class OrderAlreadyPaidException extends IllegalStateException { /* ... */ }
class InsufficientInventoryException extends RuntimeException { /* ... */ }
~~~

Ở đây, kiểu ngoại lệ không nên phụ thuộc vào chi tiết rằng dữ liệu được lưu ở PostgreSQL, MongoDB, file CSV hay API bên ngoài. Nếu thay kho lưu trữ mà tên domain vẫn đúng, đó là tín hiệu mức trừu tượng hợp lý.

### 3.2. Ngoại lệ application/service

Tên diễn đạt thao tác mà một dịch vụ cung cấp đã thất bại:

~~~java
// Tên minh họa ở tầng dịch vụ.
class ConfigurationLoadException extends RuntimeException { /* ... */ }
class ReportGenerationException extends Exception { /* ... */ }
~~~

Caller biết **nạp cấu hình** hay **tạo báo cáo** thất bại, trong khi lỗi chi tiết của parser, tệp, mạng hoặc renderer có thể nằm trong `cause`.

### 3.3. Ngoại lệ infrastructure

Tên có thể phản ánh một phụ thuộc kỹ thuật ở đúng tầng đó, ví dụ `StorageUnavailableException` trong adapter lưu trữ. Nhưng không phải mọi IOException/SQLException đều cần một wrapper riêng. Hãy giữ exception chuẩn khi nó đã đủ thể hiện hợp đồng mà caller ở tầng đó cần xử lý.

### 3.4. Ranh giới API

Ở ranh giới REST/HTTP, GraphQL hoặc UI, có thể cần chuyển exception nội bộ thành **response có cấu trúc** hoặc thông báo thân thiện. Một HTTP status/error code không nhất thiết phải là tên lớp exception. Ví dụ `OrderNotFoundException` có thể được mapping thành HTTP 404 trong một API cụ thể, nhưng lớp domain không nên mặc định mang tên `Http404Exception` chỉ để thuận tiện cho controller.

**Không được mặc định** mọi `NotFound` luôn là HTTP 404, mọi lỗi validation đều HTTP 400 hay mọi exception đều tương ứng một status cố định; mapping là chính sách của từng API.

## 4. Chọn tên theo điều kiện thất bại, không theo câu lệnh ném

Xét phương thức:

~~~java
static void pay(Order order) {
    if (order.isPaid()) {
        throw new OrderAlreadyPaidException(order.id());
    }
    // Thực hiện thao tác thanh toán hợp lệ.
}
~~~

Đây là **đoạn minh họa**, cần định nghĩa `Order` và `OrderAlreadyPaidException` thích hợp. Quy tắc ở đây là “đơn đã thanh toán không được thanh toán lại”. Tên `OrderAlreadyPaidException` mô tả **điều kiện**, không mô tả thao tác “throw”.

Các tên kém rõ nghĩa:

- `PayException`: chỉ nói có liên quan đến thanh toán, không biết lý do.
- `InvalidException`: không biết cái gì bất hợp lệ.
- `RuntimeFailureException`: phản ánh kỹ thuật thay vì hợp đồng.
- `Exception1`, `CustomException`, `MyException`: không có nghĩa miền.
- `OrderException`: có thể dùng như lớp cha phân nhóm nhưng thường quá rộng nếu ném trực tiếp cho mọi lỗi cụ thể.

Một lớp cha `OrderException` **có thể hợp lý** khi caller có nhu cầu catch toàn bộ một nhóm lỗi domain, nhưng các lớp con vẫn cần phản ánh từng tình huống. Không nên tạo sâu nhiều tầng kế thừa chỉ để mô phỏng toàn bộ sơ đồ nghiệp vụ.

## 5. Độ chi tiết phù hợp: cụ thể đến mức có ích

Có hai thái cực không tốt:

**Quá rộng:** chỉ có `ApplicationException` và truyền message khác nhau cho tất cả trường hợp. Caller phải so sánh chuỗi thông điệp để quyết định cách xử lý:

~~~java
// Mã minh họa không nên dùng để phân loại lỗi.
catch (ApplicationException ex) {
    if ("NOT_FOUND".equals(ex.getMessage())) {
        // Fragile: phụ thuộc string message.
    }
}
~~~

**Quá hẹp:** tạo một lớp cho từng câu lệnh hoặc từng chi tiết hạ tầng, chẳng hạn `PostgresQuery42TimeoutOnOrdersTableException`. Khi đổi database, kiểu exception không còn diễn đạt hợp đồng ổn định, dù người gọi chỉ cần biết thao tác lưu trữ tạm thời không khả dụng.

Câu hỏi quyết định có cần một subtype riêng:

1. **Caller có hành động khác nhau không?** Ví dụ thiếu hàng thì yêu cầu chọn số lượng khác, cổng thanh toán lỗi thì thông báo thử lại.
2. **Đây có phải một điều kiện ổn định của hợp đồng API không?** Hay chỉ là bug/chi tiết nội bộ có thể biến mất khi refactor?
3. **Có thể tài liệu hóa chính xác “khi nào ném” không?** Nếu không, tên kiểu có thể đang quá mơ hồ.
4. **Tầng sử dụng có hiểu tên đó không?** Nếu caller là domain order, tên chứa vendor SDK có thể lệch abstraction.
5. **Một kiểu chuẩn đã đủ chưa?** Với null, chỉ số, trạng thái sai, Java thường đã có `NullPointerException`, `IndexOutOfBoundsException`, `IllegalArgumentException`, `IllegalStateException`.

Ưu tiên **ít loại nhưng có ý nghĩa khác biệt rõ ràng** hơn là một cây ngoại lệ khổng lồ không mang lại cách xử lý thực tế.

## 6. Java 17+ chạy được: `OrderNotFoundException` và `OrderAlreadyPaidException`

Ví dụ này tách hai tình huống domain khác nhau: tra cứu không có kết quả và thao tác thanh toán bị từ chối vì trạng thái hiện tại.

Lưu thành `OrderNamingDemo.java`:

~~~java
public class OrderNamingDemo {
    enum Status { DRAFT, PAID }

    static final class Order {
        final String id;
        Status status = Status.DRAFT;

        Order(String id) {
            this.id = id;
        }
    }

    static final class OrderNotFoundException extends Exception {
        OrderNotFoundException(String orderId) {
            super("Không tìm thấy đơn " + orderId);
        }
    }

    static final class OrderAlreadyPaidException extends IllegalStateException {
        OrderAlreadyPaidException(String orderId) {
            super("Đơn " + orderId + " đã thanh toán");
        }
    }

    static Order find(String orderId) throws OrderNotFoundException {
        if (!"A-17".equals(orderId)) {
            throw new OrderNotFoundException(orderId);
        }
        return new Order(orderId);
    }

    static void pay(Order order) {
        if (order.status == Status.PAID) {
            throw new OrderAlreadyPaidException(order.id);
        }
        order.status = Status.PAID;
    }

    public static void main(String[] args) throws OrderNotFoundException {
        Order order = find("A-17");
        pay(order);
        System.out.println("Trạng thái: " + order.status);
        try {
            pay(order);
        } catch (OrderAlreadyPaidException ex) {
            System.out.println("Nghiệp vụ: " + ex.getMessage());
        }
        try {
            find("B-42");
        } catch (OrderNotFoundException ex) {
            System.out.println("Tra cứu: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OrderNamingDemo.java
java OrderNamingDemo
~~~

Stdout chính xác:

~~~text
Trạng thái: PAID
Nghiệp vụ: Đơn A-17 đã thanh toán
Tra cứu: Không tìm thấy đơn B-42
~~~

### Phân tích các quyết định đặt tên

- **`OrderNotFoundException`**: biểu diễn kết quả tra cứu không có đơn phù hợp. Ở chương trình minh họa, lớp này là checked exception, nên `find` khai báo `throws OrderNotFoundException`; caller bắt hoặc tiếp tục khai báo kiểu đó.
- **`OrderAlreadyPaidException`**: biểu diễn trạng thái hiện tại khiến thao tác không hợp lệ; ví dụ chọn kế thừa `IllegalStateException`, nên nó là unchecked exception và caller không bắt buộc `catch`.
- Tên của hai ngoại lệ cho phép tách đường xử lý mà **không kiểm tra text message**. Đây là lợi ích thực chất của kiểu exception riêng.
- `find` là bộ mô phỏng tra cứu ổn định, còn `pay` chỉ đổi trạng thái trong bộ nhớ. Chương trình không triển khai thanh toán thật, không xử lý giao dịch đồng thời, không chứng minh idempotency của API thanh toán.
- Nếu trong ứng dụng thực, “không tìm thấy” là kết quả bình thường dự kiến, có thể thích hợp hơn khi dùng `Optional<Order>` thay vì ném checked exception. Đây là **lựa chọn thiết kế API**, không có một đáp án đúng duy nhất.
- Nếu “đã thanh toán” được coi là kết quả idempotent thành công, API có thể trả về trạng thái thay vì ném `OrderAlreadyPaidException`. Đề bài tập trung vào việc **đặt tên khi đã quyết định đây là ngoại lệ**, không áp đặt rằng tình huống này luôn phải ném.

### Vì sao dùng `extends IllegalStateException` thay vì `extends RuntimeException`?

Cả hai đều hợp lệ cho unchecked exception. Chọn `IllegalStateException` diễn đạt rằng lỗi liên quan đến **trạng thái của đối tượng hoặc thao tác**, và cho phép caller có nhu cầu bắt nhóm `IllegalStateException` nếu thật sự phù hợp. Đổi lại, cần bảo đảm ý nghĩa “state không cho phép” đúng với hợp đồng. Nếu dự án có phân cấp domain chung với những lý do rõ ràng, có thể chọn lớp cha khác.

Không nên quyết định parent class chỉ theo tên nghe đẹp. Parent class là một phần quan hệ kiểu và ảnh hưởng tới `catch`, vì vậy nên khớp **ngữ nghĩa lẫn chính sách checked/unchecked**.

## 7. Java 17+ chạy được: bọc lỗi I/O tại ranh giới cấu hình ứng dụng

Ở tầng hạ tầng, Java đã có `IOException`; caller của tầng ứng dụng lại quan tâm hơn đến việc **nạp cấu hình** có thành công hay không. `ConfigurationLoadException` là một tên gắn với trách nhiệm của tầng trên.

Lưu thành `ConfigurationBoundaryDemo.java`:

~~~java
import java.io.IOException;

public class ConfigurationBoundaryDemo {
    static final class ConfigurationLoadException extends RuntimeException {
        ConfigurationLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String readFromStorage(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("tệp cấu hình không đọc được");
        }
        return "mode=prod";
    }

    static String loadConfiguration(boolean fail) {
        try {
            return readFromStorage(fail);
        } catch (IOException ex) {
            throw new ConfigurationLoadException(
                    "Không thể nạp cấu hình ứng dụng", ex);
        }
    }

    public static void main(String[] args) {
        System.out.println("Giá trị: " + loadConfiguration(false));
        try {
            loadConfiguration(true);
        } catch (ConfigurationLoadException ex) {
            System.out.println("Tầng ứng dụng: " + ex.getMessage());
            System.out.println("Nguyên nhân kỹ thuật: "
                    + ex.getCause().getClass().getSimpleName()
                    + " - " + ex.getCause().getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ConfigurationBoundaryDemo.java
java ConfigurationBoundaryDemo
~~~

Stdout chính xác:

~~~text
Giá trị: mode=prod
Tầng ứng dụng: Không thể nạp cấu hình ứng dụng
Nguyên nhân kỹ thuật: IOException - tệp cấu hình không đọc được
~~~

**Điều cần học:**

1. `readFromStorage` công bố `throws IOException` vì đó là hợp đồng kỹ thuật của bước đọc.
2. `loadConfiguration` chuyển sang lỗi có ý nghĩa **ứng dụng**: không thể nạp cấu hình. Nó không dùng tên `FileReadErrorException` ở abstraction cao hơn.
3. Constructor `(message, cause)` giữ lại `IOException` để có thể truy vấn `getCause()` và in stack trace đầy đủ khi debug.
4. Caller `loadConfiguration` có thể bắt một loại lỗi cấp ứng dụng ổn định dù chi tiết lưu cấu hình thay đổi.
5. `ConfigurationLoadException` trong ví dụ là unchecked vì extends `RuntimeException`. Đây là quyết định minh họa. Nếu caller phải thực hiện một bước khôi phục có kiểm tra ở thời điểm biên dịch, dự án có thể chọn checked exception.
6. `readFromStorage` dùng giá trị mô phỏng để stdout không phụ thuộc file thật. Trong code sản phẩm, logic phải giải quyết `IOException` của API đọc thực tế và chính sách logging/bảo mật dữ liệu.

**Không bọc nếu không tạo giá trị mới.** Nếu abstraction gọi `readFromStorage` đã công bố `IOException` và caller đang xử lý đúng loại đó, việc thêm `new RuntimeException("read failed", ex)` chỉ để đổi tên có thể làm hợp đồng kém rõ hơn.

## 8. Tên theo loại thất bại hay thao tác thất bại?

Hai cách đặt tên đều có thể hữu ích:

- **Theo tình huống:** `OrderNotFoundException`, `SessionExpiredException`, `InsufficientInventoryException`.
- **Theo thao tác:** `ConfigurationLoadException`, `ReportGenerationException`, `InvoiceExportException`.

Chọn cách phản ánh tốt hơn điều **người gọi thực sự muốn biết**. Với `OrderNotFoundException`, caller phân biệt được tìm không thấy so với không liên hệ được hệ thống. Với `ReportGenerationException`, có thể chấp nhận một tên theo thao tác nếu mọi thất bại tạo báo cáo đều có chính sách xử lý tương tự ở tầng sử dụng.

Nhưng `ProcessFailedException` hoặc `OperationException` không xác định được thao tác hay tình huống. Nếu một lớp không thể tách biệt hợp đồng từ tên, cần xem nó có nên tồn tại hay không.

Sơ đồ lựa chọn:

~~~text
Có một trường hợp thất bại cụ thể?
    |
    +-- Có --> Caller cần phân biệt và xử lý riêng?
    |             |
    |             +-- Có --> Đặt tên theo điều kiện rõ ràng.
    |             |
    |             +-- Không --> Dùng exception chuẩn hoặc lớp cha phù hợp.
    |
    +-- Không --> Một thao tác ở abstraction hiện tại thất bại?
                  |
                  +-- Có --> Tên theo thao tác/mức trừu tượng nếu có giá trị.
                  |
                  +-- Không --> Xem lại có cần custom exception không.
~~~

Sơ đồ chỉ là **hướng dẫn tư duy**, không thay thế phân tích hợp đồng và chính sách lỗi của sản phẩm.

## 9. Phân biệt kết quả nghiệp vụ với lỗi hạ tầng

Một sai sót nguy hiểm là dùng cùng một kiểu cho hai điều kiện không tương đương.

Ví dụ với thanh toán:

| Điều kiện | Tên minh họa | Phản ứng có thể khác |
| --- | --- | --- |
| Ngân hàng/cổng thanh toán xác nhận giao dịch bị từ chối | `PaymentDeclinedException` | Hiển thị lý do an toàn; yêu cầu phương thức thanh toán khác |
| Cổng thanh toán không phản hồi | `PaymentGatewayUnavailableException` | Kiểm tra trạng thái giao dịch trước khi retry; không tuyên bố thanh toán bị từ chối |
| Đơn đã thanh toán trước đó | `OrderAlreadyPaidException` | Tránh thực hiện thu tiền lặp; trả trạng thái phù hợp |
| Dữ liệu request không hợp lệ | `IllegalArgumentException` hoặc kiểu validation của API | Sửa dữ liệu đầu vào trước khi gọi lại |

**Cảnh báo quan trọng:** “cổng thanh toán timeout” không nhất thiết chứng minh giao dịch chưa thực hiện. Nếu việc retry có thể tạo thanh toán trùng, xử lý an toàn cần cơ chế idempotency/đối soát theo hệ thống thanh toán. Đây là ví dụ cho thấy **tên exception không chỉ ảnh hưởng log, mà còn ảnh hưởng quyết định nghiệp vụ**.

Không nên đặt `PaymentFailedException` cho mọi kết quả nếu caller cần phân biệt từ chối, đã xử lý và không biết trạng thái. Ngược lại, nếu API thật sự chỉ công bố một lỗi cấp cao và mọi nguyên nhân đều có cùng cách xử lý, một lớp tổng quát kèm cause có thể hợp lý.

## 10. Ranh giới giữa kiểm tra đầu vào và ngoại lệ domain

Các loại chuẩn như `IllegalArgumentException`, `IllegalStateException`, `NullPointerException` rất hữu ích khi hợp đồng không đòi hỏi kiểu riêng.

Ví dụ:

~~~java
static void setPageSize(int pageSize) {
    if (pageSize < 1 || pageSize > 500) {
        throw new IllegalArgumentException("pageSize phải từ 1 đến 500");
    }
}
~~~

Nếu đây chỉ là precondition của một phương thức nội bộ, không cần tạo `InvalidPageSizeException` trong hầu hết trường hợp. Nhưng nếu một API công khai có chính sách thông báo hoặc cách phục hồi đặc biệt cho một tình huống validation, kiểu riêng có thể hữu ích.

Cách quyết định:

- **Vi phạm tiền điều kiện của lời gọi:** thường xem xét exception chuẩn.
- **Quy tắc/domain invariant cụ thể:** xem xét tên domain nếu caller cần phân biệt.
- **Một kết quả dự kiến bình thường:** xem xét return type/`Optional`/result object thay vì lạm dụng exception.
- **Một phụ thuộc hệ thống thất bại:** có thể giữ exception chuẩn hoặc bọc ở boundary cấp cao.
- **Bug lập trình:** thường không cần lớp `UnexpectedBugException` riêng cho từng vị trí.

Tránh cấu trúc mà mọi lỗi đều `catch (Exception ex)` rồi ném `BusinessException("thất bại")`; điều này có thể biến bug kỹ thuật thành lỗi nghiệp vụ và làm mất phân loại mà người vận hành cần.

## 11. Chọn `Exception` hay `RuntimeException` theo hợp đồng

Đặt tên nói lên **điều kiện thất bại**. Lựa chọn superclass quyết định **cách Java kiểm tra** tại nơi gọi:

| Đặc điểm | `extends Exception` (không thuộc RuntimeException) | `extends RuntimeException` |
| --- | --- | --- |
| Phân loại | Checked | Unchecked |
| Caller có bị compiler buộc bắt hoặc khai báo khi có thể thoát? | Có | Không |
| Thích hợp khi | API cần công bố một tình huống có khả năng xử lý rõ ở ranh giới lời gọi | Vi phạm hợp đồng/trạng thái hoặc chính sách dự án muốn truyền lỗi mà không ép catch |
| Có thể dùng constructor `(message, cause)`? | Có | Có |
| Có nên đặt tên theo domain/boundary? | Có | Có |

**Không có quy tắc “lỗi nghiệp vụ luôn checked” hay “lỗi hạ tầng luôn unchecked”.** Ví dụ `OrderNotFoundException` có thể checked hoặc unchecked tùy hợp đồng; thiếu đơn hàng cũng có thể được biểu diễn bằng `Optional.empty()`. Tên biểu đạt điều kiện không nhất thiết mã hóa lựa chọn checked/unchecked.

Cân nhắc cụ thể:

1. Caller có đường phục hồi hợp lý và bạn muốn **bắt buộc nhận diện** trường hợp đó tại compile time không?
2. Đây là lỗi sử dụng API sai hay một tình huống có thể xảy ra dù caller gọi đúng?
3. Hệ sinh thái/framework trong dự án có ràng buộc hay quy ước nào?
4. Thay đổi checked exception trong public API có thể khiến các caller cũ phải sửa `catch`/`throws`; bạn đã cân nhắc tương thích chưa?
5. Nếu dùng unchecked, đã tài liệu hóa điều kiện lỗi đủ rõ chưa?

Không kéo mọi lỗi domain vào `RuntimeException` chỉ để tránh viết `throws`; cũng không biến mọi lỗi có thể xảy ra thành checked exception khiến chữ ký API quá tải.

## 12. Constructor nên cung cấp thông tin gì?

Một custom exception đơn giản, hữu ích thường hỗ trợ thông điệp và cause:

~~~java
public class ConfigurationLoadException extends RuntimeException {
    public ConfigurationLoadException(String message) {
        super(message);
    }

    public ConfigurationLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là **lớp hoàn chỉnh**, lưu trong `ConfigurationLoadException.java` nếu dùng trực tiếp. Không cần viết tất cả các constructor một cách máy móc; chỉ công bố những overload caller thật sự cần.

Khi lỗi có metadata ổn định, có thể thêm field mang ý nghĩa hợp đồng:

~~~java
public class OrderNotFoundException extends Exception {
    private final String orderId;

    public OrderNotFoundException(String orderId) {
        super("Không tìm thấy đơn " + orderId);
        this.orderId = orderId;
    }

    public String orderId() {
        return orderId;
    }
}
~~~

Mã trên là lớp hoàn chỉnh, dùng tên riêng của hệ thống và getter `orderId()`. Nếu cần API rộng, cần quyết định có nên công bố mã định danh và thông tin gì cho caller hay không; **không để dữ liệu nhạy cảm** như thông tin thanh toán, token, mật khẩu hoặc dữ liệu cá nhân vào message/log chỉ để dễ debug.

Nếu lỗi bao gồm một `cause`, constructor truyền nó vào `super(message, cause)` thay vì chỉ lưu `cause.getMessage()`, vì chuỗi text không bảo toàn loại exception, stack trace và các suppressed errors của nguyên nhân.

### Có nên công bố enum mã lỗi?

Trong API cần phân loại có cấu trúc, có thể dùng một `ErrorCode` hoặc kiểu kết quả được tài liệu hóa thay vì tạo vô số exception subtype. Ví dụ các lỗi cùng chính sách xử lý có thể được phân biệt bằng `code()`; nhưng nếu caller thường `catch (SpecificException)`, subtype riêng có thể rõ ràng hơn.

**Không dùng text message làm mã lỗi ổn định.** Thông điệp có thể được dịch, chỉnh sửa và bổ sung ngữ cảnh; những thay đổi đó không nên làm hỏng logic caller.

## 13. Giữ cause đúng mức khi chuyển abstraction

Một phương thức có thể bọc ngoại lệ của tầng dưới để cung cấp ngữ nghĩa tầng trên:

~~~java
// Minh họa trong catch (IOException ex).
throw new ConfigurationLoadException(
        "Không thể nạp cấu hình ứng dụng", ex);
~~~

Người dùng tầng application nhìn thấy `ConfigurationLoadException`; người điều tra có thể gọi `getCause()` để thấy `IOException` gốc. Điều này **khác với đổi tên tùy ý**:

~~~java
// Không nên làm mất cause:
catch (IOException ex) {
    throw new ConfigurationLoadException("Không thể nạp cấu hình ứng dụng");
}
~~~

Đoạn trên hợp lệ nếu constructor `(String)` tồn tại, nhưng nguyên nhân kỹ thuật đã bị bỏ khỏi chuỗi cause. Nếu có yêu cầu an toàn thông tin, hãy quản lý phần trình bày ra người dùng và log nội bộ thay vì mặc định vứt bỏ toàn bộ thông tin lỗi.

**Giữ cause không phải cớ để bọc mọi tầng.** Nếu một tầng chỉ chuyển tiếp ngoại lệ đúng hợp đồng đã công bố, có thể không cần wrapper. Bọc nhiều tầng với cùng nội dung `"failed"` khiến log rối mà không tăng ý nghĩa.

Khi có suppressed exceptions từ `try-with-resources`, nếu tầng dưới đã nhận chúng và ngoại lệ đó được dùng làm cause của wrapper, chúng vẫn gắn với cause. Khi điều tra, kiểm tra suppressed trên các tầng liên quan, không chỉ outermost.

## 14. Tên exception có được chứa công nghệ cụ thể không?

**Có thể, nhưng phải đúng vị trí abstraction.**

Ở một adapter PostgreSQL, tên kỹ thuật có thể hợp lý nếu API công khai của adapter gắn chặt với PostgreSQL. Nhưng nếu một tầng domain/order public API được thiết kế để không phụ thuộc công nghệ lưu trữ, `PostgresConnectionRefusedException` truyền thẳng ra caller có thể khiến domain bị khóa vào triển khai hiện tại.

Ví dụ phân biệt:

~~~text
Infrastructure:
    SQLException("connection refused")
            |
            v
Application boundary:
    OrderRepositoryUnavailableException(..., cause)
            |
            v
Order service:
    không thể tra cứu đơn ở lượt hiện tại
~~~

Sơ đồ này là minh họa; không bắt buộc mỗi tầng phải tạo thêm một đối tượng ngoại lệ. Chọn một boundary có trách nhiệm để diễn đạt điều kiện có ý nghĩa cho caller, rồi giữ cause kỹ thuật.

Nếu API domain **cần** phân biệt “không tìm thấy đơn” và “không thực hiện được tra cứu”, đừng biến cả hai thành `OrderNotFoundException`. Không trả được kết quả do mạng lỗi không chứng minh đơn hàng không tồn tại.

## 15. Đặt tên nhóm và cây kế thừa: đơn giản trước

Bạn có thể tổ chức:

~~~java
// Khung tên minh họa.
class OrderException extends RuntimeException { /* ... */ }
class OrderAlreadyPaidException extends OrderException { /* ... */ }
class OrderLockedException extends OrderException { /* ... */ }
~~~

Một `catch (OrderException ex)` có thể bắt các lỗi domain có cùng superclass, còn caller cần xử lý cụ thể có thể bắt subtype. Tuy nhiên cần xem xét:

- Những lỗi có thực sự cùng **chính sách xử lý** ở nơi bắt rộng không?
- Cây kế thừa có đang ép những điều kiện khác nhau vào cùng một nhóm không?
- Có trùng lặp với superclass chuẩn như `IllegalStateException` không?
- Có cần hỗ trợ cả checked và unchecked không? Một cây kế thừa đơn không thể vừa là checked vừa là unchecked theo hai nhánh khác nhau.
- Tên superclass `OrderException` có giúp gì thực tế hay chỉ tạo thêm tầng?

Kế thừa không bắt buộc để có tên custom exception tốt. Nhiều ứng dụng dùng các lớp exception độc lập và chỉ tạo một hierarchy khi có **giá trị xử lý chung** thật sự.

## 16. Naming convention và khả năng đọc mã

Một số quy ước thực dụng của Java:

1. **Tên lớp dùng PascalCase**, ví dụ `OrderNotFoundException`.
2. **Hậu tố `Exception`** giúp người đọc và IDE nhận biết loại lớp trong phân cấp ngoại lệ. Đây là quy ước rất phổ biến.
3. **Hạn chế hậu tố `Error`** cho lỗi ứng dụng bình thường; `java.lang.Error` thuộc nhánh có ngữ nghĩa khác và thường không phải cơ chế báo lỗi nghiệp vụ có thể phục hồi.
4. Dùng từ **cụ thể, được nhóm hiểu giống nhau**. Nếu domain gọi đối tượng là `Invoice`, đừng có chỗ dùng `Bill` và chỗ khác `Invoice` không nhất quán.
5. **Không mã hóa toàn bộ thông điệp lỗi** trong tên lớp, ví dụ `OrderWithIdMissingInDatabaseException`; phần message và metadata có thể mang chi tiết động.
6. Giữ tên **ổn định theo hợp đồng**. Tên gắn với vendor hoặc cơ sở dữ liệu dễ lỗi thời khi đổi nền tảng.
7. Với lỗi cùng tình huống nhưng nhiều ngữ cảnh, cân nhắc một loại exception + field/code rõ nghĩa thay vì các lớp trùng nhau chỉ khác tên thao tác.

Ngôn ngữ codebase có thể có quy tắc khác; cần thống nhất với phong cách hiện hữu, nhưng không từ bỏ tính chính xác về ý nghĩa lỗi chỉ để thỏa mẫu tên.

## 17. Khi nào cần tài liệu hóa `@throws`?

Tài liệu JavaDoc nên nói rõ **điều kiện ném**, không chỉ lặp tên exception:

~~~java
/**
 * Thanh toán một đơn đang ở trạng thái cho phép.
 *
 * @param order đơn hàng hợp lệ cần thanh toán
 * @throws OrderAlreadyPaidException nếu đơn đã được thanh toán
 */
static void pay(Order order) {
    // Thân triển khai nghiệp vụ.
}
~~~

Đây là minh họa, cần định nghĩa `Order` và `OrderAlreadyPaidException`. Tài liệu này giúp caller biết khi nào lỗi xuất hiện và liệu có nên kiểm tra trạng thái trước khi gọi hay không.

Một JavaDoc không hữu ích:

~~~java
/**
 * @throws OrderAlreadyPaidException khi có OrderAlreadyPaidException
 */
~~~

Thẻ `@throws` là **tài liệu**, còn mệnh đề `throws SomeCheckedException` trong chữ ký là **cú pháp ngôn ngữ có tác động đến compile-time checking**. Với unchecked exception, có thể tài liệu hóa bằng `@throws` ngay cả khi chữ ký không khai báo `throws`.

Cần đồng bộ tên, điều kiện trong JavaDoc, kiểu được ném trong code và test. Nếu hợp đồng đã quy định `OrderNotFoundException`, đừng triển khai một nhánh lại ném `IllegalArgumentException` cho chính trường hợp đó mà không có lý do.

## 18. Những phản ví dụ giúp nhận diện sai mức trừu tượng

### 18.1. Biến lỗi hạ tầng thành “not found”

~~~java
// Anti-pattern: không được coi lỗi truy vấn DB là bằng chứng đối tượng không tồn tại.
catch (SQLException ex) {
    throw new OrderNotFoundException("Không thấy đơn");
}
~~~

Đoạn này minh họa một quyết định **sai ý nghĩa**; nó còn phụ thuộc constructor tương ứng. Nếu truy vấn thất bại do database offline, bạn chưa xác định đơn có tồn tại không. Nên dùng `OrderLookupException`, `RepositoryUnavailableException` hoặc một loại phù hợp với contract và giữ `cause`, thay vì khẳng định `NotFound`.

### 18.2. Gộp từ chối thanh toán với timeout

~~~text
PaymentDeclinedException
    != PaymentGatewayUnavailableException
~~~

Bị từ chối là một **kết quả đã biết**; không thể liên hệ là **thiếu kết quả xác định**. Trong hệ thống thu tiền, nhầm hai loại có thể dẫn tới retry sai.

### 18.3. Lạm dụng tên `ValidationException`

`ValidationException` có thể hợp lý nếu API thống nhất nhiều lỗi validation vào một loại kèm danh sách trường/vi phạm. Nhưng nếu mọi `ValidationException` chỉ có message tự do, caller khó tách “sai email”, “thiếu mã” và “vi phạm giới hạn”. Khi cần xử lý có cấu trúc, cân nhắc object chứa danh sách violations thay vì tạo một exception subtype cho mỗi field.

### 18.4. Đổi tên hạ tầng theo từng dòng code

`JdbcQueryFailedAtLine52Exception` phản ánh vị trí triển khai dễ thay đổi, không phải abstraction ổn định. Stack trace/cause đã cung cấp vị trí kỹ thuật; tên type nên đóng góp **ý nghĩa semantic** khác.

## 19. Kiểm thử exception name như một phần hợp đồng

Đừng chỉ kiểm thử message. Nên có các kiểm thử về:

- **Đúng loại exception cho đúng điều kiện:** đơn không tồn tại → `OrderNotFoundException`, đơn đã thanh toán → `OrderAlreadyPaidException`.
- **Không phát sinh exception đó trong điều kiện khác:** database timeout không được báo “không tìm thấy đơn” nếu chưa xác minh kết quả.
- **Cause được bảo toàn:** nếu tầng service bọc `IOException`, `getCause()` phải là ngoại lệ kỹ thuật gốc (hoặc một wrapper trung gian được công bố).
- **Thông tin có cấu trúc:** nếu exception có `orderId()`, field phải khớp id đầu vào và không bị trộn với message.
- **Phân biệt checked/unchecked đúng hợp đồng:** compiler yêu cầu catch-or-declare cho checked exception; unchecked không buộc.
- **Khả năng tương thích:** khi thêm hay thay loại lỗi public API, các caller xử lý theo type có thể phải cập nhật.

Ví dụ test thủ công không cần thư viện bên ngoài:

~~~java
// Minh họa trong một phương thức có lớp OrderNamingDemo truy cập được.
try {
    OrderNamingDemo.find("B-42");
    throw new AssertionError("Dự kiến phải ném OrderNotFoundException");
} catch (OrderNamingDemo.OrderNotFoundException ex) {
    System.out.println("Đúng loại: " + ex.getClass().getSimpleName());
}
~~~

Trong source `OrderNamingDemo` của mục 6, các lớp lồng có quyền truy cập package phù hợp; đặt đoạn test cùng package hoặc điều chỉnh modifier khi tách thành API công khai. Đây là **đoạn minh họa không độc lập**, vì phụ thuộc code từ ví dụ trước.

Điểm kiểm tra là **kiểu ngoại lệ**. Nếu chỉ assert string `"Không tìm thấy"`, một loại ngoại lệ sai vẫn có thể lọt qua vì tình cờ cùng message.

## 20. Khi nào không nên tạo custom exception?

Không phải mọi tình huống không thành công đều cần `throw`. Một số lựa chọn khác:

| Tình huống | Lựa chọn có thể phù hợp | Lý do |
| --- | --- | --- |
| Tìm một đối tượng theo id, không tồn tại là chuyện thường | `Optional<Order>` hoặc kiểu kết quả | Không buộc caller vào đường exceptional cho một kết quả dự kiến |
| Phân tích dữ liệu người dùng với nhiều vi phạm | Result chứa danh sách `ValidationError` | Hiển thị nhiều lỗi cùng lúc thay vì chỉ lỗi đầu tiên |
| Dữ liệu đầu vào lập trình sai rõ ràng | `IllegalArgumentException` | Exception chuẩn đã diễn đạt precondition |
| Chỉ số ngoài giới hạn | `IndexOutOfBoundsException` | Exception chuẩn đã rõ nghĩa |
| Tác vụ I/O thông thường | `IOException` hoặc lớp con chuẩn | Không thêm wrapper nếu tầng caller đã chấp nhận hợp đồng I/O |
| Luồng nghiệp vụ có thể chờ/chọn phương án | Result object/enum có trạng thái | Caller xử lý mọi kết quả chủ động |

Custom exception phù hợp nhất khi **lỗi thật sự có tính exceptional trong hợp đồng cụ thể** và caller được lợi từ việc phân biệt bằng type hoặc metadata.

## 21. Checklist đặt tên trước khi công bố API

Trước khi tạo hoặc đổi tên exception, tự hỏi:

1. **Điều kiện chính xác nào làm loại exception này được ném?**
2. **Tên có chỉ rõ domain object hoặc thao tác thất bại không?**
3. **Tên có khiến người đọc tưởng một kết quả đã được xác định, trong khi thực tế chỉ biết thao tác không hoàn thành không?**
4. **Nó thuộc abstraction nào và caller ở tầng đó có hiểu được không?**
5. **Nó rò rỉ vendor, table, file path, HTTP status hoặc chi tiết implementation không cần thiết không?**
6. **Một exception chuẩn hay result object đã đủ chưa?**
7. **Có cần caller xử lý riêng theo type không? Nếu không, có thể gom một nhóm hợp lý không?**
8. **Nên checked hay unchecked theo nghĩa vụ của caller?**
9. **Đã bảo toàn `cause`, stack trace và các thông tin cần chẩn đoán chưa?**
10. **Thông điệp/metadata có tránh lộ dữ liệu nhạy cảm không?**
11. **JavaDoc `@throws` và kiểm thử có nói cùng một điều kiện không?**
12. **Tên và hợp đồng có còn hợp lý nếu đổi implementation?**

Nếu không thể diễn đạt điều kiện bằng một câu cụ thể như “ném khi đơn ở trạng thái PAID mà API không cho thanh toán lại”, tên custom exception có thể đang quá rộng hoặc bài toán vẫn chưa được mô hình hóa đúng.

## 22. Lỗi thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách làm tốt hơn |
| --- | --- | --- |
| Đặt `MyException`, `CustomException`, `Exception1` | Không nói được điều kiện hay abstraction | Đặt tên theo trường hợp thất bại |
| Đặt mọi lỗi là `BusinessException` | Caller phải phân tích text/code mơ hồ | Phân nhóm có ý nghĩa hoặc dùng result có cấu trúc |
| Gọi timeout là `NotFoundException` | Có thể báo sai rằng đối tượng không tồn tại | Phân biệt “không có kết quả” và “không tra cứu được” |
| Gọi mọi thất bại thanh toán là `PaymentDeclinedException` | Dễ nhầm timeout với bị từ chối | Tách trạng thái biết được và trạng thái chưa xác định |
| Bọc `IOException` mà bỏ `cause` | Mất stack trace/loại lỗi gốc | `super(message, cause)` |
| Dùng lớp exception chứa tên vendor ở domain API | Khóa abstraction vào chi tiết hạ tầng | Bọc tại boundary bằng tên ổn định |
| Tạo custom exception cho mọi `IllegalArgumentException` | API phình to mà ít lợi ích | Dùng built-in nếu đủ nghĩa |
| Chọn checked/unchecked chỉ theo sở thích | Làm caller khó xử lý hoặc bỏ qua trường hợp cần bắt | Thiết kế theo hợp đồng và đường phục hồi |
| Lạm dụng `Error` cho lỗi nghiệp vụ | Sai kỳ vọng phân cấp `Throwable` | Kế thừa `Exception`/`RuntimeException` phù hợp |
| Dùng message làm mã điều khiển | Message đổi là logic lỗi | Dùng type/code có hợp đồng |
| Bọc lỗi ở mọi tầng với message giống nhau | Cause chain dài, log nhiễu | Bọc khi có ngữ nghĩa mới |
| Tên quá cụ thể về SQL/file/line | Khó thay đổi triển khai | Diễn đạt nghĩa ở abstraction hiện tại |

## 23. Tự kiểm tra kiến thức

**Câu 1.** Khi lookup đơn thất bại vì database offline, nên ném `OrderNotFoundException` không?

**Đáp án:** Không chỉ vì query thất bại. Không tra cứu được **không chứng minh** đơn không tồn tại. Dùng loại lỗi thể hiện phụ thuộc không khả dụng hoặc thao tác lookup thất bại, phù hợp với abstraction.

**Câu 2.** `OrderAlreadyPaidException` và `OrderNotFoundException` có cùng nghĩa không?

**Đáp án:** Không. Một loại là vi phạm trạng thái thanh toán; loại kia là không tìm được đối tượng.

**Câu 3.** Tên ngoại lệ nên gắn với tên bảng SQL hay ngữ nghĩa public API?

**Đáp án:** Ở public domain/application API, ưu tiên ngữ nghĩa ổn định mà caller hiểu. Chi tiết SQL phù hợp hơn trong tầng hạ tầng hoặc cause.

**Câu 4.** Có bắt buộc mọi custom exception đều extends `RuntimeException` không?

**Đáp án:** Không. Có thể kế thừa `Exception` để tạo checked exception; lựa chọn theo hợp đồng bắt/khai báo của caller.

**Câu 5.** Vì sao `ConfigurationLoadException` có thể tốt hơn `IOException` tại một application boundary?

**Đáp án:** Nó giải thích **thao tác nạp cấu hình** thất bại, không buộc caller hiểu nguồn cấu hình là tệp, mạng hay lưu trữ khác; `IOException` có thể được giữ làm cause.

**Câu 6.** Nếu không có caller nào xử lý `InvalidPageSizeException` khác với `IllegalArgumentException`, có nên tạo lớp riêng không?

**Đáp án:** Thường không cần, trừ khi có hợp đồng hoặc metadata đặc biệt khác làm kiểu riêng hữu ích.

**Câu 7.** Thông điệp `ex.getMessage()` có nên dùng làm mã lỗi bền vững không?

**Đáp án:** Không. Nên dùng exception type hoặc error code được tài liệu hóa khi cần phân loại.

**Câu 8.** Khi bọc `IOException`, constructor custom exception nên có gì?

**Đáp án:** Nên nhận `message` và `cause`, chuyển vào `super(message, cause)` để bảo toàn thông tin chẩn đoán.

**Câu 9.** Một exception có tên theo thao tác như `ReportGenerationException` luôn là lựa chọn sai không?

**Đáp án:** Không. Nó phù hợp khi failure ở mức thao tác đó là đơn vị trừu tượng caller cần xử lý. Tên chung `OperationException` mới thường khó dùng.

**Câu 10.** Nếu một API coi “đã thanh toán” là kết quả idempotent thành công, có nhất thiết ném `OrderAlreadyPaidException` không?

**Đáp án:** Không. Khi tình huống là kết quả hợp lệ theo hợp đồng, có thể trả trạng thái phù hợp. Lựa chọn exception phụ thuộc vào ngữ nghĩa API.

## 24. Tài liệu tham khảo

- [Java SE 17 API — `Exception`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): constructor exception checked và mối liên hệ với `Throwable`.
- [Java SE 17 API — `RuntimeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): unchecked exception, constructor message/cause.
- [Java SE 17 API — `IllegalArgumentException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html) và [`IllegalStateException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalStateException.html): hai loại chuẩn phổ biến có thể dùng thay vì tự tạo lớp.
- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, stack trace, suppressed exceptions và phương thức chẩn đoán.
- [Java Language Specification 17 — §11, Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): quy tắc ngoại lệ checked/unchecked và xử lý.
- [Java Language Specification 17 — §8.4.6, Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): mệnh đề `throws` của phương thức.

**Ghi nhớ:** custom exception nên được đặt tên theo **điều kiện thất bại có giá trị với caller** và **mức abstraction công bố lỗi**. Dùng tên riêng khi nó giúp phân loại/hành động; dùng exception chuẩn khi đã đủ; tránh tên mơ hồ hoặc rò rỉ hạ tầng; và giữ `cause` khi bọc để không mất nguyên nhân kỹ thuật.
