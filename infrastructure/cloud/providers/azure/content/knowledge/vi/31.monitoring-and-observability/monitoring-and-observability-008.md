# Theo dõi dependency, exception và transaction ứng dụng

Một khách hàng nhấn **Đặt hàng** trên website. Sau 4,8 giây, trình duyệt hiển thị lỗi. API Spring Boot vẫn đang chạy, CPU chỉ 25% và database không có cảnh báo hạ tầng. Vậy hệ thống lỗi ở đâu: request HTTP, truy vấn Azure SQL, kết nối Redis, cuộc gọi đến cổng thanh toán, message gửi Azure Service Bus hay một exception bị bắt rồi bỏ qua? Nếu mỗi dịch vụ chỉ ghi log riêng, việc trả lời có thể mất hàng giờ.

**Application observability** cho phép theo dõi hành trình một thao tác qua những thành phần liên quan. Trong Azure, nhóm công cụ thường gồm **Azure Monitor**, **Application Insights**, **Log Analytics workspace**, **OpenTelemetry**, các loại metrics, logs và **distributed traces**. Ba đối tượng trọng tâm của bài là:

- **Dependency:** thao tác gọi ra ngoài tiến trình, chẳng hạn HTTP, JDBC/SQL, Redis, Azure Storage, Service Bus, DNS hoặc dịch vụ đối tác.
- **Exception:** lỗi được ném hoặc ghi nhận trong quá trình thực thi; không phải exception nào cũng gây HTTP 500 hoặc thất bại nghiệp vụ.
- **Transaction ứng dụng:** một thao tác có ý nghĩa với người dùng hoặc nghiệp vụ, ví dụ xác nhận đơn hàng; cần theo dõi thời gian, kết quả và các bước con qua nhiều dịch vụ.

Bài thuộc chương **Giám sát và quan sát hệ thống** của module **CLOUD_PROVIDERS_AZURE**. Module khám phá hệ sinh thái Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, compute, lưu trữ, dữ liệu, bảo mật, giám sát và chi phí. Ở đây, ta nối **request của ứng dụng Java/Spring Boot → dependency calls → exceptions → business outcome** để chẩn đoán sự cố và quản lý vận hành theo bằng chứng.

**Lưu ý phạm vi:** các ví dụ sử dụng Java 17/21, Spring Boot và Azure Monitor Application Insights. Tên SDK, phiên bản agent, bảng KQL, tính năng tự động instrument, quyền truy cập và giá có thể thay đổi theo dịch vụ/tài nguyên. Các dữ liệu, request ID, endpoint và thời gian trong bài là **minh họa**, không phải telemetry đã được đo. Không bật debug ghi dữ liệu thật hoặc fault injection trên production khi chưa được phê duyệt.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **request, dependency, exception, trace, span, event, metric và log**.
2. Phân biệt **application transaction**, **database transaction** và **distributed trace**.
3. Thiết kế cây trace từ HTTP request tới SQL, HTTP downstream và Service Bus.
4. Hiểu **trace ID, span ID, parent span ID**, W3C **traceparent/tracestate**, context propagation.
5. Chọn giữa **Azure Monitor OpenTelemetry Distro/Java agent**, SDK instrumentation và custom spans.
6. Ghi dependency duration, target, kết quả và exception mà không rò rỉ thông tin nhạy cảm.
7. Dùng **Application Insights Application Map, transaction diagnostics, Failures** và **Log Analytics/KQL** khi tính năng hỗ trợ.
8. Tìm requests chậm, dependency thất bại và exceptions theo một operation ID.
9. Xử lý các trường hợp **retry, circuit breaker, 4xx/5xx, async, queues và sampling**.
10. Thiết kế alert/SLO có ý nghĩa, kiểm soát telemetry volume và chi phí.
11. Xây dựng một bài lab và runbook theo dõi sự cố Spring Boot trên Azure.

## 2. Một thao tác đi qua những thành phần nào?

Ví dụ lệnh tạo đơn hàng:

~~~mermaid
flowchart LR
    U[Browser] --> G[API Gateway]
    G --> A[orders-api: POST /orders]
    A --> P[(Azure PostgreSQL)]
    A --> C[Redis cache]
    A --> H[payment-api HTTPS]
    A --> B[Azure Service Bus]
    B --> W[invoice-worker]
    W --> S[(Azure SQL / Blob)]
~~~

Một request có thể phát sinh nhiều **dependencies**. Bản thân orders-api có thể không lỗi CPU, nhưng cuộc gọi payment-api timeout; hoặc payment-api thành công nhưng DB commit thất bại. Một trace tốt giúp thấy **tầng nào chậm**, **lỗi nằm ở span nào**, **tổng thời gian bị tiêu tốn ở đâu** và **mối quan hệ giữa các thành phần**.

### Ví dụ timeline

~~~text
POST /orders                      4.800 ms total
  |
  +-- SQL: read cart                35 ms
  +-- Redis: get price               8 ms
  +-- HTTPS: payment-api         4.500 ms [TIMEOUT]
  |     +-- Client retry         2.200 ms
  |     +-- Client retry         2.200 ms
  +-- SQL: rollback                12 ms
  +-- Response HTTP 504             ...
~~~

Số liệu giả định chỉ để thấy cách suy nghĩ. **Thời gian các spans có thể chồng lấn**, vì vậy không cộng mọi duration rồi mặc định bằng thời gian request. Một cây trace và critical path chính xác hơn tổng các dòng.

## 3. Ba trụ cột và loại dữ liệu telemetry

| Loại | Nội dung | Ví dụ | Dùng để |
|---|---|---|---|
| **Metrics** | Số đo tổng hợp theo thời gian | Request rate, error rate, p95, JVM heap | Alert/SLO/trends |
| **Logs** | Bản ghi sự kiện kèm ngữ cảnh | Authentication denied, job finished | Điều tra chi tiết |
| **Traces** | Cấu trúc spans của một operation | POST /orders → SQL → payment | Phân tích đường đi/latency |
| **Exceptions** | Dữ liệu lỗi gồm loại, message, stack khi được phép | SocketTimeoutException | Điều tra lỗi code/dependency |
| **Events** | Sự kiện nghiệp vụ hoặc vận hành | order_placed, release_promoted | Theo dõi hành vi/tương quan |

**Logs nhiều chưa chắc quan sát tốt.** Nếu không có correlation ID, mỗi service tạo log riêng và khó ghép. **Traces cũng không thay được metrics**: sampling có thể bỏ một số traces, còn metrics thích hợp hơn để tính SLO toàn hệ thống.

### Dạng telemetry trong Application Insights

| Ý niệm | Ví dụ trong Application Insights |
|---|---|
| Request | HTTP incoming request hoặc operation được instrument |
| Dependency | HTTP/SQL/outgoing call span |
| Exception | Exception telemetry hoặc span event |
| Trace/log | Diagnostic logs với severity |
| Custom event/metric | Hành động nghiệp vụ, bộ đếm/latency |

**Không giả định cứ ghi System.out là thành một trace có correlation.** Cần cấu hình logging/telemetry pipeline và context propagation.

## 4. Application transaction khác database transaction

Từ **transaction** có ba nghĩa dễ nhầm:

1. **HTTP/application transaction:** yêu cầu người dùng như POST /checkout, gồm nhiều dependency calls.
2. **Database transaction:** thao tác được quản lý bởi ACID/commit/rollback, ví dụ **@Transactional** trong Spring.
3. **Distributed trace/transaction diagnostics:** chuỗi các spans để theo dõi một request hoặc quy trình đi qua services.

~~~text
Application operation: PlaceOrder
    |
    +-- Validate cart
    +-- DB transaction: insert order + outbox -> COMMIT
    +-- Queue publish
    +-- Payment provider call
    +-- Response / eventual completion
~~~

Một **HTTP 200** không đảm bảo tiền đã thanh toán và queue đã xử lý. Ngược lại, database **COMMIT** không đồng nghĩa client nhận response thành công. Distributed tracing là quan sát, **không cung cấp distributed ACID transaction hoặc exactly-once semantics**.

### Business outcome phải được khai báo rõ

Ví dụ hệ thống có:

- request_status = HTTP 202 Accepted;
- order_status = PENDING_PAYMENT;
- payment_status = FAILED;
- invoice_status = NOT_STARTED.

Theo dõi chỉ HTTP status sẽ làm người vận hành tưởng giao dịch thành công. Cần **domain events/metrics** hoặc custom span attributes có kiểm soát để phản ánh kết quả kinh doanh, không dùng raw PII.

## 5. Trace, span và span hierarchy

Theo OpenTelemetry, một **trace** mô tả đường thực thi của operation; mỗi **span** có tên, start/end time, attributes, status và có thể có events/links.

~~~text
TraceId: 1234567890abcdef1234567890abcdef
|
+-- Span A: HTTP SERVER POST /orders
|     SpanId: 1111111111111111
|
|    +-- Span B: PostgreSQL SELECT
|    |     ParentSpanId: 1111111111111111
|    |
|    +-- Span C: HTTP CLIENT payment-api
|    |     ParentSpanId: 1111111111111111
|    |
|    +-- Span D: Service Bus PUBLISH
|          ParentSpanId: 1111111111111111
|
+-- Span E: invoice-worker PROCESS
      Truyền context/links theo messaging semantics
~~~

### Các trường quan trọng

| Field | Ý nghĩa |
|---|---|
| **trace_id** | Định danh toàn bộ trace, thường 16 bytes/32 ký tự hex trong W3C |
| **span_id** | Định danh một span, thường 8 bytes/16 ký tự hex |
| **parent_span_id** | Span cha khi có quan hệ parent-child |
| **span.kind** | SERVER, CLIENT, PRODUCER, CONSUMER, INTERNAL |
| **name** | Tên tác vụ, ví dụ HTTP POST /orders |
| **start/end/duration** | Thời gian thực thi |
| **attributes** | HTTP method, DB system, destination, peer service, environment |
| **status** | Tín hiệu lỗi/trạng thái span theo semantic conventions |
| **events** | Sự kiện trong span, có thể là exception event |
| **links** | Liên kết đến các span khác, hữu ích cho queue/batch workflows |

**Trace ID không phải thông tin xác thực**. Nó để tương quan logs/traces; không cấp quyền xem đơn hàng. Không dùng trace ID để quyết định tenant authorization.

## 6. W3C trace context: kết nối các dịch vụ

Tiêu chuẩn W3C dùng HTTP headers:

~~~http
traceparent: 00-1234567890abcdef1234567890abcdef-1111111111111111-01
tracestate: vendor=opaque-value
~~~

Các thành phần traceparent gồm version, trace ID, parent/span ID và trace flags. Service B nhận request, dùng extracted context tạo child span và khi gọi Service C sẽ inject context tiếp.

~~~text
Browser / API gateway
  traceparent=T
       |
       v
orders-api SERVER span
  extract context T
       |
       +-- JDBC child span
       |
       +-- HTTP payment-api request
                inject traceparent=T with current client span
                     |
                     v
                payment-api SERVER child span
~~~

### Những điều không được nhầm

- **traceparent** là correlation metadata, không phải JWT/OAuth token.
- **tracestate** dành cho metadata trace vendor-specific, không nhúng PII hoặc secrets.
- **baggage** có thể lan truyền qua process boundary: chỉ dùng các giá trị có whitelist, không đưa email, session token, account number.
- Một hệ thống chuyển giữa **W3C/legacy propagation** hoặc proxy bỏ headers có thể làm đứt trace.

### Correlation khi đi qua queue

Khi publish tới Azure Service Bus/Event Hubs, propagation phải dùng message application properties/headers theo SDK/instrumentation. Với **batch, retries, fan-out**, quan hệ parent-child có thể không diễn tả đầy đủ; OpenTelemetry hỗ trợ **span links**. Không ghép mọi queue event vào cùng một trace một cách tùy tiện hoặc kéo dài trace qua nhiều ngày.

## 7. Kiến trúc quan sát trên Azure

~~~mermaid
flowchart TD
    A[Spring Boot App Service / ACA / AKS] --> O[OpenTelemetry Java instrumentation]
    O --> M[Azure Monitor / Application Insights ingestion]
    M --> W[Log Analytics workspace]
    W --> K[KQL queries / Workbooks]
    M --> I[Application Map / transaction views]
    W --> AL[Azure Monitor alerts]
    AL --> AC[Action Groups: email / webhook / ITSM]
    A --> PM[Azure platform metrics & diagnostic settings]
    PM --> W
~~~

Một **workspace-based Application Insights resource** liên kết với **Log Analytics workspace**. Nó cung cấp trải nghiệm Application Map, tìm kiếm transactions, failures và truy vấn telemetry khi dữ liệu đã được thu đúng. Azure Monitor còn có platform metrics và resource diagnostic settings: **infrastructure telemetry** khác **application instrumentation**.

### Ba lớp phải kết nối

1. **Application layer:** Java requests, dependencies, exceptions, custom spans/metrics.
2. **Azure resource layer:** App Service/AKS/Container Apps CPU, memory, restarts, network, DB metrics.
3. **Business layer:** orders completed, failed payments, queue lag, SLO của khách hàng.

Nếu chỉ nhìn application requests, bạn có thể không thấy pod **OOMKilled**; nếu chỉ nhìn node CPU, bạn có thể không thấy payment HTTP 504. Cần liên kết theo **time range, service name, trace IDs, deployment/version và resource IDs**.

## 8. Chọn phương án instrumentation cho Java

| Phương án | Khi phù hợp | Điểm cần chú ý |
|---|---|---|
| **Azure Monitor OpenTelemetry Java agent / distro** | Spring Boot/Java app muốn auto-instrument nhanh | Version JDK/agent, dependency compatibility, agent startup |
| **OpenTelemetry Java agent + exporter/collector** | Tổ chức đã chuẩn hóa OTel pipeline nhiều backend | Collector/exporter/config và vận hành |
| **OpenTelemetry SDK + manual instrumentation** | Cần business spans đặc thù hoặc framework chưa auto-instrument | Context propagation, lifecycle và double instrumentation |
| **Spring Boot Micrometer Observation/Tracing** | App Spring Boot muốn native framework observability | Bridge/exporter, sampling và auto-instrument tương thích |
| **Platform diagnostics/logs** | Bổ sung host-level metrics/logs | Không thay thế distributed trace tự động |

**Bắt đầu từ một phương pháp instrumentation chính cho mỗi service.** Bật đồng thời nhiều Java agents, SDK exporters hoặc bridge không kiểm soát có thể tạo duplicate requests/dependencies, span context không thống nhất, tăng chi phí và làm sai số liệu.

### Quy tắc lựa chọn

- Chưa có OTel platform riêng, cần nhanh: thử **Azure Monitor-supported Java instrumentation**.
- Đã dùng OTel Collector/tempo/Prometheus nhiều nền tảng: theo chuẩn OTel tổ chức và xuất sang Azure Monitor khi hỗ trợ.
- Chỉ cần biết "order validation" hay "checkout stage" nằm ở đâu: thêm **custom spans** có ngữ nghĩa nghiệp vụ, không viết lại toàn bộ HTTP/JDBC spans.
- Muốn tính toàn bộ SLO request rate: cấu hình **metrics** song song, không chỉ ước lượng từ traces đã sampled.

## 9. Cấu hình Java auto-instrumentation

Một cách triển khai phổ biến là dùng **Azure Monitor OpenTelemetry Java agent** được Microsoft hỗ trợ cho phiên bản Java phù hợp. Lệnh **minh họa**:

~~~bash
export APPLICATIONINSIGHTS_CONNECTION_STRING="<APPLICATION_INSIGHTS_CONNECTION_STRING>"
export OTEL_SERVICE_NAME="orders-api"

java -javaagent:/opt/observability/applicationinsights-agent.jar \
     -jar /app/orders-api.jar
~~~

**Lưu ý:** tên/phiên bản file agent, cấu hình role name/resource attributes và API của Azure Monitor agent thay đổi theo gói phát hành. Phải lấy **đúng agent từ nguồn chính thức**, pin version, kiểm tra cách nó đọc biến môi trường và Java support matrix trước production. Đường dẫn ở đây là ví dụ, không phải chỉ thị tải một file bất kỳ trên mạng.

### Connection string là gì?

Application Insights resource cung cấp **connection string** chứa thông tin ingestion endpoint và instrumentation identity. Nó **không phải** OAuth Bearer token chứng minh quyền người dùng, và tùy cơ chế ingestion, instrumentation key trong connection string không được xem là secret xác thực mạnh. Tuy nhiên vẫn nên bảo vệ cấu hình và giới hạn ai được phép thay thế nó để tránh telemetry pollution hoặc gửi dữ liệu sang sai resource.

### Khi agent hoạt động

Một Spring Boot app có thể tự thu nhận các HTTP server/client spans, một số JDBC/database calls, logs/exceptions và messaging dependencies theo libraries/agent support. **Không cam kết mọi third-party SDK, native call hay custom executor đều được auto-instrument**. Kiểm tra danh sách frameworks và versions được hỗ trợ.

## 10. Kiểm chứng dữ liệu đầu tiên trong Application Insights

Sau khi gắn instrumentation vào app **sandbox**, gửi requests giả:

~~~bash
curl --silent --show-error -i \
  https://<LAB_HOST>/api/health-demo

curl --silent --show-error -i \
  https://<LAB_HOST>/api/orders/demo
~~~

Đây là các URL **placeholder**; endpoints phải tồn tại trong ứng dụng lab và dùng đúng hostname. Không ghi token/PII vào shell history hoặc CLI arguments ở môi trường chia sẻ.

### Tìm ở đâu?

1. Vào đúng **Application Insights resource** trong Azure Portal.
2. Kiểm tra ingestion/live metrics nếu được hỗ trợ.
3. Dùng **Transaction search / Performance / Failures / Application Map** theo tính năng Portal hiện hành.
4. Chọn khoảng thời gian tương ứng và đúng **cloud role name / environment**.
5. Tìm HTTP request vừa thực hiện, mở end-to-end transaction details.
6. Xác minh có child SQL/HTTP dependency spans và status/duration.
7. Dùng Log Analytics query kiểm chứng bảng AppRequests/AppDependencies/AppExceptions.

**Không kết luận agent hỏng chỉ vì dữ liệu chưa hiện ngay lập tức.** Có ingestion latency, sampling, time filter, resource/connection string sai, outbound network policy hoặc permissions. Tuy nhiên, không được che một cấu hình sai bằng câu "dữ liệu sẽ tới sau" nếu chưa xác minh logs/agent.

## 11. Triển khai instrumentation trên Azure App Service

Với Spring Boot trên **Azure App Service Java SE**, agent phải được đưa vào môi trường runtime theo hướng dẫn tương ứng; với **custom container**, có thể đóng agent vào image hoặc dùng phương án instrumentation được hỗ trợ.

~~~text
CI build Spring Boot JAR
         |
         v
Azure App Service Java SE
         |
         +-- Java runtime/JDK được hỗ trợ
         +-- Azure Monitor Java instrumentation
         +-- Application Insights connection string trong App Settings
         +-- Managed identity / Key Vault nếu cần
         |
         v
Log Analytics workspace
~~~

### Những phần phải xác minh

- Đúng Application Insights resource/connection string cho **dev, staging, production**; không gửi lẫn telemetry.
- Nếu dùng **Java agent tự quản**, file agent thực sự tồn tại tại đường dẫn và startup command/JAVA_TOOL_OPTIONS đưa agent vào đúng JVM.
- Nếu App Service cung cấp **agent/codeless integration**, hiểu phiên bản, khả năng tự cấu hình và tránh bật agent trùng với tự đóng gói.
- App được phép kết nối **ingestion endpoints**, DNS/TLS và cấu hình proxy/firewall không chặn.
- **Application role name, role instance, environment, release version** được gắn nhất quán trong telemetry.
- Health Check không bị ảnh hưởng đáng kể bởi overhead của instrumentation.

**Không thêm cùng lúc hai Java monitoring agents chỉ vì muốn "có nhiều dữ liệu hơn"** nếu chưa kiểm chứng khả năng tương thích; có thể nhân đôi telemetry hoặc làm tăng startup time.

## 12. Triển khai trên Azure Container Apps

Với **Container Apps**, cách thông dụng là đóng Java application và agent được phê duyệt vào OCI image hoặc dùng phương thức OTel/collector phù hợp môi trường.

Dockerfile **minh họa** nếu agent đã được tải về, kiểm tra integrity và lưu trong build context do tổ chức kiểm soát:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app

COPY --chown=10001:10001 target/orders-api.jar /app/orders-api.jar
COPY --chown=10001:10001 observability/applicationinsights-agent.jar \
     /opt/observability/applicationinsights-agent.jar

USER 10001:10001
EXPOSE 8080

ENV JAVA_TOOL_OPTIONS="-javaagent:/opt/observability/applicationinsights-agent.jar"
ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

**Bản Dockerfile chỉ chạy được khi đã có đúng artifacts**, không tự tải agent, không pin agent version/digest trong ví dụ. Trong production phải pin base image và agent, scan SBOM/CVEs, chạy non-root, giữ connection string ngoài image.

### Cấu hình ứng dụng

~~~text
Container App: orders-api-prod
  APPINSIGHTS_RESOURCE: production instance
  APPLICATIONINSIGHTS_CONNECTION_STRING: injected via app configuration
  OTEL_SERVICE_NAME: orders-api
  APP_VERSION: 2.4.1
~~~

Các dòng trên là **mô tả cấu hình**, không phải deployment schema. Biến môi trường được tiêm theo secret/env cơ chế của ACA; tránh commit value thật vào YAML hoặc image.

### Revisions và role names

Khi hai revisions cùng chạy để canary, cần phân biệt **app version/revision** trong attributes/logs. Nếu cùng cloud role name, Application Map có thể nhóm cả hai vào một node; đó thường là điều mong muốn ở cấp service. Để chẩn đoán regression, dùng thêm **version/revision dimension** có cardinality được kiểm soát.

## 13. AKS và OpenTelemetry Collector

Trên **AKS**, có thể instrument từng Java pod bằng agent, xuất trực tiếp sang Azure Monitor khi được hỗ trợ hoặc gửi đến **OpenTelemetry Collector** đã được đội platform quản lý.

~~~mermaid
flowchart LR
    P1[orders-api Pod] --> C[OTel Collector]
    P2[payment-api Pod] --> C
    W[worker Pod] --> C
    C --> M[Azure Monitor]
    M --> L[Log Analytics]
~~~

### Khi xuất trực tiếp

- Cấu hình ingestion credentials/connection string hoặc Entra-based authentication được exporter hỗ trợ.
- Quy định sampling/attribute filtering tại app/agent.
- Kiểm tra egress TLS/DNS/proxy và network policies.
- Mỗi pod gắn **service.name, service.version, deployment.environment.name** theo conventions được hỗ trợ.

### Khi qua Collector

- Collector cần tài nguyên CPU/RAM, autoscaling và batch/retry policy.
- Có thể lọc/redact dữ liệu, điều chỉnh exporter và định tuyến ra nhiều backends.
- Network failure/backpressure có thể gây **drop telemetry**; Collector không phải nguồn dữ liệu giao dịch bền vững mặc định.
- Cần chọn architecture (DaemonSet, Deployment, sidecar) phù hợp và bảo vệ cổng OTLP.
- Không gửi raw tokens/password qua Collector như attribute hoặc log.

**OTel Collector không bắt buộc cho mọi AKS workload.** Nó là một thành phần cần vận hành; với đội nhỏ, agent được hỗ trợ xuất trực tiếp có thể đơn giản hơn.

## 14. Azure Functions, background workers và Functions host

**Azure Functions Java** có function host và Java worker theo programming model riêng. Telemetry từ host invocation/binding và spans do Java code tự tạo có thể đi qua những pipeline khác nhau.

### Khi cấu hình quan sát Function

1. Xác minh Application Insights integration của **Function App** và hosting plan.
2. Kiểm tra host logs/function executions, retries, failures.
3. Nếu thêm OpenTelemetry SDK/agent vào Java worker, kiểm tra tính tương thích và tránh gửi telemetry trùng host.
4. Propagate context từ Service Bus/Event Hubs message theo bindings/SDK được hỗ trợ.
5. Ghi business outcome và idempotency conflicts riêng với host invocation success.

Một **Function invocation thành công** không tự chứng minh message dẫn đến DB commit và email gửi được, nếu function đã bắt exception rồi tiếp tục hoặc gọi downstream bất đồng bộ không được await. Phải kiểm tra đúng thứ tự settlement/retry và status nghiệp vụ.

## 15. Dependency telemetry: đặc tính cần thu

Một dependency là hoạt động của service **gọi tới một bên ngoài process** hoặc subsystem quan trọng. Với một call, nên có:

| Thuộc tính | Ví dụ | Ghi chú |
|---|---|---|
| **Dependency type** | HTTP, SQL, Redis, Service Bus | Dùng semantic conventions |
| **Name** | GET /payments/{id}, SELECT orders | Tránh tên chứa user ID |
| **Target** | payment-api.internal, orders-db | Không ghi connection string/password |
| **Duration** | 280 ms | Hỗ trợ latency and critical-path |
| **Result code** | HTTP 503, SQL error code | Phân loại lỗi |
| **Success/status** | true/false hoặc status code | Theo semantic conventions, không mặc định mọi 4xx là lỗi hệ thống |
| **Trace/span context** | trace ID, parent span | Để ghép với request gốc |
| **Retry attempt** | 0,1,2 | Nếu thêm custom dimension, kiểm soát cardinality |
| **Service version/environment** | orders-api 2.4.1 prod | Dùng attributes ổn định |

### Những thông tin không nên thu tự do

- Toàn bộ SQL chứa literals/customer IDs.
- HTTP Authorization header hoặc Set-Cookie.
- Request/response bodies chứa PII.
- Database connection strings/SAS tokens.
- URL chứa email, số điện thoại, payment tokens, access key.
- Full message payload của Service Bus nếu có dữ liệu khách hàng.

**Tên dependency nên có cardinality thấp**, ví dụ **GET /orders/{id}** thay vì mỗi order ID tạo một dependency name riêng. Điều này giảm chi phí và giúp dashboard không quá nhiều series.

## 16. HTTP dependencies trong Spring Boot

Khi Spring Boot gọi **payment-api** bằng RestClient/WebClient/HttpClient được instrumentation hỗ trợ, agent có thể tạo **HTTP CLIENT span**.

~~~text
Incoming:
  POST /api/orders
    |
    +-- HTTP CLIENT POST payment-api /charge
            duration=980 ms
            http.response.status_code=503
            status=ERROR hoặc result logic theo instrumentation
~~~

### Ví dụ RestClient với timeout

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import java.net.http.HttpClient;
import java.time.Duration;

public final class PaymentGateway {
    private final RestClient client;

    public PaymentGateway(String baseUrl) {
        HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

        JdkClientHttpRequestFactory factory =
            new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(Duration.ofSeconds(5));
        this.client = RestClient.builder()
            .baseUrl(baseUrl)
            .requestFactory(factory)
            .build();
    }

    public String charge(String requestJson) {
        return client.post()
            .uri("/charge")
            .contentType(MediaType.APPLICATION_JSON)
            .body(requestJson)
            .retrieve()
            .body(String.class);
    }
}
~~~

**Đây là skeleton về dependency call, không phải HTTP client production hoàn chỉnh.** Mẫu dùng **RestClient và JdkClientHttpRequestFactory** (Spring Framework 6.1+/Spring Boot version tương thích), đã gắn connect timeout 3 giây và read timeout 5 giây vào request factory, nhưng chưa áp một **overall deadline** cho toàn bộ retries/business operation. Trong ứng dụng thực còn cần retry/backoff, TLS, authentication, cancellation, connection reuse và các giới hạn riêng theo Spring Framework/HTTP client version.

### Dependency failure không phải endpoint failure tự động

Một API có thể nhận 503 từ payment-api nhưng sử dụng **fallback, queue hoặc pending status** hợp lệ để trả 202. Dependency span nên thể hiện lỗi call, nhưng request span có thể thành công theo business contract. Ngược lại, việc **nuốt** timeout rồi trả 200 và báo "thanh toán thành công" là lỗi nghiệp vụ.

## 17. SQL/JDBC dependencies

Với PostgreSQL/Azure SQL và JDBC/Spring Data JPA, instrumentation được hỗ trợ có thể tạo dependency spans cho DB calls.

~~~text
POST /api/orders (SERVER)
    |
    +-- jdbc: SELECT carts (...)      15 ms
    +-- jdbc: INSERT orders (...)     31 ms
    +-- jdbc: UPDATE inventory (...)  80 ms
~~~

### Phân biệt SQL chậm và connection pool chờ

Một request tốn 2 giây không nhất thiết SQL query chạy 2 giây. Có thể:

~~~text
Wait for HikariCP connection: 1.700 ms
Execute SQL query:             100 ms
Serialize response:             40 ms
--------------------------------------
Total:                        1.840 ms
~~~

Nếu auto-instrument chỉ thấy **JDBC SQL 100 ms**, request vẫn chậm do **pool acquisition** trước đó. Cần đo metrics **Hikari active/idle/pending/timeout**, transaction timeouts, thread pools và custom spans hợp lý.

### SQL query text an toàn

Không bật full SQL parameter logging production nếu query có PII. Với JDBC spans, giữ **DB system, operation, safe statement template, server address** theo chính sách; không ghi password hoặc literal có dữ liệu nhạy cảm.

### @Transactional

~~~java
@Transactional
public Order createOrder(CreateOrderCommand cmd) {
    Order order = repository.save(...);
    outboxRepository.save(...);
    return order;
}
~~~

Đây là pseudo-code; **@Transactional** quản lý transaction của data store phù hợp, không tự commit Service Bus message và không biến toàn bộ HTTP + payment call thành một giao dịch nguyên tử. Application tracing theo dõi các bước và transaction status riêng.

## 18. Redis/Storage/Service Bus dependencies

Cùng một request có thể gọi:

- **Azure Cache/Redis** để đọc cache/lock.
- **Azure Blob Storage** để lưu file/chứng từ.
- **Azure Service Bus** để publish message.
- **Event Hubs/Cosmos DB/Azure OpenAI** cho các workload tương ứng.

~~~text
POST /orders
   +-- Redis GET cart          3 ms
   +-- PostgreSQL INSERT      20 ms
   +-- ServiceBus SEND        45 ms
   +-- Blob UPLOAD           150 ms
~~~

### Phải xác minh instrumentation hỗ trợ từng SDK

OpenTelemetry Java auto-instrumentation hỗ trợ nhiều thư viện, nhưng **không bao phủ mọi Azure SDK version hoặc mọi async callback** theo cùng một cách. Nếu chưa thấy Service Bus dependency:

1. Kiểm tra agent/version và thư viện được dùng.
2. Kiểm tra exporter/ingestion/correlation.
3. Kiểm tra asynchronous context propagation.
4. Nếu framework không hỗ trợ, thêm **custom span** bao quanh thao tác gửi/nhận theo semantic conventions.
5. Không tạo trùng spans nếu instrument bản thủ công và agent cùng lúc.

### Broker accepted khác business processed

Service Bus **Send succeeded** nghĩa broker nhận message theo semantics; **không chứng minh** worker đã xử lý và database đã commit. Muốn đo từ request → invoice created, cần consumer spans, business events và correlation key.

## 19. Dependency retries, timeouts và circuit breaker

Ví dụ một request tới payment-api bị retry:

~~~text
GET /payment-status (SERVER) 6.3 s
   |
   +-- payment-api GET attempt 1: 2.0 s timeout
   +-- delay: 200 ms
   +-- payment-api GET attempt 2: 2.0 s timeout
   +-- delay: 500 ms
   +-- payment-api GET attempt 3: 1.6 s HTTP 200
~~~

**Có thể quan sát ba dependency attempts cho một request.** Nếu nhìn duy nhất dependency success rate, tỷ lệ lỗi có thể cao mặc dù end-user request trả 200; nếu nhìn chỉ request success, bạn bỏ qua tín hiệu sắp quá tải.

### Những gì cần đo

| Metric/signal | Ý nghĩa |
|---|---|
| Number of attempts per request | Retry amplification |
| Retry-after/backoff time | Latency chờ |
| Final outcome | User-visible result |
| Circuit breaker state | OPEN/HALF_OPEN/CLOSED theo implementation |
| Timeout type | Connect, read, overall deadline |
| Dependency target | Đích nào liên tục lỗi |
| Upstream duration | Critical path |

Không dùng retry vô hạn hoặc đồng thời nhiều replicas retry đồng loạt; tạo **retry storm**. Dùng exponential backoff + jitter, bounded overall deadline và circuit breaker/bulkhead khi thích hợp.

### Span status không phải bản án nghiệp vụ

Một retry HTTP 503 có thể được ghi error, final success được ghi success. Điều quan trọng là **không diễn giải mọi failed dependency như failed transaction**, và ngược lại không che lượng retries bất thường chỉ vì transaction cuối cùng thành công.

## 20. Exception telemetry: exception nào cần ghi?

Một **exception** có thể là:

- Lỗi chưa xử lý làm request trả 5xx.
- Lỗi được bắt để retry hoặc fallback.
- Lỗi do input không hợp lệ, ánh xạ thành 400/422.
- Lỗi nghiệp vụ được thể hiện bằng domain result thay vì exception.
- Lỗi async task bị nuốt, không đi tới HTTP request.

| Tình huống | HTTP/API outcome | Cần quan sát |
|---|---|---|
| NullPointerException chưa xử lý | Thường 500 | Exception stack + request trace |
| Payment timeout, đã fallback pending | Có thể 202 | Dependency failure, exception, business pending |
| ValidationException | 400/422 | Client error rate; có thể không cần exception stack mỗi lần |
| Authorization denied | 401/403 | Security telemetry, không lộ token |
| Queue worker throws | Không có HTTP response tương ứng | Consumer trace, retry/DLQ, error event |
| Exception caught and suppressed | Có thể 200 nhưng sai nghiệp vụ | Phải instrument/log có chủ đích |

**Không log một exception nhiều lần ở mọi tầng** (repository, service, controller, global handler) nếu cùng một lỗi; điều này làm tăng log volume và tạo cảm giác có nhiều sự cố. Thông thường nên log exception một lần tại boundary có đủ ngữ cảnh, đồng thời ghi span status/exception event đúng lúc cần.

## 21. Xử lý exceptions trong Spring Boot

Spring Boot có thể dùng **@RestControllerAdvice** để chuyển exceptions thành phản hồi HTTP có cấu trúc. Đừng để stack trace/SQL error lộ ra frontend.

~~~java
package com.example.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(PaymentTimeoutException.class)
    public ProblemDetail paymentUnavailable(PaymentTimeoutException ex) {
        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_GATEWAY);
        problem.setTitle("Payment service unavailable");
        problem.setDetail("Try again later or check order status.");
        return problem;
    }
}
~~~

**PaymentTimeoutException là type do dự án tự định nghĩa**; ví dụ chưa phải project hoàn chỉnh. Với Spring Boot/Spring Framework version phù hợp, **ProblemDetail** hỗ trợ chuẩn thông báo lỗi HTTP. Trong production cần chọn **502/503/504** theo semantics thật, ghi exception với correlation ID tại nơi thích hợp, và cân nhắc xử lý timeout thành trạng thái **PENDING** thay vì luôn trả lỗi.

### Phân biệt handled exception và unhandled exception

Nếu exception đã được handler bắt và chuyển thành ProblemDetail, một số instrumentation có thể **không tự ghi exception event** dù HTTP status là 502; cần kiểm chứng. Nếu cần, ghi exception một lần có kiểm soát trong tracing/logging layer. Không ép mọi validation exception thành span ERROR nếu nó là lỗi đầu vào dự kiến theo business contract.

### Tách lỗi dự kiến và lỗi vận hành

- **Validation/business reject:** trả 400/409/422 theo API contract, metric riêng; không cần stack trace vô hạn.
- **Transient dependency outage:** có retry/fallback có giới hạn, alert theo tần suất và tác động.
- **Programming error:** exception stack và release version để truy nguyên.
- **Security failure:** giữ log tối thiểu, không log access tokens hoặc body nhạy cảm.

## 22. Custom spans cho bước nghiệp vụ

Auto-instrumentation có thể thấy HTTP/JDBC calls nhưng không biết bước **validate voucher**, **reserve inventory** hoặc **calculate shipping**. Custom spans hữu ích để đặt các bước quan trọng vào trace.

Ví dụ sử dụng **OpenTelemetry API**:

~~~java
package com.example.orders;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class PriceCalculator {

    private static final Tracer TRACER =
        GlobalOpenTelemetry.getTracer("orders-domain", "1.0.0");

    public long calculateCents(int itemCount) {
        Span span = TRACER.spanBuilder("order.calculate-price")
            .setSpanKind(SpanKind.INTERNAL)
            .startSpan();
        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("order.item_count", itemCount);
            if (itemCount < 0) {
                throw new IllegalArgumentException("Invalid item count");
            }
            return itemCount * 1200L;
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

Đoạn code có thể biên dịch khi dependency **io.opentelemetry:opentelemetry-api** tương thích được khai báo và Java version phù hợp; ví dụ giá cố định chỉ minh họa logic domain. **API không tự cung cấp exporter**: cần SDK/agent đã được cấu hình để spans đi tới Azure Monitor. Nếu GlobalOpenTelemetry chưa khởi tạo, calls có thể là no-op.

### Lưu ý khi đặt custom attributes

Nên dùng:

~~~text
order.item_count = 3
order.channel = "web"
order.validation_result = "accepted"
order.version = 2
~~~

Tránh:

~~~text
order.customer_email = "person@example.com"
payment.card_number = "<SENSITIVE>"
http.request.body = "<RAW_CUSTOMER_DATA>"
order.id = "<MILLIONS_OF_UNIQUE_VALUES_AS_METRIC_LABEL>"
~~~

Một order ID có thể hữu ích khi điều tra nhưng dễ thành PII/high-cardinality dimension. Nếu cần correlation, dùng opaque ID với governance/retention, không đưa vào **metric labels** hoặc truy vấn public.

## 23. OpenTelemetry status và exception recording

Trong OpenTelemetry:

- **span.recordException(exception)** ghi exception event vào span.
- **span.setStatus(StatusCode.ERROR)** đánh dấu lỗi span theo ý nghĩa nghiệp vụ/kỹ thuật.
- **span.end()** kết thúc span để exporter có cơ hội xuất.

### Ba tình huống

**A. Exception chưa được xử lý:** record exception và status ERROR trước khi ném tiếp, hoặc để instrumentation boundary làm việc đó; tránh record trùng.

**B. Exception được bắt và fallback thành công:** có thể ghi dependency span thất bại, nhưng **transaction span** cuối phản ánh fallback success hoặc degraded state hợp lệ.

**C. Business reject bình thường:** ví dụ voucher hết hạn có thể là 409/422 và custom event/metric, không nhất thiết là programming exception.

**Không đánh giá chất lượng ứng dụng chỉ bằng số exception telemetry.** Có ứng dụng bắt lỗi nhưng trả 200 sai, và ứng dụng ghi nhiều exception đã được xử lý hợp lệ.

## 24. Micrometer Observation trong Spring Boot

Spring Boot hỗ trợ **Micrometer Observation/Tracing** theo version và dependencies được cấu hình. Việc instrument bằng **Observation API** cho phép ghi duration/context của hoạt động nghiệp vụ.

Ví dụ ý tưởng:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class OrderValidator {
    private final ObservationRegistry registry;

    public OrderValidator(ObservationRegistry registry) {
        this.registry = registry;
    }

    public boolean validate(int count) {
        return Observation.createNotStarted("order.validate", registry)
            .lowCardinalityKeyValue("order.channel", "api")
            .observe(() -> count > 0);
    }
}
~~~

**Micrometer observation không đồng nghĩa tự có span trong Azure**: cần tracing bridge/exporter/agent configuration tương ứng. Khi kết hợp Micrometer với auto-instrumentation, kiểm chứng trace context và tránh ghi hai spans cho cùng một bước nếu gây trùng.

### Low vs high cardinality

- **Low cardinality:** http.route, outcome, dependency type, service.version (giới hạn).
- **High cardinality:** userId, raw orderId, URL chứa query string, messageId.

Metric series có thể bùng nổ chi phí/bộ nhớ nếu dùng hàng triệu giá trị nhãn. Traces có thể chứa nhiều ngữ cảnh hơn, nhưng vẫn phải tuân thủ quy định bảo vệ dữ liệu và lưu trữ.

## 25. Context propagation qua threads và async

Trong ứng dụng Spring Boot, xử lý thường chuyển từ HTTP thread sang:

- **CompletableFuture / ExecutorService**.
- **@Async**.
- **Project Reactor/WebFlux**.
- **Kafka/Service Bus listeners**.
- Batch jobs hoặc schedulers.

Trace context đôi khi được lưu trong **ThreadLocal** hoặc context abstraction tương đương. Khi tạo thread mới không qua context-aware executor, span mới có thể mất parent.

~~~text
HTTP SERVER trace T
     |
     +-- @Async worker không propagate context
            |
            +-- new root trace T2 [đứt correlation]
~~~

### Hướng xử lý

1. Ưu tiên framework integrations được agent/OTel instrumentation hỗ trợ.
2. Với custom Executor, dùng context wrapping/TaskDecorator được framework khuyến nghị.
3. Với Reactor, dùng context propagation theo phiên bản framework phù hợp.
4. Không tự lưu một **Span hoặc Scope lâu dài** trong singleton bean chia sẻ giữa requests.
5. Khi message async đến muộn, dùng messaging extraction/links đúng semantics.
6. Kiểm thử trace tree thực tế, không chỉ unit test return value.

### Một dấu hiệu context bị mất

Trong Application Insights, payment-api hiện như một **root request độc lập** dù orders-api đã gọi nó; trace IDs khác nhau. Nguyên nhân có thể là proxy bỏ W3C headers, HTTP client không instrument, async context mất hoặc service downstream không extract context.

## 26. Structured logs và correlation

Logs chỉ thực sự liên kết với traces nếu có thông tin tương quan:

~~~json
{
  "timestamp": "2026-11-20T10:12:30Z",
  "level": "WARN",
  "service": "orders-api",
  "traceId": "1234567890abcdef1234567890abcdef",
  "spanId": "1111111111111111",
  "event": "payment_retry",
  "attempt": 2,
  "dependency": "payment-api",
  "errorClass": "TimeoutException"
}
~~~

Đây là **log minh họa**; nó không tự xuất hiện chỉ vì cài Actuator. Cần logging pattern/JSON encoder/OTel log correlation phù hợp. Với SLF4J MDC, context có thể phải được giữ và làm sạch đúng khi async.

### Không log payload theo mặc định

Một request **POST /checkout** có thể chứa địa chỉ, số điện thoại hoặc dữ liệu thanh toán. Những nội dung này không cần thiết để đếm lỗi/latency và có thể khiến logs thành kho dữ liệu nhạy cảm ngoài kiểm soát.

Giữ **service, operation name, status/error category, trace ID, deployment version**; redaction và restricted diagnostics chỉ bật khi có quyền, mục đích và thời hạn rõ.

## 27. Sampling: vì sao có request mà không thấy trace?

Sampling giúp giảm volume/cost nhưng làm một số traces không xuất hiện trong truy vấn.

| Cơ chế | Ý tưởng | Trade-off |
|---|---|---|
| **Head-based sampling** | Quyết định thu trace sớm, có thể dựa parent flags | Ít overhead, có thể bỏ sót lỗi hiếm |
| **Tail-based sampling** | Quyết định sau khi có outcome/duration nếu pipeline hỗ trợ | Collector/storage/phức tạp và độ trễ |
| **Adaptive/ingestion sampling** | Điều chỉnh tỷ lệ theo khả năng sản phẩm | Kết quả có thể lệch nếu đọc raw counts |
| **No sampling** | Giữ toàn bộ telemetry | Chi phí cao, có thể quá tải |

### Ví dụ

Nếu sampling giữ 10% traces và có 1.000 requests, bạn có thể chỉ thấy khoảng 100 request records trong trace analytics. **Không dùng COUNT() của dữ liệu sampled rồi tuyên bố có đúng 100 requests thực**.

### ItemCount trong Application Insights

Một số bảng Application Insights có trường **ItemCount** giúp ước tính số records được đại diện bởi một sampled record. Khi phù hợp, có thể dùng **sum(ItemCount)** cho counts tổng thay vì count(). Tuy nhiên:

- Ý nghĩa ItemCount phụ thuộc pipeline và sampling mode.
- Tail sampling/filtering có thể không được tái tạo chính xác bằng weighting.
- Percentiles và joins của sampled traces có thể sai lệch.
- Một số custom metrics hoặc metrics độc lập với traces có chính sách sampling khác.

**SLO và billing** nên dựa trên metrics/counters đã được thiết kế đúng, không phụ thuộc hoàn toàn vào việc khôi phục count từ traces.

## 28. Log Analytics schemas: AppRequests và các bảng khác

Với **workspace-based Application Insights**, những bảng thường gặp trong **Log Analytics** gồm:

| Bảng | Dữ liệu |
|---|---|
| **AppRequests** | Request telemetry, duration, result code, operation |
| **AppDependencies** | Outgoing dependency calls, target, duration, success |
| **AppExceptions** | Exception type/message/details, operation correlation |
| **AppTraces** | Log/trace messages và severity |
| **AppEvents** | Custom events nếu exporter/SDK ghi |
| **AppMetrics** | Custom metrics/telemetry theo pipeline |

Trong một số **Application Insights classic analytics** hoặc tài liệu legacy, bạn có thể gặp các bảng **requests, dependencies, exceptions, traces** với tên cột khác. **Đừng copy một KQL query dùng AppRequests rồi chạy trong schema requests mà không chuyển tên cột.**

### Những cột hữu ích ở workspace-based tables

~~~text
TimeGenerated       thời điểm telemetry
OperationId         ID để ghép operation/trace
Id / ParentId       span/request identity và quan hệ
AppRoleName         service/application role
Name                request/dependency name
DurationMs          duration theo milliseconds
Success             true/false theo telemetry
ResultCode          HTTP/SQL/result code
ItemCount           weighting khi sampling có hỗ trợ
Properties          custom fields động
~~~

Các cột có mặt tùy bảng, SDK và ingestion pipeline; **ResultCode** có thể mang kiểu string và **Properties** có dynamic shape. Phải xem schema thực của workspace trước khi xây dashboard chính thức.

## 29. KQL: request rate và lỗi 5xx

Trong **Logs** của workspace-based Application Insights:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize
    Requests = sum(ItemCount),
    FailedTelemetry = sumif(ItemCount, Success == false),
    ServerErrors = sumif(ItemCount,
        toint(ResultCode) >= 500 and toint(ResultCode) < 600)
  by bin(TimeGenerated, 5m)
| extend ErrorRatePct =
    iff(Requests > 0, 100.0 * ServerErrors / Requests, real(null))
| order by TimeGenerated asc
~~~

### Cách đọc

- **Requests** là tổng ước tính khi ItemCount phù hợp.
- **FailedTelemetry** theo flag Success của telemetry; có thể bao gồm những loại thất bại khác HTTP 5xx.
- **ServerErrors** theo HTTP 5xx.
- **ErrorRatePct** chỉ là tỷ lệ 5xx ở request telemetry hiện diện, không tự phản ánh business failure.

**Kiểm tra schema và sampling trước khi kết luận**. Nếu telemetry bị lọc, một số requests không instrument hoặc role name sai, biểu đồ có thể thiếu dữ liệu.

## 30. KQL: requests chậm theo endpoint

~~~kusto
AppRequests
| where TimeGenerated >= ago(24h)
| where AppRoleName == "orders-api"
| summarize
    ObservedRequests = count(),
    AvgDurationMs = avg(DurationMs),
    P50Ms = percentile(DurationMs, 50),
    P95Ms = percentile(DurationMs, 95),
    P99Ms = percentile(DurationMs, 99)
  by Name
| order by P95Ms desc
~~~

**Percentiles trên records đã sampled là percentiles của mẫu được lưu**, không chắc đại diện hoàn toàn cho tất cả requests khi sampling lệch. Nếu sản phẩm có built-in server duration metrics/percentile histograms hoặc metrics đúng chuẩn, ưu tiên chúng cho SLO; KQL ở đây hữu ích cho phân tích.

### Tránh cardinality cao

Nếu request **Name** bị tạo như:

~~~text
GET /orders/1001
GET /orders/1002
GET /orders/1003
~~~

thì mỗi URL động có thể thành một nhóm riêng. Instrumentation nên dùng **route templates**, ví dụ **GET /orders/{id}**, để phân tích ổn định và giảm dimension explosion.

## 31. KQL: dependency nào đang chậm hoặc thất bại?

~~~kusto
AppDependencies
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize
    ObservedCalls = count(),
    EstimatedCalls = sum(ItemCount),
    EstimatedFailures = sumif(ItemCount, Success == false),
    P95DurationMs = percentile(DurationMs, 95)
  by Type, Target, Name
| extend FailurePct =
    iff(EstimatedCalls > 0,
        100.0 * EstimatedFailures / EstimatedCalls, real(null))
| order by EstimatedFailures desc, P95DurationMs desc
~~~

### Diễn giải

Nếu kết quả cho thấy:

~~~text
Type=HTTP
Target=payment-api.internal
Name=POST /charge
FailurePct=18%
P95DurationMs=4200
~~~

thì đây là một điểm cần điều tra. **Không khẳng định payment-api hỏng 18% toàn hệ thống** nếu SDK chỉ instrument một số calls hoặc sampling/target grouping không đầy đủ. Đối chiếu logs của payment-api, gateway metrics và HTTP status.

### Khi Target khác nhau vì hostname

Một API có thể được gọi qua internal DNS, APIM và public hostname; nếu không chuẩn hóa cloud role/service naming, Application Map có thể xem chúng là những dependencies khác nhau. Không sửa bằng cách ghi đè target tùy tiện; cần giữ đủ ngữ cảnh route thật và mapping service đáng tin.

## 32. KQL: so sánh dependency success với request success

~~~kusto
let Requests =
    AppRequests
    | where TimeGenerated >= ago(30m)
    | where AppRoleName == "orders-api"
    | summarize Requests = sum(ItemCount),
                FailedRequests = sumif(ItemCount, Success == false);
let Dependencies =
    AppDependencies
    | where TimeGenerated >= ago(30m)
    | where AppRoleName == "orders-api"
    | summarize Calls = sum(ItemCount),
                FailedCalls = sumif(ItemCount, Success == false);
Requests
| extend JoinKey = 1
| join kind=inner (Dependencies | extend JoinKey = 1) on JoinKey
| project Requests, FailedRequests, Calls, FailedCalls,
          RequestFailurePct = iff(Requests > 0,
              100.0 * FailedRequests / Requests, real(null)),
          DependencyFailurePct = iff(Calls > 0,
              100.0 * FailedCalls / Calls, real(null))
~~~

Đây là so sánh **hai tín hiệu khác mẫu số**, không phải một tỷ lệ quy đổi: một request có thể gọi 10 dependencies, retries làm số calls tăng, và nhiều requests không có dependency nào. Nó giúp phát hiện dependency bắt đầu lỗi nhiều hơn **trước khi** end-user error rate tăng.

### Ví dụ cách diễn giải

- Request failures thấp, dependency failures cao: có fallback/retry hoặc lỗi được che.
- Request failures cao, dependency failures thấp: có thể lỗi validation, serialization, CPU/thread pool, local code.
- Cả hai tăng: tập trung dependency target và critical path.

## 33. KQL: nhóm exceptions theo type và service

~~~kusto
AppExceptions
| where TimeGenerated >= ago(24h)
| summarize
    EstimatedOccurrences = sum(ItemCount),
    ObservedRows = count(),
    AffectedTraces = dcount(OperationId)
  by AppRoleName, Type, ProblemId
| order by EstimatedOccurrences desc
~~~

### Phân tích đúng

- **Type:** loại exception, ví dụ SocketTimeoutException.
- **ProblemId:** fingerprint/grouping có thể giúp nhóm lỗi tương tự, tùy SDK.
- **AffectedTraces:** số trace IDs khác nhau trong dữ liệu **đã quan sát**, không tự bằng số users bị ảnh hưởng.
- **EstimatedOccurrences:** ước tính khi ItemCount thực sự dùng cho sampling.

Nếu cùng exception xuất hiện trong nhiều services, một trace có thể có nhiều exception records. **Đừng cộng AffectedTraces giữa groups rồi coi là số requests duy nhất**.

### Khi bảng AppExceptions rỗng

Có thể do không có exception, agent chưa instrument, exception đã được catch, pipeline lọc/sampled hoặc đang xem sai resource/time. Hãy so sánh **AppRequests 5xx, AppTraces ERROR, platform logs** và thử một lỗi lab có kiểm soát.

## 34. KQL: tìm exception của một trace cụ thể

Nếu lấy được **OperationId** từ request bị lỗi:

~~~kusto
let traceId = "1234567890abcdef1234567890abcdef";
AppExceptions
| where TimeGenerated >= ago(24h)
| where OperationId == traceId
| project TimeGenerated, AppRoleName, Type, ProblemId,
          OuterMessage, OperationId
| order by TimeGenerated asc
~~~

**OuterMessage có thể chứa PII hoặc SQL details.** Chỉ truy cập trong workspace được phân quyền; dashboard public nên bỏ cột này hoặc redaction, không xuất toàn bộ message lên Slack/email alert.

### Khi có nhiều exceptions

Một HTTP request có thể retry payment 3 lần, tạo 3 SocketTimeoutException, rồi thành công. Dùng timeline/dependencies để biết **thứ tự và final result**, không coi ba exceptions bằng ba giao dịch thất bại.

## 35. KQL: ghép request, dependency và exception theo operation

Ví dụ xem timeline trong **một trace ID** đã biết:

~~~kusto
let traceId = "1234567890abcdef1234567890abcdef";
union
(
    AppRequests
    | where TimeGenerated >= ago(24h) and OperationId == traceId
    | project TimeGenerated, Kind = "REQUEST",
              Service = AppRoleName,
              Label = Name,
              Result = ResultCode,
              DurationMs,
              OperationId
),
(
    AppDependencies
    | where TimeGenerated >= ago(24h) and OperationId == traceId
    | project TimeGenerated, Kind = "DEPENDENCY",
              Service = AppRoleName,
              Label = Name,
              Result = ResultCode,
              DurationMs,
              OperationId
),
(
    AppExceptions
    | where TimeGenerated >= ago(24h) and OperationId == traceId
    | project TimeGenerated, Kind = "EXCEPTION",
              Service = AppRoleName,
              Label = Type,
              Result = "",
              DurationMs = real(null),
              OperationId
)
| order by TimeGenerated asc
~~~

### Điểm mạnh và giới hạn

- Dễ thấy **trình tự thời gian** của cùng một trace.
- Không thể hiện đầy đủ **cha–con** nếu chỉ order theo thời gian; có thể bổ sung Id/ParentId hoặc xem end-to-end trace UI.
- Các spans có thể chạy song song, thứ tự TimeGenerated không chứng minh causality.
- Nếu sampling thiếu child span, timeline không đầy đủ.
- Nếu trace context đứt, payment-api có OperationId khác và sẽ không xuất hiện.

**OperationId trong workspace-based Application Insights** thường được dùng để correlate các bản ghi cùng operation. Xác minh với pipeline của bạn trước khi xây logic phụ thuộc một định dạng cột cố định.

## 36. KQL: tìm transaction chậm nhất để điều tra

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| where AppRoleName == "orders-api"
| where Name == "POST /api/orders"
| top 20 by DurationMs desc
| project TimeGenerated, OperationId, Name, DurationMs,
          ResultCode, Success, AppRoleName
~~~

Chọn một **OperationId** từ kết quả, dùng query ở mục 35 hoặc mở **End-to-end transaction details**.

### Phân tích critical path

Giả sử:

~~~text
HTTP SERVER POST /orders  4.8 s
  +-- SQL 0.03 s
  +-- Redis 0.01 s
  +-- Payment HTTP 4.5 s
  +-- Serialization 0.02 s
~~~

Suy luận mạnh hơn "Azure SQL chậm" là **payment HTTP chiếm phần lớn request latency**. Nhưng để kết luận, phải xem trace thật, retries, scheduling, queue waits và khoảng thời gian chồng lấn.

## 37. KQL: theo dõi exceptions sau một lần triển khai

Giả sử vừa release **orders-api v2** và cần so sánh số lỗi:

~~~kusto
AppExceptions
| where TimeGenerated >= ago(2h)
| where AppRoleName == "orders-api"
| summarize
    EstimatedExceptions = sum(ItemCount)
  by bin(TimeGenerated, 5m), Type
| render timechart
~~~

### Nếu cần phân biệt v1/v2

Instrument thêm **service.version** hoặc deployment/revision attribute với cách ánh xạ vào Application Insights **Properties** được SDK hỗ trợ. Không khẳng định cột version có tên cố định; kiểm tra dữ liệu thực rồi thêm **by Version** phù hợp.

### Không chỉ nhìn exception count

Khi traffic tăng gấp 10 lần, exception count có thể tăng dù **error rate** giữ nguyên. So sánh requests, failures, latency và business outcome theo cùng deployment/time window.

## 38. KQL: kiểm tra traces/logs gắn OperationId

~~~kusto
let traceId = "1234567890abcdef1234567890abcdef";
AppTraces
| where TimeGenerated >= ago(24h)
| where OperationId == traceId
| project TimeGenerated, AppRoleName, SeverityLevel,
          Message, OperationId
| order by TimeGenerated asc
~~~

Các dòng **WARN payment retry**, **ERROR database transaction failed**, **INFO order pending** có thể cung cấp ngữ cảnh mà spans chưa mô tả.

### Cần phân biệt log severity và request outcome

Một HTTP request 200 có thể có WARN do retry thành công; một HTTP 500 có thể không có ERROR log nếu logging bị sai. Không tính SLO trực tiếp từ số dòng ERROR thay cho HTTP/server metrics.

## 39. Application Map: biết service nào gọi service nào

**Application Map** có thể hiển thị các application components/dependencies từ telemetry có correlation:

~~~text
orders-web
   |
   v
orders-api  --HTTP--> payment-api
   |
   +--SQL--> orders-db
   +--Redis-> cache
   +--Queue-> Service Bus
                |
                v
            invoice-worker
~~~

Để map đúng:

- Đặt **cloud role/service name** ổn định cho mỗi ứng dụng.
- Truyền **W3C trace context** qua HTTP/messaging.
- Tránh tất cả services dùng chung role name **app** mặc định.
- Cấu hình connection string/resource tương ứng và kiểm tra cross-resource visibility.
- Có quyền xem Application Insights/workspace của các services liên quan.

**Một map node biến mất không chứng minh service bị xóa hoặc không còn hoạt động.** Có thể do traffic không phát sinh, sampling, instrumentation không hỗ trợ, changed role names hoặc ingestion issues.

## 40. End-to-end transaction diagnostics

Với một request bị lỗi:

1. Mở Application Insights **Failures** hoặc **Performance/Transaction search**.
2. Chọn operation có time range và status đúng.
3. Mở **End-to-end transaction details** hoặc distributed trace view đang được Portal cung cấp.
4. Xem **waterfall** và các dependency spans.
5. Tìm span dài nhất hoặc span có error/status bất thường.
6. Mở correlated exceptions/logs để thấy nguyên nhân cụ thể.
7. Xác minh business outcome trong database/queue (được phân quyền).
8. Ghi hypothesis, bằng chứng và phiên bản app; không chẩn đoán chỉ từ một ảnh waterfall.

### Hình dạng waterfall minh họa

~~~text
Time (ms):     0       1000      2000      3000      4000  5000
               |---------|---------|---------|---------|-----|
POST /orders   [============================================]
 SQL SELECT    [=]
 Redis GET      []
 payment HTTP  [--------------------------------------------]
 exception                                             [X]
 response                                             [504]
~~~

Nếu waterfall chứa nhiều child spans song song, xác định **critical path** thay vì cộng durations. Một DB dependency được báo chậm đôi khi chỉ do client request chờ connection pool; cần xem threads/pool metrics để phân biệt.

## 41. SLI, SLO và error budget

Observability tốt phải trả lời: **khách hàng có được phục vụ theo cam kết không?** Không chỉ trả lời service có log hay không.

### Ví dụ SLO

Đối với **POST /orders**:

- **Availability SLO:** 99,9% requests hợp lệ hoàn thành với kết quả theo API contract.
- **Latency SLO:** 95% requests phục vụ trong dưới 500 ms trong điều kiện định nghĩa.
- **Correctness SLI:** tỷ lệ đơn không bị tạo trùng và trạng thái thanh toán nhất quán.

**Đây là ví dụ SLO**, không phải SLA mặc định của Azure hay mọi ứng dụng. Phải quy định chính xác cửa sổ đo, allowed statuses, excluded traffic, bot traffic, client cancellations và thời điểm transaction thực sự hoàn thành.

### Error budget minh họa

Nếu SLO availability = 99,9%, error budget = 0,1%. Với **1.000.000 requests hợp lệ** trong cửa sổ:

~~~text
Allowed error requests = 1.000.000 × 0,001 = 1.000
~~~

Số liệu giả định, không bao hàm các lỗi business không đo bằng HTTP. Trong thực tế, **SLO error rate** nên dựa trên metric/counter đầy đủ, không chỉ từ sampled traces.

### Tại sao phải có error budget?

Khi error budget cạn nhanh sau deployment, nhóm có thể tạm ngừng rollout và ưu tiên reliability. Nếu chỉ đặt alert "có exception" thì mỗi validation exception bình thường cũng có thể đánh thức người trực.

## 42. Azure Monitor alerts theo yêu cầu

Các loại cảnh báo có thể gồm:

| Alert type | Theo dõi | Ví dụ |
|---|---|---|
| **Metric alert** | Metrics/time series đã có | HTTP 5xx rate, CPU/availability |
| **Log search alert** | KQL từ Log Analytics | Payment dependency failure rate 5 phút |
| **Activity Log alert** | Control-plane activity | Xóa App Insights resource hoặc thay cấu hình |
| **Smart detection/anomaly** khi hỗ trợ | Pattern bất thường | Tăng exceptions/latency |
| **Application-level alert** | Business custom metrics | Order pending quá lâu, outbox backlog |

Một alert hữu ích phải có **owner, severity, threshold, evaluation window, suppression/dedup policy và runbook**. Không gửi mọi AppExceptions record thành email, vì sẽ tạo alert storm.

### Ví dụ KQL để quan sát dependency lỗi

~~~kusto
AppDependencies
| where TimeGenerated >= ago(15m)
| where AppRoleName == "orders-api"
| where Target contains "payment-api"
| summarize
    Total = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false)
| extend FailureRatePct =
    iff(Total > 0, 100.0 * Failures / Total, 0.0)
~~~

**Lưu ý:** query phục vụ minh họa logic alert. Trong Azure Monitor **log search alert**, phải cấu hình **measure/aggregation/threshold, evaluation frequency và time window** đúng khả năng loại alert. Với no-data/low-traffic, tỷ lệ trên 0 calls không nên được hiểu là hệ thống khỏe: cần alert riêng cho **absence of expected traffic** khi phù hợp.

### Tránh tỷ lệ trên mẫu quá nhỏ

Một dependency có 1 request và 1 lỗi sẽ có failure rate 100%, nhưng chưa chắc cần page. Có thể đặt điều kiện **minimum volume** và phân cấp cảnh báo:

- Warning nếu rate tăng nhưng volume nhỏ.
- Critical nếu nhiều requests bị ảnh hưởng, burn rate cao và kéo dài.
- Informational nếu chỉ một external test request lỗi.

## 43. Action Groups và runbook escalation

**Azure Monitor Action Groups** có thể kết nối tới email, SMS, webhook, ITSM hoặc automation theo lựa chọn được hỗ trợ và chính sách tổ chức.

~~~text
Metric/log alert fired
       |
       v
Azure Monitor alert rule
       |
       v
Action Group
       |
       +-- Notify on-call engineer
       +-- Open incident ticket
       +-- Include dashboard/runbook link
       +-- Optional approved automation
~~~

### Nội dung alert nên có

~~~text
Alert: orders-api payment dependency failure rate high
Environment: production
Time window: last 15 minutes
Observed calls / failures: from validated query
Scope: orders-api + payment-api target
Dashboard: approved Application Insights workbook
Runbook: internal incident procedure
Owner: payments integration team
Sensitive payloads: excluded
~~~

**Không đưa full exception message, SQL statement có parameters, customer email, Authorization header hoặc payment reference** vào email/SMS/webhook gửi rộng. Alert nên dẫn đến nguồn telemetry được phân quyền.

### Automation có rủi ro

Một alert "payment errors tăng" không nên tự động xóa database, restart mọi pods hay chuyển region ngoài data residency policy. Nếu muốn remediation tự động, phải có approvals, rate limits, idempotency và rollback.

## 44. Phân biệt saturation, latency và dependency failures

Một request chậm có thể bắt nguồn ở nhiều nơi:

| Triệu chứng | Dependency view | Metrics bổ sung | Hướng điều tra |
|---|---|---|---|
| SQL spans chậm | JDBC high p95 | DB CPU/locks/queries | Query plan, index, contention |
| Request chậm nhưng JDBC ngắn | SQL spans ít | Hikari pending connections | Connection pool wait |
| HTTP 503/429 từ payment | HTTP CLIENT failures | Remote rate limit, retries | Backoff/bulkhead/circuit breaker |
| Nhiều spans ngắn nhưng request dài | Không rõ critical path | JVM GC/thread pool | CPU throttling, thread starvation |
| Service Bus SEND thành công, invoice trễ | Publish span success | Queue age, consumer lag | Worker scale/DB lock |
| Exceptions tăng sau release | Type/ProblemId mới | App version | Regression/canary rollback |

**Đừng sửa bằng cách tăng replicas khi nguyên nhân là DB connection limit**: nhiều replicas có thể mở thêm connections và khiến sự cố nặng hơn.

### Golden signals

Một bộ tín hiệu phổ biến gồm **latency, traffic, errors và saturation**. Bổ sung **business correctness** và **dependency health** để phân tích từ trải nghiệm người dùng đến hạ tầng.

## 45. Bảo vệ dữ liệu và quyền truy cập telemetry

Telemetry có thể chứa thông tin nhạy cảm hơn bạn tưởng:

- URL/query string chứa user ID/email.
- SQL text/log exception chứa dữ liệu đơn hàng.
- HTTP headers chứa JWT/API key/cookie.
- Service Bus message properties chứa tenant/user identifiers.
- Stack trace lộ file path, package names hoặc cấu trúc hạ tầng.
- Custom span attributes ghi payment reference.

### Các nguyên tắc

1. **Data minimization:** chỉ thu thuộc tính cần chẩn đoán.
2. **Redaction:** loại secrets, PII, data regulated trước khi exporter gửi đi.
3. **RBAC:** giới hạn người được xem Application Insights và Log Analytics workspace.
4. **Retention:** đặt thời hạn lưu và quyền xuất dữ liệu theo chính sách.
5. **Data residency:** kiểm tra workspace/ingestion region, geo/replication terms và quy định tổ chức.
6. **Access auditing:** theo dõi quyền đọc/xuất logs khi cần.
7. **Deletion workflows:** xử lý yêu cầu xóa dữ liệu và sự cố privacy theo quy trình.

**Không lấy correlation ID làm biện pháp che danh tính nếu vẫn có thể join trực tiếp với customer records**. Pseudonymization cần governance, và log access vẫn phải được phân quyền.

### Authentication của ingestion

Không nhầm Application Insights **connection string/instrumentation key** với end-user identity. Khi giải pháp/exporter hỗ trợ **Microsoft Entra-authenticated ingestion** và yêu cầu tổ chức, cấu hình theo hướng dẫn/roles cụ thể; không tự giả định mọi Java agent version tự động dùng managed identity chỉ vì bật trên App Service.

### Quyền quản trị khác quyền xem dữ liệu

Azure RBAC cấp quyền tài nguyên và Log Analytics data access có nhiều scope/mô hình. Một người có quyền deploy app không nên mặc định có quyền truy cập toàn bộ logs chứa dữ liệu khách hàng.

## 46. Chi phí Application Insights và Log Analytics

Telemetry có giá trị nhưng cũng tiêu thụ tài nguyên và chi phí:

| Yếu tố | Tác động |
|---|---|
| Ingestion volume (GB) | Nhiều logs/traces/dependencies làm tăng chi phí |
| Retention | Thời gian lưu dữ liệu và điều kiện charge |
| Sampling | Giảm traces, có thể ảnh hưởng phân tích |
| High-cardinality metrics | Nhiều series/dimensions, khó query |
| Query/workbook/alerts | Có thể tăng query compute và chi phí theo mô hình |
| Cross-region telemetry | Network/data residency và latency |
| Collector/agents | CPU/RAM và chi phí vận hành |

### Ví dụ tính volume lý thuyết

Giả sử:

~~~text
100 requests/giây
× 4 telemetry records/request trung bình
× 1 KiB/record trung bình
= 400 KiB/giây

Trong 1 giờ:
≈ 1,373 GiB dữ liệu thô theo giả định nhị phân
~~~

Đây là **ước lượng thô**, chưa tính nén, metadata, ingestion accounting, retries, dynamic properties, metrics hoặc free allowances/commitment tiers. Không dùng con số này làm giá trị hóa đơn thật; đối chiếu **Azure Monitor pricing + workspace usage** tại thời điểm triển khai.

### Các cách kiểm soát chi phí

- Định nghĩa telemetry levels: **metrics cốt lõi, traces sampled, debug logs tạm thời**.
- Loại bỏ health-check traffic nhiễu khỏi traces khi chính sách cho phép, nhưng giữ metrics uptime cần thiết.
- Filter các endpoints quá nhiều (ví dụ polling) có kiểm soát.
- Không log full request/response JSON thường xuyên.
- Có retention theo environment và data classification.
- Dùng sampling được đo lường; không đặt sample rate quá thấp làm mất lỗi hiếm quan trọng.
- Đặt budgets/alerts và theo dõi ingestion GB mỗi ngày.

**Giảm sampling không phải luôn tối ưu**: nếu không còn traces đủ để tìm lỗi production, nhóm sẽ tốn thêm thời gian điều tra; cần cân bằng cost với diagnostic value.

## 47. Đo overhead của Java instrumentation

Java agent có thể tăng **CPU, RAM, startup time, log volume, network egress**. Trước rollout rộng:

1. Benchmark baseline không agent với cùng workload.
2. Bật agent ở staging hoặc canary production được phép.
3. Đo **p50/p95 latency, throughput, JVM RSS, GC, startup time**.
4. Theo dõi exporter queue/dropped spans và ingestion failures.
5. Tăng traffic từ từ, so sánh với deployment không agent.
6. Kiểm tra instrumentation của HTTP client, JDBC, messaging và async framework.
7. Pin agent version và có rollback nếu incompatibility.

### Nếu agent gây lỗi

Không tắt toàn bộ monitoring âm thầm và coi xong việc. Ghi incident/change record, rollback agent version hoặc disable instrumentation module gây lỗi theo hướng dẫn được hỗ trợ, duy trì platform metrics/logs tối thiểu và mở test tương thích.

### Tín hiệu cần cảnh báo

Nếu app request latency không đổi nhưng **telemetry dropped spans** tăng mạnh, dữ liệu chẩn đoán đang thiếu. Một hệ thống "không có errors trong Application Insights" có thể chỉ là exporter không gửi được.

## 48. Runbook điều tra một incident trong 15 phút đầu

**Tình huống:** khách hàng báo chức năng thanh toán chậm và lỗi.

### 0–3 phút: xác nhận phạm vi

1. Xem **user-impact SLO**: request rate, 5xx, p95/p99, các vùng bị ảnh hưởng.
2. Xác định dịch vụ/phiên bản mới deploy, thời điểm bắt đầu.
3. Kiểm tra Azure platform health/DB/service metrics nếu phù hợp.
4. Phân biệt public endpoint outage và chỉ một dependency chậm.

### 3–8 phút: tìm critical path

1. Trong Application Insights, lọc **POST /orders** ở khoảng có lỗi.
2. Chọn vài traces representative, không chỉ một request.
3. Xem waterfall: SQL, payment HTTP, Redis, Service Bus.
4. Kiểm tra failed dependency/result codes và associated exceptions.
5. So sánh với request thành công cùng thời điểm.

### 8–12 phút: xác minh nguyên nhân

1. Đọc exception type/message đã được redaction.
2. So sánh dependency p95 và error rate theo target.
3. Kiểm tra retries/circuit breaker, DB pool/queue lag.
4. Nếu trace đứt ở service nào, xem instrumentation/context propagation.
5. Kiểm tra có phải rollout/revision/config change mới gây regression.

### 12–15 phút: giảm tác động

1. Kích hoạt phương án rollback/feature flag đã phê duyệt khi bằng chứng phù hợp.
2. Hạn chế retry storm, scale đúng bottleneck và giữ data-plane integrity.
3. Thông báo owner/team và cập nhật incident timeline.
4. Sau phục hồi, viết postmortem: root cause, detection gaps, prevention.

**Không sửa production chỉ dựa một exception log thiếu correlation.** Bằng chứng cần nối giữa end-user failures, dependency latency và thay đổi hệ thống.

## 49. Tình huống A: requests chậm nhưng SQL spans rất nhanh

**Bối cảnh:** Khách hàng thấy POST /orders mất 3 giây; Application Insights cho thấy truy vấn SQL chỉ 60 ms.

### Giả thuyết

- HikariCP pool đang hết connections; request chờ 2,5 giây trước khi thực thi SQL.
- Java threads bị block vì quá nhiều work/GC.
- Một filter/security/interceptor xử lý chậm trước khi tới repository.
- Trace instrumentation bỏ qua giai đoạn chờ connection pool.

### Cách kiểm tra

1. Chọn traces chậm, so sánh server span duration với tổng dependency duration.
2. Xem JVM thread count, GC pauses và CPU throttling.
3. Xem HikariCP **active, idle, pending, timeout** theo thời gian.
4. So sánh max pool size với max replicas × connections và DB capacity.
5. Đo custom span nhỏ cho đoạn acquire connection nếu thực sự cần.
6. Chạy load test có giới hạn và xem pool wait tăng khi concurrency tăng.

### Khắc phục

Tối ưu transaction duration, SQL queries, connection pool sizing và upstream concurrency. **Không tăng pool size của từng pod vô hạn**, vì có thể gây quá tải DB. Một hệ thống có DB metrics bình thường vẫn có thể có **pool starvation ở Java client**.

## 50. Tình huống B: payment lỗi nhiều nhưng API vẫn trả HTTP 200

**Bối cảnh:** Application Insights ghi nhiều HTTP CLIENT 503 tới payment-api nhưng request POST /checkout có Success=true. Đội trực chỉ nhìn request error rate nên không có alert.

### Diễn giải có thể

- Ứng dụng có retry thành công nên client không thấy lỗi.
- Ứng dụng trả trạng thái **pending** một cách có chủ đích.
- Ứng dụng **bắt exception rồi trả "success" sai**.
- Instrumentation HTTP dependency đánh dấu 503, nhưng business response được xây khác.

### Phân tích

1. Xem trace có bao nhiêu attempts và final dependency outcome.
2. Đọc application/business events, không chỉ HTTP status.
3. So sánh order/payment database state với response contract.
4. Kiểm tra circuit breaker/fallback semantics.
5. Nếu HTTP 200 sai nghiệp vụ, sửa API contract và test, không đổi telemetry để che lỗi.

### Cảnh báo tốt hơn

Đặt **dependency failure rate + retry count** ở mức warning, **payment final failure/business pending age** ở mức customer-impact alert và **request 5xx/SLO burn rate** ở cấp sản phẩm. Mỗi chỉ số trả lời một câu hỏi khác nhau.

## 51. Tình huống C: trace đứt ở Service Bus consumer

**Bối cảnh:** HTTP POST /orders có Service Bus SEND dependency, nhưng trong Application Insights **invoice-worker** không nằm trong cùng operation/trace.

### Lý do có thể

- Message không mang W3C trace context/diagnostic properties.
- Worker không extract context từ message.
- Consumer được xử lý trong một worker thread mất OTel context.
- Producer/consumer dùng instrumentation không tương thích hoặc version agent khác nhau.
- Queue được xử lý bất đồng bộ và tạo **new root trace + span link**, không phải child trực tiếp.
- Hai services gửi telemetry vào resources/workspaces khác mà người điều tra không có quyền xem cả hai.

### Runbook

1. Xác minh **Service Bus message đã được gửi và nhận** bằng broker metrics, không chỉ SEND span.
2. Kiểm tra metadata truyền trace context, không log payload/secrets.
3. Xác minh Java agent/OTel integration thực hỗ trợ Service Bus SDK đang dùng.
4. Xem **consumer spans** và span links/context extraction.
5. Đặt một opaque **business event ID** nhất quán ngoài trace ID để đối soát.
6. Kiểm tra AppRoleName, time range và workspace permissions.
7. Với batch fan-in, không ép tất cả messages thành một parent trace không chính xác; dùng links.

**Tracing là công cụ tương quan, không thay broker messageId, durable state hoặc exactly-once contract.** Một message đã xử lý hợp lệ có thể thuộc trace mới; cần ghi nhận đúng semantics.

## 52. Tình huống D: exception bị nuốt trong background job

**Bối cảnh:** Đơn hàng được tạo và HTTP API trả 202, nhưng một @Async task gửi invoice email bị lỗi. Application Insights vẫn có request success, không có exception ở request trace.

### Vì sao

~~~text
HTTP Controller
  |
  +-- Persist order
  +-- Submit @Async email job
  +-- Return 202

@Async job
  |
  +-- SMTP/third-party timeout
  +-- Catch(Exception) rồi log DEBUG hoặc bỏ qua
~~~

Vấn đề không chỉ là thiếu exception telemetry: **business job không có durable state/attempt status**. Nếu JVM restart, in-memory task có thể biến mất.

### Sửa

- Dùng **transactional outbox + durable message queue** khi email là nghiệp vụ quan trọng.
- Instrument consumer trace và custom metrics **invoice_email_attempt, success, failure** theo labels thấp cardinality.
- Log sanitized exception đúng một lần, có event ID và worker version.
- Retry có giới hạn với idempotency, chuyển DLQ/incident khi lỗi không thể khắc phục.
- Có dashboard **pending age, processing rate, DLQ count**, không dựa chỉ HTTP 202.

**Không bật logging DEBUG ghi toàn bộ email body chỉ để điều tra lỗi**, vì có thể làm lộ nội dung khách hàng.

## 53. Tình huống E: exceptions tăng sau canary release

**Bối cảnh:** Sau khi chuyển 10% traffic sang orders-api v2, AppExceptions ghi nhiều **NullPointerException**, latency p95 tăng nhưng CPU tổng không đổi.

### Các bước

1. Lấy mốc thay đổi deployment và phiên bản ứng dụng trong telemetry.
2. Phân nhóm exceptions theo Type/ProblemId/service.version nếu đã instrument.
3. So sánh **v1 và v2** với traffic proportions tương ứng; không so raw counts nếu volumes khác.
4. Mở vài traces của v2, kiểm tra request name/dependencies liên quan.
5. Kiểm tra input shape, DTO/schema changes, feature flags.
6. Khi regression đã có bằng chứng, rollback/disable feature theo runbook.
7. Bổ sung regression test và cảnh báo business/exception rate theo release.

### Cần tránh

- Không khẳng định v2 sai chỉ vì exception count cao hơn trong 5 phút ngẫu nhiên.
- Không chỉ nhìn stack trace của một request nếu lỗi xảy ra ở nhiều code paths.
- Không xóa exception logs hoặc đổi logging level để làm biểu đồ xanh.
- Không rollback code mà bỏ qua database/schema migration có thể không tương thích.

## 54. Bài thực hành: điều tra transaction Spring Boot qua Application Insights

### Bối cảnh

Bạn xây **Orders Lab**, một API Spring Boot đơn giản. Mục tiêu là phát hiện chính xác một dependency chậm và một exception, không chỉ có dashboard tổng quát.

Mô hình:

~~~text
Lab client
   |
   v
orders-api (Spring Boot)
   |
   +-- HTTP client -> payment-stub (Spring Boot/mock HTTP service)
   +-- JDBC -> test database hoặc H2 (tùy lab)
   +-- Custom span -> order.validate
   |
   v
Azure Monitor / Application Insights
   |
   +-- AppRequests
   +-- AppDependencies
   +-- AppExceptions
   +-- AppTraces
~~~

**Dữ liệu chỉ dùng test customer/order IDs giả**. Nếu không có subscription Azure hoặc quyền tạo resources, thực hành phần instrumentation và logging local, chuẩn bị các truy vấn/ADR, không tự tạo resource production hay điền số liệu giả thành "đã đo".

### Phần A — Chọn môi trường và tài nguyên

1. Sử dụng subscription/resource group **sandbox** được tổ chức cho phép.
2. Chọn App Service hoặc Container Apps chạy **orders-api**; nếu có AKS lab đang tồn tại, có thể dùng với quyền được cấp.
3. Tạo hoặc dùng **workspace-based Application Insights resource** được phép.
4. Ghi lại Log Analytics workspace gắn với resource và retention/budget.
5. Cấu hình role name/service name **orders-api**, environment=lab.
6. Chuẩn bị endpoint mock **payment-stub**, không gọi cổng thanh toán thật.

### Phần B — Chuẩn bị dependency instrumentation

1. Thêm Spring Web/Actuator nếu chưa có.
2. Chọn **Azure Monitor OpenTelemetry Java agent** hoặc OTel pipeline hiện hữu, không bật song song nhiều exporters trùng.
3. Bảo đảm ứng dụng có thể kết nối endpoint ingestion qua DNS/TLS.
4. Tạo một HTTP client gọi **payment-stub** được instrument.
5. Nếu dùng JDBC, đảm bảo test database có dữ liệu giả và truy vấn an toàn.
6. Thêm custom span **order.validate** với attributes cardinality thấp.
7. Thêm một log sanitized trong cùng trace.

### Phần C — Tạo các kịch bản request

| Case | Kịch bản | Kỳ vọng trong telemetry |
|---|---|---|
| **C1** | HTTP request thành công, mock payment 200 | Request + HTTP dependency success |
| **C2** | Payment mock sleep 2 giây | HTTP dependency duration tăng, request tăng |
| **C3** | Payment mock HTTP 503, backend trả 502 | Failed dependency + failed request |
| **C4** | Payment mock 503 rồi retry thành công | Failed attempts, final business success |
| **C5** | Ném exception tại domain validation | Exception event/stack theo instrumentation |
| **C6** | Bắt business validation và trả 422 | Expected client error, tránh alert như service outage |
| **C7** | Chuyển xử lý sang @Async | Verify parent/context hoặc diagnostic link |
| **C8** | Gửi job qua Service Bus test queue nếu có | Producer/consumer context và business event ID |

**Không cố tạo lượng lớn lỗi 503/429 trên services dùng chung**. Dùng mock/stub hoặc application flag chỉ bật trong lab.

### Phần D — Ví dụ payment stub an toàn

~~~java
package com.example.obslab;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Profile("observability-lab")
@RestController
public class PaymentStubController {

    @GetMapping("/lab/payment")
    public ResponseEntity<String> payment(
            @RequestParam(defaultValue = "ok") String mode)
            throws InterruptedException {
        if ("slow".equals(mode)) {
            Thread.sleep(2000);
        }
        if ("unavailable".equals(mode)) {
            return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("mock dependency unavailable");
        }
        return ResponseEntity.ok("mock payment accepted");
    }
}
~~~

**Chỉ bật profile observability-lab trong sandbox**, không tạo public endpoint cho bất kỳ ai có thể sleep thread trong production. Code không dùng payment credentials và không xử lý giao dịch tài chính.

### Phần E — Gửi requests giả

Trong Bash/Azure Cloud Shell được phép:

~~~bash
LAB_API="https://<LAB_ORDERS_API_HOST>"

curl --fail-with-body "$LAB_API/api/orders/lab?mode=ok"
curl --fail-with-body "$LAB_API/api/orders/lab?mode=slow"
curl -i "$LAB_API/api/orders/lab?mode=unavailable"
~~~

**/api/orders/lab** là endpoint **do học viên phải triển khai** trong orders-api, gọi payment-stub qua HTTP client và mapping status/exception. Nó **không tự tồn tại** chỉ vì có PaymentStubController ở mục trên. Trong lab hãy bảo vệ truy cập, tránh token trong command line logs và verify đúng host.

### Phần F — Kiểm tra trace/correlation

1. Trong Application Insights, tìm request C1 và xác định **OperationId**.
2. Xem **Application Map** có orders-api và payment-stub hay không.
3. Mở **End-to-end transaction** của C2: dependency duration có gần 2 giây không?
4. Với C3, xem HTTP dependency status, HTTP request status và exception (nếu code ném).
5. Với C4, đếm HTTP attempts; ghi rõ final user-visible result.
6. Với C5, kiểm tra exception type và span status.
7. Với C7, kiểm tra trace context qua executor.
8. Nếu có C8, so sánh Service Bus SEND, consumer PROCESS và business event ID.

**Không tự kết luận thiếu một span là lỗi code** nếu sampling đã loại span hoặc instrumentation chưa hỗ trợ HTTP client library. Kiểm tra sampling config và agent capability trước.

### Phần G — Chạy KQL

Dùng đúng workspace/resource, thay service name và time window:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| project TimeGenerated, Name, OperationId, DurationMs,
          ResultCode, Success
| top 30 by TimeGenerated desc
~~~

~~~kusto
AppDependencies
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| project TimeGenerated, OperationId, Type, Target, Name,
          DurationMs, ResultCode, Success
| top 30 by TimeGenerated desc
~~~

~~~kusto
AppExceptions
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| project TimeGenerated, OperationId, Type, ProblemId
| top 30 by TimeGenerated desc
~~~

Nếu kết quả không có dữ liệu, kiểm tra ingestion, resource role name, time range, KQL schema, filter và sampling.

### Phần H — Đánh giá monitoring design

Học viên phải trả lời:

- C2 chậm do HTTP dependency hay do app serialization/thread starvation?
- Với C3/C4, lỗi dependency và lỗi transaction khác nhau ra sao?
- Có request nào bị log exception nhưng vẫn trả success hợp lệ?
- Sampling có khiến KQL counts/percentiles không đầy đủ không?
- Trace context có đi xuyên qua Java executor hoặc Service Bus không?
- Các thuộc tính nào cần loại bỏ vì PII/high cardinality?
- Monitoring đã có alert theo **end-user impact** chưa?

### Phần I — Lập một alert và runbook

Thiết kế một **log/metric alert** trên dependency payment:

~~~text
Alert Name: payment-dependency-high-failure
Scope: orders-api production/lab tùy bài
Condition: dependency failure ratio cao
Min volume: phải đủ calls trước khi page
Evaluation: 5–15 phút theo SLO và traffic
Action Group: team được chỉ định
Runbook: kiểm tra AppDependencies -> trace -> remote service
Safety: không kèm secrets/customer payload
~~~

Các threshold ở đây là **khung thiết kế**, không phải quy tắc có thể tự deploy mà không đánh giá traffic/sampling. Trong lab chỉ dùng **action group thử nghiệm** và giới hạn notification.

### Phần J — Bằng chứng và cleanup

~~~text
Artifacts:
  Commit SHA / JDK / Spring Boot / agent version
  App Service/Container Apps/AKS environment and region
  Application Insights resource + workspace (không có secret)
  Service name / deployment version
  Test cases C1..C8: observed vs expected
  Three KQL result summaries
  One correlated trace ID (opaque)
  One dependency latency explanation
  One exception explanation
  Sampling and PII policy
  Alert/runbook description
  Cleanup/cost checks
~~~

Chỉ xóa resources lab do mình sở hữu, không xóa Application Insights workspace, alerts hoặc dashboards dùng chung. Ngắt mock fault-injection endpoints, xóa keys đã lộ nếu có và kiểm tra Cost Management vì telemetry ingestion có thể cập nhật chậm.

## 55. Bảng lựa chọn giải pháp cho từng nhu cầu

| Mục tiêu | Tín hiệu chính | Công cụ/cách triển khai | Vì sao |
|---|---|---|---|
| API 500 tăng | Request status/rate | Azure Monitor metric alert, AppRequests | Đo tác động khách hàng |
| API chậm | Request p95 + dependency spans | Application Insights Performance / KQL | Tìm critical path |
| Payment HTTP timeout | HTTP CLIENT duration/result | AppDependencies, trace waterfall | Phân biệt remote latency |
| DB query chậm | JDBC dependency + DB metrics | AppDependencies + Azure SQL/PostgreSQL Monitor | Kết hợp client/server view |
| HikariCP cạn | Pool pending/active/timeout | Micrometer metrics + correlated traces | SQL span có thể không bao gồm wait |
| Java exception mới | Exception Type/ProblemId | AppExceptions, stack đã redaction | Phát hiện regression |
| Service Bus queue trễ | Consumer lag/oldest age | Broker metrics + worker spans | SEND success chưa bằng process success |
| Transaction nghiệp vụ sai | Business event/counter + trace | Custom observation + database facts | HTTP 200 có thể sai kết quả |
| Trace đứt giữa services | traceparent/consumer spans | OTel propagation + App Map | Giải thích thiếu correlation |
| Chi phí telemetry tăng | Ingestion GB/sampling | Log Analytics usage + Cost Management | Tránh debug logs tràn |

**Quy tắc:** bắt đầu từ **câu hỏi vận hành** rồi chọn telemetry/công cụ tương ứng. Không tạo thêm hàng trăm custom spans trước khi biết ai sẽ đọc chúng và quyết định nào chúng hỗ trợ.

## 56. Checklist triển khai production

- [ ] Đã định nghĩa **service.name/AppRoleName, environment, version và resource scope** thống nhất.
- [ ] Application Insights là **workspace-based** hoặc schema đã được xác nhận; truy vấn đúng bảng.
- [ ] Instrumentation Java agent/SDK/OTel bridge được pin phiên bản và đã test.
- [ ] Không bật trùng exporters/Java agents gây duplicate telemetry.
- [ ] HTTP requests có status, duration, route template và trace context.
- [ ] HTTP client dependencies có target, result code, duration, timeout/retry info.
- [ ] JDBC/Redis/Storage/Service Bus SDK được hỗ trợ hoặc có custom spans cần thiết.
- [ ] Trace context được truyền qua HTTP, @Async, Reactor và messaging phù hợp.
- [ ] Có business transaction name/outcome không chứa PII.
- [ ] Có custom spans cho bước domain quan trọng, không spam spans cho từng dòng code.
- [ ] Exception handling phân biệt lỗi dự kiến với lỗi thật.
- [ ] Không log exception trùng ở mọi layer.
- [ ] Không lộ raw SQL parameters, customer body, Authorization header hay keys.
- [ ] Có correlation IDs trong structured logs, được propagate/clear đúng.
- [ ] Đã thiết kế sampling và hiểu ItemCount/percentile limitations.
- [ ] Có metrics đáng tin cho SLO, không chỉ đếm sampled traces.
- [ ] Có dashboards về request rate, p95/p99, 5xx, dependency errors và worker lag.
- [ ] Azure platform metrics và application traces được ghép theo thời gian/version.
- [ ] Có ít nhất một query tìm request chậm và một query tìm exceptions theo OperationId.
- [ ] Có alert thresholds, min volume, action group và runbook.
- [ ] Có kiểm soát no-data conditions cho workload lẽ ra phải có traffic.
- [ ] RBAC của Application Insights/Log Analytics tuân thủ least privilege.
- [ ] Data residency, retention và privacy review được hoàn thành.
- [ ] Ingestion volume, log retention, collector overhead và budgets được theo dõi.
- [ ] Đã benchmark startup/CPU/RAM/latency với agent.
- [ ] Có canary/rollback plan cho agent/config changes.
- [ ] Có test lỗi dependency, exception, async context và cross-service correlation.
- [ ] Không fault-inject production hoặc gửi dữ liệu khách hàng thật vào bài lab.
- [ ] Có ownership và quy trình cải thiện instrumentations sau postmortem.

## 57. Câu hỏi tự kiểm tra

1. Dependency, exception và transaction ứng dụng khác nhau như thế nào?
2. Database transaction có phải distributed trace không?
3. Vì sao HTTP 200 không chứng minh thanh toán đã thành công?
4. Trace khác log và metric ở điểm nào?
5. Trace ID và span ID khác nhau ra sao?
6. W3C traceparent gồm những thông tin chính nào?
7. Vì sao traceparent không thể dùng thay JWT?
8. Baggage có thể gây rủi ro dữ liệu nhạy cảm như thế nào?
9. Khi nào dùng span links thay quan hệ parent-child?
10. Cách nào để instrument Spring Boot tự động trên Azure?
11. Vì sao bật hai Java agents cùng instrument JDBC có thể gây vấn đề?
12. Application Insights và Log Analytics workspace có vai trò gì?
13. Azure resource metrics khác Java application telemetry như thế nào?
14. Một HTTP dependency nên ghi các attributes nào?
15. Tại sao không đặt user ID trong dependency name/metric label?
16. Vì sao SQL spans ngắn nhưng request vẫn mất nhiều giây?
17. HikariCP connection pool wait có cần metric riêng không?
18. Retry ba lần tạo ra bao nhiêu dependency attempts có thể quan sát?
19. Dependency failure cao nhưng request 200 có thể có lý do hợp lệ nào?
20. Khi exception đã được @RestControllerAdvice xử lý, có chắc agent tạo exception event không?
21. Exception validation 422 có phải 5xx application failure không?
22. Khi nào nên dùng span.recordException và setStatus(ERROR)?
23. Micrometer Observation có tự xuất dữ liệu sang Azure không?
24. Context propagation có thể mất ở @Async/CompletableFuture như thế nào?
25. Lỗi thường gặp khi tracing qua Service Bus là gì?
26. Vì sao SEND success không đồng nghĩa consumer transaction success?
27. AppRequests, AppDependencies, AppExceptions, AppTraces dùng làm gì?
28. Schema AppRequests khác bảng requests legacy ở điểm nào?
29. Dùng KQL thế nào để tìm 20 requests chậm nhất của orders-api?
30. Dùng OperationId thế nào để ghép dependency và exception?
31. Vì sao cộng durations của nhiều child spans có thể sai?
32. ItemCount trong Application Insights được dùng khi nào?
33. Sampled traces có thể gây sai số nào cho p95 và tỷ lệ lỗi?
34. Khi nào nên dùng metric/SLI thay cho sampled KQL request count?
35. Azure Monitor alert có cần min volume threshold không?
36. Action Group notification nên chứa những gì để tránh lộ PII?
37. Data-plane RBAC và Log Analytics read permissions liên quan thế nào?
38. Khi tăng log verbosity, điều gì xảy ra với chi phí ingestion?
39. Những bước nào giúp xác minh agent gây overhead?
40. Khi Java request chậm, vì sao nên điều tra DB pool trước khi scale pods?
41. Khi canary release tăng exceptions, cần so sánh theo version/traffic như thế nào?
42. Làm sao phân biệt shared dependency outage với programming error?
43. Tại sao một message redelivery vẫn xảy ra dù distributed trace hoàn chỉnh?
44. Một incident runbook tốt cần ghi những mốc và bằng chứng gì?
45. Bài lab chứng minh điều gì khi AppDependencies ghi đúng payment HTTP 503?

## 58. Tài liệu tham khảo

- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview) — metrics, logs, alerts và observability.
- [Application Insights overview](https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview) — application telemetry, performance và transaction analysis.
- [Azure Monitor OpenTelemetry for Java](https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-enable?tabs=java) — OpenTelemetry instrumentation và cấu hình theo ngôn ngữ.
- [Application Insights distributed tracing](https://learn.microsoft.com/azure/azure-monitor/app/distributed-tracing-telemetry-correlation) — correlation và distributed transactions.
- [Application Insights Application Map](https://learn.microsoft.com/azure/azure-monitor/app/app-map) — service/dependency graph.
- [Application Insights transaction diagnostics](https://learn.microsoft.com/azure/azure-monitor/app/transaction-diagnostics) — end-to-end transaction view.
- [Application Insights telemetry data model](https://learn.microsoft.com/azure/azure-monitor/app/data-model-complete) — requests, dependencies, traces, exceptions.
- [AppRequests table schema](https://learn.microsoft.com/azure/azure-monitor/reference/tables/apprequests) — workspace-based request data.
- [AppDependencies table schema](https://learn.microsoft.com/azure/azure-monitor/reference/tables/appdependencies) — outgoing dependencies.
- [AppExceptions table schema](https://learn.microsoft.com/azure/azure-monitor/reference/tables/appexceptions) — exceptions.
- [Azure Monitor KQL overview](https://learn.microsoft.com/azure/azure-monitor/logs/log-query-overview) — query language và Log Analytics.
- [Azure Monitor alerts overview](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview) — alert rules và action groups.
- [Azure Monitor cost/usage](https://learn.microsoft.com/azure/azure-monitor/cost-usage) — ingestion, retention và cost controls.
- [Azure Monitor data collection privacy](https://learn.microsoft.com/azure/azure-monitor/logs/data-security) — quyền truy cập và dữ liệu.
- [OpenTelemetry concepts](https://opentelemetry.io/docs/concepts/) — spans, traces, metrics và logs.
- [OpenTelemetry Java](https://opentelemetry.io/docs/languages/java/) — instrumentation API và Java agent.
- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/) — chuẩn tên attributes HTTP/DB/messaging.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — traceparent/tracestate.
- [Spring Boot Actuator and observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — Micrometer/Observation/Tracing.
- [Spring Boot metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — JVM/HTTP/database metrics.
- [Azure Service Bus documentation](https://learn.microsoft.com/azure/service-bus-messaging/) — retries, settlement và messaging.
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — reliability/operational excellence/performance/cost.

**Kết luận:** Theo dõi dependency, exception và transaction ứng dụng trên Azure cần nhiều hơn việc bật logging. Hãy instrument Spring Boot bằng **OpenTelemetry/Application Insights**, truyền **trace context** qua HTTP và messaging, phân biệt **request success với dependency failure và business outcome**, đồng thời dùng **KQL/transaction waterfall** để xác định critical path và lỗi có tác động thật. Kết hợp traces với **JVM, database và Azure platform metrics**, xây alert theo SLO và quản lý sampling, chi phí, retention, quyền truy cập. Một hệ thống thực sự quan sát được là hệ thống mà đội vận hành có thể trả lời **request nào bị ảnh hưởng, dependency nào gây chậm, exception nào xảy ra, giao dịch nghiệp vụ cuối cùng ở trạng thái nào và bằng chứng nào hỗ trợ quyết định khắc phục**.
