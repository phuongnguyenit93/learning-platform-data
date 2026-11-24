# Điều khiển nhóm metric được bật hoặc tắt theo cấu hình ứng dụng

## Vì sao cần điều khiển nhóm metric?

Trong Spring Boot, Micrometer có thể thu thập metrics từ nhiều nguồn: JVM, process, hệ điều hành, HTTP server/client, connection pool, cache, executor và instrumentation nghiệp vụ do ứng dụng tự tạo. Các binder và component này thường đăng ký meter khi application context khởi tạo.

Không phải môi trường nào cũng cần toàn bộ nhóm metrics. Một dịch vụ chạy trong container có thể chỉ cần một phần JVM và HTTP metrics; một worker xử lý batch có thể cần queue depth và thời gian xử lý; môi trường kiểm thử có thể muốn tắt một nhóm instrumentation tốn tài nguyên hoặc không liên quan.

Điều khiển theo cấu hình giúp ứng dụng chọn nhóm metric cần thu thập mà không phải sửa mã nghiệp vụ mỗi lần triển khai. Có ba lớp điều khiển thường dùng:

1. **Cấu hình theo meter name:** dùng thuộc tính Spring Boot như management.metrics.enable để cho phép hoặc từ chối các tên meter cụ thể.
2. **Lọc theo nhóm tên:** dùng MeterFilter để chặn hoặc cho phép một nhóm meter theo prefix.
3. **Điều kiện khởi tạo instrumentation:** dùng ConditionalOnProperty để chỉ tạo binder hoặc component metrics tùy chọn khi cấu hình bật.

Ba cách này tác động ở các thời điểm khác nhau. Cấu hình và filter quyết định meter có được đăng ký trong registry hay không; điều kiện bean quyết định instrumentation có được khởi tạo hay không. Việc ẩn endpoint Actuator là một vấn đề riêng và không đồng nghĩa với việc ngừng thu thập metrics.

## Các nhóm metrics thường gặp trong Spring Boot

Một ứng dụng Spring Boot có thể thu thập nhiều nhóm metrics:

| Nhóm | Ví dụ meter | Mục đích |
|---|---|---|
| JVM | jvm.memory.used, jvm.threads.live, jvm.gc.pause | Theo dõi heap, thread và garbage collection |
| Process | process.cpu.usage, process.files.open | Quan sát tài nguyên của tiến trình |
| System | system.cpu.usage, system.load.average.1m | Quan sát tải hệ điều hành |
| HTTP server | http.server.requests | Đo số lượng và thời lượng request |
| HTTP client | http.client.requests | Theo dõi lời gọi HTTP ra ngoài |
| Executor | executor.active, executor.queued | Theo dõi thread pool và hàng đợi |
| Connection pool | hikaricp.connections.active | Theo dõi pool kết nối |
| Cache | cache.gets, cache.puts, cache.evictions | Theo dõi hiệu quả cache |
| Business | orders.completed, payments.failed | Đo sự kiện nghiệp vụ |

Tên meter cụ thể phụ thuộc binder, thư viện, phiên bản Spring Boot và Micrometer. Trước khi cấu hình bật/tắt, hãy kiểm tra tên thực tế trong registry hoặc endpoint metrics. Không suy ra tên chỉ từ tên nhóm trong bảng.

## Điều khiển theo meter name bằng management.metrics.enable

### Cho phép hoặc từ chối tên meter cụ thể

Spring Boot cung cấp cấu hình management.metrics.enable để điều khiển việc một meter name có được chấp nhận hay không. Có thể đặt các giá trị trong application.yml:

~~~yaml
management:
  metrics:
    enable:
      all: true
      jvm.memory.used: false
      process.cpu.usage: false
~~~

Trong ví dụ, metrics được phép theo mặc định của cấu hình all, nhưng hai meter name được chỉ định bị tắt. Cách này phù hợp khi cần điều khiển một số meter cụ thể mà không chặn toàn bộ nhóm.

Nếu muốn dùng allow-list, có thể bắt đầu bằng all=false rồi bật các meter cần thiết:

~~~yaml
management:
  metrics:
    enable:
      all: false
      http.server.requests: true
      jvm.memory.used: true
      jvm.threads.live: true
~~~

Cách cấu hình này cần được kiểm tra với phiên bản Spring Boot đang dùng và tên meter do instrumentation thực tế đăng ký. Đây là cấu hình theo tên meter; nó không tự hiểu khái niệm nhóm nghiệp vụ của ứng dụng nếu nhóm đó không được biểu diễn bằng tên hoặc filter tương ứng.

### Không nhầm tên meter với tên sau khi xuất

Micrometer registry có thể áp dụng NamingConvention khi ánh xạ meter sang backend. Ví dụ, tên có dấu chấm trong ứng dụng có thể trở thành tên dùng dấu gạch dưới ở Prometheus. Cấu hình management.metrics.enable được đánh giá trên danh tính meter của Micrometer; hãy dùng tên meter trong ứng dụng khi khai báo cấu hình, không sao chép tên đã được exporter chuẩn hóa nếu chúng khác nhau.

Khi tên metric đến từ thư viện bên thứ ba, kiểm tra endpoint Actuator hoặc registry trong môi trường thử nghiệm trước khi viết property. Nếu tên không khớp, cấu hình sẽ không tắt đúng meter dự kiến.

## Dùng MeterFilter để điều khiển cả nhóm theo prefix

### Chặn một nhóm meter

Khi muốn tắt toàn bộ meter có chung prefix, MeterFilter cung cấp các factory method như denyNameStartsWith. Ví dụ, tắt nhóm JVM:

~~~java
@Configuration(proxyBeanMethods = false)
public class MetricsFilterConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.metrics.groups",
        name = "jvm",
        havingValue = "false"
    )
    MeterFilter disableJvmMetrics() {
        return MeterFilter.denyNameStartsWith("jvm.");
    }
}
~~~

Cấu hình ứng dụng:

~~~yaml
app:
  metrics:
    groups:
      jvm: false
~~~

Khi thuộc tính jvm=false, Spring tạo MeterFilter từ chối các meter có tên bắt đầu bằng jvm. Các nhóm khác tiếp tục được đánh giá theo những filter còn lại.

Có thể áp dụng cùng cách cho nhóm meter tùy chỉnh:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "app.metrics.groups",
    name = "legacy",
    havingValue = "false"
)
MeterFilter disableLegacyMetrics() {
    return MeterFilter.denyNameStartsWith("legacy.");
}
~~~

Prefix cần được chọn có chủ đích và không chồng lấn ngoài ý muốn. Nếu nhóm có tên không theo một prefix thống nhất, có thể viết MeterFilter tùy chỉnh để kiểm tra Meter.Id theo tên hoặc tag.

### Chỉ chặn nhóm cần tắt, để các filter khác tiếp tục chạy

MeterFilter có thể trả về các quyết định ACCEPT, DENY hoặc NEUTRAL. NEUTRAL cho phép các filter tiếp theo tiếp tục đánh giá. DENY từ chối meter. ACCEPT có thể kết thúc quá trình xét filter sớm tùy thứ tự áp dụng.

Khi viết filter tùy chỉnh, chỉ nên trả về DENY cho trường hợp thật sự cần chặn; các trường hợp còn lại nên trả về NEUTRAL. Tránh tạo một filter trả ACCEPT cho mọi meter nếu còn filter khác chịu trách nhiệm giới hạn cardinality, chuẩn hóa tag hoặc áp dụng chính sách chung.

Ví dụ filter có điều kiện theo prefix:

~~~java
@Bean
MeterFilter disableDebugMetrics() {
    return new MeterFilter() {
        @Override
        public MeterFilterReply accept(Meter.Id id) {
            if (id.getName().startsWith("debug.")) {
                return MeterFilterReply.DENY;
            }
            return MeterFilterReply.NEUTRAL;
        }
    };
}
~~~

Nếu chỉ cần kiểm tra prefix, factory method denyNameStartsWith ngắn gọn và dễ đọc hơn. Filter tùy chỉnh phù hợp khi chính sách phụ thuộc nhiều điều kiện, chẳng hạn tên và một tag có giá trị xác định.

## Dùng ConditionalOnProperty để không khởi tạo instrumentation

### Bật hoặc tắt một nhóm metrics nghiệp vụ

MeterFilter chặn việc đăng ký meter ở registry, nhưng mã binder hoặc component vẫn có thể được khởi tạo và thực hiện một phần công việc. Với nhóm instrumentation tùy chọn, có thể dùng ConditionalOnProperty để không tạo bean khi nhóm bị tắt.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "app.metrics.groups",
    name = "business",
    havingValue = "true",
    matchIfMissing = true
)
public class BusinessMetricsConfiguration {

    @Bean
    BusinessMetrics businessMetrics(MeterRegistry registry) {
        return new BusinessMetrics(registry);
    }
}
~~~

Cấu hình:

~~~yaml
app:
  metrics:
    groups:
      business: true
~~~

Khi business=true hoặc thuộc tính không được khai báo (do matchIfMissing=true), Spring tạo BusinessMetrics. Khi business=false, bean không được tạo và phần instrumentation do bean này sở hữu không đăng ký meter.

Cách này hữu ích với các binder tự viết, metrics của module nghiệp vụ hoặc instrumentation có chi phí khởi tạo đáng kể. Để điều kiện có tác dụng, bean metrics phải được tạo thông qua cấu hình có điều kiện; không đồng thời đánh dấu chính class đó là Component ở nơi khác khiến nó vẫn được component scan đăng ký độc lập.

### Điều kiện bean khác với MeterFilter

| Cơ chế | Tác động chính | Khi nên dùng |
|---|---|---|
| management.metrics.enable | Cho phép/từ chối meter theo tên | Điều khiển meter cụ thể bằng application configuration |
| MeterFilter | Quyết định meter có được đăng ký trong registry | Chặn nhóm theo prefix, tag hoặc chính sách tùy chỉnh |
| ConditionalOnProperty | Quyết định bean instrumentation có được tạo không | Tắt hẳn binder hoặc nhóm instrumentation do ứng dụng quản lý |
| Endpoint exposure | Quyết định endpoint HTTP có được công bố không | Bảo vệ hoặc ẩn endpoint Actuator khỏi client |

Có thể kết hợp các cơ chế. Ví dụ, ConditionalOnProperty tắt binder nghiệp vụ khi không cần; MeterFilter vẫn là lớp bảo vệ chung cho meter có cardinality bất thường; management.metrics.enable điều khiển một số meter built-in cụ thể.

## Tắt binder built-in và tắt meter được binder tạo ra

Spring Boot có thể tự động cấu hình nhiều MeterBinder khi các dependency và điều kiện phù hợp. Nếu chỉ từ chối meter bằng MeterFilter, binder vẫn có thể được khởi tạo và gọi bindTo; các meter bị từ chối không được đăng ký, nhưng logic khởi tạo binder vẫn tồn tại.

Với binder built-in, trước tiên kiểm tra phiên bản Boot có thuộc tính bật/tắt binder chuyên biệt hay không. Tên property và tập binder được hỗ trợ có thể thay đổi theo phiên bản. Nếu không có property tương ứng, có thể dùng MeterFilter theo tên meter để ngăn nhóm được đăng ký.

Với binder do ứng dụng tự tạo, ưu tiên ConditionalOnProperty trên cấu hình hoặc bean tạo binder. Cách này thể hiện rõ nhóm nào bị tắt và tránh khởi tạo phần instrumentation không cần thiết.

Không nên loại bỏ dependency Actuator chỉ để tắt một nhóm metrics. Actuator còn cung cấp health, info và các endpoint vận hành khác. Hãy điều khiển nhóm metrics ở lớp phù hợp với mục tiêu.

## Tắt metrics không đồng nghĩa ẩn endpoint Prometheus hoặc metrics

Một ứng dụng có thể tiếp tục expose endpoint /actuator/prometheus hoặc endpoint metrics khác ngay cả khi một nhóm meter đã bị từ chối. Endpoint vẫn tồn tại và xuất các meter còn lại.

Ngược lại, ẩn endpoint khỏi HTTP exposure không tự ngừng instrumentation. Meter vẫn có thể được đăng ký và xuất qua một registry push như OTLP hoặc gửi đến backend khác.

Ví dụ, cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Cấu hình này điều khiển các endpoint được expose qua web. Nó không thay thế management.metrics.enable hoặc MeterFilter. Nếu ứng dụng dùng OTLP push, việc không expose endpoint Prometheus cũng không ngăn OTLP registry gửi metrics.

Hãy tách ba câu hỏi:

1. Instrumentation có tạo meter hay không?
2. Registry có chấp nhận và xuất meter hay không?
3. Endpoint HTTP có được expose và cho phép truy cập hay không?

Mỗi câu hỏi có cấu hình và mục tiêu vận hành khác nhau.

## Cấu hình nhiều nhóm trong một ứng dụng

Có thể chuẩn hóa tên nhóm cấu hình để người triển khai dễ bật/tắt theo môi trường:

~~~yaml
app:
  metrics:
    groups:
      jvm: true
      business: true
      diagnostics: false
      experimental: false
~~~

Nhóm business có thể được điều khiển bằng ConditionalOnProperty. Nhóm diagnostics hoặc experimental có thể dùng điều kiện bean tương tự. Nhóm JVM built-in có thể bị chặn bằng MeterFilter khi jvm=false.

Ví dụ cấu hình filter cho JVM:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "app.metrics.groups",
    name = "jvm",
    havingValue = "false"
)
MeterFilter disableJvmMetrics() {
    return MeterFilter.denyNameStartsWith("jvm.");
}
~~~

Ví dụ cấu hình bean cho diagnostics:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "app.metrics.groups",
    name = "diagnostics",
    havingValue = "true"
)
class DiagnosticsMetricsConfiguration {

    @Bean
    DiagnosticsMetrics diagnosticsMetrics(MeterRegistry registry) {
        return new DiagnosticsMetrics(registry);
    }
}
~~~

Các tên nhóm là hợp đồng cấu hình do ứng dụng tự định nghĩa. Spring Boot không tự hiểu app.metrics.groups.jvm hoặc app.metrics.groups.business nếu ứng dụng chưa khai báo điều kiện bean hay filter tương ứng.

## Thời điểm cấu hình được áp dụng

### Cấu hình lúc khởi động

Các property và MeterFilter thường được áp dụng trong quá trình tạo registry và đăng ký meter. Vì vậy, nên quyết định nhóm metrics trước khi các binder hoặc component bắt đầu tạo meter.

Nếu meter đã được đăng ký trước khi filter được áp dụng, thêm filter sau đó không tự động xóa meter đã tồn tại. Tương tự, đổi property trong Environment sau khi ứng dụng chạy không bảo đảm registry tự áp dụng lại filter hoặc loại bỏ meter cũ.

Với Spring Boot thông thường, cách vận hành đơn giản và dễ dự đoán là đặt cấu hình theo profile hoặc biến môi trường rồi khởi động ứng dụng với chính sách metrics mong muốn.

### Thay đổi cấu hình khi ứng dụng đang chạy

Không nên coi management.metrics.enable hoặc một MeterFilter tĩnh là công tắc bật/tắt nóng. Filter được dùng khi meter được đăng ký; nó không tự động quét và gỡ các meter đã tạo.

Nếu cần thay đổi động, phải thiết kế riêng cơ chế quản lý instrumentation và registry. Có thể dùng một component điều phối trạng thái, ngừng ghi vào nhóm tùy chọn, hoặc quản lý remove/re-register meter theo API và lifecycle được kiểm soát. Tuy nhiên, việc gỡ meter có thể tạo khoảng trống dữ liệu hoặc làm chuỗi counter bắt đầu lại. Cần xác định tác động đến dashboard, alert và backend trước khi bật cơ chế này.

Với hầu hết ứng dụng, cấu hình theo profile và restart có kiểm soát là lựa chọn đơn giản hơn cho thay đổi nhóm metric.

## Nhiều MeterRegistry và CompositeMeterRegistry

Một ứng dụng có thể xuất cùng meter đến nhiều backend, ví dụ Prometheus và OTLP. Filter phải được áp dụng ở registry nhận meter. Spring Boot có thể cấu hình registry tự động, nhưng registry tự tạo thủ công cần được cấu hình riêng nếu không đi qua cơ chế auto-configuration đó.

Nếu dùng CompositeMeterRegistry, cần xác minh filter nằm ở registry nào và meter được đăng ký trên composite hay registry thành phần. Không giả định một MeterFilter gắn vào một registry tùy chỉnh sẽ tự động áp dụng cho mọi registry khác trong tiến trình.

Khi cùng một meter được xuất đến nhiều backend, hãy kiểm tra chính sách bật/tắt có nhất quán. Nếu Prometheus nhận meter nhưng OTLP không nhận, có thể hai registry có filter hoặc cấu hình khác nhau. Nếu một registry bị chặn nhưng registry khác vẫn chấp nhận, dashboard giữa các backend sẽ không đồng nhất.

## Kiểm thử cấu hình bật/tắt nhóm metric

### Kiểm tra filter theo prefix

Có thể dùng SimpleMeterRegistry để xác nhận meter trong nhóm bị chặn không xuất hiện:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.config()
    .meterFilter(MeterFilter.denyNameStartsWith("jvm."));

registry.counter("jvm.gc.events").increment();
registry.counter("business.orders.completed").increment();

assertThat(registry.getMeters())
    .extracting(meter -> meter.getId().getName())
    .containsExactly("business.orders.completed");
~~~

Meter bị từ chối thường trả về một meter no-op tương ứng. Mã gọi increment vẫn chạy, nhưng meter không được thêm vào registry và không xuất hiện trong scrape.

### Kiểm tra điều kiện bean

Với Spring Boot test, tạo application context theo hai cấu hình:

- business=true: BusinessMetrics bean tồn tại và meter nghiệp vụ được đăng ký.
- business=false: bean không tồn tại và meter nghiệp vụ do bean đó sở hữu không được tạo.

Không chỉ kiểm tra bean; hãy kiểm tra cả MeterRegistry để xác nhận meter thực tế có hoặc không có. Một bean có thể tồn tại nhưng không đăng ký meter như dự kiến nếu registry hoặc filter khác từ chối.

### Kiểm tra property management.metrics.enable

Kiểm tra property bằng application context test hoặc integration test trên phiên bản Spring Boot thực tế:

1. Đặt all=true và xác nhận meter được phép xuất hiện.
2. Đặt tên meter cụ thể thành false và xác nhận meter bị từ chối.
3. Đặt all=false rồi bật lại meter cần thiết để kiểm tra allow-list.
4. Xác nhận tên property trùng với Meter.Id.getName() trước NamingConvention.
5. Kiểm tra endpoint hoặc exporter để bảo đảm meter bị tắt không xuất hiện.

Các test cần dùng đúng dependency và phiên bản Boot của ứng dụng. Không suy luận kết quả từ một SimpleMeterRegistry thuần nếu property được Spring Boot áp dụng thông qua auto-configuration.

## Theo dõi tác động của việc tắt nhóm

Tắt một nhóm metrics có thể giảm số meter, số time series, bộ nhớ và chi phí ingest. Nhưng nó cũng làm giảm khả năng quan sát. Trước khi tắt, xác định nhóm đó có đang được dashboard, alert hoặc quy trình xử lý sự cố sử dụng hay không.

Một số nguyên tắc thực tế:

- Giữ các meter cốt lõi phục vụ health và SLO.
- Tắt metrics thử nghiệm hoặc chẩn đoán chỉ khi không cần trong môi trường đó.
- Không tắt toàn bộ HTTP metrics nếu chúng là nguồn tính throughput và latency chính.
- Không tắt JVM metrics khi cần điều tra memory leak hoặc GC pressure.
- Ghi lại cấu hình nhóm metrics theo môi trường để giải thích vì sao dashboard khác nhau.
- Sau khi thay đổi, kiểm tra dashboard và alert có đang truy vấn meter đã bị tắt không.

Nếu một metric không xuất hiện, cần xác định nó bị tắt có chủ đích, không được đăng ký, bị MeterFilter từ chối, hay exporter gặp lỗi. Các nguyên nhân này có cách xử lý khác nhau.

## Những sai lầm thường gặp

**Nghĩ rằng ẩn endpoint là tắt metrics.** Endpoint exposure chỉ điều khiển truy cập HTTP; instrumentation và registry có thể vẫn hoạt động.

**Nghĩ rằng MeterFilter dừng toàn bộ binder.** Filter chặn meter registration; binder vẫn có thể được khởi tạo. Dùng ConditionalOnProperty khi cần không tạo instrumentation bean.

**Dùng sai tên metric trong cấu hình.** management.metrics.enable đánh giá tên meter của Micrometer; tên sau khi exporter chuẩn hóa có thể khác.

**Cài filter sau khi meter đã đăng ký.** Filter không tự xóa meter cũ. Cấu hình phải có hiệu lực trước khi binder tạo meter.

**Trả ACCEPT cho mọi meter trong filter tùy chỉnh.** Quyết định ACCEPT có thể khiến filter tiếp theo không được đánh giá. Dùng NEUTRAL cho meter không thuộc nhóm cần chặn.

**Cho rằng property thay đổi sẽ tự cập nhật registry đang chạy.** Cấu hình thường được áp dụng lúc khởi tạo. Thay đổi động cần thiết kế lifecycle riêng.

**Chỉ kiểm tra bean mà không kiểm tra registry.** Bean tồn tại không bảo đảm meter đã được đăng ký hoặc exporter đang gửi dữ liệu.

**Cho rằng một filter tự áp dụng cho mọi registry.** Registry tự tạo có thể nằm ngoài cơ chế cấu hình của Spring Boot. Kiểm tra từng registry và composite.

**Tắt nhóm mà không rà dashboard và alert.** Query có thể trả no data sau khi meter bị tắt. Cần điều chỉnh cảnh báo và tài liệu vận hành cùng lúc.

## Checklist điều khiển nhóm metrics

Trước khi triển khai cấu hình bật/tắt, hãy xác minh:

1. Nhóm metrics cần điều khiển gồm những meter name nào?
2. Có thể dùng management.metrics.enable cho các tên cụ thể không?
3. Nhóm có prefix ổn định để dùng MeterFilter không?
4. Có nên dùng ConditionalOnProperty để không tạo binder hoặc instrumentation bean không?
5. Filter được áp dụng trước khi meter được đăng ký chưa?
6. Filter có trả NEUTRAL cho các meter ngoài phạm vi chặn không?
7. Các registry tùy chỉnh và registry thành phần có nhận cùng chính sách không?
8. Có phân biệt tắt meter với ẩn endpoint Actuator không?
9. Cấu hình có được áp dụng lúc khởi động hay cần cơ chế runtime riêng?
10. Dashboard, alert và SLO có phụ thuộc vào nhóm bị tắt không?
11. Kiểm thử có xác nhận cả bean, registry và dữ liệu exporter không?
12. Có tài liệu hóa khác biệt metrics giữa các môi trường không?

## Kết luận

Spring Boot cho phép điều khiển metrics ở nhiều lớp. management.metrics.enable phù hợp với việc bật/tắt meter theo tên; MeterFilter phù hợp để chặn một nhóm theo prefix hoặc chính sách tùy chỉnh; ConditionalOnProperty phù hợp khi muốn không khởi tạo binder hay instrumentation tùy chọn.

Hãy cấu hình trước khi meter được đăng ký, xác minh filter áp dụng cho đúng registry và phân biệt việc tắt instrumentation với việc ẩn endpoint. Thay đổi cấu hình khi ứng dụng đang chạy không tự động gỡ các meter hiện có, vì vậy cần quản lý lifecycle riêng nếu thực sự cần bật/tắt động. Sau mỗi thay đổi, kiểm thử registry và exporter, đồng thời rà soát dashboard, alert và SLO để tránh mất tín hiệu vận hành quan trọng.
