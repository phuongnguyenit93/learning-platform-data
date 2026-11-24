# Mask SQL parameter nhạy cảm trong database observability

## 1. Mục tiêu và bối cảnh

Khi điều tra truy vấn chậm hoặc lỗi database, SQL và bind parameters giúp tái hiện vấn đề. Nhưng bind values thường chứa email, số điện thoại, địa chỉ, token, thông tin thanh toán, dữ liệu định danh hoặc nội dung nghiệp vụ riêng tư. Nếu ghi nguyên giá trị vào log, APM hoặc tracing backend, dữ liệu có thể bị nhân bản sang nhiều hệ thống, được giữ lâu hơn database và được nhiều người truy cập hơn.

**Mask SQL parameter** là cách loại bỏ, thay thế hoặc biến đổi giá trị bind parameter trước khi dữ liệu được ghi vào telemetry. Mục tiêu là giữ đủ thông tin kỹ thuật để chẩn đoán query, kiểu dữ liệu, vị trí tham số và hiệu năng, đồng thời không để lộ giá trị thật.

Bài thuộc chương **Database observability** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

Sau bài học, bạn có thể:
1. Xác định các nguồn có thể ghi SQL và bind values.
2. Phân biệt SQL template với parameter values.
3. Chọn chiến lược không ghi, redact, tokenize hoặc allowlist dữ liệu.
4. Cấu hình logging cho Hibernate/JDBC proxy mà không bật bind-value logging ở production.
5. Hiểu vì sao masking ở appender/backend thường quá muộn.
6. Thiết kế structured logs, trace attributes và metrics không chứa PII/secrets.
7. Kiểm thử log thường, exception, tracing và diagnostic tools.
8. Quản lý retention, access control và incident response khi lộ dữ liệu.

**Baseline:** Spring Boot 3.5.x, Java 17+, Hibernate/JPA và Micrometer Observation. Tên logger/property phụ thuộc Hibernate/JDBC proxy version. Kiểm tra logging backend và thư viện thực tế trước khi áp dụng.

## 2. SQL template và bind parameter

Prepared statement tách SQL structure khỏi giá trị dữ liệu:

```sql
SELECT id, email, status
FROM customer
WHERE email = ?
  AND status = ?
```

Các bind values có thể là:
- Parameter 1: alice@example.com
- Parameter 2: ACTIVE

SQL template mô tả cấu trúc truy vấn; bind values là dữ liệu runtime. Database observability thường chỉ cần template, thời gian thực thi, số rows, datasource và kết quả. Không phải lúc nào cũng cần giá trị thật của tham số.

Tránh nối parameter trực tiếp vào SQL string để log:

```java
String sql = "SELECT * FROM customer WHERE email = '" + email + "'";
log.debug("SQL: {}", sql);
```

Cách này vừa có nguy cơ SQL injection nếu dùng để thực thi, vừa làm PII xuất hiện trong message và khó redact chính xác.

Dùng prepared statement:

```java
String sql = "SELECT * FROM customer WHERE email = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    try (ResultSet result = statement.executeQuery()) {
        // Read result.
    }
}
```

Prepared statement tách cấu trúc SQL và dữ liệu; nhưng JDBC proxy hoặc ORM logger vẫn có thể ghi bind values nếu được bật.

## 3. Những nơi SQL parameter có thể bị lộ

| Nguồn | Ví dụ | Rủi ro |
| --- | --- | --- |
| Hibernate SQL logging | SQL statement | Thường chỉ template, nhưng cần kiểm tra |
| Hibernate bind logging | Parameter index/type/value | Có thể lộ PII/secrets |
| JDBC proxy | SQL + bind values | Có thể render câu SQL với giá trị thật |
| Datasource/APM agent | DB spans và statement attributes | Có thể capture statement/parameters |
| Application log | Log request/entity/repository input | Lộ giá trị trước khi query |
| Exception | Constraint violation, SQL error, custom message | Driver/database có thể đưa value vào message |
| Audit/debug tooling | Query console, profiler, support dump | Có thể lưu bản sao ngoài log pipeline |
| Trace exporter | Span attributes/events | Dữ liệu có thể đi sang telemetry backend |

Tắt một logger Hibernate không đảm bảo JDBC proxy hoặc APM agent ngừng capture. Kiểm tra toàn bộ đường đi từ ứng dụng tới nơi lưu telemetry.

### 3.1. Dữ liệu cần coi là nhạy cảm

Mặc định không ghi:
- Password, API key, access/refresh token, session cookie.
- Số thẻ, tài khoản ngân hàng, CVV hoặc payment credential.
- Email, số điện thoại, địa chỉ và thông tin định danh cá nhân.
- Ngày sinh, hồ sơ sức khỏe, thông tin nhân sự.
- Nội dung tự do do người dùng nhập nếu chưa phân loại.
- Secret, encryption key hoặc credential hệ thống.

Ngay cả identifier nội bộ như customer ID/order ID cũng có thể là dữ liệu cá nhân khi liên kết được với người dùng. Phân loại theo policy tổ chức; không coi dữ liệu là vô hại chỉ vì nó không phải password.

## 4. Chiến lược ưu tiên: không ghi bind values

Cách an toàn nhất là không bật bind parameter value logging ở production nếu không có use case được phê duyệt.

Với Hibernate 6, bind parameter logging thường gắn với logger category:
- org.hibernate.SQL: SQL statements.
- org.hibernate.orm.jdbc.bind: JDBC bind parameter values.
- org.hibernate.orm.jdbc.extract: giá trị được extract từ ResultSet.

Cấu hình production có thể giữ SQL template ở mức WARN hoặc DEBUG theo nhu cầu, đồng thời tắt bind/extract values:

```yaml
logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: OFF
    org.hibernate.orm.jdbc.extract: OFF
```

Tên logger và level hợp lệ cần đối chiếu Hibernate version. Một số bản Hibernate 5 dùng category khác. Không copy cấu hình Hibernate 6 sang Hibernate 5 mà không kiểm tra.

Nếu cần quan sát truy vấn thường xuyên, ưu tiên:
- SQL template hoặc normalized statement.
- Query fingerprint.
- Datasource/database name.
- Execution duration và outcome.
- Rows affected/returned nếu đo được an toàn.
- Trace ID/span ID.
- Error class/code đã sanitize.

Không cần bind values để xác định phần lớn vấn đề query plan, latency, lock wait hoặc connection pool.

## 5. Cấu hình theo môi trường

Không bật bind logging trong cấu hình mặc định rồi hy vọng production profile sẽ nhớ tắt. Đặt safe default ở base configuration:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        format_sql: false

logging:
  level:
    org.hibernate.SQL: WARN
    org.hibernate.orm.jdbc.bind: OFF
    org.hibernate.orm.jdbc.extract: OFF
```

Trong local development, nếu thật sự cần bind values, bật có giới hạn bằng profile riêng:

```yaml
# application-local.yml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.hibernate.orm.jdbc.extract: OFF
```

Quy tắc:
- Local data phải là synthetic/anonymized.
- Không dùng production database snapshot có PII trên máy developer nếu chưa có phê duyệt và biện pháp bảo vệ.
- Không bật TRACE bind logging trong production để “debug tạm” mà không có thời hạn, owner và change record.
- Sau điều tra, tắt cấu hình và xác nhận không còn logger/appender/agent khác capture parameter values.

Thuộc tính show-sql có thể ghi SQL trực tiếp ra console và không đi theo cùng logger routing như cấu hình logging thông thường. Production nên giữ false và quản lý SQL diagnostics qua logging framework có kiểm soát.

## 6. Masking ở nguồn phát telemetry

### 6.1. Vì sao appender masking có thể quá muộn?

Nếu bind value đã được tạo thành log event, nó có thể đã đi qua:
- Async logging queue.
- File appender.
- Console/stdout collector.
- APM agent hoặc sidecar.
- Remote log forwarder.

Masking chỉ ở một appender không đảm bảo các sink khác không nhận raw value. Nếu event đã được serialize hoặc gửi qua network, một appender khác có thể đã lưu dữ liệu thật.

Ưu tiên ngăn giá trị được tạo ra trong telemetry ngay từ nguồn. Nếu không thể tắt capture, dùng instrumentation có khả năng redact trước khi event/span được publish; test tất cả exporters và sinks.

### 6.2. JDBC proxy và datasource instrumentation

Một số thư viện JDBC proxy có thể log SQL cùng bind values để hiển thị query thực tế. Datasource proxy, P6Spy hoặc agent instrumentation có thể được cấu hình để:
- Không log parameter values.
- Thay value bằng placeholder.
- Dùng custom formatter/filter.
- Chỉ log normalized SQL.
- Exclude query/table/field nhạy cảm.

Tên property và hook phụ thuộc phiên bản thư viện. Không đoán cấu hình dựa trên ví dụ của version khác. Kiểm tra tài liệu đang dùng và xác nhận bằng test có sentinel value.

Nếu thư viện chỉ redact sau khi đã dựng log message chứa raw SQL, cần đánh giá nơi xử lý và các sink khác. Giải pháp tốt hơn thường là disable parameter capture hoặc dùng formatter không bao giờ serialize giá trị nhạy cảm.

## 7. Redaction, masking và tokenization

Ba cách biến đổi dữ liệu không giống nhau:

| Cách | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Redaction | [REDACTED] | Xóa hoàn toàn giá trị |
| Masking | ****1234 | Giữ một phần giá trị theo policy |
| Tokenization | tok_8fa... | Thay bằng token tham chiếu, cần hệ thống quản lý token |

### 7.1. Redaction

Đây là lựa chọn mặc định an toàn cho password, token, CVV và dữ liệu không cần để điều tra:

```text
bind[1] type=VARCHAR value=[REDACTED]
bind[2] type=INTEGER value=42
```

Nếu không cần biết parameter 1 có phải email hay không, không ghi value hoặc thay bằng placeholder chung.

### 7.2. Masking một phần

Chỉ dùng khi phần còn lại có mục đích chẩn đoán được phê duyệt. Ví dụ số điện thoại có thể chỉ giữ hai chữ số cuối; email có thể bỏ local part. Nhưng masking một phần vẫn là dữ liệu có thể liên kết lại với người dùng, nên cần policy, access control và retention.

Không viết regex chung trên toàn bộ SQL text rồi coi là giải pháp chắc chắn. SQL có nhiều dialect, quoting, escape và binary values; regex dễ bỏ sót hoặc làm sai cú pháp.

### 7.3. Hash/tokenization

Hash không tự động làm dữ liệu vô danh. Hash không salt của email/phone có thể bị dò bằng dictionary. Nếu cần correlation theo giá trị ổn định, dùng keyed HMAC với key quản lý an toàn và policy riêng; không ghi key hoặc raw value. Tokenization phù hợp khi cần mapping được kiểm soát, nhưng token store cũng cần bảo vệ.

Đối với đa số database logs, placeholder [REDACTED] hoặc bỏ hẳn value đơn giản và an toàn hơn.

## 8. Allowlist thay vì blocklist

Một cách nguy hiểm là log tất cả parameter rồi cố chặn vài tên field nhạy cảm như password, email, phone. Schema thay đổi hoặc query mới có thể dùng tên khác, khiến dữ liệu lọt qua.

Ưu tiên allowlist:
- Chỉ log loại metadata đã được duyệt.
- Chỉ log giá trị parameter có classification rõ là non-sensitive.
- Với parameter chưa biết, mặc định redact.
- Không suy luận an toàn chỉ từ tên cột.

| Parameter classification | Log value? | Output |
| --- | --- | --- |
| Secret/credential | Không | [REDACTED] |
| Personal data | Không, trừ phê duyệt cụ thể | [REDACTED] |
| Business identifier | Theo policy | Redacted/tokenized |
| Safe enum có tập hữu hạn | Có thể | ACTIVE |
| Unknown/unclassified | Không | [REDACTED] |

Ngay cả enum/status cũng cần xem có thể tiết lộ trạng thái tài khoản hoặc nghiệp vụ hay không.

## 9. Không đưa parameter vào metrics hoặc span attributes

Metrics cần cardinality thấp. Không đưa bind values vào tags:

```java
// Không an toàn: value có thể là email hoặc ID duy nhất.
Counter.builder("db.query.executions")
        .tag("customerEmail", email)
        .register(registry)
        .increment();
```

Dùng các tag hữu hạn:

```java
Counter.builder("db.query.executions")
        .tag("operation", "customer.lookup")
        .tag("outcome", "success")
        .register(registry)
        .increment();
```

Với tracing, span attributes/events cũng có thể được export và lưu lâu dài. Không gắn raw SQL parameters vào span attributes chỉ vì tracing backend hỗ trợ search. Giữ:
- DB system/operation.
- Normalized query summary hoặc fingerprint đã được policy duyệt.
- Duration, rows/count nếu an toàn.
- Error category/code đã sanitize.
- Service/resource attributes và trace context.

Không lưu SQL full text nếu nó có literal values. Prepared statement template thường an toàn hơn nhưng vẫn cần xem identifier/table names có tiết lộ kiến trúc hay dữ liệu riêng tư không.

## 10. Exception và database error messages

Driver/database exception có thể chứa SQL statement, constraint value, table name hoặc một phần dữ liệu đầu vào. Vì thế, masking bind logger thôi chưa đủ.

Không nên:

```java
catch (DataAccessException ex) {
    log.error("Database failure for customer {}", email, ex);
    throw ex;
}
```

Cách tốt hơn:

```java
catch (DataAccessException ex) {
    log.error("Customer lookup failed; operation=customer.lookup", ex);
    throw ex;
}
```

Tuy nhiên, throwable message/cause vẫn có thể chứa raw SQL hoặc parameter values từ driver. Nếu error message có thể chứa dữ liệu nhạy cảm:
- Dùng error code/class và operation context đã sanitize.
- Không log throwable trực tiếp vào sink không có khả năng bảo vệ phù hợp.
- Có thể log sanitized exception summary ở boundary và giữ full diagnostic trong hệ thống hạn chế quyền nếu policy cho phép.
- Tránh chuyển raw exception message sang API response.

Không bỏ cause chain khỏi mọi nơi một cách máy móc: cần giữ khả năng điều tra ở kênh bảo mật phù hợp. Nhưng đừng mặc định stack trace luôn an toàn.

## 11. Kiểm thử masking

Một test chỉ kiểm tra logger không ném exception là chưa đủ. Dùng sentinel values dễ nhận biết để tìm rò rỉ qua mọi sink.

Ví dụ sentinel:
- Email: sensitive-user-987@example.test
- Token: SECRET_SENTINEL_7F3A
- Phone: +84987654321

Test:
1. Thực thi query có các sentinel values qua ORM/JDBC.
2. Bật cấu hình logging giống production.
3. Thu output từ console/file/appender test.
4. Kiểm tra raw sentinel không xuất hiện.
5. Kiểm tra SQL template, operation name, duration và error class vẫn có thể quan sát.
6. Gây SQL constraint exception để kiểm tra message/cause không làm lộ sentinel.
7. Kiểm tra trace span attributes/events và exporter payload.
8. Kiểm tra JDBC proxy/P6Spy/APM agent nếu có trong deployment.
9. Chạy test cho từng profile (local, test, staging, production).
10. Xác nhận masking không chỉ áp dụng ở một appender trong khi sink khác nhận raw value.

Ví dụ assertion:

```java
assertThat(capturedLogs)
        .doesNotContain("sensitive-user-987@example.test")
        .doesNotContain("SECRET_SENTINEL_7F3A")
        .doesNotContain("+84987654321")
        .contains("[REDACTED]");
```

Integration test nên gom output từ các logging appenders và telemetry exporters cần kiểm soát, không chỉ một logger mock.

## 12. Vận hành và incident response

- Đặt safe default ở base config và kiểm tra effective config theo từng environment.
- Giới hạn quyền truy cập database logs, traces, APM và support bundles.
- Đặt retention ngắn nhất đáp ứng mục đích vận hành.
- Không copy raw production logs vào ticket/chat hoặc máy developer.
- Dùng synthetic/anonymized data khi tái hiện lỗi.
- Quản lý thay đổi logging/agent configuration qua review và audit trail.
- Khi bật diagnostics tạm thời, xác định owner, scope, thời hạn, data classification và nơi lưu.
- Sau điều tra, tắt capture và xác minh bằng sentinel test.
- Nếu phát hiện raw sensitive values đã bị ghi, xử lý như data exposure: giới hạn truy cập, xác định sinks/retention/replicas, thực hiện incident process và rotation credential nếu cần.

## 13. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Hibernate SQL không có value nhưng log vẫn lộ | JDBC proxy hoặc APM agent capture bind parameters | Kiểm tra mọi instrumentation và exporter |
| Tắt bind logger nhưng vẫn có parameter | Logger category khác/version khác hoặc proxy riêng | Xác minh Hibernate version và JDBC proxy config |
| Log đã redact nhưng file khác còn raw value | Masking chỉ gắn vào một appender | Redact/disable ở source, kiểm tra tất cả sinks |
| Exception message lộ SQL/value | Driver hoặc ORM đưa statement vào cause | Sanitize error summary và kiểm soát throwable sink |
| SQL log bị nhân đôi | Hibernate logger và JDBC proxy cùng log | Chọn một SQL logging source |
| Local profile làm lộ production data | Dùng production snapshot không anonymize | Chỉ dùng synthetic/anonymized data |
| Trace backend chứa parameter | Span attributes/event ghi raw SQL hoặc body | Tắt capture hoặc sanitize trước export |
| Metric cardinality tăng | Parameter values được dùng làm tags | Xóa dynamic tags, dùng operation/outcome hữu hạn |
| Regex masking bỏ sót value | SQL dialect/escaping/binary format khác | Dùng source-level redaction hoặc disable capture |
| Hash vẫn bị suy ra dữ liệu | Hash không salt có thể dò dictionary | Không hash PII; nếu cần correlation dùng keyed HMAC/tokenization |
| Masking làm mất khả năng debug | Redact cả metadata an toàn | Giữ SQL template, parameter index/type, query fingerprint và timing |
| Production bật TRACE ngoài ý muốn | Profile/environment override | Kiểm tra effective config và deployment policy |

## 14. Checklist production

- [ ] Bind parameter values không được log mặc định trong production.
- [ ] Hibernate bind/extract logger được tắt theo đúng version.
- [ ] JDBC proxy, P6Spy và APM agent đã được kiểm tra riêng.
- [ ] SQL template được parameterize; không nối raw values vào SQL/log message.
- [ ] Dữ liệu unknown mặc định được redact.
- [ ] Allowlist chỉ gồm metadata/values đã được phân loại an toàn.
- [ ] Exception messages và stack traces được đánh giá khả năng chứa PII/secrets.
- [ ] Logs và span attributes không chứa raw bind values.
- [ ] Metrics chỉ dùng tags low-cardinality.
- [ ] Masking xảy ra trước khi dữ liệu tới các sink có thể lưu raw event.
- [ ] Tất cả appenders/exporters/sidecars được kiểm thử bằng sentinel values.
- [ ] Retention, access control và incident response được xác định.
- [ ] Diagnostics tạm thời có owner, scope, expiry và review.
- [ ] Sau debug, cấu hình production được xác minh trở lại safe default.

## 15. Câu hỏi tự luyện

1. SQL template khác bind parameter values ở điểm nào?
2. Vì sao prepared statement không tự bảo đảm parameter values không xuất hiện trong logs?
3. Hibernate 6 bind logging thường dùng logger category nào?
4. Vì sao tắt một Hibernate logger chưa đủ nếu có JDBC proxy/APM agent?
5. Redaction khác masking và tokenization thế nào?
6. Vì sao allowlist an toàn hơn blocklist khi schema thay đổi?
7. Hash email không salt có thể vẫn là dữ liệu suy ra được không?
8. Vì sao masking ở appender có thể quá muộn?
9. Exception message/cause có thể làm lộ parameter như thế nào?
10. Metadata nào vẫn hữu ích khi đã redact bind values?
11. Vì sao không đưa bind values vào metrics tags hoặc span attributes?
12. Sentinel test cần kiểm tra những sinks nào?

## Tài liệu tham khảo

- [Hibernate ORM 6 — Logging](https://docs.jboss.org/hibernate/orm/6.6/logging/logging.html)
- [Hibernate ORM 6 — User Guide](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Framework — Data Access](https://docs.spring.io/spring-framework/reference/data-access.html)
- [P6Spy — Documentation](https://p6spy.readthedocs.io/en/latest/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html)
- [OpenTelemetry — Database Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/db/)

