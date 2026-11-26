# Tính không lũy đẳng khi thử lại cập nhật counter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **counter** trong Apache Cassandra là loại dữ liệu đặc biệt dùng cho phép **tăng/giảm** và khác cột `bigint` thông thường.
- Chứng minh bằng ví dụ vì sao `UPDATE ... SET views = views + 1` **không lũy đẳng (non-idempotent)**: gửi hai lần có thể tăng hai đơn vị.
- Phân tích **timeout có kết quả không rõ**: request có thể đã được replica áp dụng dù client không nhận được xác nhận; retry mù có thể đếm đôi.
- Phân biệt retry ở **HTTP client, gateway, Spring service, Java Driver, message consumer và batch job**, đồng thời kiểm soát speculative execution.
- Biết cách đánh dấu `setIdempotent(false)` cho counter mutation bằng Apache Cassandra Java Driver 4.x và không hiểu sai ý nghĩa của flag này.
- Hiểu tác động của **consistency level, replication factor, node failure** tới mức xác nhận ghi, nhưng không nhầm consistency với cơ chế khử trùng lệnh tăng.
- Sử dụng đúng CQL cho counter, ràng buộc của bảng counter, prepared statement, `CqlSession` và vai trò của Spring Data Cassandra repository/`CassandraTemplate`.
- Chọn kiến trúc phù hợp: counter native cho số liệu chấp nhận sai lệch nhỏ; event log + deduplication + projection có thể xây dựng lại cho yêu cầu đếm theo event; `bigint` + LWT cho bất biến mạnh.
- Thiết kế kiểm thử timeout sau commit, retry ở nhiều tầng, broker redelivery, deduplication không nguyên tử, hot partition và hoạt động đa DC.
- Có checklist vận hành về p95/p99, counter drift, throughput, repair/compaction, lỗi và reconciliation.

Bài thuộc chương **Bộ đếm** của **SPRING_DATA_CASSANDRA**, mô-đun truy cập Apache Cassandra qua entity mapping, repository, `CassandraTemplate` và truy vấn CQL. Thiết kế bảng theo truy vấn, partition key, consistency, paging và hiệu năng vẫn là nền tảng: counter không thay thế được việc giới hạn kích thước partition, phân tán tải hay quản lý event trùng trong một hệ thống phân tán.

> **Ghi nhớ:** `counter = counter + 1` là **một hiệu ứng cộng thêm**, không phải gán giá trị cố định. Nếu cùng một thao tác được thực hiện hai lần, kết quả có thể tăng hai lần. **Prepared statement, LOCAL_QUORUM, retry policy và idempotency key riêng lẻ không tự biến counter thành exactly-once.**

## 1. Counter là gì và dùng khi nào?

Cassandra có kiểu dữ liệu đặc biệt `counter` để lưu số được thay đổi bằng phép cộng/trừ. Một số ví dụ:

- Tổng lượt xem của một trang theo ngày.
- Số lần một API endpoint được gọi trong một khoảng quan sát.
- Tổng số thao tác đã thực hiện, khi dashboard **chấp nhận độ sai lệch** do retry, thất bại hoặc đồng bộ trễ.
- Bộ đếm mang tính thống kê/tham khảo, không quyết định chuyển tiền, định giá hay phân phối hàng tồn kho.

Ví dụ bảng:

~~~sql
CREATE KEYSPACE IF NOT EXISTS metrics
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS metrics.page_views_by_day (
    page_id uuid,
    day_bucket date,
    views counter,
    PRIMARY KEY ((page_id, day_bucket))
);
~~~

`dc1` và RF=3 chỉ để minh họa. Trong production, tên DC và replication phải tương ứng topology thật. Partition key `(page_id, day_bucket)` giúp giới hạn dữ liệu theo ngày và cho phép lookup một counter cụ thể; tuy nhiên **một trang rất nổi tiếng** vẫn có thể biến partition đó thành hot key.

Câu cập nhật:

~~~sql
UPDATE metrics.page_views_by_day
SET views = views + 1
WHERE page_id = 11111111-1111-4111-8111-111111111111
  AND day_bucket = '2026-11-25';
~~~

Đọc lại:

~~~sql
SELECT views
FROM metrics.page_views_by_day
WHERE page_id = 11111111-1111-4111-8111-111111111111
  AND day_bucket = '2026-11-25';
~~~

Trong bảng counter, `views` không phải một cột `bigint` để gán tùy ý bằng `SET views = 100`. CQL counter dành cho **thay đổi tương đối**: `views = views + delta` hoặc `views = views - delta`.

### 1.1. Phân biệt counter với bigint

| Tiêu chí | CQL `counter` | CQL `bigint` |
| --- | --- | --- |
| Mục tiêu | Tăng/giảm bằng delta | Lưu một giá trị số nguyên 64-bit |
| Ghi thông thường | `UPDATE SET views = views + 1` | `INSERT/UPDATE SET views = 123` |
| Gửi lại cùng lệnh | **Có thể tăng thêm lần nữa** | Gán cùng giá trị thường có kết quả cuối giống nhau trong điều kiện nhất định |
| Điều kiện CAS theo version | Không áp dụng LWT trực tiếp trên counter | Có thể dùng `UPDATE ... IF version = ?` trên bảng thường |
| Dữ liệu khác trong cùng bảng | Bảng counter có ràng buộc đặc biệt | Có thể có các cột thường khác |
| TTL / custom write timestamp | Không dùng như với cột thường | Có hỗ trợ tùy mutation/điều kiện |
| Phù hợp chính xác tài chính/inventory | Thường không | Có thể, nếu kèm đồng thuận/version và business invariant |

Từ “counter” trong một DTO Java không quyết định ngữ nghĩa lưu trữ. Một `long viewCount` map tới cột CQL `counter` chịu ràng buộc khác hẳn `long viewCount` map tới `bigint`.

### 1.2. Lũy đẳng (idempotency) là gì?

Một thao tác `f` được gọi là lũy đẳng nếu lặp lại thao tác với cùng đầu vào không tạo hiệu ứng bổ sung so với thực hiện một lần, trong những giả định đang xét:

~~~text
f(f(x)) = f(x)
~~~

Hai phép biến đổi:

~~~text
Gán tuyệt đối:
  f(x) = 100
  f(f(42)) = 100 = f(42)

Tăng tương đối:
  g(x) = x + 1
  g(g(42)) = 44 ≠ 43 = g(42)
~~~

Đối với counter:

~~~sql
UPDATE metrics.page_views_by_day
SET views = views + 1
WHERE page_id = ? AND day_bucket = ?;
~~~

Nếu database thực thi thành công hai lần thì số đếm thay đổi hai lần. Điều này đúng **dù hai lần gửi sử dụng cùng prepared statement, cùng partition key, cùng delta và cùng nội dung request**.

### 1.3. Những bài toán không nên dùng counter native

Nếu yêu cầu là:

- “Không được bán vượt quá 10 sản phẩm còn kho.”
- “Một giao dịch thanh toán chỉ được trừ tiền **đúng một lần**.”
- “Một voucher chỉ được sử dụng tối đa N lần, chống mọi request cạnh tranh.”
- “Báo cáo kế toán phải đối soát được chính xác theo giao dịch.”
- “Mỗi event ID chỉ được tính vào tổng **đúng một lần**, kể cả khi broker phát lại.”

thì counter native đơn lẻ thường **không đáp ứng**. Bạn cần dữ liệu nguồn có ID ổn định, cơ chế conditional/coordination hoặc công cụ giao dịch thích hợp; phần 10–12 bàn về các lựa chọn này.

## 2. Cú pháp CQL và các hạn chế quan trọng

### 2.1. Tăng, giảm và đọc

~~~sql
-- Tăng ba lượt:
UPDATE metrics.page_views_by_day
SET views = views + 3
WHERE page_id = ? AND day_bucket = ?;

-- Giảm một lượt:
UPDATE metrics.page_views_by_day
SET views = views - 1
WHERE page_id = ? AND day_bucket = ?;

-- Đọc một bucket:
SELECT views
FROM metrics.page_views_by_day
WHERE page_id = ? AND day_bucket = ?;
~~~

Mỗi lệnh tăng/giảm là một mutation có side effect. `views - 1` không có tính lũy đẳng hơn `views + 1`: retry có thể trừ hai lần.

### 2.2. Bảng counter phải tuân thủ schema riêng

Không nên tạo bảng như:

~~~sql
-- Không hợp lệ về mô hình counter:
CREATE TABLE page_views_invalid (
    page_id uuid PRIMARY KEY,
    views counter,
    page_title text
);
~~~

Trong bảng có counter, các **cột không phải primary key** phải thuộc kiểu counter theo những ràng buộc của Cassandra. Bạn không thể trộn `views counter` và `page_title text` như các cột thông thường; hãy lưu metadata trang ở bảng riêng, chẳng hạn `pages_by_id`.

Các thao tác thông thường cũng bị giới hạn:

- Không gán counter bằng `INSERT INTO ... VALUES (100)` như cột số thường.
- Không dùng `UPDATE SET views = 100` để “reset”.
- Không gắn `USING TTL` hay `USING TIMESTAMP` cho counter mutation theo cách của bảng thường.
- Không sử dụng `IF version = ?`, `IF EXISTS` hoặc `IF NOT EXISTS` trực tiếp để biến phép tăng counter thành LWT/CAS.
- Không trộn counter mutation với regular mutation trong cùng một batch để tạo giao dịch nguyên tử.

Những hạn chế là lý do cần lựa chọn mô hình dữ liệu từ yêu cầu nghiệp vụ, không phải chỉ thay `bigint` bằng `counter` trong schema hiện tại.

### 2.3. COUNTER BATCH không biến thành exactly-once

Cassandra hỗ trợ cú pháp batch dành cho counter:

~~~sql
BEGIN COUNTER BATCH
    UPDATE metrics.page_views_by_day
    SET views = views + 1
    WHERE page_id = 11111111-1111-4111-8111-111111111111
      AND day_bucket = '2026-11-25';

    UPDATE metrics.page_views_by_day
    SET views = views + 1
    WHERE page_id = 22222222-2222-4222-8222-222222222222
      AND day_bucket = '2026-11-25';
APPLY BATCH;
~~~

**Không hiểu nhầm:** `COUNTER BATCH` không phải transaction với ID duy nhất để khử trùng lần gửi lại. Khi một batch đã được áp dụng nhưng phản hồi mất, retry **cả batch** vẫn có thể cộng lại những counter được xử lý. Batch nhiều partition còn có chi phí điều phối, không phải cách thay thế event ledger hay exactly-once processing.

Trong một workload, phải xem xét có cần batch thật hay chỉ cần những cập nhật đơn lẻ theo partition; đừng gom hàng nghìn counter mutations vào một batch chỉ để “tăng hiệu năng”.

## 3. Tình huống lỗi: counter tăng nhưng phản hồi bị mất

Giả sử số lượt xem trang đang là 100. Browser gửi event `view-123`, service cập nhật:

~~~sql
UPDATE metrics.page_views_by_day
SET views = views + 1
WHERE page_id = ? AND day_bucket = ?;
~~~

Dòng thời gian:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Spring Boot API
    participant D as Java Driver
    participant C as Cassandra
    B->>A: POST view event-123
    A->>D: UPDATE views = views + 1
    D->>C: Gửi counter mutation
    C->>C: Đã áp dụng phép cộng
    C--xD: Phản hồi bị mất/chậm
    D-->>A: Timeout
    A-->>B: HTTP 503 / unknown outcome
    B->>A: Retry cùng event-123
    A->>D: UPDATE views = views + 1
    D->>C: Gửi mutation lần thứ hai
    C->>C: Áp dụng phép cộng thêm
    Note over A,C: Có thể đếm 102 thay vì 101
~~~

Cassandra có thể **đã áp dụng** update nhưng client timeout do network, coordinator chậm, driver request deadline hoặc phản hồi mất. Không thể suy từ một timeout rằng “database chắc chắn chưa tăng”.

### 3.1. Ba trạng thái khi client gửi counter update

| Điều client thấy | Điều có thể kết luận | Cách xử lý |
| --- | --- | --- |
| Request thành công theo CL | Cassandra đã phản hồi theo ngưỡng đã chọn | Cập nhật được xác nhận, nhưng đây vẫn không phải event deduplication |
| Server/driver timeout | Kết quả **không rõ**; có thể đã áp dụng toàn bộ, một phần hoặc chưa áp dụng | Không retry mù nếu cần chính xác; đối soát bằng event ID/dữ liệu nguồn |
| Network disconnect | Không biết server đã nhận/chạy chưa | Không coi lỗi kết nối là bằng chứng thao tác chưa xảy ra |

Một số request lỗi có thể là unavailable trước khi coordinator thực hiện mutation; nhưng **không phải mọi loại lỗi** đều an toàn để thử lại. Phải phân loại lỗi theo driver/server, và quan trọng hơn là định nghĩa yêu cầu chính xác nghiệp vụ.

### 3.2. Bảng ví dụ hai kết cục cùng một timeout

~~~text
Bắt đầu: views=100

Trường hợp A — lần đầu chưa được áp dụng:
  UPDATE #1 -> timeout trước khi thực thi
  UPDATE #2 -> +1
  Giá trị cuối có thể là 101

Trường hợp B — lần đầu đã được áp dụng:
  UPDATE #1 -> +1, phản hồi mất
  UPDATE #2 -> +1
  Giá trị cuối có thể là 102
~~~

Từ góc nhìn service sau timeout, hai trường hợp có thể không phân biệt được chỉ bằng trạng thái response. **Đọc lại số tổng không đủ** nếu nhiều request khác cũng đang tăng, bởi bạn không biết thay đổi nào thuộc `event-123`.

### 3.3. Vì sao đọc lại counter cũng chưa chắc giải quyết được?

Giả sử sau timeout API đọc `views=101`. Bạn vẫn không biết:

- 101 là do event hiện tại được áp dụng;
- hay do một event khác từ người dùng khác;
- hoặc có hai event được áp dụng nhưng một lần trừ hay sai lệch từ trước.

Counter chỉ lưu **giá trị tổng**, không lưu ánh xạ từ `event_id` đến việc tổng đã được cộng hay chưa. Nếu cần kết luận theo event, phải có **nguồn dữ liệu/sổ sự kiện** mang danh tính từng thao tác.

## 4. Retry có thể xảy ra ở những tầng nào?

Một ứng dụng thường có nhiều lớp retry cùng lúc:

~~~mermaid
flowchart TD
    A["Mobile/Web client retry"] --> B["Ingress/Gateway retry"]
    B --> C["Spring Service retry (@Retryable)"]
    C --> D["Java Driver retry/speculative policy"]
    D --> E["Cassandra counter mutation"]
    F["Broker redelivery"] --> C
    G["Scheduler/backfill replay"] --> C
~~~

| Tầng | Tình huống phát lại | Nguy cơ |
| --- | --- | --- |
| Browser/mobile | HTTP 5xx, mạng yếu, user bấm lại | Một event logic thành nhiều HTTP requests |
| Load balancer/gateway | Upstream timeout/retry policy | Service xử lý cùng request nhiều lần |
| Spring Retry / Resilience4j | Retry exception ở method tăng | Đếm đôi nếu lần đầu đã ghi |
| Java Driver | Retry policy hoặc speculative attempt được cho phép | Có thể phát thêm CQL attempts |
| Message broker consumer | Ack mất, consumer crash trước commit offset | Event đã ghi counter nhưng được nhận lại |
| Batch job/replay | Re-run công việc sau failure hoặc backfill | Một sự kiện có thể được cộng lại |
| Manual operation | Operator phát lại script để sửa lỗi | Không biết mutation nào đã thành công |

**Không có một flag tại tầng driver nào kiểm soát toàn bộ chuỗi này.** Kể cả khi driver không tự retry counter, API, broker hoặc người vận hành vẫn có thể phát lại cùng ý định nghiệp vụ.

### 4.1. Retry ở nhiều tầng làm tăng độ khó dự báo

Ví dụ:

~~~text
Client gửi 1 request.
Gateway có thể thử tối đa 2 lần.
Spring retry mỗi attempt tối đa 3 lần.
Driver cũng có policy riêng.
Broker có thể giao lại message sau crash.
~~~

Không nên nhân các con số này rồi tuyên bố có đúng N mutations, vì các tầng có điều kiện retry, timeout và concurrency khác nhau. Nhưng rủi ro tổng quát là **một event có nhiều cơ hội thực thi**. Phải kiểm toán policy ở **mọi tầng** và xác định nơi nào sở hữu quyết định thử lại.

### 4.2. Timeout không phải lệnh hủy mutation

`setTimeout(Duration.ofSeconds(2))` ở Java Driver giới hạn thời gian client chờ request. Khi timeout, coordinator/replicas có thể vẫn đang xử lý, hoặc một số replica đã nhận mutation. Không viết code dựa trên giả định hễ client nhận exception thì server tự rollback counter increment.

Ngay cả khi hủy HTTP request phía caller, các side effects đã được gửi tới Cassandra có thể không đảo ngược.

## 5. Java Driver 4.x: prepared statement không khử trùng counter

Dùng `PreparedStatement` để bind giá trị và tái sử dụng CQL là cách đúng, nhưng đây chỉ là tối ưu/đúng kiểu tham số, **không** thêm tính lũy đẳng.

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class PageViewCounterDao {

    private final CqlSession session;
    private final PreparedStatement increment;

    public PageViewCounterDao(CqlSession session) {
        this.session = session;
        this.increment = session.prepare(
            "UPDATE metrics.page_views_by_day " +
            "SET views = views + ? " +
            "WHERE page_id = ? AND day_bucket = ?"
        );
    }

    public void addViews(UUID pageId, LocalDate day, long delta) {
        if (delta <= 0) {
            throw new IllegalArgumentException("delta must be positive");
        }

        BoundStatement statement = increment
            .bind(delta, pageId, day)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(2))
            .setIdempotent(false);

        session.execute(statement);
    }
}
~~~

**Giải thích từng điểm:**

1. `prepare` một lần cho query cố định; `bind` theo thứ tự tham số.
2. `delta` kiểu Java `long` phù hợp phép tăng counter.
3. `pageId` và `day` ràng buộc đầy đủ partition key.
4. `LOCAL_QUORUM` là lựa chọn minh họa theo RF/local DC, không phải “chế độ exactly-once”.
5. `setTimeout` đặt deadline phía driver, không tạo rollback.
6. `setIdempotent(false)` **khai báo thao tác không lũy đẳng** để driver/policy không tùy tiện coi nó an toàn cho retry/speculative execution.
7. **Không** tự động gọi lại `addViews` khi bắt `DriverTimeoutException` nếu business không cho phép đếm trùng.

### 5.1. Đánh dấu idempotent là metadata, không phải phép biến đổi

~~~java
BoundStatement statement = increment
    .bind(1L, pageId, day)
    .setIdempotent(false);
~~~

`setIdempotent(Boolean)` thông báo cho Java Driver về tính an toàn của việc lặp attempt. Driver có thể dựa vào cờ này khi retry/speculation, tùy policy và loại lỗi.

**Sai về mặt ngữ nghĩa:**

~~~java
BoundStatement unsafe = increment
    .bind(1L, pageId, day)
    .setIdempotent(true); // KHÔNG làm UPDATE trở thành idempotent.
~~~

Đặt `true` không khiến Cassandra nhận ra request ID và bỏ qua delta đã được cộng. Nếu muốn tự động retry qua driver, phải có bằng chứng thật rằng mutation **không tạo side effect thêm** — điều mà counter increment thông thường không đáp ứng.

### 5.2. Statement của Driver 4.x mang tính immutable

Một lỗi khác:

~~~java
BoundStatement original = increment.bind(1L, pageId, day);

// Đừng bỏ giá trị trả về:
original.setIdempotent(false);

// Dùng statement được trả về:
BoundStatement configured = original.setIdempotent(false);
session.execute(configured);
~~~

Các setter trên `BoundStatement` trả một statement mới theo API immutable. Không chia sẻ một builder mutable cho nhiều request đồng thời. Mỗi HTTP event nên có bound statement của riêng nó, nhưng **sự riêng biệt của object Java cũng không khử trùng cùng event nghiệp vụ**.

### 5.3. Đọc counter an toàn

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement select = session.prepare(
    "SELECT views FROM metrics.page_views_by_day " +
    "WHERE page_id = ? AND day_bucket = ?"
);

Row row = session.execute(select.bind(pageId, day)).one();

Long views = row == null || row.isNull("views")
    ? null
    : row.getLong("views");
~~~

Phân biệt “chưa có row” và “counter có giá trị bằng 0” theo contract. Không tự suy rằng row null nghĩa là một counter được ghi có giá trị zero. Việc tạo/khởi tạo counter cũng phải tuân quy tắc CQL riêng; với dữ liệu chưa tồn tại, API có thể quy ước hiển thị 0 nhưng nên nói rõ đó là **quy ước ứng dụng**.

## 6. Consistency level không tạo idempotency

Giả sử keyspace `metrics` dùng RF=3 trong một DC:

| Consistency level | Ngưỡng phản hồi điển hình | Có khử trùng retry counter? |
| --- | --- | --- |
| `LOCAL_ONE` | Một replica tại DC cục bộ | **Không** |
| `LOCAL_QUORUM` | Hai trong ba replica cục bộ | **Không** |
| `QUORUM` | Hai trong ba replica ở ví dụ một DC | **Không** |
| `ALL` | Cả ba replica | **Không** |

Một lệnh tăng counter có thể được coordinator áp dụng nhưng response không tới được client ở **bất kỳ** CL nào. Nếu client thử lại, đó là một mutation cộng thêm mới; regular CL không dựa trên event ID để quyết định “đã xử lý rồi”.

### 6.1. Vì sao LOCAL_QUORUM vẫn hữu ích?

`LOCAL_QUORUM` giúp ràng buộc ngưỡng replica phản hồi theo chính sách của keyspace trong DC hiện tại. Nó có thể hữu ích cho SLA và cách ứng dụng nhìn thấy dữ liệu. Tuy nhiên:

- Không tạo giao dịch exactly-once.
- Không chống double increment khi retry.
- Không thay thế việc xử lý network partition, unavailable và timeout.
- Không tự đồng bộ read model ở các bảng khác.
- Không bảo đảm counter là “số sự kiện duy nhất được xử lý”, vì schema counter không chứa event ID.

### 6.2. Multi-DC và khả năng quan sát

Nếu keyspace dùng `dc1:3` và `dc2:3`, một writer ở `dc1` chọn `LOCAL_QUORUM` sẽ chỉ yêu cầu quorum trong `dc1` theo chính sách. Reader ở `dc2` dùng `LOCAL_ONE` có thể thấy giá trị trễ. Độ trễ đó là vấn đề **read visibility/replication**, khác với việc một event bị cộng hai lần.

Khi đo độ chính xác, cần phân biệt:

- **Drift do retry trùng**: event logic có nhiều mutations.
- **Read lag do replica/DC**: event đã được cộng nhưng một reader chưa thấy ngay.
- **Event loss ở upstream**: event không được gửi hoặc không được xử lý.
- **Projection lag**: bảng tổng hợp khác chưa cập nhật.
- **Đếm theo thời điểm**: hai request đang đồng thời cập nhật/đọc không tạo snapshot toàn hệ thống.

Tăng consistency không giải quyết mọi nguyên nhân trong danh sách trên.

## 7. Idempotency key ở HTTP chưa đủ nếu mutation không đi cùng giao dịch

Giả sử API nhận:

~~~http
POST /pages/{pageId}/views
Idempotency-Key: event-123
Content-Type: application/json

{"occurredAt":"2026-11-25T10:00:00Z"}
~~~

Ý tưởng đầu tiên là lưu `event-123` rồi chỉ tăng counter nếu đây là event mới. Nhưng hai thao tác riêng không thể được coi như một giao dịch atomic với counter.

### 7.1. Thứ tự A — ghi marker trước, rồi tăng counter

~~~text
1. INSERT event-123 IF NOT EXISTS -> applied=true.
2. Service bị crash trước khi UPDATE counter += 1.
3. Broker/client retry event-123.
4. INSERT marker -> applied=false, service bỏ qua.
5. Counter bị THIẾU một đơn vị vĩnh viễn nếu không có reconciliation.
~~~

LWT trên bảng marker giúp xác định event ID, nhưng không tự đảm bảo **cộng đã xảy ra**.

### 7.2. Thứ tự B — tăng counter trước, rồi ghi marker

~~~text
1. UPDATE counter += 1 được áp dụng.
2. Service crash trước khi lưu marker event-123.
3. Broker/client retry event-123.
4. Không thấy marker nên UPDATE counter += 1 lần nữa.
5. Counter bị THỪA một đơn vị.
~~~

Không có thứ tự đơn giản nào tự làm hai bước trên atomic.

### 7.3. COUNTER BATCH hoặc logged batch có cứu được không?

Không. Counter updates có semantic riêng và không được gộp tùy ý với regular/LWT marker writes trong một giao dịch trên nhiều bảng. Một `COUNTER BATCH` vẫn có rủi ro khi retry. Logged batch cũng không biến `INSERT IF NOT EXISTS` marker + counter increment thành một cross-table exactly-once transaction.

**Bài học:** Một event ledger có ID là nền tảng tốt, nhưng phải thiết kế **đường tổng hợp có thể replay/reconcile** hoặc lựa chọn cơ sở dữ liệu/cơ chế giao dịch có bảo đảm phù hợp. Không dừng lại ở pseudo-code “if unseen then increment”.

## 8. Ba chiến lược kiến trúc theo yêu cầu độ chính xác

Trước khi tối ưu CQL, cần hỏi: **một event bị tính hai lần hoặc bị bỏ sót có được chấp nhận hay không, và có thể tính lại tổng từ dữ liệu nguồn không?**

| Chiến lược | Khi phù hợp | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **A. Native counter** | Metric tham khảo, sai lệch nhỏ được chấp nhận | CQL tăng/giảm đơn giản | Retry không idempotent, không truy vết từng event |
| **B. Immutable event log + derived total** | Audit, cần dedup theo event ID, rebuild/đối soát | Có nguồn sự thật để tái tổng hợp | Thêm storage/pipeline; tổng có thể cập nhật trễ |
| **C. Bigint + LWT/CAS** | Ràng buộc bất biến ở một row, như tồn kho không âm | Kiểm tra version/state trước mutation | Chi phí Paxos, contention, không atomic với hệ thống ngoài |

Một dashboard hiển thị “khoảng 2,3 triệu lượt xem” có thể chọn **A** với hợp đồng về độ trễ/sai số. Một báo cáo doanh thu hay giới hạn quota thường đòi **B/C** hoặc hệ thống giao dịch có semantics mạnh hơn.

### 8.1. Counter gần đúng cũng phải quản trị

Ngay cả khi có thể chấp nhận một số lỗi đếm:

- Định nghĩa độ sai lệch chấp nhận được theo thời gian, theo ngày và theo sản phẩm.
- Giám sát timeout, retries, request rate, hot partitions.
- Không bật speculative execution hoặc tự retry mù counter.
- Có chiến lược reconciliation lấy mẫu hoặc nguồn quan sát độc lập.
- Tách số ước lượng dùng trong UI khỏi số chính thức dùng để thanh toán.

Không dùng tên cột `transactionCount` hay annotation Java để thay đổi semantics của CQL `counter`.

## 9. Dùng event log bất biến làm nguồn dữ liệu

Nếu mỗi lượt xem có `event_id` ổn định, lưu event riêng trước khi tính tổng:

~~~sql
CREATE TABLE metrics.view_events_by_page_day_shard (
    page_id uuid,
    day_bucket date,
    shard_id int,
    event_id uuid,
    occurred_at timestamp,
    source text,
    PRIMARY KEY ((page_id, day_bucket, shard_id), event_id)
);
~~~

`shard_id` phải được tính ổn định từ `event_id` (theo thuật toán đã định nghĩa và version hóa). Cùng event bị phát lại phải tới **cùng partition và primary key**; nếu chọn shard ngẫu nhiên mỗi attempt, hệ thống sẽ không nhận ra duplicate.

### 9.1. Lưu một event có điều kiện

~~~sql
INSERT INTO metrics.view_events_by_page_day_shard (
    page_id, day_bucket, shard_id, event_id, occurred_at, source
)
VALUES (?, ?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Đây là **LWT trên bảng dữ liệu thường**, không phải phép cập nhật counter. Trong phạm vi khóa và serial consistency đã được thiết kế đúng, event ID có thể được bảo vệ khỏi tạo thêm row cùng khóa.

- `[applied]=true`: event row vừa được chấp nhận.
- `[applied]=false`: row đã tồn tại; cần đối chiếu payload/source để phân biệt retry hợp lệ với reuse ID sai.
- Timeout: trạng thái chưa rõ; đọc/đối soát theo primary key và request ID, không suy từ exception.

Nếu nhiều data center cùng có quyền ghi sự kiện trùng, lựa chọn `SERIAL` / `LOCAL_SERIAL` phải khớp phạm vi uniqueness cần bảo vệ. Một local serial ở hai vùng khác nhau không tự bảo đảm tính duy nhất toàn cầu.

### 9.2. Rebuild được mới là khác biệt quan trọng

Với event source có ID, định nghĩa tổng:

~~~text
totalViews(page, day)
  = số event_id hợp lệ và duy nhất
    trong các shard thuộc page và day.
~~~

Projector có thể đọc từng partition và tổng hợp. Nếu projector crash, nó có thể **tính lại từ đầu hoặc từ một checkpoint được chứng minh an toàn**. Không cần đoán một phép `counter + 1` trước đó đã được áp dụng hay chưa.

Đừng chạy `COUNT(*)` qua hàng triệu events cho mỗi HTTP request. Việc tính tổng có thể là job/stream riêng, sử dụng paging, backpressure, checkpoint và giới hạn tài nguyên.

### 9.3. Sharding là đánh đổi để phân tán hot partition

Đối với trang có rất nhiều lượt xem, một partition theo `(page_id, day_bucket)` có thể lớn/nóng. Thêm `shard_id` giúp phân tán tải nhưng phải đọc nhiều shards để tổng hợp. Quy tắc shard ổn định đảm bảo một event có đúng một địa chỉ nguồn; không tự bảo đảm projector exactly-once nếu projector vẫn dùng counter increment không idempotent.

### 9.4. Broker redelivery sau khi ghi event

~~~mermaid
flowchart TD
    A["Broker phát Event E123"] --> B["INSERT E123 IF NOT EXISTS"]
    B --> C{"Kết quả?"}
    C -->|true| D["Event row đã lưu"]
    C -->|false| E["Kiểm tra cùng ID/payload"]
    C -->|timeout| F["Đối soát theo event key"]
    D --> G["Ack theo ingest contract"]
    E --> G
    F --> G
    G --> H["Projector đọc immutable events"]
    H --> I["Tính total theo generation"]
~~~

Nếu consumer crash trước ack, broker có thể phát lại, nhưng row event có ID ổn định giúp phân biệt retry. Việc ghi Cassandra và commit broker offset vẫn không mặc định là một transaction xuyên hai hệ thống.

## 10. Ghi tổng tuyệt đối bằng bigint và generation

Tổng được tính từ event source nên lưu trong **bảng thường**, tránh phép cộng mù:

~~~sql
CREATE TABLE metrics.page_view_totals_by_day (
    page_id uuid,
    day_bucket date,
    total_views bigint,
    generation bigint,
    calculated_at timestamp,
    PRIMARY KEY ((page_id, day_bucket))
);
~~~

Một projector đã tính toàn bộ source snapshot có thể ghi giá trị tuyệt đối:

~~~sql
UPDATE metrics.page_view_totals_by_day
SET total_views = ?,
    calculated_at = ?
WHERE page_id = ? AND day_bucket = ?;
~~~

Lặp lại phép gán cùng giá trị trong điều kiện không có writer cạnh tranh thường không nhân đôi số tổng. Tuy nhiên vẫn phải giải quyết **job cũ ghi sau job mới**.

### 10.1. Vì sao cần version/generation?

~~~text
Job A: đọc snapshot đời 10, tổng = 100.
Job B: đọc snapshot đời 11, tổng = 110.

B ghi 110 thành công.
A bị timeout, retry muộn và ghi 100 với write timestamp mới.
Nếu UPDATE vô điều kiện, tổng có thể lùi về 100.
~~~

Dùng CAS khi row có `generation=10`:

~~~sql
UPDATE metrics.page_view_totals_by_day
SET total_views = 110,
    generation = 11,
    calculated_at = ?
WHERE page_id = ?
  AND day_bucket = ?
IF generation = 10;
~~~

Khi row chưa tồn tại, dùng `INSERT ... IF NOT EXISTS` hoặc một quy tắc khởi tạo nhất quán. Nếu CAS thất bại, đọc lại generation rồi quyết định liệu dữ liệu tính toán còn hợp lệ không. **Cassandra không tự ưu tiên generation lớn hơn** nếu không có điều kiện/writer ordering.

### 10.2. Vì sao marker + counter vẫn không đủ?

Hai cách xử lý ngây thơ đều có cửa sổ lỗi:

~~~text
A. Ghi marker(E123) rồi counter += 1:
   crash sau marker trước counter -> thiếu đếm

B. Counter += 1 rồi ghi marker(E123):
   crash sau counter trước marker -> retry -> đếm đôi
~~~

Ngay cả một LWT để tạo marker cũng không thể làm hai mutation **marker và counter** tự trở thành atomic. Thay đổi kiến trúc là dùng marker/event row làm **nguồn sự thật**, còn total được **tái tính** và ghi tuyệt đối theo generation hoặc chủ thể điều phối.

### 10.3. Số nhanh và số đối soát là hai contract

Một hệ thống có thể trả:

~~~json
{
  "pageId": "11111111-1111-4111-8111-111111111111",
  "estimatedViews": 120347,
  "reconciledViews": 120112,
  "reconciledAsOf": "2026-11-25T10:00:00Z"
}
~~~

Con số chỉ minh họa. `estimatedViews` có thể lấy từ counter native cho UI; `reconciledViews` lấy từ event log theo một checkpoint rõ ràng, dùng khi cần đối soát. Không âm thầm dùng số ước lượng để tính tiền hoặc enforce quota chính xác.

## 11. Với tồn kho hoặc quota: dùng bigint + LWT thay counter

Bài toán: còn 10 sản phẩm, hai request cùng đặt 7. Nếu chỉ có counter:

~~~sql
-- Không có bảo vệ remaining >= 0:
UPDATE inventory_counter
SET remaining = remaining - 7
WHERE sku_id = ?;
~~~

Hai mutation có thể làm số còn lại âm. Counter không cung cấp conditional decrement phù hợp để ràng buộc `remaining >= 7` theo cùng quy tắc LWT của cột thường.

Thay bằng bảng:

~~~sql
CREATE TABLE inventory_by_sku (
    sku_id text PRIMARY KEY,
    remaining bigint,
    version bigint
);
~~~

Writer đọc `remaining=10, version=5`, tính `remaining=3` rồi CAS:

~~~sql
UPDATE inventory_by_sku
SET remaining = 3,
    version = 6
WHERE sku_id = ?
IF version = 5;
~~~

Một writer khác cũng nhìn version 5 sẽ không thể tự thắng điều kiện nếu version đã thay đổi. Service phải xem `[applied]` và kiểm tra lượng tồn kho còn phù hợp trước khi retry.

### 11.1. Driver ví dụ

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement reserve = session.prepare(
    "UPDATE inventory_by_sku " +
    "SET remaining = ?, version = ? " +
    "WHERE sku_id = ? IF version = ?"
);

BoundStatement stmt = reserve.bind(3L, 6L, skuId, 5L)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .setIdempotent(false);

boolean applied = session.execute(stmt).wasApplied();

if (!applied) {
    // Đọc version và remaining hiện tại; xử lý 409/retry.
}
~~~

`LOCAL_SERIAL` phù hợp khi những writers cùng tranh một key được điều phối trong DC có thẩm quyền. Nếu có writers cạnh tranh từ nhiều DC và yêu cầu invariant toàn cầu, xem xét `SERIAL` hoặc home-DC routing với failover kiểm soát. LWT có chi phí Paxos, contention và timeout có outcome không rõ; nó không tự đảm bảo charge/email và database write cùng một giao dịch.

## 12. Spring Data Cassandra: mapping không đổi semantics counter

Spring Data Cassandra cung cấp `CassandraRepository`, `CassandraTemplate` và entity mapping. Nhưng `save(entity)` **không nên được xem là “increment counter”**: counter cần update có toán tử cộng/trừ và CQL có giới hạn đặc thù.

### 12.1. Entity mô tả bảng để đọc

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("page_views_by_day")
public class PageViewByDay {

    @PrimaryKeyColumn(name = "page_id",
                      type = PrimaryKeyType.PARTITIONED,
                      ordinal = 0)
    private UUID pageId;

    @PrimaryKeyColumn(name = "day_bucket",
                      type = PrimaryKeyType.PARTITIONED,
                      ordinal = 1)
    private LocalDate day;

    @Column("views")
    private Long views;

    public PageViewByDay() {}
    // Getters/setters...
}
~~~

Property Java `Long` không biến cột CQL `counter` thành kiểu `bigint` có thể gán. Đường ghi phải tuân CQL counter; không gọi `save(new PageViewByDay(...,100L))` với kỳ vọng reset counter về 100. Kiểm tra mapper/version Spring Data và chỉ dùng API mà CQL sinh ra là **counter increment/decrement**.

### 12.2. Tạo adapter dùng CqlSession của Spring

~~~java
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.stereotype.Repository;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

@Repository
public class CounterMutationRepository {

    private final CqlSession session;
    private final PreparedStatement increment;

    public CounterMutationRepository(CqlSession session) {
        this.session = session;
        this.increment = session.prepare(
            "UPDATE metrics.page_views_by_day " +
            "SET views = views + ? " +
            "WHERE page_id = ? AND day_bucket = ?"
        );
    }

    public void record(UUID pageId, LocalDate day, long delta) {
        if (delta <= 0) {
            throw new IllegalArgumentException("delta must be positive");
        }

        BoundStatement stmt = increment
            .bind(delta, pageId, day)
            .setIdempotent(false);

        session.execute(stmt);
    }
}
~~~

Trong triển khai thật, CL/timeout thường nằm ở execution profile hoặc statement, và lỗi phải được phân loại theo tính chính xác nghiệp vụ. Không tạo `CqlSession` cho từng HTTP request.

`CassandraTemplate` có API update/options khác nhau theo version, nhưng nguyên tắc giữ nguyên: phải xác minh CQL sinh ra dùng toán tử counter đúng ý, không vô tình gán giá trị tuyệt đối. Khi cần kiểm soát rõ `setIdempotent(false)` và xử lý timeout, adapter `CqlSession` trực tiếp thường dễ kiểm tra hơn.

### 12.3. @Version và @Transactional không làm counter thành CAS

Spring Data Cassandra hỗ trợ optimistic locking với `@Version` cho entity phù hợp bằng LWT/conditional statements. Nhưng **counter mutations không thể được biến thành LWT bằng cách thêm `@Version`**. Tương tự, `@Transactional` trong Spring không tự tạo cross-table atomic transaction cho “ghi event marker + tăng counter + commit broker offset”.

Nếu cần CAS/version, dùng bảng thường `bigint` hoặc mô hình nguồn sự kiện có khả năng đối soát, thay vì cố ép counter table mang semantics giao dịch quan hệ.

## 13. Spring Retry, HTTP retry và broker redelivery

### 13.1. Không bọc counter mutation bằng @Retryable vô điều kiện

Ví dụ phản mẫu:

~~~java
// Phản mẫu khi cần đếm chính xác.
@Retryable
public void recordView(UUID pageId, LocalDate day) {
    counterMutationRepository.record(pageId, day, 1);
}
~~~

Nếu Cassandra đã cộng nhưng response bị mất, `@Retryable` có thể chạy lại toàn bộ method và cộng thêm một lần. Annotation không biết outcome của mutation trước đó.

Trong một API, quyết định cần dựa trên hợp đồng:

- **Metric gần đúng:** có thể chấp nhận số liệu trễ hoặc sai lệch được đo và công bố.
- **Event chính xác:** tiếp nhận event ID ổn định, lưu nguồn idempotent, xây tổng từ nguồn.
- **Quota/inventory:** sử dụng CAS/writer coordination với kiểm tra điều kiện.
- **Request lỗi không rõ kết quả:** báo trạng thái phù hợp và có đường đối soát, không tự khẳng định chưa ghi.

### 13.2. Broker redelivery sau counter write

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant K as Cassandra Counter
    B->>C: Event E7
    C->>K: UPDATE views = views + 1
    K-->>C: Mutation acknowledged
    Note over C: Crash trước ack broker
    B->>C: Redeliver E7
    C->>K: UPDATE views = views + 1 lần hai
    Note over K: Một event có thể bị đếm hai lần
~~~

Commit offset hoặc ack **sau** khi gọi `session.execute` không biến Cassandra counter write và broker acknowledgment thành một transaction. Ngay cả nếu broker có tính năng xử lý giao dịch riêng, phải xem tính năng đó **có bao phủ sink Cassandra hay không**; không mặc định.

Các hướng phòng lỗi:

1. Lưu immutable events có ID nguồn tin cậy.
2. Bảo vệ uniqueness tại nguồn khi cần; kiểm tra cùng ID/different payload.
3. Tổng hợp có checkpoint, khả năng rebuild và version để tránh snapshot cũ ghi đè.
4. Định nghĩa cách xử lý event muộn, correction/retraction và replay.
5. Giới hạn retry và tránh speculative attempts trên counter.
6. Có hệ thống đối soát thay vì dùng giá trị counter làm bằng chứng cuối cùng.

### 13.3. Quy tắc HTTP response

| Kết quả bên trong | Gợi ý về API contract |
| --- | --- |
| Đã xác nhận CQL counter write | Success theo CL đã chọn, nhưng không hứa event uniqueness |
| Event ID trùng, nguồn đã lưu cùng payload | Trả kết quả idempotent của ingest, không tạo event row mới |
| Event ID trùng nhưng payload khác | Trả conflict rõ ràng |
| Driver timeout sau mutation | Unknown outcome, có request ID để kiểm tra/đối soát |
| Không đủ replica / unavailable | Phản hồi lỗi hạ tầng phù hợp, không giả định mọi loại retry an toàn |

Không gửi raw Cassandra exception hoặc dữ liệu nhạy cảm không cần thiết ra client. Không thiết kế client kiểu nhận 500 là tự động gửi lại `+1` vô hạn.

## 14. Sharded counters, bucket và hot partition

Một trang cực phổ biến có thể khiến mọi request cùng tranh một key:

~~~text
page_id = popular-page
day_bucket = today
5.000 requests/second -> cùng một counter partition
~~~

Nếu throughput/p99 không đạt, có thể thử phân tán bằng sharded counters:

~~~sql
CREATE TABLE metrics.page_view_shard_by_day (
    page_id uuid,
    day_bucket date,
    shard_id int,
    views counter,
    PRIMARY KEY ((page_id, day_bucket, shard_id))
);
~~~

Mỗi event được đưa vào một shard theo quy tắc được định nghĩa. Tổng là tổng của các shard, có thể cần nhiều đọc ở các partition khác nhau.

### 14.1. Sharding không khử trùng event

Giả sử cùng event E42 bị retry:

- Cả hai attempt vào shard 3: shard 3 tăng hai.
- Attempt đầu vào shard 3, attempt sau vào shard 7: hai shard tăng một, tổng vẫn tăng hai.
- Chọn shard ngẫu nhiên mỗi lần: càng khó tìm nguyên nhân drift.

Sharding giải quyết **phân phối tải**, không giải quyết **idempotency**. Muốn bảo vệ theo event ID phải có nguồn sự kiện hoặc cơ chế dedup riêng được thiết kế đúng.

### 14.2. Tổng nhiều shard không có snapshot mặc định

Nếu ứng dụng đọc shard 0 ở thời điểm T0 rồi shard 1 ở T1, trong lúc có writer tiếp tục tăng, kết quả là tổng từ **những thời điểm khác nhau**. Với UI gần đúng có thể chấp nhận. Với báo cáo chính thức, dùng một nguồn dữ liệu và mốc snapshot/checkpoint rõ.

### 14.3. Bucket đúng thời gian và retention

`day_bucket date` giúp truy vấn và quản lý theo ngày, nhưng phải quy định ngày là UTC hay timezone nghiệp vụ. Một timestamp bị hiểu sai milliseconds/microseconds có thể làm event vào sai bucket. Counter không có TTL như regular cells; retention cần quy trình quản trị/xóa bucket có kiểm soát. Nếu cần truy vấn lịch sử chi tiết và paging, dùng bảng event riêng thay vì chỉ lưu một số tổng.

## 15. Theo dõi drift, error budget và tài nguyên

**Counter drift** là độ chênh giữa counter và một số chuẩn từ nguồn dữ liệu độc lập/đã đối soát, nếu nguồn đó tồn tại.

| Nhóm | Chỉ số hữu ích | Câu hỏi |
| --- | --- | --- |
| Ingest | Incoming events, unique IDs, duplicate IDs | Một event được nhận bao nhiêu lần? |
| HTTP/service | Retry attempts, unknown outcomes, timeouts | Có bao nhiêu lần có thể cộng trùng? |
| Driver | Statement idempotence, retries, speculation, in-flight | Có nhiều CQL attempts hơn expected? |
| Cassandra | Write latency, unavailable, timeout, dropped messages | Node/replica nào không khỏe? |
| Topology | RF, DC, cross-DC lag, node health | Reader đang thấy dữ liệu trễ? |
| Data | Native count vs unique event count | Drift xuất hiện ở partition/bucket nào? |
| Projection | Snapshot generation, checkpoint age, rebuild failures | Tổng reconciled mới tới mốc nào? |
| Capacity | CPU, disk I/O, compaction, hot partition QPS | Bị nghẽn bởi tải hay contention? |

Không bịa ngưỡng “drift 1% luôn an toàn” cho mọi sản phẩm; SLA phụ thuộc việc dùng số đó vào dashboard, tính phí hay enforce quota. Nếu số dư tài chính được tính từ counter, vấn đề là **mô hình dữ liệu không phù hợp**, không phải chỉ cần giám sát tốt hơn.

### 15.1. Đừng chỉ nhìn giá trị tổng

Giá trị `views=101` sau timeout không chứng minh event đang xử lý đã được cộng: một event khác có thể vừa tăng; cũng có thể một phép cộng trùng bị một lỗi khác che khuất. Đối soát cần source event IDs, request trace, hoặc một dữ liệu độc lập đáng tin cậy.

### 15.2. Phân biệt nguyên nhân tăng/thiếu

- **Thừa do retry:** cùng event được thực thi nhiều mutation.
- **Thiếu do crash:** marker được lưu nhưng increment chưa chạy.
- **Lag của read:** một replica/DC chưa trả trạng thái mong đợi ở thời điểm đọc.
- **Upstream loss:** sự kiện không được gửi hoặc bị bỏ.
- **Projection lag:** nguồn event đã có nhưng tổng dẫn xuất chưa theo kịp.
- **Bucket mismatch:** event được ghi vào ngày/shard khác do timestamp hoặc hàm hash sai.

Mỗi nguyên nhân có cách xử lý khác. Nâng CL không sửa event loss; retry counter không sửa thiếu projection; đổi shard không tự khử trùng.

## 16. Kiểm thử tính không lũy đẳng và fault injection

### 16.1. Ma trận kiểm thử

| Ca kiểm thử | Điều cần chứng minh |
| --- | --- |
| Gửi một lệnh `+1` thành công | Đọc theo CL đã chọn thấy giá trị kỳ vọng |
| Gửi hai lệnh `+1` liên tiếp | Có thể tăng hai, thể hiện non-idempotency |
| Gửi lại lệnh `-1` | Có thể giảm thêm lần nữa |
| Timeout **trước** khi server nhận mutation | Retry có thể tạo một hiệu ứng |
| Timeout **sau** khi server áp dụng mutation | Retry có thể tạo hai hiệu ứng |
| Statement có `setIdempotent(false)` | Driver policy không được mặc định coi mutation an toàn |
| Spring `@Retryable` bọc increment | Có nguy cơ đếm đôi sau unknown outcome |
| Broker redelivery E123 | Thiếu source dedup thì có nguy cơ cộng lại |
| Marker rồi crash trước counter | Có thể thiếu count |
| Counter rồi crash trước marker | Có thể thừa count |
| Retry COUNTER BATCH | Mutation trong batch có thể bị lặp |
| Event E123 `IF NOT EXISTS`, gửi lại | Nguồn event row không bị nhân đôi khi khóa/protocol đúng |
| Projector replay cùng source snapshot | Total tính lại không tự tăng thêm |
| Job generation 10 ghi muộn hơn generation 11 | CAS/writer ordering ngăn tổng bị lùi |
| RF3, một replica down | Availability/latency theo CL thực tế |
| Reader ở DC khác | Phân biệt lag với double increment |
| Trang nổi tiếng với sharded counters | Đo throughput, tail latency và drift |

### 16.2. JUnit integration test minh họa

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class CounterIntegrationTest {

    private PageViewCounterDao dao;

    @Test
    void twoUpdatesHaveTwoEffects() {
        UUID pageId = UUID.randomUUID();
        LocalDate day = LocalDate.of(2026, 11, 25);

        dao.addViews(pageId, day, 1L);
        dao.addViews(pageId, day, 1L);

        long views = readViews(pageId, day);
        assertEquals(2L, views);
    }

    private long readViews(UUID pageId, LocalDate day) {
        // Cần implement query SELECT và kết nối keyspace test.
        throw new UnsupportedOperationException("test fixture");
    }
}
~~~

Đây là **skeleton integration test**: cần inject DAO, tạo fixture Cassandra test và triển khai `readViews` trước khi chạy. Không gọi vào production hoặc coi `UnsupportedOperationException` là kiểm thử thành công.

### 16.3. Mock ném lỗi trước khi gửi là chưa đủ

Một mock chỉ ném exception **trước** khi CQL được phát đi sẽ bỏ qua chính lỗi khó nhất: server đã cộng nhưng response mất. Bộ kiểm thử cần kiểm soát cả hai tình huống:

1. **Before-apply:** mutation chưa tới server; retry có thể là lần thực thi duy nhất.
2. **After-apply/response-loss:** mutation đã được áp dụng, nhưng client thấy timeout rồi gửi lại.

Có thể test logic API bằng adapter giả lập outcome và bổ sung fault injection lên cụm test. Một unit test thuần không chứng minh đầy đủ consistency, network failure hay hành vi coordinator/replicas.

### 16.4. Kiểm thử độ chính xác của nguồn event

Nếu dùng event log:

- Hai requests cùng `event_id` phải đến cùng shard/primary key.
- Cùng ID + cùng payload được xem là duplicate hợp lệ.
- Cùng ID + payload khác được xem là lỗi/xung đột.
- Projector có thể chạy lại sau crash mà không nhân đôi total.
- Hai generation ghi theo thứ tự ngược không làm lùi tổng.
- Event muộn hoặc retraction có quy tắc đối soát.
- Không dùng `ALLOW FILTERING` để quét toàn bộ bảng trong một HTTP request.

## 17. Runbook khi phát hiện bộ đếm bị lệch

### 17.1. Khoanh vùng trước khi sửa

1. Xác định table, `page_id`, bucket, shard (nếu có) và mốc thời gian.
2. Kiểm tra có thay đổi gần đây ở gateway/Spring Retry/driver/broker không.
3. Đối chiếu số request IDs và event IDs với số mutation quan sát được.
4. Kiểm tra timeout sau khi CQL được gửi và sự cố coordinator/network.
5. Kiểm tra RF, local DC, read CL để loại trừ lag.
6. Tìm hot partitions và số attempt tăng bất thường.
7. Nếu có event log, tính tổng event unique theo đúng phạm vi.
8. Tắt nguồn phát retry không an toàn trước khi sửa dữ liệu.

### 17.2. Không trừ ngược một cách mù quáng

Giả sử counter là 1.002 nhưng tổng đối soát là 1.000:

~~~sql
UPDATE metrics.page_views_by_day
SET views = views - 2
WHERE page_id = ? AND day_bucket = ?;
~~~

Phép trừ này **cũng không idempotent**. Nếu response mất rồi operator thực thi lại, counter có thể xuống 998, thậm chí nguồn vẫn có writer tiếp tục tăng. Không đặt một script “sửa drift” tự retry như thể `views - 2` là gán lại giá trị.

Hướng phục hồi đáng tin cậy khi yêu cầu exact: xây lại **projection tuyệt đối `bigint`** từ nguồn event theo generation và công bố thời điểm snapshot. Nếu buộc phải điều chỉnh counter native, cần runbook với kiểm soát writer, theo dõi outcome, thử trên staging và kế hoạch rollback/đối soát.

### 17.3. Retention/reset cần hiểu hệ phân tán

Xóa row counter không xóa lịch sử event, cũng không làm broker ngừng redeliver. Việc reset hoặc xóa counter có thể có hệ quả tombstone/replication/repair và cạnh tranh với writer đang chạy. Không dùng reset thủ công trên production để “đưa counter về 0” nếu chưa hiểu lifecycle của counter trong phiên bản Cassandra đang dùng.

## 18. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Gửi lại `views + 1` không đổi dữ liệu vì câu CQL giống nhau.” | Mỗi lần thực thi có thể cộng thêm một. |
| “Prepared statement chống duplicate.” | Prepare chỉ chuẩn bị query/bind types. |
| “LOCAL_QUORUM bảo đảm exactly-once.” | CL không lưu ID của event. |
| “Timeout nghĩa là chưa tăng.” | Kết quả có thể đã áp dụng. |
| “Đọc lại giá trị tổng biết được event đã tính chưa.” | Tổng không chỉ ra nguồn của mỗi delta. |
| “`setIdempotent(true)` làm phép cộng an toàn.” | Flag chỉ mô tả semantics, không sửa chúng. |
| “Tắt retry driver là hết nguy cơ.” | HTTP, Spring, broker và người vận hành có thể phát lại. |
| “COUNTER BATCH là transaction chống lặp.” | Retry batch vẫn có thể gây thêm hiệu ứng. |
| “Marker IF NOT EXISTS rồi counter += 1 là atomic.” | Crash giữa hai mutation gây thiếu count. |
| “Counter rồi marker cũng đủ.” | Crash giữa hai mutation gây thừa count. |
| “`@Version` biến counter thành conditional update.” | Counter không có LWT trực tiếp như bigint thường. |
| “`save(entity)` reset counter được.” | Counter dùng toán tử cộng/trừ, không gán tùy ý. |
| “Sharding giải quyết duplicate.” | Chỉ giúp phân phối tải, vẫn có thể double count. |
| “Total gán tuyệt đối không cần version.” | Job cũ có thể ghi đè snapshot mới. |
| “Counter phù hợp enforce tồn kho không âm.” | Cần CAS/coordination có điều kiện phù hợp. |
| “Sửa lệch bằng `views - 2` rồi retry an toàn.” | Phép trừ cũng không lũy đẳng. |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `views = views + 1` không lũy đẳng?

*Đáp án:* Gửi hai lần có thể tăng hai, còn một lần tăng một.

**Câu 2.** Sau timeout, service có thể chắc chắn counter chưa tăng không?

*Đáp án:* Không; request có thể đã áp dụng nhưng response mất.

**Câu 3.** `setIdempotent(false)` bảo vệ được điều gì?

*Gợi ý:* Không để policy driver coi phép cộng là an toàn cho attempt bổ sung, nhưng không chặn retry tầng khác.

**Câu 4.** Vì sao `LOCAL_QUORUM` không khử trùng?

*Gợi ý:* Không có event ID hoặc deduplication logic.

**Câu 5.** Ghi marker trước rồi cộng có rủi ro gì?

*Gợi ý:* Crash giữa hai bước gây thiếu count.

**Câu 6.** Cộng trước rồi lưu marker gây rủi ro gì?

*Gợi ý:* Crash giữa hai bước gây double count khi retry.

**Câu 7.** `COUNTER BATCH` có exactly-once khi gửi lại không?

*Đáp án:* Không.

**Câu 8.** Vì sao cần immutable events nếu muốn báo cáo theo event chính xác?

*Gợi ý:* Có thể dedup theo ID và dựng lại total.

**Câu 9.** Sharding counter có chống event trùng không?

*Đáp án:* Không; chỉ phân phối tải.

**Câu 10.** Vì sao total bigint có thể bị ghi lùi?

*Gợi ý:* Projector snapshot cũ ghi sau snapshot mới nếu thiếu CAS/generation.

**Câu 11.** Muốn bảo vệ tồn kho không âm nên chọn gì?

*Gợi ý:* Bigint + LWT/CAS hoặc công cụ transactional phù hợp.

**Câu 12.** Vì sao broker commit offset sau counter update chưa đủ?

*Gợi ý:* Consumer crash trước ack làm broker phát lại.

**Câu 13.** Thử nghiệm nào phát hiện unknown outcome?

*Gợi ý:* Server áp dụng mutation rồi cố tình làm mất response.

**Câu 14.** `views = views - 2` có an toàn để retry không?

*Đáp án:* Không, phép trừ không lũy đẳng.

## 20. Checklist production

- **Mô hình:** Chọn native counter chỉ khi business chấp nhận semantic của counter.
- **Schema:** Chỉ counter columns ngoài primary key; partition/bucket theo access pattern.
- **CQL:** Dùng increment/decrement, không giả định reset bằng gán, TTL hay LWT trực tiếp.
- **Driver:** Prepare/bind đúng type; `setIdempotent(false)` cho counter mutation.
- **Retries:** Rà soát client, gateway, Spring, Java Driver, broker, scheduler và manual replay.
- **Unknown outcome:** Timeout không chứng minh chưa ghi; có hợp đồng lỗi/đối soát.
- **CL/RF:** Chọn consistency cho SLA/visibility, không xem nó là event dedup.
- **Nguồn sự thật:** Nếu cần exact, có event ID, primary key ổn định, lưu nguồn bất biến.
- **Atomicity:** Không coi marker + counter là transaction đơn.
- **Derived total:** Dùng absolute total và generation/CAS hoặc writer ordering.
- **Invariant:** Đối với quota/inventory, dùng bảng thường và conditional protocol thích hợp.
- **Hot key:** Giám sát per-partition QPS, p95/p99; sharding giúp tải, không giúp dedup.
- **Retention:** Bucket theo timezone nhất quán, có chính sách xóa/đối soát.
- **Observability:** Log request ID theo chính sách, metrics timeout/retry/drift/checkpoint.
- **Testing:** Before-apply, after-apply response loss, broker redelivery, duplicate IDs, crash giữa hai writes.
- **Vận hành:** Dừng nguồn duplicate trước, không trừ ngược mù khi counter lệch.
- **QA:** Đây là STEP_4 tạo knowledge; chưa chạy vòng Content QA chuyên môn STEP_6.

## Tài liệu tham khảo

- [Apache Cassandra — CQL Types](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html): kiểu `counter` và ràng buộc bảng.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): `UPDATE`, phép cộng/trừ counter, batch và conditional CQL.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/latest/cassandra/architecture/): replication, ghi phân tán và consistency.
- [Apache Cassandra Java Driver](https://apache.github.io/cassandra-java-driver/): `BoundStatement`, idempotency, retries và execution profiles.
- [Spring Data Cassandra Reference](https://docs.spring.io/spring-data/cassandra/reference/): `CqlSession`, repository, `CassandraTemplate`, LWT và entity mapping.
- [Spring Retry Reference](https://docs.spring.io/spring-retry/docs/current/apidocs/): đánh giá semantic của thao tác trước khi áp tự động retry.

## Kết luận

**Cassandra counter increment/decrement không lũy đẳng.** Nếu `views = views + 1` được áp dụng hai lần, số đếm có thể tăng hai lần; nếu response của lần đầu mất, client thường không biết kết quả cuối và một retry mù có thể đếm đôi. `PreparedStatement`, `LOCAL_QUORUM`, `setTimeout` và `setIdempotent(false)` có vai trò riêng nhưng không thể tạo bảo đảm exactly-once cho một event nghiệp vụ.

Trong **SPRING_DATA_CASSANDRA**, hãy sử dụng counter native cho số liệu chấp nhận sai lệch và kiểm soát retry ở mọi tầng. Khi cần tổng chính xác và truy vết được, lưu nguồn event bất biến có ID ổn định, xử lý trùng tại nguồn, tổng hợp thành giá trị tuyệt đối có version và khả năng replay/reconcile. Nếu cần invariant như tồn kho không âm, chọn bảng `bigint` với CAS/LWT hoặc cơ chế giao dịch phù hợp. Chỉ kết hợp đúng access pattern, partition key, consistency, paging, quan sát tải và thử nghiệm sự cố thực tế mới giúp hệ thống Cassandra phân tán đếm một cách đáng tin cậy.





