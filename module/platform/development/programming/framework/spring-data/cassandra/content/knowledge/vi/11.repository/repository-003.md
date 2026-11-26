# save, insert và ngữ nghĩa upsert của Cassandra

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao `INSERT` và `UPDATE` trong Apache Cassandra đều có **ngữ nghĩa upsert** và tại sao `repository.save(…)` không được hiểu như lệnh `INSERT` có ràng buộc duy nhất của RDBMS.
- Phân biệt trách nhiệm của `CassandraRepository`, `CassandraTemplate`, Java Driver và CQL trong việc ghi một entity.
- Phân tích tác động của **primary key**, **write timestamp**, **last-write-wins theo cell**, `null`, TTL, tombstone và ghi từng phần.
- Sử dụng CQL `IF NOT EXISTS`, `IF EXISTS` hoặc `IF <điều kiện>` khi nghiệp vụ cần cập nhật có điều kiện; hiểu chi phí và giới hạn của lightweight transaction (LWT).
- Xây dựng thao tác ghi an toàn trước retry, timeout không rõ kết quả, sự kiện sai thứ tự, thay đổi khóa và việc dữ liệu được nhân bản vào nhiều bảng phục vụ truy vấn.
- Kiểm chứng hành vi insert/upsert bằng ví dụ CQL, Spring Data repository, `CassandraTemplate` và kịch bản kiểm thử thực tế.

Bài thuộc chương **Repository** của **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra bằng entity mapping, repository, `CassandraTemplate` và CQL. Cassandra là cơ sở dữ liệu phân tán, thiết kế bảng **theo truy vấn** với partition key, clustering column, consistency level, paging và giới hạn tài nguyên. Khi thực hiện thao tác `save`, cần hiểu rõ những nguyên tắc đó vì Spring Data chỉ giúp lập và gửi câu lệnh; nó không biến Cassandra thành một RDBMS có giao dịch ACID và quản lý entity kiểu JPA.

> **Nguyên tắc nền tảng:** Trong Cassandra, một mutation thông thường được định danh bởi **primary key và các cột được ghi**. `INSERT` hay `UPDATE` có thể tạo dữ liệu nếu chưa tồn tại, đồng thời ghi đè giá trị cột tương ứng nếu khóa đã tồn tại. Nếu cần hành vi “chỉ tạo mới khi chưa tồn tại”, phải dùng cơ chế ghi có điều kiện như `IF NOT EXISTS` và kiểm tra kết quả.

## 1. Hình dung đúng về thao tác ghi của Cassandra

Xét một ứng dụng đặt hàng, cần tra cứu chi tiết đơn hàng theo mã. Bảng CQL:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal,
    revision bigint
);
~~~

`order_id` là **partition key** của bảng này. Mỗi giá trị `order_id` định danh một row trong bảng `orders_by_id`.

Giả sử bảng ban đầu chưa có đơn hàng. Chạy:

~~~sql
INSERT INTO orders_by_id (
    order_id,
    customer_id,
    status,
    total_amount,
    revision
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'CREATED',
    150000.00,
    1
);
~~~

Kết quả là một row. Nhưng chạy tiếp câu lệnh với **cùng primary key**:

~~~sql
INSERT INTO orders_by_id (
    order_id, status, total_amount, revision
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'PAID',
    150000.00,
    2
);
~~~

Cassandra **không tự báo lỗi duplicate primary key** như một bảng SQL quan hệ thường làm khi gọi `INSERT`. Câu lệnh mới ghi các cột tương ứng trên row đã có khóa đó. Nếu các write timestamp khiến mutation mới thắng, kết quả là `status = PAID` và `revision = 2`. Cột `customer_id` không được liệt kê trong lệnh `INSERT` thứ hai thì không tự bị xóa chỉ vì vắng mặt trong danh sách cột.

Đây là hành vi upsert: **update nếu row/cell đã có, insert nếu chưa có**. Cassandra không cần một bước đọc trước để quyết định nhánh tồn tại.

### 1.1. INSERT và UPDATE đều có thể upsert

Với cùng bảng, câu lệnh:

~~~sql
UPDATE orders_by_id
SET status = 'SHIPPED',
    revision = 3
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

cập nhật row theo khóa. Nếu một `order_id` chưa từng tồn tại, lệnh `UPDATE ... WHERE order_id = ...` thông thường cũng có thể tạo dữ liệu mới cho khóa đó, miễn là câu lệnh hợp lệ theo CQL và không có điều kiện ngăn ghi.

Vì thế:

| Lệnh | Khóa chưa tồn tại | Khóa đã tồn tại | Mặc định có kiểm tra tồn tại không? |
| --- | --- | --- | --- |
| `INSERT INTO ... VALUES ...` | Ghi dữ liệu mới | Ghi các giá trị cột được chỉ định | Không |
| `UPDATE ... SET ... WHERE full_primary_key = ...` | Có thể tạo row/cell mới | Cập nhật các cột chỉ định | Không |
| `INSERT ... IF NOT EXISTS` | Chỉ ghi nếu điều kiện thỏa | Không áp dụng mutation nếu row đã tồn tại | Có, qua LWT |
| `UPDATE ... IF EXISTS` | Không áp dụng nếu row không tồn tại | Cập nhật nếu kiểm tra có row | Có, qua LWT |
| `UPDATE ... IF status = 'CREATED'` | Không tự tạo theo cách upsert vô điều kiện | Chỉ cập nhật nếu giá trị hiện tại thỏa điều kiện | Có, qua LWT |

Các lệnh có điều kiện phải được dùng ở **đúng primary key**, với chi phí điều phối/đồng thuận cao hơn ghi thông thường. Điều kiện không biến thao tác trên nhiều bảng và nhiều partition thành một giao dịch RDBMS tổng quát.

### 1.2. Upsert không phải “ghi đè toàn bộ object”

Cần phân biệt:

- **Các cột được gửi trong mutation:** có thể nhận write timestamp và giá trị mới.
- **Các cột không được gửi:** nhìn chung vẫn giữ trạng thái hiện tại, nhưng kết quả thực tế còn phụ thuộc các mutation khác, TTL và delete đã xảy ra.
- **Các cột được gửi với `null`:** có thể tương ứng với thao tác xóa/tombstone, tùy lệnh CQL và cơ chế binding.
- **Một row Cassandra:** tập các cell chịu ảnh hưởng bởi timestamp/tombstone, không giống entity managed có trạng thái thống nhất được flush trong một giao dịch JPA.

Khi ứng dụng gọi `repository.save(entity)`, không nên tự suy rằng Spring Data luôn sinh đúng một câu `UPDATE status = ?` để chỉ sửa trường status. Phạm vi cột được ghi phụ thuộc metadata entity và thao tác mà lớp Spring Data sử dụng. Nếu chỉ muốn cập nhật một vài cột và giữ nguyên phần còn lại, hãy dùng một lệnh `UPDATE`/query **tường minh** và xác minh câu CQL được phát ra.

## 2. CassandraRepository.save(…) thực chất cam kết gì?

Ví dụ entity:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderById {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("created_at")
    private Instant createdAt;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    @Column("revision")
    private Long revision;

    public OrderById() {
    }

    // Constructor, getters và setters phù hợp...
}
~~~

Repository:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}
~~~

Service có thể lưu entity:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderByIdRepository repository;

    public OrderService(OrderByIdRepository repository) {
        this.repository = repository;
    }

    public OrderById save(OrderById order) {
        return repository.save(order);
    }
}
~~~

`CassandraRepository` cung cấp giao diện lưu/đọc quen thuộc, chuyển metadata mapping thành thao tác CQL. Điều quan trọng khi gọi `save`:

1. **Khóa chính xác định địa chỉ row.** Hai entity mang cùng `orderId` đều nhắm cùng row trong bảng này.
2. **`save` không đồng nghĩa với kiểm tra duy nhất.** Không được kỳ vọng một lần gọi `save` thứ hai cùng ID mặc định ném lỗi duplicate key.
3. **`save` không mở ra giao dịch JPA.** Entity vừa được đọc rồi sửa thuộc tính trong Java sẽ không tự flush nếu không gọi thao tác ghi.
4. **Không suy đoán câu CQL cụ thể chỉ từ tên phương thức.** Cách Spring Data quyết định INSERT/UPDATE và tùy chọn ghi phụ thuộc phiên bản, trạng thái entity và lớp repository/operations. Nhưng lệnh CQL vô điều kiện tương ứng vẫn mang ngữ nghĩa upsert.
5. **`save` chỉ thao tác với bảng entity được ánh xạ.** Nếu cùng đơn hàng có trong `orders_by_customer_month`, repository này không tự cập nhật read model đó.

### 2.1. Khác với save của JPA ở đâu?

| Khía cạnh | Spring Data JPA trên RDBMS | Spring Data Cassandra |
| --- | --- | --- |
| `save` / entity lifecycle | Có thể quản lý trạng thái managed/detached trong persistence context | Không có persistence context và dirty checking kiểu JPA |
| INSERT trùng primary key | Thường vi phạm unique/PK constraint | `INSERT` CQL thông thường là upsert |
| Ghi nhiều bảng | Có thể nằm trong transaction DB có rollback phù hợp | Không mặc định có transaction ACID đa bảng |
| Thay đổi object sau khi đọc | Có thể flush khi commit nếu managed | Phải có lời gọi ghi tường minh |
| Đổi primary key | Thường bị hạn chế/đòi hỏi xử lý riêng trong ORM | Địa chỉ row thay đổi; row cũ không tự biến mất |
| Truy vấn theo trường bất kỳ | SQL/index/join tùy schema và kế hoạch thực thi | Phải thiết kế partition/clustering/index theo access pattern |
| Conflict resolution | Isolation/locking/version tùy RDBMS | Write timestamp theo cell; LWT nếu cần CAS |

Tình huống hay nhầm:

~~~java
OrderById order = repository.findById(orderId).orElseThrow();
order.setStatus("PAID");

// Chỉ sửa object Java chưa bảo đảm Cassandra đã nhận mutation.
// Cần thực hiện repository.save(order) hoặc UPDATE tường minh.
~~~

Không nên coi entity Cassandra là managed entity của Hibernate.

### 2.2. Kiểm tra tồn tại trước khi save có bảo vệ được không?

Một cách viết thường gặp:

~~~java
if (!repository.existsById(orderId)) {
    repository.save(newOrder);
}
~~~

Đây là mô hình **check-then-act** có race condition:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant C as Cassandra

    A->>C: SELECT/existsById(orderId)
    B->>C: SELECT/existsById(orderId)
    C-->>A: Không thấy row
    C-->>B: Không thấy row
    A->>C: save(order A)
    B->>C: save(order B)
    Note over C: Cả hai có thể ghi cùng khóa
~~~

Hai client cùng đọc trạng thái “chưa tồn tại” rồi cùng ghi. Chúng không tự loại trừ nhau. Consistency level cao hơn có thể cải thiện cách đọc replica nhưng không biến hai bước tách rời thành một thao tác atomic compare-and-set.

Nếu yêu cầu nghiệp vụ là **chỉ một request được quyền tạo đơn với ID đó**, hãy dùng `INSERT ... IF NOT EXISTS` hoặc cơ chế phối hợp phù hợp và kiểm tra kết quả LWT.

## 3. Dùng CassandraTemplate.insert và update khi cần chọn thao tác tường minh

`CassandraTemplate` cho phép làm việc gần tầng CQL hơn repository. API Spring Data thường có các phương thức:

~~~java
// cassandraTemplate được inject vào service qua constructor.
OrderById inserted = cassandraTemplate.insert(order);
OrderById updated  = cassandraTemplate.update(order);
~~~

Tên phương thức tách thao tác **INSERT** và **UPDATE** trong tầng Spring Data. Tuy nhiên, không được chuyển ý nghĩa từ RDBMS sang Cassandra:

- `insert(entity)` phát sinh thao tác theo ngữ nghĩa `INSERT` CQL; khi trùng primary key, nếu không có điều kiện LWT, Cassandra vẫn có thể ghi đè cell.
- `update(entity)` phát sinh thao tác theo ngữ nghĩa `UPDATE` CQL; với khóa chưa có, UPDATE thông thường vẫn có thể tạo row/cell.
- Hai phương thức không tự bảo đảm “create-only” hay “update-only” nếu không có **điều kiện tồn tại**.
- Tùy phiên bản Spring Data, các tùy chọn ghi như TTL, timestamp, consistency, conditional insert và update có thể được đặt qua options/builder hoặc CQL. Luôn đối chiếu API của version đang dùng.

Bảng ra quyết định:

| Mục tiêu | Cách tiếp cận phù hợp | Điều cần kiểm chứng |
| --- | --- | --- |
| Lưu snapshot theo ID, ghi lại cùng ID được chấp nhận | `repository.save(entity)` | Những field nào được ghi, null/TTL và chính sách retry |
| Cần biểu đạt INSERT trong lớp persistence | `cassandraTemplate.insert(entity)` | Mặc định vẫn upsert nếu không có điều kiện |
| Chỉ thay `status` hoặc một vài cột | CQL `UPDATE ... SET ... WHERE full key` | Không ghi nhầm null lên các cột khác |
| Chỉ tạo khi ID chưa có | `INSERT ... IF NOT EXISTS` | Phải đọc kết quả `[applied]` và xử lý xung đột |
| Cập nhật nếu có và trạng thái đúng | `UPDATE ... IF status = ...` | Chi phí LWT, retry và kết quả thất bại |
| Tăng counter | `UPDATE counter = counter + delta` | Không áp dụng save thông thường, retry không idempotent |

### 3.1. Ví dụ cập nhật một cột với CqlSession

Khi cần kiểm soát chính xác mutation:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public class OrderStatusWriter {

    private final CqlSession session;
    private final PreparedStatement updateStatus;

    public OrderStatusWriter(CqlSession session) {
        this.session = session;
        this.updateStatus = session.prepare(
            "UPDATE orders_by_id SET status = ? WHERE order_id = ?");
    }

    public void updateStatus(UUID orderId, String status) {
        BoundStatement statement = updateStatus.bind(status, orderId);
        session.execute(statement);
    }
}
~~~

Ví dụ trên giả định `CqlSession` do Spring Boot quản lý được inject vào adapter. Nó dùng **prepared statement** để tránh tự ghép tham số vào CQL, có thể tái sử dụng ở nhiều request. Ở bảng `orders_by_id`, `WHERE order_id = ?` là điều kiện đầy đủ theo partition key và primary key.

**Giới hạn:** UPDATE này vẫn tạo row/cell cho `order_id` chưa có; đồng thời không kiểm tra thứ tự chuyển trạng thái nghiệp vụ. Nếu cần “chỉ cập nhật đơn tồn tại và đang CREATED”, phải dùng `IF EXISTS` / `IF status = 'CREATED'` và kiểm tra LWT.

## 4. CQL INSERT/UPDATE ghi theo cell và write timestamp

Trong Cassandra, một row có thể gồm nhiều cell. Đối với các mutation cạnh tranh thông thường, mỗi cell có **write timestamp** dùng để giải quyết xung đột. Nguyên tắc phổ biến là **last-write-wins theo timestamp**, không phải “request nào về sau theo đồng hồ ứng dụng” hay “transaction nào commit sau” như ta có thể suy luận từ RDBMS.

Ví dụ hai client cập nhật cùng `status`:

~~~text
Client A: status = PAID     timestamp = T1
Client B: status = CANCELLED timestamp = T2

Nếu T2 > T1, trạng thái quyết định theo cell là CANCELLED,
ngay cả khi request A được quan sát hoàn tất muộn hơn request B.
~~~

Điểm dễ bỏ sót: conflict resolution diễn ra **theo cell**, không nhất thiết theo một version object/row:

~~~text
Mutation A, timestamp T1: status = PAID, total_amount = 100
Mutation B, timestamp T2: status = CANCELLED
Mutation C, timestamp T3: total_amount = 110
~~~

Một row đọc được có thể là `status = CANCELLED` và `total_amount = 110`, kết hợp giá trị từ nhiều mutation. Cassandra không tự bảo đảm một “snapshot entity” thống nhất về nghiệp vụ nếu nhiều writer ghi các cột vào những thời điểm khác nhau.

### 4.1. Write timestamp không đồng nghĩa business revision

Giả sử một hệ thống có trường `revision`:

~~~sql
UPDATE orders_by_id
SET status = 'PAID',
    revision = 8
WHERE order_id = ?;
~~~

Nếu một worker nhận lại event revision 7 và chạy:

~~~sql
UPDATE orders_by_id
SET status = 'CREATED',
    revision = 7
WHERE order_id = ?;
~~~

sau đó, mutation cũ có thể nhận write timestamp mới hơn và **làm lùi trạng thái ứng dụng** về revision 7. Cassandra không tự hiểu rằng 8 > 7 là version nghiệp vụ cần thắng.

Giải pháp phụ thuộc nhu cầu:

- Dùng **một writer theo khóa** với bảo đảm thứ tự, có cơ chế phục hồi/replay và kiểm soát hoạt động khi thay topology.
- Dùng **LWT so sánh revision/trạng thái** cho một row khi cần CAS và chấp nhận chi phí.
- Dùng mô hình event/snapshot có idempotency và quy tắc xử lý version rõ ràng.
- Giám sát, đối soát khi có nhiều read model hoặc projector bất đồng bộ.

Chỉ thêm cột `revision` rồi tiếp tục `save` vô điều kiện **không** giải quyết race condition.

### 4.2. Tự đặt TIMESTAMP: quyền lực đi kèm trách nhiệm

CQL cho phép chỉ định write timestamp, ví dụ:

~~~sql
UPDATE orders_by_id
USING TIMESTAMP 1795000000000000
SET status = 'PAID'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

Giá trị `TIMESTAMP` trong `USING TIMESTAMP` là **microseconds** kể từ Unix epoch, khác với cột CQL `timestamp` được lưu ở độ phân giải mili giây. Đây là hai khái niệm khác nhau dù cùng tên.

Dùng client-supplied timestamp tùy tiện có thể tạo xung đột khó xử lý:

- Đồng hồ các writer lệch nhau.
- Retry cũ dùng timestamp lớn hơn update mới.
- Một write timestamp tương lai có thể chặn cập nhật hợp lệ cho đến khi đồng hồ bắt kịp.
- Timestamp bằng nhau có quy tắc tie-break riêng, không thay thế business ordering.

Chỉ chọn custom timestamp khi kiến trúc đã định nghĩa chặt trách nhiệm tạo timestamp, phân vùng writer và cơ chế khôi phục. Với nghiệp vụ cần cập nhật có điều kiện, LWT/coordination thường dễ chứng minh tính đúng đắn hơn việc dựa vào timestamp do mỗi client tự nghĩ ra.

## 5. Null, cột vắng mặt và tombstone khi save

Giả sử một entity Java:

~~~java
OrderById patch = new OrderById();
patch.setOrderId(orderId);
patch.setStatus("PAID");

// customerId, createdAt, totalAmount, revision chưa được thiết lập.
repository.save(patch);
~~~

Đây là cách rất dễ phát sinh lỗi. Tùy đường mapping và chiến lược ghi của Spring Data, các property `null` có thể được đưa vào CQL, bỏ qua hoặc được biểu diễn khác nhau. Nếu mutation thực sự ghi `null` vào cột Cassandra, Cassandra có thể tạo **tombstone** để thể hiện việc xóa cell. Nếu field bị bỏ qua, trạng thái cũ có thể còn nguyên.

**Không được giả định rằng “save object mới chỉ chứa field muốn sửa” tương đương PATCH.** Nếu muốn cập nhật duy nhất `status`, sử dụng câu CQL `UPDATE ... SET status = ?` hoặc API update tường minh chỉ nhắm cột đó.

### 5.1. Ba ý nghĩa cần phân biệt

| Tình trạng | Ý nghĩa dự kiến | Nguy cơ |
| --- | --- | --- |
| Field không được gửi trong mutation | Không thay đổi cell tương ứng | Đường mapping có thể không đúng như bạn nghĩ |
| Field được gửi bằng `null` | Xóa/đánh dấu cell không còn giá trị | Sinh tombstone, có thể làm mất dữ liệu cũ |
| Field được gửi bằng `UNSET` (nếu đường binding hỗ trợ) | Không tác động lên cell đó | Không giống null, cần hiểu API và version driver |

Trong các thao tác Java Driver dùng prepared/bound statement, Cassandra Java Driver 4.x có phân biệt trạng thái **set**, **null** và **unset**. Spring Data repository áp dụng các cơ chế mapping riêng, nên cần xác minh statement phát sinh của phiên bản thực tế.

### 5.2. Tombstone không phải lỗi ngay lập tức, nhưng cần kiểm soát

Xóa cell, xóa row và hết hạn TTL trong Cassandra có thể tạo **tombstone**. Tombstone giúp replicas biết dữ liệu cũ không được tái xuất hiện trong quá trình đồng bộ. Nếu ứng dụng liên tục ghi null, xóa/reinsert hoặc đặt TTL không phù hợp, lượng tombstone có thể gây:

- Đọc chậm vì phải duyệt nhiều dấu xóa.
- Tăng chi phí compaction và repair.
- Tăng tải hệ thống khi partition lớn hoặc truy vấn quét nhiều row.
- Khó dự đoán tail latency và memory pressure.

Không nên giải quyết việc “tạo mới” bằng mô hình xóa row cũ rồi insert lại ở mỗi lần save; cách này có thêm mutation/tombstone và cũng không cung cấp semantics giao dịch mong muốn.

## 6. TTL: upsert có thể thay đổi thời điểm hết hạn

Cassandra hỗ trợ TTL (time-to-live) trên mutation/cell. Ví dụ:

~~~sql
INSERT INTO order_drafts_by_id (
    draft_id, customer_id, status
)
VALUES (
    33333333-3333-4333-8333-333333333333,
    22222222-2222-4222-8222-222222222222,
    'DRAFT'
)
USING TTL 3600;
~~~

Giả định bảng `order_drafts_by_id` đã được tạo với các cột tương ứng và `draft_id` là primary key. Dữ liệu được ghi có thời gian sống một giờ theo TTL được áp dụng. Sau khi hết hạn, giá trị có thể bị coi là không còn tồn tại và việc dọn dẹp vật lý diễn ra sau theo cơ chế Cassandra.

### 6.1. Retry không luôn giữ nguyên TTL

Một request đầu tiên đặt TTL 3.600 giây. Nếu client timeout nhưng server đã ghi, rồi client retry sau một phút bằng cùng câu lệnh `USING TTL 3600`, mutation mới có thể **làm mới thời điểm hết hạn** của các cell được ghi. Như vậy:

- Ghi hai lần cùng khóa, cùng giá trị không nhất thiết hoàn toàn vô tác dụng phụ về TTL.
- Retry có thể làm thay đổi thời gian lưu giữ thực tế.
- Cần chọn hợp đồng lưu dữ liệu: hết hạn sau lần tạo đầu, hay hết hạn sau lần cập nhật gần nhất?

Nếu nghiệp vụ yêu cầu **hết hạn tại thời điểm cố định**, hãy lưu thời gian hết hạn nghiệp vụ và thiết kế cách suy ra TTL/cơ chế kiểm tra phù hợp, thay vì mặc định retry với TTL cố định luôn idempotent.

### 6.2. TTL không phải “xóa tất cả read model”

Nếu cùng một đơn nằm ở ba bảng, đặt TTL ở một bảng không buộc hai bảng khác hết hạn cùng lúc. TTL và tombstone thuộc phạm vi dữ liệu được ghi. Các bảng denormalized cần chính sách vòng đời rõ ràng, nhất là khi một bảng giữ lịch sử lâu hơn bảng khác.

## 7. Chỉ tạo mới: INSERT IF NOT EXISTS

Khi nghiệp vụ yêu cầu **một ID chỉ được tạo một lần**, CQL hỗ trợ điều kiện:

~~~sql
INSERT INTO orders_by_id (
    order_id,
    customer_id,
    status,
    total_amount,
    revision
)
VALUES (?, ?, 'CREATED', ?, 1)
IF NOT EXISTS;
~~~

Cassandra thực thi điều kiện bằng **lightweight transaction (LWT)**. Đây là cơ chế so sánh-và-đặt (compare-and-set) với đồng thuận cho phạm vi được hỗ trợ, đắt hơn write thông thường.

Với Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public class CreateOrderWriter {

    private final CqlSession session;
    private final PreparedStatement createOnce;

    public CreateOrderWriter(CqlSession session) {
        this.session = session;
        this.createOnce = session.prepare(
            "INSERT INTO orders_by_id " +
            "(order_id, customer_id, status, total_amount, revision) " +
            "VALUES (?, ?, 'CREATED', ?, 1) IF NOT EXISTS");
    }

    public boolean create(
            UUID orderId,
            UUID customerId,
            BigDecimal amount) {

        BoundStatement statement =
            createOnce.bind(orderId, customerId, amount);

        ResultSet result = session.execute(statement);
        return result.wasApplied();
    }
}
~~~

Ý nghĩa:

- Kết quả `true`: điều kiện đã được thỏa và mutation được áp dụng.
- Kết quả `false`: điều kiện không thỏa tại thời điểm kiểm tra; row đã tồn tại, nên không ghi đè bằng nội dung mới.
- Timeout/lỗi khi chờ phản hồi: **chưa thể chắc chắn server đã áp dụng hay chưa**. Cần kiểm tra trạng thái theo khóa hoặc retry an toàn theo hợp đồng của lệnh tạo.
- Nếu hai request cùng tạo với cùng ID, LWT giúp tránh cả hai cùng nhận áp dụng thành công cho **cùng primary key**. Nó không tự bảo vệ ràng buộc duy nhất khác nằm ở bảng/partition riêng.

`ResultSet.wasApplied()` tương ứng với cột ảo `[applied]` mà CQL trả về cho conditional statements. Ứng dụng không được hiểu “session.execute không ném exception” là chắc chắn đã tạo mới; một câu `IF NOT EXISTS` hợp lệ có thể trả `[applied] = false`.

### 7.1. Nếu ID đã tồn tại nhưng payload khác nhau?

Giả sử request A tạo đơn có `amount = 100`, request B cùng `orderId` nhưng `amount = 200`. Khi B nhận `wasApplied() == false`, có ít nhất hai khả năng nghiệp vụ:

1. B là retry hợp lệ của cùng yêu cầu, payload giống dữ liệu đã lưu.
2. B cố dùng ID đã được chiếm cho một yêu cầu khác, payload khác.

Không mặc định cả hai là “thành công idempotent”. Nên đọc hoặc truy xuất một **business request ID / idempotency key** và so sánh định danh nghiệp vụ/payload theo quy tắc đã định. Nếu cùng ID nhưng khác nội dung, trả xung đột có ý nghĩa thay vì lặng lẽ ghi đè.

### 7.2. LWT không phải giao dịch toàn bộ luồng xử lý

Tạo row đơn hàng bằng `INSERT IF NOT EXISTS` chỉ bảo đảm điều kiện **ở row/partition được xét**. Nó không đồng thời bảo đảm:

- Gửi thông báo/email chính xác một lần.
- Cập nhật bảng `orders_by_customer_month` cùng lúc và có rollback.
- Trừ hàng tồn kho ở một partition khác một cách ACID với tạo đơn.
- Phát sự kiện ra broker đúng một lần trong mọi tình huống.

Đối với luồng nhiều bước, cần idempotency nghiệp vụ, cơ chế sự kiện bền vững, retry, outbox/đồng bộ hoặc đối soát tùy thiết kế. LWT chỉ là một công cụ trong tổng thể đó.

## 8. Chỉ cập nhật khi điều kiện đúng: UPDATE IF ...

Trạng thái đơn hàng có thể cần luồng chuyển:

~~~text
CREATED -> PAID -> SHIPPED -> COMPLETED
     \-> CANCELLED (nếu nghiệp vụ cho phép)
~~~

Một lệnh upsert vô điều kiện dễ tạo thay đổi không hợp lệ, ví dụ retry cũ ghi `CREATED` sau khi đã `PAID`. Dùng CAS:

~~~sql
UPDATE orders_by_id
SET status = 'PAID',
    revision = 2
WHERE order_id = ?
IF status = 'CREATED' AND revision = 1;
~~~

Trong cùng row, Cassandra kiểm tra điều kiện và áp dụng nếu thỏa theo cơ chế LWT. Khi không thỏa, kết quả chứa `[applied] = false`, có thể kèm giá trị hiện có tùy câu lệnh.

Ví dụ Java Driver:

~~~java
PreparedStatement payIfCreated = session.prepare(
    "UPDATE orders_by_id " +
    "SET status = 'PAID', revision = 2 " +
    "WHERE order_id = ? " +
    "IF status = 'CREATED' AND revision = 1");

boolean applied = session.execute(
    payIfCreated.bind(orderId)
).wasApplied();

if (!applied) {
    // Đọc trạng thái mới nhất và quyết định:
    // đã PAID bởi retry trước, đang CANCELLED,
    // hoặc trạng thái không phù hợp để chuyển.
}
~~~

**Đừng xử lý `applied = false` chỉ bằng cách lặp lại vô hạn.** Một client khác có thể đã chuyển trạng thái hợp lệ; ứng dụng phải trả kết quả hoặc thực hiện workflow tiếp theo theo quy tắc nghiệp vụ.

### 8.1. IF EXISTS không thay thế IF status = ...

~~~sql
UPDATE orders_by_id
SET status = 'PAID'
WHERE order_id = ?
IF EXISTS;
~~~

Lệnh này chỉ ngăn việc vô tình tạo row chưa tồn tại. Nó **không** ngăn chuyển từ `CANCELLED` sang `PAID` nếu row đã tồn tại. Khi cần xác nhận trạng thái cụ thể, dùng CAS so sánh cột trạng thái/revision hoặc cơ chế phối hợp khác.

### 8.2. Serial consistency của LWT khác consistency thông thường

Java Driver/Cassandra phân biệt:

- **Regular consistency level:** ví dụ `LOCAL_ONE`, `LOCAL_QUORUM` cho phần đọc/ghi thông thường.
- **Serial consistency level:** ví dụ `SERIAL` hoặc `LOCAL_SERIAL`, dùng cho pha điều phối của conditional mutation LWT.

Không gán `SERIAL` thay thế `LOCAL_QUORUM` cho mọi thao tác `INSERT` thông thường. Khi LWT chạy nhiều data center, phải hiểu phạm vi DC, khả năng chịu lỗi và yêu cầu consistency của nghiệp vụ. LWT có chi phí round-trip/latency cao hơn, vì vậy nên đặt trên những đường ghi cần điều kiện thực sự, không bật đại trà “cho an toàn”.

## 9. Retry, timeout và idempotency

Trong một hệ thống phân tán, client có thể nhận timeout dù mutation đã được một số replica hoặc quorum áp dụng. Tình huống cơ bản:

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant D as Cassandra Driver
    participant C as Cassandra Cluster

    API->>D: INSERT order O
    D->>C: Gửi mutation
    C-->>D: Ghi hoàn tất nhưng phản hồi bị mất
    D-->>API: Timeout / không rõ kết quả
    API->>D: Retry INSERT order O
    D->>C: Mutation tiếp theo
    C-->>D: Thành công
    D-->>API: Kết quả
~~~

Nếu cả hai request cùng primary key và cùng giá trị, upsert có thể làm cho **giá trị cuối** trùng với điều mong muốn. Nhưng không phải mọi thao tác Cassandra đều idempotent theo nghĩa nghiệp vụ:

| Kiểu thao tác | Retry an toàn đến đâu? |
| --- | --- |
| `INSERT` cùng khóa, cùng các cột và không TTL hoặc hiệu ứng ngoài | Thường gần với idempotent về giá trị cuối, nhưng vẫn có write timestamp và các tương tác đồng thời cần xét |
| `UPDATE ... SET status = 'PAID'` | Thường idempotent về giá trị status trong môi trường không có writer cạnh tranh, nhưng có thể ghi đè thay đổi mới hơn |
| `INSERT ... USING TTL 3600` | Retry có thể kéo dài thời điểm hết hạn |
| `UPDATE counter = counter + 1` | **Không idempotent**; retry có thể tăng hai lần |
| `UPDATE list_col = list_col + [...]` | Một số phép biến đổi list không idempotent; retry có thể lặp phần tử |
| `INSERT IF NOT EXISTS` | Dùng điều kiện giúp tránh tạo trùng row; timeout vẫn phải xác minh kết quả và phân biệt retry với xung đột |
| `UPDATE ... IF revision = n` | Phù hợp với điều phối theo revision, nhưng phải xử lý CAS thất bại và kết quả không rõ |

### 9.1. Idempotency của driver khác idempotency nghiệp vụ

Java Driver 4.x có flag `idempotent` cho statement, ảnh hưởng việc driver có thể retry hoặc speculative execute tùy chính sách. Đánh dấu một lệnh ghi là idempotent **không tự tạo idempotency**.

Ví dụ chỉ nên đánh dấu khi đã xác định rõ ngữ nghĩa:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement readById = SimpleStatement.builder(
        "SELECT order_id, status FROM orders_by_id WHERE order_id = ?")
    .addPositionalValue(orderId)
    .setIdempotent(true)
    .build();
~~~

Đây là truy vấn đọc theo khóa; việc thử lại thường không tạo hiệu ứng ghi. Ngược lại, không bật `setIdempotent(true)` hàng loạt cho counter, thao tác thêm list, chuyển trạng thái cạnh tranh hoặc write có hiệu ứng ngoài.

### 9.2. Thiết kế create request có idempotency key

Giả sử API nhận:

~~~json
{
  "requestId": "req-9b1d",
  "orderId": "11111111-1111-4111-8111-111111111111",
  "customerId": "22222222-2222-4222-8222-222222222222",
  "totalAmount": "150000.00"
}
~~~

Hợp đồng đề xuất:

1. Client gửi một `requestId` ổn định khi retry cùng lệnh.
2. Server định danh request này với `orderId`/payload và quyết định cách ghi có điều kiện hoặc lưu trạng thái xử lý.
3. Nếu đã xử lý cùng request và payload, trả lại kết quả đã biết.
4. Nếu cùng `requestId` nhưng payload khác, trả xung đột.
5. Nếu trạng thái “không rõ” vì timeout, tra cứu trạng thái đã được ghi/điều phối trước khi retry hiệu ứng ngoài.
6. Duy trì quy trình đối soát khi ghi Cassandra thành công nhưng bước publish event/đồng bộ read model gặp lỗi.

Không có một annotation Spring Data repository nào tự cung cấp đầy đủ hợp đồng idempotency cho toàn bộ API.

## 10. Save và primary key: đổi khóa nghĩa là row khác

Giả sử hệ thống còn cần truy vấn “đơn mới nhất của khách trong tháng”:

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Một entity cho bảng thứ hai có khóa ghép:

~~~java
@PrimaryKeyClass
public class OrderByCustomerMonthKey implements Serializable {

    @PrimaryKeyColumn(
        name = "customer_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "month_bucket",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private String monthBucket;

    @PrimaryKeyColumn(
        name = "created_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING)
    private UUID orderId;

    // Constructor, getters, setters, equals(), hashCode()...
}

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {

    @PrimaryKey
    private OrderByCustomerMonthKey key;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    // Constructor, getters, setters...
}
~~~

Đoạn ví dụ lược bỏ imports/boilerplate, class khóa cần `equals()`/`hashCode()` đúng theo tất cả thành phần khóa.

### 10.1. Đổi khóa không phải sửa field bình thường

Giả sử `monthBucket` đổi từ `"2026-10"` sang `"2026-11"` rồi bạn gọi `save` một entity có key mới. Cassandra ghi vào **partition mới**. Row trong partition tháng 10 không tự bị xóa.

Cũng tương tự nếu `createdAt` là clustering key và bạn “chỉnh lại” timestamp: row ở địa chỉ khóa cũ có thể vẫn tồn tại.

Quy tắc thiết kế:

- Giữ các trường dùng làm partition/clustering key ổn định sau khi tạo.
- Nếu cần chuyển địa chỉ, phải biết khóa cũ và khóa mới, xử lý ghi mới/xóa cũ, retry và tombstone có kiểm soát.
- Với bảng theo truy vấn, sự chuyển khóa còn phải được đồng bộ đến tất cả read model liên quan.
- Không dùng `repository.save` và kỳ vọng JPA sẽ tự di chuyển row khóa cũ.

### 10.2. Một repository không cập nhật nhiều bảng

~~~java
orderByIdRepository.save(orderById);
~~~

không tự gọi:

~~~java
orderByCustomerMonthRepository.save(orderByCustomerMonth);
~~~

Spring Data Cassandra không tự duy trì foreign key/quan hệ giữa hai bảng như JPA. Nếu cùng một đơn được denormalize sang nhiều bảng, ứng dụng cần đường ghi hoặc projector để cập nhật chúng.

Kết quả thực tế có thể là:

~~~text
orders_by_id:              status = PAID
orders_by_customer_month:  status = CREATED  (view đang trễ)
~~~

Đây là **hai biểu diễn nghiệp vụ** khác nhau, không nhất thiết do các replica của một bảng thiếu consistency. `LOCAL_QUORUM` không buộc hai bảng ứng dụng đồng bộ.

## 11. Batch có giúp save nhiều bảng như transaction không?

Một số người cố gói nhiều lệnh thành batch:

~~~sql
BEGIN LOGGED BATCH
    INSERT INTO orders_by_id (
        order_id, customer_id, status, revision
    ) VALUES (?, ?, 'CREATED', 1);

    INSERT INTO orders_by_customer_month (
        customer_id, month_bucket, created_at,
        order_id, status
    ) VALUES (?, ?, ?, ?, 'CREATED');
APPLY BATCH;
~~~

CQL batch có **phạm vi bảo đảm và chi phí riêng**. Logged batch nhằm hỗ trợ atomic application theo cơ chế eventual của Cassandra cho các mutation trong batch, nhưng:

- Không cung cấp isolation kiểu transaction RDBMS giữa các reader.
- Không thể tự động rollback nghiệp vụ khi có bước xử lý ngoài Cassandra.
- Cross-partition batch có thể làm tăng độ trễ và tạo thêm tài nguyên điều phối.
- Không bảo đảm toàn bộ vòng đời đồng bộ read models, replay và thứ tự event.
- Không nên gói hàng nghìn partition vào một batch để kỳ vọng “bulk insert nhanh” như SQL.

Nếu nhiều mutation thuộc **cùng partition**, một batch nhỏ có thể phù hợp một số trường hợp nhưng vẫn cần đánh giá. Với nhiều bảng theo truy vấn, chiến lược event-driven có idempotent projector, cơ chế phục hồi và đối soát thường cho khả năng mở rộng/quan sát tốt hơn khi khối lượng lớn. Lựa chọn phụ thuộc yêu cầu consistency và topology thật.

## 12. Consistency level và durability của một upsert

Cassandra có replication factor (RF) tại keyspace và consistency level (CL) cho request. Chúng quyết định số replica được ghi/đọc để thao tác thành công, **không thay thế cơ chế LWT**.

Ví dụ trong một data center có RF = 3:

| CL | Yêu cầu phản hồi tiêu biểu | Ý nghĩa vận hành |
| --- | --- | --- |
| `LOCAL_ONE` | Một replica trong DC cục bộ | Latency/yêu cầu replica thấp hơn, có thể đọc bản sao chưa cập nhật |
| `LOCAL_QUORUM` | Hai replica trong DC cục bộ | Có sự giao nhau khi đọc/ghi quorum phù hợp, đổi lại độ trễ/khả năng sẵn sàng |
| `ALL` | Tất cả ba replica | Nhạy với lỗi một replica |

Một `INSERT` thành công tại `LOCAL_QUORUM` có nghĩa đã nhận đủ xác nhận cho mức CL yêu cầu, **không** có nghĩa “khóa này chỉ được phép tạo một lần”. Một `UPDATE` có CL cao vẫn có thể ghi đè status mới hơn về mặt nghiệp vụ nếu mutation có timestamp thắng.

Với multi-DC và `LOCAL_QUORUM`, thao tác tại DC A không tự bảo đảm mọi replica của DC B đã áp dụng mutation ngay khi client nhận thành công. Khi thiết kế read-after-write xuyên DC, cần xác định hợp đồng rõ ràng và kiểm tra topology/consistency.

### 12.1. Timeout không xác định chắc kết quả

Driver hoặc coordinator timeout không nhất thiết đồng nghĩa thao tác không được áp dụng. Có thể một số replica đã nhận mutation, hoặc coordinator đã đạt đủ replica nhưng phản hồi về client bị mất. Phần quan trọng là **trạng thái xác nhận không rõ**, nên workflow cần biết cách xử lý retry, kiểm tra theo khóa và tránh tạo thêm hiệu ứng nghiệp vụ.

Nếu dùng `IF NOT EXISTS` và nhận timeout, không thể lập tức nói “đơn chưa được tạo”. Nếu retry nhận `[applied] = false`, có thể request đầu tiên đã tạo row. Cần so sánh requestId/payload để nhận ra đây là cùng thao tác hay xung đột thật.

## 13. saveAll, hiệu năng và giới hạn tài nguyên

Repository có phương thức `saveAll(…)` cho nhiều entity, nhưng đừng coi nó đồng nghĩa:

- Một transaction ACID trên nhiều entity.
- Một batch CQL tối ưu cho mọi partition.
- Một đảm bảo “all-or-nothing” ngay lập tức giữa nhiều bảng.
- Một giải pháp bulk insert vô hạn mà không cần điều tiết tốc độ.

Hành vi nội bộ của `saveAll` và cách các thao tác được thực thi phải được kiểm tra theo **phiên bản Spring Data Cassandra**. Về mặt hệ thống, mỗi entity có partition key riêng và mutation có chi phí kết nối/replication, nên cần giới hạn throughput, quan sát timeout và tránh bão retry.

### 13.1. Tối ưu một workload ghi theo bảng truy vấn

Giả sử mỗi giây phải ghi hàng nghìn sự kiện đơn hàng:

1. **Kiểm tra access pattern.** `orders_by_customer_month` cần partition key theo khách/bucket và clustering theo thời gian; tránh một partition cho toàn bộ hệ thống.
2. **Giữ mutation nhỏ.** Không nhét lịch sử vô hạn vào `list` lớn; mỗi sự kiện nên là row theo khóa phù hợp.
3. **Dùng prepared statements cho CQL lặp lại.** Giảm công việc parse/bind, tránh ghép chuỗi tham số thủ công.
4. **Giới hạn đồng thời.** Quá nhiều request in-flight có thể gây nghẽn driver, coordinator, CPU, đĩa hoặc compaction.
5. **Đo p95/p99 và lỗi.** Quan sát latency, timeout, unavailable, retry, tombstone, partition size và tải cụm.
6. **Đánh giá CL và RF theo SLA.** Tăng CL có thể cải thiện bảo đảm xác nhận nhưng tăng đòi hỏi về replica.
7. **Chỉ dùng LWT nơi cần.** Nếu tất cả mutation đều đi qua CAS không cần thiết, contention và latency có thể tăng đáng kể.
8. **Đối soát read model.** Nếu ghi vào nhiều bảng hoặc dùng projector, theo dõi độ trễ đồng bộ và các row thiếu/sai phiên bản.

### 13.2. Ghi nóng trên cùng partition

Nếu mọi request ghi vào một partition lớn, có thể tạo **hot partition**, kể cả khi cluster có rất nhiều node. Tăng pool driver không giúp phân phối thêm dữ liệu nếu partition key cố định. Cần bucket/shard hợp lý, cân bằng giữa phân tán tải và chi phí đọc nhiều partition.

### 13.3. Paging trong luồng đọc sau save

Sau khi ghi, màn hình có thể cần “20 đơn mới nhất”:

~~~sql
SELECT order_id, created_at, status
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Câu này tận dụng partition/clustering nếu schema phù hợp. `LIMIT` giới hạn hàng, trong khi Java Driver paging state/page size phục vụ việc fetch kết quả theo trang. Không dùng offset SQL tùy ý khi Cassandra không thiết kế cho kiểu phân trang đó. Nếu view được cập nhật bất đồng bộ, danh sách có thể trễ so với chi tiết đơn ngay sau save.

## 14. Các trường hợp thực tế cần phân biệt

### 14.1. “Tạo đơn một lần”

Yêu cầu: một `orderId` chỉ được tạo một lần, retry cùng yêu cầu phải an toàn.

Hướng xử lý:

- Lựa chọn khóa/định danh nghiệp vụ ổn định.
- Dùng `INSERT ... IF NOT EXISTS` nếu cần đảm bảo create-only trên đúng row.
- Gắn requestId/idempotency key với payload.
- Kiểm tra `[applied]`, và khi timeout xác minh trạng thái trước khi tạo hiệu ứng tiếp.
- Gửi sự kiện/đồng bộ read model qua cơ chế có replay/đối soát.

### 14.2. “Ghi snapshot mới nhất”

Yêu cầu: ingest snapshot trạng thái từ một nguồn tin cậy, các bản lặp giống nhau có thể được nhận nhiều lần.

Hướng xử lý:

- Upsert theo một primary key ổn định thường phù hợp.
- Nếu sự kiện có version, chỉ nhận snapshot mới hơn bằng CAS/điều phối phù hợp.
- Không để retry cũ có timestamp mới ghi đè snapshot mới.
- Nếu nguồn có nhiều writer, định nghĩa quy tắc conflict rõ ràng thay vì dựa vào arrival order.

### 14.3. “Chỉnh một trường”

Yêu cầu: thay `status` nhưng giữ nguyên `amount`, `customerId`.

Hướng xử lý:

~~~sql
UPDATE orders_by_id
SET status = ?
WHERE order_id = ?;
~~~

Nếu chuyển trạng thái phải hợp lệ, thêm điều kiện `IF status = ?`. Không tạo một entity chỉ có `orderId` và `status` rồi giả định `save` tự patch mà không ảnh hưởng field khác.

### 14.4. “Ghi nhật ký sự kiện”

Yêu cầu: thêm nhiều event theo người dùng và thời gian, không được ghi đè nhau.

Hướng xử lý: dùng bảng có partition theo người dùng/bucket và clustering key định danh event. Nếu hai event dùng cùng primary key, upsert có thể làm chúng va chạm. Chọn key đủ phân biệt, ví dụ timestamp kết hợp `event_id` ổn định.

### 14.5. “Đếm số lần xem”

Yêu cầu: tăng lượt xem một đơn vị cho mỗi event.

Không dùng upsert set giá trị cũ + 1 sau SELECT như phép tăng atomic. CQL counter có cơ chế riêng:

~~~sql
CREATE TABLE views_by_page (
    page_id uuid PRIMARY KEY,
    views counter
);

UPDATE views_by_page
SET views = views + 1
WHERE page_id = ?;
~~~

Counter update **không idempotent** khi retry. Nếu cần “mỗi event chỉ được đếm một lần”, cần cơ chế deduplication hoặc tổng hợp từ event bền vững; không chỉ dựa vào `save` hay retry của driver.

## 15. Kiểm thử thực hành bằng CQL

Môi trường test có thể dùng keyspace riêng, RF/CL phù hợp topology test. Các lệnh dưới đây minh họa hành vi; không chạy trực tiếp trên dữ liệu production.

### 15.1. Kiểm chứng INSERT cùng khóa

~~~sql
CREATE TABLE IF NOT EXISTS upsert_lab (
    id uuid PRIMARY KEY,
    label text,
    counter_value int,
    updated_at timestamp
);

INSERT INTO upsert_lab (id, label, counter_value)
VALUES (
    44444444-4444-4444-8444-444444444444,
    'A',
    10
);

-- Cùng khóa, chỉ gửi label:
INSERT INTO upsert_lab (id, label)
VALUES (
    44444444-4444-4444-8444-444444444444,
    'B'
);

SELECT * FROM upsert_lab
WHERE id = 44444444-4444-4444-8444-444444444444;
~~~

Kỳ vọng: row có `label = 'B'` và `counter_value = 10` nếu không có mutation khác cạnh tranh hoặc TTL/delete xen vào. `counter_value` chỉ là tên cột `int` thử nghiệm, không phải kiểu CQL `counter`.

### 15.2. Kiểm chứng UPDATE trên khóa chưa có

~~~sql
UPDATE upsert_lab
SET label = 'CREATED_BY_UPDATE'
WHERE id = 55555555-5555-4555-8555-555555555555;

SELECT * FROM upsert_lab
WHERE id = 55555555-5555-4555-8555-555555555555;
~~~

Kỳ vọng: có row/cell với label mới tại ID chưa tồn tại trước đó. Đây là minh chứng `UPDATE` không tự yêu cầu row hiện hữu.

### 15.3. Kiểm chứng IF NOT EXISTS

~~~sql
INSERT INTO upsert_lab (id, label)
VALUES (
    66666666-6666-4666-8666-666666666666,
    'FIRST'
)
IF NOT EXISTS;

INSERT INTO upsert_lab (id, label)
VALUES (
    66666666-6666-4666-8666-666666666666,
    'SECOND'
)
IF NOT EXISTS;

SELECT * FROM upsert_lab
WHERE id = 66666666-6666-4666-8666-666666666666;
~~~

Kỳ vọng: lệnh đầu có `[applied] = true`, lệnh sau có `[applied] = false`, label vẫn là `FIRST` nếu không có mutation ngoài kịch bản.

### 15.4. Kiểm chứng IF EXISTS và IF theo giá trị

~~~sql
UPDATE upsert_lab
SET label = 'SHOULD_NOT_APPLY'
WHERE id = 77777777-7777-4777-8777-777777777777
IF EXISTS;

UPDATE upsert_lab
SET label = 'FINAL'
WHERE id = 66666666-6666-4666-8666-666666666666
IF label = 'FIRST';
~~~

Kỳ vọng: lệnh `IF EXISTS` với ID chưa có trả không áp dụng; lệnh `IF label = 'FIRST'` với ID trước đó có thể được áp dụng, chuyển thành `FINAL`. Nếu một writer khác đã sửa label, điều kiện có thể không thỏa.

### 15.5. Kiểm chứng xóa/tombstone

~~~sql
DELETE label FROM upsert_lab
WHERE id = 66666666-6666-4666-8666-666666666666;

SELECT * FROM upsert_lab
WHERE id = 66666666-6666-4666-8666-666666666666;
~~~

Xóa một cell làm nó không còn giá trị quan sát được trong row theo điều kiện thông thường. Cassandra quản lý tombstone để tránh dữ liệu cũ tái xuất hiện từ replica còn giữ giá trị cũ. Không suy diễn rằng bản ghi được xóa vật lý ngay lập tức hoặc `SELECT` sẽ luôn trả về số hàng giống nhau sau thao tác này khi các cột khác vẫn tồn tại.

## 16. Bài thực hành Spring Data Cassandra: chọn đúng thao tác

Một nhóm xây dựng dịch vụ đơn hàng với các API:

- `POST /orders`: tạo đơn mới, chống client retry tạo trùng.
- `PATCH /orders/{id}/status`: chuyển trạng thái theo quy tắc.
- `GET /orders/{id}`: đọc nhanh theo ID.
- `GET /customers/{id}/orders`: hiển thị đơn mới nhất theo tháng.

Bảng `orders_by_id` và `orders_by_customer_month` được thiết kế như ví dụ ở trên.

### 16.1. Bước 1 — Xác định nguồn sự thật

Định nghĩa `orders_by_id` là nguồn trạng thái chính cho thao tác đơn; các bảng danh sách là read model. Tạo đơn bằng một thao tác có điều kiện trên `order_id` nếu ID cần duy nhất.

Dòng lệnh tạo có thể dùng adapter `CreateOrderWriter` với CQL `INSERT ... IF NOT EXISTS` như phần 7. Khi thành công, trả snapshot đã tạo hoặc ID cho client. Khi nhận `[applied] = false`, kiểm tra requestId/payload và trả idempotent success hoặc conflict phù hợp.

### 16.2. Bước 2 — Chuyển trạng thái có điều kiện

Không viết:

~~~java
OrderById order = repository.findById(orderId).orElseThrow();
order.setStatus("PAID");
repository.save(order);
~~~

như một **cam kết CAS**, vì có khoảng trống giữa đọc và ghi. Hai request có thể cùng đọc `CREATED` rồi ghi hai trạng thái không tương thích.

Thay vào đó dùng:

~~~sql
UPDATE orders_by_id
SET status = 'PAID',
    revision = 2
WHERE order_id = ?
IF status = 'CREATED' AND revision = 1;
~~~

Khi `[applied] = false`, xử lý dựa trên trạng thái hiện có, không retry vô hạn. Nếu nhiều giai đoạn revision, sử dụng giá trị revision thực tế của request và đảm bảo điều kiện cập nhật đúng.

### 16.3. Bước 3 — Đồng bộ danh sách đơn

Phát thay đổi trạng thái từ nguồn có cơ chế bền vững/replay phù hợp. Một worker cập nhật `orders_by_customer_month` theo khóa đầy đủ. Vì đây là bảng denormalized, phải ngăn event cũ ghi đè state mới, bằng revision/CAS/điều phối theo khóa và cơ chế đối soát.

Không cho rằng một lần `repository.save(orderById)` có thể tự cập nhật bảng danh sách. Cũng không dựa vào replication factor để đồng bộ hai bảng nghiệp vụ.

### 16.4. Bước 4 — Xử lý timeout và retry

Giả sử API timeout khi tạo đơn. Trước khi retry tác dụng ngoài, tra cứu theo `order_id`/`requestId` và xác định:

- Đã tạo bởi đúng request hay chưa?
- Dữ liệu đã tạo có khớp payload của request?
- Sự kiện/read model đã phát hoặc có cơ chế phát lại chưa?
- Cần trả kết quả gì nếu request khác đã dùng cùng ID?

Kiểm tra cùng một request gửi hai lần; hai request khác payload cùng ID; hai cập nhật trạng thái cạnh tranh; sự kiện revision 7 đến sau revision 8; timeout trước/sau khi server áp dụng.

### 16.5. Bước 5 — Đo đúng các chỉ số

| Chỉ số | Vì sao hữu ích |
| --- | --- |
| Số lần `[applied] = false` ở create-only | Phát hiện retry, ID conflict hoặc idempotency key được dùng lại |
| Tỷ lệ CAS thất bại theo trạng thái/revision | Phát hiện contention và lệnh chuyển trạng thái không hợp lệ |
| Request timeout, unavailable, retries | Phân biệt vấn đề đường mạng/quorum với lỗi nghiệp vụ |
| p95/p99 latency của ghi thường và LWT | Cân đối chính xác và chi phí đồng thuận |
| Projection lag, số read model sai revision | Kiểm tra chất lượng đồng bộ giữa các bảng |
| Partition size, tombstone, compaction, read latency | Phát hiện hệ quả schema, null/TTL và quá tải dữ liệu |
| Số create request có kết quả không rõ | Kiểm chứng quy trình retry và khả năng đối soát |

## 17. Sai lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`repository.save` sẽ lỗi nếu ID đã tồn tại.” | Ghi Cassandra vô điều kiện có tính upsert; muốn create-only phải dùng điều kiện và kiểm tra kết quả |
| “`insert` chỉ tạo, `update` chỉ sửa, như SQL quan hệ.” | CQL `INSERT` và `UPDATE` đều có thể upsert |
| “`existsById` rồi `save` là đủ để tạo duy nhất.” | Đây là hai bước có race condition; cần LWT/coordination nếu yêu cầu |
| “`save` chỉ sửa field tôi vừa đặt.” | Phạm vi mutation phụ thuộc mapping và statement; PATCH cần câu cập nhật tường minh |
| “`null` trong entity chắc chắn được bỏ qua.” | Có thể được bind thành null/tombstone tùy đường ghi; phải xác minh |
| “Ghi cùng giá trị lần nữa luôn hoàn toàn vô tác dụng phụ.” | Write timestamp, TTL và tương tác đồng thời có thể khác nhau |
| “Cứ tăng `revision` rồi `save` là chống được retry cũ.” | Cassandra không tự so sánh business revision nếu không có điều kiện |
| “`LOCAL_QUORUM` tự chống ghi đè.” | CL là mức phản hồi replica, không phải uniqueness/business CAS |
| “Logged batch có rollback/isolation đa bảng như JPA.” | Batch có giới hạn bảo đảm/chi phí; không thay thế transaction nghiệp vụ đa bảng |
| “Timeout nghĩa là server chưa ghi.” | Kết quả có thể không rõ; cần kiểm tra hoặc retry idempotent |
| “`saveAll` là một transaction hoặc luôn nhanh hơn nhiều `save`.” | Phụ thuộc implementation/version và workload; không có cam kết ACID |
| “Đổi primary key rồi `save` sẽ xóa row cũ.” | Ghi sang địa chỉ khóa mới; row cũ cần xử lý riêng |
| “Replication sẽ tự đồng bộ `orders_by_id` và `orders_by_customer_month`.” | Replica vật lý khác với hai read model do ứng dụng thiết kế |
| “Dùng counter với `save` như số nguyên thường.” | Counter có lệnh cập nhật riêng và không idempotent khi retry |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao chạy hai lần `INSERT` với cùng primary key trong Cassandra không tự động báo duplicate key?

*Gợi ý:* `INSERT` thông thường là upsert, xung đột được xử lý theo cell/write timestamp; chỉ khi cần create-only mới dùng điều kiện `IF NOT EXISTS`.

**Câu 2.** `CassandraTemplate.insert(entity)` có tự bảo đảm chỉ tạo mới nếu khóa chưa tồn tại không?

*Gợi ý:* Tên API biểu đạt thao tác INSERT, nhưng INSERT CQL vô điều kiện vẫn là upsert. Cần điều kiện để chống tạo trùng.

**Câu 3.** Tại sao không nên triển khai “chỉ tạo một lần” bằng `existsById` rồi `save`?

*Gợi ý:* Hai client có thể cùng thấy chưa tồn tại và cùng ghi, vì không có một thao tác CAS chung.

**Câu 4.** Sau khi `repository.save(order)` timeout, có thể kết luận đơn chưa tồn tại không?

*Gợi ý:* Không; request có thể đã được ghi và phản hồi bị mất. Cần xác minh theo khóa/idempotency key.

**Câu 5.** Nếu `revision=8` đã ghi thành công, tại sao retry của revision 7 có thể làm lùi dữ liệu?

*Gợi ý:* Business revision không tự tham gia conflict resolution; cell write timestamp mới có thể thắng.

**Câu 6.** Vì sao ghi `null` có thể ảnh hưởng hiệu năng Cassandra khi lặp lại nhiều lần?

*Gợi ý:* Mutation xóa tạo tombstone; nhiều tombstone làm tăng chi phí đọc/compaction.

**Câu 7.** Khi nào `IF EXISTS` đủ và khi nào phải có `IF status = ...`?

*Gợi ý:* `IF EXISTS` chỉ kiểm tra row có tồn tại; chuyển trạng thái nghiệp vụ cần so sánh giá trị.

**Câu 8.** Một đơn xuất hiện ở hai bảng khác nhau. `save` một repository có bảo đảm bảng còn lại đồng bộ ngay không?

*Gợi ý:* Không. Đây là hai biểu diễn nghiệp vụ; cần đường đồng bộ/đối soát riêng.

**Câu 9.** Vì sao đổi `month_bucket` trong khóa ghép rồi `save` có thể để lại row cũ?

*Gợi ý:* Khóa mới xác định partition khác; Cassandra không tự di chuyển/xóa row ở khóa cũ.

**Câu 10.** Vì sao retry `UPDATE views = views + 1` nguy hiểm?

*Gợi ý:* Counter update không idempotent; một event có thể bị tính hai lần.

**Câu 11.** Nếu ghi `INSERT ... USING TTL 3600` hai lần cách nhau một phút, điều gì có thể khác so với ghi một lần?

*Gợi ý:* Retry có thể làm mới thời điểm hết hạn của cell được ghi.

**Câu 12.** `[applied] = false` khi `INSERT IF NOT EXISTS` có phải lúc nào là lỗi hệ thống không?

*Gợi ý:* Không. Đây là kết quả điều kiện không thỏa; có thể là retry cùng request hoặc xung đột ID, phải phân biệt theo nghiệp vụ.

## Kết luận

`save` và `insert` là các API thuận tiện của Spring Data Cassandra, nhưng tính đúng đắn phụ thuộc vào ngữ nghĩa của Apache Cassandra: **`INSERT` và `UPDATE` thông thường đều là upsert**. Không được suy từ tên phương thức rằng Cassandra luôn tạo mới, cấm ID trùng hoặc có giao dịch như JPA. Các mutation được xử lý theo primary key, cell và write timestamp; `null`, TTL và retry có thể tạo hiệu ứng quan trọng lên dữ liệu.

Với **SPRING_DATA_CASSANDRA**, hãy dùng `repository.save` cho đường ghi snapshot phù hợp, `CassandraTemplate` hoặc CQL tường minh khi cần chọn cột/điều kiện, `IF NOT EXISTS` cho create-only và `IF ...` cho chuyển trạng thái có điều kiện. Luôn xử lý timeout không rõ kết quả, idempotency, business revision, partition key ổn định, paging và việc đồng bộ read model giữa các bảng. Khi kiểm chứng đúng các ranh giới này, ứng dụng sẽ tận dụng được mô hình dữ liệu phân tán của Cassandra mà vẫn giữ được tính nhất quán nghiệp vụ cần thiết.
