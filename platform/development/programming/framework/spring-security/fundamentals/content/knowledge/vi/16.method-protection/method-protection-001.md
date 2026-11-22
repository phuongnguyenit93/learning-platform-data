# Vì sao tầng dịch vụ vẫn cần kiểm tra quyền ngoài quy tắc HTTP?

> **Phạm vi:** Spring Security – fundamentals → **Bảo vệ phương thức**. Mục tiêu của bài là hiểu giới hạn của phân quyền theo URL/HTTP và cách bảo vệ nghiệp vụ tại service, nơi một hành động có thể được gọi qua nhiều đường thực thi khác nhau.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao quy tắc `authorizeHttpRequests` không đủ để bảo vệ mọi lời gọi service.
2. Phân biệt kiểm tra quyền ở **HTTP boundary**, **service method** và **data access/domain boundary**.
3. Dùng `@EnableMethodSecurity` và `@PreAuthorize` để chặn lời gọi Spring-managed service trước khi nghiệp vụ chạy.
4. Hiểu vai trò Spring AOP proxy, `AuthorizationManagerBeforeMethodInterceptor` và lý do self-invocation có thể vượt qua annotation.
5. Xây kiểm tra quyền dựa trên permission, **owner**, **tenant** và dữ liệu được xác nhận từ server; tránh lỗi IDOR/BOLA.
6. Kiểm thử cùng một policy cả qua HTTP và bằng cách gọi trực tiếp service bean.
7. Phân tích trường hợp job, event/message consumer, `@Async`, transaction và ứng dụng WebFlux.

## 2. Vấn đề cốt lõi: HTTP chỉ là một cửa vào

Trong Spring MVC, cấu hình thường thấy:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**").hasAuthority("DOCUMENT_READ")
    .anyRequest().denyAll()
);
~~~

Đoạn trên là một phần của cấu hình Servlet `SecurityFilterChain`; nó **kiểm tra HTTP requests đi qua security filter chain**. Đây là lớp bảo vệ quan trọng nhưng nó không tự động gắn điều kiện `DOCUMENT_READ` vào mọi cách gọi method `DocumentService.read(...)`.

Giả sử service có thể được sử dụng từ:

- `DocumentController`: request do trình duyệt/mobile gọi;
- `DocumentExportJob`: job theo lịch hoặc tác vụ nền;
- `DocumentMessageConsumer`: xử lý message Kafka/RabbitMQ;
- `AdminTool`: CLI, batch hoặc internal integration;
- service khác trong cùng ứng dụng;
- một HTTP controller mới được thêm vào sau này.

Nếu chỉ đặt quyền ở `/api/documents/**`, policy phụ thuộc vào từng caller nhớ cấu hình đúng endpoint của nó. Một caller qua message hoặc gọi trực tiếp Java method **không phải HTTP request**, nên URL matcher không được đánh giá. Ngay trong HTTP, một route mới hoặc security filter chain cấu hình sai có thể vô tình mở đường vào cùng nghiệp vụ.

**Nguyên tắc:** *Khi một thao tác mang quyền nghiệp vụ hoặc tác động dữ liệu nhạy cảm, quyền cần được kiểm tra ở ranh giới đáng tin cậy gần thao tác đó.* Phân quyền HTTP và method nên bổ sung cho nhau.

### Sơ đồ hai lớp bảo vệ

~~~text
Client HTTP                 Scheduled Job / Message / Internal Bean
    |                                      |
    v                                      |
SecurityFilterChain                       |
    | authorizeHttpRequests               |
    | (route, method, coarse permission)  |
    v                                      v
Controller  -------------------------> Spring service proxy
                                          |
                                          v
                                 @PreAuthorize / policy
                                    |          |
                                  DENY       ALLOW
                                    |          |
                                    v          v
                           AccessDenied   Business method
                                            |
                                            v
                                   Repository / database
                                   (tenant/owner scope)
~~~

Spring method security chỉ hoạt động khi được **bật** và lời gọi đi qua interceptor/proxy phù hợp. Một lời gọi thông thường tới object `new DocumentService(...)` ngoài Spring hoặc self-invocation bỏ qua proxy có thể không được intercept; phần sau sẽ giải thích cách khắc phục.

## 3. Phân biệt ba nơi đặt quy tắc

| Tầng | Input biết rõ nhất | Ví dụ | Bảo vệ được |
| --- | --- | --- | --- |
| HTTP request | Path, HTTP method, authentication, headers đã xác minh | `GET /api/documents/**` cần `DOCUMENT_READ` | Cửa vào HTTP tương ứng |
| Service method | Hành động nghiệp vụ, method arguments, principal, trạng thái domain | `readDocument(id)` chỉ cho owner cùng tenant | Mọi caller **đi qua secured Spring proxy** |
| Repository / database / domain | Bản ghi thực, tenant ID thật, owner thật, trạng thái/phiên bản | Query có điều kiện `tenant_id = ?`; policy tại update | Phạm vi và tính toàn vẹn của dữ liệu được xử lý |

Ba tầng giải quyết ba vấn đề khác nhau. HTTP authorization có thể chặn sớm các request vô nghĩa, nhưng `hasAuthority("DOCUMENT_READ")` không biết user muốn đọc **tài liệu nào** nếu chưa tra cứu tài liệu. Service method có `id`, ngữ cảnh nghiệp vụ và repository để kiểm tra owner/tenant. Data access nên áp điều kiện scope ngay trong truy vấn đối với tập dữ liệu lớn hoặc multi-tenant để giảm nguy cơ một dòng dữ liệu lọt ra ngoài.

Một rule tốt thường có dạng:

~~~text
ALLOW readDocument(user, documentId)
    khi user authenticated
     AND user có DOCUMENT_READ
     AND tài liệu có tồn tại
     AND tài liệu thuộc tenant được phép
     AND (user là owner HOẶC có quyền chia sẻ/quản lý hợp lệ)
    còn lại: DENY
~~~

Đây là **pseudocode**, chưa phải Java. Trong nhiều hệ thống, việc tài liệu không tồn tại hay user không có quyền biết tài liệu tồn tại cũng cần thống nhất cách trả 403/404, tránh tiết lộ ID. Đừng tin `tenantId` hay `owner` chỉ vì chúng được client truyền lên từ path/header/body.

## 4. Những lý do cần thêm kiểm tra tại service

### 4.1. Cùng nghiệp vụ, nhiều entry points

Tại HTTP boundary, `authorizeHttpRequests` được áp cho request matcher. Nhưng job, event listener, command handler và lời gọi nội bộ không chạy qua `AuthorizationFilter` của Servlet. Nếu quy tắc chỉ sống trong controller/HTTP config, mỗi entry point có thể dùng một chính sách khác nhau.

Một policy tại service tạo điểm kiểm tra chung cho những lời gọi đi qua bean proxy. Khi một luồng background cần quyền đặc biệt, hãy thiết kế identity/service principal đáng tin cậy hoặc chính sách cho system action rõ ràng. Không đơn giản tắt method security để job chạy được.

### 4.2. Quy tắc URL khó biểu đạt quyền trên một bản ghi

`GET /api/documents/101` và `GET /api/documents/201` cùng match `/api/documents/**`. Nhưng tài liệu 101 có thể thuộc tenant A và tài liệu 201 thuộc tenant B. Quyền `DOCUMENT_READ` chỉ cho biết *loại hành động*; điều kiện *đối tượng nào* cần dữ liệu thật.

Nếu chỉ dựa vào `hasAuthority("DOCUMENT_READ")` rồi gọi `findById(id)` không kiểm tra tenant, kẻ tấn công có tài khoản hợp lệ có thể thay ID để lấy tài liệu khác (**BOLA / Broken Object Level Authorization**, hay IDOR trong nhiều tình huống).

### 4.3. Controller và URL có thể được tổ chức lại

Một ứng dụng có thể thêm route admin, version `/v2`, GraphQL resolver hay public integration API. Từng URL sẽ cần policy riêng, nhưng quyền đọc/sửa tài liệu nên nhất quán ở service. Đặt rule tại method giúp giảm rủi ro khi đổi routing hoặc tái sử dụng logic.

### 4.4. Tránh chỉ bảo vệ nơi gọi mà bỏ ngỏ nơi có side effect

Ví dụ `transferMoney`, `approveInvoice`, `deleteAccount`: cần xác minh quyền **trước** khi gửi tiền, cập nhật DB hay gọi hệ thống bên ngoài. Nếu service thực thi mà không tự kiểm tra, một caller khác có thể gây side effect dù HTTP endpoint chính đã được bảo vệ.

### 4.5. Business policy cần ngữ cảnh nghiệp vụ

Quy tắc có thể dựa vào trạng thái:

- Chỉ owner được sửa khi tài liệu ở `DRAFT`;
- Chỉ approver của cùng tenant được duyệt hóa đơn trong giới hạn của họ;
- Dữ liệu `CONFIDENTIAL` yêu cầu permission bổ sung;
- Người dùng bị khóa hoặc quyền đã thu hồi không được tiếp tục thực thi.

Những điều kiện này thuộc domain/policy service, khó bảo trì nếu copy vào nhiều controller hay các biểu thức URL matcher.

### 4.6. Tạo khả năng kiểm thử độc lập với HTTP

Có thể test `DocumentService.read(101)` trực tiếp với `@WithMockUser` và khẳng định `AccessDeniedException` khi thiếu quyền. Test này bảo vệ business boundary ngay cả khi endpoint được đổi. HTTP integration test vẫn cần để bảo đảm routing/security chain hoạt động đúng.

### 4.7. Giảm phụ thuộc vào một cấu hình dễ sai

Các lỗi như matcher quá rộng, thứ tự route sai, quên bảo vệ route mới, sai `securityMatcher` khi có nhiều `SecurityFilterChain` hoặc sai dispatcher policy đều có thể ảnh hưởng bảo vệ HTTP. Method security là lớp độc lập giúp hạn chế thiệt hại, dù bản thân nó cũng phải cấu hình và test cẩn thận.

**Kết luận kỹ thuật:** Service authorization không làm HTTP authorization thừa đi. Lớp HTTP chặn request không hợp lệ sớm, còn service bảo vệ nghiệp vụ khi được gọi qua các đường khác nhau.

## 5. Cơ chế method security của Spring Security

Bật tính năng ở một class cấu hình:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Đây là fragment, cần các import Spring tương ứng. `spring-boot-starter-security` **không tự bật method security** chỉ vì bạn đã thêm dependency. Với Spring Security 6.x/7.x, `@EnableMethodSecurity` là API phổ biến; `@EnableGlobalMethodSecurity` là cách cũ.

Ví dụ:

~~~java
@Service
public class DocumentService {
    @PreAuthorize("hasAuthority('DOCUMENT_READ')")
    public Document read(long id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

Đoạn minh họa này cần `Document`, `repository` và các import trong ứng dụng thật, không phải file tự chạy. `@PreAuthorize` diễn đạt một điều kiện cần có **trước khi gọi method**. Nếu user không thỏa, method sẽ không được thực thi qua đường Spring AOP method-security interceptors.

Luồng thường gặp:

~~~text
Caller --> Spring-managed service proxy
            |
            v
  AuthorizationManagerBeforeMethodInterceptor
            |
            v
     evaluate @PreAuthorize
            |
          PASS? -------- no ---> AccessDeniedException
            |
           yes
            |
            v
      execute service method
            |
            v
        return result
~~~

Spring Security dùng cơ chế `AuthorizationManager` và các interceptor tương ứng, ví dụ `PreAuthorizeAuthorizationManager`. Phần lớn ứng dụng không cần tự tạo các interceptor này; `@EnableMethodSecurity` kích hoạt chúng.

### @PreAuthorize, @PostAuthorize và @PostFilter

| Annotation | Thời điểm | Trường hợp phù hợp | Cảnh báo |
| --- | --- | --- | --- |
| `@PreAuthorize` | Trước method body | Quyền sửa/xóa/duyệt, permission và method arguments | Muốn biết owner thật có thể phải truy vấn trước |
| `@PostAuthorize` | Sau method body, xét `returnObject` | Kiểm tra quyền dựa trên kết quả đã đọc | Side effect của method đã xảy ra trước khi deny |
| `@PreFilter` | Lọc một số input collection trước gọi | Lọc input theo policy | Không phù hợp mọi loại input hoặc khối lượng lớn |
| `@PostFilter` | Lọc collection kết quả | Một số danh sách nhỏ | Có thể đã tải quá nhiều dòng trước khi lọc |
| `@Secured` / `@RolesAllowed` | Trước lời gọi | Quy tắc vai trò đơn giản | Cần cấu hình bật tương ứng, kém linh hoạt hơn SpEL |

**Không dùng `@PostAuthorize` cho thao tác chuyển tiền hoặc xóa dữ liệu** rồi nghĩ Spring sẽ hoàn tác side effect khi quyền không hợp lệ. Hãy kiểm tra trước mutation, phối hợp transaction và truy vấn ràng buộc theo tài nguyên.

### Ví dụ expression

~~~java
@PreAuthorize("hasAuthority('INVOICE_APPROVE')")
public void approve(long invoiceId) { /* ... */ }

@PreAuthorize("hasRole('ADMIN') or hasAuthority('USER_MANAGE')")
public void deactivateUser(long userId) { /* ... */ }

@PreAuthorize("hasAuthority('DOCUMENT_READ') and @documentPolicy.canRead(authentication, #p0)")
public String readDocument(long documentId) { /* ... */ }
~~~

Các method ở trên là ví dụ cú pháp, không chạy độc lập. `#p0` tham chiếu tham số vị trí 0 của method trong Spring Method Security expression, tránh phụ thuộc metadata tên tham số trong build chưa cấu hình. `@documentPolicy` trỏ tới Spring bean có tên `documentPolicy`; `authentication` do security expression cung cấp. Với build hỗ trợ đọc tên tham số, có thể dùng `#documentId` để dễ đọc.

## 6. Khi nào một @PreAuthorize chỉ kiểm tra role là chưa đủ?

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('DOCUMENT_READ')")
public Document read(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Policy này bảo đảm caller có quyền **đọc tài liệu nói chung** nhưng không ràng buộc **tài liệu được đọc**. Nếu có 10.000 tài liệu thuộc nhiều khách hàng, mọi user mang `DOCUMENT_READ` có thể đọc hết nếu biết ID.

Để hoàn thiện, phải có:

1. Permission tổng quát cho hành động `READ`.
2. Tenant scope đáng tin cậy của principal.
3. Owner hoặc quan hệ chia sẻ hợp lệ của document.
4. Điều kiện trạng thái document (đã xóa, bị khóa, chưa công bố...) nếu nghiệp vụ yêu cầu.
5. Cách xử lý đối tượng không tồn tại và lỗi repository một cách có kiểm soát.

Cùng tenant **chưa đủ** nếu chỉ owner được đọc. Owner trùng tên **chưa đủ** nếu tenant khác. Role `ADMIN` không tự động hàm ý toàn quyền xuyên tenant: quyền cross-tenant là policy riêng cần được cấp chính thức và audit.

## 7. Demo có thể chạy: HTTP rule + service rule + ownership

Ứng dụng mẫu dùng **Java 17**, **Spring Boot 3.5.7**, **Spring MVC/Servlet**, **Spring Security 6.5 line**, Maven. Mục đích là cho thấy HTTP chỉ kiểm tra `DOCUMENT_READ`, còn service kiểm tra thêm owner và tenant. Không dùng WebFlux trong demo này để tách rõ mô hình `SecurityFilterChain` và `SecurityContextHolder` của Servlet.

### Cấu trúc dự án

~~~text
document-authorization/
  pom.xml
  src/main/java/com/example/authz/
    AuthzApplication.java
    SecurityConfig.java
    DocumentStore.java
    TenantDirectory.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  src/test/java/com/example/authz/
    DocumentAuthorizationTests.java
~~~

Tạo từng file đúng đường dẫn/package. Dùng Maven 3.9+ và JDK 17+ đã cài, hoặc sinh Maven Wrapper bằng Spring Initializr. Trong demo, danh sách user, tenant và document đều để trong bộ nhớ để dễ hiểu; production dùng kho dữ liệu/identity provider được kiểm soát.

### File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>document-authorization</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### File AuthzApplication.java

~~~java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthzApplication.class, args);
    }
}
~~~

### File DocumentStore.java

~~~java
package com.example.authz;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    public record Document(
        long id, String tenantId, String owner, String body
    ) {}

    private final Map<Long, Document> documents = Map.of(
        101L, new Document(101, "north", "alice", "alice-document-101"),
        102L, new Document(102, "north", "bob", "bob-document-102"),
        201L, new Document(201, "south", "carol", "carol-document-201")
    );

    public Optional<Document> findById(long id) {
        return Optional.ofNullable(documents.get(id));
    }
}
~~~

Mỗi tài liệu có ID, tenant và owner do server lưu. `DocumentStore` là repository minh họa; thay nó bằng database thật thì cần thiết kế query/transaction phù hợp.

### File TenantDirectory.java

~~~java
package com.example.authz;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {
    private final Map<String, String> tenantByUser = Map.of(
        "alice", "north",
        "bob", "north",
        "carol", "south"
    );

    public Optional<String> tenantOf(String username) {
        return Optional.ofNullable(tenantByUser.get(username));
    }
}
~~~

Tenant scope của user lấy từ danh bạ **do server quản lý**, không tin vào query param/header mà client tùy ý đặt. Trong production, thông tin tenant có thể đến từ database hoặc JWT claim được issuer đáng tin cậy ký và được resource server kiểm tra chữ ký, audience, issuer, expiry đầy đủ.

### File DocumentPolicy.java

~~~java
package com.example.authz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentStore store;
    private final TenantDirectory directory;

    public DocumentPolicy(DocumentStore store, TenantDirectory directory) {
        this.store = store;
        this.directory = directory;
    }

    public boolean canRead(Authentication authentication, long id) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        String username = authentication.getName();

        return directory.tenantOf(username)
            .flatMap(tenant -> store.findById(id)
                .filter(doc -> doc.tenantId().equals(tenant)
                    && doc.owner().equals(username)))
            .isPresent();
    }
}
~~~

Quyết định `canRead` trả `true` khi người gọi có identity hợp lệ, tài liệu tồn tại, cùng tenant và đúng owner. Check permission tổng quát sẽ đặt ở `@PreAuthorize` của service. Nếu không tìm thấy document hoặc tenant hợp lệ, policy **deny**. Mẫu này không có quyền chia sẻ/admin; nếu thêm, phải định nghĩa rõ policy và test thay vì ngầm coi role admin có mọi quyền.

### File DocumentService.java

~~~java
package com.example.authz;

import java.util.NoSuchElementException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize(
        "hasAuthority('DOCUMENT_READ') and "
        + "@documentPolicy.canRead(authentication, #p0)"
    )
    public String read(long id) {
        return store.findById(id)
            .orElseThrow(() -> new NoSuchElementException("Document missing"))
            .body();
    }
}
~~~

Đây là **điểm chốt của demo**: kể cả khi một caller không đi qua HTTP filter, nếu caller gọi `DocumentService` qua Spring proxy, `@PreAuthorize` vẫn áp chính sách. Policy dùng `#p0` để nhận `id`, gọi `DocumentPolicy` đã được Spring quản lý, rồi mới cho method đọc body. Mọi caller được phép đều phải thỏa cả permission lẫn owner/tenant condition.

Trong phiên bản demo, tài liệu không tồn tại được `DocumentPolicy` từ chối, nên route thường nhận 403 thay vì chạy vào `NoSuchElementException`. Với production, hãy thiết kế quy tắc 403/404 và error handling nhất quán; không dùng lỗi 404 giả nếu mục tiêu nghiệp vụ cần phân biệt cho admin có quyền.

### File DocumentController.java

~~~java
package com.example.authz;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/docs")
public class DocumentController {
    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String read(@PathVariable("id") long id) {
        return service.read(id);
    }
}
~~~

Controller chỉ chuyển request vào service, không tự kiểm tra owner/tenant. HTTP rule vẫn là lớp chặn đầu tiên; business policy nằm trong `DocumentService`. Nếu thêm controller thứ hai dùng cùng service, rule tại service vẫn được áp khi bean được gọi qua proxy.

### File SecurityConfig.java

~~~java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/docs/**")
                    .hasAuthority("DOCUMENT_READ")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .authorities("DOCUMENT_READ")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob123"))
            .authorities("DOCUMENT_READ")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("carol123"))
            .authorities("DOCUMENT_READ")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol);
    }
}
~~~

Ở đây:

- `@EnableMethodSecurity` **bật kiểm tra method**, nếu quên annotation này thì `@PreAuthorize` ở service sẽ không có hiệu lực như mong đợi.
- HTTP GET `/api/docs/**` chỉ kiểm tra user có `DOCUMENT_READ`. Một user có quyền này vẫn phải qua owner/tenant check của service.
- `anyRequest().denyAll()` làm mặc định từ chối cho các route khác trong demo.
- `httpBasic` giúp thử nghiệm nhanh. Cần HTTPS nếu gửi Basic credentials qua mạng; ở localhost chỉ dùng để học.
- `InMemoryUserDetailsManager` và mật khẩu mẫu không phù hợp production. Dùng identity provider và password/secret management tương ứng.
- Demo chỉ cung cấp GET; vì vậy không tắt CSRF. Nếu thêm POST/PUT/DELETE, hãy quyết định CSRF policy phù hợp với cookie/session hay stateless API và kiểm thử.

**Không thêm `spring-boot-starter-webflux` vào demo này.** Với Spring WebFlux cần `SecurityWebFilterChain`/`@EnableReactiveMethodSecurity` và cơ chế reactive security context khác với Servlet.

## 8. Chạy ứng dụng và quan sát sự khác nhau

Từ thư mục chứa `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Nếu tạo Maven Wrapper từ Spring Initializr, có thể dùng `./mvnw test` và `./mvnw spring-boot:run`; trên PowerShell dùng `.\mvnw.cmd test` và `.\mvnw.cmd spring-boot:run`. Khi Spring Boot lắng nghe ở `localhost:8080`, dùng terminal khác:

~~~bash
curl -i http://localhost:8080/api/docs/101
curl -i -u alice:alice123 http://localhost:8080/api/docs/101
curl -i -u bob:bob123 http://localhost:8080/api/docs/101
curl -i -u carol:carol123 http://localhost:8080/api/docs/101
curl -i -u bob:bob123 http://localhost:8080/api/docs/102
curl -i -u carol:carol123 http://localhost:8080/api/docs/201
curl -i -u alice:alice123 http://localhost:8080/api/docs/999
~~~

Trên PowerShell, `curl` có thể là alias của `Invoke-WebRequest` ở một số phiên bản; có thể gọi `curl.exe` với các tham số giống trên.

Kết quả **kỳ vọng theo code** (không phải log build đã chạy trong tài liệu):

| Request | HTTP kỳ vọng | Response body khi thành công | Nguyên nhân |
| --- | --- | --- | --- |
| Anonymous → 101 | 401 | — | Chưa authentication, HTTP yêu cầu `DOCUMENT_READ` |
| Alice → 101 | 200 | `alice-document-101` | Có authority, cùng tenant và là owner |
| Bob → 101 | 403 | — | Bob có authority, cùng tenant nhưng không là owner |
| Carol → 101 | 403 | — | Carol có authority nhưng khác tenant và không là owner |
| Bob → 102 | 200 | `bob-document-102` | Bob là owner, đúng tenant |
| Carol → 201 | 200 | `carol-document-201` | Carol là owner, đúng tenant |
| Alice → 999 | 403 trong demo | — | Policy không tìm thấy bản ghi, nên fail closed |

Kết quả 401/403 đến từ security entry point và access-denied handling mặc định kết hợp với HTTP Basic và method security; response headers/body lỗi có thể thay đổi theo phiên bản/cấu hình. Khi áp dụng cho sản phẩm, test status và API error contract của chính hệ thống.

### Nếu chỉ giữ HTTP rule thì lỗi gì xảy ra?

Giả sử tạm xóa `@EnableMethodSecurity` hoặc `@PreAuthorize` khỏi service trong một môi trường thử nghiệm. Alice và Bob đều có `DOCUMENT_READ`, nên HTTP rule sẽ cho Bob vào `/api/docs/101`. Nếu service trực tiếp `store.findById(101)` mà không kiểm tra owner, Bob sẽ lấy nội dung tài liệu của Alice. Đây chính là lỗ hổng mà service-level authorization giải quyết.

Không nên triển khai thử nghiệm tắt policy lên môi trường có dữ liệu thật. Dùng test data đã biết, đưa policy trở lại, rồi giữ regression tests để ngăn lỗi quay lại.

## 9. Kiểm thử cả HTTP lẫn trực tiếp service

Với `pom.xml` ở trên đã có `spring-boot-starter-test` và `spring-security-test`, thêm file sau.

### File DocumentAuthorizationTests.java

~~~java
package com.example.authz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentService service;

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get("/api/docs/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOCUMENT_READ")
    void aliceCanReadHerDocumentOverHttp() throws Exception {
        mvc.perform(get("/api/docs/101"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice-document-101"));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOCUMENT_READ")
    void bobCannotReadAlicesDocumentOverHttp() throws Exception {
        mvc.perform(get("/api/docs/101"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOCUMENT_READ")
    void bobCannotReadAlicesDocumentDirectlyThroughService() {
        assertThrows(AccessDeniedException.class, () -> service.read(101));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOCUMENT_READ")
    void aliceCanReadDirectlyThroughService() {
        assertEquals("alice-document-101", service.read(101));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "DOCUMENT_READ")
    void tenantBoundaryIsEnforced() {
        assertThrows(AccessDeniedException.class, () -> service.read(101));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "SOME_OTHER_RIGHT")
    void ownerWithoutReadAuthorityIsRejected() {
        assertThrows(AccessDeniedException.class, () -> service.read(101));
    }
}
~~~

**Giải thích hai loại test:**

- `MockMvc` khởi tạo request giả trong Spring Test, đi qua Servlet security filter chain. Nó kiểm tra đúng rule HTTP và cách trả status.
- Test `service.read(...)` gọi **Spring-managed service proxy** được inject bởi container. Không có HTTP request nào ở đây; nếu vẫn ném `AccessDeniedException` thì method-security boundary đang hoạt động.
- `@WithMockUser` tạo principal bảo mật dùng trong test. Nó **không kiểm tra** việc xác thực Basic credentials thật hoặc JWT validation; muốn test phần đó cần integration test phù hợp.
- Test owner và tenant kiểm tra policy nghiệp vụ. Test owner thiếu authority chứng minh rằng owner-only không tự động thay thế permission.
- Trong production còn cần test lỗi repository, quyền chia sẻ, ranh giới transaction, policy cache và các case không tồn tại.

Đoạn test trên là code mẫu để người học chạy bằng Maven; kết quả "pass" chỉ được kỳ vọng khi cấu hình/môi trường khớp. Hãy chạy test thực tế trong dự án của bạn trước khi coi demo đã được xác nhận.

## 10. Vì sao một lời gọi trực tiếp vẫn bị chặn?

Với bean được inject:

~~~java
@Service
public class ExportService {
    private final DocumentService documents;

    public ExportService(DocumentService documents) {
        this.documents = documents;
    }

    public String exportOne(long id) {
        return documents.read(id);
    }
}
~~~

Đây là fragment minh họa, chưa nằm trong ứng dụng demo. `ExportService` gọi `DocumentService` thông qua reference mà Spring cấp cho nó, thường là proxy có advisor bảo mật. Nếu principal hiện tại không đủ quyền, `documents.read(id)` bị từ chối trước khi chạy body. Điều này giúp business policy được áp lại khi service dùng cho exporter, job hoặc consumer.

Tuy nhiên, **method security không tự tạo danh tính cho job**. Một scheduled job chạy ngoài HTTP thường không có `Authentication` người dùng. Nếu đó là job có quyền hệ thống, cần định nghĩa system principal/authority tách biệt, xác nhận nguồn thực thi và phạm vi tài nguyên của nó; hoặc gọi một nghiệp vụ chuyên dành cho system process được bảo vệ bằng ranh giới khác. Đừng gắn `ROLE_ADMIN` ngầm cho mọi background thread hay bỏ annotation chỉ để tránh lỗi.

### AccessDeniedException ngoài HTTP

Khi exception được ném trong HTTP security filter chain, `ExceptionTranslationFilter` có thể chuyển thành 401/403 phù hợp. Nhưng khi một job gọi service trực tiếp, không có HTTP response để chuyển. Caller phải xử lý `AccessDeniedException` theo ngữ cảnh: dừng job của user, trả lỗi tới message handling, ghi audit và quyết định retry hay dead-letter. Việc nuốt exception rồi tiếp tục mutation sẽ làm mất ý nghĩa kiểm soát quyền.

## 11. Giới hạn của Spring AOP proxy: self-invocation

Xét class sau:

~~~java
@Service
class DangerousDocumentService {

    public String wrapper(long id) {
        return this.securedRead(id);
    }

    @PreAuthorize("hasAuthority('DOCUMENT_READ')")
    public String securedRead(long id) {
        return "data";
    }
}
~~~

Đây là **mã minh họa**, không thuộc project demo. Trong cấu hình Spring AOP proxy thông thường, lời gọi `this.securedRead(id)` xảy ra **bên trong cùng đối tượng**, không đi qua proxy, vì vậy interceptor method security có thể không được gọi. Một lời gọi tới `securedRead(...)` từ bean khác qua Spring proxy lại được kiểm tra.

Giải pháp có thể áp dụng:

1. Tách method cần bảo vệ ra một service bean riêng; các caller inject bean đó và gọi qua proxy.
2. Đặt policy trực tiếp trong domain service ở điểm mutation nếu đây là invariant bắt buộc bất kể cơ chế AOP.
3. Với trường hợp đặc biệt, đánh giá AspectJ weaving theo tài liệu Spring Security, đi kèm chi phí cấu hình/test lớn hơn.

Đừng dựa vào `AopContext.currentProxy()` như cách chữa mặc định: nó ràng buộc business code với AOP và dễ gây khó bảo trì. Hãy tổ chức code để boundary bảo mật rõ ràng.

Các vấn đề proxy khác cần nhớ: class/method `final` trong một số kiểu proxy, method không thể proxy, object tự tạo bằng `new`, callback tách rời khỏi Spring, và sự khác biệt giữa interface proxy với class proxy. Kiểm thử đường gọi **thực tế**, không chỉ đọc annotation rồi giả định chắc chắn được áp.

## 12. Transaction, concurrency và dữ liệu thay đổi giữa lúc kiểm tra

Trong demo, `DocumentPolicy.canRead` tra tài liệu trước và `DocumentService.read` tra lại sau. Vì dữ liệu bất biến trong memory nên kết quả ổn định. Trong production có thể có khoảng thời gian giữa kiểm tra và sử dụng (TOCTOU — *time of check to time of use*).

Ví dụ:

~~~text
T1: policy đọc document 101 -> owner=alice, status=DRAFT
T2: admin chuyển document sang tenant khác hoặc khóa tài liệu
T3: service vẫn sửa document 101 dựa trên kết quả T1
~~~

Để giảm rủi ro:

- Thực hiện kiểm tra và mutation trong một transaction phù hợp, xét isolation/locking/versioning tùy tính nhất quán nghiệp vụ yêu cầu.
- Với write nhạy cảm, kết hợp điều kiện quyền với SQL update, ví dụ `UPDATE ... WHERE id=? AND tenant_id=? AND owner_id=? AND status='DRAFT'`, rồi kiểm tra row count. Đây là **mẫu SQL minh họa**, không thay thế transaction design.
- Tránh fetch tài liệu rộng rồi lọc trong memory; query scoped `WHERE tenant_id = :tenant AND owner_id = :owner` thường an toàn và hiệu quả hơn khi có index phù hợp.
- Nếu quyền có thể bị thu hồi ngay lập tức, xem xét token TTL, cache invalidation, policy version và concurrency semantics.
- Phân biệt "không đủ quyền" với "DB lỗi": lỗi hệ thống nên fail closed về dữ liệu nhưng không nhất thiết giả dạng 403; có thể trả lỗi dịch vụ 5xx để vận hành theo dõi.

`@Transactional` và `@PreAuthorize` đều có thể dựa trên Spring AOP. Thứ tự advice và transaction boundary có thể ảnh hưởng thời điểm đọc trạng thái. Hãy kiểm tra trường hợp dữ liệu thay đổi và đừng mặc định authorization query luôn chạy trong cùng transaction với mutation. Điều này cần được thiết kế, không có annotation đơn lẻ nào tự giải quyết hoàn toàn.

## 13. Quyền của service không chỉ là role

Một policy có thể được diễn đạt:

~~~text
subject  = (principalId, tenant, permissions, accountState)
action   = read | update | approve | delete
resource = (resourceId, owner, tenant, classification, status)
context  = (time, risk, MFA assurance, delegation, policyVersion)
decision = grant | deny
~~~

Các kiểu kiểm soát thường kết hợp:

- **RBAC:** `ROLE_MANAGER` có quyền approve invoice trong phạm vi đã chỉ định.
- **ABAC:** approval bị giới hạn theo số tiền, trạng thái, tenant và approval limit của người dùng.
- **ReBAC:** user là owner, collaborator hoặc được chia sẻ tài nguyên.
- **Permission-based:** một nhóm authority như `DOCUMENT_READ`, `DOCUMENT_UPDATE` giúp rule diễn đạt đúng hành động.

Ví dụ tên role `ADMIN` nên có nghĩa được định nghĩa rõ, đặc biệt trong multi-tenant. Không dùng `hasRole("ADMIN")` như wildcard nếu admin tenant A không được can thiệp tenant B. Mô hình "system admin vượt tenant" cần permission riêng, audit trail và quy trình cấp quyền chặt chẽ.

### Nơi đặt policy

Với policy ngắn, `@PreAuthorize("hasAuthority('DOCUMENT_READ')")` là dễ đọc. Với logic owner/tenant/approval phức tạp, dùng một bean như `DocumentPolicy` và gọi từ expression. Nếu logic được chia sẻ ngoài Spring, có thể trích thành domain-level service thuần Java nhận `PrincipalContext` và resource để kiểm thử độc lập; adapter tại `@PreAuthorize` chỉ chuyển ngữ cảnh vào policy. Cách này tránh đặt toàn bộ business logic vào chuỗi SpEL dài.

## 14. Các đường thực thi ngoài HTTP cần thiết kế identity riêng

| Entry point | Có tự chạy qua HTTP filter không? | Cần chú ý |
| --- | --- | --- |
| REST controller | Có, nếu request match một `SecurityFilterChain` | HTTP rule + service rule |
| GraphQL resolver trên HTTP | Request HTTP có thể được kiểm tra, nhưng các field/operation cần policy riêng | Resolver/service rule |
| Scheduled job | Không | System identity hoặc policy chuyên biệt |
| Message listener | Không | Validate producer, context, consumer authorization, service rule |
| Command-line runner | Không | Operator/system principal và quyền thực thi |
| Internal service bean | Không | Gọi qua proxy và truyền ngữ cảnh phù hợp |
| Async task | Không có HTTP filter cho từng callback | Security context propagation |
| WebFlux handler | Có reactive filter chain của WebFlux | Reactive method/security context riêng |

**SecurityContextHolder không tự theo bạn sang mọi thread mới.** Trên Servlet stack, strategy mặc định thường dựa trên `ThreadLocal`. Code `@Async`/`CompletableFuture`/executor có thể mất hoặc vô tình sử dụng sai context nếu tự xử lý. Khi cần truyền identity, dùng cơ chế concurrency integration của Spring Security (chẳng hạn các wrapper `DelegatingSecurityContext...` phù hợp) và kiểm thử luồng cancellation/reuse thread. Không sao chép raw credentials/token vào nhiều thread mà không hiểu vòng đời và phạm vi.

Với WebFlux, dùng `@EnableReactiveMethodSecurity`, `SecurityWebFilterChain` và `ReactiveSecurityContextHolder`; các method thường trả reactive types như `Mono`/`Flux`. Không chuyển nguyên code dùng `SecurityContextHolder`/Servlet `HttpSecurity` sang reactive stack và kỳ vọng context vẫn chính xác. Reactive authorization có mô hình bất đồng bộ riêng và không nên chặn event loop bằng policy database client đồng bộ.

## 15. Phản biện thường gặp

### “Đã có Spring Security ở gateway, sao service phải kiểm tra?”

Gateway có thể xác thực token và chặn nhóm URL, nhưng nó thường không biết trạng thái từng bản ghi hay quyền sở hữu cụ thể. Nội bộ còn có thể có job, event, API được route lại hoặc một hệ thống khác gọi trực tiếp service. Backend phải xác định principal từ nguồn đáng tin và áp policy đối với tài nguyên của chính nó. Không biến một HTTP header tự khai thành danh tính chỉ vì request đến từ mạng nội bộ.

### “Mọi controller đều gọi service này, có cần thêm annotation không?”

Nếu tất cả đường gọi hiện tại đều được bảo vệ đúng, hệ thống **có thể** đang an toàn ở phạm vi đó. Nhưng annotation tại service là điểm chốt được kiểm thử trực tiếp và chống hồi quy khi route/caller thay đổi. Với hành động nhạy cảm, đặt policy gần nghiệp vụ thường giảm phụ thuộc vào quy ước giữa các controller. Quan trọng hơn: annotation phải thực sự hoạt động qua proxy và policy phải xét đúng resource.

### “Cho phép URL rồi service deny có lãng phí không?”

Lớp HTTP kiểm tra coarse-grained permission rẻ và từ chối sớm; service tra business state ở nơi có đủ dữ liệu. Hai lớp có thể có một số kiểm tra lặp, nhưng cần giữ policy đồng bộ. Không nhân đôi tất cả rule thành hai phiên bản độc lập khó bảo trì: dùng chung policy component hoặc permission mapping được quản lý có chủ đích.

### “Có thể dùng @PostAuthorize để kiểm tra owner trả về?”

Có thể dùng cho **một số phương thức chỉ đọc** nếu kết quả cần được kiểm tra sau khi tải. Nhưng dữ liệu đã được lấy vào memory và method có thể có side effect trước khi bị từ chối. Với sửa/xóa/duyệt, ưu tiên `@PreAuthorize` và/hoặc query ràng buộc theo owner/tenant trước mutation. Với danh sách lớn, lọc tại repository thay vì `@PostFilter` toàn bộ kết quả.

### “Method security có chặn mọi lời gọi Java không?”

Không. Theo cơ chế proxy thông dụng, nó chặn các method invocation đi qua Spring AOP proxy phù hợp. Self-invocation, object không do Spring quản lý hoặc calls ngoài phạm vi interception có thể bypass. Vì vậy policy quan trọng có thể cần điều kiện ràng buộc tại repository/database và kiểm thử integration cho đường gọi.

### “Khi không có người dùng đăng nhập, job có thể tự tạo Authentication không?”

Không nên tự gán quyền rộng tùy tiện. Nếu job có vai trò nghiệp vụ hợp lệ, định nghĩa system principal/authority, xác nhận người/cấu phần được phép kích hoạt job và log audit. Nếu cần thao tác không thuộc quyền người dùng, tách thành system operation có trust boundary riêng thay vì giả mạo người dùng thật.

## 16. Danh sách lỗi thường gặp

| Lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ bảo vệ URL, để service đọc mọi ID | IDOR/BOLA qua caller khác hoặc route mới | Service/resource authorization và query scoping |
| Bỏ quên `@EnableMethodSecurity` | Annotation không thực thi như mong muốn | Bật cấu hình và có service-level tests |
| Chỉ dùng `hasAuthority`, không xét owner/tenant | User có quyền tổng quát đọc dữ liệu người khác | Dùng business policy từ dữ liệu tin cậy |
| Tin tenant do client gửi | Cross-tenant access | Dùng identity/tenant server-validated |
| `this.securedMethod()` từ cùng bean | Có thể bypass Spring proxy | Tách bean boundary hoặc explicit check |
| Tạo service thủ công bằng `new` | Không qua Spring-managed proxy | Inject bean do Spring quản lý |
| Dùng `@PostAuthorize` sau mutation | Quyết định trễ, side effect đã xảy ra | Pre-authorization + transactional constraints |
| Nuốt `AccessDeniedException` rồi tiếp tục | Làm vô hiệu hóa enforcement | Dừng thao tác, xử lý theo context |
| Cấp `ROLE_ADMIN` cho mọi background job | Vượt quyền phạm vi lớn | System identity/permission riêng |
| Dùng `SecurityContextHolder` như biến global bất biến | Sai identity trên async/thread switch | Propagate context đúng mechanism |
| Gộp permission và role prefix tùy tiện | Policy match sai | Chuẩn hóa authorities và test |
| Fetch tất cả rows rồi lọc ở Java | Dễ lộ data, tốn RAM | Scope tại query/repository |
| Không test gọi service trực tiếp | Chỉ test URL, bỏ sót proxy/policy | Unit/integration service boundary |
| Không xét transaction/concurrent writes | TOCTOU giữa kiểm tra và sử dụng | Transaction/locking/conditional update |
| Coi 403 và 404 như nhau ở mọi nơi | Lộ hoặc giấu nhầm resource existence | Thiết kế error contract có chủ đích |
| Tắt CSRF để tránh 403 của POST | Có thể mở vấn đề CSRF | Phân biệt CSRF vs authorization và sửa đúng |

## 17. Quy trình thiết kế bảo vệ một service thực tế

1. **Liệt kê entry points:** HTTP routes, jobs, message consumers, internal callers, APIs mới; đừng giả định chỉ có một controller.
2. **Xác định action và resource:** `readDocument`, `approveInvoice`, `deleteCustomer`; method arguments có đủ thông tin xác định resource ID không?
3. **Định nghĩa policy:** principal, permissions, owner/tenant, trạng thái, delegation, default deny và lỗi phụ thuộc.
4. **Cấu hình HTTP:** chỉ permit public thật sự; rule request method/path rõ, thứ tự matcher đúng, catch-all `denyAll` hoặc chính sách xác thực rõ.
5. **Cấu hình method security:** `@EnableMethodSecurity`, annotation tại service public method đi qua Spring proxy, custom policy bean cho logic phức tạp.
6. **Ràng buộc data access:** query theo tenant/owner, phân loại 403/404, transaction/locking nếu mutation.
7. **Kiểm thử:** authenticated/anonymous, permission đúng/sai, owner/other, same/cross tenant, resource missing, alternate callers và direct service invocation.
8. **Quan sát khi chạy:** log authorization denial có kiểm soát, metrics lỗi, security events phù hợp; không log password hoặc token.
9. **Review khi thay đổi:** endpoint mới, event consumer mới, thay role mapping, chuyển proxy/async/transaction, schema tenancy.

Một service có nhiều đường gọi đặc biệt cần test "quyết định vẫn đúng khi **không có HTTP request**". Đây là phép thử trực tiếp cho luận điểm chính của bài học.

## 18. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Giải thích bằng một câu.** Vì sao `.requestMatchers("/api/orders/**").hasAuthority("ORDER_READ")` không bảo vệ `OrderService.findById(...)` khi một message consumer gọi method?

**Bài 2 — Phát hiện BOLA.** Cả Alice và Bob đều có `ORDER_READ`. `findById(101)` đọc bất kỳ order ID nào. Hãy viết rule dựa trên `tenantId` và `ownerId` đáng tin cậy. Nếu chỉ kiểm tra `user.tenantId == order.tenantId`, còn tình huống lộ dữ liệu nào?

**Bài 3 — Tìm lỗi proxy.** Một method `run()` trong `DocumentService` gọi `this.delete(id)`, còn `delete` có `@PreAuthorize("hasAuthority('DOCUMENT_DELETE')")`. Tại sao có nguy cơ bypass? Hãy thay thiết kế bằng một service bean khác gọi qua proxy và viết test chứng minh người thiếu quyền bị chặn.

**Bài 4 — Direct-call test.** Trong demo, thêm một test với `@WithMockUser(username="carol", authorities="DOCUMENT_READ")` gọi `service.read(102)` trực tiếp. Kết quả đúng là gì? Vì sao ngay cả khi HTTP filter không chạy, cuộc gọi vẫn bị từ chối?

**Bài 5 — Lớp transaction.** Một user có quyền sửa bản ghi trong trạng thái `DRAFT`, nhưng record đổi thành `LOCKED` sau check. Nêu cách dùng conditional update hoặc optimistic locking để bảo đảm update không xảy ra khi state không còn hợp lệ.

**Bài 6 — Background job.** Job xuất báo cáo cần gọi service đang có `@PreAuthorize`. Bạn sẽ thiết kế system principal như thế nào để job có đúng một quyền `REPORT_EXPORT` trong tenant được phép, không dùng quyền admin tổng quát?

**Bài 7 — API scope.** Nếu frontend ẩn nút xóa cho người dùng thiếu `DOCUMENT_DELETE`, backend có thể bỏ check service không? Vì sao?

**Gợi ý trả lời:**

- Bài 1: consumer gọi Java method không qua HTTP filter; cần enforce policy tại service/domain boundary.
- Bài 2: same tenant chưa đủ nếu yêu cầu owner/collaborator; dùng dữ liệu resource thật và policy cụ thể.
- Bài 3: self-invocation không qua proxy trong Spring AOP thông dụng; gọi qua bean proxy hoặc explicit domain check.
- Bài 4: `AccessDeniedException`; policy so khớp tenant và owner của bản ghi với principal.
- Bài 5: transaction và `WHERE id = ... AND status = 'DRAFT' AND tenant_id = ...` kết hợp version/row count phù hợp.
- Bài 6: system principal có scope theo tenant, permission tối thiểu, audit caller; không tự cấp ROLE_ADMIN.
- Bài 7: không; client có thể tự gửi HTTP request và nhiều caller không đi qua UI.

## 19. Tổng kết và tài liệu chính thức

Quy tắc HTTP biết **request nào** đang đi vào ứng dụng; service biết **nghiệp vụ nào** đang thực thi và **tài nguyên nào** đang được xử lý. Đặt authorization ở service giúp mọi caller hợp lệ đi qua một policy rõ ràng và có thể kiểm thử, trong khi HTTP filter tiếp tục làm nhiệm vụ bảo vệ sớm tại ingress.

Để bảo vệ đúng thực tế, cần đồng thời nắm bốn điều kiện: **đúng danh tính**, **đúng permission**, **đúng tài nguyên/tenant/owner**, và **đúng điểm thực thi thông qua proxy hoặc domain boundary**. `@PreAuthorize` là công cụ mạnh nhưng không thay thế data-level constraints, transaction design hay việc test các đường gọi thực tế.

Nguồn tham khảo:

- [Spring Security – Method Security, Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security – Method Security (current)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security – Test Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Framework – AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Boot 3.5.7 – Official Release Announcement](https://spring.io/blog/2025/10/23/spring-boot-3-5-7-available-now)
