# Tạo phiên ở nút thứ nhất, cập nhật ở nút thứ hai rồi kiểm tra lại

Một kiểm thử tích hợp quan trọng của Spring Session là chứng minh session được tạo bởi một instance ứng dụng có thể được một instance khác đọc và cập nhật. Kiểm thử này xác nhận ứng dụng thực sự dùng kho session chung như Redis hoặc JDBC, thay vì vô tình phụ thuộc vào session trong bộ nhớ của từng servlet container hoặc vào sticky session của load balancer.

Kịch bản gồm ba bước: gửi request tạo session đến node A, gửi cùng session cookie đến node B để cập nhật thuộc tính, sau đó gửi lại cookie đến node A để đọc và xác nhận giá trị mới. Nếu node A đọc được thay đổi của node B, dữ liệu đã được chia sẻ qua repository.

## 1. Mục tiêu và điều kiện của kiểm thử

Giả sử ứng dụng Spring Session có hai instance độc lập:

- Node A chạy trên cổng ngẫu nhiên thứ nhất.
- Node B chạy trên cổng ngẫu nhiên thứ hai.
- Cả hai kết nối đến cùng Redis hoặc cùng database/schema JDBC.
- Cả hai dùng cùng namespace, serializer, timeout và cookie/header resolver.
- Mỗi node có servlet context và SessionRepositoryFilter riêng.

Kiểm thử phải chứng minh dữ liệu được truyền qua shared repository. Không để hai node chia sẻ cùng một HttpSession object hoặc cùng một servlet container trong bộ nhớ.

Luồng:

~~~mermaid
sequenceDiagram
    participant T as Integration test
    participant A as Spring node A
    participant R as Shared Redis/JDBC
    participant B as Spring node B

    T->>A: POST /test/session
    A->>R: Create and save session
    R-->>A: Persist session
    A-->>T: Set-Cookie: SESSION=...
    T->>B: POST /test/session/increment + cookie
    B->>R: Load session by ID
    R-->>B: counter = 1
    B->>R: Save counter = 2
    B-->>T: counter = 2
    T->>A: GET /test/session + same cookie
    A->>R: Load session by ID
    R-->>A: counter = 2
    A-->>T: counter = 2
~~~

Điểm quyết định là request thứ hai và thứ ba phải mang cùng session ID. Test phải lấy cookie từ response đầu tiên và gửi lại đúng cookie đó; không tự tạo session ID và không gọi repository trực tiếp để thay thế luồng HTTP.

## 2. Chuẩn bị dependency và cấu hình

Ví dụ dưới đây dùng Spring Boot Servlet, Spring Session Data Redis, Spring Web và Testcontainers Redis. Dependency cần có trong project:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Boot cần tự cấu hình Redis connection factory từ host và port của container. Khi dependency Spring Session Data Redis có mặt và cấu hình store phù hợp, auto-configuration có thể đăng ký Redis-backed SessionRepository và SessionRepositoryFilter.

Ví dụ property dùng cho cả hai node:

~~~yaml
spring:
  session:
    store-type: redis
    timeout: 10m
    redis:
      namespace: integration-test:sessions
  data:
    redis:
      host: localhost
      port: 6379
~~~

Host và port ở đây là giá trị minh họa. Trong test dùng Testcontainers, truyền host và mapped port động khi khởi động từng node. Tên property có thể thay đổi theo phiên bản Spring Boot; hãy dùng đúng cấu hình mà dependency của dự án hỗ trợ.

Nếu ứng dụng tự khai báo EnableRedisHttpSession, giữ cách cấu hình đó nhất quán và tránh tạo repository/filter thứ hai ngoài ý muốn. Test nên khởi động cùng loại cấu hình mà ứng dụng thực tế dùng.

## 3. Tạo endpoint kiểm thử session

Endpoint test cần thể hiện rõ ba hành động: tạo session, cập nhật session hiện có và đọc session hiện có. Không dùng getSession() ở endpoint update/read vì phương thức đó có thể tạo một session mới nếu cookie bị thiếu hoặc không hợp lệ.

~~~java
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionTestController {

    @PostMapping("/test/session")
    Map<String, Integer> create(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("counter", 1);
        return Map.of("counter", 1);
    }

    @PostMapping("/test/session/increment")
    ResponseEntity<Map<String, Integer>> increment(
            HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        Object value = session.getAttribute("counter");
        if (!(value instanceof Integer counter)) {
            return ResponseEntity.status(HttpStatus.CONFLICT).build();
        }

        int updated = counter + 1;
        session.setAttribute("counter", updated);
        return ResponseEntity.ok(Map.of("counter", updated));
    }

    @GetMapping("/test/session")
    ResponseEntity<Map<String, Integer>> read(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        Object value = session.getAttribute("counter");
        if (!(value instanceof Integer counter)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        return ResponseEntity.ok(Map.of("counter", counter));
    }
}
~~~

Các endpoint này chỉ phục vụ kiểm thử tích hợp, không nên mở công khai trong production. Trong ứng dụng thật, các endpoint nghiệp vụ sử dụng cùng cơ chế HttpSession mà controller này minh họa.

getSession(true) tạo session ở bước đầu tiên. Hai endpoint còn lại dùng getSession(false) để yêu cầu session đã tồn tại. Nếu request đến node B không mang cookie đúng hoặc node B không tìm thấy session trong repository, endpoint trả 401 thay vì âm thầm tạo session mới. Đây là điều kiện quan trọng để test phát hiện cấu hình sai.

## 4. Khởi động hai node độc lập với cùng Redis

Testcontainers có thể khởi chạy một Redis dùng chung. Sau đó, test khởi động hai Spring application context riêng, mỗi context mở server ở cổng ngẫu nhiên nhưng cùng trỏ đến Redis và namespace giống nhau.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class SharedSessionAcrossNodesIT {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7-alpine"))
            .withExposedPorts(6379);

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(SessionTestController.class)
    static class SessionNodeApplication {
    }

    private ConfigurableApplicationContext startNode(String namespace) {
        return new SpringApplicationBuilder(SessionNodeApplication.class)
            .web(WebApplicationType.SERVLET)
            .run(
                "--server.port=0",
                "--spring.session.store-type=redis",
                "--spring.session.timeout=10m",
                "--spring.session.redis.namespace=" + namespace,
                "--spring.data.redis.host=" + REDIS.getHost(),
                "--spring.data.redis.port=" + REDIS.getMappedPort(6379)
            );
    }

    private String baseUrl(ConfigurableApplicationContext context) {
        int port = ((WebServerApplicationContext) context)
            .getWebServer()
            .getPort();
        return "http://localhost:" + port;
    }
}
~~~

Mỗi lần gọi startNode() tạo một application context và servlet server riêng. Cả hai node dùng cùng Redis container, cùng namespace và cùng timeout. Port 0 yêu cầu hệ điều hành cấp cổng trống, tránh xung đột giữa test và các tiến trình đang chạy.

Nếu project có cấu hình component scan hoặc security riêng, hãy dùng application class test có wiring tương ứng. Không để node A và node B vô tình dùng hai cấu hình session khác nhau. Nếu test có Spring Security, cấu hình cùng filter chain, authentication test fixture và CSRF handling ở cả hai node.

## 5. Gửi cookie từ node A sang node B

Khi gọi endpoint tạo session ở node A, Spring Session phát cookie chứa session ID trong response Set-Cookie. Test cần lấy đúng cặp tên-giá trị của cookie rồi gửi trong header Cookie của request đến node B.

~~~java
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;
import org.springframework.context.ConfigurableApplicationContext;

@Test
void createsOnFirstNodeUpdatesOnSecondAndReadsOnFirst() {
    String namespace = "it:sessions:" + UUID.randomUUID();
    RestTemplate http = new RestTemplate();

    try (ConfigurableApplicationContext nodeA = startNode(namespace);
         ConfigurableApplicationContext nodeB = startNode(namespace)) {

        String urlA = baseUrl(nodeA);
        String urlB = baseUrl(nodeB);

        ResponseEntity<Map> created = http.exchange(
            urlA + "/test/session",
            HttpMethod.POST,
            HttpEntity.EMPTY,
            Map.class
        );
        assertThat(created.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(created.getBody()).containsEntry("counter", 1);

        String cookie = extractSessionCookie(created);
        HttpHeaders headers = new HttpHeaders();
        headers.add(HttpHeaders.COOKIE, cookie);
        HttpEntity<Void> withSessionCookie = new HttpEntity<>(headers);

        ResponseEntity<Map> updated = http.exchange(
            urlB + "/test/session/increment",
            HttpMethod.POST,
            withSessionCookie,
            Map.class
        );
        assertThat(updated.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(updated.getBody()).containsEntry("counter", 2);

        ResponseEntity<Map> readAgain = http.exchange(
            urlA + "/test/session",
            HttpMethod.GET,
            withSessionCookie,
            Map.class
        );
        assertThat(readAgain.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(readAgain.getBody()).containsEntry("counter", 2);
    }
}

private String extractSessionCookie(ResponseEntity<?> response) {
    List<String> setCookies =
        response.getHeaders().get(HttpHeaders.SET_COOKIE);
    if (setCookies == null) {
        throw new AssertionError("Response did not contain Set-Cookie");
    }

    return setCookies.stream()
        .map(value -> value.split(";", 2)[0])
        .filter(value -> value.startsWith("SESSION="))
        .findFirst()
        .orElseThrow(() ->
            new AssertionError("SESSION cookie was not found"));
}
~~~

Đoạn code là mẫu kiểm thử cho cookie tên SESSION, là tên mặc định thường dùng của Spring Session cookie resolver. Nếu ứng dụng đổi tên cookie, thay điều kiện lọc cho đúng cấu hình. Không gửi toàn bộ giá trị Set-Cookie làm header Cookie: chỉ gửi cặp name=value, bỏ các thuộc tính Path, Secure, HttpOnly, SameSite và Expires.

Test gửi request thứ hai trực tiếp đến URL node B và request thứ ba đến URL node A. Vì vậy, nó không phụ thuộc sticky routing. Giá trị counter=2 đọc được ở A chứng minh thay đổi do B lưu vào shared repository.

## 6. Vì sao phải đọc lại ở node A?

Nếu chỉ kiểm tra response của node B sau update, test mới chứng minh controller B trả về giá trị mới trong request hiện tại. Giá trị đó có thể vẫn nằm trong session object cục bộ của request B mà chưa được lưu đúng vào repository.

Request thứ ba quay lại node A và tải session lại từ repository. Khi A đọc được counter=2, test xác nhận:

- Node B nhận đúng session ID từ cookie.
- Node B tìm được session đã được node A tạo.
- Node B cập nhật thuộc tính trên session.
- Thay đổi được ghi vào kho chung trước khi response kết thúc.
- Node A tải được thay đổi ở request sau.

Đây là lý do test phải đợi request update hoàn tất rồi mới đọc lại. Không gọi repository ngay trong khi request B vẫn đang chạy và chưa kết thúc filter lifecycle.

## 7. Kiểm thử cùng kịch bản với JDBC

Với Spring Session JDBC, kịch bản HTTP không thay đổi. Hai node phải dùng cùng database, schema, bảng session và cùng serializer. Cấu hình minh họa:

~~~yaml
spring:
  session:
    store-type: jdbc
    timeout: 10m
    jdbc:
      initialize-schema: never
      table-name: SPRING_SESSION
  datasource:
    url: jdbc:postgresql://localhost:5432/session_test
    username: session_test
    password: <secret-from-secret-manager>
~~~

Trong test, có thể dùng Testcontainers PostgreSQL. Chạy schema migration một lần trước khi khởi động hai node; không để mỗi node cùng chạy migration tạo bảng đồng thời. Cả hai node phải dùng cùng URL, schema và table name.

Sau khi tạo session ở A, JDBC repository ghi session và attributes vào database. Node B đọc cùng record, cập nhật attribute và lưu. Request quay lại A đọc giá trị mới từ database. Nếu node B dùng schema hoặc database khác, endpoint update sẽ trả 401 vì không tìm thấy session.

Với JDBC, theo dõi transaction commit và thời điểm filter lưu session. Test phải thực hiện request tiếp theo sau khi response update hoàn tất, không đọc dữ liệu từ transaction chưa commit.

## 8. Kiểm tra âm để chứng minh test phát hiện cấu hình sai

Một test tốt không chỉ pass khi cấu hình đúng mà còn phải phát hiện cấu hình sai. Có thể khởi động node B với namespace khác:

~~~text
Node A namespace: it:sessions:shared
Node B namespace: it:sessions:isolated
~~~

Node A tạo session và trả cookie. Khi gửi cookie đó đến node B, B tìm trong namespace khác nên không thấy session. Endpoint update dùng getSession(false) phải trả 401. Nếu endpoint lại trả 200 và tạo session mới, test fixture đang che giấu lỗi vì đã dùng getSession() hoặc không xác nhận session tồn tại.

Các kiểm tra âm khác:

- Node B dùng Redis host khác.
- Node B dùng cookie name khác nên không đọc được ID.
- Node B dùng serializer không tương thích.
- Node B có timeout hoặc namespace sai.
- Request đến B không gửi cookie.

Chỉ đưa các cấu hình sai này vào test âm riêng. Không làm test chính phụ thuộc vào thứ tự ngẫu nhiên hoặc dữ liệu còn sót trong Redis.

## 9. Cách ly dữ liệu giữa các lần chạy test

Nhiều test có thể chạy song song trên cùng Redis container. Không dùng một namespace cố định cho tất cả test nếu chúng có thể chạy đồng thời.

Nên:

- Tạo namespace có UUID cho từng test hoặc test class.
- Dùng cookie mới cho mỗi scenario.
- Đặt timeout ngắn vừa đủ cho test.
- Xóa đúng key thuộc namespace test khi cleanup.
- Không gọi FLUSHDB trên Redis dùng chung.
- Không dùng Redis production hoặc database production làm backend cho integration test.
- Đóng cả hai application context sau mỗi test để giải phóng server, connection pool và scheduler.

Namespace riêng giúp tránh xung đột dữ liệu nhưng không thay thế cleanup. Redis có thể giữ key đến khi TTL hết; nếu test tạo nhiều session, cần dọn theo prefix được kiểm soát.

## 10. Kiểm tra cookie và resolver

Kiểm thử trên HTTP cần xác nhận session ID được truyền đúng:

- Response tạo session có Set-Cookie.
- Cookie name khớp cấu hình.
- Request đến node B có cùng cặp cookie name=value.
- Node B không phát một session mới thay thế do không tìm thấy ID.
- Response update không làm mất hoặc đổi session ngoài ý muốn.
- Request đọc lại ở A vẫn gửi cùng cookie.

Nếu ứng dụng dùng HeaderHttpSessionIdResolver, thay phần trích cookie bằng việc lấy header response do resolver phát và gửi lại cùng header trong request B/A. Mọi node phải dùng cùng header name và cùng quy tắc đọc/ghi/xóa ID.

Không log giá trị cookie hoặc header session trong test output. Khi assertion thất bại, chỉ in trạng thái HTTP, node đích và request correlation ID; session ID là credential và không nên xuất hiện trong log CI.

## 11. Tích hợp với Spring Security

Trong ứng dụng thật, session thường chứa SecurityContext. Test có thể mở rộng endpoint để trả về principal name thay vì chỉ counter:

- Đăng nhập qua node A.
- Lấy session cookie sau authentication.
- Gọi endpoint được bảo vệ ở node B.
- Xác nhận principal và quyền được khôi phục từ session.
- Cập nhật một attribute ở node B.
- Quay lại node A và xác nhận cả principal lẫn attribute còn đúng.

Nếu dùng form login, xử lý CSRF token theo cấu hình Spring Security. Với endpoint POST, không tắt CSRF chỉ để đơn giản hóa test. Có thể dùng test security configuration hoặc lấy token từ endpoint phù hợp, nhưng phải giữ filter chain thực tế mà ứng dụng cần xác minh.

Test cần kiểm tra cả tình huống logout:

1. Tạo session và đăng nhập ở A.
2. Gửi POST logout đến B với cùng cookie và CSRF token.
3. Gửi lại cookie cũ đến A.
4. Xác nhận endpoint bảo vệ từ chối request.

Điều này chứng minh thao tác invalidate trên một node có hiệu lực ở node còn lại thông qua shared repository.

## 12. Kiểm thử timeout và expiration giữa hai node

Để xác nhận timeout nhất quán:

1. Tạo session ở A với timeout ngắn trong profile test.
2. Gửi request hợp lệ đến B trước khi hết hạn để xác nhận session được đọc.
3. Không gửi thêm request trong khoảng vượt idle timeout.
4. Gửi cookie cũ đến A hoặc B.
5. Xác nhận session không còn được xem là hợp lệ.

Không dựa vào sleep ngắn với thời điểm chính xác tuyệt đối. Dùng Awaitility hoặc polling có giới hạn để chờ repository không còn trả session. Redis TTL và JDBC cleanup có thể dọn vật lý không đồng thời với thời điểm logic hết hạn; test HTTP nên xác nhận hành vi session trước, còn test backend-specific mới kiểm tra key/row.

Hai node phải có cùng timeout. Nếu node A và B dùng cấu hình khác nhau, test có thể cho kết quả phụ thuộc node nào nhận request cuối cùng.

## 13. Kiểm thử cập nhật đồng thời

Kịch bản một request tạo, một request cập nhật tuần tự chứng minh chia sẻ dữ liệu giữa node, nhưng chưa chứng minh repository xử lý đúng khi hai request cùng cập nhật một session.

Để kiểm tra concurrency:

- Tạo session ở A.
- Gửi hai request đồng thời, một đến A và một đến B.
- Mỗi request cập nhật một thuộc tính riêng hoặc cùng một thuộc tính theo chính sách đã chọn.
- Đồng bộ thời điểm đọc và ghi bằng latch/barrier ở test fixture nếu cần.
- Đọc lại session sau khi cả hai response hoàn tất.
- Xác nhận kết quả theo concurrency policy của repository.

Spring Session không tự tạo quy tắc merge nghiệp vụ cho mọi attribute. Nếu repository dùng last-write-wins, test phải thể hiện khả năng lost update. Nếu yêu cầu optimistic locking hoặc merge theo attribute, implementation phải cung cấp cơ chế đó và test phải xác nhận conflict được phát hiện hoặc thay đổi được hợp nhất.

Không dùng counter trong nhiều request đồng thời làm bằng chứng rằng tất cả increment được giữ nếu chưa có atomic operation. Với dữ liệu cần chính xác như số dư, tồn kho hoặc số lượng đơn hàng, dùng database transaction/locking thay vì session.

## 14. Lỗi thường gặp khi test nhiều node

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Node A tạo session nhưng B trả 401 | Redis/database, namespace hoặc schema không giống nhau | In cấu hình không nhạy cảm của từng node và xác nhận cùng backend |
| B trả 200 nhưng A đọc lại giá trị cũ | B chưa lưu thay đổi, save mode hoặc filter lifecycle sai | Đợi response B hoàn tất và kiểm tra repository integration |
| B tạo session mới thay vì cập nhật | Endpoint dùng getSession() hoặc cookie không được gửi/đọc | Dùng getSession(false), kiểm tra Cookie header |
| Test pass khi sticky session bật nhưng fail khi tắt | Hai request vẫn đến cùng node hoặc local session đang được dùng | Gọi trực tiếp hai cổng riêng và xác nhận repository ngoài tiến trình |
| Cookie không được tìm thấy trong response | Cookie name khác hoặc resolver chưa hoạt động | Kiểm tra Set-Cookie và SessionRepositoryFilter |
| Lỗi deserialize ở node B | Serializer hoặc classpath khác node A | Đồng bộ dependency, serializer và DTO |
| Test chạy lúc pass lúc fail | Namespace dùng chung hoặc dữ liệu cũ còn sót | Namespace UUID và cleanup giới hạn |
| Redis container dừng trước khi node đóng | Vòng đời Testcontainers/context không đúng | Đóng application contexts trước khi container kết thúc |
| Session timeout khác nhau giữa node | Property khác hoặc một node dùng cấu hình mặc định | So sánh timeout runtime và property binding |

## 15. Ma trận kiểm thử tối thiểu

| Bước | Node | Request | Kết quả mong đợi |
| --- | --- | --- | --- |
| 1 | A | POST tạo session | counter = 1, response có session cookie |
| 2 | B | POST cập nhật với cookie từ A | Tìm thấy session, counter = 2 |
| 3 | A | GET đọc lại với cùng cookie | counter = 2 |
| 4 | B | GET đọc với cookie sai hoặc thiếu | 401, không tạo session mới |
| 5 | B | Logout với cookie hợp lệ | Session bị invalidate trong repository |
| 6 | A | GET với cookie cũ | 401 hoặc yêu cầu xác thực lại |
| 7 | A/B | Request sau idle timeout | Session hết hạn trên cả hai node |

Khi dùng JDBC, chạy cùng ma trận trên hai application context trỏ đến cùng database/schema. Khi dùng Redis, chạy trên hai context trỏ đến cùng Redis/namespace. Test nên có cả một cấu hình âm với namespace khác để chắc chắn nó thực sự phát hiện lỗi chia sẻ.

## 16. Nguyên tắc triển khai

- Dùng hai application context/server độc lập để đại diện hai node.
- Khởi động cả hai node với cùng Redis hoặc JDBC repository.
- Đồng bộ namespace, schema, serializer, timeout và session ID resolver.
- Tạo session qua HTTP ở node A và lấy cookie/header từ response.
- Gửi đúng định danh đó đến node B, dùng getSession(false) ở endpoint update.
- Chờ response update hoàn tất rồi đọc lại ở node A.
- Không dùng sticky routing hoặc session object trong bộ nhớ để làm test pass.
- Dùng namespace riêng cho từng test và không xóa toàn bộ kho dữ liệu dùng chung.
- Bổ sung test âm, logout, timeout, Spring Security và concurrency theo yêu cầu.
- Không ghi session ID/cookie vào log CI.

Kịch bản tạo session ở node A, cập nhật ở node B rồi đọc lại ở A là bằng chứng trực tiếp rằng Spring Session đang chia sẻ trạng thái qua repository. Test chỉ có giá trị khi hai node thực sự độc lập, dùng cùng kho và cùng cấu hình, đồng thời truyền lại đúng session cookie hoặc header. Kết hợp kiểm tra âm, logout, timeout và concurrency sẽ giúp phát hiện sớm lỗi namespace, resolver, serializer hoặc vòng đời lưu session trong môi trường nhiều instance.
