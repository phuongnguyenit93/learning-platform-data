# Giới hạn truy vấn theo danh tính và kiểm soát dữ liệu trả về trong Spring Security Servlet

## 1. Khái niệm và mục tiêu

Một người dùng đã đăng nhập thành công **không mặc nhiên có quyền đọc mọi bản ghi** của một REST API. Nếu Alice và Bob cùng có ROLE_USER nhưng chỉ được xem tài liệu do mình sở hữu, việc Alice thử URL của tài liệu Bob phải bị chặn. Lỗi cho phép truy cập bằng cách đổi ID được gọi là **Broken Object Level Authorization (BOLA)**, cũng thường gọi **IDOR** (Insecure Direct Object Reference).

Hệ thống cũng có thể lộ dữ liệu ngay cả khi đã lọc đúng bản ghi: một entity có thể chứa **private_note**, dữ liệu PII hay cờ quản trị nội bộ. Việc frontend không hiển thị field đó **không che được JSON trên đường truyền**. Phân quyền tài nguyên vì thế có hai mặt:

- **Giới hạn truy vấn theo danh tính**: database chỉ trả những row trong phạm vi mà Authentication hiện tại có quyền đọc.
- **Giới hạn dữ liệu trả về**: controller chỉ trả những field được phép công bố qua DTO/projection rõ ràng.

Bài này nằm trong **Spring Security Servlet — Quyền tài nguyên**. Bạn sẽ học row-level authorization, tenant membership, query scope, count/search/pagination, DTO, HTTP 401/403/404, các lỗi cache/export và một ứng dụng chạy được với **Java 17+, Spring Boot 3.3.13, Spring Security 6, JDBC/H2 và MockMvc**.

## 2. Bốn tầng bảo mật phải tách biệt

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Request thuộc về ai? | SecurityContext, UserDetailsService, HTTP Basic |
| URL authorization | User được gọi loại endpoint không? | authorizeHttpRequests, authenticated() |
| Object authorization | User được xem document ID này không? | WHERE tenant, owner, membership |
| Field authorization | User được nhận cột nào? | SELECT projection, DocumentView DTO |

Ví dụ chỉ có URL protection:

~~~java
// Chỉ là fragment trong SecurityFilterChain:
.requestMatchers(HttpMethod.GET, "/api/tenants/**")
.authenticated()
~~~

không chứng minh Alice được xem document của Bob. Spring Security bảo vệ request ở tầng filter, còn repository/service phải thực thi **object-level authorization** và lớp response phải thực thi **field-level authorization**. Chỉ dùng hasRole("USER") không đủ nếu hai user cùng role có dữ liệu sở hữu khác nhau.

### Danh tính phải đến từ phía server

Dùng **Authentication.getName()** hoặc principal đã được framework xác thực. Không lấy owner từ request param owner=bob, JSON username=alice hoặc header X-User mà client tự sửa. Khi sử dụng JWT, phải xác minh token đúng issuer, audience, signature, expiry rồi mới dùng subject; vẫn phải kiểm tra quyền row theo nguồn tin cậy. Production nên sử dụng userId bất biến thay username/email nếu người dùng được phép đổi tên.

## 3. Mô hình ví dụ: tenant và owner

Các user:

| User | Membership active | Role |
| --- | --- | --- |
| alice | tenant-a, tenant-b | USER |
| bob | tenant-a | USER |
| carol | tenant-b | USER |

Các row tài liệu:

| ID | Tenant | Owner | Title |
| --- | --- | --- | --- |
| 101 | tenant-a | alice | Alpha report |
| 102 | tenant-a | alice | Weekly plan |
| 103 | tenant-a | bob | Payroll |
| 104 | tenant-b | carol | Legal review |
| 105 | tenant-b | alice | Migration plan |

Chính sách demo là **owner-only và active tenant membership**. Một document chỉ visible nếu:

~~~text
document.tenantId == requestedTenantId
AND document.ownerUsername == authenticatedUsername
AND exists active membership(authenticatedUsername, document.tenantId)
~~~

Từ đó Alice ở tenant-a thấy 101/102, Bob ở tenant-a thấy 103, Alice ở tenant-b thấy 105. Bob không phải thành viên tenant-b, nên không nhận tài liệu từ tenant ấy. Alice đoán ID 103 của Bob phải nhận **404**, không nhận bất kỳ field nào của document đó.

**TenantId trong path chỉ là identifier do client yêu cầu**, không phải bằng chứng đã được cấp quyền. Một người dùng có thể đổi /tenant-a thành /tenant-b trên URL; server phải kiểm tra membership và owner một cách độc lập.

## 4. Query phải được giới hạn trước khi về Java

Chống mẫu sai:

~~~java
// Fragment chống mẫu sai, không phải file độc lập:
// var rows = repository.findAll();
// return rows.stream()
//     .filter(d -> d.owner().equals(authentication.getName()))
//     .toList();
~~~

Cách này vẫn đọc dữ liệu không có quyền vào bộ nhớ, dễ leak qua log/cache, tốn tài nguyên và có thể làm sai COUNT, LIMIT/OFFSET.

**Query với quyền nằm trong SQL:**

~~~sql
SELECT d.id, d.title, d.preview
FROM documents d
WHERE d.tenant_id = ?
  AND d.owner_username = ?
  AND EXISTS (
      SELECT 1 FROM tenant_memberships m
      WHERE m.username = ?
        AND m.tenant_id = d.tenant_id
        AND m.active = TRUE
  )
ORDER BY d.id ASC;
~~~

Hai chỗ username phải bind từ Authentication.getName(), không lấy từ query/body. Mệnh đề tenant kiểm tra URL scope, owner kiểm tra row scope, EXISTS bảo đảm membership chưa bị revoke. Chỉ SELECT id, title, preview thay vì SELECT * chứa private_note.

### Cùng một visibility cho mọi đường đọc

Một hệ thống có thể bảo vệ GET /documents nhưng quên GET /documents/{id}, /count, /search hoặc /export. Tất cả phải dùng cùng predicate. Trong demo, một hằng **VISIBLE_FROM** được dùng cho list, detail và count:

- **List**: visibility + title filter + ORDER BY + LIMIT/OFFSET.
- **Detail**: visibility + AND d.id = ?.
- **Count**: SELECT COUNT(*) cùng visibility và keyword filter.
- **Search**: keyword không được làm thay đổi tenant/owner filter.

**COUNT(*) cũng có thể lộ thông tin**. Nếu Alice có hai document nhưng API count toàn bảng trả năm, nó đã tiết lộ cardinality ngoài quyền của Alice. Aggregations SUM/AVG/GROUP BY và metadata tương tự cũng cần scope.

### Phân trang, sort và LIKE

Đặt LIMIT/OFFSET sau WHERE scope. Giới hạn page size để tránh quá tải, ORDER BY theo khóa ổn định. Nếu hỗ trợ sort động, map tên sort từ allowlist server, không nối raw client input vào ORDER BY. Với dataset lớn cân nhắc cursor/keyset pagination; cursor phải gắn scope và chống sửa nếu mang dữ liệu nhạy cảm.

JdbcTemplate bind SQL parameters giúp tránh SQL injection. Nhưng trong LIKE, ký tự % và _ vẫn là wildcard. Nếu API muốn tìm **chuỗi literal**, escape chúng; demo dùng **ESCAPE '!'**, thay ! thành !!, % thành !%, _ thành !_ rồi bind. Kể cả khi người dùng nhập wildcard, predicate tenant/owner vẫn phải giữ nguyên.

## 5. Trường dữ liệu trả về phải có allowlist

Bảng documents có id, tenant_id, owner_username, title, preview và private_note. API user-facing của demo chỉ cho phép ba trường:

~~~java
public record DocumentView(long id, String title, String preview) {}
~~~

Response đúng:

~~~json
{"id":101,"title":"Alpha report","preview":"Alice safe summary"}
~~~

Không có private_note. Một query param includeSecret=true không thể tự cấp field permission. Khi có role support được xem dữ liệu đặc biệt, cần authorization riêng, DTO khác và audit. Hãy dọn field **trước khi serialize**, không gửi PII rồi dùng CSS/JavaScript mask sau.

JPA entity có getter/relationship mới có thể làm JSON mở rộng bất ngờ. DTO/projection allowlist giúp giữ output contract. Các trường như file URL, createdBy, timestamp, attachments count cũng có thể nhạy cảm.

## 6. Ví dụ Maven hoàn chỉnh

Cấu trúc:

~~~text
scoped-documents-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/scopeddocs/
    │   │   ├── ScopedDocumentsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DocumentView.java
    │   │   ├── DocumentRepository.java
    │   │   └── DocumentController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/com/example/scopeddocs/
        └── DocumentVisibilityTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>scoped-documents-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

### 6.2. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:scopeddocs;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.h2.console.enabled=false
~~~

H2 in-memory được nạp từ SQL scripts khi app khởi động, không phải database production.

### 6.3. schema.sql

~~~sql
CREATE TABLE tenant_memberships (
    username VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (username, tenant_id)
);
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    owner_username VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    preview VARCHAR(500) NOT NULL,
    private_note VARCHAR(1000) NOT NULL
);
CREATE INDEX idx_docs_scope
    ON documents (tenant_id, owner_username, id);
~~~

### 6.4. data.sql

~~~sql
INSERT INTO tenant_memberships VALUES ('alice','tenant-a',TRUE);
INSERT INTO tenant_memberships VALUES ('alice','tenant-b',TRUE);
INSERT INTO tenant_memberships VALUES ('bob','tenant-a',TRUE);
INSERT INTO tenant_memberships VALUES ('carol','tenant-b',TRUE);

INSERT INTO documents VALUES
(101,'tenant-a','alice','Alpha report',
 'Alice safe summary','INTERNAL_ALICE_SECRET');
INSERT INTO documents VALUES
(102,'tenant-a','alice','Weekly plan',
 'Alice safe plan','INTERNAL_ALICE_PLAN');
INSERT INTO documents VALUES
(103,'tenant-a','bob','Payroll',
 'Bob safe summary','INTERNAL_BOB_SECRET');
INSERT INTO documents VALUES
(104,'tenant-b','carol','Legal review',
 'Carol safe summary','INTERNAL_CAROL_SECRET');
INSERT INTO documents VALUES
(105,'tenant-b','alice','Migration plan',
 'Alice second tenant','INTERNAL_ALICE_B_SECRET');
~~~

Private notes chỉ là chuỗi giả để chứng minh field không bị xuất ra API.

### 6.5. ScopedDocumentsApplication.java

~~~java
package com.example.scopeddocs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopedDocumentsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopedDocumentsApplication.class, args);
    }
}
~~~

### 6.6. SecurityConfig.java

~~~java
package com.example.scopeddocs;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER").build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER").build();
        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("carol-pass"))
            .roles("USER").build();
        return new InMemoryUserDetailsManager(alice, bob, carol);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/tenants/*/documents",
                    "/api/tenants/*/documents/*")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }
}
~~~

HTTP Basic dùng cho demo; mật khẩu được hash bằng BCrypt. Bất kỳ client thật nào gửi HTTP Basic credentials đều cần HTTPS. Không tắt CSRF; demo chỉ có GET, các unsafe methods phải có chính sách CSRF nếu client có browser cookie/credentials được tự gửi.

### 6.7. DocumentView.java

~~~java
package com.example.scopeddocs;

public record DocumentView(
    long id,
    String title,
    String preview
) {}
~~~

### 6.8. DocumentRepository.java

~~~java
package com.example.scopeddocs;

import java.util.List;
import java.util.Locale;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private static final String VISIBLE_FROM = """
        FROM documents d
        WHERE d.tenant_id = ?
          AND d.owner_username = ?
          AND EXISTS (
              SELECT 1 FROM tenant_memberships m
              WHERE m.tenant_id = d.tenant_id
                AND m.username = ?
                AND m.active = TRUE
          )
        """;

    private static final String TITLE_FILTER = """
        AND (? = '' OR LOWER(d.title) LIKE ? ESCAPE '!')
        """;

    private static final RowMapper<DocumentView> VIEW_MAPPER =
        (rs, index) -> new DocumentView(
            rs.getLong("id"),
            rs.getString("title"),
            rs.getString("preview"));

    private final JdbcTemplate jdbc;

    public DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static String normalize(String q) {
        return q.trim().toLowerCase(Locale.ROOT);
    }

    private static String escapedLike(String q) {
        return "%" + q.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_") + "%";
    }

    public List<DocumentView> listVisible(
            String tenantId, String username,
            String q, int limit, int offset) {
        String keyword = normalize(q);
        String sql = "SELECT d.id, d.title, d.preview "
            + VISIBLE_FROM + TITLE_FILTER
            + " ORDER BY d.id ASC LIMIT ? OFFSET ?";

        return jdbc.query(sql, VIEW_MAPPER,
            tenantId, username, username,
            keyword, escapedLike(keyword), limit, offset);
    }

    public Optional<DocumentView> findVisible(
            String tenantId, String username, long id) {
        String sql = "SELECT d.id, d.title, d.preview "
            + VISIBLE_FROM + " AND d.id = ?";
        return jdbc.query(sql, VIEW_MAPPER,
            tenantId, username, username, id)
            .stream().findFirst();
    }

    public long countVisible(
            String tenantId, String username, String q) {
        String keyword = normalize(q);
        String sql = "SELECT COUNT(*) " + VISIBLE_FROM + TITLE_FILTER;
        Long count = jdbc.queryForObject(sql, Long.class,
            tenantId, username, username,
            keyword, escapedLike(keyword));
        return count == null ? 0L : count;
    }
}
~~~

VISIBLE_FROM dùng lại cho list, detail và count. Trong mỗi query, tenantId là bộ chọn do client chỉ định, username là principal server-side, membership phải active. SQL không đọc private_note. Điều kiện search và pagination chỉ bổ sung, **không thay thế visibility predicate**.

### 6.9. DocumentController.java

~~~java
package com.example.scopeddocs;

import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {

    private final DocumentRepository repo;

    public DocumentController(DocumentRepository repo) {
        this.repo = repo;
    }

    private static void validateKeyword(String q) {
        if (q.length() > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Keyword too long");
        }
    }

    @GetMapping
    public List<DocumentView> list(
            @PathVariable String tenantId,
            @RequestParam(defaultValue = "") String q,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(defaultValue = "0") int offset,
            Authentication auth) {

        validateKeyword(q);
        if (limit < 1 || limit > 100 || offset < 0 || offset > 10000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid pagination");
        }
        return repo.listVisible(
            tenantId, auth.getName(), q, limit, offset);
    }

    @GetMapping("/count")
    public Map<String, Long> count(
            @PathVariable String tenantId,
            @RequestParam(defaultValue = "") String q,
            Authentication auth) {
        validateKeyword(q);
        return Map.of("count",
            repo.countVisible(tenantId, auth.getName(), q));
    }

    @GetMapping("/{id}")
    public DocumentView detail(
            @PathVariable String tenantId,
            @PathVariable long id,
            Authentication auth) {

        return repo.findVisible(tenantId, auth.getName(), id)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Không dùng client-supplied ownerId. Detail trả 404 cho bản ghi không tồn tại hoặc không có quyền xem. Collection ngoài scope trả 200 [] theo contract của demo; ứng dụng khác có thể dùng 404 sau membership check nếu chính sách yêu cầu. Request sai limit/offset nhận 400.

## 7. Chạy bằng Maven và curl

~~~bash
mvn spring-boot:run
~~~

Mặc định ứng dụng nghe cổng 8080 khi còn trống. Không có credentials:

~~~bash
curl -i http://localhost:8080/api/tenants/tenant-a/documents
~~~

Kỳ vọng 401 Unauthorized. Alice xem tenant-a:

~~~bash
curl -i -u alice:alice-pass \
  "http://localhost:8080/api/tenants/tenant-a/documents"
~~~

Kỳ vọng 200:

~~~json
[
  {"id":101,"title":"Alpha report","preview":"Alice safe summary"},
  {"id":102,"title":"Weekly plan","preview":"Alice safe plan"}
]
~~~

Bob ở tenant-a chỉ nhận ID 103, Alice ở tenant-b chỉ nhận ID 105, Bob ở tenant-b nhận danh sách rỗng. Alice đoán ID 103 của Bob:

~~~bash
curl -i -u alice:alice-pass \
  "http://localhost:8080/api/tenants/tenant-a/documents/103"
~~~

Kỳ vọng **404 Not Found**. Count của Alice ở tenant-a:

~~~bash
curl -i -u alice:alice-pass \
  "http://localhost:8080/api/tenants/tenant-a/documents/count"
~~~

Kỳ vọng JSON {"count":2}. Search:

~~~bash
curl -i -u alice:alice-pass \
  "http://localhost:8080/api/tenants/tenant-a/documents?q=Alpha"
~~~

Kỳ vọng chỉ ID 101. Với limit=1&offset=1, Alice chỉ thấy ID 102. Sai password trả 401; limit=1000 trả 400. Curl -u chỉ dùng cho credentials giả trong ví dụ localhost; tránh lưu secrets thật vào shell history.

## 8. MockMvc integration test

Tạo **src/test/java/com/example/scopeddocs/DocumentVisibilityTest.java**:

~~~java
package com.example.scopeddocs;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentVisibilityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noCredentialsReturns401() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceOnlySeesOwnTenantADocuments() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)))
            .andExpect(jsonPath("$[0].id").value(101))
            .andExpect(jsonPath("$[1].id").value(102))
            .andExpect(jsonPath("$[0].privateNote").doesNotExist())
            .andExpect(content().string(
                not(containsString("INTERNAL_ALICE_SECRET"))));
    }

    @Test
    void bobOnlySeesHisOwnSameTenantDocument() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(103));
    }

    @Test
    void guessingAnothersDocumentIsBlocked() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents/103")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/tenants/tenant-a/documents/101")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isNotFound());
    }

    @Test
    void ownDocumentStillHidesInternalField() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents/101")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.privateNote").doesNotExist())
            .andExpect(content().string(
                not(containsString("INTERNAL_ALICE_SECRET"))));
    }

    @Test
    void membershipControlsTenantVisibility() throws Exception {
        mvc.perform(get("/api/tenants/tenant-b/documents")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(105));

        mvc.perform(get("/api/tenants/tenant-b/documents")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    void countSearchAndPaginationStayScoped() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents/count")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(2));

        mvc.perform(get("/api/tenants/tenant-a/documents")
                .param("q", "Alpha")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].id").value(101));

        mvc.perform(get("/api/tenants/tenant-a/documents")
                .param("limit", "1")
                .param("offset", "1")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(jsonPath("$[0].id").value(102));
    }

    @Test
    void likeWildcardIsLiteralAndPageSizeIsBounded()
            throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/documents")
                .param("q", "%")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(0)));

        mvc.perform(get("/api/tenants/tenant-a/documents")
                .param("limit", "1000")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isBadRequest());
    }
}
~~~

Thực thi:

~~~bash
mvn test
~~~

Các negative tests **Alice không xem được document Bob**, **Bob không xem được document Alice**, **Bob không có tenant-b membership**, và **private_note không xuất** quan trọng hơn chỉ test Alice đọc được ID 101. MockMvc đi qua Spring Security filter chain; nó không tự chứng minh mọi database/search/cache khác ngoài project cũng đúng.

## 9. Những vấn đề khi đưa vào production

**Spring Data JPA:** Có thể dùng derived query theo owner/tenant hoặc Specification/JPQL với membership, nhưng không trả findById không scoped. Không serialize JPA entity trực tiếp vì getters/relations có thể lộ field.

**PostgreSQL Row-Level Security:** Có thể tăng defense in depth nhưng phải gắn identity/tenant DB session một cách tin cậy, quản lý connection pool reset context, transaction, bypass roles và background jobs. RLS không tự bảo vệ output field.

**CREATE/UPDATE/DELETE:** Owner nên do server gán từ principal; UPDATE/DELETE cần WHERE owner/tenant/ACL và kiểm affectedRows, không chỉ WHERE id = ?. Nếu kiểm quyền một lần rồi cập nhật không scope có nguy cơ TOCTOU.

**Cache/CDN:** Cache theo URL không gắn user/tenant có thể trả response Alice cho Bob dù repository đúng. Với dữ liệu riêng tư dùng Cache-Control: no-store hoặc auth-aware cache key cùng invalidation. Search index, CSV/Excel/PDF export, analytics, download links và async jobs phải thực thi quyền tương đương.

**Quyền thay đổi lúc chạy:** Revoke membership có thể không lập tức hủy request đã vượt kiểm tra, session/JWT/cache vẫn có quyền cũ. Xác định transaction/isolation và policy kiểm tra tại operation boundary. Multi-node cần nguồn quyền chung và fail-closed khi không truy cập được dữ liệu phân quyền nhạy cảm.

**404 hay 403:** Detail ngoài scope có thể trả 404 để giảm tiết lộ sự tồn tại. 404 không tự loại side channels như timing/count. 401 thuộc lỗi chưa xác thực HTTP Basic, 403 có thể do thiếu quyền hoặc CSRF.

## 10. Bài tập có đáp án

1. Alice và Bob đều ROLE_USER ở tenant-a. Alice có đọc document 103 được không? **Không**, vì owner-only policy.
2. Trả entity có private_note rồi frontend giấu field có an toàn không? **Không**, JSON vẫn lộ field.
3. List Alice trả 2 nhưng count toàn bảng trả 5 có leak không? **Có**, count phải cùng query scope.
4. LIMIT 20 trước rồi filter Java có đúng không? **Không**, WHERE quyền phải áp trước pagination.
5. UUID khó đoán thay cho kiểm object authorization được không? **Không**, ID vẫn có thể bị lộ.
6. Client tự gửi owner=bob có phải principal đáng tin không? **Không**, lấy danh tính từ Authentication.
7. PreparedStatement khiến % trong LIKE thành literal chưa? **Chưa**, cần escape theo search contract.
8. Bob lấy response từ CDN cache của Alice có thể xảy ra dù SQL đúng không? **Có**, cần cache key đúng scope/no-store.
9. UPDATE chỉ WHERE id=? có bảo vệ owner không? **Không**, bổ sung predicate quyền và transaction.
10. Admin revoke membership sau khi request bắt đầu có tự hủy request không? **Không**, cần consistency policy tại thao tác nhạy cảm.

## 11. Checklist triển khai

- [ ] Lấy principal đã xác thực, không tin username/owner từ client.
- [ ] TenantId được kiểm membership; owner/tenant/ACL scope nằm trong mọi query.
- [ ] List, detail, count, search, aggregation và export dùng visibility policy nhất quán.
- [ ] Không query toàn bảng rồi filter trong Java hoặc trả entity nguyên trạng.
- [ ] DTO chỉ có field được công bố; test không lộ private_note/PII.
- [ ] Pagination sau WHERE, limit bounded, sort allowlist, bind SQL parameters.
- [ ] Có negative tests cross-user, cross-tenant, IDOR và field leaks.
- [ ] Các thao tác ghi kiểm quyền server-side, affected rows, transaction và CSRF phù hợp.
- [ ] Cache/CDN/search index/async export không vượt qua scope của requester.
- [ ] Có chính sách revoke, permission freshness và fail-closed theo mức rủi ro.
- [ ] Chỉ dùng H2/password mẫu ở môi trường học tập, HTTPS với credentials thật.

**Kết luận:** Spring Security Servlet xác thực user và kiểm soát khả năng gọi endpoint, nhưng quyền tài nguyên phải được enforce trong **truy vấn bản ghi** và **projection dữ liệu trả về**. Câu hỏi quyết định là: **Ai đang gọi, được thấy row nào, nhận được field nào, và còn đường đọc nào chưa dùng cùng policy?**
