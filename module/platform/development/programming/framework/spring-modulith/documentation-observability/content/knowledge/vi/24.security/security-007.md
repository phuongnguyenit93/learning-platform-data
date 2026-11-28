# Quản lý credential exporter

## 1. Vì sao exporter cần credential?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, Micrometer Tracing có thể ghi nhận các lời gọi qua application module như **orders**, **inventory**, **payments** và **notifications**. Các span được gom thành trace rồi gửi tới OpenTelemetry Collector hoặc tracing backend bằng một **exporter**. Nếu endpoint nhận telemetry nằm ngoài process hoặc ngoài mạng tin cậy, hệ thống cần xác thực client và bảo vệ dữ liệu trên đường truyền.

**Credential của exporter** là thông tin mà ứng dụng hoặc collector dùng để chứng minh danh tính khi gửi telemetry tới một endpoint. Credential có thể là bearer token/API key trong header, thông tin xác thực do OAuth2 cấp hoặc chứng thư client dùng cho mutual TLS (mTLS).

Một lỗi phổ biến là ghi token trực tiếp vào application.yml, commit file cấu hình lên Git hoặc bật HTTP wire log làm lộ Authorization header. Một lỗi khác là dùng chung credential giữa nhiều service, khiến việc thu hồi hoặc điều tra truy cập trở nên khó khăn.

Bài **“Quản lý credential exporter”** thuộc chương **Bảo mật** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Bài học tập trung vào credential của OTLP trace exporter, cách lưu trữ và cấp phát bí mật, TLS/mTLS, luân chuyển token và kiểm tra cấu hình an toàn.

Sau bài học, bạn có thể:

- Phân biệt endpoint, credential, TLS certificate và trace context.
- Xác định credential được dùng ở từng chặng ứng dụng → collector → backend.
- Cấu hình bearer token/API key qua Spring Boot properties mà không ghi bí mật vào source.
- Phân biệt property OTLP tracing giữa Spring Boot 3.5 và Spring Boot 4.x.
- Dùng Kubernetes Secret hoặc secret manager để cấp credential lúc runtime.
- Cấu hình trust certificate và client certificate cho TLS/mTLS.
- Hiểu khi nào nên dùng OAuth2/workload identity thay token tĩnh.
- Luân chuyển, thu hồi và kiểm thử credential mà không làm lộ giá trị bí mật.
- Chẩn đoán lỗi 401/403, TLS handshake và exporter authentication.

## 2. Phân biệt các thông tin bảo mật trong đường truyền telemetry

Một pipeline tracing thường có hai chặng riêng:

~~~mermaid
flowchart LR
    A["Spring Boot application"] -->|"OTLP + TLS + app credential"| B["OpenTelemetry Collector"]
    B -->|"OTLP + TLS + collector credential"| C["Trace backend"]
    A -.->|"Trace context propagation"| D["Service / module khác"]
~~~

- **Application → Collector:** credential của ứng dụng được Collector kiểm tra khi nhận OTLP.
- **Collector → Backend:** Collector có thể dùng credential khác để gửi dữ liệu tới backend.
- **Service → Service:** trace context được truyền để nối các span. Trace ID không phải credential và không dùng để xác thực.
- **TLS:** mã hóa đường truyền và xác minh danh tính máy chủ bằng certificate.
- **mTLS:** hai phía xác minh certificate của nhau; client certificate có thể là danh tính của workload.

| Thành phần | Chức năng | Có phải bí mật? |
| --- | --- | --- |
| OTLP endpoint | Địa chỉ nhận traces, ví dụ HTTPS host và port | Thường không, nhưng vẫn là thông tin cấu hình nội bộ |
| API key/bearer token | Xác thực ứng dụng hoặc collector | Có |
| OAuth2 client secret | Cho phép workload lấy access token | Có |
| Access token | Chứng minh quyền gửi telemetry trong thời hạn nhất định | Có |
| CA certificate | Xác minh certificate của peer | Thông thường không phải bí mật |
| Client certificate | Danh tính public của client trong mTLS | Không phải khóa bí mật, nhưng cần bảo vệ tính toàn vẹn |
| Client private key | Chứng minh quyền sở hữu client certificate | Có |
| traceId/spanId | Liên kết log và spans | Không phải credential; vẫn cần quản lý như dữ liệu vận hành |

Không nhúng token, private key hoặc mật khẩu vào trace attributes, baggage, resource attributes, metric labels hay log message. Các trường này phục vụ quan sát và có thể được export tới nhiều hệ thống khác.

## 3. Chọn cơ chế xác thực phù hợp

### 3.1. Bearer token hoặc API key

Đây là cách đơn giản khi Collector hoặc tracing backend yêu cầu một header xác thực. Ví dụ:

~~~http
Authorization: Bearer <TOKEN>
~~~

Hoặc backend có thể yêu cầu header riêng như X-API-Key. Tên header và định dạng phải khớp hợp đồng của endpoint nhận dữ liệu.

Ưu điểm:
- Dễ cấu hình với HTTP OTLP exporter.
- Dễ cấp credential riêng cho từng service/environment.
- Có thể thu hồi và thay token mà không cần phát hành lại ứng dụng nếu secret được cấp qua runtime configuration.

Hạn chế:
- Token tĩnh có thể tồn tại lâu và bị sao chép.
- Token hết hạn cần được cấp mới.
- Nếu log HTTP headers hoặc dump cấu hình, token có thể bị lộ.

Chỉ gửi bearer token qua HTTPS hoặc một kênh TLS được xác minh. Không gửi token qua HTTP plaintext, kể cả trong mạng riêng, trừ môi trường local test hoàn toàn cô lập và không có dữ liệu thật.

### 3.2. OAuth2 access token và workload identity

Với hệ thống hỗ trợ OAuth2/OIDC, workload có thể dùng client credentials hoặc danh tính workload để lấy access token ngắn hạn. Collector có thể dùng authenticator extension để lấy token khi export; receiver cũng có thể xác thực token được client gửi tới.

Ưu điểm:
- Token có thời hạn và scope/audience giới hạn.
- Có thể thu hồi hoặc thay đổi quyền tại identity provider.
- Tránh phải phân phối một API key dài hạn tới mọi instance.

Hạn chế:
- Cần identity provider, token endpoint và cấu hình refresh.
- Phải xử lý token expiry, clock skew, audience và quyền scope.
- Không phải mọi exporter đều tự động hỗ trợ lấy và refresh OAuth2 token.

Nếu Spring Boot exporter chỉ được cấu hình bằng một header Authorization tĩnh, việc thay token trong secret store không tự biến nó thành OAuth2 client. Khi cần token động, hãy dùng cơ chế được exporter/SDK hỗ trợ hoặc chuyển trách nhiệm xác thực outbound sang Collector có OAuth2 client authenticator.

### 3.3. TLS và mTLS

TLS bảo vệ tính bí mật và toàn vẹn của dữ liệu khi truyền, đồng thời xác minh certificate của máy chủ. mTLS bổ sung xác minh certificate client để Collector/backend biết workload nào đang kết nối.

- **Server TLS:** ứng dụng xác minh certificate của Collector.
- **Client certificate:** ứng dụng trình certificate của mình khi kết nối.
- **mTLS:** Collector xác minh client certificate bằng CA được tin cậy; ứng dụng cũng xác minh certificate của Collector.

TLS không thay thế authorization. Một client có certificate hợp lệ vẫn có thể cần policy xác định nó được gửi traces tới tenant/project nào.

## 4. Cấu hình bearer token với Spring Boot 3.5

Với Spring Boot 3.5, OTLP tracing dùng nhóm property có prefix **management.otlp.tracing**. Các property quan trọng gồm endpoint, headers và transport.

Dependency minh họa với OpenTelemetry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Cấu hình application.yml chỉ tham chiếu biến môi trường:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: "https://otel-collector.example.net:4318/v1/traces"
      transport: http
      headers:
        Authorization: "Bearer ${OTEL_EXPORTER_TOKEN}"
~~~

Trong ví dụ:
- Endpoint là OTLP/HTTP trace endpoint; thay bằng địa chỉ thực của môi trường.
- Header Authorization nhận token từ biến môi trường lúc ứng dụng khởi động.
- Giá trị token không xuất hiện trong file cấu hình được commit.
- Nếu endpoint yêu cầu header khác, dùng đúng tên và định dạng do nhà cung cấp quy định.

Spring Boot 3.5 tài liệu hóa **management.otlp.tracing.headers.\*** cho custom HTTP headers. Nếu dùng OTLP/gRPC hoặc cần metadata/authenticator động, kiểm tra khả năng của exporter bridge và cân nhắc OtlpGrpcSpanExporterBuilderCustomizer thay vì giả định HTTP header configuration áp dụng giống nhau cho mọi transport.

## 5. Cấu hình bearer token với Spring Boot 4.x

Ở Spring Boot 4.x, cấu hình OpenTelemetry tracing OTLP dùng prefix **management.opentelemetry.tracing.export.otlp**.

Dependency minh họa cho Spring Boot 4.2 với OpenTelemetry + OTLP:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Ví dụ Spring Boot 4.2:

~~~yaml
management:
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: "https://otel-collector.example.net:4318/v1/traces"
          transport: http
          headers:
            Authorization: "Bearer ${OTEL_EXPORTER_TOKEN}"
~~~

Nếu muốn dùng chung endpoint/header cho traces, logs và metrics, Spring Boot 4.x còn có nhóm **management.opentelemetry.otlp**. Tuy nhiên, credential của từng signal có thể khác nhau; cấu hình signal-specific thường dễ áp dụng least privilege hơn.

Ví dụ dùng credential chỉ cho traces:

~~~yaml
management:
  opentelemetry:
    tracing:
      export:
        otlp:
          headers:
            Authorization: "Bearer ${OTEL_EXPORTER_TOKEN}"
~~~

Không copy nguyên prefix của Boot 3.5 sang Boot 4.x. Khi nâng cấp, hãy kiểm tra configuration metadata và application properties của đúng minor version.

### 5.1. So sánh nhanh property theo phiên bản

| Mục đích | Spring Boot 3.5 | Spring Boot 4.x |
| --- | --- | --- |
| Endpoint traces | management.otlp.tracing.endpoint | management.opentelemetry.tracing.export.otlp.endpoint |
| Auth headers | management.otlp.tracing.headers.* | management.opentelemetry.tracing.export.otlp.headers.* |
| Transport | management.otlp.tracing.transport | management.opentelemetry.tracing.export.otlp.transport |
| SSL bundle | Xác minh khả năng của exporter/version; có thể cần customizer hoặc JVM trust material | management.opentelemetry.tracing.export.otlp.ssl.bundle |
| Common OTLP headers | Không dùng cùng prefix Boot 4.x | management.opentelemetry.otlp.headers.* |

Các property trên thuộc auto-configuration OpenTelemetry/OTLP. Nếu dùng Brave + Zipkin, Wavefront, Zipkin exporter khác hoặc OpenTelemetry Java Agent, cấu hình credential sẽ khác. Hãy đọc tài liệu của đúng exporter đang chạy.

## 6. Cấp token qua biến môi trường

Spring Boot hỗ trợ placeholder trong configuration. Ứng dụng đọc token từ environment variable mà secret manager hoặc nền tảng triển khai cấp lúc runtime.

Ví dụ cấu hình:

~~~yaml
management:
  opentelemetry:
    tracing:
      export:
        otlp:
          headers:
            Authorization: "Bearer ${OTEL_EXPORTER_TOKEN}"
~~~

Không đặt giá trị thật trong application.yml, Dockerfile, file .env được commit hoặc script khởi động có lưu lịch sử. Thay vào đó:
1. Lưu token trong secret manager được tổ chức phê duyệt.
2. Cấp quyền đọc secret cho workload cụ thể.
3. Inject secret vào process environment hoặc mount dưới dạng file.
4. Hạn chế quyền đọc environment/configuration của process.
5. Kiểm tra log và diagnostics không in giá trị secret.

Nếu placeholder bắt buộc nhưng biến môi trường không được cấp, ứng dụng có thể thất bại khi bind configuration hoặc khởi động. Đây là hành vi có ích để phát hiện thiếu credential sớm; không thêm token giả hoặc chuỗi rỗng làm fallback trong production.

### 6.1. Kubernetes Secret

Deployment có thể lấy token từ Secret đã được tạo qua secret manager, External Secrets hoặc quy trình quản trị bí mật:

~~~yaml
env:
  - name: OTEL_EXPORTER_TOKEN
    valueFrom:
      secretKeyRef:
        name: otlp-exporter-credentials
        key: token
~~~

Đoạn trên chỉ là phần cấu hình Pod tham chiếu tới Secret. Không commit token thật hoặc manifest Secret chứa dữ liệu nhạy cảm vào repository. Bảo vệ Kubernetes Secret bằng encryption at rest, RBAC, namespace isolation và quyền đọc tối thiểu. Chỉ service cần export traces mới nên được cấp secret này.

Nếu dùng file-mounted secret, đặt quyền file chỉ cho user chạy ứng dụng đọc được và tham chiếu bằng cơ chế config import/placeholder phù hợp. Không đưa private key vào image layer hoặc thư mục build artifact.

## 7. Dùng SSL bundle cho TLS và mTLS trong Spring Boot 4.x

Spring Boot 4.x cho phép exporter OTLP tracing tham chiếu một SSL bundle. Bundle chứa trust material để xác minh Collector và, khi dùng mTLS, client certificate/private key.

Ví dụ PEM bundle:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        otlp-client:
          truststore:
            certificate: "file:/run/secrets/otel-ca.pem"
          keystore:
            certificate: "file:/run/secrets/client-cert.pem"
            private-key: "file:/run/secrets/client-key.pem"

management:
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: "https://otel-collector.example.net:4318/v1/traces"
          ssl:
            bundle: otlp-client
~~~

Giải thích:
- otel-ca.pem là CA certificate dùng để xác minh certificate phía Collector.
- client-cert.pem là certificate client.
- client-key.pem là private key tương ứng; phải được mount từ secret store với quyền đọc hạn chế.
- ssl.bundle tham chiếu bundle tên otlp-client.
- Endpoint dùng HTTPS để bảo vệ dữ liệu telemetry.

Nếu chỉ cần server-authenticated TLS, có thể chỉ cấu hình truststore certificate. Nếu Collector yêu cầu mTLS, cung cấp cả keystore certificate và private key. Phía Collector cũng phải bật client certificate verification.

### 7.1. Cấu hình receiver phía Collector cho mTLS

Ví dụ cấu hình OTLP/HTTP receiver:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        tls:
          cert_file: /run/secrets/collector-server-cert.pem
          key_file: /run/secrets/collector-server-key.pem
          client_ca_file: /run/secrets/client-ca.pem

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]

processors:
  batch:

exporters:
  debug:
    verbosity: basic
~~~

Collector dùng server certificate/private key để cung cấp TLS và client_ca_file để xác minh certificate của ứng dụng. Các file certificate/key phải được provision an toàn; không đặt private key trực tiếp vào config repository.

Trong ví dụ này, debug exporter chỉ giúp minh họa một pipeline hoàn chỉnh. Trong production, thay nó bằng exporter đã cấu hình endpoint và credential riêng để gửi dữ liệu tới backend.

Nếu Collector chạy trong cùng cluster, giới hạn endpoint bằng network policy/firewall và chỉ cho phép workload được phép kết nối. TLS/mTLS không thay thế kiểm soát mạng hoặc authorization theo tenant.

## 8. Xác thực ở Collector và backend là hai việc riêng

Trong kiến trúc có Collector trung gian, ứng dụng không nhất thiết phải giữ credential truy cập trực tiếp backend. Có thể dùng:
- Credential A: ứng dụng → Collector.
- Credential B: Collector → backend.

Credential A chỉ cấp quyền gửi telemetry vào Collector. Credential B chỉ cấp quyền Collector export dữ liệu tới backend. Không dùng chung token nếu hai chặng có phạm vi quyền và vòng đời khác nhau.

### 8.1. Collector xác thực request gửi tới receiver

OpenTelemetry Collector dùng authenticator extension để xác thực các request HTTP/gRPC đi vào receiver. Ví dụ OIDC authenticator (cần bản phân phối Collector có extension tương ứng):

~~~yaml
extensions:
  oidc:
    issuer_url: "https://identity.example.net/realms/observability"
    audience: "otel-collector"

receivers:
  otlp/auth:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        auth:
          authenticator: oidc

service:
  extensions: [oidc]
  pipelines:
    traces:
      receivers: [otlp/auth]
      processors: [batch]
      exporters: [debug]

processors:
  batch:

exporters:
  debug:
    verbosity: basic
~~~

Client gửi tới receiver phải có token được identity provider cấp với issuer/audience phù hợp. OIDC extension không tự chấp nhận bất kỳ chuỗi API key nào; nếu dùng API key, chọn authenticator extension hỗ trợ đúng cơ chế đó và kiểm tra extension có trong Collector distribution.
Trong ví dụ, debug exporter giúp kiểm tra receiver và pipeline; production cần thay bằng exporter backend với credential outbound riêng.

### 8.2. Collector dùng credential riêng khi export tới backend

Collector cũng hỗ trợ client authenticator extension cho exporter. Ví dụ OAuth2 client lấy token để gửi tới remote Collector/backend:

~~~yaml
extensions:
  oauth2client:
    client_id: "${env:OTLP_CLIENT_ID}"
    client_secret: "${env:OTLP_CLIENT_SECRET}"
    token_url: "https://identity.example.net/oauth/token"

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:

exporters:
  otlp_grpc/backend:
    endpoint: "trace-backend.example.net:4317"
    auth:
      authenticator: oauth2client

service:
  extensions: [oauth2client]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp_grpc/backend]
~~~

Ví dụ cần Collector distribution có oauth2client extension. Client ID/secret phải được cấp qua secret manager hoặc environment injection. Không đưa các giá trị đó vào file YAML được commit.

## 9. Quy tắc least privilege cho credential exporter

Credential exporter nên có quyền nhỏ nhất đủ để gửi telemetry cần thiết:

- Cấp credential riêng theo ứng dụng hoặc workload, không dùng một token chung cho toàn bộ cluster.
- Tách dev, staging và production.
- Nếu chỉ export traces, dùng signal-specific header/credential thay vì common credential cho traces, metrics và logs.
- Giới hạn tenant, project, dataset hoặc endpoint mà token được phép ghi.
- Không cấp quyền đọc trace hoặc quản trị backend nếu exporter chỉ cần quyền ingest.
- Đặt thời hạn, rotation schedule và người/nhóm chịu trách nhiệm.
- Thu hồi credential cũ sau khi xác nhận instance mới đã export thành công.
- Audit việc tạo, đọc, thay đổi và thu hồi secret.
- Dùng workload identity/OIDC hoặc mTLS nếu nền tảng hỗ trợ và vận hành được.

Không sử dụng trace ID, span ID, service name hoặc module name làm bí mật. Các giá trị này là metadata quan sát, không chứng minh danh tính workload.

## 10. Luân chuyển và thu hồi credential

Credential cần có vòng đời rõ ràng. Một quy trình rotation an toàn có thể gồm:

1. **Tạo credential mới:** cấp token/certificate mới với cùng quyền tối thiểu cần thiết.
2. **Phân phối:** cập nhật secret manager hoặc secret reference cho workload được phép.
3. **Rollout:** restart/reload instance theo cơ chế cấu hình hỗ trợ để exporter sử dụng credential mới.
4. **Xác minh:** kiểm tra exporter không còn nhận 401/403 và trace mới xuất hiện trong backend.
5. **Thu hồi:** vô hiệu hóa credential cũ sau khi tất cả instance đã chuyển.
6. **Audit:** lưu lại thời điểm, owner, phạm vi và kết quả rotation.

Biến môi trường thường được đọc lúc process khởi động. Cập nhật Secret hoặc environment source không bảo đảm giá trị trong process đang chạy tự đổi. Hãy kiểm tra cơ chế reload của nền tảng và exporter; nếu không có dynamic refresh, cần rollout có kiểm soát.

Với token OAuth2 ngắn hạn, dùng authenticator có khả năng tự lấy và refresh token thay vì tự đặt một access token hết hạn vào header tĩnh. Với certificate, lập lịch thay trước ngày hết hạn và kiểm tra cả trust chain lẫn private key mới.

Khi nghi ngờ token bị lộ:
- Thu hồi token ngay theo quy trình incident.
- Cấp credential mới và rollout.
- Kiểm tra log truy cập Collector/backend trong khoảng thời gian liên quan.
- Xem xét quyền ingest, tenant và nguồn IP/workload.
- Xóa secret khỏi nơi lưu trữ không được phép và xử lý lịch sử Git/artifact theo quy trình incident response.
- Không chỉ xóa token khỏi file mới rồi coi như lịch sử đã an toàn.

## 11. Không để credential xuất hiện trong telemetry hoặc log

Credential exporter có thể bị lộ qua nhiều đường ngoài source code:

- HTTP client wire logging ghi Authorization header.
- Debug log in toàn bộ exporter configuration.
- Actuator env/configprops endpoint bị expose quá rộng.
- Exception message chứa URL có user/password hoặc token.
- CI log in biến môi trường.
- Crash dump, heap dump hoặc diagnostic bundle.
- Container environment inspection và process metadata.
- Trace attributes, baggage hoặc resource attributes được thêm thủ công.

Các nguyên tắc:

- Không log toàn bộ request headers hoặc exporter configuration trong production.
- Không ghi token/private key vào exception, span attribute hoặc baggage.
- Redact Authorization, Cookie, API key và query parameter nhạy cảm ở proxy/log pipeline.
- Giới hạn quyền đọc heap dump và diagnostic files.
- Không expose Actuator env/configprops cho người dùng không có quyền quản trị.
- Kiểm tra pipeline CI/CD không echo secret ra console.
- Khi cần debug, log endpoint host, protocol, status code và correlation ID; không log giá trị credential.

## 12. Kiểm thử cấu hình exporter an toàn

Một bài kiểm thử integration nên xác nhận:
1. Exporter gửi request tới đúng endpoint.
2. Request có header xác thực được cấu hình.
3. TLS certificate được xác minh.
4. Token sai hoặc hết hạn bị từ chối như dự kiến.
5. Credential mới hoạt động sau rotation.
6. Log output không chứa token hoặc private key.
7. Khi Collector/backend unavailable, exporter báo lỗi phù hợp và không làm lộ credential trong exception.
8. Credential của traces không vô tình được gửi tới signal/endpoint khác.

Trong test, dùng token giả được sinh riêng cho test và mock Collector/HTTP server. Có thể assert header tồn tại hoặc bằng giá trị fixture giả, nhưng không đọc hoặc in secret production trong test report. Không commit fixture token có quyền truy cập thật.

### 12.1. Kiểm tra bằng dấu hiệu vận hành

| Dấu hiệu | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| HTTP 401 Unauthorized | Thiếu token, token sai/hết hạn hoặc scheme không đúng | Kiểm tra secret reference, header name và Bearer prefix |
| HTTP 403 Forbidden | Token hợp lệ nhưng thiếu quyền ingest/tenant | Kiểm tra scope, audience, project và authorization policy |
| HTTP 404 Not Found | Sai endpoint hoặc path OTLP | Kiểm tra endpoint signal-specific và /v1/traces |
| TLS handshake failure | CA không tin cậy, certificate hết hạn hoặc hostname không khớp | Kiểm tra trust bundle, certificate chain và DNS name |
| mTLS client certificate rejected | Thiếu client cert, key không khớp hoặc CA chưa được trust | Kiểm tra keystore bundle và client_ca_file |
| Exporter timeout | Network, proxy, Collector hoặc backend chậm | Kiểm tra egress, DNS, collector health và timeout |
| Trace không xuất hiện dù HTTP 2xx | Sampling, pipeline, processor hoặc backend ingest | Kiểm tra sampling, Collector pipeline và trace backend |
| Log có Authorization header | Wire logging hoặc proxy logging quá chi tiết | Tắt header logging và bật redaction |

Không đưa giá trị token vào thông báo lỗi hoặc ticket. Khi cần chia sẻ log chẩn đoán, chỉ giữ status code, endpoint đã được làm sạch, service name và trace ID nếu phù hợp.

## 13. Checklist bảo mật exporter trước production

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Endpoint | Dùng HTTPS hoặc mTLS với hostname được xác minh |
| Credential | Token/API key được lấy từ secret manager hoặc secret runtime |
| Scope | Chỉ có quyền ingest traces cần thiết |
| Isolation | Credential riêng theo service và environment |
| Configuration | Không có token/private key trong source, image hoặc config commit |
| Spring Boot version | Prefix property đúng với Boot 3.5 hoặc Boot 4.x đang dùng |
| Headers | Dùng signal-specific credential nếu các signal có quyền khác nhau |
| TLS | Trust CA được cấu hình; không bỏ qua certificate verification |
| mTLS | Client cert/private key được mount an toàn và có lịch rotation |
| Collector | Receiver auth và exporter auth được cấu hình riêng theo từng chặng |
| Rotation | Có quy trình cấp mới, rollout, xác minh và thu hồi |
| Logging | Authorization header và exporter secrets được redacted |
| Actuator | Endpoint nhạy cảm chỉ mở cho người/quyền quản trị |
| CI/CD | Không echo secret; scan secret trong repository và artifact |
| Test | Có kiểm thử token sai/hết hạn, TLS và log redaction |
| Audit | Có owner, expiry, quyền truy cập và lịch sử rotation |

## 14. Ghi nhớ

**Credential exporter xác thực quyền gửi telemetry; TLS/mTLS bảo vệ và xác minh kết nối.** Hai cơ chế này bổ sung cho nhau. Trace ID, span ID và module identifier giúp liên kết dữ liệu quan sát nhưng không phải credential.

Với Spring Boot 3.5, OTLP tracing dùng nhóm management.otlp.tracing.*; Spring Boot 4.x dùng nhóm management.opentelemetry.tracing.export.otlp.* và hỗ trợ tham chiếu SSL bundle cho exporter. Hãy lấy token từ secret manager hoặc runtime secret, giới hạn quyền theo service/signal và không ghi bí mật vào source, logs hay telemetry.

Trong kiến trúc có OpenTelemetry Collector, quản lý credential riêng cho chặng ứng dụng → Collector và Collector → backend. Dùng OAuth2/workload identity hoặc mTLS khi phù hợp, luân chuyển trước khi hết hạn và xác minh bằng status/export metrics sau rollout. Quản lý credential có quy trình giúp bảo vệ trace data và giảm rủi ro lộ thông tin truy cập trong vận hành.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): dependency OTLP, cấu hình management.otlp.tracing.* và exporter customizers.
- [Spring Boot 4.2 — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): cấu hình OTLP chung và signal-specific, headers, environment-variable mapping.
- [Spring Boot 4.2 — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): management.opentelemetry.tracing.export.otlp.headers.* và ssl.bundle.
- [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): cấu hình trust material, PEM/JKS và SSL bundle.
- [OpenTelemetry — OTLP Exporter Specification](https://opentelemetry.io/docs/specs/otel/protocol/exporter/): endpoint, headers, protocol và certificate environment variables.
- [OpenTelemetry Collector — Authentication and Certificates](https://opentelemetry.io/docs/collector/configuration/): authenticator extensions, receiver/exporter authentication, TLS và mTLS.
- [OpenTelemetry Collector — Configuration Best Practices](https://opentelemetry.io/docs/security/config-best-practices/): lưu secrets, encryption, authentication, permissions và network exposure.
- [OpenTelemetry — Security](https://opentelemetry.io/docs/security/): các nguyên tắc bảo vệ pipeline và dữ liệu telemetry.

> **Giới hạn phiên bản:** Ví dụ property Boot 3.5 và 4.x có prefix khác nhau; không dùng lẫn. Cấu hình ssl.bundle minh họa cho Boot 4.x hiện hành. OTLP/gRPC, exporter tùy chỉnh, Collector authenticator extensions và cơ chế refresh token phụ thuộc implementation/distribution; xác minh đúng dependency và version trước khi triển khai.
