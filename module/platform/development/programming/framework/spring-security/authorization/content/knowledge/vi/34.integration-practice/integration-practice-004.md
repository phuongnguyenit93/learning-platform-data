# Kiểm tra chủ sở hữu bằng @PreAuthorize kết hợp bean chính sách

## 1. Bài toán thực tế và mục tiêu

Một ứng dụng Spring Security có endpoint **GET /api/documents/{id}** và **PATCH /api/documents/{id}/title**. Hai người dùng đều đã đăng nhập, nhưng Alice chỉ được đọc và sửa tài liệu của Alice; Bob chỉ được đọc và sửa tài liệu của Bob. Với ứng dụng đa tenant, ngay cả hai tài khoản có cùng vai trò cũng không được truy cập chéo tenant.

Chỉ dùng **authenticated()** trong HTTP security không đủ: điều kiện ấy trả lời câu hỏi “người gọi đã đăng nhập chưa?”, không trả lời “người này có phải **chủ sở hữu của tài liệu mang ID này** không?”. Tương tự, **hasRole('USER')** không phân biệt Alice và Bob vì họ có cùng role.

Ta sẽ đặt rào chặn tại service:

~~~java
@PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
public DocumentView read(long documentId) {
    // Chỉ chạy khi bean chính sách đã cho phép.
}
~~~

Ở đây **@PreAuthorize** là cơ chế chặn trước method invocation; **@documentPolicy** là một Spring bean chuyên kiểm quyền, nhận **Authentication** đã xác thực và **ID tài liệu** để tra thông tin owner/tenant từ dữ liệu server. Nếu chính sách trả **false**, Spring Security từ chối trước khi thân phương thức chạy.

Kết quả cần đạt:

- Alice đọc/sửa tài liệu 101 thuộc Alice: **ALLOW**.
- Alice đọc/sửa tài liệu 102 thuộc Bob, dù cùng tenant: **DENY**.
- Carol từ tenant B đọc tài liệu 101 của tenant A: **DENY**.
- Một request chưa xác thực: bị chặn ở tầng HTTP authentication.
- Không có tài liệu: chính sách **fail closed**, không xác nhận quyền sở hữu chỉ vì ID được gửi lên.
- Các phương thức nhạy cảm được gọi qua Spring-managed proxy; kiểm thử cả đường HTTP lẫn service để tránh bypass.

Bài thực hành sử dụng **Java 17+**, **Spring Boot 3.3.x**, **Spring Security 6.x** và **MockMvc**. Dữ liệu/credential minh họa chỉ dùng cho local hoặc test, không sao chép nguyên sang production.

## 2. Mô hình đe dọa: IDOR/BOLA dù đã đăng nhập

Ví dụ dữ liệu trong ứng dụng:

| Document ID | Tenant | Owner ID | Tiêu đề ban đầu |
| --- | --- | --- | --- |
| 101 | tenant-a | alice | Alpha |
| 102 | tenant-a | bob | Beta |
| 201 | tenant-b | carol | Gamma |

Danh tính đã đăng nhập lấy từ **SecurityContext**, không lấy từ request body. Kịch bản lỗi thường gặp:

~~~text
Alice đăng nhập
      |
      v
GET /api/documents/102
      |
      v
Controller gọi repository.findById(102)
      |
      v
Trả tài liệu của Bob vì chỉ kiểm authenticated()
~~~

Đây là dạng **IDOR (Insecure Direct Object Reference)** hay **BOLA (Broken Object Level Authorization)**: người dùng thay ID tài nguyên để truy cập đối tượng không thuộc quyền của mình.

Không thể chữa lỗi chỉ bằng cách che hoặc làm ID khó đoán, dùng UUID, ẩn nút bấm trên giao diện hay giới hạn vai trò chung **ROLE_USER**. Một ID khó đoán vẫn có thể lộ qua log, link chia sẻ hoặc API; quyết định authorization phải đánh giá từ **người gọi và tài nguyên cụ thể**.

### 2.1. Quy tắc owner-only của bài

Quy tắc minh họa:

~~~text
ALLOW nếu và chỉ nếu:
  - người gọi đã xác thực hợp lệ;
  - tài khoản được server nhận diện và còn thuộc phạm vi cho phép;
  - tài liệu tồn tại trong dữ liệu tin cậy;
  - tenant của tài khoản bằng tenant của tài liệu;
  - ID chủ sở hữu của tài liệu bằng ID người gọi.
Ngược lại: DENY.
~~~

Không có ngoại lệ ADMIN trong chính sách này. Nếu bài toán thực tế cho quản trị viên tenant, người được chia sẻ hoặc người được ủy quyền truy cập, cần **định nghĩa và kiểm thử rule bổ sung một cách tường minh**, không ngầm coi role mạnh là vượt mọi tenant.

Chú ý **user ID** nên là định danh ổn định trong hệ thống danh tính, không nhất thiết là username hiển thị. Demo dùng username **alice/bob/carol** làm khóa account để dễ quan sát; production nên lấy subject ID/tenant đã được xác minh từ IdP hoặc account directory của server.

## 3. @PreAuthorize và policy bean phối hợp như thế nào?

Method security của Spring Security phải được bật bằng **@EnableMethodSecurity** trong application context. Với Spring Security 6, chỉ thêm dependency spring-boot-starter-security **không tự bật** kiểm quyền trên phương thức.

Khi một bean khác gọi **DocumentService.read(101)** thông qua Spring AOP proxy:

~~~mermaid
flowchart TD
    A["HTTP request + Authentication"] --> B["Controller nhận documentId"]
    B --> C["Spring proxy của DocumentService"]
    C --> D["@PreAuthorize gọi bean documentPolicy"]
    D --> E["Đọc principal/account tin cậy"]
    E --> F["Đọc tenant và owner từ DocumentStore"]
    F --> G{"Cùng tenant và đúng owner?"}
    G -->|Không| H["AccessDeniedException / HTTP 403"]
    G -->|Có| I["Thực thi DocumentService.read hoặc rename"]
    I --> J["Trả DTO hoặc cập nhật tài liệu"]
~~~

Một expression như sau:

~~~java
@PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
~~~

được hiểu theo các phần:

| Cú pháp | Ý nghĩa |
| --- | --- |
| **@PreAuthorize** | Spring Security đánh giá điều kiện **trước khi chạy thân method** |
| **@documentPolicy** | Tìm bean Spring tên **documentPolicy** từ application context |
| **isOwner(...)** | Gọi phương thức public của bean để áp dụng chính sách nghiệp vụ |
| **authentication** | Đối tượng **Authentication** đang có trong security context |
| **#p0** | Đối số thứ nhất của phương thức đang được bảo vệ, ở đây là documentId |
| Giá trị boolean | **true** cho phép, **false** từ chối |

**#p0** hữu ích khi tên tham số không được giữ lại lúc biên dịch. Có thể dùng **#documentId** nếu cấu hình Java compiler giữ tên tham số bằng **-parameters**, hoặc dùng annotation **@P** của Spring Security; nhưng đừng giả định tên tham số luôn khả dụng ở mọi project. Trong ví dụ, **#p0** tránh sự phụ thuộc ấy.

**Vì sao đặt logic ở bean riêng?** Expression ngắn, dễ đọc và tái sử dụng; policy được test độc lập; service chỉ giữ nghiệp vụ. Đồng thời, code lấy account/tenant/owner từ nguồn dữ liệu tin cậy thay vì tin một giá trị **ownerId** do client gửi tới.

## 4. Project Java 17+ đầy đủ có thể chạy

Demo chạy local không dùng database để tránh phụ thuộc ngoài bài học. **AccountDirectory** mô phỏng nguồn danh tính/tenant, **DocumentStore** mô phỏng bảng tài liệu. Trong hệ thống thật, hai nguồn này phải đến từ dữ liệu đã được xác minh và được bảo vệ thích hợp.

Cấu trúc thư mục:

~~~text
owner-policy-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/ownership/
    │   ├── OwnerPolicyApplication.java
    │   ├── SecurityConfig.java
    │   ├── AccountDirectory.java
    │   ├── DocumentStore.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/example/ownership/
        └── OwnershipAuthorizationTest.java
~~~

### 4.1. Khai báo Gradle

**settings.gradle**

~~~groovy
rootProject.name = 'owner-policy-demo'
~~~

**build.gradle**

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
    implementation 'org.springframework.boot:spring-boot-starter-aop'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các dependency gồm Spring MVC cho controller REST, Spring Security cho filter và **@PreAuthorize**, Spring AOP cho proxy, spring-security-test cho **MockMvc**, HTTP Basic và **@WithMockUser**. Khi làm việc với một project thực tế, dùng dependency management và version đang được tổ chức hỗ trợ; version trên chỉ dành cho ví dụ tương thích Spring Boot 3.3.x.

### 4.2. Bật method security trong context

**src/main/java/example/ownership/OwnerPolicyApplication.java**

~~~java
package example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class OwnerPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnerPolicyApplication.class, args);
    }
}
~~~

Điểm phải nhớ: **@EnableMethodSecurity** phải có hiệu lực trong context chứa **DocumentService**; gắn annotation trong một configuration không được Spring scan/import sẽ không bảo vệ service. Cấu hình mặc định bật hỗ trợ **@PreAuthorize**. Không đặt **prePostEnabled = false** khi ứng dụng đang dựa vào annotation này.

### 4.3. Cấu hình HTTP security và danh tính test

**src/main/java/example/ownership/SecurityConfig.java**

~~~java
package example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/documents/**")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-pass")
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password("{noop}demo-pass")
                        .roles("USER")
                        .build(),
                User.withUsername("carol")
                        .password("{noop}demo-pass")
                        .roles("USER")
                        .build()
        );
    }
}
~~~

**Tại sao HTTP chỉ authenticated()?** Đó là dụng ý kiểm thử: Alice, Bob và Carol đều có **ROLE_USER**, nên tầng HTTP chỉ xác nhận đã đăng nhập; **DocumentPolicy** phải thực sự chặn truy cập chéo owner/tenant. Nếu đặt rule chặn mọi USER ở HTTP, một method policy bị lỗi vẫn có thể bị che khuất trong test.

**Không dùng mật khẩu {noop} ở production.** InMemoryUserDetailsManager và mật khẩu minh họa chỉ dùng cho môi trường local. Production cần PasswordEncoder an toàn, hệ thống danh tính phù hợp, truyền tải TLS và quản lý secrets. CSRF mặc định vẫn bật trong demo; request PATCH cần token CSRF hợp lệ.

### 4.4. AccountDirectory: ánh xạ principal tới user ID và tenant tin cậy

**src/main/java/example/ownership/AccountDirectory.java**

~~~java
package example.ownership;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class AccountDirectory {
    public record Account(String id, String tenantId) {
    }

    private final Map<String, Account> accounts = Map.of(
            "alice", new Account("alice", "tenant-a"),
            "bob", new Account("bob", "tenant-a"),
            "carol", new Account("carol", "tenant-b")
    );

    public Optional<Account> findByLogin(String login) {
        return Optional.ofNullable(accounts.get(login));
    }
}
~~~

Ví dụ dùng **authentication.getName()** làm login để tra account trong một nguồn do **server** quản lý. Trong production, login có thể thay đổi và có thể trùng trong những realm khác nhau; hãy ưu tiên ID bất biến/issuer/tenant được xác thực. Nếu tenant được chọn khi đăng nhập, server phải xác nhận user có membership trong tenant ấy trước khi gán security context. **Không lấy tenantId từ JSON body rồi coi như quyền đã được xác minh.**

### 4.5. DocumentStore: dữ liệu owner và tenant do server lưu

**src/main/java/example/ownership/DocumentStore.java**

~~~java
package example.ownership;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

@Repository
public class DocumentStore {
    public record Document(
            long id, String tenantId, String ownerId, String title) {
    }

    private final Map<Long, Document> documents =
            new ConcurrentHashMap<>();

    public DocumentStore() {
        reset();
    }

    public Optional<Document> find(long id) {
        return Optional.ofNullable(documents.get(id));
    }

    public Document rename(long id, String newTitle) {
        Document result = documents.computeIfPresent(id, (key, old) ->
                new Document(
                        old.id(), old.tenantId(), old.ownerId(), newTitle
                )
        );
        if (result == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return result;
    }

    public void reset() {
        documents.clear();
        documents.putAll(Map.of(
                101L, new Document(
                        101, "tenant-a", "alice", "Alpha"),
                102L, new Document(
                        102, "tenant-a", "bob", "Beta"),
                201L, new Document(
                        201, "tenant-b", "carol", "Gamma")
        ));
    }
}
~~~

**Map<Long, Document>** phù hợp với ví dụ vì ID là duy nhất toàn ứng dụng. Nếu ID chỉ duy nhất **trong từng tenant**, không được tìm tài liệu bằng ID trần rồi suy luận tenant từ request; dùng khóa kép **(tenantId, documentId)** từ tenant đã được xác minh. Với database thật, nên có index/phạm vi truy vấn phù hợp và ràng buộc tenant tại tầng dữ liệu.

Phương thức **rename** không có kiểm quyền vì nó biểu diễn thao tác lưu trữ nội bộ. Mọi entry point công khai phải đi qua tầng service được bảo vệ; trong hệ thống lớn, có thể bổ sung ràng buộc owner/tenant ngay trong câu SQL UPDATE để phòng race và tránh các đường cập nhật vượt qua service. Không expose thẳng DocumentStore thành controller.

### 4.6. DocumentPolicy: bean chính sách kiểm tra quyền sở hữu

**src/main/java/example/ownership/DocumentPolicy.java**

~~~java
package example.ownership;

import java.util.Optional;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final AccountDirectory accounts;
    private final DocumentStore documents;

    public DocumentPolicy(AccountDirectory accounts,
                          DocumentStore documents) {
        this.accounts = accounts;
        this.documents = documents;
    }

    public boolean isOwner(Authentication authentication, long documentId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        Optional<AccountDirectory.Account> account =
                accounts.findByLogin(authentication.getName());

        if (account.isEmpty()) {
            return false;
        }

        return documents.find(documentId)
                .map(document ->
                        document.tenantId().equals(
                                account.get().tenantId())
                        && document.ownerId().equals(
                                account.get().id()))
                .orElse(false);
    }
}
~~~

Những quyết định quan trọng của implementation:

1. **Fail closed:** auth null/anonymous, account không nhận diện được, tài liệu không tồn tại đều cho **false**.
2. **Không tin ID owner được client cung cấp:** ownerId/tenantId được đọc từ DocumentStore.
3. **Kiểm cả tenant lẫn owner:** tránh nhầm owner có ID/username giống nhau ở nhiều tenant, hoặc dùng một tài khoản có role đúng nhưng ở tenant khác.
4. **So sánh ID ổn định bằng equals:** không so sánh tên hiển thị hay object reference.
5. **Policy chỉ trả boolean:** không trả trực tiếp toàn bộ Document sang SpEL, log hoặc response. Điều này giảm nguy cơ lộ nội dung trước khi cho phép.

Nếu ứng dụng hỗ trợ người được chia sẻ, nhóm hoặc admin theo tenant, hãy mở rộng hàm như **canRead / canEdit**, chứ đừng chỉ thêm role global rồi bỏ tenant check. Mỗi rule cần test đầy đủ positive/negative.

### 4.7. DocumentService: gắn @PreAuthorize vào ranh giới nghiệp vụ

**src/main/java/example/ownership/DocumentService.java**

~~~java
package example.ownership;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    public record DocumentView(long id, String title) {
    }

    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
    public DocumentView read(long documentId) {
        return store.find(documentId)
                .map(DocumentService::toView)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
    public DocumentView rename(long documentId, String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        return toView(store.rename(documentId, newTitle));
    }

    private static DocumentView toView(DocumentStore.Document document) {
        return new DocumentView(document.id(), document.title());
    }
}
~~~

**@PreAuthorize** được đặt trên **cả read và rename**. Một method chỉ có quyền READ không tự bảo vệ method ghi; quy tắc nên được áp cho **mọi action nhạy cảm**. Ở đây chủ sở hữu được phép cả hai, nhưng business rule thực tế có thể khác nhau.

**#p0** luôn là tham số thứ nhất **documentId** trong hai method. Nếu về sau đổi thứ tự tham số, expression phải được cập nhật và test. Có thể dùng tên tham số **#documentId** khi được compiler hỗ trợ, nhưng đừng đổi cú pháp mà không kiểm tra. Khi **@PreAuthorize** trả false, thân **rename** chưa được gọi, vì vậy thao tác đổi title chưa xảy ra.

**Không bảo vệ chỉ một private helper rồi tự gọi bằng this:** Spring AOP proxy không chặn được self-invocation thông thường. Class và method service dùng trong ví dụ đều là Spring-managed, public và non-final, được gọi từ controller qua dependency injection.

### 4.8. DocumentController: chỉ nhận ID và dữ liệu cần cập nhật

**src/main/java/example/ownership/DocumentController.java**

~~~java
package example.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    public record RenameRequest(String title) {
    }

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DocumentService.DocumentView get(@PathVariable long id) {
        return service.read(id);
    }

    @PatchMapping("/{id}/title")
    public DocumentService.DocumentView rename(
            @PathVariable long id, @RequestBody RenameRequest request) {
        return service.rename(id, request.title());
    }
}
~~~

Controller **không nhận ownerId/tenantId để quyết định quyền**. Nó chỉ lấy document ID từ path và title mới từ request body; chính sách dùng account/owner/tenant từ nguồn server đáng tin. Nếu client cố bổ sung trường **ownerId** vào JSON, trường ấy không được dùng làm căn cứ authorization trong kiến trúc này.

## 5. Regression tests bằng Spring Security Test và MockMvc

Kiểm thử cả endpoint lẫn direct service invocation. Một test chỉ chạy user có quyền có thể luôn xanh dù annotation không hoạt động; **test từ chối người khác chủ** là điều kiện bắt buộc.

**src/test/java/example/ownership/OwnershipAuthorizationTest.java**

~~~java
package example.ownership;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipAuthorizationTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentStore store;
    @Autowired DocumentService service;

    @BeforeEach
    void restoreFixtures() {
        store.reset();
    }

    @Test
    void methodSecurityIsAppliedThroughProxy() {
        assertTrue(AopUtils.isAopProxy(service));
    }

    @Test
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.title").value("Alpha"));
    }

    @Test
    void otherOwnerInSameTenantIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/102")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void crossTenantAccessIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/101")
                        .with(httpBasic("carol", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanRenameOwnDocument() throws Exception {
        mvc.perform(patch("/api/documents/101/title")
                        .with(httpBasic("alice", "demo-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Updated\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Updated"));

        assertEquals("Updated", store.find(101L).orElseThrow().title());
    }

    @Test
    void nonOwnerCannotRenameOrCauseSideEffect() throws Exception {
        mvc.perform(patch("/api/documents/102/title")
                        .with(httpBasic("alice", "demo-pass"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Stolen\"}"))
                .andExpect(status().isForbidden());

        assertEquals("Beta", store.find(102L).orElseThrow().title());
    }

    @Test
    void anonymousCallerMustAuthenticate() throws Exception {
        mvc.perform(get("/api/documents/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownDocumentFailsClosed() throws Exception {
        mvc.perform(get("/api/documents/999")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void directServiceInvocationStillRejectsNonOwner() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(102L));
        assertEquals(101L, service.read(101L).id());
    }
}
~~~

Chạy trên máy có JDK 17+ và Gradle 8.x tương thích Spring Boot 3.3.x, từ thư mục **owner-policy-demo**:

~~~bash
gradle test
~~~

Nếu project có Gradle wrapper đã được tạo, dùng **./gradlew test** trên Linux/macOS hoặc **gradlew.bat test** trên Windows. Ví dụ ở trên không đính kèm wrapper binaries; vì thế lệnh **gradle test** cần Gradle đã cài. Có thể chạy app:

~~~bash
gradle bootRun
~~~

Sau đó thử local (chỉ khi đang dùng đúng dữ liệu giả lập):

~~~bash
curl -i -u alice:demo-pass http://localhost:8080/api/documents/101
curl -i -u alice:demo-pass http://localhost:8080/api/documents/102
~~~

Kết quả kỳ vọng: request đầu trả **HTTP 200** và JSON chứa **id=101, title=Alpha**; request thứ hai trả **HTTP 403**. **Đây là kết quả kỳ vọng dựa trên mã mẫu, không phải stdout của một lần chạy đã thực hiện.**

### 5.1. Vì sao mỗi test quan trọng?

| Tình huống | Identity/Request | Kỳ vọng | Điều được chứng minh |
| --- | --- | --- | --- |
| Đúng owner | alice → GET 101 | 200 | Người sở hữu vẫn làm được việc hợp lệ |
| Sai owner cùng tenant | alice → GET 102 | 403 | Role giống nhau không cấp quyền đọc lẫn nhau |
| Khác tenant | carol → GET 101 | 403 | Admin/user của tenant khác cũng không được vào |
| Đúng owner cập nhật | alice → PATCH 101 với CSRF | 200, title thay đổi | Cả authorization và nghiệp vụ hợp lệ |
| Sai owner cập nhật | alice → PATCH 102 với CSRF | 403, title giữ nguyên | Chặn **trước side effect** |
| Chưa đăng nhập | anonymous → GET 101 | 401 với HTTP Basic | Authentication được thực thi |
| Không có tài liệu | alice → GET 999 | 403 theo policy fail closed | Không xác nhận quyền cho ID không tồn tại |
| Gọi service trực tiếp | @WithMockUser(alice) → read(102) | AccessDeniedException | Chống việc endpoint test che lỗi method security |
| Service proxy | bean được @Autowired | isAopProxy=true | Hạ tầng interceptor được áp lên service |

**Giải thích HTTP status:** khi người đã đăng nhập bị chặn bởi **@PreAuthorize**, method security phát sinh **AccessDeniedException** trong request flow; Spring Security có thể chuyển thành HTTP **403**. Khi request chưa có authentication hợp lệ và dùng HTTP Basic, thường nhận **401** kèm yêu cầu xác thực. Khi gọi service ngoài HTTP, bạn thấy exception Java thay vì status.

**Vì sao PATCH cần CSRF token trong test?** Spring Security bật bảo vệ CSRF mặc định cho request thay đổi trạng thái. Nếu bỏ **.with(csrf())**, test PATCH có thể vẫn trả 403 nhưng **do CsrfFilter**, chưa chứng minh policy owner đã chạy. Test cung cấp CSRF hợp lệ để xác định chính xác authorization chặn non-owner.

### 5.2. Phản chứng khi cấu hình hỏng

Thử trong một nhánh/working copy test riêng rồi khôi phục:

1. Bỏ **@EnableMethodSecurity** khỏi application class: một user có thể gọi **DocumentService** mà không bị interceptor áp policy. Test **directServiceInvocationStillRejectsNonOwner** phải báo lỗi; test sai owner qua HTTP cũng không còn trả 403 như kỳ vọng.
2. Giữ method security nhưng bỏ **@PreAuthorize** khỏi **rename**: test **nonOwnerCannotRenameOrCauseSideEffect** phải phát hiện khả năng sửa tài liệu không thuộc quyền.
3. Thử đổi policy thành so sánh trực tiếp **documentId** với input ownerId từ request: test liên quan tài liệu khác chủ cần phát hiện lỗ hổng hoặc phải mở rộng fixture để chứng minh client không được tự cấp quyền.
4. Gộp method nhạy cảm vào một service rồi gọi **this.protectedMethod()** bên trong method không được bảo vệ: test direct target có thể khác kết quả so với đường gọi nội bộ. Cần test mọi entry point, hoặc tách logic bảo vệ qua bean được inject.

Chỉ kiểm 200 cho Alice là **không đủ**. Nếu annotation chưa được bật, Alice vẫn đọc được 101, test dương vẫn xanh nhưng Bob có thể đọc tài liệu của Alice.

## 6. Những anti-pattern cần tránh

### 6.1. Tin ownerId do client gửi

**Không an toàn:**

~~~java
// Sai: "ownerId" có thể bị client tự khai.
@PreAuthorize("authentication.name == #p1")
public void update(long documentId, String ownerId) {
    // Không tra owner thực tế của documentId.
}
~~~

Kẻ tấn công chỉ cần truyền ownerId trùng tên mình. **Chính sách đúng phải đọc ownerId từ database/repository tin cậy** theo tài liệu yêu cầu và kiểm tenant tương ứng. Có thể dùng document ID từ client để **tra đối tượng**; không dùng ownerId từ client để **xác định quyền**.

### 6.2. Chỉ kiểm role, không kiểm ownership

~~~java
// Không đủ cho quy tắc "chỉ chủ sở hữu".
@PreAuthorize("hasRole('USER')")
public DocumentView read(long id) {
    // Alice và Bob cùng ROLE_USER.
}
~~~

Role có thể là điều kiện bổ sung, ví dụ **hasAuthority('DOCUMENT_READ') and @documentPolicy.isOwner(authentication, #p0)**. Nhưng role toàn cục **không** thay thế kiểm owner/tenant khi policy yêu cầu.

### 6.3. Chỉ bảo vệ controller hoặc một endpoint

Nếu service không được bảo vệ, một scheduled job, message consumer, GraphQL resolver hoặc controller thứ hai có thể gọi trực tiếp repository. Đặt policy ở **service boundary** phù hợp giúp tái sử dụng, nhưng vẫn phải thống kê mọi đường vào nghiệp vụ.

Ngược lại, **@PreAuthorize** trên service không thay thế SecurityFilterChain cho authentication, CSRF, CORS và những chính sách HTTP khác. Cần kiểm cả hai tầng.

### 6.4. Gọi hàm được bảo vệ qua this

~~~java
@Service
class UnsafeDocumentService {
    public String publicEntry(long id) {
        return this.ownerOnly(id);
    }

    @PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")
    public String ownerOnly(long id) {
        return "sensitive";
    }
}
~~~

Đoạn này chỉ là **minh họa anti-pattern**, không nằm trong các file runnable mục 4. Với proxy-based Spring AOP, **this.ownerOnly(id)** là lời gọi nội bộ trên target, **không đi qua proxy** nên method annotation có thể bị bỏ qua. Sửa bằng cách đưa method nhạy cảm vào một **bean Spring riêng** rồi gọi qua bean được dependency-inject; hoặc chuyển policy sang method entry point thực sự được caller bên ngoài gọi.

Không kỳ vọng **private/final** method có annotation được proxy chặn như method public thông thường. Chỉ có annotation trong source không bảo đảm interceptor thực sự chạy.

### 6.5. Dùng @PostAuthorize thay cho @PreAuthorize khi ghi

**@PostAuthorize** đánh giá sau khi method thực thi; với thao tác ghi, side effect có thể đã xảy ra trước khi quyết định từ chối. Đối với cập nhật/xóa/approve, dùng **@PreAuthorize** hoặc một policy check trước side effect, kết hợp với kiểm tra tại thời điểm commit nếu yêu cầu bảo mật nghiêm ngặt. Với truy vấn đọc, @PostAuthorize đôi khi phù hợp để kiểm đối tượng trả về, nhưng cần thận trọng khi thân method có side effect, log dữ liệu nhạy cảm hoặc lazy loading.

### 6.6. Trả ALLOW khi lookup thất bại

Tránh pattern **catch Exception rồi return true** hoặc “không tìm thấy document thì cho qua”. Nếu không tra được owner, tenant hoặc principal, **không có cơ sở cấp quyền**. Quy định rõ trường hợp dữ liệu không tồn tại, backend lỗi hoặc timeout: chính sách có thể từ chối hoặc trả lỗi hệ thống thích hợp, nhưng không lặng lẽ biến lỗi thành ALLOW.

### 6.7. Bỏ qua tính đa tenant

Nếu resource ID không duy nhất toàn hệ thống, truy vấn **findById(id)** chưa đủ để chọn resource đúng. Khi dùng tenant trong URL hoặc header, phải kiểm tenant đó là tenant người gọi thực sự được phép hoạt động. Trong ứng dụng thực tế, nên xây repository như **findByTenantIdAndId(trustedTenantId, id)** và sau đó vẫn áp chính sách owner/ACL.

## 7. Điểm khó trong production: race, hiệu năng và tính nhất quán

### 7.1. TOCTOU giữa kiểm quyền và cập nhật

Luồng **@PreAuthorize → đọc ACL → gọi method → cập nhật DB** có thể xuất hiện khoảng thời gian giữa **time-of-check** và **time-of-use**. Nếu ownership hoặc tenant membership bị thay đổi giữa hai thời điểm, quyết định trước đó có thể không còn hợp lệ.

Tùy yêu cầu, có thể cần:
- Transaction với mức cô lập hoặc row lock phù hợp.
- Cập nhật có điều kiện, ví dụ SQL logic:

~~~sql
UPDATE documents
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_subject;
~~~

- Kiểm **số hàng cập nhật** để biết thao tác thật sự hợp lệ; không cho client tự cung cấp **trusted_tenant** hay **authenticated_subject** mà chưa xác thực.
- Với ACL chia sẻ, policy version, parent folder hoặc các quan hệ phức tạp, transaction cần bao phủ đúng những dữ kiện authorization liên quan.

SQL trên chỉ là **mẫu ý tưởng** cho database thật, không phải một phần của Java in-memory demo.

### 7.2. Lookup dữ liệu hai lần

Mã demo đọc tài liệu trong **DocumentPolicy**, rồi service đọc lại để trả DTO hoặc update. Trong production, điều này có thể gây chi phí DB và race. Một số chiến lược:
- Dùng truy vấn có điều kiện owner/tenant ở repository để vừa giới hạn phạm vi dữ liệu vừa giảm round-trip.
- Dùng transaction/snapshot nhất quán cho các thông tin policy cần thiết.
- Đưa policy vào một **AuthorizationManager** hoặc service chuyên trách có phân định rõ trách nhiệm.
- Nếu dùng cache kết quả authorization, key phải phân biệt ít nhất các yếu tố policy phụ thuộc: subject, tenant, resource, action và version/revision tương ứng với role/ACL/policy; đồng thời có chiến lược thu hồi quyền đáng tin.

**Không cache kết quả isOwner chỉ theo documentId**, vì ALLOW của Alice có thể bị tái sử dụng cho Bob. Cũng không dùng TTL như bằng chứng rằng quyền vừa thu hồi được thực thi ngay.

### 7.3. Hiển thị 403 hay 404?

Demo chọn **403** cho ID tồn tại nhưng không thuộc quyền và cả ID không tồn tại. Cách này đơn giản, không xác nhận quyền khi không thấy đối tượng, nhưng việc che giấu sự tồn tại cần đánh giá thêm cả timing, message và các endpoint khác.

Nhiều API chọn **404** cho cả “không tồn tại” và “không được phép xem” để giảm lộ thông tin. Có thể thiết kế policy/repository che giấu resource không khả dụng, nhưng phải **nhất quán** trong toàn hệ thống, không lộ thông tin qua body, search, count, cache, thời gian xử lý và audit. Không nhầm “trả 404” với việc đã thực thi authorization đúng.

### 7.4. Quyền READ và EDIT không phải luôn giống nhau

Ví dụ owner-only dùng cùng **isOwner** cho hai action để tập trung bài học. Trong nghiệp vụ thật có thể có:
- Owner được READ và EDIT.
- Collaborator được READ nhưng không EDIT.
- Tenant-admin được xem tài liệu trong tenant nhưng không vượt tenant.
- Tài liệu ở trạng thái khóa không cho EDIT dù owner hợp lệ.

Khi đó dùng **canRead(authentication, id)** và **canEdit(authentication, id)** hoặc truyền **Action** tin cậy do server xác định. Không tự suy ra mọi owner được xóa hoặc approve mọi đối tượng.

### 7.5. Tối ưu audit mà không lộ dữ liệu

Audit các lần từ chối/cho phép có liên quan tới dữ liệu nhạy cảm với các trường phù hợp: request ID, subject ID nội bộ, tenant scope, resource type/ID (theo chuẩn bảo mật tổ chức), action, policy version, outcome. Tránh log access token, session cookie, mật khẩu, toàn bộ ACL hoặc nội dung tài liệu. Phân biệt lý do **unauthenticated**, **non-owner**, **cross-tenant**, **unknown resource** trong log bảo mật có kiểm soát nếu chính sách cho phép, nhưng hạn chế tiết lộ qua response công khai.

## 8. Checklist review và test bổ sung

| Câu hỏi | Kết quả mong đợi |
| --- | --- |
| Đã bật **@EnableMethodSecurity** trong đúng application context chưa? | Có; negative service test vẫn ném AccessDeniedException |
| Service được tạo bởi Spring và gọi qua proxy chưa? | Có; kiểm AopUtils và đường gọi thực tế |
| Bean **documentPolicy** tồn tại, phương thức public đúng signature chưa? | Có; SpEL không lỗi bean/argument |
| Principal ID/tenant được lấy từ đâu? | Nguồn server tin cậy, không từ body tự khai |
| Owner và tenant resource được lấy từ đâu? | DB/repository tin cậy, không từ URL hoặc DTO do client gửi |
| Đã kiểm cả subject tenant và resource tenant chưa? | Có; cross-tenant DENY |
| Owner đúng nhưng action bị cấm có bị chặn không? | Có policy theo từng action thực tế |
| ID không tồn tại hoặc tài khoản không nhận diện được? | Không ALLOW; xử lý fail closed nhất quán |
| Quyền có được áp trước khi ghi hay không? | Có; failed PATCH không có side effect |
| Request PATCH có CSRF hợp lệ để test policy không? | Có; tránh 403 giả từ CSRF |
| Có path/consumer khác gọi trực tiếp repository không? | Không bypass service hoặc có rào quyền riêng tương đương |
| Có xử lý race khi owner/ACL đổi trong lúc request không? | Có biện pháp theo threat model và SLA |
| Test fixture có cả Alice/Bob cùng tenant và Carol khác tenant chưa? | Có, cùng test positive/negative |
| Có đo/tracing policy lookup và xử lý dữ liệu nhạy cảm trong log không? | Có, nhưng không lộ secrets |

### 8.1. Các bài tập mở rộng đúng chủ đề

1. Thêm action **DELETE** nhưng không cho owner xóa tài liệu ở trạng thái **LOCKED**; chuyển từ **isOwner** sang **canDelete** có truy vấn trạng thái đáng tin. Test rằng owner vẫn bị từ chối khi tài liệu locked.
2. Thêm một account **dave** ở tenant-a và một tài liệu 301 của dave; xác minh Alice không thể đọc tài liệu ấy, dù cùng role và cùng tenant.
3. Thêm chủ thể **tenant-admin** có thể READ tài liệu trong tenant của mình nhưng không thể EDIT nếu không phải owner. Không được dùng role ADMIN toàn cục để bỏ qua kiểm tenant.
4. Đổi repository sang Spring Data JPA; thiết kế truy vấn owner/tenant có điều kiện, xử lý transaction/TOCTOU và kiểm số dòng được cập nhật.
5. Dùng **@P("documentId")** trên tham số service thay cho **#p0**, rồi kiểm lại biểu thức bằng test. Bảo đảm method-security parameter discovery nhận đúng tên đã đánh dấu.
6. Thêm kiểm thử **direct bean invocation** từ một consumer giả lập thay cho HTTP để chứng minh rào service dùng lại được.
7. Viết test phản chứng khi tạm bỏ annotation @PreAuthorize: test negative và test trạng thái DB phải FAIL, sau đó khôi phục source.

## 9. Tổng kết

Để kiểm quyền chủ sở hữu trong Spring Security một cách đáng tin, nên kết hợp:

1. **@EnableMethodSecurity** để kích hoạt interceptor cấp phương thức.
2. **@PreAuthorize("@documentPolicy.isOwner(authentication, #p0)")** trên **service method nhạy cảm**, được gọi qua Spring proxy.
3. **Bean chính sách riêng** dùng Authentication và truy vấn owner/tenant từ nguồn dữ liệu **server tin cậy**, trả false khi thiếu căn cứ cho phép.
4. **HTTP authentication + service authorization + data-access constraints** như những lớp bảo vệ bổ trợ.
5. **Kiểm thử ALLOW và DENY** trên cùng tenant, khác tenant, method ghi có side effect, direct service call và trường hợp không tìm thấy tài nguyên.

Điểm mấu chốt không phải chỉ đặt annotation cho đẹp source code, mà là chứng minh mỗi lời gọi thực tế đi qua policy và một user **không thể tự cấp quyền sở hữu bằng cách đổi ID hoặc giả mạo ownerId**.

### Tài liệu chính thức và đọc thêm

- Spring Security 6.5 — Method Security, bean authorization, tham số method: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework — AOP Proxying Mechanisms và self-invocation: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Testing MockMvc Security: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP API Security — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
