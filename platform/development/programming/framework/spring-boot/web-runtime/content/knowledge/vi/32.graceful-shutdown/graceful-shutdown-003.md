# Bật graceful shutdown và ngừng tiếp nhận yêu cầu mới

> **Module:** Spring Boot – web-runtime → **Dừng có kiểm soát**. Bài Knowledge này tập trung vào cơ chế **graceful shutdown** của HTTP server và điều phối việc **dừng nhận request mới nhưng tiếp tục hoàn tất request đang chạy** trong một cửa sổ thời gian hữu hạn. Các ví dụ chính xác theo **Java 17+, Spring Boot 3.3.x (ví dụ 3.3.13), Spring Framework 6.1.x**. Phần triển khai ngoài JVM minh họa Docker, Kubernetes và load balancer. Không đánh đồng dừng HTTP với hủy hoặc hoàn tất tất cả background jobs, database transactions hay connection từ các hệ thống khác.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Giải thích **immediate shutdown** khác **graceful shutdown** và **traffic draining**, gồm các trạng thái đang phục vụ, ngừng nhận mới, chờ in-flight requests, đóng tài nguyên.
2. Bật graceful shutdown trong Spring Boot **3.3** bằng `server.shutdown=graceful` và điều chỉnh `spring.lifecycle.timeout-per-shutdown-phase` với đơn vị thời gian phù hợp.
3. Hiểu Spring Boot kích hoạt shutdown khi `ApplicationContext` đóng, tại phase rất sớm trong việc dừng `SmartLifecycle` beans, nhưng không phải cứ gọi một HTTP endpoint bất kỳ là JVM sẽ tự đóng.
4. Phân biệt Jetty, Reactor Netty, Tomcat và Undertow trong việc từ chối request mới: ba server đầu dừng chấp nhận ở tầng network, Undertow có thể trả **HTTP 503**; không hứa một status giống nhau cho mọi server/client.
5. Phân biệt `SIGTERM`, `SIGKILL`, EOF, IDE Stop, `kill -9`, Docker stop và Kubernetes Pod termination.
6. Dùng `spring-boot-starter-actuator`, `/actuator/health/readiness` và `/readyz` hợp lý để giúp orchestrator **ngừng gửi traffic trước khi process biến mất**; không nhầm readiness với liveness.
7. Phân bổ `terminationGracePeriodSeconds` cho **preStop + network deregistration + Spring graceful drain + các lifecycle phases + margin**, vì các khoảng này không độc lập.
8. Tạo **Maven project Java 17+ chạy được**, gửi request chậm, phát tín hiệu TERM đúng cách và quan sát request cũ hoàn tất còn request mới bị từ chối.
9. Kiểm thử zero/low-downtime rolling deployment, persistent connections, HTTP/2, SSE, WebSocket, async jobs, cleanup và tình huống hết grace period.
10. Nhận diện và sửa các lỗi thường gặp: không truyền TERM tới PID 1, bật property sai phiên bản, nhầm health endpoint với việc đóng connector, `@PreDestroy` ngủ vô hạn, timeout vượt grace period hoặc phá idempotency.

## 2. Vì sao cần dừng có kiểm soát?

Ứng dụng web hiếm khi dừng chỉ lúc hết khách. Trong thực tế có thể xảy ra:

- Deploy phiên bản mới theo rolling update: instance cũ bị thay khi vẫn đang phục vụ người dùng.
- Kubernetes scale-down/eviction, node drain, autoscaling và bảo trì.
- Docker hoặc systemd gửi stop tới process.
- Người vận hành khởi động lại để sửa lỗi, thay cấu hình, certificate hoặc kết nối.
- Health/liveness policy khiến orchestrator quyết định restart Pod.
- Hệ thống tắt vì lỗi hoặc bị `SIGKILL`/OOM: một số trường hợp **không có cơ hội graceful shutdown**.

Giả sử A đang xử lý `POST /orders` của khách trong 6 giây, còn B gửi `GET /health`. Nếu JVM bị kill ngay, A có thể mất TCP connection/response, khiến người dùng thấy lỗi dù transaction đã commit; nếu tiếp tục nhận request mới tới tận khi process chết, số request gián đoạn còn tăng.

**Mục tiêu lý tưởng của graceful shutdown:**

~~~text
t0: Ứng dụng healthy, accepting traffic
    |
t1: Nhận tín hiệu dừng có kiểm soát (TERM / context close)
    |
t2: Bắt đầu từ chối/yêu cầu routing thôi chuyển request mới tới instance
    |
t3: Những request đã thực sự được nhận trước t2 có cơ hội hoàn tất
    |    (trong thời gian chờ đã định)
    |
t4: Chấm dứt các thành phần còn lại, giải phóng tài nguyên
    |
t5: Process exit; orchestrator có thể terminate nếu quá grace period
~~~

Tình huống **không thể đảm bảo**: nếu một request chạy mãi, bị treo ở database, browser đã bỏ cuộc hoặc process hết bộ nhớ, không phải mọi request đều hoàn thành thành công. Graceful shutdown chỉ cung cấp **một khoảng drain hữu hạn**, không hứa thành công tuyệt đối hoặc exactly-once processing.

## 3. Ba thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Điều nó **không** bảo đảm |
|---|---|---|
| **Graceful shutdown** | Ngừng chấp nhận request mới, cho request đã nhận thời gian hoàn tất, sau đó dừng ứng dụng | Không bảo đảm xử lý tất cả background jobs hoặc stream vô hạn |
| **Traffic draining / deregistration** | Load balancer/ingress/service discovery ngừng chọn instance cho **new traffic** | Không tự đóng listener hoặc cancel work trong JVM |
| **Grace period** | Khoảng thời gian được phép chờ trước khi dừng cưỡng bức/đóng phase | Không phải timeout của mỗi HTTP request hay SLA của client |
| **Readiness** | Instance có sẵn sàng tiếp nhận traffic mới không? | Không phải sự sống/chết của process |
| **Liveness** | Process có cần restart vì không còn khỏe không? | Không được đồng nhất với việc dependency tạm thời không sẵn |
| **In-flight request** | HTTP request đã được instance nhận và đang được xử lý | Không phải mọi công việc liên quan đều nằm trong HTTP connector |
| **Graceful completion** | Request hoàn tất trong cửa sổ và response được trả nếu client còn kết nối | Không chứng minh side effects rollback nếu client đã timeout |
| **Hard termination** | `SIGKILL`/power loss/OOM hoặc force stop | Không gọi đầy đủ lifecycle callbacks |

**Readiness và đóng connector là hai lớp phòng thủ bổ sung.** Đánh dấu not-ready giúp LB tránh gửi thêm request sau khi cập nhật routing; Spring Boot web server có thể ngừng nhận request trực tiếp. Vì propagation của LB bất đồng bộ, có một khoảng race giữa “LB còn tưởng healthy” và “server đã dừng chấp nhận”.

## 4. Cách Spring Boot 3.3 bật graceful shutdown

Cấu hình ngắn nhất:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Bản YAML tương đương:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

**Đặc biệt theo phiên bản:** tài liệu **Spring Boot 3.3** hướng dẫn bật bằng `server.shutdown=graceful`; không lấy mặc định “graceful enabled” từ tài liệu của các nhánh Spring Boot mới hơn rồi áp ngược cho Boot 3.3. Nếu muốn dừng tức thời có chế độ `server.shutdown=immediate`; bài học này chủ động dùng `graceful`.

### Ý nghĩa hai property

- `server.shutdown=graceful`: chọn **graceful** khi đóng embedded web server và application context theo lifecycle bình thường.
- `spring.lifecycle.timeout-per-shutdown-phase=20s`: tối đa **20 giây cho mỗi phase dừng SmartLifecycle**; Spring Boot dùng timeout này cho phase graceful web shutdown. Không nói nó là **tổng timeout process chính xác 20 giây** khi còn nhiều phases hoặc việc cleanup khác.
- `server.port`, `server.tomcat.connection-timeout`, `server.tomcat.keep-alive-timeout` không thay các property trên. Connector/keepalive timeouts dùng cho pha HTTP network khác.
- Tài liệu Spring Boot cho biết shutdown là một phần đóng `ApplicationContext`, diễn ra trong **phase sớm** của việc dừng `SmartLifecycle` beans, giúp request đang xử lý có cơ hội chạy trước khi các bean dependencies bị phá hủy.

### Ví dụ cấu hình có chủ đích cho service đơn giản

~~~properties
server.port=8080

# Spring Boot 3.3: chủ động bật graceful.
server.shutdown=graceful

# Khoảng drain cho phase dừng web server.
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Cấu hình này chỉ nói về application lifecycle **khi context được đóng bình thường**. Nó không biến `kill -9` thành graceful và không quyết định Kubernetes sẽ chờ bao lâu; điều đó thuộc orchestrator.

## 5. Spring Boot thực sự ngừng nhận request mới như thế nào?

Spring Boot 3.3 hỗ trợ graceful shutdown trên **Tomcat, Jetty, Reactor Netty và Undertow**, cho cả Servlet MVC lẫn reactive web applications. Tài liệu chính thức phân biệt rõ cơ chế:

| Embedded server | Điều xảy ra với request mới khi drain | Kỳ vọng khi test |
|---|---|---|
| **Tomcat** | Ngừng chấp nhận requests mới ở tầng network | New TCP connection có thể bị refused/reset/không kết nối thành công; không hứa HTTP 503 |
| **Jetty** | Ngừng chấp nhận requests mới ở tầng network | Phụ thuộc phiên bản, connection và persistent connections |
| **Reactor Netty** | Ngừng chấp nhận requests mới ở tầng network | WebFlux HTTP server có thể từ chối ở network; cần test client behavior |
| **Undertow** | Có thể chấp nhận connection nhưng trả **503 Service Unavailable** cho request mới | Một request mới có thể nhận HTTP 503 rõ ràng |

**Không viết automated assertion “sau SIGTERM mọi request mới phải nhận HTTP 503” khi đang dùng Tomcat.** Một request có thể thất bại vì connection refused hoặc reset trước cả HTTP status. Khi có keep-alive/persistent connection, HTTP/2 multiplexing hoặc request đang được gửi đúng lúc shutdown bắt đầu, kết quả biên có thể khác. Hãy assert **không có yêu cầu nghiệp vụ mới được chấp nhận sau drain**, chứ không buộc tất cả clients thấy cùng mã.

### Khi nào một request được xem là “đã nhận”?

Race condition ở ranh giới:

~~~text
Client C1 mở TCP connection trước TERM
Client C1 gửi request header sau TERM?
Client C2 gửi một HTTP/2 stream mới qua connection cũ?
Load balancer gửi request trong lúc cập nhật EndpointSlice?
~~~

“Connection đã mở trước” không nhất thiết đồng nghĩa “request ứng dụng đã bắt đầu”. Việc xử lý sẽ phụ thuộc server, HTTP protocol và connector state. Vì vậy test cần nhìn **request start log/metric thực tế**, không chỉ thời điểm mở socket. Với async streaming, nếu request tồn tại không kết thúc, drain có thể đợi đến grace timeout.

## 6. Vòng đời Spring ApplicationContext và SmartLifecycle

Graceful shutdown diễn ra khi `ApplicationContext` được đóng. Spring Framework có lifecycle management, trong đó `SmartLifecycle` hỗ trợ:

- `start()`: bắt đầu hoạt động.
- `stop(Runnable callback)`: yêu cầu dừng bất đồng bộ rồi **gọi callback.run()** khi hoàn tất.
- `getPhase()`: xác định thứ tự.
- `isRunning()`/`isAutoStartup()`: trạng thái và auto-start.

Các phases có quy tắc: phase thấp hơn **start trước**, **stop sau**; phase cao hơn start sau, stop trước. Spring Boot web graceful shutdown nằm trong phase sớm của tiến trình dừng, nhằm cho HTTP in-flight tiếp tục trước khi tài nguyên cấp dưới bị dọn.

### Vì sao timeout-per-shutdown-phase không bằng tổng thời gian process?

Giả sử có ba nhóm lifecycle phase, mỗi nhóm có thể chờ tối đa 20 giây, và các destroy callbacks khác; tổng wall-clock shutdown có thể lớn hơn 20 giây. Chọn `terminationGracePeriodSeconds` bằng đúng 20 giây chỉ vì property Spring bằng 20s có thể khiến Kubernetes gửi SIGKILL trước khi cleanup hoàn tất.

**Không tự đặt phase cho một bean critical bằng số ngẫu nhiên** chỉ để đảm bảo nó dừng “sau Tomcat”. Nếu có background consumer, queue publisher, scheduler hoặc resource pool phụ thuộc HTTP/draining, hãy đọc contract phases của các thành phần liên quan, đưa ra stop ordering có chủ đích và integration test. Đặc biệt không đặt việc đóng DataSource quá sớm khi in-flight controller vẫn đang dùng transaction.

### @PreDestroy có đúng vai trò gì?

`@PreDestroy` và DisposableBean destruction thường xảy ra trong giai đoạn dọn bean sau lifecycle stops. Nó phù hợp cho cleanup resource nhỏ/đóng handle, **không phải một chiến thuật đáng tin để tự làm traffic drain bằng `Thread.sleep(30000)`**. Nếu cần ngừng nhận business jobs trước khi shutdown, thiết kế admission/readiness và lifecycle consumer riêng.

~~~java
// Snippet trong một @Component; không phải chương trình độc lập.
@PreDestroy
public void onDestroy() {
    logger.info("Closing application-owned resource");
    resource.close();
}
~~~

Nếu `resource.close()` có thể bị treo, cần bounded timeout và metric; tránh một @PreDestroy blocking vô hạn làm process bị SIGKILL khi orchestration grace window hết.

## 7. SIGTERM, SIGKILL và quá trình nhận tín hiệu

Trên Linux/container, có sự khác biệt cơ bản:

| Cách dừng | Cơ chế thông thường | Graceful shutdown có thể xảy ra? |
|---|---|---|
| `kill -TERM PID` | Gửi SIGTERM tới process | Có, nếu JVM nhận TERM và app shutdown bình thường |
| Docker `docker stop` | Gửi signal stop (mặc định TERM), đợi stop timeout rồi force | Có nếu entrypoint chuyển signal và đủ grace |
| Kubernetes Pod termination | preStop nếu có, sau đó TERM và cuối cùng KILL khi hết grace | Có nếu TERM đến JVM PID 1/đúng process |
| `kill -9 PID` | SIGKILL tức thời | **Không**; JVM không chạy shutdown hooks đúng cách |
| OOM kill/power loss | Không có cơ hội chạy lifecycle | **Không** |
| IDE nút Stop | Phụ thuộc IDE có gửi TERM hay terminate mạnh | Không được mặc định coi là SIGTERM |
| CTRL+C trong terminal | Thường phát SIGINT/interrupt đến foreground process group | Thường cho JVM cơ hội shutdown, nhưng nên test đúng môi trường |
| Windows Task Manager / Stop-Process | Phụ thuộc cơ chế kết thúc process | Không đồng nghĩa Linux SIGTERM |

**Dockerfile ENTRYPOINT dạng exec** nên dùng để JVM là process nhận signal:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/graceful-demo-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Nếu dùng shell-form entrypoint mà shell không `exec` Java, signal có thể tới shell chứ không tới JVM đúng cách. Không phải mọi entrypoint shell đều sai, nhưng cần chủ động forward TERM và wait child process. Tránh launcher/background helper khiến JVM không thấy tín hiệu.

### Khi dừng quá đột ngột

- Trên Linux, `kill -9` không thể được bắt bằng Java shutdown hook.
- Container runtime có thể force terminate khi hết grace period.
- Cloud load balancer có thể vẫn route traffic một thời gian ngắn do propagation.
- Nếu kernel OOM killer đóng JVM, không có cơ hội complete in-flight requests.
- Vì thế transactional durability, idempotency, retry safety và distributed architecture vẫn phải chịu được **unexpected termination**.

Graceful shutdown giúp giảm gián đoạn khi **dừng có chủ đích**, không làm hệ thống miễn nhiễm với crash.

## 8. Readiness khác liveness: làm sao bảo load balancer thôi gửi request?

**Readiness:** instance có được chọn cho **new traffic** hay không?  
**Liveness:** instance còn đủ khỏe để tiếp tục sống hay phải restart?

Spring Boot có `ApplicationAvailability` cùng `ReadinessState` và `LivenessState`. Trong lifecycle shutdown, readiness sẽ chuyển sang `REFUSING_TRAFFIC`; liveness có thể vẫn `CORRECT` trong giai đoạn drain. Đây là điều bình thường: app **còn sống để hoàn tất request cũ nhưng không muốn nhận request mới**.

| Giai đoạn Spring Boot | Liveness | Readiness | Xử lý requests |
|---|---|---|---|
| Starting | BROKEN hoặc chưa đủ thông tin | REFUSING_TRAFFIC | Chưa nhận traffic |
| Started, chưa ready | CORRECT | REFUSING_TRAFFIC | Chưa chọn làm target chính |
| Ready | CORRECT | ACCEPTING_TRAFFIC | Nhận traffic |
| Graceful shutdown | CORRECT | REFUSING_TRAFFIC | Từ chối mới, xử lý in-flight |
| Shutdown complete | Không còn runtime | Không còn probe | Process đã dừng |

Không viết readiness probe phụ thuộc trực tiếp vào mọi external service một cách mù quáng; outage DB dùng chung có thể khiến toàn bộ Pods not-ready và không còn endpoint. Liveness đặc biệt **không nên** fail chỉ vì một downstream API tạm thời chậm nếu app vẫn có thể phục hồi/circuit break.

### Dùng Spring Boot Actuator

Thêm Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Với Spring Boot 3.3, trong môi trường Kubernetes, liveness/readiness health groups có thể được auto-enable. Để lab chạy cả trên máy local, khai báo rõ:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Các đường tương ứng:

~~~text
GET /actuator/health/liveness    (health group liveness)
GET /actuator/health/readiness   (health group readiness)
GET /livez                       (additional path trên cổng app chính)
GET /readyz                      (additional path trên cổng app chính)
~~~

`management.endpoint.health.probes.add-additional-paths=true` làm `/livez` và `/readyz` có trên **main web server port**. Điều này hữu ích nếu Actuator quản lý ở cổng khác, vì một management port còn sống không bảo đảm cổng application còn nhận traffic. Không expose toàn bộ actuator `env`, `configprops`, `heapdump`, `shutdown` chỉ để có probes.

**Trong shutdown:** Boot chuyển readiness state thành refusing, nhưng chính HTTP listener cũng đang dừng chấp nhận request mới. Một probe gọi sau TERM **có thể không truy cập được** để nhìn JSON readiness=503. Điều quan trọng là orchestrator/drainer dùng trạng thái và termination lifecycle; test không được bắt buộc `curl /readyz` trả HTTP 503 sau TERM khi Tomcat đã từ chối TCP.

## 9. Phối hợp hai lớp: rút instance khỏi routing và dừng connector

Cần phân biệt:

~~~text
Load Balancer Layer                  Spring Boot process
------------------------------       -----------------------------
Mark endpoint not ready              Receive TERM / context close
Stop selecting for new traffic        Switch readiness REFUSING_TRAFFIC
Existing requests may continue        Embedded server stops new accepts
Propagation takes time                Finish in-flight during grace
External connections may persist      Close resources + exit
~~~

Nếu chỉ đổi readiness, process vẫn có thể nhận direct traffic, traffic đi qua một load balancer khác, hoặc những requests đã được queue trên đường. Nếu chỉ dừng connector, LB có thể tiếp tục gửi request đến instance đã đóng socket cho tới khi routing cập nhật, khiến gateway trả 502/503. **Kết hợp cả hai** và cho phép thời gian mạng hội tụ.

### Có nên tạo custom Filter trả 503 khi draining?

Một custom admission filter có thể hữu ích trong hệ thống yêu cầu pre-drain trước khi TERM, nhưng không phải điều kiện để Boot graceful hoạt động. Nếu filter bắt đầu trả 503 **quá sớm**, cả request đã in-flight hoặc health probes có thể bị tác động; nếu quá muộn, LB chưa kịp bỏ instance. Cần có state machine và test concurrency/cross-proxy.

Không triển khai `Thread.sleep(5000)` trong mọi controller để chờ load balancer; đó là anti-pattern làm tăng latency của request đang phục vụ. Nếu cần buffer thời gian cho route deregistration, dùng orchestrator lifecycle hoặc một drain protocol có xác thực.

## 10. Kubernetes Pod termination: thứ tự và giới hạn tổng

Kubernetes thường gửi SIGTERM khi Pod được yêu cầu dừng theo chính sách termination. Một luồng đơn giản:

~~~text
kubectl delete pod / Deployment rolling update
         |
         v
Pod enters Terminating; grace-period countdown begins
         |
         +--> EndpointSlice marks terminating endpoint ready=false
         |    (traffic removal propagates asynchronously)
         |
         +--> kubelet runs preStop if configured
         |    (this time is PART OF the same termination grace budget)
         |
         v
kubelet/container runtime sends TERM to process
         |
         v
Spring Boot graceful shutdown drains in-flight requests
         |
         v
JVM cleanup and exit
         |
         +--> if still running after grace period: SIGKILL
~~~

**Chi tiết quan trọng:** Kubernetes bắt đầu đếm `terminationGracePeriodSeconds` **trước khi** thực thi `preStop`. Hook được gọi trước TERM và phải kết thúc mới đến TERM. Nếu hook mất 8 giây, 8 giây ấy **không phải khoản cộng thêm ngoài grace period**. Kubelet có thể yêu cầu một khoảng mở rộng ngắn đặc biệt khi preStop vượt deadline, nhưng không nên coi đó là ngân sách đáng tin trong thiết kế.

EndpointSlice của Pod đang terminating đặt `ready=false`, giúp tránh route traffic thường; nhưng propagation qua kube-proxy/ingress/external LB không phải tức thì. Một số workloads cần `preStop` chờ ngắn để external load balancer cập nhật trước TERM; đó là lựa chọn cần đo và cân đối thời gian, **không phải default bắt buộc**.

### Ví dụ phân bổ ngân sách 45 giây

| Khoản | Số giây ví dụ | Điều cần lưu ý |
|---|---:|---|
| Kubernetes `terminationGracePeriodSeconds` | 45 | Tổng thời gian cho toàn bộ quá trình |
| Optional preStop/drain delay | 5 | Ăn vào 45, không được cộng thêm |
| Spring graceful web phase | 20 | `spring.lifecycle.timeout-per-shutdown-phase=20s` |
| Các lifecycle phases/resource cleanup khác | Dự trù 10 | Có thể có nhiều phases; phải đo |
| Margin network/runtime/overhead | Dự trù 10 | Chống biến động, signal delivery |
| Tổng phân bổ dự kiến | 5 + 20 + 10 + 10 = 45 | Chỉ là kế hoạch, không phải cam kết thời gian tuyệt đối |

Một ứng dụng có **nhiều SmartLifecycle phases**, @PreDestroy tốn lâu hoặc background jobs còn chạy có thể cần Kubernetes grace period lớn hơn hoặc thay quy trình cleanup. Không dùng công thức `terminationGracePeriodSeconds = spring.lifecycle.timeout-per-shutdown-phase` trong mọi hệ thống.

### Deployment YAML minh họa hợp lệ

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graceful-demo
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: graceful-demo
  template:
    metadata:
      labels:
        app: graceful-demo
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: graceful-demo:1.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /livez
              port: 8080
            periodSeconds: 2
            failureThreshold: 30
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

**Cách dùng đúng:** manifest này có hiệu lực khi cluster đã có image `graceful-demo:1.0` (đã build/push hoặc load vào local cluster), và image có `/bin/sh` cùng `sleep`. Với distroless image không có shell, dùng cơ chế khác hoặc bỏ hook. Chỉ bật preStop 5 giây nếu đã xác định cần thời gian draining route; có thể bỏ `preStop` khi EndpointSlice/controller đủ đáp ứng. Đây là cấu hình **minh họa cần hiệu chỉnh**, không phải manifest cho một cluster production bất kỳ.

`maxUnavailable: 0` cùng `maxSurge: 1` giúp rolling update duy trì các replicas sẵn sàng trong điều kiện scheduling/capacity cho phép; **không hứa zero downtime** nếu chỉ có một backend unhealthy, affinity sai, PodDisruptionBudget/cluster capacity không đáp ứng hoặc LB vẫn route đến Pod cũ. Kiểm behavior của ingress/LB đang dùng.

### Vì sao tránh dùng shutdown endpoint HTTP công khai?

Spring Boot Actuator có endpoint `/actuator/shutdown` nhưng **disabled by default**; không nên bật public HTTP shutdown để orchestration “dễ dừng”. Nếu cần admin endpoint, phải đặt trong management network có quyền và chính sách chặt; thường dùng TERM/Pod lifecycle an toàn hơn, ít attack surface hơn.

## 11. Lab chạy được: Spring Boot MVC xử lý request cũ trong graceful phase

Bài lab dùng **một ứng dụng MVC/Tomcat**, một route HTTP chậm và một route đếm in-flight. Mục tiêu không phải tạo một hệ job queue, mà là trực tiếp quan sát listener ngừng nhận mới.

~~~text
Terminal A:
  java -jar graceful-demo.jar
      |
      +-- GET /api/work?delayMs=8000  [request đã nhận, xử lý 8s]
      +-- GET /api/work?delayMs=100   [request mới thử sau TERM]
      +-- GET /api/active             [số request đang trong controller]
      +-- GET /readyz                [liveness/readiness]
   
Terminal B:
  curl request 8s
  kill -TERM PID
  try new curl
  wait for request 8s + JVM exit
~~~

### 11.1. Cấu trúc dự án

~~~text
graceful-demo/
  pom.xml
  src/
    main/
      java/
        example/
          graceful/
            GracefulDemoApplication.java
      resources/
        application.properties
    test/
      java/
        example/
          graceful/
            GracefulDemoApplicationTests.java
~~~

### 11.2. Maven pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>graceful-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ở đây `spring-boot-starter-web` mang Spring MVC và embedded Tomcat; `spring-boot-starter-actuator` cung cấp health probes, `spring-boot-starter-test` chỉ ở test scope. Không thêm WebFlux, GraphQL hay WebSocket vì không thuộc use case.

### 11.3. application.properties đầy đủ

~~~properties
server.port=8080

# Spring Boot 3.3 cần bật rõ:
server.shutdown=graceful

# Thời gian cho MỖI shutdown phase, trong đó có graceful web drain:
spring.lifecycle.timeout-per-shutdown-phase=20s

# Health probes dùng được cả local và trên cổng ứng dụng chính:
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true

# Không lộ exception hoặc stacktrace từ Spring Boot error handler:
server.error.include-message=never
server.error.include-exception=false
server.error.include-stacktrace=never
~~~

Không đặt `management.endpoint.shutdown.enabled=true`; không cần HTTP shutdown endpoint để lab hoạt động.

### 11.4. File Java ứng dụng hoàn chỉnh

Tạo `src/main/java/example/graceful/GracefulDemoApplication.java`:

~~~java
package example.graceful;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class GracefulDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(GracefulDemoApplication.class, args);
    }

    public record WorkResult(long delayMs, boolean completed) {
    }

    @RestController
    static class WorkController {
        private static final Logger log =
                LoggerFactory.getLogger(WorkController.class);

        private final AtomicInteger active = new AtomicInteger();

        @GetMapping("/api/work")
        public ResponseEntity<WorkResult> work(
                @RequestParam(defaultValue = "150") long delayMs)
                throws InterruptedException {

            // Chỉ cho demo: ngăn input vô hạn hoặc âm.
            if (delayMs < 0 || delayMs > 30000) {
                return ResponseEntity.badRequest().build();
            }

            int count = active.incrementAndGet();
            log.info("work-start delayMs={} active={}",
                    delayMs, count);

            try {
                Thread.sleep(delayMs);
                log.info("work-finished delayMs={}", delayMs);
                return ResponseEntity.ok(
                        new WorkResult(delayMs, true));
            } finally {
                int remaining = active.decrementAndGet();
                log.info("work-cleanup active={}", remaining);
            }
        }

        @GetMapping("/api/active")
        public Map<String, Integer> active() {
            return Map.of("active", active.get());
        }
    }

    @Component
    static class ResourceLifecycle {
        private static final Logger log =
                LoggerFactory.getLogger(ResourceLifecycle.class);

        @PreDestroy
        void onDestroy() {
            log.info("application-resources-destroying");
        }
    }
}
~~~

**Giải thích:**

- `WorkController` dùng `AtomicInteger` để đếm request còn nằm trong phần xử lý, không dùng static global counter dùng chung nhiều processes. Mục đích đo locally cho lab, không phải metric production hoàn chỉnh.
- `Thread.sleep(delayMs)` **cố tình blocking** nhằm quan sát drain trong Servlet MVC. Không dùng nó để mô phỏng task production; với workload thật cần DB/HTTP timeouts và bounded work.
- Code không tự gọi `System.exit` trong controller; Spring Boot quản lý graceful shutdown khi context closing bình thường.
- `@PreDestroy` chỉ ghi log cho thấy thứ tự lifecycle cleanup, không cố sleep thêm và không quyết định request nào được nhận.
- Body thành công là record serialize JSON từ Jackson trên MVC, ví dụ `{"delayMs":8000,"completed":true}`.
- Sau TERM, Tomcat có thể từ chối kết nối mới **ở network layer**, nên client có thể không nhận bất kỳ HTTP status nào. Không có đoạn Java nào trong controller buộc Spring trả HTTP 503.
- Nếu client đã đóng connection trước khi work hoàn thành, server có thể gặp lỗi ghi response; việc `work-finished` log xuất hiện không đảm bảo caller đã nhận được body.

### 11.5. JUnit integration test (không kill JVM trong test)

Tạo `src/test/java/example/graceful/GracefulDemoApplicationTests.java`:

~~~java
package example.graceful;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class GracefulDemoApplicationTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void shortRequestCompletes() {
        ResponseEntity<GracefulDemoApplication.WorkResult> response =
                http.getForEntity(
                    "/api/work?delayMs=10",
                    GracefulDemoApplication.WorkResult.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(10L, response.getBody().delayMs());
        assertEquals(true, response.getBody().completed());
    }

    @Test
    void activeCountEventuallyReturnsToZero() {
        ResponseEntity<Map> response =
                http.getForEntity("/api/active", Map.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(0, response.getBody().get("active"));
    }
}
~~~

Hai tests xác minh REST behavior bình thường. **Chúng không chứng minh graceful shutdown đúng**, vì kill JVM đang chạy JUnit trong chính process không phù hợp. Cần process-level integration test tiếp theo để kiểm TERM và in-flight requests. Trong test `RANDOM_PORT` ghi đè property `server.port=8080` để tránh tranh cổng.

### 11.6. Chạy tests và build executable JAR

~~~bash
mvn clean package
~~~

Kỳ vọng **Maven BUILD SUCCESS** và hai JUnit methods pass khi dependencies/JDK phù hợp. File output:

~~~text
target/graceful-demo-0.0.1-SNAPSHOT.jar
~~~

Chạy server trong một terminal:

~~~bash
java -jar target/graceful-demo-0.0.1-SNAPSHOT.jar
~~~

Terminal khác:

~~~bash
curl -i http://localhost:8080/api/work?delayMs=100
curl -i http://localhost:8080/api/active
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
~~~

Khi app ready, `/readyz` và `/livez` thường trả HTTP 200 cùng JSON health group có `"status":"UP"`; đây là **lúc trước shutdown**. Request `/api/work?delayMs=100` trả HTTP 200 với JSON chứa `delayMs:100` và `completed:true`.

### 11.7. Kiểm SIGTERM với process thật trên Linux/WSL/macOS

Chạy script Bash dưới đây từ thư mục gốc **sau khi đảm bảo cổng 8080 đang rảnh**. Không chạy server từ terminal khác cùng lúc. Script đợi `/readyz` báo ready, khởi động một request 8 giây, gửi TERM sau 1 giây rồi thử request mới:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

JAR="target/graceful-demo-0.0.1-SNAPSHOT.jar"
java -jar "$JAR" > graceful-demo.log 2>&1 &
APP_PID=$!

ready=false
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8080/readyz >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done

if [ "$ready" != true ]; then
  echo "App was not ready in 30s"
  cat graceful-demo.log
  kill -TERM "$APP_PID" 2>/dev/null || true
  exit 1
fi

curl -fsS \
  "http://localhost:8080/api/work?delayMs=8000" \
  > /tmp/graceful-inflight.json &
REQUEST_PID=$!

sleep 1
kill -TERM "$APP_PID"

echo "Trying a NEW request after SIGTERM:"
curl -i --max-time 2 \
  "http://localhost:8080/api/work?delayMs=100" || true

wait "$REQUEST_PID"
echo "Existing request result:"
cat /tmp/graceful-inflight.json
echo

wait "$APP_PID" || true
echo "Application log:"
tail -n 35 graceful-demo.log
~~~

Các tiện ích Bash, curl, seq, tail và đường `/tmp` giả định **Linux/macOS/WSL**. Trên Windows PowerShell, `Stop-Process` thường không tạo cùng SIGTERM semantics; nên chạy trong WSL/Linux container để test process signals chính xác. Script trực tiếp chạy `java -jar`, không chạy `mvn spring-boot:run` vì Maven launcher làm PID/signal behavior khó suy ra.

**Kết quả mong đợi khi request 8 giây đã thực sự được server nhận:**

~~~text
Trying a NEW request after SIGTERM:
(curl có thể báo Connection refused/reset hoặc HTTP error tùy connector)
Existing request result:
{"delayMs":8000,"completed":true}
Application log:
... work-start delayMs=8000 ...
... Commencing graceful shutdown ...
... work-finished delayMs=8000 ...
... work-cleanup active=0 ...
... application-resources-destroying ...
~~~

**Đây là output minh họa, không phải transcript byte-for-byte.** Logger timestamps/format/order và status của new connection phụ thuộc runtime, OS, process timing; `tail` không luôn hiện đủ mọi dòng. Điều test cốt lõi là request đã nhận trước TERM **được hoàn tất trong 20 giây** và HTTP server **không tiếp nhận work mới sau khi graceful bắt đầu**. Nếu race khiến request chậm chưa thật sự được nhận trước TERM, chạy lại có đồng bộ bằng log/metric thay vì chỉ sleep 1 giây; không tuyên bố test pass dựa trên race.

### 11.8. Thử trường hợp request dài hơn grace period

Đổi thời gian request trong một bản test khác thành 25 giây khi `timeout-per-shutdown-phase=20s`. Nếu request vẫn in-flight sau khoảng drain, nó **không được bảo đảm** hoàn tất; connector có thể đóng hoặc process bị orchestration kill theo cấu hình. Trong production cần timeouts cấp request/dependency không vượt grace, route chính sách job lâu, hoặc deadline/async model khác. Không tăng grace vô hạn chỉ để mọi work cố tiếp tục.

### 11.9. Docker test

Build image từ Dockerfile ở mục 7:

~~~bash
mvn clean package
docker build -t graceful-demo:1.0 .
docker run -d --rm --name graceful-demo \
  -p 8080:8080 graceful-demo:1.0
~~~

Khi app đã ready, trong terminal khác chạy một request dài rồi dừng container với timeout có chủ đích:

~~~bash
curl -fsS "http://localhost:8080/api/work?delayMs=8000"
~~~

~~~bash
docker stop -t 30 graceful-demo
~~~

Hai lệnh được chạy **đồng thời trên hai terminals** để request còn in-flight lúc stop; nếu đã chờ curl hoàn tất rồi mới stop thì không có bài test drain. `docker stop -t 30` cho container 30 giây sau stop signal trước force termination; cần đủ cho web shutdown phase và các cleanup liên quan. Docker có thể dùng stop signal khác nếu image/runtime cấu hình khác; kiểm thực tế.

## 12. Đừng nhầm dừng HTTP với dừng mọi công việc nền

Spring Boot graceful server shutdown tập trung vào **HTTP in-flight requests**. Nhiều loại công việc khác có lifecycle riêng:

| Loại công việc | Có tự được bao phủ hoàn toàn bởi server.shutdown=graceful không? | Cần làm gì thêm? |
|---|---|---|
| Synchronous MVC request đang xử lý | Được server tạo cửa sổ drain khi được nhận trước shutdown | Bounded service/dependency timeouts |
| WebFlux HTTP reactive request | Có web-server drain theo connector | Cancellation/discard/cleanup đúng cách |
| Scheduled `@Scheduled` job | Không mặc định là HTTP in-flight | Dừng lịch mới, chờ/cancel work đang chạy theo executor policy |
| `@Async` tasks | Không đơn thuần do web server quản lý | Task executor shutdown policy, bounded queue/timeouts |
| Kafka/Rabbit/JMS consumers | Không phải HTTP request | Stop polls/listeners, commit/ack policy và replay/idempotency |
| Quartz scheduler | Có scheduler lifecycle riêng | Graceful stop/quiesce config phù hợp |
| Background file transfer/object storage | Có thể còn sau HTTP response/202 | Abort/complete/cleanup multipart uploads và temp files |
| DB transactions | Không tự rollback vì TERM | Transaction manager/driver timeouts và data integrity |
| WebSocket sessions | Kết nối lâu và bidirectional | Protocol close/drain policy, reconnect |
| SSE/long polling | HTTP stream sống lâu | Max lifetime, cancellation, reconnect semantics |
| Distributed locks/leases | Không dựa vào HTTP connector | Bounded lease, release/renew, failover |
| Thread tự tạo `new Thread(...)` | Spring có thể không quản lý lifecycle | Executor service/SmartLifecycle và shutdown coordination |

Một scheduled job đẩy dữ liệu lên Kafka có thể đang chạy khi web connector ngừng nhận mới. Nếu process dừng và job chưa checkpoint, cần at-least-once processing và idempotency hoặc một protocol tương ứng, không trông chờ property HTTP để đảm bảo exactly-once.

### Chặn khởi động việc mới ở background worker

Một consumer có thể cần hai bước:

1. **Quiesce:** ngừng nhận thêm messages/tasks từ broker/queue.
2. **Drain:** hoàn tất những tasks đã nhận, commit/ack an toàn trong timeout.
3. **Close:** giải phóng producer/consumer connections.
4. **Force stop:** sau deadline, abort có kiểm soát và dựa vào retry/recovery khi khởi động instance mới.

Các bước này có thể được quản lý qua `SmartLifecycle`, listener container hoặc executor shutdown policy, **không** được thay bằng `@PreDestroy Thread.sleep(...)` không có ownership/metric.

## 13. SmartLifecycle cho thành phần riêng: tránh deadlock và callback bị quên

Nếu application quản lý một background task consumer có stop không đồng bộ, có thể dùng `SmartLifecycle`. Trong interface này:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
~~~

Đây là **trích API rút gọn** để giải thích, không phải file Java tự định nghĩa lại Spring interface trong project. Khi tự implement `stop(Runnable callback)`:

- Báo component ngừng nhận work mới trước khi drain.
- Gửi tín hiệu stop cho worker/executor phù hợp.
- Đợi/cancel jobs theo một giới hạn và ghi metrics.
- **Bắt buộc gọi `callback.run()` sau khi xử lý stop**, kể cả error path, để lifecycle processor không chờ đến deadline.
- Không block event loop hoặc lifecycle thread tùy tiện.
- Xác định `getPhase()` có chủ đích theo phụ thuộc tài nguyên và web server; phase order đảo ngược lúc shutdown.
- Tránh thiết kế mà HTTP server chờ background jobs trong khi jobs chờ một bean dependency đã bị đóng.

Ví dụ pseudo-flow:

~~~text
stop(callback):
    acceptingNewTasks = false
    askConsumerToStopPolling()
    finishOrCancelAlreadyClaimedTasksBeforeDeadline()
    commit/ack/rollbackAccordingToProtocol()
    releaseOwnedResources()
    callback.run()
~~~

**Không biến pseudo-flow thành production code** khi chưa có SDK broker và contract của task cụ thể. Với Spring Kafka, RabbitMQ, Quartz hay TaskExecutor, ưu tiên các lifecycle settings được thư viện hỗ trợ và test chính xác.

## 14. Startup–readiness–shutdown: vòng đời đầy đủ

Traffic sẽ chỉ ổn định khi **cả startup và shutdown** được điều phối. Một instance vừa mới khởi động có thể có TCP port sớm hơn lúc data cache/warmup/authorization/configuration hoàn chỉnh; readiness giúp ngăn gửi traffic trước khi ready.

~~~text
STARTUP
  process starts
  context initialization
  Liveness CORRECT, Readiness REFUSING_TRAFFIC
  ApplicationReadyEvent / startup tasks complete
  Readiness ACCEPTING_TRAFFIC
  load balancer begins routing

RUNNING
  new HTTP requests accepted
  in-flight requests complete
  health/metrics monitored

TERMINATION
  Pod marked Terminating / context close
  Readiness REFUSING_TRAFFIC
  no new requests accepted by web server
  in-flight requests drain
  other components cleanup
  process exits
~~~

Một health probe thành công **không có nghĩa** toàn bộ business paths có thể xử lý tốt; một readiness probe quá nặng cũng có thể gây tải/DB storm. Thiết kế liveness đơn giản phản ánh JVM có khả năng phục hồi; readiness phản ánh traffic acceptance và những dependency critical được cân nhắc cẩn thận.

### Phải chờ readiness khi rolling update

Nếu orchestrator coi Pod mới available quá sớm, nó có thể hạ Pod cũ trước khi Pod mới sẵn sàng phục vụ. Phối hợp readinessProbe, startupProbe nếu startup chậm, strategy rollout, replica count, PodDisruptionBudget và autoscaling. Graceful shutdown của Pod cũ không sửa được readiness của Pod mới.

## 15. Kết nối lâu: keep-alive, HTTP/2, SSE và WebSocket

### HTTP/1.1 keep-alive

Một client có thể giữ TCP connection mở để gửi nhiều HTTP requests. Khi graceful bắt đầu, server-specific behavior có thể khác giữa **connection đã mở** và **request mới**. Đừng đo drain bằng việc chỉ mở socket trước TERM rồi gửi request sau; phải xác nhận request đã được servlet/handler nhận trước thời điểm dừng.

Một HTTP response có thể thêm `Connection: close` hoặc đóng connection sau response tùy server/protocol, nhưng không phải một header mà Spring Boot bắt buộc gửi cho mọi request khi graceful trên mọi server. Khi test, chấp nhận connection refused/reset thay vì cố bắt HTTP 503 trên Tomcat.

### HTTP/2 multiplexing

Nhiều concurrent streams trên một connection; graceful draining có thể liên quan tới GOAWAY/stream rules tùy implementation. Không lấy behavior HTTP/1.1 ở Tomcat rồi suy ra HTTP/2 requests mới sẽ luôn fail bằng cùng một code. Cần test client thực, gateway và server versions, đặc biệt với gRPC/HTTP2 nếu service có.

### SSE và streaming

Một `text/event-stream` response có thể tồn tại nhiều phút/giờ. Nếu không có giới hạn, graceful shutdown có thể đợi đến timeout phase, rồi đóng stream chưa hoàn tất. Cần quy định heartbeat, max stream lifetime, event resume IDs và client reconnect; khi drain, có thể gửi thông điệp “server retiring” theo giao thức của app nếu response còn writable, nhưng không hứa mọi client nhận được.

### WebSocket

WebSocket không phải một HTTP request ngắn sau handshake. Kết nối hai chiều cần close handshake, session drain hoặc client reconnect policy riêng, có thể không cùng semantics với Servlet in-flight HTTP requests. Nếu dùng Spring WebSocket/STOMP, kiểm cách framework/broker dừng session subscriptions, ack, pending messages và sự phối hợp với load balancer.

### Download/upload lớn

Upload/download hàng GiB có thể kéo dài hơn shutdown grace period; cân nhắc resumable upload, chunking, object storage direct access, storage cleanup hoặc policy không xóa instance trong thời gian transfer critical. Đừng đặt phase 10 phút cho mọi service chỉ để hiếm khi có file upload; tách workload/route có thể tốt hơn.

## 16. Database transactions, idempotency và client disconnect

Graciously waiting for in-flight HTTP requests không đồng nghĩa “không bao giờ có duplicate business operations”. Ví dụ:

1. Client gửi POST tạo đơn hàng tới instance A.
2. A commit DB transaction.
3. TERM tới A hoặc gateway/client ngắt trước khi response đến client.
4. Client thấy timeout/connection reset, tưởng request thất bại.
5. Client retry POST sang instance B và có nguy cơ tạo đơn hàng thứ hai.

Phòng ngừa:

- Sử dụng **idempotency key** hoặc unique business constraint cho mutations quan trọng.
- Cho client truy vấn trạng thái giao dịch/job bằng stable identifier.
- Không viết logic “cứ IOException khi trả response thì rollback đã commit” — transaction có thể hoàn tất.
- Với distributed transaction/saga, thiết kế retry/reconciliation riêng.
- Với queue-based consumers, at-least-once delivery cần deduplication và ack/commit đúng thời điểm.

Graceful shutdown giảm xác suất cắt request giữa chừng, **không thay transactional correctness**.

## 17. Đo tải và tính ngân sách drain theo in-flight workload

Nếu HTTP server có 100 requests đang thực thi, trong đó một số mất 15 giây và phần còn lại 0.2 giây, grace 20 giây có thể đủ khi dependencies healthy. Nhưng nếu có một DB query treo 90 giây, phase 20 giây hết hạn trước khi nó hoàn tất.

Cách đo:

- Active HTTP server requests và duration histogram/tail latency theo route.
- Active servlet worker threads/queued requests; số tasks đang xử lý.
- Outbound HTTP client connection pool pending/active.
- DB connections active/pending, query timeouts, transaction durations.
- Thời gian từ SIGTERM tới “graceful shutdown complete”.
- Số in-flight requests còn lại khi grace timeout.
- Client disconnects/502/503/504 trong deployment windows.
- Número pod terminating/EndpointSlice readiness and ingress backend routing logs.
- Background consumer pending work/unacked messages và cleanup duration.

**Một công thức tư duy, không phải cam kết:**

~~~text
T_required_for_shutdown >= max(remaining_times_of_inflight_requests)
                          + lifecycle_cleanup
                          + network/orchestrator_margin

T_Kubernetes >= T_preStop + T_spring_lifecycle_total
                + T_other_cleanup + margin
~~~

Nếu nhiều lifecycle phases stop song song hay phụ thuộc nhau, tính theo **critical path** thực và kiểm việc Spring lifecycle timeout **theo từng phase**. Không lấy max request duration bằng p50; nên dùng request-time limits phù hợp để có bound hữu hạn.

### Graceful không có nghĩa tăng thread count

Nếu service đang quá tải, một đợt rolling shutdown có thể làm lưu lượng dồn vào replicas còn lại. Có thể cần tăng replica/`maxSurge`, warmup và readiness gating, không phải chỉ tăng `server.tomcat.threads.max` hoặc `timeout-per-shutdown-phase`.

## 18. Observability và log cần có khi shutdown

Một vòng đời được instrument tốt có thể log:

~~~text
time=... event=termination_requested instance=pod-a
time=... event=readiness_refusing_traffic instance=pod-a
time=... event=graceful_shutdown_started active_http_requests=12
time=... event=graceful_shutdown_completed active_http_requests=0 elapsed_ms=...
time=... event=resource_cleanup_started
time=... event=process_exit
~~~

Đây là **sơ đồ log mong muốn**, không phải định dạng log mặc định của Spring Boot. Có thể ghi các events với SLF4J và metrics/Actuator/Micrometer theo version/hệ monitoring; không nên phát lộ credentials/PII trong request path hoặc body.

### Dữ liệu hữu ích ở các tầng

| Tầng | Quan sát |
|---|---|
| Kubernetes | Pod Terminating, deletionTimestamp, terminationGracePeriodSeconds, preStop outcome, exit code 137/143 context |
| EndpointSlice | Endpoint terminating, `ready=false`, trạng thái routing |
| Ingress/LB | Requests tới terminating endpoint, 502/503/504, connection errors |
| JVM/Spring Boot | TERM observed, web graceful begin/end, SmartLifecycle stop duration, @PreDestroy |
| HTTP server | Active connections/in-flight requests, long tail durations |
| Downstream | Calls interrupted/timeout/cancel, database rollback/commit |
| Client | Retry count, connection reset, response completed vs timed out |

Exit code `143` thường tương ứng Linux SIGTERM exit convention và `137` thường tương ứng SIGKILL, **nhưng không thể kết luận nguyên nhân chỉ từ con số**: runtime/entrypoint/process signal handling ảnh hưởng kết quả. Xem `kubectl describe pod`, events, OOMKilled, logs và actual termination timing.

### Tránh lấy liveness làm readiness

Nếu một instance đã chuyển sang `REFUSING_TRAFFIC` để drain, đó **không** phải bug cần restart ngay lập tức. Nếu liveness probe bị cấu hình kiểm readiness và fail, kubelet có thể kill instance sớm hơn ý định. Hãy dùng các endpoints/health groups khác nhau cho mục đích riêng.

## 19. Ma trận kiểm thử tối thiểu

| Tình huống | Cách thực hiện | Kết quả cần quan sát |
|---|---|---|
| Graceful đã bật | Boot 3.3 properties + TERM | Có lifecycle graceful start/end, stop new accepts |
| Request cũ hoàn tất | Bắt đầu 8s work rồi TERM, phase 20s | Request trả 200 nếu client còn nhận, logs work-finished |
| Request mới sau TERM | Mở TCP/curl connection mới | Không xử lý work mới; Tomcat có thể refused/reset |
| Undertow behavior | App dùng Undertow và cấu hình grace | New request có thể nhận HTTP 503 |
| Immediate mode | Test riêng `server.shutdown=immediate` | Không kỳ vọng drain như graceful |
| SIGKILL | `kill -9` trong sandbox | Không có bảo đảm lifecycle cleanup |
| Grace timeout | Work > phase budget | Request có thể bị cắt, cleanup/forced close theo runtime |
| Docker stop | `docker stop -t 30` | JVM nhận stop signal và đủ thời gian drain |
| ENTRYPOINT shell sai | Shell không forward TERM | Không nhận lifecycle đúng, stop timeout bị dùng hết |
| preStop delay | preStop 5s, grace 45s | TERM sau preStop; cả hai chung budget |
| Local readiness | `/readyz` trước TERM | 200/UP khi ready |
| Probes after TERM | Cổng HTTP có thể đóng | Không bắt buộc JSON 503 từ Tomcat |
| Pod rolling update | Replicas >= 2, maxUnavailable 0 | Số error/availability đạt SLO khi rollout |
| Ingress stale route | Endpoint đang terminating | LB nhanh chóng ngừng route, đo 502/503 |
| HTTP/1.1 keep-alive | Giữ connection cũ và gửi requests | Kiểm chính xác request vs connection semantics |
| HTTP/2 streams | Multiplexed client | Không thêm streams mới ngoài policy khi drain |
| SSE/WebSocket | Stream/duplex session lâu | Bounded termination, reconnect |
| Async/background jobs | Work không do HTTP connector quản lý | Stop polling/cancel/ack/cleanup riêng |
| POST mutation | Commit trước khi response bị mất | Idempotency key chặn duplicate |
| Cleanup chậm | @PreDestroy/SmartLifecycle kéo dài | Kubernetes grace đủ; không bị SIGKILL bất ngờ |

**Quan trọng với test chủ động kill:** chỉ chạy trên local/staging test instance. Không kill production Pod để “chứng minh” nếu chưa có change window, failure budget và recovery plan. Dữ liệu nghiệm thu phải đến từ HTTP status, logs và metrics thực, không từ việc một lệnh kill trả exit code 0.

## 20. Những anti-pattern dễ gặp

| Anti-pattern | Vì sao sai | Cách đúng hơn |
|---|---|---|
| Không bật `server.shutdown=graceful` trên Boot 3.3 rồi mặc định nghĩ đã bật | Version-specific default khác tài liệu mới | Khai báo rõ property và test |
| `kill -9` để thử graceful | SIGKILL không chạy shutdown hooks | `SIGTERM` tới JVM đúng PID |
| `docker stop` timeout 3s nhưng Spring phase 20s | Container bị force kill trước khi drain | Phối hợp stop timeout/grace budget |
| Docker ENTRYPOINT shell-form không forward TERM | JVM có thể không nhận signal | Dùng exec-form ENTRYPOINT |
| Chỉ đổi readiness, không dừng accept | Direct/stale routing vẫn có thể gửi request | Kết hợp readiness và connector drain |
| Chỉ đóng server mà không rút LB | Gateway vẫn route vào instance đã đóng | Drain propagation/K8s EndpointSlice |
| Bắt buộc Tomcat trả HTTP 503 cho request mới | Server thường reject ở network layer | Assert no new work, chấp nhận refused/reset |
| Đặt preStop 30s với grace 30s | Không còn thời gian cho TERM/cleanup | PreStop là một phần của tổng grace |
| Tưởng per-shutdown-phase là total process shutdown timeout | Có thể nhiều phases | Dự trù tổng lifecycle/cleanup |
| `@PreDestroy` sleep vô hạn để “đợi request” | Không theo dõi in-flight, có thể treo | Built-in graceful + task lifecycle riêng |
| Đóng DB pool trước khi request drain | In-flight controller fail giữa transaction | Lifecycle ordering đúng dependency |
| Đóng Pod mới khi chưa ready | Rolling update gây downtime | readiness + maxUnavailable + capacity |
| Liveness kiểm DB/readiness làm restart storm | Dependency outage khiến Pods bị kill | Phân biệt health purposes |
| Tin 200 từ quản lý cổng khác thay cho app health | App port có thể hỏng riêng | /readyz trên main port khi phù hợp |
| Expose actuator shutdown public | Tạo đường DOS dừng app | Dùng orchestrator signal, secure mgmt |
| Không xử lý SSE/WebSocket riêng | Stream có thể chặn drain đến timeout | Bounded lifetime/reconnect/close |
| Chờ task 2 phút với grace 20s | Buộc SIGKILL/bỏ dở work | Async jobs, resumable/idempotent workflows |
| Coi hoàn tất controller là client chắc nhận response | Network/client có thể disconnect | Client reconciliation, idempotency |
| Chỉ test happy path | Không thấy boundary races | Process-level TERM, long requests, LB tests |

## 21. Quy trình triển khai an toàn

1. **Xác nhận phiên bản Boot/server** thật trong dependency tree và runtime; không suy ra Boot 3.3 giống Boot mới.
2. Bật `server.shutdown=graceful`, đặt `spring.lifecycle.timeout-per-shutdown-phase` dựa trên request/workload limits.
3. Thêm Actuator readiness/liveness probes đúng môi trường; dùng `/readyz` trên app port nếu health group cần kiểm thực sự port chính.
4. Vẽ route client→LB→Pod và xác định thời gian ingress/backend deregistration, keepalive/HTTP2 behavior.
5. Cấp `terminationGracePeriodSeconds` đủ cho preStop, lifecycle phases, cleanup và buffer.
6. Bảo đảm JVM nhận TERM, nhất là Docker PID 1/entrypoint và runtime signal policy.
7. Rà HTTP request timeout, DB timeout, job/stream lifetime để không có work vô hạn.
8. Rà các background executors, message listeners và scheduler với stop/ack/commit policy riêng.
9. Viết process-level integration test bắt đầu request chậm rồi TERM, kiểm in-flight completion và no-new-work.
10. Test forced kill để chứng minh durability/recovery, không kỳ vọng graceful khi SIGKILL.
11. Kiểm rolling update với replica/capacity phù hợp; đo 5xx, connection errors, p95/p99, in-flight và cleanup.
12. Áp canary/rollback; giữ metrics/alerts cho shutdown drain duration và forced termination.
13. Không expose quản trị HTTP shutdown ở public surface.
14. Tài liệu hóa owner và deadline cho từng group resource.
15. Định kỳ kiểm thử lại khi nâng Boot/container/orchestrator/gateway, vì default và network behavior có thể đổi.

### Một ví dụ time budget nhất quán

~~~text
App P95 normal request:         300 ms
Explicit HTTP request cap:      10 s
Spring graceful web phase:      20 s
Other phases + cleanup:         <=10 s
Kubernetes preStop if needed:    5 s
Kubernetes total grace:         45 s
Unallocated safety margin:      10 s
~~~

Đây là **ví dụ để tranh luận và đo đạc**, không phải cấu hình mặc định khuyên dùng cho mọi service. Nếu có request streaming dài hoặc nhiều SmartLifecycle phases, cần thay model/workload budgets. Không để một hard deadline của business operation lớn hơn cửa sổ shutdown mà lại hứa “mọi request sẽ hoàn tất”.

## 22. Câu hỏi ôn tập có đáp án

**1. Boot 3.3 có nên cấu hình `server.shutdown=graceful` rõ ràng không?**  
Có. Tài liệu Boot 3.3 chỉ cách bật bằng property này; đừng áp default của phiên bản mới hơn vào bài.

**2. `spring.lifecycle.timeout-per-shutdown-phase=20s` nghĩa toàn JVM chắc dừng sau đúng 20s?**  
Không. Đây là timeout **mỗi lifecycle shutdown phase**, có thể còn phases/destroy callbacks khác.

**3. Tomcat sẽ luôn trả HTTP 503 cho request mới sau TERM?**  
Không. Tomcat, Jetty và Reactor Netty dừng chấp nhận ở network layer; client có thể thấy connection refusal/reset. Undertow có thể trả 503.

**4. SIGTERM khác SIGKILL thế nào?**  
TERM cho JVM cơ hội đóng context/shutdown hooks; SIGKILL không cho chạy cleanup bình thường.

**5. IDE Stop có luôn tương đương SIGTERM?**  
Không. Phải kiểm IDE cụ thể; dùng process-level TERM test đáng tin hơn trên Linux/WSL.

**6. Readiness=REFUSING_TRAFFIC có đồng nghĩa JVM chết?**  
Không. App có thể còn sống xử lý request cũ trong drain; liveness vẫn CORRECT.

**7. Vì sao cần readinessProbe nếu Boot graceful đã chặn new requests?**  
Để orchestrator/LB ngừng chọn instance, tránh traffic lỗi tới listener đã đóng.

**8. Spring Boot health endpoint chắc còn trả JSON 503 trong khi listener đang shutdown?**  
Không. Khi connector đã ngừng nhận, probe HTTP có thể không kết nối được.

**9. preStop 5 giây có được cộng thêm ngoài terminationGracePeriodSeconds không?**  
Không. Countdown bắt đầu trước preStop; nó ăn vào cùng ngân sách.

**10. Chỉ `server.shutdown=graceful` có làm Kafka consumer dừng poll/ack an toàn không?**  
Không. Message listener/broker client có lifecycle, ack và retry riêng.

**11. Một `@PreDestroy` sleep(30000) có phải cơ chế drain đáng tin?**  
Không. Nó không quản lý HTTP in-flight request và có thể làm shutdown treo.

**12. Vì sao cần idempotency khi client bị ngắt giữa POST?**  
Vì server có thể đã commit nhưng response không đến client; retry có thể duplicate.

**13. Vì sao không đặt livenessProbe phụ thuộc hoàn toàn external DB chung?**  
DB outage có thể khiến mọi Pods bị restart đồng thời, tạo cascading failures.

**14. `maxUnavailable: 0` có tự bảo đảm zero downtime không?**  
Không. Cần đủ replicas/capacity, readiness chuẩn và LB propagation/traffic behavior đúng.

**15. Một SSE stream 1 giờ có thể ảnh hưởng graceful phase 20s không?**  
Có. Nếu stream không kết thúc, phase có thể hết hạn; cần bounded lifetime/reconnect/close strategy.

**16. Khi dùng Dockerfile shell-form ENTRYPOINT, rủi ro gì?**  
Signal tới shell có thể không được chuyển cho Java; process không chạy shutdown lifecycle đúng cách.

**17. Vì sao phải kiểm process-level test, không chỉ JUnit @SpringBootTest?**  
JUnit không mô phỏng đáng tin quá trình JVM nhận TERM và toàn bộ application context dừng khi HTTP request còn chạy.

**18. Có thể dùng HTTP /actuator/shutdown công khai để Kubernetes dừng Pod không?**  
Không nên; endpoint disabled by default, public shutdown tạo attack surface lớn. Ưu tiên TERM/orchestrator.

**19. Khi in-flight request đã hoàn thành nhưng client bị disconnect, đã chắc user nhận response chưa?**  
Chưa. Network có thể hỏng sau commit; cần operation-status query/idempotency.

**20. Nếu Spring graceful phase 20s nhưng Kubernetes grace chỉ 10s, chuyện gì xảy ra?**  
Kubernetes có thể force terminate process trước khi phase drain hoàn tất. Phải phối hợp budgets.

## 23. Tài liệu chính thức và đọc thêm

- [Spring Boot 3.3 – Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): cấu hình `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase` và hành vi từng embedded server.
- [Spring Boot 3.3 – Actuator Endpoints / Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): liveness, readiness, `/readyz`, application availability trong startup/shutdown.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): health probes và shutdown properties.
- [Spring Framework – Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `SmartLifecycle`, getPhase, stop callback và @PreDestroy.
- [Spring Framework – Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): application context và event lifecycle.
- [Spring Boot – Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): readiness/liveness availability states.
- [Kubernetes – Pod Lifecycle / Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): terminationGracePeriodSeconds, SIGTERM/SIGKILL, EndpointSlice terminating readiness.
- [Kubernetes – Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): preStop timing và container stop.
- [Kubernetes – Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): health probe configuration.
- [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): endpoint conditions và traffic routing.
- [Docker – Stop Containers](https://docs.docker.com/reference/cli/docker/container/stop/): `docker stop` và stop timeout.
- [Docker – Dockerfile ENTRYPOINT](https://docs.docker.com/reference/dockerfile/#entrypoint): exec form, PID 1, signal forwarding.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP 503 semantics.
- [Spring Boot 3.3 – Production-ready features](https://docs.spring.io/spring-boot/3.3/reference/actuator/index.html): metrics, health endpoints và operational concerns.

**Kết luận:** Để dừng HTTP service an toàn, hãy **chủ động bật graceful shutdown trên Spring Boot 3.3**, cho application một khoảng thời gian drain hữu hạn, phối hợp readiness/traffic deregistration và Kubernetes/Docker stop budget, quan sát request đang chạy, và thiết kế recovery cho những tình huống không thể graceful. “Không tiếp nhận request mới” phải được bảo đảm cả ở **connector** lẫn **hạ tầng định tuyến**, trong khi in-flight, background jobs và transactions có lifecycle riêng.
