# Cập nhật bảng phi chuẩn hóa và các ràng buộc cần kiểm chứng

## 1. Một đơn hàng, hai cách truy vấn, hai bảng

Trong **Apache Cassandra**, mô hình dữ liệu thường được thiết kế **theo truy vấn**, không tổ chức chỉ để chuẩn hóa rồi dùng phép `JOIN` cho mọi màn hình. Giả sử ứng dụng Spring Boot cung cấp:

- `GET /orders/{orderId}`: tìm chi tiết đơn hàng theo ID.
- `GET /customers/{customerId}/orders?day=...`: liệt kê đơn hàng của khách trong một ngày, mới nhất trước.

Một thiết kế phổ biến có **hai bảng phi chuẩn hóa**:

~~~text
orders_by_id                   -> lookup theo order_id
orders_by_customer_day         -> danh sách theo customer_id + order_day
~~~

Mỗi khi tạo đơn hoặc chuyển trạng thái, ứng dụng phải tính đến việc cập nhật **cả hai bảng**. Nếu chỉ dùng hai lời gọi `repository.save(...)`, lời gọi thứ nhất có thể thành công còn lời gọi thứ hai thất bại. Người học có thể nghĩ gói cả hai vào một `BEGIN BATCH ... APPLY BATCH` sẽ tạo giao dịch ACID như cơ sở dữ liệu quan hệ. **Đó là cách hiểu sai về Cassandra batch**.

Logged batch có **batchlog** để hỗ trợ các mutation trong batch được thực thi cuối cùng khi có lỗi và hệ thống phục hồi. Tuy nhiên nó **không cung cấp snapshot nguyên tử/cách ly giao dịch xuyên nhiều partition**. Hai API đọc ở hai bảng có thể nhìn thấy trạng thái khác nhau trong một khoảng thời gian, và timeout vẫn đặt client vào tình huống cần đối soát.

Bài thuộc chương **Batch** của module **SPRING_DATA_CASSANDRA**, liên kết kiến thức entity mapping, repository, `CassandraTemplate`, Java driver/CQL, partition key, tính nhất quán, paging và hiệu năng phân tán.

**Mục tiêu học tập:**

1. Tổ chức hai bảng phục vụ hai access pattern, và xác định **nguồn sự thật**.
2. Phân biệt logged, unlogged và counter batch.
3. Giải thích **batchlog, tính nguyên tử cuối cùng, giới hạn isolation** và những tình huống nhìn thấy dữ liệu lệch.
4. Ghi batch với CQL và Java driver 4.x sử dụng prepared statements.
5. Biết khi nào dùng **LWT/CAS** thay vì tưởng rằng batch tự bảo vệ version/điều kiện nghiệp vụ.
6. Kiểm chứng full primary key, TTL, timestamp, idempotency, retry, consistency, size và workflow đối soát.

## 2. Schema mẫu phục vụ từng đường truy vấn

### 2.1. Bảng nguồn: orders_by_id

~~~sql
-- app_ks phải được tạo trước với replication strategy thích hợp.
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    order_day date,
    created_at timestamp,
    state text,
    version bigint,
    updated_at timestamp
);
~~~

Query:

~~~sql
SELECT order_id, customer_id, order_day, created_at,
       state, version, updated_at
FROM app_ks.orders_by_id
WHERE order_id = ?;
~~~

### 2.2. Bảng đọc: orders_by_customer_day

~~~sql
CREATE TABLE app_ks.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    state text,
    version bigint,
    updated_at timestamp,
    PRIMARY KEY (
        (customer_id, order_day),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Query:

~~~sql
SELECT order_id, created_at, state, version
FROM app_ks.orders_by_customer_day
WHERE customer_id = ? AND order_day = ?
LIMIT 20;
~~~

| Thuộc tính | Bảng theo ID | Bảng danh sách |
| --- | --- | --- |
| `order_id` | Primary key | Clustering column thứ hai |
| `customer_id` | Cột dữ liệu | Thành phần partition key |
| `order_day` | Cột dữ liệu | Thành phần partition key |
| `created_at` | Cột dữ liệu | Clustering column thứ nhất |
| `state` | Giá trị nghiệp vụ | Bản sao cho màn hình danh sách |
| `version` | Phiên bản nghiệp vụ | Phiên bản giúp kiểm tra projection |
| `updated_at` | Thời điểm cập nhật | Thời điểm cho phép đối chiếu |

Ở bảng danh sách, `(customer_id, order_day)` là **partition key tổng hợp**; hàng trong partition được sắp bằng `(created_at DESC, order_id ASC)`. `order_id` giúp phân biệt hai đơn có cùng thời điểm tạo.

### 2.3. Nguồn sự thật phải được xác định rõ

Trong ví dụ này, giả sử **`orders_by_id` là nguồn sự thật** của trạng thái đơn, còn `orders_by_customer_day` là **read model** có thể tái tạo/đồng bộ lại.

Hệ quả:

- Trạng thái có được chuyển từ `CREATED` sang `PAID` hay không phải được quyết định ở **nguồn sự thật**.
- Bảng danh sách có thể **trễ tạm thời**, cần theo dõi và đối soát.
- Không được lấy một bản sao cũ từ bảng danh sách ghi ngược vào bảng ID mà không có kiểm tra phiên bản.
- Phải giữ `customer_id`, `order_day` và `created_at` đã commit để tìm đúng hàng trong read model.

Nếu chọn event log làm nguồn sự thật, hợp đồng commit lại khác. Không được vừa xem hai bảng là hai nguồn sự thật độc lập, vừa kỳ vọng batch tự giải quyết mọi bất đồng.

## 3. Cùng order ID không có nghĩa cùng partition trên hai bảng

~~~mermaid
flowchart LR
    A[OrderCreated command] --> B[orders_by_id: partition key order_id]
    A --> C[orders_by_customer_day: partition key customer_id + day]
    B --> D[Nhóm replica của bảng ID]
    C --> E[Nhóm replica của bảng danh sách]
    D -. Có thể khác nhau .- E
~~~

Hai bảng có **hai không gian partition khác nhau**, dù đều chứa cùng `order_id`. Một batch ghi hàng theo ID và hàng theo customer/day là **multi-table/multi-partition workload**. Không được suy luận những bảo đảm chỉ đúng trong **một partition thuộc một bảng** cũng áp dụng cho hai bảng này.

Những vấn đề cần xem lại mỗi khi thiết kế batch:

1. Mỗi statement thật sự tác động đến **partition nào**?
2. Cần atomicity **khi khôi phục mutation** hay cần **các reader thấy snapshot đồng thời**?
3. Có yêu cầu **unique ID/optimistic locking** hay không?
4. Read model có thể trễ bao lâu trước khi vi phạm SLA?
5. Nếu một request timeout, cách phân biệt **đã commit**, **chưa commit** và **chưa rõ** là gì?

## 4. Ba dạng CQL batch

Cassandra batch gom những thao tác ghi `INSERT`, `UPDATE` và `DELETE`. Nó **không gom nhiều SELECT để tạo snapshot giao dịch**, không tự hỗ trợ phép JOIN hay rollback kiểu SQL quan hệ.

| Kiểu batch | Cú pháp | Mục tiêu | Cảnh báo |
| --- | --- | --- | --- |
| **Logged** | `BEGIN BATCH` | Batchlog hỗ trợ mutation được replay sau sự cố theo cơ chế Cassandra | Không có multi-partition isolation |
| **Unlogged** | `BEGIN UNLOGGED BATCH` | Gom thao tác đã đánh giá phạm vi, thường hữu ích với một partition | Không có batchlog để khôi phục cả bộ multi-partition mutations |
| **Counter** | `BEGIN COUNTER BATCH` | Các câu counter hợp lệ | Không trộn với regular writes; retry increment có thể cộng lặp |

**Logged batch** thường được biểu diễn bằng `BEGIN BATCH`: logged là **mặc định**. Không tự thêm từ khóa `LOGGED` vào cú pháp nếu phiên bản CQL đang dùng không định nghĩa từ khóa đó.

### 4.1. BATCH không phải cách tăng throughput mặc định

Nếu job cần ghi 100.000 hàng ở 100.000 partition, gói tất cả vào một batch lớn không có nghĩa Cassandra xử lý nhanh hơn. Batch multi-partition còn có thể:

- Tăng chi phí mạng/batchlog.
- Khiến coordinator gom và phân phối quá nhiều mutation.
- Tạo hot spot và tăng độ trễ đuôi (P95/P99).
- Kích hoạt cảnh báo hoặc ngưỡng từ chối batch lớn.

Với bulk ingestion độc lập, thường nên dùng **prepared statements và các request async có concurrency/rate limit được kiểm soát**, thay vì batch khổng lồ.

## 5. Ví dụ logged batch tạo đơn ở hai bảng

~~~sql
BEGIN BATCH
    INSERT INTO app_ks.orders_by_id (
        order_id, customer_id, order_day, created_at,
        state, version, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?);

    INSERT INTO app_ks.orders_by_customer_day (
        customer_id, order_day, created_at, order_id,
        state, version, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?);
APPLY BATCH;
~~~

Hai statement **phải dùng cùng dữ liệu nghiệp vụ**, dù thứ tự bind khác nhau:

| Bất biến | Điều cần kiểm chứng |
| --- | --- |
| ID | Cùng `order_id` ở cả hai câu INSERT |
| Owner | `customer_id` không bị bind nhầm khách |
| Ngày | `order_day` được tính theo một timezone/quy tắc thống nhất |
| Khóa thời gian | `created_at` giống tuyệt đối sau chuẩn hóa mili giây |
| State | Cùng trạng thái đã được nghiệp vụ chấp nhận |
| Version | Cùng version đã commit, không tự tăng riêng từng bảng |
| Updated timestamp | Cùng business timestamp phù hợp |

**Batch không kiểm tra những bất biến đó thay ứng dụng.** Nếu một statement ghi `customer_id=A` còn statement khác ghi `customer_id=B`, CQL có thể hợp lệ và batch vẫn được áp dụng dù dữ liệu nghiệp vụ sai.

### 5.1. Không có unique constraint trong câu trên

Hai `INSERT` thường của Cassandra có thể **upsert** nếu khóa đã tồn tại. Một logged batch **không chuyển INSERT thành create-only**. Hai command cùng `order_id` với payload khác nhau có thể gây ghi đè hoặc trạng thái hòa giải theo timestamp, không tự báo duplicate key như một số RDBMS.

Nếu cần tạo duy nhất theo `order_id`, phải có **CAS `IF NOT EXISTS` hoặc cơ chế phân xử command tương đương**, và giải quyết riêng chuyện đồng bộ read model.

## 6. Batchlog và ý nghĩa của atomicity cuối cùng

Với logged batch, Cassandra dùng **batchlog** để hỗ trợ thực thi đầy đủ các mutation khi một phần quá trình gặp sự cố, theo những bảo đảm và giả định phục hồi của Cassandra.

~~~mermaid
sequenceDiagram
    participant App as Spring service
    participant Coord as Coordinator
    participant Log as Batchlog replicas
    participant P1 as Replica nhóm bảng ID
    participant P2 as Replica nhóm bảng list
    App->>Coord: BEGIN BATCH
    Coord->>Log: Ghi batchlog
    Coord->>P1: Mutation 1
    Coord->>P2: Mutation 2
    P1-->>Coord: Response theo CL
    Note over P1,P2: Một mutation có thể thấy trước mutation còn lại
    P2-->>Coord: Response theo CL
    Coord-->>App: Success khi yêu cầu thực thi/CL đạt
    Note over Log: Cleanup/replay theo quy trình batchlog
~~~

**Ý nghĩa phù hợp:** logged batch có cơ chế tăng khả năng **cả bộ mutation cuối cùng được thực hiện**, thay vì một request multi-partition unlogged có thể thiếu một mutation sau sự cố.

**Không được suy ra:**

1. Hai bảng đổi trạng thái **cùng một thời điểm đối với mọi reader**.
2. Có **isolation hoặc serializability** xuyên nhiều partition.
3. Hệ thống có lệnh **rollback** để khôi phục trạng thái business cũ.
4. Có **foreign key, unique constraint hoặc optimistic locking**.
5. Hai batch cạnh tranh được tuần tự hóa theo version nghiệp vụ.
6. Client biết chắc “chưa ghi gì” khi bị timeout.

### 6.1. Atomicity cuối cùng khác atomic visibility

~~~text
T0: Cả hai bảng state = CREATED
T1: Logged batch cập nhật PAID được gửi
T2: Bảng orders_by_id bắt đầu cho đọc thấy PAID
T3: Bảng orders_by_customer_day vẫn tạm thời cho thấy CREATED
T4: Mutation ở bảng danh sách được áp dụng/quan sát
T5: Hai bảng hội tụ về PAID nếu không có writer cạnh tranh
~~~

Reader có thể chạy `SELECT` tại T2 và T3, thấy **một nửa kết quả nghiệp vụ mới**. Đây không nhất thiết là lỗi batchlog bị mất; đó là **giới hạn atomic visibility** trong hệ phân tán.

**Cách viết yêu cầu chính xác:** “logged batch hỗ trợ atomicity của các mutation ở trạng thái hoàn tất/phục hồi” chứ không phải “mọi lần đọc xuyên hai bảng đều nhìn thấy transaction snapshot nguyên tử”.

### 6.2. Giới hạn của lời hứa phục hồi

Batchlog không thay thế monitoring, repair, backup hoặc reconciliation. Nếu cluster có sự cố lớn vượt giả định durability và chưa phục hồi hoàn tất, ứng dụng không thể hứa một thời hạn hội tụ tùy ý. Cần phân biệt **bảo đảm của cơ chế Cassandra** với **SLA thực tế của hệ thống**.

## 7. Unlogged batch: hiểu rõ phạm vi và rủi ro

~~~sql
BEGIN UNLOGGED BATCH
    UPDATE app_ks.orders_by_id
    SET state = 'PAID'
    WHERE order_id = ?;

    UPDATE app_ks.orders_by_customer_day
    SET state = 'PAID'
    WHERE customer_id = ? AND order_day = ?
      AND created_at = ? AND order_id = ?;
APPLY BATCH;
~~~

Với **unlogged batch đa partition**, không có batchlog để hỗ trợ **khôi phục toàn bộ nhóm mutation** khi một phần quá trình thất bại. Một số statement có thể áp dụng, statement khác chưa; ứng dụng phải tự theo dõi/retry/đối soát.

Unlogged batch có thể phù hợp hơn khi các mutation **cùng một partition** và đã đánh giá đúng semantics của phiên bản Cassandra. Không áp dụng kết luận “một partition” cho hai bảng khác nhau chỉ vì cùng một ID nghiệp vụ.

### 7.1. Không dùng unlogged batch để né chi phí logged batch mà giữ nguyên hợp đồng

Chuyển `BEGIN BATCH` thành `BEGIN UNLOGGED BATCH` là thay đổi **semantics phục hồi**, không chỉ thay đổi hiệu năng. Đội backend phải chủ động xác nhận khả năng chấp nhận partial failure của workflow.

## 8. Counter batch có quy tắc riêng

~~~sql
CREATE TABLE app_ks.order_counts_by_customer (
    customer_id uuid PRIMARY KEY,
    total_orders counter
);
~~~

~~~sql
BEGIN COUNTER BATCH
    UPDATE app_ks.order_counts_by_customer
    SET total_orders = total_orders + 1
    WHERE customer_id = ?;
APPLY BATCH;
~~~

Không trộn counter update với regular INSERT/UPDATE trong cùng một batch. **Counter increment không idempotent theo cách gán giá trị**: retry sau timeout có thể cộng hai lần nếu lần đầu đã được áp dụng.

Nếu business cần đếm chính xác số đơn được tạo **một lần theo command**, hãy xem xét nguồn sự thật event/command có deduplication và một mô hình aggregation phù hợp, không coi counter batch là transaction bảo vệ unique command.

## 9. Spring Data Cassandra và lựa chọn API batch

**Spring Data Cassandra** hỗ trợ entity mapping, `CassandraRepository` và `CassandraTemplate`. Những API đó thuận tiện cho query/CRUD theo key. Nhưng:

- Hai lời gọi `repository.save(...)` **không tự trở thành một Cassandra batch**.
- `@Transactional` theo semantics RDBMS/JPA **không tạo giao dịch ACID đa partition** cho Cassandra.
- Những Spring Data Cassandra version khác nhau có API batch/operations khác nhau. Cần **đối chiếu đúng version** trước khi dùng chúng như một cam kết semantics.
- Java driver 4.x qua `CqlSession` cho phép khai báo rõ `DefaultBatchType.LOGGED` và các `BoundStatement` trong một `BatchStatement`.

Trong phần kế tiếp ta dùng **Java driver** cho câu batch cụ thể, còn Spring Data repository/template vẫn có thể phục vụ những đường đọc theo entity.

## 10. Java driver 4.x: batch với prepared statements

Ví dụ một gateway giữ `CqlSession` dùng chung, chuẩn bị hai CQL một lần:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Objects;
import java.util.UUID;

public final class OrderBatchGateway {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement byCustomerDay;

    public OrderBatchGateway(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.byId = session.prepare(
            "INSERT INTO app_ks.orders_by_id " +
            "(order_id, customer_id, order_day, created_at, " +
            "state, version, updated_at) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
        this.byCustomerDay = session.prepare(
            "INSERT INTO app_ks.orders_by_customer_day " +
            "(customer_id, order_day, created_at, order_id, " +
            "state, version, updated_at) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public void createInBothTables(
            UUID orderId, UUID customerId,
            LocalDate orderDay, Instant createdAt) {
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(orderDay);
        Objects.requireNonNull(createdAt);

        Instant at = createdAt.truncatedTo(ChronoUnit.MILLIS);

        BatchStatement batch =
            BatchStatement.builder(DefaultBatchType.LOGGED)
                .addStatement(byId.bind(
                    orderId, customerId, orderDay, at,
                    "CREATED", 1L, at))
                .addStatement(byCustomerDay.bind(
                    customerId, orderDay, at, orderId,
                    "CREATED", 1L, at))
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .build();

        session.execute(batch);
    }
}
~~~

**Giả định:** Java driver 4.x, `app_ks` tồn tại, cluster có replication thích hợp với `LOCAL_QUORUM`, và Spring quản lý `CqlSession`. Đổi CL theo topology thật (môi trường một node không thích hợp với RF=3/quorum thực tế).

Giải thích:

1. Hai `PreparedStatement` được tạo **một lần** trên cùng `CqlSession`.
2. Mỗi request tạo các bound statements mới, không chia sẻ giá trị bind giữa thread.
3. `created_at` được chuẩn hóa **mili giây** vì CQL `timestamp` lưu chính xác đến mili giây; tránh lạc khóa khi đọc/xóa hàng ở bảng danh sách sau này.
4. Cả hai statement dùng cùng ID, khách, ngày, createdAt, state và version.
5. CL được cấu hình trên **batch statement**, không tự tạo isolation xuyên bảng.
6. `session.execute(batch)` thành công thể hiện request batch đã được xác nhận theo contract Cassandra; **không** có nghĩa unique ID đã được kiểm tra.
7. Nếu timeout, đừng kết luận cả hai bảng chưa có dữ liệu.

**Không đóng `CqlSession` trong method**. Tài nguyên này có vòng đời theo application/Spring context, không theo một batch.

## 11. Cập nhật state ở cả hai bảng: full key là bắt buộc

Khi đơn chuyển `CREATED → PAID`, ta có thể cần sửa cột `state` ở cả hai hàng:

~~~sql
BEGIN BATCH
    UPDATE app_ks.orders_by_id
    SET state = 'PAID', version = 2, updated_at = ?
    WHERE order_id = ?;

    UPDATE app_ks.orders_by_customer_day
    SET state = 'PAID', version = 2, updated_at = ?
    WHERE customer_id = ? AND order_day = ?
      AND created_at = ? AND order_id = ?;
APPLY BATCH;
~~~

Câu thứ hai cần **đủ bốn thành phần** của primary key. Nếu `created_at` khác bản gốc dù chỉ mili giây, hoặc `order_day` được tính theo timezone khác, Cassandra có thể **upsert một hàng mới tại khóa khác**, không báo lỗi foreign key.

### 11.1. Checklist dữ liệu trước khi gửi batch

| Ràng buộc | Điều cần kiểm tra |
| --- | --- |
| `order_id` | Cùng ID đã commit, không lấy nhầm request khác |
| `customer_id` | Đúng owner từ nguồn sự thật |
| `order_day` | Cùng quy tắc tính ngày/timezone khi tạo |
| `created_at` | Giá trị chuẩn hóa từ lúc tạo, không lấy `Instant.now()` mới |
| `state` | Cùng state đã được business chấp nhận |
| `version` | Cùng version mới, không mỗi bảng tự tăng |
| `updated_at` | Cùng business timestamp để đối chiếu |
| TTL | Đúng chính sách retention của mỗi bảng/cột |

Một logged batch **có thể áp dụng hoàn chỉnh cả hai mutation có dữ liệu sai**. Nó không validate mối quan hệ giữa chúng.

### 11.2. Hai câu SET version=2 chưa phải optimistic locking

Nếu hai writer đều đã đọc version=1, họ có thể đồng thời gửi:

~~~text
Writer A: state=PAID,      version=2
Writer B: state=CANCELLED, version=2
~~~

Không có điều kiện `IF`, Cassandra có thể xác nhận cả hai; cell cạnh tranh được hòa giải theo **write timestamp**. Cột `version` chỉ là **dữ liệu**, không tự biến thành compare-and-set.

**Quorum không tự ngăn lost update.** Nó kiểm soát số replica phản hồi, không kiểm tra nghiệp vụ “version vẫn là 1”.

## 12. Batch và LWT: ràng buộc quan trọng

**Lightweight transaction (LWT)** với `IF NOT EXISTS`, `IF EXISTS` hoặc `IF version = ?` cho phép Cassandra thực hiện conditional write trên dữ liệu được định vị. Nhưng conditional batch có **giới hạn về partition và loại statement**. Không được tự tạo một batch có `IF` trên bảng ID và các mutation tùy ý ở bảng danh sách rồi gọi đó là **giao dịch có điều kiện đa partition**.

Ví dụ ý định **không nên áp dụng nguyên xi**:

~~~sql
-- KHÔNG sao chép như một conditional multi-partition batch hợp lệ.
BEGIN BATCH
    UPDATE app_ks.orders_by_id
    SET state = 'PAID', version = 2
    WHERE order_id = ?
    IF version = 1;

    UPDATE app_ks.orders_by_customer_day
    SET state = 'PAID', version = 2
    WHERE customer_id = ? AND order_day = ?
      AND created_at = ? AND order_id = ?;
APPLY BATCH;
~~~

**Thay vào đó, tách ranh giới commit:**

1. Dùng LWT trên **nguồn sự thật `orders_by_id`**.
2. Chỉ khi `[applied] = true` mới xem command nghiệp vụ đã được chấp nhận.
3. Đồng bộ read model từ state/version đã commit bằng một workflow có thể retry.
4. Nếu `[applied] = false`, coi là conflict/condition failure theo contract, không sửa bảng danh sách như thể command thành công.
5. Nếu timeout/Unavailable, **không suy thành false**; đối soát xem quyết định đã commit chưa.

CQL CAS ở bảng ID:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, version = ?, updated_at = ?
WHERE order_id = ?
IF version = ? AND state = ?;
~~~

| Kết quả | Ứng dụng nên làm |
| --- | --- |
| `[applied] = true` | Command được chấp nhận; tiếp tục handoff cho read model |
| `[applied] = false` | Kiểm tra stale version/state, trả conflict hoặc đọc lại |
| Timeout/exception | Phân loại lỗi; có thể outcome chưa xác định, cần idempotency/reconciliation |

Java driver 4.x cung cấp `ResultSet.wasApplied()` để đọc kết quả conditional write. Với `@Query`/`@Modifying` trong Spring Data Cassandra, cần xác minh phiên bản và **không suy từ method trả `void` rằng điều kiện đã được áp dụng**.

## 13. Thiết kế projector và handoff bền vững

Nếu business state được quyết định ở `orders_by_id` bằng LWT, làm sao bảo đảm read model `orders_by_customer_day` cuối cùng cũng nhận được trạng thái mới?

~~~mermaid
flowchart TD
    A[API: PayOrder command] --> B[CAS nguồn sự thật]
    B --> C{applied?}
    C -->|Không| D[Conflict / không project]
    C -->|Có| E[Handoff bền vững / event được commit]
    E --> F[Projector có retry]
    F --> G[orders_by_customer_day]
    G --> H[Checkpoint + metrics]
    H --> I[Reconciler phát hiện lỗi hoặc lag]
~~~

Đây là **kiến trúc ứng dụng phải xây dựng**, không phải tính năng tự động từ một câu `BEGIN BATCH`.

Một lỗi thường gặp:

~~~text
T1: CAS orders_by_id -> applied = true
T2: Service gửi message tới projector -> timeout
T3: Service bị restart
T4: Bảng orders_by_customer_day không nhận được thay đổi
~~~

Khi T1 đã thành công, ứng dụng **không được rollback logic bằng cách báo command chưa diễn ra** chỉ vì T2 không có phản hồi. Phải có dấu vết bền vững để khôi phục công việc còn dang dở.

### 13.1. Các lựa chọn thực tế

**Event stream làm nguồn sự thật:** mỗi command được phân xử bằng cơ chế append/sequence/idempotency phù hợp; read models phát sinh từ các event đã commit. Một event và state snapshot là hai bước khác nhau, vì vậy cần xác định rõ **điểm commit nghiệp vụ nằm ở event stream**.

**Snapshot làm nguồn sự thật:** dùng CAS trên `orders_by_id`, sau đó tạo handoff/projection theo quy trình có thể retry, kèm reconciler dựa vào nguồn sự thật.

**Outbox hoặc CDC:** dùng khi hạ tầng/phiên bản Cassandra và topology hỗ trợ một phương án ghi nhận sự thay đổi **bền vững**. Không được nói “có outbox là atomic” nếu outbox record và quyết định nghiệp vụ là **hai partition độc lập** mà không có bảo đảm giao dịch phù hợp.

**Workflow/saga:** cần khi một command thay đổi nhiều partition hoặc nhiều hệ thống. Từng bước có trạng thái, retry/idempotency và một đường đối soát/phục hồi. Không giả định có rollback ACID cho toàn workflow.

### 13.2. Event id và version

Ví dụ projector có thể nhận:

~~~text
OrderStateChanged(orderId = X, version = 4, state = PAID)
OrderStateChanged(orderId = X, version = 3, state = CREATED)
~~~

Nếu version 3 đến **sau** version 4, câu `UPDATE state = 'CREATED'` không điều kiện ở read model có thể **làm lùi trạng thái**, nhất là khi retry phát sinh write timestamp mới. Bởi vậy projector cần:

1. **Event ID hoặc command ID ổn định** để nhận biết xử lý lặp.
2. `version` hoặc sequence gắn với quyết định đã commit.
3. **Quy tắc áp event có điều kiện** hoặc single-writer theo aggregate để không nhận bản cũ sau bản mới.
4. Checkpoint/inbox và cơ chế khôi phục khi service chết giữa lúc apply và ghi nhận checkpoint.
5. Khả năng tái tạo projection từ nguồn sự thật mà không phát lặp side effect bên ngoài.

Không được cho rằng Cassandra tự hiểu `version` là “event có version lớn hơn thì thắng” chỉ vì cột đó xuất hiện trong bảng.

## 14. Đổi khóa phân nhóm: cần INSERT khóa mới và DELETE khóa cũ

Trong bảng `orders_by_customer_day`:

- `customer_id`, `order_day` là partition key.
- `created_at`, `order_id` là clustering key.

**Primary key là bất biến.** Nếu quy tắc nghiệp vụ thay đổi `customer_id` hoặc ngày phân nhóm, `UPDATE SET order_day = ?` không thể “di chuyển” hàng sang partition mới.

Quy trình logic:

1. Biết **toàn bộ khóa cũ** của hàng trong read model.
2. Ghi hàng mới với khóa mới từ dữ liệu của nguồn sự thật đã commit.
3. Xóa hàng cũ bằng full key.
4. Thiết kế retry, idempotency, tombstone và đối soát cửa sổ có thể thấy cả hàng cũ lẫn hàng mới.

Ví dụ:

~~~sql
BEGIN BATCH
    INSERT INTO app_ks.orders_by_customer_day (
        customer_id, order_day, created_at, order_id,
        state, version, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?);

    DELETE FROM app_ks.orders_by_customer_day
    WHERE customer_id = ? AND order_day = ?
      AND created_at = ? AND order_id = ?;
APPLY BATCH;
~~~

Batch này có thể chạm **hai partition**. Logged batch có cơ chế replay mutation, **không bảo đảm atomic visibility của thao tác di chuyển** đối với một reader đọc hai partition.

### 14.1. Nguy cơ cần test

- **Khóa cũ sai:** DELETE không xóa đúng hàng; danh sách xuất hiện duplicate.
- **Khóa mới sai:** đơn biến mất khỏi danh sách mục tiêu dù nguồn sự thật vẫn có.
- **Timestamp precision khác:** `created_at` được chuẩn hóa mili giây khi tạo nhưng code update dùng nanosecond mới.
- **Retry:** một request cũ xóa nhầm hàng đã được chuyển lần khác.
- **Tombstone:** DELETE tạo marker xóa; đổi nhóm quá thường xuyên có thể gây read amplification.
- **Concurrent updates:** move theo version cũ có thể đem state cũ vào partition mới.

Để giảm rủi ro, coi metadata định vị read model là **giá trị đã commit** và cho reconciler sửa khi phát hiện sai khác. Nếu phân nhóm thay đổi liên tục, cân nhắc thiết kế bảng truy vấn khác.

## 15. TTL và tombstone: không copy retention một cách máy móc

Một ứng dụng có thể giữ `orders_by_id` lâu dài nhưng chỉ lưu danh sách tra cứu 90 ngày. Chính sách TTL phải **được mô tả riêng cho từng bảng hoặc từng loại cell**.

~~~sql
BEGIN BATCH
    INSERT INTO app_ks.orders_by_id (
        order_id, customer_id, order_day, created_at,
        state, version, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?);

    INSERT INTO app_ks.orders_by_customer_day (
        customer_id, order_day, created_at, order_id,
        state, version, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    USING TTL 7776000;
APPLY BATCH;
~~~

`7776000` giây là 90 ngày theo quy ước 24 giờ/ngày. Đây là **ví dụ chính sách**, không có nghĩa sản phẩm nào cũng nên xóa read model sau 90 ngày.

| Ràng buộc TTL | Cần kiểm chứng |
| --- | --- |
| Bảng chi tiết không được tự hết hạn | Không áp nhầm TTL của bảng danh sách sang bảng ID |
| Bảng danh sách có retention riêng | Dữ liệu biến mất khi đúng chính sách, không sớm hơn |
| Update state sau INSERT | Ghi lại cell có thể thay đổi TTL theo statement/default TTL |
| Trường KEEP/UNSET | Nếu không có mutation, không refresh TTL cũ |
| Trường NULL/DELETE | Có thể tạo tombstone, không phải “bỏ qua” |
| `default_time_to_live` | Dữ liệu ghi mới có thể chịu TTL mặc định khi không nêu USING TTL |
| Move partition | DELETE khóa cũ có thể tạo tombstone |

**Bẫy phổ biến:** ghi lại cùng giá trị `state = PAID` bằng một UPDATE mới **không đồng nghĩa giữ nguyên TTL**. Write timestamp và TTL có thể thay đổi, kể cả khi SELECT vẫn trả text `PAID`. Một batch retry cũng có thể làm mới expiration nếu statement/driver tạo mutation mới với TTL tương ứng.

### 15.1. Tombstone không được loại bỏ bởi batch

Hàng bị xóa hoặc cell hết TTL tạo thông tin xóa theo cơ chế Cassandra. Batch không làm tombstone biến mất. Trên partition lớn, việc đọc qua nhiều tombstone có thể gây tăng latency, CPU, disk I/O hoặc cảnh báo.

Không hạ `gc_grace_seconds` tùy tiện để giải quyết việc move quá thường xuyên. Cần đánh giá repair, topology và chính sách dọn tombstone của **phiên bản Cassandra thực tế**, tránh rủi ro dữ liệu đã xóa được phục hồi sai.

## 16. Batch size và hiệu năng thực tế

Một batch đa partition lớn có thể buộc coordinator xử lý quá nhiều mutation, đồng thời tốn batchlog và network traffic. Đừng đánh giá batch chỉ bằng số câu CQL: **độ lớn payload, số partition, số replica, kiểu dữ liệu và tải cluster** đều ảnh hưởng hiệu năng.

| Trường hợp | Cách tiếp cận |
| --- | --- |
| Hai mutation nhỏ phục vụ một command, thật sự cần batchlog | Cân nhắc một logged batch nhỏ, test behavior lỗi |
| Nhiều row trong **cùng partition** | Xem xét cách gom phù hợp; kiểm chứng isolation theo version |
| Hàng trăm nghìn row thuộc partition độc lập | Bounded async requests/queue, không một batch khổng lồ |
| Nhiều LWT cạnh tranh một hot partition | Giảm contention/thiết kế single-writer, không thêm batch lớn |
| Ghi counter song song với regular state | Tách mutation, không trộn trong một batch |

Cassandra có các ngưỡng cảnh báo/từ chối batch quá lớn tùy phiên bản/cấu hình. **Không suy ra một ngưỡng cố định cho mọi cluster**, và không dùng ngưỡng cảnh báo như mục tiêu “chỉ cần dưới ngưỡng là tối ưu”.

**Metrics nên theo dõi:**

1. P50/P95/P99 write latency theo kiểu batch và số partition.
2. Số byte, số statement và số partition trong batch.
3. Warnings/failures của large batch.
4. Coordinator CPU/network, batchlog pending/replay theo môi trường.
5. Timeout/Unavailable, tỷ lệ retry và độ dài request queue.
6. Hot partition, tombstone/read amplification và độ trễ projection.
7. Số lượng row lệch giữa bảng ID và bảng danh sách.

## 17. Consistency level không tạo isolation xuyên hai bảng

CL của batch quy định điều kiện phản hồi replica theo semantics Cassandra; logged batch lại cung cấp cơ chế batchlog/replay. **Hai cơ chế đó không cộng lại thành multi-table snapshot isolation.**

Giả sử RF=3 trong một datacenter, write `LOCAL_QUORUM` và read `LOCAL_QUORUM`. Dù cặp mức này hữu ích cho read-after-write **đối với một mutation được xác nhận, cùng nhóm replica và không có writer cạnh tranh**, hai câu:

~~~sql
SELECT state FROM app_ks.orders_by_id
WHERE order_id = ?;

SELECT state FROM app_ks.orders_by_customer_day
WHERE customer_id = ? AND order_day = ?
  AND created_at = ? AND order_id = ?;
~~~

vẫn là **hai truy vấn riêng**. Chúng có thể xen vào các thời điểm khác nhau của batch đang áp dụng. Không được hứa chúng luôn trả cùng version tại mọi thời điểm.

### 17.1. Multi-datacenter

`LOCAL_QUORUM` ghi ở DC A và `LOCAL_QUORUM` đọc ở DC B **không tự tạo quorum overlap giữa hai DC**. Dữ liệu có thể đang được replication sang DC B. Logged batch không tự biến local consistency thành global consistency.

Nếu nghiệp vụ yêu cầu quan sát tức thời sau failover, cần thiết kế routing, consistency, SLA và phục hồi xuyên DC riêng; không chỉ thêm `BEGIN BATCH`.

## 18. Timeout, retry và idempotency của một batch

Một batch timeout không cho client biết chắc trạng thái cuối:

~~~text
Application -> Cassandra: logged batch
Cassandra: batchlog hoặc một số mutation có thể đã được ghi
Application: timeout, chưa nhận success
Application: phải coi outcome là chưa xác định ở thời điểm đó
~~~

**Không được** tự kết luận “Cassandra rollback hết” hoặc chạy lại mọi mutation không điều kiện bằng snapshot cũ.

| Kiểu mutation | Retry có nguy cơ gì? |
| --- | --- |
| `SET state = 'PAID'` | Có thể ghi đè state mới hơn do timestamp retry |
| `INSERT` cùng key/value | Upsert/timestamp vẫn có thể thay metadata |
| `INSERT ... USING TTL` | Retry có thể làm mới expiration |
| `DELETE` | Tombstone/timestamp và cạnh tranh với reinsert |
| Counter increment | Có thể tăng hai lần |
| Gửi email/thanh toán bên ngoài | Có thể tạo side effect lặp |

Đừng đặt `setIdempotent(true)` chỉ để driver tăng số retry. **Idempotency phải được chứng minh cho toàn bộ batch** trong điều kiện timestamp, TTL, cạnh tranh và side effect thực tế.

### 18.1. Quy trình sau timeout

1. Đọc lại **nguồn sự thật** theo primary key và CL phù hợp.
2. Đối chiếu `requestId`, `version` hoặc event ID nếu hệ thống lưu.
3. Xác định command trước đã được chấp nhận hay bị từ chối.
4. Nếu command đã commit, **khôi phục read model** theo version đã commit.
5. Nếu chưa commit, có thể gửi lại lệnh **có guard** với business state hiện hành.
6. Nếu chưa xác định được, trả trạng thái pending/unknown và có quy trình đối soát thay vì báo thành công/thất bại chắc chắn.

Một ID được cấp ngẫu nhiên **mỗi lần retry** không đủ để chống duplicate command. Cần một `requestId` ổn định xuyên các lần thử và nơi lưu kết quả đủ bền vững.

## 19. Reconciliation: phát hiện và sửa bản sao lệch

Với nguồn sự thật `orders_by_id` và read model `orders_by_customer_day`, reconciler cần nhận diện:

- Hàng danh sách **thiếu** so với đơn đã commit.
- Hàng danh sách **thừa** tại khóa cũ sau khi chuyển nhóm.
- `state`, `version` hoặc `updated_at` không khớp.
- `customer_id`/`order_day`/`created_at` định vị sai.
- Hàng hết TTL đúng chính sách hay mất ngoài dự kiến.

~~~mermaid
flowchart TD
    A[Nhận orderId cần kiểm tra] --> B[Đọc orders_by_id]
    B --> C{Hàng nguồn có còn tồn tại?}
    C -->|Có| D[Lấy full key bảng danh sách]
    C -->|Không| E[Kiểm tra retention / delete workflow]
    D --> F[Đọc orders_by_customer_day theo full key]
    F --> G{Version và field khớp?}
    G -->|Có| H[Không cần sửa]
    G -->|Không| I[Project lại với guard phù hợp]
    I --> J[Ghi kết quả/metrics]
    E --> J
~~~

**Không làm theo cách quét `repository.findAll()` cả cluster rồi so sánh hai danh sách trong heap.** Phương án đó có thể rất tốn kém, không tạo snapshot toàn cục, và khó mở rộng.

Một reconciler thực tế nên:

1. Có **nguồn ID cần kiểm tra** (event log, CDC, command ledger hoặc các bucket theo ngày).
2. Đọc từng key theo access pattern phù hợp.
3. Giới hạn concurrency, page size, rate và tổng số bản ghi.
4. So sánh version; không để event cũ ghi đè projection mới.
5. Dùng retry/idempotency và báo cáo số row sai khác.
6. Chấp nhận một **ngưỡng lag hợp lý**, tránh liên tục “sửa” những write đang được apply bình thường.

### 19.1. Reconcile không tự có snapshot nguyên tử

Ngay cả khi reconciler đọc hai bảng thành công, writer có thể cập nhật giữa hai lần đọc. Vì vậy bước sửa cần version guard, single-writer hoặc quy tắc idempotency. Không coi bản sao mới đọc là bất biến.

## 20. Kiểm thử tích hợp: chứng minh từng ràng buộc

Mock repository đủ để kiểm tra service gọi đúng method, nhưng **không chứng minh batchlog, replica, concurrency hoặc hiệu năng thật**. Bài lab cần một Cassandra test cluster phù hợp.

### 20.1. Test happy path

Ví dụ JUnit 5 rút gọn, giả định `session` đã được inject từ test fixture, keyspace và hai bảng tồn tại:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

@Test
void loggedBatchWritesBothTables() {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    LocalDate day = LocalDate.of(2026, 11, 25);
    Instant createdAt = Instant.parse("2026-11-25T09:30:00Z");

    new OrderBatchGateway(session).createInBothTables(
        orderId, customerId, day, createdAt);

    PreparedStatement selectId = session.prepare(
        "SELECT state, version FROM app_ks.orders_by_id " +
        "WHERE order_id = ?"
    );
    Row source = session.execute(selectId.bind(orderId)).one();
    assertNotNull(source);
    assertEquals("CREATED", source.getString("state"));
    assertEquals(1L, source.getLong("version"));

    PreparedStatement selectList = session.prepare(
        "SELECT state, version " +
        "FROM app_ks.orders_by_customer_day " +
        "WHERE customer_id = ? AND order_day = ? " +
        "AND created_at = ? AND order_id = ?"
    );
    Row projection = session.execute(
        selectList.bind(customerId, day, createdAt, orderId)).one();
    assertNotNull(projection);
    assertEquals("CREATED", projection.getString("state"));
    assertEquals(1L, projection.getLong("version"));
}
~~~

**Lưu ý:** fixture phải có Cassandra thật, driver session, replication/CL hợp lệ, cleanup test và các imports tương ứng. Một test thành công chứng minh dữ liệu mong đợi **sau khi request hoàn tất**; nó **không chứng minh mọi reader trong lúc request chạy đều thấy hai bảng cùng thời điểm**.

### 20.2. Ma trận kiểm chứng

| Tình huống | Hành động | Kỳ vọng hoặc câu hỏi cần trả lời |
| --- | --- | --- |
| Tạo đơn bằng logged batch | Ghi hai bảng | Cùng order ID, state, version |
| Mapper bind nhầm customer/day | Dữ liệu hai bảng khác nhau | Test phải phát hiện; batch không tự reject |
| Sai precision của `created_at` | Query theo khóa khác mili giây | Phát hiện lạc hàng/upsert trùng |
| Hai tạo đơn cùng ID | Hai batch thường | Hiểu nguy cơ upsert, không có unique tự động |
| Hai writer cập nhật state | Concurrent batches | Không có optimistic locking nếu không dùng CAS |
| CAS nguồn true | Project version mới | Bảng danh sách hội tụ đúng |
| CAS nguồn false | Không project command bị từ chối | Không ghi nhầm state |
| Logged batch timeout | Request mất phản hồi | Client outcome chưa rõ; cần đối soát |
| Unlogged multi-partition gián đoạn | Fault injection trong lab | Không dựa vào batchlog để replay |
| Thay đổi order_day | INSERT khóa mới + DELETE khóa cũ | Giám sát duplicate/missing tạm thời |
| TTL riêng cho danh sách | Update sau INSERT | Kiểm tra expiration theo policy |
| Counter retry | Increment hai lần | Không giả định idempotent |
| Large batch | Tải thử có giới hạn | Xem warnings, latency, coordinator load |
| Multi-DC | Write/read local ở hai DC | Không suy diễn đọc tức thì |
| Projector nhận event cũ | Version 3 đến sau version 4 | Không làm lùi read model |
| Reconciler chạy lại | Read model thiếu hoặc lệch | Sửa idempotent, không gây thêm side effect |

### 20.3. Fault injection và topology

Muốn quan sát replay khi coordinator/replica lỗi:

1. Chỉ dùng **cluster lab riêng**, có đủ node cho RF và CL.
2. Ghi lại Cassandra/driver version, replication strategy, node topology và cấu hình timeout.
3. Tiêm lỗi có kiểm soát, quan sát trạng thái trước/sau phục hồi.
4. Phân biệt hành vi **batchlog replay** với **reconciler của ứng dụng**.
5. Không lấy một lần SELECT tức thì làm kết luận về “đã mất vĩnh viễn”.
6. Không suy từ một test thành công ra bảo đảm không có failure mode nào khác.

**Không chạy node failure, stress test hoặc network partition trên production để thực hành bài này.**

## 21. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Có batch nên hai bảng cùng thay đổi tức thời.” | Logged batch không tạo atomic visibility đa partition |
| “Logged batch giống SQL transaction.” | Batchlog/replay khác isolation/rollback trong RDBMS |
| “Hai bảng cùng order ID là cùng partition.” | Mỗi bảng có partition key và storage scope riêng |
| “Unlogged batch có replay như logged.” | Unlogged không có batchlog |
| “Batch lớn giúp bulk import luôn nhanh.” | Coordinator/batchlog có thể thành bottleneck |
| “Batch tự ngăn tạo ID trùng.” | INSERT bình thường vẫn upsert |
| “Ghi version=2 nghĩa đã có optimistic locking.” | Cần kiểm tra `IF version = ?` hoặc guard tương đương |
| “Có thể dùng IF để làm CAS đa partition tùy ý.” | Conditional batch/LWT có giới hạn partition và cú pháp |
| “QUORUM bảo đảm hai bảng có cùng snapshot.” | Consistency của replica không phải multi-table isolation |
| “Batch timeout nghĩa là chưa ghi gì.” | Một số hoặc tất cả mutation có thể đã được thực hiện |
| “Retry batch luôn idempotent.” | TTL/counters/timestamps/side effects có thể không idempotent |
| “UPDATE bảng list theo order ID là đủ.” | Cần full partition/clustering key |
| “Đổi order_day bằng UPDATE di chuyển partition.” | Primary key bất biến; cần insert/delete và đối soát |
| “TTL hai bản sao bắt buộc bằng nhau.” | Retention phụ thuộc chính sách của từng bảng/cell |
| “Logged batch tự đưa event vào message broker.” | Cần handoff/outbox/CDC/workflow riêng |
| “Dùng findAll hai bảng sẽ đối soát tốt.” | Có thể scan vô hạn và không có snapshot toàn cục |

## 22. Bài tập tổng hợp

**Đề bài:** xây một ứng dụng Spring Data Cassandra phục vụ tìm đơn theo ID và liệt kê đơn theo khách/ngày, đồng thời xử lý tạo, thanh toán và đối soát an toàn.

Các bước:

1. Tạo hai bảng từ phần 2, mô tả nguồn sự thật/read model.
2. Ghi một đơn bằng hai INSERT riêng, sau đó viết logged batch và so sánh mục tiêu của chúng.
3. Tạo `OrderBatchGateway` với hai prepared statements và `DefaultBatchType.LOGGED`.
4. Kiểm tra `customer_id`, `order_day`, `created_at` và `order_id` giống nhau ở hai bảng.
5. Thêm nhiều đơn cùng customer/day, xác minh clustering order và `LIMIT 20`.
6. Cố ý bind nhầm customer ở một statement trong môi trường test; chứng minh batch không sửa được sai sót nghiệp vụ.
7. Thực hiện hai batch cập nhật state cạnh tranh, quan sát nguy cơ lost update.
8. Viết CAS nguồn sự thật bằng `IF version = ? AND state = ?`; chỉ project command đã được áp dụng.
9. Mô phỏng projection failure sau khi CAS true; thiết kế retry/idempotency và đối soát.
10. Di chuyển một hàng danh sách sang partition ngày mới; ghi nhận tombstone và cửa sổ dữ liệu tạm thời.
11. Thử retention/TTL khác nhau cho hai bảng.
12. Thử timeout batch trong lab, không đoán “đã rollback”.
13. Đo batch size, P95/P99 latency, coordinator warnings và projection lag.
14. Thiết kế reconciler đọc theo key có page/rate limit và version guard.
15. Viết tài liệu cam kết rõ **Cassandra batch bảo vệ điều gì, ứng dụng phải tự bảo vệ điều gì**.

**Tiêu chí hoàn thành:** người học phân biệt được logged/unlogged/counter batch và **atomicity cuối cùng với isolation**, cập nhật đúng dữ liệu qua hai schema, có hướng xử lý CAS/idempotency, và xây được cách kiểm chứng/khôi phục một read model phi chuẩn hóa.

## 23. Câu hỏi tự kiểm tra

1. Vì sao một thực thể có thể xuất hiện ở nhiều bảng Cassandra?
2. Hai bảng trong bài phục vụ hai đường truy vấn nào?
3. Tại sao hai hàng có cùng order ID nhưng khác bảng không được xem là cùng partition?
4. `BEGIN BATCH` mặc định có logged không? Batchlog có vai trò gì?
5. Atomicity cuối cùng khác atomic visibility như thế nào?
6. Logged batch có tạo isolation/rollback đa partition kiểu RDBMS không?
7. Khi nào unlogged batch có thể phù hợp? Hạn chế multi-partition của nó là gì?
8. Counter batch dùng cho thao tác nào, và tại sao không nên retry increment tùy tiện?
9. Vì sao batch lớn có thể làm giảm throughput?
10. Hai INSERT của logged batch có kiểm tra duy nhất `order_id` không?
11. Những cột khóa nào bắt buộc khi cập nhật bảng `orders_by_customer_day`?
12. Điều gì xảy ra nếu `created_at` dùng trong UPDATE khác timestamp gốc?
13. Ghi version 2 ở hai bảng có phải là optimistic locking không? Vì sao?
14. Tại sao không được tự mở rộng `IF version` thành conditional batch tùy ý nhiều partition?
15. Nếu nguồn sự thật CAS thành công nhưng projection chưa cập nhật, API nên diễn giải thế nào?
16. Khi projector nhận event version cũ sau version mới, cần ràng buộc gì?
17. Đổi `order_day` của hàng danh sách cần những thao tác nào?
18. TTL của bảng ID và bảng danh sách có bắt buộc giống nhau không?
19. Một logged batch timeout có thể đã thực hiện đến đâu?
20. Vì sao `setIdempotent(true)` không được đặt khi chưa chứng minh idempotency?
21. `LOCAL_QUORUM` cho cả hai query có tạo snapshot nguyên tử xuyên bảng không?
22. Vì sao reconciler không nên quét `findAll()` toàn cluster?
23. Những metrics nào giúp phát hiện batch quá lớn hoặc projection bị trễ?
24. Test happy path có chứng minh được khả năng phục hồi mọi lỗi node không?
25. Trong thiết kế thực tế, **nguồn sự thật** là bảng/event nào và cách khôi phục các bảng còn lại là gì?

**Ghi nhớ:** Cassandra batch giúp gom mutation. **Logged batch có batchlog hỗ trợ phục hồi cả bộ mutation**, nhưng **không có atomic visibility, isolation, unique constraint hoặc CAS đa partition tùy ý**. Với bảng phi chuẩn hóa, phải **bind đúng toàn bộ khóa và dữ liệu chung, chọn nguồn sự thật, kiểm soát version/TTL/timestamp, thiết kế idempotency và reconciliation**. Chỉ sử dụng batch nhỏ khi có lý do đúng, đo trên cluster thử nghiệm và không xem `BEGIN BATCH` là sự thay thế cho giao dịch nghiệp vụ phân tán.
