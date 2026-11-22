# @TestBean hoặc @TestConfiguration để cung cấp fake, stub trong Spring Boot test

Khi kiểm thử một service Spring Boot, ta thường cần thay dependency gọi API ngoài, bộ tính giá, đồng hồ, repository hoặc cổng thanh toán bằng một implementation có hành vi dự đoán được. Khi đó có hai việc khác nhau: **thay chính một bean đã có trong context** và **bổ sung một bean test để Spring chọn nó khi inject**. `@TestBean` và `@TestConfiguration` phục vụ các mục tiêu này nhưng không phải hai tên gọi thay thế cho nhau.

**`@TestBean`** thuộc Spring TestContext từ **Spring Framework 6.2** (dùng được trong Spring Boot 3.4.x). Nó chỉ định một bean sẽ được override bằng đối tượng từ **static factory không tham số** của lớp test. **`@TestConfiguration`** thuộc Spring Boot và đã có từ các dòng Boot cũ; nó cung cấp một hoặc nhiều `@Bean` dành cho test, thường được thêm vào context chính bằng nested class hoặc `@Import`. Nó **không mặc định xóa bean production cùng type**.

Mục tiêu của bài: hiểu khi nào dùng mỗi cách, tránh lỗi trùng bean/nhầm dependency, viết được fake/stub có thể kiểm soát, quản lý state và có test xác nhận **đúng bean đang được service sử dụng**. Dự án cuối bài có ví dụ chạy với Java 17, Spring Boot 3.4.5, JUnit Jupiter và Gradle.

## 1. Test double dùng để làm gì?

Một ứng dụng có interface:

```java
public interface SurchargePolicy {
    int fee(String region);
}
```

Ở production, implementation có thể lấy biểu phí từ hệ thống ngoài. Trong test tính tổng tiền, ta muốn nó trả `7` cho mọi vùng để có kết quả dễ dự đoán. Nếu việc kết nối hệ thống ngoài không thuộc phạm vi phép thử, thay dependency như vậy là hợp lý.

| Thuật ngữ | Bản chất | Ví dụ | Thứ đang kiểm chứng |
| --- | --- | --- | --- |
| **Stub** | Cung cấp kết quả được ấn định | `fee("HN") -> 7` | Logic service xử lý giá trị 7 ra sao |
| **Fake** | Implementation hoạt động nhưng được đơn giản hóa | Repository dùng `Map` trong RAM | Luồng nghiệp vụ với kho dữ liệu giả |
| **Mockito mock** | Đối tượng Mockito hỗ trợ stub và verify | `when(policy.fee("HN")).thenReturn(7)` | Đầu ra và/hoặc lời gọi theo hợp đồng |
| **Spy** | Theo dõi object có hành vi thật | Spy bean đã tồn tại | Quan sát tương tác nhưng vẫn có thể có side effect |

`@TestBean` hoặc `@TestConfiguration` chỉ là **cách đưa test double vào Spring context**; fake/stub bên trong có thể là Java object thông thường và không nhất thiết sử dụng Mockito.

Một unit test chỉ cần `new QuoteService(new FixedSurchargePolicy(7))` nếu mục tiêu là tính toán trong Java. Chỉ cần test context khi còn phải chứng minh Spring đã chọn đúng implementation cho collaborator.

## 2. Bean definition, tên, type và lựa chọn dependency

Ví dụ service dùng constructor injection:

```java
@Service
class QuoteService {
    private final SurchargePolicy policy;
    QuoteService(SurchargePolicy policy) {
        this.policy = policy;
    }
}
```

Spring phải tìm một bean `SurchargePolicy` thích hợp. Khi chỉ có một implementation production, thao tác đó rõ ràng. Nhưng nếu test tạo thêm fake cùng interface, kết quả phụ thuộc vào cách đăng ký:

- **Bean khác tên, cùng type, không `@Primary`/qualifier**: có thể bị `NoUniqueBeanDefinitionException`, vì không chọn được ứng viên.
- **Định nghĩa bean mới trùng tên bean cũ**: có thể bị `BeanDefinitionOverrideException` khi Spring Boot tắt bean-definition overriding (mặc định phổ biến).
- **Bean mới có `@Primary`**, khác tên: chọn fake cho dependency inject theo type không có qualifier; bean production vẫn có thể truy cập theo tên.
- **`@TestBean` override đích danh bean cũ**: trong context test, tên bean đích nhận instance fake từ factory; không tạo thêm ứng viên cùng type chỉ vì thao tác override đó.

**Khác biệt quyết định:** thay một dependency đang được inject không luôn đồng nghĩa thay đổi **bean definition có cùng tên**. `@Primary` chỉ thay lựa chọn khi Spring resolve dependency theo type, còn Bean Override của TestContext thay chính bean đích.

## 3. `@TestBean`: ghi đè bean bằng static factory

Import:

```java
import org.springframework.test.context.bean.override.convention.TestBean;
```

`@TestBean` áp dụng cho **field không static** trong test class, hỗ trợ lựa chọn bean theo type/qualifier hoặc theo tên rõ ràng. Một static factory method không tham số cung cấp instance sẽ thay bean trong test `ApplicationContext`.

Ví dụ minh họa (lớp hoàn chỉnh ở mục 6):

```java
@SpringBootTest
class QuoteWithTestBeanTest {
    @TestBean(
            name = "externalSurchargePolicy",
            methodName = "newFakePolicy",
            enforceOverride = true)
    private SurchargePolicy policy;

    static SurchargePolicy newFakePolicy() {
        return region -> 7;
    }
}
```

**Các ràng buộc phải nhớ:**

1. Field `policy` phải là **instance field**, có type tương thích với bean cần override; Spring cung cấp đối tượng override vào field để test quan sát.
2. Factory `newFakePolicy` phải là **static**, **không có tham số**, kiểu trả về tương thích. Đây không phải `@Bean` factory do Spring container inject tham số.
3. `name` chỉ rõ **bean phải thay**; nếu không chỉ định, Spring suy ra theo type, qualifier và tên field theo quy tắc tìm candidate.
4. `methodName` không bắt buộc khi đặt tên factory theo quy ước mà Spring tìm được, nhưng nên ghi rõ khi có nhiều factory hoặc muốn refactor tên field an toàn.
5. `enforceOverride=true` yêu cầu bean đích **đã tồn tại**. Thiếu bean hoặc sai tên sẽ làm context fail, giúp phát hiện test không còn thay đúng dependency.
6. Nếu để mặc định `enforceOverride=false`, cơ chế `REPLACE_OR_CREATE` có thể **tạo một bean mới** khi không có bean phù hợp. Điều đó có thể che một lỗi cấu hình khi ý định là thay bean production.
7. Override được thực hiện cho **context test**, không sửa source code production, không làm biến mất bean ở tất cả context khác.

Cách này rất phù hợp để cung cấp một fake hoặc stub bằng Java thuần, đặc biệt khi bean production kết nối ra hạ tầng ngoài và test không cần chạy implementation thật.

### Nhiều candidate cùng interface?

Nếu có `stripePaymentGateway` và `localPaymentGateway` cùng implement `PaymentGateway`, `@TestBean PaymentGateway gateway` không nói rõ cái nào sẽ bị override. Hãy ghi `name="stripePaymentGateway"` hoặc `@Qualifier` đúng bean đích. Bean override không có cùng khả năng suy diễn phức tạp như mọi tình huống autowiring; cấu hình mơ hồ có thể làm test context fail.

### Không tự động kế thừa AOP advice của bean bị thay

Các override dạng `REPLACE` / `REPLACE_OR_CREATE` trong Spring TestContext tạo **manual singleton**. Đối tượng test được đăng ký không đi qua toàn bộ bean post-processing như bean production. Vì vậy đừng giả định `@Transactional`, `@Cacheable`, retry hoặc security proxy từng bao quanh bean production sẽ tiếp tục tồn tại trên fake.

Nếu cần kiểm thử transaction của một service, **giữ service thật** và chỉ thay dependency gọi hệ thống ngoài, sau đó kiểm tra transaction qua repository/database thực. Nếu thay cả service bởi `@TestBean`, test không còn là bằng chứng về advice của service production.

## 4. `@TestConfiguration`: bổ sung bean và cấu hình riêng cho test

Import:

```java
import org.springframework.boot.test.context.TestConfiguration;
```

`@TestConfiguration` là annotation Spring Boot, dùng định nghĩa các `@Bean` phục vụ test. So với `@TestBean`, `@Bean` method trong `@TestConfiguration` có thể nhận dependency từ container qua tham số. Nó thích hợp khi cần dựng một fake phức tạp hoặc nhiều bean hỗ trợ.

Có hai cách tổ chức:

- **Nested static `@TestConfiguration`** trong test class: Spring Boot bổ sung config đó bên cạnh primary app configuration khi tải test context.
- **Top-level `@TestConfiguration`** trong `src/test/java`: thường **không** được tự component scan; test cần `@Import(MyTestConfiguration.class)` tường minh. Cách này có thể tái sử dụng cho nhiều test.

Ví dụ:

```java
@TestConfiguration(proxyBeanMethods = false)
class PolicyTestConfiguration {
    @Bean("testSurchargePolicy")
    @Primary
    SurchargePolicy fakeSurchargePolicy() {
        return region -> 11;
    }
}
```

Bean `testSurchargePolicy` có tên khác `externalSurchargePolicy` production. Khi được import, cả hai bean vẫn có thể tồn tại; `@Primary` chỉ giúp những injection **theo type** ưu tiên fake.

**Không nhầm `@Primary` với override:** nếu một nơi dùng `@Qualifier("externalSurchargePolicy")`, hoặc `ApplicationContext.getBean("externalSurchargePolicy")`, nó vẫn nhận bean production. Với `List<SurchargePolicy>`, cả real và fake có thể cùng xuất hiện. Khi mục tiêu là **tuyệt đối không khởi tạo hoặc dùng bean production**, `@TestBean` theo tên hoặc tái cấu trúc cấu hình/conditional registration thường rõ ràng hơn.

### Vì sao không chỉ đặt `@Bean` cùng tên production?

Đặt `@Bean("externalSurchargePolicy")` vào test config trong khi production có bean đó không đồng nghĩa Spring tự thay. Khi bean-definition overriding bị tắt, nó có thể làm context fail do trùng tên. Bật `spring.main.allow-bean-definition-overriding=true` toàn cục chỉ để né lỗi có thể che những xung đột cấu hình khác và tạo phụ thuộc vào trình tự đăng ký. Nên ưu tiên `@TestBean` để **thay đích danh** hoặc tên khác + primary khi chỉ cần lựa chọn theo type.

## 5. Dự án minh họa — phiên bản và cấu trúc

Ví dụ cố định **Java 17, Spring Boot 3.4.5, Spring Framework 6.2.x do Boot quản lý**, Gradle Groovy DSL và JUnit Jupiter. Việc chọn Boot **3.4.x** là có chủ đích vì `@TestBean` không có trong Spring Framework 6.1 / Boot 3.3.

Quy tắc quote:

- `subtotal` là số không âm; âm thì từ chối `IllegalArgumentException`.
- Tổng giá bằng `subtotal + surcharge`.
- Real `ExternalSurchargePolicy` trả `35` cho `HN`, `20` cho `HCM`, `50` cho vùng khác.
- `@TestBean` thay real bằng fake trả `7`; `@TestConfiguration` bổ sung fake primary trả `11`.
- Dùng `Math.addExact` để không im lặng khi tổng tràn `int`.

Cây tệp:

```text
settings.gradle
build.gradle
src/main/java/com/example/beanoverride/BeanOverrideApplication.java
src/main/java/com/example/beanoverride/SurchargePolicy.java
src/main/java/com/example/beanoverride/ExternalSurchargePolicy.java
src/main/java/com/example/beanoverride/QuoteService.java
src/test/java/com/example/beanoverride/FixedSurchargePolicy.java
src/test/java/com/example/beanoverride/QuoteUnitTest.java
src/test/java/com/example/beanoverride/QuoteRealContextTest.java
src/test/java/com/example/beanoverride/QuoteWithTestBeanTest.java
src/test/java/com/example/beanoverride/FakeSurchargeTestConfiguration.java
src/test/java/com/example/beanoverride/QuoteWithTestConfigurationTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-test-bean-replacement'
```

**`build.gradle`**

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các dependency của Spring Framework và JUnit để Spring Boot quản lý nhất quán. Không trộn `spring-test` 6.2 thủ công vào một dự án Boot 3.3 đã cố định Framework 6.1 chỉ để có annotation mới. Gradle Wrapper phải có phiên bản tương thích với JDK và Boot của dự án.

## 6. Code production: service không trực tiếp khởi tạo dependency

**`src/main/java/com/example/beanoverride/BeanOverrideApplication.java`**

```java
package com.example.beanoverride;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BeanOverrideApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeanOverrideApplication.class, args);
    }
}
```

**`src/main/java/com/example/beanoverride/SurchargePolicy.java`**

```java
package com.example.beanoverride;

public interface SurchargePolicy {
    int fee(String region);
}
```

**`src/main/java/com/example/beanoverride/ExternalSurchargePolicy.java`**

```java
package com.example.beanoverride;

import org.springframework.stereotype.Component;

@Component("externalSurchargePolicy")
public class ExternalSurchargePolicy implements SurchargePolicy {
    @Override
    public int fee(String region) {
        return switch (region) {
            case "HN" -> 35;
            case "HCM" -> 20;
            default -> 50;
        };
    }
}
```

Production bean cố ý không kết nối mạng để project demo chạy độc lập. Khi ứng dụng thật truy cập remote system, vai trò test double càng rõ: tách nhánh logic service khỏi độ ổn định/chi phí của remote.

**`src/main/java/com/example/beanoverride/QuoteService.java`**

```java
package com.example.beanoverride;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final SurchargePolicy policy;

    public QuoteService(SurchargePolicy policy) {
        this.policy = policy;
    }

    public Quote quote(int subtotal, String region) {
        if (subtotal < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }
        int surcharge = policy.fee(region);
        return new Quote(
                subtotal,
                surcharge,
                Math.addExact(subtotal, surcharge));
    }

    public record Quote(int subtotal, int surcharge, int total) {
    }
}
```

Constructor injection là điều kiện quan trọng để bean replacement có tác dụng: Spring lựa chọn implementation khi tạo `QuoteService`. Nếu service tự gọi `new ExternalSurchargePolicy()` hoặc static utility bên trong, `@TestBean` hay `@Primary` không tự thay lời gọi hard-code ấy.

## 7. Test fake/stub bằng Java thuần và context gốc

**`src/test/java/com/example/beanoverride/FixedSurchargePolicy.java`**

```java
package com.example.beanoverride;

public final class FixedSurchargePolicy implements SurchargePolicy {
    private final int fee;

    public FixedSurchargePolicy(int fee) {
        this.fee = fee;
    }

    @Override
    public int fee(String region) {
        return fee;
    }
}
```

Đây là một **stub bất biến**, có thể dùng nhiều lần mà không có mutable counter/cache. Nếu cần fake repository hỗ trợ ghi/đọc, sẽ phải thiết kế reset/isolation riêng khi test context được cache.

**`src/test/java/com/example/beanoverride/QuoteUnitTest.java`**

```java
package com.example.beanoverride;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class QuoteUnitTest {
    private final QuoteService service =
            new QuoteService(new FixedSurchargePolicy(9));

    @Test
    void computesQuoteWithInjectedStub() {
        assertEquals(
                new QuoteService.Quote(100, 9, 109),
                service.quote(100, "HN"));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote(-1, "HN"));
    }
}
```

Unit test kiểm chứng quy tắc Java và dependency stub do constructor truyền vào. Nó không chứng minh Spring sẽ chọn bean nào, vì **không khởi động context**.

**`src/test/java/com/example/beanoverride/QuoteRealContextTest.java`**

```java
package com.example.beanoverride;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest
class QuoteRealContextTest {
    @Autowired
    private QuoteService service;

    @Autowired
    private ApplicationContext context;

    @Test
    void originalPolicyIsUsed() {
        assertInstanceOf(
                ExternalSurchargePolicy.class,
                context.getBean("externalSurchargePolicy"));

        assertEquals(
                new QuoteService.Quote(100, 35, 135),
                service.quote(100, "HN"));
    }
}
```

Lớp này tải context với bean production, không có override và không import fake. Nó là đường chuẩn để đối chiếu hai test thay bean ở phần sau.

## 8. Test `@TestBean`: fake thay đúng bean production

**`src/test/java/com/example/beanoverride/QuoteWithTestBeanTest.java`**

```java
package com.example.beanoverride;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.convention.TestBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class QuoteWithTestBeanTest {
    @TestBean(
            name = "externalSurchargePolicy",
            methodName = "createFake",
            enforceOverride = true)
    private SurchargePolicy policy;

    @Autowired
    private QuoteService service;

    @Autowired
    private ApplicationContext context;

    static SurchargePolicy createFake() {
        return new FixedSurchargePolicy(7);
    }

    @Test
    void targetBeanIsOverriddenAndInjected() {
        assertSame(
                policy,
                context.getBean("externalSurchargePolicy"));
        assertInstanceOf(FixedSurchargePolicy.class, policy);
        assertEquals(
                1,
                context.getBeansOfType(SurchargePolicy.class).size());

        assertEquals(
                new QuoteService.Quote(100, 7, 107),
                service.quote(100, "HN"));
    }

    @Test
    void serviceGuardRemainsActive() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote(-1, "HN"));
    }
}
```

Test xác minh ba loại bằng chứng: **bean được thay đúng tên**, **instance tiêm vào test là fake**, và **service thật đã dùng fake để tính giá 107**. Vì `enforceOverride=true`, nếu production bean `externalSurchargePolicy` bị xóa/đổi tên, context phải báo lỗi thay vì âm thầm thêm một bean.

`@TestBean` còn hỗ trợ lựa chọn theo type/qualifier mà không cần name. Trong trường hợp có nhiều bean cùng type, ghi rõ bean name như ở đây giúp tránh ambiguity. Factory ở đây đặt cùng test class; nếu dùng factory ngoài, `methodName` có thể có dạng `fully.qualified.Class#staticMethod` theo API của Spring.

Lưu ý: bean fake trả 7 là đối tượng Java thông thường, không phải Mockito mock. Nếu test cần verify invocation, có thể viết fake giữ lịch sử lời gọi hoặc chọn `@MockitoBean` phù hợp với mục đích.

## 9. Test `@TestConfiguration`: thêm bean primary, không xóa bean real

Một test configuration ở cấp file chỉ được thêm khi test `@Import` nó.

**`src/test/java/com/example/beanoverride/FakeSurchargeTestConfiguration.java`**

```java
package com.example.beanoverride;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class FakeSurchargeTestConfiguration {
    @Bean("testSurchargePolicy")
    @Primary
    public SurchargePolicy testSurchargePolicy() {
        return new FixedSurchargePolicy(11);
    }
}
```

**`src/test/java/com/example/beanoverride/QuoteWithTestConfigurationTest.java`**

```java
package com.example.beanoverride;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertSame;

@SpringBootTest
@Import(FakeSurchargeTestConfiguration.class)
class QuoteWithTestConfigurationTest {
    @Autowired
    private QuoteService service;

    @Autowired
    private ApplicationContext context;

    @Test
    void primaryFakeIsSelectedForTypeInjection() {
        assertInstanceOf(
                ExternalSurchargePolicy.class,
                context.getBean("externalSurchargePolicy"));

        Object fake = context.getBean("testSurchargePolicy");
        assertInstanceOf(FixedSurchargePolicy.class, fake);

        assertEquals(
                2,
                context.getBeansOfType(SurchargePolicy.class).size());
        assertSame(fake, context.getBean(SurchargePolicy.class));

        assertEquals(
                new QuoteService.Quote(100, 11, 111),
                service.quote(100, "HN"));
    }
}
```

Ở context này có **hai** `SurchargePolicy` beans: real `externalSurchargePolicy` và fake `testSurchargePolicy`. `@Primary` làm `QuoteService` (constructor theo type) nhận fake. Nhưng lookup theo tên `externalSurchargePolicy` vẫn ra real: không thể tuyên bố `@TestConfiguration` đã loại bỏ dependency production ở toàn bộ ứng dụng.

Nếu thay bằng **nested static `@TestConfiguration`** bên trong test, Spring Boot sẽ thêm cấu hình ấy vào context test mà không cần file top-level và import riêng. Tránh cùng lúc khai báo nested và import hai cấu hình có bean trùng tên.

## 10. Cách chạy và kết quả dự kiến

Với Gradle Wrapper tương thích với Boot/JDK, từ thư mục gốc:

```bash
./gradlew clean test
./gradlew test --tests com.example.beanoverride.QuoteUnitTest
./gradlew test --tests com.example.beanoverride.QuoteRealContextTest
./gradlew test --tests com.example.beanoverride.QuoteWithTestBeanTest
./gradlew test --tests com.example.beanoverride.QuoteWithTestConfigurationTest
```

Trên Windows dùng `gradlew.bat` với các tham số tương ứng. Những assertion trên được **thiết kế để PASS** với code nguyên bản và dependencies phù hợp; đây là kỳ vọng từ ví dụ, **không phải stdout của build đã chạy thực tế**.

| Test | Spring context? | Bean service nhận | Giá trị quote với `subtotal=100`, `HN` |
| --- | --- | --- | --- |
| `QuoteUnitTest` | Không | Stub Java trực tiếp, phí 9 | `Quote(100,9,109)` |
| `QuoteRealContextTest` | Có, mặc định | Real policy, phí 35 | `Quote(100,35,135)` |
| `QuoteWithTestBeanTest` | Có, bean bị override | Fake thay bean `externalSurchargePolicy`, phí 7 | `Quote(100,7,107)` |
| `QuoteWithTestConfigurationTest` | Có, thêm test bean | Bean `testSurchargePolicy` là primary, phí 11 | `Quote(100,11,111)` |

Các lớp Spring test có thể dùng **context khác nhau** vì override/import khác nhau. Không phải một context được thay đổi tùy ý giữa các test method. Spring TestContext cache làm cấu hình context và việc quản lý mutable state của fake trở nên quan trọng.

## 11. Khi cần Mockito thay vì fake Java

Ở Spring Framework 6.2, `@MockitoBean` thay bean bằng Mockito mock. Ví dụ sau là **trích đoạn** đặt trong lớp Spring test có import:

```java
@MockitoBean(name = "externalSurchargePolicy")
SurchargePolicy policy;

@BeforeEach
void setUp() {
    Mockito.when(policy.fee("HN")).thenReturn(7);
}
```

Import tương ứng là `org.springframework.test.context.bean.override.mockito.MockitoBean` và `org.mockito.Mockito`. Dùng cách này khi muốn từng test thiết lập response khác nhau hoặc `verify(policy).fee("HN")` là điều cần kiểm tra. Với logic có hành vi cố định và đơn giản, fake/stub Java dễ đọc và ít phụ thuộc API mocking hơn.

Phân biệt với `@MockBean` cũ ở `org.springframework.boot.test.mock.mockito.MockBean`: API Boot đó **deprecated từ 3.4** để chuyển sang `@MockitoBean`. Đừng nhầm các tên rất giống nhau giữa `@TestBean`, `@MockitoBean`, `@MockBean`, `@TestConfiguration`; mỗi loại có phiên bản và semantics khác nhau.

## 12. Giới hạn và lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| Không import được `@TestBean` | Đang dùng Framework 6.1/Boot 3.3 | Dùng Boot 3.4+ hoặc `@TestConfiguration` theo phiên bản hiện có |
| `@TestBean` fail vì bean đích không tồn tại | Sai tên/type, `enforceOverride=true` | Xác nhận bean thực sự được đăng ký ở context được thử |
| Không tìm thấy factory của `@TestBean` | Method không static, có tham số hoặc sai tên/type | Dùng static no-arg factory và `methodName` rõ ràng |
| Nhiều bean cùng type, context không start | `@TestConfiguration` thêm fake nhưng chưa chọn ưu tiên | Thêm `@Primary` hoặc `@Qualifier` ở đúng nơi injection |
| Lỗi bean definition trùng tên | `@Bean` test trùng name với production, override bị tắt | Dùng tên khác + primary hoặc `@TestBean` đúng đích |
| Có `@Primary` nhưng chỗ khác vẫn gọi real bean | Dependency theo `@Qualifier`/name hoặc lookup trong collection | Xác định cách injection của từng collaborator |
| Test chưa bao giờ nhận fake | Quên `@Import`, fake ở top-level test config chưa được tải | Assert bean identity/type và kết quả của service |
| Test dùng fake nhưng external adapter thật vẫn lỗi | Integration của adapter đã bị bỏ qua | Viết adapter contract/integration test với hạ tầng kiểm soát |
| Fake giữ state từ test trước | Singleton/context cache, không reset collection | Tạo fake bất biến, reset hoặc isolate state đúng phạm vi |
| Test không chạy advice Spring trên bean giả | Override đăng ký bare singleton, bỏ qua proxy processing thường | Giữ service thật qua proxy; test advice bằng bean/integration phù hợp |

**Điểm hay bị bỏ sót:** `@Primary` chỉ ảnh hưởng lựa chọn ứng viên cho injection theo type; một `@Qualifier("externalSurchargePolicy")` vẫn có thể chọn real bean. Nếu mục tiêu là chặn mọi đường đến remote dependency, cách thêm primary có thể chưa đủ.

**AOP và transaction:** fake được cài bằng `@TestBean` không tự giữ các advice của bean cũ. Thay payment client để thử nghiệp vụ thì hợp lý; thay cả transactional service rồi tuyên bố rollback đã đúng là suy luận không có bằng chứng.

**Context cache và isolation:** một fake singleton chứa `List`, `Map` có thể bị mutate qua test khác trong cùng context; `@TestInstance(PER_METHOD)` chỉ tạo mới đối tượng JUnit test, không bắt Spring tạo context mới. Dùng `@BeforeEach` reset hợp lý, tách test data hoặc chọn immutable fake. `@DirtiesContext` khi thật sự cần context mới nhưng tốn thời gian.

## 13. Các phản chứng giúp phát hiện cấu hình thay bean sai

Hãy thử trên **bản sao của ví dụ** rồi hoàn nguyên:

1. Bỏ `@Primary` ở `FakeSurchargeTestConfiguration`: test có hai bean cùng type không qualifier thường không dựng được service vì ambiguous dependency.
2. Đổi tên production bean nhưng giữ `@TestBean(name="externalSurchargePolicy", enforceOverride=true)`: context override phải báo lỗi thay vì lặng lẽ tạo bean thứ hai.
3. Xóa `@Import(FakeSurchargeTestConfiguration.class)`: service sẽ dùng real phí 35; assertion mong đợi 111 phải fail.
4. Đổi `new FixedSurchargePolicy(7)` thành `new FixedSurchargePolicy(8)`: test `QuoteWithTestBeanTest` phải báo đỏ ở `Quote(100,7,107)`.
5. Đặt `@Qualifier("externalSurchargePolicy")` cho dependency của một collaborator: trong context dùng `@TestConfiguration`, collaborator đó có thể nhận real bean dù test bean là primary.
6. Cho fake lưu mutable counter xuyên nhiều test method rồi bỏ cleanup: chạy từng test và cả suite có thể cho kết quả khác nhau, dấu hiệu shared state chứ không phải lỗi của JUnit order.

Bằng chứng tốt không chỉ là context khởi động thành công. Hãy xác nhận **đối tượng thực sự được inject**, **kết quả đầu ra** và phạm vi mà test double đã thay thế.

## 14. Checklist khi review bài test có fake/stub Spring

- Java/Spring Boot version có hỗ trợ annotation đang dùng không?
- Ý định là **override một bean hiện có** hay **thêm một bean mới và đổi lựa chọn injection**?
- Với `@TestBean`, field có non-static, static factory có no-arg và type tương thích không? Nên bật `enforceOverride=true` để tránh che lỗi cấu hình chứ?
- Với `@TestConfiguration`, class nằm trong test source, nested hay được `@Import` đúng test? Bean mới có vô tình trùng tên production không?
- Nếu dùng `@Primary`, collaborator có thực sự inject theo type? Có qualifier/name hoặc collection injection làm behavior khác?
- Test có assert cả bean identity/type và kết quả nghiệp vụ thay vì chỉ “context loads”?
- Fake có giữ mutable state, singleton hoặc DB ngoài? Ai reset/cleanup và có an toàn khi chạy parallel không?
- Bean bị override có AOP/transaction/security advice quan trọng cần được test bằng integration thực không?
- Có thêm contract test của adapter thật để không nhầm test fake xanh với hạ tầng production đúng không?

**Kết luận:** **`@TestBean` (Spring Framework 6.2+) thích hợp khi muốn thay đích danh một bean bằng fake/stub từ static factory**, đặc biệt với `name` và `enforceOverride=true`. **`@TestConfiguration` thích hợp khi muốn bổ sung cấu hình test**, có thể đưa vào fake qua `@Bean` + `@Primary` hoặc cấu hình injection rõ ràng. Cả hai đều chỉ tạo bằng chứng cho context kiểm thử; để tin rằng nghiệp vụ và hạ tầng đúng, cần assertion phù hợp và các test integration/contract ở đúng ranh giới.

## Tham khảo chính thức

- Spring Framework 6.2 — `@TestBean`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/test/context/bean/override/convention/TestBean.html
- Spring Framework — Bean Overriding in Tests: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — `@TestConfiguration` API: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/context/TestConfiguration.html
