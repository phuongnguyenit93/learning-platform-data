# Phân biệt tiến trình sống, ứng dụng sẵn sàng và khả năng phục vụ

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt process liveness, application readiness và khả năng phục vụ request thực tế.
- Hiểu các trạng thái LivenessState và ReadinessState của Spring Boot.
- Cấu hình health probe của Spring Boot Actuator và Kubernetes.
- Quyết định dependency nào nên tham gia readiness check và dependency nào không nên tham gia liveness check.
- Đồng bộ readiness với service discovery, load balancing và quá trình shutdown.
- Thiết kế kiểm thử để phát hiện instance còn sống nhưng không thể nhận traffic hoặc xử lý nghiệp vụ.

## 1. Ba câu hỏi khác nhau về trạng thái dịch vụ

Khi vận hành microservice, một tín hiệu sức khỏe không thể trả lời mọi câu hỏi. Cần phân biệt ba khái niệm:

1. **Tiến trình còn sống (liveness):** process hoặc JVM còn hoạt động theo cách mà nền tảng có thể tiếp tục sử dụng hay cần khởi động lại?
2. **Ứng dụng sẵn sàng (readiness):** instance đã hoàn tất khởi tạo và có thể nhận request mới ở thời điểm hiện tại chưa?
3. **Khả năng phục vụ (serving capability):** request hoặc operation cụ thể có thể hoàn thành với dữ liệu, dependency, quyền và tài nguyên hiện có hay không?

Ví dụ, một ứng dụng Spring Boot có thể có JVM đang chạy nhưng chưa hoàn tất kết nối database. Process còn sống, nhưng ứng dụng chưa sẵn sàng nhận traffic. Sau khi readiness chuyển sang ACCEPTING_TRAFFIC, một request đọc tồn kho vẫn có thể thành công trong khi request thanh toán thất bại vì payment provider đang gián đoạn. Readiness của instance không bảo đảm mọi operation đều thành công.

| Khái niệm | Câu hỏi | Phạm vi | Hành động thường tương ứng |
| --- | --- | --- | --- |
| Liveness | Process có còn tiến triển và có thể tiếp tục chạy không? | Toàn bộ process/instance | Nếu thất bại liên tục, nền tảng có thể restart container. |
| Readiness | Instance có nên nhận request mới không? | Toàn bộ instance hoặc nhóm traffic | Nếu thất bại, loại instance khỏi tập đích nhận traffic. |
| Serving capability | Request này có thể được phục vụ không? | Từng request, endpoint hoặc operation | Trả kết quả phù hợp, retry có giới hạn, fallback hoặc lỗi có kiểm soát. |

Ba trạng thái có liên quan nhưng không thể thay thế nhau. Một instance có thể alive nhưng not ready; có thể ready nhưng một endpoint cụ thể đang lỗi; và một process có thể còn tồn tại nhưng bị deadlock khiến request không được xử lý.

## 2. Liveness: process có nên tiếp tục chạy?

Liveness trả lời liệu instance có rơi vào trạng thái hỏng không thể tự phục hồi hay không. Nếu liveness thất bại vượt ngưỡng, Kubernetes có thể restart container. Với Spring Boot, Actuator cung cấp `LivenessStateHealthIndicator` và health group `liveness`.

Spring Boot biểu diễn trạng thái bằng:

- `LivenessState.CORRECT`: ứng dụng chưa phát hiện trạng thái liveness bị hỏng.
- `LivenessState.BROKEN`: ứng dụng phát hiện trạng thái không thể tiếp tục hoạt động an toàn.

Liveness thường phù hợp để phát hiện những lỗi nội bộ như:

- Một lỗi không thể phục hồi khiến ứng dụng không còn xử lý công việc.
- Trạng thái nội bộ bị hỏng và ứng dụng cần khởi động lại để khôi phục.
- Một cơ chế watchdog của ứng dụng xác định worker quan trọng đã chết hoặc không thể tiến triển.
- Ứng dụng bị kẹt ở trạng thái mà restart là cách phục hồi được thiết kế.

Không nên đưa mọi dependency bên ngoài vào liveness. Nếu database, Redis hoặc một API bên ngoài tạm thời mất kết nối, restart đồng loạt tất cả pod thường không sửa được dependency đó. Restart hàng loạt còn có thể làm tăng kết nối, tải khởi động và áp lực lên hệ thống đang gặp sự cố.

Liveness cũng không nên là một phép đo nghiệp vụ chi tiết. Một endpoint health quá nặng có thể làm tăng tải hoặc tự thất bại khi hệ thống đang quá tải. Hãy giữ liveness nhanh, cục bộ và có ý nghĩa rõ ràng.

## 3. Readiness: instance đã có thể nhận traffic chưa?

Readiness trả lời liệu instance có nên được đưa vào tập đích nhận request mới hay không. Spring Boot cung cấp:

- `ReadinessState.ACCEPTING_TRAFFIC`: instance sẵn sàng nhận traffic.
- `ReadinessState.REFUSING_TRAFFIC`: instance tạm thời không nên nhận traffic.

Spring Boot Actuator cung cấp health group `readiness` thông qua `ReadinessStateHealthIndicator`. Khi ứng dụng hoàn tất startup, Spring Boot chuyển sang trạng thái sẵn sàng theo lifecycle mặc định. Ứng dụng cũng có thể chủ động chuyển trạng thái trong các tình huống như bảo trì, warm-up hoặc shutdown.

Readiness có thể kiểm tra những điều kiện thật sự cần thiết để nhận request:

- Khởi tạo cấu hình và component quan trọng đã hoàn tất.
- Kết nối tới database bắt buộc đã được thiết lập hoặc pool đã sẵn sàng.
- Cache bắt buộc đã warm-up đủ để phục vụ traffic.
- Consumer hoặc worker quan trọng đã khởi động nếu request phụ thuộc vào chúng.
- Instance chưa vào chế độ bảo trì hoặc draining.
- Giới hạn tài nguyên còn đủ để nhận thêm request theo chính sách vận hành.

Readiness không nhất thiết phải kiểm tra mọi dependency. Nếu ứng dụng vẫn phục vụ được phần lớn request khi một hệ thống phụ trợ không sẵn sàng, đưa dependency đó vào readiness có thể khiến toàn bộ replica bị loại khỏi traffic dù chúng vẫn có khả năng phục vụ một phần chức năng.

### Readiness toàn instance và khả năng từng chức năng

Một readiness endpoint thường trả lời câu hỏi ở cấp instance: có nên gửi traffic mới đến pod này không? Nó không thay thế health check riêng cho từng dependency hoặc logic xử lý từng operation.

| Tình huống | Readiness phù hợp | Xử lý request |
| --- | --- | --- |
| Ứng dụng chưa hoàn tất tải cấu hình bắt buộc | REFUSING_TRAFFIC | Chưa nhận request. |
| Database chính không thể truy cập và mọi request đều cần database | Có thể REFUSING_TRAFFIC | Trả lỗi có kiểm soát nếu request vẫn tới trong lúc cập nhật trạng thái. |
| Dịch vụ email tạm thời lỗi nhưng API đọc dữ liệu vẫn hoạt động | Có thể vẫn ACCEPTING_TRAFFIC | Chỉ operation gửi email dùng retry/outbox hoặc báo lỗi tương ứng. |
| Payment provider lỗi nhưng order query vẫn hoạt động | Có thể vẫn ACCEPTING_TRAFFIC | Operation thanh toán dùng timeout, circuit breaker và phản hồi phù hợp. |
| Thread pool phục vụ request đã cạn và instance không thể nhận thêm traffic | Có thể chuyển REFUSING_TRAFFIC theo policy | Giới hạn queue, trả 429/503 hoặc áp dụng backpressure. |

Không đánh dấu instance NOT_READY chỉ vì một endpoint ít quan trọng gặp lỗi. Hãy xác định hợp đồng phục vụ của service và những điều kiện tối thiểu để nhận request mới.

## 4. Serving capability: request cụ thể có thể thành công không?

Serving capability là khả năng thực hiện một operation cụ thể. Nó phụ thuộc vào nhiều yếu tố tại thời điểm request:

- Dependency mà operation đó cần.
- Dữ liệu và trạng thái nghiệp vụ.
- Quyền truy cập và danh tính caller.
- Timeout, quota, rate limit và circuit breaker.
- Tài nguyên tức thời như thread pool, connection pool, queue và memory.
- Phiên bản API, schema và khả năng tương thích của dữ liệu.

Một instance có thể READY nhưng request thanh toán vẫn thất bại do payment provider timeout. Một request đọc catalog có thể vẫn thành công. Nếu readiness phản ánh trạng thái của tất cả dependency cho mọi operation, hệ thống sẽ dễ loại bỏ quá nhiều instance và tạo hiệu ứng domino.

Serving capability nên được phản ánh qua kết quả request, metrics, tracing, dependency health và các cơ chế bảo vệ như timeout, circuit breaker, bulkhead, rate limit và fallback. Không nên biến mỗi lỗi request thành thay đổi readiness toàn instance.

Ví dụ controller trả kết quả theo khả năng operation:

~~~~java
@RestController
@RequestMapping("/payments")
public class PaymentController {

    private final PaymentService paymentService;

    public PaymentController(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @PostMapping
    public ResponseEntity<PaymentResult> pay(
            @RequestBody PaymentCommand command) {
        try {
            return ResponseEntity.ok(paymentService.pay(command));
        } catch (PaymentProviderUnavailableException ex) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .build();
        }
    }
}
~~~~

Nếu payment provider tạm thời không sẵn sàng, API thanh toán có thể trả 503 hoặc phản hồi domain phù hợp. Instance vẫn có thể phục vụ các endpoint khác. Đây là xử lý ở cấp operation, không nhất thiết là lý do để restart process.

## 5. Spring Boot Actuator health groups

Thêm Actuator để cung cấp endpoint health:

~~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~~

Cấu hình ví dụ:

~~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~~

Khi health probes được bật, Spring Boot cung cấp các health group:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Khi `add-additional-paths` được hỗ trợ và bật, Spring Boot còn cung cấp các đường dẫn ngắn trên cổng server chính:

- `/livez`
- `/readyz`

Đường dẫn bổ sung trên cổng ứng dụng chính hữu ích khi management server dùng port riêng. Nếu chỉ probe management port, endpoint health có thể vẫn trả lời dù web server chính đã lỗi hoặc không nhận request. Đưa probe path lên main server port giúp kiểm tra cả đường HTTP mà ứng dụng thực sự dùng để nhận traffic.

Spring Boot có thể tự bật probes khi nhận diện môi trường Kubernetes ở một số phiên bản. Cấu hình `probes.enabled` tường minh giúp hành vi rõ ràng hơn giữa môi trường local, test và Kubernetes. Hãy kiểm tra tài liệu đúng phiên bản Spring Boot đang dùng.

### Health group không tự động kiểm tra mọi dependency

Mặc định, liveness và readiness group tập trung vào các availability state tương ứng. Không nên giả định rằng mọi `HealthIndicator` trong ứng dụng đều được đưa vào cả hai group.

Nếu cần thêm indicator vào readiness, có thể cấu hình rõ:

~~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~~

Ví dụ này thêm `db` vào readiness group. Chỉ dùng khi database là điều kiện bắt buộc để instance nhận traffic. Nếu database lỗi và toàn bộ pod cùng chuyển NOT_READY, Service có thể không còn endpoint; hãy cân nhắc khả năng degrade và cách hệ thống phục hồi.

Không thêm `db`, Redis, broker hoặc external API vào liveness chỉ để restart pod khi dependency tạm thời lỗi. Nếu buộc phải thêm một indicator, cần hiểu rõ hành động restart có thực sự khắc phục được lỗi đó hay không.

## 6. Chủ động thay đổi Availability State

Spring Boot cung cấp `ApplicationAvailability` để đọc trạng thái và `AvailabilityChangeEvent` để phát thay đổi trạng thái. Ví dụ chuyển instance sang từ chối traffic khi chuẩn bị bảo trì:

~~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceMode {

    private final ApplicationContext applicationContext;

    public MaintenanceMode(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void resumeTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~~

Trạng thái readiness do Spring Boot quản lý trong application context. Probe health group đọc trạng thái đó và phản ánh ra HTTP status. Việc phát event không tự dừng HTTP listener hoặc hủy request đang chạy; nó báo cho nền tảng và routing layer biết instance không nên nhận request mới.

Nếu ứng dụng dùng registry như Eureka hoặc Consul, cần cấu hình tích hợp tương ứng để trạng thái readiness được phản ánh vào registry khi muốn registry cũng ngừng chọn instance. Chỉ đổi Spring Boot ReadinessState không bảo đảm mọi registry tự động cập nhật trạng thái.

## 7. Kubernetes startup, liveness và readiness probes

Kubernetes cung cấp ba loại probe thường dùng:

| Probe | Mục đích | Khi thất bại |
| --- | --- | --- |
| startupProbe | Chờ ứng dụng khởi động đủ lâu trước khi đánh giá liveness/readiness. | Sau số lần thất bại cho phép, container bị restart. |
| livenessProbe | Phát hiện container không còn hoạt động bình thường. | Kubelet restart container theo policy. |
| readinessProbe | Xác định container có nên nhận traffic từ Service hay không. | Pod bị đánh dấu chưa sẵn sàng; endpoint không được chọn cho traffic thông thường của Service. |

Khi khai báo startupProbe, Kubernetes chưa chạy livenessProbe và readinessProbe cho đến khi startupProbe thành công. Đây là cách phù hợp cho ứng dụng khởi động chậm hoặc cần warm-up dữ liệu.

Ví dụ Deployment:

~~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      containers:
        - name: app
          image: example/inventory-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~~

Các giá trị trong ví dụ chỉ minh họa. Điều chỉnh period, timeout, failureThreshold và successThreshold theo thời gian startup, độ trễ health endpoint và yêu cầu phát hiện lỗi. Không đặt timeout quá ngắn khiến probe thất bại giả khi cluster đang tải cao.

Kubernetes HTTP probe xem response status trong khoảng 200–399 là thành công. Endpoint Actuator health trả trạng thái tương ứng với health group; khi group DOWN hoặc OUT_OF_SERVICE, Spring Boot thường trả HTTP 503 để probe thất bại.

### Readiness probe tác động đến Service như thế nào?

Khi readiness probe thất bại, Pod vẫn có thể chạy nhưng không được xem là ready. Kubernetes cập nhật trạng thái endpoint để Service tránh gửi traffic thông thường đến Pod chưa sẵn sàng. Với EndpointSlice, điều kiện `ready` phản ánh khả năng nhận traffic của endpoint; một số cấu hình như `publishNotReadyAddresses` thay đổi hành vi công bố endpoint.

Readiness probe không tự restart container. Nếu chỉ readiness lỗi, process vẫn tiếp tục chạy để có thể phục hồi. Liveness mới là probe quyết định restart khi thất bại liên tục.

## 8. Kết nối readiness với Service Discovery

Service discovery có thể lấy dữ liệu từ nhiều nguồn: Kubernetes Endpoints/EndpointSlices, Eureka, Consul hoặc ZooKeeper. Cần xác định rõ readiness được phản ánh ở lớp nào.

### Kubernetes Service và EndpointSlice

Với Kubernetes Service, readiness của Pod ảnh hưởng đến endpoint được dùng để chuyển traffic thông thường. DiscoveryClient đọc Endpoints hoặc EndpointSlices có thể nhìn thấy tập instance dựa trên trạng thái endpoint và cách implementation xử lý điều kiện ready.

Không nên giả định mọi thư viện discovery đều lọc endpoint giống hệt kube-proxy. Hãy kiểm tra implementation và cấu hình cụ thể, đặc biệt khi bật `publishNotReadyAddresses` hoặc dùng headless Service.

### Eureka

Eureka Client có thể tích hợp Spring Boot health status với registry bằng:

~~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~~

Đặt cấu hình này trong `application.yml` theo hướng dẫn Spring Cloud Netflix của phiên bản đang dùng. Tài liệu cảnh báo không đặt thuộc tính healthcheck này trong `bootstrap.yml`, vì trạng thái ứng dụng có thể chưa được khởi tạo đúng lúc bootstrap.

Health check integration giúp trạng thái health của ứng dụng được phản ánh vào Eureka. Tuy nhiên, không nên mặc định rằng health status tổng thể tương đương chính xác với ReadinessState hoặc mọi endpoint nghiệp vụ. Nếu muốn Eureka chỉ công bố instance khi readiness cho phép nhận traffic, hãy kiểm tra `HealthCheckHandler` đang dùng và tùy chỉnh mapping nếu cần.

### Consul và các registry khác

Consul có thể dùng health check gắn với service registration, ví dụ HTTP check tới Actuator endpoint. Cần bảo đảm check path phản ánh readiness phù hợp và chu kỳ check không tạo khoảng trễ quá lớn. Với ZooKeeper, registration thường gắn với session/ephemeral node; việc session còn tồn tại không tự chứng minh ứng dụng sẵn sàng xử lý request.

Nguyên tắc chung: trạng thái registry, readiness của instance và kết quả health check có thể có độ trễ hoặc ngữ nghĩa khác nhau. Hãy xác định nguồn nào quyết định routing cuối cùng.

## 9. Startup, warm-up và thời điểm đăng ký

Một ứng dụng thường trải qua các giai đoạn:

1. Process/container được tạo.
2. JVM và Spring ApplicationContext khởi động.
3. Bean, cấu hình và connection pool được khởi tạo.
4. Ứng dụng warm-up cache hoặc tải dữ liệu cần thiết.
5. Readiness chuyển sang ACCEPTING_TRAFFIC.
6. Instance được đưa vào tập endpoint nhận traffic.
7. Ứng dụng phục vụ request.

Không phải registry nào cũng tự đợi readiness trước khi đăng ký. Một Eureka Client có thể đăng ký instance khi application context hoàn tất một phần lifecycle, trong khi ứng dụng vẫn đang warm-up. Nếu registry nhận instance quá sớm, consumer có thể chọn endpoint chưa phục vụ được.

Các cách đồng bộ:

- Dùng readiness probe để Kubernetes không đưa Pod vào Service endpoints trước khi sẵn sàng.
- Cấu hình registry health integration nếu muốn registry cũng loại instance chưa ready.
- Điều khiển auto-registration hoặc registration lifecycle khi ứng dụng có yêu cầu khởi động đặc biệt.
- Chỉ chuyển ReadinessState sang ACCEPTING_TRAFFIC sau khi các điều kiện bắt buộc đã hoàn tất.
- Với cache warm-up, đo thời gian và đặt startupProbe đủ rộng thay vì hạ readiness threshold quá thấp.

Không dùng sleep cố định làm cơ chế readiness. Một khoảng chờ có thể quá ngắn trong môi trường chậm và lãng phí trong môi trường nhanh. Hãy kiểm tra điều kiện thực tế.

## 10. Graceful shutdown và draining

Readiness không chỉ quan trọng lúc startup. Khi ứng dụng chuẩn bị dừng, cần ngừng nhận request mới trước khi đóng listener hoặc giải phóng tài nguyên.

Một trình tự shutdown an toàn:

1. Chuyển readiness sang REFUSING_TRAFFIC.
2. Chờ Kubernetes/registry/load balancer cập nhật endpoint.
3. Ngừng nhận request mới và cho request đang chạy hoàn tất trong giới hạn.
4. Deregister instance khỏi registry nếu registry integration yêu cầu.
5. Đóng connection pool, consumer và tài nguyên ứng dụng.
6. Kết thúc process trước khi termination grace period hết.

Spring Boot hỗ trợ graceful shutdown:

~~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~~

Trong Kubernetes, đặt `terminationGracePeriodSeconds` đủ dài để bao gồm thời gian preStop hook, endpoint propagation và shutdown phase. Ví dụ:

~~~~yaml
spec:
  terminationGracePeriodSeconds: 45
~~~~

Các con số phải được điều chỉnh theo thời gian request dài nhất và thời gian cập nhật routing. Graceful shutdown của Spring Boot giúp ngừng nhận kết nối mới theo cơ chế server hỗ trợ, nhưng không tự bảo đảm registry, ingress, service mesh và mọi consumer đều đã ngừng gửi request. Cần kiểm thử toàn bộ đường đi.

## 11. Không lạm dụng health check

Một health endpoint tốt cần nhanh, ổn định và có ý nghĩa rõ ràng. Một số lỗi thiết kế thường gặp:

- **Liveness kiểm tra database:** database tạm lỗi làm tất cả pod restart, tạo restart storm.
- **Readiness kiểm tra mọi dependency:** một hệ thống phụ trợ không quan trọng khiến toàn bộ service bị loại khỏi routing.
- **Probe endpoint quá nặng:** health check thực hiện truy vấn lớn hoặc gọi nhiều dịch vụ ngoài, làm tăng tải đúng lúc hệ thống yếu.
- **Dùng management port riêng mà không hiểu giới hạn:** management server vẫn trả lời dù main HTTP server không hoạt động.
- **Dùng cùng một endpoint cho mọi probe:** liveness và readiness có mục đích khác nhau; dùng chung endpoint tổng hợp có thể dẫn đến restart không cần thiết.
- **Probe quá nhạy:** timeout hoặc failure threshold quá thấp khiến một spike ngắn gây restart hoặc loại endpoint.
- **Health check không có authentication boundary:** endpoint lộ thông tin nội bộ hoặc bị gọi quá mức từ bên ngoài.

Health endpoint nên trả trạng thái tối thiểu cần thiết, không trả stack trace, secret, connection string hoặc thông tin nhạy cảm. Giới hạn exposure và network access theo môi trường.

## 12. Ma trận xử lý tình huống

| Tình huống | Liveness | Readiness | Serving capability |
| --- | --- | --- | --- |
| JVM đang startup | Chưa đánh giá cho tới khi startup probe thành công nếu đã cấu hình | REFUSING_TRAFFIC | Chưa phục vụ request |
| JVM hoạt động, cache bắt buộc chưa warm-up | CORRECT | REFUSING_TRAFFIC | Chưa nhận traffic mới |
| Database bắt buộc bị mất kết nối | Thường vẫn CORRECT | Có thể REFUSING_TRAFFIC nếu không thể phục vụ request nào cần DB | Request phụ thuộc DB lỗi; operation khác có thể còn hoạt động |
| Email provider lỗi | CORRECT | Thường vẫn ACCEPTING_TRAFFIC nếu API chính còn phục vụ được | Operation gửi email dùng retry/outbox hoặc trả lỗi riêng |
| Một endpoint nghiệp vụ lỗi | CORRECT | Thường vẫn ACCEPTING_TRAFFIC | Endpoint đó trả lỗi có kiểm soát |
| Worker quan trọng deadlock, app không thể xử lý công việc | Có thể BROKEN nếu ứng dụng phát hiện trạng thái không thể phục hồi | REFUSING_TRAFFIC | Request liên quan không thể phục vụ |
| Instance đang graceful shutdown | CORRECT cho tới khi process kết thúc | REFUSING_TRAFFIC | Không nhận request mới, hoàn tất request đang chạy |
| Thread pool bão hòa tạm thời | Thường vẫn CORRECT | Có thể chuyển REFUSING_TRAFFIC theo ngưỡng và thời gian ổn định | Backpressure, 429/503 hoặc queue giới hạn |

Ma trận chỉ là gợi ý. Trạng thái cụ thể phải theo hợp đồng của service, cách phục hồi và tác động nếu instance bị restart hoặc loại khỏi routing.

## 13. Quan sát và kiểm thử

Theo dõi riêng các tín hiệu sau:

- Số lần liveness probe thất bại và số lần container restart.
- Số lần readiness chuyển giữa ACCEPTING_TRAFFIC và REFUSING_TRAFFIC.
- Thời gian từ process start đến readiness.
- Số endpoint ready trong Kubernetes Service/EndpointSlice hoặc registry.
- Request rate, error rate, latency và saturation theo từng endpoint.
- Connection pool, thread pool, queue depth và trạng thái dependency.
- Số request đang chạy trong thời điểm shutdown/draining.

Các kịch bản kiểm thử:

| Kịch bản | Kết quả cần xác nhận |
| --- | --- |
| Khởi động chậm | startupProbe bảo vệ container khỏi bị restart quá sớm; readiness chỉ thành công sau warm-up. |
| Database tạm ngừng | Liveness không restart pod chỉ vì DB lỗi; readiness phản ánh đúng khả năng phục vụ theo hợp đồng service. |
| Một dependency tùy chọn lỗi | Service vẫn nhận traffic nếu các operation chính còn phục vụ được. |
| Main HTTP server bị treo | Probe trên cổng ứng dụng phát hiện lỗi thay vì chỉ kiểm tra management port riêng. |
| Thread pool bão hòa | Backpressure/metrics phản ánh saturation; readiness chỉ đổi theo policy đã thiết kế. |
| Rolling update | Pod mới chỉ nhận traffic sau readiness; pod cũ ngừng nhận request mới trước khi shutdown. |
| Graceful shutdown | Request đang chạy được drain trong thời gian cho phép và instance được loại khỏi routing. |

Không chỉ kiểm tra HTTP status của health endpoint. Hãy xác nhận tác động thực tế đến Kubernetes endpoints, registry, load balancer và request từ consumer.

## 14. Checklist thiết kế

- [ ] Liveness chỉ phản ánh lỗi nội bộ cần restart để phục hồi.
- [ ] Không đưa database hoặc external service vào liveness một cách mặc định.
- [ ] Readiness phản ánh các điều kiện tối thiểu để instance nhận request mới.
- [ ] Không để một dependency tùy chọn làm toàn bộ replica NOT_READY.
- [ ] Serving capability được xử lý theo từng operation bằng timeout, circuit breaker, backpressure và lỗi phù hợp.
- [ ] Bật Spring Boot Actuator probes và expose endpoint theo chính sách.
- [ ] Dùng startupProbe cho ứng dụng khởi động chậm.
- [ ] Kiểm tra probe qua main server port nếu cần xác minh đường HTTP thực tế.
- [ ] Đồng bộ readiness với Kubernetes Service hoặc registry nếu muốn điều khiển routing.
- [ ] Kiểm tra HealthCheckHandler khi tích hợp Eureka.
- [ ] Đưa instance sang REFUSING_TRAFFIC trước graceful shutdown.
- [ ] Đặt termination grace period đủ cho endpoint propagation và request draining.
- [ ] Kiểm thử lỗi dependency, startup chậm, process hang, saturation và rolling update.
- [ ] Theo dõi liveness, readiness và kết quả request thành các tín hiệu riêng.

## Ghi nhớ

- Liveness hỏi process có nên tiếp tục chạy; readiness hỏi instance có nên nhận traffic mới; serving capability hỏi operation cụ thể có thể hoàn thành hay không.
- Kubernetes restart container khi liveness thất bại liên tục; readiness thất bại chỉ làm instance không sẵn sàng nhận traffic thông thường.
- Spring Boot biểu diễn trạng thái bằng LivenessState và ReadinessState, đồng thời cung cấp health group cho Actuator.
- Không đưa mọi dependency bên ngoài vào liveness; điều đó có thể gây restart storm.
- Readiness nên phản ánh khả năng phục vụ cốt lõi, không phải mọi chức năng tùy chọn.
- Registry và readiness có thể không đồng bộ tự động; cần cấu hình tích hợp phù hợp.
- Khi shutdown, chuyển sang REFUSING_TRAFFIC và drain request trước khi đóng tài nguyên.
- Health probe là tín hiệu vận hành; kết quả request, metrics và tracing vẫn cần thiết để đánh giá khả năng phục vụ thật.

## Tài liệu tham khảo chính thức

- [Spring Boot – Actuator: Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot – Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot – Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Kubernetes – Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes – Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Spring Cloud Netflix – Eureka Health Checks](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Commons – Service Registry](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
