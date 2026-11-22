# Quan sát phân phối tải mà không suy diễn từ vài yêu cầu

Một ứng dụng `order-service` gọi `inventory-service` bằng RestClient, WebClient hoặc OpenFeign thông qua Spring Cloud LoadBalancer. Các request được phân phối tới các `ServiceInstance` của inventory; khi quan sát vài response liên tiếp, ta có thể thấy một instance nhận nhiều request hơn instance khác. **Điều đó chưa đủ để kết luận thuật toán cân bằng tải bị lỗi.**

Cùng một kết quả “7 lần vào instance A, 3 lần vào B” có thể xuất hiện do chọn Random hoàn toàn bình thường, do Round Robin của nhiều caller độc lập, do retry, do một instance không thuộc danh sách ứng viên ở một số thời điểm, hoặc do thu thập mẫu thiếu request thất bại.

Bài thuộc chương **Quan sát hệ thống** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` hướng dẫn quan sát đúng các tầng:

- **Service discovery và lựa chọn instance:** mỗi lần chọn có bao nhiêu ứng viên, lọc theo health, zone, hint, weight, sticky session hay chính sách khác?
- **HTTP client:** một request logic của RestClient/WebClient/OpenFeign tạo bao nhiêu HTTP attempts và chúng kết thúc như thế nào?
- **Backend:** replica nào thực sự nhận và hoàn thành request, mất bao lâu, status nào?
- **Thống kê:** với cỡ mẫu N và thuật toán dự kiến, độ lệch quan sát có còn phù hợp với biến động ngẫu nhiên không?
- **Vận hành:** phân phối request count, active requests, độ trễ, tỷ lệ lỗi và CPU/concurrency có thể rất khác nhau.

Mục tiêu là đo **đúng đại lượng, đúng cửa sổ thời gian, đúng quần thể và đúng giả thuyết** trước khi đổi thuật toán, tăng retry hoặc kết luận một replica bị bỏ quên.

## 1. Câu hỏi đầu tiên: “Cân bằng” nghĩa là gì?

Một hệ thống có thể cân bằng theo nhiều mục tiêu khác nhau:

| Mục tiêu | Đại lượng cần đo | Hiểu lầm hay gặp |
|---|---|---|
| Cân bằng **lượt chọn** | Số lần LoadBalancer chọn từng `ServiceInstance` | Tưởng mỗi lần chọn luôn tạo HTTP request thành công |
| Cân bằng **attempts** | Số HTTP requests thực gửi tới từng instance | Quên retry hoặc fail trước network I/O |
| Cân bằng **requests thành công** | Số response thỏa điều kiện success đã định nghĩa | Quên các request lỗi/timed out |
| Cân bằng **active requests** | Số lời gọi đang xử lý cùng lúc trên mỗi instance | Nhầm với số requests trong một phút |
| Cân bằng **thời gian xử lý** | Tổng thời gian phục vụ hoặc latency distribution | Hai instance cùng count nhưng chi phí khác nhau |
| Cân bằng **tài nguyên** | CPU, memory, threads, connection pools, queue depth | Tưởng Round Robin tự đo CPU |
| Cân bằng **trải nghiệm** | End-to-end p95/p99, error rate, deadline miss | Chỉ nhìn tỷ lệ A/B |
| Cân bằng **theo policy** | Phân phối đúng zone/weight/hint/tenant/affinity | Mặc định mọi instance phải nhận bằng nhau |

**Spring Cloud LoadBalancer chọn instance; nó không cam kết phân phối CPU, latency hay response thành công đều nhau.** Thuật toán Round Robin hoặc Random mặc định vận hành trên **tập ứng viên được cung cấp**, không phải trên mọi instance mà dashboard tưởng đang tồn tại.

Một số câu hỏi có vẻ giống nhau nhưng cần đo khác nhau:

- “Có phải A được chọn 50% lần?” → đếm selections của caller trong một quần thể ứng viên ổn định.
- “Có phải A nhận 50% lượt HTTP?” → đếm HTTP attempts ở backend, tính cả retry và các caller khác.
- “Có phải A đang quá tải?” → xem active/concurrency, CPU, queues, service time và error rate.
- “Có phải LoadBalancer bỏ B?” → kiểm tra instance list và selection metrics, không chỉ response bodies.
- “Người dùng có bị chậm?” → đo end-to-end latency, status và retries.

## 2. Một lời gọi logic có thể tạo nhiều sự kiện khác nhau

~~~mermaid
flowchart LR
    U["Business operation"] --> C["HTTP client"]
    C --> L["LoadBalancer choose"]
    D["Discovery + suppliers"] --> L
    L --> I["Inventory instance"]
    I --> R["HTTP response / error"]
    R --> C
~~~

Khi retry bật, sơ đồ thực tế có thể là:

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant LB as LoadBalancer
    participant A as inventory A
    participant B as inventory B

    O->>LB: 1 logical GET /stock
    LB-->>O: select A
    O->>A: HTTP attempt #1
    A--xO: Connection reset
    Note over O: Retry only if configured
    O->>LB: select again
    LB-->>O: select B
    O->>B: HTTP attempt #2
    B-->>O: 200 OK
    O-->>O: 1 completed logical call
~~~

Ở ví dụ này:

| Loại đếm | Giá trị |
|---|---:|
| Business logical calls | 1 |
| LoadBalancer selections | 2 |
| HTTP attempts đến backend | Có thể là 1 hoặc 2 tùy lỗi xảy ra trước/sau khi request được gửi |
| Completed logical responses | 1 |
| Successful HTTP backend responses | 1 |
| Failed HTTP/network attempts | Ít nhất 1 lỗi ở caller, không chắc backend đã nhận |

Một lỗi kết nối TCP có thể xảy ra **trước** khi backend nhận request. Một read timeout có thể xảy ra **sau** khi backend đã xử lý thành công nhưng response chưa đến caller. Vì vậy, đếm từ caller và backend không nhất thiết giống nhau.

### Các mẫu số không được tráo đổi

Gọi:

- `N_selection`: tổng số lần lựa chọn một ServiceInstance.
- `N_sent`: tổng số attempts được transport gửi thực tế.
- `N_received`: tổng số attempts backend nhận.
- `N_success`: số attempts thành công theo định nghĩa nghiệp vụ.
- `N_logical`: tổng số lời gọi của business code.

Nếu dashboard thể hiện `N_success(A) / sum(N_success)` thì đó là **tỷ trọng requests thành công**, không đương nhiên là tỷ lệ thuật toán chọn A. Một instance lỗi có thể nhận nhiều attempts nhưng ít thành công nên gần như “biến mất” khỏi chart success.

## 3. Vì sao vài request đầu không đủ để kết luận?

Giả sử LoadBalancer chọn ngẫu nhiên đồng đều giữa hai instance A/B. Ở mỗi lần chọn, lý thuyết là:

\[
P(A)=P(B)=0.5
\]

Điều này **không có nghĩa** cứ hai request phải có một vào A và một vào B. Các chuỗi sau đều hợp lệ:

~~~text
A, B, B, A, A, B
A, A, A, B, A, A
B, B, B, B, B, A
~~~

Việc cùng instance được chọn nhiều lần liên tiếp là đặc điểm bình thường của Random. Nếu chỉ gửi 10 request mà thấy A nhận 7, B nhận 3, ta chưa có bằng chứng đáng tin về lệch thuật toán.

Với Round Robin trong **một caller, danh sách ứng viên cố định và không có retry**, các lần chọn có xu hướng luân phiên; tuy nhiên, thứ tự **response hoàn thành** có thể khác thứ tự lựa chọn do network latency và concurrency.

### Thí nghiệm phải bắt đầu bằng giả thuyết cụ thể

Ví dụ giả thuyết `H0`:

> Trong thời gian đo, một caller duy nhất dùng thuật toán Random không trọng số, chọn độc lập từ đúng ba instance luôn đủ điều kiện; xác suất chọn mỗi instance là 1/3.

Nếu giả thuyết này không đúng vì health filtering, zone, weights hoặc số instances thay đổi, so sánh với 1/3 sẽ sai ngay từ điểm xuất phát.

Đừng tự gán “mọi replica đều có 33,3% traffic” là tiêu chuẩn chung cho một hệ thống có zone preference, tenant affinity, weighted routing hoặc các caller ở những vùng khác nhau.

## 4. Biến động thống kê với Random

Nếu có `N` lần chọn độc lập, xác suất chọn instance i là `p_i`, số lần chọn `X_i` có phân phối nhị thức theo biên:

\[
X_i \sim \operatorname{Binomial}(N,p_i)
\]

Kỳ vọng và độ lệch chuẩn:

\[
E[X_i]=Np_i,\qquad
\sigma_i=\sqrt{Np_i(1-p_i)}.
\]

Tỷ lệ quan sát `\hat p_i = X_i/N` có sai số chuẩn:

\[
SE(\hat p_i)=\sqrt{\frac{p_i(1-p_i)}{N}}.
\]

Ví dụ hai instance, `p_A=0.5`:

| Số lần chọn `N` | Số A kỳ vọng | Độ lệch chuẩn của count | Xấp xỉ 95% cho tỷ lệ A |
|---:|---:|---:|---:|
| 10 | 5 | 1,58 | Xấp xỉ chuẩn **không đáng tin** vì mẫu quá nhỏ |
| 100 | 50 | 5,00 | Khoảng 40,2%–59,8% |
| 1.000 | 500 | 15,81 | Khoảng 46,9%–53,1% |
| 10.000 | 5.000 | 50,00 | Khoảng 49,0%–51,0% |

Các khoảng cho `N >= 100` là **xấp xỉ** bằng `p±1.96×SE`, **không phải SLO hoặc ranh giới đảm bảo** của LoadBalancer. Chúng giả định lựa chọn độc lập, tập ứng viên và `p` cố định, không có sticky routing/retry-affinity hay bias khác.

Với ba replica đồng đều, `N=900`, mỗi replica kỳ vọng 300 lượt chọn. Độ lệch chuẩn:

\[
\sigma=\sqrt{900\times\frac13\times\frac23}
=\sqrt{200}\approx14.14.
\]

Một mẫu minh họa có thể là:

~~~text
A: 287   (31,9%)
B: 305   (33,9%)
C: 308   (34,2%)
Tổng: 900
~~~

Đây là **số minh họa**, không phải kết quả đo thật. Những con số này không phải 300/300/300 nhưng vẫn có thể rất phù hợp với một thuật toán Random đúng. “Không đều tuyệt đối” không đồng nghĩa “không đúng Random”.

## 5. Tại sao Round Robin cũng không bảo đảm response xen kẽ?

Round Robin chọn vị trí tiếp theo trong **danh sách instance mà nó nhận được tại thời điểm lựa chọn**. Với một instance list cố định [A,B,C], một caller duy nhất, không retry và các lần chọn tuyến tính, chuỗi lựa chọn có thể là:

~~~text
choose #1 -> A
choose #2 -> B
choose #3 -> C
choose #4 -> A
choose #5 -> B
choose #6 -> C
~~~

Nhưng nếu A xử lý 500 ms, B 30 ms, C 100 ms, các response có thể **về không theo thứ tự choose**:

~~~text
choose:    A, B, C, A, B, C
complete:  B, C, B, C, A, A
~~~

Vì vậy:

- Không dùng **thứ tự body response** để chứng minh thứ tự chọn.
- Khi nhiều caller replicas cùng có LoadBalancer context riêng, không kỳ vọng mọi instance trên toàn hệ thống chia sẻ **một bộ đếm Round Robin toàn cục**.
- Khi danh sách ứng viên thay đổi độ dài/thứ tự giữa những lần chọn, thứ tự nhận instance cũng thay đổi.
- Khi có retry, một logical request có thể đóng góp hơn một lần chọn.
- Nếu một request stream kéo dài lâu, count theo lượt vẫn cân bằng nhưng active requests có thể lệch rất lớn.
- Với cơ chế same-instance preference/sticky session, Round Robin có thể không là chính sách hiệu lực cuối cùng.

Hãy kiểm tra **lần chọn** thay vì chỉ quan sát **thứ tự hoàn thành**, đặc biệt với WebClient và xử lý bất đồng bộ.

## 6. Tập ứng viên biến đổi mới là mẫu số thực tế

Spring Cloud LoadBalancer không nhất thiết lựa chọn giữa **tất cả instance có trong registry**. Các lớp `ServiceInstanceListSupplier` có thể đưa ra một tập ứng viên đã được xử lý:

~~~mermaid
flowchart LR
    R["DiscoveryClient"] --> C["Cache / supplier"]
    C --> H["Health check filter"]
    H --> Z["Zone / hint / request filtering"]
    Z --> S["Eligible ServiceInstances"]
    S --> A["RoundRobin / Random / policy khác"]
    A --> I["Instance được chọn"]
~~~

Đây là luồng khái niệm. **Thứ tự supplier thực tế phụ thuộc cấu hình**, không phải một pipeline duy nhất áp dụng cho mọi project.

Ví dụ:

| Thời gian | Ứng viên đủ điều kiện | Xác suất Random không trọng số |
|---|---|---|
| 10:00–10:05 | A, B, C | Mỗi instance 1/3 |
| 10:05–10:10 | A, C (B unhealthy) | A/C mỗi instance 1/2, B = 0 |
| 10:10–10:15 | A, B, C | Mỗi instance 1/3 |

Nếu gộp thành một biểu đồ 15 phút mà không hiển thị thay đổi danh sách ứng viên, B có vẻ “nhận ít traffic bất thường”. Nhưng đó có thể là kết quả **đúng** của health filtering.

Với zone preference, ví dụ caller `zone=az-1` có thể ưu tiên A/B trong cùng zone thay vì C ở zone khác; phải so sánh lựa chọn với **policy zone**. Với weighted routing, mục tiêu không phải 1/3 mà có thể là tỷ lệ 1:2:3 trong từng thời đoạn phù hợp.

**Đừng xây ngưỡng cảnh báo 33,3% cho mọi service ID** mà không biết liệu policy có đặt trọng số, zone, hint hoặc sticky session.

## 7. Các nguồn gây lệch phân phối cần nhận diện

| Nguồn | Hiện tượng nhìn thấy | Bằng chứng nên thu thập |
|---|---|---|
| Discovery stale | Instance mới ít được chọn hoặc instance cũ còn xuất hiện | Registry events, danh sách supplier thực tế, thời điểm refresh |
| Cache TTL | Danh sách ứng viên cập nhật trễ | Cache settings, TTL, snapshot list theo thời gian |
| Health check | Instance bị loại khi health fail | Health check results, danh sách healthy, thời điểm phục hồi |
| Zone preference | Một số replica được ưu tiên theo caller zone | Caller zone, instance metadata zone |
| Hint routing | Requests có hint khác đi tập instance khác | Hint value đã chuẩn hóa, supplier candidates |
| Weighted selection | Replica có trọng số cao nhận nhiều lượt hơn | Weights và phân phối kỳ vọng theo thời đoạn |
| Sticky session / same instance preference | Một client lặp lại trên cùng instance | Cookie/session/affinity policy, client cohorts |
| Retry aware supplier | Attempt sau tránh instance cũ | Retry count, prior instance, current selection |
| Nhiều caller replicas | Mỗi caller có trạng thái chọn riêng | Caller ID, request ID, release version |
| Horizontal autoscaling | Mẫu số đổi theo thời gian | Instance lifecycle, start/stop times |
| Canary release | Version canary nhận ít traffic có chủ đích | Routing policy, version labels |
| Circuit breaker | Một số logical calls bị chặn trước LoadBalancer | Not-permitted calls, breaker state |
| Gateway/LB tầng khác | Backend thấy lượng request không trùng client-side selection | Trace path và metrics ở từng tầng |
| Pool/transport errors | Selection có nhưng backend không nhận | Client transport errors, TCP, server access logs |

Để phân tích, hãy **phân tầng (stratify)** theo thời gian, caller và policy trước khi cộng dữ liệu. Một bảng 24 giờ tổng hợp có thể che những đợt suy giảm kéo dài 5 phút hoặc ngược lại gán sai sự mất cân bằng cho thuật toán.

## 8. Chọn thời gian và cỡ mẫu có chủ đích

Một kế hoạch đo đáng tin cần ghi rõ:

1. **Giả thuyết:** Random không trọng số hay Round Robin hay routing có chủ đích?
2. **Quần thể:** tất cả attempts từ mọi caller, hay một caller cụ thể, chỉ một route, chỉ cùng zone?
3. **Mẫu số:** selections, attempts gửi, attempts nhận, successes hay logical calls?
4. **Cửa sổ:** 1 phút, 15 phút, 1 giờ; có chứa scale events/deploy không?
5. **Cỡ mẫu:** bao nhiêu selections hợp lệ trong từng cửa sổ và từng cohort?
6. **Tiêu chí:** deviation ±? có xem thống kê hay ngưỡng vận hành?
7. **Thời gian warm-up:** LoadBalancer context init, JVM JIT, connection pool, discovery cache warm-up có làm bias?
8. **Mức concurrency:** sequential, 20 concurrent, 500 concurrent; có retry không?
9. **Trạng thái service:** tất cả instance healthy, không có zone/hint khác biệt?
10. **Khả năng thu thập:** có metric cho failures, 503/no-instance và canceled requests không?

Ví dụ ba replica mỗi instance kỳ vọng ~300 selections sau 900 lượt. Một biểu đồ 10 giây chỉ có bảy request không đủ tính toán độ lệch dài hạn. Nên báo dashboard **cả tỷ lệ lẫn sample count**; khi `N` quá nhỏ, hiển thị “mẫu ít/chưa kết luận” thay vì tô đỏ ngay.

### Ước lượng sample size cho Random

Muốn sai số xấp xỉ không quá ±5 điểm phần trăm ở độ tin cậy xấp xỉ 95% với `p=0.5` (trường hợp phương sai lớn nhất):

\[
N \approx \frac{1.96^2\cdot 0.5(1-0.5)}{0.05^2}
\approx 384.
\]

Đây là **cỡ mẫu lý thuyết cho ước lượng tỷ lệ trong mô hình Bernoulli độc lập**, không phải hướng dẫn “cứ 384 requests là test chắc chắn đúng”. Nếu lựa chọn có tương quan, policy thay đổi hoặc sample phân tầng không đúng, hiệu lực thống kê thấp hơn.

Ở khoảng tin cậy, sai số kỳ vọng giảm xấp xỉ theo `1/\sqrt N`. Muốn giảm một nửa sai số, cần khoảng **gấp bốn lần** số lượt chọn, nếu các giả định giữ nguyên.

## 9. Không suy luận nhân quả từ một biểu đồ phần trăm

Giả sử dashboard ghi:

~~~text
A: 65% completed requests
B: 25% completed requests
C: 10% completed requests
~~~

Dữ liệu này **chưa trả lời**:

- A có được LoadBalancer chọn 65% hay chỉ hoàn thành nhiều hơn?
- B/C có timeout nhiều làm thiếu dữ liệu completed?
- C có ở trạng thái unhealthy/zone khác trong nửa thời gian?
- Traffic là từ một caller hay nhiều caller có policy khác nhau?
- N = 20 hay N = 2.000.000?
- C có nhận ít request **theo chủ đích** vì canary weight?
- Thời gian nào từng replica sẵn sàng nhận traffic?
- Có reverse proxy, Service Mesh hoặc Kubernetes Service phía sau chuyển request thêm lần nữa?

Hãy phân biệt ba loại phát biểu:

- **Quan sát:** “Trong 10 phút, backend C nhận 8% successful responses của tuyến GET /stock.”
- **Giả thuyết:** “Có thể C bị health check lọc hoặc mang weight nhỏ.”
- **Kết luận:** “Danh sách eligible instances trong thời gian đó chỉ chứa C cho 8% lựa chọn theo policy, đã được đối chiếu với trace và supplier logs.”

Một dashboard tỷ lệ đơn lẻ là **tín hiệu điều tra**, không tự động là bằng chứng về nguyên nhân.


## 10. MicrometerStatsLoadBalancerLifecycle: nguồn dữ liệu ở caller

Spring Cloud LoadBalancer cung cấp `MicrometerStatsLoadBalancerLifecycle`, một `LoadBalancerLifecycle` thu thập thống kê các lời gọi được load balance. Để kích hoạt, cần có `MeterRegistry` và bật:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

Theo tài liệu Spring Cloud Commons, các meter được cung cấp gồm:

| Meter | Loại | Đo cái gì? |
|---|---|---|
| `loadbalancer.requests.active` | Gauge | Số lời gọi LoadBalancer đang active, có thể có thông tin instance trong tags |
| `loadbalancer.requests.success` | Timer | Thời lượng lời gọi load-balanced kết thúc bằng việc trả một response cho HTTP client phía dưới |
| `loadbalancer.requests.failed` | Timer | Thời lượng lời gọi load-balanced kết thúc với exception |
| `loadbalancer.requests.discard` | Counter | Các lời gọi bị discard vì LoadBalancer không lấy được `ServiceInstance` |

**Điểm phải hiểu đúng:** `loadbalancer.requests.success` **không phải mặc nhiên là số HTTP 2xx hoặc số business transactions thành công**. Theo định nghĩa lifecycle metric, “success” ở đây nói về cách một lời gọi kết thúc bằng việc đưa response cho tầng client, không bảo đảm response status là 200. Một response HTTP 500 vẫn có thể thuộc nhánh kết quả có response, tùy integration và lớp xử lý. Muốn biết 5xx, cần đo HTTP status phía caller/server ở lớp thích hợp.

Tương tự, `loadbalancer.requests.discard` không đại diện cho toàn bộ request thất bại, mà là một trường hợp cụ thể: **không lấy được instance đích**.

Các metrics có thêm tags về service instance, request hoặc response **khi dữ liệu có sẵn**. Một số blocking integrations không cung cấp đầy đủ request/response metadata, nên **đừng giả định mọi tag luôn tồn tại**. Timer `count` là số lần ghi nhận timer theo tags, không tự động bằng logical requests trong domain.

### Dependency và cấu hình demo

Trong ứng dụng Spring Boot có HTTP client với LoadBalancer, thêm Actuator để cung cấp registry/endpoint theo cấu hình:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Các dependency này **bổ sung** cho `spring-boot-starter-web` hoặc `spring-boot-starter-webflux` và HTTP client đang dùng. Nếu xuất Prometheus, thêm Micrometer Prometheus registry phù hợp với Spring Boot BOM:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Ví dụ `application.yml` dành cho môi trường kiểm thử nội bộ:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
~~~

`include-path: false` giúp tránh đưa path động chứa SKU/order IDs vào tag `uri` trong LoadBalancer metrics. Spring Cloud Commons lưu ý `RestTemplate`-backed load balancing có thể thiếu URI template và dùng raw path khi tạo tag; điều này gây **high cardinality** nếu path chứa ID không giới hạn. Với `RestClient` và `WebClient`, khi có URI template Spring Cloud có thể dùng template làm tag, nhưng vẫn cần kiểm tra registry thực tế.

**Không mở Actuator metrics/prometheus public trên Internet.** Quản lý network access, authentication, scrape permission và chính sách tiết lộ thông tin instance. Mọi example endpoint dưới đây giả định đang dùng môi trường local hoặc management network đáng tin cậy.

## 11. Kiểm tra số liệu từ /actuator/metrics

Sau khi khởi động caller và có một số request đi qua LoadBalancer, thử:

~~~powershell
Invoke-RestMethod "http://localhost:8080/actuator/metrics"

Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.success"

Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.failed"

Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.discard"
~~~

Các meter thường chỉ xuất hiện **sau khi có ít nhất một observation được ghi**. Nếu endpoint trả 404 cho một tên meter, điều đó không nhất thiết là LoadBalancer không hoạt động. Có thể là:

- Chưa có request tương ứng, nên meter chưa được đăng ký.
- Thiếu Actuator/MeterRegistry hoặc property `stats.micrometer.enabled` chưa bật.
- Đang gọi **management endpoint của backend** thay vì **caller** có LoadBalancer.
- Client không đi qua LoadBalancer, vì URL đích là IP/URL tĩnh.
- Metrics endpoint bị hạn chế exposure hoặc bảo mật.
- Tên meter/labels thay đổi theo release train và exporter.

Endpoint `/actuator/metrics/{meter}` có thể trả `measurements` và `availableTags`. Trước khi tạo dashboard, **đọc các availableTags thực tế** và xác minh chúng có định danh service ID/instance để so sánh hay không. Không đoán tên tag như `instanceId`, `serviceId` hoặc `status` rồi tạo truy vấn luôn trả số 0.

### Timer, counter, gauge phải được đọc khác nhau

- **Timer:** có `COUNT` và `TOTAL_TIME` trong Actuator; `COUNT` là số sự kiện, còn tổng thời gian chia count là latency trung bình theo cách đo meter. Trung bình không thay thế p95/p99.
- **Counter:** chỉ tăng; khi tính traffic mỗi phút dùng `increase()`/`rate()` trong hệ time-series, xử lý process restart/reset.
- **Gauge:** giá trị tại thời điểm scrape; `active=0` không có nghĩa cả phút vừa qua không nhận request.
- **Histogram/timer distribution:** phải bật/configure phù hợp nếu muốn p95/p99 đáng tin; không suy p99 từ trung bình.

Prometheus thường chuyển tên meter/units sang định dạng riêng, ví dụ timer có các series `*_seconds_count` và `*_seconds_sum`. **Kiểm tra tên series tại `/actuator/prometheus` hoặc registry thực tế** trước khi viết PromQL; không sao chép một metric name rồi mặc định hợp lệ ở mọi phiên bản.

## 12. Kết hợp client-side LoadBalancer metrics với backend metrics

Để hiểu phân phối tải, không chỉ đo caller.

~~~mermaid
flowchart LR
    O["Caller: LB lifecycle metrics"] --> LB["Select ServiceInstance"]
    LB --> A["Backend A: HTTP server metrics"]
    LB --> B["Backend B: HTTP server metrics"]
    LB --> C["Backend C: HTTP server metrics"]
    A --> M["Dashboard / tracing"]
    B --> M
    C --> M
    O --> M
~~~

Một bảng quan sát nên có các nhóm:

| Tầng | Metrics hoặc log cần thu | Phân biệt được |
|---|---|---|
| Caller business | Tổng logical calls, route/operation, errors | User-facing demand |
| LoadBalancer lifecycle | Success/failed/discard, active, tags instance khi có | Request selection/execution ở LB integration |
| HTTP client | Attempts, response status, connect/read timeout, retry count | Thành công/lỗi transport |
| Inventory HTTP server | `http.server.requests`, response status, duration | Backend đã nhận và xử lý gì |
| Inventory application | Endpoint business success/failure | Kết quả nghiệp vụ |
| Host/JVM | CPU, heap, GC, thread pools, queue depth | Chi phí xử lý/tài nguyên |
| Distributed trace | Caller span, downstream span, correlation ID, attempts | Ghép đúng đường đi của request |

Đếm request từ backend có thể bao gồm **health probes** hoặc lưu lượng không đến từ order-service. Cần lọc theo endpoint, client source và môi trường, không gộp `/actuator/health` vào biểu đồ tải nghiệp vụ.

Ở môi trường Prometheus/Kubernetes, để phân biệt replica cần label ổn định từ **scrape target** (pod/instance) hoặc từ instrumentation có kiểm soát. Không biến mỗi request ID, user ID, session hay SKU thành label; điều này gây high cardinality và làm hỏng hiệu năng/chi phí hệ thống metrics.

### Có nên trả instanceId trong response?

Trong **lab hoặc môi trường chẩn đoán có kiểm soát**, backend có thể trả:

~~~json
{
  "instanceId": "inventory-b",
  "sku": "SKU-001"
}
~~~

Điều này giúp xác minh request đã đến backend nào. Nhưng không nên đưa metadata hạ tầng nhạy cảm vào mọi response production; ưu tiên server-side metrics/logs và trace context.

Ngay cả khi response body cho thấy B, bạn mới biết **B đã trả response**. Bạn chưa biết A có từng được chọn trong một attempt trước đó rồi fail hay không.

## 13. Phân phối request count không đồng nghĩa phân phối tải tài nguyên

Xét cùng 1.000 attempts trên A và B:

~~~text
A: 500 requests, service time trung bình 10 ms
B: 500 requests, service time trung bình 200 ms
~~~

Tổng service time tương ứng:

\[
W_A=500\times10\mathrm{ms}=5000\mathrm{ms}
\]

\[
W_B=500\times200\mathrm{ms}=100000\mathrm{ms}.
\]

Số request được phân đều nhưng B tích lũy **gấp 20 lần** thời gian xử lý. Nếu throughput cố định và thời gian phục vụ lâu hơn, số in-flight requests của B thường cao hơn.

Theo một cách diễn giải gần đúng của **Little's Law** trong trạng thái ổn định:

\[
L \approx \lambda W
\]

trong đó `L` là số công việc trung bình đang ở trong hệ thống, `\lambda` là throughput và `W` là thời gian trung bình trong hệ thống. Khi hai instance nhận cùng request rate nhưng B có latency lớn hơn, active requests trên B có thể cao hơn.

**Đừng chọn một thuật toán mới chỉ vì active gauge của B cao.** Có thể B chậm do GC, DB hotspot, CPU throttling, payload khác, connection pool, noisy neighbor hoặc version mismatch. Cần kiểm tra các biến đó trước.

### Count, rate và latency nên đứng cạnh nhau

Một dashboard vận hành tốt cho mỗi service ID có thể gồm:

1. Request/s từng replica (theo status class).
2. Active requests và connection pool utilization.
3. Error rate 4xx/5xx/exception/timeout.
4. Response latency p50, p95, p99.
5. CPU, memory, GC pause, thread/queue pressure.
6. Replicas eligible từ discovery/health theo thời gian.
7. Retry rate, discarded/no-instance count.
8. Version/zone/weight của mỗi replica.

Tỷ lệ request gần 33/33/34 nhưng một replica p99 cao hơn nhiều vẫn là một vấn đề cần điều tra; ngược lại, tỷ lệ 50/30/20 có thể hoàn toàn đúng nếu weights được cấu hình như vậy.

## 14. Phân phối quan sát theo ngày có thể che bất thường ngắn

Giả sử trong 15 phút mỗi instance nhận traffic rất khác ở các giai đoạn:

| Khoảng thời gian | A | B | C | Tình trạng |
|---|---:|---:|---:|---|
| 10:00–10:05 | 200 | 200 | 200 | Cả ba healthy |
| 10:05–10:10 | 300 | 0 | 300 | B bị loại do health |
| 10:10–10:15 | 200 | 200 | 200 | B phục hồi |
| **Tổng** | **700** | **400** | **700** | B có 22,2% tổng |

Nếu chỉ nhìn tổng 15 phút, B có vẻ nhận ít đáng kể. Nhưng một thước đo theo **thời gian đủ điều kiện** sẽ cho kết luận khác: B có 0 traffic khi bị filter là hợp lý; đây là sự kiện health/discovery, không nhất thiết là lỗi Random.

Để phân tích một giai đoạn autoscale, lưu:

- Thời điểm instance được đăng ký và bắt đầu healthy.
- Thời điểm LoadBalancer supplier nhìn thấy instance, không chỉ thời điểm Kubernetes pod trở thành ready.
- Zone, hint, weight, version label ở thời điểm đó.
- Số selection trong mỗi cửa sổ có tập eligible ổn định.
- Giai đoạn cache TTL và deployment rollout.

Khi vẽ tỷ lệ, hiển thị **N và số instance eligible** cùng thời gian, không chỉ ba đường phần trăm.

## 15. Dùng thống kê để đặt câu hỏi, không làm “máy phán đúng/sai”

Với Random có xác suất lý thuyết `p_i` và N selections, độ lệch có thể được đánh giá bằng **kiểm định goodness-of-fit**, ví dụ thống kê chi-square:

\[
\chi^2=\sum_{i=1}^{k}\frac{(O_i-E_i)^2}{E_i},
\qquad E_i=Np_i
\]

trong đó `O_i` là số lựa chọn đo được cho instance i, còn `E_i` là số kỳ vọng theo policy.

Ví dụ với N=900, ba instance đều 1/3, kỳ vọng 300 mỗi instance; dữ liệu minh họa `O = (287,305,308)`:

\[
\chi^2
=\frac{(287-300)^2}{300}
+\frac{(305-300)^2}{300}
+\frac{(308-300)^2}{300}
\approx0.86.
\]

Mức độ lệch này nhỏ so với thang đo chi-square thông thường với 2 bậc tự do; **không có cơ sở để coi nó là bằng chứng rõ của bias** trong mô hình đơn giản. Tuy vậy, kiểm định không chứng minh thuật toán hoàn hảo hay backend luôn cân bằng.

### Các giới hạn phải ghi rõ

- Các expected counts nên đủ lớn cho xấp xỉ chi-square; khi mẫu nhỏ dùng phương pháp exact/Monte Carlo phù hợp thay vì tự áp kiểm định.
- Selections **không độc lập** khi dùng Round Robin hoặc sticky/affinity: kiểm định chi-square cho lựa chọn Random IID không áp dụng nguyên trạng.
- Nếu `p_i` thay đổi theo thời gian, phải chia thành các giai đoạn có policy ổn định hoặc tính expected exposure hợp lý.
- Nếu lấy nhiều cửa sổ và nhiều services, sẽ có những kết quả vượt ngưỡng chỉ do kiểm định lặp lại; cần xét multiple comparisons.
- Cần phân biệt **mức độ lệch có ý nghĩa vận hành** với **ý nghĩa thống kê**. Sai số 1 điểm phần trăm có thể rõ ràng với N rất lớn nhưng không đáng đổi kiến trúc.
- Nếu phát hiện bias, thống kê chỉ chỉ ra “dữ liệu không phù hợp giả thuyết”; nó **không tự chứng minh nguyên nhân là code LoadBalancer**.

Đối với Round Robin trong một caller, có thể xác minh **sequence selection và cardinality của eligible list** trong điều kiện kiểm soát. Đối với Random, đánh giá phân phối trên mẫu đủ lớn và dùng xác suất, thay vì assert “mỗi ba request đúng một replica”.

## 16. Tracing và log để giải thích vì sao một replica được chọn

Metric tổng hợp hữu ích để phát hiện biến động, còn tracing giúp trả lời câu hỏi **tại sao một logical call tạo nhiều attempts hoặc chọn một instance cụ thể**.

Một trace có thể chứa:

~~~text
Trace: quote-request-123
  OrderService GET /quotes
    InventoryClient logical GET inventory-service/stock
      attempt #1 -> inventory-a -> connection reset
      retry backoff 100 ms
      attempt #2 -> inventory-b -> HTTP 200
    PricingClient GET pricing-service/price -> HTTP 200
~~~

Hệ thống tracing hiện đại như Micrometer Tracing/OpenTelemetry cung cấp span propagation; không tự tạo `traceparent` bằng UUID hoặc tự nhét dynamic user information vào span attributes.

Một số hướng chẩn đoán:

- Cùng correlation ID có hai backend access logs → có thể do retry hoặc caller gửi hai attempts.
- Có một span business nhưng nhiều span outbound → phải xem retry policy và số attempts.
- Caller log đã “select inventory-a” nhưng server A không có log → lỗi có thể xảy ra trước khi HTTP request đến A.
- Server A xử lý 200 nhưng caller timeout → có thể response bị mất/đến muộn; không gọi đó là “A không nhận request”.
- Dashboard client-side metrics khác server-side → đối chiếu source traffic (gateway, probes, scheduled jobs) và thời điểm scrape.

Không log raw `Authorization`, cookies, user IDs hay toàn bộ URL chứa query nhạy cảm. Dùng route templates, service ID, instance ID từ nguồn đáng tin cậy và correlation ID đã chuẩn hóa.

## 17. Đừng thay metric quan sát bằng debug log trên mỗi request

Có thể thêm logging tạm để kiểm tra thuật toán nhưng không nên để production ghi hàng triệu dòng `selectedInstance=...` mà không giới hạn. Vấn đề gồm:

- Tăng CPU, allocation, I/O và chi phí log storage.
- Có nguy cơ chứa host/port hạ tầng nhạy cảm.
- Khi sampling/truncation xảy ra, log không còn đại diện đầy đủ cho traffic.
- Log của server chỉ chứa requests đã đến server; failures trước transport không hiện diện.
- Log selection sau request completion có thể đảo thứ tự và không mô tả chính xác Round Robin.

Ưu tiên **Micrometer counters/timers/gauges** cho trend, **tracing có sampling** cho điều tra sâu, và **log có cấu trúc** ở các điểm lỗi quan trọng. Debug logging chỉ bật có thời hạn trong môi trường được kiểm soát.

Nếu cần một custom `LoadBalancerLifecycle` để ghi chi tiết instance selection, phải kiểm tra lifecycle API và generic types theo Spring Cloud release train; không lấy một class tùy chỉnh chưa kiểm thử làm nguồn dữ liệu production.

## 18. Thiết kế dashboard để không bị phần trăm đánh lừa

Một bảng điều khiển nên nhóm theo service ID và operation trước, rồi hiển thị:

| Panel | Nội dung | Lý do |
|---|---|---|
| **Traffic attempts** | Request/s tới từng instance, status breakdown | Biết mỗi replica nhận gì |
| **LoadBalancer lifecycle** | Success/failed/discard/active theo tags có sẵn | Phân biệt không chọn được instance |
| **Eligibility** | Số ứng viên healthy và loại bỏ theo thời gian | Tỷ lệ đúng phụ thuộc tập được chọn |
| **Latency** | p50, p95, p99 từng instance và end-to-end | Count cân bằng không nghĩa tail latency cân bằng |
| **Errors** | Timeout, connect, HTTP 5xx, circuit open | Phân biệt sự cố transport với lựa chọn |
| **Retry amplification** | Attempts/logical calls | Traffic backend cao hơn traffic user |
| **Capacity** | CPU, memory, queues, active requests | Hiểu áp lực thực tế |
| **Deployment timeline** | Scale up/down, rollout, config version | Xác định điểm thay đổi policy |

Cách hiển thị tỷ lệ nên kèm **sample count**, thời gian, caller scope và expected policy. Ví dụ thông điệp “A 60% (N=5)” khác hoàn toàn “A 60% (N=500.000, expected 50%, cùng eligible set)”.

### Cảnh báo thế nào?

Thay vì chỉ cảnh báo “A lệch hơn 5%” trên mọi khoảng, một cảnh báo vận hành có thể yêu cầu kết hợp:

- Ít nhất một ngưỡng N trong cửa sổ (đủ số observations).
- Tập eligible/weight được xác nhận ổn định.
- Sai số vượt ngưỡng có ý nghĩa vận hành trong nhiều cửa sổ liên tiếp.
- Có dấu hiệu xấu thật: backend p99, error rate, active requests hoặc user-facing SLO bị ảnh hưởng.
- Không phải giai đoạn deploy/canary/health filtering có chủ đích.

**Cảnh báo nên dẫn đến hành động cụ thể**, không chỉ phát hiện một tỷ lệ không tròn số. Ví dụ “B không có traffic dù healthy, trong cùng zone và tất cả caller đáng lẽ chọn B” đáng điều tra hơn “B chỉ có 31% thay vì 33,3% sau 20 request”.


## 19. Lab: đo phân phối với ba replica inventory

Thực hành dưới đây thiết kế để học cách **đếm và giải thích dữ liệu**, không để chứng minh “mỗi instance phải nhận đúng 1/3”. Mô hình:

~~~text
order-service :8080
    |
    | @LoadBalanced RestClient
    | http://inventory-service/demo/whoami
    v
Spring Cloud LoadBalancer
    |
    +--- inventory-a :8081
    +--- inventory-b :8082
    +--- inventory-c :8083
~~~

Chạy cả ba backend cùng một codebase, chỉ khác cổng và `demo.instance-id`. Dùng `SimpleDiscoveryClient` để tập trung vào LoadBalancer mà không cần cài một registry ngoài.

### 19.1. Endpoint ở mỗi inventory replica

Các dependency cần có ở inventory: `spring-boot-starter-web` và `spring-boot-starter-actuator`. Để có custom Micrometer Counter, dùng class `io.micrometer.core.instrument.Counter` được quản lý bởi dependencies phù hợp.

~~~java
package com.example.inventory;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceController {

    private final String instanceId;
    private final Counter completedHandlerCounter;

    public InstanceController(
            @Value("${demo.instance-id}") String instanceId,
            MeterRegistry registry) {

        this.instanceId = instanceId;

        this.completedHandlerCounter = Counter.builder(
                        "demo.inventory.handler.requests"
                )
                .description("Requests reaching the demo handler")
                .tag("instance", instanceId)
                .register(registry);
    }

    @GetMapping("/demo/whoami")
    public InstanceReply whoAmI() {
        completedHandlerCounter.increment();
        return new InstanceReply(instanceId);
    }

    public record InstanceReply(String instanceId) {
    }
}
~~~

Đây là counter **request vào đến handler demo**, không phải counter của *mọi lần LoadBalancer chọn instance*, và cũng không đo một response đã thành công qua transport. Nếu client timeout trước khi backend nhận request, counter không tăng; nếu backend xử lý xong nhưng response bị mất, counter **vẫn có thể tăng**.

Chạy ba tiến trình inventory với thuộc tính riêng:

~~~powershell
java -jar inventory-service.jar --server.port=8081 --demo.instance-id=inventory-a
java -jar inventory-service.jar --server.port=8082 --demo.instance-id=inventory-b
java -jar inventory-service.jar --server.port=8083 --demo.instance-id=inventory-c
~~~

Mỗi lệnh cần chạy trong **terminal riêng**. Lệnh giả định đã có JAR của ứng dụng demo; đây không phải artifact có sẵn từ Spring Cloud. Nếu dùng Maven/Gradle ở dự án thực, có thể khởi chạy theo cách tương ứng.

Trước khi thử LoadBalancer, gọi trực tiếp từng instance:

~~~powershell
Invoke-RestMethod "http://localhost:8081/demo/whoami"
Invoke-RestMethod "http://localhost:8082/demo/whoami"
Invoke-RestMethod "http://localhost:8083/demo/whoami"
~~~

Xác nhận lần lượt nhận `inventory-a`, `inventory-b`, `inventory-c`, không có instance nào chưa sẵn sàng.

### 19.2. Cấu hình caller với SimpleDiscoveryClient và metrics

Trong `order-service/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service

  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
              - uri: http://localhost:8083

    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Mẫu này dùng **ba replica có trọng số như nhau** và không chủ ý bật zone/hint/sticky session hay retries. Nếu dự án đã có retry hoặc supplier tùy chỉnh, hãy xác minh/tắt chúng trong **môi trường lab** để mẫu đo dễ giải thích. Đừng tắt retry/circuit breaker của ứng dụng production chỉ để làm đẹp thống kê.

### 19.3. RestClient theo service ID

Tạo builder load-balanced:

~~~java
package com.example.order.http;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfig {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("inventoryRestClient")
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {

        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Expose một endpoint proxy:

~~~java
package com.example.order.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class InventoryProxyController {

    private final RestClient client;

    public InventoryProxyController(
            @Qualifier("inventoryRestClient") RestClient client) {

        this.client = client;
    }

    @GetMapping("/demo/inventory")
    public InstanceReply inventory() {
        return client.get()
                .uri("/demo/whoami")
                .retrieve()
                .body(InstanceReply.class);
    }

    public record InstanceReply(String instanceId) {
    }
}
~~~

`RestClient` gọi `http://inventory-service/demo/whoami`, và Spring Cloud LoadBalancer sẽ chọn một `ServiceInstance` trong danh sách khai báo. Endpoint controller chỉ phù hợp lab; response chứa ID hạ tầng không nhất thiết nên mở ra Internet.

### 19.4. Quan sát N = 10 trước, nhưng chưa kết luận

PowerShell:

~~~powershell
1..10 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/demo/inventory"
}
~~~

Có thể thấy Round Robin gần luân phiên, hoặc nếu đã chọn Random, kết quả có vài lần cùng replica liên tiếp. **Mười request chỉ đủ xác nhận định tuyến hoạt động, không đủ kết luận phân phối thống kê dài hạn**.

Xác minh thuật toán thực tế và supplier trước khi dự đoán tỷ lệ. Nếu một client đã dùng weighted routing hoặc custom `ReactorLoadBalancer<ServiceInstance>`, không kỳ vọng kết quả giống default.

### 19.5. Đếm 900 responses và giữ nguyên cả lỗi

~~~powershell
$N = 900
$results = New-Object 'System.Collections.Generic.List[string]'

for ($i = 0; $i -lt $N; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8080/demo/inventory" -TimeoutSec 3
        $results.Add([string]$response.instanceId)
    }
    catch {
        $results.Add("ERROR")
    }
}

$results |
    Group-Object |
    Sort-Object Name |
    Select-Object Name, Count,
        @{ Name = "Percent"; Expression = { [math]::Round(100.0 * $_.Count / $N, 2) } }
~~~

Đây là script **sequential** từ một PowerShell process. Nó đếm **responses hoàn thành được client nhận** và nhóm lỗi vào `ERROR`; không thể suy ngay N=900 nghĩa là đúng 900 LoadBalancer selections nếu framework có retry.

Ví dụ **kết quả minh họa, không phải kết quả đo thực tế**:

~~~text
Name          Count  Percent
----          -----  -------
inventory-a     287    31.89
inventory-b     305    33.89
inventory-c     308    34.22
~~~

Nếu dùng Round Robin với một caller, danh sách 3 instance cố định và không retry, lượt chọn có thể gần hoặc đúng 300/300/300 sau 900 selections; nhưng kết quả hoàn thành có thể khác khi có lỗi. Nếu dùng Random, 287/305/308 không phải bằng chứng lỗi. Với N lớn, hãy lấy các chỉ số trực tiếp từ metrics để kiểm tra chéo.

### 19.6. Đối chiếu Actuator của caller và từng backend

Ví dụ ở caller:

~~~powershell
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.success"
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.failed"
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.discard"
~~~

Ở backend, tùy cấu hình exposure:

~~~powershell
Invoke-RestMethod "http://localhost:8081/actuator/metrics/demo.inventory.handler.requests"
Invoke-RestMethod "http://localhost:8082/actuator/metrics/demo.inventory.handler.requests"
Invoke-RestMethod "http://localhost:8083/actuator/metrics/demo.inventory.handler.requests"
~~~

Trước khi so sánh, hãy chắc backend cũng bật `management.endpoints.web.exposure.include` cho metrics ở lab. Nếu dùng counter riêng có tên `demo.inventory.handler.requests`, Actuator có thể trả count và tag `instance` như code đã đăng ký. Với nhiều process, mỗi process counter bắt đầu từ 0; nhớ trừ **baseline ban đầu** thay vì so raw count giữa một instance vừa restart và một instance đã chạy nhiều giờ.

Ở caller, xem `availableTags` thực tế của loadbalancer meters. Chỉ khi có instance tag phù hợp mới sử dụng trực tiếp timer count đó để đánh giá phân phối theo instance; nếu tag thiếu hoặc không ổn định, phải bổ sung nguồn quan sát được chứng thực từ backend/traces.

### 19.7. Khi test qua WebClient hoặc OpenFeign

Logic bài thực hành vẫn giữ nguyên: business code gọi service ID, backend trả `instanceId` và caller thống kê kết quả.

Với WebClient:

~~~java
// webClient phải được tạo từ @LoadBalanced WebClient.Builder
Mono<InstanceReply> reply = webClient.get()
        .uri("http://inventory-service/demo/whoami")
        .retrieve()
        .bodyToMono(InstanceReply.class);
~~~

Request chỉ thực thi khi có subscriber. Nếu `Mono` không được subscribe hoặc bị cancel, **không được đếm nó như HTTP attempt chắc chắn đã gửi**.

Với OpenFeign:

~~~java
@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @GetMapping("/demo/whoami")
    InstanceReply whoAmI();
}
~~~

Cần thêm `@EnableFeignClients` và dependencies phù hợp; mẫu chỉ là interface minh họa trong caller. Các class `InstanceReply` cần được định nghĩa tương ứng. OpenFeign có thể dùng HTTP client/retry/metrics khác với WebClient, nên phải so sánh những lớp quan sát **tương đương**, không đối chiếu một timer count với tổng method call một cách tùy tiện.

## 20. Thử thay đổi topology để hiểu tỷ lệ

Sau bài lab ổn định, thay đổi **một yếu tố mỗi lần**.

### Kịch bản A — Dừng inventory-c

Dừng process ở cổng 8083, nhưng `SimpleDiscoveryClient` tĩnh vẫn có thể tiếp tục trả URI đó. Nếu không cấu hình health-check supplier, LoadBalancer **có thể vẫn chọn C** và tạo lỗi kết nối.

Kết quả có thể xuất hiện:

- A/B vẫn trả 200.
- Những attempts chọn C thất bại trước khi backend nhận request.
- Tỷ lệ **completed responses** của C giảm về 0.
- Tỷ lệ selection đến C **chưa chắc giảm**, vì discovery tĩnh chưa loại C.

Điều này chứng minh vì sao “C không có success” không đồng nghĩa “LoadBalancer không chọn C”.

Nếu bật một `HealthCheckServiceInstanceListSupplier` phù hợp, sau khi nó loại C khỏi tập eligible, lựa chọn mới sẽ phân bổ trên A/B theo policy. Trong Spring Cloud, health supplier có thể có cơ chế refresh/caching riêng; kiểm tra thời gian cập nhật thay vì cho rằng thay đổi là tức thì.

### Kịch bản B — Tăng độ chậm của B

Sửa **môi trường lab** để B trì hoãn 500 ms, A/C xử lý nhanh. Nếu tất cả vẫn trả 200, Round Robin có thể chọn B với tần suất tương đương nhưng **active requests** và p95/p99 của B tăng.

Khi đó nên điều tra performance/backpressure/capacity của B, không nhất thiết thay thuật toán Round Robin bằng Random. Nếu áp dụng timeout/health filtering làm B bị loại, kỳ vọng phân phối sẽ thay đổi theo thời gian.

### Kịch bản C — Bật retry có giới hạn

Tạo lỗi kết nối tạm thời cho A hoặc một instance, rồi bật retry chỉ trong lab. Quan sát:

- Một logical request có thể có hai attempts.
- Retry-aware supplier có thể tránh instance vừa lỗi, nhưng cũng có thể chọn lại cùng instance tùy policy.
- Backend requests count có thể lớn hơn số user requests.
- Caller success count có thể khác số network attempts.
- Retry tăng latency/tải; không nên bật đồng thời nhiều tầng mà không có deadline.

Kết quả test cần mô tả chính xác **tầng đang đếm**.

### Kịch bản D — Caller chạy hai replicas

Chạy hai order-service instances, cùng gọi một inventory service ID. Mỗi caller có thể có Round Robin state riêng. Nếu request từ người dùng đi vào caller A/B không đồng đều, chuỗi lựa chọn/response quan sát tổng hợp sẽ khác thí nghiệm một caller.

Đừng giả định Spring Cloud LoadBalancer có một atomic counter Round Robin **toàn cục xuyên các JVM caller**.

## 21. Kiểm thử không flaky: điều gì nên assert?

### Với Round Robin trong điều kiện kiểm soát

Nếu unit/integration test kiểm soát **một LoadBalancer instance**, danh sách cố định [A,B,C], không retry, không concurrency và không thay đổi supplier, có thể assert số lựa chọn của mỗi instance sai khác tối đa một sau N selections (và đúng bằng nhau nếu N chia hết cho ba). Nên kiểm tra ở tầng **selection** hoặc mock/stub tương đương, không dựa trên response completion order.

Nhưng nếu test chạy đồng thời với các client khác, startup warm-up khác nhau hoặc instance lists được refresh, assertion này có thể thất bại vì điều kiện thí nghiệm không còn đúng.

### Với Random

Không nên viết test như:

~~~java
// Anti-pattern: random không bảo đảm đúng 3/3 sau 6 request.
assertEquals(2, countA);
assertEquals(2, countB);
assertEquals(2, countC);
~~~

Thay vào đó:

1. Unit test kiểm tra không bao giờ chọn instance ngoài tập eligible.
2. Kiểm tra trường hợp danh sách rỗng/một instance và hành vi fallback hợp lệ.
3. Nếu test cần bảo đảm một chọn lựa cụ thể, dùng deterministic/stub strategy, không dùng Random thật.
4. Statistical test phân phối nên chạy trên mẫu lớn, có mức sai số, seed/conditions có thể ghi lại khi framework cho phép, và không dựa vào ngưỡng cứng tùy tiện.
5. Phân phối kiểm nghiệm trong môi trường load/performance test nên được báo **tỷ lệ, N và khoảng kỳ vọng**, không trở thành unit-test flaky chạy mọi PR.

### Kiểm thử semantic metrics

Đặc biệt cần test phân biệt:

- Một request HTTP 500 có thể được LB lifecycle đếm là response thay vì exception, tùy integration.
- Một lần no-instance làm tăng discard thay vì backend requests.
- Một request có retry có thể tạo nhiều events ở một số metric layers.
- Một request bị circuit breaker từ chối có thể không chạm LoadBalancer.
- Backend handler counter và HTTP server metrics có phạm vi khác nhau.
- Một instance restart làm cumulative counter bắt đầu lại.

Những kiểm thử này bảo vệ **chất lượng phép đo** — điều quan trọng không kém độ đúng của thuật toán routing.


## 22. Bảng chẩn đoán phân phối tải bất thường

| Quan sát | Giải thích có thể | Bằng chứng cần thu |
|---|---|---|
| 10 request đều vào A | Random tình cờ lặp, sticky session hoặc chỉ A eligible | Lấy mẫu lớn hơn, kiểm tra strategy và supplier |
| A/B/C nhận không đúng 1/3 | Random variation, weights, zone/hint, health filtering | Expected policy và N theo từng cửa sổ |
| Round Robin không tạo response A-B-C liên tiếp | Completion đảo thứ tự do latency/concurrency | Selection events và trace |
| C không có successful responses | C bị loại hoặc attempts tới C thất bại | Eligible list, selections, client errors và backend logs |
| `loadbalancer.requests.success` cao, nhưng HTTP 5xx tăng | Lifecycle success là có response, không đồng nghĩa HTTP 2xx | Status metrics tại HTTP client/server |
| Backend count lớn hơn user requests | Retry, gateway traffic, probes hoặc background jobs | Attempts per logical call, route và nguồn |
| Backend count thấp hơn caller selections | Connect failure, no-instance hoặc lỗi trước khi server nhận | Client transport errors và server access logs |
| Tỷ lệ đổi sau autoscale | Discovery/cache cập nhật không đồng thời | Registry events, supplier snapshots và TTL |
| B nhận ít dù healthy | Zone/hint, weight, sticky/session preference | Caller metadata, eligible list và routing policy |
| A có active gauge cao hơn | A chậm hơn, queue/pool dài hơn | p95/p99, CPU, pool, threads, queues |
| Counter Prometheus đột ngột giảm | Process restart/metrics reset hoặc scrape gap | Restart timestamp, rate/increase xử lý reset |
| Không có `loadbalancer.requests.*` | Property tắt, thiếu registry, chưa có event hoặc sai app | Config, Actuator meter list và sample traffic |
| Không thấy tag instance | Một integration không cung cấp metadata đó | `availableTags` thực tế và backend metrics |
| Time series tăng rất lớn | URI/path/user ID động trong labels | `include-path=false`, MeterFilter và route templates |
| Một logical request chọn hai instance | Retry, resubscription hoặc proxy retry | Trace attempts và retry configuration |
| Discard tăng | LoadBalancer không lấy được instance đích | Service ID, discovery và supplier |
| Phân phối request đều nhưng user-facing SLO xấu | Work/capacity, timeout hoặc latency không đều | End-to-end latency, error rate, active requests |
| Hai caller có tỷ lệ khác | Zone/state/version của từng caller khác | Caller ID, config, instance list |
| 503 tăng nhưng danh sách instance vẫn có | Backend hoặc proxy trả 503 | Phân loại status origin và health logic |

## 23. Runbook phân tích khi dashboard báo lệch

Một quy trình có thể thực hiện theo thứ tự:

1. **Khoanh phạm vi:** service ID, operation, caller instance, zone, khoảng thời gian và version triển khai.
2. **Xác nhận mẫu số:** biểu đồ đếm selections, HTTP attempts, backend arrivals, response 2xx hay logical calls? Có tính failed/canceled attempts không?
3. **Kiểm tra cỡ mẫu:** N đủ lớn để nói về tỷ lệ chưa? Nếu chỉ có vài request, báo dữ liệu nhưng chưa kết luận.
4. **Xác minh policy kỳ vọng:** Round Robin, Random, weights, zone, hints, sticky/affinity, canary và retry-aware supplier.
5. **Kiểm tra eligible list:** từng instance được discovery/health supplier cung cấp trong khoảng thời gian nào?
6. **Đối chiếu caller và server:** lifecycle metrics, transport metrics, backend HTTP status và server request counter.
7. **Kiểm tra retry:** số attempts trên mỗi logical operation, tầng nào chịu trách nhiệm retry và có no-instance không?
8. **Đọc latency/resource metrics:** p95/p99, active requests, CPU, queues, connection pools có phân bố khác nhau?
9. **Xem trace:** request bị lỗi trước khi đến instance hay backend đã nhận nhưng response không đến caller?
10. **Tái hiện có kiểm soát:** một caller, danh sách tĩnh, policy rõ, không retry, đủ N và không scale trong cửa sổ.
11. **Sửa nguyên nhân đã xác minh:** health filtering, discovery cache, zone/weight metadata, retry budget hoặc backend bottleneck, không thay thuật toán theo cảm tính.
12. **Đánh giá sau thay đổi:** dùng cùng traffic cohort và SLO, không chỉ so hai tỷ lệ phần trăm của vài phút.

### Mẫu kết luận có trách nhiệm

**Không đủ bằng chứng:**

> “Round Robin bị lỗi vì ba request đầu đều đến A.”

**Có bằng chứng hơn:**

> “Trong cửa sổ 15 phút, một caller gửi 900 lời gọi GET inventory; có ba instance healthy liên tục, policy Random không trọng số, retry tắt. Số responses thành công là A=287, B=305, C=308. Phân phối này không cho thấy sai lệch rõ so với xác suất 1/3 trong mô hình đơn giản; cần tiếp tục theo dõi latency/error rate và đối chiếu selection metrics.”

Những số liệu nêu trên là **minh họa**, không phải kết quả đo thật. Trong production phải bổ sung nguồn dữ liệu, định nghĩa rõ count, timezone/khoảng thời gian, số lỗi và độ đầy đủ của metrics.

## 24. Checklist trước khi kết luận có vấn đề về cân bằng tải

- [ ] Biết chính xác thuật toán và cấu hình của `ReactorLoadBalancer<ServiceInstance>` đang dùng.
- [ ] Kiểm tra `ServiceInstanceListSupplier` và các instance eligible trong mỗi cửa sổ.
- [ ] Phân biệt selections, sent attempts, received requests, successful responses và logical calls.
- [ ] Chia dữ liệu theo caller, route, version, zone và thời gian khi policy/topology thay đổi.
- [ ] Không suy luận Random từ vài request; luôn nêu N và xác suất kỳ vọng `p_i`.
- [ ] Không assert Round Robin theo thứ tự response hoàn thành trong môi trường concurrent.
- [ ] Không so 1/N instances nếu policy có weights, hints, zone hoặc affinity.
- [ ] Kiểm tra cache, discovery, health check, retry và scale events trước khi kết luận một replica bị bỏ quên.
- [ ] Biết nguồn của instance ID; không chỉ dựa vào body hoặc log đã bị sampling.
- [ ] Bật `spring.cloud.loadbalancer.stats.micrometer.enabled` khi cần LoadBalancer metrics và có `MeterRegistry`.
- [ ] Hiểu ngữ nghĩa `active`, `success`, `failed` và `discard`, và kiểm tra available tags thực tế.
- [ ] Không mặc định lifecycle success nghĩa là HTTP 2xx.
- [ ] Đối chiếu backend status, duration, counters và caller lifecycle/transport metrics.
- [ ] Dùng baseline/rate/increase khi xem cumulative counters; xét restart và scrape gaps.
- [ ] Bảo vệ Actuator/Prometheus và hạn chế tags/URI paths có high cardinality.
- [ ] Quan sát p95/p99, error rate, active requests và tài nguyên, không chỉ request count.
- [ ] Phân biệt logical calls và attempts trong policy retry, timeout, circuit breaker.
- [ ] Ghi nhận warm-up, rollout, health transitions và autoscaling.
- [ ] Unit test deterministic cho selection edge cases; thống kê Random trên mẫu lớn riêng.
- [ ] Cảnh báo mất cân bằng phải xét sample size, expected policy và hậu quả vận hành.
- [ ] Kết luận từ nhiều nguồn chứng cứ chứ không từ một screenshot hoặc ba responses.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ServiceInstanceListSupplier`, Round Robin/Random, health, cache, retry và phần **Spring Cloud LoadBalancer Statistics**.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): property `spring.cloud.loadbalancer.stats.micrometer.enabled` và các thuộc tính lựa chọn instance.
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): `MeterRegistry`, timer, counter, gauge, HTTP metrics.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): cấu hình và bảo vệ `/actuator/metrics`.
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meter types, tag cardinality, timer và distribution statistics.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate()`, `increase()` và counter resets.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient và HTTP client blocking.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient reactive và subscription.
- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): Feign, LoadBalancer và observability.

**Kết luận:** quan sát phân phối tải đúng bắt đầu từ **mẫu số, tập instance đủ điều kiện, policy kỳ vọng và cửa sổ thống kê**, không phải số lần một replica xuất hiện trong vài response. Random có biến động thống kê tự nhiên; Round Robin bị ảnh hưởng bởi concurrency, retry, thay đổi danh sách và nhiều caller độc lập. Kết hợp Micrometer LoadBalancer lifecycle metrics, HTTP backend counters, tracing, sample đủ lớn và dữ liệu discovery/health theo thời gian giúp nhận diện lệch phân phối thực sự mà không nhầm ngẫu nhiên thành lỗi thuật toán.
