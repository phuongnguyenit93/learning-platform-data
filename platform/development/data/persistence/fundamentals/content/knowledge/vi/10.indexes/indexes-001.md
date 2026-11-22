# Chỉ mục là gì và vì sao có thể giảm chi phí tra cứu

## Mục tiêu bài học

Sau khi học xong, người học có thể:

1. Giải thích **chỉ mục (index)** là gì và phân biệt nó với dữ liệu được lưu trong bảng.
2. Mô tả vì sao một cấu trúc tra cứu có tổ chức giúp tránh đọc nhiều hàng không liên quan.
3. Theo dõi cách một chỉ mục B-tree hỗ trợ điều kiện bằng, điều kiện khoảng và sắp xếp.
4. Nhận biết khi nào trình tối ưu truy vấn có thể chọn quét bảng thay vì dùng chỉ mục.
5. Tạo, kiểm tra và đánh giá một chỉ mục phù hợp với truy vấn thường gặp trong ứng dụng Java.

Bài thuộc chương **Chỉ mục** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module này đặt chỉ mục trong toàn bộ bài toán lưu trữ bền vững: thiết kế mô hình dữ liệu, lược đồ, truy vấn, giao dịch, cô lập, kiểm soát đồng thời và ranh giới persistence của Java; đồng thời quan tâm đến lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Hiểu chỉ mục giúp đánh giá một truy vấn bằng số công việc mà cơ sở dữ liệu phải làm, thay vì chỉ nhìn vào độ dài câu SQL.

## 1. Vấn đề: tìm vài hàng giữa rất nhiều hàng

Giả sử bảng `orders` lưu hàng triệu đơn hàng. API cần lấy 30 đơn hàng mới nhất của một khách hàng thuộc một tenant cụ thể:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND customer_id = 9001
ORDER BY created_at DESC, id DESC
LIMIT 30;
~~~

Nếu không có đường truy cập thích hợp, hệ quản trị cơ sở dữ liệu (DBMS) có thể phải đọc nhiều trang dữ liệu của bảng, kiểm tra từng hàng, giữ những hàng đáp ứng điều kiện rồi sắp xếp để tìm 30 hàng mới nhất. Cách đọc này gọi là **quét tuần tự bảng** (*sequential scan*, hoặc *table scan* tùy hệ quản trị).

Một bảng lớn thường nằm trên nhiều **trang (page/block)** của thiết bị lưu trữ; PostgreSQL thường dùng trang 8 KiB với cấu hình mặc định. Vì I/O, xử lý bản ghi và truyền dữ liệu có chi phí, việc phải đọc hàng nghìn hoặc hàng triệu trang để lấy vài chục hàng là điều ta muốn tránh.

**Chỉ mục tạo ra một đường dẫn tra cứu khác**, cho phép DBMS nhanh chóng xác định vị trí của các khóa phù hợp và chỉ đọc những phần cần thiết. Tương tự mục lục theo thuật ngữ trong sách, người đọc tra từ khóa rồi tìm đến những trang có nội dung liên quan, thay vì lật toàn bộ sách. Phép so sánh này hữu ích để hình dung, nhưng chỉ mục cơ sở dữ liệu là một cấu trúc vật lý được DBMS duy trì và sử dụng trong kế hoạch truy vấn.

## 2. Chỉ mục là gì?

**Chỉ mục** là một cấu trúc dữ liệu phụ được xây dựng trên một hoặc nhiều cột hoặc biểu thức, giúp hệ quản trị định vị, lọc hoặc duyệt dữ liệu theo một thứ tự có ích cho truy vấn.

Một mô hình khái niệm đơn giản:

| Thành phần | Vai trò |
| --- | --- |
| Bảng dữ liệu | Lưu các hàng và giá trị thuộc nghiệp vụ |
| Khóa chỉ mục (*index key*) | Giá trị mà DBMS dùng để tìm hoặc so sánh, ví dụ `tenant_id`, `created_at` |
| Vị trí/trỏ tới hàng | Thông tin giúp DBMS tìm dữ liệu liên quan trong bảng, hoặc tìm khóa bản ghi theo thiết kế của engine |
| Trang và cấu trúc chỉ mục | Tổ chức khóa để tìm nhanh mà không phải duyệt tất cả hàng |
| Bộ tối ưu truy vấn (*query planner/optimizer*) | Lựa chọn quét bảng, tra chỉ mục hoặc phương án khác dựa trên ước lượng chi phí |

Trong PostgreSQL, các mục của chỉ mục B-tree thường gắn khóa với **TID** (vị trí phiên bản hàng trong heap). Với InnoDB của MySQL, bảng thường được tổ chức theo **clustered index** của khóa chính; chỉ mục phụ mang giá trị khóa chính để tìm hàng. Vì thế, cách chỉ mục dẫn đến dữ liệu cụ thể khác nhau giữa các engine.

Chỉ mục không mặc định thay thế cho bảng. Khi câu truy vấn cần giá trị không có sẵn trong chỉ mục, cơ sở dữ liệu vẫn phải đọc bản ghi từ bảng (hoặc cấu trúc lưu trữ cơ sở tương ứng). Một số đường truy cập có thể đọc trực tiếp từ chỉ mục khi đáp ứng đủ điều kiện; đây là tối ưu bổ sung, không phải đặc tính bắt buộc của mọi chỉ mục.

### 2.1. Chỉ mục không phải bản sao được sắp xếp của toàn bộ bảng

Ví dụ, khi tạo:

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

DBMS duy trì một cấu trúc để tìm `customer_id`. Chỉ mục này không tự động lưu mọi cột như `total_amount`, `status` hay `shipping_address`. Nếu cần những cột ấy, truy vấn có thể phải truy xuất thêm dữ liệu gốc.

Chỉ mục cũng không ngụ ý rằng các hàng trong bảng được lưu vật lý theo đúng thứ tự khóa. Trong PostgreSQL, B-tree index và heap là hai cấu trúc tách biệt; bảng vẫn có thể nằm trên những trang dữ liệu không liên tiếp.

### 2.2. Khóa chính, UNIQUE và chỉ mục

Trong PostgreSQL, khai báo `PRIMARY KEY` hoặc `UNIQUE` thông thường được hỗ trợ bằng một chỉ mục B-tree duy nhất (trừ các biến thể/đặc thù mà hệ quản trị hỗ trợ). Chỉ mục này có hai vai trò: hỗ trợ truy cập và thực thi ràng buộc toàn vẹn.

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(14, 2) NOT NULL,
    status       TEXT NOT NULL
);
~~~

Ở PostgreSQL, `id` đã có đường tra cứu nhờ khóa chính; không cần tạo thêm chỉ mục trùng hệt trên `(id)`. Trái lại, một chỉ mục trên `(tenant_id, customer_id, created_at)` giải quyết mẫu truy vấn khác. **Chỉ mục tra cứu và ràng buộc nghiệp vụ không thể đánh đồng**: không xóa chỉ mục thực thi khóa duy nhất chỉ vì tưởng rằng nó ít được SELECT sử dụng.

## 3. B-tree giúp tìm kiếm như thế nào?

B-tree là cấu trúc chỉ mục thông dụng trong các hệ quản trị quan hệ, phù hợp với so sánh bằng, khoảng và nhiều phép sắp xếp. Các khóa được giữ theo thứ tự. Mỗi trang bên trong chứa thông tin định hướng để quyết định nên tiếp tục theo nhánh nào; các trang lá chứa các mục liên quan đến khóa.

Sơ đồ dưới đây minh họa nguyên lý, không thể hiện định dạng chính xác của trang PostgreSQL:

~~~text
                  [40 | 80]              <- trang gốc
                  /   |   \
                 /    |    \
            [10,25] [50,65] [90,110]     <- vùng khóa ở các trang lá
               |       |       |
             vị trí  vị trí   vị trí
              hàng    hàng     hàng
~~~

Để tìm khóa `65`, DBMS dùng thông tin ở trang gốc để chọn nhánh chứa vùng giá trị phù hợp, rồi tìm đến mục tương ứng ở vùng lá; nó không phải duyệt tuần tự các khóa `10`, `25`, `50` trước đó.

Vì một trang chỉ mục có thể chứa nhiều khóa và liên kết tới nhiều trang con, cây thường có **fan-out** lớn và số tầng ít ngay cả khi bảng có nhiều hàng.

Về mặt ý tưởng, chi phí tìm một vị trí khóa trong B-tree cân bằng tăng gần `O(log_B N)` với `B` là số nhánh hữu hiệu mỗi trang và `N` là số mục. Nếu cần trả về `K` kết quả, còn có chi phí duyệt những mục phù hợp và có thể đọc các trang chứa hàng dữ liệu. Công thức này mô tả **số bước cấu trúc**, không phải cam kết độ trễ trong mili giây: cache, truy cập ngẫu nhiên, số hàng khớp, MVCC, phân vùng và máy chủ đang chịu tải đều ảnh hưởng thời gian thực.

### 3.1. Ba kiểu truy vấn B-tree thường hỗ trợ tốt

**So sánh bằng**, nhất là khi chỉ có ít hàng phù hợp:

~~~sql
SELECT id, tenant_id, customer_id
FROM orders
WHERE id = 13579;
~~~

Nếu `id` là khóa chính, DBMS có đường tra cứu trực tiếp thay vì duyệt toàn bộ bảng. Tìm một khóa không tồn tại cũng có thể kết thúc sau khi kiểm tra vùng chỉ mục thích hợp.

**So sánh theo khoảng**, vì các khóa cùng vùng nằm gần nhau trong thứ tự chỉ mục:

~~~sql
SELECT id, created_at
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

Một chỉ mục có tiền tố phù hợp `created_at` có thể giúp tìm điểm bắt đầu của khoảng rồi duyệt phần liên quan. Truy vấn này vẫn có thể quét bảng nếu khoảng bao phủ phần lớn dữ liệu.

**Sắp xếp kết hợp giới hạn kết quả**, nhất là khi thứ tự khóa chỉ mục tương ứng thứ tự cần xuất:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = 42
  AND customer_id = 9001
ORDER BY created_at DESC, id DESC
LIMIT 30;
~~~

Với một chỉ mục đúng thứ tự khóa, DBMS có thể tìm vùng của khách hàng và lấy những mục đầu tiên theo thời gian, tránh phải sắp xếp rất nhiều hàng rồi bỏ phần lớn kết quả.

## 4. Ví dụ thực tế: thiết kế một đường truy cập cho API Java

Đây là chỉ mục B-tree đa cột dành cho truy vấn lấy đơn hàng gần đây:

~~~sql
CREATE INDEX idx_orders_tenant_customer_created_id
ON orders (tenant_id, customer_id, created_at DESC, id DESC);
~~~

Lý do chọn thứ tự:

1. `tenant_id` là ranh giới dữ liệu: mọi truy vấn của API đều giới hạn theo tenant.
2. `customer_id` tiếp tục thu hẹp trong tenant bằng phép so sánh bằng.
3. `created_at DESC` tương ứng nhu cầu lấy đơn hàng mới nhất trước.
4. `id DESC` tạo thứ tự xác định khi nhiều đơn hàng trùng `created_at`, phù hợp cho phân trang ổn định.

Lưu ý: thứ tự `tenant_id, customer_id` trong hai điều kiện bằng có thể cho kết quả tốt tương tự đối với **chính truy vấn này**, nhưng khác nhau khi xét các truy vấn chỉ lọc một trong hai cột. Không có thứ tự cột tối ưu cho mọi workload.

### 4.1. Đường đi của câu truy vấn

Với chỉ mục trên, một kế hoạch có khả năng xảy ra là:

~~~text
API / repository
      |
      v
WHERE tenant_id = ? AND customer_id = ?
      |
      v
Tìm vùng khóa phù hợp trong B-tree
      |
      v
Duyệt theo (created_at DESC, id DESC)
      |
      v
Lấy thông tin hàng cần thiết từ bảng
      |
      v
Dừng khi đủ 30 kết quả / gửi về Java
~~~

Điểm tiết kiệm chính: DBMS có khả năng **không cần quét mọi đơn hàng của tenant và không cần sắp xếp toàn bộ đơn hàng của khách hàng**. Tuy vậy, nó vẫn phải đọc các trang chỉ mục, kiểm tra tính hiển thị của hàng và có thể đọc dữ liệu ở heap.

Nếu bảng chỉ có vài trăm hàng, hoặc query lấy hầu hết bảng, quét bảng có thể nhanh hơn. **Cơ sở dữ liệu quyết định dùng chỉ mục hay không** bằng kế hoạch thực thi, chứ bản thân lệnh `CREATE INDEX` không ép mọi SELECT sử dụng nó.

### 4.2. Lượng dữ liệu và độ chọn lọc

**Độ chọn lọc** phản ánh điều kiện lọc thu hẹp tập dữ liệu đến mức nào. Có thể hiểu trực giác:

`Tỷ lệ hàng khớp = số hàng thỏa WHERE / tổng số hàng`

Giả sử **dữ liệu minh họa**, bảng có 5 triệu đơn hàng:

- `WHERE id = 13579` tối đa một hàng, rất phù hợp cho tra cứu chính xác bằng khóa chính.
- `WHERE customer_id = 9001 AND tenant_id = 42` chỉ khớp vài trăm hàng: một chỉ mục đúng cột có thể mang lại lợi ích lớn.
- `WHERE status = 'PAID'` khớp 4 triệu hàng: DBMS thường phải xử lý phần lớn bảng, nên chỉ mục đơn cột trên `status` có thể không đáng dùng cho truy vấn này.

Khái niệm chọn lọc không chỉ là số lượng giá trị khác nhau của một cột. Phân bố thực tế có thể lệch: tenant lớn có hàng triệu đơn, tenant nhỏ chỉ vài đơn. Cần kiểm tra cả **ước lượng thống kê** lẫn số hàng trả về thực tế.

### 4.3. Ví dụ thứ tự cột tạo khác biệt

Với chỉ mục:

~~~sql
ON orders (tenant_id, customer_id, created_at DESC, id DESC)
~~~

các mẫu truy vấn nên cân nhắc:

| Mẫu truy vấn | Khả năng tận dụng chỉ mục |
| --- | --- |
| `tenant_id = ? AND customer_id = ?` | Có thể tra cứu vùng khóa rất phù hợp |
| Thêm `ORDER BY created_at DESC, id DESC LIMIT 30` | Có thể tránh sort và dừng sau ít kết quả |
| Chỉ `tenant_id = ?` | Có thể sử dụng tiền tố đầu, nhưng cần đọc nhiều vùng khách hàng |
| Chỉ `customer_id = ?` | Thiếu khóa tiền tố `tenant_id`, lợi ích tìm kiếm thường hạn chế |
| Chỉ lọc `total_amount > ?` | Không phải khóa của chỉ mục này |

Bảng nói về **xu hướng**, không phải quy tắc cứng cho mọi DBMS, kích thước bảng hay kế hoạch. Một số bộ tối ưu có thể kết hợp nhiều chỉ mục hoặc chọn kiểu quét khác.

## 5. DBMS chọn chỉ mục dựa trên chi phí nào?

Để trả kết quả, DBMS phải ước lượng tổng công việc của nhiều phương án:

- **Sequential Scan:** đọc các trang của bảng, lọc từng hàng. Có lợi khi bảng nhỏ, khi rất nhiều hàng khớp hoặc khi đọc tuần tự hiệu quả.
- **Index Scan:** tìm khóa trong chỉ mục, theo các mục trỏ tới hàng trong bảng. Có lợi khi số hàng cần truy cập đủ nhỏ hoặc chỉ mục giúp thực hiện thứ tự mong muốn.
- **Bitmap Index/Heap Scan** (PostgreSQL): thu thập tập vị trí hàng từ chỉ mục rồi truy cập các trang heap theo cách giảm một phần truy cập ngẫu nhiên.
- **Index Only Scan** (PostgreSQL): có thể trả kết quả chủ yếu từ chỉ mục khi mọi cột cần thiết được chỉ mục cung cấp; vẫn chịu ảnh hưởng của quy tắc hiển thị phiên bản hàng trong MVCC.

Chi phí thực tế bao gồm đọc trang từ bộ nhớ hoặc đĩa, CPU lọc và so sánh, truy cập bảng để lấy cột thiếu, sắp xếp, tải kết quả vào ứng dụng và lượng hàng cần trả về.

Ví dụ, khi một truy vấn trả về 80% số hàng, đi qua chỉ mục rồi đọc nhiều trang của bảng có thể tốn hơn quét liên tục bảng. Còn khi truy vấn trả về 30 trong hàng triệu hàng, đường tra cứu có chỉ mục có thể tiết kiệm rất nhiều công việc.

**Chỉ mục giảm chi phí tra cứu khi nó giảm tổng số trang hoặc tổng số thao tác mà kế hoạch thực thi phải làm.** Không đủ căn cứ nếu chỉ thấy thời gian của một lần chạy giảm: lần chạy thứ hai có thể nhanh vì dữ liệu đã nằm trong cache.

## 6. Dùng EXPLAIN để quan sát thay vì phỏng đoán

Ví dụ sau dành cho **PostgreSQL**. Khi chưa có chỉ mục chuyên dụng, hãy ghi nhận kế hoạch của truy vấn:

~~~sql
ANALYZE orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND customer_id = 9001
ORDER BY created_at DESC, id DESC
LIMIT 30;
~~~

Sau đó tạo chỉ mục được đề xuất ở phần 4 rồi chạy lại truy vấn trên dữ liệu tương đương:

~~~sql
CREATE INDEX idx_orders_tenant_customer_created_id
ON orders (tenant_id, customer_id, created_at DESC, id DESC);

ANALYZE orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND customer_id = 9001
ORDER BY created_at DESC, id DESC
LIMIT 30;
~~~

Lệnh `EXPLAIN (ANALYZE, BUFFERS)` thực sự **chạy truy vấn**, cho biết kế hoạch và số liệu đo. Trong đầu ra, tập trung vào:

| Thông tin | Cách đọc |
| --- | --- |
| `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, `Index Only Scan` | Cơ sở dữ liệu chọn đường đọc nào |
| `Index Cond` | Điều kiện nào thực sự dùng để tra khóa chỉ mục |
| `Filter` | Điều kiện nào được kiểm tra thêm sau khi lấy ứng viên |
| `rows` ước lượng và `actual rows` | Kiểm tra sai lệch của thống kê và thực tế |
| `Buffers: shared hit/read` | Trang đã có trong cache hoặc cần đọc vào bộ đệm |
| `Sort` | Có còn phải sắp xếp hay không |
| `Execution Time` | Thời gian thực thi của lần chạy cụ thể, chưa đủ đại diện cho tải thật |

Kết quả giả định có thể thay đổi từ quét bảng cộng với sort sang một `Index Scan using idx_orders_tenant_customer_created_id` mà không cần sort. Điều này chỉ xảy ra nếu planner đánh giá chỉ mục rẻ hơn. Không nên tự tạo một output `EXPLAIN` giả rồi coi đó là bằng chứng đã đo.

Đặc biệt, `total_amount` không nằm trong chỉ mục mẫu, vì vậy PostgreSQL thường cần tìm phiên bản hàng trong heap để lấy cột này. Muốn bàn tới `Index Only Scan`, phải xét các cột cần trả về và cơ chế hiển thị trong MVCC; chỉ viết SELECT ít cột không bảo đảm loại bỏ việc đọc heap.

### 6.1. Đọc chỉ số và ngữ cảnh đo

Đừng đánh giá trên một bảng hầu như rỗng. Một thử nghiệm đáng tin cậy nên có:

1. Dữ liệu cùng quy mô, phân bố tenant, số đơn trên từng khách hàng và xu hướng cập nhật gần với production.
2. Cùng một truy vấn và cùng tham số, đo nhiều lần khi cache lạnh/ấm; tránh so sánh các tình huống không tương đương.
3. Các chỉ số: p50/p95/p99 độ trễ SQL/API, số trang đọc, CPU, thông lượng đọc và các chỉ số ghi.
4. Đánh giá thêm tác động INSERT, UPDATE, DELETE và dung lượng vì mọi chỉ mục mới cần được lưu và bảo trì.

Đối với production, `EXPLAIN ANALYZE` trên câu lệnh thay đổi dữ liệu có thể gây tác động thật. Hãy kiểm soát tác động khi đo các lệnh ghi; ví dụ SELECT trong bài là đọc thuần.

## 7. Liên hệ với ranh giới persistence trong Java

Đường đọc hiệu quả đòi hỏi câu SQL do repository/DAO phát ra **phù hợp với cấu trúc chỉ mục**. Một truy vấn có chỉ mục tốt vẫn có thể tốn kém nếu ứng dụng đọc quá nhiều bản ghi, sử dụng `SELECT *` không cần thiết hoặc tạo hàng trăm truy vấn nhỏ kiểu N+1.

Ví dụ JDBC dùng `DataSource` và tham số hóa:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderRepository {
    public record RecentOrder(long id, Instant createdAt,
                              BigDecimal totalAmount) {}

    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<RecentOrder> findRecent(
            long tenantId, long customerId, int requestedLimit)
            throws SQLException {

        int limit = Math.max(1, Math.min(requestedLimit, 100));
        String sql = """
            SELECT id, created_at, total_amount
            FROM orders
            WHERE tenant_id = ?
              AND customer_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        List<RecentOrder> result = new ArrayList<>();
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setLong(2, customerId);
            statement.setInt(3, limit);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    result.add(new RecentOrder(
                        rs.getLong("id"),
                        rs.getTimestamp("created_at").toInstant(),
                        rs.getBigDecimal("total_amount")));
                }
            }
        }
        return result;
    }
}
~~~

Ví dụ sử dụng cú pháp Java 17. `PreparedStatement` truyền giá trị dưới dạng tham số và tránh ghép dữ liệu không tin cậy vào câu SQL. Giới hạn kết quả giúp ứng dụng không đọc quá nhiều hàng; thứ tự `created_at DESC, id DESC` tương ứng thứ tự chỉ mục.

Tuy nhiên, **điều kiện `tenant_id` trong SQL không tự nó xác thực quyền truy cập**. Tầng ứng dụng vẫn phải xác minh người gọi được phép xem tenant và customer tương ứng, hoặc dùng cơ chế phân quyền/row-level security phù hợp. Chỉ mục chỉ tối ưu cách truy cập dữ liệu.

Với ứng dụng dùng ORM như JPA/Hibernate, câu SQL **thực sự phát ra** mới quyết định chỉ mục nào hữu ích. Kiểm tra SQL và tham số trong log/trace có kiểm soát, sau đó phân tích plan ở database. Không suy luận chỉ từ tên hàm `findRecentOrders()` hoặc tên thuộc tính Java.

## 8. Những trường hợp tạo chỉ mục chưa chắc làm truy vấn nhanh

### 8.1. Truy vấn lấy quá nhiều hàng

Nếu báo cáo lấy đa số hàng của bảng, chi phí truy cập từng hàng qua chỉ mục có thể lớn hơn quét tuần tự. Khi có điều kiện lọc nhưng vẫn khớp hàng triệu hàng, **độ chọn lọc thấp** khiến lợi ích của chỉ mục bị giảm.

### 8.2. Cột được biến đổi trong điều kiện lọc

Ví dụ:

~~~sql
SELECT id
FROM orders
WHERE DATE(created_at) = DATE '2026-11-22';
~~~

Với chỉ mục B-tree thông thường trên `created_at`, áp dụng hàm lên cột có thể khiến DBMS khó dùng điều kiện khoảng trực tiếp trên khóa. Trong PostgreSQL, có thể viết điều kiện theo khoảng thời gian thay vì ép kiểu từng hàng:

~~~sql
SELECT id
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-22 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-23 00:00:00+00';
~~~

Hai câu truy vấn chỉ tương đương khi đã xác định đúng múi giờ nghiệp vụ và cách chuyển đổi từ `TIMESTAMPTZ` sang ngày. Ví dụ thứ hai đang lọc **ngày UTC**. Nếu nghiệp vụ dùng ngày Việt Nam, phải xây ranh giới thời gian theo `Asia/Ho_Chi_Minh` rồi quy đổi chính xác. Tránh đổi cú pháp SQL làm sai ngữ nghĩa.

Nếu cần thường xuyên tìm theo kết quả biểu thức, một **expression index** có thể phù hợp trong PostgreSQL; cần đo và cân nhắc chi phí riêng.

### 8.3. Chỉ mục không đúng tiền tố hay thứ tự sắp xếp

Có chỉ mục trên `(tenant_id, customer_id, created_at)` không có nghĩa truy vấn chỉ lọc `created_at` sẽ nhanh. Trật tự khóa phù hợp với điều kiện bằng, khoảng và sắp xếp của workload cụ thể mới tạo lợi ích.

### 8.4. Bảng nhỏ, thống kê cũ hoặc phân bố lệch

DBMS có thể quét bảng nhỏ trong rất ít trang, nhanh hơn thao tác tra index. Hoặc nó ước lượng sai số hàng vì thống kê cũ, khiến plan chưa tối ưu. Cập nhật `ANALYZE`, kiểm tra `estimated rows` so với `actual rows`, và thử các giá trị tenant có quy mô khác nhau.

### 8.5. Dạng tìm kiếm không phù hợp B-tree

Điều kiện tìm chuỗi con như `LIKE '%abc%'` thường không được phục vụ hiệu quả bằng B-tree thông thường trên cả chuỗi. Tìm kiếm toàn văn, JSONB, không gian hoặc khớp gần đúng có thể cần loại chỉ mục chuyên dụng tùy engine, như GIN hoặc GiST trong PostgreSQL. Chọn cấu trúc theo **toán tử truy vấn**, không chỉ theo kiểu dữ liệu.

## 9. Chỉ mục cũng có chi phí duy trì

Chỉ mục giúp giảm công việc đọc ở một số câu truy vấn nhưng đổi lại:

- **INSERT** có thể thêm một mục vào chỉ mục.
- **UPDATE** có thể yêu cầu cập nhật mục tương ứng nếu khóa/chỉ mục liên quan thay đổi.
- **DELETE** dẫn tới xử lý các mục chỉ mục theo cơ chế phiên bản và dọn dẹp của engine.
- **Lưu trữ** tăng do các trang chỉ mục, bản ghi WAL/redo và chi phí sao lưu/khôi phục.
- **Bộ nhớ đệm** phải chia sẻ giữa trang bảng và trang chỉ mục.

Chi phí chính xác tùy engine, số lượng/loại chỉ mục, dữ liệu và cách tổ chức giao dịch. Vì vậy, đừng tạo chỉ mục cho mọi cột. Hãy ưu tiên những truy vấn có tần suất hoặc SLO quan trọng và **đo cả đường đọc lẫn đường ghi**. Chủ đề này sẽ được đào sâu ở bài về đánh đổi giữa tốc độ đọc, tốc độ ghi và dung lượng.

Khi nâng cấp schema, thêm chỉ mục trên bảng lớn có thể cần thời gian, tài nguyên và ảnh hưởng giao dịch; PostgreSQL hỗ trợ `CREATE INDEX CONCURRENTLY` cho nhiều trường hợp cần hạn chế chặn ghi, nhưng có điều kiện sử dụng riêng. Chỉ mục mới là một thay đổi migration cần được thử nghiệm và giám sát, giống các thay đổi persistence khác.

## 10. Quy trình chọn và xác minh một chỉ mục

Áp dụng tuần tự các bước sau:

1. **Chọn truy vấn quan trọng** từ API hoặc log truy vấn, bao gồm câu SQL thực, giá trị tham số, tần suất, số hàng trả về và SLO.
2. **Xem kế hoạch hiện tại**, đặc biệt các bước quét bảng, lọc, sắp xếp, lượng hàng ước lượng/thực và buffer I/O.
3. **Đề xuất khóa chỉ mục**, bắt đầu từ điều kiện bằng có tính phân biệt/tiền tố thích hợp, sau đó xét khoảng, `ORDER BY`, `LIMIT` và những truy vấn liên quan.
4. **Thử nghiệm trên dữ liệu đại diện**, so sánh plan và đo p95/p99, buffer, tài nguyên CPU/I/O, chi phí ghi và dung lượng.
5. **Triển khai bằng migration có kiểm soát**, theo dõi độ trễ sau triển khai và xác nhận không phá hỏng các truy vấn/khóa ràng buộc khác.
6. **Định kỳ đánh giá lại** khi dữ liệu, nghiệp vụ hoặc cấu trúc truy vấn thay đổi; không quyết định xóa chỉ mục chỉ dựa trên một thống kê sử dụng ngắn hạn.

Phân biệt hai câu hỏi: “Chỉ mục **có tồn tại** không?” và “Kế hoạch truy vấn **có dùng hữu ích** chỉ mục không?”. Câu hỏi thứ hai cần kế hoạch thực thi và phép đo.

## 11. Tự kiểm tra

**Câu 1.** Vì sao truy vấn lấy một đơn hàng theo khóa chính có thể nhanh trên bảng nhiều triệu hàng?

*Gợi ý trả lời:* Đường tra cứu trên khóa chính có thể tìm nhanh vùng khóa và xác định hàng cần đọc. Số trang/khóa cần duyệt nhỏ hơn nhiều so với việc quét toàn bảng, dù thời gian thực tế còn phụ thuộc cache và kiểu lưu trữ.

**Câu 2.** Một chỉ mục `(tenant_id, customer_id, created_at DESC)` có thể giúp truy vấn `WHERE customer_id = ? ORDER BY created_at DESC LIMIT 20` tốt như truy vấn có thêm `tenant_id = ?` không?

*Gợi ý trả lời:* Thường không, vì thiếu điều kiện ràng buộc tiền tố `tenant_id`. Cần đo và có thể xem xét chỉ mục khác nếu truy vấn chỉ theo customer là thường xuyên; đồng thời không được bỏ điều kiện tenant nếu nó cần cho tính đúng đắn và quyền truy cập.

**Câu 3.** Vì sao một truy vấn dùng `Seq Scan` không nhất thiết là lỗi?

*Gợi ý trả lời:* Nếu bảng nhỏ hoặc truy vấn cần phần lớn hàng, quét tuần tự có thể là kế hoạch rẻ nhất. Chỉ mục là một lựa chọn truy cập, không phải mục tiêu tự thân.

**Bài tập thực hành.** Với bảng `orders` ở phần 2, hãy đưa ra một chỉ mục cho truy vấn `WHERE tenant_id = ? AND customer_id = ? ORDER BY created_at DESC, id DESC LIMIT 30`. Sau đó dùng `EXPLAIN (ANALYZE, BUFFERS)` để so sánh trên dữ liệu đủ lớn. Ghi lại số hàng, plan, buffer, execution time và tác động của chỉ mục lên dung lượng. Lặp lại với một tenant nhỏ và một tenant có số đơn rất lớn để xem kết quả có khác nhau hay không.

## Ghi nhớ

**Chỉ mục là đường truy cập có cấu trúc giúp DBMS tìm các hàng cần thiết mà không phải duyệt toàn bộ dữ liệu.** B-tree hữu ích cho nhiều truy vấn bằng, khoảng và sắp xếp, nhưng lợi ích phụ thuộc điều kiện lọc, thứ tự cột, số hàng khớp, cấu trúc lưu trữ và kế hoạch thực thi. Khi thiết kế persistence cho Java, hãy xem chỉ mục như một phần của thiết kế truy vấn và lược đồ: hiểu cơ chế, thử trên workload thực, rồi đo kết quả trước khi triển khai.
