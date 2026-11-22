# Graceful shutdown và hoàn tất yêu cầu đang xử lý

Khi triển khai phiên bản mới của REST API, một Pod hoặc tiến trình Java cũ phải dừng để nhường chỗ cho phiên bản mới. Nếu tiến trình bị cắt ngay giữa lúc xử lý `POST /v1/orders`, người dùng có thể gặp lỗi kết nối dù đơn hàng đã được ghi vào cơ sở dữ liệu. **Graceful shutdown** giúp ứng dụng ngừng nhận việc mới, dành một khoảng thời gian có giới hạn để hoàn tất yêu cầu đang xử lý và đóng tài nguyên theo trật tự. Nó cải thiện trải nghiệm triển khai, nhưng không tự bảo đảm mọi yêu cầu đều thành công hoặc mọi thao tác chỉ thực hiện đúng một lần.

Trong module `INTEGRATION_API_REST`, chủ đề này kết nối vận hành với thiết kế REST: phương thức HTTP, idempotency, timeout, mã trạng thái, kiểm thử API, trạng thái sẵn sàng (readiness) và cơ chế retry của client đều quyết định điều gì xảy ra lúc triển khai.

Sau bài học, bạn có thể:

- Mô tả quy trình từ tín hiệu dừng đến khi request đang xử lý hoàn tất hoặc hết thời hạn chờ.
- Cấu hình graceful shutdown cho Spring Boot và phối hợp với readiness, Service/Ingress và `terminationGracePeriodSeconds` trong Kubernetes.
- Phân biệt request HTTP đồng bộ với công việc `@Async`, hàng đợi, SSE/WebSocket và tác vụ dài hạn.
- Thiết kế retry an toàn, idempotency, quan sát hệ thống và phép kiểm thử triển khai không gián đoạn.

## 1. Vì sao cần graceful shutdown?

Giả sử một client gửi yêu cầu đặt hàng đến API:

```http
POST /v1/orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Idempotency-Key: order-request-7e4

{"productId":42,"quantity":2}
```

Ứng dụng xác thực người dùng, kiểm tra tồn kho, ghi đơn hàng rồi trả `201 Created` với `Location: /v1/orders/853`. Nếu deployment bắt đầu khi tiến trình đang ghi dữ liệu, có ba khả năng quan trọng:

1. **Dừng sau khi phản hồi hoàn tất:** client nhận `201`, biết đơn hàng đã tạo.
2. **Dừng trước khi hoàn tất giao dịch:** client nhận lỗi hoặc mất kết nối; backend cần rollback hoặc cơ chế khôi phục phù hợp.
3. **Giao dịch đã commit nhưng phản hồi chưa đến client:** client không biết thao tác thành công hay chưa và có thể gửi lại request.

Graceful shutdown tăng cơ hội hoàn tất trường hợp thứ nhất bằng cách *drain* các request đang xử lý. Trường hợp thứ ba vẫn có thể xảy ra do mất mạng, timeout hoặc hết thời gian dừng. Vì vậy API ghi dữ liệu quan trọng vẫn cần **idempotency key, ràng buộc duy nhất, giao dịch và quy trình đối soát**.

### Dừng ngay và dừng có thời hạn

| Cách dừng | Hành vi thường gặp | Hệ quả với REST API |
| --- | --- | --- |
| Dừng đột ngột (`SIGKILL`, container bị kill do OOM, host mất điện) | Tiến trình không có cơ hội chạy hook dọn dẹp | Request có thể bị ngắt bất cứ lúc nào; phải phục hồi bằng thiết kế dữ liệu và client |
| Nhận `SIGTERM` nhưng không cấu hình drain phù hợp | Ứng dụng thoát nhanh hoặc đóng kết nối khi vẫn có request | Có thể thấy lỗi kết nối, `502/503` từ proxy |
| Graceful shutdown | Ngừng hoặc hạn chế nhận request mới, chờ request đang chạy trong ngân sách thời gian, đóng tài nguyên | Giảm lỗi trong quá trình rollout; không phải cam kết hoàn tất vô hạn |

**Nguyên tắc:** graceful shutdown là **nỗ lực hoàn tất có giới hạn**. Không cấu hình thời hạn vô hạn để giữ một tiến trình không bao giờ thoát; hệ thống điều phối vẫn cần cách thu hồi tài nguyên khi request treo.

## 2. Vòng đời của một lần dừng có kiểm soát

Với REST API chạy sau gateway và Kubernetes, một trình tự mong muốn là:

```text
Đang phục vụ
    |
    v
Orchestrator quyết định kết thúc instance/Pod
    |
    +--> Báo instance đang rút khỏi lưu lượng (readiness / endpoint removal)
    |        |
    |        +--> Chờ thay đổi định tuyến lan truyền nếu cần
    |
    +--> Gửi SIGTERM đến tiến trình ứng dụng
             |
             v
        Ứng dụng bắt đầu graceful shutdown
             |
             +--> Ngừng tiếp nhận request/connection mới theo khả năng server
             +--> Chờ request đã nhận và công việc có quản lý hoàn tất
             +--> Đóng pool, listener và tài nguyên theo lifecycle
             |
             +--> Hoàn tất trước deadline? -- Có --> Thoát bình thường
                                            |
                                            Không
                                            v
                              Hết thời gian: ép dừng / lỗi gián đoạn
```

Trong Kubernetes, việc đánh dấu Pod đang kết thúc và cập nhật endpoint diễn ra song song với các bước kết thúc container; không có bảo đảm mọi proxy đã ngừng gửi traffic ngay tại một thời điểm. Hook `preStop`, nếu được cấu hình, chạy trước khi kubelet gửi `SIGTERM` cho container; **đồng hồ termination grace period đã bắt đầu** trong thời gian chạy hook. Không nên hiểu sơ đồ như một trình tự đồng bộ tuyệt đối giữa control plane, load balancer và JVM.

Một số khái niệm liên quan:

- **Readiness** trả lời liệu instance có nên nhận thêm lưu lượng hay không. Khi Pod đang kết thúc, Kubernetes thường chuyển endpoint sang trạng thái không sẵn sàng cho request mới; health check riêng của ứng dụng vẫn cần được kiểm thử.
- **Liveness** phục vụ việc phát hiện container hỏng, không phải cơ chế điều phối drain. Không nên cố tình làm liveness thất bại để shutdown vì có thể kích hoạt restart hoặc kill ngoài ý muốn.
- **Grace period** là ngân sách để hook, ứng dụng và runtime dừng. Sau đó orchestrator có thể buộc chấm dứt; cleanup hook không được bảo đảm sẽ chạy.
- **Keep-alive và HTTP/2:** proxy/client có thể giữ connection đang mở. Server cần ngừng nhận request/stream mới phù hợp với stack; một số server hoặc gateway hỗ trợ tín hiệu `GOAWAY` với HTTP/2. Không suy ra rằng readiness đổi trạng thái sẽ cắt hoặc drain mọi connection cũ ngay lập tức.

Đối với rolling deployment, cần có instance mới đủ sẵn sàng trước khi mất các instance cũ. Graceful shutdown chỉ quản lý **cách một instance rời hệ thống**; số replica, chiến lược rollout, dung lượng dư và hành vi của load balancer quyết định cả dịch vụ có duy trì sẵn sàng hay không.

## 3. Cấu hình Spring Boot

### 3.1. Bật graceful shutdown

Với Spring Boot dùng embedded web server hỗ trợ graceful shutdown (ví dụ Tomcat, Jetty, Reactor Netty hoặc Undertow ở phiên bản tương thích), có thể cấu hình:

```yaml
# application.yml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
```

Hai thiết lập đầu tiên có ý nghĩa khác nhau:

- `server.shutdown: graceful` yêu cầu web server dừng tiếp nhận request mới theo cơ chế server hỗ trợ và cho request đang xử lý cơ hội hoàn tất.
- `spring.lifecycle.timeout-per-shutdown-phase: 30s` đặt thời hạn tối đa **cho mỗi phase** khi Spring dừng các bean theo lifecycle. Đây không phải một deadline tuyệt đối duy nhất cho toàn bộ quá trình JVM thoát. Nhiều phase, hook, tác vụ dọn dẹp và chậm trễ bên ngoài có thể làm tổng thời gian dài hơn.

Mức hỗ trợ chi tiết khác nhau giữa phiên bản Spring Boot và web server. Một số implementation ngừng nhận request ở lớp mạng, số khác có thể trả lỗi cho request mới trong lúc dừng. Cần xác nhận hành vi thực tế bằng kiểm thử, kể cả khi log báo đã bật graceful shutdown.

Với Spring Boot Actuator được thêm vào dependency, có thể cấu hình readiness probe tại `GET /actuator/health/readiness`. Endpoint này phản ánh khả năng nhận traffic theo cơ chế `ApplicationAvailability` khi được kích hoạt; trạng thái/kết quả phụ thuộc vòng đời và health contributor đã cấu hình. Probe nên được truy cập từ mạng nội bộ phù hợp, không nên mở toàn bộ endpoint quản trị ra Internet.

Trong Kubernetes, **SIGTERM** thường bắt đầu quy trình dừng JVM để Spring thực hiện shutdown hooks. `kill -9` hoặc `SIGKILL` không kích hoạt quá trình này. Dừng bằng `System.exit`, tín hiệu hoặc hệ thống điều phối có thể có đường đi khác nhau; hãy thử theo đúng cách ứng dụng được dừng tại môi trường đích.

### 3.2. Ví dụ endpoint để kiểm tra request đang xử lý

Đoạn mã sau chỉ dành cho môi trường thử nghiệm: endpoint cố tình giữ request trong 8 giây để quan sát shutdown.

```java
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/demo")
class SlowController {

    @GetMapping("/slow")
    ResponseEntity<Map<String, String>> slow() throws InterruptedException {
        Thread.sleep(8_000); // Chỉ mô phỏng I/O chậm trong bài kiểm thử
        return ResponseEntity.ok(Map.of("status", "completed"));
    }
}
```

Ở ứng dụng thực, tránh chủ động `Thread.sleep` trong request thread; hãy đặt timeout cho truy vấn/call downstream và dùng mô hình xử lý phù hợp. Để kiểm thử, khởi chạy ứng dụng, gọi `/v1/demo/slow`, rồi gửi SIGTERM khi response chưa trả về. Nếu thời gian shutdown đủ lớn, client kỳ vọng nhận `200 OK` sau khi request hoàn tất; nếu vượt deadline, client có thể nhận lỗi/ngắt kết nối. **Kết quả phải được kiểm chứng trên server thực tế**, không mặc định từ cấu hình.

### 3.3. Request đồng bộ khác công việc bất đồng bộ

Web server có thể biết request nào đang được xử lý, nhưng không tự biết tất cả công việc nghiệp vụ đã tách ra khỏi request. Ví dụ:

```java
@PostMapping("/exports")
ResponseEntity<Void> startExport(@RequestBody ExportRequest request) {
    exportService.startInBackground(request); // Ví dụ ý tưởng: trả về ngay
    return ResponseEntity.accepted()
            .location(URI.create("/v1/exports/" + request.jobId()))
            .build();
}
```

Nếu `startInBackground` chỉ tạo một `@Async` task trong bộ nhớ của Pod rồi trả `202 Accepted`, client có thể tin job đã được nhận, nhưng khi Pod dừng, task có thể chưa chạy xong và bị mất. Với công việc cần độ bền, hãy **ghi trạng thái job vào kho dữ liệu bền vững hoặc đẩy thông điệp vào queue có xác nhận phù hợp**, rồi mới trả `202`; cung cấp resource như `GET /v1/exports/{id}` để theo dõi. Worker nên ngừng nhận job mới khi drain, hoàn tất hoặc trả lại job chưa xong, và chỉ đánh dấu thành công sau khi commit kết quả.

`@Async`, `@Scheduled`, executor riêng và consumer Kafka/RabbitMQ có **lifecycle** và chính sách drain riêng. Khi cần, đăng ký quản lý bằng `SmartLifecycle`, bảo đảm gọi callback khi đã dừng hoặc đạt deadline, và điều chỉnh cấu hình executor theo phiên bản Spring đang sử dụng. `@PreDestroy` thích hợp cho cleanup ngắn, nhưng không nên dựa vào một hook tùy ý để chờ vô hạn mọi tác vụ.

## 4. Phối hợp với Kubernetes và reverse proxy

Một cấu hình deployment tham khảo:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rest-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: rest-api
  template:
    metadata:
      labels:
        app: rest-api
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: rest-api
          image: registry.example.com/rest-api:1.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 10"]
```

Đây là **ví dụ triển khai**, không phải cấu hình thời gian phù hợp cho mọi hệ thống. Hook `preStop` chờ 10 giây nhằm có thêm khoảng đệm cho endpoint/gateway ngừng gửi request mới trước khi ứng dụng nhận SIGTERM. Nó **tiêu thụ 10 giây trong 90 giây termination grace** và chỉ chạy được nếu image có `/bin/sh` cùng lệnh `sleep`; image distroless thường không có shell. Với hệ thống mà định tuyến đã drain đúng và đủ nhanh, có thể không cần hook chờ.

Cần kiểm thử đồng thời ba điều kiện:

1. **Định tuyến:** sau khi Pod bắt đầu terminating, Service, Ingress, API Gateway hoặc service mesh có ngừng đưa request mới vào Pod đủ sớm hay không? Sự lan truyền có thể chậm.
2. **Ngân sách thời gian:** thời gian `preStop` + các phase shutdown/cleanup + request lâu nhất có thể hoàn tất + khoảng đệm phải nằm trong `terminationGracePeriodSeconds`. Vì các hoạt động có thể chồng lấp, hãy đo timeline thật thay vì cộng các con số một cách máy móc.
3. **Khả năng phục vụ:** các Pod còn lại có đủ CPU, thread, DB connections và replica để gánh lưu lượng tăng sau khi một Pod rút khỏi rotation hay không? `maxUnavailable: 0` hỗ trợ rollout thận trọng, nhưng không thay thế đánh giá capacity và PodDisruptionBudget nếu cần.

### Vấn đề đường truyền giữ kết nối

Khi client dùng HTTP/1.1 keep-alive hoặc HTTP/2 multiplexing, một connection có thể tồn tại lâu hơn một request. Readiness không tự đóng connection đó. Tùy web server, proxy và thời điểm drain, request mới trên connection cũ có thể bị từ chối hoặc chuyển hướng. Client cần xử lý trường hợp connection reset, `503 Service Unavailable`, `GOAWAY` hoặc timeout dựa trên ngữ nghĩa từng request. Không giả định tất cả request mới đều được chuyển sang Pod khác một cách trong suốt.

Ở hệ thống có proxy kết thúc TLS, cần đo riêng chặng client → gateway và gateway → Spring. **Spring graceful shutdown không tự cấu hình connection draining của load balancer**, và graceful timeout của gateway có thể ngắn hơn của ứng dụng.

## 5. Request nào có thể hoàn tất? Request nào cần cơ chế phục hồi?

| Tình huống | Khi shutdown bắt đầu | Cách thiết kế hợp lý |
| --- | --- | --- |
| `GET /v1/products/{id}` nhanh | Đang đọc dữ liệu | Cho phép hoàn tất trong grace; client có thể retry theo chính sách nếu mất kết nối |
| `POST /v1/orders` | Đã commit DB, response chưa gửi | Dùng `Idempotency-Key` với cơ chế lưu kết quả/khóa bền vững hoặc quy tắc chống trùng để retry không tạo đơn thứ hai |
| `PUT /v1/profile` | Request bị gián đoạn | Thiết kế PUT có tính idempotent, bảo vệ cập nhật đồng thời nếu cần bằng `ETag`/`If-Match` |
| `GET /v1/reports/huge` trả body lớn | Đang stream response | Cân nhắc phân trang, tải theo phần, giới hạn thời gian và hỗ trợ resume khi thích hợp |
| `POST /v1/exports` tạo job | Trả `202` trước khi job xong | Lưu job bền vững; worker có lease/ack/retry và cơ chế dedup |
| SSE/WebSocket/gRPC stream dài hạn | Kết nối có thể sống hàng giờ | Chủ động thông báo đóng/đổi instance, cho client reconnect và tiếp tục từ checkpoint khi có thể |

Mã `202 Accepted` nghĩa là yêu cầu **đã được chấp nhận để xử lý**, không khẳng định job hoàn tất. Tương tự, graceful shutdown không thay thế transaction, outbox, checkpoint hay cơ chế xử lý lại an toàn.

### Idempotency khi client không biết kết quả

Xét một request tạo đơn hàng:

```text
Client             Old Pod                  Database
  | POST key=k         |                        |
  |------------------->| BEGIN/INSERT/COMMIT     |
  |                    |----------------------->|
  |                    |<--- COMMIT thành công ---|
  |              Pod dừng / response mất        |
  | X timeout/reset    |                        |
  |                    |                        |
  | POST key=k tới Pod mới                       |
  |--------------------------------------------->|
  |          Trả lại kết quả cũ từ idempotency store
  |<---------------------------------------------|
```

Đây là **sơ đồ nghiệp vụ**, không phải sơ đồ kết nối HTTP/DB chính xác. Để đạt kết quả mong muốn, khóa idempotency phải được lưu và kiểm tra nhất quán giữa các Pod, ràng buộc với người gọi/phạm vi thao tác và payload thích hợp, có xử lý request đồng thời và quy tắc hết hạn. Chỉ gắn một HTTP header nhưng không có lưu trữ bền vững thì không đủ.

Với `GET`/`HEAD`, retry thường an toàn về mặt ngữ nghĩa nhưng vẫn phải giới hạn số lần, backoff và deadline. Với `POST`/`PATCH`, cần hiểu tính chất nghiệp vụ; không tự retry mọi request sau một lần connection reset. Nếu server chủ động từ chối request mới trong lúc drain, có thể trả `503` và `Retry-After` khi phù hợp, nhưng việc client thấy `503` hay lỗi vận chuyển phụ thuộc kiến trúc và thời điểm ngắt kết nối.

## 6. Xác định ngân sách shutdown từ SLO thực tế

Ví dụ API có:

- Request bình thường p99 ~ 2 giây, một số request hợp lệ có thể chạy 15 giây.
- Gateway cần một khoảng ngắn để ngừng đưa traffic tới Pod cũ.
- Shutdown của worker nội bộ và đóng kết nối mất thêm thời gian.
- Deployment quy định `terminationGracePeriodSeconds: 90`.

Không chọn `timeout-per-shutdown-phase: 90s` và `preStop: sleep 30` một cách độc lập: cả hai có thể khiến ứng dụng bị kill khi đang cleanup. Hãy đo thời gian theo các mốc:

```text
T0: Pod được đánh dấu terminating
T1: preStop bắt đầu / endpoint chuyển trạng thái
T2: SIGTERM gửi tới ứng dụng
T3: Spring bắt đầu từ chối việc mới
T4: in-flight requests về 0; worker đã ngừng nhận việc
T5: JVM thoát
T6: termination grace hết hạn nếu tiến trình chưa thoát
```

Đặt ngưỡng sao cho **T5 thường xảy ra trước T6 với khoảng đệm đáng kể**, kể cả dưới tải hợp lệ. Nếu một request có timeout nghiệp vụ 5 phút nhưng Pod chỉ có 90 giây để kết thúc, phải thay đổi thiết kế: cho request tạo một job có thể tiếp tục ở instance khác, giảm thời gian xử lý hoặc thiết kế trạng thái resume; không thể dựa vào graceful shutdown để chờ đủ 5 phút.

Graceful shutdown và thời hạn request là hai ngân sách khác nhau. Một request có deadline 15 giây vẫn nên tự hủy/cắt call downstream khi quá hạn, kể cả Pod còn 60 giây để drain. Việc client tự timeout cũng không đồng nghĩa backend đã dừng xử lý; điều này liên quan trực tiếp đến idempotency và chi phí tài nguyên.

## 7. Kiểm thử đóng tiến trình và rollout

### 7.1. Thử nghiệm một tiến trình Spring Boot

Trên Linux/macOS hoặc bên trong container nơi có tín hiệu POSIX, dùng **hai terminal**:

**Terminal A:** khởi chạy ứng dụng có cấu hình `server.shutdown: graceful`.

```bash
java -jar rest-api.jar
```

**Terminal B:** gửi request chậm:

```bash
curl -v --max-time 30 'http://localhost:8080/v1/demo/slow'
```

Trong lúc request đang chạy, ở terminal khác gửi `SIGTERM` đến **PID của JVM thực tế**:

```bash
kill -TERM <java-pid>
```

Kết quả mong muốn trong trường hợp request 8 giây, phase timeout 30 giây và môi trường không có lỗi khác: client nhận response hoàn tất; JVM thoát sau khi drain/cleanup. Thử lại với request kéo dài quá ngân sách và ghi nhận client nhận lỗi gì. Không dùng `kill -9` để kiểm chứng graceful shutdown, vì tín hiệu này bỏ qua cơ chế dừng có kiểm soát. Lệnh thử nghiệm và khả năng tín hiệu tùy hệ điều hành, shell và trình quản lý tiến trình.

### 7.2. Thử nghiệm trong Kubernetes

Trong **môi trường staging**, triển khai ít nhất hai Pod, tạo một số request đồng thời và thực hiện rollout hoặc xóa một Pod được chọn:

```bash
kubectl rollout restart deployment/rest-api
kubectl rollout status deployment/rest-api
kubectl get pods -l app=rest-api -w
```

Quan sát các request phát sinh **trước, trong và sau** rollout. Đặc biệt ghi lại request ID, phiên bản Pod đã xử lý, mã HTTP, timeout, thời điểm kết thúc và thông báo shutdown từ ứng dụng. Thử cả request nhanh, request lâu, `POST` ghi DB và job bất đồng bộ. Không chỉ nhìn vào `kubectl rollout status`: rollout có thể thành công dù một số client gặp reset hoặc dữ liệu nghiệp vụ bị trùng.

### 7.3. Bộ tiêu chí nghiệm thu

| Phép thử | Kỳ vọng | Cách phát hiện lỗi |
| --- | --- | --- |
| SIGTERM khi có request ngắn đang chạy | Request hợp lệ hoàn tất trong ngân sách | Response/client logs; trace và mã HTTP |
| Request đến sau khi rút Pod khỏi định tuyến | Được Pod còn sẵn sàng xử lý hoặc nhận lỗi có thể phục hồi phù hợp | Proxy access logs, Pod ID, `502/503`, reset |
| Request dài hơn grace period | Có cơ chế timeout/khôi phục được xác định rõ | Forced kill, timeout, trạng thái DB, retry |
| `POST` đã commit nhưng client mất response | Retry cùng khóa không tạo bản ghi thứ hai | Ràng buộc dữ liệu, idempotency store, test race |
| Job `202 Accepted` còn chạy | Job hoàn tất hoặc được tái thực thi an toàn sau restart | Durable job state, ack/lease, dedup |
| Rolling deploy dưới tải | SLO về lỗi và p95/p99 trong ngưỡng cho phép | Latency histogram, request count, capacity còn lại |

Không nên dừng ở kịch bản "gửi SIGTERM trong lúc API đang chạy". Hãy lặp lại phép thử ở concurrency hợp lệ, có keep-alive/HTTP/2, khi gateway có độ trễ cập nhật routing, và khi downstream chậm hoặc gặp lỗi.

## 8. Quan sát và xử lý sự cố trong production

Để chứng minh graceful shutdown hoạt động, log và metric cần liên kết được giai đoạn dừng với lưu lượng thực:

- **Theo request:** request/trace ID, method, route, status, thời gian xử lý, thông tin timeout, Pod instance và retry. Tránh ghi token, dữ liệu cá nhân hoặc toàn bộ body nhạy cảm.
- **Theo instance:** thời điểm nhận SIGTERM, readiness chuyển trạng thái, số request in-flight, thời gian drain, kết thúc từng lifecycle phase, thời điểm JVM thoát.
- **Theo gateway:** upstream Pod được chọn, connection reset/timeout, `502/503/504`, request đến Pod đang terminating, tình trạng connection keep-alive/HTTP/2.
- **Theo downstream:** DB connection pool đang dùng/chờ, request bị block, queue depth, số job đang chạy, kết quả ack/retry.

Metric cụ thể phụ thuộc Spring Boot, Micrometer, web server và hệ thống quan sát; **không giả định có sẵn một metric tên "inflight_requests" trong mọi stack**. Nếu cần, instrument active requests và trạng thái drain với quy ước label ít cardinality. Alert dựa trên tỷ lệ lỗi, thời gian chờ và việc Pod bị ép kill lặp lại, đồng thời đối chiếu log của rollout.

Một số chẩn đoán thường gặp:

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xác minh |
| --- | --- | --- |
| `502` tăng vài giây sau rollout | Proxy còn định tuyến tới Pod cũ hoặc connection bị đóng quá sớm | Đối chiếu log proxy, Pod termination, preStop và timeout |
| Pod luôn bị `SIGKILL` khi hết grace | Request/worker không dừng, cleanup quá lâu, ngân sách không đủ | Timeline T0–T6, thread dump, executor, deadline downstream |
| Log báo graceful shutdown hoàn tất nhưng job bị mất | Job chạy ngoài web request lifecycle | Kiểm tra `@Async`, scheduler, durable queue/ack |
| Đơn hàng bị tạo hai lần | Client retry sau timeout khi transaction trước đã commit | Kiểm tra idempotency key, unique constraint, transaction |
| p99 tăng dù không có `5xx` | Pod còn lại quá tải, thiếu capacity trong rollout | Replica, CPU, pool chờ, gateway queue và autoscaling |

## 9. Bài tập thực hành

**Bài tập 1 — Phân tích ngân sách.** Một Pod có `terminationGracePeriodSeconds=35`, `preStop` ngủ 12 giây và Spring có `timeout-per-shutdown-phase=30s`. Có request hợp lệ cần 25 giây mới hoàn tất sau SIGTERM. Hãy giải thích vì sao cấu hình này có nguy cơ bị ép dừng; đề xuất cách đo và điều chỉnh. **Gợi ý:** preStop đã dùng một phần ngân sách 35 giây; shutdown còn có cleanup và có thể nhiều phase.

**Bài tập 2 — Đơn hàng bị lặp.** Client gửi `POST /v1/orders`, server commit nhưng trả response không thành công do rollout. Client gửi lại và hệ thống tạo đơn thứ hai. Thiết kế cơ chế idempotency sử dụng khóa client, kiểm tra payload và ràng buộc lưu trữ bền vững; mô tả response mà client phải nhận ở lần gửi lại.

**Bài tập 3 — Chứng minh drain.** Dùng endpoint `/v1/demo/slow`, Spring Boot Actuator và ít nhất hai Pod staging. Ghi timeline nhận `SIGTERM`, số request đang xử lý, response kết thúc và readiness/routing. Thử tạo request ngay trước khi xóa Pod và sau khi nó vào trạng thái terminating. Trình bày cách phân biệt lỗi ở app với lỗi do gateway tiếp tục gửi traffic đến Pod cũ.

**Bài tập 4 — Job bất đồng bộ.** Một REST API trả `202 Accepted` rồi chạy `@Async` để xuất báo cáo dài hai phút; Pod bị dừng sau 20 giây. Hãy đề xuất mô hình resource `/v1/exports/{id}`, lưu trạng thái job, queue, acknowledgment, retry và dedup. Giải thích vì sao tăng `timeout-per-shutdown-phase` đơn thuần chưa tạo được tính bền vững.

**Bài tập 5 — Kết nối dài.** Một client giữ SSE hoặc HTTP/2 stream trong 10 phút trong khi Pod có grace period 60 giây. Hãy nêu chính sách đóng stream, checkpoint/reconnect và trường hợp server gửi thông báo kết thúc trước khi đóng nếu giao thức/ứng dụng hỗ trợ.

**Tiêu chí đạt:** phân biệt được dừng ứng dụng với điều phối traffic; giải thích đúng vai trò của `SIGTERM`, `readiness`, `preStop` và `terminationGracePeriodSeconds`; xác định giới hạn của graceful shutdown với transaction, retry và job nền; đồng thời kiểm chứng được bằng số đo rằng request đang chạy được hoàn tất trong ngân sách hoặc được phục hồi an toàn khi bị ngắt.
