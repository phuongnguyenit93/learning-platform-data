# Spring Session, nhiều nút ứng dụng và giới hạn kho phiên cục bộ

## Mục tiêu bài học

Một ứng dụng Spring Boot chạy một JVM có thể giữ phiên HTTP trong bộ nhớ của Servlet container. Khi hệ thống mở rộng thành **nhiều instance/pod/nút** phía sau load balancer, cách lưu phiên đó bộc lộ giới hạn: mỗi nút chỉ biết các session do chính nó quản lý. Người dùng có thể đăng nhập trên nút A, sau đó request được chuyển tới nút B và bị coi là chưa đăng nhập. Nếu A bị khởi động lại hoặc ngừng hoạt động, dữ liệu phiên cục bộ có thể mất.

**Spring Session** cung cấp một tầng trừu tượng và các triển khai **SessionRepository** để đưa dữ liệu phiên ra kho chung, chẳng hạn Redis hoặc JDBC. Khi cấu hình phù hợp, nhiều nút cùng tra cứu session theo ID do trình duyệt gửi, trong khi phần lớn code vẫn làm việc với **HttpSession** của Servlet API.

Sau bài này, bạn sẽ có thể:

1. Giải thích vì sao local HttpSession khó đáp ứng cân bằng tải, failover và rolling deployment.
2. Mô tả luồng **cookie → SessionRepositoryFilter → Redis/JDBC SessionRepository → Spring Security SecurityContext**.
3. Phân biệt **chia sẻ HttpSession** với **chia sẻ mọi trạng thái của JVM**, và nhận diện những thứ Spring Session không tự giải quyết.
4. Dựng hai instance Spring Boot Servlet dùng **cùng Redis**, đăng nhập ở instance A và tiếp tục sử dụng session tại B.
5. Phân biệt **RedisSessionRepository** với **RedisIndexedSessionRepository**, và hiểu hạn chế của SessionRegistry trong môi trường nhiều nút.
6. Đánh giá rủi ro khi Redis không sẵn sàng, session hết hạn, serialize đối tượng, thay đổi phiên bản ứng dụng và lưu trữ session với quy mô lớn.

**Phạm vi:** Spring Boot 3.5.x, Spring Security Servlet 6.x, Spring Session 3.5.x, Java 17+, ví dụ dùng Redis. Các phiên bản mới hơn có thể đổi tên starter hoặc thuộc tính; khi đưa vào dự án thực tế, đối chiếu tài liệu đúng phiên bản của dự án. Reactive WebFlux dùng **WebSession** và repository reactive riêng, không sao chép trực tiếp toàn bộ cấu hình Servlet.

## 1. Vấn đề: mỗi JVM có kho phiên của chính nó

Hình dung load balancer phân phối request cho hai instance của cùng ứng dụng:

~~~text
                     Browser
            Cookie: JSESSIONID=abc
                        |
                 Load balancer
                  /           \
                 v             v
          App Node A       App Node B
          JVM / Pod A      JVM / Pod B
          Local session    Local session
          {abc -> Alice}   {không có abc}
                 |             |
          GET /me -> Alice    GET /me -> unauthenticated
~~~

Trong cấu hình Servlet container dùng kho phiên cục bộ, cookie chỉ chứa **định danh phiên**; phần dữ liệu tương ứng nằm trong bộ nhớ hoặc cơ chế storage riêng của instance. Một request đến B với cookie do A phát **không có cách mặc định** để B đọc dữ liệu phiên trong JVM của A.

Hậu quả thường gặp:

- Sau khi đăng nhập thành công, người dùng đôi lúc bị chuyển lại trang login khi request đi sang nút khác.
- Giỏ hàng, trạng thái form, flow nhiều bước hoặc SecurityContext có thể trông như “biến mất”.
- Khi node lưu session dừng hoặc được thay mới, phiên đang nằm tại đó có thể không còn truy cập được.
- Scale-out làm xác suất request chuyển nút tăng; lỗi có thể khó tái hiện nếu môi trường dev chỉ có một node.

**Đừng nhầm với tình huống login không lưu SecurityContext:** ngay trên *cùng* một node, nếu custom authentication code chỉ gọi SecurityContextHolder.setContext mà không lưu qua SecurityContextRepository, request tiếp theo cũng có thể mất đăng nhập. Spring Session giải quyết **nơi lưu phiên**, còn authentication mechanism phải lưu context đúng cách trước.

### Sticky session có đủ không?

**Session affinity/sticky routing** buộc load balancer ưu tiên gửi một client trở lại nút đã tạo session.

Ưu điểm: dễ áp dụng và giảm request chuyển nút; có thể hỗ trợ các ứng dụng cũ.

Hạn chế:

- Nút A bị lỗi hoặc bị thay trong rolling deployment thì session gắn với A vẫn có thể mất.
- Phân phối tải bị lệch khi người dùng có thời gian sống phiên khác nhau.
- Người dùng phải đi đúng load balancer/route; nhiều tầng proxy hoặc thay cấu hình affinity có thể khiến request đổi nút.
- Session cục bộ vẫn gây khó khăn cho quản lý đăng nhập đồng thời trên toàn cluster.

Sticky routing có thể là giải pháp tạm, nhưng **không tự biến kho phiên cục bộ thành kho phiên dùng chung**. Với yêu cầu failover giữ trạng thái, cần một cơ chế lưu trữ/replication phù hợp.

## 2. Spring Session thay đổi điều gì?

Spring Session cung cấp **SessionRepository** và tích hợp Servlet để thay cách lưu trữ HttpSession. Trong ứng dụng dùng Redis, request sẽ đi qua một filter thường được đăng ký bằng tên **springSessionRepositoryFilter**.

~~~text
                       Browser
                    Cookie: SESSION=xyz
                            |
                       Load balancer
                         /       \
                        v         v
                  App Node A   App Node B
                       \         /
                        \       /
                  SessionRepositoryFilter
                    (trên từng node)
                           |
                 Redis SessionRepository
                           |
                         Redis
                   {xyz -> session data}
                       /       \
                      v         v
               cả A và B có thể đọc
             session xyz theo cùng ID
~~~

Diễn biến trong một request:

1. Trình duyệt gửi cookie định danh session.
2. **SessionRepositoryFilter** bao bọc request/response để các thao tác với **HttpSession** sử dụng Spring Session repository.
3. Repository đọc session theo ID từ Redis/JDBC thay cho kho session mặc định chỉ thuộc một JVM.
4. Nếu session còn hợp lệ, Spring Security có thể đọc **SecurityContext** đã được lưu trong session đó.
5. Controller chạy và có thể đọc/ghi thuộc tính session bằng Servlet API.
6. Các thay đổi session được repository ghi về kho chung tại thời điểm phù hợp với chế độ lưu/flush.
7. Request tiếp theo tới node khác dùng cùng ID và cùng namespace để tải dữ liệu phiên.

**Spring Session không tự xác thực người dùng.** Nó cung cấp cách lưu/khôi phục session. **Spring Security** vẫn chịu trách nhiệm xác thực, phân quyền, lưu SecurityContext, bảo vệ session fixation, CSRF và logout theo cấu hình.

### Cookie mặc định: SESSION hay JSESSIONID?

Khi dùng HttpSession của Servlet container thông thường, cookie phổ biến là **JSESSIONID**. Với Spring Session Servlet và **DefaultCookieSerializer**, tên cookie mặc định là **SESSION**. Có thể đổi qua CookieSerializer nếu có yêu cầu tương thích.

Vì vậy, khi debug cần nhìn **cookie thực tế được phát**, không giả định nó luôn mang tên JSESSIONID. Cookie chứa ID để tìm session, **không chứa toàn bộ SecurityContext hoặc nội dung phiên**.

### Mọi node cần đồng nhất điều gì?

- Cùng ứng dụng hoặc các phiên bản tương thích của dữ liệu session.
- Cùng Redis/JDBC session store, namespace và cách mã hóa/serialize.
- Cùng chính sách cookie domain/path, HTTPS, proxy và session timeout.
- Cùng mô hình xác thực và SecurityContextRepository có thể đọc dữ liệu đã lưu.
- Đồng hồ được đồng bộ hợp lý, đặc biệt nếu ứng dụng áp dụng thời hạn tuyệt đối ngoài inactivity timeout.

Nếu node A ghi session vào Redis database/namespace khác với node B, dù cả hai đều “dùng Spring Session”, B vẫn không thể tải đúng session đó.

## 3. So sánh ba hướng tổ chức lưu session

| Mô hình | Session nằm ở đâu? | Khi request đổi node? | Khi node chết? | Đánh đổi chính |
| --- | --- | --- | --- | --- |
| **Local HttpSession** | JVM / Servlet container từng node | Có thể mất đăng nhập nếu sang node không có session | Có thể mất session cục bộ | Đơn giản, không cần kho ngoài, nhưng scale/failover khó |
| **Sticky + local session** | Vẫn ở mỗi node, LB cố giữ client tại node đó | Bình thường ít đổi, nhưng không có bảo đảm về failover | Thường vẫn mất hoặc cần cơ chế replication riêng | Phụ thuộc affinity, phân bố tải |
| **Spring Session + Redis/JDBC** | Kho phiên dùng chung ngoài instance | Có thể khôi phục trên node khác theo cùng ID | Thường giữ được session nếu kho chung còn hoạt động | Thêm latency, chi phí, dependency và yêu cầu vận hành |

**Một nút bị thay thế** khác với **kho session bị mất**. Spring Session có thể bảo toàn session khi JVM ứng dụng thay đổi, nhưng nếu Redis chính bị xóa dữ liệu hoặc downtime nghiêm trọng, hệ thống vẫn bị ảnh hưởng. Spring Session không mặc nhiên cung cấp high availability cho Redis.

### Redis so với JDBC

**Redis** thường thích hợp cho tải session có tần suất đọc/ghi cao, TTL và truy cập nhanh. Cần quản trị bộ nhớ, eviction, replication/failover, xác thực/TLS, serializer và số kết nối.

**JDBC** có thể phù hợp khi tổ chức đã có database vận hành ổn định và muốn quản lý session qua bảng. Cần migration schema, connection pool, chỉ mục, dọn session hết hạn, contention và hiệu năng đọc/ghi.

Spring Session có thể hỗ trợ các store khác tùy phiên bản. Lựa chọn store phụ thuộc SLA, thông lượng, chi phí, yêu cầu consistency, cấu trúc dữ liệu và hạ tầng hiện hữu. Không chọn Redis chỉ vì hệ thống có nhiều node mà bỏ qua năng lực vận hành Redis.

## 4. Spring Security liên quan thế nào?

Luồng đăng nhập bằng form có session thường là:

~~~text
POST /login (credentials + CSRF token)
      |
      v
AuthenticationManager xác thực
      |
      v
SessionAuthenticationStrategy
  ví dụ bảo vệ session fixation
      |
      v
SecurityContext chứa Authentication
      |
      v
SecurityContextRepository lưu vào HttpSession
      |
      v
Spring Session ghi session vào Redis
      |
      v
Browser nhận cookie SESSION
      |
      v
GET /me đến node B
      |
      v
Spring Session đọc Redis theo SESSION ID
      |
      v
Spring Security khôi phục Authentication
      |
      v
Authorization -> Controller -> 200
~~~

Với **formLogin** do Spring Security quản lý, framework xử lý các bước authentication và persistence theo cấu hình. Khi tự viết controller JSON login hoặc authentication filter, bạn phải bảo đảm **SessionAuthenticationStrategy** (nếu có session) và **SecurityContextRepository.saveContext(...)** được gọi đúng thời điểm. Chỉ thêm Spring Session dependency sẽ không biến controller login tự viết thành cơ chế lưu context hoàn chỉnh.

### SessionCreationPolicy phải phù hợp

| SessionCreationPolicy | Ảnh hưởng tới mục tiêu duy trì login qua Redis |
| --- | --- |
| **ALWAYS** | Spring Security có thể tạo phiên sớm; thường không cần thiết chỉ để dùng Redis |
| **IF_REQUIRED** | Phù hợp session login: chỉ tạo khi cần, dùng repository có khả năng lưu context |
| **NEVER** | Không chủ động tạo nhưng có thể dùng session sẵn có; không phải lựa chọn phổ biến cho login mới từ client chưa có session |
| **STATELESS** | Spring Security không dùng HttpSession để khôi phục SecurityContext; **không phù hợp** khi muốn dùng cookie SESSION để giữ login |

Một ứng dụng có thể dùng Redis cho những mục đích khác và đồng thời chạy API Bearer token stateless. Tuy nhiên, **đừng chọn STATELESS rồi kỳ vọng SecurityContext từ session Redis tự xuất hiện ở request mới**.

### Những gì không được “chia sẻ” chỉ vì dùng Spring Session

- **SecurityContextHolder** của thread hiện tại; nó có vòng đời riêng theo request.
- Field của bean **singleton**, static map, cache **Caffeine/ConcurrentHashMap** cục bộ.
- Thông tin đang nằm trên stack, request attributes và các transaction đang xử lý.
- **SessionRegistryImpl** lưu trong RAM của một node nếu dùng trực tiếp.
- Rate limiter, lock, idempotency key hoặc dữ liệu giỏ hàng lưu bên ngoài HttpSession.
- File upload tạm, WebSocket connection, task đang chạy trong thread/executor cục bộ.

Spring Session chỉ chia sẻ **các dữ liệu thực sự được lưu qua SessionRepository**. Nếu một node vẫn ghi dữ liệu phiên vào static map, node còn lại không nhìn thấy chúng.

## 5. Ví dụ chạy thực tế: hai node Spring Boot dùng chung Redis

Ví dụ dùng **Java 17+**, **Spring Boot 3.5.x**, Servlet stack, **Spring Security form login** và **Spring Session Data Redis**. Spring Boot 3.5 có auto-configuration cho Spring Session khi đúng module hiện diện; với cấu hình này **không cần thêm @EnableRedisHttpSession**.

Chúng ta chạy **cùng một mã ứng dụng** ở hai tiến trình có hai cổng khác nhau. Mỗi tiến trình dùng cùng Redis tại localhost:6379, cùng namespace. Người dùng đăng nhập vào A, rồi truy cập node B bằng cookie được giữ trong cùng client.

### 5.1. Khởi tạo Gradle project

Tạo project Spring Boot có cấu trúc:

~~~text
session-shared-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/example/session/SharedSessionApplication.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'session-shared-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
}
~~~

Bốn dependency có vai trò khác nhau:

- **spring-boot-starter-web**: chạy Spring MVC trên Servlet container.
- **spring-boot-starter-security**: filter chain, form login, SecurityContext.
- **spring-boot-starter-data-redis**: client/connection factory cho Redis.
- **spring-session-data-redis**: SessionRepository Redis và tích hợp Servlet HttpSession.

Dùng quản lý phiên bản dependency của Spring Boot thay vì tự gán một version Spring Session không tương thích.

### 5.2. Cấu hình Redis và thời hạn session

**src/main/resources/application.properties**:

~~~properties
spring.data.redis.host=127.0.0.1
spring.data.redis.port=6379

spring.session.timeout=20m
spring.session.redis.namespace=spring:session:multi-node-demo
spring.session.redis.repository-type=default

server.port=8081
demo.node=A
~~~

**spring.session.timeout=20m** đặt inactivity timeout của session ở mức 20 phút trong ví dụ. Timeout tính theo việc truy cập session, không phải cam kết phiên tồn tại đúng 20 phút theo đồng hồ từ lần login đầu tiên. Nếu không khai báo spring.session.timeout, Spring Boot Servlet có thể dùng server.servlet.session.timeout.

**spring.session.redis.namespace** phải giống nhau ở A/B để chúng tra cứu chung dữ liệu phiên. Nếu nhiều ứng dụng không liên quan dùng chung Redis, nên cấp namespace riêng và không cho ứng dụng này vô tình đọc hoặc sửa phiên của ứng dụng kia.

**spring.session.redis.repository-type=default** chọn RedisSessionRepository theo cấu hình này; phần 7 giải thích khi nào chuyển sang indexed.

Ở production, không viết mật khẩu Redis vào repository. Hãy lấy cấu hình kết nối từ secret management/biến môi trường, hạn chế network, bật auth/TLS theo hạ tầng và giới hạn quyền Redis.

### 5.3. Java application hoàn chỉnh

Tạo file **src/main/java/example/session/SharedSessionApplication.java**:

~~~java
package example.session;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SharedSessionApplication {

    public static void main(String[] args) {
        SpringApplication.run(SharedSessionApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/node", "/csrf").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .requestCache(cache -> cache.disable());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(passwordEncoder.encode("demo-pass"))
                .roles("READER")
                .build()
        );
    }

    @RestController
    static class Api {
        private final String node;

        Api(Environment environment) {
            this.node = environment.getProperty("demo.node", "unknown");
        }

        record NodeInfo(String node) {}
        record CsrfInfo(String headerName, String token) {}
        record WhoAmI(String node, String username,
                      boolean sessionPresent) {}

        @GetMapping("/node")
        NodeInfo node() {
            return new NodeInfo(node);
        }

        @GetMapping("/csrf")
        CsrfInfo csrf(CsrfToken csrfToken) {
            return new CsrfInfo(
                csrfToken.getHeaderName(),
                csrfToken.getToken()
            );
        }

        @GetMapping("/")
        String home(Authentication authentication) {
            return "signed in: " + authentication.getName();
        }

        @GetMapping("/me")
        WhoAmI me(Authentication authentication,
                  HttpServletRequest request) {
            HttpSession session = request.getSession(false);
            return new WhoAmI(
                node,
                authentication.getName(),
                session != null
            );
        }
    }
}
~~~

**Tại sao lựa chọn code như vậy?**

- **formLogin** của Spring Security cung cấp trang GET /login và bộ lọc xử lý POST /login. Kết quả đăng nhập được lưu vào session theo cơ chế chuẩn, phù hợp demo chia sẻ session.
- **IF_REQUIRED** không buộc tạo session ở mọi request. Khi login hoặc CSRF cần phiên, Spring có thể tạo session.
- **/csrf** cho phép client lấy token cho POST login. Ví dụ giữ CSRF bật; body/URL đăng nhập phải dùng token cùng cookie phiên.
- **/node** công khai danh tính nút, giúp phân biệt request đến A hay B.
- **/me** được bảo vệ, lấy principal từ Authentication của request. Nếu B trả username đã đăng nhập trên A, ta có bằng chứng application B đã khôi phục authentication phù hợp.
- **request.getSession(false)** chỉ quan sát session, không tạo session mới trong endpoint /me.
- **requestCache.disable()** bỏ lưu URL bị từ chối để tự động redirect sau login, giúp luồng demo dễ dự đoán; đây là lựa chọn API, không phải điều kiện bắt buộc để Spring Session hoạt động.
- Người dùng **demo/demo-pass** chỉ phục vụ môi trường học. Trong production dùng kho danh tính, password encoder, MFA và quản lý secrets thích hợp.

**Không có bean SessionRepository thủ công** trong ví dụ vì Spring Boot tự cấu hình từ dependency và thuộc tính phù hợp. Nếu thêm @EnableRedisHttpSession, bạn chuyển sang kiểm soát cấu hình annotation và Boot auto-configuration có thể lùi lại; không trộn hai cách tùy tiện.

### 5.4. Khởi động Redis và hai node

Dùng Redis local đã có hoặc chạy container Redis dành riêng cho demo:

~~~bash
docker run --rm --name session-demo-redis \
  -p 127.0.0.1:6379:6379 redis:7-alpine
~~~

Chỉ publish port ở loopback khi thực hành; không mở một Redis không bảo vệ ra Internet.

Trong hai terminal riêng, từ thư mục project có Gradle wrapper:

**Terminal A:**

~~~bash
./gradlew bootRun --args='--server.port=8081 --demo.node=A'
~~~

**Terminal B:**

~~~bash
./gradlew bootRun --args='--server.port=8082 --demo.node=B'
~~~

Trên Windows PowerShell, thay **./gradlew** bằng **.\gradlew.bat** và dùng dấu ngoặc kép cho --args nếu cần. Hai tiến trình đều trỏ tới cùng Redis và namespace.

Kiểm tra hai endpoint không yêu cầu đăng nhập:

~~~bash
curl -sS http://localhost:8081/node
# {"node":"A"}

curl -sS http://localhost:8082/node
# {"node":"B"}
~~~

Hai JSON ở trên chỉ là kết quả kỳ vọng cho cấu hình demo, không phải log được thu từ một lần chạy thực tế.

### 5.5. Đăng nhập ở A, tiếp tục phiên tại B

Ví dụ dưới đây dùng **Bash/WSL/Git Bash, curl và Python 3** để đọc trường token trong JSON. Dùng cùng một file cookie qua tất cả request; tránh in hoặc chia sẻ nội dung file cookie.

**Bước 1. Lấy CSRF token tại A và lưu cookie session.**

~~~bash
csrf=$(curl -fsS -c session-cookies.txt \
  http://localhost:8081/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

test -n "$csrf"
~~~

Lần lấy token có thể tạo HttpSession trước khi đăng nhập. Cookie mặc định với Spring Session thường tên **SESSION**, không phải JSESSIONID.

**Bước 2. POST /login tại A với credential demo và CSRF.**

~~~bash
curl -i -b session-cookies.txt -c session-cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  --data-urlencode "username=demo" \
  --data-urlencode "password=demo-pass" \
  http://localhost:8081/login
~~~

Thông thường form login thành công trả **HTTP 302** tới trang mặc định hoặc saved-request target; requestCache đã tắt nên thường chuyển về **/**. Spring Security có thể xoay session ID để chống session fixation. Tùy container, Set-Cookie có thể xuất hiện trong response và file cookie phải được cập nhật.

**Bước 3. Dùng cookie vừa lưu để gọi node B.**

~~~bash
curl -sS -b session-cookies.txt http://localhost:8082/me
# {"node":"B","username":"demo","sessionPresent":true}
~~~

Nếu dữ liệu session được lưu chính xác và cả hai node dùng cùng Redis, B có thể trả JSON với **node B**, username đã đăng nhập **demo** và sessionPresent **true**. Đây là dấu hiệu cơ bản của việc **SecurityContext được phục hồi từ session dùng chung**.

**Bước 4. Quay lại A bằng đúng cookie.**

~~~bash
curl -sS -b session-cookies.txt http://localhost:8081/me
# {"node":"A","username":"demo","sessionPresent":true}
~~~

Hai request ở bước 3 và 4 có thể đến hai JVM khác nhau nhưng mang cùng phiên đăng nhập. JSON có thể khác thứ tự key tùy serializer; hãy so giá trị trường, không phụ thuộc thứ tự.

**Bước 5. Không gửi cookie thì không được thừa hưởng đăng nhập.**

~~~bash
curl -i http://localhost:8082/me
# HTTP/1.1 302 ... Location: /login (thường gặp với form login)
~~~

Vì ví dụ bật form login, request chưa xác thực thường **được chuyển hướng tới /login**. Không kỳ vọng mặc định phải là 401; status phụ thuộc authentication entry point của ứng dụng.

### 5.6. Kiểm tra logout từ một node có hiệu lực ở node kia

Lấy CSRF token mới ở B với cookie hiện tại, sau đó logout bằng POST:

~~~bash
csrf=$(curl -fsS -b session-cookies.txt -c session-cookies.txt \
  http://localhost:8082/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

curl -i -b session-cookies.txt -c session-cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  -X POST http://localhost:8082/logout
# Thường trả 302 tới /login?logout
~~~

Sau khi session được hủy, cùng cookie cũ không còn chứng minh Authentication. Nếu gửi yêu cầu **/me** tới A sau logout, ứng dụng sẽ xử lý như client chưa đăng nhập (thường redirect tới /login).

Lý do lấy token mới: Spring Security có thể xóa CSRF token cũ khi xác thực thành công. Không nên tái sử dụng token lấy trước login cho mọi POST tiếp theo.

### 5.7. Trường hợp lưu phiên cục bộ: cách so sánh

Dùng **một bản sao riêng của project demo**, bỏ hai dependency liên quan Redis và Spring Session, đồng thời bỏ các thuộc tính spring.session.*. Giữ Spring Web và Spring Security.

Chạy lại A/B dưới hai process, đăng nhập ở A và thử **/me** trên B bằng cookie của A:

- Với container session cục bộ, A có Authentication trong kho phiên của A.
- B không có session tương ứng; kết quả thường là redirect tới login (hoặc 401 nếu cấu hình API entry point).
- Cookie container lúc này thường là **JSESSIONID**.

Nếu load balancer dùng sticky session, request có thể luôn về A và lỗi tạm ẩn đi. Khi A ngừng hoạt động, client buộc chuyển nút và có thể mất trạng thái. Hành vi thực tế còn phụ thuộc một cơ chế replication/persistence riêng nếu Servlet container đã được cấu hình; không quy mọi hệ thống Tomcat thành “chỉ có RAM” bất kể cấu hình.

## 6. Cách Spring Session lưu dữ liệu và giới hạn consistency

### 6.1. SessionRepository không tự chia sẻ mọi loại state

Trong Spring Session, các thao tác HttpSession được chuyển qua repository. Điều này thường áp dụng cho:

- Session ID, creation time, last accessed time và max inactive interval.
- Các **session attributes** mà ứng dụng đặt bằng HttpSession.setAttribute.
- SecurityContext khi Spring Security dùng repository có khả năng lưu vào HttpSession.

Các singleton bean, static fields, ThreadLocal, local cache và WebSocket connections **không trở thành distributed state** chỉ vì session repository lưu ở Redis.

Ví dụ lỗi:

~~~java
// Minh họa CÁCH LÀM SAI trong ứng dụng nhiều node:
static final Map<String, Cart> cartsBySessionId =
    new ConcurrentHashMap<>();
~~~

Map trên là tài nguyên của từng JVM. Với hai node, Cart của A không tự xuất hiện ở B. Nếu muốn chia sẻ Cart, hãy chuyển nó sang kho nghiệp vụ phù hợp hoặc session attribute có kiểm soát kích thước/serialization, tùy nghiệp vụ và yêu cầu consistency.

### 6.2. Serialization và rolling deployment

Khi session được đưa khỏi JVM, server phải **serialize dữ liệu session**. Spring Session Redis mặc định có cơ chế Java serialization trong cấu hình thông dụng; có thể tùy chỉnh serializer, ví dụ JSON với Jackson và module Spring Security phù hợp.

Hệ quả:

- Session chứa class tùy biến phải có cấu trúc có thể serialize theo serializer đang dùng.
- Nếu phiên bản code A và B khác nhau trong rolling deployment, một session được ghi bởi A có thể không deserialize được trên B khi schema hoặc class thay đổi không tương thích.
- Không nhét entity JPA đang gắn persistence context, object graph lớn, file hoặc connection vào HttpSession.
- Không coi Java native serialization từ dữ liệu ngoài không tin cậy là an toàn; giới hạn type/nguồn, cập nhật thư viện và cấu hình serializer theo khuyến nghị.
- Đổi serializer là thay đổi dữ liệu có trạng thái; cần chiến lược migration/invalidation session, không đổi đột ngột giữa các node.

**Thực hành tốt:** lưu các thuộc tính phiên nhỏ, ổn định, ví dụ user ID, trạng thái workflow gọn. Dữ liệu nghiệp vụ lớn hoặc thay đổi thường xuyên nên ở một kho có mô hình concurrency rõ ràng; không mặc nhiên đưa toàn bộ vào session.

### 6.3. TTL và thời điểm xóa

Session timeout thường biểu diễn **thời gian không hoạt động tối đa**. Khi request truy cập session, last accessed time có thể được cập nhật và TTL tương ứng được duy trì theo repository.

Redis có cơ chế hết hạn key và Spring Session có các cơ chế hỗ trợ cleanup/event; **thời điểm Redis phát expired event không được bảo đảm chính xác bằng một đồng hồ tuyệt đối**. Do đó:

- Đừng dựa vào callback “session expired” đúng chính xác giây để thực thi nghiệp vụ có yêu cầu pháp lý/chính xác cao.
- Request đọc session đã hết hạn phải được xử lý là không còn phiên hợp lệ.
- Nếu cần thời hạn đăng nhập tối đa kể cả khi user liên tục hoạt động, triển khai **absolute session lifetime** riêng; inactivity TTL không thay thế yêu cầu đó.

### 6.4. Đồng thời ghi vào cùng một session

Nếu hai request đồng thời đến A và B, cả hai đọc cùng session rồi sửa một attribute, kết quả không tự động trở thành transaction tuần tự hoàn hảo:

~~~text
A đọc counter=5              B đọc counter=5
A ghi counter=6              B ghi counter=6
Kết quả cuối có thể là 6, không phải 7
~~~

Đây là **lost update**, không phải lỗi riêng Redis. Các chế độ **SaveMode** và **FlushMode** điều khiển trường nào được lưu và khi nào flush, nhưng không mặc nhiên cung cấp transaction logic cho mọi session attribute. Đối với bộ đếm, số dư, đặt chỗ hoặc thay đổi nghiệp vụ đồng thời, dùng database transaction, atomic Redis operation hoặc cơ chế concurrency phù hợp; **không dựa vào HttpSession như kho giao dịch**.

## 7. RedisSessionRepository và RedisIndexedSessionRepository

Spring Session Redis có hai kiểu repository thường gặp:

| Repository | Khả năng chính | Trường hợp thích hợp |
| --- | --- | --- |
| **RedisSessionRepository** | Lưu/đọc session theo session ID; không có bộ chỉ mục phụ mặc định | Chia sẻ phiên HTTP thông thường giữa nhiều node |
| **RedisIndexedSessionRepository** | Có thêm index hỗ trợ tìm session theo thuộc tính, ví dụ principal name, và hỗ trợ event/lifecycle | Liệt kê/thu hồi phiên theo user, đồng bộ chính sách concurrent sessions |

Trong Spring Boot 3.5 và Spring Session 3.5, có thể chọn:

~~~properties
# Mặc định: lưu session theo ID
spring.session.redis.repository-type=default
~~~

Hoặc:

~~~properties
# Có chỉ mục để tìm phiên theo principal
spring.session.redis.repository-type=indexed
~~~

**Không đổi sang indexed chỉ vì có hai node.** Với nhu cầu đăng nhập ở A rồi dùng session ở B, repository không index vẫn đủ cho tra cứu **theo session ID**. Chỉ dùng indexed khi cần tìm tất cả session của user, quản lý giới hạn phiên hoặc xử lý sự kiện lifecycle theo yêu cầu.

### Giới hạn index/event trên Redis Cluster

Spring Session ghi nhận rằng **RedisIndexedSessionRepository** có hạn chế khi subscribe keyspace events trong Redis Cluster: nếu chỉ nhận event trên một node Redis được chọn, các sự kiện phát sinh ở node khác có thể không được thấy, làm chỉ mục phiên hết hạn không được dọn như mong đợi.

Vì vậy nếu hệ thống chạy Redis Cluster và yêu cầu thu hồi/giới hạn phiên chính xác, phải kiểm tra cụ thể mô hình event propagation, Spring Session version và cơ chế cleanup/repair. Không khẳng định “bật indexed là mọi event được nhận toàn cluster”.

### SessionRegistry cho concurrent sessions

Spring Security cung cấp **SessionRegistryImpl** trong bộ nhớ. Nếu mỗi app node có một registry riêng, cơ chế đếm phiên đồng thời có thể chỉ biết những phiên ở node đó. Ví dụ giới hạn “một phiên trên mỗi tài khoản” có thể bị vượt qua khi người dùng đăng nhập lần lượt ở A và B.

Spring Session có **SpringSessionBackedSessionRegistry**, dùng **FindByIndexNameSessionRepository** để truy vấn session theo principal trên kho chung.

Mẫu cấu hình **minh họa**, cần có bean repository kiểu indexed:

~~~java
// Trong lớp @Configuration của ứng dụng phù hợp:
@Bean
<S extends Session> SpringSessionBackedSessionRegistry<S> sessionRegistry(
        FindByIndexNameSessionRepository<S> repository) {
    return new SpringSessionBackedSessionRegistry<>(repository);
}

// Trong SecurityFilterChain đã có sessionRegistry:
http.sessionManagement(session -> session
    .maximumSessions(1)
    .sessionRegistry(sessionRegistry)
);
~~~

Đây là **đoạn cấu hình trích**, không phải class Java độc lập: cần import **org.springframework.session.Session**, **FindByIndexNameSessionRepository**, **SpringSessionBackedSessionRegistry**, cấu hình HttpSecurity và bean matching trong application context. Thực tế thường tách bean registry và truyền vào SecurityFilterChain, đồng thời đảm bảo indexed repository, principal index và handling session expiration.

**Giới hạn quan trọng:** SpringSessionBackedSessionRegistry không hỗ trợ đầy đủ mọi phương thức như registry cục bộ; chẳng hạn **getAllPrincipals()** không hỗ trợ theo tài liệu Spring Session. Nếu ứng dụng tự gọi API đó để lập danh sách user đang online, cần thiết kế giải pháp khác.

Nếu viết **custom JSON login/controller** thay cho form login, chỉ cấu hình maximumSessions có thể chưa đủ: authentication mechanism phải gọi đúng SessionAuthenticationStrategy và lưu context phù hợp. Ngoài ra, session expiration event/registry lifecycle, bảo vệ fixation và xử lý session bị từ chối cần test trong cụm nhiều node.

## 8. Redis là dependency quan trọng của ứng dụng: vận hành thế nào?

Chuyển session sang Redis giúp node ứng dụng stateless về **lưu trữ session**, nhưng lại tạo dependency chung. Mọi request cần session có thể phải truy cập Redis.

### 8.1. Redis outage

Khi Redis mất kết nối hoặc timeout:

- Request yêu cầu đọc session có thể không khôi phục được Authentication.
- Ứng dụng có thể trả lỗi 5xx/503, timeout hoặc behavior khác tùy error handling; **không hứa một mã HTTP cố định**.
- Nếu logic tự động quay lại dùng local session khi Redis hỏng mà không thiết kế rõ, có thể tạo hai nguồn trạng thái và phát sinh lỗi bảo mật/nhất quán.
- Không nên tự coi request là anonymous và cho đi tiếp vào endpoint nhạy cảm nếu không chứng minh được danh tính. Fail closed theo yêu cầu bảo mật.

Cần thiết lập timeout kết nối/đọc, retry có giới hạn, circuit breaker khi phù hợp, health/readiness kiểm tra và cơ chế xử lý sự cố. Retry bừa bãi có thể làm Redis quá tải thêm.

### 8.2. Availability, durability và eviction

Redis chạy đơn lẻ không phải kho phiên chịu lỗi tự động. Có thể cân nhắc replication/Sentinel/managed Redis/Cluster phù hợp. Xác định kỳ vọng sau failover:

- Nếu Redis failover nhưng dữ liệu chưa replicate, có thể mất một số session.
- Eviction do thiếu bộ nhớ có thể xóa key session sớm hơn inactivity timeout.
- Backup/persistence giúp khôi phục nhưng phải xét mức độ nhạy cảm của session data; restore cũ có thể tạo trạng thái session không mong muốn.
- Nếu chấp nhận buộc người dùng đăng nhập lại khi cache session mất, hãy tuyên bố rõ mục tiêu SLA thay vì giả định zero-loss.

Session lưu dữ liệu bảo mật; nên quản lý ACL, TLS, network segmentation, rotation, secret vault, namespace và không mở cổng Redis công khai. Đừng log cookie SESSION, session ID, SecurityContext hoặc dữ liệu credential.

### 8.3. Performance và chi phí

Với kho chung, mỗi request có session có thể phát sinh thao tác đọc/ghi và serialize. Số lần request, kích thước session, thời gian sống, số user đồng thời và độ trễ mạng đều ảnh hưởng tải.

Các chỉ số hữu ích:

- Redis latency/p99, connection pool saturation, error/timeout rate.
- Số session đang tồn tại và tăng trưởng dữ liệu theo namespace.
- Kích thước trung bình/p95/p99 của session attributes.
- CPU serialize/deserialize, lỗi deserialize, deserialization khi rollout.
- Số lần login lại đột ngột, logout bất thường, session không tìm thấy.
- Redis memory fragmentation, eviction count, key expiration, replica lag.

Tối ưu bằng cách giảm session payload, tránh ghi lại attribute lớn mỗi request, phân tách dữ liệu nghiệp vụ khỏi session, cân nhắc save/flush mode theo workload và benchmark. Một bộ nhớ Redis rất lớn hoặc config replication chưa đúng có thể trở thành điểm nghẽn thay cho JVM.

## 9. Cookie, CSRF, session fixation và những điểm bảo mật cần giữ

**Cookie:** Spring Session dùng cookie mang session ID. Trên môi trường HTTPS, cấu hình **Secure**, **HttpOnly**, **SameSite**, domain/path và proxy forwarding phù hợp. Không đặt token/session ID trong URL hay log. Nếu dùng nhiều host/subdomain, kiểm tra chính sách cookie thực tế; đừng mở domain quá rộng chỉ để “cả hai node nhận cookie”.

**Session fixation:** sau login, Spring Security nên đổi session ID khi có session trước đó. Dù session data ở Redis, việc giữ nguyên ID do attacker biết trước vẫn nguy hiểm; Spring Session không thay thế session fixation protection.

**CSRF:** cookie thường được browser tự gửi, nên vẫn phải bảo vệ request thay đổi trạng thái. Ví dụ giữ CSRF cho POST /login và POST /logout. API dùng Bearer header có threat model khác; **không suy ra vô hiệu hóa CSRF chỉ vì đang dùng Redis hay chia nhiều node**.

**Logout:** hủy session đã đăng nhập qua đúng SecurityContextRepository/HttpSession sẽ làm cookie cũ không còn đọc được Authentication; cần kiểm tra behavior cross-node. Nếu user login nhiều thiết bị với nhiều session khác nhau, hủy **một** session không mặc nhiên hủy tất cả.

**Quyền và trạng thái user:** session có thể giữ Authentication đã xác thực trước khi role/account thay đổi. Nếu quyền bị thu hồi, bạn cần chính sách refresh/invalidation; Spring Session không tự cập nhật mọi SecurityContext cũ khi dữ liệu user đổi.

**Session ID và principal:** không để client chọn account/role thông qua session attribute tự đặt. Dữ liệu Authentication phải đến từ luồng xác thực đáng tin, không sao chép JSON field do client gửi vào SecurityContext.

## 10. Kiểm thử hành vi nhiều node và sự cố

Một bài test đúng phải gửi request tới **hai instance riêng biệt**; cùng một JVM với hai controller không chứng minh session sharing.

| Kịch bản | Local HttpSession không replication | Spring Session + Redis đúng cấu hình |
| --- | --- | --- |
| Login tại A, request cookie tới A | Thường thành công | Thành công |
| Login tại A, cookie tới B | B có thể không biết session | B đọc session từ Redis và có thể khôi phục Authentication |
| Restart A, request cookie tới B | Phiên A có thể mất | Thường vẫn dùng được nếu session Redis còn hợp lệ |
| Session hết hạn | Request không còn authenticated | Request không còn authenticated |
| B dùng namespace khác A | Không áp dụng | B không tìm được session A |
| B không deserialize được session của A | Không chia sẻ trực tiếp object | Có thể lỗi khôi phục session/Authentication |
| Redis mất kết nối | Local session có thể vẫn dùng trong node | Request cần Redis có thể lỗi hoặc không đọc được session |
| Đổi authority tại DB sau login | Context cũ có thể giữ quyền cũ | Context cũ cũng có thể giữ quyền cũ, phải có policy thu hồi |
| Concurrent login ở A/B, registry cục bộ | Giới hạn phiên có thể không nhất quán | Chỉ nhất quán nếu có registry/index và policy phù hợp |

### Kịch bản nâng cao nên thử

1. **Luân phiên A-B-A-B** sau login để xem session liên tục ở nhiều node.
2. **Khởi động lại A**, giữ Redis và B hoạt động, kiểm tra B vẫn đọc được Authentication.
3. **Cho session hết hạn** bằng timeout ngắn trong môi trường test, xác minh cả hai node đều coi cookie cũ không còn hợp lệ.
4. **Đổi namespace trên B** tạm thời trong môi trường test; request cùng cookie phải không tìm được context. Khôi phục namespace trước khi test tiếp.
5. **Dừng Redis** trong môi trường test, quan sát status, log có kiểm soát và thời gian hồi phục; không diễn dịch 500/503 cứng nếu error handling khác.
6. **Rolling deployment khác phiên bản** với session attribute tùy chỉnh, xác minh backward/forward compatibility của serializer.
7. **Concurrent writes** cùng session từ A và B, kiểm tra mất update và phương án atomic storage.
8. **Concurrent session control** với login ở A và B, nếu ứng dụng thực sự có chính sách maximumSessions.
9. **Logout ở B, dùng lại cookie trên A**, xác minh phiên đã bị thu hồi trên kho chung.
10. **Cookie mismatch**: khác path/domain/SameSite/Secure/proxy scheme, kiểm tra browser có gửi cookie tới đúng host không.

**Gợi ý kiểm thử tự động:** ứng dụng có thể dùng **Testcontainers Redis** hoặc Redis test service dùng chung cho hai Spring Boot process/container; cho các request đi đến hai base URL khác nhau, giữ một HTTP cookie jar. Đừng chỉ mock SessionRepository rồi suy ra failover thực sự hoạt động.

## 11. Lỗi thường gặp và cách chẩn đoán

### 11.1. Có Redis nhưng request node B vẫn bị yêu cầu login

Kiểm tra theo thứ tự:

1. B có nhận **cookie SESSION** trong request không? Domain/path/proxy/HTTPS có chặn cookie?
2. A và B có cùng Redis host, database, namespace và session serializer không?
3. Redis có session ID tương ứng, và nó còn hạn hay đã bị xóa?
4. Node B có **springSessionRepositoryFilter** được cấu hình thật sự, hay chỉ có dependency Redis client?
5. Spring Security ở B có dùng HttpSession SecurityContextRepository và policy stateful phù hợp?
6. Login ở A có **lưu SecurityContext** hay chỉ set holder tạm trong request?
7. Node B có đọc được class serialized của SecurityContext/principal từ A không?
8. Có sự khác biệt Spring Security filter chain giữa hai node không?

Đừng bắt đầu bằng cách tắt CSRF hoặc đổi role nếu chưa xác minh session/cookie.

### 11.2. Login lần đầu được, sau deploy bị logout

Xem session đang ở RAM hay Redis, Redis có bị restart/evict hay session data không deserialize được bởi code mới; kiểm tra TTL, Redis persistence/replication và thay đổi cookie domain/name. Với bản nâng cấp serialization không tương thích, có thể cần chiến lược giữ compatibility hoặc invalidation session có kiểm soát.

### 11.3. Đã cấu hình maximumSessions(1) nhưng user login được ở hai node

Rất có thể **SessionRegistryImpl** vẫn nằm cục bộ; các lần login ở hai node không thấy nhau. Với Spring Session cần xem **indexed session repository**, **SpringSessionBackedSessionRegistry**, các index chính xác, session event/lifecycle và cách cơ chế login gọi session strategy. Thử đăng nhập cross-node trong test thực tế.

### 11.4. Redis memory tăng nhanh

Kiểm tra kích thước session, số session, TTL, idle session chưa cleanup, dữ liệu lớn hoặc object graph dư thừa trong attributes, index/event cleanup và eviction. Không xóa toàn bộ Redis key theo wildcard trong production để “chữa nhanh”; cần chẩn đoán có phân vùng namespace và tác động các ứng dụng khác.

### 11.5. Spring Session đã hoạt động nhưng dữ liệu nghiệp vụ vẫn biến mất

Xem dữ liệu đó có thực sự nằm trong HttpSession qua repository hay đang ở singleton/static map/caffeine/local file. Spring Session không chia sẻ mọi biến của JVM. Di chuyển state cần chia sẻ sang kho dữ liệu được thiết kế cho loại state đó.

### 11.6. Người dùng đăng xuất ở một node nhưng node kia vẫn cho truy cập

Kiểm tra cookie thực sự dùng, cache Authentication/custom token, session invalidation, SecurityContextRepository, TTL, replica lag và nguồn auth độc lập khác như remember-me/Bearer. Một hệ thống có thể vừa có session vừa có Bearer token: hủy session không tự thu hồi mọi token khác.

## 12. Quyết định kiến trúc: khi nào cần Spring Session?

**Nên đánh giá Spring Session** khi:

- Ứng dụng dùng session login/cookie để duy trì Authentication và cần scale nhiều instance.
- Muốn failover, rolling deployment ít gây mất phiên hơn.
- Cần dùng chung các thuộc tính HttpSession được kiểm soát giữa các node.
- Có năng lực vận hành một store chung đủ ổn định, an toàn và đạt tải.

**Có thể không cần cho Authentication** khi:

- API dùng Bearer token/API key được xác minh trên **mỗi request**, không dựa vào HttpSession.
- Không có dữ liệu business nào bắt buộc lưu trong HttpSession.
- Ứng dụng là một instance và không có yêu cầu duy trì phiên qua restart/failover, chấp nhận mất session theo đặc tính hệ thống.

Dù chọn giải pháp nào, hãy phân biệt ba vấn đề:

1. **Xác thực:** ai đang gọi và bằng chứng có hợp lệ không?
2. **Lưu trạng thái phiên:** giữ kết quả đăng nhập/dữ liệu phiên ở đâu để request sau đọc được?
3. **Phân quyền và vòng đời:** quyền hiện hành, logout, thu hồi, concurrency, hết hạn và audit thực hiện ra sao?

Spring Session giải quyết phần lưu session giữa các nút và cung cấp tích hợp quản lý phiên. Nó không tự hoàn tất toàn bộ xác thực, phân quyền, dữ liệu nghiệp vụ phân tán hay high availability của kho session.

## 13. Câu hỏi tự kiểm tra

**1.** Người dùng login vào node A, browser gửi lại cookie khi request đến B, nhưng B yêu cầu đăng nhập. Vì sao khi dùng local HttpSession?

**Đáp án:** Cookie chỉ chứa ID; session tương ứng nằm trong kho của A. B không tự có dữ liệu phiên A nếu không cấu hình replication/shared store.

**2.** Sticky session có bảo đảm giữ login khi A chết không?

**Đáp án:** Không. Sticky routing chỉ ưu tiên quay lại A khi A còn hoạt động; nó không tự sao chép dữ liệu session từ A sang B.

**3.** Spring Session + Redis tự làm cho SecurityContextHolder của node A xuất hiện trong thread của node B?

**Đáp án:** Không. Mỗi request có SecurityContextHolder riêng. B khôi phục SecurityContext đã **được lưu trong HttpSession** qua repository dùng chung.

**4.** Cookie tên SESSION và JSESSIONID khác nhau thế nào?

**Đáp án:** Cả hai có thể chứa định danh phiên. Servlet container thường dùng JSESSIONID; Spring Session với DefaultCookieSerializer mặc định dùng SESSION. Tên có thể cấu hình lại.

**5.** Chỉ cần hai node cùng có dependency spring-session-data-redis là đủ chưa?

**Đáp án:** Chưa. Cần cùng Redis/namespace, cùng cookie policy, session serializer và cơ chế SecurityContext phù hợp, đồng thời xác minh filter đã được đăng ký.

**6.** Khi nào dùng RedisIndexedSessionRepository?

**Đáp án:** Khi cần index/tìm session theo principal, event hoặc quản lý phiên trên nhiều node; chia sẻ session theo ID thường chỉ cần RedisSessionRepository. Với Redis Cluster phải xét hạn chế event/cleanup.

**7.** Vì sao SessionRegistryImpl có thể cho phép một user login ở hai node dù đặt maximumSessions(1)?

**Đáp án:** Nếu registry nằm trong bộ nhớ cục bộ, mỗi node chỉ biết một phần phiên. Cần registry liên kết với kho session dùng chung và cấu hình lifecycle tương ứng.

**8.** A và B cùng Redis nhưng khác namespace. Có dùng chung login session không?

**Đáp án:** Không. B tra cứu key trong namespace khác nên không tìm được dữ liệu phiên do A lưu.

**9.** Với một REST API dùng JWT stateless, có bắt buộc triển khai Spring Session vì hệ thống chạy nhiều pod?

**Đáp án:** Không. Nếu Authentication được xác minh độc lập qua token mỗi request và không cần HttpSession, Spring Session không phải điều kiện để scale pod.

**10.** Redis down thì nên tự động chấp nhận request như người dùng đã đăng nhập gần đây?

**Đáp án:** Không. Không xác minh được Authentication từ session thì không được mở quyền tùy tiện; xử lý lỗi theo chính sách fail-closed và phục hồi dịch vụ.

## Tài liệu chính thức để đọc thêm

- [Spring Boot 3.5 — Spring Session auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-session.html)
- [Spring Session 3.5 — Redis configurations, indexed repository, events, namespace](https://docs.spring.io/spring-session/reference/3.5/configuration/redis.html)
- [Spring Session — Spring Boot + Redis guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
- [Spring Session — HttpSession integration](https://docs.spring.io/spring-session/reference/httpsession.html)
- [Spring Session — Common configurations and cookie serializer](https://docs.spring.io/spring-session/reference/configuration/common.html)
- [Spring Session — Spring Security integration, distributed session registry](https://docs.spring.io/spring-session/reference/spring-security.html)
- [Spring Security 6.5 — Authentication persistence and session management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — CSRF token and servlet integration](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
