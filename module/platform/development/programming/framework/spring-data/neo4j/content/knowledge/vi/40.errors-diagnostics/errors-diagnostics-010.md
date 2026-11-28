# Giao dịch không có hiệu lực, cạn pool hoặc truy vấn quá thời gian

Khi một thao tác Spring Data Neo4j (SDN) trả về nhưng dữ liệu không thay đổi, request chờ lâu hoặc ứng dụng báo không lấy được connection, ba nhóm vấn đề thường bị nhầm lẫn: transaction chưa commit hoặc đã rollback; connection pool không còn connection rảnh; và một lớp timeout đã hết hạn. Mỗi nhóm có nguyên nhân và cách xử lý khác nhau.

Hãy xác nhận query có thực sự tạo ra thay đổi, transaction có đi qua đúng transaction manager và đã commit hay chưa. Sau đó kiểm tra vòng đời session/connection, mức đồng thời và thời gian chờ trong pool. Cuối cùng, phân biệt timeout kết nối, timeout lấy connection, timeout transaction, timeout chờ lock và timeout HTTP/request. Tăng mọi timeout hoặc tăng pool size ngay lập tức có thể chỉ làm sự cố kéo dài hơn.

## 1. Nhận diện đúng triệu chứng

| Triệu chứng | Lớp cần kiểm tra đầu tiên | Dấu hiệu thường gặp |
|---|---|---|
| Repository trả về bình thường nhưng dữ liệu không đổi | Cypher result, transaction boundary, commit/rollback | Query không match node, transaction chưa commit, exception bị bắt, gọi `@Transactional` qua self-invocation |
| Một phần thao tác ghi thành công, phần còn lại không có hiệu lực | Transaction boundary và rollback rule | Nhiều repository call không nằm trong cùng transaction, exception bị nuốt hoặc checked exception không kích hoạt rollback |
| Request chờ lâu rồi lỗi lấy connection | Driver connection pool | Pool đạt giới hạn, connection đang bị giữ bởi session/transaction chưa đóng hoặc workload đồng thời tăng |
| Query chậm rồi transaction bị hủy | Query plan, lock wait, transaction timeout | `db.transaction.timeout`, `db.lock.acquisition.timeout`, query plan tốn nhiều DB hits |
| Kết nối mới tới server thất bại | Socket connection timeout hoặc network | Host/port không truy cập được, TLS handshake hoặc server quá tải |
| Một request bị timeout nhưng query vẫn tiếp tục ở tầng khác | Deadline giữa các lớp không đồng bộ | HTTP timeout ngắn hơn transaction timeout hoặc caller hủy reactive publisher |

Đừng kết luận “transaction không chạy” chỉ vì kết quả trả về rỗng. Một query `MATCH` không tìm thấy node có thể hoàn tất thành công nhưng cập nhật zero rows. Hãy kiểm tra số bản ghi match, query counters và trạng thái transaction trước khi điều chỉnh cấu hình.

## 2. Phân biệt query không thay đổi dữ liệu với transaction không commit

Một câu lệnh Cypher có thể chạy thành công mà không tạo thay đổi:

~~~cypher
MATCH (p:Person {personKey: $personKey})
SET p.status = 'ACTIVE'
RETURN p.personKey;
~~~

Nếu không có `Person` nào mang `personKey` đã truyền, query trả về zero records và không cập nhật property. Transaction vẫn có thể commit bình thường. Vì vậy, hãy kiểm tra parameter, label, property, điều kiện WHERE và số record thực tế.

Với Java Driver, có thể kiểm tra summary sau khi tiêu thụ result:

~~~java
var result = tx.run("""
    MATCH (p:Person {personKey: $personKey})
    SET p.status = $status
    RETURN p.personKey AS personKey
    """, Map.of(
        "personKey", personKey,
        "status", "ACTIVE"
    ));

var records = result.list();
var summary = result.consume();
var counters = summary.counters();

System.out.println("records = " + records.size());
System.out.println("containsUpdates = " + counters.containsUpdates());
System.out.println("propertiesSet = " + counters.propertiesSet());
~~~

`containsUpdates()` cho biết query có tạo update hay không; `propertiesSet()` cho biết số property được đặt. Chỉ lấy summary sau khi records đã được tiêu thụ, vì `consume()` sẽ làm cạn result stream. Không trả `Result` chưa xử lý ra khỏi transaction callback.

## 3. Xác nhận transaction Spring thực sự được kích hoạt

`@Transactional` là metadata để Spring transaction infrastructure xử lý. Chỉ đặt annotation lên method chưa đủ nếu annotation-driven transaction management chưa được kích hoạt hoặc bean không được gọi qua proxy.

Trong Spring Boot, auto-configuration thường thiết lập transaction management cho ứng dụng SDN. Với cấu hình thủ công, cần có transaction manager SDN và bật annotation-driven transaction management. Nếu ứng dụng có nhiều transaction manager, hãy chỉ định manager phù hợp.

Ví dụ service boundary:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(
            OrderRepository orders,
            InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void confirmOrder(String orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));

        order.setStatus("CONFIRMED");
        orders.save(order);
        inventory.reserve(order.getProductId(), order.getQuantity());
    }
}
~~~

Hai repository call tham gia cùng transaction Neo4j do SDN cấu hình. Nếu một thao tác thất bại và exception kích hoạt rollback, toàn bộ thay đổi trong transaction đó được hoàn tác. Nếu ứng dụng có nhiều transaction manager, hãy chỉ định qualifier hoặc bean name thực tế của Neo4j manager thay vì dựa vào lựa chọn mặc định.

## 4. Các lỗi khiến transaction annotation không có hiệu lực

### Gọi method nội bộ trong cùng class

Ở chế độ proxy mặc định, Spring chỉ chặn lời gọi đi từ bên ngoài bean qua proxy. Một method gọi trực tiếp method khác trong cùng object không đi qua proxy:

~~~java
@Service
public class OrderService {

    public void process(String orderId) {
        confirm(orderId); // self-invocation: không đi qua transaction proxy
    }

    @Transactional
    public void confirm(String orderId) {
        // các thao tác Neo4j
    }
}
~~~

Đưa transaction boundary lên method được gọi từ bean khác, hoặc tách phần transactional thành một bean riêng.

### Chọn nhầm transaction manager

Ứng dụng có thể cùng lúc dùng Neo4j và một relational database. Nếu transaction annotation chọn transaction manager JDBC, thao tác SDN có thể không nằm trong transaction Neo4j mong muốn. Dùng qualifier phù hợp, ví dụ `@Transactional(transactionManager = "neo4jTransactionManager")`, cho service xử lý graph.

### Annotation nằm trên method không được proxy

Hãy đặt annotation trên method của Spring bean được gọi qua proxy. Các method private không được proxy thông thường chặn; method final hoặc cách khai báo bean cũng có thể ảnh hưởng khả năng tạo proxy tùy loại proxy. Kiểm tra method visibility, interface/class proxy và cách bean được khởi tạo.

### Transaction kết thúc trước khi công việc bất đồng bộ chạy

Nếu method transactional khởi chạy một thread, callback hoặc tác vụ `@Async` rồi trả về ngay, transaction của method có thể đã kết thúc trước khi tác vụ kia truy cập Neo4j. Transaction không tự lan sang thread khác. Hãy tạo transaction boundary trong chính bean xử lý tác vụ bất đồng bộ.

## 5. Kiểm tra rollback rule và exception bị bắt

Theo mặc định của Spring, `RuntimeException` và `Error` kích hoạt rollback; checked exception không tự kích hoạt rollback. Nếu method bắt exception rồi tiếp tục trả về bình thường, transaction có thể được commit nếu chưa bị đánh dấu rollback-only.

Ví dụ checked exception cần rollback:

~~~java
@Transactional(
    rollbackFor = InventoryException.class
)
public void confirmOrder(String orderId) throws InventoryException {
    orders.markConfirmed(orderId);
    inventory.reserve(orderId); // có thể ném checked exception
}
~~~

Nếu bắt exception để ghi log hoặc chuyển thành kết quả nghiệp vụ, hãy quyết định rõ transaction có phải rollback hay không. Có thể để exception phù hợp truyền ra ngoài hoặc khai báo `rollbackFor`. Không nuốt lỗi rồi mặc định cho rằng Spring sẽ tự rollback.

Một transaction đã bị đánh dấu rollback-only có thể kết thúc bằng `UnexpectedRollbackException` khi code bên ngoài tưởng rằng nó sẽ commit. Khi gặp lỗi này, kiểm tra exception ban đầu và transaction participant đã đánh dấu rollback-only ở đâu.

## 6. Reactive transaction cần giữ nguyên publisher chain

Với SDN reactive, transaction được gắn với reactive context và vòng đời subscription. Method transactional phải trả về `Mono` hoặc `Flux` đại diện cho công việc database:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository orders;
    private final ReactiveInventoryRepository inventory;

    public ReactiveOrderService(
            ReactiveOrderRepository orders,
            ReactiveInventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional(transactionManager = "reactiveTransactionManager")
    public Mono<Void> confirmOrder(String orderId) {
        return orders.findById(orderId)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");
                return orders.save(order)
                    .then(inventory.reserve(
                        order.getProductId(), order.getQuantity()));
            })
            .then();
    }
}
~~~

Trong ví dụ, publisher được trả về để Spring quản lý transaction tới khi publisher hoàn tất. Với Spring Boot, reactive transaction manager không được auto-configure cho Neo4j reactive repositories; cần khai báo bean `ReactiveNeo4jTransactionManager`, thường đặt tên `reactiveTransactionManager`:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;

@Bean
ReactiveNeo4jTransactionManager reactiveTransactionManager(
        Driver driver,
        ReactiveDatabaseSelectionProvider databaseSelectionProvider) {
    return new ReactiveNeo4jTransactionManager(
        driver, databaseSelectionProvider);
}
~~~

Nếu dùng `@EnableReactiveNeo4jRepositories`, thuộc tính `transactionManagerRef` phải trỏ tới đúng tên bean. Nếu dùng `@Transactional(transactionManager = "...")`, cũng phải dùng cùng tên.

Các lỗi thường gặp:

- Gọi `subscribe()` bên trong method rồi trả `Mono.empty()`: subscription tách khỏi publisher mà Spring đang quản lý.
- Gọi `block()` trong reactive flow: có thể chặn event-loop và làm mất lợi ích non-blocking.
- Tạo publisher nhưng không trả hoặc không compose nó vào publisher cuối: thao tác chưa được thực thi trong transaction mong muốn.
- Dùng imperative transaction manager cho reactive repository: transaction context không được quản lý theo reactive model.
- Hủy subscription: transaction có thể bị rollback khi publisher bị cancel trước khi hoàn tất.

Hãy compose bằng `map`, `flatMap`, `then` và `onErrorResume` theo đúng ngữ nghĩa, rồi trả publisher cuối cùng từ method transactional. Đừng tự subscribe trong service.

## 7. Transaction Java Driver không commit nếu quên gọi commit

Khi dùng explicit transaction của Java Driver, `close()` không có nghĩa là commit. Nếu transaction được đóng mà chưa gọi `commit()`, Driver rollback transaction đó:

~~~java
try (var session = driver.session()) {
    try (var tx = session.beginTransaction()) {
        tx.run("""
            CREATE (:AuditEvent {eventId: $eventId})
            """, Map.of("eventId", eventId));

        tx.commit();
    }
}
~~~

Nếu bỏ `tx.commit()`, thay đổi bị rollback khi transaction đóng.

Với managed transaction, `executeWrite()` commit khi callback trả về bình thường và rollback khi callback ném exception:

~~~java
try (var session = driver.session()) {
    session.executeWrite(tx -> {
        tx.run("""
            CREATE (:AuditEvent {eventId: $eventId})
            """, Map.of("eventId", eventId)).consume();
        return null; // callback hoàn tất bình thường: managed transaction commit
    });
}
~~~

Không trả đối tượng `Result` từ transaction callback. Hãy tiêu thụ records hoặc summary bên trong callback. Managed transaction có thể được Driver retry khi gặp lỗi transient; callback phải an toàn khi chạy lại.

## 8. Vì sao connection pool bị cạn?

Driver quản lý connection pool và cấp connection khi session cần thực thi query. Pool có giới hạn; khi mọi connection phù hợp đang bận và pool không thể mở thêm, request mới phải chờ. Nếu không lấy được connection trong acquisition timeout, Driver ném lỗi.

Các nguyên nhân phổ biến:

- Session được tạo nhưng không đóng.
- Transaction mở quá lâu hoặc chờ logic ngoài database trước khi kết thúc.
- Result stream được đọc chậm hoặc không được tiêu thụ/đóng đúng cách.
- Code tạo nhiều `Driver` instance, mỗi instance có pool riêng và tăng tổng số connection.
- Nhiều request đồng thời hơn năng lực pool/server.
- Query chậm hoặc lock contention khiến connection bị giữ lâu.
- Retry dồn dập làm tăng số lần thử lấy connection trong lúc hệ thống đã quá tải.

Session là resource cần đóng. Driver thread-safe và nên được dùng chung toàn ứng dụng; session không thread-safe, mỗi luồng xử lý cần session riêng. Không chia sẻ một session giữa nhiều thread.

## 9. Đóng session và transaction đúng vòng đời

Khi dùng Driver trực tiếp, ưu tiên `try-with-resources`:

~~~java
try (var session = driver.session()) {
    var records = session.executeRead(tx ->
        tx.run("""
            MATCH (p:Person)
            RETURN p.personKey AS personKey
            LIMIT 100
            """)
          .list()
    );
}
~~~

Đóng session trả resource về pool để được tái sử dụng. Nếu không dùng try-with-resources, cần gọi `session.close()` trong `finally`.

Với SDN repository và `Neo4jClient` được Spring quản lý, hãy để transaction manager quản lý session/transaction. Tránh tự mở thêm Driver session cho cùng một thao tác nếu không có lý do rõ ràng.

Kết quả Driver được lấy theo kiểu lazy. Nếu giữ `Result` trong khi chờ gọi HTTP hoặc xử lý nghiệp vụ lâu, session/connection có thể vẫn bị chiếm. Hãy xử lý records trong transaction, sau đó trả DTO/dữ liệu thuần cho các bước ngoài database.

## 10. Đo và điều chỉnh connection pool

Java Driver cho phép cấu hình:

- `withMaxConnectionPoolSize`: số connection tối đa trong pool. Với direct driver, giới hạn áp dụng cho pool tới database; với routing driver, giới hạn áp dụng theo từng cluster member.
- `withConnectionAcquisitionTimeout`: thời gian tối đa chờ lấy connection từ pool.
- `withConnectionTimeout`: thời gian tối đa thiết lập socket connection mới.
- `withMaxTransactionRetryTime`: tổng thời gian managed transaction được phép retry.

Ví dụ cấu hình Driver độc lập:

~~~java
import java.util.concurrent.TimeUnit;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

Config config = Config.builder()
    .withMaxConnectionPoolSize(100)
    .withConnectionAcquisitionTimeout(10, TimeUnit.SECONDS)
    .withConnectionTimeout(5, TimeUnit.SECONDS)
    .build();

Driver driver = GraphDatabase.driver(
    "neo4j+s://graph.example.com:7687",
    AuthTokens.basic(username, password),
    config
);
~~~

Các giá trị trên chỉ minh họa cách cấu hình, không phải khuyến nghị áp dụng nguyên trạng cho mọi workload. Trong Spring Boot, không tạo Driver thứ hai chỉ để thay đổi pool size; hãy tùy chỉnh Driver bean mà ứng dụng đang dùng theo cơ chế cấu hình của phiên bản Spring Boot/Neo4j Driver hiện tại.

Đừng tăng `maxConnectionPoolSize` khi chưa biết vì sao connection đang bị giữ. Pool lớn hơn có thể tăng áp lực lên Neo4j, đặc biệt khi ứng dụng chạy nhiều replica. Hãy tính tổng connection tiềm năng trên tất cả pod/instance và so với khả năng của server.

## 11. Phân biệt các loại timeout

| Timeout | Lớp áp dụng | Điều gì hết hạn? | Hướng xử lý |
|---|---|---|---|
| Connection timeout | Driver/network | Thiết lập socket tới server | Kiểm tra network, DNS, Bolt endpoint và server |
| Connection acquisition timeout | Driver pool | Chờ connection rảnh hoặc tạo connection mới | Kiểm tra session leak, query giữ connection lâu, concurrency và pool capacity |
| Transaction timeout | Neo4j transaction | Thời gian transaction thực thi vượt giới hạn | Tối ưu query, giảm transaction scope hoặc đặt timeout phù hợp |
| Lock acquisition timeout | Neo4j locking | Chờ lock quá thời gian cho phép | Điều tra transaction cạnh tranh và thứ tự cập nhật |
| Managed transaction retry time | Driver retry | Hết thời gian thử lại lỗi transient | Kiểm tra cluster/network/server và tính idempotent của callback |
| HTTP/request timeout | Web server hoặc caller | Caller ngừng chờ response | Đồng bộ deadline với transaction và chính sách hủy |

Không dùng connection timeout để xử lý Cypher chạy chậm. Không tăng transaction timeout để chữa pool cạn. Cũng không tăng HTTP timeout nếu database query đang bị khóa hoặc scan quá lớn.

## 12. Đặt transaction timeout ở đúng lớp

Với Spring transaction manager, có thể đặt timeout cho service boundary nếu transaction manager hỗ trợ timeout:

~~~java
@Transactional(
    timeout = 5
)
public Order loadOrderGraph(String orderId) {
    return orders.findDetailedOrder(orderId)
        .orElseThrow();
}
~~~

Giá trị `timeout` của Spring được tính theo giây. Xác nhận transaction manager SDN và phiên bản đang dùng có áp dụng timeout đó như mong đợi. Timeout của Spring transaction không đồng nghĩa với socket connection timeout hay HTTP timeout.

Khi dùng Java Driver trực tiếp, có thể cấu hình timeout cho transaction:

~~~java
import java.time.Duration;
import java.util.Map;

import org.neo4j.driver.TransactionConfig;

try (var session = driver.session()) {
    var result = session.executeRead(
        tx -> tx.run("""
                MATCH (o:Order {orderId: $orderId})
                RETURN o
                """, Map.of("orderId", orderId))
            .single(),
        TransactionConfig.builder()
            .withTimeout(Duration.ofSeconds(5))
            .withMetadata(Map.of("operation", "load-order"))
            .build()
    );
}
~~~

Transaction timeout phía Driver yêu cầu server chấm dứt transaction vượt thời gian cấu hình. Metadata giúp nhận diện transaction trong `SHOW TRANSACTIONS` và query log; không đưa password, token hay dữ liệu cá nhân vào metadata.

Neo4j cũng có cấu hình mặc định phía server:

~~~properties
db.transaction.timeout=30s
db.lock.acquisition.timeout=5s
~~~

`db.transaction.timeout` là thời gian mặc định cho transaction nếu client không đặt timeout riêng; giá trị `0` tắt giới hạn mặc định. Timeout tùy chỉnh do Driver gửi có thể ghi đè timeout mặc định server. `db.lock.acquisition.timeout` giới hạn thời gian chờ một lock. Hãy thay đổi các setting này theo chính sách vận hành của DBMS và đánh giá tác động tới mọi ứng dụng dùng chung database.

## 13. Đừng nhầm transaction timeout với thời gian retry

Managed transaction của Driver có thể tự chạy lại callback khi gặp lỗi transient, ví dụ server tạm thời không khả dụng. `withMaxTransactionRetryTime` giới hạn tổng thời gian Driver thử lại. Nó không phải giới hạn thời gian một query Cypher được phép chạy trong server.

Vì callback có thể được gọi nhiều lần:

- Chỉ đặt các thao tác database có thể chạy lại an toàn trong callback.
- Không gửi email, gọi payment gateway hoặc publish message trực tiếp bên trong callback nếu thao tác đó không idempotent.
- Không sửa biến global hoặc tích lũy side effect ở bên ngoài transaction.
- Dùng idempotency key hoặc outbox pattern nếu transaction cần phối hợp với hệ thống bên ngoài.

Nếu callback thất bại vì lỗi nghiệp vụ không thể retry, hãy để exception phù hợp thoát ra và xử lý theo rollback rule. Không retry vô hạn một lỗi dữ liệu hoặc lỗi cấu hình.

## 14. Điều tra transaction đang chạy và lock wait

Khi nghi ngờ transaction giữ connection hoặc chờ lock quá lâu, dùng tài khoản vận hành để kiểm tra:

~~~cypher
SHOW TRANSACTIONS YIELD *;
~~~

Tìm các transaction có thời gian chạy dài, query hiện tại, trạng thái chờ, metadata hoặc thông tin client. Nếu nhiều transaction cùng chờ lock, kiểm tra query cập nhật chung một node/relationship, thứ tự ghi và thời gian giữ transaction.

Neo4j có giới hạn số transaction đồng thời. Khi chạm giới hạn, có thể gặp status code:

~~~text
Neo.TransientError.Transaction.MaximumTransactionLimitReached
~~~

Lock acquisition timeout có thể xuất hiện dưới dạng:

~~~text
Neo.TransientError.Transaction.LockAcquisitionTimeout
~~~

Đây là dấu hiệu về năng lực transaction hoặc cạnh tranh lock ở server, không phải bằng chứng pool phía client bị cạn. Kiểm tra cả hai lớp bằng metrics và log. Không tăng giới hạn transaction đồng thời hoặc tắt lock timeout khi chưa xác định query và workload gây ra tình trạng đó.

## 15. Chẩn đoán timeout theo dấu hiệu

| Dấu hiệu/log | Có thể là | Kiểm tra |
|---|---|---|
| Lỗi chờ connection acquisition | Pool không cấp được connection đúng hạn | Session leak, transaction mở lâu, pool size, concurrency |
| Connection timeout khi mở socket | Không thiết lập được kết nối mới | Network, Bolt port, DNS, server load |
| Query bị server terminate do transaction timeout | Transaction vượt giới hạn | `db.transaction.timeout`, custom transaction timeout, query plan |
| Lock acquisition timeout | Transaction chờ lock | `SHOW TRANSACTIONS`, writer contention, transaction scope |
| `MaximumTransactionLimitReached` | DBMS đạt giới hạn transaction đồng thời | Tổng concurrency, transaction kéo dài, server capacity |
| `ConnectionReadTimeoutException` | Client không nhận được dữ liệu trong thời gian server quy định cho connection | Query/stream quá lâu, server/network, connection state |
| HTTP 504 nhưng query có thể vẫn chạy | Deadline HTTP ngắn hơn công việc database hoặc cancellation không truyền như dự kiến | Web timeout, reactive cancellation, transaction timeout |
| `UnexpectedRollbackException` | Transaction đã bị đánh dấu rollback-only | Exception trước đó, nested/participating transaction, rollback rule |

Đọc root cause và Neo4j error code thay vì chỉ dựa vào HTTP status. Nếu request timeout xảy ra sau khi commit đã hoàn tất nhưng response bị mất, client có thể không biết kết quả đã được ghi hay chưa. Với thao tác ghi có thể được gọi lại, hãy thiết kế idempotency để tránh tạo dữ liệu trùng.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ query không trả record là transaction rollback | Query có thể match zero rows nhưng vẫn commit | Kiểm tra parameters, match count và query counters |
| Đặt `@Transactional` trên method rồi gọi nội bộ cùng class | Lời gọi không đi qua proxy | Tách bean hoặc đặt boundary ở method được gọi từ bên ngoài |
| Dùng nhầm JDBC transaction manager cho thao tác SDN | Transaction Neo4j không được quản lý như dự kiến | Chỉ định transaction manager Neo4j |
| Bắt và nuốt exception trong transaction | Transaction có thể commit một phần logic đã chạy | Ném lại exception hoặc khai báo rollback rule |
| Ném checked exception nhưng kỳ vọng rollback mặc định | Spring mặc định không rollback checked exception | Dùng `rollbackFor` phù hợp |
| Gọi `subscribe()` trong reactive service | Công việc tách khỏi transaction publisher | Compose publisher và trả về `Mono`/`Flux` |
| Quên `tx.commit()` với explicit Driver transaction | Transaction bị rollback khi đóng | Gọi commit rõ ràng hoặc dùng managed transaction |
| Không đóng session Driver | Connection/socket bị giữ, pool cạn | `try-with-resources` hoặc `finally` |
| Chia sẻ một session giữa nhiều thread | Race condition và lỗi transaction/session | Mỗi luồng tạo session riêng; dùng chung Driver |
| Tạo Driver cho mỗi request | Nhiều pool và nhiều connection không cần thiết | Dùng Driver singleton |
| Tăng pool size để chữa query chậm | Server chịu nhiều tải hơn, query vẫn chậm | Đo connection hold time, tối ưu query và transaction |
| Dùng connection timeout để sửa query timeout | Điều chỉnh sai lớp | Chọn đúng loại timeout theo bảng phân biệt |
| Tăng transaction timeout mà không kiểm tra lock wait | Transaction giữ lock lâu hơn | Điều tra contention và query đang chờ |
| Retry callback có side effect ngoài database | Email/payment/message có thể bị gửi nhiều lần | Thiết kế callback idempotent và dùng outbox khi cần |

## 17. Quy trình xử lý từ triệu chứng đến nguyên nhân

1. Xác định thao tác có thực sự match dữ liệu và tạo update bằng cách kiểm tra parameters, record count và query counters.
2. Xác nhận transaction boundary: method có được gọi qua Spring proxy, có dùng đúng Neo4j transaction manager và có kết thúc bình thường không.
3. Kiểm tra exception/rollback rule, nhất là checked exception, exception bị bắt và transaction rollback-only.
4. Nếu dùng Driver trực tiếp, xác nhận explicit transaction có `commit()` và mọi session/transaction được đóng.
5. Với reactive flow, xác nhận publisher được trả về, không tự `subscribe()` hoặc `block()`, và cancellation được xử lý.
6. Nếu pool cạn, kiểm tra session leak, result stream chưa tiêu thụ, transaction dài và số Driver instance.
7. Đo connection acquisition wait, query latency, concurrency và pool utilization trước khi đổi pool size.
8. Phân biệt connection timeout, acquisition timeout, transaction timeout, lock timeout, retry time và HTTP deadline.
9. Dùng `SHOW TRANSACTIONS YIELD *`, query log và status code để tìm query/transaction giữ tài nguyên.
10. Chỉ điều chỉnh đúng lớp timeout hoặc pool sau khi có số đo; chạy lại workload đại diện và theo dõi lỗi, latency, lock wait và số connection.

## 18. Tự kiểm tra

1. Vì sao query `MATCH ... SET` có thể thành công nhưng không cập nhật property?
2. Vì sao `@Transactional` không có hiệu lực khi một method gọi method transactional khác trong cùng class?
3. Spring mặc định rollback với runtime exception và checked exception khác nhau như thế nào?
4. Vì sao reactive service phải trả publisher thay vì tự gọi `subscribe()`?
5. Điều gì xảy ra khi đóng explicit Driver transaction mà chưa gọi `commit()`?
6. Vì sao Driver nên được dùng chung còn session phải được đóng và không chia sẻ giữa nhiều thread?
7. Connection acquisition timeout khác transaction timeout như thế nào?
8. Khi nào cần kiểm tra `db.lock.acquisition.timeout` thay vì tăng connection pool?
9. Vì sao managed transaction callback phải idempotent?
10. Khi HTTP request timeout, vì sao client có thể không biết thao tác ghi đã commit hay chưa?

Khi SDN báo giao dịch không có hiệu lực, pool cạn hoặc query timeout, hãy xác định trước transaction có thực sự chạy và commit, connection có được trả về pool, hay một deadline cụ thể đã hết hạn. Sửa transaction boundary và rollback rule cho đúng; đóng session/transaction đúng vòng đời; sau đó mới điều chỉnh pool hoặc timeout dựa trên số đo. Cách tiếp cận theo từng lớp giúp tránh tăng tải Neo4j và làm sự cố khó chẩn đoán hơn.

Tài liệu tham khảo:

- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Boot – Working with Neo4j repositories and reactive transaction management](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Data Neo4j – Neo4jTransactionManager API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
- [Neo4j Java Driver – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver – Config.ConfigBuilder API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Config.ConfigBuilder.html)
- [Neo4j Operations Manual – Database transactions](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)
- [Neo4j Operations Manual – Concurrent data access and lock timeout](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Status Codes – Errors](https://neo4j.com/docs/status-codes/current/errors/all-errors/)
