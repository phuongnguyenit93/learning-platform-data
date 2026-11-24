# Nhật ký có cấu trúc, correlation ID và request ID của nhà cung cấp

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud và SDK tương ứng. Khi một request đi qua API, object storage, database, message broker và worker bất đồng bộ, log cần đủ thông tin để đội vận hành nối các sự kiện lại với nhau và tìm đúng request ở phía nhà cung cấp cloud.

Hãy xét một API tải tài liệu từ Azure Blob Storage. API trả lỗi 503. Log chỉ có dòng “Storage request failed” thì chưa đủ để điều tra. Đội vận hành cần biết request thuộc service nào, correlation ID nào, trace/span nào, thao tác Blob nào, HTTP status nào và Azure đã trả x-ms-request-id nào. Khi liên hệ Microsoft Support, service request ID giúp họ tra cứu request trong hệ thống của Azure.

Bài học này tập trung vào ba lớp định danh và cách đưa chúng vào nhật ký:

- **Nhật ký có cấu trúc (structured logging):** ghi sự kiện thành các field JSON ổn định để hệ thống log có thể lọc, nhóm và truy vấn.
- **Correlation ID:** định danh do ứng dụng quản lý để liên kết các request, log và job thuộc cùng một luồng nghiệp vụ.
- **Provider request ID:** định danh do dịch vụ cloud trả về cho một request cụ thể, dùng để điều tra ở phía nhà cung cấp.

Sau bài này, bạn có thể:

- Bật structured JSON logging với Spring Boot 3.5.
- Thiết kế schema log thống nhất giữa các service và cloud provider.
- Tạo, xác thực và truyền correlation ID qua HTTP, message và xử lý nền.
- Gắn trace ID/span ID từ Micrometer Tracing vào log.
- Thu thập AWS request ID, Azure service request ID và request details do Google API cung cấp.
- Phân biệt request ID, trace ID, correlation ID, message ID và idempotency key.
- Redact secret/PII, tránh log injection và kiểm soát chi phí lưu trữ log.
- Viết kiểm thử xác minh các field quan trọng xuất hiện trong log.

## 2. Phân biệt các loại định danh

Các ID thường xuất hiện cùng nhau trong một log event nhưng không có cùng nguồn gốc hoặc mục đích.

| Định danh | Ai tạo? | Phạm vi | Dùng để |
|---|---|---|---|
| **trace_id** | Tracing SDK/propagator | Một distributed trace | Tìm toàn bộ hành trình kỹ thuật |
| **span_id** | Tracing SDK | Một thao tác trong trace | Tìm một HTTP call, SDK call hoặc handler |
| **correlation_id** | Ứng dụng hoặc gateway tin cậy | Một request/job/business flow | Nối log và sự kiện qua nhiều service |
| **request_id nội bộ** | Ứng dụng/API | Một HTTP request hoặc một lần xử lý | Trả về caller và tìm log của request đó |
| **provider_request_id** | AWS/Azure/Google API | Một request tới dịch vụ cloud | Tra cứu request ở phía provider/support |
| **client_request_id** | Ứng dụng/client SDK | Một request gửi tới provider | Tìm request từ phía client nếu dịch vụ hỗ trợ echo/log |
| **message_id** | Broker hoặc producer | Một message | Tìm một lần gửi/nhận message |
| **idempotency_key** | Ứng dụng/caller | Một hành động nghiệp vụ có thể retry | Ngăn side effect trùng |

Ví dụ, một job có thể có một correlation_id xuyên suốt, nhưng mỗi lần gọi S3, Blob Storage hoặc Pub/Sub lại nhận một provider_request_id khác nhau. Khi SDK retry, từng attempt có thể có request ID riêng. Không dùng provider request ID làm correlation ID vì ứng dụng không kiểm soát được vòng đời của nó.

**Trace ID cũng không phải correlation ID nghiệp vụ.** Trace có thể bị sampling, được tạo lại tại trust boundary hoặc chia thành nhiều trace khi job chạy lâu. Correlation ID/job ID có thể vẫn tồn tại qua các lần retry và nhiều trace khác nhau.

## 3. Structured logging trong Spring Boot 3.5

Structured logging ghi log thành các field có tên và kiểu dữ liệu ổn định, thường là JSON. Spring Boot hỗ trợ sẵn ba định dạng JSON:

- **ECS (Elastic Common Schema):** phù hợp với hệ thống sử dụng Elastic.
- **GELF:** định dạng JSON của Graylog.
- **Logstash:** định dạng JSON phổ biến trong pipeline ELK.

Tính năng structured logging có từ Spring Boot 3.4. Với Spring Boot 3.5, có thể bật ECS cho console:

~~~yaml
spring:
  application:
    name: document-api

logging:
  structured:
    format:
      console: ecs
    ecs:
      service:
        name: document-api
        version: 1.0.0
        environment: production
~~~

Hoặc dùng Logstash:

~~~yaml
logging:
  structured:
    format:
      console: logstash
~~~

Spring Boot tự đưa các key/value trong MDC vào JSON structured log. Có thể thêm field theo từng log event bằng SLF4J fluent logging API với addKeyValue. Khi đã dùng structured format, tránh tự nối chuỗi JSON hoặc ghi log một chuỗi chứa JSON lồng bên trong message.

### 3.1. Vì sao không nên chỉ log một câu văn?

Log dạng văn bản:

~~~text
ERROR Blob download failed for document 42 with status 503
~~~

Log có cấu trúc:

~~~json
{
  "@timestamp": "2026-11-24T10:15:30.123Z",
  "log.level": "ERROR",
  "service.name": "document-api",
  "message": "Cloud dependency call failed",
  "provider": "azure",
  "provider_service": "blob",
  "operation": "download",
  "correlation_id": "req-7f3a",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "provider_request_id": "8f0a-example",
  "http_status": 503,
  "error_type": "service_unavailable"
}
~~~

Hệ thống log có thể lọc provider=azure, nhóm theo operation=download, tìm theo correlation_id hoặc đối chiếu provider_request_id với thông tin từ nhà cung cấp.

## 4. Thiết kế schema log dùng chung

Không cần mọi log event có đủ mọi field. Tuy nhiên, nên thống nhất tên và ý nghĩa các field thường dùng.

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| @timestamp | timestamp | Thời điểm log event theo UTC |
| log.level | string | INFO, WARN, ERROR, DEBUG |
| service.name | string | Tên service |
| service.version | string | Phiên bản ứng dụng |
| deployment.environment | string | local, staging, production |
| message | string | Mô tả ngắn gọn, ổn định |
| trace_id | string | Trace ID nếu có |
| span_id | string | Span ID nếu có |
| correlation_id | string | ID liên kết nghiệp vụ/request |
| request_id | string | ID của request nội bộ nếu cần |
| provider | string | aws, azure, gcp |
| provider_service | string | s3, blob, servicebus, pubsub, rds |
| operation | string | get_object, upload, send_message, query |
| outcome | string | success, error, timeout, rejected |
| http_status | integer | HTTP status nếu có |
| error_type | string | Nhóm lỗi đã chuẩn hóa |
| provider_request_id | string | ID do provider trả về |
| client_request_id | string | ID client gửi nếu dịch vụ hỗ trợ |
| retry_attempt | integer | Số thứ tự attempt nếu instrument được |
| duration_ms | number | Thời gian thao tác |

Một log event nên trả lời một câu hỏi cụ thể. Ví dụ, log bắt đầu xử lý message không cần provider request ID; log lỗi gọi S3 nên có provider, service, operation, error type và request ID nếu response có cung cấp.

Giữ tên field nhất quán giữa service. Không để service A dùng correlationId, service B dùng correlation_id, service C lại dùng requestCorrelation.

## 5. Đưa trace ID và span ID vào log

Khi Micrometer Tracing được cấu hình trong Spring Boot, trace ID và span ID có thể được đưa vào MDC. Với structured logging ECS/Logstash, các field MDC được thêm vào JSON.

Ví dụ cấu hình pattern correlation cho console dạng text:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

Nếu muốn log có thêm correlation ID nghiệp vụ, ứng dụng đặt field correlation_id vào MDC trong phạm vi request. Khi structured logging hoạt động, field này sẽ xuất hiện trong JSON.

Trace ID/span ID giúp điều tra một span cụ thể. Correlation ID giúp tìm cùng một luồng nghiệp vụ qua HTTP, queue và worker. Có thể có log chỉ có correlation ID khi trace bị sampling; cũng có log startup không có cả hai.

Spring Boot/Micrometer thường đưa trace ID và span ID vào MDC với key traceId và spanId. Nếu schema log tập trung dùng trace_id/span_id hoặc trace.id/span.id, hãy chuẩn hóa tên field ở logging customizer hoặc log ingestion pipeline; không giả định MDC key và tên field đã giống nhau.

## 6. Tạo và xác thực correlation ID cho HTTP request

Ứng dụng có thể nhận X-Correlation-ID từ API gateway hoặc client. Không nên tin mọi giá trị header đầu vào: giới hạn độ dài và ký tự để tránh log injection hoặc field bất thường. Nếu thiếu hoặc không hợp lệ, tạo ID mới.

Ví dụ Servlet filter:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Correlation-ID";
    public static final String MDC_KEY = "correlation_id";

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String candidate = request.getHeader(HEADER);
        String correlationId =
                candidate != null && SAFE_ID.matcher(candidate).matches()
                        ? candidate
                        : UUID.randomUUID().toString();

        String previous = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }
}
~~~

Filter này:

- Chỉ chấp nhận ký tự chữ/số, dấu chấm, gạch dưới và gạch ngang, tối đa 64 ký tự.
- Tạo UUID nếu header thiếu hoặc không hợp lệ.
- Đưa correlation ID vào MDC trong thời gian xử lý request.
- Trả lại header X-Correlation-ID để caller dùng khi liên hệ hỗ trợ.
- Khôi phục MDC trước đó để thread servlet không mang ID sang request tiếp theo.

Trong hệ thống có nhiều trust boundary, có thể tạo internal correlation ID mới ở gateway và lưu external request ID riêng. Không dùng correlation ID để xác thực, phân quyền hoặc chứng minh caller là ai.

## 7. Truyền correlation ID qua HTTP client

Micrometer Tracing tự truyền W3C trace context khi dùng HTTP client builder được Spring Boot auto-configure. X-Correlation-ID là field nghiệp vụ riêng nên ứng dụng phải truyền nếu muốn service downstream ghi cùng ID.

Ví dụ với RestClient.Builder:

~~~java
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class DownstreamClientConfiguration {
    @Bean
    RestClient catalogClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.internal")
                .requestInterceptor((request, body, execution) -> {
                    String correlationId =
                            MDC.get(CorrelationIdFilter.MDC_KEY);
                    if (correlationId != null) {
                        request.getHeaders().set(
                                CorrelationIdFilter.HEADER, correlationId);
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Dùng builder từ Spring context để giữ auto-configuration và tracing instrumentation. Nếu request được thực hiện trong thread nền, bảo đảm MDC correlation ID đã được propagate trước khi interceptor chạy.

Không ghi đè traceparent bằng correlation ID. Hai header này có mục đích khác nhau và phải được truyền độc lập.

## 8. Giữ MDC khi chuyển sang thread nền

MDC thường gắn với thread. Khi code chuyển từ servlet thread sang executor, correlation_id có thể không còn. Nếu dùng thread pool, phải capture và restore MDC để tránh mất ID hoặc rò rỉ ID giữa hai task.

Ví dụ TaskDecorator cho MDC:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Gắn decorator vào ThreadPoolTaskExecutor:

~~~java
executor.setTaskDecorator(new MdcTaskDecorator());
~~~

Đoạn decorator trên truyền MDC, bao gồm correlation_id. Nếu ứng dụng cần propagate cả Micrometer Observation/trace context, dùng ContextPropagatingTaskDecorator hoặc compose hai cơ chế đúng cách; đừng thay thế decorator đang truyền trace bằng một decorator chỉ copy MDC. Với Reactor, dùng context propagation theo cấu hình Spring Boot và giữ correlation metadata trong Reactor Context khi phù hợp.

## 9. Ghi log bằng SLF4J fluent API

Spring Boot structured logging hỗ trợ các key/value được thêm bằng SLF4J fluent API. Ví dụ log một lỗi dependency:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class CloudCallLogger {
    private static final Logger log =
            LoggerFactory.getLogger(CloudCallLogger.class);

    public void logFailure(
            String provider,
            String providerService,
            String operation,
            String providerRequestId,
            int status,
            String errorType) {

        log.atError()
                .addKeyValue("provider", provider)
                .addKeyValue("provider_service", providerService)
                .addKeyValue("operation", operation)
                .addKeyValue("provider_request_id", providerRequestId)
                .addKeyValue("http_status", status)
                .addKeyValue("error_type", errorType)
                .log("Cloud dependency call failed");
    }
}
~~~

Không cần nối tất cả field vào message. Giữ message ngắn và ổn định; các field dùng để lọc phải nằm riêng. Nếu provider request ID không có, bỏ field hoặc ghi null theo schema của log platform; không tự tạo ID giả rồi đặt tên là provider request ID.

## 10. Lấy request ID từ AWS SDK for Java 2.x

AWS SDK for Java 2.x cung cấp request ID từ response metadata khi service trả response thành công. Với service exception, AwsServiceException/SdkServiceException cũng cung cấp request ID để tra cứu lỗi.

Ví dụ với S3 HeadObject:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import software.amazon.awssdk.awscore.exception.AwsServiceException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;

public class S3DocumentReader {
    private static final Logger log =
            LoggerFactory.getLogger(S3DocumentReader.class);

    private final S3Client s3;

    public S3DocumentReader(S3Client s3) {
        this.s3 = s3;
    }

    public void inspect(String bucket, String key) {
        try {
            HeadObjectResponse response = s3.headObject(
                    HeadObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build());

            String requestId = response.responseMetadata().requestId();
            log.atInfo()
                    .addKeyValue("provider", "aws")
                    .addKeyValue("provider_service", "s3")
                    .addKeyValue("operation", "head_object")
                    .addKeyValue("provider_request_id", requestId)
                    .log("S3 object metadata retrieved");
        } catch (AwsServiceException ex) {
            log.atError()
                    .addKeyValue("provider", "aws")
                    .addKeyValue("provider_service", "s3")
                    .addKeyValue("operation", "head_object")
                    .addKeyValue("provider_request_id", ex.requestId())
                    .addKeyValue("http_status", ex.statusCode())
                    .addKeyValue("aws_error_code",
                            ex.awsErrorDetails() == null
                                    ? null
                                    : ex.awsErrorDetails().errorCode())
                    .setCause(ex)
                    .log("S3 request failed");
            throw ex;
        }
    }
}
~~~

Các điểm cần nhớ:

- Thành công: lấy response.responseMetadata().requestId().
- Lỗi do service trả về: lấy ex.requestId() và ex.statusCode().
- AWS error code hữu ích hơn việc chỉ nhìn HTTP status vì một số lỗi service có thể dùng status giống nhau.
- Không giả định mọi lỗi network/credential đều có AWS request ID. Nếu request chưa tới service, provider có thể chưa tạo ID.

AWS SDK có thể retry nội bộ. Request ID trong response cuối cùng thường đại diện attempt trả kết quả cuối; nếu cần điều tra từng attempt, dùng SDK telemetry/logging phù hợp và giữ request ID theo từng attempt. Không bật DEBUG toàn bộ HTTP request trong production mà không đánh giá nguy cơ log header/body nhạy cảm.

## 11. Lấy request ID từ Azure SDK for Java

Azure Storage trả service request ID trong response header x-ms-request-id. Client có thể gửi x-ms-client-request-id để hỗ trợ correlation từ phía client; hai ID này không giống nhau.

Với Azure Core, response thành công có thể đọc header từ Response.getHeaders(). Ví dụ:

~~~java
import com.azure.core.http.HttpHeaderName;
import com.azure.core.http.rest.Response;
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobProperties;
import java.time.Duration;

public void logBlobProperties(BlobClient blobClient) {
    Response<BlobProperties> response =
            blobClient.getPropertiesWithResponse(
                    null, Duration.ofSeconds(10), Context.NONE);

    String serviceRequestId = response.getHeaders().getValue(
            HttpHeaderName.fromString("x-ms-request-id"));

    log.atInfo()
            .addKeyValue("provider", "azure")
            .addKeyValue("provider_service", "blob")
            .addKeyValue("operation", "get_properties")
            .addKeyValue("provider_request_id", serviceRequestId)
            .log("Blob properties retrieved");
}
~~~

Với lỗi, BlobStorageException kế thừa HttpResponseException. Có thể lấy response và header:

~~~java
import com.azure.core.http.HttpHeaderName;
import com.azure.storage.blob.models.BlobStorageException;

try {
    // Execute a Blob operation.
} catch (BlobStorageException ex) {
    String serviceRequestId = ex.getResponse() == null
            ? null
            : ex.getResponse().getHeaderValue(
                    HttpHeaderName.fromString("x-ms-request-id"));

    log.atError()
            .addKeyValue("provider", "azure")
            .addKeyValue("provider_service", "blob")
            .addKeyValue("provider_request_id", serviceRequestId)
            .addKeyValue("http_status", ex.getResponse() == null
                    ? null
                    : ex.getResponse().getStatusCode())
            .addKeyValue("azure_error_code", ex.getErrorCode())
            .setCause(ex)
            .log("Azure Blob request failed");
    throw ex;
}
~~~

x-ms-request-id là ID do Azure service tạo. x-ms-client-request-id là ID client gửi; Azure có thể echo ID này trong response khi request được cấu hình để gửi nó. Hãy giữ hai field riêng trong log, ví dụ provider_request_id và client_request_id.

Với Azure SDK retry policy, một logical call có thể phát nhiều physical HTTP requests. Nếu chỉ đọc header từ response cuối cùng, bạn chỉ có ID của response đó. Nếu cần điều tra mọi attempt, instrument HTTP pipeline/retry policy hoặc tracing phù hợp; không suy ra số attempt từ một request ID.

## 12. Lấy request ID từ Google Cloud Java client

Không có một accessor requestId() thống nhất trên mọi Google Cloud Java client và mọi loại lỗi. Cách lấy request ID phụ thuộc API, transport và cấu trúc error details mà service trả về.

Một số Google API trả error detail theo chuẩn google.rpc.RequestInfo. Với client dùng Google API GAX, khi API đưa detail này vào ApiException, có thể đọc:

~~~java
import com.google.api.gax.rpc.ApiException;
import com.google.api.gax.rpc.ErrorDetails;
import com.google.rpc.RequestInfo;

try {
    // Call a Google API.
} catch (ApiException ex) {
    ErrorDetails details = ex.getErrorDetails();
    RequestInfo requestInfo =
            details == null ? null : details.getRequestInfo();
    String providerRequestId =
            requestInfo == null ? null : requestInfo.getRequestId();

    log.atError()
            .addKeyValue("provider", "gcp")
            .addKeyValue("provider_service", "google-api")
            .addKeyValue("provider_request_id", providerRequestId)
            .addKeyValue("status_code", ex.getStatusCode().getCode().name())
            .addKeyValue("error_reason", ex.getReason())
            .setCause(ex)
            .log("Google API request failed");
    throw ex;
}
~~~

Ví dụ này chỉ áp dụng khi API/service trả RequestInfo và phiên bản client cung cấp getErrorDetails(). Nếu detail không có, giữ provider_request_id ở trạng thái không xác định; không lấy trace ID hoặc message ID thay thế.

Với Google Cloud Storage Java, StorageException cung cấp status code, reason, debug info và thông tin lỗi khác, nhưng không nên giả định nó luôn có một provider request ID accessor chung. Kiểm tra response headers hoặc error details theo API cụ thể. Với gRPC, metadata/request ID cũng phụ thuộc service và client stub.

Một số Google API nhận field request_id do client truyền vào để hỗ trợ idempotency cho thao tác tạo/cập nhật. Field này là **client-supplied request ID**, không phải provider-generated request ID. Đừng ghi nó vào provider_request_id.

## 13. Request ID qua message và xử lý nền

Khi API gửi message vào queue, correlation ID nên được truyền cùng message để worker ghi log với cùng luồng nghiệp vụ. Provider request ID của thao tác gửi message là ID của lần gọi broker, không phải ID của message và không nên thay thế message ID.

| Thành phần | ID nên log |
|---|---|
| HTTP API | request_id, correlation_id, trace_id, span_id |
| Producer gọi broker | correlation_id, trace_id/span_id, provider_request_id nếu có |
| Message envelope | event_id/job_id/correlation_id; trace context nếu cần |
| Consumer | correlation_id, message_id, delivery_attempt, trace_id/span_id |
| Worker gọi storage/database | correlation_id, provider, operation, provider_request_id |
| DLQ/replay | original message_id, event_id, correlation_id, replay_id, reason |

Một job có thể tồn tại lâu hơn trace ban đầu. Giữ job_id hoặc correlation_id trong metadata nghiệp vụ để nối log của các lần chạy sau. Trace context dùng để nối spans kỹ thuật khi message được publish/consume; correlation ID vẫn hữu ích khi trace bị sampling hoặc job được replay.

Không đưa toàn bộ payload vào log để tìm message. Ghi message ID, event ID, schema version, destination và error category; chỉ lưu payload ở nơi có kiểm soát truy cập khi thực sự cần.

## 14. Ghi log retry và phân biệt logical call với attempt

Một thao tác SDK có thể retry nội bộ. Cần phân biệt:

- **Logical operation:** hành động ứng dụng muốn hoàn tất, ví dụ upload một tài liệu.
- **Attempt:** một request vật lý gửi tới provider.
- **Provider request ID:** ID của một attempt mà provider đã nhận và trả lời.
- **Retry count:** số attempt bổ sung sau lần thử đầu.

Ví dụ một upload có ba attempts:

~~~text
correlation_id = job-42
operation      = upload_blob
attempt 1      = 429, provider_request_id = azure-req-a
attempt 2      = 503, provider_request_id = azure-req-b
attempt 3      = 201, provider_request_id = azure-req-c
final outcome  = success
~~~

Nếu chỉ log một dòng cuối cùng, bạn biết upload thành công nhưng không biết hai attempt trước đã bị throttling. Nếu log mọi attempt, cần giữ chung correlation ID và một logical operation ID để nhóm chúng lại.

Một quy ước thực tế:

- INFO: log kết quả cuối của logical operation khi cần audit nghiệp vụ.
- WARN: log một attempt bị retryable failure nếu nó ảnh hưởng latency hoặc có ý nghĩa vận hành.
- ERROR: log logical operation thất bại cuối cùng.
- DEBUG: log chi tiết transport/SDK trong môi trường kiểm thử hoặc khi điều tra có thời hạn.

Không ghi cùng một exception ở mọi tầng (SDK wrapper, service, controller và global handler) thành nhiều ERROR event. Chọn một nơi sở hữu log lỗi cuối; tầng khác có thể bổ sung context hoặc propagate exception.

## 15. Exception, stack trace và thông tin chẩn đoán

Khi log exception:

- Ghi error.type hoặc error.class để phân nhóm.
- Ghi provider status/error code, request ID và operation nếu có.
- Gắn throwable để có stack trace khi cần.
- Tránh lặp stack trace ở mọi tầng.
- Không đưa raw exception message vào metric label hoặc field dùng để group cardinality thấp.

Exception message đôi khi chứa URL, resource path, tên account, query hoặc một phần payload. Hãy kiểm tra trước khi log nguyên văn. Spring Boot structured logging hỗ trợ giới hạn độ dài và độ sâu stack trace qua logging.structured.json.stacktrace.*.

Ví dụ:

~~~yaml
logging:
  structured:
    json:
      stacktrace:
        max-length: 8192
        max-throwable-depth: 20
        include-common-frames: false
~~~

Đặt giới hạn theo khả năng ingestion và nhu cầu điều tra. Không cắt mất root cause quan trọng; cũng không xuất stack trace hàng trăm kilobyte cho mọi lỗi lặp.

## 16. Bảo mật: redaction, PII và log injection

Log là dữ liệu vận hành có thể chứa thông tin nhạy cảm. Một khi được chuyển sang hệ thống tập trung, nhiều người và nhiều dịch vụ có thể truy cập.

**Không ghi các dữ liệu sau:**

- Password, access token, refresh token, API key, account key, private key.
- Azure SAS token/query string hoặc URL chứa chữ ký.
- HTTP Authorization, Cookie, Set-Cookie và credential header.
- Toàn bộ request/response body có dữ liệu cá nhân hoặc tài liệu người dùng.
- Database connection string và secret manager response.
- Nội dung message chứa thông tin khách hàng nếu không có nhu cầu và quyền rõ ràng.

**Kiểm soát log injection:**

- Giới hạn độ dài header do caller cung cấp.
- Whitelist ký tự cho correlation ID.
- Dùng structured fields thay vì nối chuỗi do người dùng kiểm soát.
- Không để ký tự newline trong field tự do làm giả log event mới.
- Escape/redact giá trị không tin cậy theo encoder của logging framework.

Provider request ID thường là metadata hỗ trợ chẩn đoán, không phải credential. Tuy nhiên, vẫn nên hạn chế quyền truy cập log và không đưa request ID vào URL công khai hoặc metric labels.

## 17. Cardinality, index và chi phí lưu trữ

Log và metric có yêu cầu khác nhau. Provider request ID, correlation ID và message ID là giá trị gần như duy nhất; chúng phù hợp làm field tìm kiếm trong log có kiểm soát, nhưng không phù hợp làm metric label.

| Giá trị | Structured log | Metric label |
|---|---|---|
| provider = aws/azure/gcp | Có | Có |
| operation = upload/get_object | Có | Có |
| error_type = timeout/throttled | Có | Có |
| provider_request_id | Có, ưu tiên index có kiểm soát | Không |
| correlation_id | Có, index theo chính sách | Không |
| trace_id/span_id | Có hoặc được tracing backend liên kết | Không |
| customer_id/object_name | Chỉ khi được phép và đã kiểm soát | Không |

Một số hệ thống log có chi phí index theo field. Không cần index mọi field có giá trị duy nhất; có thể giữ provider request ID trong raw log và chỉ index khi có nhu cầu điều tra. Áp dụng retention theo môi trường và mức độ quan trọng, đồng thời giới hạn DEBUG/HTTP wire logging.

## 18. Truy vấn log và runbook điều tra

Khi một request lỗi, điều tra theo thứ tự:

1. Tìm correlation_id hoặc request_id từ phản hồi API.
2. Xem trace_id để mở distributed trace nếu trace được lấy mẫu.
3. Lọc log theo provider, provider_service, operation và error_type.
4. Lấy provider_request_id của lần gọi lỗi cuối hoặc attempt cần điều tra.
5. Đối chiếu với AWS request ID, Azure x-ms-request-id hoặc request details của Google API khi liên hệ support.
6. Kiểm tra log retry, status code, client request ID và thời gian để xác định attempt nào bị lỗi.

Ví dụ truy vấn dạng SQL trong hệ thống log hỗ trợ JSON:

~~~sql
SELECT
  "@timestamp",
  service.name,
  provider,
  provider_service,
  operation,
  http_status,
  provider_request_id,
  error_type,
  message
FROM application_logs
WHERE correlation_id = 'req-7f3a'
ORDER BY "@timestamp";
~~~

Ví dụ truy vấn theo provider request ID:

~~~sql
SELECT
  "@timestamp",
  service.name,
  correlation_id,
  trace_id,
  operation,
  provider_request_id,
  message
FROM application_logs
WHERE provider_request_id = '8f0a-example';
~~~

Tên field và cú pháp query tùy hệ thống log (Elastic, CloudWatch Logs Insights, Azure Monitor Logs hoặc Google Cloud Logging). Điều quan trọng là schema phải thống nhất và request ID phải được ghi ở field riêng.

## 19. Kiểm thử và tình huống thực hành

Kiểm thử logging nên xác minh cả nội dung lẫn việc không ghi dữ liệu nhạy cảm.

| Kịch bản | Kết quả mong đợi |
|---|---|
| HTTP request không có correlation ID | Filter tạo ID mới và trả header |
| HTTP request có correlation ID hợp lệ | Giữ ID theo policy và xuất hiện trong log |
| Header chứa newline/ký tự lạ/quá dài | Bỏ giá trị đầu vào và tạo ID mới |
| Request kết thúc | MDC được khôi phục/xóa; request sau không nhận ID cũ |
| Task chuyển sang executor | Correlation ID được propagate và restore |
| HTTP downstream call | X-Correlation-ID được truyền; traceparent do tracing instrumentation quản lý |
| AWS request thành công | Log lấy request ID từ response metadata |
| AWS service exception | Log request ID/status/error code nếu service đã trả response |
| Azure Blob response | Log x-ms-request-id |
| Azure Blob exception | Log x-ms-request-id nếu response có header |
| Google API trả RequestInfo | Log request ID trong ErrorDetails |
| Google API không trả RequestInfo | Không tạo provider request ID giả |
| SDK retry nhiều lần | Không nhầm request ID cuối với toàn bộ attempts |
| Log có exception | Stack trace được giới hạn theo cấu hình |
| Request chứa secret/PII | Không xuất secret hoặc body nhạy cảm |

### 19.1. Unit test cho quy tắc correlation ID

Phần kiểm tra giá trị có thể tách thành một hàm nhỏ:

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIds {
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    private CorrelationIds() {
    }

    public static String normalize(String candidate) {
        if (candidate != null && SAFE.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

Unit test:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CorrelationIdsTest {
    @Test
    void preservesSafeValue() {
        assertEquals("req-42_a", CorrelationIds.normalize("req-42_a"));
    }

    @Test
    void replacesNewlineAndLongValues() {
        String newline = CorrelationIds.normalize("req-42\nforged");
        String longValue = CorrelationIds.normalize("x".repeat(100));

        assertNotEquals("req-42\nforged", newline);
        assertNotEquals("x".repeat(100), longValue);
        assertTrue(newline.length() <= 36);
        assertTrue(longValue.length() <= 36);
    }
}
~~~

### 19.2. Kiểm tra log JSON

Trong integration test, bật structured format và capture output. Parse từng dòng bằng JSON parser, sau đó assert:

- service.name, log.level và message tồn tại.
- correlation_id có cùng giá trị với response header.
- trace_id/span_id xuất hiện khi tracing context tồn tại.
- provider_request_id chỉ có khi adapter nhận được ID từ response/error.
- Không có field như authorization, access_token, sas hoặc raw payload ngoài whitelist.

Không nên chỉ assert chuỗi JSON có chứa một từ khóa; parse JSON giúp phát hiện field bị đổi tên, escape sai hoặc bị lồng vào message.

### 19.3. Tình huống thực hành

**Tình huống A — AWS S3:** Một HeadObject trả 403. Hãy log correlation ID, trace ID, AWS request ID, HTTP status và AWS error code; giải thích vì sao request ID có thể không tồn tại nếu lỗi xảy ra trước khi request tới S3.

**Tình huống B — Azure Blob:** Một lần upload có hai lần retry rồi thành công. Hãy phân biệt x-ms-request-id của từng response với x-ms-client-request-id do ứng dụng gửi, và xác định cần instrumentation ở tầng nào để thu thập mọi attempt.

**Tình huống C — Google Cloud:** Một API trả google.rpc.RequestInfo. Hãy lấy request ID từ ErrorDetails; sau đó kiểm thử một API không có detail này và bảo đảm log không ghi trace ID giả làm provider request ID.

**Tình huống D — Worker bất đồng bộ:** API tạo job với correlation ID job-42, sau đó worker chạy trên executor. Hãy bảo đảm MDC được propagate, log có cùng correlation ID và mỗi cloud operation ghi provider request ID riêng.

**Tình huống E — Log injection:** Caller gửi X-Correlation-ID chứa newline và chuỗi giả mạo ERROR. Hãy kiểm tra filter thay giá trị đó bằng UUID và JSON encoder vẫn tạo đúng một log event.

**Tình huống F — Rò rỉ secret:** SDK exception message có URL chứa SAS query string. Hãy thiết kế log chỉ chứa provider, operation, status, request ID và error type; không ghi URL hoặc exception message nguyên văn nếu chưa redaction.

### Câu hỏi tự kiểm tra

1. **Structured logging giải quyết vấn đề gì?** Tạo field ổn định để hệ thống log lọc và truy vấn thay vì phải phân tích câu văn tự do.
2. **Correlation ID do ai quản lý?** Ứng dụng hoặc gateway tin cậy; nó nối một luồng nghiệp vụ qua nhiều service.
3. **Provider request ID do ai tạo?** Dịch vụ cloud trả về cho một request cụ thể.
4. **Trace ID có thay correlation ID không?** Không; trace có thể bị sampling hoặc tách, còn correlation ID có thể tồn tại xuyên suốt job.
5. **AWS SDK v2 lấy request ID thành công ở đâu?** Từ response.responseMetadata().requestId().
6. **AWS service exception lấy request ID ở đâu?** Từ AwsServiceException.requestId().
7. **Azure Blob service request ID nằm ở header nào?** x-ms-request-id.
8. **Azure client request ID khác service request ID thế nào?** Client request ID do ứng dụng gửi; service request ID do Azure trả.
9. **Google Cloud có một request ID accessor dùng chung cho mọi SDK không?** Không; phụ thuộc API, error details và transport.
10. **Có nên đưa provider request ID vào metric label không?** Không; giá trị gần như duy nhất làm cardinality tăng mạnh.
11. **MDC có tự truyền qua thread pool không?** Không; cần context propagation hoặc TaskDecorator phù hợp.
12. **Có được log access token/SAS URL để debug không?** Không; dùng request ID, correlation ID, error code và trace để điều tra.

## 20. Tổng kết

Nhật ký hữu ích cho hệ thống Spring Cloud cần **schema ổn định, correlation ID xuyên service và provider request ID đúng nguồn**. Spring Boot 3.5 hỗ trợ structured JSON logging (ECS, GELF, Logstash), đưa MDC và key/value của SLF4J vào log. Micrometer Tracing bổ sung trace ID/span ID; ứng dụng bổ sung correlation ID để nối luồng nghiệp vụ qua HTTP, message và worker.

AWS SDK for Java 2.x cung cấp request ID trong response metadata và service exception. Azure Storage trả service request ID qua x-ms-request-id, tách biệt với client request ID. Google Cloud không có một accessor request ID chung cho mọi client; chỉ ghi request ID khi API thực sự trả google.rpc.RequestInfo hoặc cơ chế tương đương.

Giữ provider request ID trong log có cấu trúc, không dùng làm metric label; propagate MDC an toàn qua thread; redaction secret/PII; giới hạn stack trace và HTTP debug logging. Khi sự cố xảy ra, dùng correlation ID để tìm luồng, trace ID để mở hành trình, provider request ID để làm việc với cloud support.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Logging and Structured Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 — Tracing and Log Correlation](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [SLF4J — Fluent Logging API](https://www.slf4j.org/manual.html#fluent)
- [AWS SDK for Java 2.x — Logging with the SDK](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/logging-slf4j.html)
- [AWS SDK for Java 2.x — AwsResponseMetadata](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/awscore/AwsResponseMetadata.html)
- [AWS SDK for Java 2.x — AwsServiceException](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/awscore/exception/AwsServiceException.html)
- [Microsoft Learn — Azure SDK for Java exceptions](https://learn.microsoft.com/java/api/com.azure.core.exception?view=azure-java-stable)
- [Azure SDK for Java — HttpResponse](https://azuresdkdocs.z19.web.core.windows.net/java/azure-core/1.56.1/com/azure/core/http/HttpResponse.html)
- [Azure SDK for Java — HttpHeaders](https://azuresdkdocs.z19.web.core.windows.net/java/azure-core/1.56.1/com/azure/core/http/HttpHeaders.html)
- [Google Cloud — RequestInfo](https://docs.cloud.google.com/java/docs/reference/proto-google-common-protos/latest/com.google.rpc.RequestInfo)
- [Google Cloud — GAX ApiException and ErrorDetails](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.rpc.ErrorDetails)
- [Google Cloud — Data Manager API error details and RequestInfo (Java)](https://developers.google.com/data-manager/api/devguides/concepts/understand-errors)
