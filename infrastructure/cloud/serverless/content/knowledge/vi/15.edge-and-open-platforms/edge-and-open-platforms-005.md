# Mô hình serving và eventing trong Knative

Knative là một nền tảng mã nguồn mở xây dựng trên Kubernetes để triển khai workload theo mô hình serverless. Knative cung cấp hai nhóm khả năng thường dùng: **Serving** để chạy ứng dụng nhận request và tự động mở rộng theo lưu lượng, **Eventing** để kết nối nguồn phát sự kiện với các dịch vụ tiêu thụ sự kiện.

Với Java, có thể đóng gói ứng dụng thành container image rồi triển khai thành Knative Service. Khi cần xử lý bất đồng bộ, một nguồn sự kiện có thể gửi CloudEvent đến Broker; Trigger lọc sự kiện và chuyển đến Java service phù hợp. Cách tiếp cận này tách vòng đời compute khỏi vòng đời dữ liệu và cho phép scale theo nhu cầu.

Bài học trình bày mô hình Serving và Eventing, cách chúng phối hợp, cách đóng gói Java container, cùng các vấn đề về autoscaling, cold start, traffic splitting, delivery, retry và idempotency.

## 1. Serving và Eventing giải quyết hai bài toán khác nhau

| Thành phần | Bài toán chính | Đầu vào | Kết quả |
|---|---|---|---|
| Knative Serving | Chạy ứng dụng nhận request | HTTP request hoặc gRPC tùy cấu hình | HTTP/gRPC response |
| Knative Eventing | Định tuyến và phân phối sự kiện giữa các thành phần | CloudEvent từ source hoặc producer | Event được gửi đến subscriber/sink |
| Kubernetes | Quản lý hạ tầng container nền | Pod, Service, Deployment và tài nguyên cluster | Scheduling, networking, storage và lifecycle |

Serving phù hợp với API, webhook receiver, web backend hoặc dịch vụ HTTP. Eventing phù hợp với xử lý bất đồng bộ, tích hợp event source, fan-out và các pipeline phản ứng theo sự kiện.

Hai thành phần có thể kết hợp. Ví dụ, Java API chạy trên Knative Serving nhận yêu cầu tạo đơn hàng, ghi đơn vào database rồi phát một CloudEvent vào Broker. Một Trigger chuyển event đến Java worker khác. Worker xử lý nghiệp vụ rồi phát event tiếp theo. API không cần gọi trực tiếp từng worker và không phải giữ kết nối trong suốt quá trình xử lý.

~~~mermaid
flowchart LR
    C["HTTP client"] --> S["Knative Serving: Java API"]
    S --> D["Database"]
    S --> B["Knative Eventing Broker"]
    B --> T["Trigger lọc CloudEvent"]
    T --> W["Knative Serving: Java worker"]
    W --> O["Database / dịch vụ ngoài"]
    W --> B
~~~

Serving và Eventing không thay thế Kubernetes. Chúng bổ sung abstraction serverless lên Kubernetes, trong khi cluster vẫn chịu trách nhiệm về node, network, storage, policy và năng lực tài nguyên.

## 2. Kiến trúc Knative Serving

Knative Serving cung cấp một API để triển khai và quản lý ứng dụng container. Tài nguyên chính là Knative Service. Khi cập nhật cấu hình hoặc image, Serving tạo Revision mới và quản lý Route để đưa traffic đến revision được chọn.

Bốn khái niệm cần phân biệt:

- **Service:** tài nguyên cấp cao đại diện cho ứng dụng được triển khai.
- **Configuration:** mô tả trạng thái mong muốn của pod template và cấu hình runtime.
- **Revision:** snapshot bất biến của một cấu hình triển khai. Thay đổi image, env hoặc cấu hình tạo revision mới.
- **Route:** ánh xạ request đến một hoặc nhiều revision, có thể phân chia traffic theo tỷ lệ.

Knative Service không phải Kubernetes Service. Knative Service là custom resource do Knative Serving cung cấp; Kubernetes Service là tài nguyên networking có mục đích khác.

~~~mermaid
flowchart TD
    K["Knative Service"] --> C["Configuration"]
    K --> R["Route"]
    C --> V1["Revision 1"]
    C --> V2["Revision 2"]
    R --> V1
    R --> V2
    V1 --> P1["Pod / container"]
    V2 --> P2["Pod / container"]
~~~

Revision bất biến giúp có thể triển khai phiên bản mới, thử traffic nhỏ, quan sát rồi tăng dần traffic. Nếu có lỗi, Route có thể được điều chỉnh về revision trước đó, miễn là revision đó còn được giữ và tương thích với dữ liệu bên ngoài.

### 2.1. Đường đi của HTTP request

Một request đến Knative Service thường đi qua ingress/gateway của cluster, sau đó được định tuyến đến revision và pod tương ứng. Knative quản lý số pod theo nhu cầu. Một số thành phần nội bộ như Activator và queue-proxy hỗ trợ scale-to-zero, định tuyến, giới hạn concurrency và thu thập metric.

Ở mức khái quát:

1. Client gửi HTTP request đến domain của Knative Service.
2. Ingress hoặc gateway định tuyến request đến revision.
3. Nếu revision đã có pod sẵn sàng, request được chuyển đến pod.
4. Nếu service đã scale về zero, Activator có thể nhận request, kích hoạt scale-up và giữ request trong lúc pod khởi động.
5. Container nhận request và trả response.
6. Autoscaler quan sát lưu lượng và điều chỉnh số replica.

Chi tiết ingress, gateway, TLS và network path phụ thuộc cách cài đặt Knative và cấu hình cluster. Không nên giả định mọi cluster đều dùng cùng một ingress controller.

## 3. Triển khai Java Service trên Knative Serving

Một Java web application cần chạy trong container và lắng nghe trên interface cùng port mà nền tảng cung cấp. Knative Serving thường truyền biến môi trường PORT cho container. Ứng dụng nên bind vào 0.0.0.0 thay vì chỉ localhost để ingress trong pod có thể kết nối.

Ví dụ manifest Knative Service:

~~~yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
  namespace: apps
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/min-scale: "0"
        autoscaling.knative.dev/max-scale: "20"
    spec:
      containerConcurrency: 20
      containers:
        - image: registry.example.com/orders-api:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: APP_MODE
              value: "production"
~~~

Đây là manifest minh họa. Image registry, namespace, port và autoscaling annotation cần phù hợp với cluster. Không phải mọi annotation hoặc tính năng autoscaling đều có cùng hành vi ở mọi phiên bản Knative; kiểm tra API và cấu hình autoscaler của nền tảng đang triển khai.

Với Spring Boot, có thể cấu hình server port bằng biến môi trường PORT. Ví dụ trong application properties:

~~~properties
server.port=${PORT:8080}
~~~

Trong cấu hình production, đặt giá trị port theo biến PORT mà runtime cung cấp hoặc đọc biến này trong cấu hình ứng dụng. Container image có thể dùng JRE phù hợp với phiên bản Java:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/orders-api.jar /app/app.jar
ENV PORT=8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/app/app.jar"]
~~~

Knative yêu cầu container sẵn sàng phục vụ trong thời hạn startup được cấu hình. Ứng dụng cần khởi động nhanh, đóng kết nối đúng cách và xử lý tín hiệu dừng. Nếu ứng dụng khởi tạo database hoặc tải model lớn trước khi sẵn sàng, cần tính thời gian đó vào startup probe và cold start.

### 3.1. Container contract

Ứng dụng Java trên Knative Serving cần tuân thủ một số nguyên tắc:

- Lắng nghe trên port được truyền qua biến môi trường PORT hoặc port được cấu hình tương ứng.
- Bind vào địa chỉ có thể nhận traffic từ ingress trong pod.
- Không giả định container có IP cố định hoặc sẽ tồn tại lâu dài.
- Ghi log ra stdout/stderr để nền tảng thu thập.
- Xử lý SIGTERM và đóng tài nguyên trong khoảng thời gian graceful shutdown.
- Không lưu trạng thái nghiệp vụ duy nhất trong filesystem container.
- Có readiness/startup behavior phản ánh đúng khả năng phục vụ.

Nếu ứng dụng dùng background thread, thread đó không được coi là nơi lưu công việc bền vững. Khi pod scale down hoặc bị thay thế, process có thể kết thúc. Công việc cần hoàn tất phải được xử lý trong request có giới hạn hoặc bàn giao cho queue/event/workflow có trạng thái bền vững.

## 4. Autoscaling và scale-to-zero

Một đặc tính nổi bật của Knative Serving là autoscaling theo tải. Khi request tăng, autoscaler tăng số pod; khi tải giảm, số pod có thể giảm. Với scale-to-zero, revision có thể không giữ pod nào khi không có request trong một khoảng thời gian.

Các khái niệm quan trọng:

- **Target concurrency:** mức request đồng thời mục tiêu mà autoscaler dùng để điều chỉnh số replica.
- **Container concurrency:** giới hạn số request đồng thời mà một container nhận.
- **Minimum scale:** số replica tối thiểu cần giữ.
- **Maximum scale:** giới hạn số replica tối đa.
- **Scale-to-zero:** cho phép giảm về zero khi không có tải.
- **Scale-up/down behavior:** thời gian và cách tăng/giảm replica theo metric.

Autoscaling không có nghĩa mỗi request luôn tạo một container mới. Một pod có thể xử lý nhiều request đồng thời nếu container concurrency cho phép. Số replica được điều chỉnh dựa trên metric và cấu hình của autoscaler.

### 4.1. KPA và HPA

Knative Serving thường dùng Knative Pod Autoscaler (KPA) để điều chỉnh số pod dựa trên metric request/concurrency. Tùy môi trường, có thể cấu hình Horizontal Pod Autoscaler (HPA) để scale dựa trên CPU hoặc metric Kubernetes.

| Tiêu chí | KPA | HPA |
|---|---|---|
| Metric thường dùng | Request concurrency hoặc request rate tùy cấu hình | CPU, memory hoặc custom/external metrics theo cấu hình |
| Tích hợp với Knative request path | Có hiểu biết về traffic của Knative | Dựa vào metric Kubernetes được cấu hình |
| Scale-to-zero | Hỗ trợ trong mô hình Knative phù hợp | HPA Kubernetes truyền thống không tự scale về zero |
| Phù hợp | HTTP workload biến động, cần scale theo request | Workload cần scale theo CPU hoặc metric tài nguyên |

Khả năng cụ thể phụ thuộc phiên bản Knative, autoscaler class và cấu hình cluster. Nếu dùng HPA, hãy xác minh scale-to-zero có được hỗ trợ qua thành phần bổ sung hay không; không mặc định HPA truyền thống tự xử lý scale-to-zero.

### 4.2. Chọn concurrency phù hợp

Nếu container concurrency quá cao, một pod có thể nhận nhiều request hơn khả năng CPU, heap hoặc connection pool. Điều này làm tăng latency và timeout. Nếu đặt quá thấp, hệ thống cần nhiều pod hơn, có thể tăng chi phí khởi tạo và overhead.

Hãy đo:

- Thời gian xử lý p50/p95/p99.
- CPU và memory theo số request đồng thời.
- Số connection đến database.
- Tỷ lệ timeout và lỗi downstream.
- Throughput ổn định trên mỗi pod.

Với Java, giới hạn concurrency cần tương thích với thread pool của web server, connection pool và giới hạn tài nguyên. Không nên đặt containerConcurrency cao hơn khả năng xử lý thực tế chỉ để giảm số pod.

### 4.3. Min scale và max scale

Min scale bằng zero giúp giảm compute khi không có traffic, nhưng request đầu tiên sau thời gian idle có thể chịu cold start. Min scale lớn hơn zero giúp giữ một số pod ấm, đổi lại có chi phí compute ngay cả khi ít request.

Max scale bảo vệ cluster và dependency khỏi scale-out không giới hạn. Tuy nhiên, khi đạt max scale, request có thể phải chờ hoặc bị từ chối tùy ingress và queueing behavior. Hãy kết hợp max scale với rate limit, timeout và backpressure ở các dịch vụ phụ thuộc.

Không đặt max scale chỉ dựa trên năng lực cluster. Cần tính giới hạn của database, message broker, API đối tác và quota cloud.

## 5. Cold start và tối ưu Java trên Knative

Cold start xảy ra khi một revision cần khởi tạo pod mới, bao gồm scheduling, tải image nếu chưa có, khởi chạy container và khởi tạo ứng dụng Java.

Các yếu tố có thể làm cold start tăng:

- Image lớn hoặc nhiều layer.
- Node chưa cache image.
- JVM khởi tạo và nạp nhiều class.
- Framework khởi động chậm.
- Reflection/classpath scanning nhiều.
- Kết nối database, DNS hoặc TLS handshake.
- Startup logic đọc cấu hình/secret hoặc tải dữ liệu lớn.

Các cách giảm cold start:

1. Dùng multi-stage build và runtime image nhỏ.
2. Giảm dependency và tránh classpath scanning không cần thiết.
3. Lazy-load thành phần không cần cho request đầu tiên.
4. Dùng framework có startup time phù hợp.
5. Đo và tối ưu kết nối dịch vụ ngoài.
6. Chọn min scale > 0 nếu SLA yêu cầu độ trễ thấp và chi phí chấp nhận được.
7. Cân nhắc JVM CDS hoặc native executable nếu benchmark cho thấy có lợi.
8. Tối ưu image layer để giảm thời gian tải và giải nén.

Native executable có thể giảm thời gian khởi động JVM, nhưng không loại bỏ thời gian scheduling, image pull, kết nối mạng hoặc initialization nghiệp vụ. Hãy đo toàn bộ thời gian từ request đến response thay vì chỉ đo startup process.

## 6. Revision và traffic management

Mỗi thay đổi cấu hình triển khai tạo Revision mới. Route có thể chuyển toàn bộ traffic sang revision mới hoặc chia traffic giữa nhiều revision.

Ví dụ cấu hình Route để chia 10% traffic cho revision mới và 90% cho revision cũ:

~~~yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
spec:
  traffic:
    - revisionName: orders-api-00001
      percent: 90
    - latestRevision: true
      percent: 10
~~~

Tên revision chỉ là ví dụ. Khi triển khai thực tế, cần kiểm tra revision đã tồn tại và cách Knative sinh tên. Có thể dùng tag để tạo URL riêng cho revision phục vụ kiểm thử.

Traffic splitting hữu ích cho:

- Canary release.
- A/B testing.
- So sánh latency và error rate giữa hai bản.
- Chuyển traffic dần sau khi xác minh.
- Rollback nhanh về revision cũ.

Một rollout an toàn nên tăng tỷ lệ traffic theo từng bước, theo dõi metric và đặt điều kiện rollback. Không chỉ dựa trên HTTP 200; cần theo dõi p95 latency, lỗi nghiệp vụ, dependency error và resource saturation.

### 6.1. Tương thích schema và dữ liệu

Revision cũ và mới có thể cùng nhận traffic trong một thời gian. Nếu hai phiên bản dùng schema database không tương thích, canary có thể gây lỗi. Hãy triển khai thay đổi schema theo kiểu expand-and-contract:

1. Thêm field hoặc bảng mới nhưng vẫn giữ tương thích với phiên bản cũ.
2. Triển khai revision mới có thể đọc/ghi theo schema chuyển tiếp.
3. Chuyển traffic và xác minh.
4. Chỉ xóa cấu trúc cũ sau khi không còn revision hoặc consumer cần nó.

Không giả định rollback container image có thể rollback side effect hoặc schema đã ghi vào database.

## 7. Health check, startup và graceful shutdown

Knative Serving cần biết container đã khởi động và sẵn sàng nhận request. Ứng dụng Java nên cung cấp health endpoint hoặc cấu hình probe phù hợp.

- **Startup probe:** cho ứng dụng thời gian khởi tạo; tránh readiness/liveness kiểm tra quá sớm.
- **Readiness probe:** báo ứng dụng có thể nhận request hay chưa.
- **Liveness probe:** phát hiện process bị kẹt và cần khởi động lại, nhưng cấu hình quá nhạy có thể gây restart loop.

Không dùng một health endpoint kiểm tra tất cả dependency theo cách gây lỗi dây chuyền. Nếu database tạm thời chậm, liveness probe liên tục fail có thể khiến toàn bộ pod restart và làm tình hình xấu hơn. Phân biệt process còn sống với ứng dụng sẵn sàng nhận một loại request cụ thể.

Khi pod bị scale down, ứng dụng cần dừng nhận công việc mới và hoàn tất request đang xử lý trong grace period. Với request dài, hãy đặt timeout phù hợp và dùng cơ chế async job nếu cần thời gian vượt quá vòng đời request.

## 8. Kiến trúc Knative Eventing

Knative Eventing kết nối event producer với event consumer bằng một giao thức sự kiện chung. CloudEvents là định dạng thường được dùng để biểu diễn event theo cách có thể trao đổi giữa nhiều framework và dịch vụ.

Các khái niệm chính:

- **Event source:** thành phần tạo event, ví dụ PingSource, nguồn Kubernetes API hoặc adapter cho message system.
- **Broker:** điểm nhận và phân phối event, tách producer khỏi consumer.
- **Trigger:** đăng ký bộ lọc event và subscriber nhận các event phù hợp.
- **Sink:** đích nhận event, có thể là Knative Service, Broker hoặc URI được hỗ trợ.
- **Channel/Subscription:** mô hình phân phối event theo channel; API và implementation cụ thể phụ thuộc extension/transport được cài đặt.

Broker/Trigger là abstraction phổ biến để định tuyến event. Channel/Subscription vẫn xuất hiện trong một số mô hình hoặc hệ thống mở rộng. Không nên giả định mọi cluster cài Knative Eventing đều có cùng broker, channel type hoặc source adapter.

~~~mermaid
flowchart LR
    S1["PingSource / API Source"] --> B["Broker"]
    S2["Producer / Adapter"] --> B
    B --> T1["Trigger: order.created"]
    B --> T2["Trigger: payment.failed"]
    T1 --> W1["Knative Service: order-worker"]
    T2 --> W2["Knative Service: alert-worker"]
~~~

Broker giúp producer không cần biết cụ thể service nào đang nhận event. Trigger định nghĩa subscriber và filter. Khi thêm một consumer mới, có thể thêm Trigger mà không cần thay đổi producer nếu hợp đồng event vẫn tương thích.

## 9. CloudEvents và hợp đồng event

CloudEvents định nghĩa các thuộc tính chuẩn để mô tả event. Một CloudEvent thường có:

| Thuộc tính | Ý nghĩa |
|---|---|
| specversion | Phiên bản CloudEvents |
| id | Định danh event trong phạm vi source |
| source | Nguồn phát event |
| type | Loại event |
| subject | Đối tượng mà event liên quan, nếu có |
| time | Thời điểm xảy ra event |
| datacontenttype | Kiểu nội dung của data |
| data | Payload nghiệp vụ |

Ví dụ CloudEvent JSON dạng structured:

~~~json
{
  "specversion": "1.0",
  "id": "evt-91f2",
  "source": "/orders/service",
  "type": "com.example.order.created",
  "subject": "orders/order-1042",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "order-1042",
    "customerId": "customer-42",
    "total": 125.50
  }
}
~~~

Cặp source và id là cơ sở tốt để nhận diện một event duy nhất khi chống trùng. Không chỉ dùng id nếu nhiều source có thể phát cùng một giá trị id.

CloudEvents có thể được truyền theo structured mode hoặc binary mode. Với structured mode, metadata và data nằm trong body JSON. Với binary mode, thuộc tính context thường được truyền qua HTTP header có tiền tố ce-, còn body chứa data. Producer và consumer cần tuân theo cùng binding và content type.

Event contract nên version hóa theo type hoặc schema version. Không đổi ý nghĩa của một field đang được consumer sử dụng mà không có chiến lược tương thích. Event nên mô tả sự kiện đã xảy ra, ví dụ order.created, thay vì chỉ gửi một lệnh mơ hồ như process-order nếu consumer cần biết lịch sử nghiệp vụ.

## 10. Tạo Broker và Trigger

Một Broker là điểm nhận event trong namespace. Ví dụ manifest tạo Broker:

~~~yaml
apiVersion: eventing.knative.dev/v1
kind: Broker
metadata:
  name: default
  namespace: apps
~~~

Trigger đăng ký nhận các event từ Broker theo filter. Ví dụ, chỉ chuyển event có type là com.example.order.created đến một Knative Service:

~~~yaml
apiVersion: eventing.knative.dev/v1
kind: Trigger
metadata:
  name: order-created
  namespace: apps
spec:
  broker: default
  filter:
    attributes:
      type: com.example.order.created
  subscriber:
    ref:
      apiVersion: serving.knative.dev/v1
      kind: Service
      name: order-worker
~~~

Manifest là ví dụ theo API Knative Eventing v1. Cần cài Broker implementation và cấu hình namespace/permissions trước khi tạo resource. Broker mặc định, khả năng lưu trữ và semantics delivery phụ thuộc implementation được cluster cài đặt.

Có thể tạo nhiều Trigger trên cùng Broker để fan-out một event đến nhiều subscriber. Nếu một Trigger lọc event theo type hoặc subject, hãy đảm bảo producer gửi đúng thuộc tính và consumer kiểm tra schema trước khi xử lý.

## 11. Event source và sink

Source là adapter chuyển tín hiệu từ một hệ thống khác thành CloudEvent và gửi đến sink. Một số nguồn có thể đến từ Kubernetes API, lịch định kỳ hoặc hệ thống message. Các source cụ thể thường được cài dưới dạng extension và có API riêng.

Ví dụ PingSource phát event định kỳ vào Broker:

~~~yaml
apiVersion: sources.knative.dev/v1
kind: PingSource
metadata:
  name: periodic-cleanup
  namespace: apps
spec:
  schedule: "*/5 * * * *"
  contentType: application/json
  data: '{"task":"cleanup"}'
  sink:
    ref:
      apiVersion: eventing.knative.dev/v1
      kind: Broker
      name: default
~~~

Ví dụ trên phát event mỗi năm phút theo lịch của source. Cú pháp schedule, timezone và hành vi khi missed schedule phụ thuộc source implementation; hãy kiểm tra tài liệu extension. Không dùng PingSource làm thay thế cho một scheduler có semantics nghiệp vụ phức tạp nếu cần kiểm soát catch-up, timezone hoặc lịch chạy trùng.

Sink là đích nhận event. Sink có thể là Knative Service, Broker hoặc URI tùy cấu hình và API hỗ trợ. Khi gửi event đến service, producer không cần biết service đang chạy bao nhiêu replica. Serving có thể scale subscriber theo traffic nhận được.

## 12. Xử lý CloudEvent trong Java

Java consumer có thể dùng CloudEvents Java SDK hoặc adapter/framework để parse event từ HTTP binding. Sau khi nhận CloudEvent, ứng dụng đọc source, id, type và data, kiểm tra hợp đồng rồi gọi nghiệp vụ.

Ví dụ minh họa phần xử lý event đã được adapter parse thành CloudEvent. Interface EventInbox là kho lưu trạng thái idempotency do ứng dụng triển khai.

~~~java
import io.cloudevents.CloudEvent;
import java.nio.charset.StandardCharsets;

public final class OrderEventHandler {

    private final EventInbox inbox;
    private final OrderService orderService;

    public OrderEventHandler(EventInbox inbox, OrderService orderService) {
        this.inbox = inbox;
        this.orderService = orderService;
    }

    public void handle(CloudEvent event) throws Exception {
        if (!"com.example.order.created".equals(event.getType())) {
            throw new IllegalArgumentException("Unsupported event type");
        }
        if (event.getData() == null) {
            throw new IllegalArgumentException("Event data is required");
        }

        String eventKey = event.getSource() + ":" + event.getId();

        InboxClaim claim = inbox.claim(eventKey);
        if (claim == InboxClaim.ALREADY_PROCESSED) {
            return;
        }
        if (claim == InboxClaim.OWNED_BY_ACTIVE_WORKER) {
            throw new IllegalStateException("Event is already being processed");
        }

        try {
            String json = new String(
                    event.getData().toBytes(),
                    StandardCharsets.UTF_8);

            orderService.handleCreatedOrder(json);
            inbox.markProcessed(eventKey);
        } catch (Exception error) {
            inbox.markRetryableFailure(eventKey, error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

Các kiểu EventInbox, InboxClaim và OrderService là interface nghiệp vụ cần định nghĩa. Claim phải được thực hiện nguyên tử, thường bằng unique key trên source + id và lease/trạng thái xử lý. Khi consumer thất bại tạm thời, trạng thái phải cho phép retry an toàn; không để bản ghi PROCESSING bị giữ vô hạn. Lỗi schema hoặc event type không hỗ trợ là lỗi vĩnh viễn, nên được chuyển sang dead-letter hoặc ghi trạng thái rejected thay vì đánh dấu retryable vô hạn. Nếu event đã PROCESSED, trả thành công để delivery duplicate không tạo side effect lần nữa.

Ví dụ chỉ minh họa phần logic sau khi parse. HTTP adapter cần xử lý CloudEvents binary/structured mode theo binding được sử dụng. Không tự parse header bằng chuỗi thủ công nếu thư viện CloudEvents hoặc framework đã hỗ trợ binding chuẩn.

### 12.1. Ack sau khi đã tiếp nhận bền vững

Nếu consumer nhận event qua HTTP, response 2xx thường báo cho dispatcher rằng event đã được tiếp nhận thành công. Nếu ứng dụng trả 2xx trước khi ghi event hoặc hoàn tất xử lý theo policy, event có thể bị mất khi process chết ngay sau đó.

Có hai cách phổ biến:

- Xử lý đồng bộ và chỉ trả 2xx sau khi side effect đã commit.
- Ghi event vào inbox/queue bền vững, sau đó trả 2xx; worker xử lý tiếp bất đồng bộ.

Cách thứ hai thường phù hợp với workload dài hoặc cần retry độc lập. Trong cả hai trường hợp, duplicate vẫn có thể xảy ra và consumer cần idempotency.

## 13. Delivery, retry và dead-letter

Event delivery trong hệ thống phân tán thường có thể lặp lại. Producer có thể retry khi không nhận phản hồi; Broker hoặc dispatcher có thể giao lại khi subscriber lỗi hoặc timeout. Vì vậy, không thiết kế consumer dựa trên giả định mỗi event chỉ đến một lần.

Knative Eventing hỗ trợ cấu hình delivery behavior ở các thành phần phù hợp, bao gồm retry, backoff và dead-letter sink. Schema và nơi đặt delivery spec phụ thuộc loại resource và phiên bản Eventing. Ví dụ minh họa phần delivery trên Trigger:

~~~yaml
apiVersion: eventing.knative.dev/v1
kind: Trigger
metadata:
  name: order-created
spec:
  broker: default
  filter:
    attributes:
      type: com.example.order.created
  subscriber:
    ref:
      apiVersion: serving.knative.dev/v1
      kind: Service
      name: order-worker
  delivery:
    retry: 5
    backoffPolicy: exponential
    backoffDelay: PT1S
    deadLetterSink:
      ref:
        apiVersion: serving.knative.dev/v1
        kind: Service
        name: event-dead-letter
~~~

Các giá trị chỉ là ví dụ. Hãy xác minh API schema của Knative Eventing version và Broker implementation được cài. Dead-letter sink phải được triển khai, cấp quyền và có quy trình vận hành để xem, sửa hoặc phát lại event lỗi.

Một retry policy cần xác định:

- Lỗi nào được retry.
- Số lần retry tối đa.
- Backoff tuyến tính hay exponential.
- Thời gian chờ tối đa.
- Timeout mỗi lần delivery.
- Dead-letter destination.
- Cách người vận hành xử lý event sau khi vào DLQ.

Không retry vô hạn với event sai schema hoặc lỗi nghiệp vụ vĩnh viễn. Nếu consumer không hỗ trợ event type, có thể ghi nhận lỗi có cấu trúc và chuyển sang DLQ thay vì lặp lại mãi.

### 13.1. At-least-once và idempotency

Nhiều cấu hình event delivery hướng đến at-least-once: hệ thống cố gắng giao event, nhưng consumer có thể nhận nhiều lần. Exact delivery semantics còn phụ thuộc source, broker, channel implementation và cấu hình retry.

Không nên tuyên bố toàn bộ pipeline có exactly-once chỉ vì Broker hoặc transport có một cơ chế deduplication. Side effect trong database, payment provider hoặc API ngoài có thể không nằm trong cùng transaction.

Hãy dùng idempotency key ổn định, thường dựa trên source + event id. Lưu trạng thái event cùng kết quả nghiệp vụ bằng transaction hoặc inbox/outbox pattern. Nếu consumer gọi API ngoài, truyền idempotency key cho API đó nếu được hỗ trợ.

## 14. Ordering, fan-out và backpressure

Không phải mọi broker hoặc channel đều đảm bảo thứ tự event. Nhiều subscriber có thể xử lý đồng thời và hoàn tất theo thứ tự khác với lúc phát. Nếu nghiệp vụ cần thứ tự, hãy xác định partition key, sequence number hoặc version của aggregate.

Ví dụ, event order.updated version 8 đến trước version 7. Consumer có thể bỏ qua event cũ nếu đã xử lý version mới hơn, hoặc giữ event chờ nếu cần xử lý tuần tự. Không dùng timestamp đơn lẻ làm thứ tự tuyệt đối nếu nhiều producer có clock khác nhau.

Fan-out cho phép nhiều Trigger nhận cùng một event, ví dụ một consumer cập nhật search index và một consumer gửi notification. Các subscriber cần độc lập: lỗi ở notification không nên làm mất cập nhật index nếu broker và delivery được cấu hình tách biệt.

Backpressure cần được xử lý ở nhiều lớp:

- Giới hạn concurrency của Knative Service.
- Điều chỉnh autoscaling target và max scale.
- Giới hạn số event đang xử lý trong Java worker.
- Giới hạn connection pool và request rate đến dependency.
- Dùng queue/broker buffering nếu implementation hỗ trợ.
- Đặt timeout và retry có backoff.
- Theo dõi backlog, event age và delivery failure.

Nếu subscriber scale nhanh hơn database có thể chịu, event backlog có thể giảm trong khi database bị quá tải. Hãy đặt giới hạn dựa trên năng lực toàn hệ thống, không chỉ tốc độ của container.

## 15. Bảo mật Serving và Eventing

Một Knative Service có thể được expose ra bên ngoài hoặc chỉ truy cập nội bộ. Không mặc định mọi service đều cần public ingress. Dùng ingress policy, gateway, TLS và network policy phù hợp với mô hình cluster.

Với event:

- Xác thực producer hoặc source được phép publish.
- Giới hạn quyền tạo Broker, Trigger và Source bằng Kubernetes RBAC.
- Bảo vệ sink và callback endpoint bằng TLS và authentication phù hợp.
- Không đưa secret vào CloudEvent data nếu subscriber không cần.
- Xác thực tenant/resource trong payload bằng dữ liệu có thẩm quyền.
- Kiểm tra schema và kích thước event.
- Giới hạn URI sink để tránh SSRF hoặc gửi dữ liệu đến đích không tin cậy.
- Ghi audit cho thay đổi routing, filter và quyền truy cập.

CloudEvents chuẩn hóa cấu trúc dữ liệu, không tự xác thực nguồn phát. Một event có source là /payments/provider không chứng minh nó thực sự đến từ payment provider. Cần xác thực ở ingress/source adapter và kiểm tra tính toàn vẹn theo giao thức.

Kubernetes service account, RBAC và network policy quản lý quyền ở cluster. Nếu Java service gọi cloud APIs, dùng workload identity hoặc cơ chế danh tính của nền tảng thay vì đóng gói key dài hạn vào image.

## 16. Quan sát và troubleshooting

Với Serving, theo dõi:

- Request count, concurrency và latency p50/p95/p99.
- Replica/pod count và thời gian scale-up.
- Cold start, startup probe và readiness failure.
- Container CPU, memory, restart và OOM.
- HTTP 4xx/5xx, timeout và dependency latency.
- Revision đang nhận traffic và tỷ lệ traffic theo revision.

Với Eventing, theo dõi:

- Số event được phát và số event delivery.
- Delivery latency và event age.
- Số retry, timeout và dead-letter.
- Subscriber response code.
- Số event duplicate bị idempotency loại bỏ.
- Broker/dispatcher health và backlog nếu implementation cung cấp.
- Số event không khớp Trigger filter.
- Tỷ lệ event theo type/source.

Mỗi log nên có correlation ID, CloudEvent source/id/type, request ID, revision hoặc task identifier. Không log payload nhạy cảm hoặc secret. Nếu một event đi qua nhiều service, dùng event id hoặc trace context để nối log từ producer đến subscriber.

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Service không nhận request | Route/ingress, DNS hoặc TLS sai | Kiểm tra Route, gateway, domain và certificate |
| Pod không ready | PORT sai, startup lâu hoặc probe sai | Kiểm tra log container, port và probe |
| Scale-to-zero không scale lên | Autoscaler/Activator hoặc cấu hình min/max | Kiểm tra metric và cấu hình Serving |
| Request timeout khi cold start | Image lớn hoặc Java init chậm | Đo image pull, process startup và dependency |
| Event không đến subscriber | Source/Broker/Trigger hoặc filter sai | Kiểm tra event attributes, namespace và sink |
| Event lặp | Retry hoặc delivery semantics | Kiểm tra source/id, inbox và retry policy |
| Event vào DLQ | Subscriber lỗi liên tục hoặc schema không hợp lệ | Kiểm tra response, log và DLQ consumer |
| Database quá tải | Concurrency hoặc parallelism quá cao | Giảm scale/concurrency và giới hạn connection |

## 17. Triển khai và kiểm thử

Knative thường được cài trên Kubernetes cùng các CRD và controller của Serving/Eventing. Trước khi triển khai ứng dụng, cần xác minh:

- Knative Serving và Eventing đã được cài đúng phiên bản.
- Ingress/gateway và DNS đã cấu hình.
- Broker implementation và event source extension cần thiết đã sẵn sàng.
- Namespace, service account và RBAC đúng.
- Registry credentials hoặc workload identity cho phép pull image.
- Observability stack thu thập log và metric.

Có thể dùng kubectl để áp dụng manifest:

~~~bash
kubectl apply -f orders-api.yaml
kubectl get ksvc -n apps
kubectl get revisions -n apps
kubectl get routes -n apps
~~~

Đối với Eventing:

~~~bash
kubectl apply -f broker.yaml
kubectl apply -f order-trigger.yaml
kubectl get brokers -n apps
kubectl get triggers -n apps
~~~

Tên resource và CRD có thể khác nếu cluster dùng phiên bản hoặc extension khác. Hãy kiểm tra CRD đã cài trước khi apply manifest.

Các tình huống cần kiểm thử:

1. Service nhận request khi đã có pod sẵn sàng.
2. Service scale về zero rồi nhận request đầu tiên.
3. Tăng burst và concurrency để kiểm tra autoscaling.
4. Triển khai revision mới và chia traffic canary.
5. Rollback traffic khi revision mới có lỗi.
6. Producer phát CloudEvent đúng type và Trigger chuyển đến subscriber.
7. Event sai type không được gửi đến Trigger không phù hợp.
8. Subscriber trả lỗi và delivery retry theo policy.
9. Event vào dead-letter sink sau khi hết retry.
10. Gửi lại cùng source/id và xác minh consumer idempotent.
11. Kiểm tra event đến sai thứ tự hoặc trùng.
12. Kiểm tra RBAC và authentication ngăn producer/consumer trái phép.

## 18. Chọn Serving, Eventing hay kết hợp

| Nhu cầu | Mô hình phù hợp |
|---|---|
| HTTP API cần scale theo request | Knative Serving |
| Webhook receiver | Knative Serving; có thể phát CloudEvent sang Eventing |
| Xử lý event bất đồng bộ | Knative Eventing với subscriber trên Serving |
| Một event cần nhiều consumer | Broker và nhiều Trigger |
| Batch chạy theo lịch | Event source/scheduler phù hợp hoặc job runner; Serving không phải lựa chọn mặc định |
| Quy trình nhiều bước có trạng thái | Workflow engine kết hợp Serving/Eventing |
| Consumer cần chạy liên tục hoặc giữ kết nối lâu | Đánh giá worker/service chuyên dụng và mô hình autoscaling phù hợp |

Serving tập trung vào request lifecycle và scale container. Eventing tập trung vào event contract, routing và delivery. Kết hợp hai thành phần giúp hệ thống vừa cung cấp API đồng bộ vừa xử lý các công việc phát sinh bất đồng bộ.

Không phải mọi workload đều cần cả hai. Một service nhỏ chỉ nhận HTTP có thể chỉ cần Serving. Một pipeline event không có public API có thể chỉ cần Eventing và các subscriber. Chọn abstraction theo yêu cầu về request, event, trạng thái và delivery.

## 19. Quy trình thiết kế ứng dụng Java trên Knative

1. **Phân loại workload.** Xác định phần nào phục vụ HTTP và phần nào phản ứng theo event.
2. **Thiết kế container.** Chọn JDK/JRE, image nhỏ, port, startup và graceful shutdown.
3. **Tạo Knative Service.** Cấu hình revision, concurrency, min/max scale và ingress.
4. **Đo autoscaling.** Benchmark request concurrency, cold start và giới hạn dependency.
5. **Thiết kế event contract.** Dùng CloudEvents với source, id, type và schema rõ ràng.
6. **Cấu hình Broker và Trigger.** Chọn broker implementation, filter và subscriber.
7. **Làm consumer idempotent.** Dùng inbox/unique key, retry và DLQ.
8. **Bảo vệ hệ thống.** Cấu hình TLS, authentication, RBAC, service account và network policy.
9. **Quan sát.** Gắn correlation ID, theo dõi revision, delivery latency và lỗi.
10. **Kiểm thử failure mode.** Scale-to-zero, burst, duplicate, out-of-order, retry và rollback.

## 20. Câu hỏi tự kiểm tra

- Knative Serving và Knative Eventing giải quyết hai bài toán nào?
- Service, Configuration, Revision và Route có vai trò gì?
- Vì sao Knative Revision được xem là bất biến?
- Activator hỗ trợ scale-to-zero như thế nào?
- Container concurrency khác autoscaler target concurrency ra sao?
- Khi nào nên giữ min scale lớn hơn zero?
- Broker và Trigger tách producer khỏi subscriber như thế nào?
- CloudEvents source, id và type được dùng vào việc gì?
- Channel/Subscription khác Broker/Trigger ở mức mô hình ra sao?
- Vì sao event delivery cần idempotency dù có retry?
- Làm thế nào để kiểm soát thứ tự và backpressure?
- Những metric nào giúp phát hiện cold start hoặc event delivery chậm?

Knative Serving giúp Java container phục vụ request và scale theo lưu lượng; Knative Eventing giúp các thành phần trao đổi CloudEvent mà không phụ thuộc trực tiếp vào nhau. Khi kết hợp hai mô hình, hãy thiết kế revision và autoscaling cho đường HTTP, đồng thời thiết kế event contract, retry, dead-letter và idempotency cho đường bất đồng bộ. Đây là nền tảng để triển khai ứng dụng Java serverless trên Kubernetes một cách linh hoạt và có thể vận hành.

