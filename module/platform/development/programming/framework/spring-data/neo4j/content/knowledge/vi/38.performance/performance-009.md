# Pool, fetch size và backpressure khi có nhiều yêu cầu

Bài học này thuộc chương **Hiệu năng** của module **SPRING_DATA_NEO4J**. Khi nhiều request cùng truy cập Neo4j, hiệu năng phụ thuộc vào số kết nối đang được sử dụng, thời gian mỗi truy vấn giữ kết nối, số record được kéo về mỗi đợt và tốc độ ứng dụng xử lý kết quả. Spring Data Neo4j dùng Neo4j Java Driver để quản lý kết nối; Driver cung cấp connection pool, còn giao thức Bolt và reactive API hỗ trợ lấy kết quả theo đợt và điều tiết luồng dữ liệu.

Ba khái niệm cần phân biệt:

- **Connection pool** giới hạn số kết nối Bolt mà một Driver có thể sử dụng đồng thời và thời gian phải chờ khi pool đã hết chỗ.
- **Fetch size** quy định số record trong mỗi đợt kéo dữ liệu đối với API đồng bộ/bất đồng bộ của Driver.
- **Backpressure** cho phép consumer điều khiển tốc độ nhận record trong reactive flow để nguồn không đẩy dữ liệu nhanh hơn khả năng xử lý.

Ba cơ chế này giải quyết các nút thắt khác nhau. Tăng pool không làm query nặng chạy nhanh hơn; giảm fetch size không giới hạn số request đồng thời; và backpressure của một `Flux` không tự đặt giới hạn tổng số request đang chạy trong toàn ứng dụng.

## 1. Luồng tài nguyên khi có nhiều request

Một request dùng repository thường đi qua các bước:

1. Controller hoặc service gọi repository.
2. Spring Data Neo4j tạo session/transaction thông qua Driver.
3. Driver mượn một kết nối phù hợp từ pool hoặc tạo kết nối mới nếu còn chỗ.
4. Cypher được gửi tới Neo4j và kết quả được trả về theo giao thức Bolt.
5. Ứng dụng ánh xạ và xử lý record.
6. Khi transaction/session và kết quả hoàn tất, kết nối được trả về pool để request khác dùng.

~~~text
HTTP requests
     |
     v
Spring service / repository
     |
     v
Neo4j Java Driver
     |
     +---- connection pool ----------------------+
     |     idle connections                      |
     |     in-use connections                     |
     |     waiters khi pool đã đầy                |
     +--------------------------------------------+
     |
     v
Neo4j server
     |
     v
records theo batch hoặc theo reactive demand
     |
     v
mapping / xử lý / HTTP response
~~~

Nếu tất cả kết nối đang được giữ bởi query hoặc transaction dài, request mới phải đợi. Nếu kết quả lớn và ứng dụng đọc chậm, kết nối có thể bị giữ lâu hơn. Vì vậy, phải xem cả pool, thời gian query và vòng đời tiêu thụ kết quả khi điều tra hiện tượng chờ kết nối.

## 2. Driver, Session và connection pool

`Driver` là đối tượng quản lý cấu hình kết nối, routing và pool. Neo4j Java Driver thiết kế `Driver` để dùng chung giữa các thread; đối tượng này thread-safe, immutable và tốn chi phí khởi tạo. Ứng dụng nên dùng một bean `Driver` dùng chung trong application context.

`Session` đại diện cho một kênh làm việc với database. Tạo session là thao tác nhẹ, nhưng session không thread-safe và phải được đóng sau khi dùng. Trong code imperative, dùng try-with-resources nếu tự làm việc trực tiếp với Driver:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public class PersonQuery {

    private final Driver driver;

    public PersonQuery(Driver driver) {
        this.driver = driver;
    }

    public long countPeople() {
        try (Session session = driver.session()) {
            return session.run("MATCH (p:Person) RETURN count(p) AS total")
                .single()
                .get("total")
                .asLong();
        }
    }
}
~~~

Với Spring Data Neo4j, repository và template quản lý session theo hạ tầng của SDN. Không tự mở thêm `Driver` hoặc `Session` trong mỗi request nếu không có lý do rõ ràng. Nếu tự mở session, phải bảo đảm session và result được tiêu thụ, đóng đúng vòng đời.

Không lưu `Session` vào field của singleton service hoặc chia sẻ một session cho nhiều request. Chia sẻ bean `Driver`; để mỗi thao tác tạo session riêng thông qua SDN hoặc Driver.

## 3. Pool chứa kết nối đang dùng và kết nối rảnh

Connection pool giữ các kết nối Bolt để tái sử dụng. Pool có giới hạn tối đa, bao gồm cả kết nối đang được dùng và kết nối đang rảnh. Khi query kết thúc và session giải phóng tài nguyên, kết nối có thể trở lại trạng thái idle để request tiếp theo sử dụng.

Neo4j Java Driver 6.3 có các giá trị mặc định quan trọng:

| Cấu hình | Mặc định | Ý nghĩa |
|---|---:|---|
| `maxConnectionPoolSize` | `100` | Số kết nối tối đa trong pool theo phạm vi endpoint/database |
| `connectionAcquisitionTimeout` | `60 giây` | Thời gian tối đa chờ lấy được kết nối phù hợp |
| `connectionTimeout` | `30 giây` | Thời gian thiết lập socket connection |
| `maxConnectionLifetime` | `1 giờ` | Tuổi tối đa của một kết nối trước khi được loại khỏi pool khi acquisition |

Với URI `bolt://`, giới hạn pool áp dụng cho tổng số kết nối tới endpoint trực tiếp. Với routing URI `neo4j://`, giới hạn `maxConnectionPoolSize` áp dụng theo từng cluster member. Vì vậy, không được diễn giải `100` là tổng số kết nối của cả cụm trong mọi cấu hình.

Khi pool đạt giới hạn, Driver chờ kết nối được trả về trong khoảng `connectionAcquisitionTimeout`. Nếu hết thời gian mà không lấy được kết nối, thao tác phát lỗi. Đặt acquisition timeout bằng `0` sẽ tắt giới hạn thời gian chờ; điều đó có thể khiến request chờ vô thời hạn khi pool bị nghẽn.

## 4. Tính pool theo concurrency và thời gian giữ kết nối

Pool nên được chọn dựa trên tải thực tế và khả năng xử lý của Neo4j, không dựa đơn thuần vào số thread của web server.

Một ước lượng hữu ích là định luật Little:

\[
L \approx \lambda \times W
\]

Trong đó:

- `L` là số thao tác đang hoạt động trung bình.
- `\lambda` là số thao tác database bắt đầu mỗi giây.
- `W` là thời gian trung bình một thao tác giữ tài nguyên kết nối, tính bằng giây.

Ví dụ, nếu ứng dụng phát sinh trung bình 40 thao tác DB mỗi giây và mỗi thao tác giữ kết nối khoảng 0,15 giây, concurrency trung bình xấp xỉ 6 kết nối. Đây chỉ là ước lượng trung bình; giờ cao điểm, độ lệch latency và truy vấn dài tạo ra nhu cầu cao hơn. Hãy đo p95/p99 và kiểm tra tải đỉnh trước khi chọn giới hạn.

Các nguyên tắc:

- Pool quá nhỏ tạo hàng chờ và tăng acquisition latency.
- Pool quá lớn có thể đẩy quá nhiều query đồng thời sang Neo4j, làm tăng CPU, memory, lock contention và thời gian query.
- Query chậm giữ kết nối lâu hơn, khiến pool trông như thiếu kết nối dù nguyên nhân gốc là query plan hoặc dữ liệu.
- Một transaction kéo dài qua nhiều bước ứng dụng làm kết nối bị giữ lâu hơn cần thiết.
- Khi tăng số replica ứng dụng, mỗi replica có Driver và pool riêng; tổng kết nối có thể tăng theo số replica.

Ví dụ, 5 replica cùng dùng pool tối đa 80 có thể mở ra quy mô kết nối tiềm năng lớn hơn nhiều so với một replica. Với routing driver, còn phải tính giới hạn theo từng cluster member. Luôn đối chiếu tổng tải kết nối với giới hạn và năng lực của Neo4j cluster.

## 5. Tùy chỉnh pool qua Spring Boot

Spring Boot tự cấu hình `Driver` khi dùng `spring-boot-starter-data-neo4j`. Có thể giữ auto-configuration và tinh chỉnh `Config.ConfigBuilder` bằng bean `ConfigBuilderCustomizer`.

Ví dụ dưới đây dùng package của Spring Boot 3.x:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.boot.autoconfigure.neo4j.ConfigBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class Neo4jDriverConfiguration {

    @Bean
    ConfigBuilderCustomizer neo4jPoolCustomizer() {
        return config -> config
            .withMaxConnectionPoolSize(80)
            .withConnectionAcquisitionTimeout(5, TimeUnit.SECONDS)
            .withConnectionTimeout(3, TimeUnit.SECONDS)
            .withFetchSize(500);
    }
}
~~~

Các số `80`, `5 giây`, `3 giây` và `500` chỉ minh họa cách cấu hình, không phải khuyến nghị chung cho production. Hãy bắt đầu từ giá trị mặc định, đo tải, sau đó thay đổi từng tham số và so sánh kết quả.

Spring Boot 4 chuyển package `ConfigBuilderCustomizer` sang `org.springframework.boot.neo4j.autoconfigure`. Hãy dùng package tương ứng với major version Spring Boot của ứng dụng.

Nếu tự tạo `Driver` bằng `GraphDatabase.driver(...)`, truyền `Config` được tạo từ `Config.builder()` và chịu trách nhiệm quản lý vòng đời/đóng Driver. Trong ứng dụng Boot thông thường, ưu tiên customizer để không vô tình thay thế bean Driver mà SDN đang dùng.

## 6. Không tạo Driver hoặc Session mới cho từng request

Một lỗi thường gặp là tạo Driver mỗi lần xử lý request:

~~~java
import java.util.Map;

import org.neo4j.driver.AuthToken;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

// Không nên: mỗi lần gọi lại tạo một Driver và một pool mới.
public String findPersonName(String uri, AuthToken authToken, String id) {
    Driver driver = GraphDatabase.driver(uri, authToken);
    try {
        try (Session session = driver.session()) {
            return session.run(
                    "MATCH (p:Person {id: $id}) RETURN p.name AS name",
                    Map.of("id", id))
                .single()
                .get("name")
                .asString();
        }
    } finally {
        driver.close();
    }
}
~~~

Mỗi Driver có pool, event loop và tài nguyên mạng riêng. Tạo Driver liên tục làm tăng chi phí handshake, connection churn và số socket. Hãy inject một bean Driver dùng chung:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.stereotype.Repository;

@Repository
public class PersonLookup {

    private final Driver driver;

    public PersonLookup(Driver driver) {
        this.driver = driver;
    }
}
~~~

Nếu cần truy cập nhiều database hoặc user, cấu hình session/database selection hoặc impersonation theo API Driver/SDN thay vì tạo một Driver mới cho mỗi request.

## 7. Session và result phải được giải phóng

Một session đang làm việc gắn với tài nguyên kết nối. Nếu không đóng session, ứng dụng có thể làm cạn pool hoặc rò rỉ socket. Với API đồng bộ, luôn tiêu thụ kết quả trong phạm vi session và đóng session:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public void streamNames(Driver driver) {
    try (Session session = driver.session(
            SessionConfig.builder()
                .withDatabase("neo4j")
                .build())) {

        Result result = session.run("""
            MATCH (p:Person)
            RETURN p.name AS name
            ORDER BY name
            """);

        while (result.hasNext()) {
            Record record = result.next();
            consumeName(record.get("name").asString());
        }
    }
}
~~~

Không trả một `Result` chưa tiêu thụ ra ngoài rồi đóng session ngay. Hãy đọc hết kết quả hoặc dùng API reactive với vòng đời resource gắn trong publisher. Khi kết quả lớn, tránh gọi `list()` nếu không cần giữ toàn bộ record trong bộ nhớ.

Trong Spring Data Neo4j, để repository/template quản lý session. Không cần tự đóng tài nguyên nội bộ do SDN quản lý.

## 8. Fetch size là gì?

Từ Bolt 4 trở đi, Driver có thể kéo record theo nhiều batch thay vì yêu cầu toàn bộ kết quả trong một lần. `fetchSize` là số record tối đa được yêu cầu trong mỗi batch đối với kết quả từ API `Session` và `AsyncSession`.

Neo4j Java Driver 6.3 đặt mặc định `fetchSize` là `1000`. Có thể thay đổi mặc định bằng `Config.ConfigBuilder.withFetchSize(...)` hoặc ghi đè cho một session bằng `SessionConfig.Builder.withFetchSize(...)`.

Fetch size ảnh hưởng đến:

- Số lần trao đổi mạng cần để tiêu thụ toàn bộ kết quả.
- Số record mà Driver giữ trong buffer khi consumer chưa xử lý xong.
- Bộ nhớ phía client dùng cho kết quả chưa tiêu thụ.
- Độ trễ và throughput khi truy vấn trả nhiều record.

Fetch size không phải giới hạn tổng số record trả về, không giới hạn số query đồng thời và không làm giảm công việc Cypher phải thực hiện trên server. Một query vẫn có thể quét hoặc mở rộng nhiều node trước khi trả record đầu tiên.

## 9. Chọn fetch size lớn hay nhỏ

Fetch size tạo ra một đánh đổi:

| Fetch size | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Nhỏ | Buffer phía client nhỏ hơn; consumer có thể điều tiết dữ liệu thường xuyên hơn | Nhiều lần pull/round trip hơn, tăng overhead mạng khi kết quả lớn |
| Lớn | Ít lần pull hơn; có thể tăng throughput khi mạng và consumer xử lý nhanh | Buffer lớn hơn, tăng memory; có thể tải nhiều record về trước khi ứng dụng xử lý xong |
| `-1` (sync/async) | Driver kéo toàn bộ kết quả sau mỗi query run | Tắt batching/backpressure theo fetch size; không phù hợp với kết quả lớn nếu bộ nhớ có hạn |

Không có một giá trị tối ưu cho mọi query. Kết quả vài chục record thường không cần tinh chỉnh. Với hàng trăm nghìn record, cần đo memory, thời gian tiêu thụ, round trip và tốc độ xử lý downstream.

Một nguyên tắc an toàn là bắt đầu ở mặc định `1000`, sau đó thử các mức thấp hơn hoặc cao hơn với tập dữ liệu đại diện. Không đặt `-1` để “tăng tốc” khi chưa biết kích thước kết quả và giới hạn heap.

## 10. Đặt fetch size toàn Driver hoặc theo Session

Đặt mặc định ở Driver:

~~~java
import org.neo4j.driver.Config;

Config config = Config.builder()
    .withFetchSize(500)
    .build();
~~~

Ghi đè ở một session đồng bộ:

~~~java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

try (Session session = driver.session(
        SessionConfig.builder()
            .withDatabase("neo4j")
            .withFetchSize(200)
            .build())) {
    // Các kết quả từ Session này dùng fetch size 200.
}
~~~

Session-level fetch size ghi đè giá trị mặc định của Driver cho session đó. Cách này hữu ích khi một số tác vụ batch đọc lượng dữ liệu lớn, trong khi truy vấn request thông thường cần hành vi khác.

Lưu ý quan trọng: `withFetchSize` áp dụng cho result từ `Session` và `AsyncSession`. Với reactive session, batch pulling được điều khiển bởi subscription requests; không dùng fetch size như một nút điều khiển reactive backpressure.

## 11. Backpressure trong Reactive Streams

Trong reactive flow, subscriber quyết định số phần tử mình sẵn sàng nhận bằng demand. Driver điều chỉnh tốc độ yêu cầu record từ Neo4j theo demand đó. Nếu downstream xử lý chậm, nguồn có thể tạm dừng kéo batch tiếp theo thay vì đẩy một lượng record không giới hạn vào bộ nhớ client.

Luồng khái niệm:

~~~text
Reactor subscriber
      |
      | request(n)
      v
Spring Data Neo4j reactive publisher
      |
      v
Neo4j Driver ReactiveSession
      |
      | pull record theo demand
      v
Neo4j server
      |
      v
onNext(record) -> xử lý -> request tiếp
~~~

Backpressure đặc biệt hữu ích khi ứng dụng đọc nhiều record và phải xử lý mỗi record bằng bước tốn thời gian. Consumer có thể yêu cầu dữ liệu theo tốc độ xử lý thay vì nhận toàn bộ kết quả ngay lập tức.

Reactive session không sử dụng `fetchSize` như session đồng bộ. Kích thước batch và nhịp kéo dữ liệu reactive được quản lý qua subscription requests.

## 12. Giữ vòng đời ReactiveSession trong publisher

Khi dùng `ReactiveNeo4jRepository`, `ReactiveNeo4jTemplate` hoặc `ReactiveNeo4jClient`, SDN quản lý session và resource. Nếu tích hợp trực tiếp Neo4j Java Driver reactive API, session phải được tạo khi subscription bắt đầu và đóng khi publisher hoàn tất, lỗi hoặc bị hủy.

Neo4j Driver hướng dẫn dùng `Flux.usingWhen(...)` để gắn vòng đời session với reactive chain:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.reactivestreams.ReactiveResult;
import org.neo4j.driver.reactivestreams.ReactiveSession;
import org.neo4j.driver.Record;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Flux<Record> streamPeople(Driver driver) {
    return Flux.usingWhen(
        Mono.fromSupplier(() -> driver.session(
            ReactiveSession.class,
            SessionConfig.builder()
                .withDatabase("neo4j")
                .build()
        )),
        session -> Mono.fromDirect(
                session.run("MATCH (p:Person) RETURN p.name AS name"))
            .flatMapMany(ReactiveResult::records),
        ReactiveSession::close
    );
}
~~~

Không tạo `ReactiveSession` bên ngoài pipeline rồi giữ nó chờ publisher được subscribe. Một session chưa chạy query nhưng đã mở có thể giữ tài nguyên và làm cạn số session/kết nối khả dụng. Trong ứng dụng SDN, ưu tiên `ReactiveNeo4jClient` hoặc repository reactive để framework quản lý vòng đời.

Cancellation cũng cần được xử lý: khi HTTP client ngắt kết nối hoặc subscriber hủy, cleanup của reactive resource phải chạy để giải phóng session và kết nối.

## 13. Backpressure không phải giới hạn tổng số request

Backpressure hoạt động trong từng reactive subscription. Nếu có 500 HTTP request đồng thời và mỗi request subscribe một query, mỗi pipeline vẫn có thể tạo nhu cầu truy cập database. Backpressure giúp mỗi pipeline không nhận record nhanh hơn consumer của chính nó, nhưng không tự giới hạn 500 pipeline thành 50 query đồng thời.

Muốn giới hạn fan-out trong một pipeline, đặt concurrency cho `flatMap`:

~~~java
import com.example.graph.domain.Person;
import reactor.core.publisher.Flux;

public Flux<Person> loadPeople(Flux<String> ids) {
    return ids.flatMap(
        id -> personRepository.findById(id),
        32
    );
}
~~~

Tham số `32` giới hạn số inner publisher được subscribe đồng thời trong pipeline này. Nó không phải giới hạn toàn cục cho mọi HTTP request trong ứng dụng.

Nếu cần giới hạn tổng số truy vấn từ toàn service, dùng cơ chế bulkhead/semaphore hoặc giới hạn concurrency tại ingress/service layer. Đặt giới hạn theo năng lực database và kiểm thử tải thực tế.

## 14. limitRate, buffer và collectList

`limitRate(n)` điều chỉnh cách Reactor yêu cầu dữ liệu upstream theo các đợt. Nó hữu ích để kiểm soát demand của một pipeline:

~~~java
import com.example.graph.domain.Person;
import reactor.core.publisher.Flux;

public Flux<Person> streamPeople() {
    return personRepository.findAll()
        .limitRate(128);
}
~~~

`limitRate` không thay thế pool size và cũng không đặt giới hạn tổng request trên toàn ứng dụng.

`onBackpressureBuffer()` tạo buffer để giữ dữ liệu khi downstream không theo kịp. Buffer có thể tăng bộ nhớ nếu nguồn liên tục phát nhanh hơn consumer; nên đặt giới hạn và chính sách xử lý overflow nếu thật sự cần buffer. Với Neo4j reactive driver có khả năng phản hồi demand, ưu tiên truyền backpressure ngược tới nguồn thay vì đệm không giới hạn.

Tránh gom một `Flux` lớn thành `List`:

~~~java
Mono<List<Person>> allPeople = personRepository.findAll()
    .collectList();
~~~

`collectList()` chờ toàn bộ kết quả và giữ tất cả entity trong heap. Với tập kết quả lớn, xử lý từng record, dùng phân trang hoặc xuất theo luồng. Nếu API bắt buộc trả JSON array rất lớn, cần đánh giá memory và thời gian giữ kết nối; streaming response hoặc endpoint phân trang thường phù hợp hơn.

## 15. Fetch size không thay thế LIMIT hoặc pagination

Fetch size kiểm soát cách Driver kéo record theo batch. Nó không giới hạn tổng số record mà query trả về. Nếu endpoint chỉ cần 50 kết quả, hãy giới hạn ngay trong Cypher hoặc dùng pagination:

~~~cypher
MATCH (p:Person)
WHERE p.active = true
RETURN p
ORDER BY p.id
LIMIT $limit
~~~

Với dữ liệu lớn, dùng keyset pagination theo một thuộc tính ổn định thay vì tăng `SKIP` quá lớn:

~~~cypher
MATCH (p:Person)
WHERE p.id > $afterId
RETURN p
ORDER BY p.id
LIMIT $pageSize
~~~

Phân trang giảm số record được trả và thời gian giữ tài nguyên. Fetch size sau đó chỉ quyết định cách kéo từng batch trong phạm vi kết quả đã giới hạn.

## 16. Transaction dài làm pool nhanh đầy

Một transaction thường giữ kết nối trong suốt thời gian cần thiết để thực thi và hoàn tất. Nếu transaction bao trùm cả xử lý nghiệp vụ, gọi HTTP service khác hoặc chờ người dùng, pool có thể bị chiếm dụng lâu hơn mức cần thiết.

Ví dụ nên tránh:

Đây là đoạn minh họa ranh giới transaction; các dependency đã được inject vào service:

~~~java
@Transactional
public void processOrder(Order order) {
    orderRepository.save(order);
    paymentGateway.charge(order);  // I/O ngoài database trong transaction
    notificationClient.send(order); // tiếp tục chờ dịch vụ khác
}
~~~

Nếu gọi dịch vụ ngoài mất vài giây, transaction Neo4j có thể giữ tài nguyên trong toàn bộ thời gian đó. Hãy thu hẹp transaction vào phần đọc/ghi graph cần tính nguyên tử; thực hiện các I/O bên ngoài ở ranh giới phù hợp và thiết kế retry/outbox khi nghiệp vụ cần.

Với reactive transaction, giữ các thao tác database cần tính nguyên tử trong một pipeline, nhưng tránh nối các tác vụ chậm không cần thiết vào cùng transaction. Backpressure có thể làm chậm việc tiêu thụ record; nếu transaction còn mở trong suốt quá trình xử lý chậm, connection cũng có thể bị giữ lâu hơn.

## 17. Nhiều replica ứng dụng và tổng kết nối tới cluster

Pool thuộc về mỗi instance Driver trong mỗi process ứng dụng. Khi scale ngang, mỗi replica có pool riêng:

~~~text
Application replica A -> Driver A -> pool A
Application replica B -> Driver B -> pool B
Application replica C -> Driver C -> pool C
                         |
                         v
                    Neo4j cluster
~~~

Với URI routing `neo4j://`, Driver có thể có pool kết nối theo cluster member. Vì vậy, tổng kết nối tiềm năng phụ thuộc vào:

- Số replica ứng dụng.
- `maxConnectionPoolSize` mỗi Driver.
- Số cluster member mà Driver cần kết nối.
- Vai trò của member và loại query (read/write).
- Các ứng dụng, worker và công cụ khác cùng truy cập Neo4j.

Không tăng pool riêng lẻ trên từng replica mà không tính tổng. Ví dụ 10 replica với pool 100 có thể tạo ra tải kết nối tiềm năng rất lớn; trong routing driver, số kết nối có thể được nhân theo member. Đối chiếu với giới hạn kết nối, CPU, memory và khả năng xử lý của từng server.

## 18. Điều tiết tải khi có nhiều yêu cầu

Pool là giới hạn cuối ở tầng kết nối. Để bảo vệ database trong giờ cao điểm, ứng dụng nên có thêm kiểm soát concurrency ở tầng request:

- Đặt giới hạn số tác vụ DB đồng thời theo endpoint hoặc use case.
- Dùng bulkhead để một truy vấn nặng không chiếm hết năng lực phục vụ của các request quan trọng.
- Đặt timeout request phù hợp với acquisition timeout và query timeout.
- Dùng rate limit hoặc queue cho tác vụ batch/import thay vì bắn hàng nghìn query cùng lúc.
- Trả lỗi quá tải có kiểm soát khi hệ thống đã đạt giới hạn thay vì giữ request trong hàng đợi vô hạn.
- Tách workload đọc nặng, báo cáo hoặc export khỏi workload tương tác có latency thấp khi kiến trúc yêu cầu.

Không đặt acquisition timeout quá dài chỉ để giảm số lỗi hiển thị. Chờ lâu làm request và thread giữ tài nguyên lâu hơn, có thể tạo hiệu ứng dây chuyền khi tải tăng.

## 19. Theo dõi pool, query và consumer

Khi điều tra hiệu năng, theo dõi ít nhất ba lớp:

| Lớp | Chỉ số cần quan sát | Dấu hiệu nghẽn |
|---|---|---|
| Ứng dụng | Request rate, concurrency, p95/p99 latency, timeout, queue/bulkhead rejection | Request tăng nhanh hơn tốc độ hoàn thành |
| Driver/pool | Telemetry/log về connection đang dùng/rảnh (nếu có), acquisition latency, acquisition timeout, session leak | Pool thường xuyên chạm trần hoặc chờ lâu |
| Neo4j/query | Query duration, CPU, memory, lock wait, số record, execution plan | Query chậm hoặc server không xử lý thêm được |
| Consumer | Thời gian xử lý record, buffer size, cancellation, số phần tử được gom vào bộ nhớ | Downstream chậm, buffer tăng hoặc result bị giữ lâu |

Đừng kết luận pool thiếu chỉ vì thấy acquisition timeout. Kiểm tra query đang giữ kết nối bao lâu, có session không được đóng, có `collectList()` trên dữ liệu lớn hay transaction mở quá rộng không. Một query chậm do thiếu index có thể khiến pool bão hòa dù số request không thay đổi.

Khi dùng `EXPLAIN`/`PROFILE`, xác định query plan trước khi tăng concurrency. Tối ưu Cypher, index, số traversal và projection thường đem lại hiệu quả lớn hơn việc chỉ tăng pool.

## 20. Kiểm thử tải và chọn cấu hình

Một quy trình tuning có thể thực hiện theo các bước:

1. Đo baseline với pool và fetch size mặc định.
2. Chạy workload gần thực tế, gồm request đọc đơn giản, query graph nhiều bước và truy vấn trả nhiều record.
3. Ghi nhận throughput, p50/p95/p99, acquisition latency, timeout, CPU, memory và heap.
4. Xác định bottleneck là query/server, pool acquisition, network, mapping hay consumer.
5. Chỉ thay đổi một tham số mỗi lần: pool size, acquisition timeout, fetch size hoặc concurrency.
6. Lặp lại cùng workload và so sánh kết quả.
7. Kiểm tra khi scale số replica và khi có tác vụ batch chạy đồng thời.

Một ma trận kiểm thử hữu ích:

| Thử nghiệm | Pool | Fetch size | Consumer | Điều cần quan sát |
|---|---:|---:|---|---|
| Baseline | Mặc định | 1000 | Xử lý nhanh | Throughput và latency nền |
| Pool nhỏ | Thấp hơn baseline | 1000 | Xử lý nhanh | Acquisition wait và timeout |
| Pool lớn | Cao hơn baseline | 1000 | Xử lý nhanh | Server CPU/latency có tăng không |
| Batch nhỏ | Giữ nguyên | 200 | Xử lý chậm | Memory, round trip và thời gian hoàn tất |
| Batch lớn | Giữ nguyên | 2000 | Xử lý chậm | Buffer/heap và throughput |
| Reactive demand | Giữ nguyên | Theo subscription | Yêu cầu từng đợt | Backpressure, cancellation và session lifetime |

Không chọn cấu hình chỉ dựa vào throughput tối đa. Hãy ưu tiên latency ổn định, mức sử dụng tài nguyên có headroom và hành vi có thể dự đoán khi tải vượt ngưỡng.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Connection acquisition timed out` | Pool đầy, query giữ kết nối lâu, transaction dài hoặc session leak | Kiểm tra acquisition latency, query duration và vòng đời session trước khi tăng pool |
| Tăng pool nhưng query càng chậm | Neo4j nhận quá nhiều query đồng thời | Giảm concurrency, tối ưu query và đo năng lực server |
| Heap tăng khi đọc graph lớn | Fetch size quá cao, `collectList()` hoặc giữ result trong bộ nhớ | Giảm batch, streaming hoặc phân trang |
| Nhiều round trip khi đọc kết quả | Fetch size quá nhỏ so với kích thước record và mạng | Thử tăng fetch size với phép đo memory |
| Reactive request vẫn làm pool đầy | Backpressure từng subscription không giới hạn tổng request | Thêm bulkhead hoặc concurrency cap ở tầng ứng dụng |
| Session bị rò rỉ | Không đóng session hoặc không gắn cleanup vào reactive pipeline | Dùng try-with-resources hoặc `usingWhen` |
| Query result không hoàn tất | Result không được tiêu thụ hết hoặc không xử lý cancellation | Tiêu thụ/đóng result đúng vòng đời |
| Tăng replica làm số kết nối tăng đột biến | Mỗi replica có Driver và pool riêng | Tính tổng pool theo replica và cluster member |
| `fetchSize` không tác động reactive query | Reactive session dùng subscription demand để điều khiển batch | Điều chỉnh Reactor demand/operator, không dùng `withFetchSize` |
| Chờ kết nối lâu rồi request timeout | Acquisition timeout dài hơn ngân sách latency của request | Căn chỉnh timeout và giới hạn tải sớm hơn |

## 22. Nguyên tắc cần nhớ

- Dùng một bean `Driver` dùng chung; không tạo Driver cho từng request.
- Không chia sẻ `Session` giữa thread hoặc request; luôn giải phóng session và result.
- Pool giới hạn số kết nối đồng thời; mặc định Driver 6.3 là 100.
- Acquisition timeout mặc định là 60 giây; pool đầy sẽ chờ đến timeout rồi phát lỗi.
- Với `bolt://`, pool size giới hạn tổng kết nối tới endpoint; với `neo4j://`, giới hạn áp dụng theo cluster member.
- Tính pool theo concurrency và thời gian giữ kết nối, đồng thời tính tổng khi scale nhiều replica.
- `fetchSize` mặc định là 1000 cho kết quả từ Session/AsyncSession; có thể ghi đè theo session.
- `fetchSize` không giới hạn tổng số record, số query đồng thời hoặc công việc server phải làm.
- `fetchSize = -1` tắt batching/backpressure cho API đồng bộ/bất đồng bộ; tránh dùng với kết quả lớn.
- Reactive session điều tiết việc kéo record theo subscription demand; không dùng fetch size như cấu hình backpressure reactive.
- Backpressure từng pipeline không phải giới hạn tổng request; dùng concurrency cap/bulkhead khi cần.
- Giữ transaction ngắn, tối ưu Cypher và tránh gom kết quả lớn vào heap.
- Đo pool acquisition, query duration, consumer speed và tài nguyên Neo4j trước khi tuning.

Khi nhiều request cùng truy cập Neo4j, pool quyết định số kết nối có thể hoạt động đồng thời, fetch size điều chỉnh cách Driver lấy kết quả theo batch, còn backpressure cho phép reactive consumer điều khiển tốc độ nhận dữ liệu. Tách bạch ba cơ chế, quản lý session đúng vòng đời và giới hạn concurrency theo năng lực database sẽ giúp ứng dụng duy trì latency ổn định khi tải tăng.

## Tài liệu tham khảo

- [Neo4j Java Driver 6.3 – Config.ConfigBuilder API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Config.ConfigBuilder.html)
- [Neo4j Java Driver 6.3 – SessionConfig.Builder API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/SessionConfig.Builder.html)
- [Neo4j Java Driver Manual – Control results flow with reactive streams](https://neo4j.com/docs/java-manual/current/reactive/)
- [Neo4j Java Driver Manual – Run your own transactions and close sessions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Connection and Driver lifecycle](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual – Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/)
- [Spring Boot 3.5 – Working with Neo4j](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html)
- [Spring Boot 3.5 – ConfigBuilderCustomizer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/neo4j/ConfigBuilderCustomizer.html)
