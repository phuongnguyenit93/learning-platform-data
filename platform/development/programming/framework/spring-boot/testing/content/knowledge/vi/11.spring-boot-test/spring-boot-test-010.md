# Giao dịch trên luồng HTTP server khác với giao dịch của phương thức test trong @SpringBootTest

## 1. Hiểu đúng vấn đề: @Transactional ở test không bao trùm HTTP request thật

Một lỗi rất dễ gặp khi viết integration test Spring Boot là đặt `@Transactional` lên phương thức test, gọi API qua HTTP rồi tin rằng **mọi thay đổi dữ liệu của API sẽ được rollback khi test kết thúc**. Điều này thường **sai** khi dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc `DEFINED_PORT`.

Nguyên nhân: **test-managed transaction** do Spring TestContext bắt đầu và gắn với **luồng đang chạy phương thức test**. Trong khi đó, HTTP request thật được embedded server xử lý trên **luồng xử lý request khác** (hoặc execution context khác trong mô hình reactive). Transaction context kiểu thread-bound của test không tự truyền qua socket HTTP sang server.

Ví dụ hai luồng hoạt động độc lập:

```text
LUỒNG TEST / JUnit                      LUỒNG HTTP SERVER / ứng dụng

@Transactional @Test
  |
  |-- [test transaction T1 bắt đầu]
  |
  |-- HTTP POST /visits  ------------->  Controller nhận HTTP request
  |                                        |
  |                                        v
  |                                      Service @Transactional
  |                                        |
  |                                      [transaction T2 bắt đầu]
  |                                        |
  |                                      Repository.save(...)
  |                                        |
  |                                      [T2 commit nếu thành công]
  |                                        |
  |<------------- HTTP 201 -------------  Response
  |
  |-- [T1 rollback theo test framework]
  |
  v
Dòng dữ liệu mà T2 đã commit
KHÔNG tự biến mất vì T1 rollback
```

Sơ đồ biểu diễn tình huống thông thường: service thật được Spring gọi qua transaction proxy, propagation mặc định `REQUIRED`, có transaction manager và database phù hợp. **Không phải mọi HTTP request đều tự có transaction**; transaction T2 chỉ xuất hiện nếu server-side code/configuration thật sự khởi tạo transaction.

**Quy tắc cốt lõi:** rollback của test chỉ bảo đảm rollback những thao tác **đã tham gia vào test-managed transaction T1**. Nó không hoàn tác transaction độc lập T2 của server chỉ vì T1 và T2 cùng một JVM, cùng test class hoặc cùng database.

## 2. Test-managed transaction và application-managed transaction khác nhau thế nào?

Spring TestContext cung cấp `TransactionalTestExecutionListener`, phối hợp với `PlatformTransactionManager` để mở transaction cho test method/class được đánh dấu `@Transactional`. Với cấu hình mặc định phù hợp, transaction của test **rollback sau mỗi test**.

Ở phía ứng dụng, `@Transactional` trên một Spring bean được xử lý qua transaction interceptor/proxy hoặc cơ chế giao dịch tương ứng. Khi một HTTP request được xử lý trên server thread, interceptor tạo hoặc tham gia transaction **trong ngữ cảnh server-side của request đó**, không mượn transaction của luồng test.

| Đặc điểm | Test-managed transaction | Transaction phía HTTP server |
|---|---|---|
| Ai khởi tạo? | Spring TestContext khi chạy test có `@Transactional` | Application transaction infrastructure khi server gọi bean có transaction boundary |
| Luồng/ngữ cảnh | Luồng thực thi test (thread-bound) | Luồng hoặc context xử lý request trong server |
| Phạm vi | Code tham gia transaction đang bound với test thread | Code server được transaction interceptor quản lý |
| Kết thúc mặc định | TestContext rollback sau test, trừ khi đổi chính sách | Thường commit khi lời gọi transactional kết thúc thành công; rollback tùy exception/rule |
| `@Rollback`/`@Commit` trên test | Điều khiển test-managed transaction | **Không trực tiếp điều khiển** transaction độc lập trên server |
| HTTP POST thật từ test | Là lời gọi client; không tự kéo server vào T1 | Được xử lý ở phía server, tạo transaction riêng nếu cấu hình |
| MockMvc đồng bộ cùng test thread | Có thể tham gia T1 trong những điều kiện phù hợp | Thường không mở luồng HTTP server thật; xem thêm mục 7 |

Một điểm quan trọng: `@Transactional` là **khai báo ý định quản lý transaction**, không phải bằng chứng một transaction đã được áp dụng cho lời gọi cụ thể. Proxy boundary, propagation, transaction manager, lời gọi nội bộ qua `this` và thread chuyển đổi đều ảnh hưởng kết quả.

## 3. @SpringBootTest với RANDOM_PORT, DEFINED_PORT và MOCK

`@SpringBootTest` cho phép chọn web environment. Đối với chủ đề transaction, sự khác biệt trong **đường đi của request** rất quan trọng.

| Cấu hình | Đường gọi thường gặp | Có HTTP server thật? | Transaction của test có tự bao trùm request? |
|---|---|---|---|
| `RANDOM_PORT` | `TestRestTemplate`/HTTP client → socket → embedded server | Có | **Không**; server xử lý độc lập |
| `DEFINED_PORT` | HTTP client → cổng cố định/cấu hình → server | Có | **Không** |
| `MOCK` + `@AutoConfigureMockMvc` | `MockMvc.perform(...)` → Servlet MVC trong cùng tiến trình, thường cùng test thread | Không mở HTTP listener thực | **Có thể** tham gia T1 khi xử lý đồng bộ qua cùng thread và propagation phù hợp |
| `NONE` | Không tạo web environment | Không | Không có HTTP request thật ở cấu hình này |

Với `MOCK`, `@SpringBootTest` tự nó **không có nghĩa một `MockMvc` bean đã sẵn sàng**: trong test Spring Boot MVC, thường cần `@AutoConfigureMockMvc` để cấu hình và inject `MockMvc`.

**Tránh kết luận tuyệt đối** rằng mọi lệnh `MockMvc.perform` đều dùng chung transaction: async dispatch, `@Async`, các luồng do ứng dụng tạo, `REQUIRES_NEW`, callback ngoài transaction hoặc lời gọi sang tiến trình khác có thể nằm ngoài T1. Ngược lại, khi dùng HTTP thật, không thể lấy `@Transactional` ở test method làm cách tự động rollback thay đổi được commit ở phía server.

## 4. Ví dụ đầy đủ Java 17+ / Spring Boot 3.x / JPA / H2

Ta xây dựng ứng dụng nhỏ có endpoint `POST /visits?label=...` để ghi một bản ghi vào database. Sau đó có **hai bài test**:

1. `RANDOM_PORT` + `TestRestTemplate`: rollback transaction của test, kiểm tra bản ghi đã được HTTP server commit **vẫn tồn tại**.
2. `MOCK` + `MockMvc` đồng bộ: cùng service và cùng propagation `REQUIRED`, nhưng request xử lý trên test thread; rollback T1 làm bản ghi **biến mất**.

Đây là ví dụ thực hành, không khuyến nghị dùng H2 thay mọi test database production. H2 được dùng để minh họa transaction trong cùng JVM. Khi dự án phụ thuộc SQL dialect/locking/constraint cụ thể, hãy dùng database phù hợp (chẳng hạn Testcontainers với PostgreSQL).

### 4.1. Dependencies cần có

Trong dự án Spring Boot 3.x quản lý dependency versions và dùng Java 17+, cần các thư viện tương đương:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình Gradle**, giả định build script đã có Spring Boot/Java plugin và repositories. Với Maven, dùng các dependency tương đương và plugin chạy JUnit Jupiter phù hợp. Ví dụ dùng `jakarta.persistence` (Spring Boot 3.x), không dùng `javax.persistence` của các dự án cũ. Với Spring Boot 4 hoặc cơ chế module test khác, kiểm tra lại tọa độ starter/import phù hợp phiên bản.

Cấu trúc source đề xuất:

```text
src/main/java/com/example/txhttp/
  TxHttpDemoApplication.java
  Visit.java
  VisitRepository.java
  VisitService.java
  VisitController.java

src/test/java/com/example/txhttp/
  RealHttpTransactionTest.java
  MockMvcTransactionTest.java
```

### 4.2. Application bootstrap

Tệp `src/main/java/com/example/txhttp/TxHttpDemoApplication.java`:

```java
package com.example.txhttp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxHttpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxHttpDemoApplication.class, args);
    }
}
```

Đặt application class ở package cha `com.example.txhttp` để Spring Boot có thể tìm controller, service, JPA entity và repository của ví dụ. Không cần mở server thủ công trong test: `@SpringBootTest(RANDOM_PORT)` sẽ khởi động embedded server theo cơ chế Boot.

### 4.3. Entity và repository thật

Tệp `src/main/java/com/example/txhttp/Visit.java`:

```java
package com.example.txhttp;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.Objects;

@Entity
@Table(name = "visits")
public class Visit {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String label;

    protected Visit() {
    }

    public Visit(String label) {
        this.label = Objects.requireNonNull(label, "label");
    }

    public Long getId() {
        return id;
    }

    public String getLabel() {
        return label;
    }
}
```

Tệp `src/main/java/com/example/txhttp/VisitRepository.java`:

```java
package com.example.txhttp;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VisitRepository extends JpaRepository<Visit, Long> {
    long countByLabel(String label);
    Optional<Visit> findByLabel(String label);
}
```

Repository ở đây là **Spring Data JPA repository thật**, không phải Mockito mock. Điều này rất quan trọng: để thấy khác biệt rollback, test phải có dữ liệu được ghi thật vào một database chia sẻ giữa các kết nối. `label` là unique để mỗi ca test có thể xác định và dọn đúng bản ghi của mình.

### 4.4. Service tạo transaction ở phía ứng dụng

Tệp `src/main/java/com/example/txhttp/VisitService.java`:

```java
package com.example.txhttp;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VisitService {

    private final VisitRepository repository;

    public VisitService(VisitRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long record(String label) {
        Visit saved = repository.save(new Visit(label));
        return saved.getId();
    }
}
```

`@Transactional` đặt trên phương thức `public` của Spring-managed service. Controller bên ngoài gọi qua service bean do Spring inject, nên trong setup Spring Boot/JPA thông thường, transaction interceptor tạo/tham gia transaction.

Với propagation mặc định `REQUIRED`:
- **Ở luồng HTTP server**, không có T1 bound từ test, nên service thường mở một transaction T2 và commit khi `record` hoàn tất thành công.
- **Ở MockMvc đồng bộ cùng test thread**, test-managed T1 đang active; lời gọi service với `REQUIRED` thường **tham gia T1** thay vì tự commit độc lập.

Một thao tác `INSERT` có thể được phát xuống database trước khi transaction commit (ví dụ do `GenerationType.IDENTITY` cần ID). **INSERT đã được gửi không đồng nghĩa đã commit**. Đây là lý do phải xác minh trạng thái **sau rollback** chứ không chỉ nhìn thấy ID hoặc `save` trả về.

### 4.5. Controller HTTP

Tệp `src/main/java/com/example/txhttp/VisitController.java`:

```java
package com.example.txhttp;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/visits")
public class VisitController {

    private final VisitService service;

    public VisitController(VisitService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Long> create(@RequestParam String label) {
        Long id = service.record(label);
        return ResponseEntity.status(HttpStatus.CREATED).body(id);
    }
}
```

HTTP response `201 Created` cho biết controller đã xử lý thành công theo logic trên. Trong ví dụ đồng bộ này, transaction của service thường đã hoàn tất trước khi controller gửi response. Với một ứng dụng có queue/async background worker hoặc transaction event khác, response 201 **không nhất thiết** chứng minh toàn bộ công việc nền đã commit.

## 5. Test 1: RANDOM_PORT và HTTP thật — server commit nằm ngoài rollback của test

Tệp `src/test/java/com/example/txhttp/RealHttpTransactionTest.java`:

```java
package com.example.txhttp;

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
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:h2:mem:tx_http_real;DB_CLOSE_DELAY=-1",
                "spring.jpa.hibernate.ddl-auto=create-drop",
                "spring.jpa.open-in-view=false"
        })
class RealHttpTransactionTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    VisitRepository visits;

    @Test
    @Transactional
    void serverWriteSurvivesRollbackOfTheTestTransaction() {
        String label = "real-" + UUID.randomUUID();

        try {
            assertTrue(TestTransaction.isActive());

            ResponseEntity<Long> response = rest.postForEntity(
                    "/visits?label={label}",
                    null,
                    Long.class,
                    label);

            assertEquals(HttpStatus.CREATED, response.getStatusCode());
            assertNotNull(response.getBody());

            // Kết thúc test-managed T1 với rollback NGAY BÂY GIỜ.
            TestTransaction.flagForRollback();
            TestTransaction.end();
            assertFalse(TestTransaction.isActive());

            // Giao dịch T2 do HTTP server tạo đã commit độc lập.
            assertEquals(1L, visits.countByLabel(label));
        } finally {
            // Dù assertion trước đó lỗi, đừng để T1 còn active khi dọn.
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }

            // Dọn đúng record thuộc ca test ngoài T1.
            visits.findByLabel(label).ifPresent(visits::delete);
        }
    }
}
```

### 5.1. Vì sao test này chứng minh được điều cần học?

- `@SpringBootTest(RANDOM_PORT)` khởi động HTTP server thật ở cổng được cấp. `TestRestTemplate` được cấu hình với base URL của local server, nên đường dẫn tương đối `/visits` gửi HTTP request đến server.
- `@Transactional` trên test khiến Spring TestContext bắt đầu transaction **T1** cho test thread.
- `rest.postForEntity(...)` đi qua mạng loopback tới HTTP worker thread. Dù ở cùng JVM, server không tự thấy thread-bound T1.
- Controller gọi `VisitService.record`; transaction proxy của service xử lý một transaction **T2** bên phía server và commit khi xử lý thành công.
- `TestTransaction.flagForRollback(); TestTransaction.end();` **thực hiện rollback T1 trước khi test kết thúc**, để bài test kiểm tra trạng thái sau rollback ngay trong cùng một method.
- `visits.countByLabel(label) == 1` **sau T1 rollback** là bằng chứng bản ghi do request HTTP tạo không bị rollback cùng T1.
- Khối `finally` dọn bản ghi bằng repository thật ngoài test transaction. Nếu chỉ trông chờ rollback T1 mà không cleanup, dữ liệu HTTP đã commit có thể ảnh hưởng ca test khác.

**Không đồng nhất** `TestTransaction.end()` với `TransactionTemplate` của server: nó chỉ kết thúc test-managed transaction đang active trong test thread. Ở đây test chủ động dùng `flagForRollback` để không phụ thuộc một callback tự động cuối method.

Nếu test fail trước khi request thành công, khối finally vẫn cố làm sạch record có label tương ứng; nhưng nếu ứng dụng thực thi bất đồng bộ sau response hoặc gặp sự cố kết nối, hệ thống có thể cần chiến lược cleanup/retry riêng. Ví dụ này dùng service JPA đồng bộ để giữ kết quả xác định.

### 5.2. Những điều kiện bảo đảm tính minh họa

- JDBC URL `jdbc:h2:mem:tx_http_real;DB_CLOSE_DELAY=-1` làm nhiều connection trong **cùng JVM** cùng truy cập một H2 in-memory database đã định danh; option `DB_CLOSE_DELAY=-1` giữ database sống khi connection tạm đóng. Đây là cấu hình **chỉ cho ví dụ test**, không phải production.
- `spring.jpa.hibernate.ddl-auto=create-drop` tạo/bỏ schema trong vòng đời application context của test. Không áp dụng `create-drop` trên database production.
- `UUID.randomUUID()` tạo label riêng, tránh các test chia sẻ cùng business key.
- `VisitRepository` dùng JPA thật; `save` không bị mock.
- `TestRestTemplate` thực sự gọi HTTP endpoint và sau đó repository truy vấn DB để assert dữ liệu sau rollback.

Từng điều kiện là một phần của bằng chứng. Nếu test thay repository bằng Mockito mock và chỉ `verify(save(...))`, nó **không thể** chứng minh commit/rollback dữ liệu thật.

## 6. Test 2: MockMvc đồng bộ — lời gọi có thể cùng tham gia T1

Để so sánh, dùng chính controller, service và repository trên nhưng chạy request bằng `MockMvc` **trong cùng luồng test**. Không có HTTP server socket thực trong bài test `MOCK` này.

Tệp `src/test/java/com/example/txhttp/MockMvcTransactionTest.java`:

```java
package com.example.txhttp;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = {
                "spring.datasource.url=jdbc:h2:mem:tx_http_mock;DB_CLOSE_DELAY=-1",
                "spring.jpa.hibernate.ddl-auto=create-drop",
                "spring.jpa.open-in-view=false"
        })
@AutoConfigureMockMvc
class MockMvcTransactionTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    VisitRepository visits;

    @Test
    @Transactional
    void synchronousMockMvcWriteIsRolledBackWithTestTransaction()
            throws Exception {
        String label = "mock-" + UUID.randomUUID();

        mvc.perform(post("/visits").param("label", label))
                .andExpect(status().isCreated());

        // Cùng thread và propagation REQUIRED: dữ liệu nhìn thấy trong T1.
        assertEquals(1L, visits.countByLabel(label));

        TestTransaction.flagForRollback();
        TestTransaction.end();

        // Sau rollback T1, record của lời gọi đồng bộ không còn.
        assertEquals(0L, visits.countByLabel(label));
    }
}
```

### 6.1. Tại sao kết quả khác với HTTP thật?

Trong đường đi `MockMvc` **đồng bộ** thông thường:

```text
Test thread có transaction T1
    |
    +-- MockMvc.perform(...)
         |
         +-- DispatcherServlet + Controller (cùng thread)
             |
             +-- VisitService.record(...) qua Spring proxy
                   |
                   +-- @Transactional(REQUIRED) tham gia T1
                         |
                         +-- Repository.save(...)
    |
    +-- TestTransaction.end() rollback T1
         |
         +-- Dữ liệu chưa commit bị rollback
```

Cả hai bài test gọi cùng một `VisitService`, cùng quy tắc `@Transactional` và repository thật. **Điểm khác là đường thực thi**: `MockMvc` đồng bộ không đi qua cổng HTTP riêng, còn `TestRestTemplate` với `RANDOM_PORT` thì có.

Trong thực tế, không phải mọi xử lý qua `MockMvc` đều thuộc cùng T1. Những trường hợp dưới đây có thể làm kết luận thay đổi:
- Controller/service chuyển việc sang `@Async`, executor, event listener bất đồng bộ hoặc request async dispatch.
- Service dùng propagation `REQUIRES_NEW` và mở transaction độc lập.
- Test dùng preemptive timeout khiến code chạy trên luồng khác.
- Code gửi message hoặc HTTP sang một service khác.
- Application có transaction manager đặc biệt, reactive transaction context hoặc nhiều datasource.

Bởi vậy, khi test **transaction boundary**, cần kiểm tra hành vi thực qua đường đi cụ thể, không chỉ phân loại bằng tên công cụ.

### 6.2. Một đối chiếu ngắn

| Assertion | `RANDOM_PORT` + HTTP thật | `MOCK` + MockMvc đồng bộ |
|---|---|---|
| Test có `@Transactional` | T1 được bắt đầu ở test thread | T1 được bắt đầu ở test thread |
| Service có `@Transactional(REQUIRED)` | Server thread thường mở T2 | Service thường tham gia T1 |
| Request trả 201 | Có thể đã commit T2 | Có thể chưa commit, vẫn ở trong T1 |
| T1 rollback | Không tác động tới T2 đã commit | Rollback các thay đổi tham gia T1 |
| Truy vấn sau T1 rollback | Bản ghi HTTP còn tồn tại trong ví dụ | Bản ghi MockMvc không còn trong ví dụ |
| Cần cleanup dữ liệu? | **Có**, nếu dữ liệu T2 đã commit | Thường không cần cho dữ liệu chỉ thuộc T1; vẫn phải xem các side effect khác |

## 7. @Rollback, @Commit và TestTransaction ảnh hưởng tới transaction nào?

Spring TestContext hỗ trợ những công cụ điều khiển **test-managed transaction**:

- `@Transactional` trên test method/class: yêu cầu Spring TestContext mở transaction cho test khi có transaction manager phù hợp.
- `@Rollback` (mặc định rollback) và `@Commit`: định hướng việc kết thúc **transaction của test**.
- `TestTransaction.isActive()`: kiểm tra test-managed transaction hiện đang active trong luồng kiểm thử.
- `TestTransaction.flagForRollback()` / `flagForCommit()`: chỉ định cách kết thúc transaction của test.
- `TestTransaction.end()`: kết thúc transaction của test đang active theo flag hiện tại.
- `TestTransaction.start()`: bắt đầu test-managed transaction mới trong ngữ cảnh được framework hỗ trợ.

Ví dụ:

```java
assertTrue(TestTransaction.isActive());
TestTransaction.flagForRollback();
TestTransaction.end();
assertFalse(TestTransaction.isActive());
```

Đây là **đoạn minh họa bên trong Spring transactional test**, không phải tệp Java độc lập; `TestTransaction` thuộc `org.springframework.test.context.transaction`.

**Sai lầm cần tránh:** thêm `@Rollback(true)` hoặc `@Commit` lên một test gọi HTTP thật rồi kỳ vọng chúng điều khiển transaction của server. Chúng không gửi tín hiệu rollback/commit nào qua HTTP. Server chỉ biết transaction context của mình.

Nếu dùng `@BeforeTransaction`/`@AfterTransaction`, đây là lifecycle callbacks chạy **ngoài test-managed transaction**, có ích để chuẩn bị/kiểm chứng trạng thái commit sau khi test transaction kết thúc. Ngược lại, `@BeforeEach` và `@AfterEach` thông thường chạy trong phạm vi transaction của một Spring transactional test nếu transaction vẫn active. Vì vậy, **xóa dữ liệu ở `@AfterEach` có thể bị rollback cùng test**, khiến bản ghi đã được HTTP server commit không được xóa thực sự.

Trong ví dụ mục 5, code chủ động gọi `TestTransaction.end()` trước khi repository cleanup, nhờ đó xóa được thực hiện ngoài T1.

## 8. Vì sao cùng database, cùng JVM vẫn không chia sẻ transaction?

Một số hiểu nhầm thường bắt nguồn từ việc test và server cùng khởi động trong một JVM:

1. **Transaction context thường gắn với thread:** Với mô hình transaction imperative của Spring, resource/connection và trạng thái transaction được liên kết bằng các cơ chế như `TransactionSynchronizationManager`. Không thể suy ra một thread khác tự tham gia transaction chỉ vì cùng application context.
2. **Một database có thể có nhiều connection:** T1 dùng một connection/trạng thái transaction, T2 dùng một connection khác. Commit/rollback xảy ra theo từng transaction, không theo “toàn bộ JVM”.
3. **HTTP không mang transaction manager của Spring:** JSON, cookie hoặc header thông thường không tự chuyển một database transaction T1 sang request phía server.
4. **Context propagation là vấn đề riêng:** Truyền correlation ID, MDC, trace ID hay authentication không đồng nghĩa truyền được database transaction; đừng dùng `TaskDecorator` để ngầm coi transaction của hai luồng là một.
5. **Test thread có thể không thấy dữ liệu uncommitted của server và ngược lại:** Điều này còn phụ thuộc transaction isolation, locking và database. Nếu test tạo fixture trong một transaction chưa commit rồi gọi HTTP server truy vấn fixture đó, server có thể **không nhìn thấy** fixture; thậm chí có thể block khi va chạm lock.

Ví dụ lỗi thiết kế:
- Test `@Transactional` dùng `repository.save(new Customer(...))` để chuẩn bị dữ liệu nhưng **chưa commit**.
- Test dùng `TestRestTemplate` gọi endpoint để xử lý customer vừa tạo.
- Server dùng connection khác và truy vấn không thấy customer, trả 404.
- Người viết test tưởng repository hoặc logic service sai, trong khi dữ liệu setup **chưa được commit và không nhìn thấy ở server thread**.

Cách sửa là tạo dữ liệu trước request trong một transaction **đã commit**, dùng `@BeforeTransaction`, `TransactionTemplate` chủ động commit, hoặc `TestTransaction.end()` với flag commit khi đó là điều test cần. Sau test phải cleanup bằng một transaction độc lập. Đừng chỉ tăng isolation hoặc thêm `flush()` để “làm dữ liệu hiện ra”: **flush không đồng nghĩa commit**, nên server connection vẫn có thể không thấy dữ liệu.

## 9. Propagation, rollback rules và những ngoại lệ của quy tắc đơn giản

Dù test và xử lý ứng dụng cùng thread, transaction propagation vẫn quyết định khả năng tham gia transaction đang tồn tại:

| Propagation trong service | Ý nghĩa giản lược | Khi test có T1 và gọi qua MockMvc đồng bộ |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện có, nếu không có thì tạo mới | Thường tham gia T1 |
| `REQUIRES_NEW` | Tạm ngưng transaction hiện có, mở transaction mới | Có thể commit độc lập dù T1 rollback |
| `SUPPORTS` | Dùng transaction nếu đang có, nếu không thì chạy không có transaction | Có thể chạy trong T1 |
| `NOT_SUPPORTED` | Chạy ngoài transaction hiện có | Không đảm bảo thay đổi nằm trong T1 |
| `MANDATORY` | Yêu cầu có transaction đang tồn tại | Có thể đạt với MockMvc/T1, nhưng fail với HTTP server nếu không có transaction server-side |
| `NESTED` | Dùng nested transaction/savepoint khi transaction manager hỗ trợ | Không phải transaction độc lập hoàn toàn; phụ thuộc manager và database |

**Với HTTP thật**, dù service có `REQUIRED`, nó không thể tham gia T1 từ test thread qua socket. Nó sẽ tham gia/tạo transaction theo tình trạng transaction **bên server**.

**Rollback rules cũng quan trọng.** Trong Spring transaction declarative thông thường, unchecked exceptions (`RuntimeException`, `Error`) mặc định dẫn đến rollback; checked exceptions có thể không gây rollback nếu không có `rollbackFor` hoặc cấu hình tương ứng. Chính sách có thể thay đổi theo version/cấu hình. Không nên coi bất kỳ HTTP 500 nào cũng chắc chắn đồng nghĩa “mọi thay đổi DB rollback”; hãy kiểm tra exception path, propagation và trạng thái DB.

Một trường hợp dễ nhầm: service bắt exception trong transaction rồi nuốt lỗi và vẫn trả thành công. Nếu transaction chưa bị đánh dấu rollback-only, interceptor có thể commit; nếu đã rollback-only, có thể phát sinh `UnexpectedRollbackException`. Bài test phải xác minh trạng thái dữ liệu sau cùng.

## 10. Tại sao @Transactional trên test có thể che bug transaction của service?

Khi `MockMvc` chạy đồng bộ trong T1, một service thiếu `@Transactional` **có thể vẫn nhìn thấy transaction active** vì transaction do test tạo sẵn. Kết quả:
- Test `repository.save` thành công.
- Cuối test dữ liệu rollback.
- Tác giả suy ra service đã được transactional và commit/rollback đúng ở production.

Kết luận đó **không được chứng minh**. Một test nhằm xác minh **transaction boundary của service** nên bắt đầu từ trạng thái không có transaction do test quản lý, gọi service qua Spring proxy và kiểm tra trạng thái sau commit/rollback bằng database thật hoặc công cụ đo transaction ở đúng ranh giới.

Ví dụ chẩn đoán (đoạn minh họa trong một test có imports tương ứng):

```java
boolean transactionActiveInCurrentThread =
        TransactionSynchronizationManager.isActualTransactionActive();
```

Câu lệnh chỉ phản ánh transaction của **thread đang chạy dòng code**. Nếu chạy trong test thread, `true` không chứng minh server HTTP thread có cùng transaction. Nếu chạy trong service, `true` chứng minh tại thời điểm đó có transaction active, nhưng **không chứng minh riêng phương thức đang xét đã mở nó** hoặc dữ liệu cuối cùng đã commit.

Ngoài ra, self-invocation trong mô hình Spring AOP proxy có thể bỏ qua advice: `this.innerTransactionalMethod()` không nhất thiết đi qua proxy nếu lời gọi nội bộ cùng bean. Test không thể chỉ nhìn annotation để suy ra interceptor chạy.

## 11. Các chiến lược isolation và cleanup đúng cho real HTTP integration test

Khi dùng `@SpringBootTest(RANDOM_PORT)`, nên mặc định coi dữ liệu được HTTP server **commit là dữ liệu cần dọn chủ động**. Một số cách hợp lý:

### 11.1. Tạo business key riêng và cleanup ngoài T1

Ví dụ mục 5 dùng `"real-" + UUID.randomUUID()` để xác định chính xác bản ghi của test, rồi `findByLabel(...).ifPresent(delete)` sau khi kết thúc T1. Cách này đơn giản, không xóa dữ liệu của test khác.

Ưu tiên cleanup trong `finally` hoặc callback được bảo đảm chạy sau test transaction, và xác minh nó sử dụng connection/transaction thực sự có thể commit. Cleanup cũng có thể thất bại; khi đó kết quả test nên phản ánh lỗi môi trường hoặc trạng thái rò dữ liệu.

### 11.2. Chuẩn bị fixture có commit trước request

Khi endpoint cần đọc dữ liệu đã tồn tại:
- Dùng setup không nằm trong test-managed transaction, rồi để repository save commit theo cấu hình thực tế.
- Hoặc dùng `TransactionTemplate` có transaction manager phù hợp để tạo fixture và commit trước khi gọi HTTP.
- Hoặc điều khiển `TestTransaction` cẩn thận: kết thúc transaction với commit, sau đó mới gửi HTTP; đừng gọi `TestTransaction.end()` khi không active.

Sau khi request hoàn thành, cleanup những dữ liệu đã commit trong một transaction riêng. Không coi `saveAndFlush()` là “đã commit” khi test T1 vẫn active.

### 11.3. @Sql và cleanup script

`@Sql` có thể dùng để tạo/reset dữ liệu. Tuy nhiên với transactional test, script chạy theo transaction mode mặc định có thể tham gia T1 và rollback cùng T1, **không xóa được dữ liệu server đã commit**. Nếu cần cleanup ngoài T1, phải xem cấu hình `@SqlConfig(transactionMode = ISOLATED)` và thời điểm thực thi, hoặc dùng cơ chế tường minh sau transaction. Chỉ chạy `TRUNCATE`/xóa toàn bộ bảng khi môi trường test cô lập đủ và không có test song song đang sử dụng bảng đó.

### 11.4. Database/container riêng cho suite

Testcontainers có thể cung cấp PostgreSQL hoặc database khác với lifecycle thích hợp. Có thể:
- Tạo schema/database riêng cho một nhóm test hoặc mỗi test class.
- Reset schema bằng migration/fixture có kiểm soát giữa các test.
- Đảm bảo data cleanup không phụ thuộc vào thứ tự test hoặc việc context cache bị tái sử dụng.

Không dùng database production cho một bài test có quyền ghi/xóa. Với H2 in-memory như ví dụ, có thể giữ URL riêng giữa hai test classes để tránh cùng ứng dụng tạo/hủy schema của context khác; khi chạy tests song song, vẫn cần kiểm soát isolation cụ thể.

### 11.5. Eventual consistency và xử lý bất đồng bộ

Nếu HTTP request trả về trước khi xử lý message/event hoàn tất, **không nên lập tức assert DB đã commit** rồi kết luận test flaky. Hãy xác định hợp đồng API:
- Nếu API đồng bộ cam kết đã ghi xong khi trả 201, có thể assert trạng thái ngay.
- Nếu API trả 202 Accepted và xử lý nền, dùng cơ chế polling có timeout rõ ràng hoặc thông báo sự kiện/điều kiện đồng bộ xác định.
- Chỉ dọn dữ liệu khi hoạt động nền thực sự kết thúc hoặc có cơ chế hủy an toàn; không dùng `Thread.sleep` cố định thay cho đồng bộ đúng.

## 12. Nguy cơ khác khi test thread và HTTP server thread tách nhau

Sự khác biệt về thread không chỉ ảnh hưởng transaction:

- **SecurityContext:** Authentication được thiết lập trong test thread bằng cơ chế thread-local (ví dụ trong một unit/method-security test) không tự trở thành authentication của HTTP request thật. Với `RANDOM_PORT`, hãy truyền token/cookie/header cần thiết qua HTTP client rồi để security filter chain xác thực như production.
- **RequestContext và MDC:** Thread-local request attributes, logging MDC hoặc một số thông tin tracing không tự truyền sang server thread nếu không có cơ chế tương ứng. Một correlation ID được gửi qua header có thể giúp theo dõi, nhưng không chia sẻ database transaction.
- **Hibernate persistence context:** Entity đang managed trong T1 không tự managed trong T2. Nên truyền ID/DTO qua HTTP và để server repository load entity từ database.
- **Isolation và locking:** Test giữ lock trong T1 khi gửi request sang server có thể khiến server block, timeout hoặc deadlock. Cần commit fixture trước khi gọi HTTP để tránh lock không cần thiết.
- **Preemptive test timeouts:** Các công cụ timeout chạy code test trong thread khác có thể làm test-managed transaction của Spring không được bind vào thread thực thi câu lệnh; thay đổi đó có thể khiến dữ liệu được commit ngoài ý định. Tránh dùng preemptive timeout cho code dựa vào test-managed rollback mà không hiểu cơ chế thread.

Những điểm này càng cho thấy vì sao **“cùng JVM” không có nghĩa “cùng context thực thi”**.

## 13. Cách đọc báo cáo lỗi và kiểm tra test có thật sự chạy

Với real HTTP integration test, có hai lớp lỗi khác nhau:
1. **HTTP/request path:** response status sai, controller không nhận request, security chặn, timeout hoặc server-side exception.
2. **Database/transaction path:** transaction chưa commit, rollback ngoài dự kiến, lỗi constraint, isolation, lock hoặc dữ liệu cleanup chưa đúng.

Nếu `assertEquals(1, countByLabel(...))` sau khi T1 rollback bị fail, hãy kiểm tra theo thứ tự:
- Test dùng `RANDOM_PORT` thật hay `MOCK`/MockMvc?
- Service có transaction boundary đúng và được gọi qua Spring proxy hay không?
- Response HTTP có phải 201 và body hợp lệ không?
- Có cùng datasource/schema giữa server và test repository không?
- Transaction T1 đã **thực sự kết thúc** trước câu truy vấn readback chưa?
- Có async worker hoặc event listener làm commit sau response không?
- Có dọn dữ liệu trước khi assert hoặc khác biệt isolation giữa các connection không?

Để chạy lớp test ở mục 5, trong Gradle wrapper (Linux/macOS):

```bash
./gradlew test --tests "com.example.txhttp.RealHttpTransactionTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.txhttp.RealHttpTransactionTest"
```

Để chạy lớp `MockMvc`, thay tên bằng `com.example.txhttp.MockMvcTransactionTest`.

Với Maven wrapper (Linux/macOS):

```bash
./mvnw -Dtest=RealHttpTransactionTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=RealHttpTransactionTest test
```

Có thể chạy tương tự cho `MockMvcTransactionTest`. Các lệnh yêu cầu Java 17+, dependencies và plugin JUnit Jupiter phù hợp; bài này không chứa output `System.out.println`, nên không có một stdout cố định. Báo cáo Gradle `build/reports/tests/test/index.html` hoặc Maven Surefire `target/surefire-reports/` của **đúng module/lần chạy** mới xác nhận kết quả.

## 14. Các sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách khắc phục |
|---|---|---|
| `@SpringBootTest(RANDOM_PORT)` + `@Transactional` test và tin HTTP POST sẽ rollback | Server request chạy trong thread khác và có transaction riêng | Dọn dữ liệu đã commit hoặc dùng database cô lập |
| Cho rằng tất cả `@SpringBootTest` đều mở HTTP server | `MOCK` không mở listener thật | Chọn và kiểm tra `webEnvironment` |
| `MockMvc` luôn giống real HTTP về transaction | Dispatch đồng bộ thường chạy trong test thread | Phân biệt đường gọi và các trường hợp async/REQUIRES_NEW |
| `@Rollback(true)` trên test được xem là lệnh rollback server | Annotation chỉ điều khiển test-managed transaction | Xác minh dữ liệu sau request và cleanup ngoài T1 |
| `saveAndFlush()` rồi gọi HTTP nghĩ fixture đã commit | Flush chưa phải commit | Commit dữ liệu setup trước HTTP request |
| `@AfterEach` xóa DB trong khi T1 active | Cleanup có thể bị rollback theo test | Cleanup sau T1, `@AfterTransaction` hoặc cơ chế isolated |
| `verify(repository.save(...))` thay cho kiểm tra DB thật | Mock không chứng minh commit/rollback | Integration test với repository và database thật |
| Dựa vào ID được cấp để khẳng định commit | JPA/IDENTITY có thể cấp ID trước commit | Đọc lại sau transaction boundary phù hợp |
| Test `@Transactional` luôn xanh dù service thiếu annotation | Test T1 có thể cấp transaction sẵn cho service | Test service transaction boundary ngoài test-managed T1 |
| Không cleanup record HTTP đã commit | Test khác nhìn thấy dữ liệu cũ, suite flaky | Dùng unique key và xóa có commit |
| Test HTTP bị block vì fixture trong T1 giữ lock | Server dùng connection khác | Chuẩn bị và commit fixture trước request |
| HTTP 201 được coi là mọi background task đã commit | Xử lý async có thể tiếp tục sau response | Theo hợp đồng sync/async, đợi điều kiện hoàn thành có giới hạn |
| Dùng `System.setProperty` hoặc dữ liệu dùng chung giữa test song song | Nhiễm trạng thái JVM và database | Dùng profile/dynamic property và resource isolation phù hợp |

## 15. Checklist khi review một bài @SpringBootTest có ghi dữ liệu

- [ ] Đã xác định chính xác `webEnvironment`: `RANDOM_PORT`, `DEFINED_PORT`, `MOCK` hay `NONE`.
- [ ] Đã biết request chạy **qua HTTP socket** hay qua `MockMvc`/in-process dispatcher.
- [ ] Đã phân biệt **test-managed transaction T1** và transaction được ứng dụng/server tạo ở luồng khác.
- [ ] Không dùng `@Rollback`, `@Commit` hoặc `@Transactional` của test để hứa sẽ rollback dữ liệu HTTP server đã commit.
- [ ] Đã xác nhận service được gọi qua Spring proxy và cấu hình transaction manager/propagation đúng.
- [ ] Với API phụ thuộc fixture, dữ liệu được chuẩn bị **đã commit** trước khi server đọc.
- [ ] Đã kiểm chứng dữ liệu **sau transaction boundary**, không chỉ sau `save` hoặc `flush`.
- [ ] Đã thiết kế cleanup độc lập cho dữ liệu do HTTP server commit: unique key, finally, transaction riêng hoặc reset DB.
- [ ] Đã cân nhắc `REQUIRES_NEW`, async thread, event listener, timeout và test framework callbacks.
- [ ] Test về rollback thật dùng database thích hợp và xác minh trạng thái sau lỗi.
- [ ] Không nhầm transaction active ở test thread với transaction ở HTTP server thread.
- [ ] Đã chạy đúng lớp test/CI job và xem report thực tế trước khi kết luận PASS.

**Kết luận:** Khi `@SpringBootTest` khởi động HTTP server thật, **request được xử lý trong ngữ cảnh khác với test method**. Transaction do `@Transactional` trên test tạo ra **không tự truyền sang server**, nên rollback của test không xóa các bản ghi mà transaction phía server đã commit. Với `MockMvc` đồng bộ, lời gọi thường cùng test thread và có thể tham gia test transaction nếu propagation phù hợp, nhưng không được tổng quát hóa cho mọi trường hợp. Muốn test tin cậy, hãy xác định rõ **thread, proxy, propagation và thời điểm commit**, chuẩn bị fixture đã commit trước request và chủ động cleanup dữ liệu phát sinh từ HTTP thật.