# Tránh phụ thuộc thứ tự và dữ liệu còn lại từ test trước

Trong **Spring Boot testing**, một test có thể xanh khi chạy cả suite nhưng đỏ khi chạy riêng, hoặc xanh khi chạy riêng nhưng fail khi đổi thứ tự, chạy parallel hay chạy lại trên CI. Nguyên nhân thường gặp là **test ngầm dựa vào dữ liệu do test khác tạo**, test trước **commit mà không dọn**, fixture được **seed chỉ một lần ở startup**, hoặc các test dùng chung **cache, static fields, Spring singleton, message queue**. Đó là lỗi về quản lý dữ liệu kiểm thử, không phải giải pháp bằng cách tăng timeout hay ép @TestMethodOrder.

Nguyên tắc của bài là **mỗi test tự xác lập tiền điều kiện, chạy hành động, assert kết quả và quản lý mọi thay đổi nó sở hữu**. Rollback là một lựa chọn rất tốt với repository tests, nhưng **không tự rollback những transaction đã commit qua HTTP, REQUIRES_NEW, @Commit, thread khác hoặc external systems**.

Bài học áp dụng Java 17, Spring Boot 3.4.5, JUnit Jupiter, Spring Data JPA, H2 và Spring TestContext. Có ví dụ runnable hoàn chỉnh về **@DataJpaTest rollback**, **@Sql fixtures theo từng method**, **HTTP RANDOM_PORT test với cleanup**, **REQUIRES_NEW transaction vượt ra ngoài rollback**, và **@Commit/@AfterTransaction**. Phần cuối đề cập parallelism, context caching, Testcontainers và cách chứng minh test chạy riêng hoặc đảo thứ tự vẫn đúng. Những kết quả nêu là **kỳ vọng từ mã**, không phải log một lần chạy Gradle đã thực hiện.

## 1. Bất biến của một test độc lập

Một test đáng tin cần giữ các điều kiện:

- **Tự đủ dữ liệu đầu vào:** không đợi test A chạy trước để tạo user/order/ticket cho test B.
- **Không phụ thuộc dữ liệu tồn dư:** nếu có fixture tồn tại từ lần chạy trước, test phải chủ động nhận diện, preclean hoặc dùng database/test namespace riêng.
- **Không phụ thuộc generated ID:** sequence/identity trong nhiều database không nhất thiết rollback về giá trị cũ.
- **Không phụ thuộc thứ tự execution:** chạy riêng, chạy class, chạy suite với thứ tự khác không đổi outcome.
- **Có quy tắc cleanup rõ:** rollback những thao tác nằm trong test-managed transaction; xóa chủ động những thao tác đã commit ngoài transaction ấy.
- **Không xóa dữ liệu không thuộc test:** cleanup theo tenant, externalKey, testRunId hoặc disposable database, không DELETE toàn bảng shared.
- **Độc lập về state ngoài DB:** cache, file, queue, static variables, HTTP session, mock behavior cũng cần scope/reset.

~~~text
Arrange: xác lập baseline và tạo fixture riêng
   |
   v
Act:     gọi repository/service/HTTP endpoint
   |
   v
Assert:  kiểm tra response và state mong đợi
   |
   v
Cleanup: rollback hoặc delete đúng dữ liệu test sở hữu
   |
   v
Invariant sau test: không để lại state ảnh hưởng test khác
~~~

**Test riêng lẻ không cần hoàn nguyên toàn bộ database về trắng.** Nó chỉ cần khôi phục **phần state nó sở hữu** và tôn trọng baseline dùng chung. Trong multi-tenant system, cleanup trên toàn bộ table có thể nguy hiểm hơn không cleanup vì xóa fixture của test khác.

## 2. Phản ví dụ: test thứ hai chỉ đúng nếu test đầu tiên đã chạy

Mẫu **sai có chủ ý**:

~~~java
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class FragileTicketTests {
    static Long ticketId;

    @Test
    @Order(1)
    void createTicket() {
        ticketId = service.create("A", "shared", "title");
    }

    @Test
    @Order(2)
    void readTicketCreatedEarlier() {
        assertTrue(repository.existsById(ticketId));
    }
}
~~~

Đây là **trích đoạn không độc lập**, chưa khai báo đầy đủ service/repository/imports. Nó có nhiều lỗi thiết kế: phụ thuộc @Order, giữ ID qua static field, tin rằng dữ liệu vẫn sống qua test transaction, và fail khi chạy riêng method read. Nếu create chạy trong @DataJpaTest rollback, method read có thể nhận một ID **không còn row trong DB**.

**Cách sửa:** mỗi test tự seed một Ticket cần thiết bằng repository hoặc @Sql. Test tạo Ticket tự assert Ticket vừa tạo. Test đọc Ticket tự tạo Ticket để đọc. Không dùng test results làm fixtures cho nhau.

JUnit Jupiter có khả năng cấu hình MethodOrderer.Random để **phát hiện** một số phụ thuộc thứ tự, nhưng randomize một lần không chứng minh test độc lập. Giải pháp bền vững vẫn là fixture và cleanup đúng vòng đời.

### Bốn phép thử mà một test tốt nên vượt qua

**1.** Chạy một mình bằng Gradle --tests.

**2.** Chạy cùng các test khác, không yêu cầu thứ tự.

**3.** Chạy lại trên cùng test environment được quản lý.

**4.** Nếu suite bật parallelism, không đụng shared key, broad cleanup hoặc state không đồng bộ.

Một test chạy xanh một lần theo một thứ tự cố định không đủ chứng minh bốn điều đó.

## 3. Phân loại dữ liệu: rollback xử lý được đến đâu?

| Dữ liệu hoặc side effect | Vòng đời | Rollback của test @Transactional |
| --- | --- | --- |
| JPA/JDBC DML trong test-managed transaction | Một test method | **Thường rollback được** |
| @Sql script tham gia test transaction | Một method | **Rollback được** |
| @Commit hoặc @Rollback(false) | Row được commit | **Không dọn được bằng rollback** |
| Spring service REQUIRES_NEW | Transaction độc lập đã commit | **Không rollback cùng transaction ngoài** |
| HTTP POST qua real server | Servlet thread và service transaction khác | **Không tự rollback** |
| @Async hoặc executor thread mới | Transaction/thread khác | **Không tự rollback** |
| data.sql ở ApplicationContext startup | Baseline ngoài test transaction | **Không tự xóa** |
| Static Map, singleton Spring bean | Sống trong JVM/context | **Không** |
| Redis, Kafka, filesystem, external API | Ngoài RDBMS transaction | **Không** |
| Testcontainers container reused | Container có DB sống qua nhiều tests | **Không tự reset từng method** |

**@SpringBootTest không tự làm test transactional.** Với @SpringBootTest, muốn test-managed rollback cần thêm **@Transactional** trên test. Ngược lại, **@DataJpaTest** thường transactional và rollback theo mặc định. Cả hai chỉ áp dụng cho transaction thực sự nằm trong Spring TestContext test thread.

### Flush không phải commit

Trong JPA, repository.save(...) có thể chỉ tạo managed entity; một số SQL hoặc constraint errors xuất hiện khi flush. **saveAndFlush** giúp ép SQL đến database trong transaction test, nhưng **vẫn không commit**. Sau test mặc định rollback, row biến mất; việc count=1 trong cùng transaction không chứng minh client/connection khác đã đọc được committed data.

## 4. Test data fixture phải tự chủ và đủ phân biệt

Một fixture tốt có cả positive và negative cases. Ví dụ muốn test repository tìm ticket theo tenant + external key, cần ít nhất:

| Tenant | External key | Title | Dùng để |
| --- | --- | --- | --- |
| A | ticket-01 | first | Truy vấn khớp |
| A | ticket-02 | second | Đảm bảo không nhầm key |
| B | ticket-01 | another tenant | Đảm bảo không lộ cross-tenant |
| A | archived-01 | archived | Kiểm tra status/filter nếu có |

Không chỉ assert “count có dữ liệu”: một query quên tenant có thể cho đúng số lượng một cách tình cờ. **Test nên assert exact key/tenant và trạng thái của row, không chỉ tổng số trong database**.

Có ba chiến lược chính:

**Fixture tại method:** tự tạo entity trong @Test hoặc @BeforeEach, rollback cùng test nếu chạy trong transaction. Ưu điểm: dễ nhìn, ít phụ thuộc global setup.

**@Sql trước mỗi method:** script insert baseline được khai báo rõ và tham gia test transaction nếu cấu hình mặc định phù hợp. Phù hợp dataset SQL cố định, cần tránh seed trùng qua ISOLATED mode.

**Committed setup/cleanup:** khi HTTP, @Commit hoặc REQUIRES_NEW đã commit, dùng tenant/test-key riêng, preclean cho residue và postclean ngoài transaction hoặc database disposable.

Không dùng **@BeforeAll** insert một lần rồi cho nhiều tests cùng sửa cùng row; nó biến baseline thành shared mutable state và thường không thuộc test transaction của từng method.

## 5. Dự án runnable: Java 17, Boot 3.4.5, JPA, H2, HTTP

Dự án chứa entity **Ticket** có cặp business key **(tenantId, externalKey)** duy nhất. TicketService tạo row thông qua Spring-managed transaction. Một HTTP controller cung cấp POST /api/tickets để chứng minh server thread commit. IndependentTicketWriter dùng REQUIRES_NEW để chứng minh committed row không biến mất do outer test rollback.

**Mục tiêu:**
1. Repository tests dùng @DataJpaTest để rollback.
2. @Sql tạo baseline cho từng method rồi cũng rollback.
3. HTTP tests có unique key theo test method và pre/post cleanup.
4. Transactional test gọi REQUIRES_NEW cần @AfterTransaction cleanup.
5. @Commit test phải assert row còn sau commit rồi cleanup.
6. Mỗi test có thể chạy riêng, không phải lấy ID từ một test khác.

### 5.1. Cấu trúc tệp

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/testdata/TestDataApplication.java
src/main/java/com/example/testdata/Ticket.java
src/main/java/com/example/testdata/TicketRepository.java
src/main/java/com/example/testdata/TicketService.java
src/main/java/com/example/testdata/TicketController.java
src/main/java/com/example/testdata/IndependentTicketWriter.java
src/test/resources/sql/seed-ticket.sql
src/test/java/com/example/testdata/RollbackIsolationTest.java
src/test/java/com/example/testdata/SqlSeedIsolationTest.java
src/test/java/com/example/testdata/HttpCommitIsolationTest.java
src/test/java/com/example/testdata/RequiresNewIsolationTest.java
src/test/java/com/example/testdata/CommitCleanupTest.java
~~~

### 5.2. Gradle và application.yml

**settings.gradle**

~~~groovy
rootProject.name = 'spring-test-data-isolation'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/resources/application.yml**

~~~yaml
spring:
  datasource:
    generate-unique-name: true
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
~~~

**generate-unique-name=true** giảm nguy cơ ApplicationContexts khác nhau dùng trùng H2 in-memory database name. Tuy nhiên nó không tạo một database mới cho **mỗi method** trong cùng context. Vì Spring TestContext cache context, data đã commit vẫn có thể còn giữa các methods/classes. **ddl-auto=create-drop** chỉ phù hợp demo/test database, không dùng trong production.

**spring-boot-starter-web** cho real HTTP server; **spring-boot-starter-data-jpa** cho Hibernate/repository; **spring-boot-starter-test** cho JUnit/Spring TestContext. H2 chạy nhúng, nhưng database vẫn có schema, transactions và unique constraints thật.

### 5.3. Application class

**src/main/java/com/example/testdata/TestDataApplication.java**

~~~java
package com.example.testdata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestDataApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestDataApplication.class, args);
    }
}
~~~

### 5.4. Entity Ticket

**src/main/java/com/example/testdata/Ticket.java**

~~~java
package com.example.testdata;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "tickets",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_ticket_tenant_key",
        columnNames = {"tenant_id", "external_key"}))
public class Ticket {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 40)
    private String tenantId;

    @Column(name = "external_key", nullable = false, length = 100)
    private String externalKey;

    @Column(nullable = false, length = 200)
    private String title;

    protected Ticket() {
        // Required by JPA.
    }

    public Ticket(String tenantId, String externalKey, String title) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.externalKey = Objects.requireNonNull(externalKey);
        this.title = Objects.requireNonNull(title);
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getExternalKey() {
        return externalKey;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = Objects.requireNonNull(newTitle);
    }
}
~~~

Cặp tenant_id + external_key có unique constraint. Một test bỏ sót cleanup và insert cùng cặp lần nữa sẽ báo lỗi, nhờ đó vấn đề isolation dễ phát hiện. **Không thay unique constraint bằng cách vô hiệu hóa kiểm tra DB chỉ để test xanh**.

**Generated ID không phải fixture key đáng tin:** sequence/identity có thể tăng qua rollback. Dùng externalKey cố định theo từng method hoặc key ngẫu nhiên có lưu/log, chứ không assert ID phải bắt đầu bằng 1.

### 5.5. Repository

**src/main/java/com/example/testdata/TicketRepository.java**

~~~java
package com.example.testdata;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TicketRepository extends JpaRepository<Ticket, Long> {
    long countByTenantIdAndExternalKey(
            String tenantId, String externalKey);

    Optional<Ticket> findByTenantIdAndExternalKey(
            String tenantId, String externalKey);
}
~~~

Repository cho phép test xác nhận row bằng **tenant + test key**, không phụ thuộc generated ID hoặc data cũ. Với multi-tenant, mọi assertion/cleanup phải có đủ tenant condition.

### 5.6. Service tạo Ticket

**src/main/java/com/example/testdata/TicketService.java**

~~~java
package com.example.testdata;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TicketService {
    private final TicketRepository repository;

    public TicketService(TicketRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long create(String tenant, String key, String title) {
        Ticket saved = repository.saveAndFlush(
                new Ticket(tenant, key, title));
        return saved.getId();
    }
}
~~~

Khi được gọi trực tiếp từ một @Transactional JUnit test, service propagation mặc định **REQUIRED** sẽ thường tham gia test transaction và rollback cùng test. Khi gọi qua HTTP server thread, service có transaction riêng và commit khi hoàn thành; JUnit client thread không sở hữu transaction ấy.

### 5.7. HTTP Controller

**src/main/java/com/example/testdata/TicketController.java**

~~~java
package com.example.testdata;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tickets")
public class TicketController {
    private final TicketService service;

    public TicketController(TicketService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Created> create(@RequestBody Create request) {
        long id = service.create(
                request.tenantId(),
                request.externalKey(),
                request.title());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new Created(id));
    }

    public record Create(
            String tenantId, String externalKey, String title) {
    }

    public record Created(long id) {
    }
}
~~~

HTTP controller là minh họa cho **transport + transaction boundary**, không có production authorization/validation. Khi demo dùng HTTP POST thực, transaction của service hoàn thành trước khi response 201 được trả thành công trong trường hợp không có async work.

### 5.8. IndependentTicketWriter dùng REQUIRES_NEW

**src/main/java/com/example/testdata/IndependentTicketWriter.java**

~~~java
package com.example.testdata;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentTicketWriter {
    private final TicketRepository repository;

    public IndependentTicketWriter(TicketRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(String tenant, String key) {
        repository.saveAndFlush(
                new Ticket(tenant, key, "independent commit"));
    }
}
~~~

REQUIRES_NEW **suspend transaction ngoài** rồi mở transaction mới khi lời gọi qua Spring AOP proxy. Nếu service method thành công và commit, rollback transaction ngoài không undo row. **Không** tự gọi this.write(...) trong cùng bean để kiểm tra propagation, vì self-invocation có thể bỏ qua proxy.

## 6. Test A — rollback theo từng @DataJpaTest method

**src/test/java/com/example/testdata/RollbackIsolationTest.java**

~~~java
package com.example.testdata;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class RollbackIsolationTest {

    @Autowired
    private TicketRepository repository;

    @Test
    void createsOwnFixtureAndRunsIndependently() {
        String tenant = "ROLLBACK";
        String key = "rollback-first";

        assertEquals(0L,
                repository.countByTenantIdAndExternalKey(tenant, key));

        repository.saveAndFlush(
                new Ticket(tenant, key, "first test"));

        assertEquals(1L,
                repository.countByTenantIdAndExternalKey(tenant, key));
    }

    @Test
    void usesAnotherFixtureWithoutReadingFirstTest() {
        String tenant = "ROLLBACK";
        String key = "rollback-second";

        assertEquals(0L,
                repository.countByTenantIdAndExternalKey(tenant, key));

        Ticket ticket = repository.saveAndFlush(
                new Ticket(tenant, key, "second test"));

        assertTrue(ticket.getId() > 0);
        assertEquals(1L,
                repository.countByTenantIdAndExternalKey(tenant, key));
    }
}
~~~

**Mỗi method tự tạo dữ liệu**. @DataJpaTest mặc định transactional và rollback khi method kết thúc. Hai methods có keys khác nhau, không truyền ID qua static field và không áp đặt @TestMethodOrder. Chạy method thứ hai một mình vẫn có đầy đủ dữ liệu nó cần.

**saveAndFlush** gửi SQL vào database trong test transaction để bắt lỗi mapping/constraints. Count=1 là kết quả trong transaction, không phải chứng minh row đã commit. Identity ID chỉ được kiểm tra **lớn hơn 0**, không đoán chính xác 1 hay 2.

## 7. Test B — @Sql tự tạo baseline trước từng method

Một fixture SQL cố định có thể được seed **trước mỗi method**, miễn script tham gia test-managed transaction và cuối method rollback.

**src/test/resources/sql/seed-ticket.sql**

~~~sql
INSERT INTO tickets (tenant_id, external_key, title)
VALUES ('SEED', 'seed-key', 'Original');
~~~

**src/test/java/com/example/testdata/SqlSeedIsolationTest.java**

~~~java
package com.example.testdata;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.jdbc.Sql;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest
@Sql(
    scripts = "/sql/seed-ticket.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Execution(ExecutionMode.SAME_THREAD)
class SqlSeedIsolationTest {

    @Autowired
    private TicketRepository repository;

    @Test
    void fixtureHasOriginalValueEveryTime() {
        Ticket ticket = repository
                .findByTenantIdAndExternalKey("SEED", "seed-key")
                .orElseThrow();

        assertEquals("Original", ticket.getTitle());
        assertEquals(1L,
                repository.countByTenantIdAndExternalKey(
                        "SEED", "seed-key"));
    }

    @Test
    void modificationStaysInsideThisMethodTransaction() {
        Ticket ticket = repository
                .findByTenantIdAndExternalKey("SEED", "seed-key")
                .orElseThrow();

        ticket.rename("Changed only here");
        repository.flush();

        assertEquals("Changed only here",
                repository.findByTenantIdAndExternalKey(
                        "SEED", "seed-key")
                        .orElseThrow().getTitle());
    }
}
~~~

Spring TestContext chạy @Sql BEFORE_TEST_METHOD trong test transaction theo **default transaction handling** khi @DataJpaTest đã mở transaction. Script tạo một row trước mỗi method; khi method kết thúc, toàn bộ INSERT/UPDATE được rollback. Do đó **fixtureHasOriginalValueEveryTime** không cần chạy trước hoặc sau method modification.

**@Execution(SAME_THREAD)** bảo đảm các methods cùng class không chạy song song trên cùng fixed seed-key ngay cả khi Jupiter parallel mode được cấu hình; tuy vậy class khác dùng chung seed-key vẫn có thể gây xung đột nếu chạy parallel và chia sẻ DB. Nếu cần parallel toàn suite, dùng namespace/database riêng thay vì cố chia một key cố định.

### @SqlConfig(transactionMode=ISOLATED) là một ý khác

Nếu seed script chạy trong một **ISOLATED transaction**, nó sẽ được commit độc lập. Rollback của @DataJpaTest **không xóa row do script đã commit**. Khi đó lần chạy sau có thể gặp unique constraint do seed trùng. Vì vậy không chuyển transactionMode sang ISOLATED trừ khi cần committed baseline và có cleanup rõ.

Tương tự, **data.sql** thường được chạy lúc application context initialization, không tự chạy lại cho mỗi test method. Khi test mutate baseline đã committed, cần rollback hoặc reset/seed lại per method. Đừng giả định context cache sẽ reset database giữa hai methods.

## 8. Test C — real HTTP request commit, nên cleanup ngoài test transaction

**@SpringBootTest(webEnvironment = RANDOM_PORT)** mở embedded HTTP server thật. Một POST tới server xử lý trên servlet thread, vì vậy data được service @Transactional commit độc lập với thread của HTTP client/JUnit test.

Cách an toàn trong demo là **không gắn @Transactional lên HTTP test**, dùng **@BeforeEach preclean** và **@AfterEach cleanup** với JdbcTemplate. Mỗi method có key dựa trên tên method, nên không cần test khác chuẩn bị dữ liệu.

**src/test/java/com/example/testdata/HttpCommitIsolationTest.java**

~~~java
package com.example.testdata;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class HttpCommitIsolationTest {
    private static final String TENANT = "HTTP";

    @LocalServerPort
    private int port;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private ObjectMapper mapper;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private String key;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                Long.class, TENANT, key);
    }

    private void clean() {
        jdbc.update(
                "DELETE FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                TENANT, key);
    }

    @BeforeEach
    void prepare(TestInfo info) {
        key = "http-" + info.getTestMethod()
                .orElseThrow().getName();
        clean(); // Idempotent pre-clean after a previous crash.
        assertEquals(0L, count());
    }

    @AfterEach
    void tearDown() {
        clean(); // Runs without test-managed @Transactional.
        assertEquals(0L, count());
    }

    private void postAndVerify() throws Exception {
        String body = mapper.writeValueAsString(Map.of(
                "tenantId", TENANT,
                "externalKey", key,
                "title", "created via HTTP"));

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:"
                        + port + "/api/tickets"))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = http.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(201, response.statusCode());
        assertTrue(mapper.readTree(response.body())
                .path("id").asLong() > 0);
        assertEquals(1L, count());
    }

    @Test
    void firstPostOwnsItsKey() throws Exception {
        postAndVerify();
    }

    @Test
    void secondPostOwnsItsKey() throws Exception {
        postAndVerify();
    }
}
~~~

**Bằng chứng được bảo vệ:**

- **@LocalServerPort** lấy port thật của RANDOM_PORT server; không dựa vào 8080.
- @BeforeEach chọn key riêng theo tên method và xóa residue cũ theo đúng TENANT/key.
- HTTP POST trả 201 và JSON id>0, sau đó JdbcTemplate nhìn thấy row mà server service đã commit.
- @AfterEach xóa đúng row đã commit và assert không còn.
- Hai methods độc lập, có thể chạy riêng hoặc đổi thứ tự.

Nếu một request fail assertion sau khi server đã commit, @AfterEach vẫn chạy trong JUnit lifecycle bình thường để cleanup. Nếu JVM bị kill trước teardown, preclean lần chạy sau hoặc database ephemeral mới giải quyết residue.

**Không đặt @Transactional trên class này rồi nghĩ @AfterEach DELETE sẽ commit.** Khi test có outer test transaction, @AfterEach có thể chạy trong transaction ấy và DELETE bị rollback, trong khi server POST đã commit. Phân biệt transaction của HTTP server thread với transaction JUnit client thread.

## 9. Test D — REQUIRES_NEW commit không bị outer test rollback dọn

Service **IndependentTicketWriter** đã dùng Propagation.REQUIRES_NEW. Trong test bên dưới, outer test-managed transaction được rollback mặc định, nhưng inner service transaction commit độc lập. Để quan sát và dọn đúng trạng thái, sử dụng **@BeforeTransaction và @AfterTransaction**, đều chạy ngoài outer transaction.

**src/test/java/com/example/testdata/RequiresNewIsolationTest.java**

~~~java
package com.example.testdata;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class RequiresNewIsolationTest {
    private static final String TENANT = "INNER";
    private static final String KEY = "requires-new-fixture";

    @Autowired
    private IndependentTicketWriter writer;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                Long.class, TENANT, KEY);
    }

    private void clean() {
        jdbc.update(
                "DELETE FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                TENANT, KEY);
    }

    @BeforeTransaction
    void clearCommittedResidue() {
        clean();
        assertEquals(0L, count());
    }

    @Test
    void innerCommitSurvivesOuterRollback() {
        assertTrue(TestTransaction.isActive());
        writer.write(TENANT, KEY);
        // No assertion relying on outer transaction visibility.
    }

    @AfterTransaction
    void assertInnerCommitThenClean() {
        try {
            assertEquals(1L, count());
        } finally {
            clean();
        }
        assertEquals(0L, count());
    }
}
~~~

**Thứ tự transaction:**

~~~text
@BeforeTransaction: cleanup, count=0
BEGIN outer test transaction
    @Test invokes writer bean via Spring proxy
       suspend outer transaction
       BEGIN REQUIRES_NEW
       INSERT Ticket
       COMMIT inner transaction
       resume outer transaction
ROLLBACK outer test transaction
@AfterTransaction:
    row vẫn có vì inner commit
    cleanup ngoài transaction, count=0
~~~

Không cleanup committed inner row bằng @AfterEach của transactional test: @AfterEach vẫn thường chạy **trong outer test transaction**, nên DELETE có thể rollback. Ngoài ra, nếu test gọi private/self-invoked REQUIRES_NEW method mà không đi qua Spring AOP proxy, semantics có thể khác; ví dụ dùng @Autowired bean để bảo vệ đường gọi chuẩn.

**Chú ý connection pool:** REQUIRES_NEW có thể yêu cầu connection thứ hai khi outer transaction giữ connection. Test này dùng H2/Hikari từ Spring Boot; trong production nhiều concurrent transactions cần sizing pool phù hợp. Không sử dụng REQUIRES_NEW chỉ để test bỏ qua rollback; chọn propagation theo nghiệp vụ thật.

## 10. Test E — @Commit để kiểm chứng dữ liệu thật sự còn sau test

Rollback là mặc định phù hợp phần lớn repository tests. Đôi khi bạn cần **commit có chủ đích**, ví dụ kiểm tra @TransactionalEventListener(AFTER_COMMIT), transaction synchronization hoặc data visibility. Khi dùng **@Commit** hay **@Rollback(false)**, phải cleanup bên ngoài test transaction.

**src/test/java/com/example/testdata/CommitCleanupTest.java**

~~~java
package com.example.testdata;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Transactional
class CommitCleanupTest {
    private static final String TENANT = "COMMIT";
    private static final String KEY = "commit-fixture";

    @Autowired
    private TicketRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                Long.class, TENANT, KEY);
    }

    private void clean() {
        jdbc.update(
                "DELETE FROM tickets "
                    + "WHERE tenant_id=? AND external_key=?",
                TENANT, KEY);
    }

    @BeforeTransaction
    void baseline() {
        clean();
        assertEquals(0L, count());
    }

    @Test
    @Commit
    void commitNeedsExplicitCleanup() {
        repository.saveAndFlush(
                new Ticket(TENANT, KEY, "committed fixture"));
        assertEquals(1L, count());
    }

    @AfterTransaction
    void verifyCommittedRowThenDelete() {
        try {
            assertEquals(1L, count());
        } finally {
            clean();
        }
        assertEquals(0L, count());
    }
}
~~~

**@Commit tương đương @Rollback(false)** về ý định kết thúc **test-managed transaction**, không tự tạo transaction nếu thiếu @Transactional. Trong test này @SpringBootTest và @Transactional đã mở transaction, nên @Commit yêu cầu commit khi listener kết thúc; @AfterTransaction kiểm tra count=1 từ ngoài transaction rồi cleanup.

**@Commit không mặc nhiên rollback khi assertion fail.** Nó là commit policy; kết quả cuối còn phụ thuộc rollback-only state, commit exceptions và listeners. Nếu test fail trước khi cleanup, finally trong @AfterTransaction vẫn cố dọn row. Nếu JVM crash, preclean ở lần chạy sau là lớp bảo vệ khác.

## 11. @BeforeEach và @AfterEach khác @BeforeTransaction/@AfterTransaction

Trong một test method có **Spring @Transactional** do TestContext quản lý:

| Lifecycle hook | Chạy ở đâu? | Cách sử dụng |
| --- | --- | --- |
| @BeforeTransaction | Ngoài test transaction | Preclean/kiểm tra baseline committed |
| @BeforeEach | Trong test transaction | Tạo fixture được rollback cùng test |
| @Test | Trong test transaction | Thực hiện và assert |
| @AfterEach | Trong test transaction | Kiểm tra tạm, không đủ để xóa committed row khác transaction |
| @AfterTransaction | Ngoài test transaction | Quan sát commit/rollback cuối và cleanup |

Với **HttpCommitIsolationTest**, class **không @Transactional**, nên @BeforeEach/@AfterEach không nằm trong test-managed transaction và cleanup JdbcTemplate được commit theo cách thông thường.

**@AfterTransaction không chạy khi test không có test-managed transaction.** Vì vậy không copy một @AfterTransaction method vào test HTTP không transactional rồi chờ nó dọn.

### @Sql AFTER_TEST_METHOD không tự có nghĩa “ngoài transaction”

Spring **SqlScriptsTestExecutionListener** có thể chạy @Sql script theo transaction mode được xác định từ @SqlConfig/PlatformTransactionManager. Script AFTER_TEST_METHOD **có thể tham gia test transaction** và bị rollback sau đó. Muốn dọn committed data, cần chọn **@AfterTransaction** hoặc một @SqlConfig(transactionMode=ISOLATED) có kiểm soát, hiểu rõ lock và execution order. Không dùng một teardown script “được gắn after” để suy ra tất cả dữ liệu commit đã bị xóa.

## 12. Spring TestContext cache và @DirtiesContext không thay DB cleanup

Spring TestContext cache ApplicationContext nhằm giảm thời gian startup. Hai test classes có cấu hình giống nhau có thể dùng chung Spring beans, datasource pool, embedded H2 DB và singleton state.

**@DirtiesContext** đánh dấu context cần đóng hoặc dựng lại, nhưng **không phải lệnh DELETE trên database**. Với PostgreSQL/MySQL/Testcontainers database bên ngoài process, rows đã commit vẫn có thể sống sau khi context đóng. Với H2, DB lifecycle phụ thuộc connection và URL/DB_CLOSE_DELAY; đừng đoán rằng đóng context luôn reset toàn bộ DB.

| Công cụ | Giải quyết vấn đề nào? |
| --- | --- |
| @DataJpaTest rollback | DML trong test-managed transaction |
| @DirtiesContext | State của Spring context/cache, khi cần dựng lại |
| @AfterTransaction cleanup | Rows đã commit ngoài test transaction |
| @Sql seed per method | Baseline test có thể tái tạo |
| Testcontainers per schema/job | Database vật lý hoặc namespace riêng |
| Unique test keys | Tránh collision giữa test methods |
| Reset mock/cache cụ thể | Shared in-memory state |

**Hai contexts khác nhau vẫn có thể cùng một database thật** nếu JDBC URL giống nhau. Ngược lại, cùng một context vẫn có thể chạy test an toàn nếu mỗi method có fixture riêng và rollback/cleanup tốt. Cần biết **physical database identity** chứ không chỉ Spring context cache key.

## 13. Test song song không tự an toàn nhờ rollback

Hai tests chạy sequential và đều rollback có thể vẫn fail khi **parallel** nếu cùng INSERT unique key, cùng DELETE một table, cùng ghi global cache hoặc cùng thao tác external resource. Rollback không ngăn hai transactions tranh chấp row/lock.

Chiến lược:
- Gắn **unique external key theo method**, và theo CI run nếu nhiều jobs cùng DB.
- Nếu dùng key cố định của @Sql, dùng **SAME_THREAD**, @ResourceLock hoặc database/schema riêng; @ResourceLock chỉ phối hợp các tests tương ứng trong cùng JUnit launcher, không điều phối các CI jobs khác.
- Không dùng DELETE FROM tickets trên DB chung khi suite parallel.
- Tránh mutable static fields và singleton test fixtures.
- Nếu cùng một fixture được dùng cho nhiều tests, để nó **immutable/read-only** hoặc clone vào transaction riêng.
- Với external resources, dùng namespace riêng: Redis key prefix, Kafka topic test-run key, object-storage path riêng.
- Chờ async side effects có completion signal, không Thread.sleep đoán thời gian rồi cleanup quá sớm.

**Dùng UUID trong key không thay cleanup.** Nó giảm xác suất collision, nhưng nếu không xóa, database vẫn tích lũy residue. Với database shared giữa CI jobs, ưu tiên schema/database per job hơn phụ thuộc xác suất và global cleanup.

## 14. Kiểm tra independence một cách có hệ thống

**Đầu tiên: chạy riêng từng class/method.** Ví dụ các lệnh Gradle khi project có Wrapper tương thích với Java 17:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.testdata.RollbackIsolationTest
./gradlew test --tests com.example.testdata.SqlSeedIsolationTest
./gradlew test --tests com.example.testdata.HttpCommitIsolationTest
./gradlew test --tests com.example.testdata.RequiresNewIsolationTest
./gradlew test --tests com.example.testdata.CommitCleanupTest
./gradlew test --tests com.example.testdata.RollbackIsolationTest.createsOwnFixtureAndRunsIndependently
~~~

Trên Windows thay ./gradlew bằng gradlew.bat. Các tests **được thiết kế để PASS** với files/config kể trên; không phải stdout build thực tế được quan sát.

**Sau đó:** chạy toàn suite nhiều lần, thử alternate method order và parallel execution trong CI nếu hệ thống thật hỗ trợ. Nếu test chỉ fail khi chạy toàn suite, inspect:
- Unique key đã có từ run trước?
- @Commit hoặc REQUIRES_NEW có commit mà không cleanup?
- HTTP request chạy trên server thread?
- @Sql seed có transaction ISOLATED?
- Một test dùng @BeforeAll setup chung rồi tests khác mutate?
- Có static/singleton mutable state hoặc cache?
- Có database reuse ngoài ApplicationContext lifecycle?

**Cách dùng JUnit random order chỉ để phát hiện:**

~~~java
@TestMethodOrder(MethodOrderer.Random.class)
class RandomizedTestExamples {
    // Mỗi @Test vẫn phải tự setup và cleanup.
}
~~~

Đây là **trích đoạn minh họa**, cần imports JUnit và test methods để chạy. Random order tăng khả năng phát hiện phụ thuộc nhưng không tự sửa root cause; cần tái hiện bằng seed và sửa fixture/cleanup.

### Test thật sự độc lập khi chạy một mình

Một anti-pattern là class-level @BeforeAll tạo một tài khoản và nhiều test methods sửa nó. Khi chạy riêng test method qua filter runner, @BeforeAll có thể vẫn chạy, nên tưởng method độc lập; thực tế các methods vẫn chia sẻ account mutable. Hãy xem liệu mọi method cần state pristine có được reset qua @BeforeEach/@Sql hoặc fresh entity hay không.

Không nên cho test B tham chiếu biến static hoặc ID của test A dù @BeforeAll có tạo baseline. Baseline read-only có thể hợp lệ, nhưng mutation phải scoped.

## 15. Testcontainers và production database semantics

H2 nhanh, có schema/constraints thật và hữu ích cho unit/slice tests. Nhưng các hành vi có thể khác DB production:
- Sequence/identity sau rollback.
- Unique/FK constraints, isolation, locking, deadlocks.
- SQL dialect, collations, data types và native queries.
- Read/write concurrency giữa connections.
- Migration với Flyway/Liquibase.
- Transaction visibility khi commit/rollback.

Nếu tính năng phụ thuộc những chi tiết này, bổ sung **Testcontainers** với đúng engine/version gần deployment. Lưu ý container có thể **tái sử dụng giữa các test classes**, và database bên trong container **không tự được reset trước từng method**. Chọn one schema/database per test class/job, hoặc transactions + fixture cleanup rõ.

**@DirtiesContext không thay Testcontainers reset.** Nó làm mới Spring context chứ không xóa physical database do container đang chạy. Một test bình thường chạy vài giây không nên mặc nhiên start/stop container per method nếu không cần; cân bằng hiệu năng với mức độ cô lập.

## 16. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Biện pháp |
| --- | --- | --- |
| Test B chỉ xanh khi chạy sau A | B cần fixture từ A | Tự setup data trong B |
| @TestMethodOrder giúp suite xanh nhưng chạy riêng vẫn fail | Dùng thứ tự để che thiếu fixture | Xóa dependency, không ép order |
| Unique constraint khi chạy lại | Row commit từ test/run trước | Preclean/postclean hoặc DB riêng |
| @DataJpaTest thấy row trong method rồi biến mất | Rollback mặc định | Đúng behavior, không thêm @Commit nếu không cần |
| @SpringBootTest data còn lại sau test | Test không @Transactional hoặc service commit ngoài | Xác định tx boundary, dọn riêng |
| HTTP test để lại row dù JUnit test @Transactional | Server thread transaction khác | Cleanup ngoài test tx |
| REQUIRES_NEW row không bị outer rollback | Transaction mới đã commit | @AfterTransaction cleanup |
| @AfterEach DELETE mà committed row vẫn còn | DELETE nằm trong outer tx rồi rollback | Chuyển cleanup ngoài transaction |
| @Sql seed duplicate | Seed ISOLATED hoặc baseline committed từ run trước | Kiểm tra @SqlConfig, teardown |
| @DirtiesContext nhưng DB không sạch | Context cache khác database lifecycle | Reset DB hoặc DELETE đúng keys |
| ID generated không đúng số dự kiến | Identity counter không rollback | Assert business key/row behavior |
| Tests fail khi parallel | Cùng business key, broad cleanup, locks | Unique namespace/schema, ResourceLock |
| Fixture shared mutable bị test khác đổi | @BeforeAll/singleton/static state | Per-test fixture hoặc read-only baseline |
| Test pass một lần, fail khi rerun | Residue từ previous run | Idempotent preclean |
| Async row xuất hiện sau cleanup | Cleanup chạy trước task hoàn thành | Await completion rồi dọn |
| @Sql AFTER_TEST_METHOD cleanup không hiệu quả | Chạy trong transaction bị rollback | @AfterTransaction hoặc ISOLATED có chủ đích |
| H2 PASS, production DB fail | Dialect/isolation khác | Testcontainers production engine |
| Cleanup xóa data test khác | DELETE không giới hạn tenant/key | Cleanup scoped, database ephemeral |
| @Commit test fail và để lại row | Commit policy còn hiệu lực, teardown không chạy | finally/post-clean và preclean |
| Preemptive timeout làm rò data | Test body chạy thread khác | Tránh assertTimeoutPreemptively với test transaction |

## 17. Bài tập tự kiểm tra

**1.** Test B dùng ticketId do test A tạo. Chạy riêng B fail. Sửa bằng @Order? **Không**; B phải tự tạo Ticket/fixture.

**2.** @DataJpaTest saveAndFlush và count=1. Sau method row có còn? **Mặc định không**, do rollback.

**3.** @SpringBootTest có tự rollback mọi test methods không? **Không**; cần @Transactional trên test hoặc policy tương ứng.

**4.** HTTP POST được xử lý ở server thread và đã commit. @Transactional ở JUnit client rollback dữ liệu đó? **Không tự động**.

**5.** REQUIRES_NEW commit giữa một transactional test có bị outer rollback hủy không? **Không**.

**6.** @AfterEach trong transactional test chạy trước hay sau outer rollback? **Trước khi transaction kết thúc**, nên DELETE có thể rollback.

**7.** @AfterTransaction làm được gì mà @AfterEach không làm được? **Quan sát committed/rolled-back state ngoài test transaction và cleanup committed row**.

**8.** @Sql default trong @DataJpaTest có thể rollback cùng test method? **Có**, khi script tham gia test transaction theo cấu hình.

**9.** @SqlConfig(transactionMode=ISOLATED) có tạo committed fixtures không? **Có thể có**, vì script chạy transaction riêng được commit.

**10.** @DirtiesContext có tự truncate PostgreSQL không? **Không**.

**11.** H2 in-memory có tự tạo DB mới cho mỗi method trong một context? **Không**.

**12.** Generated ID phải reset về 1 sau rollback? **Không**; sequence/identity semantics có thể tiếp tục tăng.

**13.** UUID test key đã đủ chưa? **Chưa**; vẫn cần cleanup và external state isolation.

**14.** Nếu hai tests cùng DELETE tất cả Ticket trước khi chạy parallel, chúng độc lập không? **Không**; có thể xóa fixture của nhau.

**15.** Chạy MethodOrderer.Random một lần pass chứng minh test không phụ thuộc thứ tự không? **Không**; nó chỉ là phương tiện phát hiện.

**16.** @Commit có thể làm dữ liệu còn sau một test fail không? **Có thể**, vì commit policy khác assertion result.

**17.** Testcontainers luôn tạo DB mới trước mỗi method? **Không**, tùy lifecycle và reuse.

**18.** @BeforeAll tạo một entity rồi nhiều test thay đổi nó có an toàn không? **Không** nếu shared mutable state không reset.

**19.** Lệnh cleanup xóa toàn bảng trên shared test DB có nên dùng không? **Không**, nên giới hạn theo tenant/key hoặc dùng DB ephemeral.

**20.** Bất biến quan trọng nhất là gì? **Mỗi test tự sở hữu và quản lý data của mình, không cần test tiền nhiệm và không để residue ảnh hưởng test khác.**

### Checklist QA

- Mỗi test tạo đủ fixture và có thể chạy riêng?
- Không sử dụng static ID hay @TestMethodOrder để che phụ thuộc?
- Có biết test nào transactional/rollback mặc định?
- Có phân biệt JPA flush với DB commit?
- @Sql scripts thuộc test transaction hay ISOLATED?
- Test có key riêng theo tenant/method/run và không assert generated ID cố định?
- HTTP/REQUIRES_NEW/@Commit/async side effects đã được cleanup ngoài test rollback?
- @BeforeEach/@AfterEach vs @BeforeTransaction/@AfterTransaction đặt đúng nơi?
- @DirtiesContext không bị coi là DB cleanup?
- Có phòng tránh collision khi parallel và CI jobs dùng chung database?
- Mọi cleanup scoped đúng row, không xóa dữ liệu test khác hoặc production?
- Fixture baseline có bị mutate ngoài rollback không?
- Tests có được chạy riêng, chạy lặp và thử alternate order?
- Cần production DB semantics đã có integration tests đúng engine?
- State ngoài DB (cache/files/queue/session) có lifecycle độc lập?

**Kết luận:** Một test độc lập **không cần dữ liệu test trước để lại**, và sau khi chạy không làm môi trường trở nên khó đoán. Dùng **@DataJpaTest rollback** cho DB operations cùng test transaction, **@Sql per-method** cho baseline, và **cleanup thật sự ngoài transaction** cho dữ liệu đã commit qua HTTP, REQUIRES_NEW hay @Commit. Bổ sung key riêng, context/database isolation và kiểm tra random/parallel order khi cần. Đây là cách biến một suite Spring Boot từ “chỉ xanh trong thứ tự quen thuộc” thành một tập kiểm thử tin cậy.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — TestContext Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — Executing SQL Scripts with @Sql: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Data JPA — Reference Documentation: https://docs.spring.io/spring-data/jpa/reference/
- JUnit 5 — Test Execution Order and Parallel Execution: https://junit.org/junit5/docs/current/user-guide/
- Spring Framework — Transaction Propagation REQUIRES_NEW: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
