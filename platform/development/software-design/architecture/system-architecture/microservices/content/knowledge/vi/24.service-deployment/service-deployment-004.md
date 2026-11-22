# Readiness, liveness và thời gian khởi động

## 1. Mục tiêu và phạm vi

Một service có thể **đang chạy tiến trình** nhưng chưa sẵn sàng nhận request: ứng dụng còn khởi tạo Spring context, kết nối cơ sở dữ liệu, tải cấu hình hoặc chờ cache thiết yếu. Ngược lại, một service có thể đang xử lý bình thường nhưng tạm thời mất kết nối tới nhà cung cấp bên ngoài. Nếu hệ thống triển khai nhầm hai trạng thái này, nó có thể gửi traffic quá sớm tới một Pod, khởi động lại hàng loạt instance khi dependency lỗi, hoặc triển khai phiên bản mới khiến toàn bộ service mất khả dụng.

Trong Kubernetes, các probe giúp nền tảng quan sát **ba câu hỏi khác nhau**:

1. **Startup:** container đã có đủ thời gian để khởi động xong chưa?
2. **Readiness:** instance hiện tại có nên nhận traffic mới không?
3. **Liveness:** tiến trình có đang ở trạng thái cần khởi động lại để hồi phục không?

Ba tín hiệu phục vụ ba quyết định khác nhau. Chúng không thay thế theo dõi transaction, tracing, SLO hay trạng thái nghiệp vụ. Một Pod §Ready§ không bảo đảm mọi yêu cầu sẽ thành công, một Pod §Live§ không chứng minh tất cả dependency đã khỏe, và một Pod chạy lâu không nhất thiết đã §Ready§.

Tài liệu tập trung vào triển khai microservices với Kubernetes và ứng dụng Java/Spring Boot. Các ví dụ YAML, endpoint và ngưỡng thời gian là minh họa; cần điều chỉnh theo runtime, phiên bản, workload và quan hệ phụ thuộc thực tế.

Sau bài này, bạn có thể:

- Phân biệt đúng mục đích, kết quả và hệ quả của từng loại probe.
- Thiết kế endpoint health phản ánh trạng thái phục vụ traffic, trạng thái tiến trình và quá trình khởi động.
- Tính ngân sách startup thực tế, tránh §CrashLoopBackOff§ hoặc rollout treo do probe quá nghiêm.
- Cấu hình §startupProbe§, §readinessProbe§, §livenessProbe§ với §periodSeconds§, §timeoutSeconds§, §failureThreshold§ và §successThreshold§ phù hợp.
- Kết hợp probe với rolling deployment, graceful shutdown, autoscaling và service discovery.
- Xác định dependency nào phải ảnh hưởng readiness, dependency nào không nên kéo theo restart.
- Kiểm thử tình huống khởi động chậm, dependency lỗi, deadlock, traffic drain và rolling update.
- Đo, cảnh báo và điều tra lỗi probe thay vì đoán nguyên nhân từ trạng thái §NotReady§.

## 2. Mô hình trạng thái: chạy, sống và sẵn sàng

Có ba khái niệm dễ bị trộn lẫn:

| Trạng thái | Ý nghĩa | Câu hỏi thực tế |
|---|---|---|
| Process/container running | Tiến trình chính còn hoạt động | PID 1 hoặc tiến trình ứng dụng có còn chạy không? |
| Live | Ứng dụng có khả năng tiếp tục tiến triển, hay cần restart? | Có deadlock/treo không thể tự hồi phục không? |
| Ready | Có đủ điều kiện để tiếp nhận yêu cầu mới? | Instance đã khởi tạo và có thể phục vụ phần traffic được phân công chưa? |

Một số trường hợp:

| Tình huống | Process | Liveness mong đợi | Readiness mong đợi | Hành động phù hợp |
|---|---|---|---|---|
| JVM đang tải class, khởi tạo ứng dụng | Running | Startup probe đang bảo vệ giai đoạn đầu | Chưa ready | Chờ khởi động |
| Application đã khởi tạo, chưa dựng cache bắt buộc | Running | Live | Not ready | Chưa route traffic |
| Bình thường, xử lý request được | Running | Live | Ready | Nhận traffic |
| DB chung lỗi trong vài giây, ứng dụng có cơ chế retry | Running | Live | Tùy contract phục vụ | Hạn chế traffic hoặc trả lỗi phù hợp, không tự động restart toàn bộ |
| Deadlock không có cách tự phục hồi | Running | Not live sau khi xác nhận | Thường không ready | Restart có điều kiện |
| Đang shutdown và drain kết nối | Running | Có thể còn live | Not ready | Ngừng route request mới, hoàn tất request cũ |
| Tiến trình đã thoát | Not running | Không còn endpoint | Không ready | Cơ chế restart controller/container áp dụng |

**Câu nhớ nhanh:** readiness quyết định *có nhận traffic mới*, liveness quyết định *có cần restart*, startup quyết định *có nên cho liveness/readiness kiểm tra ngay chưa*.

## 3. Hành vi thực tế của Kubernetes

Kubernetes cung cấp ba loại container probe, mỗi loại có thể được cấu hình theo HTTP, TCP, exec hoặc cơ chế gRPC phù hợp phiên bản/nền tảng.

### 3.1. Readiness probe

Khi readiness probe thất bại, container không bị restart chỉ vì readiness thất bại. Kubernetes cập nhật trạng thái Ready tương ứng, và Pod không còn được xem là endpoint sẵn sàng cho Service routing chuẩn. EndpointSlice/kube-proxy/Ingress và các thành phần phân phối traffic có thể cần thời gian hội tụ; **existing connection hoặc đường gửi trực tiếp tới Pod IP không nhất thiết biến mất tức thì**.

Readiness được kiểm tra trong suốt vòng đời chạy, sau khi startup probe (nếu có) thành công. Khi readiness phục hồi, Pod có thể được đánh dấu Ready trở lại.

Dùng readiness cho:

- Khởi động xong, dependency/khả năng cốt lõi đã ở trạng thái phù hợp để phục vụ.
- Ứng dụng đang chuẩn bị shutdown hoặc drain nên không muốn nhận traffic mới.
- Instance đang bảo trì nội bộ, warm-up cache bắt buộc hoặc bị cô lập do trạng thái riêng.
- Điều kiện truy cập an toàn tới dữ liệu/tài nguyên thuộc trách nhiệm instance.

Không dùng readiness để khẳng định hoàn tất workflow bất đồng bộ; đó là health của quy trình nghiệp vụ cần đo riêng.

### 3.2. Liveness probe

Liveness probe thất bại liên tiếp theo cấu hình có thể khiến kubelet **restart container**. Đây là hành động mạnh và có chi phí: JVM warm-up lại, mất cache, in-flight work bị gián đoạn, load dồn sang replica khác.

Liveness phù hợp khi restart thực sự có khả năng khôi phục tiến trình, chẳng hạn trạng thái ứng dụng bị treo không thể tự hồi phục. Nó thường **không nên phụ thuộc trực tiếp vào sự sống còn của database, broker, DNS hoặc PSP**. Nếu một DB chung lỗi và mọi Pod cùng fail liveness, cluster có thể rơi vào restart storm, vừa không sửa được DB vừa khiến service khó phục hồi.

Liveness không thay thế timeout, circuit breaker, backpressure, queue bounds hoặc logic phục hồi dependency.

### 3.3. Startup probe

§startupProbe§ dành cho container khởi động chậm. Khi startup probe được cấu hình, Kubernetes **chưa thực thi readiness và liveness probes cho tới khi startup probe thành công**. Nếu startup probe liên tiếp thất bại tới ngưỡng, kubelet restart container. Sau khi startup thành công, startup probe không còn dùng để đánh giá hoạt động bình thường.

Nó đặc biệt hữu ích cho:

- Java/Spring Boot khởi tạo Spring context lâu, JIT hoặc dependency injection phức tạp.
- Tải mô hình machine learning, rule engine hoặc plugin bắt buộc trước khi phục vụ.
- Chạy bootstrap có thời hạn rõ, tạo index/cấu trúc bộ nhớ.
- Ứng dụng cần warm-up dài hơn ngưỡng liveness thông thường.

Startup probe **không phải công tắc để bỏ qua lỗi khởi động vô hạn**. Ngưỡng quá rộng có thể khiến deploy treo rất lâu trước khi phát hiện crash hoặc sai cấu hình.

### 3.4. Nếu không khai báo probe

Không cấu hình liveness nghĩa là Kubernetes không có probe chủ động để restart một tiến trình còn chạy nhưng treo. Nếu tiến trình thoát, container restart policy/controller vẫn có thể restart nó theo cơ chế riêng. Không có readiness probe, trạng thái sẵn sàng mặc định của container không được đánh giá bằng điều kiện ứng dụng tùy chỉnh. Vì vậy service có thể được đưa vào routing sớm hơn mong muốn. Không có startup probe, readiness/liveness được điều phối theo ngưỡng riêng từ lúc container chạy.

## 4. Timeline từ deploy đến nhận request

Quá trình triển khai gồm nhiều giai đoạn:

~~~text
Deployment spec applied
    |
    +--> Scheduler chọn node
    |
    +--> Node kéo image / tạo sandbox
    |
    +--> Init containers nếu có
    |
    +--> Container chính bắt đầu
            |
            +--> JVM/process startup
            +--> Framework/application initialization
            +--> Bind socket / HTTP server
            +--> Initialize mandatory resources
            +--> Startup probe success
            +--> Readiness probe success
                    |
                    +--> Pod Ready
                    +--> Service endpoints converge
                    +--> Traffic mới tới Pod
~~~

Các mốc khác nhau quan trọng cho đo thời gian:

- **Scheduling delay:** từ tạo Pod đến được gán node.
- **Image-pull time:** phụ thuộc kích thước image, registry, mạng, cache.
- **Init-container time:** các bước bootstrap hoặc chuẩn bị tài nguyên trước container chính.
- **Application startup time:** từ bắt đầu process tới khi ứng dụng có khả năng phục vụ.
- **Time to Ready:** từ container start hoặc Pod creation tới trạng thái Ready, tùy mốc đo.
- **Time to First Successful Request:** bao gồm routing hội tụ, network và warm-up còn lại.
- **Rollout completion time:** từ triển khai revision mới tới khi toàn deployment đáp ứng điều kiện rollout.

Một §startupProbe§ chỉ quan sát quá trình của **container nó gắn vào**, không giải quyết image pull chậm hoặc scheduling thiếu node. Nếu tổng thời gian rollout chậm, cần tách các giai đoạn thay vì tăng §failureThreshold§ vô điều kiện.

## 5. Sơ đồ quyết định của ba probe

~~~mermaid
flowchart TD
    A[Container started] --> B{Startup probe configured?}
    B -->|Yes| C{Startup probe succeeds?}
    C -->|No, under failure budget| D[Wait and probe again]
    D --> C
    C -->|Failure threshold reached| E[Restart container]
    C -->|Yes| F[Enable liveness and readiness checks]
    B -->|No| F
    F --> G{Liveness healthy?}
    G -->|No, failure threshold reached| E
    G -->|Yes| H{Readiness healthy?}
    H -->|No| I[Pod not ready; stop new Service routing]
    H -->|Yes| J[Pod ready for Service routing]
    I --> H
    J --> H
~~~

Đây là luồng quyết định khái niệm. Thực tế kubelet lên lịch các probe định kỳ, readiness có thể chạy ngoài lịch định kỳ khi Pod chưa Ready, và cập nhật trạng thái có độ trễ; không dùng sơ đồ để suy ra thứ tự chính xác từng mili giây.

## 6. Hợp đồng endpoint health trong ứng dụng

Đừng để ba endpoint đều gọi chung một hàm §SELECT 1 FROM database§ rồi trả §200§ nếu query thành công. Cách đó khiến mất DB tạm thời dễ biến thành restart toàn bộ fleet.

### 6.1. Endpoint liveness

Ví dụ §GET /actuator/health/liveness§ hoặc §GET /livez§.

Mục tiêu: kiểm application còn có thể tiến triển. Nếu handler HTTP đang phản hồi và framework liveness state còn đúng, có thể trả thành công mà không kiểm mọi dependency bên ngoài.

Nguyên tắc:

- Rất nhẹ, ít cấp phát bộ nhớ và không gọi network sâu.
- Tránh truy vấn DB, broker, cache hoặc nhà cung cấp bên ngoài.
- Không trả dữ liệu nhạy cảm; status đơn giản đủ cho kubelet.
- Chỉ fail trong tình huống mà restart có khả năng sửa trạng thái.
- Không biến liveness thành phép thử nghiệp vụ nặng làm tăng tải khi hệ thống chậm.

### 6.2. Endpoint readiness

Ví dụ §GET /actuator/health/readiness§ hoặc §GET /readyz§.

Mục tiêu: xác định instance có thể **nhận và xử lý loại traffic được phân công**.

Các điều kiện có thể xét:

- Ứng dụng khởi tạo xong, không đang drain/shutdown.
- Runtime config bắt buộc đã load/validate.
- Schema/migration tương thích với phiên bản đang chạy.
- Các thành phần nội bộ thiết yếu đã sẵn sàng (ví dụ in-memory index bắt buộc).
- Có năng lực phục vụ theo contract; nếu một dependency hoàn toàn thiết yếu bị mất, cần cân nhắc rõ chiến lược readiness.

**Chính sách dependency phải thận trọng:** nếu mọi replica cùng đánh dấu NotReady khi một DB chung mất kết nối trong thời gian ngắn, Service có thể không còn endpoint dù ứng dụng có thể trả lỗi có kiểm soát, thực hiện cache fallback hoặc vẫn xử lý các route không phụ thuộc DB. Hãy quyết định theo mức bắt buộc của dependency, hành vi fallback và đường phục hồi, không tự động đưa mọi dependency vào readiness.

### 6.3. Endpoint startup

Có thể dùng cùng endpoint liveness nhẹ khi tín hiệu này chỉ chuyển “thành công” sau khi giai đoạn initialization đã hoàn tất. Hoặc tạo §/startupz§ nếu quy trình khởi tạo có trạng thái riêng. Endpoint startup trả §200§ khi đã qua những bước ứng dụng cần trước khi bật probes thông thường, trả trạng thái thất bại khi chưa hoàn tất.

Trong Spring Boot, health probes được tạo theo §ApplicationAvailability§; cần hiểu lúc nào ứng dụng chuyển từ bootstrapping sang accepting traffic. Không lấy “socket mở” làm bằng chứng rằng mọi thành phần bắt buộc đã sẵn sàng.

## 7. HTTP/TCP/exec/gRPC probe: chọn đúng mức xác nhận

| Loại | Thành công khi | Điểm mạnh | Giới hạn |
|---|---|---|---|
| HTTP GET | Trả status thành công theo quy tắc Kubernetes | Gần với HTTP service, dễ phân biệt endpoint | Handler nặng, auth/redirect, port sai gây lỗi |
| TCP socket | Kết nối TCP đến port thành công | Đơn giản cho TCP service | Port mở chưa chứng minh nghiệp vụ hoạt động |
| exec | Lệnh trong container exit code 0 | Kiểm trạng thái nội bộ/đặc thù runtime | Có chi phí process, phụ thuộc shell/tool; dễ nặng |
| gRPC health | gRPC Health Checking Protocol trả SERVING | Phù hợp gRPC-native workloads | Cần cấu hình service/port và phiên bản hỗ trợ |

HTTP probe trong Kubernetes xem mã phản hồi 200–399 là thành công. Các mã 4xx/5xx được xem là thất bại; request timeout cũng dẫn đến thất bại. Không để health endpoint yêu cầu token người dùng nếu kubelet không có cách gọi được; tốt nhất hạn chế đường truy cập bằng mạng và chính sách bảo mật, và trả response tối giản.

**TCP probe không đủ** nếu service bind port từ sớm nhưng vẫn chưa xong khởi tạo. Ngược lại, một exec probe thực hiện query phức tạp có thể gây tải đáng kể khi chạy trên hàng trăm Pod. Độ sâu kiểm tra cần tương xứng với mục đích.

## 8. Cấu hình Kubernetes mẫu

Ví dụ Deployment cho một Spring Boot API chạy cổng 8080:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: order-service
          image: registry.example.invalid/order-service@sha256:REPLACE_WITH_VALID_DIGEST
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "768Mi"
~~~

Đây là **manifest minh họa**. Phải thay image digest, selector, resources, phiên bản Spring Boot, URL, policy và cấu hình production phù hợp. §sha256:REPLACE_WITH_VALID_DIGEST§ chỉ là placeholder, không phải digest có thể pull. Không coi ví dụ là deployment hoàn chỉnh; thực tế còn cần securityContext, Service, RBAC, secret, NetworkPolicy, cấu hình quan sát và những ràng buộc hạ tầng khác.

### 8.1. Giải thích các trường probe

| Trường | Ý nghĩa |
|---|---|
| §httpGet.path§ | Đường dẫn kubelet kiểm tra |
| §httpGet.port§ | Số port hoặc tên port đã khai báo |
| §initialDelaySeconds§ | Trễ trước lần probe đầu, nếu khai báo |
| §periodSeconds§ | Khoảng thời gian giữa các lần probe theo cấu hình |
| §timeoutSeconds§ | Giới hạn một lần probe trước khi bị xem thất bại |
| §failureThreshold§ | Số lần thất bại liên tiếp trước khi kết luận không khỏe |
| §successThreshold§ | Số lần thành công liên tiếp để xem khỏe; liveness/startup cần giá trị 1 |
| §terminationGracePeriodSeconds§ | Cửa sổ cho shutdown sau tín hiệu chấm dứt; có thể cấu hình tại Pod, một số loại probe cho phép override phù hợp |

Ví dụ §startupProbe§ với §periodSeconds=5§ và §failureThreshold=60§ cho khoảng ngân sách gần 300 giây để ứng dụng khởi động. Đây là **ước lượng vận hành**, không phải bảo đảm thời điểm chết chính xác, vì thời gian probe, timeout, scheduling và cách thực thi của kubelet. Nếu app bình thường cần 40 giây mà startup probe fail sau 30 giây, container có thể bị restart liên tục mà không bao giờ đạt Ready.

### 8.2. Vì sao có cả startupProbe và livenessProbe?

Nếu ứng dụng khởi động trong 90 giây, nhưng sau khi chạy đã sẵn sàng thì 30 giây không phản hồi health là dấu hiệu treo đáng nghi, cấu hình một liveness ngưỡng rất rộng để chờ startup sẽ làm chậm phát hiện treo trong suốt vòng đời. Startup probe cho phép **ngân sách khởi động rộng** và **ngưỡng liveness vận hành chặt hơn**, áp dụng ở đúng giai đoạn.

### 8.3. Readiness quá nhạy hay quá lỏng?

§failureThreshold=1§ và §periodSeconds=1§ có thể khiến readiness flapping khi event loop hoặc GC pause ngắn, gây xáo trộn traffic. Ngược lại, ngưỡng quá lớn giữ Pod trong endpoint dù nó không thể xử lý. Chọn từ P99 health latency, GC pause, dependency behavior, lưu lượng thực tế và thời gian phản ứng cần thiết. Theo dõi số lần chuyển §Ready ↔ NotReady§ để điều chỉnh.

## 9. Ví dụ Spring Boot Actuator

Với Spring Boot có Actuator và cấu hình phiên bản tương ứng, có thể kích hoạt Kubernetes probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true

server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Các endpoint mặc định thường dùng:

- §/actuator/health/liveness§
- §/actuator/health/readiness§

Spring Boot biểu diễn liveness/readiness qua §ApplicationAvailability§. Tùy thời điểm boot, ứng dụng chuyển trạng thái từ chưa sẵn sàng sang chấp nhận traffic; khi shutdown, readiness có thể phản ánh trạng thái từ chối traffic.

**Cần kiểm tra cách expose endpoint theo phiên bản Spring Boot, security configuration và cổng management thực tế.** Nếu Actuator chạy ở một management port riêng, management port có thể vẫn trả health thành công ngay cả khi main application port không phục vụ được. Đối với HTTP API, thường nên để probes phản ánh khả năng của đường phục vụ thực tế, hoặc sử dụng additional-paths trên cổng ứng dụng nếu phiên bản framework hỗ trợ.

### 9.1. Chạy cùng application port

Có thể cấu hình health probe additional paths trong phiên bản Spring Boot hỗ trợ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Cấu hình này có thể expose §/livez§ và §/readyz§ trên cổng ứng dụng chính. Khi áp dụng, xác minh endpoint nào thực sự tồn tại bằng test và đổi §path§ trong manifest tương ứng. Không giả định mọi bản Spring Boot đều hỗ trợ cùng option và behavior.

### 9.2. Security với health endpoint

Không nên trả stack trace, environment variables, secret, DB credentials hoặc toàn bộ dependency inventory cho mọi nguồn truy cập. Thông thường kubelet chỉ cần status đơn giản và HTTP status code. Có thể phân tách:

- §/livez§, §/readyz§: status tối giản, chỉ cho tuyến node/cluster cần gọi.
- §/actuator/health§ chi tiết hơn: kiểm soát truy cập theo role/network, không in secret.
- Metrics/traces/logs: kênh quan sát chuyên biệt có bảo mật riêng.

Nếu Spring Security chặn kubelet bằng 401/403, probe sẽ liên tục thất bại dù ứng dụng khỏe. Cần test chính xác đường kubelet gọi, không đơn giản mở toàn bộ Actuator ra Internet.

## 10. Thiết kế dependency health cho readiness

Một quyết định dễ gây tranh cãi là liệu readiness có kiểm database, cache, broker và PSP không. Câu trả lời phụ thuộc **contract phục vụ** và **cách xử lý lỗi**.

### 10.1. Phân loại dependency

| Nhóm | Ví dụ | Định hướng |
|---|---|---|
| Mandatory startup state | Config/schema bắt buộc, khóa định danh, local index | Startup/readiness phải xác nhận trước khi nhận traffic |
| Local unrecoverable condition | Deadlock hoặc main loop không tiến triển | Liveness có thể fail nếu restart có khả năng sửa |
| Mandatory request path | DB cần cho mọi endpoint ghi | Readiness có thể xét nhưng phải cân nhắc outage diện rộng |
| Optional capability | Email/Notification không ảnh hưởng checkout | Không nên làm cả API NotReady |
| External unreliable service | PSP, đối tác logistics | Dùng timeout/circuit breaker/degradation; đừng trực tiếp kéo liveness fail |
| Async worker dependency | Broker/consumer assignment | Readiness có thể phản ánh worker có đủ điều kiện nhận việc, nhưng tránh remove toàn fleet vì broker chung lỗi |
| Background maintenance | Cache refresh, indexing, analytics | Theo metric riêng nếu không chặn phục vụ chính |

### 10.2. Ví dụ DB chung mất kết nối

Giả sử có 10 Pod Order Service; tất cả đánh dấu NotReady ngay khi không truy vấn được DB. Khi DB có sự cố 5 giây:

1. Mọi Pod có thể rời Service endpoints.
2. Gateway/Ingress thấy không còn upstream và trả 503.
3. Nếu liveness cũng kiểm DB, mọi Pod tiếp tục restart.
4. DB phục hồi nhưng các JVM cần warm-up, khiến recovery kéo dài hơn sự cố gốc.

Một giải pháp có thể là vẫn giữ liveness healthy, readiness dựa trên điều kiện phục vụ thực tế có ngưỡng/hysteresis phù hợp, circuit breaker và ứng dụng trả lỗi nghiệp vụ/technical có kiểm soát khi DB thật sự không thể dùng. Nếu dịch vụ hoàn toàn không có chức năng nào khi DB mất kết nối, đánh dấu NotReady có thể đúng; điều quan trọng là **quyết định có tính hệ thống**, đo hệ quả và test fault thực tế.

### 10.3. Không làm probe biến thành load generator

Nếu mỗi §/readyz§ gọi một query DB, mười nghìn Pods chạy probe mỗi năm giây tạo khoảng hai nghìn queries/giây ngay cả khi không có traffic nghiệp vụ. Đừng kích hoạt deep dependency check đắt tiền trên mỗi probe.

Có thể lưu trạng thái từ một health monitor bất đồng bộ, có TTL và ngưỡng; endpoint đọc snapshot nhẹ. Cần xử lý stale snapshot và chấp nhận giới hạn; tránh đánh dấu Ready mãi mãi chỉ vì lần kiểm tra thành công nhiều phút trước.

## 11. Startup time: đo và đặt ngân sách

Startup time có nhiều nguồn:

- Java JVM startup, class loading, JIT, CDS/AOT tùy runtime.
- Spring context creation, component scanning, reflection, bean initialization.
- Kết nối tới DB, Kafka, Redis, config service; request tới dependency lúc khởi động.
- Schema validation hoặc migrations được đặt trong startup.
- Tải cache, rule set, ML model, certificates.
- DNS, TLS handshakes và các secret fetch.
- CPU throttling do request/limit quá thấp trên node bận.
- Image pull và init containers (tính vào Pod Ready, nhưng không tính vào thời gian container startupProbe sau khi bắt đầu).

### 11.1. Các mốc nên đo

Một bảng sự kiện minh họa:

~~~text
10:00:00.000  Pod created
10:00:02.100  Pod scheduled
10:00:09.500  Image ready
10:00:10.000  Container started
10:00:26.200  Spring context refreshed
10:00:32.000  Main HTTP port listening
10:00:35.100  Startup probe success
10:00:38.000  Readiness probe success
10:00:39.200  Pod Ready / endpoint observed
10:00:39.800  First successful traffic response
~~~

Từ dữ liệu này:

- Pod creation → Ready: gần 39 giây.
- Container start → readiness: gần 28 giây.
- Container start → startup probe success: gần 25 giây.
- Số liệu không đồng nhất nếu lấy timestamp từ hệ khác có clock skew; phải chuẩn hóa UTC và hiểu độ chính xác của nguồn.

Đừng cộng mọi khoảng bằng tay nếu chúng chồng nhau. Startup probe có thể bắt đầu khi HTTP port chưa mở; đó là fail bình thường trong giai đoạn warm-up nếu còn trong ngân sách.

### 11.2. Chọn failure budget

Giả sử startup bình thường:

- P50: 18 giây.
- P95: 35 giây.
- P99: 65 giây.
- Lúc node thiếu CPU có thể lên 100 giây.

Không nên đặt startup budget đúng P50. Có thể chọn biên đủ cho tail hợp lý cộng dự phòng tài nguyên, ví dụ khoảng 120–180 giây, đồng thời đặt **triển khai chậm bất thường** thành cảnh báo. Nếu thời gian thực thường vượt ngưỡng, phải đo phase và tối ưu thay vì tăng vô hạn.

Với §periodSeconds=5§, §failureThreshold=36§, thời gian tối đa xấp xỉ 180 giây. Khi startup chưa kết thúc, liveness/readiness chưa hoạt động như bình thường; người vận hành cần xem startup progress, logs và Pod events.

### 11.3. StartupProbe không bảo vệ mọi giai đoạn

Các sự cố §ImagePullBackOff§, không schedule được vì thiếu node, ConfigMap/Secret volume mount lỗi hoặc init container không hoàn tất có thể khiến main container chưa bắt đầu. §startupProbe§ của main container chưa có cơ hội chạy; cần theo dõi Pod conditions, image pull, Init status và events.

### 11.4. Startup nhanh nhưng chưa sẵn sàng

Ứng dụng có thể mở socket nhanh nhưng sau đó tải dữ liệu quan trọng ở background. Nếu readiness trả success ngay khi socket mở, request mới sẽ gặp §CacheNotReady§ hoặc 503. Định nghĩa readiness dựa trên **khả năng phục vụ**, không chỉ lifecycle event của framework.

## 12. Tương tác với rolling update

Trong Deployment rolling update, Kubernetes tạo Pod mới rồi loại dần Pod cũ theo §maxSurge§, §maxUnavailable§ và điều kiện Ready/Available.

Một cấu hình minh họa:

~~~yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
minReadySeconds: 10
progressDeadlineSeconds: 600
~~~

Ý nghĩa:

- §maxSurge=1§: cho phép số Pod vượt desired replicas thêm một đơn vị trong rollout.
- §maxUnavailable=0§: mục tiêu giữ đủ số Pod available theo tính toán Deployment khi rollout, không chứng minh không có lỗi request.
- §minReadySeconds=10§: Pod phải Ready liên tục tối thiểu 10 giây trước khi được tính Available cho rollout.
- §progressDeadlineSeconds=600§: giới hạn thời gian Deployment chờ tiến triển; nếu quá thời gian có thể báo condition §ProgressDeadlineExceeded§, không có nghĩa Kubernetes tự rollback trong mọi môi trường.

### 12.1. Tại sao readiness là release gate quan trọng?

Nếu Pod mới mở cổng rồi báo Ready ngay, controller có thể nhanh chóng giảm Pod cũ. Sau vài giây, Pod mới mới phát hiện thiếu schema, cache hoặc secret; quá trình rollout đã làm giảm năng lực phục vụ.

Readiness đúng giúp Pod mới chỉ được tính sẵn sàng khi nó thực sự phục vụ được. Tuy nhiên, **readiness không thay thế integration smoke test, canary metric, rollout monitoring và business SLI**.

### 12.2. Rolling update của microservices có hợp đồng

Đối với Order và Payment có API/event schema thay đổi, mỗi Pod có thể Ready dù không tương thích với phiên bản còn đang chạy. Để rollout an toàn cần:

- API và event schema tương thích trong giai đoạn old/new đồng thời.
- DB migration áp dụng kiểu expand–migrate–contract.
- Feature flag không bật tính năng trước khi tất cả dependency tương thích.
- Canary hoặc progressive delivery đo latency, error, nghiệp vụ theo release.
- Readiness có kiểm config/schema bắt buộc, nhưng tránh gọi deep test làm overload production.

## 13. Graceful shutdown và traffic draining

Khi Pod bị terminate hoặc scale down, cần ngăn request mới và cho request đang xử lý hoàn tất trong thời gian phù hợp.

Một trình tự khái niệm:

~~~text
Pod deletion / termination begins
   |
   +--> EndpointSlice signals terminating/not ready
   |
   +--> preStop hook nếu có
   |
   +--> SIGTERM gửi tới process chính
   |
   +--> Application stops accepting new work
   +--> In-flight requests finish or cancel safely
   +--> Consumer pauses/stops taking new messages, commits/acks safely
   +--> Resources released
   |
   +--> Container exits
       (or SIGKILL after grace period)
~~~

Thực tế thứ tự và độ trễ giữa endpoint updates, hooks và tín hiệu phụ thuộc kubelet/controller/network. Không dựa vào thứ tự tuyệt đối giữa mọi thành phần. §terminationGracePeriodSeconds§ là tổng ngân sách chấm dứt cần đủ cho xử lý đang dở và hook; không hiểu §preStop§ cộng thêm thời gian ngoài grace.

### 13.1. Spring Boot graceful shutdown

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Kết hợp với §terminationGracePeriodSeconds§ lớn hơn tổng thời gian thực sự cần cho shutdown và overhead. Khi nhận SIGTERM, Spring Boot có thể ngừng nhận request mới và chờ request đang xử lý trong một thời hạn. Đường shutdown của broker consumer/background jobs cần xác nhận riêng; không giả định web server graceful shutdown bao trùm mọi thread/job.

### 13.2. Readiness khi drain

Nếu ứng dụng chủ động chuyển readiness sang NotReady trước khi shutdown, các thành phần phân phối traffic cần thời gian để ngừng route. Một hook §preStop§ có thể được dùng trong một số kiến trúc để tạo khoảng đệm, nhưng **sleep cố định không bảo đảm zero downtime**. Cần kết hợp protocol/keep-alive behavior, load balancer draining, termination grace và end-to-end tests.

Với event consumer, không chỉ làm NotReady HTTP là đủ. Cần dừng nhận message mới, hoàn tất hoặc để redeliver an toàn, commit offset/ACK theo contract và giữ idempotency.

### 13.3. Khi timeout shutdown

Nếu đang xử lý một payment mà Pod bị kill trước khi ghi trạng thái, client/broker có thể retry. Đây là lý do hệ thống cần idempotency và recovery. Không chỉ kéo dài grace period rồi cho rằng dữ liệu tự an toàn: transaction, outbox và replay có giới hạn vẫn cần thiết.

## 14. Readiness, HPA và autoscaling

Horizontal Pod Autoscaler có thể tăng replica khi CPU/metric lên cao. Nhưng **tạo replica không đồng nghĩa tăng ngay capacity**: Pod mới cần scheduling, image, startup, warm-up và Ready; trong thời gian đó replica cũ vẫn chịu tải.

Một số rủi ro:

- HPA scale-out nhanh, nhiều JVM khởi động cùng lúc, gây CPU burst và DB connection storm.
- Pod mới chưa Ready nhưng metrics tổng thể đã đổi, khiến logic scale rung lắc.
- Liveness probe timeout do CPU starvation trong cold start nếu không có startup budget.
- Scale-in chấm dứt Pod có in-flight jobs, không drain hoặc không đủ §terminationGracePeriodSeconds§.
- Application warm-up lâu, cần capacity buffer/overprovisioning cho traffic spike.
- Queue consumer scale theo lag nhưng mỗi consumer cần partition assignment và rebalancing.

Đo thêm **time from scale decision to usable capacity**. Chọn CPU requests, startup budgets, HPA stabilization và scaling signal theo workload thật. Không đặt threshold chỉ bằng kết quả một lần benchmark.

## 15. Readiness với service chỉ có worker / consumer

Không phải mọi service đều có HTTP API. Một Kafka consumer hoặc scheduled worker vẫn cần biết khi nào có thể nhận công việc, có tiếp tục tiến triển hay không.

Ví dụ:

- **Startup:** application đã load config, kết nối thiết lập theo contract, component xử lý message đã khởi tạo.
- **Readiness:** có khả năng xử lý assignment/work đã được cấp, hoặc một điều kiện thích hợp với controller đang quản lý; HTTP endpoint chỉ là cách công bố status nếu có.
- **Liveness:** tiến trình đang tiến triển hoặc có cơ chế phát hiện deadlock không thể tự hồi phục.
- **Shutdown:** dừng poll/take new jobs, flush/commit/ACK an toàn, cho message chưa xong được retry với idempotency.

Cẩn thận với readiness phụ thuộc một consumer group có zero partition assignment: một instance nhàn rỗi nhưng khỏe có thể không có partition vì số replica lớn hơn partition; đó không nhất thiết là lỗi. Không thiết kế readiness khiến các Pod nhàn rỗi liên tục bị loại khỏi nhóm, tạo rebalance loop.

Với job chạy một lần (§Job§/§CronJob§), success/failure của process và job controller quan trọng hơn readiness để route traffic. Đừng sao chép probe của HTTP deployment sang mọi container mà không xét lifecycle.

## 16. Thiết kế một bảng policy cho từng service

Một microservice nên có bảng quyết định cụ thể:

| Service | Startup condition | Ready condition | Liveness condition | Shutdown |
|---|---|---|---|---|
| API Gateway | Proxy/config đã load | Routes/certificates thiết yếu có hiệu lực, chấp nhận request | Process/worker loop không treo | Stop new connections, drain |
| Order API | Spring context, schema/config hợp lệ | Có thể xử lý các thao tác chính theo contract | Local application progress | Stop new orders, finish/cancel safely |
| Payment API | Credentials/clients cấu hình hợp lệ | Có thể nhận payment requests và xử lý degrade policy | Không deadlock/irrecoverable loop | Không tạo attempt mới, reconcile in-flight |
| Inventory API | Database client/logic initialized | Có thể nhận reservation commands theo policy | Local process progress | Finish atomic updates, ack đúng |
| Notification worker | Consumer và template/config sẵn | Worker có thể nhận job theo contract | Event loop/worker pool tiến triển | Dừng poll, ACK/requeue đúng |
| Search API | Index metadata tương thích | Index/snapshot thiết yếu đã load | Search process không treo | Drain queries |
| Reporting worker | Scheduler/job configuration load | Tùy mô hình job, không nhất thiết có Service readiness | Process health | Persist checkpoint |

Bảng này là mẫu để thảo luận, không phải default áp đặt. Mỗi service cần xác nhận dependency/fallback, error semantics và trigger restart qua thực nghiệm.

## 17. Các anti-pattern gây downtime

### 17.1. Cả ba probe cùng query DB

Nếu DB lỗi, startup/readiness/liveness đều thất bại. Trong runtime, liveness restart mọi Pod. Tác động là thundering herd khi DB phục hồi, mất cache/JIT warm-up, làm tăng thời gian outage. Thiết kế lại liveness chỉ cho local health; readiness có dependency policy được cân nhắc riêng.

### 17.2. Dùng TCP probe khi app bind port quá sớm

Port mở không đảm bảo request handler, auth, schema, cache hoặc routing đã sẵn. Readiness nên xác nhận ability to serve, có thể bằng HTTP health state nhẹ. Kiểm startup time thực tế.

### 17.3. Readiness chỉ kiểm §200§ nhưng không phản ánh drain

Một Pod chuẩn bị terminate vẫn có thể nhận request mới nếu route chưa hội tụ. Kết hợp readiness transition, termination signal, load balancer drain và graceful shutdown.

### 17.4. Liveness probe quá đắt

Deep SQL query hoặc gọi cả chuỗi downstream trên mỗi lần kiểm tra gây thêm tải và timeout khi hệ thống bận. Probe cần nhanh, tách detailed diagnostic ra kênh quan sát riêng.

### 17.5. Startup budget thấp hơn P99 startup

Ứng dụng chưa sẵn sàng đã bị restart liên tục. Phân tích Pod events, §lastState.terminated§, logs startup và thống kê startup theo tài nguyên. Chọn ngưỡng có biên hợp lý.

### 17.6. Startup budget quá dài để che lỗi

Sai credential, schema migration fail hoặc config invalid vẫn đợi nhiều phút mới restart. Những lỗi không thể phục hồi nên fail fast, xuất reason code và để controller xử lý, không cứ trả “starting” vô hạn.

### 17.7. Management port khác main port

Probe trên management port thành công, nhưng main app port bị treo hoặc bind sai. Hãy xác thực đường phục vụ thật, hoặc expose health additional paths trên main port phù hợp.

### 17.8. Không đo startup sau thay đổi

Một dependency mới thêm vào startup làm thời gian từ 20 lên 90 giây; rollout hôm sau thiếu capacity. Cần CI/perf smoke, histogram startup và review khi thêm initializer.

### 17.9. Coi Ready đồng nghĩa khỏe toàn hệ thống

Pod Ready nhưng Payment 429 hoặc workflow chưa hoàn tất. Kết hợp readiness với E2E metrics, error budget, queue lag và business outcome.

### 17.10. Chỉ scale bằng replica count

Replica mới mất 2 phút startup, trong lúc spike diễn ra 20 giây. Cần capacity headroom, ưu tiên giảm cold-start, pre-warm hoặc chính sách scale thích hợp.

## 18. Kiểm thử chức năng của ba probe

Không nên coi §kubectl get pods§ hiện READY là bằng chứng đủ. Tạo test có chủ đích và ghi expected outcome.

| Test | Tác động đưa vào | Kỳ vọng |
|---|---|---|
| Khởi động bình thường | Deploy revision mới | Startup success, readiness success, traffic chỉ vào Pod Ready |
| Khởi động chậm | Tạo delay trong initializer/CPU throttling có kiểm soát | Startup probe chờ trong budget; không liveness restart sớm |
| Sai config bắt buộc | Thiếu secret reference/schema invalid | Fail fast hoặc startup fail rõ ràng; không route traffic |
| Dependency tạm mất | Tắt DB/PSP test trong vài giây | Liveness không restart cả fleet; readiness theo contract |
| Local deadlock không hồi phục | Cố tình làm treo handler/worker trong môi trường test | Liveness phát hiện/restart nếu cơ chế health được thiết kế cho trường hợp đó |
| Readiness chuyển false | Ứng dụng vào drain/maintenance | Pod không nhận traffic mới qua Service sau khi routing hội tụ |
| Shutdown có request đang chạy | Xóa Pod khi có request dài | Request kết thúc/cancel an toàn trong grace, retry idempotent |
| Rolling update | Deploy old→new với §maxUnavailable=0§ | Pod mới Ready trước khi capacity cũ giảm, metrics không regression |
| Autoscaling | Spike load tạo Pod mới | Thời gian tới capacity usable nằm trong budget |
| Probe flapping | Delay/GC pause ngắn, network jitter | Không chuyển Ready liên tục ngoài dự kiến |
| Consumer restart | Kill worker sau DB commit trước ACK | Redelivery an toàn, không side effect trùng |

### 18.1. Kiểm tra HTTP endpoint trong môi trường test

Lệnh minh họa khi service đã chạy trên local:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Đừng dùng kết quả localhost từ máy developer để kết luận kubelet gọi được endpoint trong Pod. Kiểm security, address/port binding, container network và readiness conditions trong cluster. Các test fault injection phải có môi trường và phạm vi được phép.

### 18.2. Test tại Kubernetes

Các thao tác quan sát không thay đổi workload:

~~~bash
kubectl get pods -n orders -o wide
kubectl describe pod order-service-example -n orders
kubectl get deployment order-service -n orders
kubectl rollout status deployment/order-service -n orders
kubectl get endpointslice -n orders
kubectl logs pod/order-service-example -n orders --previous
~~~

Tên namespace/Pod là placeholder. §--previous§ chỉ có logs nếu container đã restart và logs còn sẵn. Trong môi trường nhiều Pod, xem §describe§ events và container restart count trước khi kết luận từ một log lẻ.

### 18.3. Đọc trạng thái lỗi trong Pod

Các tình huống phổ biến:

- §Startup probe failed§: endpoint chưa mở/không trả thành công trước ngưỡng; có thể do app init chậm hoặc lỗi thật.
- §Readiness probe failed§: Pod bị đánh dấu NotReady, không nhất thiết restart; kiểm app state, endpoint và networking.
- §Liveness probe failed§: container có thể bị restart khi vượt ngưỡng; kiểm reason gốc, GC/CPU starvation và timeout.
- §CrashLoopBackOff§: container lặp crash/restart với backoff; có thể do startup probe, lỗi ứng dụng hoặc resource.
- §OOMKilled§: container chết do memory limit, không phải lỗi health endpoint; cần xem memory sizing/leak.
- §ImagePullBackOff§ / §ErrImagePull§: vấn đề image/registry, probe chính chưa chạy.
- §ProgressDeadlineExceeded§: rollout không đủ tiến triển trong deadline; kiểm Pod Ready, image, crash, quota và readiness flapping.

## 19. Quan sát và đo startup/readiness

Mỗi đợt deploy nên lưu:

- Version ứng dụng và image digest.
- Config revision, feature flag revision, secret reference version (không ghi secret).
- Thời điểm Pod created, scheduled, container started, startup success và Ready.
- Restart count, reason, OOM events.
- Số lần readiness transition và thời gian ở trạng thái NotReady.
- Failure reason đã sanitize.
- Số Pod Available/Unavailable, rollout duration và traffic errors trong canary.
- Request latency/error và business outcomes sau khi Pod được route traffic.

### 19.1. Metric gợi ý

~~~text
app_startup_duration_seconds
app_readiness_transition_total{to_state="ready|not_ready",reason="..."}
app_liveness_failure_total{reason="..."}
app_health_check_duration_seconds
deployment_time_to_ready_seconds
deployment_available_replicas
deployment_unavailable_replicas
container_restart_total
request_error_rate
request_duration_seconds
workflow_completion_rate
~~~

Đây là tên minh họa, không mặc định được Kubernetes hoặc Spring Boot export đúng tên này. Với metrics của kube-state-metrics, cAdvisor, kubelet và application registry, cần tra tên thực trong môi trường. Không đưa Pod UID, order ID hoặc thông tin bí mật làm label không giới hạn. Các lý do lỗi nên là enum hữu hạn như §config_invalid§, §initializing§, §draining§, §resource_exhausted§.

### 19.2. Dashboard theo đợt triển khai

Một dashboard rollout nên thể hiện:

1. Desired/updated/ready/available replica theo thời gian.
2. Histogram hoặc P50/P95/P99 time-to-ready theo release.
3. Restart count và nhóm termination reason.
4. Readiness flapping, startup failures và liveness failures.
5. Traffic RPS, P95/P99 latency, 5xx/429 qua Gateway.
6. Queue lag và business workflow error/stuck metrics.
7. Config/schema version, thời điểm rollout, region và node.

Một Pod Ready nhưng sản lượng workflow tụt sau khi deploy là tín hiệu riêng cần điều tra. Ngược lại, một Pod NotReady trong lúc startup nhưng rollout còn đủ capacity có thể là hành vi dự kiến.

## 20. Điều tra sự cố qua kịch bản

### 20.1. Pod restart liên tục khi deploy phiên bản Java mới

Triệu chứng: §CrashLoopBackOff§ và event startup/liveness failures. Hướng kiểm:

1. Xác nhận loại probe thực sự thất bại và mốc container started.
2. Xem §kubectl describe pod§, container §lastState§, logs lần trước và memory events.
3. So sánh startup duration, Java version, CPU request/limit, classpath và new initializers.
4. Kiểm endpoint/port/path có đúng không; Actuator security có trả 401/403 không.
5. Nếu start hợp lệ nhưng chậm, điều chỉnh startup budget dựa trên P99 và tối ưu startup.
6. Nếu config/secret invalid, sửa lỗi gốc hoặc cho fail fast với reason rõ.
7. Xác nhận Pod đạt Ready và traffic/SLI phục hồi sau thay đổi.

### 20.2. Tất cả Pod NotReady khi database mất kết nối

Triệu chứng: Service thiếu endpoints, Gateway 503, dù app không crash.

1. Kiểm readiness có health indicator DB không.
2. Xác định endpoint nào thực sự cần DB và có fallback không.
3. Cân nhắc policy readiness khi dependency chung mất; không đổi vội để “có màu xanh” mà bỏ qua tính đúng đắn.
4. Đảm bảo liveness không dựa vào DB.
5. Kiểm circuit breaker, timeout, rate limit, cache fallback và trạng thái phục hồi.
6. Chạy fault test mô phỏng mất DB ngắn và dài, đo user-facing errors, recovery time và queue state.

### 20.3. Deploy xanh nhưng có lỗi 503 trong 30 giây đầu

Triệu chứng: Pod Ready nhanh, request đầu lỗi.

- Probe có đang kiểm cổng management riêng không?
- App có warm-up/index bắt buộc sau §ApplicationReadyEvent§ không?
- Readiness có chuyển sớm, rồi flapping khi cache chưa sẵn không?
- Istio/Ingress/Service endpoints có hội tụ chậm không?
- Có lỗi schema/event không tương thích khi old/new coexist không?
- §minReadySeconds§ có đủ để phát hiện flapping ngắn không?
- Smoke test có thực sự gọi luồng nghiệp vụ qua Gateway khi revision mới nhận traffic không?

Không chỉ tăng §initialDelaySeconds§ nếu chưa hiểu mốc readiness thật.

### 20.4. Pod chấm dứt nhưng request đang chạy bị rớt

Kiểm §terminationGracePeriodSeconds§, Spring graceful shutdown, async worker stops, preStop hook, keep-alive, LB draining, route propagation và request duration. Nếu transaction có side effect, xác nhận retry idempotent và recovery. Một request dài hơn grace period cần phương án checkpoint/cancel/retry hoặc tăng grace với ngân sách vận hành hợp lý.

### 20.5. Scale-out chậm khi flash sale

Đo thời gian từ HPA quyết định tăng replicas tới Pod Ready và nhận traffic. Nếu 90 giây mà spike chỉ 20 giây, scale-out phản ứng không kịp. Hướng xử lý: capacity headroom, tối ưu image/JVM startup, tránh connection storm, pre-warm, điều chỉnh HPA theo leading indicators, đặt queue/backpressure và giới hạn request hợp lý.

## 21. Startup performance trong Java và Spring Boot

Không có một cấu hình JVM duy nhất luôn nhanh nhất. Tìm nguyên nhân theo phase:

| Phase | Tín hiệu | Ý tưởng cải thiện cần đo |
|---|---|---|
| JVM/class loading | Time to main, class load count | Giảm classpath dư, CDS/AOT khi phù hợp |
| Spring context | Bean creation, component scan | Loại bean không cần, kiểm auto-configuration |
| External config/secrets | Network wait, timeout | Cache/timeout hợp lý, tránh gọi nối tiếp không cần thiết |
| DB/migrations | Lock, schema validation, migration time | Tách migration có kiểm soát, tránh nhiều Pod cùng chạy migration |
| Client initialization | DNS/TLS, connection pool | Lazy/async init cho phần không bắt buộc, nhưng readiness phải chính xác |
| Warm-up/cache | Bulk fetch và memory | Snapshot/preload có giới hạn, đo lợi ích |
| CPU throttling | CPU throttled time | Đặt requests/limits phù hợp, tránh cold-start storm |

**Cẩn thận với lazy initialization:** khởi động nhanh hơn nhưng có thể chuyển chi phí sang request đầu tiên, làm P99 xấu hoặc gây lỗi đầu phiên. Nếu một tài nguyên bắt buộc cho route chính, readiness hoặc warm-up test cần xác nhận nó đã sẵn trước khi route traffic.

### 21.1. Không chạy migration phá tương thích trong mọi Pod

Nếu mỗi Pod mới tự chạy migration nặng khi startup, rolling update có thể tạo race, DB lock và timeout. Nên quản lý migration như một bước phát hành được kiểm soát, có backward compatibility, trạng thái rõ và rollback strategy. Readiness chỉ xác nhận schema mà phiên bản code cần; nó không thay thế thiết kế migration.

## 22. Rủi ro bảo mật của health endpoints

Các endpoint probe là một phần của mặt phẳng vận hành, cần bảo vệ:

- Chỉ expose mức thông tin tối thiểu cho liveness/readiness.
- Không trả danh sách secret, JDBC URL có credential, stack trace hoặc internal topology công khai.
- Đảm bảo endpoint có thể được kubelet gọi theo policy mạng mà không yêu cầu token người dùng.
- Phân quyền endpoint diagnostic chi tiết nếu có.
- Tránh health-check handler thực thi command không kiểm soát hoặc query chứa input bên ngoài.
- Theo dõi truy cập bất thường vào health endpoints nếu chúng bị public expose.
- Không để user-triggered header/query parameter tùy ý quyết định trạng thái Ready/Live.

Thông tin chi tiết nên ở logs/metrics/traces có RBAC và retention. Status probe không cần trở thành API quản trị.

## 23. Thiết kế test plan theo từng giai đoạn

### 23.1. Unit và component test

Kiểm logic §ApplicationAvailability§, trạng thái “starting/ready/draining”, các điều kiện chuyển hợp lệ, timeout/fallback và việc endpoint trả status đúng. Với code custom health indicator, test khi dependency trả lỗi, phản hồi chậm và phục hồi; tránh chạy dependency thật nếu đây chỉ là logic đơn vị.

### 23.2. Integration test

Chạy Spring Boot với DB/cache giả lập hoặc container thực có kiểm soát. Kiểm app chưa Ready trước khi init xong, Ready khi bắt đầu phục vụ, NotReady trong drain, Live vẫn true khi một dependency ngoài không bắt buộc lỗi. Với dependency critical, test policy đúng như thiết kế.

### 23.3. Kubernetes deployment test

Tạo rollout lên cluster thử, xác nhận:

- Startup probe giữ container khỏi liveness restart sớm.
- Readiness chỉ chuyển true khi app đã có thể phục vụ.
- Old Pod còn capacity cho đến khi new Pod Ready theo rollout strategy.
- Một Pod NotReady không còn nhận request mới qua Service sau khi hội tụ.
- Shutdown với in-flight request có kết quả đúng.
- Khi startup không thể hoàn tất, deployment báo lỗi trong thời gian hữu hạn và logs có nguyên nhân.

### 23.4. Performance, soak và resilience test

Bắn tải bình thường trong lúc tạo Pod mới, scale-out, kill Pod và làm chậm dependency. Đo P95/P99, error rate, queue backlog, time-to-ready, restart counts và trạng thái nghiệp vụ. Không chỉ kiểm health endpoint từ một máy khác rồi bỏ qua tác động traffic.

### 23.5. Rollback test

Deploy revision mới có readiness lỗi hoặc incompatibility, xác minh pipeline/controller phát hiện rollout không thành công, thực hiện rollback theo quy trình platform và kiểm phiên bản cũ thực sự Ready/serving. Không giả định Deployment tự rollback vì §ProgressDeadlineExceeded§; cần cơ chế vận hành/CD controller hoặc người chịu trách nhiệm quyết định.

## 24. Checklist triển khai

### Trước deploy

- [ ] Mỗi service có định nghĩa riêng cho startup, readiness, liveness và shutdown.
- [ ] Liveness không phụ thuộc trực tiếp các dependency dùng chung có thể lỗi tạm thời.
- [ ] Readiness phản ánh khả năng phục vụ traffic, không chỉ cổng mở hoặc JVM chạy.
- [ ] Startup budget dựa trên phân bố thời gian khởi động và có ngưỡng hữu hạn.
- [ ] Các probe nhanh, nhẹ, chỉ trả status cần thiết và có path/port đúng.
- [ ] Actuator security và cổng application/management được kiểm tra.
- [ ] Rolling strategy, §minReadySeconds§, §progressDeadlineSeconds§ và capacity headroom phù hợp.
- [ ] Graceful shutdown và termination grace đã được cấu hình.
- [ ] Ứng dụng có retry/idempotency cho side effect dở dang khi Pod bị terminate.
- [ ] Pod metadata có app/config version để điều tra.

### Trong deploy

- [ ] Có đủ Available replicas trong rollout.
- [ ] Pod mới startup → Ready theo thời gian dự kiến; không có restart loop.
- [ ] Probe failure reason và readiness flapping được quan sát.
- [ ] Traffic lỗi, latency, queue lag và workflow outcomes không regression.
- [ ] Old/new versions cùng chạy tương thích với API/schema.
- [ ] Canaries/rollout có điều kiện dừng và rollback rõ ràng.

### Sau deploy

- [ ] Time-to-ready được ghi nhận để so baseline.
- [ ] Có alert cho excessive restarts, NotReady kéo dài, rollout stalled.
- [ ] Scale-in và shutdown không làm mất message hoặc request có side effect.
- [ ] Khi dependency lỗi, failure mode đúng như policy; không có restart storm.
- [ ] Khi traffic spike, startup time không làm HPA phản ứng quá muộn.
- [ ] Metrics và health endpoint không tiết lộ dữ liệu nhạy cảm.
- [ ] Incident runbook chỉ rõ nơi xem Pod conditions, logs, rollout, tracing và business SLI.

## 25. Bài tập thực hành

### Bài A — Chọn probe cho từng tình huống

Phân loại một Pod Java trong các tình huống dưới đây:

1. Spring context chưa hoàn tất, HTTP port chưa mở.
2. App chạy nhưng đang warm-up một local index bắt buộc để search.
3. DB chung mất kết nối hai giây rồi phục hồi; ứng dụng có circuit breaker.
4. Thread pool bị deadlock không tự phục hồi.
5. Pod nhận SIGTERM và đang hoàn tất request.
6. PSP trả 429 trong một phút, nhưng phần Order có thể ghi trạng thái “pending payment” đúng contract.

Với mỗi tình huống, nêu startup/readiness/liveness mong muốn, có restart hay không, và giải thích lựa chọn dependency policy.

### Bài B — Tính startup budget

Một service có P50 startup 25 giây, P95 60 giây, P99 90 giây và đôi khi CPU throttling khiến startup 120 giây. Thiết kế §startupProbe§ với §periodSeconds=5§, chọn §failureThreshold§ có biên hợp lý. Giải thích vì sao §livenessProbe§ với §failureThreshold=3§, §periodSeconds=10§ có thể gây restart loop nếu không có startup probe.

### Bài C — Rolling update và zero-downtime

Order Service có ba replica, mỗi Pod startup 50 giây, warm-up 15 giây, request có thể chạy 20 giây. Thiết kế §maxSurge§, §maxUnavailable§, §minReadySeconds§ và §terminationGracePeriodSeconds§; nêu phép đo/test để xác minh không gián đoạn đáng kể. Thảo luận giới hạn do Service endpoint propagation, keep-alive và schema incompatibility.

### Bài D — Tìm nguyên nhân CrashLoopBackOff

Một Pod chạy Spring Boot liên tục restart. Logs không có exception, mỗi lần container chạy khoảng 30 giây, event báo liveness fail. Readiness endpoint trả 503 trước 45 giây vì đang tải cache.

Hãy nêu các giả thuyết và thay đổi tối thiểu để phân biệt lỗi khởi động chậm, cấu hình path/port sai, probe timeout và deadlock thật. Thiết kế cách đo time-to-ready trước khi chỉnh ngưỡng.

### Bài E — Dependency outage

Mười Pod Payment Service cùng kiểm PSP trong liveness và readiness. PSP ngắt mạng 20 giây. Mô tả hệ quả có thể xảy ra, thiết kế policy mới cho live/ready, timeout/circuit breaker, và test phục hồi để không có double charge hoặc stuck payment attempt.

### Bài F — Shutdown worker

Notification Service nhận event qua Kafka. Kubernetes scale-in một Pod khi nó vừa commit side effect nhưng chưa ACK message. Thiết kế thứ tự stop poll, flush/commit/ACK hoặc redelivery, idempotency và grace period. Giải thích tại sao HTTP readiness false không đủ để bảo đảm message không xử lý trùng.

## 26. Ghi nhớ cốt lõi

Trong triển khai dịch vụ, hãy luôn tách ba quyết định:

- **Startup probe:** cho phép ứng dụng vượt qua quá trình khởi động hợp lệ, nhưng phát hiện lỗi không thể khởi động trong một thời gian hữu hạn.
- **Readiness probe:** điều phối traffic tới những instance thực sự có khả năng phục vụ và rút instance khỏi routing khi chưa sẵn sàng hoặc đang drain.
- **Liveness probe:** chỉ kích hoạt restart khi tiến trình đã rơi vào tình trạng cần restart để hồi phục.

Ba probe chỉ là tín hiệu vòng đời. Khả năng triển khai an toàn còn phụ thuộc **khởi động có đo lường, dependency policy, rolling update, graceful shutdown, autoscaling, tính tương thích phiên bản và đo kết quả nghiệp vụ**. Một hệ thống đáng tin cậy không chỉ có Pod xanh, mà còn gửi đúng traffic, hoàn tất request đang chạy và phục hồi sau lỗi mà không đánh mất hoặc nhân đôi side effect.