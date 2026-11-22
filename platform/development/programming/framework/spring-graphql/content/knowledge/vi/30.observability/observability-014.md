# Không đưa query nhạy cảm vào trace

## 1. Vì sao GraphQL query có thể làm lộ dữ liệu?

Trace giúp tìm nguyên nhân của request chậm hoặc lỗi bằng cách lưu span, attribute và event của từng lần thực thi. Tuy nhiên, telemetry thường được gửi đến hệ thống tập trung, được nhiều nhóm truy cập và có thời gian lưu trữ dài hơn log ứng dụng thông thường. Nếu trace chứa GraphQL document, biến đầu vào hoặc thông báo lỗi có dữ liệu thật, thông tin nhạy cảm có thể rời khỏi phạm vi bảo vệ của dịch vụ.

Một GraphQL operation có thể chứa:

- Thông tin cá nhân như email, số điện thoại, địa chỉ hoặc ngày sinh.
- Thông tin tài chính như số tài khoản, số thẻ, số tiền hoặc dữ liệu giao dịch.
- Thông tin sức khỏe hoặc dữ liệu thuộc nhóm được bảo vệ.
- Credential như access token, API key, mật khẩu hoặc mã xác minh.
- Dữ liệu nội bộ như tenant ID, mã khách hàng, thông tin hợp đồng hoặc cấu trúc nghiệp vụ.

GraphQL document có thể chứa giá trị trực tiếp trong argument. Variables thường được gửi cùng request body. Nếu instrumentation, log hoặc APM ghi lại document hay payload, những giá trị đó có thể xuất hiện trong trace hoặc log.

Mục tiêu là giữ đủ metadata để điều tra hiệu năng và lỗi, đồng thời loại bỏ dữ liệu mà người xem trace không cần biết.

## 2. Các vị trí có thể chứa dữ liệu nhạy cảm

Không chỉ `graphql.document` mới có nguy cơ. Cần kiểm tra toàn bộ đường đi của request và telemetry:

| Vị trí | Ví dụ | Rủi ro |
| --- | --- | --- |
| GraphQL document | `customerByEmail(email: "alice@example.com")` | Literal nằm ngay trong query text |
| GraphQL variables | `{ "email": "alice@example.com" }` | Giá trị được gửi trong request payload |
| Operation name | `customer_0981234567` | Client có thể nhúng dữ liệu vào tên operation |
| Span name | `query customer_0981234567` | Dữ liệu xuất hiện ngay trên tên span và ảnh hưởng cardinality |
| GraphQL error message | `Invalid value for email alice@example.com` | Error event có thể giữ nguyên message |
| Exception message/stack trace | `Payment failed for card 4111...` | Log hoặc exception event có thể chứa giá trị đầu vào |
| HTTP headers | `Authorization`, `Cookie`, custom API key | Credential có thể bị ghi trong transport logs hoặc span attributes |
| HTTP request body | JSON chứa `query` và `variables` | Body capture hoặc debug logging có thể lưu toàn bộ payload |
| Custom Observation/Span attributes | `user.email`, `tenant.id`, `query` | Code tùy chỉnh có thể đưa dữ liệu vào telemetry |

Ngay cả tên field hoặc cấu trúc query cũng có thể tiết lộ thông tin nội bộ. Ví dụ, một field có tên `internalRiskScore` có thể cho biết logic nghiệp vụ mà API không muốn công khai. Vì vậy, việc thay literal bằng `?` giúp giảm rò rỉ giá trị nhưng không phải lúc nào cũng đủ để làm document an toàn.

## 3. Phân biệt document, variables và operation name

GraphQL request thường có ba phần cần quản lý riêng:

```graphql
query CustomerByEmail($email: String!) {
    customerByEmail(email: $email) {
        id
        displayName
    }
}
```

Variables:

```json
{
  "email": "alice@example.com"
}
```

- **Document** mô tả cấu trúc operation và các field được chọn.
- **Variables** chứa giá trị động được truyền vào argument.
- **Operation name** là tên do client đặt cho operation, ví dụ `CustomerByEmail`.

Dùng variables thay cho literal giúp tái sử dụng document và giảm nguy cơ giá trị thật xuất hiện trong query text. Tuy nhiên, variables vẫn có thể bị ghi lại nếu HTTP body, WebSocket payload hoặc request object được log/capture.

Operation name cũng do client cung cấp. Không nên nối email, user ID, tenant ID hoặc mã giao dịch vào operation name. Tên operation nên là tên cố định, có quy ước và không chứa giá trị theo từng request.

## 4. Spring GraphQL mặc định đưa gì vào Observation?

Spring for GraphQL tích hợp Micrometer qua `GraphQlObservationInstrumentation`. Với convention mặc định, Observation `graphql.request` có các KeyValue sau:

| Nhóm | Key | Ý nghĩa |
| --- | --- | --- |
| Low cardinality | `graphql.operation.type` | `query`, `mutation`, `subscription` hoặc `operation` |
| Low cardinality | `graphql.outcome` | `SUCCESS`, `REQUEST_ERROR` hoặc `INTERNAL_ERROR` |
| High cardinality | `graphql.execution.id` | Execution ID của request |
| High cardinality | `graphql.operation.name` | Operation name do client cung cấp |

Convention mặc định của Spring GraphQL không thêm raw GraphQL document hoặc variables vào các KeyValue trên. Đây là một điểm khởi đầu an toàn hơn việc ghi toàn bộ request, nhưng vẫn cần kiểm tra các instrumentation khác và custom convention trong ứng dụng.

`graphql.operation.name` là dữ liệu do client kiểm soát. Nó được xếp vào high-cardinality, chỉ phù hợp với trace và có thể chứa dữ liệu nếu client đặt tên không theo quy ước. Không xem high-cardinality là đồng nghĩa với an toàn hoặc không nhạy cảm.

## 5. Một rủi ro dễ bỏ sót: GraphQL error event

Spring for GraphQL ghi nhận các lỗi trong GraphQL response dưới dạng Observation Events. Theo convention mặc định, tên event thể hiện loại lỗi và contextual name chứa toàn bộ GraphQL error message.

Ví dụ lỗi parser có thể chỉ ra token gây lỗi. Lỗi resolver cũng có thể chứa giá trị argument hoặc thông tin từ exception bên dưới. Nếu message có email, token, số tài khoản hoặc dữ liệu cá nhân, trace event có thể lưu lại chính nội dung đó dù raw query không được thêm vào span attribute.

Vì vậy, cần kiểm soát cả:

- Message trả về từ `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`.
- Message của lỗi parse/validation do GraphQL engine tạo.
- Exception message được ghi vào log hoặc span event.
- Các custom Observation event do ứng dụng tự tạo.

Không đưa `exception.getMessage()` trực tiếp vào GraphQL error hoặc event nếu message có thể chứa dữ liệu đầu vào. Hãy trả message đã chuẩn hóa và giữ chi tiết kỹ thuật trong hệ thống log nội bộ đã được kiểm soát.

## 6. Phân biệt Spring GraphQL Micrometer với OpenTelemetry Java Agent

Một ứng dụng có thể đồng thời dùng:

1. `GraphQlObservationInstrumentation` của Spring for GraphQL.
2. OpenTelemetry Java Agent tự động instrument GraphQL Java.
3. Instrumentation HTTP của Spring Framework hoặc Java Agent.
4. Custom tracing, logging hoặc APM agent của tổ chức.

Các thành phần này không nhất thiết có cùng chính sách thu thập dữ liệu. Việc Spring GraphQL không thêm document vào convention mặc định không chứng minh rằng Java Agent hoặc APM khác cũng không ghi document.

Theo OpenTelemetry semantic conventions hiện hành, attribute `graphql.document` là opt-in. Nếu instrumentation ghi document, nó nên loại bỏ dữ liệu nhạy cảm khi có thể nhận diện và redact một cách đáng tin cậy. OpenTelemetry cũng cảnh báo operation name do client cung cấp có thể có cardinality cao và không khuyến nghị dùng nó trong span name mặc định.

Hãy kiểm tra cấu hình thực tế của tất cả instrumentation đang chạy cùng JVM. Không chỉ đọc cấu hình Spring Boot rồi kết luận trace đã an toàn.

## 7. Dùng variables thay cho literal trong query

Tránh viết giá trị cá nhân hoặc bí mật trực tiếp vào GraphQL document.

Không nên:

```graphql
query {
    customerByEmail(email: "alice@example.com") {
        id
        displayName
    }
}
```

Nên:

```graphql
query CustomerByEmail($email: String!) {
    customerByEmail(email: $email) {
        id
        displayName
    }
}
```

Gửi giá trị trong variables:

```json
{
  "email": "alice@example.com"
}
```

Cách này giúp document ổn định, dễ cache và dễ sanitize literal. Nhưng variables vẫn là dữ liệu nhạy cảm. Không ghi chúng vào log, span attribute, exception message hoặc HTTP body capture. Nếu cần chẩn đoán, hãy ghi loại thao tác, số lượng phần tử, kết quả và mã tương quan đã được thiết kế an toàn.

## 8. Chuẩn hóa operation name và dùng persisted query

Operation name nên phản ánh chức năng, không phản ánh dữ liệu của từng người dùng:

| Không an toàn | Tên cố định nên dùng |
| --- | --- |
| `FindCustomer_alice@example.com` | `FindCustomer` |
| `GetInvoice_123456789` | `GetInvoice` |
| `SearchTenant_tenant-93` | `SearchTenant` |
| `VerifyToken_eyJhbGci...` | `VerifySession` |

Với API public hoặc client không đáng tin cậy, có thể cân nhắc persisted queries/trusted documents. Server chỉ chấp nhận document đã đăng ký theo ID hoặc hash đã được kiểm soát. Cách này giúp giới hạn cấu trúc operation, tránh client gửi document tùy ý và tạo một định danh ổn định để quan sát.

Nếu dùng hash của document làm trace attribute, hãy chuẩn hóa query trước khi hash và không đưa hash có cardinality cao vào metric tag. Hash không phải biện pháp mã hóa dữ liệu: với tập query nhỏ hoặc giá trị dễ đoán, kẻ có quyền truy cập trace vẫn có thể thử đối chiếu bằng dictionary.

## 9. Chỉ giữ metadata cần thiết trong Observation Convention

Spring GraphQL cho phép thay convention mặc định bằng bean `ExecutionRequestObservationConvention`. Nếu không muốn operation name do client gửi xuất hiện trong trace, có thể override high-cardinality KeyValue và chỉ giữ execution ID.

Ví dụ cho Spring Boot:

```java
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
public class GraphQlTracePrivacyConfig {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getHighCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                // Giữ execution ID để tương quan, bỏ operation name do client cung cấp.
                return KeyValues.of(executionId(context));
            }
        };
    }
}
```

`executionId(context)` là phương thức protected của `DefaultExecutionRequestObservationConvention`. Override này giữ execution ID mặc định nhưng loại bỏ `graphql.operation.name` khỏi high-cardinality KeyValue của GraphQL request.

Nếu ứng dụng cần operation name để điều tra, hãy áp dụng allowlist tên operation ở server và kiểm tra dữ liệu trước khi cho phép ghi vào trace. Không thêm raw query hoặc variables vào convention chỉ để giúp việc debug thuận tiện hơn.

## 10. Chỉ thêm low-cardinality metadata an toàn

Khi cần phân biệt phiên bản API hoặc nhóm chức năng, hãy ưu tiên giá trị cố định, hữu hạn:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
public class SafeExecutionConventionConfig {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new SafeExecutionConvention();
    }
}

final class SafeExecutionConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.api.version", "v1"));
    }
}
```

Giá trị `v1` không thay đổi theo user hoặc request nên có cardinality thấp. Các tag hữu ích khác có thể là `client.tier=internal|partner|public` hoặc `deployment.region=ap-southeast-1`, nếu tập giá trị được kiểm soát.

Không thêm các giá trị sau vào low-cardinality KeyValue:

- Email, phone, user ID hoặc tenant ID.
- Execution ID, request ID hoặc session ID.
- GraphQL document, variables hoặc raw URL.
- Search term, free-text input hoặc mã giao dịch.

Các giá trị không giới hạn vừa làm tăng số time series vừa có thể chứa dữ liệu nhạy cảm.

## 11. Cấu hình OpenTelemetry Java Agent cho GraphQL

Nếu ứng dụng dùng OpenTelemetry Java Agent với GraphQL Java instrumentation, agent có các cấu hình riêng cho việc thu thập query document và sanitize query.

Để không ghi document vào span, cấu hình:

```bash
OTEL_INSTRUMENTATION_GRAPHQL_CAPTURE_QUERY=false
OTEL_INSTRUMENTATION_GRAPHQL_QUERY_SANITIZATION_ENABLED=true
OTEL_INSTRUMENTATION_GRAPHQL_OPERATION_NAME_IN_SPAN_NAME_ENABLED=false
```

Ý nghĩa:

| Cấu hình | Tác dụng |
| --- | --- |
| `OTEL_INSTRUMENTATION_GRAPHQL_CAPTURE_QUERY=false` | Tắt việc capture query vào `graphql.document` span attribute |
| `OTEL_INSTRUMENTATION_GRAPHQL_QUERY_SANITIZATION_ENABLED=true` | Bật sanitize literal nhạy cảm nếu query vẫn được capture |
| `OTEL_INSTRUMENTATION_GRAPHQL_OPERATION_NAME_IN_SPAN_NAME_ENABLED=false` | Không đưa operation name do client cung cấp vào span name |

Trong OpenTelemetry Java Agent hiện hành, GraphQL query capture được bật mặc định và query sanitization cũng được bật mặc định. Cấu hình tắt capture là lựa chọn chặt hơn khi không cần xem cấu trúc document trong trace. Nếu cần xem query shape để điều tra, chỉ bật capture sau khi xác minh sanitizer hoạt động với các kiểu literal mà ứng dụng sử dụng.

Các biến môi trường trên thuộc OpenTelemetry Java Agent, không phải property của Spring Boot hoặc Spring GraphQL. Kiểm tra phiên bản agent và tên property trong cấu hình đang triển khai trước khi áp dụng; các tên cũ như `query-sanitizer.enabled` đã được thay bằng `query-sanitization.enabled`.

## 12. Sanitization document có giới hạn gì?

Sanitization thường thay literal bằng placeholder để giữ cấu trúc query:

Query gốc:

```graphql
query FindCustomer {
    customerByEmail(email: "alice@example.com") {
        id
    }
}
```

Document đã sanitize có thể trông như sau:

```graphql
query FindCustomer {
    customerByEmail(email: ?) {
        id
    }
}
```

Cách này vẫn cho phép nhận biết field và cấu trúc selection set mà không giữ literal. Tuy nhiên, sanitizer không phải lúc nào cũng hiểu ý nghĩa nghiệp vụ của mọi giá trị. Nó có thể bỏ sót:

- Dữ liệu được mã hóa hoặc ghép vào string theo format riêng.
- Giá trị nhạy cảm nằm trong operation name hoặc alias.
- Nội dung nằm trong comment hoặc custom directive.
- Giá trị đã được đưa vào custom span attribute trước khi sanitizer chạy.
- Variables được ghi bởi HTTP body logger hoặc APM khác.
- Thông báo lỗi hoặc exception chứa dữ liệu thật.

Vì vậy, sanitizer là lớp phòng vệ bổ sung. Không gửi secret trong query document nếu có thể truyền bằng cơ chế xác thực an toàn, và không coi việc bật sanitizer là giấy phép để ghi toàn bộ request.

## 13. Không capture variables, headers và HTTP body

Variables thường nằm trong JSON body của HTTP request hoặc payload của WebSocket message. Dù Spring GraphQL Observation mặc định không gắn variables thành KeyValue, một thành phần khác có thể ghi request body.

Kiểm tra và tắt hoặc giới hạn:

- Request/response body logging ở reverse proxy, API gateway, servlet filter và WebClient/WebTestClient filters.
- Debug logging của HTTP message converter hoặc codec.
- APM agent có tính năng capture payload.
- Logging toàn bộ `WebGraphQlRequest`, `ExecutionInput`, variables hoặc WebSocket payload.
- Capture `Authorization`, `Cookie`, `Set-Cookie`, API key và custom authentication header.

Không đưa credential vào GraphQL variables. Access token nên được truyền qua cơ chế xác thực của transport, sau đó được xử lý trong security context. Dù vậy, header xác thực cũng không nên xuất hiện trong span attribute hoặc log.

Nếu cần log request để chẩn đoán, hãy tạo một bản ghi đã lọc gồm operation type, tên operation đã allowlist, correlation ID, kích thước payload và kết quả. Không log raw body.

## 14. Làm sạch GraphQL error message trước khi tạo response

Vì Spring GraphQL có thể đưa full error message vào Observation event, cần tạo message an toàn ngay tại nguồn.

Ví dụ dùng `@GraphQlExceptionHandler` để trả message chung:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class SafeGraphQlErrorAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handlePaymentFailure(
            PaymentGatewayException exception,
            DataFetchingEnvironment environment) {

        // Không đưa exception.getMessage() vào response hoặc trace event.
        return GraphqlErrorBuilder.newError(environment)
            .message("Không thể xử lý yêu cầu thanh toán")
            .extensions(Map.of("code", "PAYMENT_UNAVAILABLE"))
            .build();
    }
}
```

`PaymentGatewayException` là exception nghiệp vụ ví dụ của ứng dụng. Nếu cần log lỗi, ghi correlation ID, loại exception và một mã lỗi nội bộ; chỉ ghi stack trace hoặc message gốc trong hệ thống log đã được phân quyền và có chính sách redaction riêng.

Đối với lỗi parse/validation do GraphQL engine tạo, không phải lỗi nào cũng đi qua controller exception handler. Hãy kiểm tra các request sai cú pháp có tạo event chứa token hoặc literal hay không. Nếu có, cần xử lý tại instrumentation/collector phù hợp hoặc giới hạn việc export event đó theo chính sách telemetry.

## 15. Redaction tại OpenTelemetry Collector

Collector có thể làm lớp bảo vệ bổ sung trước khi telemetry được gửi đến backend. Redaction processor của `opentelemetry-collector-contrib` hỗ trợ allowlist attribute, xóa key không được cho phép và mask giá trị khớp mẫu.

Ví dụ cấu hình khái niệm:

```yaml
processors:
  redaction/graphql:
    allow_all_keys: false
    allowed_keys:
      - graphql.operation.type
      - graphql.outcome
      - graphql.field.name
      - http.request.method
      - http.response.status_code
    blocked_key_patterns:
      - '(?i).*authorization.*'
      - '(?i).*token.*'
      - '(?i).*password.*'
      - '(?i).*email.*'
    blocked_values:
      - 'Bearer\s+[A-Za-z0-9._-]+'
    masking_string: "[REDACTED]"
    summary: silent
```

Trong trace pipeline, thêm processor này trước exporter:

```yaml
service:
  pipelines:
    traces:
      processors: [redaction/graphql, batch]
```

Đây là ví dụ minh họa; cấu hình đầy đủ còn cần receiver và exporter của môi trường. Allowlist cần được điều chỉnh theo attribute thực tế mà dashboard và tracing backend sử dụng. Nếu `allowed_keys` quá chặt, một số metadata hữu ích có thể bị loại bỏ.

Redaction processor chỉ xử lý các attribute của span/log/metric datapoint theo cấu hình của nó; không giả định nó tự động làm sạch mọi nội dung trong span event name, log body, resource attribute hoặc payload tùy chỉnh. Hãy kiểm tra chính xác loại dữ liệu và phiên bản processor. Việc redaction ở Collector cũng diễn ra sau khi dữ liệu đã được gửi từ ứng dụng đến Collector, vì vậy không thay thế việc ngăn capture ở nguồn.

Theo tài liệu component hiện hành, redaction processor thuộc Collector Contrib có mức ổn định beta cho traces và alpha cho logs/metrics. Hãy đánh giá độ ổn định và kiểm thử cấu hình theo đúng bản Collector đang triển khai.

## 16. Bảo vệ telemetry ở nơi lưu trữ và truy cập

Ngay cả khi đã loại bỏ query và variables, trace vẫn có metadata cần bảo vệ. Hãy kiểm soát:

- Ai có quyền xem trace, log và metric.
- Những môi trường nào được phép export telemetry ra ngoài.
- TLS và xác thực giữa ứng dụng, Collector và backend.
- Thời gian lưu trữ, chính sách xóa và vị trí lưu trữ dữ liệu.
- Quyền truy cập theo team/service/tenant.
- Việc chia sẻ trace ID trong ticket, chat hoặc công cụ hỗ trợ.
- Backup và bản sao dữ liệu telemetry.

Sampling giúp giảm lượng telemetry và chi phí lưu trữ, nhưng không phải biện pháp redaction. Một span được chọn để export vẫn có thể chứa dữ liệu nhạy cảm. Hãy sanitize trước khi sampling/export và xác minh dữ liệu thực tế trong backend.

## 17. Kiểm thử để phát hiện query hoặc dữ liệu bị rò rỉ

Không chỉ kiểm tra code convention. Hãy kiểm thử telemetry cuối cùng sau khi đi qua instrumentation, processor và exporter.

Một bài kiểm thử privacy nên:

1. Tạo một GraphQL operation có literal giả lập nhạy cảm như `private-test@example.invalid`.
2. Gửi cùng giá trị qua variables.
3. Tạo một lỗi resolver có exception message chứa marker giả lập.
4. Gửi request với header `Authorization` chứa token giả.
5. Thu thập span, event và log qua test exporter hoặc test Collector.
6. Xác nhận marker không xuất hiện trong span name, span attributes, event name, event attributes, log body hoặc log attributes.
7. Xác nhận metadata an toàn như operation type, outcome và correlation ID vẫn còn.

Ví dụ assertion ở mức ý tưởng:

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(exportedSpan.getName()).doesNotContain("private-test@example.invalid");
assertThat(exportedSpan.getAttributes().toString())
    .doesNotContain("private-test@example.invalid")
    .doesNotContain("test-token-value");
```

Đoạn code trên minh họa assertion trên một `SpanData` đã được test exporter thu thập; `exportedSpan` là dữ liệu test, không phải biến có sẵn của Spring. Trong test thực tế, hãy duyệt cả span events và attributes của từng event, không chỉ `getAttributes()` của span. Đồng thời kiểm tra logs vì exception message có thể được ghi độc lập với trace.

Nên có regression test cho các trường hợp:

- Literal trong document.
- Variables trong request body.
- Operation name do client cung cấp.
- GraphQL parser error có offending token.
- Resolver exception có message nhạy cảm.
- Header/cookie và WebSocket `connection_init` payload.
- Custom Observation convention hoặc custom span attribute.
- Query sanitizer và Collector redaction.

## 18. Quy trình điều tra khi phát hiện dữ liệu trong trace

Khi phát hiện query hoặc giá trị nhạy cảm trong trace, hãy xác định nguồn phát trước khi sửa:

| Dấu hiệu trong trace | Nơi cần kiểm tra |
| --- | --- |
| Attribute `graphql.document` | OpenTelemetry GraphQL instrumentation, custom span processor hoặc APM agent |
| Span name chứa operation name | GraphQL Java instrumentation và custom span naming convention |
| Attribute chứa email/ID/token | Custom Observation convention, baggage, HTTP header capture hoặc application instrumentation |
| Event name chứa parser error | Spring GraphQL Observation error events và GraphQL parser message |
| Event chứa exception message | DataFetcher exception resolver, `@GraphQlExceptionHandler` hoặc exception recording handler |
| Log body chứa query/variables | HTTP filter, access log, request/response body logging hoặc WebSocket logger |
| Dữ liệu xuất hiện ở backend dù app đã redacted | Collector pipeline, exporter, backend enrichment hoặc duplicate instrumentation |

Sau khi xác định nguồn:

1. Tắt capture không cần thiết ở instrumentation tạo dữ liệu.
2. Chuẩn hóa operation name và error message.
3. Xóa custom attributes không có mục đích vận hành rõ ràng.
4. Thêm redaction/allowlist ở Collector như lớp phòng vệ thứ hai.
5. Kiểm thử lại bằng marker giả lập trên toàn bộ đường export.
6. Xử lý trace/log đã lưu theo chính sách incident và retention của tổ chức.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Spring GraphQL không ghi document nhưng trace vẫn có query | OpenTelemetry Java Agent hoặc APM khác đang capture `graphql.document` | Kiểm tra tất cả instrumentation; tắt capture hoặc bật sanitizer |
| Variables xuất hiện trong log | HTTP body logging hoặc WebSocket payload logging | Tắt body logging hoặc log bản đã lọc |
| Operation name chứa email/user ID | Client đặt tên operation động | Dùng tên cố định và allowlist/persisted query |
| Trace có parser error chứa literal | Error event giữ full GraphQL error message | Kiểm soát error message hoặc xử lý event tại instrumentation/collector |
| Convention không loại bỏ operation name | Bean convention tùy chỉnh không được auto-configure hoặc bị bean khác thay thế | Kiểm tra bean thực tế và high-cardinality KeyValue được export |
| Đã bật sanitizer nhưng vẫn thấy dữ liệu | Sanitizer không xử lý variables, operation name, error event hoặc custom attributes | Xác định đúng nguồn dữ liệu và áp dụng redaction riêng |
| Collector redaction vẫn để lọt event | Processor không xử lý loại event/name đang chứa dữ liệu | Sanitize ở nguồn và kiểm tra khả năng của processor/version |
| Metrics tăng cardinality sau khi thêm tag | Đưa user ID, query hash hoặc operation name vào low-cardinality tag | Chỉ dùng tập giá trị hữu hạn cho metrics |
| Dùng sampling nhưng trace vẫn có dữ liệu nhạy cảm | Sampling không làm sạch nội dung của span được giữ lại | Redact trước khi export; sampling chỉ giảm lượng dữ liệu |
| Log an toàn nhưng trace vẫn rò rỉ | Trace và log dùng instrumentation/processor khác nhau | Kiểm thử riêng từng signal và từng exporter |

## 20. Checklist không đưa query nhạy cảm vào trace

- [ ] Phân loại dữ liệu nhạy cảm trong document, variables, headers, error message và custom attributes.
- [ ] Không đặt email, user ID, token hoặc mã giao dịch trong operation name.
- [ ] Dùng GraphQL variables thay cho literal, nhưng không log variables.
- [ ] Hiểu các KeyValue mặc định của `GraphQlObservationInstrumentation`.
- [ ] Kiểm tra operation name vì nó do client cung cấp và có cardinality cao.
- [ ] Kiểm tra error event vì contextual name có thể chứa full GraphQL error message.
- [ ] Kiểm tra OpenTelemetry Java Agent và APM instrumentation độc lập với Spring GraphQL.
- [ ] Tắt query capture nếu không cần `graphql.document`.
- [ ] Bật query sanitization nếu vẫn cần lưu query shape.
- [ ] Không capture HTTP body, WebSocket payload, Authorization hoặc Cookie.
- [ ] Chỉ thêm metadata an toàn và có cardinality được kiểm soát.
- [ ] Chuẩn hóa error message trước khi tạo GraphQL response/event.
- [ ] Dùng Collector redaction/allowlist như lớp phòng vệ bổ sung.
- [ ] Kiểm soát quyền truy cập, export, retention và chia sẻ trace.
- [ ] Kiểm thử span name, span attributes, event attributes và logs bằng marker giả lập.

## Kết luận

Không đưa query nhạy cảm vào trace đòi hỏi kiểm soát toàn bộ đường đi của dữ liệu GraphQL. Spring for GraphQL mặc định chỉ đưa operation type, outcome, execution ID và operation name vào `graphql.request`; nó không tự thêm raw document hoặc variables vào convention mặc định. Tuy nhiên, operation name do client cung cấp và GraphQL error event có thể chứa nội dung không an toàn. OpenTelemetry Java Agent, HTTP body logging, WebSocket logging hoặc custom instrumentation cũng có thể thu thập thêm dữ liệu.

Hãy dùng variables thay cho literal, chuẩn hóa operation name, chỉ giữ metadata cần thiết, sanitize error message, kiểm tra query capture của OTel agent và dùng Collector redaction làm lớp bảo vệ bổ sung. Cuối cùng, kiểm thử dữ liệu đã export chứ không chỉ kiểm tra cấu hình trong source code. Trace tốt phải giúp điều tra request và field chậm mà không cần lưu email, token, payload hoặc nội dung riêng tư của người dùng.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — `DefaultExecutionRequestObservationConvention` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DefaultExecutionRequestObservationConvention.html)
- [Spring for GraphQL — `ExecutionRequestObservationContext` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/ExecutionRequestObservationContext.html)
- [OpenTelemetry — Semantic Conventions for GraphQL Server Spans](https://opentelemetry.io/docs/specs/semconv/graphql/graphql-spans/)
- [OpenTelemetry — Handling Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/)
- [OpenTelemetry Collector Contrib — Redaction Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/redactionprocessor)
- [OpenTelemetry Java Agent — Configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/)
