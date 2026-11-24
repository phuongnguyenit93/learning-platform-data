# Ước lượng tải theo số dịch vụ, instance và chu kỳ cập nhật

Khi triển khai Spring Cloud Service Discovery, tải của registry không chỉ phụ thuộc số lượng service. Một hệ thống có nhiều service nhưng ít instance và ít consumer có thể tạo tải thấp hơn một hệ thống chỉ có vài service nhưng hàng trăm instance, nhiều consumer liên tục tải danh sách và health check chạy với chu kỳ ngắn.

Để ước lượng tải, cần nhìn vào số service logic, tổng số instance, số tiến trình consumer truy vấn registry, chu kỳ heartbeat, chu kỳ health check, chu kỳ cập nhật danh sách và kích thước dữ liệu trả về. Mỗi registry có cách hoạt động khác nhau: Eureka thường dùng heartbeat và client fetch; Consul có agent health check cùng truy vấn catalog; ZooKeeper thiên về session và watch theo sự kiện.

Bài viết xây dựng mô hình tính tải gần đúng, đưa ra ví dụ số, giải thích ảnh hưởng của chu kỳ cập nhật và cache, rồi trình bày cách đo kiểm trước khi mở rộng hệ thống.

## 1. Các đại lượng cần biết

Trước khi tính toán, thống nhất các ký hiệu:

| Ký hiệu | Ý nghĩa |
|---|---|
| S | Số service logic được đăng ký |
| I_s | Số instance của service thứ s |
| I | Tổng số instance của toàn hệ thống, bằng tổng I_s |
| C | Số tiến trình discovery client thường xuyên truy vấn hoặc tải registry |
| T_r | Chu kỳ heartbeat/renewal của một instance |
| T_f | Chu kỳ consumer tải hoặc làm mới danh sách discovery |
| T_h | Chu kỳ health check của một instance |
| R | Kích thước response registry mà một client nhận được |
| W_s | Số consumer đang theo dõi thay đổi của service s |
| λ_d | Tốc độ thay đổi instance do deploy, scale hoặc restart |

Ví dụ, hệ thống có 40 service, mỗi service trung bình 5 instance:

\[
I = \sum_{s=1}^{S} I_s = 40 \times 5 = 200
\]

Nếu 80 tiến trình ứng dụng có bật discovery client và đều làm mới danh sách registry, C có thể là 80. Một tiến trình vừa là provider vừa là consumer vẫn có thể tạo cả renewal lẫn fetch traffic; cần đếm theo vai trò thực tế của từng client.

**Số service S** cho biết độ rộng catalog và số nhóm logic. **Tổng instance I** thường ảnh hưởng trực tiếp tới số heartbeat, health check, kích thước registry response và số bản ghi cần lưu. **Số consumer C** ảnh hưởng mạnh tới lượng truy vấn và số bản sao cache.

## 2. Các nguồn tạo tải lên registry

Tải discovery thường đến từ nhiều luồng độc lập:

1. **Đăng ký và hủy đăng ký:** xuất hiện khi instance khởi động, dừng hoặc thay đổi thông tin.
2. **Heartbeat/renewal:** provider định kỳ xác nhận instance vẫn còn hiện diện.
3. **Health check:** agent hoặc registry kiểm tra endpoint của instance theo chu kỳ.
4. **Fetch/query:** consumer tải hoặc truy vấn danh sách service instance.
5. **Watch/event:** consumer nhận thông báo khi registry thay đổi và đọc lại dữ liệu cần thiết.
6. **Refresh và retry:** client phục hồi kết nối, tải snapshot mới hoặc thử lại sau lỗi.

Không phải mọi registry đều thực hiện đủ các luồng theo cùng cách. Ví dụ, Eureka có heartbeat từ client; Consul thường để agent thực hiện health check; ZooKeeper dùng session heartbeat và watch event. Vì vậy, công thức cần được điều chỉnh theo implementation thay vì cộng máy móc mọi con số thành một QPS duy nhất.

~~~mermaid
flowchart TD
    P["Provider instances"] --> R["Registry / agent"]
    P -->|"Register / deregister"| R
    P -->|"Heartbeat / renewal"| R
    H["Health check scheduler"] -->|"Probe instance"| P
    H --> R
    C["Consumer discovery clients"] -->|"Fetch / query"| R
    R -->|"Snapshot / change notification"| C
    D["Deployment / autoscaling"] -->|"Instance churn"| P
~~~

## 3. Ước lượng heartbeat và renewal

Nếu mỗi instance gửi một renewal sau mỗi T_r giây, tốc độ renewal trung bình gần đúng:

\[
Q_{renew} \approx \frac{I}{T_r}
\]

Ví dụ có 300 instance, mỗi instance renewal 30 giây:

\[
Q_{renew} \approx \frac{300}{30} = 10 \text{ request/giây}
\]

Đây là lưu lượng trung bình. Nếu tất cả instance khởi động cùng lúc và bộ định thời gần đồng bộ, request có thể dồn thành burst. Cần quan sát peak QPS và phân bố thời gian thực tế, không chỉ dựa vào giá trị trung bình.

### Heartbeat và lease expiration

Với Eureka, các thuộc tính thường được dùng để điều chỉnh nhịp renewal và thời gian lease:

~~~yaml
eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
~~~

Ví dụ trên minh họa chu kỳ renewal 30 giây và lease expiration 90 giây. Giá trị hiệu lực cần được kiểm tra cùng cấu hình Eureka Server và hành vi của phiên bản Spring Cloud Netflix đang sử dụng.

Giảm renewal interval làm registry nhận tín hiệu thường xuyên hơn nhưng tăng request. Tăng lease expiration giúp chịu được một số gián đoạn ngắn nhưng kéo dài thời gian bản ghi cũ có thể còn tồn tại khi instance thực sự chết. Không giảm lease timeout chỉ để phát hiện lỗi nhanh nếu mạng hoặc JVM có pause đáng kể.

## 4. Ước lượng tải fetch từ consumer

Nếu mỗi consumer tải danh sách registry đầy đủ sau mỗi T_f giây, số lần fetch trung bình:

\[
Q_{fetch} \approx \frac{C}{T_f}
\]

Ví dụ 100 discovery client làm mới danh sách mỗi 30 giây:

\[
Q_{fetch} \approx \frac{100}{30} = 3.33 \text{ fetch/giây}
\]

Số request có vẻ thấp, nhưng mỗi response có thể chứa hàng trăm hoặc hàng nghìn instance cùng metadata. Vì vậy, cần tính cả kích thước payload.

Nếu một response có kích thước trung bình R byte, băng thông tải danh sách gần đúng:

\[
B_{fetch} \approx \frac{C \times R}{T_f}
\]

Giả sử R = 200 KB, C = 100 và T_f = 30 giây:

\[
B_{fetch} \approx \frac{100 \times 200}{30}
= 666.7 \text{ KB/giây}
\]

Đây là lưu lượng trung bình một chiều cho response, chưa tính request, header, TLS overhead, retry và burst. Nếu consumer chỉ truy vấn một service cụ thể thay vì tải toàn bộ catalog, R có thể nhỏ hơn đáng kể.

### Cấu hình chu kỳ fetch của Eureka

Ví dụ:

~~~yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
~~~

Chu kỳ fetch ngắn giúp consumer nhận thay đổi nhanh hơn nhưng làm tăng số lần truy vấn và lượng dữ liệu truyền. Với registry lớn, full registry fetch có thể chiếm đáng kể CPU, heap, network và thời gian parse ở mỗi client.

## 5. Ước lượng health check

Nếu mỗi instance được kiểm tra sau mỗi T_h giây, số lần probe trung bình:

\[
Q_{health} \approx \frac{I}{T_h}
\]

Với 300 instance và chu kỳ 10 giây:

\[
Q_{health} \approx \frac{300}{10} = 30 \text{ probe/giây}
\]

Nếu mỗi probe là HTTP request tới Actuator, provider phải xử lý tổng lượng request này. Khi có nhiều agent hoặc nhiều hệ thống giám sát cùng kiểm tra một endpoint, cần tính tổng các nguồn probe.

Ví dụ cấu hình Consul:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        register: true
        register-health-check: true
        health-check-path: /actuator/health
        health-check-interval: 10s
~~~

Tên và hành vi thuộc tính cần đối chiếu với phiên bản Spring Cloud Consul đang dùng. Trong mô hình Consul thông thường, agent thực hiện health check theo registration; không mặc định mỗi consumer đều gửi một probe độc lập cho từng provider.

Health check càng ngắn thì thời gian phát hiện endpoint lỗi có thể giảm, nhưng tải probe tăng. Cần chọn endpoint nhẹ, timeout hợp lý và tiêu chí phản ánh readiness thực tế. Không nên để health check thực hiện truy vấn nghiệp vụ nặng hoặc quét sâu mọi dependency ở mỗi lần probe.

## 6. Tải do đăng ký và thay đổi instance

Khi autoscaling hoặc rollout, registry nhận các thao tác register/deregister. Nếu một lần deploy tạo hoặc thay thế ΔI instance trong khoảng Δt, tốc độ thay đổi trung bình:

\[
Q_{churn} \approx \frac{\Delta I}{\Delta t}
\]

Ví dụ rollout 30 instance trong 60 giây:

\[
Q_{churn} \approx \frac{30}{60} = 0.5 \text{ thay đổi/giây}
\]

Con số trung bình này không thể hiện burst. Nếu 30 instance cùng khởi động trong 5 giây, registry có thể nhận gần 6 registration mỗi giây trong khoảng ngắn, đồng thời các consumer có thể nhận nhiều notification hoặc phải làm mới cache.

Những yếu tố làm tăng churn:

- Rolling deployment với nhiều replica được thay cùng lúc.
- Autoscaler tăng/giảm replica theo ngưỡng quá nhạy.
- Container crash-loop hoặc health check dao động.
- Session ZooKeeper hết hạn hàng loạt sau sự cố mạng.
- Registry client reconnect và đăng ký lại sau khi mất kết nối.

Giảm churn bằng rollout theo batch, giới hạn tốc độ scale, readiness gate, backoff có jitter và tránh restart hàng loạt khi registry đang phục hồi.

## 7. Mô hình tính tải tổng hợp

Với registry dùng heartbeat, polling và health check, có thể ước lượng sơ bộ:

\[
Q_{control} \approx
\frac{I}{T_r}
+ \frac{C}{T_f}
+ \frac{I}{T_h}
+ Q_{churn}
\]

Trong đó:

- I/T_r là renewal request trung bình.
- C/T_f là fetch request trung bình.
- I/T_h là health probe trung bình nếu mỗi instance có một check.
- Q_churn là registration/deregistration trung bình.

Đây là mô hình đếm thao tác gần đúng để lập kế hoạch, không phải công thức dự báo chính xác số request mà registry server nhận. Health check có thể được agent xử lý cục bộ; Consul query có thể dùng blocking request; ZooKeeper watch chủ yếu gửi notification theo thay đổi. Một số thao tác cũng đi tới provider thay vì registry server.

Nên tách thành các nhóm khi đo:

| Nhóm tải | Nơi chịu tải chính | Chỉ số cần theo dõi |
|---|---|---|
| Renewal/register | Registry API hoặc agent | Request rate, lỗi, latency |
| Full fetch/query | Registry API và consumer | QPS, payload size, CPU parse |
| Health check | Provider, agent hoặc checker | Probe rate, timeout, thời gian xử lý |
| Watch/event | Registry và consumer | Số watcher, notification fan-out, reconnect |
| Churn/recovery | Registry, client và cache | Burst registration, queue, retry, stale data |

Không nên chỉ nhìn CPU registry. Một cấu hình fetch quá thường xuyên có thể làm tăng network và CPU ở hàng trăm consumer ngay cả khi registry server vẫn còn dư tài nguyên.

## 8. Ví dụ tính tải cho một hệ thống

Giả sử hệ thống có:

- 60 service logic.
- Trung bình 5 instance mỗi service, tổng I = 300.
- 100 tiến trình discovery client tải registry.
- Eureka renewal interval 30 giây.
- Registry fetch interval 30 giây.
- Health check mỗi instance 10 giây.
- Kích thước full registry response trung bình 200 KB.

Ước lượng:

| Loại hoạt động | Phép tính | Kết quả trung bình |
|---|---:|---:|
| Renewal | 300 / 30 | 10 request/giây |
| Full registry fetch | 100 / 30 | 3.33 request/giây |
| Response bandwidth | 100 × 200 KB / 30 | 666.7 KB/giây |
| Health check | 300 / 10 | 30 probe/giây |

Như vậy có khoảng 13.33 request/giây cho renewal và fetch tới registry trong mô hình này, cộng thêm registration/deregistration. Health check tạo khoảng 30 probe/giây tới các endpoint provider nếu mỗi instance có một check.

Đây chỉ là số trung bình. Trong giờ deploy, lúc khởi động lại cluster hoặc sau một đợt mất mạng, lượng request có thể tăng nhiều lần. Cần load test với burst và failure recovery để xác định capacity thực tế.

### So sánh khi thay chu kỳ

Giữ nguyên I = 300, C = 100 và R = 200 KB:

| Thay đổi | 30 giây | 15 giây | Ảnh hưởng |
|---|---:|---:|---|
| Renewal | 10/s | 20/s | Gấp đôi renewal traffic |
| Full fetch | 3.33/s | 6.67/s | Gấp đôi query và response traffic |
| Response bandwidth | 666.7 KB/s | 1,333.3 KB/s | Gấp đôi băng thông trung bình |
| Health check 10 giây | 30/s | 30/s | Không đổi nếu giữ T_h |

Rút ngắn chu kỳ fetch từ 30 xuống 15 giây có thể giảm độ trễ cập nhật do polling, nhưng làm gấp đôi lưu lượng fetch. Cần xác định độ trễ cập nhật thực sự có ảnh hưởng đến nghiệp vụ hay không trước khi thay đổi.

## 9. Tác động của từng registry

Các registry có mô hình tải khác nhau; không áp dụng một công thức duy nhất cho mọi hệ thống.

### Eureka: heartbeat và registry fetch

Eureka client thường:

- Gửi heartbeat/renewal theo chu kỳ từ mỗi instance đã đăng ký.
- Fetch registry theo chu kỳ ở mỗi client có bật fetch.
- Cập nhật local registry cache để consumer tra cứu.
- Thực hiện register/deregister khi vòng đời instance thay đổi.

Tải tăng theo số instance ở renewal và theo số client ở fetch. Nếu mỗi client tải toàn bộ registry, kích thước catalog và metadata có ảnh hưởng trực tiếp tới băng thông, heap và thời gian parse.

Không giảm lease expiration quá thấp chỉ để xóa instance nhanh hơn. Khi có network partition hoặc JVM pause, nhiều instance có thể bị loại khỏi registry cùng lúc. Theo dõi renewal threshold, eviction, self-preservation và registry fetch latency khi tuning.

### Consul: agent health check và catalog query

Consul thường có agent chạy gần workload:

- Agent nhận registration của service.
- Agent thực hiện health check theo interval được khai báo.
- Consumer truy vấn catalog qua agent hoặc dùng cơ chế watch/blocking query.
- Agent và server đồng bộ catalog theo topology Consul.

Blocking query có thể giữ request mở tới khi index thay đổi hoặc hết thời gian chờ. Vì vậy, không nên xem mỗi lần query là một request ngắn polling liên tục; nhưng khi request hết thời gian chờ, client có thể gửi query tiếp theo. Cần theo dõi số query đang mở, thời gian chờ, index change rate và số client watch.

### ZooKeeper: session và watch

ZooKeeper dùng session để duy trì client và ephemeral znode để biểu diễn instance. Consumer có thể đăng ký watch để nhận thông báo thay đổi.

Watch giúp tránh việc mọi consumer liên tục tải toàn bộ danh sách theo một chu kỳ cố định. Tuy nhiên, khi znode thay đổi, mỗi watcher liên quan có thể nhận event và đọc lại snapshot. Một thay đổi hàng loạt có thể tạo fan-out lớn.

ZooKeeper client còn duy trì session heartbeat. Tải session phụ thuộc số client, cấu hình tick/session timeout, trạng thái kết nối và hành vi Curator; không nên lấy công thức Eureka renewal áp thẳng cho ZooKeeper.

### Static discovery

SimpleDiscoveryClient đọc danh sách instance từ cấu hình. Nó không tự gửi heartbeat, không health check và không đăng ký provider. Tải registry gần như không có nếu không có registry động; tải chuyển sang quy trình quản lý cấu hình, refresh và cache của từng ứng dụng.

## 10. Chu kỳ cập nhật và độ tươi của dữ liệu

Rút ngắn chu kỳ polling giúp consumer nhìn thấy thay đổi sớm hơn, nhưng tăng số request. Tăng chu kỳ giúp giảm tải nhưng có thể khiến consumer giữ địa chỉ cũ lâu hơn.

Độ trễ từ lúc instance thay đổi đến lúc request sử dụng danh sách mới thường gồm nhiều thành phần:

\[
T_{visible} \approx
T_{detect}
+ T_{registry-sync}
+ T_{client-refresh}
+ T_{loadbalancer-cache}
\]

Đây là mô hình phân rã để phân tích, không phải mọi registry đều có đủ bốn giai đoạn hoặc cộng tuyến tính trong mọi trường hợp. Với Eureka, cần tính lease/eviction và fetch interval. Với Consul, cần tính health check, catalog index và blocking query. Với ZooKeeper, cần tính session expiration, watch delivery và việc consumer đọc lại snapshot.

### Các lớp cache có thể làm dữ liệu cũ

Một ứng dụng có thể có nhiều lớp cache:

1. Registry hoặc agent cache.
2. Discovery client local cache.
3. Spring Cloud LoadBalancer cache.
4. Cache riêng của HTTP client hoặc gateway.

Nếu mỗi lớp có TTL riêng, thời gian stale có thể cộng dồn hoặc chồng lấn. Cần đo thời điểm thay đổi ở provider, thời điểm registry ghi nhận, thời điểm DiscoveryClient trả danh sách mới và thời điểm request thực tế ngừng gọi instance cũ.

Không đặt mọi TTL thật ngắn để cố đạt cập nhật tức thời. Cache ngắn làm tăng tải và có thể mất tác dụng khi registry đang lỗi. Chọn TTL theo yêu cầu freshness và khả năng chịu tải.

## 11. Tránh request burst và thundering herd

Khi hàng trăm instance khởi động cùng lúc, chúng có thể đồng thời:

- Kết nối tới registry.
- Đăng ký instance.
- Gửi renewal theo lịch gần nhau.
- Consumer fetch toàn bộ registry.
- Chạy health check ngay sau đăng ký.

Điều này tạo burst ngay lúc hệ thống cần registry nhất.

Các biện pháp giảm burst:

- Phân tán thời điểm khởi động instance và rollout theo batch.
- Dùng jitter cho retry hoặc lịch refresh khi implementation hỗ trợ.
- Dùng exponential backoff có giới hạn khi registry không khả dụng.
- Tránh retry đồng bộ vô hạn từ mọi client.
- Giới hạn tốc độ autoscaling và deployment.
- Giữ health check nhẹ, timeout ngắn hợp lý và interval phù hợp.
- Dùng blocking query hoặc watch thay cho polling quá dày khi registry hỗ trợ.
- Kiểm tra connection pool và giới hạn số request đồng thời.

Jitter đặc biệt hữu ích khi nhiều client được tạo cùng thời điểm. Nếu tất cả client dùng cùng một interval và cùng thời điểm bắt đầu, tải trung bình có thể thấp nhưng peak vẫn rất cao.

## 12. Chọn chu kỳ theo yêu cầu nghiệp vụ

Không nên chọn interval chỉ dựa trên một con số mặc định. Hãy xác định:

- Consumer chấp nhận gọi nhầm instance đã dừng trong bao lâu?
- Bao lâu sau deploy thì consumer cần thấy instance mới?
- Provider có thể chịu bao nhiêu health probe mỗi giây?
- Registry chịu được bao nhiêu renewal, query và watcher?
- Network latency và JVM pause thường ở mức nào?
- Có cơ chế fallback, retry và circuit breaker ở consumer không?

Ví dụ định hướng:

| Mục tiêu | Hướng chọn |
|---|---|
| Instance thay đổi ít, chấp nhận cập nhật chậm | Có thể dùng chu kỳ fetch dài hơn |
| Rollout thường xuyên, cần cập nhật tương đối nhanh | Dùng watch/blocking query hoặc fetch interval phù hợp, đồng thời đo peak |
| Health endpoint tốn tài nguyên | Tăng interval, tối ưu endpoint và tách readiness check cần thiết |
| Mạng chập chờn hoặc JVM pause dài | Tránh session/lease timeout quá ngắn |
| Registry lớn với nhiều consumer | Hạn chế full catalog fetch, dùng cache và query theo service khi phù hợp |

Nếu nghiệp vụ yêu cầu failover trong vài giây, polling 30 giây có thể không đáp ứng. Khi đó cần đánh giá cơ chế watch, health check, client-side timeout/circuit breaker và routing ở tầng hạ tầng thay vì chỉ giảm tất cả interval xuống rất thấp.

## 13. Đo lường và kiểm thử tải

Trước khi đưa vào production, nên chạy thử với số lượng service, instance và consumer gần với quy mô dự kiến. Mô phỏng cả steady state và tình huống burst.

### Chỉ số ở registry

- Request rate theo endpoint và loại thao tác.
- p50/p95/p99 latency của register, renewal, fetch và query.
- CPU, heap, garbage collection và network throughput.
- Số instance, số session, số watcher và số health check.
- Số lần timeout, retry, eviction hoặc session expiration.
- Kích thước registry response và tốc độ thay đổi catalog.

### Chỉ số ở client/provider

- Thời gian đăng ký từ lúc ứng dụng start.
- Renewal failure và số lần reconnect.
- Discovery refresh duration và tuổi của cache.
- Số instance trả về cho mỗi service ID.
- Health check latency, timeout và tỷ lệ passing.
- Tỷ lệ request tới instance không còn khả dụng.

### Kịch bản kiểm thử

1. Khởi động toàn bộ instance và đo registration burst.
2. Chạy ổn định trong một khoảng đủ dài để đo renewal, fetch và health check.
3. Scale một service lên gấp đôi trong thời gian ngắn.
4. Dừng một nhóm instance có kiểm soát và quan sát deregistration.
5. Dừng cưỡng bức một số instance để đo thời gian phát hiện lỗi.
6. Làm gián đoạn kết nối registry trong thời gian ngắn rồi phục hồi.
7. Khởi động lại registry node/agent và quan sát reconnect, retry, cache refresh.
8. So sánh độ trễ cập nhật discovery với mức CPU, network và p95 latency.

Không chỉ kiểm thử khi mọi thứ khỏe mạnh. Khả năng phục hồi sau lỗi thường tạo burst lớn hơn tải steady state.

## 14. Checklist ước lượng trước triển khai

- Đếm số service logic S và tổng instance I theo từng môi trường.
- Đếm số consumer/discovery client C thực sự fetch hoặc query registry.
- Xác định renewal interval T_r, fetch interval T_f và health interval T_h.
- Tính renewal, fetch và health probe rate trung bình.
- Đo kích thước response R để ước lượng băng thông.
- Ước lượng số instance thay đổi trong một đợt rollout và peak churn.
- Tính số watcher hoặc blocking query theo service nếu dùng cơ chế event.
- Xác định các lớp cache và thời gian dữ liệu có thể stale.
- Đo peak QPS, latency, heap và network trong bài load test.
- Thiết lập cảnh báo cho lỗi renewal, fetch, health check, session expiration và registry latency.
- Chừa headroom cho burst, retry và một phần node registry bị lỗi.

## 15. Nguyên tắc tối ưu

- Tối ưu theo tổng instance và số consumer, không chỉ theo số service logic.
- Tách renewal, fetch, health check, watch và registration churn khi tính tải.
- Tính cả kích thước payload và băng thông, không chỉ đếm QPS.
- Chọn chu kỳ dựa trên yêu cầu freshness và khả năng chịu tải.
- Dùng cache để giảm truy vấn lặp nhưng phải hiểu thời gian stale.
- Dùng watch hoặc blocking query khi phù hợp với registry thay cho polling quá dày.
- Phân tán startup, retry và rollout để tránh thundering herd.
- Không giảm lease/session timeout thấp hơn mức chịu được của mạng và JVM.
- Đo steady state lẫn burst/recovery trước khi xác định capacity.
- Theo dõi cả registry, provider và consumer vì tải được phân bố ở nhiều thành phần.

Ước lượng tải service discovery là bài toán kết hợp số instance, số client và tần suất cập nhật. Công thức đơn giản giúp dự báo mức trung bình; kích thước payload, fan-out, cache, burst và cơ chế riêng của Eureka, Consul hoặc ZooKeeper quyết định tải thực tế. Hãy dùng mô hình để lập kế hoạch ban đầu, sau đó xác nhận bằng metrics và load test ở quy mô gần production.
