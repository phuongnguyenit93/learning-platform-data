# Thứ tự quy tắc và nguyên tắc áp dụng quy tắc khớp đầu tiên trong phân quyền HTTP

Trong **Spring Security Servlet**, nhiều HTTP authorization rules có thể cùng mô tả một request. Một lỗi phổ biến là đặt quy tắc tổng quát trước quy tắc cụ thể và cho rằng framework sẽ tự chọn quy tắc “chặt nhất” hoặc “đường dẫn dài nhất”. Với cấu hình `authorizeHttpRequests` theo danh sách `requestMatchers`, hãy ghi nhớ nguyên tắc:

> **Quy tắc đầu tiên có RequestMatcher khớp với HTTP request được dùng để đưa ra quyết định authorization.** Các quy tắc phía sau không còn được xét cho cùng bước quyết định đó, ngay cả khi quy tắc đầu tiên từ chối quyền.

Bên cạnh đó còn có **một cấp độ thứ tự khác**: khi khai báo **nhiều `SecurityFilterChain`**, `FilterChainProxy` chọn **chain đầu tiên** có `securityMatcher` khớp request. Sau khi chọn chain, các quy tắc authorization thuộc **chain được chọn** mới được đánh giá. Đây là hai nguyên tắc “first-match” có liên quan nhưng **khác phạm vi**.

Bài viết tập trung vào **thứ tự quy tắc và first-match semantics trong phân quyền HTTP**; ví dụ dùng Java 17+, Spring Security 6.x, Spring Boot 3.3.5 và MockMvc. Các đoạn minh họa không độc lập được ghi rõ; ví dụ project hoàn chỉnh có thể chạy bằng Gradle khi có các dependencies tương ứng.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Giải thích cách Spring Security xét danh sách authorization matchers **theo thứ tự khai báo**.
2. Phân biệt **request matcher khớp** với **điều kiện quyền được chấp nhận**; từ chối ở rule đầu không có nghĩa chạy tiếp xuống rule sau.
3. Biết đặt quy tắc **cụ thể/chặt** trước quy tắc **rộng/chung**, và đặt `anyRequest()` ở cuối.
4. Phân biệt `securityMatcher(...)` để **chọn SecurityFilterChain** với `requestMatchers(...)` trong `authorizeHttpRequests` để **chọn authorization rule**.
5. Kiểm tra ảnh hưởng của HTTP method, đường dẫn, role, authority, rule chồng lấn, CSRF và filter chain order.
6. Viết test chứng minh các trường hợp 200/201/401/403 và phát hiện quyền bị mở ngoài ý muốn.
7. Có quy trình review và test regression khi thêm endpoint hoặc refactor security configuration.

## 2. Ba câu hỏi của một HTTP request

Một request đi qua Spring Security thường phải trả lời ba câu hỏi theo các lớp xử lý khác nhau:

**Câu hỏi A – Request vào chain nào?** `FilterChainProxy` dùng `SecurityFilterChain.securityMatcher` và **thứ tự các chain** để chọn tập filter bảo vệ request.

**Câu hỏi B – Request cần quyền gì?** Trong một chain có `AuthorizationFilter` và `authorizeHttpRequests`, danh sách `requestMatchers` được xét **theo thứ tự**, chọn quy tắc đầu tiên khớp.

**Câu hỏi C – Chủ thể có đủ quyền không?** Quy tắc vừa chọn sẽ kiểm tra `Authentication`, authorities, role hoặc logic của `AuthorizationManager` để cho phép/từ chối. Nếu đã chọn quy tắc và kết quả là deny, **không có bước tìm quy tắc tiếp theo “dễ hơn”**.

Sơ đồ:

~~~text
HTTP request
    |
    v
FilterChainProxy
    |
    +-- SecurityFilterChain @Order(1) securityMatcher -> khớp? 
    |       +-- Có: CHỌN CHAIN 1; không xét chain 2/3
    |       +-- Không: xét tiếp chain kế
    |
    +-- SecurityFilterChain @Order(2) securityMatcher -> khớp?
    |       +-- Có: CHỌN CHAIN 2
    |       +-- Không: xét tiếp
    |
    v
Trong chain đã chọn:
    AuthorizeHttpRequests / RequestMatcherDelegatingAuthorizationManager
    |
    +-- rule 1 requestMatcher -> khớp?  Có -> quyết định grant/deny
    |                                      KHÔNG xét rule 2
    +-- rule 2 requestMatcher -> khớp?  Có -> quyết định grant/deny
    +-- rule 3 requestMatcher -> ...
    +-- anyRequest() -> fallback rõ ràng nếu được cấu hình
    |
    v
Cho phép -> controller; từ chối -> security exception/entry point
~~~

**Lưu ý:** Các filter khác như `CsrfFilter` và authentication filters cũng chạy theo cấu hình chain. Một 403 có thể đến từ CSRF **trước** khi authorization rule được xét; không kết luận rằng `hasRole` gây lỗi chỉ từ HTTP status.

## 3. Một ví dụ về sai thứ tự

Xét hai đường dẫn:

- `GET /api/products/42`: user đã đăng nhập được xem.
- `GET /api/admin/audit`: chỉ admin được xem.

Cấu hình **SAI** sau đưa rule chung lên trước:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
~~~

Cả `/api/products/42` và `/api/admin/audit` đều khớp `"/api/**"`. Với `/api/admin/audit`, Spring Security dừng chọn rule ngay tại `authenticated()`. Một user bất kỳ đã đăng nhập có thể qua authorization HTTP, dù rule admin nằm ở dòng dưới!

**Rule admin không hề có cơ hội được xét.** Không có logic ngầm “rule nào cụ thể hơn” hoặc “role nào mạnh hơn” nếu rule phía trên đã match.

Cấu hình **ĐÚNG** cho ý định trên:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
~~~

Thứ tự mới:

1. `GET /api/admin/audit` khớp rule admin đầu tiên → phải có `ROLE_ADMIN`.
2. `GET /api/products/42` không khớp rule admin, khớp rule `/api/**` → cần authenticated.
3. `GET /other` không khớp hai rule trên → `anyRequest().denyAll()`.

### 3.1. Trường hợp deny trước, permit sau

Xét:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").denyAll()
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().denyAll())
~~~

Dù endpoint `/api/public/ping` được khai “permitAll” ở dòng thứ hai, nó đã khớp `/api/**` phía trên và bị `denyAll()`. **Deny không khiến framework thử rule thứ hai.**

Để public thực sự public:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/**").denyAll()
    .anyRequest().denyAll())
~~~

Tương tự, một `permitAll()` quá rộng ở đầu có thể vô hiệu việc hạn chế admin bên dưới. Kết quả phụ thuộc **rule khớp đầu tiên**, không phụ thuộc các rule phía sau “mạnh hơn” hay “yếu hơn”.

### 3.2. Bảng kiểm tra thứ tự trực quan

Cùng các rule sau:

~~~java
.requestMatchers("/api/public/**").permitAll()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
~~~

| Request | Matcher khớp đầu tiên | Quyết định cần kiểm tra |
| --- | --- | --- |
| GET /api/public/ping | /api/public/** | `permitAll()` |
| GET /api/admin/audit | /api/admin/** | `hasRole("ADMIN")` |
| GET /api/products/42 | /api/** | `authenticated()` |
| GET /private | anyRequest | `denyAll()` |

Không phải path dài nhất tự thắng. Cấu hình này hoạt động **vì người viết đã đặt matcher cụ thể ở trước matcher bao phủ rộng hơn**.

## 4. “Khớp” và “được phép” là hai bước độc lập

Mỗi rule trong `authorizeHttpRequests` về bản chất gồm:

1. Một `RequestMatcher` quyết định request có thuộc nhóm cần đánh giá không.
2. Một `AuthorizationManager`/policy quyết định principal hiện tại có đủ quyền cho request đã match hay không.

Ví dụ:

~~~java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
~~~

Với user thường truy cập `/api/admin/audit`:

- Rule đầu tiên **match đường dẫn**.
- Rule đầu yêu cầu `ROLE_ADMIN`, user không có → **deny**.
- Rule thứ hai **không được xét**, dù user chắc chắn đáp ứng `authenticated()`.

Đây là đặc tính quan trọng giúp không thể “rơi xuống” rule dễ hơn sau khi thất bại ở rule chặt. Nếu bạn chứng kiến API admin bị mở, nguyên nhân thường là một **rule bao phủ rộng đã match trước** chứ không phải framework fallback sau khi deny.

### 4.1. `hasRole` khác `hasAuthority`

- `hasRole("ADMIN")` mặc định kiểm tra authority có tiền tố `ROLE_`, ví dụ `ROLE_ADMIN`.
- `hasAuthority("SCOPE_orders.read")` kiểm tra **chuỗi authority chính xác**, không tự thêm `ROLE_` hay `SCOPE_`.
- `authenticated()` chỉ yêu cầu một principal được xác thực theo trust model của Spring Security, không kiểm tra role cụ thể.
- `fullyAuthenticated()` khác `authenticated()` ở việc không chấp nhận remember-me-only authentication làm full authentication.
- `permitAll()` không yêu cầu principal có authentication cho rule đó, nhưng **không tắt toàn bộ filter chain**.
- `denyAll()` luôn từ chối tại rule tương ứng.

Ví dụ role sai tiền tố có thể gây 403 ngay cả khi first-match đúng. Khi debug, hãy kiểm tra cả **matcher nào được chọn** và **authorities thực tế của user**; không chỉ nhìn thứ tự.

## 5. HTTP method cũng thuộc điều kiện khớp

Đường dẫn có thể đúng nhưng method khác sẽ dẫn đến rule khác.

Ví dụ nghiệp vụ đơn hàng:

- `GET /api/orders/42`: yêu cầu `SCOPE_orders.read`.
- `POST /api/orders`: yêu cầu `SCOPE_orders.write`.
- `DELETE /api/orders/42`: không được mở nếu chưa có quy tắc riêng.

Quy tắc minh họa:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/*")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers("/api/orders", "/api/orders/**")
        .denyAll()
    .anyRequest().denyAll())
~~~

Với request `GET /api/orders/42`, rule đầu match cả method/path. Với `POST /api/orders`, rule GET không match method, rule POST match và yêu cầu write. Với `DELETE /api/orders/42`, hai rule đầu không match method, rule denyAll chặn request.

**Chú ý:** Trong ứng dụng web có CSRF protection, POST/PUT/PATCH/DELETE có thể bị `CsrfFilter` từ chối do thiếu CSRF token **trước khi** rule method-aware được kiểm tra. Để test riêng authorization cho POST, sử dụng token hợp lệ hoặc một test fixture được cấu hình đúng; không tắt CSRF rộng trong production để test cho tiện.

### 5.1. Nếu bỏ method sẽ thế nào?

Cấu hình sau thường **quá rộng**:

~~~java
.requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
~~~

Nó không biểu diễn “chỉ được đọc”. Matcher chỉ nêu path, nên các HTTP methods khác đến đường dẫn đó có thể cũng khớp; nếu user có `SCOPE_orders.read` và controller có thêm POST/DELETE tương ứng, authorization HTTP có thể cho phép hành động không mong muốn. Một filter khác (như CSRF) có thể chặn một số request, nhưng **không được dùng CSRF như biện pháp thay thế cho quyền write/delete**.

Hãy đặt HTTP method matcher khi mục tiêu phân quyền phụ thuộc method và xác định rõ fallback cho methods chưa hỗ trợ.

### 5.2. Kiểu path pattern và độ phủ thực tế

Trong Spring MVC, dạng `"/api/orders/*"` chỉ minh họa một segment sau `/api/orders/`, còn `"/api/orders/**"` thường mô tả phạm vi rộng hơn. Nhưng semantics matcher thực tế có thể phụ thuộc Spring Security version, loại `RequestMatcher`, cấu hình Spring MVC/servlet path và cách framework chuẩn hóa đường dẫn. Không suy luận từ regex hay JavaScript glob; hãy test với matcher **thực tế trong ứng dụng**.

Đặc biệt cần kiểm tra:

- Có context path khác root hay không.
- Có nhiều `DispatcherServlet` hoặc servlet path tùy chỉnh không.
- Trailing slash, path variables, dấu chấm, URL encoding và semicolon/path parameters.
- Case sensitivity theo matcher và hạ tầng proxy.
- Một đường dẫn có khớp `/api/orders/**` khi không có thêm segment hay không; nếu quan trọng, khai báo rõ cả `"/api/orders"` như ví dụ.
- Forward/error dispatch từ Spring MVC đi qua security chain như thế nào.

Không cấu hình “trông giống” rồi tin rằng mọi case đã match như ý. **RequestMatcher là điều kiện do framework đánh giá trên HTTP request**, không phải danh sách đường dẫn do developer suy ra từ tên controller.

## 6. Vị trí của `anyRequest()` và chính sách mặc định

`anyRequest()` biểu diễn fallback cho request không match các rule cụ thể phía trên. Trong cấu hình theo danh sách, đặt ở **cuối**:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/actuator/health").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
~~~

Không đặt `anyRequest().permitAll()` ở đầu và kỳ vọng rule bên dưới có hiệu lực; nó sẽ bao phủ mọi request trước khi xét các rule khác. API DSL cũng có những hạn chế đối với việc tiếp tục khai rule sau `anyRequest()`.

### 6.1. Default deny thay vì default permit

Với API có dữ liệu nhạy cảm, chính sách an toàn thường là:

~~~java
.anyRequest().denyAll()
~~~

Nhờ đó endpoint mới **không tự được mở** khi developer thêm controller mà quên cập nhật authorization rules. Nếu chọn `anyRequest().authenticated()`, mọi endpoint mới chỉ cần đã đăng nhập là qua bước authorization chung, có thể vượt mong muốn đối với endpoint admin hoặc thao tác đặc biệt.

Chọn `denyAll()` làm fallback không khiến quyền của các rule phía trên bị “ghi đè”: nó chỉ được xét nếu chưa có matcher nào match trước đó.

### 6.2. Rule quá rộng ngay trước fallback

Ví dụ:

~~~java
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
~~~

Fallback denyAll **không bảo vệ** các endpoint mới dưới `/api/**` khỏi rule `authenticated()` quá chung. Nếu sau này có controller `POST /api/admin/create-user` mà không thêm rule admin ở trên, user thường đã authenticated có thể qua HTTP authorization step. Nên cân nhắc whitelist endpoint/method cụ thể hoặc tách nhóm `/api/admin/**` ở trước rule chung.

### 6.3. Khi không có matcher nào match?

Tùy phiên bản và cách xây dựng AuthorizationManager, hành vi khi không có rule match có thể khác hoặc bị cấu hình theo contract không hiển nhiên. Đừng dựa vào “mặc định đoán được” để bảo vệ API. Khai báo **fallback rõ ràng** bằng `anyRequest().denyAll()` và kiểm thử đường dẫn ngoài danh sách.

## 7. Hai cấp first-match: filter chain và authorization rule

Nếu chỉ có một `SecurityFilterChain`, việc review order thường tập trung vào `requestMatchers`. Nhưng khi có nhiều chain, còn một quyết định sớm hơn.

### 7.1. Chọn SecurityFilterChain bằng `securityMatcher`

Ví dụ **mẫu minh họa độc lập**, không ghép vào project đơn-chain ở mục 8:

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Cần đặt các methods trong Spring `@Configuration`, import `Bean`, `Order`, `HttpSecurity`, `SecurityFilterChain` và `Customizer`. Đừng copy ba bean này bên cạnh bean đơn-chain mà không xác định lại policy; các mẫu là **hai phương án khác nhau**.

Với `/api/admin/audit`:

1. `adminChain` match đầu tiên theo `@Order(1)` → được chọn.
2. Trong adminChain, `anyRequest().hasRole("ADMIN")` → user phải có ROLE_ADMIN.
3. `apiChain` cũng **có thể match URL**, nhưng không được chọn vì chain trước đã match.

Nếu đảo thứ tự hai chain, `apiChain` tổng quát có thể thắng trước và chỉ yêu cầu authenticated, làm giảm bảo vệ admin. **Đây là lỗi cấp chain**, kể cả bên trong adminChain các rules đã sắp rất đúng.

### 7.2. Một chain đã chọn không có nghĩa sẽ thử chain khác khi deny

Khi chain đầu tiên phù hợp được chọn và authorization từ chối, Spring Security **không chuyển request sang chain thứ hai** để tìm rule dễ hơn. Việc lựa chọn filter chain là **first-match**, không phải “thử đến khi chain nào cho qua”.

Tương tự, khi rule đầu tiên match nhưng deny, framework không thử rule kế trong cùng chain.

Hai lớp quyết định có cấu trúc giống nhau nhưng khác chức năng:

| Cấp | Thành phần chọn | Điều kiện | Nếu match | Nếu bị từ chối |
| --- | --- | --- | --- | --- |
| Filter chain | `FilterChainProxy` | `securityMatcher` và order của chain | Chạy filters của chain đầu tiên khớp | Không rơi sang chain kế |
| HTTP authorization rule | `RequestMatcherDelegatingAuthorizationManager` / cấu hình `authorizeHttpRequests` | `requestMatchers` theo thứ tự | Chạy authorization manager của rule đầu khớp | Không rơi sang rule kế |
| Quyền/identity | `AuthorizationManager` + Authentication | Authorities, roles, status, business policy | Grant/deny trong rule đã chọn | Xử lý security exception/entry point |

### 7.3. Nếu request không khớp SecurityFilterChain nào?

Về nguyên tắc, request không được gắn vào **bất kỳ Spring Security filter chain nào** có thể không được Spring Security bảo vệ như bạn kỳ vọng. Vì thế khi dùng nhiều chains với `securityMatcher(...)`, hãy bảo đảm có **fallback chain** bao trùm các request còn lại hoặc một kiến trúc default-deny đã được kiểm chứng.

Điều này **khác** `anyRequest().denyAll()` nằm trong một chain giới hạn `securityMatcher("/api/**")`. Fallback đó chỉ bảo vệ request **đã vào chain**; nó không tự áp dụng cho `/admin/**` nằm ngoài chain.

### 7.4. @Order khác thứ tự dòng rule trong một chain

- `@Order(1)` trên SecurityFilterChain bean ưu tiên **thứ tự lựa chọn chain**.
- Thứ tự `requestMatchers` bên trong một `authorizeHttpRequests` quyết định **quy tắc HTTP**.
- `@Order` trên method/service hay filter component không tự di chuyển rule authorization.
- Controller mapping priority của Spring MVC không tự viết lại thứ tự rule bảo mật.

Đừng debug một lỗi order trong `authorizeHttpRequests` bằng cách chỉ thay `@Order` của chain, hoặc ngược lại.

## 8. Ví dụ chạy được Java 17+: policy theo đường dẫn và HTTP method

Ví dụ sau minh họa **một filter chain** có thứ tự rõ ràng và fallback deny-all. Chương trình dùng Spring Boot 3.3.5, Spring Security, HTTP Basic, MVC và MockMvc. Bộ user in-memory chỉ phục vụ bài học; password được encode bằng BCrypt.

Ứng dụng gồm:

- `GET /api/public/ping`: ai cũng truy cập.
- `GET /api/admin/metrics`: chỉ ROLE_ADMIN.
- `GET /api/orders/42`: chỉ authority SCOPE_orders.read.
- `POST /api/orders`: chỉ SCOPE_orders.write, cần CSRF token nếu gọi theo policy mặc định.
- `DELETE /api/orders/42`: có controller nhưng **bị denyAll** do chưa có rule cho phép.
- `GET /api/profile`: người dùng đã authenticated.
- Mọi request ngoài whitelist: denyAll.

### 8.1. Cấu trúc dự án

~~~text
rule-order-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/rules/
    │   ├── RuleOrderApplication.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    └── test/java/example/rules/
        └── RuleOrderTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'rule-order-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 8.2. Application

Tệp `src/main/java/example/rules/RuleOrderApplication.java`:

~~~java
package example.rules;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuleOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuleOrderApplication.class, args);
    }
}
~~~

### 8.3. SecurityConfiguration

Tệp `src/main/java/example/rules/SecurityConfiguration.java`:

~~~java
package example.rules;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                // 1. Public cụ thể trước.
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()

                // 2. Nhóm admin chặt hơn các quy tắc thông thường.
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")

                // 3. Quyền theo method và resource cụ thể.
                .requestMatchers(HttpMethod.GET, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")

                // 4. Không mở các method orders chưa liệt kê.
                .requestMatchers("/api/orders", "/api/orders/**")
                    .denyAll()

                // 5. Một endpoint cần đăng nhập, không đòi scope.
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()

                // 6. Mọi request còn lại bị từ chối.
                .anyRequest().denyAll())

            .httpBasic(Customizer.withDefaults())

            // Không disable CSRF: POST phải thỏa CSRF policy.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .authorities("ROLE_USER", "SCOPE_orders.read")
            .build();

        UserDetails writer = User.withUsername("writer")
            .password(encoder.encode("writer-pass"))
            .authorities("ROLE_USER", "SCOPE_orders.write")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .authorities("ROLE_ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, writer, admin);
    }
}
~~~

Các điểm phải đọc kỹ:

1. Rule `GET /api/public/ping` là **public và cụ thể**, không mở `POST /api/public/ping` hoặc mọi URL dưới `/api/public/**`.
2. `"/api/admin/**"` ở trước các rule khác; chỉ admin mới qua được.
3. `HttpMethod.GET` và `HttpMethod.POST` phân biệt hai mục đích read/write.
4. `"/api/orders"` và `"/api/orders/**"` ở fallback riêng để tránh các methods chưa được duyệt có thể bị mở do rule mới bao trùm.
5. `/api/profile` chỉ yêu cầu authenticated; reader, writer và admin đều đủ điều kiện.
6. `anyRequest().denyAll()` được đặt cuối, giúp endpoint mới không tự mở quyền.
7. `httpBasic` dùng để có kết quả 401 quen thuộc khi thiếu credentials ở API protected; đây là ví dụ học HTTP authorization, không khuyến nghị HTTP Basic là lựa chọn tối ưu cho mọi production API.
8. CSRF vẫn bật mặc định. Nếu request POST thiếu token, `CsrfFilter` có thể trả 403 **trước khi** đến rule write; test cần tách rõ hai loại lỗi.
9. User in-memory có role/scope khác nhau do server cấp. `.hasRole("ADMIN")` tương đương kiểm tra ROLE_ADMIN theo prefix mặc định; không cần truyền chuỗi `"ROLE_ADMIN"` vào `hasRole`.
10. Với production, bổ sung account status, user store thật, HTTPS, key/password lifecycle, logging redaction và method-level/domain-level authorization theo threat model.

### 8.4. API Controller

Tệp `src/main/java/example/rules/ApiController.java`:

~~~java
package example.rules;

import java.security.Principal;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/admin/metrics")
    public String metrics() {
        return "admin-metrics";
    }

    @GetMapping("/api/orders/{id}")
    public String order(@PathVariable long id) {
        return "order-" + id;
    }

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.CREATED)
    public String createOrder() {
        return "created";
    }

    @DeleteMapping("/api/orders/{id}")
    public String deleteOrder(@PathVariable long id) {
        return "deleted-" + id;
    }

    @GetMapping("/api/profile")
    public String profile(Principal principal) {
        return principal.getName();
    }
}
~~~

Dù controller có method `DELETE /api/orders/{id}`, không user nào được HTTP authorization rule hiện tại cho phép gọi. Điều này chứng minh **có controller mapping** không có nghĩa security cho phép request vào controller.

### 8.5. MockMvc tests kiểm chứng thứ tự

Tệp `src/test/java/example/rules/RuleOrderTests.java`:

~~~java
package example.rules;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RuleOrderTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicPingWorksAnonymously() throws Exception {
        mockMvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void orderReadWithoutAuthenticationIsUnauthorized() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanReadOrder() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("order-42"));
    }

    @Test
    void writerCannotReadOrderWithoutReadScope() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                .with(httpBasic("writer", "writer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerCanCreateOrderWithCsrf() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }

    @Test
    void writerPostWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(httpBasic("writer", "writer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerCannotCreateOrderEvenWithCsrf() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void deleteIsDeniedByOrdersFallback() throws Exception {
        mockMvc.perform(delete("/api/orders/42")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminMetrics() throws Exception {
        mockMvc.perform(get("/api/admin/metrics")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-metrics"));
    }

    @Test
    void readerCannotReadAdminMetrics() throws Exception {
        mockMvc.perform(get("/api/admin/metrics")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void profileNeedsOnlyAuthentication() throws Exception {
        mockMvc.perform(get("/api/profile")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    void unmatchedPathIsDeniedEvenForAuthenticatedUser()
            throws Exception {
        mockMvc.perform(get("/undocumented")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

### 8.6. Giải thích test theo nguyên tắc first-match

| Test case | Rule đầu tiên khớp | Expected |
| --- | --- | --- |
| GET /api/public/ping, anonymous | GET public | 200 |
| GET /api/orders/42, anonymous | GET orders read | 401 do chưa authenticated |
| GET /api/orders/42, reader | GET orders read | 200 |
| GET /api/orders/42, writer | GET orders read | 403, thiếu SCOPE_orders.read |
| POST /api/orders, writer + CSRF | POST orders write | 201 |
| POST /api/orders, writer, thiếu CSRF | Bị CsrfFilter chặn trước | 403, không phải chứng cứ rule write sai |
| POST /api/orders, reader + CSRF | POST orders write | 403, thiếu SCOPE_orders.write |
| DELETE /api/orders/42, writer + CSRF | Orders fallback denyAll | 403 |
| GET /api/admin/metrics, admin | Admin role | 200 |
| GET /api/admin/metrics, reader | Admin role | 403 |
| GET /api/profile, reader | GET profile | 200 |
| GET /undocumented, reader | anyRequest denyAll | 403 |

Những expected status này gắn với **sample config**, bao gồm HTTP Basic và CSRF. Trong ứng dụng khác, authentication entry point có thể redirect thay 401, hoặc exception handling trả JSON; tiêu chí phân quyền vẫn là có/không cấp quyền đúng với policy.

### 8.7. Lệnh chạy

Trong thư mục project có Java 17+ và Gradle tương thích:

~~~bash
gradle test
gradle bootRun
~~~

Nếu có wrapper thì dùng:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows dùng `gradlew.bat test` và `gradlew.bat bootRun`. Đây là dự án có Spring Boot libraries; chạy `javac/java` trần mà không cung cấp đầy đủ classpath sẽ không biên dịch được.

Khi ứng dụng đang chạy trên port mặc định, có thể thử GET:

~~~bash
curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/orders/42
curl -i -u reader:reader-pass \
  http://localhost:8080/api/orders/42
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin/metrics
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/metrics
~~~

Dòng `curl -u` dùng credential thử nghiệm; **không dùng cách này với password production để tránh xuất hiện trong shell history/process list**. Trong production phải có HTTPS. Để thử POST với CSRF, nên dùng MockMvc như test hoặc thiết kế client gửi token phù hợp; không tắt CSRF chỉ vì HTTP Basic request trả 403.

## 9. Debug thứ tự rule trong hệ thống thật

Một báo cáo lỗi thường có dạng: “Người dùng thường vào được API admin” hoặc “Public API bị 401/403”. Không nên sửa theo cảm tính; hãy phân tích từng cấp.

### 9.1. Xác định chain được chọn

Nếu có nhiều `SecurityFilterChain`:

1. Liệt kê các bean chain và `@Order` thực tế.
2. Kiểm tra `securityMatcher` của từng chain trên request path/method/servlet path.
3. Xác định **chain đầu tiên khớp**. Không suy ra từ tên biến bean hoặc vị trí controller.
4. Kiểm tra chain có `AuthorizationFilter` và cơ chế authentication mong muốn không.
5. Kiểm tra fallback chain bảo vệ request không khớp chain chuyên biệt.

Nếu không tìm được chain đúng, thay order của `requestMatchers` bên trong **một chain khác** sẽ không giải quyết vấn đề.

### 9.2. Xác định authorization rule khớp đầu tiên

Trong chain đã chọn:

1. Đọc danh sách `requestMatchers` đúng thứ tự.
2. Với request cụ thể, xét lần lượt method/path/dispatcher type theo matcher thật.
3. Dừng ở **matcher đầu tiên khớp**.
4. Xem authorization condition ở rule đó: `permitAll`, `authenticated`, `fullyAuthenticated`, `hasRole`, `hasAuthority`, `access` hoặc custom manager.
5. Kiểm tra principal/authorities sau authentication.
6. Phân biệt từ chối do rule với lỗi trước đó ở CSRF, session, token decoder hoặc account status.

Một rule `hasRole("ADMIN")` có thể **đúng vị trí**, nhưng user thực chỉ có `"ADMIN"` không có `"ROLE_ADMIN"` → 403. Một rule `hasAuthority("SCOPE_orders.read")` có thể không match đúng dữ liệu scopes do JWT converter ánh xạ → 403. Những lỗi đó không phải first-match bug nhưng gây triệu chứng tương tự.

### 9.3. Log và quan sát có kiểm soát

Ở môi trường học:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Dùng log để nhận biết chain/filter/authorization decisions, nhưng không dựa vào một câu log cố định giữa mọi Spring Security version. Tránh TRACE và request body dumping trên production nếu có thể lộ password, session cookie, JWT hoặc CSRF token.

Để xác nhận rule shadowing, viết một test cho request **đồng thời match hai patterns**, dùng user chỉ đáp ứng rule chung nhưng không đáp ứng rule chặt. Nếu test cho phép truy cập, bạn có thể đang đặt rule rộng trước rule chặt.

## 10. Công thức review rule chồng lấn

Một checklist review pull request hữu ích:

| Câu hỏi | Lý do |
| --- | --- |
| Rule mới có chồng lấn một rule hiện tại không? | Có thể shadow hoặc bị shadow |
| Có rule `/api/**` hoặc `/**` quá rộng xuất hiện trước rule cụ thể? | Có thể mở hoặc khóa nhầm endpoint |
| Có method-specific rules không? | Tránh READ authority được dùng cho WRITE |
| Có fallback rõ `anyRequest().denyAll()`? | Bảo vệ endpoint mới |
| Có nhiều chains và chain tổng quát được `@Order` cao hơn chain chuyên biệt? | Chain tổng quát có thể chiếm request |
| Có securityMatcher làm một nhóm URL không thuộc chain nào? | Request có thể không được bảo vệ |
| Rules phân quyền theo role/authority có dùng đúng prefix? | Tránh quyền sai hoặc 403 nhầm |
| Test có user không đủ quyền nhưng đã authenticated không? | Phát hiện rule `authenticated()` che `hasRole` |
| Test có request ẩn chứa method khác và trailing slash không? | Phát hiện matcher coverage sai |
| Có method-level và resource-ownership checks khi cần? | HTTP path rule không thay thế object authorization |

### 10.1. Điều gì xảy ra khi thêm endpoint mới?

Giả sử hiện tại có:

~~~java
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
~~~

Ngày mai một developer thêm controller `POST /api/admin/delete-all` nhưng **quên thêm rule admin**. Vì nó khớp `/api/**`, request của user thường có Authentication có thể được HTTP authorization cho phép. Đặt fallback denyAll ở sau **không sửa được** lỗ hổng này vì request đã match rule rộng.

Các cách phòng vệ:

- Thêm rule admin trước `/api/**`, và test negative case.
- Ưu tiên whitelist các nhóm endpoint/method có chủ đích thay vì general authenticated catch-all.
- Đặt các nhóm admin dưới chain chuyên biệt hoặc tách resource policy khi có nhiều cơ chế xác thực.
- Với quyền theo object như “chỉ sửa đơn hàng của mình”, bổ sung method/service authorization và ownership checks; path-based role rule không đủ.

### 10.2. Method security không đổi cơ chế first-match HTTP

`@PreAuthorize` và method authorization có thể là **lớp kiểm soát độc lập** bên cạnh HTTP authorization. Nếu HTTP cho qua request, method security còn có thể từ chối ở bước gọi service/controller tùy cấu hình. Nhưng không nên dùng method security như lý do cho phép HTTP rule quá rộng và bỏ test.

**First-match trong danh sách `authorizeHttpRequests` không có nghĩa Spring Security bỏ qua tất cả các lớp authorization khác của ứng dụng.** Nó chỉ mô tả cách chọn rule trong một cấu hình HTTP authorization manager; các filter khác, controller logic và method-level authorization vẫn có thể áp dụng.

### 10.3. Error/Forward dispatch và multi-servlet

Các request dispatcher types như `ERROR` hoặc `FORWARD` có thể đi qua security rules theo cơ chế dispatch của Servlet và cách Spring Security đăng ký filter. Một fallback denyAll có thể làm error page hoặc view forward bị chặn trong một số app. Khi cần, tạo policy cho dispatcher types phù hợp **sau khi hiểu threat model**, không mở tất cả URL chỉ vì thấy 403 trong error flow.

Ví dụ mảnh code (chỉ áp dụng nếu ứng dụng thực sự cần cho phép các dispatch types này):

~~~java
.dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR)
    .permitAll()
~~~

Cần import `jakarta.servlet.DispatcherType`. Đặt rule này có chủ đích trong danh sách; nó vẫn tuân theo **first-match**, không phải một ngoại lệ tự động có thứ tự ưu tiên cao hơn mọi rule khác.

Nếu ứng dụng có nhiều Servlet hoặc custom servlet path, cần xác định matcher type phù hợp và dùng builder/request matcher chính xác cho path scope. Một string pattern nhìn giống đúng chưa chắc phù hợp với servlet mapping; kiểm thử trên app thực.

## 11. Các lỗi thường gặp

### 11.1. “Spring chọn rule cụ thể nhất”

**Sai.** Đây là nhầm lẫn với một số hệ thống routing/cascade khác. `authorizeHttpRequests` xét các request rules theo thứ tự khai báo; phải xếp trước-sau đúng và test.

### 11.2. “Rule đầu deny nên framework thử rule tiếp”

**Sai.** Match chọn rule; quyết định grant/deny xảy ra ở rule đó. Một deny không chuyển sang rule dễ hơn.

### 11.3. “Đặt anyRequest denyAll ở cuối là đủ để bảo vệ admin”

**Không đủ** nếu trước đó đã có `"/api/**".authenticated()` bao phủ admin URL. Fallback không được xét với request đã match.

### 11.4. “Thêm hasRole sau authenticated sẽ siết quyền”

**Sai** nếu hai matcher overlap và authenticated nằm trước. Đặt rule chặt trước hoặc thiết kế lại patterns.

### 11.5. “Chỉ có một thứ tự first-match trong cả ứng dụng”

**Sai** khi có nhiều `SecurityFilterChain`. Còn có chain selection theo `@Order` và `securityMatcher` trước HTTP rule selection.

### 11.6. “Có @GetMapping thì Spring Security sẽ chỉ kiểm GET”

**Sai.** HTTP authorization matcher là quy tắc riêng; nếu đặt path-only và controller khác hỗ trợ POST ở cùng path, policy có thể không chặn POST. Nêu method trong matcher khi quyền khác nhau theo method.

### 11.7. “Một 403 luôn do thiếu role”

**Sai.** CSRF, method mismatch, custom access decisions hoặc entry point khác có thể gây 403. Phân tích filter chain, request method, token và rule.

### 11.8. “Có requestMatcher denyAll trong chain là bảo vệ toàn site”

**Sai** nếu chain có `securityMatcher` chỉ bao phủ một nhóm URL. Cần fallback chain/default deny toàn phạm vi dự kiến.

### 11.9. “Một user đã authenticated là đủ cho mọi API read/write”

Không đúng nếu business cần scopes, quyền sở hữu resource, tenant checks hoặc recent authentication. `authenticated()` chỉ là một yêu cầu xác thực, không mô hình hóa đầy đủ authorization.

### 11.10. “Đổi các rule chỉ là refactor formatting”

Không đúng khi thứ tự thay đổi. Di chuyển một rule có thể thay đổi quyền truy cập thực. Code review phải coi thay đổi order là thay đổi **security behavior**, kèm tests regression.

## 12. Bài tập áp dụng

1. Với `/api/**.authenticated()` đứng trước `/api/admin/**.hasRole("ADMIN")`, user đã authenticated nhưng không có ROLE_ADMIN có thể qua bước HTTP authorization cho `GET /api/admin/audit` không? Giải thích rule đầu khớp.
2. Nếu đặt `denyAll()` cho `/api/**` trước `permitAll()` cho `/api/public/**`, vì sao public API bị chặn?
3. Trong ba rule cho GET orders, POST orders và orders fallback denyAll, matcher nào chọn `DELETE /api/orders/42`?
4. Vì sao `POST /api/orders` với writer có đúng scope vẫn có thể 403 khi thiếu CSRF token? Kết quả đó có chứng minh scope check sai không?
5. Giải thích sự khác nhau giữa `@Order(1)` ở bean chain và thứ tự `requestMatchers` trong chain.
6. Với admin chain matcher `/api/admin/**` và general API chain matcher `/api/**`, điều gì xảy ra nếu general chain có thứ tự ưu tiên cao hơn?
7. Nếu một request không khớp SecurityFilterChain nào, `anyRequest().denyAll()` trong chain riêng `/api/**` có bảo vệ nó không?
8. Viết bảng test cho anonymous, reader, writer, admin với ít nhất sáu endpoints có scope khác nhau; đánh dấu matcher đầu khớp và response dự kiến.
9. Sửa bad config với rule `/api/**.permitAll()` để `/api/admin/**` chỉ admin và `/api/public/**` vẫn public.
10. Một developer thêm `POST /api/orders/42/cancel`. Nếu rule read hiện tại thiếu HttpMethod, có thể có rủi ro gì?
11. Vì sao HTTP authorization path rule không thể thay thế kiểm tra “order.ownerId == principal.id”?
12. Dùng test MockMvc chứng minh `hasRole("ADMIN")` mặc định kiểm `ROLE_ADMIN` chứ không phải literal `ADMIN`.
13. Phân biệt lỗi chọn chain, lỗi chọn rule và lỗi user không có authority sau khi token đã xác thực.
14. Test những biến thể path/trailing slash/encoding cần thiết trước khi dùng wildcard matcher trong API thực.
15. Với `anyRequest().denyAll()`, user có thể nhận 403 trước khi một controller chưa tồn tại trả 404 không? Giải thích thứ tự filter/controller.
16. Vì sao thay `authenticated()` bằng `fullyAuthenticated()` có thể ảnh hưởng remember-me authentication?
17. Khi ứng dụng có ERROR/FORWARD dispatch, làm sao mở đúng loại dispatch cần thiết mà không mở mọi path?
18. Code review phát hiện một rule mới chèn lên đầu danh sách `permitAll()` cho path rộng: cần kiểm thử regression nào?
19. Nếu một API hỗ trợ cả API key và JWT, đặt `securityMatcher`/chain theo thứ tự nào để tránh credential ở endpoint này trở thành bypass ở endpoint khác?
20. Viết một decision table nhỏ thể hiện với từng request: chain đầu khớp, HTTP rule đầu khớp, condition, principal authorities và kết quả.

## 13. Checklist review và production

- [ ] Liệt kê đúng thứ tự các SecurityFilterChain bean và `securityMatcher`.
- [ ] Có fallback chain bảo vệ request ngoài các chain chuyên biệt.
- [ ] Liệt kê `requestMatchers` theo thứ tự thực trong từng chain.
- [ ] Rule cụ thể/chặt đứng trước rule chồng lấn rộng hơn.
- [ ] `anyRequest()` nằm cuối và thể hiện default policy có chủ đích.
- [ ] Không dựa vào “path cụ thể nhất tự thắng” hoặc “deny sẽ fallback xuống rule sau”.
- [ ] Method-specific rules áp dụng cho read/write/delete khi quyền khác nhau.
- [ ] Có test chặn quyền của user đã authenticated nhưng thiếu role/scope.
- [ ] Có test public, admin, normal user, method không hỗ trợ và unknown path.
- [ ] CSRF tests tách khỏi authorization tests trên unsafe methods.
- [ ] User roles/authorities có prefix/mapping đúng theo AuthenticationProvider/token converter.
- [ ] Multi-tenant/resource ownership được kiểm tra ngoài path-based rules khi cần.
- [ ] Endpoint mới không được tự mở bởi matcher `/api/**` quá rộng.
- [ ] Có regression tests khi thay thứ tự rule hoặc `@Order` của chains.
- [ ] Đã kiểm tra Servlet dispatcher types và path matching behavior trong ứng dụng thật.
- [ ] Không tắt các security filters khác để “sửa” một lỗi first-match.
- [ ] Security logs không làm lộ password, headers Authorization, session cookie hoặc CSRF token.

## 14. Kết luận

Trong Spring Security Servlet, **thứ tự là một phần của chính sách bảo mật**. Khi dùng nhiều `SecurityFilterChain`, framework chọn **chain đầu tiên có securityMatcher khớp**. Bên trong chain đó, `authorizeHttpRequests` chọn **rule đầu tiên có requestMatcher khớp** và dùng authorization condition của rule ấy để quyết định cho phép/từ chối. **Nếu rule đã match nhưng deny, framework không tìm rule khác để cho qua.**

Nguyên tắc triển khai đáng nhớ: **cụ thể trước, tổng quát sau, default deny rõ ràng và có negative tests cho mọi nhóm quyền**. Hãy kiểm thử cả method/path, chain order, role/scope và CSRF, bởi một dòng matcher đặt sai vị trí có thể mở một endpoint nhạy cảm dù tất cả các dòng riêng lẻ trông đều hợp lý.
