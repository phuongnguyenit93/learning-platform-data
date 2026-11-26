# Tích hợp WebFlux và kiểm tra đường đi không chặn

**Spring WebFlux** cung cấp mô hình xử lý HTTP dựa trên Reactive Streams, thường biểu diễn một kết quả bất đồng bộ bằng `Mono<T>` và một chuỗi kết quả bằng `Flux<T>`. **Spring Data Cassandra reactive** giúp ứng dụng đọc và ghi dữ liệu Cassandra qua các publisher đó, thay vì chặn thread của HTTP request để chờ cơ sở dữ liệu phản hồi.

Nhưng **trả về `Mono` hoặc `Flux` không đủ chứng minh một API không chặn**. Nếu controller gọi `CassandraTemplate` đồng bộ, `CqlSession.execute(...)`, `block()`, một HTTP client đồng bộ hoặc xử lý file chặn thread ngay trong luồng Reactor, hệ thống vẫn có thể tắc nghẽn event loop. Tính không chặn cần được duy trì **trên toàn đường đi**: xác thực → controller → service → repository/template → Java Driver → xử lý response.

Bài thuộc chương **Truy cập phản ứng** của module **SPRING_DATA_CASSANDRA**. Mục tiêu là xây một API WebFlux đọc sự kiện theo partition key, sử dụng `ReactiveCassandraRepository` và `ReactiveCassandraTemplate` đúng ngữ nghĩa, xử lý backpressure/timeout/error, rồi kiểm tra bằng `StepVerifier`, `WebTestClient`, integration test và công cụ phát hiện blocking. Các ví dụ ưu tiên Spring Boot 3.x, Spring Data Cassandra 4.x, Reactor và Java Driver 4.x; khi triển khai cần đối chiếu API/chữ ký với phiên bản dependency thực tế.

## 1. Thế nào là “non-blocking” trong WebFlux?

Ví dụ đường đi mong muốn:

~~~text
HTTP GET /v1/tenants/{tenantId}/events?day=...
                 |
                 v
         WebFlux handler
                 |
                 v
     Reactive access policy (Mono<Void>)
                 |
                 v
       EventService (Flux<DTO>)
                 |
                 v
    ReactiveCassandraRepository
                 |
                 v
     Cassandra asynchronous driver
                 |
                 v
       Coordinator / replicas
                 |
          async completion
                 |
                 v
     WebFlux writes HTTP response
~~~

Trong đường đi này, thread event loop không cần đứng chờ I/O Cassandra theo cách `Future.get()` hoặc `block()`. Khi request I/O chưa xong, thread có thể phục vụ tác vụ khác; Reactor sẽ phát tín hiệu kết quả/lỗi khi driver hoàn tất.

**Phân biệt ba khái niệm:**

| Khái niệm | Định nghĩa thực tế |
| --- | --- |
| **Non-blocking I/O** | Không chiếm một thread chỉ để chờ kết quả I/O ngoài tiến trình |
| **Asynchronous** | Công việc có thể hoàn thành sau và thông báo qua callback/publisher; không mặc nhiên bảo đảm không chặn ở mọi chỗ |
| **Backpressure** | Subscriber có cơ chế thông báo mức nhu cầu dữ liệu; không đồng nghĩa mỗi lần `request(1)` chỉ tạo đúng một network request hay chỉ một hàng được đọc từ Cassandra |

WebFlux phù hợp cho nhiều request chủ yếu chờ I/O, nhưng không khiến thao tác CPU nặng trở nên nhẹ hơn và cũng không chữa truy vấn Cassandra thiếu partition key hoặc phải quét nhiều tombstone.

## 2. Bắt đầu bằng bảng Cassandra theo truy vấn

Giả sử ứng dụng hiển thị lịch sử sự kiện của từng tenant trong một ngày. Bảng được thiết kế cho đúng access pattern:

~~~sql
CREATE KEYSPACE IF NOT EXISTS activity_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS activity_ks.events_by_tenant_day (
    tenant_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    status      text,
    payload     text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, event_id DESC
);
~~~

- `(tenant_id, event_day)` là **composite partition key**: câu truy vấn đọc lịch sử trong ngày phải có đầy đủ hai giá trị này.
- `occurred_at` và `event_id` là **clustering columns**: đảm bảo thứ tự đọc mới nhất trước và phân biệt sự kiện cùng thời điểm.
- `payload` có thể lớn nên danh sách chỉ đọc những cột nhỏ cần hiển thị; API chi tiết đọc theo **đầy đủ primary key**.
- `dc1: 3` chỉ là cấu hình replication minh họa; topology thật phải có đủ node và được vận hành phù hợp.

CQL danh sách:

~~~sql
SELECT tenant_id, event_day, occurred_at, event_id,
       event_type, status
FROM activity_ks.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 100;
~~~

Truy vấn trên không cần `ALLOW FILTERING` vì dùng đủ partition key. **Reactive không có nghĩa rẻ**: nếu tenant/ngày là hot partition, có hàng triệu tombstone hoặc kích thước payload lớn, request vẫn có thể chậm và tốn tài nguyên replica.

## 3. Dependency và cấu hình Spring Boot

Với Maven, ví dụ dùng starter WebFlux và Spring Data Cassandra reactive:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot thường quản lý version của starter/driver qua dependency management; đừng chọn những version độc lập không tương thích. Cấu hình minh họa:

~~~yaml
spring:
  cassandra:
    contact-points: cassandra-dc1.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: activity_ks
    schema-action: none
~~~

`schema-action: none` yêu cầu bảng/keyspace đã được tạo qua migration trước khi ứng dụng chạy. Với production, bổ sung TLS, xác thực, pooling, timeout, observability và secret management theo hạ tầng thật.

**Không đưa `spring-boot-starter-web` vào ứng dụng một cách vô tình rồi mặc định WebFlux vẫn là HTTP runtime chính**. Nếu cả MVC và WebFlux cùng có mặt, Spring Boot thường ưu tiên MVC, trừ khi có cấu hình ứng dụng phù hợp. Xác minh runtime và luồng request thực tế, đặc biệt khi dự án có dependency transitive.

## 4. Entity mapping và lớp khóa tổng hợp

Spring Data Cassandra reactive sử dụng cùng metadata ánh xạ entity/primary key cơ bản với truy cập đồng bộ:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.Table;

@PrimaryKeyClass
public class EventKey implements Serializable {
    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "event_day", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
        name = "occurred_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private UUID eventId;

    // Constructor, getters/setters và equals/hashCode.
}

@Table("events_by_tenant_day")
public class EventRow {
    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("status")
    private String status;

    @Column("payload")
    private String payload;

    // Constructor, getters/setters.
}
~~~

Đây là hai class Java minh họa (đặt ở hai file Java riêng khi triển khai). Bổ sung accessor và constructor phù hợp để Spring Data mapping hoạt động. `Instant` ánh xạ cột CQL `timestamp`; `event_day` là `date`. Tên property của Java và tên cột CQL không mặc định trùng nhau nếu dùng `@Column`/`@PrimaryKeyColumn`.

**Không đặt TTL hoặc consistency level vào tên class để kỳ vọng Cassandra tự hiểu**. Chúng là lựa chọn của schema/CQL/driver và từng thao tác, không phải hiệu ứng của reactive mapping.

## 5. ReactiveCassandraRepository và kiểu trả về

Ví dụ khai báo repository truy vấn đúng một partition:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import reactor.core.publisher.Flux;

public interface EventRepository
        extends ReactiveCassandraRepository<EventRow, EventKey> {

    @Query("""
        SELECT tenant_id, event_day, occurred_at, event_id,
               event_type, status
        FROM events_by_tenant_day
        WHERE tenant_id = ?0 AND event_day = ?1
        LIMIT 100
        """)
    Flux<EventRow> findRecent(UUID tenantId, LocalDate day);
}
~~~

Giải thích:

- `ReactiveCassandraRepository<EventRow, EventKey>` cung cấp các thao tác reactive như `findById(key)`, `save(row)`, `deleteById(key)` tùy interface/version.
- `findRecent(...)` trả về `Flux<EventRow>` thay vì `List<EventRow>`. Khi có subscription, driver thực thi truy vấn và phát dữ liệu qua publisher.
- `LIMIT 100` ở đây **giới hạn tổng số hàng** của truy vấn minh họa; không phải cursor pagination đầy đủ.
- `SELECT` không lấy `payload` cho màn hình danh sách, giảm số byte mạng/giải mã. Nếu mapping entity bị thiếu trường không được select, đừng đưa entity thiếu dữ liệu vào `save()` và mong nó vẫn giữ nguyên các cột khác.

Một số version/đường mapping có thể đòi chọn kiểu projection cụ thể (DTO/interface). Khi sử dụng interface projection, kiểm tra property và mapping của version đang chạy; code trên chọn cột tường minh để giải thích ý định truyền ít dữ liệu.

### Mono khác Flux khi nào?

| Nhu cầu | Reactor type nên trả |
| --- | --- |
| Tìm một sự kiện bằng full key | `Mono<EventRow>`, có thể rỗng |
| Đọc nhiều sự kiện trong partition | `Flux<EventRow>` |
| Ghi một entity và cần entity đã lưu | `Mono<EventRow>` |
| Xóa và chỉ cần biết đã kết thúc | `Mono<Void>` |
| Kiểm tra quyền truy cập bất đồng bộ | `Mono<Void>` hoặc `Mono<Decision>` |

`Flux` không có nghĩa “trả toàn bộ bảng”. Truy vấn Cassandra vẫn phải tuân theo khóa, giới hạn, paging và chính sách điều khiển tải.

## 6. Service reactive: nối luồng thay vì gọi subscribe

Định nghĩa DTO cho API:

~~~java
import java.time.Instant;
import java.util.UUID;

public record EventSummary(
        UUID eventId,
        Instant occurredAt,
        String eventType,
        String status) {

    public static EventSummary from(EventRow row) {
        return new EventSummary(
            row.getKey().getEventId(),
            row.getKey().getOccurredAt(),
            row.getEventType(),
            row.getStatus()
        );
    }
}
~~~

Để tránh client dùng cursor/tenantId của người khác, service kiểm tra quyền **trước khi truy cập database**. Giả sử một policy bất đồng bộ:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;

public interface ReactiveTenantAccess {
    // Mono<Void> hoàn tất nếu đã được phép;
    // Mono.error(...) khi bị từ chối.
    Mono<Void> requireRead(UUID tenantId);
}
~~~

Service:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class EventService {
    private final EventRepository repository;
    private final ReactiveTenantAccess access;

    public EventService(
            EventRepository repository,
            ReactiveTenantAccess access) {
        this.repository = repository;
        this.access = access;
    }

    public Flux<EventSummary> recent(
            UUID tenantId, LocalDate day) {

        return access.requireRead(tenantId)
            .thenMany(Flux.defer(
                () -> repository.findRecent(tenantId, day)))
            .map(EventSummary::from);
    }

    public Mono<EventSummary> one(EventKey key) {
        return access.requireRead(key.getTenantId())
            .then(Mono.defer(
                () -> repository.findById(key)))
            .map(EventSummary::from);
    }
}
~~~

**Điểm quan trọng:** `thenMany(Flux.defer(...))` yêu cầu publisher kiểm tra quyền **hoàn tất thành công** rồi mới gọi repository khi có subscription. `Flux.defer` cũng tránh gọi phương thức truy cập dữ liệu quá sớm trong lúc xây pipeline. Trong hệ thống thật, `requireRead` phải lấy danh tính hiện tại từ cơ chế xác thực WebFlux/Spring Security, kiểm tra tenant/role và trả lỗi phù hợp, không dựa vào một ID do client cung cấp.

**Không gọi `subscribe()` ở đây.** WebFlux là subscriber ở ranh giới HTTP. Nếu service tự gọi `subscribe()` rồi trả kết quả ngay, công việc database có thể chạy tách khỏi response, lỗi bị bỏ qua, không còn backpressure/cancellation đúng và khó kiểm thử.

## 7. Tích hợp REST controller bằng WebFlux

Controller chỉ **trả về publisher**, không chặn chờ kết quả:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/v1/tenants/{tenantId}/events")
public class EventController {
    private final EventService service;

    public EventController(EventService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<EventSummary> recent(
            @PathVariable UUID tenantId,
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day) {

        return service.recent(tenantId, day);
    }
}
~~~

Ví dụ request:

~~~http
GET /v1/tenants/550e8400-e29b-41d4-a716-446655440000/events?day=2026-11-25
Authorization: Bearer <access-token>
Accept: application/json
~~~

Kết quả là JSON array:

~~~json
[
  {
    "eventId": "106bf315-e3c0-4fcb-8b5d-5f480bdf0353",
    "occurredAt": "2026-11-25T08:30:00Z",
    "eventType": "ORDER_PAID",
    "status": "PROCESSED"
  }
]
~~~

Khi repository trả `Flux.empty()`, endpoint có thể trả danh sách rỗng `[]` với HTTP 200. Nếu một API chi tiết trả `Mono.empty()`, hãy quy định rõ cách chuyển thành HTTP 404 qua `switchIfEmpty(...)` thay vì để behavior ngầm tùy controller.

**Bảo mật:** client có thể thay `tenantId` trong URL; đây **không phải bằng chứng** client được đọc tenant đó. `ReactiveTenantAccess` là một phần ví dụ bắt buộc, cần triển khai dựa trên principal đã xác thực và kiểm tra quyền cho mọi request.

## 8. Toàn bộ chuỗi non-blocking: điều gì có thể làm hỏng?

| Tầng | Cách đúng | Anti-pattern |
| --- | --- | --- |
| WebFlux controller | Trả `Mono`/`Flux` trực tiếp | `return service.recent(...).collectList().block()` |
| Authorization | `Mono<Void>` kiểm tra quyền bất đồng bộ | Tra user qua JDBC chặn event loop |
| Service | `flatMap`, `concatMap`, `then`, `onErrorMap` | `Future.get()`, `join()`, `Thread.sleep()` |
| Cassandra | `ReactiveCassandraRepository`, `ReactiveCassandraTemplate` | `CassandraTemplate` đồng bộ trên event loop |
| Java Driver | Async/reactive API | `CqlSession.execute(...)` đồng bộ trên event loop |
| HTTP client khác | `WebClient` | `RestTemplate` đồng bộ trên event loop |
| File/legacy API | Dùng non-blocking API hoặc cô lập sang boundedElastic | Gọi blocking I/O trực tiếp trong `map` |
| Observability | Reactive context, instrument async flow | Logging/metrics gây block dài hoặc phụ thuộc ThreadLocal sai |

Những đoạn code **không nên** đặt ở WebFlux handler:

~~~java
// SAI: chặn thread đang phục vụ request.
List<EventRow> rows = repository.findRecent(tenantId, day)
    .collectList()
    .block();

// SAI: chuyển publisher thành Future rồi chờ đồng bộ.
List<EventRow> rows2 = repository.findRecent(tenantId, day)
    .collectList()
    .toFuture()
    .get();

// SAI: gọi đồng bộ CassandraTemplate ngay trong luồng HTTP.
EventRow row = cassandraTemplate.selectOneById(
    key, EventRow.class
);
~~~

Cả ba ví dụ đều có thể làm tắc luồng request nếu chạy trên non-blocking scheduler. Kể cả khi test nhỏ trên máy phát triển “chạy được”, tải đồng thời cao có thể làm latency tăng, request timeout và event loop bị giữ quá lâu.

### Không phải cứ dùng map là non-blocking

~~~java
return repository.findRecent(tenantId, day)
    .map(row -> {
        Thread.sleep(100);  // SAI; minh họa chặn thread.
        return EventSummary.from(row);
    });
~~~

Đoạn trên chỉ minh họa lỗi; trong Java thực tế `Thread.sleep` còn cần xử lý `InterruptedException`. `map` thực hiện transform đồng bộ trên thread đang phát tín hiệu. Nếu transform chặn, event loop/driver thread có thể bị ảnh hưởng.

## 9. Reactor operators: chọn đúng cách ghép luồng

| Operator | Mục đích | Sai lầm thường gặp |
| --- | --- | --- |
| `map` | Biến đổi giá trị đồng bộ, nhẹ | Gọi I/O blocking trong lambda |
| `flatMap` | Ghép publisher bất đồng bộ | Fan-out không giới hạn tới Cassandra/HTTP |
| `concatMap` | Ghép lần lượt, giữ thứ tự tín hiệu | Dùng cho mọi việc dù không cần, tạo throughput thấp |
| `flatMapSequential` | Cho chạy song song có kiểm soát nhưng phát kết quả theo thứ tự | Quên giới hạn concurrency/prefetch |
| `then`/`thenMany` | Chạy bước sau khi bước trước hoàn tất | Gọi bước sau trước khi được authorize |
| `onErrorResume` | Chọn hướng xử lý lỗi có chủ đích | Nuốt lỗi Cassandra và trả danh sách rỗng |
| `timeout` | Giới hạn thời gian chờ trong pipeline | Nghĩ timeout chắc chắn đã hủy mutation ở server |
| `retryWhen` | Retry theo chính sách rõ | Retry counter/LWT/mutation không idempotent mù quáng |
| `doOn...` | Quan sát signal, metrics/logging | Thực hiện side effect nghiệp vụ nặng, có thể chạy nhiều lần |

Với nhiều lần gọi database độc lập, giới hạn concurrency:

~~~java
Flux<EventSummary> result = Flux.fromIterable(days)
    .flatMap(
        day -> service.recent(tenantId, day),
        3  // tối đa 3 luồng day queries đang chạy đồng thời
    );
~~~

Đoạn này **không tự bảo đảm thứ tự thời gian toàn cục** khi ghép nhiều partition/ngày; `flatMap` có thể interleave các kết quả. Nếu API cần thứ tự newest-first tuyệt đối, phải thiết kế merge/paging theo bucket và clustering key. Đừng bỏ qua fan-out limit dù dữ liệu được đọc bằng API reactive.

## 10. ReactiveCassandraTemplate và thao tác theo khóa

Khi cần mapping linh hoạt hơn repository, `ReactiveCassandraTemplate` cung cấp API truy cập Cassandra theo publisher.

Ví dụ tìm một entity bằng **đầy đủ primary key**:

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraTemplate;
import reactor.core.publisher.Mono;

public final class EventLookup {
    private final ReactiveCassandraTemplate template;

    public EventLookup(ReactiveCassandraTemplate template) {
        this.template = template;
    }

    public Mono<EventRow> byId(EventKey key) {
        return template.selectOneById(key, EventRow.class);
    }
}
~~~

Kiểm tra signature của `selectOneById`, các tùy chọn query và bean configuration theo version Spring Data Cassandra đang chạy. Mục đích của ví dụ là **không chuyển sang template đồng bộ chỉ vì cần API truy vấn tùy biến**.

Với các query nhiều hàng, template reactive thường có API chọn dữ liệu theo `Query` và mapping entity. Khi phải kiểm soát page size, consistency level hoặc paging state đặc biệt, xác minh API tương ứng của Spring Data hoặc dùng Java Driver bất đồng bộ ở tầng adapter, không dùng API blocking.

## 11. Java Driver async khi cần truy vấn đặc biệt

Đôi lúc cần truy cập `CqlSession` trực tiếp vì câu CQL/phân trang đặc biệt. Với Java Driver 4.x, phân biệt:

~~~java
// Blocking: không gọi trên WebFlux event loop.
ResultSet blocking = session.execute(boundStatement);

// Async: CompletionStage<AsyncResultSet>.
CompletionStage<AsyncResultSet> pending =
    session.executeAsync(boundStatement);
~~~

Có thể chuyển async result thành Reactor publisher:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Flux<EventSummary> firstDriverPage(
        BoundStatement statement) {
    return Mono.fromCompletionStage(
            () -> session.executeAsync(statement))
        .flatMapMany(result ->
            Flux.fromIterable(result.currentPage()))
        .map(row -> new EventSummary(
            row.getUuid("event_id"),
            row.getInstant("occurred_at"),
            row.getString("event_type"),
            row.getString("status")
        ));
}
~~~

Giả sử `session` là bean `CqlSession` đã được quản lý và `statement` là bound statement hợp lệ. Dùng supplier trong `fromCompletionStage(() -> ...)` giúp bắt đầu request khi pipeline được subscribe, không ngay lúc xây dựng publisher.

**Giới hạn cố ý của ví dụ:** `currentPage()` chỉ duyệt **trang đầu đã nhận**. Để đi qua các trang tiếp theo, phải xử lý `hasMorePages()`/`fetchNextPage()` theo cách **bất đồng bộ**, bảo toàn backpressure, giới hạn số trang và khôi phục paging state đúng truy vấn. Không gọi `all()` hay `get()` đồng bộ để ép lấy toàn bộ dữ liệu.

Trong ứng dụng thường, ưu tiên `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate` để tránh tự viết vòng paging/row mapping không cần thiết.

## 12. Khi có thư viện blocking không thể thay ngay

Nếu bắt buộc dùng một thư viện legacy chặn I/O, **cô lập** công việc đó trên scheduler dành cho blocking:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<LegacyRecord> legacy = Mono.fromCallable(
        () -> legacyBlockingClient.loadRecord(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`boundedElastic` có giới hạn và dành cho **đoạn blocking không tránh được**, không phải “thuốc chữa” cho mọi pipeline. Nó vẫn dùng thread đang chờ I/O và có thể đầy hàng đợi khi tải cao. Hãy đặt timeout, concurrency limit và lộ trình thay thư viện blocking bằng non-blocking API.

Với Cassandra, **không nên chọn `CassandraTemplate` đồng bộ rồi bọc toàn bộ trong boundedElastic nếu `ReactiveCassandraTemplate` đã có sẵn**. Điều đó làm mất lợi ích và tăng độ phức tạp triển khai.

**`subscribeOn`** thay scheduler ở phía nguồn của chuỗi, còn **`publishOn`** thay thread xử lý tín hiệu ở phía sau operator. Đừng sử dụng các operator này chỉ để tạo cảm giác “đang chạy async” mà không hiểu phần code nào thực sự gây block.

## 13. Backpressure và paging của Cassandra không phải cùng một cơ chế

Khi subscriber yêu cầu `request(n)`, Reactor điều phối **nhu cầu phát tín hiệu**, trong khi Cassandra/driver đọc dữ liệu theo **trang mạng (fetch/page size)**. Hai cơ chế phối hợp nhưng **không tương đương một-một**.

~~~text
Client / HTTP subscriber
     request(10)
         |
         v
Reactor Flux<EventRow>
         |
         v
Spring Data reactive adapter
         |
         v
Driver Cassandra (trang dữ liệu có fetch size riêng)
         |
         v
Cassandra replicas
~~~

Một lần fetch của driver có thể nhận nhiều hàng hơn số hiện tại mà subscriber yêu cầu. Dữ liệu có thể được buffer ở tầng driver/framework; **không khẳng định `request(1)` tương đương một hàng đọc trên mạng**.

Các điểm cần thiết kế:

1. **Query vẫn cần partition key và giới hạn hợp lý.** Reactive không cho phép đọc cả cluster miễn phí.
2. **Paging state** gắn với mẫu CQL và bound parameters; API cursor công khai cần xác thực/ủy quyền, hạn dùng và bảo vệ chống sửa đổi.
3. **`LIMIT` là giới hạn tổng hàng**, không giống số hàng trong một fetch page. `LIMIT 100` có thể khiến API chỉ bao giờ trả tối đa 100 hàng.
4. **Cỡ trang và backpressure** giúp quản lý tài nguyên, không làm partition lớn tự nhỏ lại.
5. Nếu HTTP client ngắt kết nối, Reactor có thể phát **cancel signal**. Một truy vấn đã gửi tới Cassandra vẫn có thể đang chạy/được replica xử lý; cancellation không phải rollback.

### Khi không nên đưa toàn bộ dữ liệu vào bộ nhớ

~~~java
// Đường streaming, có thể phát dữ liệu theo tín hiệu của publisher.
Flux<EventSummary> items =
    service.recent(tenantId, day);

// Chuyển thành danh sách: gom hết kết quả được phát trước khi hoàn tất.
Mono<List<EventSummary>> all =
    service.recent(tenantId, day).collectList();
~~~

`collectList()` là operator hợp lệ và **không tự gọi block**, nhưng nó **tích lũy toàn bộ dữ liệu được phát trong bộ nhớ**. Chỉ dùng cho tập có giới hạn và biết rõ kích thước; không thể thay thế cursor/page size cho dữ liệu rất lớn.

## 14. JSON array, NDJSON và Server-Sent Events

Một controller trả `Flux<EventSummary>` với `application/json` thường được WebFlux serialize thành một **JSON array**. Tùy codec, buffer và client, không nên hứa mỗi event được gửi ngay lập tức khi database phát một row.

Nếu API thật sự cần **streaming từng phần tử**, có thể cân nhắc **NDJSON** hoặc **Server-Sent Events (SSE)**:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import reactor.core.publisher.Flux;

@GetMapping(produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<EventSummary> stream(
        @RequestParam LocalDate day,
        @PathVariable UUID tenantId) {
    return service.recent(tenantId, day);
}
~~~

Đây là **phác thảo method** đặt bên trong controller đã khai báo đường dẫn/field `service` ở mục 7; phần import và validation phải hợp nhất khi triển khai. NDJSON phát **mỗi đối tượng JSON trên một dòng**, không giống một JSON array. Cần giới hạn tốc độ phát, thời gian giữ kết nối, kích thước dữ liệu và xác thực request.

SSE thích hợp khi server cần liên tục thông báo sự kiện mới. Tuy nhiên **Cassandra không tự biến truy vấn SELECT thành một subscription thay đổi thời gian thực**; để phát dữ liệu mới liên tục, thường cần nguồn event/queue riêng thay vì polling Cassandra không giới hạn.

## 15. Ghi dữ liệu reactive: hiệu ứng chỉ xảy ra khi subscribe

Ví dụ thêm sự kiện:

~~~java
public Mono<EventRow> create(EventRow event) {
    // Caller/controller sẽ subscribe qua WebFlux.
    return repository.save(event);
}
~~~

Lời gọi `repository.save(event)` trả publisher. Với các publisher reactive thông thường, thao tác thực sự được kích hoạt khi subscription diễn ra. Không gọi `subscribe()` trong service rồi lập tức trả HTTP 201, vì database có thể chưa ghi xong và lỗi không còn gắn với response.

Nếu cần một endpoint ghi:

~~~java
@PostMapping
public Mono<ResponseEntity<EventSummary>> create(
        @RequestBody Mono<CreateEventRequest> request) {
    return request
        .flatMap(service::createAuthorized)
        .map(saved -> ResponseEntity
            .status(HttpStatus.CREATED)
            .body(EventSummary.from(saved)));
}
~~~

Đoạn mã là **phác thảo** minh họa ghép publisher: `CreateEventRequest`, `createAuthorized` và route/authorization cần được định nghĩa theo nghiệp vụ thực tế. Có thể chọn nhận một DTO trực tiếp thay vì `Mono<DTO>` khi body nhỏ; điều quan trọng là luồng service/database không block.

**Ghi reactive không thay đổi ngữ nghĩa Cassandra:** `save` thông thường có thể là upsert theo primary key. Timeout không chắc chắn mutation đã thất bại. Retry cần ID/timestamp ổn định và tính idempotent thực của thao tác. Reactive transaction không tự biến nhiều bảng Cassandra thành transaction SQL có isolation/rollback tổng quát.

## 16. Xử lý timeout, retry và lỗi theo mục đích

Một chuỗi đọc có timeout:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Flux;

public Flux<EventSummary> recentWithDeadline(
        UUID tenantId, LocalDate day) {

    return recent(tenantId, day)
        .timeout(Duration.ofSeconds(3))
        .doOnError(TimeoutException.class,
            ex -> metrics.recordReadTimeout());
}
~~~

`metrics` là service đo lường minh họa; cần định nghĩa khi triển khai. `timeout` ở Reactor giới hạn việc chờ tín hiệu trong publisher; với `Flux` nó còn có thể áp dụng tới **khoảng chờ giữa các tín hiệu**, không nhất thiết là một **deadline tổng cho toàn HTTP request**. Nếu cần deadline tổng, thiết kế ở tầng request/gateway và driver sao cho nhất quán.

**Không coi timeout là rollback.** Một query Cassandra đã gửi có thể vẫn hoàn tất ở server sau khi client ngừng chờ. Điều này đặc biệt quan trọng với ghi.

Ví dụ cách dùng retry **chỉ để cân nhắc với truy vấn đọc idempotent**:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Flux<EventSummary> retryingRead = service.recent(tenantId, day)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientReadFailure)
    );
~~~

`isTransientReadFailure` là predicate do ứng dụng định nghĩa dựa trên loại exception và khả năng phục hồi, **không retry tất cả exception**. Cần cân bằng retry của Reactor với retry policy của Java Driver/gateway để tránh request storm.

Đối với ghi:

- Counter increment và list append **không mặc định idempotent**.
- LWT/`IF` cần phân biệt `applied=false` sau retry với lần trước đã thành công nhưng mất phản hồi.
- Ghi TTL hoặc write timestamp mới khi replay có thể thay đổi hiệu ứng.
- Không retry lỗi cú pháp, schema, validation hay thiếu quyền.

**Anti-pattern nguy hiểm:**

~~~java
// SAI: outage Cassandra bị biến thành "không có sự kiện".
return repository.findRecent(tenantId, day)
    .onErrorResume(error -> Flux.empty());
~~~

Trả danh sách rỗng khi database không truy cập được có thể làm người dùng hoặc hệ thống đối soát hiểu sai dữ liệu. Hãy phân biệt **không tìm thấy** với **truy vấn thất bại**, trả mã lỗi HTTP thích hợp và ghi metrics.

## 17. WebFlux bảo mật và Reactor Context

Một HTTP request cần đi qua bước xác thực/ủy quyền reactive trước khi đọc partition của tenant. Trong hệ thống dùng Spring Security reactive:

- Xác thực Bearer token/cookie bằng filter chain tương thích WebFlux.
- Lấy principal từ **reactive security context**, không tin một `tenantId` đến từ query/header là đã được cấp quyền.
- Kiểm tra quyền **tại mỗi request**, kể cả request được gửi lại sau timeout.
- Tránh thư viện ACL chặn I/O trên event loop; nếu phải gọi DB/HTTP khác, chọn reactive client.
- Không đặt thông tin nhận dạng nhạy cảm vào log/tracing một cách tùy tiện.

**ThreadLocal không mặc nhiên đi theo một Reactor chain** khi nó chuyển thread. Nếu cần request ID, trace ID hoặc thông tin ngữ cảnh xuyên asynchronous boundary, dùng **Reactor Context** và tích hợp observability tương ứng, không tự suy từ tên thread.

Ví dụ minh họa ghi thêm request ID vào Reactor Context:

~~~java
Mono<EventRow> operation = repository.findById(key)
    .contextWrite(context -> context.put("requestId", requestId));
~~~

`contextWrite` giúp subscriber/upstream có thể truy cập context bằng các operator phù hợp như `deferContextual`. Nó **không tự biến requestId thành CQL bind parameter**, không thay thế propagation của framework tracing và không tạo authorization.

## 18. Đường đi non-blocking phải được kiểm tra ở nhiều cấp

Một chiến lược kiểm thử thực tế gồm ít nhất bốn mức:

| Mức kiểm thử | Công cụ | Điều có thể chứng minh | Điều chưa chứng minh |
| --- | --- | --- | --- |
| **Publisher unit test** | `StepVerifier` | Tín hiệu data/complete/error, thứ tự subscribe, security gate | Driver thực sự không chặn |
| **Controller test** | `WebTestClient` | Route, binding, JSON, HTTP status, Publisher được WebFlux subscribe | Cassandra/driver thật có hoạt động không |
| **Blocking detection** | BlockHound (khi tương thích) | Một số lời gọi blocking chạy trên non-blocking scheduler/thread | Mọi nguồn blocking đều được phát hiện |
| **Integration/load test** | Cassandra test cluster + WebFlux + metrics | Đường truy cập thật, timeout, paging, độ trễ, thread behavior | Không tự chứng minh mọi tình huống production |

**Mục tiêu là phủ toàn đường đi**, không chỉ kiểm tra một unit test gọi `StepVerifier.create(Flux.just(...))` rồi kết luận ứng dụng đã non-blocking.

## 19. StepVerifier: test publisher, sự kiện và subscription

Test service với repository/policy giả lập, dùng `PublisherProbe` để xác nhận publisher đọc Cassandra **chưa được subscribe trước khi WebFlux/service subscriber thực sự subscribe**.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class EventServiceTest {
    @Test
    void recentSubscribesAndMapsRows() {
        UUID tenant = UUID.randomUUID();
        LocalDate day = LocalDate.of(2026, 11, 25);
        UUID id = UUID.randomUUID();

        EventRepository repository = mock(EventRepository.class);
        ReactiveTenantAccess access = mock(ReactiveTenantAccess.class);
        EventRow row = mock(EventRow.class);
        EventKey key = mock(EventKey.class);

        when(row.getKey()).thenReturn(key);
        when(key.getEventId()).thenReturn(id);
        when(key.getOccurredAt()).thenReturn(
            Instant.parse("2026-11-25T08:30:00Z"));
        when(row.getEventType()).thenReturn("ORDER_PAID");
        when(row.getStatus()).thenReturn("PROCESSED");
        when(access.requireRead(tenant)).thenReturn(Mono.empty());

        PublisherProbe<EventRow> probe =
            PublisherProbe.of(Flux.just(row));
        when(repository.findRecent(tenant, day))
            .thenReturn(probe.flux());

        EventService service = new EventService(repository, access);
        Flux<EventSummary> publisher = service.recent(tenant, day);
        probe.assertWasNotSubscribed();

        StepVerifier.create(publisher)
            .assertNext(dto -> assertEquals(id, dto.eventId()))
            .verifyComplete();

        probe.assertWasSubscribed();
        verify(access).requireRead(tenant);
        verify(repository).findRecent(tenant, day);
    }
}
~~~

Test này xác minh **composition/lazy subscription và mapping** của đường service. Nó **không chứng minh Cassandra thật không chặn**, vì repository đang được mock và probe chỉ phát dữ liệu trong bộ nhớ. Đó là lý do phải có integration test và công cụ phát hiện blocking ở các mục sau.

### Test authorization chặn database trước khi query

Vì service dùng `Flux.defer`, có thể kiểm tra rằng khi policy từ chối quyền, repository không bị gọi:

~~~java
when(access.requireRead(tenant))
    .thenReturn(Mono.error(
        new org.springframework.security.access.AccessDeniedException(
            "Không có quyền")));

StepVerifier.create(service.recent(tenant, day))
    .expectError(
        org.springframework.security.access.AccessDeniedException.class)
    .verify();

verifyNoInteractions(repository);
~~~

Đoạn trên là **bổ sung cho một test case mới** có các biến `tenant`, `day`, `repository`, `access`, `service` được khởi tạo trước khi subscribe; cần thêm Spring Security dependency nếu dùng class `AccessDeniedException`. Có thể dùng một exception nội bộ tương đương trong unit test nếu ứng dụng chưa dùng Spring Security.

## 20. WebTestClient: kiểm tra HTTP endpoint

`WebTestClient` cho phép kiểm tra WebFlux request/response mà không cần biến publisher thành blocking list trong controller.

~~~java
import static org.mockito.Mockito.*;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;

class EventControllerTest {
    @Test
    void returnsJsonFromReactiveService() {
        UUID tenant = UUID.randomUUID();
        LocalDate day = LocalDate.of(2026, 11, 25);
        UUID eventId = UUID.randomUUID();

        EventService service = mock(EventService.class);
        when(service.recent(tenant, day)).thenReturn(Flux.just(
            new EventSummary(
                eventId,
                Instant.parse("2026-11-25T08:30:00Z"),
                "ORDER_PAID",
                "PROCESSED"
            )));

        WebTestClient client = WebTestClient
            .bindToController(new EventController(service))
            .build();

        client.get()
            .uri("/v1/tenants/{tenantId}/events?day={day}",
                 tenant, day)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].eventId")
            .isEqualTo(eventId.toString());
    }
}
~~~

Test này kiểm tra **routing, argument binding, HTTP status, JSON serialization** ở lớp controller. Cách `bindToController` không tự nạp mọi security filter hoặc cấu hình ứng dụng thật; cần test thêm **request không có token, token sai tenant, lỗi driver và latency** bằng application context phù hợp.

Nếu dùng `@WebFluxTest`, hãy biết đó là **test slice**; các bean Cassandra/security tùy biến có thể không được load trừ khi cấu hình rõ. Kiểm tra dependency Spring Boot test theo version của dự án.

## 21. BlockHound: phát hiện một số blocking call bị giấu

**BlockHound** là công cụ tùy chọn giúp phát hiện các lời gọi blocking đã biết chạy trên thread được đánh dấu non-blocking. Một smoke test độc lập:

~~~java
import org.junit.jupiter.api.Test;
import reactor.blockhound.BlockHound;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingDetectionTest {
    @Test
    void catchesSleepOnNonBlockingScheduler() {
        // Trong bộ test thật, cài BlockHound một lần từ sớm.
        BlockHound.install();

        Mono<String> blocking = Mono.fromCallable(() -> {
            Thread.sleep(10); // Cố ý để chứng minh phát hiện block.
            return "done";
        }).subscribeOn(Schedulers.parallel());

        StepVerifier.create(blocking)
            .expectError(BlockingOperationError.class)
            .verify();
    }
}
~~~

Ví dụ này **cố ý chứa `Thread.sleep` chỉ trong test**, không phải code production. BlockHound phải được khởi tạo đúng lúc và tương thích với JDK/Reactor/agent instrumentation. Một số JDK mới cần cờ JVM hoặc cấu hình plugin phù hợp; nếu BlockHound không cài được, **không diễn giải test bỏ qua như bằng chứng đường đi non-blocking**.

### Những điểm BlockHound không thay thế

- Không đo hiệu năng endpoint Cassandra thật.
- Không bảo đảm phát hiện mọi loại blocking library, native call hoặc CPU-bound operation.
- Không chứng minh rằng một query đã dùng partition key đúng hay replica khỏe mạnh.
- Không thay thế profiling, async thread dump, runtime metrics và load test.

**Đừng dùng cách kiểm tra tên thread một cách đơn giản** như `Thread.currentThread().getName().contains("reactor")` rồi kết luận mọi chỗ đều non-blocking. Reactor có thể chuyển scheduler hợp lệ; điều cần tìm là **lời gọi I/O chặn thật** trên non-blocking thread.

## 22. Integration test với Cassandra thật

Sau unit/controller tests, cần test đường đi:

~~~text
WebTestClient / HTTP thật
    -> WebFlux filters/security
    -> EventController
    -> EventService
    -> ReactiveCassandraRepository / Template
    -> Driver async
    -> Cassandra test cluster
    -> Response
~~~

Có thể dùng Testcontainers Cassandra hoặc một cluster test được quản lý. Quy trình:

1. **Khởi động cluster thử nghiệm**, chuẩn bị keyspace/bảng với schema đúng CQL, đưa dữ liệu fixture có nhiều tenant/ngày.
2. Chạy ứng dụng bằng cấu hình WebFlux/reactive và trỏ driver tới cluster test; kiểm tra local datacenter, credentials và schema action.
3. Gửi request của tenant có quyền, xác minh status 200, JSON, đúng thứ tự clustering và không rò dữ liệu tenant khác.
4. Gửi request tenant không được phép, xác minh 403 hoặc chính sách 404, **không truy vấn sai partition**.
5. Thử không có hàng, lỗi kết nối, timeout, replica chậm và dữ liệu TTL hết hạn.
6. Kiểm tra driver metrics, Netty event-loop latency, request concurrency và thread dump khi tải tăng.
7. Kiểm tra cancel/timeout/retry, bảo đảm không có lời gọi `block()`/`get()` nằm trên event loop.

**Mock `Mono.just(...)` không thay thế integration test**. Và ngay cả integration test thành công cũng không chứng minh hệ thống sẽ không block trong mọi trường hợp tải, lỗi mạng, payload lớn hoặc library phụ trợ.

### Một test môi trường thật phải đo những gì?

| Chỉ số | Vì sao cần? |
| --- | --- |
| HTTP p50/p95/p99 latency | Thấy đuôi trễ khi concurrent requests tăng |
| Event-loop execution delay/stall | Phát hiện thread xử lý request bị giữ quá lâu |
| Cassandra driver in-flight requests | Phát hiện saturation của connection/host |
| Driver request timeout/unavailable/retry | Biết khi nào service đang quá tải cluster |
| Active subscriptions và cancel | Xem API/client ngắt kết nối bất thường |
| BoundedElastic active/queued tasks | Phát hiện legacy blocking đang bị đẩy sang scheduler |
| Số partition, page size, row payload | Kiểm soát chi phí query và memory |
| JVM heap, GC, CPU | Phân biệt blocking I/O với CPU hoặc allocation pressure |

Không log access token, cursor nhạy cảm hoặc toàn bộ dữ liệu cá nhân chỉ để debug slow requests. Dùng request ID/tracing được kiểm soát để liên kết các sự kiện.

## 23. Khi load test, tránh những kết luận sai

Giả sử WebFlux giữ throughput khá tốt ở 100 request đồng thời nhưng tăng latency mạnh tại 5.000 request. Nguyên nhân có thể là:

- **Hot partition** ở Cassandra; nhiều request tranh cùng nhóm replica.
- **Throttling/queueing của driver**; số kết nối/in-flight query đạt ngưỡng.
- **Blocking call** ở middleware security/logging/caching mà unit test bỏ sót.
- **CPU-bound JSON serialization**, payload lớn hoặc `collectList()` ngốn heap.
- **Tombstone scanning** do TTL/xóa làm truy vấn đọc chậm.
- **Fan-out** từ `flatMap` trên nhiều ngày mà không giới hạn concurrency.
- **Retry storm** khi Cassandra timeout hoặc một host bị lỗi.

Chọn hướng khắc phục theo số liệu: tối ưu partition key/bucket, projection, paging, concurrency limit, timeout, cache, pooling, tracing hoặc thay thư viện blocking. **Tăng thread pool không làm Cassandra partition nóng biến mất**; thêm `publishOn` cũng không tự làm query nhanh hơn.

## 24. Những anti-pattern phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Trả `Mono.just(cassandraTemplate.selectOneById(...))` | Phép DB đồng bộ đã chạy trước khi tạo publisher | Dùng `ReactiveCassandraTemplate` hoặc async adapter |
| Gọi `block()` trong controller | Chặn request thread, dễ làm nghẽn event loop | Trả publisher cho WebFlux |
| Gọi `subscribe()` trong service | Side effect chạy tách khỏi HTTP lifecycle, lỗi/cancel khó quản lý | Ghép bằng `flatMap`/`then` rồi trả publisher |
| Gọi `Thread.sleep()` trong `map` | Chặn thread phát tín hiệu | Dùng timer non-blocking hoặc scheduler riêng cho legacy |
| Nghĩ `Flux` đọc vô hạn là an toàn | Heap/driver/network/partition bị quá tải | Giới hạn query, page size, concurrency và cursor |
| Bỏ security trước repository | Có thể đọc dữ liệu tenant khác | Reactive authorization trước truy vấn và binding đúng |
| Dùng `onErrorResume(... Flux.empty())` cho mọi lỗi | Outage bị hiểu thành không có dữ liệu | Phân loại lỗi, trả HTTP status phù hợp |
| Retry mọi lỗi database | Tăng tải khi outage; ghi không idempotent bị lặp | Predicate theo loại lỗi và semantics |
| `collectList()` cho hàng triệu hàng | Tích lũy tất cả kết quả, ngốn heap | Pagination/streaming và giới hạn hàng |
| Dùng `CassandraTemplate` đồng bộ dù có reactive API | Tốn thread, giảm khả năng mở rộng | `ReactiveCassandraTemplate` |
| Chỉ test `Flux.just(...)` rồi tuyên bố non-blocking | Không có đường driver thật | WebTestClient + integration + BlockHound/metrics |
| Nhầm `LIMIT` với page size | Không thể đọc quá tổng limit dù còn state | Thiết kế cursor/fetch size rõ |
| Dùng `@Transactional` và mong ACID đa bảng | CQL Cassandra không có transaction SQL tổng quát | Thiết kế LWT/idempotency/reconciliation nếu cần |

## 25. Checklist triển khai WebFlux + Reactive Cassandra

- [ ] Runtime HTTP thực sự là WebFlux trong cấu hình đang dùng.
- [ ] Dependency Cassandra dùng starter reactive, repository/template reactive.
- [ ] Entity và primary key khớp CQL; query dùng đủ partition key.
- [ ] Danh sách chọn projection nhỏ, giới hạn hàng, page size và phạm vi ngày/bucket.
- [ ] Controller/service trả `Mono`/`Flux`, không gọi `block()`, `join()` hay `subscribe()` tùy tiện.
- [ ] Authorization/tenant validation nằm trước truy vấn, dùng principal đã xác thực.
- [ ] Không có CassandraTemplate, JDBC, RestTemplate hoặc filesystem blocking trên event loop.
- [ ] Chỉ cô lập legacy blocking vào `boundedElastic` với giới hạn và timeout.
- [ ] Có backpressure/concurrency limit và phân biệt driver paging với Reactive Streams demand.
- [ ] Đã thiết kế error mapping, timeout và retry phù hợp đọc/ghi.
- [ ] Không coi cancellation hay timeout là rollback một mutation Cassandra.
- [ ] Test service bằng StepVerifier/PublisherProbe và controller bằng WebTestClient.
- [ ] Test authorization bị từ chối không truy vấn DB, kiểm tra cross-tenant.
- [ ] Có integration test qua Cassandra thật, kiểm tra blocking instrumentation và metrics.
- [ ] Quan sát p95/p99, event-loop stalls, in-flight requests, retry, memory, tombstone.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Controller trả `Flux<EventRow>` có đủ chứng minh toàn API non-blocking không?

**Đáp án:** Không. Nếu service/security/template gọi blocking I/O, đường đi vẫn chặn event loop. Cần kiểm tra toàn tuyến.

**Câu 2.** Vì sao không gọi `subscribe()` trực tiếp trong service?

**Đáp án:** Vì WebFlux phải quản lý subscription theo HTTP lifecycle. Tự subscribe tạo một nhánh xử lý riêng khó liên kết lỗi, cancel/backpressure và kết quả với response.

**Câu 3.** `ReactiveCassandraRepository` khác `CassandraRepository` ở đặc điểm quan trọng nào?

**Đáp án:** Repository reactive trả publisher `Mono`/`Flux` và sử dụng đường I/O bất đồng bộ; repository đồng bộ có các lời gọi trả kết quả trực tiếp có thể chặn thread gọi.

**Câu 4.** Có thể dùng `CassandraTemplate.selectOneById(...)` trong `Mono.just(...)` để làm nó non-blocking không?

**Đáp án:** Không. Đối số của `Mono.just(...)` được tính trước khi publisher hình thành. Dùng `ReactiveCassandraTemplate` hoặc adapter async thực sự.

**Câu 5.** `StepVerifier` với mock repository có chứng minh driver Cassandra không block không?

**Đáp án:** Không. Nó kiểm tra tín hiệu/composition của publisher trong test. Cần integration test và detection/metrics để đánh giá driver và middleware.

**Câu 6.** Reactive backpressure có nghĩa `request(1)` chỉ fetch đúng một row trên mạng không?

**Đáp án:** Không. Driver có cơ chế fetch pages/buffering; nhu cầu tín hiệu không ánh xạ 1:1 với request Cassandra.

**Câu 7.** Khi client cancel hoặc Reactor timeout một ghi, có thể khẳng định mutation chưa tới Cassandra không?

**Đáp án:** Không. Request có thể đã được coordinator/replica xử lý trước khi client ngừng chờ. Retry cần idempotency/reconciliation.

**Câu 8.** Khi phải dùng một thư viện file/HTTP blocking, làm gì?

**Đáp án:** Ưu tiên thay bằng non-blocking API; nếu chưa thể, cô lập trong `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và giới hạn concurrency/timeout.

**Câu 9.** Tại sao `LIMIT 100` trong CQL không thay thế cursor pagination?

**Đáp án:** Nó giới hạn tổng số hàng của câu truy vấn, không cho phép tiếp tục tới hàng thứ 101. Cursor cần state/khóa tiếp tục và bảo vệ phạm vi truy vấn.

**Câu 10.** Khi API WebFlux chậm, có nên tăng event-loop threads ngay?

**Đáp án:** Không mặc định. Phải đo blocking call, driver, hot partition, payload, CPU, GC, tombstone, fan-out và retry trước khi tối ưu đúng nút thắt.

---

**Ghi nhớ:** tích hợp **Spring WebFlux + Spring Data Cassandra reactive** nghĩa là giữ **đường xử lý không chặn từ HTTP tới Cassandra async driver**, không chỉ đổi chữ ký method sang `Mono` hoặc `Flux`. Dùng `ReactiveCassandraRepository`/`ReactiveCassandraTemplate`, ghép pipeline bằng Reactor operators, kiểm tra quyền tenant trước truy vấn, kiểm soát partition/paging/concurrency, không chặn event loop và không retry mutation Cassandra thiếu idempotency. Muốn xác minh kỹ thuật, cần **StepVerifier cho tín hiệu**, **WebTestClient cho HTTP**, **BlockHound/profiling cho blocking** và **integration/load test với Cassandra thật**; không một bài test đơn lẻ nào thay thế toàn bộ kiểm chứng end-to-end.
