# Bật hoặc tắt nhóm metrics bằng management.metrics.enable

## 1. Điều khiển metric nào được registry chấp nhận

Một ứng dụng Spring Boot có thể sinh metric về JVM, HTTP, cơ sở dữ liệu, cache và nghiệp vụ. Không phải môi trường nào cũng cần thu thập tất cả những metric đó.

`management.metrics.enable` là **bản đồ các quy tắc theo tên metric**, dùng để cho phép hoặc từ chối các meter khi đăng ký vào registry chịu cấu hình của Spring Boot.

Ví dụ:

```properties
management.metrics.enable.jvm=false
```

Quy tắc này tắt nhóm tên `jvm`, chẳng hạn `jvm.memory.used` và `jvm.threads.live`, trong phạm vi registry có áp dụng bộ lọc của Boot. Nó không có nghĩa là dừng JVM, dừng xử lý nghiệp vụ hoặc tắt toàn bộ Actuator.

Có thể hình dung:

```text
Instrumentation hoặc mã nghiệp vụ muốn đăng ký meter
    -> registry kiểm tra các quy tắc/filter
        -> được chấp nhận: tạo hoặc dùng meter thật
        -> bị từ chối: trả meter không ghi nhận dữ liệu
    -> mã gọi vẫn có thể tiếp tục sử dụng giao diện meter
```

Bài này dùng Spring Boot 3.3.0 và Micrometer 1.13.0 để kiểm chứng hành vi. Cấu hình nhóm metrics được Boot mô tả trong phần [Per-meter Properties](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties).

## 2. Cấu hình cơ bản: tắt một nhóm hoặc cho phép có chọn lọc

### 2.1. Giữ mặc định, chỉ loại các nhóm không cần

Nếu không đặt quy tắc liên quan, cơ chế enable này mặc định cho phép meter, với điều kiện không có filter khác từ chối nó.

Ví dụ chỉ tắt JVM và nhóm metric HTTP client có tên tương ứng:

```yaml
management:
  metrics:
    enable:
      jvm: false
      "http.client.requests": false
```

Dạng properties tương đương:

```properties
management.metrics.enable.jvm=false
management.metrics.enable.http.client.requests=false
```

Các metric ngoài hai nhóm đó không bị hai quy tắc này tắt. Dấu ngoặc kép quanh khóa có dấu chấm trong YAML giúp người đọc nhìn rõ đây là một khóa tên nhóm; không biến nó thành biểu thức chính quy.

Tên được dùng là **tên Micrometer**, ví dụ `http.client.requests`, không phải tên đã đổi sang kiểu đặt tên của Prometheus như `http_client_requests_seconds_count`.

### 2.2. Tắt mặc định rồi chỉ mở các nhóm cần dùng

Dùng khóa đặc biệt `all` làm giá trị dự phòng cho những tên chưa có quy tắc cụ thể:

```yaml
management:
  metrics:
    enable:
      all: false
      jvm: true
      "jvm.gc": false
      "http.server.requests": true
      "app.orders": true
```

Với cấu hình này, xét riêng cơ chế enable của Boot:

| Tên meter | Quy tắc quyết định | Kết quả |
| --- | --- | --- |
| jvm.memory.used | jvm=true | Cho phép |
| jvm.threads.live | jvm=true | Cho phép |
| jvm.gc.pause | jvm.gc=false | Từ chối |
| http.server.requests | http.server.requests=true | Cho phép |
| app.orders.accepted | app.orders=true | Cho phép |
| cache.gets | all=false | Từ chối nếu không có quy tắc cụ thể khác |

`all=false` không phải một lệnh phủ quyết tuyệt đối mọi tên. Nó là **giá trị dự phòng**, nên một nhóm cụ thể vẫn có thể được mở lại.

Ngược lại, `all=true` không ngăn một nhóm cụ thể bị đặt thành false.

### 2.3. Enable không tạo instrumentation còn thiếu

Đặt `management.metrics.enable.app.orders=true` chỉ cho phép tên tương ứng được đăng ký. Nó không tự tạo counter đơn hàng, không tự gắn thời gian vào service và không khiến mọi thư viện bắt đầu phát metric.

Muốn có dữ liệu vẫn cần đủ các điều kiện:

1. Có instrumentation hoặc mã đăng ký meter.
2. Có registry phù hợp.
3. Tên meter được các quy tắc/filter cho phép.
4. Có sự kiện hoặc giá trị để ghi nhận.
5. Có đường xuất/thu thập nếu cần quan sát từ bên ngoài ứng dụng.

## 3. Tên cụ thể hơn được xét trước nhóm cha

Quy tắc được giải quyết theo các phần của tên ngăn cách bằng dấu chấm. Với tên `app.orders.debug.payload`, thứ tự tìm quy tắc là:

```text
app.orders.debug.payload
app.orders.debug
app.orders
app
all, nếu chưa tìm được quy tắc
mặc định true, nếu không có cả all
```

Ngay khi tìm được quy tắc ở mức cụ thể nhất đang xét, kết quả đó được sử dụng. **Không phải cứ thấy một nhóm cha false là mọi nhóm con đều bị tắt vĩnh viễn.**

Ví dụ:

```properties
management.metrics.enable.all=false
management.metrics.enable.app.orders=true
management.metrics.enable.app.orders.debug=false
management.metrics.enable.app.orders.debug.audit=true
```

Kết quả:

| Tên meter | Quy tắc được tìm thấy trước | Cho phép? |
| --- | --- | --- |
| app.orders.accepted | app.orders=true | Có |
| app.orders.debug.payload | app.orders.debug=false | Không |
| app.orders.debug.audit.saved | app.orders.debug.audit=true | Có |
| app.billing.completed | all=false | Không |

Đây là cách mở một miền nghiệp vụ, tắt một nhánh chi tiết bên trong, nhưng vẫn giữ một nhánh con thực sự cần quan sát.

### Ranh giới nhóm là phần tên, không phải mọi chuỗi bắt đầu giống nhau

Trong Spring Boot 3.3.0:

```properties
management.metrics.enable.app.orders=false
```

khớp `app.orders` và `app.orders.accepted`, nhưng không tự khớp `app.ordersx.accepted`.

Mã triển khai tìm tên đầy đủ rồi lần lượt bỏ phần cuối sau dấu chấm. Có thể đối chiếu cách tìm này tại [PropertiesMeterFilter của Spring Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/PropertiesMeterFilter.java). Không thay quy tắc đó bằng giả định mọi cấu hình đều dùng `String.startsWith` với một chuỗi tùy ý.

## 4. Tắt metric khác với ẩn endpoint và tắt bộ xuất

Những cấu hình sau nằm ở các tầng khác nhau:

| Cấu hình | Tầng chịu tác động | Ý nghĩa |
| --- | --- | --- |
| management.metrics.enable.jvm=false | Đăng ký meter theo tên | Từ chối nhóm JVM trong registry chịu bộ lọc |
| management.endpoint.metrics.enabled=false | Endpoint Actuator metrics | Tắt endpoint chẩn đoán metrics |
| management.endpoints.web.exposure.exclude=metrics | Khả năng truy cập HTTP | Không expose endpoint metrics qua web |
| management.prometheus.metrics.export.enabled=false | Bộ xuất/registry Prometheus | Tắt cơ chế xuất Prometheus tương ứng theo cấu hình Boot |

Ví dụ chỉ expose health:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
```

Việc không expose metrics qua HTTP **không có nghĩa các meter đã ngừng tồn tại hoặc không còn được thu thập qua registry khác**.

Tương tự, tắt endpoint metrics không tự tắt endpoint prometheus hoặc mọi bộ xuất đang có. Tắt riêng bộ xuất Prometheus cũng không khẳng định các registry khác đã bị tắt.

Tài liệu [Actuator Endpoints của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) phân biệt endpoint được bật với endpoint được expose. Khi chẩn đoán, xác định đang muốn ngừng đăng ký một nhóm meter, ngừng xuất sang một hệ thống, hay chỉ thay đổi khả năng truy cập endpoint.

## 5. Meter bị từ chối sẽ hoạt động như thế nào?

Một filter từ chối meter thường khiến registry trả một đối tượng **không ghi nhận dữ liệu**, còn gọi là NOOP meter. Mã vẫn gọi được phương thức theo giao diện Micrometer.

Với counter bị từ chối trong thí nghiệm của bài:

```text
counter.increment(2) vẫn gọi được
counter.count() trả 0
registry.find(tên).counter() không tìm thấy counter đã đăng ký
```

Phân biệt:

- **Counter thật có giá trị 0:** meter đã tồn tại nhưng chưa được tăng.
- **Counter bị từ chối:** đối tượng trả về bỏ qua việc ghi; registry không công bố nó như counter được chấp nhận.

Không dùng số 0 để kết luận sự kiện nghiệp vụ chưa xảy ra. Có thể sự kiện đã xảy ra nhưng phép đo bị từ chối bởi cấu hình.

Cơ chế DENY và NOOP được Micrometer giải thích trong [Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

### Phạm vi tác động tới tài nguyên

Từ chối meter có thể giảm lượng thống kê được giữ và dữ liệu xuất, nhưng không bảo đảm loại bỏ mọi chi phí liên quan:

- Mã nghiệp vụ vẫn chạy.
- Mã có thể đã tính tag hoặc chuẩn bị đầu vào trước khi gọi meter.
- Thành phần instrumentation/binder hoặc cơ chế theo dõi nền có thể vẫn được khởi tạo tùy thư viện.
- Dữ liệu đã gửi trước đó vẫn nằm trong hệ giám sát theo chính sách lưu trữ.

Vì vậy, không coi management.metrics.enable là công tắc dừng mọi hoạt động của thư viện được đo. Nếu mục tiêu là loại bỏ một tác vụ thu thập tốn tài nguyên, cần đo tác động thực tế và kiểm tra vòng đời instrumentation tương ứng.

## 6. Thí nghiệm Java kiểm chứng quy tắc đăng ký

Chương trình dưới đây khởi tạo các Spring context tách biệt và dùng đúng auto-configuration metrics của Boot. Mỗi trường hợp áp dụng cấu hình trước khi tạo registry.

Các tên `app.*` là counter thử nghiệm do chương trình đăng ký, không phải metric JVM hoặc HTTP tự sinh. Không cần máy chủ web để kiểm chứng cơ chế enable.

### 6.1. Chuẩn bị dự án riêng

Dùng JDK 17 trở lên, khuyến nghị JDK 21. Tệp `build.gradle`:

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
    mainClass = 'demo.MetricsEnableDemo'
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

Tệp `settings.gradle`:

```groovy
rootProject.name = 'metrics-enable-demo'
```

Các phiên bản được quản lý bằng BOM Spring Boot 3.3.0. Trong ứng dụng Boot đã có quản lý phụ thuộc và Actuator, không cần tạo thêm dự án này; nó phục vụ kiểm chứng độc lập.

### 6.2. Mã nguồn đầy đủ

Tệp `src/main/java/demo/MetricsEnableDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.boot.actuate.autoconfigure.metrics.MetricsAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.metrics.MetricsProperties;
import org.springframework.boot.actuate.autoconfigure.metrics.export.simple.SimpleMetricsExportAutoConfiguration;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class MetricsEnableDemo {
    @Configuration(proxyBeanMethods = false)
    @ImportAutoConfiguration({
        MetricsAutoConfiguration.class,
        SimpleMetricsExportAutoConfiguration.class
    })
    public static class Config {
    }

    public static void main(String[] args) {
        runCase("default", Map.of(),
                "app.orders.accepted");

        runCase("prefix", Map.of(
                "management.metrics.enable.app.orders", "false"),
                "app.orders",
                "app.orders.accepted",
                "app.ordersx.accepted");

        runCase("exceptions", Map.of(
                "management.metrics.enable.all", "false",
                "management.metrics.enable.app.orders", "true",
                "management.metrics.enable.app.orders.debug", "false",
                "management.metrics.enable.app.orders.debug.audit", "true"),
                "app.orders.accepted",
                "app.orders.debug.payload",
                "app.orders.debug.audit.saved",
                "app.billing.completed");

        runCase("star-normalized", Map.of(
                "management.metrics.enable.all", "false",
                "management.metrics.enable.app.*", "true"),
                "app",
                "app.orders.accepted");

        runCase("literal-star", Map.of(
                "management.metrics.enable.all", "false",
                "management.metrics.enable[app.*]", "true"),
                "app.orders.accepted");
    }

    private static void runCase(String label, Map<String, String> enableProperties,
            String... meterNames) {
        Map<String, Object> properties = new HashMap<>();
        properties.put("management.metrics.use-global-registry", "false");
        properties.putAll(enableProperties);

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("case-" + label, properties));
            context.register(Config.class);
            context.refresh();

            SimpleMeterRegistry registry = context.getBean(SimpleMeterRegistry.class);
            System.out.println("[" + label + "]");
            if (label.equals("star-normalized") || label.equals("literal-star")) {
                System.out.println("bound.rules=" + new TreeMap<>(
                        context.getBean(MetricsProperties.class).getEnable()));
            }
            for (String name : meterNames) {
                Counter counter = registry.counter(name, "channel", "web");
                counter.increment(2);
                boolean visible = registry.find(name)
                        .tag("channel", "web").counter() != null;
                System.out.printf(Locale.ROOT, "%s registered=%s count=%.0f%n",
                        name, visible, counter.count());
            }
        }
    }
}
```

`management.metrics.use-global-registry=false` giữ các ca thử độc lập với global registry tĩnh. Mỗi context có registry mới, nên kết quả không lẫn meter hoặc số đếm của ca trước.

`TreeMap` chỉ giúp in bản đồ cấu hình theo thứ tự ổn định trong hai ca chứa dấu sao; thứ tự dòng hiển thị không quyết định quy tắc nào cụ thể hơn.

### 6.3. Chạy chương trình

Với Gradle đã cài, hoặc wrapper của chính dự án thí nghiệm:

```shell
gradle -q run
```

Có thể biên dịch/chạy trực tiếp sau khi chạy `gradle -q copyRuntimeDependencies`. Lệnh trên Windows:

```shell
javac --release 17 -encoding UTF-8 -parameters -cp "build/runtime-libs/*" -d build/manual-classes src/main/java/demo/MetricsEnableDemo.java
java -cp "build/manual-classes;build/runtime-libs/*" demo.MetricsEnableDemo
```

Trên Linux/macOS, thay dấu `;` ngăn các thành phần classpath trong lệnh `java` bằng `:`.

### 6.4. Stdout đã kiểm chứng

```text
[default]
app.orders.accepted registered=true count=2
[prefix]
app.orders registered=false count=0
app.orders.accepted registered=false count=0
app.ordersx.accepted registered=true count=2
[exceptions]
app.orders.accepted registered=true count=2
app.orders.debug.payload registered=false count=0
app.orders.debug.audit.saved registered=true count=2
app.billing.completed registered=false count=0
[star-normalized]
bound.rules={all=false, app=true}
app registered=true count=2
app.orders.accepted registered=true count=2
[literal-star]
bound.rules={all=false, app.*=true}
app.orders.accepted registered=false count=0
```

Không có số liệu thời gian phụ thuộc lịch chạy. Mỗi counter thử đều được gọi increment với cùng lượng 2, giúp phân biệt rõ meter được chấp nhận với meter bị từ chối.

## 7. Đọc các kết quả thay vì chỉ nhìn giá trị property

### 7.1. Trường hợp mặc định

Không có quy tắc enable bổ sung, `app.orders.accepted` được đăng ký và có count bằng 2.

Đây là bằng chứng về mặc định của bộ lọc enable trong context thí nghiệm; một ứng dụng thật vẫn có thể có MeterFilter khác từ chối cùng tên.

### 7.2. Trường hợp tắt một tiền tố theo nhóm

Với `app.orders=false`:

```text
app.orders             -> từ chối
app.orders.accepted    -> từ chối
app.ordersx.accepted   -> vẫn cho phép
```

Kết quả vừa chứng minh tên đúng bằng khóa cũng bị tác động, vừa chứng minh ranh giới phần tên quan trọng. Không phải mọi tên có những ký tự đầu giống nhau đều thuộc cùng nhóm.

### 7.3. Trường hợp mở lại nhánh con

Ca exceptions dùng bốn quy tắc:

```text
all=false
app.orders=true
app.orders.debug=false
app.orders.debug.audit=true
```

Nhánh order thông thường hoạt động, nhánh debug bị chặn, nhánh debug.audit được mở lại, còn billing bị giá trị dự phòng all=false chặn.

Cách đọc phù hợp là tìm quy tắc cụ thể nhất của **từng tên**, không đọc các dòng như một danh sách lệnh bật/tắt chạy lần lượt để xóa hiệu lực của nhau.

### 7.4. Vì sao app.* có thể trông như wildcard dù bộ lọc không xử lý glob?

Đây là điểm hai ca cuối cố ý kiểm tra.

Trong ca star-normalized, đầu vào có:

```properties
management.metrics.enable.all=false
management.metrics.enable.app.*=true
```

Nhưng bản đồ sau binding được in ra là:

```text
{all=false, app=true}
```

Với nguồn cấu hình được dùng trong thí nghiệm Boot 3.3.0, dấu sao không được giữ nguyên trong khóa bản đồ. Quy tắc thực sự nhận được là `app=true`, nên cả tên đúng bằng `app` cũng được mở.

Ca literal-star giữ nguyên khóa bằng bracket notation:

```properties
management.metrics.enable.all=false
management.metrics.enable[app.*]=true
```

Bản đồ lúc này là:

```text
{all=false, app.*=true}
```

Tên `app.orders.accepted` không tìm thấy quy tắc `app.*` trong quá trình tra tên và nhóm cha, nên bị all=false chặn. **Giữ nguyên dấu sao không biến khóa thành biểu thức glob.**

Spring Boot mô tả quy tắc giữ ký tự đặc biệt trong khóa map tại [Binding Maps](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps). Hai ca trên là để chẩn đoán cách binding hoạt động, không phải mẫu cấu hình được khuyến nghị.

Để mở nhóm app, cách rõ ràng là:

```properties
management.metrics.enable.app=true
```

Không thêm `.*`, không viết regex và không dựa vào việc ký tự đặc biệt vô tình bị chuẩn hóa. Khi một cấu hình chứa ký tự đặc biệt cho kết quả khó hiểu, kiểm tra bản đồ đã bind thay vì suy ra thuật toán matching từ dòng đầu vào.

## 8. Áp dụng vào ứng dụng Boot và kiểm tra đúng tầng

### 8.1. Chọn quy tắc theo tên thực tế

Trong ứng dụng đã có Actuator, bắt đầu bằng các tên meter mà instrumentation thực sự đăng ký. Ví dụ, nếu có `jvm.memory.used`, `jvm.gc.pause`, `http.server.requests`, có thể tắt riêng nhóm hoặc từng tên đó.

Đặt quy tắc `management.metrics.enable.http_server_requests_seconds_count=false` không phải cách tắt timer Micrometer có tên `http.server.requests`. Hậu tố `_count` hoặc `_sum` là một phần của dữ liệu xuất theo backend, không nhất thiết là tên meter gốc.

### 8.2. Quan sát một lần chạy mới

Cấu hình một trường hợp kiểm chứng rõ ràng:

```yaml
management:
  metrics:
    enable:
      "app.orders": false
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Sau khi ứng dụng đã thực thi đường nghiệp vụ đăng ký counter, kiểm tra:

```shell
curl "http://localhost:8080/actuator/metrics"
curl "http://localhost:8080/actuator/metrics/app.orders.accepted"
```

Các URL trên dành cho ứng dụng web có cùng tên metric; chương trình console của bài không mở cổng HTTP. Địa chỉ, cổng, base path và yêu cầu xác thực theo cấu hình ứng dụng.

Khi chỉ có đường đăng ký chịu bộ lọc này, tên bị từ chối không xuất hiện như meter được chấp nhận trong registry tương ứng. Endpoint chi tiết có thể trả không tìm thấy; điều đó khác với lỗi không expose cả endpoint metrics.

Nếu có nhiều registry hoặc một composite registry, xác định registry con thực sự dùng để xuất dữ liệu. Không lấy kết quả trên một registry ngoài luồng xuất để kết luận toàn ứng dụng đã ngừng phát metric.

### 8.3. Xác minh cả hành vi được bật

Đổi quy tắc thành true, khởi động một context/tiến trình mới và tạo lại sự kiện. Xác nhận:

- Meter xuất hiện tại registry cần kiểm tra.
- Giá trị tăng theo sự kiện xác định.
- Các nhóm khác vẫn tuân theo quy tắc của chúng.
- Dữ liệu xuất tới backend phù hợp với tên và tag đã xác minh.

Thử cả nhánh bật lẫn tắt giúp phân biệt lỗi instrumentation chưa chạy với việc bộ lọc hoạt động đúng.

### 8.4. Không mặc định đây là công tắc thay đổi trực tiếp lúc đang chạy

Cấu hình chuẩn được áp dụng trong quá trình khởi tạo. Chỉ sửa file hoặc đổi giá trị trong Environment không phải cam kết rằng các meter đang tồn tại sẽ bị xóa, được tạo lại hoặc được bật/tắt ngay.

Để kiểm chứng bằng cơ chế chuẩn của bài, thay cấu hình rồi khởi động context/ứng dụng mới. Nếu hệ thống có cơ chế refresh riêng, phải xác minh hợp đồng của cơ chế đó đối với registry, meter đã cache và dữ liệu đã xuất.

Các mẫu bị chặn trong thời gian tắt cũng không được lưu để tự bù lại khi mở.

## 9. Phạm vi lọc và việc phối hợp các filter

### 9.1. Property này phân loại theo tên, không theo tag

Quy tắc:

```properties
management.metrics.enable.http.server.requests=false
```

tác động theo tên meter, không chỉ chọn một status, method hoặc URI cụ thể. Tương tự, `app.orders=false` không có cú pháp tích hợp ở đây để “chỉ tắt channel=web”.

Nếu nhu cầu là lọc theo tag, cần một cơ chế MeterFilter phù hợp hoặc thiết kế instrumentation khác. Đừng gắn điều kiện tag vào cuối tên property rồi mong Boot hiểu nó như một truy vấn label.

### 9.2. true chưa chắc là quyết định chấp nhận cuối cùng

Trong PropertiesMeterFilter của Boot 3.3.0:

- Kết quả enable false trả DENY.
- Kết quả enable true trả NEUTRAL để các filter khác còn được xét.

Vì vậy, true có thể vẫn bị filter khác từ chối. Ngược lại, một filter ACCEPT chạy trước có thể kết thúc sớm phần xét chấp nhận, khiến các filter sau không được hỏi ở bước đó.

Nếu cấu hình enable có vẻ không hiệu lực, kiểm tra các custom filter và thứ tự áp dụng thay vì lập tức thêm các quy tắc trùng nhau. Đây là hệ quả của chuỗi filter, không phải all hay quy tắc nhóm con tự thay đổi ý nghĩa.

### 9.3. Registry phải nằm trong phạm vi được cấu hình

Các property Boot không tự áp lên mọi đối tượng Java được tạo bằng `new SimpleMeterRegistry()`. Ưu tiên registry do Spring quản lý cho phần mã ứng dụng.

Thí nghiệm nhập auto-configuration metrics của Boot để kiểm chứng quá trình áp filter thật; nó không tự viết lại thuật toán lookup để tạo một kết quả mô phỏng.

## 10. Chọn nhóm hợp lý khi vận hành

Hai hướng cấu hình thường gặp:

| Hướng | Phù hợp khi | Điều cần xem xét |
| --- | --- | --- |
| Mặc định cho phép, tắt một số nhóm | Muốn giữ khả năng quan sát rộng và giảm vài nhóm không dùng | Nhóm mới có thể tự xuất hiện nếu instrumentation bổ sung |
| all=false, chỉ mở danh sách cần dùng | Muốn kiểm soát rõ các miền số liệu được phép | Phải cập nhật danh sách khi thêm metric cần cho chẩn đoán |

Không tắt một nhóm chỉ vì nó có nhiều tên nếu chưa biết dashboard hoặc cảnh báo nào đang phụ thuộc vào nó. Một thay đổi nhỏ như tắt `jvm` có thể làm mất cả dữ liệu bộ nhớ, luồng và GC, dù nhu cầu ban đầu chỉ là bỏ một nhánh.

Khi đã tắt ở nguồn, dashboard dùng dữ liệu lịch sử vẫn có thể hiển thị các điểm cũ trong cửa sổ truy vấn. Dữ liệu vắng mặt cũng không nên được tự diễn giải thành số đo bằng 0; hai trạng thái có ý nghĩa khác nhau.

## 11. Lỗi thường gặp và cách tự chẩn đoán

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách sửa |
| --- | --- | --- |
| Metric con vẫn bật dù nhóm cha false | Có quy tắc cụ thể hơn đặt true | Tra từ tên đầy đủ lên nhóm cha |
| all=false nhưng một số metric vẫn được đăng ký | Có ngoại lệ true, filter ACCEPT khác hoặc registry khác | Kiểm tra cấu hình hiệu lực, chuỗi filter và registry xuất |
| Dùng app.* và thấy nhóm app được mở | Khóa có thể đã được chuẩn hóa trong binding | Dùng app trực tiếp; kiểm tra bản đồ enable sau binding |
| Tắt tên Prometheus nhưng timer vẫn còn | Đang cấu hình theo tên xuất thay vì tên Micrometer | Dùng tên gốc như http.server.requests |
| Chỉ ẩn metrics khỏi HTTP nhưng backend vẫn có số liệu | Thay đổi exposure, chưa từ chối meter | Chọn đúng tầng điều khiển |
| Counter trả 0 dù nghiệp vụ có chạy | Có thể là NOOP counter do bị từ chối | Kiểm tra registry.find và quy tắc enable |
| Đặt true nhưng metric vẫn không có | Instrumentation chưa tạo meter hoặc filter khác từ chối | Tạo sự kiện xác định rồi kiểm tra các điều kiện còn lại |
| Sửa file nhưng tiến trình đang chạy không đổi | Không có cơ chế làm mới registry tương ứng | Thử với context mới và cấu hình hiệu lực đã xác minh |
| Một service vẫn phát dữ liệu đã tắt | Ghi vào registry riêng hoặc qua đường instrumentation khác | Kiểm tra nơi đăng ký và nơi xuất thật sự |

## 12. Thực hành

1. **Tắt nhóm cha, mở lại một tên con.** Với app.orders=false và app.orders.accepted=true, dự đoán kết quả của app.orders.accepted và app.orders.rejected rồi kiểm chứng trên context mới.
2. **Đổi giá trị dự phòng.** Giữ all=false nhưng thêm app.billing=true. Giải thích vì sao các metric order không tự được mở.
3. **Kiểm tra ranh giới tên.** So sánh app.orders.accepted với app.ordersx.accepted dưới quy tắc app.orders=false.
4. **Phân biệt NOOP và counter thật ở 0.** Kiểm tra sự hiện diện của meter trong registry bên cạnh giá trị count.
5. **Chọn đúng tầng.** Với yêu cầu “ngừng giữ nhóm JVM”, “chỉ bỏ URL metrics khỏi HTTP” và “ngừng xuất sang Prometheus”, chọn ba cấu hình tương ứng và giải thích phạm vi tác động.

Sau các thử nghiệm, cần xác định được tên nào đang được xét, quy tắc cụ thể nhất là gì và registry nào áp dụng quy tắc. Đây là cơ sở để bật/tắt nhóm metrics có chủ đích mà vẫn hiểu vì sao số liệu xuất hiện hoặc vắng mặt.
