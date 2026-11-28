# Giữ trace lỗi dù tỷ lệ sampling thấp

## 1. Bài toán: trace bình thường rất nhiều, trace lỗi lại hiếm

Trong ứng dụng Spring Boot dùng **Spring Modulith**, một request có thể đi qua nhiều application module. Ví dụ, module **ordering** gọi **payment**, phát sự kiện **OrderPlaced** rồi module **notification** xử lý thông báo. Spring Modulith có thể tạo module-entry observations tại các điểm vào API được instrument; Micrometer Tracing chuyển những observation đó thành span để tìm trong tracing backend.

Khi lưu lượng tăng, thu thập 100% trace có thể tốn băng thông, CPU, bộ nhớ, chi phí lưu trữ và thời gian truy vấn. Vì vậy, hệ thống thường giảm tỷ lệ sampling, chẳng hạn chỉ giữ 5% trace. Nhưng nếu một request rất hiếm gặp bị lỗi, nó có thể nằm trong 95% đã bị loại bỏ. Khi đội vận hành cần điều tra nhất thì trace lại không còn.

Yêu cầu **“giữ trace lỗi dù tỷ lệ sampling thấp”** cần giải quyết hai mục tiêu:

- Giữ lại các trace có tín hiệu quan trọng như span status **ERROR**, exception hoặc thời gian xử lý vượt ngưỡng.
- Chỉ lấy một tỷ lệ nhỏ trace bình thường để kiểm soát chi phí.

Giải pháp phù hợp cho trường hợp này là **tail-based sampling**: thu thập các span của trace trước, chờ đủ thông tin rồi quyết định có export trace hay không. Collector có thể giữ mọi trace có lỗi và chỉ giữ một phần trace không lỗi.

Điểm cần nhớ ngay từ đầu: nếu ứng dụng đã **head-sample 5% và drop 95% trước khi gửi tới collector**, tail sampler không thể phục hồi các trace đã bị loại. Muốn tail sampling chọn được lỗi, các span ứng viên phải tới được tail-sampling collector. Trong mô hình đơn giản, ứng dụng gửi 100% trace tới collector; collector mới giữ mọi trace lỗi và một tỷ lệ baseline của trace bình thường.

Bài học thuộc chương **Sampling** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này dùng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác khi vận hành thông qua module graph, Actuator, event metrics, tracing và context propagation.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt head-based sampling và tail-based sampling.
2. Giải thích vì sao head sampling xác suất thấp không thể giữ chắc các lỗi phát sinh về sau.
3. Cấu hình ứng dụng Spring Boot gửi trace tới OpenTelemetry Collector để tail sampling.
4. Giữ trace có span status ERROR, trace chậm và một tỷ lệ baseline của trace bình thường.
5. Hiểu vai trò của decision_wait, giới hạn số trace trong bộ nhớ và định tuyến theo trace ID.
6. Bảo đảm lỗi được ghi nhận đúng vào span, kể cả khi exception bị xử lý hoặc retry.
7. Phân biệt trace sampling với event metrics, Event Publication Registry và độ tin cậy của xử lý message.
8. Kiểm chứng hiệu quả sampling và xử lý các trường hợp trace bị thiếu.

## 2. Head-based và tail-based sampling khác nhau ở đâu?

### 2.1. Head-based sampling: quyết định ở đầu trace

**Head-based sampling** quyết định có lấy trace ngay khi trace được bắt đầu, thường tại server hoặc SDK đầu tiên. Quyết định được đưa ra trước khi biết toàn bộ quá trình xử lý có lỗi hay không.

Ví dụ, xác suất sampling là 5%:

~~~text
Request bắt đầu
    |
    +-- Sampler quyết định 5%? ---- No ---> Không export trace
    |                                  (các span sau không thể cứu trace)
    |
    +-- Yes -----------------------> Ghi/export các span của trace
                                      |
                                      +-- Có thể thành công
                                      +-- Có thể lỗi
~~~

Ưu điểm của head sampling là quyết định sớm, ít phải giữ trace trong bộ nhớ và giảm dữ liệu ngay từ ứng dụng. Nhược điểm là sampler chưa biết lỗi sẽ xuất hiện ở cuối request, trong một module sâu hơn hay trong listener bất đồng bộ.

Với parent-based sampling, span con thường kế thừa quyết định sampling của parent. Nếu trace gốc đã bị loại, các service phía sau thường không thể tự tạo lại một trace đầy đủ chỉ bằng cách bật sampler riêng.

### 2.2. Tail-based sampling: quyết định sau khi đã thấy trace

**Tail-based sampling** nhận các span của trace, tạm giữ chúng trong collector, đợi một khoảng thời gian để thu thập đủ dữ liệu rồi mới áp dụng policy:

~~~mermaid
flowchart LR
    A["Ứng dụng gửi span ứng viên"]
    B["Collector nhận và gom theo trace ID"]
    C["Giữ trace tạm trong bộ nhớ"]
    D["Đợi decision_wait"]
    E{"Trace có lỗi hoặc chậm?"}
    F["Giữ trace"]
    G{"Được chọn vào baseline?"}
    H["Giữ trace bình thường"]
    I["Loại trace khỏi export"]
    A --> B --> C --> D --> E
    E -->|"Có"| F
    E -->|"Không"| G
    G -->|"Có"| H
    G -->|"Không"| I
~~~

Vì quyết định được đưa ra sau khi có span kết thúc, collector có thể kiểm tra status, duration và attributes của trace. Điều này giúp ưu tiên trace có lỗi ngay cả khi chúng hiếm gặp.

### 2.3. So sánh

| Tiêu chí | Head-based sampling | Tail-based sampling |
| --- | --- | --- |
| Thời điểm quyết định | Khi trace bắt đầu. | Sau khi collector nhận đủ dữ liệu trong khoảng chờ. |
| Có biết lỗi cuối cùng không? | Thường chưa biết. | Có thể kiểm tra status/attributes đã nhận. |
| Giữ mọi trace lỗi | Không bảo đảm nếu sampler đã drop từ đầu. | Có thể cấu hình policy giữ trace lỗi, nếu toàn bộ span cần thiết tới collector. |
| Tài nguyên ở đâu? | Chủ yếu giảm tải tại ứng dụng và downstream. | Collector cần bộ nhớ, CPU và băng thông để giữ trace ứng viên. |
| Độ trễ quyết định | Thấp. | Có độ trễ do buffer và decision_wait. |
| Khả năng mở rộng | Tương đối đơn giản. | Cần capacity planning và định tuyến trace nhất quán. |
| Trường hợp phù hợp | Lưu lượng rất lớn, cần sampling đơn giản. | Cần ưu tiên lỗi, trace chậm hoặc thuộc tính chỉ biết sau xử lý. |

## 3. Nguyên tắc quan trọng: đừng drop trace trước tail sampler

Giả sử ứng dụng đặt xác suất head sampling là 5%, sau đó gửi span tới OpenTelemetry Collector có tail-sampling processor:

~~~text
Ứng dụng:
  100% request bắt đầu
      |
      +-- Head sampler giữ 5% --------> Collector
      |
      +-- Head sampler drop 95% ------> Không có dữ liệu tới Collector

Collector:
  Chỉ nhìn thấy 5% đã được ứng dụng giữ
  -> Không thể biết 95% còn lại trace nào bị lỗi
~~~

Đây là cấu hình **không đáp ứng yêu cầu giữ mọi trace lỗi**. Tail sampler chỉ có thể đánh giá những trace mà nó nhận được.

Trong mô hình tail sampling đầy đủ, ứng dụng gửi mọi trace ứng viên tới collector:

~~~text
Ứng dụng:
  Head sampling = 100%
      |
      +-- Export toàn bộ span ứng viên
              |
              v
OpenTelemetry Collector:
  Giữ mọi trace có ERROR
  Giữ trace chậm theo ngưỡng
  Giữ 5% trace bình thường
  Drop phần còn lại
              |
              v
Tracing backend:
  Chỉ nhận trace đã qua policy
~~~

**100% ở phía ứng dụng không có nghĩa backend lưu 100% trace.** Nó có nghĩa collector nhận được dữ liệu cần thiết để đưa ra quyết định tail-based. Backend chỉ nhận các trace được policy chọn.

Đổi lại, collector vẫn phải nhận và xử lý toàn bộ span ứng viên. Tail sampling giảm lượng trace lưu ở backend, nhưng không xóa chi phí network và ingestion tới collector. Cần triển khai collector đủ khả năng chịu tải.

## 4. Kiến trúc Spring Boot + Spring Modulith + OpenTelemetry Collector

Một pipeline thực tế có thể gồm:

~~~mermaid
flowchart TB
    subgraph App["Spring Boot application"]
        HTTP["HTTP instrumentation"]
        MOD["Spring Modulith module-entry observations"]
        EVENT["Event listener / business observations"]
        REG["ObservationRegistry"]
        TRACE["Micrometer Tracing + OTel bridge"]
        HTTP --> REG
        MOD --> REG
        EVENT --> REG
        REG --> TRACE
    end
    SDK["OTLP exporter"]
    COL["OpenTelemetry Collector Contrib<br/>tail_sampling processor"]
    BACK["Tempo / Jaeger / tracing backend"]
    TRACE --> SDK --> COL --> BACK
~~~

### 4.1. Vai trò của từng thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| Spring Boot instrumentation | Tạo observation cho HTTP, client, database hoặc các thành phần được hỗ trợ. |
| Spring Modulith Insight/observability | Tạo module-entry observations và event metrics cho application modules. |
| ObservationRegistry | Điều phối vòng đời observation và các handler. |
| Micrometer Tracing bridge OTel | Chuyển tracing API của Micrometer sang OpenTelemetry. |
| OTLP exporter | Gửi span từ ứng dụng tới collector. |
| OpenTelemetry Collector Contrib | Gom span theo trace, áp dụng tail-sampling policies và export trace được giữ. |
| Tempo/Jaeger hoặc backend khác | Lưu và cho phép truy vấn trace đã được collector gửi đi. |

Spring Modulith Insight Starter cung cấp hỗ trợ observability/Actuator cho module. Nó **không tự quyết định tail sampling** và cũng không thay thế exporter hay collector.

### 4.2. Dependency Gradle minh họa

Với dự án Spring Boot 3.x có dependency management tương thích:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Micrometer Tracing API được nối tới OpenTelemetry.
    implementation("io.micrometer:micrometer-tracing-bridge-otel")

    // Export span bằng OTLP.
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")

    // Instrumentation của Spring Modulith.
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
}
~~~

Các phiên bản artifact nên được quản lý qua Spring Boot/Spring Modulith BOM tương thích. Với Spring Boot thế hệ mới hơn, starter OpenTelemetry hoặc cách autoconfigure có thể thay đổi; hãy dùng dependency và tài liệu đúng phiên bản thay vì ghép các ví dụ khác thế hệ.

Nếu ứng dụng chỉ dùng Brave bridge và Zipkin reporter, không thể áp dụng nguyên cấu hình OTLP collector trong bài này mà không bổ sung một đường nhận tương thích. Bài thực hành tập trung vào **Micrometer Tracing + OpenTelemetry bridge + OTLP** để dùng tail_sampling của OpenTelemetry Collector Contrib.

## 5. Cấu hình ứng dụng gửi toàn bộ trace ứng viên tới collector

### 5.1. Cấu hình sampling probability ở Spring Boot

Ví dụ application.yml:

~~~yaml
spring:
  application:
    name: shop-service

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Trong cấu hình Spring Boot tương ứng:

- management.tracing.sampling.probability: 1.0 yêu cầu sampler phía ứng dụng lấy mẫu mọi trace gốc, để collector nhận đủ trace ứng viên.
- management.otlp.tracing.endpoint trỏ tới OTLP/HTTP receiver của collector. Property và mặc định endpoint cần đối chiếu phiên bản Spring Boot đang dùng.
- spring.application.name giúp nhận diện service trong telemetry; không dùng tên động theo request.

Nếu hệ thống dùng OTLP/gRPC thay vì OTLP/HTTP, endpoint/port và cấu hình exporter sẽ khác. Collector trong ví dụ tiếp theo nhận cả gRPC và HTTP.

**Quan trọng:** tất cả service có thể tạo span trong trace cần thống nhất chính sách head sampling. Nếu service đầu tiên gửi sampled=0, service sau dùng parent-based sampler có thể không export span, khiến tail sampler chỉ nhận được một phần trace. Để tail sampling giữ lỗi xuyên service, cần bảo đảm các upstream span cũng được gửi tới collector.

### 5.2. Sampling probability không phải tỷ lệ lưu cuối cùng

Trong ví dụ trên, 1.0 có nghĩa **head sampler của ứng dụng không loại trace theo xác suất**. Collector có thể tiếp tục loại các trace bình thường sau khi đánh giá policy. Tỷ lệ lưu cuối cùng sẽ phụ thuộc:

- Tỷ lệ trace lỗi.
- Tỷ lệ trace vượt ngưỡng latency.
- Tỷ lệ baseline được chọn.
- Các policy khác và cách kết hợp chúng.

Nếu 2% trace lỗi, 1% trace chậm không lỗi và baseline chọn 5% trace bình thường, tỷ lệ export cuối không nhất thiết là 5%. Nó còn phụ thuộc các nhóm có giao nhau hay không.

## 6. Cấu hình tail sampling tại OpenTelemetry Collector Contrib

tail_sampling là processor có trong bản phân phối **OpenTelemetry Collector Contrib**. Hãy sử dụng Collector distribution có processor này; một bản Collector core tối giản có thể không chứa nó.

### 6.1. Pipeline mẫu: giữ lỗi, giữ trace chậm và lấy baseline 5%

Ví dụ cấu hình collector:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 1024
    spike_limit_mib: 256

  tail_sampling:
    decision_wait: 15s
    num_traces: 50000
    expected_new_traces_per_sec: 1000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      - name: keep-slow-traces
        type: latency
        latency:
          threshold_ms: 1000

      - name: baseline-non-error
        type: probabilistic
        probabilistic:
          sampling_percentage: 5

  batch:

exporters:
  otlp:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp]
~~~

Đây là **cấu hình minh họa cho môi trường phát triển**. Cần điều chỉnh limit_mib, spike_limit_mib, num_traces, throughput dự kiến, endpoint, TLS và xác thực theo phiên bản Collector và tải thật. Không dùng insecure: true cho kết nối production qua mạng không tin cậy.

### 6.2. Các policy trong ví dụ

| Policy | Điều kiện | Hành động |
| --- | --- | --- |
| keep-errors | Trace có span status ERROR. | Giữ trace. |
| keep-slow-traces | Thời lượng trace đạt ngưỡng 1.000 ms. | Giữ trace. |
| baseline-non-error | Trace được chọn theo xác suất 5%. | Giữ một mẫu nền để quan sát hành vi bình thường. |

Các policy trong danh sách hoạt động theo logic **một policy match là trace có thể được giữ**. Vì vậy trace lỗi hoặc chậm được ưu tiên; các trace khác vẫn có cơ hội vào baseline. Một trace vừa lỗi vừa chậm vẫn chỉ là một trace được export, không phải hai bản sao chỉ vì match hai policy.

Nếu mục tiêu là **chỉ giữ lỗi và không cần baseline**, có thể bỏ policy probabilistic. Nhưng khi đó dashboard tracing sẽ ít ví dụ về luồng thành công, khiến việc so sánh hành vi bình thường với lỗi khó hơn.

### 6.3. Ý nghĩa các tham số quan trọng

| Tham số | Ý nghĩa | Cách chọn |
| --- | --- | --- |
| decision_wait | Khoảng thời gian processor chờ nhận thêm span trước khi quyết định. | Phải đủ dài để span quan trọng, đặc biệt consumer/event span, có thời gian đến collector. |
| num_traces | Số trace tối đa được giữ trong bộ nhớ để đánh giá. | Ước lượng theo trace mới/giây và thời gian chờ. |
| expected_new_traces_per_sec | Ước lượng tốc độ trace mới để processor chuẩn bị capacity. | Đặt gần lưu lượng đỉnh, theo dõi memory và drop. |
| threshold_ms | Ngưỡng latency của policy. | Chọn theo SLO/SLI và phân bố thực tế. |
| sampling_percentage | Tỷ lệ baseline của policy xác suất. | Cân bằng khả năng điều tra với chi phí lưu trữ. |

decision_wait quá ngắn có thể khiến collector quyết định trước khi span lỗi của listener hoặc service downstream tới nơi. Quá dài làm tăng thời gian giữ trace trong bộ nhớ và làm chậm việc xuất trace. num_traces quá thấp so với lưu lượng có thể gây áp lực hoặc mất khả năng đánh giá đầy đủ.

### 6.4. Không phải cấu hình production dùng chung cho mọi tải

Thông số 50.000 traces, 15s và 1.000 traces/s chỉ là giá trị khởi đầu minh họa. Cần đo:

- Trace mới mỗi giây và số span trung bình mỗi trace.
- Độ dài trace và độ trễ của message consumer.
- Kích thước span, số attributes/events và baggage.
- RAM của collector, số trace đang chờ quyết định và số trace bị drop.
- Thời gian từ lúc request kết thúc tới lúc trace xuất hiện trong backend.

Đặt capacity dựa trên dữ liệu thật và thử tải trước khi dùng trong production.

## 7. Điều kiện để policy lỗi thật sự nhận ra lỗi

Tail sampler không tự hiểu mọi log có chữ ERROR. Policy status_code kiểm tra **status của span**. Vì vậy, instrumentation cần ghi lỗi đúng vào span tương ứng.

### 7.1. Exception phải được ghi nhận

Trong nhiều instrumentation của Spring Boot, HTTP status lỗi hoặc exception chưa được xử lý có thể được ghi nhận tự động. Với observation tự tạo, nếu callback ném exception và không bị nuốt, Observation API có thể ghi nhận lỗi trong lifecycle; tracing handler sau đó ánh xạ sang span.

Ví dụ dùng Observation API:

~~~java
package com.example.shop.payment;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class PaymentCaptureService {

    private final ObservationRegistry registry;
    private final PaymentGateway gateway;

    PaymentCaptureService(
            ObservationRegistry registry,
            PaymentGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    void capture(String orderId) {
        Observation.createNotStarted("payment.capture", registry)
            .contextualName("capture payment")
            .observe(() -> gateway.capture(orderId));
    }
}
~~~

PaymentGateway là interface minh họa. Nếu gateway.capture(...) ném exception, exception được truyền qua callback và observation có thể ghi nhận lỗi. Nếu code bắt exception rồi trả về bình thường, không nên giả định span vẫn mang status ERROR.

### 7.2. Lỗi bị xử lý bên trong cần được đánh dấu có chủ đích

Nếu ứng dụng cố ý bắt và xử lý exception nhưng vẫn muốn giữ trace để điều tra, phải ghi trạng thái lỗi hoặc một thuộc tính/marker mà policy có thể kiểm tra. Cách cụ thể phụ thuộc API instrumentation đang dùng. Với Micrometer Tracing span trực tiếp, có thể ghi lỗi qua Span.error(ex); với Observation, dùng lifecycle/error API hoặc convention/handler phù hợp phiên bản.

Đừng biến mọi kết quả nghiệp vụ bị từ chối thành ERROR một cách máy móc. Ví dụ người dùng nhập sai mã giảm giá có thể là kết quả nghiệp vụ dự kiến; lỗi database timeout hoặc payment gateway unavailable thường là lỗi kỹ thuật cần ưu tiên. Hãy định nghĩa rõ điều gì được coi là lỗi vận hành.

### 7.3. HTTP status không phải lúc nào cũng phản ánh lỗi nghiệp vụ

Một request có thể trả HTTP 200 nhưng trong payload chứa trạng thái thất bại nghiệp vụ; ngược lại, một HTTP 4xx có thể là lỗi client được dự kiến. Nếu tail policy chỉ dựa vào span status, hãy bảo đảm instrumentation hoặc convention ánh xạ đúng semantics.

Có thể dùng thêm attribute/marker cho policy nếu cần phân biệt:

- error.type hoặc status span theo convention.
- Một thuộc tính ổn định như business.outcome=declined nếu muốn giữ trace của một nhóm nghiệp vụ cụ thể.
- Latency threshold để giữ các trace chậm dù không có exception.

Các thuộc tính dùng cho tail sampling cần có quy ước rõ và không chứa dữ liệu nhạy cảm.

## 8. Spring Modulith: giữ trace lỗi tại module và event boundary

### 8.1. Module-entry spans giúp xác định lỗi nằm ở module nào

Spring Modulith có thể tạo module-entry observation khi lời gọi đi vào API module được instrument. Các tag như:

- module.identifier
- module.name
- module.method
- module.invocation-type

giúp tracing backend phân biệt điểm vào ordering, payment hoặc notification. Khi một span module được đánh dấu ERROR, tail sampler có thể giữ trace chứa span đó, kể cả request ban đầu không bị lỗi ở HTTP layer.

Module graph từ /actuator/modulith vẫn là dữ liệu kiến trúc tĩnh; trace là bằng chứng về một lần thực thi được instrument. Hai nguồn bổ sung cho nhau khi điều tra lỗi xuyên module.

### 8.2. Event listener bất đồng bộ

Giả sử ordering phát OrderPlaced, notification xử lý qua @ApplicationModuleListener:

~~~java
package com.example.shop.notification;

import com.example.shop.ordering.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        emailGateway.sendConfirmation(event.orderId());
    }
}
~~~

@ApplicationModuleListener hỗ trợ xử lý sau commit, bất đồng bộ và transaction riêng theo semantics Spring Modulith. Nếu listener chạy trên executor thread khác, cần **context propagation** để trace context có thể đi theo task. Với executor tự cấu hình, có thể gắn ContextPropagatingTaskDecorator vào đúng executor.

Tail sampler chỉ có thể gom span vào cùng trace khi chúng thực sự có **cùng trace ID** và được định tuyến tới cùng tail-sampling processor. Nếu listener bắt đầu trace độc lập do mất context, policy vẫn có thể giữ trace listener nếu nó mang status ERROR, nhưng nó không còn là trace liên tục với request ban đầu.

### 8.3. Retry sau commit hoặc restart

Event Publication Registry theo dõi publication tới transactional listener và có thể hỗ trợ resubmit publication chưa hoàn tất theo cấu hình. Nếu một lần retry diễn ra sau khi process restart, trace ban đầu có thể đã kết thúc từ lâu. Khi đó:

- Trace của lần thử mới có thể là trace mới.
- Tail sampler đánh giá trace mới theo status/latency/attributes của chính nó.
- Correlation ID nghiệp vụ giúp liên hệ các lần thử thuộc cùng một đơn hàng.
- Không dùng correlation ID thay cho trace ID hoặc giả lập parent span cũ khi context không còn hợp lệ.

**Giữ trace lỗi** và **đảm bảo event được xử lý** là hai bài toán riêng. Tail sampling không thay thế Event Publication Registry, retry policy hoặc idempotency.

## 9. Tail sampling trong hệ thống nhiều collector

### 9.1. Tất cả span của một trace phải tới cùng processor

Tail sampler cần gom các span theo trace ID. Nếu span gốc tới collector A còn span consumer tới collector B, mỗi collector chỉ nhìn thấy một phần trace và có thể ra quyết định sai.

~~~mermaid
flowchart LR
    S["Services export spans"]
    LB["Routing theo trace ID"]
    A["Tail sampler A"]
    B["Tail sampler B"]
    S --> LB
    LB -->|"Trace X"| A
    LB -->|"Trace Y"| B
~~~

Khi scale nhiều collector instance, cần **consistent routing theo trace ID** (ví dụ một gateway dùng load-balancing exporter hỗ trợ routing trace-aware) để mọi span của cùng trace tới cùng tail-sampling instance. Không chia span ngẫu nhiên theo connection hoặc round-robin nếu điều đó có thể tách một trace.

### 9.2. Late spans và trace dài

Tail sampler chỉ chờ trong khoảng decision_wait. Nếu consumer span đến sau khi quyết định đã được đưa ra, span muộn có thể không được xét trong quyết định ban đầu hoặc không được thêm vào trace đã export, tùy processor/version/cache configuration.

Điều này đặc biệt đáng chú ý với:

- Event listener xử lý chậm sau commit.
- Message nằm lâu trong broker.
- Workflow kéo dài nhiều phút.
- Retry hoặc DLQ redrive.

Đừng đặt decision_wait quá lớn chỉ để gom mọi hoạt động nghiệp vụ có thể liên quan. Trace kéo dài nhiều phút có thể không còn phù hợp là một trace đơn lẻ. Hãy thiết kế span boundary và correlation ID phù hợp, theo dõi độ trễ của message, và cân nhắc tách execution thành trace mới có liên kết nghiệp vụ rõ ràng.

### 9.3. Bộ nhớ và backpressure

Collector phải giữ span trong bộ nhớ cho đến khi quyết định. Tải tăng đột biến, trace quá dài hoặc decision_wait quá cao có thể làm bộ nhớ tăng nhanh. Cần:

- Đặt memory_limiter trước tail sampler.
- Ước lượng num_traces theo số trace đồng thời và thời gian chờ.
- Theo dõi memory, queue, dropped spans và processor errors.
- Scale collector theo tải, nhưng vẫn giữ routing theo trace ID.
- Có giới hạn bảo vệ khi backend hoặc exporter downstream chậm.

Nếu collector drop dữ liệu do thiếu bộ nhớ hoặc queue đầy, policy không thể giữ trace lỗi mà nó chưa nhận được. Tail sampling tăng khả năng giữ trace quan trọng, không tạo ra bảo đảm tuyệt đối khi pipeline bị quá tải.

## 10. Đo hiệu quả: giữ lỗi nhưng vẫn kiểm soát chi phí

Giả sử có 100.000 trace trong một giờ:

| Nhóm | Số trace | Chính sách |
| --- | ---: | --- |
| Trace có status ERROR | 300 | Giữ 100%. |
| Trace chậm không lỗi | 700 | Giữ 100%. |
| Trace bình thường còn lại | 99.000 | Giữ baseline 5% = 4.950. |
| **Tổng export** | **5.950** | **5,95% trace** trong ví dụ không giao nhau giữa nhóm lỗi/chậm. |

Đây là phép tính minh họa. Nếu nhóm lỗi và chậm giao nhau, tổng unique traces sẽ thấp hơn phép cộng số lượng từng nhóm. Nếu có policy bổ sung hoặc tỷ lệ lỗi tăng, tỷ lệ export cuối sẽ thay đổi.

Các số cần theo dõi:

- Tổng trace/span ứng viên collector nhận.
- Trace được tail sampler giữ theo policy.
- Trace bị loại do không match policy.
- Số trace đang chờ quyết định và thời gian chờ.
- Memory và dropped spans tại collector.
- Tỷ lệ trace lỗi theo service/module và tỷ lệ trace lỗi thực sự xuất hiện trong backend.

Nếu chỉ xem “tỷ lệ sampling cuối 6%”, chưa đủ kết luận policy thành công. Cần kiểm tra xem **mọi trace lỗi có status ERROR đã tới collector và được giữ** hay không.

### 10.1. Metrics không bị tail sampling thay thế

Metrics như event counter, request rate, error rate và histogram vẫn có vai trò riêng. Sampling trace không nên làm mất metrics tổng hợp:

| Tín hiệu | Dùng để trả lời |
| --- | --- |
| Counter/Timer | Có bao nhiêu request/event? Tốc độ và latency phân bố ra sao? |
| Error rate | Tỷ lệ lỗi trong toàn bộ lưu lượng được instrument là bao nhiêu? |
| Tail-sampled traces | Những lần lỗi/chậm cụ thể đã đi qua các module và span nào? |
| Module graph | Các module có quan hệ phụ thuộc cấu trúc nào? |
| Event Publication Registry | Publication tới listener đã hoàn tất hay còn cần phục hồi? |

Không tính error rate bằng cách lấy số trace lỗi chia tổng số trace được tail-sample nếu baseline sampling đã loại phần lớn trace thành công. Hãy dùng metrics không sampling để tính tỷ lệ trên toàn bộ lưu lượng.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Trace lỗi không xuất hiện dù có tail policy | Head sampler đã drop trace trước collector. | Để ứng dụng gửi toàn bộ trace ứng viên tới tail sampler; kiểm tra upstream parent sampling. |
| Collector không thấy status ERROR | Exception không được ghi vào span, bị catch/swallow hoặc convention không đánh dấu lỗi. | Ghi nhận exception và span status đúng; kiểm tra span raw trước policy. |
| Có lỗi trong log nhưng tail sampler không giữ | Log level ERROR không tự biến span status thành ERROR. | Kiểm tra span status; cấu hình instrumentation hoặc marker policy phù hợp. |
| Trace HTTP lỗi được giữ nhưng listener lỗi không cùng trace | Mất context qua executor hoặc message boundary. | Dùng TaskDecorator cho thread; Propagator/framework instrumentation cho message headers. |
| Collector giữ quá nhiều trace | Baseline quá cao, latency threshold quá thấp hoặc policy match rộng. | Xem phân bố traffic, điều chỉnh policy và đánh giá tỷ lệ unique trace. |
| Collector dùng nhiều RAM | decision_wait cao, num_traces/throughput lớn hoặc trace quá dài. | Capacity planning, memory limiter, tăng tài nguyên hoặc giảm thời gian chờ hợp lý. |
| Trace bị thiếu span cuối | Span đến sau quyết định hoặc collector nhận không đủ trace. | Tăng decision_wait có kiểm soát, kiểm tra routing và độ trễ message. |
| Một trace bị tách giữa nhiều collector | Span cùng trace ID không được route tới cùng instance. | Dùng trace-aware routing/load-balancing exporter. |
| Không thấy lỗi nghiệp vụ trên span | HTTP 200 hoặc exception được xử lý như kết quả bình thường. | Định nghĩa business outcome rõ và ghi marker/status phù hợp. |
| Trace được giữ nhưng backend không tìm thấy | Exporter lỗi, collector downstream không nhận hoặc backend drop. | Kiểm tra exporter queue, endpoint, auth/TLS và backend ingestion. |
| Trace retry không liên kết với request ban đầu | Retry sau restart là execution mới, không còn active parent. | Dùng correlation ID; chấp nhận trace mới khi đúng semantics. |
| Tỷ lệ trace cuối vượt baseline nhiều | Error/slow policies giữ thêm trace; policy overlap hoặc traffic profile thay đổi. | Tách số trace theo policy và tính unique trace, không chỉ cộng tỷ lệ. |

### Quy trình chẩn đoán nhanh

Khi trace lỗi không có trong backend, kiểm tra theo thứ tự:

1. Request/service có tạo span không?
2. Span có status ERROR hoặc marker mà policy yêu cầu không?
3. Ứng dụng có export span ứng viên tới collector không?
4. Các service upstream/downstream có cùng head-sampling policy không?
5. Collector nhận đủ span và giữ trace trong decision_wait không?
6. Tail-sampling policy có match trace không?
7. Collector có export được tới backend không?
8. Backend có lưu và index trace không?

Không điều chỉnh sampling probability, policy và exporter cùng lúc trước khi xác định trace bị mất ở tầng nào.

## 12. Checklist triển khai production

1. **Định nghĩa lỗi cần giữ:** technical error, business failure, slow trace hay một nhóm attributes cụ thể.
2. **Bảo đảm error status:** exception hoặc lỗi nghiệp vụ cần được ghi nhận trên span mà policy đánh giá.
3. **Chọn kiến trúc sampling:** head sampling hay tail sampling; nếu tail, bảo đảm ứng dụng không drop trace ứng viên trước collector.
4. **Cấu hình collector Contrib:** bật tail_sampling, memory limiter và batch/exporter phù hợp.
5. **Đặt policy baseline:** chọn tỷ lệ trace bình thường dựa trên lưu lượng và ngân sách lưu trữ.
6. **Chọn decision_wait:** căn cứ thời gian xử lý và độ trễ của message/event, không đặt tùy ý.
7. **Định tuyến theo trace ID:** khi có nhiều tail-sampling collectors, đảm bảo các span cùng trace về cùng processor.
8. **Giám sát collector:** memory, queue, dropped spans, pending traces và export failures.
9. **Kiểm tra propagation:** qua HTTP, executor, Kafka/RabbitMQ và consumer.
10. **Giữ metrics độc lập:** dùng request/error/event metrics để tính tỷ lệ trên toàn lưu lượng.
11. **Bảo vệ telemetry:** không thêm dữ liệu cá nhân, token hoặc payload nhạy cảm vào span attributes/baggage.
12. **Thử tải và diễn tập lỗi:** kiểm tra trace lỗi được giữ trong điều kiện bình thường và khi collector gần ngưỡng capacity.

## 13. Bài tập thực hành

### Bài 1 — Thấy giới hạn của head sampling

Đặt xác suất sampling ứng dụng là 5%, gửi 100 request và tạo một số request lỗi. Quan sát collector chỉ nhận được một mẫu trace. Giải thích tại sao tail policy không thể giữ các trace lỗi đã bị head sampler loại.

### Bài 2 — Cấu hình tail sampling

Đặt head sampling của ứng dụng là 100%, gửi OTLP tới Collector Contrib và cấu hình ba policy: giữ ERROR, giữ trace chậm hơn 1 giây, baseline 5%. Gửi request thành công, request lỗi và request chậm. Xác nhận các nhóm tương ứng có xuất hiện trong backend.

### Bài 3 — Exception bị swallow

Tạo một listener bắt exception rồi ghi log nhưng không ném lại. Quan sát span status. Nếu status không phải ERROR, thử ghi nhận error rõ ràng hoặc thêm attribute policy. Giải thích vì sao log ERROR không tự động đồng nghĩa span ERROR.

### Bài 4 — Async event

Cho notification xử lý OrderPlaced qua @ApplicationModuleListener. Kiểm tra context propagation và xem span listener có cùng trace ID với publisher không. Sau đó mô phỏng retry sau restart và giải thích vì sao trace mới vẫn có thể liên kết nghiệp vụ qua correlation ID.

### Bài 5 — Điều chỉnh decision wait và capacity

Thử decision_wait ngắn và dài trong môi trường tải nhỏ. Quan sát trace listener đến muộn, thời gian trace xuất hiện và memory của collector. Không dùng giá trị thử nghiệm trực tiếp cho production nếu chưa đánh giá throughput và concurrency.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao head sampling 5% không thể giữ chắc trace lỗi?

**Đáp án:** Quyết định được đưa ra trước khi biết kết quả. Trace đã bị drop ở đầu sẽ không tới tail sampler để được đánh giá.

**Câu 2.** Muốn tail sampling giữ mọi trace lỗi, ứng dụng cần làm gì?

**Đáp án:** Gửi đủ trace ứng viên tới collector, thường bằng head sampling 100% ở các service liên quan; collector mới quyết định trace nào được export tiếp.

**Câu 3.** Policy status_code: ERROR dựa trên điều gì?

**Đáp án:** Span status đã được ghi là ERROR; log ERROR hoặc exception bị swallow không bảo đảm policy nhận ra lỗi.

**Câu 4.** decision_wait quá ngắn có thể gây vấn đề gì?

**Đáp án:** Collector có thể quyết định trước khi span consumer/listener hoặc downstream đến, khiến trace bị đánh giá thiếu thông tin.

**Câu 5.** Vì sao các collector tail-sampling cần routing theo trace ID?

**Đáp án:** Mỗi processor cần nhìn thấy đủ span của cùng trace; chia span của một trace qua nhiều instance có thể làm quyết định thiếu hoặc sai.

**Câu 6.** Tail sampling có thay thế event reliability không?

**Đáp án:** Không. Nó chọn trace để lưu; Event Publication Registry, broker acknowledgement, retry và idempotency mới giải quyết theo dõi/đảm bảo xử lý event.

## 14. Tài liệu tham khảo

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, sampling, propagation và exporter.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, handlers và context propagation.
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/): Tracer, Span, bridge Brave/OpenTelemetry và context.
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor): cấu hình decision_wait, num_traces và các policy.
- [OpenTelemetry Collector — Scaling the Tail Sampling Processor](https://opentelemetry.io/docs/collector/scaling/): định tuyến trace nhất quán và mở rộng tail sampling.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head sampling, tail sampling và các khái niệm sampling.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module-entry spans, event metrics và Insight Starter.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional event listeners và Event Publication Registry.

**Ghi nhớ:** muốn giữ trace lỗi dù chỉ lưu một tỷ lệ nhỏ trace bình thường, đừng loại trace ở head sampler trước khi collector nhìn thấy chúng. Hãy để ứng dụng gửi trace ứng viên tới OpenTelemetry Collector, dùng tail-sampling policy giữ span status ERROR/trace chậm và chọn một baseline cho phần còn lại. Để quyết định đúng, collector phải nhận đủ span, đợi đủ lâu, có capacity và nhận mọi span của một trace tại cùng processor. Metrics vẫn cần thiết để đo tỷ lệ lỗi trên toàn bộ lưu lượng; tail sampling chỉ giúp giữ lại những lần thực thi đáng điều tra.
