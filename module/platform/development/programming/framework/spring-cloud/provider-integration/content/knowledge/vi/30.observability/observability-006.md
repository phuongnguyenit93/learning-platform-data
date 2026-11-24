# Tích hợp CloudWatch, Azure Monitor hoặc Google Cloud Observability theo thư viện phù hợp

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud và SDK tương ứng. Khi ứng dụng chạy trên cloud, dữ liệu quan sát cần được gửi tới nền tảng mà đội vận hành đang sử dụng: Amazon CloudWatch, Azure Monitor/Application Insights hoặc Google Cloud Observability.

Một ứng dụng Spring Boot thường cần ba nhóm tín hiệu:

- **Metrics:** số request, latency, tỷ lệ lỗi, JVM, connection pool và metric nghiệp vụ.
- **Traces:** hành trình một request qua HTTP, message broker, storage, database và worker.
- **Logs:** sự kiện có cấu trúc, exception, correlation ID và request ID của provider.

Spring Boot cung cấp nền tảng chung qua Actuator, Micrometer Observation và Micrometer Tracing. Mỗi cloud provider có cách tiếp nhận telemetry khác nhau. CloudWatch có Micrometer registry tích hợp với Spring Cloud AWS cho metrics; Azure Monitor cung cấp starter/Java agent cho Application Insights; Google Cloud khuyến nghị OpenTelemetry SDK/Java Agent cùng Collector để gửi OTLP vào Cloud Logging, Cloud Monitoring và Cloud Trace.

Sau bài này, bạn có thể:

- Chọn thư viện phù hợp với Spring Boot và nền tảng triển khai.
- Xuất metrics từ Micrometer sang CloudWatch.
- Thu thập traces, metrics và logs cho Azure Monitor/Application Insights.
- Dùng OpenTelemetry Collector để gửi telemetry tới Google Cloud Observability.
- Cấu hình identity, quyền, region, project và resource attributes.
- Thiết kế dashboard, alert và SLO có thể vận hành.
- Kiểm soát sampling, cardinality, chi phí ingestion và dữ liệu nhạy cảm.
- Kiểm thử đường đi của telemetry từ ứng dụng đến backend.

## 2. Chọn đúng lớp tích hợp

Không có một thư viện duy nhất phù hợp cho mọi tín hiệu và mọi cloud. Hãy phân biệt lớp instrument trong ứng dụng với lớp exporter/collector gửi dữ liệu.

| Lớp | Trách nhiệm | Ví dụ |
|---|---|---|
| Spring Boot Actuator | Cung cấp endpoint và auto-config cho health/metrics | /actuator/health, /actuator/metrics |
| Micrometer | Định nghĩa Timer, Counter, Gauge, Observation | MeterRegistry, ObservationRegistry |
| Micrometer registry | Gửi metrics tới backend | CloudWatch registry, OTLP registry |
| OpenTelemetry instrumentation | Tạo và propagate trace/span | Java Agent, Micrometer Tracing bridge |
| Exporter/agent | Gửi telemetry ra ngoài process | Azure Monitor Java Agent, OTLP exporter |
| Collector/agent hạ tầng | Nhận, enrich, batch, filter và route telemetry | ADOT Collector, OpenTelemetry Collector |
| Cloud observability backend | Lưu trữ, truy vấn, dashboard và alert | CloudWatch, Application Insights, Cloud Monitoring |

Với Spring Boot, nên instrument business metrics bằng Micrometer Observation/MeterRegistry. Traces có thể dùng Micrometer Tracing với OpenTelemetry bridge hoặc OpenTelemetry Java Agent. Logs nên ghi có cấu trúc ra stdout/stderr rồi để agent/collector của môi trường thu thập.

Đừng cài đồng thời nhiều agent/exporter cùng instrument một thư viện nếu chưa có chủ đích. Ví dụ, bật Azure Monitor Java Agent cùng một OpenTelemetry Java Agent khác có thể tạo span và metric trùng lặp.

## 3. Kiến trúc tổng quát

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B[Actuator + Micrometer]
    A --> C[Tracing instrumentation]
    A --> D[Structured logs]
    B --> E{Metrics export}
    C --> F[Agent / OTLP exporter]
    D --> G[stdout / log collector]
    E --> H[CloudWatch]
    E --> I[Azure Monitor]
    E --> J[OpenTelemetry Collector]
    F --> J
    G --> J
    J --> K[Google Cloud Observability]
    F --> L[ADOT / Azure Monitor agent]
    L --> H
    L --> I
~~~

Sơ đồ mô tả các lựa chọn có thể dùng, không phải một ứng dụng cần gửi mọi tín hiệu đến cả ba cloud. Trong triển khai thực tế, chọn backend đích theo môi trường. Collector hữu ích khi cần tách ứng dụng khỏi backend, chuẩn hóa resource attributes, batch telemetry hoặc gửi cùng dữ liệu tới nhiều đích.

## 4. Chuẩn bị nền tảng Spring Boot

Thêm Actuator để có metrics và health instrumentation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot tự đăng ký nhiều meter cho JVM, process, HTTP server và các thành phần được hỗ trợ. Với metric nghiệp vụ, dùng MeterRegistry hoặc ObservationRegistry thay vì tự gọi API của CloudWatch/Azure/Google trong business service.

Ví dụ một observation cho thao tác xử lý tài liệu:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class DocumentService {
    private final ObservationRegistry observations;

    public DocumentService(ObservationRegistry observations) {
        this.observations = observations;
    }

    public void generatePreview(String documentType) {
        Observation.createNotStarted(
                        "document.preview.generate", observations)
                .lowCardinalityKeyValue("document.type", documentType)
                .observe(() -> {
                    // Read source, render preview and persist the result.
                });
    }
}
~~~

Low-cardinality key/value được dùng cho metric và trace. Nếu cần gắn job ID hoặc user ID để điều tra, chỉ thêm vào trace/log theo chính sách; không đưa giá trị có số lượng không giới hạn vào metric tag.

Cấu hình tên service và các endpoint cần thiết:

~~~yaml
spring:
  application:
    name: provider-integration

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  metrics:
    tags:
      application: provider-integration
      environment: production
~~~

Chỉ expose endpoint cần thiết trong mạng quản trị. Endpoint metrics hỗ trợ chẩn đoán tại chỗ; nó không tự gửi dữ liệu lên cloud nếu chưa có registry/exporter.

## 5. AWS: gửi Micrometer metrics tới CloudWatch

### 5.1. Chọn registry và Spring Cloud AWS

Spring Cloud AWS cung cấp auto-configuration cho Micrometer CloudWatch. Với dòng Spring Cloud AWS 3.x/4.x hiện hành, dependency registry là:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-cloudwatch2</artifactId>
</dependency>
~~~

Dùng Spring Cloud AWS BOM phù hợp với phiên bản Spring Boot và Spring Cloud AWS của dự án. Không tự ghim một version Micrometer registry khác với dependency management. Các dự án Spring Cloud AWS 2.x cũ dùng artifact/property khác; không sao chép cấu hình 2.x vào dự án 3.x/4.x.

Spring Cloud AWS 3.x/4.x dùng namespace cấu hình mới:

~~~yaml
management:
  cloudwatch:
    metrics:
      export:
        namespace: ProviderIntegration
        step: 1m

spring:
  cloud:
    aws:
      cloudwatch:
        enabled: true
        region: ap-southeast-1
~~~

Namespace là bắt buộc. Chọn namespace riêng cho ứng dụng hoặc bounded context để tìm metric trong CloudWatch dễ hơn. Region phải là region nơi CloudWatch metrics được ghi.

Trong profile local, tắt publisher để tránh gửi metric test lên AWS:

~~~yaml
spring:
  cloud:
    aws:
      cloudwatch:
        enabled: false
~~~

### 5.2. Identity và IAM permission

Micrometer CloudWatch registry dùng AWS SDK để gọi CloudWatch. Spring Cloud AWS có thể cấu hình region và credentials provider theo cơ chế của AWS SDK. Trên môi trường AWS, ưu tiên IAM role gắn với workload:

- EC2: instance profile.
- ECS: task role.
- EKS: IAM Roles for Service Accounts (IRSA) hoặc EKS Pod Identity.
- Lambda: execution role.

Không đặt access key/secret key cố định trong application.yml hoặc image container. Local development có thể dùng AWS profile/SSO theo credential provider chain.

Quyền cơ bản để publish metric là cloudwatch:PutMetricData. Ví dụ policy giới hạn namespace:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "cloudwatch:PutMetricData",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "ProviderIntegration"
        }
      }
    }
  ]
}
~~~

Policy trên chỉ minh họa quyền ghi metric vào namespace đã chọn. Nếu ứng dụng cần đọc dashboard hoặc alarm thì đó là quyền của người/role vận hành, không nên tự động cấp cho runtime role của ứng dụng.

### 5.3. Kiểm tra metric đã được publish

Sau khi chạy ứng dụng với profile AWS:

1. Tạo traffic để các meter có số liệu.
2. Mở CloudWatch Metrics.
3. Chọn namespace ProviderIntegration.
4. Kiểm tra dimension application, environment, instance hoặc các tag đã cấu hình.
5. So sánh thời điểm metric xuất hiện với export step.

CloudWatch publisher gửi dữ liệu theo chu kỳ, không nhất thiết xuất hiện ngay sau từng request. Nếu đặt step là 1 phút, hãy chờ ít nhất một vài chu kỳ trước khi kết luận export bị lỗi.

## 6. AWS: lọc metric, dimension và chi phí

Mỗi tổ hợp metric name và dimension có thể trở thành một custom metric riêng được tính phí. Spring Boot auto-register khá nhiều meter cho JVM, CPU, memory và các thành phần khác. Nếu gửi tất cả mà không kiểm soát, chi phí CloudWatch có thể tăng nhanh.

Có thể dùng MeterFilter để chỉ publish các metric cần thiết:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CloudWatchMetricsConfiguration {
    @Bean
    MeterFilter cloudWatchMetricAllowList() {
        Set<String> allowed = Set.of(
                "http.server.requests",
                "jvm.memory.used",
                "jvm.gc.pause",
                "process.cpu.usage",
                "document.preview.duration",
                "document.preview.errors");

        return MeterFilter.denyUnless(
                id -> allowed.contains(id.getName()));
    }
}
~~~

Tên meter cần được xác minh từ registry của ứng dụng trước khi đưa vào allow-list. Nếu dùng MeterFilter toàn cục, nó ảnh hưởng các registry khác trong process; nếu chỉ muốn lọc CloudWatch, cấu hình filter theo registry/CloudWatch auto-configuration tương ứng với phiên bản đang dùng.

Dimension nên có tập giá trị nhỏ và ổn định:

- application: provider-integration.
- environment: dev, staging, production.
- provider: aws, azure, gcp.
- operation: upload, download, send_message.
- outcome: success, error.

Không dùng request ID, trace ID, customer ID, object key hoặc exception message làm metric dimension. Những giá trị này thuộc logs/traces.

Spring Cloud AWS có thể dùng MeterFilter để giới hạn số meter được publish. Đặt export step phù hợp với nhu cầu dashboard và chi phí; step ngắn hơn làm dữ liệu cập nhật nhanh hơn nhưng tăng tần suất publish.

## 7. AWS: logs và traces qua ADOT/CloudWatch

Micrometer CloudWatch registry chủ yếu giải quyết metrics. Để gửi traces và logs, dùng instrumentation/collector phù hợp:

- **Traces:** OpenTelemetry Java Agent hoặc AWS Distro for OpenTelemetry (ADOT) Java Agent, gửi OTLP tới ADOT Collector; collector export traces tới AWS X-Ray.
- **Logs:** ứng dụng ghi structured JSON ra stdout/stderr; CloudWatch Agent, ECS log driver, FireLens hoặc pipeline của nền tảng gửi log tới CloudWatch Logs.
- **Metrics:** Micrometer CloudWatch registry hoặc ADOT Collector/CloudWatch EMF tùy kiến trúc.

Một cấu hình Java Agent ở mức khởi chạy minh họa:

~~~bash
JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/aws-opentelemetry-agent.jar"
~~~

Đường dẫn agent phải trỏ tới JAR đã được đóng gói trong image/runtime. Cấu hình exporter endpoint và resource attributes theo ADOT Collector đang triển khai. Không giả định rằng thêm Micrometer CloudWatch registry sẽ tự xuất trace hoặc log.

Với ECS/EKS, cân nhắc chạy collector dưới dạng sidecar hoặc daemon/service theo kiến trúc nền tảng. Collector có thể batch, retry, enrich resource attributes và gửi telemetry mà không buộc ứng dụng phụ thuộc trực tiếp vào X-Ray API.

## 8. Azure: chọn Azure Monitor OpenTelemetry Distro hoặc Spring starter

Azure Monitor/Application Insights có thể nhận metrics, traces và logs. Với Java/Spring Boot, có hai hướng chính:

1. **Spring Cloud Azure Starter Monitor:** tích hợp theo Spring Boot native application và dependency management của Spring Cloud Azure.
2. **Application Insights Java Agent:** attach bằng JVM argument để tự instrument nhiều framework và thư viện mà không sửa code business.

Không bật cả starter và Java Agent cho cùng một ứng dụng nếu chưa xác định rõ cách phối hợp. Hai cơ chế cùng instrument có thể tạo spans, metrics hoặc logs trùng lặp.

### 8.1. Spring Cloud Azure Starter Monitor

Thêm dependency theo BOM Spring Cloud Azure phù hợp với phiên bản Spring Boot:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-monitor</artifactId>
</dependency>
~~~

Starter này cung cấp telemetry cho Spring Boot và tích hợp Azure Monitor OpenTelemetry. Microsoft hướng dẫn import OpenTelemetry BOM và dùng starter monitor; hãy dùng đúng version matrix của Spring Cloud Azure release đang chọn. Không tự thêm các version OpenTelemetry rời rạc nếu BOM đã quản lý chúng.

Cấu hình Application Insights connection string qua environment variable:

~~~bash
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=https://..."
~~~

Không commit connection string vào Git hoặc đóng gói trực tiếp trong container image. Connection string xác định đích telemetry; nó không thay thế cơ chế identity và authorization khi bật Microsoft Entra authenticated ingestion.

### 8.2. Application Insights Java Agent

Với Java Agent, thêm JVM argument trước -jar:

~~~bash
java -javaagent:/opt/azure/applicationinsights-agent.jar -jar app.jar
~~~

Đặt connection string trong môi trường:

~~~bash
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=https://..."
~~~

Java Agent có thể tự instrument HTTP server/client, JDBC, messaging và nhiều thư viện được hỗ trợ. Kiểm tra danh sách instrumentation theo phiên bản agent vì không phải mọi thư viện hoặc custom transport đều được hỗ trợ.

Nếu muốn cấu hình programmatically, Microsoft cung cấp runtime attach mechanism nhưng có điều kiện riêng về JRE, quyền ghi thư mục tạm và vị trí gọi attach. Với container production, JVM argument thường dễ kiểm soát hơn.

## 9. Azure: Managed Identity và Microsoft Entra authentication

Trong production, ưu tiên Managed Identity để xác thực telemetry tới Application Insights thay vì lưu secret lâu dài.

Đối với Application Insights Java Agent hỗ trợ Microsoft Entra authentication:

1. Bật system-assigned hoặc user-assigned Managed Identity cho workload.
2. Gán role **Monitoring Metrics Publisher** ở scope Application Insights resource.
3. Dùng Application Insights Java Agent phiên bản hỗ trợ Entra ingestion (từ 3.2.0 trở lên).
4. Cấu hình authentication theo tài liệu agent.

Ví dụ với system-assigned identity:

~~~bash
APPLICATIONINSIGHTS_AUTHENTICATION_STRING="Authorization=AAD"
~~~

Với user-assigned identity, thêm client ID theo format tài liệu:

~~~bash
APPLICATIONINSIGHTS_AUTHENTICATION_STRING="Authorization=AAD;ClientId=<managed-identity-client-id>"
~~~

Role Monitoring Metrics Publisher có tên chứa Metrics nhưng quyền này cho phép publish telemetry vào Application Insights, không chỉ metrics. Chỉ gán role ở scope resource cần thiết. Kiểm tra phiên bản agent và khả năng Entra auth trước khi tắt local authentication trên resource.

Trong local development, dùng phương thức xác thực được hỗ trợ cho môi trường phát triển. Không đưa client secret vào application.yml chỉ để làm cho telemetry chạy được.

## 10. Azure: resource attributes, sampling và kiểm tra dữ liệu

Đặt service name và resource attributes để Application Map phân biệt nhiều service cùng gửi về một Application Insights resource:

~~~bash
OTEL_SERVICE_NAME="document-api"
OTEL_RESOURCE_ATTRIBUTES="service.namespace=provider-integration,deployment.environment=production,service.version=1.2.0"
~~~

Nếu có nhiều ứng dụng gửi vào cùng resource, cấu hình cloud role name/role instance theo hướng dẫn Azure để Application Map hiển thị đúng topology.

Sampling giúp kiểm soát ingestion. Đừng bật 100% traces mặc định trên production có traffic lớn. Chọn sampling policy phù hợp, giữ quyết định sampling nhất quán giữa các service và kiểm tra ảnh hưởng tới trace completeness.

Sau khi chạy ứng dụng:

1. Gửi request HTTP và thực hiện một thao tác cloud.
2. Mở Application Insights.
3. Kiểm tra Requests, Dependencies, Exceptions, Traces và Metrics.
4. Dùng Application Map để xác minh service/dependency được nhận diện.
5. Chờ vài phút nếu telemetry chưa xuất hiện ngay.

Nếu chỉ thấy request nhưng không thấy dependency, kiểm tra instrumentation cho client thư viện đó. Nếu log có nhưng không gắn trace, kiểm tra MDC/structured logging và trace correlation.

## 11. Google Cloud: chọn OpenTelemetry Collector

Google Cloud Observability gồm Cloud Logging, Cloud Monitoring và Cloud Trace. Hướng tích hợp được Google khuyến nghị cho nhiều môi trường là:

1. Instrument ứng dụng bằng OpenTelemetry SDK hoặc Java Agent.
2. Gửi telemetry theo OTLP tới OpenTelemetry Collector sidecar/agent.
3. Collector nhận, batch và enrich resource attributes.
4. Collector export telemetry tới Google Cloud project qua Telemetry API.

Lợi ích là ứng dụng giữ được format vendor-neutral. Khi chuyển backend hoặc chạy đa cloud, có thể thay collector/exporter mà không phải sửa toàn bộ business code.

Google cung cấp sample Spring Boot Java sử dụng OpenTelemetry Java Agent, OTLP và Collector. Với log, sample ghi structured JSON ra stdout; collector đọc log bằng filelog receiver và gửi cùng traces/metrics tới Google Cloud.

### 11.1. Gắn OpenTelemetry Java Agent

Ví dụ khởi chạy:

~~~bash
JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/opentelemetry-javaagent.jar"
OTEL_SERVICE_NAME="document-api"
OTEL_RESOURCE_ATTRIBUTES="service.namespace=provider-integration,deployment.environment=production"
OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317"
OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
~~~

Port 4317 thường dùng OTLP/gRPC; nếu Collector chỉ mở OTLP/HTTP thì cấu hình endpoint/protocol tương ứng, thường là port 4318. Endpoint trong ví dụ là địa chỉ service nội bộ của Collector, không phải URL công khai của Google Cloud.

Java Agent tự instrument các framework và thư viện được hỗ trợ. Với business metric riêng, vẫn có thể dùng Micrometer Observation/MeterRegistry hoặc OpenTelemetry API và để exporter/collector nhận telemetry theo kiến trúc đã chọn.

### 11.2. Structured logs và trace correlation

Ghi log JSON ra stdout/stderr. Nếu muốn liên kết log với trace, đưa các field theo quy ước Cloud Logging:

- logging.googleapis.com/trace: resource name của trace.
- logging.googleapis.com/spanId: span ID.
- logging.googleapis.com/trace_sampled: true hoặc false.

OpenTelemetry Java Agent có thể đưa span context vào MDC. Logging layout cần đưa trace/span ID vào JSON field tương ứng. Nếu môi trường GKE đã tự thu thập structured logs, không cần cài thêm agent thu thập log trùng lặp.

## 12. Google Cloud: service account và quyền ghi telemetry

Trên workload production, dùng service account gắn với workload thay vì key JSON dài hạn:

- GKE: Workload Identity Federation for GKE.
- Compute Engine: service account gắn với VM.
- Cloud Run: service identity của service.
- Local development: Application Default Credentials (ADC) qua quy trình đăng nhập dành cho developer.

Các role ghi telemetry thường cần:

| Role | Quyền |
|---|---|
| roles/logging.logWriter | Ghi log vào Cloud Logging |
| roles/monitoring.metricWriter | Ghi metrics vào Cloud Monitoring |
| roles/telemetry.tracesWriter | Ghi traces qua Telemetry API |
| roles/serviceusage.serviceUsageConsumer | Dùng quota project khi cần |

Bật các API tương ứng nếu project chưa bật: Cloud Logging, Cloud Monitoring, Cloud Trace và Telemetry API. Việc bật API thường cần quyền quản trị project; runtime service account chỉ cần quyền ghi telemetry tối thiểu.

Không mount service account key JSON vào production container nếu có thể dùng workload identity. Nếu local cần ADC credentials file, chỉ dùng file developer-local và không commit file đó.

## 13. So sánh ba lựa chọn tích hợp

| Tiêu chí | AWS CloudWatch | Azure Monitor | Google Cloud Observability |
|---|---|---|---|
| Metrics với Spring Boot | Micrometer CloudWatch registry, Spring Cloud AWS auto-config | Starter Monitor/OpenTelemetry Distro thu Micrometer metrics | OpenTelemetry SDK/Agent + Collector; có thể export Micrometer qua OTLP |
| Traces | ADOT/OpenTelemetry tới X-Ray | Azure Monitor OpenTelemetry Java Agent/Starter | OpenTelemetry Java Agent + Collector tới Cloud Trace |
| Logs | JSON stdout + CloudWatch Agent/FireLens/collector | Java Agent/Starter hoặc structured logs qua agent | JSON stdout + collector/agent tới Cloud Logging |
| Identity | IAM role/workload identity | Managed Identity + Microsoft Entra ID | Service account/workload identity + ADC |
| Nơi xem | CloudWatch Metrics, Logs, X-Ray, Application Signals | Application Insights, Azure Monitor | Metrics Explorer, Logs Explorer, Trace Explorer |
| Cần chú ý | Custom metric và dimension có chi phí | Sampling, role và connection string | Collector, IAM roles, APIs và resource attributes |

Nếu cần đa cloud hoặc muốn thay backend linh hoạt, OpenTelemetry Collector là lớp trung gian hữu ích. Nếu ứng dụng chỉ chạy trên một cloud và cần tích hợp Spring idiomatic, registry/starter của provider có thể giảm cấu hình.

## 14. Quản lý cấu hình theo profile và môi trường

Không nên bật publisher production khi chạy unit test hoặc local. Tách cấu hình theo Spring profile:

~~~yaml
# application.yml
spring:
  application:
    name: provider-integration

management:
  metrics:
    tags:
      application: provider-integration
~~~

~~~yaml
# application-local.yml
spring:
  cloud:
    aws:
      cloudwatch:
        enabled: false
~~~

~~~yaml
# application-aws.yml
management:
  cloudwatch:
    metrics:
      export:
        namespace: ProviderIntegration
        step: 1m

spring:
  cloud:
    aws:
      cloudwatch:
        enabled: true
        region: ap-southeast-1
~~~

Azure và Google Cloud thường lấy connection string, OTLP endpoint, project ID và resource attributes từ environment/deployment manifest. Không nhét cả ba bộ credentials vào một file cấu hình. Chỉ bật exporter tương ứng với môi trường đang triển khai.

## 15. Dashboard, alert và SLO

Mỗi backend có cách tạo dashboard khác nhau nhưng các tín hiệu nên nhất quán:

- Request throughput và error rate.
- p50/p95/p99 latency.
- JVM heap, GC pause, CPU và thread utilization.
- Database/HTTP/cloud dependency latency.
- Queue age, backlog và dead-letter count nếu ứng dụng dùng messaging.
- Business metric như số document preview thành công.

Ví dụ SLO cho API xử lý tài liệu:

- 99% request hoàn tất dưới 1 giây.
- Tỷ lệ lỗi cuối dưới 0,5% trong cửa sổ 30 phút.
- 99% message bắt đầu xử lý trong vòng 60 giây.

Đây là ngưỡng minh họa. Chọn SLO theo yêu cầu sản phẩm và baseline tải thực tế. Alert nên dựa trên burn rate/error budget và khoảng thời gian đủ dài, tránh paging vì một spike ngắn.

CloudWatch dùng alarms và dashboards; Azure Monitor dùng metric alerts, log alerts và workbooks; Google Cloud dùng alerting policies, dashboards và SLO monitoring. Đặt tên metric, service và operation nhất quán để có thể so sánh khi chạy cùng workload trên nhiều cloud.

## 16. Cardinality, sampling, bảo mật và chi phí

### 16.1. Giữ cardinality thấp

Chỉ dùng label/tag có tập giá trị nhỏ:

- provider: aws, azure, gcp.
- service: s3, blob, pubsub.
- operation: upload, download, send_message.
- outcome: success, error.
- environment: dev, staging, production.

Không dùng request ID, trace ID, user ID, tenant ID, object key hoặc exception message làm metric label. Những giá trị này phù hợp hơn với logs/traces.

### 16.2. Sampling và batch

Trace sampling ảnh hưởng số trace được lưu, không nên làm thay đổi logic nghiệp vụ. Giữ sampling nhất quán trên các service và kiểm tra parent-based propagation. Dùng collector batch processor và retry/queue phù hợp để giảm tác động khi backend tạm thời không khả dụng.

### 16.3. Bảo vệ dữ liệu

- Không ghi token, SAS URL, access key, private key hoặc connection string đầy đủ vào log.
- Không đưa payload nhạy cảm vào span attributes hoặc baggage.
- Giới hạn quyền đọc logs/traces vì telemetry có thể chứa metadata nội bộ.
- Dùng TLS cho OTLP qua mạng không tin cậy.
- Dùng IAM/Managed Identity/service account với quyền ghi tối thiểu.
- Đặt retention và ingestion sampling theo yêu cầu pháp lý, bảo mật và chi phí.

### 16.4. Kiểm soát chi phí

CloudWatch tính phí custom metrics theo metric/dimension; Azure Monitor tính ingestion/retention theo loại dữ liệu và volume; Google Cloud có chi phí theo ingestion, retention và sản phẩm Observability được dùng. Theo dõi volume, sampling, số time series và log verbosity trước khi mở rộng production.

## 17. Kiểm thử tích hợp telemetry

Không cần gửi telemetry production trong unit test. Tách phần business metrics khỏi backend exporter để test bằng registry in-memory:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DocumentMetricsTest {
    @Test
    void recordsPreviewSuccess() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        registry.counter(
                "document.preview.completed",
                "provider", "azure",
                "outcome", "success")
            .increment();

        assertEquals(
                1.0,
                registry.get("document.preview.completed")
                        .tag("provider", "azure")
                        .tag("outcome", "success")
                        .counter()
                        .count());
    }
}
~~~

Integration test nên kiểm tra:

1. Application context khởi động với đúng exporter dependency.
2. Metric có tên và tag dự kiến.
3. Exporter có endpoint, region, namespace hoặc project đúng.
4. Identity của workload có quyền ghi telemetry.
5. Collector nhận OTLP và chuyển tiếp thành công.
6. Log JSON có service name và trace correlation fields.
7. Shutdown flush dữ liệu còn trong buffer.

Có thể dùng LocalStack để kiểm tra một phần AWS client interaction, nhưng nó không chứng minh đầy đủ CloudWatch ingestion/billing semantics. Với Azure/Google, dùng resource test và quyền giới hạn; chạy smoke test có kiểm soát rồi xác minh dữ liệu ở portal.

## 18. Troubleshooting theo dấu hiệu

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CloudWatch không có custom metrics | Thiếu namespace hoặc PutMetricData permission | Kiểm tra namespace, region, IAM role và export log |
| CloudWatch metric xuất hiện trễ | Registry publish theo step | Chờ vài chu kỳ và kiểm tra step |
| CloudWatch bill tăng nhanh | Quá nhiều meter/dimension combinations | Dùng MeterFilter, giảm tag cardinality và loại meter không cần |
| Azure Monitor không nhận telemetry | Sai connection string, role hoặc exporter config | Kiểm tra IngestionEndpoint, Managed Identity và self-diagnostics |
| Azure Application Map gộp nhiều service | Cloud role name không phân biệt | Cấu hình role name/role instance |
| Azure trace bị nhân đôi | Starter và Java Agent cùng instrument | Chỉ giữ một instrumentation path |
| Google Cloud không có metrics/traces | Collector endpoint hoặc exporter sai | Kiểm tra OTLP port/protocol, Collector logs và project |
| Google Cloud báo PermissionDenied | Service account thiếu role | Kiểm tra logging.logWriter, monitoring.metricWriter, telemetry.tracesWriter |
| Google Cloud logs không gắn trace | JSON layout không xuất special trace fields | Kiểm tra MDC và logging.googleapis.com/trace/spanId |
| Metrics có nhưng traces không có | Chưa bật tracing exporter hoặc sampling loại trace | Kiểm tra agent, exporter và sampling |
| Log có nhưng không thấy ở backend | stdout collector/agent chưa cấu hình | Kiểm tra log driver, filelog receiver hoặc agent |
| Exporter tạo tải/queue tăng | Backend chậm hoặc collector không đủ capacity | Bật batch, retry có giới hạn và theo dõi dropped telemetry |
| Local test ghi dữ liệu cloud | Exporter bật trong profile test | Tắt exporter ở local/test và dùng SimpleMeterRegistry |

Khi debug, kiểm tra lần lượt: ứng dụng có tạo meter/span/log không; exporter có nhận dữ liệu không; identity có quyền không; collector có route đúng không; backend có nhận và lưu dữ liệu không.

## 19. Bài tập thực hành và câu hỏi tự kiểm tra

**Tình huống A — AWS CloudWatch:** Một ứng dụng Spring Boot chạy trên EKS. Hãy thêm Micrometer CloudWatch registry, cấu hình namespace, region, IAM role và MeterFilter chỉ publish HTTP/JVM/business metrics. Kiểm tra metric xuất hiện trong CloudWatch và giải thích cách dimension ảnh hưởng chi phí.

**Tình huống B — Azure Monitor:** Một ứng dụng chạy trên Azure App Service. Hãy chọn giữa Spring Cloud Azure Starter Monitor và Application Insights Java Agent; cấu hình connection string, Managed Identity và Monitoring Metrics Publisher role; xác minh Requests, Dependencies và Exceptions trong Application Insights.

**Tình huống C — Google Cloud:** Một ứng dụng chạy trên GKE. Hãy thêm OpenTelemetry Java Agent, cấu hình OTLP endpoint tới Collector sidecar, gán Workload Identity và ba role ghi logs/metrics/traces; xác minh dữ liệu trong Metrics Explorer, Logs Explorer và Trace Explorer.

**Tình huống D — Đa cloud:** Cùng một service được triển khai trên AWS, Azure và GCP. Hãy chuẩn hóa service.name, environment, operation, outcome và business metric để so sánh latency/error rate mà không đưa resource ID vào metric labels.

**Tình huống E — Chi phí tăng:** CloudWatch custom metric tăng mạnh sau khi thêm tag customerId. Hãy giải thích cardinality và dùng MeterFilter/low-cardinality tags để giới hạn time series.

**Tình huống F — Telemetry bị trùng:** Ứng dụng Azure vừa dùng Spring Cloud Azure Starter Monitor vừa chạy Application Insights Java Agent. Hãy xác định cách kiểm tra duplicate instrumentation và chọn một đường tích hợp phù hợp.

**Tình huống G — Collector gián đoạn:** Collector tạm thời mất kết nối với Google Cloud. Hãy thiết kế batch, retry, queue và shutdown flush; nêu giới hạn về memory và dữ liệu có thể mất khi process bị kill.

### Câu hỏi tự kiểm tra

1. **Actuator có tự gửi metrics lên cloud không?** Không; cần Micrometer registry, exporter hoặc collector.
2. **CloudWatch registry dùng dependency nào trong Spring Cloud AWS hiện hành?** micrometer-registry-cloudwatch2.
3. **Property namespace CloudWatch của Spring Cloud AWS 3.x/4.x là gì?** management.cloudwatch.metrics.export.namespace.
4. **Quyền AWS cơ bản để ghi metrics là gì?** cloudwatch:PutMetricData.
5. **Vì sao cần MeterFilter khi publish CloudWatch?** Để giới hạn meter và dimension, giảm số custom metrics có chi phí.
6. **Azure có những đường tích hợp Java/Spring Boot nào?** Spring Cloud Azure Starter Monitor hoặc Application Insights Java Agent; tránh instrument trùng.
7. **Role Azure nào cho phép gửi telemetry vào Application Insights khi dùng Entra auth?** Monitoring Metrics Publisher.
8. **Google khuyến nghị mô hình export nào khi có thể chạy collector?** OpenTelemetry SDK/Java Agent gửi OTLP tới Collector rồi export tới Google Cloud.
9. **Google Cloud cần các role ghi telemetry nào?** Logs Writer, Monitoring Metric Writer và Cloud Telemetry Traces Writer.
10. **Vì sao phải phân biệt OTLP port 4317 và 4318?** 4317 thường dùng gRPC, 4318 dùng HTTP; endpoint/protocol phải khớp receiver.
11. **Có nên dùng request ID làm metric label không?** Không; giá trị duy nhất tạo cardinality cao.
12. **Làm sao kiểm tra export end-to-end?** Tạo traffic, kiểm tra app instrumentation, exporter/collector, IAM và dữ liệu tại portal/backend.

## 20. Tổng kết

Spring Boot cung cấp lớp instrument chung qua Actuator, Micrometer và OpenTelemetry. Khi tích hợp backend cloud, chọn thư viện theo tín hiệu cần xuất và cách triển khai: **Spring Cloud AWS + micrometer-registry-cloudwatch2** cho metrics CloudWatch; **Spring Cloud Azure Starter Monitor hoặc Application Insights Java Agent** cho Azure Monitor; **OpenTelemetry Java Agent/SDK + Collector** cho Google Cloud Observability.

CloudWatch cần namespace, region, IAM PutMetricData và MeterFilter để kiểm soát custom metric/dimension. Azure cần Application Insights resource, connection string, đúng starter/agent và Managed Identity với role Monitoring Metrics Publisher khi dùng Entra authenticated ingestion. Google Cloud cần Collector/OTLP, service account/workload identity, các API và role ghi logs/metrics/traces.

Giữ schema resource attributes nhất quán, không tạo metric label cardinality cao, kiểm soát sampling/ingestion, bảo vệ credentials và kiểm thử từ ứng dụng tới backend. Khi có kiến trúc chuẩn, đội vận hành có thể dùng cùng một bộ dashboard/SLO để đánh giá ứng dụng dù chạy trên AWS, Azure hay Google Cloud.

### Tài liệu tham khảo chính thức

- [Spring Cloud AWS 4.1 — CloudWatch metrics](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html#cloudwatch-metrics)
- [Spring Cloud AWS 3.4 — CloudWatch metrics](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html)
- [Micrometer — CloudWatch registry](https://docs.micrometer.io/micrometer/reference/implementations/cloudwatch.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Microsoft Learn — Enable Azure Monitor OpenTelemetry for Java](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=java-native)
- [Microsoft Learn — Azure Monitor with Spring Boot](https://learn.microsoft.com/en-us/azure/azure-monitor/app/java-spring-boot)
- [Microsoft Learn — Configure Application Insights OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration)
- [Microsoft Learn — Microsoft Entra authentication for Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-ad-authentication)
- [Google Cloud — Java instrumentation sample](https://docs.cloud.google.com/stackdriver/docs/instrumentation/setup/java)
- [Google Cloud — Collector-based instrumentation samples](https://docs.cloud.google.com/stackdriver/docs/instrumentation/setup/sample-overview)
- [Google Cloud — Use the Google-Built OpenTelemetry Collector](https://docs.cloud.google.com/stackdriver/docs/otlp)
