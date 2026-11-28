# Giới hạn nhãn số liệu để tránh cardinality cao từ instance_id

Trong một service broker, số lượng service instance và binding có thể tăng liên tục theo tenant, môi trường và thời gian. Mỗi instance thường có một `instance_id` duy nhất; mỗi binding và operation cũng có ID riêng. Những ID này rất hữu ích khi điều tra một yêu cầu cụ thể, nhưng nếu đưa trực tiếp vào label của metric, hệ thống monitoring có thể tạo ra hàng trăm nghìn hoặc hàng triệu time series.

Với Prometheus và các hệ thống metrics dạng time series, mỗi tổ hợp tên metric cùng tập label values tạo thành một time series riêng. Label có giá trị thay đổi theo từng instance làm số series tăng theo số tài nguyên, dù số loại hoạt động broker thực hiện không thay đổi. Hệ quả là Prometheus tiêu thụ nhiều RAM, CPU, dung lượng lưu trữ và thời gian truy vấn hơn; dashboard và alert cũng trở nên khó quản lý.

Trong module `SPRING_CLOUD_SERVICE_BROKER`, metric cần giúp trả lời các câu hỏi vận hành như provision mất bao lâu, provider nào đang lỗi, có bao nhiêu operation đang chạy và tỷ lệ bind thành công là bao nhiêu. Các câu hỏi đó thường không cần một time series riêng cho từng `instance_id`. Bài học này trình bày cách thiết kế label có tập giá trị hữu hạn, chuyển định danh chi tiết sang log/trace, đo cardinality và kiểm thử để ngăn metric tăng không kiểm soát.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích time series và label cardinality trong Prometheus.
- Nhận diện `instance_id`, `binding_id`, `operation_id` và các giá trị động có nguy cơ tạo cardinality cao.
- Ước lượng số time series từ các chiều label và loại metric.
- Thiết kế metric cho provision, update, bind, unbind, deprovision và provider calls bằng label có tập giá trị giới hạn.
- Dùng Micrometer trong Spring mà không tạo tag động theo từng instance.
- Chuyển thông tin định danh cụ thể sang structured logs, traces hoặc exemplars.
- Hiểu giới hạn của relabeling và cách giảm cardinality ở ingestion khi cần khắc phục khẩn cấp.
- Xây dựng dashboard, alert và test để phát hiện cardinality tăng bất thường.

## 1. Time series và cardinality là gì?

Trong Prometheus, một time series được xác định bởi metric name và toàn bộ label set của nó. Ví dụ:

```text
service_broker_operations_total{
  operation="provision",
  outcome="success",
  service="postgresql"
}
```

Time series này đại diện cho tổng số thao tác provision thành công của service `postgresql`. Khi counter tăng theo thời gian, Prometheus lưu các sample mới cho cùng series đó.

Nếu thêm label `instance_id`, mỗi service instance có thể tạo một series riêng:

```text
service_broker_operations_total{
  operation="provision",
  outcome="success",
  service="postgresql",
  instance_id="a7d1..."
}
```

Instance tiếp theo có ID khác sẽ tạo một label set khác và do đó tạo một time series mới. Nếu broker có 100.000 instance, metric này có thể có tới 100.000 series chỉ cho cùng một tổ hợp operation/outcome/service.

**Cardinality** của một label là số giá trị khác nhau mà label đó có thể nhận. Cardinality của một metric phụ thuộc số tổ hợp label set thực tế. Một label có vài giá trị cố định thường dễ kiểm soát; một label chứa ID duy nhất theo request hoặc tài nguyên thường có cardinality rất cao.

### 1.1. Cardinality tăng theo tổ hợp label

Giả sử một metric có các chiều:

- `operation`: 5 giá trị (`provision`, `update`, `deprovision`, `bind`, `unbind`).
- `outcome`: 3 giá trị (`success`, `failure`, `retry`).
- `service`: 4 offering.
- `instance_id`: 50.000 giá trị.

Số tổ hợp tối đa theo tích các chiều là:

```text
5 × 3 × 4 × 50.000 = 3.000.000 time series
```

Đây là ước lượng upper bound nếu mọi tổ hợp đều xuất hiện. Thực tế có thể thấp hơn, nhưng chỉ một label ID duy nhất cũng có thể làm series count tăng gần tuyến tính theo số instance. Khi nhiều metric cùng mang label đó, chi phí bị nhân lên ở từng metric.

### 1.2. Cardinality khác số sample

Một time series có thể nhận hàng nghìn sample theo thời gian mà không tạo hàng nghìn series mới. Vấn đề chính của label động là mỗi giá trị mới tạo ra một series mới, làm tăng số series đang hoạt động và churn khi tài nguyên được tạo/xóa.

Vì vậy, metric counter tăng theo từng request thường vẫn ổn nếu label set được giữ ổn định. Việc thêm `request_id` hoặc `instance_id` khiến mỗi request/instance tạo một series khác nhau mới là nguyên nhân cardinality tăng.

## 2. Vì sao `instance_id` không phù hợp làm metric label?

`instance_id` thường là định danh do platform cấp cho từng service instance. Nó có các đặc điểm:

- Hầu như mỗi instance có một giá trị khác nhau.
- Số lượng instance tăng theo tenant và thời gian.
- Instance bị deprovision nhưng series cũ vẫn có thể tồn tại trong retention window.
- Một số môi trường test tạo/xóa instance liên tục, làm series churn tăng mạnh.
- Mỗi metric mang ID đó lại tạo thêm một nhóm series khác.

Các định danh tương tự cần tránh làm label metric:

| Giá trị | Lý do rủi ro |
|---|---|
| `instance_id` | Một giá trị riêng cho từng service instance. |
| `binding_id` | Mỗi binding thường có ID riêng; số binding có thể rất lớn. |
| `operation_id` | Mỗi lần provision/update/deprovision có thể tạo operation mới. |
| `request_id`, `correlation_id`, `trace_id` | Thường duy nhất theo request hoặc trace. |
| `tenant_id`, `organization_guid`, `space_guid` | Có thể tăng theo số khách hàng/tổ chức và vòng đời hệ thống. |
| `resource_name`, `pod_name`, `namespace` | Có thể thay đổi theo lần deploy hoặc từng tenant. |
| URL đầy đủ, hostname, SQL, exception message | Giá trị động, khó giới hạn và có thể chứa dữ liệu nhạy cảm. |

Hash hoặc rút ngắn `instance_id` không giải quyết cardinality. Nếu mỗi ID vẫn ánh xạ tới một giá trị khác nhau, số series vẫn gần như không đổi; chỉ chuỗi label ngắn hơn.

### 2.1. Không phải mọi label có nhiều giá trị đều sai

Label hữu ích khi nó biểu diễn một chiều phân tích có tập giá trị được kiểm soát. Ví dụ `operation=provision|update|bind`, `outcome=success|failure`, `provider=postgres|redis` có thể hữu ích cho dashboard và alert.

Tuy nhiên, một chiều tưởng như hữu hạn vẫn có thể trở nên động nếu giá trị lấy trực tiếp từ cấu hình tenant hoặc catalog do người dùng tự tạo. Cần xác định giới hạn số service/plan/provider được phép và chuẩn hóa giá trị trước khi đưa vào metric.

## 3. Chọn label có cardinality thấp và ý nghĩa vận hành

Một metric tốt trả lời một câu hỏi vận hành cụ thể. Chỉ thêm label khi dashboard, alert hoặc truy vấn thực sự cần phân tách theo chiều đó.

Các label thường phù hợp với service broker nếu được giới hạn:

| Label | Giá trị đề xuất | Cách kiểm soát |
|---|---|---|
| `operation` | `provision`, `update`, `deprovision`, `bind`, `unbind` | Enum trong code, không dùng tên method tùy ý. |
| `outcome` | `success`, `failure`, `retrying` | Chuẩn hóa từ trạng thái nội bộ. |
| `state` | `queued`, `running`, `retry_wait`, `reconciling`, `succeeded`, `failed` | Tập state cố định trong broker. |
| `service` | `postgresql`, `redis`, `rabbitmq` | Chỉ dùng service key đã được allowlist và giới hạn số offering. |
| `plan` | `small`, `standard`, `large` | Chỉ dùng plan key đã được kiểm soát; cân nhắc bỏ nếu số plan động. |
| `provider` | `aws-rds`, `azure-db`, `kubernetes-operator` | Alias cố định, không dùng endpoint hoặc account ID. |
| `error_code` | `rate_limited`, `timeout`, `unauthorized`, `quota_exceeded` | Ánh xạ exception vào enum ổn định. |
| `http_status_class` | `2xx`, `4xx`, `5xx` | Nhóm status code thay vì lưu mọi giá trị hoặc response text. |

Một quy tắc thực tế: label phải có tập giá trị tối đa có thể liệt kê và review được. Nếu không thể trả lời “label này có tối đa bao nhiêu giá trị trong production?”, không nên thêm nó vào metric trước khi có giới hạn rõ ràng.

### 3.1. Label không nên chứa thông tin bí mật hoặc nội dung tự do

Không dùng password, token, connection URI, email, SQL, exception message hoặc raw request parameter làm label. Ngoài cardinality, các giá trị này có thể làm lộ dữ liệu nhạy cảm qua Prometheus, Grafana, remote write hoặc alert notification.

Không dùng `description` do người dùng cấu hình làm label. Nếu cần phân nhóm lỗi, ánh xạ sang một `error_code` hữu hạn do broker định nghĩa.

### 3.2. Phân biệt `instance` target label với `instance_id` OSB

Prometheus thường có label `instance` để chỉ target được scrape, thường là địa chỉ host:port của broker hoặc exporter. Đây là metadata target do Prometheus gắn vào sample. Nó khác `instance_id` của service instance trong OSB.

Không đổi target label `instance` thành một danh sách service instance ID. Với broker chạy nhiều replica, target label có thể phân biệt replica broker; `instance_id` vẫn nên được giữ ngoài metric label.

## 4. Ví dụ metric xấu và metric tốt

### 4.1. Thiết kế gây cardinality cao

```text
service_broker_operation_duration_seconds{
  operation="provision",
  instance_id="f89a2e7c-...",
  operation_id="op-7b3d...",
  tenant_id="tenant-9482",
  provider="postgres"
}
```

Mỗi instance/operation/tenant có thể tạo một chuỗi label set mới. Metric này còn kết hợp nhiều ID duy nhất, làm số tổ hợp tăng theo từng lần chạy.

### 4.2. Thiết kế có label bounded

```text
service_broker_operation_duration_seconds{
  operation="provision",
  service="postgresql",
  provider="postgres",
  outcome="success"
}
```

Metric này trả lời câu hỏi thời gian provision của PostgreSQL thành công qua provider Postgres. Có thể tổng hợp p50/p95/p99 theo service, provider và operation mà không tạo một series cho từng instance.

### 4.3. Ví dụ metric cho các hoạt động broker

```text
service_broker_requests_total{
  operation="bind",
  service="postgresql",
  outcome="success"
}

service_broker_operations_in_progress{
  operation="provision",
  service="postgresql"
}

service_broker_operation_duration_seconds_bucket{
  operation="deprovision",
  service="postgresql",
  outcome="success",
  le="30"
}

service_broker_provider_requests_total{
  provider="postgres",
  operation="create_database",
  outcome="rate_limited"
}
```

Tên metric và label là quy ước minh họa. Cần thống nhất naming convention trong broker, ví dụ counter kết thúc bằng `_total`, duration dùng đơn vị giây và label `outcome` có tập giá trị cố định.

## 5. Ước lượng và đặt ngân sách cardinality

Trước khi thêm một metric mới, liệt kê số giá trị tối đa của từng label và nhân chúng để ước lượng số tổ hợp. Ví dụ:

| Metric | Label dimensions | Ước lượng tổ hợp tối đa |
|---|---|---:|
| Request counter | 5 operation × 3 outcome × 4 service | 60 |
| Operation gauge | 5 operation × 4 service × 6 state | 120 |
| Provider latency | 4 provider × 5 operation × 3 outcome | 60 |
| Metric có instance ID | 5 operation × 3 outcome × 4 service × 50.000 instance | 3.000.000 |

Ước lượng này chưa tính số series của histogram, quantile hoặc các metric bổ sung do instrumentation tạo ra. Histogram classic có nhiều series bucket, cộng thêm series `_sum` và `_count` cho mỗi label set; vì vậy một histogram có cùng label set thường tốn nhiều series hơn một counter/gauge đơn giản.

### 5.1. Lập ngân sách theo metric và toàn broker

Nên đặt ngân sách dựa trên:

- Số service offering và plan được phép công bố.
- Số loại operation và state cố định.
- Số provider adapter.
- Số replica broker và target scrape.
- Số metric counter/gauge/timer/histogram được tạo.
- Bucket count của histogram và cách backend lưu native/classic histogram.
- Tần suất tạo/xóa instance và thời gian retention của series cũ.

Không có một ngưỡng cardinality phù hợp cho mọi cluster Prometheus. Ngân sách cần dựa trên tài nguyên, scrape interval, retention, remote write và số tenant thực tế. Quan trọng là theo dõi xu hướng active series và series churn, không chỉ chụp một con số tại một thời điểm.

### 5.2. Chú ý series churn

Ngay cả khi số instance đang active ổn định, mỗi lần tạo instance mới với label ID mới rồi deprovision instance cũ vẫn tạo series mới. Series cũ tiếp tục chiếm dữ liệu trong retention window. Do đó, một metric theo `instance_id` có thể gây chi phí lưu trữ tăng theo tổng số instance từng xuất hiện, không chỉ số instance đang hoạt động.

## 6. Instrumentation trong Spring với Micrometer

Spring Boot Actuator thường dùng Micrometer làm facade metrics. Khi tạo Counter, Timer hoặc Gauge, các tag được chuyển thành label trong backend Prometheus. Vì vậy, không thêm ID động vào `.tag()` hoặc `.tags()`.

### 6.1. Ví dụ Counter an toàn

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class BrokerMetrics {

    private final MeterRegistry registry;

    public BrokerMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordOperation(String operation, String service, String outcome) {
        Counter.builder("service_broker_operations_total")
                .description("Number of service broker lifecycle operations")
                .tag("operation", normalizeOperation(operation))
                .tag("service", normalizeService(service))
                .tag("outcome", normalizeOutcome(outcome))
                .register(registry)
                .increment();
    }

    private String normalizeOperation(String value) {
        return switch (value) {
            case "provision", "update", "deprovision", "bind", "unbind" -> value;
            default -> "other";
        };
    }

    private String normalizeService(String value) {
        return switch (value) {
            case "postgresql", "redis", "rabbitmq" -> value;
            default -> "other";
        };
    }

    private String normalizeOutcome(String value) {
        return switch (value) {
            case "success", "failure", "retrying" -> value;
            default -> "other";
        };
    }
}
```

Các hàm normalize là ví dụ allowlist. Trong production, có thể dùng enum hoặc metric key được cấu hình khi broker khởi động. Điều quan trọng là giá trị tag không được lấy nguyên vẹn từ ID, parameters hoặc nội dung lỗi của request.

### 6.2. Ví dụ Timer không gắn instance ID

```java
Timer.builder("service_broker_operation_duration")
        .description("Duration of service broker operations")
        .tag("operation", operationType.metricValue())
        .tag("service", serviceMetricKey)
        .tag("outcome", outcome.metricValue())
        .register(meterRegistry)
        .record(duration);
```

`serviceMetricKey` phải là key có tập giá trị giới hạn, không phải `instance_id` hoặc tên resource tùy ý. Timer có thể được export thành histogram/summary tùy cấu hình registry; hãy xem số series thực tế sau khi bật histogram.

### 6.3. Ví dụ sai: tag theo từng instance

```java
Counter.builder("service_broker_provision_total")
        .tag("instance_id", request.getServiceInstanceId())
        .register(meterRegistry)
        .increment();
```

Đoạn code này tạo meter riêng cho mỗi `instance_id`. Khi số instance tăng, MeterRegistry giữ nhiều meter hơn và Prometheus nhận nhiều series hơn. Không dùng hash hoặc substring của ID để né vấn đề; hãy bỏ ID khỏi metric dimension.

### 6.4. Tránh dynamic tag trong exception handler

Không viết:

```java
.tag("error", exception.getMessage())
```

Exception message có thể chứa resource name, URL, SQL, provider request ID hoặc dữ liệu thay đổi theo mỗi request. Hãy ánh xạ sang enum:

```java
String errorCode = switch (providerError.category()) {
    case RATE_LIMITED -> "rate_limited";
    case TIMEOUT -> "timeout";
    case UNAUTHORIZED -> "unauthorized";
    case QUOTA_EXCEEDED -> "quota_exceeded";
    default -> "other";
};
```

Giữ chi tiết exception đã làm sạch trong log/trace theo quyền truy cập; metric chỉ dùng `error_code` hữu hạn.

## 7. Đưa instance_id vào logs và traces thay vì metric labels

Không gắn `instance_id` vào metric không có nghĩa là bỏ khả năng điều tra một instance cụ thể. Logs và traces phù hợp hơn cho các sự kiện có định danh duy nhất.

### 7.1. Structured logs

Log có cấu trúc có thể giữ các trường:

```json
{
  "event": "service_instance_provision_completed",
  "instance_id": "instance-123",
  "operation_id": "op-456",
  "tenant_id": "tenant-acme",
  "service": "postgresql",
  "outcome": "success",
  "duration_ms": 8420,
  "correlation_id": "req-abc"
}
```

Đây là ví dụ log nội bộ, không phải metric sample. Log store có thể tìm theo `instance_id` khi điều tra. Cần giới hạn quyền truy cập, retention và bảo vệ dữ liệu định danh; tuyệt đối không đưa credentials hoặc token vào log.

### 7.2. Distributed tracing

Một trace có thể nối request từ platform tới broker, worker và provider adapter. Span có thể chứa thuộc tính như `osb.instance_id`, `osb.operation_id`, `osb.service_id` và `provider.request_id` để tìm một workflow cụ thể.

Các thuộc tính này không nên tự động được chuyển thành metric label. Một số backend tracing cho phép truy vấn attribute nhưng việc index toàn bộ giá trị duy nhất cũng có thể phát sinh chi phí. Cần áp dụng sampling, retention và indexing policy phù hợp; không ghi secret vào span attribute.

### 7.3. Exemplars liên kết metric với trace

Exemplar cho phép một sample histogram/counter mang tham chiếu tới trace ID mà không biến trace ID thành label của toàn bộ time series. Khi backend và instrumentation hỗ trợ, dashboard có thể điều hướng từ một điểm latency bất thường tới trace đại diện.

Exemplar không thay thế log/trace storage và không bảo đảm mọi backend đều hỗ trợ cùng cách truy vấn. Tuy nhiên, đây là cách hữu ích để giữ metric cardinality thấp mà vẫn có đường đi tới một lần request cụ thể.

## 8. Thiết kế metric cho vòng đời OSB

Một bộ metric có thể bao phủ các câu hỏi chính mà không cần định danh từng instance.

| Metric | Loại | Label bounded gợi ý | Câu hỏi trả lời |
|---|---|---|---|
| `service_broker_operations_total` | Counter | `operation`, `service`, `outcome` | Có bao nhiêu thao tác theo loại và kết quả? |
| `service_broker_operation_duration_seconds` | Timer/Histogram | `operation`, `service`, `outcome` | Provision/update/bind mất bao lâu? |
| `service_broker_operations_in_progress` | Gauge | `operation`, `service`, `state` | Có bao nhiêu operation đang ở từng state? |
| `service_broker_provider_requests_total` | Counter | `provider`, `operation`, `outcome` | Provider nào đang lỗi hoặc bị rate limit? |
| `service_broker_provider_request_duration_seconds` | Histogram | `provider`, `operation`, `outcome` | Provider latency thay đổi thế nào? |
| `service_broker_last_operation_polls_total` | Counter | `state`, `operation` | Platform polling với tần suất và state nào? |
| `service_broker_outbox_pending` | Gauge | `event_type` | Có bao nhiêu event đang chờ dispatch? |
| `service_broker_active_instances` | Gauge | `service`, `plan`, `state` | Có bao nhiêu instance active theo offering/plan? |

Metric `active_instances` cần được tính từ aggregate hoặc state store theo chu kỳ, không tạo một Gauge meter riêng cho mỗi instance. Nếu service/plan có thể được tenant tự tạo không giới hạn, không dùng raw name làm label; chuẩn hóa sang nhóm hữu hạn hoặc bỏ chiều đó.

### 8.1. Đo operation đang chạy mà không tạo meter theo instance

Có thể dùng gauge tổng số operation theo loại và state. Khi operation bắt đầu, tăng gauge; khi operation kết thúc hoặc chuyển state, cập nhật đúng counter/gauge tương ứng. Cần bảo đảm update metric không bị lệch khi worker restart; nếu gauge chỉ ở memory của process, nó không phải nguồn dữ liệu bền vững. Với số liệu cần phản ánh chính xác qua nhiều replica, có thể tính từ operation store và export aggregate theo chu kỳ.

### 8.2. Không tạo label theo từng endpoint URL

Với HTTP metrics, dùng route template như `/v2/service_instances/{instance_id}` thay vì URL đã thay placeholder thành ID thật. Dùng method và status class hoặc status code trong tập được giới hạn. Không đưa query string, operation ID hoặc tenant path segment vào label.

## 9. Histogram và cardinality

Histogram giúp đo phân phối latency, nhưng mỗi label set tạo ra nhiều series bucket. Nếu metric có 10 label set và histogram có 12 bucket hữu hạn, backend classic histogram còn có bucket `+Inf`, `_sum` và `_count`; số series thực tế lớn hơn một metric counter với cùng label set.

Vì vậy:

- Giữ số label dimension của histogram ít hơn counter nếu không cần phân tích sâu.
- Chọn bucket dựa trên SLA và độ trễ thực tế, không tạo hàng trăm bucket không cần thiết.
- Không dùng histogram theo `instance_id`, `operation_id` hoặc `tenant_id`.
- Kiểm tra cách Micrometer export histogram và backend đang dùng.
- Cân nhắc native histogram nếu toàn bộ stack hỗ trợ và có lợi cho workload; việc đổi histogram type không làm label cardinality động trở nên an toàn.

Ví dụ, một histogram provision theo `service` và `outcome` có thể đủ để phát hiện p95 tăng. Không cần một histogram riêng cho từng database instance.

## 10. Multi-tenant metrics mà không lộ tenant ID

Trong service broker multi-tenant, nhóm vận hành có thể muốn so sánh tải giữa các tenant. Đưa `tenant_id` trực tiếp vào mọi metric thường không phải lựa chọn tốt nếu số tenant lớn hoặc thay đổi liên tục.

Các lựa chọn:

- Dùng label `tenant_tier` với tập nhỏ như `free`, `standard`, `enterprise` nếu tier có ý nghĩa vận hành.
- Tổng hợp theo provider, service, region hoặc plan class có giới hạn.
- Dùng dashboard/query trên log analytics hoặc hệ thống billing có mô hình dữ liệu phù hợp cho phân tích theo tenant.
- Chỉ xuất metric tenant-specific cho một tập tenant được allowlist rõ ràng và có ngân sách series riêng, nếu thực sự cần.
- Tách tenant observability vào hệ thống metrics riêng khi có yêu cầu cách ly và quota rõ ràng.

Hash tenant ID không làm giảm cardinality. Thêm label tenant vào một metric có thể nhân số series với số tenant. Cần đánh giá quyền truy cập dashboard và nguy cơ suy luận hoạt động của khách hàng qua metric.

## 11. Giảm cardinality ở Prometheus khi cần khắc phục khẩn cấp

Biện pháp tốt nhất là sửa instrumentation để không phát label động. Trong lúc chờ release, Prometheus có thể dùng metric relabeling để loại bỏ label không cần hoặc bỏ hẳn metric gây vấn đề.

Ví dụ loại bỏ một metric debug có cardinality cao khỏi scrape:

```yaml
scrape_configs:
  - job_name: service-broker
    static_configs:
      - targets: ["broker:8080"]
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: "service_broker_instance_debug_info"
        action: drop
```

Đây là biện pháp tạm thời để bỏ metric không thiết yếu. Nó không sửa instrumentation và có thể làm mất dữ liệu cần điều tra. Cần ghi nhận metric bị drop, theo dõi ảnh hưởng dashboard/alert và loại bỏ rule sau khi code được sửa.

### 11.1. Cẩn thận khi dùng `labeldrop`

Có thể dùng action `labeldrop` để xóa label name như `instance_id`, nhưng cần đánh giá trước khi áp dụng. Nếu nhiều series khác nhau chỉ phân biệt bởi `instance_id`, việc xóa label sẽ làm chúng có cùng metric name và label set; dữ liệu có thể bị gộp hoặc gây xung đột sample. Không coi `labeldrop` là giải pháp an toàn mặc định.

Nếu buộc phải dùng, hãy:

1. Kiểm tra các series sau relabel có bị trùng label set hay không.
2. Xác nhận aggregation mong muốn khi nhiều instance được gộp.
3. Kiểm tra duplicate/out-of-order sample và cảnh báo ingestion.
4. Thực hiện trong môi trường staging trước.
5. Sửa instrumentation để phát metric bounded ở nguồn càng sớm càng tốt.

Metric relabeling xảy ra ở phía Prometheus sau khi scrape; nó không nhất thiết giảm số meter mà broker tạo trong JVM hoặc lượng dữ liệu endpoint phải serialize. Vì vậy, nó là lớp giảm tải ingestion, không thay thế việc sửa code.

## 12. Dashboard và alert nên dùng aggregate

Dashboard vận hành broker thường cần nhìn xu hướng tổng thể:

- Request rate theo operation/service.
- Tỷ lệ success/failure/retry.
- p50/p95/p99 latency theo operation/provider.
- Số operation đang chạy theo state.
- Provider rate limit và error rate.
- Outbox backlog, queue lag và thời gian operation chờ.
- Active instance count theo service/plan class.
- Active series và series churn của Prometheus.

Alert nên phát hiện vấn đề ở cấp service hoặc provider, ví dụ tỷ lệ provision failure vượt ngưỡng trong 10 phút hoặc p95 provider latency tăng. Tránh tạo alert rule riêng cho từng `instance_id` nếu không có hệ thống incident routing được thiết kế cho quy mô đó.

### 12.1. Ví dụ PromQL aggregate

Tốc độ provision theo service:

```promql
sum by (service) (
  rate(service_broker_operations_total{operation="provision"}[5m])
)
```

Tỷ lệ provision failure:

```promql
sum by (service) (
  rate(service_broker_operations_total{
    operation="provision",
    outcome="failure"
  }[5m])
)
/
clamp_min(
  sum by (service) (
    rate(service_broker_operations_total{operation="provision"}[5m])
  ),
  1e-9
)
```

Số operation đang chạy:

```promql
sum by (operation, state) (
  service_broker_operations_in_progress
)
```

Các truy vấn trên giả định metric được export với label như ví dụ. Chúng tổng hợp theo chiều bounded và không cần `instance_id`.

### 12.2. Drill-down từ dashboard

Khi metric báo p95 provision tăng, người vận hành có thể:

1. Chọn khoảng thời gian bất thường trên dashboard.
2. Mở exemplar/trace liên quan nếu backend hỗ trợ.
3. Tìm structured log theo `operation_id` hoặc `instance_id` từ trace/log context.
4. Đối chiếu provider request ID và operation state.

Cách này giữ metric gọn nhưng vẫn có đường điều tra chi tiết. Không cần biến mọi ID thành label để có thể tìm kiếm khi sự cố xảy ra.

## 13. Đo cardinality và phát hiện tăng bất thường

Trong Prometheus, có thể dùng metric nội bộ của server để quan sát số series. Một truy vấn phổ biến:

```promql
prometheus_tsdb_head_series
```

Theo dõi tốc độ tạo series:

```promql
rate(prometheus_tsdb_head_series_created_total[5m])
```

Tên metric nội bộ và khả năng có mặt phụ thuộc phiên bản/cấu hình Prometheus. Hãy xác minh metric thực tế trên server. Có thể dùng Prometheus UI/TSDB status hoặc công cụ phân tích cardinality của nền tảng metrics để xác định metric name và label nào chiếm nhiều series nhất.

Các dấu hiệu cần chú ý:

- Active series tăng nhanh dù request rate và số broker replica ổn định.
- Một metric có số series tăng gần bằng số service instance hoặc binding.
- Series churn cao sau các đợt test/provision/deprovision.
- Prometheus memory, WAL, compaction hoặc remote write backlog tăng.
- Query dashboard chậm hơn sau khi thêm một label.

Không chỉ nhìn tổng active series. Hãy tìm metric cụ thể tạo ra series và kiểm tra label values. Một metric mới có thể chỉ chiếm một phần tổng số series nhưng vẫn gây chi phí đáng kể nếu dùng histogram.

## 14. Kiểm thử cardinality trong ứng dụng Spring

Cardinality cần được kiểm tra như một thuộc tính của instrumentation, không chỉ là vấn đề cấu hình Prometheus.

### 14.1. Kiểm tra meter count khi instance ID thay đổi

Với Micrometer `SimpleMeterRegistry`, có thể gọi cùng một thao tác với nhiều ID khác nhau và xác minh số meter không tăng theo số ID:

```java
@Test
void instanceIdsDoNotCreateNewMeters() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    BrokerMetrics metrics = new BrokerMetrics(registry);

    for (int i = 0; i < 1_000; i++) {
        metrics.recordOperation("provision", "postgresql", "success");
    }

    assertThat(registry.find("service_broker_operations_total")
            .tags("operation", "provision", "service", "postgresql",
                  "outcome", "success")
            .counter())
            .isNotNull();
    assertThat(registry.getMeters()).hasSize(1);
}
```

Ví dụ này kiểm tra method metrics chỉ nhận label bounded. Nếu code thiết kế buộc truyền instance ID để ghi log, không truyền nó vào method tạo meter; tách logger/tracing khỏi metrics API.

### 14.2. Kiểm tra tag keys bị cấm

Có thể duyệt meter trong test và assert không có tag key như `instance_id`, `binding_id`, `operation_id`, `request_id`, `trace_id` hoặc `tenant_id` trên các metric broker được kiểm soát.

Không nên cấm toàn bộ tag key `instance` của Prometheus target vì nó có ý nghĩa riêng là scrape target. Phạm vi kiểm tra cần phân biệt metric instrumentation của ứng dụng và external labels/target labels.

### 14.3. Kiểm thử endpoint scrape

Trong integration test, scrape endpoint metrics sau khi tạo nhiều instance test. Xác minh:

- Không có label value chứa ID của từng instance.
- Số series của metric lifecycle tăng theo số tổ hợp bounded đã thiết kế, không tăng theo số instance.
- Histogram chỉ có số bucket đã cấu hình.
- Error code được normalize, không chứa exception message.
- Không có credentials hoặc tenant secret trong exposition output.

Một test tạo hàng nghìn ID giả thường đủ để phát hiện regression trước khi triển khai; không cần tạo hàng nghìn provider resource thật.

## 15. Những lỗi thiết kế thường gặp

- **Gắn `instance_id` vào mọi metric:** số series tăng theo số instance và từng metric.
- **Hash ID để giảm cardinality:** hash vẫn tạo một giá trị khác nhau cho mỗi instance.
- **Gắn `operation_id` hoặc `request_id`:** mỗi request tạo series mới.
- **Gắn `tenant_id` không giới hạn:** cardinality tăng theo số tenant và có thể lộ cấu trúc khách hàng.
- **Dùng exception message làm label:** giá trị không ổn định, có thể chứa dữ liệu nhạy cảm.
- **Dùng URL đầy đủ làm label:** path/query động làm nổ số series.
- **Thêm quá nhiều dimension hữu hạn:** tích các chiều vẫn có thể tạo số tổ hợp rất lớn.
- **Quên histogram multiplier:** bucket, sum và count làm series count lớn hơn dự kiến.
- **Chỉ dùng relabeling để chữa:** broker vẫn tạo meter động và Prometheus vẫn phải scrape payload trước relabel.
- **Alert theo từng instance:** tạo quá nhiều alert instance và khó vận hành.
- **Không có test cardinality:** regression chỉ được phát hiện sau khi Prometheus quá tải.

## 16. Checklist thiết kế metric cho service broker

- [ ] Mỗi metric có câu hỏi vận hành rõ ràng.
- [ ] Label values có tập hữu hạn và được liệt kê/kiểm soát.
- [ ] Không dùng `instance_id`, `binding_id`, `operation_id`, `request_id` hoặc `trace_id` làm metric label.
- [ ] Không dùng raw tenant ID, namespace, resource name, URL hoặc exception message làm label.
- [ ] Service/plan/provider label dùng key đã allowlist và có ngân sách.
- [ ] Cardinality được ước lượng bằng tích các chiều label.
- [ ] Histogram bucket count được tính vào ngân sách series.
- [ ] Chi tiết từng instance được ghi trong structured logs/traces có kiểm soát.
- [ ] Có thể drill-down từ metric tới trace/log bằng correlation ID hoặc exemplar.
- [ ] Dashboard và alert ưu tiên aggregate theo operation/service/provider/state.
- [ ] Có theo dõi active series và series churn.
- [ ] Có test xác minh meter count không tăng theo số instance ID.
- [ ] Có kiểm tra exposition endpoint không chứa ID/secret ngoài dự kiến.
- [ ] Relabeling chỉ dùng làm biện pháp tạm thời sau khi đánh giá series collision.

## 17. Bài tập tự luyện

### Bài tập 1: Tính cardinality

Một metric có `operation` gồm 5 giá trị, `outcome` 3 giá trị, `service` 6 giá trị và `instance_id` 20.000 giá trị. Hãy tính upper bound số series và đề xuất cách giảm label dimension.

### Bài tập 2: Thiết kế metric provision

Thiết kế counter và histogram để đo số lần provision và latency theo service/provider/outcome. Nêu rõ label nào có tập giá trị hữu hạn và label nào cần loại bỏ.

### Bài tập 3: Chọn nơi lưu instance_id

Một operator muốn xem toàn bộ operation của `instance-123`. Hãy mô tả cách dùng metric aggregate để phát hiện bất thường rồi dùng trace/log để tìm đúng operation mà không đưa ID vào label.

### Bài tập 4: Phân tích histogram

Một histogram có 8 chiều label set và 10 bucket hữu hạn. Hãy ước lượng số series classic histogram cho một tổ hợp label set, tính cả bucket `+Inf`, `_sum` và `_count`; sau đó đề xuất cách giảm số bucket hoặc dimension.

### Bài tập 5: Kiểm thử regression

Viết test tạo 1.000 instance ID giả và ghi metric cho cùng operation/service/outcome. Xác định assertion để chứng minh meter count không tăng theo số ID.

## Kết luận

`instance_id` là dữ liệu định danh quan trọng để truy vết một service instance, nhưng không phù hợp làm label của metric có vòng đời dài và số lượng lớn. Với Prometheus/Micrometer, mỗi label set duy nhất tạo một time series; vì vậy cần giữ label ở những chiều có tập giá trị hữu hạn như operation, outcome, service, provider và state. Thông tin chi tiết theo instance nên nằm trong structured logs, traces hoặc exemplar. Khi ước lượng cardinality từ đầu, kiểm tra meter count và theo dõi active series, service broker có thể giữ monitoring ổn định khi số instance, binding và operation tăng lên.

## Tài liệu tham khảo

- [Prometheus Documentation — Data model](https://prometheus.io/docs/concepts/data_model/)
- [Prometheus Documentation — Metric and label naming](https://prometheus.io/docs/practices/naming/)
- [Prometheus Documentation — Instrumentation practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus Documentation — Histograms and summaries](https://prometheus.io/docs/practices/histograms/)
- [Micrometer Documentation — Meter concepts](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Micrometer Documentation — Prometheus registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
