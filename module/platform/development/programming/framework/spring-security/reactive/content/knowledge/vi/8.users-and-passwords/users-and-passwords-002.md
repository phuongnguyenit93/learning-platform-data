# Tạo người dùng trong bộ nhớ bằng MapReactiveUserDetailsService trong Spring Security Reactive

## 1. Mục tiêu học tập

Trong một ứng dụng Spring WebFlux, bài toán đầu tiên khi học authentication là tạo ra vài tài khoản có username, mật khẩu và quyền hạn, sau đó cho Spring Security sử dụng chúng để xác thực request. **MapReactiveUserDetailsService** giúp làm điều đó mà chưa cần database: nó chứa các **UserDetails** trong bộ nhớ và tìm tài khoản theo username qua hợp đồng **ReactiveUserDetailsService**.

Sau bài học, bạn sẽ:

1. Hiểu quan hệ giữa UserDetails, ReactiveUserDetailsService, MapReactiveUserDetailsService, PasswordEncoder, ReactiveAuthenticationManager và SecurityWebFilterChain.
2. Tạo user với username, mật khẩu đã băm, roles/authorities và trạng thái tài khoản.
3. Khai báo MapReactiveUserDetailsService thành Spring bean cho WebFlux.
4. Kiểm thử tra cứu bằng StepVerifier và thử HTTP Basic thực tế bằng curl/WebTestClient.
5. Phân biệt ba bước **tra cứu user**, **xác thực password** và **kiểm tra quyền**.
6. Nhận ra giới hạn của lưu trữ trong RAM khi tiến tới production.

**Phạm vi:** đây là bài tạo người dùng trong bộ nhớ cho Spring Security **reactive**, không phải triển khai servlet và không phải hệ thống đăng ký/quản trị tài khoản production.

## 2. MapReactiveUserDetailsService trong kiến trúc WebFlux

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Công việc | Ví dụ |
| --- | --- | --- |
| **UserDetails** | Mô tả username, password hash, GrantedAuthority và trạng thái | reader, ROLE_USER |
| **ReactiveUserDetailsService** | Tra cứu một user theo username | Mono<UserDetails> findByUsername(String) |
| **MapReactiveUserDetailsService** | Triển khai dịch vụ trên bằng Map trong RAM | new MapReactiveUserDetailsService(reader, admin) |
| **PasswordEncoder** | Encode password mới và matches khi kiểm tra | BCryptPasswordEncoder |
| **ReactiveAuthenticationManager** | Nhận credential, dùng user data và password check để xác thực | Đăng nhập thành công hoặc thất bại |
| **SecurityWebFilterChain** | Kết nối HTTP authentication và authorization | httpBasic, authorizeExchange |
| **Authentication** | Danh tính tin cậy sau khi xác thực thành công | Principal reader, ROLE_USER |

Spring Security xử lý luồng HTTP Basic đại ý:

~~~text
Client -> Authorization: Basic <base64(username:password)>
         |
         v
SecurityWebFilterChain (WebFlux)
         |
         v
Thành phần xác thực username/password
         |
         +--> ReactiveUserDetailsService.findByUsername(username)
         |       |
         |       +--> Mono<UserDetails> hoặc Mono.empty()
         |
         +--> PasswordEncoder.matches(rawPassword, storedHash)
         |
         +--> Kiểm tra trạng thái của UserDetails
         |
         +--> Thành công: Authentication được tin cậy
         +--> Thất bại: không tạo đăng nhập hợp lệ
         |
         v
Authorization: authenticated, hasRole, hasAuthority
         |
         v
Controller và service
~~~

Sơ đồ giải thích các trách nhiệm, không mô tả chính xác thứ tự mọi WebFilter trong mọi cấu hình. **MapReactiveUserDetailsService không trực tiếp xác minh raw password**; nó chỉ cung cấp user record cho cơ chế xác thực. Tương tự, việc tìm thấy user không có nghĩa người gửi request là user đó.

### 2.1. So sánh với servlet

| Spring Security servlet | Spring Security reactive |
| --- | --- |
| UserDetailsService.loadUserByUsername trả UserDetails đồng bộ | ReactiveUserDetailsService.findByUsername trả Mono<UserDetails> |
| InMemoryUserDetailsManager | MapReactiveUserDetailsService |
| HttpSecurity, SecurityFilterChain | ServerHttpSecurity, SecurityWebFilterChain |
| Servlet Filter và cách quản lý context theo servlet | WebFilter và Reactor Context |

Tránh nhầm MapReactiveUserDetailsService với **InMemoryUserDetailsManager** chỉ vì hai tên đều gợi ý RAM. Chúng phục vụ hợp đồng và mô hình ứng dụng khác nhau. Không dùng block() trong WebFlux handler để ép Mono thành đối tượng đồng bộ.

## 3. Xây UserDetails đúng cách

UserDetails là hợp đồng mô tả bản ghi danh tính, gồm tên, mật khẩu đã lưu, authorities và các trạng thái như enabled, accountNonLocked, accountNonExpired, credentialsNonExpired.

Spring Security có builder **User.withUsername(...)**. Ví dụ:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

UserDetails reader = User.withUsername("reader")
        .password(encoder.encode("reader-pass"))
        .roles("USER")
        .build();

UserDetails admin = User.withUsername("admin")
        .password(encoder.encode("admin-pass"))
        .roles("USER", "ADMIN")
        .build();

MapReactiveUserDetailsService users =
        new MapReactiveUserDetailsService(reader, admin);
~~~

Đây là đoạn code để đặt trong một phương thức Java có các import phù hợp; chương trình đầy đủ ở mục 7.

- **username** là khóa tra cứu user. Hai người không nên dùng cùng username theo chính sách của hệ thống.
- **password** phải là chuỗi đã encode bằng PasswordEncoder tương thích với cơ chế xác thực.
- **roles("USER")** sinh authority **ROLE_USER** theo quy ước mặc định của Spring Security.
- **roles("USER", "ADMIN")** cho admin cả ROLE_USER và ROLE_ADMIN, để có thể vào endpoint yêu cầu quyền USER.
- **build()** tạo UserDetails từ các giá trị đã cấu hình.

Phân biệt:

~~~java
.roles("ADMIN")                  // authority ROLE_ADMIN
.authorities("orders:read")      // authority orders:read
~~~

**hasRole("ADMIN")** kiểm tra ROLE_ADMIN theo quy ước thông thường; **hasAuthority("orders:read")** so sánh chính xác chuỗi quyền. Không đưa chuỗi ROLE_ADMIN vào roles() rồi trông chờ nó tự xử lý đúng mọi trường hợp; roles() thông thường yêu cầu tên role chưa có tiền tố ROLE_.

### 3.1. Tài khoản bị khóa hoặc vô hiệu hóa

UserDetails chứa các cờ về trạng thái tài khoản. Bạn có thể tạo một fixture bị khóa:

~~~java
UserDetails locked = User.withUsername("locked")
        .password(encoder.encode("locked-pass"))
        .roles("USER")
        .accountLocked(true)
        .build();
~~~

Đây là ví dụ bổ sung, không nằm trong danh sách hai user của demo. Một user có mặt trong Map nhưng bị khóa không nên được xác thực thành công. Cơ chế xác thực kiểm tra trạng thái và password, chứ không chỉ xem Map có username.

## 4. PasswordEncoder và lưu trữ mật khẩu an toàn

**BCryptPasswordEncoder** tạo hash mật khẩu có salt và chi phí tính toán điều chỉnh được:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String storedHash = encoder.encode("reader-pass");

boolean ok = encoder.matches("reader-pass", storedHash);  // true
boolean bad = encoder.matches("wrong-pass", storedHash);  // false
~~~

Do salt, hai lần gọi encode cùng raw password có thể tạo ra hai hash khác nhau. Không so sánh encoder.encode(raw).equals(storedHash); luôn dùng **matches(raw, storedHash)**.

| Thời điểm | Hành động |
| --- | --- |
| Tạo user | Băm password một lần, lưu hash vào UserDetails |
| HTTP login | Nhận raw password qua cơ chế authentication |
| Tra cứu | MapReactiveUserDetailsService trả record có hash |
| Kiểm tra | PasswordEncoder đối chiếu raw password với hash đã lưu |
| Thành công | Framework tạo Authentication với principal và authorities |
| Phân quyền | Quy tắc URL/method/object quyết định tài nguyên được truy cập |

Đừng viết:

~~~java
// Không đúng với BCryptPasswordEncoder:
User.withUsername("reader")
        .password("reader-pass")
        .roles("USER")
        .build();
~~~

Cũng không dùng **NoOpPasswordEncoder**, tiền tố **{noop}** hoặc **User.withDefaultPasswordEncoder()** như một giải pháp production. Những cơ chế đơn giản có thể xuất hiện ở demo học tập, nhưng mật khẩu hard-code trong source/binary vẫn có thể bị đọc. Ví dụ trong bài dùng literal chỉ để người học tự thử curl; tuyệt đối không sao chép credential đó vào hệ thống thật.

**HTTP Basic** mã hóa biểu diễn username:password bằng Base64, không mã hóa bảo mật đường truyền. Khi triển khai thật phải chạy qua **HTTPS/TLS** và hạn chế log header Authorization, password, token. Không truyền password trên URL query string.

BCrypt có chi phí CPU, nên ứng dụng vẫn cần rate limit đăng nhập, giám sát tải và giới hạn đồng thời phù hợp. Mono giúp compose reactive pipeline nhưng không biến phép băm mật khẩu thành tác vụ không tốn CPU.

## 5. Khởi tạo MapReactiveUserDetailsService

Ba constructor đáng biết:

~~~java
new MapReactiveUserDetailsService(reader, admin);
new MapReactiveUserDetailsService(List.of(reader, admin));

Map<String, UserDetails> byUsername = Map.of(
        reader.getUsername(), reader,
        admin.getUsername(), admin);
new MapReactiveUserDetailsService(byUsername);
~~~

Constructor Map yêu cầu Map truy cập không blocking. Không đặt một thao tác I/O đồng bộ trong Map.get() rồi cho rằng lớp bao ngoài sẽ khiến nó reactive. Với dữ liệu ít và tĩnh, constructor varargs dễ đọc nhất.

MapReactiveUserDetailsService triển khai **ReactiveUserDetailsService** và **ReactiveUserDetailsPasswordService**; API công khai quan trọng:

~~~java
Mono<UserDetails> findByUsername(String username);
Mono<UserDetails> updatePassword(UserDetails user, String newPassword);
~~~

**findByUsername** tìm user theo tên; có user thì phát một UserDetails rồi complete; không có user thì thông thường Mono hoàn thành rỗng. Nó không kiểm tra raw password hay tạo Authentication.

**updatePassword** cho phép cập nhật password của user trong Map đang chạy. Với PasswordEncoder, tham số newPassword cần chứa giá trị **đã encode** tương ứng với cấu hình xác thực. Cập nhật này không được lưu lại qua restart hoặc tự đồng bộ tới instance khác.

Ví dụ minh họa việc đổi password trên một dịch vụ thử nghiệm:

~~~java
Mono<UserDetails> changed =
        users.findByUsername("reader")
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("User missing")))
                .flatMap(user -> users.updatePassword(
                        user, encoder.encode("new-demo-pass")));
~~~

Mã này phải được ghép vào ngữ cảnh có biến users và encoder, không phải file Java độc lập. Khi muốn đổi password trong sản phẩm thật, phải có xác minh người yêu cầu, rate limit, audit, invalidate session/token khi cần, kho dữ liệu bền vững và chính sách password.

**Không nhầm API:** MapReactiveUserDetailsService không cung cấp bộ phương thức quản trị createUser/deleteUser/updateUser như InMemoryUserDetailsManager của servlet. Có thể tạo danh sách ban đầu khi dựng bean; nếu cần đăng ký/xóa/thay đổi tài khoản production, hãy dùng service quản trị và repository/Identity Provider phù hợp.

### 5.1. Kiểm tra tra cứu bằng Mono

~~~java
Mono<UserDetails> publisher = users.findByUsername("reader");

Mono<String> names = users.findByUsername("reader")
        .map(UserDetails::getUsername)
        .switchIfEmpty(Mono.just("not found"));
~~~

Khi chạy với dữ liệu trong ví dụ, publisher phát UserDetails của reader; names phát chuỗi reader. Tuy nhiên, client có thể tự gửi username bằng query parameter để tìm một bản ghi tồn tại. Việc tra cứu như vậy **không chứng minh danh tính client**. Để bảo vệ API, dùng Authentication từ Spring Security sau khi xác thực thành công.

### 5.2. Ghi nhớ khác biệt giữa cấu hình và runtime

Bean được khởi tạo khi ApplicationContext tạo các phụ thuộc. Hash BCrypt có thể khác ở mỗi lần khởi động do salt, nhưng matches(raw, storedHash) vẫn đúng. Nếu process restart, user list được tạo lại từ mã cấu hình, và thay đổi trên Map lúc runtime không tự được khôi phục. Nhiều instance ứng dụng không chia sẻ cùng một Map.

## 6. Authentication và authorization cùng dùng danh sách user thế nào?

Spring Security nhìn user ở ba góc khác nhau:

1. **Có username?** ReactiveUserDetailsService.findByUsername trả UserDetails hay Mono.empty.
2. **Credential có hợp lệ?** Manager và PasswordEncoder kiểm tra password, trạng thái tài khoản và các điều kiện xác thực.
3. **Request có đủ quyền?** SecurityWebFilterChain/authorization đối chiếu Authentication với role, authority và policy tài nguyên.

Ví dụ hai request:

~~~text
Request A: reader/reader-pass -> tra cứu reader -> password đúng
          -> Authentication ROLE_USER -> /api/me: 200

Request B: reader/reader-pass -> tra cứu reader -> password đúng
          -> Authentication ROLE_USER -> /admin/report: 403
~~~

Request B đã xác thực thành công nhưng thiếu quyền admin. Ngược lại, username không tồn tại hoặc password sai thường nhận 401 với HTTP Basic entry point.

**Không nên trả thông báo HTTP khác nhau quá chi tiết cho username không tồn tại và password sai**, vì có thể hỗ trợ user enumeration. Không log password thô; nếu cần metric, lưu loại lỗi ở server với dữ liệu đã lọc.

**Role chưa đủ để bảo vệ bản ghi cụ thể.** Người có ROLE_USER vẫn không mặc nhiên đọc được đơn hàng của user khác. Kiểm tra owner/tenant ở tầng nghiệp vụ hoặc truy vấn dữ liệu trong phạm vi được phép.

## 7. Dự án Java 17+ chạy được: Spring Boot WebFlux + HTTP Basic + MapReactiveUserDetailsService

Demo dùng Java 17+, Gradle 8.x và Spring Boot **3.3.5**. Hai tài khoản chỉ dùng cho học tập:

| Username | Password demo | Authority |
| --- | --- | --- |
| reader | reader-pass | ROLE_USER |
| admin | admin-pass | ROLE_USER, ROLE_ADMIN |

Cấu trúc:

~~~text
memory-reactive-users/
├── settings.gradle
├── build.gradle
├── src/main/java/example/memory/MemoryUsersApplication.java
├── src/main/java/example/memory/DemoController.java
└── src/test/java/example/memory/MemoryUsersApplicationTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'memory-reactive-users'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.3. MemoryUsersApplication.java

~~~java
package example.memory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
public class MemoryUsersApplication {

    public static void main(String[] args) {
        SpringApplication.run(MemoryUsersApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

Tại đây:
- Bean **PasswordEncoder** đảm bảo password được mã hóa bằng BCrypt.
- Bean **MapReactiveUserDetailsService** cung cấp user cho cơ chế username/password của Spring Security.
- **httpBasic** nhận credential từ header; controller không tự kiểm tra mật khẩu.
- **authorizeExchange** đặt quy tắc cụ thể /admin/** trước /api/** và chính sách cuối denyAll.
- **formLogin.disable()** giúp bài demo tập trung vào HTTP Basic và mã 401/403.

### 7.4. DemoController.java

~~~java
package example.memory;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me(Mono<Principal> principal) {
        return principal.map(p -> "hello " + p.getName());
    }

    @GetMapping("/admin/report")
    public Mono<String> report() {
        return Mono.just("admin-report");
    }
}
~~~

Controller nhận Mono<Principal> đã được thiết lập bởi xử lý HTTP security trong WebFlux. Nó không gọi trực tiếp users.findByUsername để “đăng nhập hộ” client, cũng không trả UserDetails có thể chứa hash ra HTTP response.

### 7.5. Chạy và quan sát

Ở thư mục dự án, với JDK 17+ và Gradle 8.x:

~~~bash
gradle bootRun
~~~

Ở terminal Bash khác:

~~~bash
curl -s http://localhost:8080/public/ping
# pong

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
# 401

curl -s -u reader:reader-pass http://localhost:8080/api/me
# hello reader

curl -s -u admin:admin-pass http://localhost:8080/api/me
# hello admin

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:wrong-pass http://localhost:8080/api/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  -u unknown:any-pass http://localhost:8080/api/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader-pass http://localhost:8080/admin/report
# 403

curl -s -u admin:admin-pass http://localhost:8080/admin/report
# admin-report
~~~

Các dòng bắt đầu # chỉ là **stdout hoặc mã trạng thái dự kiến**, không phải lệnh. Trên Windows PowerShell, hãy dùng **curl.exe** trên một dòng thay cho cú pháp nối dòng Bash.

| HTTP request | Authentication | Authorization | Kết quả mong đợi |
| --- | --- | --- | --- |
| /public/ping không credential | Không bắt buộc | permitAll | 200 pong |
| /api/me không credential | Chưa xác thực | authenticated | 401 |
| /api/me reader đúng password | Thành công với ROLE_USER | authenticated | 200 hello reader |
| /api/me admin đúng password | Thành công với ROLE_USER, ROLE_ADMIN | authenticated | 200 hello admin |
| /api/me reader sai password | Thất bại | Không tạo danh tính hợp lệ | 401 |
| /api/me username không tồn tại | Thất bại | Không tạo danh tính hợp lệ | 401 |
| /admin/report reader hợp lệ | Thành công | Thiếu ROLE_ADMIN | 403 |
| /admin/report admin hợp lệ | Thành công | Có ROLE_ADMIN | 200 admin-report |

Đây là kết quả của cấu hình HTTP Basic cụ thể; các ứng dụng form login có thể dùng redirect thay cho HTTP 401. Demo chỉ có GET nên không trình bày thao tác ghi dữ liệu/CSRF. Nếu bổ sung POST/PUT/DELETE, phải thiết kế CSRF theo loại credential mà trình duyệt sử dụng và kiểm tra giới hạn tài nguyên.

## 8. Kiểm thử StepVerifier và WebTestClient

Cần kiểm tra **dữ liệu người dùng** và **hành vi HTTP** độc lập. Test lookup thành công không đảm bảo password verification hoặc URL authorization đúng.

### 8.1. MemoryUsersApplicationTest.java

~~~java
package example.memory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MemoryUsersApplicationTest {

    @Autowired
    MapReactiveUserDetailsService users;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    WebTestClient client;

    @Test
    void findsStoredUserWithEncodedPassword() {
        StepVerifier.create(users.findByUsername("reader"))
                .assertNext(reader -> {
                    assertEquals("reader", reader.getUsername());
                    assertFalse("reader-pass".equals(reader.getPassword()));
                    assertTrue(encoder.matches(
                            "reader-pass", reader.getPassword()));
                    assertTrue(reader.getAuthorities().stream()
                            .anyMatch(a -> "ROLE_USER".equals(a.getAuthority())));
                })
                .verifyComplete();
    }

    @Test
    void unknownUsernameIsEmpty() {
        StepVerifier.create(users.findByUsername("unknown"))
                .verifyComplete();
    }

    @Test
    void publicEndpointDoesNotNeedLogin() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanOpenMeButCannotOpenAdmin() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("hello reader");

        client.get().uri("/admin/report")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanOpenAdmin() {
        client.get().uri("/admin/report")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-report");
    }
}
~~~

Chạy trong thư mục dự án:

~~~bash
gradle test
~~~

**Kết quả mong đợi:** sáu test PASS, Gradle kết thúc bằng **BUILD SUCCESSFUL** khi các phụ thuộc được tải và môi trường hợp lệ.

- StepVerifier kiểm tra findByUsername phát UserDetails, hash không phải raw password và username không tồn tại trả empty.
- WebTestClient kiểm tra WebFilter, HTTP Basic và authorizeExchange, phân biệt credential sai (401) với thiếu quyền admin (403).

Bài test dùng cổng ngẫu nhiên, không cần server demo chạy riêng ở cổng 8080. Nếu muốn kiểm tra bảo vệ các API có dữ liệu thật, bổ sung test owner/tenant, brute-force rate limit, CSRF và các hình thức authentication thực tế.

### 8.2. Test updatePassword tách riêng

Không nên thay password của bean dùng chung giữa các HTTP test vì thứ tự test có thể làm kết quả phụ thuộc nhau. Có thể tạo instance riêng:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();
UserDetails original = User.withUsername("temporary")
        .password(encoder.encode("old-pass"))
        .roles("USER")
        .build();

MapReactiveUserDetailsService temporary =
        new MapReactiveUserDetailsService(original);

StepVerifier.create(temporary.findByUsername("temporary")
        .flatMap(user -> temporary.updatePassword(
                user, encoder.encode("new-pass"))))
        .assertNext(updated -> {
            assertTrue(encoder.matches("new-pass", updated.getPassword()));
            assertFalse(encoder.matches("old-pass", updated.getPassword()));
        })
        .verifyComplete();
~~~

Đoạn này dùng **trong phương thức test** với các import User, UserDetails, MapReactiveUserDetailsService, BCryptPasswordEncoder, PasswordEncoder và assertTrue/assertFalse; không phải file class độc lập. Nó chỉ thay đổi Map tạm trong RAM.

## 9. Khi nào nên dùng MapReactiveUserDetailsService?

**Phù hợp:** demo học Spring Security, ví dụ API HTTP Basic, kiểm thử tích hợp, proof of concept, hoặc một tập user nhỏ và cố định trong môi trường kiểm soát.

**Không phải mặc định cho production** nếu cần đăng ký, đổi/quên mật khẩu, xoay credential, nhiều replica, đa tenant, audit, khóa tài khoản theo chính sách, MFA hoặc quyền cập nhật tức thời.

| Giới hạn | Tác động | Giải pháp |
| --- | --- | --- |
| Không bền vững | Restart mất thay đổi runtime | Repository hoặc IdP bền vững |
| Không chia sẻ giữa các instance | Mỗi replica giữ user riêng | Kho định danh tập trung |
| Không có API quản trị đầy đủ | Không thể xây signup/reset password hoàn chỉnh bằng Map | Service quản trị, phân quyền, audit |
| Credential hard-code | Source/binary có thể lộ password demo | Secret manager, phát hành và xoay khóa |
| Không có sẵn chính sách login chống lạm dụng | Brute force/credential stuffing | Rate limit, giám sát, MFA |
| Password verification tốn CPU | Login flood ảnh hưởng khả năng phục vụ | Giới hạn tải, sizing và theo dõi latency |
| UserDetails không chứa đầy đủ quyền theo đối tượng | IDOR/BOLA có thể xảy ra | Kiểm tra owner/tenant ở service/repository |

Với production, có thể xây một **ReactiveUserDetailsService** riêng gọi repository không blocking:

~~~java
// Ví dụ tích hợp; userRepository, record và kiểu dữ liệu do ứng dụng định nghĩa.
public Mono<UserDetails> findByUsername(String username) {
    return userRepository.findByUsername(username)
            .map(record -> User.withUsername(record.username())
                    .password(record.encodedPassword())
                    .authorities(record.authorities())
                    .disabled(!record.enabled())
                    .accountLocked(record.locked())
                    .build());
}
~~~

Đoạn trên **không phải chương trình Java độc lập**; cần thiết kế schema, index/uniqueness, transaction, mapping authority, audit và chính sách trạng thái. Sử dụng OAuth2/OIDC hoặc Resource Server có thể thích hợp hơn khi đã có Identity Provider bên ngoài. Khi API chỉ nhận JWT bearer từ một issuer, không cần dùng MapReactiveUserDetailsService để xác thực token đó.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Có user trong Map là request đã đăng nhập” | findByUsername chỉ tìm record; cần xác thực password/token |
| “Reactive là không sử dụng CPU” | Mono là contract bất đồng bộ; BCrypt vẫn tốn CPU |
| “PasswordEncoder.encode(raw) luôn ra cùng một chuỗi” | BCrypt có salt; xác minh bằng matches |
| “Gọi roles("ADMIN") tự bảo vệ mọi admin URL” | Phải cấu hình hasRole/hasAuthority |
| “ROLE_ADMIN là argument trực tiếp cho roles()” | Thông thường dùng roles("ADMIN") hoặc authorities("ROLE_ADMIN") |
| “MapReactiveUserDetailsService là InMemoryUserDetailsManager với tên khác” | Một bên reactive, một bên servlet/synchronous |
| “HTTP Basic Base64 là bảo mật đủ” | Phải dùng TLS |
| “Mono.empty() của findByUsername nghĩa là được phép anonymous” | Nghĩa là không có UserDetails; authorization vẫn quyết định |
| “Có thể lưu user list vĩnh viễn trong RAM” | Restart và nhiều replica làm mất/lệch thay đổi |
| “updatePassword(raw) sẽ tự băm raw” | Trong mô hình dùng PasswordEncoder, phải cung cấp giá trị đã encode |
| “UserDetails có thể trả trực tiếp lên client” | Có thể lộ hash và metadata nhạy cảm |
| “authenticated() thay cho quyền trên object” | Cần role và kiểm tra owner/tenant |

## 11. Bài tập tự kiểm tra

1. MapReactiveUserDetailsService thực thi giao diện tra cứu nào, và findByUsername trả về kiểu gì?
2. Khi username tồn tại nhưng password sai, bước nào từ chối?
3. Vì sao không so sánh hai hash BCrypt tạo từ cùng raw password bằng equals?
4. roles("ADMIN") và authorities("ROLE_ADMIN") khác nhau ở cách biểu diễn nào?
5. Vì sao người dùng reader đăng nhập đúng nhưng nhận 403 tại /admin/report?
6. Nếu một controller nhận username do client gửi rồi gọi users.findByUsername(username), nó đã xác thực người gửi chưa?
7. Điều gì xảy ra khi ứng dụng restart sau khi updatePassword của Map?
8. Tại sao HTTP Basic cần TLS dù dùng Base64?
9. Nên dùng StepVerifier hay WebTestClient để kiểm tra trực tiếp findByUsername?
10. Khi nào cần chuyển sang repository reactive hoặc Identity Provider?
11. Cần cấu hình gì để endpoint mới không mặc nhiên public?
12. Vì sao không trả trực tiếp UserDetails như một API response?

**Đáp án gợi ý:** (1) ReactiveUserDetailsService và Mono<UserDetails>; (2) manager/PasswordEncoder kiểm tra credential; (3) salt; dùng matches; (4) roles thêm tiền tố ROLE_ theo quy ước; (5) thiếu ROLE_ADMIN; (6) chưa, client tự khai được username; (7) thay đổi runtime bị mất vì bean tái tạo; (8) Base64 không bảo vệ đường truyền; (9) StepVerifier, còn WebTestClient kiểm tra HTTP end-to-end; (10) khi cần persistence, quản trị, multi-instance, MFA/SSO; (11) quy tắc authorizeExchange với mặc định an toàn; (12) có thể lộ password hash hoặc trạng thái nội bộ.

## 12. Tài liệu đối chiếu

- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security Javadoc — MapReactiveUserDetailsService: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html
- Spring Security Javadoc — ReactiveUserDetailsService: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html

**Kết luận:** tạo UserDetails với password đã được BCrypt encode và authorities rõ ràng, đặt các user trong bean **MapReactiveUserDetailsService**, rồi dùng **SecurityWebFilterChain** để bật cơ chế authentication và authorization. Tra cứu username, xác thực credential và kiểm tra quyền là ba bước riêng; lớp lưu RAM giúp học cơ chế reactive nhưng không thay thế một kho danh tính production.