# Chạy lại flaky test có giới hạn và có cảnh báo

## 1. Mục tiêu của retry trong CI: thu thập bằng chứng, không che lỗi

Một bài `@ApplicationModuleTest` của Spring Modulith có thể thất bại không ổn định vì listener chạy bất đồng bộ, `ApplicationContext` được dùng chung, Testcontainers khởi động chậm, dữ liệu test chưa được dọn hoặc một assertion dựa vào `Thread.sleep(...)`. Khi nhấn **Re-run failed jobs**, bài test đôi khi xanh. Tuy nhiên, “xanh sau chạy lại” không chứng minh hợp đồng kiến trúc hoặc hành vi vẫn đúng: có thể chỉ là một race condition chưa được sửa.

Chủ đề của bài thuộc chương **CI và quality gate** trong `SPRING_MODULITH_VERIFICATION_TESTING`. Mục tiêu xuyên suốt học phần là kiểm chứng ranh giới ứng dụng Spring Modulith bằng `ApplicationModules`, kiểm thử `@ApplicationModuleTest`, sự kiện, cơ sở dữ liệu và tích hợp; ở đây ta tập trung riêng vào **cách tổ chức retry có giới hạn và cảnh báo trong CI** để các gate đó không bị làm yếu.

Một chiến lược chạy lại đúng có hai chức năng:

1. **Chẩn đoán:** xác định bài test có thể đổi kết quả khi chạy lại trong môi trường gần như giống nhau.
2. **Bảo vệ gate:** không biến một lỗi lúc chạy gốc thành “pass sạch” chỉ vì một lần chạy lại thành công.

Phải tách bốn trạng thái:

| Kết quả | Cách gọi trong bài | Ý nghĩa | Quyết định CI |
| --- | --- | --- | --- |
| PASS ngay lượt đầu | `CLEAN` | Không có lỗi được quan sát trong lượt này | PASS |
| FAIL trước, PASS sau retry | `PASSED_AFTER_RETRY` | **Có dấu hiệu bất ổn**; chưa xác định nguyên nhân là test hay hạ tầng | FAIL gate + cảnh báo |
| FAIL ở mọi attempt | `FAILED_AFTER_LIMIT` | Lỗi chưa phục hồi trong ngân sách; có thể deterministic hoặc flaky dai dẳng | FAIL gate + cảnh báo |
| Hỏng trước khi thực thi test | `INFRA_FAILURE` | Ví dụ checkout, compile, resolve dependency, runner/storage lỗi | FAIL gate; điều tra hạ tầng, không tự gắn nhãn test flaky |

**Không suy luận quá mức:** một test xanh ngay lượt đầu vẫn có thể flaky hiếm gặp; FAIL cả ba lần cũng không chứng minh lỗi deterministic. Chỉ có chuỗi FAIL→PASS là bằng chứng quan sát được về **kết quả không ổn định trong cùng đợt kiểm thử**, chưa đủ xác định nguồn gốc.

## 2. Quy ước retry budget và điều kiện được phép chạy lại

Cho pipeline minh họa một ngân sách tường minh:

| Tham số | Chính sách ví dụ |
| --- | --- |
| Lượt chạy gốc | 1 |
| Retry tối đa | 2 |
| Tổng attempts tối đa | **3** |
| Phạm vi | Test suite đã được chọn làm gate; không tự retry deployment/production side effects |
| Giới hạn thời gian job | 30 phút, bao gồm cả attempts |
| Khi PASS sau retry | Ghi `PASSED_AFTER_RETRY`, **gate vẫn FAIL**, cảnh báo owner |
| Khi cả 3 attempts FAIL | Ghi `FAILED_AFTER_LIMIT`, **gate FAIL**, yêu cầu điều tra |
| Bằng chứng | Log, exit code và JUnit XML **riêng cho từng attempt** |
| Cách khắc phục | Fix race/isolation/timing; gỡ retry hoặc giảm phạm vi khi đủ dữ liệu |

Số **2 retry** là một lựa chọn ví dụ để giới hạn chi phí; không phải một default bắt buộc của Spring Modulith, Gradle hay GitHub Actions. Cần điều chỉnh dựa vào thời gian suite và mức độ nghiêm trọng.

### Những điều không được retry mù

- **Compile error**, architectural violation từ `ApplicationModules.verify()`, schema không tương thích: chạy lại không làm code tự sửa.
- **Input hoặc fixture sai chắc chắn**: dữ liệu test sẽ vẫn sai; phải sửa test/fixture.
- **Lệnh sinh side effect trên môi trường shared/production**: retry có thể gửi email, tạo payment hoặc sửa dữ liệu nhiều lần.
- **Integration test không có cơ chế reset/cleanup**: lượt sau không còn cùng precondition, nên kết quả không so sánh được.
- **Job dùng nhiều tầng retry**: GitHub Actions retry job, Gradle Test Retry plugin và HTTP client cùng lặp có thể nhân attempts.

**Chọn một owner cho retry ở CI.** Workflow ở phần 6 tự chạy lại toàn bộ task `test` tối đa 2 lần. Nếu đã dùng plugin Gradle retry từng failed test, phải tính tổng ngân sách thực, tránh cấu hình cả hai vô tình. Khi suite rất lớn, plugin retry **chỉ failed tests** là hướng tối ưu hơn; dù dùng công cụ nào, nguyên tắc `fail on passed after retry` và lưu bằng chứng vẫn giữ nguyên.

## 3. Định vị lỗi flaky theo Spring Modulith, không trộn với lỗi hợp đồng

Mỗi nhóm test có một mức độ quyết định khác nhau:

| Nhóm | Ví dụ kiểm chứng | Dấu hiệu flaky thường gặp | Cách xử lý trước khi retry |
| --- | --- | --- | --- |
| Architecture | `ApplicationModules.of(...).verify()` | Hiếm khi là race; lỗi thường ổn định | Không cần policy retry riêng; sửa dependency |
| Module behavior | `@ApplicationModuleTest` + `PublishedEvents` | Bean override/test state hoặc context cache nhiễm | Cô lập state, xác nhận mock reset/context |
| Async event | `@ApplicationModuleListener`, `@TransactionalEventListener` | Assertion chạy trước listener hoặc trước commit | Chờ điều kiện có giới hạn, commit thật |
| JPA | Repository, `@Transactional`, flush/commit | Dữ liệu rò giữa test, rollback giả định sai | Fixture per test, transaction boundary rõ |
| Testcontainers | PostgreSQL/Kafka | Port/lifecycle, container chưa sẵn sàng, startup timeout | Đợi readiness đúng, lifecycle nhất quán |
| External adapter | Kafka/HTTP | Broker ack hoặc response đến trễ | Kiểm tra kết quả/ack, timeout và isolation |
| Parallel tests | Shared key/clock/port | Hai test đụng vào cùng state | Namespace test data, tách fixture hoặc giới hạn song song |

### Phân biệt lỗi thực với race của test

Nếu `OrderPlaced` phải được **publish đồng bộ trong module**, nên assert `PublishedEvents` ngay trong module test. Nếu contract là **listener bên ngoài sẽ xử lý hậu commit**, phải kiểm tra ở một integration test có transaction, listener và storage thích hợp. Việc đưa tất cả vào một test rồi dùng `sleep(100)` rất dễ tạo flaky giả.

Trước khi dán nhãn một lỗi “flaky”, lưu: test class/method, stack trace, JUnit XML, attempt index, runner image, Java/Gradle version, profile, test seed nếu có, container logs và thời điểm commit/ack. Thiếu bằng chứng thì retry chỉ tạo thêm nhiễu.

## 4. Ví dụ Java/JUnit: kiểm chứng publication ổn định, không sleep

Đây là ví dụ module `orders` chỉ chịu trách nhiệm công bố một domain event. Nó **không** cam kết listener async hoặc Kafka đã nhận message.

```java
// src/main/java/com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

public record OrderPlaced(String orderId) {
}
```

```java
// src/main/java/com/example/shop/orders/PlaceOrderService.java
package com.example.shop.orders;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class PlaceOrderService {

    private final ApplicationEventPublisher events;

    public PlaceOrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void place(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                "orderId must not be blank");
        }

        events.publishEvent(new OrderPlaced(orderId));
    }
}
```

Một test **không phụ thuộc timing**:

```java
// src/test/java/com/example/shop/orders/PlaceOrderModuleTest.java
package com.example.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest
class PlaceOrderModuleTest {

    @Autowired
    PlaceOrderService orders;

    @Test
    void publishesExactEvent(PublishedEvents events) {
        orders.place("ORD-101");

        assertThat(events.ofType(OrderPlaced.class))
            .singleElement()
            .satisfies(e ->
                assertThat(e.orderId())
                    .isEqualTo("ORD-101"));
    }

    @Test
    void invalidInputDoesNotPublish(PublishedEvents events) {
        assertThatThrownBy(() -> orders.place(""))
            .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.ofType(OrderPlaced.class))
            .isEmpty();
    }
}
```

**Tại sao không cần retry test này để “đợi event”?** `PublishedEvents` quan sát các sự kiện được công bố trong Spring context. Vì `PlaceOrderService.place` gọi `publishEvent` đồng bộ trong test này, assertion xác minh ngay sự kiện đã phát, đúng với hợp đồng đang kiểm. Nếu test bỗng flaky, hãy điều tra context/test state; không thêm `Thread.sleep(...)` để che lỗi.

### Phản ví dụ: assertion sai tầng

```java
// Anti-pattern trong test có listener xử lý async.
orders.place("ORD-101");
Thread.sleep(100);
assertThat(notificationRepository.count()).isEqualTo(1);
```

Đoạn minh họa này sai ở ba điểm:

1. **100 ms không phải cam kết** listener sẽ xử lý xong trên runner CI.
2. `notificationRepository.count()` có thể bị ảnh hưởng bởi record của test trước.
3. `orders.place(...)` trong ví dụ trên không có transaction; nếu listener dùng `AFTER_COMMIT`, nó có thể không chạy như mong đợi.

Đừng tăng sleep lên 1 hoặc 5 giây rồi xem như đã sửa flake; vừa chậm vừa không chứng minh điều kiện đúng.

## 5. Với listener hậu commit: chờ trạng thái đúng và cô lập transaction

Nếu hợp đồng thực sự yêu cầu module `notifications` xử lý `OrderPlaced` **sau commit**, hãy tạo một integration test khác:

```java
// Khung tích hợp: cần @SpringBootTest, TransactionTemplate,
// publisher, notificationRepository và Awaitility được cấu hình.
@Test
void storesNotificationAfterCommittedEvent() {
    transactions.executeWithoutResult(status ->
        publisher.publishEvent(new OrderPlaced("ORD-IT-101")));

    await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
            assertThat(notificationRepository
                .findAllByOrderId("ORD-IT-101"))
                .hasSize(1));
}
```

**Đây là fragment, không phải test chạy độc lập:** `transactions` là `TransactionTemplate` với transaction manager phù hợp; `publisher` là `ApplicationEventPublisher`; `notificationRepository` thuộc một implementation thật; `await()` từ Awaitility. Context cần listener production, persistence và các dependencies tương thích. Test method/class **không được có Spring Test-managed `@Transactional` bao ngoài** khi ta muốn `TransactionTemplate` thực sự commit, trừ khi đã chủ động dùng transaction propagation/phương pháp khác.

Một test khác phải kiểm tra rollback không tạo side effect. Với transactional listener, việc có event ở `PublishedEvents` trước rollback **không chứng minh listener đã chạy**; hãy quan sát DB/outbound fake sau rollback theo một khoảng thời gian hoặc tín hiệu có giới hạn, và kiểm soát isolation để tránh false positive.

### Quy tắc làm ổn định async test

- Chờ **điều kiện nghiệp vụ** (row, trạng thái completed, message acknowledgement) thay vì ngủ một khoảng cố định.
- Có timeout hữu hạn và thông điệp assertion rõ; `await()` không được chờ vô hạn.
- Dùng ID/namespace riêng cho mỗi test (ví dụ `ORD-IT-101` chỉ khi fixture được dọn/isolated).
- Tránh chạy test có shared database state song song nếu chưa có cách khóa/isolating.
- Bảo đảm transaction nguồn commit/rollback đúng như hợp đồng.
- Nếu có Testcontainers, để readiness check và lifecycle nhất quán; không tự tạo race bằng việc tái sử dụng endpoint của container đã dừng.
- Khi `@ApplicationModuleTest` chỉ nạp module mục tiêu, listener thuộc module khác có thể **không nằm trong context**; dùng integration scope đúng thay vì chờ một listener không tồn tại.

**Kết quả mong muốn:** sửa cách quan sát và fixture để test ổn định. Retry CI vẫn hữu ích để phát hiện hồi quy ngẫu nhiên còn sót, nhưng không thay cho các sửa chữa này.

## 6. GitHub Actions: tối đa hai retry, vẫn fail khi chỉ pass sau retry

Workflow dưới đây cố tình **không dùng plugin retry bổ sung**. Nó chạy `./gradlew test` một lần, nếu thất bại thì thử lại **tối đa hai lần** với cùng mã nguồn và runner; mỗi attempt có log và JUnit XML được lưu riêng. Nó phân loại kết quả, **FAIL gate** cả khi chỉ thành công ở attempt 2/3, rồi phát cảnh báo.

Lưu ý: đây là chiến lược **retry toàn bộ test task**, minh bạch nhưng tốn tài nguyên hơn retry chỉ failed tests. Phù hợp để hiểu policy và cho suite nhỏ; với suite lớn có thể thay bằng Gradle Test Retry plugin được pin version và cấu hình tương đương. Không bật cả hai tầng retry cùng lúc.

```yaml
# Ví dụ nội dung .github/workflows/modulith-test-gate.yml
name: Modulith test quality gate

on:
  pull_request:
  workflow_dispatch:

jobs:
  modulith-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle

      - name: Compile tests (không retry lỗi compile)
        run: ./gradlew --no-daemon testClasses

      - name: Test with bounded rerun (1 + tối đa 2)
        id: tests
        shell: bash
        run: |
          pass_at=0
          mkdir -p "$RUNNER_TEMP/modulith-attempts"

          for attempt in 1 2 3; do
            dir="$RUNNER_TEMP/modulith-attempts/attempt-$attempt"
            mkdir -p "$dir"

            echo "::group::Gradle test attempt $attempt/3"
            if ./gradlew --no-daemon --rerun-tasks test \
                > "$dir/console.log" 2>&1; then
              result=0
            else
              result=$?
            fi

            tail -n 60 "$dir/console.log"
            echo "::endgroup::"

            # Lưu XML trước khi attempt sau ghi đè.
            find . -type f \
              -path '*/build/test-results/test/*.xml' \
              -exec cp --parents {} "$dir/" \;

            printf 'attempt=%s exit_code=%s\n' \
              "$attempt" "$result" \
              > "$dir/outcome.txt"

            if [ "$result" -eq 0 ]; then
              pass_at=$attempt
              break
            fi
          done

          if [ "$pass_at" -eq 1 ]; then
            classification=CLEAN
          elif [ "$pass_at" -gt 1 ]; then
            classification=PASSED_AFTER_RETRY
          else
            classification=FAILED_AFTER_LIMIT
          fi

          echo "classification=$classification" >> "$GITHUB_OUTPUT"
          echo "pass_at=$pass_at" >> "$GITHUB_OUTPUT"

          # Chính sách: pass sau retry vẫn không đủ để merge.
          [ "$classification" = CLEAN ]

      - name: Annotate unstable or failed gate
        if: ${{ always() && steps.tests.outputs.classification != '' && steps.tests.outputs.classification != 'CLEAN' }}
        env:
          CLASSIFICATION: ${{ steps.tests.outputs.classification }}
          PASS_AT: ${{ steps.tests.outputs.pass_at }}
        shell: bash
        run: |
          echo "::warning title=Modulith test instability::$CLASSIFICATION (pass_at=$PASS_AT). See per-attempt artifacts."
          {
            echo "## Modulith test quality gate"
            echo "- Status: **$CLASSIFICATION**"
            echo "- First passing attempt: **$PASS_AT** (0 = none)"
            echo "- Action: investigate the first failure; do not merge."
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Upload all attempt evidence
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: modulith-test-attempts
          path: ${{ runner.temp }}/modulith-attempts/
          if-no-files-found: warn
          retention-days: 7
```

### Giải thích chính xác hành vi

- Lệnh `testClasses` là một gate **không retry**: thiếu class/import/dependency không được khoác nhãn flaky test.
- `--rerun-tasks` ép Gradle thực thi lại test thay vì lấy kết quả task từ cache/up-to-date; lưu ý nó có thể rerun cả các task phụ thuộc và tăng chi phí.
- `pass_at=1` → `CLEAN`, trả exit code 0.
- `pass_at=2` hoặc `3` → `PASSED_AFTER_RETRY`, **step trả exit code 1** mặc dù lượt cuối xanh. Đây là cảnh báo được bảo vệ bằng gate.
- Không lượt nào xanh → `FAILED_AFTER_LIMIT`, exit code 1.
- `if: always()` giúp alert và upload artifacts vẫn chạy sau khi test step thất bại. Điều kiện cảnh báo yêu cầu output `classification` có giá trị để không nhầm checkout/compile failure thành flaky.
- Mỗi attempt có `console.log`, `outcome.txt` và file XML được copy **trước lần rerun tiếp theo**, vì Gradle report path thường bị ghi đè.
- `::warning` là **annotation trên GitHub Actions**, không đồng nghĩa một Slack/PagerDuty alert đã được gửi. Failed required check mới là cơ chế thực tế chặn merge khi repository bật branch protection.

### Các giới hạn triển khai

1. Workflow dành cho runner **Ubuntu/Bash** có `find` và GNU `cp --parents`; không copy nguyên sang PowerShell/Windows.
2. Đường dẫn `build/test-results/test` là mặc định của Gradle task tên `test`; custom task như `integrationTest` phải bổ sung artifact path/command riêng.
3. Nhiều lần chạy lại **không reset môi trường một cách thần kỳ**: nếu tests ghi DB/broker, cần fixtures per attempt hoặc cleanup.
4. Job timeout 30 phút bao gồm compile, 3 lượt test và upload; chọn lại theo thời gian thực tế.
5. Versions của GitHub Actions/Java/Gradle nên được tổ chức pin và cập nhật theo chính sách supply-chain; ví dụ không cam kết đúng mọi repository.
6. Nếu Gradle command thất bại vì compile/task cấu hình trong attempt, `FAILED_AFTER_LIMIT` chỉ nghĩa **test task chưa pass**, không xác định nguyên nhân. Điều tra log/JUnit XML trước khi gắn nhãn flaky.

## 7. Cảnh báo phải phân loại được và có người chịu trách nhiệm

Một retry policy chỉ ghi “Retry 2 times” nhưng không có người nhận tín hiệu sẽ dễ biến thành nợ kỹ thuật. Tối thiểu CI phải thể hiện:

| Trường | Ví dụ | Vì sao cần |
| --- | --- | --- |
| Run/commit | GitHub run URL, SHA | Biết lỗi xuất hiện ở thay đổi nào |
| Test identity | `OrderEventIntegrationTest.afterCommit` | Tìm owner phù hợp |
| Attempt history | FAIL → PASS hoặc FAIL → FAIL → FAIL | Không mất dấu intermittent |
| Classification | `PASSED_AFTER_RETRY` / `FAILED_AFTER_LIMIT` | Phân luồng triage |
| Failure signature | Exception type/message đầu tiên | Phân biệt timing và business regression |
| Environment | JDK/Gradle, profile, DB/broker versions | Tái hiện sự cố |
| Evidence | Console, XML, container logs | Điều tra thay vì đoán |
| Owner/action | Team sở hữu module, issue và hạn sửa | Tránh flake tồn tại mãi |

Workflow phần 6 cung cấp **failed check, annotation, summary và artifacts**. Nếu tổ chức cần gửi đến Slack/Teams/PagerDuty, hãy nối cảnh báo từ workflow đáng tin hoặc CI notification integration theo chính sách bảo mật. Không gửi webhook secret vào pull request từ fork không đáng tin và không log token.

### Cách xử lý từng trạng thái

- **`CLEAN`:** cho gate qua; tiếp tục theo dõi trend vì một lượt xanh không chứng minh không flaky.
- **`PASSED_AFTER_RETRY`:** fail gate, tạo issue hoặc thông báo owner; so sánh log attempt 1 với attempt pass để tìm race/fixture leak.
- **`FAILED_AFTER_LIMIT`:** fail gate, không tự retry lần thứ tư; đọc failure đầu tiên, xác định đây là regression thật, hạ tầng hay flake liên tục.
- **`INFRA_FAILURE`:** nếu checkout/compile/test runner chưa bắt đầu thì dùng cảnh báo kiểu infrastructure; không tự thêm “flaky test” vào thống kê.

**Cảnh báo không chỉ là màu vàng trong log.** Với required CI checks, người review nhìn thấy job không đạt, artifact đầy đủ và chủ thể chịu trách nhiệm xử lý. Không nên để một job cảnh báo nhưng `continue-on-error: true` ở gate chính khiến PR vẫn merge như bình thường.

## 8. Kiểm chứng cơ chế retry và cảnh báo bằng probe có kiểm soát

Đừng chỉ tin workflow vì đã viết YAML. Ta cần kiểm tra **ba nhánh của thuật toán** mà không chờ một test flaky thực xuất hiện ngẫu nhiên.

### 8.1. Nhánh CLEAN

Không bật probe, chạy workflow trên một nhánh sạch:

- `testClasses` PASS;
- Gradle `test` attempt 1 PASS;
- Output `classification=CLEAN` và `pass_at=1`;
- Job PASS, không có annotation instability;
- Artifact attempt 1 chứa `console.log`/`outcome.txt` và JUnit XML nếu có test.

### 8.2. Nhánh PASSED_AFTER_RETRY bằng JUnit probe

Một JUnit 5 test **chỉ chạy khi chủ động bật biến môi trường** có thể cố tình fail một lần rồi pass ở lần sau. Đây là một **test kiểm tra chính sách CI**, tuyệt đối không đưa vào suite thường trực với probe bật.

```java
// src/test/java/com/example/shop/ci/RetryGateProbeTest.java
package com.example.shop.ci;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import static org.junit.jupiter.api.Assertions.fail;

class RetryGateProbeTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "CI_RETRY_PROBE", matches = "true")
    void failsOnceThenPassesOnNextGradleInvocation()
            throws Exception {

        String runnerTemp = System.getenv("RUNNER_TEMP");
        String runId = System.getenv("GITHUB_RUN_ID");

        if (runnerTemp == null || runId == null) {
            fail("Probe requires an isolated GitHub runner");
        }

        Path marker = Path.of(
            runnerTemp,
            "retry-probe-" + runId + ".marker");

        if (Files.notExists(marker)) {
            Files.createFile(marker);
            fail("Intentional first-attempt failure");
        }
    }
}
```

Đây là một probe test **tùy chọn để học và kiểm chứng workflow**, không phải file được tạo trong nhiệm vụ. Test sử dụng `RUNNER_TEMP` nằm ngoài source tree và `GITHUB_RUN_ID` để tránh trộn giữa workflow runs; cùng một job lưu marker qua các Gradle invocations.

Cách thử có kiểm soát trên **nhánh tạm**:

1. Thêm probe test vào test source đúng cấu trúc package.
2. Chỉ tại step `Test with bounded rerun`, đặt environment variable `CI_RETRY_PROBE=true`; đừng bật globally cho mọi pipeline.
3. Đảm bảo marker chưa tồn tại lúc bắt đầu run.
4. Lượt 1 probe fail và tạo marker; lượt 2 pass.
5. Kiểm tra `classification=PASSED_AFTER_RETRY`, `pass_at=2`, job **FAIL**, warning annotation và artifact của cả hai attempts.
6. Xóa probe/flag sau thử nghiệm; không dùng nó để “tạo thống kê flaky” trong CI thật.

**Giới hạn:** probe phản ánh việc rerun Gradle trong **cùng GitHub job** với filesystem tạm còn nguyên. Nó không giả lập race trong listener, broker timeout hoặc flaky do container. Nó chỉ kiểm tra policy/observability.

### 8.3. Nhánh FAILED_AFTER_LIMIT

Trong một nhánh thử nghiệm **không dùng cho merge production**, đổi probe thành `fail("intentional permanent failure")` tại mọi attempt (vẫn opt-in). Kỳ vọng:

- Có đúng ba attempt;
- `classification=FAILED_AFTER_LIMIT`, `pass_at=0`;
- Không có lượt thứ tư;
- CI gate FAIL, annotation/summary xuất hiện;
- Artifact chứa logs/XML tương ứng cả ba lần.

**Tiêu chí pass của chính policy:** branch test cố ý fail được coi là thành công nếu hệ thống cảnh báo và giữ gate đỏ như thiết kế. Không phải “test suite xanh”.

## 9. Giữ bằng chứng, đo xu hướng và sửa nguồn gốc

Khi một test chỉ pass sau retry, điều quan trọng nhất là **failure đầu tiên không bị ghi đè hoặc mất khỏi UI**.

### Hồ sơ cho mỗi lần phát hiện instability

```text
Flaky investigation record
- Test: notifications.OrderEventIntegrationTest#afterCommit
- Commit/run: <SHA và CI run URL>
- Attempts: 1 FAIL, 2 PASS
- First exception: AssertionError: expected notification row
- Event ID / order ID: test-specific identifier
- Transaction: committed? yes/no (dựa trên log)
- Context: module test hay full integration?
- Infra: Testcontainers readiness, broker ack, DB version
- Owner: team notifications
- Hypothesis: listener async xử lý sau assertion
- Fix: await persisted state; isolate fixture
- Verification: N lần chạy độc lập + required CI gate PASS
```

Log và JUnit XML của attempt 1/2 là dữ liệu điều tra; không đưa password, access token hay payload có PII vào artifact. Chính sách retention 7 ngày trong workflow chỉ là ví dụ; chọn theo quy định tổ chức.

### Đo theo test identity, không chỉ theo job

Một dashboard có thể theo dõi:

- `flaky_candidate_count`: số lần xuất hiện FAIL→PASS theo test identity.
- `flaky_rate`: số runs có dấu hiệu bất ổn trên tổng runs test đó được chạy.
- `time_to_fix` và số issue chưa đóng.
- `timeout_count` theo test class/module.
- `test_duration_p95` để nhận diện chờ đợi quá gắt.
- `retry_cpu_minutes` để đo chi phí.
- `quarantined_test_count` và tuổi của từng quarantine.

**Tránh diễn giải sai:** `PASSED_AFTER_RETRY` tính theo toàn test task trong workflow ví dụ, không tự chỉ ra test method nào đã flaky. Để đo theo từng method, cần phân tích JUnit XML/log theo attempt hoặc dùng công cụ test retry có kết quả từng test; đừng tuyên bố có metric per-test khi chưa trích xuất dữ liệu.

### Chính sách quarantine có thời hạn

Nếu một test integration rất nhiễu gây gián đoạn nhiều nhóm, có thể chuyển nó sang lane riêng **với owner, issue và hạn chót**. Nhưng:

- Không xóa test mà không có bằng chứng thay thế cho contract.
- Không `@Disabled` vô thời hạn trên architecture/transaction/idempotency gate quan trọng.
- Nếu một contract có nguy cơ cao bị bỏ khỏi PR lane, vẫn cần một gate bắt buộc trước phát hành.
- Không để `failOnPassedAfterRetry=false` hoặc `continue-on-error` trở thành workaround vĩnh viễn.
- Sau fix, chạy lặp đủ nhiều để quan sát tính ổn định, rồi bỏ quarantine/retry ngoại lệ.

**Mục tiêu dài hạn là giảm flaky tests, không tăng ngân sách retry theo thời gian.**

## 10. Bài tập thực hành và Definition of Done

### Bài tập A — Phân loại kết quả

Một pipeline chạy `./gradlew test` với tổng tối đa ba attempts:

| Attempt 1 | Attempt 2 | Attempt 3 | Classification | Gate |
| --- | --- | --- | --- | --- |
| PASS | Không chạy | Không chạy | `CLEAN` | PASS |
| FAIL | PASS | Không chạy | `PASSED_AFTER_RETRY` | **FAIL** + cảnh báo |
| FAIL | FAIL | PASS | `PASSED_AFTER_RETRY` | **FAIL** + cảnh báo |
| FAIL | FAIL | FAIL | `FAILED_AFTER_LIMIT` | **FAIL** + cảnh báo |

**Câu hỏi:** nếu attempt 1 FAIL do `ApplicationModules.verify()` phát hiện import trái module, có nên coi attempt 2 PASS là “đã sửa kiến trúc”?  
**Đáp:** Không. Cần kiểm tra task/test nào thực sự chạy và lý do bất nhất; dependency graph không tự thay đổi trong cùng commit. Nếu kết quả đổi, investigate test selection, build cache, classpath, parallel execution hoặc hạ tầng. Cảnh báo không được bỏ qua.

### Bài tập B — Chuyển một async flaky test thành deterministic test

Ban đầu:

```java
placeOrder("ORD-17");
Thread.sleep(200);
assertThat(notifications.findAllByOrderId("ORD-17"))
    .hasSize(1);
```

Hãy sửa theo hướng:

1. Xác định listener `AFTER_COMMIT` có thật sự nằm trong context không.
2. Bảo đảm transaction nguồn đã commit.
3. Dùng order/event ID riêng và cleanup state.
4. Đợi **row hoặc trạng thái hoàn thành**, không đợi cố định 200 ms.
5. Đặt timeout hợp lý, thu thập lỗi rõ khi quá hạn.
6. Kiểm tra rollback không tạo notification.
7. Chạy test riêng và chạy cùng suite nhiều lần để phát hiện state leak.

### Bài tập C — Thẩm định quality gate

Giả sử workflow khác thêm:

```yaml
- name: Test
  continue-on-error: true
  run: ./gradlew test
```

**Vì sao không đạt?** Lỗi test có thể bị cho phép bỏ qua, khiến downstream job/branch protection không chặn merge như mong muốn. Nếu thật sự cần “soft failure” ở bước thu thập dữ liệu, phải có **final hard gate** dựa trên classification và kết quả test. Bài workflow ở phần 6 chọn cách đơn giản: step `Test with bounded rerun` trả nonzero cho mọi tình trạng bất ổn hoặc fail.

### Checklist Definition of Done

- [ ] Có giới hạn attempts rõ: một lần gốc + tối đa hai retry.
- [ ] Không có vòng retry vô hạn hoặc nhiều owner retry chồng nhau.
- [ ] PASS sau retry **không** bị xem là PASS sạch.
- [ ] CI fail gate với `PASSED_AFTER_RETRY` và `FAILED_AFTER_LIMIT`.
- [ ] Có annotation/summary cùng owner thực sự được thông báo theo quy trình tổ chức.
- [ ] Log/JUnit XML được giữ riêng theo attempt, kể cả attempt đầu tiên fail.
- [ ] Test async dùng condition wait có timeout, không cố định `Thread.sleep`.
- [ ] `PublishedEvents` chỉ được dùng để chứng minh publication, không suy broker ack.
- [ ] Test transaction có commit/rollback thật khi contract yêu cầu.
- [ ] Testcontainers và fixture có lifecycle/isolation phù hợp khi rerun.
- [ ] Compile/architecture/schema failures không bị âm thầm “chữa” bằng retry.
- [ ] Có run thử `CLEAN`, `PASSED_AFTER_RETRY`, `FAILED_AFTER_LIMIT` và kiểm tra artifact.
- [ ] Retry budget, classification và quarantine policy được review định kỳ; có hướng giảm nợ flaky.

**Ghi nhớ:** retry CI là **cơ chế phát hiện và thu thập bằng chứng về bất ổn**, không phải sửa lỗi. Với Spring Modulith, hãy giữ `ApplicationModules.verify()` và module/event/database contracts như các quality gates thực sự; retry có **giới hạn**, outcome **phân loại rõ** và **cảnh báo không thể bị bỏ qua**. Mục tiêu cuối cùng là test ổn định theo nguyên nhân gốc, để pipeline xanh vì **hợp đồng đúng**, không vì đã thử đủ nhiều lần.
