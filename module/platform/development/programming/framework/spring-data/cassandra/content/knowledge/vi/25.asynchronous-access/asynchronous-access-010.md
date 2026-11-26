# Chuyển giữa CompletableFuture và Reactor tại ranh giới rõ ràng

Trong ứng dụng **Spring Data Cassandra**, đôi khi một tầng dùng **Java Driver bất đồng bộ** với `CompletionStage`/`CompletableFuture`, trong khi tầng HTTP hoặc nghiệp vụ dùng **Project Reactor** với `Mono`/`Flux`. Một thành phần khác lại yêu cầu trả `CompletableFuture` để tương thích với thư viện Java không dùng Reactor. Ta có thể chuyển đổi giữa các kiểu này, nhưng **chuyển đúng kiểu dữ liệu không tự bảo đảm đúng vòng đời thực thi**.

Sự khác biệt quan trọng là: **một tác vụ `CompletableFuture` thường đã được khởi động trước khi được trao cho người gọi**, còn **một publisher Reactor thường là công thức thực thi lười** được kích hoạt khi có subscriber. Nếu tạo future quá sớm, một câu CQL có thể chạy trước khi xác thực yêu cầu; nếu subscribe nhiều lần, cùng mutation có thể được gửi nhiều lần; nếu timeout rồi retry mà không xét idempotency, một thao tác counter có thể bị cộng hai lần.

Bài thuộc chương **Truy cập bất đồng bộ** của module **SPRING_DATA_CASSANDRA**. Ta sẽ thiết kế **ranh giới chuyển đổi rõ ràng**, kết hợp `CqlSession.executeAsync`, Spring Data reactive repository/template, `Mono.fromCompletionStage`, `Mono.toFuture`, phân trang bất đồng bộ, quản lý lỗi và kiểm thử. Mục đích là duy trì các nguyên tắc **partition key, consistency, paging và kiểm soát hiệu năng** ngay cả khi API chuyển giữa hai hệ bất đồng bộ.

## 1. Khi nào ứng dụng cần chuyển đổi?

Một kiến trúc thực tế có thể gồm:

~~~text
              WebFlux Controller
                 Mono / Flux
                     |
                     v
               Reactive Service
                     |
          +----------+----------+
          |                     |
          v                     v
  ReactiveCassandraRepository   Adapter đến thư viện Java
  ReactiveCassandraTemplate     CompletionStage / CompletableFuture
          |                     |
          +----------+----------+
                     |
                     v
              Cassandra cluster
~~~

Hoặc hệ thống có Spring MVC/Java SDK cũ dùng `CompletableFuture`, nhưng một service nội bộ mới dùng `ReactiveCassandraTemplate`.

Nguyên tắc thiết kế là **chuyển đổi một lần tại ranh giới giữa hai hợp đồng API**, không liên tục đổi `Mono → Future → Mono` trong từng method vì điều đó làm khó kiểm soát subscription, cancellation, tracing và số request Cassandra.

| Tầng | Hợp đồng tự nhiên | Hướng nên làm |
| --- | --- | --- |
| Java Driver 4.x bất đồng bộ | `CompletionStage<AsyncResultSet>` | Đổi sang `Mono` tại adapter khi service dùng Reactor |
| Spring Data Cassandra reactive | `Mono<T>`, `Flux<T>` | Giữ Reactor xuyên service/controller reactive |
| Thư viện Java chỉ nhận `CompletionStage<T>` | `CompletionStage<T>` | Chuyển từ `Mono` bằng `toFuture()` tại biên |
| Spring Data Cassandra đồng bộ | Giá trị Java hoặc `Optional<T>` | Không giả vờ non-blocking; dùng API reactive hoặc cách ly blocking |
| Batch/stream xử lý nhiều hàng | `Flux<T>` hoặc các page async | Thiết kế số trang, backpressure và giới hạn tải rõ ràng |

## 2. Khác nhau giữa CompletionStage, CompletableFuture, Mono và Flux

| Loại | Vai trò | Đặc tính cần nhớ |
| --- | --- | --- |
| `CompletionStage<T>` | Hợp đồng cho một kết quả bất đồng bộ và các bước tiếp nối | Có thể đã chạy; không đòi đối tượng phải là `CompletableFuture` cụ thể |
| `CompletableFuture<T>` | Một cách triển khai `Future` và `CompletionStage` | Có thể hoàn thành, thất bại, bị hủy; `get()/join()` là blocking |
| `Mono<T>` | Publisher 0 hoặc 1 giá trị | Thường cold/lazy; hoàn thành rỗng là một trạng thái hợp lệ |
| `Flux<T>` | Publisher 0..N giá trị | Hỗ trợ demand/backpressure trong pipeline |

**Hai khác biệt quan trọng:**

1. `CompletionStage` không phải publisher có `request(n)`. Khi một future đã được tạo, downstream Reactor **không điều khiển số request DB** đã khởi động bằng backpressure.
2. `Mono.empty()` và `CompletableFuture.completedFuture(null)` có thể được ánh xạ thành **cùng sự kiện hoàn thành không có giá trị** trong Reactor. Nếu nghiệp vụ phân biệt *không tìm thấy* và *thành công với null*, cần một kiểu kết quả rõ ràng như `Optional<T>` hoặc record.

**Một thay đổi kiểu trả về không làm câu lệnh blocking trở thành non-blocking.** `Mono.just(template.selectOne(...))` vẫn thực hiện truy vấn đồng bộ trước khi tạo publisher. Ta sẽ xem cách tránh lỗi này ở mục sau.

## 3. Dữ liệu minh họa: đọc sự kiện theo một partition

Giả sử API lấy sự kiện của một tenant theo ngày, sắp xếp mới nhất trước:

~~~sql
CREATE KEYSPACE IF NOT EXISTS activity_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS activity_ks.events_by_tenant_day (
    tenant_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (
    event_time DESC, event_id DESC
);
~~~

Schema này dùng **partition key `(tenant_id, event_day)`** và clustering columns `event_time`, `event_id`. Ví dụ này minh họa một datacenter `dc1` có RF=3; cluster thật phải dùng topology/replication phù hợp và quản lý schema qua migration.

Truy vấn danh sách nên chỉ lấy những cột cần thiết:

~~~sql
SELECT event_time, event_id, event_type
FROM activity_ks.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?;
~~~

Ở đây có đủ partition key và không cần `ALLOW FILTERING`. **Đổi từ synchronous sang asynchronous không làm một truy vấn thiếu partition key bỗng trở nên hiệu quả**. Nếu một ngày có quá nhiều sự kiện, cần xem xét bucket nhỏ hơn, phân trang, projection và kích thước partition.

## 4. Java Driver bất đồng bộ trả CompletionStage

Java Driver 4.x có `CqlSession.executeAsync(...)` trả về `CompletionStage<AsyncResultSet>`. Thực thi bất đồng bộ không có nghĩa caller phải tạo thread riêng cho mỗi request.

~~~java
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class EventDriverClient {
    private final CqlSession session;
    private final PreparedStatement query;

    public EventDriverClient(CqlSession session) {
        this.session = session;
        this.query = session.prepare("""
            SELECT event_time, event_id, event_type
            FROM activity_ks.events_by_tenant_day
            WHERE tenant_id = ? AND event_day = ?
            """);
    }

    public CompletionStage<AsyncResultSet> executeFirstPage(
            UUID tenantId, LocalDate day, int fetchSize) {
        if (fetchSize < 1 || fetchSize > 100) {
            throw new IllegalArgumentException("fetchSize ngoài phạm vi");
        }
        BoundStatement statement = query.bind(tenantId, day)
                .setPageSize(fetchSize);
        return session.executeAsync(statement);
    }
}
~~~

Phương thức này **bắt đầu gửi statement khi được gọi**, và trả lại một stage sẽ hoàn thành sau đó. Trong thực tế, các lỗi có thể xuất hiện **đồng bộ** (ví dụ validate hoặc bind sai kiểu) hoặc **bất đồng bộ** qua stage thất bại.

`AsyncResultSet` đại diện cho **trang dữ liệu hiện tại**, không nhất thiết toàn bộ kết quả. Để đọc trang kế tiếp, dùng `hasMorePages()` và `fetchNextPage()`; tuyệt đối không giả định một lần `executeAsync` đã trả hết mọi row của partition.

## 5. Cách không đúng: tạo Future trước khi tạo Mono

Mã sau chuyển kiểu nhưng làm mất tính lazy:

~~~java
CompletionStage<AsyncResultSet> started =
        eventClient.executeFirstPage(tenantId, day, 25);

Mono<AsyncResultSet> mono =
        Mono.fromCompletionStage(started);
~~~

Ở dòng đầu, Cassandra request đã được khởi tạo **trước khi có subscriber**. Trong một method controller hoặc service, điều này có thể làm request chạy quá sớm; tạo lại Mono từ cùng stage sau đó không tạo một request mới khi subscribe lại, nhưng cũng **không thể trì hoãn** request đã gửi.

Một lỗi khác:

~~~java
Mono<CompletionStage<AsyncResultSet>> wrong =
        Mono.just(eventClient.executeFirstPage(tenantId, day, 25));
~~~

Đoạn này phát ra **đối tượng stage** như một giá trị, không đợi kết quả `AsyncResultSet`; downstream sẽ phải xử lý lồng thêm một lớp async. `Mono.just(...)` cũng đã gọi method gửi Cassandra trước khi publisher được subscribe.

## 6. CompletionStage → Mono: dùng supplier tại ranh giới

Nên dùng overload nhận `Supplier<CompletionStage<T>>`:

~~~java
import reactor.core.publisher.Mono;

public Mono<AsyncResultSet> firstPage(
        UUID tenantId, LocalDate day, int fetchSize) {
    return Mono.fromCompletionStage(
        () -> eventClient.executeFirstPage(
            tenantId, day, fetchSize
        )
    );
}
~~~

Với **Reactor version hỗ trợ supplier overload**, cách này giữ việc gọi driver trong **lúc subscribe**:

~~~text
Controller tạo Mono
      |
      | (chưa executeAsync)
      v
Subscriber bắt đầu
      |
      v
Supplier được gọi -> executeAsync(...)
      |
      v
Stage completed -> Mono onNext/onComplete
               hoặc Mono onError
~~~

Một cách tường minh khác:

~~~java
public Mono<AsyncResultSet> firstPageDeferred(
        UUID tenantId, LocalDate day, int fetchSize) {
    return Mono.defer(() ->
        Mono.fromCompletionStage(
            eventClient.executeFirstPage(
                tenantId, day, fetchSize
            )
        )
    );
}
~~~

`Mono.defer(...)` làm cùng mục tiêu: **khởi tạo một stage mới theo từng subscription**. Không cần kết hợp cả hai lớp defer cho cùng mục đích.

### Mỗi subscription có thể gửi một CQL request mới

~~~java
Mono<AsyncResultSet> page = firstPage(tenantId, day, 25);

page.subscribe();   // request Cassandra thứ nhất
page.subscribe();   // request Cassandra thứ hai
~~~

Đây là hệ quả quan trọng của publisher cold. Với **SELECT idempotent**, nhiều lần subscribe có thể chỉ tốn thêm I/O; với **counter increment hoặc INSERT có side effects**, nhiều subscription có thể tạo tác động ngoài ý muốn.

Không gọi `subscribe()` bên trong service rồi lại trả `Mono` để controller subscribe lần nữa. Controller/WebFlux runtime là nơi giữ quyền điều khiển subscription của một HTTP request.

## 7. Từ AsyncResultSet thành Mono của một trang

Ví dụ DTO:

~~~java
import java.time.Instant;
import java.util.UUID;

public record EventSummary(
    UUID eventId,
    Instant eventTime,
    String eventType
) {}
~~~

Ta muốn trả **chỉ trang đầu** một cách có chủ đích:

~~~java
import java.util.ArrayList;
import java.util.List;
import reactor.core.publisher.Mono;
import com.datastax.oss.driver.api.core.cql.Row;

public Mono<List<EventSummary>> listFirstPage(
        UUID tenantId, LocalDate day, int fetchSize) {

    return Mono.fromCompletionStage(() ->
        eventClient.executeFirstPage(tenantId, day, fetchSize)
    ).map(result -> {
        List<EventSummary> items = new ArrayList<>();
        for (Row row : result.currentPage()) {
            items.add(new EventSummary(
                row.getUuid("event_id"),
                row.getInstant("event_time"),
                row.getString("event_type")
            ));
        }
        return List.copyOf(items);
    });
}
~~~

Đây là phương thức nhận một page và **chủ động bỏ qua các page sau**, vì tên `listFirstPage` nói rõ hợp đồng. Đối với API public hỗ trợ phân trang, cần trả thêm paging state/cursor chứ không để client tưởng đã lấy hết dữ liệu.

Mã mapping chạy trong quá trình xử lý response; chỉ nên thực hiện phép chuyển đổi nhẹ, **không chạy blocking I/O hoặc CPU-heavy transform** ngay trên thread callback/event loop của driver.

## 8. Từ CompletionStage<AsyncResultSet> thành Flux nhiều trang

Nếu nhu cầu là xử lý tất cả hàng (trong **phạm vi đã giới hạn**), có thể nối các page bằng `fetchNextPage()`:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public Flux<EventSummary> streamEvents(
        UUID tenantId, LocalDate day, int fetchSize) {

    return Mono.fromCompletionStage(() ->
        eventClient.executeFirstPage(tenantId, day, fetchSize)
    )
    .expand(result ->
        result.hasMorePages()
            ? Mono.fromCompletionStage(result::fetchNextPage)
            : Mono.empty()
    )
    .concatMapIterable(AsyncResultSet::currentPage)
    .map(row -> new EventSummary(
        row.getUuid("event_id"),
        row.getInstant("event_time"),
        row.getString("event_type")
    ));
}
~~~

**Giới hạn của ví dụ:** nó duyệt toàn bộ các page nếu downstream tiếp tục yêu cầu dữ liệu. `expand` là cách minh họa chuỗi page; không dùng trực tiếp để trả toàn bộ lịch sử không giới hạn cho client. Với API paginated, tốt hơn là **mỗi request chỉ lấy một page và phát một continuation cursor được bảo vệ**.

`Flux` có backpressure ở mức publisher, nhưng **không bảo đảm mỗi yêu cầu `request(1)` của downstream chỉ phát sinh đúng một row-level Cassandra request**. Driver fetch theo page, có bộ đệm và việc request page sau còn phụ thuộc operator/prefetch. Nên đo memory, số page đang được fetch và giới hạn số hàng/partition.

Một pipeline xử lý có ngưỡng nghiệp vụ có thể dùng `take(maxItems)`, nhưng **`take()` không thay thế việc hạn chế kích thước query/partition và cancellation của request đã gửi**.

## 9. Mono và Flux từ Spring Data Cassandra reactive

Nếu đã có **Spring Data reactive stack**, thường không cần đi qua CompletableFuture chỉ để dùng Cassandra:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
~~~

Repository reactive:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import reactor.core.publisher.Mono;

public interface ReactiveEventRepository
        extends ReactiveCassandraRepository<EventRow, EventKey> {
}

public Mono<EventRow> findByFullKey(
        EventKey key, ReactiveEventRepository repository) {
    return repository.findById(key);
}
~~~

`EventKey` là class composite key được ánh xạ tới primary key của `events_by_tenant_day`; `EventRow` là entity tương ứng. Constructor/mapping chi tiết cần thống nhất với bảng thực tế và có thể dùng `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@PrimaryKey` như các bài entity mapping.

`ReactiveCassandraTemplate` cũng trả publisher reactive theo API tương ứng:

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraTemplate;
import reactor.core.publisher.Mono;

public Mono<EventRow> load(
        ReactiveCassandraTemplate template, EventKey key) {
    return template.selectOneById(key, EventRow.class);
}
~~~

**Không chuyển `Mono` sang Future rồi lại sang `Mono`** giữa repository và WebFlux controller. Một chuỗi Reactor thuần giúp giữ cùng cơ chế subscription, context, cancellation và error propagation.

## 10. Reactor → CompletableFuture tại biên thư viện Java

Khi một API Java bên ngoài **buộc trả `CompletionStage` hoặc `CompletableFuture`**, ta có thể dùng `Mono.toFuture()`:

~~~java
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.NoSuchElementException;
import reactor.core.publisher.Mono;

public CompletableFuture<EventRow> findAsFuture(
        EventKey key, ReactiveEventRepository repository) {

    return repository.findById(key)
        .switchIfEmpty(Mono.error(
            new NoSuchElementException("Không tìm thấy event")
        ))
        .toFuture();
}
~~~

**Điểm mấu chốt:** `toFuture()` **subscribe ngay** để thực thi publisher. Phương thức này không trả một “future lười” đang chờ ai đó subscribe; khi được gọi, nó kích hoạt truy vấn reactive để đi tới kết quả.

Nếu upstream `Mono` phát một giá trị, future thành công với giá trị đó. Nếu upstream lỗi, future thất bại. Nếu upstream hoàn thành rỗng mà không dùng `switchIfEmpty`, future có thể hoàn thành với `null`, dễ làm tầng Java hiểu sai thành công/không tìm thấy.

Một API cho phép kết quả tùy chọn có thể trả kiểu `CompletionStage<Optional<EventRow>>`:

~~~java
public CompletableFuture<Optional<EventRow>> findOptional(
        EventKey key, ReactiveEventRepository repository) {
    return repository.findById(key)
        .map(Optional::of)
        .defaultIfEmpty(Optional.empty())
        .toFuture();
}
~~~

Ở ví dụ này cần import `java.util.Optional`. Dùng `Optional` giúp hợp đồng API phân biệt “không có hàng” với một lỗi thực thi truy vấn.

## 11. Flux → Future: đừng materialize vô hạn

`Flux<T>` có thể trả nhiều phần tử, trong khi `CompletableFuture<T>` chỉ mang **một kết quả**. Muốn đổi, trước tiên xác định **kết quả duy nhất mong muốn**.

~~~java
// Muốn tối đa 25 event.
CompletableFuture<List<EventSummary>> pageFuture =
    eventFlux
        .take(25)
        .collectList()
        .toFuture();
~~~

Hoặc lấy đúng phần tử đầu tiên:

~~~java
CompletableFuture<EventSummary> firstFuture =
    eventFlux.next()
        .switchIfEmpty(Mono.error(
            new NoSuchElementException("Không có sự kiện")
        ))
        .toFuture();
~~~

Không dùng `eventFlux.collectList().toFuture()` trên một chuỗi không giới hạn chỉ để “đổi Flux thành future”. Cách đó có thể giữ rất nhiều row trong heap và đọc hết các page Cassandra. Với luồng vô hạn, future có thể không bao giờ hoàn thành.

**Số lượng kết quả và cách kết thúc luồng** phải là một phần hợp đồng API của ranh giới chuyển đổi.

## 12. Giá trị null, Mono.empty và CompletionStage<Void>

Một `Mono<T>` không phát `onNext(null)`; không có giá trị được biểu diễn bằng **hoàn thành rỗng**. Nhưng `CompletableFuture<T>` có thể hoàn thành thành công với `null`:

~~~java
CompletableFuture<String> future =
    CompletableFuture.completedFuture(null);

Mono<String> publisher = Mono.fromCompletionStage(() -> future);
// Hoàn thành rỗng, không phát chuỗi null.
~~~

| Trạng thái | Ý nghĩa nên định nghĩa tại biên |
| --- | --- |
| `Mono<EventRow>` phát một item | Tìm thấy bản ghi |
| `Mono.empty()` | Không tìm thấy, không phải lỗi DB |
| `Mono.error(ex)` | Có lỗi cần phản hồi/ghi log |
| `CompletionStage<Optional<EventRow>>` | Có/không có bản ghi được biểu diễn tường minh |
| `CompletionStage<Void>` | Chỉ quan tâm hoàn thành/thất bại |

Đổi một lệnh ghi sang tín hiệu chỉ quan tâm hoàn thành:

~~~java
public Mono<Void> write(BoundStatement statement) {
    return Mono.fromCompletionStage(
        () -> session.executeAsync(statement)
    ).then();
}
~~~

`then()` bỏ `AsyncResultSet` sau khi stage hoàn tất, nhưng **không nuốt lỗi**. Nếu cần xác định cập nhật điều kiện `IF` có được áp dụng, không dùng `then()` trước khi đã kiểm tra trường `[applied]`.

Không dùng `onErrorResume(ex -> Mono.empty())` để biến mọi lỗi Cassandra thành “không có hàng”; nó khiến timeout/unavailable trông giống dữ liệu thực sự không tồn tại.

## 13. Truyền lỗi giữa hai mô hình bất đồng bộ

Khi `CompletionStage` thất bại, Reactor phát `onError`:

~~~java
public Mono<EventRow> loadEvent(UUID id) {
    return Mono.fromCompletionStage(
        () -> legacyEventClient.loadAsync(id)
    ).switchIfEmpty(Mono.error(
        new NoSuchElementException("Không tìm thấy event")
    ));
}
~~~

`legacyEventClient.loadAsync(id)` là API giả định trả `CompletionStage<EventRow>`. Một stage có thể thất bại với nguyên nhân từ driver; tại một số ranh giới Future, lỗi có thể được bọc bởi `CompletionException` hoặc `ExecutionException`. Cần phân loại nguyên nhân thật, không mặc định mọi lỗi cùng một lớp.

Đường ngược lại:

~~~java
CompletableFuture<EventRow> future =
    reactiveRepository.findById(key)
        .switchIfEmpty(Mono.error(
            new NoSuchElementException("Event not found")
        ))
        .toFuture();
~~~

`Mono.error` làm future hoàn thành với lỗi, không trả một `EventRow` giả. Nếu caller dùng `join()`/`get()`, nó cần xử lý các exception wrapper tương ứng.

**Không gọi `join()` hay `get()` trong WebFlux event loop hoặc callback của Cassandra driver.** Hai method đó có thể chặn thread và làm giảm khả năng phục vụ các request khác.

## 14. Cancellation không phải rollback Cassandra

Reactor hỗ trợ tín hiệu **cancel**, ví dụ client HTTP đóng kết nối hoặc pipeline đã nhận đủ phần tử. `CompletableFuture` hỗ trợ `cancel(...)`. Tuy nhiên một mutation Cassandra có thể đã đến coordinator trước khi client ngừng đợi.

~~~text
HTTP client đóng kết nối
       |
       v
Reactor subscriber bị cancel
       |
       v
Adapter ngừng quan tâm kết quả
       |
       v
Cassandra request có thể vẫn tiếp tục ở replica
~~~

**Không có bảo đảm rằng hủy subscriber hoặc future sẽ rollback `INSERT/UPDATE/DELETE`.** Với SELECT, cancellation có thể tránh một số fetch tiếp theo, nhưng request đã gửi cũng có thể vẫn tiêu tốn tài nguyên. Propagation của cancellation từ Reactor sang future phụ thuộc overload và implementation. Reactor có overload `Mono.fromFuture(future, true)` ở những phiên bản hỗ trợ để **suppress cancellation** xuống future; nó không phải một cách để điều khiển transaction server.

Đối với thao tác ghi quan trọng, cần **command ID ổn định**, chính sách retry có kiểm soát, kiểm tra trạng thái sau kết quả không chắc chắn và reconciliation. Đặc biệt, counter increment **không idempotent** và rất dễ đếm đôi khi client tự retry sau timeout/cancel.

## 15. Timeout phía Reactor và timeout của driver

Ví dụ giới hạn thời gian quan sát một trang:

~~~java
import java.time.Duration;

public Mono<List<EventSummary>> readWithTimeout(
        UUID tenantId, LocalDate day) {
    return listFirstPage(tenantId, day, 25)
        .timeout(Duration.ofSeconds(2));
}
~~~

`timeout` ở Reactor giới hạn **thời gian subscriber đợi tín hiệu**. Nó có thể phát lỗi và cancel upstream; không thể mặc nhiên chứng minh query Cassandra đã ngừng. Driver còn có request timeout và retry policy riêng.

| Tầng | Vai trò |
| --- | --- |
| HTTP deadline | Giới hạn thời gian request của client |
| Reactor `timeout` | Giới hạn thời gian pipeline phát tín hiệu |
| Java Driver timeout | Giới hạn request đến Cassandra theo driver |
| Bounded concurrency | Giới hạn số request in-flight |
| Retry deadline | Chặn chuỗi thử lại kéo dài không kiểm soát |

Các ngưỡng phải phối hợp với latency SLO; hai giây chỉ là ví dụ. Một query đã timeout ở Reactor vẫn có thể tiêu hao tài nguyên phía Cassandra, vì vậy cần đo **in-flight requests**, quá tải và các lần retry mới.

## 16. Retry tạo subscription mới: idempotency là bắt buộc

Với supplier `Mono.fromCompletionStage(() -> executeAsync(...))`, `retryWhen(...)` sẽ subscribe lại và có thể **gửi một CQL request mới**. Ví dụ chỉ dùng với một **truy vấn đọc idempotent**:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

public Mono<List<EventSummary>> readRetryable(
        UUID tenantId, LocalDate day) {
    return listFirstPage(tenantId, day, 25)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientReadFailure));
}
~~~

`isTransientReadFailure(Throwable)` là hàm do ứng dụng triển khai, nhận diện những lỗi thật sự có thể thử lại. Không retry sai cú pháp CQL, sai schema hoặc lỗi authorization.

**Không sao chép tùy tiện pattern retry sang mutation không idempotent**, chẳng hạn:

~~~java
Mono.fromCompletionStage(() -> counterDao.addOneAsync(...))
    .retryWhen(Retry.backoff(3, Duration.ofMillis(100)));
~~~

Nếu lần `+1` đầu đã được Cassandra thực hiện nhưng phản hồi thất lạc, lần thử kế tiếp có thể tăng số đếm lần nữa. Tương tự phải xem xét list append, LWT, side effects ngoài Cassandra và write timestamp/TTL của những ghi cạnh tranh.

Ngay cả với SELECT, retry quá nhiều có thể làm cluster đang lỗi càng quá tải. Cần hạn chế số lần, tổng deadline và dùng backoff.

## 17. Blocking CassandraTemplate không trở thành non-blocking vì được bọc bằng Mono

Ví dụ **sai**:

~~~java
public Mono<EventRow> wrong(EventKey key) {
    return Mono.just(
        blockingRepository.findById(key).orElseThrow()
    );
}
~~~

Lệnh `findById` chạy **trước khi có subscription**, vẫn chặn thread đang gọi method, có thể là event loop của WebFlux.

Nếu phải tích hợp một API **blocking** và chưa thể chuyển sang reactive:

~~~java
import reactor.core.scheduler.Schedulers;

public Mono<EventRow> loadFromBlockingRepository(EventKey key) {
    return Mono.fromCallable(() ->
        blockingRepository.findById(key)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .flatMap(Mono::justOrEmpty);
}
~~~

Ở đây repository trả `Optional<EventRow>`; `boundedElastic` cách ly việc blocking khỏi event loop với tài nguyên được quản lý. **I/O vẫn là blocking**, vì vậy đây là giải pháp chuyển tiếp. Khi có thể, ưu tiên `ReactiveCassandraRepository`/`ReactiveCassandraTemplate` hoặc Java Driver async rồi bridge ở adapter.

Tránh dùng `CompletableFuture.supplyAsync(blockingCall)` trên common pool không được quản trị, `subscribeOn(Schedulers.parallel())` cho blocking I/O hoặc gọi `block()/join()` để lấy kết quả giữa một pipeline Reactor.

## 18. Reactor Context không tự đi theo callback CompletionStage

Reactor có **Context** theo subscription, nhưng Java `CompletionStage` có thể thực hiện callback trên thread khác. `ThreadLocal`, MDC hoặc security context không được bảo đảm tiếp tục tồn tại nếu không có cơ chế context propagation phù hợp.

Ví dụ lấy tenant từ **ngữ cảnh tin cậy đã được thiết lập sau khi xác thực**, rồi truyền tường minh xuống driver:

~~~java
public Mono<AsyncResultSet> readFromContext(LocalDate day) {
    return Mono.deferContextual(ctx -> {
        UUID tenantId = ctx.get("authenticatedTenantId");
        return Mono.fromCompletionStage(() ->
            eventClient.executeFirstPage(tenantId, day, 25)
        );
    });
}
~~~

Không lấy tenant từ client rồi tự nhét vào Context để coi như đã authorization. Cũng không dùng một singleton mutable variable để “giữ requestId của thread hiện tại”.

Đối với tracing/logging:

- Truyền correlation ID/tenant được ủy quyền vào adapter như tham số.
- Dùng cơ chế tracing và context propagation chính thức khi đi qua Reactor/Future.
- Không giả định `ThreadLocal.get()` trong `thenApply` là request gốc.
- Chỉ log thông tin cần thiết, tránh dữ liệu nhạy cảm và paging state thô.

## 19. Backpressure, page size và concurrency là ba thứ khác nhau

| Cơ chế | Điều khiển |
| --- | --- |
| Reactor backpressure | Demand từ downstream tới publisher |
| Java Driver `setPageSize(n)` | Kích thước fetch dự kiến mỗi đợt Cassandra |
| `flatMap(mapper, concurrency)` | Số publisher/request được xử lý đồng thời trong đoạn pipeline |
| Rate limit / request deadline | Tổng công việc do client tạo ra |
| Partition key | Dữ liệu nằm ở đâu, replica nào phục vụ |

Ví dụ đọc nhiều tenant với **tối đa tám publisher cùng được subscribe**:

~~~java
Flux<List<EventSummary>> pages =
    Flux.fromIterable(authorizedTenantIds)
        .flatMap(tenantId ->
            listFirstPage(tenantId, selectedDay, 25),
            8
        );
~~~

Giả sử `authorizedTenantIds` và `selectedDay` đã được kiểm tra quyền/phạm vi. `flatMap` không bảo đảm giữ thứ tự kết quả theo danh sách đầu vào; nếu cần thứ tự, cân nhắc `concatMap` hoặc xử lý sắp xếp sau đó.

**Không tạo sẵn hàng nghìn Future rồi mới bọc bằng Flux.** Khi đó các request đã được gửi trước khi backpressure có thể can thiệp. Muốn kiểm soát tải, đặt `executeAsync` bên trong supplier/defer và giới hạn concurrency **ở nơi tạo request**.

Page size nhỏ không thay thế thiết kế partition/bucket; nên đọc đủ partition key, chọn projection nhỏ, giới hạn thời gian và trả cursor cho API phân trang thay vì materialize toàn bộ dữ liệu.

## 20. Đặt biên chuyển đổi ở adapter, không ở mọi method

Một cấu trúc rõ ràng:

~~~text
WebFlux Controller      Mono<EventPage>
        |
Reactive Service        Mono<EventPage>
        |
EventReaderAdapter      Mono<AsyncResultSet>
        |  [Stage -> Mono đúng một lần]
EventDriverPort         CompletionStage<AsyncResultSet>
        |
Java Driver             Cassandra
~~~

Ví dụ:

~~~java
public interface EventDriverPort {
    CompletionStage<AsyncResultSet> loadPage(
        UUID tenantId, LocalDate day, int fetchSize);
}

public final class ReactorEventAdapter {
    private final EventDriverPort port;

    public ReactorEventAdapter(EventDriverPort port) {
        this.port = port;
    }

    public Mono<AsyncResultSet> loadPage(
            UUID tenantId, LocalDate day, int fetchSize) {
        return Mono.fromCompletionStage(() ->
            port.loadPage(tenantId, day, fetchSize)
        );
    }
}
~~~

Giả sử các import `CompletionStage`, `Mono`, `AsyncResultSet`, `UUID`, `LocalDate` đã được bổ sung. Port không cần biết Reactor, còn reactive service không cần hiểu chi tiết executor/future của driver.

Nếu toàn bộ đường đi dùng `ReactiveCassandraTemplate`, không cần chuyển đổi qua `CompletableFuture` ở giữa. Ngược lại, thư viện Java ngoài hệ Reactor có thể nhận `Mono.toFuture()` đúng tại ranh giới SDK.

## 21. Kiểm thử tính lazy bằng StepVerifier

Một test đơn vị quan trọng: **chưa tạo request trước khi subscribe**.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AsyncBoundaryTest {
    @Test
    void stageStartsOnlyOnSubscription() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> publisher = Mono.fromCompletionStage(() -> {
            calls.incrementAndGet();
            return CompletableFuture.completedFuture("ok");
        });

        assertEquals(0, calls.get());

        StepVerifier.create(publisher)
            .expectNext("ok")
            .verifyComplete();

        assertEquals(1, calls.get());
    }
}
~~~

Nếu tạo future trước rồi mới truyền vào `fromCompletionStage(future)`, biến `calls` có thể đã tăng **trước** StepVerifier. Nếu subscribe cùng một cold Mono hai lần, supplier thông thường cũng được gọi hai lần; nên có test riêng để tránh nhân đôi mutation khi dùng pipeline chung cho nhiều người tiêu thụ.

### Kiểm tra error propagation

~~~java
@Test
void futureFailureBecomesMonoError() {
    CompletableFuture<String> failed = new CompletableFuture<>();
    failed.completeExceptionally(
        new IllegalStateException("Mock database failure")
    );

    StepVerifier.create(Mono.fromCompletionStage(() -> failed))
        .expectError(IllegalStateException.class)
        .verify();
}
~~~

Test này kiểm chứng cơ chế bridge với một failure giả lập. Khi chạy cùng Cassandra thật, lớp exception có thể khác; cần kiểm tra policy của driver/version.

## 22. Kiểm thử chiều Reactor → CompletableFuture

`toFuture()` **subscribe ngay**. Ví dụ:

~~~java
@Test
void toFutureTriggersSubscription() {
    AtomicInteger calls = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.just("ready");
    });

    assertEquals(0, calls.get());

    CompletableFuture<String> result = source.toFuture();

    assertEquals("ready", result.join());
    assertEquals(1, calls.get());
}
~~~

`join()` ở đây chỉ xuất hiện trong **test với Mono.just hoàn thành tức thời**. Không dùng nó như mẫu chặn một future trên production event loop.

Các kịch bản cần thêm:

- `Mono.empty()` và hợp đồng nullable/Optional khi tạo future.
- `Mono.error(...)` và việc caller Java nhận exception.
- Cancel future từ caller Java và xác minh reactive subscription được xử lý theo phiên bản.
- Hai lời gọi `toFuture()` trên cùng publisher cold có gây hai subscription không.
- Không chia sẻ một publisher `cache()` cho tenant khác hoặc request khác khi quyền và dữ liệu thay đổi.

## 23. Integration test Cassandra và khả năng quan sát

Khi có Cassandra test cluster đúng phiên bản:

1. Tạo dữ liệu thử nhiều hơn một page trong **một partition nhỏ**.
2. Kiểm tra adapter không gọi `executeAsync` trước subscribe (dùng spy/mocked port).
3. Lấy đúng page đầu, so sánh giá trị và thứ tự clustering với CQL.
4. Dùng `fetchNextPage()` trong một pipeline đa trang và đối chiếu toàn bộ hàng khi **không có ghi/xóa đồng thời**.
5. Đổi tenant/day; không tái sử dụng paging state cho statement/bind parameters khác.
6. Mô phỏng stage thất bại và kiểm tra `Mono.onError`.
7. Hủy một SELECT, theo dõi request in-flight và nhận thức rằng hủy không luôn ngừng I/O đã gửi.
8. Thử timeout/retry SELECT có giới hạn và đếm số lần supplier tạo request.
9. Xác nhận `flatMap(..., 8)` không để vượt số request mong muốn ở tầng ứng dụng.
10. Kiểm thử reactive repository/template với entity có composite key.
11. Kiểm thử chiều `Mono → CompletableFuture` với value, empty, error và cancel.
12. Với mutation có khả năng bị retry, dùng primary key/command ID ổn định và kiểm tra idempotency.

**Đừng đo hiệu năng bằng thời gian phương thức `executeAsync` trả stage.** Đó chủ yếu là thời gian khởi tạo request; latency thực phải tính tới khi future/publisher hoàn thành.

| Metric | Câu hỏi quan trọng |
| --- | --- |
| Requests per subscription | Có gọi Cassandra hai lần vì subscribe trùng không? |
| Cassandra in-flight requests | Có tạo future quá sớm/vượt giới hạn không? |
| P50/P95/P99 read latency | Có hot partition hoặc overload không? |
| Page count / bytes / rows | Flux có fetch hết lịch sử ngoài ý muốn không? |
| Subscriber timeout/cancellation | Client ngắt kết nối khi query vẫn chạy? |
| Driver timeout/unavailable/retries | Timeout đến từ tầng nào? |
| boundedElastic saturation | Có blocking I/O bị đưa vào reactive đường nóng không? |
| Duplicate commands | Retry có gây ghi hoặc tăng counter hai lần không? |

## 24. Những sai lầm phổ biến khi chuyển Future và Reactor

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `Mono.just(executeAsync(...))` | Khởi chạy sớm, phát stage thay vì kết quả | `Mono.fromCompletionStage(() -> executeAsync(...))` |
| Tạo Future trước rồi mới wrap Mono | Mất tính lazy | Supplier overload hoặc `Mono.defer` |
| `subscribe()` trong service rồi trả Mono | Có thể tạo hai lần thực thi | Trả publisher cho controller/framework |
| Gọi `join()`/`block()` trong WebFlux | Chặn event loop | Ghép bước bằng `flatMap`/`then` |
| `Flux.collectList().toFuture()` không giới hạn | Tăng heap và đọc quá nhiều page | Có cap/cursor rõ ràng |
| Retry counter update bằng `retryWhen` | Double count sau timeout | Không retry mù quáng, dùng ledger/reconciliation |
| Coi cancellation là rollback | Ghi Cassandra có thể vẫn xảy ra | Xử lý kết quả không chắc chắn |
| Biến mọi lỗi thành `Mono.empty()` | Che giấu DB failure | Phân biệt empty và error |
| `Mono.just(blockingRepository.findById(...))` | Chạy blocking quá sớm | Reactive API hoặc `fromCallable` + boundedElastic |
| Tin ThreadLocal/MDC tự đi theo Future | Mất tenant/trace context | Context propagation hoặc truyền tham số |
| Tạo sẵn hàng nghìn Future | Backpressure không chặn request đã gửi | Defer và giới hạn concurrency |
| Coi page size là giới hạn tổng số hàng | Query có thể còn page tiếp | Cursor/page contract hoặc fetchNextPage |
| Dùng `cache()` mà không có scope | Kết quả cũ hoặc chia sẻ giữa người dùng | Cache có key/tenant/TTL rõ ràng |
| Đổi Future ↔ Mono liên tục nhiều lớp | Khó kiểm soát subscription/lỗi | Một adapter tại ranh giới |

## 25. Checklist trước production

- [ ] Mỗi API boundary có hợp đồng rõ: `CompletionStage`, `CompletableFuture`, `Mono` hay `Flux`.
- [ ] Driver stage được khởi tạo qua supplier/defer nếu pipeline cần lazy execution.
- [ ] Biết rằng `toFuture()` subscribe ngay và có thể bắt đầu CQL request.
- [ ] Không dùng `Mono.just` với lời gọi blocking hoặc lời gọi async có side effect.
- [ ] Không dùng `block()`/`join()` trên WebFlux event loop hoặc driver callback.
- [ ] Có quy tắc cho empty/null/Optional, lỗi và cancellation.
- [ ] Reactor timeout và driver timeout nằm trong ngân sách chung của request.
- [ ] Retry phụ thuộc idempotency của statement và business command, không áp dụng mù quáng.
- [ ] CQL được chuẩn bị/bind đúng và chứa partition key theo access pattern.
- [ ] Có page size, projection nhỏ, giới hạn hàng/partition và cursor khi cần.
- [ ] Có bounded concurrency khi đọc nhiều partition/tenant.
- [ ] Không dựa vào ThreadLocal khi qua completion callback nếu thiếu propagation.
- [ ] `CqlSession`/prepared statement được tái sử dụng, không tạo session mỗi request.
- [ ] Không cache publisher giữa tenant hoặc request khi thiếu phạm vi/authorization.
- [ ] Có test hai chiều bridge, subscribe count, cancellation, empty và failure.
- [ ] Có metrics in-flight, p95/p99, page count, timeout, retry và duplicate commands.

## 26. Bài tập và câu hỏi tự kiểm tra

**Bài tập A – Lazy execution.** Viết `Mono<List<EventSummary>>` từ `executeAsync` và dùng `AtomicInteger` để chứng minh câu CQL **chưa khởi chạy trước subscription**. Subscribe hai lần để quan sát hai lần gọi supplier.

**Bài tập B – Chuyển ngược.** Tạo một Java SDK method trả `CompletionStage<Optional<EventRow>>` dựa trên `ReactiveEventRepository.findById`. Kiểm thử tìm thấy, không tìm thấy và exception. Không dùng `block()`.

**Bài tập C – Paging.** Tạo 120 event trong một partition, fetch size 25. So sánh endpoint chỉ trả một page/cursor với một `Flux` duyệt nhiều page. Giải thích vì sao hai API có mức tiêu hao tài nguyên khác nhau.

**Bài tập D – Retry.** Đề xuất retry policy cho một SELECT theo partition key và một UPDATE counter `+1`. Nêu lý do không thể dùng cùng một `retryWhen` mặc định.

**Bài tập E – Bounded concurrency.** Thiết kế pipeline đọc danh sách 1.000 tenant đã được ủy quyền với concurrency tối đa tám và đo số request Cassandra in-flight.

### Tự kiểm tra

**Câu 1.** Vì sao supplier overload của `Mono.fromCompletionStage` giữ được tính lazy?

**Đáp án:** Supplier chỉ được gọi khi subscribe. Truyền trực tiếp stage đã tạo nghĩa là tác vụ đã được khởi động trước đó.

**Câu 2.** `Mono.toFuture()` có đợi một subscriber khác không?

**Đáp án:** Không. Nó tự subscribe để đi tới kết quả của future.

**Câu 3.** Có thể coi `Mono.empty()` là exception “not found” tự động không?

**Đáp án:** Không. Cần `switchIfEmpty(Mono.error(...))` hoặc hợp đồng `Optional.empty()` rõ ràng.

**Câu 4.** Cancel subscriber có chắc chắn rollback Cassandra UPDATE không?

**Đáp án:** Không. Mutation có thể đã đến replica; ứng dụng phải xử lý kết quả không chắc chắn.

**Câu 5.** Tại sao `collectList().toFuture()` có thể nguy hiểm?

**Đáp án:** Nó có thể materialize toàn bộ Flux trong bộ nhớ và fetch nhiều page, kể cả khi API chỉ cần một page.

**Câu 6.** `fromCallable(...).subscribeOn(boundedElastic())` có làm CassandraTemplate blocking trở thành non-blocking thật không?

**Đáp án:** Không. Nó cách ly blocking I/O khỏi event loop; I/O vẫn blocking.

**Câu 7.** Vì sao retry một Mono dùng supplier có thể gửi lại statement CQL?

**Đáp án:** Retry tạo subscription mới; supplier lại gọi `executeAsync`. An toàn hay không phụ thuộc idempotency.

**Câu 8.** Vì sao không nên dựa vào ThreadLocal trong `CompletionStage.thenApply`?

**Đáp án:** Callback có thể chạy trên thread khác; cần truyền thông tin tường minh hoặc cấu hình context propagation.

---

**Ghi nhớ:** `CompletionStage`/`CompletableFuture` và Reactor `Mono`/`Flux` đều xử lý bất đồng bộ nhưng **khác vòng đời thực thi**. Chuyển **Stage → Mono** bằng supplier hoặc `Mono.defer` nếu cần lazy, chuyển **Mono → Future** bằng `toFuture()` đúng tại biên Java, và tránh đổi kiểu lặp lại trong toàn bộ service. Khi truy cập Cassandra, **cancel không phải rollback, backpressure không cứu Future đã chạy và retry có thể thực thi lại mutation**. Vẫn phải thiết kế partition key, paging, consistency, timeout, idempotency và giới hạn concurrency phù hợp workload.
