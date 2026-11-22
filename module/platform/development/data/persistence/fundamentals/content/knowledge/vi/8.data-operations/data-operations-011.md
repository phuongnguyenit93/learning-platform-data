# Phân biệt dữ liệu chưa được gửi với yêu cầu gán null

Một người dùng sửa tên hiển thị của khách hàng. API nhận JSON chỉ có trường `displayName` nhưng sau khi lưu, số điện thoại đã tồn tại lại thành `NULL`. Lỗi xảy ra vì DTO Java có `phoneNumber == null` khi trường này *không được gửi*, còn mapper xem đó là lệnh xóa. Ở chiều ngược lại, khi người dùng **chủ động xóa số điện thoại**, câu SQL dùng `COALESCE` lại giữ nguyên số cũ.

Hai lỗi trái ngược xuất phát từ một nhầm lẫn: **không cung cấp chỉ dẫn thay đổi khác với chỉ dẫn đặt giá trị thành null**.

Bài thuộc chương **Thao tác dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module trang bị nguyên lý lưu trữ dữ liệu bền vững trong ứng dụng Java, từ lựa chọn mô hình và lược đồ, truy vấn/chỉ mục đến transaction, isolation, kiểm soát đồng thời, thiết kế ranh giới persistence, xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Trong phạm vi này, bài tập trung vào cách bảo toàn ý định cập nhật giữa HTTP/JSON, DTO, domain, JDBC/ORM và database.

Sau bài học, bạn có thể:

- Phân biệt **trường vắng mặt (omitted)**, **trường có giá trị `null`** và **trường có giá trị cụ thể**.
- Chọn ngữ nghĩa thích hợp cho `POST`, `PUT`, `PATCH`, JSON Merge Patch và JSON Patch.
- Ánh xạ JSON sang kiểu Java có ba trạng thái, không làm mất thông tin trường đã được gửi hay chưa.
- Cập nhật đúng những cột được yêu cầu, đồng thời bảo vệ nullability, transaction, version và quyền truy cập.
- Thiết kế phép thử để phát hiện việc xóa dữ liệu vô tình hoặc bỏ sót yêu cầu xóa hợp lệ.

## 1. Ba trạng thái đầu vào là ba ý định khác nhau

Xét khách hàng đang có:

```json
{
  "customerId": "C-101",
  "displayName": "Minh An",
  "phoneNumber": "0901234567",
  "marketingOptIn": true
}
```

Với hợp đồng cập nhật từng phần, ba request sau khác nhau:

| Request | Trạng thái `phoneNumber` | Ý nghĩa |
| --- | --- | --- |
| `{"displayName":"Minh An Group"}` | **OMITTED** | Không thay đổi điện thoại |
| `{"phoneNumber":null}` | **SET_NULL** | Yêu cầu xóa điện thoại, nếu được phép |
| `{"phoneNumber":"0987654321"}` | **SET_VALUE** | Đổi điện thoại thành giá trị mới |

Một mô hình thao tác có thể viết:

```text
FieldChange<T>
  OMITTED        : không cập nhật trường này
  SET_NULL       : chủ động xóa giá trị
  SET_VALUE(x)   : chủ động gán giá trị x
```

Đây là **ba trạng thái của lệnh cập nhật**, không phải ba giá trị của cột SQL. Trong database, cột có giá trị hoặc `NULL`; trạng thái omitted là thông tin cần giữ khi xử lý lệnh, không được biến thành một giá trị lưu mặc định.

### Không gửi khác với chuỗi rỗng, false và 0

| Input | Có trường? | Có thể mang ý nghĩa |
| --- | --- | --- |
| Thiếu `phoneNumber` | Không | Giữ nguyên |
| `"phoneNumber":null` | Có | Xóa hoặc bị từ chối |
| `"phoneNumber":""` | Có | Gán chuỗi rỗng, không mặc định là xóa |
| `"marketingOptIn":false` | Có | Gán false |
| `"quantity":0` | Có | Gán 0, nếu nghiệp vụ cho phép |
| `"tags":[]` | Có | Có thể thay danh sách bằng danh sách rỗng |
| `"tags":null` | Có | Có ý nghĩa null riêng theo hợp đồng |

Đừng dùng truthiness (`if (value)`) để kiểm tra một trường có được gửi hay không: `false`, `0` và `""` đều có thể bị bỏ qua. Trong Java, `value != null` cũng không phân biệt JSON omitted với JSON explicit null nếu DTO đã làm mất thông tin có/không có member.

### Null trong JSON, null Java và NULL trong SQL

- **JSON `null`:** một giá trị JSON đã được gửi rõ ràng.
- **Java `null`:** tham chiếu vắng giá trị trong object Java; nguồn gốc có thể từ omitted hoặc explicit null.
- **SQL `NULL`:** giá trị không có theo mô hình ba giá trị của SQL. So sánh dùng `IS NULL` chứ không dùng `= NULL`.
- **Chuỗi `"null"`:** bốn ký tự văn bản, không phải JSON null hoặc SQL NULL.

Đặc biệt trong cột PostgreSQL `JSONB`, JSON null (`'null'::jsonb`) khác SQL NULL (`NULL::jsonb`). Cập nhật một member JSON và đặt cả cột SQL thành NULL là hai thao tác khác nhau.

## 2. Hợp đồng phải xác định chính sách cho từng trường

Giả sử API `PATCH /customers/{customerId}` có chính sách:

| Trường | Omitted | Explicit null | Giá trị cụ thể |
| --- | --- | --- | --- |
| `displayName` | Giữ nguyên | Từ chối (tên bắt buộc) | Chuỗi không rỗng, được validate |
| `phoneNumber` | Giữ nguyên | Xóa số điện thoại | Số mới theo validation |
| `marketingOptIn` | Giữ nguyên | Từ chối (boolean không null) | Chấp nhận cả true và false |
| `customerId` | Không được sửa | Không được sửa | Không được sửa |
| `tenantId` | Lấy từ ngữ cảnh quyền | Không được sửa | Không được sửa |
| `version` | Xử lý theo điều kiện concurrency | Không được sửa trực tiếp | Do server quản lý |

**Cột cho phép NULL không đồng nghĩa mọi caller được phép xóa.** Việc xóa có thể phụ thuộc trạng thái hồ sơ, quyền người dùng hoặc quy tắc xác minh. Ngược lại, cột `NOT NULL` không thay thế validation có thông báo rõ ở domain/API.

Một contract có thể chọn xử lý `{"phoneNumber":""}` thành lỗi, hoặc cho phép chuỗi rỗng, nhưng **không nên âm thầm đồng nhất nó với omitted/null** khi chưa ghi rõ chính sách.

## 3. POST, PUT và PATCH không có chung ngữ nghĩa

| Thao tác | Trường vắng mặt thường được xử lý ra sao? | Khi nhận explicit null |
| --- | --- | --- |
| **POST tạo mới** | Có thể lấy default, hoặc lỗi nếu trường bắt buộc | Lưu NULL hoặc lỗi theo schema/domain |
| **PUT thay thế representation** | Phải theo hợp đồng thay thế; thiếu trường có thể là lỗi hoặc không còn trong representation mới | Có thể là một phần representation thay thế |
| **PATCH từng phần** | Thường giữ nguyên thuộc tính chưa được đề cập | Xóa, đặt null hoặc lỗi theo định dạng patch/hợp đồng |
| **JSON Merge Patch** | Giữ nguyên member JSON vắng mặt | Loại bỏ member JSON theo RFC 7396 |
| **JSON Patch** | Chỉ làm những operation được liệt kê | `replace` với null khác `remove` |

`PATCH` không mặc nhiên đồng nghĩa một JSON object với quy tắc “null là xóa”. **Media type và hợp đồng API** mới quyết định cách áp dụng patch. Trường bị thiếu trong `POST` và `PUT` cũng không tự mang ngữ nghĩa giống trường bị thiếu trong `PATCH`.

### DB default: cột không gửi khác explicit SQL NULL

```sql
CREATE TABLE notification_preference (
    id UUID PRIMARY KEY,
    marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE
);

-- INSERT bỏ cột: lấy DEFAULT FALSE.
INSERT INTO notification_preference (id)
VALUES ('00000000-0000-0000-0000-000000000001');

-- INSERT ghi NULL rõ ràng: vi phạm NOT NULL.
INSERT INTO notification_preference (id, marketing_opt_in)
VALUES ('00000000-0000-0000-0000-000000000002', NULL);
```

Đối với `UPDATE`, cột không có trong `SET` được giữ nguyên (ngoại trừ các cơ chế khác như trigger). Gửi `= NULL` không tự kích hoạt default; nếu muốn đặt về default, đó là một **thao tác riêng** như `SET column = DEFAULT` theo khả năng engine.

## 4. Jackson: giữ thông tin member có xuất hiện hay không

Trong JSON, một object có thể thiếu khóa hoặc có khóa với `null`. Nhưng DTO đơn giản sau không đủ để lưu cả ba ý định:

```java
record CustomerPatchDto(
        String displayName,
        String phoneNumber,
        Boolean marketingOptIn
) {}
```

Với nhiều cấu hình deserialization, `{}` và `{"phoneNumber":null}` đều có thể cho `phoneNumber() == null`. Một boolean primitive còn có thể mặc định thành `false` khiến omitted bị biến thành một giá trị thật.

Dùng Jackson `JsonNode` ở ranh giới nhận request giúp phân biệt:

```java
import com.fasterxml.jackson.databind.JsonNode;

static void inspect(JsonNode root) {
    if (!root.isObject() || !root.has("phoneNumber")) {
        System.out.println("phoneNumber omitted");
        return;
    }
    JsonNode value = root.get("phoneNumber");
    if (value.isNull()) {
        System.out.println("explicit null");
    } else if (value.isTextual()) {
        System.out.println("text: " + value.textValue());
    } else {
        throw new IllegalArgumentException("Expected text or null");
    }
}
```

Ở Jackson:

- `has("phoneNumber")` trả true kể cả khi member có giá trị JSON null.
- `get("phoneNumber")` trả Java null nếu member vắng; trả `NullNode` nếu JSON chứa null.
- `hasNonNull("phoneNumber")` trả false cho **cả omitted và explicit null**, nên không dùng một mình để phân biệt.
- Nếu dùng `path(...)`, phải xét `isMissingNode()`.

Khi dùng `Map<String,Object>`, `containsKey(...)` có thể giữ thông tin có/không có khóa, nhưng cần validation kiểu dữ liệu nghiêm ngặt trước khi đưa vào domain.

### Cấu hình parser cũng là một phần hợp đồng

JSON có thể có member trùng tên:

```json
{"phoneNumber":"0901234567","phoneNumber":null}
```

Tùy parser/cấu hình, member sau có thể ghi đè member trước hoặc cả tài liệu bị từ chối. Với API nhạy cảm, cần một chính sách nhất quán và kiểm thử giữa các thành phần nhận/truyền. Đồng thời giới hạn kích thước payload, độ sâu JSON, số phần tử, kiểu dữ liệu và các chuyển đổi tự động như chuỗi rỗng thành null.

## 5. Mô hình tri-state trong Java

Một kiểu dữ liệu biểu đạt ý định tốt hơn một `String` nullable. Ví dụ Java 17:

```java
import java.util.Objects;

enum ChangeKind { OMITTED, SET_VALUE, SET_NULL }

record FieldChange<T>(ChangeKind kind, T value) {
    FieldChange {
        Objects.requireNonNull(kind, "kind");
        if (kind == ChangeKind.SET_VALUE && value == null) {
            throw new IllegalArgumentException("SET_VALUE needs a value");
        }
        if (kind != ChangeKind.SET_VALUE && value != null) {
            throw new IllegalArgumentException("Only SET_VALUE can have a value");
        }
    }

    static <T> FieldChange<T> omitted() {
        return new FieldChange<>(ChangeKind.OMITTED, null);
    }

    static <T> FieldChange<T> clear() {
        return new FieldChange<>(ChangeKind.SET_NULL, null);
    }

    static <T> FieldChange<T> set(T value) {
        return new FieldChange<>(ChangeKind.SET_VALUE, value);
    }

    boolean supplied() {
        return kind != ChangeKind.OMITTED;
    }
}

record CustomerPatch(
        FieldChange<String> displayName,
        FieldChange<String> phoneNumber,
        FieldChange<Boolean> marketingOptIn
) {
    CustomerPatch {
        Objects.requireNonNull(displayName);
        Objects.requireNonNull(phoneNumber);
        Objects.requireNonNull(marketingOptIn);
    }

    boolean isEmpty() {
        return !displayName.supplied()
                && !phoneNumber.supplied()
                && !marketingOptIn.supplied();
    }
}
```

Một giá trị `SET_VALUE(false)` vẫn là thao tác có mặt. Tương tự, `SET_VALUE("")` không trở thành omitted. Lớp domain có thể từ chối chuỗi rỗng theo quy tắc nghiệp vụ, nhưng **không nên sửa lịch sử về sự xuất hiện của trường**.

`Optional<T>` thông thường chỉ biểu diễn có/không có giá trị; nếu cả omitted và explicit null đều biến thành `Optional.empty()`, thông tin đã mất. Các thư viện wrapper hỗ trợ presence hoặc annotation Jackson **có thể** giúp, nhưng phải kiểm tra serializer/deserializer thực tế; chỉ có tên kiểu hoặc `@JsonInclude(NON_NULL)` không chứng minh đã giữ được semantics đầu vào.

## 6. Chuyển JsonNode thành lệnh cập nhật có kiểu

Lớp API nên chuyển raw JSON thành `CustomerPatch` càng sớm càng phù hợp, rồi để domain kiểm tra điều kiện nghiệp vụ. Ví dụ này dùng allowlist để từ chối các trường không được sửa qua endpoint.

```java
import com.fasterxml.jackson.databind.JsonNode;
import java.util.Iterator;
import java.util.Set;

final class CustomerPatchParser {
    private static final Set<String> ALLOWED =
            Set.of("displayName", "phoneNumber", "marketingOptIn");

    static CustomerPatch parse(JsonNode root) {
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("Expected a JSON object");
        }

        Iterator<String> names = root.fieldNames();
        while (names.hasNext()) {
            String name = names.next();
            if (!ALLOWED.contains(name)) {
                throw new IllegalArgumentException("Unknown field: " + name);
            }
        }

        FieldChange<String> displayName =
                textField(root, "displayName", false);
        FieldChange<String> phoneNumber =
                textField(root, "phoneNumber", true);
        FieldChange<Boolean> marketing =
                booleanField(root, "marketingOptIn");

        if (displayName.kind() == ChangeKind.SET_VALUE
                && displayName.value().isBlank()) {
            throw new IllegalArgumentException("Name cannot be blank");
        }

        CustomerPatch patch =
                new CustomerPatch(displayName, phoneNumber, marketing);
        if (patch.isEmpty()) {
            throw new IllegalArgumentException("Empty patch");
        }
        return patch;
    }

    private static FieldChange<String> textField(
            JsonNode object, String field, boolean nullable
    ) {
        if (!object.has(field)) {
            return FieldChange.omitted();
        }
        JsonNode value = object.get(field);
        if (value.isNull()) {
            if (!nullable) {
                throw new IllegalArgumentException(field + " cannot be null");
            }
            return FieldChange.clear();
        }
        if (!value.isTextual()) {
            throw new IllegalArgumentException(field + " must be text");
        }
        return FieldChange.set(value.textValue());
    }

    private static FieldChange<Boolean> booleanField(
            JsonNode object, String field
    ) {
        if (!object.has(field)) {
            return FieldChange.omitted();
        }
        JsonNode value = object.get(field);
        if (!value.isBoolean()) {
            throw new IllegalArgumentException(field + " must be boolean");
        }
        return FieldChange.set(value.booleanValue());
    }
}
```

Trong ví dụ:

- `{"displayName":null}` bị từ chối; `{"displayName":""}` cũng bị từ chối, nhưng vì **quy tắc khác nhau**.
- `{"phoneNumber":null}` trở thành `SET_NULL`; `{"phoneNumber":""}` là `SET_VALUE("")` và phải được domain xử lý theo chính sách điện thoại.
- `{"marketingOptIn":false}` vẫn trở thành `SET_VALUE(false)`.
- `customerId`, `tenantId` hoặc `isAdmin` trong JSON không nằm trong allowlist nên bị từ chối.

Ví dụ chưa chứa logic chuẩn hóa số điện thoại, giới hạn chiều dài và quyền sửa thông tin. Những bước này phải được bổ sung, không nên đưa mọi validation vào deserializer rồi bỏ qua domain.

## 7. Câu lệnh SQL phải bảo toàn trạng thái omitted

Ví dụ PostgreSQL:

```sql
CREATE TABLE customer (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    display_name TEXT NOT NULL,
    phone_number TEXT,
    marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
    version BIGINT NOT NULL DEFAULT 1 CHECK (version >= 1),
    CONSTRAINT pk_customer PRIMARY KEY (tenant_id, customer_id)
);
```

### SQL `SET` chỉ thay cột được liệt kê

```sql
-- Bỏ qua phone_number: không sửa giá trị cũ.
UPDATE customer
SET display_name = 'Minh An Group'
WHERE tenant_id = :tenant_id AND customer_id = :customer_id;

-- Gán NULL rõ ràng: xóa điện thoại nếu được phép.
UPDATE customer
SET phone_number = NULL
WHERE tenant_id = :tenant_id AND customer_id = :customer_id;
```

Các dấu `:tenant_id` và `:customer_id` biểu diễn bind parameters của thư viện hỗ trợ named parameters; JDBC thuần dùng `?`.

Cách viết dưới đây **không phù hợp** với yêu cầu explicit-null xóa điện thoại:

```sql
UPDATE customer
SET phone_number = COALESCE(:incoming_phone, phone_number)
WHERE tenant_id = :tenant_id AND customer_id = :customer_id;
```

`COALESCE` không nhìn thấy JSON member có xuất hiện hay không. Nó giữ `phone_number` khi input là null, bất kể null có nghĩa là omitted hay xóa. Điều này có thể phù hợp **nếu hợp đồng cố tình quy định null = không đổi**, nhưng không phù hợp với hợp đồng tri-state đang học.

### Dùng cờ present tách biệt với giá trị

```sql
UPDATE customer
SET phone_number = CASE
    WHEN :phone_present THEN :phone_value
    ELSE phone_number
END
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
```

| `phone_present` | `phone_value` | Ý nghĩa |
| --- | --- | --- |
| `false` | Bất kỳ | Giữ nguyên số cũ |
| `true` | `NULL` | Xóa số |
| `true` | `"0987654321"` | Đặt số mới |

Khi bind SQL NULL, kiểu tham số có thể cần được khai báo rõ, ví dụ `CAST(? AS TEXT)` ở PostgreSQL hoặc `PreparedStatement.setNull(..., Types.VARCHAR)` theo khả năng driver/engine. Một phương án khác là xây `SET` động từ **danh sách cột allowlist**, chỉ đưa vào câu SQL những trường được gửi và bind toàn bộ giá trị qua prepared statement; tuyệt đối không nối tên cột tùy ý do client gửi.

## 8. Java/JDBC: cập nhật tri-state với optimistic locking

Đường ghi nên kết hợp ba mối quan tâm riêng:

1. **Presence:** field nào có yêu cầu sửa?
2. **Validation và authorization:** yêu cầu sửa field đó có hợp lệ và được phép không?
3. **Concurrency:** client đang sửa dựa trên phiên bản nào của thực thể?

Ví dụ dùng câu SQL cố định để tránh phải xây chuỗi SQL động:

```sql
UPDATE customer
SET
    display_name = CASE WHEN ? THEN CAST(? AS TEXT)
                        ELSE display_name END,
    phone_number = CASE WHEN ? THEN CAST(? AS TEXT)
                        ELSE phone_number END,
    marketing_opt_in = CASE WHEN ? THEN CAST(? AS BOOLEAN)
                            ELSE marketing_opt_in END,
    version = version + 1
WHERE tenant_id = ?
  AND customer_id = ?
  AND version = ?
RETURNING version;
```

Ví dụ Java/JDBC (Java 17, PostgreSQL) sau sử dụng `CustomerPatch` từ mục 5:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.OptionalLong;
import java.util.UUID;
import javax.sql.DataSource;

final class JdbcCustomerPatchWriter {
    private final DataSource dataSource;

    JdbcCustomerPatchWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    OptionalLong apply(
            UUID tenantId,
            UUID customerId,
            long expectedVersion,
            CustomerPatch patch
    ) throws SQLException {
        if (patch.isEmpty()) {
            throw new IllegalArgumentException("No fields to update");
        }
        if (patch.displayName().kind() == ChangeKind.SET_NULL
                || patch.marketingOptIn().kind() == ChangeKind.SET_NULL) {
            throw new IllegalArgumentException("Field cannot be null");
        }

        String sql = """
                UPDATE customer
                SET display_name = CASE WHEN ? THEN CAST(? AS TEXT)
                                        ELSE display_name END,
                    phone_number = CASE WHEN ? THEN CAST(? AS TEXT)
                                        ELSE phone_number END,
                    marketing_opt_in = CASE WHEN ? THEN CAST(? AS BOOLEAN)
                                            ELSE marketing_opt_in END,
                    version = version + 1
                WHERE tenant_id = ? AND customer_id = ? AND version = ?
                RETURNING version
                """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            boolean commitAttempted = false;
            try {
                OptionalLong result;
                try (PreparedStatement ps = connection.prepareStatement(sql)) {
                    FieldChange<String> name = patch.displayName();
                    FieldChange<String> phone = patch.phoneNumber();
                    FieldChange<Boolean> consent = patch.marketingOptIn();

                    ps.setBoolean(1, name.kind() == ChangeKind.SET_VALUE);
                    if (name.kind() == ChangeKind.SET_VALUE) {
                        ps.setString(2, name.value());
                    } else {
                        ps.setNull(2, Types.VARCHAR);
                    }

                    // SET_NULL và SET_VALUE đều là yêu cầu thay đổi.
                    ps.setBoolean(3, phone.supplied());
                    if (phone.kind() == ChangeKind.SET_VALUE) {
                        ps.setString(4, phone.value());
                    } else {
                        ps.setNull(4, Types.VARCHAR);
                    }

                    ps.setBoolean(5, consent.supplied());
                    if (consent.kind() == ChangeKind.SET_VALUE) {
                        ps.setBoolean(6, consent.value());
                    } else {
                        ps.setNull(6, Types.BOOLEAN);
                    }

                    ps.setObject(7, tenantId);
                    ps.setObject(8, customerId);
                    ps.setLong(9, expectedVersion);

                    try (ResultSet rows = ps.executeQuery()) {
                        result = rows.next()
                                ? OptionalLong.of(rows.getLong(1))
                                : OptionalLong.empty();
                    }
                }

                if (result.isEmpty()) {
                    connection.rollback();
                    return OptionalLong.empty();
                }

                commitAttempted = true;
                connection.commit();
                return result;
            } catch (SQLException failure) {
                if (commitAttempted) {
                    // COMMIT có thể đã thành công dù phản hồi bị mất.
                    throw new CommitOutcomeUnknown(failure);
                }
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    static final class CommitOutcomeUnknown extends RuntimeException {
        CommitOutcomeUnknown(SQLException cause) {
            super("Reconcile operation before retrying", cause);
        }
    }
}
```

Giải thích đường ghi:

- `name.kind() == SET_VALUE` bật cập nhật tên. `SET_NULL` bị từ chối từ trước, còn omitted không sửa.
- `phone.supplied()` trả true cho cả `SET_NULL` và `SET_VALUE`. Nếu là `SET_NULL`, tham số giá trị được bind thành SQL NULL.
- `marketingOptIn:false` được bind thành `false` vì `SET_VALUE(false)` là một thao tác có mặt.
- `version = expectedVersion` làm việc kiểm tra phiên bản và cập nhật diễn ra **nguyên tử trong một câu SQL**.
- `RETURNING version` trả phiên bản mới nếu câu lệnh đã ảnh hưởng đúng một hàng, nhưng chỉ được xác nhận thành công cho caller khi transaction commit theo hợp đồng.

**Giới hạn:** mã là ví dụ về semantics cập nhật, chưa có đầy đủ kiểm tra quyền, validation điện thoại, audit/outbox và quản lý các lỗi ngoài `commit()`. Nếu đóng connection/pool thất bại sau commit đã xác nhận, tầng gọi còn phải phân biệt lỗi cleanup với commit outcome. Nếu kết quả `UPDATE` là 0 hàng, có thể ID không tồn tại, tenant sai hoặc version đã đổi; application phải xử lý mà không tiết lộ dữ liệu tenant khác.

Một request thay đổi nhiều field nên thành công **toàn bộ hoặc rollback toàn bộ**. Không được áp dụng từng field bằng các lệnh autocommit riêng nếu invariant đòi hỏi cập nhật nguyên tử.

## 9. JSON Merge Patch khác JSON Patch

### JSON Merge Patch — RFC 7396

Với media type `application/merge-patch+json`, khi patch là object:

- **Member không có trong patch:** giữ nguyên thành viên tương ứng.
- **Member có giá trị null:** loại bỏ member khỏi target object.
- **Member có giá trị khác null:** thêm/thay thế, hoặc merge đệ quy theo quy tắc của chuẩn khi phù hợp.

Target:

```json
{
  "displayName": "Minh An",
  "phoneNumber": "0901234567",
  "settings": {
    "language": "vi",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
```

Merge patch:

```json
{
  "phoneNumber": null,
  "settings": { "language": "en" }
}
```

Kết quả về cấu trúc JSON:

```json
{
  "displayName": "Minh An",
  "settings": {
    "language": "en",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
```

**Quan trọng:** chuẩn JSON Merge Patch quy định `null` trong object patch là **xóa member JSON**, không phải lệnh SQL `SET column = NULL`. Ứng dụng chỉ ánh xạ thao tác xóa member thành SQL NULL khi domain đã định nghĩa “không có thuộc tính này” là cột null. Nếu cần **đặt một member JSON thành chính JSON null**, Merge Patch object thường không thích hợp cho trường hợp đó.

Với array, Merge Patch thay thế array như một giá trị toàn bộ; không tự merge các phần tử theo ID nghiệp vụ.

### JSON Patch — RFC 6902

Media type `application/json-patch+json` dùng một danh sách operation. Hai operation sau khác nhau:

```json
[
  { "op": "replace", "path": "/phoneNumber", "value": null }
]
```

```json
[
  { "op": "remove", "path": "/phoneNumber" }
]
```

`replace` đặt giá trị **JSON null** ở vị trí đích; `remove` loại vị trí đó ra khỏi tài liệu. Các operation có điều kiện tồn tại của đường dẫn theo chuẩn; `add`, `test` cũng có semantics riêng. Khi dữ liệu là một danh sách entity con, nên cân nhắc lệnh nghiệp vụ dựa trên **ID bản ghi** thay vì chỉ index của array, vì index có thể thay đổi.

Không gọi một endpoint là “JSON Merge Patch” nếu thực tế nó áp dụng quy tắc khác mà không công bố; client có thể hiểu `null` là xóa member và mất dữ liệu không mong muốn.

## 10. ORM và mapper có thể làm mất ý định cập nhật

Một cách viết nguy hiểm:

```java
// dto.phoneNumber() có thể null vì field bị bỏ qua!
entity.setDisplayName(dto.displayName());
entity.setPhoneNumber(dto.phoneNumber());
entity.setMarketingOptIn(dto.marketingOptIn());
```

Nếu DTO đến từ JSON PATCH thiếu các field, nó có thể xóa điện thoại, đặt boolean về default hoặc ghi trạng thái không hợp lệ.

Một số cơ chế thường bị hiểu nhầm:

| Cơ chế | Điều cần hiểu |
| --- | --- |
| `BeanUtils` hoặc mapper tự động | Có thể copy cả null/default do omitted tạo ra |
| “Ignore null properties” | Chặn xóa nhầm khi omitted, nhưng cũng **chặn explicit-null hợp lệ** |
| JPA `merge(detached)` | Có thể sao chép trạng thái chưa đầy đủ của entity detached vào managed instance; không phải công cụ tự hiểu JSON PATCH |
| ORM dirty checking | Theo dõi field thực sự bị thay đổi trong managed entity, nhưng setter nhận null sai vẫn gây update sai |
| ORM dynamic update | Chỉ tối ưu các cột thay đổi; không phục hồi được thông tin presence đã mất |
| Primitive `boolean`/`int` | Default false/0 có thể bị nhầm với giá trị được gửi |
| `@JsonInclude(NON_NULL)` | Chủ yếu là quy tắc serialization output, không phải bằng chứng input giữ tri-state |

Cách phù hợp thường là **tách DTO cho CREATE/REPLACE/PATCH**, parse presence của PATCH tại boundary, chỉ áp dụng những `FieldChange.supplied()` lên managed entity đang được đọc đúng ID và version trong transaction, rồi kiểm tra invariant/authorization trước commit.

## 11. Bảo mật và quyền xóa giá trị

Một cột `phone_number` cho phép SQL NULL không có nghĩa mọi người dùng đều được phép xóa nó. Ví dụ số điện thoại đã xác minh đang dùng cho xác thực có thể cần quy trình xác nhận riêng trước khi xóa.

Ngoài validation dữ liệu, phải có:

- **Field-level allowlist:** reject những trường không thể sửa qua endpoint như `isAdmin`, `tenantId`, `accountBalance`, `createdAt`.
- **Field-level authorization:** người dùng có thể sửa tên nhưng không được gỡ bỏ mã xác minh trong một số trạng thái.
- **Object-level/tenant authorization:** kiểm tra principal và tài nguyên, không tin tenant trong request body.
- **Không rò rỉ dữ liệu:** mã lỗi không được cho biết một ID ở tenant khác có tồn tại hay không.
- **Audit và bảo mật log:** ghi ai đổi trường nào, có yêu cầu clear hay không, nhưng tránh log giá trị cá nhân nhạy cảm không cần thiết.

Ví dụ request:

```json
{
  "phoneNumber": null,
  "isAdmin": true,
  "tenantId": "another-tenant"
}
```

Parser theo allowlist phải từ chối các field bị cấm, và lớp authorization phải kiểm tra quyền xóa điện thoại. **Bảo toàn ý định không đồng nghĩa mọi ý định đều được phép thực hiện.**

## 12. Concurrency: tri-state không thay thế version check

Giả sử khách hàng có `displayName="Minh An"`, `phoneNumber="0901234567"`, `version=7`. Hai người đọc version 7: A sửa tên, B muốn xóa điện thoại.

Tri-state giúp A không xóa nhầm số, B không sửa nhầm tên. Nhưng quyết định của B có thể đã dựa trên trạng thái cũ. Với **optimistic locking**, cập nhật chỉ hợp lệ nếu phiên bản nguồn vẫn đúng:

```sql
UPDATE customer
SET phone_number = NULL,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
  AND version = 7;
```

Nếu A đã commit và tăng version thành 8, lệnh của B không ảnh hưởng hàng nào. API cần có chính sách trả conflict/precondition và cho phép đọc lại trước khi quyết định thao tác mới.

HTTP có thể dùng `If-Match` và ETag:

```http
PATCH /customers/C-101 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "customer-v7"

{"phoneNumber":null}
```

`"customer-v7"` chỉ là giá trị ETag minh họa. Khi dùng `If-Match`, điều kiện phải được kiểm chứng **nguyên tử tại nguồn ghi**, không được chỉ kiểm tra ở controller rồi cập nhật không điều kiện. Nếu các trường độc lập có thể merge an toàn, có thể chọn concurrency theo trường thay vì toàn bản ghi, nhưng phải chứng minh không phá bất biến liên trường.

**Presence trả lời “định sửa trường nào”; version trả lời “dựa trên trạng thái nào”.** Hai yêu cầu này bổ sung, không thay thế nhau.

## 13. Retry và commit outcome chưa rõ

PATCH có thể timeout sau khi database đã commit. Gửi lại có thể gây tăng version hai lần, phát hai event, ghi audit hai lần hoặc trả version conflict dù lần đầu thành công.

Một **idempotency key** nhận diện ý định thao tác, khác `customerId` (danh tính thực thể) và `version` (phiên bản trạng thái). Nếu nghiệp vụ cần kết quả retry ổn định:

1. Client dùng lại cùng key cho cùng ý định.
2. Server gắn key với tenant/principal và dấu vân tay payload.
3. Trạng thái thao tác và kết quả được lưu theo một ranh giới transaction đáng tin cậy.
4. Retry cùng key và payload trả kết quả đã ghi; cùng key khác payload bị từ chối.
5. Khi commit outcome chưa xác định, đối soát key tại nguồn có thẩm quyền trước khi chạy lại.

Không phải mọi PATCH bắt buộc có idempotency key. Nhưng ngay cả phép `SET phone_number = NULL` có vẻ lặp lại an toàn cũng có thể tạo side effect không idempotent trong workflow bên ngoài database.

## 14. Event, cache và đồng bộ từng phần

Producer có thể gửi sự kiện chỉ thay đổi tên:

```json
{
  "eventType": "CustomerPatched",
  "customerId": "C-101",
  "customerVersion": 8,
  "changes": { "displayName": "Minh An Group" }
}
```

Nếu consumer deserialize event vào DTO đầy đủ, `phoneNumber == null` có thể bị hiểu là “xóa số”, làm hỏng read model hoặc cache.

Hãy xác định rõ kiểu event:

| Kiểu | Nội dung | Ý nghĩa của omitted |
| --- | --- | --- |
| **Full-state event** | Trạng thái đầy đủ của thực thể | Thiếu field bắt buộc thường là lỗi schema |
| **Delta/partial-change event** | Chỉ các trường đổi | Không thay đổi thuộc tính không được gửi |
| **Field-mask event** | Danh sách trường đổi và map giá trị | Chỉ áp dụng trường nằm trong mask, kể cả khi giá trị null |

Ví dụ event có mask:

```json
{
  "customerId": "C-101",
  "customerVersion": 9,
  "changedFieldNames": ["phoneNumber"],
  "values": { "phoneNumber": null }
}
```

`changedFieldNames` xác nhận trường được chủ đích đổi, còn `values.phoneNumber` cung cấp giá trị mới. Consumer phải kiểm tra hai phần đồng nhất, loại bỏ sự kiện lặp/cũ theo ID và version, và tránh ghi đè trạng thái mới bằng event đến muộn.

Với Protobuf/gRPC, GraphQL hoặc CSV/ETL, mô hình presence khác nhau. Có trường hợp cần `optional`, `oneof`, wrapper, `FieldMask` hoặc một marker clear; hãy kiểm tra schema và cách codegen/binding thật sự xử lý, không giả định primitive tự giữ đủ ba trạng thái.

## 15. Tiến hóa schema và tương thích client cũ

Giả sử hệ thống thêm `preferredLanguage` và client mới hỗ trợ đổi ngôn ngữ. Client cũ **không gửi trường đó** vì chưa từng biết nó. Nếu server deserialize PATCH thành full DTO với default `"vi"` rồi ghi mọi field, lựa chọn ngôn ngữ trước đó của khách có thể bị reset.

Quy trình triển khai an toàn:

1. Chốt ngữ nghĩa omitted/null/value cho **CREATE, PATCH, full replacement và event** riêng biệt.
2. Bổ sung cột, default, nullability và migration phù hợp.
3. Đảm bảo server giữ presence; không dùng DTO default để suy ra ý định sửa.
4. Triển khai client mới; client cũ không gửi trường mới phải giữ nguyên dữ liệu.
5. Kiểm thử các phiên bản chạy song song, quan sát lỗi và có phương án rollback.

Với import CSV, **thiếu cột** khác với **cột có mặt nhưng ô trống**. Ô trống có thể là chuỗi rỗng, SQL NULL theo quy tắc import hoặc giá trị bị parser tự biến đổi; cần hợp đồng theo phiên bản. Một snapshot đầy đủ và một bản ghi delta không nên dùng cùng logic cập nhật.

## 16. Ma trận kiểm thử absent / null / value

Giả sử bản ghi ban đầu có tên “Minh An”, điện thoại “0901234567”, `marketingOptIn=true` và `version=7`.

| Request PATCH | Kết quả mong đợi |
| --- | --- |
| `{"displayName":"Minh An Group"}` | Chỉ tên thay đổi, giữ điện thoại và marketing |
| `{"phoneNumber":null}` | Điện thoại thành SQL `NULL` |
| `{"phoneNumber":"0987654321"}` | Điện thoại đổi sang giá trị mới |
| `{"phoneNumber":""}` | Không tự coi là omitted; áp dụng policy chuỗi rỗng |
| `{"displayName":null}` | Lỗi vì tên không cho null |
| `{"displayName":""}` | Lỗi vì tên không được rỗng |
| `{"marketingOptIn":false}` | Lưu chính xác false |
| `{"marketingOptIn":null}` | Lỗi vì boolean không cho null |
| `{}` | Bị từ chối theo hợp đồng ví dụ |
| `{"isAdmin":true}` | Từ chối field ngoài allowlist |
| `{"phoneNumber":123}` | Từ chối sai kiểu |
| `{"phoneNumber":null,"displayName":"Tên mới"}` | Cả hai thay đổi commit hoặc cùng rollback |
| PATCH với expected version cũ | Không ghi đè snapshot mới |
| Retry sau timeout | Đối soát, không nhân đôi side effect |
| Client cũ không gửi field mới | Field mới vẫn giữ trạng thái hiện tại |

### Unit test minh họa

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

final class CustomerPatchExamples {
    static void verify() throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        JsonNode missing = mapper.readTree(
                "{\"displayName\":\"Minh An Group\"}");
        CustomerPatch a = CustomerPatchParser.parse(missing);
        if (a.phoneNumber().kind() != ChangeKind.OMITTED) {
            throw new AssertionError("Omitted was lost");
        }

        JsonNode explicitNull = mapper.readTree(
                "{\"phoneNumber\":null}");
        CustomerPatch b = CustomerPatchParser.parse(explicitNull);
        if (b.phoneNumber().kind() != ChangeKind.SET_NULL) {
            throw new AssertionError("Explicit null was lost");
        }

        JsonNode falseValue = mapper.readTree(
                "{\"marketingOptIn\":false}");
        CustomerPatch c = CustomerPatchParser.parse(falseValue);
        if (c.marketingOptIn().kind() != ChangeKind.SET_VALUE
                || !Boolean.FALSE.equals(c.marketingOptIn().value())) {
            throw new AssertionError("False was dropped");
        }
    }
}
```

Unit test cho parser chưa chứng minh SQL cập nhật đúng. Thêm **integration test với DB thật**: đọc `phone_number` sau PATCH omitted để xác nhận không đổi, dùng `IS NULL` sau explicit null, đọc boolean false, kiểm tra version conflict và transaction rollback. Test với mock repository không chứng minh được mức cô lập hay kiểu bind của driver.

## 17. Checklist review PATCH

- Endpoint là `PUT`, `PATCH` riêng, JSON Merge Patch hay JSON Patch?
- Có chính sách cho omitted/null/empty/false/zero của **từng field**?
- DTO/deserializer còn giữ thông tin member có xuất hiện không?
- Nullability DB, validation domain và quyền sửa field có được tách rõ?
- Có allowlist để tránh cập nhật ID, tenant, trường quản trị hoặc field read-only?
- SQL có thể **bỏ qua cột omitted** và **xóa cột khi explicit null**?
- Có dùng sai `COALESCE`, ignore-null mapper, JPA `merge` hoặc primitive default?
- Cập nhật nhiều trường có được bao trong một transaction?
- Có version/ETag khi cần chống stale update?
- Khi commit không rõ kết quả, retry có cơ chế đối soát/idempotency?
- Consumer nhận full-state hay delta; có version/field mask không?
- Client cũ không gửi field mới có giữ nguyên dữ liệu?
- Integration test đã kiểm tra giá trị thực trong DB sau commit chưa?

## 18. Bài tập áp dụng

**Bài tập 1 — nhận dạng ý định.** Khách có tên “Minh An”, điện thoại “0901234567”, marketing true. Request chỉ có `{"displayName":"Minh An Group"}`. Viết ba `FieldChange` và kết quả sau update.

*Gợi ý:* Tên `SET_VALUE`, hai trường còn lại `OMITTED`.

**Bài tập 2 — xóa đúng.** Vì sao `COALESCE(:incoming_phone, phone_number)` không thỏa hợp đồng khi người dùng gửi `{"phoneNumber":null}`? Đề xuất hai cách xử lý khác.

*Gợi ý:* Dùng cờ `phone_present` tách khỏi value hoặc chỉ thêm cột vào SQL `SET` nếu member có mặt.

**Bài tập 3 — default.** Với cột `marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE`, so sánh INSERT bỏ cột, INSERT ghi `NULL` và PATCH bỏ field khi giá trị hiện tại đang true.

*Gợi ý:* INSERT omitted lấy default, explicit NULL vi phạm NOT NULL, PATCH omitted giữ true.

**Bài tập 4 — JSON Patch.** Với target `{"a":1,"b":null}`, merge patch `{"a":null}` có giữ member `a` với JSON null không? Làm sao đặt member đó thành JSON null?

*Gợi ý:* Merge Patch xóa member; JSON Patch `replace` với value null có semantics khác.

**Bài tập 5 — concurrency.** A và B cùng đọc version 7. A sửa tên, B xóa điện thoại. A commit làm version 8, B vẫn gửi expected version 7. Tri-state đúng đã đủ để B ghi ngay chưa?

*Gợi ý:* Chưa; cần quyết định chính sách merge/concurrency, thường là version check nguyên tử và đọc lại.

**Bài tập 6 — sự kiện.** Producer gửi partial event chỉ đổi tên. Consumer ghi đè full object với các field thiếu được deserializer đặt thành null. Điều gì sai?

*Gợi ý:* Những field không đổi có thể bị xóa nhầm; dùng delta có presence/field mask hoặc full-state event hoàn chỉnh.

**Bài tập 7 — phân quyền.** Caller có quyền đổi tên nhưng gửi `{"displayName":"Tên mới","isAdmin":true}`. Tại sao một DTO nhận tùy ý field không an toàn?

*Gợi ý:* Field ngoài allowlist phải bị từ chối; authorization kiểm tra quyền sửa từng field, không chỉ kiểm tra schema.

**Thực hành:** Tạo bảng `customer` ở mục 7 trong PostgreSQL thử nghiệm, dùng `CustomerPatchParser` và `JdbcCustomerPatchWriter`. Gửi các JSON thiếu điện thoại, explicit null, số mới, false, tên null và PATCH rỗng. Sau mỗi lệnh, truy vấn DB để ghi **payload, trạng thái presence, tác động SQL, giá trị trước/sau, version, lỗi và hành động retry**. Thử hai request cùng expected version và thảo luận cách đối soát khi mất phản hồi gần COMMIT.

## Ghi nhớ

**Không gửi trường là không cung cấp chỉ dẫn thay đổi; gửi trường với `null` là một chỉ dẫn rõ ràng, được diễn giải theo hợp đồng.** Với PATCH cần giữ riêng `OMITTED`, `SET_NULL` và `SET_VALUE`, không xem `false`, `0` hay chuỗi rỗng là omitted. JSON/DTO phải bảo toàn presence, domain phải kiểm tra giá trị và quyền sửa, JDBC/ORM chỉ sửa đúng cột được yêu cầu, database và transaction bảo vệ tính nhất quán. Khi dùng Merge Patch, JSON Patch, event từng phần hoặc schema mới, phải công bố rõ semantics và **kiểm chứng bằng đọc lại dữ liệu** để không xóa nhầm dữ liệu đang có hoặc bỏ qua một yêu cầu xóa hợp lệ.



