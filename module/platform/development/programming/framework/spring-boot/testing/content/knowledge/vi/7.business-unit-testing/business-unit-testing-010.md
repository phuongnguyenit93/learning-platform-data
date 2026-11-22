# Giới hạn của unit test với transaction, proxy, validation và cấu hình Spring

Unit test nghiệp vụ giúp trả lời câu hỏi **“với các đầu vào và dependency đã được kiểm soát, phương thức này có xử lý đúng quy tắc không?”**. Nó chạy nhanh vì thường gọi trực tiếp đối tượng Java, dùng mock hoặc fake và không khởi tạo `ApplicationContext`. Nhưng một phương thức có `@Transactional`, `@Validated`, `@ConfigurationProperties` hoặc phụ thuộc vào Spring AOP có thể hành xử **khác hẳn khi được gọi qua Spring bean**.

Ví dụ, service thực hiện cập nhật số dư rồi ném `RuntimeException`. Unit test dùng Mockito có thể xác nhận rằng service đã gọi `repository.save(...)` trước khi ném lỗi. Tuy nhiên, chỉ khi gọi service qua Spring transaction proxy và dùng transaction manager với cơ sở dữ liệu thật, mới có thể kiểm tra rằng thay đổi đã **rollback**. Tương tự, việc gắn `@NotBlank` lên tham số chưa bảo đảm lời gọi `new Service(...).method("")` bị từ chối; method validation cần cơ chế Bean Validation được Spring kích hoạt.

Bài học này giúp xác định ranh giới của từng loại test, giải thích điều Spring làm ngoài thân phương thức Java và cung cấp một dự án Java 17+/Spring Boot có thể dùng để kiểm chứng trực tiếp.

## 1. Bằng chứng nào từ unit test là đủ, bằng chứng nào chưa đủ?

| Điều cần bảo vệ | Unit test trực tiếp với Mockito có thể chứng minh | Điều cần thêm để kiểm tra hành vi Spring thực |
| --- | --- | --- |
| Quy tắc tính tiền, ngưỡng, trạng thái hợp lệ | Giá trị trả về, exception nghiệp vụ, lời gọi dependency cho input cụ thể | Integration test nếu kết quả còn phụ thuộc wiring/DB |
| `@Transactional` | Thân phương thức chạy đến lời gọi repository và có thể ném lỗi | Transaction manager, proxy, thao tác ghi thật, commit/rollback quan sát được |
| `@Validated` ở service | Logic validation viết bằng `if` trực tiếp | Bean Validation + Spring method validation interceptor/proxy cho tham số/return value |
| `@Valid` tại HTTP boundary | Logic xử lý DTO đã được tạo hợp lệ | Test Spring MVC xác nhận binding, validation, lỗi 400 và response contract |
| `@ConfigurationProperties` | Service chạy với một đối tượng cấu hình **tự dựng** | Binder đọc property thật, áp dụng conversion, validation, profile/override |
| Constructor injection và bean wiring | Đối tượng tạo bằng `new` khi cung cấp dependency thủ công | Context tạo được bean với qualifier, condition, profile thực tế |
| `@Cacheable`, `@Async`, `@PreAuthorize` (nếu có) | Logic thân phương thức sau khi loại bỏ những interceptor ấy | Test qua Spring-managed bean để quan sát advice tương ứng |

**Phân biệt hai loại đúng:** (1) *đúng theo thuật toán* bên trong service và (2) *đúng theo hợp đồng vận hành* khi Spring tạo bean và thực thi các cơ chế bao quanh service. Một hệ thống đáng tin cần cả hai, ở mức độ phù hợp với rủi ro.

## 2. Vì sao `new Service(...)` không tương đương lấy bean từ Spring?

Một lớp có annotation:

```java
@Service
@Validated
public class WalletService {
    @Transactional
    public int charge(@NotBlank String owner,
                      @Positive int amount,
                      boolean rejectAfterWrite) {
        // xử lý nghiệp vụ
    }
}
```

Là một **định nghĩa có metadata** cho framework. Nếu test gọi:

```java
WalletService service = new WalletService(repository, policy);
service.charge("alice", 150, false);
```

thì đó là lời gọi Java thông thường vào object mà test tự khởi tạo. Spring chưa tạo proxy cho object ấy; interceptor quản lý transaction và method validation sẽ **không tự chạy**. Các annotation không phải câu lệnh được JVM thực thi trong thân method.

Khi Spring khởi tạo bean `WalletService` trong một context đáp ứng đủ dependency và auto-configuration, framework có thể cung cấp một proxy. Lời gọi từ bên ngoài qua proxy mới là nơi các advice như transaction, validation, security, caching thực thi.

```text
Unit test gọi new WalletService(...)
  -> charge(...)  [thân method]
  -> mock repository
  -> không đi qua Spring proxy
  -> không có bảo đảm transaction/validation từ annotation

Integration test gọi @Autowired WalletService
  -> Spring proxy
  -> transaction / method validation advice (theo cấu hình)
  -> charge(...)  [thân method]
  -> repository thật / database
  -> commit hoặc rollback theo transaction rules
```

Sơ đồ giản lược, không cố định thứ tự chính xác của các advisor. Spring AOP có thể sử dụng JDK dynamic proxy nếu bean được truy cập qua interface hoặc class-based proxy tùy cấu hình. Test cần kiểm tra hành vi từ **đường gọi thực tế**, không giả định annotation sẽ có hiệu lực mọi cách gọi.

### Self-invocation là một bẫy phổ biến

Trong proxy mode thông thường, lời gọi `this.charge(...)` **từ một phương thức khác của cùng object** không đi vòng qua proxy, nên có thể bỏ qua advice của `@Transactional` hoặc method validation trên `charge`.

```java
public int runInternalCharge(String owner, int amount) {
    return this.charge(owner, amount, false);
}
```

Đây chỉ là **trích đoạn minh họa** đặt trong service mẫu. Dù client gọi `runInternalCharge` qua bean Spring, lời gọi nội bộ `this.charge` không được proxy chặn như một lời gọi bên ngoài. Không sửa bằng cách chuyển sang gọi method private hoặc final rồi kỳ vọng proxy xử lý; điểm cần giải quyết là **ranh giới gọi qua bean/proxy**. Có thể chuyển phần cần advice sang bean khác, thiết kế lại use case hoặc dùng cơ chế quản lý transaction tường minh khi phù hợp. Không dùng self-injection vòng vo làm lựa chọn mặc định.

## 3. Giới hạn 1 — `@Transactional`: gọi `save` không chứng minh commit hay rollback

`@Transactional` thuộc transaction infrastructure của Spring. Nó không tự chạy khi bạn dựng object bằng `new`. Trong cấu hình proxy thường gặp, advice tạo/tham gia transaction trước lời gọi method và quyết định commit/rollback khi lời gọi kết thúc.

Với cách dùng mặc định, **unchecked exception** (`RuntimeException` và subclass) và `Error` thường kích hoạt rollback; **checked exception** không mặc định kích hoạt rollback trừ khi cấu hình `rollbackFor` hoặc quy tắc transaction khác. Việc một method ném exception không tự chứng minh transaction thật sự tồn tại.

Ví dụ nghiệp vụ:

1. Ví `alice` có 500 đơn vị tiền.
2. Trừ 150, trạng thái dự kiến còn 350.
3. Nếu cổng thanh toán báo từ chối **sau khi đã ghi**, service ném `ChargeRejectedException extends RuntimeException`.
4. Nếu gọi qua transaction proxy, mọi thao tác JDBC tham gia transaction phải được rollback: số dư DB vẫn là 500.
5. Nếu gọi trực tiếp object bên ngoài transaction với kết nối auto-commit, bản ghi 350 có thể vẫn tồn tại sau exception.

**Một mock không thể chứng minh mục 4.** Nó chỉ chứng minh `writeBalance("alice", 350)` đã được gọi. Mockito không có transaction manager, không chạy SQL, không commit/rollback DB.

### Hai điều làm test rollback dễ có kết luận sai

**Thứ nhất: test được gắn `@Transactional`.** Với integration test được Spring Test quản lý transaction, test framework thường tạo transaction cho chính method test rồi rollback khi kết thúc. Kết quả DB “không đổi sau test” có thể do **test transaction**, không chứng minh `@Transactional` trên production service hoạt động. Nếu muốn kiểm chứng transaction boundary của service, tránh gắn `@Transactional` lên method/class test minh họa rollback này; seed data, gọi proxy, rồi đọc DB **sau khi service đã trả về hoặc ném lỗi**.

**Thứ hai: repository hoặc DB bị mock.** `verify(repository).save(...)` chứng minh tương tác; nó không chứng minh dữ liệu cuối cùng, transaction isolation, rollback trên failure, hay trigger SQL đúng. Với logic nhiều truy vấn hoặc ràng buộc DB, cần integration test trên môi trường lưu trữ phù hợp.

## 4. Giới hạn 2 — Spring proxy và advice: annotation không đồng nghĩa hành vi đã được kích hoạt

Không chỉ `@Transactional`, nhiều tính năng Spring phụ thuộc vào interceptor hoặc bean lifecycle:

| Tính năng | Điều xảy ra khi gọi object bằng `new` | Dấu hiệu nên kiểm chứng qua Spring |
| --- | --- | --- |
| `@Transactional` | Annotation không tự mở transaction | Giao dịch tồn tại, commit/rollback thực |
| `@Validated` và constraint ở method | Không tự chặn tham số sai | Method validation báo vi phạm khi gọi qua bean |
| `@Cacheable` | Không tự truy cập Spring Cache | Cache hit/miss và invalidation theo contract |
| `@Async` | Không tự chuyển lời gọi sang executor | Luồng xử lý bất đồng bộ và hoàn tất task |
| `@PreAuthorize` (khi method security bật) | Không tự kiểm tra quyền | Request/method bị từ chối hoặc chấp nhận đúng role |
| `@Value` | Field không tự được inject khi tạo bằng `new` | Property được resolve trên Spring-managed object |
| `@PostConstruct` | Không tự gọi lifecycle callback | Context gọi callback trong vòng đời bean theo cấu hình |

Các cơ chế này không nhất thiết được bật chỉ vì thấy annotation: cần starter, auto-configuration, annotation kích hoạt phù hợp và bean đi qua đường gọi được hỗ trợ.

Với proxy, cần hiểu phạm vi áp dụng: method `private` hoặc `final` không thể được class-based proxy override theo cách thông thường; self-invocation không được proxy intercept. Đừng áp dụng quy tắc “mọi annotated method đều chạy advice” một cách cơ học. Tính năng và proxy mode cụ thể quyết định giới hạn chính xác.

**Unit test vẫn rất có giá trị:** chính vì bỏ tầng hạ tầng này, nó cho feedback nhanh về phép tính và nhánh lỗi. Sai lầm là dùng kết quả unit test để tuyên bố proxy, transaction hay security đã được kiểm thử.

## 5. Giới hạn 3 — `@Valid`, `@Validated` và Bean Validation

Có ba tình huống khác nhau thường bị trộn lẫn.

### 5.1. Ràng buộc viết trực tiếp trong Java

```java
if (amount <= 0) {
    throw new IllegalArgumentException("amount must be positive");
}
```

Đây là logic Java thuần. Unit test gọi `new WalletService(...)` **có thể** kiểm tra nó ngay mà không cần Spring. Nếu test cung cấp lượng tiền âm và assert exception đúng, đó là bằng chứng về guard đã được thực thi.

### 5.2. Method validation tại Spring service

```java
@Service
@Validated
public class WalletService {
    @Transactional
    public int charge(@NotBlank String owner,
                      @Positive int amount,
                      boolean rejectAfterWrite) {
        // ...
    }
}
```

`@NotBlank` và `@Positive` chỉ là constraint metadata. Khi có Bean Validation provider (thường qua `spring-boot-starter-validation`) và Spring method validation được cấu hình, Spring proxy có thể kiểm tra tham số/return value khi lời gọi đi qua bean. Trong cấu hình mặc định của ví dụ, vi phạm constraint tại service dẫn đến `jakarta.validation.ConstraintViolationException`.

Nếu unit test dùng `new WalletService(...)`, `@NotBlank` **không tự chạy**. Muốn test constraint ở cấp Java mà không khởi tạo Spring, có thể tự dựng `Validator` và gọi `validator.validate(...)` cho object hoặc dùng `ExecutableValidator` để kiểm tra method parameters. Nhưng điều đó chỉ kiểm tra **constraint rules**, chưa chứng minh Spring proxy thực sự gọi validator khi endpoint/service được sử dụng.

### 5.3. Validation tại controller / DTO

```java
@PostMapping("/wallets")
public ResponseEntity<Void> create(@Valid @RequestBody CreateWalletRequest body) {
    // ...
}
```

Đây là **trích đoạn API**, không phải phần code runnable ở mục 7. Spring MVC tiếp nhận request, bind JSON sang DTO và kích hoạt validation ở ranh giới web khi cấu hình phù hợp. Dùng `MockMvc` hoặc HTTP integration test để kiểm tra status, body lỗi, field errors và contract của client. Unit test chỉ gọi trực tiếp `create(new CreateWalletRequest(...))` **không tự kích hoạt toàn bộ MVC binding/validation pipeline**.

`@Valid` dùng cho validation/cascade của đối tượng; `@Validated` của Spring còn cho phép chọn validation group và thường được dùng để kích hoạt method-level validation trên service. Đừng coi hai annotation này là những “lệnh kiểm tra ngay lập tức” trong một object do `new` tạo ra.

### Khi nào không nên assert loại exception quá cứng?

Tầng service có thể ném `ConstraintViolationException` theo cấu hình method validation thông thường; nhưng ứng dụng khác có thể dùng `MethodValidationException` hoặc exception đã được chuyển đổi tùy phiên bản/cấu hình. Tầng MVC có thể trả 400 thông qua `MethodArgumentNotValidException` hoặc cơ chế mới của Spring MVC. Chọn assertion theo **hợp đồng và cấu hình đã cố định trong dự án**, không giả định mọi ứng dụng Spring đều có cùng loại exception ở mọi tầng.

## 6. Giới hạn 4 — `@ConfigurationProperties`: object tự dựng chưa chứng minh property đã bind đúng

Spring Boot có thể bind property từ `application.yml`, `application.properties`, environment variables, command-line args và các nguồn cấu hình được khai báo. Test trực tiếp service thường truyền một object như:

```java
WalletService service = new WalletService(
        repository,
        new BillingPolicy(100));
```

Điều này giúp kiểm chứng logic khi mức số dư tối thiểu là 100. Nhưng nó **không kiểm tra** những việc sau:

- Property key thực tế được ghi đúng hay sai, chẳng hạn `billing.minimum-balance`.
- Context thực sự có scan/đăng ký class `@ConfigurationProperties` hay không.
- Giá trị có được conversion/binding đúng kiểu, đúng profile/override hay không.
- Constraint `@NotNull`, `@Min` trên configuration record có được validate khi Spring khởi tạo context hay không.
- Nếu property thiếu hoặc âm, quá trình khởi động có thất bại như mong muốn không.
- Có nhiều bean cùng type, qualifier hoặc conditional configuration xung đột hay không.

`@ConfigurationProperties` không làm constructor Java trở thành validator. `new BillingPolicy(-10)` vẫn tạo record chứa -10; chỉ khi qua cơ chế Bean Validation (hoặc code kiểm tra riêng) thì constraint mới được thực thi.

**Phân biệt ba cấp test về cấu hình:**

1. Unit test: truyền object `BillingPolicy(100)`; kiểm tra thuật toán với một giá trị chính xác.
2. Context test: nạp `@ConfigurationProperties` thật, assert property đã bind, type conversion và constraint.
3. Integration test theo profile/môi trường: kiểm tra hiệu lực cấu hình trong service, transaction và dependency thực tế. Test profile không tự chứng minh cấu hình production giống hệt.

Spring Boot có thể hỗ trợ `@SpringBootTest(properties = "...")`, `@ActiveProfiles("test")`, `@TestPropertySource` hoặc `ApplicationContextRunner` tùy mục tiêu. Phải xác định property source nào đang thắng trong thứ tự ưu tiên cấu hình; “test xanh với default object” không phát hiện typo trong YAML.

## 7. Ví dụ chạy được: một nghiệp vụ, hai mức bằng chứng

Dự án mẫu độc lập dùng **Java 17+, Spring Boot 3.3.5, Gradle Groovy DSL, JUnit Jupiter, Mockito, Spring JDBC, Bean Validation và H2**. Nó cố ý nhỏ để ranh giới giữa Java thuần và Spring proxy quan sát được qua database.

**Hợp đồng nghiệp vụ của ví:**

- Ví `alice` ban đầu có số dư 500.
- `charge(owner, amount, rejectAfterWrite)` trừ `amount` khỏi số dư; nếu số dư sau trừ nhỏ hơn ngưỡng cấu hình `billing.minimum-balance`, ném `IllegalArgumentException` **trước khi ghi**.
- `owner` phải không rỗng/khoảng trắng (`@NotBlank`); `amount` phải lớn hơn 0 (`@Positive`) khi gọi qua Spring-managed proxy với method validation đang bật.
- Nếu `rejectAfterWrite=true`, service ném `ChargeRejectedException` **sau khi cập nhật repository**. Với transaction hoạt động đúng, thay đổi phải rollback.
- Ngưỡng cấu hình thật trong `application.yml` là 100. Cấu hình thiếu `minimum-balance` hoặc giá trị âm phải bị bean validation từ chối khi context bind property.

Hợp đồng của ví dụ dùng số nguyên đơn vị tiền để minh họa. Hệ thống tài chính thực thường cần lưu bằng kiểu tiền tệ/đơn vị được định nghĩa rõ, kiểm tra concurrency và transaction isolation; không suy ra một demo H2 đã xử lý đủ các điều kiện đó.

### 7.1. Cấu trúc tệp

```text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/resources/schema.sql
src/main/java/com/example/testboundary/BoundaryApplication.java
src/main/java/com/example/testboundary/BillingPolicy.java
src/main/java/com/example/testboundary/WalletRepository.java
src/main/java/com/example/testboundary/ChargeRejectedException.java
src/main/java/com/example/testboundary/WalletService.java
src/test/java/com/example/testboundary/WalletServiceUnitTest.java
src/test/java/com/example/testboundary/WalletServiceIntegrationTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-test-boundary'
```

**`build.gradle`**

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate` và transaction infrastructure cần thiết; H2 là database trong bộ nhớ dùng ở runtime/test của ví dụ. `spring-boot-starter-validation` đem Bean Validation provider vào classpath. `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test và Mockito. Không cần web server vì ví dụ tập trung service/DB.

**`src/main/resources/application.yml`**

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:walletdemo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always

billing:
  minimum-balance: 100
```

H2 dùng schema `wallets`. Cấu hình này là **ví dụ đào tạo** dùng DB trong bộ nhớ; không áp dụng nguyên trạng cho production.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE wallets (
    owner VARCHAR(100) PRIMARY KEY,
    balance INTEGER NOT NULL
);
```

`spring.sql.init.mode=always` yêu cầu khởi tạo schema bằng script khi datasource được dựng; khi context của test được cache, schema thường được tạo ở lần dựng context, **không phải trước mỗi test method**. Vì vậy mỗi test integration ở dưới tự seed dữ liệu bằng `@BeforeEach`.

### 7.2. Spring Boot application và configuration binding

**`src/main/java/com/example/testboundary/BoundaryApplication.java`**

```java
package com.example.testboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

**`src/main/java/com/example/testboundary/BillingPolicy.java`**

```java
package com.example.testboundary;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "billing")
@Validated
public record BillingPolicy(
        @NotNull @Min(0) Integer minimumBalance) {
}
```

Spring Boot có thể bind record này bằng constructor duy nhất. `@ConfigurationPropertiesScan` đăng ký record config; `@Validated` cùng constraint yêu cầu giá trị có mặt và không âm khi **binder/validator của context** chạy. Java vẫn cho phép `new BillingPolicy(-10)`; annotation không tự chặn constructor được gọi thủ công.

### 7.3. Repository JDBC và service có các annotation Spring

**`src/main/java/com/example/testboundary/WalletRepository.java`**

```java
package com.example.testboundary;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class WalletRepository {
    private final JdbcTemplate jdbc;

    public WalletRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int findBalance(String owner) {
        return jdbc.queryForObject(
                "SELECT balance FROM wallets WHERE owner = ?",
                Integer.class, owner);
    }

    public void writeBalance(String owner, int balance) {
        int updated = jdbc.update(
                "UPDATE wallets SET balance = ? WHERE owner = ?",
                balance, owner);
        if (updated != 1) {
            throw new IllegalArgumentException("unknown wallet");
        }
    }
}
```

Với một record `wallets` đã được seed, `findBalance` trả về số dư của owner. Nếu owner không có dòng nào, Spring JDBC phát lỗi truy vấn; trường hợp đó nằm ngoài các tình huống hợp lệ của demo.

**`src/main/java/com/example/testboundary/ChargeRejectedException.java`**

```java
package com.example.testboundary;

public class ChargeRejectedException extends RuntimeException {
    public ChargeRejectedException(String message) {
        super(message);
    }
}
```

**`src/main/java/com/example/testboundary/WalletService.java`**

```java
package com.example.testboundary;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class WalletService {
    private final WalletRepository repository;
    private final BillingPolicy policy;

    public WalletService(WalletRepository repository, BillingPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional
    public int charge(@NotBlank String owner,
                      @Positive int amount,
                      boolean rejectAfterWrite) {
        int before = repository.findBalance(owner);
        int after = before - amount;

        if (after < policy.minimumBalance()) {
            throw new IllegalArgumentException(
                    "balance below configured minimum");
        }

        repository.writeBalance(owner, after);

        if (rejectAfterWrite) {
            throw new ChargeRejectedException("payment rejected");
        }

        return after;
    }
}
```

**Giải thích ba tầng trong một method:**

- Phép trừ và so ngưỡng là **logic Java**: unit test trực tiếp vẫn chạy.
- `@Transactional` cần **transaction advice** và transaction manager khi gọi qua Spring proxy; nó không nằm trong thân method.
- `@NotBlank` và `@Positive` cần **method validation** khi gọi qua Spring proxy; chúng không tự chạy khi object được `new`.
- `BillingPolicy` từ constructor có thể là object do unit test tự tạo hoặc object Spring bind; service không thể tự biết nguồn gốc nếu chỉ nhìn vào giá trị field.

Nguy cơ khác ở ứng dụng thật là **lost update** khi nhiều request cùng đọc rồi ghi số dư. Demo không bổ sung lock/optimistic version/atomic SQL update; các test dưới đây **không chứng minh an toàn đồng thời**.

### 7.4. Unit test dùng Mockito: chứng minh quy tắc, không chứng minh transaction

**`src/test/java/com/example/testboundary/WalletServiceUnitTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class WalletServiceUnitTest {
    @Mock
    private WalletRepository repository;

    private WalletService service;

    @BeforeEach
    void setUp() {
        service = new WalletService(repository, new BillingPolicy(100));
    }

    @Test
    void computesBalanceAndWritesExpectedValue() {
        when(repository.findBalance("alice")).thenReturn(500);

        assertEquals(350, service.charge("alice", 150, false));
        verify(repository).writeBalance("alice", 350);
    }

    @Test
    void throwsAfterWriteButCannotProveRollback() {
        when(repository.findBalance("alice")).thenReturn(500);

        ChargeRejectedException exception = assertThrowsExactly(
                ChargeRejectedException.class,
                () -> service.charge("alice", 150, true));

        assertEquals("payment rejected", exception.getMessage());
        verify(repository).writeBalance("alice", 350);
    }

    @Test
    void directInvocationDoesNotApplyMethodValidation() {
        when(repository.findBalance("")).thenReturn(500);

        assertEquals(450, service.charge("", 50, false));
        verify(repository).writeBalance("", 450);
    }

    @Test
    void preventsBalanceBelowConfiguredMinimum() {
        when(repository.findBalance("alice")).thenReturn(500);

        IllegalArgumentException exception = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.charge("alice", 450, false));

        assertEquals("balance below configured minimum",
                exception.getMessage());
    }
}
```

Test đầu chứng minh `350` là kết quả đúng với dependency mock và `BillingPolicy(100)`. Test thứ hai chứng minh method **gọi write trước khi ném runtime exception**; nó không thể xác nhận rollback, vì `WalletRepository` là mock và không có database.

Test `directInvocationDoesNotApplyMethodValidation` là **phản chứng có chủ đích**: `owner=""` vi phạm `@NotBlank` nhưng lời gọi vẫn đến mock repository và trả 450, bởi object `WalletService` được tạo trực tiếp. Test này giúp hiểu giới hạn của annotation; trong hệ thống thật, bạn có thể bổ sung guard trong domain code hoặc kiểm tra validation tại boundary cần bảo vệ.

Test cuối bảo vệ quy tắc ngưỡng trong **thân Java**. Việc tất cả unit test xanh vẫn chưa xác nhận property key đúng hoặc transaction proxy hoạt động.

### 7.5. Integration test: kiểm tra DB rollback, proxy validation và binding

**`src/test/java/com/example/testboundary/WalletServiceIntegrationTest.java`**

```java
package com.example.testboundary;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;

@SpringBootTest
class WalletServiceIntegrationTest {
    @Autowired
    private WalletService service;

    @Autowired
    private WalletRepository repository;

    @Autowired
    private BillingPolicy policy;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void seedWallet() {
        jdbc.update("DELETE FROM wallets");
        jdbc.update(
                "INSERT INTO wallets(owner, balance) VALUES (?, ?)",
                "alice", 500);
    }

    private int balance() {
        return repository.findBalance("alice");
    }

    @Test
    void springBindsApplicationProperties() {
        assertEquals(100, policy.minimumBalance());
    }

    @Test
    void successfulChargePersistsItsChange() {
        assertEquals(350, service.charge("alice", 150, false));
        assertEquals(350, balance());
    }

    @Test
    void runtimeExceptionRollsBackDatabaseWrite() {
        assertThrowsExactly(ChargeRejectedException.class,
                () -> service.charge("alice", 150, true));

        assertEquals(500, balance());
    }

    @Test
    void proxiedMethodValidationRejectsBlankOwner() {
        assertThrows(ConstraintViolationException.class,
                () -> service.charge("", 50, false));

        assertEquals(500, balance());
    }

    @Test
    void configuredMinimumIsAppliedByService() {
        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.charge("alice", 450, false));

        assertEquals(500, balance());
    }

    @Test
    void directlyConstructedServiceDoesNotOpenTransaction() {
        WalletService direct = new WalletService(repository, policy);

        assertThrowsExactly(ChargeRejectedException.class,
                () -> direct.charge("alice", 150, true));

        assertEquals(350, balance());
    }
}
```

**Đọc các assertion theo mức bằng chứng:**

- `springBindsApplicationProperties` xác nhận ứng dụng thực sự có `BillingPolicy` chứa 100 từ context; unit test `new BillingPolicy(100)` không làm được điều đó.
- `successfulChargePersistsItsChange` gọi Spring-managed bean, sau đó đọc DB thật để xác nhận write đã commit.
- `runtimeExceptionRollsBackDatabaseWrite` dùng unchecked exception sau khi viết và đọc DB **sau khi service đã ném lỗi**, mong đợi giá trị vẫn là 500. Đây là bằng chứng thực tế về rollback của service trong cấu hình test.
- `proxiedMethodValidationRejectsBlankOwner` xác nhận validation advice đang hiệu lực; vì `owner=""` không tồn tại trong DB, nếu validation không chạy, lời gọi có thể thất bại vì truy vấn DB. Kiểm tra **loại exception** là `ConstraintViolationException` giúp phân biệt hai cơ chế.
- `configuredMinimumIsAppliedByService` xác nhận bean nhận ngưỡng và service dùng đúng ngưỡng 100.
- `directlyConstructedServiceDoesNotOpenTransaction` là **phản chứng được cố ý giữ trong demo**: dù repository và config là bean thật, bản thân `WalletService` do `new` tạo nên không đi qua transaction proxy. Với H2/JDBC auto-commit của cấu hình này, write 350 đã tồn tại khi exception xảy ra. Tình huống đó **không được coi là hành vi đúng để triển khai**; nó minh họa vì sao không dùng gọi trực tiếp để đánh giá transaction.

Lớp integration test cố ý **không** gắn `@Transactional`, tránh transaction do framework tạo quanh từng method test làm che mất cơ chế commit/rollback của production service. `@BeforeEach` reset bảng về một bản ghi; bài học giả định test tuần tự. Nếu chạy song song trên cùng DB, dùng database/schema/test data riêng hoặc cơ chế isolation, vì hai test có thể xóa dữ liệu của nhau.

### 7.6. Chạy ví dụ

Tạo/đặt Gradle Wrapper tương thích với Spring Boot 3.3.x trong thư mục dự án. Trên Linux/macOS:

```bash
./gradlew test
./gradlew test --tests com.example.testboundary.WalletServiceUnitTest
./gradlew test --tests com.example.testboundary.WalletServiceIntegrationTest
```

Trên Windows dùng `gradlew.bat` với các tham số tương ứng.

Với code và môi trường tương ứng, **kỳ vọng** unit và integration tests PASS. Đây là kết quả dự đoán từ logic ví dụ, không phải stdout của một lần build đã được quan sát. Các assert xác nhận những trạng thái cụ thể: 350 sau charge thành công; 500 sau rollback; `ConstraintViolationException` khi owner rỗng qua proxy; 350 trong phản chứng direct `new`.

Để thử thay đổi có chủ đích:

1. Bỏ `@Transactional` trên `WalletService.charge`. Unit tests vẫn có thể xanh, nhưng test `runtimeExceptionRollsBackDatabaseWrite` sẽ FAIL vì DB giữ 350.
2. Bỏ `@Validated` trên service (và không bật method validation theo cơ chế khác). Unit tests không khác; integration test `proxiedMethodValidationRejectsBlankOwner` không còn nhận đúng `ConstraintViolationException`.
3. Đổi `billing.minimum-balance: 100` thành `150`. Unit test vẫn dùng object 100 nên không phản ánh thay đổi YAML; integration test kiểm tra binding 100 và test ngưỡng có thể báo đỏ.
4. Đổi `billing.minimum-balance` thành giá trị âm. Context được cấu hình validate `BillingPolicy` nên phải thất bại khi khởi động nếu Bean Validation được kích hoạt đúng.
5. Bỏ `@ConfigurationPropertiesScan`. Spring không còn tự đăng ký `BillingPolicy` theo đường scan đang dùng; integration context sẽ không dựng được `WalletService` vì thiếu dependency.

Sau thử nghiệm, khôi phục code và cấu hình gốc. Đừng suy ra một test luôn fail theo cùng exception text: wrapper startup exception và mô tả chi tiết khác nhau theo Boot/Bean Validation phiên bản, nhưng failure phase là bằng chứng chính.

## 8. Những phép kiểm bổ sung khi rủi ro cao

Ví dụ trên đã minh họa bốn ranh giới cơ bản. Trong hệ thống thật cần mở rộng theo loại rủi ro.

### 8.1. Transaction propagation, rollback rule và checked exception

`@Transactional` mặc định có `propagation=REQUIRED`: method tham gia transaction đang có hoặc tạo transaction mới khi chưa có. `REQUIRES_NEW`, nested transaction hoặc nhiều transaction manager có semantics khác. Một test đơn giản chỉ dùng một service call không chứng minh propagation đúng qua nhiều service, transaction manager đã chọn đúng datasource hoặc rollback rule cho checked exception.

Ví dụ **trích đoạn cấu hình rollback**, không phải method nằm trong dự án ở phần 7:

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void importFile() throws java.io.IOException {
    // Ghi dữ liệu rồi có thể phát IOException.
}
```

Unit test thuần Java có thể thấy `IOException`, nhưng chỉ integration test có transaction thực mới xác nhận dữ liệu được rollback theo `rollbackFor`. Tương tự, một test có `@Transactional` bao toàn bộ method có thể làm méo điều kiện so với luồng HTTP thật, nơi request chạy trên thread/transaction khác.

### 8.2. Validation: đúng chỗ, đúng lớp, đúng loại lỗi

Với validation, ưu tiên kiểm thử đúng tầng:

- Domain rule trong Java: unit test.
- Bean Validation constraint trên DTO: test `Validator` (nếu chỉ quan tâm constraint) và test Spring MVC nếu cần xác nhận binding/HTTP status.
- Method parameter/return value constraint ở service: gọi bean qua Spring context, có `@Validated`/method validation infrastructure phù hợp.
- Configuration properties: kiểm tra context binding và validation startup, đặc biệt property bắt buộc, conversion và giá trị không hợp lệ.

Đừng yêu cầu mọi tầng dùng chung một exception class. DTO nhận JSON sai có thể bị chặn bởi MVC trước khi service được gọi; service validation có thể ném `ConstraintViolationException`; quy tắc domain có thể ném `IllegalArgumentException`. Đúng hay sai phụ thuộc **hợp đồng của tầng đang test**.

### 8.3. Configuration: profile, condition và giá trị override

`@SpringBootTest` có thể nạp `application.yml` của test/project, nhưng không tự chứng minh mọi profile production tương tự. Với config quan trọng, hãy kiểm tra:

- Bean `@ConfigurationProperties` có được đăng ký và bind đúng key.
- Giá trị bắt buộc thiếu hoặc sai kiểu có chặn startup.
- `@ConditionalOnProperty`, `@Profile` hoặc bean override có chọn đúng implementation.
- Mức ưu tiên của property source khi test thêm `@SpringBootTest(properties=...)`, environment variables hoặc `@ActiveProfiles`.
- Kết quả config thực tế có ảnh hưởng đúng đến logic và dependency được chọn.

Đối với thư viện auto-configuration, `ApplicationContextRunner` cho phép dựng context hẹp với các bộ property khác nhau và assert có/không có bean hoặc startup failure. Đối với nghiệp vụ tích hợp nhiều dependency, `@SpringBootTest` phù hợp hơn khi muốn xác nhận wiring của ứng dụng. **Không cần thay mọi unit test bằng `@SpringBootTest`** chỉ vì có một số annotation.

### 8.4. Database giả lập không bảo đảm tương đương production

H2 thuận tiện kiểm chứng transaction/rollback cơ bản, nhưng không thể tự chứng minh mọi behavior của PostgreSQL, MySQL, Oracle… như isolation, locking, SQL dialect, trigger, constraint, timezone hay transaction behavior đặc biệt. Khi các chi tiết đó là rủi ro nghiệp vụ, nên có integration test trên DB engine thật, ví dụ qua Testcontainers, với schema/migration và cấu hình gần production.

Một test xanh trên H2 cho biết **trong H2 và cấu hình đã thử**, rollback/commit mong đợi xảy ra. Không nâng kết luận lên toàn bộ hệ thống dữ liệu mà không có bằng chứng bổ sung.

## 9. Dấu hiệu nhận biết một unit test đang tuyên bố quá mức

| Tuyên bố | Vì sao chưa đủ | Cần thêm |
| --- | --- | --- |
| “`verify(save)` xanh, transaction rollback đúng” | Mock không giữ transaction/DB state | Integration test kiểm tra DB sau exception |
| “Service có `@Transactional`, nên gọi `new` vẫn transactional” | Annotation không tự tạo advice | Lấy bean Spring và gọi qua proxy |
| “`@NotBlank` khiến input rỗng luôn bị chặn” | Constraint metadata cần validation infrastructure | Method validation test hoặc explicit guard |
| “`@Valid` trên DTO đã được test bằng gọi controller Java trực tiếp” | Bỏ qua MVC binding/validation pipeline | MockMvc hoặc HTTP test kiểm tra 400/body |
| “`new BillingPolicy(100)` chứng minh YAML đúng” | Object đã được tạo thủ công | Nạp context và kiểm tra binding/constraints |
| “`@SpringBootTest` xanh tức mọi nghiệp vụ đúng” | Context loading không tự assert mọi nhánh | Unit tests và integration tests có expected behavior |
| “Test có `@Transactional` rồi DB sạch, service rollback tốt” | Rollback có thể đến từ **transaction của test** | Test service boundary không có test-managed transaction |
| “Unit test mock dependency nên `@Cacheable` hoặc `@Async` đã được kiểm” | Proxy advice không chạy trên object do `new` | Test qua managed bean với điều kiện hạ tầng đúng |
| “H2 transaction xanh nghĩa là concurrency production an toàn” | Isolation và DB engine khác có thể đổi kết quả | Test engine thật, locking/versioning, kịch bản đồng thời |

Một số lỗi có thể đồng thời xuất hiện: unit test dùng chính object `new`, mock repository và cấp object config bằng tay. Đó là **môi trường cố ý tinh giản**; bài test chỉ nên khẳng định logic đúng trong môi trường ấy.

## 10. Chiến lược kiểm thử theo ranh giới trách nhiệm

Hãy tổ chức bằng chứng sao cho mỗi tầng trả lời một câu hỏi cụ thể:

1. **Unit test cho quy tắc nghiệp vụ**: với input hợp lệ/không hợp lệ, kiểm tra kết quả, exception, ranh giới, và các lời gọi dependency có ý nghĩa. Dùng Mockito khi cần cô lập; không dựng context chỉ để tính một phép toán.
2. **Context/wiring test**: khi cần biết Spring dựng được bean, property binding, profile/qualifier/condition và proxy infrastructure đã xuất hiện. Một context test có thể bắt lỗi startup nhưng không tự chứng minh behavior.
3. **Integration test ở service boundary**: dùng repository và DB thực, gọi bean Spring qua proxy, kiểm tra state sau success/failure. Đặc biệt cần cho transaction/rollback, method validation và cấu hình tác động lên nghiệp vụ.
4. **Web/API test**: khi client cần đúng status, response schema, security/validation filter và cách exception được chuyển thành HTTP. Gọi controller bằng `new` chưa kiểm thử pipeline ấy.
5. **Test với hạ tầng gần production**: khi kết luận phụ thuộc database engine, cache, message broker, concurrency hoặc feature flag. Cân bằng chi phí thực thi với rủi ro của chức năng.

Một bộ test phù hợp không nhất thiết có nhiều `@SpringBootTest`; điều quan trọng là **mỗi cơ chế ngoài thân Java được kiểm chứng ở đúng tầng**. Việc viết unit test nhanh song song với ít integration tests có mục tiêu thường dễ bảo trì và cho tín hiệu rõ hơn việc dùng một loại test cho mọi vấn đề.

## 11. Bài tập phản chứng và checklist review

**Tình huống A.** Test tạo `new WalletService(mockRepo, new BillingPolicy(100))`, gọi `charge("alice",150,true)` và xác nhận `ChargeRejectedException`. Đã chứng minh DB rollback chưa? **Chưa**. Chỉ chứng minh method ném lỗi theo nhánh Java sau khi tương tác mock. Cần đọc DB sau lời gọi qua Spring transaction proxy.

**Tình huống B.** `@Transactional` được đặt trên một method nhưng một method khác trong cùng object gọi `this.method()`. Có chắc advice kích hoạt không? **Không** trong proxy mode thông thường: self-invocation bỏ qua proxy. Cần thiết kế lại ranh giới lời gọi hoặc dùng cơ chế khác được kiểm chứng.

**Tình huống C.** `@NotBlank` có trên tham số; unit test gọi `new WalletService(...).charge("",50,false)` vẫn chạy. Annotation sai cú pháp? **Không nhất thiết**; Bean Validation constraint chưa được Spring interceptor áp dụng cho object tự tạo. Test qua Spring-managed bean và xác minh method validation được cấu hình.

**Tình huống D.** Một test dùng `@Transactional` trên chính test method, gọi service không gắn `@Transactional`, rồi thấy dữ liệu DB biến mất sau test. Có chứng minh service rollback không? **Không**. Transaction của test có thể làm điều đó. Hãy kiểm tra transaction boundary thật của service, không bị test transaction bao quanh.

**Tình huống E.** Unit test truyền `new BillingPolicy(100)`; trong YAML key bị gõ nhầm thành `billing.minimum-balnce`. Unit test có bắt được lỗi? **Không**. Context binding test hoặc validation `@NotNull` tại khởi tạo context sẽ giúp phát hiện.

**Tình huống F.** H2 integration test thành công, nhưng production dùng DB khác và xảy ra lost update dưới tải đồng thời. Kết quả có mâu thuẫn không? **Không**. Test H2 tuần tự chưa bảo vệ semantics isolation và concurrency của DB thật.

### Checklist trước khi chốt QA cho một test suite Spring Boot

- Những assertion nghiệp vụ quan trọng đã có unit test độc lập và giá trị kỳ vọng từ yêu cầu chưa?
- Có test nào đang gọi `new Service` rồi tuyên bố `@Transactional`, `@Validated` hay `@Async` đã được kiểm chứng?
- Có self-invocation, method final/private hoặc proxy mode nào làm advice không được chặn như kỳ vọng?
- Rollback test có gọi Spring-managed bean, dùng thao tác DB thật và kiểm tra state sau exception **mà không bị test transaction che lấp**?
- Validation test có phân biệt guard viết trong Java, constraint ở service và validation tại MVC boundary?
- `@ConfigurationProperties` đã được binder đọc đúng key, validate giá trị và áp dụng đúng profile chưa?
- Context test chỉ tuyên bố startup/wiring, hay đã có assertion behavior riêng để kết luận nghiệp vụ?
- Khi DB/caching/concurrency là rủi ro, test environment có đủ gần production và ghi rõ giới hạn không?
- Các test có chạy độc lập, không phụ thuộc thứ tự và không làm rò dữ liệu qua singleton/DB giữa các trường hợp?

**Kết luận:** Unit test rất mạnh để kiểm tra **logic nghiệp vụ trong thân Java**. Nhưng `@Transactional`, Spring AOP proxy, Bean Validation và property binding là những hành vi do **runtime Spring** tổ chức. Muốn xác nhận chúng, hãy gọi bean trong context phù hợp, quan sát exception/response và thay đổi dữ liệu thật, rồi giới hạn kết luận đúng theo môi trường đã được thử.
