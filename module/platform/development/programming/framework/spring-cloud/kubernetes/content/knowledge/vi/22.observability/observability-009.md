# Tránh nhãn có quá nhiều giá trị và tránh lộ Secret

Trong chương **Khả năng quan sát** của module **Spring Cloud Kubernetes**, bài này hướng dẫn thiết kế telemetry đủ để điều tra sự cố mà vẫn kiểm soát được số chuỗi thời gian và dữ liệu nhạy cảm.

Ứng dụng có thể dùng DiscoveryClient để tìm instance, đọc ConfigMap/Secret, gọi dịch vụ qua Spring Cloud LoadBalancer và nhận thông báo từ Configuration Watcher. Mỗi thành phần tạo ra cơ hội quan sát, đồng thời tạo đường đưa metadata hoặc cấu hình vào metric, log, trace và Actuator. Cần chọn từng trường được công bố theo mục đích sử dụng.

## Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Phân biệt nhãn Kubernetes, metadata discovery và nhãn metric.
- Ước lượng tác động của cardinality và nhận ra giá trị không có giới hạn hợp lý.
- Thiết kế một tập nhãn hữu hạn trước khi đăng ký meter.
- Phân biệt giảm cardinality với bảo vệ Secret.
- Cấu hình mức công bố dữ liệu phù hợp cho discovery và Actuator.
- Kiểm tra bằng dữ liệu giả để tìm đường rò rỉ trước khi dùng cấu hình thật.

Ví dụ Java dùng Spring Boot 3.5, Java 17 trở lên, Micrometer dòng 1.15 và Spring Cloud Kubernetes dòng 3.3 với BOM tương thích. Đối chiếu lại thuộc tính và API nếu dự án dùng release khác. Các đoạn cấu hình là ví dụ cho ứng dụng thử nghiệm; không phải kết quả đã triển khai trên cluster của bạn.

## 1. Ba loại nhãn dễ bị nhầm

| Khái niệm | Nằm ở đâu? | Vai trò |
| --- | --- | --- |
| Kubernetes label | Metadata của Pod, Service hoặc tài nguyên khác | Tổ chức, chọn và liên kết tài nguyên |
| Metadata của ServiceInstance | Dữ liệu DiscoveryClient trả về | Cung cấp thông tin của đích mà client tìm được |
| Metric label/tag | Bộ định danh meter hoặc chuỗi thời gian | Chia dữ liệu đo theo các chiều truy vấn |

Ví dụ Kubernetes label `app.kubernetes.io/name=orders-api` không tự trở thành nhãn của mọi metric. Nó có thể được đưa vào telemetry qua code ứng dụng, cơ chế enrichment hoặc cấu hình collector/scraper.

Nếu một pipeline chép toàn bộ metadata từ Kubernetes sang nhãn metric, một thay đổi triển khai có thể đồng thời làm tăng số chuỗi thời gian và mở rộng dữ liệu được công bố.

~~~mermaid
flowchart LR
    Sources["Request, cấu hình và Kubernetes metadata"] --> App["Instrumentation trong ứng dụng"]
    Sources --> Collector["Enrichment của collector hoặc scraper"]
    App --> Signals["Metrics, logs, traces và Actuator"]
    Collector --> Signals
    Signals --> Store["Backend, truy vấn, dashboard và cảnh báo"]
~~~

Bảo vệ chỉ tại dashboard là quá muộn để ngăn dữ liệu đã được gửi đến backend. Cần hiểu đường đi từ nguồn đến từng nơi nhận.

### 1.1. Cardinality là số giá trị phân biệt

Một nhãn `outcome` có ba giá trị `success`, `timeout`, `failure` có cardinality nhỏ và dễ dự tính. Nhãn `orderId` có một giá trị mới cho mỗi đơn hàng tiếp tục tăng theo hoạt động nghiệp vụ.

Những trường thường cần loại khỏi nhãn metric gồm request ID, trace ID, session ID, email, URL đầy đủ chứa ID hoặc query string, timestamp và thông báo exception nguyên văn. URL theo mẫu như `/orders/{id}` hữu ích hơn URL của từng đơn hàng. Xem [Micrometer: high cardinality](https://docs.micrometer.io/micrometer/reference/1.15/concepts/high-cardinality-tags-detector.html).

Cardinality thấp vẫn có thể không an toàn. Một nhãn chỉ có một giá trị nhưng giá trị đó là mật khẩu vẫn là rò rỉ. Ngược lại, Pod UID không nhất thiết là Secret nhưng có thể tạo quá nhiều chuỗi thời gian.

### 1.2. Mỗi tổ hợp nhãn tạo thêm định danh

Với một metric, có thể dùng tích số lượng giá trị của các nhãn để ước lượng giới hạn trên:

~~~text
6 mẫu route × 3 outcome × 4 dependency × 10 instance = 720 tổ hợp

Nếu thêm 20.000 orderId:
720 × 20.000 = 14.400.000 tổ hợp có thể có
~~~

Đây là giới hạn minh họa, không phải mọi tổ hợp đều xuất hiện trong thực tế. Histogram còn có thể tạo thêm các series bucket, count và sum. Nhiều metric có cùng tập nhãn làm chi phí tăng tiếp.

Prometheus định danh chuỗi thời gian theo tên metric cùng tập nhãn, vì vậy nhãn không giới hạn tạo chi phí lưu trữ và xử lý. Xem [Prometheus: metric and label naming](https://prometheus.io/docs/practices/naming/).

Việc chỉ dùng một số nhãn trong truy vấn dashboard không làm biến mất các chiều đã được thu thập.

### 1.3. Tập giá trị hiện tại nhỏ chưa đủ

Một nhãn `podName` có thể chỉ có ba giá trị ở một thời điểm, nhưng mỗi rollout tạo tên Pod mới. Trong thời gian lưu trữ dài, tổng số giá trị đã xuất hiện vẫn tăng.

Điều tương tự xảy ra với image digest, commit SHA, checksum cấu hình hoặc resourceVersion. Chúng có thể hữu ích để truy vết một lần triển khai, nhưng cần cân nhắc vị trí lưu và tần suất thay đổi trước khi thêm vào mọi metric.

Nhãn mặc định của scraper như `instance` cũng có thể thay đổi khi Pod được thay thế. Bỏ một nhãn Pod tùy chỉnh không có nghĩa đã loại hết biến động danh tính target.

## 2. Lập hợp đồng cho dữ liệu quan sát

Với mỗi metric, xác định tên nhãn, tập giá trị, nguồn tạo và giới hạn kỳ vọng. Ví dụ cho phép đo gọi dependency:

| Trường | Quyết định minh họa | Lý do |
| --- | --- | --- |
| `application` | Tên ứng dụng ổn định | So sánh giữa ứng dụng |
| `environment` | Tập môi trường do hệ thống định nghĩa | Có giới hạn theo triển khai |
| `namespace` | Namespace trong phạm vi theo dõi | Hữu ích nếu số namespace được kiểm soát |
| `dependency` | `inventory`, `payments`, `other` | Không nhận tên đích tùy ý từ request |
| `outcome` | `success`, `timeout`, `failure` | Phân loại lỗi hữu hạn |
| `orderId` | Không đưa vào metric label | Tăng theo số đơn hàng |
| `podIp` | Chỉ dùng trong chi tiết chẩn đoán khi cần | Địa chỉ thay đổi theo topology |
| `Authorization` | Không đưa vào telemetry | Có thể chứa thông tin xác thực |
| Giá trị Secret | Không đưa vào telemetry | Không phục vụ phép đo tổng hợp |

Các giới hạn phải xét toàn hệ thống. Một nhãn namespace hữu hạn ở một cluster nhỏ có thể tăng đáng kể khi mở rộng theo tenant hoặc tạo môi trường tạm cho từng nhánh mã.

### 2.1. Danh sách cho phép cần áp dụng cả tên lẫn giá trị

Chỉ cho phép khóa `dependency` chưa đủ. Nếu giá trị vẫn lấy từ `request.getParameter("target")`, người gọi có thể tạo vô số giá trị mới.

Tương tự, đổi tên khóa `password` thành `connection` không làm nội dung bớt nhạy cảm. Cần biết dữ liệu đến từ đâu và được biến đổi như thế nào.

Một quy tắc thiết kế phù hợp:

~~~text
Giá trị thuộc miền đã biết -> ánh xạ sang nhãn chuẩn
Giá trị chưa biết         -> "other" hoặc không ghi trường đó
Dữ liệu bí mật           -> không đưa vào telemetry ngay từ đầu
~~~

Không nối phần chưa biết vào `other-` rồi giữ nguyên giá trị gốc; cách đó vẫn tạo nhãn không giới hạn.

### 2.2. Phân biệt khả năng truy vết với nhãn metric

Metric trả lời các câu hỏi tổng hợp như tỷ lệ timeout theo dependency. Log hoặc trace có thể chứa một số định danh không bí mật để truy vết request khi có chính sách truy cập và lưu trữ phù hợp.

Micrometer Observation phân biệt low-cardinality và high-cardinality key-value. High-cardinality không có nghĩa dữ liệu được giữ kín; dữ liệu vẫn có thể đến tracing hoặc các handler khác. Xem [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).

Không chuyển mật khẩu, token, cookie phiên hoặc giá trị Secret sang `highCardinalityKeyValue` để “tránh metric”. Sampling cũng không ngăn một mẫu có chứa bí mật bị xuất ra.

## 3. Giới hạn nhãn ngay trong instrumentation

Ví dụ sau tạo metric `learning.dependency.calls` cho ba nhóm dependency và ba nhóm kết quả. Đây là metric tùy chỉnh của bài học, không phải metric mặc định của Spring Cloud Kubernetes.

Ứng dụng Spring Boot cần có Actuator/Micrometer. Nếu muốn xuất Prometheus, thêm registry tương ứng do BOM quản lý. Lớp chỉ sử dụng API Micrometer, không cần quyền đọc Kubernetes API.

~~~java
package com.example.orders;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class DependencyCallMetrics {

    private static final Set<String> DEPENDENCIES =
            Set.of("inventory", "payments", "other");

    private final Map<Key, Counter> counters;

    public DependencyCallMetrics(MeterRegistry registry) {
        Map<Key, Counter> created = new HashMap<>();

        for (String dependency : DEPENDENCIES) {
            for (Outcome outcome : Outcome.values()) {
                Counter counter = Counter.builder("learning.dependency.calls")
                        .tag("dependency", dependency)
                        .tag("outcome",
                                outcome.name().toLowerCase(Locale.ROOT))
                        .register(registry);
                created.put(new Key(dependency, outcome), counter);
            }
        }

        this.counters = Map.copyOf(created);
    }

    public void record(String dependency, Outcome outcome) {
        Objects.requireNonNull(outcome, "outcome is required");

        String normalized = switch (dependency == null ? "" : dependency) {
            case "inventory" -> "inventory";
            case "payments" -> "payments";
            default -> "other";
        };

        counters.get(new Key(normalized, outcome)).increment();
    }

    public enum Outcome {
        SUCCESS, TIMEOUT, FAILURE
    }

    private record Key(String dependency, Outcome outcome) {
    }
}
~~~

Ví dụ sử dụng sau khi một lần gọi đã hoàn tất:

~~~java
metrics.record("inventory", DependencyCallMetrics.Outcome.SUCCESS);
metrics.record("payments", DependencyCallMetrics.Outcome.TIMEOUT);
metrics.record("unexpected-target", DependencyCallMetrics.Outcome.FAILURE);
~~~

Lần gọi thứ ba được ghi vào `dependency=other`; chuỗi `unexpected-target` không được dùng làm tag hay tên meter. Lớp đăng ký trước chín tổ hợp và không thêm tổ hợp theo từng request.

Giới hạn chín meter chỉ áp dụng cho metric này trong một registry, với cấu hình nhãn như ví dụ. Backend vẫn có thể phân biệt target, common tag hoặc các chiều được thêm ở tầng khác.

Không đưa tên dịch vụ tùy ý từ `DiscoveryClient.getServices()`, hostname hoặc toàn bộ URI của instance vào tag chỉ vì chúng đang có trong bộ nhớ. Trước hết, xác định nhóm dependency nghiệp vụ ổn định cần quan sát.

### 3.1. Kiểm tra tính hữu hạn của phép ánh xạ

Có thể kiểm tra riêng lớp bằng `SimpleMeterRegistry` và JUnit 5:

~~~java
package com.example.orders;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DependencyCallMetricsTest {

    @Test
    void unknownDependenciesShareOneBucket() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            DependencyCallMetrics metrics = new DependencyCallMetrics(registry);

            for (int index = 0; index < 1000; index++) {
                metrics.record("unknown-" + index,
                        DependencyCallMetrics.Outcome.FAILURE);
            }

            assertEquals(9, registry.getMeters().size());
            assertEquals(1000.0, registry.get("learning.dependency.calls")
                    .tags("dependency", "other", "outcome", "failure")
                    .counter().count(), 0.0);
        }
    }
}
~~~

Đây là ví dụ kiểm thử cho người học, chưa phải kiểm thử đã chạy trong repository. Nó kiểm tra số meter và giá trị tổng hợp; không chỉ kiểm tra một chuỗi đầu ra dễ trùng với implementation.

### 3.2. Dùng MeterFilter làm giới hạn bổ sung

Có thể đặt giới hạn cho tag của nhóm metric đã chọn:

~~~java
package com.example.orders;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricBudgetConfiguration {

    @Bean
    MeterFilter dependencyTagBudget() {
        return MeterFilter.maximumAllowableTags(
                "learning.dependency.calls", "dependency",
                3, MeterFilter.deny());
    }

    @Bean
    MeterFilter outcomeTagBudget() {
        return MeterFilter.maximumAllowableTags(
                "learning.dependency.calls", "outcome",
                3, MeterFilter.deny());
    }
}
~~~

Filter áp dụng theo prefix tên meter và giới hạn số giá trị phân biệt của tag trong phạm vi đó. Nó không tự biến các giá trị vượt giới hạn thành `other`. Khi bị từ chối, meter nhận được là loại không ghi nhận phép đo; dữ liệu của tổ hợp đó có thể bị mất. Xem [Micrometer Meter Filters 1.15](https://docs.micrometer.io/micrometer/reference/1.15/concepts/meter-filters.html).

Các giới hạn cần nhớ:

- Giới hạn số giá trị không xác nhận giá trị thuộc danh sách cho phép. Ba giá trị đầu tiên vẫn có thể sai hoặc nhạy cảm.
- Giới hạn cho một tag không phải giới hạn tổng số meter của toàn registry.
- Filter không xóa dữ liệu đã xuất trước đó và không bảo vệ các log/trace riêng.
- Cần quan sát dấu hiệu từ chối hoặc thiếu dữ liệu bằng tín hiệu hữu hạn; không ghi lại nguyên giá trị bị chặn.
- Kiểm tra thứ tự filter, đặc biệt nếu có filter chấp nhận meter sớm.

Phép ánh xạ trong code vẫn là nơi kiểm soát miền giá trị. Giới hạn bổ sung không thay thế việc xử lý dữ liệu trước khi đăng ký meter hoặc trước khi lưu vào các cache riêng.

### 3.3. Không chuyển giá trị động sang tên metric

Các tên như `orders.<orderId>.duration` hoặc `dependency.<host>.calls` vẫn tạo số lượng tên không giới hạn, dù không có tag động. Giữ tên metric cố định và chỉ sử dụng các chiều đã được thiết kế.

Tương tự, băm một ID thành chuỗi khác không làm giảm số giá trị phân biệt. Cắt chuỗi có thể giảm chiều dài nhưng không tạo được một miền nhỏ có ý nghĩa nghiệp vụ.

## 4. Kiểm soát metadata của Spring Cloud Kubernetes

### 4.1. Không sao chép toàn bộ ServiceInstance vào telemetry

Một lệnh ghi log như `log.info("instance={}", instance)` có thể kéo theo metadata nhiều hơn mong muốn. Việc chép `getMetadata()` thành toàn bộ tag của meter còn khiến nhãn Kubernetes trở thành các chiều metric ngoài dự tính.

Thay vì trả hoặc ghi cả đối tượng, tạo DTO riêng với các trường đã phê duyệt. Ví dụ, một endpoint quản trị có thể chỉ trả alias dịch vụ, số đích đang thấy và thời điểm đọc; danh sách IP hoặc UID chi tiết chỉ mở cho nhu cầu chẩn đoán đã xác định.

Metadata có thể chứa annotation do công cụ triển khai, người dùng hoặc hệ thống khác thêm vào. Không coi metadata là một tập dữ liệu đã được phân loại an toàn.

### 4.2. Tắt phần metadata không có consumer

Với ứng dụng chỉ cần địa chỉ/cổng discovery và đã xác nhận không có thành phần cần các trường metadata tương ứng, có thể dùng:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        metadata:
          add-labels: false
          add-annotations: false
          add-ports: false
          add-pod-labels: false
          add-pod-annotations: false
~~~

Các cờ này điều khiển dữ liệu discovery, không phải một bộ lọc cho mọi metric, log hoặc collector. Danh sách thuộc tính được mô tả tại [Spring Cloud Kubernetes: discovery metadata](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Không áp dụng cấu hình này máy móc nếu Configuration Watcher, routing hoặc công cụ khác đang dùng nhãn/annotation để tìm ứng dụng hay management endpoint. Xác định đúng consumer và release, giữ các trường cần cho chức năng, rồi kiểm soát riêng phần đưa vào telemetry.

Nếu cần theo dõi thay đổi ConfigMap/Secret, các nhãn phục vụ Watcher chỉ nên chứa chỉ dẫn hoặc định danh phù hợp, không chứa giá trị cấu hình bí mật. Các nhãn kích hoạt theo dõi được trình bày trong [Configuration Watcher 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

### 4.3. Kiểm tra cả enrichment ngoài ứng dụng

Tắt metadata trong DiscoveryClient không ngăn Prometheus hoặc OpenTelemetry Collector tự đọc metadata Kubernetes bằng tài khoản của chúng.

Trong Prometheus Kubernetes service discovery dùng role `pod`, một phần `relabel_configs` chọn lọc có thể là:

~~~yaml
relabel_configs:
  - source_labels: [__meta_kubernetes_namespace]
    target_label: namespace
  - source_labels: [__meta_kubernetes_pod_label_app_kubernetes_io_name]
    target_label: workload
~~~

Đây chỉ là đoạn chọn nhãn, chưa phải scrape job hoàn chỉnh. Không mặc định chép mọi Pod label bằng một quy tắc `labelmap` rộng. Kiểm tra cách đổi tên, nhãn sẵn có và chính sách xử lý xung đột trong pipeline. Xem [Prometheus configuration: relabeling](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#relabel_config).

Đồng thời, không xóa tùy ý nhãn phân biệt target để ép giảm số series. Việc hợp nhất các mẫu của các tiến trình khác nhau có thể phá ý nghĩa dữ liệu. Giảm chiều không cần thiết phải đi cùng bảo toàn danh tính phép đo.

## 5. Secret có thể rời khỏi nơi lưu ban đầu

Kubernetes Secret dành cho dữ liệu nhạy cảm; ConfigMap dành cho cấu hình không bí mật. Base64 trong trường `data` là biểu diễn dữ liệu, không phải cơ chế giữ kín nội dung đối với người đã đọc được nó. Xem [Good practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

Khi ứng dụng đọc Secret vào biến môi trường, file hoặc Spring Environment, dữ liệu đó có thể đi qua code thông thường. Một lệnh serialize hoặc ghi log không tự biết giá trị ban đầu đến từ Secret.

| Đường rò rỉ | Ví dụ cần tránh | Cách giữ thông tin hữu ích |
| --- | --- | --- |
| Metric | Tag chứa token hoặc URL có credential | Dùng dependency alias và nhóm kết quả |
| Log | Dump cấu hình, request header hoặc body | Ghi tên sự kiện và các trường đã phê duyệt |
| Trace | Attribute chứa cookie, token hoặc Secret | Chỉ giữ thuộc tính phù hợp cho chẩn đoán |
| Baggage | Truyền thông tin xác thực như dữ liệu quan sát | Không đưa credential vào baggage |
| Actuator tùy chỉnh | Trả nguyên đối tượng cấu hình | Trả DTO với trường công bố rõ ràng |
| Kubernetes metadata | Đưa mật khẩu vào label/annotation | Giữ dữ liệu bí mật trong cơ chế Secret phù hợp |
| Thông báo lỗi | In nguyên connection string hoặc payload | Phân loại lỗi và dùng chi tiết đã làm sạch |

Không coi một chuỗi “đã mã hóa base64”, một phần đầu token hoặc một fingerprint của mật khẩu là dữ liệu mặc nhiên an toàn. Băm cũng không loại bỏ cardinality và có thể cho phép đoán dữ liệu có miền giá trị nhỏ. Nguyên tắc xử lý dữ liệu nhạy cảm trong telemetry được thảo luận tại [OpenTelemetry: handling sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/).

### 5.1. Tránh dump cấu hình và đối tượng tự có toString

Một `record` Java có field password có thể đưa field đó vào `toString()` được sinh tự động. Lombok hoặc các công cụ sinh mã cũng cần được xem xét khi kiểu dữ liệu chứa credential.

Không ghi log nguyên đối tượng `@ConfigurationProperties`, `PropertySource`, Map cấu hình hoặc danh sách biến môi trường để xác nhận “đã đọc Secret thành công”.

Để xác nhận một thao tác refresh, có thể chỉ ghi thông tin sự kiện:

~~~java
log.info("event=config.refresh.complete source={} result={}",
        "orders-config", "success");
~~~

Ở đây `orders-config` là alias đã phê duyệt trong ví dụ, không phải giá trị cấu hình hay tên do request tùy ý cung cấp. Nếu cần theo dõi lỗi, dùng nhóm lỗi ổn định như `timeout`, `forbidden`, `parse_error`; không tự động dùng `exception.getMessage()` làm metric label.

Stack trace và message của thư viện có thể chứa địa chỉ, dữ liệu cấu hình hoặc chi tiết request. Chọn nơi lưu và cơ chế làm sạch phù hợp, đồng thời giữ đủ mã lỗi và ngữ cảnh không bí mật để điều tra.

### 5.2. Thay đổi cấu hình không cần lộ giá trị

Khi điều tra ConfigMap, Secret hoặc Configuration Watcher, các câu hỏi hữu ích thường là:

- Sự kiện thay đổi nào đã được nhận?
- Ứng dụng mục tiêu có nhận được thông báo không?
- Thao tác đọc/refresh thành công, thất bại hay chưa áp dụng?
- Sau refresh, hành vi cần kiểm tra có đúng không?

Không cần in giá trị Secret để trả lời các câu hỏi này. Nếu cần theo dõi một lần thay đổi cụ thể, dùng định danh sự kiện không chứa bí mật và chỉ lưu ở nơi được phép. Không mặc định thêm revision mới vào mọi metric.

Ứng dụng không đọc Secret bằng API thì không nên được cấp quyền đọc Secret chỉ để phục vụ metric. Với Watcher cần theo dõi Secret, giới hạn tài khoản, namespace và phạm vi theo chức năng thực tế. Tài khoản có quyền `list` hoặc `watch` Secret có thể nhận nội dung Secret trong tài nguyên trả về; đó không phải quyền chỉ xem tên.

Một label selector phục vụ chức năng không thay thế kiểm soát quyền truy cập. Khi bản sao của Secret đã được đưa vào annotation, log hay metric, quyền bảo vệ tài nguyên Secret gốc không bảo vệ được bản sao đó.

## 6. Công bố Actuator có chủ đích

Ví dụ cấu hình cho ứng dụng thử nghiệm chỉ cần health và Prometheus:

~~~yaml
spring:
  application:
    name: orders-api

management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
    health:
      show-details: never
  metrics:
    tags:
      application: orders-api
      environment: lab
~~~

Để có endpoint Prometheus, ứng dụng cần dependency `micrometer-registry-prometheus` cùng Actuator. Các nhãn chung trong ví dụ là giá trị triển khai ổn định, không lấy từ request. Cách cấu hình registry và common tags được mô tả tại [Spring Boot Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html).

`show-values: never` bảo vệ giá trị ở các endpoint hỗ trợ sanitization như `env` và `configprops`. Nó không che nội dung của metric tùy chỉnh, log, trace, `InfoContributor` hay DTO tự viết. Xem [Spring Boot: sanitize sensitive values](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

Exposure là lựa chọn endpoint được công bố, không thay thế xác thực/phân quyền HTTP. Cổng quản trị riêng cũng cần chính sách mạng và quyền truy cập phù hợp.

Nếu Configuration Watcher qua HTTP cần gọi `refresh`, phải điều chỉnh danh sách exposure theo chức năng đó và bảo vệ đường gọi. Không thêm mọi endpoint chỉ để xử lý một lỗi kết nối Watcher.

Một health response chỉ có trạng thái vẫn có thể phục vụ probe được thiết kế phù hợp. Không cần trả tên Secret, connection string hoặc nội dung cấu hình để chứng minh Pod đang sẵn sàng.

## 7. Kiểm tra bằng dữ liệu giả và quan sát số lượng

### 7.1. Kiểm tra cardinality ở cả ứng dụng lẫn backend

Với lớp metric ở phần 3:

1. Gửi nhiều dependency chưa biết và nhiều định danh request khác nhau vào luồng thử nghiệm.
2. Kiểm tra chúng được ánh xạ về tập giá trị đã thiết kế.
3. Xác nhận meter count không tăng theo từng giá trị đầu vào.
4. Kiểm tra dữ liệu xuất ra sau khi collector/scraper thêm nhãn.
5. Thử rollout để quan sát biến động target và danh tính instance.

Nếu đã có Prometheus và metric được xuất với tên `learning_dependency_calls_total`, một truy vấn minh họa là:

~~~promql
count by (job, instance) (
  learning_dependency_calls_total{job="orders-api"}
)
~~~

Thay tên metric/job theo exporter và cấu hình thực tế. Với ví dụ đăng ký trước chín tổ hợp và không có chiều động bổ sung, kỳ vọng mỗi target có chín series cho counter này. Truy vấn đếm series không kiểm tra giá trị của chúng có bí mật hay không.

Quan sát riêng số series hiện tại và số series mới xuất hiện qua thời gian. Một thời điểm có ít series không loại trừ churn do rollout hoặc do các giá trị xuất hiện rồi biến mất.

### 7.2. Dùng canary không có giá trị xác thực

Trong môi trường thử nghiệm cô lập, chọn một chuỗi giả như:

~~~text
CANARY_NOT_A_REAL_SECRET_20261124_A
~~~

Chuỗi này không được dùng làm mật khẩu, token hoặc khóa có quyền truy cập thật. Đưa nó vào fixture cấu hình nhạy cảm của bài thử theo quy trình kiểm thử, rồi kích hoạt các luồng cần quan sát: khởi động, đọc cấu hình, gọi dependency thất bại và refresh.

Kiểm tra canary không xuất hiện trong metric, log, trace, lỗi HTTP hoặc endpoint quản trị ngoài thiết kế. Ví dụ kiểm tra body Prometheus trong bộ nhớ, không in body khi phát hiện:

~~~powershell
$canary = 'CANARY_NOT_A_REAL_SECRET_20261124_A'
$encodedCanary = [Convert]::ToBase64String(
    [System.Text.Encoding]::UTF8.GetBytes($canary)
)

$response = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:18080/actuator/prometheus'
$body = [string]$response.Content

if ($body.Contains($canary) -or $body.Contains($encodedCanary)) {
    throw 'Phát hiện canary trong telemetry; không in nội dung phản hồi'
}
Write-Output 'Không phát hiện canary trong phản hồi đã kiểm tra'
~~~

Địa chỉ trên giả sử bạn đã thiết lập đường truy cập quản trị thử nghiệm; bổ sung xác thực theo cơ chế của môi trường. Không đưa credential vào URL của lệnh.

Kiểm tra một phản hồi không chứng minh mọi pipeline đều sạch. Cần bao phủ các replica, thời điểm lỗi/refresh, agent tự động, trace attribute, sự kiện và nơi lưu log liên quan. Dữ liệu có thể bị biến đổi, nên tìm chuỗi giả chỉ là một phần của kiểm tra.

Tương tự, việc endpoint `env` không được expose hoặc đã che giá trị không chứng minh endpoint `prometheus`, `info` hay log cũng được che.

### 7.3. Dấu hiệu cần điều tra

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| Số meter tăng theo request | Giá trị đầu vào, URL thô hoặc tên metric động |
| Series tăng mạnh sau rollout | Pod/instance/revision và enrichment của scraper |
| Tag chỉ có vài giá trị nhưng chứa credential | Hợp đồng dữ liệu sai; giới hạn cardinality không giải quyết |
| Discovery đã tắt metadata nhưng backend vẫn có annotation | Collector hoặc scraper đang bổ sung dữ liệu độc lập |
| Thiếu phép đo sau khi thêm filter | Meter bị từ chối hoặc các ID bị hợp nhất |
| Secret chỉ xuất hiện khi lỗi | Exception, client wire log, fallback hoặc response lỗi |
| Secret chỉ xuất hiện sau refresh | Logging cấu hình, event hoặc đối tượng vừa được bind lại |

## 8. Khi đã phát hiện dữ liệu thật bị lộ

Nếu phát hiện credential thật trong telemetry, ưu tiên chặn đường phát sinh và xử lý credential theo phạm vi ảnh hưởng. Việc sửa tag không thu hồi quyền truy cập của một token đã rời khỏi hệ thống.

Một quy trình ứng phó có thể gồm: giới hạn truy cập dữ liệu bị ảnh hưởng, thu hồi hoặc luân chuyển credential, xác định backend/remote write/export/bản sao liên quan, và xử lý lưu trữ theo chính sách của tổ chức. Không dán giá trị bị lộ vào ticket, chat hoặc ảnh chụp để mô tả sự cố.

Xóa series mới hoặc sửa dashboard không bảo đảm dữ liệu lịch sử, cache, bản sao hay thông báo cảnh báo đã được loại bỏ. Kiểm tra hiệu lực của biện pháp khắc phục bằng dữ liệu giả và bằng xác nhận tại các nơi nhận liên quan.

## 9. Bài tập củng cố

1. Với metric có route, outcome, dependency và instance, lập bảng tập giá trị và ước lượng số tổ hợp trước/sau khi thêm một ID nghiệp vụ.
2. Sửa một instrumentation đang dùng URL đầy đủ để chỉ giữ route theo mẫu hoặc alias đã định nghĩa.
3. Kiểm tra các cờ metadata discovery và liệt kê consumer nào thực sự cần từng nhóm metadata.
4. Dùng canary giả để thử luồng lỗi và refresh; phân biệt kiểm tra Actuator với kiểm tra logs/traces.
5. Giải thích vì sao hash token, giới hạn ba giá trị nhãn hoặc bật sampling không đủ để bảo vệ Secret.
6. Thiết kế một sự kiện chẩn đoán lỗi Configuration Watcher chứa đủ ngữ cảnh điều tra mà không có giá trị ConfigMap/Secret.
