# JaCoCo: line, branch coverage và chất lượng điều kiện kiểm chứng

Trong nhóm **Build và CI** của module **Spring Boot - testing**, JaCoCo giúp trả lời **mã Java nào đã được chạy qua khi chạy test**, chứ không trực tiếp trả lời **kết quả của mã có đúng hay không**. Nếu test gọi một method rồi không kiểm tra return value, JaCoCo vẫn có thể tô xanh các dòng và branches đã thực thi. Do đó, chiến lược đúng là phối hợp **LINE coverage**, **BRANCH coverage** và **chất lượng assertions/điều kiện nghiệp vụ**.

Bài học trình bày đầy đủ: cách JaCoCo instrument bytecode, định nghĩa các counters, ngữ nghĩa của short-circuit `&&`/`||`, ma trận biên của một business policy, project mẫu **Java 17 + Spring Boot 3.5 + Gradle + JUnit Jupiter**, JaCoCo HTML/XML và coverage threshold gate trong `check`, 12 unit tests với assertions mạnh, 5 MockMvc tests, demo Java SE có stdout chính xác, đọc report/CI, mutation testing, lỗi exclusions/multi-module và checklist review.

**Nguyên tắc:** 100% line hoặc branch là **tín hiệu đường đi được thực thi**, không phải chứng nhận không có bug, không phải MC/DC và không thay thế contract/integration/security tests. Coverage threshold nên là hàng rào chống regression, không được biến thành KPI khiến người viết test cố chạy code mà không assert.

## 1. JaCoCo đo ở đâu?

```text
Java source (src/main/java)
      |
      v
javac / Gradle compileJava
      |
      v
*.class (bytecode)
      |
      v
Gradle test (JaCoCo agent instrument code)
      |
      +-- JUnit Jupiter tests
      +-- MockMvc tests
      |
      v
build/jacoco/test.exec
      |
      +-- jacocoTestReport
      |      +-- HTML report for reviewers
      |      +-- XML report for CI analyzers
      |
      +-- jacocoTestCoverageVerification
             +-- checks threshold
             +-- PASS or FAIL Gradle task
                    |
                    v
                Gradle check
           [if dependsOn is configured]
```

Ba hoạt động khác nhau:

1. **Test execution:** agent ghi instruction/branch probes. Mã production phải thực sự chạy trong JVM được instrument, không chỉ compilation thành công.
2. **Report:** `jacocoTestReport` kết hợp execution data với class files và source line debug information để tạo báo cáo.
3. **Verification:** `jacocoTestCoverageVerification` so sánh counters với ngưỡng. Nó fail nếu rule vi phạm; không tự động thay thế report hoặc kiểm tra assertions.

**Gradle không mặc định nối verification vào lifecycle `check`.** Ngoài ra, tài liệu Gradle chỉ rõ `jacocoTestReport` không tự phụ thuộc test task. Build file ở mục thực hành gắn `dependsOn` và `finalizedBy` tường minh, tránh chạy CI check xanh giả khi chưa đánh giá coverage.

## 2. Các counters của JaCoCo và ý nghĩa

| Counter | Nó đo gì? | Không nên suy luận |
| --- | --- | --- |
| `INSTRUCTION` (C0) | Bytecode instructions được chạy hoặc missed | "Có assertions đúng" |
| `LINE` | Source lines gắn instructions, có debug line information | "Cả hai nhánh trên dòng if đã chạy" |
| `BRANCH` (C1) | Bytecode branches của if/switch | "Mọi điều kiện Boolean đã độc lập được kiểm chứng" |
| `COMPLEXITY` | Cyclomatic complexity của methods | "Đủ test chính xác nếu có N methods" |
| `METHOD` | Methods có ít nhất một instruction được chạy | "Toàn bộ body/nhánh của method đã chạy" |
| `CLASS` | Classes có ít nhất một method được chạy | "Lớp hoạt động đúng" |

**LINE:** Một source line được JaCoCo xem là executed nếu **ít nhất một bytecode instruction** ánh xạ tới dòng ấy đã chạy. Khi source line biên dịch thành nhiều instructions, JaCoCo HTML có thể hiển thị **partial/yellow** dù line đã được chạm tới; màu green/full biểu thị các instructions trên dòng được covered, không phải kết quả đúng.

**BRANCH:** JaCoCo xem các điều kiện `if` và `switch` ở mức bytecode. Nó không lấy số branches bằng cách đếm `if` trên Java source; short-circuit expressions có nhiều jumps và compiler có thể tạo synthetic instructions. **Exception handling không được tính là BRANCH** theo counter C1, nên 100% BRANCH không chứng minh đã chạy các `catch`, rollback hay timeout paths.

**COMPLEXITY:** Hữu ích để phát hiện method có nhiều đường điều khiển; không tự chọn được test data/oracle. Một method có complexity thấp vẫn có thể gây lỗ hổng nghiệp vụ nếu condition sai.

**Method/Class:** Constructors và static initialization cũng có thể đóng góp counters. Với Spring Boot, việc context startup tạo beans có thể tăng method/line coverage dù chưa kiểm tra business logic.

## 3. Đọc tỉ lệ covered/missed

Với số counter có mẫu số dương:

```text
coveredRatio = covered / (covered + missed)
percentage   = 100 * covered / (covered + missed)
```

**Ví dụ giả định** (không phải output của bài chạy):

| Counter | Covered | Missed | Tỉ lệ |
| --- | ---: | ---: | ---: |
| LINE | 18 | 2 | 90% |
| BRANCH | 9 | 3 | 75% |

Nếu policy yêu cầu 90% LINE và 80% BRANCH, mẫu này **đạt LINE, trượt BRANCH**. Khi một class không có decision branch nào được JaCoCo nhận diện, BRANCH có thể là `n/a` do denominator bằng 0; đừng ép thành 0 hoặc 100 theo giả định.

Tỷ lệ project không được tính bằng trung bình đơn giản của % từng class có kích thước khác nhau. Dùng tổng counters covered/missed ở scope tương ứng; ngưỡng CLASS/PACKAGE/BUNDLE phải rõ.

## 4. Vì sao line coverage không chứng minh true/false?

```java
String tier(int total) {
    if (total >= 100) {
        return "FREE";
    }
    return "STANDARD";
}
```

Đây là snippet, chưa phải class runnable. Test chỉ gọi `tier(100)` sẽ chạm tới `if` và nhánh FREE nhưng không chạy return STANDARD. Cần thêm `tier(99)`, cả hai có assertions cụ thể. Boundary test tại **100** phát hiện mutant `>=100` bị đổi thành `>100`; test chỉ dùng 1200 không phát hiện lỗi đó.

Một method đã chạy qua tất cả dòng chưa chắc pass cả true/false cases. Ngược lại, hai branches đã chạy nhưng test không assert output cũng có thể cho JaCoCo xanh mà không có giá trị kiểm chứng.

## 5. Short-circuit: nhiều nguyên nhân cho cùng một nhánh

Một quy tắc:

```java
if (subtotal >= 1000 || (vip && subtotal >= 500)) {
    return Tier.FREE;
}
```

Đặt A=`subtotal>=1000`, B=`vip`, C=`subtotal>=500`. Java có short-circuit: nếu A true thì không đánh giá B/C; nếu A false và B false thì không đánh giá C; chỉ khi A=false, B=true mới phải xét C.

| subtotal | vip | A | B | C có thực sự được đánh giá? | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| 1000 | false | true | Skip | Không | FREE |
| 999 | false | false | false | Không | Không FREE |
| 500 | true | false | true | Có, true | FREE |
| 499 | true | false | true | Có, false | Không FREE |
| 500 | false | false | false | Không | Không FREE |

Một bài test FREE từ `subtotal=1000` **không** chứng minh VIP path đúng. Thậm chí một true/false result cho toàn bộ biểu thức không nhất thiết chứng minh ảnh hưởng độc lập của A, B, C. BRANCH dựa trên bytecode giúp chỉ ra đường đi thiếu; **MC/DC** là tiêu chí condition/decision riêng, đòi hỏi chứng minh tác động độc lập của từng điều kiện khi phù hợp với requirements.

## 6. Nghiệp vụ mô phỏng cho project runnable

ShippingPolicy định nghĩa:

1. Subtotal âm → ném `IllegalArgumentException`.
2. `subtotal >= 1000` **hoặc** `vip && subtotal >= 500` → miễn vận chuyển, `FREE`.
3. Nếu chưa FREE, coupon `SAVE10` và `subtotal >= 200` → `DISCOUNTED`.
4. Trường hợp khác → `STANDARD`.

Miễn phí có **độ ưu tiên cao hơn** coupon discount. Với số tiền thật phải quy định currency/minor units/rounding; ở đây subtotal int giúp thấy rõ lỗi biên.

```text
subtotal < 0 ?  yes -> IllegalArgumentException
        |
        no
        v
>= 1000 OR (vip AND >= 500) ? yes -> FREE
        |
        no
        v
coupon == "SAVE10" AND >= 200 ? yes -> DISCOUNTED
        |
        no
        v
      STANDARD
```

Dấu `>=`, `&&`, `||`, check null và thứ tự rules đều cần được bảo vệ bằng tests. Đây là ví dụ cố ý để học coverage/branch quality, không phải chính sách vận chuyển của một doanh nghiệp thật.

## 7. Sơ đồ project

```text
shipping-coverage/
├── build.gradle
└── src/
    ├── main/java/example/coverage/
    │   ├── CoverageApplication.java
    │   ├── ShippingPolicy.java
    │   ├── PolicyConfiguration.java
    │   ├── ShippingController.java
    │   ├── ApiErrorAdvice.java
    │   └── ShippingPolicyDemo.java
    └── test/java/example/coverage/
        ├── ShippingPolicyTest.java
        └── ShippingControllerTest.java
```

Project sử dụng Java 17, Spring Boot 3.5.x, JUnit Jupiter, MockMvc và JaCoCo Gradle plugin. Unit test policy dùng **Java thuần không mở Spring context**. MVC test dựng test slice có policy bean thật. Demo Java SE không phụ thuộc Spring, nên có thể chạy `javac/java` độc lập.

## 8. build.gradle: report và coverage gate thật

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'jacoco'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

jacoco {
    toolVersion = '0.8.13'
}

tasks.named('test') {
    useJUnitPlatform()
    finalizedBy tasks.named('jacocoTestReport')
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')

    reports {
        html.required = true
        xml.required = true
        csv.required = false
    }
}

tasks.named('jacocoTestCoverageVerification') {
    dependsOn tasks.named('test')

    violationRules {
        rule {
            element = 'CLASS'
            includes = ['example.coverage.ShippingPolicy']

            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.90
            }

            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}

tasks.named('check') {
    dependsOn tasks.named('jacocoTestCoverageVerification')
}
```

**Giải thích từng phần:**

- `id 'jacoco'` là Gradle Java coverage plugin; nó gắn JaCoCo agent vào test tasks tương ứng.
- `toolVersion='0.8.13'` pin một bản 0.8.x tương thích Java 17. Khi nâng JDK/class-file version, kiểm tra JaCoCo support matrix thay vì dùng agent cũ mãi.
- `test.finalizedBy jacocoTestReport` tạo report sau test khi Gradle chạy finalizer, giúp debug các test failures.
- `jacocoTestReport.dependsOn test` bảo đảm gọi report trực tiếp vẫn chạy tests trước.
- `xml.required=true` phục vụ CI/Sonar/coverage dashboard; `html.required=true` cho reviewer.
- `jacocoTestCoverageVerification.dependsOn test` đảm bảo verification có execution data của build mới.
- `check.dependsOn verification` là wiring quan trọng: **verification không tự động là dependency của check** trong plugin mặc định.
- Gate scope `element='CLASS'` + `includes=['example.coverage.ShippingPolicy']` bảo vệ **class nghiệp vụ trọng yếu**. Một dự án thật nên có thêm package/bundle rules và rules cho code mới; rule minh họa này không phủ cả ứng dụng.
- Minimum `0.90 LINE` và `0.80 BRANCH` là ví dụ, cần baseline và lý do theo rủi ro. Không tuyên bố project thực chạy chắc chắn đạt đúng percentages khi chưa đo.

**Cảnh báo:** `jacocoTestCoverageVerification` không tự tạo HTML/XML, còn report task không fail build vì threshold nếu không có verification. Kết hợp cả hai trong CI.

## 9. ShippingPolicy.java: class business thuần Java

Tạo `src/main/java/example/coverage/ShippingPolicy.java`:

```java
package example.coverage;

public final class ShippingPolicy {

    public enum Tier {
        FREE,
        DISCOUNTED,
        STANDARD
    }

    public Tier classify(
            int subtotal,
            boolean vip,
            String coupon) {

        if (subtotal < 0) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }

        if (subtotal >= 1000
                || (vip && subtotal >= 500)) {
            return Tier.FREE;
        }

        if ("SAVE10".equals(coupon)
                && subtotal >= 200) {
            return Tier.DISCOUNTED;
        }

        return Tier.STANDARD;
    }
}
```

Phương pháp `classify` là pure function theo inputs (ngoại trừ exception với subtotal âm), không cần Spring/DB/network. Đây là kiểu logic thích hợp nhất để test branches và boundaries nhanh.

`"SAVE10".equals(coupon)` **null-safe**: nếu coupon=null, kết quả false thay vì ném NPE. FREE được xét trước coupon. Các semantics đó là contract cần test, không chỉ những dòng được phủ.

## 10. Spring Boot configuration và application

Tạo `src/main/java/example/coverage/PolicyConfiguration.java`:

```java
package example.coverage;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PolicyConfiguration {

    @Bean
    ShippingPolicy shippingPolicy() {
        return new ShippingPolicy();
    }
}
```

Tạo `src/main/java/example/coverage/CoverageApplication.java`:

```java
package example.coverage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CoverageApplication {
    public static void main(String[] args) {
        SpringApplication.run(CoverageApplication.class, args);
    }
}
```

Business method không cần `@Service`; cấu hình tạo bean một lần cho MVC application. Trong unit tests tự tạo `new ShippingPolicy()`, còn MVC test import `PolicyConfiguration` để wiring real policy thay vì mock nó.

## 11. ShippingController.java: contract HTTP của rule

Tạo `src/main/java/example/coverage/ShippingController.java`:

```java
package example.coverage;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ShippingController {

    private final ShippingPolicy policy;

    public ShippingController(ShippingPolicy policy) {
        this.policy = policy;
    }

    @GetMapping("/shipping/tier")
    public TierResponse tier(
            @RequestParam int subtotal,
            @RequestParam(defaultValue = "false")
            boolean vip,
            @RequestParam(required = false)
            String coupon) {

        ShippingPolicy.Tier result =
                policy.classify(subtotal, vip, coupon);

        return new TierResponse(result.name());
    }

    public record TierResponse(String tier) {
    }
}
```

Tạo `src/main/java/example/coverage/ApiErrorAdvice.java`:

```java
package example.coverage;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalidSubtotal() {
        return ResponseEntity.badRequest()
                .body(Map.of(
                        "error", "invalid subtotal"));
    }
}
```

HTTP behavior được định nghĩa:

- `GET /shipping/tier?subtotal=1000` → 200 + `{"tier":"FREE"}`.
- `GET /shipping/tier?subtotal=500&vip=true` → 200 FREE.
- `GET /shipping/tier?subtotal=200&coupon=SAVE10` → 200 DISCOUNTED.
- `GET /shipping/tier?subtotal=-1` → 400 JSON error.
- Thiếu query param required `subtotal` → Spring MVC binding trả 400.

Đây là một API demo, không có security, persistence hoặc money rounding contract. MockMvc tests xác nhận mapping/status/body; chúng không mở TCP server hoặc thay unit tests cho mọi điều kiện trong ShippingPolicy.

## 12. ShippingPolicyTest.java: 12 unit tests có assertions

Tạo `src/test/java/example/coverage/ShippingPolicyTest.java`:

```java
package example.coverage;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingPolicyTest {

    private final ShippingPolicy policy =
            new ShippingPolicy();

    @Test
    void rejectsNegativeSubtotal() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.classify(-1, false, null));

        assertEquals(
                "subtotal must not be negative",
                error.getMessage());
    }

    @Test
    void zeroSubtotalIsStandard() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(0, false, null));
    }

    @Test
    void justBelowFreeThresholdIsStandard() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(999, false, null));
    }

    @Test
    void exactlyFreeThresholdIsFree() {
        assertEquals(
                ShippingPolicy.Tier.FREE,
                policy.classify(1000, false, null));
    }

    @Test
    void justBelowVipThresholdIsNotFree() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(499, true, null));
    }

    @Test
    void exactlyVipThresholdIsFree() {
        assertEquals(
                ShippingPolicy.Tier.FREE,
                policy.classify(500, true, null));
    }

    @Test
    void nonVipDoesNotGetVipFreeTier() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(500, false, null));
    }

    @Test
    void couponJustBelowThresholdDoesNotDiscount() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(199, false, "SAVE10"));
    }

    @Test
    void couponAtThresholdDiscounts() {
        assertEquals(
                ShippingPolicy.Tier.DISCOUNTED,
                policy.classify(200, false, "SAVE10"));
    }

    @Test
    void invalidCouponDoesNotDiscount() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(200, false, "WRONG"));
    }

    @Test
    void nullCouponIsSafeAndDoesNotDiscount() {
        assertEquals(
                ShippingPolicy.Tier.STANDARD,
                policy.classify(200, false, null));
    }

    @Test
    void freeTierTakesPriorityOverCoupon() {
        assertEquals(
                ShippingPolicy.Tier.FREE,
                policy.classify(1000, true, "SAVE10"));
    }
}
```

**Có 12 JUnit test methods**. Không phải chỉ gọi 12 giá trị ngẫu nhiên để tăng tỷ lệ:

1. Negative input ném đúng IllegalArgumentException, không bị nuốt.
2. Subtotal 0 nằm ở normal path.
3. Subtotal 999 (ngay dưới free) phải STANDARD.
4. Subtotal 1000 (đúng ngưỡng) phải FREE.
5. VIP với subtotal 499 không được miễn phí.
6. VIP với subtotal 500 được miễn phí.
7. Non-VIP với subtotal 500 không được áp rule VIP.
8. Coupon đúng ở subtotal 199 không được discount.
9. Coupon đúng ở 200 được discount.
10. Coupon sai ở 200 không được discount.
11. Null coupon không NPE và không discount.
12. FREE và coupon cùng match → FREE phải thắng.

**Điểm then chốt:** Expected được xác định theo **business rules**, không đọc trực tiếp từ một lần gọi method giống hệt. Việc assert message của exception cũng giúp phân biệt bug NPE với expected validation.

## 13. ShippingControllerTest.java: 5 MockMvc methods

Tạo `src/test/java/example/coverage/ShippingControllerTest.java`:

```java
package example.coverage;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ShippingController.class)
@Import(PolicyConfiguration.class)
class ShippingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void freeThresholdReturns200() throws Exception {
        mvc.perform(get("/shipping/tier")
                        .param("subtotal", "1000"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tier").value("FREE"));
    }

    @Test
    void vipThresholdReturnsFree() throws Exception {
        mvc.perform(get("/shipping/tier")
                        .param("subtotal", "500")
                        .param("vip", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tier").value("FREE"));
    }

    @Test
    void couponReturnsDiscounted() throws Exception {
        mvc.perform(get("/shipping/tier")
                        .param("subtotal", "200")
                        .param("coupon", "SAVE10"))
                .andExpect(status().isOk())
                .andExpect(
                        jsonPath("$.tier").value("DISCOUNTED"));
    }

    @Test
    void negativeSubtotalReturns400() throws Exception {
        mvc.perform(get("/shipping/tier")
                        .param("subtotal", "-1"))
                .andExpect(status().isBadRequest())
                .andExpect(
                        jsonPath("$.error").value(
                                "invalid subtotal"));
    }

    @Test
    void missingSubtotalFailsBinding() throws Exception {
        mvc.perform(get("/shipping/tier"))
                .andExpect(status().isBadRequest());
    }
}
```

**Có 5 MockMvc JUnit methods.** `@WebMvcTest(ShippingController.class)` dựng MVC slice; `@Import(PolicyConfiguration.class)` cung cấp policy bean thật. Spring Boot MVC slice bao gồm những MVC-related components như `@ControllerAdvice` trong app package, nên error advice cho subtotal âm được kiểm tra.

MVC test đo serialization, route/query binding, status và JSON. Nó không chứng minh network socket, app security, DB hoặc toàn bộ Spring Boot context. Khi một controller test mock policy, coverage của policy logic không đến từ test đó; ở bài này dùng real policy để xem rõ đường đi xuyên lớp.

## 14. Tóm tắt số test methods và phạm vi

| Class | Methods | Mục tiêu |
| --- | ---: | --- |
| `ShippingPolicyTest` | 12 | Ấn định ngưỡng, boolean, coupon, null, exception, precedence |
| `ShippingControllerTest` | 5 | HTTP binding/status/JSON |
| **Tổng** | **17** | |

**17 methods không đồng nghĩa 17 branches**. Một test method có thể thực thi nhiều bytecode branches; một `@ParameterizedTest` có thể chạy nhiều invocations; constructor/auto-config cũng có bytecode riêng. JaCoCo report sau khi chạy mới cho biết numerator/denominator thật, không tự nội suy số % từ bảng method count.

## 15. ShippingPolicyDemo.java: ví dụ Java SE chạy được

Tạo `src/main/java/example/coverage/ShippingPolicyDemo.java`:

```java
package example.coverage;

public class ShippingPolicyDemo {
    public static void main(String[] args) {
        ShippingPolicy policy = new ShippingPolicy();

        System.out.println(
                "free=" + policy.classify(
                        1000, false, null));
        System.out.println(
                "vip=" + policy.classify(
                        500, true, null));
        System.out.println(
                "coupon=" + policy.classify(
                        200, false, "SAVE10"));
        System.out.println(
                "normal=" + policy.classify(
                        999, false, null));
    }
}
```

Chạy bằng JDK 17+ từ project root, không cần Gradle/Spring:

```bash
javac -d out src/main/java/example/coverage/ShippingPolicy.java src/main/java/example/coverage/ShippingPolicyDemo.java
java -cp out example.coverage.ShippingPolicyDemo
```

Stdout **chính xác**:

```text
free=FREE
vip=FREE
coupon=DISCOUNTED
normal=STANDARD
```

**Không nhầm:** đây là Java SE demo, không tự bật JaCoCo agent; chạy `javac/java` theo lệnh trên **không tạo `test.exec`, HTML/XML coverage report**. Muốn đo coverage thì chạy Gradle test với JaCoCo plugin.

## 16. Chạy JaCoCo tasks với Gradle

Linux/macOS:

```bash
./gradlew clean test jacocoTestReport jacocoTestCoverageVerification
./gradlew clean check
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test jacocoTestReport jacocoTestCoverageVerification
.\gradlew.bat clean check
```

Dạng CI:

```bash
./gradlew --no-daemon clean check jacocoTestReport
```

**Kỳ vọng khi tasks chạy thành công, theo mặc định của project demo:**

| Đường dẫn/task | Ý nghĩa |
| --- | --- |
| `build/jacoco/test.exec` | Binary execution data của JaCoCo test agent |
| `build/reports/jacoco/test/html/index.html` | Human-readable HTML report |
| `build/reports/jacoco/test/jacocoTestReport.xml` | XML report cho CI tooling |
| `jacocoTestCoverageVerification` | Build FAIL nếu rule vi phạm |
| `check` | Lifecycle quality check, đã dependsOn verification |
| `test` | JUnit + MockMvc assertions |

**Không khẳng định stdout Gradle cố định**: console phụ thuộc version/task cache/reporting và môi trường. Những đường dẫn có thể thay đổi nếu build config đặt reportsDirectory khác hoặc sử dụng custom test suite. Không có Docker/database/service bên ngoài trong ví dụ.

Nếu `test` fail, `finalizedBy jacocoTestReport` có thể vẫn chạy để tạo artifact debug; **pipeline phải giữ trạng thái fail**. Report không làm test xanh giả.

## 17. Cách đọc JaCoCo HTML

Mở `build/reports/jacoco/test/html/index.html`, chọn package `example.coverage`, class `ShippingPolicy` rồi source view:

- Dòng **đỏ** có thể là path chưa chạy, chẳng hạn `throw IllegalArgumentException` nếu chưa test âm.
- Dòng **vàng** cho thấy một phần instructions trên dòng đã chạy; với `if` nhiều operands có thể thiếu short-circuit path.
- Dòng **xanh** biểu thị instructions của dòng được thực thi, nhưng **không chứng minh assertion đúng**.
- Diamond nhánh **đỏ/vàng/xanh** tại quyết định cho biết mức độ covered của branches (if/switch).

**Quy trình từ report đến test:**

1. Xem class/package bị thiếu counter nào, xác định source line có risk thật.
2. Đọc điều kiện, lập truth table/ngưỡng.
3. Chọn input đi vào nhánh chưa có.
4. Viết assertion expected từ yêu cầu nghiệp vụ.
5. Kiểm tra negative paths/side effects nếu có.
6. Chạy Gradle test + report lại, xem counters và test kết quả.
7. Duyệt code review để xác nhận vừa tăng coverage **vừa tăng khả năng bắt bug**.

JaCoCo source highlighting cần line number debug info trong class files. Khi class compiled không chứa mapping dòng, instruction/branch vẫn có thể được đo mà HTML source highlighting/LINE không giống dự kiến.

## 18. XML report trong CI

Một đoạn XML **minh họa**, không phải output đã đo từ project:

```xml
<counter type="LINE" missed="2" covered="18"/>
<counter type="BRANCH" missed="3" covered="9"/>
```

JaCoCo XML chứa counters ở các scope report/package/class/method phù hợp. Khi analyzer cần import, đặt path đúng và bảo đảm report được tạo sau test execution. Với SonarScanner/SonarQube đã cấu hình, có thể dùng:

```properties
sonar.coverage.jacoco.xmlReportPaths=build/reports/jacoco/test/jacocoTestReport.xml
```

**Đây là thuộc tính analyzer**, không tự được Spring Boot hay JaCoCo Gradle plugin đọc như application configuration. Multi-module cần cân nhắc relative path từ module/analyzer working directory, cùng class files và execution data hợp lệ.

CI nên upload JUnit XML và JaCoCo HTML/XML, kể cả khi tests/gate fail nếu provider có “always upload artifacts”, nhưng **không** nuốt exit code bằng `|| true` hoặc bật `continue-on-error` cho gate bắt buộc.

## 19. Coverage gate: CLASS, PACKAGE, BUNDLE

Một rule với `element='BUNDLE'` áp cho toàn bộ mã mà task report/verification biết, dễ đọc nhưng có thể bị code cũ covered cao che class mới chưa test. Rule với `element='CLASS'` và includes `example.coverage.ShippingPolicy` bảo vệ một class critical tốt hơn; nếu nhiều classes quan trọng, thêm PACKAGE/CLASS rules có lý do và dùng pipeline report diff coverage.

Rule của bài:

```groovy
rule {
    element = 'CLASS'
    includes = ['example.coverage.ShippingPolicy']

    limit {
        counter = 'LINE'
        value = 'COVEREDRATIO'
        minimum = 0.90
    }

    limit {
        counter = 'BRANCH'
        value = 'COVEREDRATIO'
        minimum = 0.80
    }
}
```

Ngưỡng **ví dụ**, không phải industry standard. Trong project thật, đo baseline trước, chọn critical path, thêm tests có assertions rồi mới tăng threshold. Không đặt gate không thực thi hoặc excludes quá rộng chỉ để có con số đẹp.

## 20. Weak test vs strong assertion

Anti-pattern:

```java
@Test
void weakTest() {
    ShippingPolicy policy = new ShippingPolicy();
    policy.classify(1000, false, null);
    policy.classify(500, true, null);
    policy.classify(200, false, "SAVE10");
}
```

Đây chỉ là snippet cần JUnit imports. Nó chạy code nhưng không kiểm tra output. Một implementation sai luôn trả STANDARD cũng có thể làm test pass. JaCoCo không đo chất lượng assertions.

Test mạnh phải assert output cụ thể:

```java
assertEquals(
        ShippingPolicy.Tier.FREE,
        policy.classify(1000, false, null));
```

Đừng lấy expected từ chính method đang test:

```java
ShippingPolicy.Tier expected =
        policy.classify(1000, false, null);
assertEquals(
        expected, policy.classify(1000, false, null));
```

Nếu bug ổn định, expected/actual sai giống nhau và test pass. Expected nên đến từ business truth table/requirements hoặc một oracle độc lập, không từ implementation.

`assertDoesNotThrow(...)` kiểm tra exception contract, **không** chứng minh return value FREE/DISCOUNTED/STANDARD đúng. Với rule ngưỡng, assert đúng enum và boundary; với network side effects, verify caller interactions và lỗi/cleanup.

## 21. Mutation testing: điều kiện nào thực sự được bảo vệ?

Mutation testing (ví dụ PIT) cố ý sửa bytecode/source behavior và chạy tests để xem mutant có bị “kill” hay sống.

| Mutant giả định | Test nào nên fail? |
| --- | --- |
| `>= 1000` đổi thành `> 1000` | `exactlyFreeThresholdIsFree()` |
| `>= 500` đổi thành `> 500` | `exactlyVipThresholdIsFree()` |
| `>= 200` đổi thành `> 200` | `couponAtThresholdDiscounts()` |
| Bỏ điều kiện `vip` | `nonVipDoesNotGetVipFreeTier()` |
| Bỏ check coupon | `invalidCouponDoesNotDiscount()` |
| `return FREE` đổi thành STANDARD | Các FREE assertions |
| `return DISCOUNTED` đổi thành STANDARD | Coupon assertion |
| Bỏ guard subtotal âm | `rejectsNegativeSubtotal()` |
| Cho coupon ưu tiên FREE | `freeTierTakesPriorityOverCoupon()` |

Khi mutant survived, reviewer nên tìm missing input hoặc weak assertion. Có mutants tương đương và giới hạn của mutation tooling nên mutation score cũng không phải bảo chứng tuyệt đối. **Project không cài PIT**; đây là phương pháp bổ sung nên cấu hình và chạy riêng nếu team cần, không khẳng định mutations đã được test trong bài.

Ví dụ giúp thấy: hai tests với subtotal 900/1200 có thể đạt true/false branch, nhưng mutant `>=1000` thành `>1000` vẫn sống nếu không có case **1000**. Boundary assertions bảo vệ requirement tốt hơn chỉ tối ưu branch ratio.

## 22. Branch 100% vẫn có thể bỏ sót exception handling

Một snippet:

```java
try {
    return repository.load(id);
} catch (IOException error) {
    return cachedCopy(id);
}
```

Trong JaCoCo, `catch` không phải BRANCH của `if/switch` theo C1 counter. Do đó cần tests riêng cho:

- IOException/HTTP timeout và mapping 503.
- Missing object vs backend unavailable.
- Resource close trong finally/try-with-resources.
- Rollback transaction và side effects.
- Interrupt/cancellation.
- Invalid validation input, security forbidden/unauthorized.
- Fallback cache stale/tenant permissions.
- Retry idempotency.

Một method có 100% BRANCH không chứng minh những contract ấy. Có thể dùng unit test fault injection, MockMvc assertions hoặc Testcontainers/protocol integration tùy lớp code, thay vì suy luận từ JaCoCo.

## 23. Spring context startup có thể tạo coverage “giả an tâm”

`@SpringBootTest` khởi động nhiều Spring beans, constructors/config methods. Những instructions đó có thể được ghi covered **dù test chưa assert hành vi thật**. Một `@WebMvcTest` chỉ dựng MVC slice; các services/repositories không import có thể không covered. Nếu controller test chỉ mock ShippingPolicy, nó không đo business branches.

Với demo, `@Import(PolicyConfiguration.class)` tạo policy bean thật trong MVC slice để các HTTP test có thể gọi class đó, còn 12 JUnit pure tests bảo vệ các business conditions.

| Mục tiêu | Cấp test phù hợp |
| --- | --- |
| Rule Java thuần | JUnit không Spring |
| MVC mapping/binding/error response | `@WebMvcTest` + MockMvc |
| SQL constraints/queries | `@DataJpaTest`/`@DataJdbcTest` |
| Auto-config conditions | `ApplicationContextRunner` |
| Full Spring bean graph | `@SpringBootTest` |
| External HTTP timeout/error | Test HTTP server/WireMock/Testcontainers |

**Coverage không nên thúc ép người viết biến mọi unit test thành full integration test** chỉ để chạy nhiều constructors. Một test mạnh là đúng tầng, nhanh, có assertions rõ và phát hiện bug cụ thể.

## 24. Multi-module và nhiều test suites

Gradle JaCoCo mặc định tạo `jacocoTestReport` gắn với task `test`. Nếu module có `integrationTest` task riêng, **không tự giả định** report mặc định đã cộng data từ task đó.

- Mỗi JVM Test task có thể tạo execution data riêng.
- Custom JacocoReport có thể nhận data của nhiều test tasks; cần `dependsOn` để thực sự chạy chúng trước khi tổng hợp.
- Gradle cung cấp JaCoCo Report Aggregation plugin cho một số mô hình JVM test suites/multi-project.
- Đảm bảo execution data phù hợp compiled classes; dùng class files khác version có thể khiến report lỗi/sai.
- Process chạy app ngoài test JVM (Docker server/another Java process) **không tự được agent của Gradle test JVM đo**.
- Parallel Gradle forks, test distribution, build cache cần kế hoạch thu thập data rõ; đừng dùng file exec stale.
- Không dựa vào các tutorial `JacocoMerge` quá cũ mà không kiểm tra Gradle version hiện tại.

**Một test integration có tồn tại không đồng nghĩa coverage integration đã đi vào report**; phải xác minh task graph và report inputs.

## 25. Coverage exclusions có thể làm sai lệch mục tiêu

Trong dự án lớn có generated code: DTOs từ OpenAPI, protobuf, compiler boilerplate. JaCoCo có một số filters nhưng không tự nhận biết mọi dạng generated code. Nếu có lý do loại trừ, cấu hình `classDirectories`/report scope đồng bộ với verification và tools nhập XML, và document rõ.

Không nên loại trừ:

- Những services/controllers khó test.
- Điều kiện authorization.
- Transaction error handlers.
- Validation branches.
- Code mới chưa kịp viết tests.
- Toàn package chỉ vì coverage thấp.

Nếu report loại trừ class nhưng verification vẫn tính, hai chỉ số lệch; nếu gate loại trừ business code để pass, quality gate bị vô hiệu. Exclusions phải thể hiện quyết định kiến trúc/ownership được review, không phải sửa metric.

## 26. CI pipeline và artifacts

```text
checkout + setup JDK17/Gradle
          |
          v
./gradlew --no-daemon clean check jacocoTestReport
          |
          +-- JUnit assertions
          +-- JaCoCo execution data
          +-- Coverage verification (LINE/BRANCH)
          +-- HTML/XML report
          |
          v
success -> review missing branches/new code
failure -> job stays FAILED, collect reports/logs
```

Artifacts nên giữ JUnit XML, JaCoCo HTML, JaCoCo XML và build logs theo quyền truy cập repository. Khi job fail, có thể upload artifacts bằng step điều kiện "always", nhưng **không** nuốt lỗi `./gradlew check || true` hay `continue-on-error` nếu gate bắt buộc.

CI quality gate cần đi đôi với code review. Nếu threshold xanh nhưng bug trong auth/pricing/tenant leak vẫn chưa được kiểm tra, reviewer phải thêm tests, không dùng coverage làm biện hộ.

## 27. Lỗi thường gặp

**1. Không thấy report:** task `jacocoTestReport` chưa chạy, `test` không chạy, chưa bật plugin, đường dẫn output được chỉnh hoặc exec data không có.

**2. check không fail:** quên `check.dependsOn jacocoTestCoverageVerification`, rule includes không match hoặc task bị skip.

**3. Branch partial dù if đã test true/false:** short-circuit operands chưa đủ cases; đọc report và truth table.

**4. Catch line đỏ dù BRANCH cao:** exception handler không là BRANCH counter; viết failure test.

**5. Coverage tăng nhờ startup:** @SpringBootTest đã chạy constructors, không thay thế business assertions.

**6. Controller test xanh còn policy coverage 0:** policy đã mock, hoặc test slice không import bean thật.

**7. XML được tạo nhưng Sonar hiển thị 0:** path/analyzer module/scope không đúng hoặc chưa upload.

**8. Report bị duplicate class name:** aggregated class files khác modules/versions đè nhau.

**9. Agent không hỗ trợ JDK:** JaCoCo version quá cũ; nâng đúng compatibility thay vì tắt coverage.

**10. Tỉ lệ quá cao sau exclude:** review filter và code quan trọng đã bị ẩn hay chưa.

**11. Local khác CI:** JDK/Gradle versions, test filtering, skipped tests, forks, cached data và compiled classes khác nhau.

**12. Coverage thấp ở một nhánh không thể xảy ra:** xem code có dead condition/invariant thay vì tạo test bất hợp pháp để tăng điểm.

**13. Report không có line info:** class files thiếu debug line-number mapping; instruction/branch có thể vẫn tính.

**14. Chỉ kiểm tra tỷ lệ bundle:** service mới rủi ro cao có thể không test, nhưng code cũ covered nhiều làm threshold vẫn pass.

## 28. Checklist QA cuối bài

**Coverage fundamentals:** phân biệt LINE, BRANCH, INSTRUCTION, COMPLEXITY? Hiểu line partial? Hiểu branch if/switch không gồm catch? Không coi 100% branch là MC/DC hoặc business correctness?

**Business tests:** Có test 999/1000, 499/500 VIP, 500 non-VIP, coupon 199/200, coupon sai/null, subtotal âm và priority FREE? Expected có độc lập với implementation? Mỗi test kiểm tra exact Tier/exception?

**Spring MVC:** Controller có đúng route/params? MVC slice import real ShippingPolicy bean? HTTP 200/400 và JSON được assert? Không coi MockMvc là external network test?

**Gradle/JaCoCo:** `id 'jacoco'`, useJUnitPlatform, report XML/HTML, `jacocoTestReport.dependsOn test`, `jacocoTestCoverageVerification.dependsOn test` và `check.dependsOn verification` đã có? Counter LINE/BRANCH dùng COVEREDRATIO? Includes đúng class? Tool version tương thích JDK?

**CI:** Report path thực, JUnit XML/HTML/XML được lưu? Multi-module/integration data được gộp đúng khi cần? Excludes có tài liệu và không che critical code? Exit code fail không bị nuốt? Có review boundary tests/mutants?

**Kết luận:** JaCoCo giúp phát hiện đường bytecode chưa được chạy và bảo vệ một mức coverage tối thiểu trong Build/CI. **LINE** chỉ số dòng có code đã chạy, **BRANCH** chỉ số kết quả điều kiện bytecode được thực thi; nhưng **chất lượng kiểm chứng** đến từ truth table, boundary cases, assertions, negative paths và khả năng test phát hiện implementation sai. Hãy dùng coverage report để tìm khoảng trống, không coi một phần trăm đẹp là sự đảm bảo chính xác.

## 29. Tài liệu tham khảo

- [JaCoCo — Coverage Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html): INSTRUCTION, LINE, BRANCH, COMPLEXITY và exception limitation.
- [JaCoCo — FAQ](https://www.jacoco.org/jacoco/trunk/doc/faq.html): probes, line-number metadata, class mismatch.
- [Gradle — JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html): report/verification tasks và task dependencies.
- [Gradle — JacocoCoverageVerification](https://docs.gradle.org/current/dsl/org.gradle.testing.jacoco.tasks.JacocoCoverageVerification.html): threshold rules.
- [Gradle — JacocoViolationRule API](https://docs.gradle.org/current/javadoc/org/gradle/testing/jacoco/tasks/rules/JacocoViolationRule.html): scope and includes.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): JUnit, MockMvc, @WebMvcTest.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): import configuration into MVC slices.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions và test lifecycle.
- [PIT — Mutation Testing](https://pitest.org/): bổ sung đánh giá độ mạnh của tests.
