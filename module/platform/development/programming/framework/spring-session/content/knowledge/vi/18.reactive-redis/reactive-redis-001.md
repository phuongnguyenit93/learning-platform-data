# ReactiveRedisSessionRepository và lưu phiên qua API Redis phản ứng

Spring Session có thể lưu phiên của ứng dụng WebFlux trong Redis thông qua **ReactiveRedisSessionRepository**. Repository này dùng API Redis phản ứng của Spring Data Redis để đọc và ghi dữ liệu mà không chặn thread xử lý request. Thay vì làm việc với HttpSession của Servlet, ứng dụng WebFlux sử dụng WebSession; Spring Session kết nối vòng đời WebSession với kho Redis dùng chung.

Mô hình này phù hợp khi toàn bộ request path được xây dựng theo reactive stack: WebFlux, Mono/Flux, reactive Redis connection và các thành phần I/O không blocking. Nếu gọi API Redis blocking hoặc tự block() trong event-loop thread, ứng dụng có thể mất lợi ích của kiến trúc phản ứng, tăng độ trễ và làm cạn thread xử lý.

## 1. Reactive session khác Servlet session như thế nào?

Spring MVC/Servlet thường làm việc với HttpSession và filter SessionRepositoryFilter. WebFlux làm việc với WebSession và WebSessionManager. Hai API cùng biểu diễn trạng thái phiên nhưng thuộc hai mô hình xử lý request khác nhau.

| Nội dung | Servlet | WebFlux |
|---|---|---|
| API phiên ứng dụng | HttpSession | WebSession |
| Tích hợp Spring Session | SessionRepositoryFilter | WebSessionManager và adapter WebSessionStore |
| Repository | SessionRepository | ReactiveSessionRepository |
| Kiểu trả về thao tác lưu trữ | Thường đồng bộ ở ranh giới repository | Mono/Flux |
| Redis API | Spring Data Redis blocking hoặc tùy cấu hình | Reactive Spring Data Redis |
| Thread model | Thường một thread xử lý request theo Servlet model | Event loop và publisher bất đồng bộ |

Không đăng ký @EnableRedisHttpSession cho ứng dụng WebFlux thuần. Annotation đó cấu hình tích hợp Servlet. Với WebFlux và Redis, dùng @EnableRedisWebSession để cấu hình reactive web session.

## 2. ReactiveRedisSessionRepository là gì?

ReactiveRedisSessionRepository là implementation reactive của ReactiveSessionRepository, lưu session trong Redis. Nó cung cấp các thao tác bất đồng bộ để tạo, tìm, lưu và xóa session. Spring Session kết nối repository này với vòng đời WebSession để controller và handler có thể sử dụng session thông qua WebFlux API.

Các thao tác repository ở mức khái niệm:

| Thao tác | Ý nghĩa | Kiểu kết quả reactive |
|---|---|---|
| createSession() | Tạo session mới | Mono<S> |
| findById(id) | Tìm session theo ID | Mono<S> |
| save(session) | Lưu trạng thái session | Mono<Void> |
| deleteById(id) | Xóa session | Mono<Void> |

Mono biểu diễn kết quả có tối đa một phần tử hoặc hoàn tất rỗng; Flux biểu diễn một chuỗi phần tử. Publisher thường là lazy: thao tác Redis chỉ thực thi khi publisher được subscribe. Khi dùng Spring WebFlux, framework sẽ subscribe vào publisher trong quá trình xử lý request/response. Vì vậy, ứng dụng nên ghép các thao tác vào chuỗi reactive và trả publisher cho framework.

Không gọi subscribe() bên trong controller chỉ để kích hoạt lưu session rồi trả response ngay. Cách đó tách công việc khỏi vòng đời request, khiến lỗi khó truyền về client và có thể làm response hoàn tất trước khi dữ liệu được lưu.

## 3. Bật Redis WebSession trong ứng dụng WebFlux

Với Spring Session, cấu hình reactive Redis session thường bắt đầu bằng @EnableRedisWebSession:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
public class ReactiveSessionConfiguration {
}
~~~

Annotation bật tích hợp WebFlux session với Redis và cấu hình thời gian không hoạt động tối đa là 1.800 giây trong ví dụ. Spring Session cung cấp repository reactive và tích hợp nó vào cơ chế quản lý WebSession.

Ứng dụng cũng cần một ReactiveRedisConnectionFactory. Với Spring Boot, connection factory thường được auto-configure từ cấu hình Redis. Nếu tự cấu hình, có thể dùng Lettuce:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisConnectionConfiguration {

    @Bean
    ReactiveRedisConnectionFactory reactiveRedisConnectionFactory() {
        return new LettuceConnectionFactory("localhost", 6379);
    }
}
~~~

Đây là cấu hình local tối giản. Production cần cấu hình host, TLS, xác thực, database/cluster endpoint, timeout và connection pool theo môi trường. Không tạo thêm factory thủ công nếu Spring Boot đã cung cấp bean phù hợp; hai factory trỏ đến hai Redis khác nhau sẽ làm session khó được chia sẻ giữa các instance.

### 3.1. Dependency

Một ứng dụng WebFlux cần dependency WebFlux và Spring Session Redis tương thích với phiên bản Spring Boot đang dùng. Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.session:spring-session-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-data-redis-reactive")
}
~~~

Quản lý version bằng Spring Boot dependency management hoặc BOM phù hợp. Tên starter và cách kéo dependency có thể thay đổi theo phiên bản Boot; kiểm tra dependency tree để tránh trộn các phiên bản Spring Session, Spring Data Redis và Spring Framework không tương thích.

## 4. Luồng request với WebSession và Redis

Khi client gửi request có session ID, Spring WebFlux dùng WebSessionManager để lấy WebSession. Tích hợp Spring Session sử dụng repository reactive để tìm session trong Redis. Khi handler thay đổi thuộc tính hoặc kết thúc phiên, thay đổi được lưu qua reactive repository theo vòng đời response.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as WebFlux WebSessionManager
    participant R as ReactiveRedisSessionRepository
    participant D as Redis
    C->>W: HTTP request + session identifier
    W->>R: findById(id)
    R->>D: Reactive Redis operations
    D-->>R: Session data
    R-->>W: Mono<WebSession state>
    W-->>C: Cấp WebSession cho handler
    Note over W: Handler đọc hoặc sửa attributes
    W->>R: save(session) khi cần
    R->>D: Reactive write + expiration
    D-->>R: Hoàn tất
    R-->>W: Mono<Void> complete
    W-->>C: HTTP response
~~~

Sơ đồ mô tả luồng khái niệm; chi tiết command, cấu trúc key, thời điểm flush và cách lưu có thể thay đổi theo phiên bản. Ứng dụng không nên phụ thuộc vào tên key nội bộ của repository để xử lý nghiệp vụ.

## 5. Đọc và cập nhật WebSession trong controller

Trong WebFlux, có thể lấy session qua ServerWebExchange.getSession(). Phương thức này trả về Mono<WebSession>, do đó thao tác với session cần nằm trong chuỗi reactive.

Ví dụ lưu mã giỏ hàng:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class CartController {

    @PostMapping("/cart/session")
    public Mono<ResponseEntity<Void>> saveCart(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(session -> {
                session.getAttributes().put("cartId", "CART-908");
                return ResponseEntity.noContent().build();
            });
    }
}
~~~

getAttributes() trả về map thuộc tính của WebSession. Việc thay đổi map làm session được đánh dấu cần lưu theo cơ chế WebSession. WebFlux/Spring Session quản lý việc lưu ở ranh giới response. Nếu cần chủ động chờ thao tác save() trong một flow đặc biệt, có thể ghép session.save() bằng then(...); không được bỏ publisher hoặc gọi subscribe() độc lập.

Đọc thuộc tính:

~~~java
@GetMapping("/cart/session")
public Mono<String> readCart(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> {
            Object value = session.getAttribute("cartId");
            return value == null ? "Chưa có giỏ hàng" : value.toString();
        });
}
~~~

Đoạn mã minh họa cách đọc một thuộc tính. Trong ứng dụng thật, nên trả DTO và xử lý session chưa tồn tại theo đúng nghiệp vụ; việc gọi getSession() có thể tạo hoặc bắt đầu một session tùy cách sử dụng.

## 6. Xóa thuộc tính, đổi ID và invalidate

WebSession cung cấp các thao tác phản ứng cho vòng đời session:

- getAttributes().remove(name) để bỏ một thuộc tính.
- changeSessionId() để thay session ID theo chính sách bảo mật.
- invalidate() để kết thúc session.
- save() để yêu cầu lưu trạng thái theo API.

Ví dụ logout:

~~~java
@PostMapping("/logout")
public Mono<ResponseEntity<Void>> logout(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::invalidate)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

Logout cần invalidate phía server để ID cũ không còn trỏ đến một session hợp lệ. Việc xóa ID ở client cũng cần được thực hiện theo cơ chế resolver đang dùng, thường là hết hạn cookie hoặc xóa header token ở client. Chỉ xóa cookie phía client mà không invalidate repository không thu hồi được một bản sao session ID đã bị lộ.

Đổi ID sau xác thực giúp chống session fixation. Nếu server phát ID mới, client phải dùng định danh mới cho request tiếp theo. Không tự đặt session ID theo username hoặc giá trị do client cung cấp.

## 7. Reactive Redis API và cách lưu dữ liệu

Spring Session quản lý việc serialize session và gọi Redis reactive API bên trong ReactiveRedisSessionRepository. Ứng dụng WebFlux thông thường nên thao tác qua WebSession, không tự tạo key Redis cho từng thuộc tính session.

Nếu triển khai một repository tùy chỉnh hoặc một cache phụ trợ, Spring Data Redis cung cấp ReactiveRedisTemplate và các reactive operations. Ví dụ đơn giản dưới đây minh họa lưu một payload byte array có TTL; đây không phải cách thay thế trực tiếp cho schema nội bộ của Spring Session:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import reactor.core.publisher.Mono;

public class ReactivePayloadStore {

    private final ReactiveRedisTemplate<String, byte[]> redis;

    public ReactivePayloadStore(
            ReactiveRedisTemplate<String, byte[]> redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(
            String key,
            byte[] payload,
            Duration ttl) {
        return redis.opsForValue().set(key, payload, ttl);
    }

    public Mono<byte[]> find(String key) {
        return redis.opsForValue().get(key);
    }

    public Mono<Boolean> delete(String key) {
        return redis.delete(key).map(count -> count > 0);
    }
}
~~~

Ví dụ cho thấy các thao tác trả về publisher. Trong repository session thực tế, ngoài payload còn cần xử lý metadata, thời hạn, cập nhật lần truy cập, session ID, xóa và serialization theo hợp đồng Spring Session. Không dùng đoạn cache đơn giản này để tự tạo một hệ thống session production nếu chưa triển khai đầy đủ các yêu cầu đó.

### 7.1. Serialization và RedisSerializationContext

ReactiveRedisTemplate cần một RedisSerializationContext xác định cách serialize key, value, hash key và hash value. Key thường dùng string serializer; value có thể là byte array hoặc serializer object phù hợp.

Ví dụ khai báo template lưu bytes:

~~~java
@Bean
ReactiveRedisTemplate<String, byte[]> payloadRedisTemplate(
        ReactiveRedisConnectionFactory connectionFactory) {
    RedisSerializationContext<String, byte[]> context =
        RedisSerializationContext.<String, byte[]>newSerializationContext(
                RedisSerializer.string())
            .value(RedisSerializer.byteArray())
            .hashKey(RedisSerializer.string())
            .hashValue(RedisSerializer.byteArray())
            .build();
    return new ReactiveRedisTemplate<>(connectionFactory, context);
}
~~~

Định dạng bytes là hợp đồng giữa các node. Nếu node A serialize theo Java serialization còn node B đọc như JSON, dữ liệu không thể khôi phục đúng. Khi đổi serializer, cần chiến lược tương thích và kiểm thử dữ liệu cũ.

Với repository do Spring Session cấu hình, hãy dùng điểm mở rộng serializer được phiên bản đó hỗ trợ. Không giả định cấu hình ReactiveRedisTemplate tùy chỉnh ở trên tự động thay serializer nội bộ của ReactiveRedisSessionRepository.

## 8. Vì sao không được block trong reactive request?

WebFlux thường dùng số lượng thread event-loop nhỏ để xử lý nhiều kết nối. Một thao tác blocking có thể giữ thread đó trong khi chờ I/O, khiến các request khác phải chờ.

Tránh các mẫu sau trong handler reactive:

~~~java
// Không nên: chặn thread để chờ Redis.
String value = reactiveRedisTemplate.opsForValue()
    .get("some-key")
    .block();

// Không nên: tự subscribe và tách công việc khỏi response lifecycle.
reactiveRedisTemplate.opsForValue()
    .set("some-key", "value")
    .subscribe();
~~~

Thay vào đó, compose publisher:

~~~java
return reactiveRedisTemplate.opsForValue()
    .get("some-key")
    .map(value -> ResponseEntity.ok(value))
    .defaultIfEmpty(ResponseEntity.notFound().build());
~~~

Nếu phải gọi thư viện blocking không thể thay thế, có thể cô lập trên scheduler dành cho blocking I/O bằng subscribeOn(Schedulers.boundedElastic()), nhưng chỉ nên dùng như giải pháp tích hợp có chủ đích. Không chuyển toàn bộ reactive Redis sang blocking chỉ vì một thành phần cũ.

## 9. TTL và vòng đời session trong Redis

Session thường có thời gian không hoạt động tối đa (maxInactiveInterval). Repository Redis cần lưu dữ liệu với expiration tương ứng để dữ liệu hết hạn được loại bỏ. Khi session được truy cập và timeout được gia hạn, repository cập nhật expiration theo chính sách của nó.

Các khái niệm cần phân biệt:

- **Idle timeout:** thời gian tối đa session không được truy cập.
- **Redis TTL:** thời gian còn lại trước khi key lưu trữ hết hạn.
- **Absolute lifetime:** giới hạn tổng thời gian tồn tại nếu ứng dụng có chính sách riêng.
- **Session invalidation:** thao tác chủ động thu hồi phiên trước TTL.

Không giả định Redis TTL luôn bằng đúng thời gian còn lại trên đồng hồ client. Repository có thể dùng expiration key hoặc cấu trúc hỗ trợ để xử lý sự kiện hết hạn. Tên key và chi tiết triển khai là nội bộ; không tự đặt TTL thủ công trên các key Spring Session đang quản lý.

Nếu cần giới hạn tuổi đời tuyệt đối, phải bổ sung chính sách ở tầng session/application và kiểm thử cùng idle timeout. Không dùng việc gia hạn TTL theo request để vô tình cho phép session tồn tại vô hạn nếu yêu cầu bảo mật quy định thời hạn tuyệt đối.

## 10. Keyspace notifications và sự kiện hết hạn

Redis keyspace notifications có thể giúp Spring Session nhận biết sự kiện khóa hết hạn hoặc bị xóa, tùy repository và phiên bản. Với Redis tự quản lý, tham số notify-keyspace-events phải được cấu hình theo yêu cầu thư viện; với Redis được quản lý, tham số có thể phải bật trong parameter group hoặc console nhà cung cấp.

Không nhầm việc TTL hoạt động với việc subscriber nhận được sự kiện. Redis vẫn có thể loại khóa hết hạn trong khi ứng dụng không nhận được notification do cấu hình, ACL hoặc mất kết nối Pub/Sub. Các listener của ứng dụng không nên dùng Pub/Sub expiration làm nguồn duy nhất cho nghiệp vụ cần bảo đảm bền vững.

Với reactive repository, cần kiểm tra tài liệu đúng phiên bản để biết event nào được hỗ trợ và cách cấu hình notification. Không suy ra toàn bộ tính năng của RedisIndexedSessionRepository Servlet đều có trong ReactiveRedisSessionRepository.

## 11. Cookie, header và định danh WebSession

Repository lưu dữ liệu session; resolver quản lý cách client gửi session ID. Trong WebFlux, cơ chế định danh được thực hiện qua WebSessionIdResolver, không phải HttpSessionIdResolver của Servlet.

Thông thường, ứng dụng browser dùng cookie để gửi ID. Có thể cấu hình resolver để đổi tên cookie, path, domain, Secure, HttpOnly và SameSite theo yêu cầu bảo mật. Với API client, có thể dùng header resolver nếu ứng dụng hỗ trợ và có chính sách bảo vệ ID rõ ràng.

Các nguyên tắc:

- Chỉ truyền session ID qua HTTPS trong production.
- Bảo vệ cookie bằng Secure, HttpOnly và SameSite phù hợp nếu dùng cookie.
- Không ghi session ID vào URL hoặc log.
- Đồng bộ resolver configuration trên mọi instance.
- Khi ID được đổi hoặc session bị invalidate, client phải nhận và áp dụng ID mới hoặc chỉ dẫn hết hạn.

Không dùng đồng thời cookie và header làm hai nguồn session ID độc lập nếu chưa định nghĩa thứ tự ưu tiên và hành vi thu hồi.

## 12. Redis reactive và khả năng mở rộng nhiều instance

Mọi instance WebFlux trong cùng cụm cần dùng chung Redis endpoint/cluster, namespace, serializer và chính sách timeout. Khi request được chuyển từ node A sang node B, node B phải tìm thấy và deserialize được session mà A đã ghi.

Các điểm cần đồng bộ:

- Phiên bản Spring Session và Spring Data Redis tương thích.
- ReactiveRedisConnectionFactory trỏ đến cùng logical store.
- Redis namespace không xung đột với ứng dụng khác.
- Serializer và type mapping giống nhau.
- Chính sách TTL và idle timeout giống nhau.
- Cấu hình resolver cookie/header thống nhất.
- ACL cho phép các lệnh Redis và kênh Pub/Sub mà repository cần.

Sticky session ở load balancer không thay thế kho dùng chung. Nó có thể giảm số lần request đổi node, nhưng node vẫn có thể restart, failover hoặc nhận traffic khác; trạng thái session cần tồn tại ngoài heap của một instance.

## 13. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ứng dụng WebFlux không thấy session đã tạo | Dùng cấu hình Servlet hoặc repository không reactive | Dùng @EnableRedisWebSession và reactive connection factory |
| Request treo hoặc throughput giảm | Gọi block() hoặc blocking Redis API trên event loop | Compose Mono/Flux, bỏ blocking call |
| Session được tạo nhưng request sau mất trạng thái | Cookie/header không được gửi, resolver khác nhau hoặc node dùng Redis khác | Kiểm tra response ID, request ID và endpoint/namespace |
| Deserialize lỗi giữa các node | Serializer hoặc class version không đồng nhất | Đồng bộ serializer và triển khai migration tương thích |
| Redis connection lỗi khi startup | Sai endpoint, TLS, secret hoặc connection factory | Kiểm tra cấu hình và health indicator |
| TTL không đúng mong đợi | Timeout cấu hình khác nhau hoặc gia hạn không như dự kiến | Kiểm tra max inactive interval và TTL của repository |
| Không nhận expiration event | Keyspace notifications hoặc Pub/Sub ACL chưa đúng | Kiểm tra tham số Redis, channel và subscriber |
| Logout xong ID cũ còn dùng được | Chỉ xóa cookie ở client, chưa invalidate server-side | Gọi WebSession.invalidate() và kiểm tra repository |
| Tự lưu session bằng ReactiveRedisTemplate gây lỗi | Thiếu metadata, TTL, serialization hoặc xử lý đồng thời | Dùng repository Spring Session hoặc triển khai đủ hợp đồng repository |

## 14. Kiểm thử reactive session

Kiểm thử cần xác nhận cả API WebFlux và trạng thái trong Redis. Có thể dùng WebTestClient cho HTTP flow và Redis thật hoặc container cho persistence.

Ma trận kiểm thử:

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Tạo session | Gọi endpoint đặt thuộc tính | Response có session identifier theo resolver |
| Đọc session | Gửi lại cookie/header | Endpoint đọc được thuộc tính đã lưu |
| Chuyển instance | Gửi request tiếp theo đến node khác | Node thứ hai khôi phục cùng session |
| Cập nhật attribute | Đổi giá trị và request lại | Giá trị mới được lưu và đọc đúng |
| Xóa attribute | Gọi thao tác remove | Thuộc tính không còn |
| Logout | Gọi endpoint invalidate | Session không còn được khôi phục |
| Idle expiration | Tạo session TTL ngắn và chờ | Repository từ chối session sau timeout |
| Serializer compatibility | Ghi bằng phiên bản cũ, đọc bằng phiên bản mới | Payload được khôi phục hoặc lỗi được xử lý an toàn |
| Redis outage | Tạm ngắt Redis trong test | Lỗi truyền qua reactive chain, không treo event loop |
| Blocking detection | Kiểm tra thread/BlockHound nếu dự án dùng | Không có blocking call ngoài vùng cho phép |

Ví dụ kiểm thử endpoint bằng WebTestClient:

~~~java
webTestClient.post()
    .uri("/cart/session")
    .exchange()
    .expectStatus().isNoContent()
    .expectCookie().exists("SESSION");
~~~

Cookie name trong assertion phải khớp resolver configuration của ứng dụng. Với test đầy đủ, lưu cookie từ response đầu và gửi lại trong request kế tiếp; không chỉ kiểm tra cookie được phát.

### 14.1. Kiểm tra không blocking

Reactive test có thể kiểm tra publisher hoàn tất bằng StepVerifier. Với ứng dụng cần bảo đảm event-loop không bị chặn, có thể dùng BlockHound trong test để phát hiện các thao tác blocking không được cho phép. Không đưa block() vào code production chỉ vì test dùng block() để lấy kết quả; test và runtime có mục đích khác nhau.

## 15. Nguyên tắc triển khai

- Dùng ReactiveRedisSessionRepository thông qua tích hợp @EnableRedisWebSession cho WebFlux.
- Làm việc với WebSession, WebSessionManager và reactive repository; không dùng Servlet HttpSession filter cho WebFlux thuần.
- Cấu hình ReactiveRedisConnectionFactory và dependency Spring Data Redis tương thích.
- Compose Mono/Flux; không block() hoặc subscribe() thủ công trong controller.
- Để Spring Session quản lý serialization, session metadata và TTL; không thao tác key nội bộ trực tiếp.
- Đồng bộ namespace, serializer, timeout và resolver trên mọi node.
- Phân biệt idle timeout, Redis TTL, absolute lifetime và invalidate.
- Cấu hình notification/ACL nếu tính năng phiên bản đang dùng yêu cầu; không coi Pub/Sub là hàng đợi bền vững.
- Kiểm thử tạo, đọc, cập nhật, xóa, hết hạn và chuyển node bằng Redis thực.
- Theo dõi connection error, latency, deserialize failure và dấu hiệu blocking.

ReactiveRedisSessionRepository kết nối vòng đời WebSession với Redis bằng các thao tác reactive. Khi ứng dụng giữ toàn bộ request path ở dạng non-blocking, dùng đúng resolver và serializer, đồng thời chia sẻ cùng cấu hình Redis giữa các node, session có thể được khôi phục nhất quán dù request tiếp theo được xử lý bởi instance WebFlux khác.
