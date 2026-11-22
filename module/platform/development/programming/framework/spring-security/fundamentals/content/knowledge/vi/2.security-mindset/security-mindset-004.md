# Nguyên tắc quyền tối thiểu và từ chối khi chưa có quy tắc cho phép

> **Bối cảnh:** Spring Security trên Servlet/Spring MVC, Java 17+ và Spring Boot 3.x. Bài học trả lời hai câu hỏi thiết kế: **mỗi danh tính thực sự cần những quyền nào?** và **ứng dụng phải làm gì với yêu cầu chưa có quy tắc cho phép rõ ràng?**

## 1. Hai nguyên tắc bổ trợ nhau

**Quyền tối thiểu (Principle of Least Privilege, PoLP):** mỗi người dùng, tài khoản dịch vụ, tiến trình và thành phần chỉ nhận những quyền **cần thiết để hoàn thành công việc được giao**, trong phạm vi dữ liệu và thời gian cần thiết. Cấp thêm quyền phải có lý do cụ thể và được kiểm soát.

**Từ chối mặc định (Deny by Default / Default Deny):** một hành động chỉ được thực hiện khi **có quy tắc cho phép áp dụng**. Nếu không có rule phù hợp, thông tin để ra quyết định thiếu hoặc điều kiện chưa được chứng minh, hệ thống **không cấp quyền**. Đây là một biểu hiện của tư duy **fail closed**.

Hai nguyên tắc liên quan nhưng không đồng nhất:

| Tình huống | Quyền tối thiểu đặt câu hỏi | Từ chối mặc định đặt câu hỏi |
| --- | --- | --- |
| Nhân viên chăm sóc khách hàng xem đơn hàng | Có cần xem mọi đơn hàng của mọi tenant không? | Nếu không có rule cho loại đơn hàng mới, request có bị chặn không? |
| Dịch vụ tạo hóa đơn gọi API | Token có cần quyền xóa người dùng không? | Một API mới chưa khai báo policy có mở cho mọi token không? |
| Quản trị viên truy cập tài liệu | Quyền quản trị có thực sự bao gồm đọc tài liệu riêng tư không? | Role ADMIN tự được miễn mọi kiểm tra hay chỉ qua rule có chủ đích? |
| Thêm endpoint khi triển khai tính năng mới | Endpoint nên phục vụ vai trò và hành động nào? | Nếu quên khai báo authorization, endpoint có bị từ chối không? |

**Không xác thực được danh tính** và **đã xác thực nhưng thiếu quyền** đều không đủ điều kiện truy cập, nhưng có thể dẫn đến các phản hồi HTTP khác nhau. Phần sau sẽ giải thích.

## 2. Hãy xác định quyền theo hành động và tài nguyên

Một quyết định truy cập đầy đủ thường cần các thông tin:

- **Subject:** ai đang hành động? Ví dụ **alice**, tài khoản service hoặc một client OAuth2.
- **Action:** định làm gì? Ví dụ **READ**, **CREATE**, **UPDATE**, **DELETE**, **APPROVE**.
- **Resource:** trên đối tượng nào? Ví dụ **document:doc-2**, **order:42**.
- **Context:** tenant, chủ sở hữu, trạng thái đơn, thời gian, môi trường, mức xác thực hoặc đặc điểm liên quan.

Có thể hình dung:

~~~text
ALLOW khi và chỉ khi:
  subject đã thỏa yêu cầu xác thực
  AND có quyền thực hiện action
  AND policy cho resource cụ thể thỏa mãn
  AND các điều kiện context bắt buộc đều thỏa mãn

Ngược lại: không cấp quyền.
~~~

Ví dụ **alice** có quyền **document:read**. Quyền này mới nói rằng alice có thể thực hiện *loại thao tác đọc tài liệu*; chưa chứng minh alice được đọc **doc-2** thuộc **bob**. Nếu API chỉ kiểm tra role chung rồi nhận ID từ URL, người dùng có thể đổi ID để truy cập tài liệu người khác. Đây là dạng lỗi **Broken Object Level Authorization (BOLA/IDOR)**.

Một ma trận quyền tối thiểu đơn giản:

| Danh tính | GET /api/ping | GET /api/docs/doc-1 (của alice) | GET /api/docs/doc-2 (của bob) | GET /api/admin/audit |
| --- | --- | --- | --- | --- |
| Anonymous | Cho phép | Không | Không | Không |
| alice, document:read | Cho phép | Cho phép | Không | Không |
| bob, document:read | Cho phép | Không | Cho phép | Không |
| admin, ROLE_ADMIN | Cho phép | Không, nếu không được cấp quyền đọc tài liệu | Không | Cho phép |

**Quyền ADMIN không mặc nhiên là "mọi thứ".** Nếu nghiệp vụ cần quản trị viên xem tài liệu trong trường hợp hỗ trợ, hãy thiết kế **quyền hỗ trợ riêng**, phạm vi phù hợp và audit; không tự suy ra quyền truy cập dữ liệu nhạy cảm từ tên role.

### 2.1. Role, authority và quyền theo đối tượng

- **Role (RBAC):** nhóm quyền gắn với nhiệm vụ, chẳng hạn **READER**, **EDITOR**, **AUDITOR**. Trong Spring Security, **hasRole("ADMIN")** theo mặc định tìm **ROLE_ADMIN**.
- **Authority:** chuỗi quyền mà Spring Security kiểm tra trực tiếp bằng **hasAuthority("document:read")**. Chuỗi authority có thể là **ROLE_ADMIN**, **document:read**, **SCOPE_documents.read**; các tiền tố có ý nghĩa tùy cấu hình.
- **Điều kiện theo đối tượng (ABAC/ownership):** kiểm tra **resource.ownerId == principal.id**, **resource.tenantId == principal.tenantId**, trạng thái nghiệp vụ hoặc quy tắc thuộc tính khác.
- **Thời gian và phạm vi:** một quyền chỉ hợp lệ trong một dự án, tenant, khoảng thời gian hoặc phiên làm việc nhất định nếu nghiệp vụ yêu cầu.

RBAC giúp quản lý nhiều người dùng; kiểm tra đối tượng ngăn một role quá rộng làm lộ dữ liệu. Trong ứng dụng thực tế thường phải kết hợp cả hai.

## 3. Default deny phải đúng ở nhiều lớp

Từ chối mặc định cần được thực thi nơi **thực sự kiểm soát truy cập**, không chỉ bằng một dòng cấu hình hay việc ẩn nút trên giao diện.

~~~text
                 HTTP request
                      |
          SecurityFilterChain nào bảo vệ?
                      |
            HTTP-level authorization
          allowlist cụ thể + denyAll cuối
                      |
              Controller / Service
                      |
          Method-level / domain policy
         role + action + resource + tenant
                      |
              Truy vấn dữ liệu
             kiểm tra đúng scope
                      |
                Thực hiện / trả kết quả
~~~

Mỗi lớp xử lý một nguy cơ khác nhau:

1. **Chuỗi bảo vệ:** request phải đi vào một **SecurityFilterChain** thích hợp.
2. **HTTP policy:** chỉ các tổ hợp URL + HTTP method được cấp quyền mới đi qua.
3. **Method/domain policy:** một thao tác nghiệp vụ phải được kiểm tra ngay cả khi được gọi từ nơi khác ngoài controller.
4. **Data scope:** câu truy vấn và cập nhật dữ liệu chỉ thao tác trên tài nguyên thuộc quyền cho phép.
5. **Tài khoản/hạ tầng:** kết nối database, service credentials và cloud roles cũng cần quyền tối thiểu.

**Một request được phép qua URL chưa đồng nghĩa toàn bộ tài nguyên bên trong đều được phép đọc hoặc sửa.**

### 3.1. Default deny trong HTTP authorization của Spring Security

Với cấu hình Servlet thông dụng:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/docs/*")
            .hasAuthority("document:read")
        .requestMatchers(HttpMethod.GET, "/api/admin/audit")
            .hasRole("ADMIN")
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

Đây là **đoạn trích trong lớp @Configuration**, cần các import và bean đầy đủ như ví dụ chạy được bên dưới.

- Các rule **cụ thể** nằm trước.
- **anyRequest().denyAll()** chặn request chưa được khai báo quyền cho phép, kể cả endpoint mới do lập trình viên vô tình thêm vào controller.
- **hasAuthority("document:read")** yêu cầu chính xác authority này; nó chưa kiểm tra chủ sở hữu tài liệu.
- **permitAll()** chỉ miễn yêu cầu authorization đối với đường dẫn được cho phép. Request vẫn đi qua **SecurityFilterChain** và các cơ chế bảo vệ khác đang áp dụng.

**Spring Security xét các rule request theo thứ tự và dùng rule đầu tiên khớp.** Nếu đặt rule rộng **anyRequest().permitAll()** hoặc **requestMatchers("/api/**").permitAll()** trước các rule hạn chế, cấu hình có thể cho phép nhiều hơn dự kiến; với API đang bảo vệ, hãy thiết kế allowlist có chủ đích.

### 3.2. Đừng nhầm giới hạn chain với chính sách trong chain

Có hai khái niệm khác nhau:

- **securityMatcher(...)**: quyết định một request có thuộc **SecurityFilterChain** này hay không.
- **requestMatchers(...)** trong **authorizeHttpRequests(...)**: quyết định quyền truy cập đối với request **đã vào chain đó**.

Khi cấu hình nhiều chain, **FilterChainProxy** chọn chain khớp đầu tiên theo thứ tự. Nếu chỉ tạo chain **securityMatcher("/api/**")** mà không có chain bao trùm còn lại, các URL ngoài **/api/** có thể **không được Spring Security bảo vệ**. Lệnh **anyRequest().denyAll()** ở chain API chỉ chặn các request **đã khớp chain API**, không tự bảo vệ phần ngoài phạm vi.

Khi cần nhiều chain, nên thiết kế **chain cuối cùng không giới hạn securityMatcher và có anyRequest().denyAll()** (hoặc rule rõ ràng cần thiết khác), kiểm tra thứ tự **@Order** và test cả URL nằm ngoài dự kiến.

### 3.3. Phương thức nghiệp vụ không tự bị từ chối mặc định

**@EnableMethodSecurity** kích hoạt khả năng dùng **@PreAuthorize**, **@PostAuthorize**... nhưng **không tự suy ra rằng tất cả method chưa được gắn rule đều bị deny**. Để method/domain layer có tính default deny, cần **quy ước phạm vi truy cập rõ ràng**: các entry point nghiệp vụ nhạy cảm phải có policy hoặc chỉ được truy cập qua lớp service đã thực thi policy; test các đường gọi nội bộ/batch/message không đi qua HTTP filter.

Tránh nghĩ rằng chỉ cần kiểm tra security ở controller là an toàn: một service có thể được dùng từ scheduled job, messaging listener hoặc controller mới.

## 4. Ví dụ hoàn chỉnh: policy theo URL, quyền và chủ sở hữu

Ví dụ bên dưới có ba tài khoản demo:

- **alice** và **bob** có authority **document:read**, mỗi người chỉ sở hữu một tài liệu.
- **admin** có **ROLE_ADMIN** để đọc audit, nhưng không được ngầm cấp **document:read**.
- Chỉ **GET /api/ping** công khai; mọi URL/method chưa liệt kê bị deny.

Đây là demo chạy bằng **Spring MVC + Spring Security + HTTP Basic**. Các endpoint đều là **GET** để tập trung vào authorization; khi thêm POST/PUT/DELETE, phải thiết kế tiếp policy cho từng thao tác và CSRF theo loại client.

### 4.1. Dependencies

Tạo ứng dụng Spring Boot 3.x với **Java 17+**, **Spring Web**, **Spring Security** và **Spring Security Test**, rồi thêm trong **build.gradle** hiện có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Dự án cần plugin Spring Boot và Java, kho Maven Central cùng version/dependency management đã cấu hình. Ví dụ dưới đây dùng package **com.example.leastprivilege**; tạo file đúng tên, đúng thư mục trong **src/main/java/com/example/leastprivilege/**.

### 4.2. Điểm khởi động: LeastPrivilegeApplication.java

~~~java
package com.example.leastprivilege;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LeastPrivilegeApplication {
    public static void main(String[] args) {
        SpringApplication.run(LeastPrivilegeApplication.class, args);
    }
}
~~~

### 4.3. SecurityConfig.java — allowlist + denyAll

~~~java
package com.example.leastprivilege;

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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/docs/*")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
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
            .authorities("document:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob123"))
            .authorities("document:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, admin);
    }
}
~~~

**Ý nghĩa bảo mật:**

1. Không khai báo **securityMatcher(...)** cho chain này, nên mặc định nó phù hợp mọi request.
2. **GET /api/ping** là ngoại lệ public đã cân nhắc.
3. **GET /api/docs/* ** yêu cầu capability đọc tài liệu ở HTTP layer.
4. **GET /api/admin/audit** yêu cầu **ROLE_ADMIN**.
5. **anyRequest().denyAll()** tạo điểm chặn cuối cùng. Ví dụ thêm controller **GET /api/new-feature** nhưng quên thêm authorization rule thì request bị từ chối.
6. **@EnableMethodSecurity** cho phép chặn thêm trong service.

Các mật khẩu hard-code chỉ dành cho **localhost/demo**. HTTP Basic gửi username/password mã hóa Base64 nên phải dùng **HTTPS** khi có mạng thực; môi trường production nên dùng identity provider, secrets và vòng đời credential phù hợp. Không tự động suy ra mô hình HTTP Basic tương đương với bearer token hoặc cơ chế session của ứng dụng khác.

### 4.4. DocumentPolicy.java — chỉ cấp quyền đối với tài liệu sở hữu

~~~java
package com.example.leastprivilege;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    // Dữ liệu giả lập; production cần truy vấn theo tenant và quyền thực tế.
    private static final Map<String, String> OWNER_BY_ID = Map.of(
        "doc-1", "alice",
        "doc-2", "bob"
    );

    public boolean ownedBy(Authentication authentication, String documentId) {
        if (authentication == null || documentId == null) {
            return false;
        }

        String owner = OWNER_BY_ID.get(documentId);
        return owner != null && owner.equals(authentication.getName());
    }
}
~~~

**Điểm then chốt:** **Map.get(...)** trả null khi tài liệu không tồn tại; biểu thức **owner != null && ...** trả **false**. Thiếu thông tin chứng minh quyền truy cập dẫn đến **không cho phép**. Không dùng điều kiện nguy hiểm như “owner == null thì cho phép” hay mặc định tenant “all”.

Bản production phải kiểm tra **user ID ổn định**, tenant và quyền trên dữ liệu thực; không coi username là ID bền vững, và không tin tham số tenant hoặc owner do client tự gửi.

### 4.5. DocumentService.java — bảo vệ điểm vào nghiệp vụ

~~~java
package com.example.leastprivilege;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.ownedBy(authentication, #p0)"
    )
    public String readDocument(String id) {
        return "document:" + id;
    }
}
~~~

Biểu thức **@PreAuthorize** phải thỏa **cả hai** điều kiện:

- **document:read**: có quyền cho loại hành động;
- **documentPolicy.ownedBy(...)**: có quyền đối với chính tài liệu được truyền vào method.

**#p0** tham chiếu tham số thứ nhất của method, tránh phụ thuộc khả năng giữ tên tham số khi biên dịch. Policy là bean do Spring quản lý, và method được gọi qua Spring proxy nên annotation có hiệu lực. Nếu một method trong cùng bean gọi trực tiếp method khác qua **this**, Spring AOP proxy có thể không chặn cuộc gọi nội bộ đó; hãy thiết kế điểm kiểm soát và test đường gọi thực tế.

Lớp service này còn bảo vệ khi có một controller khác gọi **readDocument(...)**, vì quyền được thực thi tại điểm vào nghiệp vụ do Spring quản lý, thay vì chỉ dựa vào URL cũ.

### 4.6. DemoController.java — expose các endpoint

~~~java
package com.example.leastprivilege;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final DocumentService documents;

    public DemoController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/docs/{id}")
    public String readDocument(@PathVariable String id) {
        return documents.readDocument(id);
    }

    @GetMapping("/api/admin/audit")
    public String audit() {
        return "audit";
    }

    // Controller có tồn tại nhưng không có rule cho phép ở SecurityConfig.
    @GetMapping("/api/forgotten")
    public String forgotten() {
        return "sensitive";
    }
}
~~~

Endpoint **/api/forgotten** là một trường hợp cố ý để kiểm tra **default deny**: controller tồn tại nhưng rule fallback chặn trước khi phương thức được thực thi.

### 4.7. Chạy và dự đoán kết quả

Nếu dự án đã có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Nếu chưa có wrapper, sử dụng lệnh **gradle bootRun** với bản Gradle tương thích Spring Boot của dự án, hoặc tạo wrapper theo hướng dẫn của Spring Boot.

Từ terminal khác, thử:

~~~bash
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/api/docs/doc-1
curl -i -u alice:alice123 http://localhost:8080/api/docs/doc-1
curl -i -u alice:alice123 http://localhost:8080/api/docs/doc-2
curl -i -u bob:bob123 http://localhost:8080/api/docs/doc-2
curl -i -u admin:admin123 http://localhost:8080/api/admin/audit
curl -i -u admin:admin123 http://localhost:8080/api/docs/doc-1
curl -i -u admin:admin123 http://localhost:8080/api/forgotten
curl -i -u alice:wrong http://localhost:8080/api/docs/doc-1
~~~

Đây là các **kỳ vọng** với đúng ứng dụng demo, không có reverse proxy hoặc exception handler tùy chỉnh:

| Request | HTTP | Nội dung body khi thành công | Nguyên nhân |
| --- | --- | --- | --- |
| Anonymous → /api/ping | **200** | **pong** | Chỉ endpoint này được công khai. |
| Anonymous → /api/docs/doc-1 | **401** | — | Thiếu danh tính khi endpoint cần quyền. HTTP Basic đưa challenge. |
| alice → /api/docs/doc-1 | **200** | **document:doc-1** | Có document:read và là chủ sở hữu. |
| alice → /api/docs/doc-2 | **403** | — | Có quyền loại thao tác nhưng không sở hữu doc-2. |
| bob → /api/docs/doc-2 | **200** | **document:doc-2** | Đúng quyền và đúng chủ sở hữu. |
| admin → /api/admin/audit | **200** | **audit** | Có ROLE_ADMIN. |
| admin → /api/docs/doc-1 | **403** | — | ROLE_ADMIN không tự bao gồm document:read. |
| admin → /api/forgotten | **403** | — | Rule cuối anyRequest().denyAll() chặn endpoint chưa khai báo. |
| alice với mật khẩu sai → /api/docs/doc-1 | **401** | — | HTTP Basic xác thực thất bại. |

**Không khẳng định 401/403 luôn cố định với mọi cấu hình.** Với form login, request chưa đăng nhập có thể bị redirect **302**; cách biến ngoại lệ bảo mật thành status tùy **AuthenticationEntryPoint** và **AccessDeniedHandler**. Trong ví dụ, các request đã xác thực nhưng bị deny nhận **403**. Một lỗi do chính ứng dụng hoặc reverse proxy tạo ra cũng có thể có status khác.

## 5. Kiểm thử chính sách: phải có cả ca bị từ chối

Chỉ test những gì **được phép** sẽ bỏ qua nhiều lỗi authorization quan trọng. Kiểm thử có giá trị cần chứng minh cả **không có quyền**, **sai resource** và **endpoint chưa khai báo** đều bị chặn.

Thêm file **src/test/java/com/example/leastprivilege/AuthorizationPolicyTest.java**:

~~~java
package com.example.leastprivilege;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationPolicyTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingIsExplicitlyAllowed() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousRequestCannotReadDocuments() throws Exception {
        mvc.perform(get("/api/docs/doc-1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/docs/doc-1")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("document:doc-1"));
    }

    @Test
    void readerCannotReadAnotherUsersDocument() throws Exception {
        mvc.perform(get("/api/docs/doc-2")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanViewAuditButCannotReadUnrelatedDocuments() throws Exception {
        mvc.perform(get("/api/admin/audit")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit"));

        mvc.perform(get("/api/docs/doc-1")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void newRouteWithoutAllowRuleIsDenied() throws Exception {
        mvc.perform(get("/api/forgotten")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownDocumentIdDoesNotGrantAccess() throws Exception {
        mvc.perform(get("/api/docs/doc-404")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**Cách đọc kết quả kiểm thử:**

- Test **newRouteWithoutAllowRuleIsDenied** chứng minh controller có tồn tại cũng không tự được mở quyền.
- Test **readerCannotReadAnotherUsersDocument** chứng minh quyền loại thao tác **document:read** chưa đủ để đọc mọi tài liệu.
- Test **adminCanViewAuditButCannotReadUnrelatedDocuments** ngăn việc vô tình hiểu **ADMIN** là superuser cho mọi tài nguyên.
- Test **unknownDocumentIdDoesNotGrantAccess** chứng minh policy trả **false** khi thiếu thông tin sở hữu.

Ví dụ trả **403** với ID không được phép hoặc không tồn tại theo chính sách demo. Trong hệ thống thực, có thể dùng **404** để giảm khả năng dò sự tồn tại của tài nguyên, nhưng phải thống nhất chính sách và không để thông tin rò qua nội dung lỗi, thời gian xử lý hoặc một endpoint khác.

## 6. Khi thêm tính năng mới, đánh giá quyền theo trình tự nào?

Giả sử nhóm thêm **POST /api/docs/{id}/approve**. Trước khi cho endpoint hoạt động:

1. **Xác định hành động nghiệp vụ**: **document:approve**, không tái sử dụng **document:read** chỉ vì cùng URL.
2. **Xác định danh tính được phép**: người có quyền phê duyệt trong tenant, có thể phải khác người tạo.
3. **Xác định resource condition**: tài liệu thuộc tenant nào, trạng thái có thể phê duyệt không, người duyệt có xung đột lợi ích không.
4. **Bổ sung rule HTTP rõ ràng** cho đúng **POST + path** và bảo vệ method/service xử lý.
5. **Kiểm tra dữ liệu tại thời điểm thao tác**: tránh kiểm tra quyền trước rồi dùng dữ liệu đã đổi sau đó (**TOCTOU**); thao tác nhạy cảm nên kiểm tra và cập nhật nhất quán trong transaction, với concurrency control khi cần.
6. **Test positive và negative**: anonymous, token hết hạn, tài khoản thiếu quyền, đúng quyền nhưng sai tenant, tài liệu đã được duyệt, endpoint khác chưa khai báo.
7. **Đánh giá CSRF** nếu dùng browser/cookie/session; chính sách CSRF khác nhau tùy client và cách mang credential. Không vô hiệu hóa CSRF chỉ để làm một test POST chuyển xanh.

Một policy minh họa ở tầng service (không phải lớp Java hoàn chỉnh) có thể là:

~~~java
@PreAuthorize(
    "hasAuthority('document:approve') and " +
    "@approvalPolicy.canApprove(authentication, #p0)"
)
public void approveDocument(String documentId) {
    // Thực thi có transaction và kiểm tra trạng thái nhất quán.
}
~~~

**Phân biệt:** annotation là cổng kiểm soát quyền; transaction, xử lý trạng thái và kiểm tra dữ liệu vẫn cần được hiện thực ở service/repository. Rule này không tự giải quyết tính nhất quán khi có nhiều request song song.

## 7. Các tình huống thường làm nguyên tắc bị phá vỡ

### 7.1. "Mọi người đăng nhập đều được"

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
)
~~~

Cấu hình này chỉ yêu cầu **có danh tính**, không phân biệt quyền đọc, sửa, duyệt hoặc phạm vi tenant. Đối với một API chứa dữ liệu nhiều người dùng, **authenticated()** thường là điều kiện cần nhưng **chưa đủ**. Thiết kế lại theo từng action và kiểm tra resource.

### 7.2. "Một role bao trùm mọi quyền"

~~~java
.requestMatchers("/api/**").hasRole("ADMIN")
~~~

Rule này đôi khi hợp lý cho API quản trị thật sự, nhưng không có nghĩa mọi chức năng kinh doanh phải thuộc về ADMIN. Nó dễ tạo một quyền quá rộng hoặc buộc đội vận hành chia sẻ tài khoản ADMIN. Chia theo capability như **invoice:approve**, **user:disable**, **audit:read** và chỉ cấp nhóm cần thiết.

### 7.3. "Lấy tenantId từ query parameter là đủ"

Một client gọi **GET /api/orders?tenantId=other-company**. Nếu service dùng tenantId từ request làm phạm vi query mà **không kiểm tra nó thuộc các tenant được principal phép truy cập**, chỉ cần sửa tham số là có thể lộ dữ liệu. Tenant phải được xác thực qua danh tính/policy và ràng buộc ở truy vấn; đồng thời kiểm tra quyền trên từng resource khi cần.

### 7.4. "Không có owner thì ai cũng được đọc"

Ví dụ nguy hiểm:

~~~java
// Sai: thiếu dữ liệu sở hữu lại mở quyền.
return owner == null || owner.equals(username);
~~~

Cách an toàn cho bài học:

~~~java
// Thiếu dữ liệu sở hữu: không đủ bằng chứng cấp quyền.
return owner != null && owner.equals(username);
~~~

Với lỗi database hoặc identity service, hệ thống cũng **không được mặc định cho phép** chỉ vì policy không trả được kết quả. Response có thể là **5xx** nếu phụ thuộc hỏng; nguyên tắc là **không thực hiện hành động khi chưa xác minh đủ quyền**, không bắt buộc mọi lỗi hạ tầng đều phải đổi thành 403.

### 7.5. "Ẩn nút Edit trên frontend là đã phân quyền"

Frontend chỉ là trải nghiệm người dùng. Kẻ tấn công hoặc người dùng bình thường có thể tự gửi HTTP request. Backend phải kiểm soát mọi endpoint và mọi luồng thao tác dữ liệu.

### 7.6. "Endpoint này chỉ gọi nội bộ nên miễn bảo vệ"

Các endpoint nội bộ vẫn có nguy cơ bị lộ qua cấu hình ingress, service mesh, SSRF hoặc lỗi mạng. Dùng service identity, authentication phù hợp, permission đúng phạm vi và network control, thay vì mặc định tin mọi lưu lượng nội bộ.

### 7.7. "Method security được bật nên mọi method đều an toàn"

**@EnableMethodSecurity** làm những annotation được hỗ trợ có hiệu lực khi lời gọi đi qua proxy. Method không được gắn policy không tự bị chặn. Self-invocation và đường gọi không qua proxy cũng cần xem xét. Phân quyền domain phải có quy ước rõ và kiểm thử đường gọi thực tế.

### 7.8. "Chỉ cần anyRequest().denyAll() ở một chain"

Nếu chain đó chỉ match **/api/**, các request khác có thể nằm ngoài nó. Luôn kiểm tra tổng hợp các **SecurityFilterChain**, thứ tự và chain cuối để không có lỗ hổng bao phủ.

## 8. Quyền tối thiểu cũng áp dụng ngoài request HTTP

Một thiết kế tốt phải hạn chế quyền của **thành phần thực thi**:

| Thành phần | Cần cấp | Nên tránh |
| --- | --- | --- |
| User đọc báo cáo | Quyền xem báo cáo thuộc phạm vi đã duyệt | Quyền xóa báo cáo, đọc toàn bộ tenant |
| Worker gửi email | Quyền đọc hàng đợi gửi và gửi qua provider được chỉ định | Quyền admin hệ thống, truy cập mọi bảng |
| API đọc dữ liệu | Kết nối DB với quyền SELECT trên bảng/view cần thiết | Dùng tài khoản database superuser |
| CI triển khai | Quyền deploy đúng môi trường và tài nguyên | Token tổ chức có quyền rộng hoặc không hết hạn |
| Người trực hỗ trợ | Quyền hỗ trợ có thời hạn, audit hoạt động | Chia sẻ mật khẩu admin vĩnh viễn |
| OAuth2 client | Các scope thật sự cần cho tác vụ | Scope wildcard rộng ở mọi token |

Thực hành tốt: **tách tài khoản theo nhiệm vụ**, hạn chế thời hạn token/credential, loại bỏ quyền khi đổi vai trò, thu hồi quyền khi rời dự án, quản lý secrets an toàn và lưu dấu quyết định truy cập quan trọng. Phân quyền là quá trình theo dõi thay đổi, không phải thao tác cấu hình một lần.

### 8.1. Nếu dùng JWT/OAuth2, cần đặc biệt chú ý

Trong một **Resource Server**, token hợp lệ **chưa chứng minh** mọi API đều có thể gọi. Cần kiểm tra **issuer**, **audience**, thời hạn và chữ ký theo cấu hình, sau đó áp dụng scope/authority cùng kiểm tra tenant, resource, owner. **SCOPE_documents.read** thường chỉ là quyền loại thao tác, không tự giải quyết ai được đọc tài liệu nào.

Một scope quá rộng hoặc token sống quá lâu sẽ tăng thiệt hại khi token bị lộ. Cần thiết kế vòng đời và phạm vi token dựa trên rủi ro.

## 9. Audit và kiểm chứng chính sách trước khi release

Với mỗi endpoint hoặc business action, lập bảng **subject × action × resource × context** rồi trả lời:

1. **Ai được phép?** Quyền này cần có lý do nghiệp vụ.
2. **Ai phải bị từ chối?** Bao gồm anonymous, sai role, sai tenant, không sở hữu, tài khoản bị khóa hoặc role cũ.
3. **Nếu không có rule mới thì sao?** Endpoint chưa khai báo phải bị deny hoặc không thể tiếp cận.
4. **Nếu dữ liệu policy thiếu hoặc service kiểm tra quyền lỗi thì sao?** Không thực thi hành động dựa trên giả định “chắc là được”.
5. **URL, method, service và data layer có nhất quán?** Bao gồm request matcher, chain matcher, dispatch và tác vụ ngoài HTTP.
6. **Có log để truy vết không?** Ghi subject ID, action, resource ID, decision, correlation ID trong phạm vi cho phép; **không ghi mật khẩu, token, dữ liệu nhạy cảm**.
7. **Có test từ chối và test đường đi vòng?** Thử URL chưa khai báo, HTTP method khác, role khác, tenant khác, ID khác, gọi trực tiếp service, và các loại request mà ứng dụng thực sự hỗ trợ.

Có thể bật log phát triển để đọc quyết định filter:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Chỉ bật mức phù hợp theo môi trường và không log bí mật. Khi gặp bất ngờ **401/403**, xác định chain, Authentication, authorities, request matcher đầu tiên, method rule và resource policy. Một **403** không nói rõ đã thất bại ở lớp nào nếu chưa kiểm tra log.

### 9.1. Cảnh báo về denyAll ở môi trường thực tế

**anyRequest().denyAll()** là lựa chọn mạnh cho allowlist; vì vậy khi bổ sung ứng dụng, cần xét riêng những endpoint hợp lệ như health check, asset, authentication callback, CORS preflight, error/forward dispatch và endpoint do framework cung cấp. Chỉ thêm ngoại lệ khi có nhu cầu rõ và phạm vi hẹp.

Spring Security có thể xét authorization cả các **dispatcher type** như **REQUEST**, **ERROR**, **FORWARD** tùy cấu hình. Nếu trang lỗi/forward cần hoạt động, thiết kế rule dispatch type có chủ đích; không dùng ngoại lệ **permitAll** quá rộng cho toàn ứng dụng để sửa lỗi hiển thị.

## 10. Bài tập tự đánh giá

**Bài 1 — Endpoint mới.** Bạn thêm **GET /api/export** vào controller nhưng chưa thêm rule authorization. Với **anyRequest().denyAll()** cuối chain bao trùm mọi URL, chuyện gì xảy ra?

**Đáp án:** Request bị từ chối trước khi controller xử lý. Nếu một chain không bao trùm URL đó hoặc có rule cho phép rộng đặt trước, kết quả có thể khác; phải kiểm tra cấu hình chain tổng thể.

**Bài 2 — Role đủ hay chưa?** **alice** có **document:read** nhưng gọi **GET /api/docs/doc-2** (tài liệu của bob).

**Đáp án:** Phải từ chối nếu policy sở hữu không cho phép. Authority nói về **loại hành động**, chưa khẳng định quyền với **tài liệu cụ thể**.

**Bài 3 — Mất dữ liệu sở hữu.** Service đọc owner trả null hoặc gặp timeout. Có nên mặc định mở quyền để giữ hệ thống hoạt động?

**Đáp án:** Không. Không được thực thi hành động khi thiếu bằng chứng cấp quyền. Có thể trả response lỗi hạ tầng và retry an toàn; không coi lỗi policy là quyết định ALLOW.

**Bài 4 — Chỉ có chain /api/**.** Cấu hình một SecurityFilterChain với **securityMatcher("/api/**")** và **anyRequest().denyAll()**; **GET /internal/debug** có chắc chắn bị Spring Security chặn không?

**Đáp án:** Không. Nếu không có chain nào khác khớp **/internal/debug**, endpoint có thể nằm ngoài lớp bảo vệ Spring Security.

**Bài 5 — Quyền admin.** Một người có **ROLE_ADMIN** có nên tự động đọc mọi tài liệu cá nhân?

**Đáp án:** Không mặc định. Xác định capability hỗ trợ, mục đích nghiệp vụ, phạm vi, phê duyệt và audit nếu cần quyền đặc biệt.

**Bài 6 — Xác thực và phân quyền.** Vì sao **401** và **403** đều có thể xuất hiện khi request không được phép?

**Đáp án:** **401** thường là cơ chế yêu cầu xác thực (ví dụ HTTP Basic challenge) khi chưa có danh tính hợp lệ; **403** thường cho danh tính đã được xác thực nhưng không đủ quyền. Chính sách entry point/handler và loại client có thể làm phản hồi khác.

## Tài liệu chính thức để học thêm

- Spring Security — **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Java Configuration / Multiple HttpSecurity**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **Servlet Architecture**: https://docs.spring.io/spring-security/reference/servlet/architecture.html

**Ghi nhớ:** hãy **cấp đúng hành động, trên đúng tài nguyên, trong đúng ngữ cảnh**. Mỗi lần thêm chức năng, chính sách cho phép cần được quyết định rõ ràng; **mọi trường hợp chưa chứng minh được quyền đều không được cấp quyền**.
