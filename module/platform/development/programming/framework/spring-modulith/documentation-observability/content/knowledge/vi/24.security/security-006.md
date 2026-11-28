# Bảo vệ kết nối tới telemetry backend

## 1. Vì sao kết nối telemetry cũng cần được bảo vệ?

Ứng dụng Spring Boot dùng **Spring Modulith** thường gửi metrics, traces và logs tới OpenTelemetry Collector hoặc telemetry backend. Những dữ liệu này giúp quan sát module graph khi vận hành, theo dõi event publication, đo thời gian xử lý và điều tra lỗi giữa các module. Tuy nhiên, telemetry cũng có thể chứa tên module, tên event, route, exception, thông tin hạ tầng, trace attributes và dữ liệu nghiệp vụ.

Nếu ứng dụng gửi telemetry qua kết nối không mã hóa, người có khả năng quan sát mạng có thể đọc dữ liệu hoặc sửa request. Nếu backend không xác thực client, workload không được phép có thể đẩy dữ liệu giả hoặc làm cạn tài nguyên ingest. Nếu client không xác thực danh tính server, ứng dụng có thể gửi telemetry tới một endpoint giả mạo.

Bài thuộc chương **Bảo mật** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module học này dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot thông qua module graph, Actuator, event metrics, tracing và context propagation. Chủ đề trực tiếp là **bảo vệ kết nối tới telemetry backend**: xác thực server bằng TLS, xác thực client bằng mTLS hoặc token, cấu hình OTLP exporter, quản lý secret, giới hạn egress, bảo vệ Collector và kiểm tra đường truyền trước production.

Sau bài học, bạn có thể:

1. Phân biệt TLS, mTLS và xác thực bằng bearer token.
2. Cấu hình OTLP endpoint dùng HTTPS và trust CA phù hợp.
3. Dùng SSL bundle của Spring Boot 4.x cho trace, log và metrics exporter.
4. Hiểu khác biệt cấu hình OTLP giữa Spring Boot 3.5 và 4.x.
5. Bảo vệ OTLP receiver trên OpenTelemetry Collector.
6. Quản lý token, client certificate và CA theo quy trình rotation.
7. Kiểm thử TLS handshake, xác thực client, quyền gửi dữ liệu và kết quả ingest.

## 2. Mô hình kết nối và ranh giới tin cậy

Một pipeline thường có ba chặng:

1. **Ứng dụng → Collector gần ứng dụng:** ứng dụng gửi OTLP traces, metrics hoặc logs.
2. **Collector → Collector gateway/backend:** Collector gom batch, lọc hoặc bổ sung attributes rồi chuyển tiếp.
3. **Collector/backend → kho lưu trữ và giao diện quan sát:** dữ liệu được lưu và truy vấn bởi người vận hành.

~~~mermaid
flowchart LR
    App["Spring Boot + Spring Modulith"]
    Local["OpenTelemetry Collector"]
    Gateway["Telemetry Gateway"]
    Store["Telemetry Backend"]
    IdP["Identity Provider"]
    App -->|"OTLP over TLS / mTLS"| Local
    Local -->|"TLS + OAuth2 client"| Gateway
    Gateway -->|"TLS"| Store
    Local -.->|"Token request"| IdP
    Gateway -.->|"Token validation"| IdP
~~~

Nếu ứng dụng chạy cùng Pod/host với Collector, chặng đầu có thể dùng loopback hoặc Unix domain socket tùy kiến trúc. Chặng Collector tới gateway thường đi qua mạng và cần TLS cùng cơ chế xác thực riêng. Không mặc định rằng một kết nối nội bộ đã an toàn chỉ vì nó nằm trong cùng VPC hoặc Kubernetes cluster.

### Những gì cần bảo vệ

| Tài sản | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Trace, metrics, logs | Bị nghe lén hoặc sửa trên đường truyền. | TLS, xác minh hostname và certificate chain. |
| OTLP receiver | Client lạ gửi dữ liệu hoặc gây quá tải. | mTLS, OAuth2/bearer token, network policy và rate limit. |
| Client credential | Token/private key bị lộ qua repository hoặc log. | Secret manager, mounted secret, quyền file và rotation. |
| Telemetry attributes | Dữ liệu cá nhân hoặc bí mật bị xuất ra ngoài. | Redaction, allowlist attributes, sampling và data minimization. |
| Collector gateway | Bị dùng làm relay tới backend khác. | Egress allowlist, auth riêng cho từng exporter và giới hạn pipeline. |

## 3. Phân biệt TLS, mTLS và bearer token

Ba cơ chế giải quyết các câu hỏi khác nhau:

| Cơ chế | Bên được xác thực | Mục đích |
| --- | --- | --- |
| **TLS một chiều** | Client xác thực server bằng certificate. | Mã hóa kết nối và ngăn gửi dữ liệu tới server giả mạo. |
| **mTLS** | Client và server xác thực certificate của nhau. | Xác định workload được phép kết nối ở tầng transport. |
| **Bearer token / OAuth2** | Server xác thực danh tính/quyền của client qua token. | Cấp quyền theo service account, tenant hoặc scope. |

TLS không tự xác định client nào được phép gửi dữ liệu. mTLS cung cấp danh tính client ở tầng certificate; bearer token cho phép backend áp dụng policy theo subject, audience hoặc scope. Một hệ thống có thể dùng cả mTLS và OAuth2 nếu cần hai lớp kiểm soát.

**Luôn giữ TLS khi dùng bearer token.** Token là thông tin xác thực dạng bearer; ai lấy được token có thể sử dụng nó cho tới khi hết hạn hoặc bị thu hồi. Không gửi token qua HTTP thuần.

## 4. TLS xác thực server bằng certificate chain

Khi ứng dụng kết nối tới endpoint HTTPS của Collector, TLS client cần:

1. Nhận certificate server và intermediate certificates.
2. Xây dựng chain tới CA mà client tin cậy.
3. Kiểm tra thời hạn và chữ ký certificate.
4. Kiểm tra Subject Alternative Name (SAN) có hostname trong endpoint.
5. Hoàn tất handshake trước khi gửi OTLP payload.

Nếu backend dùng certificate do public CA cấp, JVM trust store thường đã có CA đó. Nếu dùng private CA, đưa CA certificate vào trust material mà exporter sử dụng. Với private CA, nên tin cậy CA phát hành thay vì pin một leaf certificate ngắn hạn, trừ khi có quy trình pinning và rotation được quản lý.

Không tắt xác minh certificate để chữa lỗi handshake. Các cấu hình kiểu insecure, insecureSkipVerify hoặc trust-all làm client chấp nhận server giả mạo và phá vỡ mục tiêu bảo mật.

## 5. OTLP endpoint, transport và port

OpenTelemetry Collector thường dùng các cổng mặc định:

| Transport | Port thường dùng | Ghi chú |
| --- | ---: | --- |
| OTLP/gRPC | 4317 | Dùng HTTP/2 và gRPC. |
| OTLP/HTTP | 4318 | Dùng HTTP; signal endpoint có path như /v1/traces, /v1/metrics, /v1/logs. |

Đây là port mặc định phổ biến, không phải bảo đảm cấu hình của mọi Collector. Kiểm tra receiver thực tế và network policy trước khi cấu hình ứng dụng.

Với OTLP/HTTP, endpoint chung có thể là:

~~~text
https://otel-gateway.example.net:4318
~~~

Spring Boot có thể thêm signal path khi dùng endpoint chung. Nếu đặt endpoint riêng cho từng signal, dùng URL đúng path mà exporter yêu cầu, ví dụ:

~~~text
https://otel-gateway.example.net:4318/v1/traces
https://otel-gateway.example.net:4318/v1/metrics
https://otel-gateway.example.net:4318/v1/logs
~~~

Không gửi HTTP exporter tới cổng gRPC hoặc ngược lại. Một lỗi port/protocol có thể biểu hiện thành connection reset, HTTP 404/415 hoặc lỗi HTTP/2 thay vì lỗi xác thực.

## 6. Cấu hình HTTPS và SSL bundle trên Spring Boot 4.x

Spring Boot 4.x hỗ trợ cấu hình SSL bundle để dùng chung trust material và client certificate cho nhiều kết nối. Ví dụ dưới đây dùng PEM:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        otlp-client:
          truststore:
            certificate: file:/run/secrets/otel/collector-ca.pem
          keystore:
            certificate: file:/run/secrets/otel/client.crt
            private-key: file:/run/secrets/otel/client.key

management:
  opentelemetry:
    otlp:
      endpoint: https://otel-gateway.example.net:4318
      compression: gzip
      headers:
        Authorization: "Bearer ${OTEL_EXPORT_TOKEN}"
    tracing:
      export:
        otlp:
          ssl:
            bundle: otlp-client
          transport: http
    logging:
      export:
        otlp:
          ssl:
            bundle: otlp-client
  otlp:
    metrics:
      export:
        ssl:
          bundle: otlp-client
~~~

Trong ví dụ:

- **truststore.certificate** chứa CA dùng để xác minh certificate của Collector.
- **keystore.certificate** và **keystore.private-key** là danh tính client khi Collector yêu cầu mTLS.
- **management.opentelemetry.otlp.*** cấu hình endpoint, compression và header dùng chung.
- Trace và log exporter tham chiếu bundle qua namespace management.opentelemetry.
- Micrometer OTLP metrics exporter tham chiếu bundle qua namespace management.otlp.metrics.export.

Các property tham chiếu bundle trong ví dụ là:

| Signal | SSL bundle property |
| --- | --- |
| Traces | management.opentelemetry.tracing.export.otlp.ssl.bundle |
| Logs | management.opentelemetry.logging.export.otlp.ssl.bundle |
| Metrics | management.otlp.metrics.export.ssl.bundle |

Nếu chỉ dùng TLS một chiều, có thể bỏ keystore và chỉ cấu hình truststore. Nếu backend không dùng token, bỏ Authorization header. Không đặt token thật trực tiếp trong file YAML hoặc commit secret vào repository.

### 6.1. Header riêng cho từng signal

Boot 4.x cho phép đặt endpoint/header riêng cho traces, logs và metrics. Cấu hình signal-specific có ưu tiên khi trùng key; header riêng được gộp với header chung và giá trị riêng thay thế giá trị chung nếu trùng tên.

Ví dụ:

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otel-gateway.example.net:4318
      headers:
        Authorization: "Bearer ${OTEL_DEFAULT_TOKEN}"
    tracing:
      export:
        otlp:
          headers:
            X-Telemetry-Signal: traces
    logging:
      export:
        otlp:
          headers:
            X-Telemetry-Signal: logs
~~~

Chỉ dùng token chung khi backend thực sự cấp cùng quyền cho cả ba signal. Nếu metrics, traces và logs có quyền hoặc tenant khác nhau, cấp credential riêng theo signal.

## 7. mTLS: Collector yêu cầu client certificate

mTLS hữu ích khi chỉ workload có certificate hợp lệ mới được gửi telemetry. Ở phía client, ứng dụng trình certificate và chứng minh quyền sở hữu private key. Ở phía Collector, receiver kiểm tra client certificate dựa trên CA tin cậy.

Ví dụ OTLP/HTTP receiver:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        tls:
          cert_file: /etc/otel/tls/server.crt
          key_file: /etc/otel/tls/server.key
          client_ca_file: /etc/otel/tls/client-ca.pem

processors:
  batch:

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

cert_file và key_file là certificate/private key của server Collector. client_ca_file là CA dùng để xác minh client certificate. Ví dụ debug exporter chỉ để kiểm tra pipeline; production cần exporter tới backend thực và cấu hình bảo vệ dữ liệu tương ứng.

Địa chỉ 0.0.0.0 lắng nghe trên mọi interface. Trong môi trường có nhiều network interface, ưu tiên bind vào địa chỉ private/Pod interface phù hợp và giới hạn nguồn bằng firewall hoặc NetworkPolicy. Nếu nền tảng yêu cầu bind mọi interface trong container, phải giữ receiver trong private network và không publish port ra Internet.

### 7.1. Phân biệt hai CA

- **Server CA:** ứng dụng dùng để xác minh certificate của Collector.
- **Client CA:** Collector dùng để xác minh certificate của ứng dụng.

Hai CA có thể giống hoặc khác nhau tùy PKI. Không đưa private key của CA vào ứng dụng hoặc Collector runtime; chỉ phân phối certificate chain cần thiết.

### 7.2. mTLS không thay thế authorization

mTLS chứng minh workload sở hữu certificate được cấp. Nếu mọi workload trong cluster dùng cùng một client certificate, backend chỉ phân biệt được cả nhóm như một identity. Cấp certificate riêng theo service/namespace/environment và áp policy theo subject/SAN nếu cần phân quyền chi tiết.

## 8. Xác thực bằng bearer token và OAuth2

Một backend có thể yêu cầu HTTP header:

~~~http
Authorization: Bearer <access-token>
~~~

Trong Spring Boot, header có thể được cấu hình qua property headers.* hoặc environment variable/secret injection. Ví dụ:

~~~yaml
management:
  opentelemetry:
    otlp:
      headers:
        Authorization: "Bearer ${OTEL_EXPORT_TOKEN}"
~~~

Đây là cấu hình token tĩnh tại thời điểm exporter được tạo. Nếu token ngắn hạn và cần refresh tự động, không nên lưu access token sắp hết hạn trong YAML rồi chờ exporter tự làm mới. Dùng Collector làm lớp trung gian để lấy token bằng OAuth2 client credentials hoặc tích hợp cơ chế workload identity phù hợp.

### 8.1. Collector lấy token để chuyển tiếp

Collector hỗ trợ auth extension cho exporter. Ví dụ dùng OAuth2 client để lấy token từ identity provider rồi gắn token vào request gửi remote Collector:

~~~yaml
extensions:
  oauth2client:
    client_id: telemetry-agent
    client_secret: ${env:OTEL_OAUTH_CLIENT_SECRET}
    token_url: https://identity.example.net/oauth2/token

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317

processors:
  batch:

exporters:
  otlp_grpc/remote:
    endpoint: remote-collector.example.net:4317
    tls:
      ca_file: /etc/otel/tls/remote-ca.pem
    auth:
      authenticator: oauth2client

service:
  extensions: [oauth2client]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp_grpc/remote]
~~~

Ví dụ minh họa cơ chế token của Collector; cấu hình TLS cho exporter tới remote endpoint vẫn phải được thiết lập theo certificate/CA của backend. Nếu Collector nhận telemetry từ ứng dụng qua mạng thay vì loopback, hãy bật TLS/mTLS hoặc auth ở receiver đó nữa.

## 9. Quản lý secret và private key

Credential cho telemetry cần được quản lý như database password hoặc API key:

- Lấy token/private key từ secret manager hoặc secret volume do nền tảng cấp.
- Giới hạn quyền đọc file secret cho user/container chạy ứng dụng.
- Không commit .pem, .key, token hoặc keystore có password vào Git.
- Không in Authorization header, private key, token response hoặc toàn bộ exporter configuration vào log.
- Tách credential theo môi trường và service; tránh dùng một token chung cho dev, staging và production.
- Có quy trình thu hồi credential khi workload bị xâm nhập.

Ví dụ sử dụng environment variable được inject từ secret:

~~~yaml
management:
  opentelemetry:
    otlp:
      headers:
        Authorization: "Bearer ${OTEL_EXPORT_TOKEN}"
~~~

Environment variable chỉ là phương thức truyền giá trị vào process, không tự nó là secret manager. Cần bảo đảm nền tảng không hiển thị giá trị trong dashboard, process inspection, diagnostic dump hoặc log.

## 10. Khác biệt cấu hình giữa Spring Boot 3.5 và 4.x

Không nên sao chép nguyên namespace OTLP giữa các major version:

| Chức năng | Spring Boot 3.5 | Spring Boot 4.x |
| --- | --- | --- |
| Trace endpoint | management.otlp.tracing.endpoint | management.opentelemetry.tracing.export.otlp.endpoint |
| Trace headers | management.otlp.tracing.headers.* | management.opentelemetry.tracing.export.otlp.headers.* |
| Trace TLS bundle property | Không có field ssl.bundle trong OtlpTracingProperties 3.5. | management.opentelemetry.tracing.export.otlp.ssl.bundle |
| Metrics endpoint | management.otlp.metrics.export.url | management.otlp.metrics.export.url |
| Metrics headers | management.otlp.metrics.export.headers.* | management.otlp.metrics.export.headers.* |
| Metrics TLS bundle property | Không có ssl.bundle trong OtlpMetricsProperties 3.5. | management.otlp.metrics.export.ssl.bundle |
| Common endpoint/headers cho các signal | Cấu hình theo từng signal. | Có management.opentelemetry.otlp.* cho endpoint, headers và compression chung. |

Spring Boot 4.x có thể dùng SSL bundle cho exporter tương ứng. Spring Boot 3.5 dùng namespace property cũ và có giới hạn khác nhau giữa trace với metrics. Vì vậy, đừng cho rằng cấu hình TLS customizer của trace tự động áp dụng cho metrics hoặc logs.

## 11. Cấu hình TLS nâng cao cho trace exporter trên Boot 3.5

Với Boot 3.5, OtlpHttpSpanExporterBuilderCustomizer cho phép bổ sung CA riêng và client certificate vào HTTP trace exporter. Ví dụ dưới đây đọc material từ secret files:

~~~java
package com.example.shop.observability;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;

import org.springframework.boot.actuate.autoconfigure.tracing.otlp.OtlpHttpSpanExporterBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@Configuration(proxyBeanMethods = false)
class OtlpTraceTlsConfiguration {

    @Bean
    OtlpHttpSpanExporterBuilderCustomizer traceTlsCustomizer(
            ResourceLoader resourceLoader) {
        return builder -> {
            try {
                byte[] trustedCa = read(
                        resourceLoader.getResource("file:/run/secrets/otel/ca.pem"));
                byte[] clientKey = read(
                        resourceLoader.getResource("file:/run/secrets/otel/client.key"));
                byte[] clientCertificate = read(
                        resourceLoader.getResource("file:/run/secrets/otel/client.crt"));

                builder.setTrustedCertificates(trustedCa);
                builder.setClientTls(clientKey, clientCertificate);
            }
            catch (IOException ex) {
                throw new UncheckedIOException("Cannot load OTLP TLS material", ex);
            }
        };
    }

    private static byte[] read(Resource resource) throws IOException {
        try (InputStream input = resource.getInputStream()) {
            return input.readAllBytes();
        }
    }
}
~~~

setTrustedCertificates cấu hình CA dùng để xác minh server; setClientTls cấu hình private key và certificate của client. Nếu chỉ cần TLS một chiều, bỏ phần đọc client key/certificate và lời gọi setClientTls.

Đây là customizer cho **OTLP HTTP trace exporter**. Nếu dùng gRPC, cần OtlpGrpcSpanExporterBuilderCustomizer và API tương ứng của gRPC builder. Với OTLP metrics ở Boot 3.5, kiểm tra cơ chế SSL của Micrometer registry/client đang dùng hoặc đặt Collector gần ứng dụng để Collector chịu trách nhiệm kết nối mTLS ra backend. Không coi snippet trace này là cấu hình bảo mật cho cả ba signal.

## 12. Bảo vệ cả chặng Collector tới backend

Khi dùng Collector, ứng dụng chỉ xác thực Collector gần nó. Collector lại là một client độc lập và cần trust/auth riêng khi kết nối remote backend.

Một mô hình vận hành thường dùng:

- Ứng dụng gửi tới Collector sidecar/agent qua loopback hoặc mTLS.
- Collector agent gửi tới gateway qua TLS và OAuth2 client credentials.
- Gateway chỉ nhận từ agent/gateway đã xác thực.
- Gateway chỉ được egress tới endpoint telemetry backend được allowlist.

Không giả định rằng Collector tự kế thừa token hoặc client certificate của ứng dụng. Mỗi hop là một kết nối riêng, có endpoint, trust store, credential và chính sách retry riêng.

## 13. Giới hạn egress và bảo vệ mạng

TLS và token không thay thế network segmentation. Ở lớp hạ tầng:

1. Chỉ cho phép workload ứng dụng kết nối tới Collector host/service và port cần thiết.
2. Chỉ cho phép Collector gateway egress tới telemetry backend, identity provider và DNS cần thiết.
3. Không public OTLP receiver nếu không có yêu cầu; ưu tiên private endpoint hoặc internal load balancer.
4. Không expose port 4317/4318 qua public ingress mặc định.
5. Dùng Kubernetes NetworkPolicy, cloud security group hoặc firewall để giới hạn source/destination.
6. Theo dõi kết nối bị từ chối và thay đổi allowlist.

Ví dụ chính sách logic:

| Nguồn | Đích | Port | Chính sách |
| --- | --- | ---: | --- |
| Application namespace | Collector Service nội bộ | TCP 4317 hoặc 4318 | Allow theo namespace/pod selector. |
| Untrusted namespace | Collector Service | TCP 4317/4318 | Deny. |
| Collector gateway | Telemetry backend | Theo endpoint cấu hình | Allow theo FQDN/IP và port được duyệt. |
| Application namespace | Internet tùy ý | Any | Deny theo default egress policy nếu phù hợp. |
| Collector gateway | Identity provider | HTTPS 443 | Allow khi dùng OAuth2 token. |

Nếu dùng Kubernetes NetworkPolicy, cần CNI hỗ trợ enforcement. DNS egress có thể cần rule riêng; khi dùng FQDN allowlist, xác nhận nền tảng có hỗ trợ policy theo hostname hay phải quản lý IP/range.

## 14. Giảm dữ liệu nhạy cảm trước khi export

Mã hóa đường truyền không làm telemetry payload tự động an toàn. Dữ liệu có thể được lưu lâu dài, nhân bản qua nhiều Collector hoặc được nhiều nhóm truy cập.

Trước khi export, review:

- Không đưa access token, cookie, password, private key hoặc Authorization header vào span/log attributes.
- Tránh ghi request/response body mặc định nếu body có thông tin cá nhân hoặc bí mật.
- Redact SQL parameters, email, số điện thoại, payment reference và customer identifier khi không cần thiết.
- Dùng low-cardinality attributes như module name, event type, outcome và environment cho metrics.
- Dùng trace/log fields có kiểm soát để điều tra, và giới hạn quyền truy cập ở backend.
- Đặt retention và access policy theo mức nhạy cảm của telemetry.

Với Spring Modulith, event publication metrics có thể cho biết module và event type; traces có thể mang module spans, method, route và error details. Chỉ thêm business attributes khi có mục đích rõ ràng và chính sách lưu trữ phù hợp.

## 15. Kiểm thử TLS và mTLS từ môi trường chạy ứng dụng

Kiểm tra từ cùng container/Pod hoặc network namespace nơi ứng dụng thực sự chạy. Một phép thử trên laptop không chứng minh production container có cùng DNS, CA file hoặc route.

### 15.1. Xác minh server certificate

~~~bash
openssl s_client \
  -connect otel-gateway.example.net:4318 \
  -servername otel-gateway.example.net \
  -CAfile /run/secrets/otel/collector-ca.pem \
  -verify_return_error
~~~

Kỳ vọng: certificate chain hợp lệ, hostname/SAN khớp và verification thành công. Lệnh này kiểm tra TLS handshake; nó chưa chứng minh token hoặc OTLP ingest thành công.

### 15.2. Xác minh mTLS

~~~bash
openssl s_client \
  -connect otel-gateway.example.net:4318 \
  -servername otel-gateway.example.net \
  -CAfile /run/secrets/otel/collector-ca.pem \
  -cert /run/secrets/otel/client.crt \
  -key /run/secrets/otel/client.key \
  -verify_return_error
~~~

So sánh kết quả khi có và không có client certificate. Nếu receiver yêu cầu mTLS, kết nối thiếu certificate hợp lệ phải bị từ chối.

### 15.3. Xác minh OTLP ingest

Sau khi handshake thành công, phát một observation/trace test từ ứng dụng. Kiểm tra:

1. Exporter không ghi lỗi UNAVAILABLE, UNAUTHENTICATED, PERMISSION_DENIED hoặc certificate verification.
2. Collector nhận request và ghi nhận batch.
3. Pipeline có processor/exporter hoạt động.
4. Telemetry xuất hiện ở backend với service name và resource attributes đúng.
5. Token hoặc private key không xuất hiện trong logs.

Không dùng một HTTP GET vào /v1/traces để kết luận exporter hoạt động; OTLP receiver mong đợi request theo đúng protocol và method.

## 16. Kiểm thử cấu hình và vận hành trong CI

Các kiểm tra tự động có thể bao gồm:

- Kiểm tra cấu hình không chứa endpoint http:// trong production profile nếu backend yêu cầu TLS.
- Kiểm tra tên SSL bundle được tham chiếu tồn tại trong cấu hình.
- Kiểm tra secret path được mount trong container và quyền file đủ chặt.
- Dùng test Collector hoặc mock OTLP endpoint có TLS để xác nhận handshake.
- Có test mTLS âm: không certificate hoặc certificate không được CA tin cậy phải thất bại.
- Có test auth âm: token thiếu, hết hạn hoặc sai audience phải bị từ chối.
- Có smoke test export một trace/metric/log và kiểm tra Collector nhận được.
- Kiểm tra exporter error metrics và queue/drop metrics trong môi trường test.

Test không nên ghi token thật hoặc private key vào artifact. Dùng certificate test riêng, token ngắn hạn và backend giả lập.

## 17. Chẩn đoán lỗi kết nối telemetry backend

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| PKIX path building failed | JVM/exporter không tin CA ký certificate server. | Thêm đúng CA chain vào trust material; xác minh bundle đang được signal exporter sử dụng. |
| No subject alternative DNS name matching | Hostname endpoint không nằm trong SAN của certificate. | Dùng DNS name đúng hoặc cấp lại certificate có SAN phù hợp. |
| certificate expired | Server/client certificate hết hạn hoặc clock sai. | Kiểm tra thời gian, cấp certificate mới và rotation. |
| handshake_failure | TLS version/cipher không tương thích hoặc mTLS certificate bị từ chối. | Kiểm tra protocol, certificate chain, key format và client CA ở receiver. |
| HTTP 401 | Thiếu hoặc token không hợp lệ. | Kiểm tra Authorization header, issuer, audience, expiry và secret injection. |
| HTTP 403 | Danh tính hợp lệ nhưng không có quyền ingest. | Kiểm tra scope/role/tenant và policy backend. |
| gRPC UNAUTHENTICATED | Metadata token hoặc client identity không hợp lệ. | Kiểm tra auth interceptor/headers và mTLS identity. |
| gRPC PERMISSION_DENIED | Backend từ chối quyền của client. | Kiểm tra policy và scope được cấp. |
| Connection refused/timeout | Sai host/port, firewall hoặc route. | Kiểm tra DNS, service endpoint, egress policy và Collector receiver. |
| HTTP 404/415 | Sai OTLP path hoặc protocol/encoding. | Dùng đúng HTTP signal path hoặc gRPC endpoint. |
| App export được trace nhưng metrics thất bại | Trace và metrics có exporter/config namespace riêng. | Kiểm tra dependency, endpoint, headers và SSL bundle của từng signal. |
| Local Collector nhận nhưng backend không có dữ liệu | Collector pipeline/exporter/auth hoặc remote egress lỗi. | Kiểm tra Collector logs, exporter queue, auth token và remote TLS. |
| Hoạt động sau restart nhưng hỏng sau token rotation | Token tĩnh được nạp lúc startup hoặc exporter không refresh. | Dùng cơ chế token refresh/Collector auth extension hoặc recreate exporter theo quy trình. |

Không bật debug logging làm lộ Authorization header hoặc dữ liệu payload nhạy cảm trong production. Khi cần trace TLS handshake, dùng môi trường test và giới hạn quyền truy cập log.

## 18. Rotation certificate và token

Rotation cần tránh làm đứt kết nối đang chạy:

### CA rotation

1. Phân phối CA mới vào trust bundle của client trước.
2. Cấu hình server/Collector dùng certificate mới có chain tới CA mới.
3. Kiểm tra handshake từ workload thật.
4. Chờ hết thời gian chuyển tiếp và xác nhận không còn certificate cũ.
5. Gỡ CA cũ khỏi trust bundle.

### Client certificate rotation

1. Cấp client certificate mới cho đúng service identity.
2. Thêm CA ký client certificate mới vào trust bundle của Collector.
3. Mount certificate/key mới và khởi tạo lại exporter hoặc workload theo cơ chế reload hỗ trợ.
4. Xác nhận Collector nhận client identity mới.
5. Thu hồi certificate cũ sau khi toàn bộ instance đã chuyển đổi.

### Token rotation

1. Cấp token/secret mới và cho phép overlap ngắn nếu backend hỗ trợ.
2. Cập nhật secret manager hoặc OAuth2 client credentials.
3. Xác nhận exporter/Collector dùng token mới thành công.
4. Thu hồi token cũ.
5. Kiểm tra token không còn xuất hiện trong log, manifest hoặc lịch sử cấu hình.

SSL bundle hoặc secret volume có hỗ trợ reload tùy cấu hình và thành phần sử dụng; không giả định mọi exporter tự reload file khi file thay đổi. Kiểm thử rotation trên đúng Spring Boot/OpenTelemetry exporter version đang chạy.

## 19. Checklist trước production

- [ ] OTLP endpoint dùng HTTPS hoặc gRPC TLS; không gửi telemetry qua mạng không tin cậy bằng HTTP thuần.
- [ ] Server certificate chain được xác minh và hostname khớp SAN.
- [ ] Private CA đã được thêm vào trust material của đúng exporter.
- [ ] mTLS được bật khi cần xác thực workload ở tầng transport.
- [ ] Token/OAuth2 có audience, scope và thời hạn phù hợp.
- [ ] Token/private key được cấp qua secret manager hoặc mounted secret.
- [ ] Không ghi credential hoặc payload nhạy cảm vào log.
- [ ] Trace, metrics và logs có endpoint/header/SSL config đúng cho từng signal.
- [ ] Namespace property đúng với Spring Boot version đang chạy.
- [ ] Collector receiver chỉ mở trên interface/network cần thiết.
- [ ] Collector-to-backend có TLS và auth riêng cho hop đó.
- [ ] Egress allowlist giới hạn host/port tới Collector, backend và identity provider.
- [ ] Telemetry attributes đã được redaction và retention được xác định.
- [ ] Có test TLS, mTLS, auth âm/dương và OTLP ingest.
- [ ] Có cảnh báo certificate sắp hết hạn, exporter failure và Collector queue/drop.
- [ ] Có runbook rotation và thu hồi token/certificate.

## 20. Tài liệu tham khảo chính thức

- **Spring Boot — Observability:** https://docs.spring.io/spring-boot/reference/actuator/observability.html — cấu hình OTLP endpoint, headers, compression và mapping environment variables trên Boot 4.x.
- **Spring Boot — Tracing:** https://docs.spring.io/spring-boot/reference/actuator/tracing.html — cấu hình OTLP tracing exporter và builder customizers.
- **Spring Boot — SSL:** https://docs.spring.io/spring-boot/reference/features/ssl.html — SSL bundles JKS/PEM, truststore và keystore cho client/server.
- **Spring Boot 3.5 — Tracing:** https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html — dependency và properties OTLP của Boot 3.5.
- **Spring Boot 3.5 — OtlpTracingProperties API:** https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpTracingProperties.html — các trường cấu hình trace exporter 3.5.
- **Spring Boot 3.5 — OtlpHttpSpanExporterBuilderCustomizer API:** https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpHttpSpanExporterBuilderCustomizer.html — extension point cho trace exporter.
- **OpenTelemetry Collector — Configuration:** https://opentelemetry.io/docs/collector/configuration/ — cấu hình receiver/exporter, authenticator và pipeline.
- **OpenTelemetry Collector — Security guidance:** https://opentelemetry.io/docs/security/config-best-practices/ — bảo vệ Collector, lưu secret và giảm attack surface.
- **OpenTelemetry — Handling sensitive data:** https://opentelemetry.io/docs/security/handling-sensitive-data/ — data minimization và processor xử lý thuộc tính nhạy cảm.
- **OpenTelemetry — Collector hosting best practices:** https://opentelemetry.io/docs/security/hosting-best-practices/ — least privilege, bảo vệ receiver và tài nguyên Collector.
- **OpenTelemetry Protocol — Exporter specification:** https://opentelemetry.io/docs/specs/otel/protocol/exporter/ — endpoint, TLS certificate và exporter authentication.

## 21. Tổng kết

Bảo vệ kết nối telemetry backend cần phối hợp **mã hóa, xác thực, phân quyền và kiểm soát mạng**. TLS xác minh server và mã hóa payload; mTLS xác minh thêm workload client; bearer token/OAuth2 bổ sung quyền theo identity và scope. Mỗi chặng từ ứng dụng tới Collector rồi tới backend phải có trust material và credential phù hợp.

Spring Boot 4.x hỗ trợ SSL bundle cho các OTLP exporter tương ứng, trong khi Boot 3.5 dùng namespace property cũ và có giới hạn khác nhau giữa trace với metrics. Hãy xác minh cấu hình theo đúng version và từng signal, giữ secret ngoài repository, giới hạn egress, kiểm thử cả trường hợp bị từ chối và lập quy trình rotation. Khi những lớp này được kiểm soát, telemetry của Spring Modulith có thể được chuyển tới backend để vận hành mà không biến chính pipeline quan sát thành một điểm rò rỉ dữ liệu hoặc cửa ngõ gửi dữ liệu trái phép.
