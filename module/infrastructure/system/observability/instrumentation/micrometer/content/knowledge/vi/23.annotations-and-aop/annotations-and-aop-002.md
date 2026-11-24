# @Timed và cấu hình TimedAspect khi framework chưa cung cấp hỗ trợ

Micrometer cung cấp annotation `@Timed` để khai báo một phương thức cần đo thời gian thực thi. Annotation mô tả tên metric, description, tag bổ sung và tùy chọn histogram. Nó không tự thực thi phép đo: một aspect phải phát hiện annotation, bao quanh lời gọi phương thức và ghi thời lượng vào `MeterRegistry`.

Trong Spring, `TimedAspect` là thành phần AOP của Micrometer thực hiện công việc đó. Khi ứng dụng chưa có cấu hình tự động cung cấp aspect, hãy đăng ký một bean `TimedAspect` và bảo đảm Spring AOP được bật. Cũng cần hiểu giới hạn proxy: lời gọi nội bộ trong cùng object thường không đi qua proxy, nên annotation có thể không được áp dụng dù đã có trên method.

## 1. @Timed khai báo phép đo như thế nào?

`@Timed` thuộc package `io.micrometer.core.annotation`. Có thể đặt annotation trên method để khai báo một Timer cho thời gian thực thi của method đó.

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    @Timed(
        value = "catalog.product.lookup",
        description = "Thời gian tìm kiếm sản phẩm trong catalog"
    )
    public Product findProduct(String productId) {
        return repository.findById(productId)
            .orElseThrow(ProductNotFoundException::new);
    }
}
~~~

Các thành phần chính:

- `value`: tên metric được đăng ký.
- `description`: mô tả ý nghĩa của Timer.
- `extraTags`: các cặp tag key/value tĩnh bổ sung.
- `histogram`: yêu cầu cấu hình histogram cho phân phối thời gian.
- `percentiles`: yêu cầu percentile cục bộ nếu implementation hỗ trợ và được cấu hình tương ứng.
- `serviceLevelObjectives`: các ngưỡng thời lượng cần theo dõi khi registry hỗ trợ.

Không nên dùng tên metric hoặc tag value thay đổi theo từng lần gọi. Một annotation có thể được thực thi hàng triệu lần; tên và tag cần ổn định để registry tái sử dụng cùng meter.

Ví dụ thêm tag có cardinality thấp:

~~~java
@Timed(
    value = "catalog.product.lookup",
    description = "Thời gian tìm kiếm sản phẩm",
    extraTags = {"operation", "lookup", "component", "catalog"},
    histogram = true
)
public Product findProduct(String productId) {
    return repository.findById(productId)
        .orElseThrow(ProductNotFoundException::new);
}
~~~

Ở đây các tag được cố định trong code. Không đưa productId, userId, requestId hoặc giá trị đầu vào tùy ý vào extraTags. Các giá trị đó có thể tạo một time series mới cho mỗi request và làm cardinality tăng rất nhanh.

## 2. @Timed cần TimedAspect để thực thi

Annotation chỉ là metadata. Nếu không có thành phần đọc annotation và bao quanh lời gọi, method vẫn chạy bình thường nhưng Timer có thể không được tạo.

Micrometer cung cấp `TimedAspect` trong package `io.micrometer.core.aop`. Aspect này nhận `MeterRegistry` và xử lý các method được đánh dấu `@Timed`.

Trong ứng dụng Spring, có thể đăng ký bean:

~~~java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsAopConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Khi Spring tạo bean `TimedAspect`, các method phù hợp có thể được đo qua AOP proxy. Registry được inject từ Spring Boot Actuator hoặc cấu hình Micrometer của ứng dụng.

Chỉ nên có một `TimedAspect` áp dụng cho cùng nhóm method. Nếu tự khai báo bean trong khi framework hoặc thư viện khác đã cung cấp aspect tương đương, hãy kiểm tra application context để tránh đo trùng hoặc đăng ký nhiều aspect cho cùng pointcut.

## 3. Dependency cần thiết trong Spring Boot

Một cấu hình Gradle thường dùng:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-aop")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Vai trò:

- `spring-boot-starter-actuator` cung cấp tích hợp Actuator và Micrometer trong ứng dụng Spring Boot.
- `spring-boot-starter-aop` cung cấp Spring AOP và các thành phần AspectJ cần cho proxy-based aspect.
- `micrometer-registry-prometheus` cung cấp registry xuất dữ liệu cho Prometheus.

Phiên bản Spring Boot quản lý phiên bản Micrometer tương thích thông qua dependency management. Không tự ghim một phiên bản `micrometer-core` hoặc registry khác BOM nếu chưa kiểm tra tương thích.

Không phải mọi framework hoặc cấu hình Spring Boot đều tự tạo `TimedAspect`. Hãy kiểm tra application context và cấu hình đang dùng. Nếu chưa có bean, khai báo bean như phần trước. Nếu đã có hỗ trợ tương đương, không đăng ký thêm một aspect thứ hai.

## 4. Cấu hình AOP và cơ chế proxy

Spring AOP thường áp dụng advice bằng proxy. Khi một bean được inject vào bean khác, đối tượng nhận được có thể là proxy bao quanh target object. Lời gọi đi qua proxy mới có cơ hội được aspect xử lý.

Luồng gọi:

~~~text
Controller / caller
        |
        v
Spring AOP proxy
        |
        | tìm @Timed và áp dụng advice
        v
TimedAspect
        |
        | bắt đầu đo
        v
Target method
        |
        | hoàn tất hoặc ném exception
        v
TimedAspect ghi Timer
        |
        v
MeterRegistry
~~~

Khi dùng Spring Boot starter AOP, auto-configuration thường bật cơ chế proxy cần thiết. Trong ứng dụng Spring cấu hình thủ công, có thể cần bật AOP proxy bằng cấu hình phù hợp, chẳng hạn `@EnableAspectJAutoProxy`. Không thêm annotation này một cách máy móc nếu starter hoặc cấu hình hiện tại đã bật proxy.

### Self-invocation không đi qua proxy

Một giới hạn quan trọng của proxy-based AOP là lời gọi method từ method khác trong cùng object thường gọi trực tiếp qua `this`, không đi qua proxy.

~~~java
@Service
public class CatalogService {

    public void refreshCatalog() {
        // Lời gọi nội bộ, không đi qua Spring proxy.
        rebuildIndex();
    }

    @Timed("catalog.index.rebuild")
    public void rebuildIndex() {
        // Công việc xây dựng lại index.
    }
}
~~~

Nếu refreshCatalog() gọi rebuildIndex() nội bộ, `TimedAspect` thường không nhìn thấy lời gọi rebuildIndex(). Annotation vẫn nằm trên method nhưng advice không được kích hoạt.

Cách xử lý:

- Chuyển method cần đo sang một Spring bean khác và inject bean đó.
- Gọi method qua proxy từ một bean khác.
- Dùng instrumentation thủ công bằng Timer nếu ranh giới đo không phù hợp với proxy.
- Chọn weaving hoặc cơ chế AOP khác nếu ứng dụng thật sự cần intercept self-invocation.

Không tự inject bean vào chính nó chỉ để lách self-invocation nếu có thể tách trách nhiệm thành một service rõ ràng hơn.

### Visibility và method final

Proxy dựa trên interface chỉ intercept các method được gọi qua interface proxy. Proxy dựa trên subclass không thể override method final hoặc private. Vì vậy, method cần đo nên có visibility và cấu trúc phù hợp với loại proxy đang dùng.

Nếu annotation không tạo metric, hãy kiểm tra cách bean được proxy hóa, method có được gọi qua proxy không và method có bị giới hạn bởi final/private hay không.

## 5. Đặt tên Timer và chọn tag ổn định

Tên Timer nên mô tả thao tác nghiệp vụ hoặc kỹ thuật rõ ràng, ví dụ:

- `catalog.product.lookup`
- `payment.authorization`
- `inventory.reservation`
- `report.export`

Tag bổ sung phù hợp với các chiều có tập giá trị nhỏ:

~~~java
@Timed(
    value = "payment.authorization",
    extraTags = {"provider", "primary", "operation", "authorize"}
)
public AuthorizationResult authorize(Payment payment) {
    return gateway.authorize(payment);
}
~~~

Nếu cần phân biệt provider theo một tập nhà cung cấp được cấu hình trước, tag provider có thể hữu ích. Nếu giá trị provider đến từ input tự do hoặc có thể tăng không giới hạn, cần chuẩn hóa nó trước khi dùng làm tag.

Tránh:

~~~java
@Timed(
    value = "payment.authorization",
    extraTags = {"payment_id", "dynamic-value"}
)
~~~

Tag payment_id làm mỗi payment có thể tạo một series riêng. Metrics phù hợp để quan sát tổng thể và phân nhóm hữu hạn; dùng tracing hoặc log có kiểm soát cho dữ liệu định danh từng request.

## 6. Histogram, percentile và SLO trên @Timed

`@Timed` có thể khai báo một số cấu hình phân phối để Timer tạo dữ liệu phù hợp với câu hỏi vận hành.

~~~java
@Timed(
    value = "catalog.search",
    description = "Thời gian tìm kiếm catalog",
    histogram = true,
    percentiles = {0.5, 0.9, 0.95, 0.99},
    serviceLevelObjectives = {"100ms", "300ms", "1s"}
)
public SearchResult search(SearchCriteria criteria) {
    return searchService.search(criteria);
}
~~~

Ý nghĩa:

- Histogram xuất các bucket để backend có thể tổng hợp phân phối.
- Percentile là các quantile được tính tại registry/process khi implementation hỗ trợ.
- SLO là các ranh giới thời lượng cụ thể để đếm tỷ lệ quan sát nằm trong ngưỡng.

Percentile cục bộ của từng instance không thể được cộng hoặc lấy trung bình để tạo percentile chính xác toàn hệ thống. Nếu cần p95/p99 tổng hợp nhiều instance trên Prometheus, hãy cấu hình histogram phù hợp và tính quantile từ bucket ở backend.

Cấu hình trong annotation cần tương thích với registry và phiên bản Micrometer đang dùng. Nếu đã có chính sách phân phối tập trung qua MeterFilter hoặc Spring Boot properties, tránh cấu hình mâu thuẫn giữa annotation và registry.

Không bật histogram và nhiều percentile cho mọi method theo mặc định. Mỗi histogram có thể tạo nhiều bucket series trên mỗi tổ hợp tag; chỉ bật khi có nhu cầu phân tích phân phối rõ ràng.

## 7. Đo method ném exception

Thời gian thực thi vẫn có ý nghĩa khi method kết thúc bằng exception. Khi aspect bao quanh lời gọi, nó có thể ghi nhận thời lượng của lần gọi lỗi trước khi exception được truyền lại cho caller.

Ví dụ:

~~~java
@Timed(
    value = "catalog.product.lookup",
    description = "Thời gian tìm kiếm sản phẩm"
)
public Product findProduct(String id) {
    return repository.findById(id)
        .orElseThrow(ProductNotFoundException::new);
}
~~~

Hãy kiểm tra hành vi cụ thể của phiên bản Micrometer và aspect đang sử dụng, đặc biệt các tag exception hoặc cách phân biệt kết quả thành công/thất bại. Nếu cần một chiều outcome rõ ràng, có thể dùng meter riêng hoặc instrumentation thủ công với tag hữu hạn như success, not_found, failure.

Không đưa message exception vào tag. Message thường chứa ID hoặc dữ liệu đầu vào và có thể có vô hạn giá trị.

## 8. Phân biệt @Timed với metrics tự động của Spring Boot

Spring Boot Actuator và Micrometer có thể tự động ghi nhận metrics cho các thành phần framework như HTTP server requests, JVM, process, datasource hoặc cache khi các binder tương ứng được cấu hình.

Ví dụ, HTTP server metrics có thể đo thời gian request mà không cần đặt `@Timed` lên từng controller method. Metric HTTP server thường phản ánh vòng đời request ở tầng web.

`@Timed` hữu ích khi muốn đo một thao tác cụ thể trong domain hoặc service layer, ví dụ:

- Thời gian tính giá đơn hàng.
- Thời gian gọi một bước xử lý thanh toán.
- Thời gian xây dựng báo cáo.
- Thời gian tìm kiếm hoặc cập nhật index.

Không đặt @Timed lên mọi method chỉ vì có thể. Nhiều method nhỏ lồng nhau có thể tạo ra nhiều Timer trùng lặp về mặt ý nghĩa và làm khó đọc dashboard. Chọn ranh giới đo đại diện cho một hoạt động có ý nghĩa vận hành.

## 9. Đo tác vụ bất đồng bộ

Với method trả về future hoặc kiểu reactive, cần xác định thời gian muốn đo là thời gian tạo đối tượng kết quả hay thời gian hoàn tất công việc bất đồng bộ.

~~~java
@Timed("report.export")
public CompletableFuture<Report> exportAsync(ReportRequest request) {
    return CompletableFuture.supplyAsync(
        () -> reportExporter.export(request),
        exportExecutor
    );
}
~~~

Không giả định mọi phiên bản aspect đều đo cùng một cách cho mọi kiểu return. Hỗ trợ hoàn tất asynchronous phụ thuộc phiên bản Micrometer và loại abstraction. Hãy kiểm tra tài liệu phiên bản đang dùng và viết integration test xác minh Timer chỉ dừng ở thời điểm mong muốn.

Nếu cần kiểm soát chính xác vòng đời, có thể dùng Timer.Sample và dừng khi future hoàn tất:

~~~java
import io.micrometer.core.instrument.Timer;

Timer.Sample sample = Timer.start(registry);

return CompletableFuture.supplyAsync(
        () -> reportExporter.export(request),
        exportExecutor
    )
    .whenComplete((result, error) ->
        sample.stop(registry.timer("report.export"))
    );
~~~

Trong ví dụ, thời gian được đo từ trước khi submit cho đến khi future hoàn tất, bao gồm cả thời gian chờ executor. Nếu chỉ muốn đo thời gian xử lý trên worker, hãy bắt đầu Sample bên trong supplier. Chọn ranh giới đo theo câu hỏi cần trả lời.

## 10. Khi nào nên dùng Timer thủ công?

Annotation phù hợp khi ranh giới đo trùng với lời gọi method và metadata tĩnh. Timer thủ công phù hợp hơn khi:

- Chỉ đo một đoạn bên trong method.
- Cần tag outcome được xác định sau khi xử lý.
- Cần đo từ thời điểm submit đến khi async hoàn tất hoặc chỉ thời gian worker chạy.
- Cần điều khiển chính xác exception và nhánh kết thúc.
- Cần gộp nhiều method vào một thao tác nghiệp vụ.

Ví dụ:

~~~java
import io.micrometer.core.instrument.Timer;

Timer timer = registry.timer("payment.authorization");

Timer.Sample sample = Timer.start(registry);
try {
    AuthorizationResult result = gateway.authorize(payment);
    sample.stop(timer);
    return result;
} catch (RuntimeException exception) {
    sample.stop(timer);
    throw exception;
}
~~~

Nếu muốn phân biệt outcome, tạo các Timer có tag hữu hạn hoặc dùng API phù hợp để stop Sample với Timer được chọn sau khi biết kết quả. Không tạo tag dựa trên exception message hoặc dữ liệu request.

## 11. Kiểm thử TimedAspect

Kiểm thử tích hợp nên xác minh lời gọi đi qua Spring proxy thực sự tạo và cập nhật Timer. Ví dụ:

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
public class CatalogLookupService {

    @Timed("catalog.lookup")
    public String lookup() {
        return "found";
    }
}
~~~

Cấu hình aspect trong test context:

~~~java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TestMetricsConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Kiểm thử:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@Import(TestMetricsConfiguration.class)
class TimedAspectIntegrationTest {

    @Autowired
    CatalogLookupService service;

    @Autowired
    MeterRegistry registry;

    @Test
    void recordsMethodExecution() {
        service.lookup();

        Timer timer = registry.find("catalog.lookup").timer();

        assertNotNull(timer);
        assertEquals(1L, timer.count());
    }
}
~~~

Test cần chạy trong Spring context có AOP proxy, bean service và một MeterRegistry. Nếu ứng dụng đã có TimedAspect bean, không import thêm cấu hình test tạo aspect thứ hai.

Nên kiểm thử thêm:

- Method được gọi từ bean khác qua proxy.
- Self-invocation không được đo như kỳ vọng nếu không đi qua proxy.
- Method ném exception vẫn có hành vi ghi nhận đúng theo phiên bản.
- Tag và histogram được tạo theo cấu hình.
- Method async được đo tới thời điểm hoàn tất mong muốn.
- Không có hai aspect ghi trùng cùng một method.

## 12. Các lỗi thường gặp

- **Chỉ thêm @Timed nhưng không có TimedAspect:** annotation không tự tạo Timer.
- **Đăng ký TimedAspect nhiều lần:** có thể tạo advice trùng và đo sai.
- **Tự gọi method trong cùng bean:** lời gọi thường không đi qua proxy.
- **Đặt annotation trên private/final method:** proxy không thể intercept theo cách mong muốn.
- **Bean không do Spring quản lý:** Spring AOP không tự áp dụng proxy cho object được tạo bằng new.
- **Dùng tag động từ method argument:** cardinality tăng theo dữ liệu request.
- **Đo mọi method nhỏ:** tạo nhiều metric và làm dashboard khó hiểu.
- **Nhầm HTTP auto metrics với @Timed:** hai lớp đo có ranh giới và ý nghĩa khác nhau.
- **Giả định async luôn đo đến khi hoàn tất:** cần xác minh theo return type và phiên bản.
- **Bật histogram/percentile quá rộng:** tăng số series và chi phí lưu trữ.
- **Không kiểm tra registry thực tế:** method chạy nhưng Timer có thể không được tạo do aspect chưa hoạt động.

## 13. Checklist triển khai

- [ ] Xác định method đại diện cho thao tác cần đo.
- [ ] Dùng tên metric và description ổn định.
- [ ] Chỉ dùng extraTags có cardinality thấp.
- [ ] Thêm Spring AOP dependency nếu ứng dụng cần proxy-based aspect.
- [ ] Xác minh application context có đúng một TimedAspect.
- [ ] Inject MeterRegistry từ cấu hình Actuator/Micrometer.
- [ ] Đảm bảo method được gọi qua Spring proxy.
- [ ] Tránh self-invocation hoặc chọn instrumentation thủ công.
- [ ] Kiểm tra method visibility và loại proxy.
- [ ] Chỉ bật histogram, percentile và SLO khi có nhu cầu.
- [ ] Kiểm thử method thành công, exception và async.
- [ ] Xác minh metric xuất hiện trong registry và backend.

`@Timed` giúp khai báo phép đo ngay tại method, còn `TimedAspect` biến annotation đó thành Timer thực tế. Khi framework chưa cung cấp aspect, hãy đăng ký bean đúng một lần, bật Spring AOP và bảo đảm lời gọi đi qua proxy. Chọn ranh giới đo có ý nghĩa, tag ổn định và kiểm thử cả các giới hạn proxy để số liệu phản ánh đúng thời gian thực thi của nghiệp vụ.

