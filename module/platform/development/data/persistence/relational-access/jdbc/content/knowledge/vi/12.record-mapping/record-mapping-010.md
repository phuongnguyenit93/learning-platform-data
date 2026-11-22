# Thiết kế lỗi ánh xạ có đủ thông tin mà không lộ dữ liệu nhạy cảm

Trong JDBC, ánh xạ bản ghi là quá trình chuyển một dòng `ResultSet` thành đối tượng Java, chẳng hạn một DTO, domain object hoặc Java `record`. Quá trình này có thể thất bại vì dữ liệu `NULL`, cột bị đổi tên, kiểu SQL không tương thích, giá trị vượt phạm vi hoặc mã trạng thái không còn nằm trong tập giá trị ứng dụng hiểu được.

Một thông báo như `Mapping failed` giúp tránh lộ dữ liệu nhưng khó truy tìm nguyên nhân. Ngược lại, ghi toàn bộ dòng dữ liệu, tham số SQL hoặc thông điệp của driver vào log có thể làm lộ thông tin khách hàng, mã truy cập và dữ liệu nghiệp vụ. Thiết kế tốt cần đáp ứng **cả hai yêu cầu**: chỉ rõ *bước ánh xạ nào thất bại* và *không đưa giá trị dữ liệu nguồn vào kênh chẩn đoán*.

Trong module **JDBC**, chủ đề này liên quan trực tiếp đến `PreparedStatement`, `ResultSet`, `DataSource`, SQL tham số hóa, CRUD và cách tổ chức lỗi ở tầng truy cập dữ liệu. Mục tiêu bài học:

- Nhận diện các lỗi ánh xạ thường gặp và phân biệt chúng với lỗi thực thi SQL.
- Thiết kế một cấu trúc lỗi có mã ổn định, định danh truy vấn, vị trí dòng và tên trường cho phép ghi log.
- Xây dựng mapper sử dụng `ResultSet` với chính sách xử lý `NULL`, giá trị không hợp lệ và `SQLException`.
- Ghi log và trả lỗi qua API mà không đưa dữ liệu cá nhân, nội dung SQL hay thông điệp ngoại lệ chưa được kiểm soát ra ngoài.
- Kiểm thử tính hữu ích của lỗi và việc không rò rỉ dữ liệu nhạy cảm.

## 1. Vì sao ánh xạ bản ghi cần mô hình lỗi riêng?

Một phép đọc JDBC thường có các bước:

~~~mermaid
flowchart LR
    A["DataSource / Connection"] --> B["PreparedStatement"]
    B --> C["ResultSet"]
    C --> D["Row mapper"]
    D -->|Thành công| E["Java record / DTO"]
    D -->|Thất bại| F["MappingFailure an toàn"]
    F --> G["Log nội bộ"]
    F --> H["Mã lỗi chung + trace ID cho client"]
~~~

Không phải ngoại lệ nào xuất hiện khi đọc dữ liệu cũng có cùng nguyên nhân.

| Trường hợp | Nguồn lỗi | Thông tin chẩn đoán có ích |
| --- | --- | --- |
| `getLong` trả `0` cho cột `NULL` | Thiếu giá trị bắt buộc | Trường `ID`, lỗi `REQUIRED_NULL` |
| `getBigDecimal` không đọc được giá trị cột | Đọc/chuyển kiểu JDBC thất bại | Trường `AMOUNT`, lỗi `JDBC_READ_FAILED`, SQLState đã kiểm tra |
| `status` chứa một mã ngoài enum Java | Dữ liệu không phù hợp miền nghiệp vụ | Trường `STATUS`, lỗi `INVALID_ENUM` |
| SQL đổi tên bí danh `amount` nhưng mapper vẫn đọc bí danh cũ | Sai lệch hợp đồng truy vấn–mapper | Trường `AMOUNT`, lỗi `JDBC_READ_FAILED` |
| `BigDecimal` có scale không được phép | Sai hợp đồng dữ liệu | Trường `AMOUNT`, lỗi `INVALID_SCALE` |
| `executeQuery` không chạy được vì kết nối mất | Lỗi truy cập DB, xảy ra trước mapper | Mã lỗi thao tác đọc DB, mã truy vấn cố định, SQLState |
| `ResultSet.next()` thất bại do kết nối/driver | Lỗi duyệt kết quả JDBC | Lỗi đọc DB hoặc duyệt kết quả, khác với lỗi chuyển một trường |

Đặc điểm cần lưu ý: lỗi ánh xạ **không nhất thiết là lỗi của người gửi request**. Một enum trong cơ sở dữ liệu chưa được cập nhật vào code hoặc một migration đổi tên cột có thể khiến tất cả request cùng thất bại. Với API, đây thường là lỗi nội bộ, không nên tự động trả mã HTTP `400` và không nên đưa nội dung hàng dữ liệu ra phản hồi.

## 2. Tách dữ liệu chẩn đoán khỏi dữ liệu nguồn

Một cấu trúc lỗi hữu ích chỉ nên chứa những trường đã được **chọn và kiểm soát trước**.

| Trường trong lỗi/log nội bộ | Có nên ghi? | Lưu ý |
| --- | --- | --- |
| `event` / `errorCode` | Có | Mã cố định như `ROW_MAPPING_FAILED` |
| `queryId` | Có | Tên logic cố định khai báo trong code, ví dụ `invoice.findFromId.v1` |
| `rowIndex` | Có | Vị trí 1-based trong tập kết quả đang duyệt; **không phải ID bản ghi** |
| `field` | Có, nếu được cho phép | Chọn từ enum trường đã khai báo; tránh dùng nhãn cột động chưa kiểm soát |
| `reason` | Có | Enum như `REQUIRED_NULL` hoặc `INVALID_ENUM` |
| `expectedType` | Có, nếu an toàn | Mô tả đã khai báo, ví dụ `DECIMAL(19,2)` hoặc `InvoiceStatus` |
| `sqlState` | Có điều kiện | Chỉ ghi mã SQLState năm ký tự hợp lệ từ JDBC; không ghi message của driver |
| `vendorCode` | Có điều kiện | Mã số nguyên của driver; thường hữu ích để điều tra |
| `traceId` | Có | UUID/correlation ID do hệ thống tạo hoặc đã xác thực |
| Tham số SQL, giá trị cột, nội dung `ResultSet` | **Không** | Có thể chứa email, số tài khoản, token, dữ liệu y tế, nội dung người dùng |
| `record.toString()` hoặc `domainObject.toString()` | **Không** | Java `record` tự sinh `toString()` có thể in ra toàn bộ các trường |
| `SQLException.getMessage()`, `cause.toString()` chưa kiểm soát | **Không** | Driver có thể đưa SQL, giá trị nhập, tên đối tượng hoặc dữ liệu khác vào message |
| SQL đầy đủ, `PreparedStatement.toString()` | **Không** | Một số driver mở rộng câu SQL và hiển thị cả tham số |

Ví dụ, nếu cột `status` chứa chuỗi bất thường `alice@example.com`, lỗi nên thể hiện:

~~~text
event=jdbc_row_mapping_failed
code=ROW_MAPPING_FAILED
trace_id=9e0c8b46-7195-4d4c-a938-e2658254fb76
query_id=invoice.findFromId.v1
row_index=3
field=STATUS
reason=INVALID_ENUM
expected=InvoiceStatus
sqlstate=NA
~~~

**Không nên** ghi:

~~~text
Failed to map invoice_id=83745:
status='alice@example.com', email='alice@example.com',
amount=123.45, sql=SELECT ...
~~~

Ngay cả mã khóa chính, mã khách hàng hay mã tenant cũng có thể là thông tin định danh. Chỉ cần biết lỗi tại **dòng thứ ba trong kết quả**, ở **trường STATUS**, của **truy vấn logic đã biết** là đủ để mở đầu điều tra. Khi cần xác định bản ghi chính xác, dùng công cụ truy vấn có phân quyền trên dữ liệu gốc; đừng lén biến log ứng dụng thành bản sao của bảng dữ liệu.

### Ba mức thông tin khác nhau

1. **Trong mapper:** lỗi có `reason`, `field`, `rowIndex`, `queryId`; tất cả là metadata được giới hạn giá trị.
2. **Trong log/telemetry nội bộ:** bổ sung `traceId`, SQLState hoặc vendor code đã chuẩn hóa nếu có; áp dụng quyền truy cập, thời gian lưu và chính sách che giấu theo hệ thống.
3. **Trong API/UI:** chỉ đưa mã lỗi chung, thông báo dễ hiểu và `traceId` để hỗ trợ điều tra; không đưa schema, tên cột, SQL, giá trị nguồn hoặc stack trace ra client.

Một thông báo an toàn là **hợp đồng**: nó chỉ chứa các trường và giá trị được cho phép. Đừng trông cậy hoàn toàn vào regex xóa email hay số thẻ khỏi chuỗi lỗi tự do; dữ liệu nhạy cảm có thể nằm trong nhiều định dạng khác mà bộ lọc bỏ sót.

## 3. Xác định hợp đồng ánh xạ trước khi viết code

Giả sử bảng hóa đơn có trường email nhạy cảm nhưng màn hình báo cáo chỉ cần mã hóa đơn, số tiền và trạng thái:

~~~sql
CREATE TABLE invoices (
    invoice_id BIGINT PRIMARY KEY,
    customer_email VARCHAR(255) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL CHECK (amount >= 0),
    status VARCHAR(16) NOT NULL
);
~~~

Truy vấn chỉ lấy các cột cần dùng:

~~~sql
SELECT invoice_id, amount, status
FROM invoices
WHERE invoice_id >= ?
ORDER BY invoice_id
~~~

Ở phía Java, bản ghi đầu ra và quy ước ánh xạ:

~~~java
public record InvoiceSummary(
        long id,
        java.math.BigDecimal amount,
        InvoiceStatus status) {}

public enum InvoiceStatus {
    DRAFT, ISSUED, PAID
}
~~~

Đoạn `record` sử dụng Java 16 trở lên. Trên Java 8–15, có thể thay bằng lớp DTO bất biến; nguyên tắc xử lý lỗi JDBC không thay đổi.

Hợp đồng cụ thể:

| Trường Java | Cột SQL | Kiểu mong đợi | Quy tắc |
| --- | --- | --- | --- |
| `id` | `invoice_id` | `BIGINT` → `long` | Bắt buộc có giá trị |
| `amount` | `amount` | `DECIMAL(19,2)` → `BigDecimal` | Không `NULL`, không âm, scale 2, tối đa 19 chữ số |
| `status` | `status` | `VARCHAR` → `InvoiceStatus` | Không `NULL`, đúng một trong `DRAFT`, `ISSUED`, `PAID` |

Không truy vấn `customer_email` vì mapper không sử dụng. Đây là cách giảm dữ liệu nhạy cảm xuất hiện trong bộ nhớ và tránh bị đưa vào log do vô tình in cả dòng.

## 4. Mẫu Java đầy đủ: mapper với ngoại lệ an toàn

Ví dụ dưới đây sử dụng JDBC chuẩn, `DataSource`, `PreparedStatement` và `ResultSet`. Phần ghi log minh họa với `java.util.logging` để không yêu cầu framework bên ngoài.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.util.logging.Logger;
import javax.sql.DataSource;

public final class InvoiceRepository {
    private static final Logger LOG =
            Logger.getLogger(InvoiceRepository.class.getName());

    // ID truy vấn được định nghĩa trước, không chứa tham số SQL.
    private static final String QUERY_ID = "invoice.findFromId.v1";

    private final DataSource dataSource;

    public InvoiceRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public enum InvoiceStatus {
        DRAFT, ISSUED, PAID
    }

    public record InvoiceSummary(
            long id, BigDecimal amount, InvoiceStatus status) {}

    // Chỉ liệt kê những trường được phép xuất hiện trong log.
    public enum Field {
        ID("invoice_id", "BIGINT"),
        AMOUNT("amount", "DECIMAL(19,2)"),
        STATUS("status", "InvoiceStatus");

        final String columnLabel;
        final String expected;

        Field(String columnLabel, String expected) {
            this.columnLabel = columnLabel;
            this.expected = expected;
        }
    }

    public enum Reason {
        REQUIRED_NULL,
        JDBC_READ_FAILED,
        INVALID_SCALE,
        OUT_OF_RANGE,
        INVALID_ENUM
    }

    // Ngoại lệ chỉ chứa metadata được kiểm soát.
    public static final class MappingFailure
            extends RuntimeException {

        private final int rowIndex;
        private final Field field;
        private final Reason reason;
        private final String sqlState;
        private final int vendorCode;

        private MappingFailure(
                int rowIndex,
                Field field,
                Reason reason,
                String sqlState,
                int vendorCode) {
            super("ROW_MAPPING_FAILED");
            this.rowIndex = rowIndex;
            this.field = field;
            this.reason = reason;
            this.sqlState = sqlState;
            this.vendorCode = vendorCode;
        }

        public String safeDiagnostic(UUID traceId) {
            return "event=jdbc_row_mapping_failed"
                    + " code=ROW_MAPPING_FAILED"
                    + " trace_id=" + traceId
                    + " query_id=" + QUERY_ID
                    + " row_index=" + rowIndex
                    + " field=" + field.name()
                    + " reason=" + reason.name()
                    + " expected=" + field.expected
                    + " sqlstate=" + sqlState
                    + " vendor_code=" + vendorCode;
        }
    }

    public List<InvoiceSummary> findFromId(
            long minId, UUID traceId) throws SQLException {
        Objects.requireNonNull(traceId, "traceId");

        String sql = "SELECT invoice_id, amount, status "
                + "FROM invoices WHERE invoice_id >= ? "
                + "ORDER BY invoice_id";

        List<InvoiceSummary> invoices = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, minId);

            try (ResultSet rs = ps.executeQuery()) {
                int rowIndex = 0;

                while (rs.next()) {
                    rowIndex++;

                    try {
                        invoices.add(mapOne(rs, rowIndex));
                    } catch (MappingFailure failure) {
                        LOG.warning(failure.safeDiagnostic(traceId));
                        throw failure;
                    }
                }
            }
        }

        return invoices;
    }

    private static InvoiceSummary mapOne(
            ResultSet rs, int rowIndex) {

        long id = readRequiredLong(rs, Field.ID, rowIndex);
        BigDecimal amount =
                readRequiredDecimal(rs, Field.AMOUNT, rowIndex);
        String statusText =
                readRequiredText(rs, Field.STATUS, rowIndex);

        // Chỉ chuẩn hóa nếu không cần bỏ chữ số có nghĩa.
        try {
            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ignored) {
            throw fail(rowIndex, Field.AMOUNT, Reason.INVALID_SCALE);
        }

        if (amount.precision() > 19 || amount.signum() < 0) {
            throw fail(rowIndex, Field.AMOUNT, Reason.OUT_OF_RANGE);
        }

        InvoiceStatus status;
        try {
            status = InvoiceStatus.valueOf(statusText);
        } catch (IllegalArgumentException ignored) {
            // Không đưa statusText hoặc exception gốc vào lỗi.
            throw fail(rowIndex, Field.STATUS, Reason.INVALID_ENUM);
        }

        return new InvoiceSummary(id, amount, status);
    }

    private static long readRequiredLong(
            ResultSet rs, Field field, int rowIndex) {
        try {
            long value = rs.getLong(field.columnLabel);
            // Kiểm tra ngay sau getter tương ứng.
            if (rs.wasNull()) {
                throw fail(rowIndex, field, Reason.REQUIRED_NULL);
            }
            return value;
        } catch (SQLException ex) {
            throw jdbcFail(rowIndex, field, ex);
        }
    }

    private static BigDecimal readRequiredDecimal(
            ResultSet rs, Field field, int rowIndex) {
        try {
            BigDecimal value = rs.getBigDecimal(field.columnLabel);
            if (value == null) {
                throw fail(rowIndex, field, Reason.REQUIRED_NULL);
            }
            return value;
        } catch (SQLException ex) {
            throw jdbcFail(rowIndex, field, ex);
        }
    }

    private static String readRequiredText(
            ResultSet rs, Field field, int rowIndex) {
        try {
            String value = rs.getString(field.columnLabel);
            if (value == null) {
                throw fail(rowIndex, field, Reason.REQUIRED_NULL);
            }
            return value;
        } catch (SQLException ex) {
            throw jdbcFail(rowIndex, field, ex);
        }
    }

    private static MappingFailure fail(
            int rowIndex, Field field, Reason reason) {
        return new MappingFailure(rowIndex, field, reason, "NA", 0);
    }

    private static MappingFailure jdbcFail(
            int rowIndex, Field field, SQLException ex) {
        // Chỉ giữ SQLState hợp lệ và mã số nguyên; không giữ
        // message, SQL hoặc cause của driver trong exception này.
        String state = ex.getSQLState();
        if (state == null || !state.matches("[0-9A-Z]{5}")) {
            state = "UNKNOWN";
        }

        return new MappingFailure(
                rowIndex,
                field,
                Reason.JDBC_READ_FAILED,
                state,
                ex.getErrorCode());
    }
}
~~~

### Giải thích các điểm quan trọng

- **`Field` là enum tĩnh.** Mapper chọn trường từ tập giá trị được cho phép, không lấy tên cột bất kỳ hay giá trị người dùng đưa vào trường `field` của log. `columnLabel` chỉ dùng cho các hàm đọc `ResultSet`.
- **`Reason` là enum tĩnh.** Không ghép dữ liệu gốc vào message lỗi kiểu `"invalid enum: " + statusText`.
- **`getLong` cần `wasNull()`.** JDBC trả `0` khi đọc `NULL` bằng `getLong`; chỉ `wasNull()` mới phân biệt được số 0 thật và `NULL`.
- **`getBigDecimal` / `getString` có thể trả `null`.** Kiểm tra điều kiện bắt buộc ở mapper trước khi dựng bản ghi.
- **Không sửa dữ liệu âm thầm.** Với amount, `setScale(2, UNNECESSARY)` chỉ chấp nhận bỏ số 0 thừa, không cho phép cắt số có nghĩa. Scale, precision và miền giá trị được kiểm tra theo hợp đồng.
- **`SQLException` tại bước đọc trường được chuyển thành mã an toàn.** Chỉ SQLState đúng định dạng năm ký tự và mã lỗi số nguyên được giữ lại. Không chuyển `ex.getMessage()` vào `MappingFailure`.
- **Ngoại lệ gốc không được gắn làm `cause` vào lỗi này.** Trong nhiều hệ thống, logger tự in `cause` và stack trace; thông điệp driver có thể chứa nội dung nhạy cảm. Đây là lựa chọn bảo vệ log mặc định của ví dụ.
- **`traceId` nhận dưới dạng `UUID`.** Tầng gọi phải tạo hoặc xác thực ID; không nhận trực tiếp chuỗi tùy ý của người dùng rồi chèn vào log. Dùng cùng một ID cho toàn bộ thao tác để đối chiếu sự kiện.
- **Query có `WHERE invoice_id >= ?` và `setLong(1, minId)`.** Tham số được ràng buộc qua `PreparedStatement`; giá trị `minId` không xuất hiện trong log.

Đoạn mã được viết cho Java 16 trở lên (vì dùng `record`). Các phiên bản Java cũ hơn có thể dùng một DTO bình thường. Đây là ví dụ về chính sách lỗi ở tầng ánh xạ; phương thức `findFromId` vẫn khai báo `throws SQLException` cho các lỗi kết nối, chuẩn bị/truy vấn hoặc duyệt `ResultSet` bên ngoài getter trong mapper. **Các lỗi SQL ở tầng repository cũng cần bộ xử lý an toàn riêng** nếu được ghi log hoặc đưa qua API.

### Sử dụng ở tầng ứng dụng

~~~java
import java.util.List;
import java.util.UUID;

UUID traceId = UUID.randomUUID();

try {
    List<InvoiceRepository.InvoiceSummary> invoices =
            repository.findFromId(100L, traceId);

    // Xử lý dữ liệu hợp lệ.
} catch (InvoiceRepository.MappingFailure failure) {
    // Repository đã ghi một sự kiện nội bộ an toàn.
    // Tầng API trả mã chung và traceId; không trả field/row/query.
    // Ví dụ phản hồi HTTP 500 được minh họa bên dưới.
}
~~~

Một phản hồi API có thể có dạng:

~~~json
{
  "code": "INTERNAL_DATA_MAPPING_ERROR",
  "message": "Không thể xử lý dữ liệu vào lúc này.",
  "traceId": "9e0c8b46-7195-4d4c-a938-e2658254fb76"
}
~~~

`traceId` trong ví dụ chỉ là giá trị minh họa. Hệ thống thực tế phải trả về đúng ID của thao tác đang xảy ra. Không cung cấp trường `statusText`, `minId`, `customer_email`, giá trị `amount`, SQL statement hay thông điệp driver cho client.

## 5. Đặt ranh giới xử lý lỗi ở đâu?

Tầng mapper nên xử lý các lỗi phát sinh khi **dịch một dòng dữ liệu sang mô hình Java**. Tầng repository chịu trách nhiệm kết nối và truy vấn. Tầng API/service quyết định cách báo kết quả và mã lỗi cho người dùng.

~~~mermaid
flowchart TB
    R["Repository: thực thi câu SQL"] --> Q{"Thực thi/duyệt thành công?"}
    Q -->|Không| S["Lỗi truy cập DB: xử lý an toàn riêng"]
    Q -->|Có| M["Mapper: đọc trường và kiểm tra hợp đồng"]
    M --> P{"Dữ liệu hợp lệ?"}
    P -->|Có| O["Trả DTO / record"]
    P -->|Không| F["MappingFailure với metadata cho phép"]
    F --> L["Một sự kiện log nội bộ"]
    F --> A["API: mã lỗi chung + traceId"]
~~~

Nếu gọi `executeQuery` thất bại, một `SQLException` ở bước đó **không có** thông tin cột hoặc dòng ánh xạ; gán bừa `rowIndex=1` hay `field=AMOUNT` sẽ khiến người điều tra hiểu sai. Hãy ghi nhận `DB_QUERY_FAILED` hoặc mã lỗi truy vấn khác ở tầng phù hợp, gắn `queryId`/`traceId` an toàn và SQLState đã chuẩn hóa nếu hữu ích.

Ngược lại, khi mapper phát hiện trạng thái enum không hợp lệ, không cần sao chép lỗi gốc của `Enum.valueOf`. Thông điệp mặc định của `IllegalArgumentException` khi enum sai có thể **chứa nguyên chuỗi đầu vào**; giữ `cause` rồi tự động log cả exception vẫn có nguy cơ lộ dữ liệu.

### Chính sách xử lý từng dòng

- **Giao dịch, hóa đơn, số dư và nghiệp vụ quan trọng:** thường dừng ánh xạ khi gặp dòng sai, tránh vô tình trả tập kết quả thiếu dữ liệu như thể thành công.
- **Import theo lô, báo cáo có cho phép bỏ qua:** chỉ bỏ qua dòng khi hợp đồng sản phẩm quy định rõ, có số lượng lỗi, cơ chế thông báo tập kết quả không đầy đủ và quy trình xử lý dữ liệu hỏng. Không ghi giá trị của từng dòng bị loại vào log.
- **Thao tác ghi dùng transaction:** quyết định `rollback` hay lưu các dòng hợp lệ phải xuất phát từ tính nhất quán nghiệp vụ; không để mapper tùy tiện gọi `commit()` hoặc `rollback()`.

Không tự động retry lỗi ánh xạ dữ liệu cố định như `INVALID_ENUM`. Nếu dữ liệu trong DB không thay đổi, retry nhiều lần chỉ làm tăng tải và tạo log lặp. Retry chỉ phù hợp với các lỗi tạm thời đã được phân loại riêng, chẳng hạn mất kết nối.

## 6. Thiết kế quan sát và chẩn đoán ở môi trường thật

### Thông tin theo dõi đáng tin cậy

Một sự kiện ánh xạ nên có tối thiểu:

~~~text
event        = jdbc_row_mapping_failed
error_code   = ROW_MAPPING_FAILED
query_id     = invoice.findFromId.v1
row_index    = 3
field        = STATUS
reason       = INVALID_ENUM
trace_id     = <UUID do server tạo>
~~~

Nếu hệ thống dùng structured logging, mỗi thuộc tính có thể là một trường riêng thay vì ghép thành một chuỗi. Giá trị của `query_id`, `field` và `reason` nên đến từ tập định nghĩa hữu hạn. Với hệ thống nhiều phiên bản, thêm `mapper_version` hoặc tên release **cố định** có thể giúp phát hiện khác biệt giữa deployment; không cần ghi toàn bộ SQL hay payload.

Dữ liệu phục vụ điều tra có thể chia thành:

| Kênh | Thông tin nên giữ | Thông tin nên loại bỏ |
| --- | --- | --- |
| Log ứng dụng | Mã lỗi, query ID, field enum, reason, row index, trace ID, SQLState chuẩn hóa | Giá trị cột, tham số, `toString()` của record, SQL, raw exception message |
| Metric | Tổng số lỗi theo query ID/field/reason | Trace ID, ID hóa đơn, email, giá trị từng bản ghi dưới dạng nhãn |
| Distributed tracing | Trace ID, loại thao tác JDBC logic, mã lỗi an toàn | SQL đã chèn tham số, bản ghi/result, payload cá nhân |
| API/UI | Mã lỗi chung, thông báo phù hợp, trace ID | Tên bảng/cột, SQLState, chi tiết mapper và stack trace |
| Công cụ điều tra có phân quyền | Truy vấn dữ liệu gốc khi có mục đích hợp lệ và dấu vết truy cập | Không đẩy toàn bộ kết quả điều tra ngược vào log chung |

**Không dùng `traceId` làm metric label.** Mỗi request có thể tạo một trace ID khác nhau, khiến số lượng nhãn metric tăng không giới hạn. Trường hợp nhiều dòng cùng thất bại, cân nhắc giới hạn/tổng hợp log theo query ID + reason để tránh quá nhiều thông báo; giữ số lượng lỗi và tín hiệu cảnh báo.

### Quyền truy cập và thời gian lưu

Việc không đưa PII vào log làm giảm đáng kể rủi ro, nhưng log chẩn đoán vẫn cần phân quyền, giới hạn thời gian lưu và kiểm soát việc chuyển tiếp sang hệ thống ngoài. Tên truy vấn hoặc mã lỗi cũng có thể tiết lộ cấu trúc hệ thống nếu gửi ra công khai. Khi cần chẩn đoán sâu hơn, nên dùng truy cập DB đã phân quyền, có giám sát/audit, thay vì thêm log dữ liệu nguồn vào mọi request.

### Những bẫy dễ bỏ sót

- `logger.warning("row=" + row)`: với Java `record`, `toString()` thường in giá trị của mọi component, kể cả trường nhạy cảm.
- `logger.log(Level.SEVERE, "Failed", ex)`: stack trace có thể kèm `SQLException.getMessage()`, `getNextException()` hoặc các ngoại lệ lồng chứa SQL/giá trị.
- `throw new MappingException("Invalid status: " + text, ex)`: cả message lẫn cause có thể chứa giá trị lỗi.
- `logger.debug("SQL=" + preparedStatement)`: driver có thể đưa tham số đã gán vào `toString()`.
- `log("field=" + rs.getMetaData().getColumnLabel(i))`: nhãn động chưa kiểm soát có thể tiết lộ tên trường hoặc nội dung bất ngờ; ưu tiên enum field.
- `hash(email)` để ghi log “ẩn danh”: hash trực tiếp một giá trị có miền đoán được có thể bị dò ngược; chỉ dùng mã định danh giả danh theo chính sách được duyệt khi thực sự cần, không xem hash đơn giản là đã loại bỏ dữ liệu nhạy cảm.

## 7. Kiểm thử không rò rỉ dữ liệu

Viết kiểm thử để xác minh **nội dung an toàn được giữ lại** và **dữ liệu nhạy cảm không xuất hiện**. Có thể dùng dữ liệu giả có chủ đích, ví dụ một giá trị email mẫu đặc biệt, rồi kiểm tra cả message lỗi, cause, log được thu thập và phản hồi API.

| Kịch bản | Lỗi dự kiến | Kiểm tra bảo mật |
| --- | --- | --- |
| `invoice_id` là `NULL` trong nguồn/mock | `REQUIRED_NULL`, field `ID` | Không log giá trị các cột khác |
| `amount` là `NULL` | `REQUIRED_NULL`, field `AMOUNT` | Không log toàn bộ dòng hoặc đối tượng |
| `status` = `private.person@example.test` | `INVALID_ENUM`, field `STATUS` | Chuỗi email giả **không** xuất hiện trong log, exception hoặc API |
| `status` = `PAID` | Ánh xạ thành công | Log không tự in DTO khi thành công |
| Cột `amount` bị thiếu hoặc getter ném `SQLException` | `JDBC_READ_FAILED`, field `AMOUNT` | Không đưa message/cause chưa kiểm soát vào log |
| `amount` có ba chữ số thập phân có nghĩa | `INVALID_SCALE` | Không ghi số tiền cụ thể |
| `amount` âm hoặc vượt giới hạn | `OUT_OF_RANGE` | Không ghi số tiền cụ thể |
| `getLong` trả `0` và `wasNull()` là `true` | `REQUIRED_NULL` | Không nhầm `NULL` thành ID bằng 0 |
| Một lỗi mapping lặp lại trong batch lớn | Báo lỗi/bỏ dòng theo chính sách đã chọn | Không phát tán hàng nghìn dòng dữ liệu hoặc làm tăng metric cardinality |

Ví dụ kiểm tra nguyên tắc với một log đã thu thập trong test:

~~~java
String sensitive = "private.person@example.test";

// safeLog là nội dung sự kiện đã được ghi bởi test logger.
if (safeLog.contains(sensitive)) {
    throw new AssertionError("Log đã làm lộ dữ liệu nguồn");
}
if (!safeLog.contains("reason=INVALID_ENUM")
        || !safeLog.contains("field=STATUS")) {
    throw new AssertionError("Log thiếu ngữ cảnh chẩn đoán");
}
~~~

Đây chỉ là minh họa assertion. Kiểm thử thực tế nên thu thập log qua handler/test appender, bao gồm kiểm tra ngoại lệ đã được serialize hoặc log bởi global handler. Đồng thời xác minh thông điệp trả về từ HTTP không chứa SQL, tên bảng/cột nội bộ hay giá trị lỗi. **Không chạy kiểm thử với dữ liệu cá nhân thật** khi không cần thiết.

### Checklist cho code review

1. Mapper có nêu rõ cột nào là bắt buộc, cách xử lý `NULL` và giới hạn giá trị không?
2. Có dùng `rs.wasNull()` ngay sau getter trả primitive khi cần không?
3. Mọi `field`/`reason`/`queryId` đưa vào log có được khai báo trước và giới hạn giá trị không?
4. Có đoạn nào log `ResultSet`, tham số SQL, domain object, `record.toString()` hoặc ngoại lệ driver chưa kiểm soát không?
5. Có vô tình nối giá trị sai vào `IllegalArgumentException`, `NumberFormatException`, `DateTimeParseException` hoặc message lỗi chuyển đổi khác không?
6. `traceId` có được phát sinh hoặc kiểm tra bởi hệ thống và dùng xuyên suốt các tầng không?
7. Lỗi mapper có được phân biệt với lỗi kết nối, lỗi SQL, lỗi transaction và lỗi nghiệp vụ do request không?
8. API có trả thông tin vừa đủ để hỗ trợ tra cứu mà không phơi lộ nội bộ không?
9. Có kiểm thử trường hợp dữ liệu giả nhạy cảm xuất hiện trong đầu vào lỗi không?
10. Có bảo đảm chính sách fail-fast/skip-row và metric/log không tạo thêm rủi ro khi số lượng lỗi tăng mạnh không?

## 8. Bài tập thực hành

**Bài 1 — Phân loại lỗi.** Bảng `products` có cột `price DECIMAL(19,2) NOT NULL` và `availability VARCHAR(12) NOT NULL`. Khi ánh xạ một hàng sang DTO, `availability` là chuỗi `"IN_STOCK_NEW"` nhưng ứng dụng chỉ có enum `IN_STOCK` và `OUT_OF_STOCK`. Hãy đề xuất `reason`, `field` và nội dung log an toàn. Giải thích vì sao không nên đưa chuỗi gốc vào message.

**Bài 2 — Kiểm tra `NULL`.** Một mapper dùng `rs.getInt("quantity")` rồi tạo DTO luôn. Hãy bổ sung kiểm tra để phân biệt số lượng `0` hợp lệ với `NULL` không hợp lệ và tạo lỗi chứa mã/trường/vị trí dòng.

**Bài 3 — Ranh giới lỗi.** Phân biệt `SQLException` xảy ra trong `executeQuery` với `SQLException` xảy ra trong `rs.getBigDecimal("amount")`. Trường hợp nào được gắn `field=AMOUNT`? Trường hợp nào không biết vị trí cột?

**Bài 4 — Đánh giá bảo mật.** Hãy rà soát đoạn code:

~~~java
try {
    return InvoiceStatus.valueOf(rs.getString("status"));
} catch (Exception e) {
    logger.warning("Bad row: " + rs + ", error=" + e);
    throw e;
}
~~~

Chỉ ra ít nhất ba nguy cơ và thay bằng thông báo dùng `queryId`, `rowIndex`, `field`, `reason`, `traceId` đã kiểm soát. Chú ý rằng ví dụ này cũng bắt quá rộng `Exception` và không phân biệt lỗi JDBC với lỗi enum.

**Gợi ý đáp án:** (1) `INVALID_ENUM`/`AVAILABILITY`, log chỉ chứa metadata an toàn; (2) gọi `wasNull()` ngay sau `getInt`; (3) lỗi `executeQuery` thuộc tầng thực thi truy vấn, còn lỗi `getBigDecimal` đã biết field đang đọc; (4) tránh `ResultSet.toString()`, ngoại lệ có message chứa giá trị, bắt lỗi quá rộng và chuyển exception chưa kiểm soát ra tầng trên.

Một thiết kế lỗi ánh xạ JDBC tốt phải giúp người vận hành xác định được **truy vấn nào, dòng thứ mấy trong kết quả, trường nào và quy tắc nào thất bại**, đồng thời giữ **giá trị nguồn, SQL và thông điệp driver chưa được kiểm soát** ngoài các kênh log, telemetry và phản hồi công khai.
