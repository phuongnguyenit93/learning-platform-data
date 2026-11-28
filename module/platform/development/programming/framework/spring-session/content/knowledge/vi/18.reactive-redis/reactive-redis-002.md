# @EnableRedisWebSession và cấu hình kết nối Lettuce phù hợp

## Mục tiêu bài học

Spring Session Reactive cho phép ứng dụng Spring WebFlux lưu WebSession trong Redis để nhiều instance cùng khôi phục trạng thái phiên. Để bật tích hợp này, ứng dụng có thể dùng annotation `EnableRedisWebSession`. Repository reactive cần một kết nối Redis hỗ trợ reactive; Lettuce là client phổ biến vì cung cấp API non-blocking và tích hợp với Spring Data Redis.

Bài học tập trung vào cách kết hợp WebFlux, Spring Session Redis và Lettuce, cách cấu hình kết nối theo môi trường, cách truy cập WebSession trong pipeline reactive và cách kiểm thử phiên được chia sẻ giữa các instance.

Sau bài học, bạn có thể:

- Phân biệt WebSession của WebFlux với HttpSession của Servlet.
- Giải thích vai trò của `EnableRedisWebSession` và repository Redis reactive.
- Cấu hình `ReactiveRedisConnectionFactory` bằng Lettuce.
- Dùng Spring Boot properties hoặc cấu hình factory tường minh theo nhu cầu.
- Thiết lập timeout, xác thực, TLS và topology Redis phù hợp.
- Tránh gọi API blocking trong luồng reactive.
- Kiểm thử tạo, đọc, cập nhật, invalidate và chia sẻ WebSession qua Redis.

## 1. Vì sao cần Spring Session Reactive với Redis?

Trong WebFlux, mỗi request được xử lý qua pipeline reactive. Một ứng dụng vẫn có thể cần trạng thái giữa các request, chẳng hạn thông tin người dùng đã xác thực, giỏ hàng tạm hoặc tiến trình nhiều bước.

Nếu session chỉ nằm trong bộ nhớ của một instance, request tiếp theo được load balancer chuyển đến instance khác có thể không tìm thấy trạng thái. Spring Session Redis lưu session ở kho dùng chung để các instance cùng đọc và ghi.

Ví dụ triển khai:

~~~text
Browser / API client
       |
       | Cookie chứa WebSession ID
       v
Load balancer
    /       \
   v         v
WebFlux A  WebFlux B
   |          |
   +----+-----+
        |
        v
Reactive Redis Session Repository
        |
        v
      Redis
~~~

Mỗi instance cần dùng cùng Redis deployment, namespace và định dạng dữ liệu tương thích. Khi request đến instance nào, instance đó đọc Session ID từ request, truy xuất WebSession trong Redis và tiếp tục xử lý.

Redis là nơi lưu trạng thái chia sẻ. Lettuce là client quản lý kết nối và gửi lệnh đến Redis. Spring Session là lớp quản lý vòng đời WebSession. Ba thành phần có vai trò khác nhau.

## 2. WebSession khác HttpSession như thế nào?

Spring WebFlux sử dụng `WebSession` thay cho Servlet `HttpSession`.

| Nội dung | Servlet | WebFlux |
|---|---|---|
| API session | `HttpSession` | `WebSession` |
| Request abstraction | `HttpServletRequest` | `ServerWebExchange` |
| Lấy session | `request.getSession()` | `exchange.getSession()` trả về Mono |
| Cách xử lý | Servlet/filter thread model | Reactive pipeline |
| Repository Redis | Servlet Redis session repository | Reactive Redis session repository |
| Annotation Redis | `EnableRedisHttpSession` | `EnableRedisWebSession` |

Không dùng `EnableRedisHttpSession` cho ứng dụng WebFlux. Annotation đó dành cho Servlet. Tương tự, không đưa `HttpSession` vào controller reactive để quản lý phiên.

`ServerWebExchange` cung cấp `getSession()` trả về `Mono<WebSession>`. Việc lấy session nằm trong pipeline, nên có thể kết hợp với các thao tác reactive khác mà không phải chặn thread để chờ kết quả.

### Session được tạo theo cách lazy

Trong WebFlux, việc lấy đối tượng WebSession không nhất thiết đồng nghĩa với việc một session mới đã được lưu ngay. Session thường được bắt đầu khi ứng dụng thay đổi thuộc tính hoặc thực hiện thao tác khiến phiên cần được lưu. Điều này giúp endpoint chỉ đọc hoặc request không dùng session tránh tạo dữ liệu không cần thiết.

Nếu endpoint chỉ cần biết trạng thái đăng nhập, hãy đọc thuộc tính hiện có và tránh thay đổi session ngoài ý muốn. Nếu ứng dụng ghi thuộc tính mới, WebSession được đánh dấu cần lưu theo cơ chế của repository.

## 3. Vai trò của @EnableRedisWebSession

`EnableRedisWebSession` bật tích hợp Spring Session Redis cho WebFlux. Annotation được đặt trên một class cấu hình Spring.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
public class ReactiveSessionConfiguration {
}
~~~

Trong ví dụ, thời gian không hoạt động tối đa được đặt là 1.800 giây, tương đương 30 phút. Hãy chọn giá trị phù hợp với chính sách bảo mật và trải nghiệm sản phẩm.

Annotation này kích hoạt hạ tầng quản lý WebSession dựa trên Redis reactive. Repository cần một bean `ReactiveRedisConnectionFactory` để giao tiếp với Redis. Với Lettuce, `LettuceConnectionFactory` cung cấp API reactive phù hợp.

### Các thành phần trong cấu hình

| Thành phần | Trách nhiệm |
|---|---|
| `EnableRedisWebSession` | Bật WebSession repository Redis cho WebFlux |
| `ReactiveRedisConnectionFactory` | Cung cấp kết nối Redis reactive |
| `LettuceConnectionFactory` | Factory dùng Lettuce, hỗ trợ cả API imperative và reactive |
| `ReactiveRedisSessionRepository` | Quản lý dữ liệu WebSession trong Redis |
| `WebSessionManager` | Tích hợp WebSession vào request/response WebFlux |
| `WebSessionIdResolver` | Đọc và gửi định danh session theo giao thức HTTP |

Không cần tự tạo một repository thứ hai nếu annotation đã đăng ký repository cần thiết. Tạo thêm bean hoặc bật một cơ chế session khác có thể khiến ứng dụng có cấu hình trùng hoặc làm auto-configuration lùi lại.

### Chọn một cơ chế cấu hình

Có thể để Spring Boot quản lý kết nối Redis bằng properties, hoặc tự khai báo Lettuce factory khi cần cấu hình client chi tiết. Không nên khai báo nhiều `RedisConnectionFactory` cạnh tranh nhau nếu không có yêu cầu định tuyến rõ ràng.

## 4. Dependency cho WebFlux, Spring Session và Redis

Với Gradle, dependency thường gồm:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-data-redis-reactive")
    implementation("org.springframework.session:spring-session-data-redis")
}
~~~

Với Maven, khai báo các starter tương ứng và để Spring Boot dependency management quản lý phiên bản tương thích.

Không tự pin version của Spring Session hoặc Spring Data Redis khác với BOM của Boot nếu chưa kiểm tra ma trận tương thích. Phiên bản Spring Framework, Spring Data Redis và Spring Session cần thuộc tập phiên bản hỗ trợ lẫn nhau.

### Kiểm tra loại ứng dụng

Ứng dụng cần chạy trên WebFlux. Nếu đồng thời thêm Spring MVC starter, Spring Boot có thể chọn application type Servlet theo quy tắc auto-configuration. Hãy giữ classpath phù hợp với WebFlux hoặc cấu hình application type có chủ đích và xác minh runtime thực tế.

Không dùng cả hai annotation `EnableRedisWebSession` và `EnableRedisHttpSession` trong cùng một ứng dụng chỉ để thử nghiệm. Chọn đúng web stack và một cơ chế session tương ứng.

## 5. Cấu hình Lettuce qua Spring Boot

Lettuce là Redis client được Spring Boot thường dùng mặc định khi có mặt trên classpath. Lettuce hỗ trợ giao tiếp reactive, do đó connection factory do Boot tạo có thể được sử dụng như `ReactiveRedisConnectionFactory`.

Ví dụ cấu hình trong `application.properties`:

~~~properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.data.redis.connect-timeout=2s
spring.data.redis.timeout=2s
~~~

Các thuộc tính thường gặp:

| Property | Ý nghĩa |
|---|---|
| `spring.data.redis.host` | Host Redis |
| `spring.data.redis.port` | Cổng Redis |
| `spring.data.redis.username` | ACL username nếu Redis yêu cầu |
| `spring.data.redis.password` | Mật khẩu hoặc ACL password |
| `spring.data.redis.database` | Logical database được sử dụng |
| `spring.data.redis.connect-timeout` | Thời gian chờ thiết lập kết nối |
| `spring.data.redis.timeout` | Timeout lệnh theo cấu hình Boot/client |

Prefix properties có thể khác giữa các dòng Spring Boot. Với các dòng Boot hiện đại, nhóm property kết nối Redis thường nằm dưới `spring.data.redis.*`. Khi nâng cấp, đối chiếu configuration metadata của đúng release thay vì giữ nguyên prefix cũ một cách máy móc.

Không ghi mật khẩu trực tiếp vào source control. Hãy cấp giá trị qua environment variable, secret manager hoặc hệ thống cấu hình bảo mật của nền tảng triển khai. Chỉ cấp ACL quyền truy cập database/key namespace mà ứng dụng cần.

### Boot auto-configuration cung cấp gì?

Khi dependency và properties phù hợp, Boot có thể tạo `LettuceConnectionFactory` và expose nó dưới các interface connection factory của Spring Data Redis. `EnableRedisWebSession` sử dụng bean reactive phù hợp để tạo repository.

Trong trường hợp này, không cần tự tạo một factory thứ hai. Trước khi thêm cấu hình Java, hãy kiểm tra application context đã có factory chưa.

## 6. Cấu hình Lettuce tường minh khi cần kiểm soát client

Nếu cần cấu hình command timeout hoặc một topology Redis cụ thể, có thể tự khai báo `LettuceConnectionFactory`.

Ví dụ cho Redis standalone trong môi trường phát triển:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class LettuceConfiguration {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        LettuceClientConfiguration client =
                LettuceClientConfiguration.builder()
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(server, client);
    }
}
~~~

`LettuceConnectionFactory` triển khai cả `RedisConnectionFactory` và `ReactiveRedisConnectionFactory`. Điều đó cho phép cùng factory được sử dụng bởi thành phần imperative và reactive nếu ứng dụng có nhu cầu và cấu hình được thiết kế rõ.

Ví dụ này không đặt username hoặc password. Trong môi trường có xác thực, cấu hình chúng từ secret an toàn vào `RedisStandaloneConfiguration` hoặc dùng Boot properties. Không đặt credential cố định trong source code.

### Không trộn auto-config và custom factory một cách vô ý

Khi khai báo bean factory thủ công, auto-configuration của Boot có thể back off do đã có bean phù hợp. Vì vậy:

- Chỉ tạo custom factory khi thật sự cần.
- Dùng một bean factory rõ ràng cho repository session.
- Nếu có nhiều Redis deployment, xác định factory nào được repository sử dụng.
- Dùng qualifier hoặc cấu hình repository tường minh khi nhiều factory là yêu cầu thật.
- Kiểm tra context sau khi khởi động để xác nhận factory đúng.

Đừng để một cache Redis dùng factory A còn session repository vô tình dùng factory B vì bean mặc định hoặc @Primary thay đổi.

## 7. Cấu hình timeout và thời hạn session

Timeout của kết nối Redis và thời hạn session là hai loại thời gian khác nhau.

| Thời hạn | Ý nghĩa |
|---|---|
| Connect timeout | Thời gian tối đa chờ thiết lập kết nối đến Redis |
| Command timeout | Thời gian chờ một lệnh Redis hoàn tất |
| Session idle timeout | Thời gian không hoạt động tối đa của WebSession |
| Redis key TTL | Thời gian tồn tại vật lý của key session |
| Cookie expiration | Thời gian client giữ cookie định danh |

Trong ví dụ annotation:

~~~java
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
~~~

thời hạn không hoạt động của session là 30 phút. Repository dùng chính sách này để quản lý thời hạn dữ liệu. Không tăng command timeout để kéo dài session; hai cấu hình giải quyết hai vấn đề khác nhau.

Một command timeout quá dài có thể khiến request giữ tài nguyên lâu khi Redis gặp sự cố. Một timeout quá ngắn có thể tạo lỗi giả khi mạng có độ trễ bình thường. Hãy đặt giá trị theo latency thực tế, SLA và chính sách retry.

Không dùng cookie expiration làm cơ chế duy nhất để kết thúc session. Dữ liệu phía server phải hết hạn theo repository, ngay cả khi client giữ cookie cũ.

## 8. WebSession trong reactive controller

Controller WebFlux thao tác session trong pipeline reactive.

Ví dụ tăng số lần truy cập:

~~~java
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveSessionController {

    @GetMapping(value = "/api/session/visit",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, Integer>> visit(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            Integer current = session.getAttribute("visits");
            int next = current == null ? 1 : current + 1;

            session.getAttributes().put("visits", next);

            return Map.of("visits", next);
        });
    }
}
~~~

Mỗi request gửi cùng cookie session sẽ đọc giá trị trước đó, tăng lên rồi ghi lại. Session được lưu thông qua repository khi WebFlux hoàn tất việc xử lý response và quá trình lưu session được thực hiện.

Không gọi `block()` trong controller reactive để chờ session. Việc chặn event-loop thread làm giảm khả năng phục vụ đồng thời và có thể gây nghẽn toàn ứng dụng.

### Đọc session mà không tạo dữ liệu không cần thiết

Nếu chỉ cần đọc thuộc tính, không thay đổi session. Hãy tránh thêm thuộc tính mặc định hoặc cập nhật timestamp phụ trong mọi request nếu không cần thiết.

Một endpoint public không nên gọi session chỉ để kiểm tra một thông tin không liên quan. Mỗi lần sử dụng session đều có thể tạo thêm công việc truy xuất Redis.

## 9. Invalidate và thay đổi Session ID

WebFlux `WebSession` cung cấp các thao tác reactive để kết thúc hoặc thay đổi định danh phiên.

Ví dụ logout:

~~~java
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@PostMapping("/api/session/logout")
public Mono<Void> logout(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(session -> session.invalidate());
}
~~~

Thao tác invalidate trả về `Mono<Void>`. Hãy trả publisher đó về cho framework để quá trình kết thúc phiên nằm trong pipeline. Không gọi block để chờ.

Khi cần thay Session ID sau xác thực, `WebSession` có phương thức `changeSessionId()` trả về publisher. Ví dụ:

~~~java
@PostMapping("/api/session/rotate-id")
public Mono<String> rotateId(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(session ->
                    session.changeSessionId()
                            .thenReturn("Session identifier changed"));
}
~~~

Đổi ID thường được dùng để giảm nguy cơ session fixation sau khi người dùng đăng nhập hoặc thay đổi mức đặc quyền. Trong ứng dụng dùng Spring Security WebFlux, ưu tiên cấu hình session fixation protection của framework và tránh thực hiện thay đổi ID chồng lấn với cơ chế đó.

### Cookie và resolver trong WebFlux

WebFlux sử dụng `WebSessionIdResolver` thay cho `HttpSessionIdResolver` của Servlet. Cấu hình mặc định thường truyền WebSession ID qua cookie. Nếu tùy chỉnh cookie, hãy dùng API resolver dành cho WebFlux và thống nhất cookie name, path, domain và thuộc tính bảo mật giữa các instance.

Không dùng `CookieHttpSessionIdResolver` của Servlet trong WebFlux. Đây là hai API thuộc hai web stack khác nhau.

## 10. Lettuce và mô hình non-blocking

Lettuce dựa trên Netty và hỗ trợ reactive API của Spring Data Redis. Khi sử dụng trong WebFlux, thao tác Redis có thể được biểu diễn thành publisher và phối hợp với các publisher khác.

Ví dụ khái niệm:

~~~text
HTTP request
     |
     v
WebFlux handler
     |
     v
Mono / Flux pipeline
     |
     v
ReactiveRedisConnectionFactory
     |
     v
Lettuce reactive API
     |
     v
Redis server
~~~

Các nguyên tắc quan trọng:

- Không gọi API blocking trong event-loop.
- Không dùng `RedisTemplate` hoặc JDBC blocking trực tiếp trong reactive chain.
- Với dữ liệu Redis nghiệp vụ cần thao tác reactive, cân nhắc `ReactiveRedisTemplate`.
- Không tự tạo connection mới cho mỗi request nếu factory đã quản lý connection.
- Đặt timeout cho kết nối và command.
- Giới hạn concurrency ở các luồng downstream có năng lực hữu hạn.

Spring Session repository tự quản lý các thao tác session. Không tự ghi key session bằng `ReactiveRedisTemplate` vì có thể phá cấu trúc key, serialization, expiration hoặc metadata mà repository quản lý.

### Vì sao không dùng Jedis blocking?

Jedis chủ yếu cung cấp API imperative/blocking. Trong ứng dụng WebFlux, gọi lệnh blocking trên event-loop có thể giữ thread trong lúc chờ mạng và làm chậm nhiều request khác.

Lettuce có reactive support và phù hợp với pipeline non-blocking. Nếu một ứng dụng vẫn cần thư viện blocking cho công việc riêng, hãy cô lập công việc đó trên scheduler phù hợp và không để nó chặn event-loop. Đối với session reactive, dùng factory hỗ trợ `ReactiveRedisConnectionFactory`.

## 11. Standalone, Sentinel và Cluster

Lettuce có thể kết nối Redis standalone, Sentinel hoặc Cluster. Cần chọn cấu hình phù hợp với topology thật.

| Topology | Khi dùng | Điểm cần lưu ý |
|---|---|---|
| Standalone | Phát triển hoặc hệ thống Redis đơn giản | Một endpoint; cần kế hoạch HA riêng |
| Sentinel | Redis primary/replica có failover được Sentinel quản lý | Cấu hình danh sách Sentinel và master name |
| Cluster | Phân mảnh dữ liệu và mở rộng theo shard | Client cần xử lý topology và redirect |

Ví dụ cấu hình Sentinel hoặc Cluster cần dùng class cấu hình tương ứng của Spring Data Redis. Không dùng cấu hình standalone rồi chỉ đổi host thành một node bất kỳ trong cluster nếu không hiểu topology.

Với môi trường production:

- Dùng DNS/service discovery hoặc endpoint ổn định.
- Bật TLS nếu kết nối đi qua mạng không tin cậy.
- Dùng ACL username/password có quyền tối thiểu.
- Kiểm tra failover và reconnect behavior.
- Theo dõi latency, connection errors, command timeout và pool usage nếu có pool.
- Kiểm thử session vẫn được tải sau failover.

### Connection pooling

Lettuce connection có thể được chia sẻ và an toàn cho nhiều thao tác theo cách Spring Data Redis quản lý. Không mặc định rằng mọi ứng dụng reactive đều cần pool lớn.

Chỉ cấu hình pool khi có yêu cầu đo đạc hoặc loại thao tác cần connection riêng. Nếu dùng pool, kiểm tra dependency hỗ trợ pool, giới hạn active/idle, thời gian chờ mượn connection và hành vi khi Redis chậm. Pool quá nhỏ có thể tạo hàng đợi; pool quá lớn có thể làm Redis chịu quá nhiều kết nối.

## 12. Cấu hình namespace và nhiều instance

Các instance WebFlux phải dùng chung cấu hình session tương thích. Nếu mỗi instance dùng namespace khác nhau, request chuyển instance sẽ không tìm thấy session.

Ví dụ, một ứng dụng có thể dùng namespace riêng theo môi trường:

~~~text
shop:dev:web-session
shop:prod:web-session
~~~

Cấu hình namespace có thể được đặt qua thuộc tính annotation hoặc extension point mà phiên bản Spring Session hỗ trợ. Hãy kiểm tra API của đúng release trước khi thêm thuộc tính. Không dùng cùng namespace cho các ứng dụng không chia sẻ cùng định dạng session.

Các yếu tố cần thống nhất:

- Redis endpoint và database/cluster.
- Namespace session.
- Serializer và định dạng thuộc tính.
- Session idle timeout.
- Cookie resolver và thuộc tính cookie.
- Phiên bản Spring Session tương thích trong rolling deployment.

Nếu một instance dùng serializer khác, instance còn lại có thể tìm thấy session nhưng không khôi phục được thuộc tính. Nếu cookie name khác, client có thể không gửi đúng Session ID cho một instance.

## 13. Bảo mật và xử lý lỗi kết nối

Session ID là thông tin nhạy cảm dạng bearer. Người có ID và gửi lại được ID có thể tiếp tục phiên nếu repository còn dữ liệu hợp lệ.

Các biện pháp cần áp dụng:

- Dùng HTTPS.
- Cookie session bật Secure và HttpOnly; chọn SameSite theo luồng ứng dụng.
- Không đưa Session ID vào URL hoặc log.
- Không log Redis password hoặc URI chứa credential.
- Dùng Redis ACL với quyền tối thiểu.
- Bảo vệ Redis khỏi truy cập công khai.
- Giữ DTO session nhỏ và không lưu secret không cần thiết.
- Kiểm soát CORS nếu frontend khác origin.

### Khi Redis không khả dụng

Nếu Redis mất kết nối, repository reactive không thể tải hoặc lưu session. Request sử dụng session có thể nhận lỗi từ pipeline. Không nên âm thầm tạo một session mới trong bộ nhớ local để giả lập trạng thái cũ; điều đó làm mất tính nhất quán giữa các instance.

Hãy xác định chính sách lỗi:

- Endpoint nào có thể trả lỗi tạm thời và cho client retry.
- Endpoint nào không được xử lý nếu không đọc được session.
- Timeout và circuit breaker ở các dịch vụ downstream.
- Cách báo lỗi không tiết lộ hạ tầng nội bộ.
- Cách giám sát connection failure và latency.

Không retry vô hạn trong reactive pipeline. Retry cần giới hạn số lần, backoff và chỉ áp dụng cho lỗi có thể hồi phục. Với thao tác ghi, phải xem xét khả năng lệnh đã được thực hiện ở Redis nhưng response bị mất; retry có thể cần idempotency.

## 14. Kiểm thử WebSession với Redis và WebTestClient

Một test chỉ xác minh endpoint trả HTTP 200 chưa chứng minh session đã được lưu trong Redis. Cần kiểm tra cookie, thuộc tính session và việc khôi phục ở request tiếp theo.

### Kiểm thử cùng client qua nhiều request

Một quy trình kiểm thử:

1. Gửi request đến endpoint tăng counter.
2. Nhận cookie WebSession ID trong response.
3. Gửi request tiếp theo với cookie đó.
4. Xác minh counter tăng từ giá trị trước đó.
5. Gọi endpoint logout.
6. Gửi lại ID cũ và xác minh session không còn được khôi phục.

Ví dụ kiểm thử với WebTestClient:

~~~java
EntityExchangeResult<String> first = webTestClient.get()
        .uri("/api/session/visit")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .returnResult();

String sessionCookie = first.getResponseCookies()
        .getFirst("SESSION")
        .getValue();

webTestClient.get()
        .uri("/api/session/visit")
        .cookie("SESSION", sessionCookie)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.visits").isEqualTo(2);
~~~

Ví dụ giả định cookie tên `SESSION` và endpoint trả JSON. Nếu ứng dụng dùng tên cookie khác, thay bằng tên đã cấu hình. Trong test đầy đủ, cần kiểm tra cookie không null trước khi lấy giá trị.

### Kiểm thử bằng Redis thật

Dùng Testcontainers hoặc Redis test instance để xác minh:

- Repository reactive thực sự kết nối Redis.
- Session được lưu sau request.
- Session được khôi phục qua request tiếp theo.
- Invalidate làm session không còn hợp lệ.
- TTL được đặt theo cấu hình.
- Serializer hoạt động với DTO được lưu.

Mock WebSession không kiểm tra Redis connection, serialization hoặc TTL.

### Kiểm thử nhiều instance

Khởi động hai application context hoặc hai instance cùng Redis, namespace và serializer:

1. Request tạo session đến instance A.
2. Lấy cookie từ response.
3. Gửi request đến instance B với cùng cookie.
4. Xác minh B đọc được thuộc tính do A lưu.
5. Cập nhật session tại B và đọc lại tại A.

Test này chứng minh dữ liệu session nằm ở kho chia sẻ thay vì bộ nhớ local của một instance.

## 15. Những lỗi thường gặp

**Dùng @EnableRedisHttpSession trong WebFlux.**  
Đó là annotation Servlet. Dùng `EnableRedisWebSession` cho reactive WebSession.

**Không tìm thấy ReactiveRedisConnectionFactory.**  
Kiểm tra Lettuce dependency, Redis starter, custom factory bean và điều kiện auto-configuration.

**Ứng dụng có RedisConnectionFactory nhưng session reactive không khởi động.**  
Kiểm tra factory có triển khai `ReactiveRedisConnectionFactory` hay không. Factory imperative-only không đủ cho repository reactive.

**RedisTemplate hoạt động nhưng WebSession không lưu được.**  
RedisTemplate chỉ chứng minh một đường kết nối/serializer khác hoạt động. Kiểm tra reactive factory và Spring Session repository.

**Request reactive bị chậm hoặc nghẽn.**  
Tìm lời gọi `block()`, Jedis blocking, JDBC hoặc HTTP client blocking trong event-loop. Chuyển sang reactive API hoặc cô lập blocking work.

**Mỗi request tạo một session mới.**  
Kiểm tra cookie có được trả và gửi lại không, domain/path/SameSite/Secure, resolver và proxy.

**Instance A đọc được nhưng B không đọc được.**  
Kiểm tra Redis endpoint, namespace, serializer, cookie và phiên bản thư viện.

**Logout trả response nhưng session cũ vẫn tồn tại.**  
Đảm bảo publisher từ `invalidate()` được trả về và hoàn tất; xác minh repository và cookie resolver.

**Redis timeout bị hiểu nhầm là session timeout.**  
Connect/command timeout là thời gian chờ mạng/lệnh; session idle timeout là chính sách vòng đời WebSession.

## 16. Checklist cấu hình trước production

- Ứng dụng được khởi chạy ở reactive WebFlux mode.
- Có dependency Spring Session Redis và Lettuce tương thích.
- Có đúng một Redis connection factory phù hợp với reactive API.
- `EnableRedisWebSession` được bật đúng một lần nếu dùng cấu hình annotation.
- Redis endpoint, ACL, password và TLS được cấu hình từ nguồn bảo mật.
- Connect timeout và command timeout phù hợp latency thực tế.
- Session idle timeout được chọn theo chính sách.
- Cookie resolver có thuộc tính bảo mật phù hợp.
- Namespace và serializer thống nhất giữa các instance.
- Không có blocking call trong reactive event-loop.
- Có metric về Redis latency, lỗi kết nối và session request.
- Có integration test tạo, tải, cập nhật, invalidate và chia sẻ session.
- Có kiểm thử failover hoặc reconnect theo topology Redis.

## 17. Tự kiểm tra

1. `EnableRedisWebSession` dùng cho Servlet hay WebFlux?
2. Vì sao WebFlux dùng `WebSession` thay vì `HttpSession`?
3. Repository reactive cần interface connection factory nào?
4. Vì sao Lettuce phù hợp với WebFlux?
5. `LettuceConnectionFactory` có thể cung cấp những loại connection factory nào?
6. Connect timeout khác session idle timeout ở đâu?
7. Vì sao không nên gọi `block()` trong controller reactive?
8. Khi nào cần khai báo Lettuce factory thủ công thay vì dùng Boot auto-configuration?
9. Vì sao nhiều instance cần cùng namespace và serializer?
10. Cần kiểm thử những gì để xác minh WebSession được chia sẻ qua Redis?
11. Vì sao RedisTemplate hoạt động không chứng minh reactive session repository đã được cấu hình đúng?
12. Khi Redis không khả dụng, vì sao không nên âm thầm chuyển sang session local?

### Gợi ý trả lời

1. WebFlux.
2. WebFlux dùng request/response reactive và quản lý session bằng publisher; WebSession phù hợp với mô hình đó.
3. `ReactiveRedisConnectionFactory`.
4. Lettuce hỗ trợ API reactive/non-blocking thông qua Spring Data Redis.
5. Nó triển khai cả `RedisConnectionFactory` và `ReactiveRedisConnectionFactory`.
6. Connect timeout giới hạn thời gian mở kết nối; session idle timeout giới hạn thời gian phiên không hoạt động.
7. Vì block giữ event-loop thread và làm giảm khả năng xử lý đồng thời.
8. Khi cần cấu hình client hoặc topology riêng mà Boot properties không đáp ứng.
9. Để instance khác tìm đúng session và deserialize được dữ liệu.
10. Tạo session ở A, gửi cookie đến B, xác minh thuộc tính, cập nhật và kiểm tra invalidate.
11. RedisTemplate có thể dùng imperative factory và serializer khác với repository reactive.
12. Vì session local không chia sẻ giữa instance và làm sai trạng thái xác thực hoặc dữ liệu người dùng.

## Kết luận

`EnableRedisWebSession` bật Spring Session cho WebFlux và cần kết nối Redis reactive. Lettuce là lựa chọn phù hợp vì `LettuceConnectionFactory` cung cấp `ReactiveRedisConnectionFactory` cùng API Redis imperative. Có thể dùng Boot auto-configuration với properties hoặc khai báo factory tường minh khi cần kiểm soát client; cần tránh tạo factory trùng hoặc chọn sai bean.

WebFlux thao tác qua `WebSession` và publisher, vì vậy không chặn event-loop bằng API blocking. Session timeout, Redis command timeout và cookie expiration là các chính sách khác nhau. Trong môi trường nhiều instance, Redis endpoint, namespace, serializer và resolver phải tương thích. Hãy xác minh bằng WebTestClient và Redis thật các luồng tạo, đọc, cập nhật, invalidate, TTL và chia sẻ session trước khi triển khai production.

