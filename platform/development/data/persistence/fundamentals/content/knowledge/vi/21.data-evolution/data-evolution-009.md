# Quản lý chỉ mục và tác động trong lúc migration

Thêm một chỉ mục (*index*) thường được mô tả đơn giản bằng một câu `CREATE INDEX`. Nhưng trên bảng đang có hàng chục triệu bản ghi và luôn nhận giao dịch, câu lệnh ấy là **một thay đổi vận hành**: database phải đọc dữ liệu cũ, xây cấu trúc mới, ghi log và có thể chờ hoặc giữ những loại khóa nhất định. Trong thời gian đó, các request Java vẫn cần đọc, ghi và commit đúng hạn.

Ngược lại, xóa một chỉ mục tưởng như không còn dùng đến có thể đột ngột làm câu truy vấn quan trọng chậm đi, tăng tải CPU/I/O, làm hàng chờ connection dài hơn và gây timeout cho toàn ứng dụng. Vì vậy quản lý chỉ mục phải là một phần của **schema migration có kế hoạch**, chứ không chỉ là chỉnh một tệp SQL cho chạy được.

Trong chương **Tiến hóa dữ liệu** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài học tập trung vào cách lập kế hoạch, triển khai, quan sát và khôi phục khi thêm, thay đổi hoặc bỏ chỉ mục trong hệ thống Java dùng cơ sở dữ liệu quan hệ. Các ví dụ chi tiết dùng **PostgreSQL**; cú pháp và mức độ trực tuyến (*online*) cần được xác minh lại nếu sử dụng MySQL/InnoDB, SQL Server, Oracle hoặc hệ quản trị khác.

## 1. Chỉ mục giải quyết điều gì, và vì sao migration có rủi ro?

Chỉ mục là cấu trúc phụ trợ giúp database tìm, sắp xếp hoặc kiểm tra dữ liệu theo một số điều kiện. Một B-tree index thường hỗ trợ tốt các phép so sánh bằng, khoảng giá trị và một số thứ tự sắp xếp, tùy thứ tự cột, kiểu toán tử và biểu thức truy vấn.

Tuy nhiên, chỉ mục **không miễn phí**:

| Tác động | Khi thêm chỉ mục | Khi bỏ chỉ mục |
| --- | --- | --- |
| Truy vấn đọc | Có thể giảm số hàng phải quét và tránh bước sort | Query từng sử dụng index có thể chuyển sang scan/sort tốn kém |
| Ghi `INSERT/UPDATE/DELETE` | Phải duy trì thêm một cấu trúc; tăng write amplification | Có thể giảm chi phí duy trì index |
| Dung lượng | Tốn thêm disk, page cache và dung lượng backup | Giải phóng không gian của index sau khi xóa thành công |
| I/O và log | Xây index phải quét bảng, sort/ghi dữ liệu, có thể tạo WAL/replication lag | DDL và kế hoạch truy vấn vẫn có thể gây tác động |
| Khóa và đồng thời | Tùy cách tạo index, có thể chặn thao tác ghi hoặc chờ transaction đang tồn tại | Tùy lệnh DROP, có thể yêu cầu khóa và ảnh hưởng query đang chạy |
| Quy tắc dữ liệu | Unique index có thể thực thi tính duy nhất | Xóa index ràng buộc có thể làm mất bảo vệ bất biến nếu được phép |

Một thay đổi index có thể không sửa **một byte dữ liệu nghiệp vụ** nào nhưng vẫn gây downtime qua lock wait hoặc làm mất mục tiêu độ trễ (*latency SLO*). Mục tiêu migration phải bao gồm cả **tính đúng đắn, hiệu năng, độ sẵn sàng và khả năng hoàn nguyên**.

### Chỉ mục không phải ràng buộc nghiệp vụ thay thế mọi kiểm tra

Một **unique index/unique constraint** có thể chặn hai hàng trùng khóa, kể cả khi các request Java đến đồng thời. Đây là bảo vệ dữ liệu ở tầng DB. Ngược lại, một index thường để tăng tốc truy vấn **không** bảo đảm giá trị hợp lệ hay thứ tự commit.

Ví dụ, unique index trên `(tenant_id, external_id)` phù hợp khi mỗi mã ngoài chỉ xuất hiện một lần **trong từng tenant**. Unique index trên `external_id` một mình sẽ áp đặt quy tắc khác và có thể chặn dữ liệu hợp lệ của các tenant khác. Migration phải xác định bất biến cần bảo vệ trước khi chọn khóa index.

## 2. Ví dụ xuyên suốt: tối ưu danh sách đơn hàng

Giả sử ứng dụng SaaS Java có bảng đơn hàng đang hoạt động:

```sql
CREATE TABLE orders (
    order_id     BIGINT PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    version      BIGINT NOT NULL DEFAULT 0
);
```

Một API được gọi thường xuyên để đọc 50 đơn đã thanh toán gần nhất của tenant:

```sql
SELECT order_id, created_at, total_amount, version
FROM orders
WHERE tenant_id = ?
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Nếu chưa có chỉ mục phù hợp, database có thể phải đọc nhiều hàng rồi sort. Một ứng viên chỉ mục PostgreSQL:

```sql
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_recent
ON orders (tenant_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount, version);
```

Thứ tự khóa được thiết kế theo truy vấn: hai cột lọc bằng trước, tiếp đến hai cột sắp xếp. `INCLUDE` thêm dữ liệu payload vào index để **có cơ hội** đọc đủ cột cần thiết mà không phải lấy từng heap tuple. Nó không làm các cột INCLUDE tham gia thứ tự tìm kiếm, và **không bảo đảm** truy vấn sẽ dùng index-only scan: visibility map, thống kê, độ chọn lọc và chi phí thực tế ảnh hưởng kế hoạch.

Nếu chỉ mục trở nên quá rộng, chi phí ghi và không gian có thể lớn hơn lợi ích của việc hạn chế heap access. Có thể bỏ `INCLUDE` hoặc chọn ít cột hơn sau khi đo trên workload đại diện.

**Không được mặc định index trên mọi cột sẽ tốt hơn.** Query planner có thể chọn sequential scan khi bảng nhỏ, điều kiện không chọn lọc hoặc đọc phần lớn dữ liệu. Đánh giá dựa trên kế hoạch và chi phí thực tế, không chỉ dựa vào việc tên index đã xuất hiện trong schema.

## 3. Đo trạng thái trước khi viết migration

Một migration index nên bắt đầu bằng **bằng chứng về truy vấn** và **bảng kế hoạch tác động**:

1. Lưu câu SQL thực tế (kể cả điều kiện `WHERE`, `ORDER BY`, số hàng, mẫu bind value) và tần suất gọi.
2. Đo p50/p95/p99 của use case, số row đọc, thời gian SQL, I/O, lock wait, CPU, WAL rate và replication lag.
3. Xem `EXPLAIN (ANALYZE, BUFFERS)` cho câu `SELECT` trên môi trường kiểm soát, có dữ liệu/kiểu phân bố giống production.
4. Liệt kê index đã có để tránh tạo bản sao gần giống và tăng gánh nặng duy trì.
5. Ước lượng dung lượng index, dung lượng trống cho thao tác sort/build, IOPS, WAL, áp lực trên replica và thời lượng có thể chạy.
6. Xác định DDL đang dùng có thể chặn `INSERT/UPDATE/DELETE` hay không; dự trù `lock_timeout` và điểm hủy an toàn.

Trong PostgreSQL, xem các index đã khai báo và trạng thái hợp lệ của chúng:

```sql
SELECT indexrelid::regclass AS index_name,
       indisunique,
       indisvalid,
       indisready
FROM pg_index
WHERE indrelid = 'public.orders'::regclass
ORDER BY indexrelid::regclass::text;
```

`indisvalid=false` là tín hiệu index **chưa được planner dùng như index hợp lệ**; cần điều tra nguyên nhân và cách cleanup, nhất là sau khi tạo index đồng thời thất bại. `indisready` liên quan khả năng index nhận cập nhật. Không kết luận index hoàn tất chỉ từ sự tồn tại của tên trong catalog.

Quan sát kích thước và thống kê sử dụng (đây là bộ đếm tích lũy, không phải bản ghi đầy đủ của mọi query):

```sql
SELECT indexrelname,
       idx_scan,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public' AND relname = 'orders'
ORDER BY pg_relation_size(indexrelid) DESC;
```

`idx_scan=0` **không chứng minh index vô dụng**: chỉ số có thể vừa reset, ít xảy ra một truy vấn quan trọng, hoặc index phục vụ unique/constraint. Trước khi xóa, phải đối chiếu với quyền ràng buộc, query plan và workload theo chu kỳ ngày/tuần/tháng.

Đo truy vấn SELECT mẫu:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount, version
FROM orders
WHERE tenant_id = 123 AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

`EXPLAIN ANALYZE` **thực thi câu lệnh**; ví dụ trên là SELECT nên phù hợp để đo ở môi trường thử nghiệm. Đừng vô tư chạy `EXPLAIN ANALYZE` trên `UPDATE/DELETE` production: nó có thể làm thay đổi dữ liệu; nếu buộc thử, phải thiết kế transaction và rollback an toàn theo đặc tính câu lệnh. Thời gian chạy, cache nóng/lạnh, số tenant và tham số bind có thể làm kết quả khác nhau.

## 4. CREATE INDEX thường và CREATE INDEX CONCURRENTLY

Trong PostgreSQL, cách tạo index quyết định mức gián đoạn:

```sql
-- Cách truyền thống:
CREATE INDEX idx_orders_tenant_status_recent
ON orders (tenant_id, status, created_at DESC, order_id DESC);

-- Cách xây index đồng thời cho bảng đang có giao dịch ghi:
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_recent
ON orders (tenant_id, status, created_at DESC, order_id DESC);
```

Đây là **hai phương án thay thế**, không phải hai câu cần chạy liên tiếp trên cùng tên index.

| Tính chất | `CREATE INDEX` | `CREATE INDEX CONCURRENTLY` |
| --- | --- | --- |
| Hoạt động ghi cùng lúc | Bản tạo thông thường có thể chặn ghi vào bảng trong thời gian build | Thiết kế để các `INSERT/UPDATE/DELETE` vẫn tiếp tục trong phần lớn quá trình |
| Thời gian và I/O | Thường xây nhanh hơn trong điều kiện tương đương | Thường tốn nhiều việc/quét hơn và có thể chờ giao dịch/snapshot cũ |
| Dùng trong transaction block | Có thể chạy trong một transaction theo quy tắc DDL PostgreSQL | **Không được** chạy bên trong transaction block tường minh |
| Khi lỗi giữa chừng | Transaction có thể rollback toàn bộ thay đổi DDL | Có thể để lại một index **INVALID** cần xử lý |
| Mức khóa | Vẫn cần các khóa để thay đổi schema | Không có nghĩa “không khóa”: các pha vẫn cần lock thích hợp và có thể chờ |

`CREATE INDEX CONCURRENTLY` thường gồm nhiều pha/quét và chờ những transaction liên quan. Nó **không bảo đảm không blocking tuyệt đối**; một transaction dài, DDL khác hay thay đổi topology vẫn có thể khiến migration chạy lâu hoặc bị chặn. Cần kiểm soát thời điểm chạy, lock timeout, statement timeout và số thao tác build đồng thời.

Một ví dụ vận hành trên **cùng một session PostgreSQL**:

```sql
-- Chính sách timeout chỉ có tính minh họa, phải điều chỉnh theo hệ thống.
SET lock_timeout = '5s';
SET statement_timeout = '30min';

-- Câu này không được bị migration tool bao trong BEGIN ... COMMIT.
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_recent
ON orders (tenant_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount, version);
```

`lock_timeout` đặt giới hạn chờ một khóa, không giới hạn toàn bộ thời gian build. `statement_timeout` giới hạn thời gian thực thi statement và có thể hủy một build đang chạy nếu quá ngưỡng, để lại công việc cleanup. Cấu hình phải theo đúng connection/session thực thi DDL; nếu runner dùng connection khác cho mỗi câu, những câu SET phía trên có thể không áp dụng như kỳ vọng.

### Công cụ migration và transaction mặc định

Flyway, Liquibase hoặc công cụ nội bộ có thể mặc định bọc migration trong transaction. Đối với `CREATE INDEX CONCURRENTLY` của PostgreSQL, cần **cấu hình migration đó chạy ngoài transaction** theo khả năng và phiên bản công cụ cụ thể. Không cố vượt lỗi bằng cách chạy index thường trên bảng đang nóng mà chưa đánh giá lock.

Một cách tổ chức dễ kiểm soát:

1. Migration/version dành riêng cho index concurrent, có cấu hình non-transactional rõ.
2. Cơ chế quản lý thời điểm chạy và **chỉ một orchestrator sở hữu rollout**.
3. Kiểm tra sự tồn tại và tình trạng hợp lệ sau khi hoàn thành.
4. Chỉ đánh dấu rollout ứng dụng sẵn sàng dùng index khi query plan/latency thực tế đã được xác minh.

Đừng chạy nhiều bản ứng dụng cùng tự thực thi DDL index lúc khởi động mà không có cơ chế điều phối; sự cạnh tranh schema lock có thể làm startup hoặc DB bị nghẽn.

## 5. Index INVALID và xử lý migration thất bại

Nếu tạo index đồng thời bị hủy, mất kết nối hoặc gặp lỗi trong quá trình xây dựng, PostgreSQL có thể để lại **index entry mang trạng thái không hợp lệ**. Hậu quả có thể gồm tốn không gian và chi phí duy trì cập nhật, mặc dù index không được planner dùng cho truy vấn.

Quy trình xử lý an toàn:

1. **Dừng retry tự động:** lưu mã lỗi, tên index, thời điểm, phiên bản migration và nguyên nhân.
2. **Đọc catalog:** xác minh `indisvalid` và `indisready`; đồng thời kiểm tra có tác vụ build/reindex nào còn chạy.
3. **Đánh giá loại index:** unique index đồng thời thất bại có những trường hợp vẫn ảnh hưởng tới việc thực thi tính duy nhất; không tự xem nó là đối tượng “vô hại”.
4. **Chọn hướng sửa:** với index thường được tạo chưa hợp lệ và không ràng buộc constraint, có thể loại bỏ index invalid bằng thao tác phù hợp rồi tạo lại; một số trường hợp dùng `REINDEX INDEX CONCURRENTLY` theo hỗ trợ của PostgreSQL.
5. **Chỉ coi thành công sau readback:** index phải hợp lệ, kế hoạch truy vấn đã kiểm tra và không còn tác động ngoài dự kiến.

Ví dụ, khi đã xác minh index invalid **không** là phần bắt buộc của một ràng buộc và đã bảo đảm không có build đang chạy:

```sql
-- Không chạy trong explicit transaction block.
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_tenant_status_recent;

-- Sau đó chạy lại CREATE INDEX CONCURRENTLY theo migration đã sửa.
```

Không dùng `CREATE INDEX CONCURRENTLY IF NOT EXISTS` như một dấu hiệu “migration đã hoàn tất”: nếu một index **cùng tên** còn tồn tại nhưng **INVALID**, điều kiện `IF NOT EXISTS` có thể bỏ qua việc tạo mà không làm index sẵn sàng cho query. Tương tự, cùng tên không đồng nghĩa cùng định nghĩa, cùng cột INCLUDE hay cùng predicate.

**Lưu ý về rollback:** câu `DROP INDEX CONCURRENTLY` của PostgreSQL không được chạy trong transaction block, không hỗ trợ `CASCADE`, và không được dùng tùy tiện với index đang hỗ trợ một constraint mà DB quản lý. Với những ràng buộc đó, cần quy trình thay đổi constraint riêng, không “drop thử” ở production.

## 6. Unique index: migration còn là bài toán làm sạch dữ liệu

Thêm một unique index có thể thất bại nếu **dữ liệu cũ đang vi phạm quy tắc**. Ví dụ yêu cầu mỗi tenant chỉ có một địa chỉ email (sau khi chuẩn hóa chữ hoa/chữ thường):

```sql
-- Giả sử bảng customers có tenant_id, email.
SELECT tenant_id, lower(email) AS normalized_email, COUNT(*) AS duplicates
FROM customers
WHERE email IS NOT NULL
GROUP BY tenant_id, lower(email)
HAVING COUNT(*) > 1;
```

Trước khi tạo unique index:

- Xác định **quy tắc null**, cách chuẩn hóa email, collation/case sensitivity và dữ liệu cũ cần xử lý. Nhiều DB cho phép nhiều NULL trong unique index mặc định; yêu cầu “mỗi tenant phải có email” còn cần ràng buộc riêng.
- Dọn dữ liệu lỗi bằng một quy trình có audit, tránh tự xóa tài khoản chỉ để làm index build thành công.
- Triển khai hoặc chuẩn bị đường ghi Java mới sao cho **không tiếp tục tạo bản ghi trùng** trong khi cleanup/build; kiểm tra trùng bằng SELECT ở ứng dụng một mình vẫn có race.
- Dự trù việc xây index đồng thời có thể thất bại vì có duplicate đang tồn tại hoặc xuất hiện trong lúc build.

Một index biểu thức PostgreSQL có thể hỗ trợ chuẩn hóa:

```sql
CREATE UNIQUE INDEX CONCURRENTLY ux_customers_tenant_email_ci
ON customers (tenant_id, lower(email))
WHERE email IS NOT NULL;
```

Ví dụ này chọn **partial unique expression index** để áp dụng quy tắc cho email không null. Đây là một *unique index* bảo vệ dữ liệu, nhưng không phải index nào cũng có thể trực tiếp chuyển thành constraint bảng bằng `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX`; PostgreSQL có các giới hạn với index biểu thức/partial. Không giả định hai cú pháp tương đương trong mọi trường hợp.

**Nguy cơ đáng chú ý:** trong quá trình `CREATE UNIQUE INDEX CONCURRENTLY`, PostgreSQL có thể bắt đầu áp dụng kiểm tra duy nhất trước khi index trở thành hợp lệ. Nếu build thất bại và để lại index invalid, một số trường hợp index vẫn ảnh hưởng các thao tác ghi. Vì vậy cần chuẩn bị đường khôi phục và phối hợp đội vận hành, không chỉ xem đây là lỗi hiệu năng.

## 7. Chỉ mục partial, expression và kế hoạch truy vấn Java

Với bảng `orders`, nếu đa số truy vấn quan tâm riêng `status='PAID'`, có thể cân nhắc index nhỏ hơn:

```sql
CREATE INDEX CONCURRENTLY idx_orders_paid_by_tenant
ON orders (tenant_id, created_at DESC, order_id DESC)
INCLUDE (total_amount, version)
WHERE status = 'PAID';
```

Index này lưu các hàng đáp ứng predicate. Nó có thể tiết kiệm dung lượng nếu `PAID` chỉ là một phần nhỏ bảng và query luôn lọc đúng trạng thái ấy. Tuy nhiên:

- PostgreSQL chỉ dùng partial index khi planner có thể chứng minh điều kiện truy vấn **hàm ý predicate** của index.
- Một query dùng `WHERE status = ?` có thể không dùng partial index ở **generic prepared plan** vì planner không biết giá trị bind ở lúc lập kế hoạch tổng quát; có thể có khác biệt giữa custom/generic plan.
- Nếu use case cần `PENDING` hoặc các trạng thái khác, index partial trên `PAID` không giúp trực tiếp.
- Khi điều kiện trạng thái thay đổi, các hàng có thể phải được thêm/xóa khỏi partial index, vẫn phát sinh write cost.

Không hardcode trạng thái hoặc nối SQL từ HTTP một cách tùy tiện chỉ để ép planner dùng index. Query shape phải phản ánh use case có quyền truy cập và semantics nghiệp vụ rõ. Trong migration, kiểm thử **đúng PreparedStatement và distribution tham số** của Java, không chỉ thử một SQL hằng với literal.

Ví dụ JDBC đọc danh sách đơn đã thanh toán, với query shape phù hợp cho cả index tổng quát lẫn partial index:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class PaidOrderReader {
    public record PaidOrder(
            long orderId, OffsetDateTime createdAt,
            BigDecimal amount, long version) {}

    private final DataSource dataSource;

    public PaidOrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<PaidOrder> latest(long tenantId, int limit)
            throws SQLException {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải nằm trong 1..100");
        }

        String sql = """
            SELECT order_id, created_at, total_amount, version
            FROM orders
            WHERE tenant_id = ? AND status = 'PAID'
            ORDER BY created_at DESC, order_id DESC
            LIMIT ?
            """;
        List<PaidOrder> result = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, tenantId);
            ps.setInt(2, limit);
            ps.setQueryTimeout(5); // giây; hành vi hủy tùy JDBC driver

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    result.add(new PaidOrder(
                            rs.getLong("order_id"),
                            rs.getObject("created_at", OffsetDateTime.class),
                            rs.getBigDecimal("total_amount"),
                            rs.getLong("version")));
                }
            }
        }
        return result;
    }
}
```

Service trả DTO hoàn chỉnh và trả connection về pool khi rời `try-with-resources`. Nó không được **mặc định dựa vào sự tồn tại của index để bảo đảm thời gian chạy**: query timeout chỉ giới hạn chờ thực thi theo hỗ trợ driver, không tự tạo phương án fallback an toàn hoặc tránh pool exhaustion. Khi migration đổi index, theo dõi query latency và timeouts từ **cùng code path** trước/sau thay đổi.

## 8. Expand–migrate–contract cho chỉ mục

Một rollout an toàn cho bảng lớn thường chia thành các pha. Với ví dụ thêm `idx_orders_tenant_status_recent`:

```text
Pha 0: Đo baseline + xác định query/DDL
   |
   v
Pha 1: Expand
        CREATE INDEX CONCURRENTLY (không transaction block)
        Kiểm tra index VALID và kích thước/lag
   |
   v
Pha 2: Rollout ứng dụng
        Query mới sử dụng schema tương thích cũ/mới
        Đo plan, p95/p99, write overhead, lock wait
   |
   v
Pha 3: Contract
        Chỉ khi đã chứng minh index cũ không cần thiết:
        DROP INDEX CONCURRENTLY index_cu
   |
   v
Pha 4: Theo dõi và đóng migration
        Kiểm tra lỗi, ghi nhận rollback/runbook
```

Lý do chia pha: trong triển khai rolling deployment, phiên bản ứng dụng cũ và mới có thể cùng chạy. Một index mới **không bắt buộc** phải thay đổi API Java; vì vậy có thể tạo trước, đo tác động ghi, rồi chuyển query sau. Ngược lại, nếu index cũ phục vụ câu SQL từ một phiên bản ứng dụng vẫn hoạt động, xóa nó quá sớm có thể gây suy giảm hiệu năng mà không cần schema lỗi.

### Backward compatibility và rollback

Đối với index tối ưu hiệu năng, **rollback ứng dụng** thường đơn giản hơn **rollback toàn bộ DDL**: code cũ vẫn có thể chạy khi index mới còn tồn tại. Thường không cần vội xóa index mới ngay khi rollback code nếu quá trình xóa làm tăng rủi ro vận hành; có thể lên lịch dọn sau khi kiểm soát sự cố.

Đối với **unique index** hoặc constraint mới, rollback có thể **không chỉ là xóa index**: quy tắc dữ liệu có thể đã được áp dụng, dữ liệu không còn giống trước và các writer phụ thuộc quy tắc mới. Cần xem đây là migration bất biến nghiệp vụ, có kịch bản thay đổi ngược có phê duyệt riêng.

Một migration tạo index concurrent thường không có atomic rollback DDL như migration SQL trong transaction. Nên có một **rollback/repair runbook** tách biệt: cách nhận biết index invalid, điều kiện khi được drop/rebuild, metric nào cần kiểm tra, ai quyết định cắt chuyển.

## 9. Bỏ index cũ: chỉ sau khi chứng minh an toàn

Trước khi bỏ index, cần kiểm tra:

1. Nó có phục vụ **PRIMARY KEY, UNIQUE, EXCLUDE** hoặc ràng buộc thiết yếu khác không? Index do constraint sở hữu không được loại bỏ tùy tiện.
2. Có code, batch, job hoặc truy vấn hiếm chạy theo lịch tháng/quý cần index không?
3. Query plan mới có dùng index thay thế hay chuyển sang scan/sort tốn kém?
4. Chỉ số write amplification, disk và thời gian migration có thực sự cải thiện sau khi bỏ không?
5. Có kế hoạch phục hồi nếu query chậm và quy trình tạo lại index phù hợp với bảng đang có ghi không?

Đối với index thông thường không thuộc constraint trong PostgreSQL:

```sql
-- Chỉ chạy khi đã đánh giá các điều kiện an toàn.
-- Không nằm trong explicit transaction block.
DROP INDEX CONCURRENTLY IF EXISTS public.idx_orders_status_legacy;
```

Tên `idx_orders_status_legacy` là **ví dụ giả định**, không phải index đã được tạo ở phần trước. Không chạy nếu index đó không thuộc phạm vi được phê duyệt. `IF EXISTS` chỉ giúp tránh lỗi tên không tồn tại; nó không xác nhận index đã đúng loại hoặc an toàn để xóa.

Một khi index đã bị drop, planner có thể đổi kế hoạch ngay. Cần theo dõi sau migration và có phương án **recreate concurrent**; đừng giả định khôi phục một index rất lớn sẽ tức thời hoặc miễn phí.

## 10. Lock, I/O, WAL và replication lag: giám sát khi chạy

PostgreSQL có thể cho quan sát tiến độ tạo index:

```sql
SELECT pid, datname, relid::regclass AS table_name,
       index_relid::regclass AS index_name,
       command, phase, blocks_total, blocks_done
FROM pg_stat_progress_create_index;
```

`phase` có thể cho biết đang build hay đang chờ những transaction/snapshot khác. Các bộ đếm tiến độ phản ánh **pha hiện hành**, không phải dự báo thời gian kết thúc tuyệt đối. Đừng lấy `blocks_done / blocks_total` làm một % hoàn thành toàn bộ migration nếu có nhiều pha với cách đếm khác nhau.

Có thể quan sát các phiên đang chờ khóa:

```sql
SELECT pid, state, wait_event_type, wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       left(query, 160) AS query_preview
FROM pg_stat_activity
WHERE wait_event_type = 'Lock';
```

Việc xem query của session khác phụ thuộc quyền DB; đoạn SQL trên cũng có nguy cơ hiển thị dữ liệu nhạy cảm nếu ứng dụng nối literal vào câu truy vấn — nên hạn chế quyền và cẩn trọng khi log/copy kết quả.

Trong quá trình build cần quan sát:

| Tín hiệu | Nguy cơ gợi ý | Hành động |
| --- | --- | --- |
| DDL chờ lock lâu | Transaction khác đang giữ khóa, migration khác xung đột | Xác định blocker; không kill bừa transaction nghiệp vụ |
| CPU/I/O của primary tăng mạnh | Index build tranh chấp với truy vấn ứng dụng | Hạ concurrency, chọn khung giờ hoặc tạm dừng theo kế hoạch |
| WAL rate và replica lag tăng | Replica không theo kịp thay đổi trong lúc build/ghi | Theo dõi giới hạn disk, băng thông, RPO/read freshness |
| Query p95/p99 tăng | Planner đổi kế hoạch hoặc hệ thống thiếu I/O | So plan trước/sau và kiểm tra load/locks |
| Dung lượng disk giảm nhanh | Tạo index/sort/log tiêu thụ thêm dung lượng | Có ngưỡng dừng và kế hoạch mở rộng/dọn an toàn |
| Ghi chậm hoặc deadlock tăng | Thêm index tăng chi phí DML/lock contention | So sánh tần suất và phân tích transaction, không chỉ đổ cho index |
| Build dừng giữa chừng, index INVALID | Lỗi/hủy DDL concurrent | Kiểm tra catalog và repair, không đánh dấu hoàn tất |

**Không có một con số “tạo index an toàn dưới X giây” cho mọi bảng.** Dung lượng, IOPS, transaction kéo dài, checkpoint, thống kê, replication và workload quyết định thời gian/cửa sổ rủi ro. Chạy thử trên bản sao dữ liệu đại diện và xác định SLO/ngưỡng dừng thực tế.

## 11. Khác biệt giữa các DB và trách nhiệm của ứng dụng Java

| Hệ quản trị | Đặc điểm cần xác minh trước migration index |
| --- | --- |
| **PostgreSQL** | `CREATE/DROP INDEX CONCURRENTLY` có quy tắc không chạy trong transaction block; build lỗi có thể để lại index invalid; xem tiến độ và catalog |
| **MySQL/InnoDB** | `ALTER TABLE ... ADD INDEX` có các lựa chọn `ALGORITHM`/`LOCK` tùy phiên bản và loại DDL; “online DDL” vẫn có metadata lock và một số giới hạn |
| **SQL Server** | Tùy phiên bản/edition/loại index, có tính năng tạo/rebuild online, resumable và các giới hạn; phải xem khả năng hỗ trợ thực tế |
| **Oracle** | Có cơ chế xây/rebuild index online tùy loại và phiên bản; việc chờ/khóa và hỗ trợ cú pháp cần xác minh |
| **SQLite** | Thay đổi schema/index liên quan cơ chế khóa và journal/WAL; không suy từ `CONCURRENTLY` của PostgreSQL |

Trong Java:

- **JDBC/JdbcTemplate:** SQL ghi rõ trong code có thể được thay đổi độc lập với index; dùng `PreparedStatement` và kiểm tra query plan của pattern bind thật.
- **MyBatis/jOOQ:** mapper SQL hoặc mã sinh schema cần khớp migration; không chỉ deploy index rồi để mapper tạo query có thứ tự/điều kiện khác.
- **JPA/Hibernate:** query JPQL, `@Index`, `@Table` và auto schema generation là những cơ chế khác nhau. Annotation khai báo index không bảo đảm một build online an toàn ở production. Nên quản lý DDL có kế hoạch bằng Flyway/Liquibase hoặc quy trình được phê duyệt, tránh auto-update schema không kiểm soát.
- **Connection pool/transaction:** migration DDL có thể làm query chờ; các request giữ connection lâu khi chờ DB dễ gây pool exhaustion. Giới hạn transaction duration và cấu hình timeout rõ ràng.
- **Rolling deployment:** giữ khả năng tương thích giữa các phiên bản ứng dụng trong pha expand/contract, tránh phụ thuộc vào một index chưa hoàn tất.

Một index là **chi tiết vật lý của database**, không nên rò rỉ thành giả định “endpoint này luôn có index X nên không cần pagination”. Application boundary phải vẫn có giới hạn số hàng, quyền truy cập và xử lý timeout khi plan thay đổi.

## 12. Runbook mẫu cho migration trên bảng đang hoạt động

| Giai đoạn | Việc cần làm | Điều kiện vượt qua |
| --- | --- | --- |
| **Trước rollout** | Lấy baseline, kiểm tra index trùng/ràng buộc, estimate disk/IO, kiểm thử ở staging | Đã có query plan, ngưỡng dừng và người chịu trách nhiệm |
| **Chuẩn bị** | Xác nhận backup/restore, phiên bản migration tool, non-transactional DDL, timeout | Có phương án khôi phục riêng cho index invalid |
| **Build** | Chạy `CREATE INDEX CONCURRENTLY` có điều phối một owner, quan sát lock/progress | Không vi phạm SLO và resource guardrails |
| **Verify** | Xem `indisvalid`, size, plan, latency, WAL/replica lag | Index tồn tại **và** valid; hành vi truy vấn đúng |
| **App rollout** | Deploy query/version mới theo canary/rolling, theo dõi read/write workload | p95/p99/errored requests và write overhead trong ngưỡng |
| **Contract** | Đối soát mọi consumer rồi drop index cũ nếu an toàn | Không còn đường truy vấn cần index cũ |
| **Hậu kiểm** | Giám sát thêm một chu kỳ hoạt động, ghi lại quyết định và chi phí | Có số liệu, tài liệu sửa/rollback và owner vận hành |

Một **dấu hiệu thành công kỹ thuật** là công cụ migration báo hoàn tất. Một **dấu hiệu thành công vận hành** là: query đạt yêu cầu, dữ liệu không bị hỏng, write throughput không giảm quá ngưỡng, replica theo kịp và ứng dụng không tăng timeout. Cần cả hai.

## 13. Bài tập và tình huống

### Bài tập 1: chọn cách xây index

Một bảng có 80 triệu hàng, ứng dụng vẫn ghi liên tục. Developer định dùng `CREATE INDEX idx_x ON orders(tenant_id, created_at);` trong migration PostgreSQL mặc định có transaction.

**Câu hỏi:** nguy cơ chính và cách tiếp cận phù hợp hơn là gì?

**Đáp án:** cách tạo thông thường có thể chặn ghi trong thời gian build; với bảng nóng cần đánh giá `CREATE INDEX CONCURRENTLY`, tách migration khỏi transaction block, dự trù I/O/WAL/disk và theo dõi lock/tiến độ. `CONCURRENTLY` không đồng nghĩa bằng không thời gian chờ.

### Bài tập 2: tên index tồn tại nhưng query vẫn chậm

Migration chạy `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_tenant_status_recent ...` rồi log ghi “OK”. Catalog lại báo `indisvalid=false`.

**Câu hỏi:** có thể coi hoàn thành không?

**Đáp án:** không. Tên index tồn tại không bảo đảm index hợp lệ; câu `IF NOT EXISTS` có thể bỏ qua index invalid cũ. Phải điều tra build cũ, xác định cách cleanup/reindex, chạy lại phù hợp và verify cả catalog lẫn query plan.

### Bài tập 3: partial index không được dùng

Index `WHERE status='PAID'` đã có, nhưng một `PreparedStatement` Java dùng `WHERE status=?` với bind `PAID` vẫn chọn sequential scan trong một số lần chạy.

**Câu hỏi:** đây chắc chắn là lỗi DB không?

**Đáp án:** chưa chắc. Generic plan có thể không chứng minh predicate của partial index từ placeholder; ngoài ra thống kê, tỷ lệ hàng lọc và chi phí cũng quyết định plan. Đo query thật, kiểm tra custom/generic plan và cân nhắc SQL use case riêng hoặc index tổng quát khi hợp lý.

### Bài tập 4: thêm uniqueness trên dữ liệu cũ

Hệ thống muốn unique trên `(tenant_id, lower(email))` nhưng truy vấn kiểm tra thấy nhiều email trùng trong cùng tenant.

**Câu hỏi:** có nên cứ chạy `CREATE UNIQUE INDEX CONCURRENTLY` rồi để DB tự xử lý?

**Đáp án:** không. Cần làm sạch dữ liệu theo chính sách nghiệp vụ và ngăn writer tiếp tục tạo trùng, sau đó xây index và kiểm tra kết quả. Một build unique concurrent lỗi còn có thể để lại index invalid ảnh hưởng ghi; phải có runbook xử lý.

### Bài tập 5: xóa index cũ

Sau khi thêm index composite, `pg_stat_user_indexes.idx_scan` cho index cũ đang bằng 0 trong một ngày. Có thể xóa ngay không?

**Đáp án:** chưa. Có thể là index phục vụ constraint, chỉ có workload chạy hằng tuần hoặc thống kê bị reset; cần xem query plan, phụ thuộc ứng dụng và khoảng đo đủ dài. Chỉ drop khi có phương án phục hồi và giám sát sau xóa.

### Checklist trước khi đánh dấu migration thành công

- Chỉ mục mới phục vụ **query thực tế** hay chỉ do suy đoán? Có đo `EXPLAIN` và latency không?
- Có xác định DDL lock behavior, transaction boundary, timeout, kích thước disk/WAL và replication lag chưa?
- Nếu dùng `CONCURRENTLY`, migration tool có thực sự chạy **ngoài transaction block** không?
- Đã kiểm tra index **VALID**, đúng định nghĩa, không bị bỏ qua bởi `IF NOT EXISTS` trên index invalid chưa?
- Với unique/partial/expression index, đã kiểm chứng dữ liệu cũ, predicate, trạng thái writer và concurrency chưa?
- Có tính write amplification, maintenance, backup/restore và khả năng canary/rollback khi planner đổi kế hoạch không?
- Có giữ index cũ đến khi các phiên bản ứng dụng và workload phụ thuộc đã được đối soát không?
- Có runbook cho build bị hủy, index invalid, lock wait kéo dài và drop/recreate không?

**Kết luận:** Migration chỉ mục không chỉ là câu `CREATE INDEX` hay `DROP INDEX`. Nó thay đổi cách DB sử dụng CPU, I/O, WAL, khóa và dung lượng trong khi ứng dụng vẫn hoạt động; với unique index, nó còn thay đổi **quy tắc chấp nhận dữ liệu**. Cách tiếp cận an toàn là **đo trước, tạo theo phương thức phù hợp, quan sát khi chạy, xác minh index hợp lệ, rollout dần và chỉ xóa cấu trúc cũ khi đã chứng minh không còn cần thiết**.
