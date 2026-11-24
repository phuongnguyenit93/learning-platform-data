# Baggage là gì? Truyền ngữ cảnh và liên kết logs trong Spring Boot

Một request tạo đơn hàng bắt đầu ở `order-service`, gọi `inventory-service` rồi đi tiếp tới `payment-service`. Trace ID giúp các service nhận ra spans thuộc cùng một trace, nhưng đôi khi đội vận hành còn cần một số thông tin ngữ cảnh xuyên suốt hành trình, chẳng hạn kênh xử lý `web` hay `batch`, mã vùng đã chuẩn hóa hoặc loại luồng nghiệp vụ. **Baggage** là cơ chế mang những cặp key-value ngữ cảnh qua ranh giới service để các thành phần downstream có thể sử dụng khi được cấu hình.

Trong module **SPRING_BOOT_OBSERVABILITY**, baggage cần được hiểu cùng Micrometer Observation, metrics, logs và distributed tracing. Trace context định danh và nối các spans; baggage truyền thêm một lượng nhỏ context; span attributes mô tả một span; MDC hỗ trợ đưa correlation fields vào logs. Chúng liên quan nhưng không thay thế lẫn nhau. Việc truyền baggage cũng phải kiểm soát chặt dữ liệu nhạy cảm, kích thước header, allowlist và cardinality.

Bài thuộc chương **Baggage và correlation**, tập trung vào khái niệm nền tảng **Baggage là gì**, cách W3C Baggage được propagate, tích hợp Spring Boot/Micrometer Tracing, liên kết log, kiểm thử và điều tra sự cố trong môi trường thực.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích baggage và phân biệt nó với trace ID, span ID, span attributes, MDC và metric labels.
2. Mô tả cách baggage được mã hóa vào HTTP header `baggage` theo W3C Baggage.
3. Cấu hình các field baggage được phép truyền và field được đưa vào logging correlation.
4. Tạo và đọc baggage trong ứng dụng Spring Boot sử dụng Micrometer Tracing.
5. Kiểm tra propagation giữa hai service, kể cả khi chuyển qua HTTP client/server hoặc executor.
6. Thiết kế allowlist, giới hạn kích thước, thời gian sống và chính sách dữ liệu an toàn.
7. Biết khi nào nên dùng baggage, span attributes, logs hoặc metrics để giải quyết một câu hỏi vận hành.

## 1. Baggage là gì?

**Baggage** là tập hợp các cặp **key-value** được gắn với một trace context và có thể được truyền qua các ranh giới xử lý/service. Các thành phần nhận context có thể đọc baggage để bổ sung ngữ cảnh cho xử lý, logs hoặc spans theo thiết kế.

Ví dụ một luồng đặt hàng:

~~~text
order-service
  traceId = 4bf92f3577b34da6a3ce929d0e0e4736
  baggage:
    orders.channel = web
    deployment.region = ap-southeast
        |
        | HTTP request + trace context + baggage
        v
inventory-service
  đọc orders.channel = web
        |
        | HTTP request + trace context + baggage
        v
payment-service
  đọc orders.channel = web
~~~

Hai service có thể dùng cùng baggage value trong lúc xử lý một trace. Tuy nhiên, **baggage không tự được ghi vào logs, metrics hay mọi span**. Cần cấu hình hoặc code rõ ràng cho từng mục đích. Nếu service nhận không có baggage propagator/accessor tương ứng, hoặc field không nằm trong allowlist, giá trị có thể không tới nơi.

### 1.1. Vì sao cần baggage?

Một số thông tin ngữ cảnh nhỏ có thể hữu ích xuyên suốt nhiều service:

| Ví dụ key | Value ví dụ | Mục đích |
| --- | --- | --- |
| `orders.channel` | `web` hoặc `batch` | Phân biệt loại luồng xử lý |
| `deployment.region` | `ap-southeast` | Nhận biết vùng đã chuẩn hóa |
| `experiment.variant` | `control` hoặc `treatment` | Hỗ trợ phân tích một thí nghiệm đã được phê duyệt |
| `tenant.tier` | `standard` hoặc `premium` | Phân nhóm chính sách nếu được phép |
| `workflow.name` | `order-create` | Ngữ cảnh luồng nghiệp vụ có tập giá trị hữu hạn |

Những ví dụ này chỉ nên được truyền khi downstream thật sự cần. Không sử dụng baggage như một kho chứa dữ liệu request, payload hoặc trạng thái nghiệp vụ cần lưu lâu dài.

### 1.2. Baggage không phải trace ID

**Trace ID** là định danh của trace. Nó giúp backend tìm tất cả spans thuộc cùng trace. **Baggage** là dữ liệu bổ sung có thể được propagate cùng trace context. Trace ID thường được tạo và quản lý bởi tracing system; baggage thường được code hoặc policy thiết lập.

Ví dụ:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
baggage: orders.channel=web,tenant.tier=standard
~~~

Hai header có vai trò khác nhau:

- `traceparent` chứa phiên bản, trace ID, parent ID và trace flags để liên kết spans.
- `baggage` mang những key-value được cho phép truyền sang downstream.

Nếu chỉ có baggage mà không có trace context, hệ thống vẫn có thể đọc thông tin baggage nhưng không thể chỉ nhờ vậy dựng cây parent-child span. Ngược lại, một trace hoàn toàn có thể hoạt động mà không cần baggage.

## 2. Baggage, span attributes, MDC và metric labels

Đây là bốn khái niệm rất dễ bị dùng lẫn:

| Khái niệm | Nơi tồn tại | Mục đích | Có tự truyền qua service không? |
| --- | --- | --- | --- |
| **Trace context** | Context của tracer, thường serialize thành `traceparent` | Liên kết spans | Có, khi propagator và HTTP/messaging instrumentation hoạt động |
| **Baggage** | Context gắn với trace, serialize theo `baggage` | Truyền một số key-value ngữ cảnh | Có, khi field được cấu hình/cho phép và propagator hoạt động |
| **Span attributes** | Metadata của một span | Mô tả thao tác cụ thể | Không mặc nhiên; chỉ khi code/propagation bổ sung riêng |
| **MDC/log correlation** | Context logging của execution hiện tại | Ghi trace/span ID hoặc correlation fields trong logs | Không tự bảo đảm; phụ thuộc logging integration và context propagation |
| **Metric labels** | Identity của time series | Nhóm dữ liệu tổng hợp | Không truyền theo trace; được gắn bởi instrumentation/registry |

Ví dụ: `orders.channel=web` có thể được đặt thành baggage để service downstream đọc. Nếu muốn tìm trên trace backend, code có thể copy sang span attribute. Nếu muốn hiển thị trong log, cấu hình correlation fields/MDC. Nếu muốn đưa vào metrics, cần đánh giá nó có tập giá trị thấp và ổn định hay không.

**Không copy toàn bộ baggage vào mọi nơi.** Mỗi đích có yêu cầu và rủi ro khác nhau. Một baggage field an toàn để truyền nội bộ chưa chắc là metric label tốt hoặc được phép xuất thành log.

### 2.1. Baggage không thay thế span attributes

Baggage diễn tả context mà nhiều service có thể cần đọc; span attributes mô tả một span. Baggage được thêm sau khi span đã bắt đầu không nhất thiết xuất hiện trên span đó. Muốn metadata nằm trong trace, hãy gắn attribute vào đúng span hoặc dùng instrumentation/convention phù hợp.

### 2.2. Baggage không thay thế MDC

MDC là cơ chế logging để gắn các giá trị vào log event. Một số integration có thể tự thêm trace ID/span ID vào MDC, và Spring Boot có thể ánh xạ correlation fields được cấu hình từ baggage. Nếu logging xảy ra ngoài active context, hoặc async context bị mất, MDC có thể không có các giá trị mong đợi.

### 2.3. Baggage không phải metric label

Một field baggage có nhiều giá trị khác nhau như request ID, customer ID hoặc email sẽ không phù hợp để trở thành metric label. Nó có thể làm số time series tăng theo traffic và lộ dữ liệu nhạy cảm. Metrics nên dùng tập giá trị nhỏ như `orders.channel=web|batch`; truy vấn một request cụ thể nên dựa vào trace ID/log correlation và dữ liệu được phép.

## 3. W3C Baggage và HTTP propagation

W3C Baggage định nghĩa cách serialize một danh sách key-value vào header HTTP `baggage`. Một ví dụ:

~~~http
baggage: orders.channel=web,tenant.tier=standard
~~~

Khi một service nhận header và tạo downstream request có propagation, các baggage fields được phép có thể tiếp tục xuất hiện ở request tiếp theo. Đây là một cơ chế **propagation**, không phải tự động gửi dữ liệu đến trace backend.

### 3.1. Ví dụ ba service

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Payment as payment-service
    Client->>Order: POST /orders
    Note over Order: Tạo trace context
    Order->>Order: Gắn baggage orders.channel=web
    Order->>Inventory: HTTP + traceparent + baggage
    Note over Inventory: Extract context và đọc baggage
    Inventory->>Payment: HTTP + traceparent + baggage
    Note over Payment: Đọc orders.channel=web
    Payment-->>Inventory: Result
    Inventory-->>Order: Result
    Order-->>Client: Response
~~~

Trong ví dụ, nếu cả HTTP client/server đã được instrument và W3C propagator được dùng, trace context và baggage có thể nối qua các service. Nếu một service xóa header hoặc dùng propagator khác mà không chuyển đổi, đường truyền có thể bị đứt.

### 3.2. Nhiều giá trị và encoding

W3C Baggage hỗ trợ danh sách member theo cú pháp riêng, có quy tắc về ký tự, encoding và metadata tùy chọn. Ví dụ đơn giản thường đủ để minh họa:

~~~http
baggage: orders.channel=web,experiment.variant=treatment
~~~

Trong môi trường thực, **không tự nối chuỗi header bằng phép cộng tùy ý**. Dùng API baggage/propagator của tracing stack để xử lý encoding, escaping, multiple headers và giới hạn kích thước đúng chuẩn.

Một giá trị baggage có thể được encode khi đi qua HTTP; vì vậy không nên giả định chuỗi nhận được luôn giống byte-for-byte với chuỗi ban đầu. Hãy kiểm tra giá trị đã parse trong service nhận.

### 3.3. Baggage không phải dữ liệu tin cậy

Header do client gửi có thể bị giả mạo. Một service không nên tin `tenant.tier=premium` chỉ vì nó xuất hiện trong baggage. Nếu thông tin có ảnh hưởng đến quyền hạn, giá, tenant isolation hoặc quyết định bảo mật, phải xác thực nó từ nguồn có thẩm quyền; baggage chỉ là phương tiện mang context.

Đặc biệt, không dùng baggage làm cơ chế truyền authorization, session hoặc security principal. Không cho phép request bên ngoài tự chỉ định tùy ý keys/values rồi propagate xuyên toàn bộ hệ thống.

## 4. Spring Boot và Micrometer Tracing

Spring Boot tích hợp Micrometer Observation và Micrometer Tracing. Với tracing bridge phù hợp, ứng dụng có thể truy cập API tracer/baggage và dùng property của Spring Boot để chỉ rõ những field được propagate hoặc correlation.

Dependency minh họa với Spring Boot 3.x và OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Phiên bản dependency nên theo BOM của dự án. Các property dưới đây dựa trên nhóm cấu hình Spring Boot 3.x; cần xác nhận theo đúng phiên bản ứng dụng khi nâng cấp.

### 4.1. Chọn baggage fields được propagate

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
    baggage:
      remote-fields:
        - orders.channel
        - deployment.region
      correlation:
        fields:
          - orders.channel
          - deployment.region
~~~

Giải thích:

- `management.tracing.baggage.remote-fields` khai báo các field baggage được phép gửi qua ranh giới service theo hỗ trợ của Spring Boot version.
- `management.tracing.baggage.correlation.fields` khai báo field baggage cần đưa vào logging correlation/MDC theo cấu hình tích hợp.
- `sampling.probability` là xác suất sampling ví dụ; **sampling trace không quyết định baggage có được đọc trong code hay không**, nhưng có thể ảnh hưởng span data được export.

Hai danh sách trên phục vụ hai mục đích khác nhau: **remote propagation** và **log correlation**. Chỉ thêm field vào remote list không đồng nghĩa nó tự xuất hiện trong logs. Chỉ thêm vào correlation fields không đồng nghĩa nó sẽ được gửi sang service tiếp theo.

Không truyền mọi field chỉ vì framework cho phép. Hãy giữ allowlist nhỏ, ổn định, có chủ sở hữu và có lý do vận hành rõ ràng.

### 4.2. Truy cập baggage qua Micrometer Tracer API

Với Micrometer Tracing, có thể tạo baggage trong scope của thao tác:

~~~java
package com.example.orders.tracing;

import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class OrderChannelService {
    private final Tracer tracer;

    public OrderChannelService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void processWebOrder() {
        try (BaggageInScope baggage =
                     tracer.createBaggageInScope("orders.channel", "web")) {
            processOrder();
        }
    }

    private void processOrder() {
        // Gọi các bean/dependency đã được instrument phù hợp.
    }
}
~~~

`createBaggageInScope` tạo baggage trong scope hiện tại và scope đóng khi ra khỏi `try-with-resources`. Điều này giúp tránh để giá trị ngữ cảnh rò rỉ sang thao tác tiếp theo khi thread được tái sử dụng.

Đây là ví dụ API Micrometer Tracing; cách baggage được propagate phụ thuộc bridge, propagator và cấu hình `remote-fields`. Nếu API cụ thể khác theo phiên bản đang dùng, hãy dựa vào contract của Micrometer Tracing version được Spring Boot quản lý.

### 4.3. Đọc baggage trong service downstream

Khi service nhận đã extract baggage vào context và ứng dụng đang có tracer phù hợp, có thể đọc giá trị hiện tại:

~~~java
import io.micrometer.tracing.Baggage;
import io.micrometer.tracing.Tracer;

public String currentChannel(Tracer tracer) {
    Baggage baggage = tracer.getBaggage("orders.channel");
    return baggage == null ? "unknown" : baggage.get();
}
~~~

Đoạn này minh họa cách đọc baggage hiện hành; kiểm tra kiểu trả về/API trên version Micrometer Tracing của dự án. **Không dùng giá trị baggage để cấp quyền** hoặc thay thế xác thực. Nếu không có field, xử lý fallback một cách tường minh thay vì giả định giá trị luôn tồn tại.

### 4.4. Dùng @ConfigurationProperties cho allowlist nghiệp vụ

Ngoài danh sách propagation của framework, ứng dụng nên quản lý những field nào được phép tạo ở tầng nghiệp vụ. Ví dụ:

~~~java
package com.example.orders.tracing;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.Set;

@ConfigurationProperties(prefix = "app.observability.baggage")
public record BaggagePolicy(Set<String> allowedChannels) {
    public BaggagePolicy {
        allowedChannels = allowedChannels == null
                ? Set.of("web", "batch")
                : Set.copyOf(allowedChannels);
    }
}
~~~

Ví dụ này chỉ minh họa chính sách giá trị channel; cần đăng ký configuration properties theo cách ứng dụng đang dùng (ví dụ `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`). Không đưa tên key/value tùy ý từ request vào baggage.

## 5. Baggage scope, thread và async processing

Baggage thường gắn với current tracing context. Nếu một request xử lý đồng bộ, scope có thể được sử dụng trong các lời gọi lồng nhau. Khi chuyển thread, executor hoặc reactive context, phải bảo đảm context được truyền và phục hồi đúng.

### 5.1. Tránh rò rỉ baggage khi tái sử dụng thread

Ví dụ không an toàn về lifecycle:

~~~java
// Ý tưởng sai: đặt context mà không bảo đảm đóng scope.
tracer.createBaggageInScope("orders.channel", "web");
executor.execute(this::processOrder);
~~~

Thread pool tái sử dụng thread. Nếu scope không được đóng hoặc context không được restore, một thao tác sau có thể nhìn thấy giá trị từ thao tác trước. Dùng try-with-resources và cơ chế context propagation đã được framework hỗ trợ.

### 5.2. ContextPropagatingTaskDecorator

Với Spring Framework 6.1+ và Micrometer Context Propagation, một executor Spring có thể dùng `ContextPropagatingTaskDecorator` khi các context accessors cần thiết đã được đăng ký:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerConfiguration {
    @Bean
    ThreadPoolTaskExecutor baggageAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Decorator giúp capture/restore context được hỗ trợ qua task. Không nên giả định nó tự truyền mọi loại state tùy chỉnh; xác minh tracer, baggage accessor, Spring version và executor thực tế.

### 5.3. Reactor và messaging

Reactor có execution context riêng và có thể đổi thread. Dùng cơ chế context propagation phù hợp với Spring/Reactor thay vì phụ thuộc trực tiếp vào thread-local. Với Kafka/RabbitMQ, producer/consumer instrumentation hoặc message headers cần hỗ trợ inject/extract trace context và baggage.

Batch consumer có thể xử lý nhiều messages đến từ nhiều traces. Không phải lúc nào một baggage context cũng đại diện được cho tất cả message trong batch; cần xác định rõ chọn context nào, xử lý từng message riêng hay dùng span links. Không trộn tùy tiện baggage của message này sang message khác.

## 6. Baggage và log correlation

Một lợi ích thực tế của baggage là mang một số context đã được cho phép tới downstream, sau đó đưa chúng vào log correlation để việc lọc logs dễ hơn. Tuy nhiên, trace ID/span ID vẫn là định danh chính để mở một trace cụ thể; baggage là thông tin bổ sung.

Ví dụ log có cấu trúc:

~~~text
2026-11-22T09:15:10Z INFO service=inventory-service
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7 orders.channel=web event=reservation_started
~~~

Trong Spring Boot, logging integration có thể đưa trace ID/span ID vào MDC/pattern. Baggage correlation fields có thể thêm các field được cấu hình. Format cuối cùng tùy logging framework và pattern/layout.

### 6.1. Correlation trong logging pattern

Ví dụ với Logback pattern:

~~~yaml
logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-},channel=%X{orders.channel:-}]"
~~~

Đây là một pattern minh họa. Baggage key trong MDC có thể được chuẩn hóa khác tùy integration; kiểm tra một log event thật để xác nhận chính xác tên MDC key. Không đưa baggage values vào pattern một cách đại trà vì có thể log dữ liệu nhạy cảm.

### 6.2. Trace ID và baggage giải quyết hai kiểu truy vấn

| Nhu cầu | Dữ liệu phù hợp |
| --- | --- |
| Mở trace của đúng request | Trace ID |
| Xác định span cụ thể trong trace | Span ID |
| Lọc log theo thao tác đang xử lý | Trace/span ID và các log fields đã được cho phép |
| Phân nhóm luồng web/batch qua service | Baggage field đã chuẩn hóa, nếu cần |
| Phân tích số lượng request theo channel | Metric label low-cardinality |
| Tìm request theo order ID | Log/tracing search đã được bảo vệ; không dùng metric label |

Không dùng baggage làm khóa truy vấn duy nhất nếu một giá trị có thể áp dụng cho hàng nghìn requests. Baggage là context chung, không bảo đảm duy nhất.

## 7. Baggage, cardinality và bảo mật

Baggage có thể được serialize vào header HTTP và truyền qua nhiều service, proxy, gateway và logs. Một field được đưa vào baggage có thể mở rộng phạm vi lộ dữ liệu. Vì vậy cần **allowlist và giới hạn**.

| Dữ liệu | Đánh giá | Hành động |
| --- | --- | --- |
| `orders.channel=web` | Tập giá trị thấp, không nhạy cảm trong ví dụ | Có thể cho phép nếu downstream cần |
| `deployment.region=ap-southeast` | Giá trị chuẩn hóa | Có thể cho phép theo policy |
| `experiment.variant=treatment` | Ngữ cảnh phân tích | Chỉ truyền khi được phê duyệt |
| Customer email | Dữ liệu cá nhân | Không truyền mặc định |
| Access token/cookie/password | Bí mật xác thực | Tuyệt đối không đưa vào baggage |
| Raw order ID/request ID | Nhiều giá trị, có thể định danh | Hạn chế; không tự động propagate rộng |
| Request/response body | Lớn, có thể chứa dữ liệu nhạy cảm | Không truyền trong baggage |
| Security role/tenant privilege từ client | Có thể bị giả mạo | Không dùng làm căn cứ cấp quyền |

### 7.1. Baggage có thể làm tăng kích thước header

HTTP headers có giới hạn ở client, proxy, load balancer và server. Nếu thêm quá nhiều key-value hoặc values rất dài, request có thể vượt giới hạn và bị từ chối (ví dụ HTTP 431 hoặc lỗi gateway tùy hạ tầng).

Nên áp dụng:

1. Giữ số field nhỏ, chỉ dùng trường hợp downstream thực sự cần.
2. Đặt giới hạn độ dài key/value và tổng dung lượng baggage.
3. Không truyền body, JSON lớn hoặc danh sách item.
4. Tránh nhân bản cùng dữ liệu qua nhiều headers.
5. Kiểm tra behavior khi gateway strip hoặc truncate headers; không giả định mọi proxy giữ nguyên mọi metadata.

### 7.2. Trust boundary và header injection

Một client ngoài hệ thống có thể tự gửi:

~~~http
baggage: tenant.tier=premium,orders.channel=internal
~~~

Nếu backend tin các giá trị này để thay đổi giá, quyền hoặc dữ liệu được trả, hệ thống có thể bị lạm dụng. Tại trust boundary:

- Chỉ nhận những baggage fields thực sự được phép.
- Xóa hoặc ghi đè các field do client tự gửi nếu chúng không đáng tin.
- Tự xác định lại giá trị từ nguồn có thẩm quyền.
- Không propagate nguyên trạng header không được kiểm soát.
- Không dùng baggage thay thế authentication, authorization hoặc tenant isolation.

**Baggage là metadata không đáng tin cho quyết định bảo mật**, trừ khi được xác minh độc lập theo một hợp đồng tin cậy.

### 7.3. Cardinality và chi phí

Baggage không trực tiếp tạo time series. Nhưng nếu mọi service copy baggage values thành span attributes, logs hoặc metric labels thì chi phí có thể tăng:

- High-cardinality span attributes làm tăng dung lượng trace và chi phí indexing.
- Baggage được copy vào MDC làm log volume và khả năng lộ dữ liệu tăng.
- Baggage được đưa vào metric labels có thể tạo hàng loạt series.

Ví dụ `orders.channel=web|batch` có tập giá trị nhỏ; `request.id` có thể đổi mỗi request. Nếu cần truy vấn request cụ thể, dùng trace ID hoặc log correlation thay vì metric label. Không cần gửi request ID qua baggage chỉ để tái tạo trace ID.

## 8. Khi nào nên dùng baggage và khi nào không?

| Yêu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Liên kết spans thuộc cùng request | Trace context | Đây là mục đích của trace/span IDs |
| Truyền channel đã chuẩn hóa sang downstream | Baggage | Nhiều service có thể cần đọc cùng context |
| Mô tả lỗi của một span | Span event/status/attributes | Metadata thuộc thao tác cụ thể |
| Ghi trace ID vào logs | Logging correlation/MDC | Hỗ trợ tìm trace từ log |
| Tính tỷ lệ request theo channel | Metric label low-cardinality | Có thể tổng hợp và alert |
| Truyền token xác thực | Security protocol/header chuyên biệt | Baggage không phải kênh secrets |
| Truyền toàn bộ request body | Không dùng baggage | Quá lớn và nguy cơ dữ liệu nhạy cảm |
| Mang trạng thái nghiệp vụ qua nhiều ngày | Database/event/message payload theo hợp đồng | Baggage không bền vững và phụ thuộc trace |

Một quy tắc hữu ích: chỉ đưa vào baggage một giá trị **nhỏ, ổn định, cần cho downstream, an toàn qua trust boundary và có thể tồn tại trong suốt trace**. Nếu câu hỏi chỉ liên quan tới một span, span attribute có thể phù hợp hơn. Nếu cần thống kê tổng thể, hãy dùng metrics.

## 9. Kiểm thử baggage và correlation

Kiểm thử nên chia làm ba tầng: tạo/đọc baggage trong process, propagation qua HTTP và log correlation. Test một API baggage không chứng minh header đã được truyền hoặc MDC đã được cấu hình.

### 9.1. Integration test scope baggage

Với một tracing implementation thực được cấu hình trong test, có thể kiểm tra scope:

~~~java
import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Baggage;
import io.micrometer.tracing.Tracer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class BaggageScopeTest {
    @Autowired
    private Tracer tracer;

    @Test
    void restoresBaggageAfterScopeCloses() {
        Baggage before = tracer.getBaggage("orders.channel");
        String previous = before == null ? null : before.get();

        try (BaggageInScope ignored =
                     tracer.createBaggageInScope("orders.channel", "web")) {
            assertEquals("web", tracer.getBaggage("orders.channel").get());
        }

        Baggage after = tracer.getBaggage("orders.channel");
        assertEquals(previous, after == null ? null : after.get());
    }
}
~~~

Đây là **integration test cần tracing auto-configuration và exporter/tracer bean phù hợp trong test context**. Nó xác minh scope đóng xong đã khôi phục giá trị baggage trước đó (hoặc không còn giá trị nếu trước đó chưa có). Có thể cấu hình exporter in-memory/no-op phù hợp để không phụ thuộc Collector bên ngoài; mục tiêu của test là lifecycle context, không phải kiểm tra OTLP export.

### 9.2. Test propagation qua HTTP

Một integration test với hai service hoặc test server nên:

1. Tạo parent trace ở service gửi.
2. Tạo baggage field `orders.channel=web` trong active scope.
3. Gửi request bằng HTTP client đã được tracing instrument.
4. Ở server nhận, kiểm tra `traceparent` và `baggage` xuất hiện theo allowlist.
5. Đọc baggage bằng API tracing context ở phía nhận; không chỉ so sánh raw header.
6. Xác minh trace ID thống nhất và parent span ID đúng nếu HTTP tracing được cấu hình.
7. Kiểm tra field ngoài allowlist không bị propagate.

Tránh hard-code span ID vì chúng thường được sinh ngẫu nhiên. Assertions nên kiểm tra quan hệ ID và giá trị baggage đã parse.

### 9.3. Test log correlation

Để xác minh MDC:

- Tạo active span/baggage trong test logging context.
- Ghi một log event.
- Capture event qua appender hoặc logging test facility.
- Kiểm tra trace ID/span ID và correlation field được cấu hình có mặt.
- Đóng scope và xác minh event tiếp theo không mang context cũ.
- Kiểm tra logs không chứa token, email hoặc field ngoài allowlist.

### 9.4. Test async propagation

Chạy một task trên executor tái sử dụng thread:

1. Request đầu tạo baggage `orders.channel=web` và submit task.
2. Task đọc đúng value khi context propagation được cấu hình.
3. Scope đóng sau task.
4. Task tiếp theo không có baggage nếu không được truyền.
5. Chạy thêm test không có decorator để minh họa lỗi mất context.

Điều này phát hiện cả hai lỗi: **không truyền được context** và **rò rỉ context sang tác vụ khác**.

## 10. Troubleshooting: baggage không tới downstream hoặc không xuất hiện trong log

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Service downstream không thấy field | Field chưa nằm trong remote allowlist | Kiểm tra `management.tracing.baggage.remote-fields` |
| Header baggage không xuất hiện | Không có active context, propagator khác hoặc HTTP client không instrument | Kiểm tra tracer, client/server instrumentation |
| Header có nhưng API đọc null | Field parse/extract chưa được thực hiện hoặc tên key không khớp | Kiểm tra context phía nhận và cách đọc baggage |
| Logs không có baggage field | Correlation fields chưa cấu hình hoặc MDC integration không hoạt động | Kiểm tra `management.tracing.baggage.correlation.fields` và log pattern |
| Logs có trace ID nhưng không có baggage | Trace correlation đã hoạt động, baggage correlation chưa | Xác minh hai cấu hình riêng |
| Baggage mất khi chạy @Async | Context không được capture/restore | Kiểm tra TaskDecorator/context propagation |
| Baggage biến mất ở một gateway | Proxy/ingress strip hoặc giới hạn header | Kiểm tra network path và header limits |
| Một field client tự gửi được downstream tin | Trust boundary thiếu lọc/xác minh | Strip/overwrite field, xác thực nguồn dữ liệu |
| HTTP 431 / header too large | Baggage quá nhiều hoặc values quá dài | Giảm allowlist, độ dài và tổng payload |
| Metrics cardinality tăng | Baggage bị copy vào metric labels | Sửa instrumentation, dùng low-cardinality tags |
| Traces thiếu dù baggage vẫn tới | Sampling/exporter/Collector lỗi | Kiểm tra tracing pipeline riêng |
| Baggage có ở span này nhưng không ở span kia | Span attributes không tự kế thừa từ baggage | Gắn attribute tường minh ở span cần thiết |

### 10.1. Chẩn đoán theo thứ tự

1. **Tại nơi tạo:** code có tạo baggage trong active scope không?
2. **Tại context:** tracer đọc lại được giá trị ngay sau khi tạo không?
3. **Tại outbound:** remote field có được allowlist và propagator inject không?
4. **Qua mạng:** proxy/gateway có giữ header không?
5. **Tại inbound:** server extract được baggage theo đúng propagator không?
6. **Tại log:** correlation field có được đưa vào MDC/layout không?
7. **Tại trace backend:** nếu cần span attribute, code/handler có gắn attribute vào span đúng không?

Không dùng việc header baggage có mặt để kết luận trace exporter đã thành công. Export spans là một pipeline khác.

## 11. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Mỗi baggage field có mục đích rõ | Downstream thực sự cần đọc field |
| Remote allowlist nhỏ | Cấu hình field được propagate rõ ràng |
| Correlation allowlist riêng | Chỉ log field được duyệt |
| Values đã chuẩn hóa | Không nhận chuỗi tùy ý từ client |
| Trust boundary được xử lý | Strip/overwrite và xác minh dữ liệu ngoài |
| Không chứa secrets/PII | Security review và test logs/headers |
| Header kích thước hợp lý | Giới hạn key/value/tổng baggage |
| Thread/reactive context được kiểm tra | Test async, executor hoặc Reactor |
| Không đưa baggage động vào metrics | Metric label cardinality thấp |
| Span attributes được gắn có chủ đích | Không kỳ vọng baggage tự thành attribute |
| Exporter và propagation tách bạch | Có test cho cả trace context lẫn OTLP export |
| Log correlation không rò rỉ context | Test scope đóng và thread reuse |
| Tài liệu/API version được xác minh | Cấu hình khớp Spring Boot/Micrometer đang dùng |

## 12. Bài thực hành: truyền channel và liên kết logs qua hai service

**Bối cảnh:** `order-service` nhận request từ web hoặc batch, rồi gọi `inventory-service`. Nhóm vận hành muốn lọc log theo channel nhưng không muốn đưa order ID hoặc dữ liệu cá nhân vào metrics.

**Nhiệm vụ:**

1. Cài Actuator và Micrometer Tracing với bridge phù hợp; xác định HTTP client/server được instrument.
2. Cấu hình `management.tracing.baggage.remote-fields` chỉ cho phép `orders.channel` và `deployment.region`; cấu hình correlation fields riêng.
3. Kiểm tra code đầu vào chuẩn hóa channel thành `web` hoặc `batch`, không lấy raw header client.
4. Dùng `tracer.createBaggageInScope("orders.channel", channel)` trong quá trình xử lý và đóng scope bằng try-with-resources.
5. Gửi HTTP request từ order-service sang inventory-service, xác minh `baggage` và `traceparent` được truyền theo đúng hợp đồng.
6. Ở inventory-service, đọc giá trị baggage và ghi một log có correlation field đã được cho phép.
7. Xác minh logs có trace ID/span ID và channel, nhưng không có token, email, request body hoặc order ID.
8. Thêm test trường hợp client gửi `orders.channel=internal`; chứng minh ứng dụng không tin raw baggage bên ngoài.
9. Chạy tác vụ trên executor có và không có context propagation, kiểm tra baggage có tới đúng task và không rò rỉ sang task kế tiếp.
10. Xác minh `orders.channel` không trở thành metric label nếu tập values hoặc chính sách không phù hợp; thiết kế metric riêng chỉ với tập giá trị hữu hạn khi có nhu cầu phân tích.

**Kết quả mong đợi:** cấu hình allowlist, code tạo/đọc baggage, trace xuyên service, logs correlation, unit/integration tests và ghi chú về trust boundary, header size, async propagation.

## 13. Ghi nhớ

**Baggage là dữ liệu ngữ cảnh key-value có thể được propagate cùng trace context** để các service downstream dùng khi cần. Nó khác `traceparent` (định danh/liên kết spans), khác span attributes (mô tả span), khác MDC (log context) và khác metric labels (nhóm time series).

Trong Spring Boot/Micrometer Tracing, chỉ truyền baggage theo **allowlist**, giới hạn kích thước và chuẩn hóa giá trị. Không chứa secrets, PII hoặc dữ liệu có thể bị client giả mạo để quyết định bảo mật. Chỉ đưa field vào logs hoặc span attributes khi có chủ đích; không biến baggage thành metric labels có cardinality cao.

Để correlation đáng tin cậy, cần xác minh riêng **baggage creation, propagation, extraction, MDC/logging, async context propagation và tracing export**. Metrics cho xu hướng toàn hệ thống, trace ID giúp mở trace của request, baggage thêm context được kiểm soát và logs lưu lại sự kiện phục vụ điều tra.

**Tài liệu tham khảo:**

- [W3C — Baggage](https://www.w3.org/TR/baggage/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/observability.html)
