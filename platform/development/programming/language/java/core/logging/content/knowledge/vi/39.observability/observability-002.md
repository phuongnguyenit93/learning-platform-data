# Log và dashboard trong Observability cho ứng dụng Java

## 1. Mục tiêu: biến log thành thông tin vận hành có thể hành động

**Log và dashboard** là hai lớp khác nhau trong một hệ thống **Observability**:

- **Log** ghi lại những sự kiện cụ thể: thời điểm, nguồn phát, mức độ, thao tác, kết quả, mã lỗi và ngữ cảnh để điều tra.
- **Dashboard** tổ chức các truy vấn, biểu đồ, bảng và liên kết điều tra để người vận hành nhìn thấy tình trạng dịch vụ qua một khoảng thời gian.
- **Observability** là khả năng hiểu trạng thái bên trong hệ thống dựa trên các tín hiệu bên ngoài, thường phối hợp **logs, metrics và traces**. Một dashboard đẹp nhưng dữ liệu bị thiếu, sai ngữ nghĩa hoặc không liên kết được sự cố thì chưa phải observability tốt.

Ví dụ khi nhóm vận hành thấy HTTP 5xx tăng, họ thường muốn trả lời lần lượt:
1. Service và môi trường nào đang gặp vấn đề?
2. Tỷ lệ lỗi, thông lượng và latency thay đổi từ khi nào?
3. Lỗi tập trung ở route, phiên bản triển khai, instance hoặc nhóm sự kiện nào?
4. Có log chi tiết, stack trace và trace ID để lần theo request cụ thể không?
5. Dữ liệu trên dashboard có đầy đủ không, hay pipeline logging đang chậm, sampling hoặc drop?

Bài học trong nhóm **Observability** này sử dụng **Java 17+, JUL/SLF4J và Grafana Loki/LogQL** làm ví dụ. Những khái niệm chính cũng áp dụng cho Elasticsearch/Kibana, OpenSearch Dashboards hoặc nền tảng logging khác, nhưng **cú pháp truy vấn và khả năng hệ thống không giống nhau**.

Kết thúc bài, bạn có thể:
- Thiết kế một event log có schema ổn định, đủ để truy vấn nhưng không dư dữ liệu.
- Hiểu pipeline từ Java logger đến collector/storage và dashboard.
- Chọn Loki stream labels so với parsed fields/structured metadata để tránh high cardinality.
- Viết truy vấn LogQL cho log table, volume, rate, 5xx, lỗi theo route và latency p95.
- Dựng các panel phục vụ vận hành và liên kết logs với traces/metrics.
- Viết và chạy ví dụ Java 17+ phát event có kiểm soát, tính một bản tổng hợp nhỏ và kiểm tra nội dung không rò secret.
- Đánh giá sampling, lỗi ingestion, retention, quyền truy cập và tính đúng của cảnh báo.

## 2. Luồng dữ liệu: từ câu lệnh logger tới dashboard

Một kiến trúc tham khảo:

```text
Java service (JUL / SLF4J + Logback / Log4j 2)
  |
  | logger.info("event=...") hoặc structured JSON
  v
Console / stdout / rolling file / OTLP exporter
  |
  v
Agent / collector / pipeline (parse, enrich, batch, redact)
  |
  v
Log backend (ví dụ Grafana Loki)
  |
  v
Grafana Explore / dashboard / alert query
  |
  +----> drill-down bằng request_id / trace_id -> trace backend
  |
  +----> so sánh với metrics ở Prometheus/OpenTelemetry
```

**Không phải ứng dụng Java gửi trực tiếp dữ liệu đến Grafana UI.** Grafana thường truy vấn một *data source* như Loki. Tầng ứng dụng phát event, một agent/collector có thể vận chuyển và chuẩn hóa, backend lưu/index phù hợp, dashboard thực hiện truy vấn.

Định nghĩa rõ trách nhiệm:
- **Application:** chọn sự kiện/field có ý nghĩa; không ghi password, token, raw payload nhạy cảm.
- **Logging API/backend:** quyết định level, layout, format, encoder, appender, buffering, sync/async.
- **Collector:** nhận, gắn resource metadata, lọc/redact bổ sung, gửi dữ liệu, retry/batch theo policy.
- **Storage:** retention, query/index, multi-tenancy, quotas, quyền truy cập.
- **Dashboard:** tập trung vào câu hỏi vận hành, đưa ra panel có đơn vị, cửa sổ thời gian, nguồn dữ liệu và link điều tra.
- **Alerting:** phát hiện điều kiện quan trọng trên tín hiệu đáng tin; có ngưỡng, thời gian chờ, routing và runbook.

Một log event phát sinh trong JVM có thể **không đến dashboard** nếu bị logger level/filter chặn, queue đầy, appender lỗi, agent chưa kịp đẩy, collector bị giới hạn, backend chưa index hoặc quyền truy vấn không phù hợp. Vì vậy cần quan sát chính **pipeline logging**, không chỉ quan sát ứng dụng.

## 3. Logs, metrics, traces: mỗi loại trả lời điều gì?

| Tín hiệu | Câu hỏi phù hợp | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Logs | “Lỗi nào, trong request nào, kèm chi tiết gì?” | Giàu ngữ cảnh, tìm nguyên nhân cụ thể | Chi phí cao, có thể thiếu/sampling/drop |
| Metrics | “RPS, error rate, p95 đang biến động ra sao?” | Tối ưu cho tổng hợp định lượng, alert | Không đủ chi tiết từng sự kiện |
| Traces | “Request đã đi qua service/span nào?” | Liên kết luồng phân tán, waterfall latency | Thường sampling, cần propagation |
| Dashboard | “Hiện tại và xu hướng dịch vụ có gì bất thường?” | Cửa sổ vận hành kết hợp nhiều tín hiệu | Không sửa được dữ liệu gốc sai/thiếu |

**Không dùng logs để thay thế mọi metrics**. Ví dụ để giám sát SLO 99,9%, metrics/histogram từ điểm đo phù hợp thường đáng tin hơn việc đếm log dòng, đặc biệt nếu success log bị sampling. Log giúp điều tra những request bất thường phía sau cảnh báo metric.

Một luồng điều tra hiệu quả thường là:

```text
Metric: 5xx tăng -> Dashboard: route /orders/{id} xấu đi
         |
         v
Explore: log event=order_lookup_failed theo time range
         |
         v
Trace ID -> distributed trace -> span database timeout
         |
         v
Xác định thay đổi deployment / dependency / saturation
```

Correlation ID/trace ID tạo cầu nối. Tuy nhiên ID không thay thế xác nhận thời điểm, service, route, error code hay trạng thái thực tế.

## 4. Thiết kế event log để dashboard đọc được

Một bản ghi nên có **schema ổn định**. Ví dụ dạng JSON:

```json
{
  "timestamp": "2026-11-10T03:15:30Z",
  "severity": "ERROR",
  "service": "orders-api",
  "environment": "prod",
  "event": "http_request",
  "route": "/orders/{id}",
  "status": 503,
  "duration_ms": 75,
  "error_type": "UPSTREAM_TIMEOUT",
  "correlation_id": "req_7c9"
}
```

Đây là ví dụ giả định, không phải event thu từ production.

### 4.1. Nhóm field nên cân nhắc

| Nhóm | Field | Mục đích |
| --- | --- | --- |
| Thời gian | `timestamp`, ingestion/observed timestamp | Xác định lúc sự kiện xảy ra và độ trễ đến backend |
| Nguồn | `service`, `environment`, `instance`, `deployment_version` | Xác định dịch vụ, môi trường và thay đổi triển khai |
| Mức độ | `severity` / `level` | Lọc INFO/WARN/ERROR theo contract backend |
| Loại event | `event`, `error_type` | Truy vấn ổn định thay vì tìm câu tiếng Việt tự do |
| Request | `method`, `route`, `status`, `duration_ms` | Tạo bảng/tỷ lệ lỗi và phân tích latency |
| Correlation | `request_id`/`correlation_id`, `trace_id`, `span_id` | Chuyển từ panel tổng quan sang sự kiện/trace |
| Messaging | `topic`, `partition`, `offset`, `consumer_group` | Khi có Kafka, truy được record và nơi xử lý |
| Độ tin cậy | `sampling_policy`, `log_source` khi có | Giải thích sự khác nhau giữa log count và traffic thực |

Trường thời gian nên có timezone rõ; thời điểm phát sinh (`Timestamp`) có thể khác thời điểm collector nhìn thấy (`ObservedTimestamp`). Trong mô hình OpenTelemetry Logs Data Model còn có `SeverityText`/`SeverityNumber`, `Body`, `Resource`, `Attributes`, `TraceId`, `SpanId` và `EventName`. Không phải mọi Logback layout tự sinh toàn bộ các field này; cần encoder/OTel integration và schema mapping thật.

### 4.2. Tên và kiểu phải nhất quán

Tránh khi service A dùng `duration=120` nghĩa là milliseconds nhưng service B dùng `duration=120` nghĩa là microseconds. Một dashboard cộng/so sánh hai nguồn này sẽ sai dù query chạy hợp lệ.

Đề xuất:
- Ghi rõ `duration_ms` hoặc unit tương đương.
- `status` là mã HTTP dạng số; `error_type` thuộc enum hữu hạn.
- `route` là template (`/orders/{id}`), không phải path có ID thật.
- `event` ổn định, ví dụ `http_request`, `payment_failed`; không phụ thuộc một câu message đã được dịch/localize.
- `service`, `environment` dùng tên nhất quán; không ghi `prod` ở service A và `production` ở service B nếu muốn cùng dashboard.
- Tránh đổi tên key trong lúc rollout mà không hỗ trợ dashboard/query tương thích.
- Khi schema thay đổi, có version hoặc kế hoạch chuyển đổi; test JSON/logfmt đầu cuối.

**Structured logging không tự bảo đảm an toàn.** Nếu field `authorization` chứa Bearer token, nó vẫn bị lưu trong JSON. Quy tắc tối thiểu hóa dữ liệu phải được thực hiện từ nguồn.

## 5. Loki labels so với field trong nội dung log

Với **Grafana Loki**, cần phân biệt:
- **Stream labels (indexed labels):** metadata dùng để định vị stream, như `app="orders-api"`, `env="prod"` hoặc `namespace="backend"`. Nên là tập giá trị có số lượng được kiểm soát.
- **Parsed fields:** trường được tách khi truy vấn bằng `| json` hoặc `| logfmt`. Hữu ích cho `status`, `route`, `error_type`, `duration_ms`.
- **Structured metadata:** thông tin đi kèm log line, không nhất thiết được index như stream label; tùy pipeline/phiên bản, có thể dùng cho trường cần tìm mà không tạo stream quá nhiều.

Một cách chia hợp lý:

| Field | Thường chọn |
| --- | --- |
| `app`/`service` | Stream label khi tập service ổn định |
| `env`/`namespace` | Stream label |
| `cluster`/`region` | Có thể là stream label nếu cardinality hợp lý |
| `route` | Parsed field; đôi khi label nếu tập route được kiểm soát và đã đánh giá chi phí |
| `status`/`error_type` | Parsed field; có thể aggregate ở query time |
| `duration_ms` | Numeric field để `unwrap` |
| `request_id`/`correlation_id` | Giữ trong event/structured metadata, **không dùng làm indexed label cho mỗi request** |
| `trace_id`/`span_id` | Event/metadata để drill-down, tránh indexed label có nhiều giá trị |
| `user_id`, raw URL, raw payload | Không ghi mặc định; chắc chắn không dùng làm label tùy ý |

**High cardinality**: nếu mỗi request có một giá trị label khác, Loki có thể tạo rất nhiều stream, tăng chi phí index, memory, write/query latency và làm dashboard chậm. Với Prometheus/metrics, dùng `request_id` làm label cũng gây bùng nổ time series.

Mặt khác, chỉ chọn `{app="orders-api"}` quá rộng có thể quét dữ liệu rất lớn. Hãy bổ sung những **label ổn định** như `env`, `namespace` và time range thích hợp trước khi parse/filter.

### 5.1. Giá trị app/env trong ví dụ đến từ đâu?

Trong các truy vấn dưới đây, selector:

```logql
{app="orders-api", env="prod"}
```

giả định **pipeline ingest đã gắn** stream labels `app` và `env`. Nếu ứng dụng chỉ in chuỗi `event=http_request ...` ra stdout mà collector không gắn các label này, query sẽ **không match**. Trong hệ thống dùng resource attribute `service.name` của OpenTelemetry, cần mapping theo cách exporter/collector/storage thật đang dùng. Đừng suy tên label từ một ví dụ trong tài liệu.

## 6. Ví dụ LogQL để làm panel dashboard

Các ví dụ sau giả định Loki nhận các dòng **logfmt** như:

```text
event=http_request route=/orders/{id} status=200 duration_ms=12 correlation_id=req_01
event=http_request route=/orders/{id} status=503 duration_ms=75 correlation_id=req_06
```

và collector đã gắn stream labels `app="orders-api"` và `env="prod"`. Query sẽ khác nếu log lưu JSON, nếu key được đổi tên hoặc giá trị chỉ nằm trong structured metadata.

### 6.1. Tìm log gần đây trong Explore

```logql
{app="orders-api", env="prod"}
  | logfmt
  | event="http_request"
```

- Selector giới hạn stream dựa vào label.
- `| logfmt` parse field có dạng `key=value`.
- `| event="http_request"` lọc event sau parsing.
- Chọn time range ngắn (ví dụ 15 phút) và kiểm tra timestamp/label ở một log line thực tế.

Với JSON:

```logql
{app="orders-api", env="prod"}
  | json
  | event="http_request"
```

**Không dùng `| json` với logfmt và ngược lại** rồi tưởng sự kiện đã bị mất; hãy xác minh format thực được ingest trước.

### 6.2. Số event HTTP trong 5 phút

```logql
sum(
  count_over_time(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request" [5m]
  )
)
```

`count_over_time` đếm **số log lines khớp** trong cửa sổ 5 phút, không tự động bằng số request thật nếu logging có sampling/drop, hai layer ghi trùng hoặc không log một số status. Dùng panel “HTTP access log events / 5m” thay vì gắn nhãn “số request chính xác” khi không có cam kết một-event-per-request.

### 6.3. Event rate theo giây (từ log)

```logql
sum(
  rate(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request" [5m]
  )
)
```

`rate` ước tính tốc độ **log event/giây**, không phải chỉ số request/giây đáng tin tuyệt đối nếu success log được sample. Với dịch vụ production, thường nên đối chiếu metric request counter chính thức.

### 6.4. Lỗi 5xx theo route

```logql
sum by (route) (
  count_over_time(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request"
      | status=~"5.." [5m]
  )
)
```

`status=~"5.."` so khớp các mã 500–599 đã parse thành text. Đây là **số event 5xx trong 5 phút**, không phải error rate. Nếu route trong log là raw path chứa ID, số series có thể rất lớn; ưu tiên route template.

### 6.5. Tỷ lệ lỗi 5xx ước tính từ log

```logql
100 *
sum(
  rate(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request"
      | status=~"5.." [5m]
  )
)
/
sum(
  rate(
    {app="orders-api", env="prod"}
      | logfmt
      | event="http_request" [5m]
  )
)
```

Giải thích: tử số là tốc độ 5xx events/giây; mẫu số là tốc độ toàn bộ HTTP events/giây; nhân 100 ra phần trăm. Đây là tỷ lệ theo **log events**. Kết quả có thể sai nếu các level được lọc khác nhau, success logs sampling, collector drop hoặc hai tuyến log ghi trùng.

**No data không đồng nghĩa 0% lỗi.** Khi mẫu số bằng 0 hoặc query không tìm được log, Grafana/Loki có thể trả no data/NaN. Với alerting cần thiết kế rõ cách xử lý “không có traffic” và “không có telemetry”, kiểm tra ví dụ/phiên bản LogQL thực; đừng tự thay mọi no data thành một trạng thái khỏe mạnh.

### 6.6. Latency p95 ước tính từ event duration

```logql
quantile_over_time(
  0.95,
  {app="orders-api", env="prod"}
    | logfmt
    | event="http_request"
    | unwrap duration_ms
    | __error__="" [5m]
) by (route)
```

- `unwrap duration_ms` dùng giá trị numeric của field được parse.
- `__error__=""` loại những dòng có lỗi parse/chuyển kiểu trong pipeline này.
- Kết quả nhóm theo `route`, khi Loki và query được cấu hình phù hợp.

**Quan trọng:** đây là p95 **của các log events còn tồn tại**. Nếu log sampling không đồng đều hoặc queue mất event, percentile không đại diện đầy đủ traffic. Với SLO latency, nên dùng metrics histogram được instrument ở điểm xử lý phù hợp, kiểm tra aggregation across replicas.

### 6.7. Lỗi nghiệp vụ cụ thể

Giả sử schema có `event=payment_failed` và `error_type=UPSTREAM_TIMEOUT`:

```logql
{app="orders-api", env="prod"}
  | logfmt
  | event="payment_failed"
  | error_type="UPSTREAM_TIMEOUT"
```

Đây là truy vấn **mẫu** cho ứng dụng có loại event tương ứng, không phải mặc định chương trình Java ở mục 8 tạo event payment. Khi chuyển từ một panel vào Explore, nên giữ lại time range, app/env/namespace và error type để việc drill-down không bắn truy vấn toàn hệ thống.

### 6.8. Nếu sử dụng biến dashboard

Grafana có template variables, ví dụ `$app` hoặc `$env`. Với biến chọn **một** giá trị:

```logql
{app="$app", env="$env"} | logfmt | event="http_request"
```

Nếu bật Multi-value/Include All, Grafana thường kết hợp thành regex; dùng operator phù hợp, ví dụ:

```logql
{app=~"$app", env=~"$env"} | logfmt | event="http_request"
```

Đặt default và scope đủ hẹp, đặc biệt với hệ thống multi-tenant. Biến dashboard **không thay thế RBAC/tenant isolation**; người dùng không được xem dữ liệu không được cấp quyền dù nhập thủ công giá trị khác.

## 7. Những panel nên có trên dashboard dịch vụ

Một dashboard tốt không nhất thiết có thật nhiều panel. Hãy sắp theo câu hỏi vận hành:

| Vị trí/panel | Dữ liệu gợi ý | Hành động khi bất thường |
| --- | --- | --- |
| Header: service, env, time range, version | Labels/variables và deployment annotations | Xác nhận đang xem đúng môi trường |
| Request rate | Metrics request counter hoặc LogQL event rate | Có tụt traffic hoặc spike không? |
| 5xx error rate | Metrics/LogQL tỷ lệ lỗi | Lỗi tăng ở route nào? |
| Latency p50/p95/p99 | Histogram metrics; log duration chỉ khi phù hợp | Request chậm hay chỉ backend chậm? |
| Errors by route/error type | Grouped counts theo key ổn định | Mở Explore với route/error type cụ thể |
| Recent ERROR/WARN logs | Log table có link tới trace/request | Xem lỗi chi tiết và stack trace an toàn |
| Service/dependency panels | CPU, heap, GC, DB pool, queue, dependency latency | Phân biệt lỗi app với saturation |
| Pipeline health | dropped logs, collector queue, ingestion latency/no data | Có đang mất dữ liệu quan sát không? |
| Deploy annotations | Thời điểm release/config change | Đối chiếu sự cố với thay đổi |
| Runbook/owner link | Tài liệu vận hành và escalation | Giảm thời gian xử lý |

**Điểm quan trọng:** tốc độ request và latency từ log có thể là góc nhìn hữu ích, nhưng nếu yêu cầu SLO/SLA cao, ưu tiên metrics được instrument với định nghĩa rõ và dùng log để điều tra nguyên nhân.

### 7.1. Thiết kế panel dễ đọc

- Ghi **đơn vị** và time window: `5xx events/5m` khác `5xx rate (%)`.
- Dùng panel title đủ rõ: “HTTP 5xx (log event count, 5m)” tốt hơn “Errors”.
- Giữ cùng time range và timezone cho panel cần đối chiếu; phân biệt event timestamp và ingestion timestamp.
- Giới hạn số series hiển thị; dùng Top N khi nhiều route/error type.
- Đừng biểu diễn cùng một giá trị dưới ba chart nếu không thêm góc nhìn mới.
- Dùng threshold dựa vào SLO/chính sách, không chọn màu chỉ vì “trông đẹp”.
- Chú thích khi có sampling hoặc data gaps.
- Thêm link từ panel tổng quan sang query logs, trace và runbook liên quan.

### 7.2. Drill-down từ mức tổng quan đến record

Một chuỗi thao tác thực tế:

```text
Dashboard: 5xx tăng ở orders-api / prod
  |
  v
Chọn route /orders/{id} và mốc 10:05-10:15
  |
  v
Explore: event=http_request, status=503
  |
  v
Mở event, lấy correlation_id hoặc trace_id hợp lệ
  |
  v
Tìm application error log, trace, DB query, upstream timeout
  |
  v
So deployment_version và thay đổi cấu hình
```

Đừng lưu raw token, password hoặc nội dung request cá nhân vào dashboard link. Link/derived field cho trace nên được cấu hình đúng pattern, nguồn và quyền truy cập. Nếu muốn liên kết OpenTelemetry trace, **W3C TraceId chuẩn là 16 byte (thường hiển thị 32 ký tự hex)**; một `correlation_id` ứng dụng như `req_01` trong demo bên dưới **không phải** trace ID chuẩn.

## 8. Java 17+ chạy độc lập: tạo log phục vụ dashboard và kiểm tra tổng hợp

Ví dụ dưới đây **không chạy Loki/Grafana**, mà minh họa trách nhiệm của **ứng dụng Java**: phát event với schema hữu hạn, giữ route template, không ghi authorization, sau đó dùng handler in-memory để kiểm tra dữ liệu và tính tổng hợp đơn giản.

Dữ liệu mô phỏng gồm sáu HTTP requests với status và durations:

| Route | Status | Duration (ms) |
| --- | --- | --- |
| `/orders/{id}` | 200 | 12 |
| `/orders/{id}` | 200 | 18 |
| `/orders` | 201 | 22 |
| `/orders/{id}` | 500 | 35 |
| `/health` | 200 | 40 |
| `/orders/{id}` | 503 | 75 |

Tạo file **`LogDashboardDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogDashboardDemo {
    enum Route {
        ORDER("/orders/{id}"),
        CREATE("/orders"),
        HEALTH("/health");

        final String value;

        Route(String value) {
            this.value = value;
        }
    }

    // authorization có mặt trong input để test rằng nó KHÔNG được log.
    record RequestEvent(
            Route route,
            int status,
            long durationMs,
            String correlationId,
            String authorization) {}

    static String logLine(RequestEvent e) {
        if (e.route() == null
                || e.status() < 100 || e.status() > 599
                || e.durationMs() < 0) {
            throw new IllegalArgumentException("Invalid event");
        }

        String id = e.correlationId() != null
                && e.correlationId()
                    .matches("[A-Za-z0-9_-]{1,32}")
                ? e.correlationId() : "invalid";

        // Chỉ các field trong allowlist; không dùng e.authorization().
        return "event=http_request route=" + e.route().value
                + " status=" + e.status()
                + " duration_ms=" + e.durationMs()
                + " correlation_id=" + id;
    }

    static final class Capture extends Handler {
        final List<String> lines = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                lines.add(record.getMessage());
            }
        }

        @Override public void flush() {}
        @Override public void close() {}

        List<String> snapshot() {
            return List.copyOf(lines);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        List<RequestEvent> events = List.of(
            new RequestEvent(Route.ORDER, 200, 12,
                    "req_01", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.ORDER, 200, 18,
                    "req_02", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.CREATE, 201, 22,
                    "req_03", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.ORDER, 500, 35,
                    "req_04", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.HEALTH, 200, 40,
                    "req_05", "Bearer FAKE_SECRET"),
            new RequestEvent(Route.ORDER, 503, 75,
                    "req_06", "Bearer FAKE_SECRET")
        );

        try {
            events.forEach(e -> logger.info(logLine(e)));
            List<String> saved = capture.snapshot();

            if (saved.size() != events.size()
                    || saved.stream().anyMatch(x ->
                        x.contains("FAKE_SECRET")
                        || x.contains("Authorization"))) {
                throw new AssertionError("Unsafe log");
            }

            // Kiểm tra CR/LF trong correlation_id bị từ chối.
            if (!logLine(new RequestEvent(
                    Route.ORDER, 200, 1,
                    "bad\nrequest", "secret"))
                    .endsWith("correlation_id=invalid")) {
                throw new AssertionError("Unsafe ID");
            }

            long errors = events.stream()
                    .filter(e -> e.status() >= 500)
                    .count();

            List<Long> times = events.stream()
                    .map(RequestEvent::durationMs)
                    .sorted()
                    .toList();

            // Nearest-rank cho bộ dữ liệu nhỏ minh họa.
            long p95 = times.get(
                    (int) Math.ceil(0.95 * times.size()) - 1);

            System.out.println("events=" + saved.size());
            System.out.println("errors_5xx=" + errors);
            System.out.printf(Locale.ROOT,
                    "error_rate_percent=%.1f%n",
                    100.0 * errors / events.size());
            System.out.println(
                    "p95_nearest_rank_ms=" + p95);
            System.out.println(
                    "sensitive_payload_logged=false");
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac LogDashboardDemo.java
java LogDashboardDemo
```

**Standard output cố định:**

```text
events=6
errors_5xx=2
error_rate_percent=33.3
p95_nearest_rank_ms=75
sensitive_payload_logged=false
```

### 8.1. Diễn giải ví dụ

- Sáu lời gọi `logger.info(...)` được handler cục bộ thu bằng `LogRecord`; logger đặt INFO, handler ALL. Chương trình **không in từng log line** ra stdout, chỉ in bản tổng hợp.
- Có hai status `500`/`503` trong sáu event. Tỷ lệ tính trên mẫu nhỏ bằng `2/6 × 100 ≈ 33,3%`.
- Mảng durations tăng dần là `12,18,22,35,40,75`. Quy tắc **nearest-rank** chọn phần tử thứ `ceil(0.95 × 6)=6`, nên p95 minh họa bằng `75 ms`.
- Hàm `logLine` chỉ dùng route enum cố định, status, duration và correlation ID đã validate. Trường `authorization` chứa chuỗi giả nhưng **không được đưa vào message**.
- Khi `correlationId` chứa newline, nó được thay thành `invalid`, giúp tránh phá cấu trúc logfmt bởi input không tin cậy.
- Logger riêng dùng `getAnonymousLogger()` và `setUseParentHandlers(false)` tránh ảnh hưởng root logger; `finally` tháo handler.

**Giới hạn rất quan trọng:** thuật toán nearest-rank trong demo **không hứa cho cùng kết quả** với hàm quantile của Grafana/LogQL, histogram hoặc khi dữ liệu đã được aggregate. Với production latency SLO, sử dụng phép đo, loại histogram và phép tổng hợp đúng contract thay vì tái sử dụng mã test nhỏ này.

Chương trình cũng **không thiết lập** stream labels `app`/`env`, collector, auth hay Loki. Để sử dụng các LogQL query ở mục 6, pipeline thật phải vận chuyển các dòng logfmt và gắn nhãn môi trường/service đúng cách.

### 8.2. Khi đưa vào ứng dụng thật

- Chọn logger/backend (JUL, SLF4J+Logback, Log4j 2) theo hệ thống hiện có.
- Định nghĩa schema event và unit; dùng JSON encoder/logfmt encoder đáng tin cậy, **không ghép raw user input** bằng nối chuỗi như một serializer tổng quát.
- Gắn service/environment/deployment metadata bằng cấu hình deploy/collector.
- Với HTTP server thật, đo duration tại điểm bắt đầu/kết thúc phù hợp; dùng `System.nanoTime()` tính khoảng thời gian, không dùng wall clock cho latency.
- Với async request, đo tại completion callback thay vì chỉ lúc handler trả về.
- Với error, giữ exception/stack trace ở nơi phù hợp nhưng không in credential, query string hoặc DTO nhạy cảm.
- Thêm trace context bằng integration OpenTelemetry đúng chuẩn; không đặt một chuỗi correlation ID tự chế vào trường `TraceId`.
- Kiểm thử ở logger, encoder, collector và dashboard bằng canary giả trước khi rollout.

## 9. Đưa Logback/SLF4J hoặc JUL event lên pipeline

SLF4J là **API facade**; Logback/Log4j 2 là backend có thể quyết định cách ghi console/file/OTLP. Câu lệnh:

```java
// Đoạn tích hợp trong service có SLF4J Logger LOG.
LOG.info("event=http_request route={} status={} duration_ms={}",
         routeTemplate, statusCode, durationMs);
```

dễ đọc, nhưng chỉ tạo một message theo formatter/backend đang chạy. Nó **không** tự sinh JSON, resource attributes hay Loki label. Cần cấu hình encoder và collector tương thích.

Một mô hình phổ biến cho Java chạy container:
1. Application viết log line vào **stdout/stderr** theo format đã chuẩn hóa.
2. Runtime/kubelet/agent thu stdout.
3. Agent/collector parse, thêm resource metadata, xử lý theo policy và gửi đến Loki hoặc backend khác.
4. Grafana/Loki truy vấn theo stream labels ổn định; event fields parse ở query time.

Nếu ứng dụng dùng **file appender**, cần rotation, quyền file, backup, tránh shipper đọc trùng hoặc mất file sau rollover. Nếu dùng **OTLP/OTel logs**, xem exporter/collector, batching/retry, resource mapping và semantic conventions đúng phiên bản. Không tự suy rằng cài OpenTelemetry Java agent sẽ luôn thu mọi file console theo đúng schema mong muốn.

### 9.1. Chọn mức log và khối lượng

Dịch vụ có 10.000 request/giây, log một event INFO/request có thể tạo hàng trăm triệu event mỗi ngày trước khi tính thêm DEBUG/WARN. Giữ:
- Metrics/histograms cho traffic và latency ở độ phân giải vận hành.
- Logs có context cho ERROR/WARN, sự kiện audit và một phần INFO theo policy.
- Sampling success logs khi phù hợp, nhưng phải ghi chú rõ dashboard đếm **sampled events**, không phải request thật.
- Bảo toàn lỗi nghiêm trọng/audit theo yêu cầu; không drop chỉ để chart trông mượt.
- Theo dõi queue, drop count, collector backpressure và ingestion lag.

**Cân bằng chi phí và khả năng điều tra** không chỉ là hạ level từ DEBUG xuống WARN. Cần event code ổn định, trace links, sampling strategy và retention đúng loại dữ liệu.

## 10. Sự thật về alert dựa trên log

Một dashboard chỉ cho thấy vấn đề khi ai đó đang nhìn. Alert phải có điều kiện phù hợp và dẫn người nhận đến hành động.

Ví dụ alert log-based có thể phát hiện `payment_failed`/`UPSTREAM_TIMEOUT` tăng đột biến theo 5 phút. Nhưng cần cân nhắc:
- Log có đủ đại diện không? Có sampling/dropped events không?
- Mẫu số hợp lý là gì? 20 lỗi/20 request khác 20 lỗi/1 triệu request.
- Có event được phát **một lần** cho mỗi failure không, hay cùng lỗi bị retry và log nhiều lần?
- Đã tách 5xx do ingress với 5xx do ứng dụng chưa?
- Alert đi kèm route, service, env, thời gian, query điều tra và runbook không?
- Kịch bản **No Data**, query failure, collector outage và các khoảng trống telemetry được xử lý riêng chưa?

Khi có metrics instrument tốt, dùng **metrics-based SLO/error budget alerts** cho tín hiệu chính, còn logs để phân tích “lỗi cụ thể nào”. Log-based alert phù hợp cho event hiếm và rõ loại như vi phạm security policy, một lỗi xử lý nghiệp vụ cụ thể hoặc một exception type cần chú ý.

### 10.1. Giảm false positive

- Chọn window/threshold theo traffic, không chỉ một spike vài giây.
- Dùng tỷ lệ + số mẫu tối thiểu khi cần tránh báo động khi gần như không có traffic.
- Phân biệt **severity** với tác động thực tế đến người dùng.
- Group/dedupe alerts theo service/env/error type; tránh gửi hàng trăm alert cùng sự cố.
- Có silence/maintenance window có kiểm soát.
- Sau incident, cập nhật panel/alert/query dựa vào bằng chứng chứ không chỉ tăng threshold.

## 11. Data quality: dashboard có thể sai như thế nào?

### 11.1. Mất hoặc trễ log

Log pipeline có thể:
- Bị logger level/filter loại event trước khi tạo.
- Queue async đầy và drop/chặn producer.
- Mất buffered events khi shutdown/crash.
- Agent chưa kịp đọc file/stdout hoặc gặp lỗi permission.
- Collector retry/batch quá lâu, bị rate-limit/quota.
- Backend ingest chậm, sai timestamp hoặc retention xóa dữ liệu.
- Tenant/RBAC khiến người xem chỉ thấy một phần logs.

Nếu dashboard đột ngột xuống 0, có thể là traffic thực sự xuống 0 **hoặc** log ingestion hỏng. Cần dashboard/metric theo dõi `log_pipeline_dropped`, `collector_queue_size`, `last_successful_export` hoặc chỉ số tương đương của công cụ đang dùng. Tên metric cụ thể thay đổi theo sản phẩm và phiên bản; không giả định những tên ví dụ này đã có sẵn.

### 11.2. Timestamp và thứ tự

Một event có thể có:
- **Event timestamp:** thời điểm code tạo log.
- **Observed/ingest timestamp:** thời điểm collector/backend thấy event.
- **Dashboard evaluation time:** lúc query chạy.

Đồng hồ giữa nodes có thể lệch, event có thể đến muộn hoặc không theo thứ tự xuất hiện trong Explore. Khi điều tra, kiểm tra timezone, NTP, lag, source timestamp, sort order và retention. Không suy rằng log đứng trước trong UI luôn xảy ra trước trên tất cả service.

### 11.3. Trùng dữ liệu và sampling

Một request có thể tạo access log ở gateway và application, hoặc agent đọc lại file sau rotate/restart. Dashboard tổng hợp hai nguồn sẽ đếm hai event. Ngược lại, sampling 1% success logs nhưng giữ 100% errors làm error ratio tính từ log phóng đại nghiêm trọng.

Tài liệu dashboard phải ghi:
- Nguồn chính và layer (`gateway` hay `application`).
- Phạm vi event: mỗi request, mỗi retry hay mỗi operation.
- Sampling/drop policy.
- Unit và time range.
- Cách xử lý no data.
- Điều kiện mà kết quả không dùng để tính SLO.

## 12. Privacy, bảo mật và phân quyền trên dashboard

**Log có thể là dữ liệu nhạy cảm.** Dashboard làm dữ liệu dễ xem hơn và có thể tăng khả năng bị chia sẻ rộng.

Các biện pháp:
- Không log password, token, Authorization/Cookie, secret hoặc toàn bộ request/response body.
- Ưu tiên route template, error code, request ID ngẫu nhiên và field allowlist.
- Không mặc định log IP, email, user ID hay tenant ID nếu không có purpose/retention rõ.
- Kiểm tra stack trace, MDC/ThreadContext, header và formatter có tự ghi dữ liệu riêng tư không.
- Sử dụng encoder escape đúng; với logfmt, kiểm soát dấu cách/quote/newline trong value từ nguồn không tin cậy.
- Quyền xem Explore/query/export phải theo need-to-know, phân tách tenant/environment ở tầng data source/storage.
- Kiểm soát chia sẻ link dashboard, snapshot, ảnh, export CSV/JSON và file đính kèm sự cố.
- Thiết lập retention, backup, encryption và audit truy cập theo chính sách; không dùng dashboard link như lớp bảo vệ dữ liệu.
- Với trường hợp phải điều tra dữ liệu nhạy cảm, sử dụng kênh được phê duyệt, có kiểm toán và thời hạn phù hợp.

**Cẩn thận với template variables:** cho người dùng sửa `$service` hoặc `$tenant` không được coi là cơ chế authorization. Hệ thống truy vấn/backend phải từ chối xem dữ liệu không thuộc phạm vi quyền, bất kể URL hay dashboard variable.

### 12.1. Không nhầm correlation ID với trace ID

Một string như `req_01` trong demo chỉ là **correlation_id của ứng dụng**. OpenTelemetry/W3C trace ID có format, entropy và propagation riêng. Chỉ hiển thị link “View trace” khi field thực sự là trace ID hợp lệ và trace backend có dữ liệu tương ứng. Đừng để truy vấn nhảy từ service A sang service B bằng một ID do client tùy ý gửi mà không kiểm tra.

## 13. Tối ưu chi phí, hiệu năng và tốc độ truy vấn

Chi phí logs đi qua nhiều bước:
- CPU và allocation để dựng/format message.
- I/O/stdout và log rotation.
- Agent/collector CPU, memory, batch, retry, egress.
- Backend storage, index, retention và query scan.
- Dashboard refresh, variables và queries độ rộng lớn.

Tối ưu cân bằng:
1. Đặt **level phù hợp** theo environment và module. Không bật DEBUG toàn hệ thống khi không cần.
2. Dùng parameterized/lazy logging để tránh tạo message đắt khi level tắt.
3. Định nghĩa event quan trọng để **không cần dump payload**.
4. Tạo stream labels ít cardinality và selector hẹp.
5. Hạn chế `request_id`/`trace_id` trong index labels.
6. Chọn query windows phù hợp; tránh dashboard refresh quá ngắn và query trên toàn bộ log history.
7. Dùng metrics cho các tổng hợp liên tục khối lượng lớn; dùng logs cho drill-down.
8. Thiết kế retention/tiering theo giá trị dữ liệu và yêu cầu tuân thủ.
9. Giám sát ingestion errors, queue/drop, query latency và cost per service.

**Ví dụ:** một panel top routes nhóm theo raw path `/orders/12345` thay vì route template `/orders/{id}` sẽ tạo nhiều nhóm và mất ý nghĩa. Sửa từ schema tại nguồn hiệu quả hơn cố viết regex xử lý mọi biến thể path ở lúc query.

## 14. Kiểm thử log-to-dashboard theo các tầng

### 14.1. Unit test Java

Kiểm tra hàm dựng event:
- `event` đúng tên, `route` theo enum/allowlist, status 100–599, duration không âm.
- Không có raw Authorization/password/token/query string trong message.
- ID quá dài/chứa CRLF bị chuẩn hóa/từ chối.
- Trường unit nhất quán, không đổi ms sang µs mà không đổi key.
- Level cho error/normal events rõ theo contract.

Demo mục 8 đã thực hiện test bằng `AssertionError` và handler cục bộ, không cần dependencies ngoài JDK.

### 14.2. Test logging backend

Với Logback, dùng `ListAppender<ILoggingEvent>` hoặc appender test; với JUL dùng `Handler`; với Log4j 2 dùng appender/test context phù hợp. Kiểm tra:
- Level/filter có thực sự để event cần thiết đi qua?
- JSON/logfmt encoder xuất đúng fields và escaping?
- `MDC` có chứa dữ liệu ngoài allowlist hay bị rò giữa request?
- Exception có stack trace nhưng không lộ secret?
- Appender/async queue có ảnh hưởng đến việc test đọc event không?

Chờ event theo tín hiệu/timeout nếu async; không dùng `Thread.sleep` cố định rồi giả định đã flush. Hoàn nguyên logger level, appender, context và resources sau test để tránh test song song nhiễm nhau.

### 14.3. Integration test pipeline

Trong môi trường thử nghiệm:
1. Gửi HTTP request với dữ liệu giả và canary `FAKE_SECRET`.
2. Đợi app ghi event, xác minh schema/trace/correlation fields.
3. Xác minh agent/collector nhận đúng, có metadata `app`/`env`, không đổi đơn vị thời gian.
4. Truy vấn một log thật từ Loki, dùng `| logfmt`/`| json` đúng format; thử các LogQL query ở mục 6.
5. Kiểm tra dashboard variables, time range, status filter và route grouping.
6. Gây một 5xx xác định, xem panel lỗi tăng, link Explore đưa đến record.
7. Làm collector mất kết nối trong môi trường test, quan sát queue, retry, drop hoặc no data.
8. Xác minh canary không xuất hiện trong bất kỳ sink/export/backup nào.
9. Kiểm tra quyền và retention của backend; test user trái quyền không thể xem log.
10. Đo chi phí/latency của ứng dụng và dashboard khi tăng traffic.

Không dùng dữ liệu production thật để tạo canary. Các kiểm tra trực tiếp Grafana/Loki cần hệ thống đã triển khai; ví dụ Java độc lập **không thể thay thế** những integration tests này.

## 15. Troubleshooting: panel trống, số liệu sai hoặc chậm

| Hiện tượng | Nguyên nhân phổ biến | Cách kiểm tra |
| --- | --- | --- |
| Panel “No data” nhưng app đang chạy | Sai label `app`/`env`, time range, chưa ingest, filter sai | Xem raw log trong Explore và labels thật |
| Query `| json` không trả field | Source đang là logfmt/text | Kiểm tra mẫu log và chọn parser phù hợp |
| 5xx count sai | Log nhiều layer/trùng hoặc sampling success | Phân biệt layer, dedupe/metrics |
| Duration lớn hơn 1000 lần | Nhầm milliseconds/microseconds | Xem field unit và nguồn đo |
| Query p95 lỗi parse | `duration_ms` thiếu/không phải số | `unwrap` đúng field và lọc `__error__` |
| Route groups quá nhiều | Raw path có ID hoặc query | Dùng route template từ ứng dụng |
| Query rất chậm | Selector rộng, time range lớn, cardinality cao | Chọn label ổn định, giảm scan |
| Link trace không mở được | ID không đúng chuẩn hoặc trace bị sampling/xóa | Kiểm tra trace ID, sampling, retention, backend |
| Dashboard giảm về 0 đột ngột | Traffic giảm hoặc pipeline drop/collector lỗi | So metrics, ingestion health và log delivery |
| Alert không kích hoạt | “No data” không phải zero, query trả NaN hoặc window khác | Test query/rule ở time range thực |
| Lỗi lại nhiều hơn request | Retry, đa tầng, nhiều log per request | Định nghĩa event/denominator, dedupe |
| Có secret trong dashboard | Field nguồn/formatter/collector ghi quá rộng | Chặn tại source, xử lý incident và access |
| Chỉ một người không xem được data | RBAC/tenant/data source permissions | Kiểm tra policy, không nới toàn quyền |
| Chart không khớp metrics | Sampling, unit, time bounds, clock skew, labels | So cùng source/scope và định nghĩa |

**Thứ tự điều tra:** xác định service/env/time range → xem một raw event thật → xem labels và parser → thử LogQL đơn giản → thêm filter/aggregation từng bước → đối chiếu metrics → kiểm tra collector/retention/RBAC. Không bắt đầu bằng một query toàn bộ storage hoặc bật DEBUG trên production để “tạo số liệu”.

## 16. Checklist thiết kế dashboard production

- [ ] Có mục tiêu vận hành rõ: triage lỗi, theo dõi SLO, phân tích dependency, security event...
- [ ] Chọn source chính cho RPS/error/latency, biết khi nào logs chỉ là sample.
- [ ] Mọi panel ghi rõ unit, window, environment, service và ý nghĩa dữ liệu.
- [ ] Schema log có `event`, `service`, `env`, level, timestamp và các field cần thiết.
- [ ] Labels ít cardinality; không index request/trace ID theo mỗi event.
- [ ] Có thể drill-down từ 5xx/latency sang log và trace nếu ID hợp lệ.
- [ ] Hiển thị deployment annotations hoặc điểm thay đổi để đối chiếu.
- [ ] Có panel/metric phản ánh ingestion lag, collector queue và log loss.
- [ ] Cảnh báo phân biệt “zero”, “no data”, lỗi query và sự cố logging pipeline.
- [ ] Không rò token/PII, không dùng dashboard variable làm authorization.
- [ ] Xác minh quyền xem/export, retention và backup theo chính sách.
- [ ] Có test schema/query/panel từ dữ liệu giả qua pipeline thật.
- [ ] Có runbook/owner, cách phản ứng khi alert và lịch review dashboard định kỳ.

## 17. Bài tập thực hành

1. Chạy `LogDashboardDemo`. Tự tính số events, 5xx, tỷ lệ lỗi và p95 nearest-rank; đối chiếu stdout.
2. Thêm một event `status=404`. Xác định vì sao nó không làm tăng `errors_5xx` dù có thể tăng traffic và phân tích 4xx.
3. Truyền correlation ID chứa newline hoặc quá dài. Xác minh chuỗi không xuất hiện trong log; test một input hợp lệ.
4. Đổi route từ template thành raw path chứa ID giả. Giải thích rủi ro cardinality/privacy và sửa bằng enum/route mapping.
5. Trong Loki test có stream labels hợp lệ, thử query log table và `count_over_time` 5 phút. Phân biệt count với rate.
6. Tạo panel 5xx by route, thêm một query total traffic rồi tính error rate. Xem cách no data/denominator 0 được xử lý.
7. Tạo histogram metric request duration bằng thư viện instrumentation phù hợp và so với log-derived p95 trong cùng workload. Giải thích sai khác do sampling/aggregation.
8. Gắn trace ID W3C hợp lệ vào request trong môi trường test, tạo derived link từ event sang trace. Dùng `req_01` tự chế và kiểm tra vì sao nó không phải trace ID.
9. Cố ý làm collector ngừng nhận trong test; xem log line ở app vẫn có nhưng dashboard mất dữ liệu thế nào.
10. Tạo dashboard variable `app` và `env`, kiểm tra trường hợp single-value và multi-value với query selector khác nhau.
11. Lập bảng retention/quyền xem cho DEBUG, ERROR, audit và dashboard export. Kiểm tra dữ liệu canary giả không đi vào hệ thống ngoài phạm vi.
12. Viết runbook 5xx tăng cho một service: từ metrics sang dashboard, Explore, trace, deployment annotation và cách xác nhận nguyên nhân.

## 18. Ghi nhớ

- **Log** là sự kiện chi tiết; **dashboard** là góc nhìn từ truy vấn; **observability** cần sự nhất quán và khả năng liên kết logs, metrics, traces.
- Thiết kế schema từ câu hỏi vận hành: event code, service/env, status, route template, duration/unit, correlation/trace ID khi có.
- Trong Loki, chọn **stream labels có cardinality thấp**, còn request ID/trace ID/duration và nhiều field event nên ở parsed fields hoặc structured metadata.
- `count_over_time` đếm log events; `rate` đo log events/giây; `unwrap` dùng field numeric để tính percentile. Không tự coi chúng là request metrics chuẩn khi pipeline có sampling, drop hoặc duplicate.
- Dùng metrics/histograms có độ tin cậy phù hợp cho SLO/alert quan trọng và logs để drill-down.
- Dashboard tốt có nguồn dữ liệu, time range, đơn vị, quyền truy cập, pipeline health, runbook và links điều tra.
- Kiểm tra no data, ẩn danh dữ liệu, log injection, label explosion, retention và phân quyền trước production.

### Tài liệu tham khảo chính thức

- OpenTelemetry — Logs Data Model (Timestamp, ObservedTimestamp, Resource, Attributes, TraceId, Severity): https://opentelemetry.io/docs/specs/otel/logs/data-model/
- OpenTelemetry — Java instrumentation và logging: https://opentelemetry.io/docs/languages/java/
- Grafana Loki — LogQL / query language: https://grafana.com/docs/loki/latest/query/
- Grafana — Loki query editor, metric queries: https://grafana.com/docs/grafana/latest/datasources/loki/query-editor/
- Grafana — Loki template variables: https://grafana.com/docs/grafana/latest/datasources/loki/template-variables/
- Grafana Loki — Label design và cardinality: https://grafana.com/docs/loki/latest/get-started/labels/
- Prometheus — Histograms and summaries: https://prometheus.io/docs/practices/histograms/
- Oracle JDK 17 — java.util.logging.Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
