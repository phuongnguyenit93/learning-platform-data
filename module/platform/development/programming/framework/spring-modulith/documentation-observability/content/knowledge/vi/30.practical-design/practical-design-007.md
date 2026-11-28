# Thiết kế dashboard theo luồng nghiệp vụ

## Mục tiêu bài học

Một dashboard tốt cho ứng dụng **Spring Modulith** cần trả lời được câu hỏi nghiệp vụ: *“Đơn hàng đã đi đến bước nào, đang chậm ở đâu và lỗi thuộc phần nào?”* Nếu chỉ xếp các biểu đồ CPU, số request và số exception cạnh nhau, đội vận hành rất khó nhận ra một luồng trải qua nhiều application module đang bị kẹt.

Bài **Thiết kế dashboard theo luồng nghiệp vụ** thuộc chương **Thiết kế thực tế**, trong phạm vi **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Bài kết hợp **module graph**, tài liệu kiến trúc, **Spring Boot Actuator**, **event metrics**, **distributed tracing** và **context propagation** để quan sát một quy trình nghiệp vụ đi qua nhiều module trong cùng ứng dụng Spring Boot, rồi có thể tiếp tục qua message broker.

Sau khi hoàn thành, bạn có thể:

1. Phác thảo luồng nghiệp vụ và ánh xạ từng bước sang application module, event, transaction và hệ thống ngoài.
2. Phân biệt chỉ số kết quả nghiệp vụ (business KPI), chỉ số vận hành (SLI), metric của application event và trạng thái giao nhận message.
3. Thiết kế dashboard theo các câu hỏi: **bao nhiêu**, **đến đâu**, **mất bao lâu**, **lỗi ở đâu**, **còn tồn đọng gì**.
4. Xây dựng metric có tên, đơn vị và nhãn nhất quán; tránh độ phân biệt nhãn (cardinality) quá cao.
5. Sử dụng traces/logs để điều tra chi tiết mà không kỳ vọng một trace luôn tồn tại xuyên suốt mọi lần retry.
6. Đặt cảnh báo và kiểm thử dashboard dựa trên bằng chứng runtime, đồng thời đối chiếu với ranh giới module được tài liệu hóa.

> **Phạm vi ví dụ:** ứng dụng bán hàng gồm ba module `orders`, `payments`, `shipping`, có thể dùng Kafka để externalize một phần event. Các tên metric bắt đầu bằng `shop.flow.*` trong bài là **metric do ứng dụng tự định nghĩa**, không phải metric mặc định của Spring Modulith. Cấu hình Actuator, tracing và cách xuất metric phải phù hợp với phiên bản Spring Boot, Spring Modulith và registry thực tế.

## 1. Bắt đầu từ luồng nghiệp vụ, không bắt đầu từ biểu đồ

Giả sử khách hàng tạo đơn hàng. Quy trình mong muốn:

1. Module **orders** ghi nhận đơn hợp lệ, sau đó phát `OrderPlaced`.
2. Module **payments** nhận event, thử thu tiền; khi thành công thì phát `PaymentCaptured`, khi thất bại ghi nhận kết quả phù hợp.
3. Module **shipping** nhận `PaymentCaptured` rồi tạo yêu cầu giao hàng.
4. Khi cần tích hợp đối tác giao vận, một integration event như `ShipmentRequested` được **externalize** ra broker.
5. Hệ thống nhận xác nhận giao vận và cập nhật trạng thái **shipment_ready** trong nghiệp vụ.

Mục tiêu chính của dashboard: trả lời *với những đơn đã được chấp nhận, bao nhiêu đơn tiến được đến mỗi mốc, thời gian chờ bao lâu và mốc nào phát sinh nhiều lỗi?*

~~~mermaid
flowchart LR
    C["HTTP<br/>Đặt hàng"] --> O["orders<br/>order_accepted"]
    O -->|"OrderPlaced"| P["payments<br/>payment_captured"]
    P -->|"PaymentCaptured"| S["shipping<br/>shipment_requested"]
    S -->|"ShipmentRequested"| B[("Message broker")]
    B --> G["Đối tác giao vận"]
    G -->|"Trả kết quả"| R["shipping<br/>shipment_ready"]

    O -. "eventId / orderId" .-> M[("Metrics + logs")]
    P -. "eventId / orderId" .-> M
    S -. "eventId / orderId" .-> M
    R -. "eventId / orderId" .-> M
~~~

Sơ đồ là **luồng logic**. Nó không khẳng định tất cả event xử lý cùng transaction hoặc cùng trace. Với Spring Modulith, listener sử dụng `@ApplicationModuleListener` thường xử lý sau commit, bất đồng bộ và trong transaction riêng. Khi đi sang broker, luồng vượt qua ranh giới tiến trình. Mỗi ranh giới này ảnh hưởng đến cách đo độ trễ và liên kết telemetry.

### 1.1. Bảng ánh xạ nghiệp vụ sang module

| Bước nghiệp vụ | Module / thành phần sở hữu | Tín hiệu thành công | Tình huống cần thấy trên dashboard |
|---|---|---|---|
| Chấp nhận đơn | `orders` | Trạng thái `order_accepted` được lưu | Tỷ lệ từ chối, lỗi ghi dữ liệu, số đơn đầu vào |
| Thu tiền | `payments` | Trạng thái `payment_captured` được lưu | Tỷ lệ lỗi thanh toán, retry, thời gian xử lý |
| Yêu cầu giao hàng | `shipping` | Trạng thái `shipment_requested` được lưu | Event tồn đọng, gửi broker lỗi, trễ sau thanh toán |
| Đối tác nhận yêu cầu | Broker / consumer ngoài ứng dụng | Broker acknowledgment hoặc consumer confirmation, tùy hợp đồng | Producer failures, consumer lag, message bị giao lại |
| Sẵn sàng giao | `shipping` | Trạng thái `shipment_ready` được lưu | Số đơn quá hạn, thời gian đầu-cuối, tỷ lệ hoàn tất |

**Người sở hữu kết quả nghiệp vụ** phải được định nghĩa rõ. Ví dụ, broker xác nhận đã nhận message **không đồng nghĩa** đối tác đã tạo vận đơn. Nếu dashboard gọi trạng thái Kafka acknowledgment là “Giao hàng thành công”, dashboard sẽ gây hiểu nhầm dù mọi metric đều chính xác về kỹ thuật.

### 1.2. Module graph là bản đồ, trace là hành trình thực tế

Spring Modulith có thể phân tích các application module và giúp sinh tài liệu bằng `Documenter`; khi có hỗ trợ Actuator, endpoint `/actuator/modulith` có thể cho biết các module mà ứng dụng nhận diện ở runtime.

Dùng module graph để xác minh:

- Module nào sở hữu public API và domain event.
- Phụ thuộc giữa `orders`, `payments` và `shipping` có hợp lệ không.
- Một lời gọi trực tiếp xuyên module có thực sự cần thiết, hay nên dùng event.
- Những tên module nào nên xuất hiện trong metric và trace.

Dùng runtime telemetry để xác minh **một giao dịch cụ thể có thật sự đi qua các bước đã mô tả hay không**. Graph không chứng minh một event đã được phát; trace bị sample thiếu cũng không chứng minh module không chạy.

## 2. Chọn câu hỏi và KPI trước khi đặt tên metric

Dashboard nên đi từ câu hỏi của người dùng tới dữ liệu có thể đo. Một thiết kế tham khảo:

| Câu hỏi | Chỉ số | Nguồn dữ liệu ưu tiên |
|---|---|---|
| Trong một giờ có bao nhiêu đơn được chấp nhận? | `orders_accepted` | State transition bền vững hoặc business counter |
| Bao nhiêu đơn hoàn tất đến `shipment_ready`? | `shipments_ready` | Trạng thái nghiệp vụ đã commit |
| Bao nhiêu đơn còn chờ bước thanh toán hoặc giao vận? | `pending_count` | Query vào durable state hoặc read model |
| Đơn đang chờ lâu nhất bao lâu? | `oldest_pending_seconds` | Timestamp của trạng thái đang chờ |
| 95% lượt xử lý thanh toán mất dưới bao lâu? | `payment_step_p95` | Micrometer Timer histogram theo lượt xử lý |
| Có bao nhiêu lần gọi dịch vụ thanh toán thất bại? | `payment_attempt_failures` | Counter theo **attempt**, gắn loại lỗi |
| Có bao nhiêu publication chờ gửi lại? | `publication_backlog` | Event Publication Registry nếu được dùng |
| Luồng bị đứt trace ở bước nào? | Trace/span và log theo correlation | Tracing backend, log tập trung |

**Hai kiểu tỷ lệ rất dễ nhầm:**

- **Tỷ lệ thành công trên lượt thử (attempt success ratio):** số lần gọi thành công / tổng số lần thử trong cùng cửa sổ thời gian. Đo chất lượng thành phần kỹ thuật, có thể bị ảnh hưởng bởi retry.
- **Tỷ lệ hoàn tất đơn hàng theo cohort:** số đơn của **cùng một nhóm đã được chấp nhận** và đạt trạng thái đích / số đơn trong nhóm đó. Đo kết quả nghiệp vụ, đòi hỏi liên kết ID và mốc thời gian trong dữ liệu bền vững.

Không lấy số `shipment_ready` trong 5 phút gần nhất chia cho số `order_accepted` cùng 5 phút rồi gọi đó là conversion rate, vì các đơn hoàn thành có thể đến từ cửa sổ trước. Với pipeline bất đồng bộ, cách tính ấy có thể lớn hơn 100% hoặc giảm đột ngột dù hệ thống vẫn bình thường.

## 3. Chuẩn hóa ID và ranh giới quan sát

Một event nên có **eventId** cố định, **orderId** để liên kết dữ liệu nghiệp vụ và **occurredAt** để xác định khi nào sự kiện phát sinh. Khi retry cùng một event, giữ nguyên eventId; nếu xử lý thành công nhiều lần về mặt kỹ thuật, trạng thái nghiệp vụ vẫn phải được cập nhật **idempotent**.

Các mã có mục đích khác nhau:

| Giá trị | Dùng để | Nơi lưu/quan sát |
|---|---|---|
| `orderId` | Tra cứu một đơn cụ thể | Database nghiệp vụ; log/trace có kiểm soát |
| `eventId` | Khử trùng lặp, theo dõi một sự kiện qua retry | Event payload, publication registry, logs |
| `correlationId` | Liên kết các bước của quy trình dài | Payload/header hợp đồng tích hợp và logs |
| `traceId` | Liên kết span của một hoặc một nhóm lần thực thi | Tracing backend, MDC/log đã cấu hình |
| `module`, `step`, `outcome` | Phân nhóm đo lường | Metric tags có tập giá trị hữu hạn |

Đặt **orderId/eventId/traceId** lên nhãn Prometheus là một lỗi thiết kế thường gặp: mỗi ID có thể tạo một chuỗi thời gian mới. Giữ các giá trị nhận diện cao này trong logs, spans hoặc dữ liệu truy vấn; metric nên nhóm bằng tên module, loại bước, kết quả và loại lỗi với số lượng giá trị nhỏ.

Không đưa toàn bộ payload thanh toán, token, số thẻ hoặc thông tin định danh cá nhân vào trace/log. Các truy vấn drill-down phải tôn trọng quyền truy cập và chính sách giữ dữ liệu.

## 4. Thiết kế mô hình đo lường theo bước nghiệp vụ

Một quy ước tự định nghĩa có thể dùng những metric sau. Đặt tên nhất quán giúp dễ lọc theo module, kết quả và stage.

| Micrometer meter | Kiểu | Tags chính | Ý nghĩa |
|---|---|---|---|
| `shop.flow.transition` | Counter | `flow`, `step`, `module`, `result` | Số lần hệ thống ghi nhận **chuyển trạng thái** nghiệp vụ |
| `shop.flow.step.attempt` | Counter | `flow`, `step`, `module`, `outcome` | Số lượt thực thi, tính cả retry |
| `shop.flow.step.duration` | Timer | `flow`, `step`, `module` | Thời gian chạy một lượt xử lý của một bước |
| `shop.flow.end.to.end` | Timer hoặc số đo từ durable state | `flow`, `outcome` | Từ lúc nhận đơn đến mốc hoàn tất |
| `shop.flow.pending` | Gauge | `flow`, `step` | Số đối tượng còn đợi ở mỗi bước |
| `shop.flow.oldest.pending.age.seconds` | Gauge | `flow`, `step` | Tuổi tồn đọng cao nhất, đơn vị giây |
| `shop.flow.publication.pending` | Gauge nếu tự triển khai | `event_type`, `state` | Các publication trong registry chưa hoàn tất |

Các meter bắt đầu bằng `shop.flow.*` **đều là thiết kế đề xuất**. Spring Modulith có các metric riêng cho application event, ví dụ `module.events.published` ở những phiên bản và cấu hình observability hỗ trợ. Metric publish nội bộ đó không thay thế `shop.flow.transition` và **không chứng minh message đã tới broker**.

### 4.1. Counter cho state transition và attempt

Nếu có 100 đơn được chấp nhận, 95 đơn đã thu tiền và 3 lần retry thanh toán, kết quả có thể là:

- `order_accepted`: 100 business transitions.
- `payment_captured`: 95 business transitions.
- `payment_capture`: 98 hoặc nhiều hơn technical attempts, tùy số lần lỗi/thử lại.

Dùng một metric duy nhất cho cả hai ý nghĩa sẽ gây đếm trùng. Đối với business transition, cập nhật nên gắn với việc chuyển trạng thái thành công **đúng một lần** về mặt dữ liệu; đối với attempt, mỗi lần gọi ra payment gateway là một lượt riêng.

Metric counter vẫn là telemetry trong bộ nhớ rồi được scrape/export: crash hoặc mất kết nối có thể làm thiếu một số mẫu. Nếu cần báo cáo chính xác phục vụ đối soát tài chính, hãy tính từ database/ledger bền vững, còn metrics dùng để quan sát xu hướng và cảnh báo.

### 4.2. Thời gian xử lý khác thời gian chờ

Thời gian gọi payment gateway thường tính bằng vài trăm mili giây, trong khi thời gian từ `payment_captured` đến `shipment_ready` có thể kéo dài hàng phút vì hàng đợi hoặc đối tác.

Bởi vậy cần tối thiểu hai góc nhìn:

1. **Step execution duration**: thời gian một handler thực sự chạy. Dùng Timer để đo và xây dựng p50/p95/p99.
2. **Queue/waiting age và end-to-end latency**: tính từ các timestamp nghiệp vụ đã lưu. Dữ liệu này tiếp tục có ý nghĩa sau restart và qua những lần retry.

Không đo toàn bộ thời gian chờ hàng giờ bằng cách giữ một HTTP span hoặc transaction mở. Với luồng bất đồng bộ, nên dựa vào durable timestamps và correlation IDs.

## 5. Minh họa Java: tạo custom metrics bằng Micrometer

Ví dụ dùng MeterRegistry và các giá trị `enum` để không phát sinh nhãn tùy ý từ ID người dùng:

~~~java
package com.example.shop.observability;

import java.time.Duration;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    public enum FlowStep {
        ORDER_ACCEPTED("order_accepted", "orders"),
        PAYMENT_CAPTURE("payment_capture", "payments"),
        PAYMENT_CAPTURED("payment_captured", "payments"),
        SHIPMENT_REQUESTED("shipment_requested", "shipping"),
        SHIPMENT_READY("shipment_ready", "shipping");

        private final String id;
        private final String module;

        FlowStep(String id, String module) {
            this.id = id;
            this.module = module;
        }

        String id() { return id; }
        String module() { return module; }
    }

    private final MeterRegistry registry;

    public CheckoutMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    /** Ghi khi một trạng thái đã được chuyển thành công. */
    public void transitionSucceeded(FlowStep step) {
        Counter.builder("shop.flow.transition")
            .description("Durable business transitions observed by this process")
            .tags("flow", "checkout",
                  "step", step.id(),
                  "module", step.module(),
                  "result", "success")
            .register(registry)
            .increment();
    }

    /** Ghi cho từng lần thực thi, bao gồm cả các lần retry. */
    public void recordAttempt(
            FlowStep step, boolean success, Duration elapsed) {

        Counter.builder("shop.flow.step.attempt")
            .tags("flow", "checkout",
                  "step", step.id(),
                  "module", step.module(),
                  "outcome", success ? "success" : "failure")
            .register(registry)
            .increment();

        Timer.builder("shop.flow.step.duration")
            .description("Execution duration of one business step attempt")
            .publishPercentileHistogram()
            .tags("flow", "checkout",
                  "step", step.id(),
                  "module", step.module())
            .register(registry)
            .record(elapsed);
    }
}
~~~

Đây là **mã minh họa phần instrumentation**, chưa phải toàn bộ ứng dụng: cần import, package/API công khai và chính sách visibility phù hợp cho caller. Nếu các module khác phải dùng `CheckoutMetrics`, đặt hợp đồng đo lường trong một module quan sát được công bố hợp lệ hoặc gọi telemetry trong từng module theo thiết kế module graph; không để mã đo lường tạo dependency vòng.

Ví dụ ở tầng nghiệp vụ:

~~~java
// Ví dụ giả định repository cung cấp thao tác chuyển trạng thái có điều kiện.
// changed=true chỉ khi bản ghi thật sự chuyển sang PAYMENT_CAPTURED.
boolean changed = orders.markPaymentCapturedIfPending(orderId);
if (changed) {
    checkoutMetrics.transitionSucceeded(CheckoutMetrics.FlowStep.PAYMENT_CAPTURED);
}
~~~

**Lưu ý về transaction:** đoạn code trên minh họa thời điểm đo theo **kết quả state transition**. Nếu method còn đang trong transaction có thể rollback sau khi tăng counter, metric và database có thể lệch. Với yêu cầu chặt chẽ, hãy đo sau commit, phát tín hiệu từ transaction thành công hoặc tính KPI chính xác từ durable state. Đo sau commit cũng không đảm bảo tuyệt đối metric không mất khi process chết ngay sau commit.

Việc thống nhất quy tắc ghi metric quan trọng hơn việc dùng cùng tên class. Hãy xác định rõ mỗi metric phản ánh **attempt** hay **state transition đã commit** và kiểm tra tác động của retry.

## 6. Cấu hình Actuator, Prometheus và tracing

Một cấu hình Gradle Groovy DSL minh họa các dependency có liên quan:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Phiên bản nên được quản lý bởi Spring Boot/Spring Modulith BOM phù hợp. Nếu cần gửi trace tới backend, bổ sung tracing bridge, exporter và cấu hình endpoint theo phiên bản đang dùng; starter Insight không tự dựng collector.

Ví dụ chỉ dành cho môi trường kiểm thử có bảo vệ:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,modulith
  tracing:
    sampling:
      probability: 1.0
~~~

Trong production, chỉ expose những endpoint được yêu cầu và bảo vệ bằng network policy, authentication/authorization. `/actuator/modulith` chỉ tồn tại nếu Spring Modulith Actuator endpoint thực sự được đăng ký; khai báo trong danh sách `include` không tự tạo endpoint.

Để kiểm chứng khi ứng dụng đã chạy:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/modulith
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

**Ba kiểm tra khác nhau:**

- `/actuator/modulith`: mô hình application module được nhận diện.
- `/actuator/metrics`: các meter có trong registry lúc chạy.
- `/actuator/prometheus`: dữ liệu xuất theo định dạng Prometheus; cần Prometheus registry và quyền truy cập phù hợp.

Nếu chỉ thấy application module nhưng không có business metric, hãy kích hoạt workload tạo state transition và xác minh `CheckoutMetrics` được gọi thật. Nếu có metrics nhưng không có trace, kiểm tra instrumentation, sampling, tracing bridge, exporter và collector. Không coi một endpoint HTTP 401/403 là bằng chứng ứng dụng thiếu Actuator.

## 7. Chuyển từ metric sang câu truy vấn dashboard

Giả sử sử dụng Prometheus và Grafana. Với MeterRegistry Prometheus, các tên dạng `shop.flow.*` thường được chuẩn hóa sang snake_case; counter `shop.flow.transition` hiển thị như `shop_flow_transition_total`, timer `shop.flow.step.duration` xuất thành các series thời gian với hậu tố `_seconds`. Cần **kiểm tra tên thực tế từ `/actuator/prometheus`**, vì naming conventions và phiên bản registry có thể khác.

Các query bên dưới là ví dụ minh họa và cần sửa theo series thực tế.

### 7.1. Số đơn được chấp nhận trong một giờ

~~~promql
sum(
  increase(
    shop_flow_transition_total{
      flow="checkout",
      step="order_accepted",
      result="success"
    }[1h]
  )
)
~~~

Đây là **số transition được metric ghi nhận** trong cửa sổ, không phải truy vấn kế toán đảm bảo chính xác tuyệt đối nếu process restart hoặc exporter mất dữ liệu.

### 7.2. Số lần thử thanh toán lỗi trong năm phút

~~~promql
sum(
  increase(
    shop_flow_step_attempt_total{
      flow="checkout",
      step="payment_capture",
      outcome="failure"
    }[5m]
  )
)
~~~

Trên cùng một dashboard, thêm panel số lần thử thành công để phân biệt hệ thống hoàn toàn dừng gọi gateway với hệ thống vẫn gọi nhưng bị lỗi nhiều.

### 7.3. Tỷ lệ lỗi payment gateway theo lượt thử

~~~promql
sum(rate(shop_flow_step_attempt_total{
  flow="checkout", step="payment_capture", outcome="failure"
}[5m]))
/
clamp_min(
  sum(rate(shop_flow_step_attempt_total{
    flow="checkout", step="payment_capture"
  }[5m])),
  1e-9
)
~~~

Đây là **failure ratio theo attempt**; nếu một đơn lỗi hai lần rồi thành công ở lần thứ ba, sẽ có hai failed attempts nhưng cuối cùng đơn vẫn hoàn thành. Không diễn giải tỷ lệ này như conversion rate của đơn hàng.

### 7.4. p95 thời gian xử lý một lượt thanh toán

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(
      shop_flow_step_duration_seconds_bucket{
        flow="checkout",
        step="payment_capture"
      }[5m]
    )
  )
)
~~~

Query cần **histogram bucket** được bật, ví dụ qua `publishPercentileHistogram()` của Timer minh họa. Nếu registry không xuất `_bucket`, phải kiểm tra cấu hình histogram thực tế thay vì suy ra không có request nào. Thời gian p95 trong query tính bằng **giây**, là thời gian một attempt chứ không phải toàn bộ thời gian từ khi đơn được nhận tới lúc hoàn tất.

### 7.5. Backlog theo bước và tuổi đơn chờ lâu nhất

Nếu ứng dụng tự cung cấp gauge từ database/read model, có thể dùng:

~~~promql
sum by (step) (
  shop_flow_pending{flow="checkout"}
)
~~~

~~~promql
max by (step) (
  shop_flow_oldest_pending_age_seconds{flow="checkout"}
)
~~~

Hai tên trên là tên Prometheus minh họa cho gauge do hệ thống triển khai. Nếu dữ liệu trạng thái nằm trên nhiều replica cùng nhìn **chung một database**, không được `sum` một gauge toàn hệ thống lặp lại trên mỗi replica, vì sẽ đếm trùng. Khi đó cần chọn một nguồn xuất duy nhất hoặc tổng hợp theo cách phù hợp với semantics của gauge.

Một backlog tăng mà attempt rate vẫn ổn định có thể báo hiệu năng lực xử lý nhỏ hơn đầu vào; một backlog tăng đồng thời externalization failure tăng có thể là lỗi broker; một backlog lớn chỉ ở trạng thái `shipment_ready` có thể đến từ hệ thống giao vận chậm.

## 8. Bố cục dashboard theo hành trình

Dashboard nên có nhiều mức nhìn, từ kết quả nghiệp vụ tới điểm nghẽn kỹ thuật.

### 8.1. Lớp 1 — Tình trạng chung

Ở phần đầu trang nên có những panel đọc được trong vài giây:

| Panel | Câu hỏi | Cách thể hiện |
|---|---|---|
| Đơn đã chấp nhận | Đầu vào quy trình bao nhiêu? | Single stat + xu hướng theo giờ |
| Đơn hoàn tất theo cohort | Nhóm đơn gần đây hoàn tất đến đâu? | Tỷ lệ từ durable state, có độ trễ theo tuổi cohort |
| Đơn tồn đọng | Có bao nhiêu đơn cần xử lý tiếp? | Stat + phân bổ theo bước |
| Đơn tồn lâu nhất | Có đơn nào vượt thời gian cho phép? | Thời gian lớn nhất + mốc kỳ vọng |
| Lỗi xử lý hiện tại | Payment/shipping đang lỗi nhiều không? | Failure ratio theo attempt |
| Độ trễ đầu-cuối | Khách hàng thực sự chờ bao lâu? | p50/p95 từ timestamp nghiệp vụ |

Không nhồi mọi panel vào một màn hình. Với cửa sổ 5 phút, hiển thị trạng thái hệ thống gần thực; với cửa sổ 24 giờ, hiển thị xu hướng; với conversion theo cohort, ghi rõ **cohort bắt đầu khi nào** và những đơn chưa đủ thời gian hoàn tất.

### 8.2. Lớp 2 — Funnel có tính đến thời gian chờ

Ví dụ dữ liệu một cohort được nhận trong một giờ:

| Mốc | Số đơn của cùng cohort | Diễn giải |
|---|---:|---|
| `order_accepted` | 1.000 | Tập ban đầu |
| `payment_captured` | 940 | 60 đơn chưa thu tiền hoặc bị từ chối |
| `shipment_requested` | 925 | 15 đơn đã thu tiền nhưng chưa tạo yêu cầu giao |
| `shipment_ready` | 900 | 25 đơn đã yêu cầu nhưng còn chờ xác nhận |

Số liệu ở bảng là **giả định minh họa**, không phải dữ liệu dự án. Nếu cohort chưa đủ tuổi, phần `shipment_ready` thấp có thể chỉ là **đơn đang trong thời gian chờ hợp lệ**. Nên đặt thêm chỉ số *pending within SLO* và *pending overdue* cho từng mốc.

Funnel giúp nhìn thấy bước rơi nhiều; trace và logs dùng để chẩn đoán **vì sao**. Funnel không nên thay thế state machine chính thức của nghiệp vụ, nhất là khi có nhánh hoàn tiền, hủy đơn hoặc giao hàng thất bại.

### 8.3. Lớp 3 — Thời gian, retry và publication

Nhóm các panel theo module hoặc nghiệp vụ thay vì trộn các số không cùng đơn vị:

- **Payments:** throughput theo attempts, tỷ lệ lỗi, p95 gateway duration, số đơn chờ thu tiền quá hạn.
- **Shipping:** số event `PaymentCaptured` đã nhận, số `ShipmentRequested`, backlog, số lần giao lại và độ trễ sang trạng thái `shipment_ready`.
- **Broker/externalization:** publish acknowledgments, failure rate, consumer lag và publication pending/failed nếu dùng Event Publication Registry.
- **Trace quality:** có span qua module boundary không, các trace bị thiếu context ở đâu, exporter có gửi được không.

Đừng gộp **application events published**, **Kafka records published** và **consumer processing completed** thành một metric “event success”. Ba số này phản ánh các thời điểm và bảo đảm khác nhau.

### 8.4. Lớp 4 — Drill-down theo transaction cụ thể

Khi một panel báo lỗi, người trực vận hành cần nhấp hoặc lọc theo thông tin đã được phép truy cập để đi đến:

1. Danh sách các đơn tồn đọng hoặc lỗi trong cửa sổ thời gian.
2. Log tập trung với `orderId`, `eventId` hoặc `correlationId` đã được kiểm soát.
3. Một trace có span của HTTP request, module entry và handler tương ứng.
4. Tình trạng message ở broker và publication registry nếu sự cố liên quan đến externalization.
5. Hành động phục hồi: retry có kiểm soát, bù trừ hoặc hỗ trợ thủ công theo quy trình.

Một dashboard chỉ có tổng số lỗi nhưng không hỗ trợ liên hệ đến các sự kiện cụ thể sẽ mất phần lớn giá trị khi xử lý sự cố.

## 9. Liên kết module graph với observability

Cách tổ chức của Spring Modulith rất phù hợp để tạo bản đồ định vị sự cố:

~~~mermaid
flowchart TB
    subgraph Static["Bằng chứng kiến trúc"]
        SRC["ApplicationModules + Documenter"]
        ACT["Actuator /actuator/modulith"]
    end
    subgraph Runtime["Bằng chứng runtime"]
        EVT["Application event metrics"]
        BIZ["Custom business metrics"]
        TR["Spans + structured logs"]
        REG["Publication registry / broker state"]
    end
    SRC --> MAP["Bản đồ module + luồng nghiệp vụ"]
    ACT --> MAP
    EVT --> BOARD["Dashboard / cảnh báo"]
    BIZ --> BOARD
    TR --> BOARD
    REG --> BOARD
    MAP -. "đối chiếu module, event và owner" .-> BOARD
~~~

Trong thực hành, hãy lưu một bản **module graph baseline** (được sinh từ version đang triển khai) và đối chiếu sau mỗi lần sửa kiến trúc. Nếu thêm dependency trực tiếp từ shipping tới implementation nội bộ của payments, dashboard vẫn có thể “xanh” dù ranh giới module đã bị phá. Các kiểm thử `ApplicationModules.verify()` và tài liệu module graph giúp phát hiện khía cạnh kiến trúc mà runtime metric không bao phủ.

Với Insight starter và cấu hình observability tương ứng, trace có thể chứa thông tin module entry. Tên và cấu trúc thuộc tính span tùy phiên bản; hãy xem các span thực tế trước khi xây filter cứng cho `module.identifier`, `module.name` hoặc `module.method`. Metric/trace giúp biết **luồng có chạy**, còn module graph giúp biết **luồng có phù hợp thiết kế hay không**.

### 9.1. Ranh giới trace khi xử lý bất đồng bộ

Giả sử orders phát event trong transaction T1, listener payments chạy sau commit trên một executor khác:

- T1 đã commit thì listener lỗi không tự rollback T1.
- Current span là context theo thread; nếu executor không propagate, listener có thể bắt đầu trace riêng.
- Context propagation có thể dùng task decorator hoặc cơ chế được phiên bản Spring Boot/Framework hỗ trợ; phải kiểm tra executor thực tế.
- Khi sự kiện externalize qua Kafka, producer/consumer cần observation và cơ chế inject/extract trace headers tương thích.
- Khi publication được replay sau restart, trace của request cũ có thể đã đóng; một trace mới là điều hợp lệ.

Vì vậy hãy dùng **`eventId` và `correlationId`** để nối các lần xử lý nghiệp vụ qua thời gian. `traceId` phục vụ phân tích lần thực thi, không phải khóa duy nhất của toàn bộ quy trình.

## 10. Đặt SLI, SLO và cảnh báo có ý nghĩa

**SLI (Service Level Indicator)** là đại lượng đo được. **SLO (Service Level Objective)** là mục tiêu cho đại lượng ấy trong một cửa sổ thời gian. Ví dụ:

| SLI | SLO minh họa | Nguồn |
|---|---|---|
| Tỷ lệ thu tiền thành công theo attempt | ≥ 99% trong 30 phút, nếu lỗi do hệ thống | `shop.flow.step.attempt` có phân loại lỗi |
| p95 xử lý payment attempt | Dưới 2 giây trong 15 phút | Timer histogram |
| Số đơn chờ shipping quá hạn | 0 đơn quá 15 phút trong môi trường thử | Durable pending state |
| Tuổi publication cần retry | Dưới 5 phút | Event Publication Registry |
| Tỷ lệ hoàn tất theo cohort | ≥ 98% sau 1 ngày | Cohort truy vấn từ database/read model |

Các ngưỡng trong bảng chỉ là **giả định để học thiết kế**, không phải chuẩn bắt buộc của Spring Modulith. Trong production cần dựa trên yêu cầu nghiệp vụ, mùa vụ lưu lượng, lịch vận hành đối tác và khả năng dữ liệu đến trễ.

Đối với payment gateway, phải phân biệt lỗi kỹ thuật (`timeout`, `connection_error`) với từ chối thanh toán hợp lệ (`declined`). Nếu gộp hai loại này, hệ thống có thể phát cảnh báo sai khi khách hàng nhập thông tin thanh toán không hợp lệ.

**Gợi ý tổ chức cảnh báo:** cảnh báo ưu tiên dựa trên kết quả khách hàng bị ảnh hưởng (đơn chờ quá hạn) và một số chỉ báo sớm (tỷ lệ lỗi gateway, publication backlog), sau đó liên kết panel kỹ thuật để điều tra. Tránh alert riêng cho mỗi meter, vì một sự cố broker có thể khiến hàng chục alert báo động đồng thời.

### 10.1. Cảnh báo ví dụ theo pending age

Với gauge `shop_flow_oldest_pending_age_seconds` được xuất đúng semantics, một biểu thức giả định:

~~~promql
max(
  shop_flow_oldest_pending_age_seconds{
    flow="checkout",
    step="shipping"
  }
) > 900
~~~

Điều này tương đương **tuổi chờ lớn nhất trên 15 phút**. Trong cấu hình alert rule, có thể kết hợp `for:` và điều kiện tối thiểu lưu lượng để giảm nhiễu. Nếu gauge mất dữ liệu, biểu thức có thể không trả series; cần một cảnh báo riêng cho mất scrape/telemetry, không coi “không có số liệu” là “không có pending”.

## 11. Kịch bản kiểm chứng dashboard

Kiểm thử một dashboard cần cả **độ đúng dữ liệu** và **hành vi điều tra**. Trước khi test, chuẩn bị bộ dữ liệu đơn hàng thử có timestamp rõ ràng, tracing backend/metric registry và message broker nếu luồng có externalization.

| Mã | Hành động | Kết quả cần xác nhận |
|---|---|---|
| D1 | Một đơn đi qua mọi bước, không lỗi | Bốn mốc có trạng thái đúng; metrics tương ứng xuất hiện; end-to-end duration được xác định |
| D2 | Payment timeout một lần rồi retry thành công | Attempt counter tăng cho lỗi và thành công; business `payment_captured` chỉ ghi nhận một trạng thái |
| D3 | Đơn bị từ chối thanh toán hợp lệ | Dashboard phân loại thành business rejection, không mặc định là lỗi hạ tầng |
| D4 | Transaction orders rollback | Không có business `order_accepted` đã commit hoặc message after-commit tương ứng |
| D5 | Broker tạm không thể kết nối | Publication pending/failure và producer error có thể điều tra, không đánh dấu shipment hoàn tất |
| D6 | Broker khôi phục và gửi lại cùng `eventId` | Consumer idempotent, dashboard không đếm trùng business transition |
| D7 | Listener bất đồng bộ chạy không có context propagation | Trace có thể tách; vẫn liên kết được logs qua eventId/correlationId |
| D8 | Bật propagation và instrument broker | Kiểm tra trace/span linkage bằng message thực; không chỉ bằng cấu hình |
| D9 | Restart ứng dụng, rồi replay publication tồn đọng | Có trace mới nhưng event/correlation ID vẫn giúp điều tra; pending giảm khi xử lý xong |
| D10 | Thay đổi cấu trúc module trái quy tắc | `ApplicationModules.verify()` hoặc kiểm tra kiến trúc phát hiện; dashboard runtime không được xem là thay thế |
| D11 | Tạo 100 đơn thuộc một cohort, trong đó có đơn trễ | Funnel cohort và chỉ số quá hạn phản ánh đúng nhóm, không trộn với đơn ở cửa sổ khác |
| D12 | Tắt scrape metric hoặc collector | Dashboard hiển thị mất dữ liệu/unknown, không diễn giải là 0 lỗi hoặc 100% thành công |

Đối với dashboard dùng Prometheus, kiểm tra cả tên series thật, nhãn, đơn vị, kiểu counter/gauge và scrape interval. Một số query vẫn trả kết quả hợp lệ về cú pháp nhưng sai về ý nghĩa nếu metric đã được đổi tên hoặc bị nhân bản trên nhiều replica.

### 11.1. Cách đánh giá một trường hợp thành công

Khi hoàn tất một đơn thử, hãy có **bốn loại bằng chứng**:

1. **Durable state:** order được chấp nhận, payment captured và shipment ready đúng một lần.
2. **Application telemetry:** business counters/timers được ghi nhận; event metrics của Modulith chỉ phản ánh hoạt động phát event khi instrumentation hỗ trợ.
3. **Tracing/logs:** xác định được các module/handler chính, độ trễ và mối liên kết qua thread/broker.
4. **Module architecture:** các dependency giữa modules phù hợp với đồ thị kiến trúc và bài test cấu trúc.

Nếu chỉ xem dashboard “xanh” mà bỏ qua durable state, việc giao nhận trùng, retry và báo cáo sai conversion có thể không được phát hiện.

## 12. Ví dụ điều tra một sự cố thực tế

Trong 30 phút gần nhất, dashboard cho biết:

- `order_accepted` ổn định.
- `payment_capture` có p95 thấp, failure ratio gần như không đổi.
- `shipment_requested` vẫn tăng.
- `shipment_ready` tăng chậm và `oldest_pending_age_seconds` vượt ngưỡng.
- Kafka producer errors bằng 0, nhưng consumer lag tăng.

Trình tự điều tra hợp lý:

1. Khoanh vùng bottleneck **sau khi đã gửi yêu cầu giao hàng**; tránh kết luận module orders lỗi chỉ vì khách hàng thấy trạng thái đơn bị chậm.
2. Kiểm tra trạng thái publication registry để biết bên phát đã giao event thành công hay còn phải resubmit.
3. Xem consumer lag, error logs, eventId và các trường hợp retry/duplicate của consumer hoặc đối tác.
4. Mở trace của các lần xử lý gần đây; khi không còn trace gốc do asynchronous retry, dùng correlationId và durable timestamps.
5. Kiểm tra số đối tượng pending quá hạn theo cohort/đơn, sau đó lập hành động giảm tồn đọng, xử lý poison message hoặc khôi phục consumer.
6. Sau khi xử lý, xác nhận pending giảm, end-to-end latency cải thiện và business state được cập nhật; không chỉ xác nhận Kafka lag về 0.

Tình huống minh họa này cho thấy dashboard theo luồng nghiệp vụ có thể dẫn người vận hành từ **mức độ ảnh hưởng tới đơn hàng** đến **một ranh giới kỹ thuật cụ thể** bằng cách kết hợp metric, trace, registry và trạng thái bền vững.

## 13. Checklist thiết kế và bài tập áp dụng

Trước khi công bố dashboard, hãy tự kiểm tra:

- Có xác định owner của từng mốc nghiệp vụ và ý nghĩa “thành công” không?
- Có phân biệt `attempt`, business transition, application event publication và broker acknowledgment không?
- Có phân biệt conversion theo cohort với tỷ lệ xử lý trong cửa sổ thời gian không?
- Các metric có đơn vị rõ ràng, nhãn hữu hạn và cách tổng hợp đúng trong triển khai nhiều replica không?
- Có dashboard pending/oldest age để thấy các trường hợp *không xảy ra bước tiếp theo* không?
- Có liên kết tới log/trace theo ID hợp lệ, kể cả lúc retry sau restart không?
- Có kiểm tra ranh giới module bằng graph và architecture test, ngoài runtime telemetry không?
- Alert có phản ánh tác động tới khách hàng và mục tiêu SLO không?
- Tài nguyên Actuator, metric exporter và log truy vết đã được bảo vệ không?

**Bài tập:** dựng dashboard cho quy trình `orders → payments → shipping` từ một ứng dụng Spring Modulith. Tạo các business metrics theo thiết kế ở mục 4, thêm một panel Actuator/kiến trúc tham chiếu module graph, một funnel có cohort, các panel attempt failure, p95 và pending age. Tiếp theo tạo ba kịch bản: **thành công**, **payment retry**, **broker/consumer bị chậm**. Với mỗi kịch bản, thu dữ liệu từ database, Actuator/Prometheus, trace và log; giải thích mỗi panel đo điều gì, đơn vị nào và vì sao nó cho phép xác định bottleneck.

**Sản phẩm nghiệm thu:** một ảnh hoặc cấu hình dashboard, bảng định nghĩa KPI/SLI/SLO, module graph, bộ query đã xác minh tên series thật, và ba bản ghi điều tra có mã tương quan đã được ẩn danh. Kết luận phải dựa trên trạng thái nghiệp vụ và bằng chứng runtime, không chỉ dựa vào việc ứng dụng đã bật observability dependency.

## Tài liệu tham khảo

- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): sinh tài liệu ranh giới và sơ đồ ứng dụng.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Actuator, module observability và event metrics.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): listeners, event publication registry và externalization.
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure và kiểm soát truy cập.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): metrics, tracing và context propagation.
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): Counter, Timer, Gauge, tags và registry.
- [Prometheus — Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): lựa chọn window, rate, increase và nhãn.
