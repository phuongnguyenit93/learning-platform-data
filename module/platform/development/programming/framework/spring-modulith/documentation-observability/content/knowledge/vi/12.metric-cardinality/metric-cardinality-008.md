# Chọn aggregation không làm mất thông tin quan trọng

## 1. Tại sao ít time series hơn chưa chắc là quan sát tốt hơn?

Trong ứng dụng Spring Boot được tổ chức bằng **Spring Modulith**, các application module như `ordering`, `payment` và `notification` có thể phát domain event hoặc được quan sát tại điểm vào API. Khi xuất Micrometer metrics sang Prometheus/Grafana, số lượng chuỗi thời gian (*time series*) dễ tăng theo module, loại event, instance triển khai, môi trường và các nhãn nghiệp vụ tự bổ sung.

**Aggregation** là việc gộp nhiều chuỗi hoặc nhiều quan sát để trả lời một câu hỏi. Nó làm dashboard dễ đọc và truy vấn thường nhẹ hơn. Tuy nhiên, aggregation thiếu chủ đích có thể xóa mất đúng chiều dữ liệu giúp phát hiện lỗi: kênh `mobile` đang gặp sự cố, chỉ một module chậm hoặc một loại event tăng bất thường.

Ví dụ, dashboard hiển thị tổng **200 lần thử checkout** với tỷ lệ thành công **77,5%**. Con số này không cho thấy kênh `web` đạt **95%**, còn `mobile` chỉ đạt **60%**. Nếu nhóm trực vận hành chỉ theo dõi tổng, họ có thể bỏ qua sự cố tập trung trên mobile.

Vì vậy, mục tiêu không phải “giữ mọi nhãn” hay “xóa càng nhiều nhãn càng tốt”, mà là **giữ đúng chiều cần thiết cho quyết định vận hành, bỏ những chiều không có giá trị phân tích hoặc gây cardinality quá cao**.

Bài học thuộc chương **Cardinality** của `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Phạm vi của toàn module là dùng Spring Modulith để tài liệu hóa ranh giới application module, quan sát tương tác bằng Actuator, module graph, event metrics, tracing và context propagation. Trong bức tranh đó, việc chọn aggregation quyết định liệu các tín hiệu vận hành còn đủ ngữ nghĩa để kiểm chứng hành vi từng module hay không.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt metric name, label, time series, cardinality và aggregation.
2. Chọn nhãn cần giữ cho từng câu hỏi, đặc biệt là `module.identifier`, event type, `channel`, `result` và `environment`.
3. Sử dụng `sum by (...)` và `sum without (...)` trong PromQL mà không vô tình trộn những nhóm dữ liệu khác nghĩa.
4. Tính rate, tỷ lệ lỗi và độ trễ trung bình từ tử số/mẫu số đúng, không lấy trung bình của các tỷ lệ đã tổng hợp.
5. Tổng hợp histogram đúng cách khi tính p95, tránh trung bình các quantile.
6. Kiểm soát cardinality **ngay tại instrumentation**, thay vì chỉ ẩn nhãn trong dashboard.
7. Đối chiếu metrics với module graph, traces và kết quả xử lý event để không suy luận quá mức.

## 2. Những khái niệm nền tảng

### 2.1. Meter, label set và time series

Micrometer đăng ký các meter như `Counter`, `Timer` và `Gauge` trong `MeterRegistry`. Khi xuất sang một backend kiểu Prometheus, **metric name kết hợp với tập nhãn và các giá trị nhãn** giúp xác định một chuỗi thời gian.

Ví dụ *minh họa*:

~~~text
module_events_published_total{
  module_identifier="ordering",
  module_event_type="OrderPlaced",
  instance="shop-1"
}

module_events_published_total{
  module_identifier="ordering",
  module_event_type="OrderPlaced",
  instance="shop-2"
}
~~~

Hai dòng có cùng tên metric và cùng loại event, nhưng là hai series khác nhau do `instance` khác nhau. Tên Prometheus ở đây là **giả định theo cách exporter chuẩn hóa**; phải kiểm tra văn bản thật tại `/actuator/prometheus` vì quy tắc đặt tên và cách chuyển dấu chấm trong tag có thể thay đổi giữa phiên bản.

Trong Spring Modulith, counter tổng hợp của domain event có tên Micrometer là `module.events.published` và các tag cơ bản:

- `module.identifier`: định danh module phát event.
- `module.name`: tên hiển thị module.
- `module.event.type`: loại sự kiện.

Counter riêng từng loại event có tên `module.events.published.$moduleIdentifier.$simpleEventTypeName`; Spring Modulith cho phép dùng `ModulithEventMetricsCustomizer` để bổ sung tag nghiệp vụ trên counter riêng đó.

**Lưu ý:** counter “published” đếm lần công bố domain event được instrument; nó **không** phải metric mặc định về số listener đã xử lý thành công. Nếu dashboard cần phân biệt thành công/thất bại ở listener, ứng dụng phải có tín hiệu kết quả xử lý riêng.

### 2.2. Cardinality là số tổ hợp nhãn có thể phát sinh

Giả sử một metric được phân theo:

| Nhãn | Số giá trị trong ví dụ |
| --- | ---: |
| `module_identifier` | 4 |
| `module_event_type` | 8 |
| `channel` | 3 |
| `environment` | 2 |
| `instance` | 4 |

Nếu tất cả tổ hợp đều có dữ liệu, một tên metric có thể tạo tới:

\[
4 \times 8 \times 3 \times 2 \times 4 = 768\ \text{time series}
\]

Đây là **cận trên minh họa**, vì không phải module nào cũng phát đủ tám loại event, và không phải mọi event đều có `channel`. Với histogram cổ điển, mỗi tổ hợp nhãn còn tạo nhiều chuỗi cho các bucket, `_sum` và `_count`; chẳng hạn nếu có tám series `_bucket` được xuất (bao gồm bucket `+Inf`), cộng `_sum` và `_count` thì tối đa khoảng **7.680 series** cho 768 tổ hợp.

Sự bùng nổ nghiêm trọng hơn xảy ra khi thêm nhãn hầu như **duy nhất cho từng giao dịch**, như `orderId`, `customerId` hoặc `traceId`. Khi đó số series có thể tăng theo số người dùng hoặc số request, không còn được giới hạn bởi một bảng phân loại hữu hạn.

### 2.3. Aggregation không xóa chi phí đã phát sinh ở nguồn

Giả sử ứng dụng xuất 100.000 series có nhãn `orderId`, sau đó dashboard dùng `sum(...)` để hiển thị đúng một đường tổng. Prometheus vẫn phải **ingest, lưu và xử lý những chuỗi gốc** theo chính sách hệ thống. Truy vấn ít đường hơn **không tự sửa vấn đề cardinality cao ở instrumentation**.

Do đó phải giải quyết theo hai tầng:

1. **Instrument đúng:** chỉ xuất tag hữu hạn vào metrics; dữ liệu định danh cao nên đặt ở logs/traces theo chính sách dữ liệu phù hợp.
2. **Aggregate đúng:** giữ các nhãn cần thiết ở truy vấn và recording rules để không che mất sự cố.

## 3. Aggregation phải bắt đầu từ câu hỏi, không bắt đầu từ hàm `sum()`

Trước khi viết PromQL, hãy mô tả câu hỏi bằng ngôn ngữ nghiệp vụ. Ví dụ:

| Câu hỏi vận hành | Nhãn cần giữ | Có thể gộp bỏ khi phù hợp |
| --- | --- | --- |
| Tổng số domain event toàn ứng dụng trong 5 phút? | Có thể không cần nhãn; **phải ghi rõ đây chỉ là tổng publication**. | `module_identifier`, event type, `instance`. |
| Module nào đang phát nhiều event nhất? | `module_identifier`. | `instance`, pod; có thể gộp event type nếu chủ đích là tổng mọi loại. |
| `OrderPlaced` tăng bất thường so với `OrderCancelled`? | `module_identifier` và `module_event_type`. | `instance`; không gộp event type. |
| Event `OrderPlaced` từ mobile có suy giảm không? | `channel` trên **counter riêng của OrderPlaced**, có thể giữ `region`. | `instance`, pod; không gộp `channel`. |
| Tỷ lệ checkout thất bại của mỗi kênh? | `channel` và `result` ở dữ liệu gốc; kết quả cuối giữ `channel`. | `instance` nhưng phải tính tử/mẫu đúng. |
| Latency p95 của module payment theo vùng? | `module_identifier`, `region` và bucket `le` trước `histogram_quantile`. | `instance`, pod; không bỏ `le` quá sớm. |
| Production đang lỗi hay chỉ staging? | `environment` (hoặc lọc chính xác `environment="prod"`). | `instance` trong một môi trường. |

**Một quy tắc hữu ích:** mỗi nhãn bị bỏ phải có câu trả lời cho câu hỏi “nếu hai nhóm này khác nhau, mình có cần biết để hành động không?”. Nếu có, đừng gộp bỏ nhãn đó trên biểu đồ phục vụ quyết định ấy.

## 4. Ví dụ: tổng thành công che mất lỗi mobile

Giả sử nhóm `checkout` ghi một **metric nghiệp vụ riêng** `checkout.attempts`, với `channel` và `result`. Đây **không phải** metric mặc định `module.events.published` của Spring Modulith. Trong một cửa sổ năm phút, số attempt được ghi nhận:

| Kênh | Thành công | Thất bại | Tổng attempt | Tỷ lệ thành công |
| --- | ---: | ---: | ---: | ---: |
| WEB | 95 | 5 | 100 | 95% |
| MOBILE | 60 | 40 | 100 | 60% |
| **Tổng** | **155** | **45** | **200** | **77,5%** |

Nếu chỉ dùng:

~~~promql
sum(increase(checkout_attempts_total[5m]))
~~~

ta nhận được tổng lượt thử checkout, nhưng **mất chiều kết quả và kênh**. Một tổng không đủ để biết tỷ lệ thành công và khu vực cần xử lý.

Với cùng dữ liệu, giữ `channel` và `result`:

~~~promql
sum by (channel, result) (
  increase(checkout_attempts_total[5m])
)
~~~

Kết quả là bốn nhóm thay vì một. Từ đó có thể tính tỷ lệ thất bại theo từng kênh:

~~~promql
sum by (channel) (
  rate(checkout_attempts_total{result="failed"}[5m])
)
/
sum by (channel) (
  rate(checkout_attempts_total[5m])
)
~~~

Khi dữ liệu có đầy đủ hai trạng thái như bảng, kết quả sẽ gần **5%** cho WEB và **40%** cho MOBILE. Nếu dashboard chỉ hiển thị lỗi tổng **22,5%**, người trực không thấy mobile là nhóm chịu ảnh hưởng chính.

Để áp dụng chính xác, hai vế phải mô tả **cùng tập attempt, cùng cửa sổ thời gian và cùng bộ lọc môi trường**. Nếu event có thể đến trễ hoặc một giao dịch có nhiều lần thử, không được dùng `OrderCancelled/OrderPlaced` như một “tỷ lệ thất bại” thay thế khi chưa xác định rõ population và semantics.

### 4.1. Tính ratio từ tử số và mẫu số, không lấy trung bình các ratio

Từ bảng trên, trung bình không trọng số của 95% và 60% bằng 77,5%, nhưng chỉ **tình cờ** bằng tỷ lệ tổng vì hai kênh có cùng 100 attempt. Nếu WEB có 900 attempt và MOBILE có 100 attempt, trung bình hai tỷ lệ vẫn là 77,5% nhưng tỷ lệ thành công thực là:

\[
\frac{900\times 0{,}95 + 100\times 0{,}60}{900+100}
=\frac{915}{1000}=91{,}5\%.
\]

Vì vậy, công thức đúng để gộp tỷ lệ là:

\[
\text{Tỷ lệ tổng}=\frac{\sum \text{số lần đạt điều kiện}}{\sum \text{tổng số lần đủ điều kiện}},
\]

không phải `avg(percentage_of_each_instance)` hoặc trung bình đơn giản của tỷ lệ nhóm.

## 5. `by` và `without` trong PromQL

Prometheus hỗ trợ aggregation với cú pháp:

~~~promql
sum by (label_a, label_b) (expression)
sum without (label_c, label_d) (expression)
~~~

- **`by (...)`:** chỉ giữ các nhãn được liệt kê; các nhãn khác bị loại bỏ trong kết quả.
- **`without (...)`:** loại bỏ những nhãn được liệt kê, giữ lại các nhãn khác.

Hai lựa chọn này phục vụ hai ý đồ khác nhau, không phải cú pháp tương đương trong mọi tình huống.

### 5.1. Khi dùng `by`

Ví dụ **giả định** counter tổng hợp Spring Modulith được Prometheus xuất với tên `module_events_published_total` và các label đã đổi từ dấu chấm sang dấu gạch dưới:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Ý nghĩa: tổng tốc độ phát event của mọi instance, **giữ lại** module và loại event. Điều này giúp thấy riêng `ordering/OrderPlaced`, `ordering/OrderCancelled` hoặc event của các module khác.

Trong cùng trường hợp, query:

~~~promql
sum(rate(module_events_published_total[5m]))
~~~

gộp **mọi module và mọi loại event thành một tổng**. Nó có ích cho câu hỏi “tổng lượng publication là bao nhiêu?”, nhưng không đủ cho câu hỏi “event nào tạo ra sự tăng đột biến?”.

### 5.2. Khi dùng `without`

Đôi khi mục tiêu chỉ là gộp các instance/replica, **không loại bỏ các chiều khác** vốn có trong dữ liệu:

~~~promql
sum without (instance, pod) (
  rate(module_events_published_total[5m])
)
~~~

Query này giữ mọi nhãn khác ngoài `instance` và `pod`, bao gồm nhãn như module, event type, environment hoặc region nếu chúng thực sự có mặt trên series.

Đổi lại, nếu instrumentation bổ sung nhãn mới một cách bất ngờ thì `without` có thể **giữ cả nhãn mới**, khiến dashboard hoặc recording rule sinh nhiều series hơn dự kiến. Khi muốn tạo một hợp đồng dữ liệu chặt chẽ cho dashboard, `by` với danh sách nhãn rõ ràng thường dễ kiểm soát hơn.

Với recording rules lâu dài, tài liệu best practices của Prometheus cũng đề xuất cân nhắc `without` để giữ các nhãn hữu ích khác khi chỉ bỏ đúng chiều cần gộp. Quyết định cuối cùng nên dựa trên mục tiêu của rule và tập nhãn được quản trị.

### 5.3. Chọn rõ phạm vi trước khi gộp

Nếu metrics có `environment` hoặc `region`, tổng hợp trên tất cả môi trường đôi khi không có ý nghĩa:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total{environment="prod"}[5m])
)
~~~

Hoặc giữ vùng khi muốn phát hiện lỗi chỉ xảy ra ở một region:

~~~promql
sum by (region, module_identifier, module_event_type) (
  rate(module_events_published_total{environment="prod"}[5m])
)
~~~

**`environment` và `region` là nhãn minh họa do hệ thống triển khai cung cấp**, không phải lời khẳng định Spring Modulith tự gắn các tag đó. Nếu nhãn không tồn tại, câu truy vấn có bộ lọc tương ứng có thể không trả dữ liệu.

## 6. Aggregation riêng cho counter domain event của Spring Modulith

### 6.1. Giữ loại event khi mục tiêu là chẩn đoán

Spring Modulith cung cấp counter Micrometer:

~~~text
module.events.published
module.events.published.$moduleIdentifier.$simpleEventTypeName
~~~

Ở counter tổng hợp, `module.event.type` là một **chiều quan trọng** khi muốn phân biệt event phát ra. Nếu gộp hai loại `OrderPlaced` và `OrderCancelled` thành tổng “ordering events”, bạn có thể bỏ sót tình trạng số lượng hủy đơn tăng mạnh dù tổng event vẫn gần như không đổi.

Ví dụ số lần publication trong năm phút:

| Loại event của ordering | Trước thay đổi | Sau thay đổi |
| --- | ---: | ---: |
| `OrderPlaced` | 100 | 80 |
| `OrderCancelled` | 10 | 30 |
| **Tổng** | **110** | **110** |

Nếu chỉ giữ `module_identifier=ordering` và gộp event type, biểu đồ cho thấy **110 → 110**, không có biến động. Nhưng tỷ trọng event hủy đã tăng đáng kể, là một tín hiệu cần điều tra. Bảng này chỉ phản ánh **số lần công bố event**, chưa đủ kết luận phần trăm đơn bị hủy vì thời điểm phát và population có thể khác nhau.

Nên có **ít nhất hai góc nhìn** khi cần: tổng theo module cho capacity, và chi tiết theo module/event type để phát hiện thay đổi trong cấu trúc lưu lượng.

### 6.2. Giữ kênh trên counter riêng, không suy diễn tag ở counter tổng hợp

Spring Modulith cho phép làm giàu **counter của một loại domain event cụ thể** bằng `ModulithEventMetricsCustomizer`. Ví dụ, event `OrderPlaced` có enum `channel` nhận `WEB`, `MOBILE` hoặc `POS`:

~~~java
package com.example.shop;

import java.util.Locale;
import com.example.shop.ordering.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
public class EventMetricConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
            OrderPlaced.class,
            (event, builder) -> builder.tags(
                "channel",
                event.channel().name().toLowerCase(Locale.ROOT)
            )
        );
    }
}
~~~

Đoạn mã giả định `OrderPlaced` có phương thức `channel()` trả về một enum có tập giá trị cố định. Ứng dụng cần khai báo `spring-modulith-observability-api` ở compile scope và có observability runtime, chẳng hạn `spring-modulith-starter-insight`, với phiên bản tương thích.

Điểm cần nhớ: customizer này làm giàu **per-event counter**. **Không được giả định** tag `channel` cũng xuất hiện trên `module.events.published`, trừ khi hạ tầng metrics của chính dự án bổ sung nó qua một cơ chế khác.

Nếu exporter tạo ra tên `module_events_published_ordering_OrderPlaced_total` cho counter riêng (đây chỉ là **tên ví dụ**), truy vấn có thể là:

~~~promql
sum by (channel) (
  rate(module_events_published_ordering_OrderPlaced_total[5m])
)
~~~

Trước khi dùng dashboard, hãy xem tên Prometheus thật và giá trị nhãn thật tại `/actuator/prometheus`. Nếu exporter đổi chữ hoa, dấu chấm hoặc suffix, sửa truy vấn theo dữ liệu đã xuất; **không copy tên ví dụ mà bỏ qua kiểm tra**.

### 6.3. Không gộp dữ liệu khác semantics

Counter `module.events.published` và metric nghiệp vụ `checkout.attempts` không cùng đơn vị ý nghĩa: một bên đếm publication, một bên đếm attempt. Không cộng chúng vào “tổng hoạt động”, không dùng publication làm mẫu số cho listener success rate khi không có hợp đồng nghiệp vụ rõ ràng.

Tương tự, event có thể được phát nhiều lần, listener có thể retry hoặc xử lý sau commit theo thời gian khác. Nếu muốn đo **tỷ lệ listener xử lý thất bại**, hãy định nghĩa outcome metric riêng trong listener hoặc dùng dữ liệu phù hợp từ Event Publication Registry, thay vì giả định `published - processed = lost`.

## 7. Tính rate cho counter trước khi tổng hợp theo instance

Counter Micrometer thường tăng dần nhưng có thể bắt đầu lại khi instance restart. Một cách đơn giản như:

~~~promql
sum(checkout_attempts_total)
~~~

cho thấy tổng tích lũy tại thời điểm truy vấn, nhưng không trả lời chính xác “bao nhiêu attempt mỗi giây trong năm phút gần nhất?”, và cũng có thể làm người đọc hiểu sai khi pod thay đổi.

Để xem tốc độ, chọn:

~~~promql
sum by (channel) (
  rate(checkout_attempts_total[5m])
)
~~~

`rate()` xem tốc độ tăng của **từng counter series** trong cửa sổ và xử lý counter reset theo semantics của Prometheus. Sau đó `sum by(channel)` gộp các instance của cùng kênh. **Thường nên tính `rate` trước rồi mới `sum`**, không gộp raw counters của nhiều pod trước khi xử lý reset.

Nếu cần số lượt gần đúng trong một cửa sổ thay vì tốc độ/giây, `increase(...[5m])` có thể phù hợp. Giá trị từ `rate` hoặc `increase` dựa trên mẫu scrape và nội suy, nên không nhất thiết là số nguyên ngay cả khi counter chỉ tăng từng đơn vị.

### 7.1. Cửa sổ thời gian làm thay đổi ý nghĩa tín hiệu

- `rate(...[1m])` nhạy với thay đổi ngắn, nhưng dễ nhiễu khi traffic thấp hoặc chu kỳ scrape thưa.
- `rate(...[5m])` cân bằng giữa ổn định và khả năng phát hiện.
- `rate(...[30m])` mượt hơn, nhưng có thể che sự cố vừa bắt đầu hoặc mới kết thúc.

Không có cửa sổ tối ưu cho mọi bài toán. Với alert cần phản ứng nhanh, chọn khoảng đủ mẫu để tránh nhiễu. Với báo cáo dài hạn, có thể dùng khoảng lớn hơn hoặc recording rules đã được kiểm chứng.

## 8. Aggregation cho latency: giữ đúng trọng số và histogram

Ngoài counter event, Spring Modulith có **module-entry observations/spans** khi gọi API module được instrument. Nếu metrics handler và timer/histogram được cấu hình, chúng có thể cung cấp dữ liệu độ trễ. Phần dưới dùng **tên metric giả định** `module_entry_duration_seconds` để minh họa PromQL; **không khẳng định đây là tên metric mặc định của Spring Modulith**.

### 8.1. Độ trễ trung bình phải tính theo sum/count

Với timer cung cấp:

~~~text
module_entry_duration_seconds_sum
module_entry_duration_seconds_count
~~~

độ trễ trung bình theo module trong cửa sổ năm phút được tính:

~~~promql
sum by (module_identifier) (
  rate(module_entry_duration_seconds_sum[5m])
)
/
sum by (module_identifier) (
  rate(module_entry_duration_seconds_count[5m])
)
~~~

**Đúng ngữ nghĩa:** lấy tổng thời gian của tất cả lần gọi rồi chia tổng số lần gọi. Không lấy trung bình đơn giản của `avg_duration_per_instance`.

Ví dụ, instance A xử lý 1.000 request, trung bình 0,1 giây; instance B xử lý 10 request, trung bình 1,0 giây. Trung bình không trọng số giữa hai instance là 0,55 giây, nhưng độ trễ trung bình thực của tất cả request là:

\[
\frac{1000 \times 0{,}1 + 10 \times 1{,}0}{1000+10}
=\frac{110}{1010}\approx 0{,}109\ \text{giây}.
\]

Nếu đưa 0,55 giây lên dashboard, hệ thống có thể trông chậm hơn thực tế hơn năm lần do sai aggregation.

### 8.2. p95 phải giữ bucket `le` khi dùng classic histogram

Với classic histogram thực sự đã được bật và exporter có các series `_bucket`, muốn tính p95 theo module:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, module_identifier) (
    rate(module_entry_duration_seconds_bucket[5m])
  )
)
~~~

Nhãn `le` đại diện cho biên trên của bucket. **Không bỏ `le` trước khi gọi `histogram_quantile`**, vì hàm cần phân bố bucket để tính quantile.

Nếu muốn giữ region để phát hiện một vùng chậm riêng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, module_identifier, region) (
    rate(module_entry_duration_seconds_bucket[5m])
  )
)
~~~

Khi sử dụng **native histogram**, công thức khác và không nhất thiết cần nhãn `le`; hãy dùng cú pháp Prometheus phù hợp định dạng dữ liệu thực. Không lấy `avg` của các p95 từ các instance hay các module để tạo “p95 toàn hệ thống”: **trung bình các quantile không cho quantile của tập hợp**.

### 8.3. Vì sao tổng trung bình có thể che outlier?

Ngay cả trung bình có trọng số đúng vẫn có thể không cho thấy “đuôi” độ trễ. Module payment có thể xử lý phần lớn request ở 50 ms nhưng 5% request mất 3 giây do một gateway; p95 hoặc p99 hữu ích khi điều tra trải nghiệm chậm.

Đồng thời, **không phải mọi observation mặc định đều xuất classic histogram bucket**. Muốn truy vấn `_bucket`, phải bảo đảm timer/phân phối độ trễ đã được cấu hình để xuất histogram ở Micrometer hoặc registry tương ứng. Nếu không có bucket, không thể dùng truy vấn ví dụ để suy ra p95.

## 9. Các quy tắc chọn nhãn để vừa đủ chi tiết vừa an toàn

### 9.1. Phân loại nhãn theo nhu cầu

| Nhãn | Khuyến nghị | Lý do |
| --- | --- | --- |
| `module_identifier` | Giữ cho dashboard/troubleshooting theo module. | Liên hệ với ranh giới kiến trúc được Spring Modulith nhận diện. |
| `module_event_type` | Giữ khi cần phân biệt loại publication. | Không trộn event đặt hàng, hủy đơn hoặc lỗi nghiệp vụ. |
| `channel` là enum hữu hạn | Giữ nếu câu hỏi liên quan WEB/MOBILE/POS. | Dễ phát hiện sự cố theo nhóm, số giá trị nhỏ. |
| `result` là enum hữu hạn | Giữ trong metric có kết quả xử lý rõ ràng. | Cho phép tính đúng success/error ratio. |
| `environment` | Lọc hoặc giữ rõ ràng. | Tránh trộn production với staging. |
| `region` | Giữ khi có sự cố hoặc SLO theo vùng. | Tránh che lỗi cục bộ. |
| `instance`, `pod` | Có thể gộp trong biểu đồ hệ thống; giữ ở biểu đồ debug pod. | Không phải chiều nào cũng cần trên dashboard tổng. |
| `orderId`, `customerId`, `traceId` | **Không dùng làm metric tags.** | Cardinality cao, có rủi ro riêng tư. |
| `rawUrl` có tham số động | **Không dùng trực tiếp.** | Tạo hàng loạt chuỗi cho từng ID; dùng route template. |

Những tag được giữ trong biểu đồ tổng **không nhất thiết là tag phải tạo mới ở instrumentation**. Nếu một dimension đã được backend gắn qua resource labels như `region`, đừng tự nhân bản vô ích; cần quản trị tên và nguồn của mỗi label một cách thống nhất.

### 9.2. Giới hạn miền giá trị ngay từ ứng dụng

Đối với `channel`, nên sử dụng enum hoặc chuẩn hóa thành tập giá trị được quản lý:

~~~java
enum SalesChannel {
    WEB, MOBILE, POS, OTHER
}
~~~

Không chuyển nguyên chuỗi tự do do người dùng gửi vào một metric tag. Ví dụ nếu client gửi `channel="my-custom-channel-12345"`, việc tạo series mới cho mỗi giá trị có thể không dừng lại.

Nếu cần phân loại giá trị không xác định, gom vào `OTHER` và ghi chi tiết ở log có kiểm soát. Việc gom vào `OTHER` cũng là một **quyết định mất thông tin có chủ đích**: cần bảo đảm nhóm OTHER không che một xu hướng quan trọng, chẳng hạn theo dõi tỷ trọng OTHER và cập nhật enum khi một nhóm mới trở nên đáng kể.

### 9.3. Công cụ bảo vệ không thay thế thiết kế metrics

Micrometer cung cấp `HighCardinalityTagsDetector` và `MeterFilter` để phát hiện hoặc đặt giới hạn số meter/tags theo phiên bản. Chúng hữu ích như hàng rào bảo vệ, nhưng việc **chặn meter mới** có thể làm thiếu dữ liệu. Đừng dựa vào `MeterFilter` để “giải quyết” dữ liệu đã có nhãn ID duy nhất; hãy sửa điểm instrumentation và đánh giá tác động nếu chặn.

Nếu một metric đang có hàng trăm nghìn series, chỉ thêm `sum without(orderId)` vào query không bảo vệ được bộ nhớ của ứng dụng hay backend metrics. Cần sửa nguồn hoặc quy tắc ingestion được quản trị.

## 10. Giữ thông tin cần thiết ở từng tầng dashboard

Một dashboard hữu ích thường có **nhiều cấp độ aggregation** thay vì một đồ thị duy nhất:

~~~mermaid
flowchart TB
    S["Meters theo module / event type / channel / result / instance"]
    A["Tổng hoạt động: rate theo application"]
    B["Chi tiết module: rate theo module và event type"]
    C["Chi tiết nghiệp vụ: rate theo channel/result"]
    D["Điều tra sâu: region, instance, traces và logs"]
    S --> A
    S --> B
    S --> C
    B --> D
    C --> D
~~~

| Tầng | Mục đích | Gợi ý aggregation |
| --- | --- | --- |
| **Tổng quan** | Tải toàn ứng dụng, có tăng đột biến không? | Gộp instance, có thể gộp module/event nếu chỉ quan tâm tổng. |
| **Theo module** | Module nào chịu tải hoặc chậm? | Giữ `module_identifier`. |
| **Theo sự kiện** | Loại event nào biến động? | Giữ `module_identifier` và `module_event_type`. |
| **Theo kết quả nghiệp vụ** | Kênh nào, loại kết quả nào bị ảnh hưởng? | Giữ `channel` và `result` trên metric được thiết kế riêng. |
| **Điều tra sự cố** | Lỗi có tập trung vào region/pod cụ thể không? | Giữ `region`, có thể quay lại `instance`/`pod`; liên kết trace/log. |

**Đừng ghi đè metric gốc bằng một recording rule tổng hợp quá sớm** nếu còn cần phân tích theo module hay event type. Có thể lưu các recording rules theo nhiều mức phù hợp và giữ dữ liệu nguồn theo chính sách retention/chi phí đã định. Một recording rule chỉ giữ tổng không thể “khôi phục” các chiều đã loại bỏ từ chính kết quả rule đó.

### 10.1. Phân biệt mất thông tin do query với mất thông tin do instrumentation

- Nếu nguồn **còn tag `channel`** nhưng query đã `sum` bỏ nó, có thể sửa query hoặc tạo biểu đồ khác.
- Nếu instrumentation **chưa bao giờ ghi `channel`**, không thể truy vấn lại giá trị đó từ metric cũ; phải bổ sung nguồn dữ liệu phù hợp và chờ dữ liệu mới.
- Nếu backend **đã drop label hoặc chỉ lưu recording rule**, thông tin ấy có thể không tồn tại trong tập dữ liệu giữ lại.
- Nếu chỉ có **counter publication**, không thể truy ra số event xử lý thành công nếu chưa instrument outcome hoặc có một nguồn đáng tin cậy khác.

## 11. Kiểm chứng trong Spring Boot + Spring Modulith

### 11.1. Cấu hình tối thiểu để quan sát

Ví dụ Gradle Kotlin DSL cho dự án đã quản lý BOM tương thích:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
    implementation("org.springframework.modulith:spring-modulith-observability-api")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Artifact `observability-api` chỉ cần ở compile scope khi mã nguồn thực sự sử dụng những API như `ModulithEventMetricsCustomizer`. Insight Starter cung cấp Actuator và instrumentation runtime; Prometheus registry cần thêm khi muốn xuất định dạng Prometheus.

Ví dụ `application.yml` trong môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus,modulith"
~~~

Trên production, chỉ expose endpoints quản trị cho đối tượng có thẩm quyền, qua cơ chế access, Spring Security và network policy. `/actuator/modulith` công bố kiến trúc, không nên để lộ công khai.

### 11.2. Thu thập danh sách meter và nhãn thực tế

Sau khi khởi động và phát vài domain event:

~~~bash
# Liệt kê meter theo tên Micrometer.
curl -s http://localhost:8080/actuator/metrics

# Xem metric publication tổng hợp và availableTags.
curl -s http://localhost:8080/actuator/metrics/module.events.published

# Xem riêng một module và event type.
curl -s "http://localhost:8080/actuator/metrics/module.events.published?tag=module.identifier:ordering"

# Kiểm tra tên thực và nhãn sau khi export.
curl -s http://localhost:8080/actuator/prometheus
~~~

Đầu tiên cần xác nhận **tên meter thực tế và tập `availableTags`**, sau đó mới viết truy vấn PromQL. Tên của metric trong Actuator `/metrics` có thể khác tên trong `/prometheus`. Đồng thời, không suy ra event counter xuất hiện nếu chưa phát domain event và meter chưa được đăng ký.

### 11.3. Checklist kiểm chứng aggregation

1. Xác định câu hỏi nghiệp vụ và hành động mong muốn khi số liệu vượt ngưỡng.
2. Xác định **đơn vị đo**: lần phát event, lượt thử checkout, lần thành công, giây xử lý hay bucket độ trễ.
3. Kiểm tra các nhãn thực có trên từng metric; không đoán `channel` tồn tại trên counter tổng hợp Spring Modulith.
4. Quyết định nhãn **bắt buộc giữ**: module, event type, result, channel, region hoặc environment theo câu hỏi.
5. Chọn có cần gộp instance/pod không. Nếu cần debug pod, duy trì truy vấn drill-down riêng.
6. Với counter, dùng `rate`/`increase` trước aggregation theo replica; cân nhắc reset và cửa sổ.
7. Với ratio, tính **tổng tử số / tổng mẫu số**; xử lý trường hợp mẫu số bằng 0 hoặc không có dữ liệu.
8. Với độ trễ, tính average bằng tổng `_sum`/`_count`; tính p95 bằng histogram đúng định dạng, không trung bình p95.
9. So sánh tổng và các nhóm con để phát hiện trường hợp một nhóm xấu bị tổng che lấp.
10. Kiểm tra cardinality theo tên meter và thẩm định tag mới trước khi triển khai.

## 12. Sự cố thường gặp khi aggregation

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Tổng event giữ nguyên dù có bất thường | Gộp `module_event_type` hoặc `module_identifier` quá sớm. | Giữ event type và module cho biểu đồ chẩn đoán. |
| Mobile lỗi nặng nhưng dashboard ít thay đổi | Chỉ xem tỷ lệ tổng, không giữ `channel`. | Tính ratio theo `channel` bằng numerator/denominator cùng population. |
| Dashboard thấy tốc độ giảm mạnh lúc pod restart | Đọc raw counter hoặc gộp trước khi xử lý reset. | Dùng `rate(counter[window])` cho từng series rồi `sum`. |
| Không thấy dữ liệu sau khi lọc `environment="prod"` | Nguồn không có nhãn environment, hoặc tên/giá trị khác. | Kiểm tra nhãn thật, cách exporter gắn resource labels. |
| Query per-event không có `channel` | Tag chỉ được bổ sung trên counter riêng, query nhầm counter tổng hợp. | Xem per-event meter và cấu hình customizer. |
| `avg` latency tổng sai lệch rõ | Trung bình các trung bình instance có lưu lượng khác nhau. | Lấy `sum(rate(_sum)) / sum(rate(_count))`. |
| p95 có kết quả lạ | Lấy trung bình p95, thiếu bucket `le` hoặc histogram chưa bật. | Kiểm tra dạng histogram và dùng `histogram_quantile` phù hợp. |
| Một dashboard tổng có ít series nhưng backend vẫn tốn bộ nhớ | Metric nguồn có nhãn ID riêng từng giao dịch. | Sửa instrumentation và chính sách ingestion; aggregation query không xóa series gốc. |
| Tỷ lệ lỗi thành `NaN` hoặc thiếu dữ liệu | Mẫu số bằng 0, series absent, bộ lọc hai vế không khớp. | Kiểm tra cả hai vế và tình huống zero traffic; không tự coi absent là “0 lỗi”. |
| Số liệu không khớp log/traces | Khác nguồn, khác cửa sổ thời gian, sampling, retry hoặc transaction phase. | Đối chiếu semantics metric, instrumentation và correlation key nghiệp vụ. |

## 13. Bài tập thực hành

### Bài 1 — Chọn mức aggregation phù hợp

Từ dữ liệu ví dụ ở mục 4, hãy tạo hai biểu đồ: (a) tổng checkout attempts toàn ứng dụng; (b) tỷ lệ thất bại của từng kênh. Giải thích vì sao hai biểu đồ đều hữu ích và tại sao chỉ biểu đồ (a) không đủ để phát hiện mobile.

### Bài 2 — Tìm biến động bị che bởi tổng

Từ bảng `OrderPlaced/OrderCancelled` ở mục 6.1, hãy chứng minh tổng publication của ordering không đổi. Sau đó giữ event type để nhận ra loại event tăng. Giải thích vì sao **chưa được** gọi tỷ lệ `OrderCancelled/OrderPlaced` là tỷ lệ hủy đơn thật khi chưa có hợp đồng nghiệp vụ thống nhất.

### Bài 3 — Phân biệt `by` và `without`

Với tập nhãn giả định `module_identifier`, `module_event_type`, `instance` và `region`, hãy so sánh:

~~~promql
sum by (module_identifier, module_event_type) (rate(module_events_published_total[5m]))

sum without (instance) (rate(module_events_published_total[5m]))
~~~

Trường hợp nào còn `region` trong kết quả? Nếu region bị lỗi riêng, nên giữ nhãn đó ở dashboard nào?

### Bài 4 — Tính average có trọng số

Dùng dữ liệu instance A xử lý 1.000 request trung bình 0,1 giây và B xử lý 10 request trung bình 1,0 giây ở mục 8.1. Tự tính tổng thời gian, số request và độ trễ trung bình thực. Giải thích tại sao `avg(0.1, 1.0)` sai về nghiệp vụ.

### Bài 5 — Chọn tags và kiểm tra cardinality

Thiết kế tag cho `OrderPlaced` theo `channel` và một `priority` hai giá trị. Ước lượng số tổ hợp nếu có 3 channel và 2 priority, trước khi nhân thêm số instance. Sau đó giả sử thêm `orderId`: hãy giải thích vì sao query `sum by(channel)` không loại bỏ vấn đề chi phí xuất metrics tại nguồn.

### Bài 6 — Quan sát thực tế

Nếu có ứng dụng thử nghiệm, thêm `spring-modulith-starter-insight`, `micrometer-registry-prometheus` và phát vài event. Kiểm tra `/actuator/metrics`, `/actuator/prometheus`, xác nhận cách exporter đặt tên nhãn; chỉ sau đó viết các query phù hợp với dữ liệu của hệ thống mình. Tránh dùng endpoint public hoặc dữ liệu khách hàng thật trong bài tập.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `sum(rate(...))` có thể che mất sự cố của một module?

**Đáp án:** Nó gộp bỏ các chiều phân loại như module và event type. Sự tăng của một nhóm có thể bị bù bởi sự giảm của nhóm khác.

**Câu 2.** Khi nào nên dùng `sum without(instance, pod)` thay vì `sum by(module_identifier)`?

**Đáp án:** Khi muốn bỏ đúng các chiều replica/pod nhưng giữ các nhãn khác như event type hoặc region; cần kiểm soát nguy cơ có nhãn mới làm tăng số kết quả.

**Câu 3.** Vì sao `orderId` không nên làm metric tag dù dashboard cuối cùng có aggregation theo channel?

**Đáp án:** Meter và backend vẫn phải xử lý nhiều series riêng ở nguồn; query aggregation không xóa cardinality đã tạo.

**Câu 4.** Counter `module.events.published` có cho biết listener đã gửi email thành công không?

**Đáp án:** Không. Nó phản ánh event publication được instrument; cần metric kết quả listener, logs/traces hoặc trạng thái publication.

**Câu 5.** Công thức đúng để gộp các tỷ lệ success của nhiều instance là gì?

**Đáp án:** Tổng số success chia tổng số attempt thuộc cùng population và cửa sổ, không lấy trung bình không trọng số của tỷ lệ các instance.

**Câu 6.** Khi tính p95 từ classic histogram, phải giữ nhãn gì trước `histogram_quantile`?

**Đáp án:** Nhãn `le` cùng những chiều muốn giữ như module hoặc region; không thể tính p95 tập hợp bằng trung bình p95 từng instance.

## 14. Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): event counters, tag module/event type, `ModulithEventMetricsCustomizer` và module-entry observations.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): low/high cardinality trong observation và cách chuyển metadata thành metrics.
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html): rủi ro cardinality, phát hiện và cơ chế giới hạn.
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): cách diễn giải counter và tốc độ thay vì chỉ xem tổng tăng dần.
- [Prometheus — Operators](https://prometheus.io/docs/prometheus/latest/querying/operators/): `sum`, `by`, `without` và semantics aggregation.
- [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase` và `histogram_quantile`.
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/): tổng hợp histogram và lý do không trung bình các quantile.
- [Prometheus — Recording rules](https://prometheus.io/docs/practices/rules/): tổ chức tên rule, gộp tỷ lệ bằng tử/mẫu và lựa chọn nhãn còn lại.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry và cách đọc metrics qua Actuator.

**Ghi nhớ:** aggregation tốt **giảm số đường biểu đồ mà vẫn giữ thông tin cần để quyết định**. Với Spring Modulith, thường phải giữ module và event type khi chẩn đoán publication; giữ channel/result khi phân tích chất lượng nghiệp vụ; giữ `le` khi tính p95 của classic histogram; và chỉ gộp instance/pod khi không cần debug từng replica. Quan trọng hơn, thiết kế metric với tag hữu hạn ngay từ nguồn: `sum` trong dashboard không sửa được high cardinality đã phát sinh khi xuất dữ liệu.
