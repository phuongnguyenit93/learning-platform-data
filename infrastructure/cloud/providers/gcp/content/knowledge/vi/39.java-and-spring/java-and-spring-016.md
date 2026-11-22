# Graceful shutdown và xử lý tín hiệu kết thúc container

Một ứng dụng Java/Spring có thể đang xử lý HTTP request, ghi dữ liệu, xác nhận message hoặc đẩy log ra hệ thống giám sát đúng lúc nền tảng quyết định thay container. Nếu tiến trình bị dừng ngay lập tức, request có thể lỗi giữa chừng, transaction không hoàn tất, message bị xử lý lặp hoặc dữ liệu trong bộ nhớ chưa được ghi ra nơi lưu trữ bền vững.

**Graceful shutdown** là quá trình ngừng tiếp nhận công việc mới, cho công việc đang xử lý một khoảng thời gian hữu hạn để hoàn tất, giải phóng tài nguyên và kết thúc tiến trình có kiểm soát. Bài học thuộc chương **Java và Spring trên GCP**, trong module **CLOUD_PROVIDERS_GCP**. Kiến thức này giúp vận hành Spring Boot trên Cloud Run, Google Kubernetes Engine (GKE) và các môi trường container, đồng thời liên hệ với việc bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và chi phí trên Google Cloud.

Sau bài học, bạn có thể:

- Giải thích vai trò của `SIGTERM`, `SIGKILL`, PID 1 và shutdown hook trong container.
- Phân biệt giới hạn shutdown trên Cloud Run và GKE.
- Cấu hình Spring Boot để xử lý request còn chạy và dọn dẹp tài nguyên.
- Thiết kế readiness probe, preStop hook và termination grace period phù hợp.
- Đảm bảo background job, consumer, transaction và tác vụ gửi dữ liệu có khả năng bị gián đoạn an toàn.
- Kiểm thử, quan sát và xử lý lỗi khi triển khai hoặc scale down.

## 1. Vì sao container bị kết thúc?

Container không chạy vĩnh viễn. Các tình huống phổ biến gồm:

| Tình huống | Ví dụ trên Google Cloud | Rủi ro nếu dừng đột ngột |
|---|---|---|
| Phát hành phiên bản mới | Rolling update một Deployment trên GKE; thay revision Cloud Run | Request chưa trả lời, kết nối ngắt |
| Tự động co giãn | GKE giảm số Pod; Cloud Run thu hồi instance không còn cần thiết | Công việc nền chưa hoàn tất |
| Bảo trì hoặc thay node | GKE di chuyển workload, cập nhật node pool | Connection, lease hoặc lock chưa được giải phóng |
| Thay đổi cấu hình | Đổi environment variable, image hoặc resource | Một số bản ghi đang xử lý chưa được commit |
| Chủ động dừng | Docker stop, xóa Pod, dừng job | Tiến trình bị giết trước khi flush |
| Lỗi hoặc sự cố | OOM, node mất kết nối, SIGKILL cưỡng bức | Không có cơ hội chạy cleanup |

Graceful shutdown đặc biệt quan trọng trong các lần dừng có báo trước. Tuy nhiên, không phải lúc nào hệ thống cũng nhận được tín hiệu dừng. Khi node hỏng, container OOM hoặc bị kill cưỡng bức, cleanup có thể không chạy. Vì vậy **idempotency, transaction và cơ chế retry/checkpoint vẫn là yêu cầu bắt buộc** đối với công việc quan trọng.

## 2. Hiểu SIGTERM, SIGKILL và PID 1

Trên Linux, nền tảng container thường dùng signal để yêu cầu tiến trình kết thúc:

- **SIGTERM (15):** yêu cầu kết thúc có thể xử lý. JVM có thể bắt đầu shutdown sequence và chạy shutdown hooks.
- **SIGKILL (9):** kết thúc cưỡng bức, không thể bắt hoặc bỏ qua. Java không được đảm bảo chạy `finally`, `@PreDestroy` hoặc shutdown hook.
- **SIGINT (2):** thường xuất hiện khi nhấn Ctrl+C trong terminal; cũng có thể kích hoạt shutdown nhưng không phải tín hiệu mặc định của mọi nền tảng container.

Đối với container, tín hiệu được gửi đến tiến trình chính, thường là **PID 1**. Nếu PID 1 là một shell và Java chỉ là tiến trình con, shell có thể không chuyển SIGTERM cho Java. Ứng dụng sẽ không có cơ hội dọn dẹp trước khi bị cưỡng bức kết thúc.

~~~mermaid
sequenceDiagram
    participant P as Nền tảng container
    participant J as JVM / Spring Boot
    participant W as Workload
    P->>J: SIGTERM
    J->>W: Ngừng nhận công việc mới
    W-->>J: Hoàn thành phần việc đang chạy
    J->>J: Đóng ApplicationContext, cleanup
    alt Kết thúc trong thời hạn
        J-->>P: Process exit
    else Vượt thời hạn
        P->>J: SIGKILL
        Note over J: Cleanup còn lại không chạy
    end
~~~

### Dockerfile: để Java nhận được tín hiệu

Ưu tiên **exec form** cho `ENTRYPOINT`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/checkout-api.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ở ví dụ này, Java trở thành PID 1 của container. Khi nền tảng gửi SIGTERM, JVM nhận trực tiếp tín hiệu. Tùy môi trường, có thể dùng init process như `tini` để chuyển tín hiệu và thu hồi zombie processes nếu ứng dụng có nhiều tiến trình con.

Cẩn trọng với shell form:

~~~dockerfile
# Không khuyến nghị: shell có thể giữ PID 1 và không forward SIGTERM
ENTRYPOINT java -jar /app/app.jar
~~~

Nếu cần script khởi động, dòng cuối của script nên dùng `exec java -jar /app/app.jar` để thay thế shell bằng JVM. Không chỉ thêm `trap` trong shell mà bỏ qua việc forward tín hiệu và chờ child process.

### JVM và Spring có cần tự bắt SIGTERM?

Thông thường **không cần tự cài signal handler bằng API nội bộ của JDK**. Khi JVM nhận SIGTERM, quy trình shutdown thông thường chạy các JVM shutdown hook. Spring Boot đăng ký cơ chế đóng `ApplicationContext`, từ đó kích hoạt Spring lifecycle, graceful web-server shutdown và callback dọn dẹp bean.

Tự đăng ký nhiều hook hoặc gọi `System.exit(...)` bên trong hook dễ dẫn đến cạnh tranh, deadlock hoặc kết thúc trước khi cleanup xong. Chỉ viết logic quản lý signal đặc biệt khi ứng dụng có yêu cầu riêng và đã hiểu rõ vòng đời JVM.

## 3. Thứ tự shutdown mong muốn

Một tiến trình dừng có kiểm soát thường gồm:

1. **Thông báo ngừng nhận việc mới:** service dừng nhận request hoặc consumer ngừng lấy thêm message.
2. **Draining:** cho các request đang xử lý kết thúc trong khoảng thời gian hữu hạn.
3. **Hoàn tất hoặc checkpoint:** commit transaction, ghi trạng thái có thể khôi phục, thực hiện ack sau khi xử lý bền vững.
4. **Đóng tài nguyên:** connection pool, HTTP client, scheduler, executor, telemetry exporter.
5. **Thoát tiến trình:** trả mã thoát phù hợp trước hạn chót của nền tảng.

~~~mermaid
flowchart TD
    A["SIGTERM / yêu cầu ngừng"] --> B["Từ chối công việc mới"]
    B --> C["Draining request và background task"]
    C --> D{"Hoàn tất trước deadline?"}
    D -->|Có| E["Commit / ack / flush và đóng tài nguyên"]
    D -->|Không| F["Checkpoint hoặc để retry công việc dang dở"]
    E --> G["JVM exit"]
    F --> G
    G --> H["Nền tảng thu hồi container"]
~~~

Một ứng dụng không nên chờ mãi đến khi mọi request xong. Bản thân nền tảng có deadline; chờ vô hạn sẽ chỉ dẫn đến SIGKILL. Hãy chọn thời gian drain phù hợp với đặc điểm workload và vẫn chừa ngân sách cho các lifecycle phase khác.

## 4. Khác biệt giữa Cloud Run và GKE

| Khía cạnh | Cloud Run services | GKE / Kubernetes Pods |
|---|---|---|
| Tín hiệu dừng thông thường | SIGTERM đến các container trong instance | Kubelet yêu cầu runtime gửi TERM tới container |
| Thời gian trước cưỡng bức | 10 giây kể từ SIGTERM, sau đó SIGKILL | Mặc định 30 giây; cấu hình `terminationGracePeriodSeconds` |
| Khả năng điều chỉnh grace period | Không có Pod termination grace tùy chỉnh cho service | Có thể tăng/giảm trong Pod spec |
| Chuyển traffic | Nền tảng tự điều phối request; có thể ngừng instance dù còn request trong tình huống đặc biệt | EndpointSlice đánh dấu endpoint terminating, readiness false và điều phối theo Service/load balancer |
| preStop hook | Không dùng Kubernetes Pod lifecycle hook | Hỗ trợ `preStop`; thời gian hook nằm trong grace period |
| Cấu hình readiness | Startup/liveness và routing do Cloud Run quản lý | Readiness/liveness/startup probes khai báo trong Pod |
| Kiểm thử chủ động | Docker stop ở local; kiểm tra logs khi thay revision/scale down | Rolling update, xóa Pod trong staging và theo dõi events |

**Cloud Run:** tài liệu runtime contract hiện hành quy định Cloud Run gửi SIGTERM đến tất cả container trong instance, bắt đầu khoảng 10 giây trước SIGKILL. CPU vẫn được cấp trong giai đoạn này và thời gian đó được tính phí. Thông thường các request đang chạy được cho thời gian hoàn thành trước khi instance bị thu hồi; ngoại lệ có thể nhận SIGTERM trong khi request còn xử lý. Vì vậy, không nên hứa rằng một request dài luôn được chạy thêm đủ 10 giây. Ở first-generation execution environment, container không trap SIGTERM có thể bị dừng ngay; với second-generation, nên đảm bảo tiến trình xử lý signal đúng cách.

**GKE:** kubelet kích hoạt cơ chế terminate khi Pod bị xóa hoặc thay thế. `terminationGracePeriodSeconds` có giá trị mặc định 30. Nếu có `preStop`, hook chạy trước TERM và **dùng chung** khoảng thời gian này; khi hết hạn, container còn chạy sẽ bị SIGKILL. Việc một Pod chuyển sang `Terminating` hoặc readiness false không đồng nghĩa tất cả proxy/load balancer đã cập nhật ngay tức khắc.

### Phân biệt Cloud Run service, job và worker pool

Cloud Run **service** nhận request HTTP/gRPC. Cloud Run **job** chạy các task hữu hạn; khi task vượt timeout hoặc bị hủy, nó nhận SIGTERM và khoảng 10 giây trước SIGKILL. Với job, nên định kỳ ghi checkpoint và cho phép retry thay vì kỳ vọng flush toàn bộ công việc ở 10 giây cuối.

Cloud Run **worker pool** có vòng đời riêng, không tự scale về 0 vì idle theo cách service làm. Khi instance của worker pool bị shutdown, nó cũng nhận SIGTERM và khoảng 10 giây xử lý trước SIGKILL. Bộ xử lý message cần ngừng poll và khôi phục công việc được giao dở theo cơ chế của broker.

## 5. Cấu hình graceful shutdown trong Spring Boot

Spring Boot hỗ trợ graceful shutdown cho embedded web server trong ứng dụng Servlet và reactive. Ở các phiên bản Spring Boot mới, graceful shutdown có thể đã bật mặc định; một số phiên bản cũ cần bật tường minh. Để tài liệu cấu hình dễ kiểm soát khi nâng cấp, có thể khai báo rõ:

**application.yml**

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 8s
~~~

**application.properties** tương đương:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=8s
~~~

`spring.lifecycle.timeout-per-shutdown-phase` giới hạn **từng phase** của `SmartLifecycle`; nó không phải giới hạn tổng thời gian dừng container. Nếu có nhiều phase hoặc các bean cleanup chạy thêm, tổng thời gian có thể dài hơn. Đối với Cloud Run, chọn ngân sách nội bộ ngắn hơn 10 giây và kiểm tra thời gian thực tế; giá trị 8 giây ở trên chỉ là ví dụ, cần điều chỉnh với ứng dụng.

Khi `ApplicationContext` đóng, web server ngừng cho request mới vào và chờ request đang chạy theo timeout. Trên Tomcat, Jetty và Reactor Netty, việc ngừng chấp nhận request xảy ra ở tầng mạng; một số server/phiên bản khác có thể trả lỗi cho request mới. Connection keep-alive, streaming response, SSE và WebSocket cần được kiểm thử riêng, vì request giữ kết nối lâu có thể không kết thúc kịp deadline.

Graceful shutdown của web server không bảo đảm mọi background task tự hoàn thành. Cần quản lý thêm các component do ứng dụng tự tạo.

### Chọn timeout theo môi trường

Ví dụ tham khảo:

| Môi trường | Grace period của nền tảng | Cấu hình Spring gợi ý | Lưu ý |
|---|---|---|---|
| Cloud Run service | 10 giây | `timeout-per-shutdown-phase: 6s` | Chừa thời gian cho cleanup/flush, không có chỗ cho request rất dài |
| GKE deployment | 45 giây (tự đặt) | `timeout-per-shutdown-phase: 25s` | Nếu preStop 5s, vẫn còn khoảng trống cho giai đoạn khác |
| Local Docker | Tự chọn trong `docker stop -t` | 8–20 giây theo test | Cần đặt Docker timeout lớn hơn tổng thời gian cleanup |
| Cloud Run job | Khoảng 10 giây sau SIGTERM khi task bị hủy/timeout | Shutdown nhanh, checkpoint trước | Retry/idempotency mới là bảo vệ chính |

Các con số cấu hình là ví dụ. Khi thay đổi workload, đánh giá latency p95/p99, request timeout, thời gian commit, stop consumer và độ trễ flush để chọn ngân sách thực tế.

## 6. Dọn dẹp tài nguyên bằng @PreDestroy

Spring gọi callback hủy bean khi `ApplicationContext` đóng có trật tự. Với Spring Boot hiện đại dùng namespace Jakarta, có thể triển khai:

~~~java
package com.example.checkout;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class ShutdownCleanup {
    private static final Logger log =
        LoggerFactory.getLogger(ShutdownCleanup.class);

    @PreDestroy
    public void close() {
        long started = System.nanoTime();
        log.info("shutdown_cleanup_start");

        // Ví dụ: đóng một resource do bean sở hữu.
        // Không khởi động một tác vụ dài hoặc chờ vô hạn ở đây.
        // Một số resource Spring-managed đã có lifecycle tự động.

        long elapsedMs =
            (System.nanoTime() - started) / 1_000_000L;
        log.info("shutdown_cleanup_complete duration_ms={}", elapsedMs);
    }
}
~~~

Khi các bean đã có destroy method tự động (HikariCP, Kafka listener container, executor do Spring quản lý), không cần đóng lần hai bằng tay. `@PreDestroy` thích hợp cho cleanup ngắn và tài nguyên ứng dụng tự sở hữu, ví dụ đóng client riêng, xả buffer nhỏ hoặc giải phóng lock có thời hạn.

Lưu ý:

- Không đặt logic nghiệp vụ phải hoàn tất bằng mọi giá vào `@PreDestroy`: SIGKILL, OOM hoặc node failure có thể bỏ qua callback.
- Không chờ vô hạn, ngủ nhiều giây hoặc thực hiện lệnh mạng thiếu timeout.
- Cleanup nên **idempotent** để gọi lại không tạo lỗi và có thể xử lý trường hợp một phần tài nguyên đã đóng.
- Nếu đang dùng Spring Boot 2 với hệ namespace cũ, annotation có thể thuộc `javax.annotation.PreDestroy`; ví dụ trên dùng `jakarta.annotation.PreDestroy` cho các phiên bản Spring hiện đại.
- Khi cần điều phối start/stop component theo phase, cân nhắc `SmartLifecycle` thay vì nhét toàn bộ logic vào một destroy callback.

## 7. Quản lý background worker với SmartLifecycle

Giả sử ứng dụng dùng một `ExecutorService` riêng để thực hiện các tác vụ ngắn được gửi từ HTTP handler. Khi shutdown, cần ngừng nhận task mới, chờ task đang chạy trong thời hạn hữu hạn và sau đó kết thúc.

Ví dụ đơn giản có thể điều chỉnh theo nhu cầu thực tế:

~~~java
package com.example.checkout;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class BackgroundWork implements SmartLifecycle {
    private final ExecutorService executor =
        Executors.newFixedThreadPool(2);

    private final AtomicBoolean accepting = new AtomicBoolean(false);

    public boolean submit(Runnable work) {
        if (!accepting.get()) {
            return false;
        }
        try {
            executor.submit(work);
            return true;
        } catch (RejectedExecutionException rejected) {
            return false;
        }
    }

    @Override
    public void start() {
        accepting.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        accepting.set(false);
        executor.shutdown();
        try {
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            executor.shutdownNow();
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        stop(() -> {});
    }

    @Override
    public boolean isRunning() {
        return accepting.get();
    }
}
~~~

Điểm cần hiểu:

- `SmartLifecycle` cho phép Spring điều phối việc stop component theo lifecycle phase; `callback.run()` báo rằng thành phần đã dừng hoặc đã hoàn tất cố gắng dừng.
- Chặn task mới **trước** khi đóng executor và xử lý race qua `RejectedExecutionException`.
- `shutdown()` chờ các task đã nhận; `shutdownNow()` chỉ cố gắng interrupt, không bảo đảm ngắt được task đang block hoặc thực hiện I/O.
- Ví dụ giả định component chỉ có vòng đời khởi động một lần và dừng khi ứng dụng kết thúc. Nếu cần start lại trong cùng `ApplicationContext`, phải thiết kế lại executor để tạo mới sau khi stop.
- Đừng dùng executor trong ví dụ làm nơi lưu duy nhất của task quan trọng. Nếu JVM chết trước khi task được lưu bền vững, task sẽ mất. Dùng Cloud Tasks, Pub/Sub, broker có ack/redelivery hoặc một bảng outbox khi cần độ tin cậy.

Ở ứng dụng dùng `@Async` hoặc `@Scheduled`, hãy kiểm tra cấu hình shutdown của task executor/scheduler tương ứng; đừng mặc định mọi task đều được await. Với Kafka, RabbitMQ hoặc Pub/Sub, nên dùng lifecycle riêng của listener/client library để ngừng poll, xử lý commit/ack đúng thời điểm và đóng kết nối sạch.

## 8. Transaction, message và tác vụ dài khi shutdown

Giả sử một consumer xử lý message đặt hàng:

1. Nhận message từ Pub/Sub.
2. Ghi trạng thái đơn hàng vào database trong transaction.
3. Commit thành công.
4. Chỉ sau đó mới ack message.

Nếu nhận SIGTERM khi transaction chưa commit, consumer nên dừng nhận message mới; đối với message dang dở, có thể hoàn tất trong thời gian còn lại hoặc để broker redeliver. **Không ack trước khi dữ liệu được ghi bền vững.**

Vì message có thể được xử lý lại, logic cần idempotent theo message ID hoặc business key. Có thể dùng unique constraint, state machine hoặc outbox/inbox pattern; không chỉ dựa vào biến boolean trong RAM.

| Loại công việc | Cách xử lý khi shutdown | Tránh |
|---|---|---|
| HTTP request cập nhật dữ liệu | Để transaction hoàn tất trong deadline; trả trạng thái rõ ràng | Ghi một phần dữ liệu rồi trả success |
| Pub/Sub subscriber | Ngừng nhận message; ack sau commit; để redelivery nếu chưa hoàn tất | Ack ngay lúc nhận message |
| Kafka consumer | Ngừng poll; commit offset theo tiến độ bền vững; đóng consumer | Commit offset cho message chưa xử lý |
| Scheduled task | Ngừng phát task mới; checkpoint phần chưa hoàn thành | Phụ thuộc hoàn toàn vào thread trong RAM |
| Upload lớn hoặc stream dài | Chuyển sang object storage, resumable upload, chunk/checkpoint | Giữ request mở nhiều phút rồi hy vọng 10s để cleanup |
| Telemetry/log exporter | Flush có deadline; ưu tiên gửi bất đồng bộ trong lúc chạy | Đợi đến shutdown mới gửi toàn bộ log |

Với Cloud Run service, thread nền không được đảm bảo chạy liên tục khi không có request, tùy billing/CPU allocation. Nếu cần xử lý lâu và bền vững, hãy chuyển việc sang Cloud Tasks hoặc Cloud Run jobs với checkpoint, retry và định danh tác vụ rõ ràng.

## 9. GKE: readiness, preStop và thời gian terminate

Kubernetes đánh dấu endpoint của Pod đang terminate với `ready=false`, nhưng độ trễ cập nhật ở proxy hoặc load balancer vẫn có thể khiến một số kết nối hướng tới Pod cũ trong khoảng ngắn. Ứng dụng nên phối hợp readiness, termination grace period và logic dừng xử lý.

Spring Boot Actuator cung cấp probe:

- `/actuator/health/liveness` phản ánh tình trạng tiến trình.
- `/actuator/health/readiness` phản ánh khả năng nhận traffic.
- Nếu bật `management.endpoint.health.probes.add-additional-paths=true`, có thể dùng `/livez` và `/readyz` trên cổng HTTP ứng dụng, tránh kiểm tra một management port vẫn sống trong khi web server chính đã ngừng.

Cấu hình ví dụ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true

server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

Ứng dụng cần dependency `spring-boot-starter-actuator`. Khi Spring bắt đầu graceful shutdown, `ReadinessState` được chuyển sang `REFUSING_TRAFFIC`. Tuy nhiên, sau khi HTTP connector đóng, probe có thể không trả HTTP được nữa; Kubernetes cũng đánh dấu Pod terminating độc lập với probe. Readiness probe không phải tín hiệu đảm bảo toàn bộ luồng traffic đã cắt ngay lập tức.

### Ví dụ Deployment cho GKE

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: checkout-api
          image: asia-southeast1-docker.pkg.dev/example-project/apps/checkout-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

Ở ví dụ này, tổng grace period là **45 giây**, bao gồm khoảng `preStop` 5 giây và phần Spring dừng. `preStop` sleep chỉ là tùy chọn khi cần một khoảng ngắn để việc cập nhật routing lan truyền; không phải cách duy nhất hoặc luôn cần. Nếu image dùng distroless không chứa `/bin/sh` hoặc `sleep`, hook này sẽ thất bại; hãy bỏ hook hoặc thay bằng cơ chế tương thích image.

Đừng đặt `preStop` = 40 giây với grace period 45 giây rồi kỳ vọng Spring có 25 giây riêng để drain. Kubernetes đếm thời gian từ đầu quy trình terminate. Nếu hook chưa hoàn tất khi hết grace period, kubelet chỉ có thể xin một lần gia hạn ngắn khoảng 2 giây rồi tiến tới kill.

Với các hệ thống có yêu cầu availability cao, hãy kết hợp rolling update, ít nhất hai replica khi phù hợp, PodDisruptionBudget và cấu hình readiness thực tế. PDB hỗ trợ giới hạn voluntary disruptions nhưng không thay thế graceful shutdown, không ngăn được mọi loại node failure.

## 10. Cloud Run: tối ưu cho giới hạn 10 giây

Với Cloud Run service, deadline sau SIGTERM chỉ khoảng 10 giây và không thể tăng bằng `spring.lifecycle.timeout-per-shutdown-phase`. Cấu hình Spring phải nhỏ hơn thời gian nền tảng cho phép.

Một profile dùng trong Cloud Run có thể chọn:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 6s
~~~

Ví dụ này để lại một phần thời gian cho callback cleanup, nhưng nếu có nhiều phase, truy vấn database bị treo hoặc request streaming lâu, ứng dụng vẫn có thể bị SIGKILL. Do đó:

- Đặt timeout riêng cho database, HTTP client và message operations.
- Tránh `@PreDestroy` gọi dịch vụ bên ngoài mà không có timeout.
- Không bắt đầu background task mới sau khi nhận yêu cầu ngừng.
- Ghi log ngắn gọn khi shutdown bắt đầu và kết thúc; không flush lượng telemetry quá lớn.
- Dùng retry/checkpoint ở hệ thống ngoài container cho tác vụ quan trọng.
- Kiểm thử khi revision mới triển khai, traffic chuyển và instance bị thu hồi.

**Request timeout không phải shutdown timeout.** Cấu hình Cloud Run cho phép request dài hơn 10 giây không có nghĩa Spring được thêm từng ấy thời gian sau SIGTERM. Cloud Run thường có cơ chế hoàn tất in-flight request trước khi thu hồi instance, nhưng vẫn có trường hợp ngoại lệ hoặc gián đoạn đột ngột cần xử lý.

Cloud Run job cũng có giới hạn sau SIGTERM khi task timeout/hủy, trong khi task timeout có thể được cấu hình dài hơn. Đối với job lớn, ghi checkpoint định kỳ là chiến lược chính; flush cuối khi shutdown chỉ là biện pháp bổ trợ.

## 11. Kiểm thử graceful shutdown tại local

Hãy dùng môi trường thử nghiệm để đo hành vi thật. Có thể tạo một endpoint có độ trễ giả để quan sát request đang chạy:

~~~java
package com.example.checkout;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ShutdownDemoController {
    @GetMapping("/demo/slow")
    String slow() throws InterruptedException {
        Thread.sleep(3000);
        return "completed";
    }
}
~~~

Endpoint này chỉ phục vụ kiểm thử, không nên đưa vào public production API.

Build image và chạy:

~~~bash
docker build -t checkout-graceful:local .
docker run -d --name checkout-graceful -p 8080:8080 checkout-graceful:local
~~~

Ở một terminal, tạo request mất khoảng 3 giây:

~~~bash
curl -v http://localhost:8080/demo/slow
~~~

Ngay sau khi request bắt đầu, ở terminal khác:

~~~bash
docker stop --time 15 checkout-graceful
docker logs checkout-graceful
docker inspect checkout-graceful --format "{{.State.ExitCode}}"
~~~

Kỳ vọng: JVM nhận SIGTERM, Spring ngừng nhận request mới, request đang chạy có cơ hội hoàn tất và cleanup log xuất hiện trước khi container thoát. Nếu dừng container sau khi không còn request, đo riêng thời gian cleanup.

Có thể thử với `docker stop --time 2` để mô phỏng hạn chót quá ngắn. Lúc này SIGKILL có thể xảy ra trước khi Spring hoàn tất; đây là lý do không được bảo đảm mọi callback cleanup chạy.

Lưu ý `docker stop` timeout của Docker khác với deadline cố định của Cloud Run và với `terminationGracePeriodSeconds` của Kubernetes.

## 12. Kiểm thử trên GKE và Cloud Run

### Trên GKE staging

1. Triển khai nhiều replica và cấu hình readiness, graceful shutdown.
2. Tạo tải có request nhanh và request chậm, ghi nhận 5xx, latency, in-flight count.
3. Chạy rolling restart của Deployment trong namespace staging.
4. Theo dõi Pod transitions, EndpointSlice và log của container cũ.
5. Xác minh các request đang chạy không bị cắt vượt mức chấp nhận, không mất message và không commit sai trạng thái.

Ví dụ lệnh:

~~~bash
kubectl -n staging rollout restart deployment/checkout-api
kubectl -n staging rollout status deployment/checkout-api
kubectl -n staging get pods -l app=checkout-api -w
~~~

Với Pod còn tồn tại:

~~~bash
kubectl -n staging describe pod POD_NAME
kubectl -n staging logs POD_NAME -c checkout-api --timestamps
~~~

Trong lúc Pod bị xóa, log có thể chỉ còn trong Cloud Logging tùy cấu hình thu thập log và retention. Vì vậy, nên truy vấn Cloud Logging theo Pod/container/trace ID cho việc điều tra sau triển khai. Không chạy phép thử xóa Pod trên production nếu chưa có kế hoạch thay đổi.

### Trên Cloud Run staging

Cloud Run tự quyết định thời điểm thu hồi instance, nên không có lệnh tương đương để bảo đảm một instance cụ thể nhận SIGTERM ngay. Dùng `docker stop` để kiểm thử signal ở local, sau đó triển khai một revision thử nghiệm, thay đổi traffic hoặc scale behavior và quan sát log shutdown khi instance thực tế bị thu hồi.

Kiểm tra xem `java` có làm PID 1 không, cấu hình timeout có hợp lý không và callback có hoàn thành trong khoảng 10 giây. Không nên dựa vào việc một lần deploy tạo ra SIGTERM ngay lập tức để kết luận tính năng đúng hoặc sai.

## 13. Logging, metric và dấu hiệu lỗi

Nên ghi log theo cấu trúc để tìm lại giai đoạn shutdown:

~~~text
event=shutdown_started service=checkout-api revision=abc123
event=drain_completed active_requests=0 elapsed_ms=1850
event=shutdown_cleanup_complete duration_ms=120
~~~

Những chỉ số đáng quan sát:

- **Shutdown duration:** thời gian từ khi bắt đầu dừng đến lúc tiến trình thoát.
- **Request failures:** 5xx, reset connection hoặc gRPC CANCELLED/UNAVAILABLE trong giai đoạn rollout.
- **In-flight requests:** số request còn chạy khi bắt đầu drain và khi kết thúc.
- **Pod events / restart reason:** Terminating, OOMKilled, Error hoặc dấu hiệu killed.
- **Work queue:** số task đang xử lý, ack/commit timeout, retry và dead-letter count.
- **Dependency cleanup:** pool connection, executor đang chạy, flush telemetry chậm.
- **SLO:** ảnh hưởng của rollout đến availability và latency.

Ví dụ trong Cloud Logging, lọc log theo service, revision và thông điệp shutdown. Với GKE, kết hợp Kubernetes events và stdout/stderr của container. Không phải mọi tiến trình bị SIGKILL đều có cơ hội ghi dòng log cuối; khoảng trống log cũng là thông tin cần điều tra.

### Mã thoát thường gặp

| Exit code / tín hiệu | Cách diễn giải thông thường | Điều cần kiểm tra |
|---|---|---|
| `0` | Kết thúc bình thường | Cleanup thành công, job hoàn tất |
| `143` (128+15) | Một số shell/runtime ghi nhận kết thúc vì SIGTERM | Kiểm tra đã nhận tín hiệu, không suy ra lỗi chỉ từ mã 143 |
| `137` (128+9) | Thường liên quan SIGKILL; có thể là OOM hoặc vượt grace period | Xem container termination reason, memory, event/log |
| `1` hoặc mã khác | Ứng dụng báo lỗi | Exception, startup/shutdown stack trace và event |

Mã thoát phụ thuộc tiến trình và runtime; không dùng mã thoát một mình để kết luận nguyên nhân. Với container kết thúc vì OOM, thường cần xem `OOMKilled` và metric bộ nhớ.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Dockerfile chạy Java qua shell form | JVM không nhận SIGTERM trực tiếp | Dùng exec form hoặc `exec` trong launcher script |
| Đặt Spring timeout 30 giây trên Cloud Run | Container bị kill ở khoảng 10 giây | Tối ưu cleanup, giữ shutdown ngắn, checkpoint trước |
| Tưởng `@PreDestroy` luôn chạy | Mất dữ liệu khi OOM/SIGKILL/node lỗi | Idempotency, transaction, retry, durable queue |
| Chỉ cấu hình readiness, không xử lý in-flight | Request cũ bị cắt khi Pod terminate | Kết hợp drain, Spring graceful shutdown và grace period |
| preStop sleep chiếm toàn bộ thời gian | Spring không còn đủ thời gian dừng | Tính tổng preStop + các lifecycle phase + cleanup |
| Ack Pub/Sub/Kafka trước khi commit | Message có thể mất hoặc trạng thái sai | Ack/commit sau xử lý bền vững |
| Chờ network call không timeout trong callback | Dính SIGKILL trước khi log/cleanup hoàn tất | Giới hạn thời gian network và dọn dẹp |
| Shutdown consumer nhưng vẫn nhận task HTTP mới | Tác vụ mới bị từ chối hoặc thất lạc | Ngừng intake trước, drain có deadline |
| Tự bắt signal và gọi System.exit trong shutdown hook | Hook tranh chấp hoặc deadlock | Dùng lifecycle của JVM và Spring |
| Chỉ test khi container rảnh | Không phát hiện reset request khi rollout | Test với tải và request chậm |

## 15. Checklist trước khi phát hành

- [ ] Dockerfile dùng exec form hoặc launcher script có `exec` để Java nhận SIGTERM.
- [ ] Spring Boot khai báo `server.shutdown=graceful` và timeout phù hợp.
- [ ] Tổng thời gian shutdown đo được nhỏ hơn giới hạn nền tảng, có phần dự phòng.
- [ ] Có readiness và liveness probe phù hợp khi dùng GKE.
- [ ] `terminationGracePeriodSeconds` đã tính cả preStop và các phase Spring trên GKE.
- [ ] Background worker/consumer ngừng nhận công việc mới và drain hữu hạn.
- [ ] Transaction, ack, retry và idempotency đã được thiết kế cho tình huống kill bất ngờ.
- [ ] Cleanup dùng timeout, không phụ thuộc vào việc `@PreDestroy` luôn chạy.
- [ ] Request dài, streaming, WebSocket và tác vụ batch đã có chiến lược riêng.
- [ ] Có test local bằng `docker stop` và test rollout trên môi trường staging.
- [ ] Có log shutdown và metric để xác minh hành vi sau triển khai.
- [ ] Có phương án rollback, giảm tải và khôi phục công việc dang dở.

## 16. Câu hỏi tự kiểm tra

1. Vì sao Java cần là PID 1 hoặc được nhận SIGTERM từ tiến trình PID 1?
2. Sự khác biệt cơ bản giữa SIGTERM và SIGKILL là gì?
3. Đặt `spring.lifecycle.timeout-per-shutdown-phase=20s` có giúp Cloud Run cho container thêm 20 giây sau SIGTERM không?
4. Trên GKE, preStop 10 giây với termination grace 30 giây còn bao nhiêu thời gian tối đa cho các bước shutdown còn lại?
5. Vì sao readiness false không bảo đảm mọi kết nối đã được chuyển ngay sang Pod mới?
6. Khi Pub/Sub subscriber nhận SIGTERM giữa một transaction, nên ack message khi nào?
7. Vì sao `@PreDestroy` chưa đủ để bảo đảm không mất công việc quan trọng?
8. Làm thế nào kiểm thử graceful shutdown khi ứng dụng có một request chậm đang chạy?

**Gợi ý đáp án**

1. Tín hiệu của container thường gửi đến PID 1; nếu shell không forward signal, JVM không nhận yêu cầu shutdown.
2. SIGTERM cho tiến trình cơ hội dừng và cleanup, còn SIGKILL cưỡng bức kết thúc và không chạy callback.
3. Không. Cloud Run vẫn có khoảng 10 giây trước SIGKILL; Spring timeout chỉ giới hạn chờ nội bộ theo lifecycle phase.
4. Về nguyên tắc còn khoảng 20 giây (trừ overhead và thời gian routing), vì preStop tính chung trong grace period.
5. Endpoint và proxy/load balancer cập nhật bất đồng bộ; connection tồn tại trước đó có thể vẫn được dùng.
6. Sau khi transaction đã commit thành công; nếu chưa xong, để message redeliver và xử lý idempotent.
7. Shutdown hook có thể không chạy khi SIGKILL, OOM hoặc node chết; cần lưu bền vững, retry và idempotency.
8. Gửi một request chậm, phát SIGTERM bằng Docker stop hoặc rolling update ở staging, rồi đối chiếu response, log, thời gian drain và lỗi.

## Tài liệu tham khảo

- [Google Cloud: Cloud Run container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Google Cloud: Cloud Run execution environments and SIGTERM](https://docs.cloud.google.com/run/docs/configuring/execution-environments)
- [Google Cloud: Cloud Run service billing and background work](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
- [Google Cloud: Cloud Run jobs task timeouts](https://docs.cloud.google.com/run/docs/configuring/task-timeout)
- [Kubernetes: Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes: Container lifecycle hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
- [Spring Boot: Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot: Actuator Kubernetes probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Framework: Bean destruction and @PreDestroy](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html)
- [Docker: Dockerfile ENTRYPOINT exec and shell forms](https://docs.docker.com/reference/dockerfile/)

