# Thu thập report khi test thất bại

Trong CI của ứng dụng **Spring Modulith**, một quality gate tốt phải đồng thời làm được hai việc: **trả trạng thái thất bại** khi vi phạm ranh giới module hoặc kiểm thử hồi quy không đạt, và **giữ lại bằng chứng** đủ để tìm nguyên nhân. Nếu pipeline dừng ngay ở lệnh kiểm thử mà không xuất bản report, người sửa lỗi chỉ thấy một job đỏ và phải chạy lại toàn bộ bộ test.

Bài này tập trung vào việc tạo, thu thập, đọc và kiểm tra report sau những lỗi từ `ApplicationModules.verify()`, `@ApplicationModuleTest`, JUnit 5, kiểm thử sự kiện và cơ sở dữ liệu. Các ví dụ dùng Java 21 và dự án Maven hoặc Gradle; chọn **một** hệ build tương ứng với repository.

## 1. Xác định bộ bằng chứng cần giữ lại

Một lần chạy thất bại nên để lại ít nhất **tên test, nguyên nhân, stack trace, định danh commit và job, thời điểm chạy**. Dùng định dạng máy đọc được để CI tổng hợp, và định dạng dễ đọc để lập trình viên điều tra.

| Nguồn lỗi | Bằng chứng cần có | Nơi thường sinh ra |
| --- | --- | --- |
| Quy tắc phụ thuộc module vi phạm `ApplicationModules.verify()` | JUnit XML, stack trace mô tả module và dependency sai | Maven `target/surefire-reports/` hoặc Gradle `build/test-results/test/` |
| `@ApplicationModuleTest` không khởi tạo được application context | JUnit XML ghi `error`, stack trace `BeanCreationException` hoặc lỗi cấu hình | Report của task chạy test |
| Assertion/event bất đồng bộ không đạt | JUnit XML ghi `failure`, thông điệp assertion, log có correlation ID | Report của test hoặc integration test |
| Database/Testcontainers lỗi khi thiết lập | Stack trace trong JUnit XML nếu test đã được phát hiện, log khởi tạo và container | Report test, log build và log test có kiểm soát |
| Compile, resolve dependency hoặc plugin thất bại trước khi JUnit chạy | Log build và mã thoát khác 0; **có thể không có JUnit XML** | `build.log` hoặc `gradle-build.log` |

Phân biệt rõ **bằng chứng** và **quyết định gate**: upload artifact thành công không biến test hỏng thành thành công. Mã thoát của lệnh build vẫn phải là nguồn quyết định pass/fail.

## 2. Biến kiểm chứng kiến trúc thành một JUnit test có tên rõ ràng

Đừng gọi `ApplicationModules.verify()` trong script tùy ý nếu muốn CI ghi nhận nó như một test case độc lập. Đặt lời gọi trong JUnit 5 để lỗi xuất hiện trong report XML, gắn với lớp và tên phương thức cụ thể:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithArchitectureTest {

    @Test
    void moduleDependenciesMustRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Trong ví dụ, `ShopApplication` là lớp `@SpringBootApplication` của ứng dụng mẫu và nằm ở package gốc chứa các module. Nếu một module gọi vào kiểu không được phép của module khác, `verify()` làm test thất bại; report ghi stack trace và phần mô tả vi phạm do Spring Modulith/ArchUnit cung cấp. Lệnh chạy riêng để tái hiện với Maven:

```bash
./mvnw -B -ntp -Dtest=ModulithArchitectureTest test
```

Việc tách test kiến trúc khỏi test tích hợp giúp người đọc report xác định ngay lỗi phụ thuộc module, thay vì lẫn với lỗi database hoặc khởi tạo Spring context. Không bắt exception của `verify()` để chỉ in log: làm vậy JUnit có thể đánh dấu test là pass.

## 3. Để kiểm thử module và sự kiện tạo report có thể truy vết

`@ApplicationModuleTest` nạp lát cắt ứng dụng phù hợp với module được kiểm tra. Ví dụ sau giả định module `inventory` có bean `InventoryService` và phát sự kiện miền `ReplenishmentRequested` khi yêu cầu giữ hàng vượt ngưỡng:

```java
package com.acme.shop.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class InventoryEventsIT {

    @Autowired
    InventoryService inventoryService;

    @Test
    void publishesReplenishmentRequest(Scenario scenario) {
        scenario.stimulate(() -> inventoryService.reserve("SKU-42", 999))
                .andWaitForEventOfType(ReplenishmentRequested.class)
                .toArrive();
    }
}
```

`InventoryService`, `reserve(...)` và `ReplenishmentRequested` là API miền **giả định** của ứng dụng ví dụ, cần thay bằng API thật của dự án. `Scenario` chờ sự kiện thay cho việc dùng `Thread.sleep(...)`; nếu sự kiện không đến theo điều kiện/chờ đợi được cấu hình, test thất bại và có tên trong report. Khi test kiểm tra dữ liệu, cần ghi rõ database dùng trong CI (Testcontainers hoặc môi trường test), migration/schema và cách cô lập dữ liệu giữa các test; thời gian chờ sự kiện phải có giới hạn để job không treo.

Tên `InventoryEventsIT` có chủ đích: **Maven Failsafe** mặc định nhận mẫu `*IT`, còn **Surefire** mặc định nhận `*Test`. Việc đặt tên phải đi cùng cấu hình plugin và lifecycle; nếu CI chỉ chạy `test` thì bài test `*IT` có thể chưa được thực thi.

## 4. Maven: giữ XML và stack trace từ Surefire/Failsafe

Trong dự án Maven, Surefire thường thực thi unit/architecture tests ở phase `test`; Failsafe dành cho integration tests với các goal `integration-test` và `verify`. Cấu hình mẫu dưới đây dùng cùng phiên bản plugin để cố định hành vi trong CI:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
            <configuration>
                <trimStackTrace>false</trimStackTrace>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>3.5.4</version>
            <configuration>
                <trimStackTrace>false</trimStackTrace>
            </configuration>
            <executions>
                <execution>
                    <goals>
                        <goal>integration-test</goal>
                        <goal>verify</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Chạy `./mvnw -B -ntp verify` để có cả hai nhóm (nếu thực sự có test khớp mẫu). Kiểm tra đầu ra:

| Loại report | Đường dẫn trong từng Maven module | Dùng để |
| --- | --- | --- |
| Surefire JUnit XML | `target/surefire-reports/TEST-*.xml` | Architecture/unit tests và annotation-based tests có tên `*Test` |
| Failsafe JUnit XML | `target/failsafe-reports/TEST-*.xml` | Các test `*IT` được Failsafe chạy |
| Bản text | `target/surefire-reports/*.txt` và `target/failsafe-reports/*.txt` | Đọc nhanh thất bại và stack trace |
| JaCoCo (nếu đã cấu hình) | `target/site/jacoco/` hoặc `target/site/jacoco-it/` | Chứng cứ coverage, **không thay thế** JUnit report |

Với multi-module Maven, report nằm **dưới từng submodule**; đường dẫn artifact phải quét đệ quy. Không dùng `-Dmaven.test.failure.ignore=true` hoặc cấu hình `testFailureIgnore` nếu mục tiêu là gate đỏ khi test fail.

## 5. Gradle: bật XML/HTML cho tất cả task kiểu Test

Gradle sinh JUnit XML và HTML cho task `test` theo cấu hình report. Để nhất quán cả với task tích hợp tự tạo, khai báo trong `build.gradle.kts`:

```kotlin
import org.gradle.api.tasks.testing.Test
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }

    testLogging {
        events("failed", "skipped")
        exceptionFormat = TestExceptionFormat.FULL
    }
}
```

Chạy `./gradlew --console=plain check` khi task tích hợp đã được nối vào lifecycle `check`. Nếu dự án tự tạo task `integrationTest` nhưng chưa đưa vào `check`, cần gọi task đó một cách tường minh; Gradle **không tự cung cấp** task `integrationTest` cho mọi dự án.

Đường dẫn mặc định của `test` là `build/test-results/test/TEST-*.xml` và `build/reports/tests/test/index.html`. Với task `integrationTest`, thư mục tương ứng thường là `build/test-results/integrationTest/` và `build/reports/tests/integrationTest/`. CI nên upload `**/build/test-results/**` và `**/build/reports/tests/**` để bao phủ nhiều project/task. Tương tự Maven, giữ lỗi thực bằng cách không đặt `ignoreFailures = true`.

## 6. GitHub Actions: upload artifact dù lệnh verify thất bại

Ví dụ sau áp dụng cho **Maven**. `set -o pipefail` rất quan trọng: khi chuyển output qua `tee`, job vẫn nhận mã lỗi từ `./mvnw`. Bước upload có `if: always()` để được xét chạy sau bước kiểm thử thất bại.

```yaml
name: modulith-quality-gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verification:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Verify module rules and tests
        shell: bash
        run: |
          set -o pipefail
          ./mvnw -B -ntp verify 2>&1 | tee build.log

      - name: Keep diagnostic evidence
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: modulith-report-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            build.log
            **/target/surefire-reports/
            **/target/failsafe-reports/
            **/target/site/jacoco/
          if-no-files-found: warn
          retention-days: 14
```

Giả định repository có Maven Wrapper `./mvnw`; nếu không, dùng `mvn` tương ứng. Với matrix build, bổ sung biến thể JDK/OS vào `name` để mỗi job có artifact riêng. `if-no-files-found: warn` giúp nhận ra trường hợp không sinh report, nhưng cần điều tra nguyên nhân thay vì coi đây là test pass. `retention-days` cần phù hợp chính sách lưu trữ của tổ chức.

Nếu dùng **Gradle**, thay lệnh kiểm thử bằng `./gradlew --console=plain check` và thay các đường dẫn `target/...` bằng `**/build/test-results/**`, `**/build/reports/tests/**`, cùng log `gradle-build.log` nếu đã ghi qua `tee`. Giữ `pipefail` như trên.

## 7. GitLab CI: lưu artifact và xuất bản JUnit cho giao diện pipeline

Với GitLab, `artifacts: when: always` bảo đảm runner cố gắng upload sau khi `script` trả mã lỗi; `reports:junit` giúp giao diện merge request/pipeline hiển thị test case thất bại. Mẫu Maven:

```yaml
modulith-verification:
  stage: test
  image: eclipse-temurin:21-jdk
  script:
    - ./mvnw -B -ntp verify
  artifacts:
    when: always
    paths:
      - "**/target/surefire-reports/"
      - "**/target/failsafe-reports/"
    reports:
      junit:
        - "**/target/surefire-reports/TEST-*.xml"
        - "**/target/failsafe-reports/TEST-*.xml"
    expire_in: 14 days
```

Image JDK cần có công cụ Maven Wrapper có thể chạy được (wrapper tải Maven phù hợp khi cần); trong môi trường chỉ có JDK và không truy cập được kho artifact, hãy dùng image/build environment đã chuẩn bị cho CI. Log lệnh `script` được GitLab lưu ở job log theo chính sách hệ thống; nếu cần tệp log riêng, dùng `tee` cùng cơ chế giữ mã lỗi của shell. `reports:junit` không được nhầm với `paths`: phần đầu phục vụ trình tổng hợp test, phần sau phục vụ tải file để điều tra.

## 8. Đọc JUnit XML để phân loại lỗi đúng

Một report JUnit XML thường chứa `<testsuite>` và `<testcase>`, với nhánh `<failure>` cho assertion thất bại, `<error>` cho lỗi thực thi/khởi tạo test, `<skipped>` cho test bỏ qua. Tên chính xác và nội dung element tùy phiên bản test runner. Ví dụ **minh họa cấu trúc**, không phải output cố định của Spring Modulith:

```xml
<testsuite name="com.acme.shop.ModulithArchitectureTest"
           tests="1" failures="1" errors="0" skipped="0">
  <testcase name="moduleDependenciesMustRespectBoundaries"
            classname="com.acme.shop.ModulithArchitectureTest">
    <failure message="Module dependency violation">
      Violation details and stack trace...
    </failure>
  </testcase>
</testsuite>
```

Khi điều tra, dùng thứ tự: **test case → loại lỗi → thông điệp đầu tiên có nguyên nhân → stack trace → commit/build tương ứng**. Với Spring Modulith:

- Architecture test fail: đọc cặp module và kiểu phụ thuộc bị cấm; sửa thiết kế hoặc public API/named interface đúng quy ước, không ẩn lỗi bằng cách bỏ test.
- Module test báo `error` khi khởi tạo context: tìm `Caused by` gốc; kiểm tra dependency của module, cấu hình test, bean, migration và profile.
- Event test fail: xem sự kiện nào được chờ, tác vụ nào kích hoạt, có timeout hay rollback transaction không; đối chiếu log theo correlation ID.
- Integration DB fail: phân biệt lỗi kết nối/khởi tạo container với assertion sai dữ liệu; lưu phiên bản database, migration và log không chứa dữ liệu nhạy cảm.

Không dựa duy nhất vào tổng số `tests`/`failures` của một file: test bị bỏ qua, thiếu report hoặc job compile fail có thể khiến thống kê bằng 0 dù pipeline hỏng. So khớp **mã thoát build**, số report được tìm thấy và danh sách test dự kiến.

## 9. Ghi log chẩn đoán đủ dùng nhưng tránh lộ thông tin

Log hữu ích nên chứa **tên module, test, correlation ID, tên sự kiện, topic/queue, migration version, container hoặc profile test**; khi lỗi bất đồng bộ, nên có thời điểm phát và nhận sự kiện. Log không cần chứa mật khẩu, token, chuỗi kết nối có credential, payload khách hàng hay bản dump cơ sở dữ liệu.

Với test chạy nhiều luồng hoặc event delivery, dùng correlation ID ổn định trong một test case để nối request → publish → consume → assertion. Dùng log level `INFO` hoặc `DEBUG` có chọn lọc ở package test; tránh bật `TRACE` toàn ứng dụng rồi upload mọi log. Vì JUnit XML cũng có thể chứa `system-out`/`system-err`, việc bảo vệ bí mật áp dụng cho **cả XML**, không chỉ file `build.log`.

Quy định quyền tải artifact, thời hạn giữ, masking secret và bước làm sạch log nên được áp dụng ở CI. Với lỗi cần điều tra sâu, lưu thêm log container/database đã lọc thông tin nhạy cảm, định danh image và checksum/commit để tái hiện chính xác.

## 10. Những tình huống khiến report bị mất hoặc gate báo sai

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý/kiểm chứng |
| --- | --- | --- |
| Job đỏ nhưng artifact rỗng | Compile/dependency lỗi trước JUnit hoặc glob sai | Đọc `build.log`; so đường dẫn report thực tế với glob; phân biệt “chưa chạy test” |
| Console báo test fail nhưng job xanh | `|| true`, `continue-on-error`, `testFailureIgnore`, `ignoreFailures` hoặc pipeline `tee` che mã lỗi | Bỏ cấu hình nuốt lỗi; bật `pipefail`; kiểm tra exit code khác 0 |
| Không thấy `InventoryEventsIT` | Chỉ chạy Maven `test`, chưa bind Failsafe vào `verify` hoặc Gradle chưa nối `integrationTest` vào `check` | Đếm test đã thực thi; chạy lifecycle/task đúng; kiểm tra XML của IT |
| Chỉ còn report của module cuối | Artifact upload ghi đè hoặc path chỉ trỏ root `target/` | Dùng glob đệ quy; định danh artifact theo job/matrix |
| XML có lỗi nhưng không đủ thông tin | Stack trace bị cắt, logs thiếu correlation ID | Bật stack trace đầy đủ; bổ sung logging có chọn lọc cho test |
| Artifact upload thành công dù test fail | Đây là hành vi đúng của bước thu thập | Kiểm tra job/conclusion vẫn fail và PR không qua gate |
| JUnit XML xuất hiện nhưng report UI không thấy | CI chỉ lưu file ở `paths`, chưa cấu hình publisher JUnit | Thêm `reports:junit` trên GitLab hoặc bộ hiển thị test phù hợp nền tảng |

Không dùng report từ run khác làm bằng chứng cho commit đang review. Gắn artifact với commit SHA, run ID, attempt và task/test name; đặc biệt quan trọng khi re-run riêng các job fail.

## 11. Thử nghiệm quality gate bằng lỗi có chủ đích

Trước khi đưa gate vào nhánh được bảo vệ, kiểm tra trong nhánh thử nghiệm hoặc pull request tạm, rồi hoàn tác thay đổi gây lỗi:

1. **Vi phạm kiến trúc:** tạo một phụ thuộc module bị `verify()` từ chối. Kỳ vọng `ModulithArchitectureTest` fail, XML chứa test case và thông tin vi phạm; job đỏ; artifact vẫn tải được.
2. **Assertion/event thất bại:** làm một test `@ApplicationModuleTest` hoặc `InventoryEventsIT` không đạt. Kỳ vọng Surefire/Failsafe (hoặc đúng Gradle task) sinh report; tên test và stack trace xuất hiện.
3. **Lỗi trước test:** tạo lỗi biên dịch trên nhánh thử nghiệm. Kỳ vọng job đỏ, **không bắt buộc có XML**, nhưng log build vẫn được lưu và chỉ ra nguyên nhân.
4. **Khôi phục:** hoàn tác lỗi, chạy lại cùng command. Kỳ vọng job xanh, số test được chạy hợp lý, không có `failure`/`error` và artifact vẫn phản ánh đúng run mới.

Một quality gate được xem là vận hành đúng khi **test thất bại làm build thất bại, bằng chứng vẫn truy cập được, và người khác có thể dùng chính commit cùng lệnh chạy đã ghi để tái hiện**. Kiểm tra này nên được thực hiện lại khi đổi phiên bản JUnit, Maven/Gradle plugin, Spring Modulith hoặc cấu hình pipeline, vì tên task và vị trí report có thể thay đổi.
