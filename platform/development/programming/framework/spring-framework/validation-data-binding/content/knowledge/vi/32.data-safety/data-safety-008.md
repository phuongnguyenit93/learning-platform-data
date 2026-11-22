# Kiểm tra tính duy nhất với database và nguy cơ tranh chấp

## 1. Vấn đề: cả hai request đều thấy “chưa tồn tại” nhưng cùng ghi một giá trị

Giả sử ứng dụng Spring cho phép đăng ký tài khoản với username không trùng lặp. Một cách kiểm tra thường gặp:

```java
if (accountRepository.existsByUsernameKey(usernameKey)) {
    throw new UsernameTakenException();
}

accountRepository.save(new AccountEntity(usernameKey));
```

Đoạn trên chỉ là **snippet minh họa**, chưa phải implementation an toàn. Trong môi trường nhiều request đồng thời, nó có lỗ hổng **check-then-act / time-of-check-to-time-of-use (TOCTOU)**:

```text
Thời điểm       Request A                        Request B
---------       -------------------------------  -------------------------------
t1              SELECT EXISTS('lan') -> false
t2                                               SELECT EXISTS('lan') -> false
t3              INSERT username_key='lan'
t4                                               INSERT username_key='lan'
t5              COMMIT
t6                                               COMMIT

Nếu database KHÔNG có unique constraint:
  Cả A và B có thể commit -> hai dòng trùng username.

Nếu database CÓ unique constraint/index:
  Không thể có hai dòng đã commit cùng khóa vi phạm ràng buộc;
  một thao tác sẽ thất bại (hoặc chờ rồi thất bại) tùy transaction/DB.
```

**Ý chính:** kiểm tra `existsBy...` giúp đưa ra gợi ý sớm, nhưng **không bảo đảm tính duy nhất**. Quy tắc độc nhất phải được thực thi ở nơi nắm toàn bộ tập dữ liệu và có cơ chế phối hợp các giao dịch concurrent: **database unique constraint/unique index** (hoặc cơ chế ràng buộc tương đương được thiết kế chặt chẽ ở datastore cụ thể).

Cùng một rủi ro xuất hiện với email đăng ký, mã đặt phòng, số hóa đơn, mã phiếu giảm giá, mã giao dịch, số điện thoại, tên nhóm trong tenant, slug của bài viết và các nguồn tài nguyên “chỉ được tạo một lần”.

Trong chủ đề **An toàn dữ liệu**, bài này đi từ nguyên nhân race condition, thiết kế schema, cách dùng Spring Data JPA, xử lý exception thành HTTP response, đến **kiểm thử cạnh tranh bằng hai luồng**. Đồng thời phân biệt kiểm tra Bean Validation với bất biến dữ liệu ở database.

**Môi trường tham chiếu:** Java 17+, Spring Boot 3.3.6, Spring Framework 6.1, Spring Data JPA, Hibernate ORM, Jakarta Validation, H2 cho dự án demo và PostgreSQL để minh họa các lựa chọn SQL production.

## 2. Ba lớp kiểm tra và mức bảo đảm

| Lớp | Ví dụ | Mục tiêu | Bảo đảm không trùng khi có concurrency? |
| --- | --- | --- | --- |
| Client/UI | Nút “Kiểm tra username” | Trải nghiệm nhập liệu | **Không** |
| Spring application | `existsByUsernameKey`, custom `@UniqueUsername` | Phản hồi sớm, business rule | **Không**, vì check và insert không atomic |
| Database schema | `UNIQUE(username_key)`, unique index | Bất biến cho dữ liệu được lưu | **Có**, trong phạm vi khóa/ràng buộc và semantics DB |
| Database atomic insert | PostgreSQL `INSERT ... ON CONFLICT` | Cạnh tranh insert/upsert theo unique arbiter | Có, theo semantics của database và conflict target |

Đặc biệt cần phân biệt:

- **Validation lỗi input:** `@NotBlank`, `@Size`, `@Pattern` kiểm tra định dạng hoặc giới hạn giá trị.
- **Business uniqueness:** username chưa được sử dụng ở thời điểm một truy vấn quan sát.
- **Persistence invariant:** database không cho phép hai bản ghi vi phạm một khóa độc nhất tại trạng thái đã commit.

`@Valid` / `@Validated` không tự biến một truy vấn kiểm tra duplicate thành giao dịch atomic. `@Column(unique=true)` hoặc `@Table(uniqueConstraints=...)` có thể giúp Hibernate tạo DDL khi bật schema generation, nhưng production nên quản lý constraints qua migration và xác nhận constraint thực sự hiện diện ở database.

## 3. Vì sao @Transactional không tự giải quyết check-then-insert?

Nhiều code viết:

```java
@Transactional
public Account create(String usernameKey) {
    if (repository.existsByUsernameKey(usernameKey)) {
        throw new DuplicateUsernameException();
    }
    return repository.save(new Account(usernameKey));
}
```

Đây là **snippet** giả định classes đã được định nghĩa. `@Transactional` khiến một chuỗi thao tác tham gia vào transaction, nhưng nó **không bảo đảm** hai transactions đồng thời không cùng đọc “chưa tồn tại”.

Dưới isolation phổ biến `READ_COMMITTED`, hai transactions có thể cùng chạy truy vấn exists trước khi một giao dịch commit. Nếu không có unique constraint, cả hai có thể ghi. Khi có unique constraint, database buộc phải xử lý conflict của khóa trùng.

### 3.1. Transaction isolation liên quan ra sao?

- `READ_COMMITTED`: mỗi truy vấn có thể thấy dữ liệu đã commit trước thời điểm truy vấn; không chặn mặc định hai “exists=false” cùng lúc.
- `REPEATABLE_READ`: đảm bảo quan sát lặp lại theo semantics database, nhưng không nên suy rằng một truy vấn “không thấy dòng” đã khóa tên username chưa tồn tại.
- `SERIALIZABLE`: database có thể phát hiện xung đột serialization và abort một transaction; ứng dụng phải biết xử lý retry đúng phạm vi. Nó có chi phí và semantics riêng theo database. Không dùng tăng isolation như một cách “đỡ phải tạo unique index” cho bất biến đơn giản.
- `SELECT ... FOR UPDATE`: thường khóa **những dòng tồn tại được chọn**. Khi dòng chưa tồn tại, không có row cụ thể để khóa; một số database có gap/predicate locking riêng nhưng không portable. Không coi `@Lock(PESSIMISTIC_WRITE)` trên kết quả không tồn tại là giải pháp chung.

**Kết luận thực dụng:** với tính duy nhất của username/email, **unique constraint** là yêu cầu nền; transaction, locks, retries và query kiểm tra sớm là các công cụ bổ sung cho workflow cụ thể.

### 3.2. Unique key giải quyết check-then-act như thế nào?

Khi hai transactions cố insert cùng key, hệ quản trị cơ sở dữ liệu phối hợp kiểm tra tính duy nhất trên unique index/constraint. Tùy DB và tình trạng transaction, một thao tác có thể chờ transaction kia quyết định commit hay rollback. Nếu transaction trước rollback, giao dịch sau có thể tiếp tục; nếu trước commit, giao dịch còn lại bị báo conflict. Không được tự hứa **request A luôn thắng** chỉ vì gửi sớm hơn.

Trên PostgreSQL, unique constraints được thực thi bằng unique indexes. Tài liệu mô tả rõ trường hợp concurrent insert và cách `INSERT ... ON CONFLICT` sử dụng unique arbiter. Các chi tiết locking, deadlock, timeout, retries vẫn phụ thuộc database; app phải xử lý error/timeout thực tế.

## 4. Thiết kế unique constraint đúng phạm vi

### 4.1. Khóa duy nhất một cột

SQL minh họa:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username_key VARCHAR(24) NOT NULL,
    CONSTRAINT uk_accounts_username_key UNIQUE (username_key)
);
```

Ý nghĩa:

- `id` là primary key kỹ thuật.
- `username_key` là giá trị chuẩn hóa dành cho so sánh uniqueness.
- `NOT NULL` ngăn bỏ trống ở tầng DB.
- `UNIQUE` chặn trùng giá trị khóa theo collation/kiểu dữ liệu của DB.
- Tên `uk_accounts_username_key` giúp migration, logging và phân loại exception dễ theo dõi.

Lưu ý `NOT NULL` chưa đảm bảo nonblank: chuỗi rỗng có thể vẫn hợp lệ ở DB. Input `@NotBlank` và business normalization là lớp riêng; nếu các writers ngoài Spring có thể ghi trực tiếp, cần cân nhắc `CHECK` constraint hoặc schema strategy tương ứng.

### 4.2. Độc nhất theo tenant (composite unique)

Trong ứng dụng đa tenant, cùng username có thể được dùng ở những tenant khác nhau:

```sql
CREATE TABLE tenant_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    username_key VARCHAR(24) NOT NULL,
    CONSTRAINT uk_tenant_username UNIQUE (tenant_id, username_key)
);
```

Không được gắn `UNIQUE(username_key)` toàn cục nếu product rule chỉ yêu cầu không trùng trong **mỗi tenant**.

Repository cần truy vấn đúng scope:

```java
boolean existsByTenantIdAndUsernameKey(
        Long tenantId, String usernameKey);
```

Nhưng ngay cả query đủ cả hai điều kiện vẫn **không thay thế** composite unique constraint. Ngoài ra `tenantId` phải đến từ ngữ cảnh đã xác thực/ủy quyền, không được tin giá trị tenant do client tự đưa vào JSON để quyết định phạm vi security.

### 4.3. Soft delete và partial unique index

Một product có thể cho phép dùng lại username sau khi account cũ đã soft delete. Unique toàn bộ `username_key` sẽ tiếp tục chặn tài khoản mới. Trên PostgreSQL, có thể chọn:

```sql
CREATE UNIQUE INDEX uk_active_username_key
ON accounts (username_key)
WHERE deleted_at IS NULL;
```

Đây là **PostgreSQL-specific partial unique index**; không copy vào mọi DBMS mà không kiểm tra hỗ trợ. Đồng thời phải hiểu:

- Khôi phục một account đã soft delete có thể gây conflict khi username đã được sử dụng lại.
- Các trạng thái soft delete và restore phải có business policy.
- Nếu muốn mỗi tenant chỉ có một active username, index có thể dùng `(tenant_id, username_key) WHERE deleted_at IS NULL`.
- JPA `@UniqueConstraint` cơ bản không biểu diễn đầy đủ partial index, vì vậy cần migration SQL riêng.
- Một số logic như “chỉ một booking active trong cùng khoảng thời gian” không thể giải đơn giản bằng `UNIQUE(room_id, start_at)`; có thể cần exclusion constraints hoặc transactional reservation design.

### 4.4. NULL và uniqueness

Trong PostgreSQL, unique constraint thông thường coi các `NULL` là khác nhau khi kiểm tra uniqueness, vì thế nhiều bản ghi có thể chứa NULL trong cột UNIQUE. PostgreSQL có lựa chọn `NULLS NOT DISTINCT` cho trường hợp cần semantics khác. Các DBMS khác có quy tắc không hoàn toàn giống nhau.

Đối với username/email **bắt buộc**, cách rõ ràng nhất là khai báo `NOT NULL` và validate input. Không coi `UNIQUE` là đồng nghĩa `NOT NULL`.

## 5. Chuẩn hóa khóa: “Lan” và “lan” có được coi là trùng?

`UNIQUE` bảo đảm uniqueness theo **giá trị và collation đã chọn**. Nếu ứng dụng muốn username không phân biệt chữ hoa/thường, cần định nghĩa normalization policy và kiểm tra nó trên **mọi đường ghi**.

Với demo, username chỉ cho phép **ASCII chữ cái, chữ số và dấu gạch dưới**. Có thể chuẩn hóa:

```java
String key = username.toLowerCase(Locale.ROOT);
```

Vì có input policy ASCII, thao tác lower-case này rõ nghĩa cho use case. `Locale.ROOT` tránh ảnh hưởng locale máy chủ như quy tắc lowercase của một số ngôn ngữ.

Bảng hành vi demo:

| Input | Giá trị lưu `username_key` | Kết quả |
| --- | --- | --- |
| `Lan_01` | `lan_01` | Tạo mới nếu chưa tồn tại |
| `LAN_01` | `lan_01` | Conflict nếu đã có `Lan_01` |
| `lan_02` | `lan_02` | Khác với `lan_01` |
| `Lan 01` | Không qua `@Pattern` | HTTP 400, không insert |
| `Đặng` | Không qua `@Pattern` ASCII | HTTP 400 trong **demo** |

**Không suy diễn quy tắc này sang email hoặc mọi tên Unicode**. Email có quy định và thực tế vận hành về local part, domain, IDN, plus-addressing và provider-specific aliases; tự hạ chữ hoa/thường hoặc loại dấu chấm/plus trên email có thể tạo va chạm sai. Unicode names cũng cần chiến lược normalization/collation và chống confusables được thiết kế theo product. Với identifier business, hãy ghi rõ “hai giá trị nào được xem là trùng” trước khi thiết kế index.

**Rủi ro mismatch:** code kiểm tra `existsByUsernameKey(raw)` nhưng khi insert lại lưu `raw.toLowerCase(...)`, hoặc hai service dùng normalization khác nhau, sẽ cho UX sai. Nên chuẩn hóa ở một điểm logic có test, ràng buộc đúng cột lưu và migration/backfill nhất quán.

## 6. Có nên viết custom Jakarta @UniqueUsername validator?

Một custom constraint thường có dạng:

```java
public class UniqueUsernameValidator
        implements ConstraintValidator<UniqueUsername, String> {

    private final AccountRepository repository;

    @Override
    public boolean isValid(
            String username, ConstraintValidatorContext context) {

        if (username == null) {
            return true;
        }

        return !repository.existsByUsernameKey(
                username.toLowerCase(Locale.ROOT)
        );
    }
}
```

Đây là **snippet minh họa**, giả định annotation `@UniqueUsername`, imports và repository tồn tại. Nó có thể cải thiện UX bằng cách báo “username đã được dùng” ngay ở validation layer, nhưng vẫn có **race** giữa `isValid` và `INSERT`. Không dùng nó làm cơ chế uniqueness duy nhất.

Các giới hạn thực tế:

- Một request khác có thể insert ngay sau khi validator trả true.
- Validator chạy DB query; có chi phí/latency, có thể tạo hiệu ứng N+1 khi validation nhiều phần tử.
- Khi **cập nhật** profile, validator phải bỏ qua chính bản ghi đang được sửa, tránh tự báo duplicate. Cần identity và tenant scope đáng tin cậy.
- Các luồng ngoài HTTP, batch imports, admin tools, event consumers hoặc migration có thể không chạy Bean Validation.
- Không gửi thông tin nhạy cảm/khả năng enumerate account trong message public khi không được phép.
- Jakarta Validation không phải công cụ quản lý locks/transactions.
- Custom constraint sai kiểu hoặc thiếu DI/validator provider có thể khiến request lỗi không như kỳ vọng.

Với Spring MVC, thường chỉ cần format checks (`@NotBlank`, `@Pattern`, `@Size`) và DB unique constraint; nếu có chức năng preview availability thì làm endpoint advisory riêng. Không gọi `@UniqueUsername` là “đã giải quyết concurrency” trong code review.

## 7. Spring Data JPA: save, flush và commit là ba khái niệm khác

### 7.1. save(entity) không luôn ghi SQL ngay tại chỗ

`JpaRepository#save` làm việc qua persistence context. SQL insert có thể xảy ra ngay hoặc bị trì hoãn, tùy entity identifier generation, flush mode và JPA provider. Với `GenerationType.IDENTITY`, provider thường cần INSERT sớm để nhận khóa sinh ra; điều đó **không** có nghĩa tất cả entity/DB đều ghi ngay tại `save()`.

Vì thế:

```java
repository.save(entity);
```

không bảo đảm unique constraint exception sẽ luôn ném **trong đúng dòng** code đó. Lỗi có thể xuất hiện khi flush/commit.

### 7.2. saveAndFlush đẩy thay đổi xuống DB, chưa phải commit

`JpaRepository#saveAndFlush` lưu entity và gọi flush ngay trong transaction:

```java
AccountEntity saved = repository.saveAndFlush(entity);
```

Điều này hữu ích khi muốn phát hiện DB constraint violation sớm với **immediate/non-deferrable constraint**. Nhưng `flush` không phải `commit`:

- Flush gửi SQL cần thiết tới database.
- Transaction còn có thể rollback.
- Deferrable constraints (nếu database hỗ trợ) có thể được kiểm tra tại commit.
- Một số lỗi transaction/commit khác vẫn có thể xuất hiện khi transaction kết thúc.

**Không hứa “saveAndFlush đảm bảo mọi DB error đã xảy ra trước khi method trả về”**. Cần hiểu transaction boundaries.

### 7.3. @Transactional ở service thay đổi nơi exception xuất hiện

Nếu service có:

```java
@Transactional
public AccountEntity create(AccountEntity account) {
    return repository.save(account);
}
```

thì commit thường xảy ra **sau khi body của service method hoàn tất**, khi transaction interceptor kết thúc. Một `try/catch` **bên trong** body có thể không bắt được lỗi phát sinh lúc commit ở bên ngoài body. Ngược lại, controller gọi qua Spring proxy có thể nhận exception sau khi method service thoát.

Nếu `saveAndFlush` ném lỗi constraint bên trong một transaction lớn, transaction đó có thể đã bị đánh dấu rollback-only hoặc không còn an toàn để tiếp tục. **Không** catch `DataIntegrityViolationException` rồi tiếp tục nhiều writes trong cùng transaction như thể chưa có gì xảy ra.

Dự án runnable sau **cố ý không đặt `@Transactional` trên registration service**: lời gọi repository `saveAndFlush` sử dụng transaction boundary của repository proxy; lỗi uniqueness được chuyển ra cho controller advice. Đây là cách đơn giản để minh họa. Một use case production có nhiều bước cần một transaction service đúng nghĩa và error translation ở **bên ngoài transaction boundary** hoặc một thiết kế retry có chủ đích.

### 7.4. Spring chuyển DB errors thành exception nào?

Trong Spring Data/JPA, nhiều vi phạm unique, not-null, foreign key... được dịch thành:

```java
org.springframework.dao.DataIntegrityViolationException
```

Đó là exception **khá rộng**, không có nghĩa mọi trường hợp đều là duplicate username. Provider có thể có nested cause như Hibernate `org.hibernate.exception.ConstraintViolationException` hoặc SQL exception cung cấp SQLSTATE/vendor code/constraint name.

Trong ví dụ nhỏ chỉ có một business uniqueness constraint rõ ràng, handler dùng code `DATA_CONFLICT` và HTTP 409 cho lỗi integrity. **Trong hệ thống thật**, phải phân loại constraint cụ thể:

- Biết chắc unique key nào vi phạm → map sang `USERNAME_ALREADY_TAKEN`, HTTP 409 hoặc status đã được API contract định nghĩa.
- Foreign key, check/not-null lỗi do bug server → thường không nên tự nhận là “username trùng”.
- Deadlock, timeout, transient failure → không được trá hình thành duplicate; cần policy retry/backoff riêng.
- Không trả nguyên SQL, constraint stacktrace hoặc message của driver cho client.

Tùy database, PostgreSQL dùng SQLSTATE `23505` cho `unique_violation`. Tuy vậy, chỉ so SQLSTATE có thể chưa xác định được **constraint nào** khi table có nhiều unique indexes. Tên ràng buộc + schema domain mapping thường rõ hơn; cách trích xuất nằm trong provider/driver và phải có test theo database thật.

## 8. Ví dụ đầy đủ: đăng ký username với ràng buộc tại database

Project dùng Spring Boot 3.3.6, Java 17, Spring Data JPA, Hibernate Validator và H2.

Mục tiêu:

1. `POST /api/registrations` nhận JSON có username, validate format.
2. Chuẩn hóa username ASCII về lower-case.
3. Database có unique constraint `uk_accounts_username_key` trên `username_key`.
4. Chỉ insert, **không pre-check** trong đường tạo mới; database là nguồn quyết định.
5. Khi DB chặn conflict, advice trả HTTP **409** với mã an toàn `DATA_CONFLICT`, không lộ SQL.
6. `GET /api/usernames/availability` trả `available` để UI tham khảo, nhưng **không bảo đảm username còn trống lúc POST**.
7. Kiểm thử hai luồng đồng thời cùng insert username; cuối cùng đúng một bản ghi tồn tại.

### 8.1. Cấu trúc project

```text
unique-username-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/uniqueusername/
        UniqueUsernameApplication.java
        AccountEntity.java
        AccountRepository.java
        RegistrationRequest.java
        RegistrationResponse.java
        AvailabilityResponse.java
        ApiError.java
        RegistrationService.java
        RegistrationController.java
        RegistrationErrorAdvice.java
      resources/
        application.properties
    test/
      java/com/example/uniqueusername/
        RegistrationIntegrationTest.java
```

### 8.2. Gradle build

Tệp `settings.gradle`:

```groovy
rootProject.name = 'unique-username-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong demo, `Hibernate` tạo schema từ JPA annotations. Đó là lựa chọn cho môi trường học, không phải khuyến nghị chạy schema generation `create-drop` trên production.

### 8.3. application.properties

Tệp `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:unique_username_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.hikari.maximum-pool-size=8

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.format_sql=true
```

H2 là in-memory DB; mỗi lần khởi động mới có thể tạo database lại. `create-drop` phá/xây schema khi lifecycle chạy — **không dùng trong môi trường cần giữ dữ liệu thật**. Tài liệu SQL migration production được thảo luận sau phần test.

Dòng Hikari pool size giúp test hai luồng có đủ connections; nó không tạo ra bất kỳ bảo đảm uniqueness nào.

### 8.4. Main application

Tệp `src/main/java/com/example/uniqueusername/UniqueUsernameApplication.java`:

```java
package com.example.uniqueusername;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UniqueUsernameApplication {

    public static void main(String[] args) {
        SpringApplication.run(UniqueUsernameApplication.class, args);
    }
}
```

### 8.5. Entity và unique constraint

Tệp `src/main/java/com/example/uniqueusername/AccountEntity.java`:

```java
package com.example.uniqueusername;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "accounts",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_accounts_username_key",
                columnNames = "username_key"
        )
)
public class AccountEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
            name = "username_key",
            nullable = false,
            length = 24
    )
    private String usernameKey;

    protected AccountEntity() {
        // JPA yêu cầu constructor không tham số.
    }

    public AccountEntity(String usernameKey) {
        this.usernameKey = usernameKey;
    }

    public Long getId() {
        return id;
    }

    public String getUsernameKey() {
        return usernameKey;
    }
}
```

Ở đây `@Table(uniqueConstraints=...)` mô tả uniqueness trong JPA metadata. Khi Hibernate chạy `ddl-auto=create-drop`, nó tạo constraint/index tương ứng trong H2.

**Kiểm chứng schema là bắt buộc:** nếu ứng dụng dùng `spring.jpa.hibernate.ddl-auto=validate` hoặc `none` trên database thật, annotation **không tự tạo schema mới**. Cần Flyway/Liquibase/manual migration để đảm bảo constraint thực sự tồn tại.

### 8.6. Repository

Tệp `src/main/java/com/example/uniqueusername/AccountRepository.java`:

```java
package com.example.uniqueusername;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<AccountEntity, Long> {

    boolean existsByUsernameKey(String usernameKey);

    long countByUsernameKey(String usernameKey);
}
```

`existsByUsernameKey` chỉ là một read query. Nó có thể trả false rồi ngay sau đó một writer khác insert cùng username. `countByUsernameKey` hỗ trợ test/observability, không phải thay thế unique constraint.

### 8.7. DTO request, response và lỗi

Tệp `src/main/java/com/example/uniqueusername/RegistrationRequest.java`:

```java
package com.example.uniqueusername;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record RegistrationRequest(
        @NotBlank
        @Size(min = 3, max = 24)
        @Pattern(regexp = "[A-Za-z0-9_]+")
        String username
) {}
```

Chỉ hỗ trợ username ASCII [A–Z], [a–z], [0–9] và gạch dưới; dài từ 3 đến 24 ký tự. Đây là **domain policy của demo**, không phải giới hạn chung của Spring.

Tệp `src/main/java/com/example/uniqueusername/RegistrationResponse.java`:

```java
package com.example.uniqueusername;

public record RegistrationResponse(
        Long id,
        String username
) {}
```

Tệp `src/main/java/com/example/uniqueusername/AvailabilityResponse.java`:

```java
package com.example.uniqueusername;

public record AvailabilityResponse(
        String username,
        boolean available
) {}
```

Tệp `src/main/java/com/example/uniqueusername/ApiError.java`:

```java
package com.example.uniqueusername;

public record ApiError(
        String code,
        String message
) {}
```

Response thành công chỉ trả ID và canonical username, không xuất JPA entity trực tiếp. API lỗi giữ **machine code** ổn định và message đã kiểm soát; không phản chiếu raw DB error.

### 8.8. Service: insert là nơi DB quyết định

Tệp `src/main/java/com/example/uniqueusername/RegistrationService.java`:

```java
package com.example.uniqueusername;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {

    private final AccountRepository accounts;

    public RegistrationService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    public RegistrationResponse register(
            RegistrationRequest request) {

        String key = canonical(request.username());

        // KHÔNG có pre-check bắt buộc trước insert.
        // Database UNIQUE(username_key) là hàng rào cuối cùng.
        AccountEntity saved = accounts.saveAndFlush(
                new AccountEntity(key)
        );

        return new RegistrationResponse(
                saved.getId(),
                saved.getUsernameKey()
        );
    }

    public AvailabilityResponse checkAvailability(String username) {
        if (username == null
                || !username.matches("[A-Za-z0-9_]{3,24}")) {

            return new AvailabilityResponse(username, false);
        }

        String key = canonical(username);

        // Chỉ là một snapshot phục vụ UX.
        // true KHÔNG có nghĩa POST tiếp theo chắc chắn thành công.
        boolean available = !accounts.existsByUsernameKey(key);

        return new AvailabilityResponse(key, available);
    }

    private static String canonical(String username) {
        return username.toLowerCase(Locale.ROOT);
    }
}
```

**Tại sao method `register` không có `@Transactional` ở class/service?**

Trong ví dụ đơn giản, `JpaRepository#saveAndFlush` có transaction boundary do Spring Data repository quản lý. Không có outer service transaction, repository call phải hoàn tất hoặc ném exception trước khi service trả response. Điều này giúp test lặp/đồng thời dễ hiểu. Không nên áp dụng máy móc mô hình này cho nghiệp vụ gồm nhiều bảng cần transaction atomic; hãy dùng service transaction rõ và xử lý error **bên ngoài** ranh giới transaction.

**Tại sao không gọi `existsBy...` trước khi insert?**

Để nhấn mạnh invariant do unique constraint bảo vệ. Một pre-check có thể được thêm để UX tốt hơn nhưng không làm tăng guarantee nếu database đã có constraint. Hơn nữa, pre-check thêm một round trip cho mọi request. Endpoint `checkAvailability` có riêng để minh họa kết quả mang tính thời điểm.

### 8.9. REST controller

Tệp `src/main/java/com/example/uniqueusername/RegistrationController.java`:

```java
package com.example.uniqueusername;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RegistrationController {

    private final RegistrationService registration;

    public RegistrationController(
            RegistrationService registration) {

        this.registration = registration;
    }

    @PostMapping(
            path = "/registrations",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    @ResponseStatus(HttpStatus.CREATED)
    public RegistrationResponse register(
            @Valid @RequestBody RegistrationRequest request) {

        return registration.register(request);
    }

    @GetMapping("/usernames/availability")
    public AvailabilityResponse availability(
            @RequestParam String username) {

        return registration.checkAvailability(username);
    }
}
```

`@Valid` kiểm tra định dạng username trước khi service chạy. Kiểm tra `@Pattern` và `@Size` không chứng minh uniqueness. HTTP 201 thành công chỉ xảy ra sau khi repository insert và transaction hoàn tất theo luồng demo. Với workflow production nhiều bước, có thể phải cân nhắc transaction commit, messaging/outbox và thời điểm trả response.

### 8.10. @RestControllerAdvice xử lý 400, 409 và JSON parse error

Tệp `src/main/java/com/example/uniqueusername/RegistrationErrorAdvice.java`:

```java
package com.example.uniqueusername;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RegistrationErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_INPUT",
                        "Username must contain 3-24 ASCII letters, "
                                + "digits or underscores"
                )
        );
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiError> dataConflict(
            DataIntegrityViolationException exception) {

        // Demo có một business UNIQUE constraint trên username.
        // Trả mã generic; không tiết lộ tên constraint/SQL.
        return ResponseEntity.status(409).body(
                new ApiError(
                        "DATA_CONFLICT",
                        "The requested value conflicts with existing data"
                )
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_JSON",
                        "Cannot read the request JSON"
                )
        );
    }
}
```

**Giới hạn rất quan trọng của demo:** handler `DataIntegrityViolationException` đang map cả nhóm integrity errors về 409 generic. Trong API production chứa nhiều constraints, **không** nên gắn nhãn `USERNAME_TAKEN` cho mọi `DataIntegrityViolationException`. Hãy xác định rõ constraint vi phạm qua SQLSTATE/constraint name có test với DB thật; map đúng business conflicts, còn foreign-key/not-null/check lỗi khác cần phân loại riêng và có thể báo 400/409/500 tùy lỗi thuộc client hay server. 409 là quyết định API phù hợp cho resource conflict, không phải quy định mọi duplicate constraint bắt buộc trả 409.

Đặc biệt, đừng:

```java
return ResponseEntity.status(409).body(
        exception.getMostSpecificCause().getMessage()
);
```

Raw DB message có thể lộ schema, SQL, tên table, dữ liệu người dùng hoặc chi tiết nội bộ. Gửi mã máy và message an toàn; log server có thể ghi constraint identifier đã lọc và correlation ID.

## 9. Chạy ứng dụng và thử bằng curl

Tạo Gradle wrapper nếu chưa có; trong project đã có wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

### 9.1. Đăng ký mới

```bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H 'Content-Type: application/json' \
  -d '{"username":"Lan_01"}'
```

**Kỳ vọng HTTP 201**, JSON minh họa:

```json
{
  "id": 1,
  "username": "lan_01"
}
```

ID có thể khác `1` nếu DB đã có dữ liệu hoặc sequence/identity đã tiến lên. Phần quan trọng là username được lưu chuẩn hóa và request thành công.

### 9.2. Đăng ký trùng khác chữ hoa/chữ thường

```bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H 'Content-Type: application/json' \
  -d '{"username":"LAN_01"}'
```

Do cả hai được chuyển về `lan_01`, unique constraint chặn insert. **Kỳ vọng HTTP 409**:

```json
{
  "code": "DATA_CONFLICT",
  "message": "The requested value conflicts with existing data"
}
```

Dù service không gọi `existsByUsernameKey` trong `register`, database vẫn ngăn duplicate.

### 9.3. Kiểm tra availability chỉ là snapshot

```bash
curl -i 'http://localhost:8080/api/usernames/availability?username=Lan_01'
```

Nếu đã đăng ký `lan_01`, HTTP 200:

```json
{"username":"lan_01","available":false}
```

Nếu gọi với username chưa có:

```json
{"username":"other_01","available":true}
```

**available=true** chỉ mô tả thời điểm query. Một request khác có thể đăng ký `other_01` trước khi client này POST. Frontend phải chuẩn bị xử lý 409 ngay cả sau khi đã hiển thị dấu kiểm màu xanh.

### 9.4. Input sai định dạng

```bash
curl -i -X POST http://localhost:8080/api/registrations \
  -H 'Content-Type: application/json' \
  -d '{"username":"bad name"}'
```

Username chứa khoảng trắng, vi phạm `@Pattern`. **Kỳ vọng HTTP 400** với `INVALID_INPUT`. Đây là lỗi validation, khác với uniqueness conflict xảy ra lúc DB insert.

## 10. Integration tests: xác minh unique index và race condition

Tệp `src/test/java/com/example/uniqueusername/RegistrationIntegrationTest.java`:

```java
package com.example.uniqueusername;

import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    RegistrationService registration;

    @Autowired
    AccountRepository accounts;

    private ResultActions postUsername(String username)
            throws Exception {

        return mvc.perform(post("/api/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + username + "\"}"));
    }

    @Test
    void registrationCreatesCanonicalUsername() throws Exception {
        postUsername("Alpha377")
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.username").value("alpha377"));

        assertEquals(1, accounts.countByUsernameKey("alpha377"));
    }

    @Test
    void duplicateUsernameReturnsConflict() throws Exception {
        postUsername("Beta377")
            .andExpect(status().isCreated());

        postUsername("Beta377")
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("DATA_CONFLICT"));

        assertEquals(1, accounts.countByUsernameKey("beta377"));
    }

    @Test
    void caseVariantsUseTheSameUniqueKey() throws Exception {
        postUsername("Camel377")
            .andExpect(status().isCreated());

        postUsername("CAMEL377")
            .andExpect(status().isConflict());

        assertEquals(1, accounts.countByUsernameKey("camel377"));
    }

    @Test
    void availabilityIsOnlyAReadSnapshot() throws Exception {
        mvc.perform(get("/api/usernames/availability")
                .param("username", "Find377"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("find377"))
            .andExpect(jsonPath("$.available").value(true));

        postUsername("Find377")
            .andExpect(status().isCreated());

        mvc.perform(get("/api/usernames/availability")
                .param("username", "FIND377"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.available").value(false));
    }

    @Test
    void invalidFormatFailsBeforePersistence() throws Exception {
        postUsername("bad name")
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));

        assertEquals(0, accounts.countByUsernameKey("bad name"));
    }

    @Test
    void malformedJsonIsNotUniquenessFailure() throws Exception {
        mvc.perform(post("/api/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void concurrentRegistrationsProduceOneWinner() throws Exception {
        // Không đặt @Transactional trên test: các worker threads
        // cần repository transaction của chính chúng.
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<String> attempt = () -> {
            ready.countDown();

            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Start gate timed out");
            }

            try {
                registration.register(
                        new RegistrationRequest("Race377")
                );
                return "CREATED";
            } catch (DataIntegrityViolationException expected) {
                return "CONFLICT";
            }
        };

        try {
            Future<String> one = executor.submit(attempt);
            Future<String> two = executor.submit(attempt);

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            List<String> outcomes = List.of(
                    one.get(15, TimeUnit.SECONDS),
                    two.get(15, TimeUnit.SECONDS)
            );

            assertEquals(
                    1, Collections.frequency(outcomes, "CREATED")
            );
            assertEquals(
                    1, Collections.frequency(outcomes, "CONFLICT")
            );
            assertEquals(
                    1, accounts.countByUsernameKey("race377")
            );
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    @Test
    void differentNamesAreBothAllowed() throws Exception {
        postUsername("DistinctA377")
            .andExpect(status().isCreated());

        postUsername("DistinctB377")
            .andExpect(status().isCreated());

        assertEquals(1, accounts.countByUsernameKey("distincta377"));
        assertEquals(1, accounts.countByUsernameKey("distinctb377"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Kỳ vọng tám test PASS** trong môi trường đúng dependency, H2 và Java 17. Đây là expected behavior của mã ví dụ; không có tuyên bố đã chạy JUnit/Gradle thực tế trong lúc biên soạn bài.

### 10.1. Vì sao test concurrency có giá trị?

Test `concurrentRegistrationsProduceOneWinner` dùng hai threads, mỗi thread gọi service một lần. Hai `CountDownLatch` giúp hai tác vụ bắt đầu gần cùng lúc; test sau đó xác nhận **đúng một thành công, một conflict và một row tồn tại**.

Điều này không chứng minh hai SELECT `exists` đã chạy đồng thời, vì production code không pre-check. Nó chứng minh DB uniqueness được kiểm tra ngay cả khi hai thao tác insert tranh chấp.

**Race test không nên giả định request nào thắng.** Cả hai đều cùng đăng ký `Race377`; kết quả mong đợi là multiset `{CREATED, CONFLICT}`, không phải thread A luôn thắng. Test cũng không nên giả định giá trị identity ID, độ trễ của mỗi insert hoặc thứ tự log.

Nếu dùng DB thật (PostgreSQL/MySQL), nên chạy thêm integration tests qua Testcontainers hoặc CI environment tương đương. H2 giúp minh họa nhưng không thay thế kiểm thử locks/isolation, SQLSTATE, deferrable constraints và đặc tính race của DB production.

### 10.2. Vì sao test không có @Transactional?

Trong Spring Test, một test method `@Transactional` có thể tạo transaction và rollback khi kết thúc. Nếu bên trong test mở threads mới, transaction context không tự truyền qua mọi worker thread, khiến quan sát khó đoán hoặc dữ liệu bị cô lập bất ngờ.

Với bài test concurrency này, không gắn `@Transactional` trên test class/method; mỗi call repository được xử lý trong transaction riêng của nó. Khi test kết thúc, có thể query đếm row đã commit.

Không dùng `Thread.sleep(100)` làm biện pháp đồng bộ chính; sleep không tạo ra quan hệ bắt đầu rõ ràng. `CountDownLatch` giúp test ít phụ thuộc timing hơn, dù việc tạo race chính xác vẫn cần môi trường DB và orchestration phù hợp.

## 11. Cách thấy lỗi của check-then-insert bằng một lịch trình chủ động

Bài runnable bảo vệ bằng unique constraint. Để hiểu vì sao pre-check yếu, xem phép mô phỏng logic:

```text
Repository.existsByUsernameKey("demo") ở T1 -> false
Repository.existsByUsernameKey("demo") ở T2 -> false

T1: INSERT accounts(username_key) VALUES ('demo')
T2: INSERT accounts(username_key) VALUES ('demo')

Nếu có UNIQUE:
  một transaction phải bị từ chối hoặc xử lý conflict theo DB policy.

Nếu KHÔNG có UNIQUE:
  T1 và T2 có thể cùng commit -> trùng dữ liệu.
```

Một unit test mock:

```java
when(repository.existsByUsernameKey("demo"))
        .thenReturn(false)
        .thenReturn(false);
```

chỉ chứng minh hai checks có thể đều trả false; **nó không kiểm tra tranh chấp database**. Mocks không mô phỏng đầy đủ MVCC, locks, transaction commits hoặc violation. Để xác minh invariant, dùng integration test trên database thật hoặc test database có unique constraint.

Nếu muốn tạo race reproduction có chủ đích cho code dễ tổn thương, có thể dùng barrier giữa bước exists và bước insert trong một test-only service. **Không** đưa barrier/sleep vào production chỉ để làm test dễ tái hiện. Với schema thiếu unique, test có thể thấy hai rows; với schema có unique, sẽ có conflict.

## 12. PostgreSQL UPSERT và ON CONFLICT: khi nào dùng?

Trong PostgreSQL, nếu yêu cầu là “chỉ tạo nếu chưa có, không báo exception cho duplicate”, có thể dùng:

```sql
INSERT INTO accounts (username_key)
VALUES ('lan')
ON CONFLICT (username_key) DO NOTHING
RETURNING id;
```

Khi conflict, thao tác có thể không insert row và `RETURNING` không có row. Ứng dụng phải xác định UX:

- Trả 409 vì username đã được sử dụng.
- Trả một response idempotent nếu cùng principal đang yêu cầu lặp một thao tác **được định nghĩa là idempotent**.
- Không mặc định “DO NOTHING” là thành công; client có thể lầm tưởng tài khoản đã được tạo.

Một lựa chọn khác:

```sql
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-1', 1)
ON CONFLICT (sku)
DO UPDATE SET quantity = inventory.quantity + 1;
```

Đây là ví dụ upsert có chủ đích cho counter/inventory logic, không phải lời khuyên upsert account. `DO UPDATE` có semantics **ghi đè/cập nhật** và cần authorization, race analysis, isolation/idempotency. Không dùng “upsert user” để vượt qua quy tắc username đã thuộc tài khoản khác.

PostgreSQL `ON CONFLICT DO UPDATE` có đảm bảo atomic insert-or-update theo unique arbiter trong phạm vi quy định của hệ quản trị. Nhưng không tự giải quyết mọi vấn đề business như gửi email hai lần, thanh toán trùng hoặc chính sách ownership.

**Database khác có cú pháp khác:** MySQL có `INSERT ... ON DUPLICATE KEY UPDATE`; SQL Server có các cơ chế riêng và các lưu ý concurrency của `MERGE`. Không bê một cú pháp vào mọi RDBMS rồi cho rằng semantics giống nhau.

## 13. Unique constraint không đồng nghĩa idempotency

Một request “tạo tài khoản username=lan” gửi hai lần có thể dẫn tới:

1. Lần đầu thành công 201.
2. Lần sau nhận 409 do unique constraint.

Điều này bảo vệ dữ liệu, nhưng **không có nghĩa** lần sau là retry an toàn của cùng một thao tác. Một request có thể mất HTTP response sau khi DB đã commit; client retry sẽ không biết lần trước đã tạo thành công hay chưa. Với API yêu cầu idempotency, cần thiết kế riêng.

Ví dụ hệ thống thanh toán có header:

```http
Idempotency-Key: 5ef...unique-per-operation...
```

Server có thể lưu một bản ghi request-id theo phạm vi principal và operation, có unique index tương ứng, đối chiếu hash payload, trạng thái đang xử lý và kết quả đã hoàn thành. Nếu cùng idempotency key nhưng payload khác, cần reject rõ ràng. Không chỉ thêm `UNIQUE(email)` rồi gọi thế là đã chống giao dịch lặp.

Một chiến lược thường dùng:

- `UNIQUE(idempotency_key, principal_id)` theo scope.
- Atomic transaction giữa record idempotency và business writes.
- Trạng thái xử lý rõ ràng, TTL/retention phù hợp, concurrency claim.
- Trả lại response cũ cho retry hợp lệ theo API contract.

Đây là thiết kế lớn hơn uniqueness của username; phân biệt chúng giúp tránh bug tạo đơn hàng/thu tiền hai lần.

## 14. Update, restore, delete và migration cũng phải bảo vệ uniqueness

### 14.1. Không chỉ INSERT mới có conflict

Khi đổi username:

```sql
UPDATE accounts
SET username_key = 'lan'
WHERE id = 42;
```

Nếu `lan` đã thuộc một account khác, unique constraint cũng chặn UPDATE. Service “rename” có thể làm pre-check để báo sớm, nhưng phải xử lý DB conflict cuối cùng.

### 14.2. Trước khi thêm constraint cần tìm và xử lý dữ liệu trùng

Nếu bảng cũ đã có duplicates, tạo unique index có thể fail. SQL kiểm tra minh họa:

```sql
SELECT username_key, COUNT(*) AS occurrences
FROM accounts
GROUP BY username_key
HAVING COUNT(*) > 1;
```

Đối với chính sách case-insensitive, phải backfill canonical key rồi kiểm tra duplicates **trên canonical key**, không chỉ trên giá trị hiển thị. Cần quyết định quyền sở hữu, merge, rename hoặc xử lý conflict có kiểm soát. Không xóa ngẫu nhiên một trong hai tài khoản chỉ để migration thành công.

Trong hệ thống lớn, tạo index đồng thời/online có lưu ý locking, triển khai theo từng bước và rollback plan. Ở PostgreSQL, `CREATE UNIQUE INDEX CONCURRENTLY` giảm chặn writes so với tạo index thông thường nhưng có caveats riêng (có thể fail khi gặp duplicates và cần xử lý invalid index). Không chạy migration nguy hiểm mà không đọc tài liệu database/version đang dùng.

### 14.3. Phân biệt @Column(unique=true) và migration

JPA:

```java
@Column(unique = true)
private String usernameKey;
```

là gợi ý DDL/schema mapping; có thể tiện ở demo. Trong production, schema thường được quản lý bởi Flyway/Liquibase với tên constraints và rollout rõ ràng. Bảo đảm code/JPA mapping, migration SQL và database thực tế tương thích. **Chỉ nhìn annotation Java không chứng minh DB đã có constraint**.

### 14.4. Nhiều service cùng ghi một bảng

Nếu có HTTP service, batch job và event consumer cùng ghi account, một validation check trong HTTP controller không bảo vệ hai writer còn lại. Unique index ở database phục vụ mọi writer vào cùng datastore, nên là hàng rào tự nhiên.

Nếu dùng nhiều datastore/region độc lập rồi eventual consistency, không thể đơn giản suy rằng mỗi DB local unique là toàn cục unique. Cần chiến lược cấp phát ID/partition ownership, consensus hoặc conflict resolution phù hợp. Chủ đề concurrency ở distributed systems rộng hơn một RDBMS.

## 15. Error semantics: 400, 409, 422 và 500

Không có một HTTP status bắt buộc cho mọi loại vi phạm uniqueness; hãy thống nhất API contract. Một mapping tham khảo:

| Tình huống | Status thường dùng | Lưu ý |
| --- | --- | --- |
| Username chứa ký tự không hợp lệ | 400 Bad Request hoặc 422 | Validation input |
| Username đã được chiếm (được xác minh) | 409 Conflict | Tránh tiết lộ thông tin nhạy cảm |
| Duplicate idempotency key cùng payload | Có thể trả kết quả request trước | Theo idempotency contract |
| Duplicate idempotency key khác payload | 409 hoặc mã nghiệp vụ tương đương | Không âm thầm coi là thành công |
| Foreign key violation do bug service | Thường 500 hoặc mapping thích hợp | Không nói nhầm “username trùng” |
| Database deadlock/timeout | 5xx / retry policy tùy trường hợp | Không phải duplicate |
| JSON malformed | 400 | Chưa tạo được DTO |
| Trường bắt buộc thiếu | 400 | `@Valid` hoặc DB not-null tùy nơi phát hiện |

Trong demo, advice trả generic `DATA_CONFLICT` cho nhóm `DataIntegrityViolationException` để người học không phụ thuộc vào message/SQLSTATE của H2. Nếu product cần message cụ thể như “Tên đăng nhập đã được dùng”, cần xác định **đúng ràng buộc**, không đơn giản catch tất cả integrity failures.

### 15.1. Tránh information disclosure

Availability endpoint và 409 có thể trở thành công cụ enumerate usernames/emails. Với email cá nhân, nhiều hệ thống chọn thông điệp trung tính ở sign-up hoặc password reset; chính sách này phụ thuộc luồng xác minh danh tính, chống abuse và UX.

- Rate limit queries và registration attempts.
- Không lộ raw SQL exception.
- Không gửi rejected secrets trong message.
- Không trả ID hoặc thông tin profile của account đang sở hữu username.
- Ghi metrics theo error code và constraint đã xác thực; không cần log password/token.
- Tách authorization khỏi uniqueness. “Có một bản ghi trùng” không tự động cho phép client xem/sửa bản ghi đó.

## 16. Các lỗi phổ biến

**1. Chỉ dựa vào existsBy...** Hai concurrent requests có thể cùng thấy false; thiếu DB unique có nguy cơ tạo duplicates.

**2. Tin @Transactional tự làm exists+insert atomic.** Transaction không mặc định khóa một giá trị chưa tồn tại; phải hiểu isolation và constraint.

**3. Dùng @NotBlank/@Email/@Pattern để thay UNIQUE.** Format validation không bảo vệ bất biến giữa nhiều rows.

**4. Dùng custom @UniqueUsername và bỏ unique index.** Validator có check-then-act race, chỉ là UX optimization.

**5. Chỉ viết @Column(unique=true) trên entity rồi nghĩ production DB đã thay đổi.** Nếu không chạy migration/schema generation, constraint có thể chưa tồn tại.

**6. Không canonicalize trước cả đọc và ghi.** `Lan` và `lan` có thể trùng về business nhưng khác key lưu; hoặc pre-check sai field.

**7. Canonicalize email bằng quy tắc tùy ý.** Có thể gộp các địa chỉ khác nhau hoặc bỏ sót alias; cần policy phù hợp domain.

**8. Dùng UNIQUE nhưng quên NOT NULL.** Một số DB cho nhiều NULL theo unique semantics; dữ liệu bắt buộc vẫn có thể thiếu.

**9. Áp unique toàn hệ thống khi nghiệp vụ chỉ cần trong tenant.** Chặn sai giữa các tenant; dùng composite unique phù hợp.

**10. Soft-delete rồi cố tạo lại cùng key với unique toàn bảng.** Cần thiết kế partial index hoặc chính sách archive/restore.

**11. Tin save() luôn ném lỗi trong đúng dòng gọi.** Hibernate có thể gửi SQL khi flush/commit.

**12. Tin saveAndFlush() chính là commit.** Flush chưa kết thúc transaction; lỗi deferrable có thể xảy ra muộn.

**13. Bắt DataIntegrityViolationException trong transaction rồi tiếp tục lưu.** Transaction có thể rollback-only hoặc persistence context không an toàn.

**14. Catch mọi DataIntegrityViolationException và trả USERNAME_TAKEN.** Foreign key/not-null/check và nhiều unique constraints có thể gây cùng exception family.

**15. Bắt generic Exception rồi trả 409.** Che bugs, timeout, deadlock và lỗi hệ thống.

**16. Trả SQLSTATE/raw DB message cho client.** Có thể lộ thông tin schema và dữ liệu nhạy cảm.

**17. Retry duplicate insert vô hạn.** Duplicate là business conflict bền vững; retry không làm username tự hết trùng.

**18. Dùng @Lock(PESSIMISTIC_WRITE) cho row chưa tồn tại và nghĩ đã khóa được “khoảng trống”.** Semantics khác nhau theo DB/isolation, không portable.

**19. Dùng SERIALIZABLE để khỏi tạo unique constraint.** Đắt hơn, có serialization failures và retry; unique invariant vẫn nên được database thực thi.

**20. Dùng ON CONFLICT DO NOTHING rồi trả 201 Created vô điều kiện.** Không biết có row nào thật sự được tạo; cần kiểm tra kết quả.

**21. Dùng UPSERT để đăng ký account mà không xét ownership.** Có nguy cơ cập nhật bản ghi thuộc người khác.

**22. Dùng MockRepository để chứng minh race safety.** Mock không mô phỏng transaction/index/database concurrency.

**23. Test một luồng duy nhất.** Không phát hiện check-then-insert concurrency; cần tests concurrent và constraint tại schema.

**24. Gắn @Transactional lên concurrency test rồi mong threads chia sẻ cùng transaction.** Thread-bound transaction contexts không tự hoạt động theo cách đó.

**25. Coi username available=true là sự bảo đảm đặt chỗ.** Chỉ là snapshot; khi tạo vẫn phải xử lý 409.

**26. Thêm unique index lên bảng đang có duplicates mà không chuẩn bị migration.** Index creation có thể thất bại; cần inventory, cleanup và rollout.

## 17. Checklist code review

1. Xác định rõ business key: username/email/code thuộc phạm vi global hay tenant?
2. Xác định canonicalization/collation và hành vi với chữ hoa/thường, Unicode, null.
3. Có **UNIQUE** constraint/index thực sự trong database migration không?
4. Constraint có đúng danh sách cột và soft-delete predicate không?
5. Đầu vào có Bean Validation cho format/length/required không?
6. Không dùng `existsBy...` hoặc custom validator làm lớp bảo vệ duy nhất?
7. Nếu có check availability, UI có hiểu `available` chỉ là snapshot?
8. Có xử lý DB unique conflict kể cả khi pre-check vừa trả “available”?
9. Save/flush/transaction boundaries có rõ không, nhất là nơi bắt exception?
10. Có catch ở **ngoài** transaction bị rollback và tránh tiếp tục writes sau DB error?
11. Có phân loại đúng constraint khi table có nhiều unique/FK/check rules không?
12. Có map HTTP status/code an toàn, không trả SQL/driver internals?
13. Có migration/backfill xử lý dữ liệu trùng trước tạo index?
14. Có test input invalid, duplicate tuần tự, case variants và concurrency?
15. Race test có assert **đúng một row** và **đúng một conflict**, không giả định thread thắng?
16. Có test trên database production-like khi semantics SQL/locking quan trọng?
17. Nếu sử dụng UPSERT, có kiểm tra ảnh hưởng đến ownership, authorization và retry semantics?
18. Có thiết kế idempotency riêng nếu yêu cầu retry an toàn?
19. Có đo tỷ lệ unique conflicts, timeouts, deadlocks mà không lưu dữ liệu nhạy cảm?
20. Có kế hoạch rollout/rollback schema an toàn?

**Kết luận:** “Kiểm tra đã tồn tại chưa” là một lần quan sát **không được đặt chỗ**. Hai request có thể cùng đọc “chưa tồn tại” rồi cùng insert. Để duy trì tính duy nhất khi có tranh chấp, hãy **định nghĩa unique constraint/index tại database**, chuẩn hóa khóa nhất quán, xử lý lỗi ghi ở transaction boundary phù hợp và trả HTTP response an toàn. `existsBy...` hoặc custom `@UniqueUsername` chỉ cải thiện trải nghiệm, **không thay thế database invariant**. Với hệ thống thật, còn cần phân loại constraint, kiểm thử cạnh tranh trên database gần production và tách uniqueness khỏi idempotency.

## 18. Tài liệu tham khảo

- [PostgreSQL — Constraints / Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — unique single/composite keys, null semantics, named constraints và partial indexes.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html) — atomic conflict handling, DO NOTHING/DO UPDATE và caveats.
- [PostgreSQL — Index Uniqueness Checks](https://www.postgresql.org/docs/current/index-unique-checks.html) — cách unique index phối hợp với MVCC và concurrent transactions.
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html) — transaction boundary mặc định của repository và service orchestration.
- [Spring Data JPA — JpaRepository API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html) — `saveAndFlush`, `flush`.
- [Spring Framework — DataIntegrityViolationException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html) — Spring DAO exception family.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — @Transactional và transaction interceptors.
- [Jakarta Persistence — UniqueConstraint API](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/uniqueconstraint) — khai báo metadata unique constraint trong schema DDL.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html) — validation constraints, không thay thế DB integrity invariants.
