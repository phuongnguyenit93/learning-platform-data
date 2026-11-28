# Thiết kế ngoại lệ nghiệp vụ và chuyển đổi lỗi ở ranh giới hệ thống

## 1. Mục tiêu: lỗi rõ nghĩa, không rò rỉ chi tiết triển khai

Trong một ứng dụng Java 27, lỗi có thể đến từ nhiều nơi: người dùng nhập dữ liệu không hợp lệ, quy tắc nghiệp vụ từ chối một thao tác, cơ sở dữ liệu không phản hồi, hệ thống ngoài hết thời gian chờ hoặc mã nguồn vi phạm một bất biến. Những tình huống này **không nên được xử lý bằng cùng một thông điệp và cùng một chiến lược khôi phục**.

Thiết kế ngoại lệ tốt phải giải quyết ba vấn đề:

1. **Phân loại đúng lỗi:** một yêu cầu hợp lệ nhưng hết hàng khác với việc không thể kết nối kho dữ liệu.
2. **Bảo toàn ngữ cảnh để chẩn đoán:** giữ nguyên nguyên nhân kỹ thuật (*cause*), mã lỗi ổn định và thông tin tương quan cần thiết.
3. **Chuyển đổi đúng tại ranh giới:** tầng lưu trữ có thể biết **SQLException**, nhưng tầng nghiệp vụ chỉ cần biết kho dữ liệu đang không sẵn sàng; API HTTP trả mã trạng thái và thông điệp phù hợp mà không tiết lộ mật khẩu, câu SQL hoặc stack trace.

~~~mermaid
flowchart TD
    A["Client / HTTP request"] --> B["HTTP adapter: parse, authenticate, map errors"]
    B --> C["Application service / domain"]
    C --> D["Port / repository interface"]
    D --> E["Infrastructure adapter: JDBC, HTTP, filesystem"]
    E -->|"SQLException / IOException / timeout"| F["Translate to infrastructure exception"]
    F --> C
    C -->|"BusinessException or typed rejection"| B
    B -->|"HTTP status + public error code"| A
~~~

Điều cốt lõi là **dịch lỗi ở nơi biết đủ ý nghĩa của lỗi**, không quăng một ngoại lệ kỹ thuật xuyên suốt mọi tầng. Bài sử dụng API ngôn ngữ và thư viện chuẩn còn áp dụng trong Java 27; không dựa vào cơ chế cũ như **finalize()** hoặc yêu cầu runtime bật preview.

## 2. Phân loại lỗi theo nguyên nhân và khả năng phục hồi

Một cách phân loại thực dụng:

| Loại | Ví dụ | Bên nào cần xử lý? | Phản ứng thường gặp |
|---|---|---|---|
| **Đầu vào không hợp lệ** | Số lượng âm; trường bắt buộc trống | Ranh giới nhận dữ liệu hoặc ứng dụng | Từ chối có thông tin sửa đầu vào |
| **Từ chối theo nghiệp vụ** | Hết hàng, tài khoản không đủ số dư, trạng thái không cho hủy | Application/domain | Trả kết quả nghiệp vụ hoặc ngoại lệ có mã ổn định |
| **Không tìm thấy tài nguyên** | SKU không tồn tại theo kho dữ liệu hợp lệ | Application/domain | Trả Not Found nếu phù hợp ngữ cảnh |
| **Xung đột trạng thái** | Phiên bản cập nhật lạc hậu, giao dịch trùng định danh | Application/domain | Yêu cầu đọc lại/tranh chấp theo hợp đồng |
| **Hạ tầng tạm thời lỗi** | DB unavailable, network timeout | Adapter/infrastructure | Có thể retry khi thao tác an toàn, báo lỗi dịch vụ |
| **Hạ tầng không thể xử lý yêu cầu** | Cấu hình thiếu, schema không tương thích | Adapter/operations | Báo lỗi kỹ thuật, cần sửa hệ thống |
| **Lỗi lập trình/bất biến** | Null ngoài dự kiến, logic sai, trạng thái không thể xảy ra | Developer/operator | Log, cảnh báo và sửa bug; không giả thành lỗi người dùng |
| **Hủy/bị ngắt** | Thread được interrupt, request bị cancel | Điều phối/lifecycle | Dừng có kiểm soát, bảo toàn tín hiệu hủy |

Một lỗi nghiệp vụ **không đồng nghĩa** với lỗi HTTP 500, cũng không tự động được phép thử lại. Ví dụ, nếu đơn hàng không đủ tồn kho, thử lại ngay không giúp tăng tồn kho. Ngược lại, timeout từ dịch vụ khác có thể là tạm thời nhưng retry thiếu idempotency có thể tạo giao dịch trùng.

**Mã lỗi ổn định quan trọng hơn văn bản thông điệp.** Client có thể dùng mã **INSUFFICIENT_STOCK** để hiển thị giao diện phù hợp; câu chữ cho người dùng có thể thay đổi theo ngôn ngữ và sản phẩm.

## 3. Hệ phân cấp Throwable và lựa chọn checked/unchecked

Java tổ chức các đối tượng có thể ném qua **Throwable**:

~~~text
Throwable
├── Error
│   └── Các lỗi nghiêm trọng ở JVM/môi trường
└── Exception
    ├── IOException, SQLException, InterruptedException, ...
    └── RuntimeException
        ├── IllegalArgumentException
        ├── IllegalStateException
        └── Các ngoại lệ ứng dụng tự định nghĩa
~~~

Các quy tắc đáng nhớ:

- **Checked exception** là những Exception không thuộc RuntimeException; phương thức phải bắt hoặc khai báo **throws**. Ví dụ **IOException**, **SQLException**, **InterruptedException**.
- **Unchecked exception** là RuntimeException và Error; Java không bắt buộc khai báo chúng trong **throws**.
- **Error** thường biểu thị các vấn đề nghiêm trọng mà logic nghiệp vụ không được thiết kế để phục hồi. Không bắt **Throwable** hay **Error** chỉ để biến mọi sự cố thành phản hồi “thành công” hoặc 500.
- **throw** tạo luồng thoát bất thường; **throws** mô tả các checked exceptions mà phương thức có thể cho truyền ra.

Không có quy tắc tuyệt đối rằng “mọi ngoại lệ nghiệp vụ phải checked” hay “mọi ngoại lệ phải unchecked”. Chọn theo hợp đồng và kiến trúc:

| Khi nào | Lựa chọn thường phù hợp |
|---|---|
| Caller có trách nhiệm và khả năng xử lý một tình huống dự kiến | Typed result hoặc checked exception tùy API |
| Vi phạm bất biến/tiền điều kiện không được phép tiếp tục | RuntimeException có mã nghiệp vụ hoặc IllegalArgumentException |
| API I/O chuẩn đã khai báo checked exception | Tôn trọng hoặc dịch ở ranh giới phù hợp |
| Lỗi hạ tầng không muốn rò rỉ lên domain | Infrastructure-specific RuntimeException có **cause** |
| Lỗi JVM hoặc bug nghiêm trọng | Không che giấu; giám sát và sửa nguyên nhân |

**Exception không phải cơ chế thay thế cho mọi nhánh điều kiện.** Với các kết quả dự kiến xuất hiện thường xuyên, một kiểu kết quả rõ ràng có thể dễ sử dụng hơn.

## 4. Phân biệt từ chối nghiệp vụ với thất bại kỹ thuật

Giả sử nghiệp vụ kiểm tra số lượng hàng trước khi xác nhận đơn:

- **SKU không tồn tại:** một kết quả nghiệp vụ; có thể báo **ITEM_NOT_FOUND**.
- **SKU tồn tại nhưng không đủ số lượng:** một từ chối nghiệp vụ; có thể báo **INSUFFICIENT_STOCK**.
- **Cơ sở dữ liệu không truy cập được:** chưa biết còn hàng hay không; đây là lỗi hạ tầng, **không được đổi thành “hết hàng”**.
- **Mã nguồn đọc một giá trị null trái hợp đồng:** lỗi lập trình/bất biến; không đổi thành “đầu vào sai” nếu client đã gửi dữ liệu hợp lệ.

Điểm khác biệt then chốt: một kết quả nghiệp vụ có ý nghĩa **dữ liệu đã được đọc hoặc kiểm tra đáng tin cậy**. Khi nguồn dữ liệu không sẵn sàng, tầng nghiệp vụ không thể suy đoán trạng thái tài nguyên.

Một số hệ thống dùng exception cho từ chối nghiệp vụ, trong khi hệ thống khác dùng kiểu kết quả như **sealed interface**. Cả hai đều là lựa chọn hợp lệ nếu hợp đồng rõ ràng và các tầng xử lý nhất quán.

## 5. Mã lỗi nghiệp vụ ổn định và ngoại lệ chuyên biệt

Có thể tạo enum để định danh lỗi nghiệp vụ, kèm một loại RuntimeException chứa mã. Cú pháp dưới đây minh họa một thành phần có thể tách vào file riêng theo cấu trúc dự án:

~~~java
enum BusinessErrorCode {
    INVALID_QUANTITY,
    ITEM_NOT_FOUND,
    INSUFFICIENT_STOCK,
    ORDER_ALREADY_COMPLETED
}

final class BusinessException extends RuntimeException {
    private final BusinessErrorCode code;

    BusinessException(BusinessErrorCode code, String diagnosticMessage) {
        super(diagnosticMessage);
        this.code = java.util.Objects.requireNonNull(code, "code");
    }

    BusinessErrorCode code() {
        return code;
    }
}
~~~

Ứng dụng sử dụng:

~~~java
static void checkQuantity(int quantity) {
    if (quantity <= 0) {
        throw new BusinessException(
            BusinessErrorCode.INVALID_QUANTITY,
            "quantity must be positive"
        );
    }
}
~~~

**BusinessErrorCode** là giá trị để hệ thống dựa vào khi xử lý; **diagnosticMessage** là thông tin dành cho developer/operator. Không nên cho client phụ thuộc câu chữ của **getMessage()** và cũng không mặc định gửi trực tiếp thông điệp chẩn đoán ra bên ngoài.

Một thiết kế error code tốt nên:

1. Có tên ổn định và có nghĩa nghiệp vụ.
2. Không mã hóa chi tiết framework, driver hoặc ngôn ngữ hiển thị.
3. Có tài liệu về trường hợp phát sinh và cách xử lý.
4. Được gắn với chính sách retry, mức độ nghiêm trọng hoặc phản hồi giao thức tại tầng phù hợp.
5. Không dùng một mã mơ hồ như **UNKNOWN_ERROR** cho mọi sai phạm dự kiến.

Không cần tạo subclass Exception riêng cho **mọi** mã lỗi. Khi các lỗi có cùng quy tắc xử lý, một class với enum code thường đơn giản hơn. Tạo subclass khi hành vi bắt lỗi hoặc ngữ nghĩa thật sự khác nhau, chẳng hạn ngoại lệ hạ tầng có chính sách xử lý tách biệt.

## 6. Khi nào dùng kiểu kết quả thay vì ném exception?

Nếu “không được cấp tín dụng” là kết quả thường xuyên của phép đánh giá, kiểu trả về đóng có thể diễn đạt rõ hơn exception:

~~~java
sealed interface CreditDecision
        permits Approved, Rejected {
}

record Approved(String approvalId) implements CreditDecision {
}

record Rejected(String reasonCode) implements CreditDecision {
}

static CreditDecision evaluate(int score) {
    return score >= 650
        ? new Approved("approval-demo")
        : new Rejected("SCORE_TOO_LOW");
}

static String describe(CreditDecision decision) {
    return switch (decision) {
        case Approved(var id) -> "Approved: " + id;
        case Rejected(var code) -> "Rejected: " + code;
    };
}
~~~

Trong Java 27, sealed type, record, record pattern và pattern switch đều là tính năng đã được chuẩn hóa. Mẫu này giúp caller **bắt buộc xem xét các biến thể** khi biên dịch switch expression trên sealed hierarchy.

Một hướng chọn:

| Bối cảnh | Thiết kế đề xuất |
|---|---|
| Kết quả “được/không được” là thông thường, caller buộc xử lý | **Result/Decision type** |
| Tiền điều kiện bị vi phạm và không thể tiếp tục lời gọi | **BusinessException** có code |
| Thao tác I/O gặp sự cố | **IOException** hoặc exception adapter phù hợp |
| Client cần biết kết quả nào có thể retry | Mã và chính sách retry định nghĩa riêng, không chỉ suy từ loại exception |

Không dùng exception để điều khiển vòng lặp hoặc thay thế các nhánh **if** đơn giản trong đường xử lý thường xuyên. Exception vẫn là công cụ chính xác cho các trường hợp bất thường và cho việc truyền lỗi qua nhiều frame gọi hàm.

## 7. Xác thực dữ liệu ở đúng ranh giới

Nên kiểm tra các lỗi thuộc trách nhiệm của từng tầng:

- **Transport layer:** JSON hoặc payload có đúng định dạng không; các trường có kiểu phù hợp không; kích thước payload có vượt giới hạn không?
- **Application layer:** yêu cầu có đủ thông tin, định danh và tham số cần thiết không?
- **Domain layer:** yêu cầu có vi phạm các bất biến và trạng thái nghiệp vụ không?
- **Infrastructure layer:** kết nối, quyền truy cập hoặc dữ liệu lưu trữ có đáp ứng hợp đồng không?

Ví dụ record bảo vệ bất biến tại thời điểm khởi tạo:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record PurchaseCommand(String sku, int quantity, BigDecimal unitPrice) {
    PurchaseCommand {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku cannot be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }
    }
}
~~~

Ở ranh giới HTTP, có thể ánh xạ lỗi định dạng/validation phù hợp thành 400. Nhưng **không nên mặc định catch mọi IllegalArgumentException từ bất kỳ tầng nào rồi trả HTTP 400**: một IllegalArgumentException phát sinh trong thư viện nội bộ cũng có thể là bug.

Cách tiếp cận ổn định hơn là **chuyển lỗi validation bên ngoài thành mã API rõ ràng tại nơi parse/validate**, còn domain exception dùng mã nghiệp vụ riêng. Việc này giúp không biến sai sót lập trình thành lỗi của người dùng.

## 8. Port và adapter: dịch lỗi hạ tầng ở đâu?

Trong kiến trúc phân tầng/hexagonal, domain service có thể phụ thuộc vào một **port**:

~~~java
import java.util.Optional;

record Stock(String sku, int available) {}

interface StockRepository {
    Optional<Stock> findBySku(String sku);
}
~~~

Hợp đồng ở đây rõ ràng:

- **Optional.empty()**: truy vấn thành công nhưng SKU không có trong nguồn dữ liệu.
- **Optional.of(stock)**: truy vấn thành công và có dữ liệu.
- **InfrastructureException**: không thể hoàn thành truy vấn một cách đáng tin cậy vì hạ tầng lỗi.

Ví dụ exception cho adapter:

~~~java
final class InfrastructureException extends RuntimeException {
    private final String operation;

    InfrastructureException(
            String operation,
            String diagnosticMessage,
            Throwable cause) {
        super(diagnosticMessage, cause);
        this.operation =
            java.util.Objects.requireNonNull(operation, "operation");
    }

    String operation() {
        return operation;
    }
}
~~~

Không để tầng nghiệp vụ phụ thuộc trực tiếp vào **SQLException**, **SQLState**, tên table hoặc câu SQL nếu những chi tiết đó thuộc adapter. Domain service chỉ cần biết operation đã không thực hiện được. Những chi tiết kỹ thuật vẫn được giữ trong **cause** để phục vụ chẩn đoán.

## 9. Chuyển SQLException thành lỗi có ý nghĩa ở adapter JDBC

Một adapter JDBC có thể xử lý SQL exception ngay cạnh câu truy vấn:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

final class JdbcStockRepository implements StockRepository {
    private final DataSource dataSource;

    JdbcStockRepository(DataSource dataSource) {
        this.dataSource =
            java.util.Objects.requireNonNull(dataSource, "dataSource");
    }

    @Override
    public Optional<Stock> findBySku(String sku) {
        String sql =
            "SELECT sku, available FROM stock WHERE sku = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setString(1, sku);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Stock(
                    rows.getString("sku"),
                    rows.getInt("available")
                ));
            }

        } catch (SQLException cause) {
            throw new InfrastructureException(
                "stock.findBySku",
                "Stock lookup failed",
                cause
            );
        }
    }
}
~~~

**try-with-resources** đóng **ResultSet**, **PreparedStatement** và **Connection** theo thứ tự ngược lại, kể cả khi thao tác gặp lỗi. Các resource đã được khởi tạo sẽ được đóng và exception từ **close()** có thể xuất hiện dưới dạng suppressed exception.

Không nên bắt **SQLException** rồi trả **Optional.empty()**. Điều đó đánh đồng “không tìm thấy bản ghi” với “không truy vấn được”, làm hệ thống đưa ra quyết định nghiệp vụ sai.

Tùy hợp đồng adapter, có thể phân loại thêm SQLState, **SQLTransientException**, **SQLRecoverableException** hoặc lỗi ràng buộc duy nhất. Việc phân loại cần dựa trên driver, DB cụ thể và idempotency của thao tác; không phải mọi SQLException đều có thể retry.

## 10. Đừng dịch lỗi quá sớm hoặc quá nhiều lần

Lỗi kỹ thuật thường đi qua chuỗi:

~~~text
SQLException
  -> InfrastructureException(cause = SQLException)
  -> application service propagates
  -> HTTP adapter maps to 503
~~~

Đây là đường đi hợp lý vì mỗi tầng chỉ xử lý điều nó hiểu. Những cách tiếp cận nên tránh:

~~~java
// Sai: im lặng biến lỗi truy vấn thành dữ liệu rỗng.
// catch (SQLException ex) {
//     return Optional.empty();
// }

// Sai: làm mất nguyên nhân gốc.
// catch (SQLException ex) {
//     throw new RuntimeException("Database failed");
// }

// Sai: dịch mọi sự cố của tầng lưu trữ thành lỗi "không tìm thấy".
// catch (InfrastructureException ex) {
//     throw new BusinessException(ITEM_NOT_FOUND, "Not found");
// }
~~~

Nếu cần thêm ngữ cảnh khi dịch lỗi, tạo exception có **cause**:

~~~java
throw new InfrastructureException(
    "invoice.save",
    "Could not persist invoice",
    originalSQLException
);
~~~

**Nguyên tắc một tầng – một trách nhiệm:**

- Adapter lưu trữ hiểu lỗi SQL/network và dịch thành lỗi hạ tầng.
- Domain hiểu quy tắc từ chối nghiệp vụ và phát ra mã tương ứng.
- Transport boundary hiểu HTTP/JSON/gRPC và quyết định status hoặc error envelope.
- Logging/observability giữ cause chain, trace ID và metadata an toàn.

Không bắt rồi ném lại thành một RuntimeException chung ở mọi tầng, vì việc đó tạo tầng bọc vô ích và làm mờ ý nghĩa lỗi.

## 11. Ánh xạ lỗi sang HTTP ở ranh giới ngoài

Domain không nên biết **HTTP 404, 409, 422 hay 503**. Việc ánh xạ thuộc HTTP adapter/controller. Một bảng định hướng có thể dùng:

| Tình huống | Mã nghiệp vụ/kỹ thuật | HTTP thường phù hợp |
|---|---|---|
| Body JSON không thể parse hoặc thiếu field bắt buộc theo hợp đồng | INVALID_REQUEST | 400 Bad Request |
| Tài nguyên không tồn tại và caller được phép biết điều đó | ITEM_NOT_FOUND | 404 Not Found |
| Dữ liệu hợp lệ về cú pháp nhưng vi phạm một quy tắc miền | BUSINESS_RULE_VIOLATION | 422 Unprocessable Content hoặc 409 nếu xung đột trạng thái |
| Phiên bản object đã cũ, thao tác xung đột trạng thái hiện tại | VERSION_CONFLICT | 409 Conflict |
| Tài nguyên hạ tầng tạm không khả dụng | DEPENDENCY_UNAVAILABLE | 503 Service Unavailable |
| Hệ thống gặp lỗi lập trình không dự kiến | INTERNAL_ERROR | 500 Internal Server Error |
| Caller vượt giới hạn yêu cầu | RATE_LIMITED | 429 Too Many Requests |

Đây là ví dụ chính sách, **không phải luật ánh xạ cố định**. HTTP status còn phụ thuộc ngữ nghĩa endpoint, bảo mật, mô hình phân quyền, hợp đồng API và các yêu cầu của hệ thống ngoài. Ví dụ, trong một số trường hợp bảo mật, việc không cho biết tài nguyên tồn tại có thể làm 404 phù hợp hơn 403. Các mã xác thực/phân quyền nên do lớp security chuyên trách quyết định.

Ví dụ về cấu trúc response độc lập framework:

~~~java
record PublicError(String code, String message, String requestId) {}

record HttpFailure(int status, PublicError body) {}
~~~

Những trường tối thiểu nên ổn định: **code** để máy xử lý, **message** an toàn để hiển thị, **requestId** hoặc trace ID để hỗ trợ truy vết. Với HTTP API, có thể dùng dạng Problem Details theo chuẩn được hệ thống lựa chọn; không cần ép domain exception mang cấu trúc JSON.

## 12. Thông điệp công khai khác thông tin chẩn đoán

Một ngoại lệ kỹ thuật có thể chứa chi tiết nhạy cảm:

~~~text
Connection to jdbc:postgresql://internal-db:5432/orders failed
SQL: SELECT ... WHERE email = ...
Caused by: authentication/connection configuration
~~~

**Không trả** trực tiếp **exception.getMessage()**, stack trace, câu SQL, connection string hoặc thông tin token cho client. Tại HTTP boundary, dùng mã và thông điệp được định nghĩa sẵn:

~~~java
static String publicMessage(BusinessErrorCode code) {
    return switch (code) {
        case INVALID_QUANTITY -> "Số lượng phải lớn hơn 0";
        case ITEM_NOT_FOUND -> "Không tìm thấy sản phẩm";
        case INSUFFICIENT_STOCK -> "Không đủ hàng tồn";
        case ORDER_ALREADY_COMPLETED ->
            "Đơn hàng đã hoàn tất, không thể thay đổi";
    };
}
~~~

Message dành cho client có thể cần localization, nhưng **error code nên ổn định** giữa các ngôn ngữ. Không dùng thông điệp chẩn đoán như một định danh để điều khiển chương trình: so sánh theo chuỗi dễ hỏng khi thay đổi câu chữ.

Khi log exception ở phía server, cũng cần xem xét dữ liệu cá nhân, nội dung request, khóa bí mật và thông tin tài khoản. Việc giữ cause chain giúp chẩn đoán, nhưng không có nghĩa mọi chi tiết đều được phép ghi vào mọi hệ thống log.

## 13. Giữ cause chain khi chuyển đổi lỗi

Khi một exception được tạo để cung cấp ngữ nghĩa mới cho tầng gọi, nên giữ exception gốc ở trường **cause**.

~~~java
import java.io.IOException;

static String loadConfiguration(java.nio.file.Path file) {
    try {
        return java.nio.file.Files.readString(file);
    } catch (IOException cause) {
        throw new InfrastructureException(
            "configuration.load",
            "Could not read configuration file",
            cause
        );
    }
}
~~~

Ở tầng ngoài có thể kiểm tra:

~~~java
try {
    loadConfiguration(java.nio.file.Path.of("app.conf"));
} catch (InfrastructureException failure) {
    System.err.println(failure.operation());
    System.err.println(failure.getCause().getClass().getSimpleName());
}
~~~

Lợi ích của cause chain:

- Vẫn biết lỗi bắt đầu từ I/O, JDBC hay thư viện khác.
- Không làm mất stack trace tại nơi phát sinh sự cố.
- Cho phép observability liên kết exception cấp ứng dụng với nguyên nhân sâu hơn.

Không nên dùng **getCause()** để quyết định nghiệp vụ dựa vào chuỗi message của exception sâu bên trong. Nếu caller cần biết lỗi tạm thời hay vĩnh viễn, hãy cung cấp metadata đã phân loại ở adapter, ví dụ một code/chính sách retry, thay vì yêu cầu domain hiểu exception của JDBC.

## 14. Try-with-resources và vòng đời tài nguyên

Ngoại lệ thường xuất hiện đúng lúc tài nguyên cần được đóng: stream, reader, file channel, JDBC connection, statement hoặc result set. Java cung cấp **try-with-resources** cho đối tượng triển khai **AutoCloseable**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static String firstLine(Path file) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
~~~

Trình biên dịch bảo đảm logic đóng tài nguyên tương ứng với scope try-with-resources, kể cả khi thân khối ném ngoại lệ hoặc return. Không cần viết một khối **finally** thủ công cho việc đóng tài nguyên thông thường.

Khi dùng nhiều resource:

~~~java
try (var input = Files.newInputStream(source);
     var output = Files.newOutputStream(target)) {
    input.transferTo(output);
}
~~~

Các resource được đóng theo **thứ tự ngược với thứ tự khai báo**. Chỉ những resource đã khởi tạo thành công mới được đóng. Điều này quan trọng nếu thao tác mở resource thứ hai bị lỗi: resource đầu tiên vẫn phải được giải phóng.

Nên chọn resource owner rõ ràng. Ví dụ, một phương thức tạo InputStream và chuyển quyền sở hữu cho caller cần tài liệu về việc ai phải đóng; không được đóng stream trước khi caller có cơ hội đọc.

## 15. Suppressed exception: lỗi close không che lỗi chính

Khi thân try và **close()** cùng ném exception, Java giữ exception từ thân try làm lỗi chính và gắn exception phát sinh trong close vào danh sách **suppressed exceptions**.

Ví dụ độc lập:

~~~java
final class FailingResource implements AutoCloseable {
    @Override
    public void close() {
        throw new IllegalStateException("close failed");
    }
}

static void demonstrateSuppressed() {
    try (FailingResource ignored = new FailingResource()) {
        throw new IllegalStateException("processing failed");
    }
}
~~~

Kiểm tra kết quả:

~~~java
try {
    demonstrateSuppressed();
} catch (IllegalStateException failure) {
    System.out.println(failure.getMessage()); // processing failed

    for (Throwable suppressed : failure.getSuppressed()) {
        System.out.println(suppressed.getMessage()); // close failed
    }
}
~~~

Không được nhầm **cause** và **suppressed**:

- **Cause:** nguyên nhân kỹ thuật được gắn khi dịch một lỗi thành exception khác.
- **Suppressed:** lỗi phát sinh trong lúc dọn dẹp tài nguyên hoặc được chủ động gắn để bảo toàn lỗi phụ.

Các hệ thống logging tốt thường hiển thị cả cause và suppressed exceptions, hỗ trợ điều tra lỗi xử lý lẫn lỗi dọn dẹp. Tránh viết khối finally mà lệnh throw trong finally **che mất exception chính**.

## 16. Tại sao không return hoặc throw tùy tiện trong finally?

Java cho phép **finally** chạy khi thoát khỏi try trong các điều kiện bình thường, nhưng một **return** hoặc **throw** trong finally có thể thay thế kết quả/ngoại lệ đang được truyền đi:

~~~java
// Không dùng:
static int misleading() {
    try {
        throw new IllegalStateException("primary failure");
    } finally {
        return 42; // Che giấu lỗi ở try!
    }
}
~~~

Ví dụ trên minh họa anti-pattern, không phải cách xử lý tài nguyên nên áp dụng. Với tài nguyên triển khai AutoCloseable, dùng try-with-resources thay vì thủ công hóa việc đóng và làm phức tạp luồng ngoại lệ.

**Không nuốt ngoại lệ** bằng catch rỗng:

~~~java
// Không dùng:
// catch (Exception ignored) {}
~~~

Nếu một lỗi thật sự được phép bỏ qua, hãy ghi rõ nguyên nhân trong code, giới hạn phạm vi catch ở đúng loại exception dự kiến, và quyết định có cần metric hoặc thông tin quan sát hay không. Với lỗi hạ tầng không dự kiến, việc “tiếp tục như không có gì xảy ra” thường tạo dữ liệu không nhất quán.

## 17. Xử lý InterruptedException và tín hiệu hủy

**InterruptedException** không chỉ là lỗi I/O thông thường: nó thể hiện thread đang được yêu cầu ngắt trong lúc chờ. Khi catch InterruptedException nhưng không truyền tiếp dạng checked, nên **khôi phục interrupted status** để tầng điều phối có thể nhận biết yêu cầu hủy:

~~~java
static void awaitBriefly() {
    try {
        Thread.sleep(200);
    } catch (InterruptedException cause) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
            "Operation interrupted", cause
        );
    }
}
~~~

Nếu phương thức có thể khai báo **throws InterruptedException** và caller có trách nhiệm xử lý, thường tốt hơn là cho exception truyền ra. Khi đã catch và quyết định chuyển thành unchecked, phải cân nhắc bảo toàn tín hiệu interrupt.

**Không làm những việc sau:**

- Catch InterruptedException rồi bỏ qua và tiếp tục công việc dài.
- Retry vô hạn mà không xét thread đã bị hủy.
- Đổi mọi interruption thành “dịch vụ tạm lỗi, hãy thử lại” vì điều đó có thể chống lại yêu cầu cancel của caller.

**CancellationException** thường là tín hiệu hủy của một task/future, cần xử lý khác với “không đủ hàng”. Hệ thống cần xác định rõ người khởi xướng hủy và trạng thái đã được ghi nhận tới đâu.

## 18. Lỗi bất đồng bộ và CompletableFuture

Khi xử lý bất đồng bộ qua **CompletableFuture**, exception có thể được bọc trong **CompletionException** hoặc **ExecutionException** tùy cách lấy kết quả.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

CompletableFuture<String> work =
    CompletableFuture.supplyAsync(() -> {
        throw new IllegalStateException("Remote call failed");
    });

try {
    work.join();
} catch (CompletionException failure) {
    Throwable cause = failure.getCause();
    System.out.println(cause.getClass().getSimpleName());
}
~~~

- **join()** có thể ném CompletionException khi tác vụ thất bại, hoặc CancellationException khi bị hủy.
- **get()** theo hợp đồng Future có thể ném **ExecutionException** và **InterruptedException** (cùng một số loại lỗi khác).
- Callback **exceptionally(...)** hoặc **handle(...)** có thể biến lỗi thành giá trị thành công; chỉ làm vậy khi thực sự có một fallback đúng ngữ nghĩa.

Ví dụ fallback nguy hiểm:

~~~java
// Không dùng nếu dữ liệu rỗng có nghĩa "không có sản phẩm":
// return remoteStockFuture.exceptionally(error -> List.of());
~~~

Một request DB thất bại mà bị chuyển thành danh sách trống có thể khiến service báo “không có sản phẩm” sai. Nếu fallback được phép, nên biểu diễn nó bằng dữ liệu chất lượng dịch vụ rõ ràng, chẳng hạn **stale cache result** có metadata, hoặc exception để tầng trên quyết định.

Khi unwrap lỗi bất đồng bộ, đừng bỏ toàn bộ ngữ cảnh hoặc giả định **getCause()** luôn khác null. Phân loại tại ranh giới đã biết ngữ nghĩa, và giữ nguyên nguyên nhân gốc cho logging/diagnostics.

## 19. Retry, timeout và idempotency không đi kèm miễn phí

Ngoại lệ hạ tầng có thể được đánh dấu *có khả năng retry*, nhưng **retry chỉ an toàn nếu thao tác chịu được việc thực hiện lặp lại**.

Ví dụ:

- **GET** một thông tin không có tác dụng phụ có thể phù hợp để thử lại với timeout/budget được kiểm soát.
- **Gửi email** có thể gửi hai lần khi request đầu đã thành công nhưng response bị mất.
- **Ghi nhận thanh toán** có thể nhân đôi giao dịch nếu không có idempotency key hoặc hợp đồng chống trùng.
- **Trừ tồn kho** phải giữ nhất quán ngay cả khi client retry sau timeout.

Quy tắc xử lý:

1. Phân loại lỗi có thể phục hồi hay lỗi vĩnh viễn dựa trên ngữ nghĩa adapter.
2. Đặt số lần thử tối đa, timeout tổng và **backoff** hợp lý; cân nhắc jitter khi nhiều client retry đồng thời.
3. Kiểm tra idempotency và trạng thái giao dịch trước khi tự động lặp lại thao tác ghi.
4. Tôn trọng cancellation/interruption và ngân sách thời gian của request.
5. Nếu gặp lỗi nghiệp vụ dự kiến như **INSUFFICIENT_STOCK**, thường không retry máy móc.
6. Ghi nhận metric retry/failure nhưng tránh tạo log trùng vô hạn.

Không phải mọi **SQLTransientException** đều cho phép retry mọi thao tác, và **SQLException** tổng quát cũng không mang đủ thông tin về kết quả của một giao dịch đã gửi đến DB.

## 20. Transaction và trạng thái đã thay đổi một phần

Một chuỗi thao tác có tác dụng phụ có thể thất bại ở bước giữa:

~~~text
Validate order
    ↓
Reserve stock        (đã thành công)
    ↓
Charge payment       (timeout)
    ↓
Send notification    (chưa chạy)
~~~

Việc bọc toàn bộ chuỗi trong **try/catch** không tự tạo transaction trên nhiều hệ thống. Lỗi timeout khi thanh toán cũng **không chứng minh thanh toán chưa xảy ra**: response có thể bị mất sau khi phía nhận đã xử lý.

Với quy trình cần nhất quán:

- Trong một DB, dùng transaction theo khả năng của datasource và chính sách rollback phù hợp.
- Giữa nhiều dịch vụ, thiết kế **idempotency**, **outbox**, trạng thái workflow hoặc cơ chế bù trừ (*compensation*) nếu cần.
- Xác định chính xác bước nào có thể retry và bước nào phải đọc lại trạng thái.
- Không báo thành công nếu chưa xác nhận các bảo đảm nghiệp vụ cần thiết.
- Không để exception translation làm mất metadata cần thiết cho việc phục hồi.

Một **BusinessException** ném sau khi đã ghi dữ liệu không tự hoàn tác việc ghi. Transaction và resource lifecycle phải được thiết kế độc lập với câu lệnh throw.

## 21. Logging, tracing và cảnh báo lỗi đúng mức

Một chính sách quan sát lỗi hợp lý:

| Nơi | Nên làm gì? | Nên tránh gì? |
|---|---|---|
| **Repository adapter** | Thêm tên operation và cause khi dịch exception | Log full stack rồi ném lại ở mọi lần gọi |
| **Domain service** | Ném business code rõ nghĩa, giữ bất biến | Log lỗi nghiệp vụ thông thường như sự cố hạ tầng nghiêm trọng |
| **HTTP boundary** | Ánh xạ HTTP status, log exception bất ngờ một lần, gắn request ID | Trả stack trace/SQL tới client |
| **Observability** | Đo số lỗi theo code/status/operation và tỷ lệ retry | Dùng email, token hoặc payload raw làm label metric |
| **Operations** | Cảnh báo theo SLO/tỷ lệ lỗi và mức ảnh hưởng | Alert theo từng ngoại lệ validation hợp lệ |

**“Log once at the boundary”** là một hướng dẫn thường hữu ích, không phải quy tắc cứng cho mọi kiến trúc: adapter có thể ghi một sự kiện kỹ thuật có giá trị riêng, nhưng nên tránh nhân đôi cùng stack trace ở mọi tầng. Khi có structured logging, dùng các trường như **errorCode**, **operation**, **requestId** và mã trạng thái; không chỉ dựa vào message.

Luôn phân biệt **message công khai cho client** và **thông tin vận hành nội bộ**, cũng như chính sách lưu giữ và che dữ liệu nhạy cảm.

## 22. Ví dụ chạy độc lập: business error và HTTP boundary

Ví dụ sau dùng hoàn toàn Java chuẩn, không phụ thuộc framework. Nó mô phỏng ứng dụng kiểm tra tồn kho; trong hệ thống thật, port sẽ được triển khai bởi adapter JDBC/HTTP thay vì Map trong bộ nhớ.

Lưu tệp **BusinessErrorBoundaryDemo.java**:

~~~java
import java.io.IOException;
import java.util.Map;
import java.util.Objects;

public class BusinessErrorBoundaryDemo {
    enum Code {
        INVALID_REQUEST,
        ITEM_NOT_FOUND,
        INSUFFICIENT_STOCK
    }

    static final class BusinessException extends RuntimeException {
        private final Code code;

        BusinessException(Code code, String diagnosticMessage) {
            super(diagnosticMessage);
            this.code = Objects.requireNonNull(code);
        }

        Code code() {
            return code;
        }
    }

    static final class StorageFailure extends RuntimeException {
        StorageFailure(String operation, Throwable cause) {
            super("Storage operation failed: " + operation, cause);
        }
    }

    record CheckStock(String sku, int quantity) {}
    record Availability(String sku, int available) {}

    record ApiReply(int status, String code, String message) {}

    interface StockPort {
        Availability find(String sku);
    }

    static final class InMemoryStockPort implements StockPort {
        private final Map<String, Integer> stock =
            Map.of("PEN", 5, "BOOK", 2);

        @Override
        public Availability find(String sku) {
            if ("DOWN".equals(sku)) {
                throw new StorageFailure(
                    "stock.find",
                    new IOException("simulated connection failure")
                );
            }

            Integer quantity = stock.get(sku);
            return quantity == null
                ? null
                : new Availability(sku, quantity);
        }
    }

    static final class StockService {
        private final StockPort stockPort;

        StockService(StockPort stockPort) {
            this.stockPort = Objects.requireNonNull(stockPort);
        }

        String check(CheckStock request) {
            if (request == null
                    || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() <= 0) {
                throw new BusinessException(
                    Code.INVALID_REQUEST,
                    "Invalid request parameters"
                );
            }

            Availability current = stockPort.find(request.sku());

            if (current == null) {
                throw new BusinessException(
                    Code.ITEM_NOT_FOUND,
                    "Unknown SKU: " + request.sku()
                );
            }

            if (current.available() < request.quantity()) {
                throw new BusinessException(
                    Code.INSUFFICIENT_STOCK,
                    "Available=" + current.available()
                );
            }

            return "Available: " + request.sku();
        }
    }

    static ApiReply handle(CheckStock request, StockService service) {
        try {
            return new ApiReply(200, "OK", service.check(request));

        } catch (BusinessException failure) {
            return switch (failure.code()) {
                case INVALID_REQUEST ->
                    new ApiReply(400, "INVALID_REQUEST",
                        "Thông tin yêu cầu không hợp lệ");
                case ITEM_NOT_FOUND ->
                    new ApiReply(404, "ITEM_NOT_FOUND",
                        "Không tìm thấy sản phẩm");
                case INSUFFICIENT_STOCK ->
                    new ApiReply(409, "INSUFFICIENT_STOCK",
                        "Không đủ hàng tồn");
            };

        } catch (StorageFailure failure) {
            // Trong ứng dụng thật: log nội bộ với cause, requestId,
            // operation; không tiết lộ IOException cho client.
            return new ApiReply(503, "DEPENDENCY_UNAVAILABLE",
                "Dịch vụ tạm thời không sẵn sàng");

        } catch (RuntimeException unexpected) {
            // Ranh giới ngoài cùng: ghi nhận sự cố bất ngờ để điều tra.
            return new ApiReply(500, "INTERNAL_ERROR",
                "Hệ thống đang gặp sự cố");
        }
    }

    public static void main(String[] args) {
        StockService service = new StockService(new InMemoryStockPort());

        System.out.println(handle(new CheckStock("PEN", 2), service));
        System.out.println(handle(new CheckStock("PEN", 99), service));
        System.out.println(handle(new CheckStock("UNKNOWN", 1), service));
        System.out.println(handle(new CheckStock("PEN", 0), service));
        System.out.println(handle(new CheckStock("DOWN", 1), service));
    }
}
~~~

Biên dịch và chạy với JDK 27:

~~~bash
javac -encoding UTF-8 BusinessErrorBoundaryDemo.java
java BusinessErrorBoundaryDemo
~~~

Kết quả dự kiến:

~~~text
ApiReply[status=200, code=OK, message=Available: PEN]
ApiReply[status=409, code=INSUFFICIENT_STOCK, message=Không đủ hàng tồn]
ApiReply[status=404, code=ITEM_NOT_FOUND, message=Không tìm thấy sản phẩm]
ApiReply[status=400, code=INVALID_REQUEST, message=Thông tin yêu cầu không hợp lệ]
ApiReply[status=503, code=DEPENDENCY_UNAVAILABLE, message=Dịch vụ tạm thời không sẵn sàng]
~~~

Điểm quan trọng:

- **StockService** phân biệt không tìm thấy với không đủ hàng.
- **StorageFailure** có **cause** là IOException mô phỏng, nhưng tầng ngoài chỉ trả thông điệp an toàn.
- **handle** dịch ngoại lệ thành trạng thái HTTP tại ranh giới, giữ domain không phụ thuộc HTTP.
- **catch RuntimeException** cuối cùng là cơ chế báo lỗi ngoài dự kiến, không thay thế logging/monitoring thực tế.
- Demo chỉ **kiểm tra khả năng cung cấp** chứ không đặt giữ hàng: đọc tồn kho và xác nhận/đặt hàng là hai nghiệp vụ khác nhau, cần transaction hoặc cơ chế concurrency thích hợp khi thực hiện thật.

Trong code production, phần StockPort thường nên trả **Optional<Availability>** thay vì null để biểu đạt “không tìm thấy”. Ví dụ sử dụng null trong adapter giả lập để giữ mã demo ngắn; không nên áp dụng cách đó như hợp đồng repository chuẩn.

## 23. Kiểm thử contract và error mapping

Không chỉ kiểm thử đường thành công. Một bộ test có giá trị cần kiểm tra **mã lỗi, status, thông điệp công khai và việc không làm mất cause**.

Ví dụ kiểm tra logic demo bằng assert tường minh:

~~~java
static void verifyBoundary() {
    var service = new BusinessErrorBoundaryDemo.StockService(
        new BusinessErrorBoundaryDemo.InMemoryStockPort()
    );

    var insufficient = BusinessErrorBoundaryDemo.handle(
        new BusinessErrorBoundaryDemo.CheckStock("PEN", 50),
        service
    );

    if (insufficient.status() != 409
            || !"INSUFFICIENT_STOCK".equals(insufficient.code())) {
        throw new AssertionError("Expected stock conflict");
    }

    var unavailable = BusinessErrorBoundaryDemo.handle(
        new BusinessErrorBoundaryDemo.CheckStock("DOWN", 1),
        service
    );

    if (unavailable.status() != 503
            || unavailable.message().contains("connection")) {
        throw new AssertionError("Unexpected infrastructure response");
    }
}
~~~

Ví dụ trên minh họa phương pháp, có thể đặt thành phương thức test trong cùng lớp hoặc chuyển thành unit test thuộc test suite của dự án. Kiểm thử thực tế nên bổ sung:

1. Giá trị null, chuỗi rỗng, số lượng âm hoặc bằng 0.
2. SKU không tồn tại so với adapter không truy cập được.
3. Dữ liệu hợp lệ nhưng vi phạm quy tắc nghiệp vụ.
4. Exception kỹ thuật có **cause** và **suppressed** nếu có lỗi close.
5. Không lộ thông tin kết nối, token, câu SQL hoặc stack trace trong response.
6. Chính sách retry/cancellation theo đúng hợp đồng.
7. Nhiều request đồng thời nếu nghiệp vụ làm thay đổi dữ liệu chia sẻ.
8. Không log trùng vô hạn hoặc tạo metric nhãn có độ đa dạng không kiểm soát.

Với repository thực, nên có *contract tests* cho port: **Optional.empty()** chỉ có nghĩa không tìm thấy, còn lỗi kết nối phải thành lỗi hạ tầng. Điều này giúp ngăn việc một adapter mới vô tình “nuốt” các lỗi JDBC thành dữ liệu giả.

## 24. Những anti-pattern thường gặp

| Anti-pattern | Tác hại | Cách thay thế |
|---|---|---|
| **catch (Exception e) { return null; }** | Che giấu lỗi, tạo NPE xa nguyên nhân gốc | Chỉ bắt lỗi dự kiến và biểu diễn kết quả rõ nghĩa |
| Bắt SQLException rồi ném BusinessException ITEM_NOT_FOUND | Nhầm “không tìm được” với “không đọc được” | Dịch thành infrastructure error có cause |
| Ném RuntimeException không giữ cause | Mất nguồn gốc lỗi, khó điều tra | Dùng constructor nhận cause |
| Trả exception.getMessage() ra HTTP | Rò rỉ SQL, file path, token, thông tin nội bộ | Public error code và thông điệp được kiểm soát |
| Catch mọi IllegalArgumentException thành HTTP 400 | Che lỗi lập trình thành lỗi client | Validation tại ranh giới, mã lỗi chuyên biệt |
| Catch Throwable hoặc Error để tiếp tục | Che lỗi nghiêm trọng ngoài phạm vi phục hồi | Chỉ xử lý những loại lỗi hệ thống đã định nghĩa |
| Log full stack ở mọi tầng | Trùng dữ liệu, tăng chi phí, khó truy vết | Có chiến lược log rõ ràng tại ranh giới phù hợp |
| return/throw trong finally | Che exception trước đó | Dùng try-with-resources |
| Bỏ qua suppressed exceptions | Mất lỗi đóng tài nguyên | Bảo toàn stack/cause/suppressed ở logging |
| Bỏ qua InterruptedException | Vô hiệu yêu cầu hủy | Truyền tiếp hoặc khôi phục interrupt status |
| Retry mọi timeout của thao tác ghi | Có thể gây giao dịch trùng | Idempotency key, trạng thái workflow và retry budget |
| Dùng một exception cho mọi nhánh nghiệp vụ | Client không phân biệt cách phục hồi | Error code ổn định hoặc typed result |
| Đổi lỗi dịch vụ ngoài thành danh sách trống | Tạo kết quả sai nhưng có vẻ hợp lệ | Dùng failure result/fallback có metadata rõ |
| Để domain ném HTTP-specific exception | Domain phụ thuộc transport | Map status ở HTTP adapter |

## 25. Checklist khi thiết kế lỗi cho dịch vụ Java 27

- [ ] Phân biệt lỗi validation, từ chối nghiệp vụ, thiếu dữ liệu, xung đột, hạ tầng và bug.
- [ ] Có mã lỗi ổn định cho các trường hợp client cần xử lý.
- [ ] Cân nhắc typed result khi từ chối là một kết quả nghiệp vụ bình thường.
- [ ] Không dùng exception message làm hợp đồng máy đọc.
- [ ] Lỗi hạ tầng được dịch ở adapter có đủ ngữ cảnh kỹ thuật.
- [ ] Giữ nguyên cause khi bọc exception và không vô tình đánh rơi suppressed exceptions.
- [ ] Không trả dữ liệu nhạy cảm hoặc stack trace trong HTTP response.
- [ ] Không catch quá rộng ở mọi tầng; chỉ map lỗi dự kiến và có fallback tại ranh giới ngoài cùng.
- [ ] Sử dụng try-with-resources cho AutoCloseable, xác định ownership và thứ tự đóng.
- [ ] Không dùng return/throw trong finally làm mất exception trước đó.
- [ ] Tôn trọng InterruptedException và yêu cầu hủy.
- [ ] Retry được giới hạn và chỉ áp dụng khi có ngữ nghĩa idempotent/an toàn.
- [ ] Phân biệt timeout với kết luận chắc chắn rằng thao tác chưa xảy ra.
- [ ] Có chiến lược giao dịch và bù trừ cho các thao tác có tác dụng phụ nhiều bước.
- [ ] Log/metric/tracing đủ ngữ cảnh mà không nhân đôi sự kiện hoặc lộ dữ liệu nhạy cảm.
- [ ] Kiểm thử contract ở ranh giới lưu trữ, application và transport.
- [ ] Không xem HTTP 400/404/409/422/503 là phép ánh xạ tự động cho mọi domain.
- [ ] Giữ quy tắc lỗi nhất quán giữa triển khai thật, giả lập và test doubles.

**Kết luận:** Thiết kế ngoại lệ trong Java 27 không chỉ là chọn checked hay unchecked exception. Trọng tâm là **ngữ nghĩa lỗi, quyền sở hữu trách nhiệm và ranh giới chuyển đổi**. Domain phải diễn đạt đúng lý do từ chối; adapter giữ thông tin lỗi kỹ thuật nhưng không để lộ chi tiết triển khai; transport chuyển thành phản hồi rõ ràng và an toàn. Kết hợp với try-with-resources, cause chain, suppressed exceptions, cancellation và chính sách retry/idempotency, một hệ thống có thể thất bại theo cách dễ hiểu, dễ chẩn đoán và đáng tin cậy.

## Tài liệu tham khảo

- [Java Language Specification 27 — Chapter 11: Exceptions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-11.html): phân loại ngoại lệ, checked/unchecked, exception handling.
- [Java SE 27 — Throwable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Throwable.html): cause, suppressed exceptions, stack trace.
- [Java SE 27 — AutoCloseable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng tài nguyên và close().
- [Java SE 27 — SQLException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLException.html): mã SQLState, chuỗi nguyên nhân của lỗi JDBC.
- [Java SE 27 — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html): exceptional completion và xử lý lỗi bất đồng bộ.
- [Java SE 27 — InterruptedException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/InterruptedException.html): interruption và vòng đời tác vụ.
- [Java SE 27 — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): I/O API và sử dụng try-with-resources.
