# Cập nhật nhiều bảng phi chuẩn hóa và xử lý sai lệch

Trong Apache Cassandra, dữ liệu thường được **nhân bản có chủ đích vào nhiều bảng để phục vụ nhiều kiểu truy vấn**. Một đơn hàng có thể xuất hiện đồng thời ở bảng tra cứu theo mã đơn, bảng liệt kê đơn của khách hàng và bảng theo dõi đơn theo trạng thái. Cách thiết kế này giúp mỗi truy vấn đọc đúng partition, nhưng tạo ra một trách nhiệm quan trọng cho ứng dụng Spring Data Cassandra: **một thay đổi nghiệp vụ phải được phản ánh đến các bản biểu diễn liên quan, kể cả khi một phần thao tác ghi thất bại**.

Bài học thuộc chương **Thiết kế ứng dụng** của **SPRING_DATA_CASSANDRA**. Trọng tâm là kết hợp thiết kế bảng theo truy vấn với entity mapping, repository, `CassandraTemplate`/driver CQL, consistency level, batch, retry, phát hiện và sửa sai lệch. Các chiến lược được trình bày theo những bảo đảm mà Cassandra thực sự cung cấp, không giả định có giao dịch ACID xuyên nhiều partition như cơ sở dữ liệu quan hệ.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Xác định bảng nào giữ trạng thái chuẩn và bảng nào là bản biểu diễn phục vụ truy vấn.
2. Thiết kế khóa partition, khóa clustering và bucket cho các bảng phi chuẩn hóa.
3. Xây dựng luồng tạo/cập nhật/xóa bản biểu diễn, xử lý cả trường hợp thay đổi khóa truy vấn.
4. Phân biệt **logged batch**, **unlogged batch**, consistency level và **lightweight transaction (LWT)**; chọn đúng phạm vi sử dụng.
5. Thiết kế thao tác ghi có thể chạy lại an toàn, chịu được timeout, sự kiện trùng hoặc đến sai thứ tự.
6. Phát hiện, đo lường và sửa sai lệch dữ liệu bằng cơ chế đối soát có giới hạn tải.
7. Kiểm chứng cả kết quả nghiệp vụ lẫn giới hạn về hiệu năng, tombstone và partition nóng.

## 2. Vì sao cập nhật nhiều bảng là vấn đề riêng trong Cassandra?

Cassandra tổ chức dữ liệu theo **partition key** và tối ưu việc đọc/ghi khi truy vấn chỉ rõ partition cần truy cập. Thay vì trông chờ phép `JOIN` giữa nhiều bảng, ứng dụng thường tạo nhiều bản biểu diễn của cùng một thực thể.

Ví dụ hệ thống đặt hàng cần ba truy vấn:

| Truy vấn nghiệp vụ | Bảng phục vụ | Khóa truy cập chủ yếu |
|---|---|---|
| Xem chi tiết đơn hàng từ `order_id` | `orders_by_id` | `order_id` |
| Liệt kê đơn của một khách hàng, mới nhất trước | `orders_by_customer` | `customer_id`, rồi `created_at` |
| Liệt kê đơn theo trạng thái trong một ngày tạo đơn | `orders_by_status_day` | `status` và `day`, rồi `created_at` |

Khi đơn `O-123` đổi từ `PAID` sang `SHIPPED`, hệ thống có thể phải:

- Ghi trạng thái mới vào `orders_by_id`.
- Cập nhật thuộc tính `status` trong `orders_by_customer`.
- Xóa dòng ở partition trạng thái `PAID` của `orders_by_status_day`.
- Thêm dòng vào partition trạng thái `SHIPPED` của `orders_by_status_day`.

Các thao tác có thể tác động đến **nhiều partition**. Nếu ứng dụng hoặc mạng gặp lỗi giữa luồng, người dùng có thể đọc thấy trạng thái `SHIPPED` ở màn hình chi tiết nhưng vẫn thấy đơn trong danh sách `PAID`.

Đây là **sai lệch giữa các bản biểu diễn** (projection drift), khác với việc các replica của *cùng một partition* chưa hội tụ. Consistency level và cơ chế repair replica của Cassandra không tự động biết rằng những dòng nằm ở các bảng khác nhau phải phản ánh cùng một đơn hàng.

### Một mô hình tư duy hữu ích

`orders_by_id` là **nguồn dữ liệu chuẩn** (*canonical source*) trong ví dụ này. Hai bảng còn lại là **projection** có thể được xây dựng lại từ dữ liệu chuẩn và metadata cần thiết. Sự phân vai này là quyết định của ứng dụng, không phải một tính năng Cassandra tự suy luận từ tên bảng.

~~~mermaid
flowchart TD
    A["Lệnh thay đổi đơn hàng"] --> B["Ghi trạng thái chuẩn: orders_by_id"]
    B --> C["Cập nhật orders_by_customer"]
    B --> D["Xóa dòng trạng thái cũ"]
    B --> E["Thêm dòng trạng thái mới"]
    C --> F["Kiểm tra / đối soát"]
    D --> F
    E --> F
    B --> F
    F -->|Phát hiện sai lệch| G["Chạy lại thao tác sửa projection"]
~~~

Nếu chỉ có một bản ghi chuẩn, ứng dụng phải **quy định rõ cách đồng bộ và phục hồi projection**. Nếu cả ba bảng đều có quyền tự thay đổi trạng thái nghiệp vụ, việc giải quyết xung đột sẽ khó hơn nhiều.

## 3. Thiết kế bảng theo truy vấn trước khi viết mã

Ví dụ sử dụng ba bảng CQL dưới đây. Tên cột là quy ước minh họa; khi triển khai cần xác định thêm keyspace, replication factor, số lượng bản ghi và đặc điểm lưu lượng thực tế.

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal,
    updated_at timestamp,
    version bigint
);

CREATE TABLE orders_by_customer (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    version bigint,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);

CREATE TABLE orders_by_status_day (
    status text,
    day date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    version bigint,
    PRIMARY KEY ((status, day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

### Ý nghĩa của các khóa

- `orders_by_id`: một partition theo `order_id`, thích hợp khi đã biết mã đơn.
- `orders_by_customer`: một partition theo `customer_id`, bên trong có thứ tự theo thời điểm tạo. Việc thêm `order_id` giúp phân biệt hai đơn có cùng `created_at`.
- `orders_by_status_day`: partition theo cặp `(status, day)`; `day` là **ngày tạo đơn theo một quy tắc múi giờ thống nhất**. Khi đổi `status`, vị trí partition thay đổi. Bảng này trả lời câu hỏi “đơn thuộc trạng thái X, được tạo vào ngày Y”, **không** phải “đơn chuyển sang trạng thái X vào ngày Y”.

Ví dụ một số truy vấn tương ứng:

~~~sql
SELECT * FROM orders_by_id
WHERE order_id = ?;

SELECT * FROM orders_by_customer
WHERE customer_id = ?
LIMIT 30;

SELECT * FROM orders_by_status_day
WHERE status = ? AND day = ?
LIMIT 50;
~~~

Các truy vấn nêu trên chỉ rõ partition key; không cần `ALLOW FILTERING` để tìm đơn theo các tiêu chí đã thiết kế.

**Lưu ý về partition lớn và nóng:** bảng `orders_by_customer` có thể tạo partition rất lớn với khách hàng có hàng triệu đơn. Tương tự, `(status, day)` có thể là partition nóng trong ngày có nhiều đơn. Khi đó cần phân bucket nhỏ hơn hoặc thêm `shard` vào partition key, ví dụ `((status, day, shard), created_at, order_id)`, đồng thời chấp nhận truy vấn phải đọc và gộp kết quả từ nhiều shard. Chọn kích thước bucket theo số bản ghi, kích thước dữ liệu, lưu lượng và giới hạn latency đã đo, không theo một hằng số dùng cho mọi hệ thống.

**Không thêm bảng chỉ vì muốn lưu thêm một bản sao.** Mỗi bảng phụ mang thêm write amplification, dung lượng, tombstone, yêu cầu đối soát và chi phí thay đổi schema. Chỉ tạo bảng nếu nó phục vụ một mẫu truy vấn có giá trị rõ ràng.

## 4. Xác lập bất biến và hợp đồng nhất quán

Trước khi lập trình, cần viết ra **bất biến nghiệp vụ**:

> Với mỗi `order_id` tồn tại trong bảng chuẩn, bản biểu diễn theo khách hàng và bản biểu diễn theo trạng thái cuối cùng phải phản ánh cùng trạng thái, cùng phiên bản; chỉ một vị trí trạng thái hợp lệ được giữ lại theo thiết kế truy vấn.

Cụm từ **“cuối cùng”** ở đây có chủ ý. Trong hệ phân tán, có thể xảy ra khoảng thời gian projection chưa theo kịp dữ liệu chuẩn. Hợp đồng đọc cần nói rõ ai chấp nhận được khoảng trễ đó và ai cần đọc từ bảng chuẩn.

Đề xuất phân vai như sau:

| Quyết định | Quy tắc |
|---|---|
| Nguồn dữ liệu chuẩn | `orders_by_id` là nơi xác nhận trạng thái nghiệp vụ |
| Định danh ổn định | `order_id` không đổi; request tạo lại phải giữ cùng mã/idempotency key |
| Đồng hồ nghiệp vụ | `version` tăng theo lần chuyển trạng thái đã được chấp nhận |
| Metadata để sửa | Giữ `created_at`, `customer_id`, `day` và trạng thái trước/sau trong sự kiện hoặc lịch sử thay đổi cần thiết |
| Đọc cần trạng thái vừa xác nhận | Ưu tiên bảng chuẩn và consistency level phù hợp |
| Đọc danh sách/tổng hợp | Đọc projection và chấp nhận độ trễ đã công bố |
| Lỗi đồng bộ projection | Ghi nhận để retry và đối soát, không im lặng coi là đồng bộ thành công |

Cassandra dùng timestamp của từng cell để giải quyết các lần ghi cạnh tranh theo cơ chế *last-write-wins* (trừ các trường hợp dùng cơ chế điều kiện phù hợp). **Chỉ thêm cột `version` không làm Cassandra tự ngăn được bản ghi phiên bản cũ ghi đè bản ghi mới.** Muốn dựa vào phiên bản, ứng dụng phải kiểm tra phiên bản khi ghi, bảo đảm xử lý theo thứ tự cho từng đơn, hoặc có cơ chế tái dựng từ nguồn chuẩn khi phát hiện sai lệch.

## 5. Những cách triển khai cập nhật nhiều bảng

Có ba hướng chính; có thể kết hợp chúng tùy SLA và mức độ phức tạp.

### 5.1. Ghi đồng bộ các bảng trong cùng request

Request ghi bảng chuẩn, sau đó ghi từng projection và chỉ trả thành công khi các thao tác cần thiết được xác nhận.

**Ưu điểm:** triển khai dễ hiểu, sau một request thành công các bảng thường đã cập nhật theo đường ghi của request.

**Giới hạn:** nếu bảng chuẩn ghi thành công nhưng projection lỗi hoặc client timeout, hệ thống vẫn có trạng thái không đồng bộ. Request bị timeout không chứng minh các lệnh ghi đã thất bại: một hoặc nhiều lệnh có thể đã được Cassandra chấp nhận.

Phù hợp khi số projection ít, lưu lượng vừa phải, có cơ chế **retry an toàn + đối soát**, và độ trễ thêm của các lệnh ghi đáp ứng SLA.

### 5.2. Ghi nguồn chuẩn, cập nhật projection bất đồng bộ

Luồng thường gặp:

1. Xác nhận thay đổi trên bảng chuẩn.
2. Tạo tín hiệu bền vững về thay đổi (chẳng hạn qua cơ chế CDC được vận hành phù hợp hoặc một cơ chế phát sự kiện có bảo đảm).
3. Consumer nhận sự kiện, cập nhật projection theo `order_id` và `version`.
4. Lặp lại khi có lỗi tạm thời; đưa sự kiện không xử lý được sang kênh xử lý lỗi và đối soát.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant C as Canonical table
    participant S as Change stream
    participant P as Projection worker
    participant V as Query tables
    API->>C: Ghi trạng thái chuẩn
    C-->>API: Xác nhận ghi
    C-->>S: Tín hiệu thay đổi bền vững
    S->>P: Giao sự kiện (có thể lặp)
    P->>V: Upsert / delete projection
    P-->>S: Ack sau khi xử lý
    Note over P,V: Retry, kiểm soát thứ tự và đối soát
~~~

**Điểm đặc biệt quan trọng:** gọi API phát message **sau** khi ghi Cassandra, rồi cho rằng cả hai thao tác là “một giao dịch”, sẽ tạo lỗ hổng khi tiến trình chết giữa hai bước. Nếu dùng outbox hoặc CDC, phải xác minh chính xác bảo đảm của giải pháp: nơi lưu sự kiện, tính bền vững, thứ tự, cơ chế replay, dữ liệu bị trùng, backlog và khả năng phục hồi khi tiến trình gián đoạn. Không mặc định rằng một bảng outbox riêng trong Cassandra tự có giao dịch ACID với bảng chuẩn.

Hướng này phù hợp khi chấp nhận **eventual consistency** và cần tách latency của giao diện khỏi chi phí cập nhật nhiều bảng.

### 5.3. Dùng CQL batch cho một nhóm mutation có ràng buộc

CQL cung cấp `LOGGED BATCH` và `UNLOGGED BATCH`. **Logged batch** có cơ chế batch log để giúp các mutation trong batch cuối cùng được áp dụng cùng nhau trong điều kiện cluster có thể phục hồi; nó **không cung cấp isolation cho người đọc** và không biến nhiều partition thành một giao dịch quan hệ có rollback theo nghiệp vụ.

~~~sql
BEGIN LOGGED BATCH
    UPDATE orders_by_customer
    SET status = ?, version = ?
    WHERE customer_id = ? AND created_at = ? AND order_id = ?;

    DELETE FROM orders_by_status_day
    WHERE status = ? AND day = ? AND created_at = ? AND order_id = ?;

    INSERT INTO orders_by_status_day (
        status, day, created_at, order_id, customer_id, total_amount, version
    ) VALUES (?, ?, ?, ?, ?, ?, ?);
APPLY BATCH;
~~~

Đoạn CQL này minh họa **gom các mutation của projection** khi trạng thái thay đổi; các dấu hỏi phải được bind theo thứ tự tương ứng. Không có bảo đảm rằng người đọc không bao giờ nhìn thấy trạng thái trung gian.

| Cơ chế | Bảo đảm đáng lưu ý | Điều không nên suy diễn |
|---|---|---|
| Ghi lẻ với `LOCAL_QUORUM` | Mỗi thao tác ghi được xác nhận theo mức replica yêu cầu trong local DC | Không đồng bộ/atomic giữa các bảng |
| `LOGGED BATCH` | Batch log hỗ trợ tính atomic của tập mutation theo nghĩa **cuối cùng được áp dụng** | Không có isolation, rollback nghiệp vụ hay read-modify-write transaction xuyên partition |
| `UNLOGGED BATCH` | Gửi nhóm mutation mà không dùng batch log | Không có bảo đảm atomic của logged batch; không nên dùng để “chữa” sai lệch |
| LWT với `IF` | Điều kiện được kiểm tra theo cơ chế đồng thuận cho thao tác/phạm vi hợp lệ | Không tự bảo vệ các projection ở partition khác |

Dùng batch **nhỏ, có chủ đích**, đo latency và số partition bị tác động. Batch lớn xuyên nhiều partition tăng tải cho coordinator và batch log; **batch không phải công cụ tăng tốc bulk insert**. Với các thao tác nhiều partition độc lập, thường hiệu quả hơn khi dùng các lệnh ghi riêng có điều tiết concurrency. Nếu mọi mutation thuộc cùng một partition phù hợp, thao tác sẽ có đặc tính hiệu quả và atomicity khác so với batch xuyên partition; vẫn phải hiểu phạm vi giới hạn của Cassandra.

## 6. Triển khai với Spring Data Cassandra

### 6.1. Mapping nguồn chuẩn và Repository

Spring Data Cassandra giúp ánh xạ entity và truy cập bảng theo khóa chính. Với Java hiện đại, có thể khai báo entity bất biến bằng record nếu phiên bản Spring Data đang dùng hỗ trợ record mapping.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public record OrderById(
    @PrimaryKey("order_id") UUID orderId,
    @Column("customer_id") UUID customerId,
    @Column("created_at") Instant createdAt,
    @Column("status") String status,
    @Column("total_amount") BigDecimal totalAmount,
    @Column("updated_at") Instant updatedAt,
    @Column("version") long version
) {}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}
~~~

Ứng dụng có thể đọc trạng thái hiện tại qua `repository.findById(orderId)`. Cần phân biệt: `repository.save(entity)` là thao tác ghi/upsert thông thường; nó **không tự thực hiện `IF NOT EXISTS` hay kiểm tra phiên bản**. Những nơi cần tránh tạo trùng hoặc cập nhật đè trạng thái, phải sử dụng câu CQL điều kiện hay cơ chế kiểm soát cạnh tranh tương ứng.

Hai bảng projection có khóa chính ghép; có thể tạo entity với `@PrimaryKeyClass`, `@PrimaryKeyColumn` và repository riêng. Ví dụ dưới đây tập trung vào luồng mutation để thấy rõ khóa mà truy vấn phải cung cấp, dùng `CqlSession` của DataStax Java Driver được quản lý trong ứng dụng Spring. Với câu CQL tùy biến, bạn cũng có thể dùng `CqlTemplate`/`CassandraTemplate` khi API tương ứng đáp ứng nhu cầu.

### 6.2. Writer ghi projection với khóa xác định

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.LocalDate;

public final class OrderProjectionWriter {
    private final CqlSession session;
    private final PreparedStatement upsertCustomer;
    private final PreparedStatement upsertStatus;
    private final PreparedStatement deleteOldStatus;

    public OrderProjectionWriter(CqlSession session) {
        this.session = session;
        this.upsertCustomer = session.prepare("""
            INSERT INTO orders_by_customer
                (customer_id, created_at, order_id, status,
                 total_amount, version)
            VALUES (?, ?, ?, ?, ?, ?)
            """);
        this.upsertStatus = session.prepare("""
            INSERT INTO orders_by_status_day
                (status, day, created_at, order_id,
                 customer_id, total_amount, version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """);
        this.deleteOldStatus = session.prepare("""
            DELETE FROM orders_by_status_day
            WHERE status = ? AND day = ?
              AND created_at = ? AND order_id = ?
            """);
    }

    public void upsertCurrent(OrderById order, LocalDate day) {
        session.execute(upsertCustomer.bind(
            order.customerId(), order.createdAt(), order.orderId(),
            order.status(), order.totalAmount(), order.version()));

        session.execute(upsertStatus.bind(
            order.status(), day, order.createdAt(), order.orderId(),
            order.customerId(), order.totalAmount(), order.version()));
    }

    public void removeOldStatus(
            OrderById order, LocalDate day, String oldStatus) {
        session.execute(deleteOldStatus.bind(
            oldStatus, day, order.createdAt(), order.orderId()));
    }
}
~~~

Code minh họa sử dụng **prepared statement** để bind tham số, tránh nối dữ liệu động trực tiếp vào CQL. `day` phải được tính nhất quán từ `created_at`; thời gian và cách quy đổi múi giờ không được thay đổi tùy từng lần replay.

Đây là **writer cơ bản**: nó chưa tự xử lý phiên bản cũ, retry, đồng bộ theo thứ tự hay công việc đối soát. Nếu triển khai trực tiếp trong consumer có sự kiện đến sai thứ tự, một `INSERT` cũ có thể ghi đè thông tin mới; vì thế chỉ gọi `upsertCurrent` sau khi đã thỏa hợp đồng thứ tự/phiên bản ở mục tiếp theo. Kết nối `CqlSession` nên do Spring quản lý; không tự mở session mới cho từng request.

### 6.3. Chuyển trạng thái có điều kiện tại bảng chuẩn

Ví dụ một đơn đang có `version = 7` và trạng thái `PAID`. Muốn đổi thành `SHIPPED`, trước hết ứng dụng xác nhận điều kiện trên **bảng chuẩn**:

~~~sql
UPDATE orders_by_id
SET status = 'SHIPPED',
    updated_at = ?,
    version = 8
WHERE order_id = ?
IF version = 7;
~~~

Với CQL điều kiện, driver trả về trạng thái áp dụng:

~~~java
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

// Áp dụng cho một đơn đã được đọc và kiểm tra luật chuyển trạng thái.
SimpleStatement statement = SimpleStatement.newInstance(
    """
    UPDATE orders_by_id
    SET status = ?, updated_at = ?, version = ?
    WHERE order_id = ?
    IF version = ?
    """,
    "SHIPPED", changedAt, 8L, orderId, 7L
);

ResultSet result = session.execute(statement);
if (!result.wasApplied()) {
    // Có thay đổi cạnh tranh: đọc lại bản chuẩn, kiểm tra yêu cầu,
    // quyết định thử lại với version mới hoặc báo conflict.
    throw new ConcurrentModificationException(
        "Order version was changed by another writer");
}
~~~

`IF version = 7` là một ví dụ LWT trên khóa `order_id`. Cần kiểm tra trạng thái trước đó theo luật nghiệp vụ (chẳng hạn không cho `CANCELLED` chuyển `SHIPPED`); chỉ kiểm tra số phiên bản chưa đủ để thể hiện mọi luật chuyển trạng thái.

Sau khi LWT thành công, ứng dụng tạo nhiệm vụ đồng bộ projection gồm **`order_id`, `oldStatus`, `newStatus`, `version`, `created_at`**, và các khóa liên quan. Không thể giả định vì LWT trên `orders_by_id` thành công thì các bảng projection đã được cập nhật. LWT cũng tăng chi phí và độ trễ, nên dùng cho các ràng buộc thật sự cần kiểm soát cạnh tranh, không mặc định cho mọi câu ghi.

### 6.4. Thay đổi trạng thái là *di chuyển dòng*, không chỉ update một cột

Đối với `orders_by_status_day`, `status` thuộc partition key. Cassandra không cho cập nhật partition key của một dòng bằng `UPDATE`. Phải coi thao tác này là:

1. Xác nhận thay đổi trên nguồn chuẩn.
2. Ghi/cập nhật nội dung mới ở `orders_by_customer`.
3. **Xóa khóa cũ** `(PAID, day, created_at, order_id)`.
4. **Thêm khóa mới** `(SHIPPED, day, created_at, order_id)`.
5. Ghi nhận hoàn thành hoặc tiếp tục sửa sai lệch.

Nếu mất `oldStatus` hoặc `day`, bộ đồng bộ không biết chắc phải xóa khóa nào. Vì vậy sự kiện thay đổi cần mang khóa cũ hoặc hệ thống phải có nguồn đáng tin cậy để tìm lại vị trí cũ. Truy vấn quét toàn bảng chỉ để đoán trạng thái cũ là dấu hiệu thiết kế chưa đủ metadata.

**Xóa trong Cassandra tạo tombstone.** Khi trạng thái thay đổi thường xuyên, số tombstone trong bảng theo trạng thái có thể lớn, ảnh hưởng đọc và compaction. Nếu một bản ghi di chuyển quá nhiều giữa partition, nên cân nhắc lại mẫu truy vấn, granularity của projection hoặc chiến lược lưu lịch sử.

### 6.5. Tạo đơn idempotent

Khi tạo đơn, request từ client nên có **định danh yêu cầu ổn định**. Có thể cấp `order_id` từ trước rồi dùng CQL:

~~~sql
INSERT INTO orders_by_id (
    order_id, customer_id, created_at, status,
    total_amount, updated_at, version
) VALUES (?, ?, ?, 'CREATED', ?, ?, 1)
IF NOT EXISTS;
~~~

Nếu `IF NOT EXISTS` không được áp dụng, **không lập tức coi đó là lỗi hệ thống**: có thể đây là request đã được xử lý và client đang thử lại. Cần kiểm tra order hiện có có đúng danh tính/yêu cầu ban đầu hay là xung đột định danh, sau đó tiến hành đồng bộ lại projection dựa trên **trạng thái chuẩn mới nhất**. Không lấy payload `CREATED` cũ ghi đè trạng thái `SHIPPED` đã phát sinh sau lần tạo đầu tiên.

Một lần timeout sau lệnh `IF NOT EXISTS` có kết quả **chưa xác định** từ phía client. Cách an toàn là đọc/kiểm tra bảng chuẩn theo cùng `order_id` và hòa giải; không phát sinh `order_id` khác cho cùng nghiệp vụ chỉ vì request trước timeout.

## 7. Thiết kế retry và tính idempotent thật sự

### 7.1. Phân loại lỗi

| Tình huống | Điều đã biết | Xử lý phù hợp |
|---|---|---|
| Ghi chuẩn thất bại trước khi được xác nhận | Chưa thể kết luận trạng thái chuẩn nếu lỗi do timeout | Đọc lại nguồn chuẩn; retry có điều kiện với cùng request ID |
| Ghi chuẩn thành công, projection thất bại | Nguồn chuẩn mới hơn projection | Đưa đơn vào hàng chờ sửa; retry cập nhật projection |
| Writer chết sau khi ghi projection nhưng trước ack | Projection có thể đã đúng | Chạy lại thao tác idempotent, kiểm tra phiên bản |
| Một sự kiện được giao hai lần | Trùng lặp là bình thường ở hệ thống at-least-once | Cùng khóa, cùng phiên bản và không phát sinh tác dụng phụ hai lần |
| Sự kiện phiên bản 8 đến trước phiên bản 7 | Replay cũ có thể ghi đè nếu upsert vô điều kiện | Kiểm soát thứ tự theo `order_id` hoặc cập nhật có guard phiên bản và đối soát |
| Đã thêm dòng mới nhưng chưa xóa dòng cũ | Một đơn xuất hiện ở hai danh sách trạng thái | Sửa bằng cách đối chiếu chuẩn, xóa vị trí cũ, kiểm tra lại |

### 7.2. Ba lớp bảo vệ khi retry

**Lớp 1 — Khóa ổn định.** Dùng lại `order_id` và các clustering key như `created_at` trong mọi lần ghi. Nếu mỗi lần retry tạo timestamp mới trong khóa, Cassandra sẽ tạo thêm dòng thay vì cập nhật cùng dòng.

**Lớp 2 — Sự kiện có danh tính và phiên bản.** Mỗi thay đổi mang `event_id` hoặc `(order_id, version)` đủ để nhận diện lần xử lý. Lưu `oldStatus`, `newStatus` và khóa projection để thao tác xóa/ghi có thể được dựng lại.

**Lớp 3 — Chống ghi lùi.** Đảm bảo cập nhật cho từng `order_id` được tuần tự hóa, hoặc dùng cơ chế ghi điều kiện phù hợp cho projection và đối soát sau xung đột. Nếu event v7 đến sau v8, không được upsert vô điều kiện v7. Tăng phiên bản trong payload nhưng không thực thi guard **không đủ**.

Cassandra không phải một hàng đợi có total order cho mọi partition. Nếu cần xử lý theo thứ tự, nên thiết kế partition của luồng sự kiện theo `order_id`, một luồng xử lý/khóa logic cho từng order, quy tắc retry và tình huống consumer rebalance. Dù có bảo đảm thứ tự, đối soát vẫn cần vì lỗi vận hành và dữ liệu lịch sử có thể tồn tại.

### 7.3. Đừng dùng phép cộng không idempotent để cập nhật projection

Một thao tác kiểu “tăng số đơn đang giao thêm 1” không thể retry mù quáng nếu không có cơ chế chống trùng. Tương tự, các phép thay đổi dựa trên giá trị cũ, counter, side effect gửi email/thanh toán phải có hợp đồng idempotency riêng. Với projection theo đơn, **ghi giá trị hiện tại theo khóa xác định** thường dễ phục hồi hơn phép cộng/trừ.

Nếu cần số liệu tổng hợp, có thể cân nhắc pipeline aggregate độc lập với cơ chế dedup hoặc phép tính lại từ nguồn đã xác định; không suy ra rằng counter Cassandra giải quyết mọi vấn đề atomic giữa nhiều bảng.

## 8. Consistency level giải quyết phần nào?

Ở Cassandra, consistency level cho biết số replica cần đáp ứng để một **thao tác trên dữ liệu** được xác nhận. Chẳng hạn với replication factor 3 trong một data center, `LOCAL_QUORUM` thông thường cần phản hồi từ đa số replica của DC đó. Mức phù hợp phải phụ thuộc topology, replication factor, SLA về availability và đường đọc/ghi.

Giả sử API:

1. Ghi `orders_by_id` tại `LOCAL_QUORUM` và được xác nhận.
2. Ghi `orders_by_customer` tại `LOCAL_QUORUM` và được xác nhận.
3. Ghi `orders_by_status_day` bị timeout.

Không có suy luận hợp lệ nào từ hai lần `LOCAL_QUORUM` đầu tiên rằng bảng thứ ba đã đúng. Tăng lên `ALL` cho cả ba thao tác cũng không khiến chúng có transaction chung; nó chỉ thay đổi mức replica xác nhận của **từng thao tác** và làm giảm khả năng sẵn sàng khi replica bị lỗi.

Trong đường đọc yêu cầu phản ánh thay đổi vừa thực hiện:

- Đọc **bảng chuẩn**, dùng consistency level phù hợp với đường ghi và locality mong muốn.
- Không bắt buộc màn hình chi tiết phụ thuộc vào projection đang xử lý bất đồng bộ.
- Với danh sách theo trạng thái, trình bày SLA độ trễ projection hoặc cung cấp hành vi phù hợp khi có độ trễ.
- Nếu client nhận timeout, xác minh trạng thái hiện tại thay vì suy diễn “ghi chưa xảy ra”.

**LWT và serial consistency:** câu `IF` dùng cơ chế đồng thuận riêng, có cấu hình consistency bình thường và serial consistency (ví dụ `LOCAL_SERIAL` khi phù hợp). Nó kiểm soát điều kiện trong phạm vi LWT được Cassandra hỗ trợ; không tạo atomicity xuyên các projection ngoài phạm vi đó.

## 9. Phát hiện sai lệch trước khi nó thành lỗi người dùng

Sai lệch có thể đến từ lỗi ứng dụng, consumer ngừng hoạt động, retry bị bỏ quên, dữ liệu cũ không được xóa, thay đổi schema, chuyển version ứng dụng hoặc import dữ liệu. Hệ thống nên có **hai đường phát hiện**.

### 9.1. Phát hiện trực tuyến

Khi một thao tác đồng bộ thất bại, ghi lại tối thiểu:

- `order_id`, `version` kỳ vọng, loại projection cần sửa.
- `oldStatus`, `newStatus`, `day`, `created_at` và các khóa cần xóa/thêm.
- Mã lỗi, số lần retry, thời gian ghi nhận, thời gian thử tiếp theo.
- Correlation ID để nối log yêu cầu API với log worker.

Công việc sửa phải có nơi lưu bền vững hoặc khả năng tái dựng từ stream/nguồn chuẩn. Chỉ log một dòng “projection failed” rồi bỏ qua sẽ không bảo đảm sửa được dữ liệu.

### 9.2. Đối soát định kỳ

Đối soát truy xuất bản chuẩn và projection trong một tập khóa có kiểm soát:

~~~text
Với từng order_id cần kiểm tra:
  1. Đọc orders_by_id: customer_id, created_at, status, version.
  2. Tính day và khóa projection kỳ vọng.
  3. Đọc chính xác dòng orders_by_customer theo khóa.
  4. Đọc chính xác dòng orders_by_status_day tại trạng thái kỳ vọng.
  5. Kiểm tra thuộc tính + version và dấu hiệu dòng trạng thái cũ.
  6. Nếu thiếu/sai: lập tác vụ reconcile theo canonical mới nhất.
  7. Đọc kiểm tra sau sửa hoặc tiếp tục retry khi có ghi cạnh tranh.
~~~

Ví dụ sau một sự cố:

| Bảng | Giá trị đọc được | Đánh giá |
|---|---|---|
| `orders_by_id` | `SHIPPED`, version 8 | Bản chuẩn |
| `orders_by_customer` | `PAID`, version 7 | Chưa cập nhật |
| `orders_by_status_day` với khóa `(PAID, day, ...)` | Vẫn còn dòng | Dòng cũ chưa xóa |
| `orders_by_status_day` với khóa `(SHIPPED, day, ...)` | Không có dòng | Dòng mới chưa thêm |

Reconciler cần cập nhật `orders_by_customer` lên dữ liệu chuẩn, xóa dòng `PAID`, tạo dòng `SHIPPED` và xác nhận cuối cùng. Nếu trong lúc sửa đơn đã tăng lên version 9, phải xử lý theo trạng thái mới nhất, không “đóng đinh” version 8 để hoàn tất bằng mọi giá.

**Nguồn danh sách để đối soát:** không quét production bằng một truy vấn thiếu partition key hoặc thêm `ALLOW FILTERING` cho tiện. Có thể dùng change stream, danh sách yêu cầu lỗi, bucket theo thời gian, token-range scan có paging và throttling, hoặc snapshot/offline job. Với quét toàn bộ dữ liệu, cần kế hoạch tải, checkpoint, độ phủ và cơ chế tiếp tục sau gián đoạn.

### 9.3. Khó khăn khi tìm dòng thừa

Dựa vào bảng chuẩn, có thể tính **vị trí đúng** của đơn trong projection. Nhưng để tìm mọi dòng sai nằm ở các partition trạng thái khác, phải biết khóa cũ hoặc có chỉ mục/nghiệp vụ hỗ trợ đối soát. Việc bản chuẩn nói `SHIPPED` không đủ để khẳng định dòng `PAID` đã biến mất nếu chưa kiểm tra vị trí cũ.

Để xử lý, có thể:

- Mang `oldStatus` và khóa cũ trong sự kiện chuyển trạng thái.
- Lưu lịch sử chuyển trạng thái đủ để tái dựng các vị trí cần xóa.
- Với miền trạng thái nhỏ và bucket đã biết, kiểm tra các vị trí ứng viên trong một công việc đối soát được giới hạn rõ ràng.
- Định kỳ kiểm tra ngược từ projection sang chuẩn để phát hiện dòng “mồ côi”.

Cách chọn phải dựa trên số trạng thái, lưu lượng và chi phí đọc chéo partition.

## 10. Thuật toán reconcile an toàn hơn

Một job reconcile **không được tự cho mình là writer duy nhất**. Nó có thể chạy cùng lúc với API chuyển trạng thái hoặc nhiều worker khác. Thuật toán cần xử lý hiện trạng mới.

~~~text
reconcile(order_id):
  canonical = readCanonical(order_id)
  if canonical missing:
      route to deletion/tombstone policy; do not guess
  targetKey = deriveProjectionKeys(canonical)

  existing = inspectKnownProjectionKeys(order_id, canonical)
  if existing already matches target + version:
      record success
      return

  coordinatePerOrderOrUseVersionGuard(order_id)
  canonicalAgain = readCanonical(order_id)
  if canonicalAgain differs from canonical:
      reschedule using the newer canonical
      return

  repairCustomerProjection(canonicalAgain)
  removeKnownObsoleteStatusKeys(order_id)
  upsertCurrentStatusProjection(canonicalAgain)

  verifyOrRescheduleIfConcurrentChange()
~~~

Đây là **pseudocode về hợp đồng xử lý**, không phải mã có thể chạy nguyên xi. `coordinatePerOrderOrUseVersionGuard` phải được hiện thực cụ thể, ví dụ một owner xử lý theo khóa `order_id` hoặc cập nhật projection có điều kiện phiên bản. Nếu không có cơ chế này, hai worker có thể cùng đọc canonical ở hai thời điểm khác nhau và ghi lùi khi xen kẽ.

Điểm cần đạt là **hội tụ về trạng thái chuẩn mới nhất**, không cố thực thi tất cả các sự kiện lịch sử lên bảng hiện tại bằng mọi giá.

## 11. Xóa đơn, TTL và vòng đời dữ liệu

Cassandra dùng tombstone khi `DELETE`. Nếu xóa dữ liệu chuẩn trước khi giữ lại thông tin vị trí các projection, job sửa có thể mất khả năng xác định những dòng phụ phải xóa.

Một hợp đồng xóa phù hợp có thể là:

1. Xác lập trạng thái xóa/hủy trên bản chuẩn (hoặc một hồ sơ xóa bền vững) và tạo dấu vết chứa toàn bộ khóa projection.
2. Xóa hoặc làm hết hiệu lực các projection với khả năng retry.
3. Kiểm tra không còn dòng phụ khả kiến theo hợp đồng.
4. Chỉ sau khi đủ điều kiện lưu trữ và phục hồi mới dọn bản chuẩn/dấu vết xóa.

Với `TTL`, các bảng có TTL khác nhau sẽ mất dữ liệu ở thời điểm khác nhau và có thể tạo “sai lệch đúng theo cấu hình”. Cần định nghĩa rõ đây có phải hành vi chấp nhận được không. Xem xét `gc_grace_seconds`, repair của replica, tombstone và yêu cầu tránh dữ liệu đã xóa xuất hiện lại khi một replica lâu ngày không đồng bộ. Không đặt TTL ngắn cho thông tin cần thiết để khôi phục projection sau sự cố dài.

## 12. Hiệu năng khi cập nhật nhiều projection

Độ trễ một thao tác nghiệp vụ không chỉ là latency của bảng chuẩn. Nếu request đồng bộ ghi ba bảng và xóa một dòng, tổng chi phí còn bao gồm độ trễ lệnh thêm, số partition liên quan, retry, batch log (nếu có) và điều tiết concurrency.

### Những rủi ro thường gặp

| Rủi ro | Triệu chứng | Hướng xử lý |
|---|---|---|
| Partition nóng theo trạng thái/ngày | Latency tăng đột biến ở ngày nhiều đơn | Shard/bucket hợp lý, đánh đổi fan-out khi đọc |
| Partition khách hàng quá lớn | Paging chậm, đọc nhiều dữ liệu không cần thiết | Bucket theo thời gian nếu truy vấn cho phép |
| Batch xuyên nhiều partition quá lớn | Coordinator/batch log chịu tải, timeout | Batch nhỏ cho bất biến cần thiết; hạn chế số partition |
| Ghi lại dữ liệu cũ | Trạng thái nhảy lùi, version projection thấp | Điều phối theo `order_id`, guard phiên bản, reconcile |
| Tombstone tích lũy | Đọc chậm, cảnh báo tombstone | Hạn chế di chuyển dòng, kiểm tra compaction/TTL |
| Retry đồng loạt | Tải tăng mạnh sau lỗi tạm thời | Exponential backoff, jitter, giới hạn số lần và concurrency |
| Consumer backlog | Danh sách hiển thị trạng thái cũ lâu | Theo dõi lag, tăng năng lực xử lý có kiểm soát |

Để đọc danh sách dài, dùng **paging state** của Cassandra/driver và giới hạn số bản ghi. Đừng dùng `OFFSET` kiểu cơ sở dữ liệu quan hệ; và đừng mặc định `Page` có tổng số phần tử là miễn phí. Mỗi projection nên có ngân sách riêng cho số partition đọc, kích thước partition và latency p95/p99.

### Các chỉ số nên theo dõi

- `projection_lag_seconds`: thời gian từ khi canonical đổi đến khi projection đạt version đó.
- `projection_write_failures_total` và `projection_retries_total`, phân theo bảng và loại lỗi.
- `reconciliation_mismatch_total`, `reconciliation_repair_total`, `reconciliation_backlog`.
- Tỷ lệ consumer xử lý trùng/sai thứ tự, kích thước dead-letter queue nếu dùng.
- Latency p95/p99 của CQL, timeout, tombstone scan, partition size và backlog compaction.
- Phần trăm đơn có projection lệch version sau một ngưỡng SLA.

Một SLO thực tế có thể viết: “99,9% các thay đổi đơn được phản ánh ở projection trong vòng 30 giây”, **chỉ sau khi đo và xác nhận khả năng đạt mục tiêu**. SLO về độ trễ phải đi cùng theo dõi số đơn không bao giờ hội tụ.

## 13. Kiểm thử các trường hợp khó

Bên cạnh unit test mapper/key derivation, cần kiểm thử tích hợp trên Cassandra tương thích phiên bản đang triển khai, với failure injection hoặc mô phỏng hợp lý ở lớp writer/consumer. Những ca sau quan trọng hơn việc chỉ kiểm tra đường thành công:

| Ca | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Tạo lặp | Gửi cùng `order_id` hai lần | Không có hai đơn nghiệp vụ; không tạo dòng projection thừa |
| Lỗi giữa chừng | Ghi canonical xong, lỗi ở bảng trạng thái | Canonical đúng; có nhiệm vụ sửa; projection cuối cùng hội tụ |
| Timeout không rõ kết quả | Client mất phản hồi sau câu ghi | Đọc lại trạng thái rồi quyết định retry; không tạo ID mới |
| Sự kiện trùng | Consumer nhận v8 hai lần | Không có tác dụng phụ kép; projection vẫn là v8 |
| Sai thứ tự | Consumer nhận v8 rồi v7 | Projection không bị hạ về v7 |
| Hai yêu cầu cạnh tranh | Cùng xuất phát từ version 7 | Chỉ yêu cầu hợp lệ được áp dụng theo quy tắc LWT/đồng thuận |
| Đổi partition | `PAID → SHIPPED` | Dòng `PAID` được loại bỏ và có đúng dòng `SHIPPED` |
| Worker chết khi sửa | Chết giữa delete và insert projection | Reconciler chạy lại được và cuối cùng hội tụ |
| Thay đổi trong lúc reconcile | Canonical lên v9 khi job đang sửa v8 | Job phát hiện/điều phối, không kết thúc bằng trạng thái v8 |
| Tải cao | Nhiều đơn cùng status/day | Không vượt mục tiêu partition/latency; retry được điều tiết |
| Xóa/TTL | Bản chuẩn hoặc projection hết hạn | Tuân thủ chính sách vòng đời, không để dữ liệu mồ côi |

Khi kiểm thử **logged batch**, kiểm tra cả việc một người đọc khác có thể nhìn thấy trạng thái trung gian. Đừng viết test chỉ xác nhận sau batch tất cả dòng đã có rồi kết luận batch cung cấp isolation.

Trong môi trường multi-DC, bổ sung test tình huống vùng mạng lỗi, đường đọc/ghi khác DC và sự khác nhau giữa `LOCAL_QUORUM`, `QUORUM`, `LOCAL_ONE` theo topology thực tế.

## 14. Các lỗi thiết kế hay gặp

**“Dùng `@Transactional` quanh ba lời gọi repository là đủ.”** Spring Data Cassandra không tự biến ba mutation ở các partition thành giao dịch ACID giống JDBC. Annotation transaction trong mã ứng dụng không thay thế việc xác minh transaction support thực tế và phạm vi bảo đảm của Cassandra/driver.

**“Bọc hết vào một logged batch, dữ liệu không thể lệch.”** Logged batch không cho isolation, không loại bỏ timeout chưa xác định, không thay thế việc áp dụng luật nghiệp vụ, và không xử lý mọi hậu quả của xử lý trùng/sai thứ tự.

**“Đặt mọi thao tác ở `ALL` là nhất quán tuyệt đối.”** `ALL` chỉ thay đổi mức replica phải xác nhận của từng thao tác; không đảm bảo tính atomic của nhiều bảng.

**“Mỗi bảng đều có thể là nguồn chân lý.”** Nếu một nơi ghi `CANCELLED` còn nơi khác ghi `SHIPPED`, không có quy tắc phân xử thì việc đối soát không biết nên chọn giá trị nào. Cần một thẩm quyền ghi hoặc mô hình xung đột được thiết kế rõ.

**“Có version nên upsert nào cũng an toàn.”** Cột version có ý nghĩa cho kiểm tra và chẩn đoán; việc ngăn ghi lùi đòi hỏi cơ chế ghi thực thi điều kiện/thứ tự, không chỉ lưu con số.

**“Reconcile sẽ tìm được mọi dòng cũ từ mỗi bản ghi chuẩn.”** Điều đó chỉ đúng khi có đủ metadata khóa cũ hoặc chiến lược quét ngược thích hợp. Với partition key thay đổi, phải xác định cách tìm và xóa vị trí cũ ngay khi thiết kế.

**“Dữ liệu thiếu trong danh sách chắc là do Cassandra consistency.”** Trước hết phải phân biệt replica lag trong cùng bảng với projection chưa được cập nhật giữa các bảng. Hai loại lỗi có phương án xử lý khác nhau.

## 15. Quy trình lựa chọn thiết kế trong dự án

Khi thêm một loại truy vấn mới vào ứng dụng Spring Data Cassandra, đi theo chuỗi câu hỏi sau:

1. **Truy vấn nào phải nhanh?** Định nghĩa điều kiện `WHERE`, thứ tự, kích thước trang và số bản ghi dự kiến.
2. **Projection nào cần thiết?** Xây schema đúng partition key; ước lượng kích thước/hot partition.
3. **Bảng chuẩn là gì?** Định nghĩa nơi quyết định trạng thái nghiệp vụ, định danh và luật chuyển đổi.
4. **Có thay đổi primary key của projection không?** Nếu có, xác định rõ thao tác xóa cũ, thêm mới và metadata khóa cũ.
5. **Mức trễ nào được phép?** Chọn ghi đồng bộ hoặc đồng bộ bằng stream, công bố hành vi khi projection chưa theo kịp.
6. **Khi một bước lỗi thì sao?** Chọn cơ chế bền vững để retry, idempotency key, version/order guard và reconcile.
7. **Batch có giải quyết một yêu cầu thật sự không?** Nếu dùng, xác định số partition, giới hạn kích thước và bảo đảm thực tế.
8. **Phát hiện và sửa lỗi thế nào?** Thiết kế chỉ số lag/mismatch, backfill, checkpoint và kế hoạch khôi phục.
9. **Đã thử lỗi cạnh tranh và replay chưa?** Test khi timeout, trùng sự kiện, sai thứ tự, xóa cũ, multi-DC, tải cao.
10. **Khi nhu cầu truy vấn thay đổi thì sao?** Dự kiến backfill bảng projection mới từ nguồn chuẩn, chuyển reader có kiểm soát, rồi dọn cấu trúc cũ.

## 16. Bài tập vận dụng

Một nền tảng giao hàng sử dụng ba bảng như ví dụ. Đơn `X` có `order_id` cố định, `created_at` là ngày 25/11/2026 theo UTC, `status = PREPARING`, `version = 12`. Request chuyển đơn sang `DELIVERING` với version 13 đã cập nhật bảng chuẩn thành công. Worker cập nhật bảng khách hàng thành công, thêm dòng `DELIVERING` thành công, nhưng timeout khi xóa dòng `PREPARING`.

**Hãy tự trả lời:**

1. Có thể kết luận dòng `PREPARING` chưa bị xóa hay không? Vì sao?
2. Nếu gửi lại lệnh xóa cùng đầy đủ khóa cũ, tác dụng của thao tác lặp là gì?
3. Nếu đơn đã chuyển tiếp sang `DELIVERED` version 14 khi retry, worker cần kiểm tra điều gì trước khi ghi lại các projection?
4. Cần lưu những metadata nào để đối soát biết chính xác các vị trí cần xóa?
5. Vì sao không giải quyết vấn đề chỉ bằng cách đổi tất cả câu ghi sang `LOCAL_QUORUM` hoặc gói chúng thành một logged batch lớn?

**Hướng giải:** Timeout là kết quả không xác định; phải kiểm tra/readback hoặc chạy lại thao tác có tính idempotent. Lệnh xóa đúng khóa có thể được chạy lại, nhưng một worker mang dữ liệu version 13 không được ghi lùi so với version 14. Cần biết `order_id`, `created_at`, `day`, trạng thái cũ/mới, phiên bản và các khóa projection. Consistency level và batch không tự thực hiện quy tắc chống ghi lùi hoặc xác định dữ liệu chuẩn nghiệp vụ.

---

## Ghi nhớ

Thiết kế phi chuẩn hóa trong Cassandra mang lại truy vấn nhanh vì **mỗi bảng phục vụ một cách truy cập cụ thể**, đổi lại ứng dụng phải sở hữu quy tắc đồng bộ các bản biểu diễn. Với Spring Data Cassandra, repository và template giúp thao tác dữ liệu thuận tiện; **sự hội tụ, idempotency, kiểm soát thứ tự và đối soát vẫn là trách nhiệm thiết kế ứng dụng**. Khi có nguồn chuẩn rõ ràng, khóa ổn định, metadata đầy đủ, cơ chế phục hồi và quan sát được độ trễ, hệ thống có thể cập nhật nhiều bảng một cách có kiểm soát ngay cả khi không có giao dịch ACID xuyên partition.

**Đọc thêm:** tài liệu Apache Cassandra về CQL `BATCH`, consistency levels, lightweight transactions, tombstone/repair; tài liệu Spring Data Cassandra về entity mapping, repository, `CassandraTemplate` và `CqlTemplate`. Khi áp dụng vào dự án, đối chiếu với **phiên bản Cassandra, Java Driver và Spring Data Cassandra thực tế** vì API và tính năng có thể thay đổi theo phiên bản.
