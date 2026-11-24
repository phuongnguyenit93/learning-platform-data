# Quản lý token, URL đích và thông tin xác thực registry qua cấu hình riêng

Micrometer có thể xuất metrics đến nhiều hệ thống giám sát. Mỗi registry có thể cần URL, token, account ID, organization, bucket hoặc HTTP header riêng. Các giá trị này phải được cấu hình theo môi trường triển khai và được cấp từ nguồn quản lý bí mật; không đặt token thật trong source code, file cấu hình được commit hoặc tag của metric.

Khi thiết kế cấu hình, hãy tách ba loại dữ liệu:

1. **Địa chỉ đích:** URL, hostname, port và path của metrics endpoint. Đây thường là cấu hình môi trường, không nhất thiết là bí mật.
2. **Thông tin xác thực:** API key, bearer token, username/password, client certificate hoặc private key. Đây là dữ liệu nhạy cảm và cần nguồn cấp riêng.
3. **Thông tin mô tả service:** service name, environment, region hoặc deployment. Đây là metadata quan sát, không phải credential.

Sự tách biệt này giúp thay đổi endpoint mà không phải phát hành lại code, xoay vòng token mà không sửa artifact, và tránh gửi thông tin xác thực vào telemetry.

## Registry có thể push hoặc được scrape

Trước khi cấu hình credential, xác định registry dùng mô hình truyền dữ liệu nào:

| Mô hình | Ví dụ | Ai chủ động kết nối? | Vị trí xác thực thường gặp |
|---|---|---|---|
| Pull/scrape | Prometheus scrape /actuator/prometheus | Prometheus gọi ứng dụng | Scraper hoặc reverse proxy xác thực với endpoint; ứng dụng bảo vệ Actuator |
| Push | OTLP, Datadog, New Relic, InfluxDB | Ứng dụng gửi batch đến backend | Ứng dụng cung cấp token/header/API key cho registry |
| Push qua gateway | Prometheus Pushgateway | Ứng dụng gửi đến Pushgateway, Prometheus scrape gateway | Ứng dụng xác thực với gateway; Prometheus xác thực khi scrape nếu gateway được bảo vệ |

Không phải registry nào cũng có trường API key. Với Prometheus pull thông thường, ứng dụng không gửi token đến Prometheus khi export. Prometheus chủ động scrape endpoint; nếu endpoint cần bảo vệ, cấu hình TLS/auth ở web server, Spring Security hoặc proxy, đồng thời cấu hình scraper gửi credential tương ứng.

Với registry push, credential thường nằm trong thuộc tính riêng của registry hoặc trong header HTTP. Không giả định token dùng cho Datadog cũng có thể dùng cho OTLP hoặc một môi trường khác.

## Quản lý dependency và cấu hình theo môi trường

Spring Boot tự cấu hình registry khi dependency tương ứng có trên classpath. Ví dụ, với OTLP:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-otlp")
}
~~~

Phiên bản registry nên được quản lý bởi Spring Boot dependency management hoặc BOM tương thích. Không tự ghép phiên bản Micrometer Core, registry implementation và Spring Boot khác dòng nếu chưa kiểm tra tương thích.

File cấu hình được commit chỉ nên chứa giá trị mặc định không nhạy cảm hoặc placeholder:

~~~yaml
management:
  otlp:
    metrics:
      export:
        enabled: true
        url: ${METRICS_OTLP_URL}
        step: 30s
        connect-timeout: 2s
        read-timeout: 10s
        headers:
          authorization: "Bearer ${METRICS_OTLP_TOKEN}"
~~~

METRICS_OTLP_URL là cấu hình endpoint có thể thay đổi giữa local, staging và production. METRICS_OTLP_TOKEN được lấy từ môi trường chạy ứng dụng. Không thay placeholder bằng token thật trước khi commit.

Nếu token bắt buộc trong môi trường production, để ứng dụng fail khi thiếu secret thay vì tự rơi về một endpoint hoặc credential mặc định không an toàn. Chỉ dùng default cho URL nếu default đó thực sự phù hợp với môi trường local; không đặt default cho token.

Có thể tách phần cấu hình không nhạy cảm theo profile:

~~~yaml
# application-prod.yml
management:
  otlp:
    metrics:
      export:
        url: ${METRICS_OTLP_URL}
        headers:
          authorization: "Bearer ${METRICS_OTLP_TOKEN}"
~~~

Profile chỉ chọn cấu hình. Nó không phải kho bí mật: file profile vẫn có thể được đóng gói trong artifact hoặc lưu trong repository. Token phải đến từ biến môi trường, mounted secret hoặc secret manager.

## Cấp token bằng biến môi trường

Với môi trường đơn giản, hệ thống triển khai có thể inject token vào process environment. Ví dụ trên Linux:

~~~bash
export METRICS_OTLP_URL="https://collector.example.net:4318/v1/metrics"
export METRICS_OTLP_TOKEN="<token-from-secret-store>"
java -jar app.jar
~~~

Trong CI/CD hoặc orchestrator, lấy giá trị từ secret store rồi inject vào process khi chạy. Không ghi token trực tiếp vào script được commit, command line argument, build log hoặc output chẩn đoán.

Biến môi trường giúp tách secret khỏi source code, nhưng không phải vault. Người có quyền đọc environment của process, cấu hình container hoặc crash dump có thể tiếp cận giá trị. Giới hạn quyền truy cập host/container và ưu tiên secret mount hoặc secret manager khi môi trường hỗ trợ.

Với thuộc tính map header, cách ít nhầm nhất là giữ key header trong YAML và dùng placeholder cho giá trị:

~~~yaml
management:
  otlp:
    metrics:
      export:
        headers:
          authorization: "Bearer ${METRICS_OTLP_TOKEN}"
~~~

Không dùng biến môi trường có tên header làm key mới một cách tùy tiện; kiểm tra quy tắc binding của phiên bản Spring Boot nếu muốn bind trực tiếp map từ environment.

## Cấp token bằng mounted secret và config tree

Trong container hoặc Kubernetes, có thể mount secret thành file chỉ đọc. Spring Boot hỗ trợ config tree để ánh xạ tên file thành property key.

Ví dụ cấu trúc mount:

~~~text
/run/secrets/
  metrics.otlp.authorization
~~~

Nội dung file metrics.otlp.authorization chỉ chứa token, không có tiền tố Bearer:

~~~text
<token-from-secret-store>
~~~

Nạp config tree và tham chiếu secret trong cấu hình:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"

management:
  otlp:
    metrics:
      export:
        url: ${METRICS_OTLP_URL}
        headers:
          authorization: "Bearer ${metrics.otlp.authorization}"
~~~

Tên file trở thành property metrics.otlp.authorization. Placeholder thêm tiền tố Bearer khi tạo HTTP header. Nếu secret là bắt buộc, cân nhắc bỏ optional: để ứng dụng không khởi động khi mount bị thiếu. Đặt quyền file và quyền mount chỉ cho user chạy ứng dụng đọc.

Tên file trong config tree phải phù hợp với property key mà ứng dụng tham chiếu. Kiểm tra mount thực tế và cấu hình import ở môi trường triển khai; đừng giả định secret đã được mount chỉ vì manifest có khai báo.

## Cấu hình URL và header OTLP

Với Micrometer OTLP registry, Spring Boot bind cấu hình dưới prefix management.otlp.metrics.export. URL HTTP metrics thường chứa path /v1/metrics:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: https://otel-collector.internal:4318/v1/metrics
        headers:
          authorization: "Bearer ${METRICS_OTLP_TOKEN}"
        step: 30s
        connect-timeout: 2s
        read-timeout: 10s
~~~

Các điểm cần xác nhận:

- URL trỏ đúng Collector hoặc backend, đúng scheme, hostname, port và path.
- OTLP/HTTP thường dùng cổng 4318 và metrics path /v1/metrics.
- OTLP/gRPC thường dùng cổng 4317; không thể đổi port của HTTP client rồi coi đó là gRPC.
- Header chứa token phải theo đúng scheme mà backend yêu cầu, ví dụ Bearer hoặc header API key riêng.
- step điều khiển chu kỳ publish; nó không phải thời gian timeout.
- Timeout kết nối và timeout đọc cần phù hợp với mạng và kích thước batch.

Không nhúng token vào URL như https://user:password@host/path?token=... . URL thường xuất hiện trong log, exception, proxy access log và dashboard cấu hình. Dùng header hoặc cơ chế xác thực chính thức của registry.

Spring Boot cũng hỗ trợ thuộc tính management.otlp.metrics.export.headers.* cho header tùy chỉnh. Khi dùng cấu hình này, giữ tên header ổn định và chỉ đưa secret vào giá trị được inject từ nguồn bên ngoài.

## TLS, CA riêng và mutual TLS

Token không thay thế mã hóa đường truyền. Khi gửi telemetry qua mạng, dùng HTTPS hoặc TLS của giao thức tương ứng. Xác minh certificate chain và hostname của endpoint; không tắt kiểm tra certificate để khắc phục tạm lỗi trust.

Nếu Collector dùng CA nội bộ, cấu hình trust material phù hợp cho HTTP client. Spring Boot có SSL bundle và thuộc tính registry như management.otlp.metrics.export.ssl.bundle ở các phiên bản hỗ trợ. Có thể khai báo bundle cho truststore hoặc client certificate theo yêu cầu endpoint.

Mutual TLS sử dụng client certificate và private key để xác thực ứng dụng với server. Private key phải được cấp từ secret store hoặc file mount có quyền hạn chế. Không commit keystore, PEM private key hoặc password của keystore.

Nếu backend yêu cầu cả TLS client authentication và bearer token, hai cơ chế có thể cùng tồn tại: TLS xác thực kết nối ở tầng transport, còn token xác thực quyền ingest ở tầng ứng dụng. Cấu hình đúng theo chính sách backend.

## Mỗi registry có prefix và credential riêng

Spring Boot cung cấp property prefix theo từng registry. Ví dụ:

| Registry | Endpoint/đích | Credential hoặc metadata thường cấu hình |
|---|---|---|
| OTLP | management.otlp.metrics.export.url | headers.*, SSL bundle |
| Datadog | management.datadog.metrics.export.uri | api-key; application-key nếu cần metadata API |
| New Relic | Endpoint mặc định hoặc management.newrelic.metrics.export.uri | api-key và account-id |
| InfluxDB | management.influx.metrics.export.uri | token, org và bucket |
| Prometheus scrape | Endpoint /actuator/prometheus | Auth/TLS bảo vệ endpoint và cấu hình tương ứng ở scraper/proxy |

Ví dụ cấu hình Datadog:

~~~yaml
management:
  datadog:
    metrics:
      export:
        enabled: true
        uri: https://api.datadoghq.eu
        api-key: ${DATADOG_API_KEY}
        step: 30s
~~~

Chọn site URI phù hợp với tài khoản Datadog. API key phải được inject từ secret store. Không đưa application key vào cấu hình nếu chức năng export đang dùng không cần nó.

Ví dụ cấu hình New Relic:

~~~yaml
management:
  newrelic:
    metrics:
      export:
        enabled: true
        api-key: ${NEW_RELIC_API_KEY}
        account-id: ${NEW_RELIC_ACCOUNT_ID}
        step: 30s
~~~

Ví dụ cấu hình InfluxDB v2:

~~~yaml
management:
  influx:
    metrics:
      export:
        uri: https://influx.example.net:8086
        org: ${INFLUX_ORG}
        bucket: ${INFLUX_BUCKET}
        token: ${INFLUX_TOKEN}
~~~

Tên và tính sẵn có của property phụ thuộc phiên bản Spring Boot cùng registry implementation. Đối chiếu metadata cấu hình của đúng phiên bản đang dùng trước khi triển khai; không sao chép prefix từ một phiên bản khác mà chưa kiểm tra.

## Prometheus pull và bảo vệ Actuator endpoint

Prometheus thông thường scrape ứng dụng. Ứng dụng expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Endpoint /actuator/prometheus không phải nơi ứng dụng gửi token ingest. Prometheus kết nối đến endpoint này. Nếu cần xác thực, bảo vệ endpoint bằng Spring Security, reverse proxy hoặc service mesh; sau đó cấu hình Prometheus scrape client dùng TLS và credential tương ứng.

Không expose toàn bộ Actuator chỉ để Prometheus scrape metrics. Chỉ expose endpoint cần thiết, giới hạn network access và tránh để health/configuration endpoint tiết lộ chi tiết nội bộ.

Nếu dùng Pushgateway, ứng dụng kết nối đến gateway theo cấu hình push registry. Khi đó cần bảo vệ đường ứng dụng → Pushgateway; Prometheus vẫn scrape Pushgateway theo cấu hình riêng. Đừng nhầm hai chặng xác thực này.

Với Spring Boot Prometheus Pushgateway integration, cấu hình push và credential nằm dưới nhánh riêng:

~~~yaml
management:
  prometheus:
    metrics:
      export:
        pushgateway:
          enabled: true
          address: pushgateway.internal:9091
          scheme: https
          username: ${PUSHGATEWAY_USERNAME}
          password: ${PUSHGATEWAY_PASSWORD}
          push-rate: 30s
~~~

Nếu gateway dùng bearer token thay cho Basic authentication, dùng thuộc tính token được phiên bản Spring Boot hỗ trợ và không cấu hình đồng thời các cơ chế xác thực không cần thiết. Cổng, scheme và credential phải khớp với cấu hình gateway. Prometheus scrape gateway là một kết nối khác; nếu gateway bảo vệ endpoint scrape, cấu hình xác thực ở phía Prometheus riêng.

Ví dụ khi gateway yêu cầu token:

~~~yaml
management:
  prometheus:
    metrics:
      export:
        pushgateway:
          enabled: true
          address: pushgateway.internal:9091
          scheme: https
          token: ${PUSHGATEWAY_TOKEN}
~~~

Chọn cấu hình username/password hoặc token theo cơ chế gateway đang bật; không điền đồng thời chỉ để thử.

## Không để credential lọt vào metric hoặc log

Token và thông tin xác thực không phải metadata của service. Không đưa chúng vào:

- Meter name, tag, common tag hoặc distribution tag.
- Observation low-cardinality/high-cardinality key value.
- Resource attribute như service.name hoặc deployment.environment.
- Exception message, log statement, tracing baggage hoặc span attribute.
- URL query string, request path hoặc tên file metric.

Ví dụ sai:

~~~java
registry.counter(
        "metrics.export",
        "api_key", apiKey,
        "endpoint", endpoint
).increment();
~~~

Ví dụ đúng: metric chỉ ghi nhận trạng thái export theo nhóm hữu hạn, còn endpoint được cấu hình riêng:

~~~java
registry.counter(
        "metrics.export.failures",
        "backend", "otlp",
        "reason", "unauthorized"
).increment();
~~~

Không log nguyên header Authorization hoặc object cấu hình chứa token. Khi chẩn đoán, chỉ ghi backend, hostname đã được phép hiển thị, HTTP status, loại lỗi và correlation ID đã được làm sạch. Kiểm tra chính sách redaction của logging và Actuator; không giả định mọi phiên bản hoặc custom endpoint đều tự che mọi property nhạy cảm.

## Quyền tối thiểu, tách môi trường và rotation

Token ingest nên có quyền tối thiểu cần thiết: chỉ ghi metrics vào đúng project, tenant hoặc organization. Không dùng token quản trị tài khoản nếu backend cung cấp token chỉ có quyền ingest. Tách token cho local, staging và production; tách token giữa service hoặc nhóm workload khi chính sách backend hỗ trợ.

Quy trình rotation nên có các bước:

1. Tạo token mới với cùng quyền tối thiểu.
2. Cập nhật secret store hoặc mounted secret cho workload.
3. Khởi động lại hoặc reload cấu hình theo khả năng của ứng dụng.
4. Xác nhận export thành công bằng log/metric và dữ liệu xuất hiện ở backend.
5. Thu hồi token cũ sau khi các instance đã chuyển sang token mới.
6. Kiểm tra không còn workload nào dùng token cũ.

Nhiều registry đọc cấu hình lúc khởi tạo và không tự reload token khi file secret thay đổi. Nếu ứng dụng không hỗ trợ refresh an toàn, cần rollout instance mới để nạp credential mới. Không thu hồi token cũ trước khi xác nhận rollout hoàn tất, trừ khi token đã bị lộ và cần thu hồi khẩn cấp.

Thiết lập expiration và cảnh báo trước ngày hết hạn nếu backend hỗ trợ. Ghi nhận owner, mục đích, môi trường, quyền và ngày rotation của từng credential trong hệ thống quản lý secret; không ghi giá trị token vào tài liệu vận hành.

## Kiểm tra cấu hình mà không dùng token thật

Có thể kiểm tra property binding bằng giá trị giả trong test:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        headers:
          authorization: "Bearer test-token"
~~~

Test context có thể xác nhận registry nhận đúng URL và header mà không kết nối backend thật. Với integration test, dùng HTTP server giả lập hoặc Collector local để kiểm tra request, status và header đã gửi. Không in header đầy đủ trong test report; chỉ xác nhận header tồn tại hoặc so sánh trong bộ nhớ.

Các kiểm tra cần có:

- URL đúng scheme, host, port và path.
- Credential được bind từ property source dự kiến.
- Thiếu token bắt buộc làm ứng dụng fail theo chính sách đã chọn.
- Header được gửi đúng tên và scheme.
- TLS xác minh certificate và hostname.
- HTTP 401/403 được nhận diện là lỗi xác thực/phân quyền.
- HTTP 404 hoặc lỗi protocol được phân biệt với lỗi token.
- Credential không xuất hiện trong log, endpoint chẩn đoán hoặc metric tag.
- Rotation thực sự chuyển workload sang token mới.

Không dùng token production trong unit test, screenshot, pastebin hoặc issue tracker. Test secret source bằng fixture giả; test kết nối production bằng quy trình vận hành được kiểm soát.

## Chẩn đoán lỗi export

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| HTTP 401 | Token thiếu, sai, hết hạn hoặc header sai scheme | Kiểm tra property source, tên header và trạng thái token trong secret manager |
| HTTP 403 | Token hợp lệ nhưng thiếu quyền ingest hoặc sai tenant/project | Kiểm tra scope, account, organization và project |
| Connection refused | Host/port sai, Collector không chạy hoặc network policy chặn | Kiểm tra DNS, port, route và trạng thái receiver |
| HTTP 404 | Sai path hoặc endpoint không hỗ trợ loại signal | Kiểm tra path, ví dụ OTLP metrics /v1/metrics |
| TLS handshake failure | CA không tin cậy, certificate hết hạn, hostname mismatch hoặc client certificate sai | Kiểm tra truststore, SSL bundle, thời hạn và SAN của certificate |
| Export vẫn đến localhost | URL chưa được override hoặc profile không được kích hoạt | Kiểm tra active profile và property source hiệu lực |
| Chỉ một số instance export được | Secret mount hoặc environment khác nhau giữa replica | So sánh metadata cấu hình không nhạy cảm và rollout status |
| Token cũ tiếp tục được dùng | Registry không reload config sau khi secret đổi | Rollout instance hoặc dùng cơ chế refresh được hỗ trợ |
| Backend từ chối batch lớn | Payload/batch vượt giới hạn hoặc timeout | Kiểm tra batch size, step và response từ backend |
| Log chứa credential | Log request/configuration quá chi tiết hoặc redaction thiếu | Dừng log nhạy cảm, xử lý log đã lộ và rotation token |

Không ghi token vào log để chứng minh cấu hình đã bind. Chỉ xác nhận secret có mặt, độ dài nếu chính sách cho phép, nguồn property hoặc trạng thái xác thực; tránh hiển thị prefix/suffix token vì vẫn có thể làm lộ thông tin.

## Checklist vận hành

- [ ] Đã xác định registry dùng pull, push hay push qua gateway.
- [ ] URL đích được cấu hình riêng theo môi trường và đúng protocol/path.
- [ ] Token hoặc credential được lấy từ secret manager, environment hoặc mounted secret.
- [ ] File cấu hình được commit chỉ chứa placeholder, không có secret thật.
- [ ] Mỗi registry dùng đúng property prefix và credential riêng.
- [ ] Credential có quyền ingest tối thiểu và được tách theo môi trường.
- [ ] Endpoint dùng TLS; certificate chain và hostname được xác minh.
- [ ] Secret file có quyền đọc hạn chế và không được đóng gói vào image.
- [ ] Không đưa credential vào URL, metric tag, resource attribute, trace hoặc log.
- [ ] Actuator chỉ expose endpoint cần thiết và được bảo vệ phù hợp.
- [ ] Có quy trình rotation, expiration và thu hồi token.
- [ ] Đã kiểm tra HTTP 401/403, endpoint sai, TLS và network failure.
- [ ] Đã xác nhận cấu hình thực tế trên mọi replica mà không in secret.

Quản lý token, URL và credential theo cấu hình riêng giúp Micrometer xuất metrics đến đúng backend mà không gắn bí mật vào code hoặc telemetry. Giữ endpoint trong cấu hình môi trường, cấp credential từ secret source, tách quyền theo registry và xác minh TLS. Khi có rotation, kiểm tra từng instance đã nạp token mới rồi mới thu hồi token cũ; khi có lỗi export, chẩn đoán bằng endpoint, status và trạng thái cấu hình đã làm sạch thay vì ghi token ra log.

## Tài liệu tham khảo

- [Spring Boot Metrics and Supported Registries](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Micrometer OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)
