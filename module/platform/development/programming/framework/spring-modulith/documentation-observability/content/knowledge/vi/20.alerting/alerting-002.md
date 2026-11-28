# Cảnh báo lỗi khi gọi module API

## Mục tiêu học tập

Trong học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, Spring Modulith giúp mô tả ranh giới application module và quan sát cách các module tương tác trong ứng dụng Spring Boot. Bài này tập trung vào việc thiết kế cảnh báo khi một module gọi API của module khác gặp lỗi, tăng độ trễ hoặc có tỷ lệ thất bại bất thường.

Sau bài học, bạn có thể:

1. Phân biệt lỗi khi gọi API module đồng bộ với lỗi trong event listener bất đồng bộ.
2. Xác định tín hiệu có thể dùng để cảnh báo: exception, outcome, duration, HTTP status, event publication và trace.
3. Hiểu module entry spans của Spring Modulith và giới hạn của việc dùng trace làm nguồn đếm lỗi.
4. Thiết kế metric invocation riêng với tag có cardinality thấp khi cần alert chính xác theo module.
5. Viết PromQL cho error rate, invocation rate và latency percentile.
6. Tạo Prometheus alert rules có ngưỡng volume, thời gian duy trì và mức độ ưu tiên phù hợp.
7. Phân biệt lỗi kỹ thuật với business rejection, retry và lỗi đã được xử lý.
8. Kết hợp Actuator, metrics, logs, traces và module graph trong quy trình điều tra.
9. Tránh alert nhiễu, cardinality cao và việc đưa dữ liệu nhạy cảm vào telemetry.
10. Xây dựng runbook để xác định caller, target module và dependency gây ra lỗi.

**Bối cảnh:** Spring Modulith cung cấp module graph để kiểm tra cấu trúc, Actuator để xem thông tin runtime, event metrics để theo dõi publication và module entry spans để quan sát lời gọi qua API module. Những tín hiệu này hỗ trợ điều tra; để cảnh báo theo tỷ lệ lỗi và độ trễ một cách ổn định, cần metrics có semantics rõ ràng và được thu thập liên tục.

> **Phạm vi:** Ví dụ dùng Micrometer, Spring Boot Actuator và Prometheus. Tên meter và cách export phụ thuộc registry/version. Spring Modulith module spans có thể giúp tìm lỗi trong trace, nhưng không nên mặc định chúng là một counter đầy đủ cho mọi lần gọi module API.

---

## 1. Vì sao cần cảnh báo ở ranh giới module?

Một ứng dụng Spring Modulith thường có nhiều application modules, mỗi module công khai một API để module khác sử dụng. Ví dụ:

~~~text
shop
├── orders
│   └── OrderManagement
├── inventory
│   └── InventoryOperations
├── payments
│   └── PaymentOperations
└── shipping
    └── ShippingOperations
~~~

Khi `orders` gọi `inventory` để giữ hàng, lỗi ở module inventory có thể khiến thao tác tạo đơn thất bại. Khi `orders` gọi `payments`, lỗi có thể xảy ra ngay trong lời gọi đồng bộ hoặc sau đó trong event listener bất đồng bộ.

Nếu chỉ theo dõi HTTP status, ta biết request tạo đơn trả 500 nhưng chưa chắc biết module nào là nguồn lỗi. Nếu chỉ xem trace, ta có thể thấy một số lời gọi module bị lỗi, nhưng trace sampling có thể bỏ qua nhiều lần thực thi. Cảnh báo cần một tín hiệu có thể tổng hợp ổn định:

- số lần gọi module API;
- số lần gọi thất bại;
- tỷ lệ lỗi theo module đích;
- thời gian phản hồi p95/p99;
- số event publication chưa được xử lý hoặc retry nếu workflow bất đồng bộ có tracking;
- tỷ lệ lỗi của endpoint bên ngoài gọi vào ứng dụng.

### 1.1. Phạm vi cảnh báo

Một cảnh báo tốt phải trả lời được:

- **Module nào** là target đang gặp lỗi?
- **Caller nào** đang gọi target đó, nếu có dữ liệu này?
- **Operation nào** bị ảnh hưởng?
- Lỗi tăng theo tỷ lệ hay chỉ có một lần lỗi đơn lẻ?
- Lỗi kéo dài bao lâu và ảnh hưởng tới request/luồng nghiệp vụ nào?
- Có dependency ngoài, database hoặc event listener nào liên quan?
- Người trực vận hành cần làm gì tiếp theo?

Không cần tạo alert riêng cho từng method hoặc từng exception class. Nên nhóm theo module và operation có ý nghĩa vận hành.

## 2. Phân biệt lỗi module API đồng bộ và bất đồng bộ

### 2.1. Lời gọi module API đồng bộ

Ví dụ:

~~~java
@Service
class OrderService {

    private final InventoryOperations inventory;

    OrderService(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    public void place(Order order) {
        inventory.reserve(order.id(), order.lines());
        // Tiếp tục workflow nếu reservation thành công.
    }
}
~~~

Nếu `inventory.reserve(...)` ném exception và exception truyền ngược về `OrderService`, caller có thể:

- chuyển thành lỗi HTTP;
- rollback transaction;
- thử fallback;
- retry theo policy;
- hoặc xử lý và tiếp tục.

Metric ở ranh giới module có thể ghi nhận lời gọi thất bại ngay cả khi controller sau đó chuyển exception thành response có kiểm soát. Vì vậy, **module API failure** và **HTTP 5xx** là hai khái niệm liên quan nhưng không đồng nhất.

### 2.2. Event listener bất đồng bộ

Ví dụ:

~~~java
@Component
class PaymentListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        paymentService.prepare(event.orderId());
    }
}
~~~

Nếu listener chạy bất đồng bộ, exception của nó thường không quay ngược về HTTP request đã phát event. Request tạo đơn có thể trả 2xx trong khi listener payments thất bại sau đó.

Vì vậy cần hai nhóm quan sát riêng:

- **Module API invocation alerts:** lỗi trong lời gọi trực tiếp qua module API.
- **Event processing alerts:** publication chưa hoàn tất, listener thất bại/retry, consumer lag hoặc dead-letter queue tùy kiến trúc messaging.

Không dùng HTTP 5xx làm đại diện cho mọi lỗi xử lý event.

### 2.3. Ma trận tín hiệu

| Tình huống | HTTP metrics | Module invocation metric | Trace/span | Event processing signal |
| --- | --- | --- | --- | --- |
| Lời gọi module đồng bộ ném exception | Có thể thấy 5xx nếu lỗi truyền ra request | Có thể ghi outcome error | Module span có thể ghi lỗi | Không nhất thiết liên quan |
| Caller bắt exception và trả fallback | Có thể vẫn là 2xx | Vẫn có thể ghi error ở ranh giới module | Span có thể ghi lỗi nếu exception được ghi nhận | Không nhất thiết liên quan |
| Listener async thất bại sau khi HTTP trả 2xx | HTTP metric không thể hiện lỗi listener | Không thuộc invocation đồng bộ ban đầu | Listener span có thể thể hiện lỗi nếu được instrument và sample | Cần theo dõi publication/retry/consumer |
| Business rule từ chối hợp lệ | Có thể là 4xx hoặc 2xx tùy API | Nên phân loại rejected riêng | Span có thể kết thúc bình thường hoặc ghi event | Không nhất thiết là lỗi kỹ thuật |
| Dependency ngoài timeout | Có thể tạo 5xx hoặc timeout | Target module có thể ghi error | Client span và module span giúp tìm nguyên nhân | Có thể ảnh hưởng listener |

## 3. Spring Modulith cung cấp sẵn tín hiệu nào?

Spring Modulith observability có thể tạo **module entry spans** cho lời gọi vào Spring components thuộc API của application module. Các span attributes được tài liệu hóa gồm:

| Attribute | Ý nghĩa |
| --- | --- |
| `module.identifier` | Định danh kỹ thuật của application module. |
| `module.name` | Tên module. |
| `module.invocation-type` | Loại điểm vào, ví dụ bean hoặc event listener. |
| `module.method` | Method được thực thi tại điểm instrument. |

Ví dụ trace:

~~~text
HTTP POST /api/orders
└── orders.place
    └── inventory module entry
        module.identifier = inventory
        module.invocation-type = bean
        module.method = InventoryOperations.reserve
        status = ERROR
~~~

Đây là ví dụ minh họa. Tên span, attributes và cách biểu diễn lỗi phụ thuộc phiên bản Spring Modulith, Micrometer Tracing và exporter.

### 3.1. Span hữu ích để điều tra, không phải bộ đếm đầy đủ

Module entry spans giúp:

- xác định module nào được gọi;
- xem caller/parent span;
- đo thời gian một lần gọi;
- xem exception/error được ghi nhận trên span;
- liên kết với HTTP, database hoặc client spans.

Nhưng tracing có thể dùng sampling. Nếu trace bị loại, span không xuất hiện trong backend dù lời gọi đã chạy. Do đó, **không tính tỷ lệ lỗi production bằng cách đếm số trace lỗi chia cho tổng trace** trừ khi sampling và semantics được thiết kế đặc biệt để bảo đảm thống kê đó.

### 3.2. Event publication metrics không phải listener success metrics

Spring Modulith có event publication metrics, ví dụ counter publication theo event type và module. Các metric publication cho biết event được publish/ghi nhận theo instrumentation; chúng không tự chứng minh tất cả listener đã hoàn tất thành công.

Muốn cảnh báo listener failure, dùng event publication registry/tracking, retry metrics, consumer metrics hoặc dead-letter metrics tương ứng với cơ chế ứng dụng đang dùng. Đừng diễn giải counter publication thành counter xử lý thành công.

## 4. Khi nào cần metric riêng cho module API?

Nếu mục tiêu là cảnh báo như:

- tỷ lệ lỗi khi gọi `inventory` vượt 2%;
- p95 của lời gọi `payments` vượt 500 ms;
- lỗi của operation `reserve` tăng liên tục trong 10 phút;

thì cần một metric có semantics rõ cho invocation. Trước tiên hãy kiểm tra các meter đang có trong `MeterRegistry`. Nếu framework/version đã cung cấp metric phù hợp, dùng lại. Nếu không, bổ sung instrumentation riêng tại ranh giới API module.

Ví dụ một Timer có thể vừa đo duration vừa cung cấp count theo outcome:

~~~text
module.api.duration
  tags:
    target.module = inventory
    operation = reserve
    outcome = success | rejected | error
~~~

Prometheus registry có thể export timer thành các series như:

~~~text
module_api_duration_seconds_count
module_api_duration_seconds_sum
module_api_duration_seconds_bucket
~~~

Tên cụ thể phụ thuộc naming convention của registry. Hãy xem `/actuator/prometheus` để xác nhận.

### 4.1. Chọn tag có cardinality thấp

Nên dùng:

- `target.module`: một trong tập application modules hữu hạn;
- `caller.module`: chỉ khi caller được xác định ổn định;
- `operation`: tên operation được whitelist;
- `outcome`: tập nhỏ như success, rejected, error.

Không dùng:

- order ID, customer ID, event ID;
- trace ID hoặc span ID;
- raw URL hoặc query string;
- exception message;
- class name tùy ý nếu số lượng exception không được kiểm soát;
- method signature động hoặc dữ liệu đầu vào.

`module.method` là span attribute hữu ích để điều tra chi tiết; không mặc định biến nó thành metric label. Cardinality của metric phụ thuộc **tổ hợp tất cả tags**, không chỉ từng tag riêng lẻ.

## 5. Ví dụ instrument module API bằng Micrometer Timer

Ví dụ dưới đây tạo một Timer có tag outcome. Timer tự cung cấp count và duration; không cần tạo thêm một counter trùng nghĩa.

~~~java
package com.example.shop.observability;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public class ModuleApiMetrics {

    private final MeterRegistry registry;

    public ModuleApiMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T record(
            String targetModule,
            String operation,
            Supplier<T> invocation) {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return invocation.get();
        } catch (RuntimeException | Error exception) {
            outcome = "error";
            throw exception;
        } finally {
            sample.stop(Timer.builder("module.api.duration")
                .description("Duration of application module API invocations")
                .tag("target.module", targetModule)
                .tag("operation", operation)
                .tag("outcome", outcome)
                .publishPercentileHistogram()
                .register(registry));
        }
    }

    public void record(
            String targetModule,
            String operation,
            Runnable invocation) {

        record(targetModule, operation, () -> {
            invocation.run();
            return null;
        });
    }
}
~~~

### 5.1. Dùng wrapper ở caller

~~~java
@Service
class OrderService {

    private final InventoryOperations inventory;
    private final ModuleApiMetrics metrics;

    OrderService(
            InventoryOperations inventory,
            ModuleApiMetrics metrics) {
        this.inventory = inventory;
        this.metrics = metrics;
    }

    public void place(Order order) {
        metrics.record("inventory", "reserve",
            () -> inventory.reserve(order.id(), order.lines()));
    }
}
~~~

Ví dụ dùng operation đã được chọn trước là `reserve`. Không lấy operation từ request path hoặc nối thêm ID đơn hàng.

### 5.2. Giới hạn của ví dụ

- Wrapper chỉ đo những lời gọi đi qua nó. Nếu có caller khác gọi trực tiếp module API, lời gọi đó không được ghi bởi wrapper này.
- Exception chỉ được tính là error nếu thoát ra khỏi invocation. Nếu module bắt exception và trả fallback, wrapper sẽ thấy invocation thành công.
- Business rejection được biểu diễn bằng kết quả bình thường sẽ được tính là success trong phiên bản đơn giản này. Nếu cần phân biệt, hãy dùng result mapper hoặc outcome được xác định theo domain.
- Nếu tự instrument cùng một lời gọi ở nhiều lớp, metrics sẽ đếm trùng.
- Spring Modulith module span vẫn có thể được tạo song song; tránh tạo thêm span thủ công trùng lặp chỉ để có metric.

### 5.3. Phân loại business rejection

Một kết quả từ chối hợp lệ không nhất thiết là lỗi kỹ thuật. Ví dụ tồn kho không đủ có thể trả về kết quả `REJECTED` mà không ném exception. Hãy quyết định semantics rõ:

| Outcome | Ví dụ | Có nên paging alert? |
| --- | --- | --- |
| `success` | Reservation được tạo. | Không. |
| `rejected` | Không đủ hàng theo quy tắc nghiệp vụ. | Thường không; theo dõi business KPI riêng. |
| `error` | Database timeout, dependency unavailable, lỗi không mong đợi. | Có thể, tùy tỷ lệ và mức ảnh hưởng. |

Không phân loại exception bằng cách đưa tên class hoặc message vào tag. Map các trường hợp cần thiết về một tập outcome hữu hạn.

## 6. Đo duration và error ratio

Với Timer `module.api.duration`, Prometheus registry thường export:

- `module_api_duration_seconds_count`: số invocation;
- `module_api_duration_seconds_sum`: tổng duration;
- `module_api_duration_seconds_bucket`: histogram buckets nếu được bật.

### 6.1. Invocation rate theo module

~~~promql
sum by (target_module) (
  rate(module_api_duration_seconds_count[5m])
)
~~~

Kết quả là số lần gọi/giây theo module đích trong cửa sổ 5 phút.

### 6.2. Error rate theo module

~~~promql
sum by (target_module) (
  rate(module_api_duration_seconds_count{outcome="error"}[5m])
)
~~~

Đây là số invocation lỗi/giây. Nó đo tốc độ lỗi, không phải tỷ lệ lỗi.

### 6.3. Error ratio theo module

~~~promql
sum by (target_module) (
  rate(module_api_duration_seconds_count{outcome="error"}[5m])
)
/
sum by (target_module) (
  rate(module_api_duration_seconds_count[5m])
)
~~~

Kết quả là tỷ lệ invocation có outcome error trên tổng invocation đã đo. Khi không có traffic, mẫu số bằng 0 hoặc không có series; alert cần thêm điều kiện volume để tránh cảnh báo từ dữ liệu rỗng.

### 6.4. p95 duration theo module

~~~promql
histogram_quantile(
  0.95,
  sum by (le, target_module) (
    rate(module_api_duration_seconds_bucket[5m])
  )
)
~~~

Kết quả ước lượng p95 duration theo target module. Timer phải publish histogram và registry phải export bucket series. Percentile tính từ histogram có thể tổng hợp giữa nhiều instance; percentile tính cục bộ từng instance không thể đơn giản lấy trung bình thành p95 toàn cluster.

## 7. Tạo Prometheus alert rule cho module API errors

Một alert tốt cần:

- điều kiện rõ ràng;
- cửa sổ đo đủ dài để giảm nhiễu;
- ngưỡng traffic tối thiểu;
- thời gian duy trì trước khi firing;
- severity và runbook;
- labels ổn định để nhóm alert.

Ví dụ cảnh báo tỷ lệ lỗi vượt 2% trong ít nhất 10 phút, với invocation rate lớn hơn 0,1 lần/giây:

~~~yaml
groups:
  - name: module-api-alerts
    rules:
      - alert: ModuleApiHighErrorRatio
        expr: |
          (
            sum by (target_module) (
              rate(module_api_duration_seconds_count{outcome="error"}[5m])
            )
            /
            sum by (target_module) (
              rate(module_api_duration_seconds_count[5m])
            )
          ) > 0.02
          and on (target_module)
          sum by (target_module) (
            rate(module_api_duration_seconds_count[5m])
          ) > 0.1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Module API error ratio is high"
          description: "Module {{ $labels.target_module }} has an elevated invocation error ratio."
          runbook_url: "https://runbooks.example.invalid/module-api-errors"
~~~

Đây là ví dụ cần thay runbook URL và ngưỡng theo môi trường. Ngưỡng 2%, 0,1 invocation/giây và 10 phút không phải mặc định của Spring Boot hay Spring Modulith.

### 7.1. Cảnh báo p95 duration cao

~~~yaml
- alert: ModuleApiHighLatency
  expr: |
    histogram_quantile(
      0.95,
      sum by (le, target_module) (
        rate(module_api_duration_seconds_bucket[5m])
      )
    ) > 0.5
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Module API p95 latency is high"
    description: "Module {{ $labels.target_module }} p95 latency exceeds 500ms."
~~~

Ngưỡng 500 ms chỉ minh họa. Operation khác nhau có ngân sách latency khác nhau; nếu cần, thêm tag operation có tập giá trị hữu hạn và định nghĩa alert riêng cho nhóm operation quan trọng.

### 7.2. Khi nào dùng severity page?

Không phải mọi invocation error đều cần đánh thức on-call. Có thể phân cấp:

- **info:** tỷ lệ rejected nghiệp vụ thay đổi nhưng vẫn trong baseline;
- **warning:** tỷ lệ error hoặc p95 tăng kéo dài, có ảnh hưởng nhưng chưa nghiêm trọng;
- **critical/page:** module quan trọng gần như không hoạt động, error budget bị tiêu thụ nhanh hoặc workflow chính bị gián đoạn.

Alert phải gắn với tác động người dùng và SLO. Một exception đơn lẻ trong module không mặc định là sự cố cần paging.

## 8. Cảnh báo lỗi theo endpoint và module cần phối hợp

Một request HTTP có thể gọi nhiều module. Vì vậy nên có cả alert ở tầng endpoint lẫn tầng module:

| Alert | Nguồn metric | Trả lời |
| --- | --- | --- |
| HTTP 5xx ratio | `http.server.requests` | Người dùng/API client có đang nhận lỗi không? |
| HTTP p95 | `http.server.requests` histogram | Endpoint nào đang chậm? |
| Module API error ratio | `module.api.duration` outcome | Lời gọi tới module nào đang thất bại? |
| Module API p95 | `module.api.duration` histogram | Ranh giới module nào đang chậm? |
| Event processing failure/lag | Publication tracking, retry hoặc broker metrics | Listener/consumer nào chưa hoàn tất? |

### 8.1. Vì sao hai alert có thể không cùng firing?

Ví dụ caller bắt exception từ inventory và trả fallback 200. Khi đó:

- module API error ratio có thể tăng;
- HTTP 5xx ratio không tăng;
- trace có thể có module span error nếu exception được ghi nhận;
- log có thể có WARN thay vì ERROR.

Ngược lại, endpoint có thể trả 500 do lỗi validation/config ở orders trước khi gọi module khác. HTTP 5xx tăng nhưng module API error metrics không tăng.

Đây không phải mâu thuẫn; hai metric đo hai ranh giới khác nhau.

## 9. Cảnh báo lỗi của event listener riêng biệt

Với event-driven modules, một event publication có thể kích hoạt một hoặc nhiều listeners. Lỗi listener có thể xảy ra sau khi request phát event đã hoàn tất.

Cần theo dõi các tín hiệu tương ứng với cơ chế event đang dùng:

- trạng thái publication còn incomplete hoặc failed trong event publication registry;
- số lần retry;
- consumer lag nếu dùng broker;
- số message vào dead-letter queue;
- tuổi của publication/message chưa được xử lý;
- tỷ lệ listener failure theo module/event type.

Spring Modulith event publication metrics phản ánh publication, không tự đại diện cho listener success. Nếu dùng Event Publication Registry, hãy khai thác trạng thái publication theo API/Actuator support của phiên bản và cấu hình persistence đang chạy. Với broker, dùng metrics của consumer và DLQ.

### 9.1. Ví dụ cảnh báo publication tồn đọng

Pseudo-query minh họa:

~~~text
pending_publications{listener="payments"} > 0
AND oldest_pending_age_seconds > 300
~~~

Tên metric ở đây không phải tên meter mặc định được cam kết của Spring Modulith. Hãy export một metric rõ ràng từ publication tracking hoặc broker instrumentation của dự án, rồi thay pseudo-query bằng tên thật.

Cảnh báo theo **tuổi của công việc chưa hoàn tất** thường hữu ích hơn alert mỗi lần listener retry, vì retry có thể là hành vi tự phục hồi bình thường.

## 10. Kết hợp module spans với alert

Trace giúp giải thích nguyên nhân sau khi alert firing:

~~~mermaid
flowchart TD
    A["Prometheus alert: inventory error ratio tăng"] --> B["Mở dashboard theo target.module"]
    B --> C["Chọn time window và operation"]
    C --> D["Tìm trace mẫu có lỗi"]
    D --> E["Đọc module entry span"]
    E --> F["Kiểm tra child spans"]
    F --> G["Database / HTTP client / lock / downstream"]
    G --> H["Đối chiếu logs và deployment"]
    H --> I["Mitigation và xác minh metric"]
~~~

Một trace mẫu có thể cho thấy:

~~~text
orders.place
└── inventory module entry [ERROR]
    ├── inventory.database-query [OK, 12ms]
    └── inventory.reserve-stock [ERROR, 1.8s]
        └── stock-database [TIMEOUT]
~~~

Đây là minh họa. Trace sampling có thể khiến không có trace cho một số invocation lỗi; alert vẫn nên dựa trên metrics không sample.

### 10.1. Module graph giúp xác định phạm vi ảnh hưởng

Khi module inventory bị lỗi, module graph cho biết những module nào phụ thuộc vào API inventory. Kết hợp graph với telemetry để trả lời:

- Những caller nào có thể bị ảnh hưởng?
- Module nào cần kiểm tra sau khi thay đổi API?
- Có dependency không mong đợi khiến phạm vi lỗi rộng hơn không?
- Module nào đang gọi inventory trực tiếp hoặc qua event?

Module graph là thông tin cấu trúc; nó không thay thế runtime metrics và trace.

## 11. Giảm alert noise và false positives

### 11.1. Dùng minimum volume

Tỷ lệ lỗi 100% trên một invocation trong 5 phút không nhất thiết là outage. Thêm điều kiện volume tối thiểu như trong PromQL mẫu để tránh cảnh báo từ một lỗi đơn lẻ.

Với module ít traffic, có thể dùng cửa sổ dài hơn hoặc alert theo số lỗi tuyệt đối thay vì ratio đơn thuần.

### 11.2. Dùng for duration

Thuộc tính `for` yêu cầu điều kiện duy trì một khoảng thời gian trước khi alert firing. Nó giúp tránh alert do spike ngắn hoặc scrape noise.

Nhưng đặt quá dài có thể trì hoãn phát hiện outage. Chọn theo mức độ nghiêm trọng và thời gian phản ứng mong muốn.

### 11.3. Group và inhibit alerts

Trong Alertmanager:

- group theo service, environment và target module;
- gộp nhiều alert cùng nguyên nhân để tránh gửi quá nhiều notification;
- inhibit cảnh báo chi tiết khi đã có alert tổng thể nghiêm trọng;
- cấu hình repeat interval hợp lý;
- thêm runbook URL và owner.

Ví dụ, khi toàn bộ shop-service không scrape được, có thể suppress các alert module con đang thiếu dữ liệu vì nguyên nhân gốc là monitoring target down.

### 11.4. Phân biệt no data với healthy

Không có series có thể nghĩa là:

- module chưa được gọi;
- meter chưa được tạo;
- target không scrape được;
- traffic bằng 0;
- exporter/registry lỗi;
- tên metric hoặc tag query sai.

Không chuyển mọi trường hợp no data thành trạng thái healthy. Tạo alert riêng cho scrape failure và cân nhắc synthetic check cho API quan trọng.

## 12. Alert theo error budget và SLO

Nếu có SLO cho module API, ví dụ 99,9% invocation kỹ thuật hoàn tất thành công trong 30 ngày, error budget là 0,1% invocation. Tuy nhiên phải xác định:

- invocation nào nằm trong SLI;
- business rejection có tính là failure không;
- timeout và cancellation được phân loại thế nào;
- retry được đếm một lần hay mỗi attempt;
- operation nào là critical path;
- cách xử lý khi không có traffic.

Một error ratio cao trong 5 phút có thể cần cảnh báo nhanh; error budget burn rate cho biết tốc độ tiêu thụ ngân sách dài hạn. Hai loại alert bổ sung nhau.

### 12.1. Định nghĩa success trước khi viết query

Ví dụ:

- success: module API trả kết quả hợp lệ;
- rejected: business rule từ chối bình thường;
- error: exception kỹ thuật hoặc lỗi không mong đợi.

Nếu gộp rejected vào error, dashboard có thể báo module inventory lỗi chỉ vì nhiều đơn hết hàng. Nếu bỏ timeout khỏi error, alert lại bỏ sót lỗi kỹ thuật. Semantics phải thống nhất giữa code, metric và runbook.

## 13. Quy trình điều tra khi alert firing

1. Xác nhận alert thuộc environment và service nào.
2. Kiểm tra scrape target có UP không để loại trừ monitoring failure.
3. Xem request/invocation rate và minimum volume.
4. Phân loại outcome: error, rejected hay timeout.
5. Xác định target module và operation có tỷ lệ lỗi cao.
6. So sánh với deployment/config change gần thời điểm bắt đầu.
7. Tìm trace mẫu có module entry span tương ứng.
8. Đọc child spans để tìm database, HTTP client hoặc dependency chậm.
9. Tìm log theo trace ID/span ID và xem exception message đã được chuẩn hóa.
10. Nếu là async event, kiểm tra publication tracking, retry, consumer lag và DLQ.
11. Đối chiếu module graph để tìm caller bị ảnh hưởng.
12. Áp dụng mitigation, rồi theo dõi error ratio và p95 trở lại baseline.

### 13.1. Ví dụ tình huống

Alert báo `target.module=inventory` có error ratio 8% trong 10 phút.

Điều tra:

- HTTP 5xx của `POST /api/orders` tăng 4%;
- module invocation metric cho inventory error tăng 8%;
- trace mẫu có module entry span inventory lỗi sau 1,5 giây;
- child span database có timeout;
- log correlation cho thấy connection pool đã cạn;
- deployment gần nhất tăng concurrency nhưng không tăng pool capacity.

Mitigation có thể là rollback hoặc điều chỉnh pool/concurrency theo runbook. Sau đó xác nhận invocation error ratio, HTTP 5xx và p95 giảm về baseline. Các số liệu trên chỉ là ví dụ minh họa quy trình.

## 14. Bảo mật và cardinality của alert metrics

Metric labels thường được lưu lâu và tạo nhiều time series. Chỉ dùng các chiều có tập giá trị nhỏ:

~~~text
target.module = inventory | payments | shipping | ...
operation     = reserve | authorize | create-shipment | ...
outcome       = success | rejected | error
environment   = local | staging | production
~~~

Không đưa vào tags:

- order ID/customer ID/event ID;
- trace ID/span ID;
- exception message hoặc stack trace;
- raw URL/query string;
- payload hoặc thông tin cá nhân.

Exception type nếu cần điều tra nên ghi trong logs/traces; nếu muốn metric theo nhóm lỗi, map vào một taxonomy hữu hạn như `timeout`, `dependency_unavailable`, `validation`, `unknown`.

Không đưa token, password, cookie hoặc payment data vào alert labels/annotations. Alert notifications có thể đi qua email, chat hoặc hệ thống incident bên ngoài; chỉ gửi metadata cần thiết để điều tra.

## 15. Cấu hình Actuator và Prometheus cho alerting

Để có metrics liên tục, cần Micrometer registry phù hợp, ví dụ Prometheus:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Expose endpoint scrape:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
  metrics:
    tags:
      application: shop-service
~~~

Prometheus scrape config minh họa:

~~~yaml
scrape_configs:
  - job_name: shop-service
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - shop-service:8080
~~~

Endpoint `/actuator/prometheus` cần được expose và bảo vệ. Không mở metrics endpoint ra internet công cộng. Trong production, giới hạn network access cho Prometheus, dùng authentication/TLS hoặc management network theo chính sách nền tảng.

Actuator `/actuator/metrics` hữu ích để chẩn đoán meter trên một instance; Prometheus và Alertmanager mới là pipeline thu thập, đánh giá rule và gửi cảnh báo liên tục.

## 16. Kiểm thử alert rules

Trước khi triển khai, kiểm tra:

- metric được tạo khi gọi module API;
- outcome error được ghi khi exception thoát khỏi invocation;
- business rejection được phân loại đúng;
- timer count và histogram buckets xuất hiện;
- PromQL trả kết quả đúng khi có/không có traffic;
- minimum volume ngăn alert từ một mẫu quá nhỏ;
- `for` trì hoãn alert đúng như mong muốn;
- Alertmanager group/inhibit/route đúng team;
- runbook URL mở được và có bước xử lý;
- test async listener riêng biệt với module API sync.

Prometheus hỗ trợ kiểm thử rule bằng `promtool test rules` với file rule test. Có thể tạo fixture metrics cho trường hợp:

1. Không có lỗi.
2. Error ratio dưới ngưỡng.
3. Error ratio vượt ngưỡng nhưng volume thấp.
4. Error ratio vượt ngưỡng và volume đủ.
5. p95 vượt latency budget.
6. Target scrape down.
7. Module chưa được gọi trong cửa sổ.

Không chỉ test PromQL trên dữ liệu production sau khi alert đã được bật; hãy xác minh rule trước khi rollout.

## 17. Checklist triển khai alerting cho module API

- [ ] Xác định ranh giới module API và các caller quan trọng.
- [ ] Phân biệt lời gọi đồng bộ với event listener bất đồng bộ.
- [ ] Kiểm tra module entry spans của Spring Modulith đã hoạt động.
- [ ] Không dùng trace sampling làm nguồn đếm invocation lỗi.
- [ ] Xác định có metric invocation phù hợp sẵn chưa trước khi thêm custom meter.
- [ ] Nếu cần, instrument Timer/Counter tại một ranh giới duy nhất để tránh đếm trùng.
- [ ] Outcome phân biệt success, rejected và error theo semantics nghiệp vụ.
- [ ] Tag target module/operation có cardinality thấp và được whitelist.
- [ ] Không đưa business ID, trace ID hoặc exception message vào metric labels.
- [ ] Có query invocation rate, error ratio và p95 duration.
- [ ] Alert có minimum volume, for duration, severity và runbook.
- [ ] Có alert riêng cho scrape failure/no data.
- [ ] Event listener failure có metric/tracking/retry/DLQ signal riêng.
- [ ] Actuator/Prometheus endpoint được bảo vệ.
- [ ] Đã test Prometheus rules với các tình huống bình thường, lỗi và ít traffic.
- [ ] Runbook chỉ rõ cách xem trace, logs, module graph và dependency metrics.

## 18. Bài tập tự luyện

1. **Phân biệt lỗi:** Vì sao exception trong module API đồng bộ có thể làm HTTP request trả 500, trong khi listener async thất bại không làm request ban đầu đổi status?
2. **Tín hiệu:** Spring Modulith module entry span cung cấp những metadata nào? Vì sao không nên dùng trace count làm error rate chính xác?
3. **Thiết kế metric:** Đề xuất tags cho Timer đo invocation duration của inventory API.
4. **Cardinality:** Vì sao không dùng order ID, trace ID hoặc exception message làm metric tags?
5. **Code:** Giải thích vì sao wrapper Timer cần ghi outcome trong cả nhánh success và exception.
6. **Semantics:** Một module trả kết quả REJECTED bình thường khi hết hàng. Có nên tính là technical error không? Hãy đề xuất outcome.
7. **PromQL:** Viết truy vấn error ratio theo target module và giải thích cách xử lý trường hợp không có traffic.
8. **Alert:** Vì sao cần minimum volume và for duration trước khi paging?
9. **Async:** Đề xuất tín hiệu để cảnh báo listener payments thất bại sau khi HTTP request đã trả 2xx.
10. **Tracing:** Alert báo inventory error ratio tăng. Bạn dùng module span và child spans để tìm dependency gây lỗi thế nào?
11. **SLO:** Xây dựng SLI success cho module API có retry và business rejection; xác định cách đếm attempt.
12. **Vận hành:** Một alert firing nhưng Prometheus target DOWN. Vì sao cần xử lý monitoring pipeline trước khi kết luận module lỗi?
13. **Kiểm thử:** Nêu các test case cho Prometheus alert rule có ngưỡng volume.
14. **Kiến trúc:** Module graph có thể giúp xác định phạm vi caller bị ảnh hưởng sau khi inventory API lỗi như thế nào?

## 19. Tổng kết

Cảnh báo lỗi khi gọi module API cần phân biệt **lỗi ở ranh giới lời gọi đồng bộ**, **lỗi nghiệp vụ được từ chối hợp lệ** và **lỗi xử lý event bất đồng bộ**. HTTP metrics cho biết ảnh hưởng tới endpoint; module entry spans của Spring Modulith giúp điều tra lời gọi cụ thể; event publication tracking và consumer metrics theo dõi phần xử lý bất đồng bộ.

Khi cần alert theo error ratio và latency, hãy dùng metrics có semantics rõ, chẳng hạn Timer theo `target.module`, `operation` và `outcome`. Dùng PromQL để tính invocation rate, error ratio và p95; thêm minimum volume, thời gian duy trì, severity và runbook để giảm alert nhiễu.

Trace giúp tìm nguyên nhân nhưng có thể bị sampling; module graph giúp hiểu cấu trúc nhưng không phản ánh trạng thái runtime. Kết hợp metrics, logs, traces, event tracking và module graph sẽ giúp nhóm vận hành xác định module lỗi, caller bị ảnh hưởng và dependency cần xử lý. Alert là tín hiệu điều tra, không phải bằng chứng thay thế transaction state hoặc tính đúng đắn nghiệp vụ.

### Tài liệu tham khảo chính thức

1. [Spring Modulith — Production-ready Features: Observing Application Modules và Event Metrics](https://docs.spring.io/spring-modulith/reference/production-ready.html).
2. [Spring Boot — Metrics: Micrometer registries và Prometheus](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
3. [Spring Boot — Actuator Endpoints: exposure và access control](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
4. [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
5. [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).
6. [Prometheus — Recording rules and alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/).
7. [Prometheus — Alerting overview](https://prometheus.io/docs/alerting/latest/overview/).
8. [Prometheus — promtool rule unit testing](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/).
