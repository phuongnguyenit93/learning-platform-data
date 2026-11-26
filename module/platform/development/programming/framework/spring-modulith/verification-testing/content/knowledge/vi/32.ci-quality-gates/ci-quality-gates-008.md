# Không bỏ qua test kiến trúc vì build chậm

## 1. Quyết định cần bảo vệ: thời gian build không được đổi lấy mất quality gate

Trong một pull request, nhóm `orders` đổi một service và `./gradlew test` mất hơn 15 phút vì còn khởi động PostgreSQL, Kafka, Spring context và một số integration test khác. Để “tối ưu”, ai đó sửa workflow:

```yaml
# PHẢN VÍ DỤ — build xanh nhưng không kiểm kiến trúc.
- name: Build
  run: ./gradlew assemble -x test
```

Thay đổi này có thể làm PR nhanh hơn, nhưng **không còn bằng chứng** rằng `orders` chỉ gọi public API của `catalog`, không import `catalog.internal` và không tạo dependency cycle. Compiler không đủ để bảo vệ mọi quy tắc của Spring Modulith: một Java class `public` trong package nội bộ vẫn có thể bị import hợp lệ theo Java nhưng **trái hợp đồng module**.

Bài thuộc chương **CI và quality gate** trong `SPRING_MODULITH_VERIFICATION_TESTING`: rèn kiểm chứng ranh giới kiến trúc bằng `ApplicationModules`, quy tắc phụ thuộc và `@ApplicationModuleTest`; bổ sung kiểm thử event, database, integration khi cần, nhưng **không để tốc độ build trở thành lý do bỏ phép kiểm kiến trúc**.

Ta dùng ba nguyên tắc vận hành:

1. **Architecture test là required gate.** Chậm thì đo và tối ưu, không `@Disabled`, `-x test` hay `continue-on-error` để né.
2. **Không đồng nhất kiến trúc với integration.** `ApplicationModules.of(...).verify()` không cần khởi tạo toàn bộ Spring `ApplicationContext`; hãy chạy riêng, trước lane nặng.
3. **Không chấp nhận “chạy task thành công” khi không có test nào thực sự chạy.** CI cần dấu vết JUnit report và cơ chế fail nếu target test bị đổi tên/loại khỏi selection.

### Hợp đồng CI cho bài này

| Mã | Yêu cầu | Bằng chứng bắt buộc |
| --- | --- | --- |
| `CI-ARCH-01` | Mọi PR phải chạy architecture verification | Job `Architecture contract` là required check |
| `CI-ARCH-02` | Import internal/dependency cycle bị chặn | `ApplicationModules.verify()` fail |
| `CI-ARCH-03` | Không có test kiến trúc → gate đỏ | Gradle `failOnNoMatchingTests` và kiểm JUnit report |
| `CI-ARCH-04` | Context/JPA/Kafka chậm không được làm mất phép kiểm kiến trúc | Task `architectureTest` độc lập, chạy trước test suite nặng |
| `CI-ARCH-05` | Có thể điều tra vì sao build chậm | Durations/log/report đo được qua từng tầng |
| `CI-ARCH-06` | Trạng thái gate có tính bắt buộc | Không `continue-on-error`, không `if: false` hoặc path filter thiếu kiểm soát |

**Ý nghĩa của PASS:** các quy tắc kiến trúc được Spring Modulith nhận diện đã được kiểm tra thành công với mã hiện tại. PASS không chứng minh mọi transaction/event/DB behavior đúng; chúng cần các gate tương ứng. Ngược lại, test tích hợp nặng không thay thế cho lời hứa về ranh giới module.

## 2. Đo chính xác: chậm ở compile, import kiến trúc hay khởi tạo context?

Trước khi bỏ một task, phải tách thời gian thành ba phần: **biên dịch/resolve dependencies**, **kiểm tra kiến trúc**, và **khởi tạo môi trường cho integration tests**.

Giả sử Gradle project dùng Spring Boot và một `test` task tiêu chuẩn. Chạy các lệnh dưới đây **ở môi trường đo có kiểm soát**, không phải trong bước soạn bài này:

```bash
# Đo tập trung vào architecture test, không chạy cả suite.
./gradlew --no-daemon --console=plain \
  test --tests com.example.shop.ModuleArchitectureTest --profile

# Đo toàn bộ test task khi cần so sánh.
./gradlew --no-daemon --console=plain test --profile

# Khi điều tra một vấn đề bất thường:
./gradlew --no-daemon --console=plain \
  test --tests com.example.shop.ModuleArchitectureTest --info
```

`--profile` tạo báo cáo profiling Gradle trong `build/reports/profile` để thấy phần đáng kể của build; `--info` cung cấp thông tin chọn/thi hành task nhưng log có thể nhiều. Không gửi build scan/log chứa URL nội bộ, secret hoặc dữ liệu khách hàng lên dịch vụ công cộng trái chính sách tổ chức.

### Ghi tối thiểu các số đo

| Đường chạy | Thành phần cần đo | Câu hỏi |
| --- | --- | --- |
| `testClasses` | Dependency resolution, Java/test compilation | Test chưa chạy mà đã chậm? |
| `test --tests ModuleArchitectureTest` | JUnit discovery + Spring Modulith/ArchUnit verification | Verification riêng tốn bao lâu? |
| `test` | Module tests, Spring context, database/broker tests | Phần nào làm suite kéo dài? |
| Cold CI runner | Không có cache, tải dependency mới | Chi phí cold start là bao nhiêu? |
| Warm local/CI cache | Có Gradle cache hợp lệ | Tiết kiệm được bao nhiêu từ incremental build? |

Ví dụ **minh họa** sau khi đo, không phải số liệu mặc định:

| Thành phần | Thời gian |
| --- | ---: |
| Compile source/test từ đầu | 95 giây |
| Chạy riêng `ModuleArchitectureTest` | 4 giây |
| Khởi động PostgreSQL/Kafka và test tích hợp | 11 phút |
| Chạy toàn bộ suite | 13 phút |

Ở đây, **thủ phạm không phải architecture verification**. Bỏ `verify()` chỉ tiết kiệm một phần rất nhỏ nhưng mất nguyên một quality gate. Giải pháp hợp lý là tách task kiến trúc để chạy sớm và cải thiện lane integration.

### Hai điều dễ hiểu sai

- `@ApplicationModuleTest` có thể bootstrap Spring context thật và các auto-configuration liên quan; **test kiến trúc dùng `ApplicationModules.of(...).verify()` không cần annotation đó**.
- Một bài test được Gradle báo `UP-TO-DATE` hoặc `FROM-CACHE` **không tự đồng nghĩa đã bị bỏ qua**: Gradle có thể tái sử dụng kết quả nếu cache inputs đúng. Khi điều tra, so sánh task outcomes và test report; không tự động thêm `--rerun-tasks` vào mọi PR vì có thể làm build chậm vô ích.

## 3. Viết architecture test nhỏ, thuần JUnit và có mục tiêu cụ thể

Giả sử ứng dụng có hai module:

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── catalog/
│   ├── CatalogLookup.java             // API công khai
│   └── internal/
│       ├── CatalogRepository.java    // implementation
│       └── JpaCatalogAdapter.java
└── orders/
    ├── package-info.java
    ├── PlaceOrderService.java
    └── internal/
        └── OrderPolicy.java

src/test/java/com/example/shop/
└── ModuleArchitectureTest.java
```

Root application:

```java
// src/main/java/com/example/shop/ShopApplication.java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Công bố API `catalog`:

```java
// src/main/java/com/example/shop/catalog/CatalogLookup.java
package com.example.shop.catalog;

public interface CatalogLookup {
    boolean isAvailable(String sku);
}
```

Giới hạn quyền phụ thuộc của `orders`:

```java
// src/main/java/com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog"
)
package com.example.shop.orders;
```

Service `orders` chỉ dùng API công khai:

```java
// src/main/java/com/example/shop/orders/PlaceOrderService.java
package com.example.shop.orders;

import com.example.shop.catalog.CatalogLookup;
import org.springframework.stereotype.Service;

@Service
public class PlaceOrderService {

    private final CatalogLookup catalog;

    public PlaceOrderService(CatalogLookup catalog) {
        this.catalog = catalog;
    }

    public boolean canPlace(String sku) {
        return sku != null
            && !sku.isBlank()
            && catalog.isAvailable(sku);
    }
}
```

**Test kiến trúc độc lập:**

```java
// src/test/java/com/example/shop/ModuleArchitectureTest.java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void enforcesApplicationModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Lớp này:

- **Không có `@SpringBootTest` hoặc `@ApplicationModuleTest`**.
- Không inject bean, không tạo DataSource/Kafka producer và không cần Testcontainers.
- Dùng mô hình module do Spring Modulith phát hiện và kiểm tra những ràng buộc `verify()` hỗ trợ, trong đó có dependency cycle và vi phạm API/internal boundary, `allowedDependencies`.
- Được JUnit 5 runner bình thường khám phá; compile source/test theo Gradle là điều kiện cần nhưng **không đồng nghĩa khởi tạo Spring context**.
- Chỉ có một mục tiêu: một vi phạm kiến trúc phải khiến test fail và CI dừng.

Thời gian của `verify()` còn phụ thuộc số class/package, classpath và cơ chế phân tích bytecode; không hứa nó luôn chạy trong số mili-giây. Tuy nhiên, **không cần mang theo chi phí Spring integration context** chỉ để xác minh cấu trúc.

### Vi phạm nào cần bắt?

```java
// PHẢN VÍ DỤ khi CatalogRepository được khai báo public
// nhưng vẫn nằm trong catalog.internal.
import com.example.shop.catalog.internal.CatalogRepository;
```

Java compiler có thể cho import nếu class đủ `public`/visible. Nhưng theo mô hình module thông thường, `catalog.internal` **không phải API public** của application module. Nếu `orders` thực sự dùng kiểu đó, `ModuleArchitectureTest` phải đỏ. Sửa bằng cách thêm/công bố API cần thiết ở `catalog`, **không** bằng cách nới `allowedDependencies` chỉ để có build xanh.

### Kỳ vọng kiến trúc phải được giữ ổn định

| Thay đổi | Compile Java | `ApplicationModules.verify()` |
| --- | --- | --- |
| `orders` gọi `catalog.CatalogLookup` | PASS nếu class tồn tại | PASS theo mô hình |
| `orders` import kiểu `public` từ `catalog.internal` | Có thể PASS | Phải FAIL nếu là vi phạm API exposure |
| Thêm vòng `catalog → orders → catalog` | Có thể PASS | FAIL |
| Thêm module không có dependency trái luật | PASS | PASS |
| Thay giá trả về nhưng giữ API/graph | Có thể PASS | Có thể PASS — cần behavioral test riêng |

**Điểm then chốt:** đây là gate bảo vệ **cấu trúc**, không phải giá trị nghiệp vụ. Đừng nhét JPA, HTTP hoặc listener tests vào class này rồi phàn nàn rằng “architecture test quá chậm”.

## 4. Tách một task Gradle `architectureTest` và fail khi không chọn được test

Một project Gradle dùng `java` plugin/Spring Boot thường có source set `test` và task `test`. Tạo task **riêng** chỉ chạy `ModuleArchitectureTest`, nhưng tái sử dụng các class đã compile.

```groovy
// build.gradle (Groovy DSL) — đoạn cấu hình bổ sung.
// Giả định project áp dụng plugin 'java' hoặc Spring Boot
// và đã có JUnit Platform dependencies.

tasks.register('architectureTest', Test) {
    group = 'verification'
    description =
        'Verify Spring Modulith boundaries without Boot context'

    dependsOn tasks.named('testClasses')

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform()

    filter {
        includeTestsMatching(
            'com.example.shop.ModuleArchitectureTest')
        failOnNoMatchingTests = true
    }

    reports {
        junitXml.required = true
        html.required = true
    }
}

// ./gradlew check vẫn phải chạy architectureTest.
tasks.named('check') {
    dependsOn tasks.named('architectureTest')
}
```

Với mô hình này:

- `./gradlew architectureTest` chỉ chọn class kiến trúc qua Gradle `TestFilter`. Nó **vẫn biên dịch** những class cần thiết, nhưng không chạy mọi Spring context/database/broker tests.
- `includeTestsMatching` chỉ chọn test được định danh; `failOnNoMatchingTests = true` khiến task fail khi không tìm thấy test phù hợp theo filter. Một đổi tên class không được biến thành “0 tests, exit 0”.
- `./gradlew check` gồm task architecture do quan hệ `dependsOn`, đồng thời vẫn giữ lifecycle kiểm thử khác của Java plugin.
- Vì `ModuleArchitectureTest` cũng nằm trong source set `test`, `./gradlew test` thông thường **có thể chạy thêm test đó lần nữa**. Đây là sự trùng lặp nhỏ có chủ đích; không được loại nó khỏi cả hai task để “tối ưu”.
- Chạy `architectureTest` sẽ có JUnit XML tại `build/test-results/architectureTest` và HTML tại `build/reports/tests/architectureTest` theo layout Gradle thông dụng.

### Nếu architecture test bị `@Disabled` thì sao?

`failOnNoMatchingTests` bảo vệ trường hợp **không có test phù hợp**, nhưng một test được chọn rồi đánh dấu `@Disabled` có thể được report là `skipped` mà task vẫn PASS. Do đó CI cần thêm **evidence assertion**: test count phải dương, skipped count phải bằng 0 và report phải tồn tại. Bước này sẽ xuất hiện ở workflow phần 5.

### Mẫu dependency cần thiết

```groovy
dependencies {
    implementation(
        'org.springframework.modulith:spring-modulith-starter-core')

    testImplementation(
        'org.springframework.boot:spring-boot-starter-test')
    testImplementation(
        'org.springframework.modulith:spring-modulith-starter-test')
}
```

Các tọa độ trên là **mẫu cho dự án đã quản lý phiên bản tương thích bằng BOM**. Đối chiếu Spring Boot/Spring Modulith version thật của project khi thêm dependency. Không tự nhét một phiên bản starter khác vào một build đã có dependency management.

**Lưu ý về tính tự chứa:** đây là ví dụ **single-project Gradle Groovy DSL**. Với multi-project, điều chỉnh task/source set và đường dẫn report theo subproject chứa `ShopApplication`. Với Kotlin DSL, cú pháp cần đổi sang `build.gradle.kts`; không copy Groovy vào Kotlin file.

## 5. CI bắt buộc: chạy kiến trúc sớm và xác nhận có test thật

Ví dụ GitHub Actions tách hai job:

- `architecture`: chạy test kiến trúc trước, fail sớm;
- `module-tests`: chạy test suite sau khi gate kiến trúc đạt.

Để minh họa, project là Gradle single-module và task `architectureTest` được khai báo như phần 4.

```yaml
# .github/workflows/modulith-quality-gates.yml
name: Modulith quality gates

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  architecture:
    name: Architecture contract
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Verify module boundaries
        run: >
          ./gradlew --no-daemon --console=plain
          architectureTest

      - name: Verify actual test evidence
        shell: bash
        run: |
          report="build/test-results/architectureTest/TEST-com.example.shop.ModuleArchitectureTest.xml"
          test -s "$report"
          grep -Eq 'tests="[1-9][0-9]*"' "$report"
          grep -q 'skipped="0"' "$report"

      - name: Keep architecture report
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: architecture-contract-report
          path: |
            build/test-results/architectureTest/
            build/reports/tests/architectureTest/
          if-no-files-found: warn
          retention-days: 7

  module-tests:
    name: Module and integration tests
    needs: architecture
    runs-on: ubuntu-latest
    timeout-minutes: 40

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Test module behavior and integrations
        run: >
          ./gradlew --no-daemon --console=plain test
```

### Vì sao workflow này không “làm màu”?

1. Job `Architecture contract` **không có `continue-on-error: true`**. Khi `verify()` fail, job fail.
2. Job này **không có path filter** cho chỉ Java source; vì các thay đổi `build.gradle`, plugin, module detection, package metadata cũng có thể tác động kiến trúc.
3. `module-tests` có `needs: architecture`, nên nếu kiến trúc fail sẽ không chạy lane nặng. Điều này giảm chi phí CI khi PR có dependency sai.
4. `architectureTest` dùng Gradle filter fail khi target test không còn được nhận diện.
5. Bước `Verify actual test evidence` buộc có JUnit XML, số `tests` dương và `skipped=0`. Nó giảm nguy cơ test bị `@Disabled` nhưng job vẫn xanh.
6. Report được upload kể cả khi test job fail; tùy nguyên nhân compile failure mà chưa có report, `if-no-files-found: warn` tránh làm mờ root cause.
7. `test` ở job sau chạy suite tiêu chuẩn; khi cần chia integration tests theo lane riêng, phải giữ gate kiến trúc bắt buộc.

**Hạn chế cần ghi rõ:** `grep` ở đây đọc thuộc tính trên Gradle JUnit XML mặc định, phù hợp ví dụ 1 test class. Với report tùy chỉnh hoặc nhiều class, nên thay bằng parser XML có kiểm tra `tests/failures/errors/skipped` tổng hợp, không dựa vào grep văn bản. Một report tồn tại với `tests>0` chỉ chứng minh số test chạy trong report đó, nên task filter/class name phải được review cùng CI.

### Required check mới thực sự chặn merge

YAML có job fail chưa đủ nếu branch protection không yêu cầu check đó. Repository owner cần cấu hình **required status check** cho job `Architecture contract` (và `Module and integration tests` hoặc gate tương ứng), không cho merge khi job bị skip/fail.

Nếu dùng rulesets/branch protection với workflow khác, kiểm tra **tên check và sự kiện kích hoạt thực tế**. Tránh đặt toàn workflow sau `paths:` filtering khiến một required check không chạy; tùy cấu hình GitHub, trạng thái pending/skipped có thể gây kẹt hoặc bỏ bảo vệ theo cách không mong muốn. Lựa chọn an toàn cho bài là **architecture gate chạy ở mọi PR**.

## 6. Tối ưu thời gian có đo lường, không làm yếu `verify()`

Sau khi đã có task kiến trúc riêng, tối ưu theo **nút thắt đã đo**.

| Nút thắt | Tối ưu ưu tiên | Giữ lại bằng chứng gì? |
| --- | --- | --- |
| Dependency download chậm | Gradle dependency cache/mirror đáng tin | Artifact/dependency versions xác định |
| Compile nặng | Incremental compilation, tránh `clean` không cần thiết | Class files đúng source/current inputs |
| Configuration phase chậm | Configuration cache **nếu project/plugins tương thích** | Re-run test khi inputs thay đổi |
| Architecture import chậm | Giữ root package và module detection đúng phạm vi | Toàn bộ module cần bảo vệ vẫn được kiểm |
| `@SpringBootTest` khởi động chậm | Không đặt Spring context vào test architecture | `ApplicationModules.verify()` vẫn chạy |
| DB/Kafka integration lâu | Tách lane, fixture phù hợp, parallel có kiểm soát | Integration assertions không bị xóa |
| Test chạy lặp nhiều lần | Hạn chế task trùng khi đã có gate bắt buộc | Không tạo “0 tests” hoặc skip âm thầm |
| Runner cold start | Cache toolchain/dependencies phù hợp chính sách | JUnit report và required check vẫn có |

### Không tối ưu bằng cách thu nhỏ mô hình sai

Một mẹo dễ gây hại là thay:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

bằng một phân tích package nhỏ chỉ chứa `orders` mà **bỏ hẳn `catalog`/các module khác**. Việc này có thể khiến test nhanh hơn vì đã ngừng kiểm tra những dependency cần bảo vệ.

Tối ưu hợp lệ cần giữ **cùng tập module và quy tắc cần kiểm chứng**. Nếu ứng dụng có mô hình module tùy chỉnh, hãy dùng root/config đúng thiết kế. Một hiệu năng tốt nhờ ít kiểm tra hơn không phải tối ưu chất lượng.

### Cache là công cụ, không phải lý do bỏ test

Gradle có thể tái sử dụng task outputs hợp lệ khi inputs không đổi. Đây là hành vi bình thường, nhưng CI vẫn cần:

- Chạy hoặc xác nhận `architectureTest` được coi là dependency bắt buộc.
- Bảo đảm input classpath/source/config là một phần của cache key đúng.
- Lưu và đọc JUnit report phù hợp; không tin một dòng `BUILD SUCCESSFUL` khi task test không có bằng chứng.
- Khi nghi vấn lỗi cache, chạy lại với `--rerun-tasks` **chỉ để chẩn đoán**, không bật mặc định trên mọi PR.
- Không dùng `-x architectureTest` trong PR lane.

**Không có “magic flag”** giúp giữ nguyên mọi cam kết kiến trúc nhưng bỏ qua hoàn toàn phần phân tích. Hãy đo và giảm phần thừa ở compile/config/integration trước.

### Một khác biệt quan trọng khi chạy song song

Các integration tests có thể dùng nhiều threads/containers; đổi `maxParallelForks` quá cao có thể khiến máy CI nghẽn tài nguyên, tạo flaky tests và còn chậm hơn. Architecture test chỉ một class thường không được lợi từ nhiều fork; ưu tiên một fork và cache classpath hợp lệ hơn là tăng concurrency mù.

## 7. Giữ architecture gate riêng nhưng không bỏ module/event/database gates

Tối ưu `architectureTest` **không có nghĩa** mọi test khác đều phải chạy cùng tốc độ hoặc nằm cùng job.

Một phân tầng đúng:

| Lane | Công cụ | Phải chạy khi nào? |
| --- | --- | --- |
| **Architecture** | JUnit `ApplicationModules.verify()` | Mọi PR/required check, sớm |
| **Module behavior** | `@ApplicationModuleTest`, Mockito override đúng boundary | PR, trước merge |
| **Event behavior** | `PublishedEvents` hoặc `Scenario` theo contract | PR/integration gate phù hợp |
| **Persistence** | JPA/JDBC + Testcontainers | Required trước phát hành nếu sửa dữ liệu/transaction |
| **External messaging** | Kafka/RabbitMQ + contract/integration | Required trước phát hành nếu event delivery là hợp đồng |
| **Deployment smoke** | Config/profile/adapter thật ở môi trường tương ứng | Trước khi rollout hoặc tại deployment gate |

### Ví dụ module behavior không được lẫn vào test kiến trúc

Giả sử `orders` công bố `OrderRequested` sau khi kiểm tra giá:

```java
// src/main/java/com/example/shop/orders/OrderRequested.java
package com.example.shop.orders;

public record OrderRequested(
    String orderId, String sku) {
}
```

Một `@ApplicationModuleTest` có thể dùng collaborator public API `CatalogLookup` được mock:

```java
// Fragment trong test ở package com.example.shop.orders.
// Cần OrderRequestService thực, @MockitoBean CatalogLookup,
// @Autowired service và @ApplicationModuleTest.
given(catalog.isAvailable("SKU-1")).willReturn(true);

orders.request("ORD-1", "SKU-1");

assertThat(events.ofType(OrderRequested.class))
    .singleElement()
    .satisfies(e ->
        assertThat(e.orderId()).isEqualTo("ORD-1"));
```

Đây **chỉ là fragment**, không phải lớp test chạy độc lập: `OrderRequestService` và các fixture cần được định nghĩa trong ứng dụng thực. Nó minh họa một assertion hành vi khác `verify()`. `PublishedEvents` chỉ chứng minh sự kiện được công bố trong Spring context; nó không xác nhận commit hoặc broker acknowledgement.

Khi tích hợp `@TransactionalEventListener(AFTER_COMMIT)` hay `@ApplicationModuleListener`, test phải tạo transaction commit đúng và chờ **điều kiện nghiệp vụ** có timeout hữu hạn; không đặt `Thread.sleep(...)` rồi coi kết quả là hợp đồng. Với database, giữ repository/schema thật và Testcontainers khi cần kiểm tra rollback/unique constraint.

**Chiến lược đúng cho build chậm:** architecture lane nhanh chặn structural regressions trước; những lane khác được tối ưu/cô lập theo chi phí nhưng vẫn có lịch chạy và mức bắt buộc phù hợp rủi ro. Không đẩy tất cả về nightly nếu requirement yêu cầu gate trước merge hoặc release.

## 8. Tự kiểm chứng rằng gate thực sự bắt lỗi và không thể bị vô hiệu hóa âm thầm

Một pipeline chỉ đáng tin nếu có thể **cố ý phá một quy tắc** và quan sát kết quả như mong đợi. Thực hiện các thí nghiệm sau trên branch/PR thử nghiệm, không merge code sai:

### Thử nghiệm A — Vi phạm architectural boundary

Giả định `catalog.internal.CatalogRepository` là Java `public` nhưng không được công bố làm module API. Thêm một phụ thuộc thực từ `orders` đến kiểu đó.

```java
// PHẢN VÍ DỤ — chỉ đặt trong branch thử nghiệm.
package com.example.shop.orders.internal;

import com.example.shop.catalog.internal.CatalogRepository;

class WrongCatalogDependency {

    private final CatalogRepository repository;

    WrongCatalogDependency(CatalogRepository repository) {
        this.repository = repository;
    }
}
```

Dự đoán:

- Java có thể compile nếu visibility và dependencies đủ.
- `architectureTest` phải **FAIL** vì `orders` dùng internal API module `catalog` theo ranh giới mặc định.
- `Architecture contract` phải đỏ, job `module-tests` có `needs` không tiếp tục.
- JUnit report giữ failure details.
- Sau đó **revert code vi phạm**; không sửa test bằng cách mở rộng allowed dependencies.

**Điều kiện:** ví dụ `CatalogRepository` ở đây là một kiểu công khai **giả định** trong package internal. Không tự sửa implementation thật để “tạo” kiểu đó trong bài; mục tiêu là kiểm chứng policy tại repository đang sử dụng.

### Thử nghiệm B — Đổi tên hoặc gỡ test kiến trúc

Tạm thời đổi tên `ModuleArchitectureTest` thành `ModuleBoundaryCheck` nhưng **không sửa `includeTestsMatching`**. Expected: `architectureTest` FAIL do không còn match.

Tạm thời đánh dấu `@Disabled` lên method `enforcesApplicationModuleBoundaries`. Expected: report có `skipped>0` và bước `Verify actual test evidence` FAIL.

Nếu một trong hai trường hợp job vẫn xanh, **gate đang có lỗ hổng** dù YAML trông có vẻ hợp lý.

### Thử nghiệm C — Bỏ qua job bằng CI condition

Một thay đổi đề xuất:

```yaml
# PHẢN VÍ DỤ: kiến trúc có thể bị bỏ qua.
jobs:
  architecture:
    if: false
    runs-on: ubuntu-latest
    steps:
      - run: ./gradlew architectureTest
```

Không chấp nhận đề xuất này. Required check/branch ruleset phải được thiết kế để **không cho merge khi architecture job không thực sự đạt điều kiện**. Kiểm tra trên branch thử nghiệm, không suy luận từ tên job.

### Bảng kết quả phải quan sát được

| Thí nghiệm | Kỳ vọng |
| --- | --- |
| Code hợp lệ, test đầy đủ | `Architecture contract` PASS; XML có tests dương, skipped 0 |
| Import `catalog.internal` trái quy tắc | `architectureTest` FAIL, PR không merge |
| Class test bị đổi tên | Gradle filter FAIL, không có silent PASS |
| Test bị `@Disabled` | Evidence assertion FAIL |
| `-x architectureTest` ở một lệnh không phải CI | `check` có thể bị ép skip ở lệnh đó; **CI không được dùng lệnh ấy** |
| DB/Kafka integration chậm nhưng architecture đúng | Architecture PASS sớm; lane integration tiếp tục kiểm chứng riêng |

**Cảnh báo về `-x`:** người dùng vẫn có thể ép Gradle bỏ một task khi chạy local. Quality gate là ràng buộc của **CI required check** và quyền cấu hình repository, không phải một phép màu khiến mọi lệnh local không thể skip.

## 9. Khi architecture test vẫn chậm: xử lý theo nguyên nhân, không theo cảm giác

Có những codebase lớn mà việc phân tích dependency module cũng tốn thời gian đáng kể. Hãy dùng kết quả profiling ở mục 2 để chọn xử lý:

| Triệu chứng | Giả thuyết cần kiểm | Hành động |
| --- | --- | --- |
| `architectureTest` chậm ngay lần đầu, lần sau nhanh | Cold dependency/compile/cache | Kiểm tra dependency cache và incremental compile |
| Mỗi lần đều chậm trước khi JUnit bắt đầu | Task configuration, annotation processing, test compilation | Đọc Gradle `--profile`/task timings |
| Chỉ chậm trong `verify()` | Classpath/import/module discovery quá rộng | Rà root package, module detection, artifact/classpath không cần thiết nhưng **không bỏ module có nghĩa vụ kiểm** |
| Chậm khi start container | Architecture test đã kéo theo Spring/integration setup | Bỏ `@SpringBootTest`/container setup khỏi class kiến trúc, tách đúng lane |
| Context reload liên tục | Module tests khác không tái sử dụng cache do profile/mock khác | Tối ưu test configuration ở lane behavior, không bỏ `verify()` |
| CI thường xuyên timeout | Runner thiếu CPU/RAM hoặc concurrency quá cao | Đo hardware/resource contention, giảm fork/tách job |
| Test architecture có lúc PASS/FAIL cùng commit | Khác classpath/test selection/cache, race ở dữ liệu test phụ trợ | Điều tra log; không coi cycle/internal import là “flake đã được retry chữa” |
| Required check không thấy chạy trên vài PR | Workflow paths/if/branch rules | Sửa event trigger và branch protection |
| CI xanh bất ngờ dù không có XML | Target test bị bỏ hoặc report path sai | Bật fail-on-no-match và evidence assertion |

### Ba phản ứng cần tránh

1. **Bỏ `ApplicationModules.verify()` khỏi PR rồi chỉ chạy nightly.** Nếu dependency sai được merge, nightly phát hiện quá muộn. Có thể thêm nightly cho bài stress nặng, nhưng architecture gate nhanh vẫn phải bắt buộc.
2. **Chạy toàn bộ `@SpringBootTest` chỉ để verify dependency.** Điều này làm phép kiểm cấu trúc chịu chi phí của database/config/HTTP mà nó không cần.
3. **Tăng retry khi lỗi verify do import sai.** Dependency cycle/internal access là lỗi của source/classpath hiện tại; retry không sửa hợp đồng và làm CI lâu hơn.

Nếu phải lập mục tiêu hiệu năng, đặt ngân sách thực tế dựa trên số đo và hardware CI (ví dụ “architecture job p95 dưới X phút”) nhưng **không biến timeout nhỏ tùy ý thành lý do skip**. Khi vượt ngân sách, điều tra bottleneck; gate vẫn không được vô hiệu hóa.

## 10. Checklist và bài tập triển khai quality gate bền vững

### Checklist trước khi merge workflow

- [ ] Có `ModuleArchitectureTest` thuần JUnit, gọi `ApplicationModules.of(...).verify()` trên đúng application root.
- [ ] `@ApplicationModule(allowedDependencies=...)` và public/internal API được công bố có chủ đích.
- [ ] Architecture test **không** bootstrap Spring context hoặc Testcontainers chỉ để kiểm graph.
- [ ] Có Gradle `architectureTest` chọn đúng test, `failOnNoMatchingTests=true`.
- [ ] `check` phụ thuộc `architectureTest`, không có logic skip ngầm.
- [ ] CI chạy architecture gate trên mọi PR được bảo vệ, **không path filter thiếu kiểm soát**.
- [ ] Job `Architecture contract` là required status check/branch ruleset, không `continue-on-error`.
- [ ] JUnit XML chứa `tests>0`, `skipped=0`; failure artifacts được giữ.
- [ ] Không dùng `-x test`, `-x architectureTest`, `@Disabled` hay `if: false` để giải quyết chậm.
- [ ] Đã đo riêng compile, architecture verification và integration time.
- [ ] Gradle cache/incremental build được cấu hình an toàn; không ép rerun mọi task vô ích.
- [ ] Module behavior, event, JPA và messaging gates có lane rõ, không bị bỏ vĩnh viễn.
- [ ] Đã chạy một thử nghiệm cố ý vi phạm internal boundary và xác nhận job đỏ.
- [ ] Đã thử đổi tên/disable test và xác nhận CI **không** xanh giả.
- [ ] Với multi-project/custom Gradle task, đã chỉnh filter và report path đúng nơi chạy test.

### Bài tập A — Chọn cách rút ngắn build

CI mất 14 phút, trong đó biên dịch 1 phút, `ModuleArchitectureTest` 3 giây, Kafka/JPA integration 12 phút. Chọn một:

- **A:** bỏ `ApplicationModules.verify()` để giảm thời gian;
- **B:** chạy `architectureTest` trước và tách integration thành lane có cache/fixture tốt hơn;
- **C:** bật `continue-on-error: true` cho test architecture.

**Đáp án:** **B**. Hai cách còn lại đánh đổi chất lượng để tiết kiệm không đáng kể hoặc tạo gate không còn hiệu lực. Nếu integration là điều kiện phát hành, vẫn phải có required gate phù hợp trước release.

### Bài tập B — Test không còn được discover

Một developer đổi tên `ModuleArchitectureTest`, nhưng task Gradle vẫn match class cũ. Điều gì phải xảy ra?

**Đáp án:** `failOnNoMatchingTests=true` khiến `architectureTest` fail. Nếu task vẫn xanh, kiểm tra cấu hình filter và Gradle/JUnit versions. Đồng thời kiểm JUnit XML để tránh trường hợp test match nhưng bị `@Disabled`.

### Bài tập C — Đánh giá một PR “tối ưu” sai

PR thêm cấu hình vô hiệu hóa task:

```groovy
tasks.named('architectureTest') {
    enabled = false // PHẢN VÍ DỤ: không thực thi verification.
}
```

Đoạn Gradle trên có thể khiến task bị **SKIPPED** ngay cả khi nó vẫn nằm trong dependency graph của `check`. Khi review, phải yêu cầu bỏ `enabled = false`, giữ `check.dependsOn(architectureTest)` và required CI job, sau đó đo lại bottleneck. Không chấp nhận một build xanh vì task kiến trúc không thực thi.

### Definition of Done

Một triển khai đạt yêu cầu khi:

1. **Hợp đồng kiến trúc được diễn đạt thành test có thể chạy.**
2. **Test được chọn, thực sự thực thi và có JUnit report** trên PR.
3. **Vi phạm module làm required check thất bại**, không có đường tắt bỏ qua.
4. **Thời gian build được cải thiện bằng đo/tối ưu**, không bằng giảm mức kiểm chứng.
5. **Behavior/integration gates vẫn tồn tại** cho các cam kết event, transaction, database hoặc messaging.

**Ghi nhớ:** `ApplicationModules.verify()` là một **quality gate kiến trúc** chứ không phải phụ phẩm của test suite dài. Nếu build chậm, hãy đo thời gian, tách `architectureTest` thuần JUnit, dùng Gradle/CI cache đúng cách và đưa job thành required check có bằng chứng `tests>0`. Giải pháp đúng giúp pipeline nhanh hơn **mà vẫn chặn import internal, dependency cycle và vi phạm quy tắc module trước khi merge**.
