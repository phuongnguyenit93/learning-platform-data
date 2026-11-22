# Vì sao dữ liệu cần được nhân bản hoặc phân mảnh

Một cơ sở dữ liệu chạy trên một máy chủ có thể đáp ứng tốt ứng dụng trong thời gian dài. Tuy nhiên, khi số người dùng, lượng dữ liệu và mức độ quan trọng của dịch vụ tăng, một máy có thể trở thành **điểm lỗi duy nhất**, giới hạn dung lượng hoặc điểm nghẽn truy vấn. Hai kỹ thuật nền tảng để giải quyết các vấn đề này là **nhân bản dữ liệu (replication)** và **phân mảnh dữ liệu (sharding)**.

- **Nhân bản:** duy trì nhiều bản sao của cùng một tập dữ liệu trên các nút khác nhau. Mục tiêu thường là tăng khả năng phục hồi, hỗ trợ chuyển đổi khi nút hỏng và có thể chia tải đọc.
- **Phân mảnh:** chia tập dữ liệu thành nhiều phần theo một quy tắc, đặt những phần đó trên các nút hoặc nhóm lưu trữ khác nhau. Mục tiêu thường là mở rộng dung lượng, thông lượng ghi và khả năng phân phối tải.

Trong chương **Nền tảng phân tán** của **DATA_PERSISTENCE_FUNDAMENTALS**, người học cần giải thích **vì sao** chọn kỹ thuật này, phân biệt lợi ích với giới hạn, và hiểu ảnh hưởng đến Java persistence: ranh giới transaction, định tuyến câu SQL, dữ liệu đọc có thể chậm, retry khi chuyển nút, thay đổi schema, bảo mật và sao lưu.

**Điểm mấu chốt:** replication không đồng nghĩa với sharding; replication không tự động bảo đảm dữ liệu mới nhất ở mọi bản sao; sharding không tự động làm truy vấn nhanh hơn; và cả hai **không thay thế backup**.

## 1. Khi nào một cơ sở dữ liệu đơn lẻ không còn đủ?

Giả sử dịch vụ đặt hàng ban đầu có một PostgreSQL instance, gồm `customers`, `orders` và `payments`. Ứng dụng có thể gặp các giới hạn khác nhau:

| Triệu chứng | Vì sao xảy ra | Cần ưu tiên xem xét |
| --- | --- | --- |
| Máy chủ DB dừng thì toàn bộ ứng dụng không thể truy cập dữ liệu | Một nút giữ bản dữ liệu đang phục vụ duy nhất | HA, replication, failover và recovery |
| Nhiều request chỉ đọc làm CPU/I/O của DB quá tải | Cùng một instance xử lý toàn bộ truy vấn đọc | Index/query tuning, cache, sau đó cân nhắc read replica |
| Dữ liệu, index và WAL lớn hơn khả năng vận hành của một máy | Giới hạn ổ đĩa, RAM, IOPS, thời gian backup/restore | Giảm dữ liệu nóng, lưu trữ phân tầng hoặc sharding |
| Một nút ghi đạt giới hạn CPU/I/O hoặc contention | Mọi cập nhật tập trung vào một write leader | Tối ưu câu ghi, batch, lock; sharding nếu có thể phân phối ghi |
| Người dùng ở nhiều khu vực có độ trễ mạng cao | Request đi qua khoảng cách địa lý tới DB | Replica gần nơi đọc, kiến trúc nhiều vùng có chính sách nhất quán rõ |
| Một tenant lớn làm chậm tenant khác | Nhiều tenant cùng tranh chấp tài nguyên | Phân vùng/tách tài nguyên hoặc sharding theo tenant |

Trước khi triển khai phân tán, hãy kiểm tra **truy vấn thiếu index, N+1, transaction dài, connection pool cạn, khóa tranh chấp, batch sai cách và cấu hình lưu trữ**. Những lỗi này vẫn tồn tại sau khi thêm replica/shard, thậm chí khó chẩn đoán hơn.

Một nguyên tắc kinh tế: **chỉ tăng độ phức tạp phân tán khi giới hạn đã đo được hoặc yêu cầu khả dụng/phục hồi buộc phải làm vậy**. Tăng RAM/CPU/IOPS cho một nút (*vertical scaling*) và cải thiện truy vấn thường là bước hợp lý trước khi tự xây định tuyến nhiều nút.

## 2. Nhân bản: một tập dữ liệu, nhiều bản sao

Trong mô hình primary–replica thông dụng, một nút **primary/leader** nhận thay đổi; một hoặc nhiều replica nhận và áp dụng các thay đổi ấy. Mỗi replica có cùng dữ liệu *về mặt mục tiêu*, nhưng tại một thời điểm có thể đang ở **mốc cập nhật khác nhau**.

```text
                    Java application
                   /                \
          Command / write         Query / read
                 |                   |
                 v                   v
           +------------+      +------------+
           |  Primary   |----->| Replica A  |
           | writes/log |      | read-only  |
           +------------+      +------------+
                 |
                 +----------------->+------------+
                                    | Replica B  |
                                    | read-only  |
                                    +------------+

      Mũi tên biểu diễn dòng thay đổi/replication,
      KHÔNG phải bảo đảm mọi replica luôn cập nhật tức thời.
```

Tùy DB, việc nhân bản có thể chuyển **log thay đổi vật lý** (ví dụ WAL), các sự kiện/row change mang tính logic hoặc thực hiện một giao thức đồng thuận nhiều bản sao. Mô hình *leader–follower* không bao quát mọi hệ thống: có hệ thống nhiều writer hoặc hệ thống điều phối ghi bằng quorum/consensus. Cần xác định **sản phẩm và chế độ cấu hình cụ thể** trước khi nói về hành vi.

### 2.1. Nhân bản để tăng khả dụng

Nếu primary hỏng, hệ thống có thể chọn một replica đủ điều kiện làm primary mới. Điều này có ích khi giảm thời gian ngừng dịch vụ, nhưng **replication không tự động tạo HA**. Một quy trình failover an toàn còn cần:

1. Phát hiện primary không khả dụng mà không nhầm một sự cố mạng tạm thời với nút đã chết.
2. Xác định replica có dữ liệu/mốc log đủ phù hợp để được thăng cấp.
3. **Fencing:** ngăn primary cũ tiếp tục nhận ghi sau khi primary mới hoạt động, tránh *split-brain* (hai writer cùng cho rằng mình là nguồn chính).
4. Định tuyến lại ứng dụng/connection pool, xử lý DNS/proxy và các kết nối cũ.
5. Phục hồi các replica còn lại và đối soát các giao dịch có kết quả chưa xác định.

**RPO** (*Recovery Point Objective*) cho biết mức mất dữ liệu tối đa được chấp nhận sau sự cố; **RTO** (*Recovery Time Objective*) cho biết mục tiêu thời gian phục hồi dịch vụ. Replication có thể hỗ trợ cải thiện RPO/RTO nhưng phải đo trên tình huống sự cố thật, không suy từ việc có “hai máy”.

### 2.2. Đồng bộ hay bất đồng bộ?

| Cách nhân bản | Lợi ích | Rủi ro/giới hạn |
| --- | --- | --- |
| **Asynchronous replication** | Primary thường không phải chờ replica xác nhận trước khi trả commit; write latency thấp hơn | Replica có thể chậm; nếu primary hỏng trước khi thay đổi được sao chép, một phần giao dịch đã ACK có thể không có trên replica được chọn |
| **Synchronous replication/acknowledgment** | Commit phải chờ một điều kiện xác nhận từ các nút khác theo cấu hình; có thể giảm nguy cơ mất những thay đổi đã ACK | Tăng latency, phụ thuộc tốc độ và tính sẵn sàng của nhóm xác nhận; có thể làm giảm khả năng ghi khi replica không đáp ứng |
| **Quorum/consensus-based replication** | Một tập đủ nút tham gia công nhận thay đổi theo protocol; hữu ích cho điều phối leader và duy trì tính nhất quán đã định nghĩa | Cần hiểu quorum, leader election, phân vùng mạng, read protocol và độ bền của log; chi phí vận hành cao hơn |

**“Synchronous” không phải một cam kết giống nhau trên mọi DB.** Một số chế độ chỉ chờ replica *nhận* log, số khác chờ log được *flush* hoặc thay đổi được *apply*. Quorum ACK không tự suy ra mọi thao tác đọc từ bất kỳ replica đều tuyến tính (linearizable). Phải đọc chính sách commit, durability, failover và read consistency của engine đang dùng.

### 2.3. Nhân bản để chia tải đọc

Ứng dụng có thể gửi báo cáo hoặc danh sách chịu được dữ liệu trễ đến replica, giảm CPU/I/O cho primary. Nhưng tăng replica **không làm primary có thêm năng lực xử lý ghi một cách mặc định**; các replica cũng tốn CPU, ổ đĩa và băng thông để áp dụng thay đổi.

Replica hữu ích cho truy vấn analytics/chỉ đọc, song một câu query nặng vẫn có thể cạnh tranh tài nguyên với luồng replay hoặc làm tăng lag. Quyết định định tuyến phải tính đến độ mới của dữ liệu và khả năng replica bị tạm ngắt khi failover.

## 3. Dữ liệu trễ và các mức nhất quán khi đọc

Giả sử khách hàng thanh toán đơn thành công trên primary. API lập tức chuyển sang màn hình chi tiết, nhưng câu đọc được gửi đến replica chưa nhận/applied transaction mới:

```text
Thời điểm t0: Primary UPDATE orders SET status='PAID'; COMMIT thành công
Thời điểm t1: Java API trả "thanh toán thành công"
Thời điểm t2: GET /orders/42 đọc ở Replica A -> vẫn thấy 'PENDING'
Thời điểm t3: Replica A áp dụng thay đổi -> mới thấy 'PAID'
```

Đây là **replication lag**. Nó không tự động chứng minh lệnh thanh toán/commit thất bại. Cũng không được coi read replica là nguồn duy nhất để đưa ra quyết định nghiệp vụ bắt buộc phải thấy dữ liệu mới nhất.

| Nhu cầu | Chiến lược có thể dùng | Điều cần kiểm chứng |
| --- | --- | --- |
| Danh sách/báo cáo chấp nhận trễ vài giây | Read replica và cache có TTL phù hợp | Lag p95/p99, ngưỡng stale data, lúc replica ngắt kết nối |
| **Read-your-writes**: ngay sau ghi phải thấy thay đổi vừa commit | Đọc từ primary sau ghi; hoặc đợi replica vượt mốc commit phù hợp | Cùng user/session và đúng mốc version/log; timeout khi replica chưa bắt kịp |
| Quyết định giữ chỗ/trừ tồn kho/chuyển tiền | Kiểm tra và cập nhật nguyên tử trên nguồn ghi có transaction/ràng buộc phù hợp | Không dựa vào một SELECT từ replica rồi ghi mà bỏ điều kiện kiểm tra lại |
| Dữ liệu phải đọc từ nhiều vùng | Replica gần người dùng khi freshness cho phép | Vị trí dữ liệu, độ trễ và chính sách failover |

Mốc WAL/LSN, log offset hoặc version có thể hỗ trợ **đợi replica bắt kịp** trong một số hệ thống, nhưng đây là API/semantics đặc thù từng DB; không có một cách làm JDBC portable duy nhất. Nếu không có cơ chế xác minh mốc đáng tin cậy, **đọc primary** là lựa chọn dễ hiểu hơn cho những lần đọc ngay sau ghi cần tính mới.

Đọc từ primary cũng không tự bảo đảm nhất quán cho nhiều câu truy vấn nếu mỗi câu chạy ở transaction và isolation khác nhau. Khi cần một snapshot ổn định hoặc invariant đa hàng, vẫn phải chọn transaction/isolation và giao thức ghi đúng.

## 4. Phân mảnh: chia dữ liệu và phân phối tải

Trong **sharding**, mỗi shard giữ một phần dữ liệu theo quy tắc định tuyến. Thay vì tất cả hàng `orders` nằm trên một nút, hệ thống có thể chia theo `customer_id`:

```text
             Java application / API
                        |
                   Shard Router
                  /     |      \
                 v      v       v
             Shard 0  Shard 1  Shard 2
             -------  -------  -------
             customer customer customer
              1, 4...  2, 5...  3, 6...

      Mỗi shard có thể là một database độc lập
      và mỗi shard cũng có thể có replica riêng.
```

Khi chia dữ liệu theo một khóa phù hợp, một truy vấn/command có thể được chuyển đến **đúng một shard**. Dung lượng và hoạt động ghi được phân phối giữa các shard, nhưng tổng chi phí hệ thống tăng do nhiều cơ sở dữ liệu, backup, monitoring, migration và cơ chế điều phối.

### 4.1. Sharding khác partitioning trong một DB

**Partitioning** chia một bảng thành các partition logic/vật lý, ví dụ chia bảng đơn theo tháng. **Sharding** thường nói đến việc phân dữ liệu qua nhiều nút hoặc nhóm DB riêng có định tuyến. Một bảng được partition ngay trong cùng một instance có thể giúp quản lý dữ liệu và giới hạn tập phải quét, nhưng **không tự tăng tổng CPU/IOPS của máy**.

Không nên đồng nhất: “có `PARTITION BY`” = “đã sharding nhiều máy”. Một sản phẩm distributed SQL có thể tự phân phối partition/range trên các nút; ở các DB truyền thống, ứng dụng hoặc middleware có thể phải đảm nhiệm việc định tuyến.

### 4.2. Chọn shard key là quyết định kiến trúc

Một shard key tốt thường:

- Có mặt trong phần lớn truy vấn giao dịch để định tuyến đến một shard.
- Phân phối khối lượng dữ liệu và lưu lượng **đủ đều** giữa shard.
- Tương đối ổn định trong vòng đời bản ghi; đổi khóa có thể phải di chuyển dữ liệu.
- Giúp các dữ liệu cần cùng một transaction nằm **cùng shard** khi có thể.
- Phù hợp ranh giới phân quyền/tenant và chính sách lưu trữ dữ liệu.

| Cách phân phối | Ví dụ | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| **Range-based** | Customer ID 1–1 triệu ở shard A, tiếp theo ở B | Dễ định tuyến truy vấn khoảng và di chuyển range | Tăng dần ID có thể dồn ghi vào một shard nóng |
| **Hash-based** | `hash(customer_id)` → bucket/shard | Có thể phân phối đều khi khóa/lưu lượng thích hợp | Range scan và JOIN rộng; modulo trực tiếp khó mở rộng shard |
| **Directory/lookup-based** | Catalog ánh xạ `tenant_id → shard_id` | Di chuyển tenant linh hoạt, dễ tách tenant lớn | Catalog cần độ bền, cache nhất quán, và quy trình cập nhật mapping |
| **Geo/tenant-based** | Dữ liệu tenant theo vùng hợp lệ | Hỗ trợ yêu cầu vị trí dữ liệu và cô lập tài nguyên | Khó cân bằng tải; truy vấn xuyên vùng tốn kém |

**Dữ liệu phân phối đều chưa chắc tải phân phối đều.** Một khách hàng lớn có thể chiếm 60% request dù chỉ chiếm 1% số hàng; hash theo `customer_id` khi ấy vẫn đưa toàn bộ lưu lượng của khách hàng đó vào một shard. Cần đo phân phối **QPS, write rate, I/O, kích thước và lock contention** chứ không chỉ đếm số hàng.

### 4.3. Mở rộng từ N lên N+1 shard không hề miễn phí

Nếu quy tắc trực tiếp là `shard = hash(customer_id) % N`, đổi `N` có thể làm thay đổi tuyến của rất nhiều khóa. Không thể chỉ tăng `N` trong cấu hình Java rồi hy vọng dữ liệu tự xuất hiện ở nơi mới.

Các cách thiết kế thực tế gồm **virtual buckets**, consistent hashing phù hợp, hoặc bảng định tuyến tenant→shard. Khi cần di chuyển dữ liệu, thường phải:

1. Chốt nguồn dữ liệu và quyền ghi cho từng bucket/tenant.
2. Sao chép dữ liệu nền và theo dõi những thay đổi phát sinh trong lúc sao chép.
3. Đồng bộ phần chênh lệch, kiểm tra count/checksum và bất biến nghiệp vụ.
4. Chuyển hướng router **có kiểm soát**, tránh hai nơi cùng nhận ghi cho một khóa.
5. Giám sát lỗi, độ trễ, rollback/cutover và chỉ dọn dữ liệu cũ khi an toàn.

**Dual-write trực tiếp tới hai shard không tự tạo atomicity**. Nếu ghi nơi cũ thành công nhưng nơi mới thất bại, dữ liệu lệch. Cần giao thức migration có nguồn sự thật rõ ràng, CDC/log hoặc một chiến lược nhất quán đã được thử nghiệm.

## 5. Kết hợp sharding với replication

Hệ thống quy mô lớn có thể có nhiều shard, **mỗi shard lại có primary và replica**:

```text
                          API
                           |
                      Shard router
                    /               \
                   v                 v
               Shard A             Shard B
             Primary A            Primary B
              /     \              /     \
          Replica  Replica     Replica  Replica
             A1      A2          B1      B2
```

Hai chiều này giải quyết các bài toán tương đối độc lập:

- **Sharding** phân chia dữ liệu và tải ghi; để tạo một transaction ở shard A, ứng dụng phải định tuyến đúng shard A.
- **Replication** giữ nhiều bản sao cho **từng shard**, giúp phân phối tải đọc và phục hồi nút trong shard đó.
- **Failover của một shard** không được làm đổi shard key hoặc khiến hai shard cùng sở hữu một customer. Router phải cập nhật leader endpoint/metadata của đúng shard.

Điều này mở ra nhiều điểm lỗi hơn: một shard lỗi có thể ảnh hưởng một nhóm khách hàng; một thành phần điều phối chung như router/catalog nếu lỗi có thể ảnh hưởng nhiều shard. Thiết kế phải xác định blast radius, quyền truy cập, cách thay đổi topology và cách chạy migration ở hàng chục/hàng trăm database.

## 6. Ví dụ Java: định tuyến đọc primary/replica có chủ đích

Với một nhóm replication, ứng dụng có thể có hai `DataSource`: một nối tới **write endpoint** (primary), một nối tới **read endpoint** (replica). Đây là sơ đồ dùng để dạy **chính sách định tuyến**; không thay thế cấu hình HA, driver, failover proxy và TLS ở production.

Giả sử bảng bên dưới có cùng schema trên primary và replica, nhờ cơ chế nhân bản do DB cung cấp:

```sql
CREATE TABLE orders (
    customer_id BIGINT NOT NULL,
    order_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL
           CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_id, order_id)
);
```

Đường đọc Java 17+:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import java.util.UUID;

public final class OrderReader {
    public enum Consistency { REPLICA_OK, PRIMARY_REQUIRED }

    public record OrderView(UUID orderId, String status, long version) {}

    private final DataSource primary;
    private final DataSource readReplica;

    public OrderReader(DataSource primary, DataSource readReplica) {
        this.primary = primary;
        this.readReplica = readReplica;
    }

    public Optional<OrderView> get(
            long customerId, UUID orderId, Consistency consistency)
            throws SQLException {
        DataSource selected = consistency == Consistency.PRIMARY_REQUIRED
                ? primary : readReplica;
        String sql = """
            SELECT order_id, status, version
            FROM orders
            WHERE customer_id = ? AND order_id = ?
            """;

        try (Connection c = selected.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, customerId);
            ps.setObject(2, orderId);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return Optional.of(new OrderView(
                            rs.getObject("order_id", UUID.class),
                            rs.getString("status"),
                            rs.getLong("version")));
                }
                return Optional.empty();
            }
        }
    }
}
```

Tầng application quyết định consistency theo **use case**, chẳng hạn danh sách lịch sử không cần dữ liệu mới nhất có thể dùng `REPLICA_OK`; kiểm tra trạng thái **ngay sau commit** hoặc quyết định liên quan bất biến có thể cần `PRIMARY_REQUIRED`. Ứng dụng không nên tự động chuyển mọi câu đọc sang replica chỉ vì có read endpoint.

Các điểm cần hiểu:

1. `PRIMARY_REQUIRED` ở ví dụ nghĩa là **không đọc một replica bất đồng bộ**; nó không tự nâng isolation lên serializable hoặc khóa bất kỳ hàng nào.
2. Query trên replica có thể trả `Optional.empty()` dù đơn vừa được tạo trên primary. Không kết luận “không có đơn” chắc chắn chỉ từ một replica đang lag.
3. `Connection.close()` trong pool thường trả connection; `try-with-resources` không mở transaction ghi kéo dài khi chỉ có một câu SELECT.
4. Khi primary failover, endpoint và những connection hiện hữu có thể lỗi. Retry câu đọc chỉ khi phù hợp, không tự retry command có kết quả commit không rõ.
5. Phân quyền phải được thực hiện trên đường đọc và đường ghi, không dùng sự tồn tại của replica như một lớp bảo mật. `customerId` phải đến từ ngữ cảnh đáng tin cậy.

### Câu ghi vẫn phải bảo vệ invariant trên nguồn ghi

Ví dụ cập nhật trạng thái có điều kiện, luôn chạy trên **primary/leader hợp lệ**:

```sql
UPDATE orders
SET status = 'PAID', version = version + 1
WHERE customer_id = ?
  AND order_id = ?
  AND status = 'PENDING'
  AND version = ?;
```

Ứng dụng kiểm tra số hàng cập nhật. Đọc trước từ replica để hiển thị nút thanh toán **không thay thế** điều kiện kiểm tra trạng thái và version tại nơi ghi. Khi có nhiều cập nhật bắt buộc cùng commit (ví dụ thanh toán + sổ cái + outbox), mọi bước phải tham gia một transaction đúng phạm vi dữ liệu và có chiến lược lỗi/idempotency.

## 7. Ví dụ Java: định tuyến theo shard key

Với dữ liệu phân theo `customer_id`, truy vấn về một khách hàng nên chuyển đến shard của khách hàng đó. Ví dụ định tuyến **minh họa cho số shard cố định**:

```java
import javax.sql.DataSource;
import java.util.List;

public final class FixedShardRouter {
    private final List<DataSource> shards;

    public FixedShardRouter(List<DataSource> shards) {
        if (shards == null || shards.isEmpty()) {
            throw new IllegalArgumentException("Danh sách shard không được rỗng");
        }
        this.shards = List.copyOf(shards);
    }

    public DataSource forCustomer(long customerId) {
        int bucket = Math.floorMod(Long.hashCode(customerId), shards.size());
        return shards.get(bucket);
    }
}
```

Chẳng hạn, repository dùng `router.forCustomer(customerId).getConnection()` rồi luôn ràng buộc `customer_id` trong câu SQL. **Không dùng ví dụ modulo này làm router production khi có khả năng thêm/bớt shard**, vì thay đổi `shards.size()` sẽ làm nhiều khóa chuyển vị trí mà dữ liệu chưa hề được di chuyển. Một hệ thống thật thường cần mapping/bucket ổn định, phiên bản cấu hình và quy trình migration.

Nếu chỉ biết `order_id` nhưng không biết `customer_id`, router không thể định tuyến trực tiếp theo khóa của ví dụ; có thể cần lookup index/catalog, đưa khóa shard vào API, hoặc phải chạy truy vấn trên nhiều shard. Thiết kế API và khóa dữ liệu phải cân nhắc ngay từ đầu, trước khi bảng lớn lên.

**Một transaction JDBC thông thường chỉ thuộc một connection/DB.** Nếu command cần cập nhật shard A và B, việc mở hai connection rồi `commit()` từng cái không bảo đảm cả hai cùng thành công hoặc cùng rollback. Có thể dùng giao thức giao dịch phân tán khi thực sự cần và DB hỗ trợ, nhưng chi phí/khả dụng tăng lên; thường nên thiết kế dữ liệu cùng aggregate ở chung shard hoặc dùng workflow bất đồng bộ có idempotency, outbox và bù trừ.

## 8. Trade-off: không phải cứ thêm nút là mọi thứ nhanh và an toàn hơn

| Vấn đề | Replication | Sharding |
| --- | --- | --- |
| Mở rộng dung lượng dữ liệu logic | Không: mỗi full replica còn giữ bản sao của cùng tập | Có: mỗi shard giữ một phần dữ liệu |
| Tăng thông lượng đọc | Có thể, nếu đọc chịu được lag và có tài nguyên | Có thể, nếu query được phân bố theo shard |
| Tăng thông lượng ghi trên nhiều máy | Không tự tăng với mô hình single leader | Có thể, khi write load phân phối đều và không vướng coordinator |
| Tăng khả năng phục hồi một nút | Có, nếu failover/replica đúng cách | Không tự có: mỗi shard vẫn cần replication/backup riêng |
| Phức tạp vận hành | Lag, failover, consistency, replica health | Router, hotspot, reshard, cross-shard query/transaction |
| Sao lưu và khôi phục | Replica không thay thế backup độc lập | Phải backup/restore nhất quán và định vị đúng từng shard |

Với hệ thống thực tế, có thể phải chọn giữa trả lời một yêu cầu ngay và giữ tính nhất quán khi **mạng bị phân vùng**. Đây là nhóm vấn đề được diễn tả trong CAP theorem, nhưng không nên giản lược thành “một DB luôn chỉ có hai trong ba chữ C, A, P”. C trong CAP mang nghĩa nhất quán tuyến tính của thao tác trên đối tượng, còn A là đáp ứng mọi yêu cầu của nút không hỏng trong mô hình; lựa chọn phụ thuộc giao thức và hoàn cảnh partition. **Không dùng CAP như lý do bỏ qua thiết kế durability, isolation hoặc backup**.

### Nhân bản không phải bản sao lưu

Một câu `DELETE` sai, migration phá schema hoặc mã độc xóa dữ liệu có thể được sao chép sang mọi replica. Replication còn có thể nhân bản lỗi logic, dữ liệu sai hoặc sự kiện ghi nhầm rất nhanh. Vì vậy vẫn cần:

- Backup được lưu tách biệt với miền lỗi chính; có retention, quyền truy cập và khả năng phục hồi phiên bản cũ.
- Point-in-time recovery nếu yêu cầu và DB hỗ trợ; lưu log liên quan trong một phạm vi thời gian đủ dài.
- Thử **restore thực tế** và xác nhận tính nhất quán dữ liệu, không chỉ kiểm tra job backup báo thành công.
- Kế hoạch phục hồi nhiều shard tại mốc thời gian phù hợp, nhất là nếu có quan hệ nghiệp vụ vượt shard.

### Tính nhất quán có nhiều chiều

Đọc replica trễ là vấn đề **freshness/consistency giữa bản sao**. Hai transaction trên cùng primary đồng thời sửa một bất biến lại là vấn đề **isolation/concurrency control**. Bản ghi đã commit mất sau sự cố là vấn đề **durability/failover policy**. Ba nhóm này liên quan nhưng không thay thế nhau; một hệ thống có thể có replica đọc mới nhưng vẫn cho phép lost update nếu command SQL sai.

## 9. Các câu hỏi kiến trúc trước khi triển khai

1. **Mục tiêu chính:** giảm downtime, thêm read capacity, mở rộng dung lượng hay write throughput? Có đo được điểm nghẽn không?
2. **RPO/RTO:** chấp nhận mất bao nhiêu giao dịch đã ACK và phục hồi trong bao lâu? Khả năng chịu lỗi vùng địa lý tới đâu?
3. **Consistency:** use case nào cần read-your-writes, giao dịch mạnh, hoặc chấp nhận dữ liệu trễ? Có chỉ số lag và chính sách fallback không?
4. **Shard key:** bao nhiêu phần trăm câu SQL có khóa định tuyến? Phân phối tải có lệch vì tenant lớn hoặc khóa tăng dần không?
5. **Transaction boundary:** dữ liệu nào cần atomically commit cùng nhau? Có vô tình phân tán một aggregate qua nhiều shard không?
6. **Topology/failover:** ai quyết định leader, có fencing chống split-brain, ứng dụng nhận thay đổi endpoint bằng cách nào?
7. **Vận hành:** ai quản lý schema migration qua nhiều shard, backup/restore, quyền và dữ liệu cá nhân ở các vùng?
8. **Tăng trưởng:** khi thêm shard, mapping thay đổi như thế nào; có kế hoạch copy/CDC/cutover/rollback không?
9. **An toàn retry:** khi mất connection ở commit hoặc failover, làm sao đối soát request bằng idempotency key trước khi gửi lại?

Chỉ số cần theo dõi gồm **replication lag (byte/thời gian), failover duration, read/write QPS từng nút, lock wait, cache hit, CPU/IOPS, dung lượng từng shard, hotspot, tỷ lệ cross-shard query, lỗi router, p95/p99 latency và RPO/RTO qua diễn tập**. Một báo cáo “có 3 replicas, 8 shards” không thay thế kết quả đo.

## 10. Bài tập thực hành

### Bài tập 1: chọn đúng kỹ thuật

Hệ thống A có 90% lưu lượng là đọc, còn primary quá tải CPU đọc nhưng write rate thấp. Hệ thống B có dung lượng và write rate tăng đến giới hạn của một nút, dù truy vấn đã được tối ưu.

**Gợi ý:** A có thể cân nhắc **read replica** sau khi tối ưu query/cache và xác định yêu cầu freshness. B có thể cần **sharding** theo khóa phù hợp. Replication single leader không tự tăng write throughput cho B, còn sharding B vẫn cần HA/backup cho từng shard.

### Bài tập 2: đọc sau commit

API thanh toán xác nhận commit trên primary nhưng đọc replica ngay sau đó vẫn thấy `PENDING`. Đây là lost update hay replication lag? Làm sao UI hiển thị đúng?

**Đáp án:** có thể là replication lag; không kết luận lost update chỉ từ một lần đọc replica. Đọc primary khi cần read-your-writes, đợi replica đạt mốc cập nhật nếu có cơ chế tin cậy, hoặc trả trạng thái đã commit từ command rồi đồng bộ lại UI.

### Bài tập 3: phân mảnh không đều

Có bốn shard hash theo `tenant_id`. Một tenant gửi 70% tổng số request, các tenant khác chia đều phần còn lại. Hash có bảo đảm tải cân bằng không?

**Đáp án:** không. Các hàng có thể phân đều nhưng hầu hết lưu lượng của tenant lớn vẫn vào một shard. Cân nhắc cách tách tenant lớn, định tuyến theo bucket nhỏ hơn nếu nghiệp vụ cho phép, và kiểm tra ảnh hưởng đến transaction, quyền, migration.

### Bài tập 4: thêm shard

Một ứng dụng hiện dùng `hash(customer_id) % 4`. Developer đổi ngay thành `% 5` rồi triển khai, nhưng chưa chuyển dữ liệu. Điều gì có thể xảy ra?

**Đáp án:** nhiều khóa sẽ được định tuyến sang shard khác và truy vấn không thấy bản ghi, hoặc thao tác ghi tạo dữ liệu ở nơi sai. Cần mapping ổn định và quy trình reshard có đối soát, đồng bộ chênh lệch, cắt chuyển kiểm soát.

### Bài tập 5: hai giao dịch, hai shard

Java mở connection tới shard A, trừ tồn kho, rồi mở connection tới shard B, ghi booking; sau đó commit A thành công và commit B thất bại. Có thể gọi hai `commit()` và coi toàn bộ tác vụ nguyên tử không?

**Đáp án:** không. Đây là hai transaction độc lập. Nên xem lại cách đặt các bản ghi thuộc cùng nghiệp vụ trên một shard; nếu không thể, phải chọn một cơ chế phối hợp phân tán hoặc quy trình eventual consistency/saga với idempotency và bù trừ phù hợp.

### Checklist cuối bài

- Có phân biệt rõ **một dữ liệu có nhiều bản sao** (replication) với **mỗi nút giữ một phần dữ liệu** (sharding) không?
- Read replica có thể trễ; đường ghi có kiểm tra bất biến trên primary/leader hoặc giao thức ghi được DB bảo vệ không?
- RPO/RTO và độ bền commit được xác định bằng cơ chế thật, không chỉ dựa vào số replica không?
- Shard key phù hợp phân phối **lưu lượng**, routing và ranh giới transaction; có kế hoạch xử lý hotspot không?
- Có giao thức failover/fencing, kiểm tra dữ liệu sau cutover và quản lý topology khi thêm node/shard không?
- Java có trả connection đúng cách, phân loại read preference và xử lý commit-unknown/idempotency khi failover không?
- Backup, restore, schema migration, phân quyền và monitoring có bao phủ **toàn bộ** các shard/replica không?

**Kết luận:** **Nhân bản** giải quyết nhu cầu có nhiều bản sao để phục hồi và chia tải đọc; **phân mảnh** giải quyết nhu cầu phân chia dữ liệu và tải giữa các nút. Chúng có thể kết hợp nhưng không miễn phí: hệ thống phải trả giá bằng độ phức tạp của consistency, routing, failover, migration và vận hành. Chọn dựa trên mục tiêu đo được, giữ bất biến nghiệp vụ tại đúng ranh giới giao dịch, và kiểm chứng cả tình huống bình thường lẫn khi một nút/mạng gặp sự cố.
