# Resource attributes trong OpenTelemetry và Spring Boot

Khi xem distributed traces của một hệ thống Spring Boot, đội vận hành cần biết span được tạo bởi dịch vụ nào, phiên bản triển khai nào, môi trường nào và instance nào. Nếu spans chỉ hiện tên thao tác mà không có danh tính nguồn phát telemetry, việc lọc theo service hoặc đối chiếu với một lần rollout sẽ rất khó. **Resource attributes** giải quyết phần nhận diện đó: chúng mô tả **nguồn tạo telemetry**, chẳng hạn ứng dụng, process, máy chủ, container hoặc workload đang phát ra spans, metrics hay logs.

Trong module **SPRING_BOOT_OBSERVABILITY**, resource attributes là một phần của thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Chúng cần được thiết kế cùng propagation ngữ cảnh, tag/cardinality, exporter và sampling để khi điều tra lỗi hoặc độ trễ, các tín hiệu có thể được nhóm theo đúng service, môi trường và phiên bản.

Bài thuộc chương **OpenTelemetry**, tập trung vào **Resource attributes**: mô hình Resource, các thuộc tính service và runtime, cách cấu hình qua biến môi trường/SDK, tích hợp với Spring Boot và Micrometer Tracing, kiểm thử metadata, bảo vệ dữ liệu và xử lý sai lệch giữa traces, metrics và logs.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Resource trong OpenTelemetry và phân biệt resource attributes với span attributes, baggage, instrumentation scope và metric labels.
2. Chọn các thuộc tính định danh service, version, environment và instance theo Semantic Conventions.
3. Cấu hình Resource attributes qua OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES hoặc OpenTelemetry SDK.
4. Hiểu cách Resource được gắn vào telemetry và vì sao nó không phải metadata per-request.
5. Kết hợp Resource attributes trong Spring Boot/Micrometer Tracing mà không tạo nhiều OpenTelemetry SDK riêng.
6. Kiểm tra Resource trong OTLP payload, Collector và backend; xử lý merge/override khi nhiều nguồn cung cấp thuộc tính.
7. Kiểm soát cardinality, dữ liệu nhạy cảm và tính nhất quán giữa traces, metrics và logs.

## 1. Resource là gì?

Trong OpenTelemetry, **Resource** mô tả thực thể phát ra telemetry. Một ứng dụng Spring Boot chạy trong container có thể có Resource attributes như:

| Attribute | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| service.name | order-service | Tên logic của dịch vụ |
| service.namespace | commerce | Nhóm/namespace của service |
| service.version | 2.4.1 | Phiên bản ứng dụng đang chạy |
| service.instance.id | pod-7d9c8f-abc12 | Định danh một instance cụ thể |
| deployment.environment.name | production | Môi trường triển khai |
| host.name | node-03 | Tên host nếu được thu thập và phù hợp |
| cloud.region | ap-southeast-1 | Vùng cloud |
| k8s.namespace.name | commerce-prod | Namespace Kubernetes |
| k8s.pod.name | order-service-7d9c8f-abc12 | Pod phát telemetry |

Ví dụ minh họa một Resource:

~~~text
Resource:
  service.namespace = commerce
  service.name = order-service
  service.version = 2.4.1
  service.instance.id = order-service-7d9c8f-abc12
  deployment.environment.name = production
  cloud.region = ap-southeast-1
~~~

Resource thường được gắn ở cấp TracerProvider, MeterProvider hoặc LoggerProvider trong OpenTelemetry SDK; telemetry data do provider đó phát ra mang thông tin Resource tương ứng. Nhờ vậy, backend có thể lọc spans, metrics và logs theo service/instance mà không phải thêm các giá trị ấy vào từng span thủ công.

### 1.1. Resource trả lời câu hỏi “ai phát ra telemetry?”

- **Resource attributes:** ứng dụng hoặc runtime nào phát telemetry? Ví dụ service.name=order-service, service.version=2.4.1.
- **Span attributes:** thao tác cụ thể này đã làm gì? Ví dụ http.request.method=POST, http.route=/orders/{id}, db.system=postgresql.

Một request có thể tạo hàng chục spans nhưng Resource của chúng thường giống nhau vì cùng phát ra từ một service instance. Span attributes thay đổi theo từng thao tác.

### 1.2. Resource không phải business context

Không đặt order.id, customer.email, request ID hoặc trạng thái từng đơn hàng thành Resource attributes. Những giá trị đó mô tả từng request/transaction, không mô tả nguồn phát telemetry. Chúng cũng có thể thay đổi ở mỗi thao tác, làm sai nghĩa Resource và tăng chi phí indexing/cardinality.

## 2. Phân biệt Resource attributes với các loại metadata khác

| Loại | Phạm vi | Ví dụ | Có thay đổi mỗi request? |
| --- | --- | --- | --- |
| Resource attributes | Nguồn phát telemetry/provider | service.name=order-service | Thường không |
| Instrumentation scope | Thư viện/instrumentation tạo telemetry | Tên instrumentation và version | Thường không |
| Span attributes | Một thao tác/span | http.request.method=POST | Có thể |
| Baggage | Context có thể truyền sang downstream | orders.channel=web | Có thể |
| Metric labels/attributes | Nhận dạng time series hoặc metric point | http.response.status_code=500 | Có thể, nhưng cần giới hạn cardinality |
| Log fields | Một log event | error.code=INVENTORY_TIMEOUT | Có thể |

### 2.1. Resource và Instrumentation Scope

Resource cho biết **thực thể phát telemetry**. Instrumentation Scope cho biết **thư viện hoặc instrumentation nào tạo ra telemetry**. Ví dụ, một span có thể được tạo bởi instrumentation của Spring Web, JDBC hoặc một thư viện nghiệp vụ. Các spans này cùng thuộc Resource order-service nhưng scope có thể khác nhau.

Không dùng instrumentation.scope.name thay cho service.name: chúng trả lời hai câu hỏi riêng.

### 2.2. Resource và span attributes

~~~text
Resource:
  service.name = order-service
  service.version = 2.4.1

Span A:
  name = POST /orders
  http.request.method = POST
  http.route = /orders

Span B:
  name = inventory.reserve
  dependency.name = inventory
~~~

Không lặp lại service.name thành span attribute chỉ để backend có thể lọc service nếu Resource đã được gắn đúng. Tuy nhiên, một số hệ thống lưu trữ hoặc export có thể biến đổi cấu trúc; kiểm tra output thực tế của Collector/backend trước khi xây dựng query.

### 2.3. Resource không phải baggage

Resource thường được xác lập theo vòng đời provider và không thay đổi theo request. Baggage mang một số key-value trong trace context và có thể được propagate qua HTTP. Không đưa Resource attributes vào baggage để truyền service name xuống downstream: mỗi service nên tự xác định danh tính Resource của chính mình.

Ví dụ, service.name=order-service thuộc Resource của order-service. Khi gọi inventory-service, HTTP request tiếp tục trace context, nhưng Resource của spans do inventory-service phát ra phải là service.name=inventory-service.

## 3. Các Resource attributes quan trọng cho service

OpenTelemetry Semantic Conventions định nghĩa những key chuẩn để các backend và công cụ hiểu thống nhất.

### 3.1. service.name

service.name là định danh logic chính của dịch vụ:

- Ổn định qua các replica/instances của cùng một service.
- Không thay đổi theo request, user hoặc pod.
- Nên được quy định trong kiến trúc và dùng thống nhất giữa logs, metrics, traces.
- Tránh tên quá chung như java-app hoặc unknown_service nếu ứng dụng có danh tính rõ.

Ví dụ: mọi replica của order-service trong production đều dùng service.name=order-service.

### 3.2. service.namespace

service.namespace giúp nhóm các services trong một miền:

~~~text
service.namespace = commerce
service.name = order-service
~~~

Kết hợp hai thuộc tính giúp phân biệt các service trùng tên trong những miền/hệ thống khác nhau nếu tổ chức có quy ước cho phép. Đây là namespace logic của service, không nhất thiết bằng Kubernetes namespace.

### 3.3. service.version

service.version nên thể hiện phiên bản phát hành có thể đối chiếu với artifact/release, ví dụ 2.4.1. Có thể dùng version git SHA hoặc build identifier nếu hệ thống có quy tắc rõ. Version cần ổn định trong vòng đời process. Không sinh version mới cho từng request hoặc đưa toàn bộ commit message vào Resource.

### 3.4. service.instance.id

service.instance.id phân biệt **một instance cụ thể** giữa nhiều replica cùng service.name. Giá trị phải duy nhất trong phạm vi service theo yêu cầu vận hành và ổn định trong vòng đời instance. Trong Kubernetes, pod name/UID hoặc một định danh instance được nền tảng cấp có thể phù hợp tùy chính sách.

### 3.5. deployment.environment.name

Thuộc tính Semantic Conventions hiện hành là deployment.environment.name, ví dụ development, staging, production. Một số hệ thống cũ có thể dùng key deployment.environment; khi chuyển đổi cần xem version semantic conventions và hỗ trợ của backend. Tránh cùng lúc phát ra hai key không thống nhất nếu không có kế hoạch tương thích.

### 3.6. Thuộc tính host, container, Kubernetes và cloud

| Nhóm | Attribute ví dụ | Ý nghĩa |
| --- | --- | --- |
| Host | host.name, host.id | Máy chủ chạy process |
| Process | process.pid, process.runtime.name | Tiến trình/JVM |
| Container | container.id, container.image.name | Container runtime |
| Kubernetes | k8s.cluster.name, k8s.namespace.name, k8s.pod.name | Workload trong cluster |
| Cloud | cloud.provider, cloud.region, cloud.availability_zone | Hạ tầng cloud |

Không phải mọi thuộc tính đều có trên mọi runtime. Chỉ thu thập khi detector có thể xác định đáng tin và tổ chức có nhu cầu. Tránh thêm metadata máy móc khiến Resource quá lớn hoặc có thông tin hạ tầng nhạy cảm.

## 4. Resource được tạo và gắn vào telemetry như thế nào?

~~~mermaid
flowchart TD
    Config["Environment / SDK configuration"] --> Resource["Resource attributes"]
    Detect["Resource detectors<br/>process, host, container, cloud"] --> Merge["Merge resources"]
    Resource --> Merge
    Merge --> Providers["TracerProvider / MeterProvider / LoggerProvider"]
    Providers --> Trace["Spans"]
    Providers --> Metrics["Metrics"]
    Providers --> Logs["Logs"]
    Trace --> Export["OTLP / exporter"]
    Metrics --> Export
    Logs --> Export
~~~

Resource thường được khởi tạo cùng provider và được dùng cho telemetry do provider đó phát ra. Một số thuộc tính đến từ cấu hình ứng dụng; một số đến từ detector của runtime/deployment. Khi nhiều nguồn cùng cung cấp một key, phải hiểu quy tắc merge/override của SDK và thứ tự áp dụng.

### 4.1. Resource là metadata cấp provider, không phải scope động

Không nên tạo một TracerProvider mới cho mỗi request để gắn service.version hoặc tenant.id. Làm vậy vừa sai mô hình vừa có thể tạo tài nguyên lớn, exporter/thread pool trùng lặp và mất kiểm soát shutdown.

Resource thường được thiết lập lúc khởi động ứng dụng. Nếu một tác vụ cần metadata khác theo request, hãy xem xét span attributes hoặc baggage đã được kiểm soát.

### 4.2. Tính bất biến và cập nhật Resource

Trong OpenTelemetry SDK, Resource về cơ bản là metadata bất biến sau khi provider đã được cấu hình. Muốn đổi service.version sau deployment, thông thường cần một process mới/provider mới với Resource mới, chứ không cập nhật Resource trên mỗi span.

Điều này phù hợp với cách triển khai immutable: mỗi release chạy với version của chính nó, còn các instance cùng release chia sẻ service.version.

## 5. Cấu hình Resource attributes trong Spring Boot

Với Spring Boot sử dụng Micrometer Tracing bridge sang OpenTelemetry, cần bảo đảm ứng dụng chỉ dùng **một tracing infrastructure được quản lý thống nhất**. Dependency minh họa cho Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Giữ dependency versions theo Spring Boot BOM. Việc thêm OpenTelemetry SDK hoặc exporter không có nghĩa Spring Boot sẽ tự sử dụng mọi bean SDK mà bạn tự tạo; cần hiểu auto-configuration đang tạo provider/tracer nào.

### 5.1. Dùng OTEL_SERVICE_NAME

OpenTelemetry SDK Autoconfigure hỗ trợ biến môi trường:

~~~text
OTEL_SERVICE_NAME=order-service
~~~

Biến này dùng để đặt service.name khi SDK autoconfigure hỗ trợ và được cấu hình trong ứng dụng. Nó có ưu tiên đối với service.name so với cùng key trong OTEL_RESOURCE_ATTRIBUTES theo quy ước SDK autoconfigure.

### 5.2. Dùng OTEL_RESOURCE_ATTRIBUTES

Ví dụ:

~~~text
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,service.version=2.4.1,deployment.environment.name=staging,service.instance.id=order-service-pod-abc12
~~~

Đây là cú pháp danh sách key-value phân tách bằng dấu phẩy theo quy ước OTEL SDK. Giá trị cần encode theo quy định của biến môi trường/protocol nếu có ký tự đặc biệt; tránh đưa chuỗi có dấu phẩy hoặc ký tự không an toàn vào value mà không kiểm tra parser.

Trong môi trường triển khai có thể đặt các biến qua container environment, deployment manifest hoặc secret/config management. Không ghi danh sách giá trị khác nhau cho từng request.

**Điều kiện quan trọng:** OTEL_SERVICE_NAME và OTEL_RESOURCE_ATTRIBUTES được đọc bởi OpenTelemetry SDK Autoconfigure hoặc lớp cấu hình có hỗ trợ các biến chuẩn này. Nếu ứng dụng đang cấu hình SDK/provider thủ công hoặc dùng một auto-configuration khác, hãy xác minh chúng thực sự được áp dụng; đừng suy ra chỉ vì biến đã được khai báo ở container.

### 5.3. Ví dụ application.yml và deployment env

Có thể giữ tên ứng dụng trong Spring Boot:

~~~yaml
spring:
  application:
    name: order-service
~~~

Và đặt thuộc tính deployment qua biến môi trường:

~~~yaml
env:
  - name: OTEL_SERVICE_NAME
    value: order-service
  - name: OTEL_RESOURCE_ATTRIBUTES
    value: service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production
~~~

Đoạn env là ví dụ cấu trúc khai báo environment trong manifest container/Kubernetes, không phải root-level application.yml của Spring Boot. Nếu quản lý cấu hình bằng Docker Compose hoặc platform khác, cách khai báo khác nhưng các biến môi trường giữ nguyên tên.

### 5.4. Không nhầm Resource attributes với management.metrics.tags

management.metrics.tags.* của Spring Boot thêm common tags cho metrics registry. Chúng **không mặc nhiên cấu hình OpenTelemetry Resource cho spans/logs**. Ngược lại, Resource attributes cũng không nhất thiết trở thành metric labels trong mọi registry/export format.

Nếu cần cùng danh tính service ở metrics và traces, cấu hình cả hai theo một nguồn release/deployment thống nhất và xác minh output thực tế. Tránh sửa riêng lẻ ở từng nơi dẫn đến service.name=order-service nhưng metric tag application=orders-api.

## 6. Tạo Resource trực tiếp bằng OpenTelemetry Java SDK

Khi xây dựng ứng dụng/thư viện sử dụng OpenTelemetry SDK trực tiếp hoặc viết ví dụ độc lập, có thể tạo Resource:

~~~java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;

public class ResourceConfigurationExample {
    public static SdkTracerProvider createTracerProvider() {
        Resource serviceResource = Resource.create(
                Attributes.of(
                        AttributeKey.stringKey("service.namespace"), "commerce",
                        AttributeKey.stringKey("service.name"), "order-service",
                        AttributeKey.stringKey("service.version"), "2.4.1",
                        AttributeKey.stringKey("deployment.environment.name"), "staging"
                )
        );

        Resource resource = Resource.getDefault().merge(serviceResource);

        return SdkTracerProvider.builder()
                .setResource(resource)
                .build();
    }
}
~~~

Ví dụ này thể hiện API Resource ở **OpenTelemetry SDK độc lập**. Resource.getDefault() cung cấp các thuộc tính mặc định mà SDK biết cách thu thập; merge(serviceResource) kết hợp với thuộc tính service tùy chỉnh. Với cách merge của SDK Java, các giá trị từ Resource được merge vào có thể ghi đè key trùng nhau trong Resource ban đầu.

**Không chèn đoạn này vào Spring Boot một cách máy móc** nếu Boot/Micrometer đã tạo SdkTracerProvider. Tạo thêm provider thứ hai có thể khiến spans từ code khác nhau đi vào các exporter/resources khác nhau, gây khó tìm trace. Trong ứng dụng Boot, ưu tiên cơ chế cấu hình mà auto-configuration đang quản lý; chỉ tự cấu hình SDK khi bạn thực sự sở hữu toàn bộ tracing lifecycle.

### 6.1. Phối hợp detector và Resource tùy chỉnh

Resource detector có thể lấy thông tin từ process, host, container, Kubernetes hoặc cloud. Hãy:

1. Chọn detector phù hợp môi trường chạy.
2. Đặt các thuộc tính nhận diện service bằng cấu hình do ứng dụng/release cung cấp.
3. Merge theo thứ tự có chủ đích, tránh detector ghi đè service.name bằng giá trị chung.
4. Kiểm tra Resource cuối cùng trước khi export.
5. Chỉ giữ các thuộc tính runtime thực sự cần cho vận hành.

Không bật tất cả detector chỉ vì chúng có sẵn. Việc đọc metadata từ cloud/container có thể cần quyền truy cập hoặc tạo thêm traffic tới metadata endpoint.

## 7. Resource attributes qua các service và môi trường

Một trace nhiều service có thể chứa các Resource khác nhau cho từng nhóm spans.

~~~text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736

Resource: service.name=order-service
  Span: POST /orders
  Span: orders.checkout
  Span: HTTP POST inventory (CLIENT)

Resource: service.name=inventory-service
  Span: POST /reservations (SERVER)
  Span: db.query

Resource: service.name=payment-service
  Span: POST /charges (SERVER)
~~~

Trace context nối spans bằng trace ID và parent ID. Resource attributes xác định service phát ra từng span. **Không propagate Resource từ upstream sang downstream**: inventory-service phải có service.name=inventory-service, không phải order-service.

### 7.1. Mỗi replica dùng cùng service.name nhưng instance khác nhau

| Attribute | Pod A | Pod B | Pod C |
| --- | --- | --- | --- |
| service.name | order-service | order-service | order-service |
| service.version | 2.4.1 | 2.4.1 | 2.4.1 |
| service.instance.id | order-pod-a | order-pod-b | order-pod-c |
| deployment.environment.name | production | production | production |

Nếu rollout phiên bản 2.5.0, những instance mới dùng service.version=2.5.0. Nhóm vận hành có thể so sánh lỗi/latency giữa các phiên bản và instance.

### 7.2. Service name không phải hostname

service.name đại diện service logic. host.name/service.instance.id đại diện máy hoặc instance chạy. Nếu dùng hostname làm service.name, mỗi replica có thể bị backend phân loại thành một service khác, khiến dashboard và trace search bị phân mảnh.

## 8. Resource, logs và metrics

Resource attributes có thể được chia sẻ về mặt ngữ nghĩa giữa traces, metrics và logs nếu mỗi signal pipeline hỗ trợ và được cấu hình tương thích. Tuy nhiên, cách mã hóa/lưu trữ có thể khác nhau theo exporter/backend.

~~~mermaid
flowchart TD
    App["Spring Boot application"] --> Resource["Resource identity<br/>service.name/version/environment"]
    Resource --> Trace["Traces / spans"]
    Resource --> Metrics["Metrics"]
    Resource --> Logs["Logs"]
    Trace --> OTLP["OTLP / Collector"]
    Metrics --> Registry["Micrometer registry / exporter"]
    Logs --> LogExport["Log pipeline"]
    OTLP --> TraceStore["Trace backend"]
    Registry --> MetricsStore["Metrics backend"]
    LogExport --> LogStore["Log backend"]
    TraceStore -. "service + time + traceId" .-> Investigation["Cross-signal investigation"]
    MetricsStore -. "service + environment" .-> Investigation
    LogStore -. "service + traceId" .-> Investigation
~~~

### 8.1. Resource attributes và Micrometer metrics

Micrometer metrics thường có common tags như application, region, environment. Một OpenTelemetry metrics exporter có thể gắn Resource vào metric data theo mô hình OTel, trong khi Prometheus scrape thường biểu diễn labels theo cách riêng của registry/exporter. Vì vậy:

- Không giả định service.name luôn xuất thành label Prometheus nếu registry không cấu hình mapping đó.
- Không gắn service.instance.id làm label nếu hệ thống scrape/target đã cung cấp instance, trừ khi có lý do cần thiết.
- Giữ metric labels ít và ổn định; Resource identity không phải lý do để thêm nhiều label động.
- Dùng một nguồn cấu hình deployment để tránh chênh service/version/environment giữa signals.

### 8.2. Resource attributes và logs

OpenTelemetry Logs Data Model cũng hỗ trợ Resource. Nếu logs được export qua OTLP với SDK/agent phù hợp, Resource có thể giúp nhóm log theo service.name và service.version. Nếu ứng dụng dùng Logback/Log4j2 gửi log qua pipeline độc lập, các trường service/environment phải được cấu hình trong appender/agent/collector tương ứng; không mặc nhiên được copy từ OTel Resource.

### 8.3. Correlation không yêu cầu copy Resource vào mọi log line

Backend có thể nhóm log theo Resource mà không cần lặp service.name trong message text. Với file logs truyền thống, có thể cần structured fields hoặc MDC để hỗ trợ query. Tránh ghi lặp metadata lớn hoặc không nhất quán ở cả message và Resource.

## 9. Cardinality, privacy và những thuộc tính không nên đưa vào Resource

Resource attributes thường có số tổ hợp nhỏ hơn span attributes, nhưng vẫn có thể làm tăng số nhóm dữ liệu và chi phí. service.instance.id thay đổi theo replica/rollout; điều đó có thể cần cho traces nhưng khi chuyển sang metric labels có thể làm số series nhân theo instance.

### 9.1. Dữ liệu phù hợp

| Thuộc tính | Đánh giá |
| --- | --- |
| service.name | Cần có, ổn định |
| service.version | Hữu ích để phân tích rollout |
| deployment.environment.name | Hữu ích nếu giá trị được chuẩn hóa |
| service.namespace | Hữu ích khi nhóm service |
| service.instance.id | Hữu ích cho điều tra instance cụ thể; xem xét cardinality ở metrics |
| cloud.region | Hữu ích nếu vùng được chuẩn hóa |

### 9.2. Không phù hợp

Không đặt các giá trị sau thành Resource attributes:

- user.id, customer.email, số điện thoại hoặc thông tin định danh cá nhân.
- order.id, request.id, trace.id hoặc ID thay đổi theo từng request.
- Access token, cookie, password, API key hoặc dữ liệu xác thực.
- Request body, response body, danh sách item hoặc SQL chứa dữ liệu.
- Timestamps của mỗi request hoặc giá trị ngẫu nhiên tạo cho từng span.

Resource gắn với nhiều telemetry data của process. Một giá trị nhạy cảm được đưa vào Resource có thể bị lặp ở số lượng lớn spans, metrics hoặc logs và được giữ trong backend lâu dài.

### 9.3. Resource attributes và metric cardinality

Giả sử một metric có 4 values của environment, 5 values của region, 30 instances và 10 routes. Nếu mọi tổ hợp xuất hiện, số series có thể lên đến:

\[
4 \times 5 \times 30 \times 10 = 6.000
\]

Đây chỉ là mô hình đơn giản để minh họa chi phí tổ hợp labels. Hãy tránh tự động biến mọi Resource attribute thành metric label. Đặc biệt, instance ID và pod ID có thể làm series tăng khi autoscaling/rollout.

## 10. Kiểm tra Resource attributes thực tế

Đừng chỉ nhìn biến môi trường rồi khẳng định backend đã nhận đúng Resource. Kiểm tra từ SDK tới OTLP payload/Collector/backend.

### 10.1. Xem trong Collector debug output

Với Collector có debug exporter trong môi trường thử nghiệm, Resource có thể được hiển thị cùng các spans:

~~~text
ResourceSpans:
  Resource:
    service.name: order-service
    service.namespace: commerce
    service.version: 2.4.1
    deployment.environment.name: staging
  ScopeSpans:
    Spans:
      Span #0
        Name: POST /orders
~~~

Tên và cách trình bày output phụ thuộc phiên bản Collector/debug exporter. Mục tiêu là xác nhận Resource của các spans thật có các key/value mong muốn.

### 10.2. Kiểm tra trong backend trace

Chọn một trace đã export:

1. Mở span root của service vào.
2. Kiểm tra service.name, service.version, environment và instance.
3. Mở span thuộc service downstream để xác nhận Resource đổi sang service đó.
4. Đối chiếu release/version với deployment thực tế.
5. Kiểm tra không có PII/secret hoặc key tùy ý trong Resource.

Nếu backend chỉ hiển thị một số trường Resource, có thể do UI chỉ chọn các key mặc định hoặc backend không index tất cả. Kiểm tra OTLP payload/Collector output trước khi kết luận SDK không gửi attributes.

### 10.3. Resource của metrics và logs

- Prometheus: xem labels thật trên series scrape; đừng giả định mọi Resource key thành label.
- OTLP metrics: kiểm tra ResourceMetrics trong collector/debug view.
- OTLP logs: kiểm tra ResourceLogs nếu logging pipeline sử dụng OTLP.
- Logs qua stdout/file: kiểm tra structured fields, MDC hoặc collector agent đang gắn service identity.

## 11. Kiểm thử Resource configuration

Nên kiểm thử riêng việc tạo Resource và tích hợp export. Unit test có thể xác nhận key/value trong SDK; integration test xác nhận Resource thực tế xuất tới Collector.

### 11.1. Unit test với OpenTelemetry SDK Resource

~~~java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.sdk.resources.Resource;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ServiceResourceTest {
    @Test
    void containsExpectedServiceIdentity() {
        Resource resource = Resource.builder()
                .put("service.namespace", "commerce")
                .put("service.name", "order-service")
                .put("service.version", "2.4.1")
                .put("deployment.environment.name", "staging")
                .build();

        assertEquals("commerce", resource.getAttributes()
                .get(AttributeKey.stringKey("service.namespace")));
        assertEquals("order-service", resource.getAttributes()
                .get(AttributeKey.stringKey("service.name")));
        assertEquals("2.4.1", resource.getAttributes()
                .get(AttributeKey.stringKey("service.version")));
    }
}
~~~

Test này kiểm tra Resource object được tạo trong code. Nó không chứng minh Spring Boot đã dùng Resource đó hoặc OTLP exporter gửi nó đi.

### 11.2. Test merge/override

Khi cấu hình nhiều nguồn Resource, viết test để kiểm tra key trùng được merge theo thứ tự định trước. Ví dụ Resource từ detector có service.name=unknown_service, còn Resource tùy chỉnh có service.name=order-service; nếu Resource tùy chỉnh được merge sau và semantics SDK cho phép giá trị bên phải ghi đè, kết quả phải là tên service đã định.

Không mặc định rằng thứ tự nguồn luôn giống nhau ở mọi framework. Kiểm tra provider/autoconfiguration thật trước khi dựa vào precedence.

### 11.3. Integration test với Collector

1. Chạy một service có OTEL_SERVICE_NAME=order-service.
2. Cấu hình OTEL_RESOURCE_ATTRIBUTES gồm namespace, version và environment.
3. Gửi một request tạo span.
4. Nhận OTLP data ở Collector test/debug exporter.
5. Assert Resource attributes đã xuất hiện với đúng values.
6. Khởi động inventory-service với tên riêng và xác minh Resource của service đó không bị lấy từ order-service.
7. Đối chiếu logs/metrics identity với cấu hình deployment.

Test này xác minh pipeline thật; unit test Resource object không thay thế được nó.

## 12. Troubleshooting Resource attributes

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Backend hiện unknown_service | Thiếu service.name hoặc biến môi trường không được SDK đọc | Kiểm tra OTEL_SERVICE_NAME, SDK autoconfigure và Resource export |
| Tất cả pods có tên service khác nhau | Đã gán pod/hostname vào service.name | Dùng tên logic ổn định cho service, instance ID riêng |
| Downstream có Resource của upstream | Copy Resource/baggage sai hoặc cấu hình service name không riêng | Mỗi process tự xác định Resource của mình |
| service.version không đúng release | Env/config không theo artifact đang chạy | Gắn version từ build/deployment metadata |
| Resource attribute thiếu trong backend UI | Backend không hiển thị/index field hoặc Collector biến đổi | Kiểm tra OTLP Resource trước backend |
| deployment.environment.name và key cũ lẫn lộn | Nhiều version semantic conventions/cấu hình | Chuẩn hóa key và migration |
| Resource có PII/secret | Copy nhầm baggage/request data hoặc detector không phù hợp | Chặn ở nguồn, xóa/rotate, đánh giá bản sao telemetry |
| Metric labels tăng mạnh theo instance | Tự động map mọi Resource attribute thành labels | Chọn tags cần thiết; bỏ instance/pod label nếu không cần |
| Traces đúng nhưng logs sai service | Log pipeline có cấu hình identity riêng | Đồng bộ service identity giữa logging appender/agent và OTel |
| Biến OTEL_RESOURCE_ATTRIBUTES không có tác dụng | SDK không dùng Autoconfigure hoặc cấu hình khác ghi đè | Xác minh provider và Resource cuối cùng |
| Hai provider phát hai danh tính khác nhau | Tạo SDK/provider riêng hoặc nhiều auto-configuration | Dùng một tracing lifecycle thống nhất |

### 12.1. Quy trình kiểm tra theo lớp

1. **Deployment:** env vars/config map có đúng giá trị ở container đang chạy?
2. **SDK:** provider có đọc biến chuẩn hoặc cấu hình Resource không?
3. **Merge:** có detector/resource khác ghi đè key không?
4. **Instrumentation:** spans/metrics/logs được phát từ provider nào?
5. **Exporter:** OTLP payload có chứa Resource mong đợi không?
6. **Collector:** processor có thêm, đổi hoặc xóa attributes không?
7. **Backend/UI:** query và cách hiển thị có hỗ trợ các fields đó không?

Không sửa span names hoặc traceparent để chữa lỗi service.name. Resource identity và trace context là hai phần khác nhau.

## 13. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| service.name ổn định | Tất cả replicas của cùng logical service dùng cùng tên |
| service.namespace nhất quán | Namespace logic theo quy ước tổ chức |
| service.version chính xác | Khớp release/artifact đang chạy |
| service.instance.id phân biệt instance | Không thay đổi theo từng request |
| Environment được chuẩn hóa | development, staging, production theo một quy ước |
| Detector phù hợp runtime | Không thu thập metadata không cần thiết |
| Merge precedence đã xác minh | Unit/integration test cho keys trùng |
| Không có PII/secrets | Security review và kiểm tra payload |
| Resource không bị copy thành baggage | Mỗi service tự khai báo identity |
| Metrics labels có cardinality kiểm soát | Không tự map mọi Resource key thành label |
| Logs/traces/metrics identity đồng bộ | Query được cùng service/version/environment |
| SDK/provider không bị tạo trùng | Một lifecycle được quản lý rõ ràng |
| Collector/backend giữ Resource đúng | Kiểm tra payload và query ở môi trường thật |
| Version upgrade có regression test | Semantic convention và property được xác minh |

## 14. Bài thực hành: chuẩn hóa Resource cho hệ thống order

**Bối cảnh:** hệ thống có order-service, inventory-service và payment-service, triển khai nhiều replica trên Kubernetes ở staging và production. Dashboard đang hiển thị các tên service không nhất quán và đội vận hành không lọc được trace theo release.

**Nhiệm vụ:**

1. Đề xuất Resource schema thống nhất với service.namespace, service.name, service.version, service.instance.id và deployment.environment.name.
2. Chọn giá trị service name ổn định cho từng service; không dùng pod name làm service.name.
3. Thiết lập OTEL_SERVICE_NAME và OTEL_RESOURCE_ATTRIBUTES trong môi trường thử nghiệm.
4. Tạo một Resource Java SDK để kiểm tra các key/value, sau đó giải thích vì sao không nên tự tạo provider thứ hai trong Spring Boot.
5. Chạy order-service gọi inventory-service; xác minh các spans có cùng trace ID nhưng Resource service.name khác nhau.
6. Kiểm tra Resource attributes ở Collector và trace backend; xác nhận version/environment phù hợp deployment.
7. So sánh metrics labels và log fields; xác định field nào không được tự động copy từ Resource.
8. Thử cấu hình sai service.name hoặc để SDK nhận unknown_service; xây dựng quy trình phát hiện và sửa.
9. Thêm test cho merge precedence và kiểm tra không có user.id, email, token hoặc request ID trong Resource.
10. Ước lượng tác động cardinality nếu đưa service.instance.id vào mọi metric labels và giải thích cách giới hạn.

**Kết quả mong đợi:** một Resource schema, cấu hình Spring Boot/deployment, unit test Resource, integration test OTLP, sơ đồ trace nhiều service cùng Resource riêng và checklist vận hành khi thay đổi version/deployment.

## 15. Ghi nhớ

**Resource attributes mô tả nguồn phát telemetry**: service nào, phiên bản nào, instance và môi trường nào. service.name nên là tên logic ổn định; service.version xác định release; service.instance.id phân biệt replica; environment/host/cloud/Kubernetes attributes bổ sung ngữ cảnh runtime khi cần.

Resource khác span attributes, instrumentation scope, baggage, MDC và metric labels. Hãy cấu hình Resource ở provider/SDK hoặc qua các biến môi trường chuẩn OpenTelemetry khi SDK hỗ trợ, kiểm tra thứ tự merge, và không tạo một provider riêng lẻ trong Spring Boot nếu auto-configuration đã quản lý tracing lifecycle.

Để observability nhất quán, cùng một deployment metadata cần được phản ánh đúng trong traces, metrics và logs, nhưng mapping sang mỗi signal phải được kiểm tra riêng. Giữ Resource nhỏ, ổn định, không chứa PII/secrets hoặc ID theo request; kiểm thử từ cấu hình đến OTLP payload và backend thay vì chỉ nhìn biến môi trường.

**Tài liệu tham khảo:**

- [OpenTelemetry — Resources](https://opentelemetry.io/docs/concepts/resources/)
- [OpenTelemetry — Resource SDK](https://opentelemetry.io/docs/specs/otel/resource/sdk/)
- [OpenTelemetry — Semantic Conventions: Service](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [OpenTelemetry — SDK Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
