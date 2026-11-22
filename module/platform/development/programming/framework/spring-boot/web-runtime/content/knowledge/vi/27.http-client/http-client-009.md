# Quan sát lời gọi HTTP và truyền trace qua builder được quản lý trong Spring Boot

Khi một request đi qua nhiều dịch vụ, việc biết rằng server đã nhận request là chưa đủ. Ta còn cần biết ứng dụng đã gọi HTTP đến đâu, trả về status nào, mất bao lâu, có lỗi hay timeout không, và làm sao **nối các lời gọi giữa nhiều service thành cùng một distributed trace**. Trong Spring Boot, đường đi ít lỗi nhất là tạo **RestClient**, **RestTemplate** hoặc **WebClient** từ **builder đã được Spring Boot tự cấu hình và quản lý**. Các builder này được áp dụng cấu hình HTTP client, Micrometer Observation và cơ chế truyền trace context; tạo client trực tiếp có thể làm mất instrumentation dù logic HTTP vẫn chạy được.

Bài thuộc module **Spring Boot - web-runtime**, chủ đề cha **HTTP client**. Ví dụ tập trung **Spring Boot 3.3.13, Java 17, Spring MVC, RestClient.Builder, Spring Boot Actuator, Micrometer Observation, Micrometer Tracing và OpenTelemetry/Zipkin**. Những mã và package cụ thể là của nhánh Spring Boot 3.3; không sao chép package từ Spring Boot 4 vào project 3.3. Các yêu cầu an toàn về trace propagation, dữ liệu nhạy cảm, timeouts, sampling và môi trường production được trình bày xuyên suốt.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **logs, metrics, traces**, khái niệm **observation**, **span**, **trace ID**, **span ID**, **parent span** và **trace context**.
2. Giải thích vì sao inject **RestClient.Builder** được auto-configured giúp tự ghi **http.client.requests** và propagate context khi hệ thống có Micrometer Tracing.
3. Biết lúc nào chọn **RestClient** (đồng bộ), **RestTemplate** (legacy) hoặc **WebClient** (reactive) và builder tương ứng.
4. Tạo project chạy được: server nhận **GET /demo/entry**, dùng managed RestClient gọi **GET /demo/target**, hai request cùng trace ID nhưng khác span.
5. Tạo tracing backend cho môi trường dev và kiểm tra **Zipkin**, **Actuator metrics**, correlation IDs trong log, cùng header **traceparent**.
6. Phân biệt **instrumentation** với **exporting**: có metric hay span local không đồng nghĩa trace đã xuất thành công đến collector.
7. Viết test HTTP-client behavior bằng **@RestClientTest + MockRestServiceServer**; biết tại sao test slice/MockMvc không tự chứng minh network trace propagation.
8. Tránh các anti-pattern **RestClient.create**, **RestClient.builder**, **new RestTemplate**, **WebClient.create** không thông qua builder Boot trong một đường gọi cần tracing.
9. Tùy chỉnh client một cách additive qua builder/customizer mà không đè mất ObservationRegistry hoặc context propagator.
10. Chẩn đoán lỗi mất trace khi chuyển thread, WebFlux Reactor, proxy, retry, sampling và khác phiên bản propagation header.

Điều kiện đầu vào: Java 17+, Spring Boot, REST Controller, Maven, HTTP client, JSON, HTTP headers và kiến thức căn bản về logging.

## 2. Quan sát lời gọi HTTP là gì?

### 2.1. Ba trụ cột observability

| Trụ cột | Dữ liệu | Ví dụ | Câu hỏi trả lời |
| --- | --- | --- | --- |
| **Logs** | Các sự kiện có thông điệp và fields, thường kèm trace ID / span ID. | Client gọi catalog, gặp timeout lúc 12:30. | Chuyện gì đã xảy ra? |
| **Metrics** | Số liệu tổng hợp theo thời gian và tags có cardinality kiểm soát. | Số lượng, duration, status của **http.client.requests**. | Tần suất, độ trễ và tỷ lệ lỗi biến động ra sao? |
| **Traces** | Các span gắn quan hệ parent/child trong một trace. | GET /orders → client GET /catalog → catalog server. | Request đi qua những bước nào, phần nào chậm? |

**Micrometer Observation** là abstraction chung để tạo một hoạt động có thời gian sống và metadata. Observation có thể được observation handlers đưa vào **metrics**, **tracing**, hoặc cả hai. Một **Metric** không phải một **Trace**; metrics thường tổng hợp nhiều request, còn trace cho thấy chuỗi hoạt động của một request cụ thể.

### 2.2. Trace ID, span ID và parent/child

~~~text
Browser GET /demo/entry
         |
         v
Spring MVC server span (A)
    traceId = T
    spanId  = A
         |
         v
RestClient outbound HTTP span (B)
    traceId = T
    spanId  = B
    parent  = A
         |
         +-- HTTP request có propagation headers -->
                 Spring MVC /demo/target span (C)
                      traceId = T
                      spanId  = C
                      parent  = B
~~~

Ba span có thể có **cùng trace ID** nhưng **span ID khác nhau**. Một trace có thể gồm hàng chục span. Không bao giờ kỳ vọng span ID của incoming server span và outgoing client span giống nhau. Nếu ứng dụng chỉ in một random request ID trên mỗi service mà không propagation context, log có thể trông giống tracing nhưng không có parent/child relation.

### 2.3. Propagation là gì?

Trên đường đi HTTP, client instrumentation **inject** trace context vào request headers. Downstream server instrumentation **extract** context, tạo server span kế tiếp và liên kết nó với parent span upstream. Với W3C Trace Context, header thường có dạng:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor-data-if-present
~~~

Ý nghĩa bốn phần của traceparent:
- **00**: phiên bản format.
- **32 ký tự hex**: trace ID.
- **16 ký tự hex**: parent span ID mà caller gửi đi.
- **2 ký tự flags**: trace flags, ví dụ bit sampled.

Header **tracestate** có thể không xuất hiện. Nếu không dùng W3C, một số hệ thống dùng **B3** hoặc B3 multi-header. Spring Boot 3.3 có thuộc tính **management.tracing.propagation.consume/produce/type**, mặc định thường đọc được W3C/B3 và phát W3C theo cấu hình được tài liệu liệt kê. Đừng ép gửi đồng thời mọi format khi chưa có nhu cầu interoperability; thay đổi format cần kiểm tra toàn bộ service chain và gateway.

**Trace ID không phải credential**, không thay authentication/authorization hoặc user ID. Không dùng traceparent do client gửi để quyết định quyền hay chấp nhận bất kỳ baggage nào là dữ liệu tin cậy.

### 2.4. Không phải HTTP headers nào cũng tự có mặt

Tùy classpath và cấu hình:
- Chỉ có **Spring Web**: client gọi HTTP được, chưa chắc có metrics/tracing.
- Có **Spring Boot Actuator** và metrics infrastructure: các HTTP-client observations có thể tạo **http.client.requests**.
- Có **Micrometer Tracing bridge + tracer implementation + exporter**: tạo trace spans, correlation IDs và có thể gửi traces đến backend.
- Dùng **auto-configured client builders**: các customizer quan trọng, gồm instrumentation, được gắn vào client.
- Dùng client tự tạo không qua Boot builder: có thể mất customizers; request vẫn trả HTTP 200 nhưng không thấy span/hay traceparent.

Không kết luận "tracing hỏng" chỉ vì chưa thấy span trong UI; có thể sampling, exporter, network, backend indexing hoặc test setup khác nhau.

## 3. Builder được quản lý là điểm trung tâm

### 3.1. Ba API và builder tương ứng

| HTTP client | Builder đúng từ Spring Boot | Mô hình | Khi nên dùng |
| --- | --- | --- | --- |
| **RestClient** | Inject **RestClient.Builder** | Blocking / imperative, fluent API | Ứng dụng Spring MVC, service code đồng bộ. |
| **RestTemplate** | Inject **RestTemplateBuilder** | Blocking / legacy | Dự án cũ hoặc thư viện đã dựa vào RestTemplate. |
| **WebClient** | Inject **WebClient.Builder** | Reactive / non-blocking | WebFlux/Reactor, reactive service, streaming phù hợp. |

**Spring Boot 3.3** tạo và cấu hình **prototype RestClient.Builder**, do đó mỗi điểm injection thường nhận builder được cấu hình từ auto-configuration. WebClient.Builder cũng được Boot cấu hình dạng prototype khi WebFlux client có trên classpath. Với **RestTemplate**, Boot cung cấp **RestTemplateBuilder** thay vì mặc định tạo sẵn một RestTemplate bean duy nhất.

Một builder đã được Boot cấu hình có thể tích hợp:
- HTTP message converters/codecs và request factory/connector.
- Settings cho client, SSL và resources phù hợp với version/classpath.
- **ObservationRegistry**, Micrometer HTTP client instrumentation.
- **Trace context propagation** vào downstream requests khi tracing được bật.
- Các customizer do ứng dụng hoặc framework đăng ký.

Việc inject builder không bảo đảm mọi trace sẽ được backend lưu: còn phụ thuộc sample decision, exporter và collector.

### 3.2. Đúng và sai

**Nên làm trong bean do Spring quản lý:**

~~~java
@Service
public class PartnerService {
    private final RestClient client;

    public PartnerService(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://partner.example.test")
                .build();
    }
}
~~~

Đoạn trên chỉ minh họa cách inject, **không là file độc lập biên dịch được** vì thiếu import và method sử dụng. Project runnable ở mục 7 sẽ có đầy đủ file.

**Cách dễ làm mất auto-configuration:**

~~~java
RestClient clientA =
        RestClient.create("https://partner.example.test");

RestClient clientB =
        RestClient.builder()
                .baseUrl("https://partner.example.test")
                .build();

RestTemplate template = new RestTemplate();

WebClient webClient =
        WebClient.create("https://partner.example.test");
~~~

Đây là những API hợp lệ của Spring, không phải syntax error. Tuy nhiên khi dùng trực tiếp như vậy, bạn **không mặc định nhận các Observation customizers và trace propagation của Spring Boot**. Có thể gắn instrumentation thủ công nếu thật sự cần, nhưng đây là trách nhiệm của chính bạn. Với ứng dụng Boot thông thường, lựa chọn ít lỗi hơn là inject builder được quản lý.

### 3.3. Builder state và phạm vi customization

**RestClient.Builder/WebClient.Builder** có trạng thái: bạn gọi baseUrl, defaultHeader, filter, requestFactory v.v. sẽ ảnh hưởng client được build từ builder đó sau này. Vì thế:

- Ở **constructor injection** của một @Service, cấu hình builder cho một client riêng rồi build là cách rõ ràng.
- Nếu một nơi cần nhiều cấu hình khác nhau từ cùng một builder đã inject, có thể **clone()** trước khi tùy chỉnh từng client.
- Không tùy biến một builder shared mutable ở nhiều thread hoặc nhiều thành phần rồi mong mọi client có cấu hình độc lập.
- Với RestTemplateBuilder trong Boot 3.3, các method thiết lập thường trả về **builder mới**; không áp dụng giả định mutability giống RestClient.Builder.
- Nếu cần config toàn ứng dụng, khai báo **RestClientCustomizer**, **RestTemplateCustomizer** hoặc **WebClientCustomizer** phù hợp thay vì tạo lại builder trống.

**Không tự khai báo một @Bean RestClient.Builder mới trống** chỉ để đổi base URL, vì có thể thay thế builder Boot và làm mất customizers. Nếu cần builder riêng, cần sử dụng configurer/customizers tương thích; ưu tiên inject builder có sẵn và build một bean RestClient.

### 3.4. Instrumentation không đồng nghĩa mọi custom header đều an toàn

Một HTTP request interceptor/filter dùng để log hoặc thêm header có thể:
- làm lộ Authorization, Cookie, Set-Cookie hoặc payload;
- đọc body stream khiến downstream không còn body;
- tạo span trùng lặp nếu tự bọc observation ở cấp HTTP client;
- ghi high-cardinality URL vào metrics;
- ghi đè traceparent/tracestate và phá parent span.

Dùng instrumentation tích hợp của framework; chỉ thêm thông tin nghiệp vụ không nhạy cảm và có giới hạn.

## 4. Spring Boot Actuator, Micrometer Observation và Micrometer Tracing

### 4.1. Dependencies theo mục tiêu

| Mục tiêu | Dependency cơ bản | Kết quả |
| --- | --- | --- |
| HTTP client hoạt động | spring-boot-starter-web hoặc webflux phù hợp | HTTP request/response. |
| Quan sát và metrics | spring-boot-starter-actuator | Micrometer Observation và metrics instrumentation. |
| Distributed tracing (OpenTelemetry) | micrometer-tracing-bridge-otel | Bridge Observation sang tracer OTel. |
| Export traces sang Zipkin | io.opentelemetry:opentelemetry-exporter-zipkin | Gửi spans đến Zipkin khi backend sẵn sàng. |
| Export traces sang OTLP | io.opentelemetry:opentelemetry-exporter-otlp | Alternative gửi sang OTLP collector. |
| Test REST client | spring-boot-starter-test | JUnit, @RestClientTest, MockRestServiceServer. |

Trong dự án thực tế, chọn **một stack tracer/exporter nhất quán**, không đồng thời bật Brave, OTel Java Agent, Spring Boot Micrometer instrumentation và nhiều auto-instrumentation framework thiếu kế hoạch. Nếu dùng Java agent có sẵn, phải kiểm tra duplicate spans và cấu hình quản trị.

### 4.2. ObservationRegistry và tên metric

Spring Boot Actuator instrument **RestClient, RestTemplate, WebClient** được tạo từ builder quản lý. Theo tài liệu Boot 3.3, metric client mặc định thường có tên:

~~~text
http.client.requests
~~~

HTTP client observation thường có thông tin như HTTP method, status, URI template, host/client name, outcome/exception tùy phiên bản Spring Framework và instrumentation. Các tags không phải contract domain của API; đừng dựa vào mọi tag cố định nếu không kiểm tra version.

Với HTTP server, metric tương ứng thường là **http.server.requests**, không nhầm với lời gọi HTTP outbound. Một request GET /demo/entry có thể tạo **một server observation**, **một client observation** và **một server observation tại downstream**, chứ không chỉ một request duy nhất.

### 4.3. Tracing bridge và sampling

Spring Boot 3.3 hỗ trợ Micrometer Tracing với OpenTelemetry hoặc Brave. Ví dụ cấu hình dev:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Mặc định nhánh Boot 3.3 sampling thường khoảng **10%**. Bật **1.0** trong lab để các request đều dễ tìm trong backend; production phải đặt xác suất hợp lý theo khối lượng traffic, chi phí lưu trữ, yêu cầu forensic và sampling policy. Một trace không xuất hiện trong Zipkin khi sampling thấp **không chứng minh propagation đã mất**.

**Sampling ảnh hưởng việc thu thập/ghi lại span**, trong khi propagation metadata có thể tiếp tục tùy tracer và quyết định upstream. Không tự tạo trace ID mới khi sampling=false; muốn xác minh cần xem header và trace context trong hệ thống tương thích.

### 4.4. Baggage và correlation IDs

**Trace ID** liên kết các span, **span ID** phân biệt từng đoạn. **Correlation IDs trong logs** giúp lọc log cùng trace; khi Micrometer Tracing được kích hoạt, Spring Boot 3.3 thường gắn traceId/spanId vào MDC/log pattern mặc định. Không dùng **session ID** hoặc access token làm correlation ID.

**Baggage** là metadata bổ sung được propagate theo context và có thể vượt service boundary. Tuyệt đối không đưa password, session cookie, access token, email hoặc dữ liệu cá nhân nhạy cảm vào baggage. Header baggage có thể qua nhiều bên thứ ba nếu request không kiểm soát. Dùng service/tenant identifiers được chuẩn hóa và có security review nếu thực sự cần.

## 5. Trace context trên dây: W3C và B3

### 5.1. Một request có traceparent

~~~http
GET /demo/target HTTP/1.1
Host: localhost:8080
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-8d8cf3d2b21814db-01
~~~

**traceId** thường giữ nguyên qua các hop của cùng trace. Phần **parent span ID** trong outbound traceparent là ID của span đại diện cho lời gọi ra (hoặc context đã được inject), không phải nhất thiết ID server span ở downstream. Khi server nhận request, nó tạo span mới có parent là span phía client.

**Không khẳng định traceparent luôn có cùng 16 ký tự spanId trước và sau mỗi hop**; mỗi span mới cần identifier riêng. Trong lab, chỉ kiểm tra incoming trace ID giống downstream trace ID và span hierarchy trong Zipkin.

### 5.2. B3 và sự pha trộn định dạng

Trong hệ Spring Cloud Sleuth cũ, B3 headers có thể phổ biến. Spring Boot 3.3 cho phép cấu hình consume/produce propagation formats. Nếu dịch vụ A phát W3C nhưng gateway B chỉ chuyển B3, downstream có thể tạo trace mới. Hãy xác định hợp đồng propagation:
- upstream gửi format nào;
- gateway/proxy giữ hay lọc headers nào;
- downstream tracer đọc được format nào;
- trust boundary có yêu cầu khởi tạo trace mới không;
- sampling flags và baggage được giữ/giới hạn như thế nào.

Không tự chuyển đổi định dạng bằng cách copy traceId vào một header custom duy nhất; đó chưa phải là distributed trace có quan hệ parent/child.

### 5.3. W3C headers không phải authentication

traceparent và tracestate là dữ liệu **do caller có thể gửi**, không phải chữ ký mật mã. Bên nhận phải tiếp tục authentication và authorization riêng. Nếu cần chống giả mạo trace metadata, cần chính sách trust boundary, không coi trace ID là session/token.

### 5.4. Proxy và gateway

Một reverse proxy hoặc API gateway có thể:
- tiếp tục trace nếu được instrument;
- chỉ chuyển header traceparent/tracestate;
- tạo span riêng;
- gán trace mới nếu policy tách vùng tin cậy;
- bỏ headers hoặc đổi sang B3.

Nếu một service vẫn có metrics HTTP nhưng traces không liên kết, hãy kiểm tra **actual outbound headers** và hạ tầng trung gian trước khi sửa controller. Không log toàn bộ headers trong production để debug vì dễ lộ credentials.

## 6. Thiết kế demo có thể chạy

Dự án mô phỏng ba span trên **cùng một JVM** bằng cách để endpoint /demo/entry gọi lại /demo/target qua một HTTP request thật. Đây là thủ thuật **chỉ dành cho bài lab**, không nên dùng self-call qua loopback như kiến trúc production. Mục tiêu là nhìn rõ ràng giữa **server span nhận đầu vào**, **client span outbound**, và **server span nhận ở target**.

~~~text
curl /demo/entry
     |
     v
Tomcat server: /demo/entry
     |
     v
RemoteDirectoryClient
   (managed RestClient.Builder)
     |
     +--- HTTP GET http://localhost:8080/demo/target
               traceparent được inject
                          |
                          v
                  Tomcat server: /demo/target
                      extract context
                          |
                          v
                  JSON: traceId, spanId
     |
     v
/demo/entry JSON có traceId upstream và downstream
~~~

**Kết quả mong đợi:** Hai trace ID trong JSON **giống nhau**; span ID downstream thường khác server span upstream. Giá trị hex là ngẫu nhiên cho mỗi trace nên không thể ghi một stdout cố định như ví dụ thuật toán. Zipkin hiển thị các span liên kết nếu exporter/backend hoạt động.

### 6.1. Cấu trúc thư mục

~~~text
trace-client-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/httptrace/
    HttpTraceApplication.java
    TargetReply.java
    RemoteDirectoryClient.java
    TracingDemoController.java
  src/main/resources/
    application.yml
  src/test/java/com/example/httptrace/
    RemoteDirectoryClientTest.java
~~~

Dùng **Java 17**, Maven và Spring Boot **3.3.13** để package/class names tương ứng. Nếu tạo từ Spring Initializr, chọn **Spring Web**, **Spring Boot Actuator** và **Spring Boot Starter Test**; sau đó thêm tracing bridge/exporter theo POM dưới đây.

### 6.2. pom.xml — phiên bản và dependencies

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>trace-client-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-otel</artifactId>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-exporter-zipkin</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Không cần pin riêng phiên bản Micrometer, OpenTelemetry và Spring Framework** khi dùng BOM Spring Boot. Version 3.3.13 là mốc học tập cố định, không phải khuyến nghị dùng patch đã hết hỗ trợ cho production. Khi nâng cấp major, kiểm tra lại package và properties; những ví dụ dùng Boot 4 có API khác.

### 6.3. application.yml — dev tracing, metrics

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: trace-client-demo

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

**Giải thích:**
- **spring.application.name** được dùng làm service identity trong observability/tracing khi cấu hình được áp dụng.
- **server.port:8080** phải trùng với base URL của RemoteDirectoryClient để self-call lab.
- **metrics endpoint** chỉ mở ở đây cho máy học. Trên production, không public toàn bộ Actuator endpoints ra Internet.
- **sampling probability=1.0** tiện khi thử ít request. Đối với production, chọn mức thấp hơn theo traffic/cost.
- **management.zipkin.tracing.endpoint** chỉ đích Zipkin local. Nếu Zipkin chưa chạy, HTTP API **vẫn có thể hoạt động** nhưng exporter có thể log cảnh báo/lỗi gửi span; không hiểu lầm thành lỗi application request.

Nếu không muốn chạy Zipkin, có thể tạm bỏ exporter dependency/config và chỉ học observations/metrics; nhưng để kiểm tra trace parent/child trong UI đúng như bài, nên chạy Zipkin.

### 6.4. Main class

**src/main/java/com/example/httptrace/HttpTraceApplication.java**

~~~java
package com.example.httptrace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpTraceApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpTraceApplication.class, args);
    }
}
~~~

### 6.5. Data model cho response

**src/main/java/com/example/httptrace/TargetReply.java**

~~~java
package com.example.httptrace;

public record TargetReply(
        String message,
        String traceId,
        String spanId) {
}
~~~

Java **record** có sẵn từ Java 16, nên Java 17 chạy được. Jackson do spring-boot-starter-web cung cấp có thể serialize/deserialize record này. Trường **traceId/spanId** chỉ xuất hiện trong response **vì demo cố ý trả để kiểm tra**; một API sản xuất thường chỉ cần log correlation ID theo policy, không bắt buộc trả toàn bộ trace metadata cho client.

### 6.6. HTTP client quan trọng nhất: inject managed builder

**src/main/java/com/example/httptrace/RemoteDirectoryClient.java**

~~~java
package com.example.httptrace;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class RemoteDirectoryClient {
    private final RestClient client;

    public RemoteDirectoryClient(RestClient.Builder builder) {
        // Builder nhận từ Boot đã tích hợp ObservationRegistry/customizers.
        this.client = builder
                .baseUrl("http://localhost:8080")
                .build();
    }

    public TargetReply fetchTarget() {
        return client.get()
                .uri("/demo/target")
                .retrieve()
                .body(TargetReply.class);
    }
}
~~~

**Vì sao code này là trọng tâm của bài:**

1. **RestClient.Builder** là bean Spring Boot auto-configured; constructor injection lấy instance do container cấu hình.
2. Chúng ta **không gọi** RestClient.builder()/RestClient.create() theo đường thủ công.
3. **ObservationRestClientCustomizer** của Actuator có cơ hội gắn registry và instrumentation.
4. Tracing HTTP client có thể tạo client span, inject context vào outbound headers. Khi server bên kia có tracing instrumentation tương thích, nó nối vào cùng trace.
5. Chỉ build một client ở constructor rồi tái sử dụng; tránh tạo client mới trên mọi request.
6. **URI** là đường dẫn cố định, còn với URL có ID động hãy dùng **template** trong .uri("/orders/{id}", orderId) để metrics không ghi vô số raw path.
7. Client tự dùng endpoint loopback để demo; trong hệ thật cần lấy base URL từ cấu hình deployment và thực hiện network timeout, retry, TLS, authentication/authorization phù hợp.

**Không thêm header traceparent thủ công** trong fetchTarget. Auto instrumentation mới là nơi chịu trách nhiệm đặt header nhất quán với active span.

### 6.7. Controller nhận/gửi trace

**src/main/java/com/example/httptrace/TracingDemoController.java**

~~~java
package com.example.httptrace;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class TracingDemoController {
    private static final Logger log =
            LoggerFactory.getLogger(TracingDemoController.class);

    private final RemoteDirectoryClient client;
    private final Tracer tracer;

    public TracingDemoController(
            RemoteDirectoryClient client,
            Tracer tracer) {
        this.client = client;
        this.tracer = tracer;
    }

    public record EntryReply(
            String entryTraceId,
            String targetTraceId,
            String targetSpanId) {
    }

    @GetMapping("/entry")
    public EntryReply entry() {
        String currentTrace = traceId();
        log.info("Demo entry started");

        TargetReply remote = client.fetchTarget();

        log.info("Demo entry completed");
        return new EntryReply(
                currentTrace,
                remote.traceId(),
                remote.spanId());
    }

    @GetMapping("/target")
    public TargetReply target() {
        log.info("Demo target received request");
        return new TargetReply(
                "target-ok",
                traceId(),
                spanId());
    }

    private String traceId() {
        Span span = tracer.currentSpan();
        return span == null
                ? "no-active-span"
                : span.context().traceId();
    }

    private String spanId() {
        Span span = tracer.currentSpan();
        return span == null
                ? "no-active-span"
                : span.context().spanId();
    }
}
~~~

**Chú ý:** Controller inject **Tracer** đã được auto-configured từ Micrometer Tracing. Nếu bỏ tracing bridge và exporter khỏi POM, tùy auto-configuration, có thể không còn bean Tracer để inject: khi đó project demo sẽ cần bỏ phần Tracer/đổi kiến trúc. Phần code trên phải được dùng với **đầy đủ dependency POM**.

Mã đặt **log.info** bên trong server observation scope, nên khi tracing bật các log có thể có MDC traceId/spanId. Những ID đó phục vụ chẩn đoán; không chứa password/cookie hay payload.

Endpoint **/demo/entry** là request inbound; RestClient tạo một **outbound request thật** đến **/demo/target**. Tracer ở target quan sát server span của request thứ hai; **entryTraceId** và **targetTraceId** phải giống khi propagation đúng. targetSpanId phải khác span ID của entry server span theo đường tracing thông thường.

### 6.8. Khởi chạy Zipkin ở môi trường lab

Nếu máy có Docker, có thể dùng:

~~~bash
docker run --rm -p 9411:9411 openzipkin/zipkin
~~~

Mở **http://localhost:9411** để xem Zipkin UI. Khi container chưa sẵn sàng, exporter có thể báo không kết nối được; hãy kiểm tra local port 9411 và network. Lệnh không cung cấp bảo vệ production và chỉ phù hợp lab hoặc môi trường được kiểm soát.

Nếu không có Docker, dùng một Zipkin/OTLP collector đã được tổ chức triển khai, rồi cập nhật endpoint và exporter tương ứng. **Không tự gửi traces chứa dữ liệu nội bộ đến dịch vụ public không được phê duyệt.**

### 6.9. Chạy ứng dụng

Linux/macOS:

~~~bash
./mvnw clean package
java -jar target/trace-client-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvnw.cmd clean package
java -jar target/trace-client-demo-0.0.1-SNAPSHOT.jar
~~~

Có thể dùng **mvn clean package** nếu không có Maven wrapper. Chạy app từ root project; cần chắc cổng **8080** đang rảnh. Nếu đổi port, cũng phải đổi base URL client trong demo, nếu không request sẽ fail do connection refused.

### 6.10. Gọi endpoint và đọc response

~~~bash
curl -i http://localhost:8080/demo/entry
~~~

Kỳ vọng HTTP **200 OK** với body **cấu trúc** như:

~~~json
{
  "entryTraceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "targetTraceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "targetSpanId": "00f067aa0ba902b7"
}
~~~

**Các giá trị hex trên chỉ để minh họa format**; mỗi request có IDs mới. Hai trường trace ID phải bằng nhau, không lấy targetSpanId ví dụ làm giá trị cố định. Thứ tự JSON properties có thể thay đổi, và controller không trả về traceparent header. Khi không có active span, demo trả **no-active-span**, là tín hiệu cần kiểm tra tracing config chứ không phải giá trị hợp lệ.

Trong Zipkin UI, chọn service **trace-client-demo**, tìm trace theo khoảng thời gian request; kỳ vọng thấy server span của /demo/entry, HTTP client span và server span của /demo/target liên kết trong một trace. UI có thể hiển thị tên span khác nhau theo convention của instrumentation. Không khẳng định chính xác mọi span name/status nếu chưa kiểm tra version.

### 6.11. Xác minh inbound W3C propagation

Gửi traceparent hợp lệ từ client tới server:

~~~bash
curl -i \
  -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' \
  http://localhost:8080/demo/entry
~~~

Với Micrometer Tracing/OpenTelemetry W3C propagation như cấu hình lab, một incoming traceparent hợp lệ có thể làm **entryTraceId** bằng giá trị trace ID **4bf92f3577b34da6a3ce929d0e0e4736**; downstream giữ trace ID đó nếu builder instrumentation hoạt động. **Span IDs không cần giống** span ID 00f067aa0ba902b7 từ caller: server tạo span mới.

Header từ client ngoài không chứng minh danh tính hoặc quyền, không dùng nó trong authorization. Nếu đặt propagation format không tương thích hoặc proxy bỏ header, service có thể tạo trace mới.

### 6.12. Đọc HTTP client metrics qua Actuator

Sau khi gọi **/demo/entry** ít nhất một lần, thử:

~~~bash
curl -i http://localhost:8080/actuator/metrics/http.client.requests
~~~

Với Actuator metrics được bật, thường có measurement/timer cho HTTP client observations đã tạo. Trước lời gọi đầu tiên, meter có thể chưa xuất hiện và Actuator có thể trả **404** cho metric chưa được ghi nhận; đó không chứng minh auto-configuration sai. Nếu đã gọi mà không thấy, xem classpath, builder creation và metrics enablement.

Có thể xem metrics inbound riêng:

~~~bash
curl -i http://localhost:8080/actuator/metrics/http.server.requests
~~~

Không tự mặc định có chính xác một series: cùng metric có thể có nhiều tags theo method, URI template, status, exception. Để dashboard bền vững, dùng tags có giới hạn cardinality như HTTP method, route template hoặc service; không dùng raw user ID, email, token hoặc full URL query string làm low-cardinality tags.

**Actuator chỉ được mở health/info/metrics trong lab.** Production phải hạn chế management endpoints qua mạng, authentication và monitoring pipeline phù hợp.

## 7. Kiểm thử REST client bằng @RestClientTest

### 7.1. Mục tiêu của test slice

Spring Boot 3.3 có **@RestClientTest** giúp test bean HTTP client mà không phải khởi động web server thật. Nó có thể cấu hình **RestClient.Builder**, **RestTemplateBuilder** và **MockRestServiceServer**. Đoạn test dưới đây chứng minh endpoint URL và JSON mapping khi client gọi HTTP. **Nó không chứng minh distributed tracing qua network**: test slice không thay thế HTTP server thật, span exporter và propagation header.

### 7.2. Test class runnable

**src/test/java/com/example/httptrace/RemoteDirectoryClientTest.java**

~~~java
package com.example.httptrace;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(RemoteDirectoryClient.class)
class RemoteDirectoryClientTest {

    @Autowired
    RemoteDirectoryClient client;

    @Autowired
    MockRestServiceServer server;

    @Test
    void fetchTargetDeserializesJsonResponse() {
        server.expect(requestTo(
                "http://localhost:8080/demo/target"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                "{\"message\":\"target-ok\",\"traceId\":\"t1\",\"spanId\":\"s1\"}",
                MediaType.APPLICATION_JSON));

        TargetReply result = client.fetchTarget();

        assertEquals("target-ok", result.message());
        assertEquals("t1", result.traceId());
        assertEquals("s1", result.spanId());
        server.verify();
    }
}
~~~

**Ý nghĩa:**

- @RestClientTest chỉ tạo context hẹp đủ cho RemoteDirectoryClient, JSON converters và mock server.
- MockRestServiceServer intercept request mà client tạo, nên không cần server chạy cổng 8080 hay Zipkin cho test này.
- requestTo(...) xác nhận URL, method(GET) xác nhận HTTP method, withSuccess tạo response JSON.
- Assertions kiểm tra record mapping; status/content đã được mô phỏng nên không thể dùng để kết luận bên ngoài thực sự trả về như vậy.
- Test này **không kiểm tra propagation header** vì không tạo một real incoming span/network server; đó là một test chức năng HTTP client.
- Mã dùng package của Spring Boot 3.3; không copy tên package @RestClientTest từ Spring Boot 4 khác nhánh.

### 7.3. Tại sao @SpringBootTest có thể không có trace exporter?

Theo tài liệu Spring Boot 3.3, những tracing components dùng để report dữ liệu **không được auto-configured mặc định trong @SpringBootTest**. Khi cần chúng trong integration test, có thể dùng **@AutoConfigureObservability** trên test Spring Boot thật. Với sliced tests, annotation này có thể cung cấp **no-op Tracer** và không hỗ trợ export dữ liệu từ slice. Vì thế:

- Test client contract bằng @RestClientTest.
- Test trace propagation end-to-end bằng **server thật trên HTTP**, cùng collector/backend hoặc kiểm tra header ở receiving service.
- Đừng khẳng định "missing span trong @RestClientTest" là bug của production builder.
- Muốn test header propagation tự động có thể dùng in-process tracing/test instrumentation có kiểm soát, nhưng phải cấu hình tracer, active Observation và parent context rõ ràng.
- Không dùng Thread.sleep cho tracing exporter như một assertion thời gian cứng; exporter thường batch/asynchronous.

### 7.4. Kiểm thử runtime thật

Trong môi trường dev có thể thực hiện:

~~~bash
./mvnw test
./mvnw spring-boot:run
curl -i http://localhost:8080/demo/entry
curl -i http://localhost:8080/actuator/metrics/http.client.requests
~~~

Kỳ vọng test chạy, request HTTP 200, hai trace IDs của /demo/entry và /demo/target bằng nhau, metrics sau request có thể được truy xuất, và Zipkin hiển thị chuỗi spans nếu exporter đang kết nối. Không lẫn lộn test chức năng, metrics và distributed traces làm một điều kiện duy nhất.

## 8. RestTemplateBuilder: dự án legacy vẫn có instrumentation

Trong Spring Boot 3.3, **RestTemplate** là client đồng bộ cổ điển. Boot không tự cung cấp một RestTemplate bean duy nhất, nhưng cung cấp **RestTemplateBuilder** đã cấu hình. Nếu dự án hiện dùng RestTemplate, đừng tạo mới bằng **new RestTemplate()** khi muốn trace propagation qua auto-config.

Ví dụ class độc lập **nếu đặt vào cùng package và project của demo**:

~~~java
package com.example.httptrace;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class LegacyDirectoryClient {
    private final RestTemplate template;

    public LegacyDirectoryClient(RestTemplateBuilder builder) {
        this.template = builder
                .rootUri("http://localhost:8080")
                .build();
    }

    public TargetReply fetchTarget() {
        return template.getForObject(
                "/demo/target", TargetReply.class);
    }
}
~~~

**package RestTemplateBuilder ở Spring Boot 3.3 là org.springframework.boot.web.client.RestTemplateBuilder.** Các phiên bản Boot mới có thể thay package, nên khi học phải theo đúng mốc version.

RestTemplateBuilder thường trả builder mới sau mỗi configuration method. Nó cho phép cấu hình request factory, timeout, basic auth, interceptors, SSL bundle và customizers theo nhu cầu. Dùng builder Boot giúp Actuator gắn HTTP observations, thay vì trông chờ tự phát hiện một RestTemplate được tạo thủ công.

**Không cần chuyển mọi RestTemplate sang RestClient chỉ để có traces.** Nếu đã quản lý builder đúng, có thể tiếp tục instrument code cũ. Migration sang RestClient là quyết định API/maintainability riêng; chỉ cần bảo đảm observability không bị mất trong quá trình thay thế.

## 9. WebClient.Builder: client reactive

Nếu dùng **spring-boot-starter-webflux** hoặc Reactor, **WebClient** là lựa chọn non-blocking. Spring Boot cung cấp **WebClient.Builder** prototype; khi cần metrics/traces, cũng nên inject builder đó.

Ví dụ class **tùy chọn**, chỉ biên dịch khi đã có **spring-boot-starter-webflux** cùng Spring Boot project; không thêm class này vào demo Maven ban đầu nếu chưa thêm dependency:

~~~java
package com.example.httptrace;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveDirectoryClient {
    private final WebClient client;

    public ReactiveDirectoryClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://localhost:8080")
                .build();
    }

    public Mono<TargetReply> fetchTarget() {
        return client.get()
                .uri("/demo/target")
                .retrieve()
                .bodyToMono(TargetReply.class);
    }
}
~~~

**WebClient.Builder** đã được Boot áp dụng codecs, client connector/reactor resources và observation integration khi dependencies phù hợp. **WebClient.create(...)** thường bỏ qua auto-configuration/customizers. Không chuyển từ non-blocking sang .block() tùy tiện trong reactive request processing.

### 9.1. Context propagation trong Reactor

Tracing span context có thể sống trong **ThreadLocal**, còn reactive pipeline có thể chuyển thread. Trong Spring Boot 3.3, property:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

có thể bật tự động khôi phục context cho reactive operators theo cơ chế Micrometer Context Propagation/Reactor phù hợp. Cần test trên pipeline thực tế, không mặc định mọi custom scheduler, callback hoặc executor đều được xử lý chỉ nhờ property. Nếu trace bị tách ở boundary **publishOn, subscribeOn hoặc custom scheduler**, xem Reactor Context, instrumentation và context propagation thay vì chèn traceparent thủ công.

### 9.2. Không phải mọi reactive pipeline đều là HTTP

Một WebFlux app còn có Kafka, R2DBC, messaging, scheduled jobs hoặc timers; mỗi integration có semantics context riêng. HTTP client builder giải quyết HTTP outgoing instrumentation, không bảo đảm propagation tới mọi queue/worker nếu integration đó không được instrument.

## 10. Tùy chỉnh managed builder mà không phá tracing

### 10.1. Tùy chỉnh tại nơi inject

Đối với một API đối tác:

~~~java
public PartnerApiClient(RestClient.Builder builder) {
    this.client = builder
            .baseUrl("https://partner.example.test")
            .defaultHeader("Accept", "application/json")
            .build();
}
~~~

Đây là **constructor snippet thuộc một class đã có field client**, không phải file biên dịch độc lập. Nó giữ lại các customizers Boot đã áp dụng vào builder. Hãy dùng URI templates nếu path có biến và đặt timeouts theo network SLO. Không đưa traceparent, authorization token hoặc tenant ID nhạy cảm vào defaultHeader hardcode.

### 10.2. RestClientCustomizer toàn ứng dụng

Spring Boot 3.3 có **RestClientCustomizer** ở package **org.springframework.boot.web.client**. Khi cần bổ sung một header không nhạy cảm cho mọi RestClient được tạo từ builder Boot:

~~~java
package com.example.httptrace;

import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OutboundClientDefaults {

    @Bean
    RestClientCustomizer userAgentCustomizer() {
        return builder ->
                builder.defaultHeader(
                    "User-Agent", "trace-client-demo/1.0");
    }
}
~~~

Đây là **file tùy chọn, độc lập và biên dịch được** nếu thêm vào cùng project. Customizer được áp dụng vào auto-configured builders, **không đồng nghĩa client tạo bằng RestClient.create tự nhận nó**. Hãy hạn chế customizer global với những thiết lập thật sự dùng chung; basic auth hoặc certificate riêng của đối tác nên đặt vào client tương ứng.

Nếu có nhiều RestClient beans với base URLs khác nhau, giữ builder customization local hoặc clone builder. Đừng dùng một singleton RestClient.Builder mutable rồi liên tục đổi baseUrl trong runtime để gửi đến nhiều host.

### 10.3. Không override ObservationRegistry bằng registry trống

**ObservationRegistry** do Boot quản lý có observation handlers, conventions và tracing integration. Nếu tự tạo:

~~~java
ObservationRegistry registry =
        ObservationRegistry.create();
~~~

đây chỉ là một object registry mới. **Nếu tự dùng nó thay registry đã auto-configured**, các handlers của Boot/Micrometer Tracing có thể không được gắn, khiến span/metric mất. Trong bean ứng dụng hãy **inject ObservationRegistry** từ Spring và giữ auto-configured HTTP client builder. Nếu bạn tạo registry theo use case đặc biệt, cần cấu hình handlers tương đương và test.

### 10.4. Tạo observation nghiệp vụ ở tầng service

Một HTTP client span cho biết outbound duration; nhưng service có thể cần span/metric riêng như "đọc dữ liệu đối tác" bao gồm kiểm tra cache, validate, mapping và retry logic. Ví dụ **class tùy chọn có thể thêm vào demo**:

~~~java
package com.example.httptrace;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ObservedLookupService {

    private final RemoteDirectoryClient client;
    private final ObservationRegistry registry;

    public ObservedLookupService(
            RemoteDirectoryClient client,
            ObservationRegistry registry) {
        this.client = client;
        this.registry = registry;
    }

    public TargetReply lookup() {
        return Observation.createNotStarted(
                "demo.directory.lookup", registry)
                .lowCardinalityKeyValue(
                        "partner", "local-demo")
                .observe(client::fetchTarget);
    }
}
~~~

**Observation.observe(Supplier)** bắt đầu/kết thúc observation và khôi phục scope ngay cả khi code bên trong ném exception theo API tương ứng. Observation nghiệp vụ này có thể tạo span bao ngoài HTTP client span và metric nếu handlers được cấu hình. Không tự bọc lại chính framework HTTP client observation ở cùng vị trí để rồi thấy duplicate spans.

**Low-cardinality key** phải có số giá trị hữu hạn như partner=local-demo. Nếu muốn gắn ID từng request, không đưa userId/email/orderId vào metric tags; cân nhắc **high-cardinality trace attributes** có security review và retention.

## 11. Chuyển trace qua thread và async boundaries

### 11.1. Vì sao mất context?

Micrometer Tracing thường dựa trên **current scope** của thread. Khi request server chuyển sang một thread khác mà **không** propagate context, outbound RestClient dù là managed builder cũng có thể không còn nhìn thấy parent observation. Khi đó nó có thể tạo root span mới thay vì child span.

~~~text
Request thread:
  current trace T
       |
       +-- submit async task without propagation
                    |
                    v
             worker thread:
               no active trace context
                    |
                    v
             managed RestClient call
             may start unrelated trace
~~~

Builder không thể tự đoán parent context đã mất trước khi lời gọi bắt đầu.

### 11.2. ContextPropagatingTaskDecorator

Khi phải tự quản lý Spring TaskExecutor, có thể sử dụng **ContextPropagatingTaskDecorator** của Spring Framework để capture/restore context:

~~~java
package com.example.httptrace;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncObservationConfiguration {
    @Bean
    ThreadPoolTaskExecutor traceAwareExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("trace-worker-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Đây là **file tùy chọn**, không được sử dụng trong lab HTTP đồng bộ ở mục 6 nếu bạn chưa có async task. Nếu dùng nó, phải gửi task qua **chính traceAwareExecutor đó** (hoặc gắn decorator với executor đang được @Async sử dụng), không chỉ khai báo bean rồi hy vọng mọi thread pool tự được instrument.

Một số phiên bản Boot/TaskExecutor auto-config cũng có cách bật propagation thông qua auto config; hãy kiểm tra đúng phiên bản và context boundary. Không truyền một ThreadLocal/Tracer span qua thread bằng static global variable, vì dễ làm lẫn request giữa người dùng và rò rỉ context.

### 11.3. Scheduled jobs không có incoming trace

Một job định kỳ có thể không có parent server span. Khi nó thực hiện outbound HTTP, **tạo trace root mới** là hợp lý. Không xem mọi trace root là lỗi; chỉ coi là sai khi nghiệp vụ đã có parent context đáng lẽ được truyền qua boundary nhưng bị mất.

### 11.4. Retry, async và message queues

- **Retry** có thể tạo nhiều client spans cho các attempts hoặc một logical observation bao quanh retry; phụ thuộc vị trí instrument và library.
- **Circuit breaker** có thể từ chối trước khi phát request; không có outbound HTTP span trong lần từ chối đó là hợp lý.
- **Queue/Kafka** có headers/context propagation riêng; HTTP builder không tự inject context vào message broker.
- **CompletableFuture** với common pool không mặc nhiên mang ThreadLocal context.
- **WebClient/Reactor** cần quan sát Reactor Context và configuration đúng.

Khi debugging, so trace IDs ở từng boundary và biết rõ "đã có HTTP request thật hay chưa".

## 12. Logging, metrics và traces: xem kết quả đúng cách

### 12.1. Log correlation không cần tự chèn trace IDs vào message

Với Micrometer Tracing, Spring Boot 3.3 thường thêm correlation IDs từ MDC vào logs theo format được tài liệu mô tả. Ví dụ hình thức:

~~~text
INFO ... [4bf92f3577b34da6a3ce929d0e0e4736-08beba2a4cf9e1d2] Demo entry started
INFO ... [4bf92f3577b34da6a3ce929d0e0e4736-5c45a01df13d9d7f] Demo target received request
~~~

**Giá trị và format chỉ minh họa**; log output thực tế có timestamp, application name, logger/class và các field khác. Không dùng log pattern này làm golden test y nguyên. Hai log có thể cùng traceId nhưng spanId khác; đó chính là dấu hiệu thông tin phân tán.

**Không dùng session ID, JWT hoặc Authorization header làm trace ID**. Traces và logs có thể lưu lâu và được truy cập bởi nhiều đội.

### 12.2. Metrics theo URI template

Nếu gọi:

~~~java
client.get()
    .uri("/api/orders/{orderId}", 12345)
    .retrieve()
    .toBodilessEntity();
~~~

Đây là **đoạn minh họa thuộc client đã được build**, không phải chương trình chạy riêng. Dùng URI template giúp observation conventions có cơ hội ghi tag **/api/orders/{orderId}** thay vì raw path chứa từng order ID. Nếu tự nối chuỗi full URL như /api/orders/12345, metrics có thể bị **high cardinality** và nổ số series.

Low-cardinality tag ví dụ gồm HTTP method, status family, route template và tên service. Tránh raw query parameters, user ID, email, account number, tenant nếu số giá trị lớn. Với trace span high-cardinality attributes vẫn phải tuân quy định bảo mật.

### 12.3. Metrics không đo từ phía client hay server giống nhau

- **http.client.requests** đo phía caller; bao gồm network và thời gian chờ response theo instrumentation.
- **http.server.requests** đo phía server; không tự bao gồm latency của mạng trước khi request đến server.
- Nếu client timeout, server có thể vẫn xử lý request và ghi metric thành công sau đó; hai phía có thể bất đồng status.
- Proxy/gateway có thời gian queue, retry, TLS handshake, connection reuse riêng. Distributed tracing giúp phân tích đường đi nhưng không có nghĩa mọi clock đều đồng bộ đến từng nanosecond.

### 12.4. Exporter và collector

Span được tạo trong ứng dụng có thể được exporter gửi **bất đồng bộ theo batch**. Khi Zipkin không khả dụng, trace spans có thể bị drop sau retry/buffer policy; ứng dụng HTTP vẫn có thể trả response. Không đồng nhất health endpoint trả UP với trace pipeline hoạt động. Production cần giám sát:
- exporter errors/dropped spans;
- collector availability/backpressure;
- sampling rate và serviceName;
- network TLS/authentication tới backend;
- log correlation và trace search latency;
- chi phí lưu trữ / retention.

Không gửi body hoặc token của user vào tracing backend để "debug dễ hơn".

## 13. Kịch bản kiểm chứng thứ tự từng bước

### 13.1. Xác minh dependencies và bean builder

1. Maven build thành công với Java 17.
2. Trong Spring ApplicationContext có RestClient.Builder auto-configured.
3. RemoteDirectoryClient constructor nhận builder, không tự gọi static factory.
4. Actuator được bật và HTTP client metric hiện sau request.
5. Micrometer Tracing bridge + exporter có trên classpath nếu kiểm tra distributed trace.
6. Zipkin backend chạy cổng 9411 nếu muốn xem span tree.

Nếu /demo/entry báo 500 vì không kết nối được localhost:8080, kiểm tra app đang chạy trên cổng nào và baseUrl trong client; đây không phải lỗi tracing.

### 13.2. Positive trace test

1. Gọi GET /demo/entry từ curl.
2. Nhận JSON 200 và so **entryTraceId == targetTraceId**.
3. Trên Zipkin tìm service trace-client-demo.
4. Xác minh có incoming server span, outbound client span và target server span trong cùng trace.
5. Trong logs lọc theo trace ID và thấy các log của hai endpoints.
6. Truy vấn /actuator/metrics/http.client.requests sau request để xem metric.

Điểm trọng tâm: request HTTP thật giữa hai endpoints đi qua builder được quản lý, không phải người viết tự copy một trace ID vào response từ code.

### 13.3. Negative comparison có kiểm soát

Trong **bản sao bài lab** (không sửa production), có thể tạm thay constructor RemoteDirectoryClient bằng:

~~~java
public RemoteDirectoryClient() {
    this.client = RestClient.create(
            "http://localhost:8080");
}
~~~

Đây chỉ là **constructor snippet thay thế để so sánh**, không phải class riêng. Nó có thể gọi HTTP thành công, nhưng do không dùng builder Boot, auto Observation/customizers không mặc định được áp dụng. Với tracing config lab, nhiều khả năng /demo/target sẽ nhận **trace root khác** vì không có trace context trên request outbound, và HTTP client observation có thể vắng. **Không dùng bài so sánh để khẳng định mọi RestClient.create đều không thể instrument**: nếu framework/agent bên ngoài inject instrumentation riêng thì behavior có thể khác.

Sau khi hiểu, quay lại managed builder. Không thay đổi code bài lab đã deploy hay cấu hình production chỉ để cố tạo trace mismatch.

### 13.4. Trường hợp đầu vào có traceparent

1. Gửi request có traceparent W3C từ curl.
2. Xác minh entryTraceId có cùng trace ID đã gửi nếu tracer consume W3C đúng.
3. Xác minh targetTraceId vẫn bằng entryTraceId.
4. Trong Zipkin, các span thuộc cùng trace với quan hệ parent/child hợp lý.
5. Không dùng traceparent từ client ngoài để đánh giá authentication/authorization.

## 14. Lỗi thường gặp và hướng sửa

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| RestClient gọi được HTTP nhưng không có **http.client.requests** | Client được tạo bằng RestClient.create/builder riêng; thiếu Actuator/registry | Inject RestClient.Builder do Boot quản lý, kiểm tra Actuator và métrics configuration. |
| Có metrics nhưng không có trace ID | Thiếu Micrometer Tracing bridge/tracer hoặc sampling/exporter | Kiểm tra POM, management.tracing.enabled, sampling, tracer bean. |
| trace IDs khác nhau giữa caller và downstream | Không inject context, proxy bỏ headers, format W3C/B3 không tương thích | Kiểm tra managed builder và actual traceparent trên outbound/ingress. |
| @RestClientTest không xuất spans tới Zipkin | Test slice không khởi động reporting components | Test HTTP client contract riêng; dùng @AutoConfigureObservability và runtime HTTP test khi cần. |
| Zipkin không có trace nhưng API 200 | Collector chưa chạy, exporter lỗi, sampling, service name/time window | Xem exporter logs, endpoint, sampling, collector health. |
| Span IDs khác nhưng trace ID giống | Hành vi bình thường của parent/child spans | Xem cây span, đừng ép span ID trùng. |
| Header traceparent hợp lệ nhưng bị bỏ qua | Backend chỉ consume B3, proxy lọc, format parser không chấp nhận | Kiểm tra management.tracing.propagation.consume/produce/type. |
| Mất trace sau @Async/CompletableFuture | ThreadLocal scope không được propagate qua executor | ContextPropagatingTaskDecorator/executor instrumentation phù hợp. |
| Mất trace trong Reactor pipeline | Context không tự khôi phục qua operators/custom schedulers | spring.reactor.context-propagation=auto và kiểm tra Reactor Context. |
| Duplicate HTTP client spans | Java agent + Micrometer cùng instrument, custom interceptor tạo span kép | Chọn một owner, điều chỉnh instrumentation và kiểm tra span tree. |
| Metrics cardinality tăng vọt | URI tag dùng raw IDs/query hoặc custom user tags | Dùng URI templates, bỏ PII/ID khỏi low-cardinality tags. |
| request timeout nhưng server báo 200 | Client timeout trong lúc server vẫn chạy | So metrics client/server, network/proxy timeline. |
| Outbound calls từ RestTemplate mới tạo mất trace | new RestTemplate() bypass auto builder | Dùng RestTemplateBuilder của Boot. |
| WebClient.create không trace | Không áp dụng WebClient.Builder customizers | Inject managed WebClient.Builder. |
| Tracing exporter gây nhiều WARN | Backend không khả dụng hoặc cấu hình sai | Dùng collector reachable, chặn egress, giới hạn retries/batching phù hợp. |
| Lỗi sau nâng Spring Boot major | Package API, builder config và actuator property thay đổi | Mở tài liệu đúng version; Boot 3.3 khác Boot 4. |
| Logs không có traceId | Ngoài active span, instrumentation thiếu hoặc log format bị override | Kiểm tra Micrometer Tracing MDC, log pattern và scope. |

**Cách debug có thứ tự:** bắt đầu từ **đường tạo client** → observation instrumentation → tracer activation → active span → outbound propagation headers → downstream extraction → sampling/exporter/backend. Không đổ lỗi cho collector trước khi chắc chắn traceparent đã rời khỏi caller.

## 15. Bảo mật và vận hành

### 15.1. Thông tin nào được phép đưa vào trace?

Chỉ đưa các thuộc tính cần thiết để vận hành:
- service name, environment, route template;
- HTTP method, status, outcome/exception class đã được kiểm soát;
- peer service category hoặc partner code có cardinality nhỏ;
- correlation ID độc lập credential;
- các business tags đã được kiểm tra privacy/security.

Không đưa:
- Authorization bearer tokens, Basic credentials;
- Cookie, Set-Cookie, JSESSIONID/SESSION;
- password, API key, refresh token, CSRF token;
- card number, tài khoản ngân hàng, dữ liệu y tế và payload cá nhân;
- query string chứa thông tin nhạy cảm;
- request/response body mặc định của mọi HTTP call.

**Trace backend là một data store có rủi ro bảo mật riêng**: áp dụng IAM, TLS, retention, masking, audit và phân quyền.

### 15.2. Không tin traceparent làm bằng chứng identity

Client ngoài có thể tự tạo traceparent hoặc trace ID. Backend không được dựa vào nó để cấp quyền hay bỏ auth checks. Để tránh spoofing và trace bão hòa, ingress có thể giới hạn headers, sampling và rate limits theo trust boundary; cần giữ consistency propagation theo chính sách.

### 15.3. Reliability của HTTP client khác observability

**Tracing không thay thế** timeout, retry, circuit breaker hoặc idempotency:
- Set connection/read timeout phù hợp với service SLO.
- Retry chỉ khi request an toàn/idempotent và có backoff/jitter/budget.
- Không tự retry POST có side effect khi không có idempotency key.
- Bảo vệ DNS, TLS verification, proxy, SSRF khi URL động từ input user.
- Phân biệt 4xx do nghiệp vụ với 5xx/timeout và network error.
- Theo dõi pool saturation/connection reuse trong HTTP client runtime.

Builder của Boot có thể được tùy chỉnh thêm timeout/SSL/request factory nhưng phải giữ observation customizers; không dùng trust-all SSLContext để "gỡ lỗi kết nối".

### 15.4. Sampling và chi phí

Một trace có thể có hàng trăm spans. **100% sampling** trên production high traffic có thể gây chi phí và lưu trữ lớn. Lựa chọn sampling theo mục tiêu:
- demo/staging traffic nhỏ: 1.0 để dễ tìm;
- production: tỷ lệ cân bằng theo nhu cầu và chính sách;
- giữ correlation logs đúng;
- không giả định mọi request đều được lưu;
- cân nhắc error-focused sampling hoặc tail sampling nếu hệ thống collector hỗ trợ và đã đánh giá.

Khi tracing bị giảm sample rate, metrics tổng hợp vẫn rất quan trọng để theo dõi SLO.

### 15.5. Quản lý Actuator

Trong project lab, **/actuator/metrics** được expose để học. Với production, không tự bật thêm **env, configprops, heapdump, httpexchanges** ra Internet. Dùng management port/network boundary, authentication và export metrics qua Prometheus/monitoring được phép.

## 16. Checklist chất lượng trước khi merge

- [ ] Dùng RestClient.Builder / RestTemplateBuilder / WebClient.Builder **được Spring Boot auto-configured** cho mọi outbound HTTP cần observation.
- [ ] Không tạo RestClient/RestTemplate/WebClient bằng static factory rồi giả định tracing tự hoạt động.
- [ ] Spring Boot Actuator và metrics registry/ObservationRegistry được cấu hình đúng.
- [ ] Có Micrometer Tracing bridge + tracer/exporter phù hợp khi cần distributed trace.
- [ ] Sampling dev đủ cao để quan sát, sampling production theo budget.
- [ ] Inbound và outbound spans giữ cùng trace ID, có parent/child relation.
- [ ] Propagation header W3C/B3 được hai đầu và proxy hỗ trợ, không bị lọc/ghi đè.
- [ ] Client HTTP tags sử dụng URI template, không raw IDs/query PII.
- [ ] Logs có traceId/spanId correlation mà không lộ token/cookie.
- [ ] Builder customizers được áp dụng additive, không override registry/builder trống.
- [ ] Nếu dùng @Async/Reactor, kiểm tra context propagation trên thread/scheduler thật.
- [ ] Metrics **http.client.requests** xuất hiện sau request, được so sánh với server metrics.
- [ ] Zipkin/OTLP collector vận hành và exporter errors/drop được giám sát.
- [ ] @RestClientTest kiểm tra URL, method, JSON mapping; HTTP integration test kiểm tra trace propagation thực.
- [ ] Có timeouts, retry/backoff/idempotency và TLS verification phù hợp.
- [ ] Actuator endpoints được giới hạn trong production.
- [ ] Không có credentials hoặc request body nhạy cảm trong span attributes/baggage/logs.
- [ ] Kiểm tra lại API package và property names khi đổi Spring Boot major version.

## 17. Câu hỏi tự kiểm tra

**1. Có thể tạo RestClient bằng RestClient.create() và đương nhiên có trace propagation của Spring Boot không?** Không. Cách tạo trực tiếp không mặc định đi qua auto-configured RestClient.Builder và các customizers cần thiết.

**2. Để dùng RestTemplate có metrics/traces thì inject gì?** Inject **RestTemplateBuilder** do Spring Boot tự cấu hình, sau đó build RestTemplate. Không dùng new RestTemplate() nếu cần auto instrumentation.

**3. Vì sao hai span ID khác nhau nhưng vẫn thuộc một trace?** Chúng đại diện những thao tác khác nhau, liên kết qua parent/child và có cùng trace ID.

**4. Nếu thấy http.client.requests nhưng không có spans trong Zipkin thì builder sai chắc chắn không?** Không. Có thể thiếu tracer, sampling không chọn trace, exporter/collector lỗi hoặc thời gian tìm không đúng.

**5. Propagation traceparent là header xác thực service không?** Không. Caller có thể tạo nó; authentication và authorization độc lập.

**6. @RestClientTest có tự chứng minh trace propagation giữa hai HTTP server thật không?** Không. Test slice dùng mock request server; cần integration test với network/tracer.

**7. Vì sao gọi managed RestClient trong CompletableFuture vẫn có thể tạo trace root mới?** Parent context có thể đã bị mất khi đổi thread nếu không propagate ThreadLocal/observation context.

**8. Khi nâng từ Boot 3.3 lên major mới, có thể dùng nguyên RestTemplateBuilder package không?** Không nên giả định. Kiểm tra tài liệu/javadoc đúng version.

**9. Trace backend nên lưu password/authorization header để debug không?** Không. Đây là dữ liệu nhạy cảm; trace/log phải được giới hạn, mask và bảo vệ.

**10. Bật 100% sampling mãi mãi có phải cách tốt nhất không?** Không. Nó hợp lab nhưng production cần cân bằng SLO, cost, privacy và khả năng lưu trữ.

## 18. Tài liệu chính thức

1. [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): RestClient.Builder, RestTemplateBuilder, WebClient.Builder, prototype và customization.
2. [Spring Boot 3.3 — HTTP Client Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): http.client.requests và observation customizers.
3. [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html): Micrometer Tracing, auto-configured builders, propagation, sampling, exporters, MDC correlation.
4. [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html): ObservationRegistry, low/high-cardinality key values và Reactor Context.
5. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @RestClientTest, MockRestServiceServer và @AutoConfigureObservability.
6. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): management.tracing.*, propagation formats và actuator settings.
7. [Spring Framework 6.1 — HTTP Client Observability](https://docs.spring.io/spring-framework/reference/6.1/integration/observability.html): HTTP client observation context, conventions và handler semantics.
8. [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent, tracestate và format/semantics của distributed tracing headers.

**Kết luận:** Với ứng dụng Spring Boot cần quan sát outbound HTTP, **hãy inject builder do Boot quản lý** thay vì khởi tạo RestClient, RestTemplate hay WebClient thủ công. Điều này giữ auto-configuration và observation customizers, cho phép **http.client.requests**, Micrometer Tracing và propagation context hoạt động cùng nhau khi dependencies được thiết lập đúng. Kiểm tra trace bằng **cùng trace ID qua nhiều span**, parent/child links và dữ liệu từ collector; đồng thời kiểm tra logs/metrics, thread boundaries, sampling và bảo mật trước khi đưa vào production.