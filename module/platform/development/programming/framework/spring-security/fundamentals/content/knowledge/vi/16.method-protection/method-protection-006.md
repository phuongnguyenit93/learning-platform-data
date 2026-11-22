# SpEL với authentication, principal, tham số và bean chính sách

## 1. Mục tiêu học tập và phạm vi

Spring Security không chỉ kiểm tra người dùng có một vai trò cố định hay không. Trong nghiệp vụ, quyền truy cập thường phụ thuộc đồng thời vào **danh tính đã xác thực**, **tham số của phương thức đang gọi** và **dữ liệu mà hệ thống tin cậy**. Spring Expression Language (SpEL) cho phép mô tả các điều kiện này trong những annotation như `@PreAuthorize`.

Sau bài này, bạn có thể:

1. Hiểu SpEL trong method security và cơ chế Spring Security đánh giá biểu thức trước khi thực thi phương thức.
2. Sử dụng đúng `authentication`, `principal`, `authentication.name`, `hasRole`, `hasAuthority` và các phép toán logic.
3. Tham chiếu tham số phương thức qua `#documentId`, `@P`, tên tham số khi biên dịch với `-parameters` hoặc các chỉ số `#p0`/`#a0`.
4. Gọi Spring bean chính sách qua cú pháp `@documentPolicy.canRead(authentication, #documentId)` để giữ logic nghiệp vụ dễ kiểm thử.
5. Xử lý yêu cầu được phép và bị từ chối, nhận diện khác nhau giữa 401 và 403; biết giới hạn của `@PreAuthorize`, `@PostAuthorize` và proxy-based interception.
6. Chạy ví dụ hoàn chỉnh bằng **Java 17+, Spring Boot 3.3.x, Spring Security 6.x**, rồi đối chiếu bằng `curl` và kiểm thử `MockMvc`.

**Ngữ cảnh:** bài thuộc *Bảo vệ phương thức* trong *Spring Security - fundamentals*. Ví dụ chính sử dụng Spring MVC/Servlet; Spring WebFlux có cơ chế reactive method security và cách lưu security context khác. Nhiều cách viết SpEL giống nhau về ý tưởng nhưng không được tự chuyển cách quản lý thread/security context từ Servlet sang reactive.

## 2. Tại sao cần SpEL khi đã có hasRole?

Giả sử API có hai tài liệu:

| Document ID | Chủ sở hữu |
| --- | --- |
| `101` | `alice` |
| `202` | `bob` |

Hai người dùng Alice và Bob đều có role `USER`. Một quy tắc chỉ dựa trên role:

```java
@PreAuthorize("hasRole('USER')")
public Document readDocument(long documentId) {
    // ...
}
```

không phân biệt tài liệu số 101 do Alice sở hữu với tài liệu 202 do Bob sở hữu. Nếu service không kiểm tra thêm, người có role USER có thể đọc sai dữ liệu của người khác — rủi ro **IDOR / broken object-level authorization**.

Một điều kiện phù hợp hơn:

```java
@PreAuthorize("hasRole('ADMIN') or @documentPolicy.canRead(authentication, #documentId)")
public Document readDocument(@P("documentId") long documentId) {
    // ...
}
```

**Đây là fragment minh họa**, cần `Document`, bean `documentPolicy`, import `@P` và một Spring-managed service thực tế. Nó diễn đạt: *admin có quyền quản trị được đọc; còn người dùng bình thường chỉ được đọc khi bean chính sách xác nhận người gọi có quyền trên document ID này*.

Thành phần quan trọng:

- `hasRole('ADMIN')`: hàm được Spring Security cung cấp, kiểm tra authority `ROLE_ADMIN` theo prefix mặc định.
- `or`: phép OR logic của SpEL; với điều kiện thông thường, vế thứ hai không cần đánh giá nếu vế đầu đã đúng.
- `@documentPolicy`: tham chiếu bean tên `documentPolicy` do Spring ApplicationContext quản lý.
- `authentication`: đối tượng xác thực đang có trong ngữ cảnh của lời gọi.
- `#documentId`: tham số được gắn tên `documentId` của phương thức, không phải biến toàn cục hoặc thông tin tự động đọc từ URL.

**Không tin vào thông tin do client tự khai:** đưa `owner=alice` vào HTTP request không chứng minh client là Alice hoặc sở hữu tài liệu. Bean chính sách phải truy vấn quyền sở hữu từ dữ liệu server hoặc nguồn có độ tin cậy tương ứng.

## 3. SpEL được đánh giá ở đâu?

Trong ứng dụng Servlet với `@EnableMethodSecurity`, Spring Security thiết lập các interceptor thông qua Spring AOP cho method authorization. Với `@PreAuthorize`, điều kiện được đánh giá **trước khi** phương thức nghiệp vụ chạy.

```text
HTTP request / caller khác
          │
          ▼
Spring Security xác thực request / tạo Authentication
          │
          ▼
Spring bean proxy (method security)
          │
          ├─ tìm annotation @PreAuthorize
          │
          ├─ tạo evaluation context cho SpEL
          │     ├─ authentication / principal / authorities
          │     ├─ method arguments (#documentId, #username...)
          │     └─ beans trong ApplicationContext (@documentPolicy)
          │
          └─ đánh giá expression
                 ├─ true  → gọi method nghiệp vụ
                 └─ false → từ chối (không chạy method)
          │
          ▼
Kết quả hoặc lỗi được chuyển qua HTTP / caller hiện hành
```

Các điểm phải phân biệt:

- **HTTP security:** `SecurityFilterChain` áp dụng các quy tắc cho request, ví dụ `anyRequest().authenticated()`.
- **Method security:** `@PreAuthorize` áp dụng cho lời gọi phương thức của Spring-managed bean có interceptor tương ứng.
- **Resource authorization:** logic kiểm tra quyền trên tài liệu ID 101/202 thường được đặt trong bean chính sách hoặc service truy cập dữ liệu, dùng quyền sở hữu, tenant, trạng thái và các ràng buộc khác.

Một endpoint có thể vượt qua HTTP rule `authenticated()` nhưng vẫn bị `@PreAuthorize` từ chối. Đây là hai quyết định ở hai lớp khác nhau.

**Kích hoạt:** thêm dependency Spring Security **không tự kích hoạt** `@PreAuthorize`. Bạn cần `@EnableMethodSecurity` trên cấu hình Spring (hoặc cơ chế method security tương ứng). Với Spring Security hiện đại, các annotation `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` được hỗ trợ mặc định khi bật method security, còn `@Secured` hoặc JSR-250 cần cấu hình thêm nếu muốn dùng.

### Trạng thái xác thực trong lời gọi HTTP

Nếu người dùng **chưa đăng nhập** và HTTP rule đòi xác thực, thường nhận **401 Unauthorized** khi dùng HTTP Basic. Nếu người dùng **đã đăng nhập** nhưng SpEL trả false, thường nhận **403 Forbidden**. Status thực tế còn phụ thuộc cơ chế authentication, exception handling, CSRF và filter khác. Không gán mọi lỗi 403 cho SpEL mà chưa xác định điểm từ chối.

Đối với lời gọi từ scheduler/message listener/test trực tiếp mà **không có HTTP request**, ngoại lệ method security cần được caller xử lý; không mặc định có HTTP status hoặc security context như trong request.

## 4. Các biến có sẵn: authentication và principal

Method security cung cấp một tập thuộc tính/phương thức trên **expression root**. Hai mục dễ nhầm:

| Trong SpEL | Bản chất | Ví dụ hữu ích | Lưu ý |
| --- | --- | --- | --- |
| `authentication` | `Authentication` hiện hành | `authentication.name`, `authentication.authorities` | Có thể phản ánh anonymous hoặc loại xác thực khác; không dùng như dữ liệu tự khai của client |
| `principal` | `authentication.principal` | `principal.username` với principal dạng `UserDetails` | Kiểu dữ liệu tùy cơ chế authentication; không phải principal nào cũng có `username` |
| `hasRole('ADMIN')` | Hàm security expression | Kiểm tra authority `ROLE_ADMIN` | Role prefix có thể cấu hình; mặc định có `ROLE_` |
| `hasAuthority('document:read')` | Hàm security expression | So khớp authority cụ thể | Không tự sinh authority từ tên role |
| `isAuthenticated()` | Kiểm tra trạng thái security được công nhận | Không cho anonymous | Khác với đọc trực tiếp `authentication.authenticated` |

### authentication.name

`authentication.name` là cú pháp SpEL truy cập `getName()` của `Authentication`, nên thường hợp lý để so khớp **identity name**:

```java
@PreAuthorize("authentication.name == #username")
public String getMyProfile(@P("username") String username) {
    return "profile " + username;
}
```

Nếu `alice` gọi `getMyProfile("alice")`, điều kiện đúng; nếu Alice gọi với `"bob"`, điều kiện sai. Nhưng **so sánh tên** chỉ hợp lý khi dữ liệu thực sự dùng chính tên đó làm identity đáng tin. Nếu hệ thống có tên hiển thị có thể đổi, tenant, subject ID hoặc username trùng nhau ở các tổ chức, hãy so bằng ID ổn định trong policy bean.

### principal.username

Khi dùng `UserDetailsService` + HTTP Basic thông thường, principal sau xác thực có thể là `org.springframework.security.core.userdetails.User` — một `UserDetails` có `getUsername()`. Vì vậy:

```java
@PreAuthorize("hasRole('USER') and principal.username == #username")
public String getUserView(@P("username") String username) {
    return "user-view " + username;
}
```

có thể hoạt động ở cấu hình tương ứng. Tuy nhiên, với JWT/OAuth2/OIDC hoặc principal custom, principal có thể là `Jwt`, `OAuth2User`, `UserDetails` tùy implementation, hoặc type khác. **Đừng bê nguyên `principal.username` sang mọi hệ thống**: có thể gây lỗi đánh giá biểu thức nếu property đó không tồn tại. Ưu tiên `authentication.name` hoặc bean chính sách biết cách diễn giải danh tính ở hệ thống cụ thể.

Đặc biệt, `principal` của SpEL method security **khác với tên annotation `@AuthenticationPrincipal`** trên tham số controller; annotation controller là một cách tiêm principal vào method handler, còn SpEL root là ngữ cảnh để đánh giá authorization expression.

### Authorities là những tên quyền, không phải mệnh đề tự khai

Spring Security dùng `GrantedAuthority` như `ROLE_USER`, `ROLE_ADMIN` hoặc `document:read`. `hasRole('ADMIN')` thường tương đương kiểm tra `ROLE_ADMIN`, nhưng `hasAuthority('document:read')` yêu cầu authority đúng chuỗi đó. Việc người dùng có `ROLE_ADMIN` không tự suy ra họ có `document:read` nếu hệ thống chưa cấp/mapping quyền hoặc thiết lập role hierarchy.

## 5. Tham chiếu tham số phương thức: #name, @P, -parameters và #p0

Cú pháp `#documentId` tham chiếu **tham số method được Spring Security phát hiện tên**. Dấu `#` là dấu tham chiếu biến trong SpEL:

```java
@PreAuthorize("#owner == authentication.name")
public void read(@P("owner") String owner) {
    // ...
}
```

Hãy phân biệt ba thành phần: tên Java `owner`, tên do method-security discoverer cung cấp `"owner"` và biến SpEL `#owner`. Trong ví dụ trên, `@P` buộc tên cho biểu thức, nên không phụ thuộc khả năng giữ tên tham số của bytecode.

### Ba cách thường gặp

**Cách 1 — `@P("documentId")` (tường minh):**

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public String read(@P("documentId") long id) {
    return "reading " + id;
}
```

Đây là **fragment** cần bean `documentPolicy` và Spring-managed service; tên Java thực sự là `id` nhưng SpEL vẫn dùng `#documentId` nhờ `@P`.

**Cách 2 — biên dịch với `-parameters` và dùng tên Java:**

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Với source Java:

```java
@PreAuthorize("authentication.name == #username")
public String self(String username) {
    return username;
}
```

`-parameters` giúp Java reflection giữ tên tham số trong bytecode. Một số plugin/build thiết lập sẵn tùy môi trường; dự án cần kiểm tra cấu hình thực tế, đặc biệt nếu expression được đặt trên interface hoặc trong code đã biên dịch trước.

**Cách 3 — alias theo vị trí `#p0` hoặc `#a0`:**

```java
@PreAuthorize("authentication.name == #p0")
public String self(String username) {
    return username;
}
```

`#p0`/`#a0` tương ứng tham số đầu tiên; `#p1`/`#a1` là tham số thứ hai. Cách này tránh phụ thuộc tên nhưng kém rõ nghĩa và dễ hỏng khi đổi thứ tự method parameters.

Spring Security còn có thể tìm tên từ một số annotation như Spring Data `@Param` hoặc metadata khác. Bài này chọn `@P` để ví dụ chính xác, độc lập với compiler flag.

**Lỗi dễ mắc:** viết `#documentId` trong expression nhưng method lại chỉ có `long id`, không có `@P("documentId")` và không có metadata tên tương ứng. SpEL có thể nhận giá trị null/không xác định, dẫn tới từ chối hoặc lỗi khi gọi bean; đừng “sửa” bằng cách bỏ kiểm tra resource.

## 6. Vì sao nên dùng bean chính sách?

Điều kiện đơn giản như `hasRole('ADMIN')` có thể viết trực tiếp trong annotation. Nhưng kiểm tra thực tế có thể cần đọc DB, đối chiếu tenant, trạng thái, quyền chia sẻ và chính sách đang hiệu lực. Viết mọi thứ thành chuỗi SpEL dài khiến logic khó review và khó unit test.

Bean chính sách giúp biểu thức giữ mục đích rõ ràng:

```java
@PreAuthorize("hasRole('ADMIN') or @documentPolicy.canRead(authentication, #documentId)")
public Document readDocument(@P("documentId") long documentId) {
    // ...
}
```

Bean có tên chính xác `documentPolicy`:

```java
@Component("documentPolicy")
public class DocumentPolicy {
    public boolean canRead(Authentication authentication, long documentId) {
        // Tìm tài liệu và quyền sở hữu từ nguồn server tin cậy
        return false;
    }
}
```

Hai đoạn trên là **fragments**, không phải chương trình hoàn chỉnh; method trả false chỉ cho thấy chữ ký của chính sách. Phần `7` cung cấp implementation đầy đủ, có dữ liệu mẫu và test.

### Luồng dữ liệu và ranh giới tin cậy

```text
HTTP GET /api/documents/202
   ├─ Document ID từ path: 202  ─────> method parameter #documentId
   └─ Credentials hợp lệ ────────────> Authentication (name=alice, ROLE_USER)
                                               │
                                               ▼
@documentPolicy.canRead(authentication, 202)
                                               │
                                       owners[202] = "bob"
                                               │
                                  alice != bob → false → 403
```

Tài khoản admin đi qua vế `hasRole('ADMIN')` theo chính sách ứng dụng; người dùng thường dựa vào kết quả `canRead`. Đây là mô hình **role + resource ownership**, không phải RBAC thuần.

**Policy bean phải fail closed**: tài liệu không tồn tại, thiếu identity, dữ liệu tenant không hợp lệ hoặc lỗi kiểm tra quyền phải dẫn đến không cấp quyền. Đừng viết kiểu `return true` khi database time-out hoặc `owner` bằng null. Nếu policy phụ thuộc dữ liệu thay đổi trong giao dịch, hãy xử lý race condition và bảo đảm kiểm tra quyền liên hệ nhất quán với thao tác cuối.

### Viết expression dễ đọc

- `and`/`&&`: điều kiện đồng thời.
- `or`/`||`: một trong các điều kiện đúng.
- `!`: phủ định.
- `==`/`!=`: so sánh.
- Dấu ngoặc `(...)`: nhóm điều kiện, tránh hiểu sai ưu tiên toán tử.
- `@beanName.method(...)`: gọi bean Spring theo tên.
- `#paramName`: biến tham số.
- `authentication` hoặc `principal`: property trên security expression root, **không** có dấu `#` ở cách viết thông thường.

Một biểu thức dễ review:

```java
@PreAuthorize(
    "hasRole('ADMIN') or " +
    "(hasRole('USER') and @documentPolicy.canRead(authentication, #documentId))"
)
```

Đây là **fragment annotation**: trong ứng dụng thực cần đứng trước một method và bean tương ứng. Nếu vế `hasRole('USER')` không phải điều kiện nghiệp vụ, hãy bỏ nó; không thêm role chỉ để biểu thức trông “an toàn hơn”.

## 7. Ví dụ chạy được: ứng dụng Java 17 và Spring Boot

Ví dụ cho phép hai user đọc **chỉ tài liệu mình sở hữu**, admin được đọc tài liệu có tồn tại. Đồng thời có hai route phụ để so sánh biểu thức `authentication.name` và `principal.username`.

- `alice`: role `USER`, sở hữu tài liệu `101`.
- `bob`: role `USER`, sở hữu tài liệu `202`.
- `admin`: role `ADMIN`, có quyền đọc cả hai tài liệu.
- `GET /public`: công khai.
- `GET /api/documents/{documentId}`: thuộc quyền của người gọi hoặc role ADMIN.
- `GET /api/users/{username}/self`: khớp `authentication.name`.
- `GET /api/users/{username}/profile`: yêu cầu role USER và `principal.username` bằng tham số.

### 7.1. Cấu trúc dự án và Gradle

```text
spel-method-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/spelmethod/
    │   ├── SpelMethodApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/com/example/spelmethod/
        └── SpelMethodSecurityTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spel-method-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong ví dụ, method parameters của service được đặt tên bằng `@P` nên không phụ thuộc `-parameters`. Các `@PathVariable` ở controller ghi tên tường minh để tránh phụ thuộc metadata khi Spring MVC bind. Gradle giải quyết dependency Spring; không dùng `javac`/`java` trần trên classpath thiếu thư viện.

### 7.2. Ứng dụng chính

**`src/main/java/com/example/spelmethod/SpelMethodApplication.java`**

```java
package com.example.spelmethod;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpelMethodApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpelMethodApplication.class, args);
    }
}
```

### 7.3. Bật HTTP security và method security

**`src/main/java/com/example/spelmethod/SecurityConfiguration.java`**

```java
package com.example.spelmethod;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice123")
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password("{noop}bob123")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, admin);
    }
}
```

Giải thích:

1. `@EnableMethodSecurity` là điều kiện để `@PreAuthorize` có hiệu lực trên các service bean.
2. `/api/**` ở lớp HTTP chỉ yêu cầu **đăng nhập**; điều kiện chi tiết đối với user, document ID và role được xử lý tại tầng service.
3. `anyRequest().denyAll()` chặn các route chưa được định nghĩa trong policy HTTP.
4. `httpBasic(withDefaults())` cho phép quan sát phản hồi 401 khi thiếu credentials; `formLogin` được tắt để tránh redirect của login form. CSRF vẫn theo mặc định, không cần thay đổi vì các endpoint demo chỉ dùng GET.
5. `{noop}` cùng password demo là **chỉ để học**, không lưu mật khẩu rõ và không dùng những tài khoản này trong production. Ứng dụng thực phải dùng password encoder, kho identity và HTTPS.

### 7.4. Bean chính sách theo quyền sở hữu

**`src/main/java/com/example/spelmethod/DocumentPolicy.java`**

```java
package com.example.spelmethod;

import java.util.Map;
import java.util.Objects;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final Map<Long, String> owners = Map.of(
        101L, "alice",
        202L, "bob"
    );

    public boolean canRead(Authentication authentication, long documentId) {
        if (authentication == null ||
            authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        String owner = owners.get(documentId);
        return owner != null && Objects.equals(owner, authentication.getName());
    }

    public String ownerOf(long documentId) {
        return owners.get(documentId);
    }
}
```

`@Component("documentPolicy")` đăng ký bean bằng đúng tên xuất hiện trong SpEL `@documentPolicy`. Khi `DocumentService.readDocument(101)` được gọi, biểu thức có thể truyền `authentication` và `#documentId` vào method `canRead`.

Trong ví dụ, `owners` là `Map` bất biến để output dễ dự đoán, không phải hệ thống lưu tài liệu thật. Với database, policy phải nạp resource/owner từ server và kiểm tra tenant/visibility theo mô hình nghiệp vụ; không tin ID, owner hoặc role do client tự cung cấp. Nếu identity không phù hợp hoặc tài liệu không tồn tại, `canRead` trả false.

Đoạn `authentication instanceof AnonymousAuthenticationToken` chỉ là một bảo vệ bổ sung cho ví dụ; lớp HTTP đã chặn anonymous ở `/api/**`. Trạng thái `Authentication.isAuthenticated()` đơn lẻ **không đủ phân biệt** anonymous trong mọi trường hợp, vì anonymous authentication cũng có thể được đánh dấu authenticated. Khi viết chính sách tổng quát, dùng `AuthenticationTrustResolver`/cơ chế chính thức nếu cần phân loại trust level.

### 7.5. Service chứa ba kiểu biểu thức

**`src/main/java/com/example/spelmethod/DocumentService.java`**

```java
package com.example.spelmethod;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentPolicy documentPolicy;

    public DocumentService(DocumentPolicy documentPolicy) {
        this.documentPolicy = documentPolicy;
    }

    @PreAuthorize(
        "hasRole('ADMIN') or @documentPolicy.canRead(authentication, #documentId)"
    )
    public String readDocument(@P("documentId") long documentId) {
        String owner = documentPolicy.ownerOf(documentId);
        if (owner == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"
            );
        }
        return "document " + documentId + " owner=" + owner;
    }

    @PreAuthorize("authentication.name == #username")
    public String self(@P("username") String username) {
        return "self " + username;
    }

    @PreAuthorize("hasRole('USER') and principal.username == #username")
    public String profile(@P("username") String username) {
        return "profile " + username;
    }
}
```

Ba cơ chế minh họa:

- `readDocument`: kết hợp role, bean chính sách và ID thực của request. `ADMIN` được đi qua biểu thức, còn user thông thường phải có quyền sở hữu; tài liệu ID lạ vẫn trả **404** sau khi admin được cho phép, vì method nghiệp vụ kiểm tra sự tồn tại.
- `self`: chỉ so sánh tên đã xác thực `authentication.name` với tham số `#username`.
- `profile`: kiểm tra cả role USER và property `principal.username`. Điều này chạy được trong demo vì principal là `UserDetails` do `InMemoryUserDetailsManager` trả về. Nếu ứng dụng dùng JWT/OIDC, cần sửa điều kiện cho loại principal thực tế.

Các phương thức là **public method của Spring-managed service**. Lời gọi từ controller đi qua Spring proxy, nên `@PreAuthorize` được đánh giá. Với một lời gọi `this.readDocument(id)` từ method khác trong chính `DocumentService`, interceptor proxy có thể không được chạy; phần `10` phân tích lỗi self-invocation.

### 7.6. Controller gọi service qua bean được bảo vệ

**`src/main/java/com/example/spelmethod/DocumentController.java`**

```java
package com.example.spelmethod;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/documents/{documentId}")
    public String document(@PathVariable("documentId") long documentId) {
        return service.readDocument(documentId);
    }

    @GetMapping("/api/users/{username}/self")
    public String self(@PathVariable("username") String username) {
        return service.self(username);
    }

    @GetMapping("/api/users/{username}/profile")
    public String profile(@PathVariable("username") String username) {
        return service.profile(username);
    }
}
```

Controller chỉ nhận input/bind path; service chịu trách nhiệm bảo vệ method. Không được tự tin vào `username` trong URL khi làm authorization: `username` chỉ là đối tượng so sánh, còn **danh tính** đến từ `Authentication` đã được hệ thống xác thực.

### 7.7. Chạy và quan sát HTTP

Cần JDK 17+ và Gradle 8.x tương thích với Spring Boot 3.3. Trong thư mục `spel-method-demo`:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper tương thích, có thể dùng `./gradlew test` và `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat test` và `gradlew.bat bootRun` (Windows). Lệnh `gradle bootRun` khởi động ứng dụng trên cổng mặc định 8080 nếu cổng này trống và không có cấu hình khác.

Ở terminal thứ hai:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/documents/101
curl -i -u alice:alice123 http://localhost:8080/api/documents/101
curl -i -u alice:alice123 http://localhost:8080/api/documents/202
curl -i -u bob:bob123 http://localhost:8080/api/documents/202
curl -i -u admin:admin123 http://localhost:8080/api/documents/202
curl -i -u alice:alice123 http://localhost:8080/api/users/alice/self
curl -i -u alice:alice123 http://localhost:8080/api/users/bob/self
curl -i -u alice:alice123 http://localhost:8080/api/users/alice/profile
curl -i -u admin:admin123 http://localhost:8080/api/users/admin/profile
```

**Bảng kết quả dự kiến (cấu hình demo, GET):**

| Request | Danh tính | Kết quả | Điểm kiểm tra |
| --- | --- | --- | --- |
| `/public` | Anonymous | 200 | `permitAll` |
| `/api/documents/101` | Anonymous | 401 | HTTP `authenticated()` |
| `/api/documents/101` | Alice | 200 | `canRead(alice, 101) == true` |
| `/api/documents/202` | Alice | 403 | `canRead(alice, 202) == false` |
| `/api/documents/202` | Bob | 200 | `canRead(bob, 202) == true` |
| `/api/documents/202` | Admin | 200 | `hasRole('ADMIN')` |
| `/api/users/alice/self` | Alice | 200 | `authentication.name == #username` |
| `/api/users/bob/self` | Alice | 403 | Tên khác nhau |
| `/api/users/alice/profile` | Alice | 200 | `hasRole('USER')` và `principal.username` khớp |
| `/api/users/admin/profile` | Admin | 403 | Chỉ có `ROLE_ADMIN`, không có `ROLE_USER` |

Một số response body thành công xác định từ source code:

```text
GET /public (anonymous)                 -> public
GET /api/documents/101 (alice)          -> document 101 owner=alice
GET /api/documents/202 (bob)            -> document 202 owner=bob
GET /api/documents/202 (admin)          -> document 202 owner=bob
GET /api/users/alice/self (alice)       -> self alice
GET /api/users/alice/profile (alice)    -> profile alice
```

Đây là **body text**, không phải toàn bộ status line/headers. Không giả định cấu trúc lỗi JSON của 401/403 là cố định; tùy cấu hình response và entry point. Với `admin`, `principal.username` có thể bằng `"admin"` nhưng biểu thức `profile` vẫn fail vì `hasRole('USER')` false; role ADMIN **không mặc nhiên** kế thừa USER.

### 7.8. Kiểm thử tự động bằng MockMvc

**`src/test/java/com/example/spelmethod/SpelMethodSecurityTest.java`**

```java
package com.example.spelmethod;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SpelMethodSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousRequestCannotReadDocument() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isOk())
            .andExpect(content().string("document 101 owner=alice"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCannotReadBobsDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/202"))
            .andExpect(status().isOk())
            .andExpect(content().string("document 202 owner=bob"));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadDocumentOwnedByAnotherUser() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/documents/202"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void authenticationNameMatchesOnlyCurrentUser() throws Exception {
        mvc.perform(get("/api/users/alice/self"))
            .andExpect(status().isOk())
            .andExpect(content().string("self alice"));

        mvc.perform(get("/api/users/bob/self"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void principalUsernameMustAlsoMatch() throws Exception {
        mvc.perform(get("/api/users/alice/profile"))
            .andExpect(status().isOk())
            .andExpect(content().string("profile alice"));

        mvc.perform(get("/api/users/bob/profile"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminDoesNotAutomaticallyHaveUserRole() throws Exception {
        mvc.perform(get("/api/users/admin/profile"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void missingDocumentIsNotFoundForAdmin() throws Exception {
        mvc.perform(get("/api/documents/999"))
            .andExpect(status().isNotFound());
    }
}
```

Bộ test bao gồm hai lớp bảo vệ:

- **Anonymous → 401**: HTTP rule `authenticated()` chặn trước service.
- **Đã xác thực nhưng sai quyền → 403**: SpEL ở method security chặn trước khi chạy method.
- **Đúng quyền → 200**: bean policy hoặc biểu thức identity khớp.
- **Admin đọc ID không tồn tại → 404**: admin qua được authorization nhưng nghiệp vụ vẫn kiểm tra resource tồn tại.

`@WithMockUser` dựng security context giả cho test, mặc định có principal dạng Spring Security `User` và các authority như `ROLE_USER`. Nó không thử login/password của `InMemoryUserDetailsManager`. `curl -u` ở mục trên mới kiểm tra request sử dụng HTTP Basic với credentials demo.

## 8. SpEL thường dùng trong bảo vệ phương thức

| Điều kiện | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| User phải đăng nhập | `@PreAuthorize("isAuthenticated()")` | Cần danh tính xác thực được công nhận |
| Cần role cụ thể | `@PreAuthorize("hasRole('ADMIN')")` | Cần `ROLE_ADMIN` theo prefix mặc định |
| Cần authority chi tiết | `@PreAuthorize("hasAuthority('document:read')")` | Khớp authority đã được cấp |
| Cần một trong nhiều quyền | `@PreAuthorize("hasAnyAuthority('document:read','document:audit')")` | Phép OR theo authorities |
| Trùng identity | `@PreAuthorize("authentication.name == #username")` | So sánh tên xác thực với tham số |
| Principal có property tương ứng | `@PreAuthorize("principal.username == #username")` | Chỉ khi principal có `username` |
| Kết hợp role và nghiệp vụ | `@PreAuthorize("hasRole('ADMIN') or @documentPolicy.canRead(authentication,#id)")` | Dùng bean policy với resource ID |
| Kết hợp điều kiện | `@PreAuthorize("hasRole('EDITOR') and #documentId > 0")` | Cả hai điều kiện đúng; không thay kiểm tra object |

**Chú ý:** đối với `hasPermission(...)`, Spring Security cần cách đánh giá quyền (ví dụ `PermissionEvaluator`) thích hợp. Nếu chưa cấu hình đánh giá quyền trên object, đừng mặc định `hasPermission(#id, 'read')` sẽ tự biết ai sở hữu tài liệu. Trong nhiều ứng dụng, bean policy tường minh dễ hiểu hơn.

### Khi nào cần @PostAuthorize?

`@PostAuthorize` đánh giá **sau khi phương thức chạy**, có thể truy cập `returnObject`:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Document loadDocument(long id) {
    // chỉ trả Document ra caller khi owner khớp
}
```

Đây là **fragment minh họa**, cần class `Document` có property `owner` và method trong Spring-managed bean. Nó hữu ích khi điều kiện phụ thuộc object trả về. Nhưng dữ liệu đã được nạp và phương thức đã thực thi **trước** khi policy quyết định. Không dùng riêng `@PostAuthorize` để bảo vệ thao tác có **side effects** như chuyển tiền, xóa bản ghi hoặc gửi email — nếu method đã gây side effect, từ chối sau đó có thể quá muộn. Với truy vấn chỉ đọc, cân nhắc tránh nạp dữ liệu nhạy cảm không cần thiết ngay từ đầu và dùng policy ở service/data access.

`@PreFilter`/`@PostFilter` hỗ trợ lọc các collection theo biểu thức trong những trường hợp phù hợp; chúng không thay thế kiểm tra owner/tenant tại truy vấn DB với dữ liệu lớn.

## 9. Những lỗi phổ biến về biểu thức và tham số

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Dùng `principal.username` với mọi JWT/OIDC | Principal không có field `username` | Kiểm tra principal type thật, dùng `authentication.name` hoặc bean policy |
| Viết `#documentId` nhưng Java method chỉ có `id` và không có `@P` | Parameter discovery không thấy tên đã dùng | Thêm `@P("documentId")` hoặc biên dịch `-parameters` |
| Viết `@documentPolicy` nhưng bean tên khác | Bean không resolve được | Đặt tên bean rõ bằng `@Component("documentPolicy")` hoặc `@Bean("documentPolicy")` |
| Dùng `hasRole('ROLE_ADMIN')` với default prefix | Sai cú pháp/role prefix | Dùng `hasRole('ADMIN')` hoặc `hasAuthority('ROLE_ADMIN')` |
| Chỉ dùng `hasRole('USER')` cho tài liệu theo chủ sở hữu | User khác cùng role đọc được object | Policy phải tra owner/tenant/state theo resource ID |
| Chỉ dùng `authentication.authenticated` | Có thể hiểu sai anonymous authentication | Dùng `isAuthenticated()` hoặc trust resolver phù hợp |
| Lấy owner/role từ query/header/body do client gửi | Dữ liệu client có thể bị giả mạo | Quyết định từ Authentication và dữ liệu server tin cậy |
| Không bật `@EnableMethodSecurity` | Annotation `@PreAuthorize` không hoạt động | Bật method security và test denied case |
| Gọi `this.securedMethod(...)` trong cùng bean | Bypass AOP proxy trong cơ chế proxy mặc định | Gọi qua Spring-managed bean khác hoặc thiết kế lại ranh giới service |
| Đặt annotation trên đối tượng được tạo bằng `new` | Không được Spring quản lý/proxy | Sử dụng dependency injection và bean được quản lý |
| Viết expression quá dài, nhiều phép truy vấn DB | Khó review, khó kiểm thử, tăng độ trễ | Đưa quy tắc vào bean policy nhỏ, tách rõ authorization & query |
| Dùng `@PostAuthorize` cho method ghi dữ liệu | Quyết định sau side effect | Dùng `@PreAuthorize`/transactional authorization phù hợp |
| Không xét tenant hay trạng thái tài nguyên | Quyền bị mở rộng ngoài phạm vi | Kiểm tra object-level/tenant/state trong policy |
| Test chỉ có trường hợp 200 | Không phát hiện method security bị vô hiệu | Test 401, 403, 404 và người dùng có role sai |

### Lưu ý về self-invocation và proxy

Spring Method Security thường được thực thi nhờ Spring AOP proxy. Một đoạn như:

```java
@Service
class ExampleService {
    public String outer(long id) {
        return inner(id);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String inner(long id) {
        return "restricted";
    }
}
```

là **fragment giải thích lỗi**, không phải ví dụ đảm bảo an toàn. Lời gọi `outer() -> inner()` từ chính `this` thường không đi qua proxy của `inner`, nên annotation có thể bị bỏ qua. Thực hiện kiểm soát ở **điểm vào** được Spring intercept, tách bean khi cần, và xác minh bằng test trên đường gọi thật. Không coi chỉ cần gắn annotation lên bất kỳ method Java là đã được bảo vệ trong mọi trường hợp.

### Lưu ý về đa luồng và reactive

Trong Servlet, security context thường được quản lý gắn với execution theo cơ chế `SecurityContextHolder`. Chuyển sang thread khác bằng `@Async` hoặc tự tạo thread mà không có chiến lược truyền context phù hợp có thể khiến expression không thấy Authentication như mong đợi. Với WebFlux/Reactor, Spring Security dùng ngữ cảnh reactive (Reactor `Context`/`ReactiveSecurityContextHolder`) và cần cấu hình method security reactive phù hợp. Không tự sao chép `ThreadLocal` cho pipeline reactive.

### Không tạo SpEL động từ đầu vào người dùng

Annotation `@PreAuthorize("...")` là **biểu thức được phát triển và review trong code**. Đừng ghép trực tiếp một chuỗi đầu vào HTTP vào source SpEL rồi nhờ parser thực thi; điều đó có thể biến đầu vào không tin cậy thành biểu thức truy cập object/bean ngoài ý muốn. Hãy truyền dữ liệu làm **tham số đã bind** (`#documentId`, `#username`) và để policy bean quyết định quyền.

## 10. Khi thiết kế chính sách thật, cần kiểm tra những gì?

Một method như `readDocument(long id)` có thể cần nhiều điều kiện hơn việc khớp tên user:

1. **Identity**: user/subject ID từ `Authentication` đã xác minh.
2. **Role/permission**: user có authority thích hợp cho hành động `read` hay không.
3. **Ownership/share**: tài liệu thuộc user hay có quyền chia sẻ hợp lệ?
4. **Tenant boundary**: document và user có trong cùng tổ chức hoặc tenant được phép?
5. **Resource state**: tài liệu đã bị xóa, bị khóa, chỉ còn draft, hết hiệu lực?
6. **Hiệu lực phiên/token**: quyền đã bị thu hồi nhưng token/session cũ còn dùng được không?
7. **Consistency**: policy kiểm tra trên cùng phiên bản/trạng thái dữ liệu với thao tác cần bảo vệ hay không?
8. **Audit**: ghi dấu vết truy cập nhạy cảm và quyết định từ chối (không ghi token, password, cookie hoặc nội dung nhạy cảm).

Bean chính sách nên trả kết quả rõ và fail closed. Với DB, ưu tiên kiểm tra quyền gắn với truy vấn hoặc trong transaction thích hợp khi dữ liệu có thể thay đổi đồng thời. Khi không tìm thấy resource, chọn 404/403 theo policy chống lộ thông tin về sự tồn tại của tài nguyên; tránh vô tình cho client suy đoán tài liệu của người khác tồn tại.

**Đừng dùng annotation như toàn bộ thiết kế bảo mật.** Phân quyền ở method giúp bảo vệ logic nghiệp vụ qua nhiều call paths, nhưng phải được kết hợp với lớp HTTP, nguồn danh tính đáng tin và data access có kiểm soát.

## 11. Tự kiểm tra kiến thức

**Câu 1.** `authentication` và `principal` giống và khác nhau ở đâu?

**Đáp án:** `authentication` là đối tượng xác thực có name, authorities, trạng thái và principal. `principal` thường là giá trị `authentication.getPrincipal()`; kiểu cụ thể phụ thuộc cơ chế login. Với user store demo nó có property `username`; với JWT/OIDC không được mặc định điều đó.

**Câu 2.** Vì sao `#documentId` có dấu `#` còn `authentication` không có?

**Đáp án:** `#documentId` là biến tham số trong SpEL evaluation context, còn `authentication` là thuộc tính trên security expression root. `@documentPolicy` bắt đầu bằng `@` vì đó là tham chiếu bean Spring.

**Câu 3.** Nếu Alice có role USER nhưng gọi `readDocument(202)`, kết quả thế nào trong demo?

**Đáp án:** `hasRole('ADMIN')` false; policy đọc owner ID 202 là Bob, tên xác thực là Alice, trả false. Method không chạy và HTTP request thường nhận 403.

**Câu 4.** Tại sao admin được đọc ID 202 nhưng không được gọi `/api/users/admin/profile` trong demo?

**Đáp án:** method đọc document có vế `hasRole('ADMIN')`. Method profile lại đòi `hasRole('USER') and principal.username == #username`. Admin không mặc định sở hữu `ROLE_USER`, nên profile bị từ chối.

**Câu 5.** Khi nào dùng `@P` thay cho `-parameters`?

**Đáp án:** khi muốn tên SpEL rõ và độc lập với compiler metadata, đặc biệt với method API/interface hoặc dự án có nhiều cách build. Cả hai đều có thể hợp lệ; `@P` làm tên biểu thức tường minh.

**Câu 6.** Chỉ viết `@PreAuthorize("hasRole('USER')")` đã bảo vệ được document của riêng từng user chưa?

**Đáp án:** chưa. Mọi user có role USER có thể vượt qua rule đó. Cần so resource ID/owner/tenant/state ở policy hoặc authorization service.

**Câu 7.** Vì sao `@PostAuthorize` không phù hợp làm biện pháp duy nhất bảo vệ thao tác xóa dữ liệu?

**Đáp án:** vì method đã thực hiện trước khi `@PostAuthorize` kiểm tra giá trị trả về; side effect có thể đã xảy ra. Nên kiểm tra quyền trước hành động và bảo đảm transaction/consistency.

**Câu 8.** Vì sao thêm `@PreAuthorize` lên một method rồi gọi method ấy qua `this.method()` có thể không bảo vệ được?

**Đáp án:** lời gọi nội bộ có thể không đi qua AOP proxy nên interceptor không chạy. Thiết kế call path qua Spring bean proxy và kiểm thử thực tế.

**Câu 9.** Trong test `@WithMockUser`, việc Alice được phép có chứng minh password Alice đã được xác minh đúng không?

**Đáp án:** không. `@WithMockUser` dựng Authentication giả phục vụ test authorization, không thực hiện HTTP Basic login. Test HTTP Basic riêng bằng `curl -u` hoặc integration test với credentials thực.

**Câu 10.** Tại sao policy không nên tin claim `owner` trong JSON body?

**Đáp án:** client có thể sửa body. Ownership phải dựa trên document được tra cứu ở server và identity đã xác thực, không dựa trên lời khai của người gọi.

## 12. Kết luận

- **SpEL trong method security** giúp kiểm tra theo danh tính, authorities, đối số method và bean nghiệp vụ.
- **`authentication` là Authentication hiện hành; `principal` là phần principal bên trong**, có kiểu khác nhau theo cơ chế xác thực.
- Tham số method dùng **`#name`**; cần bảo đảm tên được discover bằng `@P`, `-parameters` hoặc alias phù hợp.
- **`@documentPolicy.canRead(authentication, #documentId)`** là cách đưa kiểm tra resource/ownership ra khỏi biểu thức dài và giữ logic dễ test.
- **`@EnableMethodSecurity`** và lời gọi qua **Spring-managed proxy** là điều kiện thiết yếu để `@PreAuthorize` hoạt động trong cấu hình demo.
- **403** ở method security khác với **401** do HTTP authentication; test cả trường hợp được phép và bị từ chối.
- Quyền trên một object thực tế cần xem **owner, tenant, state, vòng đời token và tính nhất quán**, không dừng ở role.
- Demo sử dụng tài khoản/mật khẩu rõ chỉ để học; ứng dụng thực cần danh tính tin cậy, secret/password handling an toàn và logging có kiểm soát.

### Tài liệu tham khảo chính thức

- Spring Security 6.5 — Method Security (SpEL, @PreAuthorize, @PostAuthorize, parameter discovery, @P): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security — Authorize HTTP Requests (quan hệ giữa HTTP và method security): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — @WithMockUser và kiểm thử method security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — MockMvc testing integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Framework — Spring Expression Language (SpEL): https://docs.spring.io/spring-framework/reference/core/expressions.html
- Spring Boot 3.3 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
