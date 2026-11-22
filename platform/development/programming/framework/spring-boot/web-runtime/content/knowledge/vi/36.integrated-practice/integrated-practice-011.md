# Triển khai thay phiên bản với graceful shutdown và yêu cầu đang xử lý

> **Module:** Spring Boot – web-runtime. **Nhóm:** Thực hành tổng hợp. Bài này thực hành **thay phiên bản dịch vụ v1 → v2 không cắt ngang một HTTP request đã bắt đầu**, đồng thời **ngừng điều hướng request mới đến instance đang rút khỏi cụm**. Ta kết hợp **Spring Boot 3.3.x, Java 17+, Maven, Docker, Kubernetes Deployment/Service, Actuator readiness/liveness, SIGTERM và quan sát in-flight requests**. Phần cuối có kiểm thử độc lập, cách xác minh, rollback, lỗi thường gặp, SLO và mở rộng cho DB, SSE, WebSocket. Các cấu hình thời gian, image và replica là **giá trị lab**, phải điều chỉnh theo tải và hạ tầng thực tế.

## 1. Mục tiêu và điều kiện nghiệm thu

Hoàn thành bài này nghĩa là bạn hiểu và tự kiểm được:

1. Tại sao rolling deployment cần **hai cơ chế bổ sung**: load balancer/Service **không chọn Pod cũ cho request mới** và Spring Boot **cho phép request đã nhận hoàn tất**.
2. Spring Boot **3.3** cần `server.shutdown=graceful` để bật graceful, và `spring.lifecycle.timeout-per-shutdown-phase` là timeout **theo phase**, không phải tổng thời gian JVM.
3. Kubernetes có `terminationGracePeriodSeconds`, `preStop`, Pod `Terminating` và EndpointSlice `ready=false`; **preStop tiêu tốn chính grace period chung**.
4. Readiness khác liveness; `/readyz` và `/livez` trên **cổng ứng dụng** giúp Kubernetes định tuyến đúng.
5. Docker `ENTRYPOINT ["java","-jar",...]` truyền tín hiệu stop phù hợp tới JVM; `kill -9`/SIGKILL không graceful.
6. Một yêu cầu kéo dài khoảng 12 giây có thể trả HTTP 200 từ **v1** khi Pod v1 nhận SIGTERM trong lúc xử lý, nếu grace budget đủ và client còn kết nối.
7. Request mới đến **Service** sau khi rollout thành công phải đi tới v2; request đang xử lý trên v1 không tự động chuyển sang v2.
8. Không nhất thiết nhận HTTP 503 từ Tomcat sau SIGTERM; **network refusal/reset** cũng là cách từ chối request mới.
9. Kiểm thử bằng Maven/JUnit cho happy path và bằng **process/pod-level test** cho graceful; JUnit bình thường không tự mô phỏng được Pod termination.
10. Phân biệt “Service có thể trả 200” với “không xảy ra một lỗi nào trên mọi request”; rolling update cần đủ replicas/capacity, readiness, drain propagation và quan sát thực tế.
11. Biết xác minh logs, EndpointSlice, rollout events, status codes 499/502/503/504, retries, active requests, timeout và request completion.
12. Có kế hoạch rollback, idempotency cho POST, chính sách streaming/long jobs và chỉ thay cấu hình khi đo được nguyên nhân.

**Tiêu chí thành công trong lab:**

- Trước update, `/api/info` trả `release=v1` và ứng dụng ready.
- Trong phép thử xóa một Pod, request `/api/slow?waitMs=12000` đã bắt đầu ở Pod đó **trả 200 với release v1** sau khi Pod nhận yêu cầu termination, nếu đủ 25 giây drain; tuyệt đối không chỉ dựa vào exit code của lệnh kubectl.
- Khi rollout `v1 → v2` thành công, tất cả Pods ready dưới Deployment mới phục vụ `release=v2`; Service không còn route bình thường tới Pod terminating theo policy.
- Các request **mới** trong rollout không phát sinh 5xx/connection errors ngoài error budget đo được; nếu có, điều tra route propagation, capacity, probes và các tầng ngoài cluster.
- Logs cho thấy `slow-start` và `slow-done` của request cũ trước khi process tắt sạch; không có khoảng chờ vô hạn.
- Có thể hoàn tác một bản deployment lỗi bằng `kubectl rollout undo` và quan sát phục hồi.

## 2. Mô hình trước–sau khi thay phiên bản

~~~text
Trước rollout:
                  Service / Ingress
                    |
            +-------+-------+
            |       |       |
            v       v       v
           Pod A    Pod B   Pod C
             v1      v1      v1
             READY   READY   READY

Khi rolling update:
                  Service / Ingress
                    |
             +------+------+-------+
             |      |      |       |
             v      v      v       v
           Pod A  Pod B  Pod C    Pod D
             v1     v1     v1      v2
           READY   READY  READY   warming...
                                     |
                                   READY
                                     |
           Pod A chuyển Terminating -> endpoint ready=false
           Pod A không nhận request mới qua routing bình thường
           Request đang chạy trong Pod A được drain tới deadline
           Pod A thoát; Pod D và các Pod v2 tiếp tục nhận traffic

Sau rollout:
                  Service / Ingress
                    |
            +-------+-------+
            |       |       |
            v       v       v
           Pod D   Pod E   Pod F
             v2      v2      v2
             READY   READY   READY
~~~

**Lưu ý:** Kubernetes không bắt buộc chọn đúng Pod A trước, không bảo đảm tiến trình khởi tạo và xóa diễn ra theo thời điểm cố định trong hình. Đây là logic tổng quan của Deployment `replicas: 3`, `maxSurge: 1`, `maxUnavailable: 0`. Tốc độ rollout phụ thuộc scheduling, image pull, startup, readiness, `minReadySeconds` và cluster capacity.

### Request đang xử lý đi đâu?

Request đã tới Pod A thì **ở lại Pod A** cho tới khi xong, bị hủy, kết nối lỗi hoặc hết deadline. Kubernetes Service không thể chuyển một Java controller method đang chạy từ Pod A sang Pod D. Điều phối phiên bản không phải migration của call stack, thread, transaction hoặc WebSocket session.

Một request mới gửi sau khi Pod A bị rút khỏi Service routing có thể được load balancer đưa tới Pod B/C/D tùy state; request mới không tự động được chặn toàn cluster. Chính **old Pod** cần ngừng tiếp nhận sau thời điểm dừng, còn các Pods khỏe tiếp tục phục vụ.

## 3. Thuật ngữ: rolling update, traffic drain và graceful shutdown

| Thành phần | Vai trò | Cạm bẫy |
|---|---|---|
| Deployment RollingUpdate | Thay ReplicaSet/Pods có image mới với policy về availability | Không tự đảm bảo in-flight request hoàn tất |
| Service/EndpointSlice | Chọn endpoint sẵn sàng cho traffic | Cập nhật route có độ trễ và các LB ngoài cluster có cache |
| Readiness probe | Báo Pod có nên nhận **request mới** không | Không đồng nghĩa Pod đã chết hoặc request cũ bị cancel |
| Liveness probe | Báo process cần restart vì không hồi phục được không | Không nên dùng dependency chập chờn để kill mọi Pods |
| Startup probe | Cho ứng dụng đủ thời gian start trước khi liveness được áp dụng | Không thay readiness gating |
| preStop lifecycle hook | Thực hiện công việc *trước khi TERM* | Thời gian hook nằm trong termination grace |
| SIGTERM | Yêu cầu process dừng có kiểm soát | Chỉ có tác dụng khi JVM nhận được và callback hoàn tất |
| Spring graceful shutdown | Ngừng nhận HTTP requests mới, đợi requests đã nhận trong timeout | Không hoàn tất stream vô hạn hoặc hủy mọi background work |
| shutdown phase timeout | `spring.lifecycle.timeout-per-shutdown-phase` | Không phải tổng thời gian Pod được phép sống |
| SIGKILL | Dừng cưỡng bức khi hết grace hoặc bị kill | Không chạy Java shutdown hooks/cleanup bình thường |
| In-flight request | Request đã vào server/handler và chưa xong | Không giống một socket rảnh đang keep-alive |
| Old/new release | Phiên bản build được deploy | Một Service có thể trả hỗn hợp v1/v2 **trong rollout**, hoàn toàn bình thường |

### Điều kiện tránh gián đoạn

Không có một property duy nhất bảo đảm zero downtime. Cần:

~~~text
Capacity đủ cho pods mới
    + Startup đúng
    + Readiness chỉ mở khi thực sự phục vụ được
    + Service/Ingress bỏ endpoint terminating kịp thời
    + Spring Boot dừng new accepts
    + Existing requests hoàn tất trong deadline
    + Client retries/idempotency hợp lý
    + DB/API compatibility v1-v2
    + Observability + rollback
    = Giảm mạnh lỗi khi rollout
~~~

**Zero-downtime** nên là mục tiêu định lượng bằng 5xx rate, connection errors và user-facing SLO, không phải lời cam kết tuyệt đối chỉ từ `maxUnavailable=0`.

## 4. Spring Boot 3.3: graceful shutdown có cần bật?

**Có.** Tài liệu **Spring Boot 3.3** ghi cách bật:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Đừng áp quy tắc mặc định của các bản Spring Boot **mới hơn** cho 3.3. Các tài liệu 3.5+/current có thể nói graceful enabled by default; bài này cố ý neo vào **3.3**.

Spring Boot hỗ trợ graceful trên Tomcat, Jetty, Reactor Netty và Undertow, cả Servlet lẫn Reactive. Khi `ApplicationContext` đóng, graceful được thực hiện ở phase sớm khi dừng các `SmartLifecycle` beans. Server dành một khoảng thời gian để request đang chạy có cơ hội hoàn tất và không cho request mới tiếp tục vào.

Hành vi từ chối request mới **khác nhau theo embedded server**:

| Server | Khi bắt đầu graceful drain | Điều client có thể thấy |
|---|---|---|
| Tomcat | Ngừng nhận mới tại network layer | Connection refused/reset/EOF; không nhất thiết HTTP 503 |
| Jetty | Ngừng nhận mới tại network layer | Lỗi network hoặc protocol-specific |
| Reactor Netty | Ngừng nhận mới tại network layer | New connection/stream không được chấp nhận theo implementation |
| Undertow | Có thể nhận connection nhưng trả HTTP 503 | `503 Service Unavailable` |

Không viết test đòi **tất cả** server gửi `503`: với Tomcat, từ chối ở TCP layer **không có HTTP response**. Persistent HTTP/1.1/HTTP/2 connections có thể tạo races; kiểm request start thực thay vì chỉ timestamp mở socket.

### spring.lifecycle.timeout-per-shutdown-phase không phải toàn bộ JVM timeout

Nếu đặt 25 giây, đó là **thời gian tối đa cho một shutdown phase**. Ứng dụng có thể có nhiều SmartLifecycle phases và resource cleanup. Đặc biệt một `@PreDestroy` tốn thời gian có thể làm shutdown lâu hơn phase graceful.

Hệ quả: Kubernetes `terminationGracePeriodSeconds` không nên bằng đúng 25 chỉ vì Spring property là 25s. Phải dành thời gian cho `preStop`, network route propagation, phases khác, closing resources, OS/runtime scheduling và margin.

## 5. Traffic draining trên Kubernetes: điều gì xảy ra khi Pod bị xóa?

Luồng mô hình hóa khi Deployment bỏ một Pod cũ:

~~~text
T0  API Server đánh dấu Pod Terminating
    |  Kubernetes bắt đầu termination grace countdown
    |
    +--> EndpointSlice cập nhật endpoint terminating=true
    |    ready=false đối với terminating endpoints thông thường
    |    Service/Ingress routing cập nhật bất đồng bộ
    |
    +--> Kubelet thực thi preStop (nếu có)
    |    hook tiêu tốn cùng terminationGracePeriodSeconds
    |
T1  preStop xong, kubelet/container runtime gửi TERM tới process
    |
T2  JVM đóng Spring ApplicationContext
    |  Spring Boot bắt đầu graceful web shutdown
    |  no new accepts, in-flight requests được chờ
    |
T3  In-flight work xong hoặc phase timeout
    |  Spring lifecycle phases khác và cleanup
    |
T4  Process exit
    |
T5  Nếu quá termination grace và vẫn còn process:
    container runtime có thể gửi SIGKILL
~~~

**Lưu ý race/độ trễ:** EndpointSlice controller, kube-proxy/Service proxy, ingress và external load balancer không đồng bộ tuyệt đối. Một endpoint terminating có `ready=false` cho traffic bình thường; một số dataplanes còn xét `serving` và `terminating` để xử lý drain, và hành vi khi tất cả endpoints đều terminating có thể khác. Không suy ra “tại microsecond Pod Terminating thì mọi request trên trái đất đã ngừng route tới nó”.

### EndpointSlice conditions

Kubernetes exposes ba điều kiện quan trọng:

- `ready`: endpoint thường sẵn sàng nhận traffic thông thường. Terminating endpoint thông thường sẽ có `ready=false` vì backward compatibility.
- `serving`: phản ánh trạng thái còn phục vụ, hữu ích khi endpoint đang terminating và cần quan sát drain.
- `terminating`: endpoint liên kết Pod đang kết thúc.

Một trạng thái minh họa có thể là:

~~~json
{
  "conditions": {
    "ready": false,
    "serving": true,
    "terminating": true
  }
}
~~~

Đây là ví dụ **không phải kết quả chắc chắn** ở mọi controller/Pod; `serving` tùy tình trạng Pod readiness và cách controller cập nhật. Một endpoint serving+terminating không nên bị diễn giải như endpoint ready cho **new regular traffic**.

## 6. Readiness, liveness và startup probe

Spring Boot Actuator tích hợp `ApplicationAvailability` và health probe groups:

- Readiness `ACCEPTING_TRAFFIC`: chọn để nhận request mới.
- Readiness `REFUSING_TRAFFIC`: chưa sẵn sàng hoặc đang dừng; không nhất thiết app chết.
- Liveness `CORRECT`: tiến trình còn khả năng phục hồi/phục vụ.
- Liveness `BROKEN`: process cần can thiệp/restart theo policy.

Các trạng thái này có thể khác nhau khi startup và shutdown. **Đang dừng**: app có thể vẫn **liveness CORRECT** để trả lời những request đã được nhận, nhưng **readiness REFUSING_TRAFFIC**. Không cấu hình liveness fail chỉ vì readiness fail; cách đó có thể khiến kubelet giết process sớm hơn drain budget.

Spring Boot Actuator:

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
~~~

Các health groups:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
GET /livez       (trên app main port)
GET /readyz      (trên app main port)
~~~

Lựa chọn `add-additional-paths=true` làm `/livez` và `/readyz` có mặt trên **cùng HTTP port với API**, giảm rủi ro management port vẫn hoạt động nhưng main app port chết. Kubernetes có thể auto-enable probes ở Boot theo môi trường, song trong lab bật rõ để thử cả local.

**Trước TERM**, `/readyz` thường trả HTTP 200/status UP khi app ready. **Sau TERM**, Tomcat có thể đã ngừng nhận connection mới, nên `curl /readyz` có thể không nối được thay vì trả JSON 503. Đó không phải bằng chứng readiness không chuyển state: **listener đã đóng** là một phần graceful.

### Tránh readiness/liveness dựa mù vào external DB

Nếu liveness phụ thuộc một database dùng chung, DB outage có thể khiến hàng loạt Pods bị restart tạo cascade. Nếu readiness phụ thuộc DB một cách cứng nhắc, toàn bộ Service có thể mất endpoints. Xác định rõ dependency nào thực sự khiến instance không thể đáp ứng một traffic class; theo dõi riêng health/metrics, giữ liveness phù hợp.

## 7. Quy hoạch time budget trước khi viết YAML

Dự kiến request HTTP của lab chạy tối đa **20 giây**. Dùng ngân sách ví dụ:

| Khoảng thời gian | Giá trị | Vai trò |
|---|---:|---|
| Longest intentional request trong lab | 20s | API giới hạn `waitMs <= 20000` |
| Spring graceful web phase | 25s | `spring.lifecycle.timeout-per-shutdown-phase=25s` |
| Optional preStop để LB route hội tụ | 5s | Nằm trong Pod grace, *trước TERM* |
| Các lifecycle phases khác + cleanup ước tính | 10s | Phải đo với app thật |
| Safety margin | 20s | Scheduling/jitter/LB/termination overhead |
| Kubernetes Pod termination grace | **60s** | 5 + 25 + 10 + 20 = 60s |

**Không xem bảng là công thức bảo đảm:** nếu thêm hai SmartLifecycle phases có thể mỗi phase chờ tới 25s, phần “other 10s” có thể không đủ. Nếu request giữ SSE/WebSocket vô thời hạn, nó có thể chạm phase timeout. Do đó phải đo shutdown duration thực, có SLO cho quiesce/cleanup và không dựa vào độ dài grace để sửa việc work không có deadline.

### Có nên luôn cấu hình preStop sleep?

Không. Kubernetes đã đánh dấu terminating EndpointSlice ready=false. Thêm sleep có thể giúp ingress/external LB route propagation trong một số hạ tầng; nhưng:

- Sleep **không tự chuyển Spring readiness** và không đóng connector; trong lúc preStop sleep, app có thể vẫn nhận direct TCP requests.
- Sleep làm giảm thời gian còn lại cho Spring drain sau TERM.
- Delay quá lớn làm rollout chậm, giữ resources cũ lâu, gây áp lực khi autoscaling.
- Nếu image distroless không có `/bin/sh`/`sleep`, hook exec sẽ fail.
- Phải đo thực tế LB deregistration latency trước khi chọn 5 giây; một hạ tầng có thể không cần preStop.

Trong lab ta dùng **5 giây** để dễ thấy timeline, ghi rõ đó là **ví dụ có thể bỏ**.

## 8. Cấu trúc project lab hoàn chỉnh

~~~text
rolling-drain-lab/
  pom.xml
  Dockerfile
  src/
    main/
      java/
        example/
          rollout/
            RollingDrainApplication.java
      resources/
        application.properties
    test/
      java/
        example/
          rollout/
            RollingDrainApplicationTests.java
  k8s/
    deployment.yaml
    service.yaml
~~~

Bài lab chọn **Spring MVC/Tomcat** vì dùng đồng bộ `Thread.sleep` để quan sát in-flight Servlet request. Đây là mô phỏng có chủ đích, **không khuyến nghị sleep trong API production**. Dịch vụ thật cần bounded DB/outbound timeouts, giới hạn concurrency, idempotency và async jobs cho tác vụ dài.

### Môi trường chuẩn bị

- JDK 17+ và Apache Maven đã cài.
- Docker để build image.
- Một Kubernetes cluster lab có quyền tạo Deployment, Service, Pod; có thể dùng **kind**, minikube hoặc cluster thử nghiệm.
- `kubectl` kết nối đúng cluster/namespace. Trước khi làm nên kiểm kubeconfig để tránh thao tác lên production.
- Với kind, phải **load local Docker image** vào node hoặc dùng container registry mà cluster có quyền pull.
- Terminal Bash cho script `kill -TERM`, `seq`, `grep`; Windows chạy trong WSL/Linux shell tương thích.
- `curl` cho HTTP; cluster có thể cần network access để pull debug client image. Nếu không có, dùng image debug đã được tổ chức cho phép.

Các lệnh Docker/kubectl phía dưới là **hướng dẫn lab**, không phải lệnh đã thực thi trên cluster người đọc.

## 9. Maven pom.xml đầy đủ

Tạo `rolling-drain-lab/pom.xml`:

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
    <artifactId>rolling-drain-lab</artifactId>
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

`spring-boot-starter-web` mang Spring MVC/Tomcat, `actuator` cung cấp health/readiness/liveness, `starter-test` cung cấp JUnit 5 và TestRestTemplate. Boot parent quản lý versions tương thích, không cần pin Spring Framework/Tomcat riêng.

`3.3.13` ở đây dùng để giữ semantics Boot 3.3 của bài. Trong production, chọn release đang được hỗ trợ và có security patches phù hợp với tổ chức; khi đổi Boot major/minor, cần kiểm lại graceful defaults và health probe properties.

## 10. application.properties: một nơi khai báo budget

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=rolling-drain-lab
server.port=8080

# Boot 3.3: phải bật rõ graceful.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s

# Actuator availability probes ngay trên main application port.
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true

# Release lấy từ Docker build ARG -> ENV; Pod name từ Downward API.
app.release=${APP_RELEASE:v1}
app.instance=${POD_NAME:local}

# Không phơi raw exceptions/stacktraces trong public errors.
server.error.include-message=never
server.error.include-exception=false
server.error.include-stacktrace=never
~~~

**Version marker:** `APP_RELEASE` là environment variable của image v1/v2; `POD_NAME` đến từ Kubernetes Downward API. Nhờ vậy Deployment chỉ cần **đổi container image** để đổi version marker; ta không phải làm hai lần `kubectl set env` và `kubectl set image`, vốn có thể gây hai rollouts riêng.

**Không nhầm:** `server.tomcat.connection-timeout` là timeout liên quan request line/connector, không quyết định thời gian controller được chạy sau khi TERM. `spring.mvc.async.request-timeout` áp cho MVC async processing, không tự biến một synchronous controller thành cancellable request.

## 11. Java application: theo dõi release, instance và active work

Tạo `src/main/java/example/rollout/RollingDrainApplication.java`:

~~~java
package example.rollout;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RollingDrainApplication {

    public static void main(String[] args) {
        SpringApplication.run(RollingDrainApplication.class, args);
    }

    public record InfoReply(
            String release, String instance, int active) {
    }

    public record SlowReply(
            String release, String instance, String callId,
            long waitMs, long elapsedMs, boolean completed) {
    }

    @RestController
    static class Api {
        private static final Logger log =
                LoggerFactory.getLogger(Api.class);

        private final String release;
        private final String instance;
        private final AtomicInteger active = new AtomicInteger();

        Api(@Value("${app.release:v1}") String release,
            @Value("${app.instance:local}") String instance) {
            this.release = release;
            this.instance = instance;
        }

        @GetMapping("/api/info")
        public InfoReply info() {
            return new InfoReply(
                    release, instance, active.get());
        }

        @GetMapping("/api/slow")
        public ResponseEntity<?> slow(
                @RequestParam(defaultValue = "500")
                long waitMs) throws InterruptedException {

            // Demo giới hạn tối đa 20s; không cho sleep vô hạn.
            if (waitMs < 0 || waitMs > 20000) {
                return ResponseEntity.badRequest().body(
                    Map.of("error", "waitMs must be 0..20000"));
            }

            final String callId = UUID.randomUUID().toString();
            final long started = System.nanoTime();
            int inflight = active.incrementAndGet();

            log.info(
                "slow-start release={} instance={} id={} "
                    + "waitMs={} active={}",
                release, instance, callId, waitMs, inflight);

            try {
                Thread.sleep(waitMs);
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);

                log.info(
                    "slow-done release={} instance={} id={} "
                        + "elapsedMs={}",
                    release, instance, callId, elapsedMs);

                return ResponseEntity.ok(new SlowReply(
                    release, instance, callId,
                    waitMs, elapsedMs, true));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                log.warn(
                    "slow-interrupted release={} instance={} id={}",
                    release, instance, callId);
                throw ex;
            } finally {
                int remaining = active.decrementAndGet();
                log.info(
                    "slow-cleanup release={} instance={} "
                        + "id={} active={}",
                    release, instance, callId, remaining);
            }
        }

        @PreDestroy
        void onDestroy() {
            log.info(
                "resources-destroying release={} instance={} "
                    + "active={}",
                release, instance, active.get());
        }
    }
}
~~~

### Giải thích code

- `/api/info` trả phiên bản, Pod name và số lượng requests đang xử lý tại **instance hiện tại**. Khi gọi qua Service, load balancer có thể chọn **một Pod khác mỗi request**; muốn theo dõi đúng Pod khi test drain, truy cập Pod IP qua debug client hoặc correlation logs.
- `/api/slow?waitMs=12000` giữ một Servlet worker thread khoảng 12 giây. Đây là **blocking demo** của Spring MVC, phù hợp để thấy graceful giữ request đã nhận. Không dùng `Thread.sleep` cho long-running business operation production.
- `active.incrementAndGet()` xảy ra ngay sau validation, `decrementAndGet()` trong `finally` giúp đếm đúng khi success hoặc interruption.
- Log `slow-start`, `slow-done`, `slow-cleanup`, `resources-destroying` cho phép phân biệt một work đã hoàn tất với process cleanup.
- `callId` giúp liên hệ log start/done trong một Pod; UUID tự sinh không phải business idempotency key.
- HTTP response mang release **v1 hoặc v2 của chính Pod thực xử lý**, không bị Kubernetes sửa giữa request. Nếu request bắt đầu trên v1 và xong trong drain, nó vẫn trả `release=v1` dù Service đã bắt đầu đưa traffic mới sang v2.
- `@PreDestroy` chỉ quan sát giai đoạn cleanup; **không dùng callback này để ngủ chờ request**. Built-in graceful web server đảm nhận việc chờ in-flight requests theo phase.
- Response success chỉ có nếu client còn kết nối. Một controller log `slow-done` không tự bảo đảm TCP bytes tới browser; kiểm thêm client status và errors.

### Ví dụ JSON output

`GET /api/info` trên Pod v1:

~~~json
{
  "release": "v1",
  "instance": "rolling-drain-lab-7c49f9b79c-k8d2n",
  "active": 0
}
~~~

Tên Pod là **minh họa**. Nếu gọi local, instance mặc định là `local`.

`GET /api/slow?waitMs=12000` khi hoàn tất trên Pod v1:

~~~json
{
  "release": "v1",
  "instance": "rolling-drain-lab-7c49f9b79c-k8d2n",
  "callId": "d3bd11b9-e7c4-49ec-a281-e2fbcbf12b4d",
  "waitMs": 12000,
  "elapsedMs": 12003,
  "completed": true
}
~~~

`elapsedMs` chỉ là kết quả ví dụ; thực tế có scheduling/GC jitter, không assert đúng 12003ms. Khi invalid waitMs, trả HTTP 400 thay vì sleep.

## 12. Unit/integration smoke tests trong JVM

Tạo `src/test/java/example/rollout/RollingDrainApplicationTests.java`:

~~~java
package example.rollout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "app.release=test-v1")
class RollingDrainApplicationTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void infoContainsTestRelease() {
        ResponseEntity<RollingDrainApplication.InfoReply> r =
                http.getForEntity(
                    "/api/info",
                    RollingDrainApplication.InfoReply.class);

        assertEquals(HttpStatus.OK, r.getStatusCode());
        assertNotNull(r.getBody());
        assertEquals("test-v1", r.getBody().release());
        assertTrue(r.getBody().active() >= 0);
    }

    @Test
    void shortRequestFinishesWithSameRelease() {
        ResponseEntity<RollingDrainApplication.SlowReply> r =
                http.getForEntity(
                    "/api/slow?waitMs=30",
                    RollingDrainApplication.SlowReply.class);

        assertEquals(HttpStatus.OK, r.getStatusCode());
        assertNotNull(r.getBody());
        assertEquals("test-v1", r.getBody().release());
        assertEquals(30L, r.getBody().waitMs());
        assertTrue(r.getBody().completed());
    }

    @Test
    void rejectsUnboundedWait() {
        ResponseEntity<String> r =
                http.getForEntity(
                    "/api/slow?waitMs=25000", String.class);

        assertEquals(HttpStatus.BAD_REQUEST, r.getStatusCode());
    }

    @Test
    void readinessIsUpBeforeShutdown() {
        ResponseEntity<String> r =
                http.getForEntity("/readyz", String.class);

        assertEquals(HttpStatus.OK, r.getStatusCode());
        assertNotNull(r.getBody());
        assertTrue(r.getBody().contains("UP"));
    }
}
~~~

Các tests dùng `RANDOM_PORT` nên có HTTP socket thật và không tranh cổng 8080. Chúng xác minh endpoint, config version marker, validation và readiness **trước shutdown**.

**Không khẳng định JUnit trên đã kiểm graceful shutdown.** Nó không gửi SIGTERM vào một JVM process đang có request kéo dài. Cần process-level và Pod-level tests ở các mục sau để chứng minh thay phiên bản/drain.

Chạy:

~~~bash
mvn clean verify
~~~

Khi Java17/Maven và dependencies tương thích, Maven phải build JAR:

~~~text
target/rolling-drain-lab-0.0.1-SNAPSHOT.jar
~~~

Kiểm test count/nội dung bằng Maven Surefire report thực, không giả lập transcript cố định.

## 13. Test local SIGTERM trước khi dùng Kubernetes

Mục tiêu: **request 8 giây đã vào controller trước TERM**, sau TERM Tomcat ngừng nhận mới, request cũ có cơ hội hoàn tất trong shutdown phase 25s.

Chạy JAR local trong Linux/WSL/macOS terminal:

~~~bash
java -jar target/rolling-drain-lab-0.0.1-SNAPSHOT.jar
~~~

Terminal khác:

~~~bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/api/info
curl -i "http://localhost:8080/api/slow?waitMs=200"
~~~

Để test TERM, **không chạy server trùng cổng** ở terminal khác. Dùng script Bash từ thư mục gốc (lệnh đây là **script độc lập chạy local**, không phải phần ứng dụng Java):

~~~bash
#!/usr/bin/env bash
set -euo pipefail

JAR="target/rolling-drain-lab-0.0.1-SNAPSHOT.jar"
java -jar "$JAR" > rolling-drain.log 2>&1 &
APP_PID=$!

ready=false
for i in $(seq 1 45); do
    if curl -fsS "http://localhost:8080/readyz" \
            >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 1
done

if [ "$ready" != true ]; then
    echo "App not ready; inspect rolling-drain.log"
    kill -TERM "$APP_PID" 2>/dev/null || true
    exit 1
fi

curl -fsS --max-time 25 \
    "http://localhost:8080/api/slow?waitMs=8000" \
    > local-inflight.json &
CALL_PID=$!

# Xác nhận đúng instance đã nhận work, tránh race TERM quá sớm.
started=false
for i in $(seq 1 40); do
    if curl -fsS "http://localhost:8080/api/info" \
            2>/dev/null | grep -q '"active":1'; then
        started=true
        break
    fi
    sleep 0.2
done

if [ "$started" != true ]; then
    echo "Slow request was not observed active; do not claim PASS"
    kill -TERM "$APP_PID" 2>/dev/null || true
    wait "$CALL_PID" || true
    exit 1
fi

kill -TERM "$APP_PID"
echo "Attempt NEW request after TERM:"
curl -i --max-time 2 "http://localhost:8080/api/info" || true

wait "$CALL_PID"
cat local-inflight.json
echo
wait "$APP_PID" || true
tail -n 40 rolling-drain.log
~~~

Kỳ vọng:

- Curl đang chờ 8s nhận body `completed=true`, `release=v1` nếu client không disconnect.
- Logs có `slow-start`, `slow-done`, `slow-cleanup` trước `resources-destroying` nếu drain hoàn tất.
- Request **mới** sau TERM có thể báo connection refused/reset, hoặc có race ở ranh giới tín hiệu; không bắt buộc HTTP 503 trên Tomcat.
- Thời gian wall-clock shutdown phải nằm trong ngân sách đo thực tế, không đòi chính xác 25.000ms.
- Nếu script thấy `active=0` sau một request cũ do đụng cổng khác hoặc đã kết thúc quá sớm, test **không có giá trị**. Dọn process cũ, chắc cổng 8080 rảnh và chạy lại.

**Đừng dùng `kill -9` để test graceful**: SIGKILL không cho JVM chạy shutdown hooks. IDE Stop hoặc Windows Stop-Process có thể terminate khác Linux TERM; nên dùng Linux/WSL/container khi kiểm cơ chế signal.

## 14. Dockerfile với version marker và JVM nhận TERM

Tạo `Dockerfile`:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
COPY target/rolling-drain-lab-0.0.1-SNAPSHOT.jar app.jar

ARG RELEASE=v1
ENV APP_RELEASE=${RELEASE}

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Vì sao viết như vậy?**

- Exec-form `ENTRYPOINT` giúp `java` nhận signal stop trực tiếp với tư cách container process, tránh shell cha không forward TERM.
- `ARG RELEASE` sử dụng khi Docker build; `ENV APP_RELEASE` gắn marker version vào image. Khi build v2, ta chỉ đổi build arg/tag và `kubectl set image`.
- Image `eclipse-temurin:17-jre` thông thường có `/bin/sh`/`sleep` để dùng preStop trong lab. Nếu dùng distroless, hook exec phải được thiết kế khác.
- Không tự chạy Java bằng `sh -c "java -jar ... &"` khiến shell không chờ child hoặc không forward TERM.

Build hai phiên bản từ cùng một source cho mục đích học:

~~~bash
mvn clean package
docker build --build-arg RELEASE=v1 \
    -t rolling-drain-lab:v1 .

docker build --build-arg RELEASE=v2 \
    -t rolling-drain-lab:v2 .
~~~

Hai images dùng **cùng code** nhưng marker khác. Trong rollout production thực tế v2 có code/schema behavior mới; lab dùng marker để cô lập vấn đề deploy/drain khỏi application compatibility.

Nếu bạn có một cluster kind tên mặc định `kind`:

~~~bash
kind load docker-image rolling-drain-lab:v1
kind load docker-image rolling-drain-lab:v2
~~~

Với minikube/remote cluster hoặc containerd runtime khác, phải dùng image registry/loader phù hợp. Không giả định image laptop tự tồn tại trên Kubernetes nodes. Không push image lab vào production registry nếu chưa được cấp quyền.

### Docker stop test thay cho Kubernetes

~~~bash
docker run -d --rm --name rolling-drain-local \
  -p 8080:8080 rolling-drain-lab:v1

# Terminal A: request còn đang xử lý:
curl -i "http://localhost:8080/api/slow?waitMs=8000"

# Terminal B: khi request đã vào app:
docker stop -t 40 rolling-drain-local
~~~

Hai terminals phải chạy **đồng thời**; stop sau khi curl đã xong không chứng minh drain. `docker stop -t 40` cho 40 giây trước force kill, đủ hơn phase 25s cho lab. Nếu Docker stop signal đã bị custom thành signal khác, kiểm image/runtime configuration.

## 15. Kubernetes Service: một địa chỉ ổn định qua nhiều Pods

Tạo `k8s/service.yaml`:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: rolling-drain-lab
spec:
  type: ClusterIP
  selector:
    app: rolling-drain-lab
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

`Service` chọn các Pods có label `app: rolling-drain-lab`, cung cấp DNS nội bộ `rolling-drain-lab` trong namespace tương ứng. Port Service 80 ánh xạ port container 8080.

**Không cần sửa Service selector giữa v1 và v2** khi dùng một Deployment rolling update. Pods cũ và mới có cùng app label; readiness/EndpointSlice và Deployment strategy điều phối những endpoints có thể nhận new traffic. Nếu triển khai blue-green thực sự cần hai Deployments/selectors hoặc traffic switching policy riêng — đó là một chiến lược khác.

## 16. Kubernetes Deployment: rolling update có giới hạn availability

Tạo `k8s/deployment.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rolling-drain-lab
spec:
  replicas: 3
  revisionHistoryLimit: 4
  minReadySeconds: 5
  progressDeadlineSeconds: 240

  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0

  selector:
    matchLabels:
      app: rolling-drain-lab

  template:
    metadata:
      labels:
        app: rolling-drain-lab
    spec:
      terminationGracePeriodSeconds: 60

      containers:
        - name: app
          image: rolling-drain-lab:v1
          imagePullPolicy: IfNotPresent

          ports:
            - name: http
              containerPort: 8080

          env:
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name

          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 2

          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
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
                command: ["/bin/sh", "-c", "sleep 5"]

          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
~~~

### Đọc Deployment đúng cách

- `replicas: 3`: mong muốn 3 Pods có thể phục vụ, chứ không chỉ một JVM đơn lẻ.
- `maxSurge: 1`: Deployment có thể tạo thêm một Pod mới trong rollout (trong giới hạn controller), giúp không cần hạ Pod cũ ngay để lấy capacity.
- `maxUnavailable: 0`: giới hạn số unavailable Pods trong rolling update theo desired replicas; **không bảo đảm** có capacity tài nguyên, ingress route đúng hoặc không xảy ra 5xx.
- `minReadySeconds: 5`: Pod phải liên tục Ready trong một khoảng trước khi được xem là Available cho tiến trình rollout; đây không phải thời gian drain.
- `progressDeadlineSeconds: 240`: nếu rollout không tiến triển đủ, controller báo `ProgressDeadlineExceeded`; không tự đảm bảo rollback hay chữa lỗi.
- `terminationGracePeriodSeconds: 60`: budget tổng cho termination, tính cả preStop.
- `preStop sleep 5`: chỉ để lab hóa route convergence; **không bắt buộc**, hãy đo trước khi dùng production.
- `readinessProbe` kiểm `/readyz`, **livenessProbe** kiểm `/livez`, **startupProbe** cho khoảng startup có kiểm soát. Tách mục đích, tránh readiness thất bại kéo theo restart.
- `POD_NAME` lấy bằng Downward API; app phản ánh chính tên Pod.
- `resources` là con số minh họa, phải sizing dựa trên traffic/GC/threads/memory footprint thật.
- `imagePullPolicy: IfNotPresent` cho phép chạy local kind image đã load; đừng dùng cùng mutable tag cho nhiều builds production không có digest tracking.

Trong YAML lab không cấu hình một management port khác; Actuator readiness/liveness additional paths chạy trên port 8080. Nếu thêm Spring Security, phải cho Kubelet health probes đi qua chính sách phù hợp mà không mở các actuator endpoints nhạy cảm.

## 17. Triển khai v1 và kiểm tra baseline

Sau khi đã build/load image v1 vào cluster lab:

~~~bash
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/deployment.yaml

kubectl rollout status deployment/rolling-drain-lab \
    --timeout=240s

kubectl get deployment rolling-drain-lab
kubectl get pods -l app=rolling-drain-lab -o wide
kubectl get endpointslices \
    -l kubernetes.io/service-name=rolling-drain-lab
~~~

Bạn cần thấy 3 Pods ready/available theo Deployment. Nếu Pod đang `ImagePullBackOff`, kiểm image tag và cluster loader; nếu `CrashLoopBackOff`, đọc startup logs. Nếu readiness không bao giờ UP, xem `/readyz`, `startupProbe`, port mapping và `application.properties`.

### Smoke test qua Service

Một cách tiện để người học dùng curl laptop là **port-forward** tới Service:

~~~bash
kubectl port-forward service/rolling-drain-lab 8080:80
~~~

Terminal khác:

~~~bash
curl -i http://localhost:8080/api/info
curl -i "http://localhost:8080/api/slow?waitMs=300"
~~~

`kubectl port-forward service/...` phù hợp để kiểm API, **không phải một load balancer performance/availability test**. Port-forward tới Service có thể được thực hiện qua một Pod được chọn; khi Pod đó biến mất, port-forward session cũng có thể đứt. Không dùng request qua port-forward rồi kết luận Service đã bị downtime trong rollout; cần in-cluster client truy cập DNS Service, hoặc ingress thật.

### Kiểm Pod version qua logs

~~~bash
kubectl logs deployment/rolling-drain-lab --tail=30
kubectl get pods -l app=rolling-drain-lab -o wide
~~~

Với nhiều replicas, `kubectl logs deployment/...` có thể chọn một Pod; khi cần logs của Pod cụ thể, dùng `kubectl logs pod/NAME` và correlation theo `instance`/`callId`. Đừng gộp log nhiều Pods không có nhãn rồi suy ra request đã chuyển nơi xử lý.

## 18. Phép thử 1 — Pod cũ nhận TERM khi request đang chạy

**Đây là bài test quan trọng nhất để chứng minh graceful**, tách khỏi timing bất định của image rollout. Ta sẽ khởi động request trực tiếp tới **Pod IP** từ một debug Pod, xác nhận request đang active, rồi xóa đúng Pod đó. ReplicaSet sẽ tạo replacement, nhưng request đã nhận vẫn gắn với old Pod nếu drain thành công.

### 18.1. Tạo debug client trong cluster lab

~~~bash
kubectl run drain-client \
  --image=curlimages/curl:8.11.1 \
  --restart=Never \
  --command -- sleep 3600

kubectl wait --for=condition=Ready pod/drain-client \
  --timeout=120s
~~~

Image minh họa `curlimages/curl:8.11.1` cần cluster pull được; nếu không hãy dùng debug image được phép trong môi trường lab. Pod chỉ chạy tạm, có `curl` để gọi Service/Pod IP trong cluster.

### 18.2. Chọn một Pod v1 và lấy Pod IP

~~~bash
OLD_POD=$(kubectl get pods \
  -l app=rolling-drain-lab \
  -o jsonpath='{.items[0].metadata.name}')

OLD_IP=$(kubectl get pod "$OLD_POD" \
  -o jsonpath='{.status.podIP}')

echo "Testing pod: $OLD_POD / $OLD_IP"
~~~

Đảm bảo `OLD_POD` đang Running/Ready và là v1. Nếu namespace có nhiều môi trường dùng cùng label, chạy lệnh trong namespace lab chính xác và giới hạn selector thích hợp.

### 18.3. Bắt đầu một request 12 giây trên Pod cũ

Chạy trong terminal Bash:

~~~bash
kubectl exec drain-client -- \
  curl -fsS --max-time 30 \
  "http://$OLD_IP:8080/api/slow?waitMs=12000" \
  > pod-inflight.json &
CALL_PID=$!
~~~

Request đến **Pod IP trực tiếp**, không đi qua Service load balancing. Đây là lựa chọn có chủ đích để giữ đúng destination khi Kubernetes rút endpoint khỏi Service; nó **không** phải cách clients production nên gọi Pods.

### 18.4. Bắt buộc xác nhận request đã vào controller

~~~bash
seen=false

for i in $(seq 1 40); do
  if kubectl exec drain-client -- \
       curl -fsS --max-time 2 \
       "http://$OLD_IP:8080/api/info" \
       | grep -q '"active":1'; then
    seen=true
    break
  fi
  sleep 0.2
done

if [ "$seen" != true ]; then
  echo "Slow request was not confirmed active; test inconclusive"
else
  echo "Confirmed in-flight request on $OLD_POD"
fi
~~~

Đừng phát `kubectl delete pod` nếu chưa xác nhận `active:1`, vì khi curl chạy chậm do cluster chưa ready hoặc request bị route sai, xóa Pod trước request sẽ chỉ kiểm refusal — **không chứng minh in-flight drain**.

### 18.5. Xóa đúng Pod đã nhận request

Chỉ sau khi xác nhận `seen=true`:

~~~bash
kubectl delete pod "$OLD_POD" --wait=false

kubectl get pods -l app=rolling-drain-lab -w
~~~

Lệnh `--wait=false` trả về mà không chờ Pod biến mất; container sẽ đi qua terminating lifecycle theo grace period. Trong lab, `preStop sleep 5` chạy trước TERM, rồi Boot có 25s phase graceful để hoàn tất request cũ. Nếu request còn chạy ~12s tổng, khi TERM thực sự tới, thường nó vẫn nằm trong budget (nhưng timing scheduler/cluster còn ảnh hưởng).

Terminal đang giữ `CALL_PID`:

~~~bash
wait "$CALL_PID"
cat pod-inflight.json
echo
~~~

**Kết quả nghiệm thu khi PASS:** curl từ debug Pod nhận HTTP 200 và body có `"release":"v1"`, `"completed":true`; log Pod cũ có `slow-start`, `slow-done`, `slow-cleanup` trước cleanup/exit khi thu được logs. Một Pod replacement được tạo bởi ReplicaSet mà không cần thay Service selector.

**Kết quả FAIL hoặc inconclusive:**

- Curl mất kết nối/exit nonzero: xem thời điểm TERM, `preStop`, grace period, OOMKill, pod networking, direct-IP routing, client timeout, exceptions.
- Request đã kết thúc **trước khi Pod thực sự nhận TERM**: vẫn là request hoàn tất, nhưng **chưa phải bằng chứng Spring graceful drain**. Đối chiếu timestamp logs và Pod termination events; lặp test với request dài hơn trong giới hạn 20s hoặc hạ preStop trong lab.
- Pod không được xóa hoặc debug Pod mất connection vì API server/exec session: không gán lỗi cho graceful Boot khi chưa đủ dấu vết.
- Pod đã mất, không còn logs: cần central log collector hoặc thu logs bằng `kubectl logs` khi Pod còn tồn tại; Kubernetes không đảm bảo có thể lấy logs từ Pod đã bị xóa.

### 18.6. Đối chiếu EndpointSlice

Trong lúc Pod terminating, có thể chạy:

~~~bash
kubectl get endpointslices \
  -l kubernetes.io/service-name=rolling-drain-lab \
  -o yaml
~~~

Tìm endpoint conditions `ready`, `serving`, `terminating` của old Pod, và endpoints của replicas còn ready. Endpoint có thể bị remove nhanh nên không chắc bạn thấy đủ trạng thái trong mỗi lần truy vấn. Cần logs/events/metrics để tránh suy luận sai từ snapshot.

**Cần phân biệt:** Pod terminating có thể vẫn đang **serving một request cũ** trong khi `ready=false` để Service ngừng chọn cho traffic mới. Đây là mô hình đúng, không phải contradiction.

## 19. Phép thử 2 — Rolling update thực sự từ v1 lên v2

Sau khi thử xóa Pod và ReplicaSet đã thay đủ 3 Pods v1 ready, hãy chuyển sang rollout image mới.

### 19.1. Chắc chắn v2 đã có trên các nodes

~~~bash
docker build --build-arg RELEASE=v2 \
  -t rolling-drain-lab:v2 .

kind load docker-image rolling-drain-lab:v2
~~~

Nếu dùng cluster không phải kind, push v2 lên registry đã cấu hình và chỉnh image phù hợp. Kết quả mong đợi là **new image chứa `APP_RELEASE=v2`**.

### 19.2. Update Deployment bằng một thay đổi image

~~~bash
kubectl set image deployment/rolling-drain-lab \
  app=rolling-drain-lab:v2

kubectl rollout status deployment/rolling-drain-lab \
  --timeout=240s
~~~

Chỉ **một mutation image** tạo rollout. Không chạy thêm một `kubectl set env APP_RELEASE=v2`, vì image đã chứa marker v2; nếu thay cả env riêng có thể kích hoạt rollout khác.

### 19.3. Theo dõi rollout

~~~bash
kubectl get pods -l app=rolling-drain-lab -w
kubectl describe deployment rolling-drain-lab
kubectl rollout history deployment/rolling-drain-lab
kubectl get replicasets -l app=rolling-drain-lab
kubectl get endpointslices \
  -l kubernetes.io/service-name=rolling-drain-lab
~~~

Khi một Pod mới warmup và trở thành Ready/Available, Deployment có thể rút một Pod cũ; số Pods thực tế có thể tạm vượt 3 do surge và Pods terminating. Không coi trạng thái có cả v1 và v2 **giữa rollout** là lỗi; điều kiện quan trọng là Service tiếp tục có endpoints sẵn sàng và request không bị cắt ngoài budget.

### 19.4. Xác minh request mới sau rollout

Qua debug Pod dùng DNS Service:

~~~bash
kubectl exec drain-client -- \
  curl -fsS --max-time 5 \
  http://rolling-drain-lab/api/info
~~~

Sau khi rollout thành công và các Pods v1 cũ đã hết serving regular traffic, response phải chứa `"release":"v2"`. Nếu vẫn nhận v1 từ một Pod cũ, kiểm rollout status, stale clients/keepalive connections, Service endpoints, image cache, labels hoặc mutable tags.

**Không hứa** rằng mọi request đang chạy trên v1 trước khi rollout sẽ tự trả `v2`. Một request đã vào v1 vẫn phản ánh v1 cho đến khi hoàn thành/drain; đây là đúng.

## 20. Đo availability liên tục trong rolling update

Một request thành công trước và sau rollout chưa chứng minh giữa hai thời điểm không có gián đoạn. Cần một **load/smoke loop liên tục** qua Service, tốt nhất từ một **in-cluster client** hoặc ingress thật:

~~~bash
# Một terminal: 100 requests nối tiếp qua DNS Service.
for i in $(seq 1 100); do
  kubectl exec drain-client -- \
    curl -sS -f \
    -o /dev/null \
    -w "status=%{http_code} total=%{time_total}\n" \
    --max-time 3 \
    "http://rolling-drain-lab/api/info" \
    || echo "request-failed i=$i"
  sleep 0.1
done
~~~

Terminal khác kích hoạt rollout `v1 → v2` trong khi loop đang chạy. Kết quả:

- Trong rollout có thể thấy responses đến từ v1 hoặc v2, miễn SLO/compatibility giữ đúng.
- Khi rollout hoàn tất, responses mới phải tới v2.
- Nếu có 5xx, `curl` exit nonzero, connection reset hoặc timeout, phải điều tra. `kubectl exec` cũng có overhead/network dependencies riêng, nên đừng coi số liệu latency từ CLI exec là benchmark chính xác của service.
- Để đo p95/p99 latency và concurrency, dùng load generator chuyên dụng (k6, Gatling, hey, wrk, JMeter) ở staging được cấp quyền, với test profile/idempotent endpoints và limits an toàn.
- Test qua `kubectl port-forward Service` không phải phép đo ổn định vì port-forward session gắn với một Pod và có thể chết khi Pod được thay.

**Không chạy load test mạnh trực tiếp lên production nếu không có change/traffic budget được duyệt.** Bài lab ưu tiên single/low-rate requests để quan sát logic.

## 21. Vì sao zero downtime không tự đến từ maxUnavailable=0?

Giả sử cả ba Pods v1 đều đang ở CPU 90%, cluster không đủ capacity scheduling Pod v2, hoặc readiness v2 trả UP quá sớm trước khi cache warmup. Deployment `maxUnavailable=0` vẫn có thể tiến triển chậm, tắc hoặc gây lỗi người dùng nếu gateway route sai.

Những điều kiện quan trọng:

- **Replica count:** một replica không có buffer tốt cho rolling replacement; nhiều replicas giúp đạt availability.
- **Scheduler capacity:** có chỗ cho `maxSurge` Pod; nếu quota/affinity/anti-affinity/chênh lệch node cản, rollout kẹt.
- **Readiness correctness:** v2 phải sẵn sàng xử lý traffic thật khi probe UP, không chỉ JVM đã bind socket.
- **Startup time:** startupProbe/liveness không giết Pod trước khi boot xong.
- **Load balancer deregistration:** cũ bị rút khỏi routing khi terminating; external LB/ingress propagation cần đo.
- **Grace budget:** in-flight requests có deadline nhỏ hơn khoảng còn lại sau preStop/TERM.
- **Capacity shift:** khi cũ dừng, request chuyển sang Pods còn lại; nếu saturation, 5xx/latency có thể tăng.
- **Database compatibility:** v1/v2 cùng tồn tại trong rollout; schema/event format phải tương thích đồng thời.
- **Client retry:** lỗi ngắn hạn có thể xảy ra và client phải xử lý được nhưng không nhân side effects.
- **Long-lived connections:** WebSocket/HTTP2/SSE và uploads có lifetimes khác request JSON.

**maxUnavailable=0** là một ràng buộc của Deployment controller về số Pods Available, không phải chứng chỉ rằng **ingress không bao giờ trả 502**.

## 22. Lệnh rollback khi v2 gây lỗi

Nếu v2 bắt đầu trả 5xx, không ready, thậm chí rollout `ProgressDeadlineExceeded`, có thể cần quay lại ReplicaSet v1:

~~~bash
kubectl rollout history deployment/rolling-drain-lab

kubectl rollout undo deployment/rolling-drain-lab

kubectl rollout status deployment/rolling-drain-lab \
  --timeout=240s

kubectl get pods -l app=rolling-drain-lab
~~~

Rollback cũng là một **rolling update mới về old template**, với nguyên tắc drain tương tự. Nó không hoàn tác database schema/migration, queue messages hoặc transactions đã được v2 thực hiện. Nếu v2 có irreversible side effects, cần kế hoạch roll-forward/compensation riêng.

Trong hệ production, rollback theo revision cụ thể nếu cần, verify image digest và security compatibility trước khi chạy. Đừng xóa mọi Pods bằng `kubectl delete pods --all` để “rollback nhanh” vì có thể làm mất availability.

### Một chiến lược version/database compatibility

Trong rolling window, hai phiên bản có thể tồn tại song song:

~~~text
v1 writes schema old-compatible
v2 reads both old/new formats
migration expand columns (backward-compatible)
roll out v2
verify
later contract/remove old schema only when v1 gone
~~~

Đây là mô hình **expand-and-contract** cho database changes. Không đổi schema theo kiểu “v2 chạy thì xóa ngay cột v1 cần” khi vẫn còn in-flight requests v1.

## 23. Quan sát logs, trace và metrics để chứng minh drain

Để phân biệt thành công thực với trùng hợp timeline, cần ít nhất:

| Dữ liệu | Trả lời câu hỏi nào? |
|---|---|
| Pod name + release tag | Request đang chạy trên v1 hay v2? |
| `slow-start` timestamp + callId | Request đã được nhận trước TERM chưa? |
| `slow-done` + response status | Handler có hoàn tất không? |
| `slow-cleanup active=0` | In-flight count đã về 0 chưa? |
| Spring graceful shutdown started/completed | Drain có thực sự diễn ra? |
| `resources-destroying` | Cleanup xảy ra khi nào? |
| Pod deletionTimestamp/termination events | Kubernetes bắt đầu termination lúc nào? |
| EndpointSlice conditions | Pod còn trong routing regular traffic không? |
| Kubelet/container exit reason | Bị SIGKILL/OOMKill hay exit bình thường? |
| Ingress/LB access/error logs | 502/503/504, client disconnect, backend chosen |
| JVM/Tomcat threads, requests active | Có exhaustion/saturation không? |
| HTTP p95/p99, error rate | User-facing SLO bị ảnh hưởng không? |

`callId` UUID trong lab an toàn để correlate giữa start/done, nhưng không nên log request body, access token hoặc user PII vào production. Nếu cần distributed traces, dùng trace IDs do trusted ingress/tracer sinh ra và propagate theo policy.

### Xem Kubernetes events và logs

~~~bash
kubectl describe pod "$OLD_POD"
kubectl logs "$OLD_POD" --timestamps
kubectl get events --sort-by=.lastTimestamp
kubectl get pods -l app=rolling-drain-lab -o wide
~~~

Các lệnh liên quan old Pod chỉ hoạt động **khi Pod còn tồn tại**; sau deletion có thể không truy xuất logs được từ kubectl. Dùng centralized logging/metrics để làm bằng chứng lâu dài. `kubectl get events` có thể nhiều kết quả, nên trong production nên giới hạn namespace/selector và retention policy phù hợp.

### Thời gian không đồng nghĩa status code

- **NGINX 499** thường là client đóng connection trước response; không phải chuẩn HTTP code mà browser nhận.
- **502** thường do gateway không nhận được upstream response hợp lệ, reset hoặc protocol issue.
- **503** có thể do Service hết ready endpoints, ứng dụng báo unavailable, hoặc Undertow graceful.
- **504** thường do gateway chờ upstream quá timeout; Spring app cũng có thể chủ động trả 504 khi downstream chậm.
- **curl exit 28** nghĩa client timeout, có thể không nhận HTTP status nào.
- Tomcat khi graceful có thể từ chối network connection mới thay vì trả HTTP 503.

Chỉ nhìn một HTTP status không đủ xác định owner. Cần correlation logs ở client, ingress, Spring Boot và backend.

## 24. Graceful không có nghĩa mọi yêu cầu được bảo đảm thành công

Các tình huống cần xử lý riêng:

### 24.1. Request vượt shutdown phase

Một request 60 giây trong khi Spring graceful phase 25s có thể bị cắt; không nên tuyên bố `server.shutdown=graceful` sẽ giữ nó mãi. Cần business deadline, retry/idempotency hoặc tách asynchronous job.

### 24.2. Client đã disconnect trước khi handler xong

Một request có thể vẫn chạy và commit DB trong khi browser timeout/cancel. Log `slow-done` không chắc client đã nhận response. Khi retry POST, có thể tạo duplicate. Dùng idempotency key, unique constraints và reconciliation API.

### 24.3. SSE, WebSocket, HTTP/2, long polling

SSE/WebSocket có thể sống lâu hơn cả grace period. Cần heartbeat, max lifetime, message resume IDs, reconnect/close strategy; HTTP/2 có multiplexing/GOAWAY semantics. Không lấy test Servlet MVC 12s và coi WebSocket 2 giờ đã an toàn khi rolling update.

### 24.4. Upload/download lớn

File transfer dài có thể còn khi Pod terminating. Cần resumable uploads, chunking, object storage direct transfer và client retry policy; không nâng grace vô hạn cho mọi API chỉ để hỗ trợ một route.

### 24.5. Background jobs và consumers

`server.shutdown=graceful` chủ yếu bảo vệ HTTP in-flight. `@Scheduled`, `@Async`, Kafka/Rabbit/JMS consumers, Quartz, DB transactions, custom threads có lifecycle riêng. Cần stop accepting new jobs, finish/ack/commit/cancel theo deadline, `SmartLifecycle`/executor policies, message redelivery/idempotency. Không đợi background work bằng `@PreDestroy Thread.sleep(60000)` không có metrics/ownership.

### 24.6. Connection keepalive và stale routes

Một client có thể còn TCP keep-alive hoặc HTTP/2 stream tới Pod cũ; LB có thể còn route stale vài giây. Một request mới sau TERM có thể bị reset/refused ngay cả khi request cũ hoàn tất. Do đó preStop/network drain/retries cần phối hợp, và phải test đúng HTTP protocol.

### 24.7. Crash/OOM/SIGKILL

Graceful chỉ xảy ra khi context có cơ hội đóng bình thường. Power loss, kernel OOM, `kill -9` hoặc container SIGKILL khi hết grace sẽ phá guarantee. Business consistency phải chịu được **unexpected termination**.

## 25. Các lỗi thường gặp khi rollout

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm/sửa |
|---|---|---|
| Curl in-flight bị reset khi TERM | Boot 3.3 chưa bật graceful; JVM không nhận TERM; timeout quá ngắn | Kiểm property, image ENTRYPOINT, logs và budgets |
| Pod v1 vẫn nhận new traffic nhiều giây | LB/ingress propagation chậm, stale keepalive, Service route policy | EndpointSlice, ingress logs, đo preStop/drain |
| 502 tăng sau rollout | Gateway gửi tới Pod đã đóng listener | Check endpoint deregistration, LB stale routes |
| 503 tăng khi Pod mới chưa ready | Không đủ ready endpoints, readiness sai, capacity thấp | maxSurge/maxUnavailable, startupProbe, HPA |
| 504 tăng | App/downstream chậm hơn gateway idle/total timeout | Trace critical path, timeouts theo hop |
| `ImagePullBackOff` | Image chưa load/push/registry auth | kind load docker-image hoặc registry credentials |
| `CrashLoopBackOff` | Startup lỗi config/port/heap | kubectl logs/describe, JVM errors |
| Rollout không complete | Pod mới không Available, quota/affinity/capacity | Deployment conditions, events, readiness |
| app log chưa có graceful | Không bật property, JVM không nhận TERM, image launcher sai | Boot 3.3 property, PID 1 và stop signal |
| `@PreDestroy` log trước slow-done | Request không ở đúng Pod, phase timeout hoặc lifecycle bất thường | callId/pod, timestamps, active metrics |
| Port-forward đứt khi Pod bị xóa | Port-forward phụ thuộc Pod được chọn | Dùng in-cluster Service request cho availability |
| Request hoàn thành trước khi Pod TERM | Test không overlap drain thật | So timestamps, tăng work trong giới hạn |
| CPU tăng/latency tăng giữa rollout | Pods còn lại quá tải, cold caches | Replica count, warmup, surge, load tests |
| Liveness fail khi readiness fail | Health probes nhầm mục đích | Dùng /livez riêng, không phụ thuộc DB chập chờn |
| preStop ăn hết grace | Hook quá lâu; TERM đến muộn | Chia lại termination budget |
| Sigkill trước cleanup | Pod grace nhỏ hơn preStop + phases | Tăng grace dựa trên đo hoặc rút ngắn work |
| v2 release marker vẫn v1 | Quên Docker build arg/image cache/tag | Image digest/ENV, rollout history, Pod describe |
| v2 lỗi schema với v1 in-flight | Migration không backward-compatible | Expand-contract, rollback plan |
| Duplicate POST khi client retry | Timeout sau DB commit nhưng trước response | Idempotency key và operation-status lookup |

**Cách điều tra đúng:** xem user-facing symptom → xác định gateway/app/client owner → đối chiếu Pod/EndpointSlice timeline → xác định grace/timeout/hard kill → kiểm active work và side effects → sửa đúng tầng → thử lại. Không tăng tất cả timeouts và xoá health probes để “làm rollout xanh”.

## 26. Ma trận kiểm thử tổng hợp

| Trường hợp | Cách test | Điều cần chứng minh |
|---|---|---|
| v1 baseline | apply Deployment/Service | 3 ready Pods, /info release v1 |
| Readiness khi startup | /readyz + startupProbe | Chỉ route khi app thực sự ready |
| Local SIGTERM | In-flight 8s + kill -TERM | Request cũ hoàn tất trước context exit |
| New connection sau TERM | curl /info tới same process | Không nhận work mới; có thể refused/reset |
| Pod deletion có in-flight | Call Pod IP 12s, confirm active, delete Pod | Body v1 200 nếu đủ drain, logs correlate |
| Terminating EndpointSlice | get endpointslices -o yaml | ready=false và terminating=true khi quan sát được |
| Replica replacement | delete one Pod | ReplicaSet tạo Pod mới ready |
| Rolling v1→v2 | set image v2 | Deployment rollout complete |
| Availability trong rollout | in-cluster Service curl loop | Error rate nằm trong budget |
| Post-rollout | Service /info | release v2 |
| Readiness v2 fail | Simulate unsafe image/config ở lab | Rollout không được tự coi succeeded |
| Rollback v2→v1 | rollout undo | Có thể phục hồi healthy image |
| Tiny termination grace | Thử trong staging có kiểm soát | Nhận diện SIGKILL/unfinished work |
| Long request > phase | Work lớn hơn giới hạn trong lab mở rộng | Không hứa thành công vô hạn |
| Client abort giữa POST | Idempotent test double | Không duplicate mutation |
| Background worker | Stop/cancel/ack test | HTTP graceful không thay worker cleanup |
| SSE/WebSocket/HTTP2 | Protocol-aware clients | Reconnect/drain đúng policy |
| External ingress | Real HTTPS user path | Không duplicate routing errors |
| Resource pressure | Load/scheduler constraints | Đo stalls/5xx, không suy từ YAML |

**Không dùng chính script có `kubectl delete pod` trên production** khi không có change window, người chịu trách nhiệm, rollback và traffic budget. Cluster lab/staging là nơi đúng để thực hiện fault injection.

## 27. Anti-pattern và cách tránh

| Sai lầm | Lý do sai | Hướng tốt |
|---|---|---|
| Quên `server.shutdown=graceful` trên Boot 3.3 | Web server có thể dừng tức thời | Bật explicit và kiểm TERM |
| `maxUnavailable=0` được coi là zero-downtime guarantee | LB/errors/capacity nằm ngoài Deployment constraint | End-to-end SLO tests |
| Gửi SIGKILL để test graceful | SIGKILL không thực hiện shutdown callbacks | SIGTERM/process-level test |
| Docker shell-form entrypoint không forward TERM | JVM không được báo dừng | Exec-form ENTRYPOINT |
| preStop sleep 60s, grace 60s | Hết budget trước TERM | preStop là một phần grace |
| Đặt Spring phase 25s, Pod grace 25s | Không còn margin cho hook/cleanup | Đo tổng lifecycle, thêm buffer |
| @PreDestroy sleep để giữ request | Sai ownership, có thể deadlock | Built-in graceful web shutdown |
| Chỉ dùng readiness, không kiểm connector | Direct/stale clients vẫn có thể gửi requests | Traffic draining + server reject |
| Chỉ dừng connector mà không deregister | LB tiếp tục route đến Pod cũ | EndpointSlice/ingress routing |
| Liveness kiểm dependency DB chung | Outage có thể restart toàn cụm | Availability design đúng mục đích |
| Gọi /readyz qua management port khác | Management port có thể sống trong khi app port fail | Additional paths trên main port |
| Test qua port-forward Pod khi xóa Pod | Port-forward bị cắt dù app đang drain | In-cluster direct Pod IP cho drain test |
| Kết luận request đã được drain vì HTTP 200 | Request có thể xong trước TERM | So start/done/TERM timestamps |
| Tất cả new requests cần HTTP 503 | Tomcat có thể từ chối ở network | Kiểm no new accepts, không hardcode status |
| Đổi image và ENV thành hai updates | Có thể tạo hai rollouts | Build release marker vào image |
| Dùng image tag mutable không digest | Stale image gây nhầm version | Immutable tags/digests |
| Bỏ qua schema compatibility | v1/v2 chạy đồng thời | Expand-contract DB changes |
| Retry POST vô điều kiện | Duplicate side effects | Idempotency keys |
| Long SSE/WS không có lifetime | Hết drain window và disconnect | Reconnect/resume strategy |
| Xóa tất cả Pods để rollback | Làm mất availability | `rollout undo` có kiểm soát |

## 28. Kiểm tra khả năng mở rộng

**Cần biết trước khi production rollout:**

- **Application load:** average/peak RPS, p95/p99 tail latency và longest legitimate in-flight request; chọn budget dựa trên đo.
- **Concurrent requests:** active Servlet threads, queue, connection pool, JDBC acquisition, downstream rate limits; vì trong rollout số Pods đang phục vụ có thể thay đổi.
- **Cold start:** initialization, secrets, TLS, DB migrations, cache warmup; readiness chỉ UP khi service có khả năng nhận traffic.
- **Load balancer:** có hỗ trợ connection draining? Độ trễ xóa endpoints? Các LB có giữ HTTP/2 keepalive? DNS TTL? Proxy retries?
- **Pod/node disruption:** voluntary eviction/PDB policies, autoscaling, node drain, spot/preemptible nodes. PodDisruptionBudget hữu ích với một số voluntary disruptions, nhưng **không tự điều khiển Deployment rolling update** như maxUnavailable của chính Deployment strategy.
- **Graceful timeouts:** Spring lifecycle phase count/length, preStop, Pod termination, gateway total/request idle timeouts, client overall deadlines.
- **Business effects:** database transaction/callback, idempotency, queued events, distributed locks/leases, emails/payment processing.
- **Observability:** immutable release + pod labels, correlation IDs, readiness/termination spans, error rate theo version.
- **Rollback:** immutable revision/image, backward-compatible DB schema, rollback decision thresholds và on-call ownership.

Nếu một công việc cần 2 phút, thay vì tăng `terminationGracePeriodSeconds` tới 10 phút cho tất cả API Pods, nên cân nhắc **202 Accepted + durable job queue + status lookup**. Điều này tách lifetime request HTTP khỏi lifetime business job và giúp deploy linh hoạt.

## 29. Bài tập nâng cao

**Bài 1 — So dòng thời gian thật.** Thu timestamps `slow-start`, Pod deletionTimestamp, TERM, `slow-done` và `resources-destroying`. Chứng minh request thực sự overlap TERM; nếu không, lặp test và ghi là inconclusive.

**Bài 2 — Tắt graceful ở bản thử nghiệm.** Đặt `server.shutdown=immediate` trong một image lab riêng; so kết quả call dài và new connections. Không làm trên production để “so nhanh”.

**Bài 3 — Giảm Pod grace.** Thử `terminationGracePeriodSeconds: 5` trong môi trường riêng, với preStop 5s và request 12s; quan sát kết quả và giải thích vì sao đây không phải một hệ thống an toàn.

**Bài 4 — Đánh giá readiness đúng.** Thêm mock warmup phase: Pod bind port trước khi hoàn thành cache init. Đừng mở readiness sớm; test Pod không nhận traffic thật trước khi warmup xong.

**Bài 5 — Hạ replica count.** So một replica và ba replicas khi maxUnavailable=0, maxSurge=1 dưới cùng RPS. Đo p99/5xx và scheduling failures.

**Bài 6 — Mô phỏng external LB delay.** Dùng ingress lab có controller logs, đo số request tới old Pod sau khi EndpointSlice ready=false. Quyết định có cần preStop 5s hay không.

**Bài 7 — Version mismatch.** Thêm một response field ở v2 nhưng giữ clients v1/v2-compatible. Thử schema expand-contract, không drop cột DB cũ trong khi v1 còn serving.

**Bài 8 — Long stream.** Tạo SSE route có heartbeat và max lifetime; xem graceful phase 25s tác động ra sao, thiết kế client reconnect/EventSource last-event-id phù hợp.

**Bài 9 — Idempotent POST.** Mô phỏng POST commit vào database rồi client disconnect trước response; dùng idempotency key để ngăn duplicate khi client retry sang v2.

**Bài 10 — Fault injection.** Cho Pod v2 cố tình fail readiness trong lab. Kiểm Deployment không đánh dấu rollout thành công giả, quan sát ProgressDeadlineExceeded và thử rollback.

## 30. Câu hỏi tự kiểm tra có đáp án

**1. RollingUpdate có tự đợi một controller xử lý xong không?**  
Không. Kubernetes điều phối Pods/endpoints; Spring Boot graceful shutdown giúp old process chờ in-flight HTTP requests.

**2. Trên Spring Boot 3.3 cần bật property nào?**  
`server.shutdown=graceful`.

**3. `spring.lifecycle.timeout-per-shutdown-phase=25s` có chắc JVM dừng trong đúng 25s?**  
Không. Timeout theo lifecycle phase; còn preStop và other lifecycle phases/cleanup.

**4. preStop 5s có được cộng thêm ngoài terminationGracePeriodSeconds không?**  
Không. Nó ăn vào Pod termination grace.

**5. Pod Terminating có nhất thiết lập tức bị remove khỏi mọi load balancer?**  
Không. EndpointSlice ready=false cho traffic thường nhưng propagation bất đồng bộ.

**6. Vì sao không bắt buộc Tomcat trả HTTP 503 sau TERM?**  
Nó có thể dừng nhận tại network layer; client thấy connection refused/reset/EOF.

**7. Readiness=false có nghĩa Pod đã chết không?**  
Không. Nó có thể còn sống để hoàn tất request cũ.

**8. Liveness có nên fail khi app đang gracefully shutting down?**  
Không chỉ vì readiness refusing; điều đó có thể cắt drain sớm.

**9. Nếu một Pod v1 nhận request trước rollout, response có thể mang version v2 không?**  
Theo code lab, không: response được tạo bởi v1 ở Pod v1, trừ khi có một hệ thống proxy/chuyển logic ngoài ví dụ.

**10. Vì sao phải kiểm version marker trong image?**  
Để tránh nhầm build/cache/tag, và chỉ cần một image update cho rollout.

**11. Test HTTP 200 qua port-forward có chứng minh zero downtime không?**  
Không. Port-forward có thể phụ thuộc một Pod; cần in-cluster/ingress traffic liên tục.

**12. Tại sao thử delete Pod riêng trước rollout v1→v2?**  
Để chủ động làm request đang chạy overlap termination, không phụ thuộc timing của một rolling update dài ngắn khó đoán.

**13. Cái gì quyết định không cho Service chọn endpoint terminating cho new regular traffic?**  
EndpointSlice/Service dataplane cùng conditions như ready=false, nhưng còn propagation và LB-specific behavior.

**14. Kiểm gì để chứng minh request cũ hoàn thành trong drain?**  
Request start trước TERM, done sau TERM, HTTP 200/complete response, cùng callId/pod version và lifecycle logs.

**15. Vì sao một request có thể trả 200 nhưng test graceful vẫn inconclusive?**  
Nó có thể hoàn tất trước khi TERM đến; không chứng minh khả năng drain.

**16. `maxUnavailable: 0` có bảo đảm không lỗi HTTP nào trong rollout?**  
Không. Nó chỉ là availability constraint ở Deployment, không bao trùm gateway/network/capacity/DB.

**17. SIGKILL có chạy @PreDestroy không?**  
Không có bảo đảm; thường process dừng ngay không chạy Java cleanup.

**18. Tại sao dùng exec-form ENTRYPOINT?**  
Để JVM nhận stop signal phù hợp, tránh shell không forward TERM.

**19. Rollback v2→v1 có tự rollback database migration không?**  
Không. Schema/data compatibility phải được thiết kế riêng.

**20. Một request POST bị timeout phía client có an toàn để retry tùy ý không?**  
Không. Có thể DB đã commit; cần idempotency/status reconciliation.

**21. SSE hoặc WebSocket vô hạn có thể giữ Pod draining đến timeout không?**  
Có. Cần lifetime/close/reconnect protocol riêng.

**22. Khi thấy 503 ở rollout có chắc Spring Boot trả không?**  
Không. Có thể gateway không có ready backend hoặc một upstream layer trả 503.

**23. Nếu startup probe sai path có thể xảy ra gì?**  
Pod bị coi không khỏe, restart hoặc không có ready endpoint; cần dùng đúng /livez và /readyz config.

**24. Sau khi rollback, thông số nào cần kiểm?**  
Image/release, ready replicas, 5xx/p95/p99, security/DB compatibility, logs và tình trạng in-flight/queues.

## 31. Checklist nghiệm thu thực hành

- [ ] Maven build và JUnit smoke tests chạy trên Java 17+.
- [ ] `server.shutdown=graceful` được khai explicit cho Spring Boot 3.3.
- [ ] `spring.lifecycle.timeout-per-shutdown-phase` có giá trị và được tính vào Pod grace.
- [ ] Actuator `/livez` và `/readyz` hoạt động trên main app port.
- [ ] Docker exec ENTRYPOINT nhận TERM.
- [ ] Image v1 và v2 khác nhau ở immutable release marker.
- [ ] Cluster lab đã load/pull được image tags; không có ImagePullBackOff.
- [ ] 3 Pods v1 Ready, Service/Deployment labels/selectors khớp.
- [ ] maxSurge=1, maxUnavailable=0, minReadySeconds được hiểu đúng.
- [ ] Pod terminationGracePeriodSeconds tính cả preStop.
- [ ] Request /api/slow đã active **trước** khi xóa đúng old Pod.
- [ ] Nếu claim graceful PASS, logs chứng minh slow-done **sau TERM** và trước exit.
- [ ] Curl từ debug Pod tới old Pod IP nhận completed=true nếu còn trong drain budget.
- [ ] EndpointSlice terminating ready=false được kiểm khi quan sát được.
- [ ] ReplicaSet tạo replacement Pod Ready sau khi xóa old Pod.
- [ ] Rolling update v1→v2 diễn ra bằng một image update.
- [ ] In-cluster Service curl loop không có unexpected 5xx/connection failures ngoài budget.
- [ ] Sau rollout hoàn tất, /api/info mới trả v2.
- [ ] Lỗi rollout có thể rollback và không làm hỏng DB/state compatibility.
- [ ] Không dùng port-forward gắn Pod làm bằng chứng availability toàn Service.
- [ ] Không dùng load test nguy hiểm trên cluster production.
- [ ] Có metrics/logs cho release, Pod, in-flight, TERM/drain, errors và rollback.

## 32. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 – Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase` và server-specific rejection behavior.
- [Spring Boot 3.3 – Actuator Endpoints/Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): ApplicationAvailability, readiness/liveness health groups, `add-additional-paths`, `/livez`/`/readyz`.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): graceful, lifecycle, actuator health và server properties.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Servlet Tomcat/Reactor Netty/Jetty/Undertow configuration.
- [Spring Framework – Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): SmartLifecycle, bean destruction và @PreDestroy.
- [Kubernetes – Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate, maxSurge, maxUnavailable, minReadySeconds, progressDeadlineSeconds.
- [Kubernetes – Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): Terminating, preStop, SIGTERM/SIGKILL và shared terminationGracePeriodSeconds.
- [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): ready, serving, terminating conditions.
- [Kubernetes – Explore Termination Behavior](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/): observation of Pod/EndpointSlice draining.
- [Kubernetes – Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): preStop timing.
- [Kubernetes – Health Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): readiness, liveness, startup probing.
- [Kubernetes – Service](https://kubernetes.io/docs/concepts/services-networking/service/): DNS/ClusterIP và endpoint routing.
- [Docker – Dockerfile ENTRYPOINT](https://docs.docker.com/reference/dockerfile/#entrypoint): exec form và signal forwarding.
- [Docker – docker container stop](https://docs.docker.com/reference/cli/docker/container/stop/): TERM/timeout behavior.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): 502/503/504 status semantics.

**Kết luận:** Một rollout thành công không chỉ là image v2 đạt Ready. Cần bảo đảm **request mới được route tới Pods đang sẵn sàng**, **request cũ đã tới v1 được hoàn tất trong giới hạn** và **cả hai phiên bản có thể cùng tồn tại tạm thời**. Spring Boot graceful shutdown, Kubernetes EndpointSlice/readiness, Pod termination grace, rolling strategy, logs và idempotency là các mảnh ghép khác nhau của cùng một bài toán.
