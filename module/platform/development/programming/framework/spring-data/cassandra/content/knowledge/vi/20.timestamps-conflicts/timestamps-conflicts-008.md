# Thử lại cùng một thao tác và giữ ngữ nghĩa cập nhật

Trong **Apache Cassandra**, một yêu cầu ghi có thể đã được một hoặc nhiều replica xử lý dù ứng dụng nhận **timeout** hoặc mất kết nối trước khi thấy phản hồi. Vì vậy, khi sử dụng **Spring Data Cassandra**, câu hỏi quan trọng không chỉ là *“có nên thử lại?”* mà còn là *“lặp lại thao tác đó có giữ nguyên kết quả nghiệp vụ không?”*.

Một câu `INSERT` với **primary key ổn định** và dữ liệu không đổi có thể được thiết kế để retry an toàn. Ngược lại, tăng counter, nối phần tử vào list, cập nhật trạng thái dựa trên giá trị đã đọc hoặc tạo ID mới mỗi lần retry có thể dẫn đến **đếm hai lần, tạo bản ghi trùng, mất cập nhật hoặc làm sống lại dữ liệu đã xóa**. Cassandra còn phân giải xung đột bằng **write timestamp theo cell**, không nhất thiết theo thứ tự request được gửi hoặc được ứng dụng nhận phản hồi.

Bài thuộc chương **Timestamp và xung đột** của module **SPRING_DATA_CASSANDRA**, tập trung vào cách giữ **ngữ nghĩa cập nhật** khi có retry, timeout và nhiều writer. Ta sẽ thực hành với entity mapping, repository, `CassandraTemplate`, CQL, prepared statement, điều kiện LWT, TTL và chính sách kiểm thử theo mô hình dữ liệu phân tán.

## 1. Timeout nghĩa là kết quả chưa biết, không phải chưa ghi

Giả sử API nhận lệnh xác nhận thanh toán đơn hàng:

~~~text
Client                  Coordinator               Replica A, B, C
  |                          |                          |
  | --- UPDATE status ------>|                          |
  |                          |---- mutation ----------->|
  |                          |<--- A đã xác nhận --------|
  |                          |<--- B phản hồi chậm ------|
  |                          |                          |
  |<----- TIMEOUT -----------|                          |
  |                          |                          |
  |     Client không thể kết luận chắc có ghi hay chưa.   |
~~~

Ví dụ keyspace có replication factor **RF=3** và thao tác dùng `LOCAL_QUORUM`, cần hai phản hồi phù hợp ở datacenter cục bộ. Nếu client hết thời gian chờ, một số replica có thể đã áp dụng mutation. Phản hồi cũng có thể bị mất **sau khi** coordinator hoàn thành công việc.

Do đó:

- **Thành công** nghĩa là thao tác được xác nhận theo consistency level yêu cầu; không phải mọi replica đã đồng bộ tức thời.
- **Timeout** nghĩa là ứng dụng **không nhận đủ xác nhận đúng hạn**; không chứng minh thao tác không xảy ra.
- **Retry** có thể khiến **cùng một lệnh được thực thi nhiều lần**. Nếu lệnh không idempotent, kết quả có thể khác hẳn thực thi một lần.

Khi thiết kế API, nên xem kết quả timeout của ghi là **không chắc chắn (ambiguous outcome)**. Chỉ trả “chắc chắn thất bại và chưa ghi” nếu thực sự có bằng chứng phù hợp từ loại lỗi và quy trình nghiệp vụ.

## 2. Chuẩn bị một bảng có primary key xác định rõ

Giả sử nghiệp vụ truy vấn các đơn hàng theo khách hàng và ngày đặt:

~~~sql
CREATE KEYSPACE IF NOT EXISTS commerce_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS commerce_ks.orders_by_customer_day (
    customer_id      uuid,
    order_day        date,
    placed_at        timestamp,
    order_id         uuid,
    status           text,
    total_amount     decimal,
    last_request_id  uuid,
    PRIMARY KEY ((customer_id, order_day), placed_at, order_id)
) WITH CLUSTERING ORDER BY (
    placed_at DESC, order_id DESC
);
~~~

Trong bảng:

| Thành phần | Vai trò |
| --- | --- |
| `(customer_id, order_day)` | **Composite partition key**, xác định partition và nhóm replica |
| `placed_at`, `order_id` | **Clustering columns** xác định hàng cụ thể và thứ tự trong partition |
| `status` | Trạng thái nghiệp vụ cần cập nhật |
| `total_amount` | Số tiền lưu trong cột CQL `decimal` |
| `last_request_id` | Dấu vết của request vừa cập nhật hàng; hỗ trợ phân tích retry, nhưng **không tự bảo đảm exactly-once** |

Tên datacenter `dc1` và RF=3 chỉ minh họa; phải có topology/replica phù hợp. Ở production, quản lý keyspace/table bằng quy trình schema migration được kiểm soát.

**Điểm quan trọng:** primary key đầy đủ là **bốn** giá trị. Nếu retry làm thay `order_id` hoặc `placed_at` thì Cassandra có thể ghi sang **một hàng khác**, dù payload nghiệp vụ trông giống nhau. Nếu cần tra cứu đơn chỉ theo `order_id`, thiết kế thêm bảng đọc tương ứng thay vì quét thiếu partition key.

## 3. Upsert theo khóa: tính idempotent phải được thiết kế

Trong Cassandra, `INSERT` và `UPDATE` thông thường mang ngữ nghĩa **upsert**: ghi các giá trị được cung cấp vào hàng có primary key tương ứng, bất kể hàng đã tồn tại hay chưa.

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day (
    customer_id, order_day, placed_at, order_id,
    status, total_amount, last_request_id
) VALUES (?, ?, ?, ?, ?, ?, ?);
~~~

Ghi hai lần **cùng primary key, cùng giá trị** thường không tạo hai hàng logic. Nhưng phải phân biệt:

~~~text
Retry A (đúng):
  order_id = UUID-123, placed_at = T1, amount = 250000
  order_id = UUID-123, placed_at = T1, amount = 250000
  => vẫn nhắm cùng một hàng

Retry B (sai):
  lần 1: order_id = UUID-123, placed_at = T1
  lần 2: order_id = UUID-999, placed_at = T2
  => nhắm hai primary key khác nhau
~~~

**Nguyên tắc thiết kế:** tạo `order_id`, `placed_at`, `order_day` và dữ liệu nghiệp vụ **một lần ở ranh giới nhận lệnh**, sau đó dùng lại đúng các giá trị đó cho mọi lần retry của **cùng một thao tác**.

Chỉ có “cùng primary key” chưa đủ để mọi thao tác idempotent: câu cập nhật có thể tăng counter, thay đổi collection, gán TTL mới hoặc sử dụng một giá trị thay đổi theo từng lần gọi. Cần xem **toàn bộ ngữ nghĩa CQL**.

## 4. Phân biệt idempotent, at-least-once và exactly-once

Một thao tác là **idempotent** nếu thực hiện nó nhiều lần với cùng đầu vào dẫn tới **trạng thái logic mong muốn như thực hiện một lần**, trong các giả định tương ứng.

| Khái niệm | Ý nghĩa thực tế |
| --- | --- |
| **At-most-once attempt** | Tránh tự động thử lại; khi timeout có thể không biết kết quả và bỏ lỡ công việc |
| **At-least-once processing** | Có thể xử lý cùng lệnh hơn một lần để tránh mất việc |
| **Idempotent operation** | Lặp lại cùng lệnh được thiết kế không tạo tác dụng phụ logic ngoài ý muốn |
| **Exactly-once business effect** | Mỗi thao tác nghiệp vụ chỉ tạo một hiệu ứng; thường cần idempotency key, lưu trạng thái, kiểm soát đồng thời và reconciliation |

**Ghi idempotent không tự biến cả workflow thành exactly-once.** Ví dụ lưu đơn vào Cassandra có thể an toàn khi retry, nhưng việc gửi email, gọi cổng thanh toán hoặc phát sự kiện đến hệ thống khác vẫn có thể lặp nếu không có cơ chế riêng.

Một API có thể chấp nhận at-least-once delivery, rồi dùng **request ID ổn định** và điều kiện lưu trạng thái để đạt **hiệu ứng nghiệp vụ không bị lặp**. Cần định nghĩa rõ phạm vi của bảo đảm, thay vì chỉ đánh dấu `setIdempotent(true)` cho statement.

## 5. Write timestamp quyết định thắng/thua, không phải request đến sau

Cassandra giải quyết xung đột ghi bằng **write timestamp theo cell**. Đối với hai giá trị cạnh tranh trên cùng một cell, timestamp lớn hơn thường được ưu tiên; khi bằng timestamp có quy tắc tie-break riêng. Không nên dựa vào tie-break để quyết định thứ tự nghiệp vụ.

Ví dụ:

~~~text
Tại cell status của cùng một hàng:

Writer A: status='PAID',       write timestamp = 1_000_000
Writer B: status='CANCELLED',  write timestamp = 1_000_010

Cho dù A đến coordinator sau B, giá trị của B có thể thắng
vì write timestamp của B cao hơn.
~~~

Để chỉ định write timestamp tường minh:

~~~sql
UPDATE commerce_ks.orders_by_customer_day
USING TIMESTAMP ?
SET status = ?
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

**Đơn vị của `USING TIMESTAMP` là micro giây** từ Unix epoch. Không nhầm với cột `placed_at timestamp`, vốn mô tả thời gian nghiệp vụ và có kiểu CQL `timestamp`. Không truyền trực tiếp `System.currentTimeMillis()` vào `USING TIMESTAMP` mà tưởng là micro giây.

Với nhiều writer:

- **Timestamp cao bất thường** trong tương lai có thể khiến những ghi hợp lệ tiếp theo bị thua.
- **Đồng hồ lệch** giữa các ứng dụng có thể làm thứ tự ghi khác thứ tự thao tác nghiệp vụ.
- **Timestamp giống nhau với giá trị khác nhau** là tình huống không nên chủ động tạo ra.
- Việc một retry dùng timestamp mới có thể làm nó cạnh tranh với các cập nhật khác như **một ghi mới**, thay vì chỉ lặp lại lần trước.

Thông thường nên để cơ chế timestamp của driver/Cassandra theo cấu hình đã chuẩn hóa đảm nhiệm. Chỉ tự gán timestamp khi có yêu cầu cụ thể và hiểu hệ quả.

## 6. Retry một ghi gán giá trị với timestamp cố định

Giả sử ứng dụng cần ghi đơn hàng lần đầu và muốn giữ **cùng write timestamp** nếu lệnh được gửi lại. Có thể chuẩn bị CQL như sau:

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day (
    customer_id, order_day, placed_at, order_id,
    status, total_amount, last_request_id
) VALUES (?, ?, ?, ?, ?, ?, ?)
USING TIMESTAMP ?;
~~~

Ví dụ Java Driver 4.x, chỉ minh họa một lệnh đã được xây dựng từ trước:

~~~java
PreparedStatement prepared = session.prepare("""
    INSERT INTO commerce_ks.orders_by_customer_day (
      customer_id, order_day, placed_at, order_id,
      status, total_amount, last_request_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    USING TIMESTAMP ?
    """);

// Các giá trị được tạo/chốt MỘT LẦN cho cùng business command.
UUID orderId = command.orderId();
Instant placedAt = command.placedAt();
LocalDate orderDay = placedAt.atZone(ZoneOffset.UTC).toLocalDate();
long writeTimestampMicros = command.writeTimestampMicros();

BoundStatement statement = prepared.bind(
    command.customerId(), orderDay, placedAt, orderId,
    "NEW", command.totalAmount(), command.requestId(),
    writeTimestampMicros
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setIdempotent(true);

session.execute(statement);
~~~

Đoạn mã giả định có `command` chứa dữ liệu đã được kiểm tra và có `CqlSession session` được Spring quản lý. Cần import Java types và driver classes; đây là ví dụ **cách bind và tái sử dụng một command** chứ không phải API controller hoàn chỉnh.

**Điều kiện để đánh dấu idempotent:** câu ghi này gán các giá trị đã chốt vào **cùng các cell**, không tăng số đếm, không nối list, không tự sinh khóa, không gán TTL thay đổi, và không kích hoạt side effect nghiệp vụ bên ngoài trong đường retry. Nếu điều kiện thay đổi, phải đánh giá lại.

Giữ timestamp cố định có thể giảm việc retry cũ ghi với timestamp mới hơn một thao tác khác. Nhưng nó **không bảo đảm** exactly-once hay tránh tất cả xung đột: một writer khác có thể sử dụng timestamp bằng/cao hơn, hoặc sửa những cell khác. Với yêu cầu tuần tự nghiệp vụ, cần mô hình trạng thái/điều kiện mạnh hơn.

## 7. Tạo microsecond timestamp đúng đơn vị

Khi nghiệp vụ thực sự yêu cầu tự chỉ định write timestamp, không lấy nhầm mili giây:

~~~java
import java.time.Instant;

public final class Timestamps {
    private Timestamps() {}

    public static long toMicros(Instant instant) {
        return Math.addExact(
            Math.multiplyExact(instant.getEpochSecond(), 1_000_000L),
            instant.getNano() / 1_000L
        );
    }
}
~~~

Ví dụ:

~~~java
Instant commandAcceptedAt = Instant.now();
long micros = Timestamps.toMicros(commandAcceptedAt);

// Lưu micros cùng thông tin command để dùng lại khi retry.
~~~

Không gọi lại `Instant.now()` **trong từng lần retry** nếu yêu cầu là giữ nguyên write timestamp của cùng lệnh. Phải phân biệt:

| Thời gian | Dùng để làm gì? |
| --- | --- |
| `placed_at` | Thời điểm đặt đơn trong primary key, phục vụ truy vấn |
| `commandAcceptedAt` | Mốc tiếp nhận thao tác nghiệp vụ |
| `writeTimestampMicros` | Thứ tự ưu tiên của mutation Cassandra khi có cạnh tranh |
| `expiresAt` | Deadline retention nếu có TTL |

Không nên lấy thời điểm sự kiện cũ (event time) để làm write timestamp một cách máy móc: sự kiện đến muộn có thể bị ghi với timestamp thấp và **thua** cập nhật đã có.

## 8. Cùng thao tác nhưng retry với timestamp mới có thể phá trạng thái

Giả sử đơn hàng chuyển từ `NEW` sang `PAID`, sau đó một tác vụ khác hủy đơn theo quy tắc nghiệp vụ. Timeline:

~~~text
T1: Request A viết status='PAID'       (write ts=100)
T2: Request A bị timeout, không biết kết quả
T3: Request B viết status='CANCELLED'  (write ts=110)
T4: Request A retry, tự cấp ts=120

Theo last-write-wins, PAID(ts=120) có thể đè CANCELLED(ts=110).
~~~

Nếu A dùng lại timestamp 100, retry của A **không nên thắng** một trạng thái có timestamp 110 đã lưu. Tuy nhiên đây chỉ là ví dụ về quy tắc timestamp, chưa chứng minh nghiệp vụ thanh toán/hủy đã được tuần tự hóa chính xác.

**Giải pháp mạnh hơn:** mô hình hóa state transition, định nghĩa những chuyển trạng thái hợp lệ và dùng **conditional update/LWT** khi cần bảo đảm điều kiện. Timestamp không tự hiểu ý nghĩa `PAID` hay `CANCELLED`.

## 9. Read-modify-write thông thường dễ mất cập nhật

Giả sử hai instance cùng đọc một entity:

~~~text
Ban đầu: status=NEW, total_amount=250000

Service A đọc entity, đổi status=PAID.
Service B đọc entity, đổi total_amount=260000.

Nếu cả A và B đều ghi lại TOÀN BỘ entity, một bản ghi
có thể gửi giá trị cũ của cột mà service kia vừa đổi.
~~~

Trong Spring Data Cassandra, `repository.save(entity)` hoặc `CassandraTemplate.update(entity)` **không nên mặc định được hiểu là dirty checking chỉ ghi trường vừa thay đổi như một persistence context JPA**. Mapped statement có thể đưa nhiều property vào mutation, tùy API/version. Nếu entity được đọc từ snapshot cũ, một số cột có thể bị ghi đè.

Khi chỉ muốn cập nhật một cột, dùng CQL tường minh:

~~~sql
UPDATE commerce_ks.orders_by_customer_day
SET status = ?
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Điều này giảm phạm vi cell bị ghi, **nhưng không tạo compare-and-set** và không ngăn hai writer cùng sửa `status`. Khi một giá trị cần được bảo vệ bởi trạng thái cũ, dùng điều kiện LWT.

## 10. Các thao tác không idempotent: counter và list

Không phải tên method `update` hay việc có primary key ổn định là đủ để cho phép retry.

### Counter

Ví dụ bảng đếm:

~~~sql
CREATE TABLE commerce_ks.page_views_by_day (
    page_id text,
    view_day date,
    views counter,
    PRIMARY KEY (page_id, view_day)
);

UPDATE commerce_ks.page_views_by_day
SET views = views + 1
WHERE page_id = ? AND view_day = ?;
~~~

Nếu lần thứ nhất đã thành công nhưng client timeout rồi retry, counter có thể tăng **hai lần**. Không đánh dấu câu counter increment là idempotent, và không tự thử lại một cách mù quáng. Counter trong Cassandra có các hạn chế riêng, không được áp dụng `USING TTL` hoặc `USING TIMESTAMP` như cập nhật cột thường.

### List append

~~~sql
CREATE TABLE commerce_ks.user_notifications (
    user_id uuid PRIMARY KEY,
    recent_messages list<text>
);

UPDATE commerce_ks.user_notifications
SET recent_messages = recent_messages + ['payment-ok']
WHERE user_id = ?;
~~~

Retry lệnh append có thể tạo **hai phần tử giống nhau**. List có thứ tự không phù hợp làm event log phát triển không giới hạn, nhất là khi cần paging và cập nhật đồng thời. Nếu muốn lưu thông báo/sự kiện, nên cân nhắc **bảng nhiều hàng** với event ID ổn định và clustering key theo truy vấn.

### Nhìn nhanh một số thao tác

| Thao tác | Retry cùng input có an toàn mặc định? | Ghi chú |
| --- | --- | --- |
| Gán giá trị scalar cố định vào cùng cell | Thường có thể thiết kế an toàn | Xét timestamp, TTL, concurrent write |
| `INSERT` cùng khóa và cùng dữ liệu không TTL | Thường có thể thiết kế an toàn | Không tạo hàng trùng theo cùng primary key |
| `counter = counter + 1` | **Không** | Có thể tăng nhiều lần |
| `list = list + [...]` | **Không** | Có thể nối trùng phần tử |
| Thêm phần tử vào `set` | Tùy semantics và ghi/xóa đồng thời | Không suy ra exactly-once workflow |
| `DELETE` cùng khóa | Tùy timestamp/race | Retry với tombstone mới có thể ảnh hưởng ghi sau đó |
| LWT `IF ...` | Cần kiểm tra kết quả | Retry có thể nhận `applied=false` sau lần đầu đã thành công |

Khi không chắc thao tác là idempotent, **đừng khai báo `setIdempotent(true)` chỉ để driver retry nhiều hơn**.

## 11. TTL khiến cùng câu ghi không còn cùng deadline

TTL là **thời gian sống** của cell được ghi, tính bằng giây:

~~~sql
INSERT INTO commerce_ks.orders_by_customer_day (
    customer_id, order_day, placed_at, order_id, status
) VALUES (?, ?, ?, ?, ?)
USING TTL 86400;
~~~

Nếu một lệnh được thực hiện lại sau 30 phút, việc dùng lại `USING TTL 86400` có thể làm **deadline hết hạn thực tế khác với lần đầu**, tùy thời điểm ghi được áp dụng, timestamp và cơ chế xử lý TTL của Cassandra. Không mặc định rằng replay với TTL bằng nhau mang ý nghĩa giữ dữ liệu đến **đúng cùng một thời điểm**.

Ví dụ nghiệp vụ “giữ trạng thái đến hết ngày UTC” nên tính deadline từ một mốc tuyệt đối:

~~~text
deadline = 2026-11-26T00:00:00Z
Lần ghi A: TTL tính từ thời gian còn lại tới deadline.
Lần retry B: tính lại hoặc quyết định không ghi nếu đã hết hạn.
~~~

Mỗi cách có rủi ro riêng khi retry ghi vào cùng cell và đụng độ timestamp của writer khác. Nếu retention phải chính xác theo event time hoặc xử lý replay đến muộn, hãy **định nghĩa riêng chính sách deadline**, so sánh với thời gian hiện tại và kiểm thử hành vi cluster/driver version; không chỉ cố định con số TTL rồi tuyên bố thao tác idempotent.

**TTL theo cell, không theo entity.** Ghi lại riêng `status` không mặc nhiên gia hạn `total_amount`. Khi TTL hết hạn, Cassandra sử dụng tombstone và compaction theo cơ chế của hệ thống, không thu hồi dung lượng vật lý tức thì.

## 12. DELETE, tombstone và nguy cơ làm mất bản ghi mới

Xóa cũng tham gia phân giải theo timestamp:

~~~sql
DELETE FROM commerce_ks.orders_by_customer_day
USING TIMESTAMP ?
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

Giả sử:

~~~text
T1: DELETE một hàng (tombstone ts=100)
T2: Writer khác ghi lại hàng hợp lệ (write ts=110)
T3: Retry DELETE cũ nhưng tự sinh ts=120
~~~

Lần retry ở T3 có thể **xóa cả dữ liệu mới hơn về mặt nghiệp vụ**, vì tombstone mới có timestamp cao hơn ghi tại T2. Nếu cố định delete timestamp theo command ban đầu, có thể tránh một số trường hợp xóa vượt qua ghi mới có timestamp lớn hơn.

Nhưng cùng timestamp không phải **phương án đồng bộ nghiệp vụ toàn diện**: Cassandra còn có các quy tắc xóa/tie-breaking và việc xử lý ghi đồng thời. Nếu nghiệp vụ yêu cầu “chỉ xóa phiên bản X nếu vẫn còn hiện tại”, dùng điều kiện hoặc mô hình trạng thái thích hợp, thay vì chỉ retry DELETE với timestamp mới.

Một trường hợp tương tự là **upsert hồi sinh hàng đã xóa**: nếu replay của một INSERT cũ mang write timestamp mới hơn tombstone hiện có, một số dữ liệu có thể xuất hiện trở lại. Đây là lý do cần quản lý vòng đời command và thứ tự cập nhật.

## 13. Conditional update/LWT cho chuyển trạng thái

Với quy tắc “chỉ đổi đơn từ `NEW` sang `PAID` khi trạng thái hiện tại còn là `NEW`”, dùng **lightweight transaction (LWT)**:

~~~sql
UPDATE commerce_ks.orders_by_customer_day
SET status = 'PAID',
    last_request_id = ?
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?
IF status = 'NEW';
~~~

LWT kiểm tra điều kiện và quyết định áp dụng mutation bằng cơ chế đồng thuận. Nó phù hợp hơn việc:

~~~text
SELECT status
if (status == NEW) UPDATE status=PAID
~~~

bởi hai lệnh đọc và ghi riêng không tạo **compare-and-set nguyên tử** dù dùng `LOCAL_QUORUM` cho cả hai.

### Thực thi bằng Java Driver

~~~java
PreparedStatement conditional = session.prepare("""
    UPDATE commerce_ks.orders_by_customer_day
    SET status = 'PAID', last_request_id = ?
    WHERE customer_id = ? AND order_day = ?
      AND placed_at = ? AND order_id = ?
    IF status = 'NEW'
    """);

BoundStatement statement = conditional.bind(
    requestId, customerId, orderDay, placedAt, orderId
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
 .setIdempotent(false);

ResultSet result = session.execute(statement);
Row row = result.one();
boolean applied = row != null && row.getBoolean("[applied]");
~~~

Đây là minh họa Java Driver 4.x; cần import `PreparedStatement`, `BoundStatement`, `Row`, `ResultSet` và khai báo các biến đầu vào. `LOCAL_SERIAL` phải được chọn theo yêu cầu đồng thuận trong topology/phiên bản Cassandra thực tế.

Nếu `applied=true`, điều kiện đã được thỏa mãn tại lần thực thi đó. Nếu `applied=false`, trạng thái có thể đã đổi bởi chính lệnh của bạn trước đó hoặc bởi một request khác. **Không suy ra “lần trước chắc chắn chưa thành công” chỉ từ `applied=false` sau retry.**

**LWT có chi phí và giới hạn riêng**; không bật cho mọi ghi nếu không cần compare-and-set. LWT không tự biến cập nhật nhiều bảng và gọi dịch vụ ngoài thành một transaction ACID chung.

## 14. Xử lý `applied=false` sau khi kết quả trước không chắc chắn

Giả sử lần đầu của cùng `requestId` đã hoàn tất nhưng phản hồi bị mất:

~~~text
Lần A:
  status NEW -> PAID, last_request_id=R1, applied=true
  phản hồi bị mất ở client

Lần B (retry):
  IF status = NEW không còn đúng
  applied=false
~~~

Trong tình huống này, `applied=false` **không có nghĩa thanh toán thất bại**. Service có thể đọc lại hàng và xem trạng thái cùng request ID:

- Nếu `status=PAID` và `last_request_id=R1`, có bằng chứng phù hợp rằng request này đã được áp dụng trong trạng thái quan sát được.
- Nếu `status=PAID` nhưng `last_request_id=R2`, có thể là writer khác; không nhận vơ kết quả cho R1.
- Nếu trạng thái chuyển sang giá trị khác, cần áp dụng **state machine nghiệp vụ** hoặc tra ledger/idempotency record để biết lịch sử thực.
- Nếu đọc không thấy hàng do TTL, delete hoặc sai partition, không kết luận về lần ghi cũ mà chưa kiểm tra điều kiện liên quan.

Ngay cả khi đọc lại thấy `R1`, một writer sau đó có thể thay đổi hàng. Nếu nghiệp vụ cần một bằng chứng bền vững cho từng command, hãy duy trì **bản ghi kết quả theo request ID** có chính sách lưu giữ, thay vì chỉ dựa vào `last_request_id` có thể bị ghi đè.

## 15. Idempotency key ở API: ngăn gửi hai lần một nghiệp vụ

Một API HTTP có thể nhận một khóa idempotency do client tạo:

~~~http
POST /v1/orders/confirm-payment
Idempotency-Key: 9c53e4bc-9cbe-4f34-8a2e-ff1e64d117ae
Content-Type: application/json

{
  "orderId": "761663ef-12a4-42a3-b596-1fe3e39e1994",
  "expectedStatus": "NEW"
}
~~~

Khóa idempotency cần được **ràng buộc với tenant/identity, loại thao tác và hash nội dung request đã chuẩn hóa**. Nếu client tái sử dụng cùng key nhưng gửi payload khác, server phải từ chối theo hợp đồng API, không lặng lẽ coi là một lần retry hợp lệ.

Luồng khái niệm:

~~~text
1. Xác thực request, lấy tenant và request ID.
2. Kiểm tra idempotency key đã biết và fingerprint payload.
3. Nếu đã hoàn tất cùng payload, trả lại kết quả đã ghi nhận.
4. Nếu chưa biết, thực hiện transition có điều kiện.
5. Lưu kết quả theo một chiến lược bền vững.
6. Nếu timeout/unknown, đưa vào trạng thái cần tra cứu/reconcile.
~~~

**Không dùng một bảng dedup riêng rồi mặc định hai lần ghi vào hai bảng Cassandra là transaction nguyên tử.** Giả sử bảng `requests_by_id` có bản ghi `PROCESSING` nhưng thao tác cập nhật đơn thất bại, hoặc đơn đã cập nhật nhưng ghi kết quả vào bảng dedup chưa thành công: workflow vẫn có **khoảng trống cần phục hồi**.

Các phương án thực tế gồm đặt marker/điều kiện trong cùng hàng khi phù hợp, dùng LWT, state machine có trạng thái trung gian, ledger theo request, timeout/reconciliation hoặc outbox/event-driven workflow với bảo đảm rõ ràng. Mục tiêu là **hiệu ứng nghiệp vụ có thể kiểm chứng**, không phải chỉ có một câu INSERT riêng cho “dedup”.

## 16. Cách chọn retry policy cho driver và service

Java Driver có cơ chế retry policy, timeout và cờ `idempotent` để quyết định một số trường hợp có thể thử lại. **Đánh dấu idempotent là một thông tin về tính an toàn của thao tác**, không phải mệnh lệnh “retry vô hạn” hay bảo đảm không có duplicate.

Ví dụ với một câu gán giá trị ổn định:

~~~java
BoundStatement insert = preparedInsert.bind(
    customerId, orderDay, placedAt, orderId,
    "NEW", amount, requestId, fixedWriteTimestampMicros
).setIdempotent(true)
 .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(insert);
~~~

Với counter/list append, hoặc workflow có điều kiện phức tạp, không bật cờ đó tùy tiện. Khi không biết chính xác ngữ nghĩa retry của driver version, **xác minh policy và metrics thật**, không suy từ tên class.

### Các tầng retry cần phối hợp

| Tầng | Có thể retry gì? | Nguy cơ |
| --- | --- | --- |
| Java Driver | Một statement theo retry policy, timeout, idempotency | Trùng mutation nếu khai báo sai idempotent |
| Spring service | Một lời gọi repository/template/driver | Dùng input, ID hoặc timestamp khác lần trước |
| HTTP gateway/client | Toàn bộ request nghiệp vụ | Lặp cả DB write và side effect bên ngoài |
| Queue consumer | Xử lý lại message sau crash/redelivery | At-least-once dẫn tới trùng nghiệp vụ nếu thiếu dedup |

Nếu mọi tầng đều tự retry nhiều lần, tổng số lần thực thi có thể tăng đáng kể. Giới hạn theo deadline, số attempt, backoff có jitter và chính sách rate limit; **không retry vô hạn** khi cluster quá tải.

Phân loại lỗi để quyết định hành động:

- `Unavailable`: số replica cần cho CL không khả dụng theo đánh giá coordinator; kiểm tra topology/CL, không chỉ retry dồn dập.
- `WriteTimeout`: kết quả ghi **có thể chưa biết**, cần xem loại write và quy tắc idempotency.
- `ReadTimeout`: query có thể chạy chậm, cần xem partition, tombstone, consistency.
- Kết nối hoặc client timeout: không chứng minh coordinator chưa xử lý yêu cầu.
- Schema/type/invalid query: sửa dữ liệu/query/configuration thay vì retry lặp lại cùng lỗi.

## 17. Thử lại thao tác bằng repository và CassandraTemplate

Spring Data Cassandra có thể thao tác theo entity:

~~~java
@PrimaryKeyClass
public class OrderKey implements Serializable {
    @PrimaryKeyColumn(name = "customer_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "order_day", ordinal = 1,
                      type = PrimaryKeyType.PARTITIONED)
    private LocalDate orderDay;

    @PrimaryKeyColumn(name = "placed_at", ordinal = 2,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private Instant placedAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 3,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private UUID orderId;

    // Constructor/getters/setters/equals/hashCode theo mapping thực tế.
}

@Table("orders_by_customer_day")
public class OrderRow {
    @PrimaryKey
    private OrderKey key;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    @Column("last_request_id")
    private UUID lastRequestId;
}
~~~

Ví dụ rút gọn, cần bổ sung import/constructor/accessor và kiểm tra version Spring Data. Repository:

~~~java
public interface OrderRepository
        extends CassandraRepository<OrderRow, OrderKey> {
}
~~~

Một retry của `repository.save(order)` với cùng key và property cố định có thể mang ngữ nghĩa upsert ổn định. Nhưng:

- `save` không tự cấp **idempotency key** hoặc đảm bảo external side effect chỉ chạy một lần.
- Mapped write có thể ghi **nhiều cột** từ entity, không phải partial update chỉ cho field vừa đổi.
- Nếu ứng dụng tái tạo entity với timestamp/ID/TTL khác, đó không còn cùng một lệnh logic.
- Cờ idempotent và các execution options phụ thuộc API/driver version.

Khi cần gắn timestamp cố định hoặc conditional statement, dùng API options phù hợp của `CassandraTemplate` hoặc viết CQL qua `CqlSession`. Không mặc định `@Query`/`@Modifying` tự cung cấp phân loại retry đúng cho mọi nghiệp vụ.

## 18. Concurrent writes: cập nhật trạng thái và dữ liệu đa bảng

Trong Cassandra, mỗi cell có thể có timestamp riêng. Hai writer sửa **hai cột khác nhau** không nhất thiết tranh chấp cùng cell; nhưng nếu một writer cập nhật nguyên entity với field cũ, nó có thể ghi đè cell được writer khác thay.

Đối với nghiệp vụ đa bảng:

~~~text
orders_by_customer_day    <- trạng thái đơn cho màn hình khách
orders_by_status_day      <- bản sao phục vụ truy vấn theo trạng thái
payment_events_by_order   <- sự kiện thanh toán
~~~

Retry một lần ghi ở bảng thứ nhất **không làm ba bảng tự động nhất quán**. Batch Cassandra có ngữ nghĩa và giới hạn riêng, không phải một transaction SQL đa bảng có rollback tùy ý. Nếu ứng dụng phát sự kiện ra queue/cổng thanh toán, Cassandra không tự bao trùm hệ thống ngoài.

Một workflow thường cần:

1. Tạo **command ID** ổn định, lưu/kiểm tra trạng thái xử lý.
2. Thực hiện state transition có điều kiện khi cần.
3. Ghi nhận kết quả/ sự kiện theo cơ chế idempotent.
4. Retry từng bước có thể xác minh, có kế hoạch reconciliation cho trạng thái không chắc chắn.
5. Kiểm tra dữ liệu denormalized, sửa sai lệch theo đường vận hành được phê duyệt.

**Chỉ dùng RF/CL cao hơn không sửa khoảng trống giữa hai lần ghi ở những bảng hoặc hệ thống khác nhau.**

## 19. Kiểm thử retry bằng failure injection có kiểm soát

Kiểm thử trên môi trường Cassandra thử nghiệm có schema, driver và replication tương tự production. Không chủ động làm down node production để thử tính idempotent.

| Kịch bản | Cách kiểm tra | Kết quả mong muốn |
| --- | --- | --- |
| Gửi lại INSERT cùng khóa | Dùng cùng `order_id`/`placed_at`/payload | Một hàng logic theo primary key |
| Retry tạo ID mới | Cố tình tạo hai ID trong test | Nhìn rõ nguy cơ hai hàng nghiệp vụ |
| Ghi A timeout, B cập nhật trạng thái | Retry A với timestamp mới và cố định | Quan sát rủi ro LWW, tránh replay cũ ghi đè B |
| Counter increment bị retry | Thực thi hai lần trong test | Nhìn thấy khả năng tăng hai lần |
| List append bị retry | Thực thi hai lần | Có thể có phần tử trùng |
| LWT retry sau phản hồi mất | Chạy cùng conditional update hai lần | Lần sau có thể `applied=false` dù lần đầu thành công |
| TTL và replay | Ghi lặp cách nhau vài phút | Kiểm tra hạn còn lại và phạm vi cell |
| DELETE cũ bị replay | Ghi lại một giá trị mới trước retry delete | Kiểm tra nguy cơ tombstone mới xóa dữ liệu |
| Client và driver cùng retry | Cấu hình giới hạn attempt | Không tạo bão request/ngoài ý muốn |

Để xem CQL write timestamp của cột scalar:

~~~sql
SELECT status, WRITETIME(status), TTL(status)
FROM commerce_ks.orders_by_customer_day
WHERE customer_id = ?
  AND order_day = ?
  AND placed_at = ?
  AND order_id = ?;
~~~

`WRITETIME(status)` trả write timestamp ở đơn vị **micro giây**; `TTL(status)` cho số giây còn lại khi cột có TTL. Đây là công cụ quan sát, **không phải bằng chứng đầy đủ về mọi lần request đã được xử lý**, vì Cassandra chỉ giữ trạng thái còn hiệu lực theo ngữ nghĩa lưu trữ.

Theo dõi thêm timeout/unavailable, retries, p95/p99 latency, số record trùng theo business ID, số conflict LWT, và số command phải reconciliation. Đừng log dữ liệu nhạy cảm hoặc toàn bộ payload của thao tác thanh toán.

## 20. Checklist trước khi bật retry cho một thao tác

- [ ] Có **business command ID / idempotency key** cố định xuyên các lần retry.
- [ ] Primary key đầy đủ và giá trị CQL được tạo **một lần**, không sinh UUID/thời gian mới khi retry cùng lệnh.
- [ ] Đã phân loại thao tác là gán giá trị, counter, list append, set mutation, delete hay LWT.
- [ ] Đã đánh giá **write timestamp**, đồng hồ, write cạnh tranh và nguy cơ cập nhật cũ đè mới.
- [ ] Nếu có TTL, đã xác định retention deadline và hiểu tác động của replay.
- [ ] Đã dùng partial update nếu chỉ muốn sửa một cột, không mặc định dirty checking.
- [ ] Có LWT hoặc state machine khi nghiệp vụ yêu cầu transition có điều kiện.
- [ ] Khi LWT `applied=false` sau retry, không tự kết luận lần đầu chưa thành công.
- [ ] Các side effect ngoài Cassandra có cơ chế chống lặp riêng.
- [ ] Driver retry policy, cờ idempotent, backoff, deadline và gateway retry được phối hợp.
- [ ] Có đường đọc/reconciliation khi ghi timeout và kết quả không chắc chắn.
- [ ] Test failure modes trên cluster thử nghiệm, theo dõi metrics và dữ liệu thực.

## 21. Tự kiểm tra

**Câu 1.** Vì sao timeout của một câu `INSERT` không đủ để kết luận Cassandra chưa ghi gì?

**Đáp án:** Replica có thể đã áp dụng mutation trước khi phản hồi mất hoặc quá hạn; client chỉ biết rằng nó không nhận đủ xác nhận đúng hạn.

**Câu 2.** Retry cùng một đơn hàng nhưng sinh `order_id` mới có còn là thao tác idempotent không?

**Đáp án:** Không về mặt bản ghi đơn hàng: primary key thay đổi, Cassandra có thể tạo hàng mới. Cần ID ổn định cho cùng command.

**Câu 3.** Vì sao retry `SET views = views + 1` có thể sai?

**Đáp án:** Lệnh tăng counter không idempotent; nếu lần đầu đã thực hiện, lần retry có thể làm số đếm tăng thêm lần nữa.

**Câu 4.** Tại sao dùng write timestamp mới cho một retry cũ có thể ghi đè trạng thái do writer khác vừa cập nhật?

**Đáp án:** Cassandra phân giải phiên bản cell theo timestamp. Retry có timestamp cao hơn có thể thắng, dù nó thuộc command nghiệp vụ xảy ra trước.

**Câu 5.** Dùng `UPDATE ... IF status='NEW'`, lần đầu thành công nhưng mất phản hồi; lần retry có thể trả `applied=false` không?

**Đáp án:** Có. Trạng thái đã không còn `NEW` sau lần đầu. Phải kiểm tra request ID, trạng thái đã lưu hoặc ledger, không xem `false` là chứng minh lần đầu thất bại.

**Câu 6.** Vì sao cố định TTL=86400 giây không mặc định giữ đúng một deadline khi lặp lại lệnh?

**Đáp án:** TTL liên quan thời điểm và ngữ nghĩa của giá trị được ghi; replay có thể ảnh hưởng thời gian hết hạn. Nếu retention theo deadline tuyệt đối, cần một chính sách tính/kiểm chứng deadline rõ ràng.

**Câu 7.** `repository.save(entity)` có bảo đảm chỉ ghi property Java vừa được sửa như JPA dirty checking không?

**Đáp án:** Không mặc định. Mapped write có thể đưa nhiều property vào statement; khi chỉ muốn một cột, nên dùng partial update rõ ràng.

**Câu 8.** Đánh dấu `setIdempotent(true)` có đảm bảo cổng thanh toán chỉ thu tiền một lần không?

**Đáp án:** Không. Cờ này hỗ trợ driver quyết định retry statement Cassandra; hiệu ứng nghiệp vụ ở hệ thống ngoài cần idempotency key và quy trình kiểm soát riêng.

---

**Ghi nhớ:** retry một thao tác Cassandra phải **giữ nguyên danh tính lệnh và ý nghĩa cập nhật**, không chỉ gửi lại cùng đoạn code. Timeout khiến kết quả ghi có thể không chắc chắn; `INSERT/UPDATE` thường upsert theo primary key; Cassandra dùng **write timestamp theo cell** để phân giải xung đột. Với thao tác gán giá trị có đầu vào ổn định, retry có thể được thiết kế idempotent; với counter, list append, TTL, DELETE hoặc chuyển trạng thái có điều kiện, phải kiểm tra ngữ nghĩa riêng. Dùng **LWT/state machine/idempotency key**, giới hạn retry và cơ chế reconciliation khi cần, đồng thời nhớ rằng CL, repository và `CassandraTemplate` **không tự tạo exactly-once effect cho toàn bộ workflow**.
