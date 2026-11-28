# Override cấu hình bằng biến môi trường

## Mục tiêu và bối cảnh

Trong ứng dụng Spring Boot được tổ chức thành các application module bằng **Spring Modulith**, cùng một phiên bản chương trình có thể chạy ở máy phát triển, CI, staging và production. Mỗi môi trường cần những giá trị riêng cho tên ứng dụng, message broker, tỷ lệ lấy mẫu trace, endpoint quan sát và mức chi tiết của logging. Nếu phải sửa mã hoặc đóng gói lại JAR mỗi lần đổi môi trường, việc đối chiếu module graph, Actuator và số liệu vận hành trở nên khó khăn vì mỗi nơi có thể đang chạy một bản khác nhau.

Bài học thuộc chương **Cấu hình môi trường**, trong phạm vi **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: dùng Spring Modulith để tạo tài liệu ranh giới application module, quan sát tương tác qua Actuator, event metrics, tracing và context propagation. Chủ đề cụ thể là **override cấu hình bằng biến môi trường**, dựa trên cơ chế externalized configuration của Spring Boot.

Sau khi học, bạn cần:

1. Hiểu giá trị nào thắng khi cùng một property xuất hiện ở `application.yml`, profile, biến môi trường, Java system property và command line.
2. Chuyển tên property sang biến môi trường theo quy tắc **relaxed binding**; nhận ra trường hợp dấu gạch ngang hoặc list gây nhầm lẫn.
3. Cấu hình Spring Modulith/Actuator/metrics/tracing cho nhiều môi trường với cùng một artifact.
4. Phân biệt override trực tiếp với placeholder trong YAML.
5. Xác nhận cấu hình được process đọc và có ảnh hưởng thực sự đến telemetry.
6. Chẩn đoán lỗi về precedence, profile, container, propagation và bảo mật.

> **Giả định:** các ví dụ sử dụng Java 17+, Spring Boot có hỗ trợ `application.yml`, Spring Modulith và Micrometer. Tùy phiên bản Spring Boot/Modulith, tên property hoặc cách bật integration có thể khác. Hãy đối chiếu metadata và tài liệu của đúng phiên bản đang chạy; đặt biến môi trường không tự cài đặt dependency hoặc tạo endpoint chưa được đăng ký.

## 1. Bài toán thực tế

Giả sử ứng dụng `shop-modulith` có ba application module:

- **orders** phát event `OrderCompleted`.
- **billing** xử lý event và tạo hóa đơn.
- **shipping** chuẩn bị giao hàng; một số event có thể được externalize sang broker.

Spring Modulith giúp tài liệu hóa ranh giới và kiểm tra quan hệ giữa các module. Tại runtime, Spring Boot Actuator, event metrics và distributed tracing giúp quan sát những lời gọi hoặc event thực sự xảy ra. Các môi trường vận hành cần giá trị khác nhau:

| Thuộc tính | Local | Staging / production |
|---|---|---|
| Tên ứng dụng | `shop-local` | `shop-staging` / `shop-prod` |
| Kafka bootstrap servers nếu dùng Kafka | `localhost:9092` | `kafka.internal:9092` |
| Sampling probability | `1.0` để quan sát bài thực hành | Ví dụ `0.10` để giảm dữ liệu trace |
| Actuator expose qua HTTP | `health,info,metrics,modulith` nếu endpoint khả dụng | Chỉ endpoint thực sự cần thiết, có bảo vệ |
| Nguồn dữ liệu quan sát | Test trace, module metrics và event flow | Trace, metrics, logs, broker/registry theo chính sách |

**Mục tiêu:** tạo một file JAR/container image rồi đưa cấu hình phù hợp vào môi trường lúc khởi động. Thay đổi sampling không làm đổi module graph; nó chỉ ảnh hưởng cách telemetry được lấy mẫu. Thay đổi địa chỉ Kafka có thể ảnh hưởng event externalization nhưng không thay thế việc kiểm chứng phát/nhận event.

## 2. Spring Boot ưu tiên các nguồn cấu hình thế nào?

Spring Boot tập hợp property từ nhiều **PropertySource**. Khi cùng một key được khai báo ở nhiều nguồn, nguồn có độ ưu tiên cao hơn quyết định giá trị hiệu lực.

Với các nguồn phổ biến, hãy ghi nhớ thứ tự **từ thấp đến cao**:

1. **Config Data**: các file `application.yml`, `application.properties`, file theo profile và các vị trí cấu hình được import. Bên trong nhóm này có quy tắc riêng theo file, vị trí và profile.
2. **Biến môi trường hệ điều hành** (OS environment variables).
3. **Java system properties**, ví dụ `-Dmanagement.tracing.sampling.probability=0.5`.
4. **SPRING_APPLICATION_JSON**, cung cấp một khối property dạng JSON.
5. **Command-line arguments**, ví dụ `--management.tracing.sampling.probability=0.9`, khi được phép sử dụng.

Đây là tóm tắt của những nguồn thường gặp trong triển khai; Spring Boot còn có default properties, `@PropertySource`, JNDI/servlet sources, random values, nguồn riêng của test và DevTools. Các nguồn test có thể đứng cao hơn thứ tự runtime ở trên. Vì vậy, khi debug môi trường thật phải kiểm tra **nguồn nào đang thắng** thay vì chỉ nhìn `application.yml`.

Ví dụ mặc định:

~~~yaml
# application.yml
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 0.10
~~~

Chạy trên Linux/macOS:

~~~bash
SPRING_APPLICATION_NAME=shop-staging \
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.25 \
java -jar shop-modulith.jar
~~~

Kết quả sau binding:

| Property | File cấu hình | Biến môi trường | Giá trị thực |
|---|---|---|---|
| `spring.application.name` | `shop-modulith` | `shop-staging` | `shop-staging` |
| `management.tracing.sampling.probability` | `0.10` | `0.25` | `0.25` |

Nếu thêm `-Dmanagement.tracing.sampling.probability=0.5` vào JVM thì giá trị thường là `0.5`. Nếu còn có `--management.tracing.sampling.probability=0.9` thì kết quả là `0.9`.

**Sampling probability chỉ quyết định chiến lược lấy mẫu** khi ứng dụng đã có tracing instrumentation. Nó không tự bật Micrometer Tracing, không cấu hình exporter và không khắc phục lỗi mất trace context qua listener bất đồng bộ.

## 3. Đặt tên biến môi trường theo relaxed binding

Spring Boot khuyến khích property canonical dạng chữ thường, các từ trong một cấp phân tách bằng dấu gạch ngang (**kebab-case**), ví dụ `management.tracing.sampling.probability`.

Khi chuyển từ tên canonical sang tên biến môi trường cho **Spring Boot Binder**:

1. Thay các dấu chấm `.` bằng dấu gạch dưới `_`.
2. Xóa dấu gạch ngang `-` trong từng tên property, **không thay mỗi dấu gạch ngang thành dấu gạch dưới**.
3. Viết hoa toàn bộ.

Ví dụ minh họa quy tắc chính thức:

~~~text
spring.main.log-startup-info
  -> SPRING_MAIN_LOGSTARTUPINFO
~~~

Bảng áp dụng vào Spring Modulith và quan sát runtime:

| Property của Spring Boot | Tên biến môi trường canonical | Công dụng |
|---|---|---|
| `spring.application.name` | `SPRING_APPLICATION_NAME` | Tên service |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` | Chọn profile |
| `spring.kafka.bootstrap-servers` | `SPRING_KAFKA_BOOTSTRAPSERVERS` | Địa chỉ Kafka nếu có dùng broker |
| `spring.kafka.template.observation-enabled` | `SPRING_KAFKA_TEMPLATE_OBSERVATIONENABLED` | Bật observation trên KafkaTemplate khi có hỗ trợ |
| `spring.kafka.listener.observation-enabled` | `SPRING_KAFKA_LISTENER_OBSERVATIONENABLED` | Bật observation trên Kafka listener container khi có hỗ trợ |
| `management.tracing.sampling.probability` | `MANAGEMENT_TRACING_SAMPLING_PROBABILITY` | Tỷ lệ lấy mẫu |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` | Các Actuator endpoint expose qua HTTP |
| `management.metrics.tags.application` | `MANAGEMENT_METRICS_TAGS_APPLICATION` | Common metrics tag |
| `management.otlp.tracing.endpoint` | `MANAGEMENT_OTLP_TRACING_ENDPOINT` | Tracing exporter endpoint ở Boot phiên bản hỗ trợ |

Lỗi dễ gặp là đặt `SPRING_KAFKA_BOOTSTRAP_SERVERS` bằng cách chuyển dấu gạch ngang sang dấu gạch dưới. Tên được xây dựng **trực tiếp theo quy tắc Binder** cho `spring.kafka.bootstrap-servers` là `SPRING_KAFKA_BOOTSTRAPSERVERS`; tương tự `observation-enabled` thành `OBSERVATIONENABLED`. Nếu môi trường có framework hoặc launcher bổ sung alias, hãy kiểm chứng giá trị đã bind thật sự, không suy diễn rằng mọi cách viết có dấu gạch dưới đều tương đương.

Đối với list, property ví dụ `app.targets[0].name` có thể được biểu diễn như `APP_TARGETS_0_NAME` khi bind bằng `@ConfigurationProperties`. List từ một nguồn ưu tiên cao thường thay thế list cũ, chứ không gộp các phần tử từ nhiều nguồn. Map key có ký tự đặc biệt, tên logger, hay key cần giữ nguyên dấu chấm có các quy tắc riêng.

**Lưu ý API:** `@ConfigurationProperties` sử dụng Binder của Spring Boot. Đọc trực tiếp `System.getenv()` hoặc `Environment.getProperty()` không đồng nghĩa tất cả phép biến đổi relaxed binding của Binder đều được áp dụng giống hệt. Với các nhóm cấu hình nghiệp vụ, dùng `@ConfigurationProperties` và tên canonical là cách dễ duy trì.

## 4. Cấu hình mặc định và override cho observability

Một file `application.yml` có thể đặt các giá trị mặc định có thể chạy tại local:

~~~yaml
spring:
  application:
    name: shop-modulith
  kafka:
    bootstrap-servers: localhost:9092

management:
  endpoints:
    web:
      exposure:
        include: health,info
  tracing:
    sampling:
      probability: 0.10
  metrics:
    tags:
      application: ${spring.application.name}
~~~

Trong ví dụ:

- Kafka chỉ cần thiết nếu ứng dụng dùng Kafka để gửi/nhận event; nếu không có tích hợp Kafka thì bỏ nhánh cấu hình này.
- `health,info` chỉ expose những endpoint thường cần nhất. Muốn xem `metrics` hoặc `modulith` cần được cấu hình expose, có dependency tương ứng và vượt qua kiểm soát truy cập.
- Common tag `application` lấy tên ứng dụng từ Spring Environment. Khi override `SPRING_APPLICATION_NAME`, tag tham chiếu đó cũng có thể mang tên mới.
- Nếu không có Micrometer Tracing bridge, tracer hoặc exporter phù hợp thì thay đổi sampling không đồng nghĩa sẽ nhìn thấy distributed trace trong backend.

### 4.1. Linux/macOS

~~~bash
SPRING_APPLICATION_NAME=shop-dev \
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=1.0 \
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,info,metrics,modulith \
java -jar shop-modulith.jar
~~~

Cú pháp trên truyền các biến cho **một process**. Có thể `export` để sử dụng trong phiên shell:

~~~bash
export SPRING_APPLICATION_NAME=shop-dev
export MANAGEMENT_TRACING_SAMPLING_PROBABILITY=1.0
java -jar shop-modulith.jar
~~~

### 4.2. Windows PowerShell

~~~powershell
$env:SPRING_APPLICATION_NAME = "shop-dev"
$env:MANAGEMENT_TRACING_SAMPLING_PROBABILITY = "1.0"
$env:MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE = "health,info,metrics,modulith"

java -jar .\shop-modulith.jar

Remove-Item Env:\SPRING_APPLICATION_NAME
Remove-Item Env:\MANAGEMENT_TRACING_SAMPLING_PROBABILITY
Remove-Item Env:\MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE
~~~

Các biến đặt trong PowerShell là của phiên PowerShell đó và các process con. Một ứng dụng khởi chạy từ IDE, Windows Service hoặc terminal khác không đương nhiên nhận các biến vừa đặt. Hãy kiểm tra đúng môi trường của **process đang chạy ứng dụng**.

### 4.3. Docker Compose

~~~yaml
services:
  shop:
    image: example/shop-modulith:1.0.0
    environment:
      SPRING_APPLICATION_NAME: shop-staging
      SPRING_PROFILES_ACTIVE: staging
      SPRING_KAFKA_BOOTSTRAPSERVERS: kafka:9092
      MANAGEMENT_TRACING_SAMPLING_PROBABILITY: "0.25"
      MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE: "health,info"
~~~

Phần `environment:` truyền biến vào container. File `.env` cạnh `compose.yaml` thường phục vụ việc thay giá trị biến trong cấu hình Compose; nó không bảo đảm tất cả key trong file `.env` tự xuất hiện bên trong container. Muốn chuyển vào container phải dùng `environment`, `env_file` hoặc cơ chế triển khai tương ứng.

Trong Docker network, `localhost` chỉ chính container. Địa chỉ `kafka:9092` là ví dụ khi broker có tên service DNS là `kafka` và có thể truy cập từ container của ứng dụng.

### 4.4. Kubernetes

Ví dụ phần `env` trong pod template của Deployment:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: shop-modulith
          image: example/shop-modulith:1.0.0
          env:
            - name: SPRING_APPLICATION_NAME
              value: shop-prod
            - name: MANAGEMENT_TRACING_SAMPLING_PROBABILITY
              value: "0.10"
            - name: MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE
              value: health,info
~~~

Đây chỉ là fragment, chưa phải manifest Deployment đầy đủ. Cập nhật cấu hình env trong Kubernetes cần tạo Pod mới hoặc rollout theo phương thức triển khai để JVM mới nhận giá trị; thay đổi ConfigMap/Secret không tự cập nhật các biến môi trường đã nằm trong process đang chạy.

## 5. Kết hợp profile với biến môi trường

Spring Boot hỗ trợ file cấu hình theo profile:

~~~yaml
# application.yml
spring:
  application:
    name: shop-modulith
management:
  tracing:
    sampling:
      probability: 0.10
~~~

~~~yaml
# application-staging.yml
management:
  tracing:
    sampling:
      probability: 0.20
~~~

Khi đặt `SPRING_PROFILES_ACTIVE=staging`, giá trị trong `application-staging.yml` được áp dụng theo quy tắc của Config Data. Nếu đặt thêm `MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.35`, biến môi trường thắng giá trị `0.20` từ file theo profile.

| Hoàn cảnh | Giá trị hiệu lực |
|---|---:|
| Chỉ `application.yml` | `0.10` |
| Bật `staging`, không có override | `0.20` |
| Bật `staging`, OS env `0.35` | `0.35` |
| Như trên và system property `-D...=0.50` | `0.50` |
| Như trên và thêm CLI `--management.tracing.sampling.probability=0.80` | `0.80` |

Từ bảng này rút ra một điều quan trọng: **profile chọn nhóm cấu hình cần nạp**, còn biến môi trường có thể ghi đè property của cả nhóm đó. Không thể kết luận “đang chạy profile production” nghĩa là sampling chắc chắn bằng một con số cố định nếu có nguồn override khác.

## 6. Override trực tiếp và placeholder trong YAML

Có hai cách chuyển một giá trị ngoài ứng dụng vào Spring Environment.

### 6.1. Override trực tiếp

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

~~~bash
export MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.65
java -jar shop-modulith.jar
~~~

Binder ánh xạ biến `MANAGEMENT_TRACING_SAMPLING_PROBABILITY` sang `management.tracing.sampling.probability`, khiến giá trị hiệu lực là `0.65`. Không cần khai báo placeholder nào trong file YAML.

### 6.2. Dùng placeholder với giá trị mặc định

~~~yaml
management:
  tracing:
    sampling:
      probability: ${TRACE_SAMPLE_RATE:0.10}
~~~

~~~bash
export TRACE_SAMPLE_RATE=0.65
java -jar shop-modulith.jar
~~~

Ở đây `TRACE_SAMPLE_RATE` được sử dụng để giải quyết placeholder. Nó không phải tên biến ánh xạ trực tiếp cho `management.tracing.sampling.probability`. Phần sau dấu `:` là giá trị mặc định khi biến tham chiếu chưa được cung cấp.

Nếu cùng lúc có:

~~~bash
export TRACE_SAMPLE_RATE=0.65
export MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.80
~~~

thì **`0.80`** ở property trực tiếp thường thắng giá trị thuộc `application.yml` được lấy qua placeholder. Đây là một nguyên nhân phổ biến của việc đã đặt một biến nhưng runtime lại hiển thị giá trị khác.

**File .env không được Spring Boot nạp tự động chỉ vì nó nằm cùng thư mục với JAR.** Hãy đảm bảo launcher/container/CI thực sự chuyển các giá trị cần thiết vào process hoặc sử dụng một cơ chế Config Data được hỗ trợ.

## 7. Tạo nhóm cấu hình riêng cho application module

Spring Boot Binder cũng có thể bind các property do dự án tự định nghĩa. Ví dụ nhóm cấu hình chỉ phục vụ khả năng quan sát:

~~~yaml
shop:
  observability:
    environment-label: local
    event-audit-enabled: false
~~~

~~~java
package com.example.shop.configuration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shop.observability")
public record ShopObservabilityProperties(
    String environmentLabel,
    boolean eventAuditEnabled
) {}
~~~

Đăng ký lớp cấu hình (nếu ứng dụng chưa dùng `@ConfigurationPropertiesScan`):

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ShopObservabilityProperties.class)
class ShopObservabilityConfiguration {}
~~~

Biến môi trường tương ứng:

~~~bash
SHOP_OBSERVABILITY_ENVIRONMENTLABEL=staging \
SHOP_OBSERVABILITY_EVENTAUDITENABLED=true \
java -jar shop-modulith.jar
~~~

**Giải thích:** vì `environment-label` chứa dấu gạch ngang nên khi chuyển sang biến môi trường phải xóa dấu ấy, tạo thành `ENVIRONMENTLABEL`. Cùng quy tắc áp dụng cho `event-audit-enabled` → `EVENTAUDITENABLED`.

Lớp record chỉ nhận dữ liệu đã bind; muốn `eventAuditEnabled` điều khiển logging/observation thì code của một bean khác phải **thực sự dùng giá trị này**. Đối với property bắt buộc, có thể sử dụng Bean Validation trên lớp cấu hình để fail fast nếu giá trị không hợp lệ.

Với event metrics, chỉ dùng tag có cardinality thấp (module, event type, outcome). EventId, orderId và traceId nên dùng trong structured logs/span attributes phù hợp; tránh đưa chúng làm metric labels vì có thể sinh số lượng chuỗi thời gian rất lớn.

## 8. Những gì biến môi trường có thể và không thể thay đổi

Spring Modulith giúp nhìn ứng dụng qua hai lớp bằng chứng:

- **Module graph và tài liệu kiến trúc:** phản ánh ranh giới application module, API công khai và phụ thuộc tĩnh. Có thể sinh bằng **Documenter**.
- **Actuator, metrics, logs và distributed tracing:** phản ánh những thao tác thực sự được ứng dụng ghi nhận ở runtime. Chúng phụ thuộc vào instrumentation, sampling, quyền truy cập và đường gửi telemetry.

| Override | Có thể tác động | Không bảo đảm |
|---|---|---|
| `SPRING_APPLICATION_NAME` | Tên dịch vụ và các tag/log tham chiếu tên đó | Thay đổi module graph hoặc API module |
| `MANAGEMENT_TRACING_SAMPLING_PROBABILITY` | Tỷ lệ lấy mẫu trace | Tracing được cài, span được export, trace qua thread |
| `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` | Endpoint Actuator nào được expose qua HTTP | Endpoint Modulith tồn tại hoặc người gọi được cấp quyền |
| `SPRING_KAFKA_BOOTSTRAPSERVERS` | Broker mà Kafka client cố kết nối | Gửi event thành công, giữ thứ tự, exactly-once |
| `SPRING_KAFKA_TEMPLATE_OBSERVATIONENABLED` | KafkaTemplate observation khi phiên bản hỗ trợ | Consumer luôn được propagate context |
| `SPRING_KAFKA_LISTENER_OBSERVATIONENABLED` | Listener observation khi phiên bản hỗ trợ | Business consumer idempotent khi gặp event trùng |

### 8.1. Event metrics và externalization

Ví dụ Spring Modulith có thể cung cấp metric `module.events.published` khi phần observability tương ứng được bật. Metric này nói về **application event được phát trong process**, không phải xác nhận rằng message đã ra Kafka hoặc được hệ thống khác xử lý thành công.

Muốn phân tích lỗi sau khi đổi Kafka bootstrap servers, cần kết hợp producer errors, trạng thái Event Publication Registry (nếu dùng), broker metadata, consumer acknowledgements và log có `eventId`. Một giá trị env chính xác không chứng minh luồng externalization thành công.

### 8.2. Sampling khác context propagation

Giả sử HTTP request phát event `OrderCompleted`; listener được xử lý bất đồng bộ trong thread khác. Dù sampling là `1.0`, trace vẫn có thể bị tách nếu executor không chuyển current observation/span context qua ranh giới thread.

Cần cấu hình executor thực sự được `@Async` hoặc `@ApplicationModuleListener` sử dụng, ví dụ với **ContextPropagatingTaskDecorator** của Spring Framework hoặc cơ chế propagation được phiên bản Spring Boot hỗ trợ. Qua Kafka, producer/consumer phải inject và extract trace headers bằng instrumentation tương thích.

Không dùng một biến sampling để kết luận đã giải quyết vấn đề propagation. Khi event được phát lại sau restart, trace context gốc thường không còn active; sử dụng `eventId`/`correlationId` ổn định để truy dấu các lần xử lý của cùng một sự kiện.

## 9. Kiểm chứng cấu hình hiệu lực

Hãy kiểm tra theo bốn lớp:

1. **Process environment:** biến có mặt trong process đang chạy hay chỉ nằm ở shell/CI/Compose bên ngoài?
2. **Property binding:** Spring Boot nhận đúng key, đúng value, đúng kiểu dữ liệu và không bị nguồn khác override?
3. **Tính năng tương ứng:** dependency và bean cần thiết có tồn tại; endpoint hoặc producer/tracer đã được kích hoạt?
4. **Hành vi runtime:** Actuator, metric, span, log, broker và publication registry có xác nhận sự thay đổi?

### 9.1. Xem Actuator trong môi trường phát triển

Ví dụ chạy thử:

~~~bash
SPRING_APPLICATION_NAME=shop-diagnostics \
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=1.0 \
MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,info,metrics,modulith \
java -jar shop-modulith.jar
~~~

Nếu dependency và quyền truy cập đã được thiết lập đúng:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/modulith
~~~

`/actuator/modulith` chỉ tồn tại khi Spring Modulith Actuator support được nạp; expose trong danh sách không tạo endpoint. HTTP 401/403 có thể là Spring Security hoạt động đúng, không phải thất bại của relaxed binding. Nếu HTTP 404, kiểm tra endpoint registration, exposure, management base-path và classpath.

`/actuator/env` và `/actuator/configprops` có thể giúp chẩn đoán property origin/binding trong môi trường quản trị được bảo vệ. Tuy nhiên, các endpoint này có thể tiết lộ thông tin nhạy cảm; không bật công khai hoặc tắt cơ chế che giá trị chỉ để debug. Cũng không nên in toàn bộ environment ra log khi chạy trên production.

### 9.2. Ma trận xác minh tối thiểu

| Mã | Thao tác | Kết quả kỳ vọng |
|---|---|---|
| C1 | Không đặt override | Lấy giá trị từ Config Data phù hợp |
| C2 | Đặt `SPRING_APPLICATION_NAME=shop-test` | Service name/property được bind thành `shop-test` |
| C3 | Đặt sampling `0.75` qua env | Binding nhận `0.75`; sampling hoạt động nếu tracer đã có |
| C4 | Đặt `MANAGEMENT_TRACING_SAMPLE_PROBABILITY` (sai tên) | Không override đúng property, test phát hiện mismatch |
| C5 | Đặt env `0.25` và system property `0.5` | System property thắng theo precedence runtime thông thường |
| C6 | Expose thêm `metrics` trong môi trường test | `/actuator/metrics` khả dụng nếu Actuator có và security cho phép |
| C7 | Thay env trong deployment khi process đang chạy | Process cũ chưa tự nhận; process/Pod mới nhận sau restart/rollout |
| C8 | Đổi Kafka bootstrap servers rồi externalize event | Xác minh broker thật, trạng thái gửi, publication registry; không chỉ xem property |
| C9 | Tăng sampling từ `0.1` lên `1.0` | Trace hiển thị nhiều hơn khi instrumentation hoạt động; không khẳng định tỷ lệ tuyệt đối từ mẫu nhỏ |
| C10 | Phát event qua listener bất đồng bộ | Kiểm tra propagation bằng span/log thực tế, độc lập với sampling |

Một test dạng sau chỉ chứng minh binding property khi chạy trong môi trường test:

~~~java
@SpringBootTest(properties = {
    "management.tracing.sampling.probability=0.75"
})
class ConfigurationTests {
    // Đặt assertion trên bean cấu hình/hành vi phù hợp.
}
~~~

Nó **không chứng minh** quy tắc ánh xạ từ OS environment, vì `@SpringBootTest(properties = ...)` đưa vào một test property source riêng. Để kiểm chứng end-to-end, cần khởi chạy process/container với biến môi trường thật rồi đọc kết quả từ ứng dụng đó.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách giải quyết |
|---|---|---|
| Biến được đặt nhưng giá trị không đổi | Tên sai hoặc biến nằm ở terminal khác | Kiểm tra process env và quy tắc Binder |
| Profile đúng nhưng giá trị sai | Env/system/CLI cao hơn Config Data | Xem lại toàn bộ PropertySource liên quan |
| File `.env` không tác dụng | Chưa được nạp vào process | Dùng `environment`/`env_file` trong Compose hoặc launcher phù hợp |
| Cấu hình sửa trên Kubernetes nhưng app vẫn cũ | Pod chưa được thay | Rollout và xác minh Pod mới |
| Property kiểu boolean/số gây lỗi startup | Chuỗi không bind được hoặc validation không đạt | Kiểm tra kiểu và value; dùng fail-fast validation |
| Actuator `modulith` trả 404 | Thiếu endpoint support hoặc sai management path | Kiểm tra classpath, endpoint registration, exposure |
| Actuator trả 401/403 | Chưa xác thực | Kiểm tra security policy và network access |
| Sampling tăng nhưng trace vẫn trống | Chưa có bridge/exporter, collector lỗi hoặc sampling không phải nguyên nhân | Kiểm tra tracer, exporter endpoint, instrumentation |
| Trace bị đứt ở listener | Thiếu context propagation qua executor | Kiểm tra executor thực tế và span context |
| App event metrics tăng nhưng broker không thấy message | Event publication trong app khác với broker acknowledgement | Kiểm tra externalizer, Kafka errors và registry |
| Đổi cấu hình logger package bằng env không đúng | Tên package/log level có quy tắc đặc biệt | Dùng cấu hình file, system property hoặc `SPRING_APPLICATION_JSON` khi cần |

### 10.1. Bí mật và an toàn vận hành

Biến môi trường **không phải kho bí mật mặc định**: người có quyền đối với process/container hoặc hệ thống log/manifest có thể xem được thông tin nhạy cảm tùy cơ chế triển khai. Với password, access token, private key và credential của broker, cần dùng secret management phù hợp, hạn chế quyền đọc và tránh in giá trị ra log hoặc Actuator.

Không đưa `eventId`, `traceId` hoặc dữ liệu khách hàng vào metric tag có cardinality cao. Với `/actuator/env`, `/actuator/configprops` và endpoints quan sát nội bộ, giới hạn exposure, yêu cầu xác thực và giữ cơ chế che giá trị nhạy cảm.

## 11. Bài tập thực hành

Chuẩn bị một ứng dụng Spring Modulith có tối thiểu hai application module `orders` và `billing`, có event từ orders sang billing, Actuator và tracing instrumentation đã hoạt động.

1. Tạo một `application.yml` dùng chung, với service name `shop-modulith`, sampling `0.10` và Actuator chỉ expose `health,info`.
2. Chạy cùng JAR ở local bằng `SPRING_APPLICATION_NAME=shop-local`, `MANAGEMENT_TRACING_SAMPLING_PROBABILITY=1.0`, expose thêm `metrics,modulith` trong mạng test có bảo vệ.
3. Chạy bản staging bằng **cùng artifact** và các biến `SPRING_APPLICATION_NAME=shop-staging`, sampling `0.20` cùng địa chỉ broker staging nếu có Kafka.
4. Kiểm tra module graph để biết orders/billing được nhận diện đúng; kiểm tra Actuator và event metrics trong từng môi trường.
5. Gửi một request làm phát event, ghi nhận trace và log; so sánh điều kiện trước/sau khi bật context propagation qua executor.
6. Cố tình dùng tên biến sai rồi kiểm tra giá trị thực; sửa tên theo quy tắc relaxed binding.
7. Nếu externalize event, cố tình làm broker không thể kết nối, ghi nhận lỗi và trạng thái publication; khôi phục broker rồi xác minh gửi lại không tạo hiệu ứng nghiệp vụ trùng.

**Bằng chứng nghiệm thu:** bảng property ↔ biến môi trường, ảnh/log cấu hình đã loại bỏ bí mật, kết quả Actuator, sơ đồ module, một trace bình thường và một tình huống lỗi/retry. Chỉ kết luận thành công khi có **bằng chứng runtime**, không chỉ khi YAML hoặc manifest có giá trị mong muốn.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn property và thứ tự ưu tiên.
- [Spring Boot — Binding From Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables): quy tắc chuyển tên cho Binder.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): expose và bảo vệ endpoint.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): tracing, metrics, context propagation.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): endpoint Modulith và quan sát module.
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): tài liệu kiến trúc từ application module.
