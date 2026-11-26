# Ánh xạ lỗi nhất quán giữa các tầng mà không che giấu nguyên nhân

Trong chương **Các mối quan tâm xuyên tầng**, bài học này tập trung vào cách một lỗi được nhận diện, chuyển tiếp và biểu diễn nhất quán khi đi qua các tầng của ứng dụng. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là tổ chức phần mềm theo kiến trúc phân tầng: tầng trình bày xử lý giao thức, tầng ứng dụng điều phối ca sử dụng, tầng nghiệp vụ bảo vệ quy tắc và tầng truy cập dữ liệu làm việc với cơ chế lưu trữ.

Một lỗi có thể bắt đầu từ dữ liệu đầu vào sai, quy tắc nghiệp vụ bị vi phạm, bản ghi không tồn tại, database mất kết nối hoặc một lỗi lập trình bất ngờ. Nếu mỗi tầng tự bắt mọi exception rồi trả về `null`, thông báo chung hoặc một exception mới không còn nguyên nhân ban đầu, hệ thống sẽ khó chẩn đoán và khó phản hồi đúng cho người gọi. Ngược lại, nếu trả nguyên thông báo SQL, stack trace hoặc tên lớp nội bộ ra API, hệ thống có thể làm lộ chi tiết triển khai và tạo hợp đồng phụ thuộc vào framework.

Mục tiêu là phân loại lỗi theo ý nghĩa, chuyển đổi ở đúng ranh giới và giữ lại thông tin kỹ thuật cần thiết để điều tra. **Ánh xạ lỗi nhất quán** không có nghĩa mọi lỗi đều biến thành cùng một loại exception hoặc cùng một HTTP status. Nó có nghĩa mỗi tầng có quy tắc rõ ràng về lỗi mà nó sở hữu, cách truyền lỗi lên trên và cách chuyển lỗi thành kết quả phù hợp với người nhận.

Sau bài học, bạn có thể:

- Phân biệt lỗi giao thức, lỗi đầu vào, lỗi nghiệp vụ, lỗi hạ tầng và lỗi lập trình.
- Quyết định khi nào nên giữ nguyên exception, khi nào cần chuyển thành exception có ý nghĩa ở ranh giới tầng.
- Bảo toàn cause chain khi bọc hoặc chuyển exception.
- Ánh xạ lỗi ứng dụng thành phản hồi HTTP ổn định mà không tiết lộ thông tin nội bộ.
- Kết hợp logging, correlation ID, transaction và retry với chính sách xử lý lỗi.
- Kiểm thử cả phân loại lỗi và cách biểu diễn lỗi ở từng ranh giới.

## 1. Lỗi đi qua các tầng như thế nào?

Xét ca sử dụng tạo đơn hàng. Client gửi request, controller chuyển request thành command, dịch vụ ứng dụng điều phối nghiệp vụ và repository ghi dữ liệu. Lỗi có thể phát sinh ở bất kỳ bước nào:

~~~mermaid
flowchart TD
    A[HTTP Request] --> B[Presentation Adapter]
    B -->|Dữ liệu sai định dạng| E1[Lỗi giao thức / đầu vào]
    B --> C[Application Use Case]
    C -->|Vi phạm quy tắc| E2[Lỗi nghiệp vụ]
    C --> D[Data Access Adapter]
    D -->|Timeout / constraint / SQL| E3[Lỗi lưu trữ]
    E1 --> F[Error Mapping tại ranh giới]
    E2 --> F
    E3 --> F
    F --> G[HTTP Response / Log / Metric]
~~~

Từng tầng hiểu một phần khác nhau của lỗi:

- Tầng trình bày biết request có đúng cấu trúc giao thức hay không và cần phản hồi client theo hợp đồng nào.
- Tầng ứng dụng biết ca sử dụng đang thực hiện bước nào và lỗi đó có thể được consumer xử lý ra sao.
- Tầng nghiệp vụ biết điều kiện nào bị vi phạm, chẳng hạn không đủ tồn kho hoặc trạng thái đơn hàng không cho phép chuyển tiếp.
- Tầng truy cập dữ liệu biết chi tiết SQL, ORM, constraint và kết nối; nó có thể nhận diện một số lỗi kỹ thuật hoặc ràng buộc lưu trữ.

Không tầng nào cần biết toàn bộ chi tiết của mọi tầng khác. Tầng dữ liệu không nên quyết định HTTP status; mô hình nghiệp vụ không nên phụ thuộc `HttpServletResponse`; controller không nên phân tích mã lỗi SQL để đoán quy tắc miền.

## 2. Phân loại lỗi theo ý nghĩa

Trước khi quyết định chuyển exception, hãy xác định lỗi thuộc nhóm nào và ai có trách nhiệm xử lý nó.

| Nhóm lỗi | Ví dụ | Nơi thường nhận diện | Hướng xử lý |
|---|---|---|---|
| Giao thức và giải mã | JSON sai cú pháp, UUID trên path sai định dạng, thiếu body | Adapter trình bày/framework | Từ chối request theo hợp đồng giao thức, thường là HTTP 400. |
| Ràng buộc đầu vào | Trường bắt buộc rỗng, số lượng không dương | Tầng trình bày hoặc validator đầu vào | Trả lỗi validation có cấu trúc, chỉ rõ trường không hợp lệ. |
| Xác thực và quyền | Chưa đăng nhập, actor không có quyền | Adapter bảo mật và tầng ứng dụng | Ánh xạ theo chính sách xác thực/phân quyền, thường là 401 hoặc 403 với HTTP. |
| Nghiệp vụ | Đơn đã đóng, tồn kho không đủ, trạng thái không cho phép | Tầng nghiệp vụ hoặc ứng dụng | Trả kết quả/lỗi nghiệp vụ ổn định; có thể là 404, 409 hoặc 422 tùy hợp đồng. |
| Hạ tầng và lưu trữ | Database timeout, mất kết nối, dịch vụ ngoài không phản hồi | Adapter hạ tầng và tầng ứng dụng | Giữ nguyên nguyên nhân kỹ thuật, phân loại khả năng phục hồi và phản hồi phù hợp. |
| Lỗi lập trình hoặc trạng thái bất ngờ | Null không dự kiến, invariant bị phá vỡ, lỗi cấu hình | Bất kỳ tầng nào | Ghi nhận đầy đủ để điều tra, trả phản hồi an toàn và không giả vờ thành lỗi người dùng. |

Một exception Java không tự cho biết cách ánh xạ ra giao thức. Ví dụ `IllegalArgumentException` có thể do người dùng gửi dữ liệu sai, nhưng cũng có thể do một lập trình viên gọi API sai. Không nên ánh xạ mọi `IllegalArgumentException` thành HTTP 400 chỉ dựa trên tên lớp. Hãy dùng exception hoặc kiểu kết quả có ngữ nghĩa rõ ràng tại ranh giới cần phân loại.

## 3. Nguyên tắc chuyển đổi exception giữa các tầng

### Chuyển đổi khi ngữ nghĩa thay đổi

Một tầng nên chuyển exception khi nó có thể bổ sung ý nghĩa thuộc trách nhiệm của mình. Ví dụ, adapter lưu trữ nhận một lỗi constraint của database. Nếu adapter xác định chắc chắn constraint đó tương ứng với quy tắc “mã đơn đã được sử dụng”, nó có thể chuyển thành exception mang ý nghĩa ứng dụng như `OrderNumberAlreadyUsedException`.

Nếu không nhận diện được nguyên nhân hoặc lỗi không thuộc hợp đồng đã công bố, hãy để exception kỹ thuật tiếp tục được xử lý ở tầng có đủ ngữ cảnh. Không nên bắt mọi `RuntimeException` rồi đổi thành `BusinessException` chung; cách đó làm mất khả năng phân biệt lỗi dữ liệu, lỗi hạ tầng và lỗi lập trình.

### Giữ nguyên cause chain

Khi bọc exception, luôn giữ exception gốc làm `cause` nếu cần chuyển ngữ nghĩa hoặc bổ sung ngữ cảnh. Java hỗ trợ constructor `super(message, cause)`:

~~~java
public final class OrderNumberAlreadyUsedException
        extends RuntimeException {

    public OrderNumberAlreadyUsedException(
            String orderNumber,
            Throwable cause) {
        super("Mã đơn hàng đã được sử dụng: " + orderNumber, cause);
    }
}
~~~

Đoạn code này giữ lỗi database trong cause chain để log có thể truy ra nguyên nhân kỹ thuật. Thông điệp của exception hướng tới ngữ nghĩa ứng dụng, không cần chứa câu SQL hoặc tên bảng. Khi exception mới được ném ra, stack trace vẫn có liên kết tới exception ban đầu.

Tránh kiểu xử lý sau:

~~~java
try {
    repository.save(order);
} catch (DataAccessException exception) {
    throw new RuntimeException(exception.getMessage());
}
~~~

Đoạn code trên tạo exception mới chỉ với thông điệp, làm mất cause chain và ngữ nghĩa của exception ban đầu. Khi điều tra production, log có thể chỉ còn một thông báo chung và không còn biết database đã báo lỗi gì.

### Không chuyển đổi chỉ để đổi tên

Nếu một tầng không bổ sung ngữ nghĩa, không thay đổi hợp đồng và không có lý do bảo vệ chi tiết nội bộ, việc bọc exception có thể chỉ làm tăng độ sâu stack trace. Giữ nguyên exception thường tốt hơn. Chuyển đổi cần có mục đích: che giấu API của framework, diễn đạt lỗi theo ngôn ngữ của tầng, hoặc cung cấp một hợp đồng ổn định cho consumer.

### Không bắt lỗi rồi tiếp tục như thể thành công

Không trả `null`, danh sách rỗng hoặc giá trị mặc định cho mọi lỗi chỉ để tránh exception. Những giá trị đó có thể là kết quả hợp lệ, khiến consumer không thể phân biệt “không có dữ liệu” với “không đọc được dữ liệu”. Nếu lỗi có thể được phục hồi, hãy trả một kiểu kết quả có trạng thái rõ ràng hoặc để exception phù hợp truyền lên nơi có chính sách xử lý.

## 4. Ví dụ: chuyển lỗi database thành lỗi có ý nghĩa

Giả sử `order_number` có ràng buộc duy nhất. Repository adapter dùng Spring JDBC hoặc Spring Data có thể nhận `DataIntegrityViolationException` khi ghi trùng. Chỉ khi xác định đúng constraint tương ứng với mã đơn, adapter mới chuyển lỗi thành exception ứng dụng:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class JdbcOrderRepository implements OrderRepository {
    private final JdbcTemplate jdbc;

    JdbcOrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void save(Order order) {
        try {
            jdbc.update(
                    "insert into orders (id, order_number) values (?, ?)",
                    order.id(), order.orderNumber());
        } catch (DataIntegrityViolationException exception) {
            if (isOrderNumberUniqueConstraint(exception)) {
                throw new OrderNumberAlreadyUsedException(
                        order.orderNumber(), exception);
            }
            throw exception;
        }
    }

    private boolean isOrderNumberUniqueConstraint(Throwable exception) {
        // Adapter-specific: inspect vendor error / constraint metadata.
        return DatabaseErrors.matchesConstraint(
                exception, "uk_orders_order_number");
    }
}
~~~

`isOrderNumberUniqueConstraint` và `DatabaseErrors` là phần minh họa cần triển khai theo database đang dùng; không nên dựa vào việc so khớp chuỗi thông báo lỗi nếu driver cung cấp mã lỗi hoặc tên constraint đáng tin cậy hơn. Một `DataIntegrityViolationException` cũng có thể do khóa ngoại, `NOT NULL` hoặc constraint khác, vì vậy không được chuyển mọi trường hợp thành “mã đơn đã tồn tại”.

Nếu adapter không thể nhận diện chính xác constraint, nó ném lại exception ban đầu. Khi đó, tầng xử lý lỗi chung có thể ghi nhận đây là lỗi lưu trữ chưa được phân loại và phản hồi lỗi hệ thống phù hợp. Cách làm này giữ được nguyên nhân thay vì gán nhầm một ý nghĩa nghiệp vụ.

Spring có cơ chế exception translation cho một số adapter persistence. `JdbcTemplate` sử dụng hệ exception `DataAccessException`; repository JPA được cấu hình phù hợp cũng có thể chuyển exception persistence thành hệ exception của Spring. Điều này giúp consumer ít phụ thuộc vào exception riêng của driver hoặc ORM. Tuy vậy, exception translation của framework không tự hiểu toàn bộ ngữ nghĩa nghiệp vụ; adapter vẫn cần chuyển các trường hợp cụ thể khi có đủ căn cứ.

## 5. Lỗi nghiệp vụ nên độc lập với HTTP và database

Tầng nghiệp vụ diễn đạt điều kiện của miền bài toán. Ví dụ:

~~~java
import java.util.UUID;

public final class InsufficientStockException extends RuntimeException {
    private final String productId;

    public InsufficientStockException(String productId) {
        super("Không đủ tồn kho cho sản phẩm " + productId);
        this.productId = productId;
    }

    public String productId() {
        return productId;
    }
}

public final class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(UUID orderId) {
        super("Không tìm thấy đơn hàng " + orderId);
    }
}
~~~

Các exception này thể hiện ý nghĩa của nghiệp vụ. Chúng không kế thừa `ResponseStatusException`, không chứa `HttpStatus` và không phụ thuộc `SQLException`. Nếu cùng ca sử dụng được gọi từ HTTP, CLI hoặc batch, mỗi adapter có thể xử lý chúng theo cách riêng.

Không nhất thiết mọi lỗi nghiệp vụ đều phải là exception. Với một số thao tác dự kiến có nhiều kết quả, kiểu kết quả tường minh như `ApprovalResult` hoặc `Either<Failure, Success>` có thể dễ hiểu hơn. Exception phù hợp khi luồng thông thường bị gián đoạn hoặc khi quy ước của ứng dụng dùng exception cho lỗi. Hãy nhất quán trong một hợp đồng và phân biệt rõ kết quả hợp lệ với lỗi.

## 6. Ánh xạ lỗi ở ranh giới trình bày

HTTP adapter chuyển lỗi của ứng dụng thành mã trạng thái và body theo hợp đồng API. Tầng nghiệp vụ không cần biết `404`, `409` hay `422`; đó là quyết định của adapter trình bày.

Một cách phân loại thường gặp:

| Lỗi ứng dụng hoặc giao thức | Phản hồi HTTP thường dùng | Ý nghĩa với client |
|---|---|---|
| JSON sai cú pháp, tham số sai định dạng | `400 Bad Request` | Request không đáp ứng cấu trúc API. |
| Chưa xác thực | `401 Unauthorized` | Client cần cung cấp thông tin xác thực hợp lệ. |
| Không có quyền thực hiện | `403 Forbidden` | Danh tính đã được xác thực nhưng không được phép. |
| Tài nguyên không tồn tại | `404 Not Found` | Không tìm thấy đối tượng được yêu cầu. |
| Xung đột trạng thái hoặc khóa duy nhất | `409 Conflict` | Yêu cầu không thể áp dụng với trạng thái hiện tại. |
| Dữ liệu hợp lệ về cú pháp nhưng không thỏa quy tắc theo hợp đồng | `422 Unprocessable Content` hoặc `409` | Client cần điều chỉnh nội dung hoặc trạng thái yêu cầu. |
| Dịch vụ phụ thuộc tạm thời không sẵn sàng | `503 Service Unavailable` | Client có thể thử lại nếu hợp đồng cho phép. |
| Lỗi không dự kiến | `500 Internal Server Error` | Hệ thống gặp lỗi; client không nhận chi tiết nội bộ. |

Đây là gợi ý, không phải bảng ánh xạ bắt buộc cho mọi API. Một API có thể chọn `409` hoặc `422` cho một số trường hợp theo ngữ nghĩa đã công bố. Điều quan trọng là mã trạng thái, error code và hành vi retry phải ổn định, được tài liệu hóa và không thay đổi tùy tiện theo lớp exception bên dưới.

### Dùng `@RestControllerAdvice` để tập trung ánh xạ

Với Spring MVC, `@RestControllerAdvice` có thể tập trung chuyển các exception đã biết thành response. Ví dụ sử dụng `ProblemDetail` của Spring Framework 6:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(
            OrderNotFoundException exception) {
        var problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Đơn hàng không tồn tại.");
        problem.setTitle("Không tìm thấy đơn hàng");
        problem.setProperty("code", "ORDER_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(OrderNumberAlreadyUsedException.class)
    ResponseEntity<ProblemDetail> handleDuplicateOrderNumber(
            OrderNumberAlreadyUsedException exception) {
        var problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Mã đơn hàng đã được sử dụng.");
        problem.setTitle("Không thể tạo đơn hàng");
        problem.setProperty("code", "ORDER_NUMBER_ALREADY_USED");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
~~~

Client nhận mã lỗi ổn định như `ORDER_NOT_FOUND` hoặc `ORDER_NUMBER_ALREADY_USED`, không cần biết exception đến từ lớp nào hoặc database dùng constraint tên gì. `ProblemDetail` cho phép thêm các thuộc tính mở rộng như error code, danh sách lỗi trường hoặc correlation ID nếu API quy định.

### Lỗi validation

Lỗi Bean Validation ở request thường được xử lý riêng vì client cần biết trường nào sai. Có thể ánh xạ thành một danh sách lỗi có cấu trúc gồm tên trường và mã lỗi ổn định. Hạn chế trả nguyên thông điệp validator nếu thông điệp đó chứa tên lớp, giá trị nhạy cảm hoặc chi tiết triển khai. Thông báo cho người dùng có thể được bản địa hóa ở tầng trình bày.

### Fallback cho lỗi không dự kiến

Một handler tổng quát nên ghi lại exception đầy đủ ở phía server và trả thông báo an toàn:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
class UnexpectedErrorHandler {
    private static final Logger log =
            LoggerFactory.getLogger(UnexpectedErrorHandler.class);

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception exception) {
        var incidentId = IncidentContext.currentId();
        log.error("Unexpected request failure, incidentId={}",
                incidentId, exception);

        var problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "Đã xảy ra lỗi. Vui lòng thử lại sau hoặc cung cấp mã sự cố khi liên hệ hỗ trợ.");
        problem.setTitle("Lỗi hệ thống");
        problem.setProperty("code", "INTERNAL_ERROR");
        problem.setProperty("incidentId", incidentId);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

`IncidentContext` là thành phần minh họa để lấy mã sự cố/correlation đã được tạo và quản lý trong request context. Không nên tin một giá trị ID tùy ý từ client mà không giới hạn định dạng và độ dài. Nếu hệ thống chưa có incident ID, có thể bỏ thuộc tính đó hoặc dùng trace ID được sinh bởi middleware quan sát.

Handler tổng quát là lớp bảo vệ cuối cùng. Các lỗi đã biết cần được ánh xạ cụ thể trước đó. Không trả `exception.getMessage()`, stack trace, SQL, tên host, đường dẫn file hoặc credential trong response. Thông tin chi tiết thuộc log và hệ thống quan sát có kiểm soát quyền truy cập.

Trong ví dụ, advice tổng quát được đặt ở mức ưu tiên thấp nhất để các advice có handler chuyên biệt được thử trước. Một dự án cũng có thể đặt fallback trong cùng `@RestControllerAdvice` với các handler cụ thể; tránh để handler `Exception.class` ở một advice ưu tiên cao hơn che mất các ánh xạ chuyên biệt.

## 7. Giữ nguyên nguyên nhân nhưng bảo vệ thông tin bên ngoài

Có hai mục tiêu cần đạt đồng thời:

- **Bên trong hệ thống:** giữ exception gốc, cause chain, stack trace, mã lỗi database hoặc thông tin kỹ thuật đủ để điều tra.
- **Bên ngoài hệ thống:** chỉ công bố error code, thông điệp và chi tiết mà hợp đồng cho phép người gọi biết.

Ví dụ, lỗi database có thể chứa tên bảng, constraint, dữ liệu đầu vào hoặc endpoint. Những thông tin đó có thể hữu ích cho kỹ sư vận hành nhưng không nhất thiết an toàn để gửi cho client. Tầng trình bày nên ánh xạ exception sang một lỗi công khai ổn định thay vì serialize đối tượng exception.

Không nên xóa nguyên nhân khi tạo lỗi công khai. Có thể giữ exception gốc trong log và chỉ gửi một DTO/ProblemDetail đã chọn lọc. Cũng không nên lưu toàn bộ request body hoặc thông tin xác thực vào log khi điều tra; cần loại bỏ token, mật khẩu, dữ liệu cá nhân hoặc trường nhạy cảm theo chính sách bảo vệ dữ liệu.

## 8. Logging, correlation và tránh ghi log trùng lặp

Log cần giúp nối các sự kiện thuộc cùng một request hoặc ca sử dụng. Một bản ghi có ích thường chứa:

- Thời điểm, mức độ nghiêm trọng và tên thành phần.
- Correlation ID hoặc trace ID để liên kết log giữa các tầng và dịch vụ.
- Mã ca sử dụng, mã đối tượng ở mức an toàn và nguồn khởi chạy khi cần.
- Error code nội bộ hoặc loại exception đã phân loại.
- Stack trace ở nơi có trách nhiệm ghi nhận lỗi, khi cần điều tra.

Không nên log cùng một exception ở mọi tầng rồi ném tiếp. Điều đó tạo nhiều stack trace giống nhau, làm nhiễu cảnh báo và khiến một sự cố trông như nhiều lỗi độc lập. Thường nên để tầng thấp chuyển exception với cause được giữ nguyên, sau đó tầng biên hoặc nơi thực sự quyết định xử lý ghi log một lần ở mức phù hợp.

Có ngoại lệ: một tầng có thể ghi log một sự kiện phục hồi hoặc fallback ngay tại nơi nó xảy ra, ví dụ retry lần thứ hai thành công. Khi đó log cần mô tả sự kiện có ý nghĩa, không chỉ lặp lại cùng stack trace. Các lỗi dự kiến như người dùng nhập sai có thể được ghi ở mức `INFO` hoặc metric mà không cần stack trace ở mức `ERROR`.

Correlation ID nên được truyền qua các lời gọi cần liên kết, kể cả message hoặc job nền. Không phụ thuộc hoàn toàn vào thread-local của HTTP request vì tác vụ bất đồng bộ có thể chạy trên thread khác. Với message, có thể đưa trace context vào metadata message và khôi phục nó ở consumer theo chuẩn quan sát đang dùng.

## 9. Ảnh hưởng của lỗi đến transaction và dữ liệu

Một exception không chỉ quyết định response; nó còn có thể quyết định transaction có commit hay rollback. Trong Spring, transaction mặc định thường rollback khi phương thức transactional kết thúc bằng `RuntimeException` hoặc `Error`. Checked exception không tự động rollback theo mặc định trừ khi cấu hình `rollbackFor` hoặc quy tắc tương ứng.

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    var order = orders.getById(orderId);
    order.confirm();
    orders.save(order);
    inventory.reserve(order);
}
~~~

Nếu `inventory.reserve` ném unchecked exception và exception thoát khỏi phương thức qua proxy transaction, thay đổi trong transaction sẽ được rollback theo cấu hình thông thường. Nếu phương thức bắt exception rồi trả về bình thường, Spring có thể commit vì transaction interceptor không còn thấy exception thoát ra. Khi cần chuyển lỗi, hãy ném exception mới có cause hoặc đánh dấu transaction rollback-only theo cách có chủ đích.

Không nên đổi exception nghiệp vụ thành checked/unchecked chỉ để làm cho rollback xảy ra mà không xét hợp đồng. Hãy quyết định rõ lỗi nào làm hủy đơn vị công việc, lỗi nào được xử lý và tiếp tục, và cách cấu hình rollback tương ứng. Nếu một batch xử lý từng bản ghi độc lập, mỗi bản ghi có thể cần transaction riêng để một lỗi không rollback toàn bộ lô.

Với thao tác phân tán qua database và message broker, rollback database không thể thu hồi một message đã gửi thành công. Nếu cần bảo đảm phát sự kiện nhất quán với dữ liệu đã commit, cân nhắc transactional outbox hoặc một cơ chế phối hợp phù hợp.

## 10. Retry và phân biệt lỗi có thể phục hồi

Không phải lỗi nào cũng nên thử lại. Có thể phân loại:

| Loại lỗi | Retry? | Lý do và chính sách |
|---|---|---|
| Dữ liệu sai định dạng | Không | Cần client sửa request. |
| Vi phạm quy tắc nghiệp vụ | Thường không | Thử lại cùng dữ liệu thường không làm điều kiện thay đổi. |
| Không có quyền | Không | Cần thay đổi danh tính hoặc quyền. |
| Timeout hoặc mất kết nối tạm thời | Có thể | Dùng số lần giới hạn, exponential backoff và jitter; kiểm tra tính idempotent. |
| Deadlock hoặc xung đột khóa tạm thời | Có thể | Thử lại toàn bộ đơn vị công việc trong transaction mới sau khi transaction trước đã rollback, với giới hạn rõ ràng. |
| Lỗi lập trình hoặc cấu hình | Không tự động | Cần sửa nguyên nhân; retry liên tục có thể làm hệ thống quá tải. |

Retry nên được đặt ở tầng biết được thao tác có an toàn khi lặp và biết giới hạn của lần thử. Ví dụ, message consumer có thể retry lỗi kết nối tạm thời; ca sử dụng đặt hàng cần idempotency key hoặc ràng buộc duy nhất để tránh tạo hai đơn nếu client timeout sau khi server đã commit.

Không ánh xạ mọi lỗi thành HTTP 503 chỉ vì muốn client thử lại. Mã phản hồi cần phản ánh trạng thái thật; nếu API hỗ trợ retry, tài liệu cần mô tả trường hợp, khoảng chờ và cách tránh lặp tác dụng phụ. Với message hoặc job, cần có retry limit, dead-letter queue hoặc trạng thái thất bại để không lặp vô hạn.

## 11. Lỗi trong tác vụ nền, CLI và batch

Không phải mọi lỗi đều được gửi thành HTTP response. Một ca sử dụng có thể được gọi từ nhiều adapter, mỗi adapter biểu diễn lỗi theo hợp đồng riêng:

| Adapter | Cách biểu diễn lỗi | Điều cần giữ |
|---|---|---|
| HTTP | Status code, error code, ProblemDetail | Thông điệp an toàn, ổn định và phù hợp với client. |
| CLI | Thông báo ngắn và exit code khác 0 | Người vận hành hiểu bước thất bại; log giữ chi tiết kỹ thuật. |
| Scheduled job | Trạng thái lần chạy, metric, log và cảnh báo | Phân biệt lỗi từng mục với lỗi làm cả lần chạy thất bại. |
| Batch | Báo cáo theo dòng, tổng số thành công/thất bại | Tiếp tục với lỗi dữ liệu dự kiến; dừng hoặc retry khi lỗi hạ tầng ảnh hưởng toàn lô. |
| Message consumer | Retry, dead-letter hoặc đánh dấu xử lý | Không ack một message chưa xử lý thành công nếu chính sách yêu cầu retry. |

Ví dụ, batch nhập 1.000 đơn có thể tiếp tục khi một dòng có mã đơn sai định dạng và ghi lỗi vào báo cáo. Nhưng nếu database mất kết nối sau 10 dòng, tiếp tục lặp 990 dòng còn lại có thể chỉ tạo thêm lỗi. Adapter cần phân biệt lỗi dữ liệu từng dòng với lỗi hạ tầng làm mất khả năng xử lý toàn bộ lô.

Tầng ứng dụng có thể trả lỗi có ngữ nghĩa như `OrderAlreadyExists`; adapter CLI có thể hiển thị thông báo, HTTP có thể trả 409 và batch có thể ghi mã lỗi vào cột kết quả. Việc biểu diễn khác nhau không làm thay đổi ý nghĩa của lỗi trong hợp đồng ứng dụng.

## 12. Kiểm thử chính sách ánh xạ lỗi

Kiểm thử nên xác nhận cả nguyên nhân được giữ lại lẫn thông tin được công bố đúng mức:

| Phạm vi | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Unit test nghiệp vụ | Quy tắc ném đúng lỗi có ý nghĩa | Đơn không đủ điều kiện phát sinh `InsufficientStockException`. |
| Adapter persistence test | Chỉ constraint đã biết được chuyển thành lỗi nghiệp vụ | Unique violation trên `order_number` thành `OrderNumberAlreadyUsedException`; lỗi khác được giữ nguyên. |
| Cause-chain test | Exception mới giữ cause gốc | `assertThat(exception.getCause()).isInstanceOf(DataIntegrityViolationException.class)`. |
| Controller advice test | Mã HTTP và error code đúng | `OrderNotFoundException` thành 404 và `ORDER_NOT_FOUND`. |
| Security/error disclosure test | Response không lộ thông tin nội bộ | Body không chứa SQL, stack trace, hostname hoặc credential. |
| Transaction test | Lỗi dẫn đến commit/rollback đúng chính sách | Exception thoát khỏi transaction làm rollback; lỗi được xử lý có chủ đích không tạo trạng thái dở dang. |
| Retry test | Chỉ lỗi tạm thời được thử lại theo giới hạn | Timeout được retry có giới hạn; validation và lỗi nghiệp vụ không bị retry. |

Với Spring MVC, `MockMvc` có thể kiểm tra response từ `@RestControllerAdvice`. Với persistence adapter, integration test trên database phù hợp giúp xác nhận exception thực tế mà driver/ORM tạo ra. Với transaction, test cần quan sát trạng thái dữ liệu sau khi phương thức thất bại thay vì chỉ xác nhận exception đã được ném.

Đừng chỉ kiểm tra thông điệp lỗi. Error code thường là phần hợp đồng ổn định hơn và có thể được client dùng để quyết định hiển thị hoặc hành động. Thông điệp có thể được dịch, chỉnh sửa hoặc thay đổi cách diễn đạt mà không làm thay đổi mã lỗi.

## 13. Những cách xử lý lỗi cần tránh

- **Bắt `Exception` ở mọi tầng:** làm mất phân loại và khiến lỗi lập trình bị xem như lỗi dự kiến.
- **Nuốt lỗi và trả giá trị mặc định:** consumer không thể phân biệt thất bại với kết quả hợp lệ.
- **Bọc exception mà bỏ cause:** làm mất dấu vết nguyên nhân gốc.
- **Trả `exception.getMessage()` ra API:** có thể tiết lộ SQL, schema, đường dẫn, dữ liệu hoặc chi tiết nội bộ.
- **Ánh xạ theo tên lớp một cách máy móc:** cùng một exception Java có thể mang ý nghĩa khác nhau tùy ngữ cảnh.
- **Ghi log cùng stack trace ở mọi tầng:** tạo nhiễu và làm khó đếm sự cố.
- **Retry mọi lỗi:** làm tăng tải và lặp lại tác dụng phụ không an toàn.
- **Chuyển lỗi hạ tầng thành lỗi nghiệp vụ:** khiến hệ thống báo sai cho người dùng và che giấu sự cố vận hành.
- **Đưa HTTP status vào domain exception:** gắn mô hình nghiệp vụ với một adapter cụ thể.

## 14. Tự rà soát thiết kế

Khi review luồng xử lý lỗi, hãy tự hỏi:

1. Lỗi thuộc giao thức, đầu vào, nghiệp vụ, hạ tầng hay lỗi lập trình?
2. Tầng nào có đủ ngữ cảnh để phân loại và chuyển lỗi một cách chính xác?
3. Nếu bọc exception, cause gốc có được giữ lại không?
4. Exception được công bố có mang ngữ nghĩa ổn định hay phụ thuộc vào SQL/ORM/framework?
5. API có trả mã lỗi ổn định và thông tin an toàn không?
6. Log có correlation ID và đủ cause chain để điều tra mà không ghi dữ liệu nhạy cảm không?
7. Transaction có rollback đúng khi lỗi xảy ra hoặc bị bắt lại không?
8. Retry có giới hạn và chỉ áp dụng cho lỗi có thể phục hồi, thao tác an toàn khi lặp không?
9. Các adapter HTTP, CLI, job và batch có thể biểu diễn cùng lỗi ứng dụng theo cách phù hợp riêng không?

Nếu một tầng phải hiểu chi tiết exception của tầng thấp, hãy xem xét chuyển đổi tại adapter sở hữu chi tiết đó. Nếu response lộ stack trace hoặc thông báo SQL, hãy giới hạn thông tin ở lớp ánh xạ trình bày. Nếu lỗi bị biến thành thông báo chung không thể điều tra, hãy khôi phục cause chain và bổ sung ngữ cảnh có kiểm soát.

## Kết luận

Ánh xạ lỗi tốt bắt đầu từ việc phân loại đúng ý nghĩa và chuyển đổi tại ranh giới có đủ ngữ cảnh. Tầng nghiệp vụ diễn đạt quy tắc, adapter dữ liệu nhận diện lỗi lưu trữ, tầng ứng dụng điều phối hành vi và tầng trình bày chuyển lỗi thành hợp đồng giao thức. Khi cần bọc exception, hãy giữ cause; khi ghi log, giữ thông tin phục vụ điều tra nhưng tránh lặp stack trace và dữ liệu nhạy cảm; khi trả lỗi cho client, chỉ công bố error code và thông điệp được phép. Kết hợp chính sách transaction, retry và kiểm thử giúp lỗi được xử lý nhất quán mà nguyên nhân thực sự vẫn có thể truy vết.
