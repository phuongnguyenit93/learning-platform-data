# Dừng nhận yêu cầu và hoàn tất công việc trước khi tắt

> **Chủ đề:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Triển khai dịch vụ (Service Deployment)  
> **Trọng tâm:** Graceful shutdown, connection draining, ngừng nhận công việc mới, chờ công việc đang chạy hoàn tất, lưu checkpoint và giải phóng tài nguyên trong thời gian cho phép.

## 1. Bài toán: một tiến trình phải dừng nhưng người dùng vẫn đang sử dụng dịch vụ

Khi rolling deployment, autoscaling giảm replica, bảo trì máy chủ hoặc ứng dụng nhận tín hiệu kết thúc, một instance thường vẫn còn request HTTP, message, job hoặc giao dịch đang thực thi. Nếu tiến trình bị dừng ngay lập tức, các request đó có thể bị ngắt kết nối, transaction bị rollback, event đã nhận nhưng chưa xử lý xong, hoặc công việc đã thực hiện ở hệ thống bên ngoài nhưng chưa ghi lại kết quả.

Hãy xét tình huống dịch vụ Checkout đang xử lý đặt hàng:

~~~text
Client
  |
  | POST /orders
  v
Load Balancer / Gateway
  |
  v
Checkout Pod A
  |
  +--> Kiểm tra tồn kho
  +--> Gửi yêu cầu thanh toán
  +--> Ghi trạng thái đơn
  +--> Phát sự kiện OrderCreated
~~~

Đúng lúc Pod A đang chờ Payment, Kubernetes quyết định thay Pod A bằng phiên bản mới. Nếu process bị kết thúc cưỡng bức ngay, client có thể nhận lỗi dù Payment đã thực sự ghi nhận giao dịch. Client thử lại có nguy cơ tạo thêm yêu cầu thanh toán. Trong khi đó, một consumer khác có thể đã nhận event nhưng chưa commit checkpoint.

**Graceful shutdown** là quá trình đưa instance từ trạng thái phục vụ sang trạng thái dừng theo một thứ tự có chủ đích: **ngăn công việc mới, cho công việc đang chạy một cơ hội hoàn thành, chuyển giao/ghi nhận phần chưa xong, đóng tài nguyên và chỉ sau đó kết thúc**.

Khả năng này không bảo đảm mọi request sẽ hoàn tất trong mọi tình huống. Mất điện, OOM kill, node chết, kill -9 hoặc thời hạn termination hết vẫn có thể cắt ngang tiến trình. Vì vậy cần kết hợp graceful shutdown với idempotency, transaction, retry và cơ chế khôi phục sau crash.

## 2. Phân biệt các thuật ngữ dễ nhầm

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Graceful shutdown | Dừng có kiểm soát, ưu tiên hoàn tất công việc đang chạy | Server ngừng nhận request và chờ request hiện hữu |
| Graceful termination | Quá trình chấm dứt instance do orchestrator/quy trình vận hành | Kubernetes thay Pod trong rollout |
| Connection draining | Ngừng đưa kết nối/yêu cầu mới đến instance, cho kết nối cũ rút dần | LB không định tuyến request mới vào Pod sắp tắt |
| Quiescing | Đưa thành phần vào trạng thái không nhận thêm công việc mới | Worker dừng nhận job mới |
| In-flight work | Công việc đã được chấp nhận nhưng chưa đạt điểm hoàn tất bền vững | Request đang ghi DB hoặc message đang xử lý |
| Readiness | Instance có nên nhận traffic mới không? | Readiness=false khi drain |
| Liveness | Process có đang hoạt động đủ để không bị coi là treo không? | Trong drain bình thường liveness có thể vẫn true |
| Drain deadline | Giới hạn tối đa dành cho việc hoàn tất và dọn dẹp | Chờ 45 giây rồi chuyển chính sách |
| Forced termination | Kết thúc sau khi hết ngân sách hoặc có sự cố | SIGKILL sau khi quá grace period |
| Checkpoint / ack | Ghi nhận phần công việc đã được hoàn thành theo hợp đồng | Commit consumer offset sau DB commit |

**“Ngừng nhận công việc mới” không có nghĩa “ngừng ngay mọi công việc”.** Ngược lại, cho phép mọi công việc hiện hữu chạy mãi không giới hạn cũng không phải graceful shutdown an toàn: rollout có thể bị treo hàng giờ, người vận hành không thể duy trì replica count và orchestrator vẫn có thể buộc kết thúc.

Cần phân biệt **dừng nhận ở tầng routing** với **dừng chấp nhận ở chính process**. Load balancer có thể còn gửi request vào Pod vài giây sau khi trạng thái readiness đổi do propagation delay hoặc kết nối HTTP keep-alive đã tồn tại. Một server cần chính sách xử lý những request “đến muộn” này, ngoài việc dựa vào orchestrator.

## 3. Mục tiêu và giới hạn của graceful shutdown

Một cơ chế shutdown tốt nên hướng đến:

1. **Không nhận thêm công việc mới** khi đã quyết định drain, trừ những request nội bộ cần thiết cho việc kết thúc.
2. **Cho công việc đã nhận hoàn tất** trong thời hạn xác định và chỉ trả thành công khi kết quả đã đáp ứng hợp đồng.
3. **Không làm mất dữ liệu** nếu công việc chưa kịp hoàn thành: message được giao lại, job được lease lại hoặc transaction được rollback an toàn.
4. **Không tạo side effect trùng** khi client, gateway hay consumer thử lại.
5. **Giải phóng tài nguyên đúng thứ tự**, không đóng database/broker trước khi worker cần chúng hoàn thành.
6. **Giữ khả năng quan sát**: biết còn bao nhiêu request, message, job và bước cleanup nào đang chờ.
7. **Kết thúc trong termination budget** để rollout/scale-down vận hành được.

Không thể hứa “zero dropped requests” chỉ bằng một shutdown hook. Người dùng có thể đóng trình duyệt, mạng có thể đứt hoặc process có thể chết đột ngột. Mục tiêu chính xác hơn là **giảm gián đoạn có thể phòng tránh và bảo đảm hệ thống phục hồi đúng khi gián đoạn vẫn xảy ra**.

### 3.1. Hai lớp bảo vệ bổ sung nhau

**Lớp 1 — Graceful path:** chuyển traffic đi nơi khác, từ chối việc mới, xử lý hết phần còn lại, đóng tài nguyên.

**Lớp 2 — Crash recovery:** transaction, idempotency key, durable queue, lease, checkpoint, outbox, retry có giới hạn và reconciliation để xử lý tình huống tắt không kiểm soát được.

Chỉ có lớp 1 thì một lần mất điện vẫn có thể làm lặp thanh toán. Chỉ có lớp 2 thì một rollout bình thường vẫn gây nhiều request lỗi không cần thiết.

## 4. Vòng đời trạng thái của một instance

Một state machine minh họa:

~~~text
STARTING
  |
  | Nạp config, kết nối dependency, warm up
  v
READY / SERVING
  |
  | Nhận tín hiệu termination hoặc drain command
  v
DRAINING
  |
  +-- Khai báo không sẵn sàng nhận traffic mới
  +-- Đóng cổng nhận công việc mới ở process
  +-- Dừng poll/claim message và job mới
  +-- Chờ in-flight + timeout có giới hạn
  +-- Ghi checkpoint/ack/lease release sau commit
  |
  +----> Hết ngân sách: thực hiện chính sách an toàn
  |
  v
STOPPING
  |
  +-- Đóng consumer, connection, pool, telemetry
  +-- Hoàn tất cleanup trong thời hạn còn lại
  v
TERMINATED
~~~

**READY / SERVING:** health/readiness cho phép nhận traffic; worker có quyền nhận công việc mới.

**DRAINING:** instance vẫn còn sống để hoàn tất request trước đó, nhưng từ chối nhận workload mới. Hệ thống cần nhận biết trạng thái này qua metric/log và thông báo phù hợp cho client nếu request mới tới.

**STOPPING:** ứng dụng giải phóng tài nguyên sau khi những thành phần sử dụng chúng đã dừng hoặc đạt deadline.

**TERMINATED:** process kết thúc. Không nên tồn tại background thread không được quản lý khiến JVM tiếp tục chạy ngoài kế hoạch.

### 4.1. Hai điều kiện cần trước khi kết thúc

Không chỉ kiểm đếm số request HTTP:

~~~text
safeToStop =
    HTTP in-flight = 0
AND message handlers in-flight = 0
AND leased jobs được hoàn tất hoặc chuyển giao an toàn
AND transaction / checkpoint đã ở trạng thái hợp lệ
AND cleanup thiết yếu đã xong
~~~

Điều kiện thực tế tùy loại ứng dụng. Một API thuần HTTP có thể không có consumer; một worker thuần Kafka có thể không cần HTTP connection draining. Tách tiêu chí theo workload để tránh yêu cầu vô nghĩa.

### 4.2. Phải xác định “công việc hoàn tất” là gì

Ví dụ về các điểm hoàn tất:

- HTTP đọc: response đã được xử lý và kết thúc theo semantics của web server; socket close phải được hiểu trong bối cảnh lỗi mạng.
- HTTP ghi đơn: transaction ghi đơn đã commit, và kết quả response được xây dựng đúng.
- Event consumer: side effect bền vững hoặc dedup marker đã commit, rồi mới ack/checkpoint theo hợp đồng.
- Outbox publisher: broker đã chấp nhận event theo mức đảm bảo cần thiết; trạng thái outbox được cập nhật an toàn.
- Batch job: checkpoint đủ để resume hoặc job đã hoàn thành và lưu kết quả.
- Saga: transition nghiệp vụ đã được commit; các bước đang chờ xử lý tiếp có record bền vững.

Trả HTTP 200 trước khi transaction commit hoặc ack message trước khi lưu kết quả làm sai ranh giới hoàn tất và khiến shutdown khó khôi phục.

## 5. Trình tự nhận và chuyển tín hiệu dừng

Ở Linux/container, tiến trình thường nhận SIGTERM để kết thúc có kiểm soát. Nếu không dừng trong thời gian grace, môi trường chạy có thể gửi SIGKILL hoặc hủy process theo cơ chế riêng.

Một trình tự thiết kế:

1. Orchestrator hoặc bộ điều khiển quyết định retire instance.
2. Cập nhật trạng thái định tuyến: instance không nên là đích cho yêu cầu mới.
3. Ứng dụng chuyển sang DRAINING, cổng nhận việc mới đóng.
4. Các request/job/message đã nhận hoàn tất hoặc được đưa về trạng thái có thể phục hồi.
5. Đóng consumer, scheduler, producer, DB/client pool và tài nguyên khác theo quan hệ phụ thuộc.
6. Flush telemetry có giới hạn, ghi sự kiện kết thúc và thoát process.
7. Nếu hết ngân sách, môi trường thực thi kết thúc cưỡng bức; hệ thống khôi phục phần chưa hoàn tất bằng cơ chế bền vững.

**Không giả định toàn bộ quá trình đều đồng bộ.** EndpointSlice, service mesh, ingress controller, external load balancer và client giữ kết nối cũ có thể nhìn thấy thay đổi ở thời điểm khác nhau. Vì vậy giai đoạn drain cần tính đến độ trễ lan truyền của routing.

### 5.1. Phân biệt SIGTERM, SIGINT và SIGKILL

- SIGTERM: tín hiệu yêu cầu process dừng; ứng dụng có thể bắt để khởi động shutdown.
- SIGINT: thường xuất hiện khi người dùng nhấn Ctrl+C; có thể được runtime/ứng dụng xử lý tương tự.
- SIGKILL: process không có cơ hội chạy shutdown hook hay đóng transaction bằng mã ứng dụng.

Trên JVM, shutdown hook chạy trong những trường hợp dừng bình thường được runtime hỗ trợ, nhưng không chạy khi process bị kill cưỡng bức hay host mất điện. Không dùng hook như cơ chế đảm bảo chính xác một lần cho side effect nghiệp vụ.

### 5.2. Điểm điều khiển shutdown nên idempotent

Tín hiệu có thể được nhận nhiều lần qua các đường khác nhau: SIGTERM, admin endpoint, actuator lifecycle hoặc orchestrator. Việc beginDrain nên **chuyển trạng thái một chiều** và có thể gọi lặp mà không tạo thêm hai lần đóng pool hoặc hai bộ cleanup cạnh tranh.

Ví dụ:

~~~text
if transition READY -> DRAINING succeeds:
    start drain procedure
else:
    return current drain status
~~~

Không mở lại READY trên cùng process chỉ vì một request admin thay đổi ý định sau khi đã giải phóng một phần tài nguyên. Nếu cần hủy rollout, nên điều phối instance ở cấp deployment thay vì cố phục sinh process đang dừng.

## 6. Connection draining ở gateway, ingress và load balancer

### 6.1. Luồng kỳ vọng

~~~text
                      Before drain             During drain

Client  ------> LB ---> Pod A (ready)      LB -X-> Pod A (not ready)
                  \--> Pod B (ready)        \-----> Pod B (ready)

                                  Pod A
                            +----------------+
                            | in-flight = 12 |
                            | accepting = no |
                            | finish requests|
                            +----------------+
~~~

Load balancer cần ngừng chọn Pod A cho **request mới**. Tuy nhiên, có các loại kết nối đã thiết lập:

- HTTP/1.1 keep-alive: một TCP connection có thể mang nhiều request theo thời gian.
- HTTP/2 và gRPC: một connection có thể có nhiều stream song song.
- WebSocket: kết nối có thể tồn tại hàng giờ.
- Server-Sent Events (SSE): response streaming kéo dài.
- Long polling: request có thể chờ lâu theo thiết kế.

Chỉ gỡ endpoint khỏi bảng routing không nhất thiết kết thúc tức thời kết nối đang mở. Phải kiểm tra behavior của web server, ingress/LB, service mesh và protocol cụ thể.

### 6.2. Request mới đến khi đã draining

Có hai nhóm request:

**Đã được chấp nhận trước drain:** ưu tiên hoàn tất trong deadline; không tự cắt ở giữa transaction chỉ vì readiness đổi.

**Bắt đầu sau drain:** nên được LB định tuyến sang instance khác. Nếu vẫn đến Pod đang drain, server có thể từ chối nhanh bằng phản hồi phù hợp, ví dụ 503 Service Unavailable và Retry-After khi chính sách cho phép, hoặc xử lý theo hành vi graceful của container. Không khuyến khích client tự retry POST không idempotent mà không có idempotency key.

Nếu tất cả replica đều draining cùng lúc và không còn nơi nhận, request mới không thể “chuyển sang instance khỏe”. Vì vậy deployment strategy và khả năng phục vụ tối thiểu quan trọng ngang shutdown hook.

### 6.3. HTTP/2, gRPC và WebSocket

**HTTP/2/gRPC:** cơ chế draining có thể dùng tín hiệu GOAWAY để báo client mở connection mới thay vì tạo stream mới trên connection cũ, đồng thời cho stream đang chạy hoàn tất trong giới hạn. Cách triển khai tùy server/framework; cần test với client thật.

**WebSocket:** có thể gửi thông điệp ứng dụng “server sắp bảo trì” và close frame phù hợp để client kết nối lại; không thể chờ vô hạn cho mọi socket. Client phải có reconnect backoff/jitter và khả năng khôi phục subscription.

**SSE/long polling:** ngắt kết nối có kiểm soát và hướng client kết nối lại theo giao thức. Cần hỗ trợ resume cursor/Last-Event-ID hoặc checkpoint khi yêu cầu không được mất event.

**Streaming upload/download:** nếu chuyển file lớn, cân nhắc giới hạn duration, resumable transfer và policy khi deadline đến. Không đặt termination grace period quá lớn chỉ để cứu một loại stream rất dài mà không có khả năng resume.

### 6.4. Sidecar và dependency trong cùng Pod

Trong service mesh, ứng dụng có thể cần proxy sidecar để tiếp tục gọi network trong lúc drain. Nếu proxy đóng trước khi app kết thúc request, graceful shutdown của app vẫn thất bại. Khi dùng sidecar, kiểm chứng thứ tự lifecycle và thời gian drain của proxy theo phiên bản hạ tầng; không mặc định chúng luôn phối hợp đúng.

## 7. Kubernetes: Pod termination, readiness và grace period

Kubernetes thường xử lý Pod deletion qua một khoảng grace period. Mặc định thường là 30 giây nếu không cấu hình khác. Trong chu kỳ termination, endpoint của Pod đang terminating được cập nhật để không nhận traffic thông thường từ Service; quá trình cập nhật và định tuyến có độ trễ lan truyền.

Đối với container có preStop hook được cấu hình, hook được chạy trước tín hiệu TERM và **thời gian thực thi hook nằm trong termination grace period**. Sau khi preStop kết thúc, runtime gửi tín hiệu kết thúc theo vòng đời container. Nếu process chưa thoát sau grace period, môi trường thực thi có thể buộc chấm dứt.

Một mô hình thời gian minh họa với terminationGracePeriodSeconds = 90:

~~~text
0s       Pod bắt đầu termination
         Endpoint routing bắt đầu thay đổi
         preStop hook (nếu có) thực thi
         |
~5s      Ứng dụng nhận SIGTERM (nếu preStop mất 5s)
         |
         | Stop accepting / drain in-flight
         |
~65s     Giới hạn phase shutdown của ứng dụng
         |
         | Cleanup / close resources / flush telemetry
         |
90s      Hết Kubernetes termination grace period
         Có thể bị force kill nếu chưa thoát
~~~

Các mốc chỉ là ví dụ tính ngân sách; thực tế phụ thuộc hook, process, runtime và orchestrator. Không thiết kế chính xác 90 giây cho 90 giây xử lý business: cần chừa biên cho propagation, shutdown của nhiều component và jitter.

### 7.1. Readiness khác liveness

- **Readiness=false:** bảo load balancer hoặc Kubernetes Service rằng Pod không nên được chọn cho traffic mới.
- **Liveness=false:** signal để hệ thống có thể restart container nếu kiểm tra thất bại; không nên tùy tiện biến trạng thái drain bình thường thành lỗi liveness.
- **Startup probe:** dành cho service khởi tạo chậm; không thay thế logic drain.

Ứng dụng nên phản ánh DRAINING trong readiness hoặc cơ chế routing tương đương. Nhưng đừng xem readiness là cổng chặn duy nhất; stale routing, connection reuse hoặc proxy có thể tiếp tục đưa request vào process trong một khoảng ngắn.

### 7.2. Ví dụ manifest Kubernetes

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: checkout
          image: example/checkout:1.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 1
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
~~~

Đây là một manifest minh họa, cần bổ sung resource requests/limits, bảo mật container, config, secret, metrics và điều kiện deployment thực tế. maxUnavailable: 0 chỉ giúp giữ replica sẵn sàng theo chiến lược rollout trong giới hạn có thể; không bảo đảm zero downtime nếu toàn bộ dependency hoặc node hỏng.

Ví dụ dùng endpoint Actuator giả định đã được bật, cấu hình health probes và được bảo vệ/giới hạn đúng. Không tự sao chép path nếu ứng dụng có context-path hoặc management port khác.

### 7.3. Có nên dùng preStop sleep?

Một số deployment dùng preStop để trì hoãn tín hiệu TERM, cho thay đổi endpoint kịp lan tới load balancer. Điều này có thể giảm khả năng request mới rơi vào instance sắp tắt khi hạ tầng định tuyến có độ trễ đáng kể.

Nhưng sleep có những giới hạn:

- Nó tiêu tốn một phần grace period.
- Thời lượng cố định không đo được thực tế LB propagation.
- Chỉ sleep không đảm bảo dừng nhận message/job hay xử lý in-flight đúng.
- Nếu preStop lỗi hoặc kéo dài, tiến trình có thể bị kill trước khi hoàn tất shutdown.

Nên dùng khi đã đo được nhu cầu trong hạ tầng cụ thể và đưa thời gian này vào termination budget. Bản thân web server vẫn cần shutdown lifecycle phù hợp. Đừng dùng một “sleep 30s” như thay thế duy nhất cho cơ chế graceful.

### 7.4. Nâng cấp/rolling deployment phải đủ năng lực

Nếu Pod A đang drain và Pod mới chưa ready, lượng traffic có thể bị dồn lên Pod B. Khi B không đủ capacity, việc drain đúng vẫn gây timeout dây chuyền.

Cần cân nhắc readiness thực, maxSurge, maxUnavailable, PodDisruptionBudget trong phạm vi áp dụng, tốc độ rollout, autoscaling behavior, số connection tới DB và headroom. Một số disruption tự nguyện có thể được PDB kiểm soát, nhưng không thể dựa vào PDB để ngăn mọi loại mất Pod.

## 8. Spring Boot: graceful shutdown của HTTP server

Spring Boot có hỗ trợ graceful shutdown với embedded web servers theo khả năng của từng runtime. Cấu hình thường dùng:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 60s
~~~

Ý nghĩa:

- **server.shutdown=graceful:** yêu cầu web server hỗ trợ ngừng chấp nhận request mới và cho request đang chạy hoàn tất khi application context shutdown.
- **spring.lifecycle.timeout-per-shutdown-phase:** ngân sách cho mỗi phase của Spring lifecycle; cần tính vào Kubernetes termination grace period và các phase liên quan.

Cấu hình này xử lý một phần HTTP lifecycle, **không tự động bảo đảm mọi Kafka consumer, scheduler, custom executor, WebSocket session, workflow hoặc transaction ngoài process đều hoàn tất**. Các thành phần đó cần cơ chế stop/drain tương ứng.

Hành vi chính xác khi request mới đến trong shutdown phụ thuộc server: Tomcat, Jetty, Reactor Netty, Undertow và cách nối tới proxy/ingress có thể khác nhau. Cần kiểm tra tài liệu theo phiên bản framework đang chạy và thử trên chính runtime của ứng dụng.

### 8.1. Đóng nguồn nhận việc trước khi đóng dependency

Một thứ tự hợp lý cho ứng dụng có HTTP và worker:

~~~text
Begin drain
   |
   +-- Stop accepting new HTTP business work
   +-- Stop scheduler creating new tasks
   +-- Stop consumer claiming/polling new messages
   |
   +-- Wait for accepted business operations
   +-- Commit transactions and checkpoints
   +-- Finish pending publisher flush if required
   |
   +-- Close consumers and worker executors
   +-- Close HTTP/DB/broker clients and pools
   +-- Flush limited telemetry
   |
   +-- Exit
~~~

Đóng database connection pool quá sớm có thể làm các request đang hoàn thành ghi dữ liệu bị lỗi. Ngược lại, không dừng scheduler trước sẽ có job mới liên tục sinh ra và drain không bao giờ về 0. Thứ tự cần dựa vào dependency graph của service.

### 8.2. Shutdown lifecycle trong Spring

Spring cung cấp lifecycle cho các bean, bao gồm SmartLifecycle, phương thức destroy và các callback dừng khi context đóng. Đối với component chủ động nhận việc, nên có cơ chế stop nhận việc và chờ in-flight, đồng thời tôn trọng timeout để quá trình đóng không chờ vô hạn.

Nếu dùng SmartLifecycle, cần hiểu phase ordering và callback stop(Runnable): khi dùng callback bất đồng bộ, phải báo hoàn tất đúng lúc component đã dừng, nếu không framework có thể hết phase timeout hoặc đóng các bean phụ thuộc khi component vẫn chạy. Không tự tạo nhiều shutdown hook cạnh tranh với lifecycle của Spring.

### 8.3. Readiness theo trạng thái ứng dụng

Spring Boot Actuator có các trạng thái availability/readiness; khi shutdown, ứng dụng cần ngừng quảng bá mình là nơi nhận traffic. Nếu tự bổ sung readiness indicator, nó nên bám một trạng thái drain nhất quán, không lẫn với liveness.

**Không để business endpoint và readiness endpoint gọi cùng một cơ chế khóa chờ dài** khiến probe bị treo khi drain. Readiness cần trả nhanh; quá trình drain thực có thể kéo dài nhiều giây hoặc phút.

### 8.4. WebFlux và lời gọi bất đồng bộ

Với ứng dụng reactive, một request có thể trả về Publisher và hoàn tất sau khi method controller đã return. Đếm in-flight bằng cách tăng trước khi return Publisher rồi giảm trong finally của method có thể sai.

Cần gắn metric/gate tại lifecycle hoàn tất của stream, ví dụ termination/cancellation signal, và phân biệt response đã kết thúc với xử lý nội bộ đã commit. Tương tự, với Servlet async, việc thoát khỏi filter không nhất thiết đồng nghĩa async request đã hoàn tất; phải dùng callback/sự kiện hoàn tất phù hợp.

## 9. Thiết kế một cổng nhận việc và bộ đếm in-flight

Khi framework hỗ trợ graceful HTTP, không cần tự viết một HTTP server mới. Tuy nhiên, ở ranh giới **business work** có thể cần một cơ chế để không tạo thêm job nội bộ khi instance đã draining và để biết còn bao nhiêu thao tác cần hoàn tất.

### 9.1. Nguyên tắc vào/ra

1. Chỉ cho request/job bắt đầu khi trạng thái là ACCEPTING.
2. Tăng bộ đếm in-flight trước khi thực thi công việc.
3. Kiểm tra lại trạng thái để xử lý race giữa accept và beginDrain.
4. Giảm bộ đếm ở đúng thời điểm công việc thực sự hoàn tất (thành công, lỗi hoặc hủy an toàn).
5. Khi drain, đóng cổng rồi đợi bộ đếm về 0 tới deadline.

### 9.2. Ví dụ Java với AtomicBoolean và AtomicInteger

~~~java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class WorkDrainGate {
    private final AtomicBoolean accepting = new AtomicBoolean(true);
    private final AtomicInteger inFlight = new AtomicInteger();

    public WorkPermit enter() {
        if (!accepting.get()) {
            throw new RejectedExecutionException("Service is draining");
        }

        inFlight.incrementAndGet();

        // Chặn race: drain có thể bắt đầu sau lần kiểm tra đầu.
        if (!accepting.get()) {
            inFlight.decrementAndGet();
            throw new RejectedExecutionException("Service is draining");
        }

        return new WorkPermit(this);
    }

    public void beginDrain() {
        accepting.set(false);
    }

    public boolean isAccepting() {
        return accepting.get();
    }

    public int inFlight() {
        return inFlight.get();
    }

    private void leave() {
        inFlight.decrementAndGet();
    }

    public static final class WorkPermit implements AutoCloseable {
        private final WorkDrainGate owner;
        private boolean closed;

        private WorkPermit(WorkDrainGate owner) {
            this.owner = owner;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                owner.leave();
            }
        }
    }
}
~~~

Cách dùng trong một đoạn xử lý đồng bộ:

~~~java
try (WorkDrainGate.WorkPermit ignored = gate.enter()) {
    // Kiểm tra input, xử lý nghiệp vụ, commit transaction.
    // Permit đóng sau khi công việc thuộc scope này hoàn tất.
    orderService.createOrder(command);
}
~~~

**Giới hạn quan trọng của ví dụ:** WorkPermit không tự đồng bộ nếu cùng object bị close đồng thời từ nhiều thread; ứng dụng phải bảo đảm mỗi permit có đúng một owner và chỉ close một lần. Đối với tác vụ async, không dùng try-with-resources bao ngoài lệnh submit rồi giải phóng permit ngay sau khi submit. Cần đóng permit trong callback completion/cancellation của tác vụ. Khi yêu cầu tính chính xác concurrency cao, cân nhắc triển khai permit với AtomicBoolean chống double close.

Không dùng cổng này như cơ chế authorization hoặc retry của giao thức; nó chỉ đại diện **trạng thái cho phép bắt đầu công việc trên instance**.

### 9.3. Chờ drain có giới hạn

Pseudocode:

~~~text
beginDrain()
stopAcceptingNewWork()
deadline = monotonicNow + drainBudget

while inFlight > 0 AND monotonicNow < deadline:
    wait for completion signal with bounded timeout

if inFlight == 0:
    close resources normally
else:
    record remaining work and apply safe timeout policy
    rely on durable recovery for unfinished operations
~~~

Không cần busy-spin liên tục để chờ inFlight=0; dùng condition/latch/notification hoặc primitive chờ có timeout. Khi deadline đến, không tự gọi System.exit(0) trước khi ghi các checkpoint cần thiết hoặc trước khi framework có cơ hội đóng tài nguyên; phối hợp shutdown phases.

## 10. Consumer Kafka, RabbitMQ và message queue phải dừng thế nào?

Dừng nhận HTTP chỉ bảo vệ request từ client. Một Pod cũng có thể chạy Kafka/RabbitMQ consumer hoặc worker. Những component này có thể tiếp tục nhận việc mới dù readiness của HTTP đã false, bởi consumer group và broker có vòng đời riêng.

### 10.1. Trình tự consumer chung

~~~text
DRAINING
   |
   +-- Ngừng claim/delivery mới theo cơ chế broker
   |
   +-- Chờ handlers đang chạy hoàn tất
   |
   +-- Commit side effect / dedup marker
   |
   +-- Ack/commit checkpoint phù hợp
   |
   +-- Close consumer / release group membership
   v
STOPPED
~~~

Điểm quan trọng là **checkpoint chỉ tiến khi công việc đạt durability contract**. Với at-least-once delivery, một message có thể được giao lại sau crash hoặc rebalance; consumer phải idempotent.

### 10.2. Kafka consumer

Trong Kafka, một consumer có thể nhận nhiều record từ poll() và xử lý qua worker pool. Để drain:

- Dừng đưa record mới vào worker pool sau khi bắt đầu drain.
- Theo dõi record đã giao cho worker và trạng thái xử lý theo partition.
- Không commit offset vượt qua record chưa được xử lý thành công theo thứ tự cần thiết của partition.
- Hoàn tất side effect/transaction, rồi commit checkpoint phù hợp.
- Khi cần pause partition, vẫn phải hiểu yêu cầu tiếp tục poll để duy trì group membership; chỉ gọi pause rồi ngừng poll vô hạn có thể dẫn đến rebalance.
- Đóng consumer theo API/timeout thích hợp để group phân lại partition cho instance khác.

Với Spring Kafka, cần dựa vào lifecycle của Kafka listener container, acknowledgment mode và tính năng stop/pause đúng phiên bản. Không gọi close từ thread khác tùy tiện hoặc giả định stop listener đồng nghĩa đã flush mọi tác vụ được dispatch sang executor riêng.

**Ví dụ tình huống:** poll nhận offset 100, 101, 102. Worker xử lý xong 101 và 102 nhưng 100 đang chờ DB. Nếu commit “đã xong 102” theo một mốc contiguous không đúng, crash có thể làm mất cơ hội xử lý offset 100. Cần bảo đảm checkpoint xử lý partition theo thứ tự hoặc dùng kiến trúc hỗ trợ theo dõi completion gap an toàn.

### 10.3. RabbitMQ và queue có acknowledgment

Với broker hỗ trợ manual ack, hướng xử lý thường là hủy subscription/consumer để không nhận delivery mới, đợi những delivery đang xử lý và ack sau khi side effect commit. Nếu channel/connection bị đóng trước ack, broker có thể requeue message theo semantics tương ứng. Người xử lý phải chịu được redelivery và deduplicate.

Prefetch/concurrency quyết định số message có thể đang in-flight lúc drain. Prefetch rất lớn có thể làm một instance giữ quá nhiều message, kéo dài shutdown và chậm bàn giao cho consumer khác.

### 10.4. Retry queue và dead-letter queue

Các message lỗi tạm thời có thể cần retry có backoff. Khi instance dừng giữa retry, không nên giữ trạng thái retry duy nhất trong RAM. Lưu retry schedule hoặc message trong broker/store bền vững.

Đẩy message vào DLQ không đồng nghĩa đã hoàn tất nghiệp vụ. Cần có runbook kiểm tra, replay có kiểm soát và bảo vệ không nhân đôi side effect.

### 10.5. Transactional outbox

Nếu một API đã commit dữ liệu nguồn và outbox trong cùng transaction, event có thể được publish sau bởi relay khác, ngay cả khi instance tạo đơn dừng. Relay cũng cần shutdown an toàn: không đánh dấu outbox “đã publish” nếu broker chưa xác nhận theo hợp đồng; nếu publish thành công nhưng chưa kịp đánh dấu rồi process chết, message có thể được gửi lại. Consumer phải idempotent.

Cơ chế này bảo vệ trước shutdown đột ngột tốt hơn gửi event chỉ trong bộ nhớ sau khi commit database.

## 11. Job nền, scheduler và tác vụ dài

Các công việc khác HTTP/message cũng cần drain, ví dụ batch import, tạo báo cáo, đồng bộ file, gửi email, làm sạch dữ liệu và cron job.

### 11.1. Không tạo job mới khi instance đã dừng nhận việc

Trước khi chờ in-flight, phải ngừng scheduler tạo job mới hoặc worker claim lease mới. Nếu scheduler cứ tạo thêm task thì bộ đếm in-flight không giảm về 0.

Ở hệ thống nhiều replica, scheduler phải có phối hợp tránh duplicate, ví dụ distributed lease/leader election hoặc scheduler trung tâm. Khi một replica dừng, instance khác chỉ nhận lại job sau khi quyền sở hữu cũ được kết thúc hoặc lease hết hạn.

### 11.2. Job ngắn và job dài

**Job ngắn:** có thể đợi hoàn tất trong ngân sách drain.

**Job dài:** phải thiết kế checkpoint, cancel an toàn hoặc bàn giao qua durable queue/lease. Không thể kỳ vọng một job chạy 45 phút hoàn tất trong grace period 60 giây.

Ví dụ import 1 triệu dòng:

~~~text
Job started
  |
  +-- Process batch 1 -> checkpoint row=10.000
  +-- Process batch 2 -> checkpoint row=20.000
  +-- ...
  +-- Drain signal
        |
        +-- Finish current bounded batch
        +-- Commit checkpoint
        +-- Release lease safely
        +-- Exit
  |
Next worker resumes from durable checkpoint
~~~

Checkpoint phải gắn với dữ liệu thực sự đã commit. Nếu checkpoint báo đã xử lý tới dòng 20.000 nhưng DB mới commit tới 19.500, phần còn lại có thể bị bỏ qua. Nếu DB commit xa hơn checkpoint, replay cần idempotent.

### 11.3. Lease và visibility timeout

Trong worker có lease, sau khi nhận việc, worker sở hữu job trong một khoảng thời gian. Nó cần gia hạn lease khi tiếp tục xử lý; khi drain, ngừng claim mới và hoàn tất/nhả lease theo chính sách.

Nếu process chết, lease hết hạn giúp worker khác nhận lại công việc. Tuy nhiên, nếu worker cũ vẫn thực thi trong một khoảng split-brain, hai worker có thể cùng làm; cần **fencing token/lease generation** hoặc version check ở nơi ghi dữ liệu khi nghiệp vụ yêu cầu.

Visibility timeout quá ngắn có thể làm message bị giao lại khi worker còn đang chạy. Timeout quá dài có thể làm phục hồi chậm sau crash. Cân bằng bằng gia hạn hợp lệ, checkpoint và idempotency.

### 11.4. Saga kéo dài vượt đời Pod

Saga không nên buộc sống trong RAM của một Pod từ đầu đến cuối. Lưu state machine, step, deadline, retry count, correlation và compensation state bền vững. Khi coordinator Pod dừng, instance khác tiếp tục dựa trên dữ liệu đã commit, không dựa vào thread cũ còn sống.

Nếu payment command đã gửi nhưng chưa biết kết quả, đừng phát lại ngay khi instance mới khởi động. Cần reconciliation/idempotency và đánh giá trạng thái thực để tránh side effect trùng.

## 12. Shutdown và transaction: điểm có thể mất hoặc nhân đôi dữ liệu

Bốn kịch bản thường gặp:

| Tình huống | Rủi ro | Cơ chế phòng vệ |
|---|---|---|
| App dừng trước DB commit | Request lỗi/rollback, client có thể retry | Transaction rõ, idempotency key |
| DB commit nhưng response chưa đến client | Client không biết kết quả, retry trùng | Idempotency/reconcile theo mã giao dịch |
| Consumer commit DB nhưng chưa ack broker | Message được giao lại | Idempotent consumer/dedup |
| Consumer ack trước khi DB commit | Message có thể mất nếu crash | Ack sau durability boundary |
| Gửi event rồi crash trước cập nhật outbox | Event có thể publish lại | Event ID và dedup |
| Shutdown giữa compensation | Trạng thái nghiệp vụ kẹt | Persisted saga state và retry/reconcile |

### 12.1. Idempotency key cho HTTP command

Client gửi một khóa idempotency ổn định cho cùng thao tác, ví dụ “tạo đơn lần này”. Server lưu khóa, fingerprint của request và kết quả hoặc trạng thái xử lý theo policy. Nếu client retry sau timeout, backend nhận biết thao tác cũ thay vì tạo giao dịch mới.

Không chỉ giữ khóa trong bộ nhớ Pod, vì Pod chết sẽ mất lịch sử. Với side effect quan trọng, cần store bền vững và transaction/locking phù hợp.

### 12.2. Chuyển trạng thái nghiệp vụ bền vững

Thay vì chỉ “worker đang chạy”, dữ liệu nên biểu diễn:

~~~text
RECEIVED -> PROCESSING -> COMMITTED
                    |
                    +--> RETRY_SCHEDULED
                    +--> FAILED_FINAL
                    +--> MANUAL_RECONCILIATION
~~~

Sau crash hoặc shutdown hết deadline, instance mới đọc trạng thái bền vững và quyết định bước an toàn. Không biến PROCESSING thành COMMITTED chỉ vì application đã bắt đầu trả HTTP 200.

### 12.3. Không nên tự hủy transaction giữa chừng vô điều kiện

Đến drain deadline, hủy ngay một RPC hoặc DB transaction có thể tạo trạng thái “không biết đã commit chưa”. Một số client/hệ thống không hỗ trợ cancellation bảo đảm rollback. Phải định nghĩa lựa chọn cho từng loại thao tác:

- Đợi thêm trong giới hạn nếu rất gần commit và ngân sách còn.
- Ghi trạng thái cần reconciliation trước khi dừng.
- Cho transaction DB rollback nếu chưa commit.
- Giữ idempotency key để client retry nhận kết quả cũ.
- Với side effect bên ngoài đã gửi, xác minh lại trạng thái trước retry/compensation.

## 13. Tính toán shutdown budget từ SLO và công việc thực

Đặt terminationGracePeriodSeconds=120 không tự chứng minh mọi request sẽ hoàn tất. Cần phân rã thời gian và có dự phòng.

Ví dụ minh họa cho Pod chỉ có HTTP ngắn và consumer có batch nhỏ:

| Thành phần | Ngân sách |
|---|---:|
| Endpoint/routing propagation hoặc preStop nếu cần | 5 giây |
| Dừng nhận việc và hoàn tất request/message đã nhận | 50 giây |
| Commit checkpoint, đóng consumer/pool | 15 giây |
| Flush telemetry/cleanup khác | 10 giây |
| Dự phòng scheduler, IO, jitter | 10 giây |
| **Tổng** | **90 giây** |

Khi có các phase chạy song song, không nhất thiết cộng tất cả theo một đường thẳng; nhưng phải đảm bảo đường găng không vượt termination grace period thực. Một preStop hook 30 giây trong Pod có grace period 30 giây có thể dùng hết toàn bộ ngân sách trước khi app được cơ hội drain.

### 13.1. Thời gian drain phụ thuộc số in-flight và capacity

Giả sử lúc bắt đầu drain có 120 request, xử lý song song tối đa 20 request, mỗi request còn khoảng 2 giây xử lý:

~~~text
Ideal waves = ceil(120 / 20) = 6
Estimated drain time ≈ 6 × 2 giây = 12 giây
~~~

Đây là ước tính đơn giản, giả định các request có thời lượng tương đương và dependency không nghẽn. Một request dài 40 giây, queue nội bộ, lock DB hoặc retry có thể làm tail latency lớn hơn nhiều. Dùng p99 (và phân bố thời gian còn lại) làm đầu vào, không chỉ average latency.

### 13.2. Lời gọi downstream phải có deadline

Khi Pod còn 20 giây để drain, một HTTP client có retry 5 lần và timeout mỗi lần 30 giây là không phù hợp. Cần giới hạn tổng deadline của nghiệp vụ và thời gian còn lại, đồng thời bảo đảm việc hủy/từ chối không làm sai trạng thái.

Với những công việc cần nhiều thời gian hơn budget, thiết kế async + durable checkpoint hoặc chuyển giao thay vì mở rộng termination grace period không giới hạn.

### 13.3. Kết thúc theo từng nhóm công việc

Một ứng dụng có thể có:

- Read-only HTTP request: chỉ cần response hoàn tất.
- Write transaction: yêu cầu commit hoặc rollback an toàn.
- Streaming connection: có protocol reconnect/resume.
- Message handler: yêu cầu checkpoint/ack phù hợp.
- Long job: yêu cầu checkpoint/lease release.
- Saga: yêu cầu durable state và handoff.

Một deadline duy nhất áp cho mọi nhóm có thể thiếu hoặc thừa. Vẫn cần **giới hạn tổng** của process, nhưng chính sách khi hết thời gian nên rõ theo từng loại công việc.

## 14. Phối hợp readiness, autoscaling và rolling deployment

### 14.1. Tránh rút quá nhiều replica cùng lúc

Khi rút một Pod, traffic sẽ chuyển qua replica còn lại. Nếu replica còn lại không có headroom hoặc bị DB saturation, shutdown đúng vẫn gây lỗi lan truyền.

Cần xem:

- RollingUpdate maxSurge/maxUnavailable và số replica tối thiểu.
- Readiness của Pod mới chỉ true khi đã warm up và dependency thiết yếu sẵn sàng.
- Connection pool/CPU của số replica còn lại.
- PodDisruptionBudget trong những disruption được cơ chế này hỗ trợ.
- HPA scale-down policies và độ trễ đo metric.
- Queue consumer group rebalance/partition ownership khi rút worker.

### 14.2. Pod mới phải thực sự sẵn sàng

Một Pod vừa mở port chưa chắc đã:

- Nạp xong cấu hình/secret và khoá xác minh.
- Warm cache hoặc compile những phần bắt buộc.
- Kết nối được DB/broker.
- Đăng ký listener đúng nhóm.
- Hoàn tất migration hoặc compatibility checks cần thiết.

Readiness quá sớm có thể nhận traffic khi Pod chưa phục vụ được. Readiness quá muộn có thể làm rollout kẹt dù Pod khỏe. Định nghĩa readiness theo điều kiện phục vụ thực, tránh kiểm tra dependency tùy chọn khiến mọi Pod đồng loạt unavailable khi một external service có sự cố.

### 14.3. Scale-to-zero và workload đặc biệt

Một worker tiêu thụ queue liên tục có thể không hỗ trợ scale-to-zero nếu không có controller tự đánh thức khi queue nhận message. Trước khi rút replica cuối, phải đảm bảo cơ chế nhận việc mới hoặc phục hồi đã tồn tại. Với dịch vụ giữ kết nối dài, cần điều phối client reconnect sang replica khác.

## 15. Quan sát quá trình drain

Nếu chỉ đo số Pod bị xóa, không thể biết shutdown có trơn tru hay không. Nên có metric và log có cấu trúc.

| Tín hiệu | Ý nghĩa |
|---|---|
| shutdown_started_total{reason} | Số lần bắt đầu shutdown theo lý do |
| service_lifecycle_state | READY, DRAINING, STOPPING theo enum hữu hạn |
| drain_inflight_requests | Request hiện đang xử lý |
| drain_inflight_messages | Message handlers đang xử lý |
| drain_inflight_jobs | Job có lease/chưa checkpoint |
| drain_duration_seconds | Thời gian drain của một instance |
| drain_timeout_total | Lần hết ngân sách khi còn công việc |
| shutdown_forced_termination_total | Trường hợp bị buộc kết thúc nếu có tín hiệu thu thập |
| queue_unacked_messages | Message đã nhận nhưng chưa ack |
| checkpoint_commit_failures_total | Lỗi ghi tiến độ khi drain |
| HTTP 5xx/503 during rollout | Tỷ lệ lỗi liên quan rút instance |
| request_retry_total | Retry có tăng đột biến khi deployment không? |
| active_connections/streams | Kết nối HTTP/2, gRPC, WebSocket còn sống |
| termination_reason / config_revision | Nối sự cố với rollout và lý do thay Pod |

Không gắn requestId, jobId, userId hoặc orderId vào nhãn metric vì cardinality lớn. ID riêng phục vụ điều tra ở log/trace có phân quyền.

### 15.1. Log chuyển trạng thái

Ví dụ:

~~~json
{
  "event": "service_shutdown_transition",
  "service": "checkout",
  "instance": "checkout-7f8d",
  "fromState": "SERVING",
  "toState": "DRAINING",
  "reason": "SIGTERM",
  "inFlightHttp": 17,
  "inFlightMessages": 3,
  "drainBudgetSeconds": 60
}
~~~

Khi kết thúc, ghi trạng thái còn lại (counts), thời gian drain và những việc cần chuyển giao. Không log password, token, payload thanh toán hoặc thông tin riêng tư.

### 15.2. Trace khi instance sắp tắt

Các request đang hoàn tất vẫn cần trace để phân biệt lỗi tại app, database, broker hay gateway. Nếu SDK telemetry đóng trước worker, những span cuối có thể mất. Flush exporter có **timeout hữu hạn** sau phần công việc chính; không giữ process vô hạn chỉ để gửi log.

Với shutdown cưỡng bức, exporter có thể không kịp gửi mọi tín hiệu. Vì vậy không coi metric/log là trạng thái duy nhất phục vụ khôi phục nghiệp vụ; checkpoint và durable state mới là bằng chứng chính.

### 15.3. Dấu hiệu shutdown chưa tốt

- Spike 502/503/499 hoặc connection reset trùng với rollout.
- Thời gian chờ request p99 tăng ngay sau rút Pod.
- Pod thường xuyên chạm termination grace period.
- Message được giao lại tăng đột biến, DLQ tăng.
- Có nhiều job bị chiếm lease đến khi timeout.
- Outbox publish backlog tăng khi scale-down.
- Saga ở trạng thái PROCESSING/PENDING lâu hơn sau deploy.
- Pod mới bắt đầu nhận traffic quá sớm.
- Traces kết thúc đột ngột, thiếu span commit/ack.
- Database connection cạn khi nhiều Pod cũ và mới cùng tồn tại.

Các tín hiệu trên là giả thuyết ban đầu; cần đối chiếu deployment event, connection routing, dependency state và trace để xác định nguyên nhân.

## 16. Kịch bản kiểm thử graceful shutdown

Không chỉ kiểm tra ứng dụng dừng khi không có request. Cần kiểm tra trong lúc có tải và công việc đang hoạt động.

### 16.1. Các trường hợp kiểm thử

| Kịch bản | Điều quan sát | Kết quả mong đợi |
|---|---|---|
| Xóa một Pod khi còn request đọc | Client latency, errors, in-flight | Request đã nhận hoàn tất nếu trong budget; request mới được định tuyến nơi khác |
| Dừng Pod khi đang ghi DB | Commit/rollback, client retry | Không mất trạng thái hoặc nhân đôi giao dịch |
| Dừng sau Payment thành công nhưng trước response | Idempotency/reconciliation | Retry trả kết quả cũ hoặc xác minh trạng thái |
| SIGTERM khi Kafka handler đang xử lý | Ack/offset, redelivery | Side effect commit đúng, replay idempotent |
| SIGTERM khi worker đã nhận batch 100 message | Remaining count, checkpoint | Không commit vượt record chưa xử lý |
| Dừng Pod có job dài | Lease/checkpoint | Instance khác resume an toàn |
| Dừng trong saga WAITING_FOR_PAYMENT | Durable state/version | Coordinator khác tiếp tục mà không phát lệnh trùng |
| Dừng khi có WebSocket/gRPC stream | Close/reconnect, resume | Client chuyển phiên hoặc nhận lỗi có thể phục hồi |
| PreStop kéo dài hơn dự kiến | Termination budget | Có cảnh báo budget bị tiêu thụ |
| Đường downstream chậm vào cuối drain | Deadline, fallback, pending side effect | Không chờ vô hạn hoặc tự tuyên bố thành công |
| SIGKILL/OOM thay vì SIGTERM | Recovery sau restart | Transaction/checkpoint/idempotency bảo vệ correctness |
| Rolling deployment liên tục | Error rate và capacity | Không rút hết các replica đủ điều kiện cùng lúc |

### 16.2. Thử bằng lưu lượng thật trong môi trường kiểm soát

Một quy trình kiểm chứng:

1. Tạo tải ổn định gồm request nhanh, request chậm và tác vụ có side effect được mô phỏng.
2. Quan sát baseline: error rate, throughput, p95/p99, in-flight và trạng thái queue.
3. Kích hoạt rolling update hoặc xóa một Pod có kiểm soát.
4. Ghi lại thời điểm Pod terminating, endpoint thay đổi, SIGTERM, bắt đầu drain và process exit.
5. So sánh request chấp nhận trước drain với kết quả sau; kiểm tra lost/duplicate/retry.
6. Kiểm tra checkpoint, job lease, queue redelivery và saga state.
7. Kiểm tra hệ thống trở lại trạng thái ổn định sau Pod mới ready.
8. Thử lặp với dependency chậm, connection dài và SIGKILL để đánh giá crash recovery.

Đối với Payment, chuyển tiền hoặc dữ liệu thật, ưu tiên mock/sandbox, môi trường cách ly và idempotency test rõ ràng để tránh side effect ngoài ý muốn.

### 16.3. Câu hỏi nghiệm thu

- Từ lúc bắt đầu drain đến khi Pod không còn được nhận routing mới mất bao lâu?
- Có request mới nào vẫn vào instance sau readiness=false? Hệ thống xử lý chúng thế nào?
- Bao nhiêu request đã được chấp nhận hoàn tất, bao nhiêu timeout và vì sao?
- Consumer có commit offset theo đúng ranh giới DB durability không?
- Có job nào không được chuyển giao hoặc saga nào bị kẹt?
- Time budget có đủ cho p99 và cleanup, hay thường xuyên chạm force kill?
- Client có retry an toàn và tôn trọng backoff không?
- Hệ thống có đủ capacity khi một Pod rút khỏi pool?
- Các tín hiệu metric/log/trace có giúp tìm nguyên nhân không?

## 17. Những sai lầm thường gặp

**“Chỉ cần bắt SIGTERM và sleep 30 giây.”** Sleep không bảo đảm LB đã ngừng gửi traffic, worker đã dừng nhận việc, request đã commit hay queue đã ack. Cần state/lifecycle và theo dõi công việc.

**“Readiness=false là không còn request nào tới.”** Endpoint/routing propagation và connection reuse tạo khoảng trễ; HTTP server phải chịu được request đến muộn.

**“Đóng DataSource ngay khi nhận SIGTERM.”** Các request in-flight còn cần DB sẽ lỗi. Đóng nguồn nhận việc trước, chờ công việc hoàn tất, rồi đóng dependency theo thứ tự.

**“Graceful shutdown của HTTP server xử lý cả Kafka consumer.”** Listener/worker có lifecycle độc lập. Phải stop polling/claiming và ack/checkpoint sau commit.

**“Dừng consumer là commit offset hiện tại.”** Nếu đã poll nhưng chưa xử lý hết, commit vượt ranh giới durability có thể làm mất message.

**“Tăng grace period thật lớn là an toàn nhất.”** Rollout có thể chậm/treo, Pod cũ giữ tài nguyên, job vô hạn không bao giờ xong. Công việc dài cần checkpoint và resume.

**“Client có thể retry mọi request sau reset.”** POST có side effect có thể đã được thực hiện. Cần idempotency key, dedup và reconciliation.

**“Shutdown hook luôn chạy.”** SIGKILL, OOM, node crash hay mất điện có thể ngắt ngay. Thiết kế phục hồi từ dữ liệu bền vững.

**“In-flight bằng 0 khi controller method return.”** Với Servlet async, WebFlux, gRPC streaming và background futures, work có thể còn chạy sau khi method return. Đếm theo hoàn tất thực tế.

**“Pod mới ready thì capacity chắc chắn đủ.”** Readiness không đo toàn bộ headroom hoặc quota database. Rollout có thể tăng áp lực vào dependency chung.

**“Log sự kiện job finished đủ để khôi phục.”** Log không thay thế transaction/checkpoint. Ghi state bền vững và kiểm tra tính đúng đắn.

**“Tắt proxy/sidecar cùng lúc chắc chắn không sao.”** Proxy có thể đóng kết nối trước khi ứng dụng gửi xong response. Phải kiểm chứng thứ tự đóng trong môi trường thực.

## 18. Bài tập tình huống: rolling deployment của Checkout

Một hệ thống có 5 replica Checkout, nhận khoảng 800 request/giây. Mỗi request bình thường mất 250 ms, nhưng có một số request chờ Payment 8 giây. Checkout còn chạy Kafka listener xử lý OrderCreated; mỗi handler có thể tốn 3 giây và commit DB trước khi ack.

Kubernetes đặt terminationGracePeriodSeconds=30. Ứng dụng chỉ có một shutdown hook gọi System.exit(0) ngay sau khi nhận SIGTERM. Gateway có HTTP keep-alive; client tự retry POST /orders khi thấy connection reset.

Trong khi triển khai phiên bản mới, một số người dùng bị timeout và phát hiện đơn hàng trùng.

**Câu hỏi:**

1. Vì sao shutdown hook hiện tại không cho request in-flight hoàn tất?
2. Vì sao Pod đã bị gỡ khỏi danh sách endpoint vẫn có thể nhận request trong một khoảng ngắn?
3. Với request Payment mất 8 giây, cần điều chỉnh graceful HTTP và termination budget như thế nào?
4. Kafka listener nên ngừng nhận record mới, commit checkpoint và close theo thứ tự nào?
5. Vì sao một request bị reset chưa chắc chưa tạo đơn? Nên dùng idempotency key ở đâu?
6. Có cần tách listener khỏi Checkout API thành workload riêng không? Những tiêu chí nào giúp ra quyết định?
7. Khi chỉ còn 4 replica phục vụ, có đủ CPU/DB connections để hấp thụ 800 request/giây không?
8. Cần kiểm tra metric nào để kết luận rollout an toàn?

**Định hướng giải:**

- Cho Pod chuyển từ SERVING sang DRAINING, giảm/loại routing mới và giới hạn request mới tại process.
- Cấu hình graceful shutdown của web server, đảm bảo grace period còn đủ cho request p99, thời gian cleanup và propagation.
- Dừng Kafka listener/claiming trước; hoàn tất handlers, commit DB và ack/checkpoint đúng semantics; crash vẫn phải redeliver idempotent.
- Lưu idempotency key cho lệnh tạo đơn và đối chiếu với trạng thái Payment khi kết quả chưa xác định.
- Đảm bảo rollout có headroom; đo in-flight, thời gian drain, forced terminations, 5xx, consumer redelivery và duplicate orders.
- Nếu HTTP và worker có nhu cầu lifecycle/capacity khác nhau, cân nhắc tách deployment và resource policy, nhưng quyết định dựa trên yêu cầu vận hành thực.

## 19. Checklist thiết kế graceful shutdown

1. Xác định tất cả nguồn nhận việc: HTTP, gRPC, WebSocket, Kafka, RabbitMQ, scheduler, lease-based jobs.
2. Biết orchestrator phát tín hiệu gì, khi nào và timeout toàn process là bao nhiêu.
3. Thiết kế state machine STARTING → SERVING → DRAINING → STOPPING → TERMINATED.
4. Phản ánh DRAINING trong readiness/routing và có chiến lược xử lý request tới muộn.
5. Ngừng **tạo/claim/poll công việc mới** trước khi đợi in-flight.
6. Đếm công việc đang xử lý đến đúng completion boundary, kể cả async/streaming.
7. Đặt drain deadline bằng ngân sách có đo p99, preStop, shutdown phases và cleanup.
8. Phối hợp HTTP server, message consumer, job scheduler, executor và dependency pool.
9. Đảm bảo ack/offset/checkpoint chỉ tiến khi side effect đã bền vững.
10. Thiết kế idempotency, outbox, replay và job lease để xử lý crash hoặc force kill.
11. Bảo vệ saga state và biết cách tiếp tục/compensate khi coordinator rời đi.
12. Giữ capacity đủ cho replica còn lại và Pod mới trước khi tăng rollout.
13. Giám sát in-flight, drain duration, errors, redelivery, forced termination và completeness của công việc.
14. Kiểm thử SIGTERM khi có tải, long request, streaming, dependency lỗi và SIGKILL.
15. Có runbook khôi phục: truy vấn durable state, reconcile side effect và retry có điều kiện.

## 20. Ghi nhớ cốt lõi

- **Graceful shutdown là chuyển giao trạng thái phục vụ có kiểm soát:** ngừng nhận việc mới, cho việc cũ hoàn tất hoặc lưu khả năng tiếp tục, rồi mới đóng tài nguyên.
- **Connection draining, readiness và shutdown của ứng dụng là các lớp phối hợp**, không có lớp nào một mình bảo vệ mọi request.
- **Termination grace period hữu hạn**, nên mỗi loại công việc cần completion boundary, deadline và fallback dựa trên durable state.
- **HTTP request, message consumer, background job và saga có cách dừng khác nhau.** Cần dừng nguồn cấp việc trước khi đóng dependency đang được chúng sử dụng.
- **Ack/checkpoint sau commit, idempotency và reconciliation** là chìa khóa để không mất hoặc nhân đôi kết quả khi process chết giữa chừng.
- **Một rollout an toàn cần đủ replica/capacity và kiểm thử có tải**, không chỉ dựa vào việc process thoát với exit code 0.
- **Hệ thống thật sự chịu lỗi khi vẫn đúng sau cả shutdown có kiểm soát lẫn crash bất ngờ.**
