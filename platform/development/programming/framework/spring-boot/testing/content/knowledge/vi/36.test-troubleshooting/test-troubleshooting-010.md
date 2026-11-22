# Database constraint chỉ lỗi sau flush hoặc commit

Một bài test Spring Data JPA gọi `repository.save(entity)` và không nhận exception; developer kết luận dữ liệu hợp lệ. Nhưng khi request đi qua service `@Transactional` trên production, transaction kết thúc và database trả lỗi unique, foreign key hoặc check constraint. Một tình huống khác nguy hiểm hơn: test `@DataJpaTest` chạy xanh vì mặc định **rollback**, trong khi deployment thật **commit** và constraint được khai báo **DEFERRABLE INITIALLY DEFERRED** chỉ bị kiểm ở cuối transaction.

Bài Knowledge **“Database constraint chỉ lỗi sau flush hoặc commit”** thuộc nhóm **Chẩn đoán lỗi kiểm thử** của module **Spring Boot – testing**. Ta sẽ hiểu chính xác các mốc **persist/save → pending SQL → flush → database statement check → commit**, rồi thiết kế các test biết *mình đang kiểm ở mốc nào*. Trọng tâm là chẩn đoán thời điểm lỗi, không chỉ học cách thêm `assertThrows`.

Bài dùng **Java 17+, Spring Boot 3.5.16, Spring Data JPA, Hibernate 6.x, JUnit Jupiter 5, H2** cho ví dụ chạy không cần Docker; bổ sung **PostgreSQL 17** trong phần thí nghiệm riêng để thấy constraint thực sự trì hoãn tới commit. H2 demo xác minh lỗi unique ở **flush**; ví dụ PostgreSQL dùng `DEFERRABLE INITIALLY DEFERRED` để minh họa lỗi có thể đợi **commit dù đã flush**. Các ví dụ đều nói rõ lớp nào được kiểm và nơi cần database thật.

**Thông điệp cần nhớ:** `save()` không đồng nghĩa đã gửi SQL, `flush()` không đồng nghĩa đã commit, và transaction rollback trong test không kiểm chứng đầy đủ một constraint được xét ở commit. Nhưng không nên nói “mọi constraint chỉ lỗi ở commit”: thời điểm phụ thuộc **JPA provider, ID generator, flush mode, SQL execution, loại constraint, DDL và database**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt entity managed/pending changes, SQL execution, flush, commit và rollback.
- Hiểu Hibernate **transactional write-behind** và vì sao `repository.save` có thể chưa chạy INSERT.
- Biết `JpaRepository.flush()`, `saveAndFlush()` và `EntityManager.flush()` thực sự làm gì.
- Phân biệt lỗi do JPA/Bean Validation, database constraint immediate và constraint deferred của PostgreSQL.
- Hiểu vì sao `GenerationType.IDENTITY` có thể chạy INSERT sớm hơn `UUID/SEQUENCE` và làm timing test thay đổi.
- Giải thích `FlushModeType.AUTO`, `COMMIT`, một số query-triggered flush và batching.
- Kiểm unique violation với `@DataJpaTest` và `assertThrows` ở **đúng lời gọi flush**.
- Không dùng `assertDoesNotThrow(repository::save)` để kết luận unique constraint đã được thử.
- Biết test commit bằng `TransactionTemplate` khi test method không bị bọc test-managed transaction.
- Biết `@DataJpaTest` mặc định rollback và vì sao điều đó có thể che lỗi commit-time.
- Hiểu `TestTransaction.flagForCommit()/end()` là một lựa chọn khi cần thử commit trong test transaction.
- Phân biệt exception ở repository proxy, service transaction proxy và HTTP controller boundary.
- Không swallow persistence exceptions trong một transaction đã marked rollback-only rồi cố trả thành công.
- Biết các SQLSTATE như PostgreSQL `23505` (unique), `23503` (foreign key), `23502` (not null), `23514` (check).
- Thiết kế application error mapping an toàn, không biến mọi `DataIntegrityViolationException` thành “email trùng”.
- Dùng SQL logs và constraint name để điều tra, nhưng không dựa vào exact localized error message.
- Kiểm dữ liệu cuối cùng sau rollback/commit bằng query ở transaction mới, không chỉ xem managed entity.
- Chọn H2 slice test hay PostgreSQL Testcontainers theo constraint semantics thực.
- Nhận biết các sai lầm về transaction rollback, query auto-flush, test data isolation và concurrent writes.

## 2. Dòng thời gian: bốn trạng thái dễ bị nhập nhằng

```text
HTTP POST /accounts
  |
  v
@Transactional service
  |
  +-- repository.save(new CustomerAccount(...))
  |      - entity được quản lý trong persistence context
  |      - INSERT có thể CHƯA được gửi
  |
  +-- repository.flush() hoặc saveAndFlush()
  |      - Hibernate thực thi pending SQL
  |      - immediate DB constraints thường được kiểm ngay
  |      - transaction CHƯA commit
  |
  +-- service method body returns
  |
  +-- transaction proxy chuẩn bị COMMIT
  |      - có thể auto-flush phần pending
  |      - database có thể kiểm deferred constraints ở COMMIT
  |
  +-- COMMIT success -> thay đổi visible theo isolation
         hoặc COMMIT fails -> rollback/error to caller
```

Lỗi “chỉ hiện khi flush hoặc commit” thường không có gì thần bí: trước đó **chưa có SQL gây vi phạm được thực thi**, hoặc database đã nhận SQL nhưng đang **trì hoãn kiểm constraint** đến khi transaction kết thúc.

**Không đồng nhất flush và commit:**

- `flush()` đồng bộ pending changes bằng SQL trong transaction hiện có.
- `commit()` kết thúc transaction thành công; trước commit có thể cần flush.
- Dữ liệu đã flush **vẫn có thể rollback**.
- Constraint immediate thường được kiểm khi statement chạy, không nhất thiết khi transaction commit.
- PostgreSQL constraint **deferrable** ở chế độ deferred có thể đợi commit dù insert và flush đã hoàn thành.
- Cơ chế này khác exception từ Bean Validation xảy ra trước SQL.

## 3. Ba trường hợp cùng một hành vi bề ngoài

| Mô tả | Nguyên nhân thật | Mốc phát hiện |
|---|---|---|
| `save` trả bình thường, `flush` ném lỗi unique | Hibernate hoãn INSERT; DB có unique thường | Khi SQL INSERT chạy trong flush |
| `saveAndFlush` trả bình thường, `commit` ném unique | PostgreSQL constraint đang DEFERRED | Khi database kiểm ở COMMIT |
| `save` ném lỗi ngay | IDENTITY cần INSERT lấy id, JPA validation hoặc SQL phát sinh sớm | Trong save/persist/SQL trước flush tường minh |

Vì vậy test nên ghi *“với entity mapping và provider/DB hiện tại, lỗi xuất hiện ở mốc X”*, không đưa ra quy tắc universal rằng mọi `save` không thể ném lỗi.

### 3.1. Mục tiêu QA khác nhau

- **Test mapping/constraint tồn tại:** gây dữ liệu vi phạm và bắt exception ở flush/commit theo DDL.
- **Test service contract:** caller của service transactional nhận lỗi nghiệp vụ/phản hồi HTTP đúng.
- **Test transaction correctness:** thất bại phải rollback mọi thay đổi thuộc transaction.
- **Test concurrency:** hai transactions đồng thời không tạo duplicate dù application có `existsByEmail` precheck.
- **Test DB fidelity:** dùng đúng PostgreSQL/Oracle/MySQL và migrations khi kiểm constraint-specific semantics.

## 4. JPA persistence context không phải database table

`EntityManager` quản lý entity instances, identity map, snapshots và pending actions. Một `repository.save` thường dùng `EntityManager.persist` cho entity mới hoặc `merge` cho entity đã tồn tại; nó đưa object vào trạng thái được quản lý trong persistence context. Hibernate có thể trì hoãn INSERT/UPDATE/DELETE để batch hoặc sắp thứ tự.

Ví dụ khái niệm:

```java
@Transactional
public void registerTwice() {
    repo.save(new CustomerAccount("duplicate@example.test"));
    repo.save(new CustomerAccount("duplicate@example.test"));

    // Đến đây có thể chưa có SQL INSERT thứ hai.
    // Không có exception KHÔNG chứng minh constraint chấp nhận.
}
// Khi proxy commit: Hibernate auto-flush, DB có thể báo unique.
```

Đây chỉ là snippet giả định `repo` đã được inject. Trong project đầy đủ bên dưới, `CustomerAccount` dùng ID `UUID` được Hibernate tạo trước khi INSERT, nhờ vậy test có thể quan sát việc hai lệnh `save` hoàn thành trước khi SQL constraint nổ lúc commit. Với `IDENTITY`, câu chuyện có thể khác.

### 4.1. “Dữ liệu thấy được qua entity” không phải bằng chứng đã lưu

Sau `entity.setEmail(...)`, gọi `entity.getEmail()` trả giá trị mới là điều hiển nhiên trong RAM. `EntityManager.find(...)` trong cùng persistence context cũng có thể trả lại cùng managed entity qua first-level cache. Muốn kiểm database state:

1. Thực hiện flush khi cần SQL.
2. `entityManager.clear()` để loại first-level-cache state.
3. Query lại trong transaction phù hợp.
4. Với yêu cầu commit thực, kết thúc transaction thành công rồi query từ transaction mới.
5. Không bỏ qua lỗi xảy ra ngay ở commit/cleanup.

## 5. Hibernate flush là gì và khi nào xảy ra?

Hibernate `flush` là quá trình đồng bộ trạng thái persistence context xuống SQL statements. Với flush mode thường dùng `AUTO`, flush có thể xảy ra:

- Khi gọi `entityManager.flush()` hoặc repository `flush()` rõ ràng.
- Trước transaction commit.
- Trước một số JPQL/HQL queries mà dữ liệu truy vấn giao với bảng có pending changes.
- Trước một số native SQL queries, tùy cách bootstrapping và registered synchronization/query spaces.
- Do một số API/generator buộc SQL sớm hơn.

Không cam kết “Hibernate chỉ flush lúc commit”. Một dòng `repository.count()` hoặc JPQL query có thể vô tình trigger flush, khiến exception xuất hiện **sớm hơn đoạn code người viết nghĩ**.

### 5.1. FlushModeType.AUTO và COMMIT

```java
entityManager.setFlushMode(FlushModeType.AUTO);
// Cho phép provider flush trước query khi cần và trước commit.

entityManager.setFlushMode(FlushModeType.COMMIT);
// Hibernate thường trì hoãn query-triggered flush cho đến commit.
```

Đây là snippet, cần import `jakarta.persistence.FlushModeType` và có `EntityManager` hợp lệ. Với JPA `COMMIT`, việc pending changes có hiển thị qua queries trước commit là **không được bảo đảm thống nhất**. Đừng đặt flush mode chỉ để ép một test nổ ở commit nếu production dùng AUTO; hãy test đúng config runtime và nêu kỳ vọng.

**Không tự đổi sang MANUAL** để “tắt exception”: manual flush có thể khiến thay đổi không được gửi ở mốc mong muốn. Nguyên nhân lỗi constraint vẫn phải được xử lý ở dữ liệu, DDL và transaction boundary.

## 6. `save`, `saveAndFlush`, `flush` và `saveAllAndFlush`

| API | Tác dụng chính | Có tự commit toàn service transaction không? |
|---|---|---|
| `repository.save(entity)` | Persist/merge entity | **Không** nếu tham gia outer transaction |
| `repository.flush()` | Đẩy pending changes qua JPA provider | **Không** |
| `repository.saveAndFlush(entity)` | Save entity rồi flush | **Không** |
| `repository.saveAllAndFlush(entities)` | Save nhiều rồi flush | **Không** |
| `entityManager.flush()` | Đồng bộ persistence context | **Không** |
| `transactionManager.commit(...)` | Kết thúc transaction | **Có**, có thể phải flush trước |
| `TransactionTemplate.execute(...)` | Chạy callback trong transaction, commit sau callback | Commit ở ranh giới execute, hoặc rollback lỗi |

**Cảnh báo ngoài transaction:** Spring Data repository methods có transaction attributes riêng. Gọi `saveAndFlush` từ controller **không có outer transaction** có thể làm repository transaction riêng kết thúc trước khi method controller trở về. Đừng viết test giả định “saveAndFlush chỉ flush không commit” mà không nói **nó đang tham gia transaction nào**.

Trong ví dụ core, `AccountService.register` có `@Transactional`; `saveAndFlush` của repository tham gia cùng service transaction nên exception immediate xảy ra khi flush, còn commit do service proxy thực hiện sau method body.

## 7. ID generation làm thay đổi thời điểm INSERT

Hibernate có nhiều generator:

- `GenerationType.IDENTITY` thường phải INSERT sớm để lấy khóa ID từ database, nên lỗi unique có thể xảy ra ngay khi `persist/save`.
- `GenerationType.SEQUENCE` có thể lấy sequence value trước nhưng trì hoãn INSERT.
- `GenerationType.UUID` trên Hibernate có thể tạo UUID phía Java trước khi INSERT, phù hợp lab quan sát pending insert.
- Assigned ID có thể khiến Spring Data `save` chọn `merge` thay vì `persist` nếu không cấu hình isNew/version; điều đó ảnh hưởng SELECT/SQL và kết luận timing.
- Hibernate JDBC batching cũng có thể thay đổi thời điểm statements được gửi, nhưng không thay định nghĩa constraint/transaction.

**Không xây test timing phụ thuộc một cách vô thức vào generator.** Mẫu dùng `@GeneratedValue(strategy = GenerationType.UUID)` với Java `UUID` để thấy hai `save` trước flush trong Hibernate 6.x. Nếu đổi sang IDENTITY, cần đánh giá lại expected exception location.

## 8. Các loại constraint và lỗi có thể xuất hiện lúc nào

| Constraint | Ví dụ | Thời điểm thông thường |
|---|---|---|
| `UNIQUE` | email không trùng | Statement thực thi hoặc commit nếu deferrable-deferred |
| `PRIMARY KEY` | id không trùng | Statement hoặc commit nếu DB hỗ trợ deferrable |
| `FOREIGN KEY` | order.customer_id phải tồn tại | Statement hoặc commit nếu FK deferrable-deferred |
| `NOT NULL` | email không null | Thường khi statement; Hibernate có thể chặn trước SQL |
| `CHECK` | quantity > 0 | Thường khi statement; PostgreSQL CHECK không deferrable |
| Application validation | `@Email`, `@NotNull`/business rule | Trước SQL, khi validate |
| Optimistic locking | `@Version` stale update | Khi update/flush hoặc commit sync |
| Trigger-defined constraint | Business validation trong trigger | Khi trigger chạy, tùy trigger DB |

Trên PostgreSQL, không phải constraint nào cũng hỗ trợ `DEFERRABLE`: **UNIQUE, PRIMARY KEY, EXCLUDE và FOREIGN KEY** có hỗ trợ; **NOT NULL và CHECK không có loại deferred tương ứng** trong `CREATE TABLE`. Ngoài ra PostgreSQL có deferrable constraint trigger, nhưng đó là cơ chế khác cần DDL/test riêng.

### 8.1. SQLSTATE hữu ích hơn chuỗi message

Trong PostgreSQL, một số mã chuẩn:

| SQLSTATE | Ý nghĩa phổ biến |
|---|---|
| `23505` | unique_violation |
| `23503` | foreign_key_violation |
| `23502` | not_null_violation |
| `23514` | check_violation |
| `23P01` | exclusion_violation |
| `40001` | serialization_failure |
| `40P01` | deadlock_detected |

Các mã này giúp phân loại, nhưng **SQLSTATE của một lỗi không luôn đủ xác định chính xác constraint nghiệp vụ**: `23505` có thể là email, username hoặc primary key. Production code nên xem constraint name đáng tin từ driver/Hibernate hoặc một mapping rõ ràng; tránh trả “EMAIL_ALREADY_USED” cho mọi unique failure trong hệ thống.

## 9. Bean Validation khác database constraint

Một entity có:

```java
@NotBlank
@Column(nullable = false)
private String email;
```

có **hai lớp** kiểm tra khác nhau:

1. Bean Validation (`jakarta.validation.constraints.NotBlank`) chạy khi validation được kích hoạt, có thể trong lifecycle pre-persist/update, với `jakarta.validation.ConstraintViolationException`.
2. `@Column(nullable=false)` tham gia metadata/schema và Hibernate nullability checks; database `NOT NULL` thực tế là tuyến bảo vệ cuối, có thể phát sinh `SQLException`.

**Hai exception tên gần giống nhưng không đồng nhất:**

- `jakarta.validation.ConstraintViolationException`: Bean Validation, danh sách violations.
- `org.hibernate.exception.ConstraintViolationException`: Hibernate database/JDBC integrity violation.
- `org.springframework.dao.DataIntegrityViolationException`: Spring DataAccessException translation category, có thể wrap Hibernate/JDBC cause.

Nếu muốn chứng minh **database** chặn dữ liệu null/check, cần test DDL/driver/JDBC ở DB phù hợp, không chỉ assert `@NotBlank` bắt lỗi trước SQL. Không thêm Bean Validation vào demo unique H2 rồi vô tình khiến test không chạm tới database.

## 10. SQL constraint có thể khác giữa H2 và PostgreSQL

H2 rất hữu ích cho JPA mapping/repository tests chạy nhanh, nhưng có khác biệt về:

- Dialect SQL, index names, execution plans và generated DDL.
- Locking/isolation, concurrency, transaction semantics.
- Sequence/identity behavior, timestamps, case/collation.
- Partial indexes, expression indexes, materialized views.
- PostgreSQL `DEFERRABLE INITIALLY DEFERRED` và `SET CONSTRAINTS`.
- Constraint names/exception wrapping/driver messages.
- Trigger/stored procedures, migrations và schema permissions.

**Không viết một H2 test rồi kết luận commit-time deferred constraint của PostgreSQL đã được kiểm.** Core demo H2 kiểm **flush-time immediate unique**; phần PostgreSQL riêng thực hiện transaction/commit thực trên provider đúng.

## 11. Project runnable: tạo tài khoản có email duy nhất

Ứng dụng demo cung cấp:

- `POST /api/accounts` với body `{"email":"Alice@Example.test"}`.
- Email được `strip()` và lowercase với `Locale.ROOT`, nên hai biến thể chữ hoa/thừa khoảng trắng có cùng canonical email.
- Email rỗng/không chứa dấu @ hợp lệ theo rule đơn giản của demo → HTTP `400`.
- Email mới → HTTP `201` với `id` UUID và `email` đã chuẩn hóa.
- Email trùng → JDBC unique violation, service phân loại `SQLSTATE 23505` rồi ném `DuplicateEmailException` để HTTP advice trả **409**.
- Các integrity errors khác không bị giả thành “email trùng”.
- Có unique constraint `uk_customer_accounts_email` trên bảng `customer_accounts`.
- Bài không dùng `repository.existsByEmail()` làm biện pháp bảo đảm uniqueness; DB constraint mới là quyết định cuối.

Lưu ý: Regex/email validation đơn giản ở demo **không phải bộ kiểm RFC-compliant hoặc kiểm quyền sở hữu email**. Chỉ tập trung vào việc database constraint được phát hiện lúc flush/commit.

### 11.1. Cây thư mục

```text
jpa-constraint-timing/
  settings.gradle
  build.gradle
  src/main/java/com/example/constrainttiming/
    ConstraintTimingApplication.java
    CustomerAccount.java
    CustomerAccountRepository.java
    AccountService.java
    RegisterAccountRequest.java
    AccountCreated.java
    InvalidEmailException.java
    DuplicateEmailException.java
    AccountController.java
    ApiErrorAdvice.java
  src/test/resources/
    application.properties
  src/test/java/com/example/constrainttiming/
    AccountServiceTest.java
    CustomerAccountRepositoryFlushTest.java
    CustomerAccountCommitBoundaryTest.java
    AccountHttpIntegrationTest.java
```

Core tests không yêu cầu PostgreSQL hoặc Docker. Với PostgreSQL deferrable unique, xem SQL riêng ở mục 29 và tùy chọn kết hợp Testcontainers ở mục 30.

## 12. Gradle và test properties

**`settings.gradle`**

```groovy
rootProject.name = 'jpa-constraint-timing'
```

**`build.gradle`**

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
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/test/resources/application.properties`**

```properties
spring.datasource.generate-unique-name=true
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false

# Bật khi cần chẩn đoán SQL cụ thể (không bắt buộc):
# logging.level.org.hibernate.SQL=DEBUG
# logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Với H2 training database, `create-drop` tạo schema theo annotations. **Không dùng `ddl-auto=create-drop` trên production database.** Dự án thực dùng migrations Flyway/Liquibase, và tests tích hợp phải áp chính migration ấy. Logging bind parameters có thể tiết lộ email/dữ liệu nhạy cảm, chỉ bật trong test với dữ liệu synthetic.

## 13. Spring Boot application

**`src/main/java/com/example/constrainttiming/ConstraintTimingApplication.java`**

```java
package com.example.constrainttiming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConstraintTimingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ConstraintTimingApplication.class, args);
    }
}
```

`@SpringBootApplication` ở package gốc bảo đảm Spring Boot quét JPA entity/repository/controller/service đúng namespace. Test `@DataJpaTest` chỉ tạo JPA slice, không nạp toàn bộ web/controller.

## 14. Entity với ID UUID và unique constraint

**`src/main/java/com/example/constrainttiming/CustomerAccount.java`**

```java
package com.example.constrainttiming;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
        name = "customer_accounts",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_customer_accounts_email",
                columnNames = "email"))
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, length = 160)
    private String email;

    protected CustomerAccount() {
        // Required by JPA
    }

    public CustomerAccount(String email) {
        this.email = email;
    }

    public UUID getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

**Lý do chọn UUID:** Hibernate có thể gán ID ở Java side để `save` không cần gửi INSERT ngay chỉ để lấy generated primary key. Vì vậy lab so sánh save/flush/commit rõ hơn. Nếu thay bằng IDENTITY, SQL có thể chạy sớm; test nên xác minh behavior của generator thật, không ép kết luận ban đầu.

**Quan trọng:** `@Table(uniqueConstraints=...)` trong demo được Hibernate schema generation sử dụng. Với production migrations, đừng chỉ tin annotation: kiểm bảng thật có constraint name/columns/mode đúng. Với composite unique hoặc partial index, cần DDL và test chi tiết hơn.

## 15. Repository, DTOs và domain exceptions

**`src/main/java/com/example/constrainttiming/CustomerAccountRepository.java`**

```java
package com.example.constrainttiming;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, UUID> {

    Optional<CustomerAccount> findByEmail(String email);

    long countByEmail(String email);
}
```

**`src/main/java/com/example/constrainttiming/RegisterAccountRequest.java`**

```java
package com.example.constrainttiming;

public record RegisterAccountRequest(String email) {
}
```

**`src/main/java/com/example/constrainttiming/AccountCreated.java`**

```java
package com.example.constrainttiming;

import java.util.UUID;

public record AccountCreated(UUID id, String email) {
}
```

**`src/main/java/com/example/constrainttiming/InvalidEmailException.java`**

```java
package com.example.constrainttiming;

public class InvalidEmailException
        extends IllegalArgumentException {
}
```

**`src/main/java/com/example/constrainttiming/DuplicateEmailException.java`**

```java
package com.example.constrainttiming;

public class DuplicateEmailException
        extends RuntimeException {

    public DuplicateEmailException(Throwable cause) {
        super("Email address already exists", cause);
    }
}
```

`DuplicateEmailException` là lỗi nghiệp vụ công khai; cause gốc vẫn ở server logs có kiểm soát, không serialize cause/raw SQL/absolute paths ra response. Khi SQLSTATE không phải `23505`, demo không tự chuyển thành email conflict.

## 16. Service: chủ động flush để bắt immediate unique đúng boundary

**`src/main/java/com/example/constrainttiming/AccountService.java`**

```java
package com.example.constrainttiming;

import java.sql.SQLException;
import java.util.Locale;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    private final CustomerAccountRepository repository;

    public AccountService(CustomerAccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public AccountCreated register(String email) {
        String normalized = normalize(email);

        try {
            CustomerAccount saved = repository.saveAndFlush(
                    new CustomerAccount(normalized));

            // DB immediate constraint has been checked by the flush.
            // The enclosing service transaction has NOT committed yet.
            return new AccountCreated(
                    saved.getId(), saved.getEmail());

        } catch (DataIntegrityViolationException failure) {
            if (hasSqlState(failure, "23505")) {
                // Throw a new RuntimeException so Spring rolls back.
                throw new DuplicateEmailException(failure);
            }
            throw failure;
        }
    }

    private String normalize(String email) {
        if (email == null) {
            throw new InvalidEmailException();
        }

        String value = email.strip()
                .toLowerCase(Locale.ROOT);

        // Deliberately simple training validation, not RFC email parsing.
        if (value.isEmpty() || value.length() > 160
                || value.indexOf('@') < 1
                || value.endsWith("@")) {
            throw new InvalidEmailException();
        }

        return value;
    }

    private boolean hasSqlState(
            Throwable throwable, String state) {

        for (Throwable cause = throwable;
             cause != null;
             cause = cause.getCause()) {

            if (cause instanceof SQLException sql
                    && state.equals(sql.getSQLState())) {
                return true;
            }
        }

        return false;
    }
}
```

**Vì sao bắt ngay sau `saveAndFlush`?** Với unique immediate của H2, INSERT chạy khi flush, repository proxy dịch lỗi DB sang `DataIntegrityViolationException`. Service phân loại SQLSTATE 23505 rồi ném domain exception. Transaction của service bị rollback vì unchecked exception. Controller advice sau đó có thể map 409.

**Giới hạn cố ý:** Dựa riêng vào SQLSTATE `23505` không xác định unique constraint nào gây lỗi. Trong demo bảng chỉ có một unique business constraint (email), nên mapping có thể dùng để học. Trong production, nên inspect **tên constraint đáng tin** qua Hibernate/driver (với fallback an toàn) hoặc dùng constraint-specific operation/exception mapping; không biến mọi 23505 (cả primary key) thành email duplicate.

**Quan trọng với PostgreSQL deferred constraints:** `saveAndFlush` có thể **không ném lỗi** với `DEFERRABLE INITIALLY DEFERRED`. Lỗi commit sẽ xảy ra **sau khi method body return**, do Spring transaction interceptor/proxy, nên catch ở trên **không nhất thiết bắt được**. Với deferred constraints, cần error mapping tại boundary bao quanh transaction execution (controller advice hoặc orchestration outside transaction) và integration test commit thật; xem mục 28–31.

### 16.1. Đừng swallow exception rồi tiếp tục commit

Phản ví dụ:

```java
@Transactional
public boolean registerAndIgnore(String email) {
    try {
        repository.saveAndFlush(new CustomerAccount(email));
        return true;
    } catch (DataIntegrityViolationException ignored) {
        return false; // Transaction may already be marked rollback-only.
    }
}
```

Sau database failure, JDBC transaction (đặc biệt PostgreSQL) có thể bị aborted; Spring transaction cũng có thể marked rollback-only. Tiếp tục query/commit có thể ném `UnexpectedRollbackException` hoặc SQL errors khác. Hãy thiết kế **transaction boundary rõ và exception propagate**, hoặc xử lý retry ở một **transaction mới** ngoài transaction đang lỗi, có idempotency và giới hạn attempts.

## 17. Controller và HTTP advice

**`src/main/java/com/example/constrainttiming/AccountController.java`**

```java
package com.example.constrainttiming;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<AccountCreated> register(
            @RequestBody RegisterAccountRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.register(request.email()));
    }
}
```

**`src/main/java/com/example/constrainttiming/ApiErrorAdvice.java`**

```java
package com.example.constrainttiming;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {

    public record ApiError(String code) {
    }

    @ExceptionHandler(InvalidEmailException.class)
    public ResponseEntity<ApiError> invalidEmail() {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_EMAIL"));
    }

    @ExceptionHandler(DuplicateEmailException.class)
    public ResponseEntity<ApiError> duplicateEmail() {
        return ResponseEntity.status(409)
                .body(new ApiError("EMAIL_CONFLICT"));
    }
}
```

**Phân biệt thời điểm:** Controller gọi `service.register(...)` qua Spring proxy. Đối với transaction do service tạo, proxy chỉ trả quyền điều khiển về controller sau khi transaction completion thành công. Nếu commit thất bại, controller không nhận `AccountCreated` bình thường. HTTP 201 chỉ nên được gửi sau service call thành công; mẫu này không dùng asynchronous fire-and-forget writes.

Mẫu advice chỉ map domain exceptions. Nếu deferred constraint ném `TransactionSystemException` / `DataIntegrityViolationException` ở commit, mapping 409 có thể cần được thiết kế tại boundary bên ngoài transaction và dựa trên error classification đáng tin — không giả định mã trên đã xử lý mọi commit-time variant.

## 18. Unit test cho normalization và error classification

**`src/test/java/com/example/constrainttiming/AccountServiceTest.java`**

```java
package com.example.constrainttiming;

import java.sql.SQLException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AccountServiceTest {

    @Mock
    CustomerAccountRepository repository;

    AccountService service;

    @BeforeEach
    void setUp() {
        service = new AccountService(repository);
    }

    @Test
    void normalizesEmailBeforeSave() {
        when(repository.saveAndFlush(any(CustomerAccount.class)))
                .thenAnswer(call -> call.getArgument(0));

        AccountCreated result = service.register(
                "  Alice@Example.test  ");

        ArgumentCaptor<CustomerAccount> saved =
                ArgumentCaptor.forClass(CustomerAccount.class);
        verify(repository).saveAndFlush(saved.capture());

        assertEquals("alice@example.test", result.email());
        assertEquals(
                "alice@example.test", saved.getValue().getEmail());
        // ID generation is not run in a Mockito-only unit test.
    }

    @Test
    void invalidEmailNeverCallsRepository() {
        assertThrows(InvalidEmailException.class,
                () -> service.register("  "));

        verifyNoInteractions(repository);
    }

    @Test
    void uniqueSqlStateBecomesDomainConflict() {
        DataIntegrityViolationException duplicate =
                new DataIntegrityViolationException(
                        "integrity failure",
                        new SQLException("duplicate", "23505"));

        when(repository.saveAndFlush(any(CustomerAccount.class)))
                .thenThrow(duplicate);

        DuplicateEmailException error = assertThrows(
                DuplicateEmailException.class,
                () -> service.register("same@example.test"));

        assertEquals(duplicate, error.getCause());
    }

    @Test
    void foreignKeySqlStateDoesNotBecomeEmailConflict() {
        DataIntegrityViolationException other =
                new DataIntegrityViolationException(
                        "integrity failure",
                        new SQLException("missing parent", "23503"));

        when(repository.saveAndFlush(any(CustomerAccount.class)))
                .thenThrow(other);

        assertThrows(DataIntegrityViolationException.class,
                () -> service.register("other@example.test"));
    }
}
```

**4 unit tests** không khởi Spring context hoặc DB. Chúng kiểm canonicalization, reject invalid input và classify lỗi theo SQLSTATE trong cause chain. Chúng **không chứng minh H2/PostgreSQL thực sự phát SQLSTATE ấy**, vì SQLException đã được Mockito tạo sẵn. Đó là trách nhiệm JPA/DB tests tiếp theo.

**Lưu ý ID:** Mockito trả lại entity không qua Hibernate, `getId()` có thể null; unit test không assert ID generated. Integration JPA/HTTP mới bảo đảm UUID được tạo.

## 19. Repository slice test: unique violation lộ lúc flush

**`src/test/java/com/example/constrainttiming/CustomerAccountRepositoryFlushTest.java`**

```java
package com.example.constrainttiming;

import jakarta.persistence.EntityManager;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
class CustomerAccountRepositoryFlushTest {

    @Autowired
    CustomerAccountRepository repository;

    @Autowired
    EntityManager entityManager;

    @Test
    void validAccountIsQueryableAfterFlushAndClear() {
        String email = "ok-" + UUID.randomUUID()
                + "@example.test";

        CustomerAccount saved = repository.save(
                new CustomerAccount(email));

        assertNotNull(saved.getId());

        repository.flush();
        entityManager.clear();

        assertEquals(email, repository.findById(saved.getId())
                .orElseThrow().getEmail());
    }

    @Test
    void twoSavesMayFinishBeforeUniqueFailureAtFlush() {
        String email = "duplicate-" + UUID.randomUUID()
                + "@example.test";

        CustomerAccount first = repository.save(
                new CustomerAccount(email));
        CustomerAccount second = repository.save(
                new CustomerAccount(email));

        // UUIDs were assigned before the pending INSERTs.
        assertNotNull(first.getId());
        assertNotNull(second.getId());

        // Immediate database UNIQUE violation happens during SQL flush.
        assertThrows(DataIntegrityViolationException.class,
                () -> repository.flush());

        // No further JPA queries in this failed transaction.
        // @DataJpaTest's test transaction rolls back after the method.
    }

    @Test
    void saveAndFlushMakesSecondViolationImmediate() {
        String email = "early-" + UUID.randomUUID()
                + "@example.test";

        repository.saveAndFlush(new CustomerAccount(email));

        assertThrows(DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new CustomerAccount(email)));
    }
}
```

**3 JPA slice tests.** H2 có immediate unique constraint, Hibernate UUID ID generator cho phép `save` tạo managed entities trước INSERT. Test thứ hai cố ý chỉ bắt lỗi tại `repository.flush()`; sau flush lỗi, transaction phải rollback — **không query hoặc gọi tiếp repository trên transaction đã fail**.

`@DataJpaTest` **mặc định transaction rollback** sau mỗi test method, nên các email/rows test này không bị commit và không cần `deleteAll()`. Tuy nhiên, default rollback cũng có thể che một constraint chỉ được kiểm **lúc commit**; vì vậy test ở mục 20 bỏ test-managed transaction và dùng TransactionTemplate chủ động commit.

### 19.1. Vì sao `assertThrows` phải đặt quanh flush?

Sai:

```java
// Phản ví dụ: có thể FAIL vì save chưa gửi INSERT.
assertThrows(DataIntegrityViolationException.class,
        () -> repository.save(new CustomerAccount(duplicate)));
```

Đúng hơn khi muốn kiểm unique immediate:

```java
repository.save(new CustomerAccount(duplicate));
assertThrows(DataIntegrityViolationException.class,
        () -> repository.flush());
```

Đây là snippets. Với `GenerationType.IDENTITY` hoặc validate trước SQL, `save` có thể đã ném lỗi, nên cần đúng test fixture/generator/DB, không ép tất cả tests giống ví dụ UUID.

## 20. Commit-boundary test: callback thành công nhưng transaction commit thất bại

**`src/test/java/com/example/constrainttiming/CustomerAccountCommitBoundaryTest.java`**

```java
package com.example.constrainttiming;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class CustomerAccountCommitBoundaryTest {

    @Autowired
    CustomerAccountRepository repository;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Test
    void commitFlushFailsAfterCallbackCompletes() {
        String email = "commit-" + UUID.randomUUID()
                + "@example.test";

        AtomicBoolean reachedEndOfCallback =
                new AtomicBoolean(false);

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        assertThrows(RuntimeException.class,
                () -> tx.execute(status -> {

                    repository.save(new CustomerAccount(email));
                    repository.save(new CustomerAccount(email));

                    // Hibernate UUID generator may not need INSERT yet.
                    reachedEndOfCallback.set(true);
                    return null;
                }));

        assertTrue(reachedEndOfCallback.get(),
                "Work callback completed before commit failed");

        // The transaction was rolled back; query in a new boundary.
        assertEquals(0L, repository.countByEmail(email));
    }
}
```

**1 commit-boundary test.** `@Transactional(propagation = NOT_SUPPORTED)` loại test-managed transaction vốn được `@DataJpaTest` tạo mặc định. `TransactionTemplate.execute` bắt đầu transaction, chạy callback, rồi thực hiện commit **sau khi callback return**. Với Hibernate UUID generator và H2 unique immediate, SQL INSERT đang chờ có thể được flush **trong tiến trình commit**; callback đã kết thúc bình thường nhưng commit ném exception. `AtomicBoolean` cho thấy phần callback không phải nơi phát sinh lỗi.

**Không nhầm cơ chế:** Trong test này lỗi unique vẫn là **immediate**; nó chỉ xuất hiện ở commit vì Hibernate **chưa flush SQL trước đó**. Đây khác với PostgreSQL deferred unique, nơi SQL đã chạy ở flush nhưng **database cố tình đợi đến commit mới kiểm**. Hai trường hợp cùng “lỗi lúc commit” nhưng cách sửa và phương pháp kiểm khác nhau.

### 20.1. Lỗi exception type tại commit có thể khác

Đừng hard-code rằng mọi commit error là `DataIntegrityViolationException` tại chỗ test gọi `TransactionTemplate.execute`. Spring JpaTransactionManager/ORM có thể wrap hoặc translate thành `DataIntegrityViolationException`, `TransactionSystemException` hoặc một RuntimeException khác tùy root cause và thời điểm. Core test bắt `RuntimeException` để xác minh commit **không thành công**, rồi kiểm callback đã kết thúc và dữ liệu không tồn tại. Để chẩn đoán sâu hơn, inspect root SQLException/SQLSTATE và Hibernate constraint name trong cause chain.

**Không áp dụng mẫu “bắt RuntimeException” bừa bãi để kiểm domain business error**: các test public API vẫn phải assert lỗi đúng contract; core test này chuyên quan sát *commit boundary*.

## 21. Full HTTP integration: lỗi unique không được trả 201

**`src/test/java/com/example/constrainttiming/AccountHttpIntegrationTest.java`**

```java
package com.example.constrainttiming;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AccountHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    CustomerAccountRepository repository;

    private final List<UUID> ownedIds = new ArrayList<>();

    private String uniqueEmail() {
        return "http-" + UUID.randomUUID() + "@example.test";
    }

    private AccountCreated create(String email) {
        ResponseEntity<AccountCreated> response =
                http.postForEntity(
                        "/api/accounts",
                        new RegisterAccountRequest(email),
                        AccountCreated.class);

        assertEquals(201, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertNotNull(response.getBody().id());
        ownedIds.add(response.getBody().id());
        return response.getBody();
    }

    @AfterEach
    void removeOnlyRowsCreatedByThisTest() {
        for (UUID id : ownedIds) {
            repository.deleteById(id);
        }
    }

    @Test
    void firstInsertPersistsCanonicalEmail() {
        String email = uniqueEmail();
        AccountCreated created = create(
                "  " + email.toUpperCase() + "  ");

        assertEquals(email, created.email());
        assertEquals(email, repository.findById(created.id())
                .orElseThrow().getEmail());
    }

    @Test
    void secondInsertOfSameEmailReturns409AndNoExtraRow() {
        String email = uniqueEmail();
        create(email);

        ResponseEntity<ApiErrorAdvice.ApiError> response =
                http.postForEntity(
                        "/api/accounts",
                        new RegisterAccountRequest(email),
                        ApiErrorAdvice.ApiError.class);

        assertEquals(409, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("EMAIL_CONFLICT",
                response.getBody().code());
        assertEquals(1L, repository.countByEmail(email));
    }

    @Test
    void invalidEmailReturns400WithoutPersistingData() {
        long before = repository.count();

        ResponseEntity<ApiErrorAdvice.ApiError> response =
                http.postForEntity(
                        "/api/accounts",
                        new RegisterAccountRequest("   "),
                        ApiErrorAdvice.ApiError.class);

        assertEquals(400, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals("INVALID_EMAIL",
                response.getBody().code());
        assertEquals(before, repository.count());
    }
}
```

**3 HTTP integration tests** chạy embedded server trên random TCP port, controller/service/repository/H2 đều thật. Lỗi unique từ `saveAndFlush` không bị nuốt, Spring transaction rollback, controller advice trả HTTP 409. Test thứ hai còn assert database chỉ có **một** bản ghi cùng email, không phải chỉ assert response status.

**Phạm vi:** Đây là integration với immediate unique H2; không chứng minh PostgreSQL deferred unique. Dữ liệu có UUID unique và `@AfterEach` chỉ delete đúng rows được test tạo. Không có class-level `@Transactional`: HTTP request chạy server thread, không nằm trong rollback transaction test thread.

## 22. Tổng số phương thức kiểm thử trong demo H2

| Test class | Số `@Test` | Bằng chứng |
|---|---:|---|
| `AccountServiceTest` | 4 | Normalize và SQLSTATE classification unit |
| `CustomerAccountRepositoryFlushTest` | 3 | Immediate unique khi flush/saveAndFlush |
| `CustomerAccountCommitBoundaryTest` | 1 | Auto-flush trong commit sau callback |
| `AccountHttpIntegrationTest` | 3 | Real HTTP, rollback, 201/400/409 và DB state |
| **Tổng** | **11** | Phân biệt pending SQL/flush/commit và public contract |

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Cần có Gradle Wrapper trong project; nếu chưa có, tạo wrapper bằng Gradle/IDE phù hợp. Kết quả **dự kiến** nếu dependencies/JDK17+/Gradle được cấu hình đúng là `BUILD SUCCESSFUL`, report tại `build/reports/tests/test/index.html`. **Mã đã được rà soát nhưng chưa thực thi Gradle/JUnit trên repository thực tế**; không coi dự kiến này là execution report.

Các assertions tập trung vào exception type/SQLSTATE/business state, **không assert exact Hibernate SQL log text**, thứ tự methods, UUID value hay thông điệp lỗi từ database.

## 23. Tại sao một test rollback có thể “xanh giả”?

Ví dụ phản diện:

```java
@DataJpaTest
class MisleadingTest {

    @Autowired
    CustomerAccountRepository repo;

    @Test
    void apparentlySavedTwice() {
        repo.save(new CustomerAccount("same@example.test"));
        repo.save(new CustomerAccount("same@example.test"));
        // Không flush, không query, test kết thúc.
        // @DataJpaTest rollback; SQL có thể chưa hề chạy.
    }
}
```

Test không assert constraint và không yêu cầu commit. Nó có thể kết thúc bình thường vì rollback loại pending work. Vì vậy dòng comment “two saves succeeded” không chứng minh database chấp nhận uniqueness.

**Cách sửa theo mục tiêu:**

- Kiểm **immediate constraint** → `repository.flush()` hoặc `saveAndFlush` trong test.
- Kiểm **deferred constraint** → transaction phải **thực sự commit** trên PostgreSQL, không chỉ flush.
- Kiểm HTTP contract → gọi service/controller thật qua boundary và assert 409 + database unchanged.
- Kiểm rollback sau error → bắt lỗi và query state trong transaction mới.
- Kiểm concurrency uniqueness → hai transactions độc lập, data race được đồng bộ/latch.

Nếu test dùng `@Rollback(false)` hoặc `@Commit` để buộc commit, nó có thể làm bẩn DB test; dùng database/schema riêng, cleanup rõ và quản lý lifecycle. `TestTransaction` hoặc TransactionTemplate giúp đặt assertion quanh đúng transaction boundary hơn là hy vọng exception xuất hiện ngoài test method sau khi listener commit.

## 24. `TestTransaction`: commit chủ động trong Spring transactional test

Spring Framework cung cấp `org.springframework.test.context.transaction.TestTransaction` cho các test có test-managed transaction. Nó cho phép flag commit/rollback và kết thúc transaction **ngay trong method** để assert kết quả, thay vì đợi listener sau test.

Snippet minh họa cho `@DataJpaTest` (không phải file runnable độc lập):

```java
@Test
void forcedCommitFailsInsideTest() {
    repository.save(new CustomerAccount("demo@example.test"));
    repository.save(new CustomerAccount("demo@example.test"));

    TestTransaction.flagForCommit();

    assertThrows(RuntimeException.class, TestTransaction::end);

    // Do not continue using the failed transaction.
}
```

Cần import `TestTransaction`, `Test`, `assertThrows` và repository fixture phù hợp. `TestTransaction.end()` kết thúc test transaction đã được flag; lỗi có thể phát sinh khi flush/commit. Cách này hữu ích để kiểm **commit thực** trong Spring tests nhưng làm thay đổi lifecycle: sau `end()` không còn active test transaction cho đến khi `TestTransaction.start()`; đừng tự query trong transaction đã fail.

**Trong demo runnable**, chúng ta chọn `TransactionTemplate` với method-level `Propagation.NOT_SUPPORTED` để ranh giới commit sáng sủa hơn và không phụ thuộc test-managed transaction của `@DataJpaTest`.

## 25. Flush không phải commit và rollback vẫn có tác dụng

Giả sử:

```text
BEGIN TRANSACTION
save(account A)
flush()   -> INSERT A đã chạy và database thấy A trong transaction này
ROLLBACK  -> A không tồn tại sau rollback
```

Việc `flush()` thành công chỉ xác nhận SQL được database chấp nhận **tại thời điểm đó**. Không được trả “đã lưu thành công vĩnh viễn” nếu transaction chưa commit. Các commit-time errors có thể còn đến từ:

- PostgreSQL deferred constraints.
- Serialization failures và deadlocks.
- Network/connection errors khi commit.
- Resource manager/JTA issues.
- DB transaction timeout hoặc lock timeout.
- Transaction đã marked rollback-only.
- Constraint trigger deferred.

**Một test bắt exception ở flush vẫn chưa kiểm đủ mọi lỗi có thể đến ở commit.** Với dịch vụ có tính nhất quán cao, cần kiểm transaction boundary và xác nhận trạng thái sau commit/rollback, không chỉ entity state trong persistence context.

## 26. Lỗi unique và “kiểm trước khi ghi” vẫn có race

Phản ví dụ thường gặp:

```java
if (!repository.existsByEmail(email)) {
    repository.save(new CustomerAccount(email));
}
```

Hai requests đồng thời có thể cùng thấy `existsByEmail=false`, cùng INSERT, rồi một transaction bị unique violation. Precheck là trải nghiệm người dùng, **không phải bảo đảm uniqueness**.

```text
Transaction T1                 Transaction T2
--------------                 --------------
exists(email)=false            exists(email)=false
save(email)                    save(email)
flush / commit                 flush / commit
SUCCESS                        UNIQUE VIOLATION
```

Tùy isolation/DB locks, transaction thứ hai có thể **chờ** transaction thứ nhất, rồi fail sau khi T1 commit. Một integration test concurrency phải dùng database thật, synchronization barriers, connection pools đủ và timeout hữu hạn; không dựa vào `Thread.sleep` để “hy vọng” hai threads đến cùng lúc. Với PostgreSQL production, cần test actual unique index/DDL của migrations.

**Không retry vô hạn** mọi 23505. Nếu request có idempotency key, có thể trả kết quả đã tạo; nếu business là “email đã tồn tại”, 409 có thể thích hợp. Mọi quyết định cần contract rõ, không dùng precheck để thay integrity constraint.

## 27. Constraint immediate và deferred trong PostgreSQL

PostgreSQL định nghĩa:

- `NOT DEFERRABLE` (mặc định): kiểm theo statement, không dời tới cuối transaction.
- `DEFERRABLE INITIALLY IMMEDIATE`: có thể chuyển sang deferred trong transaction bằng `SET CONSTRAINTS`; mặc định kiểm ngay.
- `DEFERRABLE INITIALLY DEFERRED`: kiểm khi transaction commit, trừ khi được đổi sang immediate.
- `SET CONSTRAINTS ALL IMMEDIATE` buộc kiểm các pending violations tại thời điểm lệnh được thực thi, thay vì đợi commit.
- Không phải mọi constraint cho phép deferral: PostgreSQL chỉ cho một số loại như UNIQUE/PK/FK/EXCLUDE, không phải CHECK/NOT NULL.

**Khác biệt bản chất:** Với deferred UNIQUE, một lần `entityManager.flush()` có thể chạy thành công vì database **chưa yêu cầu xét uniqueness**, chứ không phải vì Hibernate chưa gửi SQL. Test kiểu `assertThrows(..., entityManager::flush)` có thể fail (không có exception), trong khi transaction commit sẽ fail.

**Không mong H2 mô phỏng chính xác DDL này.** Dùng PostgreSQL instance/container cho test thực về deferrable constraints.

## 28. PostgreSQL lab: lỗi chỉ xuất hiện ở COMMIT dù cả hai INSERT thành công

Các lệnh sau chạy trong một **PostgreSQL test database**, ví dụ `psql` console. Không chạy trên production DB. Sử dụng một temporary table trong session hiện tại để không chạm bảng của ứng dụng.

```sql
CREATE TEMP TABLE deferred_accounts (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    CONSTRAINT uk_deferred_accounts_email
        UNIQUE (email) DEFERRABLE INITIALLY DEFERRED
);

BEGIN;

INSERT INTO deferred_accounts (id, email)
VALUES (1, 'same@example.test');

INSERT INTO deferred_accounts (id, email)
VALUES (2, 'same@example.test');

-- Hai INSERT có thể thành công dù email trùng.
-- Database giữ pending uniqueness check đến commit.

COMMIT;
-- ERROR: duplicate key value violates unique constraint
--        "uk_deferred_accounts_email"
-- SQLSTATE 23505.
-- Transaction không commit, hai INSERT bị rollback.
```

**Kết quả quan sát cần chứng minh:**

1. Hai INSERT đã được thực thi và không ném lỗi immediate.
2. Lỗi xuất hiện ở `COMMIT`.
3. Mã lỗi unique là `23505`; exact localized message có thể khác phiên bản/locale.
4. Các rows trong transaction thất bại không được commit.
5. Nếu chạy lại trong cùng `psql` session, temporary table vẫn tồn tại (vì DDL được tạo trước BEGIN) nhưng dữ liệu từ failed transaction không tồn tại.

### 28.1. Kéo lỗi về trước bằng SET CONSTRAINTS IMMEDIATE

Sau khi transaction ở trên đã thất bại/rollback, dùng một transaction mới:

```sql
BEGIN;

INSERT INTO deferred_accounts (id, email)
VALUES (10, 'new@example.test');

INSERT INTO deferred_accounts (id, email)
VALUES (11, 'new@example.test');

SET CONSTRAINTS uk_deferred_accounts_email IMMEDIATE;
-- Lỗi 23505 có thể được phát hiện NGAY tại SET CONSTRAINTS.
-- Transaction vào trạng thái lỗi; cần ROLLBACK.

ROLLBACK;
```

Lệnh `SET CONSTRAINTS ... IMMEDIATE` không tự commit; nó thay **thời điểm kiểm** và kiểm các pending changes tương ứng. Đây là một công cụ diagnostic trong transaction khi muốn biết deferred constraint đang vi phạm trước commit, nhưng không được dùng vô tội vạ để thay semantics ứng dụng; với dữ liệu được phép tạm thời vi phạm trong transaction rồi sửa trước commit, việc ép immediate quá sớm sẽ làm workflow không còn hợp lệ.

### 28.2. Điều gì xảy ra nếu dùng JPA saveAndFlush vào PostgreSQL này?

Nếu Hibernate map entity tới bảng có unique constraint `DEFERRABLE INITIALLY DEFERRED` và có active transaction:

```text
repository.save(...)
entityManager.flush()   -> INSERT chạy và được PostgreSQL chấp nhận tạm
service method returns  -> chưa có lỗi
commit                   -> PostgreSQL check deferred unique, ERROR 23505
```

Do đó test phải kiểm tại **transaction commit boundary**. Nếu service catch `DataIntegrityViolationException` chỉ xung quanh `saveAndFlush`, catch có thể **không chạy** vì commit do Spring transaction proxy thực hiện sau khi method body đã kết thúc. Đây là một trong những lý do lỗi DB đôi khi chỉ hiện trên integration test, không phải unit/mocked repository test.

## 29. DDL production: migrations phải phản ánh constraint mode thật

Entity annotations không có cú pháp portable để diễn đạt mọi PostgreSQL deferrable constraints. Trong thực tế, Flyway/Liquibase migration có thể dùng:

```sql
CREATE TABLE customer_accounts (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL
);

ALTER TABLE customer_accounts
    ADD CONSTRAINT uk_customer_accounts_email
    UNIQUE (email)
    DEFERRABLE INITIALLY DEFERRED;
```

Đây là ví dụ PostgreSQL DDL, **không phải schema cho H2 runnable demo**. Nếu áp migration này trong dự án dùng Hibernate-generated schema có sẵn unique constraint cùng tên, sẽ có xung đột; production nên dùng migration làm nguồn sự thật cho schema, thường đặt `ddl-auto=validate`/none phù hợp, không để Hibernate tự tạo rồi ALTER trùng.

**Thận trọng:** PostgreSQL không cho dùng deferrable unique constraint làm arbiter trong một `INSERT ... ON CONFLICT` clause. Nếu hệ thống dùng upsert/ON CONFLICT(email), thay unique sang DEFERRABLE có thể làm đường upsert hỏng. Chọn deferrable vì business requirement về temporary inconsistent state, không đơn giản vì muốn dời lỗi đến commit.

## 30. Integration test PostgreSQL với JDBC/Testcontainers: phương pháp đúng

Để tự động hóa commit-only behavior, có thể thêm một test **tách biệt** chạy trên PostgreSQL thật bằng Testcontainers, JDBC và JUnit. Khác với H2 demo, test này cần Docker runtime và dependencies Testcontainers/Postgres driver.

Phần dependency bổ sung **tùy chọn**, không có trong core `build.gradle` ở mục 12:

```groovy
// Add to dependencies when PostgreSQL container tests are enabled.
testImplementation 'org.testcontainers:postgresql:1.21.3'
testImplementation 'org.testcontainers:junit-jupiter:1.21.3'
testRuntimeOnly 'org.postgresql:postgresql'
```

Ví dụ **snippets hướng dẫn** (không nằm trong 11 core test methods; cần imports và file setup phù hợp):

```java
// Requires org.testcontainers.junit.jupiter.Container/Testcontainers;
// PostgreSQLContainer and java.sql imports.
@Testcontainers
class DeferredUniqueJdbcTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:17-alpine");

    @Test
    void duplicatesFailOnlyWhenCommitting() throws Exception {
        try (Connection setup = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());
             Statement ddl = setup.createStatement()) {

            ddl.execute("""
                CREATE TABLE deferred_email_probe (
                  id integer primary key,
                  email text not null,
                  CONSTRAINT uk_probe UNIQUE(email)
                    DEFERRABLE INITIALLY DEFERRED
                )
                """);
        }

        try (Connection conn = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword())) {

            conn.setAutoCommit(false);

            try (PreparedStatement insert =
                    conn.prepareStatement(
                        "INSERT INTO deferred_email_probe"
                        + " (id, email) VALUES (?, ?)")) {

                insert.setInt(1, 1);
                insert.setString(2, "same@example.test");
                insert.executeUpdate();

                insert.setInt(1, 2);
                insert.setString(2, "same@example.test");
                insert.executeUpdate();
            }

            SQLException error = assertThrows(
                    SQLException.class, conn::commit);

            assertEquals("23505", error.getSQLState());
            conn.rollback();
        }
    }
}
```

**Phạm vi của snippet:** Nó dùng **JDBC thuần** để cô lập PostgreSQL deferred semantics khỏi Hibernate flush queue; cả hai `executeUpdate()` thực sự gửi SQL, lỗi đến từ `Connection.commit()`. Để chạy cần thêm các imports JUnit/Testcontainers/`java.sql`, JVM test runner và Docker. Test tạo table bên trong container test-owned; không được chỉ vào database thật khác. Khi muốn kiểm **Spring/JPA commit exception translation**, thêm một `@SpringBootTest` hoặc JPA slice có transaction manager dùng **chính PostgreSQL container**, qua `@ServiceConnection`/`@DynamicPropertySource` và migration tương ứng.

**Không gắn nhãn H2 unit test là đã kiểm PostgreSQL commit-time deferrable constraint**. Hai tests trả lời những câu hỏi khác nhau.

## 31. JPA flush vs JDBC commit: chứng cứ nào có giá trị?

Một chẩn đoán đáng tin cần nêu:

| Quan sát | Được phép kết luận | Chưa được kết luận |
|---|---|---|
| `save()` không ném lỗi | Lời gọi save hiện tại kết thúc bình thường | SQL đã chạy, constraint pass |
| `flush()` không ném lỗi | Pending SQL đã được gửi hợp lệ theo transaction/provider hiện tại | Commit sẽ thành công |
| `flush()` ném unique | Immediate constraint/triggers bị vi phạm khi SQL chạy | Mọi constraint ở DB đều immediate |
| `commit()` ném unique sau flush thành công | Commit-time validation hoặc state/transaction khác gây lỗi | Nguyên nhân chắc chắn là deferred unique nếu chưa xem DDL |
| `@DataJpaTest` rollback xanh | Code trong test và rollback không ném lỗi visible | Commit-time constraints sẽ pass |
| `RANDOM_PORT` test HTTP 409 | App mapping/call path đã trả conflict trong topology test | Production DB/migrations giống H2 |
| Query entity trong same context thấy changed field | Java managed state đã đổi | DB khác transaction đã thấy commit |
| Query after commit thấy row | Transaction ghi đã commit và row visible cho query đó | Exactly-once khi concurrent requests |
| PostgreSQL JDBC commit 23505 trên deferred unique | Constraint deferral thực được kiểm lúc commit | Spring exception mapping 409 đã đúng |

## 32. Dùng logging/diagnostics để tìm lỗi gốc

Bật có chọn lọc trong test environment:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.orm.jpa=DEBUG
```

**Không bật bind TRACE trên production logs chứa email, tokens, PII hoặc payment data**. Với CI training, dùng synthetic email và bảo đảm artifacts không lộ secrets.

Phương pháp đọc log:

1. Tìm nơi entity được persist/merge và ID generator.
2. Kiểm có `INSERT/UPDATE/DELETE` trước dòng exception không.
3. Nếu không thấy SQL trước `save`, xem flush mode/batching/transaction boundary.
4. Nếu thấy SQL rồi exception ở `flush`, xem immediate constraint/foreign key/check.
5. Nếu flush thành công rồi commit lỗi, xem **DDL deferrable**, isolation/lock/deadlock/JTA.
6. Tìm SQLSTATE, constraint name, root SQLException và exception translation layers.
7. Xác định transaction đã rollback hay marked rollback-only; không query tiếp qua failed session.
8. Query state sau rollback ở new connection/transaction để chứng minh không có partial writes.
9. Nếu chỉ CI fail, so sánh database engine/version/schema migrations/parallel jobs.
10. Nếu query “tự làm save fail”, kiểm query-triggered auto-flush.

### 32.1. Stack trace cho biết lỗi phát sinh ở tầng nào

Một stack trace có thể nhắc đến:

- `SimpleJpaRepository.save` / `EntityManager.persist`: persistence call/generator.
- `SessionImpl.flush` / `DefaultFlushEventListener`: flush synchronization.
- `JpaTransactionManager.doCommit`: transaction completion.
- `TransactionInterceptor.invoke`: AOP transactional boundary.
- `org.hibernate.exception.ConstraintViolationException`: JDBC integrity.
- `org.springframework.dao.DataIntegrityViolationException`: Spring translated exception.
- `org.springframework.transaction.UnexpectedRollbackException`: transaction đã rollback-only mà outer flow vẫn muốn commit.

**Không tự kết luận chỉ từ class ở đỉnh stack trace**; đọc cause chain, SQLSTATE, constraint name và hoạt động trước đó.

## 33. Những lỗi thường mắc khi viết assertThrows

| Anti-pattern | Hậu quả | Cách thay |
|---|---|---|
| Bắt lỗi chỉ quanh `save` khi SQL deferred | Assert không thấy exception | Flush hoặc commit đúng mốc |
| Dùng `assertDoesNotThrow(save)` để chứng minh uniqueness | False confidence | Constraint violation test |
| Gọi `entityManager.clear` trước flush | Mất pending changes chưa gửi | Flush trước clear khi cần |
| Catch mọi `RuntimeException` rồi xem là constraint | Che logic bug | Assert SQLSTATE/type/root cause |
| Query DB trong transaction sau failed flush | Transaction poisoned, lỗi thứ cấp | Rollback; query bằng transaction mới |
| Bắt unique nhưng không kiểm rollback | Có thể còn partial side effects | Assert DB state sau failure |
| Dùng exact message tiếng Anh làm assertion | Database/provider locale khác | SQLSTATE/constraint name/category |
| Giả định `saveAndFlush` luôn commit | Sai outer transaction boundary | Tách flush vs commit |
| Dùng `@DataJpaTest` rollback để kiểm deferred commit | Không commit thật | TransactionTemplate/TestTransaction |
| Dùng H2 để test PostgreSQL DEFERRABLE | Semantics khác | PostgreSQL Testcontainers |
| `@Transactional` test HTTP và kỳ vọng server rollback | Khác threads/transactions | Scoped cleanup |
| Swallow integrity error trong `@Transactional` | Rollback-only, UnexpectedRollback | Propagate; xử lý ngoài transaction |
| Chỉ `existsByEmail` trước insert | Race concurrent requests | DB UNIQUE + conflict mapping |
| Map mọi `23505` thành email trùng | Nhầm unique constraints khác | Inspect constraint name |
| Không đo SQL flush mode/ID generator | Test timing không tái lập | Cố định config/DDL/ID strategy |
| Dùng `REQUIRES_NEW` vô cớ để “ép lưu” | Phá atomicity của outer transaction | Chỉ dùng khi requirement rõ |
| Test chỉ nhìn entity managed field | Không kiểm persisted state | Flush/clear/new transaction readback |
| Giữ `ddl-auto=create-drop` trên production | Có thể phá dữ liệu | Migrations và validate |
| Chạy Postgres test trên shared DB | Dữ liệu/test table ảnh hưởng người khác | Isolated container/schema |

## 34. Khi nào nên đặt flush ở service và khi nào không?

`saveAndFlush` có ích khi business cần phát hiện immediate database violation **trước khi làm bước tiếp theo** trong cùng transaction. Ví dụ muốn kiểm uniqueness trước khi dựng một response hoặc trước một thao tác có side effect không transactional. Tuy nhiên:

- Flush có overhead và ảnh hưởng batching.
- Flush không commit, vẫn có lỗi deferred ở commit.
- External side effects (email/Kafka/HTTP) **không rollback** nếu transaction cuối cùng thất bại.
- “Gửi email sau flush” vẫn nguy hiểm vì database có thể rollback ở commit; dùng transactional outbox/after-commit logic phù hợp.
- Không thêm flush vào mọi repository method chỉ để làm tests pass; hiểu production write path và performance.
- Nếu cần trả 409 đáng tin, transaction boundary phải hoàn thành hoặc error mapping phải ở ngoài transaction.
- Với workflow cho phép tạm vi phạm unique nhưng sửa trước commit, ép flush/SET CONSTRAINTS IMMEDIATE có thể không phù hợp.
- Không coi count/existence precheck là thay thế constraint.

**Gợi ý thiết kế:** Giữ transaction ngắn, đặt database integrity là nguồn sự thật, chuẩn hóa lỗi tại boundary nơi đã quan sát chắc transaction outcome, không để API báo 201 trước khi commit. Với message publishing, dùng outbox/idempotency để xử lý commit và external effects.

## 35. Data cleanup, test isolation và concurrent execution

Những điều cần bảo đảm khi test database constraints:

1. Mỗi test dùng unique email/title theo `UUID` trừ khi **cố ý** tạo duplicate.
2. `@DataJpaTest` rollback thường xử lý DB rows trong cùng test transaction.
3. Test dùng `TransactionTemplate` commit **thành công** cần explicit cleanup test-owned rows.
4. `RANDOM_PORT` HTTP server commit độc lập; cleanup theo created ID.
5. Đừng `deleteAll()` trên shared DB/container/tenant nếu tests chạy song song.
6. Failed PostgreSQL transactions phải rollback trước khi dùng lại connection.
7. Nếu database migration là nguồn DDL, test phải apply đúng migration.
8. Container/schema ownership phải rõ, nhất là nếu CI bị kill giữa chừng.
9. DDL tạo/đổi constraints có thể giữ locks; không chạy trên DB đang phục vụ dữ liệu thật.
10. Kiểm test không phụ thuộc thứ tự, không reuse email cố định giữa CI jobs.

**Concurrency:** UNIQUE violation khi hai transactions race không nhất thiết xuất hiện đúng cùng chỗ theo scheduler; dùng barriers, deadlines và transaction separation, không dùng `sleep` vô hạn. Một lần chạy local xanh không bảo đảm isolation level/locking của production.

## 36. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| `save` chạy bình thường, commit fail | Pending SQL auto-flush hoặc deferred constraint | SQL trace, flush mode, DDL |
| `saveAndFlush` không ném nhưng commit fail | Deferred PostgreSQL unique/FK hoặc commit error khác | `pg_constraint.condeferrable`, SQLSTATE |
| Test `@DataJpaTest` xanh nhưng API fail | Test rollback không commit | TransactionTemplate hoặc real HTTP |
| `assertThrows(save)` fail | INSERT chưa chạy vì generator/flush | Dùng flush explicit |
| `save` ném ngay với IDENTITY | DB insert sớm để lấy ID | Xác minh strategy/generator |
| `repo.count()` tự ném unique | AUTO flush trước query | SQL/query spaces và pending changes |
| Query thấy entity nhưng row chưa commit | First-level cache/read-your-writes | New transaction read |
| Duplicate API trả HTTP500 thay 409 | Exception type tại commit khác service catch | Advice outside transaction, cause mapping |
| Duplicate trả 201 rồi server log SQL error | Async write hoặc response trước commit | Bảo đảm sync transaction completion |
| `UnexpectedRollbackException` sau catch | Transaction đã rollback-only | Không swallow persistence error |
| Test unique chạy riêng xanh, suite đỏ | Email cố định hoặc DB state leak | UUID, rollback, cleanup |
| H2 pass nhưng Postgres fail | Dialect/DDL/constraint mode khác | Postgres Testcontainers |
| Vi phạm NOT NULL không có SQL log | Hibernate/Bean Validation chặn trước | Cause type, validation config |
| Insert xong publish event rồi commit lỗi | Side effect ngoài DB transaction | Transactional outbox |
| Error message đổi trên CI | Driver/locale/DB version khác | SQLSTATE + constraint name |
| PostgreSQL connection tiếp tục báo 25P02 | Transaction aborted sau prior error | Rollback trước query mới |

### 36.1. Quy trình điều tra 10 bước

1. Tái tạo bằng một **test fixture tối thiểu**, không dùng dữ liệu thật.
2. Xác định error type/gốc, SQLSTATE, constraint name.
3. Đọc schema thực tế từ migrations, không dựa hoàn toàn annotations.
4. Xác định ID strategy và provider/dialect.
5. Kiểm transaction boundary nào đang active ở từng layer.
6. Đặt explicit flush ở đúng test boundary nếu kiểm immediate constraint.
7. Nếu flush pass mà commit fail, kiểm PostgreSQL DEFERRABLE hoặc transaction failures khác.
8. Không query/tiếp tục giao dịch đã aborted; rollback rồi xác minh hậu điều kiện.
9. Kiểm HTTP status/business contract ở ngoài transaction proxy.
10. Ghi rõ kết quả là H2 flush test, commit test hay PostgreSQL deferred constraint test.

## 37. Bài tập có đáp án

### A. Hai lần save, không flush

Test làm hai lần `repo.save(new Account(sameEmail))` rồi method kết thúc bằng rollback. Có thể nói UNIQUE đã pass không?

**Đáp án:** Không. SQL có thể chưa chạy; rollback có thể bỏ pending actions. Dùng flush để kiểm unique immediate hoặc commit test để kiểm deferred constraint.

### B. Flush thành công

Đã `repository.saveAndFlush` và không có exception. Có thể trả “transaction chắc chắn commit thành công” không?

**Đáp án:** Không. Flush không commit; deferred constraint, deadlock/isolation và connection errors có thể phát sinh khi commit.

### C. SQLSTATE 23505

Mọi `23505` trong schema Orders có phải email trùng không?

**Đáp án:** Không. Nó chỉ thể hiện unique violation; cần constraint/table/operation context để map đúng business code.

### D. GenerationType.IDENTITY

Một test trước đây chỉ ném ở flush, sau khi đổi ID strategy sang IDENTITY nó ném ngay save. Đây có chắc là regression Hibernate không?

**Đáp án:** Không. IDENTITY thường cần INSERT sớm lấy ID. Kiểm mapping, generated SQL và mục tiêu test.

### E. @DataJpaTest rollback

Bạn muốn kiểm PostgreSQL deferred FK chỉ fail ở commit, nhưng @DataJpaTest mặc định rollback. Test nên thay đổi gì?

**Đáp án:** Bảo đảm commit thực bằng `TransactionTemplate` ngoài test-managed transaction, `TestTransaction.flagForCommit/end` hoặc real HTTP/DB integration và cleanup riêng.

### F. Flush và clear

Dùng `entityManager.clear()` ngay sau `save()` mà không flush. Có thể mất gì?

**Đáp án:** Pending changes chưa đồng bộ có thể bị loại khi entities detached; khi mục tiêu là persisted state, flush trước clear.

### G. Query tự trigger lỗi

`repo.findByEmail(...)` sau hai pending duplicates bỗng ném unique. Vì sao?

**Đáp án:** Với AUTO flush, query liên quan có thể trigger flush trước khi thực hiện query.

### H. H2 và PostgreSQL

H2 unique flush test pass, nhưng Postgres có DEFERRABLE INITIALLY DEFERRED. Có thể dùng kết quả H2 để chứng minh lỗi cũng ở flush trên Postgres?

**Đáp án:** Không. Postgres có thể đợi commit dù SQL đã chạy; phải test provider/DDL thật.

### I. Catch lỗi trong service

Service catch `DataIntegrityViolationException` rồi trả false trong `@Transactional`. Tại sao vẫn có thể thấy UnexpectedRollbackException?

**Đáp án:** Transaction có thể đã rollback-only/aborted, outer interceptor không thể commit thành công. Xử lý ngoài transaction hoặc propagate.

### J. Kiểm hậu điều kiện

API trả 409 cho duplicate nhưng test không query DB. Có thể bỏ sót điều gì?

**Đáp án:** Một side effect/partial write hay lỗi transaction semantics khiến row/data khác thay đổi. Query lại ở transaction mới và assert đúng số records.

### K. SET CONSTRAINTS IMMEDIATE

Trong PostgreSQL, hai INSERT trùng vào deferrable unique thành công; `SET CONSTRAINTS ALL IMMEDIATE` báo lỗi. Điều đó chứng minh gì?

**Đáp án:** Database đã trì hoãn kiểm, và việc đổi sang immediate buộc xét pending violations trước commit.

### L. Precheck race

Hai requests cùng `existsByEmail=false`. Cách nào đảm bảo chỉ một row được tạo?

**Đáp án:** Database unique constraint (và transaction semantics), ứng dụng map conflict/retry theo policy. Precheck đơn lẻ không đủ.

### M. Entity getter

Sau mutate, `getEmail()` trả giá trị mới nhưng database row vẫn cũ. Vì sao?

**Đáp án:** Managed entity state trong RAM khác trạng thái SQL committed. Flush/clear/new transaction readback theo mục tiêu.

### N. Commit exception type

Một provider ném `TransactionSystemException` thay vì `DataIntegrityViolationException` ở commit. Có nên tự gắn handler global catch mọi RuntimeException → 409?

**Đáp án:** Không. Phân tích cause/SQLSTATE/constraint name tại boundary an toàn; giữ 500 cho lỗi chưa phân loại.

### O. Business side effect

Service gửi email sau flush rồi commit bị deferred constraint fail. Người nhận đã có email xác nhận nhưng DB rollback. Cách sửa?

**Đáp án:** Tách side effect sau successful commit bằng outbox/after-commit delivery, có retry/idempotency và monitoring.

## 38. Checklist cuối bài và nguồn tham khảo

### Checklist

- [ ] Tôi phân biệt `save/persist`, SQL pending, flush, commit và rollback.
- [ ] Tôi biết flush có thể chạy trước query hoặc trước commit, không chỉ khi gọi explicit.
- [ ] Tôi biết ID generator/batching ảnh hưởng thời điểm SQL.
- [ ] Test unique immediate có assert tại `flush/saveAndFlush` phù hợp.
- [ ] Test deferred constraints thực sự commit trên database hỗ trợ.
- [ ] Tôi không dùng @DataJpaTest rollback để kết luận deferred constraint sẽ pass khi commit.
- [ ] Tôi biết `TransactionTemplate` hoặc `TestTransaction` để chủ động commit trong test.
- [ ] Tôi không coi entity getter hoặc first-level-cache read là persisted state.
- [ ] Lỗi flush làm test không tiếp tục query trên transaction đã failed.
- [ ] Có query state sau rollback/commit ở transaction mới.
- [ ] Không dùng H2 thay PostgreSQL khi test DEFERRABLE/migration-specific behavior.
- [ ] Tôi biết Postgres chỉ cho một số loại constraints DEFERRABLE.
- [ ] Tôi biết SET CONSTRAINTS IMMEDIATE có thể kéo việc xét pending violations lên trước.
- [ ] Tôi phân biệt Jakarta Bean Validation và Hibernate JDBC integrity exceptions.
- [ ] Tôi biết SQLSTATE 23505 chỉ nói unique, không xác định business constraint duy nhất.
- [ ] HTTP 201 không được phát trước transaction outcome hoàn tất.
- [ ] API 409 chỉ trả khi lỗi unique liên quan đã được nhận diện chính xác.
- [ ] Persistence errors không bị nuốt trong transaction rollback-only.
- [ ] Duplicate precheck không được dùng thay database unique constraint.
- [ ] Tests có email/IDs synthetic, unique theo method và cleanup scoped.
- [ ] Không chạy CREATE/ALTER/DROP constraints trên database production.
- [ ] SQL logs/bind TRACE không lộ dữ liệu nhạy cảm.
- [ ] Test thật có bằng chứng SQL/SQLSTATE/DDL/transaction boundary.
- [ ] Kiểm concurrent writes nếu chức năng chịu race trên production.
- [ ] Đã rà soát tác động của flush lên batching/performance và external side effects.
- [ ] Kết luận QA phân biệt code reviewed và test thực sự đã chạy.

**Kết luận:** “Database constraint chỉ lỗi sau flush hoặc commit” có ít nhất **hai cơ chế khác nhau**: Hibernate trì hoãn SQL tới flush/commit, và database như PostgreSQL **có thể trì hoãn xét constraint đã nhận SQL** tới commit. Đặt `assertThrows` quanh `save` một cách máy móc sẽ bỏ sót cả hai; chỉ ép `flush` cũng chưa đủ nếu DDL dùng deferrable constraint. Test đúng cần xác định **loại constraint, generator, flush mode, transaction boundary và DB provider**, chủ động flush hoặc commit tương ứng, rồi kiểm dữ liệu sau rollback/success. Với Spring Boot, đừng quên `@DataJpaTest` mặc định rollback, và controller/service transaction proxies có thể làm lỗi nổ **sau khi thân method đã return**.

### Tài liệu tham khảo chính thức

- Hibernate ORM — User Guide: Flushing, AUTO/COMMIT modes, query-triggered synchronization: https://docs.hibernate.org/stable/orm/userguide/html_single/#flushing
- Hibernate ORM — Transactions và transactional write-behind: https://docs.hibernate.org/stable/orm/userguide/html_single/#transactions
- Spring Data JPA — JpaRepository `flush/saveAndFlush/saveAllAndFlush`: https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
- Spring Boot 3.5 — Testing Spring Boot applications, `@DataJpaTest` rollback và `RANDOM_PORT` transactions: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — TransactionTemplate: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework 6.2 — Test-managed transactions, `TestTransaction`: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework — DAO exception translation/DataAccessException: https://docs.spring.io/spring-framework/reference/data-access/dao.html
- PostgreSQL 17 — `CREATE TABLE`, DEFERRABLE, constraint types: https://www.postgresql.org/docs/17/sql-createtable.html
- PostgreSQL 17 — `SET CONSTRAINTS`: https://www.postgresql.org/docs/17/sql-set-constraints.html
- PostgreSQL 17 — Error codes, Class 23 integrity constraint: https://www.postgresql.org/docs/17/errcodes-appendix.html
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Jakarta Persistence — EntityManager flush, persistence context semantics: https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager
