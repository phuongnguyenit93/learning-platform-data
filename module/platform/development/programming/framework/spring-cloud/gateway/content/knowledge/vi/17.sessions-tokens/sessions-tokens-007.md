# Spring Session và chia sẻ phiên khi chạy nhiều bản sao

## 1. Bài toán: người dùng chuyển từ Gateway A sang Gateway B

Một triển khai **Spring Cloud Gateway** có thể bắt đầu bằng một tiến trình xử lý mọi request. Khi lượng truy cập tăng, nhóm vận hành triển khai hai hoặc nhiều bản sao Gateway sau một load balancer:

~~~text
Browser ──> Load Balancer ──> Gateway A ──> microservices
                         └──> Gateway B ──> microservices
~~~

Nếu Gateway A lưu thông tin phiên đăng nhập trong **bộ nhớ riêng của tiến trình**, một request tiếp theo được load balancer đưa sang Gateway B có thể không tìm thấy phiên. Người dùng vừa đăng nhập ở A nhưng sang B lại bị coi như chưa đăng nhập. Một giải pháp là lưu dữ liệu phiên trong **kho chia sẻ** để A và B cùng đọc/ghi theo một session ID.

**Spring Session** tích hợp với Spring WebFlux thông qua `WebSession` và `WebSessionManager`, đồng thời có thể dùng Redis làm kho phiên chung. Bài này thuộc chương **Phiên đăng nhập và token** của module **SPRING_CLOUD_GATEWAY**. Nó kết nối vận hành nhiều bản sao Gateway với route predicate, filter chain, biến đổi đường dẫn/header, service discovery, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request.

Sau bài học, bạn sẽ:

1. Phân biệt **session cookie, session ID, dữ liệu session, access token** và sticky session.
2. Hiểu vì sao Spring Session + Redis cho phép nhiều Gateway replica chia sẻ trạng thái.
3. Phân biệt Spring WebFlux `WebSession` với Servlet `HttpSession`; tránh dùng annotation/module không phù hợp.
4. Cấu hình các bản Spring Boot / Spring Cloud Gateway khác nhau mà không trộn namespace.
5. Thực hành **hai Gateway process cùng một Redis**, kiểm tra cookie jar, counter xuyên replica, timeout và logout.
6. Biết dùng `SaveSession` khi cần lưu session trước khi Gateway forward request.
7. Đánh giá các rủi ro trong production: cookie, serialization, tính nhất quán, Redis outage, bảo mật và observability.

> **Phạm vi:** Bài tập trung vào **Spring Cloud Gateway Server WebFlux**. Các ví dụ phiên trong lab chỉ lưu bộ đếm để kiểm chứng chia sẻ trạng thái; **không phải hệ thống đăng nhập thực và không chứng minh người gọi đã được xác thực**.

## 2. Phân biệt session và token trước khi thiết kế

| Thành phần | Ví dụ | Ai giữ và kiểm tra? |
| --- | --- | --- |
| **Session ID** | Giá trị ngẫu nhiên dài do server tạo | Client gửi lại bằng cookie; Gateway tra khóa tương ứng |
| **Session cookie** | `Set-Cookie: SESSION=...; Path=/; HttpOnly; Secure` | Browser lưu theo host/path/scheme và gửi `Cookie: SESSION=...` |
| **Session data** | Thông tin xác thực đã kiểm chứng, CSRF state hoặc trạng thái nhỏ | Server/Gateway lưu trong Redis qua Spring Session |
| **Access token** | `Authorization: Bearer ...` | Resource Server xác minh token theo chuẩn phù hợp, có thể không dùng session |
| **Refresh token** | Credential để xin access token mới | Phải lưu và bảo vệ riêng, không đồng nhất với session ID |
| **Sticky session** | LB ưu tiên đưa cùng client vào cùng replica | Hành vi định tuyến của LB, không phải kho lưu session |

Một mô hình dùng **session cookie** có thể hoạt động như sau:

1. Người dùng đăng nhập; Spring Security xác minh thông tin đăng nhập.
2. Gateway tạo/đổi session ID an toàn và lưu authentication state liên quan trong `WebSession`.
3. Spring Session ghi dữ liệu phiên theo session ID vào Redis.
4. Browser chỉ giữ cookie chứa **mã phiên**, không giữ trực tiếp toàn bộ dữ liệu xác thực.
5. Request tiếp theo đến bất cứ Gateway replica nào cũng dùng cookie để lấy cùng session từ Redis.

Trong khi đó, với một API **thuần stateless Bearer JWT**, mỗi request mang JWT và Gateway xác thực chữ ký/claims; **không nhất thiết cần Spring Session**. Không nên thêm Redis session vào mọi API chỉ vì có nhiều replica.

### Token không tự biến thành session

JWT access token và session ID đều có thể được xem như credential mà người dùng cần bảo vệ, nhưng cơ chế khác nhau:

- **JWT đã ký** có thể được xác minh ngoại tuyến bằng public key, issuer, audience và thời hạn; việc thu hồi ngay thường cần thiết kế bổ sung.
- **Session ID** thường là tham chiếu đến dữ liệu trạng thái phía server; vô hiệu hóa bản ghi session có thể làm credential hết hiệu lực trên tất cả replica.
- **Spring Session** chia sẻ `WebSession` của ứng dụng, **không tự biến token JWT thành cookie session**, không tự xác thực người dùng và không cấp quyền nghiệp vụ.

## 3. Kiến trúc nhiều Gateway dùng Redis

~~~mermaid
flowchart TD
    C["Browser<br/>Cookie: SESSION=opaque-id"] --> L["Load Balancer / Ingress<br/>HTTPS public"]
    L --> A["Gateway replica A<br/>WebFlux + Spring Session"]
    L --> B["Gateway replica B<br/>WebFlux + Spring Session"]
    A <-->|"ReactiveSessionRepository"| R[("Redis<br/>shared session store")]
    B <-->|"ReactiveSessionRepository"| R
    A --> S["Microservices"]
    B --> S
~~~

**Điều kiện để một session hoạt động ở cả A và B:**

- Hai replica sử dụng **cùng Redis service/cluster và cùng session namespace**.
- Hai replica có **phiên bản Spring Session và cách serialize session attributes tương thích**.
- Client gửi **cùng session cookie** cho URL công khai, không vô tình đổi cookie name/Path/Domain.
- Session chưa hết hạn hoặc bị invalidate; kết nối tới Redis và các chính sách security còn hợp lệ.
- Hai replica có cấu hình xác thực, session timeout, mã hóa và deployment policy tương thích.

**Không cần sticky session để chia sẻ trạng thái nếu tất cả replica đọc cùng một kho phiên**, dù sticky session đôi khi được dùng để tối ưu hoặc do yêu cầu khác của hạ tầng. Sticky session **một mình** không giải quyết triệt để restart, autoscaling hoặc mất replica: nếu chỉ lưu session trong RAM của A, A chết thì session vẫn mất.

### 3.1. Vòng đời HTTP của một phiên

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant L as Load Balancer
    participant A as Gateway A
    participant R as Redis
    participant B as Gateway B

    C->>L: POST /lab/session/increment
    L->>A: Request không có cookie
    A->>R: Tạo session + counter=1
    R-->>A: Lưu thành công
    A-->>C: 200 + Set-Cookie: SESSION=...
    C->>L: POST /lab/session/increment<br/>Cookie: SESSION=...
    L->>B: Chuyển sang replica B
    B->>R: Tải session theo ID
    R-->>B: counter=1
    B->>R: Ghi counter=2
    B-->>C: 200 + counter=2
~~~

Điểm then chốt: **Redis lưu session attributes, không phải cookie browser**. Cookie mang ID để định vị bản ghi; mỗi Gateway truy xuất Redis qua Spring Session khi xử lý request.

## 4. Spring Session thay thế WebSession như thế nào?

Trong **Spring WebFlux**, phần API tiêu chuẩn là `WebSession`. Ứng dụng lấy session qua `ServerWebExchange.getSession()` hoặc nhận tham số `WebSession` trong controller. Spring Session tích hợp một `WebSessionManager` được hậu thuẫn bởi `ReactiveSessionRepository`; với Redis có triển khai reactive phù hợp.

| Spring WebFlux / Gateway | Servlet Spring MVC | Lưu ý |
| --- | --- | --- |
| `WebSession` | `HttpSession` | Hai mô hình ứng dụng khác nhau |
| `WebSessionManager` | `SessionRepositoryFilter`/Servlet session | Cơ chế tích hợp khác nhau |
| `ReactiveSessionRepository` | `SessionRepository` | Reactive API trả `Mono`/publisher |
| `@EnableRedisWebSession` | `@EnableRedisHttpSession` | Chỉ dùng bản reactive cho Gateway WebFlux nếu chọn cấu hình thủ công |
| `CookieWebSessionIdResolver` | `DefaultCookieSerializer`/Servlet cookie integration | Cấu hình cookie cũng khác |

Các dòng Spring Boot hiện đại có **Spring Session auto-configuration** khi dependency và Redis connection factory phù hợp đã có trên classpath. Trong cấu hình tự động bình thường, **không bắt buộc thêm `@EnableRedisWebSession`**. Nếu tự khai báo annotation để kiểm soát repository, Boot có thể lùi auto-config; khi đó phải chủ động quản lý cấu hình tương ứng.

**Không chặn luồng reactive:** không gọi `block()` để đọc Redis session trong Netty event loop, cũng không dùng `HttpSession` của Servlet như giải pháp cho Gateway WebFlux. Dùng các API reactive của Spring Session/WebFlux.

### 4.1. Redis là nơi lưu state, không phải kho lưu JWT mặc định

Spring Session thường lưu các attributes đã được serialize theo session ID. Không nên nhét đối tượng request/response, stream, connection, secret hoặc dữ liệu lớn vào session. Các object cần có định dạng lưu phù hợp và ổn định khi ứng dụng được rolling upgrade.

Đọc/ghi session qua Redis còn phát sinh **network I/O, latency, lỗi kết nối và chi phí bộ nhớ**. Một kiến trúc stateless JWT có thể không gặp chi phí này, nhưng lại có bài toán revoke/rotation khác. Hãy chọn mô hình theo yêu cầu nghiệp vụ, không theo trào lưu.

## 5. Chọn phiên bản, dependency và cấu hình đúng

### 5.1. Spring Cloud Gateway Server WebFlux 4.2/4.3 với Spring Boot 3.x

Khi dùng Spring Boot 3.5 và Gateway WebFlux 4.3 tương thích qua Spring Cloud BOM, các dependency Maven điển hình:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
    </dependency>
</dependencies>
~~~

Khai báo Spring Cloud BOM tương thích với Spring Boot đang chọn; không ghép bất kỳ phiên bản Gateway và Boot theo cảm tính. Starter Gateway mới có thể có tên riêng `spring-cloud-starter-gateway-server-webflux`; cần kiểm tra release đang dùng.

Với Boot 3.x, namespace cấu hình phiên Redis phổ biến là `spring.session.redis.namespace`:

~~~yaml
server:
  port: ${GATEWAY_PORT:8081}

spring:
  application:
    name: shared-session-gateway
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
  session:
    timeout: 20m
    redis:
      namespace: spring:session:gateway-lab

demo:
  replica-id: ${REPLICA_ID:A}
~~~

Trong bài lab, Gateway A và B dùng **cùng application.yml** nhưng truyền `GATEWAY_PORT`/`REPLICA_ID` khác nhau. Chúng phải cùng giá trị Redis host/port và namespace.

### 5.2. Spring Cloud Gateway Server WebFlux 5.x với Spring Boot 4.x

Spring Boot 4.x cung cấp starter riêng cho Spring Session Redis và đổi một số namespace cấu hình. Dependency mẫu cho Boot 4.x + Gateway WebFlux 5.x:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-session-data-redis</artifactId>
    </dependency>
</dependencies>
~~~

Spring Boot có thể auto-configure reactive Redis session với starter phù hợp, không nhất thiết phải thêm `@EnableRedisWebSession`. Ví dụ namespace Redis session trong Boot 4.x là **`spring.session.data.redis.namespace`**:

~~~yaml
server:
  port: ${GATEWAY_PORT:8081}

spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
  session:
    timeout: 20m
    data:
      redis:
        namespace: spring:session:gateway-lab

demo:
  replica-id: ${REPLICA_ID:A}
~~~

**Đừng trộn** `spring.session.redis.namespace` (Boot 3.x) với `spring.session.data.redis.namespace` (Boot 4.x) rồi giả định cả hai được đọc. Cả hai ví dụ đều là **một lựa chọn phiên bản riêng**, không phải hai đoạn YAML phải đặt vào cùng ứng dụng.

| Thành phần | Boot 3.5 + Gateway WebFlux 4.3 | Boot 4.x + Gateway WebFlux 5.x |
| --- | --- | --- |
| Gateway starter thường gặp | `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-server-webflux` |
| Namespace route | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Redis session dependency mẫu | `spring-session-data-redis` + reactive Redis starter | `spring-boot-starter-session-data-redis` |
| Session timeout | `spring.session.timeout` | `spring.session.timeout` |
| Redis session namespace | `spring.session.redis.namespace` | `spring.session.data.redis.namespace` |
| Redis host | `spring.data.redis.host` | `spring.data.redis.host` |

Những lựa chọn này dựa trên tài liệu cho **dòng tương ứng**, không thay thế việc kiểm tra compatibility matrix và configuration metadata của bản patch đang chạy.

### 5.3. Tự cấu hình bằng annotation khi cần

Nếu vì lý do cụ thể không muốn dùng Spring Boot auto-config, có thể chọn:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration(proxyBeanMethods = false)
@EnableRedisWebSession(
        redisNamespace = "spring:session:gateway-lab",
        maxInactiveIntervalInSeconds = 1200)
class RedisWebSessionConfiguration {
}
~~~

Đoạn này giả định đã có **một ReactiveRedisConnectionFactory** do Boot tạo từ `spring.data.redis.*` hoặc được định nghĩa rõ ràng. Khi dùng annotation, cấu hình session repository có thể ưu tiên các thuộc tính annotation thay cho property auto-config; **không ghép cả hai cách rồi mong mọi property vẫn có hiệu lực như cũ**.

Trong bài lab dưới đây, **ưu tiên auto-config của Boot**, không cần class annotation trên.

## 6. Lab chạy hai Gateway replica dùng một Redis

Lab này **không cần Authorization Server hay backend microservice** để chứng minh chia sẻ session. Ta tạo API chẩn đoán trên chính Gateway để ghi và đọc một bộ đếm trong `WebSession`. Khi hoạt động, response cho biết replica nào đã xử lý request.

### 6.1. Điều kiện đầu vào

- Một dự án Gateway Server WebFlux với dependencies và `application.yml` của **một** dòng phiên bản trong mục 5.
- Redis hoạt động tại `localhost:6379` cho cả hai Gateway process.
- Java, Maven/Maven Wrapper và Spring Cloud BOM tương thích.
- Hai cổng trống `8081` và `8082` trên máy thử nghiệm.

Nếu dùng Docker cho Redis local:

~~~bash
# Redis lab, không mở ra Internet:
docker run --rm --name redis-session-lab \
  -p 127.0.0.1:6379:6379 redis:7
~~~

Nếu Docker hoặc image không có sẵn, dùng Redis được cài đặt sẵn hoặc Redis test được quản lý. **Không dùng một Redis production công khai, không tắt bảo vệ xác thực/network chỉ để chạy lab**. Khi hai Gateway nằm trong container riêng, `localhost` trong mỗi container là container đó; phải thay Redis host bằng DNS service/container phù hợp.

### 6.2. Tạo ứng dụng Gateway

`src/main/java/demo/gateway/SessionGatewayApplication.java`:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionGatewayApplication.class, args);
    }
}
~~~

### 6.3. Controller sử dụng WebSession

`src/main/java/demo/gateway/SessionLabController.java`:

~~~java
package demo.gateway;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
public class SessionLabController {

    private final String replicaId;

    public SessionLabController(
            @Value("${demo.replica-id:A}") String replicaId) {
        this.replicaId = replicaId;
    }

    @PostMapping("/lab/session/increment")
    public Mono<Map<String, Object>> increment(WebSession session) {
        session.start();
        int previous = session.getAttributeOrDefault("counter", 0);
        int current = previous + 1;
        session.getAttributes().put("counter", current);

        // Không gửi session.getId() ra ngoài: đó là credential.
        return Mono.just(Map.of(
                "replica", replicaId,
                "counter", current));
    }

    @GetMapping("/lab/session")
    public Mono<Map<String, Object>> read(WebSession session) {
        int count = session.getAttributeOrDefault("counter", 0);
        return Mono.just(Map.of(
                "replica", replicaId,
                "counter", count));
    }

    @PostMapping("/lab/session/logout")
    public Mono<Void> logout(WebSession session) {
        return session.invalidate();
    }
}
~~~

Ở endpoint `increment`, việc cập nhật attribute khiến WebSession trở thành trạng thái cần lưu; Spring Session persisting trong vòng đời request. Endpoint `read` chỉ đọc trạng thái; nếu chưa từng tạo session, nó thấy `counter=0`.

**Lưu ý quan trọng:** Tăng counter theo cách **đọc → tăng → ghi** trong session là đủ cho bài lab tuần tự, **không phải phép cập nhật nguyên tử** khi hai request đồng thời ở hai replica. Production cần thiết kế tránh *lost update* nếu cùng một session bị chỉnh sửa song song.

### 6.4. Chạy Gateway A và Gateway B

Hai terminal Bash, ở **cùng dự án**:

~~~bash
# Terminal A
GATEWAY_PORT=8081 REPLICA_ID=A ./mvnw spring-boot:run

# Terminal B
GATEWAY_PORT=8082 REPLICA_ID=B ./mvnw spring-boot:run
~~~

Hoặc trong hai cửa sổ PowerShell:

~~~powershell
# Cửa sổ A
$env:GATEWAY_PORT = "8081"
$env:REPLICA_ID = "A"
.\mvnw.cmd spring-boot:run

# Cửa sổ B
$env:GATEWAY_PORT = "8082"
$env:REPLICA_ID = "B"
.\mvnw.cmd spring-boot:run
~~~

Cả hai process phải kết nối **cùng Redis** và chạy **cùng session namespace**. Hai port trong lab thay cho việc dựng LoadBalancer đứng trước Gateway. Điều này giúp chủ động ép request vào A hoặc B mà không cần cấu hình sticky routing.

### 6.5. Tạo session trên replica A

~~~bash
curl -i -X POST "http://localhost:8081/lab/session/increment" \
  -c session-jar.txt
~~~

Response **kỳ vọng**:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<opaque-random-value>; Path=/; HttpOnly; SameSite=Lax
Content-Type: application/json

{"replica":"A","counter":1}
~~~

Thuộc tính `Set-Cookie` thực tế còn tùy WebFlux/Spring Session/version và cấu hình cookie; không nên so sánh nguyên văn thứ tự attributes. Quan trọng là `curl -c session-jar.txt` đã lưu được session ID và JSON có `counter=1`.

### 6.6. Đọc và tăng trên replica B với cùng cookie

~~~bash
# B phải nhìn thấy trạng thái A đã lưu:
curl -i "http://localhost:8082/lab/session" \
  -b session-jar.txt

# B tăng từ 1 lên 2:
curl -i -X POST "http://localhost:8082/lab/session/increment" \
  -b session-jar.txt -c session-jar.txt

# A đọc lại:
curl -i "http://localhost:8081/lab/session" \
  -b session-jar.txt
~~~

| Lượt gọi | Replica | Giá trị kỳ vọng |
| --- | --- | --- |
| POST increment không cookie | A (8081) | `counter=1`, response có Set-Cookie |
| GET với cookie vừa lưu | B (8082) | `counter=1` |
| POST increment với cookie | B (8082) | `counter=2` |
| GET với cookie | A (8081) | `counter=2` |
| GET **không cookie** | A hoặc B | `counter=0`, không phải phiên cũ |

**Vì sao cookie jar dùng được trên cả port?** Cookie không bị phân vùng theo port; `localhost:8081` và `localhost:8082` dùng cùng hostname `localhost` và path `/`. Trong production, browser thường chỉ thấy một host công khai của load balancer, còn nhiều replica nằm phía sau.

Chỉ kiểm thử theo **thứ tự tuần tự** của bảng trước, đừng gửi cùng lúc nhiều lệnh update để tránh chồng lấn dữ liệu khi đang xác nhận lưu session.

### 6.7. Invalidate ở B rồi thử lại A

~~~bash
curl -i -X POST "http://localhost:8082/lab/session/logout" \
  -b session-jar.txt -c session-jar.txt

curl -i "http://localhost:8081/lab/session" \
  -b session-jar.txt
~~~

Sau `session.invalidate()`, bản ghi phiên cũ bị vô hiệu hóa theo cơ chế repository; request tiếp theo với ID cũ không nên lấy lại `counter=2`, mà thường thấy `counter=0`. Tùy resolver/version, cookie cũ có thể bị xóa trên response hoặc cookie jar được cập nhật. Thử trên chính môi trường chạy, đừng chỉ suy ra từ status của logout.

Trong đăng nhập thực, **logout** còn có thể cần revoke token/refresh token, xóa cookie đúng Path/Domain, thu hồi server session và dọn trạng thái ứng dụng liên quan. Ví dụ lab chỉ vô hiệu hóa WebSession.

## 7. Cookie session: phần browser giữ phải nhất quán

Browser chọn cookie dựa trên **URL công khai** chứ không nhìn thấy địa chỉ backend hoặc Redis. Nếu load balancer expose `https://api.example.test`, các Gateway replica phải thống nhất tên cookie, `Path`, `Domain`, `SameSite` và `Secure`.

| Thuộc tính | Khuyến nghị và ý nghĩa |
| --- | --- |
| **Cookie name** | Thường `SESSION`; cùng tên giữa các replica để đọc đúng ID |
| **Host / Domain** | Ưu tiên cookie host-only; tránh domain quá rộng |
| **Path** | Phù hợp đường dẫn công khai browser gọi, ví dụ `/` hoặc `/api` nếu yêu cầu |
| **Secure** | Dùng trên HTTPS public; không dựa vào HTTP nội bộ để quyết định browser có HTTPS hay không |
| **HttpOnly** | Hạn chế JavaScript đọc session ID, nhưng không tự ngăn CSRF |
| **SameSite** | Thường dùng Lax/Strict tùy flow; None yêu cầu Secure và vẫn chịu chính sách third-party cookie |
| **Max-Age/Expires** | Điều khiển vòng đời cookie client, không đồng nhất với thời hạn bản ghi session ở Redis |

### 7.1. Tùy chỉnh cookie trong WebFlux

Spring Session WebFlux dùng `WebSessionIdResolver`, mặc định thường là `CookieWebSessionIdResolver`. Có thể khai báo bean **khi cần cho HTTPS production**:

~~~java
package demo.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
public class WebSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("__Host-SESSION");
        resolver.addCookieInitializer(builder ->
                builder.path("/")
                        .secure(true)
                        .httpOnly(true)
                        .sameSite("Lax"));
        return resolver;
    }
}
~~~

Prefix `__Host-` yêu cầu cookie được đặt qua HTTPS, có `Secure`, `Path=/` và **không có Domain**. Cấu hình này **không dùng nguyên trạng với HTTP localhost lab** nếu trình duyệt/cookie jar không đáp ứng điều kiện Secure/HTTPS; hãy thử ở môi trường có HTTPS hoặc bỏ bean này khỏi lab.

Với **Servlet Spring Session**, có thể dùng `DefaultCookieSerializer` nhưng **không lấy nguyên mã Servlet áp vào Gateway WebFlux**. Nếu Gateway có nhiều ứng dụng dùng chung host, cần đánh giá xung đột cookie name và path.

### 7.2. Cookie không chia sẻ qua mọi domain

Cookie cho `api.example.test` không tự động gửi tới `service.internal` hoặc `auth.other-example.test`. Nếu Gateway đang giữ session trong Redis, backend microservice **không tự biết phiên đó** chỉ vì Gateway đã forward HTTP request tới nó. Có thể có kiến trúc backend cũng dùng chung kho session, nhưng phải thiết kế rõ cookie/namespace/serializer/security boundary và không tự coi dữ liệu session của một ứng dụng là quyền truy cập ở ứng dụng khác.

Tương tự, nếu Gateway bỏ `/api` bằng `StripPrefix`, đường dẫn backend nhận khác đường dẫn browser gọi. Cookie Path do **browser đánh giá theo URL công khai**, không theo path sau rewrite.

## 8. SaveSession GatewayFilter Factory: khi nào dùng?

Spring Cloud Gateway Server WebFlux có **`SaveSession` GatewayFilter Factory**. Tài liệu Spring mô tả nó ép thực hiện **`WebSession.save()` trước khi forward request xuống downstream**, hữu ích khi dùng Spring Session với cơ chế lưu lazy và cần bảo đảm trạng thái vừa thay đổi đã được ghi trước khi downstream được gọi.

### 8.1. Cấu hình cho Gateway WebFlux 4.2/4.3

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: session-aware-api
          uri: http://localhost:9091
          predicates:
            - Path=/api/**
          filters:
            - StripPrefix=1
            - SaveSession
~~~

### 8.2. Cấu hình cho Gateway WebFlux 5.x

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: session-aware-api
              uri: http://localhost:9091
              predicates:
                - Path=/api/**
              filters:
                - StripPrefix=1
                - SaveSession
~~~

Đây là ví dụ **route proxy riêng**, backend `localhost:9091` cần chạy nếu muốn gọi route. Lab counter ở mục 6 dùng controller nội bộ, **không cần SaveSession** để chứng minh chia sẻ phiên: Spring Session đã lưu phiên qua vòng đời request WebFlux.

**SaveSession không phải**:

- Cơ chế xác thực hay tạo session tự động cho mọi request.
- Công cụ mã hóa session, refresh token hoặc cấp access token.
- Lệnh chia sẻ Redis giữa các Gateway: chuyện đó do **Spring Session repository + cấu hình chung** thực hiện.
- Cách chuyển toàn bộ authentication state cho backend: `WebSession.save()` chỉ đảm bảo dữ liệu đã được lưu; downstream phải có cơ chế riêng để sử dụng dữ liệu hoặc nhận danh tính đã được xác minh qua kênh tin cậy.

Khi phối hợp Spring Security và Spring Session, thứ tự lưu state có thể quan trọng, đặc biệt khi downstream cũng phải truy xuất state đã lưu. Hãy kiểm chứng filter chain của phiên bản đang dùng, tránh hiểu `SaveSession` là giải pháp phổ quát cho mọi race condition.

## 9. Session timeout, Redis TTL và invalidation

### 9.1. Thời gian bất hoạt khác thời hạn cookie

`spring.session.timeout: 20m` trong ví dụ là thời gian phiên **không hoạt động** trước khi hết hiệu lực theo policy Spring Session. Nó không nhất thiết tạo cookie có `Max-Age=1200`; nhiều session cookie bị browser xóa khi đóng browser, trong khi dữ liệu Redis có TTL riêng.

Ví dụ:

~~~text
10:00  Tạo session, timeout 20 phút
10:05  Request hợp lệ có thể cập nhật lastAccessedTime
10:25  Session có thể hết hạn nếu không còn hoạt động đủ 20 phút
~~~

Thời điểm Redis xóa key thực tế còn phụ thuộc cơ chế TTL/expiration của Spring Session, độ trễ và cache. Đừng xây chính sách bảo mật dựa trên việc key phải biến mất **đúng một mili giây** sau thời hạn.

### 9.2. Logout ở một replica tác động tới replica khác

Nếu A và B cùng đọc cùng session key, logout/invalidate ở A sẽ làm B không thể tiếp tục dùng phiên cũ sau khi trạng thái được cập nhật; request kế tiếp tới B phải được đánh giá lại. Với người dùng thực, cần kiểm tra thêm session fixation protection, CSRF state, token revocation và chính sách “đăng xuất khỏi tất cả thiết bị”.

### 9.3. Xem dữ liệu Redis trong lab

Trong Redis local test, có thể dùng `SCAN` để xem namespace, tránh `KEYS *` trên hệ thống đông dữ liệu:

~~~bash
redis-cli --scan --pattern 'spring:session:gateway-lab:*'
~~~

Chỉ dùng để xác minh **có key trong namespace**, không in/đưa raw serialized session attributes hoặc session ID thật lên logs/screenshot. Redis key names có thể chứa session ID; khi ghi báo cáo nên ẩn giá trị. Trong production, cần policy truy cập và công cụ quan sát phù hợp thay vì quét key tùy tiện.

## 10. Những điểm hay gây lỗi khi chạy nhiều replica

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
| --- | --- | --- |
| A tăng counter, B lại thấy 0 | Khác Redis endpoint/namespace, cookie không được gửi, serialization không tương thích | So Redis config, cookie jar, namespace và response headers |
| Reload trang tạo session mới | Cookie Path/Domain/SameSite/Secure không khớp URL công khai | DevTools Storage/Network hoặc `curl -b/-c` |
| Đổi cổng trong lab nhưng mất cookie | Cookie jar không được tái sử dụng hoặc hostname đổi giữa `localhost` và `127.0.0.1` | Giữ cùng host và dùng lại jar |
| Logout ở A nhưng B vẫn thấy phiên | Hai replica không dùng cùng repository, session invalidate không hoàn tất, state cache khác | Xác minh Redis/trace và request kế tiếp |
| Đã thêm Spring Session nhưng vẫn dùng RAM | Dependency/auto-config reactive không kích hoạt, vô tình dùng Servlet config | Kiểm tra `WebSessionManager` và `ReactiveSessionRepository` thực tế |
| Session hết hạn sớm hoặc quá lâu | Timeout khác nhau, clock/TTL, cookie và server inactivity policy khác | So property theo phiên bản, last access và Redis expiry |
| Đổi release làm lỗi deserialize | Class/serialVersion/JSON serializer không tương thích | Rolling-upgrade test với session cũ; schema migration |
| Đột nhiên 5xx khi Redis lỗi | Redis trở thành phụ thuộc trên request path | Kiểm tra latency, timeout, failover, backpressure và alert |
| Counter ít hơn số POST đồng thời | Lost update do concurrent session modifications | Test request đồng thời; thiết kế atomic update hoặc lưu state nghiệp vụ riêng |
| Backend không nhận cookie/session | Cookie scope không khớp hoặc backend không dùng cùng session infrastructure | Phân biệt phiên ở Gateway với phiên ở backend |
| CORS báo lỗi khi dùng cookie | Cross-origin credentials/SameSite/CORS response sai | Kiểm tra preflight, allow-credentials, allow-origin cụ thể và cookie attributes |

### 10.1. Tất cả replica phải đọc chung Redis, nhưng namespace phải có chủ đích

Ví dụ nếu A dùng `spring:session:gateway-lab` và B dùng `spring:session:gateway-test`, dù cùng Redis server, chúng **không chia sẻ session**. Ngược lại, hai ứng dụng hoàn toàn khác nghiệp vụ dùng chung namespace có thể gây rủi ro đụng tên cookie và đọc attributes không tương thích. Với cùng cụm Gateway, cố ý dùng chung namespace; với ứng dụng khác, ưu tiên tách riêng.

### 10.2. Sticky session không giải quyết dữ liệu đứt gãy

Nếu LB luôn đưa một client đến A, vấn đề mất trạng thái ở B có thể bị che khuất. Hãy **kiểm thử trực tiếp A → B → A** như mục 6, hoặc tắt affinity trong môi trường thử nghiệm, để xác nhận thật sự có kho phiên chia sẻ.

### 10.3. Spring Session không phải database nghiệp vụ

Không lưu giỏ hàng lớn, lịch sử thao tác, thông tin thanh toán hoặc bộ đếm cần atomic update làm dữ liệu nghiệp vụ chính trong session. Redis session phù hợp để giữ **trạng thái phiên nhỏ và ngắn hạn**; nghiệp vụ cần nguồn dữ liệu đáng tin cậy, khóa/idempotency và consistency riêng.

## 11. Redis production: độ bền, bảo mật và phiên bản serializer

Một kho phiên Redis trung tâm giúp scale Gateway, nhưng cũng là **phụ thuộc dùng chung trên request path**. Nếu Redis lỗi hoặc chậm, mọi replica đều có thể gặp lỗi truy xuất session. Cần:

1. **Redis availability:** triển khai phù hợp (managed Redis, Sentinel/Cluster nếu yêu cầu), quan sát replication/failover, latency và tỷ lệ lỗi.
2. **Giới hạn truy cập:** private network, ACL/authentication, TLS khi cần; không mở Redis ra Internet. Secrets phải lấy từ secret manager/env, không commit YAML thật.
3. **Timeout và backpressure:** đặt network timeout/pool phù hợp, không để request chờ vô hạn. Tránh retry vô hạn vào Redis khi Redis đang lỗi.
4. **Dữ liệu nhạy cảm:** cân nhắc mức độ bảo mật khi lưu authentication state; tránh ghi session attributes/IDs ở log và trace, có chính sách xóa dữ liệu.
5. **Serialization:** mặc định Spring Session Redis có thể dùng Java serialization tùy cấu hình/dòng; cần xem compatibility và mức tin cậy của dữ liệu, hoặc chọn JSON serializer an toàn với allowlist rõ ràng. Các replica rolling upgrade phải đọc được cùng định dạng, hoặc có kế hoạch migration/expire session cũ.
6. **TTL/eviction:** giới hạn số session, memory policy và khả năng chịu tải; tránh eviction không mong muốn làm người dùng bị logout hàng loạt.
7. **Metrics:** quan sát latency Redis, session create/read/save/delete, memory, keyspace, session churn, login failures và error rates nhưng **không gắn session ID vào metric labels**.

### 11.1. Serializer tùy biến cần thận trọng

Spring Session cho phép thay serializer bằng bean có tên **`springSessionDefaultRedisSerializer`**. Đây là cơ chế cấu hình hữu ích khi phải chia sẻ session giữa nhiều bản release; tuy nhiên, không nên đưa một Jackson serializer với **default typing mở rộng cho object không tin cậy** vào production mà chưa đánh giá rủi ro deserialize và khả năng tương thích.

Nếu session chứa `SecurityContext` hoặc đối tượng Spring Security, serializer phải hiểu đúng kiểu dữ liệu/mixin cho phiên bản Spring Security đang dùng. Các cấu hình này cần được **build/test qua rolling upgrade**, không nên tự suy đoán lớp Java cũ sẽ deserialize đúng khi cập nhật framework.

### 11.2. Concurrent requests không tự có transaction toàn cục

Hai request đồng thời cùng đọc một counter rồi đều tăng từ 7 lên 8 có thể dẫn tới **lost update**, dù Redis luôn khả dụng. Spring Session chia sẻ *storage* chứ không tự khóa mọi session xuyên các Gateway replica. Với thao tác cần tính nhất quán, dùng cơ chế atomic update/transaction/đặt trạng thái nghiệp vụ ở nơi phù hợp thay vì sửa attribute session cạnh tranh.

## 12. Spring Security, CSRF, fixation và session concurrency

### 12.1. Tạo phiên không đồng nghĩa đã xác thực

Controller lab chỉ tạo một counter. Trong login thật, Spring Security phải xác thực credential, quản lý `SecurityContext`, áp chính sách authorization và tránh **session fixation** (ví dụ đổi session ID khi nâng từ anonymous sang authenticated theo cơ chế được hỗ trợ).

Không lưu một attribute `"isAdmin": true` rồi coi đó là authorization. Backend vẫn cần kiểm tra quyền tài nguyên; Gateway không nên cấp quyền chỉ vì một header hoặc session attribute do code ứng dụng tự gán.

### 12.2. Cookie-based authentication và CSRF

Trình duyệt gửi session cookie tự động khi cookie scope cho phép. Vì vậy API dùng session-cookie auth có thể bị **CSRF** khi có request thay đổi trạng thái; `HttpOnly` không tự ngăn CSRF. Cần Spring Security CSRF protection hoặc biện pháp tương đương, kiểm tra SameSite và frontend workflow.

Đối với frontend cross-origin, cấu hình CORS cho phép **origin cụ thể** và credentials khi thực sự cần. `Access-Control-Allow-Origin: *` không phù hợp với credentialed responses. CORS là cơ chế browser và **không thay thế** xác thực/CSRF.

### 12.3. Một tài khoản nhiều session và giới hạn đăng nhập đồng thời

Nếu cần giới hạn số thiết bị/phiên của một người dùng hoặc “logout mọi nơi”, phải chọn Spring Session repository có **khả năng indexing/events phù hợp** và chính sách Spring Security tương ứng theo dòng phiên bản. Không mặc định basic reactive Redis session repository cung cấp đầy đủ chức năng tìm mọi session theo principal.

Hãy phân biệt:

- **Invalidating một session hiện hành:** `WebSession.invalidate()`.
- **Thu hồi tất cả session của principal:** cần index hoặc thiết kế định danh/khóa riêng.
- **Thu hồi JWT access token:** bài toán khác Spring Session; cần thiết kế token revocation/introspection/TTL.

## 13. Quan hệ với Gateway routing, retry, rate limiting và TLS

| Thành phần Gateway | Quan hệ với shared session |
| --- | --- |
| **Route predicate** | Chọn route theo request; không tự tạo hay chia sẻ session |
| **GatewayFilter SaveSession** | Đảm bảo session được save trước khi forward khi workflow cần |
| **StripPrefix/SetPath/RewritePath** | Thay path backend nhìn thấy, nhưng cookie browser vẫn dùng path công khai |
| **LoadBalancer `lb://...`** | Chọn **backend service instance**, độc lập với việc LB trước Gateway chọn replica A/B |
| **Rate limiting** | Có thể dựa trên principal đã xác thực; session ID không nên được lộ/log làm khóa định danh công khai |
| **Retry/circuit breaker** | Không bảo đảm thao tác session hoặc nghiệp vụ nguyên tử; retry POST có thể gây lặp |
| **TLS/forwarded headers** | Bảo vệ HTTPS client→Gateway và kết nối Gateway→Redis/backend; xử lý `X-Forwarded-Proto` từ proxy tin cậy |
| **Tracing/metrics** | Quan sát cả replica ID lẫn route ID/Redis error; không đưa session ID hoặc token vào tag |

**Đặc biệt:** Nếu Gateway A lưu session và proxy request tới `orders-service`, Spring Session ở Gateway **không tự cung cấp authentication state cho orders-service**. Muốn service nhận danh tính, thiết kế rõ token relay, token exchange hoặc header đã được Gateway xác minh trên kênh được bảo vệ. Service không được tin `X-User-Id` do client gửi.

## 14. Các tình huống tự luyện

**Tình huống 1 — A lưu counter, B trả 0:** Cả hai cùng Redis nhưng B dùng namespace `gateway-v2`. Vì sao?

Trả lời: namespace khác nên B không tìm bản ghi theo khóa mà A đã lưu. Phải đồng nhất namespace cho cùng cụm Gateway, cùng cookie name/scope, rồi thử lại.

**Tình huống 2 — Có sticky session nhưng A restart:** Client có giữ được session không?

Trả lời: nếu A chỉ lưu session trong RAM thì có thể mất. Sticky routing không thay shared store. Nếu dùng Redis chung và session còn hạn, replica mới có thể nạp lại dữ liệu.

**Tình huống 3 — Cả A/B đọc counter=5 đồng thời rồi increment:** Kết quả cuối có chắc là 7 không?

Trả lời: không. Hai request có thể cùng ghi 6, tạo lost update. Session repository không tự biến mẫu read-modify-write thành atomic transaction xuyên replica.

**Tình huống 4 — Gateway dùng Spring Session nhưng backend cần user ID:** Chỉ thêm `SaveSession` có đủ không?

Trả lời: không. SaveSession đảm bảo state của WebSession được lưu trước khi forward; backend vẫn cần cơ chế được thiết kế để tiếp nhận/kiểm tra danh tính. Không tin header do client tự cung cấp.

**Tình huống 5 — Dùng JWT access token stateless và không có cookie:** Có nhất thiết dùng Redis Spring Session không?

Trả lời: không. Nếu mọi request đã được xác thực bằng JWT và không có state ở Gateway, session store có thể không cần; bài toán token revocation và authorization vẫn phải được giải quyết riêng.

## 15. Checklist trước khi đưa vào production

- [ ] Xác định rõ hệ thống cần **stateful session** hay **stateless JWT**; không dùng cả hai thiếu chủ đích.
- [ ] Gateway là **Server WebFlux** với WebFlux-compatible Spring Session/Redis dependencies.
- [ ] Boot/Gateway/Spring Session versions tương thích; dùng đúng namespace Boot 3.x hoặc 4.x.
- [ ] Các replica trỏ cùng Redis, cùng namespace và serializer tương thích; không nhầm `localhost` giữa container.
- [ ] Kiểm thử luồng A → B → A bằng **cùng cookie** mà không dựa vào sticky routing.
- [ ] Session ID đủ ngẫu nhiên, không đưa vào URL/log/metric tag và được đổi khi nâng quyền/xác thực theo policy.
- [ ] Cookie có Path/Domain đúng URL công khai; production dùng HTTPS, Secure, HttpOnly và SameSite thích hợp.
- [ ] Xử lý logout/invalidate và timeout ở Redis; không đồng nhất cookie expiration với session TTL.
- [ ] Kiểm thử Redis unavailable, slow query, failover, eviction và rolling upgrade.
- [ ] Không lưu object lớn, secret hoặc dữ liệu nghiệp vụ cần atomic transaction trong session.
- [ ] API dùng cookie-based auth có CSRF protection; CORS credentials chỉ mở cho origin được phép.
- [ ] Backend không thể bị bypass Gateway trái phép; không tin identity header từ client.
- [ ] Chỉ dùng `SaveSession` khi workflow cần bảo đảm save trước khi proxy, hiểu đúng giới hạn.
- [ ] Có metrics theo replica/route/Redis latency và error, nhưng không log token/session ID.
- [ ] Test đồng thời nhiều request cùng session, logout từ replica khác và quy trình thu hồi phiên.

## 16. Tài liệu chính thức để đối chiếu

1. [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html): `WebSessionManager`, `ReactiveSessionRepository` và cách tích hợp Redis với WebFlux.
2. [Spring Boot 3.5 — Spring Session](https://docs.spring.io/spring-boot/3.5/reference/web/spring-session.html): Spring Session auto-configuration trong reactive app.
3. [Spring Boot 4.x — Spring Session](https://docs.spring.io/spring-boot/reference/web/spring-session.html): starter `spring-boot-starter-session-data-redis` và `spring.session.timeout`.
4. [Spring Boot 3.5 — Configuration Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.session.redis.namespace`, `spring.data.redis.*`.
5. [Spring Boot 4.x — Configuration Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.session.data.redis.namespace`.
6. [Spring Session — Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html): namespace, serializer và cơ chế expiration.
7. [Spring Session — WebFlux Custom Cookie](https://docs.spring.io/spring-session/reference/guides/boot-webflux-custom-cookie.html): `WebSessionIdResolver` và `CookieWebSessionIdResolver`.
8. [Spring Cloud Gateway Server WebFlux — SaveSession](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/savesession-factory.html): lưu WebSession trước khi forward.
9. [Gateway WebFlux 4.3 — SaveSession](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/savesession-factory.html): namespace cấu hình routes cũ.

**Ghi nhớ:** **Spring Session + Redis cho phép các Gateway WebFlux replica chia sẻ dữ liệu phiên theo cùng session ID**, để một request đến A và request tiếp theo đến B vẫn thấy trạng thái nhất quán trong điều kiện lưu/đọc tuần tự và hạ tầng hoạt động. Cookie giữ **ID**, Redis giữ **state**, còn `SaveSession` chỉ hỗ trợ **save trước khi forward** trong các workflow cần thiết. Chia sẻ phiên không tự cấp quyền, không thay bảo mật cookie/CSRF/TLS và không thay thế consistency cho dữ liệu nghiệp vụ.
