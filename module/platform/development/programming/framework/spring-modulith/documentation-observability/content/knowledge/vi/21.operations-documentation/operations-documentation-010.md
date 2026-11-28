# Không xem telemetry schema là hợp đồng bất biến tuyệt đối

## 1. Vì sao telemetry schema cần được quản trị?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, telemetry giúp quan sát ranh giới và tương tác giữa các application module. Ví dụ, module ordering phát event OrderPlaced, module payment ghi nhận kết quả thanh toán, module notification gửi thông báo. Module-entry spans, event metrics, application metrics và logs cung cấp dữ liệu để dashboard và hệ thống cảnh báo theo dõi các luồng này.

Những dữ liệu đó được tiêu thụ bởi nhiều thành phần: Prometheus query metric name và labels; Grafana dashboard nhóm theo module; alert rules lọc status hoặc environment; tracing backend tìm span theo attributes; log pipeline parse JSON fields; data platform có thể lưu telemetry lâu dài để phân tích xu hướng. Vì vậy, tên metric, loại dữ liệu, đơn vị, labels, span attributes và log fields trở thành một **giao diện vận hành** giữa producer và consumer.

Giao diện này cần ổn định đủ để dashboard và alert không hỏng sau mỗi lần deploy, nhưng không thể bất biến tuyệt đối. Hệ thống phát triển: module được đổi tên, instrumentation được cải tiến, OpenTelemetry Semantic Conventions cập nhật, một label không còn hữu ích hoặc metric cũ được thay thế. Cố giữ mọi schema mãi mãi sẽ tích lũy tên gọi sai, dữ liệu dư thừa và cách đo không còn phù hợp.

Nguyên tắc đúng là **tiến hóa có kiểm soát**:

1. Xem telemetry schema như một interface có consumer và mức độ tương thích.
2. Phân loại thay đổi additive, behavior-changing và breaking.
3. Thông báo, version hóa hoặc duy trì tương thích khi cần.
4. Chuyển dashboard, alert, collector và data pipeline trước khi bỏ schema cũ.
5. Đo mức sử dụng và chỉ deprecate khi đã có bằng chứng.

Bài học thuộc chương **Tài liệu vận hành** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này hướng dẫn dùng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác khi ứng dụng Spring Boot vận hành qua module graph, Actuator, event metrics, tracing và context propagation.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện các thành phần của telemetry schema: metric, span, resource, log và event metadata.
- Phân biệt telemetry schema với domain event contract và API nghiệp vụ.
- Đánh giá thay đổi nào tương thích, thay đổi nào có thể phá dashboard hoặc alert.
- Thiết kế quy tắc đặt tên, units, labels, attributes và cardinality.
- Dùng OpenTelemetry Semantic Conventions và schema URL một cách có chủ đích.
- Lập kế hoạch migrate, dual-publish, deprecate và remove field.
- Quản trị dashboard, alert rules và collector như các consumer của schema.
- Kiểm thử schema trong CI và phát hiện drift trước khi deploy.

## 2. Telemetry schema gồm những gì?

Không chỉ metric name mới là schema. Mỗi tín hiệu có các thành phần riêng cần được ghi tài liệu.

| Tín hiệu | Thành phần schema | Ví dụ |
| --- | --- | --- |
| Metrics | Name, type, unit, description, temporality, labels/tags và semantics của value. | Counter số event đã publish; Timer latency xử lý listener. |
| Traces | Span name, kind, status, parent/link, attributes, events và resource attributes. | Module entry span có module identifier và invocation type. |
| Logs | Timestamp, severity, body, resource fields, trace/span correlation và structured attributes. | JSON log có service.name, traceId, event.name. |
| Resources | Service identity, deployment environment, version, instance và cloud/container metadata. | service.name=shop-service, service.version=2.4.0. |
| Event metrics | Event type, publishing module, outcome nếu có, tags tùy biến. | module.events.published theo module và event type. |

### 2.1. Metric schema

Một metric không chỉ là tên. Ví dụ metric latency có thể mang các ý nghĩa khác nhau:

| Thuộc tính | Ví dụ |
| --- | --- |
| Name | shop.module.listener.duration |
| Type | Timer / histogram |
| Unit | seconds |
| Description | Thời gian thực thi listener từ lúc bắt đầu đến lúc hoàn tất |
| Tags | module, event_type, outcome |
| Aggregation | count, sum, histogram buckets |

Nếu giữ nguyên tên nhưng đổi unit từ seconds sang milliseconds, query và alert có thể sai mà không có lỗi cú pháp. Nếu đổi Timer thành Gauge hoặc thay semantics từ processing duration sang queue delay, dashboard vẫn có thể hiển thị số nhưng diễn giải sai.

### 2.2. Trace schema

Trace schema gồm span names, attributes, status, events, links và resource attributes. Ví dụ:

~~~text
Span name: spring.modulith.module
Attributes:
  module.identifier = "payment"
  module.method = "authorize"
  module.invocation-type = "BEAN"
Status: ERROR
Resource:
  service.name = "shop-service"
  service.version = "2.4.0"
~~~

Span name và attribute key được dashboard, query và alert sử dụng. Đổi attribute key từ module.identifier sang module.name có thể làm saved query không tìm thấy span, dù ứng dụng vẫn export trace thành công.

### 2.3. Log schema

Log schema gồm field names và semantics:

~~~json
{
  "@timestamp": "2026-11-27T03:00:00.123Z",
  "severity": "ERROR",
  "service.name": "shop-service",
  "module.identifier": "payment",
  "event.name": "PaymentAuthorizationFailed",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
~~~

Đây là ví dụ minh họa, không phải một schema bắt buộc. Nếu log pipeline đang parse field trace_id, việc đổi thành traceId cần cập nhật parser, dashboard và correlation link.

## 3. Telemetry schema không phải domain event contract

Hai loại contract này có liên quan nhưng mục tiêu khác nhau:

| Đặc điểm | Domain event contract | Telemetry schema |
| --- | --- | --- |
| Mục đích | Truyền sự kiện nghiệp vụ giữa module hoặc service. | Quan sát, chẩn đoán, đo lường và cảnh báo. |
| Consumer | Event listener, integration adapter, hệ thống nghiệp vụ. | Dashboard, alert, collector, log/tracing backend, analytics. |
| Nội dung | Business facts cần để consumer thực hiện công việc. | Metadata, measurements và context phục vụ quan sát. |
| Compatibility | Có thể ảnh hưởng trực tiếp tới xử lý nghiệp vụ. | Có thể làm hỏng query, dashboard, alert hoặc phân tích lịch sử. |
| Chính sách thay đổi | Versioning và migration theo event contract. | Compatibility window, migration và deprecation theo consumer telemetry. |

Ví dụ, thêm field shippingAddress vào OrderPlaced là thay đổi domain event. Thêm span attribute module.identifier hoặc metric tag outcome là thay đổi telemetry schema. Không nên nhét trace ID, span ID hoặc mọi thuộc tính quan sát vào payload domain event chỉ để dashboard truy vấn thuận tiện.

Một event publication counter cũng không phải event payload. Metric module.events.published cho biết publication được instrument; payload OrderPlaced mang business facts. Đổi tên metric không nên buộc đổi event contract, và đổi event payload không nên âm thầm làm thay đổi semantics metric.

## 4. Nguyên tắc ổn định và tiến hóa

Telemetry schema nên tuân theo một số nguyên tắc:

1. **Ổn định semantics trước tên gọi:** cùng một metric name phải giữ ý nghĩa, unit và aggregation nhất quán.
2. **Additive trước destructive:** thêm field/attribute/tag thường an toàn hơn đổi hoặc xóa field đang được dùng.
3. **Không hứa bất biến vĩnh viễn:** ghi rõ phiên bản, chủ sở hữu và thời hạn hỗ trợ của schema.
4. **Consumer-aware:** kiểm tra dashboard, alert, SLO, data pipeline và truy vấn lịch sử trước khi đổi.
5. **Có thể quan sát việc migrate:** dual-publish hoặc phát metric đánh dấu phiên bản schema nếu cần.
6. **Không version hóa mọi thứ một cách máy móc:** chỉ tạo metric name version mới khi semantics hoặc compatibility thực sự yêu cầu.
7. **Giữ cardinality thấp:** không thêm identifier duy nhất thành metric label.
8. **Tuân thủ convention chung:** ưu tiên OpenTelemetry Semantic Conventions và naming convention của hệ thống.

Schema cần có tài liệu đủ để người khác biết field nào được đảm bảo, field nào tùy chọn, kiểu dữ liệu, unit, allowed values, cardinality và lifecycle.

## 5. Phân loại thay đổi theo mức độ tương thích

Không thể kết luận một thay đổi an toàn chỉ vì code compile hoặc exporter vẫn chạy. Hãy đánh giá theo producer và consumer.

| Loại thay đổi | Ví dụ | Rủi ro | Khuyến nghị |
| --- | --- | --- | --- |
| Additive | Thêm optional span attribute mới; thêm một label có miền giá trị nhỏ. | Thường thấp, nhưng có thể tăng cardinality hoặc làm query grouping thay đổi. | Có thể triển khai trực tiếp sau khi đánh giá chi phí và privacy. |
| Rename | Đổi module.identifier thành module.name; đổi metric name. | Query cũ không còn match. | Dual-publish hoặc migrate consumer trước khi remove field cũ. |
| Remove | Xóa label, attribute hoặc log field đang dùng. | Dashboard, alert và ETL có thể hỏng. | Deprecate, đo usage và có thời hạn chuyển đổi. |
| Semantic change | Cùng metric name nhưng đổi từ event published sang listener completed. | Dữ liệu lịch sử không còn so sánh được. | Dùng tên mới hoặc version mới; không âm thầm đổi semantics. |
| Type change | Counter thành Gauge; Timer thành DistributionSummary. | Query aggregation và đơn vị có thể sai. | Xem như breaking change; tạo metric mới và migrate. |
| Unit change | seconds thành milliseconds. | Ngưỡng alert và biểu đồ sai theo hệ số 1.000. | Đổi tên hoặc unit metadata theo convention; migrate query và alert. |
| Cardinality change | Thêm orderId/customerId làm tag. | Số time series tăng đột biến, chi phí và memory tăng. | Không đưa ID duy nhất vào metric labels. |
| Allowed-value change | outcome thêm giá trị PARTIAL hoặc đổi SUCCESS thành OK. | Dashboard filter cũ có thể bỏ sót dữ liệu. | Bổ sung giá trị và cập nhật consumer; ghi tài liệu enum. |

### 5.1. Additive không phải lúc nào cũng vô hại

Thêm một attribute vào span thường không phá query đang lọc các attribute cũ. Nhưng thêm một label metric có thể nhân số time series. Ví dụ metric đang có 5 module và 3 outcome có tối đa 15 tổ hợp; thêm label `region` với 20 giá trị có thể tăng lên 300 tổ hợp.

Thêm một giá trị enum cũng có thể phá dashboard nếu query dùng danh sách allowlist hoặc alert chỉ nhận `SUCCESS`/`ERROR`. Vì vậy, additive change vẫn cần đánh giá cardinality, filter và semantics.

### 5.2. Thay đổi semantics là breaking dù tên không đổi

Giả sử `shop.module.listener.duration` ban đầu đo thời gian từ lúc listener bắt đầu tới lúc hoàn tất. Một bản deploy đổi metric thành thời gian từ lúc event được publish tới lúc listener hoàn tất. Tên và unit vẫn giữ nguyên, nhưng metric mới bao gồm cả queue/commit delay.

Dashboard p95 sẽ thay đổi mạnh và alert latency có thể kích hoạt liên tục. Đây là breaking semantic change; nên tạo metric mới có tên/description phản ánh rõ queue delay hoặc processing duration.

## 6. Quy tắc đặt tên và metadata

### 6.1. Metric names

Metric name nên:

- Dùng tên ổn định, mô tả điều được đo.
- Có unit rõ ràng, ưu tiên đơn vị cơ sở như seconds, bytes.
- Phân biệt count, duration, size và state.
- Không nhúng environment, instance, module ID hoặc tenant vào metric name; dùng labels/resource attributes phù hợp.
- Không đổi type/semantics dưới cùng tên.

Ví dụ:

| Metric | Ý nghĩa | Type/unit |
| --- | --- | --- |
| `shop.module.invocations` | Số lần vào module được instrument. | Counter, count. |
| `shop.module.listener.duration` | Thời gian xử lý listener. | Timer, seconds. |
| `shop.event.processing.delay` | Độ trễ từ publication tới bắt đầu xử lý. | Timer/distribution, seconds. |
| `shop.event.publication.failures` | Số lần publication thất bại theo semantics đã định nghĩa. | Counter, count. |

Đây là tên custom minh họa. Với Micrometer, registry có thể chuyển tên sang convention riêng, ví dụ Prometheus dùng dấu underscore và suffix tương ứng. Luôn kiểm tra tên thực tế trên Actuator `/metrics` và `/prometheus`.

### 6.2. Labels/tags

Chọn tag mô tả nhóm hữu hạn:

~~~java
Counter.builder("shop.module.invocations")
    .description("Number of instrumented module invocations")
    .tag("module", moduleIdentifier)
    .tag("invocation_type", invocationType)
    .tag("outcome", outcome)
    .register(meterRegistry)
    .increment();
~~~

Ví dụ trên minh họa cách gắn tag có miền giá trị nhỏ. `moduleIdentifier`, `invocationType` và `outcome` phải được giới hạn bởi danh mục do ứng dụng quản lý.

Tránh các tag như:

- `trace_id`, `span_id`.
- `order_id`, `customer_id`, `email`.
- URL path chứa ID động hoặc query string.
- Exception message đầy đủ.
- SQL statement hoặc message payload.

Các giá trị này tạo cardinality cao hoặc có thể chứa dữ liệu nhạy cảm. Nếu cần điều tra một request, dùng trace/log correlation thay vì metric label.

### 6.3. Span attributes và OpenTelemetry Semantic Conventions

Với traces, ưu tiên semantic conventions đã được chuẩn hóa cho HTTP, database, messaging, deployment và service resources. Ví dụ `service.name`, `service.version`, `deployment.environment.name` là các resource attributes có ý nghĩa phổ biến trong OpenTelemetry.

Thuộc tính riêng của Spring Modulith như module identifier nên có namespace rõ và mô tả semantics. Không tự đổi tên convention chuẩn theo sở thích local vì các backend, dashboards hoặc instrumentation khác có thể phụ thuộc vào key chuẩn.

OpenTelemetry Semantic Conventions có thể phát triển theo version; một số convention trải qua giai đoạn migration hoặc đổi tên. Cần ghi nhận convention version/schema URL khi instrumentation hỗ trợ, và đọc migration guide thay vì giả định key sẽ bất biến mãi mãi.

### 6.4. Resource attributes khác span attributes

Resource mô tả entity tạo telemetry, chẳng hạn service, version, environment, host hoặc container. Span attributes mô tả một operation cụ thể, chẳng hạn module, method hoặc event type.

Không đặt `service.version` thành span attribute riêng cho từng span nếu đó là thuộc tính chung của process. Không đặt `orderId` thành resource attribute vì resource được gắn với nhiều spans và có thể làm cardinality tăng nghiêm trọng.

## 7. Schema của Spring Modulith và event metrics

Spring Modulith cung cấp telemetry hữu ích, nhưng cần xem meter names và tags là một phần của integration surface có thể thay đổi theo phiên bản.

### 7.1. Module-entry observations

Insight/observability integration có thể tạo module-entry observations tại điểm vào API module được instrument. Các tag thường gặp:

- `module.identifier`
- `module.name`
- `module.method`
- `module.invocation-type`

Dashboard hoặc tracing query có thể dùng các tag này để lọc module. Khi nâng cấp Spring Modulith, hãy kiểm tra release notes và span output thực tế để xác nhận key, type và allowed values. Không giả định mọi method hoặc self-invocation đều tạo span.

### 7.2. Event publication metrics

Spring Modulith cung cấp event publication metrics, gồm meter tổng hợp `module.events.published` và counter riêng theo module/event type trong các integration tương ứng. Tên meter, tag key và cách registry export có thể thay đổi khi nâng cấp framework hoặc registry.

Quy trình xác minh:

~~~bash
curl -s http://localhost:8080/actuator/metrics/module.events.published
curl -s http://localhost:8080/actuator/prometheus
~~~

Kiểm tra:

1. Meter có được đăng ký không?
2. Các available tags gồm những key nào?
3. Prometheus exporter biến đổi tên và tag như thế nào?
4. Có filter nào loại bỏ meter/tag không?
5. Dashboard và alert hiện tại đang phụ thuộc chính xác vào key nào?

Counter publication không chứng minh listener hoàn tất. Nếu cần theo dõi outcome, tạo meter riêng với semantics rõ ràng như listener attempts, completions hoặc failures; ghi rõ retry và transaction semantics.

### 7.3. ModulithEventMetricsCustomizer

Spring Modulith cho phép tùy biến tags của per-event metrics qua `ModulithEventMetricsCustomizer` ở các phiên bản hỗ trợ. Đây là điểm mở rộng có thể giúp thêm phân loại nghiệp vụ có cardinality thấp, ví dụ channel hoặc event source.

~~~java
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
~~~

Đoạn code giả định event có `channel()` và API tương ứng với phiên bản Spring Modulith đang dùng. Trước khi dựa vào tag này, xác minh nó xuất hiện trên meter nào và dashboard có query đúng meter đó. Không mặc định tag custom trên per-event counter sẽ được gắn lên counter tổng hợp.

### 7.4. Module identifier là dữ liệu có tác động rộng

Đổi tên module có thể ảnh hưởng:

- Module graph và tài liệu Documenter.
- `module.identifier` trên spans.
- Event metric tags hoặc meter name.
- Dashboard variables và grouping.
- Alert rules, recording rules và runbooks.
- Log fields và truy vấn lịch sử.

Vì vậy, đổi module identifier nên được xử lý như một telemetry schema migration, kể cả khi refactor package hoặc class là thay đổi nội bộ. Hãy cập nhật các consumer cùng release plan và giữ mapping tên cũ/mới trong giai đoạn chuyển tiếp nếu backend cần đối chiếu dữ liệu lịch sử.

## 8. Versioning: khi nào cần version schema?

Không phải mọi lần thêm attribute đều cần tăng version. Chọn cách quản lý theo phạm vi ảnh hưởng:

| Phạm vi | Cách quản lý |
| --- | --- |
| Thêm optional attribute, semantics không đổi | Additive change; cập nhật schema docs, không nhất thiết đổi major version. |
| Thêm tag có tập giá trị mới | Ghi allowed values và kiểm tra dashboard/alert. |
| Đổi metric type/unit/meaning | Tạo metric mới hoặc schema version mới; giữ metric cũ trong thời gian migrate. |
| Đổi span/log field name | Dual-write hoặc hỗ trợ cả key cũ/mới; deprecate key cũ sau khi consumer chuyển. |
| Thay convention chuẩn | Ghi convention/schema URL và lộ trình chuyển đổi theo hướng dẫn upstream. |
| Đổi resource identity | Lập kế hoạch vì service/environment grouping, retention và dashboards có thể bị chia series. |

### 8.1. Version metric name hay thêm label version?

Không nên thêm `schema_version` label vào mọi metric chỉ để quản lý phiên bản. Label này nhân số time series và làm dashboard phải xử lý nhiều series. Với breaking change về semantics, tên metric mới thường dễ hiểu và dễ migrate hơn.

Ví dụ:

~~~text
shop.module.listener.duration
shop.module.listener.processing.duration
~~~

Metric đầu tiên có thể tiếp tục phản ánh semantics cũ trong thời gian deprecation; metric thứ hai mang semantics mới. Tên cụ thể cần theo naming convention của tổ chức.

### 8.2. Version span/log schema

Với spans và logs, có thể:

- Giữ attribute cũ và thêm attribute mới trong thời gian chuyển đổi.
- Ghi `schema_url`/schema version ở instrumentation hoặc resource khi hệ thống hỗ trợ.
- Đưa `service.version` vào resource để xác định phiên bản ứng dụng tạo telemetry.
- Chuẩn hóa field names tại collector nếu cần hỗ trợ nhiều phiên bản producer.

`service.version` không thay thế schema version hoàn toàn: một phiên bản service có thể phát nhiều schema hoặc nhiều service version có thể phát cùng schema. Tách rõ version ứng dụng và version telemetry contract.

## 9. Consumer của telemetry schema

Producer không phải bên duy nhất cần được xem xét. Trước khi đổi schema, phải lập danh sách consumer.

| Consumer | Phụ thuộc vào | Rủi ro khi schema đổi |
| --- | --- | --- |
| Prometheus recording rules | Metric name, labels, type, unit. | Rule không match hoặc aggregation sai. |
| Alert rules | Query, threshold, label selectors. | Alert im lặng hoặc báo giả. |
| Grafana dashboards | Query, variables, field names, units. | Panel trống hoặc hiển thị sai đơn vị. |
| Tracing backend queries | Span name, attributes, resource fields. | Search/filter không còn tìm thấy span. |
| Log parser | JSON field names, timestamp, severity. | Parse error hoặc field bị rơi. |
| Data warehouse/ETL | Schema, event time, dimensions. | Job ingest lỗi hoặc lịch sử không đồng nhất. |
| SLO/reporting | Metric semantics, aggregation window. | SLI thay đổi ý nghĩa mà không có thay đổi SLO. |
| Runbooks | Tên metric, endpoint, dashboard link. | Hướng dẫn điều tra không còn đúng. |

### 9.1. Quản lý dashboard và alert như code

Lưu dashboard provisioning, Prometheus rules và collector configuration trong version control. Khi đổi metric/tag:

1. Tìm tất cả query tham chiếu tên cũ.
2. Tìm alert/recording rules sử dụng label cũ.
3. Tìm dashboard variables và transformations.
4. Tìm log parser hoặc trace query phụ thuộc field.
5. Cập nhật runbook và hướng dẫn vận hành.
6. Thử query với dữ liệu cũ và mới trước khi remove field.

Không phải consumer nào cũng nằm trong cùng repository. Cần có owner/catalog hoặc quy trình thông báo cho platform team, SRE và data team.

### 9.2. Dashboard phải chịu được giai đoạn mixed-version

Trong rolling deployment, một số instance có thể phát schema cũ, số khác phát schema mới. Query cần xử lý cả hai trong thời gian migrate, hoặc dashboard phải hiển thị rõ version đang được chọn.

Nếu field cũ và mới cùng xuất hiện, tránh cộng hai series đại diện cho cùng một request. Có thể lọc theo service version, phân nhóm riêng hoặc dùng query hợp nhất có logic loại trùng.

## 10. Quy trình migration có kiểm soát

Một migration telemetry schema an toàn thường có các bước sau:

~~~mermaid
flowchart TD
    A["Đề xuất thay đổi schema"]
    B["Đánh giá compatibility và consumers"]
    C{"Breaking change?"}
    D["Additive rollout"]
    E["Dual-publish / dual-read"]
    F["Migrate dashboards, alerts, ETL"]
    G["Quan sát mixed-version và usage"]
    H["Deprecate field cũ"]
    I["Remove sau compatibility window"]
    J["Cập nhật schema docs và runbooks"]
    A --> B --> C
    C -->|"Không"| D --> F --> G --> J
    C -->|"Có"| E --> F --> G --> H --> I --> J
~~~

### 10.1. Bước 1 — Đề xuất và mô tả lý do

Mỗi thay đổi nên ghi:

- Field/metric/span hiện tại và semantics hiện tại.
- Vấn đề cần giải quyết.
- Schema mới và semantics dự kiến.
- Producer/service/module sở hữu.
- Consumer đã biết.
- Phạm vi tương thích và ngày dự kiến deprecate/remove.
- Rủi ro cardinality, privacy, storage và query cost.

Không đổi schema chỉ vì tên mới “đẹp hơn” nếu không có lợi ích vận hành rõ.

### 10.2. Bước 2 — Phân loại và phê duyệt

Đánh dấu thay đổi là additive, behavior-changing hay breaking. Với breaking change, cần owner telemetry, owner dashboard/alert và các team tiêu thụ dữ liệu xác nhận kế hoạch.

Không cần quy trình phê duyệt nặng cho mọi attribute tùy chọn; nhưng thay đổi metric semantics, unit, resource identity hoặc event processing outcome có thể ảnh hưởng SLO và báo cáo, nên phải được review.

### 10.3. Bước 3 — Dual-publish hoặc adapter

Với rename metric:

~~~java
meterRegistry.counter(
    "shop.module.invocations",
    "module", moduleIdentifier,
    "outcome", outcome
).increment();

// Chỉ trong compatibility window: metric mới phản ánh cùng semantics.
meterRegistry.counter(
    "shop.module.entry.count",
    "module", moduleIdentifier,
    "outcome", outcome
).increment();
~~~

Ví dụ trên minh họa dual-publish hai counter có cùng semantics. Cần đánh giá chi phí và tránh dashboard cộng cả hai series thành tổng gấp đôi. Có thể chọn adapter tại collector hoặc recording rule nếu phù hợp hơn việc instrument hai lần ở producer.

Với span/log field rename, có thể phát cả key cũ và mới trong một khoảng thời gian, hoặc chuẩn hóa tại collector. Không dual-write vô thời hạn; đặt owner và ngày kết thúc rõ.

### 10.4. Bước 4 — Migrate consumer trước khi remove

Thứ tự thường an toàn:

1. Deploy producer phát schema mới, vẫn giữ schema cũ.
2. Deploy collector/parser hỗ trợ cả hai.
3. Migrate dashboard và alert sang schema mới.
4. Xác nhận query mới có dữ liệu và alert test hoạt động.
5. Theo dõi số producer/consumer còn dùng schema cũ.
6. Deprecate và remove schema cũ sau compatibility window.

Với metric rename, cần đảm bảo dashboard không cộng metric cũ và mới cùng lúc nếu chúng đo cùng một event. Với trace/log field, kiểm tra query lịch sử có thể cần fallback key cũ trong retention period.

### 10.5. Bước 5 — Quan sát và rollback

Trong rollout, theo dõi:

- Tỷ lệ instance phát schema mới/cũ.
- Số time series mới và mức tăng cardinality.
- Query error, no-data panel và alert firing.
- Collector parse/rejection errors.
- Backend ingest volume, storage và index latency.
- SLO/SLI có thay đổi ngoài dự kiến không.

Nếu schema mới gây lỗi consumer, rollback producer hoặc tạm khôi phục adapter. Không remove field cũ trước khi đã xác nhận migration thành công.

### 10.6. Bước 6 — Deprecate và remove

Deprecation cần có:

- Thông báo field cũ sẽ không còn được phát.
- Tài liệu schema mới và ví dụ query.
- Ngày deprecate và ngày remove dự kiến.
- Hướng dẫn migration cho consumer.
- Cách kiểm tra usage còn sót.
- Owner xử lý exception hoặc consumer chưa chuyển.

Chỉ remove khi đã có bằng chứng consumer đã chuyển hoặc owner chấp nhận mất compatibility. Với dữ liệu lịch sử, giữ mapping/documentation để giải thích vì sao series cũ kết thúc.

## 11. Collector và pipeline transformation cũng là schema boundary

Collector có thể đổi tên, thêm, xóa hoặc chuẩn hóa attributes/labels. Những processor này là một phần của contract mà dashboard nhìn thấy.

Ví dụ, collector có thể chuẩn hóa environment label hoặc map attribute cũ sang key mới. Khi thay đổi:

- Kiểm tra processor có giữ đúng resource/span scope không.
- Tránh overwrite giá trị nguồn mà không có tài liệu.
- Theo dõi dropped attributes và transform errors nếu processor cung cấp.
- Đảm bảo các pipeline traces/metrics/logs dùng mapping nhất quán khi cần.
- Version hóa collector config và deploy có kiểm soát.

Không dùng collector transformation để che một producer schema sai trong thời gian dài. Adapter có ích trong compatibility window; producer vẫn cần được migrate và tài liệu hóa.

### 11.1. OpenTelemetry schema URL

OpenTelemetry hỗ trợ gắn schema URL vào resource/scope để chỉ ra schema mô tả telemetry. Khi schema được chuyển đổi, schema URL có thể giúp consumer biết cần áp dụng mapping nào, nếu ecosystem/tooling đang dùng hỗ trợ.

Không tự tạo schema URL giả hoặc cho rằng mọi backend tự động migrate attributes theo URL. Xác nhận SDK, collector, exporter và backend thực sự giữ/hiểu metadata đó. Nếu không, versioning vẫn cần được thực hiện bằng quy trình producer-consumer thông thường.

### 11.2. Semantic Conventions migration

Khi nâng cấp OpenTelemetry instrumentation hoặc semantic conventions:

1. Xem release notes/migration guide của convention.
2. Xác định attribute cũ, mới và giai đoạn hỗ trợ cả hai.
3. Kiểm tra SDK/agent có thể phát cả hai key hay không.
4. Cập nhật trace queries, dashboards và data pipelines.
5. Chạy thử với trace mẫu ở môi trường staging.
6. Chỉ bỏ key cũ khi consumer đã chuyển.

## 12. Kiểm thử telemetry schema trong CI

Telemetry schema có thể được kiểm thử như một interface. Mục tiêu không phải đóng băng mọi field, mà phát hiện thay đổi ngoài dự kiến và yêu cầu người thay đổi cập nhật consumer.

### 12.1. Kiểm tra metric contract

Một test có thể khởi tạo application context, thực hiện một hành động đại diện và kiểm tra:

- Metric cần thiết đã được đăng ký.
- Type và unit đúng semantics.
- Tag keys bắt buộc hiện diện.
- Allowed values thuộc danh sách được phép.
- Không có tag chứa ID duy nhất hoặc dữ liệu nhạy cảm.

Ví dụ kiểm tra với Micrometer `MeterRegistry`:

~~~java
Meter meter = meterRegistry.find("shop.module.invocations")
    .tag("module", "payment")
    .meter();

assertThat(meter).isNotNull();
assertThat(meter.getId().getType()).isEqualTo(Meter.Type.COUNTER);
assertThat(meter.getId().getTag("outcome")).isEqualTo("SUCCESS");
~~~

Đây là test minh họa; metric name, tag và API phải khớp với implementation. Với Prometheus registry, kiểm tra thêm exposition output vì tên meter có thể được chuẩn hóa.

### 12.2. Snapshot span schema

Trong integration test, tạo một operation đại diện và thu span bằng in-memory exporter hoặc test tracer phù hợp. Kiểm tra các field cần giữ ổn định:

- Span name hoặc operation convention.
- Resource attributes như `service.name`.
- Module attributes được dùng trong dashboard.
- Status và error recording.
- Parent/child hoặc links nếu test cần xác nhận propagation.

Không nên snapshot toàn bộ span một cách cứng nhắc nếu SDK thêm attribute nội bộ theo version. Chỉ assert contract mà consumer thật sự phụ thuộc.

### 12.3. Kiểm tra structured log schema

Ghi một log record mẫu và parse JSON để xác nhận:

- Timestamp có offset/UTC theo quy ước.
- Severity có mapping đúng.
- `service.name`, module và event fields tồn tại.
- Trace/span IDs đúng field name.
- Không có token, payload nhạy cảm hoặc thông tin cá nhân ngoài allowlist.

### 12.4. Consumer contract tests

Dashboard và alert cũng cần được kiểm tra:

- PromQL có parse được và query trả series trong fixture data.
- Dashboard panel không rơi vào no-data khi schema mới được phát.
- Alert test chuyển sang firing khi fixture thỏa điều kiện.
- Log parser đọc được cả schema cũ và mới trong compatibility window.
- Trace query tìm được spans theo attribute mới.

Có thể lưu fixture telemetry đại diện theo phiên bản để kiểm thử parser, query và migration. Fixture cần loại bỏ dữ liệu nhạy cảm.

### 12.5. Schema diff trong pull request

Một PR thay đổi instrumentation nên kèm bảng:

| Mục | Nội dung cần ghi |
| --- | --- |
| Schema cũ | Metric/span/log field hiện tại. |
| Schema mới | Field mới, field đổi tên hoặc semantics mới. |
| Compatibility | Additive, behavior-changing hay breaking. |
| Consumers | Dashboard, alert, ETL, runbook bị ảnh hưởng. |
| Migration | Dual-publish, adapter, rollout và deprecation window. |
| Validation | Test metric/span/log, query và alert. |

Nếu không có thay đổi schema, PR vẫn có thể ghi rõ instrumentation contract không đổi để reviewer biết đã cân nhắc.

## 13. Cardinality, privacy và chi phí lưu trữ

Tiến hóa schema có thể làm chi phí tăng dù không làm dashboard hỏng ngay.

### 13.1. Cardinality của metrics

Prometheus tạo time series theo tổ hợp metric name và label values. Nếu thêm một label có hàng nghìn giá trị, số series có thể tăng mạnh.

Ví dụ:

| Label | Số giá trị giả định |
| --- | ---: |
| module | 8 |
| outcome | 4 |
| region | 5 |
| customer_id | 100.000 |

Tổ hợp có thể tăng từ 8 × 4 × 5 = 160 lên 16 triệu nếu thêm `customer_id`. Đây chỉ là phép tính minh họa; thực tế phụ thuộc số tổ hợp xuất hiện, nhưng cho thấy vì sao ID duy nhất không phù hợp làm metric label.

### 13.2. Span attributes cũng có chi phí

Trace backend thường cho phép attributes có cardinality cao hơn metric labels, nhưng vẫn có chi phí index, storage và query. Tránh gắn toàn bộ request/response body, SQL text, token hoặc dữ liệu cá nhân vào mọi span.

Chỉ thêm attribute nếu nó giúp truy vấn/điều tra và đã có quy tắc retention, masking và access control.

### 13.3. Logs có thể làm lộ dữ liệu nhạy cảm

Schema log cần quy định:

- Field nào được phép ghi.
- Field nào phải mask hoặc hash.
- Field nào tuyệt đối không ghi như access token, password, payment secret.
- Ai có quyền truy vấn log và thời gian retention.
- Cách xử lý dữ liệu cá nhân theo chính sách tổ chức.

Đổi schema không phải lý do để copy toàn bộ payload nghiệp vụ vào logs. Dùng allowlist và structured fields tối thiểu.

## 14. Quản trị ownership và lifecycle

Một schema chỉ có thể tiến hóa an toàn nếu biết ai sở hữu producer và consumer.

| Vai trò | Trách nhiệm |
| --- | --- |
| Module owner | Định nghĩa semantics telemetry của module và đảm bảo instrumentation đúng. |
| Observability/platform owner | Duy trì convention chung, collector pipeline và schema catalog. |
| Dashboard/alert owner | Cập nhật query, thresholds và kiểm thử consumer. |
| Data platform owner | Kiểm tra ETL, retention và historical compatibility. |
| Service owner | Điều phối rollout, version và rollback. |

### 14.1. Schema catalog tối thiểu

Mỗi metric/span/log field quan trọng nên có:

- Tên canonical và aliases cũ nếu có.
- Mô tả semantics.
- Producer owner.
- Type, unit và allowed values.
- Labels/attributes và cardinality dự kiến.
- Sensitivity/privacy classification.
- Consumer đã biết.
- Phiên bản đầu tiên, trạng thái active/deprecated và ngày remove.
- Link dashboard, alert, runbook và test.

Catalog có thể là YAML, tài liệu trong repository hoặc hệ thống metadata tập trung. Không cần một nền tảng mới nếu danh mục nhỏ; điều quan trọng là được review và cập nhật cùng code.

### 14.2. Lifecycle trạng thái

Một vòng đời đơn giản:

~~~text
PROPOSED -> ACTIVE -> DEPRECATED -> REMOVED
~~~

- `PROPOSED`: schema đang được review và chưa phải contract được hỗ trợ.
- `ACTIVE`: producer phát và consumer có thể dựa vào.
- `DEPRECATED`: vẫn được phát trong compatibility window nhưng không nên tạo consumer mới.
- `REMOVED`: producer không còn phát; mapping lịch sử có thể vẫn được giữ trong tài liệu.

Không dùng trạng thái `DEPRECATED` vô thời hạn. Mỗi schema cũ cần owner, thời hạn và tiêu chí remove.

## 15. Troubleshooting khi schema thay đổi làm telemetry biến mất

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Dashboard panel trống sau deploy | Metric name hoặc tag key đổi. | Xem `/actuator/metrics`, `/actuator/prometheus` và query cũ/mới. |
| Alert không còn firing dù lỗi tăng | Alert selector không match label mới hoặc semantics thay đổi. | Chạy query trực tiếp, kiểm tra labels và fixture alert. |
| p95 tăng/giảm đột ngột | Unit, histogram buckets hoặc timer semantics đổi. | Kiểm tra unit, bucket boundaries, count/sum và metric version. |
| Metric cardinality tăng | Thêm tag có nhiều giá trị hoặc URL/ID động. | So sánh active series trước/sau, loại bỏ label không bounded. |
| Trace query không tìm thấy module | Attribute key/value hoặc span name đổi. | Mở raw span, so sánh resource/span attributes. |
| Log parser báo missing field | JSON field đổi tên/type hoặc timestamp format đổi. | Xem raw log, parser errors và schema compatibility. |
| ETL job lỗi sau nâng cấp | Schema mapping hoặc field type thay đổi. | Kiểm tra schema registry/fixture, backfill và consumer version. |
| Dữ liệu lịch sử bị chia đôi | Producer cũ và mới phát hai tên metric/schema. | Phân nhóm theo service.version/schema, cập nhật query hợp nhất. |
| Module rename làm alert mất dữ liệu | module identifier được dùng làm tag và filter. | So sánh module graph, span tags, event metric labels và dashboard variable. |
| Metric mới tăng gấp đôi | Dual-publish nhưng dashboard cộng cả series cũ và mới. | Kiểm tra query aggregation và compatibility logic. |

### Quy trình điều tra

1. Xác định thời điểm schema thay đổi so với deploy.
2. So sánh raw telemetry trước và sau thay đổi.
3. Kiểm tra producer có phát dữ liệu hay không.
4. Kiểm tra collector có rename/filter/drop field không.
5. Chạy query mới và cũ trực tiếp trên backend.
6. Kiểm tra dashboard, alert và ETL consumer.
7. Nếu cần, bật lại field cũ hoặc adapter trong compatibility window.
8. Cập nhật catalog và runbook sau khi khắc phục.

## 16. Checklist trước khi phát hành schema mới

Trước khi deploy thay đổi telemetry, hãy xác nhận:

1. **Semantics:** metric/span/log field mới có định nghĩa rõ, không nhập nhằng với field cũ.
2. **Type và unit:** counter, gauge, timer, histogram và đơn vị đo không đổi ngầm.
3. **Naming:** tên tuân theo convention của Micrometer/OpenTelemetry và hệ thống.
4. **Labels/attributes:** allowed values được giới hạn; không thêm ID duy nhất vào metric.
5. **Privacy:** không phát secret, token, payload hoặc dữ liệu cá nhân ngoài chính sách.
6. **Module identity:** đổi module identifier đã được đánh giá trên graph, spans, event metrics và dashboard.
7. **Consumers:** dashboard, alert, recording rules, log parser, trace query, ETL và runbook đã được rà soát.
8. **Compatibility:** thay đổi additive hay breaking đã được phân loại.
9. **Migration:** có dual-publish/adapter, compatibility window và ngày remove nếu cần.
10. **Testing:** metric/span/log schema và consumer queries có test trong CI/staging.
11. **Mixed version:** rolling deployment có thể xử lý producer cũ và mới cùng lúc.
12. **Rollback:** có cách quay lại schema cũ hoặc bật adapter khi consumer gặp lỗi.
13. **Cost:** cardinality, storage, ingestion và query cost đã được ước lượng.
14. **Ownership:** producer owner và consumer owner biết lịch thay đổi.
15. **Documentation:** schema catalog, dashboard và runbook được cập nhật.

## 17. Bài tập thực hành

### Bài 1 — Phân loại thay đổi schema

Một PR thực hiện ba việc: thêm span attribute `module.operation`, đổi metric unit từ milliseconds sang seconds và đổi tag `outcome=SUCCESS` thành `outcome=OK`. Phân loại từng thay đổi là additive hay breaking. Nêu consumer có thể bị ảnh hưởng và migration cần thiết.

### Bài 2 — Dual-publish metric

Tạo metric counter mới có cùng semantics với metric cũ. Cho cả hai cùng phát trong staging. Cập nhật Grafana dashboard chỉ đọc metric mới và xác nhận không cộng đôi hai series. Sau đó đề xuất thời điểm remove metric cũ dựa trên usage.

### Bài 3 — Thay đổi module identifier

Đổi tên module `notification` trong một nhánh thử nghiệm. Kiểm tra module graph, module-entry span attributes, event metrics, Grafana variables và alert rules. Lập danh sách consumer cần migrate trước khi release.

### Bài 4 — Kiểm thử metric contract

Viết test dùng `MeterRegistry` xác nhận metric invocation có type Counter, tag `module` thuộc danh mục cho phép và không có `customer_id`. Thử thêm một tag mới có cardinality cao và giải thích vì sao test nên chặn.

### Bài 5 — Mixed-version deployment

Giả lập hai instance: instance A phát schema cũ, instance B phát schema mới. Viết query hoặc adapter hỗ trợ cả hai trong compatibility window. Kiểm tra dashboard không nhân đôi count và alert không bỏ sót outcome.

### Bài 6 — Deprecation và consumer inventory

Chọn một span attribute hoặc log field đang được dashboard sử dụng. Lập inventory consumer, ngày deprecate, cách đo usage và điều kiện remove. Viết runbook ngắn để xử lý nếu một consumer chưa migrate.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao telemetry schema không nên được xem là bất biến tuyệt đối?

**Đáp án:** Instrumentation, framework conventions, module structure và nhu cầu vận hành thay đổi. Schema cần tiến hóa nhưng phải có compatibility policy để consumer không bị hỏng bất ngờ.

**Câu 2.** Thêm một metric label có luôn là additive change an toàn không?

**Đáp án:** Không. Label mới có thể tăng cardinality mạnh hoặc làm query grouping/alert filter thay đổi.

**Câu 3.** Khi nào nên tạo metric name mới?

**Đáp án:** Khi metric đổi type, unit hoặc semantics theo cách khiến dữ liệu cũ và mới không còn so sánh trực tiếp. Không nên giữ cùng tên rồi âm thầm đổi ý nghĩa.

**Câu 4.** Vì sao cần inventory consumer trước khi remove một span attribute?

**Đáp án:** Dashboard, alert, trace query, ETL và runbook có thể đang phụ thuộc vào attribute đó; xóa sớm làm chúng mất dữ liệu hoặc hoạt động sai.

**Câu 5.** `service.version` có tương đương telemetry schema version không?

**Đáp án:** Không. Nó nhận diện phiên bản ứng dụng tạo telemetry; một phiên bản service có thể phát nhiều schema, và nhiều phiên bản service có thể phát cùng schema.

**Câu 6.** Dual-publish metric có rủi ro gì?

**Đáp án:** Tăng ingestion/cardinality và có thể khiến dashboard cộng đôi dữ liệu nếu query đọc cả metric cũ lẫn mới.

**Câu 7.** Event metric `module.events.published` có phải domain event contract không?

**Đáp án:** Không. Đây là telemetry về publication; domain event payload là contract nghiệp vụ cho listener và integration consumer.

## 18. Tài liệu tham khảo

- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/): quy ước tên và attributes cho traces, metrics, logs và resources.
- [OpenTelemetry — Schema](https://opentelemetry.io/docs/specs/otel/schemas/): schema URL và cách chuyển đổi schema telemetry.
- [OpenTelemetry — Resource](https://opentelemetry.io/docs/concepts/resources/): resource attributes nhận diện entity tạo telemetry.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): metric streams, temporality, aggregation và attributes.
- [Micrometer — Meter](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): meter types, naming và tags.
- [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): quy tắc đặt tên và chuyển đổi theo registry.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module-entry observations, event metrics và Insight Starter.
- [Spring Modulith — Application Events](https://docs.spring.io/spring-modulith/reference/events.html): application event và Event Publication Registry.
- [Prometheus — Data Model](https://prometheus.io/docs/concepts/data_model/): time series, metric names và labels.
- [Prometheus — Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/): naming, labels, cardinality và instrumentation guidance.

**Ghi nhớ:** telemetry schema là giao diện vận hành giữa ứng dụng và các consumer như collector, dashboard, alert, tracing backend và data pipeline. Giữ ổn định semantics, type và unit; cho phép thay đổi có kiểm soát; đánh giá cardinality/privacy; migrate consumer trước khi remove field. Với Spring Modulith, thay đổi module identifier hoặc event metrics có thể tác động đồng thời tới module graph, spans, dashboards và alert rules. Quản trị schema tốt giúp hệ thống tiến hóa mà người vận hành vẫn hiểu đúng dữ liệu.
