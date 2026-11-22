# Spring Session cho nhiều nút và giới hạn của kho phiên cục bộ

## Mục tiêu bài học

Trong ứng dụng Spring Security Servlet, form login thường gắn với **HTTP session**: sau khi xác thực thành công, người dùng mang một session cookie qua các request tiếp theo và server có thể khôi phục SecurityContext để phân quyền. Khi ứng dụng chạy trên một JVM, lưu phiên trong bộ nhớ của Servlet container có thể đủ dùng. Nhưng khi có **nhiều node** sau load balancer, session chỉ nằm ở node-A không tự xuất hiện ở node-B.

**Spring Session** cung cấp API và cơ chế thay thế cách lưu HttpSession bằng SessionRepository, có thể dùng Redis hoặc JDBC. Nhiều node dùng chung repository sẽ đọc được dữ liệu phiên của nhau. Tuy nhiên đây không phải phép màu: khả năng sẵn sàng của Redis/DB, serializer, cookie, timeout, session fixation, các cập nhật đồng thời và thu hồi quyền vẫn cần được thiết kế và kiểm thử.

Sau bài này, bạn có thể:

1. Mô tả HttpSession, session ID, cookie và SecurityContext trong Spring Security Servlet.
2. Nêu giới hạn của session in-memory ở từng node và giới hạn của load-balancer sticky session.
3. Giải thích SessionRepositoryFilter, SessionRepository, cơ chế khôi phục SecurityContext từ session dùng chung.
4. Cấu hình ví dụ Spring Boot 3.x, Spring Security 6.x, Java 17+ và Redis; chạy hai instance trên hai cổng.
5. Kiểm chứng một lần login trên A vẫn cho phép truy cập phiên xác thực từ B, kể cả khi A bị dừng.
6. So sánh Redis, JDBC, local memory, affinity và mô hình stateless API.
7. Xử lý các tình huống lỗi về TTL, cookie, Redis outage, serialization, rolling deploy và session revocation.
8. Xây checklist rollout an toàn với kiểm thử cross-node, quan sát và bảo vệ dữ liệu phiên.

Phạm vi: **Servlet stack**, không phải WebFlux. Ví dụ dùng form login dựa trên session, không phải JWT. Những mật khẩu/cấu hình Redis local trong bài chỉ dành cho máy phát triển, không dùng production.

## 1. HttpSession giữ trạng thái qua các HTTP request như thế nào?

HTTP là giao thức request/response. Server không tự biết hai request của browser là cùng người dùng nếu không có cơ chế nhận diện. Với ứng dụng session-based, server phát hành một **session ID khó đoán**. Browser giữ ID trong cookie, gửi lại trên request sau. Server tra session tương ứng rồi phục hồi thông tin đăng nhập hoặc dữ liệu ứng dụng.

~~~text
Browser                                   Server Spring Security
   | GET /private                                  |
   |---------------------------------------------->|
   | chưa authenticated => 302 /login              |
   |<----------------------------------------------|
   | GET /login, rồi POST /login + CSRF token       |
   |---------------------------------------------->|
   | AuthenticationManager xác minh credentials    |
   | SecurityContext được lưu qua HttpSession      |
   | Set-Cookie: SESSION=<opaque-id> (ví dụ)        |
   |<----------------------------------------------|
   | GET /private + Cookie: SESSION=<opaque-id>     |
   |---------------------------------------------->|
   | server tìm session và khôi phục Authentication |
   | kiểm tra authorization -> response            |
   |<----------------------------------------------|
~~~

Tên cookie không bất biến: Servlet container mặc định thường dùng JSESSIONID; Spring Session dùng DefaultCookieSerializer thường có tên SESSION. **Kiểm tra Set-Cookie thực tế**, đừng hardcode tên rồi suy đoán. Cookie thường chỉ mang ID mờ, **không** chứa toàn bộ SecurityContext hoặc role. Về mặt bảo mật, ID này vẫn là bearer credential vì người nắm ID hợp lệ có thể thử tái sử dụng phiên.

| Khái niệm | Trách nhiệm |
| --- | --- |
| Cookie phiên | Browser lưu và gửi session ID theo domain/path/Secure/HttpOnly/SameSite |
| HttpSession | API Servlet để đọc/ghi attributes, invalidate session, kiểm tra thời gian sống |
| SecurityContext | Dữ liệu Authentication mà Spring Security dùng khi phân quyền |
| SecurityContextRepository | Cách Spring Security nạp/lưu SecurityContext theo request lifecycle |
| SessionRepository | Cơ chế Spring Session lưu, đọc, tạo, xóa phiên độc lập với bộ nhớ container |
| Redis/JDBC | Kho dữ liệu thực tế để nhiều JVM chia sẻ phiên |

**SecurityContextRepository không đồng nghĩa SessionRepository**. Cái thứ nhất lo ngữ cảnh bảo mật; cái thứ hai lo HttpSession. Khi SecurityContext được lưu trong HttpSession, chúng phối hợp với nhau.

Trong Spring Security 6, nếu tự viết filter xác thực thay formLogin chuẩn, không phải cứ đặt Authentication vào SecurityContextHolder là nó tự sống qua request. Cần lưu context qua SecurityContextRepository theo contract của version đang dùng. Form login do Spring Security cung cấp xử lý các bước lưu phù hợp.

## 2. Vì sao kho phiên local gây lỗi khi scale out?

Giả sử load balancer chia request cho hai JVM, mỗi JVM có session manager trong bộ nhớ:

~~~text
                        Load Balancer
                       /             \
                  node-A             node-B
                  :8081              :8082
              session map A       session map B

POST /login  -> A: tạo session XYZ trong map A
GET /account -> B: không có XYZ trong map B
                 => xem request như chưa đăng nhập
~~~

Cả hai node có thể dùng cùng database user và password encoder, nhưng đó không đồng nghĩa **session map được chia sẻ**. Người dùng có thể gặp redirect về /login ngay sau khi đã đăng nhập thành công, tùy node xử lý request tiếp theo.

Những giới hạn điển hình:

- **Không chia sẻ dữ liệu mặc định:** một session được tạo trên A không tự có trên B.
- **Mất session khi process chết:** JVM restart, container bị hủy hoặc rolling deploy có thể khiến phiên đang lưu trong heap biến mất.
- **Failover không phục hồi phiên:** khi A mất và LB chuyển sang B, B có thể không nhận diện session ID cũ.
- **Memory pressure:** attributes lớn, idle timeout quá dài hoặc rò rỉ session làm tăng heap/GC/OutOfMemoryError.
- **Quản lý logout phân tán khó:** nếu mỗi node giữ một bản dữ liệu riêng, xóa ở A không đảm bảo phiên ở B cũng được xóa.
- **Scale-out phụ thuộc routing:** sự đúng đắn của luồng login trở nên phụ thuộc vào load balancer.

Có Servlet container hỗ trợ session replication riêng, nhưng **không được mặc định giả định** Tomcat/Jetty đã bật cơ chế đó. Replication cũng có chi phí truyền dữ liệu, serialization và nhất quán; phải xem container/topology thực tế.

### Sticky session giúp gì?

Sticky session, còn gọi là session affinity, cho LB ưu tiên đưa những request của cùng client về một node:

~~~text
Browser session XYZ --> Load Balancer --> luôn về A khi A còn khỏe
~~~

Giải pháp này có thể giảm login-loop trong tình huống bình thường, nhưng **không sao chép dữ liệu của A sang B**. Khi A bị lỗi, cập nhật hoặc bị scale down, phiên có thể mất. Nó còn gây lệch tải nếu nhiều user bám vào một node quá lâu. Vì vậy sticky session không tương đương shared session store và không tự bảo đảm failover.

Spring Session không bắt buộc phải bỏ affinity: bạn vẫn có thể duy trì routing preference vì hiệu năng. Nhưng khi đã chọn shared store, **tính đúng đắn** của phiên không nên chỉ dựa vào việc mọi request luôn tới node ban đầu.

## 3. Kiến trúc Spring Session trên Servlet

Spring Session thay/bao HttpSession qua một filter của Servlet để code phía trên vẫn dùng API quen thuộc, trong khi dữ liệu được lưu ở kho ngoài tiến trình.

~~~text
                         Load Balancer
                          /           \
                       node-A         node-B
                         |              |
              Spring Session       Spring Session
              + Spring Security   + Spring Security
                         \              /
                            Redis/JDBC
                       shared SessionRepository
~~~

Luồng trên một node:

~~~text
Servlet container
    |
springSessionRepositoryFilter
    |-- bọc HttpServletRequest/HttpServletResponse
    |-- HttpSession được phục vụ bởi SessionRepository
    |
springSecurityFilterChain / FilterChainProxy
    |-- SecurityContextRepository nạp SecurityContext
    |-- formLogin / CSRF / authorization xử lý request
    |
DispatcherServlet, controller, application service
    |
SessionRepository -> Redis/JDBC
~~~

Tên filter nổi bật là **SessionRepositoryFilter**. Trong tích hợp Spring Boot đúng cách, Spring Session được đăng ký để các filter Spring Security sử dụng session wrapper tương ứng. Đừng tự thêm một filter SessionRepositoryFilter thứ hai bằng tay vào SecurityFilterChain rồi nghĩ rằng sẽ “chắc chắn hơn”: đăng ký trùng có thể gây lỗi lifecycle.

Về chức năng:

1. Khi cần session, Spring Session tạo object đại diện một phiên và lưu vào SessionRepository theo cấu hình.
2. Trong form login, Authentication được xác minh bởi Spring Security, SecurityContext được lưu theo quy trình phù hợp.
3. Ở request sau trên node khác, cookie chứa ID dẫn đến một entry phiên trong Redis/JDBC; Spring Security đọc lại SecurityContext và kiểm tra quyền.
4. Sau logout/timeout/invalidate, session không còn được chấp nhận theo quy tắc của repository.

Spring Session **không thay AuthenticationManager, AuthenticationProvider hoặc PasswordEncoder**. Nó không biết user/password đúng sai; nó chỉ cho phép sử dụng HttpSession qua nhiều node.

Spring Session cũng không tự đồng bộ user database, roles, chính sách đổi mật khẩu, session registry tùy biến, token revocation hoặc thông tin cấu hình khác giữa các ứng dụng.

## 4. Một ví dụ chạy được: Spring Boot + Spring Security + Redis

Ta triển khai một Spring Boot 3.3.x app sử dụng Java 17+, formLogin mặc định và Spring Session Data Redis. Tạo hai JVM độc lập:

- Node A chạy cổng 8081, app.node-id=node-a.
- Node B chạy cổng 8082, app.node-id=node-b.
- Cả hai kết nối cùng Redis tại localhost:6379, cùng namespace demo:sessions.
- Người dùng đăng nhập một lần tại node A rồi gọi GET /me tại node B mà không đăng nhập lại.

Cần JDK 17+, Gradle wrapper trong project, Docker hoặc Redis local tương thích. Mã dưới đây đầy đủ cho những file được liệt kê; Spring Boot starter xử lý các dependency của security và MVC.

### 4.1. Cấu trúc project

~~~text
session-cluster-demo/
  settings.gradle
  build.gradle
  compose.yaml
  gradlew / gradlew.bat    (Gradle wrapper nếu được tạo)
  src/main/java/dev/example/cluster/
    SessionClusterApplication.java
    SecurityConfig.java
    SessionController.java
  src/main/resources/
    application.yml
~~~

settings.gradle:

~~~groovy
rootProject.name = 'session-cluster-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Nếu dùng phiên bản Boot khác, hãy để dependency management của Boot chọn phiên bản Spring Security/Spring Session đồng bộ. Không tự trộn các artifact Spring Session/Security khác major version. Để chạy bằng ./gradlew, project cần có Gradle Wrapper; có thể tạo dự án ban đầu bằng Spring Initializr hoặc Gradle phù hợp.

### 4.2. Redis local chỉ để học tập

compose.yaml:

~~~yaml
services:
  redis:
    image: redis:7.4-alpine
    ports:
      - "127.0.0.1:6379:6379"
~~~

Chạy:

~~~bash
docker compose up -d
docker compose ps
~~~

Đây là Redis local không có authentication, bind cổng host loopback. **Không triển khai cấu hình không có auth/TLS và không có HA như vậy ra Internet/production.** Khi chạy nhiều container trong cùng Docker network hoặc Kubernetes, host Redis thường phải là service name phù hợp, không phải localhost của mỗi container.

### 4.3. Lớp main

Tệp src/main/java/dev/example/cluster/SessionClusterApplication.java:

~~~java
package dev.example.cluster;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionClusterApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionClusterApplication.class, args);
    }
}
~~~

### 4.4. Spring Security stateful form login

Tệp src/main/java/dev/example/cluster/SecurityConfig.java:

~~~java
package dev.example.cluster;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("local-lab-password"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().authenticated())
                .formLogin(withDefaults())
                .logout(withDefaults())
                .build();
    }
}
~~~

Đoạn code bật formLogin với login page được framework tạo và POST /login theo cấu hình mặc định. /public được permitAll để kiểm tra node; /me yêu cầu Authentication. Không dùng SessionCreationPolicy.STATELESS, vì bài muốn giữ SecurityContext qua HttpSession.

InMemoryUserDetailsManager ở đây tạo user demo giống nhau trên hai node. Đây **không** là shared identity store: đổi vai trò/mật khẩu trên node-A không tự làm user store của B thay đổi. Trong production nên dùng nguồn user/identity nhất quán, qua database hoặc dịch vụ nhận dạng phù hợp. Spring Session chỉ xử lý phiên, không đồng bộ InMemoryUserDetailsManager.

Mật khẩu mẫu chỉ dùng local. Không hardcode thông tin xác thực production vào source code.

### 4.5. Controller xác minh đang ở node nào

Tệp src/main/java/dev/example/cluster/SessionController.java:

~~~java
package dev.example.cluster;

import java.util.Map;

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

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of(
                "message", "PUBLIC",
                "node", environment.getProperty("app.node-id", "unknown"));
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of(
                "user", authentication.getName(),
                "node", environment.getProperty("app.node-id", "unknown"));
    }
}
~~~

Không gửi session ID, raw Cookie header hoặc toàn bộ Authentication object về client. Node-id chỉ để kiểm chứng route trong demo, không bắt buộc public hóa ở hệ thống thật.

### 4.6. Cấu hình Redis SessionRepository

Tệp src/main/resources/application.yml:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    redis:
      namespace: demo:sessions

server:
  servlet:
    session:
      timeout: 30m
~~~

Hai node cần trỏ **cùng Redis và cùng namespace**. Nếu A dùng namespace demo:sessions còn B dùng demo:other, chúng không cùng kho phiên logic. Không dùng chung namespace giữa các ứng dụng khác nhau nếu chúng không được thiết kế để chia sẻ dữ liệu, serializer và chính sách cookie.

Spring Boot với dependency Spring Session Data Redis phù hợp có thể tự cấu hình SessionRepositoryFilter và repository. Ví dụ không thêm thủ công @EnableRedisHttpSession hoặc một Spring Session filter khác để tránh chồng cấu hình.

server.servlet.session.timeout là cấu hình timeout phiên cho môi trường Servlet; khi triển khai hãy xác nhận giá trị maxInactiveInterval và TTL thực tế của Spring Session version đang chạy. **Cookie lifetime khác session timeout.** Khi thay cơ chế bảo vệ cookie, cần kiểm tra Set-Cookie của response thật.

### 4.7. Chạy hai ứng dụng

Trong hai terminal riêng:

Node A:

~~~bash
./gradlew bootRun --args="--server.port=8081 --app.node-id=node-a"
~~~

Node B:

~~~bash
./gradlew bootRun --args="--server.port=8082 --app.node-id=node-b"
~~~

Với Windows PowerShell, dùng .\gradlew.bat và giữ đối số tương ứng. Cần đảm bảo cả hai tiến trình đều khởi động thành công và kết nối Redis local.

Thử:

~~~bash
curl -i http://localhost:8081/public
curl -i http://localhost:8082/public
~~~

Body hai HTTP response riêng thường có dữ liệu tương đương:

~~~json
{"message":"PUBLIC","node":"node-a"}
~~~

~~~json
{"message":"PUBLIC","node":"node-b"}
~~~

Đây là **body mẫu theo logic chương trình**, không cam kết thứ tự khóa JSON/headers cụ thể. Nếu cả hai response đều có node-a, bạn chưa thực sự kiểm chứng hai tiến trình khác nhau.

### 4.8. Kiểm tra phiên đi qua hai node

1. Dùng **cùng một browser profile** vào http://localhost:8081/me khi chưa đăng nhập. Thông thường browser được chuyển về /login.
2. Trên trang login của node A, nhập username student và password local-lab-password. Spring Security cung cấp form mặc định và xử lý CSRF tương ứng.
3. Sau đăng nhập, truy cập http://localhost:8081/me. Kỳ vọng body có "user":"student", "node":"node-a".
4. Trong **chính browser đó**, vào http://localhost:8082/me, không đăng nhập lần hai. Kỳ vọng vẫn có "user":"student" nhưng "node":"node-b".
5. Dừng tiến trình node A. Gọi lại http://localhost:8082/me. Khi Redis còn sẵn sàng và phiên chưa hết hạn/invalidate, node B vẫn xác thực được cùng session.
6. Thử logout qua POST /logout hợp lệ có CSRF token hoặc giao diện/logout endpoint tương ứng; sau khi phiên bị vô hiệu hóa, request mới tới A/B không được tự nhận là đã đăng nhập.

Trong bài thử local, **port không phải ranh giới của cookie**; cookie được ràng buộc theo domain/path/thuộc tính, nên một browser có thể gửi cookie phù hợp tới cả localhost:8081 và localhost:8082. Hai browser profile hoặc cửa sổ incognito tách cookie không chứng minh cùng phiên.

Đừng in hay dán session ID vào chat, log hoặc screenshot. Session ID hợp lệ có thể bị sử dụng để chiếm phiên.

### 4.9. Điều gì chứng minh thật sự có shared session?

Cần đủ bốn điều kiện:

- Người dùng chỉ xác thực **một lần** trên A.
- Request đến B dùng **cùng cookie phiên** sau đăng nhập, không nhập mật khẩu lại.
- Response tại B cho thấy đúng user và node-b, nghĩa là request đã vào tiến trình khác.
- Sau khi tắt A, B vẫn dùng được phiên từ Redis.

Việc hai node cùng có user/password giống nhau **không chứng minh** session sharing nếu browser đã đăng nhập riêng ở cả hai. Cũng không thể chỉ dựa vào request /public trả 200 để kết luận Redis session repository khỏe; /public có thể không cần mở session.

### 4.10. Quan sát Redis một cách an toàn

Ở môi trường local, Redis CLI có thể giúp xác nhận namespace và key tồn tại:

~~~bash
redis-cli --scan --pattern "demo:sessions:*"
~~~

Chỉ dùng ở môi trường bạn có quyền. Không dùng lệnh dump giá trị phiên/SecurityContext vào tài liệu, vì chúng có thể chứa dữ liệu bảo mật. Cấu trúc key và TTL có thể khác theo repository, version và tính năng indexed session; đừng coi một tên key cứng là hợp đồng API ổn định.

## 5. Redis, JDBC, local memory và sticky session: so sánh lựa chọn

| Phương án | Chia sẻ session giữa node? | Rủi ro chính | Khi cân nhắc |
| --- | --- | --- | --- |
| In-memory HttpSession của container | Không mặc định | Mất khi restart; chỉ node hiện tại biết session | Dev, app một node, môi trường đơn giản |
| Sticky session + local | Chưa chia sẻ thực sự | Failover/chuyển node mất session, lệch tải | Giải pháp tạm hoặc chấp nhận giới hạn |
| Spring Session + Redis | Có khi cùng repository/namespace | Redis/network outage, TTL, memory, serializer | Cluster stateful cần tốc độ và shared storage |
| Spring Session + JDBC | Có khi cùng DB/schema | DB load, cleanup, lock contention, độ trễ | Có RDBMS, tải session vừa phải, vận hành tập trung |
| Container session replication | Phụ thuộc cấu hình container | Chi phí replication, serialization, topology | Một số cluster/ứng dụng legacy |
| Stateless bearer token | Không phụ thuộc HttpSession cho authentication | Token revocation, key management, bảo vệ bearer token | REST API/Resource Server theo thiết kế stateless |

**Redis là kho dữ liệu trọng yếu**, không đơn giản là cache có thể xóa tùy ý: mất session Redis có thể làm user logout hàng loạt. HA/replication/persistence có thể giảm rủi ro nhưng cần kiểm thử failover; không cam kết zero session loss.

Với Spring Session JDBC, cần dependency JDBC + datasource/schema/session tables/cleanup đúng phiên bản. Các lần đọc/ghi phiên tạo tải lên DB; cần index, capacity planning và tuning. Dù dùng Redis hay JDBC, ứng dụng vẫn có network dependency; không có backend nào tự giải quyết mọi vấn đề phân tán.

## 6. Timeout, cookie, SessionRepository và SecurityContext

Cần phân biệt ít nhất ba mốc thời gian:

1. **Max inactive interval:** thời gian không hoạt động sau đó session bị coi là hết hạn theo chính sách repository.
2. **TTL/cleanup vật lý của kho phiên:** Redis có expiration; JDBC có cleanup. Một key có thể chưa biến mất vật lý ngay khi session đã bị coi là expired.
3. **Thời gian tồn tại cookie browser:** Cookie có thể là session cookie hoặc được cấu hình Max-Age/Expires. Cookie còn tồn tại không đồng nghĩa session phía server còn tồn tại.

Nếu browser vẫn gửi cookie nhưng Redis không còn session tương ứng, user thường bị coi là chưa đăng nhập. Ngược lại, session vẫn có trong Redis nhưng cookie bị mất hoặc Path/Domain không khớp, request cũng không khôi phục được Authentication.

Chính sách thời gian sống cần cân bằng UX và an toàn. Không tăng TTL vô hạn để tránh user phải đăng nhập lại; điều này tăng thời gian session ID bị đánh cắp có thể hữu dụng.

### Cookie flags và reverse proxy

Với production, kiểm tra:

- **Secure:** session cookie chỉ nên đi qua HTTPS khi public site dùng TLS.
- **HttpOnly:** JavaScript browser không nên đọc session cookie.
- **SameSite:** lựa chọn phù hợp với topology/frontend và kết hợp biện pháp chống CSRF.
- **Path/Domain:** không mở rộng quyền chia sẻ cookie sang ứng dụng hoặc subdomain không cần thiết.
- **Session fixation:** sau đăng nhập, Spring Security mặc định có cơ chế thay session ID phù hợp với Servlet; đừng vô hiệu hóa vì thấy ID thay đổi.
- **Forwarded headers:** phía sau TLS-terminating proxy, chỉ tin proxy đáng tin cậy và bảo đảm scheme/cookie/redirect được xác định đúng.

Session ID là credential; log access không nên ghi toàn bộ Cookie header, Set-Cookie hay session ID. Nếu cần correlation, dùng ID log độc lập, không tái sử dụng làm credential.

## 7. Những vấn đề Spring Session không giải quyết tự động

### 7.1. Redis outage và chính sách lỗi

Nếu Redis bị tắt, cả node A/B có thể không thể nạp hoặc lưu session. **Không được giả định framework tự chuyển về local session an toàn**. Một fallback âm thầm có thể làm hành vi xác thực không nhất quán giữa node, và fail-open có thể tạo lỗ hổng.

Thiết kế tối thiểu: connection timeouts, giới hạn retry, health/readiness, failover, theo dõi latency/errors, xử lý response an toàn và hướng người dùng đăng nhập lại nếu dữ liệu phiên đã mất. Khi không thể chứng minh session hợp lệ, không tự cấp quyền cho request được bảo vệ.

Đừng chỉ có health endpoint /public vì nó có thể trả 200 dù Redis down. Cần kiểm tra backend hoặc synthetic workflow cho authenticated session, đặc biệt trước rollout.

### 7.2. Serialization và rolling deploy

Session có thể lưu SecurityContext, Authentication, UserDetails và các custom attributes. Những giá trị đó phải được serializer của Spring Session ghi/đọc, phù hợp cả hai node.

Lỗi thường gặp:

- User đặt entity JPA, service object hoặc request object vào HttpSession; chúng quá lớn hoặc không serializable.
- Node mới thay đổi class/package hoặc serialVersionUID của object, node cũ không giải mã được.
- Serializer Jackson được thiết lập mà thiếu type information cần thiết hoặc cấp phép giải mã quá rộng.
- Hai node dùng serializer/namespace khác nhau nhưng cùng session cookie.
- Không kiểm thử hai phiên bản code hoạt động cùng lúc trong rolling deploy.

Khuyến nghị: giữ session attributes **nhỏ, đơn giản, có versioning**, không lưu cả object graph, không bật unsafe deserialization để sửa nhanh. Test mixed-version theo cả hướng A→B và B→A. Khi buộc phải thay format không tương thích, có kế hoạch migration/invalidation và thông báo UX phù hợp.

### 7.3. Cập nhật session đồng thời

Session chia sẻ không mặc nhiên là **transactional distributed object**. Hai request có thể đồng thời lấy cùng một session và sửa attribute, khiến thay đổi cuối ghi đè thay đổi trước:

~~~text
Request 1 đọc cart.count = 0
Request 2 đọc cart.count = 0
Request 1 ghi cart.count = 1
Request 2 ghi cart.count = 1
Kỳ vọng tăng hai lần = 2, giá trị cuối có thể = 1
~~~

Tùy repository và chế độ lưu, vấn đề lost update/ghi chồng có thể xuất hiện. Không dùng session làm nguồn sự thật duy nhất cho đơn hàng, số dư, tồn kho hoặc dữ liệu cần transaction. Đưa các dữ liệu đó vào database nghiệp vụ và dùng concurrency control, chỉ giữ reference trong session.

### 7.4. Logout, đổi quyền và revocation

Logout trên A có thể invalidate session trong Redis. Request mới trên B cùng session ID sau đó không được coi là authenticated. Nhưng **request đã chạy** trước khi invalidate có thể đã nạp SecurityContext, không nhất thiết dừng tức thì.

Nếu role hoặc trạng thái user bị thu hồi, SecurityContext lưu trong session có thể chứa authority trước đó. Spring Session không tự hỏi UserDetailsService mới ở mỗi request. Với yêu cầu cao về revocation, thiết kế kiểm tra version quyền, central session revocation hoặc chính sách tái xác thực khi thích hợp.

Khi giới hạn số phiên đăng nhập đồng thời, cần xác minh khả năng tra cứu phiên theo principal/index và SessionRegistry của ứng dụng. SpringSessionBackedSessionRegistry có thể hỗ trợ một số mô hình, nhưng **chỉ thêm dependency Spring Session không bảo đảm mọi cơ chế concurrent session control tự cấu hình đúng**; cần repository hỗ trợ index, wiring, test và hiểu lifecycle event.

### 7.5. Flush/save mode và chi phí ghi

Spring Session có những tùy chọn liên quan lúc ghi dữ liệu phiên về repository (save/flush mode) tùy backend/version. Không thể kết luận “mỗi HTTP GET đều ghi nguyên toàn bộ session” hoặc “mọi attribute được đồng bộ tức thì” nếu chưa xem cấu hình. Đổi sang flush tức thời có thể tăng số lần round trip và tác động hiệu năng.

Giám sát kích thước session, tỷ lệ request tạo/update session, độ trễ Redis/JDBC, TTL/expiration, connection pool và memory/evictions. Chỉ tối ưu khi có bằng chứng từ traffic thực tế.

### 7.6. Đồng bộ dữ liệu người dùng

Spring Session chia sẻ HttpSession, không chia sẻ InMemoryUserDetailsManager hoặc database user. Nếu mỗi node cấu hình user/password/role khác nhau, **lần xác thực mới** có thể thành công tại A nhưng thất bại tại B dù phiên được lưu chung. Production cần shared identity source và nhất quán về authentication providers/password policy.

## 8. Stateful session hay stateless API?

Với ứng dụng server-rendered dùng formLogin và cookie, shared session repository giúp scale out và quản trị logout/revocation phía server.

Với API resource server nhận Bearer token, người dùng có thể không cần server-side HTTP session cho mỗi request: thiết kế stateless phù hợp với nhu cầu. Tuy nhiên token vẫn cần kiểm tra chữ ký/issuer/audience/expiry, bảo vệ lưu trữ phía client và phương án revocation khi cần.

**SessionCreationPolicy.STATELESS** của Spring Security cho biết chain không sử dụng HttpSession để giữ SecurityContext theo mô hình stateful thông thường. Thêm spring-session-data-redis không tự biến stateless authentication thành login duy trì bằng cookie. Nếu ứng dụng vừa có web session chain vừa có API stateless chain, phân biệt rõ securityMatcher và cấu hình của từng chain.

Không chuyển sang JWT chỉ để “sửa” lỗi local session mà không đánh giá yêu cầu revocation, rủi ro token, thời hạn và UX.

## 9. Kiểm thử cross-node, failover và vận hành

| Kiểm thử | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Anonymous | GET /me trên A/B trước login | Redirect/challenge, không có authenticated user |
| Login một lần | POST login hợp lệ trên A | Browser có session cookie mới |
| Qua node | GET /me trên B với cùng cookie | user=student và node=node-b |
| Failover app | Dừng A, tiếp tục GET /me B | B vẫn đọc session khi Redis hoạt động |
| Logout | Invalidate session, request mới trên B | Không còn authenticated |
| Idle timeout | Chờ đủ timeout/test timeout ngắn | Session không còn hợp lệ |
| Redis outage | Ngắt kết nối Redis trong test | Không fail-open, lỗi rõ ràng/được kiểm soát |
| Rolling deploy | A/B khác phiên bản code | Session đọc được hoặc migration/invalidation có chủ đích |
| Cookie scope | HTTPS/proxy/context path | Cookie được gửi đúng host/path và có flags an toàn |
| Concurrent changes | Hai request cùng ghi session data | Không dùng session cho state cần transaction nghiệp vụ |

Một test cross-node chuẩn phải **buộc request đi đến hai node khác nhau**, không dựa vào load balancer vô tình chọn đúng. Kiểm tra HTTP status và nội dung thực tế, không chỉ số lượng cookie.

Chỉ số quan sát hữu ích: session lookup/write failures, Redis latency/errors, session count theo định nghĩa hợp lệ, key expiration/evictions, kích thước attribute, tần suất login redirect đột biến, lỗi deserialize, độ trễ authentication, hoạt động logout và tỷ lệ node failover.

### Khi chỉ thấy /public 200 chưa đủ

GET /public có thể không cần đọc HttpSession. Nếu Redis down, endpoint này vẫn có thể trả 200 trong một số tình huống. Vì vậy chỉ kiểm tra node sống bằng public health không chứng minh shared session healthy. Một synthetic test auth thực tế và backend health monitoring có giá trị hơn.

## 10. Lỗi phổ biến và xử lý đúng

**Lỗi A: Đăng nhập trên A rồi bị chuyển về login khi sang B.** Kiểm tra session store dùng local hay Redis, cookie có được gửi tới B không, namespace có thống nhất không, và SecurityContext đã được lưu chưa. Nếu có custom auth filter, xem có gọi saveContext theo contract không.

**Lỗi B: Đã thêm Redis client nhưng session vẫn local.** spring-boot-starter-data-redis cung cấp client, không tự biến HttpSession thành Redis session. Cần Spring Session module, đúng auto-configuration và SessionRepositoryFilter.

**Lỗi C: Redis namespace khác giữa các node.** Dù cùng host, các key không chung logical namespace nên session không đọc được. Đồng bộ cấu hình và test thực tế.

**Lỗi D: Cookie browser không gửi khi chuyển host hoặc sau proxy.** Kiểm tra Path, Domain, SameSite, Secure, scheme HTTPS, context path và reverse proxy trusted forwarded headers. Không mở cookie domain quá rộng để “chữa” vội.

**Lỗi E: Redis restart làm mọi user logout.** Nếu không có persistence/HA thích hợp, dữ liệu phiên mất là điều có thể xảy ra. Thiết kế recovery và UX, không mong đợi app tự phục hồi session không còn.

**Lỗi F: Class/serializer thay đổi sau deploy, session không đọc được.** Dùng DTO ổn định, kiểm thử rolling upgrade, xử lý incompatibility có kế hoạch. Không bật deserialization cho kiểu bất kỳ.

**Lỗi G: Dữ liệu session bị ghi đè khi request đồng thời.** Session không là transaction database. Lưu state nghiệp vụ vào DB với concurrency control và giữ session nhỏ.

**Lỗi H: Logout trên A nhưng B vẫn cho phép request đang chạy.** Phân biệt request in-flight với request mới sau invalidate, kiểm tra session ID/cookie cụ thể; nếu cần revocation tức thì cho nghiệp vụ nhạy cảm, thiết kế kiểm tra bổ sung.

**Lỗi I: Phiên hết hạn “sai” giờ.** Phân biệt idle timeout, TTL logic/physical cleanup, cookie lifetime và lastAccessedTime; xem backend, thời gian thực và cache/proxy.

**Lỗi J: Thay user role trong DB nhưng session vẫn giữ role cũ.** SecurityContext đã lưu có thể chứa authorities cũ. Cần chính sách revalidation và session revocation khi role thay đổi.

**Lỗi K: SessionCreationPolicy.STATELESS rồi mong login form giữ session.** Stateless chain không chủ đích dùng HttpSession để giữ context cho request sau. Chọn kiến trúc đúng cho từng chain.

**Lỗi L: Đưa Redis không authentication ra Internet.** Redis session store chứa dữ liệu nhạy cảm; cần private networking, ACL/auth, TLS/secret management, least privilege, backup và monitoring.

## 11. Checklist chuẩn bị cho production

1. **Thống kê session attributes và size**, loại các object quá lớn hoặc không hỗ trợ serialization.
2. **Chọn Redis/JDBC** theo số lượng session, latency, capacity, SLA, chi phí và khả năng vận hành.
3. **Xác minh SessionRepositoryFilter được bật**, không dùng đồng thời local session như fallback không được kiểm soát.
4. **Thống nhất config các node:** endpoint, namespace, serializer, timeout, cookie name/domain/path và security chain.
5. **Shared user/identity store** cho authentication mới trên mọi node; không dùng in-memory users như production.
6. **Cookie Secure, HttpOnly, SameSite, TLS**, chống session fixation và giữ CSRF protection phù hợp với form login.
7. **Bảo vệ Redis/DB** bằng ACL, mạng riêng, secret management, HA/persistence, sao lưu và giám sát.
8. **Test một lần login trên A → B bằng cùng cookie**, tắt A và xác minh B vẫn có session.
9. **Test Redis outage**, timeout, session expiration, logout và quyền bị thu hồi.
10. **Test rolling deployment**, serializer compatibility khi có hai version chạy đồng thời.
11. **Kiểm thử concurrent writes**, đưa dữ liệu cần consistency cao sang DB với transaction.
12. **Quan sát và cảnh báo**, phân biệt public health và authenticated-session health.
13. **Kế hoạch xử lý user login lại** nếu phải đổi namespace/serializer hoặc mất session store.
14. **Đánh giá API stateless riêng** khi không cần session, không chuyển đổi vô điều kiện chỉ để tránh cấu hình cluster.

## 12. Câu hỏi tự luyện có giải thích

**Câu 1.** Hai instance cùng dùng SecurityConfig giống hệt, vì sao session tạo trên A không tự nhìn thấy tại B?

**Đáp án:** local HttpSession manager nằm trong bộ nhớ từng tiến trình. Code giống nhau không đồng nghĩa session map được chia sẻ; cần shared repository hoặc replication được cấu hình.

**Câu 2.** Sticky session bảo đảm failover không?

**Đáp án:** không. Nó hướng request về cùng node khi node còn sẵn sàng, không sao chép phiên sang node khác.

**Câu 3.** Spring Session thay phần nào và không thay phần nào?

**Đáp án:** thay cách lưu/tìm HttpSession bằng SessionRepository; không thay AuthenticationManager, PasswordEncoder, SecurityContext authorization logic.

**Câu 4.** Nếu một request tới B có session cookie nhưng Redis không còn session thì sao?

**Đáp án:** cookie mang ID chứ không mang đầy đủ authentication. Session không còn → không khôi phục được SecurityContext từ phiên đó và request bảo vệ phải được xử lý như unauthenticated hoặc lỗi phù hợp.

**Câu 5.** Hai node dùng chung Redis nhưng namespace khác có chia sẻ phiên không?

**Đáp án:** không theo cấu hình thông thường. Keyspace logic khác nhau; hai node phải thống nhất repository, namespace và serializer.

**Câu 6.** Thêm Redis có tự giữ login khi chain đặt STATELESS không?

**Đáp án:** không. STATELESS là lựa chọn của Spring Security về việc không dựa vào HttpSession cho SecurityContext của request.

**Câu 7.** GET /public vẫn 200 khi Redis down có nghĩa phiên hoạt động không?

**Đáp án:** không. Endpoint công khai có thể không đọc phiên; cần synthetic authenticated request và kiểm tra backend.

**Câu 8.** Một object session được node phiên bản mới ghi nhưng node cũ không đọc được là lỗi gì?

**Đáp án:** serialization/schema/version compatibility, cần test rolling deploy, giữ format ổn định hoặc migration/invalidation có chủ đích.

**Câu 9.** Vì sao không nên lưu số dư hay đơn hàng duy nhất trong HttpSession?

**Đáp án:** session repository không tự bảo đảm transaction nghiệp vụ khi hai request cập nhật đồng thời, có thể lost updates. Dùng database nghiệp vụ.

**Câu 10.** Logout trên A có chặn tức thì mọi request in-flight trên B không?

**Đáp án:** không có bảo đảm đó. Request đã nạp context có thể đang chạy; test request mới sau invalidation và thiết kế revocation bổ sung khi cần.

## Tổng kết

Với một node, **HttpSession local** đơn giản nhưng phụ thuộc vào heap của JVM. Khi nhiều node đứng sau load balancer, routing chuyển node, restart hoặc crash có thể khiến người dùng mất phiên; **sticky session không sao chép dữ liệu**.

**Spring Session** đưa HttpSession sang **SessionRepository dùng chung** (thường Redis/JDBC), cho phép các instance Spring Security Servlet đọc cùng phiên sau khi người dùng đăng nhập. Muốn triển khai đúng phải phối hợp cookie, session ID, SecurityContext, namespace, TTL, serializer, Redis availability, logout và quyền truy cập.

Bằng chứng quan trọng nhất không phải “hai node đều hoạt động”, mà là **đăng nhập một lần ở A, dùng cùng cookie qua B, dừng A mà B vẫn đọc phiên từ kho dùng chung**, rồi kiểm thử thêm outage, logout, timeout và rolling deployment.