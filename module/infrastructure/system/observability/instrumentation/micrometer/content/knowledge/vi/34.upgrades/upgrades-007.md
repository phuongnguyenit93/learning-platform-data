# Triển khai từng phần với dữ liệu đối chứng và phương án quay lui

## Vì sao cần nâng cấp theo từng giai đoạn?

Nâng cấp Micrometer, Spring Boot, registry hoặc exporter có thể thay đổi cách ứng dụng tạo meter, chuẩn hóa tên, gắn tag, ghi histogram và gửi dữ liệu. Một thay đổi compile thành công vẫn có thể làm dashboard mất series, alert đổi ngưỡng, Collector từ chối payload hoặc số liệu trước và sau nâng cấp không còn cùng semantics.

Triển khai từng phần giúp phát hiện khác biệt ở phạm vi nhỏ trước khi ảnh hưởng toàn bộ service. Mỗi giai đoạn cần có dữ liệu đối chứng, tiêu chí tiếp tục và điều kiện quay lui. Dữ liệu đối chứng có thể là workload kiểm thử đã biết kết quả, event ledger/database, traffic của phiên bản đang chạy hoặc một nhóm instance ổn định làm control.

Trong module OBSERVABILITY_INSTRUMENTATION_MICROMETER, ứng dụng Java dùng Counter, Gauge, Timer, DistributionSummary và tag có kiểm soát; tích hợp Spring Boot và xuất metrics đến hệ giám sát. Vì vậy, nâng cấp cần kiểm tra cả instrumentation trong tiến trình lẫn pipeline export, đồng thời bảo toàn khả năng diễn giải dữ liệu trong dashboard và SLO.

Một quy trình an toàn thường gồm:

1. Kiểm kê phiên bản, meter contract và consumer.
2. Ghi baseline cùng dữ liệu đối chứng.
3. Kiểm tra tương thích và chạy test trong môi trường staging.
4. Phát hành canary với một phần nhỏ traffic.
5. So sánh phiên bản mới với control và ground truth.
6. Tăng dần tỷ lệ triển khai qua các cổng kiểm soát.
7. Chuyển dashboard, alert và consumer nếu schema thay đổi.
8. Giữ sẵn artifact/cấu hình cũ và thực hiện rollback khi vượt ngưỡng.

Không xem việc ứng dụng khởi động thành công là bằng chứng đủ để nâng cấp hoàn tất. Cần chứng minh số liệu vẫn đúng và người vận hành vẫn đọc được chúng.

## Phạm vi nâng cấp và các thành phần phụ thuộc

### Kiểm kê toàn bộ chuỗi telemetry

Trước khi sửa dependency, ghi lại những thành phần đang tham gia:

| Thành phần | Thông tin cần kiểm kê | Rủi ro khi nâng cấp |
|---|---|---|
| Java runtime | Phiên bản JDK, vendor, JVM flags | API/runtime không tương thích |
| Spring Boot | Phiên bản, dependency management | Thay đổi auto-configuration và property |
| Micrometer core | Phiên bản được resolve thực tế | API, meter behavior, Observation |
| Registry | Prometheus, OTLP hoặc registry khác | Naming, temporality, histogram, export |
| Instrumentation | HTTP, JDBC, cache, executor, custom binder | Meter bị đổi tên hoặc điều kiện bind |
| AOP/Observation | TimedAspect, CountedAspect, handlers, conventions | Annotation hoặc context không còn được xử lý như trước |
| OpenTelemetry Collector | Receiver, processor, exporter, pipeline | Payload hoặc cấu hình không tương thích |
| Backend | Prometheus, metrics backend, retention | Query, aggregation và ingestion thay đổi |
| Consumers | Dashboard, alert, SLO, recording rule, script | Mất series hoặc đổi semantics |

Đừng chỉ xem phiên bản khai báo trong build file. Kiểm tra dependency thực tế sau khi resolve để phát hiện phiên bản Micrometer bị override hoặc kéo vào từ thư viện khác.

### Để Spring Boot quản lý phiên bản tương thích

Khi dùng Spring Boot dependency management, nên để BOM của Boot quản lý phiên bản Micrometer đã được kiểm thử cùng nền tảng đó. Không nâng Micrometer core hoặc registry lên phiên bản riêng một cách tùy tiện trong khi vẫn giữ Boot cũ.

Ví dụ Gradle dùng Spring Boot plugin và dependency management:

~~~kotlin
plugins {
    id("org.springframework.boot") version "<boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-version>"
    java
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Các placeholder phải được thay bằng phiên bản đã chọn trong kế hoạch nâng cấp. Với Maven, dùng Spring Boot parent hoặc BOM tương ứng. Nếu cần override Micrometer độc lập, ghi rõ lý do, dependency compatibility matrix và bằng chứng test; không để override ngẫu nhiên qua transitive dependency.

Có thể dùng dependency insight/tree để xác minh phiên bản đã resolve. Ví dụ Gradle:

~~~powershell
.\gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
~~~

Lưu output vào hồ sơ nâng cấp để so với bản trước. Không dựa vào phiên bản trong một file build nếu dependency resolution thực tế khác.

### Lập compatibility matrix

Ghi rõ tổ hợp đã kiểm tra trước khi rollout:

| Thành phần | Bản đang chạy | Bản đích | Kiểm tra bắt buộc |
|---|---|---|---|
| JDK | Phiên bản hiện tại | Phiên bản mục tiêu | Startup, GC, runtime compatibility |
| Spring Boot | Bản hiện tại | Bản đích | Auto-configuration, property, Actuator |
| Micrometer core | Bản resolve hiện tại | Bản do Boot quản lý hoặc override đã kiểm thử | API, meter semantics, Observation |
| Registry | Bản hiện tại | Bản tương thích | Naming, histogram, temporality, scrape/export |
| Collector | Cấu hình hiện tại | Cấu hình/bản đích | Receiver, processor, exporter |
| Backend | Hiện trạng | Hiện trạng hoặc bản nâng cấp | Ingestion và query |
| Dashboard/alert | Query hiện tại | Query tương thích | Kết quả trước/sau |

Không nhất thiết phải nâng tất cả thành phần cùng lúc. Nếu nâng cả Boot, Micrometer, Collector và backend trong một lần, khi có sai lệch sẽ khó xác định nguyên nhân. Tách thay đổi theo khả năng tương thích và khả năng rollback của từng lớp.

## Đóng băng metric contract trước khi nâng cấp

### Ghi lại danh mục meter quan trọng

Chọn các meter có ảnh hưởng vận hành hoặc nghiệp vụ và ghi lại:

- Micrometer name và tên xuất ở backend.
- Loại meter: Counter, Gauge, Timer, DistributionSummary hoặc Function meter.
- Unit và quy tắc chuyển đổi.
- Sự kiện làm meter tăng hoặc ranh giới bắt đầu/kết thúc Timer.
- Tag keys, allow-list và cardinality dự kiến.
- Histogram buckets, SLO boundaries, percentile và expiry nếu có.
- Resource attributes như service.name, service.version, environment.
- Owner, dashboard, alert, SLO và query đang sử dụng.
- Nguồn tạo meter: auto-configuration, MeterBinder, Observation, AOP hay code trực tiếp.

Đây là contract dùng để đối chiếu. Một meter tên orders.completed phải tiếp tục đếm cùng loại sự kiện sau nâng cấp. Nếu bản mới thay đổi điểm ghi từ “request được nhận” sang “transaction đã commit”, đó là thay đổi semantics dù tên meter không đổi.

### Phân loại thay đổi

| Loại thay đổi | Ví dụ | Mức độ tương thích |
|---|---|---|
| Không đổi contract | Nâng patch dependency nhưng giữ tên, tag, unit, semantics | Thường dễ so sánh; vẫn cần xác minh |
| Thay đổi cách xuất | Naming convention hoặc định dạng exposition khác | Consumer có thể cần cập nhật |
| Thêm dimension hữu hạn | Thêm tag outcome với allow-list nhỏ | Tăng cardinality; query có thể cần điều chỉnh |
| Đổi histogram | Thêm/bỏ bucket hoặc đổi SLO boundary | Phân phối trước/sau khó so trực tiếp |
| Đổi semantics | Đếm completion thay vì attempt | Breaking change |
| Đổi tên hoặc unit | Đổi orders.processing thành orders.processing.duration | Consumer cần migration |
| Đổi temporality | Cumulative sang delta hoặc ngược lại | Query/aggregation phải phù hợp |

Không gom tất cả vào một thay đổi “nâng version”. Tách dependency upgrade, instrumentation refactor và metric schema migration thành các thay đổi có thể review riêng nếu kế hoạch cho phép.

## Xây dựng baseline và dữ liệu đối chứng

### Baseline production

Trước khi triển khai, thu thập baseline từ phiên bản đang chạy trong một khoảng đại diện. Bao gồm cả giờ cao điểm và thời gian ít tải nếu hai giai đoạn có hành vi khác nhau.

Các nhóm cần ghi:

- Request rate và throughput nghiệp vụ.
- Error rate theo outcome/status.
- p50, p95, p99 latency của các operation quan trọng.
- Queue depth, worker active, connection pool active/pending.
- JVM memory, GC pause, CPU và thread count.
- Số meter, số series và cardinality theo service.
- Thời gian scrape/export, kích thước payload và lỗi exporter.
- Tình trạng target/Collector/backend và độ trễ dữ liệu.

Lưu lại cửa sổ thời gian, số instance, traffic volume, phiên bản ứng dụng, cấu hình registry và dashboard query. Nếu không có ngữ cảnh này, con số baseline không thể so sánh công bằng với canary.

### Dữ liệu đối chứng độc lập

Không chỉ so metric của bản mới với metric của bản cũ. Cả hai có thể cùng sai do bug nghiệp vụ hoặc cùng dùng một định nghĩa sai.

Chọn một nguồn độc lập phù hợp với meter:

| Meter | Dữ liệu đối chứng |
|---|---|
| orders.completed | Số order duy nhất đã commit trong database/event ledger |
| payments.failed | Ledger attempt hoặc event thất bại theo đúng semantics |
| http.server.requests | Access log/load generator và số request server thực nhận |
| orders.processing Timer | Trace/test harness đo cùng ranh giới operation |
| jobs.queue.depth Gauge | Snapshot từ queue thực tế tại thời điểm gần scrape |
| payload DistributionSummary | Dataset payload có kích thước đã biết |
| executor.active | Trạng thái worker/executor tại cùng thời điểm |

Nếu metric đếm attempt thì nguồn đối chứng cũng phải đếm attempt; nếu metric đếm business completion thì nguồn đối chứng phải đếm kết quả nghiệp vụ duy nhất. Không ép hai đại lượng khác semantics phải bằng nhau.

### Workload xác định trong staging

Chuẩn bị workload có số lượng và outcome đã biết, ví dụ:

| Kịch bản | Input | Kết quả dự kiến |
|---|---:|---:|
| Order hợp lệ | 700 | 700 order commit |
| Validation rejected | 150 | 150 rejected, không commit |
| Dependency failure | 100 | 100 attempt thất bại |
| Client timeout | 50 | Xác minh riêng server có tiếp tục xử lý hay không |
| Tổng | 1.000 | 1.000 request được phát |

Gắn run ID vào dataset, log hoặc test report để truy vấn kết quả. Không đưa run ID duy nhất vào metric tag production chỉ để đối chiếu. Cô lập registry hoặc environment test nếu cần tách các lượt chạy.

Chia thử nghiệm thành baseline, warm-up, load, drain và snapshot. Chờ transaction, queue, registry step, exporter và scrape hoàn tất trước khi chốt số liệu. Client timeout không chứng minh server đã hủy xử lý; cần kiểm tra ground truth phía server.

## Kiểm thử trước khi triển khai

### Unit test instrumentation

Dùng SimpleMeterRegistry để kiểm tra logic ghi nhận:

- Counter tăng đúng số lần.
- Timer count và total time theo duration xác định.
- Gauge đọc đúng trạng thái nguồn và giữ strong reference.
- DistributionSummary ghi đúng count/total amount.
- Tag và MeterFilter tuân thủ allow-list.
- Meter count không tăng theo request ID hoặc dữ liệu động.

Tạo registry riêng cho mỗi test để tránh count bị nhiễm từ test khác. Những test này xác nhận instrumentation trong tiến trình, không chứng minh exporter hoạt động.

### Spring Boot integration test

Khởi tạo ApplicationContext thật để xác minh:

- Dependency và auto-configuration.
- JVM, HTTP, DataSource, cache hoặc executor binder cần thiết.
- management.metrics.enable và MeterFilter.
- ObservationRegistry, ObservationHandler, convention.
- TimedAspect/CountedAspect và proxy nếu dùng annotation.
- Actuator metrics hoặc Prometheus endpoint được expose đúng.
- Registry được inject là registry mà exporter sử dụng.

Với AOP, gọi bean qua Spring context; không dùng new nếu mục tiêu là kiểm tra proxy. Với Observation, xác minh handler metrics đã đăng ký; tạo Observation trên registry rỗng không tự tạo Timer.

### Exporter và backend integration test

Kiểm tra exposition hoặc payload theo backend:

- PrometheusMeterRegistry.scrape() tạo sample và label đúng.
- /actuator/prometheus trả exposition đúng.
- Prometheus server scrape target và truy vấn được series.
- OTLP exporter gửi đúng protocol, endpoint, resource attributes và metric data.
- Collector nhận metrics và chuyển qua pipeline.
- Backend query được name, unit, tags, histogram và temporality.

scrape() chỉ kiểm tra exposition trong ứng dụng; nó không chứng minh Prometheus server đã scrape và lưu dữ liệu. Mock receiver xác nhận exporter gửi request; end-to-end test mới chứng minh receiver/backend chấp nhận và có thể truy vấn dữ liệu.

## Staging: chạy song song và so sánh

### Giữ điều kiện so sánh tương đương

Triển khai phiên bản mới vào staging với cấu hình gần production. Giữ cùng workload, dataset, số instance, scrape/export interval và backend hoặc receiver tương đương.

Nếu có thể, phát cùng một workload xác định đến hai phiên bản trong môi trường cô lập. Với traffic production, có thể dùng một nhóm instance cũ làm control và một nhóm mới làm canary. Tránh gửi cùng một giao dịch thật vào hai phiên bản nếu có thể gây side effect; dùng replay an toàn, shadow traffic chỉ đọc hoặc dữ liệu test đã cô lập.

### Phân vùng dữ liệu theo phiên bản

Khi so sánh canary, cần biết series nào đến từ phiên bản nào. Ưu tiên dùng resource attribute service.version trong OTLP hoặc target/deployment label có cardinality giới hạn trong Prometheus.

Không thêm build hash, request ID hoặc release ID có giá trị không giới hạn vào meter tag. Một label phiên bản release có thể hữu ích trong thời gian chuyển đổi, nhưng cần quy định retention và loại bỏ dimension không còn cần thiết sau khi rollout hoàn tất.

Nếu bản cũ và mới cùng phát metric có cùng tên và tag nhưng semantics khác nhau, backend có thể gộp chúng vào cùng series. Khi semantics thay đổi, phải dùng metric name mới hoặc một dimension schema được thiết kế rõ ràng để tách dữ liệu trong giai đoạn migration.

### So sánh theo semantics, không chỉ so raw value

Đối với Counter cumulative, tính rate/increase theo từng instance trước rồi mới tổng hợp để xử lý reset. Không so raw counter của hai process có thời điểm khởi động khác nhau.

Đối với Timer, so count, total time và histogram trên cùng tập operation và cùng đơn vị. Không lấy trung bình p95 của từng instance để đại diện p95 toàn service; tổng hợp bucket đúng cách rồi mới tính quantile.

Đối với Gauge, so snapshot tại thời điểm gần nhau. Đối với DistributionSummary, so cùng dataset và unit. Với OTLP, xác minh cumulative/delta temporality trước khi dùng cùng query hoặc công thức.

### Ví dụ query so sánh theo version

Nếu Prometheus có target label version, có thể tính throughput theo từng phiên bản:

~~~promql
sum by (version) (
  rate(orders_completed_total[5m])
)
~~~

Với histogram latency:

~~~promql
histogram_quantile(
  0.95,
  sum by (version, le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Các tên metric và label trong ví dụ phải được thay bằng exposition thực tế. Nếu version là resource attribute được chuyển đổi theo quy tắc khác, query phải theo label tương ứng của backend. Không giả định mọi exporter giữ nguyên tên hoặc thuộc tính.

## Canary và progressive rollout

### Tăng traffic theo từng cổng

Một rollout có thể dùng các mức như 1%, 5%, 10%, 25%, 50% và 100%. Đây là ví dụ về các bước; tỷ lệ và thời gian giữ phải phù hợp với khả năng chịu lỗi, traffic và thời gian quan sát của service.

Tại mỗi bước:

1. Chuyển một phần traffic sang phiên bản mới.
2. Chờ đủ request và ít nhất các chu kỳ scrape/export cần thiết.
3. Kiểm tra health, error rate, latency, throughput và saturation.
4. So sánh meter mới với control và ground truth.
5. Kiểm tra exporter, Collector, backend và cardinality.
6. Chỉ tăng tỷ lệ khi tất cả cổng kiểm soát đạt.

Không chuyển từ 1% lên 100% chỉ vì readiness probe xanh. Readiness chứng minh ứng dụng có thể nhận traffic, không chứng minh metrics đúng.

### Các tín hiệu cần theo dõi

| Nhóm | Tín hiệu | Điều cần phát hiện |
|---|---|---|
| Availability | HTTP 5xx, failed operation, health | Lỗi tăng sau rollout |
| Latency | p95/p99 theo operation | Tail latency tăng |
| Throughput | Request và business completion rate | Mất hoặc nhân đôi sự kiện |
| Saturation | CPU, memory, GC, queue, pool | Overhead hoặc nghẽn |
| Metrics quality | Meter count, series count, missing series | Cardinality tăng hoặc meter biến mất |
| Export pipeline | Scrape failure, export error, Collector queue | Dữ liệu không đến backend |
| Semantics | So sánh với ledger/test workload | Count, unit hoặc outcome sai |
| Cost | Payload size, ingest rate, storage | Histogram/tag làm chi phí tăng |

Đặt ngưỡng dừng trước rollout. Ví dụ: error rate vượt SLO hoặc tăng đáng kể so với control; p95/p99 vượt ngưỡng; business count lệch ground truth; scrape/export failure tăng; cardinality vượt ngân sách. Ngưỡng cụ thể phải dựa trên baseline và SLO của service, không lấy một con số chung cho mọi hệ thống.

### Cổng quyết định tại mỗi giai đoạn

| Cổng | Điều kiện tiếp tục | Hành động nếu không đạt |
|---|---|---|
| Build/compatibility | Dependency tree và compile/test đạt | Dừng trước deploy |
| Staging | Meter contract, endpoint và exporter đúng | Sửa hoặc quay về dependency cũ |
| Canary nhỏ | Không có regression và dữ liệu đối chứng khớp | Dừng tăng traffic, rollback canary |
| 25–50% | Chất lượng telemetry và nghiệp vụ ổn định | Chuyển traffic về bản cũ |
| 100% | Dashboard, alert, SLO và backend ổn định | Giữ giám sát tăng cường, rollback nếu cần |
| Sau rollout | Không có lỗi trễ, consumer đã chuyển | Tiếp tục duy trì đường quay lui |

Giữ mỗi giai đoạn đủ lâu để quan sát peak load, chu kỳ batch, scrape/export và độ trễ backend. Với workload theo giờ hoặc theo ngày, một cửa sổ vài phút có thể không đủ.

## Chuyển đổi metric schema an toàn

### Không đổi nghĩa dưới cùng một tên

Nếu phiên bản mới thay đổi semantics, hãy tạo metric mới. Ví dụ, metric cũ đếm attempt còn metric mới đếm order commit duy nhất:

- orders.processing.attempts
- orders.completed

Có thể ghi cả hai trong giai đoạn chuyển tiếp nếu chi phí và cardinality cho phép. Dashboard và alert cần được chuyển sang metric mới sau khi đã xác minh số liệu. Sau đó đánh dấu metric cũ deprecated và ngừng ghi theo lịch đã thông báo.

Không dùng cùng tên và tag cho hai định nghĩa khác nhau. Dữ liệu lịch sử sẽ bị trộn, làm rate và trend mất ý nghĩa.

### Thay đổi tag hoặc histogram

Thêm tag làm tăng cardinality và có thể khiến query cũ tạo nhiều nhóm hơn. Đổi tag key có thể làm dashboard/alert không còn tìm thấy series. Đổi histogram bucket khiến phân phối trước/sau khó so trực tiếp.

Với mỗi thay đổi, ghi rõ:

- Tên metric cũ và mới.
- Tag cũ/mới cùng allow-list.
- Unit và semantics.
- Histogram/SLO boundaries.
- Query và dashboard cần sửa.
- Thời điểm bắt đầu dual publish và thời điểm ngừng metric cũ.
- Owner phê duyệt và phương án quay lui.

Nếu chỉ đổi cách hiển thị hoặc naming convention, xác minh exposition trước khi sửa consumer. Nếu đổi temporality cumulative/delta, kiểm tra pipeline và backend query vì cách tính rate/increase có thể khác.

### Dual publish có giới hạn

Dual publish nghĩa là phiên bản mới tạm thời ghi cả metric cũ và metric mới để consumer chuyển đổi. Chỉ dùng khi có lý do tương thích rõ ràng. Nó làm tăng số meter và có thể tăng CPU, memory, series và ingest.

Đặt thời hạn kết thúc dual publish, theo dõi cardinality và bảo đảm hai metric không bị cộng chung như hai nguồn độc lập trong dashboard. Không dual publish vô thời hạn.

## Chuẩn bị phương án quay lui trước khi canary

### Những thứ phải lưu trước rollout

Trước khi triển khai, lưu lại:

- Artifact/container image của phiên bản hiện tại.
- Lockfile hoặc dependency tree đã resolve.
- Cấu hình Spring Boot, registry, common tags và MeterFilter.
- Cấu hình Prometheus scrape hoặc OTLP exporter.
- Cấu hình Collector receiver/processor/exporter.
- Dashboard, alert, recording rule và SLO query hiện tại.
- Baseline, test report và metric catalog.
- Tỷ lệ traffic, routing rule và feature flag trước rollout.
- Quy trình deploy lại phiên bản trước và người có quyền thực hiện.

Không để rollback phụ thuộc vào việc phải build lại phiên bản cũ trong lúc đang có sự cố. Artifact và cấu hình cũ cần sẵn sàng, đã xác minh có thể triển khai.

### Xác định trigger rollback

Trigger phải đo được và được thống nhất trước:

- Error rate hoặc failed business operation vượt ngưỡng.
- p95/p99 latency tăng vượt ngưỡng so với control.
- Throughput hoặc business completion lệch ground truth.
- JVM CPU, allocation, GC hoặc memory tăng bất thường.
- Số meter/time series vượt cardinality budget.
- Prometheus scrape thất bại hoặc OTLP export/Collector queue lỗi.
- Dashboard/alert trọng yếu không còn dữ liệu.
- Backend từ chối payload hoặc không truy vấn được metric cần thiết.

Không chờ đủ mọi chỉ số cùng xấu mới rollback. Một lỗi semantics làm mất khả năng giám sát SLO cũng có thể là lý do dừng rollout dù request vẫn thành công.

## Quy trình rollback

### Quay lui theo thứ tự có thể kiểm soát

Khi trigger xảy ra:

1. **Dừng rollout:** không tăng thêm traffic hoặc instance mới.
2. **Giữ bằng chứng:** lưu log, deployment version, registry exposition, Collector status và query kết quả.
3. **Chuyển traffic về bản cũ:** dùng deployment/traffic controller hoặc feature flag đã chuẩn bị.
4. **Khôi phục cấu hình tương thích:** registry, exporter, endpoint, Collector và resource attributes.
5. **Xác minh bản cũ:** health, request flow, meter count, scrape/export và dashboard hoạt động lại.
6. **Kiểm tra consumer:** khôi phục query/alert cũ nếu đã thay đổi trong rollout.
7. **Đối chiếu dữ liệu:** xác định khoảng thời gian bị thiếu, trùng hoặc khác semantics.
8. **Đóng rollout:** ghi nguyên nhân, thời điểm, phạm vi ảnh hưởng và bằng chứng.

Nếu chỉ exporter hoặc Collector bị lỗi, có thể rollback riêng cấu hình pipeline mà không cần rollback toàn bộ ứng dụng, miễn là phiên bản ứng dụng vẫn tương thích với pipeline cũ. Nếu lỗi nằm ở instrumentation hoặc API incompatibility, cần quay lại artifact ứng dụng đã biết tốt.

### Rollback không xóa dữ liệu backend

Quay lui ứng dụng không tự xóa time series đã gửi. Backend có thể giữ dữ liệu của canary trong retention window. Phân vùng theo version/resource attributes giúp loại dữ liệu canary khỏi query so sánh hoặc đánh dấu giai đoạn bị ảnh hưởng.

Không xóa lịch sử backend để che chênh lệch. Ghi chú thời điểm rollback và loại series bị ảnh hưởng để dashboard và phân tích sau sự cố hiểu đúng dữ liệu.

### Nếu schema đã thay đổi

Nếu rollout đã bắt đầu dual publish hoặc consumer đã chuyển một phần:

- Khôi phục query/alert cũ trước hoặc đồng thời với traffic.
- Giữ metric mới ở trạng thái chỉ đọc nếu cần điều tra, nhưng tránh tiếp tục ghi nếu nó gây cardinality hoặc exporter overload.
- Không đổi ngược semantics của metric mới dưới cùng tên.
- Để metric cũ tiếp tục hoạt động nếu phiên bản cũ cần nó.
- Ghi rõ khoảng dữ liệu thiếu hoặc bị trộn.
- Lập kế hoạch migration lại sau khi nguyên nhân được sửa.

Nếu dashboard đã dùng metric mới nhưng application rollback về bản cũ không phát metric đó, dashboard có thể trống. Vì vậy, consumer migration phải có phương án quay lui độc lập với application deployment.

## Ví dụ kế hoạch rollout

| Giai đoạn | Phiên bản mới nhận traffic | Dữ liệu cần xác minh | Quyết định |
|---|---:|---|---|
| Baseline | 0% | Metrics, business ledger, latency, exporter | Chốt mốc tham chiếu |
| Staging | Traffic test | Unit/integration/E2E, workload xác định | Cho phép canary |
| Canary 1 | 1% | Error, latency, series, ground truth | Giữ hoặc rollback |
| Canary 2 | 5–10% | Peak sample, scrape/export, business rate | Tăng hoặc dừng |
| Progressive | 25–50% | So với control và SLO | Tăng hoặc rollback |
| Full rollout | 100% | Dashboard, alert, backend, consumer | Chấp nhận hoặc rollback |
| Stabilization | 100% | Một chu kỳ nghiệp vụ đại diện | Kết thúc giám sát tăng cường |

Tỷ lệ chỉ là ví dụ. Với service ít traffic, canary 1% có thể không đủ mẫu để kết luận; dùng traffic replay hoặc thời gian quan sát dài hơn. Với service có side effect, không replay production request nếu không có cơ chế an toàn.

## Hồ sơ nâng cấp cần lưu

Mỗi lần nâng cấp nên có một báo cáo ngắn với:

- Mục tiêu và phạm vi thay đổi.
- Phiên bản JDK, Spring Boot, Micrometer, registry và Collector.
- Dependency tree trước/sau.
- Metric contract có thay đổi hay không.
- Baseline và nguồn ground truth.
- Test unit, Spring integration, exporter và end-to-end.
- Canary percentage và thời gian giữ từng bước.
- Query so sánh, ngưỡng stop và kết quả.
- Sự cố hoặc sai lệch phát hiện được.
- Quyết định tiếp tục hoặc rollback.
- Artifact/cấu hình cũ và người chịu trách nhiệm.

Báo cáo giúp lần nâng cấp sau có dữ liệu lịch sử thay vì phải suy đoán tại thời điểm sự cố.

## Checklist trước khi bắt đầu rollout

1. Dependency tree thực tế đã được lưu và compatibility matrix đã được xác nhận chưa?
2. Spring Boot có đang quản lý phiên bản Micrometer theo BOM không?
3. Registry, exporter, Collector và backend có nằm trong phạm vi kiểm thử không?
4. Metric contract, unit, tags, histogram và temporality đã được ghi lại chưa?
5. Dashboard, alert, SLO và consumer phụ thuộc đã được kiểm kê chưa?
6. Baseline có đủ traffic và bao phủ chu kỳ nghiệp vụ đại diện không?
7. Ground truth độc lập có thể truy vấn theo test run hoặc time window không?
8. Unit, Spring integration và exporter/E2E tests đã đạt chưa?
9. Canary có phân biệt version mà không tạo tag cardinality không kiểm soát không?
10. Stop threshold và người quyết định rollback đã rõ chưa?
11. Artifact và cấu hình cũ có sẵn để triển khai lại không?
12. Query/alert cũ có thể khôi phục nếu schema migration thất bại không?

## Checklist trong và sau rollout

1. Mỗi bước có đủ traffic và thời gian chờ scrape/export không?
2. Error rate, p95/p99, throughput và saturation có nằm trong ngưỡng không?
3. Counter/Timer có khớp semantics và ground truth không?
4. Gauge có được so với snapshot cùng thời điểm không?
5. Histogram bucket và percentile có được tổng hợp đúng không?
6. Số meter, series và payload có nằm trong ngân sách không?
7. Exporter, Collector, scrape target và backend có khỏe không?
8. Dashboard, alert và SLO có dữ liệu đúng từ version mới không?
9. Dual publish có được kết thúc theo lịch không?
10. Metric cũ có được deprecate sau khi consumer chuyển thành công không?
11. Nếu rollback, traffic, config và consumer có thể quay về trạng thái đã biết tốt không?
12. Báo cáo có ghi lại bằng chứng và thời điểm thay đổi không?

## Kết luận

Nâng cấp Micrometer và pipeline metrics nên được triển khai theo từng phần, có baseline và dữ liệu đối chứng độc lập. Trước khi rollout, kiểm kê dependency, registry, exporter, Collector, backend và consumer; đóng băng metric contract; chạy unit, Spring integration và end-to-end test. Trong rollout, dùng canary/progressive delivery, phân vùng dữ liệu theo version và so sánh count, latency, histogram, cardinality cùng business ground truth.

Nếu metric name, tag, unit hoặc semantics thay đổi, coi đó là migration contract: dual publish có thời hạn, cập nhật dashboard/alert và giữ metric cũ cho đến khi consumer chuyển xong. Chuẩn bị artifact, cấu hình, routing và query cũ trước khi bắt đầu. Khi vượt ngưỡng, dừng rollout, chuyển traffic và cấu hình về bản đã biết tốt, xác minh pipeline hoạt động lại và ghi rõ khoảng dữ liệu bị ảnh hưởng. Cách làm này giúp nâng cấp có bằng chứng, giới hạn phạm vi rủi ro và giữ được khả năng quay lui thực tế.
