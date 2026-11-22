# Phân biệt lỗi tải context với lỗi assertion hoặc lỗi nghiệp vụ trong Spring TestContext

## 1. Vấn đề cần giải quyết

Trong một dự án Spring Boot, Maven/JUnit đều có thể báo `BUILD FAILURE`, nhưng nguyên nhân và hướng sửa rất khác nhau:

1. **Lỗi tải Spring context**: Spring chưa tạo được `ApplicationContext` hoặc chưa chuẩn bị được test instance; phương thức `@Test` có thể **chưa chạy**.
2. **Lỗi assertion**: phép kiểm trong test chạy rồi và kết quả thực tế không khớp điều được kỳ vọng; điển hình là `AssertionFailedError` từ JUnit hoặc `AssertionError` từ AssertJ/MockMvc.
3. **Lỗi nghiệp vụ / exception khi chạy mã ứng dụng**: code của service, controller hoặc repository ném exception trong quá trình thực hiện test. Đây có thể là **hành vi đúng** nếu exception được mong đợi và kiểm bằng `assertThrows`; hoặc là **lỗi thực sự** nếu không mong đợi.

Một dòng `Tests run: 3, Failures: 1, Errors: 1` chỉ là tín hiệu ban đầu. **`Failures`/`Errors` của test runner không phải phân loại nguồn gốc tuyệt đối**: một bug nghiệp vụ có thể bộc lộ bằng assertion fail; một exception nghiệp vụ được ném trong `@PostConstruct` có thể khiến context fail; và một lỗi setup trong `@BeforeEach` không nhất thiết là lỗi tải Spring context.

Bài học tập trung vào cách xác định **thời điểm thất bại**, **exception gốc** và **hợp đồng cần được kiểm**. Ví dụ dùng Java 17+, Spring Boot 3.5.16, JUnit Jupiter, Mockito và Spring TestContext. Các thao tác áp dụng được cả với `@SpringBootTest` và các slice tests như `@WebMvcTest`/`@DataJpaTest`, sau khi chọn đúng ranh giới kiểm thử.

## 2. Bản đồ vòng đời của một bài test Spring

Một bài `@SpringBootTest` với JUnit Jupiter thường đi qua các bước sau (thứ tự cụ thể có thể phụ thuộc extensions/listeners và cấu hình):

```text
Maven Surefire / Gradle Test / IDE
          |
          v
Khám phá lớp test và test methods
          |
          v
JUnit Jupiter + SpringExtension
          |
          v
Spring TestContext chuẩn bị test instance
          |
          +-- Tìm cấu hình (@SpringBootTest, @ContextConfiguration)
          |   Chọn profile, property sources, context customizers
          |
          +-- Tải / lấy từ cache ApplicationContext
          |   Bean definitions, auto-configuration, bean creation,
          |   dependency injection, @PostConstruct, DB/Broker setup...
          |
          +-- Inject @Autowired / @MockitoBean vào test
          |
          v
@BeforeEach và các callbacks trước method
          |
          v
@Test: gọi service / controller / repository
          |
          +-- Không có exception -> chạy assertion
          +-- Exception được assertThrows chấp nhận -> test có thể PASS
          +-- Exception bất ngờ -> test ERROR/FAIL tùy runner
          +-- Assertion không đúng -> AssertionFailedError / AssertionError
          |
          v
@AfterEach và các callbacks sau method
          |
          v
Kết quả test và báo cáo Surefire/JUnit
```

**Phân loại theo pha, không chỉ theo tên exception:**
- Khi `ApplicationContext` không tải được, lỗi thường xuất hiện ở `SpringExtension`/`TestContextManager.prepareTestInstance`, trước khi cơ thể method test thực thi.
- Khi `@BeforeEach` ném `NullPointerException`, context có thể đã tải xong. Đây là lỗi *setup test*, không tự động là context-load failure.
- Khi `@Test` ném `IllegalArgumentException` từ service, đó là lỗi/behavior lúc thực thi nghiệp vụ.
- Khi `assertEquals` nhận giá trị khác mong đợi, đó là thất bại của assertion. Nguyên nhân sâu có thể là bug nghiệp vụ, dữ liệu fixture sai, timezone hoặc expected value sai.
- Khi `@AfterEach` hoặc cleanup fail, bản thân assertion có thể đã PASS nhưng toàn test vẫn bị báo lỗi.

## 3. Bảng nhận diện nhanh

| Dấu hiệu trong log | Giai đoạn khả dĩ | Câu hỏi chẩn đoán |
| --- | --- | --- |
| `Failed to load ApplicationContext` | Load Spring context / chuẩn bị test instance | Context cấu hình thế nào? `Caused by` thấp nhất có ý nghĩa là gì? |
| `Error creating bean with name '...'` | Bean initialization trong context | Bean nào thiếu dependency/config hoặc thất bại ở factory method? |
| `UnsatisfiedDependencyException` / `NoSuchBeanDefinitionException` | Context hoặc lazy lookup | Bean bị thiếu do component scan, profile, test slice, qualifier hay mock? |
| `Failed to bind properties` / `BindException` | Config binding của Spring Boot | Key/type/property source/profiles đã đúng chưa? |
| `ApplicationContext failure threshold ... exceeded` | Lần tải context tiếp theo bị bỏ qua | Lần **đầu tiên** cùng context cache key đã fail vì lý do gì? |
| `org.opentest4j.AssertionFailedError` | Assertion của JUnit Jupiter | Expected/actual nào lệch? Test gọi code tới đâu? |
| `java.lang.AssertionError` từ AssertJ/MockMvc | Assertion / response expectation | Có sai dữ liệu, status, thứ tự list, comparator hay JSON path? |
| `IllegalArgumentException`, custom `BusinessException` từ service | Thực thi logic nghiệp vụ | Exception là contract hay bất ngờ? `assertThrows` đúng class/message chưa? |
| `HttpClientErrorException`/timeout/`DataAccessException` trong `@Test` | Adapter/hạ tầng trong lúc test chạy | Có gọi môi trường thật, sai dữ liệu, service chưa sẵn sàng? |
| `Exception in @BeforeEach` | Setup trước method, sau hoặc cùng lúc lifecycle callback | Setup tự tạo đối tượng sai hay context injection lỗi? |
| `expected: <201> but was: <401>` | Assertion HTTP; nguyên nhân có thể filter/security | Request đến app chưa? Status 401 có do security chain không? |

Không chẩn đoán chỉ từ hậu tố `Exception`. Ví dụ `IllegalStateException` có thể là Spring báo không tải được context, cũng có thể là service cố ý ném khi đơn hàng đã đóng. **Đọc stack trace và điểm phát sinh**.

## 4. Lỗi tải context: cơ chế và dấu hiệu

### 4.1. Bản chất

Spring TestContext cố tạo `ApplicationContext` (hoặc lấy context phù hợp từ cache). Với `@SpringBootTest`, Spring Boot dùng `SpringApplication` để tải cấu hình ứng dụng. Những lỗi khi tìm configuration, dựng bean graph, bind properties, khởi động embedded infrastructure hoặc gọi bean lifecycle hook có thể làm quá trình này thất bại.

Ví dụ chuỗi lỗi điển hình:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext
  ...
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
  Error creating bean with name 'checkoutService'
  ...
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
  No qualifying bean of type '...ShippingGateway' available
```

Đây là **trích mô phỏng cấu trúc log**, không phải stdout cố định của ví dụ. `Failed to load ApplicationContext` là triệu chứng phía ngoài; thiếu bean `ShippingGateway` là nguyên nhân sâu đáng xử lý.

### 4.2. Các nguyên nhân phổ biến

- Thiếu dependency: controller/service/repository không có bean vì sai `@Component`/`@Service`/`@Repository`, package scan hoặc `@Import`.
- Profile không trùng: bean chỉ tồn tại dưới `@Profile("prod")` nhưng test chạy `@ActiveProfiles("test")`.
- Phạm vi slice: `@WebMvcTest` cố ý không load toàn bộ service/repository; controller có constructor dependency không được mock/import sẽ fail ngay lúc tạo bean.
- Config sai kiểu: `@ConfigurationProperties` binding/validation fail, placeholder `@Value("\${...}")` không resolve, URL/port/timeout sai.
- Dependency ngoài chưa sẵn sàng: database, broker, vault, config server, Testcontainers/Docker, credential hoặc DNS.
- JPA: mapping lỗi, Hibernate không tạo EntityManagerFactory, migration Flyway/Liquibase lỗi, DataSource thiếu driver.
- Bean lifecycle: `@PostConstruct` hoặc `@Bean` factory method tự ném exception.
- Nhiều bean cùng kiểu nhưng không `@Primary`/`@Qualifier` rõ, dẫn tới `NoUniqueBeanDefinitionException`.
- Vòng phụ thuộc/constructor cycle hoặc một context configuration bị import trùng/mâu thuẫn.

**Sửa lỗi bắt đầu từ root cause cụ thể, không bằng cách thêm `@SpringBootTest`, tắt security hoặc mock hàng loạt mọi bean một cách ngẫu nhiên.** Mỗi biện pháp thay đổi phạm vi test và điều có thể kết luận.

### 4.3. Spring TestContext context cache

Spring tái sử dụng context thành công có cùng cấu hình. Cache key xét nhiều yếu tố, gồm classes/locations, initializers, active profiles, test property sources, context customizers (bean overrides như `@MockitoBean`), context loader và parent context.

Từ Spring Framework **6.1**, chính sách **context failure threshold** mặc định là **1**. Nếu cùng cache key đã thất bại khi load, lần thử tiếp trong cùng test process có thể bị dừng ngay:

```text
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for [...]
```

**Đó là lỗi theo sau, không phải gốc ban đầu.** Hãy tìm dòng context failure đầu tiên trong cùng lần chạy và `Caused by` của nó. Chạy một lớp test đơn lẻ trong một JVM mới có thể hiện lại nguyên nhân ban đầu vì static cache không đi xuyên process. Có thể chỉnh threshold qua JVM system property `spring.test.context.failure.threshold` bằng số nguyên dương, nhưng tăng threshold **không chữa config**. Không dùng tăng threshold làm giải pháp chuẩn cho CI.

## 5. Lỗi assertion: test đã đến được bước đối chiếu

### 5.1. Ví dụ

```java
int actual = service.total(100, "HCM"); // thực tế 110
assertEquals(999, actual);               // cố ý sai expected
```

Với JUnit Jupiter, `assertEquals(expected, actual)` thường ném `org.opentest4j.AssertionFailedError` nếu hai giá trị khác nhau. Với AssertJ, `assertThat(actual).isEqualTo(999)` ném `AssertionError` với báo cáo chênh lệch. Trong MockMvc, `andExpect(status().isCreated())` có thể ném assertion error nếu response thực là 200/400/401/500.

Điểm quan trọng:
- **Spring context đã tải được** nếu assert được gọi từ service Spring do `@Autowired` cung cấp.
- Logic ứng dụng có thể đã chạy xong, nhưng output không khớp kỳ vọng.
- Không thể suy ra bug nằm trong test hay production nếu chưa đối chiếu requirement/contract.
- Assertion failure cũng có thể do thời gian, thứ tự collection không được cam kết, fixture lệch, dữ liệu database sót lại, mock stub sai.

### 5.2. Các kiểu assertion failure

| Mã test | Dấu hiệu | Ý nghĩa |
| --- | --- | --- |
| `assertEquals(201, response.status())` | expected 201, got 401 | HTTP contract lệch; phải kiểm security/filter/request |
| `assertThat(items).containsExactly(...)` | list order khác | Contract có yêu cầu order không? Có `ORDER BY` không? |
| `assertThrows(IllegalArgumentException.class, () -> service.call())` | không ném exception | Test kỳ vọng exception nhưng code chạy bình thường |
| `assertThrows(SomeException.class, ...)` | ném exception loại khác | JUnit assertion fail vì type không khớp, dù code ném exception |
| `assertThat(result).usingRecursiveComparison().isEqualTo(expected)` | field path khác | Phân tích field, comparator, null/ID/timestamp |
| `verify(mock).save(...)` | wanted but not invoked | Mockito verification failure; service không đi đến mock đã stub/verify |

`assertThrows` “biến một exception nghiệp vụ đúng thành PASS” nếu loại exception khớp. Nếu exception được mong đợi là subclass, lưu ý `assertThrows` cho phép đúng loại hoặc subtype; dùng `assertThrowsExactly` nếu contract đòi đúng class, không chấp nhận subclass.

## 6. Lỗi nghiệp vụ: expected exception và unexpected exception

Service có thể quy định đầu vào âm không hợp lệ:

```java
public int total(int subtotal, String region) {
    if (subtotal < 0) {
        throw new IllegalArgumentException("subtotal must be >= 0");
    }
    // tính tổng...
}
```

Ba tình huống:

1. **Hành vi đúng**: test gọi `service.total(-1, "HCM")` và dùng `assertThrows(IllegalArgumentException.class, ...)`. Test PASS; exception là kết quả được chờ đợi.
2. **Unhandled business exception**: test gọi giá trị âm nhưng không assert exception; JUnit ghi lỗi khi method ném. Có thể code đúng nhưng **test sai kỳ vọng**.
3. **Bug nghiệp vụ**: test gọi giá trị hợp lệ mà service vẫn ném `IllegalStateException` hoặc trả tổng sai. Đây là lỗi behavior của SUT, có thể biểu hiện thành exception hoặc assertion failure.

Vì vậy, “lỗi nghiệp vụ” mô tả **nguyên nhân trong domain/application code**, không phải một nhãn cố định trong báo cáo test. Nếu exception nghiệp vụ được ném lúc bean khởi tạo trong `@PostConstruct`, **pha biểu hiện** lại là context load. Phải phân biệt hai trục:

| Trục | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Pha thất bại** | Hỏng khi load context, setup, chạy test, assertion hay cleanup? | Bean không tạo được trước `@Test` |
| **Nguyên nhân thực sự** | Thiếu cấu hình, bug logic, kỳ vọng sai, hạ tầng hay test setup? | URL DB sai; thuật toán tính sai; fixture lỗi |

## 7. Project thực hành chạy được: hai test PASS và ba bài tập cố ý FAIL

Ví dụ có 2 lớp test mặc định chạy PASS; 3 **exercise classes không khớp naming pattern mặc định của Maven Surefire** để không làm hỏng `mvn test`. Khi chủ động chọn bằng `-Dtest=...`, mỗi exercise cho thấy một kiểu lỗi. Mọi mã Java dùng package `com.example.contextdiag`.

### 7.1. Cấu trúc

```text
context-diagnosis-lab/
├── pom.xml
├── src/main/java/com/example/contextdiag/
│   ├── ContextDiagnosisApplication.java
│   ├── TaxPolicy.java
│   ├── FixedTaxPolicy.java
│   └── PriceService.java
└── src/test/java/com/example/contextdiag/
    ├── PriceServiceUnitTest.java
    ├── PriceServiceSpringTest.java
    ├── BrokenContextExercise.java
    ├── WrongAssertionExercise.java
    └── UnhandledBusinessExceptionExercise.java
```

### 7.2. Maven POM

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>context-diagnosis-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
```

Spring Boot parent cấu hình dependency management và Maven test tooling. Không cần web server/SQL cho ví dụ này; lỗi Spring context được tạo ra bằng một dependency cố ý thiếu.

### 7.3. Code chính

`src/main/java/com/example/contextdiag/ContextDiagnosisApplication.java`

```java
package com.example.contextdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContextDiagnosisApplication.class, args);
    }
}
```

`src/main/java/com/example/contextdiag/TaxPolicy.java`

```java
package com.example.contextdiag;

public interface TaxPolicy {
    int percent(String region);
}
```

`src/main/java/com/example/contextdiag/FixedTaxPolicy.java`

```java
package com.example.contextdiag;

import org.springframework.stereotype.Component;

@Component
public class FixedTaxPolicy implements TaxPolicy {
    @Override
    public int percent(String region) {
        return 10;
    }
}
```

`src/main/java/com/example/contextdiag/PriceService.java`

```java
package com.example.contextdiag;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    private final TaxPolicy taxPolicy;

    public PriceService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }

    public int total(int subtotal, String region) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
        return subtotal + subtotal * taxPolicy.percent(region) / 100;
    }
}
```

Phép tính sử dụng số nguyên chỉ để minh họa. Production phải cân nhắc overflow, rounding và giá trị tiền tệ bằng `BigDecimal`/minor units theo domain. Với subtotal 100 và thuế 10%, kết quả chính xác là `110`. Với subtotal âm, service ném `IllegalArgumentException` trước khi gọi policy.

### 7.4. Test PASS #1: unit không dùng Spring

`src/test/java/com/example/contextdiag/PriceServiceUnitTest.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PriceServiceUnitTest {
    @Mock
    TaxPolicy taxPolicy;

    @Test
    void totalsExpectedPercentage() {
        when(taxPolicy.percent("HCM")).thenReturn(10);
        PriceService service = new PriceService(taxPolicy);

        assertEquals(110, service.total(100, "HCM"));
    }

    @Test
    void rejectsNegativeSubtotal() {
        PriceService service = new PriceService(taxPolicy);

        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> service.total(-1, "HCM"));

        assertEquals("subtotal must be >= 0", ex.getMessage());
        verifyNoInteractions(taxPolicy);
    }
}
```

Test này chứng minh: quy tắc tính toán và ngoại lệ đầu vào. Không khởi tạo Spring context; vì thế nếu bị assertion fail, **không nên tìm lỗi component scan** của Spring.

### 7.5. Test PASS #2: Spring context tải thành công, logic thật chạy

`src/test/java/com/example/contextdiag/PriceServiceSpringTest.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class PriceServiceSpringTest {
    @Autowired
    PriceService priceService;

    @Test
    void usesRealSpringBeanGraph() {
        assertEquals(110, priceService.total(100, "HCM"));
    }

    @Test
    void expectedBusinessExceptionIsNotTestFailure() {
        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> priceService.total(-1, "HCM"));

        assertEquals("subtotal must be >= 0", ex.getMessage());
    }
}
```

Ở đây `@SpringBootTest` tìm `@SpringBootApplication` trong package và tạo context chứa `PriceService`, `FixedTaxPolicy`. `@Autowired` hoạt động; cả hai assertion PASS. Kiểm ngoại lệ đúng kiểu vẫn là một **test thành công**, không phải “đã có lỗi test”.

### 7.6. Exercise FAIL #1: lỗi tải context trước khi thân test chạy

`src/test/java/com/example/contextdiag/BrokenContextExercise.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.fail;

@SpringBootTest(classes = BrokenContextExercise.BrokenConfig.class)
class BrokenContextExercise {

    interface MissingPort {}

    static class BrokenService {}

    @Configuration(proxyBeanMethods = false)
    static class BrokenConfig {
        @Bean
        BrokenService brokenService(MissingPort missingPort) {
            return new BrokenService();
        }
    }

    @Autowired
    BrokenService brokenService;

    @Test
    void bodyCannotRunIfContextFails() {
        fail("Nếu thấy dòng này thì context đã tải được");
    }
}
```

Vì `@SpringBootTest(classes=...)` chỉ định đúng `BrokenConfig`, Spring cố tạo `BrokenService` bean từ `@Bean` method nhưng không có bất kỳ `MissingPort` bean nào. Việc resolve tham số thất bại trong quá trình load context, thường với `UnsatisfiedDependencyException` có root cause `NoSuchBeanDefinitionException`. **Test method chưa được gọi**, nên `fail("...")` không phải nguyên nhân của lỗi quan sát.

Điểm cần nhận ra trong stack trace:
- Bên ngoài có thể là `IllegalStateException: Failed to load ApplicationContext`.
- Phần giữa chỉ ra `Error creating bean with name 'brokenService'`.
- Phần nguyên nhân chỉ ra không tìm thấy bean loại `MissingPort`.
- Không xử lý bằng thay expected assertion vì chưa hề tới assertion.

**Đây là một exercise cố ý thất bại.** Không thêm vào CI thông thường nếu không có cơ chế tự động khẳng định failure dự kiến.

### 7.7. Exercise FAIL #2: context thành công, assertion sai

`src/test/java/com/example/contextdiag/WrongAssertionExercise.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class WrongAssertionExercise {
    @Autowired
    PriceService priceService;

    @Test
    void expectedValueIsIntentionallyWrong() {
        int actual = priceService.total(100, "HCM");

        assertEquals(999, actual); // expected 999, actual 110
    }
}
```

`PriceService` và `FixedTaxPolicy` có bean đầy đủ; context tải xong, `@Test` đã chạy đến `assertEquals`. Lỗi dự kiến là `AssertionFailedError` với 999 và 110. **Không** cần sửa component scan hoặc TestContext failure threshold. Phải đối chiếu yêu cầu để sửa expected hoặc service; trong bài tập này expected 999 cố tình sai.

### 7.8. Exercise FAIL #3: exception nghiệp vụ không được test xử lý

`src/test/java/com/example/contextdiag/UnhandledBusinessExceptionExercise.java`

```java
package com.example.contextdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class UnhandledBusinessExceptionExercise {
    @Autowired
    PriceService priceService;

    @Test
    void doesNotDeclareExpectedException() {
        priceService.total(-1, "HCM");
    }
}
```

Context tải thành công; `@Test` chạy vào service; service ném `IllegalArgumentException("subtotal must be >= 0")`; do không có `assertThrows` nên JUnit coi đó là exception chưa được test chấp nhận. Một số báo cáo test runner liệt kê vào `Errors`. **Không phải lỗi context**. Nếu behavior “reject negative subtotal” là đúng contract, sửa test bằng `assertThrows` như test PASS #2; không được sửa production để “nuốt” exception.

### 7.9. Chạy chính xác các trường hợp

Trong thư mục có `pom.xml`, với JDK 17+ và Maven:

```bash
# Mặc định chạy hai lớp *Test: tất cả PASS
mvn -q clean test

# Chọn từng exercise có tên không khớp pattern *Test mặc định:
mvn -Dtest=BrokenContextExercise test
mvn -Dtest=WrongAssertionExercise test
mvn -Dtest=UnhandledBusinessExceptionExercise test
```

Maven Surefire mặc định tìm tên lớp theo pattern như `Test*`, `*Test`, `*Tests`, `*TestCase`. Ba lớp kết thúc bằng `Exercise` nên không được chạy bởi `mvn test` thông thường nhưng có thể được chọn với `-Dtest=ClassName`. Chạy **từng exercise riêng** vì mỗi lệnh được thiết kế trả exit code khác 0. Sau mỗi lần quan sát, `mvn -q clean test` vẫn PASS.

| Lệnh | Context | Method `@Test` | Kết quả mong đợi |
| --- | --- | --- | --- |
| `mvn -q clean test` | Unit không cần; Spring test load được | Có | Exit code 0; các test PASS |
| `-Dtest=BrokenContextExercise` | **FAIL** lúc tạo `BrokenService` | Không | `Failed to load ApplicationContext` + nguyên nhân thiếu `MissingPort` |
| `-Dtest=WrongAssertionExercise` | PASS | Có | `AssertionFailedError` do expected 999, actual 110 |
| `-Dtest=UnhandledBusinessExceptionExercise` | PASS | Có, ném exception | `IllegalArgumentException` từ `PriceService.total` |

Output đầy đủ phụ thuộc Maven Surefire, JDK và phiên bản thư viện. Bảng diễn giải **loại lỗi mong đợi**, không giả làm toàn bộ stack trace nguyên văn. Các report có thể xem tại `target/surefire-reports` và các file report của từng lớp test.

## 8. Phương pháp tìm lỗi trong stack trace

Một cách debug hữu hiệu là lần theo thứ tự **lỗi ngoài → các Caused by → nguyên nhân cụ thể nhất**.

### 8.1. Đọc dòng lỗi ở trên cùng nhưng không dừng ở đó

Ví dụ:

```text
IllegalStateException: Failed to load ApplicationContext
    at ...
Caused by: BeanCreationException: Error creating bean 'dataSource'
    at ...
Caused by: IllegalArgumentException: Could not resolve placeholder 'DB_URL'
```

Nếu dừng ở `IllegalStateException` sẽ bỏ qua lỗi cấu hình thật: thiếu `DB_URL`. Không phải mọi `Caused by` cuối cùng đều tự giải thích được; chọn **exception đầu tiên có thông tin có thể hành động** và đọc đoạn stack trace quanh nó.

Tìm trong report/log các từ khóa:
- `Failed to load ApplicationContext`, `Error creating bean`, `UnsatisfiedDependencyException`.
- `Caused by:`, `No qualifying bean`, `Failed to bind properties`, `ConnectException`, `Access denied`.
- `expected:`, `but was:`, `ComparisonFailure`, `AssertionFailedError`.
- Tên class/method trong package ứng dụng (`PriceService.java:...`), không chỉ Spring internal frames.

### 8.2. Xác định test method đã chạy hay chưa

Dùng breakpoint hoặc một thông điệp debug tạm trong body method (không cần để lại trong code production). Nếu test body **không vào** và log nói load context fail, tập trung Spring configuration/bean graph. Nếu body đã vào và assertion fail, đối chiếu actual/expected. Nếu body vào rồi ném exception, xác định method/đầu vào phát sinh.

Một caveat: test có thể fail **trước body** vì `@BeforeEach`, parameter resolution hoặc extension riêng dù Spring context đã load. Vì vậy không thấy body chạy **chưa đủ** để kết luận context lỗi: vẫn phải đọc stack trace.

### 8.3. Đừng tin riêng cột Failures/Errors

Nhiều test runners phân loại `AssertionError` là `failure` và exception khác là `error`. Nhưng:
- Exception từ service trong `assertThrows` đúng → PASS.
- Bug từ service trả sai số → assertion failure.
- Lỗi Spring context ném exception → thường error.
- `AssertionError` do custom init code trong bean → có thể làm context fail.
- `Mockito.verify` mismatch → assertion-like failure.

Phân loại có ích để **khoanh vùng**, không thay thế phân tích pha + root cause.

## 9. Quy trình chẩn đoán 8 bước

1. **Chạy lại một lớp:** chọn test thất bại cụ thể bằng `mvn -Dtest=ClassName test` hoặc Gradle `--tests fully.qualified.ClassName`; ghi chính xác lệnh/JDK/profile/env.
2. **Xác định giai đoạn:** lỗi compile, load context, setup, chạy test, assertion, hay cleanup?
3. **Nếu context load fail:** tìm **lần đầu** cùng context key và `Caused by` có thông tin nhất; kiểm config/bean/profile/driver/migration/port.
4. **Nếu assertion fail:** so expected/actual và contract; kiểm fixture, mock behavior, clock/timezone, numeric type, list order.
5. **Nếu exception khi chạy app code:** kiểm stack frame đầu tiên thuộc source của dự án, input thực tế, loại exception và `assertThrows`.
6. **Giảm bề mặt:** với logic thuần Java, chạy unit test không Spring; với HTTP chỉ dùng `@WebMvcTest`; với SQL dùng `@DataJpaTest` hoặc integration cùng DB; full-context khi cần wiring.
7. **Sửa đúng tầng:** config/bean khi context lỗi; code/expected khi assertion lệch; input/exception contract/hạ tầng khi lỗi nghiệp vụ.
8. **Chạy lại test và suite liên quan:** xác nhận không tạo lỗi mới do profile, context cache, thứ tự chạy hoặc test data bị rò.

Nếu mỗi lần chạy test khác nhau cho kết quả khác nhau, cân nhắc vấn đề isolation/flake: static state, files, DB records, ports, clock, thứ tự test, shared mocks hoặc Testcontainers lifecycle.

## 10. Tình huống Spring Boot thực tế và cách đọc

### 10.1. `@WebMvcTest` báo thiếu service bean

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired MockMvc mvc;
}
```

Nếu `OrderController` cần `OrderService` qua constructor mà slice không chứa `OrderService`, Spring có thể báo `UnsatisfiedDependencyException` khi tạo controller. **Đây là lỗi load slice context**, không phải assertion HTTP. Có thể sửa:

```java
@MockitoBean
OrderService orderService;
```

Các đoạn ở mục này là **minh họa**, vì `OrderController` và `OrderService` thuộc dự án cụ thể. Trong Spring Framework 6.2/Spring Boot 3.5, import `org.springframework.test.context.bean.override.mockito.MockitoBean`. Nếu muốn kiểm service thật cùng controller, cân nhắc `@Import` hoặc phạm vi khác thay vì mock service.

Tuy nhiên, nếu `MockMvc` request chạy và trả `404` do mapping sai, rồi `andExpect(status().isOk())` fail, đó là **assertion failure** dù lỗi gốc vẫn có thể thuộc cấu hình web. Khác biệt nằm ở **pha phát hiện**.

### 10.2. Database không kết nối được

- Nếu DataSource/EntityManagerFactory khởi tạo eager trong context, driver/config/migration lỗi có thể làm `@SpringBootTest` hoặc `@DataJpaTest` fail trước body.
- Nếu kết nối được mở *lazy* chỉ khi repository query chạy, test có thể load context thành công rồi ném `DataAccessException`/SQL exception trong `@Test`.
- Cùng một URL sai nhưng biểu hiện ở pha khác nhau tùy lifecycle. Đừng phân loại chỉ bằng loại error.

Khi test JPA fail, kiểm driver, connection URL, secret/env, transaction, schema migration, Testcontainers và database engine. H2 qua không chứng minh PostgreSQL query/index/constraint giống production.

### 10.3. `@ConfigurationProperties` và placeholder sai

```text
Failed to bind properties under 'app.timeout' to java.time.Duration
Caused by: ...
```

Nếu bean config được tạo lúc context load, đây là config/context failure. Sửa giá trị property, kiểu/format, validation và active profiles. Không chỉnh assertion vì code test chưa được gọi.

### 10.4. Security trả 401/403

Trong `@WebMvcTest` có Spring Security trên classpath, filter chain thường tham gia test. Request thiếu xác thực có thể được xử lý bằng response 401/403 thay vì vào controller. Khi `MockMvc` assert 200 và nhận 401, lỗi test là assertion status sai. Nguyên nhân cần kiểm là security configuration hoặc test request thiếu principal/CSRF token. Dùng Spring Security Test support với `@WithMockUser` hoặc request post processor theo contract; đừng tắt toàn bộ filter chỉ để có test xanh.

### 10.5. Assertion trên JSON/collection

```java
mockMvc.perform(get("/orders"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0].id").value(12));
```

Đây là minh họa trong test đã inject `MockMvc` và import DSL `get`/`status`/`jsonPath`. Nếu API không cam kết order, hard-code `[0]` gây assertion fail dù ứng dụng đúng. Đổi assertion sang tập kết quả/định danh có ý nghĩa, hoặc thêm sort parameter/`ORDER BY` nếu order là contract.

### 10.6. Ngoại lệ business được controller map thành status

Service ném `OrderClosedException` nhưng `@RestControllerAdvice` chuyển thành HTTP 409. Tại ranh giới **service test**, nên `assertThrows(OrderClosedException.class, ...)`. Tại ranh giới **MVC test**, nên assert `status().isConflict()`/JSON lỗi. Không chờ `assertThrows(OrderClosedException.class)` trên lời gọi HTTP nếu exception đã được framework bắt và chuyển thành response.

### 10.7. Mock sai vị trí

`@Mock Repository` tạo Mockito object trong test; nó không tự thay Spring Repository bean. Nếu service `@Autowired` vẫn dùng repository thật, request có thể chạm DB hoặc fail context do datasource. Với Spring TestContext cần mock collaborator, dùng `@MockitoBean` theo bean phù hợp; với unit test thuần Java, tạo service bằng constructor với `@Mock`. Nếu đang kiểm JPA mapping thì **không mock chính repository**.

## 11. Công cụ quan sát đúng mức

### 11.1. Maven Surefire

```bash
mvn -Dtest=PriceServiceSpringTest test
mvn -Dtest=BrokenContextExercise test
```

Lệnh thứ hai cố ý thất bại. Xem `target/surefire-reports/*.txt` hoặc file XML tương ứng; kiểm phần `Caused by` và method. Thêm `-e`/`-X` cho **Maven lifecycle/plugin errors** nếu cần, nhưng Maven debug có thể tạo rất nhiều log và không thay thế Spring root-cause trace.

### 11.2. Gradle

Với dự án Gradle có `test` task:

```bash
./gradlew test --tests "com.example.contextdiag.PriceServiceSpringTest"
./gradlew test --stacktrace
./gradlew test --info
```

`--stacktrace` giúp nhìn exception từ Gradle/plugin; test framework có report/console riêng. Trên Windows dùng `gradlew.bat`. Đây là cách chạy Gradle **minh họa**; project mẫu trong mục 7 là Maven và không có `build.gradle`.

### 11.3. Spring condition evaluation

Khi auto-configuration liên quan, bật report theo tài liệu Spring Boot, ví dụ chạy app với `--debug` hoặc đặt `debug=true` trong config test phù hợp. Báo cáo giúp biết điều kiện `@ConditionalOnClass`/`@ConditionalOnBean`/`@ConditionalOnProperty` nào match hoặc không match. **Điều kiện không match không luôn là lỗi**; chỉ quan tâm khi bean cần cho test bị thiếu.

Nếu log nhiều, có thể bật DEBUG chọn lọc cho `org.springframework.test.context.cache` để xem thống kê context cache và theo dõi việc cùng cấu hình bị tạo mới. Đừng bật DEBUG toàn bộ production rồi commit log secrets.

### 11.4. Context failure threshold

Thông số `spring.test.context.failure.threshold` mặc định 1 trong Spring Framework 6.1+; tài liệu hướng dẫn đặt bằng JVM system property dương. Ví dụ có thể dùng:

```bash
mvn -Dtest=BrokenContextExercise -Dspring.test.context.failure.threshold=2 test
```

Việc Maven/Surefire chuyển system property vào forked test JVM phụ thuộc cách build được cấu hình; nếu cần chắc chắn, đặt JVM system property theo cấu hình Surefire `systemPropertyVariables`/`argLine` phù hợp. Giá trị 2 chỉ yêu cầu thử tải thêm trong cùng context key khi có nhiều lần sử dụng, **không chữa thiếu bean**. Trong dự án mẫu chỉ một lần dùng context lỗi, giá trị này có thể không làm log thay đổi.

### 11.5. `@DirtiesContext` không phải thuốc chữa

`@DirtiesContext` đánh dấu context đã dùng cần được loại khỏi cache/rebuild khi thích hợp. Nó hữu ích nếu test làm bẩn bean definitions/application context state khiến test sau bị ảnh hưởng. Nó không giúp Spring tạo được bean đang thiếu hoặc resolve sai property. Dùng bừa bãi làm suite chậm hơn và có thể che vấn đề isolation.

## 12. Phân biệt các ngoại lệ và trạng thái trong báo cáo CI

Khi review một failure trên CI, ghi lại ít nhất bốn phần:

| Mục | Ví dụ | Giá trị chẩn đoán |
| --- | --- | --- |
| **Test ID** | `BrokenContextExercise#bodyCannotRunIfContextFails` | Xác định test/class |
| **Phase** | `context initialization` | Khoanh vùng cấu hình trước method |
| **Observed exception** | `UnsatisfiedDependencyException -> NoSuchBeanDefinitionException` | Chỉ ra dependency đang thiếu |
| **Expected contract** | Có `MissingPort` bean hay cố ý không? | Quyết định sửa config/test fixture |
| **Reproduction** | `mvn -Dtest=BrokenContextExercise test` | Lặp lại độc lập |
| **Verification** | Context tải được / assertion đạt / DB state đúng | Chứng minh sửa đúng nguyên nhân |

Ngược lại:
- `WrongAssertionExercise`: `phase=assertion`, `observed=AssertionFailedError`, `expected=999`, `actual=110`. Sửa kỳ vọng trong bài tập.
- `UnhandledBusinessExceptionExercise`: `phase=test method`, `observed=IllegalArgumentException`, `contract=reject negative subtotal`. Thêm `assertThrows` nếu đây là output mong đợi.
- Nếu service trả 110 nhưng product requirements yêu cầu 120, test assert 120 là **đúng** và code business sai; không đổi expected thành 110 chỉ để xanh.

## 13. Những lỗi chẩn đoán phổ biến

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Thấy `IllegalStateException` liền kết luận context fail | Business service cũng có thể ném `IllegalStateException` | Đọc stack frame và phase |
| Thấy `@Test` không chạy liền kết luận context fail | `@BeforeEach`/parameter resolver cũng có thể fail | Đọc trace và lifecycle callback |
| Thấy `Tests run:..., Errors:1` rồi đổ lỗi Spring | Exception trong method test cũng được đánh dấu error | Tìm first meaningful application frame |
| Chỉ sửa thông báo `Failed to load ApplicationContext` | Đây thường là wrapper | Truy đến `Caused by` bean/config/Hikari/migration |
| Chỉ nhìn `failure threshold exceeded` | Lần đầu cùng cache key đã fail | Tìm lỗi context ban đầu hoặc chạy lớp độc lập |
| Chuyển mọi test sang `@SpringBootTest` | Tăng context/hạ tầng, không sửa logic | Dùng unit/slice theo boundary |
| Mock tất cả dependency khi context fail | Có thể che bean production bị thiếu | Xem bean nào thực sự thuộc boundary; `enforceOverride=true` khi phù hợp |
| Tắt security/filter để đổi 401 thành 200 | Che policy thay vì kiểm đúng contract | Thêm authentication/CSRF đúng hoặc chỉnh endpoint policy |
| Đổi expected theo actual chỉ để test xanh | Có thể hợp thức hóa bug nghiệp vụ | Đối chiếu requirement và edge case |
| Bỏ `assertThrows` vì thấy exception “đáng sợ” | Exception có thể là API contract | Assert đúng class/message và side effects |
| Rely on `@DirtiesContext` để mọi test PASS | Làm cache chậm, không chữa config và dữ liệu ngoài | Cô lập fixture/cleanup đúng |
| Tăng context failure threshold cho CI | Lặp lại lần load đã biết lỗi | Sửa root cause; threshold chỉ là công cụ chẩn đoán |
| Chỉ chạy IDE, không chạy Maven/Gradle | Profile/classpath/working directory khác CI | Lặp lại build thật và cấu hình môi trường |
| Thấy `BeanCreationException` rồi sửa bean bất kỳ | Bean bị báo có thể phụ thuộc tầng sâu | Theo dependency chain và nguyên nhân trực tiếp |

## 14. Checklist áp dụng trước khi báo lỗi

- [ ] Đã biết test chạy với **JUnit thuần**, Spring slice hay `@SpringBootTest`?
- [ ] Exception xuất hiện trong load context, test setup, test body, assertion hay cleanup?
- [ ] Có `Failed to load ApplicationContext` và chuỗi `Caused by`? Có đọc nguyên nhân sâu nhất có thể hành động?
- [ ] Có message `failure threshold exceeded`? Đã tìm **lần fail ban đầu cùng cache key**?
- [ ] Test body có chạy không? Nếu không, đã loại trừ `@BeforeEach`/extension errors?
- [ ] Nếu assertion fail, đã so contract với expected/actual và fixture, thay vì sửa số cho xanh?
- [ ] Nếu service ném exception, đây là behavior mong đợi cần `assertThrows` hay bug thật?
- [ ] Nếu `@WebMvcTest` thiếu bean, đã phân biệt slice intentionally excludes service với cấu hình production thật thiếu?
- [ ] Nếu lỗi JPA/DB, kết nối xảy ra lúc context initialization hay lúc query trong test?
- [ ] Nếu failure HTTP 401/403/404/500, đã kiểm security, mapping, handler và response status?
- [ ] Nếu đang mock, test có thực sự đưa mock vào đúng object graph Spring/Java?
- [ ] Đã tái hiện bằng đúng một lệnh, xác định JDK/Boot/profile/test class?
- [ ] Sau sửa đã chạy lại case thất bại và test suite liên quan, xác nhận không che rủi ro?

**Nguyên tắc ghi nhớ:** context-load failure cho biết **môi trường Spring của test chưa được dựng thành công**; assertion failure cho biết **một kỳ vọng trong test không khớp quan sát**; exception nghiệp vụ cho biết **code ứng dụng phát tín hiệu hoặc lỗi khi chạy**. Phân biệt pha xảy ra và nguyên nhân gốc sẽ đưa bạn tới đúng tầng cần sửa.

## 15. Tài liệu chính thức

- Spring Framework 6.2 — TestContext Framework: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework.html
- Spring Framework 6.2 — Context Failure Threshold: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework 6.2 — Context Caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Testing how-to: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- JUnit Jupiter 5.11 — Assertions and assertThrows: https://docs.junit.org/5.11.4/user-guide/
- Maven Surefire — Selecting tests: https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html
