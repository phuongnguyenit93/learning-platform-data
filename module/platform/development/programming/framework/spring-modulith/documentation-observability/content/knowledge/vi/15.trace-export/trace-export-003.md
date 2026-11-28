# Cấu hình exporter Zipkin

## Mục tiêu học tập

Trong chương **Export traces** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, bài học này hướng dẫn đưa các trace do ứng dụng Spring Boot tạo ra tới **Zipkin** để tìm kiếm và phân tích. Trọng tâm là cấu hình exporter, lựa chọn dependency theo phiên bản Spring Boot, kiểm tra kết nối và hiểu giới hạn của dữ liệu được xuất.

Sau bài học, bạn có thể:

1. Phân biệt **tracer**, **bridge**, **reporter/exporter**, **collector/backend** và giao diện Zipkin.
2. Cấu hình Spring Boot gửi spans theo định dạng Zipkin V2 tới endpoint \`/api/v2/spans\`.
3. Chọn dependency và property phù hợp giữa Spring Boot 4.2 và các dòng Spring Boot 3.x cũ hơn.
4. Khởi chạy Zipkin cục bộ bằng Docker và kết nối ứng dụng tới đúng địa chỉ trong cùng hoặc khác container.
5. Điều chỉnh sampling, timeout, endpoint và tên service theo môi trường.
6. Kiểm tra trace đã tới Zipkin, phân biệt lỗi instrumentation, sampling, exporter, mạng và truy vấn UI.
7. Kết hợp Spring Modulith module spans với Zipkin để quan sát lời gọi qua ranh giới application module.
8. Thiết kế triển khai an toàn, tránh đưa dữ liệu nhạy cảm vào span và tránh biến môi trường phát triển thành cấu hình production.

**Bối cảnh học phần:** Spring Modulith giúp sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Module graph và Actuator cho biết cấu trúc; event metrics cung cấp số liệu tổng hợp; Micrometer Tracing và Zipkin giúp xem chi tiết một lần thực thi qua các spans; context propagation nối các phần của trace qua ranh giới thread hoặc dịch vụ.

> **Lưu ý phiên bản:** Ví dụ chính dùng **Spring Boot 4.2.0**, theo tài liệu chính thức hiện hành. Spring Boot 3.5.x dùng cách khai báo dependency và namespace cấu hình Zipkin cũ hơn. Không ghép dependency của một dòng với property của dòng khác. Hãy kiểm tra đúng reference guide của phiên bản mà dự án đang quản lý bằng BOM.

---

## 1. Exporter Zipkin giải quyết vấn đề gì?

Khi một request tạo đơn đi qua nhiều thành phần, ứng dụng có thể tạo các spans như:

- HTTP server span tiếp nhận request;
- module entry span khi \`orders\` gọi API của \`inventory\`;
- span cho lời gọi HTTP tới payment provider;
- module entry span khi listener thuộc \`payments\` nhận application event;
- database hoặc messaging spans do thư viện tương ứng instrument.

Các spans này có thể được tạo trong JVM, nhưng để nhóm vận hành tìm kiếm và xem timeline ở một giao diện tập trung, chúng cần được **xuất tới một trace backend**.

**Zipkin** là hệ thống thu thập và hiển thị distributed traces. Nó nhận spans theo định dạng Zipkin, lưu trữ chúng theo cấu hình backend và cung cấp API/UI để truy vấn.

Exporter/reporter là thành phần gửi spans từ ứng dụng tới Zipkin. Với Spring Boot, phần này được auto-configure khi các dependency tracing phù hợp có mặt và endpoint được cấu hình.

~~~mermaid
flowchart LR
    A["Spring Boot application"] --> B["Micrometer Observation"]
    B --> C["Micrometer Tracing"]
    C --> D["Brave tracer"]
    D --> E["Zipkin reporter / exporter"]
    E -->|"POST Zipkin V2 spans"| F["Zipkin server :9411"]
    F --> G["Zipkin UI / query API"]
~~~

Sơ đồ mô tả phương án Brave với Zipkin. Ứng dụng cũng có thể dùng OpenTelemetry làm tracer implementation, nhưng lựa chọn dependency và exporter cần theo phiên bản Spring Boot. Ở Spring Boot 4.2, phương án Zipkin được tài liệu hóa trực tiếp là **OpenZipkin Brave với Zipkin**.

## 2. Phân biệt các thành phần trong pipeline

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Micrometer Observation** | Mô hình hóa một hoạt động được quan sát, giữ context và phát lifecycle callbacks. | HTTP request observation, custom operation, module observation. |
| **Micrometer Tracing API** | Cung cấp API thống nhất để tạo/quản lý span và truyền trace context. | \`Tracer\`, \`Span\`, \`Propagator\`. |
| **Bridge** | Kết nối API Micrometer với tracer implementation. | \`micrometer-tracing-bridge-brave\`. |
| **Tracer implementation** | Quản lý span, context và sampling. | OpenZipkin Brave. |
| **Reporter/exporter** | Chuyển spans hoàn tất thành payload và gửi tới backend. | \`zipkin-reporter-brave\` hoặc starter tích hợp tương ứng. |
| **Zipkin server** | Nhận, lưu và cung cấp API truy vấn traces. | Zipkin HTTP collector trên port 9411. |
| **Zipkin UI** | Tìm trace và hiển thị span tree/timeline. | Trang web tại \`http://localhost:9411\`. |

Các thành phần này không thể thay thế lẫn nhau:

- Có tracer mà không có exporter thì spans có thể không được gửi ra ngoài.
- Có exporter nhưng Zipkin server không chạy hoặc không truy cập được thì dữ liệu không đến nơi nhận.
- Zipkin UI mở được không chứng minh ứng dụng đã gửi spans.
- Có HTTP spans không đồng nghĩa đã có module spans; cần bật instrumentation của Spring Modulith nếu muốn quan sát ranh giới module.

## 3. Chọn đúng cách cấu hình theo Spring Boot version

Spring Boot đã thay đổi cách đóng gói dependency và namespace property khi nâng major version. Đây là điểm dễ gây lỗi nhất khi sao chép ví dụ từ bài viết cũ.

| Phiên bản | Dependency Brave + Zipkin | Property endpoint |
| --- | --- | --- |
| **Spring Boot 4.2.x** | \`org.springframework.boot:spring-boot-starter-zipkin\` | \`management.tracing.export.zipkin.*\` |
| **Spring Boot 3.5.x** | \`micrometer-tracing-bridge-brave\` + \`zipkin-reporter-brave\`, cùng Actuator | \`management.zipkin.tracing.*\` |
| **Spring Boot 3.x cũ hơn** | Kiểm tra reference guide của đúng minor version; các bản phổ biến dùng bridge/reporter riêng | Thường là \`management.zipkin.tracing.*\`, nhưng phải xác minh theo release |

Trong Spring Boot 4.2, tài liệu hiện hành hướng dẫn dùng starter Zipkin cho Brave. Hỗ trợ OpenTelemetry xuất trực tiếp theo định dạng Zipkin đã bị loại bỏ khỏi auto-configuration ở dòng 4.2; nếu ứng dụng chọn OpenTelemetry, hướng tích hợp được khuyến nghị là OTLP tới OpenTelemetry Collector/backend phù hợp.

**Quy tắc:** Chọn một phương án theo BOM Spring Boot đang dùng. Không khai báo đồng thời nhiều bridge tracer cạnh tranh hoặc trộn property của Boot 3.5 với dependency starter của Boot 4.2.

## 4. Cấu hình Zipkin với Spring Boot 4.2

### 4.1. Khai báo dependency

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-zipkin'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-zipkin</artifactId>
</dependency>
~~~

Các ví dụ giả định dự án dùng Spring Boot plugin/BOM để quản lý version. Không ghi version riêng cho starter nếu dự án đã quản lý tập trung bằng Spring Boot dependency management.

Starter này cung cấp cấu hình tracing Brave với Zipkin theo Spring Boot. Nếu ứng dụng còn cần các Actuator endpoint khác, khai báo starter Actuator phù hợp với cách tổ chức dependency của dự án.

### 4.2. Cấu hình endpoint và sampling

Ví dụ \`application.yml\` cho môi trường local:

~~~yaml
spring:
  application:
    name: shop-service

management:
  tracing:
    sampling:
      probability: 1.0
    export:
      zipkin:
        enabled: true
        endpoint: http://localhost:9411/api/v2/spans
        encoding: json
        connect-timeout: 1s
        read-timeout: 10s
~~~

Ý nghĩa:

| Property | Ý nghĩa |
| --- | --- |
| \`spring.application.name\` | Tên ứng dụng để nhận diện service trong dữ liệu tracing. |
| \`management.tracing.sampling.probability\` | Xác suất trace được chọn để thu thập. |
| \`management.tracing.export.zipkin.enabled\` | Bật/tắt auto-configuration xuất trace tới Zipkin. |
| \`management.tracing.export.zipkin.endpoint\` | URL API nhận spans của Zipkin. |
| \`management.tracing.export.zipkin.encoding\` | Định dạng payload gửi tới API. |
| \`management.tracing.export.zipkin.connect-timeout\` | Thời gian chờ thiết lập kết nối. |
| \`management.tracing.export.zipkin.read-timeout\` | Thời gian chờ phản hồi từ Zipkin. |

Endpoint mặc định của Boot 4.2 là:

~~~text
http://localhost:9411/api/v2/spans
~~~

Đây là **API nhận spans**, không phải URL giao diện. Giao diện Zipkin mặc định ở:

~~~text
http://localhost:9411
~~~

### 4.3. Sampling trong môi trường local và production

Spring Boot mặc định chỉ sample khoảng **10% request** để tránh làm quá tải backend. Đặt:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

sẽ chọn 100% trace theo sampler ratio phù hợp. Cấu hình này hữu ích khi thử nghiệm local vì ta muốn thấy mọi request trong kịch bản kiểm chứng.

Production thường cần tỷ lệ thấp hơn, dựa trên traffic, chi phí lưu trữ, khả năng backend và yêu cầu điều tra. Không nên mặc định để 100% khi hệ thống có lưu lượng lớn.

Lưu ý: sampling quyết định trace nào được giữ; nó không làm cho code path chưa instrument tự sinh span. Nếu request được chọn nhưng không có module instrumentation, trace vẫn có thể chỉ chứa HTTP spans hoặc các spans từ thư viện khác.

## 5. Khởi chạy Zipkin cục bộ bằng Docker

OpenZipkin cung cấp image Docker để thử nghiệm nhanh.

~~~bash
docker run -d --name zipkin -p 9411:9411 openzipkin/zipkin
~~~

Kiểm tra container:

~~~bash
docker ps
docker logs zipkin
~~~

Sau khi server sẵn sàng, mở:

~~~text
http://localhost:9411
~~~

Zipkin Quickstart cũng mô tả cách chạy Zipkin bằng Java hoặc từ source. Docker thường là lựa chọn nhanh cho môi trường local.

### 5.1. Dùng Docker Compose

Nếu muốn giữ cấu hình local trong repository của môi trường phát triển, có thể tạo một service Zipkin:

~~~yaml
services:
  zipkin:
    image: openzipkin/zipkin
    container_name: zipkin
    ports:
      - "9411:9411"
~~~

Chạy:

~~~bash
docker compose up -d zipkin
~~~

Dừng:

~~~bash
docker compose down
~~~

Đây là cấu hình tối giản để học và thử nghiệm. Nó không cấu hình storage bền vững, xác thực, TLS, backup hoặc mở rộng production. Hãy chọn storage và vận hành Zipkin phù hợp khi dùng lâu dài.

### 5.2. Địa chỉ endpoint khi ứng dụng cũng chạy trong container

Đây là lỗi cấu hình phổ biến:

- Ứng dụng chạy trực tiếp trên máy host: \`localhost:9411\` thường truy cập được cổng đã publish của Docker.
- Ứng dụng chạy trong **container khác cùng Docker network**: \`localhost\` trỏ về chính container ứng dụng. Hãy dùng tên service/container, ví dụ \`http://zipkin:9411/api/v2/spans\`.
- Ứng dụng chạy ở máy khác: dùng hostname/IP có thể truy cập được từ máy ứng dụng, không dùng \`localhost\`.

Ví dụ biến môi trường cho ứng dụng trong cùng Compose network ở Spring Boot 4.2:

~~~yaml
environment:
  MANAGEMENT_TRACING_EXPORT_ZIPKIN_ENDPOINT: http://zipkin:9411/api/v2/spans
~~~

Biến môi trường ánh xạ tới property theo quy tắc relaxed binding của Spring Boot.

## 6. Cấu hình Spring Boot 3.5.x

Nếu dự án chưa nâng lên Boot 4.2, dependency và property theo tài liệu Boot 3.5.x khác với ví dụ chính ở trên.

### 6.1. Brave bridge và Zipkin reporter

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-tracing-bridge-brave'
    runtimeOnly 'io.zipkin.reporter2:zipkin-reporter-brave'
}
~~~

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-brave</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>io.zipkin.reporter2</groupId>
        <artifactId>zipkin-reporter-brave</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Spring Boot dependency management/BOM cần quản lý version tương thích cho các artifact này. Không lấy version từ một bài viết khác rồi ghép tùy ý.

### 6.2. Property namespace của Boot 3.5.x

Ví dụ:

~~~yaml
spring:
  application:
    name: shop-service

management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
      encoding: JSON
      connect-timeout: 1s
      read-timeout: 10s
      export:
        enabled: true
~~~

Boot 3.5.x dùng namespace:

~~~text
management.zipkin.tracing.*
~~~

Trong khi Boot 4.2 dùng:

~~~text
management.tracing.export.zipkin.*
~~~

Đây là hai cấu trúc cấu hình theo phiên bản. Khi nâng cấp, cần chuyển property theo reference guide và kiểm tra lại giá trị hiệu lực trong ứng dụng; nếu vẫn giữ namespace cũ trong Boot mới, exporter có thể không nhận endpoint như mong đợi.

### 6.3. Nếu dự án Boot 3.5 dùng OpenTelemetry

Boot 3.5 cũng tài liệu hóa phương án OpenTelemetry bridge với Zipkin exporter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
~~~

Đây là phương án của dòng Boot 3.5. OpenTelemetry Zipkin exporter đã bị deprecate và không còn là lựa chọn auto-configuration được Spring Boot 4.2 hỗ trợ. Với ứng dụng nâng lên Boot 4.2 và chọn OpenTelemetry, nên xuất OTLP tới collector thay vì tiếp tục dựa vào Zipkin exporter cũ.

## 7. Kết hợp exporter Zipkin với Spring Modulith

Zipkin chỉ là nơi nhận và hiển thị spans. Để thấy tương tác giữa các application module, ứng dụng cần có instrumentation tạo ra các module observations trước khi exporter gửi chúng đi.

Spring Modulith cung cấp observability support cho các lời gọi vào Spring components thuộc API của application module. Khi bật, các **module entry spans** có thể mang metadata như:

| Attribute | Ý nghĩa |
| --- | --- |
| \`module.identifier\` | Định danh kỹ thuật của application module. |
| \`module.name\` | Tên module. |
| \`module.invocation-type\` | Loại điểm vào, ví dụ \`bean\` hoặc \`event listener\`. |
| \`module.method\` | Method được thực thi tại điểm instrument. |

### 7.1. Bật Insight starter

Với Gradle và BOM Spring Modulith tương thích:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Kết hợp với dependency Zipkin của Spring Boot theo phiên bản dự án. Ví dụ Boot 4.2:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-zipkin'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Insight starter gom các thành phần hỗ trợ Actuator và observability của Spring Modulith. Nó **không thay thế Zipkin exporter**. Hai nhóm dependency có trách nhiệm khác nhau:

- Insight: tạo module-related observations/spans và cung cấp thông tin module qua Actuator.
- Zipkin starter/reporter: gửi spans đã được tạo tới Zipkin.

### 7.2. Ví dụ luồng module

Giả sử có ba module:

- \`orders\`: nhận request tạo đơn;
- \`inventory\`: giữ hàng qua API bean;
- \`payments\`: nhận application event để chuẩn bị thanh toán.

~~~mermaid
flowchart LR
    A["HTTP POST /orders"] --> O["orders"]
    O -->|"Bean API call"| I["inventory"]
    O -->|"Publish OrderPlaced"| E["Application event"]
    E -->|"Event listener"| P["payments"]
    O -.-> T["Trace"]
    I -.-> T
    P -.-> T
    T --> Z["Zipkin"]
~~~

Khi request đi qua các điểm được instrument, trace có thể chứa HTTP span, module entry span và các spans khác. Nếu listener chạy bất đồng bộ, cần cấu hình context propagation để trace được liên kết phù hợp qua executor hoặc messaging. Việc chỉ cài exporter không tự tạo liên kết giữa các span.

### 7.3. Module graph khác trace

| Module graph / Actuator | Zipkin trace |
| --- | --- |
| Cho biết các application modules và dependency được phát hiện từ cấu trúc ứng dụng. | Cho biết các hoạt động runtime đã được instrument, sample và export. |
| Có thể hiển thị module chưa được gọi trong request. | Chỉ hiển thị span được tạo và gửi thành công. |
| Hỗ trợ kiểm tra cấu trúc và coupling. | Hỗ trợ điều tra duration, lỗi và thứ tự tương tác của một lần thực thi. |
| Không cho biết thời gian của một lời gọi cụ thể. | Không chứng minh mọi dependency tĩnh hoặc nghiệp vụ đều đúng. |

## 8. Propagation: để trace đi qua lời gọi HTTP

Exporter gửi spans tới Zipkin, còn **propagation** giúp các dịch vụ liên quan tiếp tục cùng trace. Khi service A gọi service B, client phải inject trace context vào request headers và server B phải extract context đó.

Trong Spring Boot, hãy dùng builder được auto-configure:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class PaymentProviderClient {

    private final RestClient client;

    PaymentProviderClient(RestClient.Builder builder) {
        this.client = builder
            .baseUrl("http://payment-provider")
            .build();
    }

    String authorize(String paymentReference) {
        return client.post()
            .uri("/authorize")
            .body(paymentReference)
            .retrieve()
            .body(String.class);
    }
}
~~~

Dùng \`RestClient.Builder\` được Spring Boot quản lý để tracing instrumentation có thể gắn vào client. Tự tạo client ngoài auto-configuration có thể làm mất tự động tạo client observation hoặc trace propagation nếu không cấu hình instrumentation tương ứng.

Với \`WebClient\`, cũng nên dùng builder do Spring Boot cung cấp.

### 8.1. Trace context không phải transaction context

Trace propagation truyền metadata như trace ID, span ID và sampling state. Nó không truyền transaction database, không bảo đảm message được giao một lần và không thay thế idempotency.

Một trace có thể kết thúc bằng lỗi dù exporter hoạt động bình thường. Một request có thể được sample nhưng downstream span bị đứt nếu propagation không đúng. Khi điều tra, xem cả trace context, event publication, retry và trạng thái dữ liệu đã commit.

## 9. Sampling và chi phí export

### 9.1. Sampling quyết định trace nào được xuất

Spring Boot mặc định sample khoảng 10% request. Với:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

ứng dụng chỉ chọn một phần trace theo xác suất. Với:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

ứng dụng chọn toàn bộ trace theo sampler ratio. Số lượng thực tế trong cửa sổ ngắn có thể dao động quanh xác suất đã cấu hình.

Sampling thường được quyết định sớm trong vòng đời trace. Nếu trace không được chọn, spans con thường cũng không được gửi theo trace đó, tùy sampler/parent context.

### 9.2. Chọn sampling theo môi trường

| Môi trường | Gợi ý ban đầu | Lý do |
| --- | --- | --- |
| Local development | Có thể dùng 1.0 | Dễ nhìn đầy đủ trace của kịch bản đang thử. |
| CI/integration test | Có thể dùng 1.0 trong phạm vi test | Cần kiểm tra trace của một kịch bản xác định. |
| Staging | Tỷ lệ cao hơn production nếu lưu lượng vừa phải | Điều tra trước khi phát hành. |
| Production | Chọn theo lưu lượng, ngân sách và yêu cầu điều tra | Tránh làm quá tải exporter/backend. |

Đây là gợi ý định hướng, không phải tỷ lệ bắt buộc. Hãy đánh giá số spans mỗi request, số request/giây, kích thước attributes, retention và chi phí backend.

### 9.3. Exporter không phải nơi sửa sampling

Nếu muốn thấy nhiều trace hơn, hãy xem sampler và property sampling trước. Tăng timeout, đổi endpoint hoặc restart Zipkin không làm những trace đã bị sampler loại xuất hiện trở lại.

## 10. Kiểm chứng từ ứng dụng tới Zipkin UI

Sau khi cấu hình dependency và endpoint:

1. Khởi chạy Zipkin server và xác nhận UI truy cập được tại port 9411.
2. Khởi động ứng dụng Spring Boot.
3. Gửi request tới một endpoint được instrument, ví dụ \`GET /\` hoặc \`POST /orders\`.
4. Chờ exporter gửi batch spans.
5. Mở Zipkin UI tại \`http://localhost:9411\`.
6. Chọn service name tương ứng với \`spring.application.name\`, đặt khoảng thời gian đủ rộng và chạy truy vấn.
7. Mở một trace và kiểm tra span tree, duration, tags, error và quan hệ parent-child.
8. Nếu có Spring Modulith Insight, tìm các span mang \`module.identifier\`, \`module.name\` và \`module.invocation-type\`.

### 10.1. Kiểm tra API Zipkin

Zipkin V2 có endpoint nhận spans:

~~~text
POST /api/v2/spans
~~~

Exporter gửi payload theo định dạng mà Zipkin API hỗ trợ, thường là JSON trong cấu hình mặc định Spring Boot. Endpoint này là API nhận dữ liệu, không phải endpoint để mở danh sách trace trong browser.

Các API truy vấn như danh sách service, danh sách span name và traces được tài liệu hóa trong Zipkin V2 API. Để học cơ bản, dùng UI là cách dễ quan sát trace tree và timeline nhất.

### 10.2. Kiểm tra tên service

Đặt tên service rõ ràng:

~~~yaml
spring:
  application:
    name: shop-service
~~~

Nếu nhiều ứng dụng cùng gửi dữ liệu vào một Zipkin backend, tên service giúp lọc trace theo nguồn. Không nên đặt mọi ứng dụng thành cùng một tên chung vì sẽ khó phân biệt trace từ các service khác nhau.

Tên service là metadata của ứng dụng, không phải tên module. Một service \`shop-service\` có thể chứa nhiều application modules như \`orders\`, \`inventory\`, \`payments\`.

## 11. Cấu hình theo môi trường và container

### 11.1. Tách endpoint khỏi file cấu hình dùng chung

Không nên hard-code địa chỉ Zipkin local trong cấu hình production. Dùng biến môi trường:

~~~yaml
management:
  tracing:
    export:
      zipkin:
        endpoint: \${ZIPKIN_ENDPOINT:http://localhost:9411/api/v2/spans}
~~~

Khi deploy, đặt \`ZIPKIN_ENDPOINT\` theo network topology của môi trường. Trong Docker Compose, giá trị có thể là:

~~~text
http://zipkin:9411/api/v2/spans
~~~

Trong Kubernetes, thường dùng DNS service nội bộ hoặc collector/gateway được tổ chức cung cấp.

### 11.2. Timeout

Spring Boot hiện hành cung cấp connect timeout và read timeout cho Zipkin exporter. Giá trị mặc định trong property reference là khoảng 1 giây để kết nối và 10 giây để chờ phản hồi. Có thể điều chỉnh theo độ trễ mạng, nhưng không nên tăng timeout vô hạn để che lỗi backend.

Nếu exporter không gửi được, cần xem log và trạng thái pipeline; timeout dài có thể làm việc phát hiện sự cố chậm hơn.

### 11.3. Bảo vệ dữ liệu khi xuất trace

Span attributes và baggage có thể chứa dữ liệu ứng dụng. Trước khi gửi tới Zipkin, hãy review:

- Không đưa access token, session cookie, password hoặc API key vào tags.
- Tránh ghi email, số điện thoại, địa chỉ và thông tin thanh toán nếu không có lý do, chính sách và kiểm soát truy cập rõ ràng.
- Không đưa toàn bộ request/response body vào span.
- Không dùng \`orderId\`, \`customerId\`, \`traceId\` làm metric tags; high-cardinality attributes trong trace cũng cần giới hạn.
- Cấu hình TLS, network policy và xác thực ở lớp gateway/proxy/backend nếu môi trường yêu cầu.
- Quy định retention, quyền truy vấn và cách xóa dữ liệu theo chính sách tổ chức.

Zipkin Quickstart là môi trường học tập. Cấu hình local tối giản không thay thế mô hình bảo mật và storage cho production.

## 12. Kiểm thử tracing export

Trong kiểm thử, cần phân biệt hai mục tiêu:

- **Kiểm tra instrumentation:** ứng dụng có tạo observation/span với metadata mong đợi không?
- **Kiểm tra export:** spans có được gửi tới Zipkin endpoint không?

Một test có thể xác minh instrumentation qua observation handler hoặc tracer test support mà không cần Zipkin server thật. Một integration test export cần backend hoặc test server nhận payload.

### 12.1. Kiểm tra trong Spring Boot test

Ở các dòng Spring Boot hiện hành, tracing components thực sự gửi dữ liệu không nhất thiết được auto-configure trong \`@SpringBootTest\` theo mặc định. Spring Boot 4.2 có property kiểm thử:

~~~yaml
spring:
  test:
    tracing:
      export: true
~~~

Chỉ bật trong test cần xác minh export và kiểm tra đúng property theo version. Nếu chỉ test business logic, không cần kết nối Zipkin thật.

### 12.2. Kiểm tra export end-to-end

Một kịch bản kiểm thử tích hợp:

1. Khởi động Zipkin test instance hoặc một endpoint giả lập giao thức Zipkin V2.
2. Khởi động ứng dụng với sampling 1.0 và endpoint trỏ tới test instance.
3. Gọi một route đã instrument.
4. Chờ batch export hoàn tất theo cơ chế của exporter.
5. Xác nhận receiver nhận payload spans.
6. Kiểm tra trace ID, span name, service name và các attributes cần thiết.
7. Nếu kiểm tra Spring Modulith, gọi qua API module và xác minh module entry span được tạo.
8. Dừng test và đảm bảo exporter được đóng/flush theo lifecycle.

Không chỉ kiểm tra HTTP request trả 200. Response 200 của ứng dụng chỉ chứng minh request xử lý theo logic web; nó không chứng minh exporter gửi span thành công.

## 13. Troubleshooting: không thấy trace trong Zipkin

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Zipkin UI không mở được | Container chưa chạy, port 9411 chưa publish hoặc port bị chiếm. | \`docker ps\`, \`docker logs zipkin\`, kiểm tra port và URL. |
| Ứng dụng báo connection refused | Endpoint sai, Zipkin chưa sẵn sàng, app container dùng \`localhost\`. | Thử từ đúng network namespace; dùng service DNS như \`zipkin\` khi cùng Compose network. |
| HTTP 404/400 khi export | Sai path, API version hoặc payload/encoding. | Kiểm tra endpoint \`/api/v2/spans\`, property và log reporter. |
| Ứng dụng chạy nhưng không có trace | Thiếu tracing dependency, observation không được instrument hoặc sampling thấp. | Kiểm tra dependency tree, sampling và request có tạo observation không. |
| Chỉ thấy HTTP spans, không thấy module spans | Chưa bật Modulith observability hoặc lời gọi không đi qua API module được instrument. | Kiểm tra Insight/core runtime và điểm gọi Spring-managed bean/listener. |
| Chỉ thấy một phần request | Sampling dưới 100%, exporter/backend lọc hoặc lỗi pipeline. | Xác minh probability, log exporter và dữ liệu nhận ở Zipkin. |
| Trace bị chia thành nhiều trace ID | Context propagation không được inject/extract qua HTTP hoặc async boundary. | Dùng auto-configured client builder và kiểm tra propagation format. |
| Zipkin UI không tìm thấy service | Tên service khác, thời gian truy vấn không đúng hoặc spans chưa được gửi. | Kiểm tra \`spring.application.name\`, time range và exporter logs. |
| Chỉ mất trace trong test | Export auto-configuration bị tắt trong test context. | Kiểm tra \`spring.test.tracing.export\` ở version hỗ trợ hoặc dùng test receiver. |

### 13.1. Trình tự điều tra ngắn

~~~mermaid
flowchart TD
    A["Không thấy trace ở Zipkin"] --> B{"Zipkin UI mở được?"}
    B -->|"Không"| C["Kiểm tra container, port, server logs"]
    B -->|"Có"| D{"Ứng dụng truy cập đúng endpoint?"}
    D -->|"Không"| E["Kiểm tra URL, Docker DNS,\n/api/v2/spans"]
    D -->|"Có"| F{"Có tracing dependency và spans?"}
    F -->|"Không"| G["Kiểm tra starter/bridge,\nObservation và sampling"]
    F -->|"Có"| H{"Exporter gửi thành công?"}
    H -->|"Không"| I["Kiểm tra timeout, HTTP status,\nnetwork và exporter logs"]
    H -->|"Có"| J["Kiểm tra service name,\ntime range và truy vấn UI"]
~~~

### 13.2. Đừng dùng một dấu hiệu thay cho toàn bộ pipeline

- Zipkin UI mở được chỉ xác nhận server đang truy cập được.
- Ứng dụng khởi động được chỉ xác nhận cấu hình không làm startup thất bại.
- Có HTTP span chỉ xác nhận một phần instrumentation hoạt động.
- Có module graph không chứng minh module spans đã được tạo.
- Có trace không chứng minh giao dịch nghiệp vụ đã commit hoặc xử lý đúng một lần.

Hãy xác định pipeline theo thứ tự: **instrumentation → sampling → tracer → exporter → network → Zipkin receiver → storage/query/UI**.

## 14. Những lỗi cấu hình khi nâng Spring Boot

### 14.1. Giữ property cũ sau khi nâng Boot

Boot 3.5:

~~~yaml
management:
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

Boot 4.2:

~~~yaml
management:
  tracing:
    export:
      zipkin:
        endpoint: http://localhost:9411/api/v2/spans
~~~

Cần chuyển cả cấu trúc dependency lẫn property. Đừng chỉ thay version Spring Boot mà giữ nguyên ví dụ cũ rồi giả định exporter vẫn được cấu hình.

### 14.2. Khai báo hai tracer bridge cùng lúc

Nếu cùng đưa Brave bridge và OpenTelemetry bridge vào classpath mà không có mục tiêu rõ ràng, auto-configuration có thể không còn xác định theo cách bạn dự kiến hoặc gây xung đột. Chọn một tracer implementation cho ứng dụng theo Spring Boot reference guide.

### 14.3. Nhầm exporter Zipkin với OTLP exporter

Zipkin V2 nhận payload theo Zipkin format tại \`/api/v2/spans\`. OTLP exporter gửi OpenTelemetry Protocol tới OTLP collector endpoint. Hai giao thức và endpoint không giống nhau.

Nếu backend chỉ nhận OTLP, dùng OTLP exporter. Nếu ứng dụng dùng Brave với Zipkin, cấu hình Zipkin reporter/starter. Không đổi URL endpoint mà không đổi exporter/protocol tương ứng.

### 14.4. Cho rằng Insight starter đã bao gồm Zipkin

Spring Modulith Insight và Zipkin exporter có trách nhiệm riêng. Insight hỗ trợ observability/module Actuator; Zipkin starter/reporter đưa spans tới backend. Nếu muốn xem module spans trong Zipkin, cần cả instrumentation và đường export.

## 15. Checklist trước khi triển khai

- [ ] Đã xác định đúng Spring Boot major/minor version.
- [ ] Dependency Zipkin đúng dòng version và được BOM quản lý.
- [ ] Chỉ dùng một tracer implementation theo cấu hình dự kiến.
- [ ] Đã cấu hình đúng endpoint Zipkin V2 \`/api/v2/spans\`.
- [ ] Đã dùng đúng namespace property cho Boot 3.5 hoặc 4.2.
- [ ] Zipkin server đang chạy và ứng dụng truy cập được từ network namespace thực tế.
- [ ] Tên service có giá trị rõ qua \`spring.application.name\`.
- [ ] Sampling probability phù hợp môi trường.
- [ ] Đã kiểm tra exporter connect/read timeout và log khi gửi lỗi.
- [ ] Nếu cần module spans, đã bật Spring Modulith Insight/observability.
- [ ] Client HTTP dùng builder được Spring Boot auto-configure để propagation hoạt động.
- [ ] Đã xác minh trace xuất hiện trong Zipkin UI bằng một kịch bản thực tế.
- [ ] Đã kiểm tra span attributes, baggage và logs không chứa dữ liệu nhạy cảm.
- [ ] Production có network access, TLS/authentication, retention và quyền truy cập phù hợp.
- [ ] Có kiểm thử hoặc runbook cho lỗi endpoint, exporter, sampling và context propagation.

## 16. Bài tập tự luyện

1. **Pipeline:** Phân biệt vai trò của Micrometer Tracing bridge, Zipkin reporter/exporter và Zipkin server. Vì sao thêm một bridge chưa đủ để thấy trace trong UI?
2. **Version:** Một ứng dụng dùng Spring Boot 4.2 nhưng vẫn cấu hình \`management.zipkin.tracing.endpoint\`. Hãy chỉ ra cấu trúc property cần chuyển và dependency cần kiểm tra.
3. **Network:** Spring Boot app và Zipkin cùng chạy trong Docker Compose. Vì sao endpoint \`http://localhost:9411/api/v2/spans\` có thể sai? Địa chỉ phù hợp là gì?
4. **Sampling:** Local đã đặt sampling 1.0, production dùng mặc định 10%. Vì sao số trace ở Zipkin không bằng số HTTP request?
5. **Module spans:** Zipkin có HTTP spans nhưng không có \`module.identifier\`. Hãy nêu các thành phần cần kiểm tra trong Spring Modulith.
6. **Propagation:** Trace của service A không nối với service B dù cả hai đều gửi spans đến Zipkin. Hãy kiểm tra client builder, headers inject/extract và propagation format.
7. **Troubleshooting:** Zipkin UI mở được nhưng không thấy service. Hãy xây dựng thứ tự kiểm tra từ request, sampling, exporter tới truy vấn UI.
8. **Security:** Những dữ liệu nào không nên đưa vào span attributes hoặc baggage? Vì sao backend tracing cần chính sách retention và phân quyền?
9. **Kiểm thử:** Thiết kế một integration test xác nhận request tạo order xuất được HTTP span và module span vào Zipkin test instance.
10. **Kiến trúc:** Vì sao Zipkin trace không thay thế module graph, kiểm thử ranh giới module hoặc kiểm thử bất biến nghiệp vụ?

## 17. Tổng kết

Cấu hình exporter Zipkin cần đủ ba phần: **ứng dụng tạo spans**, **tracer/reporter gửi spans**, và **Zipkin backend nhận rồi hiển thị dữ liệu**. Với Spring Boot 4.2, phương án Brave + Zipkin dùng \`spring-boot-starter-zipkin\` và namespace \`management.tracing.export.zipkin.*\`; các dòng Boot 3.5.x phổ biến dùng Brave bridge/reporter riêng và \`management.zipkin.tracing.*\`.

Trong học phần Spring Modulith Documentation & Observability, hãy kết hợp exporter Zipkin với Spring Modulith Insight khi cần module entry spans. Khi request đi qua các module, trace giúp quan sát duration, lỗi và quan hệ giữa những điểm được instrument. Context propagation giúp liên kết trace qua HTTP hoặc async boundary; sampling và exporter quyết định phần dữ liệu nào thực sự đến backend.

Zipkin là công cụ quan sát đường thực thi, không phải bằng chứng rằng một đơn hàng, thanh toán hoặc event đã hoàn tất đúng. Hãy kết hợp traces với module graph, event metrics, transaction state, idempotency, kiểm thử và đối soát để kiểm chứng hệ thống khi vận hành.

### Tài liệu tham khảo chính thức

1. [Spring Boot 4.2 — Tracing: Brave with Zipkin, starter và sampling](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
2. [Spring Boot 4.2 — Common Application Properties: management.tracing.export.zipkin.*](https://docs.spring.io/spring-boot/appendix/application-properties/).
3. [Spring Boot 3.5 — Tracing: bridge, reporter và property legacy](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html).
4. [Spring Boot 3.5 — Common Application Properties: management.zipkin.tracing.*](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/).
5. [OpenZipkin — Quickstart: chạy Zipkin bằng Docker](https://zipkin.io/pages/quickstart.html).
6. [OpenZipkin — Zipkin V2 API](https://zipkin.io/zipkin-api/).
7. [Spring Modulith — Production-ready Features: Observing Application Modules](https://docs.spring.io/spring-modulith/reference/production-ready.html).
