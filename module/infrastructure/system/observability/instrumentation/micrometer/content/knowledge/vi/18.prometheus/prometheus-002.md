# Chọn registry Prometheus tương thích với thế hệ Prometheus Java Client

Micrometer cung cấp registry Prometheus để chuyển các meter trong ứng dụng Java thành định dạng mà Prometheus có thể scrape. Khi thêm dependency, cần xác định thế hệ Prometheus Java Client mà ứng dụng đang sử dụng. Prometheus Java Client 0.x (thường được gọi là simpleclient) và Prometheus Java Client 1.x có thay đổi lớn về package, API và cách quản lý registry. Micrometer cung cấp các artifact khác nhau để kết nối với từng thế hệ.

Lựa chọn registry phải khớp với phiên bản Micrometer, dependency management của Spring Boot và các thư viện Prometheus khác trên runtime classpath. Nếu trộn hai thế hệ client hoặc ghép registry với client không tương thích, ứng dụng có thể gặp lỗi biên dịch, lỗi nạp class hoặc lỗi khi khởi tạo registry.

## 1. Hai thế hệ Prometheus Java Client

Prometheus Java Client 0.x là thế hệ cũ, thường được gọi là simpleclient. API của thế hệ này dùng package io.prometheus.client và các kiểu như CollectorRegistry, Collector hoặc Counter.

Prometheus Java Client 1.x là thế hệ mới, có thay đổi namespace sang io.prometheus.metrics. Các artifact và API được tổ chức lại, bao gồm registry, model metrics và exporter. Đây là một thay đổi tương thích quan trọng khi ứng dụng có code tích hợp trực tiếp với Prometheus client.

| Nội dung | Client 0.x (simpleclient) | Client 1.x |
| --- | --- | --- |
| Namespace chính | io.prometheus.client.* | io.prometheus.metrics.* |
| Registry phía client | CollectorRegistry | PrometheusRegistry |
| Artifact thường gặp | simpleclient, simpleclient_hotspot | prometheus-metrics-core, các artifact prometheus-metrics-* |
| Tích hợp Micrometer ở dòng Micrometer mới | micrometer-registry-prometheus-simpleclient | micrometer-registry-prometheus |
| Phù hợp khi | Thư viện hoặc code cũ còn phụ thuộc simpleclient | Ứng dụng mới hoặc hệ sinh thái đã chuyển sang client 1.x |

Không thể thay một artifact client 0.x bằng artifact 1.x chỉ bằng cách đổi số phiên bản. Namespace và hợp đồng API đã thay đổi; code sử dụng trực tiếp các class của client cũng cần được chuyển đổi.

## 2. Artifact registry tương ứng trong Micrometer

Từ Micrometer 1.13, tích hợp Prometheus được tách rõ theo thế hệ client:

- micrometer-registry-prometheus sử dụng Prometheus Java Client 1.x.
- micrometer-registry-prometheus-simpleclient sử dụng Prometheus Java Client 0.x (simpleclient).

Với các dòng Micrometer cũ hơn 1.13, artifact micrometer-registry-prometheus thuộc tích hợp simpleclient cũ. Vì vậy, khi đọc hướng dẫn hoặc ví dụ trên Internet, cần xem cả phiên bản Micrometer mà tài liệu đang nói đến. Cùng tên artifact micrometer-registry-prometheus có thể mang implementation khác nhau giữa các dòng Micrometer.

| Dòng Micrometer | Artifact registry | Thế hệ client |
| --- | --- | --- |
| Micrometer trước 1.13 | micrometer-registry-prometheus | Prometheus Java Client 0.x |
| Micrometer 1.13 trở lên | micrometer-registry-prometheus | Prometheus Java Client 1.x |
| Micrometer 1.13 trở lên, cần giữ client cũ | micrometer-registry-prometheus-simpleclient | Prometheus Java Client 0.x |

Hãy kiểm tra tài liệu của đúng phiên bản Micrometer đang được dependency management chọn. Không lấy tên artifact từ một ví dụ mới rồi áp dụng nguyên trạng cho một dự án đang dùng Micrometer cũ.

## 3. Chọn registry theo Spring Boot dependency management

Spring Boot quản lý phiên bản Micrometer thông qua dependency BOM. Khi dự án dùng Spring Boot, nên để BOM chọn phiên bản Micrometer và registry tương thích, trừ khi có yêu cầu nâng cấp đã được kiểm tra rõ ràng.

Ví dụ Gradle Kotlin DSL cho ứng dụng Spring Boot dùng registry Prometheus hiện hành:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Hai ví dụ trên dựa vào dependency management của Spring Boot để chọn phiên bản. Nếu ứng dụng cần giữ Prometheus Java Client 0.x trong một dòng Micrometer có hỗ trợ artifact legacy, thay artifact registry bằng:

~~~kotlin
runtimeOnly("io.micrometer:micrometer-registry-prometheus-simpleclient")
~~~

Chỉ chọn artifact legacy khi có lý do tương thích cụ thể, chẳng hạn một thư viện nội bộ hoặc custom collector vẫn phụ thuộc API simpleclient. Trước khi đổi, hãy kiểm tra toàn bộ runtime classpath và code nào đang import trực tiếp package Prometheus.

### Mốc chuyển đổi của Spring Boot

Spring Boot 3.3 chuyển sang dòng Micrometer 1.13, vì vậy tích hợp Prometheus mặc định của dòng này dùng Prometheus Java Client 1.x. Spring Boot 3.2 thuộc dòng Micrometer 1.12 và tích hợp Prometheus simpleclient cũ.

Đây là mốc tham khảo theo các dòng phát hành nền tảng. Các dự án có thể override BOM hoặc nâng riêng dependency, nên phiên bản thực tế trên runtime classpath mới là căn cứ cuối cùng. Không suy ra thế hệ client chỉ từ tên Spring Boot hoặc từ một khai báo dependency riêng lẻ.

## 4. Package API giúp nhận diện thế hệ client

Khi ứng dụng tự tạo PrometheusMeterRegistry, package import cho biết registry đang dùng thế hệ nào.

Với Prometheus Java Client 1.x và artifact micrometer-registry-prometheus trong Micrometer 1.13 trở lên:

~~~java
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;

PrometheusMeterRegistry registry =
    new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
~~~

Với Prometheus Java Client 0.x và artifact micrometer-registry-prometheus-simpleclient:

~~~java
import io.micrometer.prometheus.PrometheusConfig;
import io.micrometer.prometheus.PrometheusMeterRegistry;

PrometheusMeterRegistry registry =
    new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
~~~

Hai ví dụ có cách khởi tạo tương tự nhưng package khác nhau. Không thay package bằng phỏng đoán; hãy để IDE hoặc compiler xác nhận class đến từ artifact registry nào trên classpath.

Nếu ứng dụng chỉ inject MeterRegistry và để Spring Boot auto-configure, thường không cần import trực tiếp PrometheusMeterRegistry. Khi đó registry implementation được chọn bởi dependency và auto-configuration.

## 5. Khác biệt khi code trực tiếp với Prometheus client

Một số ứng dụng chỉ dùng API Micrometer, nhưng một số khác còn khai báo collector, registry hoặc exporter trực tiếp từ Prometheus Java Client. Khi chuyển từ 0.x sang 1.x, phần code tích hợp trực tiếp này cần được rà soát.

Ví dụ về namespace registry:

~~~java
// Prometheus Java Client 0.x
import io.prometheus.client.CollectorRegistry;

CollectorRegistry collectorRegistry = new CollectorRegistry();
~~~

~~~java
// Prometheus Java Client 1.x
import io.prometheus.metrics.model.registry.PrometheusRegistry;

PrometheusRegistry prometheusRegistry = new PrometheusRegistry();
~~~

CollectorRegistry và PrometheusRegistry thuộc hai API khác nhau. Không truyền object của thế hệ này vào constructor hoặc adapter của thế hệ kia. Custom collector, instrumentation JVM và exporter HTTP cũng cần dùng artifact/API đúng thế hệ.

Nếu code chỉ gọi API Micrometer như registry.counter(...), Timer.builder(...) hoặc Gauge.builder(...), phần lớn mã instrumentation không cần phụ thuộc trực tiếp vào Prometheus client. Đây là một lợi ích của lớp abstraction Micrometer: có thể đổi registry mà không phải viết lại logic đo lường nghiệp vụ, miễn là không ràng buộc vào API riêng của backend.

## 6. Cấu hình endpoint scrape trong Spring Boot

Khi dùng Spring Boot Actuator cùng Prometheus registry, endpoint thường được expose tại /actuator/prometheus. Có thể cấu hình:

~~~properties
management.endpoints.web.exposure.include=health,prometheus
~~~

Prometheus scrape endpoint của ứng dụng bằng cấu hình tương tự:

~~~yaml
scrape_configs:
  - job_name: order-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - localhost:8080
~~~

Endpoint Actuator cung cấp dữ liệu theo registry đã được Spring Boot cấu hình. Với cùng endpoint và cùng cấu hình exposure, việc đổi thế hệ client chủ yếu nằm ở dependency và implementation phía ứng dụng; cấu hình scrape phía Prometheus thường không cần đổi chỉ vì thay client Java.

Tuy nhiên, hãy kiểm tra nội dung exposition sau khi đổi registry. Naming convention, kiểu histogram, exemplar hoặc các khả năng riêng của client có thể ảnh hưởng đến cách dữ liệu được xuất và truy vấn.

## 7. Kiểm tra dependency graph trước khi chọn

Đừng chỉ nhìn file build. Một thư viện khác có thể kéo theo simpleclient hoặc Prometheus client 1.x thông qua dependency bắc cầu. Hãy kiểm tra runtime classpath để biết artifact thực sự được giải quyết.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency micrometer-registry-prometheus \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency prometheus \
  --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=io.micrometer,io.prometheus
~~~

Các dấu hiệu thường gặp:

| Artifact hoặc package | Gợi ý thế hệ |
| --- | --- |
| io.prometheus:simpleclient | Client 0.x |
| io.prometheus:simpleclient_hotspot | Instrumentation JVM của client 0.x |
| io.prometheus:prometheus-metrics-core | Client 1.x |
| io.prometheus:prometheus-metrics-model | Client 1.x |
| io.prometheus.metrics.* | API client 1.x |
| io.prometheus.client.* | API client 0.x |

Tên artifact cụ thể có thể khác theo phiên bản và tính năng được dùng. Hãy xem toàn bộ cây dependency, bao gồm cả các module exporter và instrumentation, thay vì chỉ tìm một dòng trong file khai báo.

## 8. Tránh trộn hai thế hệ client

Một số tình huống dễ gây xung đột:

- Thêm cả micrometer-registry-prometheus và micrometer-registry-prometheus-simpleclient mà không có yêu cầu rõ ràng.
- Thêm trực tiếp một phiên bản simpleclient không khớp với registry legacy.
- Nâng registry lên client 1.x nhưng vẫn dùng custom collector được viết cho io.prometheus.client.
- Có thư viện khác yêu cầu client 0.x trong khi ứng dụng đã chuyển sang client 1.x.
- Override riêng một module Micrometer làm các module Micrometer khác lệch phiên bản.

Lỗi có thể xuất hiện dưới dạng ClassNotFoundException, NoClassDefFoundError, NoSuchMethodError, lỗi cast hoặc lỗi khởi tạo registry. Một số xung đột chỉ xảy ra lúc chạy nên compile thành công chưa đủ chứng minh classpath tương thích.

Không cố giải quyết bằng cách thêm mọi artifact vào dependency list. Trước hết xác định thư viện nào yêu cầu client nào, sau đó chọn một thế hệ làm chuẩn hoặc lên kế hoạch chuyển đổi thư viện phụ thuộc. Chỉ dùng cả hai thế hệ trong cùng ứng dụng nếu kiến trúc và các integration thực sự tách biệt, đã xác minh không xung đột và có lý do cụ thể.

## 9. Quy trình chuyển từ simpleclient sang client 1.x

Khi muốn chuyển ứng dụng từ Prometheus Java Client 0.x sang 1.x:

1. Kiểm tra Spring Boot BOM và phiên bản Micrometer đang được quản lý.
2. Liệt kê dependency trực tiếp và bắc cầu liên quan đến io.prometheus.
3. Xác định custom collector, servlet exporter hoặc instrumentation nào import io.prometheus.client.
4. Chọn micrometer-registry-prometheus khi dùng client 1.x trong Micrometer 1.13 trở lên.
5. Chuyển code Prometheus client trực tiếp sang namespace và API 1.x nếu có.
6. Loại bỏ artifact simpleclient cũ khi không còn thư viện nào cần nó.
7. Kiểm tra runtime dependency tree để xác nhận không còn xung đột ngoài dự kiến.
8. Khởi động ứng dụng và kiểm tra registry được tạo thành công.
9. Scrape endpoint, xác minh tên metric, tags, counter, timer và histogram.
10. Chạy thử truy vấn/dashboard/alert quan trọng để phát hiện thay đổi trong exposition.

Nếu chưa thể chuyển toàn bộ thư viện phụ thuộc, có thể tiếp tục dùng registry simpleclient tương ứng trong dòng Micrometer hỗ trợ nó. Cần ghi nhận rõ lý do giữ client cũ và kế hoạch loại bỏ phụ thuộc legacy.

## 10. Kiểm thử registry được chọn

Kiểm thử nên xác nhận cả hai lớp: Micrometer đăng ký meter đúng và Prometheus registry export dữ liệu đúng.

Ví dụ kiểm tra meter với API Micrometer:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class OrderMetrics {

    private final Counter created;

    public OrderMetrics(MeterRegistry registry) {
        this.created = registry.counter(
            "orders.created",
            "channel", "web"
        );
    }

    public void recordCreated() {
        created.increment();
    }
}
~~~

Với integration test, có thể khởi tạo ứng dụng cùng registry Prometheus đã chọn, gọi recordCreated() rồi đọc endpoint scrape hoặc nội dung scrape của registry. Xác minh:

- Metric orders.created xuất hiện.
- Tag channel có giá trị web.
- Counter tăng đúng sau thao tác.
- Timer và histogram có bucket theo cấu hình nếu ứng dụng sử dụng chúng.
- Không có lỗi khởi tạo do thiếu class hoặc API không tương thích.
- Endpoint được expose và Prometheus có thể scrape.

Một unit test chỉ dùng SimpleMeterRegistry không kiểm tra được Prometheus client generation, vì registry đó không sử dụng Prometheus exporter. Cần ít nhất một integration test với đúng dependency registry sẽ chạy trong production.

## 11. Bảng quyết định chọn registry

| Tình huống dự án | Lựa chọn |
| --- | --- |
| Ứng dụng mới, Spring Boot/Micrometer hiện hành và không có phụ thuộc simpleclient | micrometer-registry-prometheus |
| Micrometer 1.13 trở lên, một thư viện còn yêu cầu Prometheus Java Client 0.x | Cân nhắc micrometer-registry-prometheus-simpleclient và xác minh toàn bộ dependency graph |
| Dự án dùng Micrometer trước 1.13 | Dùng artifact micrometer-registry-prometheus theo implementation simpleclient của dòng đó |
| Code có custom collector dùng io.prometheus.client.* | Giữ registry simpleclient tương thích hoặc chuyển collector sang API 1.x trước khi đổi |
| Ứng dụng chỉ dùng API Micrometer và muốn giảm phụ thuộc backend | Ưu tiên registry do BOM hiện hành quản lý, tránh import API Prometheus trực tiếp |

Quyết định cuối cùng cần dựa trên phiên bản Micrometer thực tế và runtime classpath. Một dự án có thể khai báo đúng artifact nhưng vẫn không tương thích nếu thư viện khác kéo vào API Prometheus thuộc thế hệ còn lại.

## 12. Checklist trước khi phát hành

- [ ] Đã xác định phiên bản Micrometer được Spring Boot BOM quản lý.
- [ ] Đã xác định registry artifact tương ứng với Prometheus Java Client 0.x hoặc 1.x.
- [ ] Không override rời rạc các module Micrometer.
- [ ] Đã kiểm tra runtime dependency tree và dependency bắc cầu.
- [ ] Custom collector/exporter dùng đúng namespace và API.
- [ ] Ứng dụng khởi tạo được registry trong môi trường tích hợp.
- [ ] Endpoint /actuator/prometheus trả về dữ liệu khi được cấu hình.
- [ ] Prometheus scrape thành công.
- [ ] Metric name, tags, counter và histogram được xác minh.
- [ ] Dashboard và alert quan trọng vẫn truy vấn đúng dữ liệu sau thay đổi.

Micrometer giúp mã nghiệp vụ không phụ thuộc trực tiếp vào Prometheus Java Client, nhưng registry vẫn phải được ghép với đúng thế hệ client. Hãy để Spring Boot BOM quản lý phiên bản khi có thể, kiểm tra package và dependency graph khi dự án có tích hợp Prometheus trực tiếp, rồi xác minh bằng endpoint scrape thực tế. Cách làm này giảm lỗi tương thích và giúp quá trình nâng cấp client có thể kiểm soát.
