# Đọc tên và tag thực tế theo phiên bản thay vì suy đoán từ dashboard mẫu

Spring Boot và Micrometer có thể tự đăng ký nhiều meter cho JVM, HTTP server, datasource, cache, executor và logging. Các meter này giúp ứng dụng có số liệu vận hành ngay sau khi tích hợp Actuator và registry phù hợp. Tuy nhiên, tên metric, tag và điều kiện đăng ký phụ thuộc phiên bản Spring Boot, phiên bản Micrometer, thư viện đang dùng, loại server và cấu hình của ứng dụng.

Một dashboard mẫu chỉ là ví dụ về cách trình bày. Không nên lấy nguyên tên series hoặc tag từ dashboard đó rồi giả định ứng dụng hiện tại cũng xuất cùng cấu trúc. Cách đáng tin cậy là xác định dependency đang chạy, liệt kê meter trong registry, kiểm tra Actuator metrics endpoint và đối chiếu dữ liệu export thực tế của backend.

Bài này hướng dẫn cách khám phá metric name và tag từ runtime, phân biệt tên Micrometer với tên đã chuyển đổi khi export, đọc các nhóm built-in metrics phổ biến và xây dựng dashboard dựa trên dữ liệu thực tế của đúng phiên bản.

## 1. Vì sao tên và tag có thể khác giữa các phiên bản?

Built-in metrics không phải một danh sách cố định áp dụng cho mọi ứng dụng Spring Boot. Một meter chỉ xuất hiện khi các điều kiện liên quan được đáp ứng, chẳng hạn:

- Dependency cung cấp binder hoặc instrumentation đã có trên runtime classpath.
- Loại server hoặc thư viện tương ứng đang được sử dụng.
- Thành phần được Spring Boot quản lý hoặc được đăng ký instrumentation đúng cách.
- Meter chưa bị tắt bởi cấu hình hoặc bị loại bởi `MeterFilter`.
- Có hoạt động đủ để tạo meter, ví dụ HTTP request đầu tiên đã đi qua server.

Khi nâng cấp Spring Boot, BOM có thể đưa vào phiên bản Micrometer khác. Các phiên bản framework và thư viện tích hợp có thể thay đổi tên meter, tag, cách chuẩn hóa route hoặc cách export. Cấu hình customizer, observation convention, common tags và MeterFilter của ứng dụng cũng có thể thay đổi cấu trúc cuối cùng.

Vì vậy, cần phân biệt ba nguồn thông tin:

1. **Tài liệu của phiên bản:** cho biết các meter mà phiên bản framework dự kiến cung cấp và điều kiện sử dụng.
2. **MeterRegistry tại runtime:** cho biết meter đã thực sự được đăng ký trong JVM hiện tại.
3. **Backend exposition:** cho biết tên series, nhãn và đơn vị sau khi registry chuyển đổi để export.

Khi dashboard không hiển thị một metric, hãy kiểm tra lần lượt ba nguồn này thay vì lập tức kết luận binder bị lỗi.

## 2. Phân biệt tên meter Micrometer và tên series backend

Micrometer dùng tên metric theo quy ước độc lập với backend, thường dùng dấu chấm để phân tách thành phần:

```text
http.server.requests
jvm.memory.used
process.uptime
```

Khi export, mỗi registry áp dụng `NamingConvention` phù hợp với backend. Ví dụ Prometheus thường chuyển tên có dấu chấm thành dấu gạch dưới và chuẩn hóa đơn vị:

| Tên trong Micrometer | Tên series Prometheus có thể thấy |
|---|---|
| `http.server.requests` | `http_server_requests_seconds_count`, `http_server_requests_seconds_sum` |
| `jvm.memory.used` | `jvm_memory_used_bytes` |
| `process.uptime` | `process_uptime_seconds` |

Đây là ví dụ minh họa quy ước export phổ biến. Tên thực tế phụ thuộc loại meter, base unit, registry và phiên bản. Timer có thể xuất thêm `_max` hoặc `_bucket` khi có histogram; Counter có thể được biểu diễn với hậu tố phù hợp cho counter của backend.

Khi gọi Actuator metrics endpoint, hãy dùng tên meter Micrometer, ví dụ:

```text
/actuator/metrics/http.server.requests
```

Khi viết PromQL, hãy dùng tên series Prometheus thực tế, ví dụ:

```promql
rate(http_server_requests_seconds_count[5m])
```

Không lấy tên Prometheus đã chuyển đổi rồi truyền nguyên vào `/actuator/metrics/{name}`, trừ khi đó cũng chính là tên meter mà registry đăng ký.

## 3. Xác định chính xác phiên bản Spring Boot và Micrometer

Trước khi xây dựng dashboard, xác định phiên bản Spring Boot và phiên bản Micrometer được phân giải trong runtime classpath. Không chỉ dựa vào phiên bản khai báo trực tiếp trong file build vì BOM hoặc dependency management có thể chọn phiên bản khác.

Với Maven, có thể kiểm tra:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot,io.micrometer
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
```

Kiểm tra cả registry đang dùng, ví dụ `micrometer-registry-prometheus`, và các module Micrometer liên quan. Nếu dự án dùng Spring Boot BOM, thông thường nên để BOM quản lý bộ phiên bản Micrometer tương thích.

Có thể ghi phiên bản Spring Boot vào log lúc khởi động:

```java
import org.springframework.boot.SpringBootVersion;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RuntimeVersionInfo {

    private static final Logger log =
        LoggerFactory.getLogger(RuntimeVersionInfo.class);

    public static void logSpringBootVersion() {
        log.info("Spring Boot version: {}", SpringBootVersion.getVersion());
    }
}
```

Thông tin phiên bản giúp đối chiếu đúng tài liệu và release notes. Khi package implementation version không có trong JAR hoặc bị thay đổi bởi cách đóng gói, dependency report vẫn là nguồn xác nhận đáng tin cậy.

## 4. Khám phá meter đã đăng ký qua MeterRegistry

Cách trực tiếp nhất để biết JVM hiện tại đang có những meter nào là duyệt `MeterRegistry`. Mỗi meter có một `Meter.Id` chứa tên, tag, loại, base unit và description.

Ví dụ một bean chẩn đoán trong môi trường phát triển:

```java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.Comparator;

@Component
public class MeterInventory {

    private static final Logger log =
        LoggerFactory.getLogger(MeterInventory.class);

    private final MeterRegistry registry;

    public MeterInventory(MeterRegistry registry) {
        this.registry = registry;
    }

    public void logInventory() {
        registry.getMeters().stream()
            .sorted(Comparator.comparing(
                meter -> meter.getId().getName()
            ))
            .forEach(this::logMeter);
    }

    private void logMeter(Meter meter) {
        Meter.Id id = meter.getId();

        log.info(
            "meter name={}, type={}, baseUnit={}, tags={}, description={}",
            id.getName(),
            id.getType(),
            id.getBaseUnit(),
            id.getTags(),
            id.getDescription()
        );
    }
}
```

Gọi `logInventory()` sau khi ứng dụng đã nhận một lượt traffic đại diện để thấy cả những meter được tạo lười khi có hoạt động. Kết quả chỉ cho biết các meter đã tồn tại tại thời điểm phương thức chạy; nếu gọi ngay lúc khởi động, một số meter HTTP, cache hoặc executor có thể chưa xuất hiện.

Không nên để chức năng dump toàn bộ registry chạy trong production ở mỗi request. Số lượng meter có thể lớn và log có thể chứa nhiều thông tin vận hành. Hãy dùng trong môi trường phát triển, test hoặc một tác vụ chẩn đoán được kiểm soát.

## 5. Khám phá tên và tag bằng Actuator metrics endpoint

Nếu ứng dụng có Spring Boot Actuator, endpoint `metrics` cho phép liệt kê và kiểm tra meter qua HTTP.

Thêm Actuator dependency nếu dự án chưa có:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Expose endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
```

Liệt kê tên meter:

```bash
curl http://localhost:8080/actuator/metrics
```

Kiểm tra một meter:

```bash
curl http://localhost:8080/actuator/metrics/http.server.requests
```

Kết quả có thể chứa các phần:

```json
{
  "name": "http.server.requests",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 42
    },
    {
      "statistic": "TOTAL_TIME",
      "value": 1.27
    },
    {
      "statistic": "MAX",
      "value": 0.18
    }
  ],
  "availableTags": [
    {
      "tag": "method",
      "values": ["GET", "POST"]
    },
    {
      "tag": "status",
      "values": ["200", "404"]
    }
  ]
}
```

Đây là ví dụ cấu trúc minh họa; số measurement, tag key và giá trị phụ thuộc meter cùng phiên bản. Trường `availableTags` cho biết các giá trị tag hiện có mà endpoint tìm thấy, không phải danh sách mọi giá trị có thể xuất hiện trong tương lai.

Có thể lọc theo tag bằng cách truyền một hoặc nhiều tham số `tag`:

```bash
curl "http://localhost:8080/actuator/metrics/http.server.requests?tag=method:GET&tag=status:200"
```

Dùng endpoint này để xác nhận tên canonical và tag trước khi viết truy vấn backend. Trong production, giới hạn quyền truy cập endpoint metrics theo chính sách bảo mật của ứng dụng; thông tin metrics có thể tiết lộ trạng thái nội bộ và lưu lượng hệ thống.

## 6. Kiểm tra tên và tag đã export qua Prometheus

Nếu ứng dụng sử dụng Prometheus registry, thêm dependency runtime tương ứng:

```xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
```

Expose endpoint Prometheus:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
```

Kiểm tra dữ liệu:

```bash
curl http://localhost:8080/actuator/prometheus
```

Tìm metric cần quan sát và ghi lại:

- Tên series chính xác.
- Tên label và tập giá trị đang có.
- Đơn vị của giá trị.
- Các hậu tố như `_count`, `_sum`, `_max`, `_bucket`.
- Có histogram hay chỉ count/total hay không.

Ví dụ, một HTTP Timer có thể xuất:

```text
http_server_requests_seconds_count{method="GET",status="200",...} 42
http_server_requests_seconds_sum{method="GET",status="200",...} 1.27
```

Nếu histogram được bật, có thể có thêm các series `http_server_requests_seconds_bucket` với label `le`. Đừng giả định có bucket chỉ vì dashboard mẫu đang vẽ p95; hãy xác nhận endpoint thực sự xuất bucket.

## 7. Các nhóm built-in metrics thường gặp

Bảng dưới đây là danh sách tham khảo các meter thường gặp trong hệ sinh thái Spring Boot/Micrometer. Đây không phải cam kết rằng mọi ứng dụng đều có tất cả meter hoặc tag trong bảng. Hãy xác minh trên runtime của đúng phiên bản đang chạy.

| Nhóm | Tên meter Micrometer thường gặp | Tag thường gặp | Điều kiện hoặc lưu ý |
|---|---|---|---|
| JVM memory | `jvm.memory.used`, `jvm.memory.committed`, `jvm.memory.max` | `area`, `id` | JVM binder; area thường phân biệt heap và non-heap, id xác định memory pool |
| Garbage collection | `jvm.gc.pause` | `action`, `cause` | Timer ghi nhận pause; tag và cách phân loại phụ thuộc JVM |
| JVM threads | `jvm.threads.live`, `jvm.threads.daemon`, `jvm.threads.peak`, `jvm.threads.states` | `state` với meter theo trạng thái | JVM binder |
| Process | `process.uptime`, `process.start.time`, `process.cpu.usage` | Có thể không có tag hoặc có tag theo binder | Phụ thuộc hệ điều hành và nguồn thông tin process |
| System CPU | `system.cpu.usage`, `system.cpu.count` | Thường không cần tag | Giá trị có thể không khả dụng trên mọi nền tảng |
| HTTP server | `http.server.requests` | Thường gồm `method`, `status`, `outcome`, `exception`, `uri` | Cần server instrumentation; tag có thể thay đổi theo MVC/WebFlux, convention và phiên bản |
| HTTP client | `http.client.requests` | Có thể gồm `clientName`, `method`, `status`, `outcome`, `uri`, `exception` | Phụ thuộc client được instrument và cách tạo request |
| JDBC connections | `jdbc.connections.active`, `jdbc.connections.idle`, `jdbc.connections.max`, `jdbc.connections.min` | Thường có `name` | Phụ thuộc datasource instrumentation |
| HikariCP | `hikaricp.connections.active`, `hikaricp.connections.idle`, `hikaricp.connections.pending`, `hikaricp.connections.max` | Thường có `pool` | Chỉ có khi dùng HikariCP và binder được đăng ký |
| Cache | `cache.gets`, `cache.puts`, `cache.evictions` | Có thể gồm `cache`, `name`, `result` | Phụ thuộc cache provider và thống kê cache được bật |
| Executor | `executor.active`, `executor.queued`, `executor.completed`, `executor.pool.size` | Thường có `name` | Chỉ có với executor được instrument/bind |
| Logback | `logback.events` | `level` | Chỉ có khi ứng dụng dùng Logback và binder tương ứng |

Tên tag trong bảng là gợi ý để điều tra, không phải hợp đồng cố định cho mọi phiên bản. Một số meter có thể được đổi tên bởi filter hoặc có tag bổ sung từ common tags.

## 8. Đọc đúng HTTP server metrics

Meter HTTP server thường là Timer, do đó có thể cung cấp count, total time, max và histogram tùy cấu hình. Tên canonical thường gặp là `http.server.requests`.

Các tag thường hữu ích:

- `method`: phương thức HTTP như GET hoặc POST.
- `status`: mã trạng thái HTTP.
- `outcome`: nhóm kết quả như SUCCESS, CLIENT_ERROR hoặc SERVER_ERROR.
- `exception`: loại exception hoặc giá trị thể hiện không có exception.
- `uri`: route template hoặc đường dẫn đã chuẩn hóa.

Không nên giả định `uri` luôn là URL nguyên bản. Instrumentation web thường cố gắng dùng route template để tránh cardinality cao. Request không được ánh xạ route có thể được biểu diễn bằng giá trị đặc biệt hoặc cách xử lý riêng tùy framework/version.

Để xác minh, gửi một số request đại diện:

1. Một request thành công.
2. Một request trả về 4xx.
3. Một request trả về 5xx nếu môi trường test cho phép.
4. Một request đến route có path variable, ví dụ `/orders/123`.

Sau đó kiểm tra `availableTags` của Actuator và series trên endpoint Prometheus. Nếu thấy mỗi ID đơn hàng tạo một giá trị `uri` riêng, hãy điều tra route convention và custom instrumentation trước khi đưa metric vào production.

## 9. Đọc JVM và process metrics

JVM metrics thường giúp trả lời các câu hỏi về heap, memory pool, garbage collection và threads.

Ví dụ:

- `jvm.memory.used`: lượng bộ nhớ đang được sử dụng ở một memory area/pool.
- `jvm.memory.max`: giới hạn tối đa nếu JVM hoặc pool cung cấp giá trị.
- `jvm.gc.pause`: thời lượng các lần pause GC được ghi nhận.
- `jvm.threads.live`: số thread đang sống tại thời điểm lấy mẫu.
- `process.uptime`: thời gian process đã chạy.
- `process.cpu.usage`: tỷ lệ CPU của process nếu nền tảng cung cấp.

Khi đọc memory metrics, không cộng mọi pool tùy tiện rồi so với heap max mà không hiểu pool có thể thay đổi hoặc có cách phân bổ khác nhau. Dùng tag `area` và `id` để phân biệt memory area và pool. Khi so sánh các môi trường, bảo đảm cùng cách tổng hợp và cùng đơn vị.

Một metric không có giá trị hữu ích trên hệ điều hành hiện tại không nhất thiết có nghĩa toàn bộ binder bị lỗi. Một số thông tin process/system phụ thuộc khả năng mà JVM và OS cung cấp.

## 10. Đọc datasource và connection pool metrics

Datasource metrics giúp theo dõi kết nối đang hoạt động, đang rảnh và giới hạn pool. Tên meter phụ thuộc binder datasource và connection pool.

Với HikariCP, các meter thường gặp có prefix `hikaricp.connections`, ví dụ:

- `hikaricp.connections.active`: kết nối đang được sử dụng.
- `hikaricp.connections.idle`: kết nối đang rảnh.
- `hikaricp.connections.pending`: số luồng đang chờ lấy connection.
- `hikaricp.connections.max`: giới hạn connection tối đa.

Tag `pool` thường phân biệt pool. Nếu ứng dụng có nhiều datasource, hãy kiểm tra tag và giá trị thực tế trước khi tổng hợp.

Không nên chỉ nhìn `active` mà kết luận pool thiếu kết nối. Hãy đối chiếu `pending`, `max`, thời gian chờ lấy connection và request latency. Một pool có active cao nhưng không có pending có thể vẫn đang hoạt động bình thường.

## 11. Đọc cache và executor metrics

Cache metrics chỉ xuất hiện nếu cache implementation hỗ trợ thống kê và được cấu hình để Micrometer quan sát. Các meter như `cache.gets` có thể phân biệt kết quả hit/miss bằng tag `result`, trong khi tag `cache` hoặc `name` xác định cache cụ thể.

Executor metrics cần được bind vào executor được quản lý hoặc được instrument. Các meter như `executor.active`, `executor.queued` và `executor.completed` có thể giúp phát hiện queue tăng hoặc pool bão hòa. Tag `name` thường dùng để phân biệt executor.

Nếu không thấy các meter này, kiểm tra:

- Cache provider có hỗ trợ thống kê không.
- Cache stats có được bật không.
- Executor có được Spring quản lý và binder có được đăng ký không.
- Meter đã được tạo chưa, ví dụ có hoạt động cache hoặc task tương ứng.
- Filter hoặc cấu hình enable/deny có loại meter không.

## 12. Vì sao dashboard mẫu có thể không khớp ứng dụng?

Một dashboard được xây dựng cho hệ thống khác có thể giả định:

- Tên metric của một phiên bản Spring Boot cụ thể.
- Registry Prometheus và naming convention nhất định.
- Tag key do một observation convention tùy chỉnh thêm.
- Histogram đã được bật.
- Một loại datasource, cache hoặc servlet container cụ thể.
- Common tags như `application`, `service`, `cluster` hoặc `environment`.

Nếu ứng dụng hiện tại không đáp ứng các giả định đó, panel có thể trống hoặc truy vấn chỉ lấy một phần dữ liệu. Không nên thêm tag giả vào metric chỉ để làm dashboard mẫu hoạt động. Hãy sửa truy vấn theo schema runtime hoặc thống nhất instrumentation nếu dashboard là chuẩn chung của tổ chức.

Một quy trình đối chiếu:

| Bước | Nguồn | Câu hỏi cần trả lời |
|---|---|---|
| 1 | Dependency tree | Spring Boot và Micrometer phiên bản nào đang chạy? |
| 2 | Tài liệu đúng phiên bản | Binder và metric đó có được phiên bản hỗ trợ không? |
| 3 | `/actuator/metrics` | Tên canonical và available tags hiện tại là gì? |
| 4 | `/actuator/prometheus` | Tên series, label và unit thực tế là gì? |
| 5 | PromQL | Truy vấn có giữ đúng tag và đơn vị không? |
| 6 | Dashboard | Panel đang giả định metric schema nào? |

## 13. Common tags, MeterFilter và convention có thể thay đổi kết quả

Ngay cả khi framework tạo meter với tên/tag mặc định, ứng dụng có thể sửa chúng qua cấu hình.

- `MeterRegistryCustomizer` có thể thêm common tags hoặc cấu hình registry.
- `MeterFilter` có thể đổi tên, bỏ tag, chuẩn hóa tag value hoặc deny meter.
- Observation convention có thể thay đổi tag được tạo cho HTTP/client/server observation.
- Naming convention của registry chuyển tên và đơn vị khi export.

Ví dụ common tags:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonTags() {
        return registry -> registry.config().commonTags(
            "service", "order-service",
            "environment", "staging"
        );
    }
}
```

Các tag chung có thể xuất hiện trên mọi meter, kể cả built-in metrics. Vì vậy, danh sách tag nhìn thấy trên endpoint runtime có thể nhiều hơn danh sách tag được tài liệu binder mô tả.

Khi kiểm tra dashboard, hãy so sánh toàn bộ label set sau khi customizer và filter đã áp dụng. Không nên dựa trên danh sách tag mặc định trong tài liệu rồi bỏ qua cấu hình riêng của ứng dụng.

## 14. Kiểm tra một meter có tồn tại nhưng không có dữ liệu

Có ba tình huống khác nhau:

1. **Meter chưa được đăng ký:** tên không xuất hiện trong Actuator metrics endpoint hoặc registry inventory.
2. **Meter đã được đăng ký nhưng chưa có quan sát:** meter tồn tại, nhưng count có thể bằng 0 hoặc chưa có mẫu phù hợp.
3. **Meter đã export nhưng truy vấn sai:** series tồn tại trong backend nhưng dashboard dùng sai tên, label, unit hoặc cửa sổ thời gian.

Đối với HTTP request metrics, gửi request trước rồi kiểm tra. Đối với cache, thực hiện get/put; đối với executor, chạy task; đối với datasource, thực hiện truy vấn. Một số binder tạo meter ngay khi khởi động, một số meter chỉ xuất hiện sau khi thành phần được sử dụng.

Khi truy vấn Prometheus, phân biệt series chưa từng tồn tại với series hiện có nhưng giá trị bằng 0. Hai trường hợp này cần cách xử lý khác nhau trong dashboard và alert.

## 15. Kiểm soát tag cardinality khi khám phá built-in metrics

Trong lúc khám phá, cần xem không chỉ tag key mà cả số lượng giá trị của mỗi tag. Một tag có tập giá trị lớn có thể tạo nhiều time series.

Các tag thường có tập giá trị hữu hạn:

- HTTP method.
- HTTP status hoặc outcome.
- JVM memory area và memory pool.
- Connection pool name.
- Executor name.
- Cache name.

Các giá trị cần xem xét kỹ:

- URL đầy đủ có ID động.
- Request ID hoặc trace ID.
- User ID hoặc tenant ID có số lượng rất lớn.
- Tên exception chứa nội dung động.
- Tên file hoặc query SQL có giá trị thay đổi liên tục.

Dùng `availableTags` để xem tập giá trị đang có và dùng backend để theo dõi số series. Nếu cần phân tích theo một chiều có cardinality cao, hãy cân nhắc log, trace hoặc một cơ chế analytics phù hợp thay vì biến mọi giá trị thành metric tag.

## 16. Quy trình lập inventory metric cho một ứng dụng

Có thể áp dụng quy trình sau mỗi khi nâng cấp Spring Boot, Micrometer hoặc thay đổi instrumentation:

1. Ghi nhận phiên bản Spring Boot, Micrometer core và registry đang chạy.
2. Liệt kê meter qua `MeterRegistry.getMeters()` sau khi ứng dụng khởi động và sau một lượt traffic đại diện.
3. Lấy danh sách tên bằng `/actuator/metrics`.
4. Với từng meter quan trọng, đọc `measurements` và `availableTags`.
5. Kiểm tra tên series và label đã export qua endpoint backend.
6. Ghi lại loại meter, đơn vị, tag keys và ví dụ giá trị.
7. Đối chiếu dashboard/alert hiện tại với inventory mới.
8. Kiểm tra cardinality và các filter/customizer đang tác động.
9. Cập nhật truy vấn và kiểm thử dashboard bằng dữ liệu thực tế.

Một inventory có thể lưu trong tài liệu vận hành của dự án, kèm phiên bản ứng dụng và ngày kiểm tra. Khi nâng cấp, so sánh inventory trước và sau để phát hiện thay đổi schema metrics.

## 17. Mẫu bảng inventory

Dùng bảng sau để ghi lại những meter thật sự quan trọng đối với dịch vụ:

| Trường | Ví dụ |
|---|---|
| Spring Boot version | Phiên bản lấy từ dependency runtime |
| Micrometer version | Phiên bản `micrometer-core` đã phân giải |
| Registry | Prometheus, JMX hoặc registry khác |
| Meter name | `http.server.requests` |
| Meter type | Timer |
| Base unit | seconds |
| Tag keys | method, status, outcome, uri, exception |
| Exported series | `http_server_requests_seconds_count`, `_sum` |
| Histogram | Bật/tắt; các bucket thực tế |
| Cardinality | Số tổ hợp tag quan sát được |
| Source | JVM binder, HTTP server observation, datasource binder... |
| Verified at | Thời điểm inventory được xác minh |

Không sao chép ví dụ vào inventory nếu chưa xác nhận trong ứng dụng. Ghi rõ những meter chưa xuất hiện hoặc chưa có dữ liệu để tránh người khác hiểu nhầm rằng chúng đã được triển khai.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Dashboard không có dữ liệu | Dùng tên backend khác với tên canonical hoặc sai label | Kiểm tra cả Actuator và endpoint export |
| `/actuator/metrics` không có meter | Binder/dependency chưa có, chưa có hoạt động hoặc meter bị deny | Kiểm tra runtime classpath, điều kiện binder và traffic |
| Actuator có meter nhưng Prometheus không có series | Registry chưa có, endpoint chưa expose hoặc meter bị filter ở registry | Kiểm tra dependency registry, cấu hình endpoint và exposition |
| Tag khác dashboard mẫu | Khác Boot/Micrometer version hoặc custom convention/filter | Đọc availableTags và meter ID thực tế |
| Truy vấn p95 không có kết quả | Histogram chưa bật hoặc tên bucket sai | Kiểm tra series `_bucket` và cấu hình distribution |
| Có quá nhiều series | Tag cardinality cao hoặc histogram nhiều bucket | Chuẩn hóa tag và chỉ bật histogram khi cần |
| Một số meter không xuất hiện ở OS cụ thể | Binder không lấy được thông tin nền tảng | Kiểm tra khả năng JVM/OS và tài liệu đúng phiên bản |
| Sau nâng cấp dashboard bị trống | Tên, tag, unit hoặc naming convention đã đổi | So sánh inventory trước/sau nâng cấp |

## 19. Checklist trước khi tin vào dashboard mẫu

- [ ] Xác nhận phiên bản Spring Boot và Micrometer đã phân giải.
- [ ] Xác nhận registry và exporter đang có trong runtime classpath.
- [ ] Liệt kê meter thực tế qua MeterRegistry hoặc Actuator.
- [ ] Dùng tên canonical của Micrometer khi gọi Actuator metrics endpoint.
- [ ] Dùng tên series thực tế đã export khi viết PromQL.
- [ ] Kiểm tra tag keys và giá trị qua `availableTags` hoặc exposition.
- [ ] Xác nhận unit, meter type và các hậu tố export.
- [ ] Gửi traffic hoặc hoạt động đại diện trước khi kết luận meter không tồn tại.
- [ ] Kiểm tra common tags, MeterFilter và observation convention.
- [ ] Xác nhận histogram thực sự được export trước khi truy vấn percentile.
- [ ] Đánh giá cardinality và tránh tag định danh duy nhất.
- [ ] Đối chiếu tài liệu đúng phiên bản sau mỗi lần nâng cấp.

Built-in metrics giúp Spring Boot và Micrometer cung cấp dữ liệu vận hành cho JVM, HTTP, datasource, cache, executor và nhiều thành phần khác. Nhưng tên và tag cần được xác nhận theo đúng phiên bản cùng cấu hình runtime. Hãy dùng dependency report để biết phiên bản, MeterRegistry và Actuator để khám phá meter canonical, rồi kiểm tra endpoint export để xây dashboard theo schema thực tế. Cách làm này giúp tránh dashboard trống, truy vấn sai đơn vị và cardinality tăng ngoài dự kiến.

## Tài liệu tham khảo

- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — cách Spring Boot cấu hình và expose metrics.
- [Spring Boot Metrics and Supported Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html#actuator.metrics.supported) — các nhóm metrics được hỗ trợ và điều kiện tích hợp.
- [Micrometer MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html) — cách truy cập và quản lý meter trong registry.
- [Micrometer Naming Conventions](https://docs.micrometer.io/micrometer/reference/concepts/naming.html) — quy ước tên và chuyển đổi theo backend.
- [Prometheus Registry for Micrometer](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html) — cách export metrics sang Prometheus.

