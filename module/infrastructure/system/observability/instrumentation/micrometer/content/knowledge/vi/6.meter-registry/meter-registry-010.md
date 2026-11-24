# Thứ tự cấu hình registry, bộ lọc và đăng ký meter

MeterRegistry là điểm trung tâm để ứng dụng đăng ký và truy cập các meter của Micrometer. Registry cũng là nơi nhận các cấu hình chung như tag mặc định, quy tắc chấp nhận hoặc từ chối meter, chuẩn hóa tên/tag và cấu hình phân phối. Thứ tự thực hiện các bước này ảnh hưởng đến danh tính meter, số lượng chuỗi thời gian và dữ liệu cuối cùng được xuất đến hệ thống giám sát.

Một nguyên tắc quan trọng khi xây dựng instrumentation là **khởi tạo registry, áp dụng cấu hình và filter, rồi mới bind binder hoặc đăng ký meter**. Nếu đăng ký meter trước, các quy tắc được thêm sau thường chỉ có tác dụng với meter đăng ký về sau; chúng không tự động viết lại hay loại bỏ meter đã tồn tại. Bài học này giải thích trình tự đó, cách tổ chức cấu hình trong Java độc lập và cách áp dụng tương tự với Spring Boot.

## Vai trò của MeterRegistry

Micrometer cung cấp API chung để tạo và cập nhật Counter, Gauge, Timer, DistributionSummary cùng các loại meter khác. MeterRegistry quản lý việc đăng ký và cho phép tìm lại meter theo danh tính của nó. Registry cụ thể quyết định cách giữ hoặc xuất các số đo.

Một meter ID về cơ bản được nhận diện bởi tên và tập tag. Ví dụ, hai meter sau có cùng tên nhưng là hai meter ID khác nhau:

~~~java
registry.counter("orders.created", "channel", "web");
registry.counter("orders.created", "channel", "store");
~~~

Registry có thể tái sử dụng meter khi cùng tên và cùng tập tag được đăng ký nhiều lần. Vì thế, thời điểm áp dụng common tags hoặc filter có ảnh hưởng đến ID cuối cùng được đăng ký.

## Trình tự cấu hình khuyến nghị

~~~mermaid
flowchart TD
    A[Tạo MeterRegistry] --> B[Thiết lập common tags]
    B --> C[Thêm MeterFilter]
    C --> D[Cấu hình phân phối]
    D --> E[Bind MeterBinder]
    E --> F[Đăng ký meter ứng dụng]
    F --> G[Ghi nhận số đo]
    G --> H[Registry xuất hoặc cung cấp metrics]
~~~

Trình tự trên thể hiện cách tổ chức an toàn, dễ đọc và dễ kiểm thử:

1. **Tạo registry:** chọn implementation phù hợp với mục đích chạy ứng dụng.
2. **Thiết lập tag chung:** thêm các chiều áp dụng cho phần lớn meter như application, environment hoặc region.
3. **Thêm filter:** định nghĩa meter nào được chấp nhận, từ chối hoặc chuẩn hóa; giới hạn miền giá trị của tag.
4. **Cấu hình phân phối:** xác định histogram, percentile hoặc SLO cho meter phân phối khi cần.
5. **Bind các binder:** đăng ký nhóm meter có sẵn như JVM, class loader, processor hoặc system metrics.
6. **Đăng ký meter nghiệp vụ:** tạo counter, gauge, timer và summary của ứng dụng.
7. **Ghi nhận số đo và xuất dữ liệu:** cập nhật meter trong lúc chạy; registry thực hiện cơ chế lưu hoặc export của implementation đang dùng.

Trong ứng dụng thật, bước tạo registry thường do framework hoặc auto-configuration thực hiện. Khi đó, hãy dùng cơ chế customizer của framework để bảo đảm cấu hình được áp dụng khi registry được tạo và trước khi các binder hoặc meter nghiệp vụ được đăng ký.

## 1. Tạo registry trước khi đăng ký meter

Với chương trình Java độc lập, có thể tạo SimpleMeterRegistry để học và kiểm tra hành vi của API:

~~~java
MeterRegistry registry = new SimpleMeterRegistry();
~~~

SimpleMeterRegistry lưu số đo trong bộ nhớ và không cần endpoint hoặc backend giám sát. Cùng cách dùng API MeterRegistry, ứng dụng có thể chọn registry khác khi cần xuất metrics.

Điều quan trọng là không gọi registry.counter(...), Timer.builder(...).register(registry) hoặc MeterBinder.bindTo(registry) trước khi hoàn tất cấu hình. Những lời gọi đó có thể đăng ký meter ngay lập tức.

## 2. Thiết lập common tags

Common tags là các cặp key/value được thêm vào những meter đăng ký qua registry. Chúng hữu ích để phân biệt application, môi trường và vùng triển khai:

~~~java
registry.config().commonTags(
    "application", "checkout",
    "environment", "prod",
    "region", "ap-southeast-1"
);
~~~

Sau cấu hình này, meter đăng ký về sau sẽ nhận các tag chung cùng với tag riêng do meter khai báo. Ví dụ:

~~~java
Counter orders = registry.counter(
    "orders.created",
    "channel", "web"
);
~~~

Meter này có các chiều application=checkout, environment=prod, region=ap-southeast-1 và channel=web.

Chỉ thêm những tag chung có giá trị ổn định. application, environment và region thường có miền giá trị nhỏ. Không dùng user ID, request ID, hostname sinh ngẫu nhiên theo từng container hoặc thông tin thay đổi theo từng request làm common tag. Một tag chung được áp dụng trên nhiều meter có thể nhân cardinality của toàn registry.

Common tags được áp dụng khi meter được đăng ký. Nếu một meter đã tồn tại trước khi gọi commonTags(...), không nên kỳ vọng registry tự thay đổi ID của meter đó hoặc thêm tag mới ngược về quá khứ. Vì vậy, hãy cấu hình common tags ngay sau khi tạo registry.

## 3. Thêm MeterFilter trước khi tạo meter

MeterFilter cho phép kiểm soát meter trong quá trình đăng ký. Các nhóm tác vụ phổ biến gồm:

| Khả năng | Mục đích | Ví dụ |
|---|---|---|
| Accept hoặc deny | Chấp nhận hoặc từ chối meter theo điều kiện | Loại meter debug khỏi registry |
| Map | Đổi tên meter hoặc biến đổi ID/tag | Chuẩn hóa tên/tag theo quy ước |
| Configure | Điều chỉnh cấu hình phân phối | Áp dụng cấu hình histogram hoặc percentile |

Ví dụ, từ chối các meter dùng tiền tố debug và giới hạn số giá trị uri cho HTTP server metrics:

~~~java
registry.config()
    .meterFilter(MeterFilter.denyNameStartsWith("debug."))
    .meterFilter(MeterFilter.maximumAllowableTags(
        "http.server.requests",
        "uri",
        100,
        MeterFilter.deny()
    ));
~~~

Filter đầu tiên từ chối các meter dùng tiền tố debug. Filter thứ hai giới hạn số giá trị khác nhau của tag uri cho meter có tên bắt đầu bằng http.server.requests. Khi vượt giới hạn, filter được truyền vào làm hành động cuối sẽ từ chối meter mới tương ứng.

Giới hạn này là hàng rào bảo vệ khi dữ liệu đầu vào không như dự kiến. Nó không thay thế việc dùng route template như /orders/{id} thay cho URL chứa ID thực tế. Nếu meter bị từ chối, dashboard hoặc alert phụ thuộc meter đó có thể thiếu dữ liệu; cần theo dõi và chọn giới hạn phù hợp.

### Thứ tự thêm filter có ý nghĩa

Khi có nhiều filter, hãy thêm chúng theo một trình tự rõ ràng và kiểm thử kết quả. Một filter có thể từ chối meter, filter khác có thể đổi tên hoặc tag, filter khác nữa có thể cấu hình phân phối. Nếu nhiều quy tắc cùng tác động đến một meter ID, thứ tự áp dụng có thể ảnh hưởng đến kết quả.

Nên gom các quy tắc liên quan vào một nơi cấu hình registry thay vì rải rác trong nhiều lớp nghiệp vụ. Khi cần biến đổi tên hoặc tag, hãy viết quy tắc có mục đích cụ thể và kiểm tra meter ID sau khi đăng ký. Không dùng filter để che giấu việc một tag có miền giá trị không giới hạn; hãy chuẩn hóa giá trị tại nơi tạo instrumentation.

## 4. Cấu hình phân phối trước khi meter được đăng ký

Timer và DistributionSummary có thể cung cấp các thống kê phân phối như histogram, percentile hoặc SLO. Những cấu hình này ảnh hưởng đến lượng dữ liệu xuất cho mỗi meter ID.

Ví dụ, một timer đo thời gian xử lý thanh toán có thể bật percentile histogram và các ngưỡng SLO:

~~~java
Timer paymentTimer = Timer.builder("payment.processing")
    .description("Thời gian xử lý thanh toán")
    .tag("dependency", "gateway")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

Trong ví dụ này, tag và cấu hình phân phối được khai báo trên builder trước khi register(registry) tạo hoặc tìm meter tương ứng. Khi cần quy tắc phân phối dùng chung cho một nhóm meter, có thể áp dụng qua MeterFilter có khả năng configure. Dù dùng builder hay filter, cấu hình phải có hiệu lực khi meter được đăng ký.

Histogram có thể tạo nhiều chuỗi dữ liệu cho một meter ID, chẳng hạn bucket, count và sum ở registry hỗ trợ Prometheus histogram. Vì vậy, chỉ bật histogram khi có nhu cầu truy vấn phân phối hoặc tính percentile ở phía backend. Chọn số bucket/SLO hợp lý và xem xét tác động đến cardinality.

## 5. Bind meter binder sau khi cấu hình registry

Micrometer có các MeterBinder để đăng ký một nhóm meter có sẵn. Ví dụ, binder JVM có thể tạo metrics về bộ nhớ, garbage collection, thread và class loader. Khi gọi bindTo(registry), binder đăng ký các meter vào registry.

~~~java
new ClassLoaderMetrics().bindTo(registry);
new JvmMemoryMetrics().bindTo(registry);
new ProcessorMetrics().bindTo(registry);
~~~

Vì binder có thể đăng ký nhiều meter ngay trong lời gọi bindTo, hãy cấu hình common tags và filter trước đó. Nếu bind trước rồi mới thêm filter, không nên kỳ vọng những meter đã được tạo sẽ tự động bị từ chối hoặc đổi tag.

Không phải ứng dụng nào cũng cần tất cả binder. Chọn binder theo câu hỏi vận hành và backend thực tế; thêm nhiều meter không cần thiết làm tăng số liệu phải thu thập và duy trì.

## 6. Đăng ký meter nghiệp vụ và ghi nhận dữ liệu

Sau khi hoàn tất cấu hình registry và binder, đăng ký meter nghiệp vụ:

~~~java
Counter orders = Counter.builder("orders.created")
    .description("Số đơn hàng được tạo")
    .tag("channel", "web")
    .register(registry);

Timer checkout = Timer.builder("checkout.processing")
    .description("Thời gian xử lý checkout")
    .tag("operation", "authorize")
    .register(registry);

orders.increment();
checkout.record(() -> processCheckout());
~~~

Khi các meter được đăng ký, registry áp dụng cấu hình và filter đã thiết lập. Việc cập nhật số đo sau đó diễn ra qua API meter, không cần lặp lại cấu hình registry ở mỗi lần ghi nhận.

Không nên tạo một registry mới cho mỗi request. Registry thường có vòng đời gắn với ứng dụng hoặc một phạm vi đo lường ổn định. Nếu mỗi request tạo registry mới, số đo bị chia cắt, tốn tài nguyên và khó xuất dữ liệu nhất quán.

## Ví dụ Java độc lập: cấu hình trước, đăng ký sau

Ví dụ sau gom các bước vào một phương thức khởi tạo. Các class MeterFilter, ClassLoaderMetrics, JvmMemoryMetrics và ProcessorMetrics cần được import từ Micrometer Core tương ứng.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.binder.jvm.ClassLoaderMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.ProcessorMetrics;

import java.time.Duration;

public class RegistrySetup {

    public static void main(String[] args) {
        MeterRegistry registry = createRegistry();

        try {
            Counter orders = Counter.builder("orders.created")
                .tag("channel", "web")
                .register(registry);

            Timer checkout = Timer.builder("checkout.processing")
                .tag("operation", "authorize")
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                    Duration.ofMillis(100),
                    Duration.ofMillis(300),
                    Duration.ofSeconds(1)
                )
                .register(registry);

            orders.increment(3);
            checkout.record(() -> {
                // Thay bằng thao tác nghiệp vụ cần đo.
            });

            System.out.println("Orders = " + orders.count());
            System.out.println("Checkout count = " + checkout.count());
            System.out.println("Registered meters = " + registry.getMeters().size());
        } finally {
            registry.close();
        }
    }

    private static MeterRegistry createRegistry() {
        MeterRegistry registry = new SimpleMeterRegistry();

        // A. Cấu hình tag chung.
        registry.config().commonTags(
            "application", "checkout",
            "environment", "local"
        );

        // B. Thêm filter.
        registry.config()
            .meterFilter(MeterFilter.denyNameStartsWith("debug."))
            .meterFilter(MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny()
            ));

        // C. Bind các nhóm meter có sẵn sau cấu hình.
        new ClassLoaderMetrics().bindTo(registry);
        new JvmMemoryMetrics().bindTo(registry);
        new ProcessorMetrics().bindTo(registry);

        return registry;
    }
}
~~~

createRegistry() trả về registry đã được cấu hình và bind các binder. Chỉ sau khi phương thức này hoàn tất, main mới đăng ký meter nghiệp vụ. Cách tổ chức này làm rõ thứ tự và giúp tái sử dụng cấu hình ở một điểm duy nhất.

Trong ứng dụng thực tế, hãy cân nhắc việc quản lý vòng đời của từng binder theo phiên bản Micrometer đang dùng. Một số binder có thể giữ tài nguyên hoặc cần được đóng khi ứng dụng dừng; hãy làm theo API lifecycle của binder tương ứng khi sử dụng chúng.

## Cấu hình trong Spring Boot

Với Spring Boot Actuator, framework thường tạo và quản lý MeterRegistry. Không nên tự tạo thêm một SimpleMeterRegistry riêng chỉ để cấu hình nếu mục tiêu là cấu hình registry mà Actuator đang sử dụng. Hãy dùng MeterRegistryCustomizer để thêm common tags và filter cho registry do Spring Boot quản lý.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> metricsCommonTags() {
        return registry -> registry.config()
            .commonTags(
                "application", "checkout",
                "environment", "prod"
            )
            .meterFilter(MeterFilter.denyNameStartsWith("debug."))
            .meterFilter(MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny()
            ));
    }
}
~~~

Spring Boot áp dụng các customizer cho registry được auto-configure. Nhờ vậy, common tags và filter có thể được thiết lập trong quá trình cấu hình registry, trước khi các meter binder được bind và meter nghiệp vụ được sử dụng. Nếu dự án có nhiều customizer, hãy kiểm soát thứ tự bằng cơ chế ordering của Spring và tránh để nhiều cấu hình mâu thuẫn cùng sửa một tag.

Cần phân biệt cấu hình registry với cấu hình endpoint export. Ví dụ, mở endpoint Prometheus là cấu hình của Actuator và web exposure; nó không thay thế common tags hoặc MeterFilter. Tương tự, thêm dependency registry Prometheus giúp Spring Boot tạo registry phù hợp, nhưng vẫn cần cấu hình các tag/filter đúng thời điểm.

## Điều gì xảy ra nếu cấu hình sau khi đã đăng ký meter?

Giả sử ứng dụng đăng ký counter trước:

~~~java
Counter orders = registry.counter("orders.created", "channel", "web");
orders.increment();
~~~

Sau đó mới thêm common tags và filter:

~~~java
registry.config().commonTags("application", "checkout");
registry.config().meterFilter(MeterFilter.denyNameStartsWith("debug."));
~~~

Không nên giả định counter orders.created đã tồn tại sẽ tự có tag application=checkout. Tương tự, một meter debug đã đăng ký sẽ không tự biến mất chỉ vì filter từ chối tên đó trong những lần đăng ký tiếp theo. Các filter tác động trong quá trình đăng ký meter; chúng không phải một cơ chế quét và sửa lại toàn bộ registry.

Nếu phát hiện cấu hình được thêm quá muộn:

1. Xác định những meter nào đã được đăng ký trước cấu hình.
2. Kiểm tra meter ID thực tế và những meter nào cần được tạo lại.
3. Điều chỉnh thứ tự khởi tạo để cấu hình chạy trước binder và instrumentation.
4. Trong môi trường phù hợp, tạo lại registry hoặc khởi động lại ứng dụng để toàn bộ meter được đăng ký theo quy tắc mới.
5. Kiểm tra dữ liệu export sau khi triển khai để xác nhận tag và filter có hiệu lực.

Không nên cố sửa hậu quả bằng cách thêm tag khác hoặc tạo registry mới trong từng thành phần. Hãy đưa cấu hình về một điểm khởi tạo có thứ tự rõ ràng.

## Kiểm thử thứ tự cấu hình

Có thể dùng SimpleMeterRegistry để kiểm tra common tags và filter mà không cần kết nối Prometheus. Ví dụ:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.config()
    .commonTags("application", "checkout")
    .meterFilter(MeterFilter.denyNameStartsWith("debug."));

registry.counter("orders.created", "channel", "web").increment();

assertEquals(
    1.0,
    registry.get("orders.created")
        .tag("channel", "web")
        .counter()
        .count()
);

assertEquals(
    "checkout",
    registry.find("orders.created")
        .tag("application", "checkout")
        .meter()
        .getId()
        .getTag("application")
);

assertNull(registry.find("debug.internal.events").meter());
~~~

Trong kiểm thử thực tế, nên có import và assertion của JUnit tương ứng. Đồng thời kiểm thử trường hợp filter từ chối meter và trường hợp maximumAllowableTags vượt ngưỡng. Những bài kiểm thử này xác nhận hành vi của registry trong bộ nhớ; chúng không thay thế kiểm thử tích hợp cho endpoint export, giao thức mạng hoặc backend giám sát.

Một checklist kiểm thử hữu ích:

- Common tags xuất hiện trên meter được đăng ký sau cấu hình.
- Meter bị deny không được đăng ký như meter hoạt động.
- Giá trị tag được map hoặc chuẩn hóa đúng.
- Giới hạn tag hoạt động khi vượt số giá trị cho phép.
- Cấu hình histogram/SLO được áp dụng cho timer hoặc summary cần đo.
- Binder được bind sau khi common tags và filter đã được cấu hình.
- Registry được đóng đúng vòng đời.

## Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách tổ chức tốt hơn |
|---|---|---|
| Đăng ký meter trước rồi mới thêm common tags | Meter cũ không nhận tag chung như kỳ vọng | Cấu hình common tags trước mọi lần đăng ký |
| Bind JVM binder trước khi thêm filter | Meter binder đã đăng ký có thể không chịu quy tắc mới | Thêm filter trước bindTo(registry) |
| Tạo registry trong mỗi request | Dữ liệu bị chia cắt và registry tăng không cần thiết | Dùng registry có vòng đời ứng dụng |
| Đặt cấu hình ở nhiều lớp nghiệp vụ | Khó biết filter nào đang tác động và theo thứ tự nào | Gom cấu hình vào factory hoặc customizer |
| Dùng filter thay cho chuẩn hóa đầu vào | Meter có thể bị từ chối nhưng nguồn cardinality vẫn còn | Chuẩn hóa tag ngay nơi tạo meter |
| Bật histogram cho mọi timer | Số chuỗi và chi phí lưu trữ tăng | Bật theo nhu cầu truy vấn và SLO |

## Ghi nhớ

- MeterRegistry cần được cấu hình trước khi meter hoặc binder được đăng ký.
- Thiết lập common tags sớm để các meter có cùng ngữ cảnh ứng dụng.
- Thêm MeterFilter trước registration để quy tắc accept, deny, map và configure có hiệu lực.
- Thứ tự khai báo filter cần rõ ràng và được kiểm thử khi nhiều quy tắc cùng tác động.
- Cấu hình histogram và SLO trước khi đăng ký timer/summary cần áp dụng.
- Bind các meter binder sau common tags và filter.
- Đăng ký meter nghiệp vụ sau khi registry đã sẵn sàng; không tạo registry theo từng request.
- Trong Spring Boot, dùng MeterRegistryCustomizer để cấu hình registry do framework quản lý.
- Filter không tự sửa meter đã tồn tại; khi cấu hình quá muộn, cần kiểm tra và tạo lại registry/meter theo vòng đời phù hợp.

Khi tổ chức đúng thứ tự, toàn bộ meter trong ứng dụng sẽ tuân theo cùng quy tắc về tag, giới hạn cardinality và thống kê phân phối. Điều đó làm cho dữ liệu Micrometer nhất quán hơn, giảm các bất ngờ khi export và giúp nhóm vận hành tin cậy hơn vào dashboard cùng cảnh báo.

