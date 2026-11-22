# Bảo vệ phương thức dịch vụ và tài nguyên theo chủ sở hữu

## 1. Mục tiêu và bài toán

Trong phần thực hành tổng hợp này, bạn xây dựng một ứng dụng Spring Boot quản lý **ghi chú riêng tư**. Người dùng đăng nhập có thể đọc, liệt kê và cập nhật ghi chú của **chính mình**; không thể đọc hoặc sửa ghi chú của người khác dù biết đúng ID. Trọng tâm là phối hợp **bảo vệ HTTP request**, **method security ở service layer** và **quy tắc sở hữu của từng đối tượng**.

Kết thúc bài, bạn sẽ:

1. Giải thích tại sao `authenticated()` hoặc `hasRole("USER")` **chưa đủ** để bảo vệ tài nguyên có chủ sở hữu.
2. Bật `@EnableMethodSecurity` và dùng `@PreAuthorize`, `@PostAuthorize` ở **Spring-managed service bean**, không chỉ đặt kiểm tra trong controller.
3. Tách việc xác thực danh tính khỏi kiểm tra chủ sở hữu trên từng ID; lấy người dùng hiện tại từ `Authentication` tin cậy ở phía server.
4. Ngăn cả **đọc trái phép** lẫn **ghi trái phép**; không làm thay đổi dữ liệu khi bị từ chối.
5. Viết kiểm thử `MockMvc` và kiểm thử gọi trực tiếp service để chống lỗi IDOR/BOLA (Insecure Direct Object Reference / Broken Object Level Authorization).
6. Nhận diện giới hạn của kiểm tra sau khi trả về, AOP proxy, tham số SpEL, CSRF và vấn đề cạnh tranh khi chuyển sang database thật.

Đây là bài **Spring Security Servlet/Spring MVC**; Spring WebFlux dùng cơ chế reactive method security khác. Ví dụ cung cấp dự án **Java 17 + Spring Boot 3.3.5 + Spring Security 6.x** chạy được về mặt cấu trúc, với user và dữ liệu giả in-memory. Phiên bản được ghim để bài tập lặp lại được; khi áp dụng vào dự án hiện tại hãy chọn nhánh Boot/Security còn được hỗ trợ và đối chiếu tài liệu của nhánh tương ứng.

## 2. Phân biệt đăng nhập, vai trò và quyền sở hữu

Giả sử database chứa:

| ID | Chủ sở hữu | Nội dung |
| --- | --- | --- |
| 1 | `alice` | Alice note one |
| 2 | `bob` | Bob private note |
| 3 | `alice` | Alice note three |

Nếu cấu hình chỉ có:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/notes/**").authenticated()
    .anyRequest().denyAll());
~~~

thì cả Alice và Bob đều **đã xác thực** nên đều có thể gọi `GET /api/notes/2`. Nếu controller tìm bản ghi chỉ bằng ID và trả thẳng, Alice đọc được dữ liệu của Bob. Đây là **lỗi phân quyền cấp đối tượng**, thường được gọi IDOR/BOLA. Tăng độ dài hoặc dùng UUID thay ID số không thay thế việc kiểm tra quyền truy cập trên object.

Phân biệt:

| Cấp kiểm tra | Câu hỏi | Cách làm trong bài |
| --- | --- | --- |
| Authentication | Client có danh tính hợp lệ không? | HTTP Basic + `UserDetailsService` |
| Request authorization | Có được vào vùng API này không? | `anyRequest().authenticated()` |
| Method authorization | Phương thức service có cho phép thao tác này không? | `@PreAuthorize` / `@PostAuthorize` |
| Object ownership | ID cụ thể có thuộc người đang gọi không? | So `Note.owner` với `authentication.name` |
| Data isolation | Danh sách hoặc truy vấn có chỉ trả dữ liệu được phép không? | `findByOwner(...)`, query scoped theo owner |

Một người có `ROLE_USER` cũng không mặc nhiên sở hữu mọi ghi chú của `ROLE_USER` khác. Ngay cả `ROLE_ADMIN` cũng không được bỏ qua quy tắc sở hữu nếu yêu cầu sản phẩm không cấp ngoại lệ cho quản trị viên.

**Hợp đồng mong muốn của bài:**

| Request | Danh tính | Kết quả |
| --- | --- | --- |
| `GET /api/health` | Anonymous | 200 |
| `GET /api/notes/1` | Anonymous | 401 |
| `GET /api/notes/1` | Alice | 200 |
| `GET /api/notes/2` | Alice | 403 |
| `GET /api/notes/2` | Bob | 200 |
| `GET /api/notes/2` | Admin không phải chủ sở hữu | 403 |
| `GET /api/notes/999` | Alice | 404 |
| `GET /api/notes` | Alice | Chỉ thấy ID 1 và 3 |
| `PUT /api/notes/1` | Alice + CSRF token hợp lệ | 200, nội dung được sửa |
| `PUT /api/notes/2` | Alice + CSRF token hợp lệ | 403, **không sửa** nội dung Bob |
| `PUT /api/notes/1` | Alice, thiếu CSRF token | 403, **không sửa** |
| `PUT /api/notes/999` | Alice + CSRF token hợp lệ | 403 theo chính sách kiểm tra trước của ví dụ |

Trạng thái 403/404 ở tài nguyên không tồn tại là **lựa chọn thiết kế**: `@PostAuthorize` trên đường đọc cho phép xử lý không tồn tại (404) trước bước xác nhận chủ sở hữu; kiểm tra `@PreAuthorize` trên đường sửa trả 403 khi chính sách không tìm thấy bản ghi. Nhiều ứng dụng production chủ động trả 404 đồng nhất cho cả "không tồn tại" và "không có quyền" để tránh lộ sự tồn tại của object. Không coi một status cụ thể là mặc định bắt buộc cho mọi hệ thống.

## 3. Từ cách làm dễ lỗi đến cơ chế bảo vệ ở service

Ví dụ **không an toàn** dưới đây chỉ nhằm phân tích, **không sử dụng trong phiên bản cuối**:

~~~java
// Đoạn minh họa lỗi: tìm bằng ID rồi trả, không kiểm tra owner
@GetMapping("/api/notes/{id}")
public Note insecureRead(@PathVariable long id) {
    return noteRepository.findById(id).orElseThrow();
}
~~~

Ngay cả khi route đã có `authenticated()`, Alice vẫn có thể đoán/chuyển `{id}` thành `2` rồi nhận ghi chú của Bob. Thêm một câu `if` trong controller có thể chặn trường hợp này nhưng dễ bị quên khi có REST endpoint khác, scheduled job, GraphQL, listener hay một service caller khác.

**Thiết kế bài thực hành:**

~~~text
HTTP request
   |
   v
SecurityFilterChain
   |-- authentication: Basic credentials -> Authentication
   |-- request rule: public health / authenticated notes
   |
   v
NoteController
   |
   v
NoteService (Spring bean qua AOP proxy)
   |-- read(id): @PostAuthorize xét owner trên kết quả đọc
   |-- update(id,...): @PreAuthorize xét owner TRƯỚC khi sửa
   |-- listForOwner(owner): @PreAuthorize chống giả mạo owner
   |
   v
NoteRepository (in-memory)
   |
   v
Dữ liệu được phép hoặc AccessDeniedException
~~~

Trong dự án thực tế, cần đặt phép kiểm tra ở **mọi đường truy xuất và thay đổi đối tượng**. Bảo vệ service là lớp phòng thủ hữu ích vì caller không phải lúc nào cũng đi qua cùng một controller. Cũng cần nhớ: chỉ các **phương thức được gọi qua Spring AOP proxy** mới được annotation method security chặn đúng cách.

## 4. Khởi tạo project để chạy trọn ví dụ

Yêu cầu JDK 17 và Gradle Wrapper từ Spring Initializr hoặc project Gradle có sẵn. Chọn Java, Gradle Groovy, Spring MVC và Spring Security. Các file ví dụ bên dưới dùng package `example.ownership`.

Cấu trúc:

~~~text
ownership-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...                 # Gradle Wrapper do generator cung cấp
├── src/main/java/example/ownership/
│   ├── OwnershipApplication.java
│   ├── SecurityConfig.java
│   ├── Note.java
│   ├── NoteRepository.java
│   ├── NoteAccess.java
│   ├── NoteService.java
│   ├── NoteController.java
│   └── HealthController.java
└── src/test/java/example/ownership/
    └── OwnershipSecurityTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'ownership-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
~~~

Spring Boot quản lý các phiên bản dependency Spring qua BOM. Không tự gán một Spring Security major version không tương thích với Boot. `spring-security-test` cho phép mô phỏng HTTP Basic, CSRF token và `@WithMockUser`. Ví dụ không dùng JPA/database để bạn thấy rõ quyết định bảo mật mà không lẫn logic lưu trữ.

### 4.1. Lớp ứng dụng

Tệp `src/main/java/example/ownership/OwnershipApplication.java`:

~~~java
package example.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OwnershipApplication {
    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }
}
~~~

Đặt các lớp còn lại cùng package `example.ownership` hoặc dưới package con để Spring Boot phát hiện bean bằng component scan.

### 4.2. Đối tượng Note có thuộc tính owner chỉ đọc

Tệp `src/main/java/example/ownership/Note.java`:

~~~java
package example.ownership;

public final class Note {
    private final long id;
    private final String owner;
    private final String content;

    public Note(long id, String owner, String content) {
        this.id = id;
        this.owner = owner;
        this.content = content;
    }

    public long getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }

    public String getContent() {
        return content;
    }
}
~~~

`owner` không lấy từ request body khi sửa ghi chú. Dùng `getOwner()` giúp SpEL trong `@PostAuthorize("returnObject.owner ...")` truy cập thuộc tính JavaBean rõ ràng. Đối tượng là immutable: sửa content tạo `Note` mới nhưng giữ nguyên owner.

### 4.3. Kho dữ liệu demo

Tệp `src/main/java/example/ownership/NoteRepository.java`:

~~~java
package example.ownership;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Repository;

@Repository
public class NoteRepository {
    private final Map<Long, Note> notes = new ConcurrentHashMap<>();

    public NoteRepository() {
        resetDemoData();
    }

    public void resetDemoData() {
        notes.clear();
        notes.put(1L, new Note(1L, "alice", "Alice note one"));
        notes.put(2L, new Note(2L, "bob", "Bob private note"));
        notes.put(3L, new Note(3L, "alice", "Alice note three"));
    }

    public Optional<Note> findById(long id) {
        return Optional.ofNullable(notes.get(id));
    }

    public List<Note> findByOwner(String owner) {
        return notes.values().stream()
                .filter(note -> note.getOwner().equals(owner))
                .sorted(Comparator.comparingLong(Note::getId))
                .toList();
    }

    public void save(Note note) {
        notes.put(note.getId(), note);
    }
}
~~~

Kho này chỉ tồn tại trong RAM và reset dữ liệu khi khởi động. Nó **không xử lý transaction, nhiều process, chuyển chủ sở hữu hay cạnh tranh dữ liệu như production**. Phần cuối bài hướng dẫn điều kiện bắt buộc khi chuyển sang SQL.

## 5. Bật cả HTTP security và method security

Tệp `src/main/java/example/ownership/SecurityConfig.java`:

~~~java
package example.ownership;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
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
                .requestMatchers(HttpMethod.GET, "/api/health").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-password"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Hai lớp bảo vệ khác nhau:**

- `SecurityFilterChain` kiểm tra request. Endpoint `GET /api/health` công khai; mọi URL còn lại yêu cầu đã xác thực. `httpBasic` giúp kiểm thử với curl; `formLogin` bị tắt để không redirect về login form trong API.
- `@EnableMethodSecurity` bật interceptor cho `@PreAuthorize` và `@PostAuthorize` trên các Spring bean. **Chỉ thêm starter Security không tự kích hoạt method security**.
- Ba tài khoản demo dùng chung password giả và BCrypt. Chỉ sử dụng ở localhost cho bài học, không mang mật khẩu cố định hoặc dữ liệu nhạy cảm vào production.
- Không có `csrf(AbstractHttpConfigurer::disable)`: cơ chế CSRF mặc định vẫn bật, vì vậy test `PUT` phải thêm token hợp lệ. HTTP Basic không tự đồng nghĩa CSRF bị tắt.
- `ADMIN` ở ví dụ chưa được cấp ngoại lệ quyền sở hữu. Vai trò chỉ là thông tin trong `Authentication`; logic owner phải chủ động xét quyền.

### 5.1. Bean chuyên kiểm tra sở hữu

Tệp `src/main/java/example/ownership/NoteAccess.java`:

~~~java
package example.ownership;

import org.springframework.stereotype.Component;

@Component("noteAccess")
public class NoteAccess {
    private final NoteRepository repository;

    public NoteAccess(NoteRepository repository) {
        this.repository = repository;
    }

    public boolean isOwner(long id, String username) {
        if (username == null || username.isBlank()) {
            return false;
        }

        return repository.findById(id)
                .map(note -> note.getOwner().equals(username))
                .orElse(false);
    }
}
~~~

Bean này chỉ nhận `id` và username, trả về Boolean. Trong annotation SpEL, `@noteAccess` trỏ đúng tới bean này, còn `authentication.name` lấy danh tính **đã được xác thực** từ SecurityContext ở server.

`false` khi ID không tồn tại nghĩa là thao tác `PUT` với ID lạ bị từ chối **trước khi** chạy method. Với sản phẩm thật, hãy quyết định rõ khi nào trả 403 và 404, tránh lộ sự tồn tại của tài nguyên qua khác biệt response.

Không viết `isOwner(id, usernameFromRequestBody)` vì client có thể đổi chuỗi username thành `bob`. Người dùng hiện tại phải được suy ra từ hệ thống authentication, không từ trường owner do client tự khai.

## 6. Khóa đường đọc, đường ghi và đường liệt kê ngay ở service

Tệp `src/main/java/example/ownership/NoteService.java`:

~~~java
package example.ownership;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class NoteService {
    private final NoteRepository repository;

    public NoteService(NoteRepository repository) {
        this.repository = repository;
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Note read(long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Note not found"));
    }

    @PreAuthorize("@noteAccess.isOwner(#id, authentication.name)")
    public Note update(@P("id") long id, String content) {
        if (content == null || content.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Content must not be blank");
        }

        Note oldNote = repository.findById(id)
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Note not found"));

        Note updated = new Note(id, oldNote.getOwner(), content);
        repository.save(updated);
        return updated;
    }

    @PreAuthorize("#owner == authentication.name")
    public List<Note> listForOwner(@P("owner") String owner) {
        return repository.findByOwner(owner);
    }
}
~~~

**Phân tích chính xác ba annotation:**

**`@PostAuthorize` với `read`:** phương thức lấy `Note` từ kho, sau đó interceptor kiểm tra `returnObject.owner == authentication.name` **trước khi trả kết quả cho caller**. Nếu Alice gọi ID 2, kết quả là ghi chú Bob nên expression sai và Spring Security ném `AccessDeniedException`; HTTP request nhận **403**. Nếu ID không tồn tại, phương thức ném `ResponseStatusException(404)` trước khi có return object, nên bên HTTP thấy **404**.

`@PostAuthorize` hợp lý cho **đọc thuần túy**, nhưng service thực tế có thể đã truy vấn dữ liệu trước khi chặn; tránh log/ghi cache nội dung chưa được phép trước khi qua kiểm tra. **Không dùng `@PostAuthorize` để bảo vệ một phương thức ghi database**: thay đổi có thể đã xảy ra rồi mới bị từ chối.

**`@PreAuthorize` với `update`:** trước khi chạy bất kỳ câu lệnh nào trong `update`, interceptor gọi `noteAccess.isOwner(id, authentication.name)`. Nếu sai, method **không được thực thi**, nên Bob không bị sửa ghi chú. Đây là lựa chọn thiết yếu cho thao tác thay đổi trạng thái. Trường hợp giả lập đổi owner giữa bước kiểm tra và bước ghi không xảy ra trong dữ liệu demo, nhưng cần biện pháp transaction/atomic update ở production (xem mục 11).

**`@PreAuthorize` với `listForOwner`:** dù controller chỉ truyền current username, service vẫn tự từ chối `listForOwner("bob")` nếu caller là Alice. Điều này ngăn một service caller khác tự truyền owner mong muốn. Repository cũng lọc tại nguồn dữ liệu `findByOwner` thay vì trả toàn bộ rồi lọc ở controller.

**Về tên tham số SpEL:** `#id` và `#owner` dùng tên do `@P("id")` / `@P("owner")` khai báo tường minh. Điều này tránh phụ thuộc vào việc compiler có giữ tên tham số hay không. Nếu bỏ `@P` và vẫn tham chiếu `#id`, cần biên dịch với `-parameters` đúng theo tài liệu method security. Có thể dùng `#p0` cho tham số đầu tiên nhưng thường khó đọc hơn.

## 7. Controller nhận ID, service quyết định quyền

Tệp `src/main/java/example/ownership/NoteController.java`:

~~~java
package example.ownership;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/notes")
public class NoteController {
    private final NoteService service;

    public NoteController(NoteService service) {
        this.service = service;
    }

    @GetMapping
    public List<Note> mine(Authentication authentication) {
        return service.listForOwner(authentication.getName());
    }

    @GetMapping("/{id}")
    public Note get(@PathVariable long id) {
        return service.read(id);
    }

    @PutMapping("/{id}")
    public Note update(
            @PathVariable long id,
            @RequestBody UpdateNoteRequest request) {
        return service.update(id, request.content());
    }

    public record UpdateNoteRequest(String content) {
    }
}
~~~

Dữ liệu request của `PUT` **chỉ gồm `content`**. ID đến từ URL nhưng không được tin tưởng như bằng chứng sở hữu; `owner` không xuất hiện trong body. Với endpoint liệt kê, controller lấy `Authentication` từ Spring Security thay vì cho client truyền tham số `?owner=bob`.

Tệp `src/main/java/example/ownership/HealthController.java`:

~~~java
package example.ownership;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    @GetMapping("/api/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
~~~

Controller `/api/health` công khai, không thao tác với NoteService và không lộ dữ liệu người dùng.

**Quan trọng:** controller được Spring tạo bean và inject một `NoteService` do Spring quản lý. Lời gọi `service.read/update/listForOwner` đi qua proxy method security. Nếu bạn tự tạo `new NoteService(...)` hoặc gọi một method có annotation bằng `this.update(...)` bên trong chính `NoteService`, interceptor proxy có thể bị bỏ qua. Không dựa vào việc annotation "tự chạy" trên mọi Java method call.

## 8. Chạy ứng dụng và kiểm tra bằng HTTP

Tại root dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Dùng terminal khác:

~~~bash
curl -i http://localhost:8080/api/health
curl -i http://localhost:8080/api/notes/1
curl -i --basic -u 'alice:demo-password' http://localhost:8080/api/notes/1
curl -i --basic -u 'alice:demo-password' http://localhost:8080/api/notes/2
curl -i --basic -u 'bob:demo-password' http://localhost:8080/api/notes/2
curl -i --basic -u 'alice:demo-password' http://localhost:8080/api/notes
curl -i --basic -u 'admin:demo-password' http://localhost:8080/api/notes/2
~~~

Trong PowerShell, sử dụng `curl.exe` thay cho alias `curl` trên Windows PowerShell cũ; có thể viết mỗi command một dòng.

### 8.1. Kết quả kỳ vọng quan trọng

- `GET /api/health`: **200** và `{"status":"ok"}`.
- `GET /api/notes/1` không gửi credentials: **401** (HTTP Basic yêu cầu xác thực).
- Alice đọc ID 1: **200** và JSON `{"id":1,"owner":"alice","content":"Alice note one"}`.
- Alice đọc ID 2: **403**, **không được trả JSON của Bob**.
- Bob đọc ID 2: **200** và JSON `{"id":2,"owner":"bob","content":"Bob private note"}`.
- Alice liệt kê `/api/notes`: **200**, chỉ chứa note ID 1 và 3, theo thứ tự ID tăng dần.
- Admin đọc ID 2: **403** vì quyền admin không tự tạo quyền sở hữu.
- Alice đọc ID 999: **404** vì không có đối tượng nào để trả từ `read`.

Đây là **kết quả mong đợi**, không phải stdout/log đã ghi lại từ môi trường của bạn. Các HTTP header bổ sung, format lỗi và thời gian chạy phụ thuộc cấu hình.

### 8.2. Vì sao không demo PUT đơn giản bằng curl?

CSRF đang bật theo cấu hình mặc định. Lệnh `PUT` có Basic credentials nhưng **thiếu CSRF token hợp lệ** sẽ bị trả **403** trước cả kiểm tra ownership. Đó là hành vi có chủ đích, không phải chứng cứ Alice không sở hữu note. Để kiểm thử an toàn, mục 9 dùng `MockMvc.with(csrf())` tạo token phù hợp test context.

Đối với giao diện trình duyệt hoặc API dùng cookie/session, cần thiết kế cách cấp và gửi CSRF token phù hợp. Không tắt CSRF chỉ để làm một ví dụ `curl -X PUT` có thể ghi dữ liệu. Với API không cookie, chỉ dùng Authorization header/token, chính sách CSRF phải được đánh giá theo threat model thực tế.

## 9. Test tự động: truy cập ngang, ghi trái phép và gọi trực tiếp service

Tệp `src/test/java/example/ownership/OwnershipSecurityTests.java`:

~~~java
package example.ownership;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OwnershipSecurityTests {
    @Autowired
    MockMvc mvc;

    @Autowired
    NoteRepository repository;

    @Autowired
    NoteService service;

    @BeforeEach
    void resetNotes() {
        repository.resetDemoData();
    }

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void anonymousCannotReadPrivateNote() throws Exception {
        mvc.perform(get("/api/notes/1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadHerOwnNote() throws Exception {
        mvc.perform(get("/api/notes/1")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void aliceCannotReadBobsNote() throws Exception {
        mvc.perform(get("/api/notes/2")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadHisNote() throws Exception {
        mvc.perform(get("/api/notes/2")
                        .with(httpBasic("bob", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").value("Bob private note"));
    }

    @Test
    void adminDoesNotBypassOwnershipAutomatically() throws Exception {
        mvc.perform(get("/api/notes/2")
                        .with(httpBasic("admin", "demo-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingNoteReturnsNotFoundOnRead() throws Exception {
        mvc.perform(get("/api/notes/999")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isNotFound());
    }

    @Test
    void listContainsOnlyCurrentOwnersNotes() throws Exception {
        mvc.perform(get("/api/notes")
                        .with(httpBasic("alice", "demo-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[1].id").value(3))
                .andExpect(jsonPath("$[0].owner").value("alice"))
                .andExpect(jsonPath("$[1].owner").value("alice"));
    }

    @Test
    void wrongPasswordCannotReadPrivateNote() throws Exception {
        mvc.perform(get("/api/notes/1")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanUpdateWithValidCsrf() throws Exception {
        mvc.perform(put("/api/notes/1")
                        .with(httpBasic("alice", "demo-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"Alice updated\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").value("Alice updated"));

        assertEquals("Alice updated",
                repository.findById(1L).orElseThrow().getContent());
    }

    @Test
    void aliceCannotUpdateBobsNoteAndNoDataChanges() throws Exception {
        mvc.perform(put("/api/notes/2")
                        .with(httpBasic("alice", "demo-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"tampered\"}"))
                .andExpect(status().isForbidden());

        assertEquals("Bob private note",
                repository.findById(2L).orElseThrow().getContent());
    }

    @Test
    void missingCsrfBlocksUpdateEvenForOwner() throws Exception {
        mvc.perform(put("/api/notes/1")
                        .with(httpBasic("alice", "demo-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"no csrf\"}"))
                .andExpect(status().isForbidden());

        assertEquals("Alice note one",
                repository.findById(1L).orElseThrow().getContent());
    }

    @Test
    void updateMissingIdIsDeniedByPreCheck() throws Exception {
        mvc.perform(put("/api/notes/999")
                        .with(httpBasic("alice", "demo-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"new\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void serviceCallerCannotForgeOwnerArgument() {
        assertThrows(AccessDeniedException.class,
                () -> service.listForOwner("bob"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void serviceCallerCannotReadOtherOwnersNote() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(2L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void serviceCallerCannotModifyOtherOwnersNote() {
        assertThrows(AccessDeniedException.class,
                () -> service.update(2L, "tampered"));

        assertEquals("Bob private note",
                repository.findById(2L).orElseThrow().getContent());
    }
}
~~~

Chạy toàn bộ test của bài:

~~~bash
./gradlew test --tests "example.ownership.OwnershipSecurityTests"
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.ownership.OwnershipSecurityTests"
~~~

**Kết quả mong đợi:** **16 test PASS**, Gradle kết thúc bằng `BUILD SUCCESSFUL`. Nếu test fail, đối chiếu version dependency và từng bước cấu hình trước khi đổi expected status. Số lượng test, tên class, path và annotation trong bài là những dữ kiện cố định; log thực tế không được giả lập thành bằng chứng chạy thành công.

**Ý nghĩa của bộ test:**

- Các test dùng `httpBasic` chạy qua filter xác thực thực sự, không chỉ tạo một mock principal. Chúng kiểm tra Alice/Bob/Admin và status 200/401/403/404.
- Test sửa ghi chú phải dùng `csrf()`; nếu không có, 403 có thể chỉ do CSRF chứ **chưa chứng minh** check owner hoạt động. Vì vậy test truy cập ngang cố tình **thêm token hợp lệ**.
- Sau khi bị 403 ở đường sửa, test kiểm tra trực tiếp repository rằng nội dung Bob vẫn nguyên vẹn. **Status 403 thôi chưa đủ chứng minh không có side effect**.
- Các test `@WithMockUser` gọi thẳng bean `NoteService` từ Spring context. Chúng chứng minh việc từ chối vẫn hoạt động **khi bỏ qua controller và HTTP filter**; đây là điểm cốt lõi của method security.
- `@WithMockUser` tạo `Authentication` giả để kiểm tra method authorization, không kiểm tra mật khẩu. Hai nhóm test kiểm tra hai vấn đề khác nhau nên bổ sung cho nhau.

## 10. Đọc chuỗi thực thi và phân biệt Pre/Post authorization

### 10.1. Alice đọc ghi chú Bob

~~~text
GET /api/notes/2 + Basic alice
       |
       v
HTTP Basic xác thực alice
       |
       v
anyRequest().authenticated(): PASS
       |
       v
NoteController.get(2) -> service.read(2) qua Spring proxy
       |
       v
NoteRepository trả Note(id=2, owner=bob)
       |
       v
@PostAuthorize: "bob" == "alice" ? FALSE
       |
       v
AccessDeniedException -> HTTP 403
(Không trả JSON ghi chú của Bob)
~~~

Ở đây quyền bị từ chối **sau khi đọc dữ liệu trong service**, nhưng **trước khi trả đối tượng ra bên ngoài proxy**. Vì vậy ví dụ chỉ dùng `@PostAuthorize` cho thao tác đọc không gây side effect.

### 10.2. Alice sửa ghi chú Bob

~~~text
PUT /api/notes/2 + Basic alice + CSRF hợp lệ
       |
       v
HTTP Basic xác thực alice; CSRF: PASS
       |
       v
HTTP request rule: authenticated -> PASS
       |
       v
NoteController.update(2,...)
       |
       v
@PreAuthorize gọi noteAccess.isOwner(2,"alice")
       |
       v
owner thực tế = "bob" -> FALSE
       |
       v
AccessDeniedException -> HTTP 403
NoteService.update KHÔNG CHẠY
Repository giữ nguyên dữ liệu
~~~

**Thứ tự kiểm tra là trọng tâm:** một chính sách được đánh giá **sau write** là quá muộn để bảo vệ tính toàn vẹn dữ liệu. `@PreAuthorize` chặn trước khi method chạy; ở production còn cần kiểm soát transaction/điều kiện UPDATE để tránh race.

### 10.3. Những trường hợp không nên rút ra quy tắc máy móc

`@PreAuthorize` hoạt động ở **method invocation**; `@PostAuthorize` hoạt động ở **return value**. Không phải mọi thao tác đọc cần dùng Post: nếu có thể truy vấn theo current owner ngay từ database, đó thường là cách hiệu quả và ít rò rỉ hơn. Không phải mọi resource "cùng role" đều được phép chia sẻ: owner, tenant và quyền được chia sẻ thường phải kiểm tra riêng.

`@PreFilter` / `@PostFilter` còn hỗ trợ lọc collection đầu vào/đầu ra, nhưng **lọc collection lớn sau khi tải toàn bộ database** thường tốn tài nguyên và dễ khiến truy vấn số lượng/pagination sai. Ưu tiên lọc trực tiếp từ query khi ứng dụng có nhiều dữ liệu.

## 11. Chuyển từ repository demo sang database thật

### 11.1. Truy vấn trong phạm vi chủ sở hữu

Đối với hệ thống lớn, thay vì luôn `findById(id)` rồi mới kiểm tra, ưu tiên truy vấn đã gắn danh tính tin cậy:

~~~sql
SELECT id, owner_id, content
FROM notes
WHERE id = :id
  AND owner_id = :current_user_id;
~~~

Dùng `current_user_id` được xác định từ danh tính xác thực phía server, **không nhận từ JSON body hay query string**. Với API danh sách:

~~~sql
SELECT id, owner_id, content
FROM notes
WHERE owner_id = :current_user_id
ORDER BY id;
~~~

Nếu muốn không tiết lộ sự tồn tại của note người khác, truy vấn scoped theo owner và trả 404 cho cả "không tồn tại" lẫn "không thuộc owner" là một chính sách hợp lý. Tuy nhiên phải áp dụng thống nhất cho GET/UPDATE/DELETE, metadata, file download và các API phụ.

### 11.2. Kiểm tra và ghi phải tránh race

Nếu service chạy:

~~~text
1. SELECT note.owner = alice  -> PASS
2. Một transaction khác đổi owner sang bob
3. UPDATE notes SET content=... WHERE id=1
~~~

thì kiểm tra đúng ở bước 1 vẫn không đủ bảo đảm ở bước 3. Hãy dùng transaction với isolation/locking phù hợp hoặc thao tác ghi có điều kiện ràng buộc **ID và owner trong cùng câu SQL**:

~~~sql
UPDATE notes
SET content = :content
WHERE id = :id
  AND owner_id = :current_user_id;
~~~

Nếu số hàng cập nhật = 0, xử lý theo chính sách không có quyền/không tồn tại của ứng dụng; không giả định ghi đã thành công. Với dữ liệu nhiều tenant, thêm `tenant_id` và các điều kiện liên quan vào truy vấn và constraint. Với quyền được ủy quyền/chia sẻ, policy phải kiểm tra record cấp quyền thực tế chứ không chỉ so owner.

### 11.3. Chủ sở hữu phải có danh tính ổn định

Trong bài, `Note.owner` là `alice` hoặc `bob` và được so với `authentication.name`. Production nên ưu tiên **user ID bất biến** (ví dụ subject đã được xác thực và ánh xạ về internal user ID) thay vì display name hoặc email có thể đổi. Các IdP/OIDC có thể có claim subject, tenant, scope; không tự động coi claim tùy ý từ client là quyền sở hữu. Với ứng dụng đa tenant, kiểm tra cả tenant boundary.

### 11.4. Nguyên tắc với role ADMIN và chính sách chia sẻ

Nếu sản phẩm có yêu cầu admin đọc một số ghi chú, chính sách phải thể hiện rõ:

~~~java
// Đoạn ý tưởng, KHÔNG thay trực tiếp mọi rule mà không xét nghiệp vụ
@PreAuthorize("hasRole('ADMIN') || @noteAccess.isOwner(#id, authentication.name)")
public Note readForAuthorizedUser(@P("id") long id) {
    // ...
}
~~~

Đoạn minh họa trên **không độc lập**, cần repository/service và import tương ứng; nếu dùng `@PostAuthorize` thuần owner của ví dụ hiện tại, admin vẫn bị chặn. Đừng thêm role bypass chỉ để sửa một test đang đỏ. Hãy làm rõ chức năng cụ thể admin được làm, cơ chế audit và dữ liệu nhạy cảm.

## 12. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách kiểm tra/sửa |
| --- | --- | --- |
| Chỉ có `authenticated()` trên route | Người dùng có thể đoán ID của người khác | Test Alice/Bob trên cùng endpoint, nhiều ID |
| Chỉ có `hasRole('USER')` | Nhiều người cùng role nhưng owner khác nhau | Kiểm tra owner/tenant/permission ở object level |
| Tin `owner` từ request body | Client tự đổi thành user khác | Lấy danh tính từ Authentication/identity service |
| Quên `@EnableMethodSecurity` | Annotation method security không được kích hoạt | Test gọi trực tiếp service phải bị từ chối |
| Dùng `new Service(...)` hoặc tự gọi `this.method()` | Có thể bỏ qua Spring AOP proxy | Inject service bean; thiết kế lời gọi đi qua proxy |
| Method `private` hoặc `final` cần proxy | Interceptor không thể bảo đảm chặn như method public được proxy | Đặt policy ở public method của bean quản lý bởi Spring |
| `@PostAuthorize` trên method ghi | Ghi dữ liệu xảy ra trước khi từ chối | `@PreAuthorize` và điều kiện UPDATE an toàn |
| Dùng `#id` nhưng compiler mất tên param | SpEL có thể không tìm được biến/đánh giá sai | Dùng `@P("id")` hoặc biên dịch `-parameters` |
| Test ghi không có CSRF | 403 do CSRF che lỗi owner | Thêm `with(csrf())`, rồi test deny/pass ownership |
| Chỉ kiểm tra HTTP 403 | Có thể đã sửa database trước khi từ chối | Assert trạng thái dữ liệu không đổi |
| Bảo vệ GET mà quên PUT/DELETE/export | IDOR còn tồn tại ở đường khác | Ma trận thao tác cho mỗi loại tài nguyên |
| Dùng owner = username có thể đổi | Đổi tên dẫn tới mất hoặc sai quyền | Ánh xạ sang internal immutable user ID |
| Tách SELECT owner và UPDATE không đồng bộ | Race dẫn tới ghi sai chủ | Atomic UPDATE có owner predicate / locking |
| Admin tự động vượt mọi ownership | Mở rộng quyền ngoài ý định | Tài liệu hóa và test ngoại lệ cụ thể |
| Chỉ phân quyền ở controller | Service caller khác có thể bỏ qua | Method security ở service và data-layer guard |

**Chú ý về exception/status:** Trong HTTP Basic của ví dụ, anonymous thường nhận 401; người đã xác thực nhưng bị phương thức từ chối thường nhận 403. Với form login có thể gặp 302, với REST exception handler tùy chỉnh có thể biến đổi body/status. Test phải phù hợp với cấu hình cụ thể; không dùng status duy nhất để kết luận một policy đúng.

## 13. Bài tập mở rộng và tiêu chí nghiệm thu

**Bài tập A — chứng minh lỗi IDOR:** trong nhánh thử nghiệm riêng, tạm bỏ `@PostAuthorize` ở `read`, chạy test `aliceCannotReadBobsNote` và quan sát test fail. Phục hồi annotation, test phải PASS. Giải thích vì sao `authenticated()` vẫn còn nhưng dữ liệu Bob bị lộ.

**Bài tập B — chống sửa chéo:** tạm bỏ `@PreAuthorize` khỏi `update`, chạy test `aliceCannotUpdateBobsNoteAndNoDataChanges`. Sau khi phục hồi, kiểm tra cả response 403 và content Bob không đổi. Vì sao kiểm tra `@PostAuthorize` sau khi save không đủ?

**Bài tập C — bảo vệ danh sách:** thêm endpoint lọc theo owner do client gửi (chỉ trong môi trường thử nghiệm), giữ `listForOwner` check ở service. Alice gọi owner=bob phải bị từ chối. Sau đó bỏ endpoint gây rủi ro và dùng danh tính từ `Authentication` như bản cuối.

**Bài tập D — chính sách chia sẻ:** mở rộng dữ liệu với `sharedWithUserIds`, viết policy `isOwnerOrShared` và test 3 trạng thái owner, người được chia sẻ, người không liên quan. Không cấp quyền sửa nếu tính năng chỉ cho phép chia sẻ đọc.

**Bài tập E — database thật:** chuyển repository sang JPA/SQL; viết query `WHERE id=? AND owner_id=?` và transaction update có điều kiện, test hai user đồng thời. Chỉ khi kiểm tra quyền và thao tác ghi cùng bảo toàn invariant mới xem như giải quyết được race.

**Checklist hoàn thành:**

- [ ] `@EnableMethodSecurity` đã bật và bean service được gọi qua proxy.
- [ ] URL/private note yêu cầu authentication; health có thể công khai.
- [ ] Alice/Bob đọc được note riêng và bị chặn khi đổi ID sang note người khác.
- [ ] Danh sách chỉ gồm note người gọi được phép đọc.
- [ ] Kiểm tra sửa nằm **trước** write và có bằng chứng dữ liệu không đổi khi 403.
- [ ] Test PUT có token CSRF hợp lệ để không nhầm 403 do CSRF với 403 do ownership.
- [ ] Test gọi service trực tiếp vẫn chặn client tự truyền owner khác.
- [ ] Có chính sách nhất quán cho missing object, admin, tenant và các API khác dùng object ID.
- [ ] Nếu dùng database thật, owner/user ID ổn định và update có điều kiện chống race.

Bạn đạt yêu cầu khi giải thích được **ai đang gọi**, **tài nguyên thuộc về ai**, **đánh giá quyền diễn ra trước hay sau method**, và **lý do các test chứng minh không có truy cập ngang hoặc thay đổi trái phép**.

## 14. Tài liệu đối chiếu

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): bật `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, SpEL, tham số method và AOP.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): phân quyền HTTP request và thứ tự rule.
- [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser` và security context trong test.
- [Spring Security 6.5 — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): `csrf()` và token không hợp lệ.
- [Spring Security — Testing Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/test/index.html): tích hợp Spring Test với Security filter.
- [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): lỗi truy cập đối tượng bằng ID và cách scope theo owner.

Tài liệu trực tuyến có version selector; đối với dự án cố định Spring Boot 3.3.5, hãy tra đúng nhánh Spring Security được Boot BOM quản lý trước khi áp dụng chi tiết API, matcher hay hành vi mặc định vào môi trường sản xuất.
