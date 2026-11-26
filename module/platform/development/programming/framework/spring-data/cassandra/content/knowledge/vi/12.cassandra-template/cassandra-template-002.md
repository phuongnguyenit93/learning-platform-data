# insert, update, delete và select theo entity

**`CassandraTemplate`** là API thao tác dữ liệu đồng bộ của **Spring Data Cassandra**. Thay vì tự viết mọi câu lệnh CQL, ứng dụng có thể đưa entity Java cho template để thực hiện **`insert`**, **`update`**, **`delete`** và **`select`**. Spring Data sử dụng metadata như `@Table`, `@PrimaryKey`, `@Column` và cơ chế chuyển đổi kiểu để xây dựng truy vấn và ánh xạ kết quả.

Điểm quan trọng là **Cassandra không có cùng ngữ nghĩa CRUD như một cơ sở dữ liệu quan hệ**. Lệnh `INSERT` và `UPDATE` thường đều mang tính *upsert*; khóa chính quyết định hàng nào được ghi; `DELETE` tạo tombstone; và truy vấn `SELECT` phải phù hợp partition key, clustering key. Bài thuộc chương **CassandraTemplate** của module **SPRING_DATA_CASSANDRA**: ta sẽ thực hành bốn thao tác theo entity, rồi xem các đánh đổi về tính nhất quán, paging và hiệu năng.

## 1. CassandraTemplate nằm ở đâu trong kiến trúc?

~~~text
Service của ứng dụng
       |
       v
CassandraTemplate (đồng bộ)
       |
       +--> Metadata của entity: @Table, @PrimaryKey, @Column
       +--> Mapping / custom conversion
       +--> Sinh hoặc thực thi truy vấn CQL theo API đã gọi
       |
       v
Java Driver (CqlSession) --> Coordinator --> Replica của partition
~~~

| Thành phần | Dùng khi nào? | Lưu ý |
| --- | --- | --- |
| `CassandraRepository` | CRUD phổ biến, query method theo interface | Không loại bỏ giới hạn CQL; thường dựa trên `CassandraTemplate` |
| **`CassandraTemplate`** | Muốn chủ động thao tác theo entity và xây `Query`/`Update` | Cân bằng giữa object mapping và quyền kiểm soát truy vấn |
| `CqlSession` / CQL trực tiếp | Cần statement/feature CQL cụ thể, kiểm soát bind và execution options | Tự xử lý binding, codec và đôi khi mapping kết quả |
| `ReactiveCassandraTemplate` | Ứng dụng dùng luồng phản ứng `Mono`/`Flux` | API khác, cùng quy tắc dữ liệu Cassandra |

Các ví dụ chính sử dụng **Spring Boot 3.x và Spring Data Cassandra tương thích**. Chữ ký method có thể khác theo phiên bản; khi áp dụng trong dự án, kiểm tra API reference của version thực tế. Template đồng bộ có thể chặn thread gọi trong lúc I/O.

## 2. Chuẩn bị bảng CQL theo truy vấn

Giả sử tính năng cần: **lưu một đơn hàng**, **đổi trạng thái**, **xóa một đơn**, **đọc theo khóa đầy đủ** và **liệt kê các đơn gần nhất của một khách hàng trong một ngày**.

Chọn bảng phục vụ các truy vấn đó:

~~~sql
CREATE KEYSPACE IF NOT EXISTS commerce_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS commerce_ks.orders_by_customer_day (
    customer_id  uuid,
    order_day    date,
    placed_at    timestamp,
    order_id     uuid,
    status       text,
    total_amount decimal,
    note         text,
    PRIMARY KEY ((customer_id, order_day), placed_at, order_id)
) WITH CLUSTERING ORDER BY (placed_at DESC, order_id DESC);
~~~

Tên `dc1` và replication factor 3 chỉ là ví dụ; cluster phải có datacenter/topology phù hợp. Trong môi trường sản xuất, tạo và thay đổi schema qua quy trình quản lý lược đồ, không cho mỗi lần ứng dụng khởi động tự sửa bảng.

Đọc khóa:

~~~text
PRIMARY KEY (
    (customer_id, order_day),   -- composite partition key
    placed_at,                  -- clustering column thứ nhất
    order_id                    -- clustering column thứ hai
)
~~~

- Cặp `(customer_id, order_day)` quyết định **partition** và token dùng để định tuyến tới replica.
- `placed_at` và `order_id` phân biệt và sắp xếp các hàng bên trong partition.
- Cả bốn giá trị tạo thành **primary key đầy đủ của một đơn hàng** trong bảng.
- Truy vấn liệt kê đơn của một khách/ngày cung cấp đủ partition key; thứ tự mặc định của bảng ưu tiên đơn mới theo `placed_at DESC`.

Không dùng `PRIMARY KEY (customer_id, order_day, placed_at, order_id)` nếu mục tiêu là chia theo khách **và ngày**: cú pháp đó chỉ có partition key `customer_id`, còn `order_day` trở thành clustering column.

## 3. Entity mapping với primary key tổng hợp

Spring Data Cassandra có thể biểu diễn khóa nhiều cột bằng `@PrimaryKeyClass` và `@PrimaryKeyColumn`. Ví dụ Java (lược bỏ một số import/boilerplate, và giả sử các class được tách vào file phù hợp):

~~~java
@PrimaryKeyClass
public class OrderKey implements Serializable {

    @PrimaryKeyColumn(
        name = "customer_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "order_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate orderDay;

    @PrimaryKeyColumn(
        name = "placed_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant placedAt;

    @PrimaryKeyColumn(
        name = "order_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private UUID orderId;

    // Constructor, getter/setter, equals và hashCode.
}

@Table("orders_by_customer_day")
public class OrderRow {

    @PrimaryKey
    private OrderKey key;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    @Column("note")
    private String note;

    // Constructor, getter/setter.
}
~~~

Các kiểu Java chính gồm `UUID`, `LocalDate`, `Instant` và `BigDecimal`, tương ứng với `uuid`, `date`, `timestamp` và `decimal` trong CQL. Entity và khóa cần có constructor/accessor phù hợp với cách Spring Data materialize object; value object khóa nên triển khai `equals/hashCode` đúng ngữ nghĩa.

**Không dùng `@GeneratedValue` theo thói quen JPA.** Cassandra không tự phát sinh khóa như một cột identity của cơ sở dữ liệu quan hệ. Ứng dụng phải cung cấp đầy đủ primary key hợp lệ trước khi ghi, chẳng hạn tạo `UUID` cho `order_id` ở tầng nghiệp vụ.

## 4. Cấu hình và inject CassandraTemplate

Với Spring Boot 3.x, dependency đồng bộ thường là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: dc1
    keyspace-name: commerce_ks
    schema-action: none
~~~

`schema-action: none` nghĩa là không dựa vào Spring Data để tự tạo lại schema khi ứng dụng khởi động; keyspace và bảng phải tồn tại trước. Nếu ứng dụng chạy trong container, `127.0.0.1` là máy/container của chính ứng dụng, không phải mặc nhiên là host Cassandra khác.

Khi auto-configuration được kích hoạt đúng, có thể inject template:

~~~java
@Service
public class OrderStorage {

    private final CassandraTemplate template;

    public OrderStorage(CassandraTemplate template) {
        this.template = template;
    }

    // Các thao tác theo entity nằm ở các phần tiếp theo.
}
~~~

Không tạo một `CqlSession` hoặc `CassandraTemplate` mới ở từng HTTP request. Ưu tiên dùng bean do Spring quản lý, cùng cấu hình driver, keyspace, xác thực và TLS của môi trường.

## 5. insert: tạo hoặc ghi đè các giá trị theo primary key

Sử dụng entity có khóa đầy đủ:

~~~java
OrderKey key = new OrderKey(
        customerId,
        LocalDate.of(2026, 11, 25),
        Instant.parse("2026-11-25T09:30:00Z"),
        UUID.randomUUID()
);

OrderRow order = new OrderRow(
        key,
        "NEW",
        new BigDecimal("250000.00"),
        "Giao trong giờ hành chính"
);

template.insert(order);
~~~

Ví dụ giả định `OrderKey` và `OrderRow` có constructor như trên, và `template` là bean đã inject. Template sử dụng mapping để tạo câu lệnh tương ứng với dữ liệu entity. Về mặt khái niệm, câu CQL có dạng:

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day
    (customer_id, order_day, placed_at, order_id,
     status, total_amount, note)
VALUES (?, ?, ?, ?, ?, ?, ?);
~~~

Các dấu `?` đại diện tham số được bind từ entity; đừng ghép chuỗi từ dữ liệu người dùng vào CQL. Metadata có thể ảnh hưởng những cột nào thực sự xuất hiện trong statement, ví dụ property `@Transient` hoặc `@ReadOnlyProperty`.

### Chữ “insert” không bảo đảm hàng trước đó chưa tồn tại

Cassandra thông thường có **ngữ nghĩa upsert**:

- Nếu primary key **chưa có**, ghi tạo hàng tương ứng.
- Nếu primary key **đã có**, các giá trị được ghi vào những cột tương ứng của hàng đó theo ngữ nghĩa timestamp/last-write-wins.
- Ghi lại cùng primary key không tạo một bản ghi logic thứ hai với cùng khóa.
- Ghi thành công không tự bảo đảm “đây là lần tạo đầu tiên”.

Nếu nghiệp vụ cần điều kiện “chỉ tạo nếu chưa tồn tại”, CQL có **lightweight transaction (LWT)** như:

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day (
    customer_id, order_day, placed_at, order_id,
    status, total_amount
) VALUES (?, ?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Đây là một **conditional write** có chi phí và ngữ nghĩa khác ghi thông thường. Không coi `template.insert(entity)` mặc định tương đương `INSERT ... IF NOT EXISTS`; nếu cần LWT, dùng API có hỗ trợ điều kiện/statement rõ ràng và kiểm tra **applied result**. Việc chọn LWT phải dựa trên nhu cầu nghiệp vụ và hiệu năng thực tế.

### Retry và idempotency

Tạo `UUID.randomUUID()` mỗi lần retry của **cùng một đơn hàng** có thể tạo nhiều hàng vì primary key mới khác. Nên tạo mã đơn **một lần** khi tiếp nhận yêu cầu nghiệp vụ, lưu mã đó và dùng lại trong các lần retry. Dù câu ghi thông thường là upsert, tính idempotent của một workflow còn phụ thuộc các side effect bên ngoài và timestamp của các lần ghi đồng thời.

## 6. update: ghi lại entity theo khóa

Ví dụ đã đọc entity và muốn đổi trạng thái:

~~~java
OrderRow stored = template.selectOneById(key, OrderRow.class);

if (stored == null) {
    throw new IllegalArgumentException("Không tìm thấy đơn hàng");
}

stored.setStatus("PAID");
template.update(stored);
~~~

`template.update(stored)` dùng metadata của entity để xây thao tác ghi. **Cần hiểu rõ các cột mà phiên bản Spring Data cụ thể đưa vào statement**: ghi theo entity không mặc nhiên có nghĩa “chỉ cập nhật thuộc tính vừa thay đổi” như một *dirty checking* session của JPA. Các giá trị khác trong entity cũng có thể được đưa vào CQL, khiến ghi lên dữ liệu cũ hoặc ghi null gây hậu quả ngoài ý muốn tùy cơ chế mapping và statement.

### UPDATE trong Cassandra cũng thường là upsert

Một câu CQL đơn giản:

~~~sql
UPDATE commerce_ks.orders_by_customer_day
SET status = 'PAID'
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

thường không buộc Cassandra phải xác minh hàng đã tồn tại trước khi cập nhật. Nếu khóa đầy đủ hợp lệ mà hàng chưa có, Cassandra vẫn có thể tạo dữ liệu mới tương ứng với giá trị được ghi. Vì vậy:

- **`update(entity)` không nên được hiểu là SQL UPDATE có bảo đảm ảnh hưởng đúng một hàng đang tồn tại.**
- Thao tác `selectOneById` rồi `update` không tạo transaction nguyên tử: giữa hai lần gọi, writer khác có thể cập nhật hoặc xóa hàng.
- Khi cần điều kiện dựa trên trạng thái hiện tại, xem xét LWT như `IF status = 'NEW'` và đánh giá chi phí.

### Khi chỉ muốn thay một cột

Đọc entity đầy đủ rồi `update(entity)` có thể tạo ghi không cần thiết và làm tăng khả năng xung đột khi nhiều service cùng quản lý các cột khác nhau. Với yêu cầu “chỉ đổi `status`”, ưu tiên **partial update** có điều kiện khóa rõ ràng:

~~~sql
UPDATE commerce_ks.orders_by_customer_day
SET status = ?
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Có thể thực hiện bằng API update/query thích hợp của `CassandraTemplate` hoặc prepared statement của `CqlSession`. Chọn đúng method của phiên bản thư viện, và kiểm tra CQL thực tế thay vì giả định mọi thao tác `update(entity)` đều chỉ ghi một property.

Trong Cassandra, cột được gán `null`, xóa cột hoặc ghi TTL có thể dẫn tới tombstone. Cách Spring Data xử lý null khi sinh statement phụ thuộc API/option/version; nếu cần phân biệt **“bỏ qua cột”** với **“xóa cột”**, hãy chỉ rõ ý định trong thao tác ghi và thử nghiệm bằng CQL thực tế.

## 7. delete: xóa một hàng theo khóa của entity

Muốn xóa đúng một đơn hàng, ứng dụng cần biết **toàn bộ primary key**. Với entity chứa khóa đầy đủ:

~~~java
OrderRow stored = template.selectOneById(key, OrderRow.class);
if (stored != null) {
    template.delete(stored);
}
~~~

Ý nghĩa CQL tương ứng là xóa hàng theo khóa:

~~~sql
DELETE FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Không dùng một entity có khóa thiếu `placed_at` hoặc `order_id` rồi kỳ vọng xóa “đúng đơn gần nhất” theo logic ứng dụng. Partition key và clustering key phải khớp hàng cần xóa.

### DELETE tạo tombstone chứ không nhất thiết thu hồi đĩa ngay

Cassandra dùng **tombstone** để thể hiện việc xóa trong hệ thống phân tán. Việc dữ liệu hết xuất hiện ở truy vấn logic và việc không gian đĩa được thu hồi qua compaction là **hai thời điểm khác nhau**.

Ngoài ra:

- Câu `DELETE` thông thường không tự là phép kiểm tra “hàng có tồn tại hay không” trước khi xóa.
- Giá trị trả về hoặc việc không có exception từ template **không nên được diễn giải là bằng chứng hàng đã tồn tại trước đó**.
- Đọc trước khi xóa rồi mới xóa không phải thao tác nguyên tử; nếu nghiệp vụ yêu cầu điều kiện đồng thời, cần cơ chế điều kiện phù hợp.
- Xóa hàng loạt hoặc xóa một partition rộng có thể sinh nhiều tombstone và ảnh hưởng read latency; đừng thiết kế đường dữ liệu thường xuyên ghi/xóa khối lượng lớn mà không đo.

Nếu nghiệp vụ cần lưu dấu lịch sử, có thể phù hợp hơn với mô hình **soft delete** hoặc bảng sự kiện bất biến, thay vì xóa vật lý mọi thay đổi. Quyết định này phụ thuộc yêu cầu truy vấn, retention và tuân thủ dữ liệu.

## 8. select: đọc đúng một hàng theo primary key đầy đủ

`CassandraTemplate` hỗ trợ đọc một entity theo ID:

~~~java
OrderRow order = template.selectOneById(key, OrderRow.class);

if (order == null) {
    // Không tồn tại hàng tương ứng trong kết quả đọc hiện tại.
}
~~~

Ở ví dụ này, `key` là object `OrderKey` chứa đầy đủ `customerId`, `orderDay`, `placedAt` và `orderId`. Lệnh CQL về mặt logic:

~~~sql
SELECT customer_id, order_day, placed_at, order_id,
       status, total_amount, note
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Đối với bảng sử dụng **composite key**, việc chỉ có `orderId` không đủ để định tuyến đọc nếu khóa CQL còn gồm các cột khác. Nếu màn hình cần “tìm đơn theo `order_id` ở bất kỳ ngày nào”, cần một **đường truy cập riêng**, ví dụ bảng `order_by_id` được thiết kế cho truy vấn đó, thay vì lạm dụng `ALLOW FILTERING`.

### selectOneById khác repository.findById?

| API | Kiểu kết quả thường dùng | Cách hiểu khi không có hàng |
| --- | --- | --- |
| `template.selectOneById(key, OrderRow.class)` | `OrderRow` hoặc `null` | Kiểm tra `null` |
| `repository.findById(key)` | `Optional<OrderRow>` | Kiểm tra `Optional.empty()` |

Cả hai vẫn cần đúng primary key và tuân theo consistency level đang áp dụng. Việc đọc không tìm thấy hàng **không mặc định chứng minh dữ liệu chưa từng tồn tại**: có thể do xóa, TTL, sai khóa/bucket, hoặc các điều kiện nhất quán/đồng bộ của Cassandra.

## 9. select: đọc nhiều entity bằng Query

Một màn hình hiển thị các đơn gần nhất của **một khách hàng trong một ngày** không cần biết sẵn `placed_at` và `order_id` của từng hàng, nhưng phải xác định **đủ partition key**.

Ví dụ sử dụng query DSL của Spring Data Cassandra:

~~~java
Query query = Query.query(
        Criteria.where("customer_id").is(customerId)
    )
    .and(Criteria.where("order_day").is(orderDay))
    .limit(20);

List<OrderRow> orders = template.select(query, OrderRow.class);
~~~

Ý nghĩa CQL:

~~~sql
SELECT customer_id, order_day, placed_at, order_id,
       status, total_amount, note
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
LIMIT 20;
~~~

Ở schema ví dụ, các hàng trong partition được sắp theo `placed_at DESC, order_id DESC`. Kết quả có thể lấy những đơn gần nhất mà không cần `ORDER BY` bổ sung. Lưu ý chỉ có **thứ tự trong một partition**, không có thứ tự toàn cục giữa nhiều khách/ngày.

Ví dụ lọc trong một khoảng thời gian:

~~~sql
SELECT order_id, placed_at, status
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at >= ?
  AND placed_at < ?
LIMIT 20;
~~~

Khoảng thời gian nên thống nhất theo UTC và cách tính `order_day`. Một truy vấn vượt ranh giới ngày cần đi qua **nhiều partition ngày**, không tự được giải quyết bằng một `WHERE placed_at BETWEEN ...` bỏ qua partition key.

### Lưu ý về query DSL và tên cột

Các class như `Query` và `Criteria` nằm trong API query của Spring Data Cassandra. Khi dùng property Java đặt tên camelCase nhưng schema CQL đặt tên snake_case, cần bảo đảm query builder và mapping của phiên bản dự án hiểu đúng tên cột; có thể dựa trên mapping metadata hoặc viết CQL tường minh khi phù hợp. Kiểm tra câu CQL thực tế được tạo để tránh lỗi “unknown column” hoặc điều kiện sai khóa.

## 10. INSERT, UPDATE và DELETE khác nhau về bảo đảm thế nào?

| Thao tác | Khi khóa chưa tồn tại | Khi khóa đã tồn tại | Có tự xác minh tồn tại? |
| --- | --- | --- | --- |
| `template.insert(entity)` | Thường tạo dữ liệu hàng mới | Upsert những giá trị được ghi | **Không** mặc định |
| `template.update(entity)` | Thường có thể tạo dữ liệu cho khóa được ghi | Upsert/cập nhật các giá trị được ghi | **Không** mặc định |
| `template.delete(entity)` | Ghi thao tác xóa theo CQL; không phải “không làm gì” bảo đảm không tombstone | Xóa hàng/giá trị được chỉ định | **Không** mặc định |
| `template.selectOneById(...)` | Có thể trả `null` | Đọc một entity theo key | Là thao tác đọc, không khóa chặt các ghi tiếp theo |

Trong Cassandra, **upsert** là ngữ nghĩa quan trọng hơn cách đặt tên method ở tầng Java. Không mặc định có:

- Auto-increment/identity primary key như một số RDBMS.
- Foreign key, join hay transaction nhiều bảng theo cách SQL truyền thống.
- Dirty checking tự động chỉ ghi những field Java vừa đổi.
- Transaction nguyên tử bao trùm `select → update → delete`.
- `DELETE` có thể trả lời chắc chắn “trước khi xóa đã tồn tại một hàng”.

Nếu nghiệp vụ yêu cầu bảo đảm điều kiện, hãy xem xét **LWT** đúng chỗ. Nếu cần tính đúng đắn qua nhiều service, thiết kế idempotency, đồng bộ sự kiện và điều kiện cạnh tranh tại tầng nghiệp vụ; template không tự cung cấp các bảo đảm này.

## 11. Ngữ nghĩa null, TTL và mapping ảnh hưởng tới CRUD

### Null và thuộc tính không tham gia persistence

Một object Java có thể chứa field `null` vì chưa được load, vì ứng dụng không set, hoặc vì muốn xóa giá trị. Ba ý định này **không luôn tương đương**. Tùy API và cấu hình statement, null có thể được bỏ qua hoặc ghi theo cách tạo tombstone. Vì vậy với partial updates, nên dùng thao tác ghi rõ cột/ý nghĩa, tránh gửi toàn entity “thiếu dữ liệu” rồi vô tình ảnh hưởng cột khác.

Annotation:

- `@Transient`: property không được mapper xem là dữ liệu lưu trữ; không đọc/ghi tương ứng với một cột.
- `@ReadOnlyProperty`: property có thể được mapping khi đọc nhưng không được đưa vào mapped insert/update theo entity.

Hai annotation không tự thay đổi schema hay ngăn CQL viết tay truy cập cột.

### TTL và thời điểm dữ liệu hết hạn

Cassandra hỗ trợ TTL ở các thao tác ghi. Ví dụ CQL:

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day (
    customer_id, order_day, placed_at, order_id, status
) VALUES (?, ?, ?, ?, ?)
USING TTL 86400;
~~~

`86400` là **số giây** (một ngày); dữ liệu viết với TTL có thể hết hạn về mặt logic sau khoảng đó. Không suy ra rằng tất cả dữ liệu vật lý sẽ được thu hồi tức thì hoặc rằng những cột khác trong hàng đều có cùng TTL nếu được ghi riêng. Tùy nhu cầu, các API template có options cho thao tác ghi; cần xem signature của đúng Spring Data Cassandra version khi dùng options thay vì hard-code ví dụ này.

Các bản cập nhật cùng cell có thể thay đổi timestamp/TTL của giá trị; thiết kế retention cần được kiểm tra cẩn thận khi có nhiều writer.

## 12. Consistency, retry và khả năng chịu lỗi

Template gửi truy vấn thông qua Java Driver, còn Cassandra phân phối đọc/ghi đến các replica theo replication strategy và **consistency level (CL)**. Với keyspace RF = 3 trong một datacenter:

| CL ví dụ | Yêu cầu phản hồi theo datacenter cục bộ | Đánh đổi |
| --- | --- | --- |
| `ONE` | Một replica | Ít replica cần chờ, có thể đọc dữ liệu cũ trong một số tình huống |
| `LOCAL_QUORUM` | Hai trong ba replica cục bộ | Tăng yêu cầu phản hồi, cần đủ replica khả dụng |
| `ALL` | Tất cả replica phù hợp | Ít chịu được replica không sẵn sàng |

Đây là ví dụ đơn datacenter; chi tiết còn phụ thuộc topology và CL được dùng. Consistency level có thể được cấu hình ở driver hoặc theo statement bằng API phù hợp. Nó **không được quyết định** bởi `@Table` hay tên method `insert/update`.

Khi có timeout:

- Không mặc định “timeout = chắc chắn chưa ghi”. Yêu cầu có thể đã tới một số replica.
- Retry với khóa và giá trị ổn định thường dễ kiểm soát hơn retry với ID mới.
- Ghi có điều kiện (LWT), counter, list mutation và các side effect bên ngoài đòi đánh giá riêng về idempotency.
- Đừng tăng timeout hoặc retry vô hạn để che giấu partition nóng, tombstone hay cluster quá tải.

Ứng dụng nên có xử lý lỗi rõ ràng cho kết nối, xác thực, timeout, thiếu schema, mapping và dữ liệu đầu vào. Truyền nguyên stack trace hoặc CQL chứa dữ liệu nhạy cảm ra HTTP response là không phù hợp.

## 13. Paging khi select nhiều hàng

`LIMIT 20` giới hạn lượng dữ liệu của một truy vấn minh họa, nhưng **khác** với paging driver. Cassandra thường dùng **paging state** để đọc các phần của cùng một query nhiều lần.

Các điều cần nhớ:

1. **Page/fetch size** kiểm soát số hàng yêu cầu nhận theo mỗi lượt fetch, không phải cơ chế nhảy ngẫu nhiên tới offset rất lớn.
2. **Paging state** thuộc về query và tập tham số tương ứng; không dùng lại một cách tùy ý cho keyspace, điều kiện, thời điểm lọc khác.
3. Paging trong một partition theo clustering key không tạo snapshot bất biến khi các hàng vẫn tiếp tục được ghi/xóa.
4. Đọc nhiều ngày hoặc nhiều shard thường phải **quản lý nhiều partition và hợp nhất thứ tự**, không tự động được giải quyết bởi một request `select(query)`.
5. `List<OrderRow>` từ một lệnh `template.select(...)` có thể materialize nhiều hàng vào bộ nhớ; cần giới hạn kết quả/tiêu thụ theo trang khi dữ liệu lớn.

Với các API paging nâng cao, dùng cơ chế mà **Spring Data Cassandra và Java Driver đúng phiên bản** cung cấp. Không coi `PageRequest.of(100, 20)` như phép truy cập tức thì tới hàng thứ 2.001 trong Cassandra.

## 14. Khi nào nên dùng template thay cho repository?

| Nhu cầu | Lựa chọn khả thi | Giải thích |
| --- | --- | --- |
| CRUD đơn giản theo full primary key | Repository hoặc `CassandraTemplate` | Cả hai khai thác entity mapping |
| Cần nhiều query có điều kiện và giới hạn khác nhau | `CassandraTemplate` với `Query` | Chủ động xây truy vấn theo mô hình partition/clustering |
| Cần partial update một vài cột | Template update API hoặc CQL statement có bind | Tránh cập nhật nguyên entity ngoài ý muốn |
| Cần conditional write, custom timestamp/TTL, lệnh CQL đặc thù | API hỗ trợ statement/options hoặc `CqlSession` | Kiểm soát rõ ngữ nghĩa ghi và kết quả |
| Ứng dụng đã dùng WebFlux nonblocking | `ReactiveCassandraTemplate` | Dùng pipeline `Mono`/`Flux`, không chặn event-loop bằng template đồng bộ |
| Cần báo cáo quét nhiều tenant/toàn hệ thống | Thiết kế bảng đọc khác hoặc hệ thống phân tích | Template không sửa được data model không phù hợp |

Không nên chuyển toàn bộ sang CQL viết tay chỉ vì template cho phép linh hoạt hơn repository; đồng thời đừng ép mọi thao tác vào entity CRUD nếu cần một câu update theo đúng cột hoặc điều kiện LWT.

## 15. Checklist thực hành và những lỗi phổ biến

Trước khi đưa một thao tác CRUD vào production:

- [ ] Entity khớp với schema: tên bảng, tên cột, kiểu Java–CQL và primary key.
- [ ] Mọi thao tác theo một hàng có **đầy đủ primary key**, không nhầm partition key với clustering key.
- [ ] Đã xác định idempotency và hành vi khi retry/timeout.
- [ ] Đã biết `insert`/`update` là upsert thông thường, không mặc định xác minh tồn tại.
- [ ] Đã kiểm tra cột nào được đưa vào mapped update, cách xử lý null và read-only property.
- [ ] `delete` có chính sách rõ ràng cho tombstone, retention và yêu cầu xóa.
- [ ] Truy vấn danh sách cung cấp đủ partition key; có `LIMIT` và paging phù hợp.
- [ ] CL/timeout được chọn từ yêu cầu nghiệp vụ và điều kiện replica, không chỉ từ tên method.
- [ ] Có kiểm thử trên schema, phiên bản Spring Data và driver thực tế.

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Insert lần hai làm thay đổi dữ liệu cũ | Cùng primary key → upsert | Kiểm tra ID, dùng conditional insert nếu nghiệp vụ yêu cầu |
| Update “thành công” dù chưa có hàng | Cassandra UPDATE có thể upsert | Không suy luận từ thành công ghi là hàng tồn tại |
| Save/update ghi đè cột khác | Mapped write có thể bao gồm nhiều property | Dùng partial update/CQL rõ ràng, kiểm tra statement |
| Select theo order_id không có kết quả | Bảng cần nhiều cột khóa khác | Truy vấn full key hoặc tạo bảng theo order_id |
| Query chậm dù dùng template | Partition quá lớn, tombstone, thiếu partition key | Thiết kế lại access pattern, theo dõi metrics |
| Delete xong disk chưa giảm | Tombstone và compaction | Không kỳ vọng thu hồi dung lượng tức thì |
| Không thấy dữ liệu vừa ghi | Key/bucket sai, CL, TTL, ghi/xóa đồng thời | Kiểm tra giá trị CQL, schema, CL và timestamp |

## 16. Tự kiểm tra

**Câu 1.** `template.insert(order)` được gọi hai lần với cùng primary key. Có chắc Cassandra có hai hàng đơn hàng khác nhau không?

**Đáp án:** Không. Cassandra định danh hàng bằng primary key; ghi bình thường có ngữ nghĩa upsert. Muốn chắc chắn chỉ tạo một lần theo điều kiện, cần chiến lược khóa ổn định và có thể cần conditional write.

**Câu 2.** Vì sao dùng `template.update(order)` không nên mặc định xem là “chỉ cập nhật status vừa thay đổi”?

**Đáp án:** Spring Data không cung cấp dirty checking như persistence context JPA cho mọi field. Mapped update có thể ghi nhiều thuộc tính theo statement được sinh; cần kiểm tra phiên bản/API và dùng partial update nếu muốn thay đúng một cột.

**Câu 3.** `template.selectOneById(key, OrderRow.class)` cần những giá trị nào?

**Đáp án:** Toàn bộ `customer_id`, `order_day`, `placed_at` và `order_id`, vì đó là primary key của hàng.

**Câu 4.** Gọi `template.delete(order)` trả kết quả thành công. Có thể kết luận chắc chắn hàng tồn tại trước đó không?

**Đáp án:** Không. Lệnh DELETE thông thường không phải điều kiện kiểm tra tồn tại và Cassandra sử dụng tombstone; cần mô hình nghiệp vụ hoặc điều kiện rõ ràng nếu phải chứng minh tồn tại trước khi xóa.

**Câu 5.** Để liệt kê 20 đơn gần nhất của một khách trong ngày, phải cung cấp điều kiện gì?

**Đáp án:** Đủ composite partition key `customer_id` và `order_day`; dữ liệu trong partition đã có thứ tự clustering `placed_at DESC, order_id DESC`. Dùng query có `LIMIT 20`, đồng thời cân nhắc paging nếu kết quả lớn hơn.

---

**Ghi nhớ:** `CassandraTemplate` giúp thao tác **insert, update, delete, select theo entity** thuận tiện, nhưng **không thay đổi ngữ nghĩa Cassandra**: insert/update thường là upsert, delete tạo tombstone, đọc một hàng cần đúng primary key, đọc danh sách cần thiết kế theo partition/clustering, và tính nhất quán phụ thuộc replica/CL. Dùng entity mapping khi thích hợp, partial CQL khi cần kiểm soát một cột hoặc điều kiện, và luôn kiểm thử với schema/driver thực tế trước khi triển khai.
