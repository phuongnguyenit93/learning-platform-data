# Xử lý log test và báo cáo thất bại an toàn

## 1. Vì sao log test REST Docs cần được bảo vệ?

Trong module **SPRING_REST_DOCS**, các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured vừa xác minh API vừa sinh generated snippets. Khi test thất bại, framework, HTTP client, assertion library và build tool có thể ghi request/response body, headers, exception message, stack trace, test parameters và snippets.

Những dữ liệu này có thể chứa Authorization, cookie, session ID, API key, access/refresh token, password, PII, query token, connection string hoặc hostname nội bộ. Preprocessor của Spring REST Docs chỉ xử lý recorded operation dùng để tạo snippet; nó không tự che HTTP client logs, assertion failure, JUnit report, console output hay CI artifacts.

Mục tiêu là giữ đủ thông tin để xác định test, operation, status và vị trí assertion thất bại, đồng thời không in credential hoặc payload nhạy cảm.

## 2. Các kênh có thể làm lộ dữ liệu

| Kênh | Ví dụ | Rủi ro |
| --- | --- | --- |
| Test framework | Exception và stack trace | Exception message chứa input nhạy cảm |
| HTTP client logging | Request/response headers, body | Raw Authorization hoặc payload |
| Assertion failure | Expected/actual value | In toàn bộ response body |
| JUnit XML/HTML | Failure message, captured output | CI lưu report lâu dài |
| Build console | Gradle/Maven output | Plugin in dữ liệu thô |
| REST Docs snippets | http-request/http-response | Preprocessor thiếu hoặc mask sai |
| Application logs | Controller/service/security logs | Log request body hoặc cookie |
| CI artifacts | Reports, snippets, dumps | Quyền truy cập rộng, retention dài |

Không có một cấu hình duy nhất bảo vệ tất cả kênh. Hãy xác định nơi nào có thể ghi raw exchange và đặt policy riêng.

## 3. Chỉ log metadata cần thiết

Khi test thất bại, metadata thường đủ để định vị vấn đề:

- Test class và method.
- REST Docs operation identifier.
- HTTP method và route template.
- Expected status và actual status.
- Content-Type và thời gian xử lý.
- Correlation ID giả lập của test.
- Assertion/path cụ thể thất bại.

Tránh ghi Authorization, Cookie, Set-Cookie, query token, raw body, password, secret, dữ liệu khách hàng hoặc toàn bộ environment variables.

Ví dụ failure summary an toàn:

```text
Test: OrderDocumentationTest.getOrder_whenMissing_returns404
Operation: orders-get-not-found
Request: GET /api/orders/{id}
Expected status: 404
Actual status: 500
Content-Type: application/problem+json
Test correlation ID: test-req-42
Failed assertion: $.code expected ORDER_NOT_FOUND
```

Thông tin này giúp truy tìm test và operation mà không in token hay body đầy đủ.

## 4. Tránh wire logging trong test thông thường

HTTP client có thể có chế độ wire/debug logging in headers và body. Chế độ này hữu ích khi điều tra cục bộ nhưng nguy hiểm trong CI hoặc môi trường dùng dữ liệu gần production.

- Không bật raw request/response logging trong pipeline mặc định.
- Nếu cần debug, giới hạn vào test cụ thể và fixture giả.
- Không log Authorization, Cookie, Set-Cookie.
- Không dump body nếu có token hoặc PII.
- Review logging config và CI variables để debug mode không bật ngoài ý muốn.
- Tắt debug sau điều tra và kiểm tra report/artifact đã tạo.

Với Spring Boot, logging mức DEBUG của HTTP client có thể in raw exchange. Đừng giả định DEBUG luôn an toàn.

## 5. Assertion failure không nên in raw payload

Một số assertion tiện lợi hiển thị toàn bộ expected/actual khi thất bại. Với body nhạy cảm, failure message có thể được lưu trong JUnit XML.

Thay vì so sánh toàn body trong mọi trường hợp:

```java
.andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
.andExpect(jsonPath("$.status").value(400))
.andExpect(jsonPath("$.correlationId").value("test-req-42"));
```

Hãy assert field cần thiết. Nếu phải so sánh toàn body, dùng fixture giả và bảo đảm reporter không in credential. Không nối raw body vào custom assertion message.

Ví dụ:

```java
assertEquals("VALIDATION_ERROR", actualCode,
        "Error code mismatch for operation orders-create");
```

Message cho biết operation và field cần kiểm tra mà không hiển thị toàn response.

## 6. Redact trước khi ghi log

Nếu cần log một phần request/response, tạo helper chỉ ghi allowlist field. Không ghi toàn bộ object rồi cố xóa secret bằng regex sau đó.

```java
Map<String, Object> safeSummary = Map.of(
        "operation", "orders-get-not-found",
        "status", 404,
        "contentType", "application/problem+json",
        "correlationId", "test-req-42"
);
logger.info("REST Docs test failure: {}", safeSummary);
```

Với header, allowlist có thể gồm Content-Type, Accept hoặc request ID giả lập. Loại Authorization và cookie. Nếu cần biết xác thực có được gửi hay không, ghi authorizationPresent=true thay vì giá trị.

## 7. REST Docs preprocessors không bảo vệ mọi log

Có thể che token trong recorded operation trước khi sinh snippets:

```java
.andDo(document("token-get",
    preprocessRequest(
        modifyHeaders().set("Authorization", "Bearer [REDACTED]")
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile(
                "\"accessToken\"\\s*:\\s*\"[^\"]+\""),
            "\"accessToken\":\"[REDACTED]\"")
    )
))
```

Cấu hình này bảo vệ snippets được tạo từ operation đã preprocess. Nó không tự che:
- HTTP client wire logs đã ghi trước đó.
- Assertion failure chứa body gốc.
- Application log ghi Authorization.
- JUnit report hoặc captured stdout/stderr.
- Custom reporter đọc response gốc.
- Debug dump do test/plugin khác tạo.

Preprocessing là một lớp bảo vệ cho tài liệu; logging cần policy riêng.

## 8. Giữ stack trace nhưng loại thông tin bí mật

Stack trace hữu ích để tìm lỗi lập trình, nhưng exception message có thể chứa SQL, URL có credential, request body hoặc dữ liệu người dùng.

- Giữ loại exception, class/method và stack trace nội bộ theo quyền truy cập.
- Dùng message chung cho client.
- Không nối raw payload/token vào exception message.
- Không đưa exception message chưa kiểm soát vào error response.
- Dùng correlation ID liên kết response công khai với log nội bộ.
- Kiểm soát access và retention của log có stack trace.

Ví dụ:

```java
catch (Exception exception) {
    String correlationId = requestCorrelation.currentId();
    logger.error("Unexpected API failure, correlationId={}",
            correlationId, exception);
    throw new InternalApiException(
            "Đã xảy ra lỗi hệ thống", correlationId);
}
```

Ví dụ giữ stack trace trong log nội bộ, còn message đưa lên HTTP là thông điệp chung. Chọn một layer sở hữu việc log exception để tránh duplicate noise.

## 9. Quản lý test fixture và secret

Dùng dữ liệu giả có marker dễ nhận biết:

```text
test-secret-marker-987
test-user@example.test
test-session-id-42
```

Không dùng token production, credential cá nhân, snapshot database có PII thật hoặc environment variable chứa secret làm expected response. Nếu test cần xác thực, tạo token giả hoặc credential chỉ dùng trong test environment.

Marker giả giúp pipeline scan artifact để phát hiện rò rỉ ngoài ý muốn.

## 10. Cấu hình JUnit và build report

JUnit XML và HTML report có thể chứa failure message và captured output. Với Gradle Groovy DSL, có thể hạn chế console output:

```groovy
tasks.test {
    testLogging {
        events "failed", "skipped"
        showStandardStreams = false
        exceptionFormat = "short"
    }
}
```

Cấu hình này giảm output console; exceptionFormat short không phải redaction. JUnit XML vẫn có thể chứa failure message, vì vậy cần kiểm tra report và quyền truy cập artifact.

Với Maven Surefire/Failsafe, chọn console/report output phù hợp và tránh plugin dump raw exchange. Không tắt toàn bộ failure details nếu team cần chẩn đoán; hãy làm failure message an toàn ngay từ source.

## 11. Scan artifact trước khi publish

Sau documentation tests, pipeline có thể scan:
- build/generated-snippets hoặc target/generated-snippets.
- JUnit XML và HTML reports.
- Captured stdout/stderr.
- Asciidoctor output.
- Debug dump hoặc HTTP exchange file do plugin tạo.

Scan marker giả từ fixture:

```text
test-secret-marker-987
test-session-id-42
```

Nếu marker xuất hiện trong artifact public, pipeline phải fail. Tránh regex quá rộng gây false positive; ưu tiên marker giả đặc trưng cộng với kiểm tra header/field nhạy cảm đã biết.

Không upload report/snippets lên artifact store public trước khi scan hoàn tất. Thiết lập retention và access control phù hợp.

## 12. Failure reporter an toàn

Có thể xây helper chỉ chứa metadata allowlist:

```java
record RestDocsFailureSummary(
        String testName,
        String operation,
        String method,
        String route,
        int expectedStatus,
        int actualStatus,
        String contentType,
        String correlationId,
        String failedPath) {}

logger.error("REST Docs failure: {}", new RestDocsFailureSummary(
        "getOrder_whenMissing_returns404",
        "orders-get-not-found",
        "GET",
        "/api/orders/{id}",
        404,
        500,
        "application/problem+json",
        "test-req-42",
        "$.code"
));
```

Không đưa raw request/response, Authorization hoặc cookie vào summary. Nếu attach summary vào report bằng JUnit extension/listener, listener chỉ nhận dữ liệu đã lọc. Nếu listener đọc response gốc, phải redact trước khi ghi.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong JUnit XML | Assertion in raw body/header | Assert field an toàn và message metadata |
| Console in HTTP exchange | Wire logging ở DEBUG | Tắt mặc định, bật cục bộ có kiểm soát |
| Snippet đã mask nhưng report vẫn lộ | Nhầm preprocessor che mọi kênh | Logging/report policy riêng |
| Stack trace chứa SQL/secret | Exception message ghép dữ liệu nhạy cảm | Message an toàn, log có kiểm soát |
| Report chứa stdout | showStandardStreams bật | Tắt nếu không cần và review report |
| CI artifact public có PII | Upload trước bước scan | Scan trước publish, giới hạn access |
| Debug dump còn lại | Plugin/test tạo file tạm | Dọn artifact debug theo policy |
| Failure message thiếu thông tin | Ẩn mọi chi tiết | Allowlist metadata và correlation ID |
| Test dùng token thật | Fixture phụ thuộc production | Dùng token giả/test-only credential |
| Scan tạo false positive | Regex chung không có context | Marker giả và rule theo file/type |

## 14. Checklist an toàn cho log và report

- [ ] Không bật raw wire logging trong CI mặc định.
- [ ] Không ghi Authorization, Cookie, Set-Cookie hoặc token.
- [ ] Không in raw body trong assertion failure nếu có dữ liệu nhạy cảm.
- [ ] Exception message không chứa credential hoặc payload.
- [ ] Stack trace nội bộ có access control và retention phù hợp.
- [ ] REST Docs preprocessors che dữ liệu trong snippets cần công bố.
- [ ] JUnit XML/HTML report được xem là artifact có thể chứa dữ liệu nhạy cảm.
- [ ] Captured stdout/stderr được kiểm soát.
- [ ] Test dùng fixture giả và marker đặc trưng.
- [ ] CI scan snippets, reports và rendered docs trước publish.
- [ ] Failure summary chỉ chứa metadata allowlist.
- [ ] Debug logging chỉ bật có thời hạn và được tắt sau điều tra.

## 15. Bài thực hành

Dùng test POST /api/auth/token và GET /api/orders/{id}:

1. Tạo fixture có marker test-secret-marker-987, không dùng token thật.
2. Tạo response lỗi chứa correlation ID giả.
3. Assert status, error code và correlation ID mà không in toàn body.
4. Cấu hình REST Docs preprocessor che token trong request/response snippets.
5. Tắt HTTP wire logging trong cấu hình test mặc định.
6. Cấu hình Gradle test logging chỉ hiển thị failed/skipped và không show standard streams.
7. Chạy test thất bại có chủ đích; kiểm tra console và JUnit report không chứa marker.
8. Kiểm tra generated snippets và Asciidoctor output cũng không chứa marker.
9. Thêm artifact scan sau test/report generation và trước upload.
10. Tạo failure summary có test name, operation, status, Content-Type, correlation ID và JSON path.
11. Kiểm tra quyền truy cập và retention của report/artifact trong CI.
12. Bật debug logging cục bộ với fixture giả, sau đó tắt và xác nhận pipeline mặc định vẫn an toàn.

**Tiêu chí hoàn thành:** bạn xác định được các kênh có thể ghi raw HTTP data; thiết kế failure message bằng metadata allowlist; phân biệt REST Docs preprocessing với logging redaction; bảo vệ stack trace, JUnit reports và CI artifacts; và xác minh pipeline scan trước publish.

## Tài liệu tham khảo

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessing.html): xử lý recorded request/response trước khi tạo snippets.
- [JUnit 5 User Guide — Test Execution and Reporting](https://junit.org/junit5/docs/current/user-guide/#running-tests): thực thi và báo cáo test.
- [Gradle — Java testing](https://docs.gradle.org/current/userguide/java_testing.html): cấu hình test logging và test reports.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu nên/không nên ghi log và bảo vệ log.
