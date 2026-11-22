# Vì sao cần bảo vệ tầng dịch vụ bên cạnh quy tắc HTTP trong Spring Security Servlet

## Mục tiêu

Khi xây dựng ứng dụng Spring Security Servlet, ta thường bắt đầu bằng các quy tắc HTTP:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
~~~

Những quy tắc đó rất cần thiết: chúng kiểm soát request **đi qua SecurityFilterChain tương ứng** trước khi tới Spring MVC. Tuy nhiên, chúng chưa đủ để bảo đảm mọi thao tác nghiệp vụ đều an toàn. Cùng một phương thức đọc hóa đơn, đổi trạng thái đơn hàng hoặc xem tài liệu có thể được gọi từ nhiều nơi: REST controller, trang MVC, scheduled job, message consumer, GraphQL resolver, batch worker, một controller mới, hoặc một service khác. Quy tắc URL không tự chạy trên những lời gọi Java không đi qua HTTP filter chain.

**Bảo vệ tầng dịch vụ (service-layer authorization, method security)** đưa chính sách truy cập tới gần nơi thực hiện hành động và truy xuất dữ liệu. Trong Spring Security, ta có thể bật @EnableMethodSecurity rồi dùng @PreAuthorize, @PostAuthorize và các AuthorizationManager thích hợp trên Spring-managed beans. Quan trọng hơn, chính sách phải kiểm tra quyền trên **đối tượng dữ liệu thực tế**, không chỉ “đã đăng nhập” hay “có role USER”.

Sau bài này, bạn sẽ biết:

1. Phân biệt HTTP authorization với method/service authorization.
2. Giải thích vì sao .authenticated() hoặc một rule role trên URL không tự ngăn truy cập trái phép bản ghi (IDOR/BOLA).
3. Nhận biết những entrypoint không đi qua controller và rủi ro khi thêm endpoint mới.
4. Hiểu @EnableMethodSecurity, @PreAuthorize, SpEL, Authentication và AuthorizationManager.
5. Xây ví dụ Java 17+, Spring Boot 3.x / Spring Security 6.x với Spring MVC, H2, Spring Data JPA, service-level ownership policy.
6. Kiểm thử cả HTTP request bằng MockMvc và lời gọi trực tiếp vào service bean.
7. Hiểu giới hạn của Spring AOP proxy: self-invocation, final/private method, khởi tạo bean thủ công và async thread.
8. Kết hợp kiểm soát ở service với truy vấn database, transaction, tenant isolation, audit và nguyên tắc deny-by-default.

Bối cảnh là **Spring Security Servlet**. Method security không phụ thuộc vào Servlet request về mặt bắt buộc, nên chính nó giúp bảo vệ một số lời gọi không qua web. Các nguồn Authentication và cách lan truyền SecurityContext phải được thiết kế phù hợp cho từng entrypoint; method annotation không tự tạo danh tính đáng tin cậy.

## 1. Quy tắc HTTP giải quyết lớp bài toán nào?

Một request từ trình duyệt thường đi theo luồng:

~~~text
HTTP client
    |
Servlet container
    |
Spring Security FilterChainProxy
    |
SecurityFilterChain đã được chọn
    |
Authentication filters -> Authentication
    |
AuthorizationFilter / authorizeHttpRequests rules
    |
DispatcherServlet
    |
Controller
    |
Service
    |
Repository / Database
~~~

Ví dụ: .requestMatchers("/api/**").authenticated() đảm bảo request đã có Authentication hợp lệ khi truy cập đường dẫn thuộc rule. Nhưng nó **không** trả lời liệu alice có quyền đọc invoice thuộc bob hay không. Với URL GET /api/invoices/102, ngay cả alice và bob đều có role USER, chỉ một người mới là chủ sở hữu hóa đơn.

Quy tắc HTTP hữu ích để:

- Chặn anonymous request sớm, trước khi vào controller.
- Cấp quyền theo URL và HTTP method, ví dụ /admin/** cần ADMIN.
- Định nghĩa một chính sách bao phủ mọi HTTP endpoint qua .anyRequest().denyAll() hoặc rule phù hợp.
- Kết hợp với CSRF, session policy, authentication entrypoint, access denied handler và security headers.
- Phân tách API chain và web chain cho các cơ chế xác thực khác nhau.

Nhưng HTTP matcher chỉ hoạt động **trên request đi qua chain đó**. Nó không bao phủ mọi lời gọi tới service bean. Ngoài ra, securityMatcher và requestMatchers khác nhau: securityMatcher chọn phạm vi một SecurityFilterChain, còn requestMatchers trong authorizeHttpRequests chọn authorization rule bên trong chain.

### Một mô hình sai thường gặp

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/documents/**").authenticated()
        .anyRequest().denyAll());
~~~

Controller:

~~~java
@GetMapping("/api/documents/{id}")
public DocumentDto document(@PathVariable Long id) {
    return documentService.read(id);
}
~~~

Nếu documentService.read(id) chỉ gọi repository.findById(id) mà không kiểm tra owner/tenant/permission, thì **mọi user đã login** có thể thử thay id trên URL để xem dữ liệu người khác. HTTP layer vẫn “đúng” theo chính sách .authenticated(), nhưng business authorization đang thiếu.

Đây là ví dụ của **Broken Object Level Authorization (BOLA)** hoặc **Insecure Direct Object Reference (IDOR)**: kẻ gọi không cần giả mạo Authentication, chỉ thay định danh dữ liệu do client được phép nhập.

## 2. Vì sao cần một lớp bảo vệ thứ hai?

Hãy xem một ứng dụng có service nghiệp vụ:

~~~text
             REST Controller ----\
             MVC Controller ------\
             Scheduled Job --------> DocumentService.read(documentId)
             Message Consumer -----/
             Another Service -----/
                                        |
                                   Repository / DB
~~~

Khi policy chỉ nằm ở REST controller hoặc SecurityFilterChain:

- Một controller mới có thể gọi service mà quên cùng rule chủ sở hữu.
- Một batch worker có thể được cấp quyền quá rộng hoặc dùng danh tính hệ thống không kiểm soát.
- Một GraphQL resolver có thể không dùng route /api/documents/{id} mà HTTP rule dự kiến.
- Unit/integration test trực tiếp gọi service bean có thể bỏ qua security nếu service không được bảo vệ.
- Một internal endpoint được đội khác thêm vào có thể chỉ check .authenticated(), tạo đường vào mới tới cùng dữ liệu.

Khi **service bean được bảo vệ bằng method security**, yêu cầu quyền được kiểm tra ở biên gọi method qua Spring AOP proxy. Dù HTTP controller chỉ check authentication, lời gọi read(documentId) vẫn có policy gần nghiệp vụ. Nếu một controller thứ hai gọi cùng proxied service, policy vẫn được áp dụng.

Mấu chốt: **defense in depth** không phải hai dòng cấu hình y hệt. Mỗi tầng nên bảo vệ điều nó biết rõ nhất:

| Tầng | Quyết định thích hợp |
| --- | --- |
| Servlet security chain | Request nào phải authenticated? Role thô nào được gọi endpoint? |
| Service/method | Caller có quyền thực hiện use case này? Có được xem/sửa dữ liệu với ID này? |
| Repository/SQL | Chỉ lấy những row thuộc owner/tenant đã xác minh; xử lý concurrency |
| Database | Constraint, transaction, row-level security khi hệ quản trị và kiến trúc hỗ trợ |
| Audit/observability | Ai thực hiện hành động nào; không lộ token hoặc dữ liệu riêng tư |

Một tầng thất bại không có nghĩa những tầng còn lại sẽ luôn cứu được hệ thống. Ví dụ gọi trực tiếp một helper trong cùng bean có thể bỏ qua proxy method security; vì vậy chính sách quan trọng còn cần query scoping, kiến trúc rõ ràng và test.

## 3. Những tình huống cụ thể mà HTTP-only không đủ

### 3.1. Thay ID trên URL

Alice có tài khoản hợp lệ, thử:

~~~text
GET /api/documents/101   -> tài liệu của alice
GET /api/documents/102   -> tài liệu của bob
~~~

Với .authenticated() cả hai request có thể qua tầng HTTP. Service phải hỏi **document 102 thuộc ai**, người gọi có quyền theo tenant/chia sẻ hay không và có đặc quyền admin hợp lệ hay không.

### 3.2. Endpoint được thêm sau

Ban đầu chỉ có:

~~~text
GET /api/documents/{id} -> DocumentService.read(id)
~~~

Sau đó developer thêm:

~~~text
GET /internal/export/{id} -> DocumentService.read(id)
~~~

Nếu developer chỉ kiểm tra endpoint mới bằng role đơn giản, ownership bị bỏ quên. Với @PreAuthorize bảo vệ read() trên service, controller mới vẫn phải đáp ứng policy khi gọi method qua proxy.

### 3.3. Công việc không phải HTTP

Một @Scheduled job hoặc message listener không có HttpServletRequest/Authentication của browser. HTTP authorization **không chạy** khi nó trực tiếp gọi DocumentService. Method security có thể bảo vệ service, nhưng job phải có một principal được thiết kế rõ hoặc dùng API riêng cho tác vụ hệ thống. Không “fix” bằng cách tự nhét ROLE_ADMIN vào SecurityContextHolder cho mọi background job.

### 3.4. API nhiều entrypoint

Ứng dụng có REST, GraphQL và websocket handler; mỗi loại có điểm xác thực/ủy quyền khác nhau. Nếu nghiệp vụ quan trọng được bảo vệ ở service thì chính sách có thể được tái sử dụng, nhưng cần xét **context propagation** và cách authentication của từng entrypoint. Không được mặc định có SecurityContext đúng trong mọi thread.

### 3.5. Quyền thay đổi theo trạng thái dữ liệu

Ví dụ quản lý order: owner chỉ được sửa khi trạng thái DRAFT; operator chỉ được approve khi có quyền và trạng thái SUBMITTED. HTTP rule hasRole('USER') không biết trạng thái bản ghi hoặc quan hệ owner. Đây là chính sách **object- và state-level**, nên đặt gần use case/transaction nơi dữ liệu được đọc.

## 4. Bật method security trong Spring Security 6

Từ Spring Security 6, sử dụng:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Đây là đoạn cấu hình cần có import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity và org.springframework.context.annotation.Configuration. Không nên cho rằng thêm dependency Spring Security hoặc tự khai báo SecurityFilterChain sẽ **tự động bật** @PreAuthorize; method security cần được kích hoạt.

Sau khi bật:

~~~java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String exportAll() {
        return "protected report";
    }
}
~~~

Khi Spring-managed bean ReportService được gọi **qua Spring proxy**, Spring Security sẽ đánh giá biểu thức **trước** khi chạy nội dung method. Với user không đủ quyền, AccessDeniedException được ném, method body không được thực thi.

Các khái niệm:

- **@PreAuthorize:** kiểm tra trước khi gọi method, dùng khi có thể quyết định quyền từ Authentication và các tham số.
- **@PostAuthorize:** kiểm tra sau khi method đã chạy, có thể dùng returnObject. Hữu ích trong vài tình huống nhưng có thể tốn tài nguyên hoặc gây side effect trước khi từ chối.
- **@PreFilter / @PostFilter:** lọc collection/array/stream theo cách Spring Security hỗ trợ, cần cân nhắc performance và dữ liệu đã được nạp.
- **Authentication:** danh tính và authorities đã được xác minh theo cơ chế đang dùng.
- **SpEL:** biểu thức bảo mật như hasRole('ADMIN') hoặc @documentPolicy.canRead(#documentId, authentication).
- **AuthorizationManager:** abstraction quyết định cho phép/từ chối; có thể dùng các manager trực tiếp ở HTTP và method security theo những context khác nhau.

Từng API có phạm vi và thời điểm đánh giá riêng. **@PreAuthorize không tự kiểm tra owner** nếu biểu thức của bạn chỉ là isAuthenticated().

### Tham số method trong SpEL

Nếu muốn dùng #documentId, Spring phải xác định tên tham số method. Có thể dùng trình biên dịch với -parameters hoặc annotation hỗ trợ của Spring Security. Để ví dụ rõ ràng, ta dùng:

~~~java
@PreAuthorize("@documentPolicy.canRead(#documentId, authentication)")
public DocumentDto read(@P("documentId") Long documentId) {
    // ...
}
~~~

@P ở đây là org.springframework.security.access.method.P, cho biết tên tham số dành cho expression evaluation. Đừng suy ra #documentId sẽ luôn có giá trị nếu bạn không dùng -parameters, @P hoặc cơ chế discovery tương thích. Trong source thật phải có bean tên documentPolicy.

## 5. Vì sao quyền trên record thường cần truy vấn dữ liệu?

Role USER chỉ là một thuộc tính của người gọi, không cho biết document có owner là ai:

~~~text
Authentication:
  name = alice
  authorities = [ROLE_USER]

Document 101:
  ownerUsername = alice
  title = Alice notes

Document 102:
  ownerUsername = bob
  title = Bob plans
~~~

Rule owner đơn giản:

~~~text
Cho phép đọc document nếu:
  (document.ownerUsername == authentication.name)
  OR caller có ROLE_ADMIN

Cho phép sửa tiêu đề nếu:
  document.ownerUsername == authentication.name
  (trong ví dụ, ADMIN không tự có quyền sửa)
~~~

Đây là **quy tắc nghiệp vụ được chọn cho bài học**, không phải chính sách mặc định của Spring Security. Trong ứng dụng thực, quyền có thể phụ thuộc tenant ID, ACL, nhóm, phân loại dữ liệu, thời điểm, trạng thái đơn hàng và hợp đồng chia sẻ.

Đừng dùng giá trị ownerUsername do client gửi trong JSON body để xét quyền; attacker có thể gửi ownerUsername=alice trong request của bob. Policy phải lấy owner từ **database hoặc nguồn sự thật đáng tin**, và caller từ Authentication đã xác minh.

**Đừng tin ID trong URL là bí mật**. Dù là UUID khó đoán, tài liệu vẫn cần authorization khi được truy cập. Một ID không đoán được có thể bị rò rỉ qua log, URL được chia sẻ hoặc lỗi frontend.

## 6. Ví dụ đầy đủ: Java 17, Spring Boot, Spring Security và H2

Chúng ta xây ứng dụng Spring MVC với:

- GET /api/documents/{documentId}: HTTP chỉ yêu cầu authenticated, service kiểm tra owner hoặc ADMIN.
- PUT /api/documents/{documentId}: HTTP chỉ yêu cầu authenticated, service chỉ cho **owner** đổi tiêu đề.
- Hai account alice, bob và một account admin, dùng password đã encode.
- H2 in-memory database với tài liệu 101 của alice và 102 của bob.
- @EnableMethodSecurity kích hoạt @PreAuthorize ở tầng service.
- @Component("documentPolicy") tra owner từ database.
- Để minh họa defense-in-depth, **service còn truy vấn data theo owner ở nhánh user thường**, giảm rủi ro khi policy bị gọi sai đường.
- MockMvc test HTTP và test trực tiếp vào proxied DocumentService.

Ví dụ dùng Java 17+, Spring Boot 3.3.5, Spring Security 6.x theo dependency management. Không dùng user/password demo trong production.

### 6.1. Cấu trúc project

~~~text
service-authorization-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (nếu đã tạo Gradle Wrapper)
  src/main/java/dev/example/serviceauth/
    ServiceAuthorizationApplication.java
    SecurityConfig.java
    DocumentEntity.java
    DocumentRepository.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  src/test/java/dev/example/serviceauth/
    DocumentAuthorizationIntegrationTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'service-authorization-demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot tự cấu hình datasource H2 in-memory và Hibernate DDL cho embedded DB phù hợp với project demo; không cần đặt mật khẩu database ở source. Với database thật, cần migration tool như Flyway/Liquibase, transaction và bảo mật secret đúng hạ tầng.

### 6.2. Main và dữ liệu khởi tạo

Tệp src/main/java/dev/example/serviceauth/ServiceAuthorizationApplication.java:

~~~java
package dev.example.serviceauth;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ServiceAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServiceAuthorizationApplication.class, args);
    }

    @Bean
    CommandLineRunner seedDocuments(DocumentRepository repository) {
        return args -> {
            if (!repository.existsById(101L)) {
                repository.save(
                        new DocumentEntity(101L, "alice", "Alice notes"));
            }
            if (!repository.existsById(102L)) {
                repository.save(
                        new DocumentEntity(102L, "bob", "Bob plans"));
            }
        };
    }
}
~~~

Các ID cố định giúp test có kết quả xác định. Với H2 memory, dữ liệu sống trong vòng đời ứng dụng và không được dùng làm nguồn tài liệu lâu dài. Trong production, không seed user/documents theo cách demo này.

### 6.3. Entity và Repository

Tệp src/main/java/dev/example/serviceauth/DocumentEntity.java:

~~~java
package dev.example.serviceauth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "demo_documents")
public class DocumentEntity {

    @Id
    private Long id;

    @Column(nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected DocumentEntity() {
    }

    public DocumentEntity(Long id, String ownerUsername, String title) {
        this.id = id;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

Tệp src/main/java/dev/example/serviceauth/DocumentRepository.java:

~~~java
package dev.example.serviceauth;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {

    boolean existsByIdAndOwnerUsername(
            Long id, String ownerUsername);

    Optional<DocumentEntity> findByIdAndOwnerUsername(
            Long id, String ownerUsername);
}
~~~

Spring Data JPA sinh truy vấn từ tên method theo tên thuộc tính entity. findByIdAndOwnerUsername giúp hạn chế dữ liệu trả về cho owner. Repository không tự tin tưởng danh tính; **caller phải truyền ownerUsername từ Authentication đã xác thực**, không lấy từ request body/URL không kiểm soát.

Để tránh quá phụ thuộc username có thể đổi, production thường nên lưu ownerUserId/tenantId ổn định và ánh xạ principal sang ID đó.

### 6.4. SecurityConfig: lớp HTTP và bật method security

Tệp src/main/java/dev/example/serviceauth/SecurityConfig.java:

~~~java
package dev.example.serviceauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-demo-pass"))
                        .roles("ADMIN").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/documents/*")
                        .authenticated()
                        .requestMatchers(
                                HttpMethod.PUT, "/api/documents/*")
                        .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

Ở HTTP layer chỉ có yêu cầu authenticated cho GET/PUT URL phù hợp. Đây là lựa chọn cố ý để minh họa service-level ownership, **không** phải lời khuyên rằng toàn bộ API chỉ cần authenticated().

Bởi CSRF không bị tắt, PUT trong test cần một CSRF token hợp lệ. Khi có browser cookie/session, CSRF là yếu tố quan trọng và độc lập với method security. Với một API bearer-token stateless thật sự, CSRF policy có thể khác nhưng phải đánh giá dựa trên cơ chế mang credentials, không disable tùy tiện.

Method security được bật bằng @EnableMethodSecurity. Mọi lời gọi qua Spring proxy của DocumentService tới các method public có @PreAuthorize được kiểm tra, kể cả lời gọi không đến từ MVC controller.

### 6.5. Component kiểm tra quyền trên đối tượng

Tệp src/main/java/dev/example/serviceauth/DocumentPolicy.java:

~~~java
package dev.example.serviceauth;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Long documentId, Authentication authentication) {
        if (!isRealUser(authentication) || documentId == null) {
            return false;
        }

        if (hasAdminRole(authentication)) {
            return repository.existsById(documentId);
        }

        return repository.existsByIdAndOwnerUsername(
                documentId, authentication.getName());
    }

    public boolean canWrite(Long documentId, Authentication authentication) {
        return isRealUser(authentication)
                && documentId != null
                && repository.existsByIdAndOwnerUsername(
                        documentId, authentication.getName());
    }

    public boolean hasAdminRole(Authentication authentication) {
        return isRealUser(authentication)
                && authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }
}
~~~

Điểm học được:

1. **Policy lấy documentId từ method parameter nhưng lấy owner từ database.**
2. authentication.getName() do Spring Security xác minh thông qua HTTP Basic trong demo, không phải client tự gửi query owner.
3. canRead cho phép owner hoặc role ADMIN; canWrite chỉ cho owner. Đó là chính sách mẫu; không mặc định admin luôn có mọi quyền.
4. Nếu documentId null hoặc Authentication không có, policy **từ chối**, không mặc định permit.
5. Kiểm tra AnonymousAuthenticationToken vì isAuthenticated() trên anonymous token không phải bằng chứng user thực sự login.
6. contains ROLE_ADMIN dựa vào authority thực tế; role prefix phải thống nhất với hệ thống identity.
7. Policy chỉ kiểm tra trước khi method thực thi. **Điều kiện dữ liệu có thể thay đổi** giữa existsBy... và lần đọc bản ghi; vấn đề transaction/race sẽ được phân tích ở phần 10.

Trong sản phẩm thật, đừng dùng tài khoản username làm khóa owner toàn cục nếu có nhiều tenant. Dùng subject/userId ổn định, tenant boundaries và quyền chia sẻ dựa vào nguồn dữ liệu đáng tin.

### 6.6. DocumentService: điều kiện method security và truy vấn hạn chế

Tệp src/main/java/dev/example/serviceauth/DocumentService.java:

~~~java
package dev.example.serviceauth;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final DocumentPolicy policy;

    public DocumentService(
            DocumentRepository repository, DocumentPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize("@documentPolicy.canRead(#documentId, authentication)")
    @Transactional(readOnly = true)
    public DocumentView read(@P("documentId") Long documentId) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        DocumentEntity doc = visibleToCurrentUser(
                documentId, authentication);
        return asView(doc);
    }

    @PreAuthorize("@documentPolicy.canWrite(#documentId, authentication)")
    @Transactional
    public DocumentView rename(
            @P("documentId") Long documentId, String newTitle) {

        if (newTitle == null || newTitle.isBlank()
                || newTitle.length() > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid title");
        }

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null) {
            throw new AccessDeniedException("No authenticated caller");
        }

        DocumentEntity doc =
                repository.findByIdAndOwnerUsername(
                        documentId, authentication.getName())
                .orElseThrow(() ->
                        new AccessDeniedException("Access denied"));

        doc.rename(newTitle.trim());
        return asView(doc);
    }

    private DocumentEntity visibleToCurrentUser(
            Long documentId, Authentication authentication) {

        if (authentication == null) {
            throw new AccessDeniedException("No authenticated caller");
        }

        if (policy.hasAdminRole(authentication)) {
            return repository.findById(documentId)
                    .orElseThrow(() ->
                            new AccessDeniedException("Access denied"));
        }

        return repository.findByIdAndOwnerUsername(
                        documentId, authentication.getName())
                .orElseThrow(() ->
                        new AccessDeniedException("Access denied"));
    }

    private static DocumentView asView(DocumentEntity doc) {
        return new DocumentView(
                doc.getId(), doc.getOwnerUsername(), doc.getTitle());
    }

    public record DocumentView(
            Long id, String ownerUsername, String title) {
    }
}
~~~

Lưu ý:

- @PreAuthorize kiểm tra quyền ở điểm gọi method qua proxy, **trước khi body chạy**.
- @P("documentId") làm tên tham số ổn định cho biểu thức #documentId.
- @Transactional đưa hoạt động JPA vào một transaction khi method thực thi.
- read dùng điều kiện owner trong **truy vấn thực tế**, trừ admin được cho phép xem tài liệu tồn tại. Đây là lớp bảo vệ bổ sung khi chính sách service bị gọi sai.
- rename chỉ truy vấn bản ghi có cùng ownerUsername với caller; không nhận ownerUsername từ client.
- Entity được quản lý trong transaction; khi đổi title, Hibernate JPA dirty checking lưu thay đổi lúc transaction commit.
- Record DocumentView là kiểu Java 17 để trả dữ liệu đơn giản, không đưa JPA entity trực tiếp vào response.
- Nhánh không tồn tại/không sở hữu trả AccessDeniedException nhằm tránh khẳng định sự tồn tại của ID người khác; policy cụ thể có thể quyết định 404 thay vì 403 nếu hợp đồng API yêu cầu.
- Câu import EnableMethodSecurity trong file này không được dùng; có thể xóa khi tối ưu IDE, không ảnh hưởng biên dịch Java.
- Demo không có tenant hoặc permission sharing phức tạp; cần áp dụng cùng nguyên tắc với các khóa dữ liệu thật.

**Điều quan trọng:** Việc dùng @Transactional cùng @PreAuthorize không tự tạo một kiểm tra quyền và cập nhật **nguyên tử tuyệt đối**. Đặc biệt nếu chủ sở hữu, tenant hoặc state có thể bị thay đổi đồng thời bởi transaction khác, cần locking, version column, query cập nhật có điều kiện hoặc transaction isolation phù hợp. Không tuyên bố “có annotation rồi là chống mọi race condition”.

### 6.7. MVC controller: mỏng, không quyết định ownership thay service

Tệp src/main/java/dev/example/serviceauth/DocumentController.java:

~~~java
package dev.example.serviceauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{documentId}")
    public DocumentService.DocumentView read(
            @PathVariable Long documentId) {
        return service.read(documentId);
    }

    @PutMapping("/{documentId}")
    public DocumentService.DocumentView rename(
            @PathVariable Long documentId,
            @RequestBody RenameRequest request) {
        return service.rename(documentId, request.title());
    }

    public record RenameRequest(String title) {
    }
}
~~~

Controller chỉ nhận định danh, body và ủy quyền công việc cho service bean được Spring tiêm qua constructor. Nó không cần tự gọi policy.canRead(...) mỗi lần vì service đã đảm bảo chính sách ở điểm vào method, nhưng **HTTP rules vẫn được giữ** để chặn anonymous/URL không cho phép sớm.

Ví dụ này không thêm một method riêng để bypass service. Trong ứng dụng thật, mọi controller/resolver phải sử dụng cùng service entrypoint đã được bảo vệ, không gọi repository trực tiếp rồi gửi dữ liệu về client.

### 6.8. Chạy ứng dụng

Tạo project với đúng cấu trúc và Gradle Wrapper, sau đó:

~~~bash
./gradlew bootRun
~~~

Với PowerShell/Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi Boot đang chạy trên localhost:8080, thử GET:

~~~bash
curl -i -u alice:alice-demo-pass \
  http://localhost:8080/api/documents/101

curl -i -u bob:bob-demo-pass \
  http://localhost:8080/api/documents/101

curl -i -u admin:admin-demo-pass \
  http://localhost:8080/api/documents/101

curl -i http://localhost:8080/api/documents/101
~~~

Kết quả điển hình:

| Request | Kết quả kỳ vọng |
| --- | --- |
| alice đọc document 101 | 200, JSON có id=101 và ownerUsername=alice |
| bob đọc document 101 | 403, không trả nội dung của alice |
| admin đọc document 101 | 200 theo nhánh canRead cho ADMIN |
| anonymous đọc document 101 | 401 theo HTTP Basic |
| alice đọc document 102 của bob | 403 |
| bob sửa document 101 của alice | 403 (với PUT và CSRF hợp lệ, service từ chối quyền) |
| alice sửa document 101 | 200 khi PUT có JSON hợp lệ và CSRF token theo cấu hình |

Không nhầm lỗi 403 do CSRF với lỗi owner. Với HTTP Basic và CSRF mặc định, một lệnh curl PUT không có CSRF token có thể bị CsrfFilter từ chối **trước khi** DocumentService chạy. Vì vậy phần test dùng spring-security-test csrf() để cô lập chính sách service. Khi triển khai API stateless thuần bearer token, cần đánh giá riêng CSRF theo cơ chế authentication; không sao chép đoạn disable(csrf) một cách máy móc.

## 7. Kiểm thử: HTTP pass chưa đủ, phải gọi service trực tiếp

Tệp src/test/java/dev/example/serviceauth/DocumentAuthorizationIntegrationTest.java:

~~~java
package dev.example.serviceauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService service;

    @Test
    void ownerCanReadOwnDocumentThroughHttp() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.ownerUsername").value("alice"));
    }

    @Test
    void otherUserCannotReadDocumentThroughHttp() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("bob", "bob-demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadByExplicitBusinessPolicy() throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("admin", "admin-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerUsername").value("bob"));
    }

    @Test
    void anonymousMustAuthenticateFirst() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void userCannotModifySomeoneElsesDocument() throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("bob", "bob-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Unauthorized change\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanRenameWithValidCsrf() throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass"))
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"title\":\"Updated Alice title\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                        .value("Updated Alice title"));
    }

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(put("/api/documents/101")
                        .with(httpBasic("alice", "alice-demo-pass"))
                        .contentType("application/json")
                        .content("{\"title\":\"No CSRF\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void proxiedServiceRejectsDirectCallFromNonOwner() {
        assertThatThrownBy(() -> service.read(101L))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void proxiedServiceAllowsDirectCallFromOwner() {
        service.read(101L);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCannotWriteByAccident() {
        assertThatThrownBy(() -> service.rename(
                101L, "Not authorized"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Những test quan trọng nhất đối với đề bài này:

- HTTP request từ bob tới ID 101 bị 403, dù bob đã vượt rule .authenticated() ở SecurityFilterChain.
- **Gọi trực tiếp** DocumentService.read(101L) từ test với @WithMockUser bob cũng bị AccessDeniedException. Không có HTTP request, controller hay URL matcher nào tham gia; đây là bằng chứng method security nằm ở service entrypoint.
- alice và admin được quyền đọc theo hai nhánh policy; admin không mặc nhiên có quyền sửa.
- PUT có CSRF hợp lệ mới cho phép đánh giá quyền service, tránh ngộ nhận CsrfFilter là ownership guard.

Vì test sửa title của record 101, nếu muốn kiểm thử giá trị title ban đầu trong nhiều test thì nên reset dữ liệu hoặc dùng transaction/fixtures độc lập. Các assertion ở đây tập trung id/owner thay vì giả định thứ tự chạy test.

Đây là bộ kiểm thử minh họa cho project Boot/H2 mặc định. Khi dùng database thật, có thể thêm integration test với Testcontainers để xác thực query scoping, tenant boundary, transaction isolation và index. Không tuyên bố một bộ unit test thuần mocking đã chứng minh an toàn dữ liệu production.

## 8. Tại sao không chỉ đặt @PreAuthorize ở controller?

Một controller có thể dùng @PreAuthorize để chặn request:

~~~java
@PreAuthorize("hasRole('ADMIN')")
@GetMapping("/admin/report")
public Report report() {
    return reportService.create();
}
~~~

Điều này hữu ích để bảo vệ controller method, nhưng reportService.create() vẫn có thể được gọi từ chỗ khác mà không qua controller. Nếu use case chỉ dành cho ADMIN bất kể entrypoint, chính sách đó nên được biểu đạt ở **service boundary** hoặc ở một lớp domain authorization được mọi entrypoint sử dụng.

Không nhất thiết phải xóa tất cả annotation ở controller. Có thể dùng:

- HTTP rules cho yêu cầu xác thực và role thô;
- Controller-level @PreAuthorize khi endpoint có yêu cầu cụ thể về transport/hợp đồng;
- Service-level @PreAuthorize để bảo vệ nghiệp vụ dùng chung;
- Repository query scoping/transaction cho dữ liệu thật.

Quan trọng là **nguồn sự thật của quyền nghiệp vụ rõ ràng**, tránh sao chép hai biểu thức ACL có thể sai lệch theo thời gian.

### Chỉ kiểm tra role tại service có đủ không?

Ví dụ:

~~~java
@PreAuthorize("hasRole('USER')")
public DocumentDto read(Long documentId) {
    return repository.findById(documentId)
            .map(this::toDto)
            .orElseThrow();
}
~~~

Nếu alice và bob đều ROLE_USER, annotation này không ngăn alice đọc record của bob. Cần kiểm tra **record-level authorization**, ví dụ kiểm tra ownerId, tenantId, sharing permission hoặc policy service như bài demo.

### Truyền ownerUsername từ controller có đáng tin không?

Không nên viết:

~~~java
@PreAuthorize("#ownerUsername == authentication.name")
public DocumentDto read(Long documentId, String ownerUsername) {
    return repository.findById(documentId)
            .map(this::toDto)
            .orElseThrow();
}
~~~

nếu ownerUsername ở đây do client truyền và chưa đối chiếu với database. Attacker có thể gọi read(102, "alice") khi logged in alice và vượt biểu thức, mặc dù record 102 thuộc bob. **So sánh người gọi với một tham số tự khai không phải kiểm tra quyền sở hữu đối tượng.**

## 9. Method security hoạt động qua Spring AOP proxy: giới hạn cần biết

Spring Security method security mặc định dùng cơ chế method interception dựa trên Spring AOP proxy. Điều này đem lại các lợi ích tái sử dụng rule, nhưng cần hiểu **cách lời gọi đi qua proxy**.

### 9.1. Self-invocation không đi qua proxy

Ví dụ:

~~~java
@Service
public class DemoService {

    public String outer() {
        return inner(); // Gọi trực tiếp trên this, thường bỏ qua proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String inner() {
        return "sensitive";
    }
}
~~~

Nếu một caller gọi demoService.outer() qua proxy, bản thân outer không có rule, còn lời gọi inner() từ this.inner() xảy ra bên trong bean và **thường không qua AOP proxy**. Vì vậy @PreAuthorize trên inner có thể không được áp dụng cho đường gọi này.

Đây là một trong những rủi ro lớn nhất khi nghĩ “cứ có annotation ở method là tự an toàn ở mọi đường gọi”.

Giải pháp ưu tiên:

1. Đặt policy trên **public entrypoint** mà caller thật sự gọi.
2. Tách use case bảo mật sang bean/service riêng và inject bean đó, để caller đi qua proxy.
3. Tránh việc service được gọi bằng new thay vì lấy từ Spring container.
4. Viết test đường đi thực tế qua Spring bean, không chỉ gọi method từ chính object.
5. Khi dùng AspectJ weaving thay AOP proxy, semantics có thể khác, nhưng đó là một cấu hình kiến trúc riêng cần kiểm thử.

### 9.2. Private, final và proxy strategy

Private method không phải public join point được Spring AOP proxy intercept theo kiểu thông dụng. Final method hoặc final class có thể không được proxy theo chiến lược subclassing (CGLIB); proxy interface có những giới hạn riêng. Với Kotlin thường phải hiểu các class/method final mặc định. Không đặt **quy tắc duy nhất** bảo vệ dữ liệu vào một private helper rồi kỳ vọng Spring Security sẽ intercept mọi lần gọi.

Giữ business service có public method rõ ràng và Spring bean phù hợp; dùng test trực tiếp gọi bean qua container để chứng minh annotation được áp dụng.

### 9.3. @Transactional và @PreAuthorize không giống nhau

Hai annotation đều có thể được hỗ trợ bởi proxy/advisors, nhưng khác trách nhiệm:

- @PreAuthorize quyết định ai được phép thực thi method.
- @Transactional quản lý transaction khi method được gọi qua proxy phù hợp.
- Không annotation nào tự thay thế database constraints hoặc kiểm tra concurrency của dữ liệu nghiệp vụ.

Thứ tự advisor và phạm vi transaction có thể tùy cấu hình; đừng giả định policy và update diễn ra như một thao tác nguyên tử chỉ vì chúng nằm trên một method. Đối với nghiệp vụ nhạy cảm, cân nhắc truy vấn cập nhật có điều kiện owner/tenant/state, optimistic locking (@Version), pessimistic locks hoặc RDBMS row-level security theo threat model.

### 9.4. @Async, thread mới và message handlers

SecurityContextHolder thường dùng ThreadLocal strategy. Khi chuyển sang @Async hoặc tạo thread khác, Authentication của HTTP request **không tự động** xuất hiện ở thread mới theo cách an toàn. Có thể dùng DelegatingSecurityContextAsyncTaskExecutor hoặc thành phần propagation tương ứng, nhưng phải hiểu principal được truyền là ai và vòng đời context.

Không truyền quyền ADMIN tổng quát sang background job chỉ để vượt @PreAuthorize. Một job hệ thống nên có **service identity** với quyền rõ, audit riêng, và hoạt động qua entrypoint có kiểm soát. Nếu job làm việc thay user, cần thiết kế delegation/impersonation có giới hạn và kiểm toán.

### 9.5. Exception từ method security khi không có HTTP

Khi @PreAuthorize từ chối, Spring Security thường ném AccessDeniedException hoặc exception liên quan. Trong HTTP request, ExceptionTranslationFilter cùng handler/entrypoint phù hợp có thể biến nó thành 401/403/redirect. Trong scheduled job hoặc message listener, **không có Servlet response**: exception cần được xử lý theo semantics của job/message (retry, dead-letter, alert, fail closed).

Không catch AccessDeniedException rồi “cho qua” hoặc dùng fallback trả toàn bộ dữ liệu vì muốn tránh lỗi UI. Nếu cần trả 404 để che sự tồn tại của tài nguyên, đó là quyết định hợp đồng API có phân tích rủi ro, không phải bỏ check.

## 10. Khi kiểm tra quyền phụ thuộc dữ liệu thay đổi: vấn đề thời điểm

Hãy xét tình huống:

~~~text
T1: DocumentPolicy.existsByIdAndOwnerUsername(101, "alice") => true
T2: Một transaction khác đổi owner của 101 sang bob
T3: DocumentService.read(101) đọc nội dung mới
~~~

Nếu bước T3 gọi repository.findById không giới hạn owner mà không recheck, alice có thể nhìn dữ liệu tại trạng thái đã đổi chủ. Từ góc nhìn transaction, đó là **time-of-check to time-of-use (TOCTOU)** hoặc race trong authorization.

Bài demo dùng query findByIdAndOwnerUsername ở service cho user thường để tăng tính phòng vệ, nhưng dưới isolation level và chiến lược concurrency khác nhau vẫn cần phân tích transaction boundary. Với các thao tác chuyển quyền, chuyển tiền, duyệt đơn hoặc update nhạy cảm, dùng:

- Truy vấn trực tiếp gắn điều kiện owner/tenant:
  
~~~sql
SELECT id, owner_username, title
FROM demo_documents
WHERE id = :id
  AND owner_username = :authenticated_username;
~~~

- UPDATE có điều kiện thay vì load-then-check-then-update ở các luồng cần tính nguyên tử:

~~~sql
UPDATE demo_documents
SET title = :new_title
WHERE id = :id
  AND owner_username = :authenticated_username;
~~~

- Lock/version để chống cập nhật chồng, và kiểm tra số row được cập nhật.
- Đối với multi-tenant, thêm tenant_id trong mọi truy vấn và index phù hợp.
- Xác định rõ quyền admin, shared access, revoked access và trạng thái đối tượng tại **thời điểm thực thi**.

Trong các snippet SQL, :authenticated_username phải đến từ SecurityContext/identity provider đã xác minh; không dùng request.queryParam("owner"). Nếu database row-level security được bật, session/database principal và policy SQL cũng cần được quản lý đúng, không giả định RLS tự bật do một annotation Java.

### Vì sao @PostAuthorize đôi khi kém phù hợp?

~~~java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public DocumentDto load(Long id) {
    return repository.findById(id).map(this::toDto)
            .orElseThrow();
}
~~~

Method load đã chạy và nạp dữ liệu **trước** khi post-authorization từ chối. Có thể phù hợp với một số read-only use case, nhưng với method có side effect, sự kiểm tra sau khi ghi là quá muộn; với collection lớn, tải quá nhiều dữ liệu trước rồi lọc cũng không hiệu quả.

Ưu tiên @PreAuthorize khi có đủ thông tin quyết định quyền trước method, kết hợp query scoping tại repository. Khi phải dựa vào returnObject, hiểu rõ transaction/side effects, exception và nguy cơ lộ dữ liệu qua log/cache. Không trả entity nhạy cảm ra ngoài trước khi được authorize.

## 11. Tenant isolation và quyền trên đối tượng

Trong SaaS multi-tenant, chỉ so sánh username thường chưa đủ. Ví dụ hai tenant đều có tài khoản tên "alice". Một document với ownerUsername=alice chưa nói nó thuộc tenant nào. Chính sách thực tế nên dựa vào **ID ổn định** của user và tenant:

~~~text
Caller: userId=U1, tenantId=T1
Document 501: ownerUserId=U1, tenantId=T1 => thường cho phép
Document 502: ownerUserId=U1, tenantId=T2 => phải kiểm tra ranh giới tenant
Document 503: ownerUserId=U2, tenantId=T1 => phụ thuộc sharing/role
~~~

Không lấy tenantId từ request header tùy ý rồi cho nó ghi đè tenant thuộc principal đã xác minh. Nếu người dùng được chuyển tenant, phải có cơ chế lựa chọn và xác nhận membership, role/permission theo tenant đã chọn.

Ở service/repository nên dùng các tham số đã được xác thực/kiểm chứng và query có điều kiện. Nếu app sử dụng Hibernate filters, global query predicates hoặc RLS, phải kiểm tra tất cả code path (native SQL, batch, async, admin) có tuân chính sách không; không chỉ tin framework interceptor một cách tuyệt đối.

Với quyền chia sẻ theo object, policy có thể cần kiểm tra ACL/permission trong database. Hãy tránh nạp dữ liệu riêng tư quá sớm hoặc đưa cache dùng chung mà không phân vùng theo principal/tenant.

## 12. API bất thường và các trường hợp HTTP route không bao phủ

### 12.1. Thay đổi URL hoặc nhiều SecurityFilterChain

Nếu một controller chuyển từ /api/documents/** sang /v2/documents/** nhưng security config chưa cập nhật, authorization HTTP có thể dùng rule khác. Một phương thức service vẫn có annotation bảo vệ sẽ giúp duy trì chính sách owner, nhưng không có nghĩa endpoint mới tự an toàn ở mọi khía cạnh (CSRF, authentication entrypoint, header policy).

Khi dùng nhiều SecurityFilterChain, FilterChainProxy chọn **chain đầu tiên** match request; một rule trong chain A không bảo vệ request do chain B xử lý. Vì vậy cần test HTTP chain selection và method security.

### 12.2. Một controller gọi repository trực tiếp

~~~java
@GetMapping("/debug/documents/{id}")
public DocumentEntity debug(@PathVariable Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Nếu controller gọi repository mà **không qua DocumentService**, @PreAuthorize trên service không chạy. Bảo vệ tầng dịch vụ hiệu quả khi kiến trúc thống nhất: các đường truy cập dữ liệu phải đi qua các use case/service được bảo vệ, và những truy vấn dữ liệu nhạy cảm còn cần query scoping/RLS.

Không tuyên bố “chỉ cần annotating một service là tất cả các controller tự an toàn”. Kiểm tra repository injections trong controller, các export batch, administrative backdoors và đường code bypass.

### 12.3. Method security không giải quyết tất cả vấn đề access control

Một service cho phép user đọc document theo owner vẫn có thể gặp:

- Mass assignment: client được sửa cả ownerUserId hoặc tenantId do binding field không kiểm soát.
- Data leakage trong logs/errors/cache/tracing.
- Unsafe object deserialization hoặc SQL injection ở repository.
- Dữ liệu riêng tư xuất hiện ở một endpoint khác không đi qua service.
- BOLA ở thao tác list/search do query không lọc đúng tenant.
- Broken function-level authorization: role được phép đọc nhưng không được delete/approve.
- CSRF/clickjacking/session fixation thuộc lớp bảo vệ web khác.
- Privilege escalation qua background service account hoặc trusted-header configuration.

Method security là một lớp quan trọng của **access-control architecture**, không phải giải pháp thay mọi biện pháp bảo mật.

## 13. Hướng dẫn chẩn đoán khi Method Security “không hoạt động”

### Lỗi 1 — Quên @EnableMethodSecurity

Triệu chứng: có @PreAuthorize trên method nhưng request sai quyền vẫn chạy. Nguyên nhân: method security chưa được bật, hoặc config không được load vào application context. Cách sửa: thêm @EnableMethodSecurity trong @Configuration tương ứng, test trực tiếp Spring-managed service bean.

### Lỗi 2 — Tạo service bằng new

~~~java
DocumentService service = new DocumentService(repository, policy);
~~~

Code này tạo object Java thủ công, **không đi qua Spring AOP proxy**. Annotation @PreAuthorize không được intercept như khi @Autowired bean. Trong ứng dụng mẫu, controller nhận DocumentService bằng constructor injection từ Spring.

### Lỗi 3 — Self-invocation trong cùng bean

Method public gọi method khác bằng this.inner() có thể bypass proxy security. Tách protected operation sang bean riêng hoặc đưa rule lên entrypoint public, test đường gọi thực tế.

### Lỗi 4 — @PreAuthorize chỉ dùng hasRole('USER')

Role USER không xác minh owner hoặc tenant. Thêm policy kiểm tra đối tượng từ DB và principal đã xác thực. Test ID của user khác, không chỉ cùng user.

### Lỗi 5 — Sai tên tham số trong SpEL

#documentId null hoặc expression evaluation lỗi khi thiếu metadata -parameters/@P. Dùng @P("documentId"), test trực tiếp gọi service với ID và xác thực cụ thể.

### Lỗi 6 — Sai role prefix

User.withUsername(...).roles("ADMIN") tạo ROLE_ADMIN; hasRole('ADMIN') thường kiểm tra ROLE_ADMIN. Nếu app dùng authorities không có prefix, biểu thức và mapping phải nhất quán. Không sửa bằng cách bỏ role check.

### Lỗi 7 — Chỉ test controller với mock service

Nếu @WebMvcTest dùng @MockBean DocumentService và không test service thật, test HTTP có thể pass mà không hề chạy method authorization. Bổ sung @SpringBootTest + real DocumentService hoặc một integration test focused method security.

### Lỗi 8 — Dữ liệu đổi owner giữa kiểm tra và dùng

Chính sách kiểm tra existsBy... trước rồi query sau có thể gặp race nếu transaction khác thay chủ. Kết hợp owner-scoped queries, conditional update, version/locks và transaction design.

### Lỗi 9 — @Async không thấy Authentication

Thread mới không nhận ThreadLocal context như request thread. Cần propagation có kiểm soát hoặc service identity riêng; không cấp quyền rộng bừa để tránh exception.

### Lỗi 10 — Dữ liệu người dùng ẩn ở một đường khác

Service đã được bảo vệ nhưng một controller dùng repository trực tiếp hoặc batch export bypass. Rà mọi entrypoint, kiến trúc module boundaries, query scoping, và test negative đa đường vào.

### Lỗi 11 — AccessDeniedException bị swallow

Một catch (Exception e) trả về document mặc định hoặc retry dưới ADMIN có thể vượt policy. Không biến access denied thành “cho phép”; trả lỗi phù hợp với entrypoint, ghi audit an toàn.

### Lỗi 12 — Dùng ownerUsername từ request JSON

Client có thể giả mạo ownerUsername. Lấy owner của document từ DB và identity đã xác minh từ Authentication, không đối chiếu hai chuỗi cùng do client cung cấp.

### Lỗi 13 — Quá tin @PostAuthorize trên method có side effect

Permission check sau khi method chạy không tự undo ngoại tác. Dùng pre-authorization hoặc validation/transaction/compensating action phù hợp; không post-filter dữ liệu nhạy cảm sau khi đã serialize/return.

### Lỗi 14 — Phân quyền ở HTTP lẫn service nhưng kết quả status gây nhầm

Nếu HTTP rule từ chối trước, service không chạy. Nếu HTTP cho qua và @PreAuthorize từ chối, exception được web security xử lý thành 403/challenge tùy Authentication. Không nhìn duy nhất status để suy tầng từ chối; dùng test và telemetry không lộ secrets.

## 14. Checklist production cho service-level authorization

1. **Xác định use case nhạy cảm:** xem, sửa, xóa, xuất dữ liệu, chuyển quyền, approve, truy cập PII.
2. **Định nghĩa rule HTTP:** method/path/role thô, authentication entry point, deny-by-default và nhiều SecurityFilterChain.
3. **Bật @EnableMethodSecurity** và kiểm thử annotation trên Spring-managed service bean thật.
4. **Ghi policy theo object/tenant/permission**, không chỉ authenticated hoặc role USER.
5. **Không tin ID/owner/tenant tự khai** trong URL, query, header, body như căn cứ duy nhất cấp quyền.
6. **Chọn principal ID ổn định**, ánh xạ JWT subject/email/username đúng theo identity provider.
7. **Đảm bảo mọi entrypoint qua service được bảo vệ:** REST, MVC, GraphQL, background, message, controller mới.
8. **Chống bypass proxy:** không new protected bean, không self-invocation mù, không đặt policy duy nhất ở private/final method.
9. **Kết hợp query scoping/transaction** và DB constraints để bảo vệ object, chống IDOR và race.
10. **Dùng @PreAuthorize đúng thời điểm**, cân nhắc khi @PostAuthorize/@PostFilter có dữ liệu lớn hoặc side effects.
11. **Thiết kế quyền của job/system identities** và context propagation cho async an toàn.
12. **Kiểm thử dương và âm:** owner, người khác, admin, anonymous, tenant khác, tài liệu không tồn tại, quyền bị thu hồi.
13. **Kiểm thử hai loại:** MockMvc trên HTTP endpoint và gọi trực tiếp bean service từ Spring context.
14. **Đo lường và audit:** ai bị từ chối, resource class nào; không log password, token, cookie hay dữ liệu bí mật.
15. **Rà các đường bypass:** controller gọi repository trực tiếp, exports, scheduled tasks, cache và native queries.
16. **Regression sau nâng framework:** kiểm tra @EnableMethodSecurity, SpEL parameter binding, proxy/AOP behavior, SecurityFilterChain và exception mapping.
17. **Least privilege:** service account không mặc định ADMIN; admin có thể đọc nhưng không nhất thiết sửa.
18. **Kiểm soát giao dịch và quyền cập nhật:** thay đổi owner/state đồng thời phải dùng policy tại thời điểm thao tác.
19. **Không dựa vào HTTP status duy nhất** để xác định tầng xử lý; có test trace và invariant nghiệp vụ.
20. **Tài liệu hóa policy gần code** và định kỳ kiểm tra security review khi thêm feature hoặc endpoint.

## 15. Câu hỏi tự luyện

**Câu 1.** Nếu URL /api/documents/** chỉ cần .authenticated(), user alice có mặc nhiên được xem document của bob không?

**Đáp án:** HTTP rule chỉ yêu cầu login; nó không kiểm tra ownership. Nếu service thiếu bảo vệ, alice có thể đọc dữ liệu của bob bằng cách thay ID. Cần object-level authorization.

**Câu 2.** Vì sao @PreAuthorize trên DocumentService có ích khi một controller mới được thêm?

**Đáp án:** nếu controller mới gọi service bean qua Spring proxy, chính sách service vẫn được đánh giá, ngay cả khi controller mới không lặp lại logic owner.

**Câu 3.** @EnableMethodSecurity có tự xuất hiện khi cấu hình SecurityFilterChain không?

**Đáp án:** không nên giả định. Phải bật method security rõ trong config; test annotation trên bean thật để xác nhận.

**Câu 4.** @PreAuthorize("hasRole('USER')") đã đủ chống IDOR chưa?

**Đáp án:** chưa. Nhiều người có cùng role USER, nhưng quyền trên từng record có thể khác; phải đối chiếu owner/tenant/permission.

**Câu 5.** Nếu gọi this.securedMethod() từ trong cùng bean thì annotation luôn chạy không?

**Đáp án:** không. Lời gọi nội bộ thường bypass Spring AOP proxy. Đặt rule trên public entrypoint hoặc tách protected operation sang bean được inject.

**Câu 6.** Vì sao test với @WithMockUser trực tiếp gọi service có giá trị riêng so với MockMvc?

**Đáp án:** nó chứng minh method-level authorization độc lập với HTTP URL và controller. Nếu chỉ MockMvc pass, có thể rule HTTP đã chặn mà service không được bảo vệ.

**Câu 7.** Nếu client gửi ownerUsername="alice" trong JSON, service có thể dựa vào nó để xác minh ownership không?

**Đáp án:** không. Client kiểm soát body, nên phải lấy owner thực từ database và caller từ Authentication đã được xác minh.

**Câu 8.** @PostAuthorize có phù hợp để kiểm soát một method chuyển tiền không?

**Đáp án:** thường không phù hợp như kiểm tra duy nhất, vì method có side effect trước khi permission được đánh giá; cần pre-check, transaction và database constraints.

**Câu 9.** Có đủ nếu canRead kiểm tra owner bằng existsBy... rồi findById sau đó không?

**Đáp án:** phải xét race: owner có thể đổi giữa hai bước. Kết hợp owner-scoped query, transaction/isolation hoặc locking theo mức bảo mật nghiệp vụ.

**Câu 10.** Service method được gọi từ @Scheduled job không có HTTP request. SecurityContext ở đâu ra?

**Đáp án:** job cần một service identity/delegation model rõ. Không có HTTP SecurityFilterChain tự tạo Authentication; async/thread contexts cũng cần propagation hoặc identity riêng.

**Câu 11.** Vì sao cùng username ở hai tenant có thể làm policy sai?

**Đáp án:** username không nhất thiết là định danh toàn cục. Cần userId và tenantId ổn định từ nguồn đáng tin, kiểm tra theo cả hai trong business query/policy.

**Câu 12.** Nếu một controller gọi repository trực tiếp thay vì service đã có @PreAuthorize thì sao?

**Đáp án:** method security trên service không chạy. Cần kiến trúc entrypoints thống nhất, hạn chế đường bypass và bổ sung database/query scoping.

## Kết luận

**HTTP authorization bảo vệ cửa vào web; service-layer authorization bảo vệ use case và dữ liệu nghiệp vụ ở nơi nhiều đường gọi cùng hội tụ.** Hai lớp không trùng vai trò. HTTP rules giúp ngăn anonymous và các phương thức/URL không hợp lệ sớm. Method security giúp bảo đảm **ai được đọc/sửa đối tượng cụ thể**, kể cả khi service được gọi từ controller khác hoặc một entrypoint không phải HTTP.

Trong Spring Security Servlet, hãy dùng **@EnableMethodSecurity + @PreAuthorize** trên những public service methods được gọi qua Spring proxy, áp dụng policy dựa trên Authentication đáng tin và ownership/tenant từ database. Kết hợp truy vấn hạn chế theo owner, transaction và kiểm thử trực tiếp bean để tránh ảo tưởng “annotation có mặt tức là bảo mật đã đủ”.

Một thiết kế vững không hỏi duy nhất “request có login hay không?”, mà còn hỏi **“chủ thể này, trong ngữ cảnh này, có quyền thực hiện hành động này trên chính dữ liệu này không?”**.