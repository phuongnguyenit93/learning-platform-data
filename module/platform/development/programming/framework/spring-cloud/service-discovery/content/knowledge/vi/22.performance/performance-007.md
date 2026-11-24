# Đo tải khi khởi động đồng loạt và phục hồi cả cụm

## 1. Vì sao phải đo hai tình huống này?

Một hệ thống microservice có thể hoạt động ổn định khi chạy đủ instance nhưng gặp sự cố khi nhiều instance khởi động cùng lúc hoặc khi cả cụm registry vừa phục hồi. Trong các thời điểm đó, nhiều thành phần cùng phát sinh công việc:

- Ứng dụng khởi tạo Spring context, kết nối database, nạp cache và warm-up.
- Nhiều client cùng đăng ký service, gửi heartbeat và tải registry.
- Registry cập nhật trạng thái, replication dữ liệu và health checks.
- Consumer làm mới discovery cache và bắt đầu gửi request tới các instance mới.
- Kubernetes scheduler, kubelet, EndpointSlice controller và API Server xử lý Pod/Service thay đổi.
- DNS, gateway, service mesh, message broker và database nhận thêm kết nối hoặc retry.

Nếu chỉ đo throughput của endpoint nghiệp vụ ở trạng thái ổn định, nhóm vận hành sẽ bỏ sót **startup storm** và **recovery storm**. Hai tình huống này có thể làm registry, API Server hoặc dependency bị quá tải ngay cả khi tổng số request nghiệp vụ chưa cao.

Mục tiêu của bài đo là xác định hệ thống chịu được bao nhiêu instance cùng khởi động, mất bao lâu để chúng sẵn sàng, mức tải đỉnh mà registry/control plane phải xử lý và thời gian toàn cụm quay lại SLO sau sự cố.

## 2. Phân biệt startup storm và recovery storm

| Tình huống | Điều gì xảy ra đồng thời? | Rủi ro chính |
|---|---|---|
| Cold start toàn cụm | Tất cả ứng dụng và registry client khởi tạo từ trạng thái lạnh | CPU/GC, DNS, kết nối database, đăng ký và fetch registry tăng đột biến |
| Scale-out lớn | Nhiều replica mới được tạo trong một cửa sổ ngắn | Registration burst, health check burst, image pull và warm-up cạnh tranh tài nguyên |
| Registry restart | Eureka/Consul server hoặc một phần control plane khởi động lại | Client reconnect, retry, full registry fetch, leader election và replication |
| Network partition phục hồi | Các node và client kết nối lại sau thời gian mất mạng | Heartbeat/fetch dồn, catalog reconciliation và dữ liệu cache chưa đồng nhất |
| Node/pool phục hồi | Nhiều Pod được schedule lại sau node failure hoặc maintenance | Scheduler, image registry, API Server, CNI, DNS và dependency cùng chịu tải |
| Dependency phục hồi | Database/broker/API bên ngoài trở lại | Retry queue và connection pool của nhiều service cùng hoạt động trở lại |

Startup storm thường bắt đầu từ một hành động triển khai hoặc scale. Recovery storm có thể xảy ra sau một sự cố mà không có thao tác deploy mới. Hãy đo riêng từng loại để tìm đúng nút thắt.

## 3. Những đại lượng cần đo

Không chỉ ghi nhận CPU và số request. Một bài đo tốt cần có mốc thời gian, tải đỉnh, độ trễ, lỗi và mức độ hội tụ của registry.

### 3.1. Các mốc thời gian của một instance

| Mốc | Định nghĩa |
|---|---|
| `t0` | Thời điểm phát lệnh tạo hoặc khởi động instance |
| `t_process` | Process/JVM bắt đầu chạy |
| `t_server` | Web server bind cổng và bắt đầu lắng nghe |
| `t_registered` | Registry chấp nhận bản đăng ký hoặc nền tảng tạo endpoint |
| `t_ready` | Readiness của ứng dụng chuyển sang cho phép nhận traffic |
| `t_visible` | Consumer thử discovery và nhìn thấy instance đủ điều kiện |
| `t_first_ok` | Request nghiệp vụ đầu tiên tới instance thành công |
| `t_failure_recovery_start` | Thời điểm bắt đầu khôi phục sau khi sự cố được xử lý hoặc fault injection kết thúc |
| `t_slo` | Thời điểm các chỉ số chính (latency, error rate, throughput) trở lại SLO đã định |

Từ các mốc này có thể tính:

- **Startup duration:** `t_ready - t0`.
- **Registration duration:** `t_registered - t0`.
- **Discovery propagation delay:** `t_visible - t_registered`.
- **Time to first successful request:** `t_first_ok - t0`.
- **Recovery time:** `t_slo - t_failure_recovery_start`, tính từ lúc bắt đầu khôi phục sau sự cố đến khi traffic trở lại SLO liên tục trong cửa sổ xác nhận.

Không phải registry nào cũng có một sự kiện `registered` giống nhau. Với Kubernetes, có thể dùng thời điểm Pod/Service được tạo và EndpointSlice chuyển endpoint sang ready. Với Eureka/Consul, dùng log/metric của client và server để xác định thời điểm nhận đăng ký, sau đó kiểm tra từ consumer.

### 3.2. Chỉ số tải và chất lượng

| Nhóm | Chỉ số nên thu thập |
|---|---|
| Ứng dụng | Startup duration, time-to-ready, CPU, memory, GC pause, thread count, connection pool, queue depth |
| Discovery client | Số lần register/renew/fetch, request latency, retry count, timeout, cache refresh duration, số instance nhìn thấy |
| Registry server | Request rate, p50/p95/p99 latency, 4xx/5xx, CPU, heap, GC, thread pool, connection count, queue/backlog |
| Health check | Số check/s, pass/warning/critical, check duration, timeout và trạng thái chuyển đổi |
| Kubernetes control plane | API request rate/latency, 429/5xx, inflight requests, watch reconnect/relist, EndpointSlice update delay, etcd latency |
| Hạ tầng | DNS latency/error, network throughput, conntrack, packet loss, disk I/O, node pressure và image pull duration |
| Traffic nghiệp vụ | Request rate, p50/p95/p99, error rate, timeout, retry, saturation và số request bị gửi tới instance chưa ready |
| Phục hồi | Time to registry healthy, time to all instances visible, time to SLO, stale instance count và số lần retry còn tồn đọng |

Luôn ghi số liệu theo cửa sổ thời gian ngắn đủ để thấy đỉnh tải. Trung bình 5 phút có thể che mất một burst kéo dài 5 giây.

## 4. Ước lượng tải trước khi chạy thử

Các công thức dưới đây giúp ước lượng tải nền. Chúng không thay thế phép đo tải đỉnh vì client có thể đồng bộ thời điểm gửi request.

Giả sử:

- `N`: số instance được khởi động.
- `S`: khoảng thời gian mà các instance được trải đều để khởi động.
- `H`: chu kỳ heartbeat/renewal.
- `C`: số consumer thực hiện fetch registry.
- `F`: chu kỳ fetch registry của một consumer.
- `Q`: số lần health check mỗi instance trong một giây.

Tải trung bình xấp xỉ:

\[
R_{register} \approx \frac{N}{S}
\]

\[
R_{heartbeat} \approx \frac{N}{H}
\]

\[
R_{fetch} \approx \frac{C}{F}
\]

\[
R_{health} \approx N \times Q
\]

Ví dụ minh họa: 900 instance được trải đều trong 90 giây tương ứng khoảng 10 lần đăng ký mỗi giây. Nếu 900 instance khởi động trong vài giây đầu, tải đỉnh có thể cao hơn rất nhiều so với mức trung bình 10 lần/giây. Nếu mỗi client retry đồng loạt sau timeout, tải thực tế còn tăng thêm.

### 4.1. Vì sao trung bình không đủ?

Giả sử 1.000 client có cùng chu kỳ fetch 30 giây và được khởi động trong cùng một thời điểm. Mức trung bình lý thuyết là khoảng 33 fetch/giây, nhưng nếu các timer được tạo gần như đồng pha, nhiều request có thể đến server trong cùng một khoảng ngắn. Cần quan sát histogram theo giây hoặc nhỏ hơn để phát hiện hiện tượng này.

Các chu kỳ và mặc định phải lấy từ phiên bản/cấu hình đang chạy. Ví dụ, cấu hình Spring Cloud Netflix hiện hành công bố `eureka.client.registry-fetch-interval-seconds` mặc định 30 giây; client Eureka cũng dùng heartbeat định kỳ. Không suy ra tải thực tế chỉ từ mặc định vì số client, retry, full fetch, peer replication và kích thước registry đều ảnh hưởng.

### 4.2. Tải retry có thể khuếch đại burst

Nếu `N` client cùng timeout và cùng retry sau một khoảng cố định, lần retry tiếp theo lại tạo một burst mới. Dùng exponential backoff có jitter để phân tán thời điểm thử lại:

\[
delay_k = U\left(0,\; \min(delay_{max}, delay_{base} \times 2^k)\right)
\]

Trong đó `U(0,x)` là giá trị ngẫu nhiên trong khoảng từ 0 đến `x`. Kết hợp giới hạn số lần retry, timeout, retry budget và circuit breaker ở tầng gọi service. Không retry vô hạn hoặc retry tất cả lỗi 4xx.

## 5. Thiết kế bài thử có thể lặp lại

### 5.1. Chuẩn bị môi trường

Môi trường thử nghiệm cần đủ giống production ở các yếu tố ảnh hưởng tới kết quả:

- Cùng loại registry, số node, replication/peer topology và cấu hình health check.
- Số instance, kích thước registry, số service và số consumer tương đương mục tiêu.
- CPU/memory limit, JVM heap, garbage collector, network và storage tương đương.
- Cùng cách triển khai, DNS, gateway, service mesh, database và message broker.
- Cùng phiên bản Spring Boot, Spring Cloud, Eureka/Consul/Kubernetes và client library.
- Đồng bộ clock giữa load generator, ứng dụng và registry để so sánh timestamp.

Không dùng registry trống nếu production có hàng nghìn service/instance. Kích thước registry ảnh hưởng payload fetch, serialization, memory và thời gian cache refresh.

### 5.2. Tách tải control plane và data plane

Nên chạy ít nhất hai nhóm đo:

1. **Control plane load:** registration, heartbeat, fetch, health check, Kubernetes API watch/list, leader election và replication.
2. **Data plane load:** request nghiệp vụ qua gateway, Kubernetes Service hoặc Spring Cloud LoadBalancer.

Nếu chỉ tạo request HTTP tới ứng dụng mà không quan sát registry/control plane, bài thử không đo được áp lực đăng ký. Ngược lại, nếu chỉ bắn request vào registry endpoint, kết quả không đại diện cho traffic nghiệp vụ.

### 5.3. Xác định mức tải mục tiêu

Tối thiểu cần biết:

- Số instance hiện tại và số instance tối đa.
- Số instance có thể khởi động trong một phút và trong một giây ở kịch bản xấu nhất.
- Số consumer và chu kỳ fetch/refresh.
- Số health check trên mỗi instance và chu kỳ kiểm tra.
- Kích thước registry, metadata trung bình và tốc độ thay đổi.
- Mức request nghiệp vụ bình thường và đỉnh trong lúc rollout.
- Thời gian phục hồi tối đa chấp nhận được.

Ghi rõ giả định trước khi chạy. Không điều chỉnh thông số giữa một lượt thử mà không ghi nhận vì sẽ làm kết quả khó so sánh.

## 6. Các kịch bản thử nghiệm chính

### 6.1. Baseline khi cụm ổn định

1. Khởi động toàn bộ service theo quy trình bình thường.
2. Chờ registry và traffic ổn định.
3. Tạo traffic nghiệp vụ ở mức nền trong một khoảng đủ dài.
4. Ghi CPU, memory, GC, registry request rate, health check, p95/p99 và error rate.

Baseline là mốc so sánh cho mọi kịch bản sau. Nếu hệ thống chưa ổn định ở baseline, chưa nên thử startup storm.

### 6.2. Khởi động đồng loạt toàn bộ instance

1. Dừng hoặc scale về trạng thái kiểm thử đã định trước.
2. Giữ registry ở trạng thái hoạt động để cô lập tải từ client.
3. Phát lệnh khởi động `N` instance trong một cửa sổ thời gian rất ngắn.
4. Theo dõi registration, heartbeat, fetch, health check và thời gian ready.
5. Kiểm tra consumer có nhìn thấy đủ instance và request có tới đúng instance ready không.
6. Lặp lại với nhiều giá trị `N` và cửa sổ khởi động khác nhau.

Không chỉ ghi thời gian instance đầu tiên sẵn sàng. Cần ghi p50/p95/p99 của `t_ready`, thời điểm instance cuối cùng ready và tỷ lệ instance không thể đăng ký.

### 6.3. Scale-out theo từng đợt

Thử các đợt tăng replica có kiểm soát, ví dụ 10%, 25%, 50% rồi 100% quy mô mục tiêu. Mỗi đợt cần chờ hệ thống ổn định hoặc ghi rõ nếu cố tình chồng lấn các đợt.

Mục đích là xác định ngưỡng mà từ đó:

- Registry latency bắt đầu tăng nhanh.
- Registration retry hoặc timeout xuất hiện.
- Database/connection pool của service bị bão hòa.
- Thời gian từ đăng ký đến consumer nhìn thấy tăng vượt mục tiêu.
- Error rate của traffic nghiệp vụ vượt SLO.

### 6.4. Khởi động lại registry trong khi client còn chạy

Thực hiện theo topology và quy trình failover của từng registry:

- Restart một node registry trong cụm HA, giữ các node peer còn lại hoạt động.
- Trong môi trường thử nghiệm riêng, restart lần lượt các node và kiểm tra quorum/leader/peer recovery.
- Quan sát client reconnect, retry, fetch lại registry và giữ cache cũ trong thời gian mất kết nối.
- Kiểm tra sau khi registry phục hồi: dữ liệu có hội tụ không, instance mới có xuất hiện không và instance cũ có bị giữ quá lâu không.

Không restart đồng thời toàn bộ registry trong môi trường production để tạo tải thử. Nếu muốn kiểm tra mất toàn cụm, dùng môi trường cô lập có dữ liệu và topology tương đương.

### 6.5. Mô phỏng network partition rồi khôi phục

1. Chặn có kiểm soát đường mạng giữa một nhóm client và registry hoặc giữa các peer.
2. Duy trì traffic nghiệp vụ trong giới hạn an toàn để quan sát hành vi khi registry mất kết nối.
3. Ghi lại retry, timeout, stale cache, trạng thái health và số instance nhìn thấy.
4. Khôi phục mạng.
5. Đo thời gian heartbeat/fetch/replication trở lại bình thường và thời gian registry hội tụ.
6. Kiểm tra request không bị dồn vào một nhóm instance do discovery view chưa đồng nhất.

Kịch bản này đặc biệt quan trọng với Eureka self-preservation và Consul catalog replication. Registry có thể giữ thông tin cũ để tránh loại nhầm instance trong sự cố mạng; consumer vẫn phải timeout nhanh và xử lý instance không còn phục vụ.

### 6.6. Node failure và reschedule hàng loạt

Trong Kubernetes, mô phỏng node drain hoặc mất node trong cluster test. Quan sát scheduler, image pull, Pod startup, readiness probe, EndpointSlice update, API Server và etcd. Cần theo dõi cả tải image registry và CNI vì chúng có thể kéo dài startup dù discovery client không phải nút thắt.

### 6.7. Dependency phục hồi sau thời gian gián đoạn

Tạm làm chậm hoặc ngắt database/broker ở môi trường thử nghiệm, sau đó khôi phục. Kiểm tra connection pool có mở lại đồng loạt không, retry queue có dồn request không và readiness có chuyển trạng thái phù hợp không. Một registry khỏe không có nghĩa dependency nghiệp vụ đã phục hồi.

## 7. Công cụ tạo tải và thu thập số liệu

### 7.1. Tạo tải request nghiệp vụ bằng k6

k6 phù hợp để tạo tải HTTP có arrival rate kiểm soát. Đo request qua đúng đường traffic mà ứng dụng sẽ dùng trong production; không dùng endpoint registry làm đại diện cho request nghiệp vụ.

Ví dụ tăng dần request rate:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    payment_traffic: {
      executor: 'ramping-arrival-rate',
      startRate: 20,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 500,
      stages: [
        { target: 50, duration: '2m' },
        { target: 100, duration: '3m' },
        { target: 150, duration: '3m' },
        { target: 0, duration: '1m' }
      ]
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000']
  }
};

export default function () {
  const response = http.get(`${__ENV.BASE_URL}/api/payments?limit=10`);
  check(response, {
    'response is successful': (r) => r.status === 200
  });
}
```

URL và ngưỡng trong ví dụ chỉ để minh họa; thay bằng endpoint nghiệp vụ chỉ đọc có chi phí gần production và SLO của hệ thống. Không dùng liveness/readiness endpoint làm tải data plane chính. Nếu endpoint làm thay đổi dữ liệu, dùng dữ liệu thử riêng và cơ chế cleanup. Để tạo startup storm, cần điều phối việc tạo instance riêng; k6 chỉ tạo request HTTP.

### 7.2. Điều phối scale trong Kubernetes

Trong cluster test, có thể dùng `kubectl scale` để tạo đợt tăng replica:

```bash
kubectl scale deployment/payment-service --replicas=100 -n payments
kubectl rollout status deployment/payment-service -n payments --timeout=10m
```

Để mô phỏng burst mạnh, scale từ số replica thấp lên số lớn trong một lần. Để mô phỏng rollout an toàn, dùng Deployment strategy với `maxSurge` và `maxUnavailable` phù hợp. Không dùng cùng một bài test để kết luận cả hai tình huống vì một bên tạo burst, bên còn lại giới hạn tốc độ thay thế Pod.

Ví dụ rollout giới hạn số Pod được tạo thêm cùng lúc:

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 0
```

`maxSurge: 2` cho phép tối đa hai Pod vượt số replica mong muốn trong quá trình rollout; `maxUnavailable: 0` yêu cầu giữ đủ số replica khả dụng theo điều kiện Deployment. Đây là ví dụ, cần cân đối quota, node capacity và thời gian readiness của ứng dụng.

### 7.3. Thu thập số liệu

- Prometheus/Grafana: scrape metric ứng dụng, registry, node, Kubernetes control plane và dependency.
- Spring Boot Actuator/Micrometer: HTTP server/client, JVM, datasource, executor, cache và custom startup timers.
- Log có timestamp: register success/failure, heartbeat/fetch, retry, health transition và readiness transition.
- Kubernetes: `kubectl get events`, Pod conditions, EndpointSlice, API Server metrics và etcd metrics.
- Load generator: request rate, latency distribution, error rate, dropped iterations và số VU thực tế.

Đồng bộ clock và gắn `serviceId`, `instanceId`, `region`, `zone`, `testRunId` vào log để đối chiếu các nguồn số liệu.

## 8. Chỉ số và đặc điểm cần quan sát theo registry

### 8.1. Eureka

Eureka Client đăng ký instance, gửi heartbeat/renewal và tải registry cache. Khi nhiều client khởi động cùng lúc, server có thể nhận burst registration; sau đó là heartbeat và fetch registry. Nếu cache delta không thể reconcile sau gián đoạn, client có thể cần full registry fetch, tạo payload và CPU cao hơn.

Các điểm cần quan sát:

- Số request register, renew, cancel và registry fetch theo giây.
- Tỷ lệ HTTP timeout/5xx, p95/p99 của request tới Eureka Server.
- Kích thước registry payload, thời gian deserialize/cache refresh và GC của client/server.
- Peer replication lag, peer request failures và số server có registry view khác nhau.
- Tỷ lệ heartbeat renewal và trạng thái self-preservation.
- Số instance `UP`, `DOWN`, `OUT_OF_SERVICE` và số bản ghi stale.

Spring Cloud Netflix hiện công bố `eureka.client.registry-fetch-interval-seconds` mặc định 30 giây; tài liệu giao tiếp Eureka mô tả heartbeat mặc định 30 giây và registry cache được làm mới theo chu kỳ. Giá trị thực tế phụ thuộc cấu hình và release đang chạy. Không giảm heartbeat/fetch interval chỉ để làm dashboard cập nhật nhanh hơn. Thay đổi interval có thể làm tăng tải toàn cụm và ảnh hưởng giả định lease/eviction; chỉ thử trong môi trường kiểm soát và đánh giá cả server lẫn consumer.

Eureka self-preservation có thể giữ instance trong registry khi số heartbeat giảm bất thường để tránh xóa hàng loạt bản ghi trong network partition. Trong test, ghi nhận trạng thái này và xác minh consumer có timeout nhanh, retry sang instance khác khi bản ghi đã stale hay không. Không tắt self-preservation chỉ để làm bài đo trông sạch hơn.

### 8.2. Consul

Ứng dụng thường đăng ký service với Consul Agent cục bộ. Agent quản lý service/check và đồng bộ trạng thái lên catalog; agent dùng anti-entropy để đối chiếu local state với catalog. Vì vậy, bài đo cần quan sát cả agent và Consul server.

Các điểm cần quan sát:

- Số lần register/deregister/check update trên mỗi agent.
- Agent-to-server RPC, lỗi kết nối và thời gian đồng bộ catalog.
- Leader election, Raft commit/apply latency, replication và server CPU/memory.
- Số health check/s, check duration, timeout và trạng thái passing/warning/critical.
- Thời gian từ khi agent nhận đăng ký tới khi catalog/query consumer nhìn thấy.
- Anti-entropy sync và số lần agent phải reconcile local state với catalog.

Consul Agent API `/agent/service/register` là đường đăng ký service vào local agent; agent gửi update tới server để global catalog đồng bộ. Consul anti-entropy có lịch đồng bộ được giãn theo quy mô cluster và agent chọn thời điểm bắt đầu ngẫu nhiên để tránh nhiều node đồng bộ cùng lúc. Dùng agent registration thay vì ghi thẳng Catalog API cho luồng đăng ký thông thường để tận dụng agent state và anti-entropy.

### 8.3. Kubernetes

Với Kubernetes, áp lực discovery có thể đến từ ứng dụng dùng Kubernetes API trực tiếp, Spring Cloud Kubernetes DiscoveryServer hoặc controller của nền tảng. Client thường lấy snapshot bằng LIST rồi theo dõi thay đổi bằng WATCH và `resourceVersion`; khi watch hết hạn hoặc mất kết nối, client cần nối lại và có thể phải list lại.

Các điểm cần quan sát:

- API request rate/latency theo resource và verb (`LIST`, `WATCH`, `GET`).
- HTTP 429/5xx, `Retry-After`, inflight requests và API Priority and Fairness.
- Watch reconnect, relist, số object được đọc và kích thước response.
- etcd request/commit/fsync latency, disk I/O và leader changes.
- Scheduler pending queue, image pull duration, Pod startup, readiness và restart count.
- EndpointSlice update rate và thời gian endpoint chuyển sang ready/not-ready.
- Số watcher/informer và số client đang mở watch.

Ưu tiên watch/informer thay vì polling LIST toàn cluster theo chu kỳ ngắn. Khi nhận HTTP 429, tôn trọng `Retry-After` và dùng exponential backoff. Khi watch resourceVersion không còn hợp lệ, client phải xử lý relist/restart watch theo semantics Kubernetes API. Một số phiên bản API Server còn có thể từ chối WATCH hoặc unpaginated LIST trong lúc watch cache chưa khởi tạo và trả 429; client cần retry thay vì tạo vòng gọi nóng.

Spring Cloud Kubernetes DiscoveryClient có thể theo dõi catalog và cập nhật discovery view; một số chế độ dùng cache. Hành vi, thuộc tính và cách triển khai watcher thay đổi theo phiên bản và loại client, nên đo đúng starter/version đang chạy, không suy từ một phiên bản khác.

## 9. Giảm thundering herd và giới hạn tải đỉnh

### 9.1. Stagger startup

Thay vì khởi động toàn bộ replica trong cùng một giây, chia thành nhiều wave. Mỗi wave chỉ tạo một phần số instance, đợi readiness và registry ổn định đến ngưỡng quy định rồi mới tiếp tục. Trong Kubernetes, điều chỉnh Deployment rolling update (`maxSurge`, `maxUnavailable`) hoặc dùng rollout orchestration.

### 9.2. Jitter cho retry và tác vụ định kỳ

Thêm jitter để các client không cùng gửi heartbeat, fetch hoặc retry tại cùng thời điểm. Jitter cần được áp dụng ở tầng có quyền cấu hình; không giả định mọi registry/client đã tự random tất cả timer.

### 9.3. Exponential backoff và retry budget

- Tăng dần khoảng nghỉ sau mỗi lỗi tạm thời.
- Thêm jitter vào thời điểm retry.
- Giới hạn số lần thử hoặc tổng thời gian retry.
- Không retry lỗi cấu hình, xác thực hoặc request không hợp lệ như thể đó là lỗi mạng.
- Dùng circuit breaker/bulkhead cho dependency nghiệp vụ để một sự cố không tạo vô hạn request.

### 9.4. Warm-up có giới hạn đồng thời

Nếu mỗi instance warm-up bằng cách gọi database hoặc nhiều service khác, giới hạn concurrency của warm-up. Có thể dùng semaphore, worker pool hoặc một hàng đợi có giới hạn để tránh hàng trăm instance cùng mở connection pool hoặc chạy truy vấn nặng.

### 9.5. Giữ readiness false trong giai đoạn warm-up

Đăng ký hoặc mở port không có nghĩa là nhận traffic. Dùng readiness probe/health status để instance chỉ vào tập endpoint sẵn sàng sau khi warm-up hoàn tất. Liveness không nên phụ thuộc mọi dependency bên ngoài, nếu không một sự cố database có thể gây restart storm.

### 9.6. Giới hạn tốc độ phục hồi

Đặt concurrency limit cho thao tác phục hồi như reconnect, full fetch, resync và cache rebuild nếu implementation cho phép. Với Kubernetes, tránh controller tự relist toàn cluster liên tục khi API Server trả 429. Với Eureka, không hạ fetch/heartbeat interval đồng loạt mà chưa đo server. Với Consul, giữ anti-entropy và agent registration hoạt động theo thiết kế.

## 10. Kịch bản đo mẫu và tiêu chí nghiệm thu

Một ma trận thử nghiệm có thể dùng như sau:

| ID | Kịch bản | Thao tác | Kết quả cần đo |
|---|---|---|---|
| T0 | Baseline | Cụm ổn định, traffic nền | Latency/error/resource baseline |
| T1 | Burst 25% | Khởi động 25% quy mô mục tiêu trong cửa sổ ngắn | Peak register/fetch, time-to-ready |
| T2 | Burst 50% | Khởi động một nửa cụm | Tỷ lệ timeout/retry, p95/p99 registry |
| T3 | Burst 100% | Khởi động toàn bộ cụm | Thời gian instance cuối cùng ready và consumer nhìn thấy đủ |
| T4 | Scale wave | Tăng replica theo nhiều wave | Throughput ổn định và mức giảm tải đỉnh |
| T5 | Registry node failure | Tắt một node registry trong HA cluster | Client failover, stale cache, peer recovery |
| T6 | Full registry recovery | Khôi phục registry trong test cluster cô lập | Time-to-registry-healthy và time-to-SLO |
| T7 | Network partition | Cắt rồi khôi phục một nhóm kết nối | Retry storm, cache reconciliation và convergence |
| T8 | Node reschedule | Drain/mất node trong Kubernetes | Scheduler/API/EndpointSlice recovery |
| T9 | Dependency recovery | Khôi phục database/broker | Connection storm, queue drain và readiness |

Tiêu chí nghiệm thu cần được xác định trước. Ví dụ:

- 100% instance mục tiêu chuyển sang ready trong thời gian startup tối đa đã thống nhất.
- Tỷ lệ đăng ký thành công đạt mục tiêu; không có instance ID trùng.
- Consumer nhìn thấy instance mới trong propagation SLO.
- Không có request nghiệp vụ tới instance đang readiness false.
- Registry/API Server không vượt giới hạn CPU, memory, connection hoặc inflight request đã đặt.
- 429/5xx và retry không tạo vòng lặp khuếch đại.
- Sau khi registry/dependency phục hồi, traffic p95/p99 và error rate trở lại SLO trong thời gian recovery mục tiêu.
- Không còn stale instance ngoài thời hạn được chấp nhận.

Không dùng một ngưỡng p95 hoặc CPU cố định cho mọi hệ thống. Ngưỡng phải dựa trên SLO, capacity của cluster, số instance, kích thước registry và yêu cầu phục hồi của ứng dụng.

## 11. Ví dụ PromQL để quan sát tải

Tên metric thực tế phụ thuộc Spring Boot/Micrometer, exporter, registry và phiên bản. Các truy vấn sau minh họa cách đo HTTP request rate và p95:

Các ví dụ dùng label `service`; nếu hệ thống không xuất label này, hãy thêm common tag/relabel phù hợp hoặc thay bằng label hiện có như `application`. Trước khi dùng query trong dashboard, xác nhận metric và label thực tế tại Prometheus.

```promql
sum by (service) (
  rate(http_server_requests_seconds_count[1m])
)
```

```promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Tỷ lệ lỗi HTTP server:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
```

Với Kubernetes API Server, tùy cluster có thể quan sát metric như `apiserver_request_total`, `apiserver_request_duration_seconds_bucket` và `apiserver_current_inflight_requests`. Hãy lọc theo resource, verb, code và client nếu label có sẵn.

Với Eureka/Consul, dashboard nên tách metric theo loại request hoặc operation; nếu chưa có metric chi tiết, bổ sung log/metric ở client hoặc proxy để phân biệt register, heartbeat, fetch và health check. Đừng gộp tất cả thành một đường `http_requests_total` vì sẽ khó tìm đúng nguồn tải.

### 11.1. Mẫu ghi kết quả cho mỗi lượt thử

| Trường | Giá trị cần ghi |
|---|---|
| `testRunId` | ID duy nhất của lượt thử |
| Phiên bản | Spring Boot, Spring Cloud, registry, Kubernetes và client |
| Quy mô | Số service, instance, consumer và kích thước registry |
| Kích hoạt | Cold start, burst %, scale wave, registry restart, partition hoặc node failure |
| Cửa sổ startup | Số giây từ instance đầu tiên đến instance cuối cùng được tạo |
| Peak register/fetch | Request/giây và thời điểm đạt đỉnh |
| Registry p95/p99 | Độ trễ theo operation |
| Lỗi/retry | Timeout, 429, 5xx, retry count và dropped iterations |
| Time-to-ready | p50/p95/p99 và thời điểm instance cuối cùng ready |
| Time-to-visible | p50/p95/p99 và thời điểm consumer nhìn thấy đủ instance |
| Recovery time | Thời gian từ khi bắt đầu phục hồi đến khi SLO ổn định trở lại |
| Kết luận | Pass/fail, nút thắt, thay đổi cần thử tiếp |

Giữ nguyên mẫu này qua các lần chạy để so sánh trước/sau khi thay đổi concurrency, jitter, rollout strategy hoặc registry configuration.

## 12. Phân tích kết quả và tìm nút thắt

Khi bài test thất bại, đối chiếu các mốc và metric theo thứ tự:

1. **Instance không được tạo kịp:** kiểm tra scheduler, quota, image pull, node capacity và startup CPU.
2. **Process chạy nhưng web server chậm mở cổng:** kiểm tra Spring bean initialization, classpath, JIT, GC và warm-up.
3. **Server mở cổng nhưng registration chậm:** kiểm tra DNS, network, registry request latency, auth/TLS, connection pool và retry.
4. **Registration thành công nhưng consumer không thấy:** kiểm tra heartbeat/fetch interval, registry cache, peer replication, Consul catalog sync hoặc Kubernetes EndpointSlice/watch.
5. **Consumer thấy instance nhưng request lỗi:** kiểm tra readiness, health filtering, port/scheme, routing, network policy và dependency.
6. **Sau sự cố không phục hồi:** kiểm tra retry storm, queue backlog, stale cache, leader election, full fetch/relist và giới hạn tài nguyên.

Tìm mốc đầu tiên bị kéo dài. Tối ưu ở tầng đó thường hiệu quả hơn tăng tài nguyên đồng loạt cho toàn bộ hệ thống.

## 13. Các lỗi thử nghiệm thường gặp

| Lỗi | Vì sao kết quả sai | Cách khắc phục |
|---|---|---|
| Chỉ đo request nghiệp vụ | Không thấy tải registration/fetch/control plane | Thu metric registry, API Server và client |
| Chỉ đo trung bình 5 phút | Che burst vài giây | Dùng histogram và scrape/rollup ngắn hơn |
| Registry test trống | Payload/cache nhỏ hơn production | Nạp số lượng service/instance gần mục tiêu |
| Load generator không đủ VU/CPU | Không tạo được arrival rate yêu cầu | Theo dõi dropped iterations và capacity của generator |
| Dùng readiness endpoint làm traffic chính | Không đại diện chi phí nghiệp vụ | Dùng endpoint test có chi phí tương tự production |
| Thay nhiều timeout/interval trong cùng lượt | Không biết thay đổi nào tác động | Thay từng biến, ghi version và config |
| Retry cố định không jitter | Tạo burst giả tạo hoặc khuếch đại sự cố | Thử cả cấu hình hiện tại và backoff/jitter mục tiêu |
| Chạy trực tiếp trên production | Có thể làm sự cố thật lan rộng | Dùng staging/canary hoặc fault injection có giới hạn và phê duyệt |
| Không đồng bộ clock | Mốc thời gian giữa log không thể so sánh | Đồng bộ NTP/chrony và gắn testRunId |

## 14. Checklist trước khi kết thúc bài đo

- [ ] Có baseline ổn định trước thử nghiệm.
- [ ] Đã ghi số instance, consumer, service và kích thước registry.
- [ ] Đã xác định cửa sổ startup và arrival rate mục tiêu.
- [ ] Đo riêng registration, heartbeat, fetch, health check và traffic nghiệp vụ.
- [ ] Đã chạy cold start, scale wave, registry failure, partition recovery và node reschedule phù hợp.
- [ ] Thu p50/p95/p99, error rate, timeout, retry và resource saturation.
- [ ] Ghi `t_registered`, `t_ready`, `t_visible`, `t_first_ok` và time-to-SLO.
- [ ] Theo dõi registry peer/leader/anti-entropy hoặc Kubernetes API/etcd/EndpointSlice.
- [ ] Kiểm tra readiness ngăn request tới instance chưa sẵn sàng.
- [ ] Xác minh retry có backoff/jitter và không tạo retry storm.
- [ ] Chạy lặp lại ít nhất một lần với cùng cấu hình để kiểm tra tính ổn định.
- [ ] Ghi rõ cấu hình, phiên bản, kết quả và giới hạn của môi trường test.

## 15. Kết luận

Đo tải khi khởi động đồng loạt và phục hồi cả cụm phải bao gồm cả control plane lẫn data plane. Hãy đo số lần đăng ký, heartbeat, fetch, health check, API watch/list và replication cùng với thời gian từ process start đến ready, từ registration đến discovery và từ sự cố đến khi traffic trở lại SLO.

Khởi động theo wave, retry có exponential backoff và jitter, warm-up có giới hạn đồng thời, readiness gate và cache/watch hợp lý giúp giảm thundering herd. Kết quả tốt không chỉ là mọi instance đã chạy, mà là registry hội tụ, consumer nhìn thấy đúng instance khỏe và toàn bộ hệ thống phục hồi trong thời gian mục tiêu mà không vượt capacity.

## Tài liệu tham khảo

- [Spring Cloud Netflix – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Netflix – Eureka Client and Registration](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Netflix Eureka – Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Netflix Eureka – Self Preservation Mode](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)
- [Consul – Agent Service HTTP API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Consul – Consistency and Anti-Entropy](https://developer.hashicorp.com/consul/docs/concept/consistency)
- [Spring Cloud Kubernetes – DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)
- [Kubernetes – API Concepts, List and Watch](https://kubernetes.io/docs/reference/using-api/api-concepts/)
- [Kubernetes – Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
