# @Rollback, @Commit và kiểm soát dữ liệu sau mỗi test trong Spring Boot

Khi kiểm thử code tương tác database, một test có thể **PASS** nhưng vẫn để lại dữ liệu cho test khác, hoặc ngược lại: dữ liệu đã xuất hiện trong cùng transaction nhưng **biến mất ngay sau test** do rollback. Hiểu sai điều này dẫn tới hai vấn đề trái ngược: test “xanh giả” vì không flush/commit ở thời điểm phù hợp, và test bị **phụ thuộc thứ tự chạy** vì dùng @Commit hay transaction độc lập mà không cleanup.

Trong Spring Boot, **@Transactional trên một JUnit test**, **@Rollback**, **@Commit**, **@BeforeTransaction**, **@AfterTransaction** và **TestTransaction** là các công cụ của **Spring TestContext Framework**. Chúng cần được phân biệt với **@Transactional trên service nghiệp vụ**, với transaction thật trên HTTP server thread, với SQL initializer và với cơ chế dọn dữ liệu database.

Bài học dùng **Java 17, Spring Boot 3.4.5, Spring Data JPA, Hibernate, H2, JUnit Jupiter**. Có ví dụ đầy đủ chạy theo cấu trúc Gradle: rollback mặc định, commit rồi cleanup, @Rollback(false), method override class-level @Commit, TestTransaction.commit/end/start và một service **Propagation.REQUIRES_NEW** cố ý tạo commit không bị rollback bởi test bên ngoài. Các kết quả test được trình bày là **kỳ vọng từ mã**, không phải stdout một phiên Gradle đã chạy.

## 1. Mô hình quan trọng nhất: test-managed transaction

Spring TestContext có một **TransactionalTestExecutionListener** (được cấu hình mặc định trong hầu hết Spring integration tests). Khi test có **Spring @Transactional** ở class hoặc method, và ApplicationContext có **PlatformTransactionManager**, listener mở **test-managed transaction trước khi method test chạy** và kết thúc transaction khi test xong.

Mặc định, transaction của test được **ROLLBACK**. Đây là hành vi của framework test, **không phải** quy tắc rằng mọi business transaction ở production cũng rollback.

~~~text
Spring TestContext chuẩn bị ApplicationContext
                    |
                    v
          @BeforeTransaction          [ngoài test transaction]
                    |
                    v
         BEGIN test transaction
                    |
                    v
              @BeforeEach              [trong test transaction]
                    |
                    v
                @Test                  [trong test transaction]
          repository.saveAndFlush(...)
          query trong cùng transaction thấy row
                    |
                    v
              @AfterEach               [trong test transaction]
                    |
                    v
        TestContext quyết định:
          mặc định -> ROLLBACK
          @Rollback(false) -> COMMIT
          @Commit -> COMMIT
                    |
                    v
           @AfterTransaction           [ngoài test transaction]
~~~

**@BeforeTransaction và @AfterTransaction** chỉ được gọi khi test method thực sự được cấu hình chạy trong test-managed transaction. Ngược lại, **@BeforeAll/@AfterAll** không nằm trong từng test transaction. **@BeforeEach/@AfterEach** thông thường chạy **bên trong test transaction đã được listener mở**; vì vậy nếu @AfterEach delete rows, thay đổi ấy cũng có thể bị rollback và **không dọn được dữ liệu mà test đã commit ở transaction khác**.

### Transaction của test không đồng nghĩa với transaction của mọi thread

Test-managed transaction gắn với **thread thực thi test** thông qua transaction context/ThreadLocal. Một lời gọi trực tiếp tới Spring service có **@Transactional(propagation=REQUIRED)** thường tham gia transaction ấy. Nhưng một request HTTP thật chạy trên servlet server thread, một @Async task hoặc một service **REQUIRES_NEW** có thể dùng transaction khác và commit độc lập. **Rollback của JUnit test không tự cuốn các transaction đó vào.**

Đây là giới hạn phải nắm trước khi thiết kế cleanup và đánh giá dữ liệu tồn tại sau test.

## 2. Ba annotation cốt lõi: @Transactional, @Rollback, @Commit

| Annotation / tình huống | Test-managed transaction có được mở? | Kết thúc mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| Không có @Transactional | **Không**, trừ cơ chế khác do code tự mở | Không có test rollback tự động | DML có thể commit theo service/connection behavior |
| @Transactional ở test method | **Có**, nếu có transaction manager phù hợp | **ROLLBACK** | Kiểm tra DB trong transaction rồi tự cô lập |
| @Transactional ở test class | **Có** với từng test method thuộc class đó | **ROLLBACK** | Mọi test có transaction độc lập ở mức method |
| @Transactional + @Rollback | Có | **ROLLBACK** | Viết rõ hành vi rollback; tương đương default |
| @Transactional + @Rollback(false) | Có | **COMMIT** | Giữ dữ liệu sau test, phải có cleanup chủ động |
| @Transactional + @Commit | Có | **COMMIT** | @Commit là cách biểu diễn chuyên biệt của @Rollback(false) |
| @Commit nhưng **không có** @Transactional | Không tự sinh test transaction | Không có test transaction để commit | Đừng kỳ vọng @Commit tự mở transaction |
| @Transactional(propagation=NOT_SUPPORTED) | Listener **không** mở test transaction | Không có rollback của listener | Thích hợp khi cố ý thử đường không transaction |

Có thể dùng **@Rollback** / **@Commit** ở class hoặc method. Annotation **method-level** có thể override policy class-level:

~~~java
@SpringBootTest
@Transactional
@Commit
class Example {
    @Test
    @Rollback
    void thisMethodRollsBack() {
        // Method-level @Rollback thắng @Commit ở class.
    }
}
~~~

Đây là **trích đoạn**, chưa có business code. **Không nên đặt cả @Commit và @Rollback trên cùng method** vì chúng thể hiện hai ý định mâu thuẫn; chọn một cơ chế rõ. Một exception trong service có thể đánh dấu transaction **rollback-only**, vì vậy “có @Commit” không bảo đảm database nhất định sẽ commit nếu transaction đã bị rollback-only hoặc commit gặp constraint error.

**@Rollback(false)** và **@Commit** là hai cách chọn hành vi **của test-managed transaction khi kết thúc**; chúng không thay đổi mọi transaction trên hệ thống. Nếu một service tạo **REQUIRES_NEW**, transaction nội bộ có lifecycle riêng. Nếu dùng database bên ngoài test và @Commit, dữ liệu tồn tại sau JUnit method cho tới khi được cleanup hoặc reset theo chính sách database.

## 3. @SpringBootTest và @DataJpaTest không có cùng mặc định transaction

**@DataJpaTest** là JPA slice test: mặc định cấu hình DataSource nhúng khi có driver phù hợp, JPA repositories/entities và **mỗi test chạy trong transaction được rollback sau method**. Nó phù hợp kiểm tra mapping, repository query, cascade, constraint và JPA flush.

**@SpringBootTest** tải ApplicationContext đầy đủ nhưng **bản thân annotation này không làm mọi test method transactional**. Muốn test-managed rollback, thêm **@Transactional** trên class hoặc method. Nếu một test dùng @SpringBootTest không có @Transactional rồi gọi service nghiệp vụ @Transactional, service có thể commit ở cuối lời gọi, và dữ liệu sẽ còn sau test.

Ví dụ ý định:

~~~java
@DataJpaTest
class RepositorySliceTest {
    @Test
    void insertIsRolledBackByDefault() {
        // @DataJpaTest mặc định đã transactional.
    }
}
~~~

~~~java
@SpringBootTest
@Transactional
class FullContextTransactionalTest {
    @Test
    void insertIsRolledBackByDefault() {
        // @Transactional mở test-managed transaction.
    }
}
~~~

Hai ví dụ là **trích đoạn**, chưa bao gồm repository. Dự án runnable từ phần 7 sẽ dùng **@SpringBootTest + @Transactional** để trình bày đầy đủ service propagation và test transaction. Có thể dùng @DataJpaTest cho các phép kiểm repository đơn giản.

**@DirtiesContext không thay cho cleanup DB.** Nó đánh dấu ApplicationContext để Spring không tái sử dụng từ context cache; việc đóng và mở lại context **không bảo đảm xóa dữ liệu đã commit** trong PostgreSQL/MySQL hoặc một H2 database sống ngoài context. Dữ liệu cần được cleanup bằng transaction/script/truncate/delete riêng hoặc database isolation phù hợp.

## 4. @BeforeTransaction và @AfterTransaction khác @BeforeEach/@AfterEach

Đây là điểm then chốt khi muốn **chứng minh rollback/commit thật sự**.

| Hook | Chạy lúc nào với test @Transactional? | Có test transaction? | Thích hợp làm gì? |
| --- | --- | --- | --- |
| **@BeforeTransaction** | Trước khi listener bắt đầu test transaction | **Không** | Kiểm tra/dọn baseline bên ngoài transaction |
| **@BeforeEach** | Sau khi test transaction đã bắt đầu | **Có** | Chuẩn bị fixture muốn tự rollback cùng test |
| **@Test** | Trong test transaction | **Có** | Thực thi và assert nghiệp vụ |
| **@AfterEach** | Trước khi listener đóng test transaction | **Có** | Assert state đang nằm trong transaction; cleanup tạm cùng tx |
| **@AfterTransaction** | Sau khi listener rollback/commit transaction | **Không** | Kiểm tra row còn sau commit hay biến mất sau rollback; cleanup committed data |

**Đừng dùng @AfterEach rồi tuyên bố “đã xác nhận rollback”.** Tại thời điểm @AfterEach chạy, test transaction vẫn thường mở, nên query sẽ thấy row do test vừa insert. Chỉ **@AfterTransaction** mới quan sát kết quả sau khi transaction kết thúc. Nếu không có transaction của test, hai annotation BeforeTransaction/AfterTransaction không chạy chỉ vì bạn đã gắn chúng lên method.

Các hook BeforeTransaction/AfterTransaction từ package:

~~~java
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;
~~~

Lưu ý: trong Spring Framework 6.1+ với JUnit Jupiter/SpringExtension, những hook này còn có thể nhận parameters qua JUnit ParameterResolvers, ví dụ TestInfo hoặc @Autowired bean. Dự án ở đây dùng fields được autowire để API dễ theo dõi.

### Nếu test commit thì cleanup đặt ở đâu?

Với một test **@Commit**, dữ liệu commit sẽ **không** bị xóa chỉ vì bạn gọi DELETE trong **@AfterEach**, vì DELETE có thể thuộc **chính transaction đang được commit**; nếu đã xóa trước commit, bạn thậm chí không còn cơ sở để kiểm tra dữ liệu thật sự tồn tại sau commit.

Một mẫu chính xác hơn:

1. **@BeforeTransaction:** xóa các row test-key còn sót từ lần chạy trước, ở ngoài test tx.
2. **@Test @Commit:** insert hoặc update; **flush** và assert state đang managed.
3. **@AfterTransaction:** đọc row từ transaction/connection mới để xác nhận đã commit.
4. **finally trong @AfterTransaction:** DELETE row bằng JdbcTemplate ngoài test tx, đảm bảo không nhiễm test khác ngay cả khi assertion thất bại.

Cleanup theo **key riêng của test** an toàn hơn “DELETE FROM every_table” trên một database dùng chung. Trên database production, các test phá hủy dữ liệu phải **tuyệt đối không** trỏ vào datasource thật.

## 5. Flush, clear và commit: ba hành vi không đồng nhất

Trong JPA/Hibernate:

- **persist/save** đặt entity vào persistence context, có thể chưa đẩy toàn bộ SQL.
- **flush** đồng bộ pending changes thành SQL bên trong transaction và có thể làm lộ constraint violation.
- **clear** detach các managed entities để lần query tiếp theo không chỉ trả object đã cache level 1.
- **commit** kết thúc transaction thành công; các thay đổi được durable/visible theo isolation rules.
- **rollback** hủy các thay đổi của transaction cho database, kể cả nếu đã flush.

Ví dụ:

~~~java
repository.saveAndFlush(new EventRecord("EVT-A", "created"));
assertEquals(1L, repository.countByEventKey("EVT-A"));
~~~

Khi chạy trong @Transactional test, dòng count=1 chỉ chứng minh **row hiện diện trong transaction này**. Sau mặc định rollback, kết quả từ một connection mới sẽ là **0**. Điều đó không phải lỗi của repository.

Spring Framework khuyến cáo **flush trong test ORM** khi cần bắt lỗi constraint/lifecycle vốn có thể chỉ phát sinh lúc flush. Nếu test cứ save rồi kết thúc bằng rollback mà không flush, một số lỗi mapping/constraint không bao giờ được phát hiện. @DataJpaTest và @SpringBootTest @Transactional đều có thể gặp vấn đề “false positive” này.

### Đọc row trong cùng transaction có chứng minh commit không?

**Không.** Một SELECT ngay sau INSERT trong cùng transaction thông thường thấy dữ liệu chưa commit (read-your-writes). Vì vậy test muốn chứng minh **đã commit thật** cần quan sát dữ liệu **sau khi transaction kết thúc**, chẳng hạn trong @AfterTransaction hoặc qua TestTransaction.end() + một query không thuộc transaction cũ.

## 6. Kết quả rollback/commit và trường hợp test thất bại

Khi test mang @Transactional, mặc định Spring TestContext sẽ rollback sau method ngay cả khi assertion của JUnit thành công. Ngược lại, **@Commit** chỉ yêu cầu commit ở cuối; nếu test fail assertion, transaction vẫn có thể được đánh dấu commit tùy cờ rollback-only, lỗi và listener lifecycle. Vì vậy dùng @Commit cần chú ý **khả năng rò dữ liệu kể cả khi test thất bại**.

Một chiến lược an toàn là:

- Chỉ dùng @Commit khi test thực sự cần xác nhận hành vi sau commit, event listener AFTER_COMMIT hoặc visibility.
- Dùng **test key/namespace riêng**, không dùng cố định ID của dữ liệu thật.
- Dọn dư lượng ở **@BeforeTransaction** để lần chạy lại không vướng unique constraint.
- Dọn sau commit trong **@AfterTransaction**, dùng **try/finally** để cleanup chạy dù assertion fail.
- Nếu process bị kill trước cleanup, một run tiếp theo vẫn dọn được qua before hook; trong CI nên dùng database/container riêng để cô lập.
- Không phụ thuộc test A commit fixture cho test B; test order không phải cách quản lý data state.

**@Sql AFTER_TEST_METHOD** có thể chạy theo transaction mode được cấu hình; không tự mặc định rằng mọi script “after” chạy **sau khi test transaction đã commit**. Nếu cần cleanup outside test tx, **@SqlConfig(transactionMode=ISOLATED)** hoặc @AfterTransaction có thể dùng tùy mục tiêu, nhưng phải hiểu execution order và transaction mode của SqlScriptsTestExecutionListener. Trong ví dụ chạy được, cleanup dùng @AfterTransaction để nhìn thấy lifecycle rõ ràng.

## 7. Dự án Java 17 + Spring Boot 3.4.5 + JPA + H2

Mục tiêu: kiểm chứng **test-managed transaction** bằng cùng một bảng **audit_events**. Mỗi test dùng **event_key riêng** để không phụ thuộc thứ tự và một JdbcTemplate đọc bảng thật khi ở ngoài JPA persistence context.

Hành vi mẫu:

- Test mặc định rollback: trong @Test row tồn tại, sau method row không còn.
- Test @Commit: trong @Test có row; sau commit row còn; sau @AfterTransaction cleanup row biến mất.
- Test @Rollback(false): semantics commit tương đương @Commit, rồi cleanup.
- Test @Rollback method override class @Commit: phương thức riêng vẫn rollback.
- TestTransaction: chủ động commit một transaction giữa method, bắt đầu transaction tiếp theo và rollback thay đổi tạm.
- Service REQUIRES_NEW: commit nội bộ không bị rollback theo test transaction ngoài, phải cleanup tường minh.

**Cấu trúc tệp:**

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/java/com/example/txqa/TxQaApplication.java
src/main/java/com/example/txqa/EventRecord.java
src/main/java/com/example/txqa/EventRecordRepository.java
src/main/java/com/example/txqa/IndependentEventWriter.java
src/test/java/com/example/txqa/DefaultRollbackTest.java
src/test/java/com/example/txqa/CommitCleanupTest.java
src/test/java/com/example/txqa/RollbackFalseCleanupTest.java
src/test/java/com/example/txqa/MethodOverrideRollbackTest.java
src/test/java/com/example/txqa/ManualTransactionTest.java
src/test/java/com/example/txqa/RequiresNewEscapesRollbackTest.java
~~~

### 7.1. Gradle build và H2 test database

**settings.gradle**

~~~groovy
rootProject.name = 'spring-test-transaction-control'
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

**H2 + create-drop** chỉ để học và test cô lập. Không dùng **ddl-auto=create-drop** cho production DB. Các test có thể dùng chung Spring ApplicationContext do cache, vì vậy mỗi test có **event_key riêng** và tự dọn commit. Nếu chạy với Testcontainers hoặc database thật, luôn dùng một database/schema test độc lập.

Dự án không có web starter nên không mở HTTP server. Điều này là **có chủ đích**, vì bài tập chính kiểm tra listener của test-managed transaction trên thread gọi JUnit test, không kiểm tra network. Phần 12 sẽ nói rõ HTTP integration test khác ở điểm nào.

### 7.2. Application class

**src/main/java/com/example/txqa/TxQaApplication.java**

~~~java
package com.example.txqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxQaApplication.class, args);
    }
}
~~~

### 7.3. JPA entity với một business key riêng cho test

**src/main/java/com/example/txqa/EventRecord.java**

~~~java
package com.example.txqa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "audit_events")
public class EventRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_key", nullable = false, unique = true)
    private String eventKey;

    @Column(nullable = false)
    private String payload;

    protected EventRecord() {
        // JPA constructor.
    }

    public EventRecord(String eventKey, String payload) {
        this.eventKey = eventKey;
        this.payload = payload;
    }

    public Long getId() {
        return id;
    }

    public String getEventKey() {
        return eventKey;
    }

    public String getPayload() {
        return payload;
    }
}
~~~

**event_key** là một key duy nhất; mỗi test dùng một chuỗi khác nhau. ID do H2 cấp để minh họa entity generation, nhưng các assertions không phụ thuộc ID auto-increment cụ thể, vì sequence/identity có thể không rollback số thứ tự khi transaction rollback.

### 7.4. Repository và service dùng transaction độc lập

**src/main/java/com/example/txqa/EventRecordRepository.java**

~~~java
package com.example.txqa;

import org.springframework.data.jpa.repository.JpaRepository;

public interface EventRecordRepository
        extends JpaRepository<EventRecord, Long> {

    long countByEventKey(String eventKey);
}
~~~

**src/main/java/com/example/txqa/IndependentEventWriter.java**

~~~java
package com.example.txqa;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentEventWriter {
    private final EventRecordRepository repository;

    public IndependentEventWriter(EventRecordRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String eventKey) {
        repository.saveAndFlush(
                new EventRecord(eventKey, "independent commit"));
    }
}
~~~

**REQUIRES_NEW** mở một transaction Spring-managed mới cho public service method được gọi **qua Spring proxy**. Nếu test bên ngoài đang có test-managed transaction, Spring suspend nó, thực hiện transaction service, commit transaction mới, rồi resume transaction ngoài. Rollback transaction ngoài **không đảo ngược commit bên trong**.

Không thử tái hiện bằng private method hoặc self-invocation **this.record(...)** trong cùng bean, vì Spring AOP proxy có thể bị bỏ qua. Ở phần test, service được **@Autowired** nên lời gọi đi qua proxy đúng cách.

## 8. Test mặc định rollback: bằng chứng trước, trong và sau

**src/test/java/com/example/txqa/DefaultRollbackTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
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
class DefaultRollbackTest {
    private static final String KEY = "default-rollback";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    @BeforeTransaction
    void beforeTransaction() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
        assertEquals(0L, count());
    }

    @BeforeEach
    void beforeEachRunsInsideTransaction() {
        assertTrue(TestTransaction.isActive());
    }

    @Test
    void insertedRowExistsBeforeRollback() {
        repository.saveAndFlush(new EventRecord(KEY, "temporary"));

        assertEquals(1L, repository.countByEventKey(KEY));
        assertEquals(1L, count());
    }

    @AfterEach
    void afterEachStillRunsInsideTransaction() {
        assertTrue(TestTransaction.isActive());
        assertEquals(1L, count());
    }

    @AfterTransaction
    void afterTransactionVerifiesRollback() {
        assertEquals(0L, count());
    }
}
~~~

**Đọc bằng chứng:**

1. **@BeforeTransaction** chạy ngoài test transaction, xóa row cũ theo KEY (nếu có) và assert baseline 0.
2. **@BeforeEach** chứng minh TestTransaction.isActive()==true.
3. **@Test** saveAndFlush, rồi repository/JdbcTemplate đều thấy row trong cùng transaction.
4. **@AfterEach** vẫn ở trong transaction nên còn thấy row, dù sắp bị rollback.
5. Spring TestContext **rollback mặc định** vì test class có @Transactional và không ghi @Commit.
6. **@AfterTransaction** dùng query bên ngoài transaction, xác nhận **row không còn**.

Không cần “xóa lại row” trong @AfterEach; rollback đủ dọn thay đổi của chính test transaction. Nhưng trước mỗi run vẫn cleanup baseline để bài test không phụ thuộc vào dữ liệu còn sót do một thao tác ngoài transaction ở run trước.

## 9. @Commit: kiểm tra dữ liệu sau commit rồi cleanup

**src/test/java/com/example/txqa/CommitCleanupTest.java**

~~~java
package com.example.txqa;

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
    private static final String KEY = "commit-and-cleanup";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    private void cleanup() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
    }

    @BeforeTransaction
    void removeResidueFromEarlierRun() {
        cleanup();
        assertEquals(0L, count());
    }

    @Test
    @Commit
    void persistsRowBeyondEndOfTestTransaction() {
        repository.saveAndFlush(new EventRecord(KEY, "committed"));
        assertEquals(1L, count());
    }

    @AfterTransaction
    void verifyCommittedDataThenCleanUp() {
        try {
            assertEquals(1L, count());
        } finally {
            cleanup();
        }
        assertEquals(0L, count());
    }
}
~~~

Tại sao không chỉ đặt **@AfterEach** để cleanup? Vì @AfterEach nằm trong transaction còn mở. Ở đây cần xác nhận dữ liệu **thật sự còn sau commit**, nên @AfterTransaction mới kiểm tra được. JdbcTemplate ngoài transaction dùng connection/transaction lifecycle riêng để DELETE. **finally** đảm bảo cleanup được thực hiện ngay cả khi assertion về count sau commit thất bại; nếu JDBC cleanup cũng hỏng, test báo lỗi thực tế.

**Quan trọng:** @Commit không nên dùng nếu mục tiêu chỉ là test repository CRUD đơn giản. Rollback mặc định thường nhanh và cô lập hơn. Chỉ commit khi cần kiểm tra **sau commit**; càng nhiều @Commit test càng cần lifecycle cleanup mạnh.

## 10. @Rollback(false): tương đương @Commit ở cuối test

**src/test/java/com/example/txqa/RollbackFalseCleanupTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Transactional
class RollbackFalseCleanupTest {
    private static final String KEY = "rollback-false";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    private void cleanup() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
    }

    @BeforeTransaction
    void reset() {
        cleanup();
        assertEquals(0L, count());
    }

    @Test
    @Rollback(false)
    void commitsRatherThanRollsBack() {
        repository.saveAndFlush(
                new EventRecord(KEY, "kept until cleanup"));
        assertEquals(1L, count());
    }

    @AfterTransaction
    void verifyThenRemoveCommittedRow() {
        try {
            assertEquals(1L, count());
        } finally {
            cleanup();
        }
        assertEquals(0L, count());
    }
}
~~~

Ở đây **@Rollback(false)** trên method đạt cùng hiệu ứng với **@Commit**. Cả hai thay đổi **quyết định kết thúc test-managed transaction**; chúng không gắn thêm transaction nếu không có @Transactional.

**Không đặt hai annotation đồng thời trên cùng method**. Chọn một cách nhất quán trong codebase, ví dụ @Commit khi muốn chủ động ghi dữ liệu và @Rollback khi muốn nhấn mạnh method override policy class-level.

## 11. Method-level @Rollback override class-level @Commit

Một class có thể đặt **@Commit** ở cấp class để những test cần commit dễ đọc, nhưng một method lại có mục tiêu rollback. Hãy cho method ghi rõ @Rollback.

**src/test/java/com/example/txqa/MethodOverrideRollbackTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.annotation.Rollback;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Transactional
@Commit
class MethodOverrideRollbackTest {
    private static final String KEY = "method-overrides-commit";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    @BeforeTransaction
    void baseline() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
        assertEquals(0L, count());
    }

    @Test
    @Rollback
    void methodChoosesRollbackDespiteClassCommit() {
        repository.saveAndFlush(
                new EventRecord(KEY, "should disappear"));
        assertEquals(1L, count());
    }

    @AfterTransaction
    void methodWasRolledBack() {
        assertEquals(0L, count());
    }
}
~~~

Khi framework quyết định kết thúc test transaction, **method-level @Rollback** có độ ưu tiên hơn **class-level @Commit**; vậy row biến mất. Đây là phép kiểm hữu ích khi dự án có một base test class hoặc meta-annotation khai báo transaction policy mà một test cụ thể cần override.

**Khuyến nghị thiết kế:** đừng rải @Commit ở base class rồi khiến nhiều test commit ngầm. Đặt commit policy càng gần test thực sự cần commit càng dễ audit và cleanup.

## 12. TestTransaction: chủ động commit/rollback ngay trong method

Đôi khi bạn muốn kiểm tra dữ liệu **sau commit** ngay trong cùng method JUnit, chứ không đợi @AfterTransaction, hoặc cần một transaction mới sau khi transaction ban đầu đã kết thúc. Spring TestContext cung cấp **TestTransaction**:

| API | Ý nghĩa |
| --- | --- |
| **TestTransaction.isActive()** | Đang có active test-managed transaction không? |
| **TestTransaction.flagForCommit()** | Đánh dấu transaction hiện tại sẽ commit khi end |
| **TestTransaction.flagForRollback()** | Đánh dấu transaction hiện tại sẽ rollback khi end |
| **TestTransaction.isFlaggedForRollback()** | Cờ kết thúc của transaction hiện tại |
| **TestTransaction.end()** | Kết thúc test transaction hiện tại theo cờ commit/rollback |
| **TestTransaction.start()** | Bắt đầu một test transaction mới khi trước đó đã end |

**src/test/java/com/example/txqa/ManualTransactionTest.java**

~~~java
package com.example.txqa;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
class ManualTransactionTest {
    private static final String PERMANENT_KEY = "manual-committed";
    private static final String TEMP_KEY = "manual-rolled-back";

    @Autowired
    private EventRecordRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    private long count(String key) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, key);
    }

    private void cleanup() {
        jdbc.update(
                "DELETE FROM audit_events WHERE event_key IN (?, ?)",
                PERMANENT_KEY, TEMP_KEY);
    }

    @BeforeTransaction
    void baseline() {
        cleanup();
        assertEquals(0L, count(PERMANENT_KEY));
        assertEquals(0L, count(TEMP_KEY));
    }

    @Test
    void commitFirstTransactionThenRollbackSecond() {
        assertTrue(TestTransaction.isActive());
        assertTrue(TestTransaction.isFlaggedForRollback());

        repository.saveAndFlush(
                new EventRecord(PERMANENT_KEY, "committed"));

        TestTransaction.flagForCommit();
        assertFalse(TestTransaction.isFlaggedForRollback());
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertEquals(1L, count(PERMANENT_KEY));

        TestTransaction.start();
        TestTransaction.flagForRollback();
        assertTrue(TestTransaction.isActive());

        repository.saveAndFlush(
                new EventRecord(TEMP_KEY, "temporary"));
        assertEquals(1L, count(TEMP_KEY));

        // TestContext rollback transaction thứ hai sau method.
    }

    @AfterTransaction
    void onlyFirstTransactionWasCommitted() {
        try {
            assertEquals(1L, count(PERMANENT_KEY));
            assertEquals(0L, count(TEMP_KEY));
        } finally {
            cleanup();
        }
        assertEquals(0L, count(PERMANENT_KEY));
        assertEquals(0L, count(TEMP_KEY));
    }
}
~~~

**Dòng thời gian:**

~~~text
TestTransaction active (mặc định flag rollback)
  -> insert PERMANENT_KEY
  -> flagForCommit(); end()  => COMMIT đầu tiên
  -> isActive() == false; count(PERMANENT_KEY)==1
  -> start() giao dịch mới
  -> flagForRollback()
  -> insert TEMP_KEY
  -> kết thúc @Test
  -> listener ROLLBACK transaction thứ hai
  -> @AfterTransaction:
       count(PERMANENT_KEY)==1
       count(TEMP_KEY)==0
       cleanup committed row PERMANENT_KEY
~~~

**TestTransaction chỉ quản lý test transaction đang hoạt động của Spring TestContext.** Nó không phải API tổng quát để điều khiển mọi transaction service chạy trên thread khác hoặc transaction đã commit. **TestTransaction.end() không bắt buộc phải gọi cho mọi test**; chỉ dùng nếu bài cần thay đổi ranh giới transaction trong method. Nếu muốn transaction mới có default rollback, vẫn có thể gọi flagForRollback() tường minh như ở đây để ý định rõ.

**Cảnh báo:** nếu gọi **TestTransaction.end()** mà không start() lại, các thao tác tiếp theo có thể chạy ngoài transaction, dẫn tới commit ngoài ý định. Phải theo dõi isActive và cleanup bất cứ committed data nào.

## 13. REQUIRES_NEW: một commit không bị rollback theo test

**src/test/java/com/example/txqa/RequiresNewEscapesRollbackTest.java**

~~~java
package com.example.txqa;

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
class RequiresNewEscapesRollbackTest {
    private static final String KEY = "requires-new-commit";

    @Autowired
    private IndependentEventWriter writer;

    @Autowired
    private JdbcTemplate jdbc;

    private long count() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE event_key = ?",
                Long.class, KEY);
    }

    private void cleanup() {
        jdbc.update("DELETE FROM audit_events WHERE event_key = ?", KEY);
    }

    @BeforeTransaction
    void baseline() {
        cleanup();
        assertEquals(0L, count());
    }

    @Test
    void independentServiceCommitSurvivesOuterRollback() {
        assertTrue(TestTransaction.isActive());

        // Proxy mở REQUIRES_NEW, inner transaction commit.
        writer.record(KEY);

        // Outer test transaction vẫn active; khi test kết thúc,
        // outer rollback không đảo ngược inner commit.
    }

    @AfterTransaction
    void committedInnerRowMustBeRemovedExplicitly() {
        try {
            assertEquals(1L, count());
        } finally {
            cleanup();
        }
        assertEquals(0L, count());
    }
}
~~~

**Đây là phản chứng rất quan trọng.** Test có @Transactional và cuối method rollback mặc định, nhưng service được gọi qua proxy có **Propagation.REQUIRES_NEW**. Transaction của service được commit độc lập, nên row vẫn còn. Nếu bạn tin “@Transactional ở test sẽ dọn hết mọi dữ liệu do test làm”, bài test này chứng minh nhận định đó **sai**.

Điểm cần phân biệt:

- **REQUIRED:** service thường tham gia transaction đã có, dữ liệu có thể rollback theo test transaction.
- **REQUIRES_NEW:** service suspend transaction hiện tại rồi mở transaction mới; khi phương thức return thành công, nó commit độc lập.
- **NOT_SUPPORTED:** phương thức chạy ngoài transaction hiện tại, nên JDBC/JPA behavior và auto-commit cần xem cụ thể.
- **@Async** hay thread mới: transaction context của test không tự propagate sang thread khác; cách dữ liệu commit phụ thuộc service transaction.
- **HTTP với RANDOM_PORT:** request xử lý ở servlet server thread, có transaction khác với thread JUnit test.

Không dùng REQUIRES_NEW trong business code chỉ để “thoát rollback của test”; hãy dùng propagation theo yêu cầu nghiệp vụ, rồi thiết kế test cleanup tương ứng.

## 14. Vì sao @AfterEach không dọn được mọi dữ liệu?

Giả sử @Test có **outer transaction** nhưng gọi một REQUIRES_NEW service đã commit row. Trong **@AfterEach**, nếu bạn viết:

~~~java
@AfterEach
void cleanup() {
    jdbc.update(
            "DELETE FROM audit_events WHERE event_key = ?",
            "requires-new-commit");
}
~~~

Đây là **trích đoạn phản ví dụ**. @AfterEach có thể đang chạy **trong outer test transaction**. DELETE được thực thi trong outer transaction và sẽ bị **rollback cùng outer transaction**, trong khi INSERT của REQUIRES_NEW đã commit; row có thể **vẫn còn**. Điều đó lý giải vì sao dọn trong @AfterTransaction ngoài transaction, hoặc dùng một cleanup transaction độc lập có chủ đích, đáng tin hơn cho loại dữ liệu này.

**Không phải @AfterEach luôn vô dụng**: khi dữ liệu được tạo trong cùng test transaction thì cả INSERT và DELETE đều rollback; nhưng cleanup ấy thường không cần thiết vì rollback mặc định đã làm việc đó. Với dữ liệu commit ngoài test transaction, cleanup phải nằm ngoài ranh giới bị rollback.

Một test integration có database dùng chung có thể cần **@SqlConfig(transactionMode=ISOLATED)** cho teardown, hoặc gọi repository cleanup thông qua transaction riêng. Hãy kiểm tra listener ordering/SQL script transaction mode của phiên bản Spring; không mặc định rằng annotation AFTER_TEST_METHOD có nghĩa “sau commit” trong mọi trường hợp.

## 15. Khi nào @Sql giúp kiểm soát fixture và cleanup?

Spring TestContext hỗ trợ **@Sql** để chạy script trước/sau test:

~~~java
@Sql(
    scripts = "/sql/seed-entries.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(
    scripts = "/sql/cleanup-entries.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class ExampleSqlScriptsTest {
}
~~~

Đây là **trích đoạn**, không thuộc runnable project vì thiếu hai scripts/imports và cấu hình test. **ISOLATED** nghĩa là script chạy trong transaction riêng và commit ngay, phù hợp khi cleanup phải bền vững ngoài test rollback. Nhưng script nào chạy trước/sau transaction test phụ thuộc listener ordering và cấu hình; nếu bạn cần assert kết quả sau commit, **@AfterTransaction** là hook tường minh hơn.

**Khuyến nghị với fixtures:**

- Dùng **@Sql hoặc repository setup** khi muốn seed dữ liệu riêng cho test.
- Khi @Sql tham gia test transaction, fixture cũng bị rollback; tốt để cô lập test method.
- Khi @Sql dùng transaction ISOLATED, dữ liệu có thể **được commit trước khi test chạy** và không tự bị rollback bởi @Transactional test; cần teardown.
- Khi @Commit, thường cần **cleanup sau commit** hoặc test DB được recreate/reset giữa runs.
- Với multiple tables có foreign keys, cleanup theo thứ tự child → parent hoặc dùng truncate/schema isolation hợp lý.
- Không chạy destructive scripts trên datasource production.

Nếu test dùng SQL init từ **schema.sql/data.sql** tại context startup, các rows khởi tạo không nằm trong test transaction. Rollback của test **không xóa baseline fixtures**; nó chỉ hủy thay đổi nằm trong transaction test.

## 16. Test transaction và Spring Data repository: những giới hạn cần biết

### 16.1. @Transactional trên test không có đầy đủ semantics của @Transactional trên service

Theo tài liệu Spring TestContext, annotation @Transactional trên **test method/class** có những thuộc tính được listener hỗ trợ giới hạn:

| Attribute trên test @Transactional | Hỗ trợ cho test-managed transaction |
| --- | --- |
| value / transactionManager | Có |
| propagation NOT_SUPPORTED và NEVER | Dùng để không chạy test transaction |
| propagation REQUIRED/REQUIRES_NEW/... | Không nên kỳ vọng listener sử dụng đủ semantics như business service |
| isolation | Không được TestContext listener dùng để tùy chỉnh test transaction |
| timeout | Không được listener dùng như business tx timeout |
| readOnly | Không được listener dùng làm chính sách test transaction |
| rollbackFor / noRollbackFor | Không được listener dùng để chọn test commit/rollback |

Muốn điều khiển commit/rollback của test, dùng **@Rollback**, **@Commit** hoặc **TestTransaction.flagForCommit/flagForRollback**. Để test isolation/timeout/readOnly hoặc propagation chi tiết của **service**, hãy gọi service qua Spring-managed proxy và kiểm tra behavior ở transaction manager/database thích hợp.

**Không đặt @Transactional trên @BeforeEach để “mở transaction”**: test listener mở transaction dựa trên test class/method, chứ không dựa vào lifecycle method; annotation ở lifecycle method không có tác dụng như suy nghĩ đó.

### 16.2. Nếu có nhiều PlatformTransactionManager

Một ApplicationContext có nhiều transaction managers (ví dụ JPA + JDBC hoặc multiple datasources). TestContext cần chọn đúng manager; có thể chỉ định:

~~~java
@Transactional(transactionManager = "orderTransactionManager")
class ExampleTwoManagers {
}
~~~

Đây là trích đoạn, bean orderTransactionManager không có trong runnable demo. Nếu chọn sai manager, test có thể rollback một datasource nhưng service ghi vào datasource khác đã commit. Cần test cả những nguồn dữ liệu có side effects, không chỉ một DB.

### 16.3. @Commit và event listeners

Một method đánh dấu **@TransactionalEventListener(phase = AFTER_COMMIT)** chỉ chạy khi transaction thực sự commit, không chạy khi test kết thúc rollback theo mặc định. Vì vậy:

- Test dùng rollback mặc định không chứng minh AFTER_COMMIT listener đã thực thi.
- Có thể dùng **@Commit** hoặc **TestTransaction.flagForCommit + end** để kích hoạt AFTER_COMMIT trong test.
- Sau đó assert side effects **ngoài transaction**, ví dụ @AfterTransaction.
- Với async listener, Kafka, HTTP hoặc queue side effects, commit của database không tự bảo đảm event delivery đồng bộ; cần synchronization/wait policy và cleanup tài nguyên ngoài DB.
- Một listener dùng REQUIRES_NEW có thể persist thêm rows khác; cần dọn cả những side effects đó.

### 16.4. Transaction commit có thể thất bại

Ví dụ unique constraint/foreign-key deferred error, optimistic conflict, deadlock hoặc rollback-only có thể phát sinh lúc flush hay commit. Test @Commit không có nghĩa sẽ luôn có committed row. Code cần assert được **expected success** hoặc **expected failure** ở đúng pha. Nếu lỗi chỉ xuất hiện khi commit, dùng TestTransaction.flagForCommit()/end() giúp đưa boundary vào thân @Test để kiểm tra exception trực tiếp, thay vì để nó xảy ra sau method khi listener cleanup.

## 17. HTTP integration tests: vì sao dữ liệu vẫn còn dù test có @Transactional?

Một test:

~~~java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class HttpIntegrationTest {
    // HTTP client gửi POST /events tới server.
}
~~~

Đây là trích đoạn. Khi HTTP client gửi request tới server thật:

~~~text
JUnit test thread:
    BEGIN test transaction
    HTTP POST /events --------------+
    wait response                    |
    ROLLBACK test transaction        |
                                     v
Servlet server thread:
    BEGIN service transaction
    INSERT row
    COMMIT service transaction
    HTTP 201 response
~~~

**Rollback ở test thread không rollback server transaction.** Nếu HTTP request tạo dữ liệu, @Transactional trên JUnit test còn có thể gây hiểu nhầm vì test đọc data bằng một connection/transaction khác. Đừng dùng nó làm cleanup duy nhất. Có thể dùng database riêng mỗi test, test-key và DELETE sau request, @Sql with isolated cleanup, Testcontainers per suite, hoặc API cleanup có authorization phù hợp.

**MockMvc không mở real socket**, thường cùng test thread nhưng behavior với async dispatch/security/transaction có thể phức tạp tùy setup. Không suy rộng test-managed transaction behavior từ MockMvc sang real HTTP server hoặc ngược lại. Chọn assertions tương ứng tầng đang test.

## 18. Dọn dữ liệu và test isolation: chọn cách phù hợp

| Cách quản lý data | Khi phù hợp | Ưu điểm | Rủi ro/cảnh báo |
| --- | --- | --- | --- |
| **Rollback mặc định** | JPA/JDBC repository test cùng test thread | Nhanh, tự cô lập DML trong test tx | Không rollback REQUIRES_NEW/async/HTTP side effects |
| **@BeforeTransaction + @AfterTransaction** | Cần assert sau rollback/commit và cleanup | Ranh giới rõ, test biết DB sau kết thúc | Viết hook dài, cleanup phải idempotent |
| **TestTransaction.end/start** | Cần xác minh commit trong thân @Test | Điều khiển lifecycle rõ | Dễ quên start lại, tạo commits ngoài ý định |
| **@Sql** | Fixtures/teardown SQL rõ ràng | Tái sử dụng scripts, kiểm soát datasets | TransactionMode và listener ordering phải hiểu |
| **Repository/JdbcTemplate cleanup ngoài transaction** | Test có committed rows | Dọn theo business/test key | Phải tránh xóa dữ liệu người khác |
| **Truncate/reset schema** | Database riêng cho từng test/suite | Cleanup rộng, ít stale residue | Không an toàn trên shared DB, FK constraints |
| **Testcontainers** | Muốn gần production DB và cô lập | Dialect/transaction behavior thực tế hơn H2 | Startup overhead và lifecycle |
| **Unique generated test keys** | Tests chạy parallel hoặc dùng chung context | Giảm collision và phụ thuộc thứ tự | Không thay cleanup nếu dữ liệu commit |
| **@DirtiesContext** | Muốn làm mới Spring bean/context state | Cô lập context cache | Không bảo đảm dọn committed database |
| **Sử dụng transaction độc lập cho seed** | Test đọc dữ liệu committed baseline | Chứng minh visibility từ connection khác | Baseline commit phải cleanup sau suite |

### Test-key và idempotent cleanup

Dùng KEY riêng cho mỗi test, như trong dự án, hoặc UUID có prefix để truy vấn đúng dữ liệu test. Một cleanup kiểu:

~~~sql
DELETE FROM audit_events WHERE event_key = ?;
~~~

thường an toàn hơn:

~~~sql
DELETE FROM audit_events;
~~~

trên DB có shared fixtures. Nếu xóa theo key đã tồn tại từ run trước, cleanup **idempotent**: zero-row DELETE cũng chấp nhận được. Tuy nhiên nếu test code tự tạo hơn một loại side effect (audit row, cache, message, file), hãy có cleanup cho **toàn bộ resource liên quan**, không chỉ bảng chính.

## 19. Kiểm tra thứ tự lifecycle mà không phụ thuộc test order

Một cách học trực quan là thêm log ở hooks:

~~~java
@BeforeTransaction
void beforeTx() { System.out.println("BEFORE_TX"); }

@BeforeEach
void beforeEach() { System.out.println("BEFORE_EACH"); }

@Test
void test() { System.out.println("TEST"); }

@AfterEach
void afterEach() { System.out.println("AFTER_EACH"); }

@AfterTransaction
void afterTx() { System.out.println("AFTER_TX"); }
~~~

Đây là trích đoạn minh họa **trong class @Transactional**; các methods không thuộc cây tệp runnable và cần JUnit/Spring imports. Các dòng được kỳ vọng theo lifecycle test method:

~~~text
BEFORE_TX
BEFORE_EACH
TEST
AFTER_EACH
AFTER_TX
~~~

Đây là **thứ tự logic được listener/JUnit thực hiện**, không phải bản log Gradle đã chạy. Các Spring TestExecutionListeners hoặc JUnit extensions khác có thể in thêm log chen giữa; thứ tự hooks nêu trên vẫn là mốc cần hiểu.

**Không dùng JUnit @TestMethodOrder để bảo đảm test B chỉ pass sau test A đã commit.** Mỗi test phải tự setup, assert và cleanup dữ liệu của mình. Nếu ứng dụng thực sự có một workflow nhiều bước, nên viết **một test method** điều khiển workflow hoặc dùng fixture độc lập với contract rõ, tránh phụ thuộc state được test khác để lại.

## 20. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm chứng và sửa |
| --- | --- | --- |
| @SpringBootTest test ghi DB rồi data còn sau test | Không có test @Transactional, hoặc side effect ở transaction khác | Xác nhận annotation, thread và service propagation |
| @DataJpaTest thấy row trong test nhưng test sau không thấy | Rollback mặc định | Đây là behavior mong muốn; dùng @Commit có cleanup nếu cần xác minh commit |
| @Commit mà @AfterEach query vẫn chưa chứng minh commit | @AfterEach chạy trước transaction kết thúc | Assert trong @AfterTransaction |
| @Commit chạy nhưng DB không còn row | Transaction rollback-only, commit fail, hoặc cleanup tự xóa trước commit | Kiểm tra logs và lifecycle, phân biệt side effects |
| Dùng @Rollback(false) nhưng không có @Transactional | Không có test transaction | Thêm @Transactional hoặc chọn test không transaction có cleanup khác |
| Test thất bại vì unique constraint ở run sau | Committed row từ run trước chưa cleanup | Idempotent pre-clean + post-clean, unique fixture keys |
| @AfterEach xóa row REQUIRES_NEW rồi row vẫn còn | DELETE tham gia outer test tx và bị rollback | Cleanup ngoài tx trong @AfterTransaction |
| JUnit test rollback nhưng async job vẫn ghi DB | Thread mới không tham gia test transaction | Wait job completion, cleanup riêng |
| HTTP RANDOM_PORT test rollback không dọn API rows | Server thread có tx riêng | Dùng cleanup ngoài transaction hoặc isolated database |
| @DirtiesContext nhưng DB data vẫn tồn tại | Context cache không phải database cleanup | Dùng DELETE/truncate/schema isolation |
| Entity save không ném constraint error | Hibernate chưa flush | saveAndFlush/entityManager.flush trong test |
| @Sql fixture không rollback như mong | Script dùng ISOLATED/committed transaction | Xem SqlConfig transactionMode và listener ordering |
| SQL cleanup xóa luôn dữ liệu test khác | Shared DB và DELETE không có WHERE | Key/namespace riêng, test DB độc lập |
| Test xanh riêng, fail cả suite | Context cache, committed rows, global state | Cleanup idempotent, không phụ thuộc thứ tự |
| @Transactional(readOnly=true) trên test tưởng ngăn write | Test listener không áp dụng readOnly như service | Kiểm tra supported attrs, dùng đúng layer |
| REQUIRES_NEW test commit ngoài ý muốn | Service transaction độc lập | Hiểu propagation, assert sau @AfterTransaction |
| Test dùng assertTimeoutPreemptively có data rò | Code chạy thread khác, mất test tx ThreadLocal | Tránh preemptive timeouts với transactional tests |
| Nhiều transaction managers, rollback sai DB | Listener chọn manager khác service | Chỉ định transactionManager và test multi-DB state |
| H2 PASS nhưng production transaction isolation khác | DB engine/dialect/isolation khác | Testcontainers engine gần production cho case quan trọng |

## 21. Bài tập tự kiểm tra

**1.** Một @DataJpaTest gọi saveAndFlush rồi countById trả 1. Sau method còn row không? **Mặc định không**; @DataJpaTest rollback. Cần @AfterTransaction hoặc transaction khác để quan sát kết quả sau rollback.

**2.** @SpringBootTest đơn thuần có tự rollback mọi test method không? **Không.** Thêm @Transactional nếu muốn test-managed transaction.

**3.** Đặt @Commit trên method không có @Transactional thì điều gì xảy ra? **Không tự tạo test transaction**; không có test-managed transaction để @Commit điều khiển.

**4.** @Commit và @Rollback(false) khác nhau về ý định commit test transaction không? **Không**: cả hai chọn commit; @Commit diễn đạt ngắn gọn hơn.

**5.** Class dùng @Commit, method dùng @Rollback. Policy nào áp dụng? **Method-level @Rollback**, nên test transaction rollback.

**6.** @AfterEach có được gọi sau rollback của test không? **Không.** Với transactional test, nó thường chạy trước khi listener rollback/commit.

**7.** @AfterTransaction có thể kiểm tra row đã commit không? **Có**, vì hook chạy sau transaction kết thúc và có thể query bằng connection ngoài test transaction.

**8.** Service @Transactional(REQUIRES_NEW) insert và commit. Outer test @Transactional cuối method rollback. Row nội bộ có biến mất không? **Không**, REQUIRES_NEW commit độc lập.

**9.** Trong @Transactional test, TestTransaction.flagForCommit() rồi end(). Dữ liệu có thể được đọc ngoài transaction chưa? **Có**, nếu commit thành công và điều kiện visibility cho phép; đó là mục đích của API.

**10.** Sau TestTransaction.end() gọi repository.save() mà chưa start() lại, có còn test rollback bảo vệ không? **Không nên giả định**; đang ngoài test-managed transaction.

**11.** @DirtiesContext có dọn committed rows trên DB ngoài không? **Không bảo đảm**; nó chủ yếu quản lý Spring ApplicationContext cache.

**12.** @Transactional JUnit test gửi HTTP POST tới embedded server RANDOM_PORT. Có chắc rollback DB writes của request không? **Không**, server xử lý transaction khác.

**13.** Dùng assertTimeoutPreemptively với Spring @Transactional test có rủi ro gì? Body chạy thread khác, các DB writes có thể không tham gia test transaction và bị commit.

**14.** Tại sao cần flush trong JPA test trước khi khẳng định không có constraint error? Bởi lỗi có thể chỉ xuất hiện lúc Hibernate gửi SQL trong flush/commit.

**15.** Dọn dữ liệu ở @BeforeTransaction có thay cho @AfterTransaction không? **Không hoàn toàn**. Preclean bảo vệ lần chạy lại, còn postclean giữ suite sạch ngay sau test.

**16.** Test muốn kiểm tra AFTER_COMMIT listener. Rollback mặc định có chạy listener này không? **Không**; cần actual commit và assert đúng thời điểm.

### Checklist trước khi chốt QA

- Test có thực sự được **@Transactional** ở class/method hoặc bởi @DataJpaTest không?
- Có đúng **PlatformTransactionManager** cho datasource cần kiểm tra?
- Mặc định rollback đã được hiểu; @Commit/@Rollback(false) chỉ dùng khi thật sự cần?
- Có phân biệt **@BeforeEach/@AfterEach trong tx** với **@BeforeTransaction/@AfterTransaction ngoài tx**?
- Có flush để phát hiện SQL/constraint/lifecycle errors trong JPA?
- Có quan sát data sau commit/rollback ở đúng phase, không chỉ count trong transaction?
- Nếu @Commit, có unique test key, preclean và cleanup bằng finally ở ngoài transaction?
- Có test method override class-level transaction policy đúng annotation?
- Khi dùng TestTransaction.end/start, có biết transaction nào active và kết thúc theo cờ nào?
- Service REQUIRES_NEW, @Async và real HTTP server có side effects ngoài test rollback không?
- @Sql fixtures, SqlConfig.ISOLATED và scripts teardown được hiểu đúng transaction mode?
- @DirtiesContext không bị dùng thay database cleanup?
- Có tránh preemptive timeout thay thread, vốn làm mất test-managed transaction?
- Có không phụ thuộc JUnit test order hoặc fixed shared IDs?
- Có database test cô lập và không có nguy cơ dọn dữ liệu production?
- Nếu behavior phụ thuộc DB isolation/locking/constraints, có integration test trên DB engine production?

**Kết luận:** **@Rollback** quyết định hủy test-managed transaction; **@Commit** và **@Rollback(false)** cho phép commit; cả ba chỉ có ý nghĩa trong đúng bối cảnh transaction do Spring TestContext quản lý. Muốn xác nhận trạng thái sau test, dùng **@AfterTransaction** hoặc **TestTransaction.end()**, và cleanup committed data **ngoài transaction sẽ bị rollback**. Một bộ test tốt vừa chứng minh CRUD đúng, vừa bảo đảm test khác không bị ô nhiễm bởi REQUIRES_NEW, HTTP requests, @Async jobs hay committed fixtures.

## Tài liệu chính thức

- Spring Framework 6.2 — TestContext Transaction Management, @Rollback/@Commit, hooks và TestTransaction: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — Integration Testing: https://docs.spring.io/spring-framework/reference/6.2/testing/integration.html
- Spring Boot 3.4 — @DataJpaTest API: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Framework — @Sql và SQL scripts trong TestContext: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html
- Spring Framework — TestTransaction Javadoc: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
