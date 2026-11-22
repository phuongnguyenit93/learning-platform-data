# JUnit tag, Gradle test filter và task kiểm thử theo nhóm trong Spring Boot

## 1. Vì sao cần phân nhóm kiểm thử?

Một dự án Spring Boot có thể có kiểm thử thuần Java chạy dưới một giây, kiểm thử Spring context cần vài giây, kiểm thử kết nối database/Kafka cần container thật và kiểm thử smoke chỉ cần biết một phiên bản ứng dụng có thể khởi động. Nếu mọi test nằm trong một Gradle `test` task không phân biệt nhóm, người phát triển phải chờ nhiều tài nguyên không cần thiết khi chỉ sửa logic nhỏ; ngược lại, nếu CI bỏ qua test chậm một cách tùy tiện, lỗi tích hợp có thể lọt vào nhánh chính.

**JUnit Jupiter `@Tag`** gắn nhãn cho test class hoặc method. **Gradle `Test.useJUnitPlatform { includeTags/excludeTags }`** chọn nhãn nào được chạy trong một task. **Gradle `--tests` hoặc `Test.filter.includeTestsMatching`** lọc theo tên class/method, **không phải nhãn**. **Các Gradle `Test` tasks** như `test`, `integrationTest`, `slowIntegrationTest` và `smokeTest` tạo những nhóm lệnh có chính sách độc lập cho local/PR/nightly/release.

Mục tiêu bài học:
1. Gắn và giải thích `@Tag("unit")`, `@Tag("integration")`, `@Tag("slow")`, `@Tag("smoke")` đúng ngữ nghĩa.
2. Phân biệt **tag filtering**, **test name filtering**, **file/class patterns**, **JUnit Platform engines** và **task selection**.
3. Hiểu cú pháp **tag expression** `&`, `|`, `!` và dấu ngoặc; cùng hành vi tag ở class/method.
4. Cấu hình Gradle Groovy DSL cho các task kiểm thử có cùng test source set nhưng bộ lọc không chồng lấn.
5. Xác định rõ `check` tự chạy nhóm nào và nhóm nào **chỉ chạy khi được chỉ định**.
6. Tránh bẫy `--tests` không vượt qua được `includeTags`, test bị lọc không phải test đã pass, hoặc untagged tests bị bỏ quên.
7. Thiết kế CI matrix, caching, reports, resource isolation và retry/flake triage cho nhóm test.
8. Có project Java 17+, Spring Boot 3.5.x, Gradle và JUnit Jupiter với code nhất quán, ví dụ command tương ứng từng nhóm, các asserts thật.

**Phạm vi:** Bài tập trung vào **tổ chức/selection/execution policy**, không cố thay thế toàn bộ `@SpringBootTest`/Testcontainers hoặc unit testing methodology. Mẫu dùng Spring Boot 3.5.8, Java 17+, Gradle Groovy DSL, JUnit Jupiter và AssertJ; không cần Docker hoặc dịch vụ ngoài. Nhóm `slow` được dùng để minh họa policy “chạy mở rộng”, không sử dụng `Thread.sleep` nhân tạo.

## 2. Bốn tầng cần phân biệt

```text
                 Developer hoặc CI
                         |
    ./gradlew check / integrationTest / smokeTest
                         |
                         v
                Gradle TASK GRAPH
                  +-----------+
                  | test      |  includeTags("unit")
                  |           |
                  | integrationTest |  includeTags("integration & !slow")
                  |           |
                  | slowIntegrationTest | includeTags("integration & slow")
                  |           |
                  | smokeTest | includeTags("smoke")
                  +-----------+
                         |
                         v
               TEST JVM / JUNIT PLATFORM
                 |              |
           Class/method       Tag expression
           name filters      include/exclude
                 |              |
                 +------ AND ----+
                         |
                         v
                 Selected tests
                         |
                  Executed / failed /
                    skipped / passed
```

Sơ đồ `AND` nhấn mạnh rằng filter theo tên và filter theo tag **cùng giới hạn tập test được chạy**; `--tests` không phải công tắc bỏ qua tag conditions của một `Test` task đã định nghĩa.

### 2.1. So sánh nhanh

| Khái niệm | Ví dụ | Chọn cái gì? | Không phải là... |
|---|---|---|---|
| JUnit tag | `@Tag("integration")` | Metadata trên test container/method | Một lệnh chạy test |
| JUnit tag expression | `integration & !slow` | Tests có integration nhưng không slow | Bộ lọc theo file name |
| Gradle JUnit filter | `useJUnitPlatform { includeTags 'unit' }` | Tests của task phù hợp tag | `--tests` |
| Gradle test name filter | `--tests "*CalculatorTest"` | Class/method có tên match | Nhãn unit |
| Gradle Test.filter | `includeTestsMatching("*CatalogTest")` | Tên class/method (pattern) | Tag expression |
| Gradle class file include | `include '**/*Test.class'` | File tests được scan | Chọn method qua `@Tag` |
| Gradle task selection | `./gradlew integrationTest` | Task được chạy | Ngầm chạy tất cả tests |
| `check` dependencies | `check.dependsOn integrationTest` | Task được đưa vào verification lifecycle | Tự động bao gồm mọi custom Test task |
| `maxParallelForks` | `2` | Số forked test JVM tối đa cho task | Số lượng tag |
| JUnit `@Disabled` | `@Disabled("reason")` | Bỏ thực thi test đã discover | Tương đương tag filter |

`@Tag` không tự làm test chậm/nhanh, không thay đổi lifecycle hay test engine, và không phải dấu hiệu test đã pass. Nó là **metadata để chọn ca phù hợp với policy build**.

## 3. JUnit Jupiter @Tag: gắn nhãn vào đâu?

### 3.1. Gắn nhãn vào test class

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("unit")
class MathRulesTest {

    @Test
    void shouldCalculateTax() {
        // Một JUnit test thuộc nhóm unit.
    }
}
```

Đây là fragment minh họa; body chưa có assertion nên **không phải chương trình test đáng dùng độc lập**. Khi class có `@Tag("unit")`, các test methods được discover trong class có tag đó trong JUnit Platform discovery/execution model.

Thực tế nên đặt tag ở **class** nếu toàn bộ class có một mức kiểm thử thống nhất. Điều này giúp reviewer thấy nhanh file nào thuộc unit/integration/smoke.

### 3.2. Gắn nhãn vào method

```java
@Tag("integration")
class CatalogIntegrationTest {

    @Test
    void quickRepositoryContract() {
        // Chạy trong nhóm integration.
    }

    @Test
    @Tag("slow")
    void fullValidationMatrix() {
        // Có CẢ "integration" (từ class)
        // VÀ "slow" (từ method).
    }
}
```

Fragment này minh họa **tag kế thừa theo hierarchy container → method**. Method `fullValidationMatrix` mang **cả hai tags**, vì thế:
- `integration & !slow` chọn `quickRepositoryContract`.
- `integration & slow` chọn `fullValidationMatrix`.
- `slow` cũng chọn `fullValidationMatrix`.
- `unit` không chọn method nào ở đây.

Tag ở method **bổ sung**, không “xóa” tag ở class. Không dùng `@Tag("slow")` trên cả class nếu mục tiêu chỉ một method slow, trừ khi muốn mọi methods của class đều được xem là slow.

### 3.3. Một class nhiều tags

```java
@Tag("integration")
@Tag("database")
class ProductRepositoryTest {
    // Mọi test ở đây mang hai tags integration và database.
}
```

Đây là fragment, chưa khai báo các test methods. `@Tag` là repeatable; có thể dùng nhiều annotation trên một class/method. Hai trục `integration` (test level) và `database` (resource/category) giúp CI chọn đúng nhóm theo điều kiện.

**Quy ước có giá trị:** Dùng một trục rõ ràng cho loại test (`unit`, `integration`, `smoke`) và trục khác cho thuộc tính (`slow`, `database`, `external`, `nightly`). Nếu mỗi team tự đặt `int`, `integ`, `IT`, `integration-test` theo cảm tính, tag filters sẽ bỏ sót test.

### 3.4. Tag không phải string tùy ý

JUnit yêu cầu tag không rỗng, không chứa whitespace, control characters hoặc các ký tự được dùng làm cú pháp tag expression như `,`, `(`, `)`, `&`, `|`, `!`. Dùng:
- `unit`, `integration`, `slow`, `smoke`, `postgres`, `api-v2`.
- Tránh `"integration test"`, `"slow,network"`, `"unit|integration"`.

Trong tag expression, toán tử `|` biểu thị **OR**, `&` biểu thị **AND**, `!` biểu thị **NOT**. Đó là cú pháp **lọc**, không phải nội dung một tag.

## 4. Cú pháp tag expressions

JUnit Platform có grammar gồm:
- `!`: phủ định tag.
- `&`: giao/AND.
- `|`: hợp/OR.
- `(` và `)`: nhóm để thay đổi thứ tự ưu tiên.

**Ưu tiên thường gặp:** `!` mạnh hơn `&`, rồi đến `|`. Nên dùng ngoặc khi expression có từ hai toán tử để người đọc và CI reviewer không phải tự suy diễn.

| Tag expression | Ý nghĩa |
|---|---|
| `unit` | Chọn các tests mang tag unit |
| `integration` | Chọn các tests mang tag integration |
| `smoke` | Chọn smoke tests |
| `unit | smoke` | Unit **hoặc** smoke |
| `integration & !slow` | Integration **và không slow** |
| `integration & slow` | Vừa integration vừa slow |
| `(integration | smoke) & !external` | Integration hoặc smoke, nhưng không cần external |
| `!slow` | Các tests không được gắn tag slow |
| `database & integration` | Integration cần database |
| `unit & integration` | Tests mang cả hai tags, thường là mùi classification sai nếu policy yêu cầu loại test độc quyền |

**Bẫy của `!slow`:** Nó cũng có thể chọn **test không có tag nào** nếu không bị filter khác loại. Vì vậy `includeTags 'unit'` chính xác hơn `excludeTags 'slow'` khi PR pipeline chỉ được chạy **các test đã được phân loại unit**.

### 4.1. Một `includeTags` có thể chứa tag expression

Gradle hỗ trợ thông qua JUnit Platform:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'integration & !slow'
    }
}
```

Đây là fragment cấu hình Gradle. JUnit Platform parse chuỗi `integration & !slow` thành expression; nó không phải một tag literal có dấu cách.

Đối với nhiều expressions:

```groovy
useJUnitPlatform {
    includeTags 'unit', 'smoke & !external'
}
```

Trong Gradle/JUnit Platform, nhiều include expressions có semantics chọn các tests phù hợp một trong các biểu thức. Cách ghi một expression rõ ràng `'unit | (smoke & !external)'` thường dễ review hơn khi policy phức tạp. Dùng `excludeTags` để loại một tập như `slow`, nhưng nhớ rằng exclude có thể làm mất ca từ tập include nếu nó mang nhiều tags.

### 4.2. Tag inheritance không giống Java @Inherited cho mọi annotation

JUnit cung cấp semantics của tag khi class, nested class, interface hoặc method được discover trong test model. Không nên cố suy ra toàn bộ inheritance từ cú pháp Java annotations nói chung. Với meta-annotations/composed annotations, đọc JUnit docs và test một sample nhỏ khi project dùng custom annotations. Điều chắc chắn trong project bên dưới: `@Tag("integration")` trên test class và `@Tag("slow")` trên method khiến method có cả hai tags khi JUnit chọn test.

## 5. Gradle --tests lọc theo tên, không lọc theo tag

### 5.1. Gradle CLI --tests dùng khi debug class/method

```bash
./gradlew test --tests "com.example.groups.PriceCalculatorTest"
./gradlew test --tests "*PriceCalculatorTest.discountTenPercent"
```

`--tests` nhận pattern tên test class/method. Nó hữu ích khi chạy một ca lỗi từ IDE hoặc CI log mà không phải chạy toàn suite.

**Sai:** `./gradlew test --tests unit` không có nghĩa “chạy các tests có `@Tag("unit")`”. Gradle sẽ cố match **tên** phù hợp pattern `unit`, không phải tag. Với cấu hình `includeTags 'unit'`, muốn chạy toàn nhóm dùng `./gradlew test`.

### 5.2. --tests và includeTags kết hợp theo giao nhau

Giả sử:
- `test` task chỉ `includeTags 'unit'`.
- `CatalogServiceIntegrationTest` có `@Tag("integration")`.

Lệnh:

```bash
./gradlew test --tests "com.example.groups.CatalogServiceIntegrationTest"
```

**Không biến integration test thành unit test.** Class được chọn theo tên nhưng vẫn **không thỏa tag** của `test`. Tùy Gradle/JUnit version/filter state, kết quả có thể báo “No tests found for given includes” hoặc task không chạy ca nào. Lệnh đúng:

```bash
./gradlew integrationTest --tests "com.example.groups.CatalogServiceIntegrationTest"
```

Ngay cả lệnh thứ hai cũng chỉ chọn những methods thuộc `integration & !slow` do task cấu hình; muốn chạy method slow phải gọi `slowIntegrationTest --tests ...`.

**Quy tắc nhớ:** `--tests` giúp **thu hẹp trong nhóm task đã chọn**, không có quyền override các tag filter cố định của task.

### 5.3. Test.filter và includeTestsMatching

Có thể đặt name filter trong build script:

```groovy
tasks.named('test', Test) {
    filter {
        includeTestsMatching '*PriceCalculatorTest'
        excludeTestsMatching '*LegacyFlakyTest'
    }
}
```

Đây là fragment tùy chọn, **không** thêm vào build mẫu bên dưới. `includeTestsMatching` và `excludeTestsMatching` áp dụng theo class/method names. Cả `filter` lẫn `--tests` không phải một trình parser tag expression.

**Bẫy:** Nếu bạn thêm permanent `includeTestsMatching '*PriceCalculatorTest'` vào task unit, các unit classes khác có thể không bao giờ chạy dù có `@Tag("unit")`. Dùng name filter chủ yếu khi debug, convention chuyển tiếp hoặc một group thật sự được định nghĩa theo tên.

### 5.4. Gradle include/exclude file patterns khác TestFilter

```groovy
tasks.named('test', Test) {
    include '**/*Test.class'
}
```

Đây là fragment cho class file patterns (không phải test method/tag), liên quan tập file được scan. Không dùng `include '**/*IntegrationTest.class'` để thay thế JUnit tags trừ khi project có convention file naming rất rõ và cần duy trì nó. Tag expressions linh hoạt hơn cho `@ParameterizedTest`, `@Nested` và methods có nhiều tính chất.

### 5.5. JUnit Platform engine filtering

```groovy
useJUnitPlatform {
    includeEngines 'junit-jupiter'
}
```

Đoạn này chọn **test engine**, không phải tag hay name. Nó có ích nếu classpath còn có JUnit Vintage/Spock engine; nhưng `includeEngines 'junit-jupiter'` không thay cho `includeTags 'unit'`. Với Spring Boot 3.5 và JUnit Jupiter, ví dụ dự án bên dưới chỉ cần `useJUnitPlatform`.

## 6. Chính sách test groups đề xuất

Đối với một project Spring Boot vừa và nhỏ:

| Nhóm | Tag hoặc expression | Mục đích | Khi nào chạy |
|---|---|---|---|
| Unit | `unit` | Pure Java/logic không cần Spring context | Local/PR, `test` |
| Integration nhanh | `integration & !slow` | Spring DI, slice/full context nhẹ | PR, `integrationTest` |
| Integration mở rộng | `integration & slow` | Ma trận lớn, DB/Testcontainers, hợp đồng ngoài JVM | Nightly/chạy riêng, `slowIntegrationTest` |
| Smoke | `smoke` | Khởi động context, đường sống tối thiểu | Release/chạy riêng, `smokeTest` |

Hai đặc điểm nên làm rõ ngay từ đầu:
- `slow` ở đây **là nhãn chính sách**, không phải một profiler tự đo thời gian. Một method chỉ được đưa vào slow lane vì nhóm xác nhận nó không cần chạy trên mọi PR, không phải vì viết `Thread.sleep`.
- `smokeTest` trong demo là **application context startup smoke**, không phải synthetic HTTP check đến một deployment ngoài môi trường. Muốn smoke thật sau deploy cần endpoint/service đang chạy và bộ test riêng với environment rõ ràng.

### 6.1. Vì sao không chỉ exclude slow khỏi task test?

Nếu `test` chỉ `excludeTags 'slow'`, các integration/smoke tests không mang slow cũng có thể bị chạy mỗi khi developer dùng `./gradlew test`. Để bảo đảm unit lane đúng, dùng **positive selection** `includeTags 'unit'`. Khi tổ chức nhiều loại test, mỗi loại phải được tag rõ; **untagged tests sẽ không được chạy trong các task có includeTags** — đó là rủi ro cần có chính sách kiểm kê/test naming guard.

### 6.2. Quy tắc tránh chạy trùng

Một test mang `@Tag("integration")` và `@Tag("smoke")` có thể được chọn ở hai tasks nếu cả hai cùng include matching tags. Nếu mong các nhóm mutually exclusive, định nghĩa convention: mỗi class chỉ có **một test-level tag** `unit`/`integration`/`smoke`, còn modifiers như `slow` có thể bổ sung. Khi có kiểm thử vừa integration vừa smoke có chủ ý, chấp nhận chạy trùng hoặc dùng expressions loại trừ minh bạch.

Trong project mẫu:
- Unit tests chỉ `unit`.
- Integration class mang `integration`; một method bổ sung `slow`.
- Smoke class chỉ `smoke`.
- Task `integrationTest` chọn `integration & !slow`.
- Task `slowIntegrationTest` chọn `integration & slow`.

Các tập được thiết kế **không chồng lấn** trong ví dụ.

## 7. Dự án thực hành Java 17+ / Spring Boot 3.5.8

Cấu trúc đầy đủ:

```text
build.gradle
src/main/java/com/example/groups/
    CiGroupsApplication.java
    PriceCalculator.java
    Quote.java
    CatalogService.java
src/test/java/com/example/groups/
    PriceCalculatorTest.java
    CatalogServiceIntegrationTest.java
    ApplicationSmokeTest.java
```

Ba classes kiểm thử chứa tổng **8 JUnit Jupiter `@Test` methods**:
- 4 unit methods.
- 2 integration-fast methods.
- 1 integration-slow method.
- 1 smoke method.

Không có file `application.properties` bắt buộc, vì project không dùng datasource/web/external clients. `@SpringBootTest` khởi tạo non-web application context; không yêu cầu DB, Docker hoặc port cố định.

### 7.1. build.gradle (Groovy DSL) hoàn chỉnh

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

// Main 'test' task: chỉ unit tests.
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'unit'
    }
    maxParallelForks = 2
    testLogging {
        events 'failed', 'skipped'
    }
}

// Custom tasks dùng lại compiled classes của sourceSets.test.
def integrationTask = tasks.register('integrationTest', Test) {
    description = 'Run integration tests suitable for pull requests'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration & !slow'
    }
    maxParallelForks = 1
    mustRunAfter tasks.named('test')
}

def slowTask = tasks.register('slowIntegrationTest', Test) {
    description = 'Run extended integration tests on demand'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration & slow'
    }
    maxParallelForks = 1
    mustRunAfter integrationTask
}

def smokeTask = tasks.register('smokeTest', Test) {
    description = 'Run application-context smoke tests'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'smoke'
    }
    maxParallelForks = 1
    mustRunAfter integrationTask
}

// Gradle Java plugin đã cho check phụ thuộc test.
// Thêm integration-fast vào PR verification lifecycle.
tasks.named('check') {
    dependsOn integrationTask
}

// slowTask và smokeTask được đăng ký nhưng KHÔNG thêm vào check:
// CI nightly/release có thể gọi chúng riêng.
```

**Phân tích từng quyết định:**
- `useJUnitPlatform`: để Gradle chạy JUnit Jupiter tests qua JUnit Platform.
- `test` chỉ `includeTags 'unit'`: `./gradlew test` không chạy integration/smoke.
- Các task khác là `Test` **mới**, nhưng dùng **cùng compiled test classes** qua `sourceSets.test.output.classesDirs` và **cùng runtime classpath**. Đây là phần bắt buộc khi tự tạo một `Test` task; đừng nghĩ mọi Gradle version tự gán source set mặc định.
- `integrationTest` chỉ chạy `integration & !slow`.
- `slowIntegrationTest` chỉ chạy `integration & slow`.
- `smokeTest` chỉ chạy `smoke`.
- `check` chạy **test + integrationTest** theo dependencies; slow/smoke là opt-in.
- `mustRunAfter tasks.named('test')` chỉ điều khiển **thứ tự khi cả hai tasks đều được schedule**, không tự tạo dependency để bắt buộc chạy task trước khi bạn gọi `integrationTest` riêng.
- Gradle tạo report directories theo task name; ví dụ `build/reports/tests/test/`, `build/reports/tests/integrationTest/`, `build/reports/tests/slowIntegrationTest/`, `build/reports/tests/smokeTest/`.

`maxParallelForks` là số test **JVM processes**, không phải số JUnit threads, và chịu giới hạn từ `--max-workers`. Nó **không ảnh hưởng tag selection**. Với Spring context integration/smoke, giữ một fork trong ví dụ để đơn giản; production có thể tăng sau khi kiểm chứng tài nguyên được cô lập.

### 7.2. CiGroupsApplication.java

Tệp `src/main/java/com/example/groups/CiGroupsApplication.java`:

```java
package com.example.groups;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CiGroupsApplication {

    public static void main(String[] args) {
        SpringApplication.run(CiGroupsApplication.class, args);
    }
}
```

Main class phục vụ `@SpringBootTest` discovery trong package `com.example.groups`. Do không có web starter, sample khởi tạo Spring context **không mở HTTP server**.

### 7.3. PriceCalculator.java: domain logic không cần Spring

Tệp `src/main/java/com/example/groups/PriceCalculator.java`:

```java
package com.example.groups;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

import org.springframework.stereotype.Component;

@Component
public class PriceCalculator {

    public BigDecimal afterDiscount(
            BigDecimal price, int percent) {

        Objects.requireNonNull(price, "price");

        if (price.signum() < 0) {
            throw new IllegalArgumentException(
                    "price must not be negative");
        }
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "percent must be between 0 and 100");
        }

        return price.multiply(
                BigDecimal.valueOf(100 - percent))
            .divide(BigDecimal.valueOf(100),
                2, RoundingMode.HALF_UP);
    }
}
```

Lớp được `@Component` để Spring integration test có thể inject, nhưng unit test vẫn **khởi tạo trực tiếp bằng `new PriceCalculator()`**; không phải bootstrap `ApplicationContext` chỉ để test một phép tính. `BigDecimal` giúp tránh float rounding bất định.

### 7.4. Quote.java: immutable result

Tệp `src/main/java/com/example/groups/Quote.java`:

```java
package com.example.groups;

import java.math.BigDecimal;

public record Quote(
        String sku,
        BigDecimal payableAmount) {
}
```

Dùng Java record để test dễ assert kết quả, không cần JPA `@Entity` hay Jackson serialization. Dự án chỉ học cách chọn test groups, không phụ thuộc persistence infrastructure.

### 7.5. CatalogService.java: Spring DI integration

Tệp `src/main/java/com/example/groups/CatalogService.java`:

```java
package com.example.groups;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final PriceCalculator calculator;

    public CatalogService(PriceCalculator calculator) {
        this.calculator =
                Objects.requireNonNull(calculator);
    }

    public Quote quote(String sku,
            BigDecimal listPrice,
            int discountPercent) {

        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank");
        }

        BigDecimal amount = calculator.afterDiscount(
                listPrice, discountPercent);

        return new Quote(sku, amount);
    }
}
```

Đây là service **stateless** được Spring inject. `@SpringBootTest` sẽ kiểm tra Spring tạo bean và wiring constructor. Unit test của `PriceCalculator` không cần Spring; tách nhóm giúp developer chọn đúng thời gian phản hồi.

## 8. Ba lớp JUnit hoàn chỉnh

### 8.1. PriceCalculatorTest.java: bốn ca unit

Tệp `src/test/java/com/example/groups/PriceCalculatorTest.java`:

```java
package com.example.groups;

import java.math.BigDecimal;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("unit")
class PriceCalculatorTest {

    private final PriceCalculator calculator =
            new PriceCalculator();

    @Test
    void discountTenPercent() {
        BigDecimal result = calculator.afterDiscount(
                new BigDecimal("100.00"), 10);

        assertThat(result)
                .isEqualByComparingTo("90.00");
    }

    @Test
    void discountWithHalfUpRounding() {
        BigDecimal result = calculator.afterDiscount(
                new BigDecimal("99.99"), 25);

        assertThat(result)
                .isEqualByComparingTo("74.99");
    }

    @Test
    void rejectsNegativePrice() {
        assertThatThrownBy(() ->
                calculator.afterDiscount(
                    new BigDecimal("-1"), 10))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("price must not be negative");
    }

    @Test
    void rejectsInvalidDiscountRate() {
        assertThatThrownBy(() ->
                calculator.afterDiscount(
                    new BigDecimal("10"), 101))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage(
                "percent must be between 0 and 100");
    }
}
```

Vì `@Tag("unit")` đặt ở **class**, cả 4 methods có tag unit; không method nào thuộc integration hoặc smoke. Các tests tạo một Java object thuần, không có network, DB, Spring context. Chúng phù hợp `test` lane chạy thường xuyên trên laptop/PR.

### 8.2. CatalogServiceIntegrationTest.java: hai ca nhanh, một ca slow

Tệp `src/test/java/com/example/groups/CatalogServiceIntegrationTest.java`:

```java
package com.example.groups;

import java.math.BigDecimal;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@Tag("integration")
class CatalogServiceIntegrationTest {

    @Autowired
    private CatalogService catalog;

    @Autowired
    private PriceCalculator calculator;

    @Test
    void contextWiresCatalogAndCalculator() {
        assertThat(catalog).isNotNull();
        assertThat(calculator).isNotNull();

        Quote result = catalog.quote(
                "SKU-A", new BigDecimal("100.00"), 10);

        assertThat(result.sku()).isEqualTo("SKU-A");
        assertThat(result.payableAmount())
                .isEqualByComparingTo("90.00");
    }

    @Test
    void serviceRejectsBlankSku() {
        assertThatThrownBy(() ->
                catalog.quote(
                    "   ", new BigDecimal("10.00"), 0))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("sku must not be blank");
    }

    @Test
    @Tag("slow")
    void extendedDiscountMatrix() {
        for (int percent = 0; percent <= 100; percent++) {
            Quote quote = catalog.quote(
                    "SKU-MATRIX",
                    new BigDecimal("100.00"),
                    percent);

            BigDecimal expected =
                    BigDecimal.valueOf(100 - percent)
                        .setScale(2);

            assertThat(quote.payableAmount())
                .as("discount percent = " + percent)
                .isEqualByComparingTo(expected);
        }
    }
}
```

**Cách JUnit nhận tags:**
- `contextWiresCatalogAndCalculator`: `integration`.
- `serviceRejectsBlankSku`: `integration`.
- `extendedDiscountMatrix`: `integration` **và** `slow` (tag ở method bổ sung tag ở class).

Vì vậy:
- `integrationTest` (`integration & !slow`) chạy **2 methods đầu**.
- `slowIntegrationTest` (`integration & slow`) chạy **1 method cuối**.
- `test` (`unit`) không chạy cả class này.

**Lưu ý về nhãn slow:** Vòng lặp 101 phép tính không được khẳng định là chậm trên CPU hiện tại. Đây là test `extended` để minh họa CI policy; dự án thật nên gắn `slow` cho tests có chi phí đáng kể như Testcontainers, migrations, full matrix hoặc external adapters. Không dùng `Thread.sleep(5000)` để ép nó “trông có vẻ slow”.

### 8.3. ApplicationSmokeTest.java: context startup smoke

Tệp `src/test/java/com/example/groups/ApplicationSmokeTest.java`:

```java
package com.example.groups;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Tag("smoke")
class ApplicationSmokeTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void applicationContextStartsWithRequiredBeans() {
        assertThat(context).isNotNull();
        assertThat(context.getBean(CatalogService.class))
                .isNotNull();
        assertThat(context.getBean(PriceCalculator.class))
                .isNotNull();
    }
}
```

Một ca smoke kiểm chứng application context có thể start và chứa các beans thiết yếu. Nó không mở cổng HTTP và **không chứng minh deployment production endpoint hoạt động**. Nếu muốn smoke qua HTTP response thật, thêm `spring-boot-starter-web` và một test `@SpringBootTest(webEnvironment=RANDOM_PORT)` riêng, hoặc CI post-deploy probe; đừng gọi một context-only test là end-to-end release validation.

## 9. Ma trận expected selection của project

| Gradle command | Task | Unit 4 | Integration fast 2 | Integration slow 1 | Smoke 1 | Tổng |
|---|---|---:|---:|---:|---:|---:|
| `./gradlew test` | `test` | 4 | 0 | 0 | 0 | **4** |
| `./gradlew integrationTest` | `integrationTest` | 0 | 2 | 0 | 0 | **2** |
| `./gradlew slowIntegrationTest` | `slowIntegrationTest` | 0 | 0 | 1 | 0 | **1** |
| `./gradlew smokeTest` | `smokeTest` | 0 | 0 | 0 | 1 | **1** |
| `./gradlew check` | `test` và `integrationTest` | 4 | 2 | 0 | 0 | **6** |
| `./gradlew check slowIntegrationTest smokeTest` | Cả bốn Test tasks | 4 | 2 | 1 | 1 | **8** |

**Đây là số methods được viết và kết quả lựa chọn theo cấu hình mẫu**, chưa phải log xác nhận test đã chạy thực tế. Nếu thêm classes mới, tag thay đổi, hoặc CLI `--tests` filter, expected counts cũng thay đổi. Gradle có thể báo task `UP-TO-DATE`/cached; số executed trong lần chạy thực cần đọc task state và XML/HTML reports.

### 9.1. Cách hiểu check và mustRunAfter

Gradle Java plugin tạo `check` task phụ thuộc `test` theo lifecycle. Ví dụ thêm `integrationTest` thành một dependency nữa. `mustRunAfter test` khiến integrationTest được thực thi sau test **khi cả hai có trong graph**.

`mustRunAfter` không tự làm integrationTest chạy khi bạn gọi `./gradlew test`. Ngược lại, `./gradlew integrationTest` có thể chạy riêng không cần unit tests trước. Điều này giúp developer chạy đúng group.

Nếu phải bảo đảm integrationTest **không thể** chạy khi unit tests fail, cấu hình `integrationTest.dependsOn test` mới tạo dependency cứng. Nhưng điều đó làm mỗi lần gọi `integrationTest` cũng chạy task unit (hoặc ít nhất thực hiện dependency graph), không còn độc lập như policy minh họa. Chọn theo yêu cầu build, không nhầm ordering với dependency.

### 9.2. Một sai lầm với custom Test tasks

Khi tạo:

```groovy
tasks.register('integrationTest', Test) {
    useJUnitPlatform {
        includeTags 'integration'
    }
}
```

Đây là **ví dụ cấu hình thiếu**, vì custom `Test` task cần `testClassesDirs` và `classpath` hợp lệ. Một số Gradle versions cũ có hành vi default khiến code trông như chạy được; không nên dựa vào điều đó, đặc biệt khi nâng Gradle. Build chính đã cung cấp rõ cả hai giá trị từ `sourceSets.test`.

## 10. Khi nào nên tách source sets thay vì chỉ tags?

Dùng cùng `src/test/java` cho mọi group giúp bắt đầu nhanh, nhưng test integration có thể cần dependencies nặng như Testcontainers, Flyway hoặc external SDK; như vậy **classpath compile của unit suite** vẫn có các dependencies này dù Gradle tags không chạy integration tests.

Một cấu trúc lớn hơn:

```text
src/test/java/               unit tests
src/integrationTest/java/    integration tests
src/smokeTest/java/          smoke tests
```

Cách này có thể được triển khai bằng:
- Gradle `sourceSets { integrationTest { ... } }` và một `Test` task riêng;
- hoặc Gradle **JVM Test Suite Plugin** `testing { suites { integrationTest(JvmTestSuite) { ... } } }`.

**Khác biệt:** Source set tách **compile/runtime classpaths và thư mục source**, còn `@Tag` tách **selection logic trong JUnit Platform**. Hai cách có thể kết hợp: tách integration source set để quản lý dependencies, rồi vẫn dùng `slow` tag để chọn subsets trong integration suite.

### 10.1. Trade-offs

| Tiêu chí | Một source set + tags | Nhiều source sets/suites |
|---|---|---|
| Thiết lập ban đầu | Ít cấu hình | Nhiều cấu hình |
| Dependencies | Dùng chung test dependency graph | Có thể chia theo suite |
| `@Tag` method-level | Thuận tiện | Vẫn dùng được |
| Có thể thiếu tag và bị bỏ sót | Có, nếu mọi task dùng includeTags | Ít hơn khi suite được chọn theo directory nhưng vẫn có thể thiếu |
| Classpath/compilation isolation | Không | Có |
| Gradle reports theo task | Có | Có |
| CI matrix | Dễ | Dễ khi suites rõ ràng |
| Dự án nhỏ | Rất phù hợp | Có thể quá phức tạp |
| Dự án nhiều Testcontainers/SDK | Có thể tốn build/test classpath | Thường dễ quản lý hơn |

Nếu chuyển sang JVM Test Suite Plugin, đọc đúng phiên bản Gradle đang dùng và khai báo dependencies cho suite. Các additional suites **không nên bị giả định tự động kế thừa mọi `implementation` dependencies của main source** chỉ vì built-in `test` suite làm vậy. Đừng đồng thời dùng cùng tên `integrationTest` cho custom `Test` task và một JvmTestSuite-generated task mà không di chuyển cấu hình thích hợp.

## 11. Kịch bản PR, nightly và release CI

### 11.1. Pull request: nhanh và có tín hiệu tốt

```bash
./gradlew clean check --max-workers=2
```

Với project mẫu, `check` gồm `test` và integration-fast; mục tiêu là 4 unit + 2 integration methods. Tùy tổ chức, có thể thêm `smokeTest` nếu khởi động context rẻ; policy ở đây giữ smoke trong release lane để phân biệt.

**Không nên** bỏ integration-fast khỏi PR chỉ vì `@SpringBootTest` mất vài giây nếu đây là phần quan trọng của contract. Mục đích tách nhóm là có ngân sách rõ, không cắt mọi test có Spring.

### 11.2. Nightly: suite mở rộng

```bash
./gradlew check slowIntegrationTest --max-workers=2
```

Task `slowIntegrationTest` chọn `integration & slow`; các ca khác đã nằm trong `check`. Nếu nightly cần xác minh DB, build container và integration data, cấu hình môi trường/credentials giả/seeded services riêng, không phụ thuộc production DB.

### 11.3. Release/local smoke

```bash
./gradlew smokeTest --max-workers=1
```

Demo smoke chỉ khởi tạo context. Nếu công ty cần **deployed smoke** sau khi rollout, nên có một job khác gọi endpoint của bản deploy, có timeout, auth và route phù hợp; không mặc định JUnit context smoke là một deployment health check.

### 11.4. Debug một test lỗi

```bash
./gradlew test   --tests "com.example.groups.PriceCalculatorTest.discountTenPercent"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.groups.PriceCalculatorTest.discountTenPercent"
```

Để debug integration-fast:

```bash
./gradlew integrationTest   --tests "com.example.groups.CatalogServiceIntegrationTest.contextWiresCatalogAndCalculator"
```

Để debug integration-slow:

```bash
./gradlew slowIntegrationTest   --tests "com.example.groups.CatalogServiceIntegrationTest.extendedDiscountMatrix"
```

Nếu bạn chạy `./gradlew test --tests "*CatalogServiceIntegrationTest"`, `@Tag("integration")` không đáp ứng `includeTags 'unit'`; đừng “sửa” bằng cách thêm tag unit sai nghĩa. Hãy chọn **đúng Gradle task**.

### 11.5. Chạy một task không đồng nghĩa CI đã chạy mọi test

Nếu CI chỉ gọi `./gradlew test`, trong policy mẫu nó **chỉ chạy unit**. Review pipeline YAML phải xem chính lệnh Gradle thực. Tương tự, `./gradlew check` **không** chạy `slowIntegrationTest` hoặc `smokeTest` trừ khi đã thêm dependencies. Sự hiện diện của task trong Gradle build file **không tự làm task nằm trong lifecycle `check`**.

## 12. @Disabled, @Tag và @Nested có vai trò khác nhau

### 12.1. @Disabled không phải test group

```java
@Disabled("Provider contract temporarily unavailable")
@Test
void shouldUseExternalProvider() {
}
```

Đây là fragment minh họa; test được discover nhưng bị disable theo JUnit condition. Gắn `@Tag("slow")` không disable test, nó chỉ ảnh hưởng nếu Gradle task lọc theo tag. Vì vậy không dùng tag `quarantined` rồi quên cả CI group đã exclude nó: kiểm thử có thể bị bỏ qua vĩnh viễn mà không ai biết.

Nếu cần quarantine, hãy có một task rõ ràng chọn `quarantined`, có ownership, expiry/review và thống kê, thay vì dùng `@Disabled` vô thời hạn. Tag không thay thế một quy trình sửa flaky tests.

### 12.2. @Nested và tag trên outer class

Một nested JUnit test class thường được discover như container con trong Jupiter model. Tags gắn vào outer container có thể áp dụng tới nested tests. Hãy kiểm thử tag expression khi nested class/method có nhiều tags và đặc biệt nếu đang chuyển một suite lớn sang tag-based filtering; tránh suy luận rằng mỗi nested class là Gradle JVM fork mới.

### 12.3. @ParameterizedTest là một method với nhiều invocations

`@ParameterizedTest` có thể sinh nhiều invocations/dynamic test display names, nhưng tag ở method vẫn áp dụng. Khi đếm reports, số test **invocations** có thể khác số source methods `@Test` hoặc số file classes. Với `--tests` filter theo method, Gradle/JUnit có thể thực thi toàn bộ invocations của method tùy bộ lọc; không dùng count source methods thay cho executed counts trong CI.

### 12.4. Meta-annotations cho convention

Một project có thể tạo custom annotation như `@FastUnitTest` được meta-annotated với `@Tag("unit")` (và có thể `@Test` nếu muốn annotation cho method). Điều này giảm lặp. Nhưng khi đã dùng custom annotations, nên viết một test/discovery check hoặc policy enforcement để bảo đảm chúng tạo tags theo ý muốn trên JUnit Platform; không chỉ đọc tên annotation rồi cho rằng Gradle nhận ra nó.

## 13. Kiểm thử tính đầy đủ của nhóm test

**Rủi ro lớn nhất của positive filtering:** một developer thêm `NewFeatureTest` nhưng quên `@Tag`. Khi tất cả test tasks đều `includeTags`, test đó có thể **không nằm trong bất kỳ task nào**, và `check` vẫn pass.

Một quy trình tránh bỏ sót:
1. Tạo convention trong CONTRIBUTING: mọi Jupiter test class có đúng một primary tag `unit`, `integration` hoặc `smoke`.
2. Có thể gắn modifier `slow`, `database`, `network` ở class/method.
3. Đưa quy định vào code review.
4. Thêm **CI architecture/discovery check** phát hiện untagged tests, hoặc dùng Gradle/JUnit launcher discovery report có kiểm soát.
5. Khi di chuyển suite, tạm có một task `allTests` không tag filters để đối chiếu số discovered tests với tổng mỗi lane; dùng tooling/report để tránh đếm trùng các tests multi-tagged.
6. Không dựa hoàn toàn vào con số ở HTML report của `test` vì đó chỉ là subset.

**Chú ý về duplicate counting:** Nếu một test mang tags của hai nhóm, tổng `unitCount + integrationCount + smokeCount` có thể lớn hơn tổng tests duy nhất. Nếu task filters chồng lấn, đây không nhất thiết là một bug, nhưng phải có convention rõ và không suy luận sai coverage.

### 13.1. Một all-tests diagnostic task (fragment)

Nếu cần một task độc lập để rà test discovery:

```groovy
tasks.register('allTestsDiagnostic', Test) {
    group = 'verification'
    description = 'Diagnostic: run all JUnit Platform tests'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform()
}
```

Đây là **tùy chọn**, không nằm trong main `build.gradle` ở phần 7. Task này **có thể chạy cả các external/slow tests**, nên chỉ dùng trong môi trường an toàn, không coi nó là lựa chọn mặc định cho mọi PR. Một cách an toàn hơn là dùng JUnit Launcher API/listener để thu thập discovered tests và tags **không execute** toàn bộ side effects, hoặc static architecture checks theo convention của team.

### 13.2. Tags không phải test coverage metric

Nếu task `integrationTest` chạy 2 methods, con số đó không đo branch coverage của `CatalogService` hoặc độ đầy đủ integration contract. Dùng code coverage, mutation testing, contract tests và review requirements ở cấp khác. Tag chỉ là **cách phân luồng thực thi**.

## 14. Gradle task ordering, caching và reports

### 14.1. Mỗi Test task có report riêng

Với Gradle `Test` tasks, output thường nằm ở:

```text
build/reports/tests/test/index.html
build/reports/tests/integrationTest/index.html
build/reports/tests/slowIntegrationTest/index.html
build/reports/tests/smokeTest/index.html

build/test-results/test/
build/test-results/integrationTest/
build/test-results/slowIntegrationTest/
build/test-results/smokeTest/
```

Các task được cấu hình độc lập có kết quả/report riêng. CI nên publish toàn bộ artifact reports của những tasks đã chạy, không chỉ `build/reports/tests/test`. Nếu `integrationTest` fail mà CI chỉ thu thập unit report, khả năng chẩn đoán sẽ kém.

### 14.2. UP-TO-DATE và FROM-CACHE không phải tests executed trong lần chạy

Gradle có incremental build, up-to-date checks và build cache. Một `Test` task có thể không execute lại khi inputs/outputs được xem là hợp lệ. Vì thế:
- `BUILD SUCCESSFUL` không phải bằng chứng mọi `@Test` vừa chạy lại.
- `UP-TO-DATE` và `FROM-CACHE` có ý nghĩa khác `executed`.
- Khi điều tra nghi ngờ, có thể dùng `--rerun-tasks` để buộc các tasks chạy lại và đối chiếu logs/reports.
- Không cần `--rerun-tasks` cho mọi PR nếu build cache được quản lý và tin cậy.

Nếu build cấu hình bỏ qua test task do `onlyIf`/filter sai, `NO-SOURCE` hoặc không có selected tests có thể xuất hiện. Hãy xem đúng task console output và test results.

### 14.3. mustRunAfter không tạo dependency

Mẫu:
```groovy
integrationTest.mustRunAfter test
```

Chỉ nói **nếu cả hai có trong task graph thì test đi trước integrationTest**. Nó không tự yêu cầu chạy unit khi developer gọi integrationTest. Trái lại:
```groovy
integrationTest.dependsOn test
```
sẽ tạo dependency; integrationTest không chạy nếu task dependency fail. Tùy mục tiêu test groups, chọn khác nhau. Trong main sample, `check` phụ thuộc cả hai tasks; ordering constraint điều khiển thứ tự.

### 14.4. --parallel và --max-workers không chọn test group

```bash
./gradlew check --parallel --max-workers=4
```

Đây là Gradle scheduler/build concurrency flags. Nó không tự đổi `includeTags`; tasks được chọn bởi CLI và task dependencies. Với multi-module build, `--parallel` có thể cho tasks giữa projects chạy đồng thời. Một JUnit tag `@Tag("serial")` không phải distributed lock giữa projects; nếu nhóm integration cần chung DB, phải cô lập schema/port/data hoặc điều phối CI riêng.

### 14.5. maxParallelForks và JUnit threads là tầng khác

`maxParallelForks=2` chỉ nói tối đa hai JVM test processes cho một task. `junit.jupiter.execution.parallel.enabled=true` (nếu cấu hình) mới cho phép JUnit concurrency bên trong JVM. Cả hai cũng không quyết định `@Tag` selection. Việc tăng forks không thay thế unit/integration/smoke policy.

## 15. CI matrix: làm rõ nhóm kiểm thử và tài nguyên

Một matrix phổ biến:

| Stage | Gradle command | Nhóm | Điều kiện môi trường |
|---|---|---|---|
| PR quick | `./gradlew test` | Unit | Java + dependencies |
| PR verification | `./gradlew check` | Unit + integration nhanh | App context hoặc mocks |
| Nightly | `./gradlew check slowIntegrationTest` | Thêm integration slow | Docker/DB nếu suite thật yêu cầu |
| Release smoke | `./gradlew smokeTest` | Startup smoke | Demo không cần deploy |
| Incident reproduction | `./gradlew integrationTest --tests ...` | Một integration method phù hợp | Test fixture của method |
| Full diagnostic | `./gradlew allTestsDiagnostic` | All selected by JUnit Platform | Chỉ khi an toàn với external side effects |

CI không nên chạy commands mà không biết **nhóm nào được chọn**. Khi đồng bộ CI/GitHub Actions/GitLab/Jenkins, luôn ghi rõ Gradle tasks và profiles. Nếu project dùng secrets/test credentials, chỉ cho job cần external dependency dùng quyền đó; unit task không cần production tokens.

### 15.1. Kiểm soát tài nguyên theo nhóm

**Unit tests:** stateless, không DB, có thể bật nhiều forks nếu hiệu quả.

**Integration tests:** có thể dùng `@SpringBootTest`, `@DataJpaTest`, Testcontainers. Cần random ports, unique DB schema/IDs, cleanup/rollback đúng thread và container lifecycle. Nếu hai Gradle `Test` tasks dùng chung database, `mustRunAfter` điều khiển thứ tự khi cùng task graph, nhưng **không khóa** một job CI khác.

**Slow tests:** thường có data migration, contract với hệ thống phụ thuộc, hoặc full input matrix. Dùng timeout hợp lý, retry có kiểm soát và report. Không tạo ra “slow tests” bằng cách chèn sleep cho đủ tính chất.

**Smoke tests:** kiểm tra khởi động/đường sống tối thiểu của app. Khi chạy post-deploy, test phải có retry/backoff/health semantics phù hợp, không đồng nhất JUnit context smoke với service readiness của deployment.

### 15.2. JUnit @Tag không thay thế test isolation

Dù chia nhóm, những tests trong cùng task có thể song song tùy Gradle/JUnit config. Nếu hai integration methods cùng dùng static `Map`, file cố định hoặc shared H2 database, tag `integration` không làm chúng tự cô lập. Cần riêng `@TempDir`, `@ResourceLock` (chỉ cùng JUnit execution plan), transactions/isolation/unique data, hoặc serial lane ở Gradle task/CI level.

Trong project demo, `CatalogService` và `PriceCalculator` là stateless nên không dùng shared DB/file, phù hợp cho ví dụ group selection.

## 16. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| `./gradlew test` không chạy integration | `test` chỉ include `unit` | Gọi `integrationTest` |
| `--tests integration` không chạy các tags | `--tests` lọc theo tên | Dùng task có `includeTags 'integration'` |
| `--tests "*CatalogServiceIntegrationTest"` với `test` không thấy tests | Task unit tag filter loại class | Gọi `integrationTest --tests ...` |
| Slow method chạy trong PR | integrationTask include `integration` mà không exclude slow | Dùng `integration & !slow` |
| Slow method không chạy trong nightly | CI chưa gọi `slowIntegrationTest` | Bổ sung task vào nightly command |
| Smoke class vô tình chạy trong unit | Unit task chỉ exclude slow, không include unit | Positive selection `includeTags 'unit'` |
| Test mới bị bỏ sót | Quên `@Tag` | Convention + discovery/static check |
| Test bị chạy hai lần | Hai tasks chọn cùng tập tag | Đảm bảo expressions disjoint hoặc chấp nhận chủ đích |
| Custom `Test` task NO-SOURCE | Thiếu `testClassesDirs` hoặc `classpath` | Cấu hình từ source set hoặc suite |
| `check` không chạy integration | Chưa `dependsOn integrationTask` | Thêm dependency verification lifecycle |
| `mustRunAfter` không chạy task trước | Ordering không phải dependency | Dùng `dependsOn` nếu cần |
| Tag expression không match | Cú pháp sai hoặc tag gắn sai class/method | Dùng `&`, `|`, `!` và ngoặc |
| Tag có space/pipe | Tag identifier không hợp lệ | Đổi thành `slow-integration` hoặc hai tags |
| Class có `@Tag("slow")` khiến mọi method bị loại | Tag áp dụng cho mọi methods | Chuyển modifier xuống method thích hợp |
| `@Disabled` test không xuất hiện như pass | Disable là condition khác tag | Bỏ disable sau khi sửa |
| `@ParameterizedTest` count lớn hơn source methods | Nhiều invocations | Đọc report invocations |
| Class path filter quá hẹp | `include '**/*Test.class'` lọc bỏ classes tên khác | Dùng JUnit tags/naming policy nhất quán |
| Gradle `--parallel` không tăng số JUnit methods | Không phải Jupiter mode | Cấu hình JUnit concurrency riêng |
| Unit + integration dùng chung mock bean và flaky | Shared Spring context/mock state | Tách contexts, mock ownership, serial lane |
| DB integration fail khi nhiều forks | Shared schema, fixed IDs hoặc ports | Unique schema/data/ports |
| Reports không có integration results | CI chỉ upload `test` report | Upload report per Test task |
| IDE chạy test nhưng Gradle không | IDE JUnit launcher không dùng Gradle tags | Chạy Gradle task đúng để đối chiếu |
| `BUILD SUCCESSFUL` nhưng không thấy methods | Task cached/skipped/no matching tags | Đọc task state và XML report |
| Tag enum bị refactor | Tag là string, không type-safe | Constants/composed annotations/convention tests |
| CI nightly chậm mà không biết nguyên nhân | Trộn unit/integration/slow | Tách task và report duration từng nhóm |
| `@Tag("database")` nhưng không có DB | Tag không tự tạo resource | Tạo Testcontainers/config thực khi cần |
| Smoke test pass nhưng HTTP deployment lỗi | Smoke chỉ @SpringBootTest context | Thêm post-deploy HTTP smoke |
| CI chọn tất cả qua `!slow` | Untagged và smoke vẫn có thể match | Positive include các nhóm cần thiết |

### 16.1. Checklist chẩn đoán nhanh

1. Đọc đúng **Gradle task** được gọi.
2. Xem `useJUnitPlatform { includeTags/excludeTags }` của task đó.
3. Xem `@Tag` ở test class, method và enclosing/nested classes.
4. Xem có `--tests`, `filter.includeTestsMatching`, class file patterns hoặc engine filters không.
5. Kiểm tra custom `Test` task đã có `testClassesDirs` và `classpath` đúng.
6. Xác nhận `check` dependencies có group bạn nghĩ sẽ chạy.
7. Xác nhận JUnit Jupiter runtime/launcher dependency phù hợp.
8. Đọc XML/HTML reports theo **đúng tên task**.
9. Khi không tìm thấy tests, kiểm tra tags/expressions trước khi sửa package scan hoặc business code.
10. Khi pass nhưng nghi không chạy test, kiểm tra task state (`UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`) và executed test count.
11. Không thay `@Tag("integration")` bằng `@Tag("unit")` chỉ để chọn test bằng một task sai.
12. Không tăng Gradle forks/CI resources trước khi giải quyết shared state.

## 17. Bài tập tự luyện

### Bài tập A: tag inheritance

Cho class `@Tag("integration")` gồm hai methods: `testA()` không gắn tag thêm; `testB()` gắn `@Tag("slow")`. Hãy dự đoán:
- `includeTags('integration')` chọn cả hai.
- `includeTags('integration & !slow')` chỉ chọn A.
- `includeTags('integration & slow')` chỉ chọn B.
- `includeTags('slow')` chỉ chọn B.
- `includeTags('unit')` không chọn cả hai.

Kết quả này minh họa **điều kiện trên tập tags**, không liên quan tới thứ tự method hoặc việc các tests đã pass.

### Bài tập B: --tests có vượt tag filter không?

Trong `test` task có `includeTags 'unit'`, chạy:

```bash
./gradlew test --tests "*CatalogServiceIntegrationTest"
```

Kết quả lựa chọn kỳ vọng: **không có integration tests được chạy**, vì name filter không override tag filter. Muốn chạy `contextWiresCatalogAndCalculator` dùng:

```bash
./gradlew integrationTest   --tests "*CatalogServiceIntegrationTest.contextWiresCatalogAndCalculator"
```

### Bài tập C: test không có tag

Thêm `UntaggedNewFeatureTest` với `@Test` nhưng không `@Tag`. Chạy `./gradlew check`. Test đó không được chọn bởi `unit` hoặc `integration & !slow`; việc `check` thành công **không chứng minh** test mới đã chạy. Hãy thêm tag phù hợp hoặc cải thiện policy kiểm kê; không coi việc bỏ qua là tốt.

### Bài tập D: sửa nhóm mà không chạy trùng

Thử thêm `@Tag("smoke")` vào `CatalogServiceIntegrationTest` trên class. Dự đoán các methods có cả integration/smoke, và task `smokeTest` có thể chạy thêm test đó. Nếu muốn nhóm không chồng lấn, di chuyển smoke check thành class riêng hoặc điều chỉnh expressions theo ownership. Không phụ thuộc vào tên file `*IntegrationTest` để suy ra JUnit sẽ tự loại smoke.

### Bài tập E: nhóm nightly có timeout

Trong dự án thật, một `slowIntegrationTest` dùng PostgreSQL Testcontainers có thể cần Docker. Thiết lập task có timeout/resource policy và dữ liệu độc lập, rồi kiểm chứng CI chạy đúng task chỉ ở nightly. Không thêm sleep vào demo để giả workload; dùng dependency thật nếu mục tiêu là test hệ thống ngoài.

## 18. Kiểm chứng JUnit/Gradle thực tế

### 18.1. Chạy theo từng task

Linux/macOS:

```bash
./gradlew test
./gradlew integrationTest
./gradlew slowIntegrationTest
./gradlew smokeTest
./gradlew check
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat integrationTest
.\gradlew.bat slowIntegrationTest
.\gradlew.bat smokeTest
.\gradlew.bat check
```

Project mẫu chỉ cung cấp `build.gradle` và `src` files; nó giả định bạn đã có một **Gradle wrapper** tương thích hoặc dùng `gradle` đã cài. `./gradlew` không tự tồn tại chỉ vì có `build.gradle`. Để tạo wrapper từ một Gradle installation phù hợp, có thể chạy `gradle wrapper` ở project directory.

### 18.2. Kiểm tra reports sau khi chạy

| Task | HTML report | Expected selected methods |
|---|---|---:|
| `test` | `build/reports/tests/test/index.html` | 4 |
| `integrationTest` | `build/reports/tests/integrationTest/index.html` | 2 |
| `slowIntegrationTest` | `build/reports/tests/slowIntegrationTest/index.html` | 1 |
| `smokeTest` | `build/reports/tests/smokeTest/index.html` | 1 |

Đây là số **theo thiết kế source và task filters**, **không phải kết quả chạy thực tế** trong môi trường hiện tại. Bài này không tự khẳng định build/test đã PASS. Sau khi chạy, đối chiếu counts ở XML/HTML report, trạng thái skipped/failed và CLI filtering. Nếu tests được cache và không execute lại, hiểu rõ task state trước khi báo “đã chạy tất cả”.

### 18.3. Rủi ro khi chạy với nhiều JUnit versions

Spring Boot 3.5 quản lý bộ JUnit Jupiter/Platform qua dependency BOM. Gradle cần test runtime launcher phù hợp. Nếu bạn tự ép JUnit API version khác JUnit Engine/Platform version, test discovery có thể fail hoặc báo `NoSuchMethodError`. Hãy giữ versions aligned theo Spring Boot BOM, tránh copy dependencies từ một hướng dẫn JUnit 6 vào project Spring Boot 3.5 chưa được nâng cấp.

### 18.4. Không cần javac/java đơn lẻ cho project

Mã `PriceCalculator` dùng Spring annotation `@Component` và tests dùng JUnit/AssertJ, nên cách hợp lý là build/test qua Gradle hoặc Maven với dependency management. `javac` đơn lẻ không có Spring/JUnit jars trên classpath sẽ không biên dịch toàn project. Nếu muốn học riêng phép toán `BigDecimal`, có thể tách class Java thuần không annotation, nhưng sẽ không kiểm tra tag filtering của JUnit/Gradle.

## 19. Checklist hoàn tất trước khi áp dụng ở CI

- [ ] Có một danh mục primary tags nhất quán: `unit`, `integration`, `smoke`.
- [ ] `slow` và các feature/resource tags được dùng như modifiers, không làm mất primary type.
- [ ] Mỗi JUnit test class/method được phân vào tối thiểu một nhóm chạy định kỳ.
- [ ] Biết tags ở class được áp dụng tới test methods; method tag bổ sung không xóa class tag.
- [ ] Tag identifiers hợp lệ, không chứa whitespace hoặc toán tử expression.
- [ ] Các task Gradle dùng `useJUnitPlatform` với `includeTags` rõ ràng.
- [ ] Không nhầm `--tests` với tag filter.
- [ ] Không nhầm `filter.includeTestsMatching` và file include patterns với tags.
- [ ] Khi gọi `--tests`, lựa chọn name phải nằm **bên trong group** mà task cho phép.
- [ ] Custom `Test` tasks có `testClassesDirs` và `classpath` rõ ràng.
- [ ] `check` phụ thuộc đúng tasks cần cho PR, không giả định mọi task tự được include.
- [ ] Nightly/release commands gọi riêng slow/smoke tasks khi policy yêu cầu.
- [ ] Tag expressions `integration & !slow` và `integration & slow` không chồng lấn trong ví dụ.
- [ ] Có quy trình phát hiện untagged tests và không tuyên bố coverage đầy đủ chỉ từ `test` report.
- [ ] Đã cân nhắc source set riêng nếu integration cần dependencies nặng.
- [ ] Không để fixed port/DB schema/file path gây race khi tăng concurrency.
- [ ] Không dùng `@Disabled` như cách vĩnh viễn bỏ qua flaky tests.
- [ ] JUnit Platform launcher/engine dependencies được align với Spring Boot BOM.
- [ ] CI upload HTML/XML reports của tất cả tasks đã chạy.
- [ ] Task cache/UP-TO-DATE được hiểu đúng, không bịa executed count.
- [ ] Mọi dòng lệnh trong tài liệu đã được kiểm tra tương ứng đúng tên Gradle task.
- [ ] Chạy kiểm thử thật và đọc report trước khi nói runtime PASS.

## 20. Tài liệu chính thức

- [JUnit 5 User Guide — Tagging and Filtering](https://docs.junit.org/5.14.1/writing-tests/tagging-and-filtering.html): `@Tag`, tag expressions, tagging test classes/methods.
- [JUnit 5 User Guide — Gradle Build Support](https://docs.junit.org/5.14.1/running-tests/build-support.html): `useJUnitPlatform`, `includeTags`, `excludeTags`, runtime dependencies.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): tags, test filtering, `--tests`, reports.
- [Gradle — TestFilter API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/TestFilter.html): `includeTestsMatching`, `excludeTestsMatching`.
- [Gradle — Test Task API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html): `testClassesDirs`, `classpath`, `maxParallelForks`, `filter`, `useJUnitPlatform`.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): tách integration source set/suite, task wiring, verification lifecycle.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices và Spring Boot starter-test.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): context caching, transaction lifecycle và mock overrides.
- [JUnit 5 User Guide — Test Instance Lifecycle](https://docs.junit.org/5.14.1/writing-tests/test-instance-lifecycle.html): instance lifecycle và test method semantics.

**Kết luận:** `@Tag` chỉ **gắn nhãn**, `useJUnitPlatform { includeTags ... }` mới quyết định một Gradle `Test` task chọn những nhãn nào, còn `--tests` chỉ lọc **tên class/method** trong tập mà task cho phép. Với project Spring Boot, một cấu hình có chủ đích gồm `test` cho `unit`, `integrationTest` cho `integration & !slow`, `slowIntegrationTest` cho `integration & slow`, và `smokeTest` cho `smoke` giúp local/PR/nightly/release chạy đúng cấp độ. Đừng quên thêm integration-fast vào `check`, bảo vệ chống untagged tests, phân vùng dependencies/tài nguyên khi cần và đối chiếu **report thật** trước khi kết luận CI đã kiểm tra toàn bộ.