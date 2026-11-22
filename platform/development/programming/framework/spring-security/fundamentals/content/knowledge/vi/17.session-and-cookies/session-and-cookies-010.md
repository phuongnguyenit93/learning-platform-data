# Kho phiên chia sẻ khi ứng dụng chạy nhiều nút

> **Module:** Spring Security - fundamentals  
> **Nhóm:** Phiên và cookie  
> **Cốt lõi:** Một phiên đăng nhập có thể tồn tại xuyên nhiều instance khi tất cả cùng dùng kho lưu `HttpSession` và cùng tra cứu session ID từ cookie. Chia sẻ cookie nhưng không chia sẻ trạng thái server là chưa đủ.

## 1. Mục tiêu học tập

Sau khi đọc bài này, bạn có thể:

- Giải thích vì sao đăng nhập tại node A nhưng request đến node B lại bị yêu cầu đăng nhập.
- Phân biệt session cookie, session ID, session attributes và `SecurityContext` của Spring Security.
- So sánh sticky session và kho phiên chia sẻ (distributed/shared session store).
- Cấu hình Spring Session Redis cho Spring Boot Servlet/Spring Security và chạy hai instance độc lập với cùng Redis.
- Kiểm thử login, truy cập qua A/B, logout, timeout và xử lý khi Redis lỗi.
- Nhận diện yêu cầu bảo mật, consistency, serialization và vận hành của shared session store.

## 2. Bài toán nhiều nút

Ứng dụng web thường được triển khai nhiều bản sao sau load balancer:

~~~text
                Browser
             Cookie: SESSION=xyz
                    |
                    v
              Load Balancer
                /       \
               v         v
           App Node A  App Node B
            port 8081   port 8082
~~~

Nếu mỗi instance dùng session mặc định trong RAM của Servlet container, luồng sau có thể xảy ra:

1. Alice đăng nhập qua node A; node A lưu trạng thái phiên và thông tin authentication trong bộ nhớ cục bộ.
2. Browser giữ cookie chứa session ID do server cấp.
3. Request tiếp theo đi tới node B và gửi cùng cookie.
4. B không có session tương ứng với ID ấy trong RAM riêng.
5. B không thể khôi phục ngữ cảnh bảo mật của Alice và có thể chuyển hướng lại trang login.

Triệu chứng: phiên chập chờn, sau refresh bị logout, giỏ hàng mất, workflow nhiều bước khởi động lại, hoặc lỗi chỉ xảy ra khi tăng số replica.

**Điểm cần phân biệt:** cookie đã được gửi tới B chưa đồng nghĩa B có dữ liệu session. Cookie thường chỉ là một định danh mờ để tra cứu trạng thái ở phía server, chứ không chứa toàn bộ object user.

### Ba lớp liên quan

| Thành phần | Vị trí | Ý nghĩa |
| --- | --- | --- |
| Session cookie, ví dụ `SESSION` | Browser, gửi theo Domain/Path/SameSite/Secure | Chứa session ID để server tra cứu |
| Server-side session | RAM container, Redis hoặc kho dùng chung | Giữ attributes, metadata, thời hạn, trạng thái workflow |
| Spring SecurityContext | Ngữ cảnh bảo mật theo request; có thể được persist vào session | Chứa `Authentication` và authorities cho lần xử lý tiếp theo |

Session ID là bearer credential quan trọng. Nếu ai chiếm được ID còn hiệu lực, họ có thể mạo danh phiên; không log ID công khai hoặc trả session ID trong response JSON.

## 3. Sticky session so với distributed session

### Sticky session

Load balancer dùng session affinity để đưa các request của Alice về đúng node A:

~~~text
Alice -> LB -> A -> A -> A
Bob   -> LB -> B -> B -> B
~~~

Cách này có thể giúp ứng dụng legacy dùng local session tiếp tục hoạt động khi routing giữ nguyên. Tuy nhiên, nếu A restart, scale-in, hỏng hoặc load balancer thay đổi route, B vẫn không có RAM của A. Sticky routing cũng làm phân tải kém đều và gây phụ thuộc vào chính sách LB.

### Kho phiên dùng chung

Các nút đọc/ghi session vào một kho chung, ví dụ Redis:

~~~text
               Browser: SESSION=sid-42
                         |
                         v
                    Load Balancer
                       /     \
                      v       v
                    Node A   Node B
                      \       /
                       v     v
                        Redis
               sid-42 -> session attributes
                         SecurityContext
                         expiry metadata
~~~

Node A có thể ghi session, Node B có thể dùng cùng cookie/session ID để đọc lại. Các instance phải nhất quán về backend, namespace, serializer và cách xử lý cookie. Khi dữ liệu được lưu thành công trong kho chung, việc đổi node không đương nhiên làm mất phiên.

Sticky session và Redis store không loại trừ nhau, nhưng tính đúng đắn của ứng dụng có yêu cầu failover **không nên lệ thuộc** sticky routing.

## 4. Spring Session và Spring Security tích hợp ra sao?

Trong ứng dụng **Servlet/Spring MVC**, Spring Session cung cấp một filter và `SessionRepository` để thay thế thực thi `HttpSession` thông thường. Khi dùng backend Redis:

~~~text
HTTP request + Cookie SESSION
         |
         v
Spring Session filter đọc session ID
         |
         v
Redis SessionRepository tìm session attributes
         |
         v
HttpServletRequest/HttpSession đã được wrap
         |
         v
Spring Security phục hồi SecurityContext nếu dùng session persistence
         |
         v
Controller/service đọc hoặc cập nhật HttpSession
         |
         v
Spring Session lưu dữ liệu thay đổi về Redis
~~~

Spring Security chịu trách nhiệm **xác thực** và **phân quyền**; Spring Session chịu trách nhiệm lưu và tìm session. Redis không tự kiểm tra username/password.

Với form login, SecurityContext sau khi xác thực thành công thường được persist vào `HttpSession` qua cơ chế Spring Security thích hợp. Khi Spring Session thay backend thành Redis, các nút có thể phục hồi cùng context.

Không mặc định mọi ứng dụng đều phải lưu SecurityContext trong session: API JWT/Bearer stateless có thể xác thực mỗi request và không cần session để nhận diện người dùng.

## 5. Ví dụ thực hành Java 17+: hai tiến trình dùng chung Redis

Bộ ví dụ sau dùng Java 17+, Gradle 8.x, Spring Boot 3.3.5, Spring Security 6.x và Spring Session Redis do Boot BOM quản lý. Sử dụng form login mặc định để việc phục hồi authentication có thể quan sát trực tiếp.

Mô hình thử: A chạy ở cổng 8081, B ở 8082, Redis local ở 6379. Cùng một browser sử dụng **localhost** ở hai cổng; cookie theo host chứ không theo port.

### 5.1. Cấu trúc project

~~~text
shared-session-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/cluster/
    │   ├── SharedSessionApplication.java
    │   ├── SecurityConfig.java
    │   └── SessionController.java
    └── resources/
        └── application.properties
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'shared-session-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
}
~~~

Giải thích:

- Starter Web cung cấp Tomcat và Spring MVC/Servlet stack.
- Starter Security cung cấp security filter chain và form login.
- Starter Data Redis cung cấp `RedisConnectionFactory` và Redis client.
- `spring-session-data-redis` tích hợp `SessionRepository` dựa trên Redis và filter tương ứng; Spring Boot hỗ trợ auto-configuration.
- Dùng dependency versions do Boot quản lý để tránh ghép các bản Spring Session/Security không tương thích.

### 5.2. Main application

File `src/main/java/demo/cluster/SharedSessionApplication.java`:

~~~java
package demo.cluster;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SharedSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SharedSessionApplication.class, args);
    }
}
~~~

### 5.3. Spring Security form login

File `src/main/java/demo/cluster/SecurityConfig.java`:

~~~java
package demo.cluster;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

Mật khẩu `demo-pass` chỉ phục vụ local demo, tuyệt đối không đưa tài khoản này lên môi trường công khai. Hai instance có cùng cấu hình user, nhưng việc các node chia sẻ phiên đến từ **Redis session store**, không phải từ việc có cùng password.

CSRF protection được giữ theo mặc định cho form login. Không tắt CSRF để tránh rắc rối với phiên; trang login mặc định của Spring Security xử lý token trong form.

### 5.4. Controller lưu bộ đếm vào `HttpSession`

File `src/main/java/demo/cluster/SessionController.java`:

~~~java
package demo.cluster;

import java.util.Map;
import jakarta.servlet.http.HttpSession;
import org.springframework.core.env.Environment;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    private final Environment environment;

    public SessionController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/public/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/")
    public Map<String, Object> home(
            Authentication authentication, HttpSession session) {
        Integer oldCount = (Integer) session.getAttribute("counter");
        int count = (oldCount == null ? 0 : oldCount) + 1;
        session.setAttribute("counter", count);

        return Map.of(
            "node", environment.getProperty("server.port", "8081"),
            "user", authentication.getName(),
            "counter", count
        );
    }
}
~~~

Quan trọng: bộ đếm được đặt trong `HttpSession`, **không** phải field của controller hay biến static. Nếu A ghi counter vào session và B đọc được counter đó, chúng đang sử dụng state chung. Response không công khai session ID.

`oldCount + 1` chỉ an toàn để minh họa khi request tuần tự; với hai request concurrent, read-modify-write có thể mất cập nhật. Không dùng `HttpSession` như một database transaction cho số dư/hạn mức thực.

### 5.5. Cấu hình Redis và session

File `src/main/resources/application.properties`:

~~~properties
server.port=8081

# Cả hai instance dùng cùng Redis.
spring.data.redis.host=localhost
spring.data.redis.port=6379

# Server-side inactivity timeout.
server.servlet.session.timeout=30m

# Cùng namespace trên tất cả node, tách biệt với ứng dụng khác.
spring.session.redis.namespace=learning:shared-session-demo

# Cấu hình flush mode minh họa.
spring.session.redis.flush-mode=on_save

# Cookie bảo vệ cơ bản trên local demo.
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

Với Spring Boot có dependency Spring Session Redis và Redis auto-config thích hợp, thường **không cần** tự thêm `@EnableRedisHttpSession` vào project. Spring Session filter được đăng ký bằng Boot auto-configuration.

Các instance cần nhất quán:

| Cấu hình | Node A | Node B |
| --- | --- | --- |
| Redis host/port | `localhost:6379` | `localhost:6379` |
| Redis namespace | `learning:shared-session-demo` | `learning:shared-session-demo` |
| Security/session serializer | Cùng phiên bản/cấu hình tương thích | Cùng phiên bản/cấu hình tương thích |
| Public hostname | `localhost` | `localhost` |
| HTTP port | `8081` | `8082` |

Nếu chạy trên hai máy khác nhau, `localhost` **không còn** chỉ cùng một Redis. Cả hai phải dùng hostname Redis chung qua mạng riêng. Điều đó thường là nguồn lỗi khi chuyển từ demo local sang Kubernetes hoặc nhiều VM.

### 5.6. Chạy Redis

Nếu đã có Docker và cổng local 6379 đang rảnh:

~~~bash
docker run --name shared-session-redis -d -p 127.0.0.1:6379:6379 redis:7
~~~

Cổng Redis trong demo chỉ bind loopback của host, tránh vô tình public server Redis. Nếu container đã có hoặc hệ thống cung cấp Redis riêng, dùng instance phù hợp thay vì tạo mới.

Kiểm tra Redis:

~~~bash
docker exec shared-session-redis redis-cli ping
~~~

Stdout dự kiến:

~~~text
PONG
~~~

### 5.7. Build một lần, chạy hai instance

Trong thư mục project:

~~~bash
gradle bootJar
~~~

Jar theo cấu hình ví dụ dự kiến ở `build/libs/shared-session-demo-0.0.1-SNAPSHOT.jar`.

Terminal A:

~~~bash
java -jar build/libs/shared-session-demo-0.0.1-SNAPSHOT.jar --server.port=8081
~~~

Terminal B:

~~~bash
java -jar build/libs/shared-session-demo-0.0.1-SNAPSHOT.jar --server.port=8082
~~~

Đây là **hai tiến trình** cùng dùng một jar; override port không ảnh hưởng namespace Redis. Trên production, hai tiến trình có thể nằm trong container khác nhau, phía trước được route bởi load balancer.

### 5.8. Kiểm thử trên browser

1. Mở `http://localhost:8081/`. Vì chưa đăng nhập, Spring Security chuyển đến form login.
2. Nhập username `alice` và password `demo-pass`. Form login mặc định xử lý CSRF token và tạo/ghi session cần thiết.
3. Sau khi về `/`, ví dụ body:

~~~json
{"node":"8081","user":"alice","counter":1}
~~~

4. Cùng browser profile, mở `http://localhost:8082/`. **Không đăng nhập lại**, ví dụ nhận:

~~~json
{"node":"8082","user":"alice","counter":2}
~~~

5. Quay lại `http://localhost:8081/`, ví dụ:

~~~json
{"node":"8081","user":"alice","counter":3}
~~~

Thứ tự các JSON keys không được bảo đảm; ở đây chỉ quan tâm đến giá trị. Kết quả count giả định các request tuần tự và không có prefetch/refresh khác đến path `/`.

**Tiêu chí PASS:** cùng browser từ A sang B vẫn authenticated, và state `counter` tiếp tục tăng thay vì reset về 1. Truy cập với hai hostname khác nhau (`localhost` và `127.0.0.1`) có thể không gửi chung cookie; đó là quy tắc cookie, không chứng minh Redis hỏng.

### 5.9. Quan sát namespace Redis

Trong môi trường demo:

~~~bash
docker exec shared-session-redis redis-cli --scan --pattern 'learning:shared-session-demo:*'
~~~

Các key session thực tế có thể chứa session IDs. Không sao chép ra log, ticket hay tài liệu công khai. Không chạy `FLUSHALL`, `KEYS *` rồi xóa hàng loạt trên Redis dùng chung.

Nếu muốn chứng minh dependency vào Redis, thử tắt Redis **trong môi trường học tập** và quan sát app có thể không đọc/ghi session; đừng thử trên hệ thống có người dùng thật.

## 6. Cookie, TTL, timeout và session fixation

Browser thường giữ cookie tên `SESSION` khi dùng Spring Session; nếu chỉ dùng Servlet container local session, tên thường là `JSESSIONID`. Tên có thể tùy biến; **không suy đoán toàn bộ backend chỉ từ tên cookie**.

### Cookie không chứa toàn bộ session

~~~http
GET / HTTP/1.1
Host: example.com
Cookie: SESSION=<opaque-id>
~~~

Cookie chứa ID giúp tìm session trên Redis. Không đưa password, principal details, giỏ hàng hoặc SecurityContext trực tiếp vào cookie session ID theo mặc định.

### Các thuộc tính cookie quan trọng

| Thuộc tính | Mục đích |
| --- | --- |
| `HttpOnly` | Giảm khả năng JS đọc cookie qua `document.cookie`; không giải quyết toàn bộ XSS |
| `Secure` | Chỉ gửi cookie qua HTTPS trong ngữ cảnh được browser hỗ trợ |
| `SameSite` | Hạn chế một số trường hợp gửi cookie cross-site; không thay thế CSRF |
| `Path` | Giới hạn các request path có cookie |
| `Domain` | Quy định miền/subdomain chia sẻ cookie; tránh đặt quá rộng |
| `Max-Age`/`Expires` | Thời hạn cookie browser, **khác** server-side idle timeout |

Production nên chạy HTTPS và thiết lập `Secure`, `HttpOnly`, SameSite/Domain/Path phù hợp. Khi TLS kết thúc tại reverse proxy, cần cấu hình forwarded headers/đường truyền tin cậy để server xác định scheme chính xác.

### Server-side timeout

`server.servlet.session.timeout=30m` mô tả max inactive interval trong demo. Session có thể hết hạn trên Redis ngay cả khi browser vẫn giữ cookie cũ; request phải được coi là chưa có session hợp lệ.

Redis TTL/expiry events không đồng nghĩa event dọn dẹp nhất thiết xảy ra đúng mili giây. Ứng dụng cần dựa vào trạng thái session hợp lệ khi tra cứu, không coi một Redis pub/sub event là bằng chứng duy nhất.

### Session fixation protection

Khi người dùng đăng nhập, Spring Security thường thay đổi session ID trên Servlet container hiện đại để giảm nguy cơ session fixation. Với Spring Session, việc đổi ID phải tương thích với session repository và cookie mới. Đừng “đóng đinh” session ID trong client hoặc lưu ID như một khóa nghiệp vụ bất biến.

### Logout xuyên nút

Hãy thử: login trên A, truy cập B thành công, logout trên B, quay lại A. Request vào resource protected ở A phải được yêu cầu xác thực lại khi session đã được vô hiệu hóa. Shared store giúp tác dụng của invalidate có thể được quan sát từ mọi nút, nhưng application còn phải triển khai logout và cookie handling đúng.

## 7. Hai lựa chọn Redis session repository

Spring Session Redis hỗ trợ hai kiểu chính:

| Repository | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| `RedisSessionRepository` | Lưu/truy xuất session theo ID, không duy trì indexes bổ sung | Phần lớn nhu cầu session lookup cơ bản |
| `RedisIndexedSessionRepository` | Duy trì thêm index để tìm session theo principal và xử lý một số sự kiện expiry/deletion | Khi cần tìm mọi session của user hoặc luồng lifecycle phụ thuộc events |

Với Spring Boot cấu hình hiện đại, `RedisSessionRepository` thường là default; các property như `spring.session.redis.repository-type=default` hoặc `indexed` cho phép chọn tùy bản tương ứng.

Đừng tự bật indexed vì nghĩ “nhanh hơn”. Nó thêm chi phí index/sự kiện và có caveat về Redis Cluster. Tài liệu Spring Session lưu ý rằng indexed repository có thể subscribe expiry events trên một node ngẫu nhiên của cluster, gây cleanup index không đầy đủ khi key hết hạn ở node khác. Các tính năng như global logout bằng index cần kiểm thử trên topology thật.

Demo này chỉ cần repository cơ bản để tra cứu session bằng ID.

## 8. Serialization và rolling deployment

Session attributes phải serialize khi ghi lên Redis và deserialize khi nút khác đọc. Mặc định thường dùng Java serialization trong Spring Session Redis; các đối tượng được lưu cần serializable và tương thích giữa các instance.

Ví dụ:

~~~text
Node A đang chạy phiên bản CartState v1
    -> serialize vào session Redis

Node B vừa rollout CartState v2 không tương thích
    -> deserialize lỗi hoặc đọc dữ liệu sai
    -> request/session bị lỗi
~~~

Các nguyên tắc:

- Không lưu object quá lớn, repository, datasource, socket hoặc service bean vào session.
- Dùng dữ liệu cần thiết, cấu trúc ổn định, và kiểm tra version compatibility khi rolling deploy.
- Không đổi serializer giữa chừng mà không có kế hoạch migration/invalidating sessions.
- Để custom serialization, Spring Session hỗ trợ bean `springSessionDefaultRedisSerializer` nhưng phải tương thích với `SecurityContext` và các type của Spring Security.
- Không cho bên không tin cậy ghi key session; deserialization dữ liệu không đáng tin là một rủi ro bảo mật.

Việc hai node cùng kết nối Redis không đủ nếu classpath/schema/serializer không tương thích.

## 9. Đồng thời ghi session và nhất quán dữ liệu

Shared session store giải quyết tra cứu state xuyên nút, **không cung cấp một distributed transaction cho mọi operation**.

Ví dụ hai requests cùng đọc counter=4:

~~~text
Node A: read 4 -> set 5
Node B: read 4 -> set 5
Node A: save 5
Node B: save 5

Hai requests nhưng counter cuối có thể là 5, không phải 6.
~~~

Đây là lost update của read-modify-write trên cùng session. Nếu cần số dư/hạn mức/giỏ hàng có semantics đồng thời nghiêm ngặt, hãy dùng cơ chế atomic update, optimistic locking hoặc dữ liệu nghiệp vụ có transaction riêng, thay vì tin `HttpSession` tự giải quyết mọi race.

### Flush mode

- `ON_SAVE`: lưu khi repository save; trong web flow thường trước khi response commit.
- `IMMEDIATE`: cố cập nhật session lên Redis sớm hơn khi giá trị thay đổi.

Flush mode tác động tần suất ghi và thời điểm visibility giữa requests, nhưng không tự bảo đảm atomicity hay giải quyết xung đột giữa mọi nút.

## 10. Vận hành Redis như một thành phần bảo mật

Khi session được lưu ở Redis, Redis không còn chỉ là cache tùy chọn mà là **dependency quan trọng của quá trình đăng nhập**.

### Tính sẵn sàng

- Redis outage có thể làm request lỗi hoặc không thể khôi phục session.
- Cân nhắc Redis Sentinel, Cluster hoặc dịch vụ managed HA tùy SLA.
- Theo dõi latency, bộ nhớ, eviction, connection pool, errors, backup/restore và failover.
- Chọn eviction/memory policy có chủ đích; một eviction có thể khiến người dùng mất session.
- Khi dùng Redis Cluster, xem lại indexed repo, events/expiry và giới hạn topology.

### Bảo mật kết nối

- Không public Redis port ra Internet.
- Ưu tiên private network, TLS, ACL/password và secret rotation theo chính sách triển khai.
- Cô lập namespace và quyền truy cập của từng ứng dụng.
- Không dump/log dữ liệu session, credential, serialized SecurityContext hoặc session IDs ở nơi không cần.
- Dùng một hệ thống audit phù hợp để phát hiện truy cập session trái phép.

### Thay đổi quyền trong lúc session còn hiệu lực

Cùng shared store không đồng nghĩa mỗi session lập tức cập nhật authorities khi role trong database bị thu hồi. Session có thể còn giữ `Authentication` từ lúc login. Đối với nghiệp vụ nhạy cảm, cần cơ chế revalidation, session invalidation hoặc cập nhật security context theo chính sách.

### Stateless JWT là trường hợp khác

Nếu tất cả endpoint xác minh JWT/Bearer token mỗi request và sử dụng `SessionCreationPolicy.STATELESS`, có thể không cần Redis-backed `HttpSession` để nhận diện user trên nhiều nút. Các nút chỉ cần tin cùng issuer/keys/policy. Không trộn mô hình stateless với kỳ vọng form-login session persistence mà không thiết kế rõ.

## 11. Phân biệt Servlet `HttpSession` và WebFlux `WebSession`

Demo dùng **Spring MVC/Servlet**. Ứng dụng Spring WebFlux có `WebSession` và reactive Spring Session integration, khác về API/filter với `HttpSession`.

Không copy nguyên `@EnableRedisHttpSession` hoặc Servlet-specific filters vào một ứng dụng WebFlux thuần và cho rằng đã chia sẻ reactive session đúng. Reactive security context sử dụng Reactor Context; khi cần server-side session hãy chọn reactive Redis session repository và cấu hình tương ứng.

Với cả hai stack, nguyên lý vẫn là: một client có session ID và nhiều nút cần cùng truy xuất session state, không dựa vào RAM cục bộ của một node.

## 12. Bộ kiểm tra nghiệm thu đa nút

| Kịch bản | Thao tác kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Login | Browser vào A, login | Có session cookie hợp lệ, A trả user Alice |
| Cross-node | Cùng browser vào B | Không login lại, B trả user Alice |
| Shared state | A tăng counter, B truy cập | Counter tiếp tục tăng qua hai nút |
| Quay lại A | B rồi A | Không reset phiên |
| Logout | Logout ở B, truy cập protected route trên A | A yêu cầu đăng nhập lại |
| Restart | Restart A, Redis còn | B tiếp tục phiên còn hợp lệ |
| Timeout | Hết inactivity interval | Cả A/B không cho dùng session cũ |
| Cookie khác host | Đổi `localhost` thành `127.0.0.1` | Cookie không tự chia sẻ giữa host khác nhau |
| Concurrent updates | Hai requests cùng sửa một session | Phải hiểu rủi ro lost update; không mặc định +2 |
| Redis down | Ngắt Redis trong môi trường test | Ghi nhận lỗi theo chính sách, không giả định fail-open |

### Chẩn đoán sự cố

| Triệu chứng | Nên kiểm tra |
| --- | --- |
| B đòi login lại | Cookie host/path/name, Redis host/namespace, serializer, security persistence |
| Counter luôn là 1 | Không gửi cookie, không lưu session, timeout/eviction hoặc request nhầm hostname |
| Lỗi sau rolling update | Session object schema/serialization thay đổi không tương thích |
| Lúc được lúc mất | Load balancing, Redis availability, cookie scope, data races |
| Logout không áp dụng toàn cluster | Session invalidation/persistence, cookie khác, cache cục bộ |
| Redis đầy và user bị logout | Eviction policy, TTL, memory, error handling |
| Dữ liệu session thay đổi không đều | Concurrent writes, flush/save mode, code dùng static/local state |

## 13. Checklist thực hành

- [ ] Xác định ứng dụng **thật sự cần stateful session**, không phải API hoàn toàn stateless.
- [ ] Tất cả nodes dùng cùng Redis endpoint, session namespace, serializer và security configuration tương thích.
- [ ] Cookie scope đúng public host/path; trên production có HTTPS, Secure, HttpOnly, SameSite phù hợp.
- [ ] Không log session ID hoặc chứa bí mật không cần thiết trong session.
- [ ] Login, A-to-B, logout, timeout và restart được test với ít nhất hai instance.
- [ ] Cân nhắc migration dữ liệu session trong rolling deployment.
- [ ] Không dùng shared `HttpSession` làm nguồn dữ liệu authoritative cần atomic consistency.
- [ ] Có kế hoạch Redis HA, monitoring, network access, credentials và failure modes.
- [ ] Có chính sách invalidation khi account/roles thay đổi.
- [ ] Không tắt CSRF hoặc bỏ security filters chỉ để test phiên thuận lợi.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao cookie vẫn được browser gửi nhưng sang node B lại bị yêu cầu login?

**Đáp án:** Cookie chỉ mang session ID. Nếu B không đọc được attributes/SecurityContext ứng với ID đó từ cùng kho session, B không thể khôi phục identity của A.

**Câu 2.** Sticky session có thay được shared session store không?

**Đáp án:** Không hoàn toàn. Affinity giữ request ở một node trong điều kiện routing ổn định; nếu node đó mất hoặc route đổi, local RAM session vẫn không thể tự di chuyển.

**Câu 3.** Cùng kết nối Redis nhưng không chia sẻ phiên: vì sao?

**Đáp án:** Có thể khác namespace, cookie ID/scope, session repo, serializer hoặc SecurityContext persistence. Cần kiểm tra cả chain lưu và chain đọc.

**Câu 4.** Spring Session Redis có khiến mọi phép cộng counter session thành atomic across nodes không?

**Đáp án:** Không. Concurrent read-modify-write có thể gây lost updates; phải chọn cơ chế riêng nếu cần atomicity.

**Câu 5.** JWT stateless có bắt buộc Redis-backed HttpSession để chạy đa nút không?

**Đáp án:** Không. Nếu xác minh bearer token mỗi request và không cần stateful session, các nút có thể hoạt động mà không lưu login state trên Redis.

**Câu 6.** Vì sao không in giá trị cookie `SESSION` vào JSON response để debug?

**Đáp án:** Session ID còn hiệu lực có thể dùng để chiếm phiên. Chỉ quan sát an toàn, bảo vệ logs và không công khai ID.

## 15. Tổng kết và tài liệu đọc thêm

**Chia sẻ kho phiên giải quyết vấn đề dữ liệu session nằm riêng trong RAM từng node.** Cookie chứa session ID; Spring Session Redis ánh xạ ID tới attributes trên một backend chung; Spring Security có thể khôi phục `Authentication` qua SecurityContext được persist trong phiên. Để hệ thống hoạt động đúng và an toàn, các node cần cùng Redis/namespace/serializer, cookie scope chuẩn và chính sách timeout/logout/HA/concurrency rõ ràng.

Tài liệu chính thức:

- [Spring Session — Spring Boot + Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
- [Spring Session — Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/websession.html)
