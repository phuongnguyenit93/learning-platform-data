# Đối chiếu log ứng dụng, sự kiện Kubernetes và distributed trace

Một yêu cầu thất bại trong ứng dụng Spring chạy trên Kubernetes có thể để lại nhiều dấu vết: log ở dịch vụ gọi, span của lời gọi HTTP, trạng thái container bị khởi động lại và Event do kubelet phát ra. Mỗi nguồn mô tả một phần khác nhau của sự cố. Muốn nối chúng thành lời giải thích đáng tin cậy, cần dùng đúng định danh, đúng thời gian và đúng phạm vi bằng chứng.

Bài học thuộc chương **Khả năng quan sát** của module **SPRING_CLOUD_KUBERNETES**. Trọng tâm là điều tra các đường đi có DiscoveryClient, Spring Cloud LoadBalancer, ConfigMap, Secret, Configuration Watcher và sức khỏe Pod. Không cần bật tất cả các tính năng này để có tracing; chỉ quan sát những thành phần thực sự tham gia kiến trúc.

## 1. Mục tiêu và điều kiện thực hành

Sau bài học, bạn có thể:

- Đi từ một lỗi nghiệp vụ đến trace, log của đúng instance và Event của đúng đối tượng Kubernetes.
- Phân biệt trace ID, span ID, Pod name, Pod UID, container ID và revision cấu hình.
- Thu thập log trước và sau restart mà không trộn các vòng đời container.
- Đọc đúng thời điểm quan sát, chuỗi Event và giới hạn của dữ liệu được lưu.
- Xác định bằng chứng còn thiếu trước khi kết luận nguyên nhân.
- Kiểm chứng luồng truyền context qua một lời gọi HTTP giữa hai ứng dụng Spring.

Ví dụ tracing dùng **Spring Boot 3.5.x**, Micrometer Tracing với OpenTelemetry và bộ phiên bản Spring Cloud Kubernetes **3.3.x** tương thích qua Spring Cloud BOM. Đây là mốc tham chiếu của ví dụ, không phải hướng dẫn nâng cấp.

Lab giả định có namespace `obs-lab`, hai ứng dụng `orders` và `pricing`, Service `pricing` trên cổng 8080, cùng hệ thống nhận OTLP và xem trace đã hoạt động. Phần Java trình bày các lớp cần ghép vào ứng dụng mẫu, không phải một bộ manifest triển khai cluster hoàn chỉnh.

## 2. Ba nguồn dữ liệu trả lời ba loại câu hỏi

| Nguồn | Câu hỏi phù hợp | Giới hạn quan trọng |
| --- | --- | --- |
| Log ứng dụng | Mã đã đi qua nhánh nào, gặp exception gì, đang dùng cấu hình nào? | Có thể thiếu context, bị lọc, bị rotate hoặc chưa kịp ghi |
| Kubernetes Event | Thành phần Kubernetes đã báo điều gì về một đối tượng? | Không phải lịch sử đầy đủ của mọi thay đổi hay lỗi |
| Distributed trace | Yêu cầu đi qua những thao tác và dịch vụ nào, tốn thời gian ở đâu? | Chỉ thấy những phần được instrument, giữ lại và xuất thành công |

Cần phân biệt thêm ba khái niệm cùng có chữ “event”:

- **Kubernetes Event:** đối tượng tài nguyên do thành phần trong cluster báo cáo.
- **Sự kiện watch:** thông báo thay đổi tài nguyên qua Kubernetes API, dùng bởi client hoặc controller.
- **Span event hoặc Spring application event:** sự kiện trong hệ thống tracing hoặc trong tiến trình Spring.

Configuration Watcher quan sát ConfigMap qua watch không có nghĩa mỗi thay đổi đó tạo một Kubernetes Event. Một lỗi đọc Secret trong ứng dụng cũng không bắt buộc tạo Event `Warning` mà bạn nhìn thấy qua `kubectl get events`.

Kubernetes mô tả Event là dữ liệu bổ sung theo cơ chế best effort và có thời gian lưu hữu hạn. Vì vậy “không tìm được Event” không chứng minh “không có sự cố”. Xem [Kubernetes Event](https://kubernetes.io/docs/reference/kubernetes-api/core/event-v1/).

~~~mermaid
flowchart LR
    Failure["Yêu cầu lỗi"] --> Trace["Trace ID và span"]
    Trace --> Logs["Log của dịch vụ / instance"]
    Logs --> Identity["Cluster + namespace + Pod UID"]
    Identity --> Status["Trạng thái Pod / container"]
    Identity --> Events["Kubernetes Event"]
    Logs --> Revision["Revision cấu hình / bản triển khai"]
    Status --> Timeline["Timeline có nguồn bằng chứng"]
    Events --> Timeline
    Trace --> Timeline
    Revision --> Timeline
~~~

## 3. Chọn khóa đối chiếu trước khi tìm kiếm

### 3.1. Danh tính của yêu cầu

`traceId` nối các span thuộc cùng trace. `spanId` xác định một thao tác trong trace; các dịch vụ trong cùng trace thường có span ID khác nhau. Không yêu cầu span ID của log ở `orders` phải bằng span ID của log ở `pricing`.

Một request ID nghiệp vụ có thể giúp tìm yêu cầu khi không còn trace, nhưng không tự trở thành trace ID. Một thông điệp bất đồng bộ, lần retry hoặc công việc chạy nền cũng cần quy tắc liên kết riêng.

### 3.2. Danh tính của workload

| Khóa | Dùng để làm gì? | Điều dễ nhầm |
| --- | --- | --- |
| Cluster hoặc định danh nguồn cluster | Tách những môi trường có tên trùng nhau | Cùng namespace và Pod name ở hai cluster vẫn là hai workload |
| Namespace | Giới hạn phạm vi tài nguyên | Tên Service hoặc Pod không đủ duy nhất trên toàn cluster |
| Pod name | Tìm nhanh Pod khi vận hành | Tên có thể được dùng lại, đặc biệt với StatefulSet |
| Pod UID | Nhận diện một vòng đời đối tượng Pod | Restart container trong cùng Pod không tự đổi Pod UID |
| Container name | Chọn container ứng dụng hay sidecar | Log sidecar có thể bị trộn với log ứng dụng |
| Container ID hoặc lần restart | Tách những tiến trình kế tiếp trong cùng Pod | Pod UID giống nhau chưa chứng minh cùng tiến trình |
| Service và phiên bản ứng dụng | Nhóm theo chức năng và bản phát hành | Không xác định duy nhất một instance |
| Revision cấu hình công khai | Nối cập nhật cấu hình với hành vi thực tế | Thời điểm nhận refresh chưa chắc là thời điểm áp dụng |

IP có ích khi truy vết một đích mạng nhưng không phải định danh bền vững: IP có thể được tái sử dụng, là ClusterIP hoặc thuộc proxy. Muốn nối IP với Pod cần dữ liệu ánh xạ ở **đúng khoảng thời gian sự cố**.

OpenTelemetry có các thuộc tính tài nguyên như `k8s.namespace.name`, `k8s.pod.name` và `k8s.pod.uid`. Hãy kiểm tra backend thực tế đã có chúng; việc đặt tên ứng dụng không tự bổ sung đầy đủ metadata Kubernetes. Xem [Kubernetes semantic conventions](https://opentelemetry.io/docs/specs/semconv/resource/k8s/).

### 3.3. Bộ khóa tối thiểu để điều tra

Một bộ bằng chứng hữu ích thường gồm:

~~~text
cluster
namespace
service.name và phiên bản ứng dụng
pod.name + pod.uid
container.name + container.id hoặc restart count
trace.id + span.id nếu có
timestamp UTC + khoảng thời gian tìm kiếm
config.revision nếu sự cố liên quan cấu hình
~~~

Đây là hợp đồng dữ liệu đề xuất, không phải tập field mặc định chung cho mọi backend. Chẳng hạn, MDC có thể dùng `traceId` còn kho log lưu thành `trace_id`; cần chuẩn hóa ánh xạ thay vì tìm một tên field không tồn tại.

Không gắn trace ID, Pod UID, request ID hoặc revision thay đổi liên tục làm nhãn metric chỉ để liên kết dữ liệu. Chúng phù hợp hơn trong log, trace hoặc metadata của target.

## 4. Chuẩn bị log có context và metadata Pod

Trong container spec, lấy thông tin Pod bằng Downward API:

~~~yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  - name: POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
  - name: NODE_NAME
    valueFrom:
      fieldRef:
        fieldPath: spec.nodeName
~~~

Cách này không đòi ứng dụng phải có quyền `list pods` chỉ để biết chính mình là Pod nào. Các trường khả dụng được quy định trong [Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/).

Với Micrometer Tracing, Spring Boot có thể đưa trace ID và span ID từ MDC vào log. Ví dụ tùy chỉnh phần correlation trong cấu hình ứng dụng:

~~~yaml
spring:
  application:
    name: orders

logging:
  pattern:
    correlation: "[traceId=%X{traceId:-},spanId=%X{spanId:-},ns=${POD_NAMESPACE:local},pod=${POD_NAME:local},podUid=${POD_UID:local}] "
~~~

Đổi `spring.application.name` thành `pricing` ở ứng dụng tương ứng. Pattern trên bổ sung metadata vào log chữ; nó không tự tạo resource attributes cho trace.

Khi dùng JSON logging hoặc collector, cấu hình bộ phân tích để giữ từng field riêng. Một bản ghi **đã chuẩn hóa để minh họa** có thể là:

~~~json
{
  "timestamp": "2026-11-24T03:15:00.125Z",
  "level": "WARN",
  "service.name": "orders",
  "k8s.namespace.name": "obs-lab",
  "k8s.pod.name": "orders-example",
  "k8s.pod.uid": "859507bd-3475-4d67-b0ef-7225c71c204d",
  "container.name": "orders",
  "trace_id": "9a4e5b2f1c8d4076ab93d581c27e604f",
  "span_id": "2000000000000001",
  "event": "pricing_call_failed",
  "downstream_status": 503
}
~~~

Đây không phải đầu ra JSON tự sinh bởi pattern ở trên. Pipeline cần cấu hình định dạng, parse và enrichment phù hợp để có cấu trúc như vậy.

Log khởi động, scheduler hoặc một callback không có span hiện hành có thể để trống trace ID. Không tự điền một ID giả để làm log “đủ field”. Nếu log từ request mất ID sau khi chuyển thread, kiểm tra truyền context qua executor, Reactor hoặc cơ chế bất đồng bộ đang dùng.

Cũng cần phân biệt timestamp do ứng dụng ghi, timestamp runtime thêm vào log và thời điểm collector nhận bản ghi. Sự chậm trễ của collector không tự là sự chậm trễ nghiệp vụ.

## 5. Truyền trace qua HTTP trong ứng dụng Spring

Spring Boot 3.5 có cấu hình cho Micrometer Tracing và OpenTelemetry OTLP. Các dependency liên quan trong ví dụ gồm:

~~~text
org.springframework.boot:spring-boot-starter-actuator
io.micrometer:micrometer-tracing-bridge-otel
io.opentelemetry:opentelemetry-exporter-otlp
~~~

Dùng phiên bản do BOM phù hợp quản lý, bên cạnh dependency web của ứng dụng. Nếu đã có Java agent hoặc starter OpenTelemetry khác, kiểm tra kiến trúc instrumentation trước khi bổ sung để tránh tạo span trùng.

Cấu hình xuất trace mẫu cho lab:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://otel-collector.observability.svc.cluster.local:4318/v1/traces
~~~

Endpoint trên là ví dụ OTLP HTTP; phải có receiver thực sự lắng nghe và đường mạng cho phép truy cập. Sampling 100% dùng để dễ kiểm chứng trong lab. Nó không bảo đảm backend nhận mọi span nếu exporter, hàng đợi hoặc đường mạng bị lỗi.

Dùng builder do Spring Boot tự cấu hình để tạo HTTP client, nhờ đó giữ phần instrumentation và propagation. Tài liệu có hướng dẫn ở [Spring Boot Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html). Có thể đối chiếu tên thuộc tính theo [Common Application Properties 3.5](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).

### 5.1. Client ở ứng dụng orders

~~~java
package example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PricingClientConfiguration {

    @Bean
    RestClient pricingClient(
            RestClient.Builder builder,
            @Value("${demo.pricing-base-url:http://pricing:8080}")
            String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}
~~~

Ví dụ gọi bằng DNS Service trong cùng namespace. Nếu dự án thực sự dùng `@LoadBalanced` và DiscoveryClient, cấu hình client theo kiến trúc đó và kiểm tra lại propagation sau khi áp dụng các customizer. Đừng thêm LoadBalancer chỉ để tạo trace.

Controller `orders`:

~~~java
package example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class QuoteController {

    private static final Logger log =
            LoggerFactory.getLogger(QuoteController.class);

    private final RestClient pricingClient;

    public QuoteController(RestClient pricingClient) {
        this.pricingClient = pricingClient;
    }

    @GetMapping("/demo/quote")
    public String quote(
            @RequestParam(defaultValue = "false") boolean fail) {

        log.info("event=quote_started demo_fail={}", fail);

        try {
            String result = pricingClient.get()
                    .uri(uriBuilder -> uriBuilder
                            .path("/demo/price")
                            .queryParam("fail", fail)
                            .build())
                    .retrieve()
                    .body(String.class);

            log.info("event=quote_completed");
            return result;
        }
        catch (RestClientResponseException exception) {
            log.warn("event=pricing_call_failed downstream_status={}",
                    exception.getStatusCode().value());
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY,
                    "Pricing unavailable",
                    exception);
        }
    }
}
~~~

Đây là đường gọi lab để nhìn rõ lỗi HTTP từ downstream. Cấu hình timeout và xử lý lỗi mạng riêng trước khi dùng trong dịch vụ thật; đoạn bắt exception trên chỉ xử lý nhóm lỗi phản hồi HTTP tương ứng.

### 5.2. Endpoint ở ứng dụng pricing

~~~java
package example.pricing;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class PriceController {

    private static final Logger log =
            LoggerFactory.getLogger(PriceController.class);

    @GetMapping("/demo/price")
    public String price(
            @RequestParam(defaultValue = "false") boolean fail) {

        if (fail) {
            log.warn("event=demo_price_rejected");
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Demo failure");
        }

        log.info("event=price_returned");
        return "100000";
    }
}
~~~

Tham số gây lỗi chỉ dành cho lab. Không triển khai một chức năng tạo lỗi công khai như vậy trong sản phẩm.

Khi hai bên instrument và propagation đúng, trace có thể gồm:

~~~text
orders: HTTP server /demo/quote
  └─ orders: HTTP client đến pricing
       └─ pricing: HTTP server /demo/price
~~~

Ba span có cùng trace ID nhưng span ID khác nhau. Log ở `orders` trước hoặc sau lời gọi thường thuộc scope của server span, không nhất thiết thuộc client span đang thấy trong waterfall.

## 6. Đọc Kubernetes Event đúng đối tượng và thời điểm

Đừng nối Event với Pod chỉ bằng tên. Một Event có UID riêng của nó, đồng thời tham chiếu đối tượng được nói đến:

| Ý nghĩa | core/v1 Event | events.k8s.io/v1 Event |
| --- | --- | --- |
| Đối tượng liên quan | `involvedObject` | `regarding` |
| UID của Pod được nói đến | `involvedObject.uid` | `regarding.uid` |
| Nội dung mô tả | `message` | `note` |
| Thời điểm quan sát đầu | `eventTime` hoặc các trường thời gian tương thích cũ | `eventTime` |
| Chuỗi lặp | `series` nếu có, hoặc `count` và timestamp cũ | `series.count`, `series.lastObservedTime` |

`metadata.uid` của Event không phải Pod UID. `metadata.creationTimestamp` là lúc đối tượng Event được tạo, không nhất thiết là lần xuất hiện gần nhất của một chuỗi lặp.

Với dữ liệu cũ, `firstTimestamp` và `lastTimestamp` có thể hữu ích. Với dữ liệu dùng series, xem `series.lastObservedTime` và count. Ghi lại API version của bản ghi và những trường thực tế có mặt; không mặc định mọi reporter điền cùng một tập trường. Đối chiếu [schema core/v1 Event](https://kubernetes.io/docs/reference/kubernetes-api/core/event-v1/) và [định nghĩa events.k8s.io/v1](https://github.com/kubernetes/api/blob/v0.32.0/events/v1/types.go).

Một bản Event rút gọn để đọc, không phải manifest dùng để apply:

~~~yaml
apiVersion: events.k8s.io/v1
kind: Event
metadata:
  name: pricing-example.event-example
eventTime: "2026-11-24T03:15:00Z"
regarding:
  kind: Pod
  namespace: obs-lab
  name: pricing-example
  uid: 3be351f2-7138-4da2-95c4-84a346b305b9
reason: Unhealthy
type: Warning
note: "Readiness probe failed"
reportingController: kubernetes.io/kubelet
series:
  count: 4
  lastObservedTime: "2026-11-24T03:15:15Z"
~~~

Bản ghi này cho biết reporter đã quan sát tình trạng readiness thất bại và gộp bốn lần xuất hiện trong series. Nó không cung cấp bốn timestamp riêng, không chứng minh mỗi request nghiệp vụ đều lỗi trong toàn khoảng đó và không tự chứng minh container bị restart. Readiness thất bại và liveness thất bại có tác động khác nhau.

Lệnh sắp xếp theo `metadata.creationTimestamp` chỉ sắp xếp thời gian tạo đối tượng Event. Nếu một Event đã tồn tại rồi được cập nhật count, thứ tự đó không mô tả chính xác thứ tự các lần xuất hiện mới nhất.

`Warning` cũng không tự là nguyên nhân gốc của một lỗi nghiệp vụ. Một Event gần thời điểm trace chỉ là ứng viên cần đối chiếu thêm.

## 7. Quy trình điều tra từ một lỗi nghiệp vụ

Các lệnh dưới đây dùng PowerShell. Chúng là ví dụ đọc dữ liệu trong môi trường mà bạn có quyền; thay tên cluster, namespace, Pod và container cho đúng hệ thống.

### Bước 1: Cố định phạm vi

Ghi trace ID nếu có, thời gian UTC, lỗi người dùng nhận được, dịch vụ và môi trường. Ví dụ:

~~~text
Cluster: lab-cluster
Namespace: obs-lab
Khoảng điều tra: 2026-11-24T03:14:30Z đến 2026-11-24T03:16:30Z
Service vào: orders
Trace ID: 9a4e5b2f1c8d4076ab93d581c27e604f
Triệu chứng: /demo/quote trả HTTP 502
~~~

Kiểm tra context trước khi dùng lệnh:

~~~powershell
kubectl config current-context

$namespace = 'obs-lab'
$traceId = '9a4e5b2f1c8d4076ab93d581c27e604f'
$fromUtc = '2026-11-24T03:14:30Z'
~~~

Thời gian trong ví dụ là dữ liệu minh họa. Khi điều tra thật, dùng khoảng bao trùm sự cố và mở rộng có kiểm soát nếu chưa đủ dữ liệu. Tránh tìm trên toàn bộ lịch sử rồi ghép các bản ghi trùng tên nhưng khác lần triển khai.

### Bước 2: Đọc trace và xác định cạnh bị lỗi

Trên trace backend, tìm trace ID và ghi:

- Service, span kind, span ID và quan hệ parent/child.
- Thời điểm bắt đầu, duration và loại lỗi của cạnh.
- HTTP status hoặc exception đã được ghi.
- Resource attributes xác định instance nếu có.
- Đích mạng hoặc instance được chọn nếu instrumentation có cung cấp.

HTTP 502 ở gateway hoặc `orders` không chứng minh `orders` là nơi phát sinh nguyên nhân gốc. Hãy lần theo cạnh downstream. Với ví dụ lab, có thể thấy `pricing` trả 503 rồi `orders` chuyển thành 502.

Không cộng duration của các span lồng nhau như các thao tác độc lập. Một server span có thể đã bao gồm thời gian chờ client span; các span song song còn có thể chồng lấn.

### Bước 3: Tìm log theo trace rồi thu hẹp về Pod

Ví dụ tìm log của tất cả replica `orders` đang tồn tại:

~~~powershell
kubectl -n $namespace logs -l app=orders -c orders --since-time=$fromUtc --timestamps=true --prefix=true --tail=-1 |
    Select-String -SimpleMatch $traceId
~~~

Sau đó làm tương tự với `app=pricing` và container `pricing` nếu trace đi qua nó.

`--prefix` giữ tên Pod và container ở mỗi dòng; `--tail=-1` tránh bỏ sót do giới hạn số dòng mặc định khi dùng selector. Dùng cả cluster và namespace để tìm trong kho log tập trung khi Pod đã bị xóa.

Lọc một dòng theo trace ID có thể bỏ mất stack trace nhiều dòng hoặc log khởi động không có ID. Khi xác định được Pod, lấy lại khoảng log đầy đủ của container đó:

~~~powershell
$podName = 'pricing-example'
$containerName = 'pricing'

kubectl -n $namespace logs $podName -c $containerName --since-time=$fromUtc --timestamps=true --tail=-1
~~~

Chọn container cụ thể để không nhầm log ứng dụng với proxy hoặc sidecar. Các tùy chọn được mô tả trong [kubectl logs](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/).

### Bước 4: Chụp danh tính và trạng thái hiện tại

~~~powershell
$podSnapshot = kubectl -n $namespace get pod $podName -o json |
    ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    throw 'Khong doc duoc Pod; khong tiep tuc voi snapshot khong hop le'
}

$podUid = $podSnapshot.metadata.uid
$observedAt = [DateTimeOffset]::UtcNow.ToString('o')

[pscustomobject]@{
    ObservedAt = $observedAt
    Namespace = $podSnapshot.metadata.namespace
    PodName = $podSnapshot.metadata.name
    PodUid = $podUid
    NodeName = $podSnapshot.spec.nodeName
}

$podSnapshot.status.containerStatuses |
    Select-Object name, ready, restartCount, containerID, state, lastState |
    ConvertTo-Json -Depth 8
~~~

Đây là snapshot lúc chạy lệnh, không phải lịch sử trạng thái ở mọi thời điểm. `restartCount` hiện tại không xác định chính xác giờ từng lần restart. Kiểm tra container tương ứng, `lastState.terminated`, reason, exit code và các timestamp nếu có.

Nếu trace hoặc log ghi một Pod UID khác snapshot hiện tại, dừng việc ghép theo tên. Bạn có thể đang nhìn một Pod mới có cùng tên. Cần tìm lịch sử telemetry của UID cũ.

### Bước 5: Lấy log trước lần restart

Nếu container đã khởi động lại và log trước còn tồn tại:

~~~powershell
kubectl -n $namespace logs $podName -c $containerName --previous --since-time=$fromUtc --timestamps=true --tail=-1
~~~

`--previous` nhắm đến instance container trước đó trong cùng Pod, không phải Pod trước của Deployment. Nó không phải kho lịch sử của mọi lần restart.

Log có thể đã rotate hoặc bị mất khi vòng đời workload kết thúc. Muốn điều tra sau khi Pod bị thay thế, cần pipeline lưu log ngoài Pod. Giới hạn của log trên node được trình bày trong [Kubernetes Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/).

### Bước 6: Tìm Event của đúng Pod UID

Với selector theo schema core/v1:

~~~powershell
kubectl -n $namespace get events --field-selector "involvedObject.uid=$podUid" -o json
~~~

Kiểm tra API version trả về. Nếu chủ động truy vấn `events.k8s.io/v1`, đọc các tham chiếu `regarding` và selector được API đó hỗ trợ; không giả định tên trường giống core/v1.

Đọc các mốc quan sát và series trong JSON. Có thể mở rộng sang ReplicaSet, Deployment hoặc node liên quan khi dữ liệu cho thấy cần thiết. Event của node không tự chứng minh mọi Pod trên node đều chịu cùng một lỗi.

Nếu không có quyền đọc Event, báo rõ “không có dữ liệu do quyền truy cập”, không báo “không có Event”. Tương tự, không nâng quyền ServiceAccount ứng dụng chỉ để người vận hành xem được toàn bộ cluster.

### Bước 7: Ghép timeline và đánh dấu mức chắc chắn

Tạo bảng gồm thời gian UTC, nguồn, định danh đối tượng, quan sát và suy luận. Giữ nguyên timestamp gốc và chỉ chuẩn hóa múi giờ để trình bày.

Không sửa log thiếu field bằng cách tự suy ra trace ID hoặc Pod UID từ dòng ở gần. Nếu phải nối bằng thời gian và IP, ghi rõ đó là suy luận và nêu độ chắc chắn.

## 8. Ví dụ điều tra: container restart trong lúc gọi downstream

Giả sử một hệ thống dùng DiscoveryClient và Spring Cloud LoadBalancer để gọi trực tiếp instance `pricing`. Đội dự án có thêm log lựa chọn đích, nối được IP với Pod UID ở thời điểm gọi. Bảng sau là dữ liệu giả định cho bài học, không phải đầu ra mặc định của framework:

| UTC | Nguồn | Quan sát |
| --- | --- | --- |
| 03:15:00.000 | Trace orders | Client span bắt đầu gọi pricing |
| 03:15:00.010 | Log chọn đích | Đích là IP 10.42.3.17, thuộc Pod UID U ở thời điểm đó |
| 03:15:00.210 | Trạng thái container được thu thập sau đó | Container trong Pod UID U có lần kết thúc với reason OOMKilled và finishedAt quanh mốc này |
| 03:15:00.240 | Trace/log orders | Lời gọi đến đích gặp connection reset |
| 03:15:00.300 | Phản hồi ứng dụng | Người dùng nhận lỗi 5xx |
| 03:15:02.000 | Event nếu reporter phát và hệ thống còn lưu | Có tín hiệu liên quan đến tình trạng probe hoặc việc chờ restart |
| 03:15:03.000 | Log khởi động | Tiến trình pricing mới bắt đầu trong cùng Pod UID U |

Các mốc từ nhiều nguồn có thể lệch do đồng hồ và thời điểm thu thập. Không dùng độ chính xác hiển thị tới mili giây để ngầm khẳng định đồng hồ mọi node chính xác tới mili giây.

Có thể kết luận có căn cứ:

- Lỗi request xảy ra ở lời gọi downstream.
- Đích đã được nối với Pod UID U bằng bằng chứng tại thời điểm đó.
- Container của Pod U đã bị kết thúc với reason `OOMKilled` trong khoảng liên quan.
- Restart tạo ra tiến trình mới dù Pod UID vẫn như cũ.

Chưa đủ căn cứ để kết luận:

- Đó là lỗi rò rỉ heap Java cụ thể nào.
- Một thay đổi ConfigMap trước đó là nguyên nhân làm tăng bộ nhớ.
- Mọi lỗi 5xx trong cùng phút đều do Pod này.
- Tất cả client đã nhìn thấy cùng một tập endpoint ở cùng thời điểm.

Cần thêm bằng chứng như memory metrics, giới hạn container, native memory, tải và hồ sơ bộ nhớ để giải thích vì sao OOM xảy ra. Exit code 137 riêng lẻ không đủ để gán nguyên nhân OOM; ở đây reason của trạng thái container là dữ liệu bổ sung quan trọng.

Nếu không có log ánh xạ đích hoặc server span có Pod UID, việc nối client span với Pod U chỉ bằng “IP hiện tại trùng nhau” là yếu hơn. IP đó có thể đã được tái sử dụng hoặc chỉ là IP của Service. Hãy ghi rõ thiếu bằng chứng thay vì hoàn thiện câu chuyện bằng suy đoán.

Kubernetes Event trong tình huống này là dữ liệu hỗ trợ. Nguyên nhân kết thúc container cần đối chiếu trạng thái và telemetry tương ứng, không bắt buộc phải có một Event mang tên `OOMKilled`.

## 9. Đối chiếu các tính năng Spring Cloud Kubernetes

| Thành phần đang dùng | Bằng chứng nên nối | Kết luận cần tránh |
| --- | --- | --- |
| DiscoveryClient | Log đồng bộ/discovery, namespace, loại endpoint và tập instance tại thời điểm lỗi | “Service tồn tại nên discovery chắc chắn đúng” |
| Spring Cloud LoadBalancer | Client span, lần chọn đích, retry và dữ liệu instance | “Mỗi span tương ứng đúng một lần chọn instance” khi có retry hoặc instrumentation khác |
| ConfigMap/Secret | Thao tác đọc, kết quả API, revision công khai, bước áp dụng | “API đọc thành công nên nghiệp vụ đang dùng giá trị mới” |
| Configuration Watcher | Nguồn thay đổi, ứng dụng đích, kết quả thông báo và log refresh | “Watcher nhận sự kiện nên mọi replica đã cập nhật” |
| Actuator và Pod health | Kết quả health group, probe, trạng thái container và trace nghiệp vụ | “Pod Ready nên mọi request phải thành công” |

Configuration Watcher có thể gửi thông báo refresh qua HTTP hoặc qua Bus. Nó là một tiến trình có log, đường kết nối và danh tính riêng; xem [Configuration Watcher 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Một thay đổi cấu hình lúc 03:14 có thể ảnh hưởng hàng nghìn request sau đó. Không gán tất cả request ấy vào cùng trace của Watcher. Dùng revision và danh tính instance để nối thay đổi với hành vi, còn trace giữ quan hệ của từng luồng thực thi.

Nếu HTTP refresh đã được instrument và có propagation, lời gọi Watcher đến ứng dụng có thể có trace của riêng luồng refresh. Việc đó không làm các request nghiệp vụ tương lai tự trở thành con của luồng đó. Không mặc định Watcher có sẵn toàn bộ instrumentation cần cho cách nối này.

Với lỗi 403 khi đọc tài nguyên, ghi resource, verb, namespace, kết quả và danh tính liên quan. Đừng chờ một Kubernetes Event để xác nhận mọi lỗi RBAC. API audit log, nếu cluster có cấu hình và bạn được phép đọc, là nguồn khác với Event và có mục đích riêng.

Không log token ServiceAccount, header Authorization, giá trị Secret hoặc toàn bộ cấu hình chỉ để nối request. Revision công khai và metadata nguồn thường đủ cho bước đối chiếu ban đầu.

## 10. Bài thực hành: lỗi HTTP có trace nhưng không có Event tương ứng

Mục tiêu là kiểm chứng rằng ba nguồn dữ liệu bổ sung cho nhau và không bắt buộc cùng có bản ghi cho một lỗi.

### Bước 1: Tạo đường quan sát đến orders

Chọn một Pod `orders` đang chạy trong lab, ghi Pod name và UID. Mở port-forward trong một terminal riêng:

~~~powershell
kubectl -n obs-lab port-forward pod/orders-example 18080:8080
~~~

Thay `orders-example` bằng tên thực tế. Port-forward vào một Pod giúp cố định instance vào; nó không mô phỏng đầy đủ đường Ingress hoặc load balancer bên ngoài.

### Bước 2: Gửi một request có trace context hợp lệ

Nếu hai ứng dụng được cấu hình nhận W3C Trace Context, có thể dùng request lab sau:

~~~powershell
curl.exe --include --header "traceparent: 00-9a4e5b2f1c8d4076ab93d581c27e604f-1000000000000001-01" "http://127.0.0.1:18080/demo/quote?fail=true"
~~~

Header minh họa gồm version, trace ID, parent span ID và trace flags theo [W3C Trace Context](https://www.w3.org/TR/trace-context/). Đây là ID cố định để tìm một lượt thử; dùng ID mới cho các lượt sau, không tái dùng một ID cho mọi request.

Trace context do client gửi không phải chứng cứ xác thực người dùng. Biên tiếp nhận cần có chính sách tin cậy phù hợp; không dùng trace ID làm khóa quyền truy cập.

Nếu propagation format của hệ thống là format khác hoặc gateway có chính sách tạo trace mới, không mặc định backend sẽ giữ ID trong ví dụ. Kiểm tra ID thực tế trong log ở điểm vào trước.

### Bước 3: Đối chiếu trace và log

Với đúng mã mẫu và đường gọi hoạt động:

- `pricing` chủ động trả 503 cho `fail=true`.
- `orders` ghi `pricing_call_failed` với downstream status 503 và trả 502.
- Trace có cạnh đi từ `orders` đến `pricing` nếu instrumentation và export hoạt động.
- Log của hai dịch vụ mang cùng trace ID ở scope tương ứng, còn span ID có thể khác.

Tìm log của request trên từng dịch vụ và đối chiếu Pod UID. Nếu trace có dữ liệu resource Kubernetes, kiểm tra nó có khớp metadata log không.

Nếu không tìm thấy trace, kiểm tra sampling, propagation, exporter và cửa sổ thời gian. Không đổi ngay kết luận thành “request chưa bao giờ chạy”.

### Bước 4: Đọc Event và trạng thái Pod

Dùng UID của các Pod tham gia để đọc Event và trạng thái container. Bạn có thể không thấy Event lỗi nào do lỗi HTTP này: ứng dụng chủ động trả 503 không bắt buộc gây restart, probe thất bại hoặc tạo Event Kubernetes.

Đừng tạo một Event giả chỉ để đủ ba loại dữ liệu. Báo cáo trung thực: “Đã thấy lỗi HTTP trong trace và log; không có Event liên quan trong dữ liệu đã thu thập.”

### Bước 5: So sánh với một request thành công

Gửi `fail=false` với trace ID mới. So sánh cùng cạnh HTTP, log và instance. Request này giúp kiểm tra khả năng quan sát của đường gọi, nhưng không chứng minh mọi đường lỗi mạng hoặc mọi replica đều được instrument đầy đủ.

Không cần restart Pod hoặc đổi RBAC trong bài thực hành này. Tình huống restart ở phần trước dùng để luyện đọc bằng chứng đã thu thập.

## 11. Khi dữ liệu bị thiếu hoặc mâu thuẫn

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Log có trace ID nhưng backend không có trace | Sampling, span chưa hoàn tất, exporter lỗi, collector drop hoặc thời gian lưu |
| Hai service có hai trace ID khác nhau | Propagation format, client builder, proxy/gateway, context bị mất hoặc luồng bất đồng bộ |
| Trace chỉ có client span, không có server span | Kết nối chưa đến server, thiếu instrumentation, sampling khác hoặc server chưa xuất span |
| Log có cùng tên Pod nhưng UID khác | Đã thay thế Pod; tách hai vòng đời |
| Pod UID giống nhau nhưng log startup lặp lại | Kiểm tra restart count và container ID |
| Event xuất hiện trước hoặc sau trace theo thứ tự khó hiểu | Clock skew, series gộp, mốc quan sát khác nhau hoặc collector trễ |
| `kubectl logs` không có dữ liệu mà kho log vẫn có | Pod đã bị xóa, log đã rotate hoặc phạm vi truy vấn khác |
| Không có Event trong API nhưng kho Event có bản ghi cũ | Khác thời gian lưu hoặc bản ghi đã được lưu ngoài API |

Một server span bị thiếu không tự chứng minh server không nhận request. Có thể tiến trình chết trước khi xuất span. Ngược lại, log “bắt đầu xử lý” cũng không chứng minh request đã hoàn tất.

Trace được lấy mẫu là một tập quan sát, không phải toàn bộ lưu lượng. Khi nghi ngờ mất dữ liệu, xem cả tỷ lệ thu thập và sức khỏe pipeline. Việc tăng sampling cũng không sửa được lỗi mất context hay enrichment sai.

Nếu dùng OpenTelemetry Collector để bổ sung resource attributes, kiểm tra quy tắc liên kết dữ liệu với Pod và quyền metadata. Collector có thể biến đổi hoặc bổ sung telemetry nhưng không tự chứng minh quan hệ nhân quả giữa Event và span. Xem [Transforming telemetry](https://opentelemetry.io/docs/collector/transforming-telemetry/).

Các bản ghi đến từ node hoặc proxy cần được gắn đúng nguồn. Gán tất cả telemetry đi qua một gateway về Pod của gateway sẽ phá hỏng khả năng nối với Pod ứng dụng.

## 12. Viết kết luận có thể kiểm chứng

Một bản kết luận ngắn nên tách quan sát, suy luận và điểm còn thiếu:

~~~text
Triệu chứng:
  Một nhóm request orders trả 5xx trong khoảng UTC đã xác định.

Định danh:
  Cluster, namespace, trace ID, service, Pod UID và container liên quan.

Đã xác nhận:
  Client span đến pricing bị lỗi.
  Bằng chứng chọn đích nối lời gọi với Pod UID cụ thể.
  Trạng thái container cho thấy lần kết thúc có reason OOMKilled.

Suy luận:
  Lần kết thúc container có khả năng liên quan trực tiếp đến lỗi lời gọi.

Chưa xác định:
  Nguyên nhân khiến bộ nhớ vượt giới hạn.
  Phạm vi toàn bộ request bị ảnh hưởng.

Bước tiếp theo:
  Đối chiếu số đo bộ nhớ, giới hạn, tải và dữ liệu chẩn đoán bộ nhớ.
~~~

Chỉ dùng “đã xác nhận” cho điều nguồn dữ liệu thực sự chứng minh. Nếu thời gian giữa hai nguồn gần hơn sai số đồng hồ, đừng khẳng định thứ tự chính xác chỉ bằng timestamp.

Một kết quả điều tra tốt không cần ép đủ cả ba loại bản ghi. Nó cần nối đúng request với đúng instance và vòng đời, giải thích giới hạn của từng nguồn, rồi dùng các bằng chứng độc lập để tăng hoặc giảm độ tin cậy của giả thuyết. Đó là cách biến log, Kubernetes Event và distributed trace thành công cụ vận hành hữu ích cho các ứng dụng Spring Cloud Kubernetes.
