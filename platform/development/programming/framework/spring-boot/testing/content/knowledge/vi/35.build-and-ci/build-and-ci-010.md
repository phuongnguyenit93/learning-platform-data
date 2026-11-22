# Mutation testing để đánh giá khả năng phát hiện thay đổi sai

## 1. Bài test xanh chưa chắc bắt được một lỗi nhỏ

Một dịch vụ Spring Boot có 100% line coverage, toàn bộ JUnit tests đều pass, nhưng chỉ cần đổi điều kiện `subtotal >= 10_000` thành `subtotal > 10_000` là đơn hàng đúng 10.000 xu bị tính phí giao hàng sai. Nếu các tests chỉ thử 9.000 và 12.000, vẫn không test nào thất bại. Coverage cho biết code **đã được chạy qua**; nó không đảm bảo assertions nhận ra giá trị sai.

**Mutation testing** là kỹ thuật cố tình tạo những thay đổi nhỏ (*mutants*) vào mã sản phẩm đã biên dịch rồi chạy tests để xem bộ kiểm thử có phát hiện được không. Với ví dụ trên, một mutation operator thay so sánh `>=` thành `>`. Nếu JUnit test cho đúng ranh giới 10.000 báo fail, mutant được **KILLED**. Nếu toàn bộ tests áp dụng cho mutant vẫn pass, nó **SURVIVED**. Đây là cách đánh giá khả năng **phát hiện thay đổi sai**, không chỉ khả năng đi qua dòng code.

Bài thuộc chủ đề **Build và CI**, tập trung vào thiết kế test, cấu hình PIT (PITest) cho Java/Spring Boot, đọc báo cáo, cải thiện assertions và đưa mutation testing vào CI theo cách có thể vận hành.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích original code, mutation operator, mutant, covering test và mutant status.
- Phân biệt `KILLED`, `SURVIVED`, `NO_COVERAGE`, `TIMED_OUT`, `NON_VIABLE`, `RUN_ERROR` và `MEMORY_ERROR`.
- Phân biệt line/branch coverage với mutation coverage và test strength.
- Nhận diện mutant còn sống do thiếu boundary case, thiếu assertion hay test double quá rộng.
- Biết mutant tương đương (*equivalent mutant*) và vì sao không ép mọi dự án đạt 100%.
- Cài Gradle PIT plugin với JUnit Jupiter, chỉ định đúng `targetClasses` và `targetTests`.
- Chạy `./gradlew test` và `./gradlew pitest`, đọc báo cáo HTML/XML.
- Thiết kế unit tests cho business rules trước khi mở rộng sang Spring MVC/full context.
- Đặt baseline, theo dõi xu hướng và xác định ngưỡng `mutationThreshold` có căn cứ.
- Tránh CI quá chậm hoặc flaky do PIT chạy lại Spring context/DB/Testcontainers nhiều lần.
- Áp dụng ví dụ **Java 17+, Spring Boot 3.5.16, PIT Gradle plugin 1.19.0** với **17 JUnit Jupiter methods** ở ba tầng.

**Phạm vi phiên bản:** ví dụ dùng Java 17+, Spring Boot **3.5.16**, Gradle Groovy DSL, JUnit Jupiter, Mockito và PIT. Bộ cấu hình mẫu ghim `pitestVersion='1.22.1'` cùng `junit5PluginVersion='1.2.3'` để có một bộ version minh họa cụ thể: JUnit 5 plugin 1.2.3 yêu cầu PIT >= 1.19.4, và tài liệu Gradle PIT plugin 1.19.0 có ví dụ PIT engine 1.22.1. Đây **không phải khẳng định chúng là các bản mới nhất**; trước khi nâng cấp cần kiểm tra compatibility với Gradle, JUnit Platform và các plugins đang dùng.

## 2. Mutation testing hoạt động ở tầng nào?

PIT biến đổi **Java bytecode** sau khi compiler tạo class files, không tự ý sửa source file của repository như một developer commit mã lỗi. PIT thường:

1. Phân tích mã sản phẩm và test classes được chọn.
2. Chạy phân tích coverage/timing nền để biết tests nào đi qua những đoạn mã.
3. Áp dụng một mutation operator lên một vị trí bytecode để tạo một mutant.
4. Chạy các covering tests phù hợp khi bytecode mutant được thay vào chương trình.
5. Ghi nhận test fail, vẫn pass, không có coverage hoặc lỗi runtime/timeout.
6. Lặp lại cho các mutant khác và sinh báo cáo.

```text
         Source code + JUnit tests
                    |
                javac/Gradle
                    |
                  .class
                    |
              PIT baseline scan
             coverage + test timing
                    |
         +----------+-----------+
         |          |           |
      Mutant A   Mutant B    Mutant C
        >=→>     return→0   if→inverted
         |          |           |
         v          v           v
       tests      tests       tests
         |          |           |
        FAIL       PASS       NO_COVERAGE
         |          |           |
       KILLED    SURVIVED    NO_COVERAGE
                    |
                    v
             HTML/XML report
                    |
                 Reviewer
          add assertion / test / triage
```

Sơ đồ mô tả khái niệm; PIT chọn và lên lịch mutants/tests dựa trên engine, test plugin, enabled mutators và bytecode thực. **Không** giả định PIT nhất định tạo đúng số mutants cho từng dòng Java; Java compiler và các bộ lọc mutation ảnh hưởng kết quả.

### 2.1. Ví dụ một thay đổi rất nhỏ

Code đúng:

```java
boolean freeShipping(int subtotalCents) {
    return subtotalCents >= 10_000;
}
```

Mutant:

```java
boolean freeShipping(int subtotalCents) {
    return subtotalCents > 10_000;
}
```

Một test chỉ gọi `freeShipping(20_000)` và expect true vẫn pass ở cả bản đúng lẫn mutant. Test ở đúng boundary:

```java
assertThat(freeShipping(10_000)).isTrue();
```

sẽ fail trên mutant. Những đoạn trên là **snippets minh họa riêng**, không phải file production runnable của project phía sau.

### 2.2. Các mutation operators điển hình

PIT có nhiều mutators trên bytecode, ví dụ:

| Dạng mutation | Thay đổi mô hình | Rủi ro được gợi ra |
|---|---|---|
| Conditional boundary | `>=` → `>` | Off-by-one ở ngưỡng |
| Negate conditional | Đảo nhánh `if` | Không test case deny/allow |
| Return value | Trả giá trị khác/default | Không assert result |
| Math operation | Thay phép tính | Không assert total |
| Remove void call | Bỏ lời gọi void | Không kiểm tra side effects |
| Increments | Thay đổi bước tăng/giảm | Không kiểm tra vòng lặp hoặc bộ đếm |

**Tên và tập operators chính xác phụ thuộc PIT version và mutator group.** Các biểu diễn Java ở bảng chỉ để dễ hình dung; PIT biến đổi bytecode nên đôi khi báo cáo source mapping không trực giác. Bắt đầu bằng `mutators=['DEFAULTS']` thay vì bật mọi operator; tài liệu PIT không khuyến khích dùng `ALL` thiếu chọn lọc vì nhiễu, chi phí và equivalent mutants.

## 3. Đọc từng trạng thái mutation một cách chính xác

| Status | Ý nghĩa | Hành động |
|---|---|---|
| `KILLED` | Ít nhất một test thất bại với mutant, phát hiện thay đổi | Giữ assertion/fixture; không cần “sửa” mutant |
| `SURVIVED` | Có test bao phủ nhưng không phát hiện thay đổi | Xem test inputs, assertions, mocks, hoặc tính tương đương |
| `NO_COVERAGE` | Không có test bao phủ vị trí mutant theo phân tích PIT | Thêm test đi qua đường code nếu thuộc scope |
| `TIMED_OUT` | Test với mutant vượt timeout; có thể do infinite loop hoặc timing | Kiểm tra mutant/runtime; không xem mọi timeout là kết quả chắc chắn |
| `NON_VIABLE` | Bytecode mutant không thể load/chạy hợp lệ | Xem công cụ/operator; không coi là test bắt được business bug |
| `RUN_ERROR` | Engine/test runtime gặp lỗi khi thực thi mutant | Điều tra môi trường, classpath, flakiness |
| `MEMORY_ERROR` | Có lỗi tài nguyên/bộ nhớ khi chạy mutant | Xem heap, fork count, tests và mutation configuration |

**SURVIVED không có nghĩa “chắc chắn có bug production”.** Nó cho biết bộ test áp dụng không phân biệt được original và mutated code. Mutation có thể tạo một behavior sai quan trọng, cũng có thể tương đương trong mọi input hợp lệ, hoặc biến đổi một đoạn không thuộc contract đang đánh giá. Reviewer phải phân loại.

**NO_COVERAGE khác SURVIVED.** Nếu không có test nào đi qua nhánh, vấn đề đầu tiên là reachability/ownership của test. Nếu có covering tests nhưng mutant sống, thường cần một input chạm ranh giới hoặc một assertion đủ mạnh.

**TIMED_OUT không nên bị dùng để nâng điểm “giả”**. Một biến thể khiến loop chạy vô hạn thường bị kill qua timeout theo một số cách tính/reporting, nhưng những test thời gian nhạy cảm, resource starvation và CI load cũng có thể gây timeout không ổn định.

## 4. Coverage cao vẫn có thể mutation score thấp

### 4.1. Line coverage trả lời câu hỏi gì?

Line coverage trả lời: **Trong lần chạy test gốc, những dòng bytecode/source nào được thực thi?**

Ví dụ:

```java
Quote q = pricing.quote(9_999, 2, false);
assertThat(q).isNotNull();
```

Test này đi qua service và có thể tăng line coverage, nhưng không kiểm tra phí giao hàng 500 hay tổng phải trả 10.499. Nếu mutant đổi shipping fee thành 0 và vẫn trả một Quote object, test vẫn xanh.

### 4.2. Mutation coverage trả lời câu hỏi gì?

Mutation testing hỏi: **Nếu một biến thể sai được thay vào vùng code đã chọn, tests có fail không?** Nó bổ sung thông tin về **sức mạnh của assertions và chất lượng test data**.

Bảng minh họa, **không phải kết quả đã chạy PIT**:

| Chỉ số minh họa | Giá trị |
|---|---:|
| Tổng mutants hợp lệ được tính trong ví dụ | 25 |
| Killed | 18 |
| Survived | 2 |
| No coverage | 5 |
| Mutation score giả định | 18 / 25 = 72% |
| Test strength giả định theo nhóm covered | 18 / (18 + 2) = 90% |

Theo tài liệu PIT, `mutationThreshold` là ngưỡng score tính từ mutations bị kill trên tổng mutations. `testStrengthThreshold` xem tỷ lệ killed trong nhóm có coverage (killed / (killed + survived), loại nhóm không có coverage). Với công cụ/version/report khác nhau, hãy xác minh cách đếm `TIMED_OUT`, filtered/nonviable mutations và denominator trong kết quả thật; **không tái sử dụng số minh họa như kết quả tool**.

### 4.3. Không đối xử mutation score như thước đo an toàn duy nhất

- 95% score trên utility class không bảo đảm JWT authorization, SQL transaction hay security filters được kiểm tra.
- 70% score trên critical financial domain code có thể đòi review cao hơn 90% trên generated mappings.
- Mutator set khác nhau → score có thể không so sánh trực tiếp.
- Scope `targetClasses`/`targetTests` khác nhau → denominator thay đổi.
- Equivalent mutants có thể giới hạn score tối đa thực tế.
- Flaky/time-dependent tests khiến statuses không đáng tin.
- Test coverage còn phải bao gồm integration contracts và non-functional requirements ngoài mutation operators.

Mutation score là **một tín hiệu về khả năng test phát hiện lỗi trong phạm vi đã mutate**, không phải chứng chỉ ứng dụng an toàn hay không có bugs.

## 5. Equivalent mutant và giới hạn lý thuyết

Một **equivalent mutant** có bytecode khác nhưng behavior quan sát được tương đương với original trong phạm vi input hợp lệ. Ví dụ sau là **snippet khái niệm**, không được build vào project demo:

```java
// Original:
if (count >= 1) {
    return "valid";
}

// Mutant:
if (count > 0) {
    return "valid";
}
```

Với số nguyên, hai điều kiện này tương đương. Không có một test input int nào buộc original và mutant trả khác nhau trong nhánh ấy. Việc cứ thêm tests để kill mutant như vậy chỉ tạo nhiễu.

**Cách xử lý:**

1. Đọc original condition và operator thực sự PIT đã áp dụng.
2. Xác định domain/range của inputs (bao gồm null, negatives, overflow, invalid inputs).
3. Chứng minh vì sao mutated behavior tương đương hoặc không thuộc required contract.
4. Ghi rationale vào review/issue; điều chỉnh mutation scope/filter có giải thích nếu cần.
5. Không tạo assertion giả hoặc sửa production code trái nghiệp vụ để tăng score.

**Đừng vội gọi một mutant là equivalent chỉ vì khó kill.** Trước hết thử boundary, path negatives, state changes và kiểm tra test double có ngăn production code chạy hay không.

## 6. Xây một chính sách mutation testing cho Spring Boot

Một repo có controllers, services, repository, configurations, generated code, DTOs và external integrations. Không nhất thiết mutate tất cả mọi thứ với mọi JUnit tests ngay lập tức.

Một chiến lược có thể vận hành:

1. Chọn **business-critical deterministic code** trước: pricing, eligibility, authorization decisions, business state transitions, retries và validation helpers.
2. Chạy **pure unit tests** làm mutant consumers đầu tiên để feedback nhanh, không phải khởi động Spring context cho mỗi mutation.
3. Mutate service classes có branching thực, không mặc định nhắm vào generated DTOs/records/mappers.
4. Giữ riêng MVC slice, repository, security và full-context tests cho contracts của Spring/DB/HTTP.
5. Dần mở rộng mutation scope tới modules khác khi baseline rõ.
6. Thu báo cáo HTML cho developers và XML cho CI parsing/trends.
7. Đặt ngưỡng fail-build theo baseline đã đo, tránh áp “90%” từ bên ngoài.
8. Phân loại survivors có rủi ro cao trước khi cố tối đa hóa tổng điểm.
9. Giữ CI tổng thể khả thi: chạy targeted mutation ở PR/merge và broader schedule khi cần.
10. Khi thay mutator set, target classes hoặc plugin version, ghi nhận đây là **metric-series change**.

### 6.1. Vì sao Spring context có thể khiến PIT rất chậm?

PIT chạy tests nhiều lần với mutated bytecode. Một test `@SpringBootTest` kéo DataSource, JPA, security, Testcontainers và HTTP clients có startup cost đáng kể. Spring TestContext cache có thể giảm cold-start trong một JVM với cùng key, nhưng PIT điều phối và fork JVMs để thử mutations, nên **không có bảo đảm** context đã cache từ `./gradlew test` sẽ được dùng lại trong `./gradlew pitest`.

Mutants có thể tạo startup failure, thay bean lifecycle hoặc khiến external dependency timeout. Vì vậy hãy tách:

- **Unit PIT task** cho pure functions / service policy khi đủ evidence.
- **Integration suites** kiểm tra Spring wiring và interfaces thật.
- **Broader mutation runs** theo lịch hoặc module-specific scope khi ROI hợp lý.

Không bỏ integration tests để tăng PIT score; đừng đưa mọi `@SpringBootTest` vào PIT rồi ngạc nhiên vì CI kéo dài.

## 7. Ví dụ hoàn chỉnh: phí giao hàng của một Spring Boot API

Chúng ta tạo một ứng dụng Spring Boot nhỏ có policy tính phí:

- `subtotalCents` là tổng tiền hàng (đơn vị xu/đồng nhỏ nhất), phải ≥ 0.
- `itemCount` là số sản phẩm, phải > 0.
- Khách **premium** được miễn phí giao hàng.
- Đơn hàng có subtotal **≥ 10.000** cũng miễn phí.
- Nếu không được miễn phí, có từ **3 sản phẩm trở lên** thì phí là **350**.
- Nếu không được miễn phí và có ít hơn 3 sản phẩm thì phí là **500**.
- Tổng thanh toán = subtotal + shipping.
- Không truy cập database, mạng, clock hoặc random; vì vậy policy rất phù hợp để mutation test bằng plain JUnit.

### 7.1. Các trường hợp biên cần phát hiện

| Case | subtotal | count | premium | shipping | total |
|---|---:|---:|:---:|---:|---:|
| 1 sản phẩm | 2.000 | 1 | false | 500 | 2.500 |
| 2 sản phẩm | 2.000 | 2 | false | 500 | 2.500 |
| 3 sản phẩm | 2.000 | 3 | false | 350 | 2.350 |
| 4 sản phẩm | 2.000 | 4 | false | 350 | 2.350 |
| Ngay dưới miễn phí | 9.999 | 2 | false | 500 | 10.499 |
| Đúng ngưỡng miễn phí | 10.000 | 2 | false | 0 | 10.000 |
| Ngay trên ngưỡng | 10.001 | 2 | false | 0 | 10.001 |
| Premium giá nhỏ | 1 | 1 | true | 0 | 1 |
| Subtotal bằng 0, hợp lệ | 0 | 1 | false | 500 | 500 |
| Subtotal âm | -1 | 1 | false | Reject | — |
| Count bằng 0 | 1.000 | 0 | false | Reject | — |
| Count âm | 1.000 | -1 | false | Reject | — |

**Quan trọng:** đây là business policy **của demo**, không phải quy định phí giao hàng áp dụng cho một doanh nghiệp thật. Trong production còn phải xem currency, rounding, promotions, delivery zones, taxes, max quantity, idempotence và overflow.

### 7.2. Cấu trúc file

```text
mutation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/mutation/
    │   ├── MutationDemoApplication.java
    │   ├── ShippingQuote.java
    │   ├── ShippingQuoteService.java
    │   └── ShippingQuoteController.java
    └── test/java/com/example/mutation/
        ├── ShippingQuoteServiceTest.java
        ├── ShippingQuoteControllerWebMvcTest.java
        └── ShippingQuoteFlowSpringBootTest.java
```

Mẫu có **17 JUnit Jupiter methods**: 12 unit tests, 3 MVC slice tests và 2 full-context smoke tests. PIT được cấu hình **chỉ mutate ShippingQuoteService và chọn ShippingQuoteServiceTest** để đo business logic mà không lặp khởi động Spring context. MVC/full-context tests vẫn chạy ở Gradle `test`, bảo vệ HTTP mapping và real bean wiring; chúng **không được tính** trong PIT targeted run được cấu hình bên dưới.

## 8. Cấu hình Gradle và PIT (Groovy DSL)

**File `settings.gradle`:**

```groovy
rootProject.name = 'mutation-demo'
```

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'info.solidsoft.pitest' version '1.19.0'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

pitest {
    // Chosen, pinned example versions; not a claim of newest versions.
    pitestVersion = '1.22.1'
    junit5PluginVersion = '1.2.3'

    // Scope the mutation to production policy code only.
    targetClasses = ['com.example.mutation.ShippingQuoteService']
    targetTests = ['com.example.mutation.ShippingQuoteServiceTest']

    mutators = ['DEFAULTS']
    threads = 2
    outputFormats = ['HTML', 'XML']
    timestampedReports = false

    // First run: measure real baseline; do not set an invented gate.
    mutationThreshold = 0
}
```

### 8.1. Tại sao cấu hình như vậy?

- `info.solidsoft.pitest` là plugin Gradle bên thứ ba cho PIT; bản 1.19.0 được công bố trên Gradle Plugin Portal.
- `pitestVersion` chọn engine cụ thể thay vì tự động đi theo version mặc định của plugin.
- `junit5PluginVersion` thêm `org.pitest:pitest-junit5-plugin` vào **PIT tool classpath**, không chỉ vào `testImplementation` của ứng dụng, và cấu hình JUnit 5 test plugin.
- `targetClasses` chọn bytecode của production class cần mutate; **không mutate test code**.
- `targetTests` chỉ định lớp tests có cơ hội kill mutants; khi scope thay đổi, mutation score có thể thay đổi.
- `mutators=['DEFAULTS']` dùng set mutators mặc định có tính thực dụng trước khi thử stronger operators.
- `threads=2` giới hạn concurrency tương đối; tăng threads chỉ khi CI có đủ CPU/RAM và tests thread-safe.
- `outputFormats=['HTML','XML']` tạo kết quả dễ review và máy đọc.
- `timestampedReports=false` cho vị trí report ổn định trong CI.
- `mutationThreshold=0` **chưa fail build nếu mutation score thấp**. Đây là bước dựng baseline, không phải policy lâu dài.

Tài liệu Gradle plugin cho biết report mặc định nằm dưới `build/reports/pitest`. Khi nâng plugin, kiểm tra task name, report path, Gradle API compatibility và JUnit Platform version.

### 8.2. Chọn version và dependency một cách có trách nhiệm

Tại thời điểm biên soạn, Gradle PIT plugin có bản 1.19.0; JUnit5 plugin 1.2.3 yêu cầu PIT engine 1.19.4 trở lên. PIT engine 1.22.1 trong cấu hình đáp ứng ràng buộc tối thiểu đó. Bản PIT mới hơn có thể tồn tại và làm mutation sets/reporting khác. Đừng tự thay bằng chữ `latest` trong CI reproducible build.

Spring Boot 3.5.16 là bản phát hành của nhánh 3.5.x trong năm 2026; với ứng dụng production dài hạn, cân nhắc vòng đời hỗ trợ của nhánh Boot/Gradle/PIT đã chọn. Mỗi lần nâng major Boot hoặc JUnit phải chạy lại test/PIT và so API compatibility.

### 8.3. Không dùng JaCoCo thay cho PIT

JaCoCo giúp thu line/branch coverage; PIT dùng mutation analysis. Hai công cụ **bổ sung**, không thay thế nhau. Có thể chạy JaCoCo trước để tìm uncovered regions, sau đó dùng PIT cho các dòng đã được cover nhưng assertions yếu. Không nên fail PR chỉ vì một tỷ lệ đơn lẻ mà không hiểu denominator/scope.

## 9. Production code: application, DTO và service

### 9.1. Spring Boot entrypoint

**File `src/main/java/com/example/mutation/MutationDemoApplication.java`:**

```java
package com.example.mutation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MutationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MutationDemoApplication.class, args);
    }
}
```

### 9.2. DTO là immutable record

**File `src/main/java/com/example/mutation/ShippingQuote.java`:**

```java
package com.example.mutation;

public record ShippingQuote(
        int subtotalCents,
        int shippingCents,
        int totalCents
) {}
```

Record này đại diện output API. Vì PIT chỉ target `ShippingQuoteService`, những compiler-generated methods của DTO record **không** tự được tính vào mutation score target. Scope hẹp là chủ ý của bài học, không phải chứng minh DTO serialization luôn đúng; nhóm MVC tests kiểm tra phần đó.

### 9.3. Service chứa các nhánh nghiệp vụ

**File `src/main/java/com/example/mutation/ShippingQuoteService.java`:**

```java
package com.example.mutation;

import org.springframework.stereotype.Service;

@Service
public class ShippingQuoteService {

    public ShippingQuote quote(
            int subtotalCents, int itemCount, boolean premium) {

        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be nonnegative");
        }

        if (itemCount <= 0) {
            throw new IllegalArgumentException(
                    "itemCount must be positive");
        }

        int shippingCents;

        if (premium || subtotalCents >= 10_000) {
            shippingCents = 0;
        }
        else if (itemCount >= 3) {
            shippingCents = 350;
        }
        else {
            shippingCents = 500;
        }

        return new ShippingQuote(
                subtotalCents,
                shippingCents,
                Math.addExact(subtotalCents, shippingCents));
    }
}
```

**Tại sao đây là mục tiêu tốt cho mutation testing?**

- Điều kiện `subtotalCents < 0` nên bị phát hiện khi inversion/boundary bị thay.
- `itemCount <= 0` cần test cả 0 và số âm.
- `premium || subtotalCents >= 10_000` cần thử cả premium low amount và regular threshold.
- `itemCount >= 3` cần thử 2, 3 và 4.
- Phí 350/500 và total phải được assert bằng giá trị cụ thể, không chỉ nonnull.

Sử dụng `Math.addExact` giúp phát hiện integer overflow nếu có thể xuất hiện. Trong chính policy minh họa này, tổng với subtotal lớn ≥10.000 được miễn phí, nên overflow số nguyên không nằm trong các trường hợp hợp lệ thông thường; **không tuyên bố test hiện tại đã chứng minh overflow handling cho mọi thiết kế giá**.

### 9.4. Controller HTTP mỏng

**File `src/main/java/com/example/mutation/ShippingQuoteController.java`:**

```java
package com.example.mutation;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ShippingQuoteController {

    private final ShippingQuoteService service;

    public ShippingQuoteController(ShippingQuoteService service) {
        this.service = service;
    }

    @GetMapping("/quotes")
    public ShippingQuote quote(
            @RequestParam int subtotalCents,
            @RequestParam int itemCount,
            @RequestParam(defaultValue = "false") boolean premium) {

        return service.quote(subtotalCents, itemCount, premium);
    }
}
```

Controller dùng Spring MVC để bind query parameters thành types và serialize ShippingQuote record thành JSON. Application **không thêm Spring Security** để ví dụ chỉ tập trung vào mutation testing, không xem một GET 200 như bằng chứng authentication/authorization đúng.

Đối với invalid domain inputs như subtotal âm, service ném IllegalArgumentException; demo **không tự cấu hình mapping 400 cho domain exception**. Nếu cần API contract rõ về invalid domain input, thêm @ControllerAdvice/@ExceptionHandler và test riêng thay vì tự giả định mọi IllegalArgumentException là 400.

## 10. Pure JUnit unit tests: 12 methods phát hiện mutant

**File `src/test/java/com/example/mutation/ShippingQuoteServiceTest.java`:**

```java
package com.example.mutation;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ShippingQuoteServiceTest {

    private final ShippingQuoteService service =
            new ShippingQuoteService();

    @Test
    void rejectsNegativeSubtotal() {
        assertThatThrownBy(() ->
                service.quote(-1, 1, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("subtotalCents");
    }

    @Test
    void rejectsZeroItemCount() {
        assertThatThrownBy(() ->
                service.quote(1_000, 0, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("itemCount");
    }

    @Test
    void rejectsNegativeItemCount() {
        assertThatThrownBy(() ->
                service.quote(1_000, -1, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("itemCount");
    }

    @Test
    void oneRegularItemPaysFullShipping() {
        assertThat(service.quote(2_000, 1, false))
                .isEqualTo(
                        new ShippingQuote(2_000, 500, 2_500));
    }

    @Test
    void twoRegularItemsStillPayFullShipping() {
        assertThat(service.quote(2_000, 2, false))
                .isEqualTo(
                        new ShippingQuote(2_000, 500, 2_500));
    }

    @Test
    void threeRegularItemsGetReducedShipping() {
        assertThat(service.quote(2_000, 3, false))
                .isEqualTo(
                        new ShippingQuote(2_000, 350, 2_350));
    }

    @Test
    void fourRegularItemsKeepReducedShipping() {
        assertThat(service.quote(2_000, 4, false))
                .isEqualTo(
                        new ShippingQuote(2_000, 350, 2_350));
    }

    @Test
    void justBelowFreeShippingThresholdStillPays() {
        assertThat(service.quote(9_999, 2, false))
                .isEqualTo(
                        new ShippingQuote(9_999, 500, 10_499));
    }

    @Test
    void exactlyAtFreeShippingThresholdIsFree() {
        assertThat(service.quote(10_000, 2, false))
                .isEqualTo(
                        new ShippingQuote(10_000, 0, 10_000));
    }

    @Test
    void aboveFreeShippingThresholdRemainsFree() {
        assertThat(service.quote(10_001, 2, false))
                .isEqualTo(
                        new ShippingQuote(10_001, 0, 10_001));
    }

    @Test
    void premiumCustomerGetsFreeShippingEvenForTinyOrder() {
        assertThat(service.quote(1, 1, true))
                .isEqualTo(
                        new ShippingQuote(1, 0, 1));
    }

    @Test
    void zeroSubtotalIsValidButStillPaysShipping() {
        assertThat(service.quote(0, 1, false))
                .isEqualTo(
                        new ShippingQuote(0, 500, 500));
    }
}
```

### 10.1. Vì sao cả object equality có ích?

Java record `ShippingQuote` tự cung cấp value-based equality. Assertion so với `new ShippingQuote(subtotal, shipping, total)` kiểm tra **đồng thời ba fields**. Nếu code bị mutate từ shipping 500 thành 0, hoặc total được tính sai, test có cơ hội fail.

Không phải mọi mutant sẽ được kill. PIT có thể tạo mutators mà test case chưa chạm, có filter loại một số operators hoặc xuất hiện equivalent mutants. **Không tuyên bố đã đạt một điểm PIT cụ thể khi chưa chạy.**

### 10.2. Bốn ranh giới quan trọng

- Subtotal -1 / 0: nhận diện đảo điều kiện `subtotalCents < 0`.
- ItemCount 0 / 1: nhận diện điều kiện `itemCount <= 0`.
- Count 2 / 3 / 4: nhận diện `itemCount >= 3`.
- Subtotal 9.999 / 10.000 / 10.001: nhận diện `subtotalCents >= 10_000`.

Nếu một mutation operator thay `>=` thành `>`, test đúng tại 10.000 mới phân biệt được hai implementations. Nếu đảo `premium`, test premium low amount sẽ fail. Nếu bỏ bước cộng shipping trong total, các case không miễn phí sẽ fail.

### 10.3. Một anti-test dễ tạo mutant sống

**Đoạn sau chỉ minh họa test yếu, không có trong lớp runnable:**

```java
@Test
void weakAssertion() {
    ShippingQuote result =
            service.quote(9_999, 2, false);
    assertThat(result).isNotNull();
}
```

Hàm có thể trả phí sai mà test vẫn xanh. Thay bằng assert `shippingCents=500` và `totalCents=10499`; kiểm tra đúng contract, không tăng số lượng assertions vô nghĩa để “giết” mutant.

## 11. MVC slice tests: 3 methods cho HTTP contract

**File `src/test/java/com/example/mutation/ShippingQuoteControllerWebMvcTest.java`:**

```java
package com.example.mutation;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(ShippingQuoteController.class)
class ShippingQuoteControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ShippingQuoteService service;

    @Test
    void successfulRequestBindsParametersAndSerializesQuote()
            throws Exception {
        when(service.quote(9_999, 2, false))
                .thenReturn(new ShippingQuote(
                        9_999, 500, 10_499));

        mvc.perform(get("/quotes")
                .param("subtotalCents", "9999")
                .param("itemCount", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subtotalCents")
                        .value(9_999))
                .andExpect(jsonPath("$.shippingCents")
                        .value(500))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499));

        verify(service).quote(9_999, 2, false);
    }

    @Test
    void missingItemCountIsBadRequestBeforeService()
            throws Exception {
        mvc.perform(get("/quotes")
                .param("subtotalCents", "2000"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void invalidIntegerParameterIsRejectedBeforeService()
            throws Exception {
        mvc.perform(get("/quotes")
                .param("subtotalCents", "banana")
                .param("itemCount", "1"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

Nhóm này kiểm tra Spring MVC routing, `@RequestParam` binding, default premium=false, JSON serialization và 400 cho missing/malformed parameters.

**Vì service là `@MockitoBean`, những tests này không kiểm tra business logic service thật.** Mutation target chủ ý chỉ chọn `ShippingQuoteServiceTest`, nên các MVC tests không được PIT dùng để đánh giá mutants của service. Đây là sự phân lớp có chủ đích, không phải một sơ suất về scope.

Nếu ứng dụng có Spring Security thực, web slice có thể nạp security config theo cách khác full context; cần security-enabled tests riêng và không tắt filters chỉ để đạt 200.

## 12. Full-context seam tests: 2 methods cho real bean wiring

**File `src/test/java/com/example/mutation/ShippingQuoteFlowSpringBootTest.java`:**

```java
package com.example.mutation;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(classes = MutationDemoApplication.class)
@AutoConfigureMockMvc
class ShippingQuoteFlowSpringBootTest {

    @Autowired
    MockMvc mvc;

    @Test
    void webToRealServiceAppliesShippingPolicy()
            throws Exception {
        mvc.perform(get("/quotes")
                .param("subtotalCents", "9999")
                .param("itemCount", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shippingCents")
                        .value(500))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499));
    }

    @Test
    void webToRealServiceHonorsExactFreeThreshold()
            throws Exception {
        mvc.perform(get("/quotes")
                .param("subtotalCents", "10000")
                .param("itemCount", "2")
                .param("premium", "false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shippingCents")
                        .value(0))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_000));
    }
}
```

Nhóm này dùng **full Spring application context** với controller và service thật. Nhưng `MockMvc` chạy in-process; `@SpringBootTest` mặc định không mở real HTTP socket chỉ vì có MockMvc. Nếu muốn chứng minh embedded servlet container, TLS, socket hoặc real HTTP flow, thêm suite `@SpringBootTest(webEnvironment=RANDOM_PORT)` và HTTP client.

**Vì sao không đưa seam tests vào targetTests của PIT sample?** Chúng có giá trị chứng minh Spring wiring, nhưng mỗi mutant chạy qua full context có thể rất tốn thời gian, trong khi domain policy đã có JUnit unit tests. Khi unit mutation score đã ổn, có thể mở rộng scope với integration mutants cụ thể nếu có bug chỉ xuất hiện qua Spring proxy/configuration.

## 13. Chạy ví dụ theo đúng thứ tự

### 13.1. Chạy JUnit suite gốc trước

Trên Linux/macOS với Gradle Wrapper đã có:

```bash
./gradlew clean test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

**Mong đợi về thiết kế:** có **17 JUnit tests** (12 + 3 + 2) và chúng đều pass khi JDK/Gradle/dependencies tương thích. Đây là kết quả **kỳ vọng của code**, không phải stdout được chép từ một lần chạy thực. Không tuyên bố JUnit đã pass khi `test` báo UP-TO-DATE/FROM-CACHE mà không xác minh test report phù hợp.

### 13.2. Chạy PIT sau khi baseline tests pass

Linux/macOS:

```bash
./gradlew pitest
```

Windows PowerShell:

```powershell
.\gradlew.bat pitest
```

PIT sẽ dùng mutation target và JUnit 5 plugin đã cấu hình. Nếu setup build/plugin/test engine không tương thích, hãy sửa lỗi đó **trước** khi đánh giá mutation score. Một dòng `No mutations found` hoặc `No tests found` không phải thành công về chất lượng test; kiểm tra target globs, compiled classes và plugin classpath.

### 13.3. Báo cáo

Với Gradle PIT plugin, report thường ở:

```text
build/reports/pitest/
    index.html
    mutations.xml
    ... per-class/package HTML files
```

Cấu trúc thư mục/filenames thực tế có thể thay đổi theo PIT version và report output settings; hãy kiểm tra artifact thực tế, không tự tạo liên kết tới file chưa xuất hiện.

Mở HTML và tìm class `ShippingQuoteService`. Những mutants còn sống cần được xem theo operator, method, line và test cases. XML phù hợp để lưu CI artifact, tổng hợp theo job/module và so sánh baseline. **Không sửa trực tiếp report files**; sửa code/tests rồi chạy lại.

### 13.4. Chạy thử mục tiêu hẹp khi debug

Nếu một test yếu chỉ kiểm tra status hoặc object nonnull, chạy riêng test/JUnit và PIT targeted service class để hiểu feedback nhanh. Tăng mutation scope khi đã có baseline; không bắt đầu bằng cả codebase với toàn bộ Spring integration suite nếu một developer còn đang học semantics của PIT.

## 14. Một bài lab: cố ý làm test yếu rồi cải thiện

Đây là **thao tác thực hành trên bản sao/demo repo, không áp dụng vào source production thật**.

### 14.1. Trường hợp yếu

Giả sử chỉ có test:

```java
ShippingQuote q = service.quote(9_999, 2, false);
assertThat(q).isNotNull();
```

PIT có thể tạo một mutant làm shipping=0 thay vì 500; test vẫn pass vì Quote không null. Trạng thái có thể là SURVIVED tùy mutator/coverage.

### 14.2. Bổ sung assertion đúng contract

```java
ShippingQuote q = service.quote(9_999, 2, false);
assertThat(q.shippingCents()).isEqualTo(500);
assertThat(q.totalCents()).isEqualTo(10_499);
```

Nếu mutant làm shipping=0 hoặc total sai, assertions có khả năng fail. **Chỉ thêm assertion vì đó là behavior bắt buộc**, không phải vì muốn “kéo điểm” theo một operator cụ thể.

### 14.3. Trường hợp boundary

Một bug đổi `subtotalCents >= 10_000` thành `subtotalCents > 10_000`:

- Test ở 9.999: cả hai implementations thu phí.
- Test ở 10.001: cả hai miễn phí.
- **Test ở 10.000:** original miễn phí, mutant thu phí.

Đây là giá trị cốt lõi của mutation testing: nó gợi ra **test input phân biệt được hai hành vi**.

### 14.4. Trường hợp side effect

Nếu service production có:

```java
inventory.reserve(orderId);
payment.capture(orderId);
```

một mutation operator bỏ lời gọi void có thể tạo mutant vẫn pass nếu test chỉ assert response DTO. Khi reserve/capture là contract, test nên xác minh side effect qua repository/fake/spy/integration phù hợp; với external services, cần xác nhận behavior thực ở tầng tương ứng, không chỉ Mockito verify call trong một unit test bị stubbing rộng.

Đây là snippet riêng; demo phí giao hàng **không** có inventory/payment methods, và PIT target của demo không tạo mutation cho snippet này.

## 15. Quy trình triage một mutant SURVIVED

Khi PIT báo SURVIVED, đừng tự động thêm một assertion để nó chết. Sử dụng trình tự:

1. Xác định **production class/method/line** bị mutate, operator và mutated behavior.
2. Xem đã có covering tests chưa, và tests ấy dùng input nào.
3. Viết ra sự khác nhau giữa original và mutant dưới dạng điều kiện/hành vi dễ hiểu.
4. Tìm **input phân biệt**: boundary, null/empty, zero, negative, overflow, role khác, retry failure, business transition.
5. Kiểm tra assertion có kiểm tra output/side effect thật hay chỉ `notNull`/status 200.
6. Kiểm tra mocking có bỏ qua chính production method bị mutate không.
7. Xem mutant có thực sự **reachable** trong input domain đã khai báo.
8. Nếu có bug khả dĩ, thêm test nhỏ nhất theo requirement và giữ trong suite.
9. Nếu tương đương, giải thích bằng lập luận/đặc tả, cân nhắc filtering có scope nhỏ.
10. Nếu tool báo RUN_ERROR/TIMED_OUT, chẩn đoán environment trước khi chốt.
11. Chạy lại JUnit gốc, sau đó PIT, xác nhận mutant status thay đổi.
12. Review xem test bổ sung là meaningful regression guard hay chỉ assertion phục vụ operator.

**Đừng sửa logic sản phẩm khi original đang đúng chỉ để ép điểm mutation.** Mục tiêu là biết tests có bắt được bug thực tế, không viết code cho hợp khẩu vị mutation engine.

### 15.1. Một survivor là tín hiệu chứ không phải verdict

Một mutation ở logging, toString, generated framework code, final unreachable branch hoặc condition tương đương có thể không cần assertion. Trong khi mutant ở payment amount, authorization branch, retry stop condition hoặc stock decrement là ưu tiên cao. Vì thế review phải đánh giá **risk × behavior**, không chỉ số survivors.

### 15.2. Nếu PIT báo NO_COVERAGE

Kiểm tra:

- Target class/method có thuộc production code cần test không?
- JUnit 5 plugin có load được tests không?
- targetTests pattern có vô tình bỏ lớp liên quan không?
- Code có được đi qua trong test gốc?
- Integration context có tạo bean bị mock nên production code không chạy không?
- Mutated path chỉ chạy với input hiếm mà tests chưa cung cấp?
- PIT coverage discovery có bị lỗi test engine/classpath không?

Nếu tests thực sự không chạm critical branch, thêm test phù hợp. Nếu `NO_COVERAGE` do cấu hình chọn tests sai, sửa scope chứ không vội chê bộ JUnit.

## 16. Pitest với Spring Boot: scope và các bẫy

### 16.1. Spring-managed service và plain Java unit test

Một `@Service` vẫn có thể được instantiate bằng `new ShippingQuoteService()` nếu behavior không phụ thuộc Spring proxy/config injection. Đây là lựa chọn tốt cho mutation target **thuần Java**.

Nhưng nếu method chịu `@Transactional`, `@Cacheable`, `@Retryable` hoặc `@PreAuthorize`, plain unit test không tự chạy những Spring advices. Cần giữ integration tests qua Spring-managed bean hoặc specialized tests để bảo vệ contracts ấy.

### 16.2. MVC slice có thể mock chính service cần mutate

`@WebMvcTest` với `@MockitoBean ShippingQuoteService` giúp kiểm tra routing/JSON, nhưng bean service thật không chạy. Nếu để PIT mutate service và chỉ chọn MVC slice test ấy, mutation có thể bị NO_COVERAGE hoặc không được tiêu thụ như mong muốn.

**Không lấy MVC slice with mocked service làm bằng chứng business mutation score.** Hoặc chọn plain service tests, hoặc full integration tests không mock target cần kiểm tra.

### 16.3. Transaction, DB và Testcontainers

PIT engine có thể chạy nhiều mutants; nếu mỗi mutant mở database/container hoặc test dùng shared external state, performance và isolation trở thành vấn đề. Với JPA query/database semantics, có thể phải dùng mutation testing kết hợp integration tests hoặc SQL-specific testing, nhưng cần giới hạn scope và tài nguyên.

Đặc biệt:

- `@Transactional` test rollback DB không reset mọi static/ThreadLocal/Kafka state.
- Với `RANDOM_PORT`, client/test thread và server thread khác; test transaction không tự rollback server writes.
- Shared Testcontainers lifecycle có thể khiến mutated tests fail do resource stopped chứ không phải mutant.
- Context cache static trong một JVM không được reuse giữa PIT forked JVMs như một bảo đảm.
- Spring 6.2 có failure threshold; startup failure đầu tiên có thể khiến các contexts cùng key fail sớm về sau.
- Một test environment phụ thuộc random port/time/system properties làm score kém ổn định.

### 16.4. @DirtiesContext và mock reset

Nếu suite chứa `@DirtiesContext` sau từng method, PIT có thể reload context rất nhiều lần. Nếu @MockitoBean được reset mặc định sau method, không cần đóng cả context chỉ để xóa stubs.

Không chạy parallel các Spring tests có shared dirty context/mock override mà chưa hiểu race. Tăng PIT threads trên suite có @DirtiesContext/Testcontainers sẽ dễ tạo flaky KILLED/TIMED_OUT vì hạ tầng hơn là vì mã.

### 16.5. Kotlin, Lombok, generated code và records

Compiler tạo bytecode mà developer không trực tiếp viết. PIT mutate bytecode chứ không parse source theo ý định của bạn. Nếu một số mutants xuất hiện ở generated mapping/record/object methods, xem có ích hay không. Phạm vi sample chủ ý chỉ mutate ShippingQuoteService để tránh làm score bị chi phối bởi generated DTO methods.

Không lọc toàn bộ một package quan trọng chỉ vì score thấp. Scope/filter phải được review và ghi lại, nếu không metric có thể tăng “đẹp” do bạn bỏ những đoạn khó test.

## 17. Thiết kế mutation gate trong CI theo từng giai đoạn

### Giai đoạn 1 — Baseline, chưa chặn merge

- `./gradlew clean test` phải pass.
- `./gradlew pitest` chạy với targetClasses/targetTests đã chốt.
- Lưu HTML/XML report và version config.
- Ghi killed/survived/no coverage/error statuses.
- Xem các survivors critical và viết regression tests.
- Không tự đặt ngưỡng 90% mà chưa hiểu equivalent mutants/coverage gaps.
- Xác nhận CI thực thi task PIT, không bị skipped hoặc fail soft im lặng.

### Giai đoạn 2 — Ngưỡng có căn cứ

Khi baseline ổn định và reviewers đã triage những mutants quan trọng, có thể thiết lập ngưỡng ví dụ:

```groovy
pitest {
    mutationThreshold = 70
}
```

Đây chỉ là **một ví dụ cấu hình sau khi biết baseline**, không khuyến cáo mức 70 cho mọi nhóm. Với score thấp hơn threshold, PIT có thể fail task/build theo chính sách plugin. Để tránh fail giả, xác minh plugin version xử lý score, precision, timeout/errors và test selection như mong muốn.

Ngoài tổng score, nhóm có thể quy định:

- Không cho phép một `SURVIVED` mới ở payment/authorization/core financial rules mà chưa được review.
- Phải có negative test cho các trạng thái deny/reject.
- Không cho phép `NO_COVERAGE` trong changed critical domain branches.
- Báo cáo mỗi lần đổi mutator set hoặc target scope.
- Tránh hạ threshold/loại class chỉ để CI chuyển xanh.

### Giai đoạn 3 — Phân tầng job theo chi phí

Ví dụ pipeline:

```text
PR / merge request
      |
      +-- compile + unit + MVC/JPA integration tests
      |
      +-- PIT targeted critical pure/domain classes
      |       -> XML/HTML artifact
      |       -> agreed gate or reviewer action
      |
      +-- security/DB/container contract jobs
              (when relevant to changed code)

Nightly / scheduled
      |
      +-- broader PIT scope by module
      +-- compare trend + investigate survivors
      +-- retain reports for review
```

Bất kể CI dùng GitHub Actions, GitLab CI, Jenkins hay Buildkite, nguyên tắc là **regular tests phải chạy và pass trước**, PIT tasks không bị nuốt lỗi bằng `continue-on-error` không có kiểm soát, và report được lưu làm artifact. Nếu muốn incremental/changed-code mutation, phải kiểm tra chính xác PIT/Gradle extension hoặc workflow hỗ trợ; **đừng tự khẳng định Gradle plugin luôn tự chọn file thay đổi trong PR**.

### 17.1. Hạ tầng tái lập được

Ghim plugin/PIT/JUnit versions, dùng fixed test data, không gọi live production APIs, kiểm soát DB/container state và chạy trên JDK/Gradle hợp lệ. Nếu CI dùng shared runners, cân nhắc CPU contention và PIT timeouts. Tăng threads chỉ khi đã đo.

### 17.2. Ví dụ logic pipeline (không phụ thuộc nền tảng)

```bash
./gradlew clean test
./gradlew pitest
# Publish build/reports/pitest as a CI artifact.
```

Không giả mạo stdout hoặc job success trong tài liệu. Một build có PIT report nhưng bị lỗi load tests/engine không phải “mutation QA PASS”.

## 18. Theo dõi xu hướng và không làm đẹp chỉ số

Các metrics có thể hữu ích:

| Metric | Điều trả lời | Nguy cơ diễn giải sai |
|---|---|---|
| Killed mutants | Có bao nhiêu thay đổi được tests bắt | Không xét severity/biz criticality |
| Survived mutants | Thay đổi không bị phát hiện | Không phải tất cả là production bug |
| No coverage mutants | Vùng bị mutate không được test đi qua | Có thể do targetTests/engine config |
| Mutation score | Tỷ lệ tổng quát theo PIT scope/denominator | Đổi scope/mutators làm score mất tính so sánh |
| Test strength | Mức phát hiện trong phần có coverage | Bỏ qua uncovered critical paths |
| Runtime duration | Chi phí feedback trong CI | Không phản ánh test effectiveness |
| Error/timeout rate | PIT run có ổn định không | Đếm timeout giả là killed |
| Escaped critical mutants | Domain risk chưa được tests bắt | Phải triage theo severity |
| Coverage trend | Đo phạm vi thực thi code | High line coverage vẫn assertions yếu |

Để so sánh giữa hai lần chạy, giữ cố định project scope, target tests, mutator set, tool versions và assumptions về environment. Nếu thay một yếu tố, annotate baseline mới. Một score tăng từ 70 lên 85 có thể do added tests **hoặc** do loại những classes khó mutate khỏi target.

### 18.1. Không tối ưu bằng cách tắt mutation operators bừa bãi

Nếu PIT có nhiều survivors ở nhánh khó test, trước hết xem chúng có represent realistic faults không. Tắt operators chỉ để có score cao sẽ làm metric bớt hữu ích. Có thể dùng exclusions cho generated code, logs hoặc truly equivalent area khi có lý do; lưu rationale và áp dụng phạm vi hẹp.

### 18.2. Không dùng một mutation threshold cho mọi module

Một module math/pricing deterministic có thể đạt score cao và chạy nhanh; một module Spring Boot configuration/adapter với nhiều generated code có thể có nhiều mutants ít ý nghĩa hoặc cần integration setup rất nặng. Nên chọn scope/threshold theo domain risk và chi phí, ghi rõ chính sách per module. Tuy nhiên, không dùng khác biệt ấy để bỏ qua critical authorization/validation transitions.

## 19. Troubleshooting PIT và JUnit 5 trên Spring Boot

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `pitest` task không tồn tại | Gradle PIT plugin chưa áp dụng | Kiểm tra plugins block và Gradle sync |
| Không thấy JUnit tests | Thiếu `pitest-junit5-plugin` hoặc targetTests sai | junit5PluginVersion/runner classpath/test discovery |
| `No mutations found` | targetClasses không match production bytecode | Kiểm tra package FQN và compiled classes |
| `NO_COVERAGE` hàng loạt | Tests bị lọc, mock target, hoặc test không đi qua code | Xem targetTests và JUnit discovery |
| PIT process fail khi baseline JUnit pass | JUnit Platform/PIT plugin version conflict | Ghim/đối chiếu versions, xem root stack |
| `NoSuchMethodError` ở JUnit | Incompatible JUnit Platform/plugin | Chỉnh pair PIT/JUnit5 plugin/Boot BOM |
| Report score 0 dù tests xanh | Chỉ kiểm tra class không có assertions hoặc wrong tests selected | Xem generated mutants và test selection |
| Nhiều `SURVIVED` trên boundary | Thiếu exact threshold input | Test 9.999/10.000/10.001 |
| Nhiều `SURVIVED` trên return | Chỉ assert nonnull hoặc không assert fields | Assert business outcome |
| `TIMED_OUT` tăng khi tăng threads | CPU contention/test startup chậm | Giảm threads/điều chỉnh infra sau khi đo |
| `RUN_ERROR` | Invalid classpath, environment hoặc engine | Root logs, do not count as business detection |
| `MEMORY_ERROR` | PIT fork/heap/resource pressure | Giới hạn threads, đặt JVM heap khi cần |
| PIT trên @SpringBootTest rất chậm | Full context/DB/Testcontainers repeated | Target pure logic trước, integrate scope có chủ đích |
| Testcontainers bị dừng bất chợt | Lifecycle/test worker/fork mismatch | Stable container ownership/isolation |
| CI task bị UP-TO-DATE, không thấy report mới | Build caching/stale artifact path | Kiểm tra task execution, report timestamp |
| XML report không parse | Format/version/schema mismatch | Validate actual XML, không regex HTML |
| Score dao động | Timings, flaky tests, dynamic state, tool versions | Fix deterministic fixtures, pin versions |
| Mutation threshold chặn merge quá sớm | Baseline chưa triage/equivalent mutants | Giai đoạn học/baseline trước |
| Tất cả mutants bị filter out | Exclusion/scope cấu hình quá rộng | Review targetClasses/mutators |
| Service @Transactional không được test | Pure new Service bỏ proxy | Giữ Spring-managed integration test |
| MVC slice pass nhưng service mutants sống | Service bị @MockitoBean thay thế | Chọn real service test hoặc unit target |
| Test theo thứ tự làm score flaky | Shared mutable state | Independent tests, cleanup, no global mutation |
| Tăng coverage nhưng score không tăng | Tests chạy thêm lines nhưng assertions yếu | Mutant-level triage và stronger assertions |

## 20. Bài tập thực hành có lời giải

### A. Chỉ có line coverage 100%

Một service có 100% line coverage nhưng mutation score 42%. Điều đó chứng minh service sai không?

**Không.** Nó cho biết nhiều mutants trong scope chưa bị tests phát hiện. Xem first survivors/no coverage, đặt câu hỏi về input/expected output, triage equivalent mutants và criticality.

### B. Mutant đổi >= thành >

Một policy free shipping có điều kiện subtotal≥10.000. Test nào phân biệt original và mutant?

**Đúng 10.000.** Với 9.999 và 10.001 cả hai có thể trả cùng kết quả.

### C. SURVIVED nhưng đã cover line

Cần thêm test đi qua dòng ấy nữa không?

**Chưa chắc.** Trước hết xem input và assertion. Covering test đã chạy nhưng có thể chỉ assert notNull. Thêm một boundary/negative outcome assertion có ý nghĩa hơn gọi thêm một lần giống hệt.

### D. NO_COVERAGE cho method payment

Đó là lỗi PIT hay thiếu test?

Có thể là cả hai. Kiểm tra targetTests và test discovery; nếu chọn đúng tests mà không test nào gọi payment path, đó là gap thực.

### E. Equivalent mutant

Original `count>=1` và mutant `count>0` đối với integer. Có test nào kill được không?

**Không nếu đây là toàn bộ semantics được quan sát.** Ghi nhận tương đương thay vì thêm assertion vô lý.

### F. @WebMvcTest với mock service

PIT mutate service thật nhưng JUnit test chỉ dùng @MockitoBean service. Tại sao mutants không bị kill?

Vì controller gọi mock thay vì service implementation. Dùng pure JUnit tests cho policy hoặc full integration tests với real service.

### G. PIT mất nhiều phút trong SpringBootTest

Có phải tăng threads từ 2 lên 16 là giải pháp mặc định?

**Không.** Nếu nguyên nhân là startup/DB/fork/resource contention, tăng concurrency có thể làm worse. Bắt đầu bằng targetClasses/targetTests phù hợp và đo CPU/RAM/timeouts.

### H. 72% và 90% có mâu thuẫn không?

**Không nhất thiết.** Trong ví dụ 18 killed, 2 survived, 5 no coverage: overall score 18/25 = 72%, trong phần covered test strength = 18/(18+2) = 90%.

### I. MutationThreshold = 0

Có nghĩa tests đủ tốt chưa?

**Không.** Nó chỉ bỏ qua ngưỡng fail-build để thu baseline. Reviewer vẫn phải xem report và mutants quan trọng.

### J. Tất cả mutants đều KILLED

Có chứng minh JWT auth, security filters, PostgreSQL và TLS hoạt động không?

**Không.** Cần test các ranh giới ấy riêng. PIT score chỉ trong mutation target và selected tests.

### K. Tăng score bằng cách excludedClasses

Khi nào chấp nhận?

Khi excluded code thực sự generated/irrelevant/equivalent theo policy và có rationale kiểm chứng được. Không nên exclude pricing/security code chỉ vì mutants khó kill.

### L. PR thay đổi shipping policy và làm test lỗi

Nên sửa test expected hay production code?

Đầu tiên đối chiếu **business requirement**. Nếu policy mới đúng, cập nhật tests theo yêu cầu đã duyệt; nếu change vô ý sai, sửa production code. Mutation testing không tự quyết định nghiệp vụ nào đúng.

### M. TIMED_OUT ở CI nhưng không ở local

Có thể do điều gì?

CPU contention, JVM heap, PIT threads, Testcontainers startup và test flakiness. Điều tra environment và operator; không mặc định đó là “killed” đáng tin.

### N. Cần bật ALL mutators ngay không?

**Không.** Bắt đầu DEFAULTS, triage survivors và tối ưu test data/score. STRONGER/ALL có thể tăng chi phí/equivalent mutants, cần thử có kiểm soát.

### O. Cần mutation testing mỗi push không?

Tùy ngân sách feedback. Targeted critical mutation có thể ở PR; full/broader module có thể chạy theo lịch. Quan trọng là không để regressions quan trọng thoát vì test suite bị bỏ qua hoặc mutation job không thực sự chạy.

## 21. Checklist QA để triển khai mutation testing trong CI

- [ ] Có baseline JUnit suite chạy thực, tất cả critical tests pass.
- [ ] Chỉ rõ PIT engine/Gradle plugin/JUnit5 plugin và versions.
- [ ] Java 17+ và Spring Boot/Gradle test toolchain tương thích.
- [ ] Không ghi `latest` thay vì pinned artifact versions trong build CI.
- [ ] PIT JUnit 5 plugin nằm trên PIT tool classpath, không chỉ testImplementation.
- [ ] `targetClasses` trỏ đúng production code, không mutate tests.
- [ ] `targetTests` có covering tests thật, không mock mất target.
- [ ] Scope/mutator set được công bố trong báo cáo/baseline.
- [ ] Khởi động bằng DEFAULTS, không bật ALL không có lý do.
- [ ] Các validation boundaries 0/1, < / = / > được bao phủ khi có ý nghĩa.
- [ ] Positive và negative cases kiểm tra kết quả cụ thể.
- [ ] Assertions kiểm tra state/output/side effects thật, không chỉ notNull.
- [ ] Không dựa trên request status 200 khi cần kiểm chứng payload/authorization.
- [ ] Không lấy line coverage làm mutation evidence.
- [ ] Đã phân biệt KILLED, SURVIVED, NO_COVERAGE, TIMED_OUT, NON_VIABLE.
- [ ] Equivalent mutants có rationale chứ không auto-dismiss.
- [ ] Mutants critical được review theo severity/risk.
- [ ] MutationThreshold đặt sau khi đo baseline, không tùy tiện.
- [ ] Thay tool version/target scope thì tạo comparison baseline mới.
- [ ] Có HTML report để developers triage, XML cho CI/machine aggregation.
- [ ] CI thực thi cả test task lẫn pitest task theo policy.
- [ ] CI artifacts chứa actual reports, không báo pass khi task skipped.
- [ ] Mutation run không phụ thuộc credentials/real production APIs.
- [ ] Shared DB/Testcontainers/clock/random được kiểm soát.
- [ ] @SpringBootTest/@WebMvcTest/@DataJpaTest vẫn kiểm tra đúng contract riêng.
- [ ] Khi needed, integration tests giữ real Spring AOP/security/db behavior.
- [ ] Mutation threads phù hợp CPU/RAM và test isolation.
- [ ] Không dùng @DirtiesContext đại trà để giải quyết mutation flakiness.
- [ ] Không dùng exclusions để làm đẹp score thiếu kiểm soát.
- [ ] Build reports thể hiện executed/failed/skipped/error statuses rõ.
- [ ] Không tuyên bố đạt score cụ thể nếu chưa chạy PIT.
- [ ] Team có cách xử lý SURVIVED/NO_COVERAGE và việc ai review.
- [ ] CI phản hồi đủ nhanh để developers không bỏ qua mutation job.
- [ ] Bảo vệ regression tests quan trọng ngay cả khi score tổng đã vượt threshold.

## 22. Kết luận

**Mutation testing không hỏi “test có chạy qua code không?” mà hỏi “test có phản ứng khi code bị thay đổi sai không?”** PIT tạo variants trên bytecode, thực thi JUnit tests và chỉ rõ những thay đổi bị phát hiện hoặc bị bỏ sót.

Với Spring Boot:

- Dùng **unit mutation tests** cho nghiệp vụ thuần Java để có phản hồi nhanh.
- Giữ **MVC, JPA, security và full-context integration tests** khi các contracts phụ thuộc Spring/DB/HTTP.
- Đọc các status và triage từng mutant quan trọng, đừng thần thánh hóa một percentage.
- Test exact boundaries, failure paths và side effects thay vì chỉ assertions yếu.
- Bắt đầu bằng scoped target + DEFAULTS + pinned PIT/JUnit5 plugin versions.
- Đưa PIT vào CI theo **baseline → triage → agreed threshold → monitoring**, không áp ngưỡng tưởng tượng.
- Quản lý tốc độ và flakiness bằng deterministic fixtures, scopes phù hợp và kiểm tra report thật.

Ví dụ runnable có Java 17+, Spring Boot 3.5.16, Gradle PIT plugin 1.19.0, PIT 1.22.1, JUnit5 plugin 1.2.3 và **17 JUnit Jupiter methods** (12 unit/3 MVC slice/2 full-context). Đây là **bộ mã/kiểm thử thiết kế và rà soát theo tài liệu**, không phải bằng chứng đã thực sự chạy Gradle, JUnit hay PIT trong phiên soạn bài.

## 23. Tài liệu tham khảo chính thức

- [PIT — Basic Concepts](https://pitest.org/quickstart/basic_concepts/): bytecode mutation, running covering tests, KILLED/SURVIVED/NO_COVERAGE và other statuses.
- [PIT — Mutation Operators](https://pitest.org/quickstart/mutators/): built-in mutators, default/stronger operator groups.
- [PIT — Maven Quick Start and Parameters](https://pitest.org/quickstart/maven/): targetClasses/targetTests, mutationThreshold, testStrengthThreshold, report formats và Maven goal.
- [PIT — FAQ](https://pitest.org/faq/): equivalent mutants, timeout fluctuations, recommendations about ALL operators.
- [Gradle PIT Plugin — Official Documentation](https://gradle-pitest-plugin.solidsoft.info/): Gradle plugin 1.19.0, junit5PluginVersion, pitestVersion, targetClasses, reports và test-process options.
- [Gradle Plugin Portal — info.solidsoft.pitest](https://plugins.gradle.org/plugin/info.solidsoft.pitest): plugin version availability.
- [PIT JUnit 5 Plugin — Official Repository](https://github.com/pitest/pitest-junit5-plugin): plugin version 1.2.3, minimum PIT engine requirement and runtime integration notes.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): SpringBootTest, MockMvc, test slices and context behavior.
- [Spring Boot 3.5.16 release notes](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/): release and support-lifecycle context.
- [JUnit 5 — User Guide](https://docs.junit.org/5.13.0/user-guide/): JUnit Jupiter, assertions, extensions and test discovery.
