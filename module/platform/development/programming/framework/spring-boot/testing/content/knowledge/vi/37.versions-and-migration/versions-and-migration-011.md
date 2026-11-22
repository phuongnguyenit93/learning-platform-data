# Giữ ma trận hành vi làm chuẩn khi refactor hoặc nâng cấp bộ kiểm thử

## 1. Vì sao một test suite xanh sau refactor vẫn có thể là regression?

Một dự án Spring Boot chuẩn bị chuyển từ các lớp `@SpringBootTest` nặng sang unit test và test slices. Hoặc đội phát triển nâng Spring Boot 3.5 lên 4.x, chuyển JUnit/test dependencies, đổi Mockito bean override và cập nhật imports. Sau đó Gradle báo toàn bộ tests xanh. Có thể kết luận không thay đổi behavior không?

**Chưa.** Test suite có thể xanh vì:

- Một assertion quan trọng đã bị xóa khi tách lớp kiểm thử.
- Controller được mock cả service và repository, nên không còn test nào phát hiện sai wiring thật.
- JSON response đổi field name nhưng test mới chỉ kiểm tra HTTP 200.
- `@Valid` bị bỏ sót, request sai dữ liệu vẫn đi xuống service.
- JPA slice dùng database khác và không phát hiện lỗi query dialect.
- Test mới dựa vào một mock được stub trả giá trị đúng, không chạy logic cần bảo vệ.
- Các tests quan trọng bị filtered/skipped hoặc không được CI discover.
- Snapshot/expected output được cập nhật hàng loạt mà chưa xác minh thay đổi có chủ đích.
- Refactor làm mất test security/transaction/real HTTP vốn trước đây phát hiện được lỗi.

Để tránh mất chứng cứ khi thay đổi **cách kiểm thử**, ta cần một chuẩn độc lập với **framework version, lớp test và annotation**: **ma trận hành vi (behavior matrix)**. Mỗi dòng mô tả một hợp đồng mà hệ thống phải giữ, đầu vào hoặc sự kiện kích hoạt, kết quả quan sát được, phạm vi dữ liệu và test nào là bằng chứng. Trong quá trình chuyển đổi, ma trận là **chuẩn đối chiếu**; test code chỉ là cách hiện thực bằng chứng cho từng dòng.

> **Không dùng “tất cả tests pass” làm tiêu chí duy nhất. Hãy hỏi “mọi hành vi bắt buộc trong ma trận còn có bằng chứng hiệu lực không?”**

Bài học thuộc nhóm **Phiên bản và chuyển đổi**, đề bài **“Giữ ma trận hành vi làm chuẩn khi refactor hoặc nâng cấp bộ kiểm thử”**.

### Mục tiêu

Sau bài này, bạn có thể:

1. Xây ma trận từ yêu cầu, bug lịch sử, public API, integration contracts và business invariants.
2. Gắn mã ổn định `B01`, `B02`... cho hành vi mà **không** gắn cứng với tên test method.
3. Phân biệt **hợp đồng bên ngoài** với chi tiết implementation có thể đổi khi refactor.
4. Xác định owner test ở unit, MVC slice, JPA slice, full-context hoặc real HTTP.
5. Dùng negative/boundary cases để phát hiện đúng loại regression.
6. Thực hiện baseline → dual-run → chuyển ownership → chạy suite/gate → loại test dư thừa.
7. Tách intentional behavior change khỏi regression và infrastructure/test-harness change.
8. So các mốc nâng Spring Boot 3.5 → 4.x mà không giả định imports/dependencies giữ nguyên.
9. Tránh dùng snapshot cập nhật tự động làm bằng chứng giả.
10. Theo dõi CI test discovery, skip counts, context cache, isolation, flaky tests và rollback.
11. Áp dụng ví dụ Java 17+, Spring Boot **3.5.16**, Gradle, JUnit Jupiter có **25 @Test methods** trên bốn tầng, liên kết về một ma trận.
12. Chứng minh rằng ma trận hành vi là **một tài sản kiểm thử có phiên bản**, không chỉ một bảng đẹp trong tài liệu.

**Lưu ý phiên bản:** Mẫu mã biên dịch được thiết kế cho **Spring Boot 3.5.x / Spring Framework 6.x / Java 17+**. Spring Boot 4.0 đã modularize test modules/packages/starter names; phần nâng cấp nêu cách di trú, nhưng **mã demo 3.5 không được tuyên bố chạy nguyên imports trên Boot 4**. Khi nâng, lấy chính các dòng ma trận làm tiêu chuẩn để viết lại test adapters.

## 2. Một dòng ma trận hành vi phải nêu được điều gì?

Ma trận nên mô tả **behavior có thể quan sát và kiểm chứng**, thay vì chỉ tên test hoặc coverage percentage.

| Trường | Mục đích | Ví dụ |
|---|---|---|
| `ID` | Định danh lâu dài | `B08` |
| `Contract` | Hành vi bất biến | Tổng hàng ≥ 10.000 thì phí giao = 0 |
| `Stimulus/input` | Đầu vào kích hoạt | subtotal = 10.000, itemCount = 2, member = false |
| `Expected observable` | Kết quả đo được | shipping = 0, total = 10.000 |
| `Boundary/negative` | Trường hợp phân biệt hành vi | 9.999 và 10.001 |
| `Owner layer` | Nơi chứng minh chính | Unit policy |
| `Cross-layer evidence` | Chứng cứ nối tầng nếu cần | MockMvc full-context |
| `Old evidence` | Test trước refactor/nâng cấp | LegacyQuoteSpringBootTest |
| `New evidence` | Test mới chịu trách nhiệm | QuotePolicyTest.b08... |
| `State` | COVERED/GAP/INTENTIONAL_CHANGE | COVERED |
| `Why/source` | Yêu cầu, quyết định, bug | Rule vận hành về miễn phí giao |

**Không bắt buộc mọi dự án cần đủ 11 cột**; quan trọng là người review có thể trả lời: *Nếu ai đó cố tình làm sai điều kiện này, test nào sẽ fail?* Và *sau khi đổi Spring Boot/JUnit/Mockito, điều đó còn đúng không?*

### 2.1. Hai kiểu thay đổi khác nhau

**Thay cách kiểm thử:** đổi `@SpringBootTest` sang `@WebMvcTest`, thay `@MockBean` bằng `@MockitoBean`, thay test assertion API, nâng plugin. **Expected behavior giữ nguyên**.

**Thay hành vi sản phẩm:** nghiệp vụ quyết định giảm ngưỡng miễn phí giao từ 10.000 xuống 8.000. **Expected behavior có thể đổi**, nhưng phải có yêu cầu/approval/migration notes. Không được lén đổi expected để một test pass.

### 2.2. Ma trận là chuẩn, không phải test file

Một tên test có thể thay từ `shouldCreate()` sang `b12_postReturnsCreated()`. Một framework assertion có thể đổi từ Hamcrest sang AssertJ. Cả hai thay đổi này **không phải** lý do xóa hợp đồng `B12`.

Nếu một hợp đồng không còn áp dụng, đánh dấu `RETIRED` kèm quyết định và lý do. Đừng âm thầm xóa dòng rồi để tổng số tests/coverage tăng “đẹp”.

## 3. Xây ma trận từ nguồn đáng tin cậy

Một ma trận không thể được tạo chính xác chỉ bằng cách liệt kê những tests hiện có. Tests cũ có thể đã thiếu negative cases hoặc kiểm tra nhầm implementation detail. Nguồn nên gồm:

1. Business requirements, acceptance criteria và public API specifications.
2. Các lỗi sản xuất từng xảy ra; behavior mà regression test phải tiếp tục bắt.
3. Spring MVC request/response contracts: status, headers, JSON, validation, errors.
4. Data rules: schema, unique constraints, query predicates, transaction semantics.
5. Security contracts: anonymous/authorized/forbidden, CSRF, filters, method authorization.
6. Configuration contracts: profiles, `@ConfigurationProperties` defaults/validation, conditional beans.
7. External contracts: HTTP/Kafka/DB protocol, retry and idempotency behaviors.
8. Định nghĩa timing/ordering khi thật sự có SLA hoặc concurrency invariant.
9. Các test hiện hữu, để biết hiện tại đã bảo vệ điều gì và chỗ nào đang bỏ sót.
10. Change log và migration guide của framework, để chủ động kiểm tra vùng rủi ro.

**Không bê test behavior đang sai thành chuẩn chỉ vì test đó tồn tại lâu.** Đối chiếu yêu cầu trước khi đóng băng expected.

### 3.1. Ưu tiên theo mức độ rủi ro

| Mức | Ví dụ | Yêu cầu bằng chứng |
|---|---|---|
| Critical | Tiền, số dư, quyền truy cập, idempotent payment | Negative, boundary, real integration khi cần |
| High | API errors, transaction boundaries, DB mappings | Test đúng layer + cross-layer path |
| Medium | Formatting, optional defaults, read-only queries | Unit/slice phù hợp |
| Low | Log message, internal helper detail | Chỉ test nếu là contract thật |

Không dùng mức rủi ro để miễn kiểm thử các behavior bắt buộc; dùng nó để quyết định kiểm thử ở những ranh giới nào và review kỹ tới đâu.

## 4. Ma trận chuẩn của một tính năng ví dụ

Để thực hành, ta xây một API tạo báo giá. **Chính sách nghiệp vụ của ví dụ**, không đại diện cho giá/điều kiện vận chuyển của doanh nghiệp thật:

- `subtotalCents` không âm.
- `itemCount` phải ≥ 1.
- Nếu `member=true`, phí giao = 0.
- Nếu tổng hàng ≥ 10.000, phí giao = 0.
- Nếu không miễn phí và có từ 3 món, phí giao = 300.
- Nếu không miễn phí và có 1–2 món, phí giao = 500.
- `totalCents = subtotalCents + shippingCents`.
- POST /api/quotes chấp nhận JSON hợp lệ, trả 201 và Location.
- GET /api/quotes/{id} trả báo giá đã lưu hoặc lỗi 404 ổn định.
- Request thiếu/bất hợp lệ trả 400 với error code ổn định.
- Repository lưu/đọc và truy vấn ngưỡng tổng tiền.
- Full-context path phải nối controller → service → repository **thật**.

### 4.1. Ma trận bắt buộc

| ID | Input/điều kiện | Expected behavior | Owner chính |
|---|---|---|---|
| B01 | subtotal = -1 | Từ chối số âm | Unit |
| B02 | count = 0 hoặc -1 | Từ chối số lượng không dương | Unit |
| B03 | subtotal 2.000; count 1; member false | shipping 500; total 2.500 | Unit |
| B04 | subtotal 2.000; count 2; member false | shipping 500; total 2.500 | Unit |
| B05 | subtotal 2.000; count 3; member false | shipping 300; total 2.300 | Unit |
| B06 | subtotal 2.000; count 4; member false | shipping 300; total 2.300 | Unit |
| B07 | subtotal 9.999; count 2; member false | shipping 500; total 10.499 | Unit |
| B08 | subtotal 10.000; count 2; member false | shipping 0; total 10.000 | Unit + seam |
| B09 | subtotal 10.001; count 2; member false | shipping 0; total 10.001 | Unit |
| B10 | subtotal 1; count 1; member true | shipping 0; total 1 | Unit |
| B11 | subtotal 0; count 1; member false | Hợp lệ; shipping 500; total 500 | Unit |
| B12 | POST JSON hợp lệ | 201; Location; body có id và totals | MVC slice + seam |
| B13 | POST thiếu subtotal/count hoặc count=0 | 400; code INVALID_REQUEST; không gọi service/ghi DB | MVC slice + seam |
| B14 | GET id có trong repository | 200; JSON trùng báo giá đã lưu | MVC slice + seam |
| B15 | GET id không tồn tại | 404; code QUOTE_NOT_FOUND | MVC slice + seam |
| B16 | Persist entity và query total≥10.000 | ID/columns đúng; boundary inclusive | JPA slice |
| B17 | POST → service thật → JPA thật → GET | End-to-end bean wiring trong MockMvc full-context | Full seam |
| B18 | POST JSON sai cú pháp | 400; code MALFORMED_JSON | MVC slice |

**Vấn đề cần chú ý:** B13 có *nhiều trường hợp con*; mỗi input thiếu/sai nên có test riêng để failure rõ nguyên nhân. Một dòng ma trận có thể ánh xạ nhiều test methods. Ngược lại, một full-context test có thể chứng minh cùng lúc B08, B12, B14, B16 và B17. **Không có quy luật mỗi ID đúng một @Test.**

### 4.2. Những thứ chưa thuộc ma trận demo

Demo dùng H2, MockMvc, không Spring Security, không Docker/Kafka và không real HTTP socket. Vì thế nó **không** chứng minh PostgreSQL dialect, JWT authorization, TLS, transaction across HTTP server threads hoặc external broker delivery. Nếu đây là requirements của ứng dụng thực, phải thêm các dòng hành vi và integration tests thích hợp; không đánh dấu COVERED dựa trên những tests demo.

## 5. Phân lớp bằng chứng: một test nhanh không tự thay mọi integration test

| Layer | Điều test thấy | Điều thường không thấy |
|---|---|---|
| Pure JUnit unit | Java branching, output, exception, side-effect qua fake/mock | Spring bean scan/AOP/HTTP/SQL |
| `@WebMvcTest` | MVC route, JSON binding, validation, status, advice | Real service nếu `@MockitoBean` thay |
| `@DataJpaTest` | JPA mapping, derived query, DataSource/transaction slice | Controller/service cross-layer behavior |
| `@SpringBootTest` + MockMvc | Spring-managed beans, MVC in-process, repository thật | TCP socket/server port/TLS |
| `@SpringBootTest(RANDOM_PORT)` | Real embedded HTTP server/client boundary | Không tự bảo đảm external systems đúng |
| Contract/external integration | Protocol/DB/broker behavior với service thật | Không thay pure unit edge cases |

Cần **duy trì ma trận xuyên các lớp**; không lấy số lượng unit tests tăng làm lý do bỏ hết full-context seam tests.

### 5.1. Đặt ownership theo behavior, không theo công cụ

Ví dụ `B08` về ngưỡng 10.000 thuộc policy unit test là owner chính. Một full seam test lặp lại đúng ngưỡng giúp chứng minh controller→service→JPA đang dùng policy thật, không bị mock hoặc override. Nhưng không cần chạy full Spring context cho tất cả các giá trị 9.999/10.000/10.001 nếu unit coverage đủ và seam đã chứng minh wiring.

### 5.2. Nếu bỏ MockMvc full-context sẽ mất gì?

Một `@WebMvcTest` với `@MockitoBean QuoteService` vẫn có thể chứng minh status/JSON, nhưng **không chứng minh** service bean thật tồn tại, repository được inject hoặc Spring AOP transaction advice hoạt động. Nếu ma trận có B17, phải có test nào đó còn đi qua real beans.

### 5.3. Nếu chuyển PostgreSQL sang H2 thì sao?

Một query chạy trên H2 chỉ chứng minh query hoạt động trên H2. Nếu production có JSONB, collation, custom indexes, locks hoặc vendor-specific SQL, thêm behavior matrix rows cho đúng production database và dùng Testcontainers/real-dialect tests. Không ghi chung “JPA đã được kiểm tra” nếu chưa bao phủ ranh giới đó.

## 6. Điều gì dễ đổi khi nâng cấp Spring Boot và thư viện test?

### 6.1. Nâng Spring Boot 3.5 lên 4.x

Spring Boot 4.0 migration guide cho thấy **module/test starter được modularize**. Một số ví dụ quan trọng:

| Hạng mục | Spring Boot 3.5 | Khi nâng Boot 4.x cần kiểm tra |
|---|---|---|
| Web starter | `spring-boot-starter-web` | `spring-boot-starter-webmvc` là tên được khuyến nghị |
| Test dependencies | `spring-boot-starter-test` thường đủ cho nhiều stacks | Technology-specific test starters, ví dụ `spring-boot-starter-webmvc-test`, `spring-boot-starter-data-jpa-test` |
| Test annotations | `org.springframework.boot.test.autoconfigure...` | Package test autoconfiguration theo technology module mới |
| MVC test in full context | `@AutoConfigureMockMvc` trong demo | Xác nhận có module và annotation phù hợp |
| Mock annotations | Boot `@MockBean` deprecated từ Boot 3.4 | Ưu tiên Spring Framework `@MockitoBean`; review migration |
| Mockito plain @Mock | Có thể phụ thuộc listener/harness cũ trong một số tests | Dùng `MockitoExtension` cho pure Mockito tests |
| JSON mapping | Jackson 2 thường được Boot 3.5 dùng | Boot 4 mặc định Jackson 3; xem serialization/migrations |
| Rest test clients | MockMvc/TestRestTemplate tùy test setup | API/test auto-config thay đổi; kiểm tra docs/guide |
| JPA/validation | Boot-managed Hibernate/Validator | Xem schema/query/constraint behavior sau dependency changes |

**Không sử dụng bảng làm một script đổi imports tự động.** Từng module/config cần kiểm tra migration guide của exact target release; Spring Boot 4.0 có các “classic starters” để hỗ trợ chuyển dần, nhưng đó là bước trung gian chứ không phải chuẩn cuối.

Mặc dù mã test có thể đổi package hoàn toàn, **B01–B18 vẫn phải giữ expected behavior** nếu sản phẩm không thay đổi yêu cầu. Chỉ những thay đổi đã được phê duyệt mới cập nhật ma trận.

### 6.2. Jakarta, Mockito, JUnit, Jackson cũng ảnh hưởng contract

Nâng dependency có thể làm thay đổi:

- Constraint validation và exception wrappers.
- Error JSON mặc định, timestamp, null serialization, enum naming, date/time formatting.
- Matching các Mockito stubbings, mock reset behavior, bean override qualifiers.
- Test engine discovery, parameterized test source, extension initialization.
- JDBC/Hibernate SQL generation, schema validation, transaction semantics.
- Spring TestContext cache key và context customizers.
- Assertion library API (nhưng assertion **hợp đồng** vẫn phải giữ).
- Runtime Java baseline; dùng đúng JDK/toolchain cho branch mục tiêu.

**Đừng kiểm tra chỉ việc compile.** Một test adapter được chỉnh imports thành công vẫn có thể bỏ mất assertion field/status hoặc thay production bean bằng mock không đúng phạm vi.

### 6.3. Ghi “phiên bản nào đang là chuẩn”?

Một dự án có thể lưu metadata tối thiểu trong README/ADR:

```text
Behavior matrix revision: 2026-11
Production API contract revision: checkout-quotes-v1
Baseline runtime: Java 17 / Spring Boot 3.5.x
Target runtime: Java supported by target Boot 4.x release
Test tools: JUnit Jupiter + Spring TestContext + Mockito
Behavior decision: B01-B18 unchanged
Known exception: none (or approved change ID)
```

Đây là **mẫu metadata**, không phải tình trạng dự án cụ thể. Không nên dùng bản test đang nâng cấp làm nguồn duy nhất cho expected results; nếu cần, tham chiếu yêu cầu/ADR đã duyệt.

## 7. Quy trình chuyển đổi có thể kiểm toán

### Bước 1 — Chụp baseline hành vi

Trước khi sửa annotation/dependencies, chạy **toàn bộ test suite gốc** trên đúng commit, JDK và runtime đã biết. Ghi:

- Behavior IDs đang được chứng minh.
- JUnit executed/passed/failed/skipped counts.
- HTTP status, headers, body fields, validation error codes.
- Database query/transaction expectations.
- Security/auth/error contracts.
- Những tests bị disabled, flaky hoặc chỉ pass khi chạy theo thứ tự.
- Toolchain versions và CI job names.
- Raw JUnit XML/HTML, logs đã redact và test artifact links.

Nếu baseline đang fail, **không** đặt một mốc “100% pass” giả. Ghi lỗi/ngoại lệ rõ và phân biệt known preexisting defect với regression của upgrade.

### Bước 2 — Lập ma trận/owner cũ

Gắn mỗi hành vi Bxx với method/suite hiện tại. Những dòng không có test cần đánh dấu GAP, không tự đánh dấu COVERED chỉ vì developer nhớ có ai đó từng kiểm tra.

### Bước 3 — Viết tests mới trong khi giữ tests cũ

Triển khai unit/slice/full seam theo owner mới. **Chạy cả hai** trong cùng mốc source khi khả thi. Khi nâng major framework, có thể cần hai branches/JDKs riêng; chạy baseline trên branch cũ và target trên branch mới, nhưng **cùng expected behavior matrix revision**.

### Bước 4 — Kiểm tra tương đương hành vi, không chỉ pass count

Một test cũ và một test mới có thể cùng pass nhưng kiểm tra đầu vào khác nhau. So **từng ID**: stimulus, boundary, negative state, expected observable và ranh giới system under test còn thực thi. Nếu đổi fixture/source data, chứng minh vì sao đó vẫn là cùng case.

### Bước 5 — Chỉ bỏ test cũ khi ma trận đã có owner mới

Nếu chuyển logic B01–B11 sang unit tests, các edge cases được chuyển đầy đủ. Giữ B17 ở full-context hoặc thay bằng integration test khác chứng minh same seam. Bỏ một test trùng lặp là hợp lý; bỏ behavior là mất coverage.

### Bước 6 — Chạy đúng CI gates

Chạy compile + unit + MVC/JPA slices + full integration smoke + security/external jobs khi áp dụng. Đọc **JUnit XML test counts**, không chỉ Gradle task green hoặc cached. So mutation/coverage trends khi phù hợp; một score cao không chứng minh matrix completeness.

### Bước 7 — Chốt migration decision

Ghi:

- ID nào unchanged.
- ID nào intentionally changed (link requirement/approval).
- ID nào known GAP và action/owner.
- Version/build changes.
- Evidence links của baseline và target.
- CI execution counts/time.
- Ngày review và người chịu trách nhiệm cập nhật ma trận.

## 8. Ví dụ chạy được: build, file tree và môi trường

Để không chỉ là lý thuyết, phần này tạo một ứng dụng REST + domain rule + Spring Data JPA, bốn test suites tương ứng với ma trận.

**Bản dùng để biên soạn ví dụ:** Java 17+, Spring Boot 3.5.16, JUnit Jupiter, AssertJ, Mockito, H2. **Mã đầy đủ cho các file liệt kê dưới đây**, không yêu cầu Kafka, Docker hay external HTTP server.

### 8.1. Cây file

```text
behavior-contract-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/contract/
    │   │   ├── ContractDemoApplication.java
    │   │   ├── PriceBreakdown.java
    │   │   ├── QuotePolicy.java
    │   │   ├── QuoteEntity.java
    │   │   ├── QuoteRepository.java
    │   │   ├── QuoteResult.java
    │   │   ├── QuoteService.java
    │   │   ├── QuoteRequest.java
    │   │   ├── QuoteController.java
    │   │   ├── QuoteNotFoundException.java
    │   │   ├── ApiError.java
    │   │   └── QuoteErrorHandler.java
    │   └── resources/application.properties
    └── test/java/com/example/contract/
        ├── QuotePolicyTest.java
        ├── QuoteControllerWebMvcTest.java
        ├── QuoteRepositoryDataJpaTest.java
        └── QuoteFlowSpringBootTest.java
```

### 8.2. Gradle Groovy DSL

**File `settings.gradle`:**

```groovy
rootProject.name = 'behavior-contract-demo'
```

**File `build.gradle`:**

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Demo dễ quan sát và tránh nhiều JVM forks.
    maxParallelForks = 1
    forkEvery = 0
}
```

**File `src/main/resources/application.properties`:**

```properties
# Demo local only; do not deploy H2 credentials/settings to production.
spring.datasource.generate-unique-name=true
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
```

H2 runtime dependency và embedded database auto-configuration cho phép test JPA/full-context không cần Docker. `generate-unique-name=true` giúp mỗi DataSource embedded mới có tên khác, tránh tình trạng các cached test contexts vô tình dùng cùng H2 in-memory DB. Schema được Hibernate tạo/xóa cho demo; production nên dùng migrations và kiểm tra trên đúng database engine khi cần.

**Lưu ý:** `build.gradle` không tự tạo Gradle Wrapper; cần có Gradle phù hợp để chạy `gradle test` hoặc tạo wrapper. Trong một dự án thật, H2/ddl-auto settings nên thuộc **test configuration** thay vì production application.properties; bài để trong main resources chỉ nhằm chạy demo độc lập.

### 8.3. Tổng phương thức kiểm thử

| Lớp | @Test methods | Test boundary |
|---|---:|---|
| `QuotePolicyTest` | 12 | Pure Java unit |
| `QuoteControllerWebMvcTest` | 7 | MVC slice, mock service |
| `QuoteRepositoryDataJpaTest` | 3 | JPA slice, embedded H2 |
| `QuoteFlowSpringBootTest` | 3 | Full Spring context + MockMvc + JPA |
| **Tổng** | **25** | B01–B18, với một số ID có nhiều tests |

**Một method không luôn bằng một case** khi dùng `@ParameterizedTest`. Mẫu cố ý dùng `@Test` độc lập để việc mapping ID và test report dễ theo dõi; sau đó có thể chuyển sang parameterized tests mà không đổi behavior matrix.

## 9. Production code: application và price policy

### 9.1. Application entrypoint

**File `src/main/java/com/example/contract/ContractDemoApplication.java`:**

```java
package com.example.contract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractDemoApplication.class, args);
    }
}
```

### 9.2. Immutable breakdown

**File `src/main/java/com/example/contract/PriceBreakdown.java`:**

```java
package com.example.contract;

public record PriceBreakdown(
        int subtotalCents,
        int shippingCents,
        int totalCents
) {}
```

Java record có value-based equals/hashCode nên unit tests có thể so toàn bộ fields với expected record. Nó không bảo đảm mọi serialization contract; MVC tests vẫn phải xác minh JSON.

### 9.3. Pure policy được Spring quản lý nhưng test độc lập được

**File `src/main/java/com/example/contract/QuotePolicy.java`:**

```java
package com.example.contract;

import org.springframework.stereotype.Component;

@Component
public class QuotePolicy {

    public PriceBreakdown price(
            int subtotalCents, int itemCount, boolean member) {

        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be nonnegative");
        }

        if (itemCount <= 0) {
            throw new IllegalArgumentException(
                    "itemCount must be positive");
        }

        int shippingCents;

        if (member || subtotalCents >= 10_000) {
            shippingCents = 0;
        }
        else if (itemCount >= 3) {
            shippingCents = 300;
        }
        else {
            shippingCents = 500;
        }

        return new PriceBreakdown(
                subtotalCents,
                shippingCents,
                Math.addExact(subtotalCents, shippingCents));
    }
}
```

**Behavior chính:** B01–B11. Class được `@Component` để full context inject vào service, nhưng pure unit tests có thể gọi `new QuotePolicy()` vì rule **không dùng Spring proxy/configuration**. Không được áp dụng cách đó cho class mà contract phụ thuộc `@Transactional`, `@PreAuthorize`, `@Cacheable` hoặc environment injection.

### 9.4. Boundary cases là chìa khóa của ma trận

Nếu refactor đổi `subtotalCents >= 10_000` thành `subtotalCents > 10_000`, B07/B09 có thể vẫn pass, **B08 phải fail**. Nếu đổi `itemCount >= 3` thành `itemCount > 3`, B05 phải fail. Nếu đảo `member` condition, B10 phải fail. Nếu đổi phí 500 thành 0, B03/B04/B07/B11 phải fail.

Ma trận không cần biết code dùng ternary, if/else, switch hay một lookup table; nó chỉ biết **đầu vào và kết quả phải đúng**.

## 10. Production code: JPA persistence và service

### 10.1. Entity và mapping

**File `src/main/java/com/example/contract/QuoteEntity.java`:**

```java
package com.example.contract;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "quote_records")
public class QuoteEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "subtotal_cents", nullable = false)
    private int subtotalCents;

    @Column(name = "shipping_cents", nullable = false)
    private int shippingCents;

    @Column(name = "total_cents", nullable = false)
    private int totalCents;

    protected QuoteEntity() {
        // JPA constructor.
    }

    public QuoteEntity(
            int subtotalCents,
            int shippingCents,
            int totalCents) {
        this.subtotalCents = subtotalCents;
        this.shippingCents = shippingCents;
        this.totalCents = totalCents;
    }

    public Long getId() {
        return id;
    }

    public int getSubtotalCents() {
        return subtotalCents;
    }

    public int getShippingCents() {
        return shippingCents;
    }

    public int getTotalCents() {
        return totalCents;
    }
}
```

Không test ID bằng giá trị cứng như 1 nếu nó là generated ID; chỉ cần xác nhận non-null/positive và dùng chính ID trả về cho GET. Đừng tạo database fixtures phụ thuộc thứ tự AUTO_INCREMENT giữa các tests.

### 10.2. Spring Data JPA repository

**File `src/main/java/com/example/contract/QuoteRepository.java`:**

```java
package com.example.contract;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface QuoteRepository
        extends JpaRepository<QuoteEntity, Long> {

    List<QuoteEntity> findByTotalCentsGreaterThanEqual(
            int minTotalCents);
}
```

Method này dùng **inclusive boundary**. Việc nâng version Spring Data/Hibernate có thể ảnh hưởng SQL generation; JPA slice giúp kiểm tra behavior trên H2 trong demo. Nếu sản phẩm dùng dialect khác, owner của B16 phải chạy với đúng engine để đảm bảo tương thích.

### 10.3. DTO response và missing exception

**File `src/main/java/com/example/contract/QuoteResult.java`:**

```java
package com.example.contract;

public record QuoteResult(
        long id,
        int subtotalCents,
        int shippingCents,
        int totalCents
) {}
```

**File `src/main/java/com/example/contract/QuoteNotFoundException.java`:**

```java
package com.example.contract;

public class QuoteNotFoundException
        extends RuntimeException {

    public QuoteNotFoundException(long id) {
        super("Quote " + id + " not found");
    }
}
```

Không bắt client so nguyên văn exception message vì nó là internal implementation detail. HTTP client chỉ cần code ổn định `QUOTE_NOT_FOUND` và 404 từ controller advice.

### 10.4. Spring service thực

**File `src/main/java/com/example/contract/QuoteService.java`:**

```java
package com.example.contract;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class QuoteService {

    private final QuotePolicy policy;
    private final QuoteRepository repository;

    public QuoteService(
            QuotePolicy policy, QuoteRepository repository) {
        this.policy = policy;
        this.repository = repository;
    }

    @Transactional
    public QuoteResult create(
            int subtotalCents, int itemCount, boolean member) {

        PriceBreakdown amount =
                policy.price(subtotalCents, itemCount, member);

        QuoteEntity saved = repository.save(
                new QuoteEntity(
                        amount.subtotalCents(),
                        amount.shippingCents(),
                        amount.totalCents()));

        return fromEntity(saved);
    }

    @Transactional(readOnly = true)
    public QuoteResult get(long id) {
        if (id <= 0) {
            throw new QuoteNotFoundException(id);
        }
        return repository.findById(id)
                .map(QuoteService::fromEntity)
                .orElseThrow(() ->
                        new QuoteNotFoundException(id));
    }

    private static QuoteResult fromEntity(QuoteEntity e) {
        return new QuoteResult(
                e.getId(),
                e.getSubtotalCents(),
                e.getShippingCents(),
                e.getTotalCents());
    }
}
```

**Vì sao không chỉ dùng unit test cho service?** `@Transactional` hoạt động qua Spring-managed proxy. `new QuoteService(...)` không chứng minh transaction interceptor. B17 dùng full Spring context để kiểm chứng wiring và đường persistence. Đối với rollback/commit propagation phức tạp, cần các test riêng, không tuyên bố B17 bao phủ mọi transaction semantics.

## 11. Production code: HTTP contract và error codes

### 11.1. Validated request

**File `src/main/java/com/example/contract/QuoteRequest.java`:**

```java
package com.example.contract;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record QuoteRequest(
        @NotNull @Min(0) Integer subtotalCents,
        @NotNull @Min(1) Integer itemCount,
        boolean member
) {}
```

Dùng `Integer` thay vì primitive cho hai required fields giúp `@NotNull` phân biệt **thiếu key** và giá trị 0. Với primitive `int`, thiếu key có thể trở thành 0; nếu 0 lại hợp lệ (subtotal), một request thiếu subtotal có thể bị chấp nhận sai. Contract B13 yêu cầu missing subtotal bị 400.

### 11.2. API error response

**File `src/main/java/com/example/contract/ApiError.java`:**

```java
package com.example.contract;

public record ApiError(
        String code,
        String message
) {}
```

Trong ma trận B13/B15/B18, **code và HTTP status** là hợp đồng. Message có thể thay đổi khi localization, nhưng bài mẫu chọn message cố định để dễ kiểm chứng. Không assert toàn bộ stack trace hoặc localized Hibernate Validator message.

### 11.3. REST controller

**File `src/main/java/com/example/contract/QuoteController.java`:**

```java
package com.example.contract;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<QuoteResult> create(
            @Valid @RequestBody QuoteRequest request) {

        QuoteResult result = service.create(
                request.subtotalCents(),
                request.itemCount(),
                request.member());

        URI location = URI.create("/api/quotes/" + result.id());

        return ResponseEntity.created(location)
                .body(result);
    }

    @GetMapping("/{id}")
    public QuoteResult get(@PathVariable long id) {
        return service.get(id);
    }
}
```

Spring MVC sử dụng Jackson để deserialize request record và serialize response record. Controller không tự tính phí; policy vẫn nằm trong service. HTTP test B12/B14 phải thấy JSON fields/status/Location; unit policy test không thể chứng minh route/serialization.

### 11.4. Stable exception handling

**File `src/main/java/com/example/contract/QuoteErrorHandler.java`:**

```java
package com.example.contract;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class QuoteErrorHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> validationError(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_REQUEST",
                        "Request validation failed"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> malformedJson(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "MALFORMED_JSON",
                        "Invalid JSON body"));
    }

    @ExceptionHandler(QuoteNotFoundException.class)
    ResponseEntity<ApiError> quoteMissing(
            QuoteNotFoundException exception) {

        return ResponseEntity.status(404).body(
                new ApiError(
                        "QUOTE_NOT_FOUND",
                        "Quote not found"));
    }
}
```

**Tại sao explicit advice quan trọng khi nâng version?** Default error representations, localization và media type negotiation có thể đổi giữa framework releases. Khi ứng dụng **tự công bố** stable error codes/HTTP status, kiểm tra đúng các contract đó. Nếu team muốn chuyển sang RFC Problem Details, đây là intentional API change cần version/review của B13/B15/B18; không cập nhật snapshots vô điều kiện.

## 12. Unit tests: B01–B11 không cần Spring context

**File `src/test/java/com/example/contract/QuotePolicyTest.java`:**

```java
package com.example.contract;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Tag("contract")
class QuotePolicyTest {

    private final QuotePolicy policy = new QuotePolicy();

    @Test
    void b01_negativeSubtotalIsRejected() {
        assertThatThrownBy(() ->
                policy.price(-1, 1, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("subtotalCents");
    }

    @Test
    void b02_zeroCountIsRejected() {
        assertThatThrownBy(() ->
                policy.price(1_000, 0, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("itemCount");
    }

    @Test
    void b02_negativeCountIsRejected() {
        assertThatThrownBy(() ->
                policy.price(1_000, -1, false))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("itemCount");
    }

    @Test
    void b03_oneItemPaysFullShipping() {
        assertThat(policy.price(2_000, 1, false))
                .isEqualTo(
                        new PriceBreakdown(2_000, 500, 2_500));
    }

    @Test
    void b04_twoItemsPayFullShipping() {
        assertThat(policy.price(2_000, 2, false))
                .isEqualTo(
                        new PriceBreakdown(2_000, 500, 2_500));
    }

    @Test
    void b05_threeItemsGetReducedShipping() {
        assertThat(policy.price(2_000, 3, false))
                .isEqualTo(
                        new PriceBreakdown(2_000, 300, 2_300));
    }

    @Test
    void b06_fourItemsKeepReducedShipping() {
        assertThat(policy.price(2_000, 4, false))
                .isEqualTo(
                        new PriceBreakdown(2_000, 300, 2_300));
    }

    @Test
    void b07_justBelowThresholdStillPays() {
        assertThat(policy.price(9_999, 2, false))
                .isEqualTo(
                        new PriceBreakdown(9_999, 500, 10_499));
    }

    @Test
    void b08_exactThresholdIsFree() {
        assertThat(policy.price(10_000, 2, false))
                .isEqualTo(
                        new PriceBreakdown(10_000, 0, 10_000));
    }

    @Test
    void b09_aboveThresholdIsFree() {
        assertThat(policy.price(10_001, 2, false))
                .isEqualTo(
                        new PriceBreakdown(10_001, 0, 10_001));
    }

    @Test
    void b10_memberGetsFreeShippingOnSmallOrder() {
        assertThat(policy.price(1, 1, true))
                .isEqualTo(
                        new PriceBreakdown(1, 0, 1));
    }

    @Test
    void b11_zeroSubtotalIsAllowed() {
        assertThat(policy.price(0, 1, false))
                .isEqualTo(
                        new PriceBreakdown(0, 500, 500));
    }
}
```

### 12.1. Vì sao 12 methods chỉ chứng minh 11 IDs?

B02 có **hai negative cases** (zero và negative count). Hai methods bảo vệ cùng một rule nhưng tránh nhầm nguyên nhân khi test fail. Nếu chuyển sang `@ParameterizedTest`, có thể có 1 phương thức chạy hai invocations; ma trận B02 **không đổi**.

### 12.2. Assertions nào là bằng chứng?

- So bằng `PriceBreakdown` record để bảo vệ subtotal, shipping và total cùng lúc.
- Dùng đúng ngưỡng 9.999/10.000/10.001.
- Không assert UUID/ID/time ngẫu nhiên.
- Negative tests phải thực sự ném exception; test chỉ `notNull` không bảo vệ rule.
- B10 phải dùng subtotal nhỏ để điều kiện miễn phí do `member`, không vô tình test miễn phí vì ≥10.000.
- Không đổi test expected để phù hợp bug implementation.

**Giới hạn:** đây là pure unit test nên không kiểm tra việc Spring có tạo QuotePolicy bean hay không. B17 giữ bằng chứng đó.

## 13. MVC slice: B12–B15 và B18

**File `src/test/java/com/example/contract/QuoteControllerWebMvcTest.java`:**

```java
package com.example.contract;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@Tag("contract")
@WebMvcTest(QuoteController.class)
class QuoteControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    QuoteService service;

    @Test
    void b12_postReturns201LocationAndFullJson()
            throws Exception {
        when(service.create(9_999, 2, false))
                .thenReturn(new QuoteResult(
                        41L, 9_999, 500, 10_499));

        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "subtotalCents": 9999,
                      "itemCount": 2,
                      "member": false
                    }
                    """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", "/api/quotes/41"))
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.subtotalCents")
                        .value(9_999))
                .andExpect(jsonPath("$.shippingCents")
                        .value(500))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499));

        verify(service).create(9_999, 2, false);
    }

    @Test
    void b13_missingSubtotalReturns400()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"itemCount":1,"member":false}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));

        verifyNoInteractions(service);
    }

    @Test
    void b13_missingItemCountReturns400()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"subtotalCents":2000,"member":false}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));

        verifyNoInteractions(service);
    }

    @Test
    void b13_zeroCountReturns400()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"subtotalCents":2000,"itemCount":0}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));

        verifyNoInteractions(service);
    }

    @Test
    void b14_getKnownQuoteReturns200WithJson()
            throws Exception {
        when(service.get(41L))
                .thenReturn(new QuoteResult(
                        41L, 2_000, 300, 2_300));

        mvc.perform(get("/api/quotes/{id}", 41L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.shippingCents")
                        .value(300))
                .andExpect(jsonPath("$.totalCents")
                        .value(2_300));

        verify(service).get(41L);
    }

    @Test
    void b15_missingQuoteReturns404StableCode()
            throws Exception {
        when(service.get(404L))
                .thenThrow(
                        new QuoteNotFoundException(404L));

        mvc.perform(get("/api/quotes/{id}", 404L))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("QUOTE_NOT_FOUND"));
    }

    @Test
    void b18_malformedJsonReturns400StableCode()
            throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{broken-json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_JSON"));

        verifyNoInteractions(service);
    }
}
```

### 13.1. Ranh giới của các assertions

Tests chạy Spring MVC dispatch, Jackson mapping, Bean Validation và QuoteErrorHandler **thật**. QuoteService được `@MockitoBean` thay thế để loại DB/service rule khỏi phạm vi; vì thế:

- B12 bảo vệ HTTP semantics và DTO.
- B13 bảo vệ việc invalid request bị chặn **trước service**.
- B15 bảo vệ mapping exception tới HTTP 404/code.
- B18 bảo vệ malformed JSON response.

Nhưng **chúng không chứng minh** QuoteService thực sự được tạo/inject hoặc database đã ghi đúng. B17/full seam chịu trách nhiệm ấy. Khi nâng Boot 4, import `@WebMvcTest` và test starter có thể đổi; đầu vào và expected HTTP contract **không được tự đổi** chỉ để mã compile.

### 13.2. @MockitoBean so với @MockBean

Spring Boot 3.5 hỗ trợ Spring Framework 6.2 `@MockitoBean`. Boot `@MockBean` đã deprecated từ 3.4 theo hướng thay bằng `@MockitoBean`. Đây là **thay test harness**, không phải thay behavior. Sau khi migrate, kiểm tra test thực sự override đúng bean và không để một mock mới tạo thay cho real wiring guard ngoài mong muốn.

### 13.3. Nếu có Spring Security?

Sample không có security starter. Trong ứng dụng thật, `@WebMvcTest` có thể nạp security support/filter chain tùy cấu hình. Không xóa `SecurityFilterChain`, không cấu hình `addFilters=false` một cách máy móc để test xanh. Thêm ma trận các tình huống anonymous/authorized/forbidden/CSRF và giữ security integration evidence đúng scope.

## 14. JPA slice: B16 kiểm tra persistence và query semantics

**File `src/test/java/com/example/contract/QuoteRepositoryDataJpaTest.java`:**

```java
package com.example.contract;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("contract")
@DataJpaTest
class QuoteRepositoryDataJpaTest {

    @Autowired
    QuoteRepository repository;

    @Autowired
    EntityManager entityManager;

    @Test
    void b16_persistThenClearReloadsActualMappedColumns() {
        QuoteEntity saved = repository.saveAndFlush(
                new QuoteEntity(2_000, 500, 2_500));

        Long id = saved.getId();
        assertThat(id).isNotNull();

        // Do not read only the same managed entity instance.
        entityManager.clear();

        QuoteEntity reloaded =
                repository.findById(id).orElseThrow();

        assertThat(reloaded.getSubtotalCents())
                .isEqualTo(2_000);
        assertThat(reloaded.getShippingCents())
                .isEqualTo(500);
        assertThat(reloaded.getTotalCents())
                .isEqualTo(2_500);
    }

    @Test
    void b16_queryIncludesExactThreshold() {
        repository.saveAndFlush(
                new QuoteEntity(9_700, 300, 10_000));
        repository.saveAndFlush(
                new QuoteEntity(9_000, 500, 9_500));

        assertThat(repository
                .findByTotalCentsGreaterThanEqual(10_000))
                .extracting(QuoteEntity::getTotalCents)
                .containsExactly(10_000);
    }

    @Test
    void b16_queryAboveAllRowsReturnsEmpty() {
        repository.saveAndFlush(
                new QuoteEntity(9_700, 300, 10_000));

        assertThat(repository
                .findByTotalCentsGreaterThanEqual(10_001))
                .isEmpty();
    }
}
```

### 14.1. Vì sao clear persistence context?

Sau `saveAndFlush`, `findById` có thể trả lại chính managed entity trong JPA first-level cache. `entityManager.clear()` buộc một lần tải lại, làm test mapping/DB readback có ý nghĩa hơn. Điều này không thay thế DB-level integration test nếu cần kiểm tra actual commit/isolation.

### 14.2. @DataJpaTest transaction rollback

Spring Boot 3.5 `@DataJpaTest` mặc định transactional và rollback sau từng method. Vì vậy ba tests có thể tạo dữ liệu độc lập mà không cần `@DirtiesContext`. Trong phần JPA query, dữ liệu không bị “tồn” từ method trước theo test transaction bình thường.

**Giới hạn:** H2 không bảo đảm compatibility với PostgreSQL JSONB/collation/locks hoặc migration scripts production. Nếu B16 yêu cầu production dialect, dùng Testcontainers đúng engine/version và thêm test setup tương ứng.

## 15. Full-context seam: B12–B17 nối các tầng thật

**File `src/test/java/com/example/contract/QuoteFlowSpringBootTest.java`:**

```java
package com.example.contract;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@Tag("contract")
@SpringBootTest(classes = ContractDemoApplication.class)
@AutoConfigureMockMvc
@Transactional
class QuoteFlowSpringBootTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    QuoteRepository repository;

    @Autowired
    ObjectMapper mapper;

    @Test
    void b17_postThenGetUsesRealSpringBeansAndJpa()
            throws Exception {
        MvcResult created = mvc.perform(
                post("/api/quotes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "subtotalCents": 9999,
                          "itemCount": 2,
                          "member": false
                        }
                        """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.subtotalCents")
                        .value(9_999))
                .andExpect(jsonPath("$.shippingCents")
                        .value(500))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499))
                .andReturn();

        long id = mapper.readTree(
                created.getResponse().getContentAsString())
                .get("id").asLong();

        assertThat(id).isPositive();
        assertThat(repository.findById(id)).isPresent();

        mvc.perform(get("/api/quotes/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id))
                .andExpect(jsonPath("$.totalCents")
                        .value(10_499))
                .andExpect(header().doesNotExist("Location"));
    }

    @Test
    void b13_invalidPostDoesNotPersist()
            throws Exception {
        long before = repository.count();

        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"subtotalCents":100,"itemCount":0}
                    """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));

        assertThat(repository.count()).isEqualTo(before);
    }

    @Test
    void b15_notFoundSurvivesFullContextWiring()
            throws Exception {
        mvc.perform(get(
                "/api/quotes/{id}", Long.MAX_VALUE))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("QUOTE_NOT_FOUND"));
    }
}
```

### 15.1. Vì sao full-context seam test cần tồn tại?

Unit policy không biết Spring bean injection. MVC slice dùng mock service. JPA slice không chạy controller/service. Test đầu tiên ở lớp này chứng minh **cả chuỗi**:

```text
POST JSON
   -> MVC request binding/validation
   -> QuoteController real bean
   -> QuoteService real Spring bean
   -> QuotePolicy real bean
   -> QuoteRepository real JPA bean
   -> H2 persistence
   -> GET same generated ID
   -> JSON response through MVC
```

Đây là bằng chứng B17. Nếu xóa `@Service` khỏi QuoteService, component scanning/wiring có thể fail; nếu đổi JPA mapping/query, test có khả năng fail. Đổi full suite thành **chỉ** MVC slices với `@MockitoBean QuoteService` sẽ xóa chứng cứ B17.

### 15.2. Vì sao @Transactional giúp isolation ở đây?

Test dùng `@SpringBootTest` **mock web environment** và `@AutoConfigureMockMvc`. Request MockMvc thông thường chạy cùng test thread; repository operations tham gia test-managed transaction và rollback sau method. Điều này phù hợp demo.

**Không suy rộng cho `RANDOM_PORT`:** khi client gửi HTTP thật tới embedded server, client/test thread và server thread khác; test `@Transactional` không tự rollback server-side writes. Khi nâng test từ MockMvc sang real HTTP, phải thêm cleanup/isolation và giữ các ma trận hành vi liên quan.

### 15.3. Why not assert exact generated ID?

Hibernate/DB có thể thay strategy/sequence sau upgrade. B12/B17 chỉ yêu cầu ID hợp lệ, Location trỏ ID ấy và GET trả cùng entity. Hardcode ID=1 là assertion vào implementation detail khi không có business requirement cho ID sequence.

### 15.4. Giới hạn của seam test

Nó không mở socket HTTP thật, không dùng production PostgreSQL, không chạy security policy hay Kafka. Ma trận có thể tiếp tục mở rộng ở các mức đó theo rủi ro sản phẩm; không đánh dấu “end-to-end production verified” chỉ vì một MockMvc path xanh.

## 16. Đối chiếu code tests với B01–B18

| IDs | Test owners theo mẫu | Loại bằng chứng |
|---|---|---|
| B01–B11 | `QuotePolicyTest.b01...b11...` (12 methods) | Domain policy và boundaries |
| B12 | `QuoteControllerWebMvcTest.b12...` | HTTP status, Location, JSON |
| B13 | Ba methods `b13...` ở MVC và một full negative | Missing/invalid values và no persistence |
| B14 | `QuoteControllerWebMvcTest.b14...` + full GET path | GET JSON payload |
| B15 | `QuoteControllerWebMvcTest.b15...` + full missing ID | 404/error code và real wiring |
| B16 | Ba methods `b16...` ở JPA | Persist/clear/query inclusive |
| B17 | `QuoteFlowSpringBootTest.b17...` | Real controller/service/JPA wiring |
| B18 | `QuoteControllerWebMvcTest.b18...` | Malformed JSON → stable 400 error |

**Tổng số methods = 12 + 7 + 3 + 3 = 25.** Một số ID có owner phụ để tránh lỗ hổng khi chuyển mock/framework. Trong code này, full seam không thử trực tiếp B08 exact threshold; B08 đã có unit owner, còn seam chứng minh production policy được wired thật với input 9.999. Nếu đội yêu cầu B08 phải có cross-layer evidence riêng (ví dụ lỗi lịch sử ở threshold sau serialization), hãy bổ sung một full seam threshold test; không đánh dấu nó đã chạy qua full nếu chưa có.

### 16.1. Sửa ma trận chứ không bịa test

Không nên ghi “B08 có full seam” vì bạn tưởng một test nên làm điều đó. Ma trận ở phần 4.1 mô tả **unit + seam là coverage mục tiêu**; bộ test hiện tại chỉ chứng minh B08 ở unit và **wiring chung** ở seam. Khi chuẩn hoá làm gate, có thể ghi:

```text
B08 | unit=PASS | cross-layer=GAP
    | action=add exact-threshold full seam only if required
```

hoặc điều chỉnh owner mục tiêu thành unit + B17 seam gián tiếp nếu policy của nhóm chấp nhận. Trạng thái phải phản ánh thực tế. Đây là bài học quan trọng nhất khi dùng ma trận: **đừng làm đẹp evidence**.

### 16.2. Một review scenario giả định

Developer bỏ `@Valid` khỏi QuoteController. Unit policy vẫn pass; JPA slice vẫn pass. Nhưng MVC tests B13 phải fail vì invalid POST không còn bị chặn; nếu service mock chưa stub, controller có thể trả lỗi khác hoặc 201, dù thế test status/code assertion đỏ. Full B13 cũng phải fail vì request có count=0 đi vào domain exception thay vì structured 400.

Developer đổi query derived method từ GreaterThanEqual sang GreaterThan. JPA B16 test đúng 10.000 phải fail.

Developer đổi policy threshold từ 10.000 sang 10.001. Unit B08 fail. Đó mới là bằng chứng behavioral matrix có tác dụng.

## 17. Lệnh chạy và kiểm tra test discovery

Linux/macOS, khi đã có Gradle Wrapper phù hợp:

```bash
./gradlew clean test

# Chạy từng tầng:
./gradlew test --tests "com.example.contract.QuotePolicyTest"
./gradlew test --tests "com.example.contract.QuoteControllerWebMvcTest"
./gradlew test --tests "com.example.contract.QuoteRepositoryDataJpaTest"
./gradlew test --tests "com.example.contract.QuoteFlowSpringBootTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests "com.example.contract.QuotePolicyTest"
.\gradlew.bat test --tests "com.example.contract.QuoteControllerWebMvcTest"
.\gradlew.bat test --tests "com.example.contract.QuoteRepositoryDataJpaTest"
.\gradlew.bat test --tests "com.example.contract.QuoteFlowSpringBootTest"
```

Khi dự án thật dùng Maven, cần pom.xml với Spring Boot BOM/parent, Maven Surefire và JUnit Platform tương ứng; chỉ khi đã có Maven Wrapper mới dùng `./mvnw test`. Đừng trộn Gradle và Maven instructions vào cùng một build mà không có lý do.

### 17.1. Kết quả kỳ vọng và kết quả thực

**Thiết kế mong đợi:** 25 JUnit methods được phát hiện và pass nếu environment/versions/phần code đầy đủ phù hợp. Nội dung được rà soát theo tài liệu API nhưng **chưa biên dịch, chạy Gradle hoặc JUnit trong phiên soạn**.

Sau khi chạy thật, xem `build/test-results/test` và `build/reports/tests/test`. Trước khi chuyển trạng thái ma trận sang PASS cần:

- Số tests executed đúng (không bị filter mất).
- Failed=0, Error=0.
- Skipped=0 cho những tests bắt buộc.
- Không có known flaky failures bị retry che mất.
- Evidence/commit/JDK/version tương ứng.
- Test result không chỉ được gắn nhãn UP-TO-DATE/FROM-CACHE mà thiếu traceability tới run hợp lệ.

### 17.2. Tạo báo cáo ma trận sau test run

Một đội có thể dùng CSV/Markdown/JSON để lưu metadata, ví dụ:

```text
id,contract,owner,baseline,target,status,notes
B01,negative-subtotal,QuotePolicyTest,pass,pass,COVERED,
B08,free-at-10000,QuotePolicyTest,pass,pass,COVERED,
B13,invalid-http-input,QuoteControllerWebMvcTest,pass,pass,COVERED,
B16,jpa-inclusive-query,QuoteRepositoryDataJpaTest,pass,pass,COVERED,
B17,real-wiring,QuoteFlowSpringBootTest,pass,pass,COVERED,
```

Đây là **mẫu CSV minh họa sau một run giả định**, không phải artifact đã sinh tự động. Trong thực tế, nếu không có baseline/target run thì điền NOT_RUN/UNKNOWN, **không tự ghi pass**. Như vậy ma trận không phụ thuộc cách đặt tên test của phiên bản cũ.

## 18. So sánh baseline và target theo một quy trình có thể lặp lại

Một PR nâng Boot 3.5 → 4.x có thể được review qua bảng:

| ID | Baseline 3.5 | Target 4.x | Kết luận |
|---|---|---|---|
| B01–B11 | PASS thực tế | PASS thực tế | Behavior giữ nguyên |
| B12 | POST 201/Location/JSON | Cùng contract | Nếu chỉ còn status 201 thì GAP |
| B13 | Missing values → 400 code | Cùng contract | Nếu default error changed ngoài ý muốn thì regression |
| B15 | 404 code | Cùng contract | Nếu advice không được load, không cho qua |
| B16 | Query inclusive | Query inclusive | Nếu dialect/SQL semantics đổi, điều tra |
| B17 | Real bean path | Real bean path | Nếu mock thay service, GAP |
| B18 | Malformed JSON 400/code | Cùng contract | Nếu Jackson migration đổi mapping, phải review |

**Tất cả chữ PASS trong bảng là logic ví dụ**, không phải báo cáo đã chạy trên Boot 4. Muốn chốt thật phải có CI artifacts cho cả hai branches và ma trận revision tương ứng.

### 18.1. Khi cả hai branch fail ở cùng ID

Đừng gọi đó là upgrade regression ngay. Có thể là **defect có từ trước** hoặc test/environment bị lỗi. So sánh root cause, kiểm tra requirement và ghi class `PRE_EXISTING`. Nhưng cũng không được xóa ID chỉ vì lỗi tồn tại lâu.

### 18.2. Khi baseline pass, target fail

Phân loại trước khi sửa:

- **Product regression:** contract thực sự bị phá.
- **Test harness migration:** import/test dependency/extension/test discovery sai.
- **Test assumption brittle:** test phụ thuộc thứ tự DB ID, locale, timestamp, SQL string hoặc implementation detail.
- **Intentional change:** requirement/API đã được phê duyệt đổi.
- **Infrastructure failure:** container không sẵn sàng, CI network, cache/fork mismatch.

Giải quyết đúng loại. Không sửa production code để đáp ứng một assertion brittle; cũng không nới lỏng HTTP contract chỉ để tất cả tests pass.

### 18.3. Khi target pass nhưng test bị skipped

Một kết quả xanh với B17 test **không được chạy** không có giá trị tương đương. Dùng CI test reports và test discovery gates; khi đổi test engine, package, tags hoặc filters cần xác nhận tests vẫn được phát hiện. Với Gradle, đọc XML reports; nếu dự án dùng Maven, đọc Surefire/Failsafe output.

## 19. Cách xử lý intentional behavior changes

Nếu sản phẩm thật sự đổi ngưỡng miễn phí giao từ 10.000 sang 8.000, B08 không còn “free at 10.000 là boundary”. Không được chỉ sửa expected B08 rồi chốt.

Quy trình nên là:

1. Link approved requirement/ADR/issue.
2. Sửa statement của business contract và mốc hiệu lực/version.
3. Xác định compatibility: khách API cũ hay dữ liệu cũ có bị ảnh hưởng không?
4. Sửa cả negative boundaries: 7.999 / 8.000 / 8.001.
5. Xác định consumers cần cập nhật (API docs, SDK, DB migration, dashboards).
6. Đánh dấu B08 cũ `SUPERSEDED` hoặc revision, không xóa dấu vết.
7. Tạo B08-v2 hoặc dòng mới nếu cần traceability xuyên versions.
8. Chạy các test owner tương ứng và full seam nếu ranh giới thay đổi.
9. Đối chiếu tác động tới cache/serialization/config và CI artifacts.
10. Ghi rõ người phê duyệt, ngày bắt đầu hiệu lực, version compatibility.

### 19.1. Đừng biến snapshots thành nguồn chân lý duy nhất

Golden snapshot phù hợp khi JSON/document output dài và ổn định. Nhưng việc chạy `updateSnapshots` sau upgrade rồi commit tất cả diffs mà không review từng semantic change có thể **hợp thức hóa regression**.

Với HTTP contracts quan trọng, ưu tiên assert fields/status/headers/error codes cụ thể. Nếu snapshot cần thiết:

- Canonicalize field order khi order không thuộc contract.
- Mask dynamic timestamps/IDs/ports khi chúng không thuộc contract.
- Không mask các field cần bảo vệ (amount, user role, status).
- Review diff với business owner/consumer.
- Giữ baseline snapshot và target snapshot diff có reason.
- Version snapshot khi API version thực sự đổi.
- Không dùng opaque snapshot hash làm bằng chứng duy nhất.

## 20. Stability: input fixtures và outputs phải deterministic

Ma trận chỉ có giá trị nếu cùng một stimulus tạo expected observable ổn định.

### 20.1. Những nguồn nondeterminism thường gặp

| Nguồn | Rủi ro khi nâng/refactor | Cách xử lý |
|---|---|---|
| Current time | Timestamp đổi mỗi run | Inject Clock/fixed time |
| Random UUID | Snapshot khác | Assert format/referential consistency |
| Generated JPA ID | Tăng khác nhau giữa contexts | Assert non-null rồi dùng ID nhận được |
| Locale/timezone | Error message, date JSON khác | Chốt locale/zone nếu là contract |
| Unordered DB queries | Danh sách trả thứ tự ngẫu nhiên | ORDER BY explicit hoặc assert không xét order |
| Parallel tests | Shared DB/mock/singleton state | Isolated data, serial group hoặc locks phù hợp |
| Cached ApplicationContext | Bean state rò giữa methods | Reset state/rollback/avoid mutable singleton |
| Testcontainers mapped ports | Random host port | @ServiceConnection/DynamicPropertySource |
| External HTTP calls | Data/latency thay đổi | Contract stub có kiểm soát + integration job |
| Spring Security default | 401/403/CSRF khác | Security-enabled tests theo policy thật |
| H2 vs PostgreSQL | Collation/SQL dialect khác | Real-dialect integration |
| Retry/timeouts | Flaky dưới CI CPU load | Deterministic schedule, wait for readiness |

### 20.2. @DirtiesContext có phải cách cô lập chuẩn?

Không. Spring TestContext cache lưu context theo metadata trong JVM. `@DirtiesContext` đóng/evict context; dùng đại trà làm suite chậm và có thể gây race khi parallel. Với JPA slice/full MockMvc test, transaction rollback/cleanup data thường phù hợp hơn. Với Mockito, reset mock phù hợp hơn. Với mutable singleton state, dùng API clear/restore hoặc tách context có chủ đích.

### 20.3. Test-only configuration cũng có thể làm sai bằng chứng

Nếu muốn test @ConfigurationProperties binding, đừng thay toàn bộ config bằng Mockito mock. Nếu muốn test authentication, đừng tắt security filter cho tiện. Nếu muốn test database query, đừng stub repository results. **Đúng test double ở ngoài boundary; sai test double ở chính behavior cần kiểm tra.**

## 21. Dùng mutation testing để thẩm định ma trận

Mutation testing (ví dụ PIT) có thể kiểm tra liệu tests có phản ứng với những thay đổi nhỏ trong production code không.

Ví dụ:

- Mutation `>= 10_000` → `> 10_000` phải bị B08 phát hiện.
- Mutation `itemCount >= 3` → `itemCount > 3` phải bị B05 phát hiện.
- Mutation `shipping = 500` → `shipping = 0` phải bị B03/B04/B07/B11 phát hiện.
- Bỏ `@Valid` trong controller không nhất thiết là bytecode mutation mà PIT mặc định tạo, nên MVC B13 vẫn cần riêng.
- Đổi JPA query `GreaterThanEqual` sang `GreaterThan` thuộc Spring Data semantics, cần JPA B16.
- Thay real bean bằng mock không được pure policy test phát hiện, cần B17.

**Mutation score không thay thế behavior matrix.** Nó hỗ trợ đánh giá assertions của các vùng Java code được mutate. Không phải mọi regression trong Spring wiring, protocol, annotations, migration hoặc external systems đều được một bộ mutators mặc định mô phỏng.

### 21.1. Đánh giá “một test bị xóa” có làm mất hành vi không?

Trước khi xóa test cũ, thử diễn đạt mutation/hành vi sai mà test đó từng bắt. Nếu new owners còn bắt được, việc bỏ test trùng có lý. Nếu không, đánh dấu GAP và bổ sung test mới trước khi xóa. Không dựa vào tổng số methods tăng/giảm.

## 22. CI gates theo ma trận, không chỉ tỷ lệ pass

Một CI job chuyển đổi đáng tin cần nhiều lớp điều kiện:

1. **Compile/build** trên exact target Java/Spring Boot/Gradle/Maven.
2. **JUnit execution**: test classes được discover, không skipped ngoài policy.
3. **Behavior coverage**: mọi required IDs có owner đúng boundary.
4. **Results**: required tests pass trong môi trường hợp lệ.
5. **Cross-layer integrity**: seam/security/external contracts không biến thành mocks.
6. **Data/source compatibility**: schema migration và serializers checked khi cần.
7. **Stability**: không lạm dụng retries để giấu flakiness.
8. **Evidence preservation**: lưu báo cáo và baseline-target diff.
9. **Approved exceptions**: intentional changes được ghi reason/version.
10. **Performance**: đo suite duration/context starts sau khi correctness được giữ.

### 22.1. Pipeline gợi ý

```text
PR refactor / framework upgrade
          |
          v
  compile + unit + MVC + JPA + full smoke
          |
          +--> JUnit XML: executed/failed/skipped
          |
          +--> behavior matrix validation
          |       required IDs with real owners?
          |       baseline vs target expectations?
          |
          +--> security/DB/container contract jobs (nếu cần)
          |
          +--> optional PIT/coverage trends
          |
          v
       approve / block

Periodic audit:
  inspect tests marked disabled, flaky and matrices with GAP
```

Lệnh cơ bản cho Gradle project mẫu:

```bash
./gradlew clean test
# Collect build/test-results/test and build/reports/tests/test
```

Đây là **pipeline ý tưởng**, không cung cấp sẵn GitHub Actions/GitLab/Jenkins config. Việc so mapping ma trận có thể làm thủ công trong PR hoặc tự động qua test naming/metadata parser, nhưng phải kiểm tra parser không đánh dấu COVERED khi method chỉ tồn tại mà chưa chạy.

### 22.2. Không tự gán PASS từ source code

Một bài viết chỉ có mã mẫu chưa thực thi, nên trạng thái thực là `NOT_RUN`. Muốn trạng thái COVERED ở CI cần có run result verified, test selection đúng và expected. Tên `b17_...` trong source giúp tìm owner, **không phải một chứng nhận runtime**.

## 23. Những lỗi thường gặp khi chuyển bộ test

| Anti-pattern | Vì sao mất bảo vệ | Cách đúng |
|---|---|---|
| Thay toàn bộ @SpringBootTest bằng unit tests | Bỏ Spring wiring | Giữ full seam B17 |
| Assert HTTP 200 nhưng bỏ JSON fields | Serialization regressions không bị bắt | B12/B14 assert fields |
| Mock QuoteService ở mọi test | Không còn real policy/JPA path | Unit policy + full seam |
| JPA test chỉ save rồi find trong cùng persistence context | First-level cache có thể che DB readback | Flush + clear + reload |
| H2 xanh được gọi là PostgreSQL compatible | SQL dialect khác | Testcontainers real DB khi cần |
| Tự cập nhật snapshots khi nâng Jackson | Có thể hợp thức hóa lỗi response | Review diff theo Bxx |
| Đổi @MockBean sang @MockitoBean nhưng không xem target | Có thể create mock thay thiếu bean | Review override policy |
| Chỉ sửa imports khi nâng Boot 4 | Test engine/module/default behavior có thể đổi | Matrix, test discovery, dependencies |
| Bỏ @Valid để MockMvc test bớt fail | Invalid request lọt | Giữ B13 |
| Bỏ @Transactional mà không kiểm tra data leakage | Test phụ thuộc order | Explicit cleanup/rollback |
| Chạy RANDOM_PORT và nghĩ @Transactional rollback server-side | Client/server threads khác | Separate cleanup |
| Assert generated ID phải bằng 1 | Brittleness khi đổi DB | Assert valid ID/referential consistency |
| So nguyên localized exception message | Locale/framework đổi không phải contract | Stable error code |
| Set @DirtiesContext cho mọi class | Cache thrash, chậm/race | Reset đúng resource |
| Dùng unique inline property cho mọi test | Nhiều cache keys | Chuẩn hóa equivalent configs |
| Skipped test được tính PASS | False green | CI executed/skip gate |
| Chỉ xem total test count | Tests có thể kiểm tra hành vi khác | Map theo ID |
| Xóa một ID không còn phù hợp mà không ghi lại | Mất traceability | RETIRED/SUPERSEDED có reason |
| Sửa expected theo behavior mới chưa được duyệt | Test hợp thức hóa regression | Review requirement trước |
| Golden snapshot hash thay semantic asserts | Khó biết thay đổi ảnh hưởng gì | Assert status/fields/side effects |
| Cố đạt 100% code coverage | Coverage không chứng minh assertions mạnh | Behavioral negative/boundary + mutation |
| CI chỉ chạy test trên một JDK không phải target | Không chứng minh upgrade target | Explicit test toolchain matrix |
| Tự động retry flaky test rồi báo green | Che lỗi isolation | Diagnose root causes |
| Bảo mật không được thêm vào matrix | Không có evidence về auth | Security integration tests riêng |
| Không cập nhật docs/API consumers sau behavior change | Contract drift | Version + compatibility plan |

## 24. Bài tập thực hành và lời giải

### A. Refactor full test thành unit test

**Bài:** Sau khi chuyển một test controller→service→repository thành unit policy, tất cả B01–B11 pass. Có thể xóa test full-context cũ không?

**Đáp:** Chỉ khi những yêu cầu về wiring/persistence/HTTP mà test cũ bảo vệ có owner mới. B17 vẫn cần một seam test qua real Spring-managed beans; unit policy không thay nó.

### B. Nâng Boot 3.5 lên 4.x

**Bài:** Import `@WebMvcTest` đổi package, developer xóa lớp test MVC cho build pass. B12/B13/B14/B15/B18 có còn COVERED không?

**Đáp:** Không nếu không có test khác chứng minh đúng HTTP contract. Cần dùng test starter và annotation/import mới theo migration guide, giữ cùng test inputs/expected.

### C. Thay assert JSON bằng status

**Bài:** Test cũ B12 assert 201, Location, id, shipping, total. Test mới chỉ assert 201.

**Đáp:** B12 bị giảm bằng chứng. Bất kỳ lỗi JSON/Location có thể lọt. Trạng thái GAP cho các fields bị bỏ hoặc sửa lại assertions.

### D. Đổi điều kiện ngưỡng

**Bài:** Developer đổi `subtotal >= 10_000` thành `subtotal > 10_000`. Test nào phải đỏ?

**Đáp:** B08 exact boundary; B07 và B09 có thể vẫn xanh.

### E. Đổi JPA query

**Bài:** Derived query trở thành GreaterThan thay vì GreaterThanEqual. Test unit policy có phát hiện không?

**Đáp:** Không. JPA B16 query inclusive với 10.000 phải phát hiện.

### F. Error JSON thay sau Jackson upgrade

**Bài:** API trước đây trả `{"code":"INVALID_REQUEST"}`, sau nâng version trả default HTML/Problem Details, nhưng HTTP status vẫn 400.

**Đáp:** Nếu stable error code là contract, đây là regression B13; phải restore advice/content negotiation hoặc phê duyệt API version change, không chỉ sửa snapshot.

### G. Nhiều test methods hơn trước

**Bài:** Trước refactor có 100 tests, sau có 160. Có chắc coverage tốt hơn không?

**Đáp:** Không. Quan trọng là ID contract, test boundary và strength. Một trăm tests cùng assert notNull không thay 10 tests có negative/boundary proof.

### H. @DataJpaTest transaction rollback

**Bài:** Vì sao không cần @DirtiesContext sau mỗi method JPA slice?

**Đáp:** Mặc định @DataJpaTest dùng test-managed transaction rollback; có thể cô lập row mutations. Nhưng không suy rollback cho external systems/threads hoặc schema modifications ngoài transaction.

### I. RANDOM_PORT và transaction

**Bài:** Test gửi HTTP thật POST tạo row, @Transactional gắn trên JUnit test. Row có tự rollback không?

**Đáp:** Không bảo đảm vì server chạy transaction ở thread riêng. Cần cleanup/isolated DB cho real HTTP tests.

### J. Fake data trong snapshot

**Bài:** JSON có generated ID ngẫu nhiên, snapshot luôn khác.

**Đáp:** Đừng loại ID hoàn toàn nếu referential consistency là contract. Assert ID hợp lệ, dùng ID returned để GET và so cùng ID; bỏ điều kiện “ID phải luôn bằng 1”.

### K. Tên test đổi

**Bài:** `shouldWork()` được đổi thành `b12_post...`. Hợp đồng B12 có cần đổi không?

**Đáp:** Không. B12 là business/API contract ID, không phụ thuộc tên method; cập nhật mapping owner nếu cần.

### L. Known failure ở baseline

**Bài:** B15 đã fail trước upgrade. Có nên nói Boot 4 tạo regression B15?

**Đáp:** Không tự động. Ghi PRE_EXISTING và điều tra; nếu root cause khác mới là regression target. Không xóa ID.

### M. Snapshot update hàng loạt

**Bài:** Nâng JSON library làm 40 snapshot khác, developer chạy update all.

**Đáp:** Không chốt ngay. Phân loại diffs theo public contract, normalize những fields không có nghĩa, review changes có chủ đích. Nếu B12/B13/B14/B15 thay semantics, cần approval.

### N. Mock service trong MVC test

**Bài:** MVC B12 trả đúng JSON từ Mockito stub. Nó có chứng minh QuotePolicy.price đúng không?

**Đáp:** Không. Policy unit B01–B11 và full seam B17 còn cần. Stubbing chỉ chứng minh controller chuyển request/response theo contract.

### O. Full seam chạy với H2

**Bài:** Production dùng PostgreSQL; full seam H2 pass. Có thể nói transaction/SQL tương thích production không?

**Đáp:** Không. Cần real PostgreSQL migration/query tests khi contract có database-specific semantics.

### P. JUnit tests bị skipped sau nâng

**Bài:** Gradle báo BUILD SUCCESSFUL nhưng chỉ executed 20/25 methods do tag filter.

**Đáp:** Không đạt gate nếu 5 methods là required. Sửa test discovery/tag/job wiring, chạy lại; không gán COVERED khi không có evidence.

## 25. Checklist QA dùng khi review PR hoặc framework upgrade

- [ ] Ma trận có ID ổn định, contract, inputs, expected, owner và nguồn yêu cầu.
- [ ] Đã bao gồm bugs lịch sử và các boundary/negative cases quan trọng.
- [ ] Có trạng thái COVERED/GAP/INTENTIONAL_CHANGE/RETIRED rõ ràng.
- [ ] Behavior contract độc lập với tên test/framework package.
- [ ] Có baseline đã chạy thực ở version/JDK/source commit xác định.
- [ ] Có target run ở version/JDK/source commit xác định.
- [ ] JUnit executed/passed/failed/skipped được đối chiếu, không chỉ build xanh.
- [ ] Không gán PASS cho tests chỉ tồn tại trong code nhưng chưa chạy.
- [ ] Tất cả required IDs còn có test owner đúng boundary.
- [ ] Unit tests giữ input boundary và expected output cụ thể.
- [ ] MVC tests giữ status/Location/headers/JSON/error codes.
- [ ] MVC invalid tests xác minh không gọi service khi appropriate.
- [ ] Repository tests chạy SQL/JPA thật, không mock repository.
- [ ] Có flush/clear/reload khi cần tránh JPA first-level cache false positive.
- [ ] Các câu hỏi về SQL dialect có real-DB test nếu production khác H2.
- [ ] Cross-layer seam còn dùng real controller/service/repository beans.
- [ ] Không dùng mock ở chính layer đang là mục tiêu proof.
- [ ] Security/CSRF/filter tests được giữ khi sản phẩm có contract đó.
- [ ] Transaction/cache/AOP behavior có Spring-managed integration tests khi cần.
- [ ] Real HTTP tests còn nguyên nếu TCP/container behavior là contract.
- [ ] @Transactional rollback không bị suy sai ở RANDOM_PORT server thread.
- [ ] Migration guide/dependency/test starters/imports phù hợp exact target Boot.
- [ ] @MockitoBean được target đúng, không vô ý hide missing production bean.
- [ ] Jackson/validation error codes được kiểm tra bằng semantic assertions.
- [ ] Dynamic IDs/time/locale/order không làm snapshot flaky.
- [ ] Không chấp nhận snapshot “update all” không review.
- [ ] Intentionally changed IDs có approval/API version/compatibility note.
- [ ] Known preexisting failures được tách khỏi target regressions.
- [ ] Context cache keys/mock overrides/test profiles được kiểm soát.
- [ ] Test data/singleton/mock/static state được cleanup, không dựa test order.
- [ ] JUnit/Gradle/Maven fork/parallel config không làm mất test discovery.
- [ ] CI giữ evidence artifacts và đường dẫn baseline-target so sánh.
- [ ] Mutation testing bổ trợ mà không thay ma trận hành vi.
- [ ] Runtime/CI performance được đo sau khi correctness đã giữ.
- [ ] Không lộ credentials/PII trong fixtures, logs hoặc reports.
- [ ] Các GAP có owner và kế hoạch bổ sung tests.
- [ ] Không xóa test cũ trước khi chuyển hết behavior ownership cần thiết.
- [ ] Mã Java 17+/Boot 3.5 sample và mã migrated Boot 4 được review theo version riêng.

## 26. Kết luận

**Ma trận hành vi là điểm cố định khi công cụ kiểm thử và phiên bản framework thay đổi.** Nó lưu lại những gì ứng dụng **phải làm**, chứ không ràng buộc rằng hành vi ấy luôn cần cùng một test class, cùng annotation hoặc cùng assertion library.

- Xây ma trận từ yêu cầu và bugs thực, không chỉ từ test names.
- Mỗi dòng có input/boundary/expected observable/owner/evidence.
- Giữ unit, slice và full-context tests đúng vai trò; không mock bỏ ranh giới cần chứng minh.
- Khi nâng Spring Boot/JUnit/Jackson/Mockito, có thể sửa imports/test starters nhưng **không mặc định sửa expected business/API outcomes**.
- Dùng baseline và target runs có JUnit XML/CI evidence; đừng cho phép skipped/disabled tests tự biến thành PASS.
- Phân biệt regression, harness migration, brittle assertion, intentional change và infrastructure failure.
- Khi một hành vi thật sự đổi, version/review ma trận cùng API consumers; không âm thầm xóa hoặc cập nhật snapshot.
- Bảo vệ các negative/boundary states, real wiring, persistence và security contracts tương ứng.

Ví dụ Java 17+/Spring Boot 3.5.16 cung cấp **25 JUnit Jupiter methods**: 12 pure policy tests, 7 MVC slice tests, 3 JPA slice tests và 3 full-context seam tests. Chúng cho thấy cùng một tập B01–B18 có thể được phân phối giữa các tầng mà vẫn có traceability. **Mã mới chỉ được rà soát theo tài liệu, chưa biên dịch hoặc chạy JUnit thực tế trong phiên biên soạn**; trước khi dùng làm CI baseline thật, phải thực thi và lưu báo cáo đúng môi trường.

## 27. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, @WebMvcTest, @DataJpaTest, test slices, MockMvc và rollback/real HTTP.
- [Spring Boot 3.5 — Test Slices Appendix](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): danh sách auto-configuration theo test slice.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular test starters, API/package changes, MockMVC/Mockito/Jackson migration notes.
- [Spring Framework 6.2 — TestContext Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): context key, reuse, LRU/default 32 và @DirtiesContext.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): test-managed rollback, thread boundaries, TestTransaction.
- [Spring Framework 6.2 — @MockitoBean/@MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean override, qualifiers, cache key và mocks.
- [Spring Boot 3.5 — MockBean API deprecation](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): chuyển sang @MockitoBean.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): derived queries và property method parsing.
- [JUnit 5 — User Guide](https://docs.junit.org/5.13.0/user-guide/): test discovery, annotations, parameterized tests, execution options.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): test task, filtering, JUnit Platform và reports.
