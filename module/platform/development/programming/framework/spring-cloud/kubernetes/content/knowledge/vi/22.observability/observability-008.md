# Metrics của HTTP client và chi phí gọi API server

Trong chương **Khả năng quan sát** của module **SPRING_CLOUD_KUBERNETES**, đo HTTP client giúp trả lời hai câu hỏi khác nhau: ứng dụng gọi dịch vụ nghiệp vụ nhanh và ổn định đến đâu, và các tính năng tích hợp Kubernetes đang tạo bao nhiêu công việc cho API server. Hai câu hỏi có liên hệ nhưng không thể dùng chung một phép suy luận đơn giản.

Một request từ `order-api` tới `inventory-service` không đồng nghĩa với một request tới Kubernetes API server. DiscoveryClient có thể đọc dữ liệu đã lưu trong bộ nhớ; ngược lại, informer hoặc Configuration Watcher có thể tiếp tục trao đổi với API server ngay cả khi ứng dụng không nhận traffic nghiệp vụ.

Bài học dùng ví dụ **Spring Boot 3.5.x**, Spring Framework 6.2, Java 17 trở lên và **Spring Cloud Kubernetes 3.3.x** theo BOM tương thích của dự án. Prometheus được dùng để minh họa cách truy vấn. Cần đối chiếu tên meter, nhãn và khả năng instrumentation với đúng phiên bản, client và registry thực tế.

Sau bài học, bạn có thể:

- Tách metric HTTP nghiệp vụ, metric thao tác discovery/config và metric Kubernetes API server.
- Tạo HTTP client có observation bằng builder được Spring Boot cấu hình.
- Đọc throughput, độ trễ, lỗi và retry mà không nhầm số thao tác logic với số request mạng.
- Ước lượng tác động của replica, polling, LIST/WATCH và phạm vi namespace.
- Thiết kế phép đo để chọn đúng tính năng Spring Cloud Kubernetes cần cho triển khai.

## 1. Xác định đang đo lớp nào

Xét ứng dụng `order-api` chạy nhiều replica, gọi `inventory-service` và nhận cấu hình từ Kubernetes:

```text
Yêu cầu nghiệp vụ
       │
       v
   order-api ── HTTP client / LoadBalancer ──> inventory-service
       │
       ├─ DiscoveryClient ──> dữ liệu cục bộ hoặc nguồn discovery
       │                                 │
       │                                 v
       └─ ConfigMap/Secret client ──> Kubernetes API server

Configuration Watcher ── LIST/WATCH ──> Kubernetes API server
          │
          └─ thông báo refresh ──> các ứng dụng đích
```

Đường đi thực tế phụ thuộc implementation. Khi dùng HTTP DiscoveryClient qua DiscoveryServer, ứng dụng còn có một lớp HTTP tới DiscoveryServer; chi phí truy cập Kubernetes có thể nằm ở server đó.

| Lớp đo | Ví dụ | Điều metric thể hiện | Điều chưa thể kết luận |
| --- | --- | --- | --- |
| HTTP client nghiệp vụ | GET danh mục tồn kho | Thời gian và kết quả exchange được instrument | Bao nhiêu lần gọi Kubernetes API để phục vụ exchange |
| Thao tác logic của ứng dụng | `DiscoveryClient.getInstances(...)` | Tần suất lookup, thời gian trả kết quả, danh sách rỗng/lỗi | Lookup có thực sự thực hiện request mạng không |
| HTTP transport của Kubernetes client | GET/LIST hoặc kết nối WATCH | Request/attempt mà SDK và instrumentation quan sát được | Toàn bộ chi phí CPU, lưu trữ và fan-out của control plane |
| API server | Request theo verb, resource, code | Tải mà API server tiếp nhận từ các client | Toàn bộ tải đó thuộc riêng `order-api` |

Trước khi vẽ biểu đồ, ghi rõ **điểm bắt đầu, điểm kết thúc và phạm vi của phép đo**. Một timer bọc cả vòng retry có ý nghĩa khác timer ghi cho từng attempt.

## 2. Bật metric cho HTTP client do Spring quản lý

### 2.1. Dùng builder đã được Spring Boot cấu hình

Spring Boot Actuator hỗ trợ instrumentation cho `RestClient`, `RestTemplate` và `WebClient` khi sử dụng builder được auto-configure. Tên observation mặc định là `http.client.requests`. Tự gọi factory tạo client mới có thể bỏ qua phần cấu hình observation. Xem [Spring Boot: HTTP Client Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html#actuator.metrics.supported.http-clients).

Ví dụ dưới là một client gọi bằng DNS của Kubernetes Service. Nó minh họa instrumentation HTTP, không tự tạo cấu hình Spring Cloud LoadBalancer:

```java
package example.observability;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public final class InventoryGateway {

    private final RestClient client;

    public InventoryGateway(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service:8080")
                .build();
    }

    public String findInventory(String sku) {
        return client.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .body(String.class);
    }
}
```

Ví dụ giả định dự án có Spring MVC/web starter để dùng `RestClient`, Actuator và Service đích có API tương ứng. Timeout kết nối, đọc và pool cần được cấu hình theo HTTP transport mà dự án lựa chọn; không coi ví dụ ngắn này là toàn bộ cấu hình client production.

URI template `/inventory/{sku}` giúp giữ số giá trị của nhãn `uri` hữu hạn. Tránh tạo tag chứa SKU thật, user ID, request ID hoặc URL đầy đủ có query động.

Nếu dùng builder `@LoadBalanced` tùy biến, cần giữ cả cấu hình observation và cấu hình LoadBalancer. Việc một builder được đăng ký thành bean không tự chứng minh nó đã áp dụng đầy đủ các customizer của Spring Boot.

### 2.2. Chuẩn bị xuất metric

Nếu dự án quản lý dependency bằng Spring Boot, thêm các dependency phù hợp, không tự chọn phiên bản Micrometer lệch khỏi BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Cấu hình minh họa trong `application.yml`:

```yaml
spring:
  application:
    name: order-api

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: "${spring.application.name}"
      deployment_namespace: "${K8S_NAMESPACE:local}"
    distribution:
      percentiles-histogram:
        "[http.client.requests]": true
```

`K8S_NAMESPACE` cần được inject từ `metadata.namespace` của Pod bằng Downward API nếu muốn nhận giá trị Kubernetes thật. `application` và `deployment_namespace` là common tag của ví dụ, không phải nhãn mà mọi ứng dụng mặc định đều có.

Cấu hình histogram tạo thêm series để tính percentile trên Prometheus. Chỉ bật cho các meter cần thiết và kiểm soát số tag; không bật cho mọi meter mà chưa đánh giá chi phí. Prometheus vẫn cần được cấu hình scrape, còn endpoint `metrics` phục vụ chẩn đoán tại ứng dụng. Việc expose endpoint không tự tạo cấu hình scrape hoặc ServiceMonitor.

Giới hạn truy cập các endpoint quản trị bằng mạng và HTTP security phù hợp. Một Prometheus scraper có thể cần quyền xác thực riêng; không mở tất cả Actuator để xử lý một lỗi scrape.

## 3. Đọc đúng ý nghĩa của HTTP client metric

Với Spring Framework 6.2, các nhãn thường gặp gồm:

| Nhãn observation | Ý nghĩa | Lưu ý khi đọc |
| --- | --- | --- |
| `method` | Phương thức HTTP | Ví dụ `GET`, `POST` |
| `uri` | URI template khi có | Không nên là đường dẫn chứa ID không giới hạn |
| `client.name` | Tên suy ra từ host của URI request | Không mặc định là tên logic của mọi service sau các tầng LoadBalancer |
| `status` | HTTP status hoặc giá trị biểu diễn lỗi chưa có response | Ví dụ `200`, `500`, `IO_ERROR`, `CLIENT_ERROR` |
| `outcome` | Nhóm kết quả exchange | Cần đọc cùng status và lỗi |
| `error` | Lớp exception hoặc `none` | Không lấy exception message làm tag |

Tên nhãn xuất ra backend có thể được chuẩn hóa, chẳng hạn `client.name` thành `client_name` trong Prometheus. Với phiên bản nêu trong bài, nhãn `exception` có thể còn xuất hiện để tương thích nhưng đã được đánh dấu deprecated trong convention tương ứng. Xem [Spring Framework 6.2: HTTP Client Instrumentation](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html#observability.http-clients).

Độ trễ phía client không chỉ là thời gian xử lý trên server đích. Nó có thể phản ánh chờ kết nối, thiết lập kết nối, truyền dữ liệu và xử lý response trong ranh giới observation của client. Vì vậy, client chậm nhưng server đích không chậm là tình huống có thể xảy ra.

Đồng thời, số exchange quan sát được không phải lúc nào cũng bằng số attempt cấp transport. Retry hoặc redirect nội bộ có thể nằm bên trong một exchange; retry ở một tầng ngoài có thể tạo nhiều exchange. Phải xác định vị trí instrumentation và retry trước khi dùng count để suy ra request mạng.

Nếu một meter chưa xuất hiện, hãy tạo một exchange hoàn tất rồi kiểm tra lại. Không có series có thể do chưa có mẫu, client không được instrument, meter bị lọc hoặc scrape sai; nó không tự chứng minh rằng không có traffic.

## 4. PromQL cho HTTP client

Các ví dụ dưới giả định registry xuất timer dưới dạng `http_client_requests_seconds_*`, các nhãn đúng như ví dụ và Prometheus đang thu thập dữ liệu. Luôn kiểm tra exposition thực tế trước khi dùng nguyên truy vấn.

### 4.1. Tần suất exchange theo đường gọi

```promql
sum by (client_name, method, uri, status) (
  rate(http_client_requests_seconds_count{
    application="order-api",
    deployment_namespace="shop"
  }[5m])
)
```

Kết quả có đơn vị exchange/giây tại ranh giới được đo. Nó bao gồm những client được instrument và mang tag tương ứng, không tự bao gồm mọi kết nối của JVM.

### 4.2. p95 của một nhóm client

```promql
histogram_quantile(
  0.95,
  sum by (le, client_name) (
    rate(http_client_requests_seconds_bucket{
      application="order-api",
      deployment_namespace="shop"
    }[5m])
  )
)
```

Kết quả có đơn vị giây. Truy vấn cần histogram bucket; chỉ có `_count` và `_sum` thì chưa đủ để tính p95. Tổng hợp bucket giữa các replica rồi tính quantile có ý nghĩa khác với lấy trung bình các p95 được tính riêng trên từng replica.

Micrometer giải thích sự khác biệt giữa histogram có thể tổng hợp và percentile tính tại client trong [Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).

### 4.3. Theo dõi các nhóm lỗi riêng biệt

Ví dụ tốc độ response 5xx:

```promql
sum by (client_name, status) (
  rate(http_client_requests_seconds_count{
    application="order-api",
    deployment_namespace="shop",
    status=~"5.."
  }[5m])
)
```

Lỗi chưa nhận được response cần được xem riêng, chẳng hạn:

```promql
sum by (client_name, status) (
  rate(http_client_requests_seconds_count{
    application="order-api",
    deployment_namespace="shop",
    status=~"IO_ERROR|CLIENT_ERROR"
  }[5m])
)
```

Đây là nhóm trạng thái của convention được giả định trong bài. Với client hoặc convention khác, dùng giá trị thực tế. Nếu tính tỷ lệ lỗi, tử số và mẫu số phải dùng cùng tập client, cùng nhãn lọc và cùng cửa sổ thời gian; phân biệt không có traffic với tỷ lệ lỗi bằng không.

Không coi mọi 4xx là lỗi hạ tầng. `404` có thể là kết quả nghiệp vụ bình thường, trong khi `401/403` từ Kubernetes API thường cần điều tra xác thực hoặc RBAC. Chính sách lỗi phải dựa trên API được gọi.

## 5. Kubernetes SDK không mặc định dùng cùng instrumentation

Spring Cloud Kubernetes có các implementation discovery dựa trên Fabric8, Kubernetes Java Client và HTTP DiscoveryClient qua DiscoveryServer. Client nào thực sự truy cập Kubernetes, sử dụng transport nào và có cache/informer ra sao là thông tin cần ghi nhận trước khi đo. Xem [Spring Cloud Kubernetes 3.3: DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html).

**Có Actuator và thấy `http.client.requests` không chứng minh các request của Fabric8 hoặc Kubernetes Java Client đã nằm trong meter đó.** SDK có thể tự tạo HTTP transport, interceptor hoặc event loop riêng, không đi qua builder Spring Boot ở phần trước.

Cách xác minh có thể gồm:

1. Xác định implementation, phiên bản SDK và transport đang hoạt động.
2. Tìm cơ chế metrics/observation chính thức mà phiên bản đó hỗ trợ, nếu có.
3. Trong môi trường thử nghiệm, thực hiện một thao tác API đã biết rồi quan sát series tăng ở meter nào.
4. Kiểm tra retry, redirect và WATCH được instrumentation tính ở ranh giới nào.
5. Đối chiếu dữ liệu phía client với API server và traffic nền, không chỉ nhìn tên meter.

Nếu cần bổ sung instrumentation, đặt tại điểm mở rộng được SDK hỗ trợ. Không sửa logic xác thực, bỏ kiểm tra TLS hoặc thay client Kubernetes bằng một client HTTP chưa cấu hình đầy đủ chỉ để có metric.

Có thể định nghĩa hợp đồng metric riêng cho transport, nhưng phải ghi rõ đây là **tên đề xuất**, không phải meter mặc định của Spring Cloud Kubernetes:

| Tên Micrometer đề xuất | Loại | Phạm vi |
| --- | --- | --- |
| `platform.kubernetes.api.attempts` | Counter | Một attempt mạng thực sự mà hook transport quan sát được |
| `platform.kubernetes.api.request.duration` | Timer | Thời gian request hữu hạn, theo ranh giới đã công bố |
| `platform.kubernetes.watch.active` | Gauge | Số stream WATCH đang hoạt động |
| `platform.kubernetes.watch.reconnects` | Counter | Số lần nối lại, với nhóm nguyên nhân hữu hạn |
| `platform.kubernetes.cache.last.sync` | Gauge hoặc dữ liệu trạng thái phù hợp | Thời điểm đồng bộ thành công gần nhất theo định nghĩa của client |

Tag có thể là `verb`, `resource`, `result` hoặc một nhóm namespace đã kiểm soát. Không gắn token, tên Secret, request body hoặc URL đầy đủ vào series. Thời gian từ event WATCH cuối cùng không tự chứng minh cache lỗi thời: có thể đơn giản là chưa có tài nguyên nào thay đổi.

## 6. Đo thao tác discovery mà không gọi nó là request API

Ngay cả khi chưa instrument được transport, bạn vẫn có thể đo một thao tác logic của ứng dụng. Ví dụ dưới đo những lời gọi đi qua wrapper này:

```java
package example.observability;

import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public final class ObservedDiscovery {

    private final DiscoveryClient discoveryClient;
    private final MeterRegistry registry;

    public ObservedDiscovery(DiscoveryClient discoveryClient,
                             MeterRegistry registry) {
        this.discoveryClient = discoveryClient;
        this.registry = registry;
    }

    public List<ServiceInstance> instances(String serviceId) {
        Timer.Sample sample = Timer.start(registry);
        String result = "success";
        try {
            List<ServiceInstance> instances =
                    discoveryClient.getInstances(serviceId);
            if (instances.isEmpty()) {
                result = "empty";
            }
            return instances;
        } catch (RuntimeException exception) {
            result = "error";
            throw exception;
        } finally {
            sample.stop(registry.timer(
                    "platform.discovery.lookup", "result", result));
        }
    }
}
```

Mã gọi cần dùng `ObservedDiscovery.instances(...)` để được đo. Wrapper không tự chặn mọi lời gọi nội bộ của LoadBalancer hoặc toàn bộ DiscoveryClient trong hệ thống. Tên `platform.discovery.lookup` là meter tự định nghĩa của bài.

Các giá trị `success`, `empty`, `error` tạo tập tag hữu hạn; ví dụ không đưa `serviceId` tùy ý vào tag. Timer đã có số lần và tổng thời gian, nên không cần thêm một counter chỉ để đếm lại cùng thao tác. API `Timer.Sample` được mô tả tại [Micrometer: Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

Nếu wrapper ghi 10.000 lookup trong khi transport chỉ ghi vài request nền, đó có thể là hiệu quả của cache. Nếu transport nhiều request nhưng lookup ít, hãy tìm refresh nền, reconnect, health check hoặc thao tác của SDK nằm ngoài wrapper. Không dùng timer lookup để tính trực tiếp số HTTP request tới Kubernetes.

## 7. Đo từ phía Kubernetes API server

Khi cluster cho phép truy cập hệ thống quan sát control plane, các metric hữu ích thường gồm:

| Metric | Dùng để quan sát |
| --- | --- |
| `apiserver_request_total` | Số request theo `verb`, `resource`, `code` và các chiều khác |
| `apiserver_request_duration_seconds` | Phân bố độ trễ phía API server |
| `apiserver_response_sizes` | Phân bố kích thước response |
| `apiserver_longrunning_requests` | Số request dài hạn đang hoạt động thuộc phạm vi metric theo dõi |
| `apiserver_current_inflight_requests` | Mức request đang chiếm giới hạn inflight theo loại request của API server |

Metric và nhãn có thể khác theo phiên bản hoặc môi trường cung cấp Kubernetes. Tham chiếu định nghĩa chính thức tại [Kubernetes Metrics Reference](https://kubernetes.io/docs/reference/instrumentation/metrics/).

### 7.1. Tần suất request của những resource liên quan

```promql
sum by (verb, resource, code) (
  rate(apiserver_request_total{
    resource=~"services|endpoints|endpointslices|configmaps|secrets"
  }[5m])
)
```

API server thường dùng các verb logic như `LIST`, `WATCH`, `GET`; một LIST và một WATCH đều có thể dùng HTTP GET ở transport. Không đồng nhất nhãn `verb` của API server với nhãn `method` của HTTP client.

Truy vấn này quan sát mọi nguồn nằm trong tập series đã scrape và bộ lọc resource, **không phải riêng ứng dụng `order-api`**. Nếu Prometheus thu nhiều cluster, bổ sung nhãn định danh cluster thật của hệ thống; không cộng chúng ngầm với nhau.

### 7.2. p95 của LIST Service

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(apiserver_request_duration_seconds_bucket{
      verb="LIST",
      resource="services"
    }[5m])
  )
)
```

Đây là độ trễ phía API server của tập request được chọn, không phải toàn bộ độ trễ mà ứng dụng cảm nhận. Nó cũng không đo trực tiếp độ mới của danh sách instance tại client.

WATCH là stream dài hạn. Một timer chỉ ghi khi exchange hoàn tất có thể chưa ghi mẫu trong suốt thời gian stream vẫn mở. Đừng trộn thời gian sống của WATCH với độ trễ của GET/LIST rồi kết luận API server xử lý chậm; hãy theo dõi trạng thái stream, reconnect và đồng bộ dữ liệu riêng.

### 7.3. Không quy toàn bộ tải control plane cho một ứng dụng

Các nhãn tiêu chuẩn của `apiserver_request_total` không có sẵn nhãn `application` hay service account để lọc chính xác từng workload. Gắn common tag ở Actuator của ứng dụng cũng không làm API server tự có tag đó.

Muốn phân bổ chi phí, kết hợp instrumentation phía client, phân tách danh tính client/service account theo kiến trúc phù hợp, log/audit được phép truy cập và thí nghiệm có kiểm soát. Audit cũng cần chọn mức ghi và bảo vệ dữ liệu; không thu request/response body của Secret chỉ để đếm request.

Nếu managed cluster không cung cấp đầy đủ metric control plane, báo rõ giới hạn quan sát. Có thể đánh giá count/latency phía client và tác động đến ứng dụng, nhưng không khẳng định đã đo trọn chi phí API server.

## 8. Ước lượng chi phí: đừng chỉ nhìn QPS

Chi phí truy cập API có nhiều chiều:

```text
chi phí ≈ số request + dữ liệu trả về + số stream đang mở
        + số event phân phối + retry/reconnect
        + CPU/bộ nhớ xử lý và lưu cache ở hai phía
```

Đây là mô hình suy luận, không phải công thức quy đổi thành một đơn vị tiền hoặc CPU chính xác. Hai LIST đều trả `200` nhưng một LIST trả vài object và một LIST trả hàng nghìn object có chi phí khác nhau.

### 8.1. Mô hình gọi trực tiếp theo request nghiệp vụ

Giả sử một thiết kế có các điều kiện sau:

- `N = 40` replica.
- Mỗi replica nhận `R = 20` request nghiệp vụ/giây.
- Mỗi request cần một lookup.
- Implementation giả định thực hiện hai request API cho mỗi lookup, không dùng cache và chưa retry.

Khi đó:

```text
Q_API = N × R × 2
      = 40 × 20 × 2
      = 1.600 request API/giây
```

Đây là **tình huống giả định để tính tải**, không phải hành vi mặc định của mọi DiscoveryClient. Nếu mỗi request API có trung bình ba attempt do retry tại một tầng được xác định, tải attempt có thể lên khoảng 4.800/giây trong cùng mô hình.

Không áp dụng hệ số retry đó nếu count bạn đang đọc đã đếm từng attempt; làm vậy sẽ nhân chi phí hai lần.

### 8.2. Mô hình polling

Giả sử 40 replica, mỗi lần refresh thực hiện hai request hữu hạn và chu kỳ là 30 giây:

```text
Q_poll ≈ N × F / P
       = 40 × 2 / 30
       ≈ 2,67 request/giây ở trạng thái ổn định
```

`F` phải là số request thực tế cho một vòng refresh, kể cả phân trang nếu có. Công thức chưa bao gồm tải khởi động, retry, request khác và việc nhiều replica cùng refresh vào một thời điểm.

Tăng chu kỳ polling giảm tần suất gọi nhưng làm tăng độ trễ nhìn thấy thay đổi. Nếu mỗi response lớn, QPS thấp vẫn có thể đi kèm băng thông và chi phí deserialize/cache đáng kể.

### 8.3. Mô hình LIST rồi WATCH

Trong mô hình giả định mỗi replica mở một watcher cho mỗi cặp namespace–loại resource, với 40 replica, hai loại resource và một namespace:

```text
số stream WATCH đang mở ≈ 40 × 2 × 1 = 80 stream
```

80 stream không có nghĩa là 80 request mỗi giây. Với mô hình LIST rồi WATCH, còn có tải khởi tạo LIST, mở WATCH, phân phối event và nối lại khi mất kết nối. Phân trang hoặc nhiều client độc lập có thể tăng thêm số request.

Các phiên bản và client có thể dùng cơ chế khởi tạo theo stream khác mô hình đơn giản trên. Cần đọc hành vi thực tế thay vì suy từ tên informer.

Kubernetes mô tả resource version, watch và xử lý khi lịch sử không còn khả dụng trong [Kubernetes API Concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/). Khi client phải đồng bộ lại, một đợt relist có thể tạo burst dù traffic nghiệp vụ giữ nguyên.

### 8.4. Chú ý thời điểm rollout và mất kết nối đồng loạt

Trạng thái ổn định chưa phản ánh toàn bộ tải. Nếu nhiều replica khởi động cùng lúc, chúng có thể đồng thời nạp cấu hình và khởi tạo cache. Nếu proxy hoặc mạng ngắt các stream cùng lúc, reconnect có thể tăng đột biến.

Vì vậy, so sánh ít nhất ba giai đoạn: khởi động/rollout, ổn định và hồi phục sau gián đoạn. Một biểu đồ trung bình dài hạn có thể che hoàn toàn burst quan trọng.

## 9. Giảm chi phí theo nguyên nhân đã đo được

### 9.1. Chỉ dùng discovery khi cần dữ liệu discovery

Nếu ứng dụng chỉ cần gọi một Kubernetes Service bằng DNS, không nhất thiết cần SDK để liệt kê Service hoặc Endpoint ở mỗi instance. Nếu ứng dụng cần metadata instance, lựa chọn Pod cụ thể hoặc chính sách LoadBalancer riêng, discovery có thể có giá trị.

Spring Cloud Kubernetes LoadBalancer hỗ trợ các mode dựa trên Pod hoặc Service. Dùng mode Service không đồng nghĩa chắc chắn không còn truy cập API để tìm Service hoặc cổng; cần đo đường đi thực tế. Xem [Spring Cloud Kubernetes 3.3: LoadBalancer](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/load-balancer.html).

### 9.2. Thu hẹp phạm vi namespace và resource

Giới hạn discovery vào namespace cần thiết thường làm giảm tập dữ liệu phải quản lý. Không bật all-namespaces chỉ để tránh tìm hiểu namespace resolution.

Cần phân biệt lọc ở API server với lọc sau khi đã tải dữ liệu về. Một biểu thức lọc ở bộ nhớ có thể giảm kết quả ứng dụng sử dụng nhưng không giảm kích thước response hoặc số object được watch. Chỉ kết luận tiết kiệm request/dữ liệu sau khi kiểm chứng vị trí áp dụng bộ lọc.

RBAC và bộ lọc discovery cũng có vai trò khác nhau: filter không phải ranh giới cấp quyền. Chỉ cấp những quyền mà tính năng đã chọn thực sự cần, không cấp quyền toàn cluster chỉ để hết lỗi `403`.

### 9.3. Tái sử dụng client và cache phù hợp

Không tạo một Kubernetes client mới trong mỗi request nghiệp vụ. Client mới có thể kéo theo pool, thread hoặc watcher riêng. Kiểm tra vòng đời bean và số client thực sự trong mỗi replica.

Cache/informer giúp tách tần suất request nghiệp vụ khỏi tần suất gọi control plane, nhưng cần có chính sách dữ liệu đủ mới và khả năng đồng bộ lại. Thêm một lớp cache khác chưa chắc có lợi nếu discovery implementation đã có cache; hãy xem metric hit/miss, lookup, transport và thời gian cập nhật trước khi thêm lớp mới.

### 9.4. Kiểm soát retry, timeout và reconnect

Retry không giới hạn có thể làm API server càng quá tải khi đang gặp lỗi. Đặt giới hạn attempt, deadline tổng, backoff và jitter theo khả năng của client; tránh nhiều tầng retry cùng nhân số lần gọi.

Một `403` do RBAC sai cần sửa quyền/phạm vi; lặp lại nhanh thường không giúp. `429` cần phân biệt phản hồi từ API server với throttling cục bộ của client. Tôn trọng cơ chế retry được client/server hỗ trợ và kiểm tra hàng đợi, giới hạn concurrency trước khi tăng QPS/burst.

Kubernetes API Priority and Fairness có cơ chế phân loại và điều phối request. Tăng số attempt không tạo thêm năng lực xử lý và có thể làm ảnh hưởng client khác. Xem [Kubernetes: API Priority and Fairness](https://kubernetes.io/docs/concepts/cluster-administration/flow-control/).

### 9.5. Tách chi phí cấu hình khỏi chi phí thông báo refresh

Nạp ConfigMap/Secret lúc startup, theo dõi thay đổi và gửi thông báo refresh là các loại công việc khác nhau. Configuration Watcher có thể theo dõi tài nguyên rồi thông báo cho ứng dụng qua HTTP hoặc Spring Cloud Bus; tài liệu mô tả luồng này tại [Spring Cloud Kubernetes 3.3: Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Đo riêng workload watcher và ứng dụng đích. Một thay đổi có thể kích hoạt nhiều thông báo hoặc nhiều lần ứng dụng đọc lại dữ liệu; giảm số watcher không tự chứng minh giảm mọi chi phí refresh. Nếu cấu hình được mount thành volume, không quy mọi request của kubelet để cập nhật volume cho HTTP client trong JVM.

### 9.6. Kiểm tra cả health check và tác vụ nền

Traffic API có thể đến từ health check discovery, scheduler, polling cấu hình hoặc cache refresh. Nếu tần suất API thay đổi theo chu kỳ probe thay vì theo traffic nghiệp vụ, hãy điều tra những nguồn này.

Không đưa một truy vấn API nặng vào mỗi lần liveness/readiness nếu không có lý do vận hành rõ ràng. Việc thêm giám sát cũng cần tránh tự tạo thêm tải mà chính nó đang cảnh báo.

## 10. Bài thực hành đo trước và sau thay đổi

Thực hiện trong namespace thử nghiệm, dùng bộ dữ liệu và traffic có giới hạn. Các lệnh dưới minh họa cách quan sát; chúng không thực hiện thay đổi cấu hình Kubernetes client.

### 10.1. Xác nhận meter ở một Pod

```powershell
# Thay POD_NAME bằng Pod ứng dụng thực tế trong namespace shop.
kubectl -n shop port-forward pod/POD_NAME 18080:8080

# Chạy ở terminal khác sau khi tạo traffic qua InventoryGateway.
curl.exe -s http://localhost:18080/actuator/metrics/http.client.requests
curl.exe -s http://localhost:18080/actuator/prometheus
```

Truy cập cần tuân theo security của ứng dụng. Nếu muốn giới hạn kết quả theo tag, dùng tên Micrometer ở endpoint chẩn đoán, ví dụ:

```powershell
curl.exe -s "http://localhost:18080/actuator/metrics/http.client.requests?tag=client.name:inventory-service"
```

Ở `/actuator/metrics`, tên là `http.client.requests`; trong Prometheus có thể là `http_client_requests_seconds_count`. Không dùng tên đã chuẩn hóa của Prometheus làm tên meter trong URL chẩn đoán.

### 10.2. Thiết lập đường cơ sở

Ghi lại cùng một khoảng đo và các điều kiện:

| Nhóm thông tin | Nội dung cần ghi |
| --- | --- |
| Kiến trúc | Loại discovery/client, transport, cache/informer, đường đi qua DiscoveryServer nếu có |
| Phạm vi | Số replica, namespace, resource, kích thước dữ liệu |
| Traffic | Request nghiệp vụ/giây và thao tác lookup/giây |
| Client | Exchange/attempt, status/error, độ trễ, retry/reconnect, số stream |
| API server | Request theo verb/resource/code, độ trễ và kích thước response nếu quan sát được |
| Chất lượng phục vụ | Độ trễ nghiệp vụ, lỗi, thời gian nhìn thấy thay đổi instance/cấu hình |

Giữ cả pha khởi tạo và pha ổn định. Nếu metric control plane là số liệu toàn cluster, ghi nhận workload nền và giới hạn quy kết thay vì gắn nhãn kết quả là chi phí chính xác của ứng dụng.

### 10.3. Chỉ thay một yếu tố mỗi lượt

Ví dụ chọn một trong các thay đổi sau:

- Thu hẹp từ phạm vi rộng sang namespace thực sự cần.
- Sửa việc tạo client theo request thành tái sử dụng một client đúng vòng đời.
- Điều chỉnh chu kỳ polling theo độ trễ cập nhật chấp nhận được.
- Sửa retry lồng nhau hoặc reconnect không có backoff.
- Thử đường gọi DNS của Service khi không còn nhu cầu discovery ở client.

Giữ traffic và dữ liệu gần tương đương, sau đó đo lại. Không chấp nhận thay đổi chỉ vì count giảm: cần kiểm tra lookup còn đúng, cấu hình vẫn cập nhật và ứng dụng hồi phục được sau gián đoạn.

### 10.4. Mẫu kết luận có thể kiểm chứng

Một kết luận tốt có thể là:

> Trong môi trường thử nghiệm, sau khi tái sử dụng client và giữ nguyên số replica, số attempt API phía client giảm trong pha ổn định; lỗi nghiệp vụ không tăng và thời gian nhận thay đổi Service vẫn đạt mục tiêu đã đặt. Số liệu API server là tổng của cluster nên được dùng để đối chiếu xu hướng, chưa phân bổ chính xác cho riêng ứng dụng.

Đây là **mẫu cách báo cáo**, không phải kết quả đo đã được thực hiện. Báo cáo thực tế cần nêu cửa sổ đo, giá trị trước/sau và nguồn metric.

## 11. Các kết luận sai thường gặp

| Kết luận vội | Vấn đề | Cách đọc đúng hơn |
| --- | --- | --- |
| Có Actuator nên mọi Kubernetes request đã được đo | SDK có thể dùng transport riêng | Kiểm chứng instrumentation của client cụ thể |
| Một lookup bằng một API request | Cache, phân trang và retry thay đổi quan hệ | Đo lookup và attempt riêng |
| WATCH mở lâu nên API chậm | Đang nhầm thời gian sống stream với độ trễ request hữu hạn | Đo stream active, reconnect và đồng bộ cache |
| API server tăng QPS là do ứng dụng này | Metric thường tổng hợp nhiều client | Kết hợp dữ liệu client và danh tính/nguồn được phép quan sát |
| Tỷ lệ 5xx thấp nghĩa là không có lỗi client | DNS, TLS, timeout có thể chưa nhận HTTP response | Đọc cả nhóm lỗi transport và exception |
| Giảm polling càng nhiều càng tốt | Có thể làm thông tin instance/cấu hình chậm cập nhật | So sánh cả chi phí lẫn mục tiêu độ mới |
| Mode Service luôn loại bỏ mọi request API | Vẫn có thể cần khám phá Service/cổng | Đo implementation và đường gọi thực tế |
| Bộ lọc kết quả ít hơn nên băng thông API đã giảm | Bộ lọc có thể chạy sau khi tải dữ liệu | Xác định nơi áp dụng và đo response size |
| Lấy trung bình p95 các Pod là p95 toàn ứng dụng | Percentile riêng không tổng hợp theo cách đó | Tổng hợp histogram bucket rồi tính quantile |
| Đưa URL, Pod IP và request ID vào tag sẽ dễ điều tra hơn | Số series tăng theo dữ liệu động | Dùng nhãn hữu hạn; để chi tiết trong log/trace phù hợp |

Để đánh giá chi phí gọi Kubernetes API, cần biết ứng dụng đang làm thao tác gì, client thực sự gửi gì và API server tiếp nhận gì. Khi giữ riêng ba lớp đo này, bạn có thể chọn discovery, LoadBalancer, cơ chế cấu hình và Configuration Watcher dựa trên nhu cầu triển khai cùng bằng chứng quan sát được.
