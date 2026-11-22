# Subscription, nhu cầu nhận dữ liệu và vòng đời kết quả

> **Chương:** Bất đồng bộ và reactive  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra với kiến trúc phân tán, mô hình wide-column, partition key, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý sự cố và kết nối từ ứng dụng Java.

Một ứng dụng Java truy vấn bảng sự kiện có hàng triệu bản ghi. Với cách viết đồng bộ, vòng lặp `ResultSet` có thể đọc đến đâu lấy trang tiếp đến đó. Với cách bất đồng bộ, `executeAsync()` trả một `CompletionStage<AsyncResultSet>` và ứng dụng chủ động điều khiển các trang. Còn với cách **reactive**, ứng dụng nhận một **`Publisher<ReactiveRow>`**, biểu đạt bằng Reactive Streams: subscriber đăng ký, yêu cầu số lượng phần tử qua `Subscription.request(n)`, nhận lần lượt `onNext` và kết thúc bằng `onComplete` hoặc `onError`.

Không phải có `Flux` là Cassandra trở thành dòng dữ liệu thời gian thực vô hạn. Một truy vấn CQL `SELECT` thông thường vẫn là **truy vấn hữu hạn**, có paging, chịu giới hạn consistency, timeout và năng lực replica. Reactive Streams chủ yếu giúp **truyền nhu cầu tiêu thụ (demand) và quản lý vòng đời kết quả trong ứng dụng**, để không đẩy dữ liệu xuống subscriber nhanh hơn khả năng xử lý của nó.

Bài này trả lời bốn câu hỏi thực tế:

1. **Khi nào truy vấn bắt đầu chạy?** Lúc gọi `executeReactive`, lúc `subscribe`, hay lúc `request(n)`?
2. **Subscriber chỉ xin hai hàng thì sao?** Driver lấy dữ liệu theo trang hay hai lần đọc độc lập?
3. **Nếu subscriber dừng giữa chừng?** Những kết quả chưa nhận, request đang bay, kết nối pool và kết quả đã ghi sẽ thế nào?
4. **Một `ReactiveResultSet` có thể dùng lại không?** Điều gì xảy ra với `cache()`, `retry()` hoặc hai subscribers?

> **Phạm vi phiên bản:** ví dụ dựa trên **Apache Cassandra Java Driver 4.x** và tài liệu chính thức của **4.19**, kết hợp **Reactive Streams 1.0.x** và **Project Reactor 3.x**. Tên package reactive trong driver là `com.datastax.dse.driver.api.core.cql.reactive` vì lý do lịch sử; các API này **vẫn hoạt động với Apache Cassandra OSS**, không bắt buộc DataStax Enterprise. Khi dùng Spring Data Cassandra Reactive, phải đối chiếu release train/BOM và hành vi của tầng Spring riêng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `Publisher`, `Subscriber`, `Subscription` và các tín hiệu `onSubscribe/onNext/onComplete/onError`.
2. Giải thích `request(n)` là **nhu cầu cộng dồn** ở phía consumer; `request(0)`/âm không hợp lệ và `Long.MAX_VALUE` có thể coi là nhu cầu không giới hạn.
3. Hiểu `ReactiveResultSet` của Java Driver 4.x mặc định **cold, unicast, chỉ một subscriber**, và vì sao subscription thứ hai thất bại.
4. Dùng `Flux.from(session.executeReactive(statement))`, phân biệt một query result với việc tạo luồng queries, xử lý write result **không phát ra hàng**.
5. Mô tả cách demand tác động đến **fetch page** trong Cassandra và giới hạn backpressure khi ghi.
6. Quản lý `cancel`, complete/error, timeout, session lifecycle và tài nguyên liên quan mà không tự cho rằng đã rollback mutation.
7. Viết subscriber điều khiển demand từng đợt, Reactor pipeline cho SELECT, giới hạn concurrency cho ghi và test bằng `StepVerifier`.
8. Phân biệt giới hạn trên phía subscriber (`take`, `limitRate`) với giới hạn CQL ở server (`LIMIT`, partition key, page size).

## 2. Bốn thành phần Reactive Streams

### 2.1. Ai sản xuất, ai tiêu thụ?

| Thành phần | API tiêu biểu | Vai trò trong Cassandra Java Driver |
|---|---|---|
| **Publisher<T>** | `subscribe(Subscriber<? super T>)` | `ReactiveResultSet` phát `ReactiveRow` của một query |
| **Subscriber<T>** | `onSubscribe`, `onNext`, `onError`, `onComplete` | Code/Framework nhận dữ liệu và quyết định cần bao nhiêu |
| **Subscription** | `request(long n)`, `cancel()` | Quan hệ riêng giữa một subscriber và publisher, chịu trách nhiệm demand và hủy |
| **Processor** | Vừa subscriber vừa publisher | Operator/adapter như `map`, `filter`, `publishOn` hoặc pipeline phức tạp |

**`Publisher` không tự chứa một `List<Row>` đã tải sẵn**. Nó mô tả nguồn có thể phát phần tử khi được tiêu thụ. Khi tạo một `ReactiveResultSet`, driver chưa thực hiện CQL; tài liệu driver xác định truy vấn thực sự **được kích hoạt khi có subscription**.

### 2.2. Trình tự tín hiệu hợp lệ

~~~mermaid
sequenceDiagram
    participant S as Subscriber / Reactor
    participant P as ReactiveResultSet
    participant D as Cassandra Driver
    participant C as Coordinator / Replicas
    S->>P: subscribe(subscriber)
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P->>D: Thực hiện / tiếp tục phân phối kết quả
    D->>C: Native protocol SELECT, fetch pages khi cần
    C-->>D: Các row theo trang
    D-->>P: ReactiveRow, ReactiveRow
    P-->>S: onNext(row 1)
    P-->>S: onNext(row 2)
    Note over S,P: Không phát vượt demand còn lại
    S->>P: request(3)
    P-->>S: onNext(row 3...5) nếu còn dữ liệu
    P-->>S: onComplete() khi hết kết quả
~~~

Sơ đồ là **mô hình hành vi**, không khẳng định driver luôn gửi network request đúng lúc `request(2)`, hay mỗi lần `request(2)` tương ứng một CQL page. Việc kích hoạt truy vấn có thể bắt đầu ngay sau subscription; số row được fetch/buffer theo page size, prefetch và đường vận hành.

### 2.3. Vòng đời quan sát được của một subscription

~~~text
NEW publisher (chưa subscribe)
   |
   v
onSubscribe(subscription)   -- subscriber giữ Subscription
   |
   v
ACTIVE (có thể chờ demand, nhận onNext, chờ page/connection)
   |\
   | \----> cancel() ----> CANCELLED (không còn mong nhận dữ liệu)
   |
   +------> onComplete() -> COMPLETED (terminal)
   |
   +------> onError(e) --> FAILED (terminal)
~~~

Theo Reactive Streams, **sau terminal `onComplete` hoặc `onError` không còn `onNext` mới**. `cancel` là yêu cầu hủy subscription, **không phải một terminal signal gửi bắt buộc đến subscriber**. Có thể vẫn có tín hiệu đang trên đường tới khi cancellation được quan sát; subscriber phải xử lý các trạng thái cạnh tranh an toàn.

### 2.4. Những quy tắc demand phải thuộc

| Lời gọi | Ngữ nghĩa | Điều cần nhớ |
|---|---|---|
| `request(1)` | Xin tối đa một phần tử mới | Có thể `request(1)` nhiều lần để xử lý từng row |
| `request(5)`, sau đó `request(3)` | Demand cộng dồn, tối đa 8 row còn được phép phát | Không phải “thay demand 5 bằng 3” |
| `request(Long.MAX_VALUE)` | Có thể coi là không giới hạn | Không đồng nghĩa toàn bộ bảng vừa được tải vào RAM ngay |
| `request(0)` hoặc `request(-1)` | **Không hợp lệ** | Theo spec 3.9 phải báo `onError(IllegalArgumentException)` khi subscription chưa bị hủy |
| `cancel()` | Không muốn nhận thêm | Có thể trễ khi có onNext đã phát/đang xử lý; không rollback server |
| Không gọi `request(n)` | Subscriber chưa yêu cầu row | Có thể không có `onNext`; timeout/terminal error vẫn có thể xảy ra |

Theo đặc tả Reactive Streams, `Publisher` **không được phát nhiều `onNext` hơn demand**. Nhưng việc subscriber xin 2 rows **không phải chỉ thị native protocol yêu cầu Cassandra đọc đúng 2 rows từ disk**: Cassandra native protocol dùng giao thức paging khác, và driver có thể đã fetch/buffer nhiều rows trong một page.

## 3. Java Driver 4.x: CqlSession.executeReactive là Publisher lạnh

### 3.1. API và package thật

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveResultSet;
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;
import org.reactivestreams.Publisher;

// session được tạo trước, đã có local DC, TLS/auth nếu cần.
ReactiveResultSet rs = session.executeReactive("SELECT ...");
Publisher<ReactiveRow> rows = rs; // ReactiveResultSet là Publisher<ReactiveRow>.
~~~

**Đừng thay `com.datastax.dse...ReactiveRow` bằng một class `com.datastax.oss...ReactiveRow` tự đoán.** Package được giữ vì lịch sử dù driver Apache OSS hỗ trợ. Thư viện `org.reactivestreams:reactive-streams` phải có trong classpath để gọi reactive methods; Project Reactor là một thư viện **bổ sung**, không bắt buộc nếu bạn dùng Subscriber/Publisher thuần.

### 3.2. Lazy: tạo publisher chưa gửi truy vấn

~~~java
ReactiveResultSet rs = session.executeReactive(
    "SELECT event_time, event_id, payload FROM stream_lab.events_by_device " +
    "WHERE device_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = '2026-11-21'");

// Đến đây rs chưa được subscribe => chưa thực hiện query này.
// Nói chung không giữ rs vô thời hạn rồi để CqlSession đóng trước khi subscribe.
~~~

Khi dùng Reactor:

~~~java
import reactor.core.publisher.Flux;

Flux<ReactiveRow> stream = Flux.from(rs);
// Đây cũng chỉ là mô tả pipeline, chưa có subscriber.

// Trong chương trình CLI/lab, blockLast() tự subscribe rồi chờ completion.
stream.doOnNext(row -> System.out.println(row.getUuid("event_id")))
      .blockLast();
~~~

**Chỉ dùng `blockLast()` ở CLI/test nơi được phép chặn.** Trong WebFlux/reactive handler, trả `Flux` cho framework để nó subscribe theo vòng đời HTTP, không gọi `block()`/`subscribe()` thủ công rồi trả một publisher khác.

### 3.3. Unicast, single-subscription: không phải publisher có thể subscribe tùy ý

Theo Java Driver 4.19, `ReactiveResultSet` mặc định:

- **cold:** truy vấn không chạy trước subscription.
- **unicast:** một subscriber nhận một luồng kết quả.
- **single-subscription-only:** **một lần subscribe** cho mỗi `ReactiveResultSet`; gọi subscribe lần hai vào đúng đối tượng có thể kết thúc bằng lỗi `IllegalStateException`.

~~~java
ReactiveResultSet once = session.executeReactive(
    "SELECT event_time FROM stream_lab.events_by_device " +
    "WHERE device_id = 11111111-1111-4111-8111-111111111111 " +
    "AND event_day = '2026-11-21'");

Flux<ReactiveRow> flux = Flux.from(once);
// Demo khái niệm: subscribe đầu dùng nguồn, subscribe thứ hai lỗi.
// flux.count().block();
// flux.count().block();  // Không được dựa vào lần thứ hai hoạt động.
~~~

Đây là đặc tính của **result set cụ thể**, không có nghĩa mỗi session chỉ chạy được một query. Một `CqlSession` quản lý nhiều queries đồng thời. Nếu muốn **thực thi query mới ở mỗi subscriber**, tạo **ReactiveResultSet mới cho mỗi subscription**:

~~~java
import reactor.core.publisher.Flux;

Flux<ReactiveRow> rerunnable = Flux.defer(() ->
    Flux.from(session.executeReactive(
        "SELECT event_time, event_id, payload " +
        "FROM stream_lab.events_by_device " +
        "WHERE device_id = 11111111-1111-4111-8111-111111111111 " +
        "AND event_day = '2026-11-21'")));

// Mỗi lần subscribe -> một ReactiveResultSet mới -> một query mới.
// Đây là hành vi chủ động; không dùng lại cho mutation nếu không an toàn.
~~~

**Cảnh báo:** `Flux.defer` không “cho phép subscribe lại đối tượng cũ”; nó **tạo một query mới**. Hai subscribers có thể nhận dữ liệu khác nhau nếu Cassandra đang có ghi mới, consistency thấp hoặc TTL hết hạn giữa hai lần đọc. Với INSERT/UPDATE, subscribe lần hai có thể gây side effect lặp.

## 4. Nhu cầu nhận dữ liệu đi từ Subscriber tới Cassandra như thế nào?

### 4.1. Demand có giới hạn là backpressure

Một subscriber đọc từng đợt có thể:

1. `request(2)` từ `onSubscribe`.
2. Xử lý hai `onNext`.
3. Sau khi xử lý xong đợt, `request(2)` tiếp.
4. Khi đủ dữ liệu hoặc người dùng hủy HTTP request, `cancel()`.

Điều này ngăn publisher phát rows vượt số yêu cầu chưa được đáp ứng. Nhưng **không tự giới hạn thời gian xử lý hoặc lượng buffering** của operator phía sau; nếu dùng `publishOn`, `flatMap`, `buffer`, `onBackpressureBuffer`, cần hiểu prefetch và bộ nhớ riêng.

### 4.2. Paging mới là cơ chế điều tiết giữa driver và Cassandra

Cassandra native protocol **không có một message chuẩn “subscriber đã request thêm 2 rows”**. Driver quản lý việc fetch các trang tiếp theo dựa trên nhu cầu và trạng thái stream. Vì vậy:

- `request(2)` bảo vệ **số onNext**, không khẳng định server chỉ scan đúng hai hàng.
- Truy vấn vẫn có `page size`; một trang chứa nhiều row, yêu cầu paging tiếp theo có thể phát sinh khi driver cần dữ liệu.
- Khi downstream chậm, driver có thể **giảm nhịp lấy page tiếp**; Cassandra vẫn đã tiêu thụ CPU/IO để tạo những trang đã gửi.
- Subscriber cực chậm, node chậm hoặc request bị nghẽn vẫn có thể gặp `DriverTimeoutException`/`ReadTimeoutException`.
- Nếu truy vấn quét partition lớn/tombstones hoặc cần `ALLOW FILTERING`, reactive backpressure **không biến query đó thành rẻ**.

**Sơ đồ tác động:**

~~~mermaid
flowchart LR
    A["Subscriber demand<br/>request(n)"] --> B["Driver reactive publisher"]
    B --> C["Phân phối rows đã có<br/>không vượt demand"]
    B --> D["Tăng/giảm fetch page tiếp<br/>theo demand và buffer"]
    D --> E["Native protocol paging"]
    E --> F["Cassandra coordinator"]
    F --> G["Replicas / SSTables"]
    H["CQL LIMIT, PK, CL, page size"] -. "Quyết định workload" .-> E
~~~

### 4.3. Ba loại giới hạn không được nhầm

| Giới hạn | Nằm ở đâu? | Điều nó **không** bảo đảm |
|---|---|---|
| `Subscription.request(n)` | Reactive Streams giữa subscriber và publisher | Không bắt Cassandra scan đúng `n` rows/disk reads |
| `Flux.take(n)` | Operator phía subscriber; sau n phần tử thường cancel upstream | Không có nghĩa CQL chỉ đọc n rows trên server; pages có thể đã fetch |
| CQL `LIMIT n` | Query semantics tại server, cùng partition/filter/clustering | Không là hard cap về số byte SSTable scanned nếu có tombstone/filter |
| `Statement.setPageSize(n)` | Mong muốn kích thước mỗi page native protocol | Không giới hạn tổng result hoặc buộc đúng n rows/page |
| `Flux.limitRate(n)` | Điều chỉnh demand upstream trong Reactor | Không thay `LIMIT` hay page-size của CQL |

Nếu nghiệp vụ chỉ cần 10 event gần nhất, hãy **thiết kế bảng có clustering phù hợp + CQL LIMIT 10** rồi áp Reactor operator để điều tiết consumption nếu cần. Không viết `SELECT *` trên một partition khổng lồ rồi mong `take(10)` luôn tiết kiệm server work.

## 5. Viết Subscriber thuần để thấy request(n) và cancel()

### 5.1. Subscriber đọc theo đợt hai hàng

Ví dụ thuần `org.reactivestreams`, không bắt buộc dùng Reactor:

~~~java
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveRow;
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;
import java.util.concurrent.atomic.AtomicInteger;

final class TwoAtATimeSubscriber implements Subscriber<ReactiveRow> {
    private Subscription subscription;
    private final AtomicInteger received = new AtomicInteger();

    @Override
    public void onSubscribe(Subscription s) {
        this.subscription = s;
        s.request(2); // Nhận tối đa 2 phần tử trước khi xin tiếp.
    }

    @Override
    public void onNext(ReactiveRow row) {
        // Chỉ làm xử lý NGẮN, KHÔNG block IO/đợi HTTP ở đây.
        System.out.println("event_id=" + row.getUuid("event_id"));
        int total = received.incrementAndGet();

        if (total >= 6) {
            subscription.cancel(); // Dừng sau 6 row; không xóa row trong DB.
        } else if (total % 2 == 0) {
            subscription.request(2); // Demand cộng dồn cho đợt tiếp.
        }
    }

    @Override
    public void onError(Throwable cause) {
        System.err.println("Query error type: "
                + cause.getClass().getSimpleName());
    }

    @Override
    public void onComplete() {
        System.out.println("Query fully consumed");
    }
}
~~~

Gắn subscriber vào kết quả:

~~~java
// rs được tạo từ session.executeReactive(preparedBoundStatement).
rs.subscribe(new TwoAtATimeSubscriber());
~~~

**Kỳ vọng:** Nếu kết quả có ít hơn 6 rows, nhận `onComplete`. Nếu đủ 6 rows, subscriber gọi `cancel()` và **không được chờ onComplete như dấu hiệu bắt buộc**. Nếu đang có tín hiệu đã phát trước khi cancel, có thể cần xử lý cạnh tranh trạng thái; đừng xem ví dụ là bộ đếm phân tán chính xác.

**Mục tiêu demo:** nhìn rõ `Subscription`, demand và cancellation. Trong production, tránh `System.out.println` theo từng row trên thread driver, tránh lộ dữ liệu khách hàng, và dùng Reactor/operator hoặc hàng đợi bounded để tách việc xử lý nặng.

### 5.2. Vì sao request(0) không phải “tạm dừng”?

~~~java
// SAI: request(0) là vi phạm Reactive Streams Specification 3.9.
// subscription.request(0);
~~~

Muốn tạm chưa nhận thêm row, **đơn giản không gọi request mới** sau khi hết demand cũ. Khi sẵn sàng xử lý, gọi `request(k)` với `k > 0`. Đối với async processing, cần điều phối sự kiện hoàn thành xử lý với việc cấp demand mới; không tự block `onNext` chờ future.

### 5.3. Không gọi request(Long.MAX_VALUE) khi không có capacity

Khi subscriber gọi `request(Long.MAX_VALUE)`, nó nói rằng có thể nhận không giới hạn row theo flow control. Nếu downstream lại đưa mỗi row vào một queue vô hạn hoặc gọi một tác vụ chậm, OOM có thể xuất hiện tại **operator/application**, dù driver làm đúng Reactive Streams contract.

Ưu tiên kiểm soát demand qua Reactor operators, bounded queue hoặc batch xử lý có giới hạn; **không tạo unbounded buffering** chỉ vì “reactive là non-blocking”.

## 6. Reactor pipeline cho SELECT và WebFlux

### 6.1. Prepared statement và mapping theo partition

Giả sử dữ liệu được thiết kế theo truy vấn “các event mới nhất của một thiết bị trong một ngày”:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
~~~

Ứng dụng có thể prepare một lần lúc startup và trả `Flux` mỗi khi có yêu cầu:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import reactor.core.publisher.Flux;

// Ví dụ JDK 17+: record là DTO bất biến.
record EventView(Instant eventTime, UUID eventId, String payload) {}

static Flux<EventView> findEvents(
        CqlSession session, PreparedStatement select,
        UUID deviceId, LocalDate day) {

    BoundStatement statement = select.bind(deviceId, day)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(2)     // Lab: mong muốn trang nhỏ để quan sát paging.
        .setIdempotent(true); // SELECT chỉ đọc, không có side effect.

    // defer tạo một ReactiveResultSet MỚI cho mỗi subscription.
    return Flux.defer(() -> Flux.from(session.executeReactive(statement)))
        .map(row -> new EventView(
            row.getInstant("event_time"),
            row.getUuid("event_id"),
            row.getString("payload")))
        .limitRate(2);
}
~~~

Prepared statement (tạo và dùng lại khi session còn sống):

~~~java
PreparedStatement select = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM stream_lab.events_by_device " +
    "WHERE device_id = ? AND event_day = ? " +
    "LIMIT 100");
~~~

Ở đây:

- `SELECT` có đầy đủ **partition key**; driver có thể tính routing key/token và ưu tiên local replica theo load balancing policy.
- `LOCAL_QUORUM` phải có RF/DC phù hợp; không tự hoạt động trên lab một node với RF=3.
- `setPageSize(2)` chỉ là **page size mong muốn**, không giới hạn kết quả ở 2.
- `LIMIT 100` là giới hạn server-side để không trả quá 100 rows; nó vẫn không đảm bảo query rẻ nếu partition cực rộng hoặc có tombstone.
- `limitRate(2)` là cách điều tiết **upstream demand của Reactor**, không phải một API đặt CQL page size.
- `Flux.defer` là cách cho phép một **method repository** trả publisher có thể được subscribe nhiều lần bằng cách tạo truy vấn mới mỗi lần. Không dùng nếu việc truy vấn lặp lại làm sai nghiệp vụ.

### 6.2. Trong HTTP WebFlux, trả publisher cho framework

Ví dụ một controller đơn giản (phần auth/validation được rút gọn):

~~~java
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/devices")
final class DeviceEventController {
    private final EventQueryService queryService;

    DeviceEventController(EventQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{deviceId}/days/{day}/events")
    Flux<EventView> events(@PathVariable UUID deviceId,
                           @PathVariable LocalDate day) {
        return queryService.events(deviceId, day);
        // Không gọi .subscribe(), .block() hoặc .blockLast() tại đây.
    }
}
~~~

`EventQueryService` là bean ứng dụng giả định sử dụng `findEvents(...)` phía trên; ví dụ controller chưa bao gồm cấu hình Spring Boot, auth và giới hạn query nên **không phải ứng dụng standalone**. WebFlux chịu trách nhiệm subscribe theo vòng đời response, điều tiết downstream và báo cancellation khi client ngắt kết nối.

**Lưu ý Spring Data Cassandra:** Reactive repositories/`ReactiveCqlTemplate` có thể xây pipeline từ **API async của driver** rồi expose `Flux/Mono`. Không mặc nhiên suy mọi method Spring Data đều trả chính đối tượng `ReactiveResultSet` từ `executeReactive`. Nhưng các nguyên tắc *chưa subscribe thì chưa thực thi*, demand, cancellation và tránh block vẫn rất quan trọng ở tầng Reactor.

### 6.3. Không dùng .subscribe() để “kích hoạt sớm” rồi bỏ kết quả

Phản ví dụ:

~~~java
Flux<EventView> flux = findEvents(session, select, deviceId, day);

// SAI nếu HTTP framework cũng subscribe vào publisher này:
// flux.subscribe(row -> System.out.println("side effect"));
// return flux;
~~~

Với `Flux.defer`, hai subscriptions gây **hai CQL queries độc lập**. Với `Flux.from(existingReactiveResultSet)`, lần subscribe thứ hai **lỗi**. Ngoài ra, manual subscription không còn gắn chặt với timeout, cancellation và xử lý error của HTTP request.

Nếu cần logging/metrics trên **cùng một execution**, dùng `doOnNext`/`doOnError`/`doFinally` trong pipeline mà framework sẽ subscribe, không subscribe thêm chỉ để ghi log.

## 7. Luồng ghi: Publisher rỗng không có nghĩa là chưa ghi

### 7.1. INSERT/UPDATE không điều kiện thường không phát row

Một `INSERT` CQL không phải query trả danh sách kết quả. Với `executeReactive(insertStatement)`, publisher thường **phát 0 `ReactiveRow`**, rồi `onComplete` khi request hoàn tất bình thường.

~~~mermaid
sequenceDiagram
    participant A as Reactor / Subscriber
    participant B as ReactiveResultSet
    participant C as Cassandra
    A->>B: subscribe + request(1)
    B->>C: INSERT ...
    C-->>B: Success (không có rows)
    B-->>A: onComplete()
    Note over A,B: Không có onNext nhưng có thể ghi đã thành công
~~~

Điều này **không** nói rằng dữ liệu đã được purge/repair, mọi replica đều cập nhật hoặc không có lỗi về sau. Nó nói rằng câu CQL trả response thành công theo consistency của statement. Với timeout/mất ACK, outcome của mutation có thể **không xác định** ngay cả khi client thấy `onError`.

### 7.2. doOnNext không kích hoạt truy vấn, flatMap mới subscribe publisher con

Ví dụ **sai**:

~~~java
Flux.just(insertStatementA, insertStatementB)
    .doOnNext(session::executeReactive)
    .blockLast(); // doOnNext gọi phương thức tạo Publisher nhưng bỏ qua nó.
~~~

Ở đây pipeline ngoài có subscriber, nhưng mỗi `executeReactive` chỉ tạo **một Publisher lạnh** rồi bị bỏ. **Không có subscription vào result set con nên không có INSERT nào được thực thi**.

Ví dụ đúng với Reactor:

~~~java
Flux.just(insertStatementA, insertStatementB)
    .concatMap(stmt -> Flux.from(session.executeReactive(stmt)).then())
    .blockLast(); // Chỉ dùng .blockLast() trong CLI/test.
~~~

`concatMap` subscribe lần lượt từng câu lệnh, chờ completion của câu trước mới tiếp tục. Điều đó giúp giới hạn số writes đồng thời bằng 1, nhưng **không biến các câu lệnh thành một transaction liên partition**.

### 7.3. Đếm số lệnh hoàn thành, không đếm số rows

~~~java
import reactor.core.publisher.Flux;

Flux<BoundStatement> writes = Flux.fromIterable(writeStatements);

Flux<Integer> acknowledgements = writes.flatMap(
    stmt -> Flux.from(session.executeReactive(stmt)).thenReturn(1),
    8
);

// sum() ở đây chỉ minh họa việc đếm completed write requests.
// Với Reactor có thể dùng:
// Mono<Long> completedCount = acknowledgements.count();
~~~

**Giải thích chính xác:** `thenReturn(1)` phát số 1 **sau khi result publisher hoàn thành bình thường**. Nó phù hợp để đếm write requests đã có response thành công; **không chứng minh toàn bộ nghiệp vụ nhiều bảng atomic**, không thay thế LWT và không tự bảo đảm hiệu lực của retry sau timeout.

Nếu một lệnh là LWT, đừng tự coi completion = `[applied]=true`. Dùng `ReactiveResultSet.wasApplied()` để xác định điều kiện đã được áp dụng hay không, rồi ánh xạ kết quả theo nghiệp vụ.

### 7.4. Giới hạn concurrent writes: demand ở phía Cassandra không đầy đủ

Driver 4.19 lưu ý native protocol **không cung cấp cơ chế backpressure hai chiều như Reactive Streams**. Trong luồng ghi, Cassandra **không gửi `request(n)` cho Java** để nói còn chỗ cho bao nhiêu mutations; nếu upstream phát nhanh hơn năng lực coordinator, cluster có thể gặp `WriteTimeoutException`, `OverloadedException`, GC/network queue và các lỗi khác.

Do đó, Reactor phải **giới hạn số Publisher con được subscribe đồng thời**:

~~~java
Flux.fromIterable(writeStatements)
    .flatMap(
        stmt -> Flux.from(session.executeReactive(stmt)).thenReturn(1),
        8  // Lab: tối đa 8 request CQL con in-flight từ operator này.
    )
    .count(); // Trả Mono<Long>; phải được subscribe ở caller.
~~~

Thông số 8 **chỉ là ví dụ**; tìm mức phù hợp theo p95/p99, RF/CL, kích thước mutation, hot partitions, driver pool và server load. Nếu nhiều application instances cùng ghi, concurrency=8 **trên mỗi instance** vẫn có thể tạo tổng tải 8×N; phải tính limit toàn hệ thống.

**Cẩn trọng với flatMap:** nó có thể cho các writes hoàn thành **khác thứ tự input**. Nếu cùng partition cần bảo toàn trình tự business operations, cân nhắc `concatMap` hoặc nhóm theo key có concurrency giới hạn; dù vậy một pipeline tuần tự không thay thế CAS, timestamp/conflict resolution và idempotency khi xảy ra retry.

## 8. Vòng đời kết quả khi complete, error và cancel

### 8.1. Bảng trạng thái và ý nghĩa vận hành

| Sự kiện | Subscriber nhận gì? | Điều đã/không được bảo đảm |
|---|---|---|
| `onSubscribe` | Một `Subscription` | CQL được tạo ở phía driver, không chứng minh đã nhận row |
| `request(n)` | Demand cộng dồn | Không đảm bảo server chỉ scan n rows |
| `onNext(row)` | Một giá trị `ReactiveRow` | Dữ liệu có thể đến từ page đã fetch, không bảo đảm snapshot toàn cluster |
| `onComplete()` | Kết thúc thành công, không còn row | SELECT đã được tiêu thụ hết theo query; ghi đã có response theo CL |
| `onError(e)` | Terminal error | Có thể đã phát **một phần rows**, và mutation có thể có unknown outcome |
| `cancel()` | Không bắt buộc có `onComplete` | Dừng quan tâm kết quả phía subscriber, **không rollback** Cassandra |
| `session.closeAsync()`/`close()` | Đóng resource/pools của CqlSession | Không nên dùng để “cancel một query” trong session dùng chung |

Một subscriber chỉ có thể nhận **một terminal event** `onComplete` hoặc `onError`. `cancel()` không phải “onError(CancellationException)” bắt buộc. Khi dùng Reactor, `doFinally(signalType)` có thể báo `CANCEL` để quan sát hủy và giải phóng tài nguyên **thuộc pipeline**.

### 8.2. Cancel không hủy chắc chắn work đã gửi tới server

Giả sử frontend xem 20 rows rồi đóng tab:

~~~text
HTTP client disconnects
  -> WebFlux/Reactor upstream subscription.cancel()
  -> Driver ngừng phát thêm row và có thể ngừng fetch pages mới
  -> Những page/request đã gửi tới coordinator vẫn có thể xử lý xong
  -> CqlSession/pool chung của ứng dụng vẫn phải sống cho request khác
~~~

Không suy rằng:

- Cassandra đã dừng mọi request đang xử lý trên replica.
- Những mutations đã gửi sẽ rollback.
- Không còn CPU/IO server đã tiêu tốn.
- Cancel tương đương `DELETE`/`TRUNCATE` hoặc thu hồi paging state trên disk.

Với SELECT, cancel thường giúp **tránh tiếp tục tiêu thụ và fetch những trang chưa cần**, nhưng không phải bảo đảm chính xác từng byte mạng. Với write hoặc LWT, cancellation sau khi gửi request có thể tạo **unknown outcome**, cần dựa vào idempotency/marker nghiệp vụ nếu caller sẽ retry.

### 8.3. doFinally đúng để làm cleanup/metrics

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger delivered = new AtomicInteger();
Flux<EventView> stream = findEvents(session, select, deviceId, day)
    .doOnNext(event -> delivered.incrementAndGet())
    .doOnError(error -> metrics.recordQueryError(error))
    .doFinally(signal -> {
        metrics.recordTermination(signal.name(), delivered.get());
        // Đóng resource per-subscription nếu đã tạo ở bên ngoài.
        // KHÔNG đóng session chung tại đây.
    });
~~~

`metrics` là service quan sát giả định; đoạn code mô tả pattern, không phải chương trình chạy riêng. Nếu một `Flux` có **nhiều subscriptions** nhờ `defer`, dùng biến `AtomicInteger` được tạo ngoài pipeline như ví dụ sẽ **trộn đếm** giữa chúng; production nên đặt state per-subscription bằng `Flux.defer(() -> { AtomicInteger count = ...; return ...; })` hoặc Reactor Context/metrics operator tương ứng.

### 8.4. onError có thể đến sau vài onNext

Tình huống SELECT có nhiều pages:

~~~text
Page 1: onNext row 1..100
Page 2: onNext row 101..200
Fetch page 3: timeout / node Down
Terminal: onError(DriverTimeoutException)
~~~

Client đã thấy 200 rows **không có nghĩa toàn query thành công**. Nếu operator `onErrorResume(error -> Flux.empty())` biến lỗi thành completion không báo, ứng dụng có thể nhầm 200 rows thành **toàn bộ tập dữ liệu**, dẫn đến export thiếu.

Nếu nghiệp vụ cho phép partial results, hãy **biểu diễn rõ trạng thái partial/incomplete** bằng protocol/API và checkpoint, không chỉ nuốt lỗi. Nếu retry toàn query sau partial delivery, subscriber có thể thấy **duplicate rows**; cần dedup theo primary key hoặc cơ chế resumable paging/checkpoint được kiểm thử.

### 8.5. Timeout phía driver và timeout toàn stream

`basic.request.timeout`/`Statement.setTimeout(Duration)` trong Java Driver giới hạn các request của driver theo ngữ nghĩa phiên bản, nhưng một stream lớn gồm nhiều pages hoặc nhiều queries có thể kéo dài hơn deadline nghiệp vụ. Hãy dùng một **deadline đầu-cuối** ở application.

Trong Reactor:

~~~java
import java.time.Duration;

Flux<EventView> bounded = findEvents(session, select, deviceId, day)
    .timeout(Duration.ofSeconds(2));
~~~

`Flux.timeout(Duration)` thường giới hạn **thời gian chờ giữa các tín hiệu tiếp theo**, **không tương đương một deadline tuyệt đối hai giây cho toàn bộ stream** khi hàng liên tục đến. Với deadline tuyệt đối, dùng cơ chế timeout từ context/framework hoặc một timer chung và `takeUntilOther`/cancellation được kiểm chứng; không reset budget cho mỗi page.

**Khi timeout/hủy:** có thể ngừng tiêu thụ phía Java, nhưng Cassandra vẫn xử lý công việc đã nhận. Không dùng timeout/cancel như rollback guarantee.

## 9. Vòng đời CqlSession và tài nguyên

### 9.1. Session không phải một kết quả truy vấn

`CqlSession` giữ connection pools, topology/schema metadata, prepared statement cache và trạng thái network. `ReactiveResultSet` biểu thị **kết quả của một query riêng**. Vì thế:

- Tạo **một session dài hạn** cho một ứng dụng/service phù hợp, không tạo session mỗi subscriber/row/HTTP request.
- `ReactiveResultSet` là **single-subscription**, có vòng đời riêng.
- Khi `cancel()` một query, **không đóng session dùng chung** vì còn requests khác.
- Khi application shutdown, ngừng nhận requests mới, đợi in-flight trong giới hạn rồi **đóng CqlSession** theo lifecycle của framework.
- Đóng session trước khi publisher đang chờ subscribe hoặc fetch pages có thể làm query lỗi; quản lý ownership/lifecycle tường minh.

### 9.2. Pattern cấu hình bean trong Spring Boot

Nếu dùng Spring Boot:

~~~java
// Chỉ minh họa lifecycle; class ứng dụng/config và credentials phải được
// cung cấp theo BOM và môi trường thực tế.
//
// @Bean(destroyMethod = "close")
// CqlSession cassandraSession(DriverConfigLoader config) {
//     return CqlSession.builder().withConfigLoader(config).build();
// }
~~~

Trong Spring Data Cassandra, autoconfiguration có thể đã sở hữu `CqlSession`; **không tự tạo thêm session không cần thiết** gây nhiều connection pools và schema listeners. Tài nguyên do bean tạo phải được framework đóng khi dừng ứng dụng; không đóng trong `doFinally` của từng request.

### 9.3. Tài nguyên thuộc pipeline và doFinally/usingWhen

Nếu mỗi request tạo file tạm, lease, buffer hoặc outbound stream riêng, phải giải phóng đúng cả ba nhánh **complete/error/cancel**. Reactor `doFinally` hoặc `usingWhen` giúp gắn cleanup với subscription lifecycle. Nhưng cleanup của Java-side resource **không** suy ra mutation Cassandra đã rollback.

Ví dụ ý tưởng:

~~~java
Flux<EventView> flow = findEvents(session, select, deviceId, day)
    .doFinally(signalType -> {
        // COMPLETED/ON_ERROR/CANCEL ở Reactor.
        // Ghi metric, release per-request resources.
    });
~~~

Không dùng `try-with-resources(CqlSession ...)` ở một service method trả `Flux` nếu block `try` sẽ đóng session **trước khi publisher được subscribe**. Phải quản lý session theo application lifetime, hoặc dùng một resource scope reactive thực sự đúng vòng đời subscriber.

## 10. Metadata kết quả và LWT trong ReactiveResultSet

### 10.1. Hai lớp metadata

Ngoài rows, `ReactiveResultSet` cung cấp các metadata publishers:

~~~java
Publisher<? extends ColumnDefinitions> getColumnDefinitions();
Publisher<? extends ExecutionInfo> getExecutionInfos();
Publisher<Boolean> wasApplied();
~~~

Tương ứng với:

- **ColumnDefinitions:** schema cột của result.
- **ExecutionInfos:** thông tin các executions/pages theo driver, gồm coordinator và metadata tùy request.
- **wasApplied:** kết quả của conditional LWT hoặc giá trị theo quy ước API cho non-conditional CQL.

Theo tài liệu Java Driver, các publishers metadata **không thể hoàn tất trước khi query result chính hoàn tất**; nếu query chính lỗi, metadata publishers báo cùng lỗi. Vì vậy, đừng chỉ subscribe metadata trước rồi đợi nó hoàn tất trong khi chẳng ai tiêu thụ source rows.

### 10.2. Chỉ subscribe kết quả một lần rồi lấy metadata

~~~java
import com.datastax.dse.driver.api.core.cql.reactive.ReactiveResultSet;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

ReactiveResultSet rs = session.executeReactive(selectStatement);

// Source rs được subscribe ĐÚNG MỘT LẦN:
Mono<Void> rowsCompleted = Flux.from(rs).then();

Mono<Void> printInfo = rowsCompleted.thenMany(
        Flux.from(rs.getExecutionInfos()))
    .doOnNext(info ->
        System.out.println("Coordinator=" + info.getCoordinator()))
    .then();

// Khi caller subscribe printInfo, nó trước hết consume rows,
// sau đó subscribe metadata. Chỉ dùng block() ở CLI/test.
// printInfo.block();
~~~

Ví dụ này **cố ý bỏ nội dung rows** để minh họa metadata. Trong ứng dụng cần đọc dữ liệu, nên mapping và xử lý rows trong cùng pipeline, rồi mới chuyển sang tổng hợp metadata. **Đừng subscribe rowsCompleted riêng, rồi lại subscribe printInfo**: điều đó sẽ subscribe `rs` hai lần và thất bại.

Với `ReactiveRow`, cũng có thể đọc thông tin từng row:

~~~java
Flux.from(session.executeReactive(selectStatement))
    .doOnNext(row -> {
        // Metadata cho row/page tương ứng; đừng log mỗi row ở tải lớn.
        var coordinator = row.getExecutionInfo().getCoordinator();
    });
~~~

`var` yêu cầu Java 10+; nếu app dùng Java 8, khai báo kiểu `Node` tường minh. Không dùng kiểu biến ví dụ để suy luận coordinator đã liên lạc replica nào; CL/replication còn do Cassandra thực hiện.

### 10.3. Đọc wasApplied() cho LWT

Giả sử câu CQL đã prepare là `INSERT ... IF NOT EXISTS`:

~~~java
ReactiveResultSet rs = session.executeReactive(conditionalWrite);

Mono<Boolean> applied = Flux.from(rs)
    .then(Mono.from(rs.wasApplied()));
~~~

Pipeline này tiêu thụ result chính rồi đọc metadata `wasApplied` (không subscribe result lần hai). Sau đó:

- `true`: điều kiện đã áp dụng theo response LWT.
- `false`: điều kiện CAS không thỏa, **không phải lỗi mạng**.
- `onError`: phải phân loại timeout/unavailable/unknown outcome; không suy là false.

Nếu muốn các cột điều kiện trả về khi CAS false, có thể xử lý `ReactiveRow` nếu query đó phát hàng và đối chiếu `ColumnDefinitions`; tập cột trả về **tùy loại LWT, schema và phiên bản**. Với `UPDATE ... IF EXISTS` false, thường chỉ có `[applied]`. Với `INSERT IF NOT EXISTS` false, có thể trả dữ liệu hàng hiện hữu. Không giả định mọi LWT đều có đủ entity.

**Lưu ý:** đối với non-LWT, `wasApplied` theo API có thể trả `true` theo quy ước; **không dùng nó để chứng minh `CREATE TABLE IF NOT EXISTS` vừa tạo bảng mới**.

## 11. Nhiều subscriber, cache, share và nguy cơ dữ liệu cũ

### 11.1. Ba chiến lược khác nhau

| Mục tiêu | Kỹ thuật | Khi nào dùng | Rủi ro |
|---|---|---|---|
| Mỗi subscriber **chạy query mới** | `Flux.defer(() -> Flux.from(session.executeReactive(stmt)))` | Mỗi HTTP request đọc trạng thái tại thời điểm riêng | Hai executions, dữ liệu có thể khác, tải tăng |
| Hai downstream observers xem **cùng một execution** | `Flux.from(rs).publish()` và kết nối có kiểm soát | Tính hai loại aggregate cùng lúc trên một stream | Subscriber đến muộn có thể bỏ lỡ rows; phải điều phối |
| Nhiều subscribers cùng đọc **kết quả đã lưu** | `Flux.from(rs).cache()` | Tập kết quả nhỏ, có giới hạn rõ | Dễ giữ toàn bộ rows trong RAM và dữ liệu trở nên stale |

**Không có giải pháp chung** cho cả ba nhu cầu. Nếu hai endpoint gọi lại một `ReactiveResultSet` đã subscribe, đó không phải cơ chế cache: subscription thứ hai thất bại.

### 11.2. Ví dụ cache một tập nhỏ

~~~java
import reactor.core.publisher.Flux;

// Chỉ hợp lý khi query đã có LIMIT nhỏ và dữ liệu không nhạy cảm.
Flux<String> cached = Flux.from(session.executeReactive(
        "SELECT status FROM stream_lab.device_status_by_id " +
        "WHERE device_id = 11111111-1111-4111-8111-111111111111"))
    .map(row -> row.getString("status"))
    .cache();

// Các lần subscribe vào "cached" nhận replay từ Reactor cache.
// Driver source chỉ cần một subscription, không còn lỗi unicast.
~~~

**Phân biệt:** `cache()` không refresh Cassandra khi subscriber mới xuất hiện; kết quả có thể stale. `cache()` không có giới hạn kích thước theo mặc định, nên dùng nó cho SELECT hàng triệu rows có thể làm OOM và vô tình giữ payload nhạy cảm trong memory lâu hơn chính sách retention. Cân nhắc cache có TTL/size explicit ở tầng phù hợp hoặc chạy query riêng.

### 11.3. Multicast không phải replay

~~~java
Flux<String> shared = Flux.from(session.executeReactive(
        "SELECT status FROM stream_lab.device_status_by_id " +
        "WHERE device_id = 11111111-1111-4111-8111-111111111111"))
    .map(row -> row.getString("status"))
    .publish()
    .autoConnect(2);
~~~

Pipeline trên đợi **hai subscribers** rồi mới subscribe upstream, tránh lỗi source single-subscription. Nhưng nó là **multicast**, không tự lưu/replay rows cho người đến muộn; hai subscribers phải phối hợp đăng ký đúng thời điểm. **Không gọi `shared.blockLast()` tuần tự hai lần rồi chờ nó chạy**: lần đầu có thể đợi subscriber thứ hai và không bao giờ bắt đầu.

Với export lớn, streaming multicast có thể giảm RAM so với cache nhưng cần chính sách xử lý subscriber chậm, backpressure, cancellation và lỗi toàn luồng. Nếu một subscriber bị chậm cực độ, tốc độ chung có thể bị hạn chế.

### 11.4. Retry bằng defer: mỗi retry là một query mới

~~~java
// Ý tưởng cho SELECT idempotent; không chạy khi chưa xác định timeout policy.
Flux<EventView> retryable = Flux.defer(() ->
        Flux.from(session.executeReactive(readStatement)))
    .map(row -> new EventView(
        row.getInstant("event_time"),
        row.getUuid("event_id"),
        row.getString("payload")));

// Nếu dùng retryWhen, nó resubscribe vào "defer" và chạy query mới.
// Phải có max attempts, backoff+jitter và deadline nghiệp vụ.
~~~

Nếu lỗi xuất hiện **sau khi đã phát hai trang**, retry toàn query có thể phát lại rows cũ, **tạo dữ liệu trùng downstream**. Với nghiệp vụ export/ETL cần resume token/checkpoint theo primary key và kiểm soát paging state, dedup hoặc start-over ở một sink transactional phù hợp. Không chỉ thêm `retry(3)` vào stream rồi coi là exactly-once.

## 12. Lab CQL và Java: quan sát subscription thật

### 12.1. Chuẩn bị môi trường

Ví dụ giả định **cluster lab** Apache Cassandra 4.x/5.x có datacenter tên `dc1` và **ba node** để dùng RF=3 cùng `LOCAL_QUORUM`. Nếu dùng lab một node, chỉnh RF/CL đúng điều kiện thực. Không chạy fault injection trên production.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

Trong `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS stream_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS stream_lab.events_by_device (
  device_id uuid,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS stream_lab.device_status_by_id (
  device_id uuid PRIMARY KEY,
  status text
);

INSERT INTO stream_lab.device_status_by_id (device_id, status)
VALUES (11111111-1111-4111-8111-111111111111, 'ACTIVE');
~~~

`IF NOT EXISTS` **không tự sửa schema nếu bảng/keyspace đã tồn tại**. Trước khi thử, đối chiếu `DESCRIBE KEYSPACE stream_lab` và `DESCRIBE TABLE stream_lab.events_by_device`; tên datacenter phải khớp topology. Mẫu có một partition cố định để dễ kiểm tra, nhưng không dùng nó làm benchmark hiệu năng toàn cluster.

### 12.2. Tạo sáu sự kiện để thấy trang và hủy

~~~sql
INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:00:00Z',
  22222222-2222-4222-8222-000000000001, 'sample-1');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:01:00Z',
  22222222-2222-4222-8222-000000000002, 'sample-2');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:02:00Z',
  22222222-2222-4222-8222-000000000003, 'sample-3');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:03:00Z',
  22222222-2222-4222-8222-000000000004, 'sample-4');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:04:00Z',
  22222222-2222-4222-8222-000000000005, 'sample-5');

INSERT INTO stream_lab.events_by_device
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21', '2026-11-21T10:05:00Z',
  22222222-2222-4222-8222-000000000006, 'sample-6');

SELECT event_time, event_id, payload
FROM stream_lab.events_by_device
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Vì clustering order `event_time DESC`, SELECT trả event mới hơn trước. Tất cả ID và payload là **dữ liệu mẫu**, không đại diện user/token thực.

### 12.3. Test StepVerifier với demand khởi đầu bằng 0

Tạo Reactor test với `reactor-test` tương thích Reactor version/BOM:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

UUID deviceId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111");
LocalDate day = LocalDate.of(2026, 11, 21);

Flux<EventView> stream = findEvents(session, select, deviceId, day);

StepVerifier.create(stream, 0L) // Ban đầu không có row demand.
    .expectSubscription()
    .thenRequest(1)
    .expectNextCount(1)
    .thenRequest(2)
    .expectNextCount(2)
    .thenCancel()
    .verify();
~~~

Kỳ vọng:

- Subscriber nhận **không quá 1 row** trước khi cấp thêm 2 demand, theo Reactive Streams contract.
- Đã quan sát tổng 3 rows, sau đó hủy subscription.
- Cần có **ít nhất ba rows** trên source trong lab. Với dữ liệu bị TTL/xóa hoặc query sai partition, test có thể kết thúc sớm.
- Hủy không làm mất ba rows còn lại trong Cassandra; ta chỉ không tiếp tục tiêu thụ query đó.
- Dù trang đặt `pageSize=2`, demand vẫn là số row được phép **phát**, không nhất thiết số row đã được server scan hoặc trả trong một page.

Test này xác minh contract; muốn biết số page fetch thật phải dùng metrics/tracing phù hợp, không suy từ `expectNextCount(3)`.

### 12.4. Test complete khi đọc hết kết quả

~~~java
StepVerifier.create(
        findEvents(session, select, deviceId, day)
            .map(EventView::eventId))
    .expectNextCount(6)
    .verifyComplete();
~~~

Lab chỉ đạt kỳ vọng nếu sáu rows ở trên tồn tại và không có rows khác cùng partition đã được thêm từ lần chạy trước. Nếu chạy lặp, **tạo partition key mới hoặc dọn lab có kiểm soát**, không dùng một dataset đã thay đổi rồi cố coi số 6 là chuẩn cố định.

### 12.5. Test nhiều subscribers

~~~java
ReactiveResultSet rs = session.executeReactive(readStatement);
Flux<ReactiveRow> once = Flux.from(rs);

// Trong test độc lập có dữ liệu:
// StepVerifier.create(once).expectNextCount(6).verifyComplete();
// StepVerifier.create(once).expectError(IllegalStateException.class).verify();
~~~

Lần hai lỗi vì **cùng ReactiveResultSet bị subscribe lại**, không phải Cassandra “không có hàng”. Để test cách chạy query mới mỗi lần, dùng:

~~~java
Flux<ReactiveRow> freshEachTime =
    Flux.defer(() -> Flux.from(session.executeReactive(readStatement)));
~~~

Hoặc cache chỉ khi tập row **nhỏ và có giới hạn**, không biến một query streaming thành cache toàn bảng.

### 12.6. Test write rỗng và completion

~~~java
import reactor.core.publisher.Mono;

// insertStatement được prepare/bind đúng vào dữ liệu lab.
Mono<Void> completedWrite = Flux
    .from(session.executeReactive(insertStatement))
    .then();

StepVerifier.create(completedWrite)
    .verifyComplete();
~~~

Không nên viết `expectNextCount(1)` chỉ để xác nhận INSERT: mutation không điều kiện **không nhất thiết phát một row**. Với LWT cần kiểm tra riêng `wasApplied`, không suy `onComplete` bằng điều kiện đã thắng. Nếu write bị timeout, test phải kỳ vọng `onError`/unknown outcome, không cho rằng mutation rollback.

### 12.7. Test lỗi giữa các trang

Với proxy/cluster lab được phép, tạo timeout khi đang fetch page tiếp theo. Ghi lại:

1. Số rows subscriber đã nhìn thấy trước `onError`.
2. Số rows được persist/đã export tới sink.
3. Có `onComplete` không? (Không, nếu stream kết thúc bằng `onError`.)
4. Nếu retry từ đầu, có duplicate row IDs không?
5. Deadline toàn export, số retries/attempts, CPU/network/driver pool.

**Không** chỉ viết `onErrorResume(error -> Flux.empty())` để “cho dashboard xanh”, vì như vậy partial export sẽ biến thành success giả. Phải trả trạng thái incompleteness/partial result rõ ràng hoặc bảo đảm idempotent resume từ checkpoint.

## 13. Observability và tối ưu vận hành

### 13.1. Đo cả consumer, driver lẫn cluster

| Lớp | Chỉ số nên đo | Vì sao quan trọng |
|---|---|---|
| **Subscriber/Reactor** | Subscription starts, received rows, request batches, cancellation, completion, error | Xác định ứng dụng tiêu thụ đủ hay bỏ giữa chừng |
| **Demand/Buffer** | Rows pending, prefetch, queue depth, `limitRate` và concurrency | Phát hiện operator buffer quá nhiều hoặc subscriber chậm |
| **Java Driver** | Requests/s, in-flight, throttling queue/delay, pool available-streams, page latencies | Chứng minh DB/network có bị nghẽn |
| **Cassandra** | Read/write p95/p99, dropped messages, CPU, GC, tombstone scanned, compaction backlog | Phân biệt subscriber chậm với query/datastore chậm |
| **Business** | Rows thực xuất, duration end-to-end, partial exports, duplicate side effects | Không chỉ “stream không ném exception” |

Java Driver metrics có thể **tắt mặc định**, cần bật rõ loại metric theo version và đánh giá overhead. Không coi cặp metric `onNext/s` và `CQL requests/s` là cùng đơn vị: một query có thể sinh nhiều rows/pages, hoặc một write không sinh row nào.

### 13.2. Request timeout và backpressure không thay SLA

Nếu consumer rất chậm, mặc dù `request(n)` điều tiết onNext, tổng thời gian export có thể tăng. Vấn đề có thể là:

- Thiếu demand vì subscriber chờ xử lý blocking.
- Operator `publishOn` prefetch quá nhiều/queue tăng.
- Partition chứa nhiều tombstone hoặc trả mỗi page rất ít rows.
- Network WAN/TLS/JVM GC hoặc coordinator chậm.
- Too many concurrent writes không có backpressure upstream.

Hãy đo **end-to-end latency và số pages** trước khi chỉnh page size hoặc retry. Giảm `pageSize` quá nhỏ có thể tăng số round trips; tăng quá lớn có thể tăng bộ nhớ và response size. Sử dụng nhiều partitions/keyspaces khi cần, nhưng không đổi partition key chỉ để sửa một subscriber bị block.

### 13.3. Ngăn subscribe nhầm hai lần ở tầng framework

Một số pattern gây double execution:

~~~text
ReactiveResultSet rs = session.executeReactive(statement)
  -> Flux.from(rs) trả cho HTTP
  -> service khác cũng subscribe để audit
  => subscriber thứ hai lỗi

Flux.defer(() -> Flux.from(session.executeReactive(statement)))
  -> HTTP subscribe
  -> audit subscribe
  => hai CQL executions khác nhau (không lỗi nhưng nhân tải)
~~~

Muốn audit cùng một request, dùng side-effect operator trong **một pipeline**, hoặc publish event đã được chuẩn hóa qua outbox/service khác có ngữ nghĩa rõ. **Không để một subscription phụ vô tình chạy lại một `INSERT` hoặc một LWT**.

## 14. Tình huống thực tế và bài tập

### Bài 1 — Chưa subscribe có ghi được không?

Code gọi `session.executeReactive(insertStatement)` rồi bỏ giá trị trả về. Log nói “đã gửi thành công”. Hàng đã chắc được ghi chưa?

**Đáp án:** chưa. `ReactiveResultSet` là publisher lạnh; không có subscription thì query chưa được kích hoạt theo reactive API.

### Bài 2 — request(2) có làm server chỉ đọc hai hàng?

Một subscriber gọi `request(2)`. Người viết API cho rằng Cassandra chỉ scan đúng 2 rows nên chi phí server bằng 2 rows. Đúng không?

**Đáp án:** sai. Demand giới hạn số phần tử `onNext`, còn Cassandra native protocol và driver vận hành theo **page**. Một page có thể chứa nhiều rows và server đã đọc/scan nhiều hơn demand.

### Bài 3 — request(0) để tạm dừng?

Subscriber gọi `request(0)` khi queue đầy. Tại sao sai?

**Đáp án:** số phần tử yêu cầu phải dương. Theo Reactive Streams spec, request không dương là vi phạm và phải báo `onError(IllegalArgumentException)` khi còn active. Muốn tạm dừng thì chưa xin thêm demand, đồng thời quản lý queue bounded.

### Bài 4 — Cancel có xóa dữ liệu không?

Client ngắt kết nối khi đã nhận 4/100 rows. App gọi `cancel()` và hiểu rằng Cassandra đã hủy CQL hoàn toàn, đồng thời trả lại tài nguyên cluster ngay lập tức. Nhận định nào đúng?

**Đáp án:** cancellation giúp ngừng phát/fetch thêm khi được quan sát, nhưng **không đảm bảo** hủy request đang xử lý ở coordinator và không rollback mutation. `CqlSession` vẫn là tài nguyên chung của app.

### Bài 5 — Vì sao lần subscribe thứ hai lỗi?

Hai thành phần dùng cùng một `ReactiveResultSet`; subscriber thứ hai nhận `IllegalStateException`. Có phải Cassandra Down?

**Đáp án:** không; đó là ràng buộc **single-subscription**. Dùng một pipeline multicast/cache có chủ đích, hoặc tạo result set mới per subscriber nếu muốn query lại.

### Bài 6 — Write không có onNext

Một INSERT reactive `onComplete` nhưng không có `onNext`. Developer kết luận chưa ghi thành công. Đúng hay sai?

**Đáp án:** sai. CQL mutation bình thường không trả rows; completion bình thường có thể biểu thị đã có response thành công theo CL. Cần xử lý `onError` và unknown outcome riêng, không dựa số row bằng 0.

### Bài 7 — flatMap với concurrency vô hạn

Một job tạo 200.000 INSERT publishers rồi dùng `flatMap` không giới hạn thực tế và cluster báo overloaded. Có phải Cassandra không hỗ trợ reactive?

**Đáp án:** không. Cassandra không có wire-level Reactive Streams demand cho ghi; cần giới hạn in-flight writes, backpressure đầu vào, retry budget và tải đa instance. Sử dụng `flatMap(..., concurrency)` hoặc `concatMap` theo yêu cầu thứ tự.

### Bài 8 — Partial results bị nuốt lỗi

Export đã nhận 2 page, page thứ ba lỗi, pipeline dùng `onErrorResume(e -> Flux.empty())` và trả HTTP 200 với 200 rows. Rủi ro?

**Đáp án:** hệ thống có thể báo hoàn tất khi **thiếu dữ liệu**. Phải truyền trạng thái partial/error, hoặc có checkpoint/retry idempotent bảo đảm completeness; không che lỗi bằng completion.

### Bài 9 — Cache cả bảng để hỗ trợ hai subscriber

Team dùng `Flux.from(rs).cache()` cho query trả hàng triệu records. Vấn đề?

**Đáp án:** Reactor có thể giữ toàn bộ rows trong memory, làm OOM hoặc lưu dữ liệu quá lâu; cần giới hạn query, cache bounded phù hợp hoặc streaming multicast. Nếu muốn hai executions độc lập, dùng `Flux.defer` và chấp nhận chi phí DB.

### Bài 10 — Timeout trong Reactor có phải deadline toàn stream?

Pipeline dùng `.timeout(Duration.ofSeconds(2))`; các rows liên tục đến mỗi giây trong một giờ. Có chắc stream dừng sau 2 giây tổng thời gian?

**Đáp án:** không. Operator dạng này thường áp timeout **giữa các tín hiệu**. Deadline toàn nghiệp vụ cần mốc thời gian tuyệt đối/budget riêng, không reset theo page hoặc row.

### Checklist hoàn thành

- [ ] Phân biệt `Publisher`, `Subscriber`, `Subscription` và `Processor`.
- [ ] Biết thứ tự `onSubscribe` → `onNext*` → `onComplete/onError`; `cancel()` không đồng nghĩa terminal signal.
- [ ] Hiểu `request(n)` cộng dồn, phải dương và không phát vượt demand.
- [ ] Biết `ReactiveResultSet` của Driver 4.x mặc định cold/unicast/single-subscription-only.
- [ ] Không bỏ publisher lạnh trả về từ `executeReactive` khi cần ghi.
- [ ] Không subscribe thủ công tại handler WebFlux rồi cũng trả Flux cho framework.
- [ ] Biết `Flux.defer` tạo **query mới** cho từng subscription; `cache/publish` chia sẻ một execution với giới hạn tương ứng.
- [ ] Biết demand điều tiết **fetch pages** chứ không ra lệnh server đọc đúng n rows.
- [ ] Phân biệt `request(n)`, `take(n)`, `limitRate(n)`, CQL `LIMIT n` và `setPageSize(n)`.
- [ ] Không đánh giá INSERT thất bại chỉ vì không có `onNext`.
- [ ] Có giới hạn concurrency/backpressure đầu vào khi gửi writes.
- [ ] Hiểu cancellation không rollback mutation hoặc đóng session chung.
- [ ] Biết query metadata publishers chỉ hoàn tất khi query result hoàn tất; không subscribe result chính hai lần.
- [ ] Có xử lý error/timeout, partial result và retries không phát duplicate ngoài ý muốn.
- [ ] Đã thử `StepVerifier` với initial demand 0, request thêm, complete và cancel.
- [ ] Đo p95/p99, in-flight writes, memory buffer, subscriptions, cancel/error và số rows thực xử lý.

## 15. Tài liệu tham khảo

1. Apache Cassandra Java Driver 4.19 — [Reactive Streams](https://apache.github.io/cassandra-java-driver/4.19.0/core/reactive/): publisher lạnh, giới hạn một subscriber, cách viết SELECT/INSERT, backpressure, cache, retry.
2. Apache Cassandra Java Driver 4.19 — [ReactiveResultSet API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/dse/driver/api/core/cql/reactive/ReactiveResultSet.html): `Publisher<ReactiveRow>` và `ReactiveQueryMetadata`.
3. Apache Cassandra Java Driver 4.19 — [ReactiveSession API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/dse/driver/api/core/cql/reactive/ReactiveSession.html): `executeReactive(String/Statement)`.
4. Apache Cassandra Java Driver 4.19 — [ReactiveRow API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/dse/driver/api/core/cql/reactive/ReactiveRow.html): giá trị của row và execution metadata.
5. Apache Cassandra Java Driver 4.19 — [Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): page size, paging state và đường fetch pages.
6. Apache Cassandra Java Driver 4.19 — [Async Programming](https://apache.github.io/cassandra-java-driver/4.19.0/core/async/): so sánh CompletionStage/AsyncResultSet với reactive consumption.
7. Reactive Streams JVM Specification — [Publisher/Subscriber/Subscription rules](https://github.com/reactive-streams/reactive-streams-jvm): `request(n)`, terminal signals, cancellation và thread-safety.
8. Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Flux.defer`, `flatMap` concurrency, `concatMap`, `limitRate`, `cache`, `publish`, `doFinally`, `StepVerifier`.
9. Spring Data Cassandra — [Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): composition vs execution, reactive repositories/templates và driver integration.
10. Apache Cassandra Documentation — [CQL Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) và [Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): partition key, clustering order, LIMIT và consistency.
