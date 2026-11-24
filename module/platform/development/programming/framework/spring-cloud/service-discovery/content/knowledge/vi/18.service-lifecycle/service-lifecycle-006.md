# Rút lưu lượng, chờ yêu cầu đang chạy và tắt ứng dụng êm

Khi triển khai phiên bản mới, bảo trì hoặc thay thế một instance microservice, chỉ gửi lệnh dừng tiến trình là chưa đủ. Consumer có thể vẫn nhìn thấy instance trong registry và tiếp tục gửi request tới nó; request đang xử lý có thể bị ngắt giữa chừng; message consumer hoặc tác vụ nền có thể mất công việc chưa hoàn tất.

Quy trình shutdown an toàn cần thực hiện theo thứ tự: đưa instance ra khỏi luồng nhận traffic, chờ trạng thái đó lan tới registry và các bộ định tuyến, ngừng nhận công việc mới, đợi công việc đang chạy hoàn tất trong giới hạn thời gian, rồi mới đóng ApplicationContext và tiến trình. Spring Boot hỗ trợ graceful shutdown cho embedded web server; Spring Cloud và registry cung cấp cơ chế đánh dấu hoặc hủy đăng ký instance; nền tảng triển khai phải cấp đủ thời gian cho toàn bộ quy trình.

## 1. Ba việc khác nhau trong quá trình dừng service

Cần phân biệt ba mục tiêu:

| Mục tiêu | Việc cần làm | Kết quả mong muốn |
|---|---|---|
| Rút lưu lượng (traffic drain) | Đánh dấu instance không nhận request mới trong registry, readiness hoặc load balancer | Consumer ngừng chọn instance đó |
| Chờ công việc đang chạy (in-flight drain) | Ngừng nhận request/job mới và chờ request, tác vụ hiện tại hoàn tất | Không cắt ngang xử lý đang diễn ra |
| Tắt ứng dụng êm (graceful shutdown) | Gửi SIGTERM, đóng server và các bean theo lifecycle với timeout | Tài nguyên được giải phóng có trật tự |

Ba việc có liên quan nhưng không thay thế cho nhau. Đánh dấu OUT_OF_SERVICE không tự đợi request hiện tại hoàn tất. Graceful shutdown của web server không tự bảo đảm registry đã ngừng quảng bá instance. Deregister chỉ xóa registration, không tự dừng tiến trình hoặc hoàn tất công việc nền.

## 2. Trình tự shutdown tổng thể

Một quy trình rolling deployment có thể diễn ra như sau:

    Bản triển khai mới
          |
          v
    Khởi động instance mới
          |
          v
    Instance mới health/readiness đạt
          |
          v
    Đánh dấu instance cũ không nhận traffic
          |
          v
    Registry và LoadBalancer cập nhật danh sách
          |
          v
    Ngừng nhận request và công việc mới
          |
          v
    Chờ request/job đang chạy hoàn tất
          |
          v
    Gửi SIGTERM cho instance cũ
          |
          v
    Spring Boot graceful shutdown
          |
          v
    Deregister và giải phóng tài nguyên
          |
          v
    Tiến trình kết thúc

Trong triển khai rolling, nên bảo đảm instance mới đã sẵn sàng trước khi rút instance cũ. Nếu rút instance cũ trước khi có capacity thay thế, hệ thống có thể thiếu khả năng phục vụ trong khoảng thời gian cập nhật registry.

Sau khi đánh dấu instance không nhận traffic, cần chờ registry, cache của DiscoveryClient, cache của LoadBalancer và các proxy liên quan cập nhật. Không có một khoảng chờ cố định áp dụng cho mọi hệ thống. Hãy quan sát trạng thái registry và lưu lượng thực tế từ consumer.

## 3. Readiness khác với liveness và health tổng thể

Spring Boot có hai trạng thái availability quan trọng:

- Liveness cho biết tiến trình còn ở trạng thái có thể tiếp tục hoạt động hay cần được khởi động lại.
- Readiness cho biết ứng dụng có sẵn sàng nhận traffic mới hay không.

Khi bắt đầu drain, ứng dụng nên chuyển readiness sang REFUSING_TRAFFIC. Liveness vẫn có thể là CORRECT vì tiến trình vẫn hoạt động và cần thời gian hoàn tất các request hiện tại.

Có thể bật health probes trong application.yml:

    management:
      endpoint:
        health:
          probes:
            enabled: true
      endpoints:
        web:
          exposure:
            include: health,info

Spring Boot cung cấp các endpoint:

    /actuator/health/liveness
    /actuator/health/readiness

Readiness probe phải được load balancer hoặc nền tảng triển khai sử dụng. Chỉ expose endpoint readiness không tự động khiến Eureka, Consul hoặc một proxy bất kỳ ngừng gửi traffic. Cần tích hợp probe với thành phần định tuyến tương ứng.

## 4. Chủ động chuyển readiness sang REFUSING_TRAFFIC

Spring Boot cho phép thay đổi trạng thái readiness bằng AvailabilityChangeEvent. Có thể xây dựng một endpoint quản trị nội bộ để bắt đầu drain:

    import org.springframework.boot.availability.AvailabilityChangeEvent;
    import org.springframework.boot.availability.ReadinessState;
    import org.springframework.context.ApplicationEventPublisher;
    import org.springframework.http.ResponseEntity;
    import org.springframework.web.bind.annotation.PostMapping;
    import org.springframework.web.bind.annotation.RequestMapping;
    import org.springframework.web.bind.annotation.RestController;

    @RestController
    @RequestMapping("/internal/lifecycle")
    public class LifecycleController {

        private final ApplicationEventPublisher publisher;

        public LifecycleController(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @PostMapping("/drain")
        public ResponseEntity<Void> drain() {
            AvailabilityChangeEvent.publish(
                    publisher,
                    this,
                    ReadinessState.REFUSING_TRAFFIC
            );
            return ResponseEntity.accepted().build();
        }
    }

Sau khi gọi endpoint này, health group readiness phản ánh trạng thái không nhận traffic. Thành phần giám sát có thể quan sát readiness chuyển sang OUT_OF_SERVICE hoặc DOWN tùy cách health status được ánh xạ.

Endpoint drain phải được bảo vệ bằng authentication, authorization và giới hạn mạng truy cập. Không expose endpoint quản trị này công khai. Cần thiết kế thao tác idempotent để gọi lặp lại không làm hỏng lifecycle.

Chuyển readiness chỉ tác động tới những thành phần thực sự kiểm tra readiness. Nếu consumer gọi trực tiếp qua Eureka hoặc Consul, cần cập nhật trạng thái registry hoặc cấu hình health integration phù hợp.

## 5. Đưa instance ra khỏi registry

### Eureka

Eureka hỗ trợ trạng thái OUT_OF_SERVICE. Instance vẫn có registration nhưng không được trả về như một instance đang hoạt động trong các truy vấn discovery thông thường.

Spring Cloud Commons cung cấp Service Registry Actuator endpoint. Có thể expose endpoint trong application.yml:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,serviceregistry

Đọc trạng thái hiện tại:

    curl http://localhost:8080/actuator/serviceregistry

Đưa instance ra khỏi traffic:

    curl -X POST http://localhost:8080/actuator/serviceregistry \
      -H "Content-Type: application/json" \
      -d "{\"status\":\"OUT_OF_SERVICE\"}"

Sau khi drain và bảo trì xong, khôi phục trạng thái UP nếu instance vẫn còn chạy:

    curl -X POST http://localhost:8080/actuator/serviceregistry \
      -H "Content-Type: application/json" \
      -d "{\"status\":\"UP\"}"

Các giá trị trạng thái phụ thuộc ServiceRegistry implementation và phiên bản Spring Cloud. Với Eureka, OUT_OF_SERVICE là trạng thái được hỗ trợ. Cần đọc lại trạng thái bằng GET và kiểm tra danh sách instance mà consumer nhận được.

Spring Cloud Netflix cũng hỗ trợ actuator pause/resume. Khi các endpoint này được bật, gọi /actuator/pause đưa Eureka instance sang OUT_OF_SERVICE; /actuator/resume gỡ override để instance trở lại trạng thái do ứng dụng báo sau heartbeat tiếp theo. Kiểm tra cấu hình exposure và bảo mật của endpoint trước khi sử dụng.

### Consul

Consul có thể đưa một service vào maintenance mode theo ServiceID. Khi maintenance được bật, service được đánh dấu không khả dụng và bị loại khỏi kết quả DNS/API phù hợp.

Agent API:

    curl -X PUT \
      "http://localhost:8500/v1/agent/service/maintenance/inventory-service-8080?enable=true&reason=planned-drain"

Khi muốn đưa service trở lại:

    curl -X PUT \
      "http://localhost:8500/v1/agent/service/maintenance/inventory-service-8080?enable=false"

Thay inventory-service-8080 bằng ServiceID thực tế. Agent API yêu cầu quyền ACL service:write. Không nhầm ServiceID của instance với service name dùng để truy vấn.

Nếu consumer dùng Spring Cloud Consul, có thể bật query-passing để chỉ nhận các instance có health check passing:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true

Maintenance mode và health check là hai tín hiệu riêng. Maintenance chủ động đưa service ra khỏi pool; health check phản ánh kết quả kiểm tra endpoint. Cần xác minh trạng thái trong Consul và kết quả truy vấn health service trước khi dừng tiến trình.

### Khác biệt giữa OUT_OF_SERVICE và deregister

OUT_OF_SERVICE hoặc maintenance giữ registration nhưng đánh dấu service không nên nhận traffic. Deregister xóa registration khỏi registry. Trong quy trình bảo trì một instance sẽ được khởi động lại, có thể dùng trạng thái out-of-service trước rồi để lifecycle deregister khi ứng dụng đóng. Nếu instance sẽ tiếp tục chạy sau bảo trì, cần đưa nó trở lại UP hoặc tắt maintenance mode sau khi readiness đạt.

## 6. Chờ registry và consumer ngừng gửi request

Sau khi cập nhật trạng thái, không nên dừng tiến trình ngay lập tức. Cần chờ trạng thái mới lan tới các thành phần có thể chọn instance:

- Registry server hoặc Consul Catalog nhận thay đổi.
- Eureka client hoặc Consul Discovery client của consumer cập nhật danh sách.
- Cache của Spring Cloud LoadBalancer làm mới.
- Gateway, reverse proxy hoặc service mesh cập nhật endpoint pool.
- Consumer không còn chọn instance cũ cho request mới.

Độ trễ phụ thuộc heartbeat, registry fetch interval, response cache, health-check interval, client cache và cấu hình load balancer. Persistent connection hoặc keep-alive cũng có thể làm request tiếp tục đi qua một kết nối đã được thiết lập.

Cách xác minh tốt nhất là quan sát traffic thực tế và danh sách instance từ phía consumer. Có thể dùng metric request theo instance, access log, dashboard load balancer hoặc một endpoint kiểm tra discovery. Chỉ chờ một số giây tùy ý mà không xác minh có thể khiến request mới vẫn tới instance đang chuẩn bị dừng.

Nếu hệ thống có nhiều lớp cache, hãy xác định lớp nào quyết định lựa chọn instance và chu kỳ làm mới của lớp đó. Retry từ consumer cũng cần được tính đến vì request có thể được gửi lại tới instance khác sau khi lần gọi đầu thất bại.

## 7. Chờ HTTP request đang chạy hoàn tất

Sau khi instance không còn nhận traffic mới, cần cho các request hiện tại có thời gian kết thúc. Spring Boot graceful shutdown hỗ trợ embedded web server trong cả ứng dụng Servlet và Reactive.

Cấu hình rõ trong application.yml:

    server:
      shutdown: graceful

    spring:
      lifecycle:
        timeout-per-shutdown-phase: 45s

Khi ApplicationContext bắt đầu đóng, Spring Boot khởi động graceful shutdown ở giai đoạn dừng SmartLifecycle. Web server ngừng nhận request mới theo cách triển khai của server và cho request đang xử lý hoàn tất trong grace period.

Với Tomcat, Jetty và Reactor Netty, server ngừng nhận request mới ở network layer trong graceful shutdown. Cách xử lý kết nối mới có thể khác theo server và phiên bản. Undertow ở các phiên bản được hỗ trợ có thể vẫn nhận kết nối nhưng trả HTTP 503 trong giai đoạn shutdown.

spring.lifecycle.timeout-per-shutdown-phase là giới hạn thời gian cho mỗi phase dừng lifecycle. Nếu request chưa hoàn tất khi hết thời gian, quá trình shutdown vẫn tiếp tục và công việc còn lại có thể bị ngắt. Vì vậy, timeout phải lớn hơn thời gian xử lý request bình thường và phù hợp với giới hạn termination của nền tảng.

Trong các phiên bản Spring Boot hiện hành, graceful shutdown được bật mặc định cho các embedded web server được hỗ trợ. Khai báo rõ server.shutdown=graceful giúp ý định cấu hình dễ nhận biết và cần kiểm tra lại theo phiên bản Boot cùng server đang sử dụng.

## 8. Chọn timeout dựa trên thời gian xử lý thực tế

Không nên đặt timeout quá ngắn chỉ để rollout nhanh. Nếu request thông thường có thể mất 20 giây và một số request hợp lệ mất 40 giây, timeout 10 giây sẽ khiến request bị cắt khi shutdown.

Có thể dùng bảng sau làm điểm khởi đầu:

| Loại workload | Cần đo | Điều cần cân nhắc |
|---|---|---|
| REST API ngắn | p95/p99 latency và request đang hoạt động | Grace period lớn hơn thời gian xử lý dài hợp lệ |
| API báo cáo hoặc export | Thời gian tạo file và truyền response | Cân nhắc job bất đồng bộ hoặc tải file từ object storage |
| Streaming/SSE/WebSocket | Thời gian sống của connection | Cần giao thức báo reconnect hoặc đóng connection có kiểm soát |
| gRPC streaming | Thời gian stream và chính sách reconnect | Drain stream, gửi trạng thái kết thúc và chờ client chuyển kết nối |
| Tác vụ nền | Thời gian xử lý một job và checkpoint | Dừng nhận job mới, hoàn tất hoặc trả job về queue an toàn |

Các request kéo dài vô hạn không thể được bảo đảm hoàn tất chỉ bằng một timeout shutdown. Cần có giới hạn request, cancellation protocol, checkpoint hoặc cơ chế resume để tránh mất dữ liệu.

## 9. Dừng tác vụ nền và message consumer

Graceful shutdown của embedded web server tập trung vào HTTP server. Nó không tự động bảo đảm mọi scheduler, executor, message listener hoặc consumer bên ngoài ngừng nhận việc mới đúng thời điểm.

Với worker hoặc message consumer, quy trình nên là:

1. Tạm dừng polling hoặc nhận message mới.
2. Chờ các message đã nhận được xử lý hoàn tất.
3. Acknowledge hoặc commit offset sau khi xử lý thành công.
4. Nếu không thể hoàn tất trong grace period, trả message về cơ chế retry/requeue hoặc để hệ thống giao lại theo semantics của broker.
5. Dừng scheduler, executor và các listener container.
6. Đóng connection và giải phóng tài nguyên.

Không commit offset trước khi xử lý thành công nếu điều đó có thể làm mất message. Với tác vụ không idempotent, cần thiết kế idempotency key hoặc cơ chế deduplication để xử lý trường hợp client retry sau khi instance cũ bị dừng.

Các bean quản lý công việc nền có thể triển khai SmartLifecycle để nhận tín hiệu stop và gọi callback khi đã hoàn tất. Cần thiết kế phase phù hợp để producer ngừng phát việc trước consumer hoặc worker đóng tài nguyên mà chúng còn cần dùng.

## 10. Consul deregistration khi Spring Boot dừng

Spring Cloud Consul tự đăng ký service theo lifecycle khi discovery được bật. Thuộc tính spring.cloud.consul.discovery.deregister mặc định cho phép tự động hủy đăng ký service khi lifecycle dừng.

Có thể khai báo rõ:

    spring:
      cloud:
        consul:
          discovery:
            register: true
            deregister: true

Khi ứng dụng shutdown bình thường, Spring Cloud Consul gửi yêu cầu deregister tới Consul Agent. Service và các check liên quan được gỡ khỏi registration của agent và đồng bộ với catalog.

Thứ tự chính xác giữa graceful web-server shutdown và bước deregister do các lifecycle phase của phiên bản Spring Cloud/Spring Boot quyết định. Không giả định rằng deregister luôn hoàn tất trước khi server ngừng nhận kết nối. Vì vậy, hãy đưa instance ra khỏi traffic bằng thao tác drain tường minh trước khi gửi SIGTERM; deregistration trong shutdown là bước kết thúc registration.

Nếu ứng dụng bị kill cưỡng bức, máy chủ mất điện hoặc Consul Agent không thể truy cập, thao tác deregister có thể không hoàn tất. Khi đó health check và health-check-critical-timeout của Consul là cơ chế dự phòng để phát hiện và dọn registration lỗi kéo dài.

Nếu đặt deregister=false, cần có một quy trình bên ngoài chịu trách nhiệm dọn registration. Không tắt tự động deregister nếu chưa có cơ chế thay thế đã được kiểm thử.

## 11. Eureka deregistration và trạng thái OUT_OF_SERVICE

Eureka nhận heartbeat định kỳ từ client. Khi instance dừng bình thường, Eureka client có thể hủy đăng ký trong lifecycle shutdown. Khi muốn rút instance khỏi traffic trước khi đóng ứng dụng, hãy chủ động đặt OUT_OF_SERVICE qua ServiceRegistry endpoint hoặc cơ chế pause của Spring Cloud Netflix.

Hai thao tác có ý nghĩa khác nhau:

- OUT_OF_SERVICE: giữ registration nhưng không coi instance là endpoint đang phục vụ.
- Deregister: xóa registration khỏi Eureka Server.

Không nên chỉ trông chờ lease hết hạn để rút lưu lượng trong một deployment có kế hoạch. Lease expiration là cơ chế phát hiện instance mất heartbeat; nó không phải quy trình drain có chủ đích. Hãy xác minh Eureka Dashboard và kết quả discovery từ consumer trước khi dừng tiến trình.

## 12. Kubernetes: preStop và terminationGracePeriodSeconds

Kubernetes gửi SIGTERM tới process trong container khi Pod bắt đầu kết thúc. Kubelet chờ trong khoảng termination grace period; khi hết thời gian, process còn chạy sẽ bị SIGKILL.

preStop hook chạy trước khi gửi SIGTERM và thời gian hook cũng được tính vào termination grace period. Có thể dùng hook để gọi endpoint drain nội bộ trước khi Spring Boot nhận tín hiệu dừng.

Ví dụ cấu hình minh họa:

    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: order-service
          image: example/order-service
          lifecycle:
            preStop:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - "curl -fsS -X POST http://127.0.0.1:8080/internal/lifecycle/drain; sleep 10"

Trong ví dụ, image cần có curl. Endpoint drain chuyển readiness sang REFUSING_TRAFFIC. Khoảng chờ 10 giây chỉ là giá trị minh họa để cho EndpointSlice, ingress hoặc load balancer cập nhật; cần thay bằng thời gian đã đo trong cluster thực tế.

Pod readiness probe có thể dùng:

    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      failureThreshold: 1

Nếu management server dùng port riêng, readiness probe phải gọi đúng port đó. Nếu endpoint drain nằm trên application port, preStop phải gọi đúng địa chỉ và port của application server.

terminationGracePeriodSeconds phải lớn hơn tổng thời gian preStop, thời gian drain request và các bước đóng tài nguyên, cộng thêm một khoảng dự phòng. Ví dụ preStop chờ 10 giây, Spring Boot có shutdown phase 45 giây, còn 35 giây dự phòng trong tổng 90 giây. Nếu timeout thực tế vượt ngân sách, Kubernetes sẽ gửi SIGKILL và request có thể bị ngắt.

Kubernetes cập nhật EndpointSlice và đánh dấu terminating endpoint không còn ready cho traffic thông thường. Quá trình cập nhật tới ingress hoặc load balancer có độ trễ; do đó ứng dụng vẫn nên phối hợp readiness và drain thay vì giả định mọi consumer dừng gửi request tức thì.

## 13. Docker và tín hiệu SIGTERM

Khi chạy Docker, lệnh docker stop gửi tín hiệu dừng tới process chính rồi chờ theo stop timeout trước khi cưỡng bức kết thúc container. Có thể đặt thời gian chờ trong Docker Compose:

    services:
      order-service:
        image: example/order-service
        stop_grace_period: 90s

Bảo đảm JVM là process chính hoặc entrypoint chuyển tiếp SIGTERM đúng cách. Nếu shell script khởi chạy Java mà không dùng exec, tín hiệu có thể không được chuyển tới JVM như mong đợi.

Ví dụ entrypoint:

    #!/bin/sh
    exec java -jar app.jar

Không dùng docker kill hoặc SIGKILL cho shutdown thông thường. SIGKILL không cho JVM chạy shutdown hook, không chờ request và không thực hiện deregistration qua lifecycle.

## 14. Tính ngân sách thời gian shutdown

Toàn bộ quy trình cần có một ngân sách thời gian nhất quán:

    Termination grace period
      >= preStop/drain trigger
       + registry/load balancer propagation
       + in-flight request drain
       + background task drain
       + Spring lifecycle shutdown
       + safety buffer

Một ví dụ minh họa:

| Giai đoạn | Thời gian dự kiến |
|---|---:|
| Gọi endpoint drain và đánh dấu readiness | 1 giây |
| Chờ routing/registry cập nhật | 10 giây |
| Chờ HTTP request và background task | 35 giây |
| Spring lifecycle shutdown | 20 giây |
| Dự phòng | 14 giây |
| Tổng termination budget | 80 giây |

Các giai đoạn có thể chồng lấn tùy thiết kế; bảng là ngân sách lập kế hoạch, không phải timeline cố định của Spring Boot. Cần đo thời gian thực tế ở môi trường triển khai và bảo đảm timeout của nền tảng lớn hơn thời gian ứng dụng cần.

Nếu spring.lifecycle.timeout-per-shutdown-phase là 45 giây nhưng Kubernetes chỉ cho 30 giây, kubelet có thể SIGKILL ứng dụng trước khi Spring hoàn tất. Nếu preStop chiếm 20 giây, phần thời gian còn lại cho SIGTERM và graceful shutdown sẽ ngắn hơn tương ứng.

## 15. Kiểm chứng quy trình drain

Một bài kiểm thử nên mô phỏng cả request ngắn và request dài:

1. Khởi động ít nhất hai instance của cùng một service.
2. Gửi request liên tục qua LoadBalancer hoặc gateway để xác nhận traffic đang phân phối.
3. Bắt đầu drain một instance bằng endpoint nội bộ hoặc thao tác registry.
4. Kiểm tra trạng thái readiness, Eureka/Consul và danh sách instance consumer nhận được.
5. Xác nhận request mới chuyển sang instance còn lại.
6. Tạo một request dài trên instance đang drain và ghi nhận nó hoàn tất trước khi process thoát.
7. Gửi SIGTERM và theo dõi log lifecycle, thời điểm server đóng và deregistration.
8. Kiểm tra registry không còn instance cũ và consumer không tiếp tục chọn địa chỉ đó.
9. Lặp lại với một message consumer hoặc tác vụ nền đang chạy.
10. Thử trường hợp request vượt quá timeout để xác nhận hệ thống xử lý timeout, retry và dữ liệu dở dang an toàn.

Nên ghi timestamp cho các mốc: bắt đầu drain, readiness chuyển trạng thái, registry cập nhật, request cuối cùng bắt đầu, request cuối cùng kết thúc, SIGTERM nhận được và process thoát. Các mốc này giúp điều chỉnh termination budget bằng số liệu thay vì phỏng đoán.

## 16. Lỗi thường gặp khi shutdown

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Request mới vẫn tới instance đang dừng | Chưa cập nhật registry/readiness hoặc cache chưa refresh | Rút instance khỏi traffic trước SIGTERM và xác minh consumer |
| Request đang xử lý bị reset | Grace period quá ngắn hoặc dùng SIGKILL | Tăng timeout và đo p99/thời gian xử lý dài |
| Eureka vẫn hiển thị instance | Chưa đặt OUT_OF_SERVICE hoặc client chưa deregister | Kiểm tra ServiceRegistry status, heartbeat và shutdown log |
| Consul vẫn giữ registration | Agent không nhận deregister hoặc deregister bị tắt | Kiểm tra lifecycle, ACL và health-check-critical-timeout |
| Readiness DOWN nhưng traffic vẫn tới | Load balancer không dùng readiness hoặc gọi trực tiếp registry khác | Tích hợp readiness với đúng tầng định tuyến |
| Message bị xử lý hai lần | Consumer bị dừng trước khi ack/commit hoặc retry không idempotent | Thiết kế ack sau xử lý, idempotency và deduplication |
| Kubernetes kill process trước khi hoàn tất | terminationGracePeriodSeconds ngắn hơn tổng shutdown budget | Tăng grace period hoặc giảm thời gian drain có kiểm soát |
| Docker không gửi SIGTERM tới JVM | Shell entrypoint không chuyển tiếp tín hiệu | Dùng exec để JVM nhận tín hiệu trực tiếp |
| WebSocket/SSE bị ngắt đột ngột | Connection tồn tại lâu hơn grace period | Có thông báo reconnect, resume token hoặc giới hạn thời gian connection |

## 17. Bảo mật endpoint drain và thao tác registry

Endpoint drain, pause/resume và ServiceRegistry có thể làm instance ngừng nhận traffic. Người không có quyền nếu gọi được có thể gây gián đoạn dịch vụ.

Cần:

- Chỉ expose endpoint quản trị trong mạng nội bộ.
- Bảo vệ bằng authentication và role phù hợp.
- Giới hạn quyền thay đổi trạng thái; quyền GET và POST không nhất thiết giống nhau.
- Dùng ACL token có phạm vi hẹp khi gọi Consul Agent API.
- Ghi audit log gồm instance ID, trạng thái cũ/mới, người thực hiện, thời điểm và lý do.
- Không nhúng token thật vào script, command history hoặc repository.
- Kiểm tra trạng thái trước và sau khi drain để tránh tác động nhầm instance.

Endpoint drain nên idempotent: gọi nhiều lần vẫn giữ instance ở trạng thái không nhận traffic. Endpoint resume chỉ được dùng sau khi ứng dụng và dependency đã sẵn sàng phục vụ trở lại.

## 18. Kết luận

Một lần shutdown an toàn gồm ba bước phối hợp: rút instance khỏi traffic, chờ request và công việc đang chạy hoàn tất, rồi đóng ứng dụng bằng graceful shutdown. Readiness và registry status giúp consumer ngừng chọn instance; Spring Boot graceful shutdown bảo vệ request đang xử lý trong thời gian chờ; ServiceRegistry và provider thực hiện status update hoặc deregistration.

Trong rolling deployment, hãy khởi động và xác nhận instance thay thế trước, đánh dấu instance cũ không nhận traffic, chờ registry và load balancer cập nhật, drain HTTP cùng message/job đang chạy, sau đó gửi SIGTERM. Cấu hình timeout của Spring Boot, preStop và termination grace period phải được tính chung. Cuối cùng, xác minh registry, traffic và log shutdown để bảo đảm instance đã rời hệ thống theo đúng kế hoạch.

## Tài liệu tham khảo

- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — Application Availability and Readiness](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Actuator Health Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Cloud Commons — ServiceRegistry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Netflix — Eureka Client Pause and Resume](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Consul — Service Agent HTTP API and Maintenance Mode](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Kubernetes — Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)

