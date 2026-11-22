# Quản lý timeout, hủy truy vấn và tài nguyên kết nối

## 1. Vì sao một truy vấn reactive vẫn có thể làm hệ thống nghẽn?

Một dịch vụ Spring Boot dùng WebFlux nhận yêu cầu tra cứu đơn hàng, truy vấn PostgreSQL qua R2DBC rồi gọi HTTP API của đối tác. Trong giờ cao điểm, API trả `504` hoặc `503` sau vài giây; số kết nối đang dùng tăng đến giới hạn pool. Một số request từ client đã hủy nhưng truy vấn SQL vẫn còn chạy trên server. Sau khi bật retry, hệ thống càng chậm vì một truy vấn tốn nhiều thời gian được thực thi lại nhiều lần.

Đây là nhóm lỗi của **quản lý thời gian, tín hiệu hủy và vòng đời tài nguyên**. Dùng `Mono`/`Flux` không mặc nhiên giải quyết các vấn đề này. Reactive giúp tránh giữ một Java thread bị chặn cho từng thao tác I/O, nhưng kết nối database vẫn là tài nguyên hữu hạn; SQL nặng vẫn chiếm tài nguyên server; và hủy subscription không phải lúc nào cũng có nghĩa server đã hủy câu lệnh hoặc rollback mọi tác dụng phụ.

Trong module `SPRING_BOOT_INTEGRATION`, các luồng có thể kết hợp HTTP client, database, cache và broker. Cần quản lý deadline xuyên các adapter, đảm bảo tài nguyên được trả khi hoàn thành/lỗi/hủy, và quy định khả năng retry của các thao tác có tác dụng phụ.

Bài học sử dụng **Spring Boot 3.x, Reactor, Spring Data R2DBC, PostgreSQL** làm ví dụ chính. Một số phần áp dụng tương tự cho reactive MongoDB và các reactive client khác, nhưng cách server thực thi `cancel`, transaction và timeout có thể khác nhau theo driver, giao thức và phiên bản.

## 2. Phân biệt timeout ở từng ranh giới

Một API trả lời chậm có thể đang chờ kết nối, đang chạy SQL, chờ trả dữ liệu, bị chặn bởi transaction khác hoặc chậm ở HTTP phía sau. Đặt duy nhất một `timeout(2s)` mà không biết đoạn nào chậm sẽ khiến việc chẩn đoán khó khăn.

| Ranh giới | Tài nguyên đang chờ | Cơ chế kiểm soát | Khi quá hạn |
| --- | --- | --- | --- |
| **Request deadline** | Toàn bộ thao tác nghiệp vụ | Deadline tổng của HTTP/request/caller; Reactor `timeout` trên pipeline phù hợp | Hủy upstream và báo lỗi theo hợp đồng; không tự rollback mọi hệ thống ngoài |
| **Pool acquisition** | Chờ một connection từ pool | `spring.r2dbc.pool.max-acquire-time` khi dùng pool hỗ trợ | Không lấy được connection trong thời hạn |
| **Tạo connection** | DNS, TCP, TLS, xác thực với database | Driver options; `max-create-connection-time` của R2DBC pool | Thất bại khi tạo connection, cần phân loại lỗi |
| **SQL execution** | Server xử lý câu truy vấn, khóa bảng/row | Database-side statement timeout, driver-specific options | Server hủy lệnh hoặc phản hồi lỗi theo engine |
| **Đọc result stream** | Dữ liệu từ server về client | Backpressure, giới hạn kết quả, timeout từng pha | Có thể đã nhận một phần kết quả |
| **Transaction** | Tài nguyên gắn với giao dịch | Reactive transaction manager, server lock/idle/statement timeouts | Cần rollback hoặc đối soát nếu kết quả commit mơ hồ |

**Không nhầm ba câu sau:**

1. **“Request đã timeout”**: một thành phần không muốn chờ nữa.
2. **“Subscription đã cancel”**: Reactor gửi tín hiệu hủy tới nguồn còn đang được subscribe.
3. **“SQL đã bị dừng trên database”**: server nhận và áp dụng yêu cầu hủy, hoặc hết deadline ở phía server.

Ba sự kiện có liên quan nhưng **không đồng nghĩa**. Nhiều driver cố gắng chuyển tín hiệu hủy thành việc dừng thao tác đang chạy; tuy nhiên mức độ đảm bảo, độ trễ và xử lý protocol tùy driver/server. Lưu ý đặc biệt với lệnh ghi: timeout từ client không chứng minh transaction chưa commit.

### Minh họa dòng thời gian

~~~mermaid
sequenceDiagram
    participant U as HTTP client
    participant A as Spring WebFlux
    participant P as R2DBC pool
    participant D as Database
    U->>A: GET /orders/{id}
    A->>P: Acquire connection
    P-->>A: Connection
    A->>D: Execute SELECT
    Note over A: Client deadline hết
    A-->>U: Timeout / error response
    A-->>D: Cancel propagated (best effort)
    Note over D: SQL có thể cần thời gian để dừng
    A->>P: Cleanup / return connection
~~~

Nếu timeout xảy ra **trước khi lấy connection**, nên không còn yêu cầu acquire nào tồn tại sau hủy. Nếu timeout khi query đang chạy, cleanup connection cần được driver/pool hoàn tất trước khi tái sử dụng an toàn; không nên lấy một connection đang có lệnh dang dở để chạy lệnh khác.

## 3. Cơ chế subscribe, cancel và doFinally của Reactor

Một publisher reactive thường là **lazy**: tạo một `Mono` hoặc `Flux` chưa tự chạy truy vấn. Truy vấn chỉ được thực thi sau khi có subscriber, chẳng hạn HTTP runtime của WebFlux subscribe vào publisher do controller trả về.

~~~java
Mono<OrderView> result = repository.findOrder(orderId);
// Chỉ tạo Publisher; chưa có lý do để database chạy query.

return result;
// WebFlux đăng ký subscription để phục vụ request.
~~~

Khi `timeout` phát hiện publisher không đáp ứng điều kiện thời gian, nó có thể phát `TimeoutException` downstream và **cancel subscription upstream**. Tương tự, nếu HTTP client ngắt kết nối và WebFlux giải phóng request, quá trình hủy có thể lan xuống chuỗi reactive. Nhưng một đoạn mã tự gọi `subscribe()` ở bên trong service sẽ tạo subscription riêng, nằm ngoài vòng đời request ban đầu.

### Các signal quan trọng

| Signal / operator | Cách hiểu | Lưu ý |
| --- | --- | --- |
| `onComplete` | Publisher kết thúc bình thường | Không chứng minh một tác vụ ngoài DB đã thành công nếu bị tách bằng `subscribe()` |
| `onError` | Publisher báo lỗi | Lỗi timeout ở downstream có thể xuất hiện như `onError` |
| `cancel` | Subscriber không cần thêm dữ liệu | Không phải một lỗi Reactor được gửi tới upstream qua `onError` |
| `doOnCancel` | Callback khi publisher bị hủy | Có ích để theo dõi hủy, không phải nơi làm cleanup bất đồng bộ thủ công |
| `doFinally(SignalType)` | Callback khi kết thúc vì hoàn thành, lỗi hoặc hủy | Có thể ghi metric/phân loại signal `ON_COMPLETE`, `ON_ERROR`, `CANCEL` |
| `timeout(Duration)` | Timeout của publisher theo semantics của operator | Với `Flux`, thường kiểm tra thời gian chờ **giữa các phần tử**, không tự là tổng deadline của toàn stream |
| `onErrorResume(...)` | Ánh xạ lỗi thành fallback | Không xử lý signal cancel nếu upstream chỉ bị hủy và không phát lỗi downstream ở vị trí đó |

**Điểm dễ sai:** `Flux.timeout(Duration.ofSeconds(2))` không bảo đảm toàn bộ stream hoàn thành trong hai giây. Một Flux phát một phần tử mỗi giây có thể kéo dài nhiều phút mà vẫn không timeout do có phần tử đến liên tục. Để giới hạn tổng thời gian, phải thiết kế deadline cho **toàn luồng/request**, không chỉ khoảng im lặng giữa hai phần tử; tránh coi stream bị cắt ngắn là kết quả đầy đủ.

**Một lỗi khác:** gọi `block()` trong request handler WebFlux trên event-loop có thể chặn thread xử lý I/O, gây nghẽn và tạo timeout dây chuyền. R2DBC là driver reactive, vì vậy nên trả về `Mono`/`Flux` trực tiếp. Nếu phải gọi thư viện **blocking** (ví dụ JDBC cũ), đặt nó trong adapter riêng với scheduler phù hợp và giới hạn tải; không trộn trực tiếp blocking I/O vào callback của event-loop.

## 4. Cấu hình R2DBC connection pool có giới hạn

### 4.1. Tại sao pool vẫn cần trong reactive?

Reactive không có nghĩa là connection vô hạn. Một transaction dài, stream result chưa kết thúc hoặc query chậm vẫn giữ connection. Khi lượng request lớn hơn sức phục vụ của database, pool phải giới hạn số kết nối hoạt động và thời gian chờ acquire thay vì khiến ứng dụng giữ hàng nghìn request đang chờ vô hạn.

Ví dụ dependency Spring Boot 3.x (Gradle Kotlin DSL):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Cấu hình cơ bản:

~~~yaml
# application.yml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal.example:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 16
      max-idle-time: 10m
      max-acquire-time: 2s
      max-create-connection-time: 5s
~~~

`${DB_PASSWORD}` là placeholder Spring để lấy từ biến môi trường `DB_PASSWORD`. Dùng secret manager cho credential, và cấu hình TLS của PostgreSQL/driver theo chính sách môi trường. Giá trị `16` kết nối, `2s` acquire và `5s` create chỉ để minh họa; cần đo dựa trên giới hạn `max_connections` của database, số instance, lượng query song song và lưu lượng thật.

Các thuộc tính pool phụ thuộc vào version Spring Boot/R2DBC Pool; phải kiểm tra chúng được bind thành công thay vì suy đoán từ YAML. Nếu không có pool implementation phù hợp trên classpath hoặc tự tạo `ConnectionFactory` riêng, các property `spring.r2dbc.pool.*` có thể không điều khiển connection factory thực tế.

**Không tính tổng số connection chỉ từ một instance.** Với 20 pods, `max-size=16` có thể tương ứng tối đa hàng trăm connection; còn phải dành chỗ cho migration, admin, worker và dịch vụ khác. Cần phân bổ pool size theo **toàn hệ thống**, sau đó dùng backpressure, concurrency limit hoặc admission control để tránh vượt sức database.

### 4.2. Điều gì xảy ra khi không trả connection?

~~~text
HTTP requests
    |
    v
Reactive service
    |
    v
R2DBC Pool (max-size=16)
  [borrowed: 16] [idle: 0] [pending: tăng]
    |
    v
PostgreSQL
  Query chậm / lock / stream chưa kết thúc
~~~

Nếu `borrowed` luôn sát `max-size`, `pending acquire` và acquire latency tăng, các request mới có thể báo timeout dù database không lỗi kết nối. Hãy xem nguyên nhân giữ connection: query thiếu index, transaction quá dài, stream không được tiêu thụ/đóng, adapter tự tạo connection mà quên close, hoặc số request đồng thời vượt khả năng.

Không sửa sự cố này chỉ bằng cách tăng `max-size`. Tăng số connection quá mức có thể khiến PostgreSQL chịu nhiều query đồng thời hơn, làm latency xấu đi. Cần đo query plan, thời gian giữ transaction, concurrency và tỷ lệ lỗi pool acquire.

## 5. Timeout ở pipeline Reactor và lỗi trả về API

### 5.1. Đặt timeout tại adapter, có thông tin quan sát

Một adapter Spring Data R2DBC có thể dùng `DatabaseClient` để thực thi truy vấn:

~~~java
// OrderReadAdapter.java — Spring Boot 3.x / Spring R2DBC
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class OrderReadAdapter {
    private static final Logger log =
            LoggerFactory.getLogger(OrderReadAdapter.class);
    private static final Duration QUERY_BUDGET = Duration.ofSeconds(3);

    private final DatabaseClient db;

    public OrderReadAdapter(DatabaseClient db) {
        this.db = db;
    }

    public Mono<OrderView> find(String tenantId, UUID orderId) {
        Mono<OrderView> query = db.sql("""
            SELECT id, status
            FROM orders
            WHERE tenant_id = :tenant AND id = :id
            """)
                .bind("tenant", tenantId)
                .bind("id", orderId)
                .map((row, metadata) ->
                        new OrderView(
                                row.get("id", UUID.class),
                                row.get("status", String.class)))
                .one()
                .doFinally(signal ->
                        log.debug("R2DBC source finished: {}", signal));

        return query
                .timeout(QUERY_BUDGET)
                .doOnError(TimeoutException.class,
                        error -> log.warn("Order read deadline exceeded"));
    }
}

record OrderView(UUID id, String status) {}
~~~

`.one()` trả về một `Mono`; `timeout(3s)` bao trùm từ lúc subscription đến khi có item/kết thúc, gồm cả thời gian chờ kết nối trong pool nếu truy vấn đi qua pool. Khi timeout, Reactor phát `TimeoutException` downstream và cancel `query` upstream. `doFinally` đặt **trước** `timeout` thường quan sát `CANCEL` ở nguồn bị hủy; callback sau `timeout` có thể quan sát `ON_ERROR`. Đây là cách xác định timeout do pipeline chủ động cắt ngắn, không phải dấu hiệu SQL đã dừng ngay trên server.

Tham số `tenantId` chỉ là ví dụ; trong API nhiều tenant, phải lấy nó từ ngữ cảnh đã xác thực và kiểm tra quyền. `bind(...)` giữ giá trị tách khỏi câu SQL, tránh nối raw input vào truy vấn.

**Chỉ đặt timeout sát adapter là chưa đủ:** một HTTP request còn có thể chờ gọi WebClient, cache hoặc broker. Nên đặt **deadline tổng** ở ranh giới use case, phân bổ các ngân sách con hợp lý và tránh việc mỗi adapter tiêu hết một deadline riêng khiến tổng thời gian vượt SLA.

### 5.2. Timeout ở tầng API có thể chuyển thành phản hồi nào?

Việc map exception sang HTTP status là hợp đồng API, không phải thuộc tính cố định của R2DBC:

- Tra cứu phụ thuộc database đang quá tải có thể trả `503 Service Unavailable` kèm mã lỗi nghiệp vụ ổn định và `Retry-After` nếu có chính sách thực tế.
- Một API hoạt động như gateway chờ hệ thống phụ thuộc có thể trả `504 Gateway Timeout` theo hợp đồng vận hành.
- Timeout không đồng nghĩa `404 Not Found`; `404` chỉ dành cho trường hợp truy vấn đã hoàn tất và xác nhận không có dữ liệu được phép xem.
- Không trả chi tiết SQL, connection string, địa chỉ database hay stack trace cho client. Log nội bộ theo trace ID và loại lỗi.

Ví dụ, `.onErrorResume(TimeoutException.class, ...)` có thể ánh xạ sang response/fallback tại **tầng API hoặc service**, nhưng không nên biến mọi timeout thành kết quả trống `Mono.empty()`. Việc đó che mất sự cố dependency và khiến business logic tưởng một đơn hàng không tồn tại.

Nếu HTTP client đã disconnect, server có thể không gửi được một phản hồi timeout nào; luồng upstream cần được giải phóng. Không tạo subscription “fire and forget” trong controller chỉ để tránh lỗi hủy: điều đó khiến query tiếp tục chiếm connection dù không còn request cần kết quả.

## 6. Hủy truy vấn ở client và timeout ở database server

### 6.1. Vì sao cancel subscription chưa đủ?

Khi subscriber cancel, Reactor chuyển tín hiệu tới driver nếu đường reactive giữ đúng cấu trúc. Driver có thể gửi thông điệp hủy theo giao thức hoặc dọn tài nguyên của connection; nhưng chi tiết phụ thuộc driver:

- Database có thể đã hoàn thành query trước khi yêu cầu cancel tới nơi.
- SQL có thể đang chờ khóa hoặc đang xử lý trên server; việc hủy thường cần thêm thời gian.
- Với lệnh `UPDATE`/`INSERT`, server có thể đã commit; timeout trên client không chứng minh thao tác chưa có hiệu lực.
- Connection pool không nên tái sử dụng một connection chưa được dọn sạch trạng thái giao thức/transaction.

Vì vậy, với truy vấn đắt hoặc yêu cầu giới hạn tài nguyên server, nên kết hợp **timeout của Reactor** với **cơ chế giới hạn thực thi ở database**, khi driver và engine hỗ trợ.

### 6.2. PostgreSQL statement_timeout

PostgreSQL hỗ trợ `statement_timeout` để hủy câu lệnh trên server khi vượt giới hạn. Với transaction, dùng `SET LOCAL` để tránh thay đổi cấu hình vĩnh viễn của session được pool tái sử dụng:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '2500ms';
SELECT id, status
FROM orders
WHERE tenant_id = 'tenant-42' AND id = '00000000-0000-0000-0000-000000000001';
COMMIT;
~~~

`SET LOCAL` chỉ có phạm vi transaction hiện tại và không nên chạy như một lệnh độc lập ngoài transaction rồi kỳ vọng nó có hiệu lực cho truy vấn sau. Timeout của PostgreSQL có thể trả lỗi SQLSTATE liên quan `query_canceled`, thường là `57014`. Sau lỗi PostgreSQL trong một transaction, transaction có thể ở trạng thái abort; phải rollback trước khi dùng connection cho công việc khác.

Đối với một service dùng Spring R2DBC, có thể kết hợp `TransactionalOperator` để hai lệnh thực thi trong cùng transaction được bind qua Reactor Context:

~~~java
// PostgresTimedReadService.java
import java.time.Duration;
import java.util.UUID;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class PostgresTimedReadService {
    private final DatabaseClient db;
    private final TransactionalOperator tx;

    public PostgresTimedReadService(
            DatabaseClient db, TransactionalOperator tx) {
        this.db = db;
        this.tx = tx;
    }

    public Mono<OrderView> find(String tenantId, UUID orderId) {
        Mono<OrderView> work =
                db.sql("SET LOCAL statement_timeout = '2500ms'")
                  .then()
                  .then(db.sql("""
                      SELECT id, status FROM orders
                      WHERE tenant_id = :tenant AND id = :id
                      """)
                          .bind("tenant", tenantId)
                          .bind("id", orderId)
                          .map((row, metadata) ->
                                  new OrderView(
                                          row.get("id", UUID.class),
                                          row.get("status", String.class)))
                          .one());

        return tx.transactional(work)
                .timeout(Duration.ofSeconds(4));
    }
}
~~~

Ở đây `TransactionalOperator` phải được Spring cấu hình với **reactive** transaction manager của connection factory tương ứng, ví dụ `R2dbcTransactionManager`. Có thể đăng ký bean operator:

~~~java
@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

Khi dùng đoạn `@Bean`, cần import `org.springframework.context.annotation.Bean`, `org.springframework.transaction.ReactiveTransactionManager` và `org.springframework.transaction.reactive.TransactionalOperator` trong lớp `@Configuration` của ứng dụng.

Thứ tự này đặt budget **2,5 giây cho mỗi statement** trên PostgreSQL và **4 giây cho toàn publisher**, trong đó có thời gian chờ pool, bắt đầu transaction, chạy câu lệnh và cleanup. Đây là ví dụ về **hai lớp deadline**, không phải bảo đảm cả hai kết thúc chính xác vào mốc đó. Nếu pool acquire mất quá lâu, Reactor timeout có thể tới trước khi truy vấn bắt đầu.

Không đặt `SET statement_timeout = ...` ở cấp session không kiểm soát trên connection pool vì cấu hình có thể rò sang request khác. Nếu muốn áp dụng lâu dài cho role/database, nên dùng cấu hình do DBA quản lý, với giới hạn đã được đánh giá. Với MySQL, MongoDB hoặc hệ khác, tên tùy chọn và ý nghĩa timeout khác; **không giả định chúng hỗ trợ `SET LOCAL statement_timeout`**.

### 6.3. Cancellation và transaction

Reactive transaction được gắn vào **Reactor Context**, không dựa vào một `ThreadLocal` cố định như nhiều luồng imperative. Khi downstream hủy publisher có transaction đang mở, Spring transaction operator sẽ cố gắng cleanup và rollback theo vòng đời subscription. Tuy nhiên nếu commit đã thực hiện hoặc đang ở vùng kết quả mơ hồ khi mất mạng, **không thể suy ra toàn bộ business operation đã rollback**.

Không chuyển qua `subscribe()` hoặc `block()` bên trong transaction method rồi hy vọng child flow tự dùng đúng connection/transaction. Với `@Transactional` reactive, phương thức nên trả về `Mono`/`Flux` để transaction interceptor quản lý subscription. Nếu cần phối hợp nhiều nguồn dữ liệu, `@Transactional` của một `R2dbcTransactionManager` không làm HTTP/broker hoặc một database khác tham gia atomic commit.

## 7. Giải phóng connection theo đủ ba đường: complete, error, cancel

### 7.1. Ưu tiên template và transaction manager của Spring

Khi dùng `R2dbcEntityTemplate`, `DatabaseClient` hoặc repository reactive của Spring, framework quản lý việc lấy/trả connection theo publisher và transaction context. Khi có transaction, Spring bind connection với transaction thay vì đóng sau từng statement. Không nên tự gọi `close()` trên connection đang được Spring quản lý, và không giữ connection trong field của singleton service.

Với logic truy cập `ConnectionFactory` trực tiếp, người viết mã phải tự bảo đảm cleanup **ngay cả khi subscriber cancel**. `try/finally` đồng bộ không thể bao phủ đầy đủ vòng đời tài nguyên bất đồng bộ sau khi method đã trả về `Publisher`.

### 7.2. Mono.usingWhen cho kết nối thủ công

Ví dụ đếm số đơn mở bằng API R2DBC SPI, không qua `DatabaseClient`:

~~~java
// RawOrderCounter.java — ví dụ kết nối thủ công
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class RawOrderCounter {
    private final ConnectionFactory factory;

    public RawOrderCounter(ConnectionFactory factory) {
        this.factory = factory;
    }

    public Mono<Long> countOpen() {
        return Mono.usingWhen(
                Mono.from(factory.create()),
                connection -> Mono.from(
                        connection.createStatement("""
                            SELECT COUNT(*) FROM orders WHERE status = $1
                            """)
                                .bind(0, "OPEN")
                                .execute())
                        .flatMap(result -> Mono.from(
                                result.map((row, metadata) ->
                                        row.get(0, Long.class)))),
                connection -> Mono.from(connection.close()),
                (connection, error) -> Mono.from(connection.close()),
                connection -> Mono.from(connection.close()));
    }
}
~~~

`usingWhen` nhận lần lượt publisher tạo resource, callback sử dụng resource, cleanup khi hoàn tất, cleanup khi lỗi và cleanup khi cancel. Với connection lấy từ pool, `close()` thường trả connection về pool theo hợp đồng của pool, thay vì bắt buộc đóng socket vật lý. Sau cleanup không tái sử dụng reference connection đã đóng/trả pool.

Ví dụ trên sử dụng cú pháp parameter marker `$1` **riêng của PostgreSQL** và giả định `COUNT(*)` trả một số `Long`. Các driver khác có marker hoặc kiểu dữ liệu khác. Đây là ví dụ cho bài học về vòng đời tài nguyên; với truy vấn thông thường, ưu tiên `DatabaseClient` để giảm mã quản lý kết nối thủ công.

Không dùng `doFinally(signal -> connection.close().subscribe())` như một cách cleanup thông thường. Subscription tách rời có thể chạy không đúng thứ tự, không được await, và lỗi cleanup bị mất. Hãy dùng `usingWhen` hoặc abstraction của Spring để gắn cleanup vào vòng đời publisher.

### 7.3. Result và connection có thể bị giữ lâu bởi stream

Một `Flux` trả hàng trăm nghìn row có thể giữ connection tới khi stream hoàn tất hoặc bị cancel. `collectList()` chuyển toàn bộ stream thành một collection trong memory, làm tăng áp lực heap; `take(100)` có thể hủy upstream sau 100 row nhưng không thay thế câu `LIMIT 100` ở SQL server. Nên dùng truy vấn có giới hạn, keyset pagination hoặc batching có kích thước kiểm soát.

Ví dụ:

~~~sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenant
  AND (created_at, id) > (:last_created_at, :last_id)
ORDER BY created_at, id
LIMIT 200;
~~~

Đây là dạng **keyset pagination** khi đã có cursor hợp lệ và chỉ mục phù hợp, giúp mỗi request lấy một trang thay vì giữ query stream quá dài. Cursor cần ràng buộc theo tenant, kiểu dữ liệu và thứ tự ổn định; cursor đầu tiên có thể dùng điều kiện khác thay cho tuple comparison.

## 8. Kiểm soát concurrency và backpressure

### 8.1. flatMap không giới hạn có thể làm cạn pool

Trong luồng tích hợp đọc một batch ID từ Kafka hoặc HTTP rồi truy vấn database để làm giàu dữ liệu, một `flatMap` không có giới hạn hợp lý có thể tạo nhiều subscription query cùng lúc. Reactive không tạo thêm connection khi pool đã đầy, nhưng backlog chờ acquire vẫn lớn và làm trễ các request quan trọng.

~~~java
// enrichment: mỗi ID là một đơn cần tra cứu
Flux<OrderView> enrich(Flux<UUID> ids, String tenantId,
                       OrderReadAdapter adapter) {
    return ids.flatMap(
            id -> adapter.find(tenantId, id),
            8); // tối đa 8 inner publisher đồng thời tại operator này
}
~~~

`flatMap(..., 8)` giới hạn số inner subscription trong **một pipeline**, không giới hạn tổng tải toàn bộ ứng dụng. Nếu có 100 request cùng chạy, mỗi request tối đa 8 truy vấn vẫn có thể sinh nhu cầu lớn. Cần điều phối bằng pool, HTTP/broker concurrency, rate limiting và giới hạn workload khi cần.

| Operator/chiến lược | Bảo toàn thứ tự output? | Ý nghĩa |
| --- | --- | --- |
| `flatMap(mapper, concurrency)` | Không bảo đảm | Chạy một số inner publisher song song, xuất kết quả theo lúc hoàn tất |
| `concatMap(mapper)` | Có | Xử lý tuần tự; dễ kiểm soát thứ tự, giảm concurrency |
| `flatMapSequential(mapper, concurrency)` | Có với thứ tự nguồn | Có concurrency nhưng có thể phải đệm kết quả đến sớm |
| SQL `LIMIT` + keyset pagination | Kết quả theo `ORDER BY` đã chỉ định | Giảm dữ liệu và thời gian giữ connection của mỗi lần đọc |

Nếu các event cập nhật cùng một thực thể, `flatMap` có thể làm hiệu ứng ghi xuất hiện sai thứ tự. Chọn thứ tự theo khóa nghiệp vụ và version/CAS chứ không chỉ dựa vào thứ tự nhận message. Với dữ liệu lớn, chỉ số **số truy vấn đang chạy**, **pending acquire** và **thời gian giữ connection** quan trọng hơn số thread Java.

### 8.2. Backpressure không miễn phí

Publisher và subscriber có cơ chế request số lượng phần tử, nhưng không phải mọi database driver đều truyền backpressure thành dừng đọc chính xác từng row ở server. Có driver buffering hoặc cách fetch riêng. Một `Flux` đọc vô hạn và consumer chậm vẫn có thể giữ connection lâu, làm pool nghẽn. Nên ưu tiên query giới hạn, pagination và thiết kế batch với kích thước phù hợp.

Không giải quyết query chậm bằng `publishOn(Schedulers.boundedElastic())`: R2DBC đã là API nonblocking; chuyển scheduler không làm SQL nhanh hơn hay tự giải phóng connection. `boundedElastic` phù hợp hơn cho code blocking bắt buộc phải cô lập, với giới hạn tải.

## 9. Retry, idempotency và timeout khi ghi dữ liệu

### 9.1. Một lần timeout có thể đã làm thay đổi database

Giả sử consumer xử lý sự kiện `PaymentCaptured(eventId=pay-813)` để trừ tiền trong PostgreSQL. Nếu client timeout ngay sau lúc SQL hoàn thành hoặc commit được gửi tới server, không thể kết luận update thất bại. Retry vô điều kiện có thể trừ tiền lần hai.

Thiết kế tốt hơn là dùng **idempotency key bền vững và unique constraint**, ghi dấu xử lý cùng transaction với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE consumed_payment_event (
    event_id TEXT PRIMARY KEY
);

-- Chạy bên trong transaction nghiệp vụ.
WITH inserted AS (
    INSERT INTO consumed_payment_event(event_id)
    VALUES (:event_id)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
)
UPDATE wallet
SET balance = balance - :amount
WHERE wallet_id = :wallet_id
  AND balance >= :amount
  AND EXISTS (SELECT 1 FROM inserted);
~~~

Một transaction thực sự phải kiểm tra kết quả `rowsUpdated()`: khi bằng 0, cần phân biệt sự kiện đã xử lý với ví không tồn tại hoặc không đủ số dư. Nếu đó là lỗi nghiệp vụ mới, **rollback** cả marker vừa được insert; không commit một dấu “đã xử lý” khi hiệu ứng cần thiết chưa xảy ra. Ràng buộc số dư, quyền, event ID và concurrency cần được xác định theo hợp đồng nghiệp vụ.

### 9.2. Chỉ retry lỗi được phân loại là tạm thời và an toàn

| Tình huống | Retry tự động? | Ghi chú |
| --- | --- | --- |
| `SELECT` chỉ đọc và driver báo lỗi tạm thời rõ ràng | Có thể, với backoff/giới hạn | Giữ **deadline tổng** và tránh retry storm |
| Timeout chờ acquire khi pool đang quá tải | Rất hạn chế | Retry ngay có thể làm tăng pending queue |
| SQL sai syntax, thiếu bảng, quyền bị từ chối | Không | Lỗi cấu hình/contract cần sửa |
| Database statement timeout do query chậm cố hữu | Thường không | Phân tích index/query plan/lock trước |
| `INSERT`/`UPDATE` có kết quả commit không rõ | Không retry mù quáng | Kiểm tra idempotency key và đối soát |
| Consumer xử lý lại cùng sự kiện broker | Phải an toàn khi replay | Inbox/unique key trong cùng transaction nghiệp vụ |

Nếu dùng `retryWhen(Retry.backoff(...))`, nên giữ chính sách retry **bên trong deadline tổng** của request. Mỗi retry subscribe lại vào publisher, nghĩa là có thể thực thi SQL mới. Đừng đặt nhiều tầng retry độc lập khiến số lượt thực thi nhân lên. `TimeoutException` và signal cancellation có thể đi qua đường xử lý khác nhau, nên việc retry phải dựa vào kết quả và nguồn lỗi cụ thể.

### 9.3. Khi phối hợp HTTP/broker và database

Giả sử Spring Boot nhận event Kafka, ghi order projection qua R2DBC rồi commit offset. Nếu DB commit thành công nhưng consumer crash trước khi commit offset, message được giao lại. Cần inbox/idempotency theo `eventId` trong DB; ack/commit broker **sau khi DB commit**. Nếu timeout ở ranh giới commit, offset Kafka không chứng minh DB đã rollback.

Với WebClient gọi HTTP ngoài database, `TransactionalOperator` chỉ quản lý transaction R2DBC. Nó **không rollback HTTP request** hoặc publish Kafka/RabbitMQ đã được hệ thống ngoài chấp nhận. Muốn bảo toàn luồng tích hợp, cần outbox/saga, idempotency và chính sách bù trừ.

## 10. Quan sát và gỡ lỗi trong production

### 10.1. Theo dõi theo từng pha

Những chỉ số cần quan sát (tên metric thực tế tùy phiên bản instrumentation):

| Nhóm | Tín hiệu nên theo dõi | Ý nghĩa |
| --- | --- | --- |
| **API** | request latency p95/p99, timeout count, client disconnect/cancel | Phân biệt caller hết hạn với database chậm |
| **R2DBC pool** | acquired/idle/pending, thời gian acquire, tỷ lệ acquire timeout | Pool có đang bão hòa hoặc bị giữ connection lâu? |
| **SQL** | query latency, statement timeout, SQLSTATE, slow query plan | Lệnh nặng, thiếu index, lock contention |
| **Transaction** | thời gian transaction, rollback, commit error, lock wait | Giao dịch giữ tài nguyên hoặc commit không rõ |
| **Reactive pipeline** | complete/error/cancel theo adapter và trace ID | Phân biệt upstream cancel với source error |
| **Hệ ngoài** | WebClient timeout, broker lag, retry count, idempotency conflict | Tìm ranh giới gây độ trễ hoặc replay |

Khi log exception, giữ correlation ID, tên operation, duration, phân loại error và SQLSTATE an toàn. Không log password, connection URL có secret, toàn bộ payload nhạy cảm hoặc SQL đã gắn dữ liệu riêng tư.

Với PostgreSQL, có thể kiểm tra session còn chạy hoặc đang chờ:

~~~sql
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS query_age
FROM pg_stat_activity
WHERE application_name = 'orders-integration'
  AND state <> 'idle';
~~~

Người vận hành cần quyền phù hợp để xem đủ thông tin. `pg_stat_activity` phản ánh ảnh chụp tại thời điểm truy vấn, không phải bằng chứng duy nhất rằng client đã hoặc chưa gửi cancel. Khi nhiều tầng timeout khác nhau, so khớp timestamp và trace để tránh quy sai lỗi cho pool hay database.

### 10.2. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân cần kiểm tra | Hành động |
| --- | --- | --- |
| Lỗi `PoolAcquireTimeoutException` hoặc tương đương | Pool đầy, connection bị giữ lâu, query quá chậm | Quan sát acquired/pending, giới hạn concurrency, xem transaction và query plan |
| API timeout nhưng `pg_stat_activity` vẫn thấy query | Driver hủy chưa hoàn tất hoặc server không áp dụng timeout | Kiểm tra driver, DB statement timeout, lock và cancellation |
| Pool ít connection rảnh dù request đã đóng | Resource không cleanup khi cancel; xử lý detached | Kiểm tra manual `subscribe()`, `usingWhen`, transaction boundaries |
| `Flux` trả dữ liệu mãi nhưng không timeout | `Flux.timeout` theo khoảng giữa phần tử | Thiết kế total deadline và phân trang |
| Tăng `max-size` nhưng p99 tệ hơn | Database quá nhiều query đồng thời | Giảm concurrency, tối ưu index, cân đối pool toàn cluster |
| Client nhận `503` dù SQL nhanh | Chờ acquire quá lâu, HTTP dependency hoặc queue khác | Đo duration theo từng pha thay vì chỉ thời gian SQL |
| Sau timeout write, retry tạo dữ liệu trùng | Kết quả commit không rõ, thiếu idempotency | Unique event ID, transaction, đối soát và retry có điều kiện |
| `@Transactional` có vẻ không rollback | `subscribe()` tách luồng, sai transaction manager hoặc commit đã xong | Giữ publisher trong reactive chain, kiểm tra context và ranh giới commit |

## 11. Kiểm thử cancellation và connection cleanup

Kiểm thử trên **database tương thích production** (ví dụ PostgreSQL qua Testcontainers), pool nhỏ và môi trường độc lập. Unit test với mock chỉ kiểm tra tín hiệu Reactor, không chứng minh database thực sự dừng SQL hay connection được trả về pool.

| Ca thử | Cách tái tạo | Kết quả cần kiểm chứng |
| --- | --- | --- |
| Timeout trước khi lấy connection | Pool `max-size=1`; giữ connection bằng một transaction rồi gọi request thứ hai | Request thứ hai hết hạn acquire; không còn pending acquire sau hủy |
| Timeout khi query đang chạy | `SELECT pg_sleep(5)`, timeout client ngắn hơn | Downstream nhận timeout; điều tra cancel/transaction và pool hồi phục |
| Timeout server | `SET LOCAL statement_timeout` thấp hơn thời gian query | PostgreSQL hủy statement, transaction rollback/cleanup đúng |
| Client ngắt kết nối | Cancel subscription trong khi đang stream | `doFinally` quan sát `CANCEL`; connection trở lại pool sau cleanup |
| Lỗi trong transaction | Cố ý gây constraint violation | Rollback, không có cập nhật một phần |
| Timeout đúng lúc write/commit | Tạo điều kiện mạng/chậm DB khiến kết quả không chắc | Không tự retry gây trùng; đối soát qua idempotency key |
| Tăng concurrency mạnh | Nhiều request `flatMap` cùng lúc | Pool không vượt giới hạn; độ trễ/queue được đo và có giới hạn |
| Nâng cấp driver | Chạy cùng bộ test trên R2DBC driver mới | Timeout, cancellation, pool lifecycle không đổi ngoài dự kiến |

Ví dụ Reactor Test kiểm tra tín hiệu timeout ở downstream:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.test.StepVerifier;

void shouldTimeoutSlowQuery(DatabaseClient db) {
    StepVerifier.create(
            db.sql("SELECT pg_sleep(5)")
              .then()
              .timeout(Duration.ofMillis(250)))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(3));
}
~~~

Đoạn test giả định có `reactor-test` trong test classpath và một PostgreSQL test đang chạy; đây là minh họa cho **downstream**. Nó chưa chứng minh `pg_sleep` đã dừng phía server. Sau `StepVerifier`, cần kiểm tra pool không rò connection, có thể thực thi query mới và PostgreSQL không giữ query/transaction bất thường.

**Không dùng virtual time để kết luận cleanup tài nguyên mạng thật.** `StepVerifier.withVirtualTime` chỉ thích hợp để kiểm thử riêng timer/backoff thuần Reactor; cancellation của driver, pool, PostgreSQL và network cần integration test.

## 12. Tình huống tổng hợp và câu hỏi tự kiểm tra

**Tình huống A — “API timeout nhưng pool vẫn hết connection”.** Handler trả `Mono` từ `DatabaseClient`, nhưng một nhánh service tự `subscribe()` để ghi audit và không quản lý subscription. Khi HTTP client disconnect, publisher chính bị hủy, còn query audit vẫn chạy. Sửa bằng việc đưa audit vào luồng được quản lý vòng đời hoặc ghi outbox để worker xử lý độc lập có giám sát. Đo acquired/pending trước và sau khi cancel.

**Tình huống B — “Timeout hai giây nhưng stream chạy cả phút”.** API dùng `Flux.timeout(2s)` với một row trả về mỗi giây. Operator thấy khoảng cách giữa các phần tử đủ ngắn nên stream không lỗi. Sửa bằng deadline toàn request, giới hạn result/pagination và query execution timeout server.

**Tình huống C — “Retry sau timeout trừ tiền hai lần”.** R2DBC update hoàn tất nhưng response bị mất quanh ranh giới commit; handler retry `UPDATE balance = balance - amount`. Sửa bằng business event ID duy nhất, transaction và rào chắn idempotency, sau đó đối soát khi kết quả lần đầu chưa rõ.

### Tự kiểm tra

1. **`Mono.timeout` có chắc SQL bị PostgreSQL dừng ngay không?** Không. Reactor cancel upstream, còn server cancellation phụ thuộc driver/database và có thể trễ.
2. **`Flux.timeout(2s)` giới hạn toàn stream trong hai giây?** Không; thường giới hạn khoảng im lặng giữa các phần tử.
3. **Vì sao cần `max-acquire-time` ngoài query timeout?** Vì thời gian chờ connection có thể lớn dù SQL chạy nhanh.
4. **Tại sao `SET LOCAL statement_timeout` phải ở trong transaction?** Để cấu hình có hiệu lực với transaction hiện tại và không rò sang session khác trong pool.
5. **`usingWhen` khác `doFinally(... close().subscribe())` ra sao?** `usingWhen` gắn cleanup bất đồng bộ vào vòng đời complete/error/cancel và quản lý subscription cleanup.
6. **Tăng pool size có luôn giảm timeout?** Không; có thể làm database quá tải vì thêm query đồng thời.
7. **Timeout lệnh ghi có nghĩa chưa commit?** Không; cần coi kết quả commit là có thể mơ hồ và dùng idempotency/đối soát.
8. **`@Transactional` cho R2DBC có quản lý Kafka/HTTP?** Không, chỉ tài nguyên thuộc transaction manager tương ứng.
9. **Làm sao chứng minh connection trả về pool sau cancel?** Dùng integration test, quan sát acquired/idle/pending và thử query mới sau cleanup.

Trong luồng dữ liệu reactive của Spring Boot, cấu hình đúng kết hợp **deadline tổng**, **timeout từng pha**, **cancellation có thể quan sát**, **cleanup cho complete/error/cancel**, **pool và concurrency có giới hạn**, cùng **idempotency cho ghi dữ liệu**. Các lớp này giải quyết những ranh giới khác nhau; kiểm thử với driver và database thực giúp xác nhận hành vi khi timeout, cancel hoặc nâng cấp.
