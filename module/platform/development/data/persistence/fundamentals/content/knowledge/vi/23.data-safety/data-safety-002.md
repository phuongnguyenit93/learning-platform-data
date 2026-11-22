# Nguyên tắc cấp quyền tối thiểu cho tài khoản ứng dụng

Trong chương **An toàn dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, bảo vệ dữ liệu không chỉ là mã hóa kết nối hay tránh SQL injection. Mỗi ứng dụng Java đăng nhập vào hệ quản trị cơ sở dữ liệu bằng **một danh tính có quyền cụ thể**. Nếu danh tính đó được cấp quyền quá rộng, một lỗi lập trình, tài khoản bị lộ hoặc điểm chèn SQL có thể biến thành hành động xóa bảng, thay dữ liệu ngoài phạm vi nghiệp vụ, đọc thông tin nhạy cảm hay sửa cấu trúc database.

**Nguyên tắc cấp quyền tối thiểu (principle of least privilege)** yêu cầu mỗi danh tính chỉ có **những quyền cần thiết, trên đối tượng cần thiết, trong thời gian cần thiết** để thực hiện nhiệm vụ đã được phê duyệt. Điều này áp dụng cho tài khoản runtime của API, batch job, consumer, công cụ migration, báo cáo, backup và vận hành.

Bài học tập trung vào ranh giới persistence Java: cách nhận diện quyền thực sự cần, phân biệt phân quyền ứng dụng và database, thực hiện `GRANT`/`REVOKE` bằng ví dụ PostgreSQL, quản lý bí mật và connection pool, bảo vệ dữ liệu đa tenant, thử nghiệm quyền trong CI và tránh nâng quyền ngoài ý muốn.

## 1. Vì sao tài khoản database là một ranh giới an toàn?

Giả sử dịch vụ đơn hàng dùng tài khoản có thể:

- `SELECT`, `INSERT`, `UPDATE`, `DELETE` trên mọi bảng của tất cả dịch vụ.
- `CREATE`, `ALTER`, `DROP` các đối tượng trong schema.
- Đọc bảng chứa token thanh toán và dữ liệu nội bộ.
- Sử dụng đặc quyền quản trị hoặc bỏ qua row-level security.

Trong happy path, mã Java có thể chỉ chạy vài câu SQL đúng nghiệp vụ. Nhưng nếu endpoint bị SQL injection, thư viện bị chiếm quyền thực thi hoặc credential bị lộ, kẻ tấn công có thể dùng **toàn bộ quyền của tài khoản**, không chỉ các câu SQL lập trình viên dự định chạy.

Nếu tài khoản API chỉ được đọc các cột cần thiết và cập nhật `orders.status`, database có thể từ chối nhiều hành động không thuộc chức năng của service. Hạn chế này giúp **giảm phạm vi thiệt hại (blast radius)** khi một lớp bảo vệ khác thất bại.

```text
HTTP / Message
      |
      v
Java Application Service
(xác thực, phân quyền, domain policy)
      |
      v
JDBC / JPA / Connection Pool
      |
      v
DB role: shop_api
   SELECT  shop.orders             -> được phép theo GRANT/RLS
   UPDATE  shop.orders.status      -> được phép theo GRANT/RLS
   DELETE  shop.orders             -> từ chối
   SELECT  billing.payment_tokens  -> từ chối
   ALTER   shop.orders             -> từ chối
      |
      v
Database: transactions, WAL, backups
```

**Least privilege là phòng thủ nhiều lớp**, không thay thế xác thực, quyền nghiệp vụ, query parameterization, giao dịch, backup hay giám sát. Một tài khoản vẫn có thể gây tác hại bằng chính quyền hợp lệ của nó: quyền `UPDATE status` vẫn có thể bị lạm dụng để đổi trạng thái hàng loạt nếu không có kiểm tra chủ sở hữu và điều kiện nghiệp vụ.

## 2. Phân biệt xác thực, phân quyền database và quyền nghiệp vụ

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Kết nối đại diện cho danh tính nào? | Driver PostgreSQL xác thực role `shop_api`. |
| **Database authorization** | Danh tính đó được làm gì trên đối tượng nào? | `shop_api` được `SELECT shop.orders`, không được `DELETE`. |
| **Business authorization** | Người dùng cuối được làm gì với bản ghi nào? | Khách A chỉ được xem đơn của A. |
| **Data governance** | Ai phê duyệt, giám sát, lưu giữ và khôi phục dữ liệu? | Quy định truy cập thông tin nhạy cảm, audit, backup. |

Ứng dụng dùng connection pool thường phục vụ nhiều người dùng cuối qua **cùng một role database**. PostgreSQL có thể biết `current_user = shop_api` nhưng **không tự biết khách hàng nào đã gửi HTTP request**, trừ khi kiến trúc truyền một ngữ cảnh tin cậy hoặc dùng cơ chế phân biệt danh tính ở DB.

Không suy diễn rằng vì role có `SELECT` nên tất cả người dùng được phép đọc mọi hàng. Quyền database xác định **năng lực tối đa của process**, còn quyền nghiệp vụ giới hạn **ai được sử dụng năng lực đó và với dữ liệu nào**.

## 3. Lập ma trận quyền theo nhiệm vụ

Một ma trận quyền tốt trả lời bốn câu hỏi:

1. **Ai?** API runtime, worker, reporting, migrator, backup, vận hành.
2. **Trên đâu?** Database, schema, bảng, cột, sequence, function, view.
3. **Được làm gì?** `CONNECT`, `USAGE`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `EXECUTE`, `CREATE`, ownership và đặc quyền quản trị.
4. **Khi nào/ở phạm vi nào?** Production hoặc staging, tenant, phiên bản triển khai, cửa sổ bảo trì, quyền tạm thời.

Ví dụ cho hệ thống bán hàng:

| Danh tính | Nhu cầu hợp lệ | Quyền thường cân nhắc | Quyền không nên có |
| --- | --- | --- | --- |
| `shop_api` | Đọc, tạo, chuyển trạng thái đơn. | DML trên đúng bảng/cột; RLS nếu cần. | DDL, owner, quyền schema khác. |
| `shop_consumer` | Xử lý sự kiện, inbox/outbox. | DML trên bảng điều phối được cấp. | Quyền sửa dữ liệu ngoài service. |
| `shop_report` | Xem tổng hợp đã phê duyệt. | `SELECT` trên view/projection báo cáo. | Ghi đơn, đọc dữ liệu thô nhạy cảm. |
| `shop_migrator` | Tạo/sửa schema khi triển khai. | DDL đúng môi trường theo quy trình. | Dùng làm credential API lâu dài. |
| `backup_agent` | Sao lưu/kiểm tra khôi phục. | Quyền đặc thù theo công cụ và DBMS. | Tài khoản toàn quyền nếu không cần. |
| Tài khoản khẩn cấp | Khắc phục sự cố có phê duyệt. | Quyền cao hơn **tạm thời**, được audit. | Dùng chung thường trực. |

Không phải dự án nào cũng cần rất nhiều role; mức tách phải tương xứng rủi ro và chi phí vận hành. Nhưng **dùng cùng một tài khoản toàn quyền cho mọi service** là tín hiệu thiếu ranh giới.

## 4. PostgreSQL: role, ownership, PUBLIC và quyền kế thừa

PostgreSQL dùng **role** để quản lý danh tính và quyền. Role có thể `LOGIN` để được dùng làm danh tính kết nối hoặc `NOLOGIN` để gom quyền và làm chủ sở hữu object.

Các khái niệm quan trọng:

- **Object owner:** chủ sở hữu có quyền kiểm soát và thay đổi object; tài khoản runtime không nên sở hữu schema/bảng nghiệp vụ.
- **GRANT/REVOKE:** cấp hoặc thu hồi quyền trên những loại object hỗ trợ.
- **Role membership/inheritance:** quyền hiệu lực có thể đến từ role khác, tùy cấu hình inheritance và khả năng `SET ROLE`.
- **PUBLIC:** nhóm đặc biệt bao gồm mọi role; quyền cấp cho `PUBLIC` có thể làm một lệnh `REVOKE` chỉ nhắm vào role riêng không đủ.
- **SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS:** là đặc quyền/thuộc tính không phù hợp với tài khoản runtime thông thường.

Quyền trên database, schema và table là **những lớp khác nhau**:

| Quyền | Ý nghĩa khái quát | Không đồng nghĩa với |
| --- | --- | --- |
| `CONNECT ON DATABASE` | Cho phép kết nối tới database theo các kiểm soát khác. | Quyền đọc toàn bộ bảng. |
| `USAGE ON SCHEMA` | Cho phép tham chiếu đối tượng trong schema theo quyền object tương ứng. | Quyền `SELECT` trên mọi bảng. |
| `CREATE ON SCHEMA` | Cho phép tạo object trong schema. | Quyền cần cho một API CRUD bình thường. |
| `SELECT ON TABLE` | Cho phép đọc bảng hoặc cột được cấp. | Quyền `UPDATE` hoặc đọc bảng khác. |
| `UPDATE (column)` | Cho phép sửa những cột cụ thể. | Quyền sửa mọi cột hay mọi hàng theo chính sách nghiệp vụ. |
| `EXECUTE ON FUNCTION` | Cho phép gọi một function. | Bảo đảm function chỉ đọc dữ liệu. |

Trong PostgreSQL, quyền sở hữu thường không thể bị “lấy lại” đơn giản như một `GRANT` đối với chính owner. Cần **không để runtime trở thành owner ngay từ đầu**.

## 5. Tách tài khoản migration và tài khoản runtime

Thiết kế phổ biến là: schema owner không login, migration runner có quyền điều hành DDL khi cần, còn application principal chỉ có quyền DML cần thiết.

```text
CI/CD migration:
    shop_migrator (LOGIN)
          |
       SET ROLE
          v
    shop_owner (NOLOGIN)
          |
    CREATE/ALTER tables/indexes

Java service:
    shop_api (LOGIN)
          |
    SELECT/INSERT/UPDATE các cột được phép
          |
    tables owned by shop_owner
```

Ví dụ PostgreSQL, chạy bởi quản trị viên có quyền thích hợp:

```sql
CREATE ROLE shop_owner NOLOGIN;
CREATE ROLE shop_migrator LOGIN NOINHERIT;
CREATE ROLE shop_api LOGIN;
CREATE ROLE shop_report LOGIN;

GRANT shop_owner TO shop_migrator;

-- Chạy trong database mục tiêu, ví dụ shopdb.
CREATE SCHEMA shop AUTHORIZATION shop_owner;

GRANT CONNECT ON DATABASE shopdb
    TO shop_migrator, shop_api, shop_report;
GRANT USAGE ON SCHEMA shop TO shop_api, shop_report;
```

Ví dụ không chứa password thật. Việc tạo role `LOGIN` **không tự tạo credential dùng được qua password authentication**; secret/cơ chế xác thực phải được provision riêng theo platform.

**Quan trọng:** nếu `CONNECT` đã được cấp cho `PUBLIC` theo mặc định hoặc từ trước, các dòng `GRANT CONNECT` trên **không biến database thành whitelist độc quyền**. Quản trị viên phải kiểm kê quyền hiện hành và cân nhắc `REVOKE CONNECT ON DATABASE shopdb FROM PUBLIC` trong một migration có đánh giá tác động, không chạy tùy tiện khi production có nhiều dịch vụ dùng chung.

Một migration có thể chạy qua `shop_migrator` rồi chuyển role trước khi tạo đối tượng:

```sql
SET ROLE shop_owner;

CREATE TABLE shop.orders (
    id          UUID PRIMARY KEY,
    tenant_id   UUID NOT NULL,
    status      TEXT NOT NULL
                CHECK (status IN ('DRAFT', 'SUBMITTED', 'CANCELLED')),
    total_cents BIGINT NOT NULL CHECK (total_cents >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

RESET ROLE;
```

Role thực hiện `SET ROLE` cần cấu hình membership và quyền phù hợp phiên bản PostgreSQL đang dùng. **shop_api không phải thành viên shop_owner** và không có khả năng chuyển sang role này. Migration phải được review/version-control; tài khoản DDL không được đưa vào cấu hình ứng dụng chạy lâu dài.

## 6. Cấp quyền bảng và cột thay vì `GRANT ALL`

Giả sử API chỉ cần tạo và đọc đơn, sau đó chuyển trạng thái hợp lệ. Với bảng `shop.orders`:

```sql
-- Đọc các cột mà API thực sự cần.
GRANT SELECT (id, tenant_id, status, total_cents, created_at)
ON TABLE shop.orders TO shop_api;

-- Tạo đơn, nhưng không cho API tự thay created_at.
GRANT INSERT (id, tenant_id, status, total_cents)
ON TABLE shop.orders TO shop_api;

-- Chỉ được sửa trạng thái, không được đổi số tiền hoặc tenant.
GRANT UPDATE (status)
ON TABLE shop.orders TO shop_api;

-- Cố ý không cấp DELETE, TRUNCATE, TRIGGER, REFERENCES,
-- CREATE ON SCHEMA, ownership hoặc quyền trên billing.*.
```

Nếu code bị lỗi và chạy `UPDATE shop.orders SET total_cents = ...`, PostgreSQL từ chối do không có quyền `UPDATE` trên cột này. Role cũng không được phép `DELETE FROM shop.orders` hay `TRUNCATE` theo thiết kế.

### Quyền cần cho biểu thức và `RETURNING`

Ví dụ câu cập nhật có điều kiện:

```sql
UPDATE shop.orders
SET status = 'SUBMITTED'
WHERE id = :order_id AND status = 'DRAFT'
RETURNING id, status;
```

PostgreSQL còn cần quyền `SELECT` trên các cột được đọc trong điều kiện/biểu thức hoặc `RETURNING`. Các placeholder `:order_id` biểu diễn giá trị cần bind qua JDBC hoặc công cụ SQL, không phải cú pháp JDBC `PreparedStatement` trực tiếp.

**Cấp quyền UPDATE trên một cột không đồng nghĩa đã bảo vệ toàn bộ quy tắc nghiệp vụ.** API vẫn phải kiểm tra người gọi, tenant và chuyển trạng thái; câu `UPDATE ... WHERE status = 'DRAFT'`/constraint/RLS có thể tạo thêm lớp bảo vệ tại thời điểm ghi. Đừng dùng GRANT để thay cho domain policy.

## 7. Quyền trên sequence, function và view có ý nghĩa riêng

Một ứng dụng đủ quyền trên bảng vẫn có thể thiếu quyền sử dụng sequence hoặc gọi function được phê duyệt. Cách xử lý là **cấp đúng quyền còn thiếu**, không nâng role thành owner.

### Sequence

```sql
CREATE SEQUENCE shop.order_number_seq;

-- Khi ứng dụng thực sự cần gọi nextval của sequence này:
GRANT USAGE ON SEQUENCE shop.order_number_seq TO shop_api;
```

Trong PostgreSQL, `nextval` cần các quyền sequence thích hợp (`USAGE` hoặc `UPDATE`); `currval` và `setval` có yêu cầu riêng. Với cột identity hoặc ORM sinh ID theo cách khác, phải kiểm tra SQL thực thi trước khi cấp quyền. Không cấp `ALL ON ALL SEQUENCES IN SCHEMA shop` chỉ vì một lần lấy ID lỗi.

### Function

```sql
-- Hàm đã được tạo và review trong migration.
GRANT EXECUTE ON FUNCTION shop.submit_order(uuid) TO shop_api;
```

Quyền `EXECUTE` không có nghĩa hàm vô hại. Một function có thể ghi dữ liệu và có thể chạy bằng quyền owner nếu dùng `SECURITY DEFINER`. PostgreSQL thường cấp `EXECUTE` trên function mới cho `PUBLIC` theo default privileges nếu không được thay đổi. Các function nhạy cảm cần xem lại default privileges và thu hồi quyền không mong muốn **trong cùng migration transaction nếu khả thi**, tránh cửa sổ truy cập.

### View báo cáo

```sql
CREATE VIEW shop.order_status_report AS
SELECT status, COUNT(*) AS order_count
FROM shop.orders
GROUP BY status;

GRANT SELECT ON shop.order_status_report TO shop_report;
```

View giúp chỉ công bố một phần dữ liệu, nhưng phải review quyền owner/invoker, RLS và khả năng suy diễn dữ liệu nhạy cảm từ thống kê tập quá nhỏ. Một view không tự làm an toàn mọi truy vấn hay mọi schema.

## 8. Default privileges và bảng được tạo sau này

Một lỗi deployment: runtime được cấp quyền trên các bảng cũ, nhưng migration tạo bảng mới, sau đó API nhận `permission denied`. Ngược lại, cấp `ALL ON ALL TABLES` mỗi lần deploy có thể làm rò dữ liệu bảng mới chưa review.

Hai cách:

1. **Whitelist tường minh:** mỗi migration cấp đúng quyền cột/bảng mà phiên bản ứng dụng cần. Phù hợp khi schema chứa dữ liệu nhạy cảm hoặc trách nhiệm không đồng nhất.
2. **Default privileges theo chính sách:** chỉ dùng khi một role thực sự được phép thao tác trên **mọi object tương lai** thuộc phạm vi đó.

Ví dụ, nếu đã có quyết định rằng `shop_read_all` được xem mọi bảng mới trong schema shop:

```sql
CREATE ROLE shop_read_all NOLOGIN;

ALTER DEFAULT PRIVILEGES FOR ROLE shop_owner IN SCHEMA shop
    GRANT SELECT ON TABLES TO shop_read_all;

-- Không tự động GRANT shop_read_all TO shop_api.
```

Các giới hạn:

- Default privileges ảnh hưởng **đối tượng tạo trong tương lai**, không hồi tố bảng hiện tại.
- Cấu hình `FOR ROLE shop_owner` áp dụng cho những object **được tạo dưới shop_owner**; nếu migration tạo object bằng role khác, quy tắc có thể không áp dụng.
- `GRANT SELECT ON TABLES` cho tất cả bảng mới có thể quá rộng nếu schema xuất hiện bảng chứa secrets.
- Quyền mặc định của function, sequence và schema cần xem riêng.

Nếu mỗi bảng cần kiểm tra bảo mật riêng, **GRANT tường minh trong migration** là lựa chọn rõ ràng và dễ audit hơn.

## 9. Multi-service: vì sao cần tách DataSource theo trách nhiệm?

Một ứng dụng có API, consumer và báo cáo không nhất thiết phải dùng cùng credential:

```text
HTTP API       -> DataSource(shop_api)
                   READ + INSERT + UPDATE(status)

Async consumer -> DataSource(shop_consumer)
                   Inbox/outbox và state cần thiết

Reporting      -> DataSource(shop_report)
                   SELECT trên report views

Migration      -> shop_migrator qua pipeline riêng
                   DDL theo phiên bản
```

Tách role giúp lỗi ở dashboard không thể sửa dữ liệu đơn hàng, API không tự ghi bảng của worker và credential migration không tồn tại trong process runtime.

**Đánh đổi:** nếu một nghiệp vụ bắt buộc ghi hai bảng trong **cùng transaction**, không thể tùy tiện tách các bước sang hai datasource độc lập rồi tin rằng `@Transactional` sẽ làm chúng nguyên tử. Phải chọn phân ranh giới phù hợp cơ chế transaction hoặc thiết kế giao thức khác. Least privilege phải phối hợp với atomicity, không phá vỡ nó.

## 10. Multi-tenant: quyền DB không thay cho quyền từng khách hàng

Một role có `SELECT shop.orders` về kỹ thuật vẫn có thể đọc hàng của nhiều tenant. Nếu service phục vụ nhiều tenant:

1. Lấy tenant từ **authentication context tin cậy**, không tin trực tiếp vào tham số từ client.
2. Giới hạn mọi đường đọc/ghi theo tenant; có thể bổ sung **row-level security (RLS)** trong PostgreSQL khi phù hợp threat model.

Ví dụ SQL có phạm vi:

```sql
SELECT id, status, total_cents
FROM shop.orders
WHERE tenant_id = :authenticated_tenant_id
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

`:authenticated_tenant_id` là giá trị do backend xác định từ quyền của caller, không phải thông tin có thể tự khai tùy ý.

### Chính sách RLS trên PostgreSQL

Một phương án minh họa:

```sql
-- Chạy dưới quyền owner/migration có kiểm soát.
ALTER TABLE shop.orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY shop_orders_tenant_policy
ON shop.orders
FOR ALL TO shop_api
USING (
    tenant_id =
    NULLIF(current_setting('app.tenant_id', true), '')::uuid
)
WITH CHECK (
    tenant_id =
    NULLIF(current_setting('app.tenant_id', true), '')::uuid
);
```

`USING` hạn chế những hàng có thể nhìn thấy/tác động theo policy; `WITH CHECK` kiểm tra giá trị mới khi insert/update. Nếu `app.tenant_id` không có, biểu thức không khớp hàng; nếu được đặt với chuỗi UUID không hợp lệ, truy vấn có thể lỗi chuyển kiểu. RLS **không cấp quyền bảng**: role vẫn cần GRANT tương ứng.

Giới hạn cần nhớ:

- Owner có thể bỏ qua RLS theo mặc định, trừ những trường hợp cấu hình `FORCE ROW LEVEL SECURITY`; superuser và role có `BYPASSRLS` vẫn là các ngoại lệ đặc biệt. Runtime không nên là owner hay mang đặc quyền đó.
- Một role có thể thực thi SQL tùy ý có thể tự đặt custom setting `app.tenant_id`; policy chỉ dựa vào biến do chính role có thể đổi **không phải tường bảo vệ tuyệt đối trước SQL injection**. Cần bind tham số, phân quyền ứng dụng, kiểm soát SQL và cân nhắc cách cô lập tenant mạnh hơn nếu threat model yêu cầu.
- View, function, role khác và policy bổ sung có thể ảnh hưởng hành vi thực tế; phải test end-to-end.

### Ngữ cảnh tenant trong Spring JDBC và connection pool

Đặt tenant trong **transaction-local setting** để tránh session cũ rò sang request tiếp theo:

```java
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class TenantOrderReader {
    public record OrderRow(UUID id, String status, long totalCents) {}
    private final JdbcTemplate jdbc;

    public TenantOrderReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<OrderRow> listForTenant(UUID authenticatedTenantId) {
        jdbc.queryForObject(
            "SELECT set_config('app.tenant_id', ?, true)",
            String.class,
            authenticatedTenantId.toString()
        );
        return jdbc.query("""
            SELECT id, status, total_cents
            FROM shop.orders
            ORDER BY created_at DESC, id DESC
            LIMIT 50
            """,
            (rs, n) -> new OrderRow(
                (UUID) rs.getObject("id"),
                rs.getString("status"),
                rs.getLong("total_cents")
            )
        );
    }
}
```

Với `set_config(..., true)`, thay đổi chỉ có hiệu lực trong transaction hiện hành; cần đảm bảo cả hai câu SQL chạy trên **cùng connection do Spring transaction manager quản lý**. Tenant ID phải lấy từ nguồn xác thực đáng tin. Dùng `SET app.tenant_id = ...` theo session mà không reset khi trả connection về pool có nguy cơ **request B nhận tenant context của A**.

Ví dụ RLS này không phải cấu hình production hoàn chỉnh; cần test với chính role runtime, driver, transaction manager, các đường batch/report, owner privilege và khả năng injection.

## 11. SQL injection và least privilege là hai lớp bổ sung

Nếu Java nối đầu vào người dùng trực tiếp thành SQL, role ít quyền vẫn có thể bị khai thác **trong phạm vi quyền được cấp**.

**Không nên làm:**

```java
String sql = "SELECT status FROM shop.orders WHERE id = '" +
        orderIdFromRequest + "'";
// Dữ liệu không tin cậy bị ghép trực tiếp vào câu SQL.
```

**Dùng JDBC PreparedStatement:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public final class JdbcOrderLookup {
    public String findStatus(Connection connection, UUID orderId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT status FROM shop.orders WHERE id = ?")) {
            statement.setObject(1, orderId);
            try (ResultSet rows = statement.executeQuery()) {
                return rows.next() ? rows.getString("status") : null;
            }
        }
    }
}
```

Mã này minh họa bind, **chưa có authorization theo tenant** nếu ứng dụng không bật/thiết kế RLS hoặc thêm điều kiện tenant. Với identifier như tên bảng/cột, JDBC không bind bằng `?` như giá trị; dùng **allowlist** ánh xạ từ lựa chọn bên ngoài sang identifier cố định, không chèn raw string.

**Parameter binding ngăn chèn SQL** ở điểm xây query, còn **least privilege giảm phạm vi thiệt hại** nếu một đường thực thi SQL độc hại vẫn xuất hiện. Hai lớp không thay thế nhau.

## 12. `search_path` và `SECURITY DEFINER` có thể tạo đường nâng quyền

Trong PostgreSQL, một tên bảng hoặc function không chỉ rõ schema có thể được phân giải qua `search_path`. Nếu role không đáng tin có quyền tạo object trong schema nằm trên đường phân giải, SQL nhạy cảm có thể bị dẫn tới object không mong muốn.

Các nguyên tắc:

- Dùng identifier có schema như `shop.orders` trong các query nhạy cảm.
- Không cấp `CREATE ON SCHEMA` cho runtime khi không cần.
- Review quyền `CREATE` trong schema `public` và những schema thuộc `search_path`.
- Hạn chế `SECURITY DEFINER`; khi dùng phải review owner, cố định `search_path` tin cậy, tránh SQL động không kiểm soát và thu hẹp `EXECUTE`.
- Không xem function là “chỉ đọc” chỉ vì caller dùng `SELECT function_name(...)`.

Ví dụ khung function cần review cẩn thận:

```sql
CREATE FUNCTION shop.read_order_count()
RETURNS BIGINT
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, shop, pg_temp
AS $func$
    SELECT COUNT(*) FROM shop.orders;
$func$;
```

Nếu function chạy bằng quyền owner, caller có thể đọc kết quả tổng hợp mà bản thân không có quyền đọc bảng nguồn, tùy cấu hình. Việc đó chỉ hợp lệ khi **cố ý thiết kế một API dữ liệu có kiểm soát**. Phải kiểm tra chính sách RLS/owner và quyền EXECUTE mặc định của PUBLIC, tránh tạo một đường đọc dữ liệu nhạy cảm không được review.

## 13. Tài khoản runtime không được tự chạy migration

Một sai lầm phổ biến là dùng chính tài khoản tạo bảng lúc phát triển làm tài khoản cho ứng dụng production. Khi đó nó sở hữu object và có thể thay đổi/drop chúng theo quyền owner.

Một quy trình hợp lý:

1. **Provisioning:** quản trị tạo database, role, schema, cơ chế authentication và chính sách mạng.
2. **Migration:** pipeline riêng chạy DDL bằng migrator/owner, có review, rollback/recovery plan.
3. **Runtime:** Java service dùng tài khoản chỉ có DML cần thiết.
4. **Maintenance/backup:** công cụ chuyên dụng dùng role riêng theo nhiệm vụ.

Ví dụ cấu hình Spring Boot minh họa:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-internal:5432/shopdb
    username: shop_api
    password: ${DB_APP_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
```

`${DB_APP_PASSWORD}` chỉ là placeholder, không phải mật khẩu. Credential phải được cấp từ secret manager hoặc cơ chế an toàn tương đương. `ddl-auto: validate` chỉ phù hợp khi thực sự dùng JPA/Hibernate và muốn kiểm tra mapping; nó không thay thế migration hay cơ chế phân quyền.

Nếu validate/schema mismatch thất bại, ứng dụng nên báo lỗi triển khai và dừng theo quy trình, **không tự đổi sang tài khoản migrator** để sửa schema lúc runtime.

## 14. Tài khoản báo cáo cũng cần giới hạn quyền và tài nguyên

Tài khoản đọc báo cáo thường không cần quyền ghi. Tách `shop_report` khỏi `shop_api` giúp giảm rủi ro sửa dữ liệu nếu dashboard bị lỗi hoặc credential bị lộ.

Tuy nhiên một role “chỉ đọc” vẫn có thể làm lộ thông tin hoặc gây tải nặng. Vì vậy:

- Cấp `SELECT` trên view/projection cần thiết, không mặc định tất cả bảng thô.
- Bảo vệ dữ liệu theo tenant và chính sách suy diễn từ thống kê tổng hợp.
- Có giới hạn statement timeout, quota/concurrency theo khả năng của hệ thống.
- Định tuyến đến read replica nếu yêu cầu độ mới và topology cho phép; replica không tự thay thế authorization.
- Không chia sẻ credential reporting với đối tác khác phạm vi quyền.

Độ bí mật, tính toàn vẹn và khả năng sẵn sàng đều là mục tiêu của cấp quyền tối thiểu.

## 15. Quản lý secrets, TLS và kết nối tồn tại sau rotation

Credential database phải được coi là khả năng truy cập hệ thống. Không hard-code password trong Git, hướng dẫn deploy, JDBC URL được ghi log hoặc SQL script chia sẻ rộng.

Thực hành:

- Tách credential production, staging và development.
- Mỗi workload/service có danh tính phù hợp; tránh chia sẻ một account giữa nhiều service không cần.
- Cấp secrets từ secret manager hoặc cơ chế platform có phân quyền.
- Dùng TLS và kiểm tra định danh máy chủ nếu triển khai yêu cầu; kết hợp cấu hình mạng/firewall/pg_hba.
- Hạn chế nơi credential xuất hiện trong environment dumps, logs, tracing hoặc debug screens.
- Có chính sách rotation, thu hồi, giám sát và ứng cứu khi nghi bị lộ.

### Vì sao đổi password chưa đủ?

Giả sử HikariCP đang giữ 20 connection được xác thực bằng `shop_api`. Khi quản trị đổi password, những **session đã xác thực có thể tiếp tục tồn tại** đến khi kết nối bị đóng. Đổi password không phải bằng chứng mọi session cũ đã bị thu hồi ngay lập tức.

Quy trình rotation có kiểm soát:

1. Provision credential mới an toàn, theo cách có thể chuyển đổi.
2. Cập nhật cấu hình workload và recycle connection pool/instance.
3. Xác minh connection mới thành công bằng quyền runtime.
4. Thu hồi credential cũ và kiểm tra các session hiện hữu.
5. Kiểm tra log/audit nếu đây là sự cố lộ credential, theo runbook bảo mật.

Việc đóng session có thể làm hủy transaction đang chạy nên phải theo quy trình vận hành có thẩm quyền. Với sự cố bảo mật, cần kiểm tra cả khả năng đã bị truy cập dữ liệu trước khi credential được xoay.

## 16. Thay đổi schema và quyền trong rolling deployment

Least privilege phải được duy trì khi schema thay đổi. Ví dụ phiên bản mới cần `UPDATE orders.shipping_status` nhưng migration chưa cấp quyền UPDATE cột đó; kết quả là `permission denied` sau deploy.

Quy trình hợp lý:

1. Thiết kế thay đổi theo **expand–migrate–contract** nếu nhiều phiên bản ứng dụng chạy song song.
2. Review câu SQL mới và những quyền cần cho runtime, job, report.
3. Triển khai schema và GRANT phù hợp ở thời điểm có thể duy trì tương thích.
4. Integration test với **credential runtime thật**, không chỉ migrator.
5. Triển khai ứng dụng và theo dõi lỗi SQL/quyền.
6. Thu hồi quyền không còn cần sau khi phiên bản cũ và job liên quan đã dừng.
7. Lưu GRANT/REVOKE trong migration và review diff privilege trước/sau.

Tránh tạm cấp `ALL PRIVILEGES` “cho chắc” mà không có thời hạn hoặc cơ chế tự kiểm tra thu hồi. Các quyền tạm thời rất dễ trở thành quyền vĩnh viễn.

## 17. Kiểm tra quyền hiệu lực trên PostgreSQL

Quyền hiệu lực có thể đến từ nhiều đường: grant trực tiếp, membership, PUBLIC, ownership và function. Vì vậy, không thể chỉ nhìn file SQL migration rồi kết luận.

```sql
-- Thuộc tính role runtime.
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls
FROM pg_roles
WHERE rolname = 'shop_api';

-- Kiểm tra quyền database/schema/table.
SELECT
    has_database_privilege('shop_api', 'shopdb', 'CONNECT')
        AS can_connect,
    has_schema_privilege('shop_api', 'shop', 'USAGE')
        AS can_use_schema,
    has_schema_privilege('shop_api', 'shop', 'CREATE')
        AS can_create_in_schema,
    has_table_privilege('shop_api', 'shop.orders', 'SELECT')
        AS can_select_whole_table,
    has_column_privilege('shop_api', 'shop.orders', 'status', 'UPDATE')
        AS can_update_status,
    has_table_privilege('shop_api', 'shop.orders', 'DELETE')
        AS can_delete_orders;
```

**Lưu ý:** `has_table_privilege(..., 'SELECT')` có thể trả false khi role chỉ có quyền SELECT ở mức **một số cột**. Với GRANT theo cột, kiểm tra từng cột:

```sql
SELECT
    has_column_privilege('shop_api', 'shop.orders', 'id', 'SELECT')
        AS can_read_id,
    has_column_privilege('shop_api', 'shop.orders', 'total_cents', 'SELECT')
        AS can_read_total,
    has_column_privilege('shop_api', 'shop.orders', 'status', 'UPDATE')
        AS can_change_status;

SELECT current_user, session_user, current_database();
```

Nếu service API đáng lẽ chạy `shop_api` nhưng `current_user` là owner/migrator, cần điều tra ngay. `current_user` và `session_user` có thể khác nhau do `SET ROLE` theo thiết kế; phải hiểu ngữ cảnh trước khi kết luận.

Các hàm kiểm tra quyền không thay cho **chạy SQL thật bằng role runtime trong môi trường kiểm thử**, đặc biệt khi RLS, view và SECURITY DEFINER có thể thay đổi kết quả.

## 18. Negative tests: xác nhận điều bị cấm thực sự bị cấm

Không chỉ kiểm tra những thao tác được phép; cần kiểm thử **quyền phải từ chối**:

| Kịch bản | Kỳ vọng với role `shop_api` |
| --- | --- |
| Kết nối vào database mục tiêu với credential hợp lệ. | Thành công. |
| `SELECT` các cột được cấp của `shop.orders`. | Thành công, bị giới hạn tenant nếu có RLS. |
| `INSERT` đơn hợp lệ vào các cột đã cấp. | Thành công khi constraint/policy thỏa. |
| `UPDATE shop.orders SET status = ...`. | Thành công nếu điều kiện nghiệp vụ/RLS thỏa. |
| `UPDATE shop.orders SET total_cents = ...`. | **Bị từ chối quyền**. |
| `DELETE FROM shop.orders`. | **Bị từ chối quyền**. |
| `TRUNCATE shop.orders`. | **Bị từ chối quyền**. |
| `CREATE TABLE shop.extra ...`. | **Bị từ chối** do không có CREATE. |
| `ALTER/DROP TABLE shop.orders`. | **Bị từ chối** do không sở hữu đối tượng. |
| `SELECT billing.payment_tokens`. | **Bị từ chối** ngoài phạm vi dịch vụ. |
| Đọc/sửa hàng tenant B dưới ngữ cảnh A. | Không truy cập được nếu tenant isolation được thiết kế đúng. |
| Gọi function nhạy cảm ngoài danh sách được phép. | **Bị từ chối** sau khi xét quyền PUBLIC. |
| Chuyển sang owner bằng `SET ROLE`. | **Bị từ chối**. |

Các test có tác dụng phụ phải chạy ở **database cô lập**, không thử câu `DROP`/`TRUNCATE` trên production. Trong test, nếu câu `DELETE ... WHERE id = random_uuid` trả 0 hàng **mà không báo lỗi quyền**, đó có thể là dấu hiệu role thực sự đã được cấp DELETE, không phải một negative test thành công.

### Khung Spring/JDBC integration test

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

class RuntimePrivilegeTest {
    // Inject JdbcTemplate cấu hình bằng shop_api ở môi trường test.
    private JdbcTemplate jdbc;

    @Test
    void runtimeCannotDeleteOrders() {
        assertThrows(DataAccessException.class,
            () -> jdbc.update(
                "DELETE FROM shop.orders WHERE id = ?",
                UUID.randomUUID()
            )
        );
    }

    @Test
    void runtimeIdentityIsExpected() {
        String dbUser = jdbc.queryForObject(
            "SELECT current_user", String.class);
        assertEquals("shop_api", dbUser);
    }
}
```

Đoạn này là **khung test** cần Spring test context, dependency injection, dữ liệu fixture và PostgreSQL thật. Mock JDBC hoặc một in-memory DB không nhất thiết tái hiện role, GRANT, RLS và ownership của PostgreSQL. Test tenant cần xác nhận khi thiếu setting, khi transaction kết thúc và sau khi cùng pooled connection được dùng lại cho request khác.

**Không xử lý lỗi permission denied bằng cách tự kết nối lại bằng tài khoản admin.** Đó là một đường nâng quyền ẩn. Lỗi thiếu quyền là lỗi triển khai/cấu hình cần fail rõ, ghi log an toàn và sửa bằng migration/grant được review.

## 19. Quan sát, audit và kiểm tra quyền mở rộng bất thường

Các sự kiện nên có khả năng truy vết:

- Tạo/xóa role hoặc thay đổi thuộc tính `SUPERUSER`, `CREATEROLE`, `BYPASSRLS`.
- `GRANT`/`REVOKE` trên database/schema/table/sequence/function, membership, ownership.
- Migration đổi schema hoặc default privileges.
- Kết nối từ workload/địa chỉ bất thường, login thất bại, credential bị lộ.
- Permission denied tăng sau deploy hoặc truy vấn sang schema khác trách nhiệm.
- Truy vấn lượng dữ liệu nhạy cảm bất thường, thao tác DDL ngoài cửa sổ bảo trì.
- Rotation credential và session tồn tại kéo dài.

Cần phối hợp database audit/log, log ứng dụng, events từ secret manager và hệ thống giám sát. Không có một câu SQL duy nhất chứng minh mọi hành động nguy hiểm đã được ghi lại. Khi logging, tránh ghi password, token và dữ liệu cá nhân; tên role, application name, trace ID, operation name và mã lỗi phù hợp thường hữu ích hơn dữ liệu bind thô.

Các công cụ observability cũng phải được cấp quyền tối thiểu. Một hệ thống log tập trung lưu mọi câu SQL kèm thông tin nhạy cảm nhưng được nhiều người đọc sẽ tạo **bề mặt rò rỉ mới**.

## 20. Quyền khẩn cấp, backup và giới hạn vận hành

Có nhiệm vụ hợp lệ cần quyền cao hơn runtime: restore, migration khẩn, sửa dữ liệu có phê duyệt hoặc điều tra sự cố. Không giải quyết bằng cách đổi cấu hình API sang tài khoản DBA.

Quy trình **break-glass** nên có:

1. Mục đích, đối tượng và thao tác cụ thể.
2. Danh tính riêng, xác thực mạnh, cấp quyền tạm thời và có thời hạn.
3. Phê duyệt/audit theo rủi ro và kế hoạch phục hồi.
4. Giới hạn phạm vi, kiểm tra trạng thái sau thao tác.
5. Thu hồi quyền, kiểm tra session còn sống và ghi lại kết quả.

Với backup, role và công cụ phải có quyền đúng mô hình database. Nhưng **bản backup đầy đủ cũng chứa dữ liệu nhạy cảm**: cần bảo vệ file, khóa giải mã, quyền truy cập và kiểm thử restore. API runtime không nên có quyền đọc tất cả database chỉ vì hệ thống có yêu cầu sao lưu.

## 21. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “API chạy nội bộ nên dùng superuser cho tiện.” | Bug, injection, dependency và credential lộ vẫn có thể xảy ra. |
| “Cấp `GRANT ALL` rồi sửa sau.” | Quyền thừa dễ tồn tại lâu dài; cấp theo SQL thật và test. |
| “`USAGE ON SCHEMA` là đọc được mọi bảng.” | Còn cần quyền trên từng object/cột. |
| “REVOKE quyền trực tiếp là role chắc chắn hết quyền.” | Có thể còn quyền qua PUBLIC, membership hoặc ownership. |
| “Chỉ có quyền SELECT thì không gây sự cố.” | Có thể rò dữ liệu hoặc gây tải đọc lớn. |
| “Tenant ID trong custom setting là bảo mật tuyệt đối.” | Phải tin cậy nguồn, reset theo transaction và chống injection. |
| “EXECUTE function nghĩa là chỉ đọc.” | Function có thể ghi hoặc chạy với quyền owner. |
| “Migration có thể dùng account API và tự cấp quyền.” | Tách owner/migrator/runtime theo nhiệm vụ. |
| “Password mới làm mọi session cũ biến mất ngay.” | Session đã xác thực có thể còn sống. |
| “Test bằng tài khoản owner đã chứng minh runtime an toàn.” | Phải chạy test bằng role runtime và negative test. |
| “Permission denied nghĩa là khách hàng làm sai.” | Thường là lỗi cấu hình/quyền của dịch vụ, cần xử lý kỹ thuật. |
| “GRANT, RLS và PreparedStatement thay thế nhau.” | Chúng bảo vệ các ranh giới khác nhau, phải phối hợp. |

## 22. Checklist cấp quyền tối thiểu cho ứng dụng Java

1. Runtime, consumer, report, migrator, backup có identity/credential tách biệt hợp lý?
2. Runtime không mang `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS` hoặc ownership không cần?
3. Đã đối chiếu từng SQL thực thi với quyền bảng/cột cần thiết?
4. Đã review schema, sequence, view, function, `PUBLIC` và default privileges?
5. Đã kiểm tra role membership và khả năng `SET ROLE`?
6. Mọi đường API, consumer, job, report có tenant authorization/RLS đúng thiết kế?
7. Connection pool có thiết lập/reset ngữ cảnh tenant và xử lý rotation đúng?
8. Bí mật không nằm trong mã/log, có TLS và rotation theo chính sách?
9. Migration grant phù hợp trong rolling deployment và có quy trình thu hồi quyền cũ?
10. Integration test sử dụng role runtime và xác minh cả **hành động bị cấm**?
11. Có audit phát hiện nâng quyền, truy cập bất thường và lỗi permission denied?
12. Có runbook thu hồi credential, break-glass và phục hồi dữ liệu?

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao API chỉ đọc và tạo đơn không nên kết nối PostgreSQL bằng superuser?

Vì superuser có khả năng vượt xa nhu cầu, làm tăng thiệt hại khi code, dependency hoặc credential bị lộ. API cần role runtime với đúng quyền DML.

**Câu 2.** Role được cấp `UPDATE(status)`. Vì sao câu `UPDATE ... WHERE id = ? RETURNING id, status` vẫn cần quyền đọc?

Vì các cột được đọc trong điều kiện/`RETURNING` còn cần `SELECT` tương ứng. Quyền sửa một cột không cấp quyền đọc tất cả cột.

**Câu 3.** Vì sao cấp `CONNECT ON DATABASE shopdb TO shop_api` chưa chứng minh các role khác không thể kết nối?

Vì quyền có thể được cấp cho `PUBLIC` hoặc qua role khác; còn phụ thuộc chính sách mạng và authentication. Cần kiểm tra quyền hiệu lực.

**Câu 4.** Migration tạo bảng mới, runtime báo permission denied. Cần kiểm tra gì?

Kiểm tra owner tạo object, GRANT theo bảng/cột, USAGE trên schema, default privileges của đúng role tạo object và câu SQL thực thi. Không tự nâng thành superuser.

**Câu 5.** GRANT SELECT trên bảng đơn có tự bảo vệ tenant A khỏi xem đơn tenant B không?

**Không.** Cần authorization nghiệp vụ và/hoặc RLS có ngữ cảnh tenant đáng tin cậy.

**Câu 6.** Vì sao đặt tenant ID theo session mà không reset trong JDBC pool nguy hiểm?

Vì connection có thể được tái sử dụng cho tenant khác. Nên dùng transaction-local setting cùng connection, phân quyền và kiểm thử rò rỉ context.

**Câu 7.** Đổi password shop_api có bảo đảm mọi connection cũ đóng lập tức?

**Không.** Session đã xác thực có thể tồn tại; cần kế hoạch recycle/thu hồi theo runbook.

**Câu 8.** Function có `SECURITY DEFINER` cần xem những yếu tố nào?

Owner, `search_path`, SQL động, quyền EXECUTE từ PUBLIC, dữ liệu truy cập, RLS và tham số do caller cung cấp.

**Câu 9.** Test chạy bằng owner thành công có chứng minh runtime được cấp đúng quyền không?

**Không.** Cần test bằng credential runtime và có negative tests về DELETE/ALTER, truy cập bảng nhạy cảm và khác tenant.

**Câu 10.** Khi gặp permission denied, API có nên tự chuyển sang shop_migrator rồi retry không?

**Không.** Đó là đường nâng quyền ngầm; phải báo lỗi kỹ thuật, cảnh báo và sửa grant qua quy trình.

## Kết luận

**Cấp quyền tối thiểu là một ranh giới cốt lõi của an toàn dữ liệu**, không phải bước cấu hình sau cùng. Tài khoản runtime Java cần đúng quyền trên đúng bảng/cột/schema/function; migration và tác vụ quản trị dùng danh tính riêng; quyền hiệu lực được kiểm tra cả qua role inheritance, `PUBLIC`, ownership và đường gọi gián tiếp.

Khi thiết kế persistence, hãy kết hợp **GRANT/REVOKE có chủ đích**, SQL tham số hóa, business authorization, RLS khi phù hợp, bảo vệ credential, tách nhiệm vụ và kiểm thử bằng tài khoản runtime thật. Những bảo đảm về giao dịch, backup, schema evolution và hiệu năng vẫn quan trọng, nhưng chúng không giúp hệ thống an toàn nếu một tài khoản ứng dụng có thể làm nhiều hơn nhiệm vụ mà nó được phép thực hiện.
