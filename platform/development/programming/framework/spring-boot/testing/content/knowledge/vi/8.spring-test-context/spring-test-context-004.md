# `@SpringJUnitConfig` khi cần Spring nhưng không cần Spring Boot

## Mục tiêu học tập

Spring Boot thường cung cấp `@SpringBootTest`, `@WebMvcTest` và nhiều test slice tiện lợi. Tuy nhiên, một class có thể chỉ cần **Dependency Injection (DI), cấu hình bean, profiles, properties hoặc vòng đời Spring TestContext** mà không cần khởi tạo toàn bộ ứng dụng Boot. Với JUnit Jupiter, annotation **`@SpringJUnitConfig`** cho phép viết kiểm thử dùng Spring Framework thuần, với một `ApplicationContext` được khai báo tường minh.

Sau bài này, bạn có thể:

- Giải thích `@SpringJUnitConfig` là tổ hợp của `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`.
- Viết test JUnit 5 có Spring DI **mà không cần `@SpringBootApplication` hoặc `@SpringBootTest`**.
- Chọn lúc nào nên dùng Java unit test thuần, `@SpringJUnitConfig`, Spring Boot slice test hoặc `@SpringBootTest`.
- Cấu hình `@Bean`, lấy property bằng `@TestPropertySource`, tiêm dependency vào test và kiểm tra hành vi thực tế.
- Hiểu vòng đời TestContext, cache `ApplicationContext`, tính độc lập của test, giới hạn của `@Transactional` và những lỗi phổ biến.
- Chạy ví dụ Java 17 bằng Gradle Wrapper, xác nhận test đã được JUnit Platform thực thi.

Bài học tập trung vào **Spring TestContext trong JUnit Jupiter**. Nội dung có thể áp dụng cho module Spring Framework thuần hoặc module nằm trong repository Spring Boot nhưng chỉ cần một context hẹp.

## 1. Khi nào cần Spring nhưng không cần Spring Boot?

Giả sử có một module xử lý giá theo cấu hình. Bạn muốn kiểm rằng:

1. `@Configuration` đã tạo đúng `DiscountPolicy`.
2. `QuoteService` nhận `DiscountPolicy` thông qua Spring DI.
3. Property `pricing.vipDiscount` từ môi trường test thực sự được sử dụng.
4. Kết quả giảm giá của service đúng yêu cầu.

Một unit test thuần bằng `new QuoteService(new DiscountPolicy(...))` có thể kiểm **thuật toán**. Nhưng nó không kiểm rằng Spring đã đọc property, tạo bean và nối các dependency đúng cách. `@SpringJUnitConfig` giải quyết phần khoảng trống đó bằng một context nhỏ, được tạo từ cấu hình bạn chỉ định.

~~~text
JUnit Jupiter
    |
    | @SpringJUnitConfig(PricingTestConfig.class)
    v
SpringExtension + Spring TestContext
    |
    | đọc @ContextConfiguration / @TestPropertySource
    v
AnnotationConfigApplicationContext (ApplicationContext thích hợp)
    |
    +-- Bean DiscountPolicy từ Environment
    |
    +-- Bean QuoteService nhận DiscountPolicy
    |
    +-- Inject QuoteService vào test
    |
    v
@Test -> assertion hành vi cấu hình + DI + logic thật
~~~

Sơ đồ mô tả quá trình thông dụng của một test có cấu hình annotation. Spring TestContext chọn cách tạo `ApplicationContext` phù hợp với khai báo của test; bạn không cần tự gọi `new AnnotationConfigApplicationContext(...)` trong mỗi test.

**Điểm quan trọng:** `@SpringJUnitConfig` **không tự bật Spring Boot auto-configuration**, không tự tìm class `@SpringBootApplication`, không tự khởi động embedded server và không tự tạo database/DataSource. Context có gì phụ thuộc vào `@Configuration`, `@ComponentScan`, `@Import`, profiles, property sources và các thành phần bạn khai báo. Đây là đặc tính giúp test cô lập, nhưng cũng có nghĩa là các bean mong đợi sẽ không tự xuất hiện như khi khởi động Boot đầy đủ.

## 2. `@SpringJUnitConfig` thực sự làm gì?

Về mặt ý nghĩa, có thể coi:

~~~java
@SpringJUnitConfig(PricingTestConfig.class)
class PricingSpringTest {
    // ...
}
~~~

tương đương với tổ hợp:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PricingTestConfig.class)
class PricingSpringTest {
    // ...
}
~~~

Hai đoạn trên **minh họa annotation**; chúng là khai báo trên test class, không phải chương trình Java chạy độc lập. `@SpringJUnitConfig` là annotation tổ hợp (composed annotation) dành cho JUnit Jupiter của **Spring Framework Test**, thường import từ `org.springframework.test.context.junit.jupiter.SpringJUnitConfig`.

Giải thích:

- **`SpringExtension`** tích hợp Spring TestContext Framework với JUnit Jupiter. Nó tham gia các callback của JUnit để chuẩn bị test instance, tiêm dependency và áp dụng các TestExecutionListener liên quan.
- **`@ContextConfiguration`** mô tả **context cần tải**: cấu hình class, file XML hoặc context initializer, tùy lựa chọn. `@SpringJUnitConfig(PricingTestConfig.class)` là cách viết ngắn cho trường `classes`.
- **`@Autowired`** trên field hoặc tham số được Spring xử lý khi TestContext chuẩn bị đối tượng test. Đối tượng được tiêm là bean thật của context, trừ khi bạn tự khai báo test double thông qua cấu hình.
- **`@TestPropertySource`** bổ sung property source cho context của test; `Environment` và các bean có thể đọc nó.
- **`@ActiveProfiles`** chọn profile khi tải context. Dùng để bật những bean/property khác nhau theo nhu cầu kiểm thử.

`@SpringJUnitConfig` thuộc Spring Test, **không phải một annotation riêng của Spring Boot**. Không cần cài `spring-boot-starter-test` cho dự án Spring Framework thuần nếu đã khai báo đúng `spring-test`, `spring-context` và JUnit Jupiter.

### Spring TestContext là gì?

TestContext là một lớp tích hợp dành cho kiểm thử: nó quản lý context, đưa dependency vào test, điều phối các listeners và có thể cache `ApplicationContext` giữa các test có cấu hình tương đương. Nhờ vậy không phải tạo context lại cho từng method.

Cơ chế này là **framework kiểm thử của Spring**. Bạn vẫn dùng JUnit Jupiter để discovery, chạy `@Test`, thực hiện `assertEquals` và xuất kết quả; SpringExtension cung cấp hỗ trợ DI và context. Vì thế phải có cả JUnit Platform được Gradle cấu hình đúng lẫn Spring TestContext dependencies.

## 3. Chọn đúng cấp độ test

| Bạn muốn xác minh điều gì? | Lựa chọn thường hợp lý | Có khởi động Spring context không? |
| --- | --- | --- |
| Thuật toán, validation, mapping thuần Java | JUnit 5 + `new` object | Không |
| Bean wiring, `@Configuration`, property, `@Profile`, Spring converter hoặc AOP có cấu hình hạn chế | `@SpringJUnitConfig` | Có, theo cấu hình chỉ định |
| Controller binding, validation và JSON response trong ứng dụng Spring Boot | `@WebMvcTest`, `MockMvc` | Có, một MVC slice do Boot cấu hình |
| Toàn bộ Spring Boot auto-configuration và phối hợp nhiều bean | `@SpringBootTest` | Có, Boot application context |
| Repository/JPA mapping/transaction qua DB | Test slice hoặc integration test có DB/hạ tầng phù hợp | Có, cần DataSource và các cấu hình liên quan |
| Servlet-based web context trong Spring Framework thuần | `@SpringJUnitWebConfig` khi thích hợp | Có, WebApplicationContext |

**Mục tiêu quyết định công cụ.** Nếu chỉ cần kiểm `discount = subtotal × 0.9`, dùng Java unit test thuần thường đơn giản và nhanh nhất. Nếu cần chứng minh Spring đọc property và tiêm đúng bean, `@SpringJUnitConfig` có giá trị. Nếu cần kiểm Boot binding từ `application.yml`, `@ConfigurationProperties`, web auto-configuration hoặc component scanning của cả ứng dụng, `@SpringBootTest`/slice phù hợp hơn.

Không có quy tắc “Spring test luôn tốt hơn unit test” hay “context test luôn chậm đến mức phải tránh”. Chi phí context phụ thuộc số bean, auto-configuration, I/O và test setup. Khi dùng đúng ranh giới, `@SpringJUnitConfig` thường nhỏ và dễ xác định hơn một Boot context toàn hệ thống.

## 4. Dựng dự án Java 17 + Spring Framework Test + JUnit 5

Ví dụ sau **không áp dụng Spring Boot plugin và không có `@SpringBootApplication`**. Mục tiêu là chạy các bean Java thực bằng một Spring TestContext có property xác định.

### 4.1. Bài toán cần kiểm

Quy tắc giả định:

- Khách VIP được giảm **10%** theo property `pricing.vipDiscount=0.10` của test.
- Khách thường không được giảm.
- Tiền được giữ hai chữ số thập phân, làm tròn `HALF_UP`.
- Tổng tiền `null` hoặc âm bị từ chối bằng `IllegalArgumentException`.
- `QuoteService` được Spring tạo từ `DiscountPolicy` và dùng đúng policy.

Expected cho giá 100.00 của VIP là 90.00; khách thường với giá 100.00 là 100.00. Các giá trị kỳ vọng được xác định từ quy tắc, **không gọi lại chính công thức SUT để sinh expected**.

Cấu trúc file:

~~~text
spring-context-test-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   ├── DiscountPolicy.java
    │   └── QuoteService.java
    └── test/java/com/example/testing/
        ├── PricingTestConfig.java
        └── QuoteServiceSpringTest.java
~~~

Bốn file Java nằm cùng package `com.example.testing`. Các tệp Gradle Wrapper được tạo bằng công cụ Gradle tương thích hoặc đã có trong repository; `gradle-wrapper.jar` là artifact nhị phân **không tự chép nội dung bằng tay**.

**`settings.gradle`**

~~~groovy
rootProject.name = 'spring-context-test-demo'
~~~

**`build.gradle`** — bộ phiên bản minh họa nhất quán: Spring Framework 6.1.15, JUnit Jupiter 5.10.2, JUnit Platform Launcher 1.10.2. Cần JDK 17+ và Gradle phiên bản tương thích.

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.15'

    testImplementation 'org.springframework:spring-test:6.1.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích dependency:

- **`spring-context`** chứa `ApplicationContext`, `@Configuration`, `@Bean`, `Environment` và hỗ trợ DI.
- **`spring-test`** chứa `@SpringJUnitConfig`, `SpringExtension`, TestContext và `@TestPropertySource`.
- **`junit-jupiter`** cung cấp Jupiter API/engine để JUnit 5 phát hiện `@Test`.
- **`junit-platform-launcher`** cung cấp launcher runtime cho Gradle/JUnit Platform.
- **`useJUnitPlatform()`** cho Gradle test task chạy JUnit Platform. Chỉ thêm dependency mà không cấu hình runner chưa phải một pipeline test chắc chắn.

Nếu bạn đang làm trong module Spring Boot **đã có dependency management**, hãy để Boot BOM quản lý version Spring/JUnit tương thích; đừng copy nguyên dependency version từ ví dụ thuần Spring sang Boot project rồi gây lệch bộ Spring Framework. Ví dụ này giữ mọi thứ đơn giản để minh họa annotation, không nhằm nâng cấp package trong repository hiện có.

### 4.2. Mã sản phẩm là Java thuần

**`src/main/java/com/example/testing/DiscountPolicy.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class DiscountPolicy {

    private final BigDecimal vipDiscount;

    public DiscountPolicy(BigDecimal vipDiscount) {
        Objects.requireNonNull(vipDiscount, "vipDiscount");
        if (vipDiscount.signum() < 0
                || vipDiscount.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "vipDiscount must be between 0 and 1");
        }
        this.vipDiscount = vipDiscount;
    }

    public BigDecimal finalAmount(BigDecimal subtotal, boolean vip) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }

        BigDecimal multiplier = vip
                ? BigDecimal.ONE.subtract(vipDiscount)
                : BigDecimal.ONE;

        return subtotal.multiply(multiplier)
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

`DiscountPolicy` không phụ thuộc Spring. Nó nhận tỷ lệ qua constructor, kiểm giá trị từ 0 đến 1, sau đó thực hiện phép tính tiền bằng `BigDecimal`. Đặt `setScale(2, HALF_UP)` để kết quả được chuẩn hóa theo hợp đồng của ví dụ.

**`src/main/java/com/example/testing/QuoteService.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.util.Objects;

public final class QuoteService {

    private final DiscountPolicy policy;

    public QuoteService(DiscountPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    public BigDecimal quote(BigDecimal subtotal, boolean vip) {
        return policy.finalAmount(subtotal, vip);
    }
}
~~~

`QuoteService` cũng là Java thuần; mọi tương tác với Spring sẽ đặt trong **cấu hình bean của test**. Thiết kế này giúp tách rõ ba câu hỏi: thuật toán có đúng không, service dùng dependency nào, và Spring DI đã nối đúng dependency hay chưa.

### 4.3. Cấu hình Spring chỉ dùng cho test

**`src/test/java/com/example/testing/PricingTestConfig.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class PricingTestConfig {

    @Bean
    DiscountPolicy discountPolicy(Environment environment) {
        String rateText =
                environment.getRequiredProperty("pricing.vipDiscount");

        return new DiscountPolicy(new BigDecimal(rateText));
    }

    @Bean
    QuoteService quoteService(DiscountPolicy policy) {
        return new QuoteService(policy);
    }
}
~~~

Giải thích những chi tiết quan trọng:

- `@Configuration` cho Spring biết class chứa phương thức tạo bean.
- `@Bean` đăng ký `DiscountPolicy` và `QuoteService` trong `ApplicationContext`.
- Spring tự cung cấp `Environment` vào bean method, từ đó đọc property của test.
- Spring cũng tìm bean `DiscountPolicy` và truyền vào `quoteService(DiscountPolicy policy)`. Đây là **DI thực sự**, không phải một mock.
- `@Configuration(proxyBeanMethods = false)` hợp lý vì các bean method độc lập: method `quoteService` nhận dependency qua tham số thay vì gọi `discountPolicy()` trực tiếp trong class cấu hình. Không dựa vào interception giữa các `@Bean` methods.
- Cấu hình đặt ở `src/test/java` nên chỉ tồn tại trên test classpath của module này.

Nếu property `pricing.vipDiscount` không có, `getRequiredProperty(...)` ném exception khi context tạo `DiscountPolicy`; test sẽ fail ở khởi tạo context. Đây là tín hiệu cấu hình thiếu, khác với một assertion về business logic.

### 4.4. Test bằng `@SpringJUnitConfig`

**`src/test/java/com/example/testing/QuoteServiceSpringTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(PricingTestConfig.class)
@TestPropertySource(properties = "pricing.vipDiscount=0.10")
class QuoteServiceSpringTest {

    @Autowired
    private QuoteService quoteService;

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void vipCustomerGetsDiscountFromTestConfiguration() {
        // Arrange: Spring inject QuoteService and property 0.10
        BigDecimal subtotal = new BigDecimal("100.00");

        // Act
        BigDecimal actual = quoteService.quote(subtotal, true);

        // Assert: 10% discount leaves 90.00
        assertEquals(new BigDecimal("90.00"), actual);
    }

    @Test
    void regularCustomerKeepsFullPrice() {
        BigDecimal actual =
                quoteService.quote(new BigDecimal("100.00"), false);

        assertEquals(new BigDecimal("100.00"), actual);
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> quoteService.quote(new BigDecimal("-1.00"), true));
    }

    @Test
    void injectedServiceIsManagedBySpring() {
        assertSame(
                applicationContext.getBean(QuoteService.class),
                quoteService);
    }
}
~~~

Class này chỉ dùng:

- `@SpringJUnitConfig(PricingTestConfig.class)` để tạo context từ bean config chỉ định.
- `@TestPropertySource` để cung cấp tỷ lệ giảm giá cho `Environment`.
- `@Autowired` để đưa các bean vào test; `ApplicationContext` cũng được Spring cung cấp.
- `@Test` và `Assertions` của JUnit Jupiter để chứng minh hành vi.

Không có `@SpringBootTest`, `@SpringBootApplication`, `@SpringBootConfiguration` hoặc Boot auto-configuration. **Bốn test method có bốn lượt thực thi** khi class được JUnit Jupiter phát hiện. Các test không in `System.out`, nên **không có stdout nghiệp vụ**; kết quả pass/fail được ghi qua Gradle/JUnit report.

**Test thứ tư bảo vệ wiring:** `applicationContext.getBean(QuoteService.class)` và field `quoteService` phải cùng tham chiếu bean singleton (scope mặc định của `@Bean`). Đây là assertion về **cấu hình Spring**; test này có thể vô ích nếu mục tiêu chỉ là kiểm công thức, nhưng ở đây nó giúp người học nhìn rõ DI.

**Không hiểu sai test đầu:** khi test VIP pass, nó cho thấy cấu hình `0.10`, bean wiring và phép tính phối hợp đúng trên ví dụ đã chọn; nó chưa chứng minh tất cả quy tắc giá hoặc trường hợp biên. Để kiểm sâu `DiscountPolicy`, bổ sung unit tests trực tiếp với nhiều đầu vào và policy khác nhau, thay vì mở context cho mọi case.

### 4.5. Chạy bằng Gradle Wrapper

Từ thư mục có `settings.gradle`, `gradlew`/`gradlew.bat`:

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
./gradlew test --tests 'com.example.testing.QuoteServiceSpringTest'
~~~

Xem Gradle/JUnit report tại:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.testing.QuoteServiceSpringTest.xml
~~~

Với file đầy đủ như trên, dự kiến **4 test pass**. `BUILD SUCCESSFUL` là thông điệp của Gradle nếu build thành công, không phải stdout do test tự in. Nếu task trả `UP-TO-DATE` hoặc `FROM-CACHE`, kết quả có thể được tái sử dụng; để điều tra vấn đề, chạy `./gradlew test --rerun-tasks` khi cần.

Nếu repository chưa có Wrapper, cần tạo bằng một bản Gradle tương thích đã cài, ví dụ `gradle wrapper --gradle-version 8.5` đối với dự án demo Java 17, rồi giữ đủ script và file wrapper trong VCS. Đây là bước bootstrap; với repository thực, hãy dùng Gradle version đã được dự án chọn. Java toolchain vẫn cần JDK 17 có sẵn hoặc cơ chế provisioning đã cấu hình.

## 5. Mở rộng `@SpringJUnitConfig` khi cần nhiều cấu hình

### 5.1. Viết tương đương ở dạng dài

Nếu muốn thấy rõ từng phần của annotation, đoạn sau tương đương về mục đích với khai báo ví dụ:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PricingTestConfig.class)
@TestPropertySource(properties = "pricing.vipDiscount=0.10")
class QuoteServiceSpringTest {
    // Có thể viết cùng các @Autowired và @Test method như ví dụ.
}
~~~

Đoạn này **chỉ minh họa cấu hình annotation**, vì phần thân test đã có ở mục 4.4. Nếu dùng dạng dài, cần import `org.junit.jupiter.api.extension.ExtendWith`, `org.springframework.test.context.junit.jupiter.SpringExtension` và `org.springframework.test.context.ContextConfiguration`.

**Không thêm cả `@SpringJUnitConfig` và `@ExtendWith(SpringExtension.class)` cho cùng mục đích** khi không có lý do đặc biệt. Viết chồng annotation không làm test “Spring hơn” hay tự động thêm bean; nó chỉ gây khó hiểu vì `@SpringJUnitConfig` đã chứa phần mở rộng cần thiết.

### 5.2. Nhiều config class

Nếu có những nhóm bean tách biệt, có thể ghép:

~~~java
@SpringJUnitConfig(classes = {
        CoreConfig.class,
        TestAdapterConfig.class
})
class CoreIntegrationTest {
    // Các bean từ hai @Configuration classes tham gia context.
}
~~~

Đây là snippet cú pháp: `CoreConfig`, `TestAdapterConfig` và các imports phải tồn tại trong một dự án thực. Đừng nhầm việc liệt kê hai class trong annotation với việc **scan toàn bộ package**; TestContext tải chính các cấu hình đã chỉ định và các import/scan mà những cấu hình ấy yêu cầu.

Dùng `@Import(SomeConfig.class)` bên trong một config khi cần tái sử dụng một nhóm bean. Nếu có annotation `@ComponentScan`, hãy giới hạn package để tránh vô tình nạp rất nhiều bean ngoài phạm vi test.

### 5.3. Profiles và properties

Khi chỉ cần khác cấu hình giữa các test, kết hợp:

~~~java
@SpringJUnitConfig(PricingTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "pricing.vipDiscount=0.20")
class TwentyPercentDiscountTest {
    // Test case cho cấu hình giảm 20%, khác ví dụ 10%.
}
~~~

Đây là snippet cấu hình; không tự là chương trình chạy được. Import `org.springframework.test.context.ActiveProfiles`, `org.springframework.test.context.TestPropertySource`.

`@ActiveProfiles("test")` chọn profile hoạt động khi TestContext tạo context. Nó **không tự tạo hoặc đọc `application-test.yml` theo quy ước của Spring Boot** trong một project Spring Framework thuần. Nếu muốn property từ file, khai báo `@TestPropertySource(locations = "classpath:pricing-test.properties")` hoặc cung cấp `PropertySource` bằng cấu hình Spring phù hợp. `@TestPropertySource(properties = "...")` là cách thuận tiện và dễ đọc cho một vài giá trị nhỏ.

Mỗi tổ hợp cấu hình, profiles và property source có thể dẫn đến **khóa cache context khác nhau**. Test với `0.10` và test với `0.20` không nên giả định sẽ dùng cùng một context singleton.

### 5.4. Tiêm dependency qua constructor hoặc method parameters

Ví dụ đã dùng field injection để đơn giản. Trong test JUnit Jupiter + SpringExtension, còn có thể dùng constructor injection được Spring quản lý khi đánh dấu phù hợp:

~~~java
@SpringJUnitConfig(PricingTestConfig.class)
@TestPropertySource(properties = "pricing.vipDiscount=0.10")
class ConstructorInjectionExampleTest {

    private final QuoteService quoteService;

    @Autowired
    ConstructorInjectionExampleTest(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @Test
    void quoteServiceIsInjected() {
        assertNotNull(quoteService);
    }
}
~~~

Đây là snippet có body minh họa; để biên dịch, thêm import `@Autowired`, `@Test`, `assertNotNull`, `@SpringJUnitConfig`, `@TestPropertySource`, class `QuoteService` và `PricingTestConfig` từ ví dụ. Với test class nhiều constructor hoặc kết hợp cơ chế parameter resolution, cần xác định rõ JUnit/Spring chịu trách nhiệm cung cấp những tham số nào; việc thêm `@Autowired` lên constructor giúp Spring giải quyết.

SpringExtension cũng hỗ trợ resolution ở tham số method thử nghiệm (ví dụ `@Autowired QuoteService`), nhưng không buộc phải sử dụng. Tránh có nhiều kiểu injection khác nhau trong cùng suite nếu không tăng độ rõ ràng.

### 5.5. XML context (khi dự án legacy cần)

`@SpringJUnitConfig` có thể trỏ tới resource cấu hình XML bằng thuộc tính `locations` theo hợp đồng của `@ContextConfiguration`; ví dụ cú pháp:

~~~java
@SpringJUnitConfig(locations = "classpath:test-context.xml")
class LegacyXmlContextTest {
    // ...
}
~~~

Snippet chỉ minh họa, yêu cầu file `test-context.xml` tồn tại trên classpath và định nghĩa bean hợp lệ. Không đưa cách cấu hình XML mới vào mọi dự án hiện đại khi Java `@Configuration` đã đủ. Mục đích của `locations` là cho phép dùng các context definition phù hợp trong dự án đang có.

## 6. Vòng đời TestContext và cache `ApplicationContext`

Khi JUnit tạo test instance, SpringExtension tích hợp với TestContext để chuẩn bị bean injection; TestContext có thể giữ cache của các `ApplicationContext` đã tải nhằm giảm thời gian khởi tạo. Trong các test có cùng cấu hình Spring tương đương, context thường được **tái sử dụng**, thay vì tạo lại cho mỗi method.

Điều đó có hai hệ quả:

**Lợi ích:** Tạo `ApplicationContext` một lần cho nhiều test có cùng cấu hình giúp suite nhanh hơn và giảm chi phí đăng ký bean. Ngay cả khi test class có nhiều method, không nên mặc định context mở lại cho từng method.

**Rủi ro:** Singleton bean có **trạng thái mutable** có thể giữ dữ liệu giữa các method/test class. Nếu test A sửa trạng thái singleton và không reset, test B có thể phụ thuộc thứ tự chạy hoặc fail ngẫu nhiên. Đây là lỗi test isolation, không nhất thiết là lỗi của `@SpringJUnitConfig`.

### Cách giữ test độc lập

- Ưu tiên bean domain/service **stateless** khi có thể. Ví dụ `DiscountPolicy` và `QuoteService` không lưu dữ liệu mutable giữa test.
- Mỗi test tạo input riêng; đừng thay đổi property hoặc trường singleton dùng chung rồi quên reset.
- Nếu có database/repository giả giữ trạng thái, dọn dữ liệu hoặc tạo fixture độc lập phù hợp với lifecycle.
- Nếu test tạo luồng, lịch hoặc tác động hệ thống, dừng/đóng resource đúng cách; context cache không tự cô lập mọi side effect.
- Chỉ dùng `@DirtiesContext` khi test **thực sự làm bẩn cấu hình/trạng thái context** đến mức không thể tái sử dụng an toàn. Annotation này buộc Spring bỏ context khỏi cache và tải lại khi cần, tăng chi phí. Nó không phải nút “reset mọi thứ” nên được gắn mặc định vào tất cả test.
- Với kiểm thử transaction, TestContext hỗ trợ transaction management nếu có `PlatformTransactionManager` và listeners/cấu hình đúng. Trong ví dụ thuần Spring không có DataSource/transaction manager, vì vậy gắn `@Transactional` vào test không tự tạo DB hoặc bảo đảm rollback.

### Caching không phải kiểm thử trạng thái

Đừng viết test kiểu “test 1 thêm item, test 2 thấy item đã thêm” như một chủ đích thiết kế; JUnit không cam kết chạy theo thứ tự mà bạn tưởng trừ khi đã thiết lập thứ tự rõ ràng, và thứ tự thường không cần thiết cho unit/integration tests độc lập. Mỗi test nên tự chuẩn bị trạng thái ban đầu, hoặc dùng fixture đặt ở lifecycle thích hợp rồi reset có kiểm soát.

## 7. Những thứ `@SpringJUnitConfig` không tự cung cấp

| Điều muốn dùng | Vì sao chưa chắc có | Cần bổ sung gì? |
| --- | --- | --- |
| Một bean theo interface | Chưa khai báo bean hoặc component scan | `@Bean`, `@Import` hoặc `@ComponentScan` đúng phạm vi |
| Property từ `application.yml` | Quy ước Boot chưa được bật | `@TestPropertySource`, `@PropertySource` với định dạng phù hợp hoặc custom property setup |
| Embedded HTTP server | Không có Boot web server lifecycle mặc định | Web context/Boot test thích hợp tùy mục tiêu |
| `MockMvc` auto-config | Không tự bật MVC setup/Boot auto config | Web test context hoặc cấu hình `MockMvc` phù hợp; trong Boot có thể dùng `@WebMvcTest` |
| JPA `EntityManager`, repository và DB | Chưa có persistence config, DataSource, transaction manager | Cấu hình persistence/integration test riêng |
| Spring Security filter chain | Chưa nạp Security config | Import/cấu hình Security khi hợp đồng yêu cầu |
| `@ConfigurationProperties` bind theo quy ước Boot | Binder/auto config của Boot không tự xuất hiện | Boot test phù hợp hoặc thiết lập binding rõ ràng |
| Một “tốc độ nhanh bảo đảm” | Tải các bean/hạ tầng phụ thuộc config thực tế | Giữ context hẹp và fixture độc lập |
| Mockito mock của mọi dependency | Spring TestContext không tự mock | Khai báo test double bằng cơ chế phù hợp hoặc dùng object thật |

Một trường hợp dễ gây hiểu nhầm: trong ứng dụng Spring Boot, một `@Configuration` có `@ComponentScan` ở package gốc rộng có thể kéo vào nhiều bean, kể cả các bean gắn với Boot/application config. Lúc ấy test thực tế không còn “nhẹ” như mong đợi. Hãy **giới hạn rõ classes/imports/scan** thay vì dựa vào cảm giác tên annotation là “slice”.

Ngược lại, nếu test đòi kiểm đầy đủ Boot behavior nhưng lại tự chọn vài bean trong `@SpringJUnitConfig`, việc test pass không bảo đảm application Boot khởi động được. Hai loại test phải bổ sung bằng chứng cho nhau.

## 8. So sánh với `@SpringBootTest` và `@SpringJUnitWebConfig`

### `@SpringJUnitConfig` và `@SpringBootTest`

`@SpringJUnitConfig` nêu rõ Spring context configuration và kích hoạt SpringExtension qua Spring Test. `@SpringBootTest` dùng Spring Boot test infrastructure để tìm/khởi tạo Boot application configuration và áp dụng cơ chế Boot phù hợp. Cả hai dùng JUnit Jupiter qua SpringExtension khi cấu hình đúng, nhưng **phạm vi khởi động và các tính năng được kích hoạt khác nhau**.

Với module Spring Framework thuần, dùng `@SpringJUnitConfig` để kiểm bean wiring/config. Với module Boot mà test cần property binding, security/web/repository auto config của Boot, dùng Boot test slice hoặc `@SpringBootTest` theo mục tiêu. Không mặc định `@SpringBootTest` có nghĩa sẽ khởi chạy HTTP server thật: chế độ `webEnvironment` mặc định không yêu cầu server trên port thực, còn các chế độ random/defined port mới thay đổi hành vi đó.

### `@SpringJUnitWebConfig`

Spring Framework cũng có `@SpringJUnitWebConfig` cho JUnit Jupiter với **`WebApplicationContext`**; annotation này kết hợp phần lớn lợi ích của `@SpringJUnitConfig` với `@WebAppConfiguration`. Nó phù hợp khi cần kiểm cấu hình web của Spring MVC thuần.

Tuy vậy, nếu project là Spring Boot và chỉ cần kiểm controller serialization/binding, `@WebMvcTest` cùng `MockMvc` thường làm rõ mục đích hơn. `@SpringJUnitWebConfig` không tự bật Boot MVC auto-configuration tương đương `@WebMvcTest`.

## 9. Các lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Cách chẩn đoán/sửa |
| --- | --- | --- |
| `No qualifying bean of type…` | Chưa khai báo bean cần tiêm hoặc config không được load | Kiểm `@SpringJUnitConfig(classes=...)`, `@Bean`, import/scan, profile |
| `Failed to load ApplicationContext` | Cấu hình bean lỗi, property thiếu, exception lúc tạo bean | Đọc **root cause** phía dưới stack trace, không chỉ dòng đầu |
| Property `pricing.vipDiscount` không tìm thấy | Chưa có `@TestPropertySource`, sai key hoặc nguồn property | Kiểm key và annotation, xác minh context dùng config mong muốn |
| JUnit không phát hiện test | Thiếu JUnit Jupiter engine/`useJUnitPlatform()` | Kiểm Gradle test dependency, task và `org.junit.jupiter.api.Test` |
| `@Autowired` field null | Không dùng SpringExtension, test bị tạo/thao tác ngoài TestContext hoặc thiếu bean | Dùng `@SpringJUnitConfig` đúng trên JUnit Jupiter test |
| Test dùng nhầm `org.junit.Test` | JUnit 4 và Jupiter khác nhau | Import `org.junit.jupiter.api.Test`; nếu có legacy test cần migration/engine phù hợp |
| Có bean khác thừa làm test rất chậm | Component scan quá rộng hoặc cấu hình kéo I/O | Giới hạn test config classes và các import cần thiết |
| Test fail khi chạy cả suite nhưng pass riêng | Singleton shared mutable state, context cache, shared DB, thứ tự chạy | Reset fixture, tránh state giữa test, dùng `@DirtiesContext` có chủ đích |
| `@Transactional` không rollback như dự kiến | Thiếu transaction manager hoặc test không được quản lý đúng | Cấu hình persistence/transaction manager và test level thích hợp |
| `@ConfigurationProperties` chưa bind | Đang dùng Spring thuần nhưng kỳ vọng Boot Binder | Dùng Boot test hoặc tự cấu hình binding |
| Trùng context/bean definition hoặc có hai bean cùng type | Import/config bị lặp hoặc hai bean không phân biệt | Chỉ rõ test config, `@Qualifier` khi nghiệp vụ cần |
| Test chỉ verify bean tồn tại | Không kiểm hành vi hoặc property thực sự áp dụng | Assert cả kết quả nghiệp vụ và giá trị property ảnh hưởng tới output |
| Context fail vì thiếu external service | Test config vô tình kéo dependency ngoài | Dùng fake/test adapter, tách đúng ranh giới, bỏ scan không cần |
| Context không được cache như mong đợi | Config, profiles, properties khác; `@DirtiesContext` đang kích hoạt | Kiểm tập cấu hình test; tránh tạo nhiều variant tương đương nếu không cần |

### Cách xác định test đang sai ở tầng nào

Nếu JUnit báo **không tìm thấy test**, hãy bắt đầu ở runner/import/dependency, chưa kết luận Spring bean sai.

Nếu JUnit đã chạy nhưng Spring báo **Failed to load ApplicationContext**, hãy đọc nguyên nhân gần nhất trong stack trace: thiếu bean, property, bean factory method ném exception hoặc profile không phù hợp.

Nếu context tải và injection thành công nhưng `assertEquals` fail, cần kiểm **nghiệp vụ/expected/giá trị property**. Đừng đổi cấu hình Gradle hay thêm `@DirtiesContext` như cách sửa mặc định cho một assertion sai giá.

Nếu test chỉ fail trong CI, kiểm JDK/Gradle, dependency repository, environment variables, property resources và I/O ngoài máy. Một test thật sự chỉ dùng bean Java như ví dụ thường dễ tái lập hơn test vô tình kéo database/network.

## 10. Quy trình áp dụng vào codebase

1. **Nêu rõ hành vi cần chứng minh.** Nếu là công thức thuần Java, ưu tiên unit test trực tiếp. Nếu là bean wiring/property/profile/AOP, cân nhắc Spring TestContext.
2. **Tạo test config nhỏ nhất có thể.** Dùng `@Configuration` và các `@Bean`/`@Import` thực sự cần thiết; hạn chế component scan.
3. **Dùng `@SpringJUnitConfig(MyConfig.class)`.** Nó đã tích hợp JUnit Jupiter và SpringExtension. Thêm `@TestPropertySource`/`@ActiveProfiles` khi có yêu cầu.
4. **Tiêm bean qua `@Autowired`.** Giữ setup của test rõ ràng; đừng trộn việc tạo service bằng `new` và nhận bean từ Spring mà không giải thích phạm vi.
5. **Viết assertion từ hợp đồng.** Với ví dụ giá, kiểm VIP 100.00 -> 90.00 và khách thường -> 100.00; kiểm input lỗi không được xử lý tùy tiện.
6. **Chạy bằng Wrapper và đọc report.** Xác định test có được discover, context có tải, assertion có pass và không có I/O không mong muốn.
7. **Giữ state độc lập.** Hãy nhớ context có thể cache và singleton tồn tại qua nhiều lượt test; dọn state có chủ đích.
8. **Thêm test ở đúng mức nếu cần.** Nếu yêu cầu chứng minh HTTP/DB/Boot auto-config, tăng cấp bằng MVC slice/Boot integration test; không kết luận từ test context nhỏ rằng toàn hệ thống đúng.

## 11. Bài tập tự luyện

**Bài A — thay property:** Đổi `@TestPropertySource(properties = "pricing.vipDiscount=0.10")` thành `0.20`. Trước khi chạy, hãy đổi expected của VIP từ 90.00 thành 80.00 (với subtotal 100.00). Nếu bean đọc đúng property, test phải pass. Nếu giữ expected 90.00, test VIP phải fail; sau đó hoàn nguyên theo bài gốc.

**Bài B — bỏ bean:** Tạm bỏ `@Bean QuoteService quoteService(...)` khỏi `PricingTestConfig`. Dự kiến context không thể inject field `QuoteService` của test. Quan sát root cause và khôi phục. Bài tập chứng minh test thực sự kiểm Spring wiring chứ không tự tạo service ở ngoài context.

**Bài C — unit test thuần:** Viết một `DiscountPolicyTest` không dùng bất kỳ Spring annotation nào, tạo `new DiscountPolicy(new BigDecimal("0.10"))`. Kiểm ba giá trị 0.00, 10.05 (làm tròn HALF_UP ra 9.05 nếu VIP) và tổng âm. Giải thích vì sao không cần Spring context cho những assertion đó.

**Bài D — profiles:** Tạo hai `@Configuration` với `@Profile("test")` và `@Profile("prod")`, tạo bean cùng một interface theo profile khác nhau. Dùng `@SpringJUnitConfig` + `@ActiveProfiles("test")` để khẳng định bean test được inject. Tránh scan cả package hoặc import cả hai bean không điều kiện.

**Bài E — context cache:** Tạo một singleton fake repository có danh sách mutable, viết test thêm dữ liệu rồi chạy nhiều method. Quan sát nguy cơ rò trạng thái khi tái sử dụng context. Sửa bằng cách dọn danh sách trước mỗi test hoặc dùng fixture độc lập; chỉ sử dụng `@DirtiesContext` nếu cách reset hợp lý không khả thi.

## 12. Checklist trước khi hoàn tất

- [ ] Tôi đang cần kiểm **Spring configuration/wiring**, không chỉ một phép tính thuần Java?
- [ ] `@SpringJUnitConfig` trỏ đúng config class; JUnit Jupiter và `spring-test` có trên test classpath?
- [ ] `useJUnitPlatform()` được áp dụng cho Gradle test task?
- [ ] Mọi bean cần dùng đều do context được chỉ định tạo, không lệ thuộc vào Boot auto-config vô tình?
- [ ] Property và profile có nguồn rõ ràng (`@TestPropertySource`/`@ActiveProfiles` hoặc cấu hình tương đương)?
- [ ] Assertion kiểm cả hành vi có ý nghĩa, không chỉ “bean != null”?
- [ ] Các test không phụ thuộc trạng thái singleton chia sẻ, thứ tự chạy hay hạ tầng không kiểm soát?
- [ ] Khi kiểm HTTP, transaction, repository hay Boot auto-config, tôi đã dùng đúng tầng test tương ứng?
- [ ] Báo cáo Gradle/JUnit thể hiện số test thực sự được thực thi và failure message chỉ ra nguyên nhân?

**Ghi nhớ:** `@SpringJUnitConfig` là cách gọn để dùng **SpringExtension + @ContextConfiguration** trong JUnit Jupiter. Nó phù hợp khi bạn cần **Spring DI và TestContext** với tập bean cấu hình tường minh, nhưng không cần Spring Boot khởi tạo ứng dụng. Kiểm chứng thuật toán bằng unit test thuần khi có thể; kiểm Bean/Property/Profile với một Spring context nhỏ; chỉ mở rộng sang Boot hoặc hạ tầng thật khi hợp đồng đòi hỏi.
