# Tách nhóm unit, slice, integration và kiểm thử đầu cuối

Trong dự án Spring Boot, nếu mọi phép kiểm đều chạy chung một tác vụ `./gradlew test`, một sửa đổi nhỏ có thể phải chờ hàng chục lần khởi động Spring context, migrations, container, HTTP server và dịch vụ thử nghiệm. CI chậm khiến vòng phản hồi kéo dài; CI quá dựa vào mock có thể rất nhanh nhưng để lọt lỗi cấu hình Spring, JPA, transaction hoặc API thực tế. Tách các nhóm kiểm thử không chỉ là gắn nhãn “nhanh/chậm”: đó là cách định nghĩa **ranh giới được kiểm chứng**, mức chi phí, trách nhiệm cô lập dữ liệu và cổng chất lượng tương ứng.

Bài Knowledge **“Tách nhóm unit, slice, integration và kiểm thử đầu cuối”** thuộc mục **Build và CI** của module **Spring Boot – testing**. Ta sẽ xây một dự án **Java 17+, Spring Boot 3.5.16, Gradle, JUnit Jupiter 5, Mockito, MockMvc, JPA/H2 và Java HttpClient**; tổ chức bốn nhóm bằng JUnit `@Tag`, chạy với Gradle tasks riêng `unitTest`, `sliceTest`, `integrationTest` và `e2eTest`, rồi cấu hình GitHub Actions để chạy nhóm nhanh khi mở pull request, kiểm integration trong CI và E2E trên **ứng dụng đã đóng gói/khởi động độc lập**.

**Nguyên tắc trung tâm:** *Unit kiểm quy tắc Java; slice kiểm một phần Spring integration; integration kiểm nhiều thành phần thực làm việc cùng nhau; E2E kiểm hành trình qua giao diện công khai của một deployment đang chạy.* Một test không trở nên “integration” chỉ vì đặt tên `SomeIntegrationTest`; cũng không trở nên “unit” chỉ vì chạy nhanh. Quan trọng nhất là **lỗi nào test có thể phát hiện và lỗi nào nó không nhìn thấy**.

## 1. Mục tiêu học tập

- Phân biệt unit, slice, integration và E2E theo dependency boundary, loại bằng chứng và rủi ro.
- Biết chọn `@WebMvcTest`, `@DataJpaTest`, `@RestClientTest`, `@JsonTest`, `ApplicationContextRunner`, `@SpringBootTest`, hoặc JUnit thuần.
- Sử dụng JUnit `@Tag("unit")`, `@Tag("slice")`, `@Tag("integration")`, `@Tag("e2e")`.
- Cấu hình Gradle `Test` tasks với `testClassesDirs` và `classpath` tường minh; không phụ thuộc test discovery ngầm.
- Hiểu `useJUnitPlatform`, `includeTags`, `excludeTags` và `--tests` kết hợp như thế nào.
- Bảo đảm bài test chưa gắn tag không bị **âm thầm bỏ sót** ở toàn bộ CI.
- Biết Gradle `test`, `check`, `build` chạy gì và các nhóm integration/E2E có được gọi hay không.
- Tách PR checks, integration checks, nightly/release E2E và kiểm các jobs bị skip.
- Phân biệt chạy `@SpringBootTest(RANDOM_PORT)` trong test JVM với E2E tới app `java -jar` đã khởi động ngoài process.
- Dùng dữ liệu riêng theo UUID/test run, transaction rollback đúng phạm vi, cleanup qua API/repository.
- Giải thích vì sao test `@Transactional` không rollback server-side commits ở `RANDOM_PORT`.
- Hiểu Spring TestContext cache, JUnit parallelism và Gradle forks để tránh tối ưu sai.
- Biết khi nào nên nâng từ tag filtering sang source sets/JVM Test Suite plugin.
- Đọc JUnit XML/report theo từng task, phát hiện “0 tests executed nhưng build xanh”.
- Nêu đúng giới hạn kết luận: không suy load/performance/production readiness chỉ từ một nhóm test.

## 2. Bốn nhóm là bốn phạm vi bằng chứng

| Nhóm | Ranh giới chủ yếu | Thành phần thật | Thường giả lập/giới hạn | Câu hỏi cần trả lời |
|---|---|---|---|---|
| **Unit** | Object/method Java | Domain/service logic | Repository, HTTP, clock | Quy tắc và nhánh lỗi có đúng? |
| **Slice** | Một mảnh Spring context | MVC+Jackson, JPA hoặc HTTP client adapter | Layers ngoài slice | Controller/serializer/query/client contract đúng? |
| **Integration** | Nhiều layers/dependencies | Full Spring context, server/DB tùy test | Các service ngoài phạm vi được công bố | DI/transaction/HTTP/persistence cùng hoạt động? |
| **E2E** | Public API của app đang chạy | Executable artifact và đường request được định nghĩa | Thường không truy cập beans/internal repository trong test | Hành trình người dùng thật qua deployment hoạt động? |

Đây là **quy ước của bài**, không phải phân loại phổ quát. Một số nhóm gọi full Spring context + real HTTP trong cùng JVM là end-to-end; ở đây nó thuộc **integration** để dành **E2E** cho một bài test độc lập với Spring TestContext, chỉ gọi một app đã start/deploy.

Một `@WebMvcTest` chạy chậm vì application slice có Security filters vẫn là slice. Một test JUnit dùng Docker/PostgreSQL thật là integration dù không có annotation `@SpringBootTest`. Phân loại theo nguồn dữ liệu và các thành phần tham gia, không theo thời lượng.

## 3. Lợi ích thực tế khi chia nhóm trong CI

```text
Trước:
  gradle test
    - 200 pure unit
    - 60 MVC/JPA slice
    - 20 Spring full-context
    - 8 Testcontainers
    - 5 gọi shared staging
  => PR chậm, dễ bị flaky network làm mọi thay đổi bị chặn

Sau:
  ./gradlew test
    - unit + slice + mọi test untagged
    - kiểm nhanh theo từng commit

  ./gradlew integrationTest
    - app context/DB/server/container tự sở hữu trong CI

  ./gradlew e2eTest -Pe2eBaseUrl=http://127.0.0.1:18080
    - app JAR start riêng, test chỉ gọi public HTTP
    - chạy ở job được kiểm soát

  Các nhóm có JUnit XML/HTML report riêng và quality gate riêng.
```

Việc tách **không được** làm mất những test integration duy nhất bảo vệ transaction hoặc DB dialect. Nếu một lỗi chỉ xảy ra ở kết nối giữa hai lớp, việc dồn hết tests vào nhóm unit để đạt PR thời gian thấp sẽ làm coverage kém đi. Đánh giá kết quả cuối cùng bằng **thời gian feedback, số tests thực thi, độ độc lập và khả năng phát hiện lỗi**.

## 4. Cách chọn phạm vi nhỏ nhất nhưng không đánh mất lỗi

| Lỗi được giả định | Scope phù hợp tối thiểu | Cách chứng minh |
|---|---|---|
| Title rỗng được phép tạo | Unit | Assert exception và không gọi repository |
| “Hoàn tất” hai lần không bị chặn | Unit | State transition và exception |
| Route `POST /api/tasks` sai | MVC slice | MockMvc assert 201/JSON |
| JSON field `completed` đổi tên | MVC slice | JSONPath |
| `findByTitleIgnoreCase` bị sai | JPA slice | Query H2 với khác kiểu chữ |
| Entity state không flush | JPA slice/integration | flush-clear-reload |
| Service mất `@Transactional` | Integration thực, không bọc transaction test | Real HTTP + DB readback |
| Spring bean thiếu | Integration | ApplicationContext fail |
| Executable JAR không khởi động | E2E/packaging | java -jar + readiness |
| TLS/nginx/Ingress sai | E2E qua gateway thực | Network/auth contract |
| PostgreSQL-specific SQL | Integration với Postgres | Testcontainers + migrations |
| p95 dưới tải 100 RPS | Performance/load riêng | k6/Gatling, không đo bằng 1 JUnit assert |
| Downstream mất mạng | Fault-injection integration | Controlled proxy/downstream |

Một test `contextLoads()` dù dùng `@SpringBootTest` không bảo vệ nghiệp vụ. Chất lượng đến từ **assertion có khả năng fail khi bug tồn tại**, chứ không chỉ từ việc tạo ApplicationContext lớn.

## 5. Test pyramid, chi phí và tần suất chạy

Nhóm unit thường nhiều nhất vì chi phí thấp và chẩn đoán lỗi nhanh. Slice bảo vệ những hành vi mà unit mocks không nhìn thấy: Jackson, Spring MVC, Bean Validation, repository query và Data JPA. Integration bảo vệ wiring/transaction/HTTP/DB, còn E2E bảo vệ hành trình thông qua một deployment. Đừng đặt tỉ lệ cứng 70/20/10 nếu domain không phù hợp.

Một kiến trúc Build/CI có thể dùng:

- **Mỗi pull request:** unit + slice, một số integration thiết yếu và static analysis.
- **Trước merge/nhánh chính:** integration với database/container isolated; các checks bắt buộc.
- **Nightly:** nhóm tích hợp đắt/khó, phân tích flaky và performance baseline.
- **Release candidate:** E2E qua artifact triển khai, kịch bản quyền/tenant/rollback quan trọng.
- **Production smoke:** synthetic probes có phạm vi hạn chế, không thay E2E có data cleanup.

Tần suất là quyết định dựa trên risk-budget. Một integration test chạy dưới 2 giây và bảo vệ bug cực nguy hiểm có thể xứng đáng chạy PR. Một E2E mất 10 phút trên shared staging không nên chạy mọi code change nếu có cách nhanh hơn để bảo vệ phần lớn logic.

## 6. Ví dụ thực hành: API checklist có persistence

Ta tạo một API nhỏ:

| Request | Kết quả |
|---|---|
| `POST /api/tasks` body `{"title":"Release"}` | 201, task mới với UUID, `completed=false` |
| `GET /api/tasks/{id}` | 200, id/title/completed |
| `POST /api/tasks/{id}/complete` | 200, `completed=true` |
| Hoàn tất lại cùng task | 409, `ALREADY_COMPLETED` |
| Title trống hoặc dài quá 80 | 400, `INVALID_TITLE` |
| ID không tồn tại | 404, `TASK_NOT_FOUND` |
| `DELETE /api/tasks/{id}` | 204, phục vụ cleanup E2E |

Các tầng:

```text
TaskController + TaskErrorAdvice
           |
           v
TaskService (@Transactional)
           |
           v
TaskRepository (Spring Data JPA)
           |
           v
ChecklistItem (H2 embedded)

Unit:         Service + Mockito repository
MVC slice:    Controller + MockMvc + Mockito service
JPA slice:    Repository + EntityManager + H2
Integration:  RANDOM_PORT + TestRestTemplate + service/repo H2 thật
E2E:          Java HttpClient -> app JAR khởi động riêng
```

Ứng dụng demo không có authentication, multi-tenant ownership, concurrency load hoặc production DB migration. Không dùng nguyên trạng để chứa dữ liệu khách hàng. Mục tiêu ở đây là **tách bằng chứng kiểm thử và tổ chức chúng trong Gradle/CI**.

## 7. Cây thư mục dự án

```text
spring-boot-test-groups/
  settings.gradle
  build.gradle
  src/main/java/com/example/testgroups/
    TestGroupsApplication.java
    ChecklistItem.java
    TaskRepository.java
    CreateTaskRequest.java
    TaskResponse.java
    InvalidTitleException.java
    MissingTaskException.java
    AlreadyCompletedException.java
    TaskService.java
    TaskController.java
    TaskErrorAdvice.java
  src/test/resources/
    application.properties
  src/test/java/com/example/testgroups/
    TaskServiceUnitTest.java
    TaskControllerSliceTest.java
    TaskRepositorySliceTest.java
    TaskHttpIntegrationTest.java
    TaskExternalE2ETest.java
  .github/workflows/
    verify.yml
```

Mẫu đặt **cả bốn nhóm trong cùng `src/test/java`** để một project dễ copy, nhưng các Gradle Test tasks lọc bằng JUnit tags. Đây là **runtime test filtering**: tất cả nhóm vẫn cùng test compilation classpath. Mục 30 giải thích cách tách `sourceSets` hoặc JVM Test Suite plugin khi muốn giới hạn dependency thực sự.

## 8. Gradle dependencies và các task kiểm thử

**`settings.gradle`**

```groovy
rootProject.name = 'spring-boot-test-groups'
```

**`build.gradle`** — file hoàn chỉnh cho project demo:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

// PR fast group. Untagged tests are INCLUDED so they cannot
// silently disappear from every task.
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'integration', 'e2e'
    }
    reports.junitXml.required = true
    reports.html.required = true
}

tasks.register('unitTest', Test) {
    group = 'verification'
    description = 'Run unit-tagged tests.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'unit'
    }
}

tasks.register('sliceTest', Test) {
    group = 'verification'
    description = 'Run MVC/JPA slice-tagged tests.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'slice'
    }
}

tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Run full-context integration tests.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'integration'
    }
    shouldRunAfter tasks.named('test')
    maxParallelForks = 1
}

tasks.register('e2eTest', Test) {
    group = 'verification'
    description = 'Run external E2E against approved local app.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'e2e'
    }
    systemProperty 'e2e.baseUrl',
            providers.gradleProperty('e2eBaseUrl').orElse('').get()
    maxParallelForks = 1
}
```

**Tại sao gán `testClassesDirs` và `classpath` cho custom Test tasks?** Theo tài liệu Gradle, task `Test` mới không tự biết nên dùng lớp nào và execution classpath nào. Hai thuộc tính trên chỉ chính xác source set `test` được biên dịch. Với Gradle các phiên bản mới, dựa vào ngầm định có thể dẫn đến task `NO-SOURCE` hoặc không thấy tests.

**Tại sao `test` dùng `excludeTags` thay vì chỉ `includeTags 'unit','slice'`?** Nếu một developer quên gắn `@Tag` cho test mới, cấu hình include-only có thể bỏ qua nó trong tất cả jobs. Mẫu này cho **untagged** chạy trong `test`; CI vẫn nên có bước audit tags để phân loại đúng.

## 9. Cách `@Tag` được dùng trong JUnit 5

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("unit")
class ExampleUnitTest {
    @Test
    void rule() {
        // Java-level assertion
    }
}
```

Trong các file thật bên dưới, tag đặt trên **test class**. JUnit Jupiter cho phép test methods thừa hưởng tag class. Mỗi class có **một primary scope tag**: `unit`, `slice`, `integration` hoặc `e2e`.

Nếu một method vừa tag `slice` vừa tag `integration`, nó có thể chạy hai lần khi CI gọi hai task. Nếu hành vi có side effects, điều này làm data cleanup phức tạp và dễ double execution. Có thể thêm tag phụ như `slow`, `postgres` nhưng không lẫn lộn primary scope.

### 9.1. Task nào chạy bài nào?

| Gradle task | Loại lọc | Test chạy |
|---|---|---|
| `test` | exclude `integration`, `e2e` | Unit, slice, untagged |
| `unitTest` | include `unit` | Chỉ unit |
| `sliceTest` | include `slice` | Chỉ slice |
| `integrationTest` | include `integration` | Chỉ integration |
| `e2eTest` | include `e2e` | Chỉ E2E |

`./gradlew check` và `./gradlew build` từ Java plugin mặc định chạy `test`, **không tự chạy các task integration/e2e mới đăng ký** nếu bạn không thêm dependency/call riêng. Vì vậy báo cáo phải phân biệt “fast pass” với “all stages pass”.

## 10. Spring Boot application root

**`src/main/java/com/example/testgroups/TestGroupsApplication.java`**

```java
package com.example.testgroups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestGroupsApplication {

    public static void main(String[] args) {
        SpringApplication.run(TestGroupsApplication.class, args);
    }
}
```

Có một application root trong cùng package giúp `@WebMvcTest`, `@DataJpaTest` và full `@SpringBootTest` tìm đúng configuration. Test không được tự thêm một SpringBootApplication khác trong test sources rồi làm mọi slice load config ngoài ý muốn.

## 11. JPA entity và repository

**`src/main/java/com/example/testgroups/ChecklistItem.java`**

```java
package com.example.testgroups;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.Objects;

@Entity
@Table(name = "checklist_items")
public class ChecklistItem {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, length = 80)
    private String title;

    @Column(nullable = false)
    private boolean completed;

    @Version
    private Long version;

    protected ChecklistItem() {
        // JPA constructor
    }

    public ChecklistItem(String id, String title) {
        this.id = Objects.requireNonNull(id);
        this.title = Objects.requireNonNull(title);
        this.completed = false;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isCompleted() {
        return completed;
    }

    public void complete() {
        if (completed) {
            throw new AlreadyCompletedException();
        }
        completed = true;
    }
}
```

**`src/main/java/com/example/testgroups/TaskRepository.java`**

```java
package com.example.testgroups;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TaskRepository
        extends JpaRepository<ChecklistItem, String> {

    Optional<ChecklistItem> findByTitleIgnoreCase(String title);
}
```

`@Version` cung cấp optimistic locking khi có concurrent writes, nhưng bài không test cạnh tranh nhiều transactions; không được tuyên bố hệ thống chống mọi duplicate requests. `findByTitleIgnoreCase` tạo tình huống JPA slice hữu ích mà mock repository không thể kiểm.

## 12. Request/response records và exception types

**`src/main/java/com/example/testgroups/CreateTaskRequest.java`**

```java
package com.example.testgroups;

public record CreateTaskRequest(String title) {
}
```

**`src/main/java/com/example/testgroups/TaskResponse.java`**

```java
package com.example.testgroups;

public record TaskResponse(
        String id, String title, boolean completed) {
}
```

**`src/main/java/com/example/testgroups/InvalidTitleException.java`**

```java
package com.example.testgroups;

public class InvalidTitleException
        extends IllegalArgumentException {
}
```

**`src/main/java/com/example/testgroups/MissingTaskException.java`**

```java
package com.example.testgroups;

public class MissingTaskException
        extends RuntimeException {
}
```

**`src/main/java/com/example/testgroups/AlreadyCompletedException.java`**

```java
package com.example.testgroups;

public class AlreadyCompletedException
        extends RuntimeException {
}
```

Dùng exception theo domain để controller advice map đúng mã lỗi; không catch tất cả `RuntimeException` rồi trả `400`. Validation title trong `TaskService`, không phụ thuộc bean validation starter. Nếu chuyển sang `@Valid`/`@NotBlank`, phải thêm `spring-boot-starter-validation` và tests tương ứng.

## 13. Service thật: nơi bắt transaction và business rules

**`src/main/java/com/example/testgroups/TaskService.java`**

```java
package com.example.testgroups;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {

    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public TaskResponse create(String title) {
        if (title == null
                || title.isBlank()
                || title.strip().length() > 80) {
            throw new InvalidTitleException();
        }

        ChecklistItem item = new ChecklistItem(
                UUID.randomUUID().toString(), title.strip());
        repository.save(item);
        return view(item);
    }

    @Transactional(readOnly = true)
    public TaskResponse read(String id) {
        return view(repository.findById(id)
                .orElseThrow(MissingTaskException::new));
    }

    @Transactional
    public TaskResponse complete(String id) {
        ChecklistItem item = repository.findById(id)
                .orElseThrow(MissingTaskException::new);
        item.complete();
        // Managed entity update is flushed at transaction commit.
        return view(item);
    }

    @Transactional
    public void delete(String id) {
        if (!repository.existsById(id)) {
            throw new MissingTaskException();
        }
        repository.deleteById(id);
    }

    private TaskResponse view(ChecklistItem item) {
        return new TaskResponse(
                item.getId(), item.getTitle(), item.isCompleted());
    }
}
```

Test unit tạo service bằng `new TaskService(mockRepository)` nên **không có Spring AOP transaction proxy**. Entity mutate trong unit vẫn đổi boolean, nhưng DB commit không được chứng minh. Integration test qua HTTP kiểm một repository call sau request để phát hiện trường hợp entity mutation không được persist.

## 14. Controller và advice: public HTTP boundary

**`src/main/java/com/example/testgroups/TaskController.java`**

```java
package com.example.testgroups;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @RequestBody CreateTaskRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(request.title()));
    }

    @GetMapping("/{id}")
    public TaskResponse read(@PathVariable String id) {
        return service.read(id);
    }

    @PostMapping("/{id}/complete")
    public TaskResponse complete(@PathVariable String id) {
        return service.complete(id);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        service.delete(id);
    }
}
```

**`src/main/java/com/example/testgroups/TaskErrorAdvice.java`**

```java
package com.example.testgroups;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class TaskErrorAdvice {

    public record ErrorBody(String code) {
    }

    @ExceptionHandler(InvalidTitleException.class)
    public ResponseEntity<ErrorBody> invalidTitle() {
        return ResponseEntity.badRequest()
                .body(new ErrorBody("INVALID_TITLE"));
    }

    @ExceptionHandler(MissingTaskException.class)
    public ResponseEntity<ErrorBody> missingTask() {
        return ResponseEntity.status(404)
                .body(new ErrorBody("TASK_NOT_FOUND"));
    }

    @ExceptionHandler(AlreadyCompletedException.class)
    public ResponseEntity<ErrorBody> alreadyCompleted() {
        return ResponseEntity.status(409)
                .body(new ErrorBody("ALREADY_COMPLETED"));
    }
}
```

`TaskController` là HTTP adapter mỏng. Slice MVC kiểm method/path/status/JSON/advice; integration kiểm controller→service→JPA thật; E2E kiểm behavior qua executable artifact. Không có Spring Security trong demo: ứng dụng production cần authentication/authorization và negative tests riêng.

## 15. Test properties tránh đụng database thật

**`src/test/resources/application.properties`**

```properties
spring.jpa.hibernate.ddl-auto=create-drop
spring.datasource.generate-unique-name=true
spring.jpa.open-in-view=false
```

- `create-drop` dành cho embedded H2 trong test, **không** áp dụng cho production.
- `generate-unique-name` giảm khả năng nhiều ApplicationContexts trùng H2 in-memory database name.
- `open-in-view=false` tránh phụ thuộc persistence context kéo dài qua HTTP serialization.
- Unit tests không đọc properties này vì không nạp Spring.
- E2E khởi động JAR riêng, **không tự tải `src/test/resources`**; CI cung cấp startup arguments tách biệt.

Với production database cần Flyway/Liquibase migrations và test trên database đúng dialect; H2 không thay thế PostgreSQL locking, JSONB, timezone/unique semantics.

## 16. Unit test: không Spring, không database, không network

**`src/test/java/com/example/testgroups/TaskServiceUnitTest.java`**

```java
package com.example.testgroups;

import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@Tag("unit")
@ExtendWith(MockitoExtension.class)
class TaskServiceUnitTest {

    @Mock
    TaskRepository repository;

    TaskService service;

    @BeforeEach
    void setup() {
        service = new TaskService(repository);
    }

    @Test
    void createTrimsTitleAndWritesOneEntity() {
        TaskResponse result = service.create("  Release  ");

        ArgumentCaptor<ChecklistItem> captor =
                ArgumentCaptor.forClass(ChecklistItem.class);
        verify(repository).save(captor.capture());

        assertEquals("Release", result.title());
        assertFalse(result.completed());
        assertEquals("Release",
                captor.getValue().getTitle());
        assertEquals(result.id(), captor.getValue().getId());
    }

    @Test
    void invalidTitleDoesNotCallRepository() {
        assertThrows(InvalidTitleException.class,
                () -> service.create("   "));
        verifyNoInteractions(repository);
    }

    @Test
    void completeChangesDomainState() {
        ChecklistItem item = new ChecklistItem(
                "u1", "Plan");
        when(repository.findById("u1"))
                .thenReturn(Optional.of(item));

        TaskResponse result = service.complete("u1");

        assertTrue(item.isCompleted());
        assertTrue(result.completed());
        verify(repository).findById("u1");
    }

    @Test
    void duplicateCompletionFails() {
        ChecklistItem item = new ChecklistItem(
                "u2", "Review");
        item.complete();
        when(repository.findById("u2"))
                .thenReturn(Optional.of(item));

        assertThrows(AlreadyCompletedException.class,
                () -> service.complete("u2"));
    }

    @Test
    void missingTaskFails() {
        when(repository.findById("unknown"))
                .thenReturn(Optional.empty());

        assertThrows(MissingTaskException.class,
                () -> service.read("unknown"));
    }
}
```

**5 unit methods** kiểm input boundary, title normalization, state transition, duplicate error và missing record. Mocks per test không có shared Spring context. Không dùng `@SpringBootTest` để chứng minh một quy tắc thuần Java.

**Giới hạn:** `@Transactional` trên service trong test này **không kích hoạt proxy**. Nếu developer xóa annotation, `completeChangesDomainState` vẫn pass. Điều này có chủ đích: transaction được kiểm ở integration.

## 17. MVC slice: thật MVC, giả service

**`src/test/java/com/example/testgroups/TaskControllerSliceTest.java`**

```java
package com.example.testgroups;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Tag("slice")
@WebMvcTest(TaskController.class)
class TaskControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    TaskService taskService;

    @Test
    void createReturns201AndJsonContract() throws Exception {
        when(taskService.create("Release"))
                .thenReturn(new TaskResponse(
                        "t1", "Release", false));

        mvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Release\"}"))
                .andExpectAll(
                        status().isCreated(),
                        jsonPath("$.id").value("t1"),
                        jsonPath("$.completed").value(false));

        verify(taskService).create("Release");
    }

    @Test
    void getMapsTaskToJson() throws Exception {
        when(taskService.read("t1"))
                .thenReturn(new TaskResponse(
                        "t1", "Release", false));

        mvc.perform(get("/api/tasks/t1"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.title").value("Release"));
    }

    @Test
    void completionMapsToService() throws Exception {
        when(taskService.complete("t1"))
                .thenReturn(new TaskResponse(
                        "t1", "Release", true));

        mvc.perform(post("/api/tasks/t1/complete"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.completed").value(true));
    }

    @Test
    void invalidTitleMapsTo400() throws Exception {
        when(taskService.create(""))
                .thenThrow(new InvalidTitleException());

        mvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"\"}"))
                .andExpectAll(
                        status().isBadRequest(),
                        jsonPath("$.code").value("INVALID_TITLE"));
    }

    @Test
    void duplicateCompletionMapsTo409() throws Exception {
        when(taskService.complete("t1"))
                .thenThrow(new AlreadyCompletedException());

        mvc.perform(post("/api/tasks/t1/complete"))
                .andExpectAll(
                        status().isConflict(),
                        jsonPath("$.code").value("ALREADY_COMPLETED"));
    }
}
```

**5 slice methods** kiểm route, JSON, HTTP response và exception advice. `@WebMvcTest` quét selected controller, MVC infrastructure và các thành phần web như advice; `@MockitoBean` đưa service giả vào slice. Khi service validation bị xóa trong production, `invalidTitleMapsTo400` vẫn có thể pass vì mock được cấu hình ném exception: **unit test mới chứng minh validation**, integration test chứng minh nối lớp.

## 18. JPA slice: query và dirty checking thật với H2

**`src/test/java/com/example/testgroups/TaskRepositorySliceTest.java`**

```java
package com.example.testgroups;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("slice")
@DataJpaTest
class TaskRepositorySliceTest {

    @Autowired
    TaskRepository repository;

    @Autowired
    EntityManager entityManager;

    @Test
    void titleIgnoreCaseDerivedQueryWorks() {
        repository.saveAndFlush(
                new ChecklistItem("j1", "Release Notes"));

        assertTrue(repository.findByTitleIgnoreCase(
                "rElEaSe nOtEs").isPresent());
    }

    @Test
    void dirtyCheckingPersistsAfterFlushAndClear() {
        ChecklistItem item = repository.saveAndFlush(
                new ChecklistItem("j2", "Write docs"));

        item.complete();
        entityManager.flush();
        entityManager.clear();

        ChecklistItem loaded = repository.findById("j2")
                .orElseThrow();

        assertTrue(loaded.isCompleted());
        assertEquals("Write docs", loaded.getTitle());
    }
}
```

**2 JPA slice methods** dùng `@DataJpaTest`, mặc định có transaction rollback theo test method. `flush/clear` giúp kiểm database state, không chỉ state còn ở first-level cache. Một Unit test Mockito trả sẵn entity không bắt được lỗi query/SQL mapping.

H2 không đảm bảo mọi SQL/locking semantics giống production. Nếu ứng dụng dùng PostgreSQL-specific queries hoặc migrations, thêm integration group với Postgres Testcontainers, không biến `@DataJpaTest` H2 thành lời cam kết cho mọi database.

## 19. Integration: full Spring context, HTTP thật và commit thật

**`src/test/java/com/example/testgroups/TaskHttpIntegrationTest.java`**

```java
package com.example.testgroups;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("integration")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TaskHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    TaskRepository repository;

    private final List<String> ownedIds = new ArrayList<>();

    @AfterEach
    void cleanup() {
        for (String id : ownedIds) {
            if (repository.existsById(id)) {
                repository.deleteById(id);
            }
        }
    }

    private String create(String title) {
        ResponseEntity<TaskResponse> response =
                http.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest(title),
                        TaskResponse.class);

        assertEquals(201, response.getStatusCode().value());
        assertNotNull(response.getBody());

        String id = response.getBody().id();
        ownedIds.add(id);
        return id;
    }

    @Test
    void createCompleteAndReadCommittedResult() {
        String id = create("Integration");

        ResponseEntity<TaskResponse> completed =
                http.postForEntity(
                        "/api/tasks/{id}/complete",
                        null, TaskResponse.class, id);

        assertEquals(200, completed.getStatusCode().value());
        assertNotNull(completed.getBody());
        assertTrue(completed.getBody().completed());

        ResponseEntity<TaskResponse> read =
                http.getForEntity(
                        "/api/tasks/{id}",
                        TaskResponse.class, id);

        assertEquals(200, read.getStatusCode().value());
        assertNotNull(read.getBody());
        assertTrue(read.getBody().completed());

        assertTrue(repository.findById(id)
                .orElseThrow().isCompleted());
    }

    @Test
    void badTitleReturns400AndDoesNotCreateTask() {
        long countBefore = repository.count();

        ResponseEntity<TaskErrorAdvice.ErrorBody> response =
                http.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest(" "),
                        TaskErrorAdvice.ErrorBody.class);

        assertEquals(400, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("INVALID_TITLE", response.getBody().code());
        assertEquals(countBefore, repository.count());
    }

    @Test
    void completingTwiceReturns409() {
        String id = create("Complete only once");

        ResponseEntity<TaskResponse> first =
                http.postForEntity(
                        "/api/tasks/{id}/complete",
                        null, TaskResponse.class, id);
        assertEquals(200, first.getStatusCode().value());

        ResponseEntity<TaskErrorAdvice.ErrorBody> second =
                http.postForEntity(
                        "/api/tasks/{id}/complete",
                        null, TaskErrorAdvice.ErrorBody.class, id);

        assertEquals(409, second.getStatusCode().value());
        assertNotNull(second.getBody());
        assertEquals("ALREADY_COMPLETED",
                second.getBody().code());
    }
}
```

**3 integration methods**, Spring Boot khởi embedded server trên random port. TestRestTemplate sử dụng actual local TCP request; controller/service/repository/H2 đều là thật. Test **không** có class-level `@Transactional`: client thread và server transaction khác nhau, rollback ở test thread **không** hoàn nguyên server commits.

`@AfterEach` xóa **chỉ các ID đã tạo bởi test**, giúp không làm bẩn test khác khi context/database cache được reuse. Khi CI process bị kill, Java lifecycle không bảo đảm cleanup; môi trường H2 isolated hoặc database per-job là hàng rào bổ sung. Không xóa toàn bảng shared chỉ để giảm vài dòng.

### 19.1. Vì sao integration khác MVC slice?

Nếu `TaskService.complete` mất `@Transactional`, entity mutate trong pure unit vẫn đúng, còn MVC slice mock service không chạy code. Real HTTP integration với repository readback có thể phát hiện **dữ liệu không commit**. Không dùng `@SpringBootTest + @MockitoBean TaskService` để kết luận đã kiểm transaction service: mock đã thay logic/AOP cần test.

## 20. E2E: black-box Java HttpClient tới app đã start

E2E theo bài này **không inject Spring beans, không đọc repository trực tiếp và không khởi context trong JUnit test process**. Nó sử dụng `java.net.http.HttpClient` để gọi ứng dụng đóng gói `java -jar`. Để tránh gửi thao tác POST/DELETE nhầm tới shared staging/production, demo **chỉ chấp nhận base URL loopback** với port xác định.

**`src/test/java/com/example/testgroups/TaskExternalE2ETest.java`**

```java
package com.example.testgroups;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("e2e")
class TaskExternalE2ETest {

    private static final ObjectMapper JSON =
            new ObjectMapper();

    @Test
    void createCompleteReadAndDeleteThroughPublicHttp()
            throws Exception {

        String base = System.getProperty(
                "e2e.baseUrl", "").replaceAll("/+$", "");

        // This educational E2E intentionally permits ONLY loopback.
        assertTrue(base.matches(
                "http://(127\\.0\\.0\\.1|localhost):[0-9]{2,5}"),
                "Set -Pe2eBaseUrl to an approved local HTTP port");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        String id = null;
        String title = "e2e-" + UUID.randomUUID();

        try {
            HttpRequest create = HttpRequest.newBuilder(
                            URI.create(base + "/api/tasks"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            JSON.writeValueAsString(
                                    new CreateTaskRequest(title))))
                    .build();

            HttpResponse<String> created = client.send(
                    create, HttpResponse.BodyHandlers.ofString());

            assertEquals(201, created.statusCode());
            JsonNode body = JSON.readTree(created.body());
            id = body.get("id").asText();
            assertEquals(title, body.get("title").asText());
            assertFalse(body.get("completed").asBoolean());

            HttpRequest complete = HttpRequest.newBuilder(
                            URI.create(base + "/api/tasks/"
                                    + id + "/complete"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.noBody())
                    .build();

            HttpResponse<String> done = client.send(
                    complete, HttpResponse.BodyHandlers.ofString());
            assertEquals(200, done.statusCode());
            assertTrue(JSON.readTree(done.body())
                    .get("completed").asBoolean());

            HttpRequest read = HttpRequest.newBuilder(
                            URI.create(base + "/api/tasks/" + id))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> fetched = client.send(
                    read, HttpResponse.BodyHandlers.ofString());
            assertEquals(200, fetched.statusCode());
            assertTrue(JSON.readTree(fetched.body())
                    .get("completed").asBoolean());

        } finally {
            if (id != null) {
                HttpRequest delete = HttpRequest.newBuilder(
                                URI.create(base + "/api/tasks/" + id))
                        .timeout(Duration.ofSeconds(5))
                        .DELETE()
                        .build();

                HttpResponse<String> response = client.send(
                        delete, HttpResponse.BodyHandlers.ofString());
                assertEquals(204, response.statusCode(),
                        "E2E cleanup must delete test-owned task");
            }
        }
    }
}
```

**1 E2E method** tạo/hoàn tất/đọc/xóa task qua HTTP public. Input title có UUID để không trùng giữa các runs. Base URL qua Gradle property `-Pe2eBaseUrl` được truyền thành JVM system property; nếu thiếu, test **FAIL**, không âm thầm skip. Connect/request timeouts hữu hạn.

**Giới hạn trung thực:** Local java -jar + H2 E2E chứng minh executable JAR/startup/HTTP/JPA trên máy test. Nó **không** kiểm HTTPS Ingress, OAuth, PostgreSQL production, Redis hay multi-pod vì chúng không thuộc topology này. Một staging E2E cần allowlist, test identity, environment approval, data isolation/retention và contract phù hợp, không chỉ xóa regex safety guard.

### 20.1. Cleanup khi CI crash

`finally` hoạt động khi flow Java thoát, nhưng không chạy nếu process bị kill hoặc server commit rồi client mất response **trước khi lấy ID**. Production-grade E2E cần test-run prefix/idempotency key, TTL hoặc janitor và isolated tenant/database để xử lý orphaned records. Trong demo, app/H2 được tạo riêng cho job và dừng sau test, giảm tác động ngoài ý muốn.

## 21. Tổng số tests và phạm vi phát hiện

| Class | Tag | Methods | Phát hiện chính |
|---|---|---:|---|
| `TaskServiceUnitTest` | unit | 5 | Rule/validation/state |
| `TaskControllerSliceTest` | slice | 5 | Route/JSON/advice |
| `TaskRepositorySliceTest` | slice | 2 | Derived query/JPA flush |
| `TaskHttpIntegrationTest` | integration | 3 | Real HTTP/wiring/commit |
| `TaskExternalE2ETest` | e2e | 1 | Black-box executable app |
| **Tổng** | | **16** | Các tầng có trách nhiệm riêng |

`./gradlew test` của demo dự kiến chạy **12 methods** ở unit+slice, không chạy 3 integration/1 E2E. `./gradlew unitTest` chạy 5; `sliceTest` chạy 7; `integrationTest` chạy 3; `e2eTest` chạy 1 nếu được gọi. Đây là **số tests được thiết kế từ source**, **không** phải kết quả đếm từ một lần chạy Gradle thực tế.

## 22. Lệnh chạy local và debugging

```bash
# Gradle Wrapper phải tồn tại trước khi dùng.
./gradlew test

# Chạy các nhóm độc lập:
./gradlew unitTest
./gradlew sliceTest
./gradlew integrationTest

# Chọn một method trong đúng task:
./gradlew unitTest \
  --tests com.example.testgroups.TaskServiceUnitTest.invalidTitleDoesNotCallRepository

# Build artifact, chạy server ở terminal khác:
./gradlew bootJar
java -jar build/libs/spring-boot-test-groups-0.0.1-SNAPSHOT.jar \
  --server.port=18080 \
  --spring.jpa.hibernate.ddl-auto=create-drop

# Khi server local đã ready:
./gradlew e2eTest -Pe2eBaseUrl=http://127.0.0.1:18080
```

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`, dùng cú pháp xuống dòng PowerShell hoặc lệnh Java một dòng. Các tasks có `includeTags` và filter `--tests` sẽ áp dụng **cả hai** điều kiện; chọn một integration class qua `unitTest --tests` không làm nó đổi tag.

**Lưu ý:** Nếu chưa có Gradle Wrapper, tạo bằng Gradle/IDE theo convention và commit `gradlew`, `gradlew.bat`, `gradle/wrapper/*`. Cặp `build.gradle/settings.gradle` không tự sinh wrapper.

## 23. Test discovery: kiểm cả số methods thực sự chạy

Một pipeline có thể báo **BUILD SUCCESSFUL** nhưng không có test vì:

- Custom `Test` task thiếu `testClassesDirs` hoặc `classpath`.
- Không có `@Tag("integration")` do quên/case mismatch.
- File đặt sai source directory hoặc không compile.
- JUnit Platform/TestEngine thiếu.
- `--tests` lọc sai class/method.
- Tất cả tests bị `@Disabled` hoặc assumptions skip.
- Gradle task báo `NO-SOURCE`.
- Tag expression include/exclude sai.

Dùng:

```bash
./gradlew tasks --group verification
./gradlew test --info
./gradlew integrationTest --info
./gradlew e2eTest --dry-run
```

`--dry-run` **không thực thi tests**, chỉ xem task graph. Đọc JUnit XML/số tests executed trong CI để xác nhận. Đặt guard yêu cầu có những test classes quan trọng hoặc số phương thức tối thiểu theo policy; khi thêm/xóa test, cập nhật guard qua code review. Đừng coi stage “0 tests executed” là integration pass thực chất.

## 24. Spring context cache và chi phí thực thi

Spring TestContext cache dùng khóa cấu hình gồm class/location, active profiles, properties, bean overrides, DynamicPropertySource customizers và web resource context. Các classes dùng **cùng key** trong cùng JVM có thể reuse ApplicationContext; nhưng unit thuần không cần context, và JVM fork/process khác không chia sẻ static cache.

**Spring Framework 6.2 default max size là 32 contexts, LRU eviction.** Có thể thay bằng JVM system property `spring.test.context.cache.maxSize` khi có lý do đo đạc, nhưng không tự tăng rồi kết luận suite chắc chắn nhanh hơn.

- `@WebMvcTest` có một context slice; `@DataJpaTest` là key khác.
- `@SpringBootTest(RANDOM_PORT)` là full web server context, khác MOCK.
- `@MockitoBean` qualifiers/names có thể ảnh hưởng key; đặt nhất quán khi cùng bean target.
- `@ActiveProfiles`/`@TestPropertySource` khác tạo các contexts hợp lệ khác nhau.
- `@DirtiesContext` buộc evict/reload; dùng khi context thật sự dirty, không chỉ để xóa một DB row.
- Gradle `maxParallelForks`, `forkEvery` có trade-off reuse/memory/capacity.
- E2E chạy app ngoài process, không dùng Spring TestContext cache của JUnit.

**Điều kiện bắt buộc:** Reuse **Spring bean graph**, nhưng không reuse **mutable test state** giữa methods. Rollback DB, xóa test-owned records, reset Clock/cache/mock/threads, không dựa vào thứ tự chạy.

## 25. Isolation riêng cho từng nhóm

| State | Unit | Slice | Integration | E2E |
|---|---|---|---|---|
| Java object | Khởi tạo mới mỗi test | Có thể context singleton reuse | Context reuse, reset mutable state | Không truy cập trực tiếp |
| Database | Mock repo | @DataJpaTest rollback | ID riêng, cleanup/test transaction đúng boundary | Test tenant/ID, cleanup qua API |
| HTTP port | Không có | MockMvc không mở socket | RANDOM_PORT | Port deployment được chỉ rõ |
| File/temp | @TempDir nếu cần | @TempDir | Test-owned directory/container | API cleanup/TTL |
| Clock | Fixed/test clock riêng | Control property/bean rõ | Có reset/đồng bộ background jobs | Không ép giờ trên service không kiểm soát |
| Message queue | Mock publisher | Thường mock | Test topic/consumer group | Dedicated namespace |
| Credentials | Không cần | Fake test identity | Test-only credentials | Approved least-privilege identity |

**RANDOM_PORT và transaction:** Spring Boot docs nói HTTP client và server xử lý trong threads/transactions riêng. `@Transactional` trên test method sẽ không rollback transaction server. Mẫu dùng `@AfterEach` theo ID, không dùng `deleteAll()` trên database chung.

## 26. GitHub Actions: PR và integration là hai gates

Một workflow mẫu chạy fast và integration ở jobs riêng, E2E chỉ khi workflow được kích hoạt thủ công. Nó cần Gradle Wrapper đã commit. **`.github/workflows/verify.yml`**:

```yaml
name: Verify Spring Boot test groups

on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v6
      - name: Unit + slice + untagged
        run: ./gradlew test
      - name: Upload fast reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: fast-test-reports
          path: |
            build/test-results/test/**
            build/reports/tests/test/**

  integration:
    needs: fast
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v6
      - name: Full Spring HTTP + H2
        run: ./gradlew integrationTest
      - name: Upload integration reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: integration-test-reports
          path: |
            build/test-results/integrationTest/**
            build/reports/tests/integrationTest/**

  e2e:
    if: github.event_name == 'workflow_dispatch'
    needs: integration
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v6
      - name: Build executable jar
        run: ./gradlew bootJar
      - name: Start isolated app and run E2E
        shell: bash
        run: |
          set -euo pipefail
          java -jar build/libs/spring-boot-test-groups-0.0.1-SNAPSHOT.jar \
            --server.port=18080 \
            --spring.jpa.hibernate.ddl-auto=create-drop \
            > e2e-app.log 2>&1 &
          app_pid=$!
          trap 'kill "$app_pid" 2>/dev/null || true' EXIT

          ready=0
          for attempt in $(seq 1 40); do
            if curl -fsS http://127.0.0.1:18080/actuator/health \
                 >/dev/null 2>&1; then
              ready=1
              break
            fi
            sleep 1
          done
          if [ "$ready" -ne 1 ]; then
            echo 'App did not start successfully' >&2
            exit 1
          fi

          ./gradlew e2eTest \
            -Pe2eBaseUrl=http://127.0.0.1:18080
      - name: Upload E2E reports and logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-test-reports
          path: |
            build/test-results/e2eTest/**
            build/reports/tests/e2eTest/**
            e2e-app.log
```

**Điểm cần biết:**

- Phiên bản Actions dựa trên ví dụ Gradle/GitHub chính thức có sẵn khi soạn; doanh nghiệp có thể pin commit SHA và kiểm runner compatibility/security policy.
- Spring Boot Actuator cung cấp readiness probe `/actuator/health` trong lab; không mặc định mở mọi actuator endpoints ra Internet.
- `e2e` job **không chạy tự động trên PR/push** theo YAML này, chỉ khi `workflow_dispatch`. Nếu release policy bắt buộc E2E, hãy tạo required job/approval tương ứng; một job bị skip không phải PASS.
- `needs: fast/integration` làm việc chạy tiếp phụ thuộc stage trước thành công; nếu upstream fail, E2E không chạy.
- GitHub Actions jobs là các runners riêng, không tự chia sẻ build/test caches, artifacts hay Spring contexts.
- Upload artifacts với `if: always()` lưu XML/HTML/logs sau failure; phải tránh tokens/passwords/private data.
- E2E app khởi bằng JAR/H2 **của chính CI runner**, không gọi external production.
- Shell `sleep 1` trong readiness polling có **giới hạn 40 lần và điều kiện thành công**, khác sleep cố định rồi hy vọng app đã ready.

## 27. Báo cáo kiểm thử phải tách theo từng Gradle task

Gradle `Test` task có XML và HTML output riêng, thường:

```text
build/test-results/test/...
build/reports/tests/test/...

build/test-results/unitTest/...
build/reports/tests/unitTest/...

build/test-results/sliceTest/...
build/reports/tests/sliceTest/...

build/test-results/integrationTest/...
build/reports/tests/integrationTest/...

build/test-results/e2eTest/...
build/reports/tests/e2eTest/...
```

**Không được** báo “tất cả tests pass” chỉ vì `build/reports/tests/test/index.html` xanh: file ấy không đại diện integration/e2e khi chúng là tasks riêng. Cần tổng hợp từng stage với trạng thái **PASS, FAIL, SKIPPED, NOT RUN** và số tests thực chạy, lưu artifacts từng job. Cũng không dùng `ignoreFailures=true` hoặc retry plugin để đổi fail thành “green” mà không công khai.

## 28. Khi nào dùng source sets hoặc JVM Test Suite thay `@Tag`?

Tags giúp tổ chức **runtime selection** nhanh trong một source set. Nhưng mọi test classes vẫn compile/run với `testImplementation`:

- Unit test về mặt kỹ thuật vẫn có thể import `@SpringBootTest` hoặc Testcontainers.
- E2E test vẫn mang JUnit/Spring Test libraries dù không sử dụng.
- Một dependency optional có trên test classpath có thể che lỗi “không có dependency” thật.
- Classpath khác cho DB provider hoặc native image không thể được tạo chỉ bằng `@Tag`.
- Test fixtures/phụ thuộc giữa modules có thể cần giới hạn compile-time.

Khi cần **dependency/source isolation**, chuyển sang source sets riêng:

```text
src/test/java/               pure unit
src/sliceTest/java/          Spring slice tests
src/integrationTest/java/    Spring + containers + database
src/e2eTest/java/            black-box HTTP tests
```

Gradle JVM Test Suite plugin cũng cung cấp mô hình test suites. Việc di chuyển đòi hỏi khai báo source sets/configurations/compile/runtime classpaths riêng và `Test` tasks phù hợp; không chỉ chuyển thư mục. Với bài demo, dùng tag để tập trung vào **CI task splitting** trước, rồi cải tiến isolation khi dự án lớn và có lý do.

### 28.1. Source set snippet tham khảo

```groovy
// Snippet định hướng, không thay build.gradle đầy đủ ở mục 8.
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'
        compileClasspath += sourceSets.main.output
        runtimeClasspath += output + compileClasspath
    }
}
configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}
tasks.register('integrationTest', Test) {
    group = 'verification'
    testClassesDirs =
            sourceSets.integrationTest.output.classesDirs
    classpath =
            sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
```

**Không dán đoạn này bên dưới `build.gradle` của demo** mà không xóa task `integrationTest` cũ: Gradle không cho đăng ký hai tasks cùng tên. Cần kiểm test compilation/runtime classpaths và fixtures sau refactor. Tài liệu Gradle “Configuring integration tests” và JVM Test Suite là nguồn chuẩn để hoàn thiện.

## 29. Gradle task graph, forks và parallel execution

- `dependsOn`: thêm nhiệm vụ bắt buộc vào graph.
- `shouldRunAfter`: sắp thứ tự khi **cả hai đã ở trong graph**, không kéo task mới vào.
- `mustRunAfter`: ép thứ tự khi hai tasks được chọn, cũng không phải dependsOn.
- `maxParallelForks`: cho phép nhiều test JVM processes, có thể tăng throughput nhưng cũng tăng CPU/memory và giảm cache reuse.
- `forkEvery`: tạo JVM mới sau N test classes, có thể làm Spring TestContext cache không reuse được.
- Gradle Build Cache/Configuration Cache **khác** Spring TestContext cache; một task cache hit không có nghĩa test đã được thực thi lần này.
- Tách jobs nhanh/integration/E2E tạo báo cáo rõ, nhưng có overhead dependency downloads/JVM startup giữa runners.

Nếu CI đã chạy `./gradlew test` ở job fast, đừng vô tình thêm `integrationTest.dependsOn test` rồi chạy lại fast suite trong job integration. Trong YAML, `needs: fast` là gate ở cấp workflow; Gradle integration task có thể chạy độc lập để debug.

## 30. Test isolation và Spring TestContext cache

TestContext cache reuse cùng `ApplicationContext` key trong cùng JVM. Nó **không reset mọi mutable state**:

- `@DataJpaTest` rollback dữ liệu theo transaction test.
- Real HTTP server commits không được test-client `@Transactional` rollback.
- `@MockitoBean` mocks có reset lifecycle; chạy parallel với shared mocks cần thận trọng.
- Singleton caches, mutable Clock, static fields và SecurityContext ThreadLocal cần isolation.
- `@Scheduled`/`@Async` jobs có thể chạy sau test và làm thay đổi fixtures.
- Redis/Kafka/object storage/file system không tham gia rollback của JPA transaction.
- `@DirtiesContext` buộc reload context; chỉ dùng khi bean graph/state thực sự không thể hoàn nguyên an toàn.

Spring Framework 6.2 TestContext cache **default tối đa 32 contexts** với LRU; context key chịu ảnh hưởng profile, properties, context customizers, bean overrides, DynamicPropertySource và web environment. Tăng cache size không tự sửa flaky data leak; cần đo context misses/CI elapsed và phân loại state cụ thể.

## 31. Kiểm thử quan trọng không chỉ là happy path

Một release pipeline đáng tin cần **negative tests** trong các nhóm đúng cấp:

- Unit: null/blank/too-long title, duplicate transition, missing domain record.
- MVC slice: invalid JSON, sai media type, 400/404/409 mapping, path/method contract.
- JPA slice: unique constraints, derived query case, dirty checking, migrations.
- Integration: transaction rollback/commit, data readback sau HTTP, exception mapping với real service.
- E2E: public 201→200→204 hành trình, authentication/tenant boundaries nếu app có security.
- External dependencies: container unavailable, timeout/circuit breaker, idempotency/compensation nếu có.
- Performance: RPS, p95 và error budgets bằng load tool riêng, không gọi một unit test là load test.

**Không sao chép cùng một assertion vào cả bốn nhóm mà bỏ qua lỗi riêng của mỗi nhóm.** Ví dụ E2E chỉ `status 200` có thể vẫn xanh khi `completed` sai; phải assert business state. Ngược lại unit 100% branches không thay được JPA transaction integration.

## 32. Tối ưu CI theo thời gian và khả năng phát hiện lỗi

Khi suite chậm, điều tra:

1. Tổng `Gradle test task wall time`, compilation, dependencies downloads.
2. Số Spring contexts thực sự load và cache hits/misses.
3. Các `@DirtiesContext` và bean overrides/property variants gây key explosion.
4. Docker/Testcontainers image pull/connection readiness.
5. Migrations/schema initialization.
6. Build/test JVM forks và parallel contention.
7. HTTP server startup và test environment wait.
8. Mocks/external service latency, retry và timeout.
9. CI artifact upload time.
10. Flaky retry rate và hidden dependencies giữa tests.

Tối ưu **không phải** xóa hết full-context tests. Một bản tối ưu đáng giữ phải cải thiện feedback mà không giảm số **bug hypotheses được bảo vệ**. Từng loại test nên có mục đích: unit bắt business rule, slice bắt MVC/JPA config, integration bắt transaction/wiring, E2E bắt startup/packaging/public journey.

## 33. Flakiness, dữ liệu dùng chung và retry

Các nguồn flaky điển hình:

| Triệu chứng | Nguyên nhân | Hướng sửa |
|---|---|---|
| Chạy riêng xanh, cả suite đỏ | Static/singleton state leak | Reset/per-test data |
| H2 duplicate key giữa tests | Dùng chung ID, không rollback | Unique IDs/transaction cleanup |
| E2E 404 khi bắt đầu | Server chưa ready hoặc deploy đang diễn ra | Readiness + bounded retry |
| Port đã bị dùng | Fixed port giữa jobs | RANDOM_PORT hoặc isolated port |
| Test server timeout | Resource contention trong CI | Giới hạn forks, đo capacity |
| Spring context load fail dây chuyền | Một lỗi startup root | Tìm first failure, không sửa từng test |
| Docker container không chạy | CI chưa có Docker/permissions | Setup job, không skip ngầm |
| Test phụ thuộc thứ tự | Dữ liệu A được B dùng | Self-contained fixtures |
| Mockito verification sai khi parallel | Shared mock reset/race | Phân nhóm/limit parallel |
| E2E không xóa task khi process kill | Finally không chạy | Test-owned environment/janitor |
| Test report xanh nhưng 0 methods | Tag/filter/task config sai | Check XML executed count |
| CI retry pass sau 3 lần | Race/network issue còn tồn tại | Điều tra first failure |

**Không coi retry xanh là sửa được test.** Một integration test luôn phải retry nhiều lần báo hiệu race/resource contention/teardown lỗi. Ghi root-cause và giữ artifacts của lần fail đầu, đừng tăng retry vô hạn.

## 34. Thực hành thiết kế pipeline theo rủi ro

Với một ứng dụng bán hàng thực tế:

- Sửa quy tắc giá: unit tests của pricing là gate nhanh.
- Sửa JSON pricing endpoint: MVC slice + contract test.
- Sửa bảng Orders/transaction: JPA slice + integration DB thật bắt buộc.
- Sửa Spring Security: MVC security slice + real HTTP authorization integration.
- Sửa Dockerfile/JAR config: E2E startup/health qua artifact.
- Sửa connection pooling: integration với service thật + load baseline.
- Sửa queue event/async: integration với broker/test-run consumer group.
- Sửa migration production: apply schema migrations trên DB cùng dialect.
- Sửa toàn bộ checkout journey: selected black-box E2E qua các services được quy định.

Với mỗi sự thay đổi, hỏi: **Lỗi nào có thể lọt qua nhóm hiện tại?** Nếu test chỉ chứng minh controller nhưng rủi ro là transaction, cần bổ sung đúng loại integration test. Tăng toàn bộ E2E không phải luôn là câu trả lời tốt nhất vì chi phí cao và khó chẩn đoán lỗi nhỏ.

## 35. Câu hỏi ôn tập

### A. Tag hay source set?

Tất cả tests ở `src/test/java`; developer thêm `@Tag("unit")`. Nó có loại bỏ Spring Boot Test khỏi unit classpath không?

**Đáp án:** Không. Tag chỉ lọc runtime. Muốn compile/dependency isolation dùng source sets/JVM Test Suite hoặc module riêng.

### B. Test mặc định

Với build.gradle này, `./gradlew test` chạy `@Tag("integration")` không?

**Đáp án:** Không, vì `excludeTags 'integration','e2e'`. Nó vẫn chạy untagged để giảm nguy cơ silent omission.

### C. Gradle build

`./gradlew build` pass có chứng minh `e2eTest` đã pass không?

**Đáp án:** Không. Java `check` task mặc định có `test`, không tự kéo các custom groups. Cần inspect task graph/reports.

### D. MVC slice

`@WebMvcTest` mock TaskService, test JSON 201 pass. Có bảo đảm service `@Transactional` commit không?

**Đáp án:** Không; service thật không chạy. Integration real HTTP + DB readback bảo vệ lớp ấy.

### E. JPA query

Mockito trả sẵn `ChecklistItem` bất kể title, production query IgnoreCase sai. Nhóm nào kiểm tốt hơn?

**Đáp án:** `@DataJpaTest` với H2/DB thật và input mixed-case.

### F. Real HTTP rollback

`@SpringBootTest(RANDOM_PORT)` test client có `@Transactional`. POST commit trong server có rollback cùng test thread?

**Đáp án:** Không. Client/server khác threads/transactions. Cleanup theo ID hoặc isolated database.

### G. E2E safety

Một developer thay `-Pe2eBaseUrl` thành URL production để kiểm nhanh. Có nên để test tự POST/DELETE không?

**Đáp án:** Không. Bản demo chặn host ngoài loopback. Môi trường khác cần authorization, allowlist và test-data policy riêng.

### H. 0 methods executed

Gradle integrationTest SUCCESS nhưng JUnit XML không có method nào. Có coi integration gate đã kiểm chứng không?

**Đáp án:** Không. Phải kiểm classpath, tags và số tests thực chạy.

### I. Parallel forks

Tăng `maxParallelForks` từ 1 lên 8, hai tests cùng cố dùng một DB row và tên file cố định. Điều gì xảy ra?

**Đáp án:** Race/collision. Tăng parallelism không tạo isolation; dùng unique fixtures/schema hoặc giới hạn nhóm không parallel-safe.

### J. HTTP200 chưa đủ

E2E assert 200 từ `GET /api/tasks/{id}` nhưng không kiểm `completed` sau POST. Có thể bỏ sót lỗi gì?

**Đáp án:** Task không được cập nhật/commit nhưng endpoint vẫn đọc và trả 200. Assert state nghiệp vụ và DB/API readback.

### K. Testcontainers

Một test cần PostgreSQL-specific SQL; chỉ dùng H2 in-memory JPA slice có đủ không?

**Đáp án:** Không. Tạo integration với Postgres Testcontainers/migrations tương ứng.

### L. Context cache

Mỗi test class có `@DirtiesContext` để xóa một row. Vì sao gây chậm?

**Đáp án:** Evict/reload contexts nhiều lần; rollback hoặc scoped cleanup thường phù hợp hơn.

### M. E2E job skipped

Workflow quy định E2E chạy chỉ khi workflow_dispatch, nhưng release chưa gọi. Báo cáo release nên ghi gì?

**Đáp án:** E2E NOT RUN, không phải PASS. Nếu bắt buộc, cấu hình workflow/approval và required gate.

### N. Đếm tests

Một method tag cả `slice` và `integration` được chạy từ hai tasks. Có thể gây hậu quả nào?

**Đáp án:** Chạy lặp, fixtures side effects/collision; nên một primary tag hoặc chủ động xử lý duplicate executions.

### O. CI artifacts

Integration job fail nhưng upload report chỉ chạy ở `if: success()`. Làm sao điều tra?

**Đáp án:** Khó vì artifacts thiếu. Dùng `if: always()` và giữ XML/HTML/logs có lọc secrets.

## 36. Checklist triển khai

- [ ] Định nghĩa rõ unit/slice/integration/E2E bằng boundary và bug hypothesis.
- [ ] Mỗi test class có một primary scope tag.
- [ ] Unit không dùng full Spring context/external IO khi không cần.
- [ ] MVC/JPA slice không lạm dụng `@SpringBootTest`.
- [ ] Integration giữ thật những beans/AOP/DB cần kiểm.
- [ ] E2E không inject internal repository/beans trong test process.
- [ ] JUnit Platform được bật bằng `useJUnitPlatform`.
- [ ] Custom Test tasks có testClassesDirs và classpath đúng.
- [ ] `test` không bỏ qua toàn bộ untagged tests.
- [ ] Có kiểm số tests executed; không coi 0 tests là PASS thực.
- [ ] `unitTest/sliceTest/integrationTest/e2eTest` có report theo task.
- [ ] `check/build` task graph đã được xác minh.
- [ ] CI required checks đúng với release/merge policy.
- [ ] E2E job có allowlist, app readiness, bounded timeouts.
- [ ] Test data có UUID/owner và cleanup đúng tài nguyên.
- [ ] Integration RANDOM_PORT không dựa vào test transaction rollback.
- [ ] JPA slice có rollback/flush-clear theo nhu cầu.
- [ ] Không dùng H2 để kết luận mọi production SQL dialect đều đúng.
- [ ] Không xóa shared DB/table dữ liệu không thuộc test.
- [ ] Mutable state/Mockito mocks/scheduled jobs có isolation.
- [ ] @DirtiesContext chỉ dùng khi context không thể reuse an toàn.
- [ ] Testcontainers lifecycle khớp Spring context cache.
- [ ] CI forks/parallel tasks không tranh chấp ports/DB/file path.
- [ ] Có test persisted state để bắt transaction bug.
- [ ] E2E phản ánh artifact đã build và public API thật.
- [ ] Scripts không tự gửi dữ liệu tới production/staging không được duyệt.
- [ ] CI artifacts lưu cả khi failure và không lộ secrets.
- [ ] Test flakiness có owner và root cause, không retry vô hạn.
- [ ] Report phân biệt PASS/FAIL/SKIPPED/NOT RUN.
- [ ] QA ghi trung thực code reviewed so với tests đã chạy thực.

**Kết luận:** Tách nhóm unit, slice, integration và kiểm thử đầu cuối giúp CI trả feedback nhanh, có kiểm soát chi phí và giữ đủ bằng chứng cho các lỗi quan trọng. **Unit** bảo vệ business rules; **slice** bảo vệ MVC/JPA/client framework behavior; **integration** bảo vệ wiring, transaction và persistence/HTTP thật; **E2E** bảo vệ sản phẩm đã đóng gói/khởi động và public journey. JUnit `@Tag` + Gradle `Test` tasks là điểm bắt đầu dễ áp dụng, nhưng vẫn phải quản lý **isolation, test discovery, Spring cache, dữ liệu và quyền môi trường**. Một pipeline chạy nhanh với hàng loạt bài test bị skip hoặc cùng mock hết dependency không phải pipeline chất lượng.

### Tài liệu tham khảo chính thức

- Gradle — Testing in Java & JVM projects, Test tasks, JUnit Platform tags, test classes/classpath: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — JVM Test Suite plugin: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
- Gradle — Test task DSL: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- Spring Boot 3.5 — Testing Spring Boot Applications, @WebMvcTest/@DataJpaTest/@SpringBootTest RANDOM_PORT: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — Context Caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — Test-managed transactions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- JUnit Jupiter — Tagging and Filtering: https://docs.junit.org/5.13.4/writing-tests/tagging-and-filtering.html
- JUnit Jupiter — Build Support for Gradle: https://docs.junit.org/5.13.4/running-tests/build-support.html
- Official Gradle GitHub Actions setup (v6): https://github.com/gradle/actions/blob/main/docs/setup-gradle.md
- GitHub Actions — Storing and sharing build artifacts: https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
- Java SE 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Testcontainers for Java — Integration testing: https://java.testcontainers.org/
