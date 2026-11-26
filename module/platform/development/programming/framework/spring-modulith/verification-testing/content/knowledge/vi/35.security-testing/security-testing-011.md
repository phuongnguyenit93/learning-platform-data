# Lưu report không chứa dữ liệu nhạy cảm

## 1. Hợp đồng của một security test report an toàn

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, chúng ta kiểm chứng ranh giới ứng dụng Spring Modulith bằng `ApplicationModules` và luật phụ thuộc module; sử dụng `@ApplicationModuleTest`, kiểm thử sự kiện, cơ sở dữ liệu và tích hợp, kết hợp **quality gate CI** để ngăn lỗi phụ thuộc sai và hồi quy. Riêng chương **Security testing**, bài **“Lưu report không chứa dữ liệu nhạy cảm”** xử lý một nguy cơ nằm ngay trong quy trình kiểm thử: **test chạy đúng nhưng report/log/artifact làm lộ thông tin**.

Giả sử bài test phân quyền cho module `billing` cố ý gửi một request có `Authorization: Bearer ...` và email của người dùng giả lập. Khi assertion fail, framework có thể in **actual object**, HTTP request, exception message hoặc raw payload vào JUnit XML. Nếu CI tải toàn bộ `target/` hay `build/` lên làm artifact, dữ liệu đó có thể tồn tại lâu hơn môi trường test và được nhiều người truy cập hơn.

Mục tiêu không phải làm report “ít chi tiết nhất có thể”, mà là **giữ đủ bằng chứng kiểm chứng nhưng không đưa bí mật/PII vào kênh không được phép**.

**Hợp đồng nghiệm thu:**

1. Report vẫn ghi được **check ID, trạng thái PASSED/FAILED, phiên bản định dạng, thời gian hoặc số lượng nếu cần**.
2. Report **không chứa** mật khẩu, bearer token, API key, cookie, dữ liệu cá nhân thật, đường dẫn URL có query bí mật, request/response body hoặc thông tin từ exception chưa được phân loại.
3. Trường được đưa ra report phải nằm trong **allowlist**, có nguồn và miền giá trị kiểm soát được. Không serialize cả object rồi mới hy vọng regex che hết.
4. Cả kết quả **PASSED và FAILED** đều đi qua cùng một chính sách an toàn; đặc biệt failure path không được đổ nguyên `Throwable#getMessage()` vào báo cáo.
5. Chỉ **file an toàn đã được xác minh** được phép upload lên CI; test runner stdout, JUnit XML và file phụ khác phải được kiểm soát riêng.
6. Khi không tạo được report an toàn hoặc bước kiểm tra phát hiện rò rỉ, **quality gate phải fail**, không tự động bỏ qua.

Phạm vi bài này là **test report, report artifact và các bề mặt phát sinh trong quá trình kiểm thử**, không viết lại phần căn bản về xác thực, phân quyền hay Testcontainers.

## 2. Kiểm kê các điểm dữ liệu có thể chảy vào report

Không chỉ file do nhóm tự tạo mới được coi là “report”. CI và test tooling thường sinh thêm nhiều bản sao của thông tin chạy test.

| Bề mặt | Dữ liệu có thể bị thu thập | Nguy cơ điển hình | Quy tắc |
| --- | --- | --- | --- |
| **JUnit XML** | Test name, failure message, stack trace, system-out, system-err | Assertion in toàn bộ token hoặc JSON chứa PII | Kiểm soát nguồn assertion/log; rà XML riêng |
| **Gradle HTML/XML reports** | Tên test, exception, console output theo tool/config | Tên `@ParameterizedTest` chứa email; actual object bị dump | Tên test cố định, không hiển thị object nhạy cảm |
| **Maven Surefire/Failsafe output** | XML, text, stdout/stderr tùy plugin | `redirectTestOutputToFile` chỉ chuyển nơi lưu dữ liệu | Không coi redirect là redact |
| **SLF4J/Logback test logs** | Messages, MDC, exception, request details | `log.error("{}", exception)` ghi URL chứa credential | Log error code/enum an toàn |
| **MockMvc/HTTP client** | URI, header, cookie, body | `andDo(print())` hoặc HTTP wire logs ghi `Authorization` | Chỉ bật log có kiểm soát cho dữ liệu synthetic |
| **Testcontainers** | Container logs, env, stack trace khởi động | DB URI/password hoặc payload in từ service | Không upload raw `getLogs()` bừa bãi |
| **Database/broker diagnostics** | SQL bind parameters, topic/key/payload, outbox rows | Email, token, tenant ID trong query/log | Tách telemetry nội bộ có quyền truy cập riêng |
| **Snapshot/screenshot/attachment** | HTML, response JSON, UI state, file tạm | PII còn trong snapshot/screenshot | Chỉ xuất bằng chứng đã được làm sạch |
| **CI artifact upload** | File/folder glob | Upload `target/**`, `build/**`, coverage/temp dumps | Publish **allowlist đường dẫn hẹp** |
| **Tên file, link và metadata** | Filename, URL, job parameters | Customer email trong tên file; token ở query URL | Tên cố định hoặc mã test synthetic |

Theo OWASP Logging Cheat Sheet, access token, session identifier, mật khẩu, key và nhiều dữ liệu cá nhân **không nên được ghi trực tiếp**. Chúng cần bị loại bỏ, làm mờ hoặc xử lý theo chính sách trước khi đi vào log. Trong ngữ cảnh test report, cách ít rủi ro nhất là **không đưa chúng vào bản ghi báo cáo ngay từ đầu**.

### Phân loại dữ liệu trước khi xuất

| Loại | Ví dụ | Quyết định mặc định |
| --- | --- | --- |
| **Secret/credential** | Password, API key, access/refresh token, cookie, private key, DB URL có credential | **Không xuất** |
| **Personal/tenant data** | Email, số điện thoại, địa chỉ, tên thật, mã khách hàng có thể tra cứu | **Không xuất mặc định**; nếu cần xử lý theo chính sách pháp lý |
| **Raw request/response** | Headers, query string, JSON payload, body lỗi | **Không xuất**; nội dung thường trộn bí mật |
| **Exception detail** | `Throwable#getMessage()`, SQL với bind values, URL của client | **Không sao chép nguyên văn** |
| **Operational identifier** | Correlation/request ID, test case ID | Chỉ xuất khi ID **synthetic, vô nghĩa ngoài test** và được cho phép |
| **Metadata allowlist** | Enum `CHECK_ID`, `PASSED/FAILED`, schema version, duration bucket | Có thể xuất theo chính sách |

Một UUID không tự nhiên là “không nhạy cảm”: nếu đó là ID hóa đơn/khách hàng thật, nó có thể dùng để liên kết tới dữ liệu cá nhân. Ví dụ phía dưới chỉ dùng **ID và canary sinh trong test**, không lấy từ production.

## 3. Thiết kế report theo allowlist trước khi viết file

Một schema **an toàn theo thiết kế** có miền giá trị nhỏ:

```text
format_version=1
check=INVOICE_OWNER_GUARD
outcome=FAILED
```

Các trường `format_version`, `check`, `outcome` là **hằng số và enum của ứng dụng test**, không phụ thuộc user input. Không có `principal.email`, `Authorization`, path URL, payload hay `error.message`.

### Tại sao allowlist tốt hơn “ghi trước rồi redact”?

Ví dụ **không nên dùng**:

```java
// Phản ví dụ: toString() có thể bao gồm token/email/body.
String raw = "result=" + observation;
String masked = raw.replaceAll(
        "(?i)Bearer\\s+\\S+", "Bearer [REDACTED]");
Files.writeString(reportPath, masked);
```

Vấn đề:

- Có thể có token ở **query parameter**, cookie, JSON nested, URL-encoded text hoặc stack trace, không khớp regex.
- Raw string đã được tạo và có thể vô tình đi vào log/debug trước bước redact.
- Regex có thể che một kiểu secret nhưng bỏ sót định dạng mới; đổi serializer có thể làm rò dữ liệu.
- `record.toString()` và Lombok `@Data` có thể tự in toàn bộ fields, kể cả trường mới thêm.
- Sau khi report đã được upload, redact lại bản local **không thu hồi** mọi bản sao.

**Quy tắc:** dựng bản xuất từ một **projection độc lập** chỉ dùng field được cho phép. Dùng scanner/redaction pattern như **lớp phòng thủ thứ hai**, không phải cơ chế chính.

### Schema hữu hạn và có thể kiểm chứng

| Trường | Kiểu | Nguồn | Cho phép? |
| --- | --- | --- | --- |
| `format_version` | Hằng số `1` | Report writer | Có |
| `check` | Enum `SecurityCheckCode` | Test/quality gate | Có |
| `outcome` | Enum `CheckOutcome` | Kết quả được xác minh | Có |
| `duration_bucket` | Enum `FAST/MEDIUM/SLOW`, nếu cần | Timer đã lượng hóa | Tùy chính sách |
| `actor_email` | String không giới hạn | Request/fixture | Không |
| `authorization` | String header | SecurityContext/HTTP | Không |
| `error_message` | String không giới hạn | Throwable/log | Không |
| `request_uri` | String, có thể chứa query | HTTP | Không |

Khi cần điều tra sâu một failure, hãy dùng **kênh diagnostic bảo mật riêng** có phân quyền, thời hạn lưu và quy trình phê duyệt, thay vì đẩy raw error sang report có phạm vi truy cập rộng.

## 4. Java implementation: chỉ ghi enum an toàn xuống file

Ví dụ giả định module `com.acme.securityreport` có một thành phần Spring chịu trách nhiệm tạo **report artifact** sau khi một security test hoàn tất. Các trường nhạy cảm tồn tại trong observation **chỉ để test được quy tắc loại trừ**; production nên giới hạn việc giữ raw credentials ngay từ nguồn.

### 4.1. Contract kiểm tra

`src/main/java/com/acme/securityreport/SecurityCheckCode.java`:

```java
package com.acme.securityreport;

public enum SecurityCheckCode {
    REPORT_FIELD_ALLOWLIST,
    INVOICE_OWNER_GUARD,
    MODULE_DEPENDENCY_RULES
}
```

`src/main/java/com/acme/securityreport/CheckOutcome.java`:

```java
package com.acme.securityreport;

public enum CheckOutcome {
    PASSED,
    FAILED
}
```

`src/main/java/com/acme/securityreport/SecurityCheckObservation.java`:

```java
package com.acme.securityreport;

import java.util.Objects;

public record SecurityCheckObservation(
        SecurityCheckCode check,
        CheckOutcome outcome,
        String actorEmail,
        String authorizationHeader,
        String requestUrl,
        String rawFailureMessage) {

    public SecurityCheckObservation {
        Objects.requireNonNull(check, "check");
        Objects.requireNonNull(outcome, "outcome");
    }

    @Override
    public String toString() {
        // Hạn chế một đường rò phổ biến khi object bị log nhầm.
        // Không thay thế cho allowlist và không an toàn nếu
        // framework serialize các fields bằng reflection.
        return "SecurityCheckObservation[redacted]";
    }
}
```

**Không log `SecurityCheckObservation` hoặc dùng reflection serializer trên nó.** `toString()` đã được override để tránh một đường rò, nhưng các fields vẫn chứa dữ liệu nhạy cảm trong memory. Với production, tốt hơn là tạo report từ **object đã được giới hạn field ngay tại nguồn**, không truyền raw token đi qua report subsystem.

### 4.2. Writer chỉ đọc các enum được phép

`src/main/java/com/acme/securityreport/SafeSecurityReportWriter.java`:

```java
package com.acme.securityreport;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Objects;

import org.springframework.stereotype.Component;

@Component
public class SafeSecurityReportWriter {

    public Path save(
            SecurityCheckObservation observation,
            Path trustedReportDirectory) throws IOException {

        Objects.requireNonNull(observation, "observation");
        Objects.requireNonNull(trustedReportDirectory,
                "trustedReportDirectory");

        // Tên file cố định, không xây từ email, URL hoặc tenant ID.
        Path reportPath = trustedReportDirectory
                .resolve("security-summary.txt");

        String safeText =
                "format_version=1\n"
                + "check=" + observation.check().name() + "\n"
                + "outcome=" + observation.outcome().name() + "\n";

        Files.createDirectories(trustedReportDirectory);
        Files.writeString(
                reportPath,
                safeText,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);

        return reportPath;
    }
}
```

**Bằng chứng trong code:** writer chỉ đọc `check()` và `outcome()`; không đọc `actorEmail()`, `authorizationHeader()`, `requestUrl()` hay `rawFailureMessage()`. Do đó một token mới, số điện thoại hay full URL thêm vào observation sẽ **không tự xuất hiện trong report** nếu không ai sửa allowlist.

**Điều kiện vận hành quan trọng:**

- `trustedReportDirectory` phải là đường dẫn **do test runner/CI quản lý**, không lấy trực tiếp từ input của người dùng.
- File cố định chỉ nên có **một writer** trong report-export job. Nếu nhiều tests/threads cùng ghi một file, phải có aggregator/locking hoặc file an toàn theo test ID; tránh race và overwrite kết quả.
- `TRUNCATE_EXISTING` giúp ghi bản mới nhưng **không** đảm bảo ghi atomic; khi cần artifact integrity, hãy ghi vào staging cùng filesystem rồi move có kiểm tra.
- Hệ thống file và artifact store vẫn cần ACL, retention và encryption policy theo môi trường. File “an toàn về nội dung” không thay thế quản trị quyền.
- Khi mở rộng schema, chỉ thêm field **có định nghĩa miền giá trị** và test chứng minh không chứa secret.

## 5. JUnit + `@ApplicationModuleTest`: readback file thật ở cả PASSED và FAILED

Đây là phép kiểm **có thể thực hành**: tạo canary **hoàn toàn giả lập**, lưu file bằng Spring bean thật, đọc lại bytes và xác minh cả hai trạng thái outcome **không chứa dữ liệu cấm**. Không cần PostgreSQL, Kafka hay Docker, vì claim đang kiểm tra là **chính sách report writer**.

`src/test/java/com/acme/securityreport/SafeSecurityReportModuleTests.java`:

```java
package com.acme.securityreport;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class SafeSecurityReportModuleTests {

    @Autowired SafeSecurityReportWriter writer;

    @ParameterizedTest(name = "outcome={0}")
    @EnumSource(CheckOutcome.class)
    void savedReportContainsOnlyAllowlistedFields(
            CheckOutcome outcome,
            @TempDir Path isolatedDirectory) throws Exception {

        // Canary tổng hợp, KHÔNG bao giờ dùng token/email production.
        String canary =
                "TEST_ONLY_CANARY_" + UUID.randomUUID();

        SecurityCheckObservation observation =
                new SecurityCheckObservation(
                        SecurityCheckCode.REPORT_FIELD_ALLOWLIST,
                        outcome,
                        "synthetic+" + canary + "@example.invalid",
                        "Bearer " + canary,
                        "https://example.invalid/invoices?"
                                + "access_token=" + canary,
                        "Synthetic failure contains " + canary);

        Path file = writer.save(observation, isolatedDirectory);
        String saved = Files.readString(
                file, StandardCharsets.UTF_8);

        String expected = "format_version=1\n"
                + "check=REPORT_FIELD_ALLOWLIST\n"
                + "outcome=" + outcome.name() + "\n";

        // Boolean assertions: failure output không in raw
        // report hay secret làm actual/expected value.
        assertThat(saved.equals(expected))
                .as("report fields must match the strict allowlist")
                .isTrue();

        assertThat(saved.contains(canary))
                .as("synthetic canary must never reach report")
                .isFalse();

        assertThat(saved.contains("Bearer "))
                .as("Authorization header must be omitted")
                .isFalse();

        assertThat(saved.contains("access_token="))
                .as("request query secret must be omitted")
                .isFalse();

        assertThat(Files.isRegularFile(file)).isTrue();
    }
}
```

### Vì sao đây là một phép kiểm có ý nghĩa?

1. Test chạy **Spring bean thật** `SafeSecurityReportWriter` trong phạm vi application module.
2. `@TempDir` cấp **thư mục riêng** cho từng invocation, không làm rơi file vào artifact CI mặc định.
3. `@EnumSource` chạy với cả `PASSED` và `FAILED`. Chú ý: `FAILED` ở đây là **giá trị metadata của observation**, không có nghĩa JUnit test cố ý thất bại.
4. Input chứa email, bearer header, URI/query và raw failure message **synthetic**.
5. Test đọc lại **file đã lưu**, không chỉ kiểm tra chuỗi trước khi ghi.
6. Assertion dùng **boolean** sau khi so sánh, không đưa toàn bộ nội dung `saved` vào failure message.

**Không viết**:

```java
// Anti-pattern trong test bảo mật report:
// Khi fail, AssertJ có thể in actual String chứa bí mật.
assertThat(saved).isEqualTo(expected);
assertThat(saved).doesNotContain(observation.authorizationHeader());
```

Nếu writer bị sửa lỗi và vô tình ghi raw bearer, assertion thứ hai có thể in **actual report** hoặc phần dữ liệu cấm vào JUnit XML/console. Dùng dạng `assertThat(saved.contains(canary)).isFalse()` để báo lỗi **bằng tín hiệu boolean**, và dùng canary **giả**.

**Negative control an toàn:** trên một branch thử nghiệm, cho writer **tạm thêm** `observation.authorizationHeader()` vào file; test phải FAIL, nhưng chỉ dữ liệu canary synthetic được dùng. Hoàn nguyên code ngay sau phép kiểm. Không dùng token thật để kiểm chứng chức năng redaction.

## 6. Giữ JUnit failures, logs và test names không mang secret

Kể cả custom report ở mục 4 an toàn, **report của JUnit/Surefire/Gradle vẫn có thể rò dữ liệu** nếu test hoặc framework in raw input ở chỗ khác.

### 6.1. Assertion message là một phần của security surface

So sánh:

```java
// Yếu về tính riêng tư nếu response/toString() chứa token.
assertThat(response).isEqualTo(expectedResponse);

// An toàn hơn khi điều cần chứng minh là một trạng thái:
boolean denied = response.statusCode() == 403;

assertThat(denied)
        .as("unauthorized invoice access must be denied")
        .isTrue();
```

`response` ở đây là object HTTP response **minh họa** của ứng dụng. Đoạn thứ hai không in raw body trong assertion failure, nhưng **không tự dọn** logs mà HTTP client hoặc server đã ghi trước đó.

Đối với exception:

```java
// Anti-pattern: exception.getMessage() có thể mang URL/token.
logger.warn("Verification failed: {}", exception.getMessage());

// Phù hợp hơn khi đã phân loại lỗi:
logger.warn("security_check={} outcome={} error_code={}",
        SecurityCheckCode.INVOICE_OWNER_GUARD,
        CheckOutcome.FAILED,
        "ACCESS_DENIED");
```

`logger` là SLF4J logger giả định của ứng dụng; code trên là minh họa policy chứ không phải class độc lập. **Không ghép raw Throwable vào logging overload** nếu exception message hoặc stack trace có thể chứa dữ liệu bí mật. Với nguyên nhân cần điều tra sâu, ghi vào kênh diagnostic bảo mật theo chính sách riêng.

### 6.2. JUnit `TestReporter` không phải vùng lưu “riêng tư”

JUnit 5 hỗ trợ phát report entries:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestReporter;

class SafeReportingEntryTests {

    @Test
    void publishesOnlyKnownSafeValues(TestReporter reporter) {
        reporter.publishEntry(
                "security_check", "INVOICE_OWNER_GUARD");
        reporter.publishEntry(
                "outcome", "PASSED");
    }
}
```

Tùy test engine và reporter, những entries có thể xuất hiện trong console/XML/reporting output. Vì thế **chỉ publish các giá trị allowlisted**. Không dùng:

```java
// Không publish email/token/full exception message:
reporter.publishEntry("request", rawHttpRequest);
```

`rawHttpRequest` chỉ là biến minh họa; đây là anti-pattern, không phải code đầy đủ.

### 6.3. Test names và parameterized display names cũng là dữ liệu xuất bản

```java
// Tránh biến email/token thành display name của JUnit report:
@ParameterizedTest(name = "user={0}")
@ValueSource(strings = {"synthetic-alice@example.invalid"})
void authorizationCase(String userName) {
    // ...
}
```

Ví dụ trên dùng dữ liệu giả nên không rò dữ liệu thật, nhưng nếu thay source bằng dữ liệu production hoặc một bearer token, tên test có thể xuất hiện ở **CI dashboard, XML, notifications**.

Tốt hơn: dùng tên **role/scenario code**, không chứa email, account ID hay customer reference:

```java
@ParameterizedTest(name = "role-case={0}")
@EnumSource(RoleCase.class)
void authorizationCase(RoleCase roleCase) {
    // ...
}
```

`RoleCase` là enum do test định nghĩa, ví dụ `OWNER_ALLOWED`, `OTHER_OWNER_DENIED`. Đừng in trực tiếp object người dùng hoặc `@ArgumentsSource` chứa PII.

### 6.4. Không dùng report “ẩn lỗi” thay cho test đúng

Không đặt `showExceptions=false` rồi kết luận đã hết rò dữ liệu. Giảm log trên console chỉ **thay cách hiển thị**, không chắc đã xóa failure detail khỏi XML/HTML và artifact. Test vẫn phải **fail thực** khi policy sai; an toàn là không đưa raw secret vào lỗi ngay từ nguồn.

## 7. Spring Modulith, HTTP và Testcontainers: những đường rò đặc thù

Một module test có thể có nhiều nền tảng quan sát: Spring SecurityContext, database, event publication registry, Kafka/RabbitMQ và container logs.

### 7.1. `@ApplicationModuleTest` và `Scenario`

Khi kiểm tra `OrderPaid(id)` làm module shipping phát event/ghi DB, nên quan sát **boolean/sanitized state** theo ID synthetic:

```java
// Đoạn minh họa bên trong @ApplicationModuleTest
// có Scenario, repository và event contract thực của ứng dụng:
scenario.publish(new OrderPaid(orderId))
        .andWaitAtMost(Duration.ofSeconds(8))
        .forStateChange(
                () -> shippingRepository.statusOf(orderId),
                status -> status.filter("READY"::equals)
                        .isPresent())
        .andVerify(status ->
                assertThat(status.isPresent())
                        .as("shipment readiness should be committed")
                        .isTrue());
```

`OrderPaid`, `shippingRepository` và `Scenario` là những thành phần được định nghĩa ở dự án; đoạn chỉ minh họa **cách tránh dump entity có trường nhạy cảm**, không phải bài test hoàn chỉnh. Với dữ liệu đã commit, cần cleanup theo `orderId`; không dùng `@Transactional` test rollback để mặc định dọn transaction riêng của `@ApplicationModuleListener`.

**Tránh**:

```java
// Không làm với entity có ownerEmail, paymentInfo hoặc token:
assertThat(actualShipmentEntity).isEqualTo(expectedShipmentEntity);
logger.info("event={}", fullDomainEvent);
```

Nếu assertion fail, `actualShipmentEntity.toString()` hoặc record auto-`toString()` có thể in nội dung nhạy cảm.

### 7.2. HTTP security tests: tránh in header/body

Một số công cụ có thể in request/response rất dễ dàng:

```java
// Anti-pattern khi có Authorization/cookie/PII:
mvc.perform(request).andDo(print());
```

Trong đó `mvc`, `request` và `print()` thuộc ngữ cảnh MockMvc. `andDo(print())` hữu ích khi debug request **synthetic không nhạy cảm**, nhưng không nên để mặc định trong security suite có headers thật. Cũng cần rà HTTP client logging, RestAssured log-all và wiretap.

Phép kiểm HTTP 401/403 thường chỉ cần **status code**:

```java
mvc.perform(get("/api/invoices/{id}", syntheticInvoiceId))
        .andExpect(status().isForbidden());
```

Đây là đoạn test trong MockMvc đã có security filter chain phù hợp; imports `MockMvcRequestBuilders.get` và `MockMvcResultMatchers.status`. Mẫu không in `Authorization` hay response body vào report khi assertion fail.

### 7.3. Testcontainers logs và DB/Kafka

- `container.getLogs()` có thể trả nguyên stdout/stderr của service trong container. Nếu ứng dụng ghi credentials, SQL bind values hoặc request body, **đừng upload raw logs**.
- `@ServiceConnection` và `@DynamicPropertySource` có thể cấu hình datasource an toàn, nhưng log `spring.datasource.password`, `jdbcUrl` có embedded credential hoặc environment dump vẫn là rủi ro riêng.
- Spring JDBC/Hibernate ở mức TRACE có thể ghi bind parameters (email, tenant ID, thông tin thanh toán).
- Kafka `ConsumerRecord.toString()`, headers hoặc payload JSON có thể chứa user data; không in record raw khi assertion fail.
- Spring Modulith Event Publication Registry có thể lưu serialized event data để phục hồi. **Bảng registry không phải test report công khai**; khi export snapshot cho debug phải phân loại và kiểm soát như dữ liệu ứng dụng.

**Hai nhóm bằng chứng khác nhau:**

1. **Business contract evidence:** đúng loại event, thành công/thất bại, SQL state theo ID synthetic, độ trễ, số lượng; có thể đưa vào safe report nếu được phép.
2. **Raw diagnostic:** HTTP body, Kafka payload, database row, stack trace chứa input, Docker env; chỉ lưu ở kênh đặc biệt khi được duyệt, không upload rộng bằng report mặc định.

Nếu `Scenario` timeout, report công khai có thể ghi `check=EVENT_STATE_REACHED;outcome=FAILED;error_code=TIMEOUT`, thay vì dump nguyên serialized event có thông tin cá nhân.

## 8. CI artifact: xuất đúng file đã được kiểm chứng, không upload cả thư mục

Một file `security-summary.txt` an toàn không giúp được gì nếu pipeline vẫn tự động upload tất cả **JUnit XML, Gradle HTML, raw logs hoặc dumps**.

### 8.1. Tạo artifact có vị trí do CI tin cậy

Ví dụ **một test xuất report riêng** bên trong package module `com.acme.securityreport`. Test này được chọn riêng trong CI, không chạy song song với writer khác cùng file:

`src/test/java/com/acme/securityreport/SafeReportExportTests.java`:

```java
package com.acme.securityreport;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

@Tag("safe-report-export")
@ApplicationModuleTest
class SafeReportExportTests {

    @Autowired SafeSecurityReportWriter writer;

    @Test
    void exportsOnlyAfterCanaryVerification(@TempDir Path staging)
            throws Exception {

        String configuredDirectory =
                System.getProperty("safe.report.dir");

        assertThat(configuredDirectory != null
                && !configuredDirectory.isBlank())
                .as("CI must supply safe.report.dir")
                .isTrue();

        String canary = "TEST_ONLY_CANARY_" + UUID.randomUUID();

        var observation = new SecurityCheckObservation(
                SecurityCheckCode.REPORT_FIELD_ALLOWLIST,
                CheckOutcome.PASSED,
                "synthetic+" + canary + "@example.invalid",
                "Bearer " + canary,
                "https://example.invalid/?token=" + canary,
                "Synthetic exception with " + canary);

        Path candidate = writer.save(observation, staging);
        String content = Files.readString(
                candidate, StandardCharsets.UTF_8);

        boolean safe = content.equals(
                "format_version=1\n"
                + "check=REPORT_FIELD_ALLOWLIST\n"
                + "outcome=PASSED\n")
                && !content.contains(canary);

        // Chưa được phép copy/publish nếu phép kiểm fail.
        assertThat(safe)
                .as("allowlist verification must pass before export")
                .isTrue();

        Path destination = Path.of(configuredDirectory);
        Files.createDirectories(destination);

        Files.copy(candidate,
                destination.resolve("security-summary.txt"),
                java.nio.file.StandardCopyOption.REPLACE_EXISTING);
    }
}
```

**Những gì test export thực sự chứng minh:** *REPORT_FIELD_ALLOWLIST* đã được kiểm chứng với canary synthetic, và **chỉ bản đã qua kiểm tra** được sao chép từ staging sang thư mục CI. Đây **không phải** bản tổng hợp kết quả của toàn bộ security suite, nên không được trình bày `outcome=PASSED` của file này là “mọi security tests đã pass”. Kết luận toàn suite vẫn do **exit code và test reports** của build quyết định.

**Tại sao dùng `@TempDir` rồi mới copy?** Nếu writer vô tình ghi canary vào file, test fail **trước** khi copy tới đường dẫn được cấu hình để upload. Staging vẫn chứa dữ liệu synthetic trong lúc test chạy, nên không upload staging và để JUnit dọn temp đúng lifecycle.

Để sản xuất **báo cáo tổng hợp nhiều test**, sử dụng một **aggregator chạy sau test suite** có đầu vào là các outcome đã kiểm chứng và schema allowlist; không để nhiều test methods cạnh tranh ghi vào một file chung.

### 8.2. Minh họa GitHub Actions: chỉ upload đường dẫn hẹp

Đoạn workflow **minh họa một job trên môi trường GitHub Actions** với Java/Maven; dùng đúng Maven wrapper và tên test class đã viết ở trên:

```yaml
name: security-report-safe

on:
  pull_request:

jobs:
  security:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Run report safety verification
        run: >
          ./mvnw -B
          -Dtest=SafeReportExportTests
          -Dsafe.report.dir=target/safe-reports
          test

      - name: Check only the sanitized artifact
        run: |
          test -f target/safe-reports/security-summary.txt
          if grep -Eqi 'Bearer |authorization|access_token|password|@' \
              target/safe-reports/security-summary.txt; then
            echo "Unsafe field marker detected in report" >&2
            exit 1
          fi

      - name: Upload sanitized report only
        uses: actions/upload-artifact@v4
        with:
          name: safe-security-report
          path: target/safe-reports/security-summary.txt
          if-no-files-found: error
          retention-days: 7
```

**Điều kiện đi kèm:**

- Đây là **report-safety stage minh họa**, không thay full architecture/security/DB/broker tests. Pipeline production phải chạy **tất cả required gates** ở những jobs tương ứng.
- `grep -Eqi` chỉ là một **defense-in-depth heuristic**; nó không thể phát hiện mọi secret. Điểm phòng vệ chính là writer allowlist và test đọc lại đúng bytes.
- `grep -q`/`-q` trả trạng thái mà **không in đoạn khớp**, tránh tự lộ token trong log CI khi phát hiện dấu hiệu vi phạm.
- `if-no-files-found: error` khiến thiếu report không bị biến thành thành công im lặng.
- `retention-days` là **thời hạn lưu artifact** do nền tảng hỗ trợ, không phải quyền truy cập. Cần xem cả cấu hình repository/org và chính sách pháp lý.
- `permissions: contents: read` hạn chế quyền job ở ví dụ; quyền xem/tải artifact vẫn do nền tảng và chính sách repository kiểm soát.
- Trên repository public hoặc PR không đáng tin, phải đánh giá nguy cơ disclosure/poisoning trước khi upload; không truy cập secrets hoặc upload raw logs chỉ để debug.

### Không làm các thao tác sau

```yaml
# Anti-pattern: vô tình upload cả dữ liệu nhạy cảm chưa kiểm duyệt
with:
  path: |
    target/**
    build/**
    **/*.log
```

Cũng không dùng `cat target/surefire-reports/*.xml` hoặc `grep -n "token" ...` trên CI để kiểm tra rò rỉ: những lệnh đó có thể in **chính nội dung nhạy cảm** vào console. Scanner/gate nên trả **mã lỗi và loại vi phạm**, còn mẫu dữ liệu chi tiết phải lưu ở kênh có quyền phù hợp nếu thật sự cần.

## 9. Maven/Gradle reports: cấu hình đúng nhưng không tạo cảm giác an toàn giả

Cách build tool biểu diễn output có thể khác nhau theo phiên bản. Mục tiêu của bước này là **xác định các bản sao của report**, không che đi failure hoặc làm test bị skip.

### Maven Surefire/Failsafe

Maven Surefire có các cài đặt liên quan output của test:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <!-- Console output được chuyển vào file.
             Đây KHÔNG phải cơ chế redact secrets. -->
        <redirectTestOutputToFile>true</redirectTestOutputToFile>
    </configuration>
</plugin>
```

Khi bật `redirectTestOutputToFile`, raw stdout/stderr có thể nằm trong file thay vì console. XML của Surefire cũng có thể có `<system-out>`/`<system-err>` theo phiên bản và cấu hình; tài liệu Surefire hiện hành có tham số `enableOutErrElements`. **Không** chỉ tắt một tùy chọn rồi tuyên bố đã giải quyết rò dữ liệu — phải kiểm tra toàn bộ nơi output được lưu.

Nếu dự án dùng Maven Failsafe cho `*IT`, nó có report/output riêng. Không chỉ rà `target/surefire-reports/` mà bỏ qua integration reports.

**Quy tắc:** test không được đưa raw secret vào stdout/failure messages ngay từ đầu; report generator chỉ nhận allowlisted fields; raw build outputs phải có quyền truy cập phù hợp, thời hạn lưu rõ ràng và quy trình xử lý khi lỗi xảy ra.

### Gradle TestLogging

Ví dụ cấu hình để **giảm độ dài log trên console**, không phải làm sạch XML:

```groovy
tasks.withType(Test).configureEach {
    testLogging {
        events 'failed', 'skipped'
        exceptionFormat = 'short'
        showStandardStreams = false
    }
}
```

Tài liệu Gradle phân biệt **console test logging** với **file test reports**. `showStandardStreams=false` không đồng nghĩa `system-out` được xóa khỏi mọi report hoặc test process không còn ghi output ở nơi khác. `exceptionFormat='short'` không xóa failure message được sinh từ raw data.

Cũng cần lưu ý:

- Gradle thường tạo XML/HTML reports trong `build/test-results` và `build/reports/tests`; đường dẫn có thể được tùy chỉnh.
- Maven Surefire/Failsafe có XML/text reports trong `target`.
- Report entries, screenshots, request dumps và attachments từ plugin khác có đường dẫn **khác**.
- Không cho phép lộ dữ liệu trên console rồi hy vọng CI artifact upload không bao gồm console: CI logs cũng là nơi lưu trữ cần bảo vệ.

### Kiểm chứng đủ vòng đời

1. Chạy test với **canary synthetic**, không với token thật.
2. Kiểm tra output console (không in chính nội dung cấm khi phát hiện).
3. Kiểm tra JUnit XML/HTML, Surefire/Failsafe/Gradle report files, test result attachments.
4. Kiểm tra đường dẫn artifact upload thực tế và quyền download.
5. Kiểm tra **failure path** bằng một mutation synthetic; xác minh khi test đỏ, report/log vẫn không lộ canary.
6. Nếu phát hiện dấu hiệu rò, **fail gate và xử lý report như sự cố bảo mật** — không chỉ xóa bản file local.

## 10. Runbook, checklist và bài tập

### 10.1. Runbook khi scanner hoặc reviewer phát hiện dữ liệu nhạy cảm

| Tình huống | Ưu tiên hành động | Điều không nên làm |
| --- | --- | --- |
| Canary synthetic xuất hiện trong safe report | Fail test/gate; tìm field bị serialize ngoài allowlist | Nới regex để “cho xanh” |
| Token/PII thật xuất hiện trong CI log/artifact | Hạn chế quyền truy cập; thu hồi/rotate secret nếu cần; xử lý theo quy trình sự cố | Re-run rồi cho rằng bản cũ biến mất |
| JUnit XML chứa raw exception | Sửa assertion/error mapping; kiểm tra cả report builder | Chỉ tắt console output |
| HTTP request dump có `Authorization` | Tắt raw request log; thay bằng status/route code allowlisted | In log thêm để debug công khai |
| Testcontainers `getLogs()` chứa credential | Dừng upload raw logs; xác định ai ghi credential ra container stdout | Dùng `docker logs` trong public CI log |
| Report xuất thành công nhưng all tests skipped | Fail pipeline theo executed-count/required-gate policy | Ghi `PASSED` thủ công |
| Artifact có retention quá dài/quyền rộng | Sửa ACL, retention, lifecycle; rà bản đã tồn tại | Chỉ đổi retention cho các bản tương lai |

**Giải quyết sự cố đúng mức:** nếu đã công khai token thật, cần xem đó là dữ liệu đã bị lộ; tùy loại credential phải thu hồi/rotate, đánh giá phạm vi người có quyền truy cập, xóa artifact/log theo chính sách nền tảng và ghi nhận sự cố. Xóa file khỏi workspace sau khi upload **không thu hồi** bản sao ở artifact store hoặc cache.

### 10.2. Checklist trước khi lưu và công bố report

- [ ] Report có **schema allowlist** hữu hạn, không serialize raw test/domain objects.
- [ ] **PASSED và FAILED** đều được xuất bằng cùng chính sách an toàn.
- [ ] Không có mật khẩu, bearer token, API key, cookie, refresh token, private key, DB credential.
- [ ] Không có email/số điện thoại/địa chỉ thật hoặc resource/customer IDs nhạy cảm.
- [ ] Không có raw request/response, URL query string hoặc `Throwable#getMessage()` chưa phân loại.
- [ ] Tên test, tên file, parameterized display names không chứa dữ liệu người dùng.
- [ ] Assertion khi fail không in actual object/record/HTTP response mang secret.
- [ ] `@TempDir`/staging được dùng khi kiểm tra file trước khi publish; không upload staging.
- [ ] Test readback xác nhận **bytes của file đã lưu** đúng allowlist.
- [ ] Canary/negative control dùng **test-only synthetic secret**, không có giá trị bên ngoài.
- [ ] JUnit XML, Maven/Gradle reports, stdout/stderr và stack traces được rà riêng.
- [ ] MockMvc, SQL bind logging, Testcontainers `getLogs()`, Kafka payload và event registry không bị upload raw.
- [ ] CI artifact chỉ định **đúng file đã kiểm chứng**, không dùng glob rộng `target/**`/`build/**`.
- [ ] Scanner fail bằng **mã lỗi/nhãn**, không in đoạn secret khớp pattern.
- [ ] Retention, quyền truy cập, xử lý artifact đã tồn tại và bảo mật runner được xác định.
- [ ] Nếu không tạo được report hoặc không có required tests executed, gate không báo xanh giả.
- [ ] `ApplicationModules.verify()` và các security tests behavior vẫn chạy độc lập với kiểm tra report riêng tư.

### 10.3. Bài tập thực hành

1. **Phân loại:** Với các trường `checkId`, `outcome`, `ownerEmail`, `Authorization`, `fullUrl`, `errorMessage`, lập allowlist tối thiểu cho report.
2. **Rủi ro `toString()`:** Vì sao Java `record` chứa `authorizationHeader` có thể làm lộ token khi `log.info("{}", record)`?
3. **Writer:** Viết `SafeSecurityReportWriter` chỉ xuất `format_version`, `check` và `outcome` như enum.
4. **Readback:** Dùng `@TempDir` ghi file và đọc lại bằng `Files.readString`; assert file đúng schema mà không in toàn bộ actual report khi fail.
5. **Hai trạng thái:** Chạy `@EnumSource(CheckOutcome.class)` và xác nhận cả `PASSED` lẫn `FAILED` đều không chứa synthetic canary.
6. **Mutation:** Tạm thêm `observation.authorizationHeader()` vào writer. Vì sao test canary phải đỏ và cần hoàn nguyên ngay?
7. **Assertion:** So sánh `assertThat(response).isEqualTo(expected)` với kiểm chứng `status == 403` qua boolean. Phép nào có nguy cơ in raw response khi fail?
8. **TestReporter:** Viết `reporter.publishEntry("check", "INVOICE_OWNER_GUARD")`. Vì sao không publish `requestBody`?
9. **JUnit XML:** Một suite không in token ra console nhưng XML vẫn có `system-out`. Đâu là bước kiểm tra tiếp theo?
10. **Maven/Gradle:** Vì sao `redirectTestOutputToFile=true` và `showStandardStreams=false` không phải biện pháp redact?
11. **Spring Modulith:** Một `Scenario` timeout và exception chứa serialized `OrderPaid` với email. Chọn error code nào có thể đưa vào public report thay raw payload?
12. **Testcontainers:** Khi PostgreSQL container fail, có nên upload toàn bộ `container.getLogs()` lên artifact CI không? Nêu cách chẩn đoán có kiểm soát.
13. **CI artifact:** Sửa workflow dùng `target/**` thành allowlist `target/safe-reports/security-summary.txt`; tại sao việc sửa path vẫn chưa đủ bảo vệ console logs?
14. **Incident:** Nếu phát hiện access token thật trong artifact đã upload hôm qua, tại sao xóa bản local hôm nay chưa đủ?
15. **Quality gate:** Report privacy test pass nhưng toàn bộ DB security tests skipped. Làm sao thiết kế gate không phát biểu sai rằng “mọi kiểm thử bảo mật đã đạt”?

**Gợi ý:** (1) chỉ enum metadata; (2) auto-`toString()`; (3) projection; (4) boolean assertions; (5) cả hai outcomes; (6) test fail không in raw; (7) so raw object dễ leak; (8) report entry có thể được lưu; (9) rà XML/plugin outputs; (10) chỉ thay vị trí/hiển thị; (11) `EVENT_STATE_TIMEOUT`; (12) cần sanitized diagnostics; (13) console thuộc surface riêng; (14) rotate/revoke và xử lý bản sao; (15) executed-count, quality gate độc lập.

### 10.4. Tài liệu tham khảo

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): nhóm dữ liệu không nên đưa vào log, xử lý input, bảo vệ lưu trữ và truy cập.
- [JUnit Jupiter — TestReporter](https://docs.junit.org/current/api/org.junit.jupiter.api/org/junit/jupiter/api/TestReporter.html): `publishEntry(...)` và reporting entries.
- [JUnit Jupiter — TempDir](https://docs.junit.org/current/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html): thư mục tạm biệt lập cho test.
- [Maven Surefire — Plugin Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo): `redirectTestOutputToFile`, `enableOutErrElements` và các reports.
- [Maven Surefire — Report Plugin](https://maven.apache.org/surefire/maven-surefire-report-plugin/): tổng hợp báo cáo kiểm thử.
- [Gradle — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): XML/HTML test reports và console test logging.
- [Gradle — TestLogging DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.logging.TestLogging.html): `showStandardStreams`, exception format và giới hạn của console settings.
- [GitHub Actions — upload-artifact](https://github.com/actions/upload-artifact): `path`, `if-no-files-found`, `retention-days`.
- [GitHub Docs — Artifact and Log Retention](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository): retention và quyền quản trị.
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `Scenario` và vòng đời module test.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event publication registry, event payload và async handling.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): architecture gate tách khỏi runtime security/report gate.
- [Testcontainers Java — Container Logs](https://java.testcontainers.org/features/container_logs/): `getLogs()` và `followOutput(...)`, cần chính sách riêng khi lưu.
