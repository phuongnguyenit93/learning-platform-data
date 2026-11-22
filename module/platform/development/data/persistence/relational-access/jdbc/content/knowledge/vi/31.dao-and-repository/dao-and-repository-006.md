# Biểu diễn lỗi không tìm thấy, trùng khóa và xung đột cập nhật trong JDBC DAO/Repository

Trong chương **DAO và Repository**, lớp truy cập dữ liệu không chỉ có nhiệm vụ chạy `SELECT`, `INSERT`, `UPDATE` hoặc `DELETE`. Nó còn phải trả lời một câu hỏi quan trọng cho tầng nghiệp vụ: **thao tác không thực hiện được vì lý do gì?** Không tìm thấy bản ghi, vi phạm khóa duy nhất, dữ liệu đã bị người khác sửa, hay hệ thống đang gặp sự cố kết nối là những tình huống khác nhau, không nên bị gom thành một giá trị `false` hoặc một ngoại lệ chung không rõ nguyên nhân.

Ví dụ, API sửa email khách hàng có thể nhận kết quả `UPDATE` bằng 0 dòng vì ID không tồn tại, vì bản ghi thuộc tenant khác hoặc vì `version` người dùng gửi đã cũ. Trong khi đó, một `INSERT` có thể thất bại vì email trùng ràng buộc `UNIQUE`. Nếu repository luôn trả `null` cho mọi lỗi hoặc bắt mọi `SQLException` để trả “không tìm thấy”, ứng dụng có thể hiển thị sai thông báo, retry sai, che khuất lỗi hạ tầng hoặc vô tình làm lộ sự tồn tại của dữ liệu tenant khác.

Bài này thiết kế hợp đồng rõ ràng giữa **DAO/Repository** và tầng service trong ứng dụng JDBC: dùng `Optional` cho truy vấn không thấy bản ghi, phân loại **duplicate key** bằng mã lỗi được driver/DB xác nhận, phát hiện **optimistic locking conflict** qua số dòng cập nhật và cột phiên bản, giữ nguyên những lỗi SQL không thuộc ba nhóm trên, đồng thời xử lý transaction và kiểm thử các nhánh thực tế. Ví dụ dùng `DataSource`, `Connection`, `PreparedStatement` và `ResultSet` theo API JDBC chuẩn; những mã SQLState của PostgreSQL được ghi rõ là **phụ thuộc hệ quản trị**.

## 1. Đừng đồng nhất ba tình huống lỗi

Ba trường hợp thường cần biểu diễn trong một repository:

| Tình huống | Ví dụ | Nguồn tín hiệu phổ biến | Cách phản hồi ở tầng nghiệp vụ |
| --- | --- | --- | --- |
| **Không tìm thấy** (*not found*) | `SELECT` theo ID không trả hàng; `DELETE` không xóa hàng | `ResultSet.next() == false` hoặc `executeUpdate() == 0` với điều kiện phù hợp | Trả kết quả vắng mặt; có thể là HTTP 404 tùy API và chính sách bảo mật |
| **Trùng khóa** (*duplicate key*) | Tạo khách hàng có `(tenant_id,email)` đã tồn tại | DB từ chối `INSERT`/`UPDATE` vì `UNIQUE` hoặc `PRIMARY KEY` | Trả lỗi trùng dữ liệu với mã nghiệp vụ rõ ràng; thường HTTP 409 |
| **Xung đột cập nhật** (*update conflict*) | Hai người cùng đọc `version=5`, người ghi sau dựa trên bản cũ | `UPDATE ... WHERE version=?` tác động 0 hàng | Yêu cầu tải lại dữ liệu và quyết định hợp nhất/thử lại; thường HTTP 409 |

Thực tế còn có lỗi **kết nối, timeout, khóa ngoại, vi phạm `CHECK`, deadlock, lỗi câu SQL và cấu hình driver**. Đây không phải “không tìm thấy” hoặc “trùng khóa”; phải được phân loại riêng hoặc đưa ra kênh lỗi hạ tầng để điều tra.

### Vì sao API trả `boolean` có thể không đủ?

```java
boolean save(Customer customer); // false có nghĩa là gì?
```

Với chữ ký như trên, `false` có thể bị hiểu nhầm là không tìm thấy, xung đột phiên bản hoặc lỗi DB. Thay vào đó, hãy định nghĩa kết quả có tên:

```java
enum CreateOutcome {
    CREATED,
    DUPLICATE_KEY
}

enum UpdateOutcome {
    UPDATED,
    STALE_OR_MISSING,
    DUPLICATE_KEY
}
```

`STALE_OR_MISSING` là trạng thái **có chủ đích**: khi một câu `UPDATE` có cả `id` và `version` ảnh hưởng 0 hàng, thường chưa thể kết luận chính xác bản ghi đã bị xóa hay phiên bản đã thay đổi. Phần 6 sẽ giải thích cách phân biệt khi nghiệp vụ thật sự cần.

Hợp đồng kết quả nên mô tả **sự kiện đã được xác minh**, không mô tả một nguyên nhân do code tự đoán.

## 2. Định nghĩa schema và các bất biến trước khi viết DAO

Giả sử ứng dụng quản lý khách hàng theo tenant trên PostgreSQL:

```sql
-- DDL minh họa theo PostgreSQL, thực thi bằng migration identity.
CREATE SCHEMA app;

CREATE TABLE app.customer (
    id           BIGINT PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    email        VARCHAR(255) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    version      BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_customer_tenant_email UNIQUE (tenant_id, email)
);
```

Ở đây `id` được cung cấp bởi tầng gọi để giữ ví dụ tập trung vào biểu diễn lỗi; trong hệ thống thật có thể dùng `IDENTITY` hoặc generated keys và phải kiểm tra khả năng driver. `tenant_id` là phạm vi phân quyền của từng truy vấn. `version` tăng khi bản ghi được sửa, cho phép phát hiện bản đọc cũ.

Hai ràng buộc quan trọng:

- **`PRIMARY KEY(id)`:** không tồn tại hai khách hàng có cùng ID. Một lỗi trùng khóa có thể xuất phát từ ID, không chỉ từ email.
- **`UNIQUE(tenant_id,email)`:** trong cùng tenant, email không được trùng. Hai tenant khác nhau **có thể** dùng cùng email nếu nghiệp vụ cho phép.

Đừng chỉ viết câu `SELECT` kiểm tra email tồn tại trước khi `INSERT` rồi coi đó là bảo vệ duy nhất. Khi hai transaction chạy đồng thời, cả hai đều có thể thấy “chưa tồn tại” trước khi một trong hai ghi. **Ràng buộc duy nhất ở DB** mới là nguồn xác thực cuối cùng.

### Lịch chạy gây trùng khóa

```text
Transaction A                         Transaction B
-------------                         -------------
SELECT email -> chưa có               SELECT email -> chưa có
INSERT tenant=7,email=x@example.com
                                      INSERT cùng tenant/email
COMMIT thành công                      DB từ chối do UNIQUE
```

Thứ tự thực thi, khóa và thời điểm báo lỗi có thể khác tùy DB/isolation. Nguyên tắc vẫn là: **điều kiện duy nhất phải được DB cưỡng chế**, và DAO cần chuyển lỗi vi phạm đúng loại thành kết quả mà tầng nghiệp vụ hiểu được.

## 3. Không tìm thấy: dùng `Optional` cho truy vấn một hàng

Đối với `SELECT` theo khóa, một hợp đồng dễ hiểu là:

```java
Optional<Customer> findById(long trustedTenantId, long id)
        throws SQLException;
```

`Optional.empty()` nghĩa là **không có hàng phù hợp điều kiện truy vấn** tại thời điểm đọc. Nó không nói rằng DB gặp lỗi, cũng không tự phân biệt ID không tồn tại với ID thuộc tenant khác.

Ví dụ:

```java
String sql = """
        SELECT id, tenant_id, email, display_name, version
        FROM app.customer
        WHERE tenant_id = ? AND id = ?
        """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, trustedTenantId);
    ps.setLong(2, id);

    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            return Optional.empty();
        }
        return Optional.of(new Customer(
                rs.getLong("id"),
                rs.getLong("tenant_id"),
                rs.getString("email"),
                rs.getString("display_name"),
                rs.getLong("version")));
    }
}
```

Đoạn minh họa là **thân phương thức** trong lớp có `dataSource` và các import thích hợp; `Customer` là record được định nghĩa trong ví dụ repository ở phần 5.

**Không dùng `null` hoặc `Optional.empty()` trong `catch(SQLException)`.** Nếu mất kết nối, sai tên bảng hoặc lỗi quyền truy cập xảy ra, caller cần biết rằng truy vấn không hoàn tất chứ không phải “khách hàng không tồn tại”.

Trong hệ thống multi-tenant, `trustedTenantId` phải được lấy từ danh tính đã xác thực ở server, không tin nguyên giá trị client gửi. Trả `Optional.empty()` cho bản ghi tenant khác có thể là lựa chọn bảo mật có chủ đích để không tiết lộ sự tồn tại của đối tượng; chính sách đó cần được thiết kế ở tầng authorization.

## 4. Trùng khóa: đừng kiểm tra bằng chuỗi thông báo lỗi

Trong JDBC, `executeUpdate()` có thể ném `SQLException` khi DB từ chối thao tác vì ràng buộc duy nhất. Những thông tin thường dùng để phân loại:

- `SQLException.getSQLState()`: mã trạng thái SQL; PostgreSQL dùng `23505` cho `unique_violation`.
- `SQLException.getErrorCode()`: mã riêng của nhà cung cấp; chẳng hạn driver MySQL thường báo mã `1062` cho duplicate entry.
- `SQLIntegrityConstraintViolationException`: lớp ngoại lệ cho một số lỗi ràng buộc dữ liệu, nhưng **không** đồng nghĩa với trùng khóa duy nhất; các driver cũng không nhất thiết ném đúng lớp này.
- `SQLException.getNextException()`: các lỗi SQL có thể được xâu chuỗi. Cần duyệt khi driver cung cấp chi tiết dưới dạng chuỗi.

Không viết:

```java
// SAI: thông điệp có thể thay đổi theo DB, driver, phiên bản và ngôn ngữ.
if (error.getMessage().contains("duplicate key")) {
    return CreateOutcome.DUPLICATE_KEY;
}

// SAI: mọi SQLState bắt đầu bằng "23" không phải unique violation.
if (error.getSQLState().startsWith("23")) {
    return CreateOutcome.DUPLICATE_KEY;
}
```

Lớp SQLState `23` biểu thị nhóm **vi phạm tính toàn vẹn**, có thể bao gồm khóa ngoại, `NOT NULL`, `CHECK` và nhiều lỗi khác. Câu `error.getSQLState()` còn có thể trả `null`, nên đoạn so `startsWith` phía trên có thể ném thêm `NullPointerException` và che lỗi ban đầu.

### Bộ phân loại riêng cho PostgreSQL

```java
import java.sql.SQLException;

public final class PostgresSqlErrorClassifier {
    private PostgresSqlErrorClassifier() {}

    public static boolean isUniqueViolation(SQLException failure) {
        for (SQLException current = failure;
             current != null;
             current = current.getNextException()) {
            if ("23505".equals(current.getSQLState())) {
                return true;
            }
        }
        return false;
    }
}
```

Đây là **adapter cho PostgreSQL**, không phải logic khả chuyển tuyệt đối. Khi cần hỗ trợ MySQL, SQL Server hoặc Oracle, viết adapter riêng dựa trên **kết hợp SQLState, vendor code và tài liệu driver đã kiểm chứng**. Không lấy một mã phổ biến ở DB này rồi áp dụng cho mọi DB.

Một điểm quan trọng: `23505` chỉ cho biết **có một ràng buộc duy nhất bị vi phạm**, không cho biết ràng buộc ấy chắc chắn là `uq_customer_tenant_email`. Nếu bảng còn `PRIMARY KEY(id)`, lỗi cũng có thể do ID trùng. Khi nghiệp vụ cần thông báo “email đã tồn tại” thay vì “trùng dữ liệu”, cần nhận diện **tên constraint** qua API/metadata đặc thù nhà cung cấp (nếu hỗ trợ) và đối chiếu với allowlist tên constraint đã định nghĩa. Không đoán tên constraint bằng cách parse `getMessage()`.

## 5. Ví dụ repository: ba kết quả có kiểu và lỗi hạ tầng tách riêng

Repository dưới đây dùng **PostgreSQL** và bảng `app.customer` ở phần 2. Đây là một lớp Java tự chứa, chỉ phụ thuộc các API JDBC chuẩn cùng helper `PostgresSqlErrorClassifier` đã giới thiệu. Kết quả nghiệp vụ được biểu diễn bằng `Optional` hoặc enum; lỗi SQL **không được nhận diện chắc chắn** vẫn được ném ra dưới dạng `SQLException`.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerJdbcRepository {
    public record Customer(
            long id, long tenantId, String email,
            String displayName, long version) {}

    public record NewCustomer(
            long id, long tenantId, String email, String displayName) {}

    public enum CreateOutcome {
        CREATED,
        DUPLICATE_KEY
    }

    public enum UpdateOutcome {
        UPDATED,
        STALE_OR_MISSING,
        DUPLICATE_KEY
    }

    private final DataSource dataSource;

    public CustomerJdbcRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Optional<Customer> findById(long trustedTenantId, long id)
            throws SQLException {
        String sql = """
                SELECT id, tenant_id, email, display_name, version
                FROM app.customer
                WHERE tenant_id = ? AND id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, trustedTenantId);
            ps.setLong(2, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Customer(
                        rs.getLong("id"),
                        rs.getLong("tenant_id"),
                        rs.getString("email"),
                        rs.getString("display_name"),
                        rs.getLong("version")));
            }
        }
    }

    public CreateOutcome create(NewCustomer customer)
            throws SQLException {
        Objects.requireNonNull(customer);
        Objects.requireNonNull(customer.email());
        Objects.requireNonNull(customer.displayName());

        String sql = """
                INSERT INTO app.customer (
                    id, tenant_id, email, display_name, version
                ) VALUES (?, ?, ?, ?, 0)
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, customer.id());
            ps.setLong(2, customer.tenantId());
            ps.setString(3, customer.email());
            ps.setString(4, customer.displayName());
            try {
                int count = ps.executeUpdate();
                if (count != 1) {
                    throw new SQLException(
                            "INSERT phải tác động đúng một dòng: " + count);
                }
                return CreateOutcome.CREATED;
            } catch (SQLException failure) {
                if (PostgresSqlErrorClassifier.isUniqueViolation(failure)) {
                    return CreateOutcome.DUPLICATE_KEY;
                }
                throw failure;
            }
        }
    }

    public UpdateOutcome updateEmail(
            long trustedTenantId,
            long id,
            long expectedVersion,
            String newEmail) throws SQLException {
        Objects.requireNonNull(newEmail);

        String sql = """
                UPDATE app.customer
                SET email = ?, version = version + 1
                WHERE tenant_id = ? AND id = ? AND version = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setString(1, newEmail);
            ps.setLong(2, trustedTenantId);
            ps.setLong(3, id);
            ps.setLong(4, expectedVersion);

            try {
                int count = ps.executeUpdate();
                if (count == 1) {
                    return UpdateOutcome.UPDATED;
                }
                if (count == 0) {
                    return UpdateOutcome.STALE_OR_MISSING;
                }
                throw new SQLException(
                        "UPDATE không được tác động nhiều hơn một dòng");
            } catch (SQLException failure) {
                if (PostgresSqlErrorClassifier.isUniqueViolation(failure)) {
                    return UpdateOutcome.DUPLICATE_KEY;
                }
                throw failure;
            }
        }
    }
}
```

Ví dụ dùng Java 16+ cho `record` và SQL text block; phiên bản Java cũ có thể thay bằng lớp dữ liệu và chuỗi SQL thông thường. `DataSource` trong ví dụ được giả định cấp kết nối mới ở `autoCommit=true`: mỗi `INSERT` hoặc `UPDATE` là **một statement** được DB xử lý theo ranh giới transaction của nó. Khi một nghiệp vụ yêu cầu thêm ghi lịch sử, tạo bản ghi phụ hoặc cập nhật nhiều bảng cùng lúc, tầng service phải sở hữu **một transaction cho tất cả các bước**, không gọi từng phương thức tự mượn kết nối rồi tưởng rằng chúng cùng transaction.

**Giới hạn cố ý của kết quả:**

- `DUPLICATE_KEY` nghĩa là PostgreSQL báo trùng một khóa/unique constraint nào đó. Nó **không khẳng định email đã bị trùng** nếu chưa kiểm tra constraint cụ thể.
- `STALE_OR_MISSING` nghĩa là không có hàng khớp **đồng thời** `tenant_id`, `id` và `expectedVersion` trong lúc cập nhật. Không khẳng định riêng “không tìm thấy” hay “phiên bản cũ”.
- `SQLException` khác vẫn được truyền lên. Không che timeout, sai SQL, lỗi quyền, mất kết nối hoặc lỗi ràng buộc khác dưới một trong hai enum.
- Với `UPDATE`, dù `newEmail` giống email hiện tại, biểu thức `version = version + 1` vẫn tạo thay đổi khi hàng khớp; nhờ đó `count=0` không bị nhầm với “giá trị không đổi” trong cấu hình driver đếm số hàng thực sự thay đổi. Hành vi affected-row vẫn cần được kiểm thử trên DB/driver được chọn.
- Phần ví dụ không tự kiểm tra quyền tenant. `trustedTenantId` phải được lấy từ ngữ cảnh xác thực ở server.

## 6. Xung đột cập nhật: tại sao `UPDATE count = 0` chưa đủ để báo 404?

**Optimistic locking** là chiến lược không giữ khóa trong toàn bộ thời gian người dùng đọc và chỉnh sửa. Khi tải bản ghi, ứng dụng đọc cả `version`; lúc ghi, nó yêu cầu DB chỉ cập nhật nếu phiên bản vẫn đúng:

```sql
SELECT id, email, version
FROM app.customer
WHERE tenant_id = ? AND id = ?;

-- Sau khi người dùng sửa, gửi lại expectedVersion đã đọc:
UPDATE app.customer
SET email = ?, version = version + 1
WHERE tenant_id = ? AND id = ? AND version = ?;
```

Giả sử cả A và B đọc `version=7`:

| Bước | Yêu cầu A | Yêu cầu B | Trạng thái DB |
| --- | --- | --- | --- |
| 1 | `SELECT` → version 7 | | version 7 |
| 2 | | `SELECT` → version 7 | version 7 |
| 3 | `UPDATE ... WHERE version=7` → 1 hàng | | version 8 |
| 4 | | `UPDATE ... WHERE version=7` → 0 hàng | version 8 |

Nếu B cứ dùng `UPDATE ... SET email=? WHERE id=?` mà không kiểm tra phiên bản, B có thể ghi đè email do A vừa sửa. Với điều kiện phiên bản, B nhận được tín hiệu **không áp dụng được thay đổi dựa trên bản cũ**.

Nhưng kết quả 0 hàng cũng có thể đến từ những tình huống sau:

| Tình huống | Kết quả của `UPDATE ... WHERE tenant_id=? AND id=? AND version=?` |
| --- | --- |
| ID không tồn tại | 0 |
| ID tồn tại nhưng thuộc tenant khác | 0 |
| ID đúng tenant nhưng đã bị xóa | 0 |
| ID đúng tenant, version đã tăng | 0 |
| ID đúng tenant, version khớp | Thường 1, nếu SQL/driver và constraint cho phép |

Vì vậy, hợp đồng repository trung thực nên trả **`STALE_OR_MISSING`** hoặc một loại `NOT_APPLIED` tương tự, **không tự động đổi mọi 0 hàng thành 404**.

### Có thể đọc lại để phân biệt không?

Tầng service có thể chạy `findById(...)` sau khi `UPDATE` trả 0:

- Nếu đọc lại thấy bản ghi trong tenant, nhiều khả năng phiên bản đã thay đổi.
- Nếu không thấy, có thể bản ghi đã bị xóa, không tồn tại hoặc không thuộc tenant hiện tại.

Nhưng **đây không phải kết luận nguyên tử tuyệt đối**: một transaction khác có thể xóa hoặc thêm dữ liệu giữa lần `UPDATE` và lần `SELECT` kiểm tra. Nếu nghiệp vụ bắt buộc phân biệt chính xác 404/409 trong cùng một quyết định, cần thiết kế giao dịch, khóa/điều kiện và mức cô lập theo DB; thí dụ khóa hàng bằng `SELECT ... FOR UPDATE` (nếu DB hỗ trợ) trong cùng transaction rồi xác minh bản ghi và phiên bản trước khi ghi. Ngay cả khi đó, phải xét quyền tenant, timeout, deadlock và cách báo lỗi concurrent.

Với API công khai, việc không phân biệt tenant khác và ID không tồn tại đôi khi còn là lựa chọn **an toàn** để tránh rò rỉ thông tin. Không chạy một query không lọc tenant chỉ để tạo thông báo 404/409 “chính xác hơn”.

## 7. Khóa duy nhất và phiên bản có thể xung đột cùng lúc

Hai cơ chế bảo vệ **hai bất biến khác nhau**:

1. `UNIQUE(tenant_id,email)` bảo đảm một email không được gán cho hai hàng khác nhau trong cùng tenant.
2. `WHERE version = ?` bảo đảm thao tác ghi không dựa trên phiên bản cũ của **chính hàng đang sửa**.

Ví dụ, A và B sửa **hai khách hàng khác nhau** để có cùng email. Cả hai có thể có phiên bản khớp, nhưng một câu `UPDATE` vẫn bị DB từ chối vì `UNIQUE`. Trường hợp này là **duplicate key**, không phải optimistic conflict.

Ngược lại, A và B cùng sửa một khách hàng, dùng chung expectedVersion: người đến sau thường nhận `STALE_OR_MISSING` mà không nhất thiết phát sinh lỗi unique.

### Vì sao kiểm tra “email đã tồn tại chưa?” trước khi ghi không đủ?

```java
// Cách kiểm tra trước chỉ phục vụ thông báo sớm:
if (!emailAlreadyExists(tenantId, email)) {
    insertCustomer(tenantId, email);
}
```

Đoạn minh họa có thể gặp **race condition**: một request khác chèn cùng email sau lúc `emailAlreadyExists` trả false. Cần giữ ràng buộc `UNIQUE` trong DB và vẫn xử lý lỗi duplicate khi câu `INSERT/UPDATE` thực sự chạy. Tương tự, đọc `version` trước khi cập nhật mà không đưa `version` vào `WHERE` cũng không bảo vệ khỏi lost update.

**Tránh retry mù quáng:** Khi email đã trùng theo bất biến nghiệp vụ, chạy lại ngay cùng dữ liệu sẽ thường thất bại tiếp. Khi `version` cũ, cần **đọc lại, tính lại quyết định nghiệp vụ và hỏi cách xử lý xung đột nếu cần**, không tự động gửi lại lệnh ghi với dữ liệu cũ.

## 8. Thiết kế hợp đồng trả lỗi từ DAO đến service và HTTP API

Một repository tốt tách ba tầng thông tin:

```text
PostgreSQL / JDBC
   |
   +-- ResultSet không có hàng -------------------> Optional.empty()
   |
   +-- executeUpdate() == 0 khi check version ----> STALE_OR_MISSING
   |
   +-- SQLState 23505 ----------------------------> DUPLICATE_KEY
   |
   +-- SQLException khác ------------------------> kênh lỗi kỹ thuật
                                                      |
                                                      v
DAO/Repository kết quả có nghĩa rõ ràng ---> Service: chính sách nghiệp vụ
                                                      |
                                                      v
                                       API: mã lỗi công khai, thông điệp an toàn
```

Ở tầng service, dùng mã có tên rõ ràng thay vì trả nguyên ngoại lệ JDBC cho HTTP client:

| Tín hiệu repository | Service nên quyết định | HTTP thường dùng (tham khảo) |
| --- | --- | --- |
| `findById` trả `Optional.empty()` | Không thấy bản ghi theo phạm vi quyền đã xét | 404 hoặc cách biểu diễn không lộ tồn tại |
| `create` trả `DUPLICATE_KEY` | Phân loại ràng buộc cụ thể; nếu thật sự trùng nghiệp vụ thì báo conflict | 409; đôi khi 422 theo hợp đồng API |
| `updateEmail` trả `STALE_OR_MISSING` | Tải lại trạng thái hoặc trả conflict tổng quát; chỉ phân biệt 404/409 khi có cơ sở | 409 hoặc 404 theo chính sách |
| `updateEmail` trả `DUPLICATE_KEY` | Thông báo trường duy nhất không hợp lệ khi đã xác định đúng constraint | 409/422 |
| `SQLException` do mất kết nối, timeout | Ghi log có kiểm soát, giám sát, cân nhắc retry có điều kiện | 500/503/504 tùy ngữ cảnh |
| `SQLException` do lỗi SQL, schema, quyền | Lỗi triển khai/vận hành cần xử lý, không báo “không tìm thấy” | 500 và cảnh báo nội bộ |

Ví dụ định dạng lỗi công khai mang mã ổn định:

```json
{
  "code": "CUSTOMER_UPDATE_CONFLICT",
  "message": "Dữ liệu đã thay đổi hoặc không còn khả dụng. Hãy tải lại.",
  "requestId": "example-correlation-id"
}
```

Không trả `SQLException.getMessage()` trực tiếp ra HTTP response: thông điệp driver có thể chứa tên bảng, SQL, giá trị dữ liệu, constraint hoặc thông tin kết nối. Log nội bộ nên lưu correlation ID, tên thao tác, SQLState, vendor code và stack trace có kiểm soát quyền truy cập; cần che dữ liệu cá nhân và credential.

**Có thể chọn kiểu trả khác enum:** Java có thể dùng `sealed interface`/`record` cho các biến thể kết quả có payload, chẳng hạn `Created(id)`, `DuplicateKey(constraintCode)` và `Conflict(currentVersion)`. Chỉ đính kèm `currentVersion` nếu đã đọc nó hợp lệ, đúng tenant và có quyền tiết lộ; đừng dựng một giá trị phiên bản giả từ số dòng cập nhật 0. Quan trọng là caller không phải đoán lỗi từ chuỗi thông báo.

## 9. Lỗi hạ tầng, constraint khác và chính sách retry

JDBC có nhiều lớp ngoại lệ: `SQLIntegrityConstraintViolationException`, `SQLTransientException`, `SQLTransactionRollbackException`, `SQLTimeoutException`... Tuy vậy, mapping thực tế phụ thuộc driver và điều kiện. Không nên viết quy tắc “mọi `SQLException` đều có thể thử lại” hoặc “mọi `SQLIntegrityConstraintViolationException` đều là duplicate key”.

### Những nhóm lỗi cần tách

| Dấu hiệu | Ý nghĩa cần xem xét | Hành động thường phù hợp |
| --- | --- | --- |
| PostgreSQL `23505` | Unique violation | Trả duplicate theo constraint đã xác định, không retry cùng dữ liệu mù quáng |
| PostgreSQL `23503` | Foreign-key violation | Phân biệt tham chiếu không hợp lệ với duplicate |
| PostgreSQL `23502` | Not-null violation | Xem validation hoặc hợp đồng schema |
| PostgreSQL `23514` | Check violation | Xử lý điều kiện bất biến không thỏa |
| PostgreSQL `40001` | Serialization failure | Có thể retry **toàn bộ transaction** theo chính sách |
| PostgreSQL `40P01` | Deadlock detected | Rollback và cân nhắc retry toàn bộ transaction |
| Lỗi mạng/connection/timeout | Kết quả thao tác có thể chưa rõ | Điều tra, cân nhắc idempotency và trạng thái commit |

Các mã PostgreSQL ở bảng chỉ là **ví dụ cho DB cụ thể**. Với DB khác, tra cứu SQLState và mã vendor thực tế, ghi lại trong contract test. Một nhóm SQLState rộng như `23` hoặc `40` có thể dùng để định hướng chẩn đoán, không đủ để quyết định chính sách nghiệp vụ chi tiết.

Để không bỏ qua những lỗi xâu chuỗi:

```java
static void logSqlErrors(SQLException first) {
    for (SQLException current = first;
         current != null;
         current = current.getNextException()) {
        System.err.printf(
                "SQLState=%s vendor=%d type=%s%n",
                current.getSQLState(),
                current.getErrorCode(),
                current.getClass().getSimpleName());
    }
}
```

Mã minh họa không ghi raw SQL và giá trị tham số, nhưng ứng dụng thực tế phải có logger/correlation ID và chính sách kiểm soát log phù hợp. Không cho phép một logger bị lỗi làm che lỗi nghiệp vụ ban đầu.

### Retry phải có điều kiện

- **Optimistic conflict:** không retry nguyên lệnh với `expectedVersion` cũ; phải đọc và tính lại từ dữ liệu mới, có giới hạn số lần hoặc chuyển quyết định cho người dùng.
- **Serialization/deadlock:** nếu DB hủy transaction, có thể thực hiện lại **toàn bộ transaction** với dữ liệu được đọc lại, khi thao tác không tạo side effect ngoài DB chưa được bảo vệ.
- **Duplicate key:** chỉ thử lại khi nghiệp vụ có phương án hợp lệ như chọn khóa/giá trị mới hoặc idempotency key đã được kiểm soát; không thay đổi dữ liệu âm thầm.
- **Mất kết nối khi `commit()`:** có thể không biết transaction đã commit hay chưa. Không tự phát lại lệnh chuyển tiền/tạo đơn khi thiếu khóa chống trùng hoặc truy vấn xác minh trạng thái.

Lưu ý đặc biệt với **PostgreSQL**: sau khi một câu SQL gây lỗi trong transaction thủ công, transaction thường ở trạng thái lỗi cho tới khi `ROLLBACK`. Vì vậy, repository bắt `23505` rồi trả enum **không có nghĩa** service được tiếp tục chạy các statement khác trên cùng transaction như thể chưa xảy ra gì. Nếu cần xử lý lỗi mà vẫn tiếp tục trong cùng transaction, phải thiết kế `Savepoint` hoặc đơn vị công việc thích hợp và kiểm chứng trên DB.

## 10. Quyền sở hữu transaction quyết định cách biểu diễn lỗi

Các phương thức trong `CustomerJdbcRepository` mượn connection riêng cho **một statement**. Mô hình này hợp lý khi thao tác độc lập và `autoCommit=true`, nhưng một nghiệp vụ tạo khách hàng rồi ghi audit event cần **cùng một transaction**:

```text
Service sở hữu transaction
        |
        v
DataSource.getConnection()
        |
        +-- setAutoCommit(false)
        |
        +-- customerDao.insert(connection, ...)
        |
        +-- auditDao.insert(connection, ...)
        |
        +-- commit() nếu mọi bước hợp lệ
        |
        +-- rollback() khi một bước thất bại/xung đột
        |
        v
Connection.close() -> trả về pool
```

DAO nhận `Connection` từ service **không được tự đóng** kết nối đó và không được tự `commit`/`rollback`. Tầng sở hữu transaction quyết định các bước này. Nếu dùng Spring/JTA hoặc transaction manager, không tự thay đổi `autoCommit` hay đóng connection mà framework đang quản lý.

Một mẫu transaction thủ công dành cho một đơn vị công việc nhiều bước:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void runUnitOfWork(DataSource source) throws SQLException {
    try (Connection connection = source.getConnection()) {
        if (!connection.getAutoCommit()) {
            throw new SQLException(
                    "Ví dụ yêu cầu một connection mới ở autoCommit=true");
        }
        connection.setAutoCommit(false);
        boolean transactionEnded = false;

        try {
            // Chạy các thao tác bằng chính connection này.
            // Mỗi DAO nhận connection từ bên ngoài, không tự close/commit.
            performCustomerMutation(connection);
            insertAuditRecord(connection);

            connection.commit();
            transactionEnded = true;
        } catch (SQLException | RuntimeException failure) {
            if (!transactionEnded) {
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;
        } finally {
            if (transactionEnded) {
                connection.setAutoCommit(true);
            }
            // Nếu rollback thất bại, trạng thái DB có thể chưa rõ;
            // không bật autoCommit vì có thể commit ngoài ý muốn.
        }
    }
}
```

`performCustomerMutation` và `insertAuditRecord` trong ví dụ là **các phương thức minh họa** do ứng dụng triển khai. Chúng phải kiểm tra kết quả `INSERT/UPDATE` và ném hoặc báo lỗi để service rollback khi cần. Khi `commit()` ném lỗi do mất kết nối, trạng thái commit có thể không xác định; đây không phải bằng chứng chắc chắn rằng giao dịch chưa ghi dữ liệu.

**Không được trả `DUPLICATE_KEY` như thành công rồi commit audit event của một thao tác thất bại.** Nếu service muốn biến duplicate thành một kết quả nghiệp vụ bình thường, vẫn phải quyết định rollback đơn vị công việc hoặc dùng savepoint đã thiết kế. Quyền sở hữu transaction là một phần của hợp đồng lỗi, không phải chi tiết tùy ý.

## 11. Kiểm thử tích hợp những nhánh không tìm thấy, trùng và stale

Unit test với mock có thể kiểm tra mapper và kết quả enum, nhưng không chứng minh DB báo đúng mã lỗi hoặc `version` cập nhật đúng khi có nhiều connection. Nên có integration test chạy trên **PostgreSQL và driver đúng phiên bản** trong môi trường cô lập.

### Ma trận ca kiểm thử

| Ca | Điều kiện chuẩn bị | Kỳ vọng |
| --- | --- | --- |
| Tìm khách hàng tồn tại | ID và tenant đúng | `Optional.of(Customer)`, email/version đúng |
| Tìm ID không tồn tại | ID chưa có | `Optional.empty()` |
| Tìm ID thuộc tenant khác | ID có thật nhưng tenant sai | `Optional.empty()`, không tiết lộ dữ liệu |
| Tạo khách hàng mới | `(tenant_id,email)` chưa tồn tại | `CREATED`, đọc lại có 1 hàng |
| Tạo trùng khóa chính | Đổi email nhưng giữ nguyên ID | `DUPLICATE_KEY`, dữ liệu cũ không bị ghi đè |
| Tạo trùng email trong cùng tenant | ID mới, email đã có | `DUPLICATE_KEY`, không có hàng mới |
| Cùng email ở tenant khác | ID mới, tenant khác | Thành công nếu schema/authorization cho phép |
| Cập nhật phiên bản đúng | expectedVersion bằng DB | `UPDATED` và `version` tăng 1 |
| Cập nhật với phiên bản cũ | expectedVersion từ bản đọc trước | `STALE_OR_MISSING` và giá trị mới không ghi đè |
| Cập nhật ID không có | ID không tồn tại | `STALE_OR_MISSING` |
| Cập nhật email thành email trùng | Version đúng, email đích đã dùng | `DUPLICATE_KEY`, transaction xử lý theo policy |
| Lỗi schema/quyền/connection | DB từ chối vì lý do khác unique | `SQLException` được giữ nguyên, không biến thành 404 |

### Ví dụ test trạng thái stale bằng JUnit 5

Giả sử test fixture đã tạo `CustomerJdbcRepository dao` và khách hàng `(tenant_id=7, id=42, version=0)`. Test sau kiểm chứng cơ chế bảo vệ **khi dùng lại phiên bản cũ**:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

@Test
void staleVersionDoesNotOverwriteNewerEmail() throws Exception {
    var before = dao.findById(7L, 42L).orElseThrow();
    long oldVersion = before.version();

    assertEquals(
            CustomerJdbcRepository.UpdateOutcome.UPDATED,
            dao.updateEmail(7L, 42L, oldVersion, "first@example.com"));

    assertEquals(
            CustomerJdbcRepository.UpdateOutcome.STALE_OR_MISSING,
            dao.updateEmail(7L, 42L, oldVersion, "second@example.com"));

    var after = dao.findById(7L, 42L).orElseThrow();
    assertEquals("first@example.com", after.email());
    assertEquals(oldVersion + 1, after.version());
}
```

Đây là **phương thức test minh họa**, đặt trong class JUnit 5 có field `dao` và fixture riêng. Hai lần cập nhật tuần tự đã đủ chứng minh câu `WHERE version=?` không chấp nhận một version cũ. Để kiểm chứng cạnh tranh thực sự, cho hai request độc lập đọc cùng phiên bản rồi dùng hai connection/luồng để ghi theo lịch có kiểm soát. Có thể dùng `CountDownLatch` và timeout; không chỉ dựa vào `Thread.sleep` ngẫu nhiên rồi kết luận không có race condition.

### Kiểm thử unique và cách báo lỗi theo driver

Sử dụng hai khách hàng có cùng `tenant_id` và email nhưng ID khác nhau. Lệnh `create` thứ nhất phải thành công; lệnh thứ hai phải trả `DUPLICATE_KEY` qua bộ phân loại PostgreSQL. Tạo tiếp một khách hàng cùng email ở tenant khác để xác minh ràng buộc `UNIQUE(tenant_id,email)` đúng phạm vi. Ngoài ra, cố ý chèn ID trùng với email khác để chứng minh `DUPLICATE_KEY` **không đủ xác định trường bị trùng**.

Test không nên chạy bằng tài khoản quản trị, trừ phần migration/fixture; tài khoản runtime cần có quyền thao tác như production. Dữ liệu test nên được dọn bằng transaction rollback hoặc schema/database cô lập, tránh phụ thuộc các hàng đang dùng bởi test khác. Với PostgreSQL, không nên tiếp tục chạy statement trong cùng transaction sau unique violation mà chưa rollback hoặc xử lý savepoint.

## 12. Lỗi thiết kế thường gặp trong DAO/Repository

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `catch(SQLException) { return null; }` | Che lỗi kết nối/schema thành không tìm thấy | Dùng `Optional.empty()` chỉ khi `ResultSet` thật sự không có hàng |
| `UPDATE` tác động 0 hàng ⇒ luôn 404 | Nhầm optimistic conflict thành không tồn tại | Trả `STALE_OR_MISSING` hoặc kiểm tra thêm theo transaction |
| `SELECT` kiểm tra trùng rồi `INSERT` không bắt lỗi | Race condition giữa hai yêu cầu | Đặt `UNIQUE` trong DB và dịch lỗi đúng loại |
| Coi mọi SQLState `23xxx` là duplicate | Nhầm FK/`NOT NULL`/`CHECK` | Dùng mã đặc thù hoặc adapter từng DB |
| Phân loại lỗi bằng `getMessage().contains(...)` | Dễ hỏng khi đổi ngôn ngữ/phiên bản driver | Dùng SQLState/vendor code/constraint metadata đáng tin |
| Biến mọi `SQLException` thành HTTP 409 | Che timeout, sai SQL và mất kết nối | Phân biệt business outcome với lỗi hạ tầng |
| Không tăng cột `version` ở mọi đường ghi | Optimistic lock có thể không phát hiện thay đổi | Mọi `UPDATE` hợp lệ phải tuân thủ chính sách version |
| Retry nguyên bản ghi cũ khi conflict | Có thể ghi đè thay đổi mới nếu bỏ điều kiện version | Tải lại và tính lại nghiệp vụ, giới hạn retry |
| Trả message SQL nội bộ cho HTTP client | Lộ tên bảng, dữ liệu và thông tin hạ tầng | Mã lỗi công khai an toàn; log bảo mật nội bộ |
| DAO tự close `Connection` nhận từ service | Phá transaction nhiều bước | Tách rõ người sở hữu connection/transaction |
| Bắt `23505` trong transaction rồi chạy tiếp | PostgreSQL có thể giữ transaction ở trạng thái lỗi | Rollback hoặc dùng savepoint thiết kế rõ |
| Test với mock rồi kết luận mapping SQLState đúng | Driver/DB thật có thể trả mã/lớp khác | Integration/contract test trên driver đích |
| Query kiểm tra tenant khác không lọc tenant | Có thể lộ dữ liệu mà client không được phép biết | Kiểm tra authorization và giữ phạm vi tenant |

## 13. Bài thực hành: thiết kế hợp đồng lỗi cho đơn hàng

Cho bảng `orders(id, tenant_id, external_code, status, version)`, trong đó `id` là khóa chính, `(tenant_id, external_code)` là khóa duy nhất và `version` bắt đầu từ 0:

1. Thiết kế `Optional<Order> findById(tenantId,id)`. Phân biệt không có hàng phù hợp với lỗi SQL; bảo đảm tenant lấy từ ngữ cảnh tin cậy.
2. Thiết kế `createOrder(...)` trả `CREATED` hoặc `DUPLICATE_KEY`. Thử cùng `external_code` ở hai tenant và hai mã khác nhau trong cùng tenant.
3. Viết `UPDATE orders SET status=?, version=version+1 WHERE tenant_id=? AND id=? AND version=?`. Khi update count bằng 0, trả kết quả chưa áp dụng có tên rõ ràng, không tự kết luận ID mất.
4. Tạo hai bản đọc cùng `version`, cho request thứ nhất cập nhật thành công, request thứ hai cập nhật với phiên bản cũ. Assert bản ghi mới nhất không bị ghi đè.
5. Cố tình vi phạm `UNIQUE` khi đổi `external_code`, xác nhận đây là duplicate key **khác** stale version.
6. Thử một ràng buộc `CHECK` hoặc khóa ngoại thất bại. Xác nhận classifier không nhận nhầm thành duplicate chỉ vì mã lỗi bắt đầu bằng `23`.
7. Bổ sung câu ghi `order_audit` trong cùng transaction; thử lỗi ở bước thứ hai và xác nhận rollback cả hai bước.
8. Xây bảng ánh xạ kết quả DAO sang mã lỗi API. Không trả raw SQL message; kiểm tra 404/409 không làm lộ sự tồn tại của đơn hàng tenant khác.
9. Ghi lại SQLState/vendor code của DB/driver đang thử, sau đó chạy contract test tương ứng nếu dự án hỗ trợ driver khác.

**Câu hỏi tự kiểm tra:**

- Vì sao `Optional.empty()` khác với bắt `SQLException` rồi trả `null`?
- `UNIQUE(tenant_id,email)` bảo vệ điều gì mà một câu `SELECT` trước `INSERT` không bảo vệ được?
- SQLState `23505` có chứng minh email trùng, hay chỉ chứng minh một ràng buộc unique bị vi phạm?
- Vì sao `UPDATE ... WHERE id=? AND version=?` ảnh hưởng 0 hàng chưa đủ kết luận 404?
- Một lỗi `23505` trong PostgreSQL transaction thủ công ảnh hưởng gì tới statement tiếp theo?
- Khi mất kết nối lúc commit, vì sao không nên retry một lệnh tạo đơn chưa có idempotency?
- Vì sao DAO không được tự đóng `Connection` mà tầng service đã cấp cho một transaction nhiều bước?

**Ghi nhớ:** Trong JDBC DAO/Repository, hãy biểu diễn **không tìm thấy** bằng một kết quả vắng mặt có chủ đích như `Optional.empty()`; **trùng khóa** bằng tín hiệu ràng buộc duy nhất do DB xác nhận và bộ phân loại lỗi đúng driver; **xung đột cập nhật** bằng kiểm tra phiên bản trong `WHERE` cùng số hàng bị ảnh hưởng. Không gộp những tình huống ấy với `SQLException` về kết nối, SQL hay transaction. Kết quả có tên rõ ràng, quyền sở hữu transaction và integration test trên DB thật giúp service đưa ra phản hồi đúng mà không làm mất dữ liệu hoặc che giấu sự cố.
