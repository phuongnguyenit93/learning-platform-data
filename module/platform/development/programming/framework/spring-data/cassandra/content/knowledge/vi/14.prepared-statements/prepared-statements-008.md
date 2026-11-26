# Fetch size, consistency, timeout và tính lũy đẳng của statement

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Sử dụng `PreparedStatement`, `BoundStatement` và `CqlSession` của Apache Cassandra Java Driver 4.x; phân biệt bước chuẩn bị câu lệnh với bước bind tham số cho từng request.
- Giải thích `setPageSize(…)` điều khiển kích thước trang fetch, khác với `LIMIT` trong CQL và cursor phân trang của API.
- Chọn `setConsistencyLevel(…)` theo replication factor, local data center, SLA, độ trễ và yêu cầu nhất quán của nghiệp vụ.
- Dùng `setTimeout(…)` có căn cứ; phân biệt timeout phía driver, server, kết nối và HTTP, đặc biệt khi kết quả ghi chưa rõ.
- Đánh giá `setIdempotent(…)` trước retry/speculative execution, phân biệt statement idempotent với xử lý nghiệp vụ đúng một lần.
- Điều chỉnh chính sách theo statement hoặc execution profile, hiểu quan hệ với `spring.cassandra.request.*` trong Spring Boot.
- Nhận biết tác động của partition key, clustering key, paging, tính phân tán và thiết kế bảng theo truy vấn đối với hiệu năng.
- Xây dựng bộ kiểm thử tình huống mất replica, timeout, ghi trùng, counter, TTL, đọc nhiều trang và các request cạnh tranh.

Bài thuộc chương **Prepared statement** của **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra bằng entity mapping, repository, `CassandraTemplate` và CQL. Các tham số trong bài là chính sách phía client cho một statement, **không thay thế mô hình dữ liệu**. Muốn đọc nhanh theo khách hàng và thời gian, bạn vẫn phải thiết kế partition key, clustering order và bảng đọc đúng access pattern.

**Phạm vi:** Mã ví dụ dùng Cassandra Java Driver 4.x (`com.datastax.oss.driver.api`) và Spring Data Cassandra/Spring Boot tương thích. Chi tiết cấu hình framework thay đổi giữa các phiên bản; nên kiểm tra dependency và API của dự án trước khi đưa code vào production.

## 1. PreparedStatement, BoundStatement và CqlSession

Câu lệnh CQL có giá trị biến đổi giữa các request nên được prepare một lần và bind lại:

~~~mermaid
flowchart LR
    A["CQL có marker ?"] --> B["session.prepare(cql)"]
    B --> C["PreparedStatement được dùng lại"]
    C --> D["bind(customer A, month A)"]
    C --> E["bind(customer B, month B)"]
    D --> F["BoundStatement A + options"]
    E --> G["BoundStatement B + options"]
    F --> H["session.execute"]
    G --> H
    H --> I["Cassandra coordinator/replica"]
~~~

| Thành phần | Chức năng |
| --- | --- |
| `CqlSession` | Session kết nối cluster, thường là bean dùng chung do Spring Boot quản lý |
| `PreparedStatement` | Câu CQL đã được prepare và metadata kiểu marker; nên tái sử dụng |
| `BoundStatement` | Một câu prepared được gắn giá trị và các tùy chọn thực thi |
| `BoundStatementBuilder` | Builder giúp bind theo tên/vị trí và thiết lập nhiều options |
| `ResultSet` / `AsyncResultSet` | Row và metadata trang, thông tin thực thi |
| `DriverExecutionProfile` | Bộ mặc định cho request timeout, page size, consistency... |
| `CassandraTemplate` / repository | Tầng ánh xạ object và thao tác dữ liệu Spring Data |

### 1.1. Thiết kế bảng theo truy vấn trước khi prepare

Giả sử cần lấy lịch sử đơn theo khách hàng/tháng, theo thứ tự mới nhất:

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Partition key là **`(customer_id, month_bucket)`**; clustering columns là `created_at` và `order_id`. Truy vấn hợp lệ cho một partition:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?;
~~~

Không thể sửa một query thiếu `month_bucket` chỉ bằng cách nâng consistency, timeout, page size hoặc prepare. Bản chất của query-driven design là tạo bảng cho câu hỏi cần trả lời và giữ partition có kích thước, mức tải phù hợp.

### 1.2. Prepare một lần, bind mỗi request

~~~java
import java.time.Duration;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class CustomerOrderReader {

    private final CqlSession session;
    private final PreparedStatement selectMonth;

    public CustomerOrderReader(CqlSession session) {
        this.session = session;

        this.selectMonth = session.prepare(
            "SELECT order_id, created_at, status, total_amount " +
            "FROM orders_by_customer_month " +
            "WHERE customer_id = ? AND month_bucket = ?"
        );
    }

    public ResultSet find(UUID customerId, String month) {
        BoundStatement bound = selectMonth
            .bind(customerId, month)
            .setPageSize(200)
            .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(2))
            .setIdempotent(true);

        return session.execute(bound);
    }
}
~~~

**Giải thích:** `prepare` chạy một lần khi adapter được tạo; `bind` tạo statement mới ứng với request; các `setXxx` trả một statement mới mang tùy chọn đã chỉnh. Tránh cách viết gọi `setPageSize(...)` nhưng bỏ qua giá trị trả về, vì API statement của Driver 4.x theo hướng **immutable**.

`PreparedStatement` có thể tái sử dụng giữa nhiều request, nhưng nên cấp riêng một `BoundStatement`/builder cho mỗi lượt bind. Không cố chia sẻ và sửa cùng một builder giữa các thread.

### 1.3. Không prepare trong vòng lặp hoặc nối giá trị vào CQL

~~~java
// Không nên chạy cho mọi request:
PreparedStatement p = session.prepare(
    "SELECT * FROM orders_by_customer_month " +
    "WHERE customer_id = ? AND month_bucket = ?");
BoundStatement b = p.bind(customerId, bucket);
~~~

Driver có cơ chế quản lý/cache prepared metadata, nhưng lặp lại prepare không cần thiết vẫn tạo overhead hoặc tăng độ phức tạp. Giữ prepared query cố định ở adapter, không tạo query text khác nhau cho từng giá trị.

Marker `?` bind **giá trị**, không bind identifier như tên bảng hoặc tên cột:

~~~sql
-- Không dùng ? để thay tên bảng:
SELECT * FROM ? WHERE customer_id = ?;
~~~

Nếu cần đọc nhiều bảng có cấu trúc tương thích, chọn tên bảng từ **allowlist** đã được provision, kiểm tra quyền và prepare từng câu CQL hợp lệ. Không nhận thẳng tên bảng do client gửi rồi nối chuỗi không kiểm soát.

## 2. Bốn thiết lập thực thi và mức ưu tiên

| Thao tác | API Driver 4.x | Điều khiển | Điều KHÔNG được bảo đảm |
| --- | --- | --- | --- |
| Fetch size | `setPageSize(int)` | Kích thước trang kết quả mục tiêu | LIMIT, OFFSET hoặc tối ưu query sai partition |
| Consistency | `setConsistencyLevel(ConsistencyLevel)` | Ngưỡng/phạm vi replica phản hồi | Transaction ACID hay CAS nghiệp vụ |
| Timeout | `setTimeout(Duration)` | Giới hạn chờ request phía client | Server chưa ghi khi client timeout |
| Lũy đẳng | `setIdempotent(Boolean)` | Metadata cho retry/speculative execution an toàn | Exactly-once hay tự biến mutation thành idempotent |

Các options gắn vào `BoundStatement` có thể ghi đè mặc định từ execution profile. Hai lượt bind cùng một prepared query **có thể mang chính sách khác nhau**. Bảng/primary key/replication không thay đổi khi bạn chỉnh options này.

Ví dụ:

~~~java
BoundStatement interactive = selectMonth.bind(customerId, bucket)
    .setPageSize(50)
    .setTimeout(Duration.ofSeconds(2))
    .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(true);

BoundStatement export = selectMonth.bind(customerId, bucket)
    .setPageSize(500)
    .setTimeout(Duration.ofSeconds(10))
    .setConsistencyLevel(ConsistencyLevel.LOCAL_ONE)
    .setIdempotent(true);
~~~

`LOCAL_ONE` ở ví dụ export **chỉ có ý nghĩa nếu nghiệp vụ chấp nhận dữ liệu có thể trễ**. Không nên mặc định export cần nhất quán kém hơn API. Một báo cáo giao dịch chính xác có thể đòi mức consistency khác.

## 3. Fetch size: page size không phải LIMIT

### 3.1. Một truy vấn có thể có nhiều lần fetch

Giả sử một partition trả về 1.200 row và statement dùng `setPageSize(100)`:

~~~text
CQL trả 1.200 row
 |
 +-- trang 1: tối đa khoảng 100 row mục tiêu
 +-- trang 2: tối đa khoảng 100 row mục tiêu
 +-- ...
 +-- trang cuối: phần còn lại

Duyệt hết ResultSet có thể kích hoạt nhiều request fetch.
~~~

Page size là **mục tiêu**, không phải cam kết server sẽ luôn trả chính xác số row đó. Đồng thời, `session.execute(statement)` không có nghĩa toàn bộ 1.200 row đã được tải ngay: driver xử lý các trang tiếp theo theo cơ chế paging.

~~~java
ResultSet result = session.execute(
    selectMonth.bind(customerId, "2026-11").setPageSize(100));

for (Row row : result) {
    // Với API đồng bộ, duyệt có thể tự fetch trang sau.
    System.out.println(row.getUuid("order_id"));
}
~~~

Cần import `Row` từ `com.datastax.oss.driver.api.core.cql.Row`. Nếu API chỉ muốn trang đầu, **không duyệt cả `ResultSet`** rồi mới lấy một phần nhỏ trả về HTTP.

### 3.2. So sánh LIMIT, page size và paging state

~~~sql
SELECT order_id, created_at, status
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

- **`LIMIT 20`:** Giới hạn tổng số row query có thể trả theo ngữ nghĩa CQL.
- **`pageSize=100`:** Số row mục tiêu cho một lần fetch. Nếu `LIMIT 20`, kết quả không bỗng tăng thành 100.
- **Paging state:** Token tiếp tục đúng truy vấn đã bind; không phải offset trang số học.
- **HTTP cursor:** Hợp đồng của API, có thể bao gói paging state, bucket, quyền truy cập và metadata khác.

Trên statement `LIMIT 1000` và `pageSize=100`, việc tiêu thụ toàn bộ kết quả có thể fetch khoảng mười trang. Trên statement `LIMIT 20` và `pageSize=100`, kết quả vẫn tối đa 20 row.

### 3.3. AsyncResultSet cho phép xử lý đúng trang hiện tại

~~~java
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

BoundStatement bound = selectMonth
    .bind(customerId, "2026-11")
    .setPageSize(100)
    .setIdempotent(true);

CompletionStage<AsyncResultSet> pending =
    session.executeAsync(bound);

pending.thenAccept(page -> {
    for (Row row : page.currentPage()) {
        System.out.println(row.getUuid("order_id"));
    }

    if (page.hasMorePages()) {
        // Có thể gọi page.fetchNextPage() khi được phép tiếp tục.
        // Phải xử lý CompletionStage và lỗi bất đồng bộ riêng.
    }
});
~~~

`page.currentPage()` chỉ chứa row của trang hiện tại; `fetchNextPage()` trả một `CompletionStage<AsyncResultSet>` cho lần tiếp theo. Khi triển khai thật, cần xử lý exception, cancellation, tài nguyên và **backpressure** thay vì gọi fetch liên tục không kiểm soát.

### 3.4. Paging state phải gắn với query và giá trị bind

Không dùng paging state của `customer_id=A` cho truy vấn `customer_id=B`. Không thay `WHERE`, `LIMIT`, các values hoặc schema rồi mặc định token cũ vẫn đúng. Không coi token là một số offset có thể tự tăng.

Nếu expose cursor cho client, cần thiết kế:

1. Bảo vệ token khỏi bị sửa/giả mạo hoặc lưu server-side.
2. Ràng buộc cursor với user, partition, filter và phiên bản dữ liệu/schema khi cần.
3. Có giới hạn tuổi cursor và chính sách xử lý token hết hạn.
4. Thực thi giới hạn page size cho request và toàn bộ công việc.
5. Tính đến việc dữ liệu mới chen vào các trang khi có ghi đồng thời.

### 3.5. Chọn page size theo tải

| Nhỏ | Lớn |
| --- | --- |
| Payload mỗi lần fetch nhỏ hơn | Ít round-trip hơn khi xử lý nhiều row |
| Thường giảm đỉnh RAM và chi phí giải mã mỗi trang | Có thể tăng memory, network, thời gian xử lý trang |
| Có thể tăng số lần fetch | Có thể làm đuôi độ trễ p99 xấu hơn nếu row rộng |
| Hợp API tương tác, row lớn | Chỉ hợp export khi được đo và kiểm soát |

Giá trị như 100, 200 hay 500 trong ví dụ **không phải cấu hình tối ưu mặc định**. Phải đo độ rộng row, UDT/collection, network, request đồng thời, kích thước partition, tombstone và p95/p99. Tăng page size không sửa được hot partition hoặc `ALLOW FILTERING`.

## 4. Consistency: ngưỡng phản hồi replica

**Replication factor (RF)** của keyspace cho biết số replica mục tiêu; **consistency level (CL)** của statement cho biết ngưỡng/phạm vi xác nhận cần có.

Giả sử cluster có RF = 3 trong DC `dc1` với đủ node lành mạnh:

| CL | Số replica phản hồi trong tình huống điển hình | Ý nghĩa |
| --- | ---: | --- |
| `LOCAL_ONE` | 1 ở DC cục bộ | Nhanh hơn trong nhiều tình huống, nhưng có thể thấy replica chưa cập nhật |
| `LOCAL_QUORUM` | 2 ở DC cục bộ | Đa số, có chi phí/đòi hỏi sẵn sàng cao hơn |
| `QUORUM` | 2 ở toàn bộ các DC trong ví dụ một DC | Ở mô hình một DC ngưỡng số lượng giống local quorum |
| `ALL` | 3 | Nhạy với một replica không phản hồi |

~~~java
BoundStatement bound = selectMonth
    .bind(customerId, "2026-11")
    .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM);
~~~

### 4.1. LOCAL_QUORUM trong cụm nhiều DC

Nếu keyspace có `dc1:3, dc2:3`, write `LOCAL_QUORUM` tại `dc1` cần đạt quorum **dc1**, không yêu cầu `dc2` đã bắt kịp khi phản hồi về client. Ngay sau đó, một client đọc tại `dc2` với `LOCAL_QUORUM` **không** mặc định có read-after-write xuyên DC.

Cũng cần phân biệt:

- Replica vật lý của **một bảng** được sao chép bởi Cassandra.
- Bảng `orders_by_id` và `orders_by_customer_month` là **hai read model nghiệp vụ** có thể cập nhật khác thời điểm.
- LWT `IF ...` kiểm soát điều kiện ghi trên phạm vi hợp lệ, khác với CL thông thường.

Tăng consistency của hai truy vấn không tự đồng bộ hai bảng, không tự chặn bản tin nghiệp vụ revision cũ ghi đè revision mới.

### 4.2. Giao nhau của quorum có giới hạn

Trong mô hình một DC lý tưởng, đọc R replica, ghi W replica, nếu `R + W > RF` thì hai tập xác nhận phải giao nhau. Với RF=3 và `LOCAL_QUORUM` cho cả đọc/ghi, `2+2>3`. Nhưng đây không phải cam kết tuyệt đối mọi request thấy “giá trị mới nhất” khi có concurrent writes, timeout, timestamp cạnh tranh hoặc topology thay đổi.

`LOCAL_QUORUM` với RF=1 chỉ cần một replica, không tạo ra khả năng chịu lỗi dù tên gọi có chữ quorum. Hãy xem RF và topology thực tế, không chọn CL chỉ vì tên trông mạnh.

### 4.3. CL không phải một giao dịch ACID

Ví dụ:

~~~sql
UPDATE orders_by_id
SET status = 'PAID'
WHERE order_id = ?;
~~~

Dù request được gửi ở `LOCAL_QUORUM`, lệnh CQL thông thường vẫn upsert; nó không tự kiểm tra rằng trạng thái cũ là `CREATED` hay revision phù hợp. Nếu một writer khác ghi `CANCELLED`, kết quả còn phụ thuộc timestamp và đồng thời.

Để yêu cầu “chỉ chuyển khi trạng thái đang CREATED”, dùng conditional update:

~~~sql
UPDATE orders_by_id
SET status = 'PAID', revision = 2
WHERE order_id = ?
IF status = 'CREATED' AND revision = 1;
~~~

Cassandra dùng LWT cho điều kiện; phải kiểm tra `[applied]`, latency và conflict. Với LWT, Java Driver còn cho phép `setSerialConsistencyLevel(ConsistencyLevel.LOCAL_SERIAL)` hoặc `SERIAL` riêng cho phần điều phối đồng thuận. **Không đặt `SERIAL` làm consistency thông thường cho mọi statement.**

### 4.4. Không hạ CL chỉ để che lỗi

Khi thấy `UnavailableException` hoặc timeout ở `LOCAL_QUORUM`, hãy kiểm tra RF, số node hoạt động, tên local DC, mạng, log coordinator và SLA. Hạ xuống `LOCAL_ONE` có thể giảm yêu cầu phản hồi nhưng đồng thời thay đổi mức bảo đảm dữ liệu. Chỉ làm vậy nếu có chính sách degrade đã được chấp nhận rõ ràng.



## 5. Timeout: giới hạn phía driver, không phải rollback

### 5.1. Phân biệt các tầng timeout

~~~java
BoundStatement statement = selectMonth
    .bind(customerId, "2026-11")
    .setTimeout(Duration.ofSeconds(2));
~~~

`setTimeout` giới hạn thời gian Java Driver chờ kết quả một request. Khi timeout, **không thể kết luận Cassandra chưa xử lý hoặc chưa ghi**.

| Timeout | Phạm vi | Điều cần kiểm tra |
| --- | --- | --- |
| Driver request | Client chờ phản hồi CQL | Latency, retry, paging, coordinator |
| Connection | TCP/TLS/khởi tạo kết nối | DNS, firewall, network, node |
| Server read/write | Coordinator chờ replicas | Consistency, RF, node, tải |
| HTTP/API | Tổng request ứng dụng | SLA, logic, mapping và những dependency khác |

Một request có thể timeout ở driver nhưng mutation đã áp dụng. Ngược lại, server cũng có thể trả `ReadTimeoutException`/`WriteTimeoutException` trước khi hết client timeout. Cần phân loại ngoại lệ theo nguồn thay vì chỉ tăng mọi timeout.

### 5.2. Ghi xong nhưng phản hồi bị mất

~~~mermaid
sequenceDiagram
    participant API
    participant Driver
    participant Cassandra
    API->>Driver: INSERT order
    Driver->>Cassandra: Gửi mutation
    Cassandra->>Cassandra: Áp dụng mutation
    Cassandra--xDriver: Phản hồi bị mất
    Driver-->>API: Timeout
    Note over API,Cassandra: Row có thể đã được ghi
~~~

Retry mù có thể tạo tác dụng phụ:

- `INSERT` thông thường có tính upsert.
- Ghi lại `USING TTL 3600` có thể làm mới hạn sống.
- Retry một revision cũ có thể ghi đè mutation nghiệp vụ mới nếu timestamp thắng.
- Counter increment có thể tăng hai lần.
- Append vào list có thể ghi trùng.
- `INSERT IF NOT EXISTS` có thể trả `[applied] = false` ở retry do lần trước đã thành công.

Nếu cần kết quả chính xác, xây dựng idempotency key/request ID, cách kiểm tra theo primary key, revision/CAS khi phù hợp và quy trình đối soát cho kết quả không rõ.

### 5.3. Chọn timeout theo SLA

Với API SLA 3 giây, phải dành thời gian cho auth, logic nghiệp vụ, driver, mapping và response. Timeout DB 30 giây có thể trái hợp đồng; timeout quá ngắn lại tạo false timeout khi p99 cao.

Với export nhiều trang, timeout cho một request **không giới hạn tổng thời gian export**. Cần giới hạn toàn công việc, số page/byte, request đồng thời, backpressure và chính sách hủy. Không tăng timeout để che hot partition, tombstone hoặc query sai partition key.

## 6. Tính lũy đẳng: setIdempotent()

### 6.1. Định nghĩa

Statement idempotent khi gửi lại thao tác không tạo ra **tác dụng phụ đáng kể bổ sung**, theo ngữ cảnh nghiệp vụ đã xác định.

~~~java
BoundStatement read = selectMonth.bind(customerId, "2026-11")
    .setIdempotent(true);
~~~

`SELECT` không sửa dữ liệu nên thường lũy đẳng. Hai lần đọc có thể thấy trạng thái khác nhau nếu có concurrent writes, nhưng bản thân việc đọc lại không tạo mutation.

**`setIdempotent(true)` là một khai báo cho driver**, không tự biến CQL thành lũy đẳng, không bảo đảm exactly-once và không tự bật mọi retry. Retry policy, speculative execution policy và loại lỗi vẫn quyết định có attempt bổ sung hay không.

### 6.2. Đánh giá từng thao tác

| Statement | Idempotency | Lưu ý |
| --- | --- | --- |
| `SELECT ... WHERE full_partition_key = ?` | Thường `true` | Không tạo side effect |
| `INSERT` cùng khóa/cùng giá trị scalar | Có thể | Xét writer cạnh tranh và timestamp |
| `UPDATE ... SET status = 'PAID'` | Phải xem nghiệp vụ | Retry cũ có thể ghi đè trạng thái mới |
| `INSERT ... USING TTL 3600` | Thận trọng | Retry làm mới TTL |
| `UPDATE views = views + 1` (counter) | **false** | Retry đếm hai lần |
| `UPDATE actions = actions + [?]` (list append) | **false** | Chèn trùng |
| `INSERT ... IF NOT EXISTS` | Không suy cho toàn workflow | Timeout, `[applied]` và request ID |
| Ghi CQL rồi gửi email/event | Không xác định chỉ từ CQL | Side effect ở hệ thống khác |

Cassandra giải quyết xung đột ghi theo **timestamp cấp cell**, không tự so sánh business revision. Một statement mang giá trị cố định có thể idempotent trong môi trường chỉ một writer nhưng không an toàn khi có nhiều writer và trạng thái tiến triển.

### 6.3. Ví dụ counter không idempotent

~~~sql
CREATE TABLE page_views (
    page_id uuid PRIMARY KEY,
    views counter
);
~~~

~~~java
PreparedStatement increment = session.prepare(
    "UPDATE page_views SET views = views + 1 WHERE page_id = ?"
);

BoundStatement step = increment.bind(pageId)
    .setIdempotent(false)
    .setTimeout(Duration.ofSeconds(2));

session.execute(step);
~~~

Nếu request đầu đã được áp dụng nhưng response mất, retry sẽ tăng lần nữa. PreparedStatement hay LOCAL_QUORUM không khử trùng phép cộng. Khi cần mỗi event đếm đúng một lần, phải có cơ chế chống lặp ở tầng event/aggregation.

### 6.4. List append và TTL

~~~sql
UPDATE session_history
SET actions = actions + ['LOGIN']
WHERE session_id = ?;
~~~

Với `actions list<text>`, retry append có thể sinh phần tử trùng. Với lịch sử vô hạn, hãy dùng bảng event theo user/time bucket và event ID ổn định thay vì collection khổng lồ.

Ghi cùng giá trị `USING TTL 3600` lần nữa sau một phút cũng có thể kéo dài thời gian hết hạn. “Kết quả cuối có cùng giá trị” **không đủ** chứng minh tính lũy đẳng.

### 6.5. Các công cụ phục vụ mức bảo đảm khác nhau

~~~text
setIdempotent(true): metadata để driver quyết định attempt bổ sung
requestId          : định danh lệnh API gửi lại
IF NOT EXISTS      : chặn ghi trùng một row theo điều kiện
revision + CAS     : tránh thay đổi nghiệp vụ sai thứ tự
event deduplication: chống lặp side effect ở downstream
~~~

Không có một flag statement nào tự đảm bảo exactly-once end-to-end.

## 7. Retry, speculative execution và reconnection

| Cơ chế | Kích hoạt | Đánh đổi |
| --- | --- | --- |
| Retry policy | Attempt lỗi theo rule của policy | Gửi thêm request, lặp tác dụng phụ nếu unsafe |
| Speculative execution | Request chậm, policy cho phép thử song song | Tăng tải, có thể gây contention |
| Reconnection policy | Node/connection mất, driver kết nối lại | Không tự xử lý workflow nghiệp vụ chưa rõ kết quả |

Statement được đánh dấu idempotent **có thể đủ điều kiện** retry/speculate; không có bảo đảm mọi exception đều retry. Khi speculating cho read, phải đo p95/p99, speculative attempts, request rate, pool in-flight, CPU/IO và tail latency trên cụm; nếu toàn cluster quá tải, attempt thêm có thể làm tệ hơn.

Không lấy timeout 2 giây nhân với số attempts để tính tổng thời gian một cách máy móc. Deadline/attempt và policy tùy phiên bản; cần kiểm soát SLA ở tầng gọi API/công việc.

## 8. Bind marker theo tên và BoundStatementBuilder

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT order_id, created_at, status " +
    "FROM orders_by_customer_month " +
    "WHERE customer_id = :customer_id " +
    "AND month_bucket = :month_bucket"
);

BoundStatement bound = prepared.boundStatementBuilder()
    .setUuid("customer_id", customerId)
    .setString("month_bucket", "2026-11")
    .setPageSize(200)
    .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(2))
    .setIdempotent(true)
    .build();

ResultSet result = session.execute(bound);
~~~

Named markers giúp giảm nhầm thứ tự, nhưng kiểu binder vẫn phải khớp CQL type. Nếu dùng dấu `?` thì `prepared.bind(v1, v2)` là cách đơn giản. Không cần prepare lại khi chỉ thay các tùy chọn statement.

Không chia sẻ một builder để sửa giữa nhiều thread; tạo statement riêng mỗi request. Đừng nội suy trực tiếp tên bảng hoặc giá trị user vào câu CQL.


## 9. Execution profile và cấu hình mặc định

Khi một statement **không** tự thiết lập page size/consistency/timeout/idempotency, Java Driver có thể lấy giá trị từ `DriverExecutionProfile`. Có thể khai báo profile khác nhau cho API tương tác, export hoặc nghiệp vụ có SLA đặc thù.

Ví dụ cấu hình Java Driver 4.x bằng HOCON:

~~~hocon
datastax-java-driver {
  basic {
    request {
      timeout = 2 seconds
      page-size = 200
      consistency = LOCAL_QUORUM
      default-idempotence = false
    }
  }

  profiles {
    export {
      basic.request.timeout = 10 seconds
      basic.request.page-size = 500
    }
  }
}
~~~

`default-idempotence = false` ở đây là lựa chọn thận trọng: các statement chưa được phân loại sẽ không tự được tuyên bố lũy đẳng. Query được chứng minh an toàn có thể gọi `setIdempotent(true)` riêng.

Một statement chọn profile:

~~~java
BoundStatement export = selectMonth
    .bind(customerId, "2026-11")
    .setExecutionProfileName("export")
    .setIdempotent(true);
~~~

Profile `export` sẽ cung cấp timeout/page size riêng; các thuộc tính chưa override có thể kế thừa default profile. Nếu statement gọi thêm `setTimeout(Duration.ofSeconds(3))`, giá trị **trực tiếp** đó ưu tiên hơn timeout của profile. Thứ tự khái quát:

~~~text
BoundStatement option được chỉ định tường minh
    > named execution profile của statement
    > default execution profile
    > reference defaults/fallback của driver
~~~

Không phải mọi tùy chọn của driver đều hỗ trợ thay đổi nóng. Khi đổi HOCON/driver loader, cần biết phương thức reload và option nào được áp dụng lên session đang hoạt động, thay vì chỉ dựa vào việc file đã đổi.

### 9.1. Cấu hình Spring Boot

Ứng dụng Spring Boot thường cho phép các defaults qua `application.yml`:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cassandra-1.internal
      - cassandra-2.internal
    local-datacenter: dc1
    keyspace-name: order_service
    request:
      timeout: 2s
      page-size: 200
      consistency: LOCAL_QUORUM
~~~

`local-datacenter` phải khớp tên DC thật; `contact-points` chỉ là điểm bắt đầu khám phá node. `keyspace-name` không tự quyết định RF, schema hay số replica đang khỏe.

Spring Boot tự tạo `CqlSession`, vì vậy không nên tạo session mới chỉ để thay timeout. Có thể dùng `spring.cassandra.config` cho file HOCON nâng cao hoặc `DriverConfigLoaderBuilderCustomizer` để bổ sung option driver (tùy phiên bản Spring Boot). Các override trực tiếp trên `BoundStatement` có thể ưu tiên so với defaults.

### 9.2. Java Driver thuần và DriverConfigLoader

Khi không dùng Boot, có thể đặt defaults lập trình:

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;

DriverConfigLoader loader =
    DriverConfigLoader.programmaticBuilder()
        .withDuration(
            DefaultDriverOption.REQUEST_TIMEOUT,
            Duration.ofSeconds(2))
        .withInt(
            DefaultDriverOption.REQUEST_PAGE_SIZE, 200)
        .withString(
            DefaultDriverOption.REQUEST_CONSISTENCY,
            "LOCAL_QUORUM")
        .withBoolean(
            DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE,
            false)
        .build();
~~~

Khi tự xây dựng `CqlSession`, cần truyền loader qua `CqlSession.builder().withConfigLoader(loader)` và quản lý đúng keyspace, contact points, local DC, SSL/auth và vòng đời. Không trộn hai đường quản lý session mà không có lý do.

### 9.3. Đọc cấu hình đang có hiệu lực

Có thể kiểm tra giá trị của default profile:

~~~java
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;

DriverConfig config = session.getContext().getConfig();
DriverExecutionProfile defaults = config.getDefaultProfile();

Duration timeout = defaults.getDuration(
    DefaultDriverOption.REQUEST_TIMEOUT);

int pageSize = defaults.getInt(
    DefaultDriverOption.REQUEST_PAGE_SIZE);
~~~

Đây là cách xác minh **default profile**, còn statement có thể ghi đè thông qua `setTimeout`/`setPageSize` hoặc chọn profile khác. Không log secret/token/TLS private key khi in cấu hình.

## 10. Tích hợp với repository và CassandraTemplate

Spring Data Cassandra cho phép thao tác theo entity:

~~~java
@Table("orders_by_id")
public class OrderById {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("status")
    private String status;

    // Constructor, getters, setters...
}

public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}
~~~

Đọc từ repository:

~~~java
Optional<OrderById> order =
    orderByIdRepository.findById(orderId);
~~~

Hoặc qua `CassandraTemplate`:

~~~java
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

OrderById order = cassandraTemplate.selectOne(
    query(where("order_id").is(orderId)),
    OrderById.class
);
~~~

Các API này sinh và thực thi câu CQL theo mapping. Chúng **không tự lấy một đối tượng `BoundStatement` do adapter khác tạo** để áp dụng các `setXxx` của bạn.

Khi cần chính sách riêng cho request:

1. Nếu phù hợp, cấu hình defaults và named execution profile cho driver.
2. Sử dụng các option/query extensions mà phiên bản Spring Data Cassandra hỗ trợ.
3. Với đường cần kiểm soát chính xác statement/driver, tạo adapter sử dụng **cùng `CqlSession` đã được Spring quản lý**; ánh xạ kết quả sang DTO hoặc dùng converter phù hợp.

Không mở thêm `CqlSession` cho từng request HTTP. Session mới tăng kết nối, chi phí metadata và phức tạp vận hành.

### 10.1. Adapter đọc với CqlSession và DTO

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

// Có thể đặt record ở file Java riêng.
record OrderCard(
    UUID orderId,
    Instant createdAt,
    String status,
    BigDecimal totalAmount
) {
}

public final class OrderCardReader {

    private final CqlSession session;
    private final PreparedStatement latest20;

    public OrderCardReader(CqlSession session) {
        this.session = session;
        this.latest20 = session.prepare(
            "SELECT order_id, created_at, status, total_amount " +
            "FROM orders_by_customer_month " +
            "WHERE customer_id = ? AND month_bucket = ? LIMIT 20"
        );
    }

    public List<OrderCard> list(UUID customerId, String month) {
        BoundStatement bound = latest20.bind(customerId, month)
            .setPageSize(20)
            .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(2))
            .setIdempotent(true);

        List<OrderCard> result = new ArrayList<>();

        for (Row row : session.execute(bound)) {
            result.add(new OrderCard(
                row.getUuid("order_id"),
                row.getInstant("created_at"),
                row.getString("status"),
                row.getBigDecimal("total_amount")
            ));
        }

        return result;
    }
}
~~~

Đoạn code minh họa đường đi qua Java Driver; với Java 17+ có thể dùng record. Đảm bảo types khớp schema CQL: `timestamp` đọc qua `Instant`, `decimal` qua `BigDecimal`, `uuid` qua `UUID`. Đối với UDT hoặc domain type phức tạp, Spring Data mapping hoặc custom converter có thể phù hợp hơn cách đọc `Row` thủ công.

Dù vòng `for` có thể fetch thêm page, query có `LIMIT 20` nên kết quả có giới hạn. Với export hàng triệu row, không tạo `List` chứa toàn bộ dữ liệu trong RAM.

## 11. Cập nhật có điều kiện: regular CL và serial CL

Một upsert vô điều kiện:

~~~sql
UPDATE orders_by_id
SET status = 'PAID'
WHERE order_id = ?;
~~~

có thể ghi khi row chưa tồn tại và không kiểm tra trạng thái trước đó. Nếu nhiều writer cạnh tranh, retry cũ có thể ghi đè state mới.

Khi workflow cần chuyển từ `CREATED` sang `PAID` theo revision:

~~~sql
UPDATE orders_by_id
SET status = 'PAID', revision = 2
WHERE order_id = ?
IF status = 'CREATED' AND revision = 1;
~~~

Ví dụ Java Driver:

~~~java
PreparedStatement payIfCreated = session.prepare(
    "UPDATE orders_by_id " +
    "SET status = 'PAID', revision = 2 " +
    "WHERE order_id = ? " +
    "IF status = 'CREATED' AND revision = 1"
);

BoundStatement guarded = payIfCreated.bind(orderId)
    .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(ConsistencyLevel.LOCAL_SERIAL)
    .setTimeout(Duration.ofSeconds(5))
    .setIdempotent(false);

boolean applied = session.execute(guarded).wasApplied();

if (!applied) {
    // Có thể một request khác đã chuyển trạng thái.
    // Cần đọc trạng thái và quyết định theo nghiệp vụ.
}
~~~

Đây là LWT, có chi phí đồng thuận và contention. `LOCAL_SERIAL` liên quan pha serial của LWT; `LOCAL_QUORUM` là CL thông thường. `wasApplied()` phản ánh kết quả điều kiện của CQL. Nếu request **timeout**, không được tự kết luận `applied = false`; mutation có thể đã được áp dụng, cần kiểm tra/retry theo thiết kế.

## 12. Thực hành: API tương tác và export có SLA khác nhau

Dịch vụ có hai đường đọc cùng bảng `orders_by_customer_month`:

- API trả **20 đơn mới nhất** của một khách hàng trong một tháng.
- Export đọc nhiều trang của các partition/bucket đã được xác định trước.

### 12.1. API: hạn chế tổng số row

~~~java
PreparedStatement latest20 = session.prepare(
    "SELECT order_id, created_at, status, total_amount " +
    "FROM orders_by_customer_month " +
    "WHERE customer_id = ? AND month_bucket = ? LIMIT 20"
);

BoundStatement interactive = latest20
    .bind(customerId, "2026-11")
    .setPageSize(20)
    .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
    .setTimeout(Duration.ofSeconds(2))
    .setIdempotent(true);

ResultSet page = session.execute(interactive);
~~~

`LIMIT 20` giới hạn kết quả, còn `setPageSize(20)` chỉ điều khiển fetch. `LOCAL_QUORUM` có ý nghĩa theo RF và local DC thật, không phải “bật bảo đảm mạnh” độc lập topology.

### 12.2. Export: nhiều trang, giới hạn tài nguyên

~~~java
PreparedStatement allInMonth = session.prepare(
    "SELECT order_id, created_at, status, total_amount " +
    "FROM orders_by_customer_month " +
    "WHERE customer_id = ? AND month_bucket = ?"
);

BoundStatement export = allInMonth
    .bind(customerId, "2026-11")
    .setPageSize(500)
    .setConsistencyLevel(ConsistencyLevel.LOCAL_ONE)
    .setTimeout(Duration.ofSeconds(10))
    .setIdempotent(true);
~~~

`LOCAL_ONE` ở đây **chỉ minh họa khi nghiệp vụ cho phép dữ liệu trễ**, không phải khuyến nghị mặc định cho mọi export. Nếu báo cáo phục vụ đối soát giao dịch, có thể cần CL/đường đọc khác. Chọn theo hợp đồng nghiệp vụ.

Bên cạnh statement options, export phải:

1. Có giới hạn tổng thời gian và số row/byte.
2. Xử lý theo stream/page có backpressure, không gom tất cả vào RAM.
3. Giới hạn số export đồng thời để không lấn át API tương tác.
4. Theo dõi fetch count, latency, throughput, errors, retry/speculation.
5. Nếu đọc qua nhiều bucket, có cursor/logic ghép kết quả: Cassandra không sắp xếp toàn cluster bằng một paging state.
6. Định nghĩa hành vi khi dữ liệu bị cập nhật trong lúc phân trang.

### 12.3. Những ca kiểm thử cần có

| Kịch bản | Mong đợi |
| --- | --- |
| `LIMIT 20` và `pageSize=100` | Tổng row không vượt 20 |
| `LIMIT 1000` và `pageSize=100` | Có thể fetch nhiều trang khi tiêu thụ |
| Chỉ cần trang đầu | Không vô tình lặp toàn bộ ResultSet |
| RF3, LOCAL_QUORUM trong một DC | Cần hai replica phản hồi theo giả định khỏe |
| Down một replica trong staging RF3 | Đo availability và latency thực tế |
| Query thiếu `month_bucket` | CQL không khớp partition key ghép |
| Timeout sau INSERT | Trạng thái không rõ, không tự động lặp side effect |
| Counter update bị retry | Có nguy cơ tăng hai lần |
| LWT trả `[applied]=false` | Không coi là ghi mới thành công |
| Named profile timeout 10s nhưng statement đặt 3s | Statement override có ưu tiên |
| Tăng page size quá lớn | Đo network, memory, p99 trước/sau |
| Speculative execution trên SELECT | Đo request rate và cluster load |
| Đọc cùng dữ liệu tại hai DC khác nhau | Không mặc định read-after-write xuyên DC |

## 13. Quan sát và xử lý lỗi

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| Timeout dù tăng page size | Hot partition, tombstone, replica chậm | Query, schema, server metrics |
| Số request thực cao hơn số lần `execute` | Paging, retry hoặc speculative executions | Metrics attempt/page, driver logs |
| Kết quả thiếu/trùng khi phân trang | Sai paging state, query/values thay đổi, concurrent writes | Cursor contract, partition, bucket |
| `UnavailableException` tại LOCAL_QUORUM | Không đủ replica healthy trong DC | RF, local DC, nodetool status |
| Upsert sau retry làm lùi revision | Business version không được bảo vệ | CAS/revision, writer ordering |
| Counter tăng sai | Mutation không idempotent được retry | Idempotency policy, event dedup |
| Export làm chậm API | Nhiều trang/đồng thời quá cao | Concurrency limit, backpressure |
| Thay YAML nhưng timeout không đổi | Nhiều lớp config hoặc statement override | DriverConfig/ExecutionProfile thực tế |
| CL đúng nhưng hai bảng lệch | Read model chưa được đồng bộ | Projection lag, replay và đối soát |

### 13.1. Thứ tự điều tra query chậm

1. Query có đủ partition key và clustering restrictions hợp lệ không?
2. Có `ALLOW FILTERING`, collection lớn hoặc tombstone/partition quá lớn không?
3. Có nhiều page fetch vô tình do iterator không?
4. CL có yêu cầu các replica bị chậm/down không?
5. Driver retry/speculation làm request rate tăng không?
6. Timeout thuộc phía driver, server hay HTTP?
7. Chỉ sau khi có số liệu mới thay page size, timeout hoặc pool.

### 13.2. Thứ tự điều tra ghi timeout

1. Xác định câu CQL có thể tạo side effect gì.
2. Xác định write đã áp dụng chưa, bằng khóa/idempotency key hoặc cơ chế ghi điều kiện.
3. Nếu `[applied]=false`, phân biệt retry cũ với xung đột payload.
4. Kiểm tra writer cạnh tranh, revision và thứ tự event.
5. Kiểm tra các bảng read model có bắt kịp nguồn hay không.
6. Thiết kế retry hữu hạn, logging/tracing và đối soát.

## 14. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Page size là giới hạn tổng row.” | Chỉ mục tiêu mỗi fetch; LIMIT là giới hạn kết quả CQL. |
| “Đã prepare thì query sẽ nhanh bất kể WHERE.” | Prepare không sửa access pattern hoặc partition key. |
| “Một execute luôn tương ứng một round-trip.” | Paging/retry/speculative attempts có thể thêm request. |
| “LOCAL_QUORUM luôn cần ba replica.” | Với RF3 trong một DC, nó thường cần hai. |
| “CL cao đồng bộ mọi bảng denormalized.” | Replication replica khác projection consistency giữa bảng. |
| “Timeout nghĩa là INSERT chưa ghi.” | Kết quả có thể đã áp dụng. |
| “setIdempotent(true) biến UPDATE thành an toàn.” | Flag chỉ mô tả tính an toàn đã được chứng minh. |
| “Đánh dấu true sẽ tự bật speculation.” | Cần policy/config tương ứng. |
| “Counter increment có thể retry vì dùng prepared.” | Counter increment vẫn không lũy đẳng. |
| “TTL không ảnh hưởng tính lũy đẳng.” | Ghi lại có thể thay expiry. |
| “Tăng timeout sửa được hot partition.” | Phải tối ưu schema/query/tải. |
| “Mỗi option khác nhau cần prepare lại.” | BoundStatement mang options riêng. |
| “Page size cho phép nhảy tới trang 10000.” | Cassandra paging theo token/cursor, không phải offset tùy ý. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `setPageSize(100)` có giới hạn query tối đa 100 row không?

*Gợi ý:* Không; client tiếp tục duyệt có thể fetch thêm trang.

**Câu 2.** `LIMIT 20` khác `pageSize=20` như thế nào?

*Gợi ý:* Một cái giới hạn tổng row CQL, cái kia điều khiển kích thước mỗi lần fetch.

**Câu 3.** Với RF3 trong một DC, LOCAL_QUORUM cần bao nhiêu replica phản hồi?

*Đáp án:* Hai.

**Câu 4.** Timeout sau INSERT có chứng minh server chưa ghi không?

*Gợi ý:* Không; có thể response đã mất.

**Câu 5.** Vì sao `setIdempotent(true)` không nên áp dụng hàng loạt cho mọi UPDATE?

*Gợi ý:* Retry cũ, counter, TTL, list append và state transition có thể gây side effect.

**Câu 6.** Vì sao `setTimeout(Duration.ofSeconds(2))` của một export nhiều trang không đảm bảo cả export tối đa hai giây?

*Gợi ý:* Các trang sau cần thêm fetch và logic xử lý riêng; phải có deadline toàn công việc.

**Câu 7.** Nếu execution profile timeout 10 giây nhưng statement đặt 3 giây, cái nào có hiệu lực?

*Đáp án:* Override trực tiếp trên statement.

**Câu 8.** `LOCAL_SERIAL` dùng cho trường hợp nào?

*Gợi ý:* Pha serial của LWT, không phải consistency mặc định cho mọi SELECT.

**Câu 9.** Paging state của một customer có thể dùng cho customer khác không?

*Gợi ý:* Không; token gắn với query và bound values tương ứng.

**Câu 10.** `CassandraRepository.findById` có tự sử dụng một BoundStatement do code khác tạo không?

*Gợi ý:* Không; repository phát sinh truy vấn riêng theo Spring Data và driver config của session.

## 16. Checklist production

- **Access pattern:** Bảng, partition key và clustering key đúng truy vấn.
- **Prepare:** CQL cố định được prepare và tái sử dụng; giá trị được bind theo type.
- **Statement:** Mỗi request nhận bound statement riêng; giữ giá trị trả về của các setter immutable.
- **Paging:** LIMIT đúng hợp đồng; page size theo payload/p99; cursor ràng buộc với query.
- **Consistency:** Xét RF, local DC, multi-DC, SLA và chấp nhận dữ liệu trễ.
- **Timeout:** Có ngân sách HTTP/driver/server; không retry mù khi mutation không rõ kết quả.
- **Idempotency:** Phân loại thao tác; không đánh dấu counter/list append không an toàn là true.
- **Retry/speculation:** Đo attempt bổ sung, tail latency và tải cluster.
- **LWT:** Chỉ dùng khi cần điều kiện; đọc `[applied]` và xử lý CAS failure.
- **Profiles:** Một nơi sở hữu mỗi default; biết statement override ưu tiên.
- **Spring Data:** Dùng repository/template cho entity mapping; adapter CqlSession nếu cần options đặc thù.
- **Vận hành:** Theo dõi page count, timeout, unavailable, p95/p99, tombstone, partition size và projection lag.
- **Kiểm thử:** Timeout sau ghi, mất replica, retry trùng request, paging nhiều trang, writer cạnh tranh và multi-DC.

## Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.x — Documentation](https://apache.github.io/cassandra-java-driver/4.19.0/): prepared/bound statements, paging, query profiles và configuration.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): primary keys, SELECT/LIMIT, consistency và conditional statements.
- [Spring Data Cassandra — Reference](https://docs.spring.io/spring-data/cassandra/reference/): entity mapping, repository và CassandraTemplate.
- [Spring Boot — NoSQL Support](https://docs.spring.io/spring-boot/reference/data/nosql.html): cấu hình Cassandra và tích hợp CqlSession.

## Kết luận

Trong Apache Cassandra Java Driver 4.x, hãy **prepare CQL một lần và bind cho từng request**. `setPageSize` chỉ điều khiển lượt fetch, `setConsistencyLevel` chọn ngưỡng phản hồi replica, `setTimeout` giới hạn thời gian chờ phía client, còn `setIdempotent` thông báo tính an toàn khi statement được gửi lại. Các lựa chọn có thể đặt trên `BoundStatement` hoặc kế thừa execution profile, nhưng không tự thay đổi dữ liệu hay ngữ nghĩa nghiệp vụ.

Với **SPRING_DATA_CASSANDRA**, Spring Data repository và `CassandraTemplate` hỗ trợ mapping/thực thi, còn `CqlSession` cho phép kiểm soát trực tiếp statement khi cần. Muốn ứng dụng đáng tin cậy trên Cassandra phân tán, hãy bắt đầu từ **bảng theo truy vấn và partition key đúng**, rồi phối hợp paging, RF/CL, timeout, retry, LWT, idempotency và observability theo SLA. Hiệu năng bền vững và tính đúng đắn đến từ thiết kế tổng thể, không phải chỉ tăng fetch size hay timeout.