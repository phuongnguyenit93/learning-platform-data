# Spring Security Reactive là gì và giải quyết vấn đề nào trong ứng dụng WebFlux?

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
- Giải thích Spring Security Reactive là gì và vì sao ứng dụng Spring WebFlux cần một lớp bảo mật tương thích với mô hình reactive.
- Phân biệt **xác thực (authentication)**, **phân quyền (authorization)** và việc lưu/lan truyền thông tin bảo mật trong một luồng Reactor.
- Mô tả đường đi của một HTTP request qua **SecurityWebFilterChain** trước khi đến handler WebFlux.
- Cấu hình một API có endpoint công khai, endpoint cần đăng nhập và endpoint chỉ dành cho vai trò ADMIN; dự đoán đúng mã phản hồi HTTP 200, 401 và 403.
- Nhận diện các giới hạn của ví dụ học tập và những lưu ý khi áp dụng với JWT, session, CSRF, CORS và các nguồn dữ liệu reactive.

## 2. Bối cảnh: WebFlux đã xử lý HTTP, vì sao còn cần Security?

**Spring WebFlux** là web stack của Spring hỗ trợ xử lý bất đồng bộ và kiểu dữ liệu reactive như \`Mono<T>\` (0–1 kết quả) và \`Flux<T>\` (0–n kết quả). Một request có thể đi qua nhiều giai đoạn không đồng bộ; công việc không nhất thiết luôn chạy trên cùng một thread.

WebFlux chịu trách nhiệm những việc như định tuyến, gọi controller/handler, chuyển đổi dữ liệu và tạo HTTP response. Riêng việc một caller **là ai, được làm gì, và truy cập tài nguyên nào** là chính sách bảo mật cần được thực thi nhất quán. Nếu tự viết kiểm tra tài khoản trong từng controller, ứng dụng dễ bỏ sót endpoint, lặp logic, khó kiểm thử và khó xử lý nhất quán lỗi xác thực.

**Spring Security Reactive** là khả năng bảo mật của Spring Security dành cho WebFlux. Nó cung cấp cơ chế nhận diện người gọi, kiểm tra quyền truy cập và tích hợp với luồng xử lý reactive thông qua các **WebFilter**, trong đó cấu hình trung tâm thường là một hoặc nhiều bean \`SecurityWebFilterChain\`.

Vấn đề mà nó giải quyết không chỉ là “thêm màn hình đăng nhập”:

| Vấn đề trong API WebFlux | Spring Security Reactive hỗ trợ |
| --- | --- |
| Người lạ gọi API chứa thông tin riêng tư | Yêu cầu xác thực trước khi truy cập |
| Người đã đăng nhập gọi chức năng ngoài quyền hạn | Đánh giá quyền theo đường dẫn, HTTP method, role/authority hoặc method |
| Mỗi controller tự kiểm tra token và trả lỗi khác nhau | Tập trung chính sách vào security filter chain và các cơ chế xác thực chung |
| Thực thi reactive đổi thread giữa các bước | Cung cấp \`ReactiveSecurityContextHolder\` dựa trên **Reactor Context** |
| Ứng dụng cần HTTP Basic, OAuth2/JWT hoặc OAuth2 Login | Có các thành phần tích hợp tương ứng, tùy dependency và cấu hình |
| Cần các biện pháp bảo mật web thông dụng | Có thể cấu hình security headers, CSRF, CORS integration và quản lý security context |

**Ranh giới quan trọng:** Spring Security **không tự bảo đảm** rằng mọi mật khẩu được lưu an toàn, mọi truy vấn DB không blocking, mọi nghiệp vụ đã kiểm tra chủ sở hữu dữ liệu, hoặc hệ thống tự động chống được mọi kiểu tấn công. Các chính sách và thành phần thực tế vẫn phải được thiết kế đúng.

## 3. Ba khái niệm cốt lõi

### 3.1. Authentication — xác thực “bạn là ai?”

Authentication kiểm tra thông tin chứng minh danh tính, chẳng hạn cặp username/password, HTTP Basic credentials hoặc JWT hợp lệ. Kết quả là một đối tượng \`Authentication\` chứa principal (người gọi), trạng thái xác thực và authorities.

Ví dụ: request gửi \`Authorization: Basic ...\`. Spring Security giải mã thông tin HTTP Basic, xác minh thông tin đăng nhập bằng cơ chế đã cấu hình, rồi tạo thông tin xác thực cho request. HTTP Basic chỉ là cơ chế minh họa thuận tiện; dữ liệu đăng nhập thật phải được bảo vệ bằng HTTPS.

### 3.2. Authorization — phân quyền “bạn được làm gì?”

Sau khi biết người gọi là ai, Spring Security so sánh quyền của họ với chính sách truy cập. Ví dụ:
- \`/public\`: mọi người đều được xem.
- \`/profile\`: phải được xác thực.
- \`/admin\`: phải có role \`ADMIN\`.

\`hasRole("ADMIN")\` theo quy ước mặc định kiểm tra authority \`ROLE_ADMIN\`; còn \`hasAuthority("SCOPE_read")\` kiểm tra chính xác authority \`SCOPE_read\`. Với JWT, cách chuyển claim thành authority cần được cấu hình hoặc hiểu đúng theo cơ chế đang dùng.

### 3.3. SecurityContext — thông tin xác thực của luồng xử lý

\`SecurityContext\` giữ \`Authentication\`. Trong Spring MVC/Servlet, nhiều ví dụ quen dùng \`SecurityContextHolder\` cùng chiến lược dựa trên \`ThreadLocal\`. Với WebFlux, không được giả định một request luôn ở một thread.

Spring Security Reactive dùng **Reactor Context** để gắn thông tin bảo mật với chuỗi xử lý reactive. Truy cập nó qua \`ReactiveSecurityContextHolder.getContext()\`, vốn trả về \`Mono<SecurityContext>\`. Context được lan truyền trong luồng Reactor được nối đúng cách, kể cả khi có chuyển thread; nó không tự lan truyền qua một tác vụ tự tách khỏi pipeline hoặc thư viện blocking tùy tiện.

## 4. Một HTTP request được bảo vệ như thế nào?

Luồng khái quát:

1. HTTP request đến server chạy WebFlux.
2. Security \`WebFilter\` chọn **SecurityWebFilterChain** phù hợp với request. Một ứng dụng có thể có nhiều chain với matcher và thứ tự ưu tiên khác nhau.
3. Các filter bảo mật áp dụng những bước liên quan như đọc credentials/token, kiểm tra authentication, thiết lập security context hoặc áp dụng các biện pháp bảo vệ khác.
4. Bộ phận authorization đối chiếu request với quy tắc đã khai báo.
5. Nếu được phép, request tiếp tục đến \`DispatcherHandler\`, controller/functional handler và service.
6. Handler trả về \`Mono\`/\`Flux\`; WebFlux hoàn thiện response. Nếu request không đủ điều kiện bảo mật, quá trình có thể dừng sớm với lỗi HTTP tương ứng.

~~~text
Client
  |
  v
WebFlux HTTP server
  |
  v
Security WebFilter chain
  |-- Xác thực / tạo Authentication khi cần
  |-- Reactor SecurityContext
  |-- Kiểm tra quyền theo request
  |
  +-- Chưa xác thực, tài nguyên yêu cầu login --> 401 Unauthorized
  +-- Đã xác thực nhưng thiếu quyền ---------> 403 Forbidden
  |
  v
WebFlux handler/controller --> reactive service --> HTTP response
~~~

Đây là sơ đồ khái quát để hiểu trách nhiệm; thứ tự các filter thực tế còn phụ thuộc cấu hình. \`SecurityWebFilterChain\` thuộc **WebFlux**, khác với \`SecurityFilterChain\` dựa trên Servlet và các \`OncePerRequestFilter\` thường gặp trong Spring MVC. Không thay thế hai loại này cho nhau.

## 5. Ví dụ chạy được: API WebFlux với public, private và admin

Ví dụ dùng **Java 17**, **Spring Boot 3.3.13** và **Gradle** để có bộ phiên bản tái lập khi học. Đây là phiên bản minh họa; dự án triển khai thực tế nên chọn một nhánh Spring Boot đang được hỗ trợ và kiểm tra cập nhật bảo mật. Ví dụ chỉ có các endpoint HTTP GET để tập trung vào authentication và authorization.

Cấu trúc:

~~~text
webflux-security-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── DemoApplication.java
    ├── SecurityConfig.java
    └── GreetingController.java
~~~

**\`settings.gradle\`**

~~~groovy
rootProject.name = 'webflux-security-demo'
~~~

**\`build.gradle\`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

\`spring-boot-starter-webflux\` cung cấp web stack reactive; \`spring-boot-starter-security\` đưa Spring Security và tích hợp bảo mật phù hợp vào ứng dụng. Chưa cần thêm \`spring-boot-starter-web\` cho ví dụ này.

**\`src/main/java/demo/DemoApplication.java\`**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**\`src/main/java/demo/GreetingController.java\`**

~~~java
package demo;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("Noi dung cong khai");
    }

    @GetMapping("/private")
    public Mono<String> privateEndpoint() {
        return Mono.just("Noi dung can dang nhap");
    }

    @GetMapping("/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("Khu vuc quan tri");
    }

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "Xin chao, "
                        + context.getAuthentication().getName());
    }
}
~~~

\`/me\` đọc danh tính từ **reactive security context** của request. Nó không tự đọc \`ThreadLocal\`, và chỉ được khai báo cho caller đã đăng nhập ở cấu hình bên dưới. Chuỗi response trong code cố ý dùng ASCII để kết quả \`curl\` dễ so sánh nguyên văn; phần giải thích vẫn dùng tiếng Việt đầy đủ dấu.

**\`src/main/java/demo/SecurityConfig.java\`**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    public MapReactiveUserDetailsService userDetailsService() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}demo123")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Ý nghĩa từng quy tắc:**
- \`permitAll()\`: cho phép \`GET /public\` dù chưa đăng nhập; request vẫn đi qua security filter chain.
- \`hasRole("ADMIN")\`: \`/admin\` yêu cầu quyền \`ROLE_ADMIN\`. Tài khoản \`reader\` không có quyền này.
- \`anyExchange().authenticated()\`: các endpoint còn lại, gồm \`/private\` và \`/me\`, yêu cầu authentication.
- \`httpBasic(...)\`: bật xác thực HTTP Basic để dùng \`curl -u\` trong bài.
- \`formLogin(...disable)\`: tắt màn hình đăng nhập HTML vì ví dụ dùng API.
- \`MapReactiveUserDetailsService\`: nguồn user **trong bộ nhớ** cho demo, không đại diện cho cơ sở dữ liệu sản xuất.

**Cảnh báo với \`{noop}\`:** Nó yêu cầu bộ mã hóa mật khẩu không hash, chỉ nhằm giúp kiểm chứng flow cục bộ. Không sử dụng mật khẩu hard-code hoặc \`{noop}\` trong sản phẩm thật. Hãy dùng password encoder mạnh (như BCrypt/Argon2 theo cấu hình phù hợp), quản lý secrets đúng cách và một kho tài khoản an toàn. Ví dụ cũng không bỏ cấu hình CSRF mặc định; các endpoint đều GET, không thực hiện thay đổi trạng thái.

### Chạy và quan sát kết quả

Từ thư mục dự án, dùng Gradle đã cài (hoặc \`./gradlew\` nếu dự án có Gradle Wrapper):

~~~bash
gradle bootRun
~~~

Mở terminal khác, thực hiện:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u reader:demo123 http://localhost:8080/private
curl -i -u reader:demo123 http://localhost:8080/admin
curl -i -u admin:demo123 http://localhost:8080/admin
curl -i -u reader:demo123 http://localhost:8080/me
~~~

Kỳ vọng đối với các lệnh trên, theo đúng thứ tự:

| Lời gọi | HTTP status | Body/ý nghĩa |
| --- | --- | --- |
| \`GET /public\`, không credentials | **200 OK** | \`Noi dung cong khai\` |
| \`GET /private\`, không credentials | **401 Unauthorized** | Cần đăng nhập; HTTP Basic có thể trả \`WWW-Authenticate\` |
| \`GET /private\`, \`reader\` | **200 OK** | \`Noi dung can dang nhap\` |
| \`GET /admin\`, \`reader\` | **403 Forbidden** | Đã xác thực nhưng không có role ADMIN |
| \`GET /admin\`, \`admin\` | **200 OK** | \`Khu vuc quan tri\` |
| \`GET /me\`, \`reader\` | **200 OK** | \`Xin chao, reader\` |

Các header và phần thân lỗi do framework tạo có thể khác nhau theo phiên bản/cấu hình; bảng chỉ chốt status và body của các request thành công. Có thể kiểm tra thêm \`curl -i -u reader:sai-mat-khau http://localhost:8080/private\`: phải bị từ chối xác thực, thông thường là **401**.

**Phân biệt 401 và 403:** 401 thường có nghĩa là chưa có authentication hợp lệ để vào tài nguyên được bảo vệ (thiếu hoặc sai credentials). 403 có nghĩa là quyền truy cập bị cấm, điển hình khi caller đã xác thực nhưng không đủ quyền. Đây là hành vi mong đợi của cấu hình demo; cách xử lý lỗi có thể được tùy biến.

### Vì sao ví dụ này vẫn là “reactive”?

Controller trả \`Mono<String>\` và thành phần user details là \`MapReactiveUserDetailsService\`. Spring Security giữ thông tin đăng nhập trong chuỗi Reactor của request, để downstream handler có thể đọc bằng \`ReactiveSecurityContextHolder\`.

Điều đó **không** có nghĩa bất kỳ đoạn code nào trong ứng dụng cũng tự động non-blocking. Ví dụ, gọi JDBC blocking, \`Thread.sleep\`, \`block()\` hoặc một SDK đồng bộ trên event-loop vẫn có thể làm nghẽn khả năng xử lý đồng thời. Khi kết nối một kho người dùng bên ngoài, cần lựa chọn API/trình điều khiển phù hợp và xử lý I/O blocking ngoài event-loop khi thật sự cần.

## 6. Nhìn sâu hơn vào vai trò của các thành phần

| Thành phần | Trách nhiệm chính |
| --- | --- |
| \`ServerHttpSecurity\` | DSL để mô tả chính sách bảo mật HTTP cho WebFlux |
| \`SecurityWebFilterChain\` | Bộ filter bảo mật áp dụng cho một nhóm request |
| \`Authentication\` | Danh tính/principal cùng authorities và trạng thái xác thực |
| \`ReactiveAuthenticationManager\` | Giao diện thực hiện xác thực theo kiểu reactive, trả \`Mono<Authentication>\` |
| \`ReactiveUserDetailsService\` | Giao diện tra cứu người dùng dưới dạng reactive; \`MapReactiveUserDetailsService\` là bản trong-memory |
| \`ReactiveSecurityContextHolder\` | Đọc/ghi \`SecurityContext\` từ Reactor Context |
| \`ServerSecurityContextRepository\` | Tùy chiến lược để nạp/lưu security context, ví dụ theo WebSession |
| \`@EnableReactiveMethodSecurity\` | Bật kiểm soát quyền ở tầng method khi có yêu cầu |

Không phải ứng dụng nào cũng cần tự triển khai mọi giao diện trong bảng. Chẳng hạn, resource server xác minh JWT thường dùng cơ chế decode/validate token và chuyển claim thành authorities thay cho việc tra password qua \`ReactiveUserDetailsService\`.

### Vì sao \`SecurityContextHolder\` kiểu ThreadLocal dễ gây lỗi ở WebFlux?

Một lỗi tư duy thường gặp là đọc \`SecurityContextHolder.getContext()\` tại một điểm bất kỳ rồi tin rằng đó luôn là người dùng của request. Trong pipeline reactive, callback có thể được thực thi trên thread khác hoặc vào thời điểm khác. Hãy đọc context trong pipeline qua \`ReactiveSecurityContextHolder\`, như endpoint \`/me\` ở trên, và tránh tự gọi \`subscribe()\` để tách một công việc mà vẫn giả định context request sẽ có sẵn.

Khi cần kiểm soát quyền trên service, đừng chỉ dựa vào controller; cân nhắc \`@EnableReactiveMethodSecurity\` với \`@PreAuthorize\` trên các method reactive thích hợp. Authorization ở endpoint và ở nghiệp vụ là hai lớp bổ trợ, đặc biệt khi một service được gọi từ nhiều entry point.

## 7. Áp dụng vào một API thực tế

Giả sử ứng dụng WebFlux phục vụ đơn hàng:
- \`GET /products\`: có thể công khai nếu nghiệp vụ cho phép.
- \`GET /orders/me\`: cần đăng nhập.
- \`GET /admin/orders\`: chỉ dành cho vai trò quản trị.
- \`GET /orders/{id}\`: ngoài việc xác thực còn phải kiểm tra đơn hàng đó có thuộc người gọi hay không.

Quy tắc \`authenticated()\` chỉ trả lời “đã đăng nhập chưa”; **không** tự kiểm tra chủ sở hữu từng đơn hàng. Nếu mọi user đã đăng nhập đều được đọc \`/orders/{id}\`, có thể xảy ra lỗi truy cập tài nguyên của người khác (IDOR/BOLA). Cần kiểm tra quyền theo **đối tượng nghiệp vụ** tại service hoặc cơ chế authorization thích hợp.

Với hệ thống dùng JWT, định hướng thường gặp là:
1. Ứng dụng hoạt động như **OAuth2 Resource Server** với dependency tương ứng.
2. Cấu hình issuer/JWK và các bước kiểm tra chữ ký, thời hạn, issuer/audience theo yêu cầu.
3. Xác định chính xác cách chuyển claim/scopes thành authorities.
4. Dùng \`SecurityWebFilterChain\` để yêu cầu các authority đó theo endpoint; vẫn kiểm soát quyền sở hữu dữ liệu ở service.

Đây là hướng mở rộng, **không phải** ngụ ý chỉ thêm dependency hoặc kiểm tra một claim bằng tay là đã an toàn. JWT có thể giúp xác thực request, nhưng phân quyền đối tượng, quản lý vòng đời token và chính sách thu hồi/phiên phải được thiết kế riêng.

## 8. Những điểm an toàn và vận hành cần nhớ

**CSRF:** Spring Security có bảo vệ CSRF trong nhiều cấu hình web. Với ứng dụng dùng session/cookie hoặc cơ chế credentials mà trình duyệt tự gửi, các request thay đổi trạng thái cần chiến lược CSRF đúng. Không tắt CSRF chỉ vì “đây là REST API”. Việc có thể tắt cho một API chỉ nhận Bearer token thật sự stateless phải dựa trên mô hình đe dọa cụ thể.

**CORS:** CORS quy định nguồn gốc trang web nào được phép đọc response từ trình duyệt; nó **không thay thế authentication/authorization**. CORS phải cấu hình đúng với security chain và xử lý preflight khi API được gọi xuyên origin.

**HTTPS và credentials:** Basic gửi thông tin đăng nhập dạng mã hóa Base64, không phải mã hóa bí mật; bắt buộc dùng HTTPS ngoài môi trường thử nghiệm tin cậy. Không log password, token hoặc header Authorization. Không đặt mật khẩu production trong mã nguồn.

**Password storage:** Lưu password dưới dạng hash thích hợp; sử dụng công cụ password encoder chuẩn. Không dùng \`{noop}\` ngoài demo. Có cơ chế chống brute-force, quản lý session/token và giám sát theo nhu cầu.

**Reactive I/O:** Bảo mật không sửa được một DB/HTTP client blocking. Với lookup tài khoản hoặc token introspection, ưu tiên tích hợp reactive; nếu phải dùng API blocking, cô lập phần đó để không chiếm event-loop. Việc chuyển sang scheduler khác cũng không biến bản thân I/O thành non-blocking.

**Mặc định và thứ tự rule:** Luôn định nghĩa rule bao phủ những request chưa khớp (\`anyExchange()\`); hạn chế khai báo \`permitAll()\` quá rộng. Thứ tự matcher quan trọng: rule tổng quát đặt trước có thể khiến rule chi tiết phía sau không được áp dụng như dự kiến. Khi có nhiều \`SecurityWebFilterChain\`, cần chú ý matcher và \`@Order\`.

**Kiểm thử chính sách:** Với \`WebTestClient\`, nên kiểm tra ít nhất ba nhóm: anonymous bị 401 tại endpoint bảo vệ; user đủ quyền nhận 2xx; user sai role bị 403. Ngoài ra kiểm tra lỗi xác thực và quyền truy cập dữ liệu cụ thể. Không chỉ thử “đăng nhập thành công”.

## 9. Các lỗi phổ biến và cách tránh

| Lỗi | Hậu quả/cách xử lý |
| --- | --- |
| Mang cấu hình \`HttpSecurity\` / Servlet \`SecurityFilterChain\` sang WebFlux | Dùng \`ServerHttpSecurity\` và \`SecurityWebFilterChain\` cho reactive web stack |
| Tưởng \`authenticated()\` đồng nghĩa với “được phép xem mọi dữ liệu” | Bổ sung rule role/authority và kiểm tra quyền trên từng đối tượng |
| Dùng \`SecurityContextHolder\` ThreadLocal như trong MVC | Dùng \`ReactiveSecurityContextHolder\` bên trong reactive pipeline |
| Tự \`subscribe()\` hoặc \`block()\` tùy tiện | Duy trì chuỗi \`Mono\`/\`Flux\`; chỉ đưa blocking code sang nơi phù hợp khi bất khả kháng |
| Nhầm \`hasRole("ADMIN")\` với \`hasAuthority("ADMIN")\` | Nhớ role thường được ánh xạ thành \`ROLE_ADMIN\`; authority kiểm tra chuỗi đã khai báo |
| Chỉ nhìn HTTP 200 và bỏ qua ca unauthorized/forbidden | Viết các bài kiểm thử 401, 403 và kiểm tra quyền sở hữu đối tượng |
| Tắt CSRF hoặc mở CORS \`*\` không xét cách browser gửi credentials | Thiết kế theo authentication flow thực tế và nguyên tắc quyền tối thiểu |
| Dùng \`{noop}\`, mật khẩu mặc định, token ghi log | Chỉ dùng credential demo cục bộ; thay bằng bảo vệ và quản lý production đúng cách |

## 10. Tự kiểm tra hiểu bài

1. Nếu người chưa đăng nhập gọi \`/private\`, vì sao cấu hình ví dụ trả 401? Nếu \`reader\` gọi \`/admin\`, vì sao trả 403?
2. Vì sao \`ReactiveSecurityContextHolder\` phù hợp với WebFlux hơn việc phụ thuộc vào \`ThreadLocal\`?
3. Vì sao \`authenticated()\` chưa đủ để bảo vệ \`GET /orders/{id}\`?
4. Khi chuyển từ HTTP Basic demo sang JWT, phần nào vẫn giữ vai trò chính sách truy cập, và những điều kiện kiểm tra token nào phải được thiết kế thêm?
5. Nếu \`/public\` cần được gọi từ trình duyệt khác origin, có thể thay \`permitAll()\` bằng cấu hình CORS không? Vì sao?

**Ghi nhớ:** Spring Security Reactive là lớp **xác thực, phân quyền và quản lý security context theo mô hình reactive** cho ứng dụng WebFlux. Nó đặt chính sách an ninh xuyên suốt trước các handler, đồng thời cho phép downstream code truy cập danh tính an toàn trong chuỗi Reactor. Bảo mật hoàn chỉnh vẫn cần quyền ở tầng nghiệp vụ, cấu hình web đúng, hạ tầng lưu trữ an toàn và kiểm thử các trường hợp bị từ chối.

**Tài liệu chính thức để đào sâu:**
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html