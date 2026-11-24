# Quy ước tên và tag có thể tùy biến cho thư viện dùng chung

Một thư viện Java dùng chung có thể được tích hợp vào nhiều ứng dụng, mỗi ứng dụng có tên dịch vụ, vùng triển khai và quy ước metrics riêng. Nếu thư viện tự cố định toàn bộ tên meter và tag, các ứng dụng khó điều chỉnh cách phân nhóm dữ liệu; nếu thư viện tự thêm những tag như request ID hoặc URL đầy đủ, cardinality có thể tăng rất nhanh.

`MeterBinder` là điểm tích hợp phù hợp để thư viện đăng ký các meter của mình vào `MeterRegistry` do ứng dụng cung cấp. Thư viện có thể nhận một đối tượng cấu hình quy ước metrics, dùng nó để tạo tên meter và tag, rồi đăng ký gauge, counter, timer hoặc meter khác. Nhờ vậy, thư viện vẫn sở hữu ý nghĩa của phép đo, còn ứng dụng có thể tùy biến cách định danh trong giới hạn đã thiết kế.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, nội dung này kết nối `MeterBinder` với quy tắc đặt tên, tag, tích hợp Spring Boot, kiểm soát cardinality và kiểm thử instrumentation. Cần phân biệt quy ước do thư viện định nghĩa với `NamingConvention` của registry: một bên quyết định tên canonical và tag của meter, bên kia chuyển chúng sang định dạng mà backend yêu cầu.

## 1. Vì sao thư viện dùng chung cần quy ước có thể tùy biến?

Giả sử một thư viện HTTP client được dùng bởi ba ứng dụng: `catalog-service`, `billing-service` và `notification-service`. Thư viện cần đo số kết nối đang hoạt động và thời gian gọi client. Nếu tên và tag được cố định cứng, tất cả ứng dụng có thể tạo cùng tên meter với cách phân nhóm không phù hợp, hoặc không thể phân biệt các client khác nhau.

Một quy ước cho phép ứng dụng cung cấp:

- Prefix tên meter, ví dụ `acme.http.client` hoặc `billing.outbound`.
- Tag định danh thư viện/client, ví dụ `client=catalog-api`.
- Tag môi trường hoặc vùng triển khai nếu chiều đó thực sự cần trong dashboard, ví dụ `region=ap-southeast`.
- Các key tag đã được chuẩn hóa theo quy ước nội bộ, nếu ứng dụng có yêu cầu tương thích.

| Thành phần | Chủ thể quyết định | Ví dụ |
| --- | --- | --- |
| Ý nghĩa phép đo | Thư viện | Số kết nối đang hoạt động, thời gian request |
| Prefix và hậu tố logic của tên | Quy ước cấu hình | `acme.http.client.connections.active` |
| Tag nhận diện thư viện | Ứng dụng hoặc cấu hình thư viện | `client=catalog-api` |
| Tag môi trường/vùng | Ứng dụng triển khai | `region=ap-southeast` |
| Tên export và quy tắc ký tự | Registry/backend | Prometheus có thể đổi dấu chấm thành dấu gạch dưới |

Thư viện nên cung cấp giá trị mặc định có ý nghĩa và cho phép ứng dụng ghi đè. Không nên yêu cầu người dùng thư viện tự xây dựng lại toàn bộ instrumentation chỉ để đổi prefix hoặc tag.

## 2. MeterBinder là ranh giới đăng ký meter

`MeterBinder` là một interface có phương thức `bindTo(MeterRegistry registry)`. Spring Boot Actuator tự động phát hiện các bean triển khai `MeterBinder` và gọi chúng để đăng ký meter vào registry được cấu hình. Với ứng dụng Java không dùng Spring Boot, có thể gọi `bindTo` trực tiếp.

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

public final class ClientPoolMetricsBinder implements MeterBinder {
    private final PoolStats poolStats;
    private final ClientMetricsConvention convention;

    public ClientPoolMetricsBinder(
            PoolStats poolStats,
            ClientMetricsConvention convention) {
        this.poolStats = poolStats;
        this.convention = convention;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        // Đăng ký meter tại đây.
    }
}
```

Binder nhận `MeterRegistry` từ bên ngoài. Thư viện không nên tự tạo `PrometheusMeterRegistry` hoặc một registry cụ thể, vì như vậy sẽ gắn chặt vào backend và khó kiểm thử. Ứng dụng quyết định registry nào được inject; binder chỉ đăng ký meter qua API chung.

Một binder có thể được bind vào nhiều registry, ví dụ khi ứng dụng dùng composite registry. Vì vậy, tránh giữ một trường `Counter` hoặc `Timer` duy nhất được gán lại mỗi lần `bindTo` chạy rồi dùng trường đó cho mọi registry. Với binder chỉ đăng ký gauge dựa trên object trạng thái, mỗi registry sẽ tạo meter riêng trỏ đến cùng nguồn dữ liệu. Với counter/timer cần được cập nhật từ code nghiệp vụ, hãy tổ chức component ghi nhận sao cho handle được lấy từ registry phù hợp, hoặc quản lý handle theo từng registry.

## 3. Tạo đối tượng quy ước tên và tag của thư viện

Thư viện có thể định nghĩa một đối tượng nhỏ để quản lý prefix và tag dùng chung. Ví dụ sau dùng `Tags` của Micrometer để lưu tập tag bất biến:

```java
import io.micrometer.core.instrument.Tags;

public final class ClientMetricsConvention {
    private final String prefix;
    private final Tags commonTags;

    public ClientMetricsConvention(String prefix, Tags commonTags) {
        if (prefix == null || prefix.trim().isEmpty()) {
            throw new IllegalArgumentException("prefix must not be blank");
        }
        String normalizedPrefix = trimDots(prefix.trim());
        if (normalizedPrefix.isEmpty()) {
            throw new IllegalArgumentException("prefix must contain a name");
        }
        this.prefix = normalizedPrefix;
        this.commonTags = commonTags == null ? Tags.empty() : commonTags;
    }

    public String name(String logicalName) {
        if (logicalName == null || logicalName.trim().isEmpty()) {
            throw new IllegalArgumentException("logicalName must not be blank");
        }
        String normalizedName = trimDots(logicalName.trim());
        if (normalizedName.isEmpty()) {
            throw new IllegalArgumentException("logicalName must contain a name");
        }
        return prefix + "." + normalizedName;
    }

    public Tags tags() {
        return commonTags;
    }

    private static String trimDots(String value) {
        int start = 0;
        int end = value.length();
        while (start < end && value.charAt(start) == '.') start++;
        while (end > start && value.charAt(end - 1) == '.') end--;
        return value.substring(start, end);
    }
}
```

Ứng dụng tạo convention theo cấu hình riêng:

```java
ClientMetricsConvention convention = new ClientMetricsConvention(
        "acme.http.client",
        Tags.of(
                "client", "catalog-api",
                "region", "ap-southeast"));
```

Binder dùng `convention.name("connections.active")` để tạo tên canonical `acme.http.client.connections.active`, và dùng `convention.tags()` để gắn tag chung. Nếu một ứng dụng cần prefix khác, nó tạo convention khác mà không phải sửa mã thư viện.

Trong thư viện production, nên kiểm tra thêm tag key không rỗng, tag value không null và không có key trùng nhau. Prefix nên được cấu hình ở startup, không được lấy từ dữ liệu request. Các tên logical do thư viện kiểm soát nên ổn định qua các phiên bản.

## 4. Đăng ký meter bằng convention trong MeterBinder

Ví dụ hoàn chỉnh dưới đây đăng ký hai gauge cho connection pool. `PoolStats` là abstraction do thư viện hoặc adapter của ứng dụng cung cấp:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

public final class ClientPoolMetricsBinder implements MeterBinder {
    private final PoolStats poolStats;
    private final ClientMetricsConvention convention;

    public ClientPoolMetricsBinder(
            PoolStats poolStats,
            ClientMetricsConvention convention) {
        this.poolStats = poolStats;
        this.convention = convention;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder(
                        convention.name("connections.active"),
                        poolStats,
                        PoolStats::activeConnections)
                .description("Current active connections in the client pool")
                .tags(convention.tags())
                .register(registry);

        Gauge.builder(
                        convention.name("connections.max"),
                        poolStats,
                        PoolStats::maxConnections)
                .description("Maximum configured connections in the client pool")
                .tags(convention.tags())
                .register(registry);
    }
}
```

Ví dụ abstraction trạng thái:

```java
public interface PoolStats {
    double activeConnections();
    double maxConnections();
}
```

Gauge giữ tham chiếu đến `poolStats` và đọc giá trị khi registry thu thập metrics. Đối tượng trạng thái phải có vòng đời ít nhất bằng meter và phải được giữ tham chiếu mạnh. Không truyền một object tạm thời rồi để nó bị garbage collector thu hồi.

Các meter đăng ký từ cùng binder dùng chung prefix và tag, nhưng có hậu tố riêng. Nếu muốn bổ sung tag theo từng meter, hãy thêm chúng tại builder và bảo đảm các key không xung đột với tag chung.

## 5. Tùy biến key và value của tag

Một số tổ chức muốn đổi cả tag key. Ví dụ, thư viện mặc định dùng `client`, nhưng nền tảng nội bộ yêu cầu `remote_service`. Có thể để ứng dụng tạo `Tags` với key phù hợp:

```java
Tags applicationTags = Tags.of(
        "remote_service", "catalog-api",
        "deployment_region", "ap-southeast");

ClientMetricsConvention convention = new ClientMetricsConvention(
        "platform.outbound.http",
        applicationTags);
```

Meter được đăng ký theo convention này sẽ dùng prefix `platform.outbound.http` và hai key tag đã cấu hình. Đây là tùy biến ở phía thư viện trước khi đăng ký meter.

Không nên để người dùng thư viện tùy ý cung cấp mọi tag từ mỗi request. Hãy chỉ cho phép thay đổi key/value ở cấp cấu hình ứng dụng và dùng các giá trị ổn định trong suốt vòng đời tiến trình. Nếu cần tag theo operation, hãy định nghĩa tập operation hữu hạn như `get`, `post`, `health-check` thay vì lưu URL đầy đủ hoặc tên method động.

## 6. Tích hợp convention vào Spring Boot

Ứng dụng Spring Boot có thể khai báo convention và binder dưới dạng bean. Spring Boot Actuator sẽ gọi `bindTo` trên binder và truyền registry được auto-configure:

```java
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientMetricsConfiguration {
    @Bean
    ClientMetricsConvention clientMetricsConvention() {
        return new ClientMetricsConvention(
                "acme.http.client",
                Tags.of(
                        "client", "catalog-api",
                        "region", "ap-southeast"));
    }

    @Bean
    MeterBinder clientPoolMetricsBinder(
            PoolStats poolStats,
            ClientMetricsConvention convention) {
        return new ClientPoolMetricsBinder(poolStats, convention);
    }
}
```

Trong ứng dụng thật, giá trị `prefix`, client name và region nên đến từ cấu hình như `@ConfigurationProperties` hoặc environment variables. Không hardcode môi trường triển khai trong thư viện dùng chung. Bean `PoolStats` cần được cung cấp bởi connection pool hoặc adapter tương ứng.

Ví dụ YAML cấu hình ở ứng dụng:

```yaml
observability:
  client:
    metrics:
      prefix: acme.http.client
      client-tag-key: client
      client-name: catalog-api
      region-tag-key: region
      region: ap-southeast
```

Lớp properties của ứng dụng có thể chuyển các giá trị này thành `ClientMetricsConvention`. Thư viện nên cung cấp constructor nhận convention hoặc options object, không tự đọc trực tiếp file cấu hình của từng framework nếu thư viện được thiết kế độc lập với Spring.

## 7. Phân biệt quy ước của thư viện, NamingConvention và MeterFilter

Ba cơ chế này có thể cùng tác động đến tên và tag nhưng nằm ở các lớp khác nhau:

| Cơ chế | Thời điểm/vai trò | Phạm vi tác động |
| --- | --- | --- |
| `ClientMetricsConvention` của thư viện | Trước khi đăng ký meter; tạo tên canonical và tag mà binder sử dụng | Meter do thư viện đó đăng ký |
| `NamingConvention` | Khi registry chuyển tên và tag sang định dạng backend | Quy tắc export của registry, ví dụ đổi dấu chấm thành dấu gạch dưới |
| `MeterFilter` | Trong quá trình đăng ký; có thể từ chối hoặc biến đổi `Meter.Id` | Các meter đi qua registry có gắn filter |

Ví dụ, binder đăng ký tên canonical `acme.http.client.connections.active`. Prometheus registry có thể công bố tên dạng `acme_http_client_connections_active`. Thư viện không cần tự đổi dấu chấm thành dấu gạch dưới; đó là trách nhiệm của registry.

Nếu ứng dụng muốn đổi tag key toàn cục hoặc loại bỏ một nhóm meter, có thể dùng `MeterFilter`. Tuy nhiên, filter được cấu hình ở cấp registry có thể ảnh hưởng đến meter của các thư viện khác. Đối với quy ước riêng của một thư viện, truyền convention vào binder thường dễ kiểm soát và ít gây tác động ngoài ý muốn hơn.

Không nên dùng `NamingConvention` của registry để thay đổi ngữ nghĩa meter. Naming convention chủ yếu chuẩn hóa cú pháp export; nó không phải API cấu hình prefix và tag riêng cho từng thư viện.

## 8. Tránh xung đột tên và tag

Khi nhiều bản sao của một thư viện hoặc nhiều client cùng đăng ký meter, tên và tag phải phân biệt đúng đối tượng được đo. Nếu cùng tên và cùng tập tag, Micrometer sẽ xem đó là cùng meter ID và có thể trả về meter đã tồn tại. Nếu hai nguồn trạng thái khác nhau vô tình dùng chung ID, dashboard sẽ gộp chúng thành một chuỗi dữ liệu.

Ví dụ, hai client khác nhau cần tag phân biệt:

```java
ClientMetricsConvention catalogConvention = new ClientMetricsConvention(
        "acme.http.client",
        Tags.of("client", "catalog-api"));

ClientMetricsConvention billingConvention = new ClientMetricsConvention(
        "acme.http.client",
        Tags.of("client", "billing-api"));
```

Hai meter có cùng tên nhưng khác `client` tag nên là hai meter ID khác nhau. Ngược lại, không nên tạo tên meter chứa client ID động trong từng request; dùng tag ổn định sẽ giúp backend tổng hợp theo chiều client.

Hãy xác định rõ tag chung nào được thêm bởi ứng dụng và tag nào được thêm bởi binder. Tránh lặp cùng key với các giá trị khác nhau. Đối với `commonTags` ở cấp registry, cần phối hợp với tag của binder để không tạo tag trùng hoặc làm meter ID khó dự đoán.

## 9. Kiểm soát cardinality trong thư viện dùng chung

Thư viện được tích hợp vào nhiều ứng dụng nên có thể nhân rộng cardinality của một tag qua nhiều instance. Tag nên đại diện cho chiều phân tích có tập giá trị hữu hạn:

| Tag phù hợp | Tag nên tránh |
| --- | --- |
| `client=catalog-api` | `request_id=...` |
| `region=ap-southeast` | `user_id=...` |
| `operation=get` | `url=/orders/12345` |
| `outcome=success` | `exception_message=...` |
| `pool=primary` | `connection_id=...` |

Thư viện nên tài liệu hóa tag key và vocabulary được phép. Nếu ứng dụng muốn thêm tag tùy chỉnh, hãy giới hạn ở cấu hình startup và xác định rõ số lượng giá trị tối đa. Không cung cấp callback lấy tag từ request mà không có cơ chế chuẩn hóa.

Có thể dùng `MeterFilter.maximumAllowableTags(...)` ở cấp registry như lớp phòng vệ bổ sung. Nhưng giới hạn registry không thay thế hợp đồng tag trong thư viện: người dùng vẫn cần biết tag nào ổn định, tag nào có thể làm số time series tăng nhanh.

## 10. Kiểm thử convention và binder

`SimpleMeterRegistry` phù hợp để xác minh binder đăng ký đúng tên, tag và giá trị gauge. Test có thể tạo hai convention khác nhau để chứng minh cùng một thư viện có thể được cấu hình theo hai ứng dụng:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class ClientPoolMetricsBinderTest {
    @Test
    void registersMetersUsingConfiguredPrefixAndTags() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            AtomicInteger active = new AtomicInteger(3);
            PoolStats stats = new PoolStats() {
                @Override
                public double activeConnections() {
                    return active.get();
                }

                @Override
                public double maxConnections() {
                    return 20;
                }
            };

            ClientMetricsConvention convention = new ClientMetricsConvention(
                    "acme.http.client",
                    Tags.of("client", "catalog-api", "region", "ap-southeast"));

            new ClientPoolMetricsBinder(stats, convention).bindTo(registry);

            double current = registry.get(
                            "acme.http.client.connections.active")
                    .tags("client", "catalog-api", "region", "ap-southeast")
                    .gauge()
                    .value();

            assertThat(current).isEqualTo(3.0);

            active.set(7);

            double updated = registry.get(
                            "acme.http.client.connections.active")
                    .tags("client", "catalog-api", "region", "ap-southeast")
                    .gauge()
                    .value();

            assertThat(updated).isEqualTo(7.0);
        }
    }
}
```

Test này xác minh tên canonical, tag và việc gauge đọc trạng thái mới. Có thể bổ sung test với prefix khác hoặc tag key khác để kiểm tra khả năng tùy biến. Cũng nên xác minh hai client cùng prefix nhưng khác tag tạo ra hai meter ID riêng.

Unit test với `SimpleMeterRegistry` không xác minh tên sau khi registry chuẩn hóa hoặc output backend. Nếu cần kiểm tra Prometheus, thêm integration test với `PrometheusMeterRegistry` hoặc endpoint `/actuator/prometheus`, rồi xác nhận tên export, label và giá trị.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Hardcode prefix và tag trong binder | Ứng dụng không thể tích hợp theo quy ước riêng | Nhận convention/options qua constructor |
| Thư viện tự tạo registry cụ thể | Gắn chặt vào backend và khó kiểm thử | Nhận `MeterRegistry` từ bên ngoài qua `bindTo` |
| Nhầm convention của thư viện với `NamingConvention` | Tên canonical bị trộn với quy tắc export | Tách lớp tạo tên/tag và lớp chuẩn hóa backend |
| Dùng cùng tên và tag cho hai nguồn trạng thái khác nhau | Meter bị gộp ngoài ý muốn | Thêm tag định danh ổn định như client hoặc pool |
| Đưa request ID hoặc URL thô vào tag | Cardinality tăng mạnh | Dùng vocabulary hữu hạn hoặc route template |
| Giữ một Counter/Timer field duy nhất trong binder đa registry | Lần bind sau có thể ghi đè handle của registry trước | Quản lý handle theo registry hoặc tách binder và recorder |
| Gauge tham chiếu object không còn sống | Giá trị gauge không còn đáng tin cậy | Giữ object nguồn trong vòng đời của binder |
| Đổi tag key nhưng không cập nhật dashboard | Truy vấn cũ không còn khớp label | Quản lý thay đổi như một thay đổi hợp đồng metrics |

## 12. Quy trình thiết kế convention cho thư viện

Khi xây dựng một thư viện có instrumentation dùng chung, hãy thực hiện theo trình tự:

1. Xác định những phép đo thư viện cần cung cấp và đặt tên logic ổn định.
2. Chọn meter type phù hợp: gauge cho trạng thái, counter cho sự kiện tích lũy, timer cho thời lượng, summary cho phân phối số.
3. Định nghĩa prefix mặc định và tập tag mặc định có cardinality thấp.
4. Tạo options hoặc convention object để ứng dụng tùy biến prefix, tag key và tag value ở thời điểm khởi động.
5. Triển khai `MeterBinder` nhận convention cùng đối tượng trạng thái; đăng ký meter vào registry được truyền vào.
6. Không phụ thuộc vào registry cụ thể và không tự đọc cấu hình môi trường của ứng dụng trong thư viện lõi.
7. Viết unit test với `SimpleMeterRegistry` cho tên, tag, type và giá trị.
8. Kiểm thử export bằng registry adapter thực tế nếu tên và label backend là một phần của hợp đồng vận hành.
9. Tài liệu hóa tag, vocabulary, cardinality dự kiến và ảnh hưởng khi đổi prefix hoặc key.

`MeterBinder` giúp thư viện đăng ký instrumentation vào registry của ứng dụng mà không sở hữu backend. Một convention object được truyền vào binder cho phép ứng dụng tùy biến tên canonical và tag theo chuẩn nội bộ, trong khi thư viện vẫn giữ nguyên ý nghĩa của các phép đo. Khi tách rõ convention của thư viện, naming convention của registry và chính sách `MeterFilter`, instrumentation dùng chung sẽ dễ tích hợp, kiểm thử và duy trì hơn.
