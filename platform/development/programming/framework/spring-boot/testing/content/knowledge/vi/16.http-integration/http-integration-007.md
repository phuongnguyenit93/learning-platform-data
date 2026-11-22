# HTTP tích hợp: Dữ liệu được commit trên server và chiến lược dọn sau test

## Mục tiêu học tập

Khi kiểm thử một API Spring Boot bằng HTTP thật, nhiều người viết `@Transactional` lên test và tin rằng toàn bộ dữ liệu tạo bởi request sẽ tự động bị rollback sau mỗi method. Giả định này **không đúng** trong trường hợp thông dụng `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc `DEFINED_PORT`: request đi qua socket đến web server; mã xử lý HTTP chạy trên **server thread**, còn JUnit test và transaction do Spring TestContext quản lý chạy trên **test thread**. Giao dịch database ở server có thể **commit độc lập** trước khi test kết thúc.

Nếu không có cơ chế cleanup, dữ liệu “rác” còn lại có thể làm các test chạy sau thất bại, gây kết quả phụ thuộc thứ tự, lỗi unique constraint, sai số đếm bản ghi, khó chạy song song và nguy hiểm nếu trỏ nhầm database production.

Sau bài này, bạn có thể:

- Giải thích ranh giới giữa test transaction, HTTP request, server transaction và database commit.
- So sánh `MockMvc` không mở socket với `@SpringBootTest(RANDOM_PORT)` dùng HTTP thật.
- Chứng minh bằng một test Java 17 rằng rollback của transaction trên test thread **không xóa** bản ghi đã commit qua API.
- Tổ chức cleanup an toàn qua `@AfterEach`, API DELETE, transaction độc lập, `@AfterTransaction`, `@Sql`, database/schema cô lập hoặc Testcontainers.
- Chọn chiến lược dựa trên dữ liệu, mức test, quyền truy cập DB, hoạt động bất đồng bộ và chạy song song.
- Viết test không phụ thuộc thứ tự và không sử dụng `deleteAll()` toàn hệ thống một cách nguy hiểm.
- Phân biệt trạng thái commit đã xác nhận với eventual consistency và side effect không thuộc transaction.
- Chẩn đoán test flakiness, connection pool deadlock, rollback “ảo”, dữ liệu không sạch và sai môi trường database.

Bài có một ví dụ chạy được bằng **Java 17, Spring Boot 3.3.5, Spring MVC, Spring Data JPA, H2, JUnit Jupiter, Gradle và `TestRestTemplate`**. Các đoạn mở rộng ngoài project sẽ được đánh dấu là **minh họa**.

## 1. Hai tiến trình tư duy: test method và HTTP handler không chung transaction

Trước tiên cần phân biệt **test tạo request** và **ứng dụng xử lý request**.

Một lời gọi trực tiếp vào service trong cùng thread có thể tham gia transaction đang có của test (tùy transaction manager, propagation và cấu hình). Nhưng khi test gửi HTTP đến embedded server thật, công việc xử lý của controller/service diễn ra trên **thread khác**. Giao dịch Spring kiểu imperative thông thường gắn với thread thông qua transaction synchronization, **không tự đi theo HTTP request từ test thread sang server thread**.

~~~text
JUnit test thread                         Spring Boot server thread
-----------------                         -------------------------
@BeforeEach tạo fixture
@Transactional test transaction (nếu có)
    |
    | HTTP POST /api/tasks --------------->|
    |                                       | Controller nhận request
    |                                       | Service @Transactional
    |                                       | BEGIN server transaction
    |                                       | INSERT INTO http_tasks ...
    |                                       | COMMIT server transaction
    |<------------- HTTP 201 Created ------|
    |
    | Assert response/GET
    | Kết thúc test
    | ROLLBACK test transaction
    v
Dữ liệu server commit vẫn tồn tại trong database
~~~

**Điểm cốt lõi:** Hai transaction có thể truy cập cùng database nhưng **không phải cùng transaction**. Rollback giao dịch A trên test thread không “đi tìm và đảo ngược” những giao dịch B đã commit ở server thread. Một khi server transaction commit, dữ liệu tồn tại cho các transaction khác đọc thấy, trừ khi có cơ chế cleanup/compensation riêng.

Đây là hành vi được Spring Boot mô tả cho `@SpringBootTest` với `RANDOM_PORT` hoặc `DEFINED_PORT`. Không phải bug của JUnit, Spring Data JPA hay H2. Kiểm thử phải thể hiện rõ **ai chịu trách nhiệm tạo và ai chịu trách nhiệm xóa dữ liệu**.

### Test rollback áp dụng được tới đâu?

`@Transactional` trên test Spring (khi có `TransactionalTestExecutionListener` và transaction manager thích hợp) có thể mở một **test-managed transaction**; mặc định transaction này rollback sau test. Những thao tác repository/service **trong phạm vi transaction ấy** thường tham gia nó với propagation phù hợp.

Tuy nhiên:

- HTTP client chỉ **gửi request**; nó không mang transaction JDBC của test sang server.
- Servlet container nhận request bằng thread riêng.
- `@Transactional` của service phía server tạo/tham gia **server-side transaction**.
- Service trả thành công sau khi transaction đã hoàn tất theo interceptor thông thường; dữ liệu có thể đã commit trước khi response được gửi.
- Một API bất đồng bộ có thể trả 202 Accepted **trước khi** dữ liệu được ghi; khi đó cần test eventual consistency riêng, không được giả định HTTP 202 nghĩa database đã commit.
- Nếu service dùng `REQUIRES_NEW`, messaging, scheduler hoặc transaction manager khác, phạm vi commit có thể còn phức tạp hơn.

## 2. Phân biệt các kiểu test Spring

| Kiểu test | Có HTTP server thật? | Controller được gọi thế nào? | Cơ chế rollback có thể tác động gì? |
| --- | --- | --- | --- |
| JUnit unit test, `new Service(...)` | Không | Không có HTTP | Không có Spring test transaction trừ khi tự tạo |
| `@DataJpaTest` | Không | Gọi repository/JPA trong test thread | Thường rollback các thao tác thuộc test-managed transaction |
| `@WebMvcTest` + `MockMvc` | Không | Mock Servlet request trong JVM, thường cùng test thread | Không suy ra server HTTP/transaction thật; tùy context và thao tác |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Không | `MockMvc.perform(...)` | Có thể tham gia test transaction cho xử lý đồng bộ cùng thread; cần xét propagation/async |
| `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate` | Có | HTTP thật trên socket → server thread | Rollback test thread **không rollback commit phía server** |
| `@SpringBootTest(DEFINED_PORT)` + HTTP client | Có | HTTP thật trên cổng định nghĩa | Vấn đề transaction tương tự RANDOM_PORT; thêm rủi ro trùng port |
| End-to-end test từ tiến trình/container khác | Có | HTTP qua mạng/proxy | Không chia sẻ local test transaction; phải cleanup bằng API/DB/fixture |

**Không đánh đồng “full context” với “real HTTP”.** `@SpringBootTest` mặc định dùng `MOCK`, không bật server thật. Khi mục tiêu là kiểm database commit sau API qua network, dùng `RANDOM_PORT` và HTTP client thật. Khi chỉ kiểm mapping/validation HTTP, `MockMvc` có thể đủ và nhanh hơn.

### Vì sao MockMvc có thể làm người học hiểu sai?

Giả sử:

~~~java
@Transactional
@Test
void createsAndRollsBackInMockMvc() throws Exception {
    mockMvc.perform(post("/api/tasks")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"demo\"}"))
        .andExpect(status().isCreated());
}
~~~

Đây là **snippet minh họa**, chưa đủ class/imports. Trong nhiều trường hợp MVC đồng bộ, `MockMvc` chạy handler cùng test thread; thao tác repository có thể tham gia transaction test và bị rollback. Đổi test thành `TestRestTemplate` gọi server thật **có thể đổi semantics transaction**, dù request URL, payload và assertion vẫn giống nhau.

Ngoài ra, nếu MVC handler dùng `@Async`, `REQUIRES_NEW`, event listener hoặc luồng khác, ngay cả test MockMvc cũng không nên khẳng định “mọi side effect chắc chắn rollback”. Luôn kiểm ranh giới thực tế.

## 3. “HTTP 201” và “database đã commit” liên quan thế nào?

Trong một API đồng bộ điển hình:

1. Controller nhận POST.
2. Service được proxy `@Transactional` gọi.
3. Service gọi `repository.save(...)`.
4. Transaction interceptor **commit** nếu service kết thúc thành công.
5. Controller tạo response 201.

Vì vậy khi client nhận 201, việc ghi trong **transaction service đó** thường đã commit. Nhưng đây là một **mô hình có điều kiện**, không phải luật cho mọi hệ thống.

Các ngoại lệ cần biết:

- API trả **202 Accepted** rồi đưa job vào queue; DB có thể chưa thay đổi.
- Ghi qua event listener/`@Async` sau response.
- DB transaction commit nhưng publish message thất bại, hoặc ngược lại.
- Service chỉ gọi `save` trong transaction dài hơn do caller quản lý; commit có thể xảy ra sau khi method trả.
- API chỉ ghi vào cache/broker, database chưa có record.
- Response bị mất trên mạng **sau khi server commit**; client thấy timeout nhưng dữ liệu thực tế đã tồn tại.
- Hệ thống đọc từ read replica có replication lag; GET kế tiếp có thể chưa thấy dữ liệu dù primary đã commit.

Khi viết test, hãy đặt tên đúng điều muốn chứng minh: “POST trả 201”, “bản ghi đã được commit vào primary database”, “GET khác đọc được bản ghi” hoặc “eventual consistency đạt trong giới hạn thời gian”. Đây là **các điều kiện quan sát khác nhau**.

## 4. Nguyên tắc chọn chiến lược dọn dữ liệu

Cleanup phải thỏa ít nhất năm tiêu chí:

1. **Đúng phạm vi:** chỉ dọn dữ liệu do test tạo, không xóa dữ liệu test khác hoặc production.
2. **Đúng thời điểm:** dọn **sau khi** server đã thực sự hoàn tất ghi/side effects trong phạm vi test.
3. **Đúng transaction:** lệnh cleanup được **commit**, không bị rollback cùng test transaction.
4. **An toàn khi test fail:** dùng hook `@AfterEach`, `try/finally` hoặc fixture lifecycle để cố gắng dọn ngay cả khi assertion lỗi.
5. **Độc lập và lặp lại được:** test chạy đơn lẻ, chạy cả suite hoặc chạy song song không phụ thuộc thứ tự.

Các cách thường dùng:

| Cách | Ưu điểm | Giới hạn/rủi ro |
| --- | --- | --- |
| `@AfterEach` + repository delete theo ID/test key | Tường minh, phạm vi hẹp, dễ đọc | Phải chạy ngoài transaction bị rollback và có quyền truy cập DB |
| Cleanup bằng HTTP DELETE endpoint | Kiểm public lifecycle, không cần nối trực tiếp DB từ test | API DELETE có thể thiếu quyền, cleanup thất bại theo mạng, không xóa mọi side effect |
| Cleanup trong `finally` | Bảo đảm chạy khi assertion ném exception trong JVM | Không chạy khi tiến trình bị kill/crash; có thể che exception gốc nếu cleanup lỗi |
| `@AfterTransaction` | Hook sau khi test transaction đã kết thúc | Chỉ chạy cho transactional test, cần hiểu transaction lifecycle |
| `@Sql(AFTER_TEST_METHOD)` với transaction mode phù hợp | Quản lý dữ liệu test bằng SQL rõ ràng | Script toàn bảng nguy hiểm, transaction mode mặc định có thể không phù hợp |
| `TransactionTemplate` với transaction mới | Kiểm soát commit/rollback tường minh | Cần cấu hình đúng propagation/transaction manager |
| Database/schema riêng mỗi test/class | Cô lập mạnh, dễ reset bằng drop schema | Tốn startup/migration/resources |
| Testcontainers lifecycle | Dùng engine DB gần production; có thể cô lập hạ tầng | Container reuse/shared DB vẫn cần cleanup; thời gian khởi tạo |
| `@DirtiesContext` | Bỏ Spring ApplicationContext bị nhiễm trạng thái | **Không tự rollback/xóa dữ liệu đã commit ở DB ngoài context** |
| Database snapshot/truncate toàn bộ | Nhanh trong DB test riêng, reset toàn diện | Không an toàn khi nhiều test cùng DB; kiểm FK/sequence/parallel |

Một chiến lược tốt **không nhất thiết** chỉ có một kỹ thuật: ví dụ dùng Testcontainers PostgreSQL tách khỏi production, tạo namespace mỗi test, cleanup theo test ID sau HTTP request, và teardown container khi suite kết thúc.

## 5. Ví dụ chạy được: Spring Boot, JPA, H2 và HTTP thật

Ví dụ minh họa một ứng dụng quản lý task tối giản. Ta muốn kiểm rằng:

- `POST /api/tasks` tạo bản ghi và trả 201.
- `GET /api/tasks/{id}` gọi bằng **HTTP request khác** đọc thấy bản ghi đã được commit.
- Rollback một transaction tạo ở **test thread** không làm mất task do server thread đã commit.
- `DELETE /api/tasks/{id}` xử lý xóa qua HTTP và GET tiếp theo trả 404.
- Input không hợp lệ trả 400 và không để lại record.
- Mỗi test tạo tên task riêng dạng `it-<UUID>`; cleanup ở `@AfterEach` xóa **chỉ bản ghi có tên đó** bằng một repository query có transaction riêng.

### 5.1. Vì sao dùng tên task ngẫu nhiên?

Nhiều ví dụ test gọi `repository.deleteAll()` trước/sau mỗi method. Điều này chỉ tương đối an toàn khi database **hoàn toàn dành riêng cho một test độc lập**, không có suite khác đang chạy. Nếu các method/class chạy song song trên cùng DB, `deleteAll()` của test A có thể xóa dữ liệu test B.

Project này dùng `title` duy nhất cho từng test như một **cleanup key**. Đây là cách đơn giản để dạy tư duy “xóa chính những gì mình tạo”, không phải khuyến nghị biến title thành security identifier trong production. Hệ thống thật nên dùng **testRunId, tenant test riêng, correlation ID hoặc danh sách resource IDs** được quản lý theo quyền và hợp đồng.

### 5.2. Cấu trúc thư mục

~~~text
http-commit-cleanup-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/httpcommit/
    │   ├── HttpCommitApplication.java
    │   ├── TaskEntity.java
    │   ├── TaskRepository.java
    │   ├── TaskService.java
    │   └── TaskController.java
    └── test/java/com/example/httpcommit/
        └── HttpServerCommitIntegrationTest.java
~~~

Đây là một **project hoàn chỉnh về mặt source**. Nếu chưa có Gradle Wrapper, cần tạo bằng Gradle tương thích hoặc dùng Wrapper đã được commit trong repository; `gradle-wrapper.jar` là file nhị phân không tự gõ bằng tay.

**`settings.gradle`**

~~~groovy
rootProject.name = 'http-commit-cleanup-demo'
~~~

**`build.gradle`** — Java 17, Spring Boot 3.3.5, Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

- `spring-boot-starter-web` khởi động embedded Servlet server khi dùng `RANDOM_PORT`.
- `spring-boot-starter-data-jpa` cung cấp JPA, Hibernate, transaction manager và Spring Data repositories.
- H2 chỉ tồn tại trên **test runtime classpath** để chạy DB in-memory trong test; không phụ thuộc DB server bên ngoài.
- `spring-boot-starter-test` cung cấp Spring TestContext, JUnit Jupiter và `TestRestTemplate`.
- `junit-platform-launcher` và `useJUnitPlatform()` cấu hình JUnit Platform cho Gradle.

Đừng mang `spring.jpa.hibernate.ddl-auto=create-drop` của ví dụ sang production: đó là tùy chọn **chỉ để tạo/xóa schema test**. Trong production, dùng migration/schema management được kiểm soát.

### 5.3. Spring Boot application

**`src/main/java/com/example/httpcommit/HttpCommitApplication.java`**

~~~java
package com.example.httpcommit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpCommitApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpCommitApplication.class, args);
    }
}
~~~

Class ở root package `com.example.httpcommit`, nên component scan của Boot tìm được controller/service và repository/entity tương ứng.

### 5.4. JPA entity

**`src/main/java/com/example/httpcommit/TaskEntity.java`**

~~~java
package com.example.httpcommit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "http_tasks")
public class TaskEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String title;

    protected TaskEntity() {
        // Required by JPA
    }

    public TaskEntity(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

`GenerationType.IDENTITY` dùng ID do database cấp, H2 hỗ trợ trong cấu hình này. Thuộc tính `unique = true` giúp demo đơn giản: một test title tương ứng tối đa một record. Ở sản phẩm thật, title thường **không phải khóa duy nhất**; khi áp dụng chiến lược cleanup cần dùng resource ID, tenant/test marker hoặc khóa nghiệp vụ có hợp đồng phù hợp.

### 5.5. Repository hỗ trợ cleanup có phạm vi

**`src/main/java/com/example/httpcommit/TaskRepository.java`**

~~~java
package com.example.httpcommit;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface TaskRepository
        extends JpaRepository<TaskEntity, Long> {

    long countByTitle(String title);

    @Modifying
    @Transactional
    @Query("delete from TaskEntity t where t.title = :title")
    int deleteByExactTitle(@Param("title") String title);
}
~~~

`deleteByExactTitle` là một JPQL bulk DELETE có điều kiện theo **title của test**:

- `@Modifying` báo cho Spring Data JPA đây là modifying query.
- `@Query` chỉ rõ câu DELETE; không phụ thuộc inference tên method.
- `@Param` nối tham số `:title`, không cần dựa vào tên tham số ở bytecode.
- `@Transactional` đảm bảo repository thực hiện delete trong một transaction khi được gọi ngoài transaction khác và **commit khi method kết thúc thành công**.
- Trả `int` là số row bị xóa; zero có thể hợp lệ khi API DELETE đã xóa trước hoặc POST thất bại.

**Giới hạn:** Nếu gọi method này **bên trong một test-managed transaction đang rollback**, `@Transactional` mặc định với propagation `REQUIRED` có thể tham gia transaction ấy và cleanup cũng sẽ bị rollback. Vì vậy project **không đánh dấu test class/method là `@Transactional`**; phần chứng minh rollback dùng `TransactionTemplate` trong một phạm vi nhỏ riêng.

Không dùng JPQL delete không có WHERE cho database dùng chung. Trong hệ thống nhiều bảng, cleanup còn phải xử lý foreign key/aggregate và side effect liên quan; không mặc định xóa một row cha là đã dọn toàn bộ.

### 5.6. Service: transaction của server commit riêng

**`src/main/java/com/example/httpcommit/TaskService.java`**

~~~java
package com.example.httpcommit;

import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {

    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public TaskEntity create(String title) {
        return repository.saveAndFlush(new TaskEntity(title));
    }

    @Transactional(readOnly = true)
    public Optional<TaskEntity> findById(Long id) {
        return repository.findById(id);
    }

    @Transactional
    public boolean delete(Long id) {
        if (!repository.existsById(id)) {
            return false;
        }
        repository.deleteById(id);
        return true;
    }
}
~~~

`@Transactional` trên public method của `@Service` được Spring proxy áp dụng khi controller gọi qua bean service. Khi `create` kết thúc bình thường, transaction interceptor thực hiện commit trước khi trả quyền điều khiển cho controller. `saveAndFlush` đẩy SQL tới database trước khi method kết thúc, nhưng **flush không đồng nghĩa commit**; commit vẫn xảy ra khi transaction hoàn tất. Đây là phân biệt cần thiết: dữ liệu có thể được flush trong một transaction rồi cuối cùng rollback.

Tương tự, `delete` chạy trong server-side transaction. Với HTTP DELETE trả 204 sau khi service hoàn tất, dữ liệu thường đã commit việc xóa ở DB trong ví dụ đồng bộ này.

Một ứng dụng production cần xử lý race giữa `existsById` và `deleteById`, optimistic locking/idempotency và quyền xóa. Bài demo tối giản để tập trung vào **transaction boundary/cleanup**, không tuyên bố đây là thiết kế API concurrency đầy đủ.

### 5.7. Controller cung cấp POST, GET và DELETE

**`src/main/java/com/example/httpcommit/TaskController.java`**

~~~java
package com.example.httpcommit;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    public record CreateTaskRequest(String title) {
    }

    public record TaskResponse(Long id, String title) {
    }

    @PostMapping
    public ResponseEntity<TaskResponse> create(
            @RequestBody CreateTaskRequest request) {

        if (request == null || request.title() == null
                || request.title().isBlank()
                || request.title().length() > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid title");
        }

        TaskEntity saved = service.create(request.title());
        TaskResponse body = new TaskResponse(
                saved.getId(), saved.getTitle());

        URI location = URI.create(
                "/api/tasks/" + saved.getId());

        return ResponseEntity.created(location).body(body);
    }

    @GetMapping("/{id}")
    public TaskResponse find(@PathVariable("id") Long id) {
        TaskEntity found = service.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "task not found"));

        return new TaskResponse(
                found.getId(), found.getTitle());
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(
            @PathVariable("id") Long id) {

        if (!service.delete(id)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "task not found");
        }

        return ResponseEntity.noContent().build();
    }
}
~~~

**Hợp đồng API của demo:**

| HTTP | Thành công | Dữ liệu/side effect |
| --- | --- | --- |
| POST `/api/tasks` | 201 Created + JSON `id`, `title` + `Location` | Tạo một task trong transaction server |
| GET `/api/tasks/{id}` | 200 OK + JSON | Đọc dữ liệu đã có |
| DELETE `/api/tasks/{id}` | 204 No Content | Xóa task trong transaction server |
| GET/DELETE ID không tồn tại | 404 Not Found | Không tạo task |
| POST với title rỗng/blank hoặc quá 100 ký tự | 400 Bad Request | Không ghi dữ liệu |

Service trả một JPA entity nội bộ nhưng controller chuyển thành **response record** để tránh serialize entity/hợp đồng database trực tiếp. Đoạn code không cần đăng nhập vì demo không khai báo Spring Security; với sản phẩm thật, phải kiểm auth/authorization và không cho người dùng xóa tài nguyên tùy ý.

## 6. JUnit integration test: commit thật và cleanup đúng chỗ

**`src/test/java/com/example/httpcommit/HttpServerCommitIntegrationTest.java`**

~~~java
package com.example.httpcommit;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import com.example.httpcommit.TaskController.CreateTaskRequest;
import com.example.httpcommit.TaskController.TaskResponse;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = HttpCommitApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "spring.datasource.url="
                + "jdbc:h2:mem:http_commit_demo;DB_CLOSE_DELAY=-1",
            "spring.datasource.username=sa",
            "spring.datasource.password=",
            "spring.jpa.hibernate.ddl-auto=create-drop",
            "spring.jpa.open-in-view=false"
        })
class HttpServerCommitIntegrationTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate client;

    @Autowired
    private TaskRepository repository;

    @Autowired
    private PlatformTransactionManager transactionManager;

    private String testTitle;

    @BeforeEach
    void setUp() {
        testTitle = "it-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanCommittedData() {
        // Test KHÔNG được đánh dấu @Transactional.
        // Repository method mở transaction cleanup và commit.
        // Chỉ xóa dữ liệu có title do method test này tạo.
        repository.deleteByExactTitle(testTitle);
    }

    private TaskResponse createThroughHttp() {
        ResponseEntity<TaskResponse> response =
                client.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest(testTitle),
                        TaskResponse.class);

        assertEquals(HttpStatus.CREATED,
                response.getStatusCode());
        assertNotNull(response.getBody());
        assertNotNull(response.getBody().id());
        assertEquals(testTitle, response.getBody().title());

        return response.getBody();
    }

    @Test
    void postCommitsAndAnotherHttpGetSeesTheData() {
        assertTrue(port > 0);

        TaskResponse created = createThroughHttp();

        // Repository query chạy trên test thread SAU HTTP response.
        // Không có test-managed transaction bao quanh method.
        assertEquals(1L, repository.countByTitle(testTitle));

        ResponseEntity<TaskResponse> fetched =
                client.getForEntity(
                        "/api/tasks/{id}",
                        TaskResponse.class,
                        created.id());

        assertEquals(HttpStatus.OK, fetched.getStatusCode());
        assertNotNull(fetched.getBody());
        assertEquals(created.id(), fetched.getBody().id());
        assertEquals(testTitle, fetched.getBody().title());
    }

    @Test
    void rollingBackClientThreadDoesNotUndoServerWrite() {
        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        template.executeWithoutResult(status -> {
            // HTTP handler chạy trên server thread/transaction khác.
            createThroughHttp();

            // Chỉ rollback transaction đang chạy ở TEST THREAD.
            status.setRollbackOnly();
        });

        // Sau rollback của test thread, server write vẫn commit.
        assertEquals(1L, repository.countByTitle(testTitle));
    }

    @Test
    void deleteThroughHttpCommitsAndNextGetReturns404() {
        TaskResponse created = createThroughHttp();

        ResponseEntity<Void> deleted =
                client.exchange(
                        "/api/tasks/{id}",
                        HttpMethod.DELETE,
                        HttpEntity.EMPTY,
                        Void.class,
                        created.id());

        assertEquals(HttpStatus.NO_CONTENT,
                deleted.getStatusCode());

        assertEquals(0L, repository.countByTitle(testTitle));

        ResponseEntity<String> afterDelete =
                client.getForEntity(
                        "/api/tasks/{id}",
                        String.class,
                        created.id());

        assertEquals(HttpStatus.NOT_FOUND,
                afterDelete.getStatusCode());
    }

    @Test
    void invalidPostDoesNotCreateAnyRecord() {
        ResponseEntity<String> response =
                client.postForEntity(
                        "/api/tasks",
                        new CreateTaskRequest("   "),
                        String.class);

        assertEquals(HttpStatus.BAD_REQUEST,
                response.getStatusCode());
        assertEquals(0L, repository.countByTitle(testTitle));
    }
}
~~~

### Tại sao project này dùng `TransactionTemplate`?

Trong test thứ hai, `TransactionTemplate` mở **một transaction cục bộ trên thread của JUnit**. Trong callback, test gửi HTTP POST qua `TestRestTemplate`. Service trên server thread tạo transaction riêng, ghi task và commit. Sau đó callback gọi `status.setRollbackOnly()`; chỉ transaction ở test thread rollback.

Kết thúc callback, `repository.countByTitle(testTitle)` chạy **ngoài transaction đã rollback** và vẫn thấy 1 row. Như vậy test trực tiếp chứng minh sự khác biệt mà không cần gắn `@Transactional` lên toàn test class — vì nếu làm thế thì `@AfterEach` có thể bị chạy **trong transaction test và bị rollback theo**.

### Vì sao `@AfterEach` có thể dọn được dữ liệu ở đây?

- Class/method không có `@Transactional` test-level, nên `@AfterEach` chạy ngoài một test-managed transaction.
- Repository `deleteByExactTitle` được gắn `@Transactional`, vì thế Spring tạo một transaction mới khi cần và commit câu DELETE.
- Dữ liệu đã commit của server có thể được repository nhìn thấy tại thời điểm cleanup theo điều kiện đồng bộ của ví dụ.
- `@AfterEach` được JUnit gọi dù assertion trong method test ném lỗi bình thường, nên đây là đường cleanup mặc định cho mỗi case.
- Nếu test DELETE đã xóa task, cleanup trả 0 row — đó không phải lỗi.
- Nếu POST bị từ chối, cleanup cũng không phải xóa gì, giữ behavior idempotent.

**Không nhầm với cleanup chắc chắn tuyệt đối:** `@AfterEach` không chạy nếu JVM bị kill, máy sập, tiến trình gặp lỗi nghiêm trọng, hoặc container bị mất. Với hạ tầng test dùng lâu dài, cần thêm TTL, schema teardown, database reset hoặc cleanup job theo run ID khi phù hợp.

### Vì sao dùng title duy nhất thay cho `deleteAll()`?

Mỗi test có `testTitle = "it-" + UUID.randomUUID()`, nên ngay cả khi nhiều method chạy song song cùng database demo, method A không dùng `deleteAll()` xóa task mà method B tạo. Các assertion `countByTitle(testTitle)` cũng không bị record của test khác làm lệch.

Tuy nhiên, một UUID title không thay thế **security ownership**; đây chỉ là test fixture key trong một database in-memory được dành riêng cho kiểm thử. Khi ứng dụng thật cho phép trùng title, hãy dùng một `testRunId`/tenant test marker hoặc theo dõi resource IDs thay vì thêm unique constraint chỉ vì test cần cleanup.

## 7. Chạy test và xác minh kết quả

Từ project root có `settings.gradle`, `build.gradle`, `gradlew`:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng class:

~~~bash
./gradlew test --tests 'com.example.httpcommit.HttpServerCommitIntegrationTest'
~~~

Có **4 method `@Test`**, không có `@ParameterizedTest` hoặc `@RepeatedTest` trong project. Với cấu hình demo đúng, mong đợi **4 test pass**.

Báo cáo Gradle/JUnit thường nằm ở:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.httpcommit.HttpServerCommitIntegrationTest.xml
~~~

Không có `System.out.println` trong source, nên **không có stdout nghiệp vụ cố định**; Gradle có thể báo `BUILD SUCCESSFUL` nếu build thành công. Nếu task dùng cache và hiện `UP-TO-DATE`/`FROM-CACHE`, kết quả có thể được tái sử dụng; khi điều tra cần chạy lại có thể dùng:

~~~bash
./gradlew test --rerun-tasks
~~~

Gradle Wrapper cần được tạo từ một Gradle tương thích hoặc dùng bộ Wrapper sẵn có của repository; với demo Java 17/Spring Boot 3.3.5 có thể bootstrap, ví dụ:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó lưu `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties` và `gradle-wrapper.jar` vào VCS theo quy định. Nếu build dùng CI, cần có JDK 17 phù hợp; Wrapper không tự cung cấp JDK trong mọi cấu hình.

### Những điều các test thật sự chứng minh

| Test | Bằng chứng | Không tự chứng minh |
| --- | --- | --- |
| `postCommitsAndAnotherHttpGetSeesTheData` | POST 201, repository đọc được row, GET qua HTTP khác trả dữ liệu | DB production có cấu hình giống H2 |
| `rollingBackClientThreadDoesNotUndoServerWrite` | Rollback transaction test thread không xóa server write | Mọi kiểu transaction/async đều có ngữ nghĩa giống nhau |
| `deleteThroughHttpCommitsAndNextGetReturns404` | DELETE qua API làm record biến mất trong demo | Mọi side effect ngoài DB cũng được xóa |
| `invalidPostDoesNotCreateAnyRecord` | Input không hợp lệ trả 400, không có row ứng với test key | Không có lỗi/side effect nào ở toàn hệ thống |

Dùng **GET mới sau POST** rất quan trọng: nó tránh test chỉ tin vào response của POST hoặc JPA persistence context của một transaction đang giữ entity chưa commit. Nó tạo một quan sát từ request khác, gần với khách hàng HTTP thật.

## 8. Tại sao không dùng `@Transactional` trên toàn class real-HTTP test?

Xét đoạn rút gọn:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class MisleadingHttpTest {

    @Autowired
    TestRestTemplate client;

    @Test
    void createsTask() {
        client.postForEntity(
                "/api/tasks",
                new CreateTaskRequest("sample"),
                String.class);

        // Spring TestContext sẽ rollback transaction của test
        // nhưng KHÔNG tự rollback transaction đã commit trên server.
    }
}
~~~

Đây là **snippet cảnh báo**, chưa có toàn bộ imports/type declarations. Nếu method được Spring TestContext đặt trong transaction, test transaction sẽ rollback theo mặc định, nhưng server-side transaction vẫn có thể commit.

Nguy hiểm hơn, nếu thêm:

~~~java
@AfterEach
void cleanup() {
    repository.deleteAll();
}
~~~

trong **transactional test class**, JUnit `@AfterEach` thông thường được chạy **bên trong test-managed transaction**. Lệnh `deleteAll()` có thể tham gia transaction đó rồi bị rollback, khiến cleanup **không có hiệu lực** đối với dữ liệu đã commit từ server. Đây là tình huống người viết test tưởng đang dọn, nhưng database vẫn giữ record.

### Khi nào `@AfterTransaction` có ích?

Spring TestContext hỗ trợ hook:

~~~java
@AfterTransaction
void cleanupAfterTestTransaction() {
    repository.deleteByExactTitle(testTitle);
}
~~~

Snippet này **chỉ minh họa** cho test đã được cấu hình `@Transactional` và có transaction manager tương ứng. `@AfterTransaction` được gọi **sau khi test-managed transaction kết thúc**, nên repository cleanup có thể mở transaction mới để commit. Điều kiện: test key phải còn được giữ trong test instance và cleanup method được Spring TestContext thực thi theo lifecycle.

Không dùng `@AfterTransaction` như hook mặc định cho test **không có test-managed transaction**; nó không có ý nghĩa thay `@AfterEach` cho mọi JUnit test. Với real-HTTP integration tests, cách đơn giản và dễ review nhất thường là **không thêm `@Transactional` ở test class** và chủ động cleanup các resource đã tạo.

### Có thể dùng `TransactionTemplate` REQUIRES_NEW trong cleanup không?

Có, khi thật sự cần điều khiển transaction:

~~~java
TransactionTemplate template =
        new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

template.executeWithoutResult(status ->
        repository.deleteByExactTitle(testTitle));
~~~

Đây là snippet dùng variables đã được inject và import `TransactionTemplate`, `TransactionDefinition`. `REQUIRES_NEW` tạo transaction độc lập và có thể suspend transaction đang có. Tuy vậy:

- Nếu test đang giữ một database connection, việc mở thêm connection có thể làm cạn pool khi test chạy song song.
- `REQUIRES_NEW` không sửa được việc trỏ nhầm DB hoặc query DELETE quá rộng.
- Không phải lúc nào cũng cần `REQUIRES_NEW`: nếu test method không transactional như project runnable, `@Transactional` trên repository cleanup với propagation mặc định đã đủ.
- Khi có nhiều transaction managers, phải chỉ rõ **đúng manager/DataSource**.

## 9. `@Sql` sau test: dùng được nhưng phải hiểu transaction mode

Spring TestContext có `@Sql` để chạy SQL scripts theo lifecycle test. Một pattern dễ thấy:

~~~java
@Sql(
        scripts = "/sql/cleanup-tasks.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
class TaskHttpTest {
    // ...
}
~~~

Đây là snippet minh họa: cần file script thật, imports và Spring test context. Với một real-HTTP test mà test method có `@Transactional`, việc script cleanup chạy trong **transaction test rồi rollback** có thể không đạt mục tiêu nếu không chọn đúng transaction semantics.

Một lựa chọn khi cần cleanup SQL đã commit độc lập là dùng:

~~~java
@Sql(
    scripts = "/sql/cleanup-tasks.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
~~~

Đoạn trên minh họa `ISOLATED` để script chạy trong transaction riêng với cấu hình phù hợp. **Không copy nguyên script “DELETE FROM http_tasks” vào DB được chia sẻ**: script phải có điều kiện theo test key/schema hoặc database phải hoàn toàn cô lập. Vì SQL script là resource tĩnh, truyền marker ngẫu nhiên của từng test vào script có thể cần công cụ fixture riêng; trong ví dụ runnable, repository query theo `testTitle` dễ kiểm soát hơn.

### Vì sao `@Sql` không phải lựa chọn tốt nhất cho mọi case?

- SQL cleanup bị ràng buộc dialect và schema thực tế.
- Script tĩnh khó chọn đúng những resource do **một test method ngẫu nhiên** tạo.
- Nếu database có foreign keys, phải có thứ tự xóa phù hợp.
- Nếu test dùng nhiều DataSources, phải chọn đúng datasource và transaction manager trong `@SqlConfig`.
- Cleanup SQL không tự dọn file storage, message broker, search index hoặc cache.
- Trong CI chạy nhiều job dùng chung DB, `TRUNCATE` có thể phá dữ liệu job khác.

Chọn `@Sql` khi fixture là dữ liệu tĩnh, DB được cô lập hoặc script có điều kiện scoped rõ ràng. Dùng repository/API cleanup khi cần theo dõi resource được tạo động.

## 10. Dọn qua HTTP DELETE: khi nào phù hợp?

Một chiến lược khác là **dọn thông qua API công khai**:

~~~text
POST /api/tasks  ->  201 + id
GET  /api/tasks/{id} -> 200
DELETE /api/tasks/{id} -> 204
GET /api/tasks/{id} -> 404
~~~

Ưu điểm:

- Không cần test trực tiếp nối DataSource.
- Bài test mô phỏng chính workflow thật và kiểm quyền/xóa qua API.
- Phù hợp với E2E tests chạy ở một tiến trình hoặc container khác.

Nhưng nó có giới hạn:

- API không nhất thiết hỗ trợ xóa thật (soft delete/archive).
- DELETE có thể cần authentication/authorization, tenant và CSRF/token.
- Nếu POST đã commit nhưng response bị timeout/lost, test có thể **không có ID** để DELETE.
- Nếu DELETE chỉ enqueue một job, 204/202 không bảo đảm dữ liệu đã biến mất ngay.
- API DELETE chỉ dọn aggregate của API; file, cache, message hoặc billing side effects có thể vẫn tồn tại.
- Một bài test lỗi cần giữ bản ghi để điều tra có thể xung đột cleanup policy; giải pháp là môi trường test tách biệt và retention có hạn.

Vì vậy **cleanup bằng API** thường là lựa chọn phù hợp cho black-box test, còn **cleanup bằng repository/DB** phù hợp khi test sở hữu database fixture. Trong ví dụ, test `deleteThroughHttpCommitsAndNextGetReturns404` vừa kiểm API delete, vừa giữ `@AfterEach` làm safety net theo title.

### `try/finally` và giữ lỗi gốc

Khi test tạo nhiều tài nguyên, có thể:

~~~java
Long createdId = null;
try {
    createdId = createTaskOverHttp();
    assertTaskVisible(createdId);
} finally {
    if (createdId != null) {
        deleteTaskOverHttp(createdId);
    }
}
~~~

Snippet này minh họa mẫu kiểm soát resource, không phải project runnable; các helper cần tự định nghĩa. Điểm yếu: nếu cleanup ném exception, nó có thể làm thông báo lỗi gốc khó đọc. Trong một test harness nghiêm túc, thu thập cả lỗi chính và lỗi cleanup (ví dụ suppressed exception/log có kiểm soát), không âm thầm bỏ cleanup failure.

**`@AfterEach`** cũng có thể báo một lỗi cleanup riêng. Không xem “assertion pass nhưng cleanup fail” là thành công: dữ liệu còn sót có thể phá các test tiếp theo.

## 11. Database/schema cô lập và Testcontainers

Ở các hệ thống lớn, dọn từng record sau test có thể không đủ hoặc quá phức tạp. Thay vào đó, test có thể chạy trên **database/schema riêng** rồi hủy toàn bộ sau suite hoặc sau từng class.

### H2 in-memory như ví dụ

- Nhanh, không cần Docker.
- Có thể tách database theo tên URL và Spring ApplicationContext.
- Không nhất thiết giống PostgreSQL/MySQL production về dialect, transaction isolation, constraint hay migration.
- Với `DB_CLOSE_DELAY=-1`, H2 database có thể sống tới khi JVM kết thúc; context cache/pool cũng ảnh hưởng vòng đời.
- `ddl-auto=create-drop` tạo/xóa schema theo vòng đời persistence unit/context, **không phải reset giữa từng test method**.
- **Đừng dựa vào context eviction** để xem data đã sạch trong mọi tình huống.

### Testcontainers PostgreSQL

Với logic JPA/native SQL phụ thuộc database engine, có thể chạy PostgreSQL container tạm trong test. Spring Boot 3.3 có hỗ trợ `@ServiceConnection` cùng starter Testcontainers, hoặc dùng `@DynamicPropertySource` để truyền JDBC URL/user/password. Đặt `@SpringBootTest(RANDOM_PORT)` và kiểm API qua HTTP thật.

Cơ chế minh họa:

~~~text
JUnit suite
    |
    +-- PostgreSQLContainer / schema test riêng
    |      +-- migrations chạy trên DB test
    |
    +-- Spring Boot embedded HTTP server RANDOM_PORT
    |      +-- TaskService @Transactional
    |      +-- DataSource -> PostgreSQL container
    |
    +-- POST/GET/DELETE qua HTTP thật
    |
    +-- cleanup theo testRunId/resource IDs
    |
    +-- container/schema teardown khi suite hoàn tất
~~~

Một snippet định hướng cho JUnit 5:

~~~java
@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PostgreSqlHttpIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired TestRestTemplate, test methods, cleanup...
}
~~~

Đây **không phải project độc lập**: cần Testcontainers dependencies, database schema, entity/repository và code fixture của ứng dụng. Boot Testcontainers classpath và container runtime phải hoạt động. Không tự sao chép snippet vào app không có Docker/Podman compatible runtime.

### Một container mỗi class có bảo đảm dữ liệu sạch giữa các method?

**Không.** Nếu cùng database/container được dùng qua nhiều test methods, dữ liệu commit bởi method trước vẫn còn. Bạn phải:

- Xóa resource theo test ID;
- Dùng schema/database riêng từng test;
- Dọn bằng SQL trong phạm vi test DB;
- Hoặc tạo container mới đúng mức isolation.

Tái sử dụng container qua JVM/test runs giúp tăng tốc nhưng có thể giữ state và gây lỗi khó lặp lại. Nếu bật Testcontainers reusable mode, hãy nêu rõ quy tắc cleanup và không dùng database chứa dữ liệu nhạy cảm.

### Không chỉ database: hạ tầng có side effects khác

Một POST có thể tạo:

- File/object trong S3 hoặc local disk;
- Message trong Kafka/RabbitMQ;
- Cache Redis entry;
- Search index document;
- Email hoặc webhook;
- Payment/billing transaction;
- Scheduled job hoặc outbox event.

**Rollback JDBC không hoàn tác các side effects này.** Nếu integration test kiểm workflow toàn hệ thống, fixture phải có chiến lược cleanup/compensation riêng cho từng nguồn, thường với test namespace và credentials sandbox. Tránh gọi payment/email production trong test.

## 12. Test chạy song song: cleanup theo namespace, không xóa toàn bảng

Một suite có thể được JUnit/Gradle cấu hình chạy parallel methods/classes. Nếu mọi test dùng chung database, bất kỳ cleanup toàn bảng nào cũng là điểm tranh chấp.

**Mẫu không an toàn trong database dùng chung:**

~~~java
@BeforeEach
void resetEverything() {
    repository.deleteAll();
}
~~~

Method này có thể xóa record do test khác vừa tạo, khiến test B không tìm thấy dữ liệu. Nó cũng có nguy cơ xóa dữ liệu không thuộc test nếu kết nối DB sai.

**Mẫu tốt hơn trong một database test được kiểm soát:**

~~~java
@BeforeEach
void prepare() {
    testKey = "it-" + UUID.randomUUID();
}

@AfterEach
void clean() {
    repository.deleteByTestKey(testKey);
}
~~~

Snippet minh họa kiến trúc; `deleteByTestKey` cần được khai báo/triển khai và test entity có marker phù hợp. Trong demo, `testTitle` đóng vai trò tương tự. Không nên thêm test-only field vào domain model **chỉ vì** muốn chèn dữ liệu test nếu điều đó phá domain; có thể sử dụng tenant/test account riêng, correlation ID nghiệp vụ, hoặc isolation ở DB/schema.

### Khi nào `deleteAll()`/`TRUNCATE` có thể dùng?

Khi bạn **chắc chắn** database/schema chỉ dành cho **một test job không chia sẻ**, các thao tác reset toàn bảng có thể đơn giản và nhanh. Ví dụ container mới cho mỗi test class, không có concurrent readers/writers khác. Ngay cả khi đó, phải:

- Kiểm môi trường thật sự là test DB;
- Không có traffic bên ngoài;
- Quản lý transaction/FK/sequence;
- Không còn async jobs đang ghi sau khi reset;
- Không dùng endpoint DELETE ALL không auth trong môi trường production.

Một test worker không có quyền xóa dữ liệu rộng không nên tự bypass bằng credentials production hoặc bật profile nguy hiểm. Isolation tốt hơn là cấp riêng DB/schema cho test.

### Vì sao dọn trước **và** sau test?

- **Trước test:** đảm bảo fixture sạch nếu test trước fail và chưa dọn được.
- **Sau test:** giảm dữ liệu rác sau suite và giảm ảnh hưởng test tiếp theo.

Nhưng “dọn trước” phải có **phạm vi an toàn**; không nên tự xóa dữ liệu không thuộc mình. Với marker mới ngẫu nhiên, thường không có record cũ để dọn trước — bạn có thể bắt đầu bằng kiểm đếm bằng 0 trong namespace riêng. Cleanup sau test vẫn quan trọng; nếu DB dành riêng cho job, teardown toàn schema/container sau suite xử lý phần còn sót khi một JVM chết.

## 13. Điều gì xảy ra nếu response POST bị timeout sau khi server commit?

Một tình huống rất thực tế:

~~~text
Client gửi POST tạo task
          |
          v
Server INSERT + COMMIT thành công
          |
          v
Mạng bị ngắt trước khi client đọc response
          |
          v
Client nhận timeout/IOException
          |
          v
DB vẫn có task, test không biết id mới
~~~

Vì vậy cleanup chỉ dựa trên ID trả từ response có thể **không tìm thấy dữ liệu cần dọn** khi request thất bại sau commit. Một **testRunId hoặc idempotency key** được tạo **trước khi gửi request** giúp test tìm lại/cleanup dữ liệu ngay cả khi mất response.

Trong demo, `testTitle` được tạo ở `@BeforeEach` trước HTTP POST nên cleanup có thể tìm record bằng title ngay cả khi client không đọc được ID. Đây là một **lợi thế của cleanup key được xác định trước**.

### Idempotency và retry

Một client không nên retry POST không idempotent một cách mù quáng. Nếu response bị mất sau commit, retry có thể tạo thêm bản ghi hoặc gặp unique constraint. API quan trọng nên cân nhắc `Idempotency-Key` hoặc request ID có lưu trạng thái, kèm logic xử lý duplicate tương ứng.

Test cần có case:

1. Gửi POST có key `K`.
2. Giả lập response mất/timeout nếu test harness hỗ trợ.
3. Gửi lại cùng key `K`.
4. Xác minh API không tạo bản ghi kép nếu contract yêu cầu idempotency.
5. Cleanup theo key/resource IDs.

Đây là phần mở rộng của chủ đề commit/cleanup; project cơ bản không cài đặt idempotency, vì vậy **không được kết luận** ví dụ đã giải quyết bài toán retry production.

## 14. Eventual consistency và cleanup bất đồng bộ

Nếu API POST trả `202 Accepted`, quá trình ghi có thể được giao cho queue/worker. Hoặc API có transaction DB commit trước nhưng search index/cache cập nhật trễ. Khi đó:

- Một GET ngay sau POST có thể tạm trả 404 hoặc trạng thái cũ.
- Cleanup ngay trong `@AfterEach` có thể chạy **trước** khi async worker ghi dữ liệu.
- Worker có thể tạo lại record **sau khi** test đã cleanup.
- Một DELETE cũng có thể chỉ enqueue việc xóa và trả 202.

Với workflow async, cần **bounded polling** theo một điều kiện quan sát được:

~~~text
POST -> nhận jobId
    |
    v
Poll GET /jobs/{jobId} cho tới COMPLETED hoặc timeout hữu hạn
    |
    v
Assert dữ liệu cuối cùng theo contract
    |
    v
DELETE/cleanup theo test key
    |
    v
Poll trạng thái cleanup nếu hệ thống eventual
~~~

Không dùng `Thread.sleep(5000)` cố định để “hy vọng” worker xong: nó làm test chậm và flaky khi CI quá tải. Có thể dùng Awaitility hoặc một helper polling có timeout/backoff để chờ điều kiện, **không polling vô hạn**.

Tuy nhiên bounded polling là cho hệ thống **thực sự bất đồng bộ**. Trong project demo, service đồng bộ `@Transactional` và GET đọc primary H2, nên sau POST 201 ta kỳ vọng row đã hiện diện ngay. Nếu phải thêm sleep để test demo pass, đó có thể là dấu hiệu giao dịch hoặc test setup sai.

## 15. Transaction propagation: REQUIRED, REQUIRES_NEW và trường hợp khó

Spring dùng transaction propagation để quyết định method có tham gia transaction hiện có hay mở mới. Một số trường hợp quan trọng trong test:

| Propagation | Ý nghĩa thường gặp | Tác động cần cân nhắc |
| --- | --- | --- |
| `REQUIRED` (mặc định `@Transactional`) | Tham gia transaction hiện có trong thread, nếu chưa có thì mở mới | Test thread và server thread vẫn khác nhau |
| `REQUIRES_NEW` | Suspend transaction hiện có và tạo transaction mới | Có thể commit độc lập; cẩn thận connection pool |
| `SUPPORTS` | Tham gia transaction nếu có; nếu không chạy không có transaction | Khó suy ra rollback nếu caller khác |
| `NOT_SUPPORTED` | Chạy ngoài transaction; suspend transaction hiện tại | Không có rollback mặc định cho thao tác được commit riêng |
| `NESTED` | Nested transaction theo savepoint khi hỗ trợ | Không đồng nghĩa chia sẻ transaction qua HTTP/network |

Với `@SpringBootTest(RANDOM_PORT)`, transaction A trên test thread và transaction B trên server thread vốn **không nằm trong cùng thread-bound context**. `REQUIRED` của service phía server không thể “join A” chỉ vì A đã gửi HTTP request.

### Connection pool deadlock trong test transaction

Nếu test thread mở transaction và giữ một connection, sau đó gửi HTTP tới server, server thread có thể cần **một connection thứ hai**. Nếu pool chỉ có **1 connection**, server chờ connection; test thread lại chờ HTTP response. Kết quả có thể là deadlock/timeout.

Trong project demo, Hikari pool mặc định có nhiều connection; `TransactionTemplate` không thực hiện DB write giữ lock dài trong callback. Với ứng dụng thực, không nên duy trì transaction không cần thiết quanh một HTTP call. Nếu cần kiểm transaction trap, có thể cô lập thành một test nhỏ và dùng pool phù hợp, tránh coi timeout là bằng chứng rollback hoạt động.

### Database isolation và “GET đã thấy dữ liệu”

`GET` từ request khác là một phép quan sát hữu ích, nhưng kết quả cũng chịu ảnh hưởng isolation level và DataSource routing:

- Read Committed thường thấy dữ liệu sau commit.
- Một transaction đã mở với snapshot cũ có thể không thấy row mới theo isolation level.
- Read replica có thể lag.
- Cache có thể trả stale data.
- Một query trong cùng JPA persistence context có thể đọc entity từ cache cấp một, không chứng minh round-trip DB mới.

Trong demo, GET tạo request khác, service mở transaction read-only mới và đọc H2 primary; đó là bằng chứng phù hợp với mục tiêu của bài.

## 16. `@DirtiesContext` không phải lệnh rollback dữ liệu ngoài Spring

`@DirtiesContext` yêu cầu Spring TestContext coi ApplicationContext bị bẩn và loại khỏi cache. Nó hữu ích khi một test thay đổi **trạng thái bean/context** không thể reset an toàn. Nhưng:

- Nó không gửi `ROLLBACK` cho transaction server đã commit.
- Nó không xóa row ở PostgreSQL/MySQL ngoài JVM.
- Nó không xóa Kafka messages, S3 objects hoặc Redis keys.
- Nó không bảo đảm database H2 có cùng lifecycle với context nếu DB_CLOSE_DELAY hoặc connection khác vẫn giữ dữ liệu.
- Nó tăng thời gian test vì context phải khởi tạo lại.

**Đừng thêm `@DirtiesContext` vào mọi real-HTTP test chỉ để mong dữ liệu sạch.** Nếu cần isolation thật, dùng database/schema riêng, cleanup có điều kiện hoặc teardown của container.

## 17. Khi nào không cần cleanup database?

Không phải mọi HTTP integration test đều tạo dữ liệu. Một test GET trên fixture đọc-only có thể không cần cleanup nếu nó thực sự không mutate DB, cache hoặc external state. Những trường hợp sau thường đơn giản hơn:

- `@WebMvcTest` chỉ mock controller collaborator, không viết DB.
- Service unit test với repository fake không dùng Spring context.
- GET endpoint chỉ đọc dữ liệu fixture đã dựng và test không có tác động phụ.
- Test dùng transaction trong cùng thread/memory DB và đã xác nhận rollback bao phủ mọi thao tác liên quan.

Tuy nhiên cần xem **side effect ngầm**: access log, audit event, counters, outbox, cache warm-up, “last seen” timestamp hoặc tạo session. Nếu test công bố là read-only nhưng handler cập nhật database, vẫn cần isolation/cleanup.

## 18. Bảo vệ môi trường test khỏi database production

Trước khi chạy một bài test có cleanup, hãy xác minh **database nào thật sự được kết nối**. `@AutoConfigureTestDatabase(replace = NONE)`, test profile hoặc Testcontainers configuration không tự tạo một “lá chắn” nếu credentials/URL đang trỏ nhầm production.

Nguyên tắc an toàn:

- Test phải dùng database/schema/container được cấp riêng.
- Không dùng account production có quyền DELETE/TRUNCATE.
- Giới hạn quyền network của CI tới production DB khi có thể.
- Đặt prefix/namespace rõ cho tài nguyên thử nghiệm, có TTL hoặc run-id.
- Có thể assert `DatabaseMetaData.getURL()`/`getDatabaseProductName()` trong integration setup theo chính sách dự án; không in secret.
- Nếu test có cleanup rộng, cần fail-fast khi database không nằm trong allowlist môi trường test.
- Không chạy migration destructive trên database có dữ liệu thật.
- Khi test dùng object store/email/payment, dùng sandbox/test buckets và fake/sandbox credentials riêng.

**Ví dụ H2 của bài được giới hạn trong test properties** và H2 test runtime. Project không chứa password production, không mở kết nối database ngoài và không cung cấp endpoint DELETE ALL.

### Xác minh JDBC URL trong test khi môi trường quan trọng

Snippet minh họa:

~~~java
try (Connection connection = dataSource.getConnection()) {
    String url = connection.getMetaData().getURL();

    assertTrue(url.startsWith("jdbc:h2:mem:"));
}
~~~

Đây **không phải một test độc lập**, cần `DataSource` được inject và imports. Trong database PostgreSQL Testcontainers, có thể assert product name là `PostgreSQL` và host/DB/schema thuộc test infrastructure. Tránh log URL chứa credentials hoặc kết luận chỉ từ tên profile “test”.

## 19. Kỹ thuật cleanup cho nhiều bảng/aggregate

Một API tạo order thường ghi nhiều bảng:

~~~text
POST /orders
   |
   +-- orders
   +-- order_items
   +-- inventory_reservations
   +-- outbox_events
   +-- audit_log
~~~

Nếu cleanup chỉ xóa `orders`, có thể để lại reservations/outbox/audit hoặc bị foreign-key constraint chặn. Hãy tạo **resource graph** rõ ràng trước khi chọn cách dọn:

1. Xác định parent/child và khóa ngoại.
2. Quyết định hard delete, soft delete, archive hoặc compensation theo contract.
3. Dọn đúng thứ tự hoặc dùng database cascade đã được thiết kế/chấp nhận.
4. Ghi lại IDs/testRunId của mọi tài nguyên được tạo.
5. Với outbox/message, đợi consumer dừng hoặc dọn namespace của test.
6. Đảm bảo cleanup không kích hoạt một business workflow nguy hiểm ngoài ý muốn (refund, email, billing).

Nếu aggregate có nhiều side effect, việc **drop schema/container** sau mỗi isolated test run đôi khi an toàn hơn viết hàng chục lệnh DELETE thủ công — miễn test infrastructure bảo đảm namespace riêng, không có tài nguyên production chung.

### Bulk JPQL DELETE có gì cần chú ý?

`@Modifying @Query("delete ...")` chạy bulk update/delete trực tiếp ở DB, **không đồng bộ tất cả entity đang được giữ trong JPA persistence context**. Nếu test vẫn giữ entity managed từ trước, có thể phải `flush/clear` thích hợp hoặc đọc trong transaction mới trước khi assert. Project demo đọc/cleanup ở những transaction tách biệt và không dùng một EntityManager lâu dài xuyên suốt tests.

Trong hệ thống thật, bulk delete có thể bỏ qua entity lifecycle callbacks hoặc cascade được thực hiện ở tầng ORM so với xóa từng entity. Chọn cleanup query theo schema thực tế, không xem bulk delete là tương đương mọi nghiệp vụ xóa của ứng dụng.

## 20. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Test pass đơn lẻ nhưng fail khi chạy cả suite | Dữ liệu POST của test trước đã commit, cleanup thiếu | Tạo test key riêng, `@AfterEach` hoặc database isolation |
| Test `@Transactional` vẫn để lại row | HTTP handler chạy server thread với transaction độc lập | Không dựa vào rollback test; cleanup commit ngoài transaction test |
| `@AfterEach` gọi delete mà row vẫn còn | Cleanup đang nằm trong test-managed transaction và bị rollback | Bỏ `@Transactional` ở real-HTTP test hoặc dùng `@AfterTransaction`/ISOLATED cleanup |
| `@DirtiesContext` không dọn PostgreSQL | Chỉ evict Spring context cache | Xóa resource/teardown database rõ ràng |
| Test khác bị mất dữ liệu | Cleanup `deleteAll()/TRUNCATE` chạy trên DB chia sẻ | Dùng điều kiện theo testRunId/ID hoặc isolate DB |
| HTTP trả 201 nhưng DB không thấy row | Async commit, đọc replica, transaction chưa kết thúc, sai DB | Kiểm transaction timing/DB routing; bounded polling nếu eventual |
| Client timeout nhưng DB có record | Server commit thành công trước khi response mất | Cleanup theo key được tạo trước request, dùng idempotency |
| GET trả 404 ngay sau 201 | Đọc replica lag, sai ID/context, async state | Kiểm primary/replica, path, eventual consistency |
| Cleanup bị deadlock/timeout | Transaction giữ lock hoặc pool thiếu connection, writer async còn chạy | Tránh txn dài quanh HTTP; đảm bảo pool/ordering, chờ job |
| Cleanup bỏ sót child records | Aggregate nhiều bảng/side effects | Thiết kế graph cleanup hoặc teardown schema |
| Test rollback nhưng query vẫn thấy row cũ | Đọc trong JPA persistence context cache hoặc fixture từ test khác | Query mới/clear context, kiểm namespace |
| `DataIntegrityViolationException` khi rerun | Unique key cố định và data còn sót | Unique test data, scoped cleanup, DB isolation |
| POST test 500 do DB không có schema | Test DB không chạy migration/DDL hợp lệ | Setup schema bằng migration/test config đúng |
| Đọc nhầm database production | Profile/env URL/credentials bị rò | Allowlist test DB, fail-fast, cấm quyền prod |
| Cleanup lỗi khi DELETE qua API | Auth/CSRF/ownership/soft-delete/async delete | Cấp đúng test credentials, assert cleanup, có fallback an toàn |
| Test chạy quá chậm | Full-context per method, container startup nhiều lần | Cân bằng context caching và DB isolation; không dùng `@DirtiesContext` đại trà |
| MockMvc rollback được nhưng RANDOM_PORT không | Khác boundary thread/network | Viết test ở đúng tầng, không suy ra ngữ nghĩa transaction giống nhau |
| `@Sql` script bị rollback | TransactionMode không đúng cho real-HTTP cleanup | Dùng `ISOLATED` hoặc cleanup repository ngoài transaction |
| Test luôn đếm sai tổng row | Test khác chạy song song/shared fixture | Đếm theo test key, không assert count toàn bảng |
| Teardown container fail | Container/runtime resource bị treo | Quản lý lifecycle/CI cleanup riêng, không phụ thuộc method-level hook |

### Quy trình chẩn đoán một row bị “rò” sau test

1. Xác nhận test có gọi **HTTP thật** hay MockMvc.
2. Kiểm `@Transactional` đặt ở **test class**, **service**, **repository** hoặc mọi nơi; vẽ lại thread/transaction boundaries.
3. Xác định server đã commit trước response chưa, hay đang xử lý async.
4. Kiểm cleanup method có chạy không và nó thuộc transaction nào.
5. Kiểm cleanup query có dùng đúng key, đúng datasource/schema/tenant.
6. Kiểm response/GET sau cleanup trong transaction **mới** thay vì persistence context cũ.
7. Kiểm có concurrent tests/consumers đang tái tạo record không.
8. Đọc root cause từ Gradle/Spring logs, không “sửa” bằng cách đổi assertion mong đợi sang 1 row.

## 21. Quy trình áp dụng cho dự án thật

Một quy trình có thể review được:

**Bước 1 — Chốt mục tiêu kiểm thử.** Có cần chứng minh HTTP + DB commit thực không? Nếu chỉ kiểm controller mapping, ưu tiên MVC slice; nếu chỉ logic nghiệp vụ, unit test.

**Bước 2 — Cấp DB test an toàn.** H2 cho CRUD đơn giản, PostgreSQL Testcontainers cho SQL/transaction đặc thù; môi trường không có credentials production.

**Bước 3 — Chọn `RANDOM_PORT`.** Để client gửi request tới server thật; dùng `TestRestTemplate`/`WebTestClient` có base URL phù hợp, không hardcode 8080.

**Bước 4 — Tạo test marker trước request.** TestRunId/UUID/tenant fixture giúp tìm/xóa resource ngay cả khi mất response.

**Bước 5 — Gửi request và kiểm hợp đồng.** Assert HTTP status/body/Location, rồi dùng GET hoặc repository read **trong transaction mới** để quan sát commit.

**Bước 6 — Tổ chức cleanup một cách chủ động.** `@AfterEach` + repo delete ở transaction riêng, hoặc DELETE API, hoặc schema/container isolation. Không gắn `@Transactional` vào toàn real-HTTP test mà không hiểu tác động.

**Bước 7 — Kiểm side effects ngoài DB.** File, cache, outbox, queue, jobs, email sandbox; tách fake/integration theo phạm vi.

**Bước 8 — Kiểm chạy lặp và chạy song song.** Chạy class nhiều lần, đảo thứ tự, bật parallel nếu suite hỗ trợ, xác nhận không có state leakage.

**Bước 9 — Kiểm cleanup thất bại có bị phát hiện không.** Nếu xóa lỗi, test phải báo đúng lỗi, không bỏ qua một cách im lặng.

**Bước 10 — Thêm teardown ở tầng hạ tầng.** Nếu một JVM chết trước `@AfterEach`, DB/container/namespace vẫn được thu dọn bằng CI lifecycle hoặc TTL theo quy định.

## 22. Bài tập thực hành

**Bài A — thấy commit sau HTTP:** Chạy `postCommitsAndAnotherHttpGetSeesTheData`. Giải thích vì sao GET thứ hai và repository count sau response có ý nghĩa hơn việc chỉ assert POST 201.

**Bài B — chứng minh rollback không “qua HTTP”:** Chạy `rollingBackClientThreadDoesNotUndoServerWrite`. Đổi assertion từ 1 thành 0 để thấy fail; hoàn nguyên. Vẽ hai thread và hai transaction.

**Bài C — làm hỏng cleanup có chủ đích:** Trong nhánh test DB riêng, tạm bỏ `@AfterEach`. Chạy lại test có title cố định để quan sát state leakage/unique constraint. Sau đó khôi phục cleanup và dùng test key ngẫu nhiên.

**Bài D — test method `@Transactional`:** Tạo một class minh họa gắn `@Transactional` lên test method real-HTTP, dùng `@AfterEach` repository delete. Xác minh cleanup có thể bị rollback theo test transaction; thử chuyển sang `@AfterTransaction` hoặc bỏ test-level `@Transactional`.

**Bài E — dọn theo ID thay vì title:** Sửa fixture theo dõi IDs của các task tạo trong test. Với mỗi ID, gọi DELETE hoặc repository delete trong cleanup. Phân tích trường hợp response bị mất trước khi test biết ID và tại sao cần thêm marker tạo sẵn.

**Bài F — kiểm parallel:** Tạo hai test mỗi test có marker riêng và chạy song song trên cùng test DB. Đảm bảo cleanup của test A không xóa row của B; giải thích vì sao `deleteAll()` không phù hợp.

**Bài G — database khác engine:** Thay H2 bằng PostgreSQL Testcontainers, chạy migrations, verify DB product name và kết quả DELETE/GET. So sánh chi phí khởi tạo và cách teardown container.

**Bài H — eventual consistency:** Chuyển POST thành 202 + async worker trong sandbox test. Viết bounded polling tới khi record xuất hiện, rồi đợi worker hoàn tất trước cleanup. Không dùng sleep cố định để che sự bất đồng bộ.

**Bài I — side effect ngoài DB:** Sau POST, giả lập một outbox event và một file object trong test bucket. Viết cleanup có điều kiện theo run ID cho cả database, event/object. Không dùng sandbox credentials có quyền production.

**Bài J — transaction propagation:** Trong service tạo task, thử `REQUIRES_NEW` trong một bài test chuyên biệt. Quan sát việc commit độc lập và tình huống connection pool nhỏ; phân biệt với test-managed rollback.

## 23. Checklist trước khi merge HTTP integration test có DB

- [ ] Tôi đã xác định đây là **HTTP thật trên RANDOM_PORT/DEFINED_PORT**, không phải MockMvc?
- [ ] Tôi biết code nào chạy test thread, code nào chạy server thread?
- [ ] Nếu có `@Transactional` ở test, tôi không mặc định nó rollback server commit?
- [ ] Tôi kiểm POST status **và** bằng chứng dữ liệu có thể đọc lại ngoài transaction tạo?
- [ ] Dữ liệu test có marker/id duy nhất được tạo **trước** request khi cần?
- [ ] Cleanup chỉ xóa tài nguyên do test sở hữu, không xóa toàn DB chia sẻ?
- [ ] Hook cleanup thực hiện **ngoài transaction sẽ rollback** và chính nó commit?
- [ ] Cleanup vẫn được thử thực thi khi assertion fail, và lỗi cleanup được báo rõ?
- [ ] Test không phụ thuộc method/class order và có thể chạy song song theo cấu hình?
- [ ] Tôi phân biệt synchronous commit với async job/202/eventual consistency?
- [ ] Nếu POST timeout sau commit, vẫn có cách truy tìm/xóa resource?
- [ ] DB/test credentials được cô lập, không thể vô tình xóa production?
- [ ] Cleanup xử lý đúng aggregate/foreign key/outbox/cache/storage side effects khi có?
- [ ] `@DirtiesContext` không bị dùng thay một database cleanup đúng nghĩa?
- [ ] Các `@Sql` script có transaction mode, datasource và điều kiện scope rõ?
- [ ] Gradle/JUnit report xác nhận test thật sự được chạy, không chỉ “UP-TO-DATE”?
- [ ] Nếu JVM/CI chết, có cơ chế TTL/teardown ở tầng hạ tầng cho resource còn sót?

## 24. Tài liệu tham khảo chính thức

Các liên kết sau giải thích behavior của Spring Boot 3.3 và Spring Framework 6.x, là nền tảng cho project ví dụ. Khi sử dụng Boot/Spring phiên bản khác, kiểm lại Javadoc và các semantics tương ứng của codebase.

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest` với `RANDOM_PORT/DEFINED_PORT`, server và client ở thread/transaction riêng, rollback test không rollback server.
- [Spring Framework 6.1 — Transaction Management trong TestContext](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/tx.html): test-managed transactions, `@Rollback`, `@BeforeTransaction`, `@AfterTransaction` và lifecycle.
- [Spring Framework 6.1 — TransactionalTestExecutionListener API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/transaction/TransactionalTestExecutionListener.html): điều phối test transaction.
- [Spring Framework — SQL Scripts trong test](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): `@Sql`, execution phases và transaction modes.
- [Spring Data JPA — Transactions](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): repository method transaction và việc chọn ranh giới tại service.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): container test và `@ServiceConnection`.
- [JUnit Jupiter — Lifecycle Methods](https://docs.junit.org/5.10.2/user-guide/#writing-tests-annotations): `@BeforeEach`, `@AfterEach` và lifecycle fixtures.

**Ghi nhớ:** Khi test gửi **HTTP thật**, giao dịch được commit trong **server thread** không biến mất chỉ vì test method có `@Transactional` và rollback. Muốn test độc lập, hãy **tạo test key rõ ràng, quan sát commit bằng request/transaction khác, cleanup trong transaction được commit và chỉ xóa đúng tài nguyên của mình**. Với hệ thống phức tạp, kết hợp DB/schema/container riêng cùng cơ chế teardown để xử lý cả những lần test bị dừng đột ngột.
