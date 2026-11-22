# Phân biệt phân vùng dữ liệu với phân vùng mạng

Trong một hệ thống lưu trữ phân tán, cụm từ **phân vùng** có thể chỉ hai khái niệm hoàn toàn khác nhau:

- **Phân vùng dữ liệu (data partitioning):** một **quyết định thiết kế** nhằm chia dữ liệu thành các phần để lưu trữ, truy vấn hoặc mở rộng.
- **Phân vùng mạng (network partition):** một **kiểu sự cố truyền thông** khiến các nút hoặc nhóm nút không trao đổi thông điệp đáng tin cậy trong một khoảng thời gian.

Cả hai đều xuất hiện trong chương **Nền tảng phân tán** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, nhưng chúng giải quyết và gây ra những vấn đề khác nhau. Phân vùng dữ liệu trả lời câu hỏi **“bản ghi này được lưu ở đâu?”**. Phân vùng mạng đặt câu hỏi **“khi các nút không thể liên lạc, chúng được phép làm gì mà vẫn giữ đúng dữ liệu?”**.

Hiểu sự khác biệt đặc biệt quan trọng trong Java persistence: ứng dụng cần định tuyến truy vấn đến đúng shard, đặt ranh giới transaction, xử lý connection/failover, kiểm soát retry và xác định bảo đảm nhất quán của dữ liệu. Một hệ thống có thể phân vùng dữ liệu tốt nhưng vẫn chịu sự cố mạng; ngược lại, một database không chia shard vẫn có thể bị phân vùng mạng giữa primary và replica.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Định nghĩa **data partitioning**, **table partition**, **shard**, **replica** và **network partition** bằng ví dụ cụ thể.
2. Phân biệt **chia dữ liệu để mở rộng** với **mất liên lạc giữa các nút**.
3. Giải thích khi nào cần phân vùng ngang, phân vùng dọc, range/hash partitioning, và chi phí rebalancing.
4. Mô tả ảnh hưởng của network partition đến leader, quorum, read/write availability và khả năng xuất hiện split-brain.
5. Diễn giải lựa chọn trong **CAP** mà không nhầm CAP consistency với tính Consistency trong ACID.
6. Viết SQL PostgreSQL minh họa partitioning và mã Java định tuyến đọc theo shard key.
7. Thiết kế cách xử lý timeout, **unknown commit outcome**, failover, idempotency và các bài kiểm thử lỗi mạng.

## 2. Tóm tắt so sánh trước khi đi sâu

| Tiêu chí | Phân vùng dữ liệu | Phân vùng mạng |
|---|---|---|
| Bản chất | Cách tổ chức hoặc phân bố dữ liệu có chủ đích | Sự cố mất hoặc suy giảm truyền thông giữa các nút |
| Câu hỏi chính | Bản ghi nằm ở partition/shard nào? | Nút A có thể liên lạc và thống nhất trạng thái với nút B không? |
| Có cần nhiều máy? | **Không**: table partitioning có thể nằm trên một PostgreSQL instance | Có ít nhất hai thực thể/nút cần trao đổi nhưng không giao tiếp được như mong đợi |
| Mục đích/động cơ | Scale, quản lý dữ liệu, giảm phạm vi scan, chia tải | Không phải tính năng muốn bật để scale; hệ thống phải **chịu đựng** sự cố này |
| Công nghệ liên quan | Partition key, range/hash/list, shard router, rebalancing | Timeout, failure detector, consensus, leader election, quorum, fencing |
| Rủi ro chính | Skew, hot shard, cross-shard join/transaction, thay đổi mapping | Không đạt quorum, mất khả dụng, dữ liệu đọc trễ, split-brain nếu điều phối sai |
| Cách kiểm tra | EXPLAIN/pruning, phân bố bản ghi, shard load và truy vấn theo khóa | Fault injection có kiểm soát, failover, kiểm thử consistency và recovery |

**Không suy ra “dữ liệu đã phân vùng” đồng nghĩa “hệ thống chịu được phân vùng mạng”.** Phân vùng dữ liệu không tự tạo replica, không bảo đảm failover và không quyết định mức nhất quán khi mất liên lạc.

## 3. Phân vùng dữ liệu là gì?

**Data partitioning** chia một tập dữ liệu logic thành các nhóm nhỏ dựa trên tiêu chí xác định. Mục tiêu có thể là quản lý dữ liệu theo thời gian, cải thiện hiệu năng truy vấn, giảm kích thước vùng index, chia tải hoặc mở rộng khả năng lưu trữ.

Ví dụ một bảng đơn hàng có hàng trăm triệu hàng. Có thể chia theo:

- **Thời gian:** đơn tháng 11/2026 nằm trong một partition, đơn tháng 12/2026 trong partition khác.
- **Khách hàng hoặc tenant:** các tenant khác nhau được phân tới các shard khác nhau.
- **Vùng địa lý:** dữ liệu phục vụ miền Nam, miền Bắc, quốc gia hoặc khu vực khác nhau.
- **Hash của khóa:** dùng hàm băm của tenant_id để phân bố tương đối đều.

### 3.1. Horizontal partitioning (phân vùng ngang)

Chia **các hàng** của cùng một cấu trúc logic theo một khóa. Ví dụ:

~~~text
Bảng logic: orders
       |
       +-- Partition tháng 11: đơn có order_date trong tháng 11
       +-- Partition tháng 12: đơn có order_date trong tháng 12
       +-- Partition tháng 01: đơn có order_date trong tháng 01
~~~

Mỗi phần chứa các hàng khác nhau nhưng thường có cùng bộ cột. Hệ quản trị hoặc tầng ứng dụng quyết định hàng nào thuộc phần nào.

### 3.2. Vertical partitioning (phân vùng dọc)

Chia **các cột hoặc nhóm thuộc tính** theo nhu cầu truy cập. Ví dụ dữ liệu hồ sơ khách hàng có phần cơ bản và phần thông tin ít dùng:

~~~text
customers_core: (customer_id, name, status)
customers_private: (customer_id, address, extra_profile)
~~~

Hai phần liên kết bằng customer_id. Cách này có thể tách truy cập và bảo mật, nhưng tăng nhu cầu join/lookup nhiều lần. Không phải cứ tách hai bảng là đã có sharding sang hai máy.

### 3.3. Partitioning khác sharding

Trong thực tế, từ **sharding** thường được dùng cho **phân vùng ngang qua nhiều database instance hoặc nút**, mỗi shard giữ một tập con dữ liệu.

~~~text
Ứng dụng Java
      |
      v
  Shard Router
   /    |    \
  /     |     \
Shard A Shard B Shard C
Tenant  Tenant  Tenant
1,4... 2,5... 3,6...
~~~

Tuy nhiên, **table partitioning** của PostgreSQL có thể chỉ chia một bảng thành các partition vật lý trong **cùng một instance**. Nó giúp quản lý dữ liệu và partition pruning, nhưng không tự cung cấp khả năng chịu mất máy hay phân tán giao dịch.

**Replicating** lại là chuyện khác: replica chứa bản sao của cùng dữ liệu hoặc cùng shard, không phải tập dữ liệu khác biệt theo nghĩa chia ngang. Một hệ thống thực tế có thể **shard dữ liệu và tạo nhiều replica cho mỗi shard**.

## 4. Các cách đặt khóa phân vùng dữ liệu

| Chiến lược | Cách làm | Điểm mạnh | Rủi ro |
|---|---|---|---|
| **Range** | Chia theo khoảng thời gian, ID hoặc giá trị | Dễ prune khi query theo khoảng; archive dữ liệu cũ thuận tiện | Dữ liệu mới có thể tập trung vào partition nóng |
| **List** | Chia theo danh sách giá trị xác định | Hợp với vùng, nhóm nghiệp vụ hoặc trạng thái | Phân bố lệch, cần quản lý giá trị mới |
| **Hash** | Băm khóa rồi chọn partition | Có thể trải tải tương đối đều | Query range kém thuận tiện; thay số partition có thể gây di chuyển nhiều hàng |
| **Composite** | Kết hợp nhiều lớp partition, ví dụ range rồi hash | Hỗ trợ cả vòng đời dữ liệu và phân bố | Phức tạp trong quản trị, index và định tuyến |
| **Directory-based** | Bảng cấu hình/catalog map key → shard | Dễ điều phối di chuyển tenant theo đơn vị | Phải bảo vệ tính đúng, độ sẵn sàng và version của routing catalog |

Chọn khóa phân vùng phải dựa trên **mẫu truy vấn**. Nếu API thường lọc theo tenant_id nhưng dữ liệu chỉ chia theo một ID không liên quan, Java hoặc DBMS có thể cần **fan-out** tới nhiều partition/shard để tìm kết quả.

### 4.1. Shard key ảnh hưởng truy vấn và transaction

Giả sử bảng đơn hàng được chia theo **tenant_id**.

- Truy vấn “lấy đơn hàng của tenant 42” có thể đến **một shard** nếu routing chính xác.
- Truy vấn “tìm mọi đơn hàng có trạng thái FAILED trên tất cả tenant” có thể cần quét **nhiều shard** rồi tổng hợp.
- Một transaction chuyển dữ liệu giữa hai tenant có thể liên quan **hai shard**; transaction cục bộ trên một Connection không tự làm giao dịch liên shard trở nên nguyên tử.

Một khóa chia dữ liệu tốt giúp những thao tác **thường đi cùng nhau** nằm cùng shard. Nhưng không có khóa nào tối ưu cho mọi loại truy vấn: cần đánh đổi giữa scale, locality, access pattern và khả năng thay đổi kiến trúc.

### 4.2. Hot shard và data skew

Phân vùng dữ liệu không bảo đảm tải được phân đều. Một tenant cực lớn hoặc partition chứa “tháng hiện tại” có thể chiếm nhiều I/O trong khi những shard khác gần như nhàn rỗi.

Các dấu hiệu cần theo dõi:

- Kích thước và số hàng mỗi partition/shard.
- QPS, latency p95/p99, CPU và I/O theo shard.
- Tỷ lệ truy vấn phải fan-out.
- Tốc độ phát sinh dữ liệu mới và số lượng hàng nóng.
- Thời gian rebalancing và ảnh hưởng tới truy vấn đang chạy.

**Skew** là mất cân đối về dữ liệu/tải; nó khác **network partition**, dù cả hai đều có thể làm một nhóm request bị timeout.

## 5. Thực hành: table partitioning bằng PostgreSQL

Ví dụ bảng sự kiện giao dịch được partition theo **thời gian tạo**. Mỗi tháng là một partition trong cùng PostgreSQL instance.

~~~sql
CREATE TABLE payment_events (
    event_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    tenant_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE payment_events_2026_11
    PARTITION OF payment_events
    FOR VALUES FROM ('2026-11-01 00:00:00+00')
               TO   ('2026-12-01 00:00:00+00');

CREATE TABLE payment_events_2026_12
    PARTITION OF payment_events
    FOR VALUES FROM ('2026-12-01 00:00:00+00')
               TO   ('2027-01-01 00:00:00+00');

CREATE INDEX payment_events_tenant_time_idx
    ON payment_events (tenant_id, occurred_at);
~~~

**Vì sao khóa chính gồm cả occurred_at?** Trong PostgreSQL, ràng buộc **PRIMARY KEY/UNIQUE trên bảng partitioned** phải bao gồm các cột khóa partition theo yêu cầu hiện thực, vì index dùng để kiểm tra unique không phải một global index độc lập xuyên mọi partition. Vì vậy, **event_id riêng lẻ không được chính bảng partitioned này bảo đảm duy nhất trên mọi tháng**. Nếu ứng dụng cần event_id toàn cục, phải chọn thiết kế phát ID và cơ chế bảo vệ tính duy nhất bổ sung phù hợp.

Chèn dữ liệu qua bảng cha:

~~~sql
INSERT INTO payment_events
    (event_id, occurred_at, tenant_id, event_type, payload)
VALUES
    (1, '2026-11-10 09:00:00+00', 42,
     'PAYMENT_CREATED', '{"amount": 125000}'),
    (2, '2026-12-10 10:00:00+00', 42,
     'PAYMENT_SETTLED', '{"amount": 125000}');
~~~

Truy vấn theo khoảng:

~~~sql
EXPLAIN
SELECT event_id, occurred_at, event_type
FROM payment_events
WHERE tenant_id = 42
  AND occurred_at >= '2026-11-01 00:00:00+00'
  AND occurred_at <  '2026-12-01 00:00:00+00'
ORDER BY occurred_at DESC;
~~~

DBMS có thể **partition prune**, tức bỏ qua các partition không thể chứa hàng thỏa điều kiện. Kế hoạch EXPLAIN cụ thể phụ thuộc statistics, phiên bản, cách viết predicate và dữ liệu; không bảo đảm luôn dùng index hoặc chỉ đọc đúng một partition trong mọi trường hợp.

### 5.1. Các giới hạn quan trọng của table partitioning

1. **Không tự chuyển dữ liệu sang nhiều máy** chỉ vì dùng PARTITION BY.
2. **Không tự có replica/failover**: nếu máy DB chứa tất cả partition ngừng, dịch vụ vẫn bị ảnh hưởng.
3. **Phải quản lý partition mới**: một INSERT ngoài mọi khoảng đã khai báo có thể lỗi nếu không có default partition hoặc quy trình tạo partition đúng lúc.
4. **Index, VACUUM, thống kê và retention** vẫn cần được quản trị.
5. **Unique/foreign key** có các hạn chế hoặc chi phí theo phiên bản và cấu trúc partition.
6. **Partition pruning cần điều kiện phù hợp với khóa phân vùng**, không phải tăng hiệu năng cho mọi truy vấn một cách tự động.

Bài thực hành này minh họa **phân vùng dữ liệu**, không mô phỏng phân vùng mạng.

## 6. Sharding: định tuyến tới nhiều database instance

Khi dữ liệu quá lớn hoặc tải vượt khả năng một instance, có thể dùng **application-level sharding**, **database middleware** hoặc nền tảng distributed SQL hỗ trợ tự động phân bố.

Ví dụ chia tenant_id thành ba shard:

~~~text
              Java API
                 |
            tenant_id = 42
                 |
           Shard Resolver
             /   |   \
            v    v    v
         Shard0 Shard1 Shard2
           |      |      |
        DB node DB node DB node
~~~

Một hàm đơn giản có thể tính **hash(tenant_id) mod 3** để chọn shard. Nhưng khi tăng từ 3 lên 4 shard, nhiều tenant đổi vị trí theo phép modulo; việc sửa số shard trong code **không tự di chuyển dữ liệu**.

Hệ thống production cần có một chiến lược như:

- **Consistent hashing** hoặc danh mục routing có version.
- Quy trình chuyển dữ liệu theo đợt và đối soát.
- Điều phối khi dữ liệu đang di chuyển: chuyển route, đồng bộ thay đổi, tránh đọc/ghi sai shard.
- Khả năng rollback kế hoạch migration khi phát hiện lỗi.
- Theo dõi số tenant và lưu lượng trên mỗi shard.

### 6.1. Ví dụ Java JDBC định tuyến truy vấn đọc

Mỗi shard có cùng schema **tenant_orders** và lưu tập tenant khác nhau. Ví dụ DDL chạy **riêng trong mỗi database shard**:

~~~sql
CREATE TABLE tenant_orders (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Một router Java minh họa cách chọn shard từ **tenant_id**:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import javax.sql.DataSource;

public final class ShardedOrderReader {
    public record Order(long id, String status, BigDecimal amount) {}

    private final List<DataSource> shards;

    public ShardedOrderReader(List<DataSource> shards) {
        if (shards == null || shards.isEmpty()) {
            throw new IllegalArgumentException("Thiếu DataSource");
        }
        this.shards = List.copyOf(shards);
    }

    private DataSource resolve(long tenantId) {
        // Minh họa fixed topology. KHÔNG đổi shard count/order
        // khi chưa có quy trình migration dữ liệu và routing.
        int hash = Long.hashCode(tenantId);
        int index = Math.floorMod(hash, shards.size());
        return shards.get(index);
    }

    public Optional<Order> find(
            long tenantId, long orderId) throws SQLException {
        if (tenantId <= 0 || orderId <= 0) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }

        String sql = """
                SELECT order_id, status, amount
                FROM tenant_orders
                WHERE tenant_id = ? AND order_id = ?
                """;

        try (Connection connection = resolve(tenantId).getConnection();
             PreparedStatement query = connection.prepareStatement(sql)) {
            query.setLong(1, tenantId);
            query.setLong(2, orderId);

            try (ResultSet rows = query.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Order(
                        rows.getLong("order_id"),
                        rows.getString("status"),
                        rows.getBigDecimal("amount")));
            }
        }
    }
}
~~~

**Ý nghĩa:** DataSource tương ứng với shard được chọn từ tenant_id. **WHERE tenant_id = ?** còn giúp phân tách dữ liệu ở tầng SQL và hỗ trợ ràng buộc. Nhưng đây chỉ là **routing demo**, không phải bộ điều phối sharding production: chưa có catalog/version, health/failover, reshard, distributed transaction, phân quyền tenant, hay consistency giữa replicas.

**Thận trọng:** nếu đổi số lượng hoặc thứ tự các phần tử trong danh sách DataSource, phép chia lấy dư có thể đưa cùng tenant đến database khác. Không thực hiện thay đổi ấy trước khi có kế hoạch di chuyển và xác minh dữ liệu.

## 7. Phân vùng mạng là gì?

**Network partition** xảy ra khi các nút cần liên lạc không thể trao đổi thông điệp đáng tin cậy với nhau trong một khoảng thời gian, dù một hoặc nhiều nút vẫn đang chạy.

Ví dụ có ba nút dữ liệu A, B, C:

~~~text
Trước sự cố:
    A <------> B <------> C
     \__________________/

Khi liên kết mạng bị chia:
    A <------> B     X     C

A và B vẫn liên lạc, C không liên lạc được với A/B.
C có thể đang hoạt động nhưng không biết trạng thái mới nhất của A/B.
~~~

Từ bên C, việc không nhận được thông điệp có thể do:

- Network drop hoặc đường truyền bị ngắt.
- Độ trễ quá lớn khiến yêu cầu vượt timeout.
- Firewall/routing/proxy sai cấu hình.
- Nút bên kia bị treo, quá tải hoặc đã dừng.
- Cơ chế phát hiện lỗi chưa đủ thông tin để phân biệt các khả năng trên.

**Timeout không tự chứng minh một nút đã chết.** Trong hệ phân tán, khi thông điệp không đến, một nút không thể luôn xác định ngay **“đối tác chết”** hay **“mạng đang chậm/mất liên lạc”**. Quyết định failover phải dùng giao thức điều phối, không chỉ thử ping vài lần rồi tự mở quyền ghi cho cả hai phía.

### 7.1. Network partition không nhất thiết làm mọi request thất bại

Một ứng dụng chỉ đọc dữ liệu đã có trên node C có thể vẫn nhận được kết quả tại C trong một số mô hình. Nhưng kết quả đó có thể **cũ** nếu C không nhận được các bản cập nhật mới từ A/B.

Ngược lại, một hệ thống yêu cầu ghi phải được quorum chấp nhận có thể **từ chối ghi tại C** dù C đang chạy khỏe, để tránh trạng thái hai bên tự xác nhận các cập nhật xung đột.

Vì vậy, cần hỏi chính xác **loại thao tác nào còn được phép** thay vì chỉ hỏi “database có online không?”.

## 8. Hai khái niệm độc lập nhưng có thể xảy ra đồng thời

Một hệ thống có thể ở một trong bốn tình huống:

| Phân vùng dữ liệu? | Phân vùng mạng? | Ví dụ | Vấn đề cần giải quyết |
|---|---|---|---|
| Không | Không | Một PostgreSQL instance khỏe, mọi client kết nối bình thường | SQL, transaction và tài nguyên thông thường |
| Có | Không | Đơn hàng chia theo tenant ở ba shard, mạng thông suốt | Định tuyến, phân bố tải, transaction giữa shard |
| Không | Có | Một dataset được replica trên ba nút nhưng C mất liên lạc | Quorum, leader, quyền đọc/ghi, dữ liệu trễ |
| Có | Có | Nhiều shard, mỗi shard có replicas; một vùng mạng bị tách | Cả routing theo shard **lẫn** điều phối/quorum của từng nhóm replica |

Ví dụ dữ liệu đơn hàng chia thành **Shard X** và **Shard Y**, mỗi shard có một primary và hai replicas. Một sự cố mạng có thể cắt một replica của **Shard X** ra khỏi quorum nhưng không ảnh hưởng tới tất cả replica của **Shard Y**.

**Phân vùng dữ liệu** quyết định dòng đơn hàng thuộc X hay Y. **Phân vùng mạng** quyết định các replica của X hoặc Y có thể xác nhận/nhìn thấy cùng một trạng thái hay không.

## 9. Replication, leader và nguy cơ split-brain

**Replication** tạo bản sao của một phần dữ liệu để nâng khả năng chịu lỗi, phục vụ đọc hoặc tăng độ bền theo kiến trúc. Replication khác sharding: các replica của một shard cùng chứa **bản sao dữ liệu của shard đó**.

~~~text
                 Shard tenant 0..999
                         |
                    Leader A
                    /      \
                   v        v
               Replica B  Replica C
~~~

Nếu B và C mất liên lạc với A, một lỗi nguy hiểm là **hai phía đều tin mình có quyền ghi chính**. Khi cả A và một node mới được promote tự chấp nhận ghi trên cùng dữ liệu, đó có thể là **split-brain**.

Split-brain **không tự động xảy ra** chỉ vì mạng bị chia. Một giao thức leader election, quorum, **term/epoch** và fencing đúng có thể ngăn hai leader hợp lệ cùng nhận ghi. Nguy cơ xuất hiện khi quá trình điều phối failover, cấu hình hoặc cơ chế chặn leader cũ bị sai.

### 9.1. Fencing và epoch có tác dụng gì?

Một hệ thống có thể cấp quyền ghi cho leader theo **term/epoch** tăng dần. Thành phần lưu trữ hoặc coordinator chỉ chấp nhận leader có token/epoch hợp lệ; leader cũ bị **fence** khi có leader mới.

Điều này ngăn tình huống: A bị cô lập, B được promote thành leader, mạng hồi phục rồi A tiếp tục ghi như thể mình vẫn là leader. **Fencing phải được kiểm soát tại nơi tác dụng ghi thực sự được chấp nhận**; chỉ đổi cờ trong bộ nhớ Java không đủ nếu A vẫn có thể ghi vào shared storage.

### 9.2. Asynchronous và synchronous replication

- **Replication bất đồng bộ:** primary có thể xác nhận COMMIT trước khi replica nhận được thay đổi. Failover sang replica chậm có thể làm mất một số transaction đã xác nhận ở primary cũ.
- **Replication đồng bộ:** một số cơ chế commit đợi xác nhận từ nút khác, có thể giảm cửa sổ mất dữ liệu nhưng tăng độ trễ và có thể giảm khả dụng ghi khi mất liên lạc/quorum.

Tên “synchronous” không đồng nghĩa mọi replica đã áp dụng và trả dữ liệu mới nhất. Cần kiểm tra chính xác **mức xác nhận**: đã nhận qua mạng, đã ghi vào bộ nhớ, đã flush bền vững hay đã apply/hiển thị.

## 10. CAP: mạng bị chia thì phải đánh đổi gì?

Trong bối cảnh CAP, **C** (*Consistency*) là dạng tính nhất quán mạnh gần với **linearizability** trên dữ liệu được nhìn như một bản sao duy nhất; nó **không đồng nghĩa** chữ C của ACID là sự giữ các ràng buộc nghiệp vụ. **A** (*Availability*) là mỗi yêu cầu tới một nút không lỗi theo mô hình phải nhận được phản hồi hợp lệ, không phải “99,99% uptime”. **P** (*Partition tolerance*) là khả năng hệ thống tiếp tục đối mặt với việc các nút không trao đổi thông điệp.

Khi một phân vùng mạng đang tồn tại, hệ thống không thể đồng thời duy trì **linearizable consistency** và **availability cho mọi yêu cầu** trên cả hai phía của phân vùng, theo các giả định của mô hình CAP.

Ví dụ một hàng lưu số dư được replica ở hai phía tách biệt:

- Nếu cả hai phía đều cho phép cập nhật và trả thành công độc lập, các bản sao có thể mâu thuẫn; không còn bảo đảm đọc/ghi linearizable như một bản sao.
- Nếu chỉ phía có quyền/quorum mới được ghi, phía cô lập có thể từ chối hoặc chờ; giữ consistency nhưng hy sinh availability của một số request.

**Không nên nói “mỗi database luôn chọn đúng hai chữ C/A/P”** như ba tùy chọn cấu hình độc lập. Sự đánh đổi trong CAP xuất hiện **khi network partition thực sự xảy ra**; khi mạng thông suốt, vẫn có nhiều mức độ trễ và độ nhất quán để tối ưu. Cũng không nên suy từ CAP rằng tất cả truy vấn phải đồng loạt dừng hoặc một DB “AP” là có thể bỏ qua mọi bất biến nghiệp vụ.

### 10.1. Ví dụ hai chiến lược khi phân vùng mạng

~~~text
              Mạng bị chia
      [A, B có quorum]    X    [C cô lập]
              |                   |
   Từ chối ghi trên C?      C vẫn muốn ghi?
              |                   |
     Ưu tiên tính đúng     Ưu tiên khả năng nhận ghi
    trên một lịch thống nhất   ở cả hai phía có thể tạo
                               xung đột cần hòa giải
~~~

Cách phù hợp phụ thuộc dữ liệu. Tồn kho hoặc chuyển tiền thường đòi hỏi quy tắc mạnh hơn một bảng chỉ ghi nhận lượt xem hoặc sự kiện có thể hòa giải.

## 11. Quorum là gì và có giới hạn gì?

**Quorum** là ngưỡng đủ số nút tham gia xác nhận để một thao tác hoặc quyết định được coi là hợp lệ trong một giao thức. Với nhóm ba replica, nhiều giao thức dùng **đa số = 2/3**.

~~~text
Replica: A, B, C
Sự cố mạng: A <-> B     X     C

Nhóm A+B có thể đủ 2/3 để tiếp tục hoạt động theo giao thức.
Nút C một mình không đủ quorum để tự nhận quyền ghi/leader.
~~~

Trong mô hình quorum đọc/ghi đơn giản với **N** replica, các công thức thường được nhắc đến là:

\[
R + W > N,\qquad W > \frac{N}{2}
\]

Trong đó **R** là ngưỡng replica tham gia một lần đọc, **W** là ngưỡng ghi. Công thức diễn tả khả năng **giao nhau của các tập quorum** khi membership cố định. Nhưng **điều kiện giao nhau không tự động bảo đảm linearizability**: còn cần xử lý phiên bản dữ liệu, thứ tự thao tác, ghi đồng thời, leader/consensus, thay đổi membership và lỗi thông điệp.

Ví dụ: **N=3, R=2, W=2** cho quorum giao nhau, nhưng không thể kết luận mọi hệ thống cấu hình số đó đều linearizable. Cần xem giao thức cụ thể như consensus/replication protocol của nền tảng.

### 11.1. Quorum và khả dụng dưới phân vùng mạng

Khi nhóm A+B đạt quorum, nó có thể tiếp tục xử lý một số thao tác theo giao thức. C cô lập có thể phải từ chối ghi, dù CPU và đĩa của C đều khỏe. Đó là hành vi **có chủ đích** để tránh nhận ghi không thể hòa giải.

**Đừng điều khiển failover chỉ bằng ping:** không nhận heartbeat có thể do mạng chậm. Thực hiện failover không được khiến hai primary cùng phục vụ ghi ngoài cơ chế fencing.

## 12. Ảnh hưởng đến ứng dụng Java và ranh giới transaction

Phân vùng dữ liệu và phân vùng mạng tác động đến persistence theo hai cách rất khác nhau.

### 12.1. Khi dữ liệu được sharding

Một repository Java phải biết **shard key** và route đúng DataSource. Nếu cùng một nghiệp vụ chỉ cập nhật dữ liệu trên một shard, có thể dùng transaction JDBC cục bộ.

Nếu cập nhật **hai shard**:

~~~text
Connection A -> Shard A: UPDATE tài khoản nguồn
Connection B -> Shard B: UPDATE tài khoản đích
~~~

Hai lệnh **Connection.commit()** riêng không tạo thành một commit nguyên tử. Nếu A commit và B thất bại, dữ liệu bị ghi nửa chừng. Cần thiết kế lại locality hoặc dùng giao thức phù hợp như saga/outbox, cơ chế giao dịch phân tán được hỗ trợ, hoặc chuyển bất biến về nơi có thể cập nhật nguyên tử.

**Không coi @Transactional ở một service bất kỳ là bảo đảm toàn bộ database/shard cùng commit**: transaction manager và nguồn dữ liệu quyết định phạm vi thực tế.

### 12.2. Khi có phân vùng mạng

Trường hợp client Java gửi COMMIT rồi mất kết nối:

~~~text
Java Client            Node đang nhận ghi
    |                         |
    |------ COMMIT ---------->|
    |                   Có thể đã commit
    X mất đường truyền        |
    |<---- phản hồi mất -------|
~~~

Client không thể kết luận chắc chắn DB chưa commit. Có thể transaction đã commit nhưng phản hồi mất; cũng có thể node bị hủy, hết quorum hoặc failover đã thay trạng thái cụm.

Đây là **unknown commit outcome**. Reconnect tới một node mới **không chuyển transaction cũ sang**; cũng không chứng minh node mới đã thấy đủ WAL từ node cũ nếu replication bất đồng bộ.

Thiết kế nghiệp vụ ghi quan trọng nên:

1. Có **operation_id/idempotency key ổn định** cho cùng một thao tác.
2. Lưu mã đó cùng thay đổi nghiệp vụ **trong cùng transaction** ở nguồn dữ liệu có thẩm quyền.
3. Sau lỗi kết nối/COMMIT không rõ, đối soát mã và các trường nghiệp vụ trên nơi được coi là authoritative theo cơ chế failover.
4. Phân biệt **transaction đã bị DB từ chối rõ ràng** với **giao dịch chưa thể xác nhận thành bại**.
5. Không tạo operation_id mới để retry chuyển tiền/đặt hàng một cách mù quáng.
6. Với hiệu ứng ngoài DB (email, message broker, cổng thanh toán), dùng outbox/idempotent consumer hoặc cơ chế bù trừ phù hợp.

Một transaction bị DB xác nhận hủy do serialization failure có thể retry **toàn bộ transaction** nếu nghiệp vụ cho phép. Một timeout mạng ở COMMIT thì cần **đối soát**, không retry vô điều kiện.

## 13. Đọc từ replica: stale reads và read-your-writes

Sharding quyết định **nơi chứa từng nhóm dữ liệu**; replication quyết định **nơi tồn tại nhiều bản sao của nhóm đó**. Khi Java có thể đọc từ replica, điều quan trọng là mức nhất quán:

| Mô hình đọc | Điều có thể xảy ra | Hướng áp dụng |
|---|---|---|
| Đọc từ primary đã xác nhận thao tác | Có thể nhìn thấy cập nhật theo bảo đảm DB/giao thức | Các quyết định nghiệp vụ cần consistency mạnh |
| Đọc từ asynchronous replica | Có thể chưa nhìn thấy COMMIT mới nhất trên primary | Dashboard, báo cáo hoặc nội dung chấp nhận trễ |
| Read-your-writes | Cùng client cần thấy bản ghi mình vừa ghi | Stick to primary, session token/LSN hoặc cơ chế nền tảng hỗ trợ |
| Eventual consistency | Các replica dần hội tụ khi cập nhật tới nơi | Dữ liệu có thể trễ và ứng dụng phải chấp nhận |

Network partition có thể làm **replication lag** tăng đến mức dữ liệu trên một phía ngày càng cũ. **Một replica vẫn trả SELECT thành công không chứng minh dữ liệu là mới nhất**.

Ví dụ: người dùng vừa tạo đơn hàng ở primary, sau đó được điều hướng tới replica chậm và thấy “không tìm thấy đơn”. Nếu API coi đó là bằng chứng việc tạo đơn thất bại, nó có thể tạo đơn trùng. Cần chọn nơi đọc và chính sách session consistency phù hợp.

## 14. Failover, routing và stale metadata

Khi một shard có nhiều replica và primary lỗi, tầng điều phối có thể promote node mới. Nhưng Java cần kết nối tới đúng node sau failover.

Các yếu tố có thể gây lỗi:

- **DNS cache/TTL:** ứng dụng vẫn dùng địa chỉ cũ trong một khoảng thời gian.
- **Connection pool:** còn các kết nối cũ đến node không còn phục vụ ghi.
- **Routing catalog:** ánh xạ tenant → shard đã đổi trong lúc reshard nhưng một instance dùng version cũ.
- **Replication lag:** node mới chưa chắc có toàn bộ transaction đã commit trên primary cũ nếu replicate async.
- **Leader fencing:** node cũ không được tiếp tục ghi sau khi node mới được công nhận.
- **Retry storm:** nhiều instance cùng reconnect và retry dồn dập sau khi DB phục hồi.

**Giải pháp không phải tự động “thử node kế tiếp trong danh sách và ghi vào đó”**. Việc lựa chọn primary hợp lệ, quorum, quyền ghi và fencing phải dựa trên giao thức của nền tảng, không dựa vào phỏng đoán ở repository.

### 14.1. Tại sao phân vùng dữ liệu phức tạp hơn khi có network partition?

Một shard catalog có thể chỉ tới Shard A, nhưng A có các replicas ở hai phía mạng. Ứng dụng cần cả:

1. **Routing đúng shard** theo key.
2. **Routing đúng replica/leader hợp lệ** của shard ấy theo trạng thái cluster.

Đúng shard mà sai primary có thể gây lỗi đọc-only, stale read hoặc nguy cơ ghi không hợp lệ. Đúng primary nhưng sai shard có thể khiến “không tìm thấy bản ghi” dù dữ liệu nằm ở nơi khác.

## 15. Vận hành và quan sát hai loại phân vùng

### 15.1. Metric cho phân vùng dữ liệu

- Kích thước và số hàng trên mỗi partition/shard.
- QPS, p95/p99 latency, I/O và CPU theo shard.
- Hot key/hot tenant và tỷ lệ phân bố dữ liệu.
- Số query fan-out qua nhiều shard.
- Tỷ lệ partition pruning trên các truy vấn điển hình.
- Trạng thái rebalancing, routing catalog version và số lỗi route sai.
- Tỷ lệ cross-shard transaction hoặc công việc bù trừ.

### 15.2. Metric cho phân vùng mạng

- RTT, packet loss, timeout và số lần mất kết nối giữa các nút.
- Heartbeat/failure detector và chuyển trạng thái quorum.
- Leader election/term/epoch, lần promote/failover.
- Replication lag, WAL/LSN lag và thời gian replica phục hồi.
- Tỷ lệ read/write bị từ chối vì thiếu quorum.
- Số request có **unknown commit outcome** và thời gian đối soát.
- Retry attempts, connection pool pending và tình trạng reconnect storm.

Đừng chỉ nhìn một metric “DB up/down”. Một node có thể hoạt động nhưng bị tách mạng; một shard có thể vẫn trả read nhưng không trả write; một replica có thể trả kết quả nhưng đã trễ đáng kể.

### 15.3. Truy vấn PostgreSQL tham khảo

Xem bảng cha và các partition trực tiếp:

~~~sql
SELECT
    inhparent::regclass AS parent_table,
    inhrelid::regclass AS child_partition
FROM pg_inherits
WHERE inhparent = 'payment_events'::regclass
ORDER BY child_partition;
~~~

Xem kích thước mỗi relation liên quan:

~~~sql
SELECT
    relname,
    pg_size_pretty(pg_total_relation_size(oid)) AS total_size
FROM pg_class
WHERE relname LIKE 'payment_events_2026_%'
ORDER BY relname;
~~~

Kiểm tra một PostgreSQL node đang trong trạng thái standby/recovery:

~~~sql
SELECT pg_is_in_recovery() AS is_in_recovery;
~~~

Truy vấn **pg_is_in_recovery()** giúp xác định trạng thái recovery của instance, **không phải một giao thức kiểm tra quorum hay phát hiện network partition**. Hệ thống HA cần kết hợp trạng thái cluster và công cụ điều phối phù hợp.

## 16. Kiểm thử thực hành có kiểm soát

Nên dùng **môi trường staging độc lập**, dữ liệu giả và có backup trước khi thử bất kỳ kịch bản failover hoặc lỗi mạng nào. Không tự ngắt mạng production để “thử độ bền”.

| Kịch bản | Điều cần xác minh |
|---|---|
| Query theo partition key của PostgreSQL | EXPLAIN thể hiện partition pruning phù hợp và kết quả đúng |
| Query không có partition key | Quan sát có phải scan nhiều partition và tăng tải hay không |
| Tenant A và B nằm ở hai shard | Java router chọn đúng DataSource, truy vấn có tenant_id |
| Thêm shard mới | Migration/routing version tránh làm mất tenant khi mapping thay đổi |
| Một replica bị tách khỏi quorum | Nút cô lập không tự nhận ghi trái giao thức; request được trả lỗi rõ |
| Primary gặp sự cố và failover | Node mới được công nhận hợp lệ, leader cũ bị fence, client cập nhật route |
| Replica bất đồng bộ bị trễ | API có yêu cầu read-your-writes không đọc nhầm dữ liệu cũ |
| Lỗi mạng quanh COMMIT | Ứng dụng không nhân đôi nghiệp vụ, dùng operation_id để đối soát |
| Kết nối hồi phục đồng loạt | Pool/retry được giới hạn; không tạo reconnect storm |
| Một shard nóng bất thường | Hạn mức và theo dõi giúp giảm tác động tới shard khác trong phạm vi kiến trúc |

**Kiểm tra kết quả nghiệp vụ**, không chỉ kiểm tra HTTP 200. Chẳng hạn tổng số đơn hàng được tạo cho cùng operation_id phải đúng một hiệu ứng; không có hai leader cùng xác nhận ghi cho cùng phiên bản dữ liệu; cross-shard chuyển tiền không được ghi nửa chừng mà không có cơ chế bù trừ.

### 16.1. Câu hỏi cần trả lời sau test

1. Có ghi vào sai shard sau thay đổi routing không?
2. Có read stale từ replica trong luồng đòi hỏi đọc nhất quán không?
3. Khi không đạt quorum, DB trả lỗi sớm hay để request chờ tới timeout dài?
4. Sau failover, ứng dụng có đối soát transaction chưa rõ kết quả không?
5. Khi mạng hồi phục, các replica có hội tụ theo giao thức, không có ghi trái quyền không?
6. RPO/RTO thực tế đạt yêu cầu nghiệp vụ hay không?

Không thể chứng minh toàn bộ tính đúng hệ phân tán chỉ qua một lần thử nghiệm. Fault injection cần kết hợp kiểm thử bất biến, log/metrics và hiểu chính xác giao thức lưu trữ đang dùng.

## 17. Hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “Data partition và network partition đều là chia dữ liệu.” | Một bên là **tổ chức dữ liệu**, bên kia là **mất liên lạc mạng**. |
| “PostgreSQL PARTITION BY là sharding nhiều máy.” | Table partitioning có thể hoàn toàn nằm trên một instance. |
| “Có shard thì đã có HA.” | Sharding không tự có replica hoặc failover. |
| “Replica chính là một shard khác.” | Replica sao chép cùng tập dữ liệu; shard thường giữ tập con khác nhau. |
| “Network partition xảy ra nghĩa là node chắc chắn đã chết.” | Node có thể khỏe nhưng không trao đổi thông điệp được. |
| “Ping timeout đủ để bầu primary mới.” | Cần quorum/leader election/fencing phù hợp để tránh split-brain. |
| “CAP C là ACID Consistency.” | CAP C gần với linearizable consistency, khác kiểm tra bất biến ACID. |
| “R+W>N chắc chắn bảo đảm linearizability.” | Quorum giao nhau còn cần giao thức giải quyết phiên bản/thứ tự và membership. |
| “Mạng bị chia thì cả cluster phải dừng.” | Khả năng đọc/ghi tùy node, quorum và bảo đảm được chọn. |
| “Failover sang async replica luôn giữ mọi COMMIT cũ.” | Replica có thể lag; phải xem RPO và cơ chế replication. |
| “COMMIT timeout chứng minh transaction chưa chạy.” | Server có thể đã commit nhưng phản hồi mất; cần idempotency và đối soát. |
| “Thêm shard chỉ cần đổi số N trong hash mod N.” | Còn phải di chuyển dữ liệu, đồng bộ routing và tránh ghi sai. |
| “@Transactional trên Java tự commit nguyên tử nhiều DB.” | Phạm vi transaction phụ thuộc transaction manager và hạ tầng. |
| “Đọc replica thành công nghĩa là kết quả mới nhất.” | Replica có thể stale, nhất là dưới network partition. |

## 18. Bài tập tự kiểm tra

### Bài 1 — Xác định loại partition

Một bảng PostgreSQL được chia thành partition theo tháng nhưng tất cả vẫn nằm trên một máy. Đây là loại phân vùng nào? Nó có tự chống được mất máy không?

**Gợi ý:** phân vùng dữ liệu theo range, không phải phân vùng mạng và không tự mang lại HA.

### Bài 2 — Một node vẫn chạy nhưng mất liên lạc

Replica C vẫn trả lời SELECT nhưng không nhận heartbeat từ A và B. Có thể kết luận C đã “chết” không?

**Gợi ý:** không. C có thể bị cô lập mạng. Kết quả đọc có thể trễ, việc có được ghi hay không tùy giao thức.

### Bài 3 — CAP

Trong network partition, tại sao hệ thống yêu cầu linearizable writes có thể từ chối ghi ở phía cô lập dù node đó đang chạy khỏe?

**Gợi ý:** nếu cả hai phía đều ghi độc lập, có thể không còn một thứ tự linearizable chung. Từ chối ghi ở phía thiếu quyền/quorum là lựa chọn bảo vệ consistency.

### Bài 4 — Shard key

Ứng dụng chia đơn hàng theo tenant_id nhưng báo cáo cần tổng hợp tất cả tenant. Điểm bất lợi có thể là gì?

**Gợi ý:** phải fan-out nhiều shard, gom kết quả, quản lý timeout/partial failure và độ nhất quán của dữ liệu tổng hợp.

### Bài 5 — Rebalancing

Router dùng hash(tenant_id) mod 3. Nhóm vận hành đổi sang mod 4 mà không di chuyển dữ liệu. Điều gì xảy ra?

**Gợi ý:** nhiều tenant bị route tới shard khác với nơi chứa dữ liệu, dẫn đến “không tìm thấy”, sai ghi hoặc dữ liệu phân tán không có kế hoạch. Cần catalog/reshard.

### Bài 6 — Replica và read-your-writes

Client vừa tạo đơn ở primary, sau đó đọc từ replica async và không tìm thấy đơn. Có thể tự tạo lại đơn mới vì “chưa tồn tại” không?

**Gợi ý:** không. Có thể replica lag. Cần route/consistency phù hợp và idempotency.

### Bài 7 — Quorum

Một nhóm ba replica bị chia thành A+B và C. Vì sao C một mình thường không được tự trở thành leader nếu giao thức yêu cầu majority quorum?

**Gợi ý:** C chỉ có 1/3 phiếu, không đạt đa số; việc cho phép ghi ở cả hai phía có nguy cơ tạo hai lịch sử khác nhau.

### Bài 8 — Java JDBC trên hai shard

Java dùng Connection A trừ tiền và Connection B cộng tiền, mỗi bên commit riêng. Có được coi là một transaction nguyên tử không?

**Gợi ý:** không. Phải thiết kế locality hoặc dùng giao thức phân tán/bù trừ phù hợp.

### Bài 9 — Mất phản hồi COMMIT

Java gửi COMMIT, đường mạng bị cắt, không nhận được phản hồi. Lập tức gửi lại lệnh ghi cùng nội dung bằng mã yêu cầu mới có an toàn không?

**Gợi ý:** không. Cần operation_id ổn định, đối soát theo nguồn có thẩm quyền và cân nhắc trạng thái failover.

### Bài 10 — Nhận diện hai loại vấn đề trong metrics

Một shard dùng 95% CPU, những shard khác dùng 10%; đồng thời A và B không còn trao đổi heartbeat với C. Cần gọi tên hai hiện tượng gì?

**Gợi ý:** **hot shard/data skew** và **network partition**. Chúng có thể xảy ra cùng lúc nhưng có cơ chế xử lý khác nhau.

## 19. Ghi nhớ và áp dụng

**Phân vùng dữ liệu** là quyết định thiết kế về **cách phân chia và xác định vị trí bản ghi**. Nó giúp mở rộng, phân tải và quản lý dữ liệu, nhưng tạo chi phí định tuyến, rebalancing và giao dịch liên shard. **Phân vùng mạng** là sự cố **các nút không thể giao tiếp đáng tin cậy**; nó buộc hệ thống phân tán xác định quyền đọc/ghi, leader, quorum, mức nhất quán, khả dụng và hành vi phục hồi.

Hai khái niệm **độc lập nhưng thường gặp cùng nhau** trong nền tảng có nhiều shard và replica. Java persistence phải vừa **chọn đúng shard theo khóa**, vừa **kết nối tới node có quyền phục vụ thao tác tương ứng**. Các lỗi mạng gần COMMIT đòi hỏi idempotency và đối soát; transaction cục bộ không tự trở thành giao dịch nguyên tử xuyên nhiều DB.

Khi thiết kế hệ thống, hãy xác định bất biến nghiệp vụ trước, chọn partition key theo truy vấn, định nghĩa consistency và RPO/RTO rõ ràng, rồi kiểm thử cả shard routing lẫn fault tolerance. Hiểu đúng ranh giới này là nền tảng để xây dựng persistence Java **mở rộng được, giữ dữ liệu nhất quán và phục hồi có kiểm soát khi mạng gặp sự cố**.
