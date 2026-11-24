# Health endpoint và Actuator cho Spring Integration Adapters

Khi một ứng dụng Spring Boot khởi động thành công, việc HTTP server còn trả lời được **không bảo đảm** toàn bộ hệ thống tích hợp đang hoạt động. Một inbound File adapter có thể đã dừng poll, SFTP session liên tục lỗi xác thực, HTTP outbound gateway liên tục timeout, Kafka listener chưa được gán partition hoặc một JDBC poller không thể lấy bản ghi. Ngược lại, một đối tác SFTP tạm ngừng **không nhất thiết** là lý do để khởi động lại tất cả container của ứng dụng: làm vậy có thể khiến hàng đợi và backlog nặng thêm.

**Spring Boot Actuator** cung cấp các endpoint quản trị để quan sát trạng thái ứng dụng, trong đó `/actuator/health` là điểm khởi đầu quan trọng. Muốn thiết kế health cho ứng dụng **Spring Integration Adapters**, ta phải trả lời ba câu hỏi khác nhau:

1. **Liveness:** Tiến trình còn sống và có khả năng phục hồi mà không cần restart không?
2. **Readiness:** Instance hiện có sẵn sàng nhận thêm công việc từ hệ thống điều phối không?
3. **Integration dependency health:** Các adapter, poller, kết nối và tác vụ nghiệp vụ có đang hoạt động theo hợp đồng không?

Bài thuộc chương **Spring Boot** của module `SPRING_INTEGRATION_ADAPTERS`. Module tìm hiểu cách kết nối hệ thống ngoài bằng **inbound/outbound adapter, gateway, poller và MessageChannel** với File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, cùng hợp đồng message, lỗi và vòng đời kết nối. Nội dung này thiết kế health/observability cho chính những luồng tích hợp đó, không chỉ cho một REST API thông thường.

> **Nguyên tắc:** “Ứng dụng đang chạy” không có nghĩa “dữ liệu đang lưu chuyển đúng”; “đối tác bên ngoài bị lỗi” cũng không tự động có nghĩa “instance này cần bị restart”. Health phải phản ánh **mục đích của tín hiệu và hành động mà tín hiệu kích hoạt**.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt Actuator health, liveness/readiness, startup probe, metrics, traces, logs và business-level checks.
2. Giải thích `HealthIndicator`, `HealthContributor`, `CompositeHealthContributor`, status aggregation và HTTP status mapping.
3. Cấu hình `spring-boot-starter-actuator`, `management.endpoints.web.exposure.include` và `management.endpoint.health.*`.
4. Thiết kế health groups theo vai trò instance và rủi ro của các dependency.
5. Sử dụng Kubernetes liveness/readiness/startup probes mà không tạo restart loop khi đối tác lỗi.
6. Xây một `HealthIndicator` thụ động cho poller, phân biệt **poll thành công nhưng không có message** với **poller không chạy**.
7. Theo dõi File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC, tách kết nối, backlog, xử lý và kết quả nghiệp vụ.
8. Tránh health checks tốn kém, gây side effect hoặc làm lộ thông tin nhạy cảm.
9. Kiểm thử kết quả health/HTTP status, trạng thái trước và sau startup, outage và recovery.
10. Lập runbook, test matrix, SLO và checklist cho ứng dụng tích hợp khi triển khai vận hành.

## 2. Actuator là gì và Health endpoint giải quyết gì?

Actuator là tập hợp các thành phần của Spring Boot giúp **quản lý và quan sát ứng dụng đang chạy**. Tùy dependency, phiên bản và cấu hình, Actuator có thể cung cấp health, info, metrics, loggers, mappings, environment, beans, thready/heap diagnostic và các endpoint đặc thù khác. **Không có nghĩa tất cả endpoint đều được bật hoặc public trên HTTP.**

`/actuator/health` trả về **một trạng thái tổng hợp** dựa trên các health contributor được đăng ký. Nó phục vụ cả giám sát con người lẫn chương trình điều phối, nhưng không phải một API đặc tả toàn bộ nghiệp vụ. Ví dụ:

~~~json
{
  "status": "UP"
}
~~~

Điều này chỉ nói các contributor trong **phạm vi health group đang được truy vấn** dẫn tới trạng thái tổng hợp `UP`. Không tự suy rằng:

- Mọi hệ thống ngoài đều đã được kiểm tra;
- Kafka lag bằng 0;
- Tất cả SFTP files đã nhập;
- Không có message lỗi trong DLQ;
- HTTP outbound đã hoàn tất mọi transaction;
- Không có đơn hàng đang chờ đối soát.

### 2.1. Các loại tín hiệu không nên nhập làm một

| Tín hiệu | Câu hỏi trả lời | Hành động thường phù hợp |
|---|---|---|
| **Liveness** | Có nên restart tiến trình vì bị hỏng không thể tự phục hồi? | Kubelet/agent restart instance nếu điều kiện thật sự fatal. |
| **Readiness** | Instance có nên được chọn nhận thêm traffic/công việc không? | Đưa ra hoặc loại khỏi tuyến traffic. |
| **Dependency health** | DB/broker/partner có khả dụng ở mức cần thiết? | Điều tra, retry/backoff, failover, circuit breaker. |
| **Poller/consumer state** | Endpoint có chạy và còn tiến hành poll/consume không? | Restart endpoint có kiểm soát, sửa scheduling/connection. |
| **Data-flow metrics** | Có throughput, backlog, độ trễ, lỗi, duplicate? | Scale, tuning, điều tra nghiệp vụ. |
| **Business verification** | Side effect cuối đã thực sự được xác nhận? | Reconcile, redrive, hỗ trợ nghiệp vụ. |

Health trả lời một câu hỏi **định tính có hành động đi kèm**; metrics/traces giúp trả lời **vì sao** và **mức độ ảnh hưởng**.

## 3. Liveness, readiness và startup: không đánh đồng

### 3.1. Liveness

Liveness phù hợp để phát hiện instance bị kẹt hoặc hỏng đến mức **restart có khả năng cải thiện trạng thái**. Không nên cho toàn bộ upstream HTTP, SFTP hoặc Kafka vào liveness chỉ vì chúng quan trọng. Một partner outage có thể ảnh hưởng mọi instance; việc Kubernetes liên tục restart những instance khỏe sẽ gây thêm tải và làm mất trạng thái trong bộ nhớ.

Ví dụ liveness có thể dựa trên `livenessState` do Spring Boot quản lý, kết hợp rất ít điều kiện nội bộ thật sự fatal theo thiết kế. Nếu một failure có thể tự hồi phục qua reconnect/backoff, thường **không nên biến nó thành liveness DOWN**.

### 3.2. Readiness

Readiness cho biết instance có sẵn sàng nhận workload hay không. Một instance đang startup hoặc graceful shutdown có thể `REFUSING_TRAFFIC`, trong khi process vẫn sống.

Tùy kiến trúc, DB bắt buộc có thể là điều kiện readiness. Nhưng việc đưa một **shared dependency** vào readiness của mọi instance cũng cần xem xét: nếu tất cả instances đồng loạt bị loại khỏi tuyến, dịch vụ có thể không còn nơi trả response lỗi hữu ích hoặc phục hồi.

### 3.3. Startup probe

Kubernetes `startupProbe` cho phép ứng dụng có thời gian khởi động dài mà không bị liveness probe restart quá sớm. Nó không thay thế readiness, và không phải một loại `HealthIndicator` bắt buộc của Spring Boot.

### 3.4. Một ví dụ tình huống

| Tình huống | Liveness | Readiness | Dependency/business alert |
|---|---|---|---|
| Ứng dụng đang bootstrap | Thường chưa đánh giá hoặc process sống | Chưa sẵn sàng | Theo dõi startup. |
| Kafka broker tạm unavailable, consumer tự reconnect | Vẫn sống | Tùy vai trò instance | Broker outage, lag, retry. |
| Partner HTTP trả 503 | Vẫn sống | Thường không nên tự loại mọi API instance | Partner failure/circuit breaker. |
| SFTP inbound poller bị stop ngoài kế hoạch | Tiến trình có thể còn sống | Tùy service có chỉ làm ingestion | Cảnh báo endpoint stopped + backlog. |
| DB bắt buộc mất kết nối | Vẫn sống | Có thể refusing, theo policy | DB outage, queue/inbox safety. |
| Worker deadlocked không thể tiến triển | Có thể là liveness failure nếu phát hiện đáng tin | Không sẵn sàng | Thread/lock diagnostic. |
| Graceful shutdown | Vẫn sống trong lúc drain | Không nhận traffic mới | Theo dõi in-flight. |

**Không có một bảng liveness/readiness đúng cho mọi topology.** Một ứng dụng chỉ chạy file poller, không phục vụ HTTP clients, có cách xử lý readiness khác API gateway. Cần biết Kubernetes readiness có thực sự điều khiển việc phân phối workload ấy không.

## 4. Thành phần cấu thành Health trong Spring Boot

| API/khái niệm | Vai trò |
|---|---|
| `HealthIndicator` | Contributor có phương thức `health()` trả `Health`. |
| `ReactiveHealthIndicator` | Biến thể phản ứng phù hợp reactive stack. |
| `HealthContributor` | Abstraction chung cho health contributors. |
| `CompositeHealthContributor` | Gom nhóm contributor lồng nhau. |
| `Health` | Chứa `Status` và thông tin detail (khi được hiển thị). |
| `Status` | Các trạng thái như `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN`. |
| `HealthEndpoint` | Endpoint Actuator tổng hợp health. |
| **Health group** | Tập contributor và chính sách hiển thị/status riêng cho từng mục đích. |
| **Status aggregator** | Quyết định tổng hợp trạng thái của các contributor. |
| **HTTP status mapper** | Ánh xạ status sang mã HTTP để probe/monitor hiểu. |

### 4.1. Ý nghĩa các trạng thái thường gặp

| Status | Nghĩa gợi ý | HTTP mặc định thường gặp |
|---|---|---|
| `UP` | Đủ điều kiện đã kiểm tra. | 200 |
| `DOWN` | Một điều kiện cần thiết không đạt. | 503 |
| `OUT_OF_SERVICE` | Cố ý không nhận phục vụ. | 503 |
| `UNKNOWN` | Chưa có đủ bằng chứng để kết luận. | Thường là 200 nếu không có mapping tùy biến. |

**Lưu ý:** status tùy biến và health group có thể có aggregation/HTTP mapping riêng. Khi tự cấu hình mapping, phải kiểm tra phản hồi HTTP thực tế; **không mặc định mọi status lạ tự dẫn tới 503**. Với Kubernetes, HTTP code mới là tín hiệu probe tiêu thụ, nên một `UNKNOWN` xuất hiện trong JSON nhưng HTTP 200 có thể không chặn readiness như kỳ vọng.

### 4.2. Tổng hợp health không đồng nghĩa “tất cả thật sự đã được kiểm tra”

~~~mermaid
flowchart TD
    HTTP["GET /actuator/health"] --> AGG["Health aggregation"]
    AGG --> DB["db HealthIndicator"]
    AGG --> DISK["diskSpace HealthIndicator"]
    AGG --> CUSTOM["custom poller/partner indicator"]
    AGG --> STATUS["UP / DOWN / OUT_OF_SERVICE / UNKNOWN"]
    STATUS --> RESP["JSON + HTTP status"]
~~~

Thành phần nào có mặt phụ thuộc vào **auto-configuration, bean trong context, health group và cấu hình enable/disable**. Không phải mọi transport trong Spring Integration đều có sẵn một health indicator tự động đủ sâu; đặc biệt không suy “có Kafka client/SFTP adapter” nghĩa `/health` đã kiểm tra end-to-end của chúng.

## 5. Maven và Gradle: bổ sung Actuator

Với một dự án đã dùng Spring Boot BOM hoặc dependency management phù hợp, phụ thuộc tối thiểu:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.integration:spring-integration-test")
}
~~~

Đối với các transport thật, thêm dependency adapter tương ứng (File, SFTP, JMS, AMQP, Kafka, JDBC, HTTP) và connector/driver. Với Prometheus, còn cần registry phù hợp, chẳng hạn `micrometer-registry-prometheus` ở phiên bản tương thích; Actuator một mình không bảo đảm endpoint `/actuator/prometheus` hoạt động.

**Phiên bản:** ví dụ được trình bày theo các API phổ biến của Spring Boot và Spring Integration hiện đại, đặc biệt dòng có health groups và availability states. Tên endpoint, tùy chọn YAML và chữ ký API có thể thay đổi theo phiên bản; khi triển khai phải xác nhận với dependency versions thực tế. Không tự cài cùng lúc nhiều version không tương thích.

## 6. Cấu hình Actuator tối thiểu an toàn

~~~yaml
spring:
  application:
    name: shipment-integration

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
~~~

Với cấu hình này, mục tiêu là có health endpoint phục vụ kiểm tra cơ bản và các health probes được bật trên phiên bản Boot hỗ trợ.

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Ví dụ phản hồi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

Đây là **mẫu**, không phải kết quả đã chạy trên dự án của người học. Content type cụ thể phụ thuộc phiên bản và content negotiation. Khi probes chưa được kích hoạt hoặc contributor không tồn tại, một URL có thể không khả dụng; phải xem response thật, không lấy sample làm bằng chứng.

### 6.1. Health details không dành cho public internet

`show-details: never` giảm nguy cơ lộ thông tin vận hành từ phản hồi. Khi cần xem component details, có thể dùng mức `when_authorized`, cấu hình roles và Spring Security phù hợp. Không bật `always` trên public endpoint mà chưa có network/authentication controls.

### 6.2. Đừng expose mọi endpoint để tiện debug

Không dùng:

~~~yaml
# KHÔNG khuyến nghị đưa lên internet mà không có kiểm soát.
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Các endpoint cấu hình, environment, logging và diagnostics có thể tiết lộ metadata hệ thống hoặc hỗ trợ thao tác quản trị. Chỉ expose những endpoint thật sự cần, qua network policy và quyền hạn thích hợp. Health endpoint dùng cho kubelet/load balancer nên có **đường truy cập nội bộ**, không mặc định public toàn internet.

## 7. Health groups: cùng một ứng dụng, nhiều câu hỏi khác nhau

Một ứng dụng có thể có nhóm:

- `liveness`: instance cần restart hay không;
- `readiness`: có nên nhận thêm traffic không;
- `integrations`: tình trạng các dependency/adapter theo dõi vận hành;
- `criticalDependencies`: chỉ những dependency thật sự cần để phục vụ workload.

### 7.1. Tạo group riêng cho integration

~~~yaml
management:
  endpoint:
    health:
      group:
        integrations:
          include: partnerSftp,partnerHttp,db
          show-details: when_authorized
          roles: OPS
~~~

Ví dụ này **giả định** context có contributor IDs `partnerSftp`, `partnerHttp` và `db`; với custom bean có tên `partnerSftpHealthIndicator`, Spring Boot thường rút gọn suffix `HealthIndicator` thành contributor ID `partnerSftp`. Nếu dùng tên bean khác, group sẽ phải dùng ID thực tế. Trong môi trường có cấu hình kiểm tra thành viên group khắt khe, nhóm không chứa ID tồn tại có thể làm startup lỗi; hãy xác minh bằng test context.

Truy vấn:

~~~bash
curl -i http://localhost:8080/actuator/health/integrations
~~~

Không nhất thiết đưa toàn bộ group `integrations` vào readiness; tránh một partner lỗi kéo tất cả instance khỏi traffic khi ứng dụng vẫn có thể phục vụ tác vụ khác.

### 7.2. Readiness chỉ gồm thành phần thật sự bắt buộc

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
~~~

Đây là **một lựa chọn kiến trúc** khi database là điều kiện bắt buộc của workload. Nó không phải “best practice cho mọi ứng dụng”. Các readiness/liveness groups mặc định của Spring Boot thường tập trung vào availability states, **không tự cộng mọi external systems**. Nếu cần mở rộng, hãy làm chủ đích và test hệ quả khi dependency chung bị outage.

### 7.3. Khi app có nhiều vai trò

Nếu cùng một process vừa xử lý HTTP API vừa chạy poller SFTP, readiness của HTTP traffic **không chắc** là công cụ thích hợp để chặn SFTP inbound. Hãy xác định:

1. Endpoint/quy trình nào thực sự phụ thuộc component đó.
2. Workload controller nào đọc readiness.
3. Khi probe DOWN, có tuyến thay thế hoặc worker khác xử lý không.
4. Một dependency failure diện rộng có khiến mọi instance bị remove không.
5. Có cần tách deployment API và ingestion worker để điều phối độc lập không.

## 8. Kubernetes probes và management port

Ví dụ deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shipment-integration
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shipment-integration
  template:
    metadata:
      labels:
        app: shipment-integration
    spec:
      containers:
        - name: app
          image: example/shipment-integration:1.0
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
~~~

**Đây là manifest minh họa**, không phải giá trị SLO chung. Phải tinh chỉnh `failureThreshold`, `periodSeconds`, `timeoutSeconds`, startup window, graceful termination và endpoint path theo đặc tính ứng dụng. Docker image, namespace, service account và policies của ví dụ chưa đầy đủ để triển khai production.

### 8.1. Management port riêng có thể che lỗi chính

Nếu `management.server.port` khác server port chính, Actuator có thể vẫn phản hồi khi listener HTTP chính bị hỏng. Khi yêu cầu probe phản ánh main web server, Spring Boot ở các phiên bản hỗ trợ có tùy chọn:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Trên các phiên bản hỗ trợ, liveness/readiness có thể xuất hiện thêm tại **`/livez` và `/readyz` trên main server port**. Cần kiểm tra endpoint thực tế bằng integration test; không tự giả định mọi release hỗ trợ property hoặc cùng default mapping. Nếu dùng management port riêng, đừng cấu hình kubelet gọi main-port paths khi chưa chắc chúng được expose.

### 8.2. Readiness không quản lý toàn bộ queue consumer

Một Kafka consumer container hoặc inbound File poller có thể tiếp tục chạy độc lập với HTTP load balancer. Kubernetes readiness DOWN **không mặc nhiên dừng poller, ngừng đọc Kafka hoặc pause JMS listener**. Muốn ngăn nhận thêm việc từ broker, cần logic pause/stop/container lifecycle riêng; test cả hệ quả ACK/offset và backlog.

## 9. HealthIndicator tự viết: chọn loại bằng chứng

Một custom `HealthIndicator` phải trả lời **điều gì được kiểm tra**, không chỉ return `UP` khi bean được tạo thành công.

| Chiến lược | Điểm mạnh | Rủi ro |
|---|---|---|
| **Active check** | Gọi `ping`/query tới nguồn để biết connectivity hiện tại. | Gây tải, timeout, auth side effect, nhiều probe đồng thời. |
| **Passive state** | Đọc trạng thái từ những lần I/O/poll thật. | Có thể stale; không có traffic không có nghĩa lỗi. |
| **Cached active check** | Giới hạn tần suất gọi nguồn ngoài. | Phải xác định TTL, stale/unknown semantics. |
| **Heartbeat của poller** | Phát hiện scheduler vẫn gọi source, kể cả khi không có message. | Không chứng minh target xử lý end-to-end. |
| **Lifecycle state** | Bean/endpoint `isRunning()`. | Running không đồng nghĩa message flowing. |
| **Backlog/lag check** | Đo sức khỏe xử lý/độ trễ. | Metric có thể phù hợp hơn cờ UP/DOWN nhị phân. |
| **Canary/synthetic transaction** | Gần business outcome nhất. | Có side effect/chi phí, cần account/fixture riêng. |

### 9.1. Bốn trạng thái dễ nhầm khi giám sát poller

1. **Poller còn chạy, nguồn rỗng:** `receive()` trả `null` bình thường.
2. **Poller không được gọi:** schedule ngừng, endpoint stop hoặc thread pool kẹt.
3. **Poller được gọi nhưng source throw:** lỗi kết nối, quyền, schema...
4. **Poll thành công, downstream fail:** đã nhận message nhưng chưa xử lý thành công.

Một counter chỉ tăng khi **nhận được message** không phân biệt được trường hợp 1 và 2. Muốn đo heartbeat, phải **ghi nhận mỗi lần poll nguồn thành công kể cả trả null**.

## 10. Thiết kế custom indicator theo tín hiệu thụ động

Ta xây một `PollMonitor` thread-safe, ghi nhận lần poll nguồn thành công, lần poll lỗi và thời điểm. `HealthIndicator` chỉ **đọc snapshot**, không mở SFTP connection mỗi khi Actuator bị gọi.

~~~mermaid
flowchart LR
    SCHED["Poller scheduler"] --> SRC["Observed MessageSource"]
    SRC --> REAL["Real File/SFTP/JDBC source"]
    SRC --> MON["PollMonitor<br/>last success/failure"]
    HEALTH["GET /actuator/health/integrations"] --> IND["PollHealthIndicator"]
    IND --> MON
    IND --> JSON["UP / DOWN / UNKNOWN"]
    REAL --> CH["MessageChannel"]
    CH --> HANDLER["Business handler"]
~~~

### 10.1. Định nghĩa một snapshot bất biến

~~~java
package example.integration.health;

import java.time.Instant;

public record PollSnapshot(
        Instant lastSuccessfulPoll,
        Instant lastFailedPoll,
        long consecutiveFailures) {
}
~~~

### 10.2. Monitor dùng Clock để kiểm thử được

~~~java
package example.integration.health;

import java.time.Clock;
import java.util.concurrent.atomic.AtomicReference;

public final class PollMonitor {
    private final Clock clock;
    private final AtomicReference<PollSnapshot> current =
            new AtomicReference<>(
                    new PollSnapshot(null, null, 0));

    public PollMonitor(Clock clock) {
        this.clock = clock;
    }

    public void successfulPoll() {
        current.updateAndGet(old -> new PollSnapshot(
                clock.instant(),
                old.lastFailedPoll(),
                0));
    }

    public void failedPoll() {
        current.updateAndGet(old -> new PollSnapshot(
                old.lastSuccessfulPoll(),
                clock.instant(),
                old.consecutiveFailures() + 1));
    }

    public PollSnapshot snapshot() {
        return current.get();
    }
}
~~~

Đây là monitor **thụ động**: nó không biết SFTP credential, không gọi API ngoài và không đọc DB. `AtomicReference` giữ snapshot bất biến nên khi scheduler cập nhật, Actuator đọc được một tập trường nhất quán.

**Hạn chế có chủ ý:** số `consecutiveFailures` phản ánh lỗi nhận nguồn đã instrument, không phản ánh lỗi downstream handler; nó không phải Kafka lag hoặc business failure count.

## 11. HealthIndicator đọc PollMonitor, không kích hoạt side effect

~~~java
package example.integration.health;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class PollHealthIndicator implements HealthIndicator {
    private final PollMonitor monitor;
    private final Clock clock;
    private final Duration maxSilence;

    public PollHealthIndicator(
            PollMonitor monitor,
            Clock clock,
            Duration maxSilence) {
        this.monitor = monitor;
        this.clock = clock;
        this.maxSilence = maxSilence;
    }

    @Override
    public Health health() {
        PollSnapshot state = monitor.snapshot();
        Instant lastSuccess = state.lastSuccessfulPoll();

        if (lastSuccess == null) {
            return Health.unknown()
                    .withDetail("reason", "NO_SUCCESSFUL_POLL_YET")
                    .build();
        }

        if (clock.instant().isAfter(lastSuccess.plus(maxSilence))) {
            return Health.down()
                    .withDetail("reason", "POLL_HEARTBEAT_STALE")
                    .withDetail("consecutiveFailures",
                            state.consecutiveFailures())
                    .build();
        }

        return Health.up()
                .withDetail("reason", "RECENT_SUCCESSFUL_POLL")
                .withDetail("consecutiveFailures",
                        state.consecutiveFailures())
                .build();
    }
}
~~~

### 11.1. Vì sao chưa có poll trả UNKNOWN?

Trước lần poll đầu, app **chưa có bằng chứng** đủ để tuyên bố inbound source đang hoạt động. Nhưng nếu poller chạy **mỗi 24 giờ**, “chưa có poll” lúc ứng dụng mới khởi động không đồng nghĩa instance bị lỗi. Vì vậy ví dụ trả `UNKNOWN` để phản ánh giới hạn bằng chứng.

**Cực kỳ quan trọng:** Nếu indicator này được đưa vào Kubernetes readiness với mục tiêu chặn nhận traffic, `UNKNOWN` có thể vẫn map HTTP 200 theo mapping mặc định; **không được xem nó là readiness gate** mà chưa xác minh status aggregation/HTTP mapping. Nếu business bắt buộc chặn cho tới poll đầu, hãy định nghĩa startup grace/requirement và status trả về có HTTP code rõ ràng, không phụ thuộc default bất ngờ.

### 11.2. Khi nào heartbeat stale?

`maxSilence` phải được chọn dựa trên **lịch poll và sự dao động có thể chấp nhận**. Với poller mỗi 30 giây, ngưỡng 3 phút có thể hợp lý trong một hệ thống; với cron mỗi ngày, ngưỡng 3 phút sẽ liên tục `DOWN` dù mọi thứ bình thường. Chưa có baseline thì đây chỉ là ví dụ, không phải SLO mặc định.

### 11.3. Health UP không chứng minh business outcome

Trong code này, `UP` chứng minh **đã có ít nhất một poll gần đây trả về bình thường**. Nó không chứng minh:

- Nguồn chứa message mới.
- File đã đủ bytes hoặc đúng schema.
- HTTP outbound thành công.
- Kafka offset đã commit.
- DB side effect cuối cùng đã được xác nhận.

Những câu hỏi đó cần health indicators/metrics/reconciliation riêng.

## 12. Quan sát MessageSource: poll rỗng vẫn là một lần poll

Để cập nhật `PollMonitor` đúng chỗ, tạo decorator quanh `MessageSource<T>`. Decorator gọi nguồn thật, ghi kết quả poll và **không thay đổi** payload/header hoặc nuốt exception.

~~~java
package example.integration.health;

import java.util.Objects;

import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;

public final class ObservedMessageSource<T>
        implements MessageSource<T> {

    private final MessageSource<T> delegate;
    private final PollMonitor monitor;

    public ObservedMessageSource(
            MessageSource<T> delegate,
            PollMonitor monitor) {
        this.delegate = Objects.requireNonNull(delegate);
        this.monitor = Objects.requireNonNull(monitor);
    }

    @Override
    public Message<T> receive() {
        try {
            Message<T> message = delegate.receive();
            monitor.successfulPoll(); // Kể cả message == null.
            return message;
        } catch (RuntimeException ex) {
            monitor.failedPoll();
            throw ex; // Giữ nguyên retry/error semantics.
        }
    }
}
~~~

### 12.1. Vì sao exception phải được ném tiếp?

Nếu health wrapper bắt lỗi SFTP/JDBC rồi trả `null`, poller tưởng nguồn đang rỗng, trong khi adapter có thể đang mất kết nối. Khi đó:

- Error channel/retry advice không có cơ hội xử lý lỗi thực.
- Health có thể còn `UP` nếu wrapper gọi `successfulPoll()` sai.
- Vận hành khó phân biệt “không có dữ liệu” với “không nhận được dữ liệu”.
- Backlog tăng nhưng không có cảnh báo.

Wrapper chỉ **quan sát**, không làm thay đổi nghĩa của `MessageSource.receive()`.

### 12.2. Những ngoại lệ của mẫu decorator

Ví dụ bắt `RuntimeException` phù hợp cho phần lớn API `receive()` đồng bộ; nó không tự bao quát mọi dạng lỗi. Nếu nguồn/framework **bắt và xử lý exception bên trong rồi trả null**, wrapper không nhận được thông tin lỗi; phải gắn observation vào error handler hoặc transport metric ở đúng tầng.

Nếu có `MessageSource` reactive/asynchronous hoặc kết nối được thiết kế kiểu streaming, cách quan sát cần phù hợp lifecycle của nó; không áp decorator này một cách máy móc cho mọi inbound adapter.

### 12.3. Không chặn scheduler bằng health check

Decorator chỉ cập nhật một `AtomicReference`, gần như không tăng network round-trip. Nếu mỗi lần poll lại gọi thêm `sftpSessionFactory.getSession()` để “xác minh sức khỏe”, chính health logic có thể gây load và thay đổi failure mode; cần tránh.

## 13. Đăng ký bean và health contributor ID

Một cấu hình minh họa cho nguồn SFTP đã được tạo bởi module integration:

~~~java
package example.integration.health;

import java.io.File;
import java.time.Clock;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.core.MessageSource;

@Configuration
public class PollHealthConfiguration {

    @Bean
    Clock healthClock() {
        return Clock.systemUTC();
    }

    @Bean
    PollMonitor sftpPollMonitor(Clock healthClock) {
        return new PollMonitor(healthClock);
    }

    @Bean(name = "partnerSftpHealthIndicator")
    PollHealthIndicator partnerSftpHealthIndicator(
            PollMonitor sftpPollMonitor,
            Clock healthClock) {
        return new PollHealthIndicator(
                sftpPollMonitor,
                healthClock,
                Duration.ofMinutes(3));
    }

    @Bean(name = "observedSftpFileSource")
    MessageSource<File> observedSftpFileSource(
            @Qualifier("sftpFileSource")
            MessageSource<File> actualSource,
            PollMonitor sftpPollMonitor) {
        return new ObservedMessageSource<>(
                actualSource, sftpPollMonitor);
    }
}
~~~

**Điều kiện của ví dụ:** `sftpFileSource` là **bean nguồn thực do cấu hình SFTP inbound khác cung cấp**. Nếu bean đó không tồn tại, application context không thể khởi tạo; phần này là mẫu wiring, không tự dựng SFTP connection hoặc credentials.

### 13.1. Dùng observed source trong IntegrationFlow

~~~java
// Ví dụ thành phần của @Configuration:
@Bean
IntegrationFlow sftpInboundFlow(
        @Qualifier("observedSftpFileSource")
        MessageSource<File> observedSftpFileSource) {
    return IntegrationFlow
            .from(observedSftpFileSource,
                    endpoint -> endpoint
                            .id("sftpInboundEndpoint")
                            .poller(Pollers
                                    .fixedDelay(Duration.ofSeconds(30))
                                    .maxMessagesPerPoll(1)))
            .channel("importedFiles")
            .get();
}
~~~

Imports `IntegrationFlow`, `Pollers`, `File`, `Duration`, `MessageSource` và `@Qualifier` cần bổ sung trong source thật. Đây là một fragment thiết kế; kênh `importedFiles` phải được đăng ký và có consumer. Đừng tạo hai pollers cùng đọc nguồn chỉ để health.

### 13.2. Global /health và group đều có thể bị ảnh hưởng

Khi contributor `partnerSftpHealthIndicator` được đăng ký, nó có thể nằm trong kết quả **global `/actuator/health`**, không chỉ group `integrations`. Nếu indicator `DOWN` trong một partner outage, global status có thể thành `DOWN`. Vì thế:

- Kubernetes liveness nên gọi `/actuator/health/liveness`, **không gọi global `/health` chỉ vì URL ngắn hơn**.
- Readiness group phải được định nghĩa có chủ đích.
- Các monitor/operator muốn thấy tích hợp dùng `/health/integrations` hoặc metric/alert riêng.
- Nếu custom indicator chỉ phục vụ chẩn đoán nhưng làm global status bất lợi, cân nhắc cấu trúc contributor, policy aggregation, custom management endpoint/metrics thay vì đặt `HealthIndicator` nào cũng trở thành dependency fatal.

Thêm một indicator thường tạo ảnh hưởng tổng hợp ngoài ý muốn; cần test cả **global, liveness, readiness và diagnostic group**.

## 14. Sự khác biệt giữa adapter running và message processing thành công

Với endpoint Spring Integration, một lifecycle interface như `SmartLifecycle` có thể cho biết `isRunning()`. Nhưng:

~~~text
Endpoint isRunning() == true
    != scheduler đã poll gần đây
    != nguồn ngoài có thể truy cập
    != message đã được xử lý
    != downstream side effect đã xác nhận
~~~

Mẫu health chỉ kiểm tra `isRunning()` có thể bị false positive khi:

- Scheduler thread pool bị chiếm dụng.
- Source liên tục trả `null` do filter sai.
- Kafka listener chưa có partition assignment.
- Handler bị lỗi nhưng endpoint vẫn running.
- Worker đang backlog nhiều giờ.

### 14.1. Một mô hình quan sát bốn tầng

~~~mermaid
flowchart LR
    LIFE["Lifecycle<br/>endpoint running"] --> P["Poll/Consume<br/>attempts"]
    P --> MSG["Message processing<br/>success/error"]
    MSG --> BIZ["Business confirmation<br/>target readback"]
~~~

| Tầng | Điểm đo | Có thể chứng minh |
|---|---|---|
| Lifecycle | `isRunning()`, assignment, subscription | Endpoint/consumer được start/assigned theo nghĩa riêng. |
| Source activity | Lần poll/receive gần nhất, connect failures | Scheduler/source còn hoạt động. |
| Processing | Handler throughput, error, retry, DLQ | Message đã đi vào và qua các bước xử lý. |
| Business outcome | DB state, outbound ACK + reconciliation | Kết quả cuối đã được xác minh. |

Không nhất thiết tạo bốn health indicators đều trả DOWN; một số chỉ số thích hợp hơn với **metrics và dashboard**.

## 15. File inbound adapter: health của nguồn cục bộ

File polling thường không cần network connection; filesystem và readiness của file mới là yếu tố chính.

### 15.1. Những điều có thể kiểm tra

- Thư mục input có tồn tại, đúng loại directory và đúng quyền truy cập?
- Poller có chạy theo lịch, kể cả khi không có file?
- Có lỗi `AccessDeniedException`, disk-full hoặc path mismatch?
- Có số file `*.ready` đang chờ quá ngưỡng không?
- Có nhiều file `*.tmp` tồn tại quá lâu, gợi ý producer đang kẹt?
- Metadata filter có ghi nhận và đọc lại đúng qua restart?

**Không dùng health endpoint để quét/đọc toàn bộ thư mục hàng triệu files mỗi vài giây.** File count/backlog age nên được cập nhật bằng một scheduled monitor có giới hạn hoặc lấy từ metrics đã thu thập.

### 15.2. Thiết kế theo ý nghĩa

| Tín hiệu | Có nên quyết định liveness? | Nên quan sát ở đâu? |
|---|---|---|
| Directory không tồn tại | Thường không | Integration diagnostic; readiness nếu ingestion bắt buộc. |
| Poller stopped ngoài kế hoạch | Không mặc định | Endpoint metric/alert, có thể readiness worker. |
| Không có file mới trong ngày | Không, nếu đối tác không gửi | Business schedule/SLO metric. |
| File ready pending quá hạn | Không | Backlog/oldest pending alert. |
| Disk full không thể ghi file tạm | Không tự quyết định | Disk health, integration alerts; policy readiness riêng. |

### 15.3. Khi cần kiểm tra readiness của file directory

Một active check có thể kiểm tra `Files.isDirectory(path)` và `Files.isReadable(path)`, nhưng **đừng ghi file thử vào thư mục production theo mỗi request `/health`**. Ghi file có thể kích hoạt chính inbound adapter, tạo dữ liệu giả hoặc gây tranh chấp quyền.

## 16. SFTP inbound/outbound: tránh biến health thành máy tải file

SFTP có nhiều loại lỗi: DNS, TCP, SSH handshake, host key, authentication, session pool, remote permission, directory, rate-limit và partial transfer.

| Health signal | Cách đo phù hợp | Rủi ro |
|---|---|---|
| Session connection | Cached active check hoặc thụ động theo I/O thật | Mở nhiều session khi probe dày. |
| Host key/authentication | Error category từ kết nối thật | Không nên retry credentials sai vô hạn. |
| Poll success | `MessageSource.receive()` success kể cả null | Không chứng minh có file mới. |
| Download success | Transfer count/bytes và completion | Không chứng minh CSV business valid. |
| Remote backlog | List/cached scan có giới hạn | Large directories gây tải SFTP. |
| Partial file | File readiness/rename policy | Thất bại có thể không làm endpoint stop. |
| Output upload confirmation | Remote readback/file metadata khi workflow yêu cầu | Cần idempotency để không upload trùng. |

**Không đưa việc SFTP remote directory có ít nhất một file vào liveness.** Đối tác có thể không gửi file hôm đó nhưng kết nối vẫn khỏe. Hãy đo **poll attempt success** riêng với **data arrival SLO**.

### 16.1. Khi nào nên dùng UNKNOWN?

Nếu poller chỉ chạy cron hằng ngày và chưa tới thời điểm poll đầu, trạng thái nguồn có thể `UNKNOWN`. Hãy xác định:

1. Có cần một startup validation riêng không?
2. Lần kết nối gần nhất đã cách bao lâu?
3. Có bắt buộc phải sẵn sàng ngay để nhận file không?
4. Khi đối tác có maintenance window, trạng thái nên là degraded hay outage?

Không dùng cùng một ngưỡng heartbeat 2 phút cho mọi SFTP partner dù lịch poll khác nhau.

## 17. HTTP outbound gateway: timeout không đồng nghĩa đối tác đã thất bại

HTTP outbound gateway trong Spring Integration có thể gọi API đồng bộ, chờ response rồi chuyển thành message reply. Health của partner HTTP có thể được quan sát qua:

- request count, success/error codes và response latency;
- connect timeout/read timeout và số attempt retry;
- circuit breaker state;
- last successful request, rate-limit 429;
- số request có kết quả chưa xác định;
- backlog/gateway pending calls.

### 17.1. Active probe cần an toàn

Một HTTP health indicator **không nên gọi POST tạo đơn hàng thật** chỉ để kiểm tra server còn sống. Nếu partner có `GET /health` hoặc `HEAD /ping` được contract bảo đảm **read-only, không gây side effect**, có thể dùng active check có timeout, caching và rate-limit. Nhưng:

- Endpoint health của partner có thể `UP` dù business API bị lỗi.
- Check cần credential riêng và không được log token.
- Response 200 của health URL không chứng minh request nghiệp vụ thành công.
- HTTP 401/403 của health URL có thể do policy/credential, không phải server chết.

### 17.2. Unknown outcome sau POST

Nếu POST đến server và client read timeout, server có thể đã ghi dữ liệu nhưng response bị mất. Dù health indicator ghi lỗi timeout, **không được tự retry operation có side effect** khi thiếu idempotency key hoặc readback.

Để vận hành:

- Health chỉ phản ánh kết nối/độ sẵn sàng theo policy.
- Metrics ghi unknown outcome.
- Reconciliation kiểm tra trạng thái thực tại target.
- Gateway retry có hạn và tuân theo safety contract.

## 18. JDBC/database: health kết nối khác health xử lý batch

Spring Boot có thể auto-configure `db` health contributor khi có DataSource phù hợp, tùy cấu hình. Contributor dạng này thường kiểm tra khả năng truy cập DB ở mức connection/validation query, **không có nghĩa tất cả SQL nghiệp vụ hay data consistency đều đúng**.

### 18.1. Những câu hỏi tách biệt

| Câu hỏi | Loại kiểm tra |
|---|---|
| DB connection có thiết lập được không? | DB health/connection validation. |
| DB có quyền đọc/ghi bảng inbox/outbox không? | Integration/permission test riêng. |
| Poller có query được record READY? | Source execution metric/health. |
| Có row bị lock quá lâu? | DB contention metric/alert. |
| Có stale outbox events? | Backlog/oldest pending SLO. |
| Có thể commit transaction nghiệp vụ? | Integration transaction test + monitoring. |
| Một row bị xử lý hai lần? | Idempotency/reconciliation metrics. |

### 18.2. Không chạy query nặng ở mỗi /health

Không dùng:

~~~sql
-- Không nên thực thi trên mỗi request probe:
SELECT COUNT(*)
FROM massive_inbox_table
WHERE status = 'PENDING';
~~~

Nếu query không có index hoặc khối lượng lớn, health check có thể làm tăng tải DB và góp phần gây sự cố. Dùng **metrics được cập nhật định kỳ, query có giới hạn/caching** hoặc phép kiểm tra connection nhẹ theo mục tiêu.

### 18.3. Readiness khi database bắt buộc

Ứng dụng có thể cần DB để nhận request; đưa `db` vào readiness có thể hợp lý. Nhưng nếu DB outage diện rộng, toàn bộ instances có thể bị loại khỏi traffic. Kiểm tra cách load balancer, ingress và consumer xử lý **zero ready endpoints**, khả năng trả lỗi 503 hợp lệ và runbook failover. Không thay một quyết định kiến trúc bằng việc mù quáng thêm `db` vào mọi readiness group.

## 19. JMS listener và AMQP consumer

Với JMS/AMQP, một connection/channel tới broker có thể tồn tại nhưng consumer không xử lý được message; ngược lại, broker outage tạm thời có thể được container tự reconnect.

### 19.1. JMS

Quan sát nên gồm:

- listener container state (started/stopped/failed theo API phiên bản);
- connection/session error count;
- consume và acknowledgment/transaction outcome;
- redelivery attempts/poison message;
- pending queue depth hoặc oldest message age khi broker cung cấp metric;
- DLQ backlog và recovery failures.

Nếu app chủ yếu phục vụ HTTP request độc lập với JMS, broker outage không nhất thiết phải làm HTTP readiness DOWN. Nếu app chỉ là JMS worker, cần xác định controller/worker semantics thay vì hy vọng HTTP readiness tự pause listener.

### 19.2. AMQP

Đối với RabbitMQ hoặc broker tương ứng:

- RabbitMQ management/connection health có thể là một tín hiệu;
- consumer ACK/NACK/requeue có thể khác publisher confirm;
- queue backlog/DLX/DLQ cần metric riêng;
- một `RabbitHealthIndicator` (nếu auto-config trong stack đang dùng) không chứng minh message đã tới consumer hoặc side effect đã được lưu.

### 19.3. Test failure mode

| Fault | Indicator/metric kỳ vọng |
|---|---|
| Broker restart | Kết nối lỗi/recovery; ứng dụng không restart loop vô ích. |
| Listener stopped | Lifecycle alarm, dù `/health` toàn cục có thể UP. |
| NACK-requeue vô hạn | Poison-message/retry alert, không chỉ connection health. |
| DLQ phát triển | Business processing alert, không tự suy instance chết. |
| Quarantine publisher unavailable | Recovery failure alert có mức ưu tiên cao. |

## 20. Kafka: connection health không thay lag, assignment hoặc offset

Kafka consumer là cơ chế message-driven với poll/commit offset, nhưng nó **không đồng nhất** với Spring Integration `PollerMetadata` của một `MessageSource`. Một topic có dữ liệu và broker đang chạy không bảo đảm ứng dụng đã xử lý chúng.

| Lớp | Điểm quan sát | Ý nghĩa |
|---|---|---|
| Broker connectivity | Kafka client/broker request failure | Có kết nối/operation kỹ thuật nào thất bại? |
| Consumer lifecycle | Listener container running/paused | Container sẵn sàng nhận data theo cấu hình? |
| Partition assignment | Assigned partitions count | Instance có nhiệm vụ tiêu thụ partition nào? |
| Consumer lag | Log end offsets so với committed/position theo định nghĩa | Có backlog và độ trễ tiêu thụ không? |
| Processing failures | Handler exception/retry counts | Data đã nhận nhưng không xử lý được? |
| DLT | DLT record/publish result/oldest age | Có poison message cần can thiệp? |
| Business confirmation | DB/outbox/target evidence | Side effect cuối được xác nhận chưa? |

### 20.1. Assignment bằng 0 không luôn là lỗi

Với nhiều replicas hơn partitions, một số consumers có thể **không được gán partition**. Coi `assignedPartitions == 0` là liveness DOWN sẽ tạo restart loop không cần thiết. Health threshold phải hiểu group membership, partition count, scaling và policy.

### 20.2. Lag là metric và alert chứ không phải luôn là health DOWN

Lag tăng khi traffic burst có thể bình thường trong thời gian ngắn. Dùng consumer lag, oldest-event age, processing latency và backlog SLO để đánh giá. Nếu lag quá hạn đe dọa tác vụ cốt lõi, có thể có diagnostic degraded state, nhưng phải xác định **ai sẽ hành động và readiness/liveness có giúp hay làm tệ hơn không**.

### 20.3. Commit offset khác business completion

Một consumer có thể commit offset sau khi message được đưa tới DLT theo policy. Điều đó không có nghĩa transaction nghiệp vụ đã thành công. Health/reporting nên tách `PROCESSED`, `RECOVERED_TO_DLT`, `UNKNOWN_OUTCOME` và `FAILED_WITHOUT_DURABLE_RECOVERY`.

## 21. MessageChannel và Spring Integration graph

Spring Integration có thể dùng:

- `DirectChannel`: handler đồng bộ trên thread gửi;
- `ExecutorChannel`: chuyển sang executor bất đồng bộ;
- `QueueChannel`: có queue để consumer lấy sau;
- publish-subscribe, routing, bridge, aggregator, filter và gateway.

### 21.1. Không chỉ đếm “send success”

`MessageChannel.send() == true` chỉ cho biết message được channel chấp nhận theo semantics của channel; với async executor/queue, downstream có thể fail sau đó.

Một pipeline cần metrics cho:

~~~mermaid
flowchart LR
    SRC["Inbound Source"] --> CH["MessageChannel"]
    CH --> H["Handler / Transformer"]
    H --> OUT["Outbound Adapter"]
    OUT --> TARGET["External Target"]
    CH --> Q["Queue/Executor<br/>pending + rejection"]
    H --> ERR["ErrorChannel / Retry"]
    OUT --> RECON["Target readback / reconciliation"]
~~~

### 21.2. Actuator integration graph và management instrumentation

Ở một số phiên bản và cấu hình, Spring Integration tích hợp Actuator/Micrometer để cung cấp graph, metrics hoặc management endpoints (ví dụ tên `integrationgraph`). **Không mặc định endpoint đó tồn tại và được expose chỉ vì có starter Actuator**. Cần xác minh:

1. Phiên bản Spring Integration và Spring Boot hỗ trợ những integration endpoints nào.
2. Dependency và management configuration có bật tính năng không.
3. Endpoint có thực sự được expose qua web/JMX không.
4. Security policy có cho phép đọc topology không (graph có thể tiết lộ tên systems/channels).
5. Metrics có được instrument ở source/handler/channel cần quan sát không.

Topology graph rất hữu ích để debug wiring và lifecycle, nhưng **không thay health hay bảo đảm business flow xử lý đúng**.

## 22. Health, metrics, logs, traces và audit: dùng đúng công cụ

| Công cụ | Câu hỏi | Ví dụ |
|---|---|---|
| **Health** | Điều kiện vận hành nào đạt/không đạt? | Poll heartbeat stale, readiness refusing. |
| **Metrics** | Tần suất, tốc độ, lỗi, backlog, tỷ lệ? | Poll count, P95 latency, DLQ oldest age. |
| **Structured logs** | Sự kiện nào đã xảy ra, lỗi gì? | `eventId`, `endpointId`, error category. |
| **Distributed tracing** | Request/event đi qua những đâu, mất thời gian ở bước nào? | HTTP gateway → handler → DB. |
| **Audit/evidence** | Tại sao xử lý/thu hồi/redrive, ai quyết định, kết quả ở đâu? | Quarantine resolution, target readback. |

### 22.1. Ví dụ sự cố có health UP nhưng nghiệp vụ thất bại

~~~text
SFTP poll mỗi 30 giây: SUCCESS (không có exception)
MessageSource trả một file: SUCCESS
CSV parser reject: UNKNOWN_STATUS
File được quarantine: SUCCESS
Business update applied: 0

Poll health = UP (source hoạt động)
Contract error count tăng
Quarantine oldest age tăng
Business integration SLO có nguy cơ vi phạm
~~~

Không phải health indicator sai: nó đang đo **source polling**, không đo **business translation**. Sai lầm nằm ở việc người vận hành hiểu `UP` là “không có lỗi nghiệp vụ”.

## 23. Bảo mật Actuator: giới hạn exposure, details và quyền truy cập

Actuator là **management plane**, không phải một trang dashboard công khai. Người dùng cuối thường chỉ cần API nghiệp vụ, còn người vận hành cần health status, metrics và diagnostics theo quyền hạn.

### 23.1. Những rủi ro phổ biến

| Rủi ro | Điều cần ngăn |
|---|---|
| Public `/actuator/env` hoặc `/beans` | Lộ cấu trúc/configuration, dù một số value được sanitization. |
| Public health details | Lộ tên database, địa chỉ broker, remote host, exception message. |
| Endpoint có thao tác thay đổi trạng thái | Người ngoài có thể điều chỉnh logger/config/management feature. |
| Health check dùng secret không bảo vệ | Log hoặc response chứa password/token/certificate paths. |
| Metrics với label ID cá nhân | Lộ business identifiers, tăng cardinality. |
| Expose cả management port | Bỏ qua network segmentation/firewall của ứng dụng. |
| Dùng một API key chung cho tất cả probes | Khó rotate và phân quyền. |

### 23.2. Show details có điều kiện

~~~yaml
management:
  endpoint:
    health:
      show-details: when_authorized
      roles: OPS
~~~

Property này **không tự cung cấp authentication**. Muốn `when_authorized` đúng ý đồ, cần cấu hình Spring Security/authorization cho management endpoints và roles tương ứng, kèm test một người không có quyền chỉ thấy thông tin được phép.

### 23.3. Network security trước cả HTTP response

- Kubernetes probe nội bộ cần truy cập endpoint, nhưng không đồng nghĩa người dùng internet có quyền truy cập.
- Nếu chạy management port riêng, áp dụng network policy/security group và ingress thích hợp.
- Giới hạn `management.endpoints.web.exposure.include` theo nguyên tắc least privilege.
- Nếu bật thêm metrics/prometheus, kiểm tra ai có quyền scrape; Prometheus endpoint có thể tiết lộ tên service, broker và topology.
- Không đưa thông tin cá nhân, credential, raw event payload vào `Health.withDetail(...)`.

### 23.4. Authentication có thể làm kubelet probe thất bại

Khi áp Spring Security cho tất cả actuator endpoints, kubelet gọi không có token có thể nhận HTTP 401/403 rồi đánh dấu instance không khỏe. Cần thiết kế đường probe **nội bộ và quyền hẹp** phù hợp kiến trúc, rồi test cả người dùng trái phép lẫn kubelet. Không giải quyết bằng cách public toàn bộ Actuator.

## 24. Health check phải có ngân sách tài nguyên

Kubernetes có thể gọi probes nhiều lần mỗi phút, Prometheus scrape metrics định kỳ, và monitoring tools cũng có thể gọi `/health`. Một health group gồm các active checks đắt đỏ có thể làm tăng tải đúng lúc upstream đang lỗi.

### 24.1. Ước tính tải

Ví dụ hai replicas, mỗi replica được probe mỗi 5 giây:

~~~text
Health requests per instance ≈ 12 lần/phút
Hai replicas ≈ 24 lần/phút

Nếu mỗi request mở 3 SFTP sessions và 2 DB connections:
  → đến 72 SFTP opens/phút, 48 DB validations/phút
  (chưa tính readiness/liveness/monitoring scrape khác)
~~~

Đây là phép tính minh họa để thấy **chi phí nhân theo số instance và số probe**. Thực tế phụ thuộc số request/endpoint/replica, caching và frequency.

### 24.2. Nguyên tắc hiệu năng

1. **Ưu tiên passive state** cho nguồn I/O đã được polling/listener kiểm tra thường xuyên.
2. **Active check chỉ khi cần**, với timeout, connection pool và rate-limit phù hợp.
3. **Cache kết quả có TTL** nhưng nêu rõ stale semantics.
4. **Không dùng shared executor của business flow** để chạy health job nặng khiến health gây starvation.
5. **Không làm việc gây side effect** như tạo booking, publish event thật hay xóa file.
6. **Không quét backlog lớn mỗi request**; dùng metrics cập nhật định kỳ.
7. **Không để một dependency dùng hết thời gian budget** của toàn health group.
8. **Đo chính latency của health checks** để phát hiện endpoint trở thành nguồn tải.

### 24.3. Health endpoint bị treo cũng là một tín hiệu

Nếu health indicator đồng bộ chờ SFTP timeout 60 giây, kubelet có thể timeout ngay từ ngoài, trong khi Actuator thread pool bị chiếm dụng. Thiết kế cần bảo đảm check bounded và hành vi khi timeout. Một số phép kiểm tra nên nằm ngoài request thread và chỉ đọc cached state.

## 25. Trạng thái DEGRADED, UNKNOWN và OUT_OF_SERVICE

Spring Boot có các trạng thái phổ biến `UP`/`DOWN`/`OUT_OF_SERVICE`/`UNKNOWN`; người dùng cũng có thể định nghĩa custom `Status` và aggregation rules. Tuy nhiên:

- Một custom `DEGRADED` không tự có ý nghĩa HTTP chuẩn.
- Cần định nghĩa thứ tự aggregation nếu muốn nó ảnh hưởng global health.
- Cần định nghĩa HTTP mapping cho custom status theo group.
- Kubernetes readiness chỉ hiểu **mã HTTP probe thành công/thất bại**, không đọc ngữ nghĩa business của JSON.

### 25.1. Chọn status dựa trên hành động

| Quan sát | Health state gợi ý | Hành động đi kèm |
|---|---|---|
| Không có poll lần đầu ở poller chạy mỗi ngày | `UNKNOWN` cho diagnostic | Chờ lịch/kiểm tra startup plan. |
| Poller chết và không tự phục hồi | `DOWN` trong diagnostic | Restart endpoint hoặc điều tra scheduler. |
| App chủ động drain để deploy | `OUT_OF_SERVICE`/readiness refusing | Ngừng nhận traffic mới. |
| Partner API chậm nhưng có fallback | Custom degraded metric/alert | Failover/limit/retry, không restart mọi pod. |
| DB bắt buộc không truy cập được | `DOWN` trong dependency/readiness nếu policy | Cô lập traffic, điều tra DB. |
| Source healthy nhưng DLQ quá hạn | Health kỹ thuật có thể `UP` | Business alert, redrive/reconciliation. |

### 25.2. Flapping và hysteresis

Nếu chỉ cần một timeout để chuyển readiness DOWN, rồi một success chuyển UP, trạng thái có thể **dao động liên tục** khi mạng không ổn định. Cân nhắc:

- ngưỡng N failures liên tiếp;
- cửa sổ thời gian;
- tối thiểu M successful checks trước khi hồi phục;
- startup grace;
- error category và maintenance windows.

Hysteresis là **policy theo rủi ro**, không tự xảy ra chỉ vì `HealthIndicator` trả về một status. Test phải xác minh cả downgrade và recovery, không để trạng thái DOWN vĩnh viễn.

## 26. Availability events và lifecycle Spring Boot

Spring Boot theo dõi trạng thái sẵn sàng/sống của ứng dụng qua các API availability (ví dụ `ApplicationAvailability`, `LivenessState`, `ReadinessState`). Một thành phần có thể công bố trạng thái readiness khi workload thật sự cần ngừng nhận thêm việc:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;

final class TrafficDrainCoordinator {
    private final ApplicationEventPublisher events;

    TrafficDrainCoordinator(ApplicationEventPublisher events) {
        this.events = events;
    }

    void stopAcceptingWork() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.REFUSING_TRAFFIC);
    }

    void resumeAcceptingWork() {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

**Không gọi `REFUSING_TRAFFIC` khi SFTP partner 503 một lần mà không có chính sách.** Đây là quyết định ở mức instance/service. Khi controller đã loại pod khỏi traffic, cần biết:

1. Các requests đang chạy được drain như thế nào?
2. Pollers hoặc broker listeners có được pause/stop không?
3. Pending messages có durable không?
4. Ai/điều kiện nào đưa readiness trở lại `ACCEPTING_TRAFFIC`?
5. Có bị tất cả instances rút khỏi service cùng lúc không?

### 26.1. Graceful shutdown

Một quá trình shutdown đúng thường bao gồm:

~~~mermaid
sequenceDiagram
    participant Deploy as Deployment controller
    participant App as ApplicationAvailability
    participant LB as Load balancer
    participant Flow as Spring Integration flows
    participant Source as Source/Broker
    Deploy->>App: Bắt đầu shutdown
    App-->>LB: Readiness REFUSING_TRAFFIC
    Deploy->>Flow: Graceful stop / drain
    Flow->>Source: ACK/commit chỉ theo outcome
    Flow-->>Deploy: In-flight settled / timed out
    Deploy->>App: Process shutdown
~~~

Flow trên là **mô hình mong muốn**; thực tế còn phụ thuộc `terminationGracePeriodSeconds`, lifecycle phases, listener container, transaction và từng adapter. Đừng coi việc readiness DOWN là bằng chứng pending work đã được xử lý xong.

## 27. Metrics bằng Micrometer: bổ sung Health

Nếu ứng dụng có Micrometer registry, có thể instrument poll attempts và failures mà không làm thay đổi logic retry:

~~~java
package example.integration.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class PollMetrics {
    private final Counter attempts;
    private final Counter failures;

    public PollMetrics(MeterRegistry registry) {
        this.attempts = Counter.builder("integration.poll.attempts")
                .tag("source", "partner-sftp")
                .register(registry);
        this.failures = Counter.builder("integration.poll.failures")
                .tag("source", "partner-sftp")
                .register(registry);
    }

    public void attempted() {
        attempts.increment();
    }

    public void failed() {
        failures.increment();
    }
}
~~~

Điểm instrument phải chọn rõ: `attempts.increment()` được gọi **đúng một lần khi bắt đầu nhận nguồn**, kể cả kết quả rỗng. `failures.increment()` chỉ tăng khi operation được xác định là lỗi. Nếu có nhiều retry layers, cần phân biệt **attempt của source, retry attempts của handler và redelivery của broker**.

### 27.1. Metrics nên có cho integration pipeline

| Metric gợi ý | Định nghĩa | Cách dùng |
|---|---|---|
| `integration.poll.attempts` | Số lượt poll source | Biết poller còn chạy. |
| `integration.poll.failures` | Số lượt poll lỗi | Phát hiện source/connection failure. |
| `integration.messages.received` | Business messages nhận được | Không đồng nhất với poll attempts. |
| `integration.messages.processed` | Message qua handler theo contract | Chưa chắc đích đã confirmed. |
| `integration.messages.recovered` | Message được durable quarantine/DLT | Phân biệt business success. |
| `integration.backlog.oldest.age` | Tuổi pending event lâu nhất | Phát hiện dữ liệu bị kẹt. |
| `integration.retry.attempts` | Retry trong process | Theo dõi retry storm. |
| `integration.target.confirmations` | Kết quả cuối có bằng chứng | Business success rate. |

Các tên trên là **quy ước minh họa**, không phải metric tự động luôn xuất hiện. Với endpoint/adapter cụ thể, kiểm tra metric do framework và Micrometer version cung cấp, tránh tự đếm trùng.

### 27.2. Không dùng request ID làm metric tag

`eventId`/`traceId` có cardinality gần vô hạn, không nên là tag trên time-series metrics. Dùng tags ít biến động như `sourceType`, `endpointId`, `result`, `errorCategory`; đặt correlation chi tiết vào tracing/log có phân quyền.

### 27.3. Prometheus endpoint không mặc nhiên public

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Chỉ bật ví dụ này trong môi trường **có registry Prometheus và kiểm soát truy cập/network**. Nếu không có registry tương ứng, không suy endpoint `/actuator/prometheus` sẽ tồn tại. Có thể dùng các hệ thống monitoring khác không cần expose Prometheus.

## 28. Unit test custom HealthIndicator với Clock điều khiển được

Không nên viết unit test `Thread.sleep(180_000)` để chờ một heartbeat hết hạn. Hãy inject `Clock` như thiết kế ở trên và di chuyển thời gian trong test.

### 28.1. Đồng hồ giả có thể tăng theo bước

~~~java
package example.integration.health;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

final class MutableClock extends Clock {
    private final AtomicReference<Instant> now;
    private final ZoneId zone;

    MutableClock(Instant initial) {
        this(initial, ZoneOffset.UTC);
    }

    private MutableClock(Instant initial, ZoneId zone) {
        this.now = new AtomicReference<>(initial);
        this.zone = zone;
    }

    void advance(Duration duration) {
        now.updateAndGet(old -> old.plus(duration));
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId requestedZone) {
        return new MutableClock(now.get(), requestedZone);
    }

    @Override
    public Instant instant() {
        return now.get();
    }
}
~~~

Trong ví dụ này, `withZone(...)` tạo một clock **riêng với snapshot thời gian hiện tại** cho test đơn giản; nếu test yêu cầu hai clock chia sẻ cùng một nguồn thời gian mutable qua `withZone`, hãy chia sẻ `AtomicReference` theo thiết kế. Mục tiêu là tránh phụ thuộc wall clock/CI.

### 28.2. Test no-poll, empty-poll, stale và recovery

~~~java
package example.integration.health;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;
import org.springframework.integration.core.MessageSource;

class PollHealthIndicatorTest {

    @Test
    void emptyPollIsStillSuccessfulButStalePollIsDown() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-11-23T09:00:00Z"));
        PollMonitor monitor = new PollMonitor(clock);
        PollHealthIndicator indicator =
                new PollHealthIndicator(
                        monitor, clock, Duration.ofMinutes(3));

        assertEquals(Status.UNKNOWN,
                indicator.health().getStatus());

        MessageSource<String> empty = () -> null;
        ObservedMessageSource<String> source =
                new ObservedMessageSource<>(empty, monitor);

        assertNull(source.receive()); // Nguồn rỗng, poll thành công.
        assertEquals(Status.UP,
                indicator.health().getStatus());

        clock.advance(Duration.ofMinutes(4));
        assertEquals(Status.DOWN,
                indicator.health().getStatus());

        assertNull(source.receive()); // Poll tiếp tục thành công.
        assertEquals(Status.UP,
                indicator.health().getStatus());
    }

    @Test
    void sourceExceptionIsNotSwallowed() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-11-23T09:00:00Z"));
        PollMonitor monitor = new PollMonitor(clock);
        MessageSource<String> failing = () -> {
            throw new IllegalStateException("test failure");
        };

        ObservedMessageSource<String> source =
                new ObservedMessageSource<>(failing, monitor);

        assertThrows(IllegalStateException.class, source::receive);
        assertEquals(1,
                monitor.snapshot().consecutiveFailures());
        assertNull(monitor.snapshot().lastSuccessfulPoll());
    }
}
~~~

**Bằng chứng của test:** logic health của decorator/indicator đúng với clock được điều khiển. **Không chứng minh** SFTP server hay scheduler thật đang chạy. Đây là unit test, không phải network integration.

### 28.3. Thêm ca lỗi sau lần poll thành công

Nếu `successfulPoll` lúc 09:00, lỗi xuất hiện 09:01, indicator vẫn có thể `UP` cho tới khi quá `maxSilence`. Đó là **quy tắc đã chọn** (heartbeat stale), không nhất thiết là lỗi code. Nếu ứng dụng yêu cầu chuyển DOWN ngay sau N lỗi liên tiếp, bổ sung threshold, viết test theo chính sách ấy và đảm bảo không tạo flapping không cần thiết.

## 29. Spring Boot Test: xác minh HTTP health endpoint thực sự trả đúng

Đơn vị `HealthIndicator.health()` trả `DOWN` chưa chứng minh probe trả HTTP 503, vì health group có thể cấu hình khác hoặc indicator không nằm trong nhóm. Vì vậy cần **HTTP-level Actuator tests**.

### 29.1. Mẫu MockMvc khi ứng dụng sử dụng Spring MVC

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "management.endpoint.health.probes.enabled=true",
        "management.endpoints.web.exposure.include=health"
})
@AutoConfigureMockMvc
class ActuatorHealthHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void exposesLivenessAndReadinessStatus() throws Exception {
        mvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));

        mvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
~~~

Test giả định application context đã khởi động xong và availability states đang `CORRECT/ACCEPTING_TRAFFIC`. **Nếu ứng dụng có security filter, custom health group, non-default servlet path hoặc readyness dependencies bị lỗi**, code cần điều chỉnh fixture/authorization theo contract. Không dùng `@AutoConfigureMockMvc(addFilters = false)` để vô hiệu hóa security trong test mà mục tiêu là chứng minh security.

### 29.2. Test readiness REFUSING_TRAFFIC

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.web.servlet.MockMvc;

class ReadinessBehaviorSnippet {

    @Autowired MockMvc mvc;
    @Autowired ApplicationEventPublisher events;

    @Test
    void refusingTrafficProducesUnavailableReadiness() throws Exception {
        AvailabilityChangeEvent.publish(
                events, ReadinessState.REFUSING_TRAFFIC);
        try {
            mvc.perform(get("/actuator/health/readiness"))
                    .andExpect(status().isServiceUnavailable())
                    .andExpect(jsonPath("$.status")
                            .value("OUT_OF_SERVICE"));
        } finally {
            AvailabilityChangeEvent.publish(
                    events, ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
~~~

Đây là **fragment test**: để chạy thật, đặt trong lớp có `@SpringBootTest` và `@AutoConfigureMockMvc` cùng configuration phù hợp. Restore availability trong `finally` để không làm context cache ảnh hưởng các test khác. Nếu test suite có nhiều test thao tác availability chạy parallel trên cùng context, phải cô lập.

### 29.3. Test global /health khác group

Đăng ký một custom health indicator trả `DOWN` và so sánh:

- `GET /actuator/health`: status tổng hợp theo contributors.
- `GET /actuator/health/liveness`: chỉ liveness group theo cấu hình.
- `GET /actuator/health/readiness`: readiness group theo cấu hình.
- `GET /actuator/health/integrations`: integration group với indicator tương ứng.

Test nên bắt **cả JSON status và HTTP status**, không chỉ một trong hai. Đặc biệt với `UNKNOWN` hoặc status custom, hãy assert mapping thực tế thay vì giả định.

## 30. Test auth và data disclosure của management endpoints

Ví dụ một ứng dụng chỉ muốn:

- Kubelet nội bộ: xem `/health/liveness` và `/health/readiness`.
- Người vận hành role `OPS`: xem `/health/integrations` cùng details cần thiết.
- Người dùng không có quyền: **không** xem cấu hình nhạy cảm hay topology.

### 30.1. Các ca bảo mật

| Caller | Endpoint | Expected |
|---|---|---|
| Internal probe có policy được cấp | `/actuator/health/liveness` | HTTP success nếu state UP. |
| Internal probe | `/actuator/health/readiness` | Đúng HTTP mapping UP/OUT_OF_SERVICE. |
| Anonymous từ public interface | `/actuator/env` | Không được truy cập. |
| Anonymous | `/actuator/health/integrations` | Chỉ thông tin public hoặc bị chặn theo policy. |
| Operator `OPS` | Diagnostic health group | Được xem details đã redacted theo policy. |
| Người dùng không có `OPS` | Diagnostic health group | Không được xem details nội bộ. |
| Bất kỳ caller | Health response chứa secret | **Không có** token/password/connection string. |

Không nên coi mã HTTP 200 đối với anonymous health là lỗi bảo mật nếu contract cố ý cho phép **status tối thiểu** trên endpoint nội bộ. Vấn đề là **exposure ra ngoài và details được trả**, không chỉ status code.

### 30.2. MockMvc không kiểm thử toàn bộ network policy

MockMvc có thể xác minh Spring Security filter và HTTP mapping trong JVM; nó không kiểm tra Kubernetes NetworkPolicy, Ingress, firewall, mTLS proxy hoặc management port routing thật. Với triển khai production, còn cần kiểm tra deployment/network layer.

## 31. Kiểm thử outage/recovery theo từng adapter

Các fault tests nên sử dụng **môi trường cô lập**, không ngắt kết nối production:

| Fault injection | Điểm đo | Điều không được xảy ra |
|---|---|---|
| SFTP server offline | Last poll success/failure, reconnect | Health check liên tục mở session gây storm. |
| HTTP partner trả 503 | Failure rate, latency, circuit breaker | Liveness của mọi pod bị DOWN vô ích. |
| DB tạm unavailable | DB contributor, readiness policy, recovery | ACK dữ liệu đầu vào khi transaction chưa bền. |
| Kafka broker restart | Consumer reconnect/lag, retry | Restart loop pod dù broker đang recover. |
| JMS consumer stopped | Lifecycle state, backlog | /health UP bị hiểu là consumer vẫn xử lý. |
| AMQP poison message | DLQ, redelivery attempts | NACK-requeue loop vô hạn không alert. |
| File permission denied | Poll failure, error channel | Trả null và ghi poll success giả. |
| Endpoint stop/start | Lifecycle state, heartbeat reset | Stale state bị báo UP mãi. |
| Graceful shutdown | Readiness transition, in-flight drain | Traffic mới vẫn tiếp tục được cấp. |
| Disk full | Disk health và File processing | Health check tạo thêm file thử làm nặng lỗi. |

### 31.1. Ghi rõ mức kiểm thử

- **Unit:** kiểm tra monitor/indicator bằng fake clock.
- **Flow integration:** kiểm tra poller, channel, error path trong Spring context.
- **Transport integration:** dùng SFTP server/HTTP stub/broker/DB thử nghiệm.
- **Deployment:** chạy pod/management port/network/probes thực.
- **Business E2E:** kiểm tra dữ liệu cuối/offset/ACK/reconciliation khi cần.

Việc health group trả `DOWN` trong unit test không chứng minh Kubernetes đã **thật sự** loại instance khỏi traffic. Bằng chứng đó thuộc deployment/cluster test.

## 32. Ma trận kiểm thử Health endpoint và Actuator

| # | Kịch bản | Tầng | Bằng chứng cần có |
|---:|---|---|---|
| 1 | Starter Actuator có mặt | Spring context | Health endpoint đăng ký đúng. |
| 2 | Health exposure tối thiểu | HTTP/security | Chỉ endpoint được phép có thể gọi. |
| 3 | Health mặc định UP | HTTP | JSON và HTTP code phù hợp. |
| 4 | Global contributor DOWN | HTTP | Global aggregation phản ánh đúng. |
| 5 | Custom UNKNOWN status | HTTP | HTTP mapping không bị giả định sai. |
| 6 | Liveness group | HTTP | Độc lập với integration diagnostic nếu thiết kế. |
| 7 | Readiness ACCEPTING_TRAFFIC | HTTP | Probe thành công theo policy. |
| 8 | Readiness REFUSING_TRAFFIC | HTTP | `OUT_OF_SERVICE`, 503 theo mapping. |
| 9 | Readiness không tự gồm mọi dependency | Context/HTTP | Chỉ contributor được include. |
| 10 | Readiness có db bắt buộc | Context/HTTP | Policy & aggregation rõ. |
| 11 | Group integrations có thành viên đúng | Context | Startup và endpoint không lỗi vì missing ID. |
| 12 | Indicator chưa có poll | Unit | `UNKNOWN` theo contract. |
| 13 | Poll rỗng lần đầu | Unit | Được ghi nhận là successful poll. |
| 14 | Poll trả một message | Unit/flow | Health heartbeat và payload không bị sửa. |
| 15 | Poll source throw | Unit | Exception tiếp tục propagate, failure state tăng. |
| 16 | Poll heartbeat quá hạn | Clock unit | Status DOWN theo threshold. |
| 17 | Poll lại sau stale | Clock unit | Health phục hồi UP. |
| 18 | N lỗi liên tiếp | Unit | Threshold/hysteresis theo thiết kế. |
| 19 | Poller stopped | Flow | Lifecycle/alert khác poll empty. |
| 20 | Poller running nhưng handler lỗi | Flow | Không báo business success giả. |
| 21 | File directory mất quyền | File integration | Error và recovery rõ ràng. |
| 22 | SFTP no-new-file | SFTP integration | Không bị coi là remote outage. |
| 23 | SFTP remote unreachable | SFTP integration | Error category/backoff/health policy. |
| 24 | SFTP wrong host key | Security/integration | Không disable verification. |
| 25 | HTTP health check read-only | HTTP transport | Không tạo business side effect. |
| 26 | HTTP 503 partner | HTTP integration | Diagnostic error, không restart storm. |
| 27 | HTTP POST timeout | E2E | Unknown outcome, idempotency/readback. |
| 28 | DB connection fail | DB integration | DB contributor/ready policy được xác nhận. |
| 29 | JDBC inbox backlog | DB/metrics | Pending age metric, không query nặng ở probe. |
| 30 | JMS broker restart | JMS integration | Listener recover theo chính sách. |
| 31 | JMS queue poison | JMS integration | DLQ/backlog được alert. |
| 32 | AMQP requeue loop | AMQP integration | Retry storm có cảnh báo/giới hạn. |
| 33 | Kafka consumer assignment = 0 hợp lệ | Kafka integration | Không đánh giá liveness sai. |
| 34 | Kafka lag vượt SLO | Metrics/operations | Alert và owner, không chỉ health status. |
| 35 | Kafka DLT publish failed | Broker integration | Recovery failure được phát hiện. |
| 36 | Main/management ports tách | Deployment | Probe gọi đúng port/path. |
| 37 | `/livez`/`/readyz` thêm path | Deployment | Path thật khả dụng nếu được hỗ trợ. |
| 38 | Kubelet access policy | Security/deployment | Probe được gọi, public details bị chặn. |
| 39 | Health indicator chậm | Load test | Bounded timeout, không chiếm tài nguyên vô hạn. |
| 40 | Health scrape dồn dập | Load test | Không tạo session storm tới SFTP. |
| 41 | Startup probe khi cold start | Deployment | Không restart trước startup budget. |
| 42 | Readiness khi graceful shutdown | Deployment | Ngừng traffic mới, in-flight có drain. |
| 43 | Spring Integration graph | Context/security | Chỉ expose nếu có hỗ trợ/quyền. |
| 44 | Micrometer counter | Unit/metrics | Attempts khác messages, labels bounded. |
| 45 | Error detail có secret | Security | Password/token không lộ ở response/log. |
| 46 | Multiple replicas outage chung | Deployment | Không đồng loạt restart vô ích. |
| 47 | Context cache test | Spring Test | Không leak health state/availability. |
| 48 | Quarantine backlog tăng | E2E/metrics | Alert mặc dù source health UP. |
| 49 | Probe status custom `DEGRADED` | HTTP | Mapping code và aggregation đã test. |
| 50 | Khôi phục sau lỗi và restart | Recovery/E2E | Data/ACK/target evidence chính xác. |

Mỗi test phải ghi **initial state, action, nguồn dữ liệu, threshold, expected status và HTTP code, timeout, teardown**. Nếu chỉ ghi “Actuator trả 200”, không đủ chứng minh ứng dụng đang khỏe theo mục tiêu vận hành.

## 33. Case study: ứng dụng SFTP → DB → Kafka chạy trên Kubernetes

### 33.1. Bối cảnh và mục tiêu

Một ứng dụng Spring Boot triển khai hai replicas:

1. Poll SFTP mỗi 30 giây để nhận file đối tác đã sẵn sàng.
2. Parse file và cập nhật bảng inbox/orders trong PostgreSQL.
3. Sau khi commit, tạo outbox event.
4. Publisher gửi event ra Kafka, xác nhận trạng thái outbox.
5. Dashboard giám sát data latency, pending/failed files và Kafka backlog.

Rủi ro: SFTP có maintenance, database đôi lúc chậm, Kafka broker có thể rebalance; không muốn restart toàn bộ ứng dụng chỉ vì một hệ thống ngoài tạm lỗi.

~~~mermaid
flowchart TD
    PARTNER["Partner SFTP<br/>ready files"] --> POLL["SFTP inbound poller"]
    POLL --> PARSE["Parse + validate"]
    PARSE --> DB["PostgreSQL inbox/orders"]
    DB --> OUTBOX["Outbox publisher"]
    OUTBOX --> KAFKA["Kafka topic"]

    POLL --> PH["Passive poll heartbeat"]
    DB --> DH["DB connectivity"]
    OUTBOX --> METRIC["Pending/confirmations metrics"]
    KAFKA --> METRIC
    PH --> ACT["Actuator integration health"]
    DH --> ACT
    ACT --> OPS["Operator diagnostics"]
    METRIC --> ALERT["SLO alerts"]

    READY["Readiness state<br/>+ selected mandatory deps"] --> KUBE["Kubernetes readiness"]
    LIVE["Liveness state"] --> KUBE
~~~

### 33.2. Cần định nghĩa rõ hai mặt “khỏe”

**Technical availability:** service/process, Spring context, DB connection khi bắt buộc, inbound poller lifecycle, SFTP session theo ngưỡng.

**Business throughput:** số file ready tồn đọng, số rows chưa xử lý, target confirmation, oldest pending, Kafka outbox lag và reconciliation.

Health không thể thay thế business throughput SLO; chúng phải được hiển thị cạnh nhau.

### 33.3. Chính sách health đề xuất

| Thành phần | Health/metric | Có làm liveness DOWN? | Có làm readiness DOWN? |
|---|---|---|---|
| Spring Boot livenessState | Liveness group | Theo availability | Không áp trực tiếp. |
| Spring Boot readinessState | Readiness group | Không | Theo availability. |
| PostgreSQL | DB contributor + connection failures | Không mặc định | Có thể có nếu tất cả workload cần DB. |
| SFTP poller | Passive heartbeat + outage duration | Không | Không mặc định; cân nhắc nếu service chỉ ingestion. |
| File backlog | Oldest file age, pending count | Không | Thường metric/alert thay vì readiness. |
| Kafka outbox | Oldest pending, publisher failures | Không | Tùy đường xử lý; thường cần operations alert. |
| DLQ/quarantine | Count/oldest age | Không | Không mặc định, có owner xử lý. |

Đây là **một đề xuất**, không phải sự thật chung. Nếu service chỉ làm ingestion không có REST traffic, readiness probe có thể không tự điều khiển Kafka/SFTP intake; cần phối hợp lifecycle của consumer/poller.

### 33.4. Tình huống A — SFTP outage trong 15 phút

**Observed:**

~~~text
12:00  SFTP poll OK, receive() trả null
12:01  DNS/TCP timeout bắt đầu
12:02  consecutiveFailures tăng
12:04  lastSuccessfulPoll vượt ngưỡng heartbeat
12:05  /health/integrations có partnerSftp DOWN
12:15  SFTP phục hồi
12:16  poll thành công, health trở lại UP
~~~

**Expected:**

- Không nhầm `receive() == null` với failure.
- Diagnostic health chỉ chuyển DOWN sau policy đã chốt.
- Liveness vẫn UP nếu ứng dụng còn tự hồi phục được.
- Metrics/alert cho biết SFTP unavailable, backlog/oldest age.
- Không tự bật HTTP 503 global thành một vòng restart pod nếu Kube liveness gọi đúng group.
- Khi phục hồi, xử lý file backlog theo filter/idempotency; không nhân bản bản ghi DB.

### 33.5. Tình huống B — PostgreSQL outage

Nếu application service không thể commit domain transaction:

1. Xem connection pool/DB health và readiness policy.
2. Ngừng nhận workload mới hoặc kiểm soát backpressure nếu cần.
3. Không ACK/message checkpoint trước khi có durability theo contract.
4. Phục hồi connection có retry/backoff, tránh tạo hàng nghìn attempts đồng thời.
5. Readback target và outbox/inbox sau recovery để xác minh không mất dữ liệu.

Không coi `db Health UP` là bằng chứng commit nghiệp vụ đã thành công; một user/role có thể đọc được connection nhưng không có permission ghi bảng.

### 33.6. Tình huống C — Kafka broker outage

Nếu DB commit thành công và outbox event chưa publish:

- HTTP liveness/readiness của ứng dụng có thể không đổi, tùy workload.
- Outbox pending age tăng, publisher failures tăng.
- Có cảnh báo theo SLO chứ không “restart để hy vọng Kafka chạy”.
- Sau broker phục hồi, publisher replay outbox có idempotency/producer semantics đã thiết kế.
- Kết quả cuối được đo bằng Kafka publish confirmation và eventual consumer processing theo nhu cầu nghiệp vụ.

### 33.7. Tình huống D — CSV schema đổi

SFTP poll, download và DB đều có thể khỏe, nhưng parser liên tục gặp field mới:

- `/health/integrations` có thể còn `UP`.
- `contract_errors_total` và quarantine backlog tăng.
- Alert phải phân loại lỗi contract (không retry network vô ích).
- Sau khi cập nhật translator, redrive file/event có owner và audit.

Đây là minh chứng rõ nhất cho giới hạn của **health kỹ thuật**.

## 34. Runbook vận hành khi /actuator/health DOWN

Một health alert chỉ hữu ích khi người vận hành biết **tiếp theo phải làm gì**.

### 34.1. Quy trình chẩn đoán

~~~mermaid
flowchart TD
    A["Probe DOWN / unhealthy"] --> TYPE{"Endpoint nào?"}
    TYPE -- "Liveness" --> L["Kiểm tra process fatal state,<br/>threads, OOM, startup/shutdown"]
    TYPE -- "Readiness" --> R["Kiểm tra availability state,<br/>required dependencies"]
    TYPE -- "Integrations" --> I["Kiểm tra adapter/partner<br/>poll heartbeat + errors"]
    L --> ACTION["Chọn hành động theo runbook"]
    R --> ACTION
    I --> ACTION
    ACTION --> VERIFY["Xác minh hồi phục và backlog"]
~~~

### 34.2. Trình tự cụ thể

1. **Xác định endpoint:** là `/health` global, `/health/liveness`, `/health/readiness` hay group tùy biến?
2. **Kiểm tra HTTP code và JSON status:** không chỉ xem UI báo đỏ, cần nhận diện mapping.
3. **Xác định contributor:** DB, disk, passive poller, readinessState hay custom indicator.
4. **So sánh với metrics:** source attempts, failures, last success, backlog, DLQ, latencies.
5. **Đọc log/trace có correlation:** giữ đúng tenant/source/version, không lộ secret.
6. **Kiểm tra trạng thái endpoint:** poller/listener running, stop phase, partition assignment, connection recovery.
7. **Phân loại lỗi:** instance fatal, dependency outage, contract invalid, expected idle, unknown outcome.
8. **Chọn xử lý đúng:** restart instance chỉ khi thích hợp; thường cần reconnect, điều chỉnh config, pause/resume, redrive hoặc vendor incident.
9. **Đối soát dữ liệu:** không đóng incident chỉ vì health trở lại UP nếu còn backlog quá hạn.
10. **Cập nhật SLO/runbook:** nếu cảnh báo là false positive do cron dài hoặc state UNKNOWN, điều chỉnh policy có test.

### 34.3. Khi nào không nên restart?

Đừng restart hàng loạt khi:

- đối tác HTTP/SFTP đang outage diện rộng;
- Kafka broker đang khôi phục cluster hoặc rebalance bình thường;
- backlog tăng vì burst nhưng worker vẫn xử lý;
- DB maintenance dự kiến có retry/backoff;
- health check bị lỗi do endpoint probe timeout quá thấp hoặc active check tạo tải;
- chỉ có message contract mới chưa được translator hỗ trợ.

Restart có thể xóa cache, gián đoạn in-flight work hoặc tạo thêm duplicates. Liveness nên nhắm tới những failure mà **restart thực sự là một cơ chế hồi phục có ích**.

### 34.4. Đóng incident bằng bằng chứng

Đóng incident khi:

- Health/group liên quan quay lại trạng thái kỳ vọng và ổn định trong cửa sổ phù hợp.
- Poller/consumer đã resume thực sự, không chỉ bean running.
- Pending/backlog/oldest age tiến về mức cho phép.
- Error/quarantine items được xử lý hoặc có owner, SLA, trạng thái rõ ràng.
- Side effects cuối được readback hoặc có evidence theo business contract.
- Đã xác định nguyên nhân và hành động phòng ngừa nếu incident nghiêm trọng.

## 35. Anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Kubernetes liveness gọi global `/health` | SFTP/DB external outage làm restart toàn bộ pods. | Gọi liveness group, chỉ dùng fatal checks. |
| Readiness bao gồm mọi partner | Shared outage có thể loại toàn service. | Chọn mandatory dependencies theo traffic/role. |
| `isRunning() == true` được coi data flow khỏe | Scheduler kẹt vẫn running. | Poll heartbeat, message throughput, lag. |
| Chỉ đếm message mới để đo heartbeat | Source rỗng hợp lệ bị báo DOWN. | Đếm cả poll success trả null. |
| Poller catch exception rồi trả null | Che lỗi connection thành no-data. | Re-throw, error handling riêng. |
| Health endpoint mở SFTP session mỗi lần | Probe storm gây thêm tải. | Passive/cached/timeout-bounded check. |
| Probe ghi file thử vào input directory | Tạo message giả hoặc kích hoạt importer. | Check an toàn, không side effect. |
| Health gọi HTTP POST tạo đơn | Tạo side effect ngoài ý muốn. | Read-only endpoint hoặc passive metrics. |
| Health query COUNT trên bảng khổng lồ | DB tải cao lúc đang sự cố. | Query bounded/cached, metrics riêng. |
| Status `UNKNOWN` chắc chắn làm probe fail | HTTP code có thể vẫn 200. | Test status-to-HTTP mapping. |
| Custom `DEGRADED` không cấu hình | Probe có thể hiểu là OK. | Aggregation/status mapping rõ. |
| Cho tất cả management endpoints public | Lộ topology/configuration, rủi ro thao tác. | Exposure allowlist, auth/network controls. |
| `show-details: always` cho internet | Lộ hostname, exception/secret. | Minimal public, authorized diagnostics. |
| Kubelet bị 401 nhưng gọi đó là app DOWN | Lỗi cấu hình probe/security. | Thiết kế internal access, test auth. |
| Management port khác main port nhưng probe main mặc định | Route sai hoặc che lỗi server chính. | Test đúng port/path hoặc additional paths. |
| Xem HTTP 200 của health là business success | DLQ/backlog có thể tăng. | Target verification và business alerts. |
| Tắt probe để “sửa” false positive | Mất khả năng quan sát. | Chỉnh đúng signal/threshold/action. |
| Chỉ test indicator method, không test Actuator HTTP | Mã HTTP/group mapping có thể sai. | MockMvc/HTTP integration. |
| Dùng `Thread.sleep` chờ stale heartbeat | Flaky và chậm CI. | Inject `Clock`/fake time. |
| Bật metric tag bằng eventId | Cardinality cao, tăng chi phí. | Tags bounded, trace/log cho ID. |
| Không dọn readiness state giữa tests | Context cache bị nhiễm. | Restore trong finally, cô lập. |
| Quarantine lỗi contract làm health technical DOWN luôn | Trộn kỹ thuật và nghiệp vụ. | Health riêng, metrics/alerts theo nguyên nhân. |

## 36. Bài tập thực hành

### Bài tập 1 — Bật Actuator và nhận diện health groups

Tạo Spring Boot app dùng `spring-boot-starter-actuator`.

Yêu cầu:

1. Chỉ expose `health` và `info` qua HTTP nội bộ.
2. Bật `liveness`/`readiness` theo phiên bản Boot đang dùng.
3. Gọi ba endpoint health và ghi HTTP code/JSON body.
4. Phân biệt `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN`.
5. Kiểm tra một endpoint không được expose không thể bị truy cập trái phép.

### Bài tập 2 — Custom PollHealthIndicator

Tạo `PollMonitor`, `ObservedMessageSource<T>` và `PollHealthIndicator` như ví dụ.

Yêu cầu:

1. `receive()` trả null vẫn tăng heartbeat thành công.
2. Một exception làm failure count tăng và được propagate.
3. Trước poll đầu trả UNKNOWN.
4. Sau hơn ngưỡng stale trả DOWN.
5. Sau poll success lại trả UP.
6. Dùng `Clock` giả thay vì `Thread.sleep`.

### Bài tập 3 — Health group không ảnh hưởng liveness

Tạo một indicator `partnerSftpHealthIndicator` có thể chuyển DOWN bằng fixture.

Yêu cầu:

1. Custom group `integrations` chứa indicator.
2. Kiểm tra global `/health` và integration group phản ánh DOWN theo cấu hình.
3. `/health/liveness` vẫn UP khi process còn khỏe.
4. `/health/readiness` theo policy đã chốt.
5. Assert cả **JSON status và HTTP code**.

### Bài tập 4 — File/SFTP polling và backlog

Tạo File inbound adapter đọc `@TempDir` hoặc SFTP server test.

Yêu cầu:

1. Poll khi directory rỗng, không báo lỗi giả.
2. Tạo file `*.ready` và xác minh message được nhận.
3. Ngắt SFTP hoặc làm directory mất quyền, kiểm tra failure metric/health.
4. Cho một file sai schema vào quarantine, giải thích vì sao poll health có thể vẫn UP.
5. Đo oldest pending age và thiết kế alert riêng.
6. Restart poller, kiểm tra filter/checkpoint/idempotency.

### Bài tập 5 — HTTP và JDBC dependencies

Tạo một HTTP outbound gateway tới stub server và một JDBC inbox trên DB test.

Yêu cầu:

1. Stub 200, 429, 503 và timeout, quan sát transport metrics.
2. Chứng minh health active check là read-only, không tạo order test.
3. Ngắt DB và kiểm tra `db` contributor khi có DataSource.
4. Cân nhắc đưa DB vào readiness, đo hậu quả khi mọi instance cùng không ready.
5. Xác minh DB connection UP không đồng nghĩa business row đã commit.

### Bài tập 6 — JMS/AMQP/Kafka consumer observability

Chọn một broker chạy isolated:

1. Consumer bắt đầu, nhận và xử lý một message.
2. Broker restart, kiểm tra recovery của listener/container.
3. Tạo message gây lỗi, kiểm tra redelivery/DLQ/DLT.
4. So sánh connection health, consumer running, lag/queue depth và business confirmation.
5. Giải thích vì sao ACK/offset không đủ chứng minh kết quả nghiệp vụ.
6. Thiết kế alert cho poison-message loop và oldest pending.

### Bài tập 7 — Kubernetes deployment probes

Thiết kế manifest cho app có thời gian startup dài và management port có thể khác main port.

Yêu cầu:

1. Startup probe cho warmup; liveness chỉ cho fatal state.
2. Readiness theo đúng traffic/workload.
3. Kiểm tra path/port `/actuator/health/readiness` hoặc `/readyz` thực tế.
4. Giả lập SFTP outage, chứng minh không có pod restart loop.
5. Giả lập graceful shutdown và in-flight processing.
6. Ghi threshold và lựa chọn timeout dựa trên baseline, không copy số mẫu mù quáng.

### Bài tập 8 — Runbook và SLO

Một đối tác SFTP gửi file mỗi 15 phút; kết quả phải xuất hiện trên Kafka trong khoảng thời gian nghiệp vụ cho phép.

Yêu cầu:

1. Xác định SLO về **availableAt → confirmedAt**.
2. Chọn health indicators cho poll/source và metrics backlog/lag.
3. Đề xuất ngưỡng stale heartbeat theo lịch poll.
4. Thiết kế cảnh báo khi health UP nhưng business outcome trễ.
5. Viết runbook: triage, rollback, redrive, reconciliation, incident closure.
6. Đặt ownership và giới hạn thông tin được log/display.

## 37. Checklist nghiệm thu Health/Actuator cho integration services

- [ ] **Đã định nghĩa rõ mục đích** của liveness, readiness và integration dependency health.
- [ ] **Actuator starter có mặt**, phiên bản Boot/Integration tương thích.
- [ ] **Management endpoints chỉ expose tối thiểu**, không public diagnostics ngoài ý muốn.
- [ ] **Health details được kiểm soát bằng security/network policy**.
- [ ] **Các status UP/DOWN/OUT_OF_SERVICE/UNKNOWN có nghĩa rõ**.
- [ ] **HTTP status mapper được kiểm thử**, kể cả status custom.
- [ ] **Health groups được chọn có chủ đích**, không trộn mọi external dependency vào liveness.
- [ ] **Kubernetes probe gọi đúng endpoint/port/path**, kể cả khi management port tách riêng.
- [ ] **Startup probe và graceful shutdown** được cân nhắc.
- [ ] **Readiness thực sự điều khiển workload mong muốn**, không nhầm với tự pause Kafka/SFTP.
- [ ] **Các custom HealthIndicator không gây side effect**.
- [ ] **Active checks có timeout/caching/chi phí giới hạn**.
- [ ] **Poll heartbeat phân biệt source rỗng với poller ngừng**.
- [ ] **Source exception không bị nuốt thành null**.
- [ ] **SFTP/HTTP/File/JDBC/JMS/AMQP/Kafka có tín hiệu đặc thù**, không chỉ bean running.
- [ ] **DB health không được dùng như bằng chứng commit nghiệp vụ**.
- [ ] **Broker ACK/offset khác business confirmation**.
- [ ] **Lag, backlog, DLQ/quarantine có metrics/alerts riêng**.
- [ ] **Metric tags cardinality bounded, không chứa secret/PII**.
- [ ] **Có unit test với fake Clock, không dùng sleep để đo stale time**.
- [ ] **Có HTTP test cho global, liveness, readiness và diagnostic groups**.
- [ ] **Có test startup, outage, recovery, stop/restart và auth**.
- [ ] **Có transport integration/deployment tests khi SLA yêu cầu**, không chỉ mock.
- [ ] **Mọi trạng thái DOWN đều có hành động và owner**, tránh restart storm.
- [ ] **Runbook kiểm tra business reconciliation trước khi đóng incident**.
- [ ] **Fixture và endpoint state được cleanup sau tests**, không ảnh hưởng context cache.

## 38. Tổng kết

Spring Boot **Actuator Health endpoint** là một thành phần thiết yếu để vận hành các ứng dụng **Spring Integration Adapters**, nhưng nó chỉ đáng tin khi từng chỉ báo có **ý nghĩa, phạm vi và hành động đi kèm**. `/actuator/health` tổng hợp health contributors; `liveness`/`readiness` giúp điều phối vòng đời instance; **health groups** cho phép phân biệt tình trạng tích hợp với điều kiện nhận traffic.

Trong ứng dụng kết nối **File, SFTP, HTTP, JDBC, JMS, AMQP và Kafka**, không nên coi “endpoint running”, “HTTP 200”, “poll không có message”, “broker ACK” hoặc “DB connection UP” là bằng chứng toàn bộ nghiệp vụ hoàn tất. Một `HealthIndicator` thụ động dựa trên `MessageSource` có thể theo dõi poll thành công mà không mở kết nối ngoài ở mỗi lần probe. Còn **throughput, lag, pending age, duplicate, DLQ và business target confirmations** cần metrics, tracing, audit và reconciliation riêng.

Khi triển khai Kubernetes, hãy giữ **liveness** tập trung vào failure thật sự cần restart, **readiness** gắn với khả năng nhận workload, và **integration diagnostics** phục vụ vận hành chuyên sâu. Kiểm thử cả **logic indicator, HTTP mapping, security, transport outage và deployment probes** để một lỗi đối tác không biến thành restart loop; đồng thời không để một trạng thái health `UP` che giấu dữ liệu đang bị kẹt.

Điều cần trả lời khi nhìn vào dashboard không chỉ là “ứng dụng còn sống không”, mà là **nó có nên nhận thêm việc, adapter nào đang ngừng tiến triển, message nào chưa được xác nhận ở đích, ai cần xử lý và bằng chứng nào chứng minh hệ thống đã hồi phục**.
