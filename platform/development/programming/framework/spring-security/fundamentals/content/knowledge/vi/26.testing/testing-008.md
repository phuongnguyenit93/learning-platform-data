# Kiểm thử cho phép, từ chối và quyền sở hữu tài nguyên trong Spring Security

> **Phạm vi:** Kiểm thử authorization và quyền sở hữu từng bản ghi (*object-level authorization*) trong ứng dụng Spring Boot 3.x, Spring Security 6.x, Spring MVC (Servlet stack), Java 17+, JUnit 5, MockMvc và Spring Data JPA. Bài học kết hợp kiểm thử **được phép**, **bị từ chối** và **không được truy cập tài nguyên của người khác**. Ví dụ dùng HTTP Basic để dễ tái hiện; cùng nguyên tắc có thể áp dụng với form login, session hoặc Bearer token sau khi điều chỉnh cách tạo principal.

## 1. Phân biệt ba điều kiện cần kiểm thử

Một ứng dụng đã cấu hình `authenticated()` hoặc `hasRole("USER")` vẫn có thể làm lộ dữ liệu: Alice và Bob đều có role `USER`, nhưng Alice không được phép đọc hay sửa tài nguyên riêng của Bob. Vì vậy test bảo mật cần kiểm **ai gửi request**, **họ có quyền dùng chức năng không**, và **bản ghi được truy cập có thuộc phạm vi của họ không**.

| Loại kiểm thử | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Cho phép (*allow*)** | Người dùng hợp lệ và đủ quyền có thực hiện được hành động không? | Alice đọc ghi chú của Alice → 200; admin xem báo cáo quản trị → 200. |
| **Từ chối (*deny*)** | Người chưa xác thực hoặc thiếu role/authority có bị chặn không? | Không credentials → 401 với HTTP Basic; Alice gọi `/api/admin/summary` → 403. |
| **Quyền sở hữu tài nguyên (*ownership*)** | Người dùng đã đăng nhập có bị chặn khi đổi ID sang bản ghi của người khác không? | Alice gọi `/api/items/{bobId}` → 404 theo chính sách che sự tồn tại của tài nguyên. |

**Authentication** chứng minh danh tính. **Authorization** quyết định được thực hiện hành động. **Ownership** là một điều kiện authorization ở **cấp đối tượng/bản ghi**, độc lập với việc hai người có cùng role hay không.

Một endpoint như `GET /api/items/{id}` chỉ dùng:

```java
.requestMatchers("/api/items/**").authenticated()
```

mới chứng minh client phải đăng nhập; nó **không tự kiểm** bản ghi có thuộc người đăng nhập. Nếu service dùng `repository.findById(id)` để trả dữ liệu, người dùng có thể đổi ID và đọc thông tin người khác. Lỗ hổng này thường được gọi **Broken Object Level Authorization (BOLA)** hoặc **IDOR**.

### 1.1. Không lẫn lộn 401, 403 và 404

| Phản hồi | Ý nghĩa trong ví dụ HTTP Basic | Trường hợp test |
| --- | --- | --- |
| **401 Unauthorized** | Chưa cung cấp credentials hợp lệ hoặc authentication thất bại. | Anonymous, sai mật khẩu. |
| **403 Forbidden** | Đã xác thực nhưng không đủ authority để dùng chức năng; hoặc request bị CSRF từ chối. | Role USER gọi đường ADMIN; POST/PATCH/DELETE thiếu CSRF. |
| **404 Not Found** | Không tìm thấy tài nguyên **trong phạm vi người dùng có quyền xem**. | Alice thử ID tài nguyên của Bob; một ID không tồn tại. |
| **200 OK** | Đọc hoặc cập nhật tài nguyên thành công. | Alice đọc hoặc đổi tên mục của mình. |
| **201 Created** | Tạo tài nguyên thành công, server tự gán người sở hữu. | Alice POST tạo mục mới với CSRF hợp lệ. |
| **204 No Content** | Xóa tài nguyên thành công và không trả body. | Alice DELETE mục của chính mình. |

Đối với tài nguyên ngoài phạm vi, hệ thống có thể chọn **403 hoặc 404 theo chính sách**. Ví dụ trong bài cố tình dùng **404** cho cả “ID không tồn tại” và “ID tồn tại nhưng thuộc người khác”, nhằm hạn chế tiết lộ sự tồn tại của dữ liệu. Vì thế **không ép mọi lỗi thiếu ownership thành 403**. Điều cần chứng minh là response không chứa dữ liệu ngoài quyền và không có thay đổi trái phép.

Với **form login**, anonymous có thể bị chuyển hướng đến trang đăng nhập thay cho 401; với OAuth2 Bearer, token hỏng thường trả 401. Viết assertion theo cơ chế auth mà ứng dụng thực sự đang dùng.

## 2. Thiết kế ma trận test trước khi viết code

Tạo hai người dùng bình thường `alice` và `bob` với cùng `ROLE_USER`; một admin có `ROLE_ADMIN`. Tạo ít nhất hai bản ghi có **ID khác nhau**: `alice-private` thuộc Alice và `bob-private` thuộc Bob. Khi test quyền sở hữu, phải dùng **credentials Alice + ID Bob** và kiểm tra từ chối. Một fixture chỉ có một user không thể phát hiện lỗi rò rỉ giữa các user.

| HTTP request | Danh tính | Kỳ vọng |
| --- | --- | --- |
| `GET /api/public` | Anonymous | 200. |
| `GET /api/items` | Anonymous | 401. |
| `GET /api/items` | Alice, mật khẩu sai | 401. |
| `GET /api/admin/summary` | Alice (`ROLE_USER`) | 403. |
| `GET /api/admin/summary` | Admin (`ROLE_ADMIN`) | 200. |
| `GET /api/items` | Alice | 200; danh sách chỉ chứa item của Alice. |
| `GET /api/items/{aliceId}` | Alice | 200; đúng dữ liệu Alice. |
| `GET /api/items/{bobId}` | Alice | 404 theo chính sách owner-scoped. |
| `GET /api/items/{bobId}` | Bob | 200. |
| `GET /api/items?ownerUsername=bob` | Alice | Vẫn chỉ trả dữ liệu Alice; query param không được chọn chủ sở hữu. |
| `GET /api/items/{bobId}` | Admin không sở hữu | 404: role ADMIN không tự vượt quyền owner khi chưa có chính sách. |
| `POST /api/items` | Alice, thiếu CSRF | 403 theo cấu hình CSRF mặc định trong demo. |
| `POST /api/items` | Alice, CSRF hợp lệ | 201; owner được server gán là Alice. |
| `PATCH /api/items/{bobId}` | Alice, có CSRF | 404; item Bob không bị sửa. |
| `DELETE /api/items/{bobId}` | Alice, có CSRF | 404; item Bob vẫn tồn tại. |
| `PATCH /api/items/{aliceId}` | Alice, có CSRF | 200; chỉ item Alice được đổi. |
| `DELETE /api/items/{aliceId}` | Alice, có CSRF | 204; chỉ item Alice được xóa. |

**Test dương tính và âm tính phải đi đôi:** nếu chỉ test request bị từ chối, một cấu hình `denyAll()` sai cũng có thể làm mọi test “xanh”. Nếu chỉ test request được phép, một cấu hình `permitAll()` sai cũng có thể làm mọi test “xanh”. Cần ít nhất một case đúng quyền và một case thiếu quyền trên cùng nhóm endpoint.

### 2.1. Mỗi test cần kiểm đúng tầng

- **Filter-level:** 401 khi anonymous, 403 khi thiếu role hoặc sai CSRF.
- **Service/repository-level:** truy vấn thực sự gắn `owner` hoặc `tenant`, không dùng `findById` toàn hệ thống cho endpoint riêng.
- **Object-level:** Alice không truy cập được bản ghi Bob, dù đoán được ID.
- **Mutation-level:** POST/PUT/PATCH/DELETE phải bị chặn khi sai quyền; response bị chặn **và database không đổi**.
- **Serialization-level:** response trả DTO vừa đủ, không gửi entity toàn bộ hoặc dữ liệu của bản ghi ngoài scope.

Một `@WithMockUser` có thể giúp giả principal để kiểm rule, nhưng **không tự chứng minh** password, provider hay mapping `SecurityFilterChain` thực sự chạy. Ví dụ tích hợp dùng `httpBasic(...)` để credentials đi qua filter và provider.

## 3. Cấu trúc ứng dụng mẫu Java 17+

Ví dụ gồm HTTP Basic, JPA/H2 và một bảng `work_items` có `owner_username`. Tài khoản:

- `alice` / `alice123` — `ROLE_USER`.
- `bob` / `bob123` — `ROLE_USER`.
- `admin` / `admin123` — `ROLE_ADMIN`.

Chính sách:

1. Ai cũng gọi được `GET /api/public`.
2. `/api/admin/**` yêu cầu `ROLE_ADMIN`.
3. `/api/items` và `/api/items/{id}` yêu cầu đăng nhập.
4. Service lấy **username đã xác thực** từ `Authentication`, rồi chỉ tìm/sửa/xóa item với **đồng thời** `id` và `owner_username`.
5. Dữ liệu ngoài phạm vi trả **404**; không có bypass owner cho admin.
6. Spring Security CSRF giữ nguyên mặc định, nên POST/PATCH/DELETE trong MockMvc phải gửi CSRF token hợp lệ.

### 3.1. Tệp Gradle

`settings.gradle`:

```groovy
rootProject.name = 'ownership-security-test'
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

Spring Boot **3.3.5** là phiên bản minh họa được ghim để cấu hình dễ tái lập, **không phải khẳng định bản mới nhất**. Spring Boot quản lý các phiên bản Spring Security Test/JPA/JUnit tương thích; không khai báo riêng version `spring-security-test` khi dùng BOM này.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:ownership_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`create-drop` chỉ dùng cho demo/test với H2. Production nên dùng migrations (Flyway/Liquibase), kiểm soát schema và quyền database chặt chẽ. Dùng JDK 17+ và một bản Gradle 8.x tương thích với Spring Boot 3.3.x.

### 3.2. Mã ứng dụng đầy đủ

Tạo **một** tệp `src/main/java/demo/ownership/OwnershipSecurityApplication.java`. Java cho phép một public class có tên đúng như tệp và nhiều class package-private cùng package; nên đoạn code dưới đây là chương trình Spring Boot hoàn chỉnh cho demo.

```java
package demo.ownership;

import java.util.List;
import java.util.Optional;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

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
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class OwnershipSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipSecurityApplication.class, args);
    }

    @Bean
    CommandLineRunner exampleData(WorkItemRepository items) {
        return args -> items.saveAll(List.of(
            new WorkItem("alice", "alice-private"),
            new WorkItem("bob", "bob-private")
        ));
    }
}

@Entity
@Table(
    name = "work_items",
    indexes = @Index(name = "idx_work_item_owner",
                     columnList = "owner_username")
)
class WorkItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_username", nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected WorkItem() {}

    WorkItem(String ownerUsername, String title) {
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

// Repository cung cấp cả thao tác CRUD chung và truy vấn có giới hạn.
// Service bảo vệ API phải dùng truy vấn kèm owner.
interface WorkItemRepository extends JpaRepository<WorkItem, Long> {
    List<WorkItem> findByOwnerUsernameOrderByIdAsc(
        String ownerUsername
    );

    Optional<WorkItem> findByIdAndOwnerUsername(
        Long id, String ownerUsername
    );
}

record ItemView(Long id, String title) {
    static ItemView from(WorkItem item) {
        return new ItemView(item.getId(), item.getTitle());
    }
}

record CreateItemRequest(String title) {}

record RenameItemRequest(String title) {}

@Service
class WorkItemService {
    private final WorkItemRepository items;

    WorkItemService(WorkItemRepository items) {
        this.items = items;
    }

    @Transactional(readOnly = true)
    public List<ItemView> listMine(String currentUsername) {
        return items.findByOwnerUsernameOrderByIdAsc(currentUsername)
            .stream()
            .map(ItemView::from)
            .toList();
    }

    @Transactional(readOnly = true)
    public ItemView getMine(Long id, String currentUsername) {
        return ItemView.from(requireOwned(id, currentUsername));
    }

    @Transactional
    public ItemView createMine(
            String currentUsername, String newTitle) {
        validateTitle(newTitle);
        WorkItem item = items.save(
            new WorkItem(currentUsername, newTitle)
        );
        return ItemView.from(item);
    }

    @Transactional
    public ItemView renameMine(
            Long id, String currentUsername, String newTitle) {
        validateTitle(newTitle);
        WorkItem item = requireOwned(id, currentUsername);
        item.rename(newTitle); // JPA dirty checking trong transaction
        return ItemView.from(item);
    }

    @Transactional
    public void deleteMine(Long id, String currentUsername) {
        WorkItem item = requireOwned(id, currentUsername);
        items.delete(item);
    }

    private WorkItem requireOwned(Long id, String username) {
        return items.findByIdAndOwnerUsername(id, username)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND)
            );
    }

    private void validateTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "title must not be blank"
            );
        }
    }
}

@RestController
@RequestMapping("/api")
class WorkItemController {
    private final WorkItemService service;

    WorkItemController(WorkItemService service) {
        this.service = service;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/admin/summary")
    public String adminSummary() {
        return "admin-summary";
    }

    @GetMapping("/items")
    public List<ItemView> list(Authentication authentication) {
        return service.listMine(authentication.getName());
    }

    @GetMapping("/items/{id}")
    public ItemView getById(
            @PathVariable("id") Long id,
            Authentication authentication) {
        return service.getMine(id, authentication.getName());
    }

    @PostMapping("/items")
    @ResponseStatus(HttpStatus.CREATED)
    public ItemView create(
            @RequestBody CreateItemRequest body,
            Authentication authentication) {
        return service.createMine(
            authentication.getName(), body.title()
        );
    }

    @PatchMapping("/items/{id}")
    public ItemView rename(
            @PathVariable("id") Long id,
            @RequestBody RenameItemRequest body,
            Authentication authentication) {
        return service.renameMine(
            id, authentication.getName(), body.title()
        );
    }

    @DeleteMapping("/items/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable("id") Long id,
            Authentication authentication) {
        service.deleteMine(id, authentication.getName());
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
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error", "/api/public").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);
        return http.build();
    }
}
```

### 3.3. Những chi tiết bảo mật phải hiểu

**Lấy owner từ principal.** Controller dùng `authentication.getName()` do Spring Security đã xác thực, không nhận `ownerUsername` từ query param hay body như nguồn quyền truy cập. Với ứng dụng thực, ưu tiên **ID user ổn định** từ principal/`sub` đã kiểm chứng thay cho username có thể đổi.

**Dùng query gắn owner.** `findByIdAndOwnerUsername(id, username)` tương đương yêu cầu **cả ID lẫn chủ sở hữu phải khớp** trong SQL. Nếu ID thuộc người khác, query không trả bản ghi, service trả 404. `findByOwnerUsernameOrderByIdAsc` chỉ liệt kê dữ liệu của principal; không tải toàn bộ rồi lọc trong Java.

**Role và ownership là hai điều kiện khác nhau.** Security chain dùng `hasRole("ADMIN")` cho URL admin. Nhưng API `/api/items/{id}` vẫn theo chủ sở hữu ở service. Trong policy này, account `admin` không tự đọc được item của Bob. Nếu muốn có tác vụ support truy cập xuyên owner, phải khai báo **permission riêng, có giới hạn và audit**, thay vì âm thầm bỏ điều kiện owner.

**Chặn cả thao tác ghi.** `renameMine` và `deleteMine` tìm bản ghi **trong phạm vi owner** trước khi đổi/xóa. Test phải xác nhận tài nguyên Bob **không thay đổi** khi Alice dùng ID Bob. Chỉ có status 404 là chưa đủ nếu code vẫn có side effect trước khi trả lỗi.

**Tạo mới an toàn.** `createMine` gán owner từ `Authentication`; DTO chỉ chứa `title`. Client không được quyết định owner theo một trường tùy ý. Hệ thống thật nên cấu hình rõ cách xử lý trường JSON không biết, validate input và giới hạn độ dài title.

**DTO bảo vệ response.** `ItemView` chỉ chứa ID và tiêu đề; không serialize thẳng entity JPA hoặc password/metadata nhạy cảm. Chính sách này hạn chế phơi bày dữ liệu không cần thiết dù chủ sở hữu được phép đọc.

**CSRF vẫn bật.** Trong ví dụ HTTP Basic, Spring Security mặc định yêu cầu CSRF token cho các HTTP method thay đổi trạng thái. Test POST/PATCH/DELETE với `.with(csrf())` để kiểm quyền sau khi CSRF đã hợp lệ; có test riêng cho trường hợp thiếu token. Đừng tắt CSRF chỉ để test có status 200.

**Không dùng password hard-coded trong production.** Ví dụ cố ý dùng user demo để minh họa test. Triển khai thật cần HTTPS, nguồn user tin cậy, lưu hash và cơ chế chống brute-force. CSRF và cơ chế bảo vệ phụ thuộc mô hình credentials thực tế.

## 4. Kiểm thử HTTP và database bằng `spring-security-test`

Tạo `src/test/java/demo/ownership/OwnershipSecurityTest.java`. Đây là test tích hợp chạy cùng Spring Boot application, MockMvc, SecurityFilterChain thực và H2 database. Mỗi test tạo lại **hai tài nguyên thuộc hai người khác nhau** để các case độc lập và không phụ thuộc ID được sinh ra là `1`, `2` hay giá trị khác.

```java
package demo.ownership;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
    .delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
    .get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
    .patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
    .post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .status;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipSecurityTest {
    @Autowired MockMvc mvc;
    @Autowired WorkItemRepository items;

    @BeforeEach
    void resetData() {
        items.deleteAll();
        items.saveAll(List.of(
            new WorkItem("alice", "alice-private"),
            new WorkItem("bob", "bob-private")
        ));
    }

    private Long idFor(String owner) {
        // Chỉ dùng helper này để lấy ID fixture trong test.
        return items.findByOwnerUsernameOrderByIdAsc(owner)
            .get(0)
            .getId();
    }

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedListRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/items"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/items")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userRoleCannotUseAdminFunction() throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanUseAdminFunction() throws Exception {
        mvc.perform(get("/api/admin/summary")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-summary"));
    }

    @Test
    void aliceListContainsOnlyHerItems() throws Exception {
        mvc.perform(get("/api/items")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title")
                .value("alice-private"));
    }

    @Test
    void aliceCanReadHerItem() throws Exception {
        mvc.perform(get("/api/items/{id}", idFor("alice"))
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("alice-private"));
    }

    @Test
    void bobCanReadHisItem() throws Exception {
        mvc.perform(get("/api/items/{id}", idFor("bob"))
                .with(httpBasic("bob", "bob123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("bob-private"));
    }

    @Test
    void aliceCannotReadBobsItemEvenWhenSheKnowsTheId()
            throws Exception {
        mvc.perform(get("/api/items/{id}", idFor("bob"))
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void queryParameterCannotChangeTheAuthenticatedOwner()
            throws Exception {
        mvc.perform(get("/api/items?ownerUsername=bob")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$", hasSize(1)))
            .andExpect(jsonPath("$[0].title")
                .value("alice-private"));
    }

    @Test
    void adminRoleDoesNotImplicitlyBypassItemOwnership()
            throws Exception {
        mvc.perform(get("/api/items/{id}", idFor("bob"))
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void itemIdOutsideTheAuthorizedScopeReturns404()
            throws Exception {
        mvc.perform(get("/api/items/{id}", 999999L)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("alice", "alice123"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"new-item\"}"))
            .andExpect(status().isForbidden());

        assertThat(items.findByOwnerUsernameOrderByIdAsc("alice"))
            .hasSize(1);
    }

    @Test
    void invalidCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("alice", "alice123"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"new-item\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validOwnerCanCreateWithCsrf() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("alice", "alice123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"created-by-alice\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title")
                .value("created-by-alice"));

        assertThat(items.findByOwnerUsernameOrderByIdAsc("alice"))
            .extracting(WorkItem::getTitle)
            .contains("created-by-alice");
        assertThat(items.findByOwnerUsernameOrderByIdAsc("bob"))
            .extracting(WorkItem::getTitle)
            .containsExactly("bob-private");
    }

    @Test
    void aliceCannotRenameBobsItem() throws Exception {
        Long bobId = idFor("bob");

        mvc.perform(patch("/api/items/{id}", bobId)
                .with(httpBasic("alice", "alice123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"stolen-title\"}"))
            .andExpect(status().isNotFound());

        assertThat(items.findById(bobId).orElseThrow().getTitle())
            .isEqualTo("bob-private");
    }

    @Test
    void bobCanRenameHisItem() throws Exception {
        Long bobId = idFor("bob");

        mvc.perform(patch("/api/items/{id}", bobId)
                .with(httpBasic("bob", "bob123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"bob-updated\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                .value("bob-updated"));

        assertThat(items.findById(bobId).orElseThrow().getTitle())
            .isEqualTo("bob-updated");
    }

    @Test
    void aliceCannotDeleteBobsItem() throws Exception {
        Long bobId = idFor("bob");

        mvc.perform(delete("/api/items/{id}", bobId)
                .with(httpBasic("alice", "alice123"))
                .with(csrf()))
            .andExpect(status().isNotFound());

        assertThat(items.findById(bobId)).isPresent();
    }

    @Test
    void aliceCanDeleteHerItem() throws Exception {
        Long aliceId = idFor("alice");

        mvc.perform(delete("/api/items/{id}", aliceId)
                .with(httpBasic("alice", "alice123"))
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertThat(items.findById(aliceId)).isEmpty();
        assertThat(items.findByOwnerUsernameOrderByIdAsc("bob"))
            .hasSize(1);
    }
}
```

### 4.1. Tại sao đây là integration test thực chất?

- `@SpringBootTest` nạp application context đầy đủ, gồm `SecurityConfiguration`, filter chain, user service, password encoder, controller, service và JPA/H2.
- `@AutoConfigureMockMvc` bật MockMvc với các filter mặc định (không đặt `addFilters=false`). Request được xử lý trong cùng tiến trình mà **không cần mở cổng TCP**.
- `.with(httpBasic(...))` tạo Basic credentials thật trên request. Authentication filter/provider phải xử lý mật khẩu đúng hoặc sai; đây là khác biệt với fake principal.
- `.with(csrf())` cho phép kiểm tra authorization của request ghi sau khi CSRF hợp lệ. Thiếu/sai token được test thành ca riêng.
- `@BeforeEach` xóa và tạo lại hai fixture độc lập; test không phụ thuộc thứ tự chạy hoặc ID tự tăng. Các thao tác xóa/sửa trong test trước không làm sai dữ liệu test sau.
- Không chỉ assert HTTP response: các test bị từ chối còn kiểm **database không đổi** (`bob-private` vẫn tồn tại, không thành `stolen-title`).
- Không dùng `@WithMockUser` cho ca sai mật khẩu, vì annotation này bỏ qua quá trình xác minh credential.

**Lưu ý về fixture:** `items.findById(...)` hoặc `deleteAll()` trong lớp test chỉ để **thiết lập và kiểm chứng** dữ liệu thử nghiệm. Các endpoint business vẫn chỉ dùng `findByIdAndOwnerUsername(...)`. Trong code thực tế, cân nhắc test data builders, transactional fixtures hoặc một DB container nếu SQL/locking/migration phụ thuộc DB production; H2 không tái hiện toàn bộ hành vi PostgreSQL/MySQL.

### 4.2. Chạy test và ứng dụng

Nếu dự án có Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Trên Windows:

```bat
gradlew.bat test
gradlew.bat bootRun
```

Nếu chưa có Gradle Wrapper, dùng lệnh `gradle test` và `gradle bootRun` với bản Gradle 8.x tương thích. Ứng dụng mẫu chạy ở cổng 8080 theo cấu hình mặc định nếu cổng còn trống.

Các lệnh `curl` Bash để quan sát luồng đọc:

```bash
# Public
curl -s -i http://localhost:8080/api/public

# Không có credentials: thường 401
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/items

# Alice nhìn thấy mục của mình
curl -s -u alice:alice123 \
  http://localhost:8080/api/items

# Bob nhìn thấy mục của mình
curl -s -u bob:bob123 \
  http://localhost:8080/api/items

# Alice không có quyền gọi admin summary: 403
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice123 http://localhost:8080/api/admin/summary

# Admin đủ ROLE_ADMIN: 200
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/admin/summary
```

Kết quả status khi chạy lệnh thứ 2, 5 và 6 lần lượt là:

```text
401
403
200
```

Lệnh liệt kê trả JSON của đúng chủ sở hữu, với `id` do H2 cấp lúc chạy. Để tự thử lấy ID Bob bằng credentials Alice, đọc ID qua lệnh Bob rồi gọi `/api/items/{id}` với Alice; **kết quả mong đợi là 404**, không cần giả định ID cố định. Với POST/PATCH/DELETE, dùng MockMvc test đã minh họa để tạo CSRF token đúng quy trình test.

## 5. Kiểm thử ranh giới quyền: những ca dễ bị bỏ sót

### 5.1. Tách role-based authorization và ownership

Một user có `ROLE_USER` có thể dùng endpoint chung; điều đó không có nghĩa họ đọc được toàn bộ record. Khi viết test, tạo hai user **cùng role** để tránh bị đánh lừa bởi kiểm tra role:

```text
Alice ROLE_USER -> GET /api/items/{aliceId} => 200
Alice ROLE_USER -> GET /api/items/{bobId}   => 404
Bob   ROLE_USER -> GET /api/items/{bobId}   => 200
```

Nếu test chỉ có user `ADMIN` và user `GUEST`, kết quả 403 có thể đơn giản là do thiếu role; bạn chưa chứng minh được **owner enforcement**. Ngược lại, nếu rule cho phép admin vượt owner, hãy định nghĩa và test riêng; không suy diễn `ROLE_ADMIN` tự có quyền đọc mọi tài nguyên.

### 5.2. Quyền truy cập riêng tư và dữ liệu chia sẻ

Tài nguyên thực tế có thể thuộc **user**, **tổ chức** hoặc có danh sách **ACL/share grants**. Không áp dụng mọi ví dụ theo user cho dữ liệu tenant:

- **Private note:** điều kiện `id = :id AND owner_user_id = :currentUserId`.
- **Shared organization document:** cần kiểm user có READ permission đối với tổ chức, rồi query `id = :id AND organization_id = :authorizedOrgId`; một thành viên tổ chức không mặc nhiên xem private note trong cùng tổ chức.
- **Admin/support override:** chỉ khi policy cho phép, thường cần permission riêng, audit reason và test không mở rộng ngoài phạm vi.
- **Nested resource:** `GET /projects/{projectId}/tasks/{taskId}` phải kiểm cả project access và task thực sự thuộc project được phép; không chỉ kiểm task ID toàn cục.

Ví dụ test mở rộng cho tổ chức: Alice thuộc Alpha, Bob thuộc Beta; Alice với role giống Bob không được trả task Beta dù biết `taskId`. Khi user có nhiều tổ chức, `orgId` do client chọn chỉ là **đề nghị phạm vi**; server phải xác thực membership/permission trước khi dùng trong query.

### 5.3. 404 che sự tồn tại của tài nguyên

Lựa chọn 404 cho `findByIdAndOwner...` có ưu điểm tránh tiết lộ “ID Bob có tồn tại hay không”. Tuy nhiên cần nhất quán với logging, response schema và trạng thái các thao tác khác. Một API có thể trả 403 rõ ràng khi người dùng nhìn thấy một resource nhưng không được sửa; đó cũng là thiết kế hợp lệ nếu đã được quy định.

**Kiểm thử cả hai điều kiện:** ID không tồn tại và ID tồn tại nhưng ngoài phạm vi đều phải không tiết lộ payload, kể cả message exception. Không nên trả tên owner hoặc nội dung tài nguyên trong thông báo lỗi, ví dụ “Tài liệu của Bob tồn tại nhưng Alice không có quyền”.

### 5.4. Không chỉ kiểm status, hãy kiểm side effect

Một controller có thể `save()` xong rồi mới kiểm owner và trả 403. Test chỉ `.andExpect(status().isForbidden())` sẽ bỏ sót tác động dữ liệu. Với PATCH/DELETE, xác minh sau request rằng:

1. Bản ghi của người bị nhắm tới còn nguyên.
2. Không có bản ghi mới ngoài phạm vi được tạo.
3. Cập nhật của chủ sở hữu hợp lệ thật sự được commit.
4. Không có sự kiện hoặc job bất hợp pháp được phát ra nếu hệ thống có event/outbox (mở rộng cho integration test cần thiết).

Trong ví dụ, assertions `assertThat(items.findById(bobId)...).isEqualTo("bob-private")` và `.isPresent()` trực tiếp xác nhận dữ liệu Bob không thay đổi sau request Alice.

### 5.5. Điều kiện owner phải có trong query, không chỉ ở UI

Sai cho endpoint riêng:

```java
// Sai: frontend ẩn nút, nhưng backend vẫn lấy record toàn cục.
WorkItem item = items.findById(id).orElseThrow();
return ItemView.from(item);
```

Đúng theo chính sách của ví dụ:

```java
WorkItem item = items.findByIdAndOwnerUsername(id, currentUsername)
    .orElseThrow(() ->
        new ResponseStatusException(HttpStatus.NOT_FOUND)
    );
return ItemView.from(item);
```

Đoạn code này minh họa thân method sử dụng các biến `items`, `id`, `currentUsername` đã được khai báo trong service, **không phải tệp Java độc lập**.

Ngay cả khi kiểm owner sau `findById(...)` có thể làm đúng, điều kiện ở query giảm nguy cơ nhánh khác bỏ sót, tránh tải dữ liệu ngoài scope vào cache/log và dễ tái sử dụng cho phân trang. Với cập nhật cạnh tranh, conditional `UPDATE ... WHERE id=? AND owner_user_id=?` còn giúp bảo vệ ngay tại thời điểm ghi.

## 6. Chọn test annotation/công cụ cho đúng mục tiêu

| Công cụ | Kiểm được gì? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Tích hợp HTTP, filter chain, service và persistence thực trong context test. | Không bảo đảm dữ liệu production hay mọi cấu hình profile giống hoàn toàn. |
| `@WebMvcTest` | MVC/controller và filter/context thuộc slice, tốt cho HTTP boundary. | Service/repository thật nếu đã bị mock; owner enforcement nằm ở service có thể bị bỏ qua. |
| `@WithMockUser` | Authorization với principal và authorities giả lập. | Password, account lookup, authentication provider, user thật. |
| `.with(user("alice").roles("USER"))` | Gắn principal giả vào một request MockMvc. | Quy trình Basic/form login thực. |
| `.with(httpBasic("alice","alice123"))` | Thêm Basic header, để filter/provider kiểm credentials khi được load đúng. | Bản thân postprocessor không chứng minh auth filter đang gắn nếu MockMvc tắt filters. |
| `.with(csrf())` | Đưa token CSRF hợp lệ vào request test. | Toàn bộ quy trình lấy token của browser/client production. |
| `@WithUserDetails("alice")` | Nạp user fixture qua `UserDetailsService`, đưa vào SecurityContext. | Không đối chiếu password thô như login request. |

**Vì sao dùng full context cho ví dụ?** Quyền sở hữu thực thi trong `WorkItemService` và repository. Nếu `@WebMvcTest(WorkItemController.class)` mock service để luôn trả item Alice, test 200 chỉ chứng minh controller gọi mock; không bắt được việc service production dùng `findById()` toàn cục. Muốn slice test, hãy thêm **service/repository integration tests riêng** và ít nhất một HTTP integration test nối các tầng.

`@WithMockUser` rất hữu ích khi chỉ kiểm `@PreAuthorize`, role và user name. Nhưng nếu cần kiểm 401 khi sai password hoặc password encoder, dùng `httpBasic(...)`, form login processor hoặc cơ chế Bearer thật theo cấu hình.

### 6.1. Nạp đúng security chain

- Với full context, `@AutoConfigureMockMvc` mặc định thêm filters; không dùng `addFilters=false` trong test authentication/authorization.
- Với `@WebMvcTest`, cần nhập cấu hình bảo mật cần kiểm bằng `@Import(SecurityConfig.class)` khi slice không tự nạp các bean custom. Những repository/service không thuộc slice thường phải mock hoặc import phù hợp.
- Với MockMvc dựng thủ công từ `WebApplicationContext`, `.apply(springSecurity())` tích hợp `FilterChainProxy`.
- Với nhiều `SecurityFilterChain`, xem `securityMatcher`, `@Order`, matcher của HTTP method/path. Test ít nhất một URL thuộc từng chain, và tránh mặc định nghĩ URL nào cũng qua cùng filter.
- Với security ở method (`@PreAuthorize`), cần `@EnableMethodSecurity` và gọi Spring bean proxy thực; nếu controller dùng mocked service, method security trên service thật có thể không được thực thi.

**Cảnh báo kiểm thử giả:** Nếu bỏ toàn bộ rule owner hoặc đổi repository sang `findById`, các test owner âm tính phải **đỏ**. Nếu test suite vẫn xanh khi cố tình bỏ security rule, cần xem nó có đang bypass filters, mock authentication quá nhiều hoặc chỉ kiểm HTTP status mà không kiểm dữ liệu.

## 7. Test phân trang, search, export và thao tác hàng loạt

Một endpoint detail an toàn chưa chứng minh các lối truy cập khác an toàn. Khi phát triển ứng dụng thật, thêm các ca:

- `GET /api/items?page=0&size=20`: `Page.content` và `totalElements` chỉ tính mục của chủ sở hữu; không lấy page toàn hệ thống rồi `.filter(...)` trong Java.
- `GET /api/items?title=...`: điều kiện search kết hợp `owner = :currentUser` bằng `AND`, không `OR` làm lọt item người khác.
- `GET /api/items/count`, dashboard hoặc aggregate: count/sum cũng phải theo scope; không trả tổng hệ thống.
- CSV/Excel export, download file, thumbnail, attachment và background report: cùng ràng buộc owner/tenant.
- API batch nhận nhiều ID: kiểm **từng ID** trước khi trả, sửa hoặc xóa; đừng kiểm một ID rồi dùng truy vấn không scope cho toàn danh sách.
- Filter/sort từ client chỉ được chọn các trường cho phép, không được biến thành một query expression tùy ý vượt phạm vi.
- Cache phải có key phân biệt scope hoặc thực hiện authz trước khi phục vụ cached data; cache chỉ theo `itemId` có thể gây rò rỉ cross-user.

Ví dụ repository phân trang có scope (đoạn này thêm vào `WorkItemRepository` của ví dụ và cần import `Page`, `Pageable`):

```java
Page<WorkItem> findByOwnerUsername(
    String ownerUsername, Pageable pageable
);
```

Spring Data áp dụng điều kiện owner trong truy vấn kết quả và count. Với JPQL/native query phức tạp và count riêng, cần bảo đảm **mọi query** đều mang cùng predicate `owner`/`tenant`. Test ít nhất hai user với nhiều record và xác nhận `totalElements` không bao gồm dữ liệu user khác.

### 7.1. Tránh rủi ro time-of-check/time-of-use

Ví dụ kiểm `owner` trên entity, sau đó thực hiện một thao tác ghi không scope trong transaction khác có thể bị tác động bởi các thay đổi đồng thời về quyền/chủ sở hữu. Nếu cần ràng buộc chặt hơn, dùng update có predicate:

```sql
UPDATE work_items
SET title = :new_title
WHERE id = :item_id
  AND owner_username = :current_username;
```

Sau đó kiểm số hàng bị ảnh hưởng: `0` nghĩa là item không có trong phạm vi được phép, có thể trả 404 theo policy. Với JPA `@Modifying`, cần transaction ghi và chú ý persistence context/cache. Đây là lựa chọn nâng cao cho thao tác cạnh tranh; không phải yêu cầu mặc định cho mọi ứng dụng demo.

## 8. Các lỗi test dễ khiến đánh giá bảo mật sai

### 8.1. Một test chỉ có `@WithMockUser(roles="ADMIN")`

Test đó chỉ xác nhận một principal giả với `ROLE_ADMIN` có thể vào endpoint. Nó **không** kiểm password, role lấy từ database, hoặc quyền owner. Hãy bổ sung test credentials thật và test người cùng role với tài nguyên khác owner.

### 8.2. `@AutoConfigureMockMvc(addFilters=false)`

Việc tắt filter khiến controller có thể chạy mà không qua Spring Security, nên test `200` không phản ánh ứng dụng production. Chỉ dùng cách này nếu chủ ý kiểm MVC logic thuần; **không báo là đã kiểm authorization**.

### 8.3. Chỉ assert 403 khi PATCH của người khác

Nếu thiếu CSRF token, request có thể nhận 403 **vì CSRF**, không chứng minh owner được kiểm. Trong ca owner denial, hãy gửi **CSRF hợp lệ** và expect 403/404 theo policy; test CSRF thiếu/sai token thành những ca riêng.

### 8.4. Dùng `findAll()` rồi lọc trong Java

Request có thể trả đúng JSON trong test nhỏ nhưng query đã tải dữ liệu của mọi user. Khi thêm paging/count/cache/log, có thể lộ dữ liệu hoặc sai tổng số. Repository có scope ngay từ query và test các đường danh sách, tìm kiếm, thống kê.

### 8.5. Test ID cứng

Nếu test giả định ID Alice là `1`, Bob là `2` và H2 không reset identity sau cleanup, test có thể thất bại không liên quan security. Lấy ID từ fixture/repository như `idFor("bob")` trong test.

### 8.6. Dùng user khác quyền thay cho người cùng quyền

Alice USER và Bob ADMIN tạo ra 403 do role; điều đó không chứng minh data isolation. Dùng Alice và Bob cùng `ROLE_USER` để test object ownership.

### 8.7. Không quan sát database sau request bị chặn

Một controller có thể ghi xong rồi phát sinh lỗi, khiến status bị từ chối nhưng dữ liệu đã thay đổi (tùy transaction/exception behavior). Với mutation, assert bản ghi không đổi và không có side effect trái phép.

### 8.8. Test profile vô tình dùng policy khác

`@ActiveProfiles("test")`, mock `AuthenticationManager`, hoặc một test configuration `permitAll()` có thể che sự sai khác với production. Cần ghi rõ chain và profile nào đang kiểm, đồng thời có một integration test đối chiếu cấu hình ứng dụng thật.

### 8.9. Chỉ kiểm status, không kiểm payload

API trả 200 và chứa một item đúng của Alice nhưng cũng kèm item Bob sẽ lọt qua nếu chỉ assert status. Dùng `jsonPath("$", hasSize(1))` và kiểm nội dung kỳ vọng; với response lớn, test thêm rằng không có bất kỳ ID/owner nào ngoài scope.

### 8.10. Bỏ quyền trên endpoint con và đường truy cập thay thế

`GET /api/items/{id}` an toàn nhưng `/api/items/{id}/attachment`, `/api/files/{fileId}`, export hoặc websocket subscription vẫn có thể lộ dữ liệu. Test cả các đường đi thực tế đến cùng resource, gồm GET lẫn thao tác write.

## 9. Mẫu kiểm thử bổ sung cho method security

Nếu quyền được áp dụng trong service bằng `@PreAuthorize`, cần nạp bean method security thật. Ví dụ **phác thảo**, không phải class Java tự chạy độc lập:

```java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig {}

@Service
class ApprovalService {
    @PreAuthorize("hasAuthority('approve:item')")
    public String approve() {
        return "approved";
    }
}
```

Cần import các annotation tương ứng và sử dụng bean `ApprovalService` do Spring tạo (không gọi `new ApprovalService()`). Kiểm:

- `@WithMockUser(authorities="approve:item")`: phương thức được phép.
- `@WithMockUser(authorities="read:item")`: bị từ chối.
- Principal vắng mặt: bị từ chối theo cấu hình.

Khi service chứa cả ownership predicate, vẫn phải test ID của user khác. `@PreAuthorize("hasRole('USER')")` không thể thay điều kiện chủ sở hữu. Việc self-invocation hoặc gọi mocked service có thể bỏ qua AOP proxy, khiến test không xác minh `@PreAuthorize` thật sự chạy. Muốn xác nhận HTTP status, bổ sung integration test gọi endpoint đi qua service bean thật.

## 10. Quy trình chẩn đoán khi kết quả không như kỳ vọng

Khi thấy một case sai, kiểm tra theo thứ tự:

1. **Cấu hình test có đúng?** `spring-security-test` ở test classpath; `@SpringBootTest`/`@WebMvcTest` nạp đúng SecurityConfig; MockMvc có filter chain.
2. **Danh tính nào đang được dùng?** HTTP Basic hợp lệ, `@WithMockUser` giả, Bearer token, session? Có thật sự authentication thành công?
3. **HTTP method/path match rule nào?** Rule `/api/**` đặt trước `/api/admin/**` có thể che rule đặc biệt; kiểm order và `securityMatcher` khi nhiều chain.
4. **Có bị CSRF chặn trước khi kiểm owner không?** Với POST/PATCH/DELETE trong bài, gửi `.with(csrf())` trước khi đánh giá ownership.
5. **Service query có owner predicate không?** Nếu có `findById(id)` toàn cục ở một nhánh, test cross-user phải chỉ ra.
6. **Đã lấy principal từ nguồn đáng tin chưa?** Không nhận `ownerUsername` từ client làm quyền.
7. **Status bị từ chối có làm dữ liệu đổi không?** Query lại DB; với event/queue, kiểm audit/outbox.
8. **Payload có rò rỉ?** Kiểm danh sách, JSON fields, count, logs và exception message.
9. **Fixture có ít nhất hai user cùng role không?** Dùng ID sinh từ fixture; không phụ thuộc thứ tự test.
10. **Một thay đổi cố tình làm hỏng rule có khiến test đỏ không?** Tạm thay owner-scoped query bằng global query trong nhánh thử nghiệm để đánh giá độ nhạy của test suite, sau đó hoàn nguyên trong môi trường phát triển.

## 11. Bài tập tự đánh giá

**A.** Hai user cùng `ROLE_USER`. Test chỉ kiểm Alice có thể gọi `/api/items/{aliceId}` và nhận 200. Đã đủ chưa?  
**Đáp án:** Chưa. Phải kiểm Alice bị chặn khi dùng `{bobId}`, Bob vẫn có thể truy cập `{bobId}`, và list không chứa item Bob.

**B.** Alice gửi PATCH ID Bob, test nhận 403 nhưng không gửi CSRF token. Có chứng minh owner policy không?  
**Đáp án:** Chưa. 403 có thể đến từ `CsrfFilter`. Cần gửi token hợp lệ để request đi tới tầng owner, expect kết quả theo policy và kiểm DB không bị sửa.

**C.** Endpoint `GET /api/items/{id}` trả 404 khi Alice dùng ID Bob. Có nghĩa ID không tồn tại trên toàn hệ thống không?  
**Đáp án:** Không. Nó chỉ có nghĩa bản ghi không tồn tại **trong phạm vi được phép của Alice**. Đây là cách cố ý tránh lộ sự tồn tại tài nguyên của người khác.

**D.** Admin gọi một endpoint của owner Bob và nhận 404. Điều đó có sai không?  
**Đáp án:** Không nếu policy owner-scoped không cho admin bypass. Quyền support xem xuyên owner phải là một đặc quyền riêng được định nghĩa và kiểm thử rõ ràng.

**E.** `@WithMockUser(username="alice",roles="USER")` test truy cập thành công nhưng mật khẩu `alice123` trong nguồn user đã sai. Vì sao?  
**Đáp án:** Annotation giả lập authentication; không kiểm password. Dùng `httpBasic` hoặc cơ chế xác thực thực để kiểm provider.

**F.** API list trả đúng một item Alice nhưng `Page.totalElements=300` gồm item toàn hệ thống. Test status/payload đơn giản có phát hiện không?  
**Đáp án:** Không. Phải kiểm count, search, pagination và mọi aggregate với cùng điều kiện scope.

**G.** Một test xóa item Bob bằng Alice nhận 404. Cần assertion bổ sung nào?  
**Đáp án:** Kiểm `repository.findById(bobId)` vẫn hiện diện và dữ liệu không đổi; bảo vệ side effect quan trọng như response.

**H.** Một API cho phép `POST /api/items` với `ownerUsername=bob` từ body, nhưng client đang đăng nhập là Alice. Có nguy cơ gì?  
**Đáp án:** Gán owner theo input không tin cậy có thể tạo hoặc thao túng dữ liệu cho người khác. Chủ sở hữu phải lấy từ principal hoặc một quyền ủy quyền đã xác minh; test Alice không thể chọn owner Bob.

## 12. Checklist trước khi chốt bài kiểm thử bảo mật

- [ ] Có **allow và deny** test cho mỗi nhóm endpoint quan trọng.
- [ ] Có ít nhất **hai user cùng role** nhưng sở hữu resource khác nhau.
- [ ] Có ca anonymous, credentials sai, role thiếu và role đủ.
- [ ] Có ca người A đọc/sửa/xóa ID của B, không chỉ dùng ID sai ngẫu nhiên.
- [ ] Owner/tenant lấy từ server-verified principal và permission, không tin userId/owner từ client.
- [ ] List/detail/search/count/page/export đều có scope theo quyền dữ liệu.
- [ ] POST/PATCH/DELETE kiểm CSRF riêng; test ownership dùng CSRF hợp lệ.
- [ ] Test mutation bị từ chối xác nhận database không đổi.
- [ ] Test tạo mới xác nhận owner được gán từ principal phía server.
- [ ] HTTP status 403/404 tuân thủ policy nhất quán và không rò rỉ dữ liệu nhạy cảm.
- [ ] SecurityFilterChain và provider đúng với ứng dụng được load; không tắt filters.
- [ ] Không dùng `@WithMockUser` làm bằng chứng password/provider đã được kiểm.
- [ ] Có test đường dẫn con, batch, file, cache và phân trang nếu hệ thống hỗ trợ.
- [ ] Các test chủ động thất bại khi bỏ owner restriction hoặc role rule.

## 13. Ghi nhớ và tài liệu tham khảo

**Một bài test authorization đạt yêu cầu phải chứng minh ba điều cùng lúc:** (1) người được phép có thể làm việc, (2) người thiếu authentication/role bị chặn, và (3) người đã đăng nhập vẫn không thể xem hoặc thay đổi tài nguyên của người khác. Cặp test **owner đúng → được phép** và **owner sai cùng role → bị từ chối, không đổi dữ liệu** là bằng chứng trực tiếp cho bảo vệ cấp đối tượng.

Tài liệu đối chiếu:

- [Spring Security — Testing trong Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [OWASP API Security Top 10 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
