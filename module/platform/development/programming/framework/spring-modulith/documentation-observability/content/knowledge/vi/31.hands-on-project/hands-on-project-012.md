# Xây dashboard và runbook cho production

## Mục tiêu bài thực hành

Trong hệ thống Spring Boot được tổ chức bằng **Spring Modulith**, một request HTTP có thể đi qua nhiều **application module**, phát domain event, chuyển sang thread bất đồng bộ rồi externalize thông điệp tới broker. Một dashboard chỉ hiển thị CPU hoặc số lần HTTP trả lỗi không đủ để trả lời câu hỏi: *“Người dùng có nhận được kết quả nghiệp vụ chưa, luồng đang mắc ở module nào và xử lý sự cố ra sao?”*

Bài **Xây dashboard và runbook cho production** thuộc chương **Thực hành tổng hợp**, trong phạm vi **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: tạo tài liệu ranh giới module, dùng **module graph**, **Spring Boot Actuator**, **event metrics**, **distributed tracing** và **context propagation** để kiểm chứng kiến trúc và hoạt động thật của ứng dụng.

Sau bài học, người học sẽ có một bản thiết kế đủ cụ thể để triển khai và vận hành:

1. Bản đồ luồng nghiệp vụ, application module, event, transaction và điểm tích hợp ngoài.
2. Bộ SLI/SLO, metric contract, dashboard có các panel ưu tiên và lối đi từ tổng quan tới chi tiết.
3. Cảnh báo liên kết trực tiếp tới runbook theo tình huống và mức độ ảnh hưởng.
4. Quy trình điều tra, giảm tác động, khôi phục, đối soát và xác nhận hết sự cố.
5. Bộ tiêu chí nghiệm thu gồm trạng thái nghiệp vụ, metrics, logs, traces, Actuator và Event Publication Registry.
6. Quy tắc giới hạn dữ liệu nhạy cảm, kiểm soát chi phí và quyền truy cập cho production.

> **Quy ước:** ứng dụng bán hàng minh họa gồm `orders`, `payments`, `shipping`; dùng Kafka cho tích hợp ngoài. Các meter `shop.*`, tên alert, ngưỡng SLO và tên bảng trong bài là **thiết kế ví dụ**, không phải tính năng Spring Modulith tự sinh. Chỉ số do Spring Modulith cung cấp, tên thuộc tính span và cấu hình exporter cần đối chiếu đúng phiên bản thư viện và hệ thống telemetry đang chạy.

## 1. Chọn luồng nghiệp vụ trước khi chọn dashboard

Ta theo dõi quy trình từ khi khách đặt đơn đến khi hệ thống xác nhận yêu cầu giao hàng:

~~~mermaid
flowchart LR
    HTTP["HTTP POST /orders"] --> ORD["orders<br/>Đơn đã chấp nhận"]
    ORD -->|"OrderPlaced"| PAY["payments<br/>Đã thu tiền"]
    PAY -->|"PaymentCaptured"| SHIP["shipping<br/>Đã tạo yêu cầu giao"]
    SHIP -->|"ShipmentRequested"| KAFKA[("Kafka / broker")]
    KAFKA --> EXT["Đối tác giao vận"]
    EXT -->|"ShipmentAccepted"| DONE["shipping<br/>Đối tác đã tiếp nhận"]
~~~

Trong ứng dụng mẫu:

- **orders** sở hữu tính hợp lệ và trạng thái đơn hàng.
- **payments** sở hữu kết quả thu tiền và quyết định retry/bù trừ khi thanh toán thất bại.
- **shipping** sở hữu trạng thái yêu cầu giao hàng và phản hồi từ đối tác.
- **Kafka** xác nhận việc gửi message tới broker; điều đó chưa đồng nghĩa đối tác đã chấp nhận vận chuyển.
- **Event Publication Registry** của Spring Modulith, khi được cấu hình, theo dõi những publication tới transactional listeners và việc hoàn thành chúng; registry không thay thế trạng thái cuối cùng trong hệ thống đối tác.

Mỗi bước có thể thực thi trong transaction và thread riêng. Ví dụ `@ApplicationModuleListener` thường chạy bất đồng bộ, sau commit và trong transaction mới. Vì vậy, lỗi xử lý thanh toán không tự rollback transaction đã tạo đơn; đó là tình huống nghiệp vụ cần bộc lộ trên dashboard, không phải chỉ dấu duy nhất cho lỗi HTTP.

### 1.1. Hợp đồng đo lường cho từng mốc

| Mốc | Module sở hữu | Dấu hiệu hoàn thành bền vững | Tình trạng có thể tồn đọng |
|---|---|---|---|
| `order_accepted` | orders | Order đã commit ở trạng thái accepted | Không áp dụng sau khi đã chấp nhận |
| `payment_captured` | payments | Transaction/ledger thanh toán đã xác nhận capture | `awaiting_payment` |
| `shipment_requested` | shipping | Yêu cầu giao hàng đã được lưu | `awaiting_shipping` |
| `shipment_published` | integration | Broker xác nhận gửi record theo chính sách producer | `awaiting_externalization` |
| `shipment_accepted` | shipping | Phản hồi từ đối tác được lưu và đối soát | `awaiting_partner` |

**Phân biệt bốn sự kiện:** application event được phát, publication registry hoàn thành, broker nhận message, và đối tác xử lý nghiệp vụ thành công. Bốn kết quả có thể xảy ra ở các thời điểm khác nhau; không nên gom thành một thước đo “event thành công”.

### 1.2. Đối chiếu ranh giới module

Spring Modulith có thể dựng mô hình `ApplicationModules`, kiểm tra phụ thuộc và sinh tài liệu module bằng **Documenter**. Với Actuator support tương ứng, endpoint `/actuator/modulith` có thể cung cấp thông tin module được nhận diện trên instance chạy thật.

Bản đồ kiến trúc là **baseline**: orders công bố event, payments và shipping đăng ký các listener hợp lệ, không truy cập trực tiếp vào implementation nội bộ của module khác.

Đồ thị module kiểm chứng cấu trúc, còn traces và metrics kiểm chứng những đường chạy thật. Một luồng có đầy đủ trace vẫn có thể phá ranh giới module; một module không xuất hiện trong trace có thể chỉ vì sampling hoặc chưa phát sinh request.

## 2. Deliverables của dự án

Đầu ra của bài thực hành gồm một bộ tài liệu và cấu hình có thể review:

| Thành phần | Nội dung phải có | Chủ sở hữu |
|---|---|---|
| Module/flow map | Module, event, transaction, broker, điểm kết thúc nghiệp vụ | Tech lead + người sở hữu nghiệp vụ |
| Metric catalog | Tên, đơn vị, kiểu, labels, nguồn, điều kiện tạo metric | Development + SRE |
| SLI/SLO sheet | Công thức, cửa sổ đánh giá, threshold, cách xử lý thiếu dữ liệu | Product + SRE |
| Dashboard | Tổng quan, funnel theo cohort, queue/backlog, latency, dependency và drill-down | SRE + Development |
| Alert rules | Mức độ ưu tiên, biểu thức, thời gian `for`, runbook URL | SRE |
| Runbooks | Triệu chứng, điều tra, giảm tác động, phục hồi, xác nhận và escalation | Owner của module |
| Verification report | Test input, evidence, kết quả PASS/FAIL, giới hạn còn tồn tại | QA + SRE |

Không cần công bố chính xác những giá trị nhạy cảm như token, kết nối nội bộ hay thông tin khách hàng trong các deliverables. Người vận hành chỉ cần biết nơi truy cập an toàn và cách kiểm tra hệ thống.

## 3. Chọn SLI/SLO dựa trên trải nghiệm người dùng

**SLI** là đại lượng đo được. **SLO** là mức mục tiêu của SLI trong một khoảng thời gian. Thiết kế tham khảo:

| SLI | SLO minh họa | Cách đo | Cảnh báo liên quan |
|---|---|---|---|
| HTTP request thành công | ≥ 99,9% trong 30 ngày | HTTP server requests đã phân loại lỗi theo nghiệp vụ | `SHOP-HTTP-ERROR-RATE` |
| Thu tiền thành công về mặt kỹ thuật | ≥ 99% attempts không lỗi hạ tầng trong 1 giờ | Attempts đã phân loại outcome | `SHOP-PAYMENT-ERROR-RATE` |
| p95 thời gian một payment attempt | Dưới 2 giây trong 15 phút | Timer/histogram gateway call | `SHOP-PAYMENT-LATENCY` |
| Đơn chờ xử lý quá thời hạn | Không có đơn `awaiting_shipping` quá 15 phút | Durable state + timestamp | `SHOP-SHIPPING-OVERDUE` |
| Tuổi publication chưa hoàn tất | Dưới 5 phút ở steady state | Publication Registry | `SHOP-PUBLICATION-STALE` |
| Tỷ lệ đơn hoàn tất theo cohort | ≥ 98% sau 24 giờ | Read model từ cùng cohort accepted | Báo cáo vận hành và cảnh báo theo policy |

Đây là **con số học tập**, không phải cam kết chung cho mọi hệ thống. Trong production phải thỏa thuận với chủ nghiệp vụ dựa trên thời gian thanh toán, cam kết đối tác, giờ cao điểm và thời gian event có thể đến trễ.

Tránh dùng số `shipment_accepted` trong 5 phút chia số `order_accepted` trong cùng 5 phút như conversion rate. Hai tập có thể không phải cùng những đơn hàng. **Conversion cần theo cohort**, ví dụ nhóm đơn được nhận từ 08:00–09:00 và theo dõi phần trăm trong nhóm đạt `shipment_accepted` sau 24 giờ.

### 3.1. Định nghĩa attempt, transition và waiting

Ba góc nhìn bổ sung cho nhau:

- **Attempt:** mỗi lần gọi hệ thống thanh toán, gồm cả retry. Dùng đo sức khỏe của thành phần kỹ thuật.
- **State transition:** một lần thay đổi trạng thái nghiệp vụ đã commit. Dùng đo tiến trình một đơn hàng; phải idempotent để tránh đếm hai lần.
- **Waiting age/backlog:** số đơn đang chờ và thời gian chờ của chúng. Dùng phát hiện các sự cố *không tạo ra request lỗi mới* nhưng âm thầm làm đơn tồn.

Business metrics trong bộ nhớ có thể bị mất khi tiến trình crash trước lần scrape. Báo cáo đối soát tiền hoặc số đơn chính xác phải truy vấn **durable state/ledger**, còn các metrics phục vụ giám sát xu hướng và alert sớm.

## 4. Đặt tên metric và giới hạn labels

Bộ metric ví dụ:

| Meter (Micrometer) | Kiểu | Nhãn có cardinality thấp | Ý nghĩa |
|---|---|---|---|
| `shop.checkout.attempt` | Counter | `step`, `outcome` | Lượt gọi tại một bước, có retry |
| `shop.checkout.step.duration` | Timer | `step` | Thời gian xử lý của một attempt |
| `shop.checkout.transition` | Counter | `state`, `result` | Chuyển trạng thái nghiệp vụ được quan sát |
| `shop.checkout.pending` | Gauge | `state` | Số đơn chờ ở trạng thái tương ứng |
| `shop.checkout.oldest.pending.age.seconds` | Gauge | `state` | Tuổi đơn chờ lâu nhất tính bằng giây |
| `shop.publication.pending` | Gauge | `target`, `state` | Publication tồn đọng/thất bại, do ứng dụng tự xuất |
| `shop.externalization.attempt` | Counter | `target`, `outcome` | Số lần producer thử gửi tới broker |

Với Spring Modulith observability, có thể gặp **`module.events.published`** và các metrics theo module/loại event tùy phiên bản. Chúng đo phát event trong ứng dụng, **không** đồng nhất với `shop.externalization.attempt` hay broker acknowledgments.

Quy tắc đặt nhãn:

- `step`, `state`, `module`, `outcome` sử dụng enum hoặc tập giá trị được quản lý; không lấy tên động từ payload.
- **Không đặt `orderId`, `eventId`, `traceId`, customer email làm labels**; chúng sinh vô số series và có thể rò rỉ thông tin.
- `orderId/eventId/correlationId` thuộc logs/trace hoặc dữ liệu truy vấn có kiểm soát quyền truy cập.
- Mỗi metric phải ghi rõ **đơn vị**, nguồn, thời điểm cập nhật và cách tổng hợp khi chạy nhiều replica.

### 4.1. Mã minh họa ghi nhận attempt

Đây là lớp thu thập dữ liệu độc lập với việc đo durable state:

~~~java
package com.example.shop.observability;

import java.time.Duration;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class CheckoutAttemptMetrics {

    public enum Step {
        PAYMENT_CAPTURE("payment_capture"),
        SHIPMENT_REQUEST("shipment_request");

        private final String id;
        Step(String id) { this.id = id; }
        public String id() { return id; }
    }

    private final MeterRegistry registry;

    public CheckoutAttemptMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(Step step, boolean success, Duration elapsed) {
        Counter.builder("shop.checkout.attempt")
            .description("Number of technical step attempts")
            .tags("step", step.id(),
                  "outcome", success ? "success" : "error")
            .register(registry)
            .increment();

        Timer.builder("shop.checkout.step.duration")
            .description("Duration of each step attempt")
            .publishPercentileHistogram()
            .tag("step", step.id())
            .register(registry)
            .record(elapsed);
    }
}
~~~

Mã trên không tự lấy thời gian hoặc phân biệt lỗi business vs infrastructure; caller phải đo `Duration` và phân loại `success` đúng theo hợp đồng. Ví dụ `payment_declined` có thể là một **kết quả hợp lệ của nghiệp vụ**, không nên tính thành lỗi hạ tầng nếu SLO là availability của gateway.

Nếu code từ module payments sử dụng lớp quan sát ở package riêng, hãy thiết kế một **public API module observability** hợp lệ và xác nhận bằng kiểm thử ranh giới Modulith. Tránh cho telemetry trở thành nguồn gây phụ thuộc vòng.

### 4.2. Gauge backlog phải có nguồn dữ liệu rõ

Một Gauge được đọc từ bộ nhớ riêng của từng instance có thể sai nếu mỗi replica chỉ giữ một phần trạng thái. Một Gauge trên mỗi instance cùng truy vấn **toàn bộ** database cũng có thể bị nhân nhiều lần nếu dashboard dùng `sum`.

Các lựa chọn thực tế:

1. Định kỳ dựng snapshot từ read model/DB rồi xuất qua **một metrics exporter** chuyên biệt.
2. Nếu mỗi replica chỉ sở hữu một partition riêng, gắn label shard rõ ràng và chỉ cộng khi tập partition là duy nhất.
3. Nếu nhiều instance đều trả một **giá trị toàn cục giống nhau**, dùng `max` hoặc chọn một exporter chính; không `sum` bừa bãi.

Gauge `oldest.pending.age.seconds` phải tính bằng **thời gian hiện tại trừ thời điểm vào trạng thái**, không dùng thời điểm event producer bắt đầu gửi nếu muốn đo thời gian khách hàng phải chờ.

## 5. Tích hợp Spring Modulith, Actuator và observability

Ví dụ Gradle Groovy DSL với phiên bản được BOM phù hợp quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Nếu ứng dụng thực sự externalize qua Kafka:
    implementation 'org.springframework.modulith:spring-modulith-events-kafka'

    // Cần thêm tracing bridge và exporter tương thích với Boot BOM.
}
~~~

Ví dụ cấu hình trong **môi trường kiểm thử có kiểm soát**:

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
        include: health,info,metrics,prometheus,modulith
  tracing:
    sampling:
      probability: 1.0
~~~

Trong production, giảm sampling theo nhu cầu, giới hạn Actuator exposure và bảo vệ endpoint bằng authentication/authorization cùng network policy. **Insight starter không tự tạo collector hoặc tracing exporter**. Cần lắp Micrometer Tracing bridge, exporter và backend phù hợp (chẳng hạn OTLP) rồi kiểm tra thực tế.

Để module graph phản ánh kiến trúc mong muốn, dùng kiểm thử Spring Modulith, ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ShopApplication` là Spring Boot application class của ví dụ; điều chỉnh trong dự án thực. Test trên **kiểm tra cấu trúc module**, chưa phải test metric hay trace. Có thể dùng Spring Modulith **Documenter** để sinh tài liệu module graph ở một bước build/test riêng và lưu artifact cho review.

### 5.1. Nguồn bằng chứng tại runtime

Trong môi trường test có quyền truy cập:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/modulith
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

Mỗi endpoint có ý nghĩa khác nhau:

| Nguồn | Trả lời được | Không chứng minh |
|---|---|---|
| Module graph / `/actuator/modulith` | Module nào được nhận diện, quan hệ/module information | Một event thực tế đã chạy |
| `/actuator/metrics` | Meter nào đã được tạo trong runtime | Broker đã xác nhận record |
| `/actuator/prometheus` | Series được exporter cung cấp | Conversion nghiệp vụ chính xác tuyệt đối |
| Distributed trace | Các span thực thi, độ trễ và liên kết theo trace context | Không bị mất event khi restart |
| Event Publication Registry | Publication nào hoàn tất/chưa hoàn tất/thất bại tùy triển khai | Đối tác bên ngoài đã xử lý nghiệp vụ |
| Durable business state | Đơn đã đạt mốc nghiệp vụ nào | Đường đi chi tiết của từng lần gọi |
| Kafka producer/consumer metrics | Hoạt động gửi, nhận, lag, lỗi transport | Hành động cuối cùng của người dùng thành công |

Nếu `/actuator/modulith` trả **404**, kiểm tra dependency/registration/exposure/base-path. Nếu trả **401/403**, đó có thể là chính sách bảo vệ đúng. Khi metric không xuất hiện, xác minh đã tạo workload phát event, đúng tên metric và có registry; nhiều meter chỉ xuất hiện **sau lần sử dụng đầu tiên**.

## 6. Thiết kế dashboard production thành bốn lớp

Tách dashboard theo độ sâu điều tra giúp người trực vận hành không phải nhìn hàng chục đồ thị cùng lúc.

### Lớp A — Trạng thái khách hàng và dịch vụ

Panel đầu trang nên trả lời ngay:

| Panel | Hiển thị | Cách diễn giải |
|---|---|---|
| Accepted orders trong 1 giờ | Số lần chuyển `order_accepted` hoặc read model | Thông lượng đầu vào |
| Completed order cohort | % của cùng cohort đã đạt `shipment_accepted` sau 24 giờ | Kết quả nghiệp vụ |
| Pending by state | Số đơn chờ ở từng mốc | Điểm nghẽn |
| Oldest pending age | Giây chờ lâu nhất mỗi mốc | Rủi ro quá hạn |
| Payment gateway error ratio | % lỗi theo **attempt** | Độ ổn định thành phần |
| HTTP error budget | Availability SLI và burn rate nếu đã định nghĩa | Tác động đến request đồng bộ |

Mỗi panel phải ghi **đơn vị**, cửa sổ thời gian, độ trễ dữ liệu, nhãn môi trường và runbook liên quan. Đừng hiển thị dữ liệu thiếu như số `0` thành công: `no data`, `stale` và `zero` là ba trạng thái khác nhau.

### Lớp B — Funnel và độ trễ theo hành trình

Theo dõi một **cohort** đơn đã được chấp nhận trong cùng cửa sổ, rồi đo số đơn đạt từng mốc. Ví dụ giả định:

| Mốc | Đơn trong cohort ban đầu 1.000 | Cần tìm hiểu |
|---|---:|---|
| `order_accepted` | 1.000 | Mốc gốc |
| `payment_captured` | 960 | 40 chưa thanh toán/không đạt |
| `shipment_requested` | 945 | 15 đang chờ tạo yêu cầu giao |
| `shipment_accepted` | 910 | 35 chờ đối tác xác nhận |

Các số là **dữ liệu minh họa**. Đối với cohort chưa đủ 24 giờ, sự chênh lệch chưa chắc là lỗi. Bổ sung cột `within_SLO` và `overdue` hoặc biểu đồ phân bố tuổi chờ.

Về độ trễ, tách:

- **Execution duration** của một attempt: đo bằng Timer, hữu ích để phát hiện latency của payment gateway.
- **Queue delay**: từ lúc vào trạng thái chờ đến lúc handler bắt đầu.
- **Business end-to-end latency**: từ khi đơn accepted đến lúc đối tác xác nhận; tính từ timestamp bền vững.

### Lớp C — Event publication, broker và worker

Nhóm panel kỹ thuật theo điểm giao tiếp:

- Application event publication rate theo module/type.
- Số publication pending/failed/stale ở registry, tuổi bản ghi cũ nhất.
- Kafka send rate, send errors, latency, consumer lag theo topic/group.
- Số lần handler retry và lỗi phân loại.
- Worker thread/executor saturation nếu được instrument.
- Phân bố độ trễ xử lý nội bộ so với thời gian chờ ngoài.

Trong Spring Modulith, một application event được phát **khác** với event externalization hoàn thành. Producer Kafka có ack thành công **khác** với việc consumer cập nhật durable state. Dashboard phải diễn đạt đúng từng mốc này.

### Lớp D — Drill-down để xử lý một đơn bị kẹt

Từ panel overdue, cho phép người có quyền:

1. Mở tập đơn tồn đọng từ read model, được giới hạn thời gian và lọc dữ liệu nhạy cảm.
2. Xem `orderId`, `eventId`, `correlationId`, trạng thái hiện tại và lần cập nhật cuối.
3. Mở log/trace tương ứng theo ID đã được phép tra cứu.
4. Đối chiếu trạng thái publication và broker.
5. Xem bước xử lý tiếp theo có thể làm theo runbook: kiểm tra dependency, retry an toàn hoặc báo người sở hữu nghiệp vụ.

Không lưu payload khách hàng đầy đủ, thông tin thanh toán, token hoặc private key trong span/log chỉ để thuận tiện drill-down.

## 7. Ví dụ PromQL cho những panel quan trọng

Trong Prometheus registry, `shop.checkout.attempt` dạng Counter thường xuất ra `shop_checkout_attempt_total`; Timer `shop.checkout.step.duration` có thể xuất `shop_checkout_step_duration_seconds_bucket` khi bật histogram. Hãy **xem tên series thực tế ở `/actuator/prometheus`** trước khi sao chép query: naming conventions và cấu hình registry có thể ảnh hưởng tên đầu ra.

### 7.1. Lỗi payment attempt trong năm phút

~~~promql
sum(
  increase(
    shop_checkout_attempt_total{
      step="payment_capture",
      outcome="error"
    }[5m]
  )
)
~~~

### 7.2. Tỷ lệ lỗi theo attempt (không phải conversion)

~~~promql
sum(rate(shop_checkout_attempt_total{
  step="payment_capture", outcome="error"
}[5m]))
/
clamp_min(
  sum(rate(shop_checkout_attempt_total{
    step="payment_capture"
  }[5m])),
  1e-9
)
~~~

Để giảm cảnh báo ở giai đoạn hầu như không có lưu lượng, kết hợp thêm điều kiện tối thiểu về tổng attempts trong cửa sổ.

### 7.3. p95 xử lý payment attempt

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(
      shop_checkout_step_duration_seconds_bucket{
        step="payment_capture"
      }[5m]
    )
  )
)
~~~

Đây là **thời gian thực thi một attempt** theo giây. Nếu chưa bật histogram hoặc tên series khác, query có thể không trả dữ liệu. Không diễn giải khoảng trống thành kết quả `0 giây`.

### 7.4. Tuổi pending shipping cao nhất

~~~promql
max(
  shop_checkout_oldest_pending_age_seconds{
    state="awaiting_shipping"
  }
)
~~~

Metric được thiết kế từ `shop.checkout.oldest.pending.age.seconds` trong bảng ở mục 4. Nếu nhiều replica cùng xuất một **giá trị toàn cục**, dùng `max` tránh nhân số lượng như phép `sum`; với partition độc lập, cần thiết kế phép tổng hợp riêng.

### 7.5. Publication pending

~~~promql
max(
  shop_publication_pending{
    target="externalization",
    state="pending"
  }
)
~~~

Tên series này là **ví dụ của gauge tự triển khai**. Trạng thái và schema cụ thể của Event Publication Registry phụ thuộc phiên bản Spring Modulith và cơ chế lưu trữ. Không giả định Spring Modulith mặc định xuất sẵn metric có tên trên.

## 8. Từ SLO sang cảnh báo có thể hành động

Một alert tốt cần ghi rõ **điều gì sai, ảnh hưởng tới ai, nguồn kiểm chứng và bước tiếp theo**. Mỗi alert nên có đường dẫn tới một runbook đã được review.

Ví dụ alert rules của Prometheus cho hai tình huống. Các metric ở đây là ví dụ do ứng dụng hoặc exporter cung cấp:

~~~yaml
groups:
  - name: shop-checkout
    rules:
      - alert: SHOP_PAYMENT_ERROR_RATE
        expr: |
          (
            sum(rate(shop_checkout_attempt_total{
              step="payment_capture",
              outcome="error"
            }[5m]))
            /
            clamp_min(
              sum(rate(shop_checkout_attempt_total{
                step="payment_capture"
              }[5m])),
              1e-9
            )
          ) > 0.05
          and
          sum(increase(shop_checkout_attempt_total{
            step="payment_capture"
          }[5m])) >= 30
        for: 10m
        labels:
          severity: warning
          team: payments
        annotations:
          summary: Payment attempts đang lỗi vượt ngưỡng
          runbook: https://runbooks.example.org/shop/payment-errors

      - alert: SHOP_SHIPPING_OVERDUE
        expr: |
          max(shop_checkout_oldest_pending_age_seconds{
            state="awaiting_shipping"
          }) > 900
        for: 5m
        labels:
          severity: critical
          team: shipping
        annotations:
          summary: Có đơn hàng chờ shipping quá 15 phút
          runbook: https://runbooks.example.org/shop/shipping-overdue
~~~

Các URL `runbooks.example.org` là **địa chỉ minh họa**, cần thay bằng nơi lưu runbook nội bộ có quyền truy cập phù hợp. Ngưỡng 5%, tối thiểu 30 attempts và thời gian 15 phút là giả định của bài thực hành.

**Điểm cần lưu ý khi đánh giá alert:**

- Dùng `for:` để giảm nhiễu từ spike ngắn; nhưng đừng trì hoãn cảnh báo dữ liệu mất mát thực sự nếu SLO yêu cầu phản ứng nhanh.
- Missing series do lỗi scrape không làm phép so sánh lớn hơn ngưỡng trở thành true. Cần alert riêng cho **mất telemetry** (ví dụ `up == 0` của target liên quan hoặc kiểm tra freshness của metric).
- Phân loại các kết quả nghiệp vụ hợp lệ (như khách từ chối thanh toán) khỏi lỗi kỹ thuật.
- Alert từ **durable pending age** bổ sung cho request error rate: hệ thống có thể vẫn trả 200 OK trong khi đơn hàng đang tắc.
- Alert nên có `service`, `environment`, `team` phù hợp; tránh nhãn động là ID giao dịch hoặc dữ liệu nhạy cảm.

## 9. Thiết kế runbook sử dụng trong ca trực

Runbook là tài liệu hành động dưới áp lực: người trực cần xác định nhanh tình trạng, quyền được phép sử dụng và cách xác minh đã phục hồi. Mỗi runbook nên có cấu trúc cố định:

| Trường | Thông tin cần điền |
|---|---|
| Mã và tên | Ví dụ `RB-SHIPPING-01 — Shipping overdue` |
| Alert liên quan | Biểu thức, SLI/SLO, mức độ severity |
| Impact | Người dùng, chức năng và cửa sổ ảnh hưởng |
| Ownership | Module owner, primary on-call, escalation |
| Dashboard / logs / traces | Liên kết đã phân quyền |
| Read-only diagnostics | Các câu lệnh/queries an toàn có thể chạy |
| Mitigation | Hành động giảm tác động và điều kiện thực hiện |
| Recovery / replay | Các bước phục hồi có kiểm soát idempotency |
| Exit criteria | Bằng chứng kết thúc sự cố |
| Follow-up | Audit, postmortem, kiểm thử phòng ngừa |

Cần tách rõ **quan sát** và **hành động có thể thay đổi dữ liệu**. Đọc metric/log/publication registry thường là thao tác chẩn đoán; resubmit event, reset offset, replay hàng loạt, chỉnh trạng thái đơn hay rollback production phải theo quyền hạn và quy trình phê duyệt vận hành hiện hành.

### 9.1. Runbook RB-SHIPPING-01 — Đơn chờ shipping quá lâu

**Trigger:** `SHOP_SHIPPING_OVERDUE` đang firing; gauge tuổi đơn `awaiting_shipping` cao hơn 900 giây ít nhất 5 phút.

**Tác động:** đơn đã qua bước thanh toán nhưng chưa đạt trạng thái giao hàng tiếp theo đúng cam kết; người dùng có thể thấy trạng thái chờ kéo dài.

**Đọc dữ liệu trước khi can thiệp:**

1. Xem số đơn pending và độ tuổi theo thời gian; xác nhận có dữ liệu fresh, đúng môi trường.
2. Từ read model xác định các order đang ở `awaiting_shipping`, thời điểm chuyển trạng thái, số lần thử và eventId gần nhất. Chỉ dùng truy vấn read-only được cấp quyền.
3. Đối chiếu tỷ lệ `shipment_requested`, publication pending/failed và producer Kafka error rate.
4. Nếu bên phát đã gửi thành công, kiểm tra consumer lag, lỗi deserialize và phản hồi đối tác.
5. Mở traces gần đây; nếu tracing đứt ở async/broker, liên kết log bằng `eventId`/`correlationId`.

**Bảng quyết định:**

| Quan sát | Giả thuyết ưu tiên | Bước tiếp theo |
|---|---|---|
| Publication pending tăng, Kafka gửi lỗi | Broker/network/authentication bị lỗi hoặc externalizer không gửi được | Kiểm tra producer error, broker reachability, credentials và status registry |
| Producer ack bình thường, consumer lag tăng | Consumer đang chậm/dừng hoặc partition không được xử lý | Kiểm tra consumer group, tài nguyên, retry và poison message |
| Consumer đã xử lý nhưng trạng thái đơn không cập nhật | Lỗi nghiệp vụ/persistence/idempotency | Tra log transaction, dữ liệu đối soát và error classification |
| Pending age cao nhưng dữ liệu đã hoàn thành | Gauge/read model bị trễ hoặc bị nhân bản | Kiểm tra freshness, nguồn gauge, query và exporter |
| Không có metric sau deploy | Scrape/Actuator/registry lỗi | Kiểm tra telemetry trước khi kết luận luồng đã dừng |

**Giảm tác động:** nếu lỗi ở đối tác hoặc broker, cân nhắc tạm dừng gửi mới, chuyển sang cơ chế chờ/retry đã được thiết kế hoặc giới hạn lưu lượng theo policy để bảo vệ backlog. Không tự động sửa trạng thái `shipment_accepted` chỉ để xóa cảnh báo.

**Khôi phục:** khi dependency ổn định, kiểm tra publication nào có thể resubmit an toàn; xác minh producer và consumer dùng **eventId ổn định**, có idempotency ở consumer và lịch sử ghi nhận đủ để đối soát. Đối với poison message, phân loại nguyên nhân trước khi cho chạy lại. Nếu cần replay nhiều bản ghi, thực hiện theo quy trình được duyệt và có phương án dừng.

**Kết thúc sự cố:** backlog giảm bền vững, pending age xuống ngưỡng, đơn thực sự đạt trạng thái kỳ vọng trong database, không xuất hiện xử lý trùng, và các metric/traces đã phục hồi.

### 9.2. Runbook RB-PAYMENT-01 — Lỗi thanh toán tăng

**Trigger:** `SHOP_PAYMENT_ERROR_RATE` firing, có đủ số attempts và tỷ lệ lỗi vượt ngưỡng.

**Điều tra:**

1. Kiểm tra phân loại outcome: lỗi HTTP 5xx, timeout, kết nối gateway, lỗi token hay từ chối thanh toán hợp lệ.
2. So sánh failure ratio, p95 attempt duration và số đơn `awaiting_payment`.
3. Tra changes vừa deploy, cấu hình gateway/credential, rate limit và circuit breaker của client.
4. Xem trace gần thời điểm bắt đầu lỗi; phân biệt thời gian chờ network và thời gian xử lý trong module payments.
5. Kiểm tra các khoản tiền đã capture nhưng chưa cập nhật durable state trước khi thực hiện retry.

**Giảm tác động:** có thể kích hoạt chính sách circuit breaker/backoff, giới hạn retry hoặc định tuyến sang giải pháp dự phòng đã được thỏa thuận. Retry thanh toán **phải sử dụng idempotency key được gateway và nghiệp vụ hỗ trợ**; retry mù có thể gây trừ tiền hai lần.

**Kết thúc:** error ratio và latency hồi phục, backlog `awaiting_payment` giảm, đối soát ledger/gateway không có giao dịch trùng và cảnh báo hết firing trong cửa sổ đánh giá.

### 9.3. Runbook RB-OBS-01 — Không có spans hoặc module metrics

**Trigger:** truy vấn trace/metric không có dữ liệu sau một thay đổi deployment hoặc có alert telemetry missing.

**Trình tự kiểm tra:**

1. Xác nhận ứng dụng còn sống bằng health và business requests; `no data` **không đồng nghĩa** service đã down.
2. Kiểm tra phiên bản Spring Boot/Modulith, classpath, dependency `spring-modulith-starter-insight`, Actuator và Micrometer/tracing bridge.
3. Xác minh endpoint metric được expose trên kênh quản trị riêng; meter có thể chỉ xuất hiện sau khi đã tạo event.
4. Kiểm tra sampler, endpoint exporter, collector, routing và network.
5. Nếu chỉ trace async bị tách, kiểm tra executor đang dùng `@ApplicationModuleListener` và cấu hình context propagation; nếu qua Kafka, kiểm tra inject/extract trace headers.
6. So sánh module graph baseline với runtime để biết việc mất metric có liên quan đến module detection hay do instrumentation.

**Khôi phục:** sửa cấu hình exporter/sampling/instrumentation trong phạm vi được cho phép, phát một event thử trong môi trường kiểm soát, kiểm tra metric và span ở backend. Không tăng sampling production lên `1.0` lâu dài mà chưa tính chi phí và dữ liệu nhạy cảm.

**Kết thúc:** telemetry fresh trở lại, module spans/event metrics phù hợp workload, alerts mất dữ liệu không còn firing. Những thành phần nghiệp vụ đã chạy trong lúc thiếu trace có thể phải đối soát bằng durable state và logs, không suy diễn lại được toàn bộ trace đã mất.

## 10. Ví dụ tác nghiệp đọc dữ liệu

Các ví dụ dưới đây là lệnh **đọc trạng thái** trong môi trường thử nghiệm. Địa chỉ, tên deployment và nhóm Kafka chỉ mang tính minh họa.

### 10.1. Actuator

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/modulith
curl -i http://localhost:8080/actuator/prometheus
~~~

Chỉ dùng với endpoint đã được đăng ký và truy cập đúng quyền. Trong production, thường nên dùng mạng quản trị hoặc công cụ nội bộ có xác thực thay vì trực tiếp mở cổng Actuator ra Internet.

### 10.2. Kubernetes

~~~bash
kubectl -n commerce get pods -l app=shop-modulith
kubectl -n commerce get deployment shop-modulith
kubectl -n commerce describe deployment shop-modulith
kubectl -n commerce logs deployment/shop-modulith --since=15m
~~~

Nếu nghi ngờ rollout gây lỗi, xem revision/deployment events rồi so sánh thời điểm cảnh báo. `kubectl rollout undo` là thao tác thay đổi production, cần dùng theo quy trình vận hành; không thực hiện tự động chỉ vì metric có spike.

### 10.3. Kafka consumer lag

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.internal:9092 \
  --describe \
  --group shipping-consumer
~~~

Command cho biết tình trạng consumer group và lag nếu có quyền, nhóm tồn tại và endpoint broker truy cập được. Không đặt lại offset hoặc xóa topic khi chưa xác định được tác động đến event ordering, duplicate và yêu cầu đối soát.

## 11. Trace context qua module, thread và broker

Dashboard sản xuất phải xử lý ba trường hợp:

**Trong cùng thread:** nếu Spring Modulith observability instrument một public module entry, span có thể cho biết module và method được gọi. Trace cho phép đi từ HTTP request tới đoạn xử lý, tùy sampling và instrumentation.

**Qua listener bất đồng bộ:** `@ApplicationModuleListener` có thể chạy trên executor khác. ThreadLocal chứa current observation/span có thể bị mất. Cần cấu hình **context propagation** phù hợp trên executor thực tế (ví dụ `ContextPropagatingTaskDecorator` theo Spring Framework) và xác minh bằng span/log thật.

**Qua Kafka và sau restart:** producer/consumer cần inject/extract headers theo tracing instrumentation. Khi một publication được resubmit sau vài giờ hoặc sau restart, context của HTTP request ban đầu thường không còn active; trace mới có thể xuất hiện. Dùng `eventId`/`correlationId` để liên kết nghiệp vụ, không yêu cầu mọi lần xử lý dùng một traceId.

Cũng không nên đưa toàn bộ baggage của request vào message headers. Các ranh giới tin cậy giữa service, broker và đối tác cần chính sách riêng đối với dữ liệu được phép truyền.

### 11.1. Quy tắc drill-down an toàn

Một truy vấn từ metric sang trace nên chuyển các nhãn có cardinality thấp như `service`, `module`, `step`, `outcome` và khoảng thời gian. Nếu cần mở đơn hàng cụ thể, truy vấn vào hệ thống nghiệp vụ qua công cụ có phân quyền, rồi mới xem các `eventId`/trace liên quan.

Không xây metric dashboard theo kiểu “mỗi orderId là một đường biểu đồ”. Điều đó gây cardinality rất cao và có thể rò rỉ dữ liệu khách hàng.

## 12. Kiểm thử dashboard và runbook trước production

Cần chủ động tạo các tình huống để xác minh cả alert và hành động xử lý. Dữ liệu test phải có thời điểm rõ ràng; dùng môi trường tích hợp có database, broker, telemetry collector và các workflow có thể tái hiện.

| Mã | Kịch bản | Bằng chứng phải có |
|---|---|---|
| P1 | Đơn được chấp nhận và đi hết luồng | Trạng thái bền vững đúng, có business metrics, trace/log liên quan |
| P2 | Payment timeout rồi retry thành công | Attempt error + attempt success tăng, business capture chỉ một lần |
| P3 | Thanh toán bị từ chối hợp lệ | Không gắn sai nhãn `infrastructure_error`, funnel thể hiện trạng thái đúng |
| P4 | Transaction `orders` rollback | Không có business transition đã commit và message after-commit từ giao dịch lỗi |
| P5 | Kafka broker tạm thời không truy cập | Producer lỗi, publication còn pending/failed, alert hữu ích |
| P6 | Broker hồi phục và publication resubmit | Gửi lại cùng eventId; consumer idempotent; backlog giảm |
| P7 | Kafka ack đã thành công nhưng đối tác chưa xác nhận | Dashboard phân biệt `shipment_published` và `shipment_accepted` |
| P8 | Consumer lag tăng và đơn shipping quá hạn | Pending age alert firing; runbook xác định đúng phía consumer |
| P9 | Mất context propagation qua executor | Log/span chỉ ra trace tách; vẫn drill-down bằng eventId |
| P10 | Bật propagation qua executor và broker | Trace/span linkage có bằng chứng từ message thực |
| P11 | Collector hoặc scrape target bị lỗi | Dashboard hiển thị no-data/telemetry alert, không coi là 0 lỗi |
| P12 | Scale ứng dụng từ một lên ba replica | Gauge toàn cục không bị nhân ba do query sai |
| P13 | Thay đổi code gây dependency module sai | `ApplicationModules.verify()` phát hiện, bổ sung kiến trúc vào quy trình deploy |
| P14 | Có 100 đơn thuộc cùng cohort, một số hoàn tất muộn | Conversion và overdue theo đúng cohort/tuổi, không lấy hai cửa sổ độc lập chia nhau |
| P15 | Thực hiện drill-down từ alert tới một đơn tồn đọng | Người có quyền tìm được state, event history, trace/log và bước xử lý trong runbook |
| P16 | Rollback một release quan sát bị lỗi | Metrics/traces và Actuator khôi phục, trạng thái nghiệp vụ vẫn được bảo toàn |

### 12.1. Bảng nghiệm thu chéo

| Lớp kiểm chứng | PASS khi nào | Nếu FAIL cần xem |
|---|---|---|
| **Kiến trúc module** | Graph và `ApplicationModules.verify()` phù hợp thiết kế | Package, API công khai, dependency vòng |
| **Business state** | Cohort và trạng thái bền vững chính xác | Transaction, idempotency, read model |
| **Actuator** | Endpoint được đăng ký, expose đúng mạng/quyền | Starter, auto-config, security |
| **Application events** | Metric event tăng khi publish nội bộ | Event publisher, listener, Modulith instrumentation |
| **Broker/publication** | Pending/retry/delivery phản ánh thực tế | Registry, producer, consumer |
| **Tracing** | Có span/trace phù hợp với sampling và context propagation | Tracer, exporter, executor, broker headers |
| **Alerting** | Alert xuất hiện khi có lỗi và không đánh đồng missing data với success | PromQL, label, `for`, telemetry freshness |
| **Runbook** | On-call xác định được bước điều tra và kết thúc sự cố | Hướng dẫn còn thiếu, quyền truy cập, escalation |

Không đánh dấu `PASS` cho toàn bộ dashboard chỉ vì PromQL trả được số. Cần có **test fixture hoặc workload biết trước kết quả** để so sánh với dữ liệu bền vững.

## 13. Đưa dashboard và runbook vào quy trình vận hành

Một luồng triển khai thực tế:

1. **Baseline:** lưu sơ đồ module, mô tả event, định nghĩa metric, kết quả test và một tập traces mẫu của phiên bản đang chạy.
2. **Code review:** kiểm tra meter/tags, loại lỗi, idempotency, truy cập module hợp lệ; đảm bảo không xuất thông tin nhạy cảm.
3. **Staging verification:** chạy các kịch bản P1–P15, kiểm tra scrape, exporter, tracing collector, broker và runbooks.
4. **Production rollout:** triển khai theo chiến lược đã chọn (rolling/canary); so sánh metric và trace của phiên bản mới với baseline.
5. **Enable alerts:** gắn team, severity, runbook URL và thời gian làm việc; kiểm tra luồng thông báo của hệ thống on-call.
6. **Game day:** mô phỏng một sự cố có kiểm soát, đo thời gian phát hiện, tìm nguyên nhân, khôi phục và đối soát.
7. **Bảo trì:** review SLO, chỉnh ngưỡng khi yêu cầu thay đổi, cập nhật runbook sau postmortem, kiểm tra dashboard khi nâng Spring Boot/Modulith.

### 13.1. Tiêu chí hoàn thành dự án

Bài thực hành được xem là đạt khi có đủ các thành phần có thể kiểm tra độc lập:

- **Dashboard:** có lớp business funnel, pending/overdue, attempt error/latency, event publication, broker và drill-down.
- **Observability:** Actuator/metrics/traces xuất được dữ liệu, module graph giúp xác minh ranh giới thiết kế; sampling và propagation có bằng chứng.
- **Reliability:** retry có eventId ổn định, consumer idempotent và publication/broker state được quan sát tách biệt.
- **Alert & runbook:** tối thiểu hai alert nghiệp vụ/vận hành gắn runbook, có hướng dẫn điều tra, giảm tác động, khôi phục và xác nhận.
- **Validation:** kịch bản failure injection có kết quả, không đếm trùng business transition, không lấy missing-data làm zero.
- **Security:** endpoint quản trị được bảo vệ; logs/traces/metric tags không phát tán thông tin nhạy cảm.
- **Handover:** người trực ca khác có thể đọc alert, mở dashboard, áp dụng bước chẩn đoán an toàn và biết khi nào cần escalation.

## 14. Bài tập mở rộng

Sau khi dựng xong dashboard đầu tiên, hãy bổ sung thêm **một module inventory** tham gia trước bước `shipment_requested`. Yêu cầu là lưu được mối liên hệ giữa `OrderPlaced`, `StockReserved`, `PaymentCaptured` và `ShipmentRequested` theo một correlation ID; cập nhật module graph và dashboard mà không tăng tag cardinality bằng orderId.

Thử tạo ba lỗi có kiểm soát: inventory hết hàng, listener thanh toán retry sau restart và consumer giao vận chậm. Với từng lỗi, giải thích **alert nào nên firing**, **runbook nào cần mở**, **dữ liệu nào cần đối soát** và **bằng chứng nào cho phép đóng incident**. Nếu module graph phát hiện dependency bất hợp lệ nhưng metrics vẫn xanh, giải thích vì sao cần cả kiểm thử kiến trúc lẫn telemetry runtime.

## Tài liệu tham khảo

- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html): mô hình module và kiểm chứng ranh giới.
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): sinh tài liệu, sơ đồ ứng dụng.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Actuator, module observability và event metrics.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional event listeners, publication registry và externalization.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): bảo vệ endpoint và cấu hình exposure.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): metrics, tracing và context propagation.
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): Counter, Timer, Gauge, tags và cardinality.
- [Prometheus — Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): `rate`, `increase`, label matching và range vectors.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): cú pháp alert expression, `for`, labels và annotations.
