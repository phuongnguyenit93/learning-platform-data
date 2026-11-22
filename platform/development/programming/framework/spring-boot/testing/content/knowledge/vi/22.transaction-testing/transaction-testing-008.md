# HTTP thật, @Async và lời gọi chạy ngoài luồng transaction của test

Trong nhóm **Giao dịch kiểm thử** của module **Spring Boot - testing**, một hiểu lầm rất nguy hiểm là: “Đã đánh dấu test bằng `@Transactional` thì mọi thay đổi database xuất phát từ test sẽ được rollback.” Khẳng định ấy **chỉ đúng cho công việc thực sự tham gia test-managed transaction**. HTTP request được xử lý trên thread của server, tác vụ chạy qua `@Async`/executor, một lời gọi có transaction độc lập, hoặc code bị test framework chuyển sang thread khác có thể **ghi và commit dữ liệu ngoài transaction của JUnit test**.

Spring TestContext ràng buộc trạng thái test-managed transaction với **thread hiện tại** (qua `ThreadLocal`). Nó không tự truyền một JDBC transaction/connection sang HTTP server thread, worker của `@Async`, `CompletableFuture.supplyAsync(...)` hoặc task scheduler. Vì thế, một test xanh khi chạy riêng có thể để lại dữ liệu khiến test chạy sau thất bại hoặc, nghiêm trọng hơn, ghi nhầm vào một database không dành cho test.

Bài này sẽ phân biệt rõ:

1. **Gọi trực tiếp service** hoặc `MockMvc` **đồng bộ** trong cùng thread: thường có thể tham gia transaction của test và rollback theo Spring Test.
2. **HTTP thật qua `@SpringBootTest(webEnvironment = RANDOM_PORT)`**: client test và server xử lý request trên các thread khác nhau; transaction của server **không thuộc rollback của test**.
3. **`@Async` gọi qua Spring proxy**: logic chạy ở thread khác; nếu worker tạo transaction riêng và commit thành công thì rollback của caller test không gỡ commit ấy.
4. **Ngắt thread/preemptive timeout/REQUIRES_NEW/event listener**: các ranh giới có thể làm thay đổi hành vi transaction, dù tên method hoặc annotation nhìn giống nhau.

Có ví dụ đầy đủ cho **Java 17+, Spring Boot 3.5, JUnit Jupiter, Spring JDBC + H2**, gồm mã ứng dụng, schema, test rollback trực tiếp, test `MockMvc`, test HTTP server thật, test `@Async` thành công/thất bại và chương trình Java SE độc lập chứng minh nguyên tắc `ThreadLocal`.

## 1. Test-managed transaction là gì?

Trong Spring TestContext, `TransactionalTestExecutionListener` có thể mở **test-managed transaction** trước test method có `@Transactional`. Mặc định, Spring Test rollback nó khi method kết thúc, trừ khi bạn đổi chính sách bằng `@Commit`, `@Rollback(false)` hoặc `TestTransaction.flagForCommit()`.

Ví dụ đơn giản:

```java
@SpringBootTest
class NoteWriterTest {

    @Autowired NoteWriter writer;
    @Autowired NoteStore store;

    @Test
    @Transactional
    void directCallUsesTestTransaction() {
        writer.create(new NoteRequest("TEST-A", "message"));
        assertEquals(1, store.countByKey("TEST-A"));
        // TestContext rollback sau khi method kết thúc.
    }
}
```

Đây là **skeleton minh họa**, không phải file hoàn chỉnh: cần imports và các class `NoteWriter/NoteRequest/NoteStore` được định nghĩa bên dưới. Kết luận hợp lệ: khi method `writer.create(...)` được gọi **trên cùng thread**, transaction do service bắt đầu với propagation `REQUIRED` thường **tham gia transaction có sẵn của test**. Dữ liệu nhìn thấy trong test, nhưng bị rollback khi test transaction kết thúc.

**Không được kết luận:** mọi side effect bất đồng bộ phát sinh từ method sẽ rollback; hoặc việc `store.countByKey(...) == 1` ngay trong test chứng minh dữ liệu đã commit bền vững. Một transaction có thể nhìn thấy các thay đổi **chưa commit của chính nó**.

### Ba loại transaction dễ nhầm

| Phạm vi | Ai quản lý? | Ví dụ | Rollback test có bao phủ? |
| --- | --- | --- | --- |
| **Test-managed** | Spring TestContext | `@Transactional` trên JUnit method | **Có** đối với việc tham gia chính transaction này |
| **Spring-managed application transaction** | Spring AOP/transaction manager | `@Transactional` trên service bean | **Có nếu join test transaction**; không nếu mở transaction độc lập |
| **Application-managed** | Code dùng `TransactionTemplate`/transaction manager trực tiếp | Worker tự tạo transaction | Phụ thuộc nó tham gia hay mở transaction riêng |

Hai method cùng có `@Transactional` không đảm bảo dùng cùng transaction: propagation, thread, proxy và transaction manager phải được xét đồng thời.

## 2. Ranh giới thread quyết định tính tham gia transaction

Với transaction manager kiểu imperative (JDBC/JPA), Spring gắn transaction state với thread thực thi. Khi chạy code trên thread khác, thread ấy không tự thấy `TransactionSynchronizationManager` state của caller.

```text
JUnit test thread                    HTTP / @Async worker thread
----------------                    --------------------------
TestContext BEGIN test-tx
    |
    +-- writer.create()                  (không có gì nếu không gọi)
    |       joins test-tx
    |
    +-- HTTP POST ---------------------> request handler
    |                                    writer.create()
    |                                    BEGIN app-tx
    |                                    INSERT
    |                                    COMMIT app-tx
    |
    +-- asyncNotes.submit() -----------> executor worker
    |                                    writer.create()
    |                                    BEGIN app-tx
    |                                    INSERT
    |                                    COMMIT app-tx
    |
TestContext ROLLBACK test-tx          server/worker commits còn tồn tại
```

Một **Spring-managed transaction trên worker** có thể vẫn tồn tại và hoạt động tốt, nhưng đó là transaction **khác**. Vấn đề không phải “`@Async` làm mất mọi `@Transactional`”, mà là **transaction của caller không được truyền**. Nếu worker được gọi qua một service `@Transactional` proxy, worker có thể mở transaction mới cho chính nó.

### TransactionSynchronizationManager để làm gì?

Trong test chẩn đoán có thể hỏi:

```java
boolean active =
        TransactionSynchronizationManager
                .isActualTransactionActive();
```

Kết quả nói về **thread hiện tại**, không chứng minh mọi thread khác cũng có transaction, và không khẳng định transaction sẽ commit/rollback khi method kết thúc. Nó chỉ là một công cụ debug.

**Cảnh báo:** Với **reactive transactions** (R2DBC/Reactor), Spring dùng `Reactor Context` thay cho `ThreadLocal` truyền thống. Các nhận xét và mã runnable trong bài dùng **blocking JDBC/JPA-style imperative transactions**. Không áp nguyên xi các quy tắc ThreadLocal sang mọi reactive pipeline.

## 3. Phân biệt MockMvc, HTTP thật và gọi trực tiếp

| Cách kiểm tra | Thực sự mở TCP HTTP server? | Thread xử lý thông thường | Cùng test-managed transaction? |
| --- | --- | --- | --- |
| Gọi `noteWriter.create(...)` trực tiếp | Không | JUnit test thread | **Có**, nếu Spring proxy và REQUIRED join |
| `MockMvc.perform(...)` cho **controller đồng bộ** | Không | Thường cùng test thread | **Có thể có**, thường join test transaction |
| `@SpringBootTest(webEnvironment = MOCK)` + `MockMvc` | Không | Mock servlet request, thường đồng bộ | Thường cùng thread khi synchronous |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` + `TestRestTemplate` | **Có** | HTTP client và server thread khác | **Không** truyền test transaction qua socket |
| `@SpringBootTest(webEnvironment = DEFINED_PORT)` | **Có** | Server thread khác | Không truyền test transaction |
| `@Async` qua Spring proxy + executor | Không bắt buộc | Worker thread | Không tự join transaction test |
| `CompletableFuture.runAsync(...)` | Không bắt buộc | Executor/common pool | Không tự join transaction test |
| `@Async` tự gọi method trong cùng bean (**self-invocation**) | Không | Có thể vẫn là caller thread | `@Async` thường **không được áp dụng** qua proxy |

**`MockMvc` không phải “HTTP thật”** mặc dù API của nó trông giống gọi GET/POST. MockMvc có thể chạy controller, validation và Jackson qua servlet infrastructure giả; với controller đồng bộ, nhiều thao tác nằm ngay trên test thread. Điều này làm `@Transactional` test có thể rollback thao tác DB từ MockMvc, khác rõ ràng với `RANDOM_PORT`.

Tuy nhiên, **không tuyên bố mọi MockMvc request đều nằm cùng transaction**: async MVC controller, `Callable`, `DeferredResult`, task offloading, explicit transaction propagation hoặc I/O bên ngoài có thể vượt ranh giới này. Khi có asynchronous dispatch, cần kiểm tra worker và lifecycle tương ứng.

## 4. @SpringBootTest RANDOM_PORT không rollback transaction của server

Theo Spring Boot 3.5, khi dùng `RANDOM_PORT` hoặc `DEFINED_PORT`, HTTP client test và embedded server **chạy khác thread**, vì thế **khác transaction**. Giả sử JUnit test:

```java
@Test
@Transactional
void testHttpPost() {
    restTemplate.postForEntity(
            "/notes",
            new NoteRequest("HTTP-A", "hello"),
            NoteView.class);
}
```

Đây là skeleton của một test đã có `TestRestTemplate` và app chạy trên random port. Test method có `@Transactional` **không khiến code bên trong server controller kế thừa transaction của test**. Khi service server gọi `@Transactional` và phương thức trả thành công, transaction của server có thể commit; rollback của test sau đó **không thể quay lại commit từ thread khác**.

### Cạm bẫy đặc biệt: test xanh nhưng dữ liệu vẫn còn

Một bài test chỉ assert HTTP 201 và không kiểm tra DB sau transaction có thể xanh, sau đó chạy suite lần nữa thì vấp duplicate key do request trước đã commit.

Ví dụ anti-pattern:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class HttpRollbackAssumptionTest {
    @Test
    void createsNote() {
        // HTTP POST thực sự commit ở server.
        // @Transactional của test không dọn server write.
    }
}
```

Đừng hiểu đoạn trên là test hoàn chỉnh. Đây là cảnh báo cho trường hợp **gắn @Transactional trên cả class để “tự dọn DB”** trong khi đang gọi HTTP thật.

### Cách đúng

- Dùng database/container/schema **riêng cho integration tests**.
- Chọn test key duy nhất mỗi method, không dùng chung dữ liệu production.
- Dọn **committed data ngoài transaction test** bằng `finally`, một cleanup transaction độc lập hoặc reset DB/container theo lifecycle hợp lý.
- Xác minh dữ liệu đã commit bằng connection/transaction **khác** sau khi test transaction kết thúc.
- Không dựa vào rollback trong test method để loại side effects ở server.
- Nếu kiểm tra behavior nghiệp vụ chứ không cần HTTP socket, cân nhắc service-level test hoặc MockMvc synchronous test để scope dễ điều khiển hơn.

## 5. @Async và executor: không kế thừa transaction của caller

Để bật async processing:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
    // Có thể định nghĩa executor bean riêng.
}
```

Một method:

```java
@Async("lessonExecutor")
public CompletableFuture<String> work() {
    return CompletableFuture.completedFuture("done");
}
```

Nếu method được gọi **qua Spring proxy**, work chạy bằng executor đã định nghĩa và thường không cùng thread với caller. Test có `@Transactional` chỉ quản lý transaction trên test thread; worker không tự có transaction ấy.

### @Async và @Transactional phối hợp như thế nào?

Khuyến nghị minh bạch về transaction boundary:

```text
Caller test thread
    |
    v
AsyncNoteWriter proxy (@Async)
    |
    +-- executor worker thread
            |
            v
        NoteWriter bean proxy (@Transactional)
            |
            v
        repository/JdbcTemplate INSERT
            |
            v
        COMMIT transaction của worker
```

Ví dụ này đặt `@Async` và `@Transactional` trên **hai bean khác nhau**, tránh nhầm thứ tự AOP advice. Điều quan trọng:

- `@Async` phải được bật bằng `@EnableAsync` hoặc cấu hình tương đương.
- Lời gọi phải **đi qua proxy**. `this.asyncMethod()` trong cùng class thường chạy đồng bộ với proxy mode mặc định.
- Chọn một `Executor` cụ thể giúp test deterministic hơn, đặt thread name, pool size và shutdown lifecycle rõ.
- Dùng `CompletableFuture<T>` hoặc `Future<T>` để **chờ kết quả và quan sát exception**, thay vì chỉ dùng `void @Async` rồi đoán task hoàn tất.
- `@Transactional` đặt trên service thực hiện SQL và được gọi từ worker qua bean proxy; nó tạo/join transaction theo trạng thái **của worker thread**.
- Timeout khi gọi `future.get(5, SECONDS)` chỉ giới hạn thời gian chờ của test; nó không tự rollback các transaction đã commit ở worker.

### Future thất bại không đồng nghĩa transaction bên ngoài cũng rollback

Nếu worker service:

```java
@Transactional
public void createThenFail(NoteRequest request) {
    store.insert(request.key(), request.body());
    throw new IllegalStateException("controlled failure");
}
```

thì unchecked exception làm transaction của **worker service** rollback theo default rules. Test dùng `CompletableFuture.get(...)` có thể nhận `ExecutionException` chứa lỗi gốc; đó là bằng chứng future thất bại, nhưng muốn chứng minh DB rollback phải kiểm tra row thực sự không tồn tại.

Ngược lại, nếu worker đã commit rồi một bước khác sau đó thất bại, **future exceptional không tự hoàn tác commit trước đó**. Phải phân biệt transaction boundary và thứ tự side effects.

## 6. Mã Java 17+ đầy đủ: JDBC H2, REST và @Async

Ta xây ứng dụng nhỏ lưu các ghi chú test. Có ba luồng:

1. `NoteWriter.create(...)` lưu một row có transaction.
2. `NoteController POST /notes` gọi service qua **HTTP thật**.
3. `AsyncNoteWriter.submit(...)` chạy trong executor rồi gọi cùng service từ **worker thread**.

Mọi test dùng key duy nhất để tránh va chạm. Schema H2 được tạo trên **test classpath**; mã Java production không phụ thuộc vào H2 cụ thể.

### 6.1. Cấu trúc files

```text
src/
├── main/
│   └── java/example/testing/transactions/
│       ├── TransactionDemoApplication.java
│       ├── NoteRequest.java
│       ├── NoteView.java
│       ├── NoteStore.java
│       ├── NoteWriter.java
│       ├── NoteController.java
│       ├── AsyncConfig.java
│       ├── AsyncNoteWriter.java
│       └── ThreadLocalScopeDemo.java
└── test/
    ├── resources/schema.sql
    └── java/example/testing/transactions/
        ├── DirectRollbackTest.java
        ├── MockMvcRollbackTest.java
        ├── RealHttpTransactionTest.java
        └── AsyncTransactionTest.java
```

### 6.2. Gradle dependencies

Trong project Spring Boot **3.5.x** được tạo bằng Spring Initializr và đã có plugins/repositories/Java toolchain tương thích, phần dependencies trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung**, không phải toàn bộ build file có thể chạy độc lập. Java 17 là minimum cho ví dụ này; Boot BOM quản lý version JDBC, H2, JUnit và Spring Framework tương thích.

Vì H2 ở `testRuntimeOnly`, **không được kết luận `main()` chạy production mà không cần datasource**. Để chạy application bên ngoài test, phải cung cấp DB/data source configuration, schema và migrations production. H2 ở đây chỉ dùng cho test.

### 6.3. Application: TransactionDemoApplication.java

Tạo `src/main/java/example/testing/transactions/TransactionDemoApplication.java`:

```java
package example.testing.transactions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TransactionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                TransactionDemoApplication.class, args);
    }
}
```

Package gốc chung giúp Spring Boot scan controller, repository và service trong ví dụ. Khi test gọi `@SpringBootTest`, Spring tìm ứng dụng trong package và cấu hình bean tương ứng.

### 6.4. Schema H2 test: schema.sql

Tạo `src/test/resources/schema.sql`:

```sql
CREATE TABLE notes (
    note_key VARCHAR(100) PRIMARY KEY,
    note_text VARCHAR(400) NOT NULL
);
```

Với `spring-boot-starter-jdbc` và embedded H2 trong test classpath, SQL initializer mặc định của Spring Boot có thể chạy `schema.sql` khi tạo test datasource. Không sử dụng Flyway/Liquibase cùng schema.sql nếu chúng tạo trùng bảng. Trong production, dùng migration/lifecycle phù hợp.

Không lưu mật khẩu, token hay PII thật vào bảng demo. Test sẽ dùng key dạng `HTTP-<UUID>`/`ASYNC-<UUID>` và nội dung thử nghiệm.

### 6.5. Request/response DTOs

Tạo `src/main/java/example/testing/transactions/NoteRequest.java`:

```java
package example.testing.transactions;

public record NoteRequest(String key, String body) {
}
```

Tạo `src/main/java/example/testing/transactions/NoteView.java`:

```java
package example.testing.transactions;

public record NoteView(String key, String state) {
}
```

Đây là hai Java records riêng, mỗi file chứa một public top-level type đúng tên. Trong demo không thêm validation annotations để tập trung vào transaction behavior. Trong HTTP API production, cần kiểm tra input, quyền truy cập, giới hạn độ dài, duplicate key và mapping lỗi an toàn.

### 6.6. JDBC storage: NoteStore.java

Tạo `src/main/java/example/testing/transactions/NoteStore.java`:

```java
package example.testing.transactions;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NoteStore {
    private final JdbcTemplate jdbc;

    public NoteStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String key, String body) {
        jdbc.update(
                "INSERT INTO notes(note_key, note_text) VALUES (?, ?)",
                key, body);
    }

    public int countByKey(String key) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notes WHERE note_key = ?",
                Integer.class, key);
        return result == null ? 0 : result;
    }

    public void deleteByKey(String key) {
        jdbc.update(
                "DELETE FROM notes WHERE note_key = ?", key);
    }
}
```

Code sử dụng **parameterized SQL** với placeholders `?` thay vì nối key vào chuỗi SQL. `NoteStore` không tự cấu hình transaction; `JdbcTemplate` tham gia connection/transaction context do Spring quản lý trên thread hiện tại. Nếu không có transaction, JDBC operation thường thực hiện với connection auto-commit theo cấu hình.

**Quan trọng:** `countByKey` bên trong transaction test có thể thấy bản ghi chưa commit của chính transaction đó. Muốn chứng minh dữ liệu committed bên ngoài, bài test sẽ **kết thúc transaction test trước khi query lại**.

### 6.7. Transactional service: NoteWriter.java

Tạo `src/main/java/example/testing/transactions/NoteWriter.java`:

```java
package example.testing.transactions;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NoteWriter {
    private final NoteStore store;

    public NoteWriter(NoteStore store) {
        this.store = store;
    }

    @Transactional
    public void create(NoteRequest request) {
        store.insert(request.key(), request.body());
    }

    @Transactional
    public void createThenFail(NoteRequest request) {
        store.insert(request.key(), request.body());
        throw new IllegalStateException(
                "controlled failure");
    }
}
```

Với `PlatformTransactionManager` phù hợp và proxy được Spring áp dụng, một lời gọi ngoài bean tới `create(...)` sẽ:

- **Join** transaction có sẵn trên chính thread ấy nếu propagation mặc định `REQUIRED` và transaction manager tương thích.
- **Mở transaction mới** nếu chưa có transaction trên worker/server thread.
- **Commit** khi method trả thành công nếu chính interceptor đã mở transaction.
- **Rollback** khi method ném unchecked exception (như `IllegalStateException`) theo rule mặc định.

Bởi vậy, cùng một `NoteWriter.create(...)` có thể bị rollback trong direct/JUnit test nhưng commit qua HTTP thật hoặc `@Async`. Đây chính là hợp đồng cần kiểm thử.

### 6.8. Controller: NoteController.java

Tạo `src/main/java/example/testing/transactions/NoteController.java`:

```java
package example.testing.transactions;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/notes")
public class NoteController {
    private final NoteWriter writer;

    public NoteController(NoteWriter writer) {
        this.writer = writer;
    }

    @PostMapping
    public ResponseEntity<NoteView> create(
            @RequestBody NoteRequest request) {
        writer.create(request);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NoteView(request.key(), "stored"));
    }

    @PostMapping("/fail")
    public ResponseEntity<NoteView> createThenFail(
            @RequestBody NoteRequest request) {
        writer.createThenFail(request);
        throw new AssertionError(
                "Expected service exception");
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ApiError> mapFailure(
            IllegalStateException error) {
        return ResponseEntity.status(
                        HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError("WRITE_FAILED"));
    }

    public record ApiError(String code) {
    }
}
```

Điểm cần lưu ý:

- Controller gọi `NoteWriter` qua **bean khác**, nên `@Transactional` service được Spring proxy intercept. Không self-invoke `this.create(...)` trên chính service để kỳ vọng proxy hoạt động.
- Khi endpoint `POST /notes` thành công, server transaction có thể commit **trước khi response HTTP 201 tới test**.
- `POST /notes/fail` gọi service ném `IllegalStateException`, làm rollback transaction của **service server-side**; exception handler trả public error code ổn định.
- Dòng `throw new AssertionError(...)` nằm sau lời gọi service chỉ để làm rõ nhánh ấy không được chạy khi service đúng. Nó **không phải expected runtime path** và không lộ ra client theo kịch bản được test.
- Ví dụ không triển khai authentication/authorization, request validation, rate limiting hay error taxonomy production. Đừng triển khai công khai nguyên trạng mà không bổ sung các ranh giới ấy.

### 6.9. Cấu hình async executor: AsyncConfig.java

Tạo `src/main/java/example/testing/transactions/AsyncConfig.java`:

```java
package example.testing.transactions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {

    @Bean(name = "lessonExecutor")
    public ThreadPoolTaskExecutor lessonExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("lesson-async-");
        executor.initialize();

        return executor;
    }
}
```

`@EnableAsync` cho phép Spring intercept `@Async`; tên `lessonExecutor` giúp test biết chắc task nào được chạy ở executor nào. `ThreadPoolTaskExecutor` là bean Spring quản lý; khi context đóng, lifecycle/destroy xử lý executor. Không tạo một executor mới trong mỗi test rồi bỏ quên thread.

**Không dùng `Thread.sleep` để “đợi async xong”**. Hãy chờ `CompletableFuture.get(timeout, unit)` hoặc dùng synchronization primitive/event phù hợp khi test yêu cầu quan sát trạng thái.

### 6.10. Async worker: AsyncNoteWriter.java

Tạo `src/main/java/example/testing/transactions/AsyncNoteWriter.java`:

```java
package example.testing.transactions;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncNoteWriter {
    private final NoteWriter writer;

    public AsyncNoteWriter(NoteWriter writer) {
        this.writer = writer;
    }

    @Async("lessonExecutor")
    public CompletableFuture<AsyncReceipt> submit(
            NoteRequest request) {
        writer.create(request);

        return CompletableFuture.completedFuture(
                new AsyncReceipt(
                        request.key(),
                        Thread.currentThread().getName()));
    }

    @Async("lessonExecutor")
    public CompletableFuture<Void> submitThenFail(
            NoteRequest request) {
        writer.createThenFail(request);
        return CompletableFuture.completedFuture(null);
    }

    public record AsyncReceipt(
            String key, String threadName) {
    }
}
```

`AsyncNoteWriter` và `NoteWriter` **là hai Spring beans**. Khi caller gọi `asyncNoteWriter.submit(...)` qua bean proxy, Spring chọn `lessonExecutor` và chạy method body ở worker thread; method body gọi `writer.create(...)` qua transactional proxy. Nếu SQL commit thành công, future hoàn thành với `AsyncReceipt`; nếu SQL/logic thất bại, future hoàn thành **exceptionally**.

Tại sao method khai báo trả `CompletableFuture.completedFuture(...)` dù là async? Trong Spring `@Async`, method mục tiêu có thể trả một future tạm đã hoàn thành; proxy trả **future của tác vụ** đã được executor submit cho caller. Khi caller đợi `get(...)`, nó nhận giá trị hoặc exception sau khi worker đã chạy.

**Lưu ý:** `@Async void` không truyền exception qua một Future; nếu cần bắt lỗi trong test và production workflow, ưu tiên `CompletableFuture<T>` hoặc một cơ chế giám sát/ack riêng. Không cho rằng task đã hoàn thành chỉ vì method được gọi.

## 7. Test 1: gọi service trực tiếp và rollback thật

Tạo `src/test/java/example/testing/transactions/DirectRollbackTest.java`:

```java
package example.testing.transactions;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE)
class DirectRollbackTest {
    @Autowired
    private NoteWriter writer;

    @Autowired
    private NoteStore store;

    private String key;

    @BeforeTransaction
    void createUniqueTestKey() {
        key = "DIRECT-" + UUID.randomUUID();
    }

    @Test
    @Transactional
    void directCallIsVisibleInsideTestTransaction() {
        writer.create(new NoteRequest(key, "direct"));

        assertEquals(1, store.countByKey(key));
        // Không commit. Spring Test rollback sau method.
    }

    @AfterTransaction
    void verifyOutsideTransaction() {
        assertEquals(0, store.countByKey(key));
    }
}
```

**Hai thời điểm kiểm tra khác nhau:**

- Trong `@Test @Transactional`, `NoteWriter.create` với `REQUIRED` tham gia transaction test, nên `countByKey(key) == 1`.
- `@AfterTransaction` chạy **sau khi Spring TestContext kết thúc transaction**; query thấy không còn row vì test đã rollback.

`@BeforeTransaction` và `@AfterTransaction` được Spring TestContext gọi với những test method có test-managed transaction. Chúng không phải JUnit `@BeforeEach`/`@AfterEach` thông thường. Đây là cách chắc hơn để **đo kết quả rollback sau transaction** thay vì đọc ngay trong transaction.

**Không dùng khóa cố định** cho nhiều test classes/CI jobs. UUID làm dữ liệu độc lập hơn, nhưng không thay thế dedicated test database.

## 8. Test 2: MockMvc đồng bộ có thể join test transaction

Tạo `src/test/java/example/testing/transactions/MockMvcRollbackTest.java`:

```java
package example.testing.transactions;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MockMvcRollbackTest {
    @Autowired
    private MockMvc mvc;

    @Autowired
    private NoteStore store;

    private String key;

    @BeforeTransaction
    void setKey() {
        key = "MOCK-" + UUID.randomUUID();
    }

    @Test
    @Transactional
    void synchronousControllerJoinsCallerTestTransaction()
            throws Exception {
        String json = """
                {"key":"%s","body":"through mock mvc"}
                """.formatted(key);

        mvc.perform(post("/notes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.key").value(key))
                .andExpect(jsonPath("$.state").value("stored"));

        assertEquals(1, store.countByKey(key));
    }

    @AfterTransaction
    void noRowAfterRollback() {
        assertEquals(0, store.countByKey(key));
    }
}
```

`MockMvc` ở đây chạy **controller đồng bộ** qua mock servlet infrastructure, không qua một HTTP socket và server thread độc lập. Trong ví dụ này, request processing tham gia test thread/transaction; vì thế `@AfterTransaction` kiểm tra row đã bị rollback.

**Đừng suy rộng:** nếu controller dùng `@Async`, `DeferredResult`, executor, messaging hoặc một transaction `REQUIRES_NEW` khác, một số side effects có thể chạy ngoài test-managed transaction dù gọi bằng MockMvc.

## 9. Test 3: HTTP thật commit bên server, rollback của test không xóa được

Tạo `src/test/java/example/testing/transactions/RealHttpTransactionTest.java`:

```java
package example.testing.transactions;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpTransactionTest {
    @Autowired
    private TestRestTemplate http;

    @Autowired
    private NoteStore store;

    @Test
    @Transactional
    void testRollbackDoesNotUndoServerCommit() {
        String serverKey = "HTTP-" + UUID.randomUUID();
        String localKey = "LOCAL-" + UUID.randomUUID();

        try {
            ResponseEntity<NoteView> response =
                    http.postForEntity(
                            "/notes",
                            new NoteRequest(serverKey, "from server"),
                            NoteView.class);

            assertEquals(
                    HttpStatus.CREATED,
                    response.getStatusCode());
            assertNotNull(response.getBody());
            assertEquals(serverKey, response.getBody().key());

            // Ghi này diễn ra ngay trong test-managed tx.
            store.insert(localKey, "from junit thread");
            assertEquals(1, store.countByKey(localKey));

            // Kết thúc transaction test một cách tường minh.
            TestTransaction.flagForRollback();
            TestTransaction.end();

            // Lúc này hai SELECT chạy ngoài test transaction.
            assertEquals(0, store.countByKey(localKey));
            assertEquals(1, store.countByKey(serverKey));
        } finally {
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }
            // Cleanup ngoài tx test, kể cả nếu assertion fail.
            store.deleteByKey(localKey);
            store.deleteByKey(serverKey);
        }
    }

    @Test
    void failedServerTransactionRollsBackItsOwnWrite() {
        String key = "FAIL-HTTP-" + UUID.randomUUID();

        try {
            ResponseEntity<NoteController.ApiError> response =
                    http.postForEntity(
                            "/notes/fail",
                            new NoteRequest(key, "should rollback"),
                            NoteController.ApiError.class);

            assertEquals(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    response.getStatusCode());
            assertNotNull(response.getBody());
            assertEquals(
                    "WRITE_FAILED",
                    response.getBody().code());
            assertEquals(0, store.countByKey(key));
        } finally {
            store.deleteByKey(key);
        }
    }
}
```

**Hai test này chứng minh hai kết luận độc lập:**

1. **Server commit sống qua rollback của JUnit:** HTTP POST `/notes` được server xử lý trên thread khác và service tự tạo/commit transaction. Sau khi `TestTransaction.end()` rollback transaction của test, row **localKey biến mất** nhưng row **serverKey vẫn tồn tại**. Test sau đó dọn row server đã commit bằng JDBC ngoài test transaction.
2. **Lỗi server rollback transaction của chính nó:** `/notes/fail` vào `NoteWriter.createThenFail`, ném unchecked exception và trả HTTP 500 công khai; database không giữ row mới vì **server service transaction** rollback. Không nên hiểu lỗi HTTP tự rollback mọi operation trước đó nếu chúng đã commit riêng.

### Vì sao kết thúc test transaction trước khi kiểm tra?

Nếu chỉ query DB từ cùng test-managed transaction, bạn có thể quan sát trạng thái chưa commit hoặc bị ảnh hưởng bởi isolation của connection. `TestTransaction.end()` giúp test **thoát hẳn transaction caller**, sau đó `store.countByKey(...)` quan sát dữ liệu ở một transaction/connection khác.

**Lưu ý lifecycle:** `TestTransaction.end()` chỉ hợp lệ khi test-managed transaction đang active. Khi gọi thủ công, bạn chịu trách nhiệm flag rollback trước, không để method kết thúc trong trạng thái mơ hồ. Đoạn `finally` xử lý trường hợp assertion lỗi trước khi transaction được kết thúc.

### Cleanup trong finally phải nằm ngoài transaction test

Một anti-pattern là thêm `@AfterEach void cleanup(){ store.deleteByKey(serverKey); }` vào class có `@Transactional` rồi tin rằng DELETE sẽ tồn tại. Với test transaction active, `@AfterEach` cũng có thể chạy **bên trong transaction test và bị rollback**, làm committed row của server vẫn còn.

Ví dụ đặt `TestTransaction.end()` trước `store.deleteByKey(...)` trong `finally` để bảo đảm cleanup nằm **ngoài transaction test**. Mỗi test cần database riêng/test key rõ để không xóa dữ liệu của người khác.

**Không sử dụng database production** cho các test có HTTP thật hoặc explicit cleanup. Đặt cấu hình `spring.datasource.*` theo test profile/container chuyên dụng.

## 10. Test 4: @Async commit trên worker khác transaction test

Tạo `src/test/java/example/testing/transactions/AsyncTransactionTest.java`:

```java
package example.testing.transactions;

import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE)
class AsyncTransactionTest {
    @Autowired
    private AsyncNoteWriter asyncWriter;

    @Autowired
    private NoteStore store;

    @Test
    @Transactional
    void asyncWorkerCommitSurvivesCallerRollback()
            throws Exception {
        String asyncKey = "ASYNC-" + UUID.randomUUID();
        String localKey = "LOCAL-" + UUID.randomUUID();

        try {
            AsyncNoteWriter.AsyncReceipt receipt =
                    asyncWriter.submit(
                            new NoteRequest(asyncKey, "worker"))
                            .get(5, TimeUnit.SECONDS);

            assertEquals(asyncKey, receipt.key());
            assertTrue(receipt.threadName()
                    .startsWith("lesson-async-"));

            // Ghi của caller nằm trong test transaction.
            store.insert(localKey, "caller");
            assertEquals(1, store.countByKey(localKey));

            TestTransaction.flagForRollback();
            TestTransaction.end();

            assertEquals(0, store.countByKey(localKey));
            assertEquals(1, store.countByKey(asyncKey));
        } finally {
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }
            store.deleteByKey(localKey);
            store.deleteByKey(asyncKey);
        }
    }

    @Test
    void asyncFailureRollsBackWorkerTransaction()
            throws Exception {
        String key = "FAIL-ASYNC-" + UUID.randomUUID();

        try {
            ExecutionException error = assertThrows(
                    ExecutionException.class,
                    () -> asyncWriter.submitThenFail(
                                    new NoteRequest(key, "bad"))
                            .get(5, TimeUnit.SECONDS));

            assertNotNull(error.getCause());
            assertInstanceOf(
                    IllegalStateException.class,
                    error.getCause());

            assertEquals(0, store.countByKey(key));
        } finally {
            store.deleteByKey(key);
        }
    }
}
```

**Vì sao phải `get(5, SECONDS)`?** Nó buộc test đợi future hoàn thành trước khi kiểm tra DB và cleanup. Không dùng `Thread.sleep(100)` rồi hy vọng worker đã commit/rollback. Tên thread `lesson-async-...` là dấu hiệu test đã đi qua executor định danh, giúp bắt lỗi tự gọi method làm `@Async` không được intercept.

**Nhưng cần phân biệt hai tầng timeout:** `future.get(5, SECONDS)` giới hạn **thời gian đợi của test**; khi timeout, worker có thể vẫn tiếp tục chạy. Nếu test thật có thể treo, cần điều phối cancellation và cleanup task/lifecycle phù hợp trước khi dọn DB. Một test timeout không tự chứng minh tác vụ đã bị hủy.

**Hai outcomes:**

- Thành công: `NoteWriter.create` mở/commit transaction của worker; rollback ở JUnit caller không xóa row.
- Thất bại: `NoteWriter.createThenFail` trong worker ném unchecked exception; transaction của worker rollback và Future báo lỗi. Test kiểm tra **cả exception lẫn absence của row**.

Test này không chứng minh “mọi @Async commit” — chỉ chứng minh luồng được setup đúng như source, nơi worker gọi một transactional service và transaction của nó kết thúc thành công.

## 11. Chạy các test bằng Gradle

Từ root project có Gradle wrapper:

```bash
./gradlew test --tests example.testing.transactions.DirectRollbackTest
./gradlew test --tests example.testing.transactions.MockMvcRollbackTest
./gradlew test --tests example.testing.transactions.RealHttpTransactionTest
./gradlew test --tests example.testing.transactions.AsyncTransactionTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.transactions.DirectRollbackTest"
.\gradlew.bat test --tests "example.testing.transactions.MockMvcRollbackTest"
.\gradlew.bat test --tests "example.testing.transactions.RealHttpTransactionTest"
.\gradlew.bat test --tests "example.testing.transactions.AsyncTransactionTest"
```

**Kỳ vọng khi project, driver và schema đúng:** có **6 JUnit test methods**: một direct, một MockMvc, hai HTTP thật và hai async. Tất cả pass. Console output thay đổi theo Gradle/JUnit/logging nên không có một chuỗi stdout chung chính xác cho các lệnh trên.

**Tại sao test isolation vẫn quan trọng khi chạy thành công từng class?** Các `@SpringBootTest` có web environment khác nhau có thể tạo context khác nhau; mỗi context có DataSource riêng hoặc chia sẻ cấu hình database tùy setup. UUID keys + finally cleanup giúp hạn chế va chạm, nhưng nếu dùng container/test DB dùng chung và parallel execution, vẫn phải bảo đảm isolation.

Nếu DB thiếu `notes`, kiểm tra `src/test/resources/schema.sql`, datasource H2 test runtime, Spring SQL initialization và migration conflict. Nếu container test thật được dùng thay H2, schema initialization có thể cần `spring.sql.init.mode=always` hoặc migration phù hợp.

## 12. Java 17 thuần: ThreadLocal không tự vượt qua executor

Để nhìn thấy sự khác nhau giữa thread caller và worker mà **không cần Spring**, tạo `src/main/java/example/testing/transactions/ThreadLocalScopeDemo.java`:

```java
package example.testing.transactions;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThreadLocalScopeDemo {
    public static void main(String[] args) throws Exception {
        ThreadLocal<String> marker = new ThreadLocal<>();
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        marker.set("test-transaction");
        try {
            String workerValue = executor.submit(
                    () -> marker.get())
                    .get(2, TimeUnit.SECONDS);

            System.out.println(
                    "caller=" + marker.get());
            System.out.println(
                    "worker=" + (workerValue == null
                            ? "no-test-transaction"
                            : workerValue));
        } finally {
            marker.remove();
            executor.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với JDK 17+ từ project root:

```bash
javac -d out src/main/java/example/testing/transactions/ThreadLocalScopeDemo.java
java -cp out example.testing.transactions.ThreadLocalScopeDemo
```

Stdout **chính xác**:

```text
caller=test-transaction
worker=no-test-transaction
```

Chương trình **không mở JDBC transaction**; nó chỉ mô tả một đặc điểm của `ThreadLocal`: giá trị gắn trên caller thread không tự xuất hiện trong executor worker thread. Đây là **phép tương tự hữu ích**, không phải bằng chứng thay thế cho integration tests có DB và Spring AOP proxy ở các mục 7–10.

**Lưu ý:** truyền manually một ThreadLocal marker sang worker không đồng nghĩa đã truyền được một transaction thật. Không cố copy transaction state/connection qua thread bằng custom `TaskDecorator` vì có thể làm sai thread-safety và resource ownership. Nếu cần atomicity giữa các bước bất đồng bộ, thiết kế transactional boundary, outbox/saga hoặc orchestration thích hợp.

## 13. @Transactional REQUIRES_NEW và transaction nằm ngoài test

Ngay cả **cùng thread**, code có thể commit riêng nếu một bean Spring-managed dùng propagation `REQUIRES_NEW`:

```java
@Service
public class IndependentWriter {
    @Transactional(
            propagation = Propagation.REQUIRES_NEW)
    public void writeIndependent() {
        // Một transaction độc lập được bắt đầu.
    }
}
```

Đây là **đoạn minh họa** (cần source file, imports và repository); chưa có trong bộ runnable. Khi method được gọi qua proxy, Spring có thể **suspend** transaction hiện có và tạo transaction mới, commit/rollback riêng. Vì vậy, một `@Transactional` test không đảm bảo rollback side effect do `REQUIRES_NEW` đã commit.

Ngược lại, `Propagation.REQUIRED` trên service gọi cùng thread thường join transaction test, nên rollback hiệu quả đối với thao tác của chính transaction ấy. Các propagation khác như `NOT_SUPPORTED`/`NEVER` cũng thay đổi hợp đồng, nhưng semantics của test-managed `@Transactional` trên test method chỉ hỗ trợ một tập annotation attributes nhất định.

### @Transactional trên test method không áp dụng mọi thuộc tính giống service

Theo Spring TestContext:

- `@Transactional` trên test: xác định có mở test transaction và transaction manager nào. `@Transactional(propagation = NOT_SUPPORTED)` hoặc `NEVER` sẽ không chạy test-managed transaction.
- Nhiều attributes như isolation, timeout, readOnly, rollbackFor/noRollbackFor trên annotation **không được xử lý đầy đủ theo semantics giống application service** trong test-managed transaction.
- Dùng `@Commit`, `@Rollback`, hoặc `TestTransaction.flagForCommit/flagForRollback` để kiểm soát outcome test transaction.
- Nếu muốn kiểm tra transaction propagation thật của service, gọi bean qua proxy và thiết kế assertion ngoài transaction phù hợp.

### Đừng kỳ vọng self-invocation kích hoạt transaction mới

Một method trong class gọi `this.otherTransactionalMethod()` thường không đi qua Spring proxy, nên `@Transactional(REQUIRES_NEW)` trên method được gọi nội bộ có thể **không được áp dụng** trong proxy mode mặc định. Lỗi này cũng xảy ra với `@Async` self-invocation. Tách thành bean khác hoặc thiết kế orchestration qua proxy rõ ràng.

## 14. Preemptive timeout có thể làm bỏ transaction test

Spring TestContext tài liệu chính thức cảnh báo một trường hợp khó phát hiện:

```java
@Test
@Transactional
void dangerousPreemptiveTest() {
    assertTimeoutPreemptively(
            Duration.ofSeconds(2),
            () -> noteWriter.create(
                    new NoteRequest("X", "value")));
}
```

Đoạn này là anti-pattern minh họa, cần imports JUnit và service; **không chạy trong bộ test runnable**.

Vì sao nguy hiểm? `assertTimeoutPreemptively(...)` có thể thực thi callback trên **thread khác** với thread Spring đã gắn transaction state. Khi callback gọi service `@Transactional(REQUIRED)`, service thấy không có transaction caller và có thể mở/commit transaction riêng. Test framework vẫn rollback test-managed transaction trên thread ban đầu — nhưng commit của callback đã nằm ngoài nó.

**Khi cần timeout assertion:**

- `assertTimeout(...)` của JUnit thường **không preemptive**, chạy executable trên thread gọi và đo thời gian; có giới hạn là không thể cắt ngang tác vụ bị treo.
- Với integration tests cần chống treo, dùng timeout ở mức build/runner, API timeout cụ thể, hoặc cấu hình JUnit có hiểu biết về thread mode; không thay bằng `assertTimeoutPreemptively` một cách mù quáng.
- `@Timeout` của JUnit có cấu hình thread mode khác nhau. Đừng đồng nhất nó với `assertTimeoutPreemptively` mà không đọc runner configuration.
- Nếu test đã có committed side effect, timeout không bảo đảm cleanup đã chạy; cần lifecycle/compensating cleanup riêng.

## 15. Event listener, message queue và after-commit callbacks

Các luồng khác cũng dễ vượt khỏi rollback của test:

### 15.1. @TransactionalEventListener(AFTER_COMMIT)

Một event listener dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ chạy khi transaction phù hợp **commit**. Trong một `@Transactional` test mặc định rollback, listener AFTER_COMMIT thường **không chạy**. Nếu test expected event side effect, không nhất thiết listener bị lỗi; có thể transaction chưa commit đúng phase.

Ngược lại, nếu event được phát trong một **HTTP server transaction** commit hoặc một **worker transaction** commit, listener AFTER_COMMIT có thể chạy dù test thread rollback. Nếu listener còn `@Async`, side effect có thể đến muộn; test phải chờ một acknowledgement/event có kiểm soát và có cleanup phù hợp.

### 15.2. @Async event handler / messaging

Nếu service gửi message đến queue hoặc gọi HTTP client bên ngoài ngay trong test transaction, rollback DB không tự “thu hồi” message đã gửi. Message broker và remote service không tham gia JDBC rollback chỉ vì caller có `@Transactional`. Đây là lý do transaction-aware event publication, transactional outbox hoặc saga có giá trị trong production.

**Hạn chế của test dùng fake:** nếu mock broker chỉ ghi vào một List trong cùng thread, test có thể bỏ sót side effects/visibility/retry của hệ thống thật. Dùng integration test phù hợp khi hợp đồng liên quan external messages.

### 15.3. CompletableFuture và scheduler không tự kế thừa transaction

`CompletableFuture.supplyAsync(...)` thường chạy trên common pool hoặc executor bạn truyền. Đây cũng là thread boundary. Nếu task gọi DAO trực tiếp không có transaction interceptor, hành vi commit phụ thuộc JDBC connection/autocommit. Nếu task gọi transactional service bean qua proxy, nó dùng transaction của worker, không của JUnit.

## 16. Dữ liệu test: setup, cleanup và @Sql

**Nguyên tắc thiết kế dữ liệu test cho cross-thread tests:**

1. **Dedicated test database** (H2 riêng mỗi context, Testcontainers cho engine thật) và credentials an toàn.
2. Mỗi test tự tạo key độc nhất; không phụ thuộc thứ tự methods.
3. Không trỏ datasource test vào production/shared staging có dữ liệu thật.
4. Chờ HTTP response/future hoàn tất trước khi kiểm tra kết quả cuối cùng.
5. Dọn committed data **ngoài transaction sẽ rollback**, ví dụ trong `finally` sau khi `TestTransaction.end()`, hoặc bằng cleanup component có transaction riêng được kiểm soát.
6. Nếu task có thể còn chạy sau timeout, không dọn DB song song rồi tuyên bố môi trường sạch; phải hủy/chờ worker hoặc cô lập container/suite để không race.
7. Dùng `@AfterTransaction` để xác minh state **sau rollback** ở test do Spring TestContext quản lý, không chỉ trong method.
8. Với multi-thread tests, kiểm tra database isolation/transaction manager để hiểu session nào có thể thấy dữ liệu chưa commit.

### @BeforeEach và @AfterEach nằm ở đâu?

Với test-managed `@Transactional`, lifecycle `@BeforeEach` và `@AfterEach` của JUnit thường chạy **bên trong transaction test**. Vì thế:

```java
@AfterEach
void cleanup() {
    store.deleteByKey("HTTP-A");
}
```

có thể **không dọn được một server-side committed row**: DELETE bị rollback cùng test transaction. Nếu cần việc trước/sau transaction, Spring Test có `@BeforeTransaction`/`@AfterTransaction`. Trong bộ runnable, với HTTP/async, cleanup được đặt tường minh **sau khi kết thúc test-managed transaction** để tránh hiểu nhầm.

### @Sql và transaction modes

`@Sql` hữu ích để seed/cleanup fixture, nhưng phải xem transaction mode:

- Với `@Sql` mặc định cùng test transaction, dữ liệu seed/delete có thể rollback với transaction test.
- `@SqlConfig(transactionMode = ISOLATED)` có thể chạy script trong **transaction riêng đã commit**, phù hợp một số setup/cleanup nhưng dễ làm rò state nếu dùng không cẩn thận.
- `@Sql(executionPhase = AFTER_TEST_METHOD)` không tự bảo đảm chạy ngoài test-managed transaction; điều đó phụ thuộc listener/mode.
- Đừng cho rằng một `@Sql` DELETE bất kỳ sẽ xóa committed server writes khi cleanup nằm sai transaction.

Nếu toàn bộ database dành riêng cho một integration suite, có thể thiết kế reset schema, truncate hoặc recreate ephemeral container giữa tests; cân nhắc chi phí khởi động với độ ổn định. Không dùng `DELETE FROM ...` không có điều kiện trên database mà bạn không chắc được cô lập.

## 17. So sánh các chiến lược kiểm thử khi có thread boundary

| Mục tiêu | Tầng test nên chọn | Transaction/cleanup strategy |
| --- | --- | --- |
| Logic Java/service không cần DB | JUnit unit + fake/mock | Không tạo transaction thật |
| Service JDBC business method và transaction join | `@SpringBootTest` hoặc JDBC slice | `@Transactional` rollback + `@AfterTransaction` khi cần |
| MVC controller đồng bộ, JSON mapping | `MockMvc` / `@WebMvcTest` | Có thể join caller tx; vẫn test ranh giới khi có async |
| HTTP status/headers/serialization/socket thật | `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate`/HTTP client | **Không tin test rollback; cleanup committed rows** |
| Async executor + transactional service | `@SpringBootTest` với `@EnableAsync` + real executor | `CompletableFuture.get(timeout)`, kiểm tra DB sau completion, cleanup độc lập |
| Event sau commit / queue | Integration + broker/container phù hợp | Chờ acknowledgement, cleanup message/DB, kiểm soát idempotency |
| Transaction propagation `REQUIRES_NEW` | Integration test với proxy thật | Observe committed state ngoài caller tx |
| Reactive database pipeline | R2DBC slice/integration + Reactor transaction tools | Reactor Context + `TransactionalOperator`, không dựa vào JDBC ThreadLocal |

**Không chọn mức test rộng chỉ vì thích:** nếu một service thuần chỉ tính tổng tiền, JUnit không có Spring/DB sẽ nhanh và ổn định hơn. Nhưng với ranh giới HTTP thật, @Async, commit/rollback và DB visibility, **mock hoàn toàn không chứng minh được** các side effects thực.

## 18. Các lỗi thường gặp

**1. Gắn `@Transactional` trên class `@SpringBootTest(RANDOM_PORT)` rồi tin HTTP writes tự rollback.** Server thread dùng transaction khác, commit có thể vẫn còn.

**2. Nhầm MockMvc với HTTP qua socket.** MockMvc controller đồng bộ thường chạy trong test thread; `RANDOM_PORT` có server riêng. Hai kiểu test có rollback semantics khác nhau.

**3. Chỉ assert HTTP 201, không kiểm tra DB sau transaction test.** Có thể bỏ qua committed side effects hoặc data contamination.

**4. Kiểm tra DB trong cùng transaction rồi nói đã commit.** Đọc của chính transaction có thể thấy uncommitted write.

**5. Dùng `@AfterEach` DELETE trong test `@Transactional` để dọn server commit.** DELETE có thể bị rollback; chuyển cleanup ra ngoài transaction.

**6. Kết thúc TestTransaction nhưng quên flag rollback.** Dễ tạo kết quả khó hiểu; gọi `flagForRollback()` và `end()` theo đúng ý định.

**7. Gọi `@Async` method bằng `this.method()` trong cùng bean.** Proxy không intercept, method có thể chạy đồng bộ, test xanh giả.

**8. Gắn `@Async` nhưng thiếu `@EnableAsync`/executor đúng.** Method không thật sự chạy trên worker như mong muốn. Assert thread name/observable behavior.

**9. Dùng `Thread.sleep` để chờ task.** Dễ flaky trên CI; dùng Future/acknowledgement có timeout.

**10. Không kiểm tra `CompletableFuture` exception.** Một `void @Async` có thể lỗi ở background chỉ được log; test vẫn xanh. Dùng typed Future nếu cần assert lỗi.

**11. Tưởng Future exceptional làm rollback mọi transaction trước đó.** Commit đã thành công trước exception vẫn tồn tại; inspect transaction boundaries.

**12. Tưởng `@Transactional(REQUIRES_NEW)` tham gia rollback caller.** Nó có thể mở/commit transaction độc lập, ngay trên cùng thread.

**13. Dùng `assertTimeoutPreemptively` với test-managed transaction.** Callback chạy trên thread khác và có thể commit ngoài transaction test.

**14. Tưởng `@TransactionalEventListener(AFTER_COMMIT)` luôn chạy trong transactional test mặc định rollback.** Nó cần commit đúng phase; khi test rollback có thể không chạy.

**15. Dùng cùng một key/DB state cho mọi test.** Commits từ HTTP/async test làm duplicate key hoặc test phụ thuộc chạy trước/sau.

**16. Dùng test DB trỏ nhầm production.** Cleanup/insert thử nghiệm là destructive side effect; phải dùng dedicated test instance/schema.

**17. Quên khác biệt JDBC vs reactive transaction.** Imperative ThreadLocal không phải Reactor Context transaction propagation.

**18. Lạm dụng @DirtiesContext để xóa committed DB rows.** Reload Spring context không bảo đảm xóa database; cần cleanup/migration/container lifecycle thật.

**19. Coi HTTP 500 là bằng chứng DB đã rollback.** Nếu operation khác đã commit trước lỗi, dữ liệu vẫn còn. Assert database sau request.

**20. Khi test timeout, cleanup dữ liệu trong lúc async worker còn chạy.** Worker có thể insert **sau** cleanup và để lại data. Hủy/chờ task hoặc cô lập environment.

## 19. Checklist QA trước khi kết luận rollback an toàn

**Xác định boundary:**

- Test gọi service trực tiếp, MockMvc đồng bộ, HTTP socket thật hay executor?
- Có Spring TestContext test transaction không? `@Transactional` đặt ở đâu?
- Có `PlatformTransactionManager` đúng và bean proxy thật không?
- Code ghi dữ liệu chạy trên **thread nào**? Có qua `@Async`/`CompletableFuture` không?
- Transaction propagation của service là `REQUIRED`, `REQUIRES_NEW` hay `NOT_SUPPORTED`?
- Test có gọi method nội bộ qua `this` khiến AOP proxy bị bỏ qua không?

**Quan sát dữ liệu:**

- Có phân biệt uncommitted local row và committed server/worker row không?
- Test kiểm tra dữ liệu sau khi **test transaction đã end/rollback** chưa?
- Nếu HTTP trả error/future thất bại, có assert state DB thay vì chỉ status/exception?
- Kết quả phụ thuộc DB isolation hay trên một kết nối riêng không?
- Có test cả success và failure path của worker/server không?

**Async và timeout:**

- `@EnableAsync`, executor, thread prefix và `@Async("...")` có đúng không?
- Có chờ Future/ack với timeout hữu hạn, không dùng `Thread.sleep`?
- Nếu timeout/cancel, worker thực sự đã dừng trước cleanup chưa?
- Có tránh `assertTimeoutPreemptively` trên các thao tác transaction-sensitive?
- Error của async được thu vào Future hay xử lý/log một cách có kiểm soát?

**Cleanup và CI:**

- DB riêng cho integration tests, không có credentials production?
- Key/fixture riêng mỗi method, không dựa thứ tự test?
- Dọn committed HTTP/@Async rows **ngoài test transaction**?
- Nếu dùng `@AfterEach`/`@Sql`, transaction mode của cleanup có đúng không?
- Có ngăn test song song phá dữ liệu của nhau hoặc dùng container lifecycle không phù hợp?
- Kết luận chỉ trong phạm vi test thực sự chạy, không coi mock test là kiểm tra DB/network thật?

**Kết luận:** `@Transactional` trong JUnit test **không phải cơ chế dọn toàn bộ side effects của một workflow**. Với imperative Spring TestContext, transaction được gắn với thread. Gọi trực tiếp hoặc MockMvc đồng bộ thường có thể rollback, nhưng **HTTP thật qua RANDOM_PORT**, **@Async worker** và các transaction độc lập có thể commit ngoài transaction test. Test đúng phải xác định **thread + proxy + propagation + transaction manager**, chờ task hoàn tất, đọc DB sau khi rollback caller và dọn các committed writes bằng lifecycle **ngoài transaction test**.

## 20. Tài liệu tham khảo

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `RANDOM_PORT`/`DEFINED_PORT` và việc HTTP client/server ở transactions khác nhau.
- [Spring Framework 6.2 — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): `ThreadLocal`, rollback, `TestTransaction`, `@BeforeTransaction`/`@AfterTransaction`, preemptive timeout.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@EnableAsync`, `@Async`, executor qualification, proxy self-invocation và Future exceptions.
- [Spring Framework — @Transactional API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): thread-bound transaction semantics và propagation.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/reference/how-to/data-initialization.html): `schema.sql` và embedded database initialization.
