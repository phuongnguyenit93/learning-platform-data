# Thiết kế quyền cơ sở dữ liệu theo nhu cầu tối thiểu trong JDBC

Trong chương **Bảo mật truy cập**, ứng dụng Java dùng JDBC không chỉ cần ngăn SQL injection bằng `PreparedStatement` mà còn phải giới hạn **tài khoản cơ sở dữ liệu có quyền làm những gì**. Nếu tài khoản của API tra cứu khách hàng được cấp quyền sửa mọi bảng, tạo schema hoặc xóa dữ liệu, một lỗi lập trình hay tài khoản bị lộ có thể gây thiệt hại vượt xa chức năng mà API cần thực hiện.

**Nguyên tắc quyền tối thiểu (*least privilege*)**: mỗi danh tính truy cập DB chỉ được cấp các quyền cần để thực hiện những thao tác đã được phê duyệt, trên đúng đối tượng dữ liệu và trong đúng môi trường. Quyền không cần thiết phải được loại bỏ; không dùng tài khoản quản trị hoặc tài khoản sở hữu schema cho công việc CRUD thông thường.

Bài này hướng dẫn xây dựng ma trận quyền từ yêu cầu nghiệp vụ, tách vai trò runtime/migration/reporting, minh họa `GRANT`/`REVOKE` bằng PostgreSQL, kết hợp `DataSource`, `Connection` và `PreparedStatement`, rồi kiểm thử bằng chính tài khoản của ứng dụng. Đồng thời phân biệt **quyền ở DB**, **phân quyền người dùng trong ứng dụng** và **gợi ý `Connection.setReadOnly(true)`** để không nhầm chúng thành một cơ chế bảo vệ duy nhất.

## 1. Quyền tối thiểu bảo vệ trước điều gì?

Giả sử hệ thống có các chức năng:

- API xem thông tin và cập nhật email khách hàng.
- Tác vụ xuất báo cáo chỉ đọc một số trường của khách hàng.
- Công cụ migration tạo bảng, index và thay đổi schema khi triển khai phiên bản mới.

Nếu ba chức năng dùng chung một tài khoản có quyền sở hữu toàn bộ database, một câu SQL ngoài ý muốn ở tác vụ báo cáo cũng có thể `UPDATE` hoặc `DELETE` bảng nghiệp vụ. Khi tài khoản runtime bị lộ, kẻ tấn công có thể tận dụng cả quyền tạo đối tượng hoặc sửa schema dù endpoint bình thường không làm những việc ấy.

Mô hình nên phân lớp:

```text
Người dùng / dịch vụ gọi API
             |
             v
Xác thực + kiểm tra quyền ở tầng ứng dụng
             |
             v
Repository JDBC -> DataSource -> tài khoản DB của workload
                                      |
                                      v
                         Quyền được DB cưỡng chế
                         trên schema / bảng / cột / hàng

Pipeline triển khai riêng -> danh tính migration -> DDL theo kiểm soát
```

**Phạm vi bảo vệ khác nhau:**

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Phân quyền ứng dụng | Người dùng A có được sửa khách hàng B không? | Xác thực, kiểm tra tenant, role nghiệp vụ |
| Quyền DB | Tài khoản JDBC có được `DELETE` bảng `customer` không? | `GRANT SELECT`, `GRANT UPDATE`, `REVOKE DELETE` |
| Chính sách hàng của DB | Tài khoản này được đọc những hàng nào? | Row-level security (RLS), view có chính sách |
| Bí mật/kết nối | Ai có thể lấy credential và kết nối DB? | Secret manager, TLS, mạng riêng, tài khoản riêng |

Một lớp không thay thế các lớp còn lại. `PreparedStatement` giúp tham số hóa giá trị SQL, nhưng **không thu hẹp quyền của tài khoản đã kết nối**. Ngược lại, quyền DB tối thiểu vẫn không thay cho xác thực và kiểm tra quyền nghiệp vụ tại API.

## 2. Bắt đầu bằng ma trận thao tác – đối tượng – phạm vi

Trước khi viết `GRANT`, hãy kiểm kê **SQL thực sự được chạy** trong từng workload. Với mỗi câu lệnh, xác định:

1. Bảng, view, sequence hoặc procedure được truy cập.
2. Thao tác `SELECT`, `INSERT`, `UPDATE`, `DELETE` hay gọi routine.
3. Cột cần đọc, cột cần ghi; kể cả cột nằm trong `WHERE`, `JOIN` và `RETURNING`.
4. Phạm vi tenant/hàng; quyền nào do DB cưỡng chế, quyền nào hiện do ứng dụng đảm nhiệm.
5. Danh tính nào đang chạy: API, worker, báo cáo, migration hoặc quản trị.

Ví dụ ma trận quyền:

| Workload | Bảng/cột cần đọc | Quyền ghi cần có | Không cần |
| --- | --- | --- | --- |
| `customer-api` | `customer.id`, `tenant_id`, `email`, `status` | `INSERT(tenant_id,email,status)`; `UPDATE(email,status)` | `DELETE`, sửa `credit_limit`, `ALTER TABLE` |
| `customer-report` | `id`, `tenant_id`, `status` | Không có | `INSERT`, `UPDATE`, `DELETE`, đọc `email`/`credit_limit` |
| `schema-migration` | Metadata/schema cần thay đổi | `CREATE`, `ALTER`, `DROP` theo quy trình | Không dùng làm tài khoản HTTP runtime |
| `support-tool` | View đã lọc/ẩn trường nhạy cảm | Theo nhu cầu và phê duyệt | Quyền đọc tất cả cột của bảng gốc |

Ma trận chỉ là ví dụ: trong hệ thống thật, từng quyền phải xuất phát từ code, yêu cầu vận hành và quy định dữ liệu. Nếu API thực sự cần xóa khách hàng, hãy thiết kế một đường xóa có kiểm soát hoặc một danh tính riêng, **không ngầm mở `DELETE` cho mọi workload**.

**Nguyên tắc quan trọng:** Đừng cấp `SELECT *` chỉ vì một repository hiện tại dùng câu `SELECT * FROM customer`. Hãy sửa SQL để chỉ chọn cột cần thiết, rồi cấp quyền tương ứng; thiết kế quyền và thiết kế truy vấn cần hỗ trợ nhau.

## 3. Tách vai trò runtime, reporting và migration

Một kiến trúc thực tế nên có danh tính DB riêng theo **mục đích hoạt động**:

- **Runtime role/account:** thực thi CRUD đã được phê duyệt; không sở hữu bảng, không có quyền DDL, không tự cấp quyền cho tài khoản khác.
- **Read-only/reporting role/account:** chỉ truy cập bảng/view và cột phục vụ báo cáo; không có quyền ghi dữ liệu.
- **Migration/DDL identity:** dùng bởi pipeline triển khai được kiểm soát; có quyền thay đổi schema theo phạm vi, không được dùng làm credential của API.
- **Admin/backup/monitoring identity:** tách riêng theo trách nhiệm; đặc quyền cao phải có kiểm soát truy cập, log và thời hạn sử dụng phù hợp.

Nếu database hỗ trợ role nhóm và tài khoản đăng nhập tách rời, có thể cấp quyền cho role **không đăng nhập**, rồi cho tài khoản runtime làm thành viên:

```text
           customer_access_role (không đăng nhập)
             /                         \
            / GRANT cho thành viên      \ quyền SELECT/INSERT/UPDATE
           v                             v
      customer_api_login           app.customer

        migration_login -------> sở hữu/migration schema
        report_login ----------> role chỉ có quyền đọc
```

Mối quan hệ role membership, quyền kế thừa, mặc định `PUBLIC` và cú pháp quản lý role khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle... **Không mang nguyên câu SQL quản lý role từ DB này sang DB khác**. Mỗi hệ quản trị cần một chính sách quyền đã kiểm thử thực tế.

Tránh chia sẻ credential giữa các môi trường phát triển, staging và production. Một tài khoản bị lộ ở test không được trở thành đường truy cập production.

## 4. Ví dụ PostgreSQL: cấp đúng quyền cần cho API khách hàng

Để minh họa, giả sử migration đã tạo schema và bảng:

```sql
-- Ví dụ theo PostgreSQL, chạy bằng danh tính migration/owner,
-- KHÔNG chạy bằng tài khoản ứng dụng thông thường.
CREATE SCHEMA app;

CREATE TABLE app.customer (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    email        TEXT NOT NULL,
    status       TEXT NOT NULL,
    credit_limit NUMERIC(12, 2) NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, email)
);
```

Nghiệp vụ API chỉ cần xem `id`/`email`/`status` và tạo hoặc cập nhật khách hàng trong tenant tương ứng. Nó **không** được đọc/sửa `credit_limit`, không xóa bản ghi và không sửa cấu trúc bảng.

Ví dụ chính sách quyền:

```sql
-- PostgreSQL: chạy bằng tài khoản quản trị/owner có quyền CREATE ROLE
-- và GRANT trên các đối tượng liên quan.
CREATE ROLE customer_access NOLOGIN;
CREATE ROLE customer_api LOGIN;

-- Tên database 'appdb' là ví dụ, thay bằng tên thật khi triển khai.
GRANT CONNECT ON DATABASE appdb TO customer_api;

-- USAGE cho phép tìm tên đối tượng trong schema, không tự cho SELECT.
GRANT USAGE ON SCHEMA app TO customer_access;

-- Chỉ đọc đúng bốn cột cần thiết:
GRANT SELECT (id, tenant_id, email, status)
    ON TABLE app.customer TO customer_access;

-- Chỉ chèn những cột thuộc chức năng:
GRANT INSERT (tenant_id, email, status)
    ON TABLE app.customer TO customer_access;

-- Chỉ cập nhật email và trạng thái:
GRANT UPDATE (email, status)
    ON TABLE app.customer TO customer_access;

-- Cho phép tài khoản đăng nhập sử dụng quyền qua role nhóm.
GRANT customer_access TO customer_api;
```

Tài khoản `customer_api` cần được cấu hình xác thực một cách an toàn bởi hệ thống cấp phát danh tính/secret manager. **Không đặt mật khẩu DB trực tiếp trong file SQL, source code hoặc commit Git.** Ví dụ `CREATE ROLE ... LOGIN` cố ý không minh họa secret; cơ chế xác thực thực tế phải được thiết lập và xác minh khi triển khai.

Điểm cần hiểu:

- `GRANT USAGE ON SCHEMA` cho phép truy cập tên đối tượng trong schema theo quyền của vai trò; tự nó không cấp `SELECT` hay `INSERT` trên bảng.
- `GRANT SELECT (id, tenant_id, email, status)` là quyền đọc theo **cột**. `SELECT *` sẽ bao gồm `credit_limit` và có thể bị DB từ chối, đó là hành vi mong muốn.
- `INSERT` không cho phép tự đặt `id` vì cột đó không nằm trong danh sách được cấp. Với cột `IDENTITY` ở ví dụ PostgreSQL, việc tạo giá trị mặc định có quy tắc khác với một cột `BIGSERIAL` dùng sequence gọi trực tiếp; nếu schema dùng `SERIAL`/`nextval(...)`, có thể phải cấp thêm quyền sequence phù hợp, nhưng không cấp `USAGE ON ALL SEQUENCES` một cách mặc định.
- `UPDATE (email,status)` không cho phép sửa `credit_limit`. Câu lệnh `UPDATE` dùng điều kiện `WHERE id = ? AND tenant_id = ?` còn cần quyền `SELECT` trên các cột tham chiếu; quyền đọc ấy đã nằm trong ví dụ.
- Không cấp `DELETE`, `TRUNCATE`, `CREATE` hoặc quyền sở hữu bảng cho runtime. Một lỗi gọi `DELETE` phải bị DB chặn thay vì chỉ được ngăn bằng code review.

**Cảnh báo về mặc định:** Trong PostgreSQL, quyền có thể đến từ nhiều nguồn (role membership, quyền đã cấp từ trước, `PUBLIC`, quyền sở hữu, superuser...). Những lệnh `GRANT` trên **không tự thu hồi** quyền rộng mà vai trò đã có từ nguồn khác, và `GRANT CONNECT` không có nghĩa chỉ `customer_api` được kết nối. Hãy kiểm tra quyền hiệu dụng và quyền mặc định trên môi trường thật; chỉ thực hiện `REVOKE` diện rộng sau khi đánh giá tác động tới các ứng dụng khác.

## 5. Khi nào dùng `REVOKE` và tại sao không đủ nếu chỉ nhìn `GRANT`?

`REVOKE` thu hồi một quyền đã cấp theo cú pháp/hệ quản trị, nhưng quyền hiệu dụng có thể vẫn còn qua role khác, `PUBLIC` hoặc quyền sở hữu đối tượng. Một ví dụ PostgreSQL:

```sql
-- Chỉ minh họa: cần chạy bởi người có quyền quản trị grant.
REVOKE DELETE ON TABLE app.customer FROM customer_access;

-- Rà soát quyền phát sinh từ PUBLIC (nếu có) trước khi áp dụng:
-- REVOKE ... FROM PUBLIC;
```

Nếu `customer_access` chưa từng được cấp `DELETE`, `REVOKE` không thay đổi gì. Nếu `customer_api` còn là thành viên của một role khác có `DELETE`, câu lệnh trên **không đủ** để chặn xóa. Nếu nó là chủ sở hữu bảng hoặc tài khoản đặc quyền cao, nhiều giới hạn quyền thông thường không áp dụng như mong đợi.

**Thiết kế đúng** là tạo danh tính runtime ít đặc quyền từ đầu và kiểm tra đường kế thừa, thay vì lấy tài khoản admin rồi liên tục thu hồi từng quyền. Khi nâng cấp hệ thống, quy trình kiểm soát thay đổi phải xem lại cả `GRANT` mới và membership mới.

### Quyền trên đối tượng mới

Migration tạo bảng mới không đồng nghĩa runtime tự có quyền truy cập bảng ấy. Tùy DB và cấu hình mặc định, những quyền mới có thể cần được cấp trong migration. PostgreSQL có `ALTER DEFAULT PRIVILEGES` để định nghĩa quyền mặc định cho đối tượng tương lai do một role tạo ra, nhưng cấp quyền mặc định quá rộng cho mọi bảng mới dễ vi phạm least privilege.

Với hệ thống cần quyền đến cấp cột, cách dễ kiểm toán thường là **mỗi migration khai báo các `GRANT` cụ thể của đối tượng mới**, rồi chạy test xác thực. Tránh dùng `GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ...` như cách sửa nhanh khi một màn hình bị từ chối truy cập.

## 6. JDBC vẫn phải dùng SQL tham số hóa và đúng ngữ cảnh tenant

Quyền DB bảo vệ ranh giới đối tượng và cột; ứng dụng vẫn phải lọc đúng khách hàng/tenant theo **danh tính đã được xác thực**, không lấy `tenantId` tùy ý từ request rồi tin rằng người gọi có quyền.

Repository sau dùng `DataSource` với **credential runtime ít đặc quyền**, chỉ yêu cầu những cột đã được `GRANT SELECT`. Câu SQL đặt schema rõ ràng và bind giá trị bằng dấu `?`.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource runtimeDataSource;

    public CustomerRepository(DataSource runtimeDataSource) {
        this.runtimeDataSource = Objects.requireNonNull(runtimeDataSource);
    }

    public record Customer(long id, String email, String status) {}

    public Optional<Customer> findById(long trustedTenantId, long id)
            throws SQLException {
        String sql = """
                SELECT id, email, status
                FROM app.customer
                WHERE tenant_id = ? AND id = ?
                """;

        try (Connection connection = runtimeDataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, trustedTenantId);
            ps.setLong(2, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Customer(
                        rs.getLong("id"),
                        rs.getString("email"),
                        rs.getString("status")));
            }
        }
    }

    public boolean updateEmail(
            long trustedTenantId, long id, String newEmail)
            throws SQLException {
        Objects.requireNonNull(newEmail, "newEmail");
        String sql = """
                UPDATE app.customer
                SET email = ?
                WHERE tenant_id = ? AND id = ?
                """;

        try (Connection connection = runtimeDataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setString(1, newEmail);
            ps.setLong(2, trustedTenantId);
            ps.setLong(3, id);
            int updated = ps.executeUpdate();
            if (updated > 1) {
                throw new SQLException(
                        "UPDATE không được ảnh hưởng hơn một khách hàng");
            }
            return updated == 1;
        }
    }
}
```

Ví dụ dùng Java 16+ (`record` và SQL text block), và giả định `DataSource` đã được cấu hình ở tầng hạ tầng với tài khoản `customer_api`. Code **không tự đổi thành tài khoản admin** khi gặp lỗi quyền. `trustedTenantId` phải được xác định từ danh tính/ủy quyền ở server; nếu nhận thẳng từ tham số do client có thể sửa, điều kiện `WHERE tenant_id = ?` không tự tạo ranh giới tenant an toàn.

**Không sử dụng `SELECT *`** trong code này: ngoài tốn dữ liệu, thao tác còn yêu cầu đọc `credit_limit` mà role runtime cố ý không có. `ResultSet` chỉ lấy các cột được phép, kết nối và statement được đóng bằng `try-with-resources`.

Nếu cần cập nhật nhiều bảng trong cùng một nghiệp vụ, tầng sở hữu transaction phải dùng **một `Connection`** phù hợp quyền và quản lý `commit`/`rollback`. Không gộp hai `DataSource` có mức đặc quyền khác nhau vào một transaction một cách tự phát; cần thiết kế quy trình rõ ràng cho đơn vị công việc đó.

## 7. Quyền bảng/cột không tự phân tách dữ liệu theo tenant

Với SQL `GRANT SELECT ... ON app.customer` ở trên, DB cho phép tài khoản runtime đọc các **cột được cấp trên mọi hàng** của bảng, trừ khi còn có cơ chế ràng buộc hàng. Nếu một developer quên `WHERE tenant_id = ?`, DB vẫn có thể trả dữ liệu của tenant khác.

Ba lớp bảo vệ thường được dùng cùng nhau:

| Lớp | Ví dụ | Giới hạn |
| --- | --- | --- |
| Authorization trong ứng dụng | Xác thực token, suy ra tenant, bind `WHERE tenant_id = ?` | Lỗi code/endpoint có thể bỏ sót điều kiện |
| View hoặc routine đã hạn chế tập hàng | Chỉ cấp `SELECT` trên view được thiết kế kiểm soát | Phải phân tích security context và quyền truy cập bảng gốc |
| Row-level security (RLS) nếu DB hỗ trợ | Chính sách DB áp dụng theo danh tính/ngữ cảnh | Cần hiểu owner bypass, đặc quyền và cách cấp ngữ cảnh tin cậy |

PostgreSQL hỗ trợ **row-level security** với chính sách `USING`/`WITH CHECK`; các DB khác có cơ chế tương đương hoặc giải pháp khác. RLS có thể giảm hậu quả khi repository quên điều kiện tenant, nhưng thiết kế đúng cần xác định **nguồn danh tính tenant mà DB có thể tin cậy**.

Ví dụ ý tưởng của chính sách:

```text
SELECT/UPDATE:
    chỉ nhìn và thao tác hàng có tenant_id = tenant hiện hành tin cậy

INSERT:
    chỉ được tạo hàng có tenant_id = tenant được phép
```

**Cảnh báo quan trọng:** Nếu RLS lấy tenant từ một biến session mà chính tài khoản runtime có thể sửa tùy ý, chỉ gọi `SET app.tenant_id = ?` không mặc nhiên là một ranh giới chống kẻ tấn công chiếm được tài khoản đó. Cần đánh giá mô hình đe dọa, cách cấp danh tính, quyền `SET`, vai trò owner/superuser và các lối bypass theo tài liệu DB. Tenant isolation cũng phải được kiểm thử trên **cùng driver/pool/cách quản lý transaction** như production.

Nếu hệ thống dùng tài khoản DB khác nhau cho mỗi tenant hoặc mô hình database/schema riêng, chi phí vận hành và connection pool tăng nhưng ranh giới quyền có thể khác. Quyết định phải dựa trên yêu cầu bảo mật và quy mô, không chỉ vào việc viết được một `WHERE`.

## 8. `setReadOnly(true)` và `PreparedStatement` không thay `GRANT`

Hai nhầm lẫn dễ dẫn đến thiết kế kém an toàn:

### Nhầm JDBC read-only hint với tài khoản chỉ đọc

```java
try (Connection connection = reportingDataSource.getConnection()) {
    connection.setReadOnly(true);
    // Đây là gợi ý JDBC cho driver/DB, không phải cơ chế phân quyền.
}
```

`Connection.setReadOnly(true)` là **gợi ý về ý định chỉ đọc** và có thể kích hoạt tối ưu hoặc chế độ read-only ở driver/DB. Chuẩn JDBC **không bảo đảm** mọi lệnh ghi đều bị chặn. Một báo cáo tuyệt đối không được thay đổi dữ liệu cần dùng **tài khoản có quyền đọc thật ở DB**, không chỉ cờ `readOnly`.

### Nhầm tham số hóa SQL với phân quyền

`PreparedStatement` ngăn dữ liệu tham số bị diễn giải như một phần cú pháp SQL trong các vị trí bind hợp lệ. Nó **không chặn** một câu `DELETE` được lập trình sẵn nếu tài khoản có quyền xóa. Vì vậy:

```java
// Vẫn là SQL có tham số, nhưng phải bị DB từ chối nếu role không có DELETE.
try (PreparedStatement ps = connection.prepareStatement(
        "DELETE FROM app.customer WHERE id = ?")) {
    ps.setLong(1, customerId);
    ps.executeUpdate();
}
```

Đoạn minh họa trên **không được chạy trên dữ liệu production** để kiểm tra quyền. Nếu cần negative test, dùng môi trường kiểm thử cô lập và rollback. Nó cũng chứng minh tại sao **không cấp quyền thừa**: SQL injection được phòng ở lớp tham số không bảo vệ trước một đường code nguy hiểm có chủ đích hoặc lỗi nghiệp vụ.

Tên bảng, tên cột hoặc chuỗi `ORDER BY` **không thể bind bằng `?`** của JDBC chuẩn. Nếu một API hỗ trợ chọn cột sắp xếp, cần ánh xạ giá trị người dùng sang **allowlist** các biểu thức SQL do ứng dụng định nghĩa; không nối raw identifier từ request, và không để user chọn role DB tùy ý.

## 9. Quản lý credential và connection pool theo mức đặc quyền

`DataSource` là ranh giới ứng dụng sử dụng để mượn kết nối. Thực tế, ứng dụng có thể cấu hình các `DataSource` khác nhau cho workload khác nhau:

```text
customerApiDataSource   --> customer_api_login   --> SELECT/INSERT/UPDATE giới hạn
reportingDataSource     --> report_login         --> SELECT qua bảng/view đã duyệt
migration pipeline      --> migration_login      --> DDL theo quy trình triển khai
```

**Không** tạo một pool duy nhất bằng tài khoản admin rồi đổi role theo từng request để “đỡ tốn kết nối”. Trạng thái session có thể bị giữ lại trong kết nối tái sử dụng; nếu không được reset chính xác, request sau có thể thừa hưởng role, schema, transaction hoặc ngữ cảnh tenant của request trước.

Nguyên tắc vận hành:

1. Credential ở **secret manager** hoặc cơ chế cung cấp bí mật của hạ tầng; không hard-code trong Java, file cấu hình công khai hay test log.
2. Nếu hỗ trợ, dùng **TLS kết nối DB** và cấu hình xác minh certificate/hostname phù hợp với driver, không tắt kiểm tra TLS chỉ để “cho kết nối thành công”.
3. Phân tách tài khoản production/staging/dev, giữa API/reporting/migration, và giữa workload có nhu cầu dữ liệu khác nhau.
4. Pool được cấu hình với số kết nối và quyền phù hợp; dùng `try-with-resources` để trả connection đúng hạn.
5. Khi **xoay vòng secret/thu hồi quyền**, lên kế hoạch refresh hoặc tạo lại các connection vật lý đang tồn tại theo cơ chế pool. Một kết nối đã xác thực có thể tiếp tục tồn tại cho đến khi bị thay thế; thời điểm quyền mới có hiệu lực cần kiểm chứng trên DB.
6. Không ghi credential, SQL chứa giá trị nhạy cảm hoặc thông tin khách hàng vào stack trace/log chẩn đoán pool.
7. Nếu phải dùng `SET ROLE`, `setSchema(...)` hoặc biến session, phải có thiết kế reset/transaction boundary riêng, test cả nhánh lỗi và kiểm tra quyền hiệu dụng sau khi trả rồi mượn lại connection.

**`Connection.setSchema(...)` không phải một thao tác cấp hoặc thu hồi quyền.** Nó đổi ngữ cảnh phân giải tên bảng (nếu driver hỗ trợ), không làm tài khoản mất quyền đã được DB cấp ở schema khác. Để tránh trỏ nhầm đối tượng, SQL nghiệp vụ quan trọng nên dùng tên schema rõ ràng hoặc chính sách `search_path` an toàn đã kiểm chứng.

## 10. Kiểm tra quyền hiệu dụng, không chỉ đọc file migration

Với PostgreSQL, có thể hỏi quyền bằng những hàm catalog như:

```sql
SELECT
    current_user,
    session_user,
    has_table_privilege(
        current_user, 'app.customer', 'DELETE') AS can_delete_customer,
    has_column_privilege(
        current_user, 'app.customer', 'email', 'UPDATE') AS can_update_email,
    has_column_privilege(
        current_user, 'app.customer', 'credit_limit', 'SELECT')
        AS can_read_credit_limit;
```

Mong đợi với tài khoản runtime của ví dụ: `can_delete_customer = false`, `can_update_email = true`, `can_read_credit_limit = false`. Đây là **cú pháp riêng của PostgreSQL**, không phải câu SQL khả chuyển giữa các DB.

Đồng thời, nên có kiểm thử tích hợp **đăng nhập bằng đúng credential của `DataSource` production-like** rồi thử:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| `SELECT id,email,status` trong `app.customer` | Thành công |
| `UPDATE email WHERE tenant_id = ? AND id = ?` trên fixture hợp lệ | Thành công khi thỏa điều kiện |
| `INSERT(tenant_id,email,status)` | Thành công, tạo ID theo schema |
| `SELECT credit_limit FROM app.customer` | Bị DB từ chối |
| `UPDATE app.customer SET credit_limit = ...` | Bị DB từ chối |
| `DELETE FROM app.customer ...` | Bị DB từ chối |
| `CREATE TABLE app.some_table ...` | Bị DB từ chối |
| Role báo cáo thực thi `INSERT` hoặc `UPDATE` | Bị DB từ chối |
| API dùng tenant khác với quyền người gọi | Bị từ chối/không trả dữ liệu theo chính sách ứng dụng và DB |

Các negative test phải chạy trong **test database cô lập**, không phải trên bảng production. Test cần phân biệt bị từ chối do **quyền DB** với việc câu SQL không khớp hàng hoặc sai cú pháp. Một `UPDATE` trả `0` hàng không chứng minh vai trò đã bị cấm cập nhật; và một `SQLException` bất kỳ không chứng minh lỗi quyền nếu SQLState/vendor code thuộc lỗi khác.

Trong JDBC có thể ghi `SQLException.getSQLState()`, `getErrorCode()` và thông tin driver/DB để điều tra, nhưng không hard-code duy nhất một mã lỗi cho mọi hệ quản trị:

```java
try {
    repository.updateEmail(trustedTenantId, customerId, newEmail);
} catch (SQLException error) {
    System.err.printf("SQLState=%s, vendorCode=%d%n",
            error.getSQLState(), error.getErrorCode());
    throw error; // Tầng trên quyết định cách chuyển thành lỗi nghiệp vụ.
}
```

Đoạn này giả định biến `repository`, `trustedTenantId`, `customerId` và `newEmail` đã tồn tại. Trong ứng dụng thực tế, không trả nguyên SQL exception hoặc thông tin cấu trúc DB cho người gọi HTTP; log có kiểm soát và ánh xạ thành thông báo không tiết lộ chi tiết nhạy cảm.

## 11. Rủi ro vòng đời quyền khi schema và code thay đổi

Quyền tối thiểu không phải nhiệm vụ làm một lần khi tạo database. Những thay đổi sau có thể làm mô hình quyền lệch khỏi thực tế:

- **Migration thêm cột nhạy cảm:** câu `SELECT *` của một role có `SELECT` toàn bảng sẽ đọc thêm cột mới. Quyền theo cột hoặc view cho phép giới hạn rõ hơn, nhưng cần test khi schema thay đổi.
- **Migration tạo bảng mới:** pipeline cần cấp quyền đúng cho workload sử dụng; không mặc định cấp `ALL` cho toàn schema.
- **Tác vụ mới dùng chung tài khoản API:** nhu cầu của một job có thể làm role chung dần có quá nhiều quyền. Cân nhắc danh tính riêng thay vì tăng quyền cho tất cả dịch vụ.
- **Role membership đổi:** quyền có thể mở rộng qua role cha hoặc `PUBLIC` dù script `GRANT` riêng không đổi.
- **Xóa tính năng:** cần thu hồi quyền và credential không còn cần thiết, thay vì để lại nhiều tài khoản ít được kiểm soát.
- **Nâng cấp DB/driver/pool:** thay đổi ngữ nghĩa session, auth, role hoặc cách reset connection có thể ảnh hưởng ranh giới bảo vệ.
- **Incident response:** khi thu hồi credential phải cân nhắc connection còn tồn tại, secret rotation, log truy cập và các đối tượng đã bị sửa; chỉ sửa chuỗi cấu hình chưa chắc đủ.

Một quy trình thay đổi tốt gồm **review ma trận quyền → migration quyền theo đối tượng → test thành công/thất bại → kiểm tra runtime thật → giám sát**. Kiểm toán cả bảng, view, sequence, routine và schema, không chỉ bảng nghiệp vụ.

## 12. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| API dùng tài khoản admin/owner để chạy CRUD | Lỗi nhỏ có thể sửa/xóa schema hoặc nhiều dữ liệu | Tách runtime và migration |
| `GRANT ALL PRIVILEGES` để chữa một lỗi truy cập | Tạo quyền thừa kéo dài | Xác định đúng câu SQL/cột cần thiết rồi cấp riêng |
| Chỉ kiểm tra `GRANT` trực tiếp | Bỏ qua quyền qua role khác, `PUBLIC` hoặc sở hữu | Kiểm tra quyền hiệu dụng bằng tài khoản thật |
| Coi `setReadOnly(true)` là bảo vệ không ghi | DB/driver có thể không cưỡng chế chặn ghi | Dùng tài khoản DB read-only thật |
| Coi `PreparedStatement` tự thực hiện authorization | Endpoint vẫn có thể truy vấn hàng của tenant khác | Xác thực và ràng buộc ngữ cảnh tenant |
| `SELECT *` ở runtime | Đọc quá nhiều cột; có thể lộ cột mới sau migration | Chọn cột rõ ràng và grant theo nhu cầu |
| Role runtime có `CREATE`/`ALTER`/`DROP` | Tăng bề mặt tấn công của ứng dụng | Dùng migration identity riêng |
| Dùng một pool admin rồi `SET ROLE` tùy request | Có thể rò rỉ trạng thái role giữa các lần mượn | Pool theo credential/workload; reset session có kiểm chứng |
| Hard-code mật khẩu JDBC trong source/log | Lộ credential và khó rotation | Secret manager, TLS, kiểm soát log |
| Quên quyền sequence/routine/view | SQL đúng vẫn bị từ chối | Kiểm kê các đối tượng phụ trợ cần thiết |
| Test quyền bằng tài khoản admin | Test chạy qua nhưng runtime thật thiếu/quá quyền | Dùng đúng credential production-like |
| Bỏ qua quyền trên hàng trong hệ thống multi-tenant | Có quyền SELECT bảng có thể đọc tenant khác | Authorization đúng ngữ cảnh, cân nhắc RLS |

## 13. Thực hành xây dựng chính sách quyền tối thiểu

Với bảng `app.customer` ở phần 4, hãy thực hiện trên môi trường PostgreSQL kiểm thử:

1. **Liệt kê đường SQL:** repository có `SELECT`, `INSERT` và `UPDATE` cột nào? Có dùng `WHERE tenant_id`, `RETURNING id`, sequence hoặc procedure không?
2. **Lập ma trận:** đánh dấu quyền của API, báo cáo và migration. Ghi rõ những quyền **không** được cấp.
3. **Tạo vai trò:** dùng danh tính quản trị riêng để tạo role quyền không đăng nhập, tài khoản runtime và reporting. Cấp `CONNECT`, `USAGE` và các quyền cột theo ma trận.
4. **Chạy repository JDBC:** cấu hình `DataSource` bằng credential runtime; dùng `PreparedStatement` để gọi `findById` và `updateEmail`. Xác minh chương trình không cần nâng quyền.
5. **Chạy negative test:** xác nhận các câu đọc `credit_limit`, `DELETE` và DDL bị DB từ chối. Đừng chỉ kiểm tra số dòng trả về.
6. **Thử tenant khác:** gọi API với danh tính không sở hữu khách hàng được hỏi; xác nhận tầng ứng dụng không dùng tenant do client tự khai và kiểm tra giải pháp DB-level nếu yêu cầu.
7. **Thêm cột qua migration:** thử thêm một cột nhạy cảm; xác minh tài khoản API không vô tình được đọc cột mới. Cập nhật ma trận quyền và test nếu tính năng cần truy cập.
8. **Kiểm tra connection pool:** mượn, thực thi và trả connection; xác minh không lưu trạng thái role/tenant ngoài phạm vi một request. Thử rotation/reconnect trong môi trường test.
9. **Viết báo cáo:** mô tả từng quyền với lý do nghiệp vụ, tài khoản sở hữu, kết quả positive/negative test và kế hoạch rà soát khi đổi schema.

**Tự kiểm tra:**

- Vì sao `PreparedStatement` đã tham số hóa vẫn không thể thay thế quyền `GRANT`/`REVOKE`?
- Tại sao một role có quyền `SELECT` trên bảng chưa chắc chỉ đọc được hàng của tenant hiện tại?
- `GRANT USAGE ON SCHEMA` đã cho phép đọc bảng chưa?
- Câu `UPDATE ... WHERE tenant_id = ? AND id = ?` cần những quyền cột nào ngoài `UPDATE(email)`?
- Tại sao `REVOKE DELETE` trên một role không luôn làm mất quyền xóa của thành viên?
- Vì sao `Connection.setReadOnly(true)` không phải một ranh giới bảo mật?
- Sau rotation credential, có thể vẫn còn connection vật lý đã xác thực trước đó không?

**Ghi nhớ:** Quyền tối thiểu trong JDBC được thực thi bởi **database**, không phải một setter của `Connection`. Hãy tách tài khoản runtime, reporting và migration; cấp `CONNECT`/`USAGE` cùng quyền `SELECT`, `INSERT`, `UPDATE` trên đúng đối tượng/cột; tránh quyền `DELETE`/DDL không cần thiết; kiểm tra cả quyền qua role và `PUBLIC`. Kết hợp quyền DB với `PreparedStatement`, xác thực tenant, quản lý secret/pool và **kiểm thử quyền bằng chính credential ít đặc quyền**, để một lỗi ứng dụng không dễ vượt quá phạm vi dữ liệu mà dịch vụ cần xử lý.
