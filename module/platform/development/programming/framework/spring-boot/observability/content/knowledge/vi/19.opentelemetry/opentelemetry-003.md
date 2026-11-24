# OpenTelemetry Resource

Khi một hệ thống Spring Boot có hàng chục instance chạy ở nhiều môi trường, trace và metric đều cần trả lời câu hỏi: **telemetry này được tạo bởi service nào, phiên bản nào, instance nào và đang chạy ở đâu?** Nếu mỗi span phải tự lặp lại tên service, hostname và môi trường triển khai thì dữ liệu dễ thiếu nhất quán. OpenTelemetry giải quyết việc đó bằng **Resource**: tập thuộc tính mô tả thực thể đang phát ra telemetry.

Bài **OpenTelemetry Resource** thuộc chương **OpenTelemetry** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Ý chính:** Resource mô tả **nguồn phát telemetry** (ví dụ service và instance); Span attributes mô tả **một operation cụ thể**; metric attributes phân nhóm **một chuỗi số liệu**; instrumentation scope mô tả **thư viện tạo telemetry**. Chọn đúng lớp giúp service identity nhất quán trên traces, metrics và logs, đồng thời tránh lặp metadata ở mọi span.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Resource trong OpenTelemetry và vì sao nó quan trọng trong hệ thống nhiều service/instance.
2. Phân biệt Resource attributes, Span attributes, metric attributes và Instrumentation Scope.
3. Nhận diện các thuộc tính service phổ biến như service.name, service.namespace, service.version và service.instance.id.
4. Chọn thuộc tính deployment, host, container, process phù hợp với mục đích quan sát.
5. Cấu hình resource identity trong Spring Boot và hiểu vai trò của spring.application.name, OTEL_SERVICE_NAME và OTEL_RESOURCE_ATTRIBUTES.
6. Hiểu cách merge resource attributes và precedence khi cùng một key xuất hiện ở nhiều nguồn.
7. Biết khi nào resource attributes có cardinality phù hợp và khi nào cần tránh identifier không ổn định.
8. Kiểm tra Resource trên traces, metrics, logs và Collector pipeline.
9. Tránh những lỗi service identity làm phân tách dashboard hoặc gộp nhầm nhiều ứng dụng.
10. Dùng Resource để liên kết tín hiệu trong điều tra sự cố.

## 2. Resource trong mô hình OpenTelemetry

OpenTelemetry định nghĩa Resource là một biểu diễn bất biến (immutable) của thực thể được quan sát, được biểu diễn bằng Attributes. Ví dụ, một tiến trình chạy trong container trên Kubernetes có thể được mô tả bằng service name, pod/container identity, hostname, OS và process information. Resource được phát hiện/cấu hình độc lập với exporter; exporter nhận telemetry cùng Resource thay vì phải tự suy đoán service identity.

~~~mermaid
flowchart TD
    A["Observed entity<br/>Spring Boot service instance"] --> B["Resource"]
    B --> C["service.name"]
    B --> D["service.namespace / version"]
    B --> E["service.instance.id"]
    B --> F["deployment / host / container / process"]
    G["Instrumentation library"] --> H["Instrumentation Scope"]
    B --> I["Telemetry"]
    H --> I
    I --> J["Spans / Metrics / Logs"]
    J --> K["Exporter"]
    K --> L["Collector / observability backend"]
~~~

Resource thường được gắn với các provider tương ứng khi SDK/provider được tạo. Ví dụ, một TracerProvider có Resource nhận diện ứng dụng tạo span. Metrics và logs SDK/provider tương ứng cũng có Resource. Exporter có thể serialize Resource dưới dạng resource attributes hoặc đưa vào metadata của giao thức.

### 2.1 Một Resource đại diện cho thực thể nào?

Một quy tắc hữu ích:

- Các instance cùng một service logic có cùng service.name.
- Mỗi instance đang chạy cần được phân biệt khi vận hành bằng service.instance.id phù hợp.
- Service có thể được nhóm trong namespace hoặc domain bằng service.namespace.
- Bản phát hành được mô tả bằng service.version khi có thông tin build đáng tin cậy.
- Vị trí triển khai như deployment.environment.name, cloud.region, k8s.namespace.name hoặc container.id bổ sung ngữ cảnh về nơi service chạy.

Không gắn một service.name khác nhau cho mỗi pod/replica. Nếu mỗi replica tự nhận service.name riêng, dashboard sẽ phân mảnh một service logic thành rất nhiều service.

### 2.2 Resource là immutable

Resource được thiết kế bất biến sau khi provider được tạo. Điều này giúp mọi span/metric/log do provider tạo ra nhận cùng service identity trong vòng đời tương ứng. Nếu deployment version hoặc instance identity thay đổi, thông thường đó là process/instance mới với Resource mới, không phải cập nhật Resource trên từng request.

## 3. Resource attributes và các lớp metadata khác

| Loại metadata | Trả lời câu hỏi | Ví dụ | Phạm vi |
|---|---|---|---|
| **Resource attributes** | Ai tạo telemetry? | service.name=order-service, deployment.environment.name=production | Thực thể phát telemetry |
| **Instrumentation Scope** | Thư viện/instrumentation nào tạo telemetry? | scope name=io.micrometer, version=... | Nhóm telemetry theo instrumenter |
| **Span attributes** | Span đang thực hiện operation nào? | http.request.method=POST, db.system.name=postgresql | Một span |
| **Span events** | Điều gì đã xảy ra trong span? | retry scheduled, exception event | Mốc trong span |
| **Metric attributes** | Series metric cần được nhóm theo chiều nào? | route=/orders/{id}, status=500 | Một metric data point/time series |
| **Log attributes** | Log record chứa thông tin gì? | message, severity, trace_id, span_id | Một log record |

Ví dụ với một request đặt hàng:

~~~text
Resource:
  service.name = order-service
  service.version = 2.4.1
  deployment.environment.name = production

Instrumentation scope:
  name = io.micrometer.observation
  version = ...

Span:
  name = POST /orders
  attributes:
    http.request.method = POST
    http.response.status_code = 201

Metric:
  name = http.server.request.duration
  attributes:
    http.request.method = POST
    http.route = /orders
    http.response.status_code = 201
~~~

service.name không phải span attribute riêng của request; nó nhận diện nguồn phát. http.route là thông tin của request/operation, không phải identity của service. Không lẫn hai lớp khi thiết kế query hoặc filter.

### 3.1 Resource khác Instrumentation Scope

Một service có thể dùng nhiều thư viện instrument khác nhau: Spring MVC instrumentation, Micrometer Observation, JDBC instrumentation hoặc một thư viện client. Resource có thể giống nhau vì tất cả telemetry cùng được tạo bởi một service instance; Instrumentation Scope khác nhau để cho biết thư viện nào tạo ra telemetry đó.

Khi backend hiển thị một trace, bạn có thể thấy cùng Resource trên các spans nhưng scope name khác nhau. Đây không phải service đổi tên; đó là các nguồn instrumentation khác nhau trong cùng process.

## 4. Những service resource attributes quan trọng

OpenTelemetry Semantic Conventions quy định key và ý nghĩa của resource attributes để backend diễn giải nhất quán.

| Attribute | Ý nghĩa | Ví dụ | Hướng dẫn |
|---|---|---|---|
| service.name | Tên logic của service | order-service | Ổn định giữa các replica |
| service.namespace | Namespace nhóm service | commerce | Phân biệt domain/organization |
| service.version | Phiên bản service | 2.4.1 hoặc git SHA | Phản ánh artifact/build |
| service.instance.id | Định danh instance cụ thể | UUID/pod identity | Phân biệt các replica đồng thời |
| deployment.environment.name | Môi trường triển khai | production, staging, development, test | Dùng giá trị well-known nếu áp dụng |
| service.language.name | Ngôn ngữ implementation | java | Thường do SDK/resource provider xác định |

### 4.1 service.name phải ổn định giữa các replicas

Ví dụ ba pod cùng chạy Order Service:

~~~text
service.name = order-service
service.instance.id = pod-7f9a
service.instance.id = pod-8c21
service.instance.id = pod-2b40
~~~

Ba instance chia sẻ service.name, nhưng có instance IDs khác nhau. Khi query tổng service, lọc theo service.name. Khi tìm một replica cụ thể có lỗi, thêm service.instance.id hoặc Kubernetes pod attributes nếu được thu thập.

Không gắn pod name hoặc container ID vào service.name vì mỗi lần scale/rollout sẽ tạo một service identity khác.

### 4.2 service.version nên phản ánh build đang chạy

Một version có thể là semantic version, release tag hoặc commit SHA. Điều quan trọng là giá trị có thể liên kết tới artifact thực đã deploy. Không dùng một giá trị chung không phân biệt được bản build; khi rollout phiên bản mới, dashboard/trace cần so sánh được hai nhóm version.

Nếu dùng Spring Boot build-info, resource provider tương ứng có thể lấy build name/version từ build-info.properties tùy integration. Nếu tự cấu hình, đảm bảo pipeline build đưa đúng version vào runtime.

### 4.3 service.instance.id phải phân biệt instance

service.instance.id nên duy nhất cho từng instance của cùng service namespace/name trong phạm vi cần phân biệt. Có thể lấy từ pod UID, instance UUID hoặc identifier do platform cấp. Tránh dùng hostname chung cho nhiều container nếu hostname không duy nhất; cũng cân nhắc độ ổn định khi process restart.

### 4.4 deployment.environment.name

Semantic Conventions hiện hành dùng key deployment.environment.name; các giá trị well-known gồm development, production, staging và test. Môi trường tùy chỉnh có thể dùng giá trị riêng nếu không có giá trị well-known phù hợp. Đây là thuộc tính phân loại môi trường; nó không làm cho service identity khác nhau theo quy tắc uniqueness của service.

Đừng nhầm key cũ deployment.environment trong một số tài liệu/cấu hình cũ với semantic convention hiện hành. Khi nâng cấp, kiểm tra schema/version và mapping ở Collector/backend trước khi đổi query.

## 5. Các Resource attributes từ hạ tầng

Ngoài service identity, resource có thể chứa thông tin nơi process chạy. Chỉ bật những detector/attributes thực sự hữu ích và phù hợp chính sách dữ liệu.

| Nhóm | Ví dụ attributes | Dùng để |
|---|---|---|
| Host | host.name, host.arch, host.id | Xác định máy/VM |
| Operating system | os.type, os.description, os.version | Phân biệt runtime OS |
| Process | process.pid, process.executable.name, process.command_line | Điều tra tiến trình |
| Process runtime | process.runtime.name, process.runtime.version | Theo dõi Java runtime |
| Container | container.id, container.image.name, container.image.tag | Điều tra container/deployment |
| Kubernetes | k8s.namespace.name, k8s.pod.name, k8s.deployment.name | Nhóm theo workload |
| Cloud | cloud.provider, cloud.region, cloud.availability_zone | Phân tích vùng/infra |

Một số attributes có thể tạo cardinality đáng kể khi đưa vào metrics. Ví dụ process.pid thay đổi mỗi lần restart; pod name biến thiên khi rollout. Chúng hữu ích cho trace/log resource hoặc phân tích instance, nhưng không nhất thiết nên thêm vào mọi metric series.

### 5.1 Auto-detection không phải lúc nào cũng đủ

SDK/resource providers có thể phát hiện host, OS, process, container hoặc service identity. Tuy nhiên:

- Detector phụ thuộc SDK, runtime, quyền truy cập và môi trường.
- Một số detector bị tắt mặc định hoặc chỉ có trong một distro/agent cụ thể.
- Kubernetes metadata có thể cần deployment platform/Collector enrichment.
- Container image digest/tag không phải lúc nào cũng tự lấy được.
- Chạy local có thể tạo resource attributes khác production.

Hãy xác nhận Resource thật được gửi ra, không chỉ dựa vào danh sách detector dự kiến.

## 6. Cấu hình Resource trong Spring Boot

Spring Boot có thể tạo Resource cho OpenTelemetry integration dựa trên property/môi trường mà nó hỗ trợ. Trước tiên, đặt tên ứng dụng rõ ràng:

~~~yaml
spring:
  application:
    name: order-service
~~~

Spring Boot OpenTelemetry auto-configuration có thể dùng spring.application.name làm giá trị mặc định cho service.name nếu không có giá trị ưu tiên cao hơn. Một tên rõ ràng tốt hơn nhiều so với backend chỉ hiển thị unknown_service:java.

### 6.1 Cấu hình service metadata

Ví dụ minh họa cách khai báo resource attributes trong một integration có hỗ trợ:

~~~yaml
otel:
  resource:
    attributes:
      service:
        namespace: commerce
        version: 2.4.1
      deployment:
        environment:
          name: production
~~~

Cấu trúc property phụ thuộc integration. OpenTelemetry Spring Boot Starter hỗ trợ schema cấu hình SDK riêng; Spring Boot Actuator built-in OpenTelemetry auto-configuration có nhóm property riêng. Không sao chép YAML của starter vào cấu hình Actuator và giả định binding giống nhau. Xác minh bằng configuration metadata của dependency đang dùng.

Một cách cấu hình phổ biến của OpenTelemetry SDK là biến môi trường:

~~~bash
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production
~~~

Các giá trị trong OTEL_RESOURCE_ATTRIBUTES là chuỗi key=value phân tách bằng dấu phẩy. Dấu phẩy và dấu bằng nằm trong key/value cần percent-encode theo quy tắc của OTel. Không ghép tùy tiện một value chứa dấu phẩy vào danh sách vì parser có thể diễn giải thành member khác.

### 6.2 Lưu ý về Spring Boot auto-configuration

Spring Boot reference hiện hành phân biệt các biến môi trường Resource nó hỗ trợ, trong đó có OTEL_RESOURCE_ATTRIBUTES và OTEL_SERVICE_NAME. Không mặc định mọi biến môi trường của OpenTelemetry SDK autoconfigure đều có hiệu lực khi dùng Spring Boot built-in OpenTelemetry auto-configuration. Nếu cần toàn bộ cơ chế SDK autoconfigure hoặc resource providers khác, hãy làm theo hướng dẫn Spring Boot phù hợp và hiểu rằng tự cung cấp OpenTelemetry bean có thể làm tắt auto-configuration của Boot, ảnh hưởng các tính năng observability tích hợp.

### 6.3 Xác định integration đang sử dụng

Có ít nhất hai kiểu tích hợp dễ bị nhầm:

- **Spring Boot Actuator + Micrometer Tracing/OpenTelemetry bridge:** Resource thuộc tracing/metrics provider do Spring Boot quản lý. Dùng property của Spring Boot và dependency bridge/exporter tương ứng phiên bản.
- **OpenTelemetry Spring Boot Starter hoặc Java agent/autoconfigure:** Có schema/property riêng như otel.resource.attributes và resource provider detectors. Không sao chép nguyên YAML của starter vào cấu hình Actuator rồi giả định Spring Boot sẽ bind giống nhau.

Trước khi áp dụng, xác định ứng dụng đang dùng integration nào, provider nào được tạo và ai chịu trách nhiệm cấu hình Resource.

## 7. Precedence và merge Resource attributes

Cùng một resource key có thể xuất hiện từ nhiều nguồn: giá trị SDK mặc định, environment variables, resource detectors, Spring properties hoặc user-provided Resource. Nếu không hiểu precedence, service có thể mang nhầm tên hoặc version.

Theo OpenTelemetry Resource SDK specification, OTEL_RESOURCE_ATTRIBUTES được merge với resource do người dùng cung cấp như một resource phụ; user-provided Resource có độ ưu tiên cao hơn khi trùng key. Với Spring Boot OpenTelemetry auto-configuration, resource attributes do người dùng cấu hình cũng được áp dụng sau phần environment và có thể ghi đè giá trị môi trường; Spring Boot còn cung cấp default service.name từ spring.application.name nếu chưa có.

| Nguồn ví dụ | Giá trị service.name | Ý nghĩa |
|---|---|---|
| Runtime default | unknown_service:java | Fallback khi không có tên khác |
| spring.application.name | order-service | Tên mặc định từ cấu hình Spring |
| OTEL_SERVICE_NAME | checkout-api | Service name theo OTel env |
| OTEL_RESOURCE_ATTRIBUTES | service.name=legacy-api | Resource attribute từ danh sách env |
| User-provided Spring/Resource attribute | service.name=order-service-v2 | Có thể ưu tiên hơn nguồn môi trường theo integration |

Bảng thể hiện các nguồn có thể tham gia, không phải một thứ tự precedence duy nhất áp dụng cho mọi Spring Boot major/integration. Dùng precedence được tài liệu của đúng Spring Boot/OpenTelemetry integration quy định. Luôn kiểm tra Resource thực tế sau khi chạy.

### 7.1 service.name và OTEL_SERVICE_NAME

OpenTelemetry SDK convention quy định OTEL_SERVICE_NAME là cách đặt service name chuyên biệt; nó có precedence cao hơn service.name được cung cấp qua OTEL_RESOURCE_ATTRIBUTES trong SDK autoconfigure thông thường. Tuy nhiên Spring Boot có resource merge/binding riêng. Khi sử dụng built-in OpenTelemetry auto-configuration, hãy theo tài liệu Spring Boot hiện hành và test khi nhiều nguồn cùng cấu hình; đừng trộn precedence của Java agent với precedence của Spring Boot starter.

### 7.2 Không set cùng một key ở quá nhiều nơi

Nếu service.name được ghi trong YAML, environment và deployment manifest, rất khó biết giá trị nào thắng. Nên chọn một nguồn authoritative theo môi trường:

- spring.application.name hoặc cấu hình ứng dụng cho identity logic.
- Deployment environment variables cho giá trị riêng của môi trường.
- Build metadata cho service.version.
- Platform metadata/detector cho instance/container/host identity.

Ghi lại nguồn sở hữu từng key trong quy trình triển khai và xác minh sau rollout.

## 8. Resource được gắn vào telemetry như thế nào?

Một Resource có thể được gắn với provider và dùng cho nhiều tín hiệu. Trong OpenTelemetry data model, mỗi Span/Metrics/Log Record gắn với Resource tương ứng hoặc được nhóm dưới Resource trong export format.

~~~mermaid
flowchart TD
    R["Resource<br/>service.name=order-service<br/>service.version=2.4.1"]
    R --> T["TracerProvider"]
    R --> M["MeterProvider"]
    R --> L["LoggerProvider"]
    T --> S["Spans"]
    M --> D["Metric data"]
    L --> G["Log records"]
    S --> E["OTLP Export"]
    D --> E
    G --> E
    E --> C["Collector"]
    C --> B["Backend"]
~~~

Một exporter OTLP có thể gửi các loại signal theo pipeline riêng. Collector có thể nhận resource attributes, thêm metadata từ Kubernetes hoặc cloud, lọc/transform attributes và chuyển tiếp tới backend.

### 8.1 Resource và Instrumentation Scope trong export

OTLP biểu diễn Resource tách khỏi danh sách spans hoặc metric data của Resource đó. Backend có thể flatten resource fields vào record view, trong khi một số nơi giữ chúng thành metadata riêng. Instrumentation Scope được mô tả riêng để nhận diện thư viện tạo telemetry.

Không giả định mọi backend hiển thị Resource giống hệt nhau. Ý nghĩa thuộc tính theo semantic convention vẫn cần nhất quán.

### 8.2 Resource của metrics có tác động tới time series identity

Khi exporter chuyển Resource attributes thành labels, chúng có thể tham gia phân biệt series. service.name và environment giúp nhóm metrics đúng service. Nhưng service.instance.id, pod, container hoặc version có thể làm số series tăng. Cân nhắc backend và query model trước khi bật mọi resource detector cho metrics.

## 9. Resource trong Spring Boot/Micrometer và OpenTelemetry

Spring Boot thường sử dụng Micrometer Observation làm lớp instrumentation chung. Khi metrics hoặc tracing handler tạo telemetry, registry/provider liên quan sẽ đính kèm metadata theo cách implementation hỗ trợ.

Cần phân biệt:

- **Micrometer common tags** như management.metrics.tags.application: các tags gắn vào meter/metric registry, không tự động là Resource attributes của OpenTelemetry.
- **OpenTelemetry Resource attributes:** nhận diện telemetry provider/entity, được cấu hình cho OTel SDK/provider.
- **MDC fields:** dữ liệu log theo execution scope; không tự động là Resource.
- **Observation low-cardinality key-values:** metadata trên observation để handler chuyển sang signal phù hợp; không mặc nhiên trở thành Resource.

Ví dụ common metrics tags:

~~~yaml
management:
  metrics:
    tags:
      application: order-service
      environment: production
~~~

Cấu hình này gắn common tags vào Micrometer metrics theo Spring Boot; không nên coi nó là cách duy nhất để cấu hình OTel Resource. Nếu cần resource identity trong trace hoặc OTLP logs, phải cấu hình OTel resource theo cơ chế integration đang dùng.

### 9.1 Vì sao service.name trong trace và metrics lại khác?

Các nguyên nhân có thể:

- OTel Resource lấy service.name từ một nguồn, Micrometer common tag application lấy nguồn khác.
- Ứng dụng dùng hai registry/provider riêng.
- Collector transform/rename resource attributes.
- Backend map service identity theo logic riêng.
- Các services được cấu hình khác nhau hoặc đang trong rollout.

Chọn một tên service canonical rồi mapping nhất quán. Không tự đổi service.name theo từng span hoặc route.

## 10. Resource identity và cardinality

Resource attributes giúp phân biệt service/instance nhưng một số key có nhiều giá trị. Cardinality phụ thuộc signal và backend: một resource attribute có thể tạo nhóm Resource khác nhau cho trace/log; nếu được flatten thành metric labels, nó có thể làm tăng số time series.

| Attribute | Cardinality thường gặp | Gợi ý |
|---|---|---|
| service.name | Thấp/vừa, theo số service | Nên có |
| service.namespace | Thấp | Hữu ích khi tổ chức nhiều domain |
| service.version | Theo số build còn chạy | Hữu ích cho rollout; quản lý retention |
| deployment.environment.name | Thấp | Dùng giá trị chuẩn hóa |
| service.instance.id | Theo số instance | Hữu ích nhưng có thể tăng metric series |
| host.name | Theo số host | Chỉ bật nếu cần |
| container.id | Cao, đổi theo container | Cân nhắc signal/backend |
| process.pid | Cao và thay đổi | Có ích cho debug, không phải label mặc định mọi dashboard |
| request.id / trace.id | Gần như duy nhất mỗi request | Không thêm làm Resource attribute |
| user.id / order.id | Rất cao và có thể nhạy cảm | Không dùng làm Resource |

Không đưa ID request, span, order hoặc user vào Resource vì Resource mô tả thực thể phát telemetry, không mô tả từng request. Nếu service.instance.id thay đổi mỗi request thì bạn đã dùng sai lớp metadata.

### 10.1 Version có thể tạo nhiều Resource groups sau rollout

Trong rolling deployment, một lúc có thể tồn tại version 2.4.0 và 2.4.1. Điều này hợp lý: backend có thể phân biệt hai phiên bản để xem lỗi chỉ xảy ra sau rollout. Khi rollout hoàn tất, số Resource groups sẽ ổn định theo version đang chạy.

Không đổi service.name cho mỗi release; dùng service.version để theo dõi release.

## 11. Resource trong Kubernetes

Trong Kubernetes, Resource có thể mang service identity cùng namespace/pod/container metadata. Ví dụ:

~~~text
service.namespace = commerce
service.name = order-service
service.version = 2.4.1
service.instance.id = 7f9a... (pod UID)
deployment.environment.name = production
k8s.namespace.name = commerce-prod
k8s.pod.name = order-service-7f9a
k8s.deployment.name = order-service
container.id = container runtime identifier
~~~

Một số thuộc tính được SDK/Collector phát hiện, còn một số cần Kubernetes resource detector hoặc Collector processor. Chỉ cấu hình detector khi môi trường có thể cung cấp thông tin và policy cho phép.

### 11.1 Resource detection tại app hay Collector?

Có thể enrich Resource ở hai nơi:

- **Application SDK:** tự biết process/runtime/service và một số host/container data; thuận tiện khi exporter gửi telemetry trực tiếp.
- **Collector:** có thể bổ sung Kubernetes attributes dựa trên pod IP, connection metadata hoặc platform API; giúp centralize config và tránh mọi service phải tự tích hợp detector.

Không enrich cùng một key với hai nguồn mâu thuẫn. Thiết lập precedence/override policy rõ ràng trong Collector và kiểm tra kết quả sau processor.

### 11.2 Không expose metadata hạ tầng nhạy cảm

Process command line, host IDs, cloud account IDs, container image path hoặc internal topology có thể tiết lộ chi tiết hạ tầng. Chỉ thu thập key cần thiết, giới hạn ai được truy cập backend và áp dụng retention phù hợp.

## 12. Kiểm tra Resource sau khi chạy Spring Boot

Không chỉ nhìn vào application.yml; cần xem telemetry thực sự xuất ra.

### 12.1 Qua OpenTelemetry Collector/OTLP backend

Nếu dùng OTLP, mở span hoặc log resource trong backend và xác minh các key:

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = staging
service.instance.id = ...
~~~

Nếu thiếu service.name, kiểm tra spring.application.name, OTEL_SERVICE_NAME, resource attributes và OTel provider auto-configuration. Nếu giá trị khác dự kiến, kiểm tra nguồn ghi đè và Collector processors.

### 12.2 Qua debug exporter trong môi trường local

Có thể dùng exporter/debug hoặc in Resource từ SDK trong test. Với OpenTelemetry Java API, ý tưởng là đọc Resource gắn với provider/SDK signal. API cụ thể tùy provider/SDK version; tránh ép Spring Boot auto-configured bean sang implementation cụ thể khi chưa xác nhận loại bean.

Pseudo-code định hướng:

~~~java
// Pseudocode: lấy Resource từ provider/SDK đang sử dụng.
// API cụ thể phụ thuộc loại OpenTelemetry SDK/provider.
Resource resource = configuredTracerProvider.getResource();
System.out.println(resource.getAttributes());
~~~

Đây là pseudocode, không phải đoạn có thể copy chạy trên mọi Spring Boot setup. Trong production, ưu tiên quan sát Resource ở telemetry đã export để kiểm chứng cả merge và Collector pipeline.

### 12.3 Kiểm tra OTEL_RESOURCE_ATTRIBUTES

Ví dụ:

~~~bash
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES="service.namespace=commerce,service.version=2.4.1,deployment.environment.name=staging"
~~~

Nếu value cần chứa ký tự đặc biệt như dấu phẩy hoặc dấu bằng, percent-encode theo OTel environment variable format. Nếu shell/container platform xử lý dấu ngoặc kép khác nhau, kiểm tra environment thực tế bên trong process chứ không chỉ manifest.

## 13. Kết hợp Resource với metrics, logs và traces

Resource là điểm liên kết service identity giữa các signal. Khi query, có thể bắt đầu từ service.name và deployment environment rồi mở các dữ liệu tương ứng.

~~~mermaid
flowchart LR
    R["Resource<br/>service.name=order-service"] --> M["Metrics<br/>request rate / latency / errors"]
    R --> T["Traces<br/>server/client spans"]
    R --> L["Logs<br/>application events"]
    M --> Q["Phát hiện service suy giảm"]
    T --> Q2["Khoanh span/dependency"]
    L --> Q3["Đọc exception/context"]
    Q --> Q4["Correlation theo service/resource"]
    Q2 --> Q4
    Q3 --> Q4
~~~

Ví dụ điều tra:

1. Dashboard lọc service.name=order-service và deployment.environment.name=production cho thấy HTTP p95 tăng.
2. Trace backend lọc cùng Resource để xác định version/instance có span DB chậm.
3. Logs cùng service identity hiển thị timeout và trace correlation.
4. So sánh service.version cũ/mới để xác định lỗi chỉ xuất hiện sau rollout.
5. Xem service.instance.id để kiểm tra vấn đề có tập trung vào một replica hay không.

Trace ID liên kết một request; Resource liên kết telemetry theo thực thể phát. Không thay Trace ID bằng service.name hoặc ngược lại.

## 14. Lỗi thường gặp khi cấu hình Resource

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Backend hiển thị unknown_service:java | Chưa đặt service.name hoặc Spring application name | Đặt spring.application.name/OTEL_SERVICE_NAME và kiểm tra integration |
| Mỗi pod xuất hiện như một service khác | service.name lấy pod name/instance ID | Dùng tên logic chung; chuyển pod ID sang service.instance.id hoặc k8s.pod.name |
| Trace và metrics có service name khác nhau | OTel Resource và Micrometer common tags cấu hình khác | Đồng bộ canonical service identity và kiểm tra Collector mapping |
| service.version trống | Không sinh build-info hoặc chưa cấu hình resource | Gắn build metadata đáng tin cậy |
| Nhiều Resource groups bất ngờ | instance/version/host attributes thay đổi hoặc sai detector | Kiểm tra từng attribute theo signal |
| deployment environment không thống nhất | Dùng key cũ/mới hoặc giá trị tự do | Chuẩn hóa deployment.environment.name |
| Resource attributes không ghi đè như kỳ vọng | Hiểu sai precedence giữa Boot, SDK và env | Xác định integration/version, test nguồn trùng key |
| OTEL_RESOURCE_ATTRIBUTES không có hiệu lực | Spring Boot auto-config hỗ trợ giới hạn biến hoặc sai cú pháp | Kiểm tra reference Boot, env của process, encoding |
| Có service.name trong logs nhưng không trong traces | Log MDC/common fields không phải OTel Resource | Kiểm tra OTel provider Resource và exporter |
| Collector đổi hoặc mất key | Processor/filter/transform config | Kiểm tra từng pipeline processor |
| Metrics time series tăng mạnh | Resource attributes high-cardinality bị flatten thành labels | Giảm labels và chọn attributes hợp lý theo signal |
| service.instance.id giống nhau giữa replicas | Dùng giá trị cố định cho mọi instance | Dùng pod UID/instance UUID phù hợp |
| service.name đổi sau mỗi release | Gắn version vào service.name | Giữ service.name; đưa release vào service.version |

## 15. Playbook: service identity sai sau deployment

**Tình huống:** Dashboard trước rollout hiển thị order-service; sau rollout xuất hiện unknown_service:java và dữ liệu bị tách.

1. **Kiểm tra application config:** spring.application.name có còn được đặt không?
2. **Kiểm tra process environment:** OTEL_SERVICE_NAME và OTEL_RESOURCE_ATTRIBUTES có được inject vào container không?
3. **Xác định integration:** Spring Boot built-in auto-configuration, OpenTelemetry Spring Boot Starter hay Java agent?
4. **Kiểm tra precedence:** có user resource attributes/SDK config nào ghi đè hoặc resource provider nào không hoạt động?
5. **Kiểm tra Collector:** có transform/override service.name hoặc tách pipeline không?
6. **So sánh tín hiệu:** traces, metrics, logs có cùng canonical service identity không?
7. **Kiểm tra instance:** service.instance.id có khác nhau giữa replicas nhưng service.name vẫn giống nhau không?
8. **Khắc phục và xác minh:** gửi telemetry mới, xác nhận Resource đúng ở exporter/backend trước khi sửa dashboards/alerts.

Không đổi dashboard để thích nghi với service identity sai khi nguyên nhân thực sự nằm ở cấu hình Resource.

## 16. Bài tập tự kiểm tra

**Bài 1 — Phân loại metadata.** Với một request POST /orders, hãy phân loại service.name, service.version, host.name, http.request.method, spanId và status code vào Resource, SpanContext hay Span attributes/metric attributes. Giải thích.

**Bài 2 — Identity của replicas.** Có bốn pod chạy cùng Order Service. service.name và service.instance.id nên có quan hệ như thế nào? Vì sao không gắn pod name vào service.name?

**Bài 3 — Version rollout.** Một rollout chạy đồng thời version 2.4.0 và 2.4.1. Nên thay service.name hay service.version? Hậu quả nếu mỗi version dùng service.name khác nhau?

**Bài 4 — Property precedence.** spring.application.name là order-service, OTEL_SERVICE_NAME là order-api và user-provided Resource đặt service.name=checkout. Hãy nêu cách kiểm tra giá trị cuối theo đúng Spring Boot/OpenTelemetry integration; vì sao không thể suy diễn precedence của Java agent cho mọi cấu hình Boot?

**Bài 5 — Cardinality.** Có 100 pods và mỗi pod gửi 20 metrics. Nếu service.instance.id bị flatten thành metric label, số series có thể tăng theo chiều nào? Khi nào giá trị này vẫn hữu ích?

**Bài 6 — Spring metrics tags.** Cấu hình management.metrics.tags.application=order-service có tự động tạo OpenTelemetry Resource service.name không? Giải thích khác nhau giữa Micrometer common tags và OTel Resource.

**Bài 7 — Collector enrichment.** Khi nào nên phát hiện k8s.pod.name tại Collector thay vì từng app? Điều cần kiểm tra nếu app và Collector cùng gán service.instance.id?

**Bài 8 — Điều tra service name sai.** Trace backend hiển thị unknown_service:java, log backend ghi order-service. Hãy lập thứ tự kiểm tra từ Spring application name, OTel configuration, exporter và Collector.

### Gợi ý trả lời

1. service.name/version/host là Resource; spanId thuộc SpanContext; method/status gắn với span hoặc metric data point theo instrumentation.
2. service.name giống nhau cho cả bốn pod; service.instance.id khác nhau. service.name nhận diện service logic, instance ID phân biệt replica.
3. Giữ service.name, đổi service.version. Nếu đổi service.name theo release, dashboard chia service thành nhiều nhóm.
4. Xem phiên bản và integration cụ thể, nguồn user-provided/env/default, rồi kiểm tra Resource thực tế đã export. Spring Boot có merge behavior riêng, không thể lấy precedence Java agent làm quy tắc chung.
5. Có thể tạo nhiều series theo số pod × các chiều metric khác; hữu ích cho điều tra instance nhưng cần cân bằng chi phí.
6. Không. Đây là Micrometer common tags; Resource của OTel được cấu hình ở provider/integration tương ứng.
7. Collector phù hợp khi muốn centralize Kubernetes metadata và tránh mỗi service cần platform API; đảm bảo không có hai nguồn mâu thuẫn ghi cùng key.
8. Kiểm tra application config/environment, SDK/provider, Resource merge, exporter, Collector processors và log/trace pipeline riêng.

## 17. Tài liệu tham khảo chính thức

- [OpenTelemetry Specification — Resource SDK](https://opentelemetry.io/docs/specs/otel/resource/sdk/): định nghĩa Resource bất biến, gắn Resource với telemetry và merge environment attributes.
- [OpenTelemetry Semantic Conventions — Resources](https://opentelemetry.io/docs/specs/semconv/resource/): các service/host/container/deployment resource attributes.
- [OpenTelemetry — SDK Configuration for Java](https://opentelemetry.io/docs/languages/java/configuration/): OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES và resource providers.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Resource trong OpenTelemetry, biến môi trường được Spring Boot hỗ trợ và auto-configuration.
- [OpenTelemetry Spring Boot Starter — SDK Configuration](https://opentelemetry.io/docs/zero-code/java/spring-boot-starter/sdk-configuration/): resource attributes, resource detectors, service name precedence của starter.
- [OpenTelemetry — Resources](https://opentelemetry.io/docs/concepts/resources/): cách Resource mô tả thực thể phát telemetry.
- [OpenTelemetry Protocol — Common](https://opentelemetry.io/docs/specs/otlp/): cấu trúc resource và telemetry trong OTLP.
- [OpenTelemetry Semantic Conventions — Deployment](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/): deployment.environment.name và các giá trị well-known.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation và tích hợp metrics/tracing trong Spring.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): phân biệt Micrometer metrics và common tags trong Spring Boot.

**Ghi nhớ:** Resource trả lời **“thực thể nào đã phát ra telemetry?”**. Giữ service.name ổn định giữa replicas; dùng service.instance.id để phân biệt instance, service.version để nhận diện release, deployment.environment.name để phân nhóm môi trường. Đừng nhầm Resource với span attributes, MDC hoặc Micrometer common tags. Trong Spring Boot, xác định đúng integration và precedence của resource configuration, sau đó kiểm tra Resource ở telemetry đã export; cấu hình đúng từ đầu giúp metrics, logs và traces có cùng service identity để điều tra sự cố xuyên tín hiệu.

