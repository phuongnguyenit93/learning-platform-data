# Cấu hình tag chung bằng management.metrics.tags và MeterRegistryCustomizer

## 1. Tag chung giải quyết vấn đề gì?

Giả sử cùng metric `orders.accepted` được thu thập từ nhiều dịch vụ, môi trường và vùng triển khai. Chỉ nhìn tên metric, ta chưa biết số liệu thuộc ứng dụng nào hay đang chạy ở đâu.

**Tag** là cặp khóa/giá trị gắn với một meter, giúp phân loại và lọc số liệu. **Tag chung**, hay common tag, là tag được cấu hình ở mức registry để các meter thuộc phạm vi đó nhận cùng thông tin mặc định. Ví dụ:

```text
Tên: orders.accepted
Tag chung:
    application = billing-service
    environment = staging
    region      = ap-southeast-1
Tag riêng của meter:
    channel     = web
```

Nhờ đó có thể hỏi “số đơn được chấp nhận của billing-service ở staging”, hoặc so sánh các vùng triển khai mà vẫn giữ cùng tên metric.

Trong hệ sinh thái Spring Boot Actuator:

```text
Nguồn cấu hình triển khai
    -> management.metrics.tags hoặc MeterRegistryCustomizer
    -> cấu hình MeterRegistry trước khi đăng ký meter
    -> meter nhận các tag phù hợp
    -> Actuator/bộ xuất metrics cho phép kiểm tra và truy vấn
```

Tag chung không tự tạo sự kiện, không tăng counter và không thay đổi phép tính của timer. Nó thay đổi thông tin định danh/phân loại của meter.

## 2. Hiểu ranh giới của một tag chung

### 2.1. Tag chung và tag riêng bổ sung cho nhau

| Thông tin | Nơi đặt phù hợp | Lý do |
| --- | --- | --- |
| Tên ứng dụng | Common tag | Ổn định cho các metric của ứng dụng |
| Môi trường triển khai | Common tag | Dùng lọc local/staging/production |
| Vùng triển khai | Common tag | Cùng ngữ cảnh triển khai của registry |
| Loại kênh web/batch | Tag riêng của metric nếu mỗi sự kiện có thể khác | Phản ánh chiều phân loại của thao tác |
| Kết quả success/failure | Tag riêng của metric | Có thể khác nhau giữa các sự kiện |
| ID từng yêu cầu, mã khách hàng, nội dung lỗi | Không dùng làm common tag | Không phải ngữ cảnh chung ổn định; dễ tạo quá nhiều chuỗi |

Một meter được nhận diện chủ yếu bởi tên và tập tag. Cùng tên nhưng khác `region` hoặc `channel` có thể là hai meter khác nhau trong registry. Các số đếm không tự chuyển từ meter này sang meter kia khi tag thay đổi.

### 2.2. “Chung” có phạm vi registry

Common tag áp dụng thông qua registry được cấu hình và cơ chế xuất tương ứng. Nếu mã tự tạo một registry ngoài vòng đời Spring, cấu hình của Boot không tự động xuất hiện trên đối tượng đó.

Không đồng nhất common tag với:

- Tham số hoặc header của một HTTP request.
- MDC của hệ thống logging.
- Tag của một trace/span.
- Nhãn do máy chủ giám sát bổ sung khi thu thập dữ liệu.

Chúng có thể dùng cùng một số ý nghĩa như môi trường hoặc ứng dụng, nhưng là các cơ chế khác nhau.

## 3. Cách thứ nhất: management.metrics.tags

Dùng properties khi giá trị có thể mô tả bằng cấu hình triển khai. Ví dụ trong ứng dụng Spring Boot 3.3 đã có Actuator:

```yaml
spring:
  application:
    name: billing-service

management:
  metrics:
    tags:
      application: "${spring.application.name}"
      environment: "${APP_ENV:local}"
      region: "${DEPLOY_REGION:local}"
```

Các khóa `application`, `environment`, `region` là tên tag do ứng dụng chọn. Việc đặt `spring.application.name` không có nghĩa mọi meter tự có tag `application`; ở đây ta khai báo rõ ánh xạ đó.

Các placeholder có ý nghĩa:

- `${spring.application.name}`: dùng tên ứng dụng từ cấu hình Spring.
- `${APP_ENV:local}`: dùng giá trị cấu hình APP_ENV nếu có, nếu không dùng `local`.
- `${DEPLOY_REGION:local}`: dùng vùng triển khai, có giá trị mặc định khi chạy cục bộ.

Những giá trị tag nên được biểu diễn như chuỗi. Không để tên môi trường hoặc vùng khác nhau chỉ vì viết hoa/thường, dấu cách hoặc quy ước đặt tên không thống nhất.

Nếu dùng `application.properties`, cấu hình tương đương là:

```properties
spring.application.name=billing-service
management.metrics.tags.application=${spring.application.name}
management.metrics.tags.environment=${APP_ENV:local}
management.metrics.tags.region=${DEPLOY_REGION:local}
```

Chọn định dạng cấu hình phù hợp với dự án, không cần sao chép cùng khai báo vào cả hai tệp.

Spring Boot mô tả trực tiếp cơ chế này trong phần [Common Tags](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.common-tags). Không cần viết lại các tag đó tại từng lời gọi `registry.counter(...)` hay từng timer builder.

### Profile và môi trường không tự có cùng nghĩa

Có thể cấu hình giá trị theo profile, nhưng tên profile là lựa chọn kỹ thuật của ứng dụng. Một ứng dụng có thể bật nhiều profile cùng lúc, chẳng hạn `staging,redis`. Vì vậy, đừng mặc định danh sách profile chính là giá trị môi trường mong muốn để truy vấn.

Đặt một trường như APP_ENV với quy ước rõ ràng khi cần phân loại môi trường vận hành. Các tệp theo profile, biến môi trường và tham số khởi động vẫn tuân theo cơ chế ưu tiên nguồn cấu hình của Spring Boot.

## 4. Cách thứ hai: MeterRegistryCustomizer

Dùng `MeterRegistryCustomizer` khi cần lấy dữ liệu từ cấu hình Java, kiểm tra/chuẩn hóa giá trị, hoặc áp dụng theo loại registry.

### 4.1. Cấu hình bổ sung, không khai báo trùng khóa

Ví dụ chọn chia trách nhiệm như sau:

- `application` và `environment` thuộc properties.
- `region` được bổ sung bằng customizer.
- Các tag nghiệp vụ như `channel` do meter khai báo.

YAML cho phương án này:

```yaml
spring:
  application:
    name: billing-service

app:
  metrics:
    region: "${DEPLOY_REGION:local}"

management:
  metrics:
    tags:
      application: "${spring.application.name}"
      environment: "${APP_ENV:local}"
```

Ở phương án này, không đồng thời khai báo thêm `management.metrics.tags.region`, vì region đã có một nơi sở hữu rõ ràng.

Tệp `CommonMetricsConfiguration.java`, nằm trong phạm vi quét cấu hình của ứng dụng:

```java
package demo;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class CommonMetricsConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> deploymentRegion(Environment environment) {
        String region = environment.getRequiredProperty("app.metrics.region").trim();
        if (region.isEmpty()) {
            throw new IllegalArgumentException("app.metrics.region must not be blank");
        }
        return registry -> registry.config().commonTags("region", region);
    }
}
```

Factory method tạo một callback cấu hình. Tham số `registry` của lambda là registry được Boot chuyển vào khi áp dụng tùy biến; không cần inject `MeterRegistry` vào factory method chỉ để gọi lại nó.

`getRequiredProperty` làm rõ yêu cầu phải có cấu hình region; ví dụ còn loại bỏ khoảng trắng đầu/cuối và từ chối giá trị rỗng. Có thể thêm kiểm tra tập giá trị hợp lệ theo quy ước triển khai nếu cần, nhưng tránh truy vấn dịch vụ từ xa hoặc đọc dữ liệu theo từng request trong callback khởi tạo registry.

Spring Boot nêu cách dùng callback tại phần [Getting Started với metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#getting-started).

### 4.2. Generic type quyết định phạm vi áp dụng

`MeterRegistryCustomizer<MeterRegistry>` có thể áp dụng cho các loại registry phù hợp được Spring quản lý. Khi chỉ cần tùy biến một loại cụ thể, có thể khai báo generic type cụ thể, ví dụ `MeterRegistryCustomizer<SimpleMeterRegistry>`.

Điều đó có hệ quả thực tế: customizer dành cho SimpleMeterRegistry không phải cấu hình chung bảo đảm xuất hiện trên một registry Prometheus khác. Giữ generic type rõ ràng thay vì dùng raw type; kiểm tra loại registry thực tế trong môi trường triển khai.

Không tự tạo một registry mới bên trong customizer. Mục đích là cấu hình đối tượng được truyền vào, không tạo một hệ thống metrics tách rời.

## 5. Thời điểm áp dụng quan trọng hơn việc gọi commonTags ở đâu cũng được

Một trình tự hợp lý là:

```text
Tạo registry
    -> áp dụng customizer và các cấu hình/filter liên quan
    -> bind các nhóm metric
    -> đăng ký và sử dụng metric nghiệp vụ
```

Boot cung cấp vòng đời phù hợp để customizer chạy trước khi bind các meter thông thường do nó quản lý. Trong mã Spring Boot 3.3.0, `MeterRegistryPostProcessor` áp dụng customizer trước filters/binders tương ứng; xem [mã nguồn MeterRegistryPostProcessor](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryPostProcessor.java).

Đây là lý do chọn bean customizer thay vì chờ tới `ApplicationRunner`, một request đầu tiên hay một phương thức khởi tạo tùy ý rồi mới gọi `registry.config().commonTags(...)`.

### Cấu hình muộn không cập nhật đồng loạt meter cũ

Trong Micrometer, common tag được áp dụng qua cơ chế ánh xạ định danh khi đăng ký meter. Khi một meter đã tồn tại, thêm common tag không có nghĩa định danh của đối tượng meter cũ được sửa lại.

Hơn nữa, gọi lại cùng tên và các tag đầu vào sau khi cấu hình ánh xạ thay đổi có thể nhận **meter khác** vì tập tag cuối cùng đã khác. Số đếm của meter mới có thể bắt đầu từ 0 trong khi meter cũ vẫn giữ số đếm cũ. Thí nghiệm ở phần sau kiểm chứng chính trường hợp này.

Vì vậy, thay đổi common tag là thay đổi cấu hình định danh. Thiết kế nó ổn định trong vòng đời triển khai; không dùng commonTags như một setter để đổi môi trường hoặc người dùng đang hoạt động.

## 6. Khi trùng khóa: phân biệt hai loại “ưu tiên”

### 6.1. Ưu tiên nguồn cấu hình của Spring

Nếu nhiều nguồn cùng cung cấp `management.metrics.tags.environment`, Spring Boot giải quyết nguồn cấu hình hiệu lực trước khi giá trị đó được dùng.

Ví dụ, một giá trị trong tệp có thể được thay bởi nguồn ưu tiên cao hơn như tham số khởi động theo các quy tắc của Boot. Đây là cơ chế cấu hình Spring; xem [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 6.2. Kết hợp tag khi meter được đăng ký

Đây là bước khác. Với cơ chế common-tag filter của Micrometer 1.13.0:

- Common tag không ghi đè tag cùng khóa đã có trên meter ID.
- Một common-tag filter phía sau không ghi đè giá trị cùng khóa đã được common-tag filter phía trước thêm vào.
- Gọi `commonTags` nhiều lần có thể bổ sung khóa mới; không nên hiểu là thay thế toàn bộ tập tag cũ.

Quy tắc được ghi rõ trong [MeterFilter.commonTags của Micrometer 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/config/MeterFilter.java).

Ví dụ registry có region mặc định `ap-southeast-1`, nhưng một meter được đăng ký với `region=eu-west-1`, thì tag riêng có thể được giữ là `eu-west-1`. **Common tag là giá trị chung mặc định, không phải cơ chế cưỡng chế meter phải mang một giá trị duy nhất.**

Không xây quy ước “YAML luôn thắng Java” hoặc “Java luôn ghi đè YAML” cho các khóa trùng nhau. Callback, filter và tag riêng tạo thành chuỗi xử lý; hãy cho mỗi khóa một nơi sở hữu và kiểm tra định danh cuối cùng.

### 6.3. Có nhiều customizer thì sao?

Nếu cần thứ tự giữa các customizer, có thể dùng cơ chế `@Order`/`Ordered` của Spring; customizer có thứ tự ưu tiên cao hơn được áp dụng trước theo vòng đời Boot. Tuy nhiên, thứ tự callback không phải thứ tự hiển thị các nhãn trên mọi hệ giám sát.

Đặc biệt, tài liệu Boot lưu ý thứ tự common tag có ý nghĩa với Graphite và khuyến nghị custom MeterFilter khi cần kiểm soát cách đó. Không dựa vào thứ tự dòng YAML hoặc thứ tự chuỗi nhãn nhìn thấy trên màn hình để thiết kế định danh.

## 7. Thí nghiệm chạy độc lập với cấu hình metrics thật của Boot

Chương trình sau dùng Spring context và nhập đúng các auto-configuration metrics của Boot. Nó không khởi động máy chủ web. Cấu hình được đưa vào Environment trước khi refresh context để kiểm chứng cả binding `management.metrics.tags` và customizer.

Các giá trị được chọn cố định nhằm làm kết quả tái lập được; đây không phải cấu hình bắt buộc của mọi ứng dụng.

### 7.1. Dự án Gradle

Dùng JDK 17 trở lên, khuyến nghị JDK 21. Tạo dự án riêng với `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-actuator-autoconfigure'
    implementation 'org.springframework:spring-context'
    implementation 'io.micrometer:micrometer-core'
}

application {
    mainClass = 'demo.CommonTagsDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs += ['-parameters']
}

tasks.register('copyRuntimeDependencies', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

`settings.gradle`:

```groovy
rootProject.name = 'common-tags-demo'
```

BOM Spring Boot 3.3.0 quản lý các phiên bản thư viện dùng trong thí nghiệm, bao gồm Micrometer 1.13.0. Trong dự án Boot đã có cơ chế quản lý phụ thuộc, chỉ cần bổ sung Actuator nếu chưa có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Không cần thêm starter AOP chỉ để sử dụng common tag.

### 7.2. Chương trình Java đầy đủ

Tệp `src/main/java/demo/CommonTagsDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.boot.actuate.autoconfigure.metrics.MetricsAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.metrics.export.simple.SimpleMetricsExportAutoConfiguration;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

public class CommonTagsDemo {
    @Configuration(proxyBeanMethods = false)
    @ImportAutoConfiguration({
        MetricsAutoConfiguration.class,
        SimpleMetricsExportAutoConfiguration.class
    })
    public static class Config {
        @Bean
        MeterRegistryCustomizer<MeterRegistry> regionTags(Environment environment) {
            String region = environment.getRequiredProperty("app.metrics.region");
            return registry -> registry.config().commonTags("region", region);
        }

        @Bean
        MeterBinder demoOrders() {
            return registry -> registry.counter("demo.orders.accepted", "channel", "web")
                    .increment(2);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo", Map.of(
                            "spring.application.name", "billing-demo",
                            "management.metrics.tags.application", "${spring.application.name}",
                            "management.metrics.tags.environment", "staging",
                            "management.metrics.use-global-registry", "false",
                            "app.metrics.region", "ap-southeast-1"
                    )));
            context.register(Config.class);
            context.refresh();

            SimpleMeterRegistry registry = context.getBean(SimpleMeterRegistry.class);
            Counter inherited = registry.get("demo.orders.accepted")
                    .tag("region", "ap-southeast-1").counter();
            System.out.println("boot.tags=" + tags(inherited));
            System.out.printf(Locale.ROOT, "boot.count=%.0f%n", inherited.count());

            Counter explicit = registry.counter("demo.orders.accepted",
                    "channel", "web", "region", "eu-west-1");
            explicit.increment();
            System.out.println("explicit.region=" + explicit.getId().getTag("region"));
            System.out.println("distinct.meter=" + (inherited != explicit));
            System.out.printf(Locale.ROOT, "boot.original.count=%.0f%n", inherited.count());
        }

        demonstrateLateConfiguration();
    }

    private static void demonstrateLateConfiguration() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Counter before = registry.counter("demo.late", "phase", "before");
            before.increment(3);
            registry.config().commonTags("region", "local");
            registry.config().commonTags("region", "replacement", "team", "training");

            Counter after = registry.counter("demo.late", "phase", "after");
            Counter requestedAgain = registry.counter("demo.late", "phase", "before");

            System.out.println("late.before.region=" + before.getId().getTag("region"));
            System.out.println("late.after.region=" + after.getId().getTag("region"));
            System.out.println("late.after.team=" + after.getId().getTag("team"));
            System.out.println("late.reused.instance=" + (before == requestedAgain));
            System.out.printf(Locale.ROOT, "late.old.count=%.0f late.new.count=%.0f%n",
                    before.count(), requestedAgain.count());
        } finally {
            registry.close();
        }
    }

    private static Map<String, String> tags(Meter meter) {
        Map<String, String> result = new TreeMap<>();
        meter.getId().getTags().forEach(tag -> result.put(tag.getKey(), tag.getValue()));
        return result;
    }
}
```

`MeterBinder` trong thí nghiệm chỉ đăng ký một counter để có dữ liệu đối chiếu. Nó được Boot gọi sau bước cấu hình registry; không cần thêm endpoint hoặc lặp tag application/environment/region trong binder.

Chạy với Gradle đã cài, hoặc wrapper của chính dự án thí nghiệm:

```shell
gradle -q run
```

Để biên dịch/chạy trực tiếp, trước hết chạy `gradle -q copyRuntimeDependencies`, sau đó dùng lệnh trên Windows:

```shell
javac --release 17 -encoding UTF-8 -parameters -cp "build/runtime-libs/*" -d build/manual-classes src/main/java/demo/CommonTagsDemo.java
java -cp "build/manual-classes;build/runtime-libs/*" demo.CommonTagsDemo
```

Trên Linux/macOS, thay dấu `;` ngăn các thành phần classpath trong lệnh `java` bằng `:`.

### 7.3. Stdout đã kiểm chứng

```text
boot.tags={application=billing-demo, channel=web, environment=staging, region=ap-southeast-1}
boot.count=2
explicit.region=eu-west-1
distinct.meter=true
boot.original.count=2
late.before.region=null
late.after.region=local
late.after.team=training
late.reused.instance=false
late.old.count=3 late.new.count=0
```

Phần cố ý cấu hình muộn có thể phát thêm log cảnh báo về việc cấu hình MeterFilter sau khi đã có meter. Log đó nằm ngoài các dòng stdout được liệt kê và chính là dấu hiệu của thứ tự cấu hình không phù hợp trong nửa sau của thí nghiệm.

`TreeMap` chỉ dùng để in tag theo thứ tự ổn định, giúp so sánh kết quả. Nó không định nghĩa thứ tự tag khi xuất sang một backend.

## 8. Giải thích kết quả thí nghiệm

### 8.1. Tag từ properties và customizer được kết hợp

Dòng `boot.tags` có bốn khóa:

| Khóa | Giá trị | Nguồn |
| --- | --- | --- |
| application | billing-demo | management.metrics.tags và placeholder spring.application.name |
| environment | staging | management.metrics.tags.environment |
| region | ap-southeast-1 | MeterRegistryCustomizer |
| channel | web | Tag riêng khi binder đăng ký counter |

Counter có count bằng 2 vì binder gọi `increment(2)`. Việc thêm tag không làm số đếm thành bốn hay tăng theo số khóa.

Trong mã Boot 3.3.0, `management.metrics.tags` được chuyển thành một filter áp dụng common tag qua [PropertiesMeterFilter](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/PropertiesMeterFilter.java). Như vậy, properties và Java đi vào cùng quá trình cấu hình định danh meter, thay vì tạo hai bản sao counter độc lập chỉ vì có hai nguồn cấu hình.

### 8.2. Tag riêng tạo một định danh khác

Lần đăng ký tiếp theo chỉ rõ `region=eu-west-1`. Nó giữ giá trị riêng đó và nhận một meter khác:

```text
explicit.region=eu-west-1
distinct.meter=true
boot.original.count=2
```

Counter mới được tăng một lần; counter gốc vẫn là 2. Nếu truy vấn gộp tất cả region cho cùng tên metric, cần hiểu rằng đang cộng số liệu của các chuỗi khác nhau.

Việc có thể đặt region riêng cũng cho thấy cần thống nhất ý nghĩa của khóa: nếu region được quy ước là “nơi ứng dụng đang triển khai”, mã nghiệp vụ không nên tái dùng cùng khóa để chỉ “vùng khách hàng được phục vụ”. Khi cần cả hai, chọn hai tên tag phân biệt rõ.

### 8.3. Common tag thêm sau không sửa meter đã tồn tại

Meter đầu tiên của registry thứ hai được đăng ký trước khi có common tag:

```text
late.before.region=null
```

Giá trị `null` ở đây nghĩa là **không có khóa region trên ID**, không phải một tag có chuỗi giá trị `"null"`.

Sau hai lời gọi commonTags, meter được đăng ký mới có:

```text
region = local
team   = training
```

Region vẫn là `local`, vì lời gọi commonTags sau không ghi đè region đã được common-tag filter trước thêm vào. Khóa team chưa có thì được bổ sung.

Cuối cùng, yêu cầu đăng ký lại cùng tên và tag đầu vào `phase=before` đi qua cấu hình hiện tại, nhận ID có thêm common tag. Nó không dùng lại đối tượng cũ:

```text
late.reused.instance=false
late.old.count=3 late.new.count=0
```

Điều này giải thích vì sao thêm tag muộn có thể tạo dữ liệu bị chia tách: một phần metric cũ thiếu tag, một phần metric mới có tag, và số đếm không được chuyển sang tự động.

## 9. Kiểm tra kết quả trong ứng dụng thật

### 9.1. Kiểm tra registry mà ứng dụng đang sử dụng

Đối với meter đã đăng ký, có thể đọc `getId().getTags()` để xem tag trên đối tượng cụ thể, như thí nghiệm đã làm. Khi có nhiều registry hoặc một CompositeMeterRegistry, xác định cả registry con thực sự xuất dữ liệu; đừng kết luận về dữ liệu cuối cùng chỉ từ một đối tượng registry không được backend sử dụng.

Ưu tiên inject `MeterRegistry` do Spring quản lý. Một `new SimpleMeterRegistry()` tự tạo trong service là một đối tượng khác; bean customizer không tự được chạy lên mọi đối tượng Java được tạo bằng new.

Các lệnh tĩnh trên `Metrics` dùng global registry. Boot có tích hợp global registry theo cấu hình, nhưng không nên dựa vào giả định mọi đường đăng ký tĩnh đều tương đương với bean được inject. Thí nghiệm đặt `management.metrics.use-global-registry=false` để tránh ảnh hưởng tới trạng thái global giữa các lần chạy.

### 9.2. Kiểm tra qua Actuator

Trong ứng dụng web Boot đã có Actuator, có thể mở endpoint metrics cho cấu hình cục bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Sau khi ứng dụng đã đăng ký metric tương ứng:

```shell
curl "http://localhost:8080/actuator/metrics/demo.orders.accepted"
curl "http://localhost:8080/actuator/metrics/demo.orders.accepted?tag=environment:staging&tag=region:ap-southeast-1"
```

Các yêu cầu trên áp dụng cho ứng dụng web có cùng metric; chương trình console ở phần trước không tự mở các URL đó. Cổng, base path và yêu cầu xác thực tùy theo cấu hình của ứng dụng.

Xem những tag khả dụng và lọc theo các giá trị đã xác minh. Không đưa một bản JSON cố định của một registry làm khuôn cho mọi backend. Nếu có ánh xạ ở registry con/bộ xuất, đối chiếu dữ liệu xuất thực tế trước khi kết luận tag bị thiếu.

### 9.3. Kiểm tra tại hệ giám sát

Với Prometheus, tag thường trở thành label. Tên metric có thể được đổi theo naming convention, chẳng hạn counter có thể xuất dưới tên `demo_orders_accepted_total`; kiểm tra tên thực tế trước khi viết truy vấn.

Ví dụ truy vấn chỉ áp dụng sau khi registry Prometheus đã được cấu hình, dữ liệu đã được thu thập và các tên/label này thực sự tồn tại:

```promql
sum by (region) (
  rate(demo_orders_accepted_total{
    application="billing-demo",
    environment="staging"
  }[5m])
)
```

Tag chung cho phép giữ phạm vi ứng dụng/môi trường rồi so sánh region. Nó không tự thiết lập quá trình scrape hoặc truyền dữ liệu; chương trình console dùng SimpleMeterRegistry không có bước xuất Prometheus này.

## 10. Giữ tập tag hữu ích và ổn định

### 10.1. Chú ý số lượng tổ hợp giá trị

Một chuỗi thời gian thường gắn với một tập label cụ thể. Nếu một metric có 2 môi trường, 3 vùng và 4 kênh xuất hiện trong toàn hệ thống, có thể có tới 24 tổ hợp ở các chiều đó, trước khi xét các chiều khác.

Đó là số tổ hợp tiềm năng trên dữ liệu toàn hệ thống, không có nghĩa mỗi tiến trình mặc nhiên sinh 24 meter: environment/region thường cố định trên một tiến trình; chỉ những tổ hợp thực sự được tạo mới xuất hiện.

Các common tag ổn định như application/environment/region thường có giá trị phân tích rõ. Tag lấy từ ID yêu cầu hoặc từng khách hàng có thể tăng theo dữ liệu không giới hạn. Không dùng common tag để mang thông tin thay đổi theo từng request; sử dụng các nhóm phân loại hữu hạn ở metric thích hợp, hoặc công cụ theo dõi chi tiết khác.

Tài liệu [Naming Meters của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html) giải thích common tag, thời điểm áp dụng và rủi ro số lượng giá trị tag.

### 10.2. Đổi tên hoặc giá trị tag là đổi cách phân loại lịch sử

Chuyển environment từ `prod` sang `production` tạo giá trị label khác. Dashboard lọc `prod` không tự đọc cả `production`. Tương tự, đổi khóa `application` thành `service` ảnh hưởng truy vấn và quy ước dữ liệu.

Khi thay cấu hình, cập nhật các truy vấn liên quan và dự kiến giai đoạn số liệu cũ/mới cùng tồn tại. Không kỳ vọng commonTags viết lại dữ liệu lịch sử đã xuất.

### 10.3. Không dùng common tag để mang trạng thái có thể thay đổi

Region triển khai phù hợp làm common tag khi ổn định trong vòng đời tiến trình. Ngược lại, trạng thái đơn hàng, kết quả xử lý hoặc người dùng hiện tại có thể thay đổi giữa các sự kiện. Nếu đọc một giá trị theo request trong customizer lúc khởi động, nó không tự thay đổi theo các request sau.

Callback cấu hình registry là bước khởi tạo, không phải bộ lắng nghe mọi thay đổi nghiệp vụ.

## 11. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Có spring.application.name nhưng thiếu tag application | Chưa khai báo tag tương ứng | Thêm management.metrics.tags.application hoặc customizer rõ ràng |
| Chỉ một số metric có tag | Cấu hình sau khi metric cũ đã đăng ký, hoặc có nhiều registry | Chuyển cấu hình về bước khởi tạo và kiểm tra registry xuất |
| Customizer không chạy | Cấu hình ngoài phạm vi quét, bean chưa được đăng ký hoặc generic type không khớp | Kiểm tra bean và loại registry thực tế |
| Tag không có giá trị như dự kiến | Cấu hình hiệu lực khác, placeholder hoặc khóa sở hữu bị trùng | Xác minh nguồn cấu hình rồi kiểm tra ID cuối cùng |
| Gọi commonTags lần nữa nhưng giá trị cũ không đổi | Hiểu commonTags như thao tác ghi đè | Cấu hình một lần, tránh nhiều nơi sở hữu cùng khóa |
| Cùng tên metric nhưng số đếm bị chia | Tag cuối cùng khác nhau, có meter mới sau thay đổi cấu hình | Kiểm tra toàn bộ tập tag và ổn định định danh từ đầu |
| Registry tự tạo có số liệu nhưng Actuator không thấy | Đang ghi vào registry ngoài luồng Spring quản lý | Dùng registry được inject |
| Giá trị khác nhau chỉ vì dấu cách/viết hoa | Thiếu quy ước hoặc chuẩn hóa | Kiểm tra/chuẩn hóa trong cấu hình hay customizer |
| Số chuỗi tăng nhanh | Tag có quá nhiều giá trị hoặc đổi theo từng sự kiện | Giới hạn chiều phân loại và loại thông tin không phù hợp |

## 12. Thực hành tự kiểm chứng

1. **Chỉ dùng properties:** bỏ customizer region và chuyển region sang management.metrics.tags.region. Với context mới, xác nhận counter có đủ application/environment/region/channel.
2. **Phân chia hai nguồn:** giữ application/environment trong properties và region trong customizer như thí nghiệm. Chỉ ra nơi sở hữu từng khóa.
3. **Kiểm tra cấu hình muộn:** giải thích vì sao meter trước đó có region=null và số đếm 3, còn meter được đăng ký lại có số đếm 0. Nêu cách tổ chức khởi tạo để tránh điều đó.
4. **Kiểm tra trùng khóa:** đăng ký một meter với region riêng; xác nhận common tag không cưỡng chế giá trị triển khai. Đề xuất tên riêng nếu cần đo cả vùng triển khai và vùng được phục vụ.
5. **Kiểm tra loại registry:** thay generic customizer bằng loại cụ thể và đánh giá nó sẽ tác động tới registry nào, trước khi chuyển sang backend khác.

Sau bài thực hành, cần đọc được nguồn của từng tag, thời điểm nó được áp dụng và registry nào thực sự xuất nó. Ba thông tin đó giúp lựa chọn giữa properties và customizer, đồng thời tránh các chuỗi metrics thiếu tag hoặc bị chia tách ngoài ý muốn.
