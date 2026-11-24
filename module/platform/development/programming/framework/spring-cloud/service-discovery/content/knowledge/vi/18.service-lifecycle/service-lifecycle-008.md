# Rolling update, blue-green và thời gian chồng lấn các instance

Khi triển khai phiên bản mới của một microservice, phiên bản cũ và phiên bản mới thường phải cùng tồn tại trong một khoảng thời gian. Khoảng chồng lấn này giúp hệ thống tiếp tục phục vụ request trong khi instance mới khởi động, kiểm tra readiness, đăng ký vào registry và được các consumer nhìn thấy. Nếu dừng instance cũ quá sớm, consumer có thể vẫn giữ địa chỉ cũ trong cache hoặc chưa biết instance mới đã sẵn sàng.

Trong hệ thống Spring Cloud, rolling update và blue-green cần phối hợp ba vòng đời: vòng đời của process/container, trạng thái trong Eureka hoặc Consul, và cache danh sách instance ở consumer/LoadBalancer. Một lần deploy thành công ở orchestrator chưa chứng minh tất cả consumer đã chuyển sang endpoint mới.

## 1. Vì sao cần thời gian chồng lấn?

Giả sử `inventory-service` đang có ba instance phiên bản `v1`. Khi triển khai `v2`, không nên dừng cả ba instance cũ rồi mới khởi động instance mới. Consumer có thể rơi vào khoảng thời gian không tìm thấy instance, hoặc tiếp tục gọi địa chỉ cũ dù process đã dừng.

Thời gian chồng lấn cho phép:

- Instance mới khởi động, nạp cấu hình, kết nối dependency và hoàn tất warm-up.
- Readiness probe xác nhận instance có thể nhận request.
- Eureka/Consul ghi nhận trạng thái mới và cập nhật registry/cache.
- Consumer tải hoặc quan sát thay đổi, sau đó LoadBalancer bắt đầu chọn instance mới.
- Instance cũ ngừng nhận request mới, hoàn tất request đang chạy và đóng tài nguyên có kiểm soát.

Điều quan trọng là phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Process overlap | Process cũ và mới cùng tồn tại trên hạ tầng |
| Discovery overlap | Cả instance cũ và mới cùng xuất hiện trong registry |
| Traffic overlap | Consumer có thể chọn cả instance cũ và mới để xử lý request mới |
| Drain period | Instance cũ còn chạy để hoàn tất request/connection đã nhận nhưng không nhận traffic mới |

Trong rolling update, traffic overlap thường được chấp nhận nếu hai phiên bản tương thích API và dữ liệu. Trong blue-green, traffic overlap thường được kiểm soát bằng gateway, service ID riêng hoặc cơ chế routing có trọng số.

## 2. Rolling update hoạt động như thế nào?

Rolling update thay từng nhóm instance cũ bằng instance mới. Trong Kubernetes Deployment, chiến lược `RollingUpdate` dùng hai tham số chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `maxSurge` | Số Pod được phép tạo thêm vượt số replica mong muốn trong lúc cập nhật |
| `maxUnavailable` | Số Pod tối đa được phép không sẵn sàng trong quá trình cập nhật |

Giả sử Deployment có `replicas: 4`, `maxSurge: 1` và `maxUnavailable: 0`: Kubernetes có thể tạo thêm một Pod mới, nhưng phải giữ đủ bốn Pod sẵn sàng trước khi tiếp tục loại Pod cũ. Điều này cần tài nguyên CPU/RAM dư để chạy Pod mới trong giai đoạn chồng lấn.

Ví dụ manifest rút gọn:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: inventory-service
          image: example/inventory-service:2.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health
              port: http
            periodSeconds: 5
            failureThreshold: 30
```

`maxSurge` và `maxUnavailable` có thể là số tuyệt đối hoặc phần trăm. Với giá trị phần trăm, Kubernetes làm tròn `maxSurge` lên và `maxUnavailable` xuống. Giá trị mặc định của cả hai là 25%. Chọn giá trị dựa trên số replica, năng lực cluster và mức sẵn sàng tối thiểu cần duy trì.

`minReadySeconds` yêu cầu Pod phải ở trạng thái Ready liên tục trong khoảng thời gian đó trước khi Deployment coi rollout đã tiến triển. Nó không thay thế thời gian chờ registry hoặc consumer cache cập nhật.

## 3. Readiness phải phản ánh khả năng nhận traffic

Readiness trả lời câu hỏi: instance có thể nhận request mới ngay lúc này không? Liveness trả lời câu hỏi khác: process có còn sống đủ để tiếp tục chạy không? Không dùng liveness thay readiness.

Trong Spring Boot, có thể bật Kubernetes probes:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
```

Spring Boot cung cấp các endpoint `/actuator/health/liveness` và `/actuator/health/readiness`. Khi khởi động, instance có thể sống nhưng chưa sẵn sàng vì đang warm-up, chạy migration tương thích, nạp cache hoặc chờ dependency thiết yếu. Khi đó readiness nên ở trạng thái `REFUSING_TRAFFIC`; liveness vẫn có thể là `CORRECT`.

Không đưa mọi dependency vào liveness. Nếu database tạm thời mất kết nối và liveness thất bại, orchestrator có thể restart hàng loạt instance trong lúc hệ thống đang quá tải. Readiness chỉ nên xét những dependency thực sự cần cho request mà service cam kết phục vụ.

**Lưu ý quan trọng:** Kubernetes readiness chỉ điều khiển Pod Ready và endpoint của Kubernetes Service. Nó không tự động đổi trạng thái trong Eureka hoặc Consul. Nếu consumer tra cứu qua Eureka/Consul, cần cấu hình health integration hoặc quy trình pause/deregister tương ứng để registry phản ánh trạng thái đó.

## 4. Đăng ký instance mới trước khi rút instance cũ

Trình tự rolling update an toàn ở mức tổng quát:

1. Tạo instance mới với phiên bản mới.
2. Chờ ứng dụng khởi động, kết nối dependency và hoàn tất warm-up.
3. Để readiness chuyển sang sẵn sàng.
4. Xác nhận Eureka/Consul đã nhận instance mới với trạng thái phù hợp.
5. Chờ consumer/LoadBalancer nhìn thấy instance mới; gửi smoke test qua đường gọi thực tế.
6. Chọn một instance cũ để ngừng nhận request mới.
7. Cập nhật trạng thái discovery hoặc deregister instance cũ.
8. Chờ cache và routing ngừng chọn instance cũ.
9. Drain request, connection và message đang xử lý.
10. Gửi SIGTERM/đóng application context và kết thúc process.
11. Lặp lại với instance cũ tiếp theo.

Trong Kubernetes, controller quản lý rollout theo Pod readiness và EndpointSlice. Trong Eureka/Consul, trạng thái discovery có thể có độ trễ riêng. Nếu hai cơ chế cùng tồn tại, hãy kiểm tra cả hai thay vì chỉ dựa vào trạng thái Deployment.

## 5. Eureka trong lúc rolling update

Eureka nhận registration metadata và heartbeat từ từng instance. Với cấu hình phổ biến, heartbeat mặc định là 30 giây, lease expiration là 90 giây. Khi instance tắt có kiểm soát, Eureka Client gửi thao tác cancel/unregister trong shutdown; nếu process chết đột ngột, server phải chờ lease hết hạn hoặc health/status mechanism cập nhật.

### 5.1. Đảm bảo instance mới chỉ được công bố khi đã sẵn sàng

Mặc định Eureka dựa trên heartbeat để xác định client còn sống. Nếu muốn trạng thái Actuator của ứng dụng được truyền tới Eureka, bật health check integration:

```yaml
eureka:
  client:
    healthcheck:
      enabled: true
```

Đặt thuộc tính này trong `application.yml`, không đặt trong `bootstrap.yml`. Khi được bật, trạng thái health của ứng dụng có thể ảnh hưởng tới trạng thái instance Eureka; consumer mặc định thường chỉ dùng instance `UP`.

Không giả định Kubernetes readiness tự cập nhật Eureka. Kiểm tra instance status trên Eureka Dashboard/API và kiểm tra consumer thực sự lọc trạng thái `UP`.

### 5.2. Đưa instance cũ ra khỏi traffic

Spring Cloud Commons cung cấp actuator pause/resume khi các endpoint tương ứng được bật. Gọi `/actuator/pause` đưa instance Eureka sang `OUT_OF_SERVICE`, giúp các consumer ngừng chọn instance cho request mới sau khi thay đổi được truyền tới registry/cache. Gọi `/actuator/resume` bỏ override và trạng thái ứng dụng được khôi phục ở heartbeat tiếp theo.

Đây là thao tác đưa instance ra khỏi rotation; nó không tự chờ tất cả request đang chạy kết thúc. Sau pause, cần chờ consumer ngừng chọn instance cũ rồi mới drain và shutdown.

Trong shutdown có kiểm soát, Eureka Client thường cancel registration. Nếu shutdown bất thường, lease mặc định có thể khiến record tồn tại lâu hơn. Không dùng lease expiration 90 giây như thời gian drain; lease là cơ chế phát hiện client mất liên lạc, không phải quy trình graceful deployment.

### 5.3. Độ trễ propagation

Spring Cloud Netflix giải thích instance có thể cần tới ba chu kỳ heartbeat để metadata được đồng bộ giữa instance, server và client. Với heartbeat mặc định 30 giây, tình huống thông thường có thể cần khoảng 90 giây; Netflix Eureka cũng mô tả cache server và fetch delta client có thể khiến thay đổi lan truyền tới các consumer mất tới khoảng hai phút.

Đây là mô tả về propagation và cache, không phải SLA cố định. Peer replication, server response cache, registry fetch interval, mạng và cache LoadBalancer có thể làm thời gian thực tế thay đổi. Hãy đo trên đúng topology.

## 6. Consul trong lúc rolling update

Spring Cloud Consul đăng ký service với Consul Agent. Mặc định một HTTP health check gọi `/actuator/health` mỗi 10 giây. Nếu check thất bại, instance chuyển sang `critical`. Spring Cloud Consul có `deregister=true` mặc định để hủy registration khi ứng dụng shutdown có kiểm soát.

Ví dụ cấu hình health check dùng readiness endpoint:

```yaml
spring:
  cloud:
    consul:
      discovery:
        register: true
        deregister: true
        register-health-check: true
        health-check-path: /actuator/health/readiness
        health-check-interval: 10s
```

`health-check-path`, `health-check-interval`, `register` và `deregister` là cấu hình phía producer. `deregister: true` cho phép Spring Cloud Consul tự hủy registration khi ứng dụng shutdown có kiểm soát. Ở consumer, bật `query-passing` nếu chỉ muốn nhận instance có các check ở trạng thái passing:

```yaml
spring:
  cloud:
    consul:
      discovery:
        query-passing: true
```

`query-passing` mặc định là `false`. Nếu consumer không bật hoặc không lọc trạng thái phù hợp, một record `critical` vẫn có thể xuất hiện trong kết quả truy vấn tùy API.

Khi instance cũ chuyển readiness sang không sẵn sàng, Consul Agent sẽ phát hiện qua health check ở lần kiểm tra tiếp theo. Với interval 10 giây, không nên kỳ vọng thay đổi được phản ánh tức thì. Có thể dùng API deregister chủ động trong quy trình shutdown hoặc để Spring Cloud Consul tự deregister khi application context đóng.

`health-check-critical-timeout` có thể yêu cầu Consul tự deregister service nếu trạng thái critical kéo dài quá thời hạn; đây là chính sách dọn record, không phải cơ chế drain. Không đặt thời hạn quá ngắn nếu instance có thể phục hồi sau một đợt lỗi mạng.

## 7. Tính thời gian chồng lấn

Không nên chọn overlap chỉ bằng một con số mặc định. Hãy đo các mốc sau:

| Ký hiệu | Khoảng thời gian |
|---|---|
| `T_ready` | Từ lúc process mới khởi động tới khi readiness đạt |
| `T_registry` | Từ readiness tới khi registry ghi nhận trạng thái mới |
| `T_consumer` | Từ registry update tới khi các consumer quan trọng nhìn thấy instance mới |
| `T_validation` | Thời gian smoke test và xác nhận phiên bản mới xử lý đúng request |
| `T_remove_old` | Thời gian từ lúc đánh dấu instance cũ không nhận traffic tới khi consumer ngừng chọn nó |
| `T_drain` | Thời gian hoàn tất request, connection và message đang xử lý |
| `T_margin` | Khoảng dự phòng cho jitter, retry, mạng và biến động tải |

Thời gian traffic overlap tối thiểu nên bao phủ lúc instance mới được consumer nhìn thấy và xác nhận:

\[
T_{overlap} \ge T_{registry} + T_{consumer} + T_{validation} + T_{margin}
\]

Process cũ cần tiếp tục sống thêm trong thời gian loại khỏi routing và drain:

\[
T_{old\_alive\_after\_cutoff} \ge T_{remove\_old} + T_{drain} + T_{margin}
\]

Ví dụ minh họa: readiness mới đạt sau 25 giây; registry và consumer cần 70 giây để nhìn thấy instance; smoke test mất 15 giây; thời gian dự phòng 20 giây. Traffic overlap cần ít nhất khoảng 105 giây sau khi bắt đầu readiness/registration (không tính thời gian khởi động 25 giây nếu mốc đo bắt đầu từ lúc process được tạo). Khi rút instance cũ, nếu propagation removal mất 40 giây và request dài nhất cần 30 giây để hoàn tất, process cũ cần được giữ thêm ít nhất 70 giây cộng dự phòng.

Đo p95/p99 propagation và thời gian request dài nhất thay vì dùng trung bình. Nếu hệ thống có WebSocket, streaming, upload lớn hoặc tác vụ dài, `T_drain` cần tính theo loại kết nối đó hoặc có chính sách giới hạn/di chuyển session riêng.

## 8. Blue-green deployment khác rolling update ở đâu?

Blue-green duy trì hai môi trường hoặc hai nhóm instance độc lập:

- **Blue:** phiên bản hiện tại đang phục vụ production.
- **Green:** phiên bản mới đã triển khai và được kiểm thử trước khi nhận traffic production.

Luồng triển khai:

1. Giữ Blue tiếp tục phục vụ traffic.
2. Dựng Green với đủ capacity, cấu hình và dependency.
3. Chờ Green readiness và health check đạt.
4. Kiểm tra Green qua route nội bộ hoặc smoke-test URL riêng.
5. Chuyển traffic ở gateway, ingress hoặc load balancer sang Green (có thể chuyển từng phần nếu hỗ trợ weighted routing).
6. Theo dõi error rate, latency, saturation và business metrics.
7. Giữ Blue sống trong rollback window.
8. Khi Green ổn định và request cũ đã drain, mới deregister/shutdown Blue.

### 8.1. Tránh để discovery tự trộn Blue và Green ngoài ý muốn

Nếu Blue và Green cùng đăng ký một service ID, ví dụ `payment-service`, một consumer dùng `DiscoveryClient` + LoadBalancer có thể nhận cả hai nhóm instance và gửi traffic tới cả hai. Điều đó có thể biến một lần cutover blue-green thành rollout trộn phiên bản.

Có ba cách kiểm soát:

- Đăng ký service ID riêng, ví dụ `payment-blue` và `payment-green`; gateway hoặc cấu hình upstream quyết định service ID đang nhận traffic.
- Dùng tag/metadata version và một routing layer có khả năng lọc hoặc phân phối trọng số theo version.
- Giữ discovery nội bộ cho từng nhóm và thực hiện cutover ở gateway/service mesh thay vì để mọi consumer tự chọn từ danh sách chung.

Với Eureka, metadata không tự động tạo routing rule; consumer/LoadBalancer phải hiểu metadata đó. Với Consul, tags có thể dùng trong truy vấn theo tag nếu client được cấu hình phù hợp. Không chỉ thêm tag `blue`/`green` rồi giả định mọi consumer sẽ tự lọc.

### 8.2. Rollback window

Trong blue-green, Blue nên được giữ nguyên trạng thái có thể khởi động lại/nhận traffic trong một khoảng rollback window sau cutover. Nếu Green có lỗi, gateway có thể chuyển traffic về Blue nhanh hơn so với việc build và deploy lại phiên bản cũ.

Rollback chỉ an toàn nếu Green chưa tạo thay đổi dữ liệu không tương thích với Blue. Vì vậy, database migration, event schema và API contract cần hỗ trợ cả hai phiên bản trong thời gian chồng lấn.

## 9. Tương thích dữ liệu trong thời gian hai phiên bản cùng chạy

Discovery overlap chỉ giải quyết việc định tuyến. Nó không bảo đảm phiên bản cũ và mới hiểu dữ liệu giống nhau.

Áp dụng chiến lược expand-contract cho database:

1. **Expand:** thêm cột/bảng/index mới theo cách phiên bản cũ vẫn chạy được.
2. **Deploy compatible code:** triển khai phiên bản mới có thể đọc/ghi tương thích với schema cũ và mới.
3. **Migrate:** backfill hoặc chuyển dữ liệu theo từng bước, theo dõi sai lệch.
4. **Switch:** chuyển traffic hoàn toàn sang phiên bản mới.
5. **Contract:** chỉ xóa cột/field cũ sau khi không còn instance hoặc consumer nào cần chúng.

Với message broker, bảo đảm consumer cũ đọc được message mới hoặc producer mới vẫn phát schema tương thích. Với REST/gRPC, thêm field tùy chọn trước, ngừng dùng field cũ sau và tránh đổi ý nghĩa field trong lúc hai phiên bản cùng tồn tại.

## 10. Graceful shutdown và connection draining

Rút instance khỏi registry không đồng nghĩa mọi request đang chạy đã kết thúc. Consumer có thể đang giữ connection pool, HTTP keep-alive, WebSocket hoặc request dài. Ứng dụng cần một giai đoạn drain trước khi process dừng.

Spring Boot hỗ trợ graceful shutdown cho embedded web server. Có thể cấu hình tường minh:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
```

Trong giai đoạn shutdown, embedded server ngừng nhận request mới theo cách phù hợp với server và cho request đang chạy một khoảng thời gian hoàn tất. `timeout-per-shutdown-phase` giới hạn thời gian chờ cho lifecycle phase; khi hết thời gian, shutdown tiếp tục.

Với Kubernetes, `preStop` hook chạy trước khi container nhận SIGTERM, và thời gian chạy hook được tính trong `terminationGracePeriodSeconds`. EndpointSlice đánh dấu endpoint đang terminating; `ready` chuyển `false`, còn `serving` có thể vẫn là `true` trong lúc endpoint đang drain. Không giả định load balancer bên ngoài cập nhật tức thì; cần kiểm thử thời gian truyền thay đổi.

Ví dụ rút gọn:

```yaml
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: inventory-service
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
```

`sleep 5` chỉ là ví dụ chờ propagation của endpoint/routing trong một môi trường đã đo được. Nó không tự deregister khỏi Eureka/Consul và không phải giải pháp đúng cho mọi cluster. Thời gian grace phải đủ cho preStop, graceful shutdown của Spring Boot, request dài nhất và cleanup:

\[
T_{terminationGrace} \ge T_{preStop} + T_{SpringGracefulShutdown} + T_{cleanup} + T_{margin}
\]

Không để `terminationGracePeriodSeconds` ngắn hơn tổng thời gian ứng dụng cần; nếu quá hạn, Kubernetes có thể gửi SIGKILL và cắt request còn lại.

Đối với message consumer, cần ngừng nhận message mới trước, hoàn tất hoặc trả lại message đang xử lý, commit/ack đúng thời điểm rồi mới đóng connection. Đối với scheduler/leader election, bảo đảm chỉ một phiên bản thực hiện tác vụ không idempotent nếu Blue và Green cùng chạy.

## 11. Trình tự rút một instance cũ an toàn

Quy trình tổng quát khi chủ động retire một instance:

1. Đưa readiness về không sẵn sàng để endpoint routing của nền tảng ngừng gửi request mới.
2. Đưa instance ra khỏi discovery: Eureka `OUT_OF_SERVICE`/pause hoặc Consul health check không passing/deregister theo chiến lược.
3. Chờ consumer và LoadBalancer cập nhật; xác nhận instance không còn được chọn cho request mới.
4. Ngừng nhận công việc nền và message mới.
5. Drain request, connection và session đang hoạt động.
6. Gửi SIGTERM hoặc đóng Spring ApplicationContext.
7. Để Spring Boot graceful shutdown hoàn tất trong timeout đã cấu hình.
8. Xác nhận registry không còn record active và process đã kết thúc.

Thứ tự chính xác giữa readiness, registry status và preStop phụ thuộc nền tảng. Nếu registry check đọc Actuator readiness, có thể để readiness đổi trạng thái kích hoạt check; nếu dùng Eureka pause hoặc Consul deregistration chủ động, hãy thực hiện trước khi process đóng. Cần kiểm thử hành vi thực tế của lifecycle integration trong ứng dụng.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Rollout hoàn tất nhưng request vẫn tới instance cũ | Consumer registry cache hoặc LoadBalancer cache chưa cập nhật | Đo propagation; giữ process cũ sống trong khoảng removal + drain |
| Pod mới Ready nhưng Eureka chưa có instance | Kubernetes readiness không tự cập nhật Eureka; Eureka registration/health integration chậm | Kiểm tra Eureka registration, `healthcheck.enabled` và trạng thái `UP` |
| Consul hiển thị instance cũ critical nhưng consumer vẫn chọn | Consumer không bật `query-passing` hoặc không lọc health state | Bật `spring.cloud.consul.discovery.query-passing=true` nếu chỉ muốn instance passing |
| Cả Blue và Green đều nhận traffic | Cùng đăng ký một service ID và consumer không lọc version | Dùng service ID riêng hoặc routing rule có kiểm soát |
| Request đang chạy bị reset khi Pod dừng | Grace period ngắn, chưa drain hoặc SIGKILL xảy ra | Tăng grace period phù hợp, bật graceful shutdown và đo request dài nhất |
| Không có instance trong lúc rollout | `maxUnavailable` quá cao, new instance chưa ready hoặc old instance bị rút quá sớm | Dùng surge capacity, readiness đúng và giữ overlap đủ lâu |
| Rollback không chạy được | Schema/data đã thay đổi không tương thích phiên bản cũ | Dùng expand-contract và giữ compatibility trong rollback window |
| Consul record critical tồn tại lâu | Critical check không tự deregister ngay | Cấu hình critical timeout phù hợp hoặc deregister chủ động khi shutdown |
| Job nền chạy hai lần trong overlap | Blue và Green cùng chạy scheduler/consumer không có coordination | Dùng leader election, distributed lock hoặc tắt job ở một nhóm |

## 13. Theo dõi rollout và xác định thời điểm kết thúc overlap

Theo dõi các chỉ số:

- Số instance theo version, service ID, trạng thái readiness và trạng thái registry.
- Thời điểm instance mới đăng ký, chuyển `UP`/passing và xuất hiện trong consumer.
- Số request theo version và tỷ lệ lỗi theo instance.
- Request đang chạy, connection mở, WebSocket/session và message chưa ack trên instance cũ.
- p95/p99 latency, timeout, retry, 5xx và saturation CPU/RAM.
- Thời gian từ khi retire tới khi không còn consumer chọn instance cũ.

Chỉ kết thúc overlap khi:

1. Instance mới đã được các consumer cần thiết nhìn thấy.
2. Smoke test và business checks đạt.
3. Traffic mới đã chuyển khỏi nhóm cũ.
4. Request/connection/message trên nhóm cũ đã drain hoặc được xử lý theo chính sách.
5. Rollback window đã kết thúc và schema/data tương thích cho phép loại phiên bản cũ.

Không dùng riêng trạng thái `Deployment Available` hoặc số lượng instance trong dashboard registry làm tiêu chí duy nhất.

## 14. Thực hành rolling update và blue-green

### 14.1. Rolling update

1. Chạy ba replica `inventory-service:v1` và xác nhận consumer gọi được cả ba.
2. Deploy `v2` với `maxSurge: 1`, `maxUnavailable: 0`.
3. Quan sát Pod mới khởi động và readiness chuyển true.
4. Xác nhận registry nhận instance `v2` và consumer thấy instance mới.
5. Tạo tải request trong lúc rollout để xác nhận `v1` và `v2` cùng xử lý được.
6. Quan sát từng instance `v1` chuyển out-of-service/critical/deregister, sau đó drain.
7. Xác nhận không có request mới tới instance cũ sau khi đã loại khỏi routing.
8. Kiểm tra rollout hoàn tất và không có lỗi tăng bất thường.

### 14.2. Blue-green

1. Giữ `payment-blue` tiếp tục nhận traffic.
2. Triển khai `payment-green` với service ID riêng và cùng hợp đồng API.
3. Gọi smoke test trực tiếp vào Green.
4. Chuyển một tỷ lệ nhỏ traffic qua Green nếu gateway hỗ trợ weighted routing.
5. Theo dõi lỗi/latency/business metrics và tăng dần tỷ lệ.
6. Chuyển hoàn toàn traffic sang Green.
7. Giữ Blue trong rollback window; nếu có lỗi, chuyển route về Blue.
8. Sau khi xác nhận an toàn, drain và deregister Blue.

Trong cả hai bài thực hành, thử thêm một request dài và một message đang xử lý để xác minh graceful shutdown thực sự chờ công việc hoàn tất.

## 15. Checklist triển khai

- [ ] Đã chọn rolling update hoặc blue-green theo khả năng routing và rollback.
- [ ] Có capacity cho `maxSurge` và mức `maxUnavailable` đã chọn.
- [ ] Readiness phản ánh khả năng nhận traffic; liveness chỉ phản ánh khả năng sống của process.
- [ ] Đã xác minh readiness được phản ánh vào đúng hệ thống routing và registry.
- [ ] Instance mới đã `UP`/passing và consumer nhìn thấy trước khi rút instance cũ.
- [ ] Đã đo propagation của Eureka/Consul, consumer cache và LoadBalancer.
- [ ] Nếu dùng Consul, consumer đã lọc passing checks khi yêu cầu chỉ instance khỏe.
- [ ] Nếu dùng Eureka, đã hiểu pause/resume, `OUT_OF_SERVICE`, cancel và lease expiry.
- [ ] Blue và Green có service ID/routing rule để tránh nhận traffic ngoài ý muốn.
- [ ] API, database schema và message format tương thích trong thời gian overlap.
- [ ] Instance cũ ngừng nhận request mới trước khi drain.
- [ ] `terminationGracePeriodSeconds` đủ cho preStop, graceful shutdown và cleanup.
- [ ] Đã xử lý request dài, WebSocket, message consumer và scheduler/leader election.
- [ ] Có rollback window và tiêu chí kết thúc overlap rõ ràng.
- [ ] Đã thử rollback trong staging, không chỉ thử deploy tiến lên.

## Tài liệu tham khảo

- [Kubernetes — Update a Deployment Without Downtime](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/)
- [Kubernetes — Deployment RollingUpdate, maxSurge và maxUnavailable](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes — Pod Termination Lifecycle và preStop](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — EndpointSlices: ready, serving và terminating](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Cloud Netflix — Eureka Health Checks, Pause/Resume và Registration](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul — Service Discovery và HTTP Health Check](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
