# API rate limit, phản hồi 429 và backoff

Trong chương **Hiệu năng và độ bền** của module **SPRING_CLOUD_KUBERNETES**, bài học này giải quyết một tình huống thường gặp: ứng dụng vẫn chạy, nhưng các lần đọc cấu hình, cập nhật discovery hoặc gọi dịch vụ khác bắt đầu bị giới hạn. Cách xử lý cần giúp hệ thống phục hồi mà không tạo thêm một đợt tải từ chính các lần thử lại.

Ứng dụng Spring tích hợp Kubernetes có hai hướng giao tiếp cần theo dõi riêng: giao tiếp với Kubernetes API để lấy thông tin hạ tầng, và giao tiếp với các dịch vụ nghiệp vụ qua địa chỉ Service hoặc Spring Cloud LoadBalancer. Một chính sách retry đúng cho hướng này chưa chắc phù hợp với hướng còn lại.

## 1. Kết quả cần đạt và tình huống xuyên suốt

Sau bài học, bạn có thể:

- Xác định thành phần phát sinh HTTP 429 và phân biệt với throttling ngay trong client.
- Đọc `Retry-After`, thiết kế exponential backoff có jitter, số lần thử hữu hạn và deadline tổng.
- Giảm tải do DiscoveryClient, đọc ConfigMap/Secret và Configuration Watcher tạo ra.
- Phối hợp retry với Spring Cloud LoadBalancer, RBAC, cache và các probe của Pod.
- Kiểm chứng việc phục hồi bằng số request thực tế, thời gian chờ và độ mới của dữ liệu.

Giả sử `checkout` chạy 40 replica trong namespace `shop`. Ứng dụng dùng Spring Cloud Kubernetes để tìm các instance của `inventory` và đọc cấu hình giá từ ConfigMap. Một đợt rollout đồng thời làm nhiều Pod khởi động, đọc cấu hình và thiết lập lại discovery. Cùng lúc, `inventory` áp dụng quota dùng chung cho các request của `checkout`.

Nếu cả Kubernetes API và `inventory` đều có phản hồi 429, tăng số lần retry cho mọi HTTP client sẽ khiến cả hai phía chịu thêm tải. Việc đầu tiên là xác định nguồn phản hồi, phạm vi quota và nơi đang sở hữu chính sách thử lại.

## 2. Ba dạng giới hạn cần phân biệt

| Dạng giới hạn | Dấu hiệu điển hình | Nơi cần điều chỉnh |
| --- | --- | --- |
| Kubernetes API từ chối request | Request tới API server nhận HTTP 429; cần xem response và số liệu control plane | Lưu lượng API, phạm vi discovery/config, chính sách client và quản trị API server |
| Dịch vụ nghiệp vụ hoặc gateway giới hạn | Request tới `inventory` hoặc ingress/gateway nhận HTTP 429 | Quota của API, lưu lượng nghiệp vụ, retry tại nơi gọi |
| Client tự hạn chế trước khi gửi | Request chờ token, chờ connection pool hoặc bị bulkhead từ chối; có thể chưa gửi HTTP | Rate limiter, giới hạn đồng thời và hàng đợi phía client |

HTTP 429 biểu thị giới hạn số request theo chính sách bên nhận; phản hồi có thể kèm `Retry-After`. Quota có thể gắn với danh tính gọi, tài nguyên hoặc nhiều server, nên chuyển request sang Pod khác không bảo đảm hết giới hạn. Response 429 không được lưu như một response thông thường trong HTTP cache. [RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Kubernetes API Priority and Fairness (APF) quản lý cạnh tranh về khả năng xử lý đồng thời. Khi vượt khả năng cấp cho một mức ưu tiên, request có thể phải xếp hàng hoặc nhận 429. Vì vậy, không diễn giải mọi 429 của API server thành một quota QPS cố định cho từng Pod. [Kubernetes: API Priority and Fairness](https://kubernetes.io/docs/concepts/cluster-administration/flow-control/).

Một log ghi “throttling” chưa chứng minh server đã trả 429. Cần đối chiếu HTTP status, đích gọi và vị trí thời gian bị tiêu tốn: chờ client, truyền mạng hay chờ server.

### Phân loại lỗi trước khi quyết định thử lại

| Kết quả | Cách xử lý ban đầu |
| --- | --- |
| `429 Too Many Requests` | Giảm tốc; xem `Retry-After`; chỉ retry khi thao tác và ngân sách cho phép |
| `401 Unauthorized` | Kiểm tra credential, token và cơ chế làm mới xác thực; không lặp vô hạn cùng credential |
| `403 Forbidden` | Kiểm tra ServiceAccount, namespace và RBAC; backoff không bổ sung quyền |
| `409 Conflict` khi cập nhật tài nguyên | Kiểm tra xung đột phiên bản; có thể cần đọc lại và tính lại thay đổi |
| `410 Gone` trong watch | Xử lý vòng đời watch và `resourceVersion`, không lặp mãi cùng phiên bản đã hết hạn |
| `503`, lỗi kết nối hoặc timeout | Áp dụng chính sách riêng theo nguyên nhân và tính an toàn của thao tác |

Với watch có phiên bản lịch sử không còn được giữ, client cần đồng bộ lại bằng GET/LIST thích hợp rồi mở watch từ `resourceVersion` mới. Ưu tiên cơ chế có sẵn của thư viện client thay vì tự viết vòng reconnect bên ngoài. [Kubernetes API Concepts: efficient detection of changes](https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes).

## 3. Tại sao retry có thể làm sự cố nặng thêm?

### 3.1. Tải đều và tải dồn là hai vấn đề khác nhau

Trong một mô hình polling giả định, nếu mỗi replica đọc ba nhóm tài nguyên sau mỗi 20 giây, lưu lượng nền xấp xỉ:

```text
40 replica × 3 lượt đọc / 20 giây = 6 request/giây
```

Đây là phép tính minh họa, không phải công thức nội bộ của Spring Cloud Kubernetes. Một lượt đọc có thể cần nhiều request do phân trang, namespace, profile cấu hình hoặc cách triển khai client.

Nếu 40 Pod cùng khởi động và mỗi Pod gửi ba request ban đầu, có thể có 120 request dồn vào một khoảng ngắn, dù trung bình dài hạn chỉ là 6 request/giây. Cần đo cả lưu lượng đều, burst lúc khởi động và đợt reconnect sau lỗi mạng.

Một rate limiter cục bộ cho phép 5 request/giây ở mỗi Pod cũng có thể tạo tổng 200 request/giây với 40 Pod. Nếu quota áp dụng chung cho danh tính hoặc ứng dụng, giới hạn từng Pod phải được tính cùng số replica, hoặc phối hợp bằng cơ chế dùng chung.

### 3.2. Retry khuếch đại số request

Với tối đa ba lần thử lại, mỗi thao tác logic có tối đa bốn lần gọi. Khi cả 100 thao tác đều gặp lỗi đủ lâu:

```text
100 thao tác × (1 lần đầu + 3 lần thử lại) = tối đa 400 lần gọi
```

Nếu hai tầng lồng nhau đều cho tối đa bốn lần gọi, giới hạn lý thuyết có thể thành 16 lần gọi xuống tầng dưới cho một thao tác ban đầu. Một tổ hợp dễ gặp là gateway retry, ứng dụng retry rồi HTTP client tiếp tục retry.

Từ đó có ba quyết định thiết kế:

1. Chọn một tầng chịu trách nhiệm retry cho từng luồng gọi.
2. Hạn chế số thao tác đang bay và kích thước hàng đợi, bên cạnh tốc độ gửi.
3. Đặt ngân sách retry cho cả workload, không chỉ cho từng request.

Ví dụ, “tối đa 20 request retry cho 100 request gốc trong một cửa sổ đo” là một chính sách ngân sách do đội vận hành lựa chọn. Đây không phải mặc định của Spring Cloud Kubernetes. Khi ngân sách hết, trả lỗi có kiểm soát hoặc dùng phương án suy giảm đã được nghiệp vụ chấp nhận.

## 4. Hiểu và tôn trọng `Retry-After`

`Retry-After` có hai dạng: số nguyên không âm chỉ số giây chờ, hoặc một thời điểm HTTP-date. [RFC 9110, mục 10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after).

Ví dụ thứ nhất yêu cầu chờ ba giây sau khi nhận response:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/json

{"error":"rate_limited"}
```

Ví dụ thứ hai dùng một thời điểm tuyệt đối:

```http
Retry-After: Wed, 25 Nov 2026 10:00:00 GMT
```

Nếu response thứ hai được nhận lúc `09:59:57 GMT`, thời gian chờ được tính là ba giây. Khi dùng dạng ngày giờ, đồng bộ đồng hồ có ý nghĩa thực tế. Deadline nội bộ nên dùng đồng hồ đơn điệu để tránh bị ảnh hưởng bởi chỉnh giờ hệ thống.

Quy ước xử lý trong bài này:

- Header hợp lệ: coi thời gian được chỉ định là sàn chờ trước khi thử lại.
- Header thiếu hoặc không phân tích được: dùng backoff cục bộ và ghi nhận tình trạng header.
- Thời điểm đã qua hoặc giá trị bằng 0: vẫn giữ backoff cục bộ để tránh vòng lặp gửi dồn.
- Thời gian chờ lớn hơn ngân sách còn lại: dừng thao tác đồng bộ hiện tại; chỉ chuyển sang công việc nền nếu thiết kế nghiệp vụ đã cho phép.

Không cắt `Retry-After: 60` thành hai giây chỉ vì `maxBackoff` cục bộ là hai giây. Nếu request chỉ còn tám giây, lựa chọn phù hợp là dừng chờ và báo kết quả thích hợp, không gửi sớm hơn thời gian đã chọn để tôn trọng server.

## 5. Thiết kế backoff có jitter và deadline

Với lần thử lại thứ `k`, bắt đầu từ `k = 0`, đặt trần backoff cục bộ:

```text
B(k) = min(cap, base × 2^k)
```

Hai cách phân tán thời điểm gửi thường dùng trong thiết kế client:

| Cách chọn | Khoảng chờ cục bộ | Đặc điểm |
| --- | --- | --- |
| Full jitter | Ngẫu nhiên từ 0 đến B(k) | Phân tán rộng; có thể chọn một lần chờ rất ngắn |
| Equal jitter | B(k)/2 cộng ngẫu nhiên từ 0 đến B(k)/2 | Giữ một khoảng chờ tối thiểu ở mỗi vòng |

Ví dụ `base = 200 ms`, `cap = 2 s`, equal jitter cho ba lần thử lại lần lượt nằm trong khoảng `100–200 ms`, `200–400 ms` và `400–800 ms`.

Nếu có thời gian chờ từ server là `R`, bài này chọn chính sách:

```text
wait = max(R, localBackoff) + jitter_bổ_sung_không_âm
```

Jitter bổ sung giúp các replica cùng nhận `Retry-After: 3` không nhất loạt gửi lại đúng sau ba giây. Không dùng jitter âm làm thời gian thực tế thấp hơn `R`. Đây là lựa chọn thiết kế cho bài thực hành, không phải thuật toán mặc định của mọi Kubernetes client.

Trước mỗi retry, kiểm tra tuần tự:

```text
Lỗi có nằm trong chính sách không?
  → Thao tác có an toàn để gửi lại không?
  → Còn số lần thử và ngân sách retry dùng chung không?
  → Thời gian chờ cộng thời gian dành cho lần gọi sau có vừa deadline không?
  → Nếu đều đạt: lên lịch chờ rồi gửi lại.
```

Cần phân biệt **timeout mỗi lần gọi** với **deadline của toàn bộ thao tác**. Timeout đặt lại sau mỗi retry sẽ không tự giới hạn tổng thời gian gồm nhiều lần gọi và nhiều khoảng chờ.

Với GET đọc dữ liệu, gửi lại thường thuận lợi hơn. Với thao tác tạo đơn, thanh toán hoặc gọi `/actuator/refresh`, phải kiểm tra tác dụng phụ và cơ chế chống trùng. Việc có HTTP 429 không đủ để suy ra mọi tầng trung gian đều chưa tạo tác dụng phụ. Nếu kết quả một lần ghi không rõ do timeout, cần đối soát trạng thái hoặc dùng cơ chế idempotency đã được API bảo đảm.

## 6. Giảm request do Spring Cloud Kubernetes tạo ra

### 6.1. Chỉ bật phạm vi discovery thực sự cần

Một cấu hình minh họa cho ứng dụng chỉ tìm dịch vụ trong namespace `shop`:

```yaml
spring:
  application:
    name: checkout
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - shop
        catalog-services-watch-delay: 60000
```

`all-namespaces` và `namespaces` quyết định phạm vi tìm kiếm. Với cơ chế catalog watch được tài liệu mô tả, `catalog-services-watch-delay` điều chỉnh khoảng phát heartbeat theo mili giây. Không xem thuộc tính này là QPS limiter cho mọi request, hay khoảng reconnect của mọi Kubernetes watch. Cần kiểm tra triển khai DiscoveryClient và cách bật catalog watcher của release đang dùng. [Spring Cloud Kubernetes: DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html), [Common application properties](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Tăng khoảng cập nhật có thể giảm một phần hoạt động nền nhưng làm chậm việc phản ánh thay đổi. Hãy đo tuổi của danh sách instance và thời gian loại instance không còn phục vụ. Không giả định mỗi request nghiệp vụ luôn phát sinh một request Kubernetes API; điều này phụ thuộc supplier, cache và triển khai discovery.

Nếu ứng dụng chỉ cần gọi một Kubernetes Service ổn định, đánh giá khả năng dùng DNS Service và cơ chế cân bằng sẵn có. Quyết định bổ sung DiscoveryClient hoặc Spring Cloud LoadBalancer cần xuất phát từ yêu cầu như chọn instance, metadata hoặc chính sách định tuyến ở client.

### 6.2. ConfigMap và Secret: chọn nguồn đọc, rồi chọn cách cập nhật

Spring Cloud Kubernetes có thể tạo property source từ ConfigMap. Nhiều nguồn cấu hình, namespace và profile làm đường đọc phức tạp hơn, nên cần khai báo đúng những nguồn ứng dụng dùng. [Spring Cloud Kubernetes: ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Các lựa chọn kiến trúc cần được phân biệt:

| Nhu cầu | Hướng triển khai cần đánh giá |
| --- | --- |
| Chỉ lấy cấu hình khi khởi động | Đọc một lần; cập nhật bằng quy trình rollout có kiểm soát |
| Đọc file cấu hình được mount | Dùng nguồn file tương thích với Spring Boot; xác định riêng cơ chế nạp lại |
| Cần cập nhật động | Dùng cơ chế refresh phù hợp; giới hạn nguồn, người nhận và số lần xử lý |
| Cần theo dõi Secret | Bật có chủ đích, cấp quyền tối thiểu và tránh ghi giá trị vào log |

Không thay một bản cấu hình hợp lệ bằng dữ liệu rỗng chỉ vì lần đọc tiếp theo nhận 429. Đội ứng dụng cần quy định dữ liệu nào được phép dùng bản hợp lệ gần nhất, tuổi tối đa chấp nhận được và hành vi khi quá hạn. Cấu hình liên quan thu hồi quyền hoặc credential có thể cần chính sách nghiêm ngặt hơn cấu hình giao diện.

### 6.3. Configuration Watcher cần được tính vào ngân sách tải

Configuration Watcher có thể theo dõi thay đổi cấu hình rồi kích hoạt refresh qua HTTP hoặc Spring Cloud Bus. Việc volume được Kubernetes cập nhật không tự bảo đảm Spring đã nạp lại cấu hình. [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Trong tình huống 40 replica, một thay đổi cấu hình có thể dẫn đến nhiều lần đọc lại và nhiều lần tái tạo thành phần của ứng dụng. Đây là suy luận về thiết kế fan-out; số request thực tế phải được đo trên triển khai đã chọn.

Khi thiết kế luồng cập nhật:

- Thu hẹp namespace, selector và tập ứng dụng nhận sự kiện.
- Đánh giá gộp các thay đổi liên tiếp thay vì refresh lặp lại cho mọi lần sửa rất sát nhau.
- Giới hạn xử lý đồng thời và có hàng đợi hữu hạn cho công việc refresh.
- Kiểm tra chính sách thử lại của lời gọi refresh; không bọc thêm retry nghiệp vụ một cách mặc định.
- Xác minh thay đổi đã được áp dụng đúng ở các replica sau khi control plane phục hồi.

### 6.4. RBAC là điều kiện đúng, không phải nút tăng quota

Chỉ cấp quyền GET/LIST/WATCH cho những loại tài nguyên và namespace client thực sự sử dụng. Discovery có thể cần Service cùng Endpoints hoặc EndpointSlice, tùy lựa chọn của release; đọc Secret là một quyền riêng cần cân nhắc. Bám theo manifest của đúng client và release thay vì sao chép một ClusterRole quá rộng.

Các lệnh chỉ đọc sau giúp người vận hành có quyền kiểm tra ServiceAccount `checkout`:

```powershell
kubectl auth can-i get configmaps -n shop --as=system:serviceaccount:shop:checkout
kubectl auth can-i list services -n shop --as=system:serviceaccount:shop:checkout
kubectl auth can-i watch endpointslices.discovery.k8s.io -n shop --as=system:serviceaccount:shop:checkout
```

Người chạy lệnh với `--as` phải có quyền impersonation phù hợp. Nếu kết quả là thiếu quyền, sửa RBAC đúng phạm vi; tăng retry chỉ tạo thêm phản hồi 403.

Nếu Pod không còn cần truy cập Kubernetes API trực tiếp, có thể đánh giá tắt tự động mount token bằng `automountServiceAccountToken: false`. Chỉ làm sau khi đã kiểm tra mọi thành phần trong Pod, bao gồm discovery/config. [Kubernetes: Configure Service Accounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/).

## 7. Ví dụ WebClient: retry 429 tại một tầng

Ví dụ này xử lý **GET nghiệp vụ tới `inventory`**. Nó không thay đổi chính sách retry bên trong Fabric8 hoặc Kubernetes Java Client mà Spring Cloud Kubernetes sử dụng. Cấu hình client Kubernetes cần được kiểm tra riêng theo implementation và phiên bản dependency.

Giả định dự án đã có Spring Boot WebFlux, Spring Cloud LoadBalancer và đúng một lựa chọn DiscoveryClient của Spring Cloud Kubernetes, với các phiên bản tương thích theo BOM. `inventory` là service id discovery trả về trong namespace thực hành.

Các giá trị sau được chọn cho bài học:

| Tham số | Giá trị |
| --- | --- |
| Số lần thử lại tối đa | 3, tức tối đa 4 lần gọi tính cả lần đầu |
| Timeout mỗi lần gọi | 2 giây |
| Deadline toàn thao tác | 8 giây |
| Backoff cục bộ | Equal jitter, base 200 ms, cap 2 giây |
| `Retry-After` | Tôn trọng khi hợp lệ; quá deadline thì dừng |
| Lỗi được retry | Chỉ HTTP 429 cho GET này |

### 7.1. Tắt retry LoadBalancer trong ứng dụng thực hành

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
```

Thuộc tính trên tắt retry LoadBalancer trên phạm vi ứng dụng thực hành để đoạn code dưới sở hữu retry. Nó vẫn giữ chức năng chọn instance. Spring Cloud có các thuộc tính riêng cho status được retry và số lần thử trên cùng/khác instance; không coi việc thêm `429` vào danh sách là bảo đảm client sẽ tôn trọng `Retry-After`. [Spring Cloud Commons: common abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html), [Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html).

Trong ứng dụng có nhiều client, cần thiết kế phạm vi chính sách tương ứng. Đồng thời kiểm tra gateway, service mesh và HTTP connector để tránh một tầng khác tiếp tục nhân số lần gọi.

### 7.2. Khai báo builder có LoadBalancer

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder inventoryWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Với `@LoadBalanced`, tên host `inventory` bên dưới được dùng làm service id để chọn địa chỉ instance. Nếu chọn kiến trúc gọi trực tiếp DNS Service, dùng client thường và địa chỉ DNS phù hợp thay cho cách khai báo này. [Spring Cloud Commons: Spring WebClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html).

### 7.3. Cài đặt chính sách có giới hạn

Đoạn mã dùng cú pháp Java 17 trở lên; yêu cầu Java tối thiểu thực tế còn phụ thuộc dòng Spring Boot/Spring Cloud mà dự án chọn. Đặt lớp trong package được ứng dụng quét component.

```java
import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class InventoryClient {

    private static final long MAX_RETRIES = 3;
    private static final Duration PER_ATTEMPT = Duration.ofSeconds(2);
    private static final Duration TOTAL = Duration.ofSeconds(8);

    private final WebClient client;

    public InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.client = builder.clone().baseUrl("http://inventory").build();
    }

    public Mono<String> getItem(String id) {
        return Mono.defer(() -> {
            long startedNanos = System.nanoTime();

            Retry policy = Retry.from(signals -> signals.concatMap(signal -> {
                Throwable failure = signal.failure();

                if (!(failure instanceof WebClientResponseException response)
                        || response.getStatusCode().value() != 429
                        || signal.totalRetries() >= MAX_RETRIES) {
                    return Mono.<Long>error(failure);
                }

                long retryIndex = signal.totalRetries(); // 0, 1, 2
                long ceilingMs = Math.min(2_000L, 200L << (int) retryIndex);
                long localMs = ceilingMs / 2
                        + ThreadLocalRandom.current().nextLong(ceilingMs / 2 + 1);
                Duration delay = Duration.ofMillis(localMs);

                Optional<Duration> serverDelay = retryAfter(response.getHeaders());
                if (serverDelay.isPresent()) {
                    if (serverDelay.get().compareTo(delay) > 0) {
                        delay = serverDelay.get();
                    }
                    delay = delay.plusMillis(
                            ThreadLocalRandom.current().nextLong(101));
                }

                Duration remaining = TOTAL.minusNanos(
                        System.nanoTime() - startedNanos);
                Duration roomForWait = remaining.minus(PER_ATTEMPT);
                if (roomForWait.isNegative()
                        || delay.compareTo(roomForWait) >= 0) {
                    return Mono.<Long>error(failure);
                }

                // Production: kiểm tra thêm ngân sách retry dùng chung ở đây.
                // Mono.delay chờ bằng lịch hẹn, không giữ thread bằng sleep.
                return Mono.delay(delay);
            }));

            return Mono.defer(() -> client.get()
                            .uri("/items/{id}", id)
                            .retrieve()
                            .bodyToMono(String.class)
                            .timeout(PER_ATTEMPT))
                    .retryWhen(policy)
                    .timeout(TOTAL);
        });
    }

    private static Optional<Duration> retryAfter(HttpHeaders headers) {
        String value = headers.getFirst(HttpHeaders.RETRY_AFTER);
        if (value == null || value.isBlank()) {
            return Optional.empty();
        }

        String raw = value.trim();
        if (raw.matches("[0-9]+")) {
            try {
                return Optional.of(Duration.ofSeconds(Long.parseLong(raw)));
            } catch (NumberFormatException tooLarge) {
                // Số giây vượt long chắc chắn không vừa deadline 8 giây.
                return Optional.of(Duration.ofSeconds(Long.MAX_VALUE));
            }
        }

        try {
            Instant retryAt = ZonedDateTime.parse(
                    raw, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant();
            Duration wait = Duration.between(Instant.now(), retryAt);
            return Optional.of(wait.isNegative() ? Duration.ZERO : wait);
        } catch (DateTimeParseException invalidDate) {
            return Optional.empty();
        }
    }
}
```

`retrieve()` mặc định chuyển response lỗi 4xx/5xx thành `WebClientResponseException`, nhờ đó chính sách có thể kiểm tra status và header. Với `Retry.from`, tín hiệu phát ra kích hoạt một lần đăng ký lại; trả `Mono.error(failure)` giữ lỗi khi cần dừng. Không kết thúc companion bằng một luồng rỗng để vô tình nuốt lỗi. [Spring Framework: retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html), [Reactor: Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html).

Một số điểm cần đọc kỹ trong ví dụ:

- Hai `Mono.defer` tách phạm vi thao tác logic và từng lần gọi; mỗi subscription mới có deadline riêng.
- Timeout hai giây nằm trong phần được retry; timeout tám giây bao cả các lần chờ và gọi.
- Trước khi chờ, code dành đủ hai giây cho lần gọi tiếp theo. Vì vậy có thể dừng trước khi dùng hết ba retry.
- Khi không còn phù hợp với deadline, code trả lỗi 429 gần nhất. Nếu tổng thao tác chạm timeout trong lúc đang chạy, kết quả có thể là lỗi timeout tổng.
- Code không retry 401, 403, lỗi kết nối hoặc timeout. Những lỗi đó cần chính sách riêng nếu nghiệp vụ yêu cầu.
- Bộ phân tích ngày giờ minh họa dùng dạng RFC 1123 phổ biến của HTTP-date; nếu cần tương thích các dạng HTTP-date cũ, bổ sung parser tương ứng và kiểm thử riêng.
- Giới hạn mỗi request chưa thay thế giới hạn đồng thời và ngân sách retry trên toàn workload. Các giới hạn đó chưa được cài trong đoạn mã này.

Khi đưa vào hệ thống thật, áp dụng các customizer, quan sát và cấu hình connector của dự án; đặt giới hạn pool, connect timeout và TLS theo môi trường. Nếu tự xử lý response bằng `exchangeToMono`, cần tiêu thụ hoặc giải phóng body trong luồng xử lý để bảo vệ connection pool. [Spring Framework: Exchange](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html).

## 8. Thử lại Kubernetes API và khôi phục watch

Chính sách cho API server phải nằm ở đúng client mà Spring Cloud Kubernetes đang dùng. Không suy ra một thuộc tính như `spring.cloud.kubernetes.client.qps` luôn tồn tại hay có cùng nghĩa giữa các starter.

Khi cấu hình, ghi nhận ít nhất: loại client, phiên bản, thành phần tạo client bean, limiter phía client, số lần retry sẵn có, timeout request và cơ chế reconnect watch. Kiểm tra tên thuộc tính trong tài liệu và configuration metadata của đúng release trước khi đưa vào cấu hình triển khai.

Phân biệt ba hoạt động:

| Hoạt động | Chính sách cần chú ý |
| --- | --- |
| GET/LIST ngắn | Timeout hữu hạn, phạm vi hẹp, không lồng thêm retry nếu client đã xử lý |
| WATCH dài hạn | Thời hạn kết nối, nối lại có backoff/jitter, không reconnect đồng loạt |
| LIST lại để khôi phục watch | Giới hạn tải khi nhiều replica cùng phải đồng bộ lại |

Không áp dụng timeout hai giây của ví dụ GET nghiệp vụ cho mọi watch dài hạn. Đồng thời, không để một vòng reconnect không giới hạn tốc độ liên tục khởi tạo kết nối rồi gọi LIST lại.

Khi có cache đang phục vụ ứng dụng, phân biệt **cache còn dữ liệu hợp lệ nhưng chưa cập nhật** với **discovery thật sự không có instance**. Trong khoảng gián đoạn control plane, cách xử lý cần tuân theo tuổi dữ liệu tối đa đã định. Sau khi kết nối phục hồi, kiểm tra sự hội tụ của trạng thái thay vì chỉ kiểm tra “đã reconnect”.

## 9. Kết hợp với các cơ chế bảo vệ khác

Backoff giãn các lần thử lại; nó không giới hạn toàn bộ request mới đến ứng dụng. Phối hợp cơ chế theo mục tiêu:

| Cơ chế | Mục tiêu | Điểm cần tránh |
| --- | --- | --- |
| Rate limiter | Giới hạn tốc độ gửi theo phạm vi quota | Tính quota từng Pod mà quên số replica |
| Bulkhead/giới hạn đồng thời | Bảo vệ số tác vụ, connection hoặc slot đang dùng | Hàng đợi không có giới hạn và deadline |
| Circuit breaker | Tạm ngừng gọi khi dependency liên tục có vấn đề | Tính mọi 429 riêng của một tenant thành lỗi chung của tất cả tenant |
| Cache dữ liệu hợp lệ | Giảm đọc lại trong khoảng chấp nhận được | Dùng dữ liệu hết hạn mà không đo tuổi hoặc không cho phép về nghiệp vụ |
| Retry budget | Khống chế tổng tải bổ sung do retry | Chỉ giới hạn từng request rồi bỏ qua tổng lưu lượng |

Cần chọn rõ tài nguyên được bảo vệ trong lúc backoff. Chờ bằng `Mono.delay` tránh giữ thread, nhưng vẫn còn trạng thái của thao tác logic; nếu số thao tác chờ không giới hạn thì bộ nhớ và độ trễ vẫn tăng. Không giữ connection hoặc slot dành cho request mạng đang chạy chỉ để chờ timer retry.

### Probe của Pod phải phản ánh đúng khả năng phục vụ

Liveness thất bại có thể dẫn đến restart container, còn readiness thất bại làm Pod không được dùng như một endpoint sẵn sàng theo cơ chế Service thông thường. [Kubernetes: liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Vì vậy, không gắn liveness trực tiếp với việc lần đọc Kubernetes API gần nhất có thành công hay không. Trong một đợt 429, restart hàng loạt có thể tạo thêm request khởi động. Readiness cần trả lời ứng dụng còn phục vụ an toàn với trạng thái hiện có hay không; startup probe cần phù hợp với thời gian khởi tạo thực tế.

Nếu phản hồi cho người gọi bên ngoài, chọn status theo hợp đồng API. Một 429 từ API server dùng nội bộ để đọc cấu hình không tự động có nghĩa người dùng cuối đã vượt quota. Với quota thực sự của người gọi, có thể giữ ngữ nghĩa 429; với dependency không sẵn sàng, cần xem xét hợp đồng lỗi tương ứng. Không đổi lỗi thành `200` với danh sách rỗng rồi để người dùng hiểu đó là dữ liệu thật.

## 10. Quan sát được tải gốc, tải retry và độ mới dữ liệu

Log cho mỗi quyết định retry nên đủ để ghép theo thao tác:

```text
operation=inventory.read target=inventory status=429
attempt=2 max_attempts=4 retry_after_ms=1000 wait_ms=1086
remaining_ms=7420 decision=retry request_id=demo-42
```

Trong ví dụ log này, `attempt=2` là lần gọi sắp thực hiện. Ghi thống nhất quy ước đếm trong hệ thống. Không đưa token, nội dung Secret hoặc toàn bộ response nhạy cảm vào log.

Các số đo ứng dụng có thể tự định nghĩa:

| Số đo | Ý nghĩa cần quan sát |
| --- | --- |
| Request gốc và request vật lý | Tính số lần gọi thực tế trên một thao tác logic |
| Số 429 theo target/operation | Phân biệt control plane và dịch vụ nghiệp vụ |
| Retry được thực hiện/bị từ chối | Phân biệt hết lần thử, hết deadline và hết ngân sách |
| Phân phối thời gian backoff | Kiểm tra có gửi dồn hoặc gửi sớm hơn chính sách không |
| Request đang chạy và tác vụ đang chờ | Phát hiện connection pool/hàng đợi bị dồn |
| Tuổi cấu hình và tuổi danh sách instance | Đánh giá dữ liệu có còn đủ mới để phục vụ không |
| Tần suất reconnect và LIST lại | Tìm vòng khôi phục watch tạo tải quá mức |

Những mục trên là yêu cầu quan sát do ứng dụng thiết kế, không phải tên metric mặc định được Spring Cloud Kubernetes cam kết cung cấp. Chọn nhãn có số lượng giá trị hữu hạn; tránh dùng request id, tên Secret tùy ý hoặc URL đầy đủ làm nhãn metric.

Ở control plane, nếu đã thu thập và được cấp quyền xem, đối chiếu `apiserver_flowcontrol_rejected_requests_total`, `apiserver_flowcontrol_current_inqueue_requests` và `apiserver_flowcontrol_request_wait_duration_seconds` để kiểm tra từ chối/xếp hàng do APF. [Kubernetes: APF observability](https://kubernetes.io/docs/concepts/cluster-administration/flow-control/#observability).

Đánh giá thành công bằng cả số lỗi, độ trễ và số request vật lý. Một cấu hình che được 429 bằng retry nhưng làm p99 vượt thời gian người dùng chờ vẫn chưa đạt mục tiêu phục hồi.

## 11. Thực hành có kiểm soát

Thực hành trong môi trường thử nghiệm, với mock `inventory` do bạn kiểm soát. Giữ một instance mock khi cần kiểm chứng chuỗi response; nhiều instance với bộ đếm riêng có thể làm thứ tự response khác dự kiến. Không cần cố tình gây quá tải API server để học cách xử lý 429.

### 11.1. Xác minh retry và thời gian chờ

Cấu hình mock hoặc công cụ giả lập HTTP theo các kịch bản dưới đây, rồi gọi `getItem("42")`. Ghi timestamp nhận request ở mock và kết quả của thao tác logic.

| Kịch bản | Chuỗi response của mock | Kết quả cần kiểm chứng |
| --- | --- | --- |
| Phục hồi nhanh | `429 Retry-After: 1`, sau đó `200` | Hai lần gọi; khoảng từ response lỗi đến request sau ít nhất một giây |
| Chờ quá lâu | `429 Retry-After: 60` | Một lần gọi; dừng theo lỗi, không ngủ 60 giây và không gửi lại sau hai giây |
| Không có header | Liên tục `429` trả nhanh | Tối đa bốn lần gọi; chờ theo equal jitter; kết quả cuối vẫn là lỗi |
| Header sai | `429 Retry-After: invalid`, sau đó `200` | Dùng backoff cục bộ, không lỗi parser và không retry tức thì |
| HTTP-date | `429` với thời điểm tương lai, sau đó `200` | Đợi theo thời điểm đã tính; kiểm soát đồng hồ trong phép kiểm chứng |
| Thiếu quyền | `403`, sau đó mock sẵn sàng trả `200` | Chỉ một lần gọi; policy này không retry 403 |
| Lần gọi quá chậm | Mock chậm hơn hai giây | Lỗi timeout; policy này không tự retry timeout |
| 429 với thời gian chờ bằng 0 | `429 Retry-After: 0`, sau đó `200` | Vẫn có backoff cục bộ |

So sánh mốc **nhận response 429** với mốc **gửi request kế tiếp**, không chỉ so thời gian bắt đầu hai request. Scheduler có thể làm thời gian chờ dài hơn dự kiến, nên kiểm tra sàn chờ và khoảng dung sai hợp lý.

Ngoài các trường hợp chức năng, kiểm chứng việc hủy subscription trong lúc chờ: request đã hủy không nên tiếp tục sinh retry mới. Với code được dùng trong production, thêm kiểm chứng header số rất lớn, số âm và ngày đã qua, cùng ngân sách retry dùng chung.

### 11.2. Quan sát discovery/config trong một rollout nhỏ

Với namespace thử nghiệm đã có ứng dụng, dùng các lệnh chỉ đọc:

```powershell
kubectl get pods -n shop
kubectl get events -n shop --sort-by=.lastTimestamp
kubectl get endpointslices -n shop -l kubernetes.io/service-name=inventory
kubectl logs -n shop -l app=checkout --all-containers=true --since=10m --prefix=true
```

Đối chiếu nhãn log với manifest thực tế. Sự kiện Kubernetes không thay thế log client, audit hoặc metric API server để xác nhận 429.

Tiếp theo, thông qua quy trình triển khai của môi trường lab, quan sát một đợt thay đổi nhỏ rồi so sánh:

1. Số request Kubernetes API lúc ổn định và trong lúc Pod khởi động.
2. Số thao tác nghiệp vụ gốc với tổng số request xuống `inventory`.
3. Thời gian discovery phản ánh EndpointSlice thay đổi.
4. Thời gian các replica nhận cấu hình mới và phiên bản cấu hình đang áp dụng.
5. Số restart, trạng thái readiness và số tác vụ chờ retry.

Khi tạm gián đoạn đường tới API server trong lab, xác minh cả hai giai đoạn: ứng dụng hành xử theo chính sách dữ liệu cũ trong thời gian mất kết nối, rồi hội tụ đúng sau khi phục hồi. Không kết luận đạt chỉ vì log đã ngừng xuất hiện lỗi.

## 12. Quy trình xử lý khi xuất hiện 429

1. **Xác định nguồn:** lấy status, target, thời điểm và operation; phân biệt API server, gateway, dịch vụ và limiter cục bộ.
2. **Đo mức khuếch đại:** so request vật lý với thao tác gốc; kiểm tra retry ở gateway, mesh, LoadBalancer, ứng dụng và Kubernetes client.
3. **Giảm áp lực trước:** hạn chế request mới, công việc đồng thời, burst khởi động và refresh fan-out theo khả năng thực tế.
4. **Kiểm tra nhịp thử lại:** số lần hữu hạn, jitter, `Retry-After`, deadline và ngân sách dùng chung.
5. **Kiểm tra cấu hình hạ tầng:** phạm vi namespace, nguồn ConfigMap/Secret, lifecycle watch, RBAC và dữ liệu cache đang được dùng.
6. **Đánh giá hành vi phục vụ:** dữ liệu có đủ mới, Pod có bị restart lặp và lỗi trả ra có đúng hợp đồng API hay không.
7. **Xác nhận phục hồi:** tải retry giảm, request gốc hoàn thành trong mục tiêu độ trễ, discovery/cấu hình hội tụ và không có hàng đợi tiếp tục tăng.

Nếu tải hợp lệ đã được tối ưu mà control plane vẫn thiếu khả năng phục vụ, phối hợp với người quản trị để đánh giá capacity và chính sách APF bằng số liệu. Thay đổi đó cần được xem cùng tải của các workload khác; tăng quyền RBAC, tăng retry hoặc thêm replica ứng dụng không tự giải quyết giới hạn xử lý của API server.
