# Phối hợp readiness, gỡ khỏi cân bằng tải và tín hiệu SIGTERM

## 1. Vấn đề: ứng dụng phải ngừng nhận request mới trước khi rời hệ thống

Trong chủ đề **Dừng có kiểm soát** của **Spring Boot - web-runtime**, việc dừng một instance không nên đơn giản là “kill tiến trình rồi cho instance khác phục vụ”. Với một service sau load balancer, có thể đang có request xử lý dở, connections keep-alive, transaction chưa commit, SSE/WebSocket chưa kết thúc, scheduled jobs và background consumers.

Mục tiêu của **graceful shutdown** là:
1. Cho hệ thống điều phối biết instance **không còn nên nhận request mới**.
2. Cho load balancer/Service/Ingress **thời gian ngừng chọn endpoint cũ**.
3. Gửi **SIGTERM** để tiến trình JVM chủ động đóng ApplicationContext.
4. Để Spring Boot và HTTP server **ngừng nhận request mới và chờ các request đang chạy hoàn tất trong giới hạn**.
5. Dọn các tác vụ và kết nối còn lại theo shutdown policy.
6. Thoát trước khi runtime hết thời hạn và dùng SIGKILL.
7. Đảm bảo các replicas mới đã **ready** và vẫn còn đủ capacity trước, trong và sau rollout.

**Ba khái niệm cần tách bạch:**
- **Readiness** là tín hiệu “có nên đưa traffic mới tới instance này không?”
- **Deregistration/connection draining** là thay đổi lựa chọn endpoint của tầng load balancing và để connections cũ có cơ hội kết thúc.
- **SIGTERM + graceful shutdown** là tín hiệu/chính sách dừng tiến trình, ngăn server nhận request mới và cho các request đang xử lý thời gian hoàn tất.

Chỉ một cơ chế không thay thế được toàn bộ. Đổi readiness sang false **không tự giết JVM**, còn gửi SIGTERM quá sớm có thể làm load balancer tiếp tục trỏ requests vào một endpoint không còn nhận kết nối.

**Phạm vi:** Spring Boot **3.3.13**, Java **17+**, Spring MVC/embedded Tomcat và Kubernetes Pod lifecycle. Spring Boot 3.3 yêu cầu bật **server.shutdown=graceful**; đừng nhầm với mặc định của một số phiên bản Spring Boot mới hơn. Các con số timeout trong ví dụ **chỉ dành cho lab** và phải được kiểm bằng điều kiện triển khai thực.

## 2. Mô hình tổng quát và ranh giới trách nhiệm

~~~text
Client
  |
  v
DNS / external Load Balancer / Ingress
  |
  v
Kubernetes Service / EndpointSlice routing
  |
  +--------------+-------------------+
  |              |                   |
  v              v                   v
Pod A          Pod B               Pod C
Ready          Ready               Ready
  |              |                   |
  |      Rolling update: B terminating
  |              |
  |              +--> EndpointSlice terminating=true
  |              |                  ready=false
  |              +--> Routing update propagates asynchronously
  |              +--> Optional preStop hook completes
  |              +--> Kubelet sends TERM to container process
  |              +--> Spring context closes
  |              +--> Embedded web server drains in-flight requests
  |              +--> JVM exits
  |              |
  |              +--> SIGKILL if termination grace expires
  |
  +--> New requests should go to remaining ready endpoints
~~~

**Đây là mô hình mục tiêu, không phải một chuỗi bảo đảm tuyệt đối về thời gian.** Kubernetes cập nhật EndpointSlice và kubelet thực hiện shutdown là các nhánh diễn ra đồng thời; load balancer, Ingress và clients có thể có cache/connection pooling. Khi Pod được đánh dấu terminating, EndpointSlice **ready=false**, nhưng các thành phần routing vẫn cần nhận và áp dụng thay đổi.

Đừng nhầm **Kubernetes Service** (routing) với **Spring Boot readiness probe** (báo trạng thái) hoặc với **Servlet connector** (socket đang nhận HTTP). Cả ba thuộc những phạm vi kiểm soát khác nhau.

## 3. Readiness, liveness và startup probe phục vụ mục tiêu khác nhau

| Cơ chế | Câu hỏi | Khi thất bại thường dẫn tới |
| --- | --- | --- |
| Readiness probe | Instance có thể nhận traffic mới chưa? | Pod bị loại khỏi tập endpoints sẵn sàng phục vụ traffic thông thường |
| Liveness probe | Tiến trình/app có bị kẹt hỏng và cần restart không? | Kubelet có thể restart container theo policy |
| Startup probe | App đã vượt giai đoạn khởi động chậm chưa? | Tạm bảo vệ liveness/readiness khỏi đánh giá quá sớm theo cấu hình |
| Kubernetes terminating state | Pod đang bị xóa/dừng? | EndpointSlice có terminating=true, ready=false |
| Load balancer deregistration | Routing có ngừng chọn endpoint? | New traffic chuyển sang endpoints khác khi thông tin đã cập nhật |
| Graceful shutdown của Spring Boot | Request hiện tại có được chờ hoàn tất? | Server ngừng nhận mới, drain trong thời hạn |
| SIGTERM | Tiến trình được yêu cầu kết thúc? | JVM shutdown hook được chạy nếu nhận tín hiệu và runtime cho phép |
| SIGKILL | Buộc dừng ngay? | Không chạy Java shutdown hooks; tác vụ dở có thể mất |

**Readiness false không giống liveness broken.** Khi cố ý drain một Pod đang khỏe, chỉ nên báo “không tiếp nhận traffic mới”, không biến liveness thành lỗi để kubelet khởi động lại không cần thiết.

**Startup probe** hữu ích khi app warm up, chạy migrations hoặc dựng cache lâu. Khi chưa ready, app có thể lắng nghe port nhưng không đủ điều kiện phục vụ nghiệp vụ. Khi đã ready, readiness probe mới dẫn traffic vào instance.

### 3.1. Spring Boot availability states

Spring Boot cung cấp:
- **LivenessState.CORRECT** / **BROKEN**.
- **ReadinessState.ACCEPTING_TRAFFIC** / **REFUSING_TRAFFIC**.
- **ApplicationAvailability** để đọc trạng thái.
- **AvailabilityChangeEvent** để công bố trạng thái khi ứng dụng có cơ chế kiểm soát.

Trong vòng đời khởi động: trước khi app hoàn tất startup/runners, readiness thường **REFUSING_TRAFFIC**; khi app sẵn sàng, nó thành **ACCEPTING_TRAFFIC**. Trong graceful shutdown, Spring Boot 3.3 ghi trạng thái **REFUSING_TRAFFIC** nội bộ. Tuy nhiên, ở thời điểm shutdown HTTP connector đã bắt đầu ngừng nhận request mới, **external readiness endpoint có thể không còn truy cập được**. Đây là lý do không nên coi readiness response lúc shutdown là một API có thể luôn gọi được.

### 3.2. Tại sao không phụ thuộc database cho liveness?

Nếu database chung bị chậm, cả 10 Pod cùng đặt liveness phụ thuộc DB có thể đồng loạt bị restart, làm sự cố nặng hơn. Liveness nên phản ánh khả năng sống của chính ứng dụng. Với readiness, cân nhắc external dependency có thực sự thiết yếu và có thể hỏng cục bộ hay không; việc đưa shared dependency vào readiness của mọi Pod cũng có thể khiến Service mất toàn bộ endpoints.

Theo Spring Boot, readiness/liveness health groups mặc định không tự thêm mọi external HealthIndicator vào. Chỉ bổ sung nếu đã xác định rõ tác động.

## 4. Spring Boot Actuator readiness probe đúng cách

Spring Boot 3.3 với **spring-boot-starter-actuator** có các health groups:
- **/actuator/health/liveness**
- **/actuator/health/readiness**

Trong Kubernetes, probes có thể được tự bật khi Spring Boot phát hiện môi trường Kubernetes. Để chạy local nhất quán và không dựa môi trường, khai báo tường minh:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

**management.endpoint.health.probes.add-additional-paths=true** cũng ánh xạ:
- **/livez** trên **cổng HTTP ứng dụng**.
- **/readyz** trên **cổng HTTP ứng dụng**.

Điều này đặc biệt hữu ích nếu bạn chạy Actuator ở một **management.server.port khác**, vì health endpoint ở cổng management có thể vẫn sống trong khi cổng application không tiếp nhận request. Probe trên **cổng ứng dụng thực** giúp kiểm cả đường HTTP đang phục vụ traffic.

Khi ready, response JSON của health endpoint thường thể hiện **status UP** với HTTP 200. Khi readiness từ chối, health status có thể là **OUT_OF_SERVICE** và thường ánh xạ HTTP 503 theo mặc định. Trong lúc HTTP connector đóng, client có thể thấy **connection refused/EOF** thay vì JSON 503; không hứa status cố định ở giai đoạn shutdown.

### 4.1. Cấu hình Actuator bảo mật

Mặc định Spring Boot chỉ expose health endpoint qua HTTP. Không cần expose các endpoints nhạy cảm như env, beans, heapdump hoặc shutdown chỉ để Kubernetes probe.

Nếu có Spring Security custom SecurityFilterChain, phải bảo đảm **/readyz** và **/livez** được phép truy cập bởi kubelet/ingress đúng cách theo network policy, trong khi endpoints khác vẫn được bảo vệ. Đừng tạo đường quản trị công khai cho phép client bất kỳ đánh dấu app unready hoặc tắt server.

## 5. Graceful shutdown của Spring Boot 3.3

### 5.1. Bật graceful shutdown tường minh

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

**server.shutdown=graceful**: kích hoạt graceful shutdown của embedded web server. Với Spring Boot 3.3, cần cấu hình tường minh thay vì giả định mặc định giống các bản mới.

**spring.lifecycle.timeout-per-shutdown-phase=30s**: giới hạn thời gian chờ **mỗi phase** trong quá trình stop các SmartLifecycle beans. Graceful shutdown của web server diễn ra ở giai đoạn sớm của quá trình stop. Đây **không phải giới hạn tổng thời gian JVM shutdown đúng 30 giây trong mọi điều kiện**; nhiều phases, destroy callbacks hoặc dependencies có thể tiêu tốn thêm thời gian.

Theo Spring Boot 3.3, graceful shutdown được hỗ trợ với Tomcat, Jetty, Reactor Netty và Undertow. Cách không nhận request mới khác nhau:
- **Tomcat, Jetty và Reactor Netty**: ngừng nhận request mới ở network layer.
- **Undertow**: có thể nhận connection mới rồi trả **503 Service Unavailable**.

Do đó **không tuyên bố rằng mọi server trả HTTP 503 ngay sau SIGTERM**. Trên Tomcat, request mới có thể gặp connection refused hoặc network error. Keep-alive, HTTP/2 và các request đã đi vào server trước lúc bắt đầu shutdown khiến quan sát thực tế phức tạp hơn.

### 5.2. Những gì graceful shutdown bảo vệ

- Cho các **HTTP requests đang được xử lý** hoàn tất trong khoảng thời gian cho phép.
- Chặn nhận HTTP requests mới khi cơ chế shutdown kích hoạt.
- Hạn chế số lần reset kết nối không cần thiết nếu request đủ ngắn.
- Phối hợp với ApplicationContext lifecycle để các bean được stop/destroy.

**Không bảo đảm**:
- Mọi transaction và background tasks hoàn thành nếu thời gian vượt hạn.
- Task đã rời request thread, job queue bên ngoài hoặc consumer Kafka/JMS được drain đúng chỉ nhờ server.shutdown.
- Long-lived WebSocket/SSE connections có thể duy trì mãi mà không ảnh hưởng shutdown.
- SIGKILL cho phép @PreDestroy chạy.
- Tất cả reverse proxies đã ngừng gửi traffic ngay khi app nhận SIGTERM.

Muốn dừng jobs/consumers, phải dùng shutdown logic riêng, SmartLifecycle hoặc cơ chế của integration với ngân sách thời gian phù hợp.

## 6. Thứ tự phối hợp: drain traffic trước, TERM sau, kill cuối cùng

Timeline khái niệm:

~~~text
t0                  t1                 t2                 t3
|-------------------|------------------|------------------|
Deployment update   Endpoint changed   SIGTERM delivered  JVM exit
Pod terminating     ready=false        to process 1       when done
    |                  |                    |
    +--> Control plane updates EndpointSlice |
    +--> Endpoint routing changes propagate  |
    +--> preStop can delay TERM              |
                                            +--> Spring readiness REFUSING_TRAFFIC
                                            +--> Web server refuses new requests
                                            +--> In-flight requests finish
                                            +--> Beans/resources stop
    |
    +------------- terminationGracePeriodSeconds ------------+
                                                             |
                                                             +--> SIGKILL if process still alive
~~~

**Điểm then chốt:** timer **terminationGracePeriodSeconds** bắt đầu khi Pod được yêu cầu kết thúc, **không bắt đầu sau khi preStop đã sleep xong**. preStop tốn thời gian trong cùng ngân sách. Phần còn lại phải đủ để JVM thực hiện graceful shutdown và cleanup.

Đồng thời, endpoint termination propagation là bất đồng bộ. Việc Kubernetes điều khiển EndpointSlice không đồng nghĩa external Load Balancer, Ingress hoặc client connection pool sẽ biết ngay lập tức. Vì vậy một khoảng **drain delay** có thể hữu ích tùy môi trường, nhưng phải được đo, không chọn tùy tiện.

### 6.1. preStop chạy trước SIGTERM

Trong Linux container thông thường, khi Pod terminating:
1. Kubelet bắt đầu graceful termination countdown.
2. Nếu có lifecycle **preStop** và grace period khác 0, kubelet chạy hook.
3. Khi hook kết thúc, kubelet yêu cầu container runtime gửi **SIGTERM** (hoặc stop signal được chọn) tới process 1.
4. Runtime chờ process dừng tới khi hết grace period.
5. Nếu container còn chạy khi hết hạn, runtime gửi **SIGKILL**.

Đây là thứ tự của **kubelet tại node**, trong khi EndpointSlice update/proxy propagation có thể diễn ra đồng thời ở control plane.

### 6.2. preStop sleep có tác dụng gì và không có tác dụng gì?

Ví dụ hook:

~~~yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 8"]
~~~

Trong 8 giây này:
- Process Java **chưa nhận SIGTERM từ nhánh shutdown thông thường**, nên còn có thể phục vụ request cũ.
- Pod đã được đánh dấu terminating và EndpointSlice thường phản ánh **ready=false**, giúp routing thôi chọn endpoint cho request thông thường.
- Các proxies còn cập nhật chậm có thời gian áp dụng trạng thái mới.

Nhưng:
- Đây **không phải xác nhận load balancer đã drain xong**.
- External LB có thể giữ routing/keep-alive lâu hơn 8 giây.
- Nếu image không có **/bin/sh** hoặc lệnh sleep, hook sẽ lỗi.
- Sleep quá dài ăn mất thời gian graceful shutdown thật.
- App readiness nội bộ có thể còn ACCEPTING_TRAFFIC trong lúc sleep nếu chưa có cơ chế đặt unready riêng.

**preStop sleep là một công cụ phối hợp có điều kiện, không phải điều kiện bắt buộc cho mọi cluster hoặc cách chữa mọi reset.**

### 6.3. Đánh dấu unready chủ động trước TERM

Nếu hệ thống có kênh điều phối **được xác thực và giới hạn mạng**, có thể công bố readiness false trước khi thực sự tắt server:

~~~java
// Fragment: method được gọi từ một trusted internal control flow.
// Cần import ApplicationContext, AvailabilityChangeEvent và ReadinessState.
void beginDrain(ApplicationContext context) {
    AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC
    );
}
~~~

Đây là **fragment**, không phải REST endpoint công khai hay chương trình Java độc lập. Khi readiness đã chuyển false nhưng HTTP connector còn mở, external probe có thể quan sát **/readyz** là unready trước lúc SIGTERM. Hệ thống có thể chờ đủ propagation rồi mới yêu cầu shutdown.

**Quan trọng:** readiness false **chỉ là tín hiệu cho routing**, không tự ngừng phục vụ direct requests. Nếu một client gọi Pod IP hoặc giữ kết nối cũ, request vẫn có thể đi vào app khi chưa gọi shutdown. Phải kết hợp admission policy nếu cần từ chối request mới ngay lập tức.

Không tạo public **POST /drain** không có authentication; attacker có thể khiến toàn bộ instances tự loại khỏi Service. Ngoài Kubernetes, việc set unready trước và deregister ở load balancer cụ thể phải dùng API/control plane của LB, không suy luận chỉ từ Spring event.

## 7. Kubernetes EndpointSlice: ready=false khác bị xóa ngay

Trong các phiên bản Kubernetes hiện đại, endpoint đại diện cho Pod terminating có thể **vẫn còn trong EndpointSlice** trong giai đoạn drain, với các conditions:

~~~yaml
conditions:
  ready: false
  serving: true
  terminating: true
~~~

Đây là một **ví dụ trạng thái có thể quan sát**. Với Pod terminating:
- **terminating=true**: Pod đang kết thúc.
- **ready=false** được thiết lập để các clients/load balancers thông thường không dùng endpoint đó cho new traffic.
- **serving** cung cấp thêm thông tin có thể dùng cho drain; không phải mọi consumer đều xử lý điều kiện này giống nhau.

Không nhầm **EndpointSlice ready=false** với **Spring Boot AvailabilityState REFUSING_TRAFFIC**: chúng có thể xảy ra tại thời điểm khác nhau. Một Pod có thể đang terminating và bị gỡ khỏi routing **ngay khi app chưa nhận SIGTERM**.

Không tuyên bố endpoint “được xóa ngay lập tức” khi Pod bắt đầu terminating. Kubernetes có thể giữ record với terminating=true để hỗ trợ connection draining. Khi Pod kết thúc, record cuối cùng sẽ được loại khỏi Service endpoint set.

### 7.1. External load balancer có thể cần deregistration riêng

Ví dụ một Kubernetes Service ở sau Ingress/NGINX/Envoy hoặc external cloud load balancer. Các thành phần khác nhau có thể:
- Watch EndpointSlices trực tiếp hoặc gián tiếp.
- Cache upstream endpoints.
- Duy trì keep-alive connections tới Pod.
- Áp connection-draining timeout riêng.
- Bắt đầu retry tới endpoint khác khi upstream đóng.

**Không có một khoảng sleep cố định bảo đảm đúng cho mọi LB**. Quan sát upstream resets, 5xx của ingress, thời điểm endpoint thay đổi và thời gian request đang chạy để chọn preStop/termination grace.

Nếu dùng external LB quản lý target groups không đồng bộ với Kubernetes Service, cần kiểm cả deregistration delay của nhà cung cấp, không chỉ Pod readiness probe.

## 8. Ngân sách thời gian khi dừng: tính từ toàn bộ chuỗi

Ví dụ thiết kế ban đầu:

| Khoảng | Thời lượng minh họa | Ý nghĩa |
| --- | --- | --- |
| Kubernetes termination grace | **55 giây** | Toàn bộ ngân sách trước SIGKILL |
| preStop drain delay | **8 giây** | Chờ routing propagation, trước SIGTERM |
| Spring lifecycle phase timeout | **30 giây/phase** | Giới hạn chờ từng SmartLifecycle phase, gồm graceful web server phase |
| Dự phòng | **17 giây** nếu chỉ một phase 30 giây | Cho phases khác, cleanup, scheduling jitter |

Tính minh họa: **55 = 8 + 30 + 17**. Nhưng **không** được kết luận JVM chắc chắn thoát trong 38 giây: spring.lifecycle.timeout-per-shutdown-phase là giới hạn **mỗi phase**, có thể có nhiều phases, bean destruction và external operations. Cần đo shutdown wall-clock thực tế, rồi tăng termination grace hoặc tối ưu shutdown.

### 8.1. Quy tắc sizing

- Termination grace phải đủ cho **preStop + graceful in-flight time + các shutdown phases + cleanup + margin**.
- Timeout của request bình thường và gateway phải phù hợp với thời gian còn lại.
- Nếu phần việc dài hơn ngân sách, thiết kế trả **202 Accepted + durable job ID** hoặc checkpoint/requeue thay vì giữ một HTTP request vô hạn.
- Không tăng preStop sleep vô hạn để che mất lỗi shutdown quá chậm.
- Nếu app có nhiều containers/sidecars, cần kiểm thứ tự shutdown và thời hạn toàn Pod.
- Khi muốn giảm downtime, kết hợp rolling update **maxUnavailable, maxSurge, PodDisruptionBudget, capacity** chứ không chỉ tăng terminationGracePeriodSeconds.

### 8.2. Nếu SIGKILL xảy ra

SIGKILL không thể được JVM bắt để chạy shutdown hook. Những công việc đang xử lý có thể bị cắt dở:
- DB transaction có thể rollback theo connection close, nhưng phải kiểm trạng thái thực.
- Remote API side effect có thể đã xảy ra dù response chưa gửi.
- Message đã nhận nhưng chưa ack có thể được redeliver.
- File đang ghi dở có thể còn lại nếu không có atomic rename/checkpoint.

Vì vậy graceful shutdown là một lớp giảm rủi ro, **không thay idempotency, transaction boundaries và durable work queue**.

## 9. Lab chạy được: Spring Boot MVC với readiness và request chậm

Lab này chứng minh:
1. Khi app ready, **/readyz** và **/livez** trả kết quả healthy.
2. Một HTTP request đang chạy trong Controller có thể hoàn tất khi JVM nhận SIGTERM nếu grace đủ.
3. Spring Boot dừng nhận requests mới trong graceful shutdown.
4. Khi app đã dừng, health probe ở port ứng dụng không còn trả response.
5. Docker exec-form ENTRYPOINT giúp signal đến đúng process Java.

### 9.1. Cây dự án

~~~text
graceful-demo/
├── pom.xml
├── Dockerfile
├── k8s.yaml
└── src/
    ├── main/
    │   ├── java/com/example/graceful/GracefulDemoApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/graceful/ProbeIntegrationTest.java
~~~

Các tệp Dockerfile, k8s.yaml được mô tả bên dưới; chúng dùng cùng project nhưng chỉ cần Maven/Java để thử SIGTERM tại máy local.

### 9.2. pom.xml đầy đủ

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

    <groupId>com.example</groupId>
    <artifactId>graceful-demo</artifactId>
    <version>1.0.0</version>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
~~~

### 9.3. application.yml

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
  endpoints:
    web:
      exposure:
        include: health
~~~

- **server.shutdown: graceful**: cần trong Spring Boot 3.3 để bật xử lý request đang chạy khi dừng.
- **timeout-per-shutdown-phase: 30s**: đủ cho request lab dài tối đa 15 giây trong phase web server, chưa tính overhead.
- **probes.enabled**: tạo liveness/readiness health groups cả khi chạy local.
- **probes.add-additional-paths**: cho phép **/readyz** và **/livez** trên port 8080.
- **exposure.include: health**: không expose các Actuator endpoints nhạy cảm không cần thiết.

Không đặt **management.server.port** khác trong lab, để probes kiểm đúng web server.

### 9.4. Java source đầy đủ

**src/main/java/com/example/graceful/GracefulDemoApplication.java:**

~~~java
package com.example.graceful;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class GracefulDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(GracefulDemoApplication.class, args);
    }
}

@RestController
class DemoController {
    private final ApplicationAvailability availability;
    private final AtomicInteger inFlight = new AtomicInteger();

    DemoController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/api/slow")
    Map<String, Object> slow(
            @RequestParam(defaultValue = "5000") long ms
    ) throws InterruptedException {
        if (ms < 0 || ms > 15000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "ms must be 0..15000"
            );
        }

        inFlight.incrementAndGet();
        try {
            // Mô phỏng công việc blocking đang thực thi trên Servlet worker.
            Thread.sleep(ms);
            return Map.of(
                    "status", "completed",
                    "requestedMs", ms
            );
        } finally {
            inFlight.decrementAndGet();
        }
    }

    @GetMapping("/api/state")
    Map<String, Object> state() {
        return Map.of(
                "readiness", String.valueOf(
                        availability.getReadinessState()
                ),
                "liveness", String.valueOf(
                        availability.getLivenessState()
                ),
                "inFlight", inFlight.get()
        );
    }
}
~~~

**Giải thích mã:**
- **@SpringBootApplication** bật Spring Boot auto-configuration, Tomcat và Actuator.
- **ApplicationAvailability** cho phép đọc trạng thái readiness/liveness hiện tại.
- **/api/slow?ms=5000** tạo request đồng bộ giữ Servlet worker khoảng 5 giây rồi trả JSON. Thread.sleep chỉ là demo, không phải việc cần làm trong code production.
- **ms < 0 hoặc > 15000** trả HTTP 400 có chủ đích để không dùng lab như một endpoint tạo công việc vô hạn.
- **AtomicInteger inFlight** đếm số requests đang trong method slow; không đếm mọi request khác, sockets, async tasks hay requests ở các replicas khác.
- **/api/state** in trạng thái Spring Boot và số slow requests đang chạy, dùng để quan sát trước SIGTERM.
- Java 17 hỗ trợ toàn bộ APIs. Một file chứa public GracefulDemoApplication và package-private DemoController hợp lệ.

Khi graceful stop, Spring Boot đóng ApplicationContext và Tomcat chờ in-flight requests theo timeout. **Không nên mong /api/state vẫn truy cập được sau khi connector ngừng nhận HTTP requests**, dù readiness nội bộ đã chuyển REFUSING_TRAFFIC.

### 9.5. Integration test của probes

**src/test/java/com/example/graceful/ProbeIntegrationTest.java:**

~~~java
package com.example.graceful;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ProbeIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void probesAreAvailableOnMainPort() {
        assertEquals(
                HttpStatus.OK,
                http.getForEntity("/livez", String.class).getStatusCode()
        );
        assertEquals(
                HttpStatus.OK,
                http.getForEntity("/readyz", String.class).getStatusCode()
        );
    }
}
~~~

Đây là integration test có real embedded web server trên **random port**, xác nhận hai probes trả HTTP 200 khi app đã sẵn sàng. Nó **không** tự chứng minh SIGTERM graceful shutdown vì bài test vẫn chạy trong cùng JVM. Phần thử signal bên dưới cần tiến trình riêng.

### 9.6. Build và chạy local

Yêu cầu Java 17+, Maven và cổng 8080 còn trống:

~~~bash
mvn test
mvn package
java -jar target/graceful-demo-1.0.0.jar
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -s http://localhost:8080/api/state
curl -s "http://localhost:8080/api/slow?ms=1000"
~~~

Khi app đã khởi động thành công, probes thường trả **HTTP 200** và JSON health với **status UP**. /api/state trả readiness **ACCEPTING_TRAFFIC**, liveness **CORRECT**, inFlight có thể là 0 khi không có request slow; đây là snapshot nên số thay đổi theo thời điểm.

Với request slow đơn lẻ thành công, JSON có các giá trị:

~~~json
{"requestedMs":1000,"status":"completed"}
~~~

Thứ tự keys của Map không được Java Map.of bảo đảm; minh họa chỉ khẳng định hai trường và giá trị. Lệnh curl -i có thêm headers trong stdout.

### 9.7. Thử SIGTERM cùng request đang xử lý (Linux/macOS)

Chạy trong thư mục project, không để ứng dụng khác dùng port 8080:

~~~bash
java -jar target/graceful-demo-1.0.0.jar > demo.log 2>&1 &
APP_PID=$!

# Chờ ready trước khi gửi request; cần curl.
until curl -fsS http://localhost:8080/readyz > /dev/null; do
  sleep 1
done

curl -sS "http://localhost:8080/api/slow?ms=5000" > slow.json &
REQUEST_PID=$!

# Đợi một chút để request đã vào Controller.
sleep 1

# Gửi TERM tới tiến trình java, không dùng kill -9.
kill -TERM "$APP_PID"

wait "$REQUEST_PID"
cat slow.json
wait "$APP_PID"
~~~

Khi request đã thật sự vào Controller trước SIGTERM và timeout đủ, **slow.json** dự kiến chứa JSON với **status completed** và **requestedMs 5000**; JVM có thể thoát ngay sau khi công việc đang thực thi hoàn thành và các beans stop. Nếu shell load/scheduling thay đổi khiến request chưa vào Controller ở thời điểm TERM, curl có thể thất bại — đây là kiểm thử tương tác, không phải một phép thử định thời tất định.

Mở demo.log để kiểm các dòng graceful shutdown tương ứng với runtime phiên bản hiện tại; không dựa vào một chuỗi log cố định như hợp đồng API.

**Không dùng kill -9** để kiểm graceful shutdown: SIGKILL không chạy shutdown hooks. Trên Windows, cách dừng từ IDE hoặc một số lệnh kill process có thể không giống SIGTERM của Linux; có thể kiểm thử trong Docker Linux để tái hiện semantics.

### 9.8. Kết quả kỳ vọng và giới hạn

| Tình huống | Kỳ vọng hợp lý |
| --- | --- |
| /readyz khi app running/ready | HTTP 200, status UP |
| /api/slow?ms=1000 bình thường | HTTP 200, JSON completed |
| SIGTERM sau khi /api/slow 5 giây đã bắt đầu | Request có cơ hội hoàn tất trong grace 30 giây |
| Request mới sau Tomcat bắt đầu graceful stop | Không được nhận mới; client có thể gặp network error |
| /readyz khi HTTP connector đã đóng | Có thể không còn kết nối được; không bắt buộc trả JSON 503 |
| SIGKILL hoặc timeout termination quá ngắn | In-flight request có thể bị cắt |
| SIGTERM gửi tới shell wrapper không forward signal | JVM có thể không chạy shutdown hook đúng lúc |

**Không khẳng định zero-downtime chỉ dựa vào demo một instance.** Zero-downtime rolling update cần replicas khác đang ready, không bị saturation và load balancer routing đã cập nhật.

## 10. Docker: signal phải đến đúng JVM

Tệp **Dockerfile** ở root project:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/graceful-demo-1.0.0.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**JSON exec-form ENTRYPOINT** giúp process Java làm PID 1 trong container, nhận stop signal do container runtime gửi. Tránh shell-form:

~~~dockerfile
# KHÔNG NÊN dùng nếu shell không exec/forward TERM đúng:
ENTRYPOINT java -jar /app/app.jar
~~~

Shell wrapper có thể trở thành PID 1 và không forward SIGTERM như mong muốn. Nếu bắt buộc dùng start script, dòng cuối nên **exec java -jar ...** và cần hiểu tín hiệu, PID 1 signal handling, zombie reaping hoặc init process.

Build/run:

~~~bash
mvn package
docker build -t graceful-demo:1.0.0 .
docker run --rm --name graceful-demo -p 8080:8080 graceful-demo:1.0.0
~~~

Ở terminal khác, khi server ready:

~~~bash
curl -s http://localhost:8080/readyz
curl -s "http://localhost:8080/api/slow?ms=5000" &
sleep 1
docker stop --time 50 graceful-demo
wait
~~~

**docker stop --time 50** gửi stop signal tới PID 1 rồi chờ tối đa 50 giây trước khi buộc kill theo Docker semantics. Nó **không mô phỏng Kubernetes EndpointSlice deregistration**; chỉ kiểm tra signal/shutdown của JVM và khả năng request hoàn tất.

Nếu dùng distroless image, có thể không có **/bin/sh** hoặc lệnh sleep, nên Kubernetes preStop dạng exec sleep cần điều chỉnh. Exec-form Java có thể dùng với image không có shell; đừng để một preStop hook phụ thuộc tool không tồn tại.

## 11. Kubernetes Deployment và Service đầy đủ cho lab

Để minh họa readiness, Pod termination và Service endpoints, tạo tệp **k8s.yaml**. Image **graceful-demo:1.0.0** phải được đưa vào cluster trước, ví dụ **kind load docker-image graceful-demo:1.0.0** nếu sử dụng kind. Với cluster khác, thay bằng image được publish tới registry của tổ chức theo quy trình triển khai.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graceful-demo
spec:
  replicas: 3
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
      terminationGracePeriodSeconds: 55
      containers:
        - name: web
          image: graceful-demo:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 1
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 1
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 30
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 8"]
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: graceful-demo
spec:
  selector:
    app: graceful-demo
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

**Cách đọc manifest:**
- **replicas: 3**: có các instances khác trong thời gian rollout; không cam kết đủ capacity nếu tải vượt năng lực còn lại.
- **maxSurge: 1, maxUnavailable: 0**: cấu hình rolling update ưu tiên giữ available replicas theo Kubernetes Deployment semantics. Để thật sự không gián đoạn, vẫn cần đủ CPU/memory, lịch trình rollout và probes chuẩn.
- **readinessProbe /readyz**: Kubernetes chọn Pod cho traffic khi probe báo ready. Sau khi Pod terminating, EndpointSlice ready=false theo termination semantics.
- **livenessProbe /livez**: kiểm tình trạng sống; không flip liveness thành broken chỉ để drain.
- **startupProbe /livez**: cho app khoảng thời gian startup trước khi liveness/readiness có hiệu lực theo probe policy. Không cần ở mọi ứng dụng, nhưng hữu ích khi startup chậm.
- **preStop sleep 8**: kéo dài thời gian Pod còn chạy trước TERM để route update lan truyền.
- **terminationGracePeriodSeconds 55**: ngân sách toàn Pod, bao gồm preStop, thời gian sau TERM và cleanup.
- **resources**: chỉ là ví dụ lab, phải đo heap/CPU thực tế.
- **Service ClusterIP**: route tới tập endpoints đang hợp lệ; thử từ trong cluster hoặc port-forward phù hợp.

### 11.1. Thực hành với kind

Nếu bạn đã có **kind**, **kubectl**, Docker và cluster đang chạy:

~~~bash
docker build -t graceful-demo:1.0.0 .
kind load docker-image graceful-demo:1.0.0
kubectl apply -f k8s.yaml
kubectl rollout status deployment/graceful-demo
kubectl get pods -l app=graceful-demo
kubectl get endpointslices -l kubernetes.io/service-name=graceful-demo
~~~

Nếu chưa có kind cluster, cần tạo cluster bằng quy trình riêng trước khi chạy. Không dùng **kubectl delete --force --grace-period=0** để test graceful shutdown vì nó bỏ qua mục tiêu kiểm thử.

Khi rollout lại:

~~~bash
kubectl rollout restart deployment/graceful-demo
kubectl rollout status deployment/graceful-demo
kubectl get pods -l app=graceful-demo
kubectl get endpointslices -l kubernetes.io/service-name=graceful-demo
~~~

Để xem trạng thái đang chuyển, mở thêm terminal chạy **kubectl get pods -l app=graceful-demo -w** và đọc EndpointSlice bằng lệnh get -o yaml trong một khoảng ngắn. Do quá trình terminating có thể kết thúc nhanh, không phải lần kiểm nào cũng bắt gặp trạng thái trung gian; xem Kubernetes events/logs nếu cần.

### 11.2. Không giả định preStop là “từ chối traffic”

Trong 8 giây sleep, Java app vẫn chạy và có thể đang báo ACCEPTING_TRAFFIC nội bộ. **Pod termination metadata** làm EndpointSlice ready=false, giúp các thành phần routing đúng chuẩn thôi chọn nó. Nhưng một proxy cập nhật chậm hoặc client dùng địa chỉ Pod trực tiếp có thể vẫn gửi request vào container.

Nếu yêu cầu nghiêm ngặt, dùng quy trình drain chủ động và authenticated **trước SIGTERM**, hoặc tích hợp LB provider-specific deregistration, chờ propagation được quan sát, rồi kết thúc. Không expose một endpoint public cho người dùng bất kỳ tự gọi shutdown/drain.

### 11.3. Phân biệt Pod Ready và Available trong rollout

Deployment có thể đánh giá replica availability theo readiness và **minReadySeconds** nếu cấu hình; một Pod mới đã khởi động process nhưng chưa ready thì chưa nên nhận traffic. **maxUnavailable=0** không bảo đảm zero-downtime nếu readiness probe quá lạc quan, DB migrations không tương thích hoặc tất cả replicas cùng phụ thuộc service hỏng.

Production cần xem thêm **PodDisruptionBudget**, node drain, autoscaling, topology, rolling strategy và capacity khi chỉ còn N-1 instances.

## 12. Spring ApplicationAvailability và quy trình pre-drain nâng cao

Trong hệ thống có orchestrator khác Kubernetes hoặc LB deregistration chậm, có thể tách thành ba trạng thái nghiệp vụ:
- **SERVING**: sẵn sàng nhận request.
- **DRAINING**: đã phát readiness false, không nhận công việc mới có side effects; requests hiện tại tiếp tục hoàn tất.
- **STOPPING**: SIGTERM, HTTP connector shutdown, đóng resources.

Các transition này phải được điều phối qua kênh nội bộ xác thực. Đừng dùng một enum tự chế để thay toàn bộ Spring Boot readiness, Kubernetes EndpointSlice hoặc LB control plane; cần tích hợp các trạng thái.

### 12.1. Thao tác chỉ đánh dấu unready

~~~java
// Fragment trong một trusted lifecycle/control service.
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

void markUnready(ApplicationContext applicationContext) {
    AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC
    );
}
~~~

Đây là fragment minh họa, không biên dịch độc lập. Nó đổi **availability state của Spring Boot**, không tự:
- đóng server socket;
- chờ cache của load balancer cập nhật;
- kết thúc request đang chạy;
- thực thi SIGTERM;
- dừng background consumer.

Nếu có một trusted preStop flow đặt app unready rồi sleep, phải giới hạn quyền gọi; endpoint dùng shared secret không đủ khi triển khai sai network/security controls. Không copy một REST POST /drain permitAll vào production.

### 12.2. Tại sao không nên mark liveness broken khi drain?

Liveness probe fail có thể kích hoạt kubelet restart container thay vì để drain bình thường, khiến connection reset và tạo nhiều replicas churn. Khi một instance khỏe nhưng sắp dừng, phù hợp hơn là **readiness REFUSING_TRAFFIC** và **liveness CORRECT** cho đến khi shutdown thực sự diễn ra.

## 13. Những gì HTTP graceful shutdown không thể tự xử lý

### 13.1. @Async, scheduled jobs, queues

Một HTTP Controller đã hoàn tất có thể đã enqueue một background job. Nếu SIGTERM xảy ra sau response 202 mà job đang nằm trong in-memory executor queue, việc dừng web server **không bảo đảm task hoàn thành**.

Giải pháp:
- Dùng durable queue/DB outbox và ack theo transaction/idempotency khi cần.
- Stop nhận jobs mới, ngừng polling/consumption, chờ in-flight jobs theo ngân sách riêng.
- Với executors, gọi shutdown(), awaitTermination(...) và nếu vẫn không xong thì có chính sách checkpoint/cancel minh bạch.
- Với scheduled tasks hoặc message consumers, xem SmartLifecycle, listener container shutdown semantics và acknowledgment/redelivery.

Không giữ toàn bộ state quan trọng chỉ trong JVM RAM rồi kỳ vọng @PreDestroy được chạy trong mọi sự cố. Node crash, OOMKill và SIGKILL có thể ngắt không có cleanup.

### 13.2. WebSocket, SSE và gRPC streaming

Một WebSocket/SSE stream có thể sống hàng giờ; chờ vô hạn sẽ ngăn rollout hoàn tất. Phải có chính sách:
- Dừng tạo subscriptions mới khi draining.
- Thông báo client reconnect sang endpoint khác nếu protocol cho phép.
- Đóng stream với mã/reason tương ứng, không gửi secret.
- Giới hạn max connection age và thời gian drain.
- Hỗ trợ reconnect/backoff, resume từ cursor đã được kiểm quyền.
- Không suy luận Tomcat HTTP graceful shutdown tự xử lý mọi long-lived connection đúng business protocol.

Một client giữ HTTP/2/gRPC stream dài hoặc SSE/WS có thể cần retry/resume riêng; không thể bảo đảm “mọi kết nối luôn giữ tới khi user tự đóng” trong một termination window hữu hạn.

### 13.3. Database transactions và side effects

Một request có thể gọi payment provider xong nhưng chưa trả response; SIGKILL khiến client không biết kết quả. Retry có thể tạo giao dịch trùng. Dùng idempotency key, outbox, saga hoặc transaction pattern thích hợp; graceful shutdown chỉ giảm xác suất, không thay correctness.

**Chỉ xác nhận thành công với client sau khi state/side effect đã đạt tiêu chí durability của API.**

## 14. SIGTERM và PID 1 trong container

### 14.1. Linux signals cơ bản

- **SIGTERM**: yêu cầu tiến trình dừng có kiểm soát; JVM thường chạy shutdown hooks trong shutdown sequence.
- **SIGINT**: thường từ Ctrl+C; có thể kích hoạt shutdown theo Java runtime.
- **SIGKILL**: buộc dừng, không có cơ hội chạy shutdown hooks.
- **Exit code 137** thường gắn với SIGKILL/128+9, nhưng còn phải xem container OOMKilled, grace expiry hoặc yếu tố khác; không chẩn đoán chỉ bằng mã này.
- **Exit code 143** thường gắn SIGTERM/128+15 ở môi trường shell/container, nhưng quá trình Java có thể trả exit code khác khi xử lý signal hoặc lỗi.

Đừng đưa ra cam kết “SIGTERM chắc chắn hoàn tất mọi cleanup”. Nếu shutdown hook/phase bị kẹt và grace hết, runtime có thể buộc kill.

### 14.2. Vì sao shell-form ENTRYPOINT nguy hiểm?

~~~dockerfile
# Nên dùng:
ENTRYPOINT ["java", "-jar", "/app/app.jar"]

# Không nên giả định shell wrapper sẽ forward signal:
# ENTRYPOINT java -jar /app/app.jar
~~~

Exec form chạy Java trực tiếp làm PID 1; shell-form thường dùng một shell wrapper. Nếu wrapper không forward TERM đúng cách, Java có thể không được yêu cầu shutdown trước khi timeout. Nếu startup script cần logic, dùng **exec java -jar ...** ở cuối script.

### 14.3. Dừng từ IDE không giống Linux SIGTERM

Một IDE có thể dùng stop action không gửi SIGTERM theo cách Docker/Kubernetes sử dụng. Spring Boot docs cảnh báo kết quả graceful shutdown qua IDE có thể khác. Kiểm tra bằng **kill -TERM**, **docker stop** hoặc Kubernetes Pod termination khi cần xác nhận hành vi thực tế.

## 15. Readiness và load balancing trong HTTP/2, keep-alive, sticky sessions

### 15.1. Request mới có thể đi trên connection cũ

Load balancer không chọn Pod mới cho mỗi HTTP request trong mọi protocol. Nó có thể tái sử dụng TCP keep-alive connection, HTTP/2 multiplex streams hoặc giữ sticky affinity. Khi endpoint bị deregister:
- LB thường ngừng tạo new upstream connections sau khi cập nhật routing.
- Nhưng existing connections/streams có thể còn request đang chạy.
- Tùy proxy, một request mới trên existing keep-alive connection có thể bị từ chối hoặc reroute.
- HTTP/2 GOAWAY/drain behavior cần xem protocol, server và proxy cụ thể.

Không nói “EndpointSlice ready=false tức mọi TCP packets đến Pod chấm dứt ngay”. Health/routing là điều kiện chọn đích, không phải luôn là lệnh đóng socket hiện hữu.

### 15.2. Sticky session và WebSocket

Với sticky sessions hoặc WebSockets, client có thể gắn với Pod cũ lâu hơn HTTP request thường. Khi drain:
- Thông báo/reconnect theo protocol.
- Giữ session state trong shared store nếu cần.
- Không giữ business data chỉ ở memory của Pod sắp chết.
- Hỗ trợ resume/reauthentication khi client chuyển node.
- Tránh client reconnect dồn dập sau rollout bằng jitter.

## 16. Monitoring và phép đo khi rollout

Các metrics và logs nên quan sát:

| Lớp | Chỉ số | Câu hỏi |
| --- | --- | --- |
| Kubernetes | Pod Ready/Terminating/Available, EndpointSlice conditions | Pod đã bị đánh dấu terminating? |
| Probe | /readyz, /livez status và probe failures | Đã ngừng chọn Pod mới? |
| Ingress/LB | upstream 502/503/504, resets, endpoint target count | Routing cập nhật đã xong? |
| Tomcat | active requests, busy threads, connections | Còn request đang chạy? |
| Spring lifecycle | time from SIGTERM to context closed | Shutdown hoàn tất trong grace? |
| JVM/container | exit code, SIGKILL, OOMKilled, restart count | Bị buộc kill hay thoát bình thường? |
| DB/outbound | active connections/transactions, timeouts | Có đóng DB pool trước khi request xong? |
| Queue/consumers | unacked jobs, requeue, duplicate processing | Background tasks có an toàn? |
| Client | resets/timeouts, retry count, p95/p99 | User thực sự thấy bao nhiêu lỗi? |
| Rollout | available replicas, unavailable duration | Có thiếu capacity trong lúc rollout? |

**Điểm cần đo là user-visible failures**, không chỉ Kubernetes báo rollout thành công. Một rollout có thể thành công về deployment state nhưng gây hàng trăm HTTP 502 nếu deregistration chậm.

### 16.1. Log correlation

Khi thử shutdown:
1. Ghi timestamp Pod marked terminating/EndpointSlice ready false.
2. Ghi timestamp kubelet preStop bắt đầu/kết thúc.
3. Ghi timestamp JVM nhận TERM hoặc Spring bắt đầu shutdown.
4. Ghi thời điểm HTTP server ngừng nhận request mới.
5. Ghi in-flight request cuối cùng hoàn tất.
6. Ghi thời điểm Java process exit.
7. So khớp với proxy upstream errors và client retries.

Tránh log raw Authorization, cookies hoặc body dữ liệu nhạy cảm. Dùng trace/correlation IDs không cấp quyền.

## 17. Runbook kiểm thử end-to-end

### 17.1. Local JVM SIGTERM test

- [ ] Build runnable jar, bật server.shutdown=graceful.
- [ ] Chạy app qua Java process, chờ /readyz healthy.
- [ ] Gửi một request /api/slow đủ dài.
- [ ] Gửi SIGTERM khi request đã bắt đầu.
- [ ] Xác nhận request có cơ hội trả 200 trong grace.
- [ ] Gửi request mới trong shutdown và ghi nhận network/HTTP outcome, không kỳ vọng cố định 503.
- [ ] Đo thời gian Java process exit.
- [ ] Kiểm shutdown logs, không chỉ status curl.

### 17.2. Docker test

- [ ] Dùng exec-form ENTRYPOINT, Java nhận stop signal.
- [ ] docker stop với thời gian chờ đủ.
- [ ] Quan sát in-flight request và thời gian shutdown.
- [ ] Thử giảm stop timeout có chủ đích trên lab để hiểu SIGKILL, không làm trên production.
- [ ] Kiểm cleanup/exit code, không coi exit 137 là luôn do một nguyên nhân duy nhất.

### 17.3. Kubernetes rolling update

- [ ] Có ít nhất hai replicas và đủ capacity khi một Pod rời service.
- [ ] Readiness probe kiểm cổng ứng dụng thực.
- [ ] Liveness không phụ thuộc database chung và không fail khi drain bình thường.
- [ ] Pod terminationGracePeriodSeconds đủ cho preStop và Spring lifecycle.
- [ ] EndpointSlice của Pod terminating có ready=false.
- [ ] Load balancer/Ingress thực sự cập nhật routing trước khi Pod đóng server.
- [ ] Đo upstream resets và 502/503/504 trong rollout.
- [ ] Kiểm WebSocket/SSE/gRPC reconnect nếu có.
- [ ] Kiểm background jobs/queues và DB transactions khi Pod bị dừng.
- [ ] Kiểm số lượng replicas Available/Ready sau update.
- [ ] Không dùng force delete để suy ra graceful behavior.

### 17.4. Failure injection có kiểm soát

Trên staging được phép:
1. Chạy request chậm 5–15 giây và SIGTERM với grace đủ.
2. Thử tăng latency của ingress route update, xác nhận preStop buffer cần thiết.
3. Thử proxy giữ connection cũ/HTTP/2.
4. Thử shutdown khi có database transaction và message đang xử lý; xác minh no duplicate hoặc redelivery-safe.
5. Thử SIGKILL hoặc grace quá ngắn và kiểm hệ thống có phục hồi nhờ idempotency.
6. Thử Pod bị OOMKill; không giả định @PreDestroy chạy.
7. Thử capacity N-1 replicas trong rolling update.
8. Thử liveness/readiness fail riêng biệt, không tạo restart loop.
9. Thử reconnect burst sau terminate hàng loạt, có backoff/jitter.

Không thực hiện destructive fault injection trên production khi chưa được phê duyệt.

## 18. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Cứ rollout là HTTP 502/503 thoáng qua | LB chưa gỡ upstream khi JVM đóng | EndpointSlice propagation, preStop/drain, LB behavior |
| /readyz fail ngay sau SIGTERM nhưng không có JSON | Connector đang ngừng accept | Bình thường; đọc internal state/logs |
| Pod thoát trước request 10 giây hoàn tất | Grace quá ngắn hoặc chưa bật graceful | server.shutdown, lifecycle timeout, TERM timing |
| JVM không nhận signal trong Docker | Shell-form ENTRYPOINT/wrapper | Exec-form, exec java, PID 1 |
| Pod bị SIGKILL sau preStop sleep | Sleep dùng hết termination grace | Tính tổng ngân sách, rút preStop hoặc tăng grace |
| HTTP 200 vẫn được phục vụ sau readiness false | Direct/old connection, readiness không đóng port | Drain/admission/routing policy |
| /livez fail khi drain, kubelet restart Pod | Dùng liveness để báo không ready | Phân biệt readiness/liveness |
| Actuator management port healthy nhưng main port không nhận | Probe kiểm sai network stack | add-additional-paths và main port |
| External LB vẫn gửi vào Pod terminating | LB cache/deregistration lag | Provider-specific target drain, traffic telemetry |
| WebSocket bị reset mỗi rollout | Không có reconnect/close protocol | Client retry/resume/reauth |
| Kafka job xử lý trùng sau rollout | Ack/commit chưa bền vững, redelivery | Idempotency và consumer drain |
| Spring lifecycle 30s nhưng tổng stop >30s | Timeout theo phase, thêm bean destruction | Đo từng phase và termination grace |
| Pod mới Ready nhưng request thất bại | Probe quá lạc quan, warmup chưa xong | Startup/readiness thực, load test |
| Rolling update maxUnavailable=0 vẫn lỗi | LB lag, không đủ N-1 capacity, sticky connections | Test traffic thật, network/ingress |
| Force delete “nhanh” nhưng mất request | SIGKILL/không graceful | Tránh force nếu muốn drain |
| preStop exec không chạy | Image không có /bin/sh hoặc sleep | Dùng image/hook tương thích |

## 19. Câu hỏi tự kiểm tra

**1.** Readiness false có tự đóng HTTP server không?  
**Đáp án:** Không. Nó báo cho routing/probe, không tự đóng sockets hoặc kết thúc JVM.

**2.** SIGTERM có bảo đảm load balancer đã gỡ Pod trước khi shutdown không?  
**Đáp án:** Không. Routing update là bất đồng bộ; cần phối hợp Pod termination, preStop/drain hoặc LB-specific deregistration.

**3.** Trong Spring Boot 3.3, cần property nào bật graceful?  
**Đáp án:** **server.shutdown=graceful**.

**4.** spring.lifecycle.timeout-per-shutdown-phase=30s là deadline tuyệt đối toàn JVM?  
**Đáp án:** Không, đó là timeout theo phase, có thể còn phases khác và cleanup.

**5.** terminationGracePeriodSeconds bắt đầu sau khi preStop kết thúc?  
**Đáp án:** Không. Nó tính cả thời gian chạy preStop.

**6.** Pod terminating có thể còn nằm trong EndpointSlice không?  
**Đáp án:** Có. ready=false, terminating=true; serving có thể phản ánh khả năng tiếp tục phục vụ traffic draining.

**7.** Có chắc SIGTERM làm Tomcat trả 503 cho request mới không?  
**Đáp án:** Không. Tomcat thường dừng nhận ở network layer; client có thể gặp refused/reset/timeout.

**8.** /readyz ở management port riêng luôn chứng minh cổng application còn nhận traffic?  
**Đáp án:** Không. Nên dùng additional paths trên main port nếu cần kiểm stack phục vụ thực.

**9.** Vì sao không dùng liveness broken khi cần gỡ Pod khỏi LB?  
**Đáp án:** Liveness failure kích hoạt restart; readiness phù hợp hơn để loại khỏi traffic.

**10.** preStop sleep 8 giây có bảo đảm mọi external LB đã cập nhật?  
**Đáp án:** Không, phải đo LB/Ingress propagation và điều chỉnh theo môi trường.

**11.** Docker shell-form ENTRYPOINT có nguy cơ gì?  
**Đáp án:** Shell làm PID 1 không forward TERM tới Java, làm shutdown hook không chạy đúng lúc.

**12.** SIGKILL có chạy @PreDestroy không?  
**Đáp án:** Không. Cần durability, idempotency và recovery riêng.

**13.** HTTP request hoàn thành nhưng background task còn chạy thì server.shutdown có bảo đảm task xong không?  
**Đáp án:** Không. Task/queue có lifecycle riêng, cần drain/ack/durability.

**14.** Last Event ID của SSE/WebSocket reconnect có tự chứng minh quyền truy cập không?  
**Đáp án:** Không. Event replay phải reauthorize theo user/tenant.

**15.** maxUnavailable=0 có tự bảo đảm zero errors khi rollout không?  
**Đáp án:** Không. Capacity, readiness correctness, LB propagation, proxies và long-lived sessions đều ảnh hưởng.

**16.** Có thể dùng /api/state để đọc readiness REFUSING_TRAFFIC sau khi server graceful stop bắt đầu không?  
**Đáp án:** Không chắc. Tomcat có thể ngừng nhận HTTP nên endpoint không còn truy cập; dùng logs và application events để kiểm.

**17.** Một request có side effect bị SIGKILL trước khi trả response. Retry có nguy cơ gì?  
**Đáp án:** Thực thi side effect hai lần; cần idempotency key/state reconciliation.

## 20. Checklist triển khai và kết luận

- [ ] Đã bật **server.shutdown=graceful** trên Spring Boot 3.3.
- [ ] Có **spring.lifecycle.timeout-per-shutdown-phase** phù hợp thời gian in-flight.
- [ ] Readiness/liveness được tách đúng; /readyz và /livez chạy trên main HTTP port.
- [ ] Có đủ replicas/rolling strategy và capacity khi Pod cũ rời LB.
- [ ] Hiểu EndpointSlice ready=false, serving/terminating state và độ trễ routing.
- [ ] preStop delay nếu cần, nhưng không lạm dụng và phải tính trong tổng grace.
- [ ] terminationGracePeriodSeconds đủ cho preStop + JVM shutdown + margin.
- [ ] Docker/OCI image dùng exec-form ENTRYPOINT hoặc forward signal đúng.
- [ ] Không dùng SIGKILL/force delete để kiểm graceful behavior.
- [ ] Có policy cho WebSocket/SSE/gRPC streams và reconnect/backoff.
- [ ] Background workers, queues, database/outbound clients có shutdown riêng.
- [ ] Có idempotency, transaction và durable state để sống sót sau forced kill.
- [ ] Quan sát client errors, LB resets, in-flight requests, phase duration và exit reasons.
- [ ] Kiểm tra thật bằng SIGTERM, Docker stop và Kubernetes rollout trong staging.
- [ ] Không expose drain/shutdown control endpoint công khai.

**Ghi nhớ:** shutdown an toàn là một **giao thức phối hợp giữa ứng dụng, bộ cân bằng tải và orchestrator**, không phải chỉ một property Spring Boot. **Readiness** cho biết instance có còn được chọn cho traffic mới; **EndpointSlice/LB deregistration** chuyển traffic khỏi nơi sắp dừng; **SIGTERM** bắt đầu shutdown của JVM; **graceful shutdown** cho request đang xử lý hoàn tất trong giới hạn; **SIGKILL** là ranh giới cưỡng bức cuối cùng. Chỉ khi thời gian, routing, signal và task lifecycle khớp nhau thì rolling update mới giảm thiểu request lỗi một cách đáng tin.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Graceful Shutdown, server.shutdown và lifecycle phase timeout: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Actuator Endpoints, Kubernetes probes, readiness/liveness và additional paths: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — ApplicationAvailability, ReadinessState và events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Kubernetes — Pod Lifecycle, termination flow, preStop, SIGTERM/SIGKILL, EndpointSlice conditions: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Kubernetes — Pods and Endpoint Termination Flow: https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/
- Kubernetes — Configure Liveness, Readiness and Startup Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Kubernetes — Container Lifecycle Hooks: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/
- Kubernetes — Deployment Rolling Updates: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Spring Framework — SmartLifecycle and ApplicationContext shutdown: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Docker — Dockerfile ENTRYPOINT exec and shell forms: https://docs.docker.com/reference/dockerfile/#entrypoint
