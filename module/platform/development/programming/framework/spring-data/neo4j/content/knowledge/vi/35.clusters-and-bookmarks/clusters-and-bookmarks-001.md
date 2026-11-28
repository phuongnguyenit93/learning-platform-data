# URI kết nối trực tiếp và URI có định tuyến

Spring Data Neo4j (SDN) sử dụng Neo4j Java Driver để mở kết nối Bolt, chạy Cypher và làm việc với node cùng relationship. Khi ứng dụng kết nối tới một máy Neo4j đơn lẻ, địa chỉ máy chủ thường là đủ. Khi database chạy trong causal cluster, ứng dụng cần chọn cách kết nối để driver có thể gửi thao tác tới đúng thành viên và tiếp tục hoạt động khi topology thay đổi.

Neo4j Java Driver cung cấp hai nhóm URI chính: **URI trực tiếp** dùng scheme `bolt` và **URI có định tuyến** dùng scheme `neo4j`. Hậu tố bảo mật `+s` hoặc `+ssc` có thể kết hợp với cả hai nhóm. Khác biệt giữa direct và routing nằm ở cách driver chọn máy chủ; hậu tố bảo mật quyết định cách mã hóa và xác thực chứng chỉ TLS.

Bài học này giải thích cách chọn URI cho standalone và cluster, cách routing driver khám phá topology, cách phân biệt read/write routing, cách cấu hình Spring Boot và các lỗi thường gặp khi dùng SDN trong môi trường nhiều máy.

## Cấu trúc và các nhóm URI

Một connection URI có dạng tổng quát:

~~~text
<scheme>://<host>[:<port>]
~~~

- `scheme` chọn direct driver hay routing driver, đồng thời có thể quy định TLS.
- `host` là địa chỉ đầu vào ban đầu để driver kết nối.
- `port` là cổng Bolt, mặc định thường là `7687` nếu không chỉ định.

Các scheme Java Driver hiện hành thường dùng:

| URI scheme | Kiểu kết nối | Bảo mật |
|---|---|---|
| `bolt://` | Trực tiếp tới host được chỉ định | Không mã hóa theo scheme |
| `bolt+s://` | Trực tiếp tới host được chỉ định | TLS, xác minh chứng chỉ CA |
| `bolt+ssc://` | Trực tiếp tới host được chỉ định | TLS, chấp nhận chứng chỉ tự ký |
| `neo4j://` | Có định tuyến qua routing table | Không mã hóa theo scheme |
| `neo4j+s://` | Có định tuyến qua routing table | TLS, xác minh chứng chỉ CA |
| `neo4j+ssc://` | Có định tuyến qua routing table | TLS, chấp nhận chứng chỉ tự ký |

Hai trục cần nhớ:

- `bolt` so với `neo4j` quyết định driver kết nối thẳng một máy hay sử dụng routing table.
- `+s` và `+ssc` quyết định chế độ TLS và trust certificate.

Không nên chọn URI chỉ dựa trên tên scheme. Server phải được cấu hình để hỗ trợ đúng giao thức và chứng chỉ tương ứng. Nếu không chắc chắn, cần xác nhận URI do quản trị viên database hoặc nhà cung cấp dịch vụ cấp.

## URI trực tiếp với bolt

URI `bolt://host:7687` tạo direct driver. Driver kết nối tới đúng host và cổng được chỉ định, không lấy routing table để chuyển transaction sang thành viên khác.

Ví dụ:

~~~text
bolt://db01.internal.example:7687
~~~

Cách này phù hợp khi:

- Ứng dụng cần kết nối tới một Neo4j standalone.
- Một tác vụ quản trị phải nhắm tới một máy cụ thể.
- Hạ tầng bên ngoài đã chịu trách nhiệm chọn node đích và cung cấp endpoint phù hợp.
- Cần kết nối tới một thành viên cluster cụ thể để phục vụ một mục đích vận hành có chủ đích.

Direct driver không tự phát hiện topology cluster, không tự chuyển sang primary khác nếu host đích gặp sự cố và không phân phối read transaction tới các secondary. Nếu host đó dừng hoạt động, ứng dụng cần cơ chế failover bên ngoài hoặc cấu hình lại endpoint.

### Ví dụ Java Driver với direct URI

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

public class DirectConnectionExample {

    public static void main(String[] args) {
        String uri = "bolt://db01.internal.example:7687";
        String username = "neo4j";
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri,
                AuthTokens.basic(username, password))) {

            driver.verifyConnectivity();

            try (Session session = driver.session()) {
                String result = session.executeRead(tx ->
                    tx.run("RETURN 'connected' AS status")
                        .single()
                        .get("status")
                        .asString()
                );

                System.out.println(result);
            }
        }
    }
}
~~~

`GraphDatabase.driver(...)` tạo Driver và connection pool; việc tạo object Driver chưa nhất thiết mở kết nối mạng ngay. `verifyConnectivity()` chủ động xác minh kết nối và thông tin xác thực. `executeRead(...)` khai báo thao tác đọc trong transaction, nhưng vì driver là direct nên thao tác vẫn chạy trên host được chỉ định.

Driver là thread-safe và tốn tài nguyên để khởi tạo. Ứng dụng nên tạo một instance dùng chung thay vì tạo Driver mới cho mỗi request. Đóng Driver khi ứng dụng dừng để giải phóng connection pool.

## URI có định tuyến với neo4j

URI `neo4j://host:7687` tạo routing driver. Driver kết nối tới địa chỉ đầu vào, nhận routing table từ server rồi sử dụng các địa chỉ trong bảng để gửi transaction tới thành viên phù hợp.

Ví dụ:

~~~text
neo4j://cluster-entry.internal.example:7687
~~~

Routing driver có thể sử dụng với causal cluster và cả một số cấu hình standalone hỗ trợ routing interface. Khi kết nối cluster, driver khám phá các thành viên và vai trò của chúng, sau đó chọn server theo access mode của transaction.

Luồng tổng quát:

~~~text
Ứng dụng SDN
    |
    v
Neo4j Java Driver
    |
    | Kết nối tới URI đầu vào
    v
Cluster entry point
    |
    | Trả routing table
    v
Driver cập nhật topology
    |
    +------> Primary: transaction ghi
    |
    +------> Secondary/read replica: transaction đọc
    |
    v
Driver refresh routing table theo chu kỳ
~~~

URI đầu vào là điểm bắt đầu khám phá cluster, không nhất thiết là máy sẽ xử lý mọi query. Sau khi nhận routing table, driver có thể kết nối trực tiếp tới các địa chỉ được quảng bá trong bảng.

Routing driver hỗ trợ failover tốt hơn direct driver vì có thể làm mới routing table và chọn thành viên khác khi topology thay đổi. Tuy nhiên, nó không bảo đảm ứng dụng luôn kết nối thành công nếu toàn bộ cluster không khả dụng, routing table không truy cập được hoặc các địa chỉ được quảng bá không thể truy cập từ mạng client.

### Ví dụ Java Driver với routing URI

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public class RoutingConnectionExample {

    public static void main(String[] args) {
        String uri = "neo4j://cluster-entry.internal.example:7687";
        String username = "neo4j";
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri,
                AuthTokens.basic(username, password))) {

            driver.verifyConnectivity();

            SessionConfig sessionConfig = SessionConfig.builder()
                .withDatabase("neo4j")
                .build();

            try (Session session = driver.session(sessionConfig)) {
                long personCount = session.executeRead(tx ->
                    tx.run("MATCH (p:Person) RETURN count(p) AS total")
                        .single()
                        .get("total")
                        .asLong()
                );

                System.out.println("People: " + personCount);
            }
        }
    }
}
~~~

Trong ví dụ, `executeRead(...)` đánh dấu transaction là đọc để routing driver có thể chọn server đọc phù hợp. Với thao tác ghi, dùng `executeWrite(...)`. Nếu ứng dụng chỉ dùng transaction mặc định mà không khai báo access mode phù hợp, driver có thể xem đó là transaction read/write và gửi tới primary.

Một routing URI cũng có thể kết nối tới một địa chỉ thuộc cluster bất kỳ làm entry point. Tuy nhiên, nếu chỉ khai báo một entry point và máy đó không sẵn sàng, driver không thể lấy routing table mới từ chính entry point ấy. Có thể tăng khả năng khám phá bằng DNS có nhiều địa chỉ A/AAAA, custom address resolver hoặc một endpoint đầu vào ổn định được hạ tầng quản lý.

## Direct và routing khác nhau ở đâu?

| Tiêu chí | Direct URI (`bolt`) | Routing URI (`neo4j`) |
|---|---|---|
| Máy đích ban đầu | Host trong URI | Host trong URI để khám phá |
| Routing table | Không sử dụng | Có |
| Chuyển transaction theo vai trò cluster | Không | Có |
| Tự khám phá thành viên khác | Không | Có |
| Phân phối read/write theo access mode | Không | Có |
| Failover theo topology cluster | Cần cơ chế ngoài driver | Driver có thể refresh routing table và chọn server khác |
| Phù hợp nhất | Standalone hoặc một host cụ thể | Causal cluster hoặc deployment hỗ trợ routing |

Một điểm dễ nhầm: `neo4j://` không chỉ dành riêng cho cluster. Neo4j 4.x trở lên cung cấp routing interface cho cả standalone; routing driver có thể lấy routing table từ một instance đơn lẻ. Vì vậy, với standalone Neo4j hiện đại, cả `bolt://` và `neo4j://` có thể hoạt động. Chọn `bolt://` khi cần nhắm trực tiếp một host; chọn `neo4j://` khi muốn dùng cơ chế routing của driver.

Với Neo4j 3.x standalone, routing interface chưa có như các phiên bản mới, do đó `bolt://` là lựa chọn phù hợp. Scheme lịch sử `bolt+routing://` đã được thay thế bởi `neo4j://` trong dòng driver/Neo4j 4.x; không dùng nó cho cấu hình mới.

## TLS: +s và +ssc

Direct và routing URI đều có biến thể bảo mật. Hậu tố TLS không làm thay đổi việc driver có routing hay không:

- `bolt+s://`: direct connection, bật TLS và xác minh chứng chỉ theo CA đáng tin cậy.
- `bolt+ssc://`: direct connection, bật TLS và chấp nhận chứng chỉ tự ký.
- `neo4j+s://`: routing connection, bật TLS và xác minh chứng chỉ theo CA đáng tin cậy.
- `neo4j+ssc://`: routing connection, bật TLS và chấp nhận chứng chỉ tự ký.

Ví dụ với Aura:

~~~text
neo4j+s://<instance-id>.databases.neo4j.io
~~~

Aura thường cung cấp URI `neo4j+s://` vì kết nối dùng TLS với chứng chỉ được xác minh. Dùng chính URI trong thông tin kết nối của instance thay vì tự đoán hostname hoặc đổi scheme.

Ví dụ môi trường nội bộ dùng chứng chỉ CA:

~~~text
neo4j+s://graph-cluster.example.com:7687
~~~

`+ssc` hữu ích cho môi trường thử nghiệm dùng chứng chỉ tự ký. Không nên chọn nó chỉ để né lỗi chứng chỉ trong production; hãy cài CA certificate đúng cách và dùng `+s` khi có thể.

Không trộn cấu hình trust/encryption trong Driver Config một cách tùy tiện với scheme URI đã quy định TLS. Scheme URI xác định hành vi bảo mật của kết nối; nếu cần trust strategy đặc biệt, hãy theo đúng hướng dẫn của Java Driver cho phiên bản đang dùng.

## Cấu hình URI trong Spring Boot và Spring Data Neo4j

Spring Boot tự cấu hình Neo4j Driver từ các property `spring.neo4j.*`. SDN sử dụng Driver này cho repository, `Neo4jTemplate` và `Neo4jClient`.

### Kết nối trực tiếp tới một máy

Ví dụ `application.properties` cho một instance nội bộ:

~~~properties
spring.neo4j.uri=bolt://localhost:7687
spring.neo4j.authentication.username=neo4j
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Trong môi trường production, cung cấp password qua biến môi trường hoặc secret manager, không commit thông tin xác thực vào repository.

### Kết nối routing tới cluster

Chỉ cần đổi URI sang scheme routing và host entry point:

~~~properties
spring.neo4j.uri=neo4j://cluster-entry.internal.example:7687
spring.neo4j.authentication.username=neo4j
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Với cluster bật TLS và dùng chứng chỉ CA:

~~~properties
spring.neo4j.uri=neo4j+s://cluster-entry.internal.example:7687
spring.neo4j.authentication.username=neo4j
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Không cần tạo riêng một Driver bean chỉ để dùng routing nếu Spring Boot đã auto-configure Driver. Các repository SDN và Neo4jClient sẽ sử dụng Driver do Spring quản lý. Nếu tự khai báo Driver bean, cần đảm bảo nó thay thế cấu hình mặc định đúng cách và được đóng theo vòng đời ứng dụng.

### Kiểm tra kết nối khi ứng dụng khởi động

Có thể inject Driver để kiểm tra kết nối và lấy thông tin server:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Neo4jConnectionCheck {

    @Bean
    ApplicationRunner verifyNeo4jConnection(Driver driver) {
        return args -> driver.verifyConnectivity();
    }
}
~~~

`verifyConnectivity()` giúp phát hiện sớm URI, credential, TLS hoặc network không hợp lệ. Nó không thay thế health check liên tục cho cluster và cũng không chứng minh mọi thành viên trong routing table đều truy cập được từ ứng dụng. Hãy kiểm tra log driver và cấu hình advertised address khi kết nối khởi tạo được nhưng query tới thành viên khác thất bại.

## Routing read và write trong cluster

Trong causal cluster, primary có thể xử lý cả read và write. Secondary/read replica phục vụ read và nhận dữ liệu được đồng bộ từ primary; secondary không xử lý write transaction thông thường. Routing driver dùng access mode để chọn nhóm server phù hợp.

Với Neo4j Java Driver:

~~~java
long count = session.executeRead(tx ->
    tx.run("MATCH (p:Person) RETURN count(p) AS total")
        .single()
        .get("total")
        .asLong()
);

String created = session.executeWrite(tx ->
    tx.run("""
        CREATE (p:Person {employeeCode: $code})
        RETURN p.employeeCode AS code
        """, org.neo4j.driver.Values.parameters("code", "E-9001"))
        .single()
        .get("code")
        .asString()
);
~~~

Trong SDN, cần đánh dấu các thao tác đọc bằng transaction read-only khi muốn driver route chúng tới secondary. SDN và Java Driver không phân tích Cypher để tự suy ra query nào chỉ đọc; vì vậy, một query đọc qua custom method không tự động được coi là read-only trong mọi trường hợp.

Repository minh họa:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    List<Person> findByActiveTrue();
}
~~~

Ví dụ service SDN:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonQueryService {

    private final PersonRepository people;

    public PersonQueryService(PersonRepository people) {
        this.people = people;
    }

    @Transactional(readOnly = true)
    public Iterable<Person> findActivePeople() {
        return people.findByActiveTrue();
    }
}
~~~

Các repository method đọc dựng sẵn như `findById`, `findAllById`, `findAll` và các method existence được định nghĩa sẵn có thể được đánh dấu read-only theo mặc định. Với custom service/query, hãy kiểm tra transaction metadata và khai báo `@Transactional(readOnly = true)` khi phù hợp.

Read routing có thể trả về dữ liệu hơi trễ hơn primary do replication. Nếu use case yêu cầu đọc ngay những gì vừa ghi, cần bảo đảm causal consistency; không tùy tiện bỏ read-only chỉ để ép tất cả truy vấn vào primary nếu không có yêu cầu nhất quán như vậy.

## URI routing không thay thế bookmark

Routing và bookmark giải quyết hai vấn đề khác nhau:

- **Routing URI** giúp driver khám phá cluster và chọn máy chủ theo access mode.
- **Bookmark** mang thông tin causal consistency để transaction tiếp theo có thể chờ dữ liệu từ transaction trước đã được áp dụng.

Một routing driver có thể gửi read transaction tới secondary. Nếu thao tác đọc phải nhìn thấy dữ liệu vừa commit ở transaction trước, bookmark cho phép driver duy trì thứ tự nhân quả. SDN quản lý bookmark nội bộ cho các transaction liên tiếp trong cùng thread hoặc cùng reactive stream; ứng dụng SDN thông thường không cần tự truyền bookmark cho mỗi lời gọi repository.

Đối với ứng dụng dùng nhiều Driver/session hoặc trao đổi bookmark qua nhiều tiến trình, cần tìm hiểu bookmark manager và bookmark API của Java Driver. Không giả định chỉ cần đổi từ `bolt://` sang `neo4j://` là mọi lần đọc ở mọi session sẽ tự động có read-your-own-writes.

## DNS, advertised address và khả năng truy cập mạng

Routing driver nhận routing table từ server. Bảng này chứa địa chỉ của các thành viên mà driver cần kết nối. Vì thế, việc chỉ truy cập được host entry point chưa đủ.

Các vấn đề triển khai thường gặp:

- Server quảng bá hostname nội bộ chỉ phân giải được trong subnet khác.
- Firewall cho phép kết nối tới entry point nhưng chặn các Bolt address trong routing table.
- Container hoặc Kubernetes pod phân giải DNS khác với máy chạy Neo4j.
- Certificate không chứa hostname được quảng bá trong subject alternative name.
- Chỉ một entry point được khai báo và entry point đó ngừng hoạt động.
- Cấu hình advertised address trả về IP riêng không thể truy cập từ client ngoài mạng.

Trong cluster self-managed, quản trị viên cần cấu hình routing listen/advertised address để client nhận được endpoint có thể truy cập. Driver custom resolver có thể giúp ánh xạ địa chỉ entry point sang một tập địa chỉ ban đầu, nhưng resolver không tự sửa các địa chỉ được server quảng bá trong routing table. Vì vậy, cần cấu hình server/network đúng thay vì chỉ sửa client.

Nếu các thành viên cluster được công bố qua DNS có nhiều bản ghi A/AAAA, driver có thể sử dụng các địa chỉ đó làm entry point. Nếu dùng resolver, các địa chỉ phải là host hợp lệ và có cổng Bolt tương ứng. Không đưa HTTP endpoint hoặc địa chỉ browser vào connection URI của Java Driver.

## Chẩn đoán kết nối và lỗi thường gặp

Có thể xác minh kết nối trực tiếp bằng Java Driver:

~~~java
try (Driver driver = GraphDatabase.driver(
        "neo4j://cluster-entry.internal.example:7687",
        AuthTokens.basic("neo4j", System.getenv("NEO4J_PASSWORD")))) {

    driver.verifyConnectivity();
    System.out.println(driver.getServerInfo());
}
~~~

Nếu `verifyConnectivity()` thành công nhưng query trong cluster vẫn lỗi, hãy kiểm tra routing table, advertised address, DNS, firewall, certificate hostname và quyền truy cập database. `verifyConnectivity()` xác nhận driver kết nối được tới database theo URI; nó không chứng minh mọi địa chỉ cluster đã quảng bá đều có thể truy cập.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Kết nối direct được nhưng routing thất bại | Client không truy cập được địa chỉ trong routing table | Kiểm tra advertised address, DNS và firewall |
| Write transaction thất bại khi direct vào secondary | Direct driver không tự route write sang primary | Dùng `neo4j://` hoặc kết nối đúng primary khi có lý do vận hành |
| Read không được phân phối sang replica | Transaction bị xem là read/write | Dùng `executeRead` hoặc `@Transactional(readOnly = true)` |
| Driver không failover khi host dừng | Dùng `bolt://` direct hoặc chỉ có entry point không sẵn sàng | Dùng routing URI và nhiều entry point/DNS phù hợp |
| Lỗi certificate sau khi bật TLS | Hostname không khớp certificate hoặc CA chưa được trust | Kiểm tra SAN, trust store và chọn `+s` đúng cách |
| Aura từ chối URI | Dùng sai host hoặc scheme | Dùng URI `neo4j+s://` do Aura cung cấp |
| Neo4j 3.x standalone không dùng được `neo4j://` | Server không cung cấp routing interface | Dùng `bolt://` hoặc nâng cấp server |
| Dùng `bolt+routing://` trong cấu hình mới | Scheme lịch sử đã được thay thế | Dùng `neo4j://` |
| App kết nối được entry point nhưng lỗi khi query | Routing table chứa địa chỉ không thể truy cập | Sửa server routing advertised address và network |

## Quy trình chọn URI

Khi cấu hình một ứng dụng SDN mới:

1. Xác định database là standalone hay causal cluster.
2. Xác định server version và giao thức TLS được cung cấp.
3. Nếu cần kết nối một host cụ thể, chọn `bolt`, `bolt+s` hoặc `bolt+ssc`.
4. Nếu muốn driver tự khám phá topology và route read/write, chọn `neo4j`, `neo4j+s` hoặc `neo4j+ssc`.
5. Cấu hình URI, username và password trong `spring.neo4j.*`.
6. Kiểm tra kết nối bằng `Driver.verifyConnectivity()`.
7. Với cluster, xác nhận mọi advertised address đều truy cập được từ ứng dụng.
8. Đánh dấu read-only transaction cho các truy vấn đọc cần route tới secondary.
9. Kiểm tra bookmark/causal consistency cho use case cần đọc dữ liệu vừa ghi.
10. Kiểm thử khi một entry point hoặc một thành viên cluster tạm thời không khả dụng.

## Bài tập thực hành

Với ứng dụng Spring Data Neo4j quản lý `Person`, `Department` và relationship `WORKS_IN`, hãy thực hiện:

1. Kết nối một Neo4j standalone bằng `bolt://localhost:7687`.
2. Đổi sang `neo4j://localhost:7687` trên phiên bản Neo4j có routing interface và quan sát hành vi kết nối.
3. Dùng Java Driver với `executeRead` để đếm Person.
4. Dùng `executeWrite` để tạo Person và kiểm tra node được lưu.
5. Kết nối một cluster bằng `neo4j://` và quan sát routing table/driver log.
6. Thử kết nối một thành viên cụ thể bằng `bolt://` và giải thích vì sao thao tác không tự chuyển sang server khác.
7. Cấu hình Spring Boot với `spring.neo4j.uri` cho direct URI và routing URI.
8. Bật TLS trong môi trường test, so sánh `+s` và `+ssc` với chứng chỉ CA và chứng chỉ tự ký.
9. Đánh dấu một service method `@Transactional(readOnly = true)` và kiểm tra routing của query đọc trong cluster.
10. Tạo một transaction ghi rồi đọc tiếp trong SDN, quan sát cơ chế bookmark nội bộ.
11. Thử cấu hình advertised address không thể truy cập và đọc lỗi từ driver log.
12. Viết tài liệu cấu hình kết nối cho local, staging và production, nêu rõ lý do chọn scheme và yêu cầu mạng/TLS.

Khi triển khai SDN với Neo4j, hãy chọn `bolt://` nếu cần nhắm trực tiếp một máy và `neo4j://` nếu muốn driver khám phá cluster, route read/write và cập nhật topology. Kết hợp hậu tố TLS phù hợp với chứng chỉ của server, cấu hình read-only transaction cho truy vấn đọc trong cluster và kiểm tra advertised address từ đúng mạng chạy ứng dụng.

Tài liệu tham khảo chính thức:

- [Neo4j Java Driver Manual - Connection](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver Manual - Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Operations Manual - Routing and load balancing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/)
- [Spring Boot - Connecting to a Neo4j database](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Data Neo4j FAQ - Using a cluster](https://docs.spring.io/spring-data/neo4j/reference/faq.html)

