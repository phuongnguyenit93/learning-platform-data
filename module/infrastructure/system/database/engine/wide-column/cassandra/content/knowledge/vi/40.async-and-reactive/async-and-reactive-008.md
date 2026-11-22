# Reactive API, Publisher và điều kiện hỗ trợ theo driver khi truy vấn Apache Cassandra

## 1. Vấn đề: “không chặn luồng” chưa chắc là “reactive”

Trong module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, ứng dụng Java phải làm việc với CQL, **partition key**, replication, consistency level, compaction và repair trên Apache Cassandra phân tán. Khi ứng dụng cần truy vấn nhiều partition hoặc trả dữ liệu liên tục cho HTTP/gRPC, cách lấy kết quả ảnh hưởng trực tiếp đến **số request in-flight, bộ nhớ, tải coordinator/replica và tail latency**.

Ba cách thực thi thường được nhắc tới:

- **Đồng bộ:** `session.execute(statement)` trả `ResultSet`; thread gọi có thể chờ network.
- **Bất đồng bộ:** `session.executeAsync(statement)` trả `CompletionStage<AsyncResultSet>`; ứng dụng xử lý kết quả qua callback/future và chủ động xử lý page.
- **Reactive:** khi driver có API tương ứng, `session.executeReactive(statement)` cung cấp kết quả theo **Reactive Streams `Publisher`**, để bên nhận điều khiển nhu cầu nhận phần tử, thay vì luôn tạo ngay một danh sách lớn.

**Mục tiêu bài học** thuộc chương **Bất đồng bộ và reactive**:

1. Giải thích `Publisher`, `Subscriber`, `Subscription` và tín hiệu `request(n)`.
2. Xác định các **điều kiện cần về phiên bản driver, thư viện và kiểu API** để thực sự dùng Reactive API.
3. Kết nối prepared/bound CQL với `Publisher` và Reactor `Flux` khi lựa chọn tích hợp đó có sẵn.
4. Phân biệt **demand theo hàng (row)** với page size, server request, bytes và end-to-end rate limit.
5. Hiểu cancellation, cold publisher, nhiều subscriber, error handling và timeout.
6. Tránh dùng `block()`, `collectList()` hoặc fan-out vô hạn làm mất lợi thế reactive.
7. Liên hệ reactive execution với token-aware routing, CL, tombstone, replica load và tài nguyên Cassandra.
8. Viết kiểm thử và runbook vận hành cho workload reactive.

> **Reactive không làm CQL tự động nhanh hơn hoặc một truy vấn thiếu partition key thành hợp lệ.** Nó chủ yếu thay đổi cách Java tiêu thụ kết quả, điều phối concurrency và biểu đạt backpressure.

## 2. Điều gì xảy ra trên đường đi của một truy vấn?

~~~mermaid
flowchart LR
    A["HTTP/gRPC hoặc job"] --> B["Reactive Subscriber"]
    B -->|"request(n)"| C["Publisher của Java Driver"]
    C --> D["Coordinator Cassandra"]
    D --> E["Replica theo token, RF và CL"]
    E --> D
    D -->|"CQL pages"| C
    C -->|"onNext(Row), onError, onComplete"| B
    B --> F["Bounded processing/output"]
    G["Rate limit / max concurrency / deadline"] -.-> B
    H["Disk, SSTable, compaction, repair"] -.-> E
~~~

Các request CQL vẫn đi qua coordinator và replica. Driver có thể lấy một hoặc nhiều **page** để cung cấp dữ liệu, trong khi Subscriber yêu cầu các **row**. Không thể suy rằng `request(1)` tương ứng chính xác một request CQL qua mạng, một byte dữ liệu hoặc một read I/O trên disk.

Một truy vấn đọc một partition rộng vẫn có thể gây tốn tài nguyên ở server trước khi một row được gửi tới client.

## 3. Bốn giao diện Reactive Streams cần phân biệt

Reactive Streams for JVM dùng các giao diện thuộc package `org.reactivestreams`:

| Thành phần | Vai trò | Quy tắc thực hành |
|---|---|---|
| `Publisher<T>` | Nguồn có khả năng phát phần tử `T` | Publisher gửi dữ liệu cho mỗi subscription theo contract |
| `Subscriber<T>` | Bên nhận các tín hiệu từ nguồn | Phải nhận `onSubscribe` trước khi có `onNext` |
| `Subscription` | Quan hệ giữa một publisher và một subscriber | Có `request(long n)` và `cancel()` |
| `Processor<T,R>` | Vừa Subscriber vừa Publisher để biến đổi luồng | Không bắt buộc để đọc kết quả Cassandra |

Các tín hiệu quan trọng:

1. `onSubscribe(subscription)`: Subscriber nhận `Subscription`.
2. `subscription.request(n)`: Subscriber cho biết **số phần tử tối đa mong nhận thêm**; `n > 0`.
3. `onNext(item)`: Publisher phát phần tử trong phạm vi demand.
4. `onError(error)`: phát lỗi kết thúc luồng.
5. `onComplete()`: kết thúc bình thường.
6. `subscription.cancel()`: bên nhận không cần phần còn lại.

Sau `onError` hoặc `onComplete`, luồng đã kết thúc; không nên có các sự kiện `onNext` mới theo contract.

**`request(0)` và số âm không phải cách tạm dừng hợp lệ**. Để tạm dừng, đơn giản **chưa request tiếp**; để dừng hẳn, dùng `cancel()`.

### 3.1. Backpressure là quyền kiểm soát nhu cầu nhận phần tử

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher
    participant D as Driver / Coordinator
    S->>P: subscribe
    P-->>S: onSubscribe(subscription)
    S->>P: request(2)
    P->>D: Fetch nếu cần
    D-->>P: Một page kết quả
    P-->>S: onNext(row1)
    P-->>S: onNext(row2)
    Note over S,P: Không phát thêm row nếu không còn demand
    S->>P: request(1)
    P-->>S: onNext(row3)
    S->>P: cancel()
    Note over D,P: Cancellation không bảo đảm server đã hủy mọi thao tác đang chạy
~~~

Các thư viện như Reactor và RxJava triển khai thêm hàng trăm operator, nhưng **Reactive Streams là hợp đồng thấp hơn**; không phải mọi `Publisher` là Reactor `Flux` và không phải Reactor là thành phần mặc định của Cassandra server.

### 3.2. Reactive Streams không đồng nghĩa Java `Flow.Publisher`

Java 9 có `java.util.concurrent.Flow.Publisher`, còn các API trong nhiều Java Driver 4.x và Reactor dùng `org.reactivestreams.Publisher`. Chúng có khái niệm gần nhau nhưng **là các kiểu Java khác nhau**, không nên cast trực tiếp.

Nếu project dùng `Flow.Publisher`, cần adapter tương thích với version thư viện. Không tự giả định `executeReactive` trả kiểu `Flow.Publisher` chỉ vì project đang chạy JDK 17.

## 4. Điều kiện hỗ trợ theo Java Driver và stack ứng dụng

### 4.1. Kiểm tra API trước khi viết code

Khi tài liệu nhắc đến “reactive Cassandra”, trước tiên phải xác định **đúng driver**:

| Trường hợp | Điều cần kiểm tra |
|---|---|
| **Java Driver 4.x hỗ trợ Reactive API** | `CqlSession.executeReactive(...)`, reactive result type và package thực tế trong artifact đang dùng |
| **Java Driver 3.x** | Không mặc định có API/mẫu code Reactive Driver 4.x; dùng tài liệu theo major |
| **Bản phân phối/driver do nhà cung cấp quản lý** | Compatibility matrix, version và API được cấp phép/hỗ trợ |
| **Spring Data Cassandra reactive** | Tương thích giữa Spring Data, Spring Framework, driver và Reactor; repository abstraction không đồng nghĩa mọi driver version |
| **Ứng dụng chỉ dùng executeAsync** | `CompletionStage` là async API, chưa tự có demand-aware `Publisher` |
| **Ứng dụng chỉ dùng Java Flow API** | Kiểm tra adapter, không ép kiểu giữa hai Publisher interfaces |

Các ví dụ sau đặt giả định **driver 4.x cụ thể có `executeReactive`**. Nếu IDE/compiler báo không tồn tại method/type, hãy kiểm tra **artifact, version, import và compatibility matrix**, không tự thêm cast hoặc sao chép mã của major khác.

Một số bản phát hành/nhánh driver có thay đổi **nhà bảo trì, Maven coordinates và chính sách support**. Tên group/artifact phải lấy từ tài liệu của bản đang sử dụng; không khẳng định tất cả bản 4.x có cùng tọa độ dependency hoặc hỗ trợ JVM/Cassandra release như nhau.

### 4.2. Phân biệt dependency bắt buộc và tùy chọn

- **Driver core**: nơi cung cấp `CqlSession` và API thực thi tương ứng, nếu phiên bản có Reactive API.
- **Reactive Streams interfaces**: `Publisher`, `Subscriber`, `Subscription`. Kiểm tra dependencies được kéo theo từ phiên bản driver, không phải cài mọi thư viện “reactive” trên classpath.
- **Project Reactor** (`reactor-core`): **tùy chọn** để dùng `Flux`, `Mono`, `StepVerifier` (StepVerifier thực tế thuộc `reactor-test`).
- **RxJava**: lựa chọn khác nếu ứng dụng đã dùng; phải tương thích Reactive Streams adapters/versions.
- **Spring WebFlux/Spring Data**: framework bậc cao; không bắt buộc cho ví dụ driver native.

Tương thích phải xem **cả ba trục**: Java/JDK, Java Driver ↔ Cassandra server/protocol, và library/framework ↔ driver. Hệ thống dùng Cassandra 4.x **không tự quyết định** bạn phải dùng Java Driver 4.x nào.

### 4.3. Điều kiện vận hành ngoài dependency

Reactive API chỉ hữu ích khi:

- Query CQL có partition key và access pattern phù hợp.
- Có chính sách **page size, LIMIT, timeout, CL**.
- Có giới hạn **concurrency, retries và số subscription đồng thời**.
- Downstream xử lý không chặn vô hạn và không gom mọi row vào heap.
- Ứng dụng quan sát `onError` và cancellation, không dùng `subscribe()` fire-and-forget để làm mất lỗi.
- Session được tái sử dụng đúng vòng đời và kết nối theo local DC, auth, TLS.

Nếu điều kiện sau không đạt, reactive có thể **tăng** tải cluster do việc tạo ra nhiều subscription quá dễ dàng.

## 5. Đối chiếu synchronous, asynchronous và reactive API

| Thuộc tính | `execute` | `executeAsync` | `executeReactive` khi hỗ trợ |
|---|---|---|---|
| Giao diện | `ResultSet` | `CompletionStage<AsyncResultSet>` | `Publisher` của result rows |
| Cách tiêu thụ | `one()`/iterator | `currentPage()` và `fetchNextPage()` | Subscriber/request hoặc Reactor operator |
| Thread gọi có đợi request? | Có thể chặn khi gọi/nhận page | Không cần đợi qua callback | Dựa vào subscription và signals |
| Điều khiển nhu cầu | Consumer kéo row, sync paging | Tự quyết khi fetch page tiếp | Demand theo `request(n)` |
| Hạn chế heap | Duyệt streaming thay vì `all()` | Không gom current pages | Backpressure, tránh `collectList()` |
| Kiểm soát lỗi | Exception được ném | Future thất bại | `onError` |
| Dừng giữa chừng | Dừng iteration; ảnh hưởng đã fetch vẫn tồn tại | Bỏ/không fetch page sau; quản lý future | `cancel()` và quy tắc lifecycle |
| Một request CQL có rẻ hơn? | Không mặc định | Không mặc định | Không mặc định |
| Phù hợp | CLI/service nhỏ | Async workflow có số page rõ | Luồng nhiều phần tử với downstream demand |

**Reactive thường phù hợp khi downstream là reactive** (WebFlux, Reactor-based pipeline), nhưng không cần ép tất cả ứng dụng synchronous dùng Publisher. Quyết định nên dựa trên concurrency, observability, readability và chi phí vận hành.

## 6. Tạo bảng thực hành với partition key đúng

Giả sử cluster **lab**, datacenter `dc1` và đủ replica cho RF=3:

~~~cql
CREATE KEYSPACE telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_lab.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Câu query:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT ?;
~~~

Ở đây:

- Partition key = `(device_id, event_day)`: tất cả giá trị được bind giúp driver có cơ sở token-aware routing.
- Clustering key = `event_time`: hỗ trợ đọc mới nhất trước trong partition.
- `LIMIT` giới hạn **tổng số row** cho một query.
- `page size` giới hạn **mục tiêu số row** mỗi lần server trả/page.
- `LOCAL_QUORUM` chỉ chọn điều kiện replica responses, **không giúp Reactor xử lý row nhanh hơn**.

Thử với row mẫu:

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T08:30:00Z',
    24.6,
    'OK'
);

INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T08:31:00Z',
    24.8,
    'OK'
);
~~~

Ví dụ chỉ dùng để thực hành trên lab, không tạo lại keyspace production hoặc dùng tài khoản admin ở endpoint HTTP.

## 7. Native Reactive API: từ BoundStatement đến Publisher

### 7.1. Chuẩn bị statement một lần

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare(
    "SELECT event_time, reading_value, status " +
    "FROM telemetry_lab.readings_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT ?"
);

UUID deviceId = UUID.fromString(
    "11111111-1111-1111-1111-111111111111");
LocalDate eventDay = LocalDate.of(2026, 11, 21);

BoundStatement statement = prepared
    .bind(deviceId, eventDay, 100)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(25);

// Chỉ dùng khi phiên bản driver có Reactive API:
var publisher = session.executeReactive(statement);
~~~

Ví dụ dùng `var` (Java 10+). `session` là `CqlSession` đã khởi tạo với contact points, local DC, TLS/auth phù hợp và được tái sử dụng. Bản Java cũ có thể dùng kiểu kết quả cụ thể theo driver API.

`PreparedStatement` có vai trò **cố định CQL shape, bind typed values**; nó cũng giúp driver hiểu partition-key metadata khi có thể. Reactive API không thay thế bind parameter hoặc ngăn CQL injection nếu ứng dụng đã nối raw input vào query string.

### 7.2. Publisher chưa phải List

Kết quả reactive là **nguồn row** theo subscription, không phải `List<Row>` sẵn. Đừng giả định:

~~~java
// SAI về mặt khái niệm:
List<Row> allRows = session.executeReactive(statement);
~~~

Muốn tiêu thụ, cần **subscribe**, hoặc chuyển sang một thư viện hỗ trợ Reactive Streams như Reactor:

~~~java
// Minh họa khi project có reactor-core:
Flux.from(session.executeReactive(statement))
    .subscribe(row -> {
        System.out.println(row);
    });
~~~

Đoạn này chỉ là demo dòng dữ liệu. Trong service thực, `subscribe` thủ công không liên kết lỗi và lifecycle với HTTP caller; nên **trả publisher/Flux cho tầng gọi hoặc dùng subscriber có quản lý**.

### 7.3. Không gọi `executeReactive` là server push stream liên tục

Cassandra vẫn thực hiện **CQL truy vấn hữu hạn**, kết quả thường theo page. Publisher giúp client tiêu thụ row theo demand; server không phải một message broker tự phát các bản ghi mới mãi mãi.

Nếu cần **change stream** liên tục, phải xem CDC, event log hoặc architecture khác. Reactive `SELECT` không tự theo dõi mutation vừa thêm sau khi câu query ban đầu bắt đầu.

## 8. Dùng Subscriber để hiểu request(n) và cancel()

Để thấy rõ cơ chế demand, có thể dùng một `Subscriber` không phụ thuộc Reactor. Đoạn ví dụ **tập trung vào lifecycle**; dùng `Object` để không buộc cú pháp chi tiết của kiểu row wrapper thay đổi giữa các bản driver.

~~~java
import org.reactivestreams.Publisher;
import org.reactivestreams.Subscriber;
import org.reactivestreams.Subscription;

import java.util.concurrent.atomic.AtomicBoolean;

public final class DemandSubscriber implements Subscriber<Object> {
    private Subscription subscription;
    private final AtomicBoolean stopped = new AtomicBoolean();
    private long seen;

    @Override
    public void onSubscribe(Subscription s) {
        this.subscription = s;
        s.request(1); // Chỉ yêu cầu một phần tử ban đầu.
    }

    @Override
    public void onNext(Object row) {
        if (stopped.get()) {
            return;
        }

        try {
            processRow(row);
            seen++;
        } catch (RuntimeException error) {
            stopped.set(true);
            subscription.cancel();
            reportFailure(error);
            return;
        }

        if (seen >= 100) {
            stopped.set(true);
            subscription.cancel();
        } else {
            subscription.request(1);
        }
    }

    @Override
    public void onError(Throwable t) {
        stopped.set(true);
        reportFailure(t);
    }

    @Override
    public void onComplete() {
        stopped.set(true);
        reportSuccess(seen);
    }

    private void processRow(Object value) {
        // Demo: logic ngắn, không block thread tín hiệu.
        // Code thật nên nhận đúng kiểu ReactiveRow của driver.
    }

    private void reportFailure(Throwable error) {
        System.err.println(error.getClass().getSimpleName());
    }

    private void reportSuccess(long count) {
        System.out.println("completed rows=" + count);
    }
}
~~~

Đăng ký subscriber với publisher driver khi kiểu Publisher và generic parameter tương thích:

~~~java
// Tại chỗ đã có BoundStatement và CqlSession.
// Subscriber<Object> nhận phần tử như Object để minh họa demand.
session.executeReactive(statement)
    .subscribe(new DemandSubscriber());
~~~

**Cảnh báo production:** code này chỉ minh họa contract `request(1)`, không phải implementation an toàn đầy đủ cho concurrency, cancellation race, metrics hay downstream error propagation. Khi phải xử lý phức tạp hoặc tốn thời gian, nên dùng Reactor operator/executor có giới hạn và tránh block driver I/O threads.

### 8.1. Chọn demand một phần tử có phải tối ưu không?

Không nhất thiết. `request(1)` có thể tạo overhead signals/callbacks nhiều hơn một mức demand vừa phải; `request(Long.MAX_VALUE)` lại không có giới hạn theo nhu cầu, dễ gây rủi ro nếu downstream không thể xử lý kịp.

Điểm đúng là **demand phù hợp năng lực xử lý**. Trong Reactor, operator có thể quản lý request/prefetch gián tiếp; không cần tự viết Subscriber trong hầu hết ứng dụng.

### 8.2. Không gọi `request()` khi subscription đã bị hủy

Sau `cancel()`, không kỳ vọng tiếp tục nhận dữ liệu. Một số tín hiệu đã nằm trong đường truyền/event queue có thể có race trong implementation, vì vậy cần thiết kế xử lý trạng thái và tránh side effect không idempotent.

Không sử dụng cancellation như một **transaction rollback**: Cassandra không rút lại các mutations đã chạy chỉ vì Java Subscriber không còn nhận row.

## 9. Reactor `Flux`: ánh xạ row sang DTO

### 9.1. Ví dụ repository reactive

Một cách triển khai Java Driver 4.x có Reactive API và Reactor:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import reactor.core.publisher.Flux;

import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

public final class ReactiveReadingRepository {
    private final CqlSession session;
    private final PreparedStatement query;

    public ReactiveReadingRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.query = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM telemetry_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT ?"
        );
    }

    // Giả định JDK hỗ trợ record, có thể thay bằng DTO class.
    public record ReadingDto(
        Instant eventTime, Double readingValue, String status) {}

    public Flux<ReadingDto> find(UUID deviceId,
                                 LocalDate day,
                                 int limit) {
        if (limit < 1 || limit > 200) {
            return Flux.error(
                new IllegalArgumentException("Invalid limit"));
        }

        // defer bảo đảm việc tạo statement/Publisher ở mỗi subscription
        // nằm trong lifecycle do subscriber thực sự yêu cầu.
        return Flux.defer(() -> {
            BoundStatement stmt = query
                .bind(deviceId, day, limit)
                .setPageSize(Math.min(limit, 50))
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            return Flux.from(session.executeReactive(stmt))
                .map(row -> new ReadingDto(
                    row.getInstant("event_time"),
                    row.isNull("reading_value")
                        ? null : row.getDouble("reading_value"),
                    row.getString("status")));
        });
    }
}
~~~

Mẫu này nhấn mạnh:

- CQL/statement được prepare **một lần** trong repository.
- `Flux.defer` chỉ tạo publisher khi có subscription.
- Mỗi subscription có thể làm một **request CQL thực tế**; đừng dùng nhiều subscription nếu tưởng là cache cùng một kết quả.
- Mapper chỉ đọc các cột được SELECT và xử lý `null` cho `double` nếu cần.
- `LIMIT` và page size được giới hạn rõ; không suy rằng `Flux` tự chặn truy vấn nguồn rộng.
- `LOCAL_QUORUM` là chính sách dữ liệu, không phải backpressure.
- Không có `block()` hay `collectList()` trong đường trả dữ liệu.

**Ghi chú phiên bản:** mã giả định reactive row mà phiên bản driver cung cấp có các getter CQL kiểu `getInstant`/`getDouble`/`getString`. Hãy đối chiếu chữ ký `ReactiveResultSet` và kiểu phần tử thực tế trong Javadoc của artifact trước khi copy vào code production. Nếu reactive row là wrapper theo version, dùng API row/getter đúng với version đó.

### 9.2. Giữ Flux ở ranh giới API

Với Spring WebFlux (nếu toàn bộ stack có hỗ trợ), tầng controller có thể trả:

~~~java
// Đoạn minh họa: không đưa full imports/cấu hình Spring.
@GetMapping("/devices/{id}/readings")
public Flux<ReadingDto> readings(
        @PathVariable UUID id,
        @RequestParam LocalDate day) {
    return repository.find(id, day, 100);
}
~~~

Trong project có kiểu DTO nested như `ReactiveReadingRepository.ReadingDto`, phải import/định danh đúng. Đây là minh họa kiến trúc, không phải controller copy-paste hoàn chỉnh.

**Điều quan trọng:** ranh giới HTTP không phải lúc nào cũng phản ánh demand chính xác xuống Cassandra; buffering/serialization, proxy và client connection ảnh hưởng. Cần đo memory và backpressure **end-to-end**, không chỉ thấy return type `Flux` rồi coi toàn hệ thống không thể quá tải.

## 10. Backpressure khác page size, LIMIT và quota server

### 10.1. Năm giới hạn độc lập

| Cơ chế | Kiểm soát gì? | Không bảo đảm điều gì? |
|---|---|---|
| `request(n)` | Demand tối đa thêm `n` phần tử từ Publisher | Không tương đương `n` request CQL hoặc `n` byte |
| `setPageSize(k)` | Mục tiêu số row/page | Không phải hạn mức bytes/RAM tuyệt đối |
| CQL `LIMIT m` | Số row tối đa trong kết quả | Không hạn chế số SSTable/tombstone server phải quét |
| Max active subscriptions | Số query stream cùng hoạt động | Không giới hạn bytes/query nếu row rất rộng |
| Rate/bytes budget | QPS, rows/s hoặc bytes/s của job/service | Không sửa truy vấn thiếu partition key |

Ví dụ:

~~~text
Statement: LIMIT 1000, pageSize = 100
Subscriber: request(5)

Có nghĩa:
  - CQL có thể trả tối đa 1000 row.
  - Driver có thể nhận kết quả theo page mục tiêu 100 row.
  - Publisher chỉ nên phát tối đa 5 row theo demand hiện có.
  - Server có thể đã xử lý/driver giữ phần dữ liệu còn lại của page.
~~~

**Backpressure không phải quota tài nguyên Cassandra**. Nếu partition chứa nhiều tombstone, server có thể phải quét nhiều entry trước khi trả một row. Một row lớn cũng có thể tiêu thụ nhiều bytes dù `request(1)`.

### 10.2. Reactor `limitRate` không phải CQL LIMIT

~~~java
Flux.from(session.executeReactive(statement))
    .limitRate(32)
    .doOnNext(row -> consume(row))
    .subscribe();
~~~

`limitRate(32)` điều chỉnh cách Reactor request upstream, **không sửa CQL thành `LIMIT 32`**, không ép page size bằng 32 và không tự chặn tổng row của query. `consume` là hàm xử lý minh họa.

### 10.3. Tránh `onBackpressureBuffer` không giới hạn

~~~java
// ANTI-PATTERN nếu không hiểu rõ buffer và tốc độ downstream.
Flux.from(session.executeReactive(statement))
    .onBackpressureBuffer()
    .subscribe(this::slowlyConsume);
~~~

Buffer không giới hạn có thể gom dữ liệu trong heap khi downstream chậm. Nếu thật sự cần buffer, phải quy định **số phần tử/bytes, overflow policy và metrics**, không chỉ chọn operator có chữ “backpressure”.

### 10.4. Ví dụ tính bộ nhớ

Số liệu **giả định**:

~~~text
Average decoded row payload = 8 KiB
Page size target           = 500 rows
Concurrent subscriptions   = 100

Payload xấp xỉ:
8 KiB × 500 × 100 = 400000 KiB ≈ 390,6 MiB

Chưa tính:
  driver buffers, object overhead, DTO,
  queue downstream, network buffers, GC headroom.
~~~

Vì vậy cần giới hạn **concurrency và row size**; `request(n)` không phải chứng chỉ “không bao giờ OOM”.

## 11. Paging reactive và ngữ nghĩa của kết quả theo thời gian

### 11.1. Khác AsyncResultSet

Với async API, bạn thường chủ động xử lý `AsyncResultSet.currentPage()` rồi `fetchNextPage()`. Với Reactive API, Publisher/driver chịu trách nhiệm cung cấp row theo **subscriber demand** và quy tắc paging của phiên bản tương ứng.

Không tự viết `fetchNextPage()` trên `ReactiveRow` nếu phiên bản không có contract ấy. Sync, async và reactive đều dùng CQL paging nhưng **interface tiêu thụ khác nhau**.

### 11.2. Page có thể không đủ mục tiêu row

- Server có giới hạn nội bộ theo kích thước response.
- Row lớn làm page có thể ít hơn số hàng mục tiêu.
- Tombstone và read path tăng chi phí trước khi page có row.
- Page kế tiếp vẫn chịu latency của network/coordinator/replica.
- `LOCAL_QUORUM` và topology vẫn ảnh hưởng từng request thực thi.

### 11.3. Time to first row khác total consumption time

~~~text
T0: subscriber subscribe()
T1: first onNext(row)
T2: row cuối của page thứ nhất
T3: last onNext(row)
T4: onComplete()

Time to first row:   T1 - T0
Total consume time:  T4 - T0
~~~

Nếu stream 10.000 row có first-row latency tốt nhưng total time kéo dài, không thể kết luận query đã phục vụ nhanh toàn bộ dữ liệu. Cần đo cả số page, duration tổng và tốc độ downstream.

### 11.4. Paging không phải snapshot giao dịch

Giữa các page, mutation mới, DELETE, TTL và repair có thể thay đổi dữ liệu đọc. `Publisher` không tạo snapshot ACID toàn bảng. Với export/cutover đòi điểm phục hồi ổn định, cần thêm snapshot/CDC/event log hoặc reconciliation theo yêu cầu.

## 12. Cancellation: ngừng nhận dữ liệu không hoàn tác CQL

### 12.1. Khi HTTP client ngắt kết nối

Tầng reactive có thể `cancel()` subscription. Hệ quả thường mong muốn:

- Subscriber không nhận thêm row không cần thiết.
- Driver có thể tránh fetch những page tiếp theo khi không còn demand.
- Những request **đã được gửi** có thể vẫn đang chạy tại coordinator/replica.
- Mutation đã áp dụng không tự rollback.
- Event đã được gửi downstream không bị thu hồi.

**Không khẳng định `cancel()` hủy ngay mọi tác vụ server**. Cần xem khả năng cancellation thực tế của driver/server trong phiên bản đang dùng.

### 12.2. `take(n)` không thay CQL LIMIT

~~~java
Flux.from(session.executeReactive(statement))
    .take(20)
    .doFinally(signal -> metrics.recordTermination(signal.toString()));
~~~

`take(20)` có thể hủy phần upstream sau đủ 20 row. Nhưng hãy đặt **`LIMIT 20`** tại CQL nếu API chỉ cần 20 row để giảm chi phí nguồn. `metrics` trong ví dụ là thành phần ứng dụng giả định.

### 12.3. Hủy một reactive write

Khi ứng dụng hủy Publisher chứa một mutation `INSERT` hoặc `UPDATE` vì timeout:

- Không có transaction rollback tự động.
- Có thể một số replica đã apply mà Java chưa nhận ACK.
- Retry cần đánh giá idempotency và operation ID.
- Counter, LWT, TTL và DELETE có quy tắc riêng.

Đừng đánh dấu write là “chắc chắn chưa chạy” chỉ vì downstream cancel.

## 13. Cold Publisher, nhiều subscription và retry

### 13.1. Một lần subscribe có thể là một lần CQL execution

Với nhiều Reactive API, Publisher là **cold** hoặc bắt đầu việc thực thi khi subscribe. Hợp đồng cụ thể phải xác nhận theo driver version. Vì vậy:

~~~java
Flux<ReadingDto> flux = repository.find(deviceId, day, 100);

flux.subscribe(this::sendToAudit);
flux.subscribe(this::sendToHttpClient);
~~~

**Có thể** tạo hai request CQL và hai lượt paging, không phải tự động chia sẻ một kết quả. Nếu cần multicast/cache, phải thiết kế memory/cancellation/retention và privacy; đừng cache vô hạn dữ liệu tenant.

### 13.2. `retry` và `repeat` có thể resubscribe

~~~java
// ANTI-PATTERN: thử lại rất nhiều lần mà không đánh giá lỗi.
repository.find(deviceId, day, 100)
    .retry(100)
    .subscribe();
~~~

Ở tầng Reactor, retry/repeat có thể **subscribe lại toàn Publisher**, kích hoạt query mới. Nếu stream đã gửi một phần row rồi lỗi, retry có thể **phát lại row đã gửi**. Điều này nguy hiểm cho HTTP streaming hoặc side-effecting sink.

Phải phân biệt retry của **driver request** với retry của **Reactor pipeline** và retry của gateway/client upstream.

### 13.3. Hai lần subscribe không nhất thiết thấy cùng dữ liệu

Dữ liệu Cassandra có thể thay đổi do INSERT, DELETE, TTL, consistency và replication; cold Publisher không phải một bản sao lưu snapshot bất biến. Nếu cần tính nhất quán point-in-time, phải thiết kế cơ chế bên ngoài `Publisher`.

## 14. Concurrency: hàng nghìn Publisher nhỏ vẫn có thể làm quá tải cluster

### 14.1. Anti-pattern fan-out không giới hạn

~~~java
for (UUID deviceId : deviceIds) {
    repository.find(deviceId, day, 100)
        .subscribe(row -> sendRow(row));
}
~~~

Mỗi subscription có request/page buffer riêng. Token-aware routing giúp chọn coordinator khi đủ partition key, nhưng **không giới hạn tổng in-flight hoặc hot partition**.

### 14.2. Bounded fan-out với Reactor

~~~java
import reactor.core.publisher.Flux;

int maxConcurrentPartitions = 8;

Flux<ReactiveReadingRepository.ReadingDto> rows =
    Flux.fromIterable(deviceIds)
        .flatMap(
            deviceId -> repository.find(deviceId, day, 50),
            maxConcurrentPartitions
        );
~~~

`flatMap(..., 8)` giới hạn số inner Publishers hoạt động đồng thời **trong pipeline này**. Nếu có 100 HTTP requests chạy cùng lúc, tổng số inner subscriptions **có thể tới gần 800**. Cần admission control và rate/bytes budget **toàn service/pod/cluster**, không chỉ giới hạn một Flux.

Nếu cần bảo toàn thứ tự theo phần tử đầu vào, cân nhắc `concatMap` hoặc operator có ordering phù hợp, chấp nhận đánh đổi throughput.

### 14.3. Giới hạn tải phải theo hệ thống

- Rate limiter theo tenant/query template.
- Semaphore/in-flight budget có phạm vi chia sẻ.
- Deadline end-to-end.
- Backpressure tới HTTP sink/worker queue.
- Kiểm soát row bytes, partition width và page size.
- Load shedding/circuit breaker khi Cassandra quá tải.
- Theo dõi node xấu nhất, không chỉ average cluster QPS.

**Reactive không tự biết Cassandra còn bao nhiêu IOPS/CPU**. Nhiều subscriptions cùng chạm một partition vẫn gây hotspot ở tập replica đó.

## 15. Không block callback/thread khi xử lý row

### 15.1. Anti-pattern: gọi blocking API trong `map`

~~~java
// ANTI-PATTERN: I/O blocking có thể giữ event-loop/callback thread.
Flux.from(session.executeReactive(statement))
    .map(row -> {
        writeToSlowExternalApi(row);
        return row;
    });
~~~

Nếu `writeToSlowExternalApi` là HTTP/JDBC/file I/O đồng bộ, việc chạy trực tiếp trong callback có thể làm trễ tín hiệu, gây timeouts hoặc starvation ở tầng client. **Reactive chỉ nonblocking nếu các đoạn xử lý liên quan cũng được thiết kế nonblocking hoặc được cô lập đúng cách.**

### 15.2. Dùng scheduler riêng khi bất khả kháng

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Flux.from(session.executeReactive(statement))
    .flatMap(
        row -> Mono.fromCallable(() -> blockingTransform(row))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

Đây là ví dụ operator, `blockingTransform` phải được định nghĩa. `boundedElastic` có cơ chế giới hạn thread/queue, nhưng **không bảo đảm queue không bao giờ quá lớn**. Giới hạn concurrency (ở đây 8) và theo dõi thời gian thực thi/dung lượng vẫn cần thiết. Nếu có nonblocking client tương ứng, thường nên ưu tiên.

### 15.3. Dùng `block()` có thể đánh mất lợi ích reactive

~~~java
// ANTI-PATTERN trong WebFlux event-loop:
ReadingDto first = repository.find(deviceId, day, 100)
    .next()
    .block();
~~~

`block()` biến việc chờ kết quả thành đồng bộ và có thể chặn event loop. Nếu service vốn synchronous và không cần stream, dùng `execute()` hoặc `executeAsync()` theo thiết kế có thể đơn giản hơn việc “bọc Flux rồi block”.

Không dùng `Thread.sleep()` trong `onNext` để điều tiết tốc độ; hãy sử dụng demand, rate limiter hoặc scheduler/backpressure policy phù hợp.

## 16. Xử lý lỗi từ Publisher một cách tường minh

### 16.1. `onError` khác kết quả rỗng

Một SELECT trả về **0 row** sẽ hoàn thành bình thường; ngược lại, lỗi mạng, `DriverTimeoutException` hoặc `AllNodesFailedException` thường đi theo **`onError`** (hoặc wrapper tương ứng của framework).

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.DriverTimeoutException;

Flux<ReadingDto> observed =
    repository.find(deviceId, day, 100)
        .doOnError(error -> {
            if (error instanceof DriverTimeoutException) {
                metrics.increment("driver_timeout");
            } else if (error instanceof AllNodesFailedException) {
                metrics.increment("all_nodes_failed");
            } else {
                metrics.increment("other_failure");
            }
        });
~~~

`metrics` là thành phần giả định của ứng dụng. Với `AllNodesFailedException`, `getAllErrors()` có thể hỗ trợ chẩn đoán **coordinator candidates** và causes; không cho biết toàn bộ replica đã down.

### 16.2. Tránh biến timeout thành “không có dữ liệu”

~~~java
// ANTI-PATTERN: nuốt mọi lỗi Cassandra:
repository.find(deviceId, day, 100)
    .onErrorResume(error -> Flux.empty());
~~~

Nếu API trả `200 OK []` khi thực ra query timeout, caller có thể hiểu nhầm không có sự kiện. Hãy phân loại **business empty** và **service failure** bằng status/error contract rõ ràng.

### 16.3. Retry Reactor có chọn lọc và giới hạn

~~~java
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import java.time.Duration;
import reactor.util.retry.Retry;

Flux<ReadingDto> retried =
    repository.find(deviceId, day, 100)
        .retryWhen(
            Retry.backoff(1, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(500))
                .jitter(0.5)
                .filter(e -> e instanceof DriverTimeoutException)
        );
~~~

**Đây chỉ là ví dụ cú pháp Reactor, không phải policy khuyến nghị retry mọi DriverTimeout**. Cần kiểm tra SELECT idempotent, deadline còn đủ, cluster không overload và số attempt đã tính cả driver/gateway. Nếu lỗi xảy ra sau khi đã phát một phần row, **resubscribe có thể phát trùng phần đã đọc**; với HTTP streaming, điều đó có thể vi phạm hợp đồng response.

### 16.4. Lỗi đồng bộ trước lúc subscribe

Đoạn mã tạo `PreparedStatement`/`BoundStatement` có thể gây lỗi validation hoặc codec trước khi Publisher được subscribe. `Flux.defer` giúp chuyển một số bước dựng Publisher vào lúc subscription, nhưng **không làm CQL invalid trở thành lỗi có thể retry**.

Đối với kiểm thử, phải có cả trường hợp:

- API trả `Flux.error` khi input limit không hợp lệ.
- Server/driver trả lỗi `onError`.
- Publisher phát 0 row rồi `onComplete`.
- Mapper ném exception khi CQL column type không khớp.
- Downstream cancel giữa stream.

## 17. Timeout, CL và tính đúng khi reactive query

### 17.1. Phân biệt ba loại deadline

| Đồng hồ | Điều gì được giới hạn | Nhầm lẫn cần tránh |
|---|---|---|
| Driver request timeout | Request/operation driver theo contract version | Không mặc định là deadline tổng của mọi page/row |
| Reactor `timeout(Duration)` | Khoảng chờ tín hiệu theo operator | Không nhất thiết là tổng wall-clock duration của toàn stream |
| HTTP/gRPC deadline | Thời gian phục vụ toàn request | Không có nghĩa server tự rollback công việc đã bắt đầu |

Ví dụ:

~~~java
repository.find(deviceId, day, 100)
    .timeout(Duration.ofSeconds(5));
~~~

Operator timeout có thể cancel upstream khi không thấy tín hiệu trong khoảng quy định. Nhưng việc cancel ở Java **không bảo đảm Cassandra đã dừng request đang thực thi**.

### 17.2. LOCAL_QUORUM không thay đổi do Flux

Với keyspace RF=3 trong `dc1`, `LOCAL_QUORUM` cần quorum hai replica theo quy tắc thao tác. Chuyển từ `executeAsync` sang `executeReactive` **không đổi bảo đảm consistency** hoặc biến ba bản sao thành một.

Nếu replica chậm do compaction/repair, stream reactive vẫn bị ảnh hưởng latency và errors. Khi gặp timeout:

- Xác minh driver deadline và query shape.
- Kiểm tra RF/CL và node state.
- Đối chiếu `tpstats`, disk, SSTable/tombstone read path.
- Giảm fan-out/reactive subscriptions nếu quá tải.

### 17.3. Write và cancellation: outcome có thể không rõ

Nếu dùng reactive write rồi timeout/cancel:

- Một số replica có thể đã áp dụng mutation.
- `INSERT` cùng primary key/value có thể gần idempotent nhưng timestamp, TTL và concurrent update cần xét.
- Counter increment có thể bị cộng trùng nếu retry.
- LWT `IF NOT EXISTS` cần xác minh operation identity/invariant khi lần đầu không rõ outcome.
- `DELETE` với timestamp mới có thể che dữ liệu hợp lệ được ghi giữa các attempts.
- Side effects ngoài Cassandra cần deduplication/outbox hoặc cơ chế phù hợp.

Reactive Streams **không có transaction exactly-once**. Retry phải đánh giá theo nghiệp vụ chứ không chỉ theo exception class.

## 18. Quan sát reactive pipeline cùng tài nguyên Cassandra

### 18.1. Dashboard nên có ba lớp

| Lớp | Metric nên đo | Nguy cơ được phát hiện |
|---|---|---|
| **HTTP/Reactive** | Subscriber count, cancellation, time to first row, total duration, onError rate | Client quá chậm, disconnect, stream quá dài |
| **Driver** | Request QPS, p95/p99, timeout, retries, coordinator, pool/in-flight | Lỗi mạng, retry storm, coordinator pressure |
| **Cluster/node** | Disk free/latency, compaction pending, SSTables per read, flush, repair, streaming, CPU/GC | Replica đang quá tải |

Ngoài ra nên có `rows emitted` và `bytes emitted` theo query template, số stream active và số stream đã hoàn tất. Không dùng raw tenant/device ID hoặc routing key làm label high-cardinality.

### 18.2. Các lệnh kiểm tra trên lab hoặc vận hành có quyền

~~~bash
# Trạng thái node/DC/rack.
nodetool status

# Pending/active/dropped theo thread pool.
nodetool tpstats

# Backlog và tiến độ compaction.
nodetool compactionstats

# Streaming trong bootstrap/repair/rebuild.
nodetool netstats

# Table-level latency/dung lượng/SSTables.
nodetool tablestats telemetry_lab.readings_by_device_day
~~~

`netstats` không hiển thị mọi CQL native transport traffic. `status` có node `UN` **không chứng minh** latency/queues đang khỏe. Output/cú pháp của `nodetool` thay đổi theo release, cần kiểm tra help của bản đang chạy.

### 18.3. Theo dõi rate và memory bằng một bảng giả định

| Thời điểm | Active streams | Page size | API p99 | Worst-node disk free | Kết luận sơ bộ |
|---|---:|---:|---:|---:|---|
| 09:00 | 20 | 100 | 90 ms | 38% | Baseline |
| 09:15 | 100 | 500 | 380 ms | 33% | Tải đã tăng |
| 09:30 | 400 | 500 | 1.200 ms | 26% | Cần giảm concurrency, điều tra |
| 09:35 | 50 | 100 | 220 ms | 26% | Sau giảm tải, vẫn cần quan sát backlog |

**Các số là giả định**, không phải benchmark Cassandra. Không kết luận nguyên nhân chỉ từ bảng này: cần xem QPS, row bytes, compaction, GC và network cùng thời điểm.

### 18.4. Đo đúng phạm vi latency

Với stream dài, cần phân biệt:

- **Time to first row**.
- **Time to last row / onComplete**.
- **Số page/bytes đã nhận**.
- **Thời gian chờ downstream** và khi upstream bị demand=0.
- **Timeout rate** và errors, không chỉ latency của success.
- **Cancellation rate** và nguyên nhân client ngắt kết nối.

Không lấy trung bình p99 từng node làm p99 toàn cluster; percentile cần gộp histogram/phân bố đúng.

## 19. Kiểm thử tích hợp Reactive API

### 19.1. Một kiểm thử cơ bản với StepVerifier

Nếu project có Reactor Test (`reactor-test`) và cluster lab:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(repository.find(deviceId, day, 2))
    .assertNext(row -> {
        if (row.eventTime() == null) {
            throw new AssertionError("eventTime was null");
        }
    })
    .thenCancel()
    .verify();
~~~

Đoạn test yêu cầu trong lab có ít nhất một row khớp và phiên bản Java DTO hỗ trợ `record`. `thenCancel` kiểm tra luồng có thể hủy; nó **không chứng minh server luôn hủy ngay một query đã gửi**.

Đối với query có số row cố định đã seed, có thể dùng `expectNextCount` và `verifyComplete` để kiểm tra toàn bộ, nhưng cần kiểm soát dataset/CL để tránh test flaky.

### 19.2. Kiểm thử demand bằng Subscriber tùy chỉnh

Một Publisher có thể được test bằng Subscriber chủ động:

1. Subscribe nhưng chưa request dữ liệu.
2. Gọi `request(1)`, quan sát không nhận quá demand.
3. Sau khi xử lý row đầu, request thêm một số nhỏ.
4. Gọi `cancel()`, kiểm tra không có hành vi downstream không mong muốn.
5. Thử lỗi input/timeout và xác minh `onError` được phân loại.
6. Xác minh `onComplete` không bị lẫn với một stream đã lỗi.

Điều kiện race/concurrency cần dùng công cụ test có virtual time hoặc synchronization phù hợp, không dựa vào `Thread.sleep` để “đoán” kết quả async.

### 19.3. Các test bắt buộc về correctness

| Bài test | Điều kiểm tra |
|---|---|
| Query trả 0 row | `onComplete` không có item, không phải `onError` |
| Limit hợp lệ/bất hợp lệ | Server-side LIMIT và Java validation |
| Row có nullable field | DTO giữ null đúng, không tự biến thành 0 |
| Một partition lớn | Page size, heap, total consume time, cancellation |
| Client cancel sau 5 row | Không phát side effect thêm ở downstream |
| Subscriber thứ hai | Không giả định dùng chung một CQL execution |
| Retry sau 2 row rồi lỗi | Không lặp side effect hoặc row IDs |
| Network/driver timeout | `onError`, không biến thành kết quả rỗng |
| 100 subscription đồng thời | In-flight/concurrency/admission control vẫn giới hạn |
| Schema/driver upgrade | Method/type signatures và codecs tương thích |
| CL/local DC | Kết quả/timeout phù hợp RF/replica availability |
| Slow downstream | Không có queue/heap tăng không giới hạn |

**Không fault-inject trực tiếp trên production.** Dùng test cluster cô lập và dữ liệu giả, cùng các ngưỡng tốc độ thấp để test không trở thành stress test ngoài kế hoạch.

## 20. Lựa chọn kiến trúc: Reactive API hay async paging?

Chọn theo yêu cầu thực tế:

| Nhu cầu | Lựa chọn thường thích hợp | Điểm kiểm soát |
|---|---|---|
| Trả tối đa 10 row cho API sync | `execute` hoặc `executeAsync` | CQL LIMIT, timeout |
| Workflow async xử lý từng page rõ ràng | `executeAsync`/`fetchNextPage()` | Chủ động fetch, backpressure ở application |
| HTTP reactive streaming các row | `executeReactive` + Reactor/WebFlux nếu tương thích | Demand, cancellation, toàn bộ pipeline |
| Backfill lớn theo token ranges | Async/reactive có throttle hoặc công cụ import phù hợp | Bytes/s, partition routing, checkpoint |
| Đồng bộ hóa state một lần | Prepared sync/async hoặc reactive theo stack | Idempotency/CL, không bắt buộc reactive |
| Thay đổi liên tục từ DB | CDC/event broker được thiết kế | `executeReactive(SELECT)` không tự là change feed |
| Legacy driver không có Reactive API | Giữ async có kiểm soát hoặc nâng version có kế hoạch | Driver/JDK/server compatibility |

**Đừng xây một bridge `Flux.create(sink -> session.execute(...))` với synchronous blocking JDBC-style logic rồi gọi là reactive Cassandra.** Bridge có thể dùng trong một số hệ thống chuyển tiếp, nhưng phải quản lý scheduler, demand, cancellation và blocking threads cẩn thận.

### 20.1. Nếu driver hiện tại không có `executeReactive`

Phương án khả thi:

- Dùng `executeAsync` và một vòng paging có **bounded demand** được tự triển khai và test.
- Nâng driver trong một kế hoạch có compatibility matrix, regression tests và rollback.
- Sử dụng abstraction/framework reactive được hỗ trợ chính thức bởi stack.
- Chọn sync code nếu workload nhỏ và đơn giản, tránh bridge phức tạp không cần thiết.

Không tự gọi `executeReactive` trên bản 3.x chỉ vì documentation của Driver 4.x có method đó.

### 20.2. Nếu đã dùng Spring Data Cassandra reactive

Kiểm tra stack:

- Spring Data Cassandra version có hỗ trợ driver/server đang sử dụng không?
- Reactive repository thực sự dùng driver/API nào phía dưới?
- Consistency level, paging, tracing, retry và timeout được cấu hình ở layer nào?
- Bộ chuyển mã `UDT/collection` và mapping có khác native driver không?
- HTTP response backpressure có truyền xuống repository đúng cách không?

Spring abstraction có thể hữu ích, nhưng **không tự thay thế việc hiểu Publisher contract** hay data model Cassandra.

## 21. Runbook A — Code không tìm thấy `executeReactive`

**Tình huống:** Một module Java được nâng từ Driver 3.x lên 4.x; ví dụ reactive không compile, hoặc ở runtime báo `NoSuchMethodError` / `ClassNotFoundException`.

### Bước 1 — Xác định đúng artifact và package

Ghi nhận driver major/minor/patch, nhà phát hành, tọa độ dependency, JDK và các library reactive được khai báo. Không kết luận “Cassandra không hỗ trợ reactive” chỉ vì thiếu một method trong classpath của **một phiên bản driver cụ thể**.

### Bước 2 — Kiểm tra classpath thực tế

Xem có nhiều driver versions cùng xuất hiện qua dependency transitives không; tìm dấu hiệu `NoSuchMethodError` khi compile thành công nhưng runtime tải JAR cũ. Việc đọc dependency graph là công việc build/CI của project, **không cần sửa classpath ngẫu nhiên trong production**.

### Bước 3 — Đối chiếu API thực tế

Dùng IDE/Javadoc của đúng artifact để xác minh:

- `CqlSession` có `executeReactive` không?
- Giá trị trả về có thực thi `org.reactivestreams.Publisher` không?
- Kiểu row/getters là gì?
- Driver yêu cầu các dependencies nào?
- Java/JDK, CQL protocol và Cassandra server version được hỗ trợ ra sao?

Đừng dùng code `java.util.concurrent.Flow.Publisher` để ép kiểu sang `org.reactivestreams.Publisher` nếu chưa có adapter.

### Bước 4 — Kiểm tra Reactor integration

Nếu driver có Publisher nhưng code không thấy `Flux` hoặc `StepVerifier`, xác minh `reactor-core` / `reactor-test` đã được thêm ở module cần thiết, phiên bản tương thích và không có classpath conflict. **Reactor không phải chính driver**; một lỗi import Reactor không chứng minh native Reactive API không tồn tại.

### Bước 5 — Đưa ra quyết định

- Nếu version hiện tại hỗ trợ: sửa imports/dependencies và test compile/integration.
- Nếu version không hỗ trợ: tiếp tục `executeAsync` với paging và backpressure rõ, hoặc lập kế hoạch upgrade theo compatibility matrix.
- Nếu có runtime binary mismatch: điều chỉnh dependency resolution/release artifact, không bypass kiểm thử.
- Ghi version pairs và quyết định để tránh tái diễn.

### Bước 6 — Smoke test trước rollout

Thực thi SELECT theo partition key ở lab, subscribe một lần, kiểm tra 0/1/n rows, lỗi và cancellation. Sau đó đo QPS, p99 và heap với tải vừa phải. Không triển khai production chỉ vì ví dụ compile được.

## 22. Runbook B — Reactive service tăng heap và latency

**Tình huống:** Sau khi chuyển sang Reactor, application heap/GC tăng, có khoảng 500 active streams, Cassandra `ReadStage Pending` và p99 tăng; code có `collectList()` và `flatMap` không giới hạn.

### Bước 1 — Khoanh vùng

Ghi query template, số active subscriptions, concurrency HTTP, page size, LIMIT, row/response bytes, timeout và thời điểm deploy. Không log raw tenant/partition IDs.

### Bước 2 — Xác định buffer

Tìm:

~~~text
collectList()
onBackpressureBuffer() (không có cap)
flatMap(...) (không giới hạn concurrency)
request(Long.MAX_VALUE) vào consumer chậm
block() / Thread.sleep() / synchronous I/O trong callbacks
hai subscribe() cho cùng Publisher khi không chủ ý
~~~

Không phải mọi lần dùng các API trên đều sai, nhưng mỗi cái cần được kiểm tra trong workload và memory budget thực tế.

### Bước 3 — Đo Cassandra

- `nodetool tpstats`: Active/Pending/Dropped có tăng không?
- `nodetool compactionstats`: backlog có tranh disk?
- Disk free, read latency, GC, network và row sizes.
- Query có đủ partition key; có nhiều tombstone/SSTable không?
- `nodetool netstats`: streaming khi bootstrap/repair có tranh I/O không?

### Bước 4 — Hạn chế tải

Giảm active subscriptions, `flatMap` concurrency, page size theo workload; bỏ buffer không giới hạn; đặt rate limiter/admission control chia sẻ. Nếu hệ thống quá tải, pause bulk scan/backfill không thiết yếu theo runbook.

### Bước 5 — Đặt lại semantics

Không chỉ thay `collectList()` bằng operator khác mà vẫn ép downstream giữ toàn bộ DTO. Cần streaming tới sink với quota, cancellation đúng và kiểm soát memory ở tất cả các lớp.

### Bước 6 — Xác minh

Theo dõi heap/GC, active streams, API first/total latency, timeout, compaction, node xấu nhất và error budget; chỉ tăng concurrency từng bước sau khi ổn định.

## 23. Runbook C — Dữ liệu xuất hiện trùng sau retry hoặc client ngắt kết nối

**Tình huống:** Một API streaming trả 30 row, gặp network timeout, operator `retryWhen` subscribe lại. Client nhận 15 row đầu hai lần hoặc job side-effecting sink ghi lặp.

### Bước 1 — Xác định vị trí lỗi

Publisher đã phát row nào trước `onError`? Retry thuộc driver hay Reactor? Có gateway retry cả HTTP request không? Logs cần gắn **logical request ID** nhưng tránh lưu dữ liệu nhạy cảm.

### Bước 2 — Kiểm tra hợp đồng output

Nếu HTTP streaming đã gửi một phần body, service có thể không thể thay status code hay “thu hồi row đã gửi”. Cần xác định **response có được phép phát trùng không** và cách client resume.

### Bước 3 — Tắt retry toàn stream nếu không an toàn

Đối với streaming trả kết quả cho người dùng, thường nên kết thúc với lỗi rõ hoặc dùng cursor/paging token có hợp đồng nếu phù hợp hơn, thay vì ngầm phát lại từ đầu.

### Bước 4 — Thiết kế định danh dữ liệu

Dùng primary key/clustering key để deduplicate hoặc checkpoint ở consumer nếu nghiệp vụ cho phép. Token không tự là cursor thời gian và paging state không bảo đảm snapshot giữa các lần subscribe.

### Bước 5 — Nếu đây là write pipeline

Kiểm tra operation ID, idempotency, TTL/timestamp, counter/LWT và side effects. Cancellation/timeout không chứng minh mutation chưa được ghi.

### Bước 6 — Kiểm thử lại

Mô phỏng lỗi sau khi phát một phần row trong lab, xác minh số lần query thực sự chạy, downstream nhận bao nhiêu row, có duplicate hay không, và rate/heap vẫn nằm trong ngưỡng.

## 24. Những ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
|---|---|
| “Async và reactive là một.” | `CompletionStage` khác `Publisher` và demand-based protocol |
| “Mọi Java Driver Cassandra có executeReactive.” | Phải xác minh đúng driver/version/artifact/API |
| “Reactor có sẵn trong Cassandra server.” | Reactor là thư viện JVM ở application, tùy chọn |
| “Publisher là một List đã tải hết.” | Là luồng phần tử theo subscription và demand |
| “request(1) nghĩa server chỉ đọc một row.” | Có page/server buffers, tombstone/SSTable scan |
| “Page size 100 giới hạn tổng query 100 row.” | Cần CQL LIMIT hoặc cơ chế stop riêng |
| “limitRate(32) tương đương CQL LIMIT 32.” | `limitRate` điều chỉnh demand Reactor |
| “Flux tự ngăn tất cả OutOfMemoryError.” | Buffer, collectList, row lớn và fan-out vẫn gây OOM |
| “onBackpressureBuffer luôn tiết kiệm RAM.” | Buffer không giới hạn có thể làm heap tăng |
| “cancel() chắc chắn dừng coordinator ngay.” | In-flight CQL có thể vẫn được xử lý |
| “cancel reactive write = rollback.” | Mutation có thể đã được replica apply |
| “Subscribe hai lần luôn chia sẻ một SELECT.” | Có thể tái thực thi query hai lần |
| “retry() chỉ lặp phần row bị lỗi.” | Có thể resubscribe toàn Publisher, phát trùng |
| “Một Flux mặc định hỗ trợ exactly once.” | Không; phải thiết kế idempotency/reconciliation |
| “flatMap(...,8) giới hạn toàn bộ service 8 request.” | Chỉ giới hạn trong pipeline đó |
| “block() trong WebFlux vẫn nonblocking.” | Block có thể chiếm event-loop |
| “onErrorResume(Flux.empty()) vô hại.” | Che lỗi thành dữ liệu rỗng, làm sai nghiệp vụ |
| “Token-aware routing chữa hot partition.” | Tập replica vẫn chịu tải tập trung |
| “LOCAL_QUORUM không còn quan trọng khi dùng Flux.” | CL vẫn quyết định điều kiện phản hồi replica |
| “Reactive SELECT tự nhận dữ liệu mới liên tục.” | Không phải CDC/change feed |
| “Publisher tạo snapshot toàn bảng.” | Các page có thể quan sát dữ liệu biến đổi |
| “Không thấy stream trong netstats là không có CQL load.” | netstats chủ yếu là SSTable streaming |
| “Giảm DriverTimeout là đủ dù p99 tăng.” | Phải xét SLO, API latency và tải toàn hệ thống |

## 25. Bài tập và đáp án

### Câu 1 — Sự khác biệt cốt lõi

`CompletionStage<AsyncResultSet>` có đồng nghĩa `Publisher` không?

**Đáp án:** Không. CompletionStage mô tả hoàn tất bất đồng bộ một computation/page; Publisher mô tả nguồn phần tử kèm subscription, demand và lifecycle signals.

### Câu 2 — Driver 3.x

Ứng dụng dùng package `com.datastax.driver.core.*` và không có `executeReactive`. Có nên thêm `reactor-core` rồi gọi trực tiếp method 4.x không?

**Đáp án:** Không. Reactor không tự bổ sung native method cho driver 3.x. Cần dùng API hiện có hoặc nâng phiên bản theo compatibility matrix.

### Câu 3 — Reactive Streams và Java Flow

Có thể cast `org.reactivestreams.Publisher` thành `java.util.concurrent.Flow.Publisher` không?

**Đáp án:** Không mặc định. Chúng là interface khác nhau; cần adapter nếu phải giao tiếp hai kiểu.

### Câu 4 — Demand

Subscriber gọi `request(5)`. Có nghĩa Cassandra chỉ đọc đúng năm entry trên SSTable?

**Đáp án:** Không. Demand chỉ kiểm soát phần tử phát xuống subscriber; server/driver có thể đọc/buffer một page hoặc quét nhiều tombstone trước khi trả row.

### Câu 5 — LIMIT

CQL có `LIMIT 500` và page size 50. `request(10)` có thay `LIMIT` thành 10 không?

**Đáp án:** Không. CQL có thể trả tới 500 row; demand chỉ yêu cầu nhận phần tử theo subscription hiện tại.

### Câu 6 — request(0)

Muốn tạm dừng stream, có nên gọi `request(0)`?

**Đáp án:** Không. Reactive Streams yêu cầu `n > 0`; muốn chờ thì không request thêm, muốn dừng thì cancel.

### Câu 7 — Cancellation

Client hủy sau 20 row. Có đảm bảo server đã dừng mọi công việc CQL chưa?

**Đáp án:** Không. Request/page đã gửi có thể còn được xử lý; hủy không rollback.

### Câu 8 — Hai subscriber

Một cold Publisher được subscribe hai lần. Có thể mặc định chỉ có một query CQL không?

**Đáp án:** Không. Có thể thực thi lại query cho mỗi subscription; phải xác nhận contract và có sharing/cache chủ đích nếu cần.

### Câu 9 — Fan-out

100 HTTP requests đồng thời, mỗi request có `flatMap` concurrency=8. Tổng inner subscriptions có thể tới mức nào?

**Đáp án:** Gần 800 trong ví dụ lý tưởng. Cần limiter chung, không chỉ concurrency per-request.

### Câu 10 — Buffer

Pipeline dùng `onBackpressureBuffer()` không giới hạn và downstream xử lý chậm. Rủi ro gì?

**Đáp án:** Heap/GC và OOM có thể tăng, dù upstream là Publisher. Cần buffer bounded/overflow policy và rate/concurrency control.

### Câu 11 — Reactive trong WebFlux

Controller gọi `repository.find(...).block()` trên event-loop. Có còn nonblocking end-to-end không?

**Đáp án:** Không. `block()` có thể chặn luồng xử lý event-loop; nên trả `Flux/Mono` hoặc dùng API sync ở kiến trúc sync.

### Câu 12 — Retry sau khi đã phát data

Stream phát 10 row rồi lỗi, `retryWhen` subscribe lại từ đầu. Hậu quả nào có thể xảy ra?

**Đáp án:** 10 row đầu có thể bị phát lại/trùng, nhất là với sink có side effect hoặc HTTP streaming; cần checkpoint/dedup hoặc không retry toàn stream.

### Câu 13 — Null và onComplete

Query thành công nhưng không có row; Publisher gọi `onComplete` mà không `onNext`. Có phải lỗi timeout?

**Đáp án:** Không. Đây là kết quả rỗng hợp lệ; timeout/error thường đi `onError`.

### Câu 14 — Reactive write

Một mutation counter nhận timeout rồi Publisher tự retry. Có an toàn không?

**Đáp án:** Không mặc định. Lần đầu có thể đã increment; lần retry tăng thêm. Cần operation identity/dedup hoặc thiết kế khác.

### Câu 15 — Consistency

Chuyển `executeAsync` sang `executeReactive` và dùng cùng `LOCAL_QUORUM`. Có làm quorum RF=3 chỉ còn một replica không?

**Đáp án:** Không. CL và RF của Cassandra không thay đổi do API phía Java.

### Câu 16 — Hệ thống bị chậm

Page size=500, active streams=400, p99 tăng và compaction backlog lớn. Có nên chỉ tăng timeout?

**Đáp án:** Không. Cần giảm concurrency/page size nếu hợp lý, kiểm tra disk, SSTable/tombstone, backpressure và đo SLO. Tăng timeout có thể chỉ làm request tồn tại lâu hơn.

### Câu 17 — Reactive SELECT có phải CDC?

Một subscription `executeReactive(SELECT ...)` có tự phát thêm row khi dữ liệu mới được INSERT vào bảng không?

**Đáp án:** Không. Nó tiêu thụ kết quả truy vấn; change feed cần CDC/event stream riêng.

### Câu 18 — Biên giới hỗ trợ

Một bản Driver 4.x cụ thể không có kiểu/method reactive theo tài liệu bạn đang đọc. Bước đúng là gì?

**Đáp án:** Xác minh release Javadoc, Maven artifact, dependency conflicts, JDK và server/driver compatibility. Nếu không được hỗ trợ, chọn `executeAsync` hoặc nâng driver có kế hoạch; không ép cast.

## 26. Checklist triển khai và kiểm toán

### 26.1. Driver và thư viện

~~~text
[ ] Đã xác định chính xác Java Driver version, artifact, JDK.
[ ] executeReactive và kiểu Publisher có trong API version sử dụng.
[ ] org.reactivestreams / Reactor / RxJava adapters tương thích.
[ ] Không nhầm Java Flow.Publisher với Reactive Streams Publisher.
[ ] Đã đối chiếu driver ↔ Cassandra server/protocol compatibility.
[ ] CqlSession được tái sử dụng, auth/TLS/local DC đúng.
[ ] Spring Data/WebFlux version được kiểm tra nếu sử dụng.
~~~

### 26.2. CQL, backpressure và correctness

~~~text
[ ] Query đầy đủ partition key hoặc có access pattern được phê duyệt.
[ ] Prepared/bound values, không nối raw CQL input từ người dùng.
[ ] LIMIT và page size phù hợp row size/workload.
[ ] Subscriber demand được xử lý; không request(0)/negative.
[ ] Không có buffer/list unbounded hoặc collectList trên tập lớn.
[ ] Max active subscriptions/in-flight/rate/bytes có quota chia sẻ.
[ ] Không block driver callback hoặc WebFlux event loop.
[ ] Cancellation và timeout không bị coi là rollback.
[ ] Retry/resubscribe có idempotency, deadline và dedup nếu cần.
[ ] Không tự biến onError thành kết quả rỗng.
[ ] Không giả định paging là snapshot hoặc SELECT là change stream.
[ ] RF, CL, DC, token-aware routing và replica load được hiểu đúng.
~~~

### 26.3. Test và vận hành

~~~text
[ ] Unit tests kiểm tra demand, onError, onComplete, cancel.
[ ] Integration tests seed row, kiểm tra 0/1/n records và nullable.
[ ] Test hai subscriptions; xác minh có/không có query repeat.
[ ] Test retry sau partial output và xử lý trùng.
[ ] Test slow downstream và concurrency lớn ở lab an toàn.
[ ] Metrics có active streams, first-row/total latency, rows/bytes.
[ ] Driver QPS/timeouts/retries và backend compaction/GC/disk.
[ ] Không log raw routing key, tenant ID, credentials hoặc full row.
[ ] Có runbook backpressure, dependency mismatch và retry duplicate.
[ ] Có điều kiện pause/load shed khi node xấu nhất chạm SLO.
~~~

## 27. Tổng kết

Reactive API trong Cassandra Java Driver cần được hiểu theo **hai lớp độc lập nhưng liên quan**:

1. **Lớp driver/hỗ trợ:** chỉ dùng `executeReactive` khi đúng Java Driver version/artifact có phương thức và kiểu Publisher phù hợp; kiểm tra tương thích JDK, server/protocol và các framework tùy chọn như Reactor/Spring.
2. **Lớp Reactive Streams:** `Publisher` phát tín hiệu qua `Subscription`, `Subscriber` gọi `request(n)` và `cancel()` để biểu đạt nhu cầu/lifecycle.
3. **Backpressure không thay CQL LIMIT/page size:** nhu cầu nhận row khác với bytes đã đọc, server paging, tombstone/SSTable scan hoặc quota resource.
4. **Reactive không tự đảm bảo bounded memory:** nhiều subscriptions, `collectList`, `onBackpressureBuffer` và blocking callbacks vẫn có thể khiến heap, p99 và replica load tăng mạnh.
5. **Mỗi subscription/retry có thể tái thực thi CQL:** đừng tự mặc định dữ liệu được cache, không lặp row hoặc có snapshot giữa các lần đọc.
6. **Cancellation không rollback:** request đã gửi có thể tiếp tục; mutation timeout/cancel phải xử lý theo idempotency và consistency.
7. **Giữ đường đi nonblocking thực sự:** không `block()` trên event-loop, không làm I/O chặn trong onNext, giới hạn fan-out bằng quota chia sẻ.
8. **CQL/cluster vẫn quyết định phần lớn chi phí:** partition key, token routing, RF/CL, compaction, repair, tombstone và network không thay đổi chỉ vì API Java trả Flux.
9. **Đo và kiểm thử end-to-end:** time to first row, total consume time, active streams, p99, errors, retries, cancellation, disk/GC và data correctness.

Câu hỏi để thiết kế một luồng truy vấn reactive không chỉ là **“đã trả về Flux hay chưa?”**, mà là: **“Driver version có thực sự hỗ trợ Publisher này, subscriber có khả năng xử lý theo demand, toàn hệ thống có giới hạn subscription và bytes, và việc cancel/retry có giữ đúng dữ liệu theo CL cũng như nghiệp vụ hay không?”**. Chỉ khi trả lời được các câu đó bằng code, test và số liệu, Reactive API mới giúp Java–Cassandra vận hành ổn định hơn.
