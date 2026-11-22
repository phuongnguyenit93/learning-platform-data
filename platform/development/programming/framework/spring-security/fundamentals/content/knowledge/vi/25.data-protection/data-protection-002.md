# Giới hạn truy vấn theo người dùng hoặc tổ chức hiện tại trong Spring Security

> **Chủ đề:** Bảo vệ dữ liệu ở cấp bản ghi (*record-level authorization*) trong ứng dụng Spring Boot/Spring Security. Bài học tập trung vào hai kiểu giới hạn: chỉ dữ liệu **thuộc người dùng đang đăng nhập** và chỉ dữ liệu **thuộc tổ chức mà người đó được phép truy cập**. Ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring Data JPA/H2 chạy trên Servlet stack. Đây là bài về bảo vệ **truy vấn dữ liệu**; xác thực HTTP và role chỉ là tiền đề.

## 1. Vì sao đã đăng nhập vẫn có thể xem dữ liệu của người khác?

Giả sử hệ thống có hồ sơ công việc:

| ID | Người sở hữu | Tổ chức | Nội dung |
| --- | --- | --- | --- |
| `101` | `alice` | `org-alpha` | Ghi chú riêng của Alice |
| `102` | `bob` | `org-alpha` | Ghi chú của Bob trong Alpha |
| `103` | `bob` | `org-beta` | Ghi chú của Bob trong Beta |

Alice có tài khoản hợp lệ với role `USER`. Nếu controller chỉ yêu cầu `.authenticated()` rồi gọi `repository.findById(103)`, Alice có thể thử thay ID trong URL để lấy ghi chú của Bob thuộc Beta. Đây là một dạng **Broken Object Level Authorization (BOLA)**, còn gọi là **IDOR** (*Insecure Direct Object Reference*). Dữ liệu bị lộ mặc dù Spring Security đã xác thực thành công.

**Nguyên tắc cốt lõi:** *Quyền truy cập phải là điều kiện của chính phép truy vấn hoặc thao tác dữ liệu*, dựa trên danh tính đã xác thực và phạm vi tổ chức đã được kiểm chứng. Chỉ ẩn nút, ẩn dòng ở frontend, kiểm tra `ROLE_USER` hay sử dụng UUID khó đoán đều không thay thế được phép kiểm tra này.

### 1.1. Hai chính sách phải tách rõ

**Theo người dùng (*owner-scoped*):** `/api/me/items` trả **chỉ** những mục có `ownerUserId = currentUserId`. Một thành viên cùng tổ chức không mặc nhiên được xem dữ liệu riêng của người khác.

**Theo tổ chức (*organization-scoped / tenant-scoped*):** `/api/organizations/{orgId}/items` trả các mục thuộc `organizationId = orgId`, **nhưng chỉ sau khi** server xác minh người đang đăng nhập là thành viên có quyền đọc của tổ chức đó. Trong một chính sách cộng tác, Alice và Bob có thể cùng xem các mục của `org-alpha`, nhưng không được xem `org-beta` chỉ bằng cách thay URL.

Chọn chính sách theo **loại tài nguyên và nghiệp vụ**. Một bảng có cột `organization_id` không có nghĩa tất cả thành viên đều xem được mọi bản ghi; tài liệu riêng trong tổ chức có thể cần **đồng thời** điều kiện tổ chức và người sở hữu.

| Đường truy cập | Điều kiện bắt buộc | Sai lầm phổ biến |
| --- | --- | --- |
| Danh sách “của tôi” | `owner_user_id = principal.userId` | Client gửi `?userId=bob` rồi server tin giá trị đó. |
| Chi tiết “của tôi” | `id = :id AND owner_user_id = :currentUserId` | `findById(id)` rồi trả thẳng entity. |
| Danh sách tổ chức | Kiểm tra membership/permission và `organization_id = :authorizedOrgId` | Chỉ lọc theo `orgId` lấy từ URL. |
| Chi tiết trong tổ chức | Membership/permission và `id = :id AND organization_id = :authorizedOrgId` | Kiểm membership nhưng query item toàn cục theo ID. |
| Tài nguyên riêng trong tổ chức | Membership/permission và cả `organization_id` lẫn `owner_user_id`/ACL | Ghép điều kiện sai bằng `OR` khiến phạm vi mở rộng. |

`owner_user_id` cần là định danh **ổn định** (ví dụ user ID hoặc OIDC subject đã xác minh). `created_by` dùng để audit **không nhất thiết** là chủ sở hữu hiện tại hoặc cơ sở cấp quyền; xác định rõ ý nghĩa từng cột.

## 2. Ba tầng bảo vệ: authentication, permission, data scope

Một request truy vấn dữ liệu an toàn thường đi theo trình tự:

```text
HTTP request
  |
  v
Spring Security xác thực (Authentication)
  |-- chưa hợp lệ --> 401 với API Basic/Bearer, hoặc redirect login
  v
Principal đáng tin cậy (userId/username đã xác thực)
  |
  +-- endpoint theo user: currentUserId
  |
  +-- endpoint theo org: orgId do client yêu cầu
  |        |
  |        +--> tra membership/quyền của currentUserId với orgId
  |                  |-- không được phép --> 403 (hoặc 404 theo policy)
  |                  +-- được phép --> authorizedOrgId
  v
Service xây truy vấn với ràng buộc user/org ngay ở database
  |
  +-- không tìm thấy bản ghi trong phạm vi --> 404 / danh sách rỗng
  v
DTO chỉ chứa dữ liệu được phép -> HTTP response
```

**Authentication** xác nhận danh tính. **Authorization tại endpoint** xác nhận có được gọi chức năng không. **Data scope** bảo đảm hàng dữ liệu trả về thuộc đúng phạm vi. Chỉ có `@PreAuthorize("isAuthenticated()")` hay `hasRole("USER")` chưa đủ khi những người cùng role sở hữu dữ liệu khác nhau.

Nguồn dữ liệu đáng tin cậy gồm:

- `Authentication`/`@AuthenticationPrincipal` do Spring Security đã xác thực: có thể lấy `authentication.getName()` trong ví dụ username/password.
- Membership và quyền tổ chức lưu ở database/server hoặc một nguồn quyền đã được xác minh, **không lấy từ request body như một sự thật hiển nhiên**.
- Claim `sub`, `tenant`, `org_id` trong token **chỉ đáng tin** sau khi signature, issuer, audience, expiry và chính sách ứng dụng đã được kiểm tra; token cho biết danh tính/claim, không tự động chứng minh quyền còn hiệu lực ở mọi tổ chức.

Không được lấy `userId` từ `@RequestParam`, `X-User-Id`, `X-Tenant-Id` hoặc JSON body để quyết định chủ sở hữu nếu các giá trị đó do người dùng tự đặt. `orgId` trong URL có thể là **lựa chọn tổ chức cần xem**, nhưng bắt buộc qua kiểm tra membership và gắn vào query sau khi được chấp thuận. Với tác vụ nội bộ không có HTTP principal, phải cung cấp **ngữ cảnh hệ thống được cấp quyền riêng**, không mặc định scope toàn hệ thống.

### 2.1. Thực hiện giới hạn ngay trong SQL/JPQL

**Dễ lộ dữ liệu:**

```java
// Sai cho endpoint dữ liệu riêng: chỉ lọc bằng ID.
WorkItem item = repository.findById(id).orElseThrow();
// Kiểm tra sau khi đã lấy toàn cục dễ bị bỏ sót ở nhánh khác.
```

**Đúng cho owner-scoped:**

```sql
SELECT id, title, organization_id
FROM work_items
WHERE id = :id
  AND owner_user_id = :current_user_id;
```

**Đúng cho organization-scoped sau khi đã kiểm quyền tổ chức:**

```sql
SELECT id, title, owner_user_id
FROM work_items
WHERE id = :id
  AND organization_id = :authorized_org_id;
```

Hai điều kiện cùng nằm trong **một query** giúp ngay cả ID đoán được cũng không trả bản ghi ngoài phạm vi. Tham số được bind qua JPA/JDBC; không ghép SQL thủ công từ username, orgId hoặc input của client.

**Tránh “tải toàn bộ rồi filter trong Java”**: dữ liệu ngoài phạm vi đã được đọc vào tiến trình, tốn RAM, có thể bị đưa vào log/cache hoặc vô tình ghi ra response. `Page`/`Slice`, count, sort và search càng dễ lộ dữ liệu nếu filter được thực hiện sau phân trang.

## 3. Ví dụ Java 17+ chạy được: người dùng và tổ chức

Ví dụ xây ứng dụng Spring Boot với 2 user `alice` và `bob` (HTTP Basic), 2 tổ chức `org-alpha`, `org-beta`. Alice thuộc Alpha; Bob thuộc cả Alpha và Beta. Các item được lưu trong H2/JPA. Chính sách minh họa:

- `/api/me/items` và `/api/me/items/{id}` chỉ đọc item do user hiện tại sở hữu.
- `/api/organizations/{orgId}/items` và `.../{id}` cho phép thành viên tổ chức đọc **mọi item của tổ chức đó**. Chính sách này dành cho **dữ liệu chia sẻ**, không được áp dụng cho dữ liệu riêng.
- Không cần role riêng cho mỗi tổ chức trong ví dụ; phép kiểm tra membership nằm ở database. Trong hệ thống thật nên lưu thêm vai trò và các permission READ/WRITE của từng membership.

### 3.1. Tạo dự án

Tạo các tệp sau trong dự án Gradle dùng Java 17 và Gradle 8.x.

`settings.gradle`:

```groovy
rootProject.name = 'scoped-query-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:scoped_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`ddl-auto=create-drop` chỉ dùng cho **demo H2**, không dùng để thay migration của production. Bản Spring Boot 3.3.5 được ghim để tạo ví dụ tái lập được, không ngụ ý là bản mới nhất.

### 3.2. Mã nguồn đầy đủ

Đặt **toàn bộ** mã bên dưới vào `src/main/java/demo/scope/ScopedQueryApplication.java`. Java cho phép có một `public class` và nhiều class/record package-private trong cùng tệp. Không cần tạo thêm tệp Java cho những class khác.

```java
package demo.scope;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ScopedQueryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopedQueryApplication.class, args);
    }

    @Bean
    CommandLineRunner sampleData(
            WorkItemRepository items,
            MembershipRepository memberships) {
        return args -> {
            memberships.saveAll(List.of(
                new OrgMembership("alice", "org-alpha"),
                new OrgMembership("bob", "org-alpha"),
                new OrgMembership("bob", "org-beta")
            ));

            items.saveAll(List.of(
                new WorkItem("alice", "org-alpha", "alice-private"),
                new WorkItem("bob", "org-alpha", "bob-alpha"),
                new WorkItem("bob", "org-beta", "bob-beta")
            ));
        };
    }
}

@Entity
@Table(
    name = "work_items",
    indexes = {
        @Index(name = "idx_item_owner", columnList = "owner_username,id"),
        @Index(name = "idx_item_org", columnList = "organization_id,id")
    }
)
class WorkItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_username", nullable = false)
    private String ownerUsername;

    @Column(name = "organization_id", nullable = false)
    private String organizationId;

    @Column(nullable = false)
    private String title;

    protected WorkItem() {}

    WorkItem(String ownerUsername, String organizationId, String title) {
        this.ownerUsername = ownerUsername;
        this.organizationId = organizationId;
        this.title = title;
    }

    public Long getId() { return id; }
    public String getOwnerUsername() { return ownerUsername; }
    public String getOrganizationId() { return organizationId; }
    public String getTitle() { return title; }
}

@Entity
@Table(
    name = "org_memberships",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_membership",
        columnNames = {"username", "organization_id"}
    )
)
class OrgMembership {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String username;

    @Column(name = "organization_id", nullable = false)
    private String organizationId;

    protected OrgMembership() {}

    OrgMembership(String username, String organizationId) {
        this.username = username;
        this.organizationId = organizationId;
    }
}

// Chú ý: Các method này luôn có điều kiện owner hoặc organization.
// JpaRepository vẫn có findAll/findById; tầng service không được
// dùng chúng để phục vụ endpoint dữ liệu riêng.
interface WorkItemRepository extends JpaRepository<WorkItem, Long> {
    List<WorkItem> findByOwnerUsernameOrderByIdAsc(String username);

    Optional<WorkItem> findByIdAndOwnerUsername(
        Long id, String username
    );

    List<WorkItem> findByOrganizationIdOrderByIdAsc(String organizationId);

    Optional<WorkItem> findByIdAndOrganizationId(
        Long id, String organizationId
    );
}

interface MembershipRepository extends JpaRepository<OrgMembership, Long> {
    boolean existsByUsernameAndOrganizationId(
        String username, String organizationId
    );
}

record ItemView(Long id, String title, String organizationId) {
    static ItemView from(WorkItem item) {
        return new ItemView(
            item.getId(), item.getTitle(), item.getOrganizationId()
        );
    }
}

@Service
@Transactional(readOnly = true)
class ItemQueryService {
    private final WorkItemRepository items;
    private final MembershipRepository memberships;

    ItemQueryService(
            WorkItemRepository items,
            MembershipRepository memberships) {
        this.items = items;
        this.memberships = memberships;
    }

    List<ItemView> listMine(String currentUsername) {
        return items.findByOwnerUsernameOrderByIdAsc(currentUsername)
            .stream()
            .map(ItemView::from)
            .toList();
    }

    ItemView getMine(Long id, String currentUsername) {
        return items.findByIdAndOwnerUsername(id, currentUsername)
            .map(ItemView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND)
            );
    }

    List<ItemView> listOrganization(
            String organizationId, String currentUsername) {
        requireMembership(currentUsername, organizationId);
        return items.findByOrganizationIdOrderByIdAsc(organizationId)
            .stream()
            .map(ItemView::from)
            .toList();
    }

    ItemView getOrganizationItem(
            Long id, String organizationId, String currentUsername) {
        requireMembership(currentUsername, organizationId);
        return items.findByIdAndOrganizationId(id, organizationId)
            .map(ItemView::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND)
            );
    }

    private void requireMembership(
            String username, String organizationId) {
        if (!memberships.existsByUsernameAndOrganizationId(
                username, organizationId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
    }
}

@RestController
@RequestMapping("/api")
class ItemController {
    private final ItemQueryService service;

    ItemController(ItemQueryService service) {
        this.service = service;
    }

    @GetMapping("/me/items")
    List<ItemView> mine(Authentication authentication) {
        return service.listMine(authentication.getName());
    }

    @GetMapping("/me/items/{id}")
    ItemView mineById(
            @PathVariable("id") Long id,
            Authentication authentication) {
        return service.getMine(id, authentication.getName());
    }

    @GetMapping("/organizations/{orgId}/items")
    List<ItemView> byOrganization(
            @PathVariable("orgId") String orgId,
            Authentication authentication) {
        return service.listOrganization(
            orgId, authentication.getName()
        );
    }

    @GetMapping("/organizations/{orgId}/items/{id}")
    ItemView oneInOrganization(
            @PathVariable("orgId") String orgId,
            @PathVariable("id") Long id,
            Authentication authentication) {
        return service.getOrganizationItem(
            id, orgId, authentication.getName()
        );
    }
}

@Configuration
class SecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }
}
```

### 3.3. Phân tích điểm bảo vệ

**Thứ nhất, username lấy từ principal.** Controller chỉ chuyển `authentication.getName()` sau khi Spring Security đã xác thực; route `/api/me/items` không nhận một `userId` tùy ý từ client để chọn dữ liệu người khác. Dùng username là lựa chọn đơn giản cho demo; production nên dùng user ID ổn định, vì username có thể thay đổi.

**Thứ hai, query owner luôn gắn điều kiện owner.** `findByOwnerUsernameOrderByIdAsc(username)` tương đương ý tưởng `WHERE owner_username = ? ORDER BY id`; `findByIdAndOwnerUsername(id, username)` yêu cầu **cả ID và chủ sở hữu**. Nếu Alice đoán ID của Bob, method trả `Optional.empty()` và API trả 404.

**Thứ ba, route tổ chức có hai hàng rào độc lập.** `requireMembership(...)` đối chiếu **user đã xác thực** với `orgId` ở server; sau đó `findByOrganizationId...` lọc dữ liệu bằng đúng tổ chức đã được phép đọc. Membership không được suy ra chỉ từ role `USER`; Bob và Alice có cùng role nhưng quyền tổ chức khác nhau.

**Thứ tư, 403 và 404 có chủ đích.** Không thuộc tổ chức → 403 trong chính sách demo. Có quyền đọc tổ chức nhưng mục không tồn tại **trong tổ chức đó** → 404; không tiết lộ mục có tồn tại ở tổ chức khác hay không. Một hệ thống có thể thống nhất dùng 404 cho cả hai nếu muốn giảm khả năng suy đoán tài nguyên, miễn chính sách nhất quán.

**Thứ năm, response chỉ là DTO.** `ItemView` chỉ chứa trường cần thiết. Không đưa thẳng entity JPA, quan hệ lazy, thông tin mật khẩu hoặc membership nhạy cảm vào JSON.

**Thứ sáu, dữ liệu được lọc ở repository.** Không có `items.findAll()` hoặc `items.findById(id)` trong service phục vụ HTTP. Trong hệ thống lớn nên dùng một API truy cập dữ liệu có scope mặc định, hạn chế các đường truy vấn “global” tình cờ được gọi từ controller.

### 3.4. Chạy và thử với curl

Dùng Gradle Wrapper nếu có:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Nếu chưa tạo wrapper, chạy `gradle bootRun` với Gradle 8.x tương thích. Các lệnh dưới đây chạy trong Bash có `curl` khi app ở `http://localhost:8080`:

```bash
# Chưa xác thực
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me/items

# Alice xem dữ liệu của chính mình
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice123 http://localhost:8080/api/me/items

# Alice được phép xem dữ liệu chia sẻ trong Alpha
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice123 \
  http://localhost:8080/api/organizations/org-alpha/items

# Alice không thuộc Beta
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice123 \
  http://localhost:8080/api/organizations/org-beta/items

# Bob thuộc Beta
curl -s -o /dev/null -w '%{http_code}\n' \
  -u bob:bob123 http://localhost:8080/api/organizations/org-beta/items

# Sai password
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:wrong http://localhost:8080/api/me/items
```

Kết quả HTTP dự kiến theo đúng thứ tự:

```text
401
200
200
403
200
401
```

Để nhìn dữ liệu thực, gọi:

```bash
curl -s -u alice:alice123 http://localhost:8080/api/me/items
curl -s -u alice:alice123 \
  http://localhost:8080/api/organizations/org-alpha/items
```

Lệnh đầu chỉ chứa mục `alice-private`, lệnh thứ hai chứa cả `alice-private` và `bob-alpha` theo chính sách cộng tác của tổ chức Alpha; **không lệnh nào** cho Alice xem mục `bob-beta`. ID do H2 tạo khi chạy, nên tránh phụ thuộc một ID cứng trong kịch bản thủ công.

> **Lưu ý thực tế:** Basic auth và tài khoản hard-coded chỉ phục vụ demo. HTTP Basic gửi credentials trong request; triển khai thật cần HTTPS và bảo vệ chống dò mật khẩu. Ví dụ chỉ có `GET` nên không tắt CSRF. Khi thêm thao tác thay đổi trạng thái qua browser/cookie hoặc Basic auth, phải đánh giá và xử lý CSRF thích hợp.

## 4. Kiểm thử ngăn truy cập chéo bằng MockMvc

Không chỉ test rằng người dùng “đúng” nhận 200. Phải chứng minh người dùng **không thể truy cập dữ liệu của người khác**, kể cả khi biết chính xác ID và thử đổi tổ chức.

Tạo `src/test/java/demo/scope/ScopedQuerySecurityTest.java`:

```java
package demo.scope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ScopedQuerySecurityTest {
    @Autowired MockMvc mvc;
    @Autowired WorkItemRepository items;

    private Long idOf(String title) {
        // findAll() chỉ dùng để chuẩn bị dữ liệu test,
        // tuyệt đối không phục vụ endpoint của người dùng.
        return items.findAll().stream()
            .filter(item -> item.getTitle().equals(title))
            .findFirst()
            .orElseThrow()
            .getId();
    }

    @Test
    void unauthenticatedUserIsRejected() throws Exception {
        mvc.perform(get("/api/me/items"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerListDoesNotLeakOtherUsers() throws Exception {
        mvc.perform(get("/api/me/items")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title").value("alice-private"));
    }

    @Test
    void changingQueryParameterCannotImpersonateOwner() throws Exception {
        mvc.perform(get("/api/me/items?ownerUsername=bob")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title").value("alice-private"));
    }

    @Test
    void aliceCannotReadBobsItemById() throws Exception {
        Long bobsId = idOf("bob-alpha");
        mvc.perform(get("/api/me/items/{id}", bobsId)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void memberCanReadSharedOrganizationItems() throws Exception {
        mvc.perform(get("/api/organizations/org-alpha/items")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(2)));
    }

    @Test
    void nonMemberCannotListAnotherOrganization() throws Exception {
        mvc.perform(get("/api/organizations/org-beta/items")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void itemCannotEscapeOrganizationScope() throws Exception {
        Long betaItemId = idOf("bob-beta");
        mvc.perform(get(
                "/api/organizations/org-alpha/items/{id}", betaItemId)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void authorizedMemberCanListTheirOrganization() throws Exception {
        mvc.perform(get("/api/organizations/org-beta/items")
                .with(httpBasic("bob", "bob123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title").value("bob-beta"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Hoặc `gradlew.bat test` trên Windows. Các test dùng `httpBasic(...)` nên đi qua filter xác thực và controller thật; không giả định `@WithMockUser` đủ để kiểm tra toàn bộ tích hợp.

**Các ca quan trọng nhất:** biết ID item của Bob nhưng không truy cập được từ `/me` (404); có membership Alpha nhưng không lấy item Beta bằng cách cài ID Beta vào URL Alpha (404); không có membership Beta nên không thể liệt kê Beta (403). Các trường hợp này trực tiếp kiểm tra ranh giới dữ liệu thay vì chỉ kiểm tra authentication.

## 5. Mở rộng cho phân trang, tìm kiếm, thống kê và export

Giới hạn truy vấn phải có trong **mọi** đường dữ liệu, không chỉ endpoint đọc theo ID.

### 5.1. Phân trang đúng phạm vi

Sai: đọc một trang toàn hệ thống rồi lọc `owner` bằng Java. Ví dụ trang đầu chứa 20 item của người khác, sau filter có thể còn 0 item dù người dùng có dữ liệu ở trang sau; hơn nữa tổng số item và thứ tự có thể lộ thông tin.

Đúng: tạo method repository có scope **trước khi phân trang**:

```java
// Những chữ ký sau là các phương thức bổ sung cho
// WorkItemRepository, không phải class độc lập.
Page<WorkItem> findByOwnerUsername(
    String username, Pageable pageable
);

Page<WorkItem> findByOrganizationId(
    String organizationId, Pageable pageable
);
```

Cần thêm import `org.springframework.data.domain.Page` và `Pageable`. Service phải kiểm membership tổ chức trước khi gọi method org. Với `Page`, Spring Data dùng truy vấn count bổ sung để tính tổng; **count cũng phải giữ cùng bộ lọc**. Với truy vấn JPQL custom phức tạp, xem xét `countQuery` cùng `WHERE`/`JOIN`/tenant scope.

### 5.2. Tìm kiếm và sort

Câu điều kiện nên có cấu trúc:

```sql
SELECT *
FROM work_items
WHERE organization_id = :authorized_org_id
  AND title LIKE :safe_search_pattern
ORDER BY id
LIMIT :limit OFFSET :offset;
```

`authorized_org_id` bắt buộc, không được biến mất khi `search` rỗng. Tránh xây `WHERE organization_id = :id OR title LIKE ...` vì điều kiện `OR` có thể mở rộng phạm vi ra tổ chức khác. Nếu có nhiều điều kiện, dùng dấu ngoặc rõ ràng:

```sql
WHERE organization_id = :authorized_org_id
  AND (title LIKE :q OR description LIKE :q)
```

Validate/allowlist các trường sort để không nhận tên cột SQL tùy ý; giới hạn kích thước trang để tránh lạm dụng. Sử dụng parameter binding và quy tắc escape của `LIKE` khi nhận ký tự `%`/`_` từ người dùng, tránh kết quả tìm kiếm rộng ngoài dự kiến.

### 5.3. Aggregate, count, dashboard và export

Một `count(*)` không có `WHERE organization_id = :authorized_org_id` vẫn có thể lộ quy mô dữ liệu tổ chức khác. `SUM`, `GROUP BY`, chart, CSV/XLSX export, report jobs, autocomplete, search index và API batch cũng cần cùng chính sách. Không được dùng endpoint export riêng gọi `findAll()` vì “chỉ export dữ liệu”.

Nếu truy vấn qua `JOIN`, lọc tenant ở **mọi bảng có ranh giới bảo mật** hoặc xác minh quan hệ xuyên tenant không thể tồn tại. Ví dụ item có `organization_id = alpha` nhưng tham chiếu đến `customer_id` thuộc Beta thì chỉ lọc item chưa chắc đủ; cần ràng buộc foreign key/quan hệ và kiểm dữ liệu liên quan.

## 6. Cập nhật, xóa và tạo mới cũng phải có scope

Bảo vệ các query đọc là bắt buộc nhưng chưa đủ. **Update/delete/batch** phải dùng chính sách tương đương; không xác thực quyền trên `GET` rồi cho phép `PATCH` hoặc `DELETE` truy cập toàn cục.

### 6.1. Conditional write trong một câu lệnh

Ví dụ JPQL bổ sung cho repository; đây là **đoạn minh họa tích hợp**, chưa phải endpoint độc lập:

```java
@Modifying
@Query("""
    update WorkItem w
       set w.title = :newTitle
     where w.id = :id
       and w.ownerUsername = :currentUsername
    """)
int renameOwned(
    @Param("id") Long id,
    @Param("currentUsername") String currentUsername,
    @Param("newTitle") String newTitle
);
```

Cần import `org.springframework.data.jpa.repository.Modifying`, `Query` và `org.springframework.data.repository.query.Param`, gọi method trong transaction ghi (`@Transactional`, không phải readOnly). **Kết quả `0` hàng** nghĩa là không tìm thấy bản ghi được phép thay đổi; API có thể trả 404. Bulk update JPQL bỏ qua một số lifecycle callbacks và có thể làm persistence context cũ, vì thế cần kiểm tra quy tắc domain/audit và làm mới context nếu cần.

### 6.2. Tạo mới và đổi tổ chức

Khi tạo item, **không nhận `ownerUsername` từ request như chủ sở hữu được tin cậy**; gán owner từ principal phía server. Nếu client chọn `organizationId`, xác minh quyền tạo (`CREATE`) trong tổ chức trước khi persist. Khi đổi organization hoặc owner, thực hiện chính sách **chuyển quyền sở hữu** tường minh, kiểm quyền ở cả nguồn và đích, không coi đó là cập nhật trường thông thường. Nếu lưu child/attachment, child phải gắn với cùng phạm vi item cha.

### 6.3. Tránh thời điểm kiểm quyền và ghi bị tách rời

Mẫu `findById(id)`, kiểm membership, rồi transaction khác `save(entity)` có thể gặp tình trạng quyền hoặc tổ chức thay đổi ở giữa (**TOCTOU**). Với thao tác nhạy cảm, cân nhắc conditional `UPDATE ... WHERE id = ? AND organization_id = ?`, khóa/phiên bản `@Version`, transaction thích hợp, hoặc xác minh quyền nhất quán tại thời điểm ghi. Không được tin rằng quyền đã kiểm ở một request trước còn có hiệu lực mãi.

## 7. Chọn “tổ chức hiện tại” an toàn

Một người có thể thuộc nhiều tổ chức. “Tổ chức hiện tại” phải là **phạm vi đã chọn và đã xác minh**:

1. Client yêu cầu xem `org-alpha` (trong URL, session hoặc lựa chọn UI).
2. Server xác thực user hiện tại.
3. Server kiểm user còn là member và có permission cần thiết của `org-alpha`.
4. Chỉ sau đó mới đưa **authorizedOrgId** vào service/repository query.
5. Nếu không có membership, thiếu quyền, org không hợp lệ hoặc context mơ hồ: **fail closed** (403/404), không tự bỏ điều kiện `WHERE` để “trả tất cả”.

**Không dùng HTTP header `X-Tenant-Id` hoặc query param `tenantId` như quyền cấp sẵn**: đó chỉ là giá trị client yêu cầu, trừ khi đến từ một thành phần trusted gateway có xác minh và toàn bộ boundary đã được bảo vệ. Không chỉ dùng `ROLE_ADMIN` toàn cục để cấp quyền mọi tổ chức; đặc quyền support/super-admin cần một policy và audit riêng.

Nếu dùng JWT có claim `org_id`, server phải kiểm chữ ký/token đầy đủ và quyết định claim đó đại diện tổ chức được chọn, danh sách quyền tại lúc phát hành hay chỉ một hint. Khi membership bị thu hồi, claim cũ có thể stale; cần chính sách TTL, revocation hoặc tra quyền hiện hành theo mức rủi ro.

**Multi-tenant bằng shared database:** `organization_id` là ranh giới dữ liệu, nên có index, foreign key, unique constraint theo tổ chức (ví dụ `(organization_id, external_code)`), và ngăn record tham chiếu qua tenant sai. Nếu database hỗ trợ Row-Level Security (như PostgreSQL RLS), có thể dùng làm lớp bảo vệ bổ sung. Tuy nhiên app phải truyền tenant context đúng theo **transaction/connection**, tránh rò rỉ khi connection pool tái sử dụng kết nối; RLS không thay thế việc xác minh user được quyền chọn tenant.

## 8. Những lỗi bảo mật phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `findById(id)` trong service của endpoint riêng | IDOR/BOLA: đoán ID xem bản ghi khác | `findByIdAndOwner...` hoặc `findByIdAndOrganizationId...`. |
| `findAll()` rồi `.filter(...)` | Lộ qua log/cache, paging/count sai, tốn tài nguyên | Đưa điều kiện vào query DB. |
| Tin `userId`/`orgId` từ client | Giả mạo principal hoặc đổi tenant | Lấy user từ SecurityContext, xác minh org membership. |
| Dùng `hasRole("USER")` cho mọi truy vấn | Người cùng role nhìn thấy dữ liệu nhau | Authorization theo owner/org/ACL ở data layer. |
| `WHERE tenant=:id OR ...` | `OR` có thể mở rộng dữ liệu cross-tenant | Tenant predicate bắt buộc với nhóm điều kiện trong ngoặc. |
| Check membership nhưng đọc item bằng ID toàn cục | Member Alpha đọc được ID item Beta | Membership **và** `WHERE organization_id=:orgId`. |
| Chỉ bảo vệ GET | PATCH/DELETE/export vẫn lộ/ghi chéo | Scope mọi thao tác và bulk query. |
| Cache key chỉ theo `itemId` | Cache của người/tenant này phục vụ cho người khác | Cache key gồm tenant/permission scope hoặc cache kết quả đã được authz cẩn thận. |
| `ThreadLocal` tenant không được reset | Request tiếp theo nhận tenant context cũ | Ưu tiên truyền scope tường minh; nếu dùng thread context thì `try/finally`, xử lý async. |
| “Không tìm thấy org” thì bỏ lọc | Fail open và trả dữ liệu toàn cục | Thất bại đóng: 403/404 hoặc danh sách trống theo policy. |

### 8.1. Async, job nền, event consumer, webhook

`Authentication` trong `SecurityContextHolder` thường gắn với thread của request, **không bảo đảm có sẵn trong `@Async`, scheduler, queue consumer hoặc job nền**. Không tự lấy `SecurityContextHolder.getContext().getAuthentication().getName()` trong mọi nơi rồi giả định giá trị luôn hợp lệ. Với tác vụ nền, truyền một scope explicit đã được tạo hợp lệ (user/tenant/permissions hoặc service-account policy), và **kiểm quyền lại khi cần**. Không chuyển scope người dùng sang mọi job nền rồi vô ý thực hiện thao tác toàn hệ thống.

### 8.2. Cache và search index

Nếu một user của Alpha truy vấn cache có key `"items:page:1"` không kèm tenant, user Beta có thể nhận dữ liệu cache Alpha. Cần key có `authorizedOrgId`, các tham số query và khi cần cả user/permission version. Với Elasticsearch hoặc index/search engine, **query filter theo tenant phải chạy tại search engine**, kể cả đề xuất/autocomplete và thống kê; không chỉ lọc phần kết quả trả về.

### 8.3. Quyền của người dùng thay đổi khi đang đăng nhập

User rời tổ chức hoặc bị khóa quyền truy cập; session/JWT cũ có thể vẫn hợp lệ đến khi hết hạn. Nếu mọi request chỉ dựa trên claim membership cũ, dữ liệu có thể tiếp tục lộ. Kiểm membership hiện tại, TTL phù hợp, revocation và invalidation tùy chính sách rủi ro. Với dữ liệu nhạy cảm, kiểm quyền ở thời điểm thực thi truy vấn.

## 9. Checklist kiểm thử và giám sát

Trước khi phát hành một endpoint đọc/ghi dữ liệu có owner/tenant, kiểm tra:

- [ ] Principal được xác thực và lấy từ nguồn server tin cậy; không thể giả bằng body/header.
- [ ] Policy owner, organization, private-in-org, role/permission được định nghĩa rõ.
- [ ] Org do client chọn được **xác minh membership + permission** trước khi truy vấn.
- [ ] Mọi query list/detail/search/page/count/aggregate/export đều có scope ở DB.
- [ ] ID ngoài phạm vi trả 404/403 đúng policy, không rò rỉ payload của record khác.
- [ ] Update/delete/create/bulk và child resources dùng cùng phạm vi.
- [ ] Test user A truy cập ID của B cùng tổ chức; user A truy cập tổ chức khác; thử đổi URL/query param.
- [ ] Kiểm test `Page.totalElements`, filter search, sort và cache cross-tenant.
- [ ] Có quy tắc xử lý khi membership bị thu hồi, token cũ, job nền hoặc context vắng mặt.
- [ ] Logs/audit lưu user ID, org ID, request ID và quyết định quyền phù hợp, không ghi token/password/dữ liệu bí mật.

**Test âm tính quan trọng hơn chỉ kiểm tra 200:** cần cố tình dùng credentials của Alice để gọi ID của Bob và tài nguyên Beta. Nếu chỉ test `@WithMockUser` cùng một account hoặc mọi dữ liệu test đều thuộc một tenant, bài kiểm thử gần như không bắt được lỗ hổng scope.

## 10. Bài tập tự đánh giá

**Tình huống A:** `/api/orders/{id}` yêu cầu `.authenticated()` rồi gọi `findById(id)`. Người dùng thay ID để xem đơn hàng của user khác.  
**Phân tích:** authentication thành công nhưng thiếu object-level authorization. Dùng `findByIdAndOwnerUserId(id, currentUserId)` hoặc chính sách quyền tương đương.

**Tình huống B:** `/api/organizations/{orgId}/reports` lọc `orgId` đúng URL nhưng không kiểm thành viên.  
**Phân tích:** attacker có thể đổi URL sang tổ chức khác. Phải kiểm membership/READ permission trước rồi query theo authorized org.

**Tình huống C:** Alice thuộc Alpha; item ID 103 thuộc Beta. API kiểm Alice là member Alpha rồi gọi `findById(103)`.  
**Phân tích:** vẫn có thể leak Beta. Truy vấn phải chứa **cả** `id=103` và `organizationId=Alpha`, không chỉ một phép kiểm membership tách rời.

**Tình huống D:** Query `WHERE organization_id=:id OR title LIKE '%urgent%'`.  
**Phân tích:** nó có thể trả item của tổ chức khác nếu title khớp. Đúng phải là `organization_id=:authorizedId AND (điều kiện tìm kiếm...)`.

**Tình huống E:** Dữ liệu đã lọc theo tổ chức trong `List<Item>`, nhưng API tổng số gọi `count()` toàn bảng.  
**Phân tích:** count vẫn lộ thống kê cross-tenant. Mọi truy vấn phụ (`countQuery`, `SUM`, autocomplete, export) phải áp dụng cùng phạm vi.

**Tình huống F:** Dữ liệu user có `created_by=alice`, nhưng đã chuyển quyền sở hữu cho Bob.  
**Phân tích:** `created_by` là audit, không còn quyết định ai được đọc nếu policy dựa trên `owner_user_id`. Phải dùng cột/quy tắc ownership thật.

## 11. Ghi nhớ và tài liệu tham khảo

**Công thức an toàn:** `authenticated principal` → `authorized user/org scope` → `database query with mandatory owner/tenant predicate` → `DTO`. Spring Security xử lý xác thực và kiểm quyền ở lớp HTTP; ứng dụng vẫn phải thực thi quyền ở **cấp hàng dữ liệu**. Một API bảo mật đúng không chỉ ngăn truy cập khi chưa login mà còn ngăn **người đã login** xem dữ liệu họ không sở hữu hoặc không được tổ chức cho phép.

Tài liệu chính thức:

- [Spring Security — Authentication Architecture và SecurityContext](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data — Defining Query Methods, paging và sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [OWASP API Security — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
