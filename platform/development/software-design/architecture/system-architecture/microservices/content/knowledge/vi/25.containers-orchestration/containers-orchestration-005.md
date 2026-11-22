# Health probe và tương tác với vòng đời ứng dụng

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Container và điều phối. Tài liệu hướng dẫn thiết kế, cấu hình và kiểm thử health probe cho ứng dụng container, đặc biệt trên Kubernetes, đồng thời giải thích cách probe liên kết với startup, readiness, liveness, quá tải, graceful shutdown và rolling deployment. Ví dụ dùng Java/Spring Boot, nhưng các nguyên tắc áp dụng cho nhiều runtime và hệ thống điều phối khác.

## 1. Vì sao health probe là một phần của kiến trúc microservices?

Trong microservices, một tiến trình còn tồn tại không có nghĩa nó đã sẵn sàng phục vụ request. Một container có thể đang chạy nhưng chưa khởi tạo xong, vừa mất kết nối với dependency quan trọng, đang tải dữ liệu cache hoặc đang đóng dần các kết nối để được thay thế khi rollout. Ngược lại, một dependency ngoài gặp lỗi ngắn hạn không đồng nghĩa tiến trình ứng dụng bị hỏng đến mức cần restart.

Nếu hệ thống điều phối chỉ dựa vào trạng thái process, những tình huống sau dễ xảy ra:

- **Cold start:** HTTP port đã mở nhưng database migration, cache warm-up, consumer assignment hay bootstrap chưa hoàn tất; request thật đi vào quá sớm.
- **Kẹt xử lý:** event loop/thread pool không xử lý được công việc, dù process vẫn sống và cổng TCP vẫn mở.
- **Phụ thuộc ngoài tạm thời lỗi:** mọi Pod cùng restart vì health check gọi database đang gián đoạn; restart storm làm sự cố trầm trọng hơn.
- **Rolling deployment:** Pod cũ nhận thêm request sau khi bắt đầu kết thúc, hoặc Pod mới nhận traffic trước khi sẵn sàng.
- **Quá tải:** probe tranh tài nguyên với request, bị timeout và kích hoạt thêm restart đúng lúc service cần ổn định nhất.
- **Worker bất đồng bộ:** HTTP endpoint xanh nhưng message consumer không còn poll, hoặc consumer đã ngừng nhưng readiness vẫn báo nhận việc mới.
- **Cấu hình sai:** service trả 200 trong khi thiếu secret, sai phiên bản schema hoặc chưa thể xử lý nghiệp vụ được giao.

**Health probe** là phép kiểm tra lặp lại mà orchestrator hoặc hệ quan sát dùng để xác định trạng thái vận hành. Kết quả probe phải có **ý nghĩa hành động rõ ràng**: có được gửi traffic vào không, có cần restart container không, hay chỉ cần theo dõi/khởi tạo lâu hơn.

Một probe tốt không chỉ trả lời “có trả 200 được không” mà phải thể hiện chính xác quyết định của tầng dùng kết quả đó.

## 2. Ba loại probe cốt lõi trong Kubernetes

| Probe | Câu hỏi cần trả lời | Khi thất bại đủ ngưỡng | Khi nào hữu ích |
| --- | --- | --- | --- |
| **startupProbe** | Ứng dụng đã khởi động thành công chưa? | Kubelet kết thúc và khởi động lại container theo restart policy | Ứng dụng cold start dài, khởi tạo phức tạp |
| **readinessProbe** | Instance hiện có nên nhận traffic/việc mới không? | Pod bị coi là chưa Ready và bị loại khỏi các endpoint sẵn sàng của Service | Bootstrap, dependency cần thiết, draining, quá tải có chủ đích |
| **livenessProbe** | Tiến trình đang ở trạng thái có thể tự phục hồi không, hay cần restart? | Kubelet restart container khi đạt failure threshold | Deadlock hoặc trạng thái lỗi nội bộ cần khởi động lại |

**Không đánh đồng tác dụng:** Readiness thất bại **không tự restart** container. Liveness thất bại **không chỉ bỏ Pod khỏi load balancer**; nó dẫn đến kết thúc container để khởi động lại. Startup failure cũng có thể restart. Một service có thể live nhưng not ready; ví dụ service đang khởi động, đang drain hoặc tạm không có đủ năng lực nhận request.

### 2.1. Startup probe

Startup probe giúp tránh việc liveness giết một ứng dụng mất nhiều thời gian khởi động. Khi startupProbe được khai báo, Kubernetes **chưa thực hiện liveness và readiness probes cho đến khi startupProbe thành công**. Sau thành công, liveness/readiness hoạt động bình thường. Startup probe không phải công cụ kiểm tra kết nối database mãi mãi sau khởi động.

Ví dụ service cần tối đa khoảng hai phút để bootstrap: startupProbe có periodSeconds = 5, failureThreshold = 30, nghĩa là khoảng 150 giây ngân sách cho những lần kiểm tra (chưa kể thời điểm chạy/timeout và chi tiết thực tế của kubelet). Chọn budget theo thời gian cold start đo được, không sao chép con số tùy tiện.

### 2.2. Readiness probe

Readiness biểu thị khả năng nhận **công việc mới**. Khi một Pod chưa Ready, Kubernetes cập nhật trạng thái endpoint để không chọn nó làm endpoint sẵn sàng cho những kết nối Service mới trong quá trình cập nhật trạng thái mạng. Quá trình lan truyền tới kube-proxy, gateway, service mesh hoặc external load balancer **không nhất thiết tức thời**.

Một Pod live nhưng not ready có thể đang chờ khởi tạo, trong quá trình drain, bị thiếu tài nguyên ngắn hạn hoặc đang phục hồi một dependency bắt buộc. Khi phục hồi, readiness có thể tự chuyển lại thành công mà không cần restart.

### 2.3. Liveness probe

Liveness chỉ nên thất bại khi **restart có khả năng chữa được tình trạng hiện tại**: deadlock kéo dài, trạng thái nội bộ bị hỏng không hồi phục, vòng xử lý chính ngừng tiến triển mà không có cách tự phục hồi. Nếu chỉ vì DB hoặc mạng chậm, restart tất cả instance có thể gây mất cache, tăng connection churn và khiến outage kéo dài.

**Quy tắc thực hành:** Liveness thiên về kiểm tra sức sống nội bộ; readiness thiên về khả năng phục vụ. Startup thiên về một lần bootstrap. Đừng sử dụng cùng một health predicate nặng cho cả ba loại chỉ vì dễ cấu hình.

## 3. Vòng đời container và tương tác của probes

~~~text
CREATE POD
    |
    v
Image pull / container start
    |
    v
Application bootstrap
    |
    +--> startupProbe fails temporarily -> keep checking
    |
    +--> startupProbe succeeds
              |
              v
       liveness/readiness active
              |
          readiness OK?
           /        \
          no        yes
          |          |
     Not Ready     Ready -> new traffic
          |          |
     retry probe    liveness check
          |          |
          +----------+
              |
         termination requested
              |
              v
      Pod marked terminating
              |
        preStop hook / TERM
              |
              v
       stop new work + drain
              |
              v
       finish in-flight + flush
              |
              v
             EXIT
~~~

Trong thực tế, trạng thái Pod còn phụ thuộc Pod conditions, init containers, sidecars, readiness gates, restart policy, scheduling, service discovery và controller. Sơ đồ chỉ thể hiện luồng quản lý ứng dụng chính.

**Một biến thường bị nhầm:** Container Running là trạng thái runtime; Pod Ready là điều kiện của toàn Pod. Pod có nhiều container thì readiness của tất cả container liên quan và readiness gates có thể ảnh hưởng Pod Ready. Khi sidecar chưa Ready, Pod có thể không được chọn làm endpoint dù container ứng dụng khỏe.

## 4. Chọn dạng probe: HTTP, TCP, exec, gRPC

Kubernetes hỗ trợ nhiều cơ chế:

| Loại | Cách thực hiện | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **httpGet** | Kubelet gọi HTTP GET tới Pod IP/port/path | Dễ biểu đạt readiness/liveness theo ngữ nghĩa ứng dụng | Phải có HTTP endpoint phản hồi đúng; cần bảo vệ và tránh check quá nặng |
| **tcpSocket** | Kubelet thử mở kết nối TCP tới port | Đơn giản, phù hợp service ít logic HTTP | Port mở không chứng minh app xử lý nghiệp vụ được |
| **exec** | Kubelet chạy lệnh trong container | Phù hợp phần mềm không mở HTTP probe endpoint | Spawn process mỗi lần, tốn tài nguyên; cần executable trong image |
| **grpc** | Sử dụng giao thức gRPC Health Checking | Hợp service gRPC có health service | Cần triển khai health protocol và chú ý hỗ trợ port/probe config |

HTTP probe coi mã phản hồi trong khoảng **200–399** là thành công. Một endpoint redirect hoặc reverse proxy trả 302 có thể làm probe được coi là thành công dù logic readiness chưa chắc đúng; vì thế nên thiết kế endpoint trả trực tiếp 200 khi khỏe và 503 khi chưa sẵn sàng, không chuyển hướng tới login hoặc trang khác.

Một TCP probe có thể thành công khi socket accept nhưng worker pool đã deadlock. Ngược lại, HTTP probe trên cùng event loop bị kẹt giúp phát hiện event loop không phản hồi, nhưng nếu endpoint được xử lý trên thread riêng thì có thể báo live trong khi luồng nghiệp vụ chính đã ngừng hoạt động. Chọn probe phù hợp kiến trúc concurrency.

gRPC Health Checking thường có service/status tương ứng; không phải bất kỳ gRPC method tự đặt tên Health nào cũng được kubelet hiểu. Trong triển khai thực tế, cấu hình phải khớp protocol, port và service health handler.

## 5. Thiết kế endpoint health: tối thiểu, nhanh, xác định được

Một contract đơn giản:

~~~http
GET /health/live HTTP/1.1
Host: pod.internal

HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

Khi chưa Ready:

~~~http
GET /health/ready HTTP/1.1
Host: pod.internal

HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"status":"OUT_OF_SERVICE"}
~~~

Các đường dẫn chỉ là ví dụ. Với Spring Boot Actuator có thể dùng `/actuator/health/liveness` và `/actuator/health/readiness` khi các nhóm probe được kích hoạt và expose phù hợp. Hãy chọn đúng endpoint framework đã cấu hình, tránh đặt hai tên khác nhau ở YAML và code.

Yêu cầu kỹ thuật:

- Trả kết quả nhanh, tốt nhất chỉ đọc state đã biết và các kiểm tra nội bộ rẻ.
- Không làm ghi dữ liệu, chạy migration, gửi message hoặc gọi một giao dịch thanh toán thật.
- Không khóa toàn cục và không chờ vô hạn vào DB/API.
- Có timeout và concurrency budget; probe không được tạo một dependency storm.
- Có thể báo lỗi qua HTTP status; body phục vụ chẩn đoán nhưng không chứa secret hoặc stack trace.
- Không phụ thuộc việc người dùng đã đăng nhập vào ứng dụng.
- Có status/metric rõ để vận hành biết vì sao chưa Ready.
- Kết quả ổn định đủ để không flap liên tục ở một ngưỡng quá sát.

Tách health phục vụ điều phối khỏi **diagnostic health** sâu dùng cho vận hành. Diagnostic endpoint có thể kiểm tra nhiều dependency, nhưng nó không nên bị kubelet gọi liên tục với chu kỳ ngắn nếu mỗi lần gọi tạo tải nặng.

## 6. Những dependency nào nên đưa vào readiness?

Đây là quyết định kiến trúc theo **khả năng phục vụ thật**. Không có quy tắc “readiness phải ping tất cả dependency”.

| Dependency/tình huống | Quyết định readiness thường hợp lý | Lý do |
| --- | --- | --- |
| Chưa nạp config bắt buộc, schema không hợp lệ | Not Ready / fail startup | Không thể phục vụ đúng |
| Chưa khởi tạo internal router, listener, worker | Not Ready | Chưa xử lý request được |
| DB bắt buộc cho mọi thao tác và không thể retry/circuit-break | Có thể Not Ready trong giai đoạn bootstrap; khi outage toàn cụm cần cân nhắc | Mọi Pod cùng unready có thể làm đường truy cập báo không còn backend |
| DB chỉ phục vụ một phần endpoint | Không nhất thiết loại toàn service; endpoint lỗi có kiểm soát | Các API khác vẫn có thể hữu ích |
| Cache có fallback tới DB hoặc stale data được phép | Thường vẫn Ready | Cache mất không phải mất khả năng phục vụ toàn bộ |
| Telemetry backend không truy cập được | Không nên làm liveness/readiness fail | Không thể để logging backend quyết định uptime ứng dụng |
| Payment API bên ngoài đang lỗi | Cân nhắc circuit breaker, degrade, trả lỗi có kiểm soát | Restart hoặc xóa toàn bộ Pod không chữa lỗi đối tác |
| Instance chuẩn bị tắt để rollout | Not Ready và ngừng nhận việc mới | Cho phép drain các request hiện tại |
| Worker đã ngừng poll broker vì shutdown | Worker không còn sẵn sàng nhận message mới | Phản ánh đúng vai trò consumer |

**Rủi ro cascade:** Nếu readiness của tất cả Pod gọi chung một database và database gặp outage, tất cả Pod có thể Not Ready đồng thời. Gateway/load balancer sẽ không còn backend, kể cả cho những endpoint không cần DB như cached read hoặc trả lỗi nghiệp vụ có kiểm soát. Do đó nên phân biệt **availability của dependency** với **capability của chính instance**.

Có thể thiết kế readiness trả về các khả năng bắt buộc của service, còn dependency state đưa vào metrics/circuit breaker và diagnostic health. Với service mà 100% công việc không thể tiến hành khi một dependency vắng mặt, readiness nên được quyết định theo SLO và behavior của các lớp phía trước, không chỉ theo thói quen “ping DB là được”.

## 7. Cấu hình Kubernetes Deployment với ba probe

Ví dụ cho một Java HTTP service có các endpoint health rõ ràng:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: orders
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
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: order-service
          image: registry.example.com/order-service:1.8.0
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
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            successThreshold: 1
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

**Lưu ý:** Đây là manifest minh họa. App phải thực sự có Actuator readiness/liveness endpoints đang hoạt động trên port 8080; tùy cấu hình Spring Boot, đường dẫn và actuator port có thể khác. Tag image mô tả ví dụ; khi rollout production cần quản lý digest/version được kiểm thử. Giá trị probes, số replica, grace period và rolling strategy phải chọn theo số đo và năng lực hạ tầng.

Ý nghĩa:

- Startup probe cho phép một cửa sổ bootstrap dài; trước khi pass, liveness/readiness chưa chạy.
- Readiness được gọi định kỳ để điều chỉnh việc tham gia nhận traffic.
- Liveness đủ ngưỡng thất bại sẽ restart container.
- terminationGracePeriodSeconds = 60 cho ứng dụng thời gian kết thúc có kiểm soát; nó bao gồm cả thời gian dành cho hook nếu có.
- maxUnavailable = 0 và maxSurge = 1 là một chiến lược rollout cho ví dụ ba replica; cần quota và scheduler còn chỗ cho Pod bổ sung.

**Không nhầm failureThreshold với tổng giây chính xác**: periodSeconds, timeoutSeconds, initialDelaySeconds, scheduling và probe execution ảnh hưởng thời điểm thực tế. Hãy đo trên cluster trong điều kiện CPU pressure/cold start thay vì tính theo công thức rồi mặc định đó là SLA tuyệt đối.

## 8. Startup chậm và sự phối hợp với liveness

Một Java/Spring Boot container có thể phải tạo dependency graph, validate configuration, khởi tạo connection pool, thực hiện một số warm-up và tải dữ liệu. Nếu liveness bắt đầu quá sớm, ứng dụng bị kill khi sắp khởi động xong; các lần restart lại làm cold start từ đầu.

Ví dụ timeline:

~~~text
t=0s     Container created
t=5s     Startup probe chưa thành công
t=20s    JVM init, dependency injection
t=45s    Cache warm-up
t=70s    App lắng nghe HTTP
t=75s    Startup probe success
t=80s    Readiness success => nhận traffic
~~~

Startup probe nên kiểm tra tín hiệu xác nhận tiến trình đã bootstrap được, không nên gắn một danh sách dependency không liên quan kéo dài startup. Nếu ứng dụng không thể khởi động vì config bắt buộc sai, nó nên fail startup với lỗi đã được redact; restart có thể tiếp tục xảy ra cho đến khi sửa cấu hình, nhưng không nên để app báo Ready giả.

**Không dùng liveness để bắt service chưa sẵn sàng.** Một app vẫn sống và đang tiếp tục bootstrap không cần bị restart chỉ vì chưa nhận request được. Khi startupProbe đã pass, liveness mới được sử dụng để bắt trạng thái không thể tự phục hồi.

## 9. Readiness trong rolling deployment

Một Deployment rollout tuần tự cần có ý nghĩa:

1. Controller tạo Pod phiên bản mới theo maxSurge/maxUnavailable và quota.
2. Pod mới chạy bootstrap/startup.
3. StartupProbe pass, readinessProbe bắt đầu xác định khả năng nhận traffic.
4. Khi Pod mới Ready, controller có thêm năng lực có thể sử dụng và tiếp tục tiến trình rollout.
5. Pod cũ được yêu cầu kết thúc, chuyển vào trạng thái terminating; traffic mới dần ngừng chuyển tới nó.
6. Pod cũ drain các request đang chạy, đóng kết nối và thoát trong grace period.
7. Hệ thống tiếp tục cho đến khi phiên bản mới đạt số replica/availability như mong muốn.

Điểm dễ bỏ sót là **readiness không đồng nghĩa “đã nhận request thành công trên toàn đường đi”**: readiness có thể pass nhưng ingress rule, mTLS, DB config hay service discovery chưa đúng. Bởi vậy rollout cần smoke test và theo dõi error rate/latency sau deploy.

Tùy cấu hình, `minReadySeconds` của Deployment có thể yêu cầu Pod ở trạng thái Ready liên tục một khoảng thời gian trước khi coi là Available. Nó giúp tránh tính một Pod vừa Ready rồi fail ngay như năng lực ổn định, nhưng không thay thế kiểm thử hoặc SLO gates.

**Khi chỉ có một replica**, chiến lược maxUnavailable = 0 phụ thuộc vào khả năng tạo Pod mới trước khi xóa Pod cũ, còn hoạt động kết nối và trạng thái dependency quyết định zero-downtime có đạt thật hay không. Không hứa “zero downtime” chỉ dựa vào manifest rollingUpdate.

## 10. Graceful shutdown: từ SIGTERM đến hoàn tất request

Khi Pod bị xóa hoặc rollout, Kubernetes khởi tạo quá trình termination theo grace period. Thông thường kubelet chạy preStop hook nếu có, sau đó gửi tín hiệu TERM cho process chính trong container; khi hết thời gian cho phép, runtime có thể kết thúc cưỡng bức.

~~~text
Pod deletion requested
       |
       v
Mark terminating / update endpoint state
       |
       v
preStop hook (if configured)
       |
       v
SIGTERM to main process
       |
       v
Application enters draining state
       |
       +-- stop accepting new HTTP connections/work
       +-- stop broker polls or new job acquisition
       +-- finish/cancel in-flight by deadline
       +-- flush/commit messages and state safely
       +-- close external resources
       |
       v
Process exits
       |
       v
Container termination complete
~~~

Tín hiệu EndpointSlice/Service route và việc dừng nhận request có thể không đến mọi proxy ngay lập tức. HTTP keep-alive, HTTP/2 multiplexing, mesh sidecar hoặc long-lived stream còn khiến một Pod nhận thêm công việc sau khi bắt đầu termination. Ứng dụng phải chủ động chuyển sang draining và có chính sách từ chối/hoàn tất công việc mới.

### 10.1. Trình tự an toàn trong ứng dụng

- Chuyển application state sang **DRAINING**, làm readiness fail hoặc công bố không nhận việc mới trước khi đóng logic phục vụ.
- Ngừng lắng nghe job mới hoặc tạm dừng consumer/poller theo cơ chế broker.
- Cho request đang chạy hoàn thành trong một **in-flight budget**.
- Với request kéo dài hơn budget, trả lỗi/cancel có kiểm soát, dùng idempotency/recovery để không làm mất side effect.
- Flush buffered logs/metrics trong giới hạn nhỏ; không làm shutdown phụ thuộc mãi vào telemetry.
- Commit/ack message sau durable completion, không commit chỉ vì ứng dụng sắp tắt.
- Đóng listener, thread pools và database connections; đảm bảo shutdown hook được thực thi.

Tùy giao thức, HTTP server có thể chặn request mới và chờ request cũ; TCP/gRPC/WebSocket có cơ chế khác như GOAWAY hoặc close handshake. Ứng dụng có streaming RPC dài phải quy định **drain timeout** và reconnect behavior.

### 10.2. PreStop hook và grace period

`preStop` chạy **trước tín hiệu TERM**, và thời gian hook tính vào terminationGracePeriodSeconds. Một hook sleep dài có thể chiếm hết ngân sách, khiến khi ứng dụng cuối cùng nhận TERM thì gần như không còn thời gian xử lý in-flight.

Ví dụ `preStop: sleep 10s` đôi khi giúp proxy kịp cập nhật routing, nhưng chỉ là một biện pháp tạm khi đã đo propagation delay. Nó không thay thế việc server thật sự hỗ trợ graceful shutdown. Nếu dùng preStop để gọi endpoint “drain” thì endpoint phải chuyển state an toàn, idempotent và không yêu cầu credential lộ trong manifest.

**Chọn thời gian theo tổng chi phí:** propagation delay + long-running request deadline + broker commit/outbox + resource close + margin. Tăng grace period quá lớn có thể làm rollout kéo dài và tiêu tốn Pod quota; quá nhỏ làm mất request/đứt message giữa chừng.

## 11. Ví dụ Spring Boot Actuator với liveness/readiness

Spring Boot có ApplicationAvailability với các trạng thái:

- **LivenessState:** phản ánh tình trạng hoạt động nội bộ như CORRECT/BROKEN.
- **ReadinessState:** phản ánh có chấp nhận traffic mới như ACCEPTING_TRAFFIC/REFUSING_TRAFFIC.

Khi cấu hình phù hợp, Actuator có các nhóm probe:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info

server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Ví dụ trên dành cho ứng dụng Spring Boot hỗ trợ các property tương ứng; hãy đối chiếu phiên bản framework và các port/path thực tế. Việc bật probes/Actuator và exposing endpoints phải tuân thủ chính sách bảo mật deployment.

Các endpoint theo nhóm:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Nếu Actuator chạy ở management port riêng, endpoint có thể báo khỏe trong khi main application port không nhận request do worker/thread pool của app bị nghẽn. Khi mục đích là kiểm tra đường phục vụ chính, cân nhắc exposing probe groups trên main server port hoặc có một kiểm tra nội bộ phù hợp, tùy framework.

**Không thêm ping DB vào liveness:** Liveness trong Spring Boot nên dựa vào trạng thái nội bộ. Với readiness, việc thêm DB health indicator phải được cân nhắc theo phần 6; không tự đưa tất cả health indicators vào readiness group.

### 11.1. Readiness khi bắt đầu drain

Một ứng dụng có thể công bố readiness không chấp nhận traffic trong quá trình shutdown:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class DrainController {
    private final ApplicationContext context;

    public DrainController(ApplicationContext context) {
        this.context = context;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
            context, ReadinessState.REFUSING_TRAFFIC
        );
    }
}
~~~

Đây là minh họa cách phát trạng thái ứng dụng. Cần gọi nó tại điểm bắt đầu draining phù hợp với lifecycle của app và đảm bảo các listener thật sự ngừng nhận việc mới. Việc publish một sự kiện readiness **không tự chặn kết nối TCP mới**, cũng không đảm bảo mọi reverse proxy ngừng định tuyến tức thời.

Trong Spring Boot, khả năng graceful shutdown của embedded server, handling của request và cách phản hồi khi shutdown phụ thuộc container/server và phiên bản; test thực tế với server đang dùng thay vì mặc định hành vi giống nhau giữa Tomcat, Jetty, Netty.

## 12. Gắn probe với vòng đời bất đồng bộ và message consumer

Health của một service chỉ xử lý HTTP khác với một Kafka/RabbitMQ worker. Consumer có thể không có endpoint business HTTP, nhưng vẫn cần thể hiện trạng thái tiếp nhận công việc.

Ví dụ vòng đời consumer:

~~~text
STARTING
  -> connect broker
  -> subscribe / join consumer group
  -> assignment ready
  -> RUNNING (nhận message)
  -> DRAINING (ngừng lấy message mới)
  -> hoàn thành hoặc chuyển giao in-flight
  -> commit/ack an toàn
  -> STOPPED
~~~

Readiness của worker không nhất thiết chỉ là “broker reachable”. Nên phản ánh **consumer đã sẵn sàng xử lý message** hay chưa; ví dụ đã có assignment nếu ứng dụng đòi hỏi assignment trước khi nhận nhiệm vụ. Nếu worker không có inbound Service HTTP, readiness vẫn có thể hữu ích cho Pod condition/rollout semantics, nhưng việc tắt readiness **không tự tạm dừng Kafka consumer**. Worker phải chủ động pause/stop polling và bảo vệ in-flight.

Đối với Kafka:

- Ngừng nhận batch mới hoặc pause các partition theo API phù hợp; giữ group protocol/rebalance được xử lý đúng cho đến khi shutdown.
- Hoàn tất record đang chạy, commit **chỉ những offset xử lý thành công liên tục** theo partition, không nhảy qua record còn dở.
- Khi Pod mất assignment, xử lý rebalance và idempotency để tránh side effect trùng.
- Nếu timeout trong khi drain, phần chưa hoàn tất có thể được redeliver; consumer phải xử lý an toàn.

Đối với RabbitMQ:

- Dừng nhận delivery mới, quản lý prefetch và unacked messages.
- Ack chỉ khi side effect hoàn tất; nếu ngắt kết nối trước ack, broker có thể redeliver.
- Không ném tất cả message về queue với requeue ngay vô hạn; chính sách retry/DLQ phải có giới hạn.

Đối với scheduled jobs, cần cấm bắt đầu job mới khi DRAINING, lưu checkpoint hoặc sử dụng lease/lock có expiry. Một worker có thể live nhưng không ready để nhận thêm nhiệm vụ, và điều đó không có nghĩa phải restart.

## 13. Health probe và quá tải: tránh restart storm

Một service quá tải có thể làm liveness endpoint chậm vì tranh CPU hoặc thread. Nếu liveness quá nhạy, kubelet restart hàng loạt Pod. Restart khiến cache mất, kết nối DB được tạo lại, cold start tăng và tải dồn sang những Pod còn chạy — dễ tạo vòng xoáy.

Các biện pháp:

1. Probe phải nhẹ, deadline nhỏ nhưng **failureThreshold đủ chịu được jitter** của CPU scheduling và GC pause bình thường.
2. Đo p99 thời gian phản hồi health endpoint khi load test. Không giả định kiểm tra nhanh trong môi trường nhàn rỗi là đủ.
3. Readiness có thể phản ánh admission control nếu Pod đã quá tải kéo dài, nhưng cần hysteresis để tránh “flapping”.
4. Sử dụng bounded queue, concurrency limit, rate limiting, load shedding thay vì đẩy mọi bài toán quá tải vào liveness.
5. Ưu tiên phân bổ tài nguyên để health handler còn cơ hội chạy, nhưng không dành một thread riêng báo xanh giả khi business event loop hoàn toàn chết.
6. Nếu mọi Pod cùng Not Ready vì overload, traffic có thể không có backend để gửi; cân nhắc cân bằng giữa trả 503 có kiểm soát và loại hoàn toàn khỏi endpoint.
7. Giữ liveness độc lập với external API lỗi vì restart không sửa được dependency.

Ví dụ có 3 Pod, mỗi Pod xử lý bền vững 100 req/s. Khi traffic tăng 500 req/s, việc cả 3 Pod cùng fail liveness rồi restart không tạo được năng lực mới; tổng năng lực còn tạm bằng 0 trong cold start. Giải pháp cần kiểm soát admission, scale nếu dependency cho phép và xử lý quá tải có chủ đích.

## 14. Tuning ngưỡng và tránh dao động

Những tham số thường có:

| Tham số | Ý nghĩa | Cách chọn |
| --- | --- | --- |
| periodSeconds | Chu kỳ probe thông thường | Đủ phát hiện nhanh nhưng không gây tải |
| timeoutSeconds | Timeout mỗi lần probe | Hợp với p99 probe dưới tải + margin |
| failureThreshold | Số lần thất bại liên tiếp trước hành động | Phù hợp ngưỡng lỗi có thể tự phục hồi |
| successThreshold | Số lần thành công liên tiếp để coi lại là healthy | Dùng để tránh flapping với readiness; liveness/startup bị giới hạn theo Kubernetes |
| initialDelaySeconds | Trễ ban đầu trước probe | Có thể dùng, nhưng startupProbe rõ hơn cho app cold start dài |
| terminationGracePeriodSeconds | Khoảng thời gian cho termination | Đủ drain và close, không kéo dài vô ích |

Readiness có thể sử dụng một state machine thay vì gắn trực tiếp vào ngưỡng CPU hoặc queue:

~~~text
READY:
  queue_depth >= HIGH for sustained period
      -> NOT_READY

NOT_READY:
  queue_depth <= LOW for recovery window
      -> READY
~~~

HIGH và LOW khác nhau tạo hysteresis. Tuy nhiên trong nhiều hệ thống, **load shedding bằng HTTP 429/503 tại admission** mang lại hành vi dự đoán tốt hơn việc liên tục rút Pod khỏi Service. Khi readiness flapping, rollout và traffic balancing cũng dao động.

Không đặt `timeoutSeconds: 1` chỉ vì đó là mặc định phổ biến nếu ứng dụng Java chịu GC pause hoặc CPU throttling vượt một giây ở tải dự kiến. Ngược lại, timeout hàng chục giây cho liveness làm chậm phát hiện deadlock. Chọn theo dữ liệu quan sát và mô hình failure.

## 15. Probe đơn giản có thể tạo kết luận sai

### TCP liveness “cổng mở = sống”

Cổng TCP có thể vẫn mở nhưng endpoint bị kẹt vì worker pool cạn hoặc deadlock. Nếu chỉ dùng TCP, liveness không phản ánh khả năng thực thi. Dùng HTTP nội bộ hoặc heartbeat progress của luồng quan trọng khi thích hợp.

### Readiness ping mọi downstream

Mỗi lần readiness gọi DB, Redis, broker và 10 HTTP APIs sẽ tạo nhiều traffic kiểm tra. Khi một provider gặp outage, tất cả Pod cùng chuyển Not Ready; việc probe thất bại còn làm tăng tải ở provider. Chỉ kiểm tra những capability cần thiết và cân nhắc dùng trạng thái đã được cập nhật bởi bộ giám sát nội bộ có rate limit.

### Liveness dựa vào database connection

DB outage tạm thời khiến mọi container restart đồng loạt; kết nối mới và migration retry có thể gây thảm họa thứ cấp. Liveness nên phát hiện lỗi mà restart container có thể giải quyết.

### Endpoint readiness luôn trả 200

Nếu chưa load config, chưa khởi tạo worker hoặc đã bắt đầu drain mà endpoint vẫn trả 200, orchestrator sẽ gửi request vào instance chưa/không còn khả năng xử lý.

### Mọi probe dùng cùng một endpoint “/health”

Khó phân biệt nguyên nhân và hành động: một lỗi dependency sẽ đồng thời làm liveness restart, readiness loại Pod và startup fail. Tách semantic của từng endpoint dù response JSON đều có status.

### Endpoint health có auth redirect

Nếu thiếu quyền, endpoint trả 302 tới trang login; HTTP probe có thể coi redirect là thành công. Health handler phải có HTTP status trực tiếp và bảo vệ truy cập bằng port/network/identity theo kiến trúc.

### Probe không đi qua đường xử lý chính

Endpoint chạy trên management thread pool riêng có thể báo live trong khi web server chính không xử lý request. Phải biết mình đang kiểm tra JVM process, server lắng nghe hay capability thực sự. Thiết kế probe/metrics bổ sung theo nhu cầu.

## 16. Security: endpoint nào được công khai?

Health endpoints không nên tiết lộ password, token, DSN, tên host nội bộ chi tiết hoặc stack trace. Nội dung công khai chỉ nên đủ cho orchestration (200/503). Diagnostic health dành cho vận hành có thể có thông tin dependency nhưng cần authentication/RBAC và hạn chế quyền đọc.

Một lựa chọn triển khai:

- Cho kubelet probe truy cập Pod IP và cổng health nội bộ bằng cấu hình phù hợp.
- Không mở endpoint diagnostic chi tiết qua public ingress.
- Chỉ expose nhóm readiness/liveness cần thiết, body tối giản.
- Không yêu cầu login redirect cho kubelet probe.
- Giới hạn traffic tới management port bằng network policy hoặc chính sách tương đương; lưu ý đường đi thực tế của probe từ node/kubelet.
- Không chứa secret trong reason hoặc exception message.
- Có log và metric khi readiness/liveness chuyển trạng thái, tránh ghi log mỗi 5 giây cho một probe thành công.
- Nếu dùng service mesh sidecar/probe rewriting, xác minh endpoint mà kubelet thực sự gọi và ảnh hưởng của sidecar readiness.

**Probe không phải security control.** Một Pod healthy không đồng nghĩa người gọi được phép truy cập API. Authorization, mTLS, network policy và validation vẫn phải được thực thi ở đường đi request thật.

## 17. Deployment và PodDisruptionBudget

Health probe liên quan chặt với rollout vì Deployment controller quan sát Pod Ready/Available. Nhưng có thêm yếu tố:

- **maxSurge:** cho phép tạo thêm Pod trong rolling update; cần quota/CPU memory để Pod mới schedule được.
- **maxUnavailable:** giới hạn số Pod unavailable trong rolling update theo strategy; chọn theo năng lực và SLO.
- **minReadySeconds:** yêu cầu Ready ổn định một khoảng trước khi tính Available.
- **progressDeadlineSeconds:** giới hạn tiến độ triển khai theo controller, giúp phát hiện rollout bị kẹt.
- **PodDisruptionBudget (PDB):** giúp bảo vệ số Pod available trong một số tình huống voluntary eviction; **không thay thế** cấu hình strategy cho Deployment và không bảo vệ khỏi mọi loại outage hoặc crash.
- **Readiness gates:** có thể dùng thêm tín hiệu bên ngoài Pod khi thực sự cần, nhưng phải vận hành/đặt condition tương ứng.

Một Pod thiếu readinessProbe có thể được coi ready sau khi container start theo các điều kiện khác, dù ứng dụng còn chưa nạp cache. Vì vậy probe là hợp đồng quan trọng giữa application và orchestrator.

**Rollout test không chỉ kiểm tra số replica:** cần kiểm tra Pod mới Ready, traffic thực sự thành công, Pod cũ drain, error rate không tăng bất thường và hệ thống có thể rollback phiên bản nếu cấu hình/schemas tương thích.

## 18. Graceful shutdown ở HTTP, gRPC và WebSocket

### HTTP đồng bộ

Đặt readiness thành Not Ready khi drain, dừng nhận request mới theo khả năng server, cho in-flight chạy đến deadline, trả lỗi có kiểm soát với request chưa thể hoàn tất. Với request có side effect, phải có idempotency/reconciliation vì client có thể timeout trước khi server commit.

### HTTP keep-alive và HTTP/2

Một kết nối đang mở có thể tiếp tục truyền request khi Pod bắt đầu terminating. Không xem “đã cập nhật EndpointSlice” là lời bảo đảm rằng proxy đã đóng mọi kết nối. Server/proxy cần hỗ trợ connection draining và ngừng tiếp nhận request mới.

### gRPC

Với kết nối gRPC dài hạn, ứng dụng cần cơ chế graceful stop hoặc gửi tín hiệu đóng kết nối phù hợp. Nếu có streaming RPC dài hơn grace period, không thể chờ vô hạn; thiết kế reconnection, cursor/checkpoint và deadline.

### WebSocket/SSE

Long-lived connection có thể vượt nhiều phút. Khi Pod termination, phát tín hiệu đóng/reconnect nếu giao thức hỗ trợ, lưu state bền vững và đảm bảo client có backoff/reconnect. Probe Ready không tự di chuyển một WebSocket đang mở sang Pod khác.

### Background task

Không giữ graceful shutdown chỉ để chờ một task có thể chạy hàng giờ nếu grace period vài chục giây. Job cần checkpoint, lease/fencing hoặc chia nhỏ thành đơn vị idempotent để tiếp tục sau khi Pod mới nhận công việc.

## 19. Sự khác nhau giữa liveness và khả năng tiến triển của ứng dụng

Một process có thể đáp ứng `/health/live` trong khi tất cả request nghiệp vụ đang chờ vì thread pool cạn. Ngược lại, một service xử lý batch vẫn khỏe dù trong vài giây không có message để xử lý.

Để quan sát khả năng tiến triển, bổ sung các metric:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| http_server_requests_in_flight | Số request đang xử lý |
| http_request_duration p95/p99 | Độ trễ thực tế người dùng thấy |
| executor_active_threads / queue_depth | Saturation nội bộ |
| event_loop_lag | Event loop đang trễ |
| last_successful_message_timestamp | Consumer có hoàn tất công việc gần đây hay không |
| consumer_lag / oldest_message_age | Backlog broker và khả năng drain |
| database_pool_active/pending | Sự chờ connection |
| readiness_state_changes_total | Tần suất vào/ra Not Ready |
| container_restarts_total | Hậu quả của liveness/startup failure |
| probe_duration_seconds | Chi phí và tail latency của probe |
| termination_drain_seconds | Thời gian chờ in-flight khi shutdown |

Không nên đặt toàn bộ các metric trên thành điều kiện liveness tức thời. Metric giúp SRE tìm nguyên nhân, còn probe nên thực hiện quyết định điều phối đơn giản, ổn định và có khả năng khôi phục.

## 20. Kiểm thử probe trong CI

Health behavior là một phần hợp đồng vận hành; có thể kiểm thử như business behavior.

### 20.1. Startup

- Khi thiếu config bắt buộc, app không báo ready giả; có lỗi rõ và không chứa secret.
- Khi khởi động chậm trong budget, startupProbe có thời gian chờ phù hợp và không bị liveness restart sớm.
- Khi bootstrap không thể hoàn tất, container không đứng vô hạn ở trạng thái nhận traffic giả.
- Khi đã khởi động, readiness đáp ứng từ true/false theo capability.

### 20.2. Readiness

- Trước khi khởi tạo xong, HTTP readiness trả 503 hoặc trạng thái fail đúng contract.
- Sau khi thành công, trả 200 và Pod được đưa vào endpoint sau khi controller/kubelet quan sát.
- Khi bắt đầu drain, readiness chuyển Not Ready và app dừng nhận việc mới.
- Khi dependency bắt buộc tạm lỗi, readiness hành xử đúng chính sách thay vì tất cả Pod cùng flap vô lý.
- Khi phục hồi từ Not Ready có thể trở lại Ready mà không cần restart, nếu đó là trạng thái có thể tự phục hồi.

### 20.3. Liveness

- App đang hoạt động bình thường trả thành công nhanh ngay cả dưới tải dự kiến.
- Lỗi kết nối telemetry hoặc external API riêng lẻ không làm liveness fail.
- Một trạng thái deadlock/hỏng nội bộ mà restart có thể khắc phục được dẫn đến liveness fail sau ngưỡng.
- Không có phản hồi “healthy” giả từ management port khi đường xử lý chính đã hoàn toàn tắc mà không có giám sát bổ sung.

### 20.4. Graceful termination

- Gửi SIGTERM trong lúc có request đang chạy; request đủ ngắn hoàn thành, request dài xử lý theo deadline.
- Sau khi drain, app không nhận thêm job/message mới và cleanup connection đúng.
- Consumer không ack/commit message chưa xử lý xong.
- Broker redelivery và client retry không tạo tác động nghiệp vụ trùng.
- App thoát trước terminationGracePeriodSeconds đã chọn với điều kiện tải phù hợp.
- Sau rollout, không có spike 5xx/timeout vượt ngưỡng chấp nhận.

Các kiểm thử ở mức đơn vị/component có thể chủ động đổi trạng thái lifecycle; một số test phải chạy trên Kubernetes/Compose để chứng minh tác động thật tới routing, TERM signal và thời gian kết thúc.

## 21. Ví dụ test ngữ nghĩa readiness trong Spring Boot

Có thể kiểm tra trạng thái Availability qua application context hoặc gọi endpoint thực bằng WebTestClient/TestRestTemplate tùy server và stack. Một ví dụ logic đơn giản:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class AvailabilityTransitionTest {
    private final ApplicationContext context;
    private final ApplicationAvailability availability;

    AvailabilityTransitionTest(
        ApplicationContext context,
        ApplicationAvailability availability
    ) {
        this.context = context;
        this.availability = availability;
    }

    @Test
    void entersRefusingTrafficDuringDrain() {
        AvailabilityChangeEvent.publish(
            context, ReadinessState.REFUSING_TRAFFIC
        );

        assertThat(availability.getReadinessState())
            .isEqualTo(ReadinessState.REFUSING_TRAFFIC);
    }
}
~~~

Đây là **khung minh họa**, không phải class JUnit chạy độc lập nguyên trạng: cần khởi tạo Spring test context để inject ApplicationContext/ApplicationAvailability và dọn/khôi phục state sau test. Để kiểm tra đầy đủ, gọi HTTP endpoint và xác minh response status, sau đó kiểm tra hành vi ngừng nhận request hoặc chuyển Pod endpoint khi chạy Kubernetes. Đừng coi một unit assertion trên enum là đã chứng minh toàn bộ cluster drainage.

### Kịch bản kiểm thử triển khai

~~~text
Given: 3 replicas Ready, có request kéo dài 15 giây
When: rollout image version mới
Then:
  - Pod mới không nhận traffic trước readiness OK
  - Pod cũ đánh dấu terminating và giảm new requests
  - In-flight request kết thúc trong grace budget nếu được hỗ trợ
  - Không mất business transaction
  - Không có spike lỗi/timeout ngoài SLO
  - Pod mới Ready và service tiếp tục có năng lực phục vụ
~~~

Cần thu các mốc: Pod deletionTimestamp, readiness transitions, EndpointSlice, SIGTERM delivery, server stop, request completion, container exit và error metrics. Kiểm tra trong môi trường có sidecar/ingress thật nếu chính chúng là một phần rủi ro.

## 22. Incident runbook: Pod restart liên tục

**Triệu chứng:** Một loạt Pod tăng restart count, ứng dụng thỉnh thoảng trả 503 và Kubernetes events ghi liveness/startup probe failed.

Quy trình điều tra:

1. Xem events và tình trạng container: lý do restart, exit code, startup/liveness timeout hay OOMKilled.
2. Đối chiếu thời điểm restart với deploy, GC pause, CPU throttling, heap pressure và latency của probe.
3. Kiểm tra endpoint liveness có gọi downstream hay chạy query nặng không.
4. Xác minh startupProbe có đủ budget so với cold start thật và readiness có bị kích hoạt sớm không.
5. Nếu tất cả Pod restart cùng lúc khi DB lỗi, phân tách DB khỏi liveness và xem lại chiến lược readiness.
6. Nếu Pod bị kill khi đang drain, kiểm tra preStop hook, SIGTERM, timeout của server và termination grace.
7. Thực hiện thay đổi nhỏ có kiểm soát, dùng load test để chứng minh không còn restart storm.
8. Theo dõi restart count, 5xx, p99 latency, thời gian Ready và availability sau thay đổi.

Không nên chỉ tăng failureThreshold vô hạn để che một deadlock thực sự. Cần phân biệt **false positive probe** với **process thật sự không thể phục hồi**.

## 23. Incident runbook: Pod Running nhưng không nhận traffic

**Triệu chứng:** Container Running, CPU bình thường, nhưng Service không gửi request đến Pod hoặc rollout bị kẹt.

Kiểm tra lần lượt:

- Pod Ready condition có false không? Container readinessProbe nào thất bại?
- Pod có nhiều container/sidecar không? Một sidecar hoặc readiness gate có đang giữ Pod chưa Ready?
- Probe path/port/scheme có đúng, có bị 302 redirect hoặc 401 do auth không?
- Application bind 127.0.0.1 trong container hay Pod IP interface, trong khi kubelet probe theo Pod IP?
- Network policy, service mesh hoặc rewrite probe có can thiệp đường probe không?
- App đã start xong nhưng readiness chờ dependency nào? Kiểm tra state transition và logs đã redact.
- Service selector, endpoint slices, targetPort và DNS có khớp Pod labels/ports không?
- Có tình huống tất cả Pod Not Ready do một shared dependency hoặc aggressive overload readiness không?

Một Pod Running chưa chắc Ready. Một Pod Ready chưa chắc public ingress đã có route đúng. Dùng dữ liệu từ từng tầng để khoanh lỗi thay vì restart mù.

## 24. Incident runbook: lỗi tăng trong rolling deployment

Nếu sau khi deploy số request timeout/502/503 tăng, kiểm tra:

1. Pod mới có báo Ready quá sớm trước bootstrap hoặc cache warm-up không.
2. Pod cũ đã bắt đầu termination nhưng proxy còn gửi request mới qua keep-alive/h2 connection không.
3. App có gọi graceful shutdown và đủ thời gian drain không.
4. preStop hook có chiếm phần lớn grace period không.
5. Consumer job có bị cancel giữa chừng, ACK quá sớm hoặc thiếu idempotency không.
6. EndpointSlice, ingress và service mesh cập nhật trạng thái terminating ở thời điểm nào.
7. Rollout strategy có đủ maxSurge/resource quota để không giảm số Pod phục vụ xuống quá thấp không.
8. Phiên bản mới có schema/config incompatibility với phiên bản cũ trong cửa sổ rollout không.

Có thể rollback artifact nếu tương thích, nhưng rollout lỗi đôi khi do config, secret, DB migration hoặc policy. Phải xác định root cause trước khi lặp lại deployment.

## 25. Các nguyên tắc vận hành bổ sung

### 25.1. Probe không thể thay metrics và synthetic transactions

Readiness/liveness là tín hiệu nhị phân cho orchestrator. Chúng không đủ để phát hiện request thành công nhưng trả dữ liệu sai, p99 latency tăng hoặc một phần workflow bị lỗi. Cần SLO metrics, tracing và synthetic transaction có kiểm soát khi nghiệp vụ quan trọng.

### 25.2. Kết quả probe không phải SLA tuyệt đối

Khoảng phát hiện lỗi phụ thuộc period/threshold/timeout, scheduler và kubelet execution. Endpoint state propagation tới proxy có độ trễ. Chỉ khi đo thực tế mới biết thời gian mất và phục hồi traffic.

### 25.3. Probe dùng tài nguyên thật

Mỗi Pod gọi health endpoint nhiều lần mỗi phút. Với 1.000 Pod và period 5 giây, hệ thống có khoảng 200 health requests mỗi giây chỉ tính một loại probe; nếu mỗi probe gọi DB, tải kiểm tra lan sang DB. Giữ nội dung probe nhẹ và ưu tiên đọc state đã biết.

### 25.4. Không dồn mọi quyết định vào một boolean

Một service có thể live nhưng đang degrade, còn HTTP nhưng mất broker consumer, hoặc chỉ một endpoint không hoạt động. Trạng thái điều phối nên đơn giản, còn nguyên nhân chi tiết được thể hiện qua metric/diagnostic health để tránh quyết định restart hoặc loại Pod quá rộng.

### 25.5. Phân tách trách nhiệm

- **Ứng dụng:** định nghĩa trạng thái live/ready/draining, hỗ trợ shutdown và idempotency.
- **Orchestrator:** thực thi probe, restart, endpoint management và rollout.
- **Gateway/mesh:** cập nhật routing và connection draining theo trạng thái thực.
- **Operations/SRE:** SLO, dashboard, alert, incident runbook và chính sách rollout.
- **CI:** kiểm tra transition và termination trong kịch bản sự cố có thể lặp lại.

## 26. Bảng sai lầm phổ biến

| Sai lầm | Hệ quả | Cách tiếp cận đúng |
| --- | --- | --- |
| Dùng cùng /health nặng cho cả ba probes | DB lỗi khiến restart storm | Tách startup/readiness/liveness theo semantic |
| Liveness ping database | Mọi Pod restart vì outage chung | Liveness dựa vào tiến trình và state nội bộ |
| Readiness luôn 200 từ khi port mở | Traffic tới trước bootstrap | Phản ánh khả năng nhận việc thật |
| Liveness quá sớm | Kill ứng dụng đang khởi động | StartupProbe và cold-start budget |
| TCP probe được coi tương đương xử lý nghiệp vụ | Port mở khi app deadlock | HTTP/progress probe phù hợp |
| Probe trả 302 tới login | Redirect có thể bị xem là success | Endpoint health trả 200/503 trực tiếp |
| Health endpoint log secret/stack trace | Lộ dữ liệu vận hành | Body tối giản, diagnostic endpoint bảo vệ |
| Probe gọi hàng chục downstream mỗi 5 giây | Tạo thêm tải và cascade | Kiểm tra nhẹ, dependency status có cache |
| Readiness flap khi CPU tăng nhất thời | Endpoint/rollout dao động | Hysteresis, failure threshold, admission control |
| preStop sleep hết grace period | Không đủ thời gian drain | Chia ngân sách termination rõ |
| Chỉ gửi SIGTERM nhưng không dừng job mới | Job bị kill giữa chừng | Drain state, stop acquisition, checkpoint |
| Ack event trước xử lý xong | Mất message khi shutdown | Ack/commit sau durable completion |
| Không xử lý duplicate/retry | Double charge/side effect | Idempotency và reconciliation |
| Gán Pod Ready bằng việc port mở | Không thấy lỗi config/dependency | Readiness contract theo capability |
| Quá tin readiness cho zero downtime | 502/503 lúc endpoint propagation | Connection draining và test rollout thực |
| Rollout chỉ nhìn số replicas | Có Pod Ready nhưng business lỗi | Smoke/SLO gating, quan sát user traffic |
| Không kiểm tra sidecar/readiness gates | Pod cứ Not Ready khó hiểu | Quan sát Pod conditions toàn Pod |

## 27. Checklist thiết kế và triển khai

- [ ] Xác định rõ startup, readiness, liveness khác nhau và mục đích hành động tương ứng.
- [ ] Có startupProbe nếu cold start có thể vượt liveness budget bình thường.
- [ ] Liveness chỉ fail khi restart có khả năng sửa lỗi nội bộ.
- [ ] Readiness biểu thị khả năng nhận công việc mới theo SLO/capability của service.
- [ ] Health endpoints phản hồi nhanh, không có side effect và không truy cập secret không cần thiết.
- [ ] Không trả redirect/auth page khiến kubelet hiểu nhầm probe.
- [ ] Probe không gọi mọi dependency theo chu kỳ; tránh cascade khi upstream outage.
- [ ] HTTP/gRPC/TCP/exec probe được chọn theo kiến trúc và đúng port/path.
- [ ] Timeout, period, threshold được chọn qua cold-start/load-test metrics.
- [ ] Service có trạng thái STARTING → READY → DRAINING → STOPPED rõ.
- [ ] Khi drain, app dừng nhận request/job mới và cho in-flight hoàn tất theo deadline.
- [ ] SIGTERM, preStop và terminationGracePeriodSeconds được tính ngân sách chung.
- [ ] Không ack/commit message trước khi durable completion; hỗ trợ redelivery/idempotency.
- [ ] Rolling deployment có resource budget, strategy, readiness và smoke test phù hợp.
- [ ] Quan sát restart count, readiness transitions, probe latency và drain duration.
- [ ] Health endpoint có chính sách network/access rõ, không lộ secret hoặc stack trace.
- [ ] CI kiểm thử startup chậm, failed dependency, overload, SIGTERM và rollover.
- [ ] Test triển khai thật kiểm tra traffic routing/termination với ingress/sidecar sử dụng thực.
- [ ] Có runbook cho CrashLoopBackOff, Pod Running Not Ready và rollout tăng 5xx.

## 28. Câu hỏi thường gặp

**Health probe có phải chỉ là HTTP GET /health trả 200?**

Không. HTTP GET là một cách triển khai. Điều quan trọng là mỗi loại probe đại diện đúng một quyết định: startup đã xong chưa, Pod hiện nên nhận traffic không, và process có cần restart để hồi phục không.

**Có nên đưa database vào liveness?**

Thường không. Database outage chung không được sửa bằng cách restart toàn bộ Pod. Hãy xem readiness, circuit breaker, error handling và metrics theo yêu cầu nghiệp vụ; chỉ fail liveness khi trạng thái nội bộ thực sự cần restart.

**Nếu readiness fail thì Kubernetes có restart container không?**

Không phải do readiness failure đơn thuần. Pod bị coi chưa sẵn sàng nhận traffic qua Service; liveness/startup failure hoặc lý do container khác mới có thể gây restart.

**StartupProbe có luôn cần không?**

Không bắt buộc nếu ứng dụng bootstrap ổn định và liveness được cấu hình phù hợp. Nó đặc biệt hữu ích khi cold start dài hoặc dao động, vì bảo vệ app khỏi liveness trong giai đoạn khởi động.

**Có thể dùng TCP probe thay HTTP probe không?**

Có, nhưng TCP chỉ chứng minh kết nối đến port mở được, không chứng minh business handler đang xử lý tốt. Chọn theo failure mode cần phát hiện.

**Readiness fail khi một API bên ngoài bị lỗi có đúng không?**

Tùy ảnh hưởng của API đó đến toàn bộ khả năng phục vụ. Nếu các route khác vẫn có thể trả lời hoặc service chủ động degrade, làm tất cả Pod Not Ready có thể gây outage lớn hơn. Thiết kế readiness theo capability và đo cách hệ thống phản ứng khi dependency outage.

**preStop sleep có đảm bảo zero downtime không?**

Không. Sleep chỉ có thể dành thời gian cho endpoint propagation; nó tiêu thụ grace period và không thay server graceful shutdown. Cần dừng nhận traffic, drain, xử lý keep-alive/gRPC/worker và kiểm thử thực tế.

**Nếu dùng Spring Boot Actuator thì đã đủ chưa?**

Actuator cung cấp endpoint và lifecycle states hữu ích nhưng không quyết định thay thiết kế: dependency nào tác động readiness, lúc nào drain, timeout bao nhiêu, HTTP server có graceful stop không, và rollout có giữ SLO không. Phải tích hợp với Kubernetes YAML, client retry và messaging semantics.

**Có thể dùng readiness để làm load balancing dựa theo CPU không?**

Có thể nhưng nên thận trọng. Flapping readiness khi CPU gần ngưỡng có thể làm traffic dồn qua lại và giảm capacity. Admission control/rate limiting, concurrency budget và autoscaling theo resource/latency thường là các cơ chế chính; readiness dùng khi Pod thực sự không nên nhận thêm việc.

**Vì sao Pod Ready nhưng 502 vẫn tăng khi rollout?**

Endpoint update có thể trễ, proxy còn kết nối cũ, server thoát trước khi drain hoặc config/network route mới sai. Readiness chỉ là một phần của cơ chế chuyển traffic; kiểm tra SIGTERM, preStop, grace period, keep-alive, mesh/ingress và SLO.

---

**Nguyên lý ghi nhớ:** *Startup trả lời khi nào ứng dụng đã khởi tạo được; readiness trả lời khi nào instance nên nhận công việc mới; liveness trả lời khi nào cần restart để tự phục hồi. Ba tín hiệu đó chỉ hữu ích khi được gắn với một vòng đời ứng dụng có trạng thái rõ, graceful shutdown thật, thời hạn xử lý in-flight, bảo vệ dependency và kiểm thử rollout thực tế.*