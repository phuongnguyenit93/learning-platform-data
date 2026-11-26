# Backfill theo token range hoặc partition với giới hạn tải trong Spring Data Cassandra

Khi ứng dụng dùng **Spring Data Cassandra** cần đổi mô hình dữ liệu theo truy vấn mới, tạo thêm bảng phi chuẩn hóa hoặc chia lại partition để giảm điểm nóng, chỉ tạo schema mới chưa đủ: dữ liệu lịch sử vẫn nằm ở bảng cũ. **Backfill** là tiến trình đọc dữ liệu nguồn và ghi vào bảng đích, có thể tạm dừng, tiếp tục sau lỗi, đối soát dữ liệu và bảo vệ hiệu năng Cassandra.

Vì Apache Cassandra phân phối dữ liệu theo **partition key** trên một vòng token (*token ring*), có hai cách chia công việc thường gặp:

- **Theo partition:** biết trước toàn bộ partition key cần di trú và đọc từng partition bằng truy vấn đúng khóa.
- **Theo token range:** chia miền token thành các khoảng, quét các partition thuộc từng khoảng. Phù hợp khi không có danh mục partition key đầy đủ.

Bài học phân tích lựa chọn giữa hai cách, tổ chức paging/checkpoint, triển khai worker bằng Java Driver 4.x và Reactor bên cạnh Spring Data Cassandra, giới hạn concurrency và QPS, xử lý dữ liệu thay đổi trong khi quét, retry idempotent và xác minh trước khi cutover.

## 1. Bài toán di trú bảng theo truy vấn

Giả sử dữ liệu gốc lưu sự kiện bất biến theo ID:

~~~sql
CREATE TABLE events_by_id (
    event_id uuid PRIMARY KEY,
    account_id uuid,
    occurred_at timestamp,
    event_type text
);
~~~

Ứng dụng hiện cần đọc sự kiện theo tài khoản và tháng. Truy vấn tương lai nên có bảng đích với partition key phù hợp:

~~~sql
CREATE TABLE events_by_account_month (
    account_id uuid,
    month_bucket int,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((account_id, month_bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Đích dùng partition key tổng hợp `(account_id, month_bucket)` và clustering key `(occurred_at, event_id)`. Bucket tháng được tính theo UTC, ví dụ sự kiện ngày 2026-11-25 có `month_bucket=202611`. Cách này giới hạn phạm vi mỗi partition, tránh lịch sử một tài khoản lớn thành một partition không giới hạn.

~~~sql
SELECT event_id, occurred_at, event_type
FROM events_by_account_month
WHERE account_id = ? AND month_bucket = ?
LIMIT 100;
~~~

`LIMIT 100` chỉ giới hạn kết quả truy vấn; không thay thế paging hoặc giới hạn tải. Thứ tự clustering được bảo đảm **trong partition** chứ không tạo thứ tự toàn cục cho mọi tài khoản.

Trong phần mã chính, giả định sự kiện **bất biến**: một `event_id` luôn có cùng `account_id`, `occurred_at` và `event_type`; không UPDATE, DELETE hay TTL trên sự kiện. Nhờ vậy, ghi cùng một bản sao vào cùng primary key đích nhiều lần có kết quả nghiệp vụ như một lần. Mục 7 giải thích các rủi ro khi giả định này không đúng.

~~~mermaid
flowchart LR
    A["events_by_id<br/>PK: event_id"] --> B["Backfill theo partition / token"]
    B --> C["events_by_account_month<br/>PK: account_id, month_bucket"]
    D["Ghi mới hoặc CDC"] --> C
    E["Checkpoint / Manifest"] -. "Đã xử lý đến đâu" .-> B
    F["Giới hạn tải"] -. "Concurrency và RPS" .-> B
~~~

## 2. Chọn quét theo partition hay token range

| Tiêu chí | Quét theo partition | Quét theo token range |
| --- | --- | --- |
| Điều kiện | Có **danh mục partition key đầy đủ**. | Không cần danh mục key; biết cấu trúc key và partitioner. |
| Truy vấn | `WHERE partition_key = ?`. | `WHERE token(partition_key) >= ? AND token(partition_key) < ?`. |
| Khả năng giới hạn công việc | Theo số partition, số row hoặc clustering range. | Theo các subrange token và số page/row. |
| Hiệu quả đọc | Thường tốt hơn nếu có key; Cassandra định tuyến tới replica của partition. | Có thể tốn nhiều I/O khi quét hàng loạt partition trên cluster. |
| Tính đầy đủ | Phụ thuộc độ đầy đủ và cập nhật của danh mục key. | Phụ thuộc độ bao phủ các khoảng token và sự thay đổi dữ liệu trong lúc quét. |
| Checkpoint | Từng key hoặc nhóm key; partition lớn cần paging. | Từng range; nên chia đủ nhỏ để có thể chạy lại. |
| Rủi ro | Thiếu key, hot/large partition, danh mục không nhất quán. | Lỗi ranh giới, tải cao, các range có lượng dữ liệu không đều. |

**Ưu tiên partition** nếu một hệ thống upstream sở hữu danh mục key đáng tin cậy. Ví dụ bảng nguồn có partition key `account_id` và đã có manifest đầy đủ mọi tài khoản cần xử lý: worker có thể đọc `WHERE account_id = ?` và paging theo clustering key.

Trong ví dụ `events_by_id`, partition key nguồn là `event_id`. Danh sách `account_id` **không giúp đọc trực tiếp** nguồn theo tài khoản; nếu có danh sách toàn bộ `event_id`, mới có thể quét theo partition bằng `WHERE event_id = ?`. Khi không có danh mục đầy đủ, quét theo token là một lựa chọn thực tế.

Với partition key tổng hợp như `PRIMARY KEY ((tenant_id, bucket_id), occurred_at)`, phải dùng **đủ cả `tenant_id` và `bucket_id`** cho truy vấn partition; token scan phải dùng `token(tenant_id, bucket_id)` với đúng thứ tự thành phần.

Không coi một câu `SELECT * FROM events_by_id` chạy đến hết là kiến trúc backfill an toàn: thiếu cơ chế chia việc, giới hạn tải, resume và kiểm soát độ nhất quán khi nguồn có thay đổi.

## 3. Chia token range đúng ranh giới

Partitioner chuyển partition key thành token để phân phối dữ liệu. Với **`Murmur3Partitioner`**, token thuộc miền số nguyên có dấu 64-bit:

\[
\text{min}=-2^{63}, \qquad \text{max}=2^{63}-1.
\]

Có thể tạo manifest của các khoảng rời nhau theo quy ước:

- Mọi range trung gian là **`[lowerInclusive, upperExclusive)`**.
- Range đầu bắt đầu ở `Long.MIN_VALUE`, **bao gồm** token nhỏ nhất.
- Range cuối dùng **`[lowerInclusive, Long.MAX_VALUE]`** để bao gồm token lớn nhất.
- Range tiếp theo bắt đầu đúng tại cận trên của range trước; không có lỗ hoặc chồng lấn.

~~~text
Long.MIN_VALUE                                   Long.MAX_VALUE
     |-------------------|--------------------|-----------------|
       [min, boundary1)    [boundary1, b2)       [b2, max]
          range A              range B             range C
~~~

Quét một khoảng trung gian trên nguồn có partition key đơn `event_id`:

~~~sql
SELECT event_id, account_id, occurred_at, event_type
FROM events_by_id
WHERE token(event_id) >= ? AND token(event_id) < ?;
~~~

Range cuối thay dấu so sánh bên phải thành `<= ?`. Khi binding token dạng `long`, **chỉ áp dụng trực tiếp ví dụ này với `Murmur3Partitioner`**. Kiểm tra partitioner thực tế của cluster trước khi lập manifest; một số partitioner khác không dùng token kiểu `bigint` giống ví dụ.

**Không tính `Long.MAX_VALUE + 1` bằng `long`** vì sẽ overflow. Nếu sinh N range trải đều miền token, dùng `BigInteger` để tính các boundary trung gian và xác minh giá trị trước khi đổi về `long`. Các khoảng token dài bằng nhau không có nghĩa chứa số row hoặc kích thước dữ liệu bằng nhau: cần đo và có thể chia nhỏ work unit quá nặng.

### Vì sao checkpoint mỗi `lastToken` không đủ?

Giả sử một page chứa nhiều row cùng partition, worker ghi được một nửa rồi crash. Nếu chỉ nhớ token của row cuối và lần sau đọc `token(pk) > lastToken`, những row chưa ghi thuộc cùng partition/token sẽ **bị bỏ sót**. Hash collision giữa các partition khác nhau cũng có thể xảy ra.

Giải pháp đơn giản, tin cậy: đánh dấu **toàn range `DONE`** chỉ sau khi tất cả page và write của range đã được xác nhận. Nếu crash giữa range, replay **toàn range** bằng các phép ghi idempotent. Chia range nhỏ giúp việc replay rẻ hơn.

Nếu muốn lưu paging state để resume giữa range, phải tính đến CQL statement cố định, phiên bản driver/protocol, paging state dạng opaque và sự biến động nguồn; **paging state không phải ảnh chụp nhất quán của dữ liệu**. Không tự coi nó là một cursor có thể tiếp tục mãi sau khi schema hoặc truy vấn thay đổi.

## 4. Thiết kế worker với checkpoint bền vững

Một job lớn nên có **manifest các work unit** và nhiều worker có lease:

~~~mermaid
flowchart TD
    P["Sinh manifest"] --> Q["PENDING"]
    Q --> W["Worker claim lease"]
    W --> S["Đọc partition/range + paging"]
    S --> T["Điều tiết read/write"]
    T --> I["UPSERT bảng đích"]
    I --> A{"Mọi page/write đã ack?"}
    A -- "Không" --> F["FAILED / retry với backoff"]
    F --> Q
    A -- "Có" --> D["Checkpoint DONE"]
    D --> V["Đối soát và đồng bộ thay đổi"]
~~~

Một work unit nên lưu:

| Thuộc tính | Công dụng |
| --- | --- |
| `job_id`, `work_id` | Định danh đợt di trú và unit. |
| `lower_token`, `upper_token`, `upper_inclusive` | Ranh giới quét token; hoặc `partition_key` đầy đủ nếu chia theo partition. |
| `state` | `PENDING`, `LEASED`, `DONE`, `FAILED`. |
| `lease_owner`, `lease_until`, `fencing_version` | Chặn worker cũ ghi checkpoint của lease mới. |
| `attempts`, `rows_read`, `write_acks`, `error_class` | Thống kê/retry và điều tra. |
| `migration_version`, `started_at`, `finished_at` | Phát hiện job chạy mã chuyển đổi khác phiên bản. |

Quy trình:

1. Claim một unit và lấy lease bền vững; chỉ một worker được quyền **đánh dấu kết quả** theo phiên bản lease hiện hành.
2. Đọc từng page, ghi các row vào bảng đích trong giới hạn tải, chờ tất cả write được xác nhận.
3. Nếu bất kỳ page hoặc write gặp lỗi chưa xử lý được, **không đánh dấu `DONE`**; đưa unit trở lại hàng retry có kiểm soát.
4. Khi toàn bộ range hoàn tất, đánh dấu `DONE` bằng thao tác bền vững, có xác nhận và kiểm tra fencing.
5. Sau restart, chỉ lấy unit còn công việc. Chấp nhận thực tế hai worker có thể từng chạy trùng khi lease hết hạn; nội dung ghi phải hỗ trợ **at-least-once**.

Conditional update/LWT có thể phù hợp để điều phối **một số ít record trạng thái** nếu cần, nhưng không nên dùng LWT cho từng row dữ liệu chỉ để ghi dấu backfill. Ghi trạng thái `DONE` xác nhận tiến trình worker, **chưa tự chứng minh dữ liệu đích đã đồng bộ với mọi thay đổi mới nhất**.

## 5. Worker đọc theo token và ghi bất đồng bộ bằng Java Driver + Reactor

Spring Data Cassandra hỗ trợ entity mapping, repository và `CassandraTemplate`; còn một backfill scan token theo paging có thể dùng **`CqlSession` của Java Driver 4.x** để điều khiển statement rõ ràng. Worker không thay thế toàn bộ đường truy cập repository của ứng dụng.

Ví dụ dưới đây thực hiện **một token range**, đọc tuần tự từng page nguồn và cho phép tối đa tám lệnh ghi target chạy đồng thời **trong một page**.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Instant;
import java.time.ZoneOffset;

final class EventRangeBackfill {
    private static final int READ_PAGE_SIZE = 200;
    private static final int WRITES_PER_RANGE = 8;
    private final CqlSession session;

    EventRangeBackfill(CqlSession session) {
        this.session = session;
    }

    // Boundaries phải được sinh cho Murmur3Partitioner.
    Mono<Void> range(long lowerInclusive, long upper,
                     boolean includeUpper) {
        String upperPredicate = includeUpper ? "<= ?" : "< ?";
        String cql =
            "SELECT event_id, account_id, occurred_at, event_type " +
            "FROM events_by_id " +
            "WHERE token(event_id) >= ? AND token(event_id) "
            + upperPredicate;

        SimpleStatement scan = SimpleStatement.builder(cql)
            .addPositionalValue(lowerInclusive)
            .addPositionalValue(upper)
            .setPageSize(READ_PAGE_SIZE)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .build();

        return Mono.fromCompletionStage(() -> session.executeAsync(scan))
            .flatMap(this::copyPage);
    }

    private Mono<Void> copyPage(AsyncResultSet page) {
        return Flux.fromIterable(page.currentPage())
            .flatMap(this::writeEvent, WRITES_PER_RANGE)
            .then(Mono.defer(() -> {
                if (!page.hasMorePages()) {
                    return Mono.empty();
                }
                return Mono.fromCompletionStage(
                        () -> page.fetchNextPage())
                    .flatMap(this::copyPage);
            }));
    }

    private Mono<Void> writeEvent(Row row) {
        Instant occurredAt = row.getInstant("occurred_at");
        var utc = occurredAt.atZone(ZoneOffset.UTC);
        int monthBucket = utc.getYear() * 100 + utc.getMonthValue();

        SimpleStatement upsert = SimpleStatement.builder(
                "INSERT INTO events_by_account_month " +
                "(account_id, month_bucket, occurred_at, " +
                "event_id, event_type) VALUES (?, ?, ?, ?, ?)")
            .addPositionalValue(row.getUuid("account_id"))
            .addPositionalValue(monthBucket)
            .addPositionalValue(occurredAt)
            .addPositionalValue(row.getUuid("event_id"))
            .addPositionalValue(row.getString("event_type"))
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true) // Chỉ an toàn vì event bất biến.
            .build();

        return Mono.fromCompletionStage(() -> session.executeAsync(upsert))
            .then();
    }
}
~~~

Các giả định: source/target đã có schema, trường bắt buộc không `null`, keyspace/cluster hỗ trợ consistency level `LOCAL_QUORUM`. Đoạn mã chỉ xử lý **một range**, chưa bao gồm manifest, checkpoint, rate limiter tổng thể hoặc retry. Caller phải bắt `onError` và không đánh dấu `DONE` khi pipeline lỗi.

Nếu một ghi gặp lỗi, `flatMap` có thể hủy subscription của các ghi khác, nhưng việc hủy ở phía client **không bảo đảm** Cassandra đã dừng/rollback các mutation đang chạy. Vì vậy một lần replay có thể viết lại những row đã ghi thành công từ lần trước; đây là lý do dữ liệu đích phải idempotent.

### Giới hạn số range chạy cùng lúc

Một coordinator có thể xử lý manifest bằng `Flux` với giới hạn số inner subscriptions:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record TokenUnit(long fromInclusive, long to, boolean includeUpper) {}

interface CheckpointStore {
    // Lưu trạng thái bền vững và kiểm tra quyền lease/fencing.
    Mono<Void> markDone(TokenUnit unit);
}

final class BackfillCoordinator {
    Mono<Void> migrate(Flux<TokenUnit> claimedUnits,
                       EventRangeBackfill worker,
                       CheckpointStore checkpointStore) {
        return claimedUnits
            .flatMap(unit ->
                worker.range(unit.fromInclusive(),
                             unit.to(),
                             unit.includeUpper())
                    .then(Mono.defer(
                        () -> checkpointStore.markDone(unit))),
                4)
            .then();
    }
}
~~~

Đây là **đoạn mã minh họa phần điều phối**: `claimedUnits` và `CheckpointStore` phải được cung cấp bởi hệ thống manifest/lease; `markDone` trả về `Mono<Void>` đại diện cho **thao tác checkpoint bền vững có kiểm tra lease/fencing**. Nhờ `then(Mono.defer(...))`, thao tác đánh dấu `DONE` chỉ bắt đầu sau khi scan và mọi ghi của unit hoàn tất thành công. Bản thân ví dụ chưa hiện thực checkpoint store hoặc cơ chế claim lease.

Với 4 range và 8 ghi/range, pipeline có tối đa khoảng **32 write target in-flight** nếu không có nguồn request khác; số này không bao gồm retries/speculative execution nội bộ driver và những pod khác. `flatMap(..., 4)` giới hạn **một subscription**, không giới hạn toàn cluster.

### Quét theo partition với key đầy đủ

Nếu nguồn được thiết kế theo `account_id` (một mô hình **khác** với `events_by_id`), và có manifest đầy đủ các account, worker nên đọc trực tiếp partition:

~~~java
SimpleStatement byPartition = SimpleStatement.builder(
        "SELECT occurred_at, event_id, event_type " +
        "FROM events_by_account WHERE account_id = ?")
    .addPositionalValue(accountId)
    .setPageSize(200)
    .setIdempotent(true)
    .build();
~~~

Đoạn code chỉ hợp lệ khi bảng `events_by_account` có partition key `account_id`; không thể dùng query này trên bảng nguồn chỉ được khóa bởi `event_id`. Một partition lớn vẫn cần paging và giới hạn tải. Nếu manifest chỉ chứa `tenant_id` mà partition key thật là `(tenant_id, bucket_id)`, manifest chưa đủ để khẳng định đã xử lý hết dữ liệu.

## 6. Giới hạn tải: concurrency, RPS, queue và deadline

Backfill là workload nền, nên ưu tiên SLA/SLO của request người dùng. **Concurrency limit** kiểm soát bao nhiêu request đang chạy, còn **rate limit** kiểm soát bao nhiêu request mới có thể gửi theo giây. Cần dùng cả hai: khi Cassandra trả lời rất nhanh, giới hạn 32 request đồng thời vẫn có thể tạo hàng nghìn request/giây.

| Thông số minh họa | Mức dùng trong thử nghiệm | Ý nghĩa |
| --- | ---: | --- |
| Số range đang chạy | 4 | Tránh mở quá nhiều scan cùng lúc. |
| Ghi đồng thời/range | 8 | Giới hạn số target writes từ một page. |
| `pageSize` | 200 row | Giới hạn bộ nhớ và kích thước page. |
| Tổng write attempts/s | 300 | Giới hạn QPS kể cả retry. |
| Queue chờ permit | 64 | Không dồn vô hạn công việc khi cluster chậm. |
| Retry sau lỗi tạm thời | Tối đa 2 lần thêm nếu còn deadline | Tránh khuếch đại sự cố. |

**Các số liệu là ví dụ để tuning, không phải cấu hình khuyến nghị**. Giá trị thực phụ thuộc replication factor, consistency level, kích thước row, tổng node, network, compaction, partition distribution và traffic ứng dụng.

### Gate trước mỗi request

Đặt **rate gate dùng chung** trước lệnh gọi `CqlSession.executeAsync(...)`, tính cả các attempt retry và page fetch. Một giao diện giả lập bằng Reactor:

~~~java
// Pseudocode: rateGate là thành phần được dùng chung,
// có queue hữu hạn và deadline rõ ràng.
Mono<Void> writeWithRateLimit(Row row) {
    return rateGate.acquireWritePermit()
        .then(Mono.defer(() -> writeEvent(row)));
}
~~~

Thay `this::writeEvent` trong `copyPage` bằng `this::writeWithRateLimit`. Đây là pseudocode vì `rateGate` cần hiện thực bằng token bucket hoặc thư viện rate limiter phù hợp với hệ thống. Nếu một job có nhiều pod, cần **quota toàn job** hoặc phân bổ quota cố định theo pod; giới hạn 300 RPS **mỗi pod** với 10 pod có thể tạo 3.000 RPS tổng cộng.

Hạn mức cần tính **attempt**, không chỉ số hàng nghiệp vụ; mỗi retry là một request thật. Đừng để queue chờ kéo dài vượt deadline; một request đã mất phần lớn thời gian ở queue thường sẽ timeout dù chưa chạy CQL.

### Hạn mức của Java Driver

Java Driver 4.x có `ConcurrencyLimitingRequestThrottler` để giới hạn số request in-flight và queue ở cấp `CqlSession`:

~~~hocon
datastax-java-driver {
  advanced.throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 64
    max-queue-size = 128
  }
  basic.request.timeout = 5 seconds
}
~~~

Các giá trị chỉ minh họa; cần kiểm tra cấu hình theo bản driver/ứng dụng đang sử dụng. Driver throttler không tự giới hạn RPS **toàn job** và không thay thế rate gate. Đừng đặt queue lớn ở cả ứng dụng lẫn driver khiến request chờ hai tầng rồi tăng timeout để che nguyên nhân.

### Giảm tải thích nghi

Worker cần có khả năng **pause** khi traffic production bị ảnh hưởng. Theo dõi latency p95/p99, `ReadTimeout`, `WriteTimeout`, `Overloaded`, queue, CPU/I/O, GC, compaction, dropped messages và retry rate. Khi những chỉ số vượt ngưỡng đã xác định, giảm concurrency/RPS hoặc ngừng nhận range mới; khi ổn định mới tăng chậm trở lại.

Không nhìn duy nhất CPU trung bình toàn cluster. Một hot partition hoặc một token range chứa nhiều row/tombstone có thể làm nhóm replica chịu tải cao dù nhiều node khác vẫn còn tài nguyên.

## 7. Đồng bộ thay đổi mới trong lúc backfill

**Quét token ring không tạo snapshot giao dịch nhất quán toàn cluster.** Khi worker quét xong một range, ứng dụng vẫn có thể thêm, sửa hoặc xóa dữ liệu trong chính range đó. Nếu chỉ chạy backfill một lần rồi chuyển truy vấn, có thể bỏ sót thay đổi phát sinh trong lúc quét.

Lộ trình migration an toàn hơn:

~~~mermaid
flowchart LR
    A["Tạo bảng đích"] --> B["Dual-write hoặc CDC"]
    B --> C["Backfill lịch sử"]
    C --> D["Đuổi kịp change stream"]
    D --> E["Reconciliation + shadow read"]
    E --> F["Chuyển read traffic dần"]
    F --> G["Giữ rollback window"]
~~~

**Dual-write:** ứng dụng ghi cả nguồn và đích. Không mặc định hai thao tác ở các partition khác nhau là một transaction ACID; một phía có thể thành công và phía kia thất bại. Phải có operation ID, retry/đối soát và xử lý trạng thái ghi chưa xác định.

**CDC/change stream:** dữ liệu được ghi nguồn rồi phát sự kiện thay đổi sang đích. Job cần theo dõi offset/watermark, lag, replay và khả năng xử lý sai thứ tự. Không giả định thứ tự toàn cục giữa mọi partition nếu hệ thống CDC không bảo đảm.

**Tạm dừng ghi:** đôi khi hợp lý cho tập dữ liệu nhỏ với cửa sổ downtime được phép; phải xác nhận không còn writer khác hoặc message consumer tiếp tục tạo dữ liệu.

### Ghi lại dữ liệu cũ có thể đè dữ liệu mới

Giả sử backfill đọc bản ghi có `state=NEW` tại T1; ứng dụng cập nhật `state=PAID` vào đích tại T2; sau đó backfill ghi lại dữ liệu cũ ở T3. Cassandra áp dụng **last-write-wins theo timestamp của cell**. Nếu lệnh backfill mang timestamp mới hơn, dữ liệu cũ có thể **đè** dữ liệu mới.

Đối với row mutable cần một chiến lược cụ thể:

1. Có **version hoặc timestamp logic** với quy tắc đơn điệu, nhất quán giữa nguồn/đích/change events.
2. Nếu copy write timestamp từ nguồn, phải hiểu `writetime(column)` là **theo cell**, không mặc nhiên biểu diễn một snapshot hợp lệ của cả row.
3. Replay change stream từ watermark đúng và đối soát sau backfill, không cho backfill cũ thắng bản cập nhật mới.
4. Truyền cả **DELETE/tombstone** theo thứ tự phù hợp; không được hồi sinh bản ghi đã xóa.
5. Thiết kế riêng cho **TTL, counter, collection, LWT**. Copy một row đang có TTL bằng insert mới không TTL có thể làm dữ liệu tồn tại quá lâu; retry counter increment có thể tăng nhiều lần.

Với sự kiện **bất biến** ở ví dụ, cùng một `event_id` ánh xạ đến đúng một khóa đích và các giá trị cố định. Replay cùng UPSERT thường có kết quả cuối như một lần ghi, miễn không có TTL hoặc tác dụng phụ bên ngoài thay đổi qua mỗi lần thử.

Không dùng `BATCH` lớn trên nhiều partition như cách tăng throughput. Batch Cassandra có các mục đích và bảo đảm riêng, không thay thế giới hạn request hoặc tạo giao dịch ACID tổng quát cho di trú nhiều bảng.

## 8. Retry và xử lý lỗi khi backfill

Backfill dài hạn phải coi lỗi node, timeout và restart là điều dự kiến. Nhưng retry chỉ hợp lý khi phép ghi có thể lặp lại an toàn.

| Lỗi | Ý nghĩa | Xử lý |
| --- | --- | --- |
| `UnavailableException` | CL không đủ replica đang khả dụng. | Giảm/pause job, kiểm tra RF/CL và node; retry có giới hạn khi có cơ sở. |
| `ReadTimeoutException` | Page đọc chưa nhận đủ phản hồi đúng hạn. | Retry page/range chưa checkpoint; **không coi như hết dữ liệu**. |
| `WriteTimeoutException` | Có thể một số replica đã áp dụng mutation. | Không kết luận ghi chưa xảy ra; replay chỉ khi idempotent/đã có đối soát. |
| `OverloadedException` | Coordinator quá tải. | Giảm concurrency/RPS, backoff có jitter; không retry tức thì hàng loạt. |
| `RequestThrottlingException` | Driver chạm giới hạn in-flight/queue. | Giảm admission, theo dõi queue và deadline. |
| `DriverTimeoutException` | Hết thời gian chờ phía driver. | Đánh giá trạng thái chưa xác định, deadline và khả năng replay. |
| CQL/schema/serialization sai | Lỗi logic cố định. | Đưa unit `FAILED`, sửa migration; không retry vô hạn. |

Ví dụ worker ghi 199/200 hàng của page trước khi gặp `WriteTimeout`. Nếu replay cả page/range, 199 hàng đã ghi sẽ bị UPSERT lần nữa. Đây là **at-least-once processing**. Với dữ liệu bất biến và khóa đích xác định, replay có thể chấp nhận; với counter hoặc thao tác gửi email/thanh toán bên ngoài, replay có thể tạo tác dụng phụ trùng lặp.

Đặt `setIdempotent(true)` ở statement **chỉ sau khi kiểm chứng idempotency thật**. Tránh nhiều tầng retry chồng nhau (driver, service, HTTP) tạo hàng chục attempt cho một bản ghi. Mọi retry phải bị tính vào rate budget và deadline tổng. Nếu unit lỗi liên tục, chuyển sang `FAILED` và tiếp tục các unit độc lập, không để một range lỗi giữ hết workers.

Consistency level phải phù hợp với nghiệp vụ: `LOCAL_ONE` có thể có latency thấp hơn nhưng cũng có thể đọc bản sao chưa cập nhật; `LOCAL_QUORUM` đòi hỏi đủ replica trong datacenter cục bộ. Không giảm CL chỉ để backfill chạy nhanh mà chưa đánh giá hậu quả dữ liệu và reconciliation.

## 9. Xác minh dữ liệu trước khi cutover

Tất cả work unit có trạng thái `DONE` chỉ có nghĩa là worker đã hoàn tất quy trình đã định. Để chuyển truy vấn sang bảng đích cần đối soát:

1. **Độ bao phủ:** manifest có bao hết token ring hoặc tất cả partition key không? Range đầu/cuối, ranh giới inclusive/exclusive có đúng?
2. **Số key:** tập `event_id` ở đích có tương ứng tập nguồn tại watermark xác định không? Có thiếu/dư do biến động nguồn, retry hay TTL không?
3. **Nội dung:** `account_id`, `occurred_at`, `event_type` và `month_bucket` UTC có đúng không? Clustering query có cho kết quả hợp lệ không?
4. **Tính mới:** dual-write hoặc CDC đã đuổi kịp, không còn event thất lạc hoặc write thất bại một phía?
5. **Khả năng khôi phục:** crash/restart và lease expiry có tạo thiếu dữ liệu hoặc lỗi trùng lặp không?
6. **Hiệu năng:** partition size, p95/p99, page count, tombstone và mức tải của truy vấn mới có đáp ứng SLO?

### Không chỉ dùng `COUNT(*)`

`COUNT(*)` trên bảng Cassandra lớn có thể rất tốn kém và hai bảng có cùng số row vẫn có thể khác key/value. Dùng đối chiếu **theo key hoặc partition** và canonical hash trên dữ liệu chuẩn hóa, có watermark để giải thích những thay đổi đang được xử lý:

| Chỉ số | Điều xác minh | Giới hạn |
| --- | --- | --- |
| `rows_read` | Số row nguồn đã quan sát. | Có thể lặp khi retry; nguồn có thể đổi. |
| `write_ack` | Số write đã được driver xác nhận. | Không tự chứng minh toàn bộ dữ liệu đích đúng. |
| Missing target keys | Các event cần replay/khắc phục. | Phải xét CDC lag và thời điểm đối soát. |
| Mismatched values | Lỗi mapping, phiên bản hoặc copy. | Cần chuẩn hóa format và so dữ liệu đúng watermark. |
| CDC high watermark/lag | Các thay đổi đến đâu. | Không thay thế kiểm tra lỗi xử lý event. |
| P99 ở bảng đích | Hiệu năng theo access pattern mới. | Cần test với nhiều account và partition thực tế. |

**Shadow read** có thể đọc bảng mới ở một tỉ lệ nhỏ trong khi API vẫn dùng nguồn làm kết quả chính, sau đó so sánh theo ngữ nghĩa nghiệp vụ. Quá trình so sánh cũng cần **giới hạn tải**, bảo vệ dữ liệu nhạy cảm trong log và phân loại sai khác do lag hợp lệ hoặc lỗi di trú thực sự. Chỉ chuyển traffic khi ngưỡng sai khác và SLO đạt yêu cầu.

## 10. Quan sát tiến độ và điều hành backfill

Nên phát metrics theo job, operation và loại lỗi, không thêm `event_id`, `account_id` hoặc token riêng lẻ làm metric label vì cardinality cao và có thể chứa dữ liệu nhạy cảm.

| Metric minh họa | Công dụng |
| --- | --- |
| `backfill_units_total{state}` | Unit `PENDING`, `LEASED`, `DONE`, `FAILED`. |
| `backfill_rows_read_total` | Số row đọc và số row bị replay nếu đo riêng. |
| `backfill_write_attempts_total{result}` | Tổng write attempts, bao gồm retry. |
| `backfill_inflight` | Số read/write request đang chạy. |
| `backfill_page_fetch_duration_seconds` | Độ trễ đọc từng trang. |
| `backfill_throttle_wait_seconds` | Thời gian chờ quota. |
| `backfill_retries_total{error_class}` | Tỷ lệ lỗi và nguyên nhân retry. |
| `backfill_cdc_lag_seconds` | Độ trễ đồng bộ thay đổi. |
| `backfill_reconciliation_mismatches_total{type}` | Sai khác khóa/giá trị/version/TTL. |

Các tên trên là **metric ứng dụng tự định nghĩa**, không phải metric Java Driver mặc định. Kết hợp với driver/Cassandra metrics về pending tasks, request latency, connection pool, dropped messages, compaction, CPU, disk I/O và GC.

### Runbook từng giai đoạn

1. **Chuẩn bị:** tạo schema đích, kiểm tra RF/CL, partitioner, danh mục key hoặc token manifest, checkpoint store, dashboard và cách pause.
2. **Canary:** chạy vài range/partition đại diện, bao gồm nhóm lớn/hot; đo correct mapping và tác động lên production traffic.
3. **Tăng dần:** mở rộng concurrency/RPS theo SLO, không nhắm mục tiêu throughput tối đa bằng mọi giá.
4. **Sự cố:** ngừng claim unit mới, giảm quota, giữ checkpoint an toàn, phân loại lỗi và resume sau khi cluster ổn định.
5. **Đối soát:** hoàn tất lịch sử, theo dõi CDC lag, so key/value và shadow read.
6. **Cutover:** chuyển dần read traffic sang bảng mới, giữ rollback window và observability.
7. **Dọn dẹp:** chỉ bỏ đường đọc/ghi cũ hoặc xóa bảng nguồn khi đã xác minh không còn phụ thuộc, sau các yêu cầu retention/khôi phục.

## 11. Tình huống thực hành

**Bối cảnh:** `events_by_id` có 80 triệu sự kiện bất biến; API mới cần truy vấn `events_by_account_month`. Traffic mới vẫn liên tục phát sinh và cluster có nhiều ứng dụng cùng truy cập.

Một kế hoạch hợp lý:

1. Chuẩn bị schema đích và đường dual-write/CDC có cơ chế phục hồi.
2. Sinh token manifest phủ miền Murmur3 hoặc danh mục `event_id` đầy đủ; chia unit nhỏ, có lease/checkpoint.
3. Chạy canary ở các range nhỏ. Thử `pageSize=200`, 4 ranges và 8 writes/range như ví dụ, sau đó chỉnh bằng số đo thực.
4. Dùng rate gate toàn job, giới hạn queue và deadline. Khi production p99 tăng hay Cassandra báo `Overloaded`, giảm tải.
5. Chỉ checkpoint `DONE` sau khi toàn bộ page và write được xác nhận. Crash giữa unit thì replay idempotent.
6. Đuổi kịp thay đổi mới, đối chiếu key/value và đo query đích với workload thực tế.
7. Chuyển read traffic dần, quan sát sai khác và hiệu năng rồi mới quyết định ngừng dùng bảng cũ.

**Câu hỏi tự kiểm tra:** Vì sao checkpoint theo `token(pk) > lastToken` có thể bỏ sót dữ liệu? Vì sao `flatMap(..., 8)` không giới hạn toàn cluster? `WriteTimeout` có nghĩa row chắc chắn chưa được ghi không? Tại sao backfill cũ có thể đè UPDATE mới? Và tại sao mọi range `DONE` vẫn chưa đủ để cutover?

## 12. Tổng kết

Backfill trong Spring Data Cassandra là bài toán **điều phối dữ liệu phân tán có giới hạn tài nguyên**. Nếu có manifest partition key đầy đủ, nên đọc trực tiếp theo partition. Nếu không, chia token ring thành các range bao phủ không gian token, paging có kiểm soát và checkpoint theo unit đã ghi thành công. Cả hai cách đều cần giới hạn **concurrency, RPS, queue và deadline** cũng như retry idempotent.

Với dữ liệu đang thay đổi, backfill chỉ di trú phần lịch sử; dual-write/CDC, version/tombstone/TTL, reconciliation và shadow read mới tạo cơ sở an toàn để cutover. Thiết kế bảng đích theo partition key của truy vấn mới và đo hiệu năng thực tế trước khi chuyển lưu lượng.

### Tài liệu tham khảo

- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/).
- [Apache Cassandra — Architecture and partitioners](https://cassandra.apache.org/doc/latest/cassandra/architecture/).
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/).
- [Java Driver 4.x — Asynchronous API](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/async/).
- [Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/).
- [Java Driver 4.x — Request throttling](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/throttling/).
- [Spring Data Cassandra — Reference Documentation](https://docs.spring.io/spring-data/cassandra/reference/).
