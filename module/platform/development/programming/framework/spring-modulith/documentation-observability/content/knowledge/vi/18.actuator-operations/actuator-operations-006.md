# Readiness, liveness và telemetry backend

> **Chương:** Actuator và vận hành  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

## 1. Vì sao một ứng dụng cần nhiều tín hiệu availability?

Một ứng dụng Spring Boot có các application modules `order`, `inventory`, `payment` và `notification`. Ứng dụng có thể đã khởi động thành công, nhưng chưa chắc sẵn sàng nhận request. Ví dụ:

- Spring context đã được tạo nhưng ứng dụng vẫn đang nạp dữ liệu cấu hình.
- Cache cục bộ quan trọng chưa warm up.
- Một phần xử lý khởi tạo chưa hoàn tất.
- Ứng dụng đang shutdown và cần từ chối request mới.
- Một thành phần cục bộ bị deadlock hoặc không thể phục hồi.
- OpenTelemetry Collector hoặc trace backend tạm thời không nhận telemetry.

Nếu chỉ kiểm tra process còn sống hay cổng HTTP đang mở, hệ thống điều phối không thể phân biệt những tình huống trên. Spring Boot Actuator cung cấp health endpoint và availability states; Kubernetes sử dụng chúng qua startup, liveness và readiness probes.

Điểm cần phân biệt: **khả năng phục vụ request của ứng dụng và khả năng gửi telemetry tới backend là hai vấn đề vận hành riêng**. Một Collector gặp sự cố không nhất thiết có nghĩa ứng dụng đặt hàng không thể phục vụ khách hàng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt startup, liveness và readiness probe theo hành động mà Kubernetes thực hiện.
2. Giải thích `LivenessState`, `ReadinessState` và `ApplicationAvailability` trong Spring Boot.
3. Cấu hình health groups của Actuator cho Kubernetes.
4. Chọn đúng health indicators cần đưa vào readiness và tránh đưa dependency ngoài vào liveness.
5. Đưa readiness/liveness path lên cổng ứng dụng chính khi management server dùng cổng riêng.
6. Giám sát riêng OpenTelemetry Collector và đường truyền telemetry.
7. Đối chiếu Actuator, module metadata, event metrics và traces khi xử lý sự cố.

## 2. Ba loại Kubernetes probe

Kubernetes cung cấp ba probe, mỗi loại phục vụ một mục đích khác nhau:

| Probe | Câu hỏi | Khi thất bại liên tiếp | Dùng khi |
|---|---|---|---|
| Startup | Ứng dụng đã hoàn tất giai đoạn khởi động chưa? | Kubelet dừng và khởi động lại container theo restart policy | Startup lâu, cần dành đủ thời gian cho khởi tạo |
| Liveness | Ứng dụng còn có thể tiếp tục hoạt động không? | Kubelet restart container | Deadlock hoặc lỗi nội bộ không thể tự phục hồi |
| Readiness | Pod hiện có thể nhận traffic không? | Pod bị đánh dấu not ready và bị loại khỏi endpoint nhận traffic của Service | Đang khởi tạo, bảo trì, quá tải hoặc thiếu dependency bắt buộc |

### 2.1. Startup probe

Startup probe chỉ chạy trong giai đoạn khởi động. Khi probe này chưa thành công, kubelet chưa chạy liveness và readiness probe cho container đó.

Điều này hữu ích khi ứng dụng cần thời gian để:
- Khởi tạo Spring context và các bean.
- Chạy các tác vụ bootstrap cần thiết.
- Nạp dữ liệu tham chiếu.
- Warm up cache.
- Hoàn tất migration hoặc bước chuẩn bị được kiểm soát.

Nếu startup probe vượt quá ngưỡng thất bại, kubelet dừng container và áp dụng restart policy. Sau khi startup probe thành công, liveness và readiness mới bắt đầu hoạt động.

### 2.2. Liveness probe

Liveness trả lời câu hỏi: **process này còn có khả năng tự tiếp tục làm việc không?**

Một ví dụ phù hợp là ứng dụng bị deadlock ở một phần cốt lõi, không còn xử lý được công việc và không có cơ chế tự phục hồi. Nếu liveness thất bại đủ số lần, Kubernetes restart container.

Liveness không nên thất bại chỉ vì database, message broker, API ngoài hoặc telemetry backend đang tạm thời mất kết nối. Nếu tất cả Pod cùng kiểm tra một dependency ngoài và cùng bị đánh dấu liveness failure, Kubernetes có thể restart đồng loạt, làm tăng tải lên chính dependency đang gặp sự cố và tạo cascading failure.

### 2.3. Readiness probe

Readiness trả lời câu hỏi: **Pod này có thể nhận request mới vào lúc này không?**

Nếu readiness thất bại, container vẫn chạy. Kubernetes đánh dấu Pod not ready và không gửi traffic Service thông thường tới Pod đó cho đến khi readiness thành công trở lại.

Readiness có thể hữu ích khi:
- Ứng dụng chưa hoàn tất startup.
- Một dependency bắt buộc để xử lý request đang không khả dụng.
- Ứng dụng đang drain traffic để bảo trì.
- Hệ thống chủ động giảm tải một instance.
- Một trạng thái nghiệp vụ nội bộ khiến instance tạm thời không nhận request.

Readiness probe được chạy trong toàn bộ vòng đời container, vì vậy logic kiểm tra phải nhẹ, có timeout và tránh tạo tải lớn.

### 2.4. So sánh bằng một tình huống

Giả sử database của hệ thống đặt hàng tạm ngừng trong hai phút, còn ứng dụng và cache cục bộ vẫn hoạt động:
- Liveness vẫn thành công: process không bị deadlock và còn khả năng phục hồi.
- Readiness có thể thất bại nếu database thực sự bắt buộc để phục vụ các request hiện tại.
- Startup probe không liên quan sau khi startup đã hoàn tất.
- Khi database phục hồi, readiness có thể trở lại thành công và Pod nhận traffic trở lại.

Không nên tự động chọn cách loại Pod khỏi traffic khi database lỗi. Nếu toàn bộ replica cùng phụ thuộc vào database đó, đánh dấu tất cả not ready không khắc phục được sự cố và có thể làm dịch vụ mất toàn bộ endpoint. Cần quyết định theo khả năng phục vụ thực tế, cơ chế degrade/fallback và chiến lược chịu lỗi của ứng dụng.

## 3. Spring Boot Application Availability

Spring Boot mô hình hóa availability bằng hai state chính:
- `LivenessState`: `CORRECT` hoặc `BROKEN`.
- `ReadinessState`: `ACCEPTING_TRAFFIC` hoặc `REFUSING_TRAFFIC`.

Các state được quản lý thông qua `ApplicationAvailability`. Ứng dụng có thể đọc state hiện tại hoặc phát `AvailabilityChangeEvent` để thông báo state thay đổi.

### 3.1. Vòng đời availability khi startup

Một vòng đời Spring Boot điển hình:

| Giai đoạn | Liveness | Readiness | HTTP server |
|---|---|---|---|
| Starting | `BROKEN` | `REFUSING_TRAFFIC` | Chưa khởi động |
| Application context đã refresh | `CORRECT` | `REFUSING_TRAFFIC` | Có thể chưa nhận traffic |
| Application runners hoàn tất, ứng dụng ready | `CORRECT` | `ACCEPTING_TRAFFIC` | Nhận request |
| Graceful shutdown bắt đầu | `CORRECT` | `REFUSING_TRAFFIC` | Từ chối request mới khi quá trình drain diễn ra |

Spring Boot phát các availability events trong các giai đoạn startup và shutdown. Actuator đọc state này qua các health indicators tương ứng.

### 3.2. Health indicators mặc định

Khi Actuator hỗ trợ Kubernetes probes, Spring Boot cung cấp:

| Health indicator | State được phản ánh |
|---|---|
| `livenessstate` | `LivenessStateHealthIndicator` |
| `readinessstate` | `ReadinessStateHealthIndicator` |

Hai indicator này được đưa vào các health groups riêng:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Trong môi trường Kubernetes, Spring Boot tự động cấu hình các probe health groups. Có thể bật rõ bằng cấu hình `management.endpoint.health.probes.enabled` khi muốn kiểm thử ngoài môi trường Kubernetes hoặc muốn cấu hình chủ động.

**Health endpoint tổng hợp `/actuator/health` không đồng nghĩa với readiness hoặc liveness.** Global health có thể chứa nhiều indicator khác; Kubernetes nên gọi đúng group dành cho hành động của probe.

## 4. Cấu hình Actuator health groups

Một cấu hình cơ bản:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
~~~

Ý nghĩa:
- Chỉ expose endpoint `health` qua web trong ví dụ này.
- Bật liveness/readiness health groups.
- Tạo các đường dẫn bổ sung trên cổng HTTP chính của ứng dụng.
- Không hiển thị chi tiết health cho client probe thông thường.

Khi `add-additional-paths` bật, Spring Boot cung cấp:

| Path trên cổng ứng dụng chính | Health group |
|---|---|
| `/livez` | Liveness |
| `/readyz` | Readiness |

Nếu không bật additional paths, probe có thể dùng các path dưới Actuator:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

### 4.1. Vì sao nên kiểm tra trên cổng ứng dụng chính?

Một số hệ thống đặt Actuator ở cổng quản trị riêng bằng `management.server.port`. Nếu probe chỉ gọi cổng quản trị, nó có thể thành công trong khi web server chính gặp lỗi, không mở được kết nối hoặc không phục vụ request.

Với `management.endpoint.health.probes.add-additional-paths=true`, Spring Boot đưa liveness/readiness path lên **main server port**, giúp probe đi qua cùng web server mà traffic thực tế sử dụng.

Nếu cần path riêng, health group hỗ trợ cấu hình `additional-path` với prefix `server:` hoặc `management:`. Prefix xác định path được expose ở cổng nào; path bổ sung là một path segment.

## 5. Đưa probe vào Kubernetes Deployment

Ví dụ Deployment cho ứng dụng Spring Boot nghe cổng 8080:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: shop-service
  template:
    metadata:
      labels:
        app: shop-service
    spec:
      containers:
        - name: shop-service
          image: example.invalid/shop-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Đây là ví dụ cấu hình để học, cần thay image, namespace, security context và các thông số theo môi trường triển khai.

### 5.1. Đọc các thông số probe

| Field | Ý nghĩa |
|---|---|
| `periodSeconds` | Khoảng thời gian giữa các lần kiểm tra |
| `timeoutSeconds` | Thời gian tối đa chờ một lần kiểm tra |
| `failureThreshold` | Số lần thất bại liên tiếp trước khi probe được coi là thất bại |
| `successThreshold` | Số lần thành công liên tiếp để phục hồi trạng thái sau lỗi; liveness/startup yêu cầu giá trị 1 |
| `initialDelaySeconds` | Thời gian chờ trước lần kiểm tra đầu tiên nếu không bị startup probe chi phối |

Trong ví dụ, startup probe cho ứng dụng tối đa khoảng 300 giây (30 × 10 giây) để vượt qua giai đoạn khởi động. Khi startup thành công, liveness và readiness bắt đầu chạy.

Nếu readiness thất bại ba lần, Pod bị đánh dấu not ready; container vẫn tiếp tục chạy và probe tiếp tục được thực hiện. Nếu liveness thất bại ba lần liên tiếp, kubelet restart container theo restart policy.

Không chọn timeout quá thấp so với thời gian phản hồi bình thường của health endpoint. Một probe bị timeout do CPU contention hoặc tải cao có thể tạo ra restart không cần thiết.

## 6. Chọn HealthIndicator cho readiness

Spring Boot **không tự đưa mọi external health indicator vào readiness group**. Mặc định readiness group phản ánh readiness state của ứng dụng. Nhà phát triển phải quyết định có đưa thêm indicator hay không.

Ví dụ, nếu mọi request đặt hàng đều cần database và không có fallback:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~

`db` là health contributor cho database do Spring Boot auto-configuration cung cấp khi có cấu hình phù hợp. Khi database health indicator không UP, readiness group có thể trả trạng thái không sẵn sàng.

### 6.1. Khi nào nên đưa dependency vào readiness?

Đưa dependency vào readiness nếu đồng thời đáp ứng các điều kiện:
1. Request mà Pod nhận sẽ không thể xử lý đúng khi dependency đó không khả dụng.
2. Ứng dụng không có fallback hoặc chế độ degrade hợp lệ cho request đó.
3. Kiểm tra dependency có timeout rõ ràng và không tạo tải quá mức.
4. Khi dependency phục hồi, readiness có thể phục hồi mà không cần restart Pod.
5. Việc loại một số Pod khỏi traffic không làm phần còn lại quá tải hoặc gây mất toàn bộ service.

Nếu ứng dụng có thể phục vụ read-only request bằng cache khi database tạm ngừng, một readiness check database quá rộng có thể loại một instance vẫn phục vụ được một phần traffic. Trong hệ thống phức tạp, cần cân nhắc health group theo vai trò hoặc readiness policy riêng.

### 6.2. Vì sao không đưa dependency ngoài vào liveness?

Không cấu hình liveness group như sau:

~~~yaml
management:
  endpoint:
    health:
      group:
        liveness:
          include: livenessState,db,redis
~~~

Nếu database hoặc Redis tạm thời mất kết nối, tất cả container có thể bị restart mặc dù process không hỏng. Việc restart không sửa được database/Redis; nó chỉ tạo thêm kết nối mới và tăng áp lực lên dependency.

Liveness nên phản ánh lỗi **nội tại, không thể tự phục hồi** của process. External dependencies thường thuộc readiness hoặc một health group chẩn đoán riêng.

## 7. Chủ động thay đổi ApplicationAvailability

Spring Boot cho phép ứng dụng thay đổi availability state bằng `AvailabilityChangeEvent`. Ví dụ sau minh họa một thành phần chuyển ứng dụng sang trạng thái từ chối traffic khi cần bảo trì cục bộ:

~~~java
package com.acme.shop.availability;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
class MaintenanceAvailability {
    private final ApplicationEventPublisher events;

    MaintenanceAvailability(ApplicationEventPublisher events) {
        this.events = events;
    }

    void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.REFUSING_TRAFFIC);
    }

    void resumeAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Khi readiness state đổi sang `REFUSING_TRAFFIC`, readiness health indicator phản ánh trạng thái mới. Khi chuyển lại `ACCEPTING_TRAFFIC`, Pod có thể trở lại nhận traffic nếu các điều kiện khác đều đạt.

### 7.1. Khi nào mới đặt LivenessState.BROKEN?

Chỉ đánh dấu `LivenessState.BROKEN` khi ứng dụng phát hiện một lỗi cục bộ nghiêm trọng và không thể phục hồi theo cơ chế bình thường, ví dụ một thành phần nội bộ cốt lõi đã hỏng đến mức restart là hành động khôi phục hợp lý.

Không dùng liveness state để báo:
- Database đang bảo trì.
- OpenTelemetry Collector không truy cập được.
- Trace backend từ chối export.
- Một API ngoài có lỗi tạm thời.
- Một event listener đang retry.

Những tình huống đó không tự chứng minh process cần restart.

## 8. Telemetry backend là một đường vận hành riêng

Với Spring Modulith, nhóm có thể dùng Micrometer Observation/Tracing để tạo module invocation spans, event metrics và HTTP observations. Các spans có thể đi qua OpenTelemetry exporter tới Collector, rồi được chuyển tới Tempo, Jaeger hoặc backend tương thích.

~~~mermaid
flowchart LR
    App["Spring Boot + Spring Modulith"]
    Obs["Micrometer Observation / Tracing"]
    Exporter["OTLP exporter"]
    Collector["OpenTelemetry Collector"]
    Backend["Trace backend"]
    Client["Client / Service"]
    App --> Obs --> Exporter --> Collector --> Backend
    App -.->|"Business traffic"| Client
~~~

Nếu Collector hoặc trace backend mất kết nối:
- Ứng dụng có thể tiếp tục xử lý đơn hàng.
- Exporter có thể retry hoặc giữ batch trong queue tùy cấu hình.
- Queue có thể tăng, đầy và làm telemetry bị drop.
- Dashboard có thể thiếu trace hoặc cập nhật trễ.
- Liveness/readiness của ứng dụng không nên tự động chuyển thành DOWN chỉ vì telemetry backend lỗi.

**Telemetry là bằng chứng giúp quan sát hoạt động, không mặc nhiên là dependency nghiệp vụ của request.** Nếu tổ chức có yêu cầu bắt buộc về audit hoặc lưu vết giao dịch, cần thiết kế event log/audit store bền vững theo nghiệp vụ. Không coi trace exporter hoặc Collector là nơi lưu trữ giao dịch có bảo đảm.

## 9. Theo dõi sức khỏe của OpenTelemetry Collector

Collector có các extension và internal telemetry riêng. Chúng giúp giám sát Collector độc lập với health endpoint của ứng dụng.

### 9.1. Health check extension

Ví dụ cấu hình extension:

~~~yaml
extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
~~~

Khai báo extension trong mục `extensions` chưa đủ; phải kích hoạt nó trong `service.extensions`. Endpoint health check cho biết trạng thái health check của Collector theo extension/version được triển khai.

Health check endpoint **không chứng minh rằng trace đã được lưu bền vững hoặc truy vấn được ở backend**. Nó chỉ là một tín hiệu về trạng thái Collector. Vẫn cần theo dõi receiver, exporter, queue và backend.

### 9.2. Internal telemetry metrics

Collector tự phát metrics để quan sát process và các thành phần nhận/gửi telemetry. Tùy version và cấu hình, các metrics thường dùng gồm:

| Metric | Câu hỏi vận hành |
|---|---|
| `otelcol_receiver_accepted_spans` | Collector đã nhận bao nhiêu spans? |
| `otelcol_receiver_refused_spans` | Receiver từ chối bao nhiêu spans? |
| `otelcol_exporter_sent_spans` | Exporter gửi thành công bao nhiêu spans? |
| `otelcol_exporter_send_failed_spans` | Có bao nhiêu spans gặp lỗi gửi tới đích? |
| `otelcol_exporter_enqueue_failed_spans` | Có bao nhiêu spans không đưa được vào queue? |
| `otelcol_exporter_queue_size` | Queue hiện có bao nhiêu batch? |
| `otelcol_exporter_queue_capacity` | Queue có dung lượng bao nhiêu batch? |
| `otelcol_process_memory_rss` | Collector đang sử dụng bao nhiêu resident memory? |
| `otelcol_process_uptime` | Collector đã chạy bao lâu? |

Collector thường expose internal Prometheus metrics tại `127.0.0.1:8888/metrics` theo cấu hình mặc định của bản phân phối. Endpoint và metric names có thể thay đổi theo Collector version, distribution và cấu hình telemetry; hãy kiểm tra cấu hình đang chạy.

### 9.3. Diễn giải dữ liệu nhận và gửi

Một số mẫu dấu hiệu:

| Quan sát | Khả năng cần điều tra |
|---|---|
| Accepted tăng, sent tăng tương ứng | Luồng ingest/export có hoạt động |
| Accepted tăng, queue size tăng liên tục | Exporter hoặc backend chậm hơn tốc độ nhận |
| Queue gần capacity, enqueue failures tăng | Queue đầy; có nguy cơ mất telemetry |
| Send failures tăng kéo dài | Network, auth, TLS hoặc backend có vấn đề |
| Refused spans tăng | Receiver từ chối dữ liệu hoặc quá tải |
| Accepted không tăng | Ứng dụng không gửi, không phát spans, sampling loại trace hoặc receiver không nhận |
| Sent tăng nhưng backend không tìm thấy trace | Kiểm tra routing, tenant, retention, indexing và truy vấn backend |

Không dùng một tỷ lệ accepted/sent đơn giản làm bằng chứng chắc chắn về mất dữ liệu. Sampling, filtering, routing, retry, queue và độ trễ có thể làm số liệu lệch nhau trong một cửa sổ ngắn. So sánh cùng signal type và khoảng thời gian đủ dài, đồng thời kiểm tra log và trạng thái queue.

## 10. Có nên đưa telemetry backend vào readiness của ứng dụng?

Thông thường **không nên**.

Giả sử service `order` gửi spans tới Collector. Nếu Collector tạm thời dừng:
1. Request đặt hàng vẫn có thể được xử lý và commit thành công.
2. Trace exporter có thể retry hoặc drop spans khi hết queue.
3. Dashboard tracing tạm thiếu dữ liệu.
4. Nếu readiness kiểm tra Collector, mọi Pod `order` có thể bị loại khỏi Service.
5. Traffic có thể dồn vào các service/replica khác dù logic đặt hàng vẫn hoạt động.

Kết quả là một sự cố quan sát telemetry biến thành sự cố phục vụ người dùng.

### 10.1. Cách phân tách health signal

| Health signal | Nơi kiểm tra | Hành động khi lỗi |
|---|---|---|
| App liveness | Actuator `/livez` | Restart khi process không thể tự phục hồi |
| App readiness | Actuator `/readyz` | Ngừng gửi traffic mới tới Pod |
| Collector health | Collector health_check extension | Cảnh báo hoặc điều phối Collector |
| Collector pipeline | Internal metrics, logs, queue và exporter failures | Điều tra backlog, retry, network, backend |
| Trace backend ingest/query | Synthetic trace hoặc backend health/ingest metrics | Cảnh báo đội observability |
| Business audit/event durability | Event store/outbox/audit subsystem | Áp dụng policy nghiệp vụ và khôi phục dữ liệu |

Nếu cần trang chẩn đoán trong Actuator, có thể tạo health group riêng tên `telemetry` cho một custom contributor. Ví dụ đường dẫn `/actuator/health/telemetry` dùng để người vận hành kiểm tra trạng thái kết nối telemetry. **Không thêm group này vào liveness hoặc readiness theo mặc định.**

### 10.2. Khi nào telemetry thực sự là dependency bắt buộc?

Chỉ khi hợp đồng nghiệp vụ quy định request không được chấp nhận nếu không ghi được một bản audit bền vững, mới nên đưa cơ chế audit vào quyết định phục vụ request. Khi đó cần phân biệt:
- Audit record có được ghi bền vững và có transaction semantics phù hợp không?
- Telemetry backend có bảo đảm durability và xác nhận commit không?
- Có cơ chế retry, outbox và xử lý trùng lặp không?
- Mất telemetry có thể khiến dữ liệu nghiệp vụ không thể kiểm toán không?

Trace exporter thường được thiết kế cho quan sát và có thể sampling/drop; không nên dùng nó làm audit log duy nhất.

## 11. Bảo vệ health endpoints và tránh lộ thông tin

Health endpoint có thể tiết lộ trạng thái database, broker, filesystem, remote services hoặc chi tiết exception. Vì vậy:
- Chỉ expose endpoint cần thiết cho probe.
- Không expose toàn bộ Actuator endpoint ra public network.
- Giới hạn quyền truy cập management interface bằng network policy, authentication hoặc cấu hình ingress phù hợp.
- Dùng `show-details: never` cho endpoint probe công khai.
- Nếu cần chi tiết, tạo management endpoint nội bộ có xác thực và chỉ cho operator truy cập.
- Health check phải có timeout, không truy vấn lặp lại đắt đỏ theo mỗi lần kubelet gọi.
- Tránh đưa connection string, credentials, tenant IDs hoặc dữ liệu nhạy cảm vào health details.

Ví dụ cấu hình tối thiểu đã nêu ở trên chỉ expose `health`. Nếu cần thêm `metrics`, `prometheus` hoặc `modulith`, hãy đánh giá riêng quyền truy cập và network exposure.

## 12. Kiểm chứng với Spring Modulith và Actuator

Trong ứng dụng Spring Modulith, các nguồn bằng chứng trả lời các câu hỏi khác nhau:

| Nguồn | Câu hỏi |
|---|---|
| `/actuator/health/liveness` | Process có ở trạng thái liveness CORRECT không? |
| `/actuator/health/readiness` | Ứng dụng có đang ACCEPTING_TRAFFIC không? |
| `/livez` và `/readyz` | Main HTTP connector có phục vụ probe path không? |
| `/actuator/modulith` | Runtime nhận diện những application modules nào? |
| `/actuator/metrics` | Những meter nào đã được đăng ký? |
| `module.events.published` | Có event publication được instrument không? |
| Trace backend | Request thực tế đi qua module invocation nào? |
| Collector internal metrics | Telemetry có được nhận và gửi đi không? |

Một tình huống thực tế:
- `/readyz` trả thành công.
- `/actuator/modulith` hiển thị các module `order`, `inventory`, `payment`.
- `module.events.published` tăng.
- Collector `otelcol_exporter_send_failed_spans` tăng và queue tăng.
- Backend tracing không hiển thị trace mới.

Kết luận hợp lý: **ứng dụng vẫn có thể nhận traffic nhưng pipeline telemetry đang gặp sự cố**. Cần kiểm tra Collector exporter, network, auth/TLS, queue và backend ingest. Không restart toàn bộ ứng dụng đặt hàng chỉ vì trace backend tạm ngừng nhận spans.

## 13. Quy trình xử lý sự cố theo thứ tự

### Bước 1 — Xác định loại probe đang thất bại
- Startup probe: ứng dụng có khởi động trong thời hạn cấu hình không?
- Liveness probe: process có bị deadlock hoặc hỏng nội bộ không?
- Readiness probe: ứng dụng đang từ chối traffic hay dependency bắt buộc đang lỗi?
- Collector health: bản thân Collector có trả health status không?

Không kết luận từ trạng thái Pod tổng quát; đọc probe events và response endpoint cụ thể.

### Bước 2 — Kiểm tra port và path

Xác nhận kubelet gọi đúng port:
- Main server port với `/livez`, `/readyz` khi bật additional paths.
- Management port với `/actuator/health/liveness`, `/actuator/health/readiness` nếu cấu hình theo cách đó.

Nếu management port riêng, kiểm tra main connector độc lập.

### Bước 3 — Đọc health contributor

Nếu readiness DOWN, xác định contributor nào làm group DOWN. Kiểm tra cấu hình include/exclude để biết có external health indicator nào được thêm vào không.

### Bước 4 — Phân biệt lỗi ứng dụng và lỗi telemetry

Nếu ứng dụng ready nhưng trace thiếu:
- Kiểm tra exporter log và retry.
- Kiểm tra Collector accepted/refused spans.
- Kiểm tra exporter queue và send failures.
- Kiểm tra backend ingest, tenant và truy vấn.
- Kiểm tra sampling và observation predicate nếu có cấu hình.

### Bước 5 — Xác minh nghiệp vụ

Đối chiếu request response, dữ liệu commit, event publication state và log nghiệp vụ. Metric publish hoặc trace thiếu không tự chứng minh request thành công/thất bại.

### Bước 6 — Khôi phục và quan sát

Sau khi sửa, xác nhận readiness ổn định, queue giảm về mức bình thường, send failures ngừng tăng và trace mới có thể truy vấn được ở backend.

## 14. Thực hành: mô phỏng readiness và telemetry backend outage

Dựng ứng dụng Spring Boot có module `order`, `inventory`, `notification`, Actuator health probes và một OpenTelemetry Collector.

### Phần A — Probe của ứng dụng
1. Bật Actuator health probes.
2. Bật additional paths trên main server port.
3. Cấu hình Kubernetes startup, liveness và readiness probe.
4. Gửi request trong lúc ứng dụng đang khởi tạo; xác nhận Pod chưa nhận traffic.
5. Sau khi startup hoàn tất, xác nhận readiness chuyển sang ACCEPTING_TRAFFIC.
6. Chuyển ứng dụng sang REFUSING_TRAFFIC bằng availability event; xác nhận Pod bị loại khỏi Service endpoints nhưng process không bị restart.
7. Khôi phục ACCEPTING_TRAFFIC và xác nhận Pod nhận traffic trở lại.

### Phần B — Dependency và liveness
1. Nếu database là dependency bắt buộc, thêm `db` vào readiness group.
2. Tạm dừng database trong môi trường test.
3. Quan sát readiness thất bại nhưng liveness vẫn thành công.
4. Phục hồi database và xác nhận readiness trở lại.
5. Thử một lỗi nội bộ không thể phục hồi trong môi trường kiểm thử; đánh giá có nên publish LivenessState.BROKEN hay không.

### Phần C — Telemetry backend outage
1. Bật Collector health_check extension và internal metrics.
2. Gửi một request đi qua ít nhất hai module để tạo spans.
3. Xác nhận Collector nhận spans và exporter gửi tới backend.
4. Tạm ngắt kết nối Collector tới backend trong môi trường thử nghiệm.
5. Theo dõi queue size, send failures, enqueue failures và Collector logs.
6. Xác nhận `/readyz` của ứng dụng vẫn phản ánh khả năng phục vụ nghiệp vụ, không tự DOWN chỉ vì trace backend mất kết nối.
7. Khôi phục backend, kiểm tra retry/queue và truy vấn trace mới.

### Bảng kết quả mong đợi

| Tình huống | Liveness app | Readiness app | Hành động chính |
|---|---|---|---|
| Đang startup, chưa hoàn tất | Chưa được kiểm tra nếu startup probe chưa pass | Chưa được kiểm tra nếu startup probe chưa pass | Chờ startup probe |
| App ready | UP | UP | Nhận traffic |
| App chủ động drain | UP | DOWN/REFUSING_TRAFFIC | Ngừng traffic mới |
| Database bắt buộc bị lỗi và được đưa vào readiness | UP | DOWN | Loại khỏi traffic, chờ phục hồi |
| Collector/backend telemetry lỗi | UP | Thường vẫn UP | Điều tra telemetry pipeline |
| App deadlock không tự phục hồi | DOWN/BROKEN | Có thể DOWN | Restart container |
| Backend trace phục hồi | UP | UP | Xác nhận export và trace visibility |

Đây là kết quả kỳ vọng của kịch bản thực hành, không phải kết quả một cluster Kubernetes đã được chạy trong repository.

## 15. Các lỗi thiết kế thường gặp

### 15.1. Dùng global health làm liveness

`/actuator/health` có thể chứa DB, broker, disk space hoặc các indicator khác. Dùng global health cho liveness có thể khiến dependency ngoài làm container restart. Hãy dùng liveness health group riêng.

### 15.2. Đưa tất cả dependency vào readiness

Nếu tất cả service đều kiểm tra cùng một database hoặc broker, một outage có thể khiến toàn bộ Pod bị loại khỏi Service. Chỉ thêm dependency thật sự bắt buộc cho khả năng phục vụ request và đánh giá fallback/circuit breaker.

### 15.3. Đặt Actuator ở management port rồi chỉ probe cổng đó

Health endpoint quản trị có thể trả thành công dù main server connector không hoạt động. Dùng additional paths trên cổng chính hoặc thiết kế probe đi qua đúng đường HTTP mà traffic sử dụng.

### 15.4. Dùng liveness để thay thế retry

Một API ngoài chập chờn không phải lý do restart process. Dùng timeout, retry có giới hạn, circuit breaker và fallback ở tầng gọi dependency. Liveness chỉ dành cho trạng thái nội bộ không thể phục hồi.

### 15.5. Đưa Collector vào app readiness

Collector có thể bị deploy, restart hoặc mất kết nối backend trong khi ứng dụng vẫn phục vụ request. Nếu readiness phụ thuộc Collector, sự cố telemetry có thể làm service nghiệp vụ mất traffic. Theo dõi Collector và backend bằng health endpoint, internal metrics và synthetic telemetry riêng.

### 15.6. Nghĩ Collector health UP nghĩa là trace đã được lưu

Health check extension chỉ xác nhận trạng thái health của Collector theo extension. Nó không chứng minh exporter gửi thành công, backend nhận dữ liệu, dữ liệu đã được lưu bền vững hoặc query trả về trace. Cần theo dõi accepted/sent/failed/queue và xác minh backend.

### 15.7. Health check quá đắt hoặc có side effect

Không thực hiện migration, publish event, gửi trace thử, hoặc chạy truy vấn nặng trong mỗi lần kubelet gọi readiness. Health checks nên nhẹ, có timeout và không thay đổi dữ liệu nghiệp vụ.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Readiness probe thất bại thì Kubernetes có restart container không?

**Đáp án:** Không. Pod được đánh dấu not ready và không nhận traffic Service thông thường; container vẫn chạy và readiness tiếp tục được kiểm tra.

**Câu 2.** Liveness probe thất bại liên tiếp có thể khiến điều gì xảy ra?

**Đáp án:** Kubelet dừng và khởi động lại container theo restart policy sau khi vượt ngưỡng failure.

**Câu 3.** Startup probe có tác dụng gì với liveness/readiness?

**Đáp án:** Khi startup probe được cấu hình, kubelet chưa chạy liveness và readiness cho đến khi startup probe thành công.

**Câu 4.** Vì sao không nên đưa database vào liveness?

**Đáp án:** Database outage có thể khiến mọi Pod restart đồng loạt dù process không hỏng, làm tăng tải và gây cascading failure.

**Câu 5.** Spring Boot readiness group mặc định có tự chứa mọi health indicator không?

**Đáp án:** Không. Mặc định readiness phản ánh readiness state; nhà phát triển quyết định có thêm indicator như `db` hay custom check.

**Câu 6.** Khi `management.server.port` tách khỏi main port, làm sao kiểm tra đúng web server phục vụ traffic?

**Đáp án:** Bật `management.endpoint.health.probes.add-additional-paths=true` để tạo `/livez` và `/readyz` trên main server port.

**Câu 7.** Collector health endpoint trả thành công có chứng minh backend đã lưu trace không?

**Đáp án:** Không. Cần kiểm tra exporter send failures, queue, backend ingest và khả năng truy vấn trace.

**Câu 8.** Trace backend tạm thời không nhận telemetry, ứng dụng đặt hàng có phải chuyển readiness sang DOWN?

**Đáp án:** Thông thường không. Nếu nghiệp vụ vẫn phục vụ được, hãy giám sát và xử lý pipeline telemetry riêng. Audit bắt buộc cần một cơ chế lưu bền vững riêng.

**Câu 9.** Counter `module.events.published` tăng có chứng minh listener đã hoàn tất không?

**Đáp án:** Không. Publication và listener completion là các giai đoạn khác nhau; cần đối chiếu publication state, log và kết quả nghiệp vụ.

## 17. Checklist triển khai production

- [ ] Startup, liveness và readiness được định nghĩa theo ba mục đích khác nhau.
- [ ] Liveness chỉ phản ánh lỗi nội bộ không thể tự phục hồi.
- [ ] Readiness chỉ chứa dependency thực sự cần để phục vụ request.
- [ ] Không đưa telemetry backend vào readiness mặc định.
- [ ] Đã quyết định rõ cách xử lý khi dependency chung của toàn bộ replica bị lỗi.
- [ ] Actuator chỉ expose health endpoint cần thiết cho probe.
- [ ] Chi tiết health không bị lộ cho client không được phép.
- [ ] Nếu dùng management port riêng, probe vẫn kiểm tra main server connector.
- [ ] Startup probe có đủ thời gian cho ứng dụng khởi tạo.
- [ ] Timeout/period/failure threshold phù hợp với latency và tải thực tế.
- [ ] Readiness có thể phục hồi tự động sau outage.
- [ ] Collector health_check extension được bật trong `service.extensions`.
- [ ] Collector internal metrics được scrape/giám sát.
- [ ] Có cảnh báo cho refused spans, send failures, queue saturation và enqueue failures.
- [ ] Backend có kiểm tra ingest và synthetic trace/query khi cần.
- [ ] Audit/event durability được xử lý bằng cơ chế phù hợp với nghiệp vụ, không dựa duy nhất vào trace exporter.
- [ ] Có runbook phân biệt app availability với telemetry pipeline health.

## 18. Ghi nhớ

- **Startup probe** bảo vệ ứng dụng khởi động lâu; **liveness** quyết định restart; **readiness** quyết định nhận traffic.
- Spring Boot Actuator ánh xạ `ApplicationAvailability` thành health groups `liveness` và `readiness`.
- **Không đưa database, broker, API ngoài hoặc telemetry backend vào liveness.** Chỉ thêm dependency vào readiness sau khi đánh giá khả năng phục vụ và fallback.
- Khi management server dùng cổng riêng, additional paths giúp probe kiểm tra main server connector.
- **Collector health UP không đồng nghĩa trace đã đến backend.** Theo dõi receiver, exporter, queue, failed sends và xác minh truy vấn ở đích.
- Module graph, Actuator health, event metrics và tracing cung cấp các bằng chứng khác nhau; không suy luận trạng thái nghiệp vụ từ một tín hiệu duy nhất.

## Tài liệu tham khảo

1. [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — Liveness/readiness health groups, additional paths, external state và cảnh báo dependency.
2. [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html) — `ApplicationAvailability`, `AvailabilityChangeEvent` và lifecycle states.
3. [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html) — Health groups và Kubernetes probes trong Boot 3.5.
4. [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/) — Hành vi kubelet, failure thresholds và cấu hình probe.
5. [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) — Ví dụ cấu hình và startup timing.
6. [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/) — Health check extension và cách kích hoạt extension trong service section.
7. [OpenTelemetry Collector — Internal Telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/) — Internal metrics, exporter queues, accepted/refused spans và send failures.
8. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Module observability và event metrics.

