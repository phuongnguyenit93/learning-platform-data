# Cấu hình timeout, retry và giới hạn tài nguyên theo môi trường

Ứng dụng Spring Data Neo4j (SDN) chạy ổn định khi thời gian chờ, chính sách retry và giới hạn tài nguyên được đặt theo cùng một ngân sách vận hành. Nếu mỗi lớp tự chờ quá lâu hoặc tự retry độc lập, một request có thể giữ session và connection lâu hơn cần thiết, tạo hàng đợi trong pool và làm tải database tăng thêm đúng lúc hệ thống đang gặp sự cố.

Cần phân biệt các lớp cấu hình: timeout kết nối, timeout chờ connection pool, timeout transaction trên Neo4j, retry budget của Neo4j Java Driver, kích thước connection pool, fetch size và giới hạn concurrency/memory phía DBMS. Các giá trị này có mục đích khác nhau; không thể thay thế cho nhau bằng một con số timeout chung.

Bài học tập trung vào cách tổ chức cấu hình cho local development, test, staging và production; cách đặt deadline có thứ tự; cách giới hạn retry an toàn; và cách đo tải trước khi tăng pool hoặc concurrency.

## 1. Bản đồ các lớp timeout và giới hạn

Một request gọi repository có thể đi qua nhiều lớp trước khi nhận kết quả:

~~~mermaid
flowchart TD
    A["HTTP request / caller deadline"] --> B["Service deadline"]
    B --> C["Lấy connection từ Driver pool"]
    C --> D["Mở transaction trên Neo4j"]
    D --> E["Chạy Cypher và đọc kết quả"]
    E --> F["Commit / rollback"]
    F --> G["Trả response"]
~~~

Mỗi lớp có một giới hạn riêng:

| Cấu hình | Kiểm soát điều gì? | Không có nghĩa là |
| --- | --- | --- |
| Request timeout | Thời gian caller chờ response | Neo4j chắc chắn đã dừng query khi client hết giờ |
| Connection timeout | Thời gian thiết lập kết nối mạng tới server theo cấu hình Driver | Thời gian query được phép chạy |
| Connection acquisition timeout | Thời gian chờ Driver cấp một connection phù hợp từ pool | Giới hạn số record hoặc số transaction |
| Transaction timeout | Thời gian một transaction được phép chạy trước khi Neo4j chấm dứt nó | Retry budget |
| Max transaction retry time | Khoảng thời gian tối đa Driver managed transaction được phép thử lại khi gặp lỗi retryable | Timeout của một lần query |
| Max connection pool size | Số connection tối đa trong pool | Số request tối đa của toàn bộ hệ thống |
| Fetch size | Số record được lấy theo từng batch trong một số kiểu session đồng bộ | Giới hạn tổng số record trả về |
| Transaction memory/concurrency limit | Tài nguyên transaction mà Neo4j cho phép tiêu thụ | Giới hạn heap của ứng dụng Java |

Một thứ tự deadline hữu ích là:

- Pool acquisition phải ngắn để request không xếp hàng quá lâu.
- Transaction timeout phải nhỏ hơn deadline của service.
- Tổng thời gian kết nối, chạy transaction và retry phải nằm trong deadline request.
- Request timeout ở gateway hoặc HTTP client nên lớn hơn một chút so với deadline nội bộ để ứng dụng có thời gian trả lỗi có kiểm soát.

Ví dụ, nếu API có deadline 5 giây, không nên cho Driver retry 30 giây rồi mới trả lỗi. Hãy dành phần ngân sách cho connection acquisition, transaction và serialization/response.

## 2. Cấu hình Driver bằng Spring Boot properties

Khi dùng spring-boot-starter-data-neo4j, Spring Boot tự cấu hình Neo4j Java Driver. Các thuộc tính kết nối và pool thường nằm dưới spring.neo4j:

~~~yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: from-local-secret
    connection-timeout: 5s
    max-transaction-retry-time: 3s
    pool:
      connection-acquisition-timeout: 2s
      max-connection-pool-size: 20
      max-connection-lifetime: 30m
      metrics-enabled: true
      log-leaked-sessions: false

  data:
    neo4j:
      database: neo4j
~~~

Ví dụ dùng giá trị local minh họa. Trong môi trường thật, URI, username, password và database nên được cấp từ environment variables hoặc secret manager. Không commit mật khẩu thật vào repository.

Các thuộc tính cần hiểu:

- spring.neo4j.uri: địa chỉ Bolt hoặc URI phù hợp với topology Neo4j.
- spring.neo4j.connection-timeout: timeout kết nối theo binding và mô tả của Spring Boot version đang dùng. Trong Spring Boot 3.4, property appendix mô tả nó là timeout mượn connection từ pool.
- spring.neo4j.max-transaction-retry-time: giới hạn thời gian Driver managed transactions được thử lại.
- spring.neo4j.pool.connection-acquisition-timeout: giới hạn thời gian chờ cấp connection từ pool.
- spring.neo4j.pool.max-connection-pool-size: giới hạn số connection trong pool.
- spring.neo4j.pool.max-connection-lifetime: tuổi tối đa của connection trước khi Driver loại bỏ nó.
- spring.neo4j.pool.metrics-enabled: bật metrics của pool nếu phiên bản Boot/Driver hỗ trợ.
- spring.neo4j.pool.log-leaked-sessions: hỗ trợ điều tra session không được đóng.
- spring.data.neo4j.database: database mặc định mà SDN sử dụng.

Tên property và package Java có thể thay đổi giữa các dòng Spring Boot. Hãy dùng configuration metadata và tài liệu đúng phiên bản mà dự án đang quản lý. Spring Boot 3.x và 4.x có thay đổi package của một số API cấu hình Neo4j.

## 3. Phân biệt connection timeout và connection acquisition timeout

Hai timeout này giải quyết hai vấn đề khác nhau.

**Connection timeout** liên quan đến việc thiết lập kết nối mạng tới Neo4j. Nếu DNS, TCP, TLS hoặc server handshake không hoàn tất trong thời gian cho phép, thao tác kết nối thất bại.

**Connection acquisition timeout** giới hạn thời gian Driver chờ một connection có thể sử dụng từ pool. Nếu pool đã đạt max size và các connection hiện tại đều đang bận, request mới phải chờ connection được trả về hoặc hết thời gian acquisition.

Ví dụ:

- Server không thể truy cập: connection establishment timeout có thể xảy ra.
- Server vẫn khỏe nhưng mọi connection đang bận: acquisition timeout có thể xảy ra.
- Connection được cấp nhanh nhưng Cypher chạy lâu: đây là vấn đề transaction/query timeout hoặc query performance.

Không tăng acquisition timeout để che giấu pool bị thiếu capacity. Nếu pool thường xuyên cạn, hãy kiểm tra session lifecycle, query latency, transaction duration và concurrency trước khi tăng max pool size.

Neo4j Java Driver cung cấp các API riêng như withConnectionTimeout(...) và withConnectionAcquisitionTimeout(...). Trong Driver API, withConnectionTimeout(...) là socket connection timeout, còn withConnectionAcquisitionTimeout(...) là thời gian chờ cấp connection phù hợp. Property appendix của Spring Boot có mô tả riêng cho spring.neo4j.connection-timeout; vì binding và mô tả có thể thay đổi theo dòng Boot, hãy kiểm tra configuration metadata của đúng dependency đang dùng khi cần phân biệt chính xác thời gian mở socket với thời gian lấy connection từ pool.

## 4. Transaction timeout phải được đặt ở phía transaction/database

Timeout của HTTP request hoặc connection pool không thay thế transaction timeout. Nếu client ngắt kết nối trong khi query đang chạy, không nên mặc định rằng server-side transaction đã bị chấm dứt ngay lập tức.

Neo4j hỗ trợ cấu hình timeout mặc định ở DBMS bằng:

~~~properties
db.transaction.timeout=15s
~~~

Giá trị 0s mặc định có nghĩa tính năng transaction timeout bị tắt. Đặt một giá trị dương để Neo4j chấm dứt transaction chạy quá thời gian cho phép.

Có thể kiểm tra setting:

~~~cypher
SHOW SETTINGS
YIELD name, value, defaultValue, isDynamic
WHERE name IN [
    'db.transaction.timeout',
    'db.transaction.concurrent.maximum',
    'db.memory.transaction.max',
    'db.memory.transaction.total.max'
]
RETURN name, value, defaultValue, isDynamic
ORDER BY name
~~~

Nếu cần timeout riêng cho một transaction khi dùng Neo4j Java Driver trực tiếp, Driver hỗ trợ TransactionConfig:

~~~java
import java.time.Duration;

import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

try (Session session = driver.session(
        SessionConfig.builder()
            .withDatabase("application")
            .build())) {

    var result = session.executeRead(
        tx -> tx.run("""
                MATCH (person:Person {id: $id})
                RETURN person.name AS name
                """,
                java.util.Map.of("id", personId))
            .single()
            .get("name")
            .asString(),
        TransactionConfig.builder()
            .withTimeout(Duration.ofSeconds(5))
            .withMetadata(java.util.Map.of(
                "application", "spring-data-neo4j",
                "operation", "find-person"
            ))
            .build()
    );
}
~~~

Đây là ví dụ dùng Driver API trực tiếp. Khi thao tác qua SDN repository và Neo4jClient trong Spring-managed transaction, hãy dùng transaction manager của SDN và kiểm tra cách phiên bản đang dùng áp dụng transaction definition/timeout. Không mở một transaction Driver độc lập bên trong một transaction SDN rồi kỳ vọng hai transaction tự tham gia cùng nhau.

Spring hỗ trợ khai báo timeout theo giây trên transaction:

~~~java
@Transactional(timeout = 8)
public Order createOrder(CreateOrderCommand command) {
    // Các thao tác repository thuộc transaction này.
}
~~~

Timeout này được gửi qua Spring transaction infrastructure. Hãy xác nhận bằng integration test rằng transaction manager và phiên bản SDN/Driver của ứng dụng thực sự áp dụng nó ở Neo4j. Nếu cần một giới hạn mặc định cho toàn database, cấu hình db.transaction.timeout ở server vẫn là một lớp bảo vệ quan trọng.

Transaction timeout tùy chỉnh có thể ghi đè timeout mặc định phía server. Một số phiên bản Neo4j cũ có quy tắc xử lý khác khi custom timeout lớn hơn server default; hãy đối chiếu tài liệu đúng phiên bản database đang chạy.

## 5. Retry budget không phải query timeout

spring.neo4j.max-transaction-retry-time điều khiển thời gian tối đa Driver cho phép retry đối với managed transaction. Driver chỉ retry những lỗi được xác định là có thể thử lại, thường là lỗi transient do sự cố tạm thời hoặc chuyển đổi cluster.

Thuộc tính này không có nghĩa mỗi query được phép chạy trong khoảng thời gian đó. Một query chạy lâu cần transaction timeout hoặc giới hạn riêng; retry budget chỉ quyết định Driver có thể tiếp tục thử lại một managed transaction trong bao lâu.

Cũng cần phân biệt hai cách thực thi:

- Driver managed transaction như executeRead/executeWrite có retry behavior tích hợp.
- Một transaction được mở tường minh hoặc Spring-managed transaction qua SDN không nên được giả định sẽ tự chạy lại toàn bộ callback giống managed transaction API.

Vì vậy, không coi max-transaction-retry-time là chính sách retry chung cho mọi repository method. Hãy xác định chính xác API/transaction path mà ứng dụng đang dùng.

## 6. Retry phải an toàn và có giới hạn

Managed transaction callback có thể được thực thi lại khi Driver gặp lỗi retryable. Code bên trong callback vì thế phải có tính idempotent và không được phụ thuộc vào side effect chỉ được phép xảy ra một lần.

Một lệnh MERGE theo khóa ổn định có thể giúp thao tác ghi lặp không tạo node trùng:

~~~cypher
MERGE (order:Order {id: $orderId})
ON CREATE SET
    order.createdAt = datetime(),
    order.status = 'PENDING'
RETURN order
~~~

Nếu orderId là idempotency key được tạo từ yêu cầu nghiệp vụ và có uniqueness constraint phù hợp, request lặp có thể tìm lại cùng một Order. Cần thiết kế riêng hành vi cập nhật khi node đã tồn tại; MERGE không tự làm mọi nghiệp vụ trở thành idempotent.

Không đặt các hành động sau bên trong callback có thể được retry:

- Gửi email hoặc SMS.
- Gọi payment provider.
- Gửi message trực tiếp lên broker.
- Ghi file hoặc tăng counter bên ngoài transaction.
- Thay đổi biến global hoặc state dùng chung.

Nếu cần phát side effect sau khi graph commit, dùng event/outbox phù hợp. Với outbox, ghi event trong cùng transaction Neo4j, rồi worker giao message với idempotency key và retry riêng.

Chỉ retry lỗi transient hoặc lỗi được phân loại retryable. Không retry vô hạn các lỗi như Cypher syntax, authentication, authorization, constraint violation hoặc input không hợp lệ.

Nếu ứng dụng có thêm Spring Retry, Resilience4j hoặc retry ở HTTP client, tránh xếp nhiều lớp retry không có ngân sách chung. Ví dụ Driver thử lại 3 lần, service thử lại 3 lần và gateway thử lại 3 lần có thể tạo tới 27 lần thực thi ở tầng sâu. Hãy chọn một lớp sở hữu retry chính, giới hạn số lần, dùng exponential backoff có jitter và dừng khi deadline request không còn đủ.

## 7. Thiết kế connection pool theo concurrency

Neo4j Java Driver quản lý connection pool. Pool size cần được tính theo số request đồng thời thực sự truy cập database, thời gian giữ connection và khả năng phục vụ của Neo4j.

Các nguyên tắc:

- Một Driver thường được chia sẻ trong ứng dụng; không tạo Driver mới cho mỗi request.
- Session là đối tượng nhẹ nhưng không thread-safe; không chia sẻ cùng một Session giữa nhiều thread đồng thời.
- Đóng session/resource đúng vòng đời để connection được trả về pool.
- Connection pool size là giới hạn của từng Driver instance, không phải tổng giới hạn toàn bộ deployment.
- Tăng pool size có thể làm số transaction đồng thời tăng và gây quá tải DBMS nếu database không đủ CPU, memory hoặc I/O.

Nếu có 4 application replicas và mỗi Driver được cấu hình max pool size là 30, mỗi replica có thể giữ tối đa 30 connection trong pool tới một database/đích tương ứng. Tổng kết nối tiềm năng từ ứng dụng có thể lên tới 120, chưa tính các client khác. Với routing driver trong cluster, pool còn phụ thuộc các server member mà Driver kết nối.

Đừng lấy max pool size mặc định 100 làm con số bắt buộc. Hãy đo số connection đang sử dụng, connection acquisition latency, số transaction hoạt động và query latency trước khi tăng.

## 8. Fetch size, streaming và giới hạn dữ liệu trả về

Neo4j Java Driver có fetch size để điều khiển số record lấy theo từng batch trong một số kiểu session đồng bộ. Driver hiện đại thường dùng mặc định 1000 record cho fetch size; có thể thay đổi bằng ConfigBuilder hoặc SessionConfig.

Fetch size không giới hạn tổng số record của query. Nếu query trả một triệu record và ứng dụng gọi list()/collectList() để giữ tất cả trong bộ nhớ, fetch size nhỏ chỉ thay đổi cách truyền dữ liệu theo batch; ứng dụng vẫn có thể materialize toàn bộ một triệu record.

Với reactive driver, lượng dữ liệu được điều tiết theo demand/subscription của Reactor thay vì dùng fetch size như synchronous session. Tuy nhiên, ứng dụng vẫn có thể tạo áp lực bộ nhớ nếu dùng collectList() trên một stream lớn hoặc đặt flatMap concurrency quá cao.

Giới hạn dữ liệu ở cấp query:

~~~cypher
MATCH (person:Person)
WHERE person.tenantId = $tenantId
RETURN person.id AS id, person.name AS name
ORDER BY person.id
SKIP $skip
LIMIT $limit
~~~

Chỉ trả property cần dùng, phân trang hoặc stream kết quả theo nhu cầu. Không tải cả entity graph lớn nếu use case chỉ cần một vài trường.

Với thao tác ghi lớn, chia thành batch transaction có kích thước hữu hạn. Neo4j giữ state thay đổi trong transaction cho tới khi transaction kết thúc; một transaction ghi quá lớn có thể tiêu thụ nhiều bộ nhớ. Với import/bulk update, cân nhắc batch processing hoặc Cypher subquery transaction phù hợp thay vì gom hàng triệu thay đổi vào một transaction.

## 9. Giới hạn concurrency và memory phía Neo4j

Pool size phía Driver chỉ kiểm soát số connection từ một ứng dụng. DBMS còn có giới hạn transaction và memory riêng.

Một số setting vận hành:

| Setting | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| db.transaction.concurrent.maximum | Database | Số transaction tối đa chạy đồng thời; mặc định hiện hành là 1000 |
| db.transaction.timeout | Database | Thời gian mặc định tối đa cho transaction; 0s là tắt timeout |
| db.memory.transaction.max | Database | Giới hạn memory cho một transaction; 0 có nghĩa không đặt giới hạn riêng |
| db.memory.transaction.total.max | Database | Giới hạn tổng memory transaction trong database; 0 có nghĩa không đặt giới hạn ở setting này |
| dbms.memory.transaction.total.max | DBMS | Giới hạn tổng memory transaction của các database; mặc định theo tỷ lệ heap của DBMS |

Các setting memory và concurrency phải được điều chỉnh theo heap, page cache, số database, workload và edition/version Neo4j. Không sao chép một con số từ máy khác mà không đo.

Có thể giảm áp lực transaction bằng cách:

- Chia batch ghi thành transaction nhỏ.
- Giới hạn số request đồng thời tại application/service layer.
- Giới hạn flatMap concurrency trong reactive pipeline.
- Không giữ transaction mở trong khi gọi API bên ngoài hoặc chờ người dùng.
- Tối ưu Cypher để giảm số node/relationship trung gian.
- Giới hạn kích thước graph được hydrate và payload trả về.

## 10. Giới hạn concurrency ở tầng ứng dụng

Một ứng dụng có thể nhận nhiều request hơn số connection pool hoặc số transaction Neo4j có thể phục vụ. Khi đó, request xếp hàng ở pool, làm latency tăng. Hãy đặt một giới hạn concurrency có chủ đích ở application layer.

Ví dụ với reactive flow, giới hạn số thao tác repository chạy đồng thời:

~~~java
Flux<Person> loadPeople(Flux<String> personIds) {
    return personIds.flatMap(
        personRepository::findById,
        8
    );
}
~~~

Tham số 8 giới hạn số inner publisher được subscribe đồng thời trong operator này. Nó không phải giới hạn toàn ứng dụng nếu nhiều request khác cũng chạy cùng lúc. Cần kết hợp với bulkhead/semaphore hoặc giới hạn request ở tầng web nếu muốn có một ngân sách toàn cục.

Với imperative application, dùng executor có queue hữu hạn hoặc bulkhead phù hợp. Queue không giới hạn chỉ chuyển tình trạng quá tải thành tăng memory và latency.

Không đặt concurrency chỉ theo số CPU của ứng dụng. Query graph có thể giữ connection lâu do traversal, locking, transaction hoặc tải dữ liệu lớn. Hãy dùng thời gian giữ connection và throughput thực tế để tính.

## 11. Cấu hình khác nhau theo môi trường

Mỗi môi trường phục vụ mục tiêu khác nhau. Giá trị dưới đây là điểm bắt đầu minh họa, không phải default bắt buộc hay sizing production phổ quát.

| Môi trường | Kết nối/acquisition | Retry budget | Transaction timeout | Pool |
| --- | --- | --- | --- | --- |
| Local development | Ngắn, khoảng 2–3 giây | 0–2 giây để lỗi dễ lộ | Khoảng 10–15 giây | Nhỏ, khoảng 5–10 |
| Automated test | Ngắn, khoảng 1–2 giây | 0–1 giây để test không chờ lâu | Khoảng 5–10 giây | Nhỏ, khoảng 3–5 |
| Staging | Gần production | Theo cùng quy tắc production | Gần production | Theo tải kiểm thử |
| Production | Theo latency và network thực tế | Nằm trong request deadline | Theo SLO của use case | Load test và capacity planning |

**Local development** nên phản hồi lỗi nhanh khi Neo4j không chạy. Bật leak logging nếu cần phát hiện session không đóng. Tránh cấu hình retry dài khiến mỗi lần thử local phải chờ hàng chục giây.

**Automated test** cần timeout ngắn và ổn định để test thất bại nhanh khi container không sẵn sàng. Retry quá dài có thể che lỗi môi trường hoặc làm CI treo. Dùng database/container riêng cho test song song.

**Staging** nên mô phỏng production về topology, pool, security, transaction timeout và giới hạn tài nguyên. Dùng staging để kiểm tra load, failover, pool exhaustion và retry trước khi phát hành.

**Production** cần đặt ngân sách theo SLO, p95/p99 latency, request deadline, số replica, pool capacity và khả năng Neo4j. Không tăng retry hoặc pool chỉ để làm giảm tỷ lệ lỗi quan sát được; đôi khi lỗi nhanh giúp hệ thống phục hồi tốt hơn.

## 12. Ví dụ cấu hình theo Spring profiles

Cấu hình nền có thể chứa các giá trị chung và đọc thông tin kết nối từ môi trường:

~~~yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: from-secret-store
    connection-timeout: 5s
    max-transaction-retry-time: 3s
    pool:
      connection-acquisition-timeout: 2s
      max-connection-pool-size: 20
      max-connection-lifetime: 30m
      metrics-enabled: true
  data:
    neo4j:
      database: application
~~~

Profile local development:

~~~yaml
spring:
  neo4j:
    connection-timeout: 3s
    max-transaction-retry-time: 1s
    pool:
      connection-acquisition-timeout: 1s
      max-connection-pool-size: 5
      log-leaked-sessions: true
~~~

Profile test:

~~~yaml
spring:
  neo4j:
    connection-timeout: 2s
    max-transaction-retry-time: 0s
    pool:
      connection-acquisition-timeout: 1s
      max-connection-pool-size: 4
      log-leaked-sessions: true
~~~

Profile production:

~~~yaml
spring:
  neo4j:
    connection-timeout: 5s
    max-transaction-retry-time: 2s
    pool:
      connection-acquisition-timeout: 1s
      max-connection-pool-size: 40
      max-connection-lifetime: 30m
      metrics-enabled: true
      log-leaked-sessions: false
~~~

Các con số trên chỉ minh họa cách override profile. Pool size 40 chỉ hợp lý nếu tổng số replicas, các client khác và khả năng DBMS đã được load test. Retry 0s trong test cũng cần được xác minh với phiên bản Driver; nếu muốn kiểm tra retry behavior, hãy viết test riêng thay vì dựa vào retry mặc định trong mọi test.

Không nhân bản toàn bộ cấu hình giữa các file profile nếu chỉ một vài giá trị thay đổi. Giữ cấu hình nền và override các giá trị riêng của môi trường để tránh drift.

## 13. Tùy chỉnh Driver bằng ConfigBuilderCustomizer

Nếu cần điều chỉnh thuộc tính Driver chưa được expose bằng Spring Boot property, có thể dùng ConfigBuilderCustomizer thay vì tự tạo một Driver bean mới.

Ví dụ với Spring Boot 3.x:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.boot.autoconfigure.neo4j.ConfigBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class Neo4jDriverConfiguration {

    @Bean
    ConfigBuilderCustomizer neo4jDriverCustomizer() {
        return config -> config
            .withFetchSize(500)
            .withConnectionLivenessCheckTimeout(
                5,
                TimeUnit.MINUTES
            )
            .withLeakedSessionsLogging();
    }
}
~~~

Ví dụ điều chỉnh fetch size cho synchronous session và bật log session leak để điều tra. Connection liveness check cân bằng giữa việc kiểm tra connection idle đã chết và chi phí thêm network call khi lấy connection; không đặt quá ngắn nếu chưa có bằng chứng cần thiết.

Spring Boot gọi các ConfigBuilderCustomizer bean khi xây dựng Driver auto-configured. Có thể khai báo nhiều customizer và chúng được gọi theo thứ tự cấu hình. Với Spring Boot 4, package của ConfigBuilderCustomizer thay đổi; hãy import theo API version đang dùng.

Nếu tự khai báo Driver bean, Spring Boot có thể không tạo auto-configured Driver nữa. Khi đó, các property spring.neo4j.* có thể không còn được áp dụng theo cách bạn kỳ vọng. Chỉ tự quản lý Driver khi thực sự cần toàn quyền cấu hình và phải bảo đảm mọi thành phần SDN dùng cùng Driver instance.

## 14. Đo lường để chọn pool và timeout

Không thể chọn giá trị production chỉ bằng cách đọc default. Hãy đo workload đại diện.

Các metrics nên theo dõi:

| Metric | Dấu hiệu cần quan sát |
| --- | --- |
| Connection acquisition latency | Tăng cao có thể cho thấy pool cạn hoặc connection tạo chậm |
| Connections in use / idle | Phân biệt thiếu pool với connection bị giữ lâu |
| Connection creation/failure | Phát hiện lỗi mạng, TLS, DNS hoặc server unavailable |
| Transaction duration | Tìm transaction dài và query cần tối ưu |
| Retry count và retry duration | Phát hiện transient failures hoặc retry storm |
| Query latency p50/p95/p99 | So sánh với SLO của API |
| Active transactions | Phát hiện concurrency tăng bất thường |
| Transaction memory | Tìm query/batch tiêu thụ nhiều memory |
| Application heap/GC | Phát hiện graph hydration hoặc result materialization quá lớn |
| Error rate theo loại | Phân biệt timeout, auth, constraint, query syntax và database unavailable |

Neo4j có thể kiểm tra transaction đang chạy:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, username, database, currentQuery,
      elapsedTime, status
RETURN transactionId, username, database, currentQuery,
       elapsedTime, status
ORDER BY elapsedTime DESC
~~~

Dùng query log, transaction metadata và application trace để liên kết request với query. Tránh ghi password, token, dữ liệu cá nhân hoặc toàn bộ parameter nhạy cảm vào log.

Đối với pool metrics, bật tính năng metrics phù hợp với Spring Boot/Driver version và đưa dữ liệu vào hệ thống monitoring. Đặt cảnh báo theo xu hướng acquisition latency, pool saturation và retry rate thay vì chỉ cảnh báo khi exception xuất hiện.

## 15. Phân biệt quá tải pool với query chậm

Khi request chậm, hãy xác định thời gian bị tiêu thụ ở đâu:

- Nếu connection acquisition latency tăng nhưng query latency thấp, pool hoặc session lifecycle có thể là nguyên nhân.
- Nếu acquisition thấp nhưng transaction duration cao, điều tra Cypher, index, traversal, lock contention hoặc lượng graph được hydrate.
- Nếu retry rate tăng cùng service unavailable, kiểm tra network, cluster topology và tình trạng Neo4j.
- Nếu application heap tăng khi query trả nhiều record, kiểm tra fetch/streaming, projection và việc materialize toàn bộ kết quả.
- Nếu transaction memory tăng, kiểm tra batch size, số lượng ghi và thời gian transaction mở.

Đừng tăng pool khi query đang chậm. Thêm connection có thể làm nhiều query nặng chạy đồng thời, khiến CPU/memory của database bị quá tải nặng hơn.

## 16. Những lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng retry time làm query timeout | Query dài vẫn có thể chạy quá lâu | Đặt transaction timeout riêng |
| Pool acquisition timeout quá dài | Request xếp hàng và giữ tài nguyên | Đặt ngắn theo request deadline |
| Max pool size tăng không dựa trên load test | DBMS nhận quá nhiều transaction đồng thời | Tính theo replicas và capacity DBMS |
| Retry ở nhiều tầng | Retry amplification và tải tăng đột biến | Một retry budget có giới hạn |
| Retry mọi exception | Lỗi cú pháp/auth/constraint bị lặp vô ích | Chỉ retry lỗi transient/retryable |
| Transaction callback có side effect | Callback retry có thể gửi email/message nhiều lần | Idempotency và outbox |
| Dùng pool size để giới hạn tổng request | Không kiểm soát concurrency toàn deployment | Thêm bulkhead/rate limit ở application |
| Fetch size quá lớn | Tăng áp lực memory và network | Điều chỉnh batch size, stream dữ liệu |
| Fetch size quá nhỏ | Tăng số lần pull và round trip | Benchmark với workload thật |
| Dùng collectList() trên stream rất lớn | Heap ứng dụng tăng mạnh | Stream, phân trang hoặc batch |
| Giữ transaction mở khi gọi API ngoài | Lock và connection bị giữ lâu | Kết thúc transaction trước side effect |
| Chỉ cấu hình timeout ở HTTP client | Query server-side có thể vẫn chạy | Đặt transaction timeout phía Neo4j |
| Tạo Driver riêng cho từng service | Nhiều pool và connection chồng lấn | Dùng một Driver được quản lý trong context |

## 17. Quy trình cấu hình cho một môi trường mới

1. Xác định request deadline và SLO của API.
2. Chọn transaction timeout nhỏ hơn deadline của service.
3. Chọn connection acquisition timeout để request không chờ pool quá lâu.
4. Đặt connection timeout phù hợp với network và topology.
5. Xác định Driver API có dùng managed transaction retry hay không.
6. Đặt retry budget nhỏ hơn thời gian request còn lại và chỉ retry lỗi transient.
7. Tính pool size theo số replicas, database topology và các client khác.
8. Giới hạn concurrency và batch size ở tầng ứng dụng.
9. Kiểm tra transaction timeout, concurrent maximum và memory guardrail phía Neo4j.
10. Load test với query, graph size và phân bố tải gần production.
11. Theo dõi acquisition latency, transaction duration, retry rate, memory và p95/p99.
12. Điều chỉnh một nhóm giá trị mỗi lần và lưu kết quả benchmark.
13. Kiểm thử failover, database unavailable, pool exhaustion và query timeout.
14. Lặp lại quy trình khi tăng replicas, đổi topology hoặc thay đổi workload.

## 18. Bài tập tự kiểm tra

1. Connection timeout khác connection acquisition timeout ở điểm nào?
2. Vì sao retry budget không phải query timeout?
3. spring.neo4j.max-transaction-retry-time áp dụng cho loại Driver transaction nào?
4. Vì sao không nên giả định mọi repository method tự retry toàn bộ transaction?
5. Điều kiện nào khiến một managed transaction callback phải idempotent?
6. Vì sao không gửi email hoặc gọi payment provider bên trong transaction callback có thể retry?
7. Pool size 40 trên mỗi replica có nghĩa gì khi ứng dụng chạy bốn replicas?
8. Fetch size giới hạn batch như thế nào và vì sao không giới hạn tổng số record?
9. Reactive Driver quản lý backpressure khác synchronous fetch size ra sao?
10. db.transaction.timeout và db.transaction.concurrent.maximum kiểm soát điều gì?
11. Vì sao transaction ghi lớn nên được chia batch?
12. Làm thế nào phân biệt pool saturation với Cypher query chậm?
13. Tại sao timeout ở HTTP client không thay thế transaction timeout ở Neo4j?
14. Những metrics nào cần theo dõi trước khi tăng pool size?

Khi hoàn thành bài học, bạn cần thiết kế được một ngân sách timeout nhất quán, phân biệt retry của Driver với retry ở tầng ứng dụng, giới hạn connection/concurrency/memory theo năng lực từng môi trường và dùng metrics để chứng minh cấu hình phù hợp. Đây là nền tảng để vận hành ứng dụng Spring Data Neo4j ổn định khi tải tăng hoặc database gặp sự cố tạm thời.

## Tài liệu tham khảo

- [Spring Boot – Common Application Properties (Neo4j)](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html)
- [Spring Boot – Working with Neo4j](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Boot – ConfigBuilderCustomizer API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/neo4j/ConfigBuilderCustomizer.html)
- [Neo4j Java Driver – Config](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Config.html)
- [Neo4j Java Driver – ConfigBuilder](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Config.ConfigBuilder.html)
- [Neo4j Java Driver – Transactions and retry behavior](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Operations Manual – Database transactions](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)
- [Neo4j Operations Manual – Transaction and memory settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)

