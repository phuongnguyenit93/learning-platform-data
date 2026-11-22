# Startup probe, readiness, liveness và ranh giới với Actuator

Spring Boot khởi động chậm, Pod bị restart liên tục, hoặc application trả HTTP 200 ở endpoint kiểm tra sức khỏe nhưng API chính vẫn lỗi là những tình huống rất thường gặp khi triển khai dịch vụ web. Ba khái niệm của Kubernetes — **startup probe**, **readiness probe**, **liveness probe** — giải quyết **ba câu hỏi khác nhau**. Trong Spring Boot, `ApplicationAvailability` và Spring Boot Actuator giúp biểu diễn tình trạng hiện tại cho kubelet đánh giá.

Bài thuộc nhóm **Triển khai ứng dụng** của module Spring Boot web-runtime. Ví dụ dùng **Spring Boot 3.3.x, Java 17+, Spring MVC, Actuator và Kubernetes**. Có code Gradle/Java chạy được, thử HTTP trước/sau warmup, test thay đổi trạng thái readiness, Dockerfile, manifest Deployment, troubleshooting và checklist production.

**Nguyên lý trung tâm:** **Actuator công bố trạng thái; kubelet/Kubernetes áp chính sách restart hoặc định tuyến**. HTTP 200 từ một endpoint health không chứng minh mọi giao dịch nghiệp vụ, database, reverse proxy hay người dùng bên ngoài đều hoạt động.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt startup, readiness và liveness theo mục đích, chu kỳ và hậu quả khi thất bại.
- Giải thích vì sao `startupProbe` ngăn `readinessProbe` và `livenessProbe` hoạt động cho đến khi lần startup probe đầu tiên thành công.
- Nhận biết **readiness fail → NotReady/rút traffic**, **liveness fail → restart**, **startup fail vượt ngưỡng → restart**.
- Hiểu Spring Boot `ApplicationAvailability` và các enum `LivenessState`/`ReadinessState`.
- Phân biệt `ApplicationStartedEvent` với `ApplicationReadyEvent`, đặc biệt khi `ApplicationRunner` warmup.
- Bật các health groups `/actuator/health/liveness`, `/actuator/health/readiness` trong Boot 3.3.
- Dùng `/livez` và `/readyz` trên **main server port** khi có management port riêng.
- Giải thích vì sao **Actuator `/actuator/startup` không phải Kubernetes startupProbe**.
- Viết/kiểm thử Deployment manifest với failure thresholds, period và timeout hợp lý.
- Sử dụng `@SpringBootTest(RANDOM_PORT)` và `TestRestTemplate` để xác minh readiness 200→503→200.
- Đặt boundaries cho DB/cache/broker health checks, tránh cascading restarts.
- Chẩn đoán 404, 401, 503, connection refused, probe timeout, CrashLoopBackOff và rolling deployment.
- Phân biệt health probe, business monitor, tracing, SLO và graceful shutdown.

## 2. Ba câu hỏi và ba hành động của Kubernetes

| Probe | Câu hỏi | Khi thất bại đủ số lần | Khi nào chạy |
| --- | --- | --- | --- |
| `startupProbe` | Container đã khởi động đủ để bắt đầu theo dõi bình thường chưa? | Restart container theo policy | Chạy từ khi startup đến **lần thành công đầu**, rồi ngừng |
| `readinessProbe` | Pod này có nên nhận request mới ngay bây giờ không? | Đánh dấu **NotReady**, cập nhật Service endpoints; **không restart chỉ vì readiness** | Liên tục sau startup gate |
| `livenessProbe` | Process có hỏng đến mức nên restart không? | Restart container | Liên tục sau startup gate |

**Không có quy tắc rằng cả ba probe phải dùng ba URLs khác nhau.** Với Spring Boot, có thể dùng `/livez` cho cả startup và liveness nhưng đặt thresholds khác nhau; dùng `/readyz` cho readiness. Khi có startupProbe, kubelet **không thực hiện readiness/liveness trước khi startupProbe thành công**. Nếu không có startupProbe, readiness và liveness hoạt động theo lịch riêng, không chờ nhau.

### 2.1. Thí dụ giúp nhớ

- JVM đang load classes và warm cache 60 giây: **startup** cần budget đủ dài để không bị restart quá sớm.
- Ứng dụng đang warmup mô hình, đã nhận HTTP connections nhưng chưa sẵn sàng xử lý user requests: **liveness** có thể UP, **readiness** vẫn DOWN/OUT_OF_SERVICE.
- Một Pod mất kết nối với tài nguyên **chỉ thuộc Pod đó**, không thể nhận traffic: readiness có thể 503, nhưng chưa chắc phải restart.
- Critical application thread deadlock hoàn toàn không tự phục hồi: đây mới là ứng viên cho liveness failure/restart.
- Shared database tạm down: restart toàn bộ JVM **không sửa database**, nên không đưa DB check vào liveness thông thường.

### 2.2. Readiness và Service routing

Khi readiness fail, Kubernetes không nên route Service traffic mới đến container/Pod đó theo các điều kiện phù hợp. Thay đổi EndpointSlice/ingress/proxy diễn ra bất đồng bộ, **không phải một transaction ngay tức khắc**. Connection cũ có thể còn sống; các clients có thể vẫn gặp reset hoặc 503 trong rollout. Readiness không đảm bảo zero-downtime nếu load balancer, client retry và graceful shutdown không được thiết kế.

### 2.3. Khi toàn bộ Pods NotReady

Nếu tất cả instances bị đánh dấu NotReady vì một external dependency chung, Service có thể hết endpoints sẵn sàng; phía client có thể bị lỗi kết nối hoặc ingress trả 503 tùy implementation. Vì thế đánh giá readiness phải xét hiệu ứng toàn cụm, không chỉ từng Pod.

## 3. Actuator, Kubernetes và Spring Boot có ranh giới rõ

```text
Kubernetes kubelet
   |
   | HTTP GET PodIP:8080/livez hoặc /readyz
   v
Spring Boot main HTTP server
   |
   +-- /livez  --> Actuator liveness health group
   |                   |
   |             LivenessStateHealthIndicator
   |                   |
   +-- /readyz --> Actuator readiness health group
                       |
                 ReadinessStateHealthIndicator
                       |
                ApplicationAvailability
                       |
           Spring lifecycle / app decisions

kubelet nhận HTTP status hoặc timeout
   |
   +-- startup failure vượt threshold  -> restart
   +-- liveness failure vượt threshold -> restart
   +-- readiness failure              -> NotReady
```

**Spring Boot `ApplicationAvailability`** là một interface cung cấp trạng thái availability trong JVM. Ngay cả khi không thêm Actuator, Spring Boot có thể quản lý trạng thái này; nhưng **không tự tạo đường HTTP Actuator health group** nếu thiếu Actuator và web setup.

**Actuator** tạo `HealthIndicator` và `HealthContributor`, tổng hợp thành `HealthEndpoint` và health groups. Với status mặc định, `UP` thường trả HTTP 200; `DOWN`/`OUT_OF_SERVICE` thường trả HTTP 503. **Kubelet HTTP probe xét status code 200–399**, không phải tự parse body JSON có `"status":"UP"`.

**Kubernetes** mới là thành phần thực hiện restart container hoặc cập nhật EndpointSlices/readiness conditions. Actuator không gọi Kubernetes API để delete/restart Pod chỉ vì liveness down.

### 3.1. Những việc một health endpoint không tự chứng minh

Một endpoint `/livez` HTTP 200 không chứng minh:

- User thật có thể truy cập qua TLS/Ingress/CDN từ Internet.
- Controller xử lý payment với đúng authorization và transaction.
- Mọi đường API đều hoạt động.
- Database đã có dữ liệu cần thiết.
- Một queue consumer không bị stalled.
- Session Redis đã hoạt động trên cả 5 replicas.
- Latency và error rate nằm trong SLO.
- Client request đang thực hiện đã hoàn thành trước pod termination.

Muốn kiểm tra các hợp đồng này, dùng integration tests, synthetic canary monitoring, metrics/tracing và domain-specific checks **phù hợp**, không đẩy tất cả vào liveness.

## 4. ApplicationAvailability và Spring startup lifecycle

Spring Boot 3.3 có:

```java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
```

Các trạng thái cốt lõi:

- `LivenessState.BROKEN`: runtime không hoạt động đúng và được coi là không thể tự phục hồi; restart có thể có ích.
- `LivenessState.CORRECT`: runtime nội bộ vẫn đúng.
- `ReadinessState.REFUSING_TRAFFIC`: tạm thời không nên nhận traffic mới.
- `ReadinessState.ACCEPTING_TRAFFIC`: sẵn sàng tiếp nhận traffic.

### 4.1. Timeline theo Spring Boot 3.3

| Giai đoạn | Liveness | Readiness | HTTP server |
| --- | --- | --- | --- |
| Starting: context chưa hoàn thành | `BROKEN` | `REFUSING_TRAFFIC` | Có thể chưa mở listener |
| Started: context refresh xong, trước/đang chạy runners | `CORRECT` | `REFUSING_TRAFFIC` | Có thể lắng nghe nhưng chưa nên nhận user traffic |
| Ready: sau runners, `ApplicationReadyEvent` | `CORRECT` | `ACCEPTING_TRAFFIC` | Sẵn sàng nhận traffic |
| Graceful shutdown | Thường `CORRECT` | `REFUSING_TRAFFIC` | Từ chối requests mới, xử lý inflight theo deadline |
| Process stopped | Không còn health HTTP | Không còn | Cổng đóng |

**Đừng yêu cầu luôn nhận `{"status":"OUT_OF_SERVICE"}` trong giai đoạn rất sớm.** Nếu server chưa bind, kubelet nhận connection refused chứ không có HTTP response. Khi graceful shutdown đóng listener, probe cũng có thể không truy cập được trạng thái dù state đã đổi.

### 4.2. ApplicationStartedEvent khác ApplicationReadyEvent

```text
ApplicationContext refreshed
         |
ApplicationStartedEvent
         |
ApplicationRunner/CommandLineRunner
         |
ApplicationReadyEvent
         |
Readiness ACCEPTING_TRAFFIC
```

`ApplicationStartedEvent` được phát sau context refresh, **trước** runners. `ApplicationReadyEvent` chỉ đến khi runners hoàn thành. Nếu một `ApplicationRunner` warmup mất 8 giây, trong thời gian đó liveness có thể CORRECT còn readiness REFUSING_TRAFFIC. Đó là trạng thái hợp lệ.

### 4.3. Nếu runner thất bại

Khi runner ném exception và không được ứng dụng xử lý, Spring Boot startup có thể thất bại, context đóng và process exit. Nó không nhất thiết tiếp tục chạy mãi với readiness 503. Nếu muốn degraded mode, phải thiết kế exception policy, retries, circuit breaker và phân loại những lỗi thật sự cho phép tiếp tục.

### 4.4. Ứng dụng tự công bố readiness

Trong bean có `ApplicationContext context`, có thể gọi:

```java
AvailabilityChangeEvent.publish(
    context, ReadinessState.REFUSING_TRAFFIC);
```

Khi đã hoàn thành drain hoặc phục hồi:

```java
AvailabilityChangeEvent.publish(
    context, ReadinessState.ACCEPTING_TRAFFIC);
```

Đây là **snippet** yêu cầu imports và biến `context`, không phải controller để ai cũng gọi được trên public network. Chỉ phát `LivenessState.BROKEN` khi thật sự muốn hệ thống restart vì runtime không thể tự phục hồi; không dùng để thử trực tiếp trên production.

## 5. Những HTTP endpoints Actuator tạo

Thêm:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Trong Kubernetes, Spring Boot tự enable liveness/readiness probe groups khi phát hiện platform. Ngoài Kubernetes, với Spring Boot **3.3**, đặt tường minh:

```properties
management.endpoint.health.probes.enabled=true
```

Các đường phổ biến:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

### 5.1. Global health khác liveness/readiness

- `/actuator/health`: tổng hợp health contributors được cấu hình, có thể có DB/disk/Redis nếu dependencies hiện diện.
- `/actuator/health/liveness`: health group cho **livenessState**.
- `/actuator/health/readiness`: health group cho **readinessState**.
- `/actuator/startup`: hiển thị **startup steps instrumentation** khi cấu hình và expose, **không** phải Kubernetes startupProbe.

Nếu DB check làm `/actuator/health` trả 503, điều đó không tự đồng nghĩa `/actuator/health/liveness` phải 503. Spring Boot không tự thêm toàn bộ external health contributors vào liveness/readiness probe groups.

### 5.2. Vì sao /actuator/startup không phải startupProbe

Actuator `startup` endpoint trình bày thông tin startup từ `ApplicationStartup`/`BufferingApplicationStartup` khi được bật. Nó phục vụ chẩn đoán các bước bootstrap, không phải liveness và không được đảm bảo sẵn sàng trong quá trình bootstrap. Chỉ vì cùng chữ “startup” không có nghĩa nên cho kubelet GET `/actuator/startup`.

Kubernetes startupProbe là **cấu hình ở Pod spec**, ví dụ:

```yaml
startupProbe:
  httpGet:
    path: /livez
    port: http
```

Kubelet quan tâm HTTP status/timeout. Actuator startup endpoint không được viết để đảm bảo hợp đồng này.

### 5.3. Status-to-HTTP

Mặc định các health status như `UP` → HTTP 200 và `DOWN`/`OUT_OF_SERVICE` → HTTP 503. Tùy biến `management.endpoint.health.status.http-mapping.*` có thể thay status mapping. Đừng cấu hình readiness OUT_OF_SERVICE thành HTTP 200 chỉ để dashboards không báo đỏ: kubelet lúc đó sẽ hiểu sai và đưa traffic đến Pod chưa sẵn sàng.

### 5.4. Bảo vệ health details

Đặt:

```properties
management.endpoint.health.show-details=never
management.endpoints.web.exposure.include=health
```

Đây là baseline tốt cho lab; production vẫn cần network policies và security chain thích hợp. Không expose `env`, `heapdump`, `loggers`, `shutdown`, `configprops` ra Internet vô điều kiện. Health detail có thể chứa DB hostnames, error messages hoặc deployment internals không nên công khai.

## 6. Management port tách khỏi business port

Giả sử:

```properties
server.port=8080
management.server.port=9090
```

Một health probe ở `9090` có thể 200 ngay cả khi business HTTP listener 8080 bị cấu hình sai hoặc không nhận kết nối. Main server và management server là những web infrastructures khác nhau trong cấu hình separate management context.

Để tăng độ tin cậy, Spring Boot 3.3 hỗ trợ:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

Nó tạo thêm các health group routes trên **main port**:

```text
http://pod-ip:8080/livez
http://pod-ip:8080/readyz
```

Nếu có management port, các Actuator routes gốc có thể tồn tại:

```text
http://pod-ip:9090/actuator/health/liveness
http://pod-ip:9090/actuator/health/readiness
```

Khuyến nghị cho Kubernetes web API: probe `/livez`/`/readyz` trên **port 8080** để ít nhất chứng minh main listener còn xử lý probe HTTP. Chúng vẫn không thử DB/payment business flow trừ khi bạn thiết kế riêng.

### 6.1. Không tự viết một controller luôn 200

Phản ví dụ:

```java
// Không dùng để thay built-in liveness health group:
@GetMapping("/livez")
public String live() {
    return "OK";
}
```

Nếu endpoint luôn 200, nó che mất `LivenessState.BROKEN`. Khi đã đặt `add-additional-paths=true` thì không cần controller riêng; còn có nguy cơ mapping collision.

### 6.2. Context path và HTTPS

Nếu dự án đặt `server.servlet.context-path=/api`, đường probe ở main server có thể chịu ảnh hưởng prefix; cần xác minh URL thực với phiên bản/cấu hình của bạn. Nếu web server bind `127.0.0.1` bên trong container thay vì 0.0.0.0/Pod IP, kubelet HTTP GET Pod IP có thể connection refused. Nếu chỉ hỗ trợ TLS hoặc có service mesh, chọn `scheme` và mesh probe rewriting phù hợp.

## 7. Startup probe vận hành chi tiết

### 7.1. Startup gate

Kubernetes chỉ chạy startupProbe đến khi nó **thành công một lần**. Trong thời gian đó, liveness và readiness chưa chạy. Sau thành công, startupProbe ngừng và liveness/readiness hoạt động theo lịch riêng. Pod không tự Ready chỉ vì startupProbe pass; **readiness phải thành công** và các Pod conditions khác cũng phải thỏa.

### 7.2. Startup failure

Khi startupProbe fail đủ `failureThreshold` consecutive tries, kubelet restart container. Nếu tiếp tục fail, Pod có thể hiển thị `CrashLoopBackOff`/backoff restarts. Điều này khác readiness: readiness fail chỉ mark NotReady, không tự restart.

### 7.3. StartupProbe nên dùng /livez hay /readyz?

**/livez** (lựa chọn thường được Boot docs nêu): đánh dấu runtime đã khởi động đủ để liveness checks bắt đầu. Nó có thể thành công **trước khi** runners/warmup hoàn tất; readiness tiếp tục ngăn traffic. Đây là cách phân tách “process started” với “business ready”.

**/readyz** (tùy yêu cầu): chỉ coi startup qua khi đã sẵn sàng tiếp traffic. Nhưng nếu readiness phụ thuộc shared DB, DB down khiến startup thất bại đủ số lần → restart liên tục, dù JVM không hỏng. Chọn có chủ đích, không lấy /readyz làm startup theo phản xạ.

**Một failure mode khó nhận thấy:** nếu `ApplicationRunner` bị kẹt vĩnh viễn sau khi liveness đã CORRECT, startupProbe `/livez` có thể xanh còn readiness cứ đỏ. Không có gì buộc kubelet restart nếu liveness tiếp tục thành công. Giải pháp đúng là **warmup có timeout**, fail startup có kiểm soát, hoặc có watchdog tiến triển nội bộ; không gắn DB vào liveness tùy tiện.

### 7.4. StartupProbe không bắt buộc mọi ứng dụng

Nếu ứng dụng khởi động nhanh và liveness được cấu hình đủ tolerance, readiness đã ngăn traffic trước khi Ready, startupProbe có thể không cần. Dùng startupProbe khi startup time dài/biến thiên đáng kể hoặc liveness threshold steady-state sẽ restart app quá sớm.

## 8. Kubernetes probe fields: cách tính thực tế

Các fields quan trọng:

| Field | Ý nghĩa |
| --- | --- |
| `httpGet.path` | Đường GET thực trên Pod IP/port |
| `port` | Number hoặc named container port |
| `periodSeconds` | Chu kỳ thực hiện; readiness khi NotReady có thể được thực hiện thường hơn |
| `timeoutSeconds` | Giới hạn thời gian mỗi probe |
| `failureThreshold` | Số failures liên tiếp để áp hành động |
| `successThreshold` | Số successes liên tiếp; với startup/liveness phải là **1** |
| `initialDelaySeconds` | Thời gian trì hoãn ban đầu nếu cần |
| `terminationGracePeriodSeconds` | Pod shutdown budget; không phải thời gian startup |

Ví dụ `startupProbe.failureThreshold=24`, `periodSeconds=5` cho budget xấp xỉ **120 giây**, không phải deadline cứng chính xác từng mili giây. Scheduling, probe timeouts, delays và node load có ảnh hưởng. `livenessProbe.failureThreshold=3`, `periodSeconds=10` cho detection window khoảng vài chục giây sau startup; tune theo GC pauses, CPU throttling và retry policy.

### 8.1. HTTP success

Kubelet HTTP probe xem status **200–399** thành công. 404/401/403/500/503 hoặc timeout/refused thất bại. Cẩn trọng: nếu Spring Security redirect `/readyz` sang trang login với **302**, kubelet có thể xem đó là success. Probe URL phải trả health status trực tiếp chứ không redirect login.

### 8.2. Timeout và giả lỗi do overload

`timeoutSeconds=1` có thể quá chặt khi cold start, garbage collection hoặc CPU throttling. Các liveness timeouts giả dẫn đến restart khiến Pod cold caches và dependency reconnect, tạo vòng lặp quá tải. Đừng “sửa” bằng cách luôn cho health 200; đo resource utilization, p99 latency và chọn thresholds phù hợp.

## 9. Deployment YAML có đủ ba probes

Ví dụ deploy 2 replicas, main HTTP port 8080. Manifest phù hợp lab/staging, **không phải universal production config**:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: probe-lab
spec:
  replicas: 2
  revisionHistoryLimit: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: probe-lab
  template:
    metadata:
      labels:
        app: probe-lab
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: app
          image: registry.example.test/probe-lab:1.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
            successThreshold: 1
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
            successThreshold: 1
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1
          resources:
            requests:
              cpu: 150m
              memory: 256Mi
            limits:
              memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: probe-lab
spec:
  selector:
    app: probe-lab
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
```

**Ý nghĩa:**

- Startup có khoảng 120 giây cho các tình huống JVM cold start; liveness không restart sớm trong cửa sổ đó.
- Sau startup, readiness cứ 5 giây kiểm tra instance có nhận traffic được chưa.
- Sau startup, liveness mỗi 10 giây kiểm tra process có cần restart không.
- `maxUnavailable: 0` cố giữ Pod cũ khi Pod mới chưa Ready trong rolling update, nhưng không tự bảo đảm hệ thống không có lỗi hoặc tài nguyên cluster đủ để tạo surge Pod.
- `terminationGracePeriodSeconds: 40` áp dụng shutdown, không phải startup budget.
- Image là ví dụ, cần build/push vào registry cluster thực sự có quyền pull.
- Các resource requests/limits trong manifest chỉ minh họa; phải benchmark cho app/JVM thật để tránh OOMKilled/CPU throttling.
- Production có thể còn securityContext, service account, network policies, HPA, PDB, affinity và ingress/TLS.

## 10. External dependencies: liveness phải cực kỳ thận trọng

### 10.1. Không đưa shared DB vào liveness

**Phản ví dụ nguy hiểm:**

```properties
management.endpoint.health.group.liveness.include=livenessState,db
```

Giả sử database chung ngừng trong 30 giây. Nếu liveness phụ thuộc DB, tất cả Pod có thể bị restart. Restart JVM không khôi phục DB mà tăng startup load/connection storm và có thể làm mất công việc inflight.

Liveness chỉ nên xét trạng thái runtime nội bộ không thể recover; thông thường dùng built-in `livenessState` mà không thêm DB/Redis/Kafka/payment API.

### 10.2. Readiness thêm dependency khi nào?

Nếu instance không thể phục vụ **bất kỳ request có ý nghĩa nào** khi một local dependency mất, có thể thêm kiểm tra đó vào readiness. Nhưng cân nhắc:

1. Có fallback/cache/circuit breaker không?
2. Dependency shared giữa mọi Pods hay riêng một Pod?
3. Readiness fail tất cả Pods sẽ làm Service không có endpoints không?
4. Check có nhanh, bounded, không tạo side effects không?
5. Tần suất health calls có tăng tải dependency không?
6. Khi hồi phục có hysteresis/debounce chống trạng thái nhấp nháy không?

Spring Boot không tự thêm health contributors external vào readiness group. Ví dụ property tùy chọn **chỉ khi đã có indicator tên `catalogWarmup`**:

```properties
management.endpoint.health.group.readiness.include=readinessState,catalogWarmup
```

Nếu chưa có bean contributor này, đừng chép nguyên property vào base app. Hãy chọn đúng tên HealthIndicator và scope; thiếu contributor có thể khiến health group không hợp lệ.

### 10.3. Custom HealthIndicator optional

Class này là **mở rộng riêng**, không bắt buộc cho runnable baseline ở mục sau:

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("catalogWarmup")
public class CatalogWarmupHealth implements HealthIndicator {

    private final AtomicBoolean prepared =
            new AtomicBoolean(false);

    public void markPrepared() {
        prepared.set(true);
    }

    public void markNotPrepared() {
        prepared.set(false);
    }

    @Override
    public Health health() {
        return prepared.get()
                ? Health.up().build()
                : Health.outOfService().build();
    }
}
```

Một warmup service có thể gọi `markPrepared()` sau khi local data/model đã sẵn sàng. Nếu health group include `catalogWarmup`, readiness còn phụ thuộc state này. **Không làm remote DB query tốn 2 giây trong mỗi call `health()`**; làm như vậy khiến probes tự tạo tải lớn.

### 10.4. Readiness không thay circuit breaker

Nếu DB mất nhưng một số endpoints vẫn trả cached content, cho toàn Service NotReady có thể tệ hơn giữ Pod Ready và trả degraded result an toàn. Ngược lại, nếu mọi request đều cần DB và không có fallback, việc rút traffic có thể hợp lý hơn liên tục trả 500. Chính sách tùy hợp đồng nghiệp vụ; không có cấu hình universal.

## 11. Dự án Spring Boot Java 17+ chạy được

Ta tạo application nhỏ có:

- `GET /api/hello`: API mẫu.
- `GET /demo/state`: trả Java `ApplicationAvailability` (chỉ để học, không mở public).
- `ApplicationRunner` mô phỏng warmup 8 giây.
- Actuator health groups liveness/readiness.
- `/livez` và `/readyz` trên main HTTP port.
- Integration test với `TestRestTemplate` chứng minh readiness từ 200 sang 503 còn liveness vẫn 200.

### 11.1. Gradle project

Tạo bằng [Spring Initializr](https://start.spring.io/), Java 17+, Spring Boot 3.3.x, Gradle/Groovy, chọn **Spring Web** và **Spring Boot Actuator**.

`settings.gradle`:

```groovy
rootProject.name = 'probe-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Project cần **Gradle Wrapper** do Initializr tạo (`gradlew`, `gradlew.bat`, `gradle/wrapper`). Không chạy riêng `javac DemoController.java` vì class này cần Spring classpath từ Gradle. Dùng dependency management của Spring Boot thay vì trộn Spring Framework/Actuator versions tùy ý.

Cấu trúc:

```text
settings.gradle
build.gradle
gradlew
gradlew.bat
gradle/wrapper/...
src/
  main/
    java/demo/
      ProbeLabApplication.java
      DemoController.java
      WarmupRunner.java
    resources/
      application.properties
  test/
    java/demo/
      ProbeHttpIntegrationTest.java
```

### 11.2. ProbeLabApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProbeLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProbeLabApplication.class, args);
    }
}
```

### 11.3. DemoController.java

```java
package demo;

import java.util.Map;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ApplicationAvailability availability;

    public DemoController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }

    // Chỉ dùng để học ở local.
    @GetMapping("/demo/state")
    public Map<String, String> state() {
        return Map.of(
                "liveness",
                availability.getLivenessState().name(),
                "readiness",
                availability.getReadinessState().name()
        );
    }
}
```

Sau startup thành công, body `/demo/state` thường tương đương:

```json
{
  "liveness": "CORRECT",
  "readiness": "ACCEPTING_TRAFFIC"
}
```

Trong lúc warmup chưa xong, có thể thấy CORRECT/REFUSING_TRAFFIC nếu listener đã hoạt động. Nếu server chưa bind/không tiếp nhận request, `curl` sẽ báo lỗi kết nối thay vì có JSON. `/demo/state` không thay `/livez`/`/readyz` và không phải route cần mở ở production.

### 11.4. WarmupRunner.java

```java
package demo;

import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class WarmupRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(WarmupRunner.class);

    @Value("${probe.demo.warmup-seconds:8}")
    private int seconds;

    @Override
    public void run(ApplicationArguments arguments)
            throws Exception {

        if (seconds < 0 || seconds > 120) {
            throw new IllegalArgumentException(
                    "warmup-seconds must be 0..120");
        }

        log.info("WARMUP_BEGIN seconds={}", seconds);

        TimeUnit.SECONDS.sleep(seconds);

        log.info("WARMUP_COMPLETE");
    }
}
```

`ApplicationRunner` chạy **sau ApplicationStartedEvent và trước ApplicationReadyEvent**. Thời gian sleep 8 giây chỉ để quan sát, không là kỹ thuật warmup production. Với ứng dụng thật, startup có timeout/failure semantics, không giữ một worker thread sleep không lý do.

### 11.5. application.properties

```properties
spring.application.name=probe-lab
server.port=8080

# Bật probe groups trong local, không chỉ Kubernetes.
management.endpoint.health.probes.enabled=true

# Có /livez và /readyz trên cổng ứng dụng.
management.endpoint.health.probes.add-additional-paths=true

# Chỉ expose health, không mở env/heapdump/shutdown...
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never

# Cố tình trì hoãn ApplicationReadyEvent.
probe.demo.warmup-seconds=8

# Explicit graceful shutdown cho Spring Boot 3.3.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Các properties này thuộc **Spring Boot 3.3**. Ở Kubernetes, Boot có thể auto-enable health groups; đặt `enabled=true` trong demo làm việc chạy local có hành vi rõ. Nếu cấu hình `management.server.port=9090`, `/livez`/`/readyz` vẫn được expose trên main port khi `add-additional-paths=true`.

### 11.6. Chạy

Từ thư mục có Gradle Wrapper:

```bash
./gradlew clean test bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test bootRun
```

Đóng gói executable JAR:

```bash
./gradlew bootJar
java -jar build/libs/probe-lab-0.0.1-SNAPSHOT.jar
```

Nếu chạy bằng `bootRun` rồi gửi signal dừng, nhớ PID của Gradle launcher có thể khác JVM app; dùng trực tiếp `java -jar` trong thí nghiệm shutdown để biết signal đến đúng process.

## 12. Quan sát warmup bằng curl

Mở **terminal A** chạy JAR. Trong **terminal B**, bắt đầu polling trước khi app startup hoàn tất:

```bash
while true; do
  printf "live="
  curl -sS -o /dev/null -w '%{http_code}' \
    http://localhost:8080/livez
  printf " ready="
  curl -sS -o /dev/null -w '%{http_code}' \
    http://localhost:8080/readyz
  printf "\n"
  sleep 1
done
```

Trên Linux/macOS, khi HTTP chưa mở, curl có thể in `000` vì **không có HTTP response**. Khi app đã Started, liveness có thể 200 còn readiness 503. Khi runner log `WARMUP_COMPLETE` rồi Spring phát ApplicationReadyEvent, readiness thường chuyển 200. Thời điểm chính xác phụ thuộc máy, startup order và scheduler.

Khi cả hai đã UP:

```bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/demo/state
curl -i http://localhost:8080/api/hello
```

Response health có thể có JSON:

```json
{"status":"UP"}
```

HTTP status thường 200. Khi readiness REFUSING_TRAFFIC, response có thể là:

```json
{"status":"OUT_OF_SERVICE"}
```

với HTTP **503**. Đây là response shape minh họa; các headers/media type theo Spring Boot Actuator có thể thay theo Accept/version. Kubelet đánh giá status code, không so sánh raw JSON string.

### 12.1. Tại sao một request sớm có thể bị từ chối thay vì nhận 503?

Trước khi Servlet connector chấp nhận HTTP requests, chưa tồn tại HTTP response để trả 503. Kubelet nhận connection refused/timeout, và tính là probe failure. Điều này bình thường trong startup window; startupProbe xử lý bằng failure budget, không đòi web server trả JSON từ giây đầu.

### 12.2. Không ép response luôn HTTP 503 khi chưa Ready

Một request thông thường không nhất thiết bị Spring MVC chặn chỉ vì `ReadinessState.REFUSING_TRAFFIC`. Tác dụng chính của readiness state là để platform **ngừng route new traffic**. Trong local, gọi trực tiếp API tới port trong lúc readiness đỏ có thể vẫn nhận response, tùy Boot lifecycle timing. Đừng nhầm readiness với cơ chế security filter cấm toàn bộ business requests.

## 13. HTTP integration test có chuyển readiness 200→503→200

`@SpringBootTest(webEnvironment=RANDOM_PORT)` start embedded server thật trên cổng ngẫu nhiên. Trong test ta chủ động publish event và đo kết quả HTTP. Tạo `src/test/java/demo/ProbeHttpIntegrationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "probe.demo.warmup-seconds=0"
)
class ProbeHttpIntegrationTest {

    @Autowired
    TestRestTemplate client;

    @Autowired
    ConfigurableApplicationContext context;

    @Test
    void appIsLiveAndReadyAfterBoot() {

        ResponseEntity<String> live =
                client.getForEntity("/livez", String.class);

        ResponseEntity<String> ready =
                client.getForEntity("/readyz", String.class);

        assertThat(live.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(ready.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(live.getBody()).contains("UP");
        assertThat(ready.getBody()).contains("UP");
    }

    @Test
    void refusingTrafficOnlyChangesReadiness() {

        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.REFUSING_TRAFFIC
        );

        try {
            ResponseEntity<String> ready =
                    client.getForEntity("/readyz", String.class);
            ResponseEntity<String> live =
                    client.getForEntity("/livez", String.class);

            assertThat(ready.getStatusCode())
                    .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
            assertThat(ready.getBody())
                    .contains("OUT_OF_SERVICE");
            assertThat(live.getStatusCode())
                    .isEqualTo(HttpStatus.OK);
        } finally {
            // Không để state ảnh hưởng các tests dùng chung context.
            AvailabilityChangeEvent.publish(
                    context,
                    ReadinessState.ACCEPTING_TRAFFIC
            );
        }
    }
}
```

**Test chứng minh:** HTTP main-port health group routes có thật; khi publish REFUSING_TRAFFIC thì `/readyz` trả 503 trong khi `/livez` vẫn 200. `TestRestTemplate` được thiết kế cho integration tests và không xem mọi response 4xx/5xx là exception.

**Test không chứng minh:** kubelet restart, EndpointSlice routing, Ingress/TLS, distributed DB health, preStop hoặc restart/eviction. Cần thí nghiệm trên cluster staging.

### 13.1. Vì sao test đặt warmup-seconds=0?

`@SpringBootTest` chỉ chạy test method sau khi context đã sẵn sàng. Nếu muốn quan sát các trạng thái **trong** startup, cần chạy app như process bên ngoài và polling từ trước, không chỉ dùng một method JUnit sau khi startup xong.

### 13.2. Không chạy state-mutating tests song song vô điều kiện

Availability state nằm trong application context. Nếu các test chạy parallel với chung context, test publish REFUSING_TRAFFIC có thể ảnh hưởng test khác. `finally` phục hồi state, nhưng parallel isolation vẫn cần quản lý. Dùng separate context, tránh parallel hoặc có synchronization nếu suite lớn.

### 13.3. MockMvc khác RANDOM_PORT

`MockMvc` có thể test controllers và Actuator mappings theo mock Servlet request, nhưng không khởi động TCP HTTP listener. `RANDOM_PORT` kiểm tra main listener path thật. Cả hai vẫn không mô phỏng kubelet, Pod IP routing hoặc network policy.

## 14. Dockerfile và container thử nghiệm

Sau khi build `bootJar`, tạo `Dockerfile`:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app

COPY build/libs/probe-lab-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Exec-form ENTRYPOINT giúp JVM là main process và nhận stop signal rõ ràng từ container runtime. Nếu dùng shell-form entrypoint, TERM có thể không được forward tới JVM như mong muốn. Để thử local:

```bash
docker build -t probe-lab:local .
docker run --rm -p 8080:8080 probe-lab:local
```

Trong terminal khác gọi `/livez`/`/readyz`. Để áp manifest Kubernetes, phải push image tới registry hoặc cấu hình cluster dùng local image đúng cách; image `registry.example.test/...` trong YAML chỉ là minh họa.

**Phân biệt:** Docker HEALTHCHECK không giống Kubernetes `readinessProbe`. Docker có health state; Kubernetes controller và Service endpoints dùng Pod Ready conditions theo probes của kubelet.

## 15. Deployment thật: kubectl và chẩn đoán

Sau khi có Kubernetes cluster staging và image hợp lệ:

```bash
kubectl apply -f probe-lab.yaml
kubectl rollout status deployment/probe-lab
kubectl get pods -l app=probe-lab -w
kubectl describe pod <POD_NAME>
kubectl logs <POD_NAME> -c app
kubectl logs <POD_NAME> -c app --previous
kubectl get endpointslice \
  -l kubernetes.io/service-name=probe-lab
```

`<POD_NAME>` là placeholder lệnh CLI, thay bằng tên Pod thực. `--previous` giúp đọc container logs trước một lần restart, nếu log còn được giữ.

### 15.1. Ý nghĩa các lỗi hay gặp

- `connection refused`: container chưa bind, process đã chết, port/path sai hoặc listener chỉ bind loopback.
- `HTTP 404`: Actuator không expose route, thiếu additional paths hoặc context path sai.
- `HTTP 401/403`: Spring Security chặn kubelet, cần policy tối thiểu cho health route.
- `HTTP 302`: có thể là redirect login và kubelet vẫn coi success; cần sửa.
- `HTTP 503`: health group báo DOWN/OUT_OF_SERVICE hoặc app đang drain.
- `context deadline exceeded`: timeout quá ngắn, CPU throttle/GC pause, network hoặc deadlock.
- `CrashLoopBackOff`: repeated restart nhưng **không nhất thiết** do probe; app có thể tự crash/OOMKilled/config failure.
- `Pod Running, Ready false`: process vẫn chạy nhưng readiness fail, startup chưa xong, một container khác fail hoặc readiness gate không được thỏa.

Đọc `kubectl describe pod` events, container `lastState`, restart count, resource metrics, logs và EndpointSlice; đừng chỉ dựa vào một dòng “Unhealthy”.

### 15.2. Kubelet probe không đi qua Ingress theo mặc định

HTTP probe từ kubelet thường nhắm **Pod IP:container port/path**, không truy cập URL qua Service/Ingress/TLS/CDN. Do đó `curl https://api.example.com/health` 200 **không** chứng minh kubelet path/port đúng; ngược lại kubelet /readyz pass cũng không đảm bảo public API qua gateway hoạt động.

### 15.3. Security, redirects và 3xx

Với Spring Security, health probe có thể cần permit read-only `/livez`/`/readyz` cho kubelet/internal network. Giữ Actuator management endpoints khác được bảo vệ. Không cấu hình `anyRequest().permitAll()` chỉ để probes xanh. Không để endpoint redirect login: 3xx có thể được kubelet xem success dù health không được đánh giá.

### 15.4. Localhost trong container

Nếu ứng dụng bind `server.address=127.0.0.1` trong container, probe từ kubelet tới Pod IP sẽ bị từ chối. Để main port lắng nghe trên Pod interface, dùng default binding phù hợp (thường all interfaces) và bảo vệ bằng NetworkPolicy/Ingress/Security. Không dùng `httpGet.host: localhost` để che cấu hình listening sai.

## 16. Readiness trong rolling deployment và shutdown

Một rolling update lý tưởng:

1. Pod mới được tạo và JVM bootstrap.
2. StartupProbe thành công trước startup budget.
3. Liveness hoạt động ở steady state.
4. Readiness chỉ 200 khi instance thật sự có thể nhận traffic.
5. Service/EndpointSlice cập nhật route, Pod mới bắt đầu nhận load.
6. Pod cũ được đánh dấu terminating, ingress/proxy rút traffic bất đồng bộ.
7. Spring Boot graceful shutdown ngừng nhận request mới và chờ inflight requests trong budget.
8. Client retries/idempotency xử lý các request bị ảnh hưởng.

**Readiness false không đóng ngay các connections đang tồn tại.** Clients dùng keep-alive/WebSocket/SSE có thể tiếp tục kết nối trong lúc rollout. Tùy service, cần thông báo client reconnect/resubscribe và có cursor/replay nếu event durability quan trọng.

### 16.1. terminationGracePeriodSeconds khác probe thresholds

`terminationGracePeriodSeconds` quy định Pod shutdown deadline. Ví dụ:

```yaml
spec:
  terminationGracePeriodSeconds: 40
  containers:
    - name: app
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
```

Đây là snippet để merge vào `spec.template.spec` của Deployment, không phải manifest độc lập. `preStop` tiêu thụ một phần của 40 giây, **không tự được cộng thêm** sau grace. Sleep 5 giây chỉ hữu ích nếu cluster/ingress cần thời gian propagate và đã được đo. Không copy vào mọi app theo thói quen.

### 16.2. Graceful shutdown của Spring Boot 3.3

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Trong Boot 3.3, `server.shutdown=graceful` cần bật tường minh để embedded web server có cơ hội drain; Boot 3.4 đổi mặc định. Đây là cơ chế **khác Kubernetes probes**. Nếu graceful phase dài hơn Pod grace còn lại, kubelet có thể cưỡng chế kill trước khi app xong.

### 16.3. Không coi probe là cơ chế đảm bảo transaction

Một HTTP POST có thể commit DB rồi client nhận connection reset khi Pod dừng. Client retry có thể thực hiện giao dịch trùng nếu thiếu idempotency key. Probes giảm sự cố bằng routing/drain nhưng không cho exactly-once; cần transaction, retry policy và durable state riêng.

## 17. WebFlux, management context và protocol khác

Với Spring WebFlux, Actuator vẫn có liveness/readiness health groups, nhưng server là Reactor Netty thay vì Tomcat. Nếu một application thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot có quy tắc chọn web application type; không mặc định đổi sang reactive chỉ vì có WebFlux dependency.

Nếu application dùng riêng management port/context, Actuator health request ở đó có thể thành công khi main pipeline khác không khỏe. Additional main-port paths là cơ chế phù hợp cho HTTP web service. Với gRPC-only app, Kubernetes có gRPC probe handler theo gRPC Health Checking Protocol; đừng nghĩ Actuator HTTP health group tự là gRPC health server.

Kubernetes còn hỗ trợ TCP và exec probes:

- TCP chỉ chứng minh socket chấp nhận kết nối, không bảo đảm HTTP app trả đúng.
- Exec có thể chạy command nội bộ, nhưng distroless image có thể không có shell/curl, và việc fork process định kỳ có chi phí.
- HTTP GET thấy actual route status, phù hợp với Actuator liveness/readiness trên HTTP web app.
- gRPC probe dùng semantics riêng và cấu hình khác.

## 18. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `/actuator/health` tổng hợp cho liveness | Shared DB lỗi → restart storm | Dùng `/livez` group livenessState |
| Dùng URL luôn 200 cho readiness | Pod chưa warmup vẫn nhận traffic | Dùng `/readyz` gắn ApplicationAvailability |
| Không có startupProbe khi cold start rất lâu | Liveness kill trước khi startup hoàn tất | Startup budget đủ theo p99 |
| StartupProbe trỏ `/actuator/startup` | Endpoint không phải probe, có thể 404 | Dùng `/livez` hoặc endpoint có contract rõ |
| Cho rằng startup success = Pod Ready | Readiness chưa pass | Theo dõi cả readiness/Pod conditions |
| Liveness chờ readiness | Không có startup gate thì probes độc lập | Dùng startupProbe nếu cần |
| `/readyz` 503 nhưng `/livez` 200 | Tưởng lỗi không nhất quán | Đây có thể là trạng thái chuẩn trong warmup/drain |
| Management 9090 200 là đủ | Business 8080 có thể chết | Additional paths trên main port |
| Cấu hình `/livez` nhưng thiếu Actuator | 404 | Thêm starter và probe properties |
| Bật probe groups chỉ trong K8s, local test 404 | Khác môi trường detection | `management.endpoint.health.probes.enabled=true` |
| Probe trả 302 login | Kubelet có thể coi 302 thành công | Không redirect; áp security routes rõ |
| Probe chỉ bind 127.0.0.1 | Kubelet tới Pod IP bị refused | Bind main interface đúng |
| Timeout 1s trong JVM GC pause | False liveness restart | Tune và đo GC/CPU |
| Readiness phụ thuộc mọi external health checks | Tất cả Pods NotReady khi dependency chung lỗi | Xem fallback, criticality, scope |
| Probe query DB nặng mỗi giây | Health check làm DB quá tải | Cheap/bounded checks, giảm tần suất |
| `CrashLoopBackOff` luôn do liveness | Bỏ sót OOM, process exit, bad image | Xem events/lastState/previous logs |
| Chỉ kiểm tra local URL, không thử Pod IP | Path/port/network mismatch | Test qua mạng K8s |
| Không test rollout dưới tải | Existing connections có thể bị cắt | Graceful, ingress drain, retries |
| Xem health 200 là E2E thành công | Business API vẫn có thể fail | Synthetic monitor, SLO, tracing |

## 19. Câu hỏi tự kiểm tra

**1.** ReadinessProbe thất bại ba lần sẽ restart Pod?  
**Đáp án:** Không chỉ vì readiness; Pod trở thành NotReady và routing thay đổi. Restart thuộc startup/liveness failure hoặc process exit/nguyên nhân khác.

**2.** LivenessProbe thất bại đủ threshold sẽ thế nào?  
**Đáp án:** Kubelet restart container theo policy. Điều này không có nghĩa Service tự sửa dữ liệu nghiệp vụ.

**3.** StartupProbe thành công có đồng nghĩa readiness 200 không?  
**Đáp án:** Không. StartupProbe chỉ mở cổng cho liveness/readiness checks, còn readiness phải thành công riêng.

**4.** Boot `ApplicationStartedEvent` xảy ra trước hay sau `ApplicationRunner`?  
**Đáp án:** Trước runner. `ApplicationReadyEvent` xảy ra sau runner khi startup hoàn thành.

**5.** `LivenessState.CORRECT` cùng `ReadinessState.REFUSING_TRAFFIC` có hợp lý?  
**Đáp án:** Có. Runtime vẫn sống, nhưng app chưa sẵn sàng nhận traffic.

**6.** `/actuator/startup` có cùng chức năng Kubernetes startupProbe?  
**Đáp án:** Không. Đó là diagnostics startup steps và có thể không tồn tại nếu chưa cấu hình `ApplicationStartup`.

**7.** Kubelet HTTP probe có cần body `{"status":"UP"}`?  
**Đáp án:** Không; status 200–399 được xem success. Body là thông tin cho người/monitor khác.

**8.** DB shared down có nên đánh liveness fail để restart tất cả Pods?  
**Đáp án:** Thường không. Restart không sửa DB và có thể gây cascading failure.

**9.** App có management port 9090 nhưng main port 8080. Nên probe ở đâu?  
**Đáp án:** Nên có additional paths `/livez`/`/readyz` trên cổng 8080 để xác minh main listener, không chỉ management context.

**10.** 24 lần thử startup mỗi 5 giây nghĩa là chính xác 120.000 ms?  
**Đáp án:** Là budget xấp xỉ 120 giây; kubelet scheduling/timeout/delay có ảnh hưởng.

**11.** HTTP 302 redirect login có thể được kubelet xem success không?  
**Đáp án:** Có, vì HTTP 2xx/3xx thường được xem success; sửa probe path/security để trả health status trực tiếp.

**12.** Vì sao không đặt readiness include shared DB mặc định cho mọi service?  
**Đáp án:** Khi DB down toàn cụm, tất cả Pods có thể NotReady; nếu service có fallback, đây có thể là sự cố tệ hơn. Chọn theo business contract.

**13.** Liveness 200 trong khi một runner không bao giờ kết thúc có thể xảy ra?  
**Đáp án:** Có. Liveness có thể CORRECT sau context started, readiness REFUSING mãi. Warmup cần timeout/watchdog/fail-fast policy.

**14.** Test `RANDOM_PORT` có chứng minh Kubernetes restart không?  
**Đáp án:** Không, chỉ chứng minh HTTP routes/status; kiểm tra kubelet cần cluster staging/live environment.

**15.** Tại sao probe HTTP 200 chưa chứng minh client Internet truy cập được?  
**Đáp án:** Kubelet gọi Pod IP trực tiếp; Ingress/DNS/TLS/CDN và business request có các failure modes khác.

## 20. Checklist production

- [ ] Spring Boot 3.3 có Actuator, health probe groups và properties đúng phiên bản.
- [ ] `/livez` và `/readyz` được kiểm tra trên main application port.
- [ ] Khi dùng management port riêng, `add-additional-paths=true` và main listener được xác minh.
- [ ] Liveness không phụ thuộc DB/Redis/Kafka/external API theo mặc định.
- [ ] Readiness phản ánh khả năng nhận traffic mới, không lạm dụng mọi external health checks.
- [ ] Có startupProbe khi cold start dài hoặc biến thiên lớn.
- [ ] Startup budget, liveness threshold và readiness timeout dựa trên số liệu thật.
- [ ] Warmup có timeout/retry/fail semantics, không giữ app ở NotReady vô hạn.
- [ ] Readiness/liveness không bị redirect login/401/403 do Security config.
- [ ] Chỉ expose Actuator endpoints tối thiểu, không lộ health details.
- [ ] Kubelet dùng đúng port, path, scheme; app bind trên Pod interface.
- [ ] HTTP health checks nhanh, bounded và không tạo side effects/connection storm.
- [ ] `RANDOM_PORT` integration tests xác minh readiness chuyển 200↔503.
- [ ] Kubernetes staging tests xác minh Ready, restartCount, EndpointSlice và rollout.
- [ ] Xử lý CPU throttling/GC pauses để tránh false liveness restarts.
- [ ] Rolling update có graceful shutdown và Pod termination budget phù hợp.
- [ ] Có metrics 5xx, latency, probe failures, Pod restarts, OOMKilled, startup duration.
- [ ] Business clients có retry/idempotency và error handling khi Pod drain.
- [ ] Không coi health 200 là business E2E success; dùng synthetic monitors khi cần.
- [ ] Runbook phân biệt startup, readiness, liveness, process crash và proxy failure.

## 21. Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Actuator Endpoints và Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
2. [Spring Boot 3.3 — SpringApplication và Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
4. [Spring Boot 3.3 — ApplicationAvailability Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html)
5. [Spring Boot 3.3 — AvailabilityChangeEvent Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html)
6. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
7. [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
8. [Kubernetes — Configure Liveness, Readiness, Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
9. [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
10. [Kubernetes — Service](https://kubernetes.io/docs/concepts/services-networking/service/)
11. [Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
12. [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)

**Kết luận:** **startupProbe** bảo vệ thời gian khởi động, **readinessProbe** quyết định có nên tiếp nhận traffic, **livenessProbe** phát hiện process hỏng cần restart. **Spring Boot ApplicationAvailability/Actuator** cung cấp states và HTTP health groups; **Kubernetes** mới quyết định route và restart theo manifest. Tách readiness khỏi liveness, không cho shared dependencies quyết định liveness, đặt probes ở đúng main port và kiểm tra behavior qua HTTP/Kubernetes để tránh restart storm hoặc đưa traffic vào Pod chưa sẵn sàng.
