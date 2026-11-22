# `@Primary`, `@Qualifier` và giới hạn của việc bật bean definition overriding trong test Spring Boot

## Mục tiêu

Trong test Spring Boot, ta thường muốn thay một dependency production bằng phiên bản kiểm thử: đồng hồ cố định, fake gateway, implementation đọc dữ liệu in-memory, hoặc một policy chuyên cho kịch bản test. Có ba thao tác rất dễ bị gọi chung là “override bean”, nhưng **khác nhau về bản chất**:

1. **Thêm bean mới cùng kiểu** rồi dùng `@Primary` để ưu tiên nó khi Spring tiêm dependency theo type.
2. **Chỉ định bean phải nhận** bằng `@Qualifier` tại điểm injection.
3. **Thay bean definition trùng tên** khi Spring được phép overriding — một cơ chế của bean registry có rủi ro và giới hạn riêng.

Sau bài này, bạn có thể:

- Giải thích bean **name**, bean **type**, candidate và cách Spring chọn dependency để inject.
- Dùng `@Primary` và `@Qualifier` đúng ngữ nghĩa, không nhầm với việc xóa hay ghi đè một bean definition.
- Phân biệt `NoUniqueBeanDefinitionException` với lỗi xung đột định nghĩa bean cùng tên.
- Hiểu tại sao Spring Boot thường **không cho phép bean definition overriding theo tên** theo mặc định và khi bật `spring.main.allow-bean-definition-overriding=true` cũng không giải quyết mọi lỗi DI.
- Viết test JUnit Jupiter/Spring Boot sử dụng `@TestConfiguration` + `@Import` để thêm test bean một cách có kiểm soát.
- Kiểm tra cả logic nghiệp vụ lẫn bean đã được chọn, thay vì chỉ assert “context khởi động thành công”.
- Nhận biết trường hợp nên dùng test bean, `@MockBean`/`@MockitoBean` theo phiên bản, profile/conditional config hoặc unit test Java thuần.

Phạm vi bài học là **thay thế hoặc lựa chọn bean trong môi trường kiểm thử**, không phải hướng dẫn bật ghi đè bean toàn ứng dụng.

## 1. Bean type, bean name và injection candidate

Mỗi bean trong Spring container có một **tên (bean name)** và một tập kiểu có thể dùng để tìm/tiêm nó. Ví dụ:

~~~java
@Bean
FeePolicy standardFeePolicy() {
    return amount -> amount >= 500 ? 0 : 30;
}
~~~

Spring đăng ký bean tên `standardFeePolicy` (mặc định theo tên phương thức `@Bean`), với kiểu `FeePolicy`. Đây chỉ là snippet khai báo; `FeePolicy` được định nghĩa đầy đủ trong ví dụ chạy được ở mục 4.

Giả sử test đăng ký thêm:

~~~java
@Bean
@Primary
FeePolicy promoFeePolicy() {
    return amount -> amount >= 500 ? 0 : 10;
}
~~~

Lúc này có **hai bean khác tên cùng type**:

~~~text
ApplicationContext
  FeePolicy candidates:
    - "standardFeePolicy" : FeePolicy, production
    - "promoFeePolicy"    : FeePolicy, test, @Primary
~~~

Cả hai định nghĩa có thể cùng tồn tại. Khi một constructor nhận `FeePolicy` nhưng không có qualifier, Spring ưu tiên candidate có `@Primary` nếu việc phân giải phù hợp và chỉ có một primary hợp lệ. Khi constructor yêu cầu `@Qualifier("standardFeePolicy")`, nó hướng tới bean production cụ thể bất chấp bean test đang được ưu tiên cho injection không qualifier.

Điều đó khác với **trùng tên**:

~~~text
ApplicationContext
  "standardFeePolicy" : definition từ ProductionConfig
  "standardFeePolicy" : definition từ TestConfig     <-- xung đột tên
~~~

Đây là vấn đề **hai định nghĩa cùng khóa tên** trong bean registry, không phải vấn đề hai candidate cùng type. `@Primary` không giải quyết xung đột tên.

### Thuật ngữ cần phân biệt

| Thuật ngữ | Nghĩa | Câu hỏi phải trả lời |
| --- | --- | --- |
| Bean definition | Bản mô tả Spring sẽ tạo một bean ra sao | Có định nghĩa nào đăng ký cùng tên không? |
| Bean name | Định danh để truy xuất bean trong container | Có trùng khóa tên giữa hai định nghĩa không? |
| Bean type | Kiểu interface/class dùng để phân giải dependency | Có bao nhiêu candidate phù hợp? |
| `@Primary` | Ưu tiên một candidate khi injection không có chỉ định chặt hơn | Bean nào được chọn theo type? |
| `@Qualifier` | Thu hẹp/chỉ định candidate ở injection point | Điểm tiêm này muốn bean nào? |
| Definition overriding | Cho phép một định nghĩa cùng tên thay thế định nghĩa đã có | Định nghĩa cuối cùng nào được giữ cho tên đó? |

Câu ghi nhớ: **`@Primary` chọn, `@Qualifier` chỉ định, còn bean definition overriding thay định nghĩa theo tên.** Ba cơ chế không thể hoán đổi cho nhau.

## 2. `@Primary`: ưu tiên bean, không xóa bean cũ

`@Primary` thuộc `org.springframework.context.annotation.Primary`. Nó có thể đặt lên class được Spring quản lý hoặc `@Bean` method. Khi Spring tìm **một bean** cho một dependency theo type và có nhiều candidate, annotation đánh dấu candidate được ưu tiên.

~~~java
@Configuration
class PricingConfig {

    @Bean
    FeePolicy standardFeePolicy() {
        return new StandardFeePolicy();
    }

    @Bean
    @Primary
    FeePolicy promotionalFeePolicy() {
        return new PromotionalFeePolicy();
    }
}
~~~

Snippet chỉ minh họa ngữ nghĩa; cần định nghĩa các class tương ứng để biên dịch. Hai bean được đăng ký dưới **hai tên khác nhau**. Nếu code nhận `FeePolicy` thuần:

~~~java
class CheckoutService {
    CheckoutService(FeePolicy policy) {
        // Spring sẽ ưu tiên bean @Primary khi có nhiều candidate.
    }
}
~~~

thì bean `promotionalFeePolicy` được ưu tiên khi giải quyết constructor này. Mặc dù vậy:

- `applicationContext.containsBean("standardFeePolicy")` vẫn có thể trả true.
- `applicationContext.getBean("standardFeePolicy")` vẫn trỏ đến bean cũ; `@Primary` **không đổi nghĩa tra cứu bằng tên**.
- Injection `List<FeePolicy>`, `Map<String, FeePolicy>` hoặc array có thể nhận **cả hai bean**; `@Primary` không lọc collection xuống chỉ còn bean ưu tiên.
- Nếu chỉ có **một** bean phù hợp thì Spring không cần `@Primary`.
- Nếu có **hai candidate cùng được đánh dấu primary** cho một injection type không có cách phân biệt khác, có thể vẫn xảy ra lỗi mơ hồ; `@Primary` không phải cơ chế phân hạng 1, 2, 3.
- Các điều kiện như `@Qualifier`, scope, autowire-candidate metadata và những cơ chế chọn bean khác vẫn tham gia quyết định cuối. `@Primary` không đảm bảo thắng mọi trường hợp.

### Khi nào `@Primary` hợp lý trong test?

Một ứng dụng production có bean `Clock.systemUTC()`, còn test cần `Clock.fixed(...)`. Nếu cần giữ cả hai định nghĩa để kiểm bean production vẫn tồn tại, ta có thể import bean `fixedTestClock` với `@Primary` và inject `Clock` không qualifier vào SUT. SUT nhận đồng hồ test, nhưng production clock vẫn có thể lấy được theo tên.

Tương tự, một service đọc `FeePolicy` qua constructor có thể nhận policy test ở một test context cụ thể. Điều này dễ đọc hơn việc bật override theo tên cho toàn context chỉ để đổi một dependency.

**Cẩn thận:** Nếu một production constructor đã gắn `@Qualifier("standardFeePolicy")`, thêm `@Primary` lên bean `promoFeePolicy` sẽ **không** làm constructor đó bỏ qualifier. Test phải kiểm đúng điểm tiêm thực sự, thay vì giả định bất cứ `@Primary` nào cũng thay được dependency.

## 3. `@Qualifier`: yêu cầu rõ candidate tại nơi inject

`@Qualifier` thuộc `org.springframework.beans.factory.annotation.Qualifier` và được dùng trên field, constructor parameter, method parameter hoặc những điểm injection phù hợp.

~~~java
@Service
class AuditService {

    private final FeePolicy policy;

    AuditService(@Qualifier("standardFeePolicy") FeePolicy policy) {
        this.policy = policy;
    }
}
~~~

Đây là snippet cú pháp; `FeePolicy` và service mẫu được định nghĩa đầy đủ trong chương trình ở mục 4. Annotation **không tạo bean mới** và không thay đổi định nghĩa bean có sẵn. Nó hướng Spring chọn một candidate thỏa điều kiện của qualifier.

Trong trường hợp thông dụng `@Qualifier("standardFeePolicy")`, giá trị qualifier khớp bean name. Về bản chất, qualifier là **cơ chế lọc candidate**; nó cũng có thể được định nghĩa bằng metadata/annotation chuyên biệt, không chỉ là phép “tìm tên bean” trong mọi trường hợp. Nếu nhiều candidate vẫn thỏa cùng một qualifier, quy tắc chọn tiếp theo như primary và cấu hình liên quan vẫn có thể quan trọng.

### So sánh ba điểm injection

Giả sử context có bean `standardFeePolicy` và bean `promoFeePolicy` được đánh dấu `@Primary`:

| Injection point | Bean được mong đợi | Vì sao |
| --- | --- | --- |
| `CheckoutService(FeePolicy policy)` | `promoFeePolicy` | `@Primary` ưu tiên candidate cho type |
| `AuditService(@Qualifier("standardFeePolicy") FeePolicy policy)` | `standardFeePolicy` | Injection point đã chỉ rõ qualifier |
| `@Autowired Map<String, FeePolicy> policies` | Cả hai bean | Collection injection thu thập các candidate phù hợp |

Trong test, luôn kiểm **kết quả thực tế**: với giá trị 100, policy production trả 30, policy test trả 10. Khi cùng một application context có cả hai, hai service nhận policy khác nhau thì hành vi phải khác nhau đúng như đặc tả.

### Vì sao không gắn qualifier vào mọi constructor?

Nếu mọi service bị ràng buộc vào tên bean cụ thể, khả năng đổi implementation khi thử nghiệm hoặc cấu hình theo môi trường sẽ giảm. Với một interface chỉ cần **một implementation được chọn theo môi trường**, constructor injection thuần type thường linh hoạt. Với trường hợp **có chủ đích cần đúng một provider** (ví dụ kênh thanh toán nội địa, nguồn dữ liệu primary/replica, tenant hoặc policy dùng để kiểm toán), qualifier làm hợp đồng rõ hơn. Quyết định phải dựa trên thiết kế, không nên áp dụng máy móc.

## 4. Ví dụ Java 17 + Spring Boot chạy được: hai bean khác tên, một bean `@Primary`

### 4.1. Mục tiêu ví dụ

Chúng ta kiểm một Spring Boot application có:

- `FeePolicy` — interface tính phí vận chuyển.
- `standardFeePolicy` — bean production: đơn hàng từ **500 trở lên miễn phí**, còn lại phí **30**.
- `CheckoutService` — service inject `FeePolicy` **không qualifier**.
- `AuditFeeService` — service inject `@Qualifier("standardFeePolicy")` để luôn sử dụng chính sách chuẩn.
- `promoFeePolicy` — bean **chỉ dùng trong test**, khi đơn nhỏ hơn 500 phí **10**; được đăng ký qua `@TestConfiguration` và `@Import`, gắn `@Primary`.

Hai test class giúp đối chiếu:

1. **Không import test bean:** `CheckoutService` dùng `standardFeePolicy` (phí 30).
2. **Import test bean:** `CheckoutService` dùng `promoFeePolicy` (phí 10), nhưng `AuditFeeService` vẫn dùng `standardFeePolicy` (phí 30). Context còn cả hai bean.

Ví dụ cố tình **không** dùng bean definition overriding. Nó chứng minh cách chọn candidate trong test một cách rõ ràng và an toàn hơn.

### 4.2. Cấu trúc thư mục

~~~text
bean-selection-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   ├── DemoApplication.java
    │   ├── FeePolicy.java
    │   ├── CheckoutService.java
    │   └── AuditFeeService.java
    └── test/java/com/example/testing/
        ├── PromoFeeTestConfig.java
        ├── ProductionWiringTest.java
        └── ImportedPrimaryWiringTest.java
~~~

Các script/tệp Gradle Wrapper cần được tạo bởi Gradle hoặc có sẵn trong repository; không viết tay nội dung nhị phân `gradle-wrapper.jar`. Chúng được minh họa trong cấu trúc để chỉ rõ lệnh chạy qua Wrapper ở mục 4.7.

**`settings.gradle`**

~~~groovy
rootProject.name = 'bean-selection-demo'
~~~

**`build.gradle`** — phiên bản minh họa Spring Boot 3.3.5, Java 17; dự án thật nên dùng BOM/Gradle version mà repository quy định:

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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` hỗ trợ Boot context và DI; không cần web server vì project này không có HTTP API. `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring TestContext và các dependency phục vụ test. `useJUnitPlatform()` giúp Gradle chạy Jupiter test. `testRuntimeOnly` thêm launcher theo convention hiện đại. Java toolchain cần một JDK 17 được tìm thấy hoặc provisioning được cấu hình.

**`src/main/java/com/example/testing/FeePolicy.java`**

~~~java
package com.example.testing;

@FunctionalInterface
public interface FeePolicy {
    int feeFor(int orderAmount);
}
~~~

**`src/main/java/com/example/testing/DemoApplication.java`**

~~~java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    public FeePolicy standardFeePolicy() {
        return orderAmount -> {
            if (orderAmount < 0) {
                throw new IllegalArgumentException(
                        "orderAmount must not be negative");
            }
            return orderAmount >= 500 ? 0 : 30;
        };
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Bean production tên `standardFeePolicy`. Với `orderAmount=100`, phí là 30; với `500`, phí là 0; với số âm, ném `IllegalArgumentException`.

**`src/main/java/com/example/testing/CheckoutService.java`**

~~~java
package com.example.testing;

import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public final class CheckoutService {

    private final FeePolicy feePolicy;

    public CheckoutService(FeePolicy feePolicy) {
        this.feePolicy = Objects.requireNonNull(feePolicy);
    }

    public int shippingFee(int orderAmount) {
        return feePolicy.feeFor(orderAmount);
    }
}
~~~

Constructor chỉ có **type `FeePolicy`**, không qualifier. Khi context có hai policy, Spring sẽ cần một quy tắc chọn candidate, ở đây là `@Primary` từ test config.

**`src/main/java/com/example/testing/AuditFeeService.java`**

~~~java
package com.example.testing;

import java.util.Objects;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public final class AuditFeeService {

    private final FeePolicy standardPolicy;

    public AuditFeeService(
            @Qualifier("standardFeePolicy") FeePolicy standardPolicy) {
        this.standardPolicy = Objects.requireNonNull(standardPolicy);
    }

    public int referenceFee(int orderAmount) {
        return standardPolicy.feeFor(orderAmount);
    }
}
~~~

`AuditFeeService` có chủ đích dùng **policy chuẩn** như tham chiếu kiểm toán, nên dependency này được gắn qualifier. `@Primary` trên policy test sẽ không làm nó tự ý đổi sang policy khuyến mại.

### 4.3. Test-only config: `@TestConfiguration` và `@Import`

**`src/test/java/com/example/testing/PromoFeeTestConfig.java`**

~~~java
package com.example.testing;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class PromoFeeTestConfig {

    @Bean
    @Primary
    public FeePolicy promoFeePolicy() {
        return orderAmount -> {
            if (orderAmount < 0) {
                throw new IllegalArgumentException(
                        "orderAmount must not be negative");
            }
            return orderAmount >= 500 ? 0 : 10;
        };
    }
}
~~~

`@TestConfiguration` là annotation của Spring Boot cho config dùng trong test. Khi được đặt ở **top-level class** trong `src/test/java`, nó không tự được component scan mặc định của Boot đưa vào production app context; ở test cần nó, ta **import tường minh**. `@Bean` tạo bean mới tên `promoFeePolicy`, còn `@Primary` đánh dấu ưu tiên cho injection theo type.

**Điểm then chốt:** `promoFeePolicy` **khác tên** `standardFeePolicy`, nên không gây bean-definition name collision. Cả hai cùng implement interface `FeePolicy`, và annotation `@Primary` giải quyết việc chọn bean cho `CheckoutService`.

Trong một dự án có component scanning tùy biến, các quy tắc scan có thể khác; hãy giữ test-only config trong test source set và import có chủ đích. Không chuyển class này sang `src/main/java` chỉ để sửa một lỗi test setup.

### 4.4. Test 1 — ngữ cảnh production, không import policy test

**`src/test/java/com/example/testing/ProductionWiringTest.java`**

~~~java
package com.example.testing;

import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ProductionWiringTest {

    @Autowired
    private CheckoutService checkout;

    @Autowired
    private AuditFeeService audit;

    @Autowired
    private Map<String, FeePolicy> policies;

    @Test
    void productionServicesUseStandardPolicy() {
        assertEquals(30, checkout.shippingFee(100));
        assertEquals(30, audit.referenceFee(100));
        assertEquals(0, checkout.shippingFee(500));
    }

    @Test
    void testPolicyIsNotPresentWithoutImport() {
        assertEquals(
                Set.of("standardFeePolicy"),
                policies.keySet());
    }
}
~~~

Không có `@Import(PromoFeeTestConfig.class)`. Context nhận bean production `standardFeePolicy`, vì vậy Spring có đúng một candidate cho `CheckoutService`. Hai method `@Test` tạo **2 invocation** trong class này.

### 4.5. Test 2 — import policy test có `@Primary`

**`src/test/java/com/example/testing/ImportedPrimaryWiringTest.java`**

~~~java
package com.example.testing;

import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(PromoFeeTestConfig.class)
class ImportedPrimaryWiringTest {

    @Autowired
    private CheckoutService checkout;

    @Autowired
    private AuditFeeService audit;

    @Autowired
    private FeePolicy chosenByType;

    @Autowired
    @Qualifier("standardFeePolicy")
    private FeePolicy explicitlyStandard;

    @Autowired
    private Map<String, FeePolicy> policies;

    @Test
    void unqualifiedConsumerUsesTestPrimary() {
        assertEquals(10, checkout.shippingFee(100));
        assertEquals(0, checkout.shippingFee(500));
    }

    @Test
    void qualifiedConsumerKeepsProductionPolicy() {
        assertEquals(30, audit.referenceFee(100));
        assertEquals(0, audit.referenceFee(500));
    }

    @Test
    void bothNamedDefinitionsRemainRegistered() {
        assertEquals(
                Set.of("standardFeePolicy", "promoFeePolicy"),
                policies.keySet());

        assertEquals(
                30,
                policies.get("standardFeePolicy").feeFor(100));
        assertEquals(
                10,
                policies.get("promoFeePolicy").feeFor(100));
    }

    @Test
    void primaryAndQualifierSelectDifferentInstances() {
        assertSame(policies.get("promoFeePolicy"), chosenByType);
        assertSame(policies.get("standardFeePolicy"),
                explicitlyStandard);
    }

    @Test
    void bothPoliciesRejectNegativeAmounts() {
        assertThrows(IllegalArgumentException.class,
                () -> checkout.shippingFee(-1));

        assertThrows(IllegalArgumentException.class,
                () -> audit.referenceFee(-1));
    }
}
~~~

Đây là test Spring Boot thực sự chạy bean wiring và hai implementation `FeePolicy`. Không có database, network hoặc mock để che logic. Các expected `30`, `10`, `0` xuất phát từ quy tắc đã mô tả, không gọi lại cùng implementation để tạo expected.

**Những điều bài test chứng minh:**

- `CheckoutService` **không có qualifier**, vì vậy nhận policy test được đánh dấu `@Primary`.
- `AuditFeeService` có qualifier `standardFeePolicy`, nên tiếp tục nhận policy production.
- `Map<String, FeePolicy>` có **hai entry**, chứng minh `@Primary` không xóa bean còn lại.
- `chosenByType` trỏ cùng instance với `promoFeePolicy`, `explicitlyStandard` trỏ cùng instance với `standardFeePolicy` (scope singleton của `@Bean` mặc định).
- Cả hai policy từ chối dữ liệu âm, nên test không chỉ “chọn đúng tên” mà còn xác minh hành vi ở boundary.

Class này có **5 invocation**. Cộng với 2 invocation của `ProductionWiringTest`, toàn bộ project ví dụ có **7 lượt JUnit test** khi chạy cả hai class.

### 4.6. Vì sao hai test class không can thiệp nhau?

Spring TestContext có cơ chế **cache ApplicationContext** dựa trên cấu hình merged context. Class `ImportedPrimaryWiringTest` có `@Import(PromoFeeTestConfig.class)`, còn `ProductionWiringTest` không import config ấy. Do đó hai test này có **tập cấu hình khác nhau** và không nên được thiết kế dựa trên việc dùng cùng một context instance.

Bean config test là top-level `@TestConfiguration` chỉ được import khi cần. Không dùng state mutable chia sẻ, không cần `@DirtiesContext`, không phụ thuộc thứ tự test. Nếu test config hoặc singleton fake có trạng thái thay đổi, hãy tự reset fixture hoặc thiết kế test độc lập; cache Spring context không tự cách ly mọi state.

### 4.7. Chạy bằng Gradle Wrapper

Tại thư mục root có `settings.gradle` và Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chỉ chạy class import:

~~~bash
./gradlew test --tests 'com.example.testing.ImportedPrimaryWiringTest'
~~~

Chỉ chạy class production:

~~~bash
./gradlew test --tests 'com.example.testing.ProductionWiringTest'
~~~

Với mã ví dụ đúng như trên, kỳ vọng **7 test pass**. Không có `System.out.println`, nên **không có stdout nghiệp vụ cố định**. Gradle có thể in `BUILD SUCCESSFUL` khi task thành công, hoặc dùng lại kết quả với `UP-TO-DATE`/`FROM-CACHE` khi điều kiện phù hợp. Xem số test thực sự trong báo cáo:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.testing.ProductionWiringTest.xml
    └── TEST-com.example.testing.ImportedPrimaryWiringTest.xml
~~~

Khi cần buộc chạy lại để chẩn đoán, dùng `./gradlew test --rerun-tasks`. Nếu tạo project mới chưa có Wrapper, có thể bootstrap từ một Gradle đã cài tương thích, ví dụ `gradle wrapper --gradle-version 8.8 --distribution-type bin` cho demo này. Trong repository thực, dùng bản Gradle mà project đã chọn. Wrapper không tự cài JDK; cần Java 17 được cấu hình phù hợp.

## 5. Khi nào lỗi `NoUniqueBeanDefinitionException` xuất hiện?

Giả sử có hai bean cùng interface:

~~~java
@Bean
FeePolicy standardFeePolicy() { /* ... */ }

@Bean
FeePolicy promoFeePolicy() { /* ... */ }
~~~

Nếu không có primary, không có qualifier và không có quy tắc phân giải khác, constructor `CheckoutService(FeePolicy feePolicy)` có thể dẫn tới lỗi dạng:

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
standardFeePolicy,promoFeePolicy
~~~

Đây là **minh họa kiểu thông báo lỗi**, không đảm bảo nguyên văn stack trace ở mọi phiên bản Spring. Vấn đề: **hai candidate theo type**. Cách xử lý tùy hợp đồng:

1. Đánh dấu một implementation `@Primary` nếu nó nên là mặc định khi nhiều bean cùng type.
2. Thêm `@Qualifier` ở injection point nếu consumer phải nhận một implementation cụ thể.
3. Không đăng ký hai bean trong cùng context nếu chỉ cần một — ví dụ tách theo `@Profile`, điều kiện cấu hình hoặc tổ chức lại imports.
4. Nếu consumer thực sự cần tất cả implementation, đổi thiết kế injection thành `List<FeePolicy>`/`Map<String, FeePolicy>` và xác định rõ cách sử dụng.

**Không giải quyết bằng `spring.main.allow-bean-definition-overriding=true`** khi bean có **hai tên khác nhau**. Property overriding điều khiển xung đột định nghĩa **cùng bean name**, chứ không loại bớt candidate cùng type.

### Điểm tinh tế: tên parameter và tên bean

Trong một số tình huống, Spring có cơ chế phân giải dựa trên tên injection point khi có đủ metadata, qualifier hoặc fallback matching. Điều đó có thể làm một test tưởng như “không qualifier” lại chọn được một bean cụ thể. Để test rõ ràng và ổn định, **đừng dựa vào trùng hợp tên parameter/field** làm chính sách lựa chọn giữa nhiều implementation. Dùng `@Primary` hoặc `@Qualifier` khi có nhiều candidate có chủ đích và kiểm behavior thực sự.

## 6. Lỗi trùng bean name và bean definition overriding

Giờ xét **hai cấu hình đăng ký cùng tên**:

~~~java
// Config sản phẩm - snippet minh họa:
@Configuration
class ProductionGatewayConfig {

    @Bean("paymentGateway")
    PaymentGateway realGateway() {
        return new RemotePaymentGateway();
    }
}

// Config test - snippet minh họa:
@TestConfiguration
class TestGatewayConfig {

    @Bean("paymentGateway")
    PaymentGateway fakeGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Đây là snippets để phân tích lỗi; `PaymentGateway`, `RemotePaymentGateway` và `FakePaymentGateway` chưa định nghĩa thành project runnable ở ví dụ mục 4. Nếu hai cấu hình cùng được đăng ký vào một context Boot mà **cùng tạo bean name `paymentGateway`**, đó là xung đột **bean definition name**, không phải hai bean khác tên cùng type.

Spring Boot theo mặc định thông thường **không cho phép bean-definition overriding bằng tên**. Trong trường hợp trùng tên này, quá trình đăng ký có thể fail với `BeanDefinitionOverrideException` hoặc một lỗi khởi tạo context liên quan; thông báo cụ thể phụ thuộc thời điểm/loại đăng ký và phiên bản thư viện.

### `spring.main.allow-bean-definition-overriding=true` làm gì?

Trong Spring Boot, property:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

cho phép bean factory **chấp nhận việc một bean definition cùng tên thay thế một definition khác** ở những đường đăng ký phù hợp. Nó là một **cấu hình container**, không phải annotation làm test bean thành primary.

Nếu bật lên, test có thể hết lỗi xung đột tên. Tuy nhiên:

- **Không đảm bảo bean test sẽ thắng** chỉ vì nó nằm ở `src/test/java`; definition nào được giữ còn phụ thuộc trình tự xử lý/đăng ký cấu hình. Một cấu hình test có thể bị ghi đè ngược nếu giả định thứ tự sai.
- **Không giúp phân giải hai bean khác tên cùng type.** Lỗi `NoUniqueBeanDefinitionException` vẫn có thể xảy ra.
- **Không tự thay mọi tham chiếu tới implementation production.** Một số dependency có qualifier, binding theo tên, factory method, conditional config hoặc lifecycle riêng.
- **Không chứng minh application production khởi động đúng.** Test có thể vô tình che lỗi bean trùng tên đáng lẽ cần sửa ở production.
- **Không bảo đảm context khởi tạo được:** vẫn có thể thiếu bean, circular dependency, lỗi property, lỗi constructor hoặc điều kiện cấu hình khác.
- **Có thể làm test phụ thuộc thứ tự và cấu trúc scan/import**, khiến refactor/config import mới thay đổi definition cuối cùng được đăng ký.

Vì vậy **không bật overriding trên toàn ứng dụng hoặc toàn bộ test suite chỉ để “cho Spring chạy qua”**. Đây là lựa chọn có chủ đích trong một số hệ thống legacy, chứ không phải mặc định cho việc thay dependency test.

### Khi nào *có thể* cân nhắc overriding theo tên?

Khi kiến trúc/compatibility thực sự yêu cầu một bean name cố định và không thể thay thế qua profile, conditional config, qualifier, fake injection hoặc cơ chế test bean override chuyên dụng, nhóm có thể cân nhắc bật overriding **chỉ trong phạm vi test liên quan**, với:

- Test khẳng định **bean definition/behavior thực sự được chọn** sau khi context load, không chỉ kiểm rằng context khởi động.
- Cấu hình nguồn bean và thứ tự import được hiểu rõ và review được.
- Test khác bảo đảm **production context vẫn khởi động không bị che lỗi**.
- Tài liệu giải thích lý do không dùng một cơ chế rõ hơn và phạm vi áp dụng tối thiểu.

Nếu không có những điều kiện đó, ưu tiên **thêm bean khác tên + `@Primary`**, **`@Qualifier`**, profile/conditional config hoặc hỗ trợ test replacement có chủ đích.

## 7. Điều gì thực sự được “thay thế”?

Hãy đặt câu hỏi: “Mục tiêu của tôi là thay **sự lựa chọn dependency**, hay thay **định nghĩa bean có tên cụ thể**?”

| Mong muốn | Kỹ thuật thường phù hợp | Có giữ bean production cùng context không? |
| --- | --- | --- |
| Consumer theo type nhận policy test thay policy production | `@Import` test bean khác tên + `@Primary` | Có |
| Chỉ một consumer cụ thể nhận policy cố định | `@Qualifier` tại injection point | Có |
| Chỉ test profile dùng adapter fake | `@ActiveProfiles("test")` + `@Profile` tương ứng | Tùy cách khai báo/profile |
| Chỉ muốn thay giá trị property hiện có | `@TestPropertySource` hoặc Boot test properties | Thường có; không cần thêm bean |
| Mock một dependency theo type/name trong Boot test | Test mock annotation được **phiên bản dự án hỗ trợ** | Định nghĩa test replacement theo cơ chế mock |
| Thay một bean definition cùng tên | Bean override chuyên dụng; nếu buộc phải, container overriding có kiểm soát | Không nhất thiết, vì định nghĩa cùng tên có thể bị thay |
| Kiểm thuật toán đơn lẻ mà không cần Spring DI | `new` object với fake/Clock.fixed | Không mở context |

**Nhận xét:** Một test có thể nói “thay thế dependency” mà vẫn giữ bean production. Trong bài chạy được, `CheckoutService` nhận `promoFeePolicy` nhưng `standardFeePolicy` còn nguyên và `AuditFeeService` vẫn dùng nó. Đó là **thay lựa chọn candidate** ở một injection point, không phải overwrite registry.

## 8. `@Profile` và `@ConditionalOnMissingBean` có thể phù hợp hơn

### 8.1. Dùng `@Profile` cho những implementation theo môi trường

Nếu ứng dụng có các implementation phải **loại trừ nhau theo môi trường**, cấu hình theo profile thường rõ ý hơn dùng overriding:

~~~java
@Configuration
class GatewayConfiguration {

    @Bean
    @Profile("!test")
    PaymentGateway liveGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Profile("test")
    PaymentGateway fakeGateway() {
        return new InMemoryPaymentGateway();
    }
}
~~~

Đây là snippet minh họa; các type/implementation cần tồn tại trong dự án thực. Với `@ActiveProfiles("test")`, test context không đăng ký `liveGateway` từ config này, nên không cần `@Primary` hay ghi đè theo tên. Với production profile không phải `test`, bean live sẽ được tạo.

Tuy nhiên, **đừng đưa fake test implementation vào artifact production một cách tùy tiện**. Trong codebase lớn, có thể giữ fake dưới `src/test/java` và import test-only config thay vì đặt fake trong main. Profile không thay thế việc thiết kế ranh giới và đảm bảo production wiring được test riêng.

### 8.2. Dùng conditional config cho bean mặc định có thể được cung cấp bởi ứng dụng

Trong Spring Boot, một bean fallback có thể được khai báo với `@ConditionalOnMissingBean` để chỉ tạo khi context chưa có candidate phù hợp:

~~~java
@Configuration(proxyBeanMethods = false)
class DefaultGatewayAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultGateway() {
        return new RemotePaymentGateway();
    }
}
~~~

Snippet minh họa loại cấu hình “default nếu chưa có implementation”. Khi consumer/test đã đăng ký một bean `PaymentGateway` đúng thời điểm điều kiện được đánh giá, fallback có thể **không được đăng ký**, nhờ vậy tránh tạo hai candidate. Cơ chế này đặc biệt thường gặp trong auto-configuration.

**Giới hạn quan trọng:** `@ConditionalOnMissingBean` không phải lệnh “xóa bean đã tạo” và **phụ thuộc thời điểm xử lý bean definitions/điều kiện**. Nó được thiết kế phù hợp cho auto-configuration và cần được áp dụng khi biết rõ thứ tự cấu hình; không tự động sửa mọi xung đột bean name/type. Đừng dán annotation này vào bất kỳ bean nào đang trùng để mong có phép override thần kỳ.

### 8.3. Với `@Qualifier` cố định, thêm `@Primary` có thể không đủ

Nếu constructor production đã viết:

~~~java
public PaymentService(
        @Qualifier("realGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

thì import `@Primary` fake với tên `fakeGateway` **không tự thay đổi lựa chọn** của constructor. Nếu mục tiêu test phải cắm fake vào consumer này, nên cân nhắc:

- Tái thiết kế consumer để injection theo interface không cần tên implementation khi hợp đồng cho phép.
- Chọn profile/conditional config sao cho candidate đúng được đăng ký dưới tên/qualifier mà consumer yêu cầu.
- Sử dụng test mock/bean replacement mechanism hỗ trợ target bằng name/qualifier theo phiên bản thư viện.
- Tạo unit test trực tiếp với constructor `new PaymentService(fakeGateway)` nếu không cần kiểm container wiring.

Không dùng property overriding theo tên như “phép sửa nhanh” mà không kiểm toàn bộ kết quả bean resolution.

## 9. Spring Boot 3.3, 3.4+ và cơ chế test mock/replacement

Khi cần **một dependency mock thực sự** thay vì thêm một implementation thật, annotation cụ thể phụ thuộc phiên bản Spring Boot/Spring Framework:

- Với **Spring Boot 3.3.x** như ví dụ runnable, `@MockBean` của Spring Boot Test là một cơ chế test mock được hỗ trợ trong phiên bản này. Nó có thể thêm/thay bean trong test `ApplicationContext` theo quy tắc của annotation, chứ không giống việc đơn giản đưa `@Primary` lên một bean khác.
- Trong hệ Spring Framework **6.2+**, Spring Test cung cấp hỗ trợ bean override trong test, gồm `@MockitoBean` và `@TestBean` trong những ngữ cảnh được hỗ trợ; Spring Boot các phiên bản mới tích hợp các cơ chế thích hợp. Spring Boot 3.4 bắt đầu hướng chuyển khỏi `@MockBean` của Boot sang cơ chế mới, nhưng **không copy `@MockitoBean` vào Boot 3.3.x** vì bộ Spring Framework 6.1.x của phiên bản ví dụ không có API đó.
- Cơ chế bean override chuyên dụng có quy tắc riêng về target theo type/name, chỉ cho phép thay hay có thể tạo khi thiếu, factory method và context hierarchy. Phải đọc hướng dẫn **đúng phiên bản dependency đang dùng** để chọn annotation và cú pháp hợp lệ.

Nội dung bài không dùng `@MockBean`/`@MockitoBean` trong chương trình chính vì mục đích là chứng minh **khác biệt giữa candidate selection, qualifier và bean-definition override**. Khi không cần chạy logic thật của external gateway, mock annotation có thể phù hợp hơn một `@Primary` fake; khi muốn kiểm chính logic thật của policy, đừng mock chính policy đang được kiểm.

### Tránh bật overriding chỉ để thay một `@MockBean`

Mock test annotation có vòng đời, target selection và integration với Spring TestContext riêng. Bật `spring.main.allow-bean-definition-overriding=true` là một công tắc khá rộng ở bean registry, **không thể xem là tương đương** với việc áp dụng một annotation override có mục tiêu. Cần quyết định dựa vào điều gì sẽ được test và loại bean nào được phép thay.

## 10. Chẩn đoán lỗi theo hai trục: tên và kiểu

Khi context fail, đầu tiên phân biệt **tên bean trùng** hay **type có nhiều candidate**:

| Triệu chứng | Vấn đề thật | Hướng xử lý |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` khi inject `FeePolicy` | Có nhiều candidate theo type, chưa chọn được một | `@Primary`, `@Qualifier`, profile, cấu hình điều kiện hoặc thu hẹp imports |
| `BeanDefinitionOverrideException` khi đăng ký `paymentGateway` | Có nhiều definition **cùng name** trong registry, overriding bị chặn | Đổi bean name, tránh import trùng, dùng test replacement đúng mục tiêu |
| `NoSuchBeanDefinitionException` | Không có candidate phù hợp hoặc qualifier không khớp | Kiểm bean registration, annotation, profile, import và target qualifier |
| Context tải nhưng injection dùng policy production | Test bean không được import/primary không có hiệu lực/consumer gắn qualifier | Assert candidate theo tên và đầu ra như ví dụ |
| Context tải nhưng có cả policy thật lẫn fake | Dùng `@Primary` chỉ đổi lựa chọn, không xóa bean | Đây có thể là chủ đích; nếu không, tách bằng profile/conditional/override chính xác |
| `@Primary` vẫn có lỗi mơ hồ | Có nhiều primary hoặc qualifier/kiểu không phù hợp | Kiểm số lượng primary trong đúng tập candidate và injection point |
| Bật overriding nhưng lỗi type vẫn còn | Bean có tên khác nhau, không trùng định nghĩa tên | Tắt công tắc rộng, sửa candidate selection |
| Bean test vô tình xuất hiện ở test khác | Config top-level bị quét rộng hoặc được import chung | Giới hạn `@TestConfiguration` và scope import |
| Test pass, production fail khi khởi động | Fake/test config đang che lỗi wiring production | Có test production context riêng, như `ProductionWiringTest` |
| Test run đơn lẻ pass, chạy cả suite fail | State singleton, context cache hoặc fixture bị chia sẻ | Reset state, tránh phụ thuộc thứ tự; dùng context cache có chủ đích |
| Test dùng tên bean nhưng refactor đổi method `@Bean` | Bean name mặc định cũng đổi | Khai báo tên explicit khi tên là contract, hoặc bỏ qualifier cứng nếu không cần |
| Lỗi JUnit test không được chạy | Sai runner/Gradle/test source set, không liên quan bean | Kiểm `useJUnitPlatform()`, JUnit Jupiter import, test task và report |

### Cách đọc nguyên nhân sâu trong stack trace

`Failed to load ApplicationContext` chỉ là **biểu hiện tầng ngoài**. Cần xem exception bên trong:

- `NoUniqueBeanDefinitionException` → Spring không chọn được **một candidate**.
- `BeanDefinitionOverrideException` → container không cho **trùng tên definition**.
- `NoSuchBeanDefinitionException` → không có candidate phù hợp với type/qualifier.
- Exception ở constructor factory bean → lỗi code/cấu hình tạo instance, không nhất thiết liên quan overriding.
- Lỗi property, external service, database → có thể test context đang import quá rộng hoặc thiếu môi trường.

Với Gradle, chạy `./gradlew test --stacktrace` hoặc `--info` để đọc thêm chi tiết nếu cần. Đừng sửa bằng cách bật cả debug logs lẫn overriding một cách không có mục tiêu, vì nó có thể che lỗi gốc.

## 11. Context caching và độ tin cậy của test

Spring TestContext cache các `ApplicationContext` khi tập cấu hình tương đương, gồm các thành phần như imports/test customizers, profiles và property sources. Việc mỗi test class import một nhóm bean khác có thể tạo **cache key khác**, khiến nhiều context được tải. Đây là sự đánh đổi giữa test isolation và tốc độ.

Ví dụ có hai class trong bài:
- `ProductionWiringTest` khởi tạo context từ `DemoApplication` không import policy test.
- `ImportedPrimaryWiringTest` import `PromoFeeTestConfig` để có thêm primary policy.

Bộ test **không được dựa vào thứ tự hai class**. Với bean không giữ mutable state như hai lambda policy, việc cache không làm thay đổi kết quả. Khi dùng fake repository có danh sách mutable, cần xóa dữ liệu giữa các test hoặc tạo fixture độc lập; không mặc định context cache sẽ reset singleton.

Với test có hàng chục cấu hình import nhỏ khác nhau, thời gian khởi tạo có thể tăng; đôi khi một tập test chia sẻ config rõ ràng giúp giảm churn context, nhưng không nên gom tất cả fake/config của hệ thống vào một `MegaTestConfig` chỉ để cache được một context. Điều đó làm mất khả năng hiểu ranh giới và tăng nguy cơ bean trùng.

### `@DirtiesContext` có giải quyết bean overriding không?

Không. `@DirtiesContext` yêu cầu Spring TestContext xem context đã bị làm bẩn và loại khỏi cache để có thể tải lại. Nó **không biến hai bean cùng type thành một**, cũng không tự cho phép trùng definition name. Nếu lỗi xảy ra **khi tạo context**, làm dirty context sẽ không chữa nguyên nhân đăng ký/chọn bean. Dùng annotation này cho thay đổi state/config khiến context không thể được tái sử dụng an toàn, không dùng như lệnh reset chung.

## 12. Sai lầm thiết kế và các phương án thay thế

### Lỗi A: muốn test service nhưng mock chính service

Nếu test cần kiểm `CheckoutService.shippingFee(...)` mà lại mock `CheckoutService` trả 10, bài test chỉ chứng minh mock trả đúng stubbing. Hãy chạy service thật với `FeePolicy` thật hoặc fake phù hợp, và assert expected từ yêu cầu. Trong ví dụ, cả `CheckoutService` và hai policy đều chạy code thật.

### Lỗi B: bật overriding toàn repo vì một bean trùng

Điều này thay hành vi bean registry ở nhiều test, có thể che những xung đột tên đáng lẽ phải phát hiện. Hãy tìm **hai class định nghĩa bean có cùng tên**, rồi đổi tên/scope/profile hoặc dùng test bean override có mục tiêu. Nếu test cần cả bean thật và fake, **đặt hai tên khác nhau** và dùng `@Primary`/`@Qualifier` thay vì cố loại bean cũ.

### Lỗi C: `@Primary` được thêm nhưng consumer có `@Qualifier`

`@Primary` không làm biến mất qualifier cứng trong code. Hãy xác định **consumer cần chọn theo cấu hình hay luôn bắt buộc một provider**. Nếu chọn theo cấu hình, refactor injection thành interface không qualifier có thể đúng hơn. Nếu bắt buộc provider, test phải bảo toàn hành vi này hoặc dùng replacement có mục tiêu.

### Lỗi D: dùng `@Qualifier` để “đăng ký” bean

`@Qualifier("promoFeePolicy")` ở field test hoặc constructor không tạo `promoFeePolicy`. Nếu không có bean definition phù hợp, Spring vẫn báo thiếu bean. Đầu tiên cần `@Bean`, `@Component`, `@Import` hoặc một cơ chế registration/override thật; sau đó qualifier mới giúp chọn đúng candidate.

### Lỗi E: coi mọi bean có cùng type là xung đột

Nhiều bean cùng interface là thiết kế bình thường: nhiều chiến lược thanh toán, nhiều handler, nhiều kênh gửi thông báo. Xung đột chỉ xảy ra khi một injection point cần **duy nhất một bean** mà chưa có quy tắc chọn phù hợp. Nếu consumer thực sự muốn chạy **mọi** strategy, `List<T>`/`Map<String,T>` có thể là đúng hợp đồng hơn một primary.

### Lỗi F: test wiring không kiểm hành vi

Test chỉ viết `assertNotNull(context.getBean(CheckoutService.class))` có thể pass dù inject nhầm policy, vì bean nào cũng khởi tạo được. Bài mẫu kiểm các giá trị **10**, **30**, **0** và instance selection, chứng minh policy được chọn ảnh hưởng trực tiếp tới kết quả.

### Lỗi G: test config bị lộ sang production

Đặt `@TestConfiguration` hoặc fake gateway ở `src/main/java` chỉ để test compile làm tăng nguy cơ cấu hình test xuất hiện khi build/deploy. Giữ test-only class dưới `src/test/java` và import tường minh. Nếu cần chia sẻ fixtures giữa nhiều Gradle modules, dùng test fixtures hoặc module kiểm thử riêng, không nhét fake vào business runtime artifact.

## 13. Quy trình quyết định khi muốn thay bean trong test

Hãy đi theo thứ tự, bắt đầu từ mục tiêu kiểm thử:

1. **Có cần Spring context không?** Nếu chỉ kiểm một class thuần Java, tiêm collaborator bằng constructor trực tiếp sẽ đơn giản, nhanh và ít rủi ro.
2. **Mục tiêu là đổi dữ liệu cấu hình hay đổi implementation?** Nếu chỉ đổi rate/URL/flag, cân nhắc test properties hoặc profile; không tạo bean chỉ để thay giá trị.
3. **Có thể giữ bean production không?** Nếu có, tạo bean test **khác tên**, import cục bộ và dùng `@Primary` cho injection theo type.
4. **Consumer có qualifier cố định không?** Nếu có, xem đây là hợp đồng hay chi tiết triển khai; không giả định primary có thể thay qualifier.
5. **Cần mock thật hay fake có hành vi?** Nếu cần điều khiển response/call và không muốn chạy adapter, dùng test mock mechanism theo phiên bản; nếu muốn hành vi xác định, fake hoặc object thật có thể tốt hơn.
6. **Có trùng bean name không?** Nếu có, tìm nguồn đăng ký và chọn một chiến lược thay thế rõ ràng; không mặc định bật overriding.
7. **Có yêu cầu production vẫn khởi động đúng không?** Có test production wiring riêng, không để toàn bộ suite chỉ chạy trên fake.
8. **Có assertion quan sát được không?** Kiểm output, exception, side effect hoặc payload, không chỉ kiểm context/bean tồn tại.
9. **Có test context state không?** Giữ test config nhỏ và singleton fake stateless/resettable; tránh phụ thuộc thứ tự suite.
10. **Khi fail, biết là lỗi tên hay kiểu không?** Đọc root cause: trùng definition name, nhiều candidate cùng type hoặc thiếu candidate.

## 14. Bài tập thực hành

**Bài A — thấy rõ tác dụng `@Primary`:** Trong `PromoFeeTestConfig`, tạm bỏ `@Primary` và chạy `ImportedPrimaryWiringTest`. Vì context có hai `FeePolicy` khác tên mà `CheckoutService` inject theo type, việc chọn candidate có thể trở nên mơ hồ và context fail. Khôi phục annotation và giải thích vì sao lỗi không phải trùng tên definition.

**Bài B — qualifier thắng primary:** Giữ `promoFeePolicy` là primary. Chạy test `qualifiedConsumerKeepsProductionPolicy` và kiểm `AuditFeeService.referenceFee(100)` vẫn là **30**. Đổi tạm qualifier trong constructor từ `standardFeePolicy` sang `promoFeePolicy` để thấy kết quả đổi thành **10**. Hoàn nguyên thay đổi.

**Bài C — cả hai bean vẫn có mặt:** Trong `bothNamedDefinitionsRemainRegistered`, kiểm đúng hai key của `Map<String, FeePolicy>`. Nếu một bean bị xóa khỏi context, test phải fail. Giải thích vì sao sự tồn tại của hai bean cho thấy đây **không** phải bean-definition overriding.

**Bài D — tạo xung đột tên có chủ đích:** Trong một nhánh thử nghiệm, đổi tên bean test thành `standardFeePolicy` (ví dụ `@Bean("standardFeePolicy")`). Với Boot mặc định không cho overriding theo tên, dự kiến context fail lúc đăng ký definition. Khôi phục tên `promoFeePolicy`. Không bật overriding chỉ để hoàn thành bài tập.

**Bài E — kiểm test oracle:** Tạm đổi biểu thức trong standard policy từ `orderAmount >= 500` thành `orderAmount > 500`. Test `productionServicesUseStandardPolicy` với subtotal 500 phải fail vì kỳ vọng **0** theo đặc tả. Hoàn nguyên. Đây là một lỗi nghiệp vụ mà chỉ assert bean tồn tại sẽ không bắt được.

**Bài F — xác minh production:** Bỏ `@Import` khỏi class test import, rồi chạy `ProductionWiringTest` để thấy application context vẫn có policy chuẩn. Nếu ứng dụng thực chỉ khởi động được khi test import fake, cần một bài test production wiring/integration phù hợp để phát hiện khoảng trống.

**Bài G — quyết định hướng thay thế:** Với một `PaymentGateway` gọi mạng thật và một `FakePaymentGateway` in-memory, hãy chọn giữa (1) unit test constructor injection không Spring, (2) import fake khác tên + primary, (3) test mock replacement, (4) profile/conditional config. Nêu rõ từng lựa chọn chứng minh được gì và điều gì vẫn cần integration test.

## 15. Checklist trước khi chốt cấu hình test

- [ ] Tôi đã phân biệt được **hai bean cùng type** với **hai định nghĩa cùng name**?
- [ ] Tôi dùng `@Primary` để **chọn ưu tiên**, không gọi nó là “xóa bean production”?
- [ ] Điểm injection có `@Qualifier` nào làm primary không được chọn không?
- [ ] Nếu inject `List<T>`/`Map<String,T>`, tôi đã hiểu nhiều bean cùng type vẫn xuất hiện?
- [ ] Test bean được khai báo trong test source set, import vào **đúng test context**, không bị scan rộng?
- [ ] Tôi không bật `spring.main.allow-bean-definition-overriding=true` chỉ để che xung đột cấu hình?
- [ ] Nếu thật sự cần thay bean definition, tôi đã chọn cơ chế hỗ trợ của phiên bản Spring Boot/Spring Framework hiện có?
- [ ] Có test bảo đảm application production vẫn khởi động và wire đúng các bean thật khi cần?
- [ ] Assertion kiểm **hành vi**, không chỉ “context loads” hoặc “bean != null”?
- [ ] Test không phụ thuộc trạng thái fake được cache hoặc thứ tự chạy giữa test class?
- [ ] Gradle/JUnit chạy đúng test task, báo cáo phản ánh đầy đủ số invocation và nguyên nhân fail?

**Ghi nhớ:** `@Primary` quyết định **candidate được ưu tiên** khi injection theo type; `@Qualifier` làm rõ **candidate mà điểm tiêm yêu cầu**. Cả hai **không tự thay bean definition trong registry**. Chỉ bật bean definition overriding khi thực sự hiểu xung đột cùng tên, thứ tự đăng ký, phạm vi và tác động của nó; trong đa số test Spring Boot, một test config nhỏ, lựa chọn candidate tường minh hoặc cơ chế test replacement có mục tiêu sẽ dễ bảo trì và đáng tin hơn.
